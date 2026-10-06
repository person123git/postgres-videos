# pgvideo

pgvideo turns a storyboard into a narrated MP4. A storyboard is one JSON file:
the scenes of a video, with what each screen shows and what is said over it.
`scripts/pgvideo build` narrates it with a local Kokoro model, times captions
and scenes from the measured audio, renders the slides, and encodes, checks,
and delivers the MP4. A later build with exactly the same inputs reuses the
video.

The videos explain pages of
[person123git/postgres-llm-wiki](https://github.com/person123git/postgres-llm-wiki).
**The content is written by an LLM harness** that follows
[AGENTS.md](AGENTS.md): it downloads the wiki into the request's run directory,
reads the page, writes a plan and the storyboard, and calls `build`. pgvideo
does not download or read the wiki, does not plan or review, and does not check
what a storyboard says. It is the narration and video generation utility, and
nothing else.

The Python runtime, packages, models, tools, caches, and outputs all stay inside
this directory, and every pgvideo command runs in a Linux sandbox.

## Prerequisites

- **Linux on x86_64** for the local runtime, Kokoro, FFmpeg, and Chromium:
  kernel 6.7 or newer with Landlock enabled, and glibc 2.28 or newer.
  `scripts/setup` provisions all of them inside the project, except the system
  libraries that headless Chromium links to. On Debian and Ubuntu these come
  from `libnss3`, `libnspr4`, `libglib2.0-0`, `libdbus-1-3`, `libatk1.0-0`,
  `libatk-bridge2.0-0`, `libatspi2.0-0`, `libasound2`, `libgbm1`, `libexpat1`,
  `libudev1`, `libxkbcommon0`, `libx11-6`, `libxcb1`, `libxcomposite1`,
  `libxdamage1`, `libxext6`, `libxfixes3`, and `libxrandr2`; recent releases
  add a `t64` suffix to some of these names. `doctor` names a missing library.
- **An LLM harness**, to write the content: one that can read repository
  instructions, read and write files, run local commands, and download the wiki
  from GitHub with `curl` and `tar`. The harness brings its own model
  connection and credentials; pgvideo never calls a model
  and never sees those credentials. A storyboard written by hand works too.

## Quick start

```sh
/path/to/postgres-videos/scripts/setup
```

`setup` provisions everything the project needs and ends with an offline sample.
Then open the repository in your harness and ask for a video:

> Read this project's AGENTS.md and generate a summary video from
> wiki/v18/questions/observability/track-activity-query-size.md for a PostgreSQL
> administrator. Aim for three minutes.

The harness downloads the latest wiki into `runs/<id>/wiki_content/`, reads the
page there, writes `runs/<id>/scratch/plan.json` and
`runs/<id>/scratch/storyboard.json`, and runs:

```sh
scripts/pgvideo build --storyboard runs/<id>/scratch/storyboard.json --request <id> --json
```

It finishes by reporting the delivered files:

```text
output/<id>/track-activity-query-size.mp4
output/<id>/transcript.md, captions.srt, captions.vtt, references.md,
  quality-report.json, manifest.json
```

Ask the harness to continue a request later; what it wrote is in
`runs/<id>/scratch/`, and the wiki it downloaded and the last build are beside
it in `runs/<id>/`.

## Commands

Every command runs through `scripts/pgvideo`.

| Command | What it does |
| --- | --- |
| `build --storyboard <file> [--request <id>] [options]` | Imports the storyboard, then narrates, times, renders, checks, and delivers it. A new `--request` name starts a request; an existing one is rebuilt in place. Without `--request`, a new request gets a generated ID. |
| `build --request <id>` | Builds the request's imported storyboard again, for example after an interrupted build. |
| `narrate --request <id> [--refresh-unit <unit>] [--lufs] [--true-peak]` | Repeats narration, then timing, rendering, and the checks. |
| `timing --request <id>` | Repeats timing, then rendering and the checks. |
| `render --request <id> [--crf] [--audio-bitrate]` | Repeats rendering and the checks. |
| `validate --request <id>` | Repeats the media checks and the delivery. |
| `doctor [--sample]` | Checks the local environment; `--sample` also makes a short offline narration, slide, and MP4. |
| `test [--pattern <glob>]` | Runs the test suite in the offline sandbox. |

### `build` options

| Option | Default | Meaning |
| --- | --- | --- |
| `--storyboard <file>` | the request's imported storyboard | Storyboard file (JSON or YAML) inside the project. |
| `--request <id>` | a generated ID | The request's name: the directory under `runs/` and `output/`. |
| `--voice`, `--language`, `--speed` | `af_heart`, `a`, `1.0` | Kokoro voice, language code, and speaking speed. |
| `--width`, `--height` | `1920`, `1080` | Video size; both must be even. |
| `--output <dir>` | `output` | Output directory inside the project. |
| `--no-reuse` | off | Builds the narration and MP4 even when a validated video with the same inputs exists. |
| `--json` | off | Prints one result as JSON on standard output; progress goes to standard error. |

A request remembers the options it was built with, so a rebuild needs only the
ones that change.

### Result and exit status

With `--json`, `build` prints:

```json
{"request_id": "…", "stage": "validation", "status": "completed", "issues": [],
 "duration_seconds": 184.3,
 "delivery": {"directory": "…/output/<id>", "video": "…/output/<id>/<page>.mp4",
              "files": [{"path": "…", "sha256": "…"}]},
 "message": "Delivered …"}
```

| Status | Exit | Meaning |
| --- | --- | --- |
| `completed` | 0 | The video and its files are delivered. |
| `needs_review` | 3 | Narration or rendering cannot handle something in the storyboard (`stage` is `storyboard`, with `issues`), or a media measurement is outside its limits (`stage` is `validation`; see `runs/<id>/quality-report.json`). |
| `failed` | 1 | An error, such as a storyboard that does not match its schema, a slide whose content overflows, or a missing local tool. `stage` names where it stopped. |

A result folds more than three issues of one code into one issue with a `count`,
the first messages as `examples`, and the scenes it names;
`runs/<id>/script.md` lists each one.

## The storyboard

[schemas/storyboard.schema.json](schemas/storyboard.schema.json) is the format,
and [prompts/draft.md](prompts/draft.md) says how to write one.

```json
{
  "schema": "pgvideo/storyboard/v3",
  "title": "How track_activity_query_size is used",
  "document": {"path": "wiki/v18/questions/observability/track-activity-query-size.md", "version": 18},
  "scenes": [
    {"id": "answer", "part": "answer", "title": "Short answer",
     "screen": {"layout": "bullets", "heading": "Short answer",
                "lines": ["`track_activity_query_size` sets the slot size"]},
     "narration": [{"text": "`track_activity_query_size` sets the size of each slot.",
                    "origin": "document", "sources": ["Short Answer"]}],
     "citations": [{"text": "guc_tables.c", "url": "https://…"}]}
  ]
}
```

- `title` and `document` describe the video. Every slide shows the PostgreSQL
  version above its heading and the page's path in its footer.
- A scene is one screen held while its narration plays. Its `screen` has a
  `layout` (`title`, `question`, `bullets`, `steps`, `code`, `table`,
  `diagram`, `terms`, `image`, or `credits`) and that layout's content. An
  `image` names a file inside the project by its path from the project root,
  such as a figure under `runs/<id>/wiki_content/`.
- A narration item's `text` is what the captions show, with code in backticks.
  pgvideo derives the spoken text from `pronunciation/en.yaml`; an item may
  carry its own with `tts` and `tts_source: "manual"`.
- `origin`, `sources`, and `citations` say where the content comes from. They
  appear in the transcript and the references; pgvideo does not check them.

Importing a storyboard checks only what narration and rendering depend on:

| Issue | Severity | Meaning |
| --- | --- | --- |
| `unspeakable_tts` | blocking | The spoken text has a symbol Kokoro would read aloud or drop. Add a pronunciation or write the item's `tts`. |
| `diagram_edge` | blocking | An edge names a node the diagram does not have. |
| `missing_image` | blocking | A slide image is not an image file inside the project. |
| `dense_screen`, `long_line`, `long_heading`, `long_code`, `wide_code`, `dense_table` | warning | A screen may be hard to read. The renderer stops only when content does not fit the slide. |
| `empty_screen` | note | A bullets, steps, or question screen has no lines. |

## The plan

[schemas/plan.schema.json](schemas/plan.schema.json) is the format of the plan
a harness writes before the storyboard, and [prompts/plan.md](prompts/plan.md)
says how to write one. It records the request (document, audience, detail, and
duration), the main answer, the claims in teaching order, the caveats, the
time budgets, and the omissions. No pgvideo command reads a plan. Its format is
fixed so that a later session, or another harness, can continue from the file.

## Common tasks

### Make a video

Ask the harness; see [Quick start](#quick-start). To build a storyboard you
wrote yourself:

```sh
scripts/pgvideo build --storyboard path/to/storyboard.json --request my-video
```

### Change a video

Edit the storyboard and run the same `build` command again. The request is
rebuilt in place. Sentences whose spoken text did not change reuse their cached
audio, so only the changed ones are synthesized.

### Continue an interrupted build

```sh
scripts/pgvideo build --request <id>
```

### Fix a pronunciation

Edit `pronunciation/en.yaml`, then build the storyboard again. A sentence can
also carry hand-written TTS text with `tts_source: manual`. To synthesize one
unit again without changing it:

```sh
scripts/pgvideo narrate --request <id> --refresh-unit answer.n2.u1
```

Unit IDs are listed in `runs/<id>/narration/audio-map.json`.

### Re-encode, deliver again, or build instead of reusing

```sh
scripts/pgvideo render --request <id> --crf 18
scripts/pgvideo validate --request <id>
scripts/pgvideo build --request <id> --no-reuse
```

### Check the environment

```sh
scripts/pgvideo doctor             # every check; runs before each command anyway
scripts/pgvideo doctor --sample    # also a short offline narration, slide, and MP4
scripts/pgvideo test               # unit and integration tests
```

## Network and containment

Model inference happens in the harness, outside pgvideo's sandbox, with the
harness's own credentials; the project sandbox does not contain the harness.
pgvideo's commands run in the sandbox: `setup` downloads the locked runtime and
models, and every other command, including narration, rendering, and the media
checks, runs with IP connections denied. No pgvideo command calls a model,
receives inference credentials, or downloads the wiki: the harness downloads the
wiki itself, with `curl`, before it writes anything. See
[Containment](#containment).

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| The harness does not follow the workflow | Tell it to read `AGENTS.md`; not every harness loads it automatically. |
| "does not match schemas/storyboard.schema.json" | The storyboard is malformed or includes fields pgvideo computes, such as statuses or sentence IDs. One rule broken in many scenes is reported as one line. |
| `unspeakable_tts` | Add the term to `pronunciation/en.yaml`, or give the sentence its own `tts` with `tts_source: manual`. |
| "Slide … has overflow, cropped content, or a missing image" | The scene's content does not fit one slide. Split the scene or shorten its lines, code, or table. |
| "Encoded audio loudness is outside delivery limits" | See `runs/<id>/quality-report.json`. Do not lower the audio bitrate: below 192 kb/s the encoder adds more to the true peak. |
| The video is too long or too short | The result's `duration_seconds` is the measured length. Change the storyboard and build again. |
| Command fails before starting | `scripts/pgvideo doctor` names the missing or changed local dependency; `scripts/setup --offline` restores it. |
| "native dependency is missing" names a system library | Headless Chromium links to it. Install the distribution package that provides it; see [Prerequisites](#prerequisites). |
| "project containment cannot be enforced" | The kernel is older than 6.7 or has Landlock disabled. Commands fail rather than run unconfined; see [Containment](#containment). |

## Where files go

| Location | Contents |
| --- | --- |
| `runs/<id>/scratch/` | What the harness writes for a request: `plan.json`, `storyboard.json`, and its notes. Not committed. |
| `runs/<id>/wiki_content/` | The request's copy of the wiki, downloaded by the harness when the request starts: `glossary.md`, `versions.md`, and one `vNN/` directory per PostgreSQL version. |
| `runs/<id>/authored-inbox/`, `runs/<id>/reviews-inbox/` | Files the request receives from someone else: storyboards in `authored-inbox/`, reviews in `reviews-inbox/`. |
| The rest of `runs/<id>/` | One request's build: `request.json` (its settings), `manifest.json` (stage records), `storyboard.json` (the imported storyboard with spoken text), `script.md`, audio, captions, slides, the draft MP4, and `quality-report.json`. It is kept after delivery so any stage can be repeated. |
| `output/<id>/` | The delivery: `<page>.mp4`, `transcript.md`, `captions.srt`, `captions.vtt`, `references.md`, `quality-report.json`, and `manifest.json`. |
| `cache/` | Downloads and reusable results: narration units in `cache/narration/` and validated videos in `cache/videos/`. |
| `.runtime/` | The local Python runtime, FFmpeg, eSpeak NG, Chromium, temporary files, and `environment-report.json`. |
| `AGENTS.md`, `prompts/`, `schemas/` | The harness's instructions, how to write the plan and the storyboard, and their formats. |

Deleting a request's directory under `runs/` deletes the request: its plan,
storyboard, and notes go with its wiki copy and its build, and its video can no
longer be reused. The delivered files in `output/<id>/` stay.

## How it works

### Local environment

`scripts/setup` provisions a project-local Python 3.11.16 runtime and `.venv/`,
a hash-locked wheelhouse, the Kokoro model and voice, an English language model,
bundled fonts, Playwright's headless Chromium, FFmpeg, and the eSpeak NG library
and data. The current `tools.lock` supports Linux x86_64. PyTorch is the
CPU-only build from download.pytorch.org, because PyPI's Linux wheel depends on
the CUDA libraries, which narration on the CPU never loads. Setup downloads and
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
font, TLS, and tool paths with project-local values, and drops `LD_PRELOAD`,
`LD_LIBRARY_PATH`, and `LD_AUDIT`. Every command then confines itself before it
re-executes: a Landlock ruleset limits file access, and for offline commands a
seccomp filter denies IP sockets. Every program the command starts inherits
both, and neither can be removed.

| Command | Network | File access outside the project |
| --- | --- | --- |
| `setup` | allowed | denied except the operating system paths below and the resolver configuration |
| `setup --offline`, `doctor`, `test`, and every other `scripts/pgvideo` command | IP sockets denied | denied except the operating system paths below |

Sandboxed processes may open files and list directories only inside the
project and in:

- `/usr/lib`, `/usr/lib64`, `/lib`, and `/lib64`: system libraries, the dynamic
  loader, and the locale archive; and `/etc/ld.so.cache`, the loader's index;
- `/usr/share/zoneinfo`;
- `/etc/debian_version`, because pip names the distribution in its user agent
  and fails when the file exists but cannot be read;
- `/proc`;
- `/sys/devices` and `/sys/bus/pci/devices`: PyTorch and Chromium read the
  processor topology, and Chromium's GPU process exits unless it can list the
  PCI devices;
- `/dev/null`, `/dev/zero`, `/dev/random`, `/dev/urandom`, `/dev/tty`, and
  `/dev/pts`.

`setup` may also read `/etc/resolv.conf`, `/run/systemd/resolve`,
`/etc/hosts`, `/etc/nsswitch.conf`, `/etc/host.conf`, and `/etc/gai.conf` to
resolve host names. Processes may write only inside the project and to
`/dev/null` and terminals. They may execute only project files, `/bin/sh`,
`/bin/bash`, `/bin/dash`, and the dynamic loader `/lib64/ld-linux-x86-64.so.2`,
through which the kernel starts every dynamically linked program.

Offline commands cannot create IPv4 or IPv6 sockets, which covers UDP, and
cannot bind or connect TCP sockets. They cannot use `io_uring` either, because
it can create a socket that the filter does not see. Metadata lookups,
Unix-domain sockets, signals, and other local IPC remain available, so system
services such as systemd-resolved and D-Bus can act for a process. A command
started by an already sandboxed process, such as the test suite, keeps that
sandbox; another layer could only narrow it.

Landlock needs Linux 6.7 or newer (ABI 4) with the `landlock` security module
enabled. On a kernel without it, commands fail rather than run unconfined.

Some libraries look outside the project unless configured. Chromium on Linux
loads no font, bundled or not, without a readable Fontconfig configuration, and
the host's is outside the sandbox. The controlled environment therefore sets
`FONTCONFIG_FILE` to `assets/fonts/fonts.conf`, which lists only the bundled
fonts and keeps the font cache in `cache/fontconfig/`. It points
`SSL_CERT_FILE` at the hash-locked `certifi` bundle and sets `OPENSSL_CONF` to
the null device. Setup installs `scripts/sitecustomize.py` into `.venv/`, so
`mimetypes` uses Python's built-in table instead of host files such as
`/etc/mime.types`.

`doctor` runs before every command. It checks interpreter and package
locations, locked artifact hashes, FFmpeg capabilities, browser files, fonts,
and writable directories. It parses the ELF dynamic section of every project
binary and resolves each needed library through `DT_RUNPATH` or `DT_RPATH`,
with `$ORIGIN`, without binutils' `readelf`; each must resolve inside the
project or to a system library under `/usr/lib`, `/usr/lib64`, `/lib`, or
`/lib64`. A system library that is not installed fails this check by name. A
library that only another project directory holds is accepted, because only the
project can supply it. Doctor also attempts four accesses that the sandbox must
deny: writing `/tmp`, reading `/etc/passwd`, running `/usr/bin/true`, and, when
offline, connecting to a TEST-NET address.

`doctor --sample` runs offline. It synthesizes a Kokoro WAV and renders a
1920 × 1080 slide with headless Chromium, then encodes an H.264/Opus MP4 with
`+faststart` and verifies it with ffprobe and a full decode. It confirms
through the DevTools protocol that the slide text used only the fonts in
`assets/fonts/`, and that every native library mapped by the sample came from
the project or the system library directories. Outputs stay in `.runtime/tmp/`.

Doctor writes `.runtime/environment-report.json` with the resolved paths,
versions, sandbox profile, probe results, the last sample result for the
current locks and scripts, operating system requirements, and limitations.
Explicit
`GITHUB_TOKEN`, `HF_TOKEN`, and proxy settings may pass to child processes;
they are not saved in reports.

The sandbox denies the following attempts, and setup and the offline sample
still pass. They were observed once with `strace` on Ubuntu 26.04 (Linux 7.0,
x86_64) during `setup --offline` and `doctor --sample`:

- pip lists `/etc` and runs `lsb_release` and `uname` to describe the host.
- Python's `ctypes.util.find_library` runs `ldconfig`, `gcc`, and `ld`; joblib
  tries to create a semaphore in `/dev/shm`; urllib3 creates an IPv6 socket
  when it is imported; and importing PyTorch reads `/etc/nsswitch.conf` and
  `/etc/passwd`.
- Chromium reads `/etc/hosts`, `/etc/host.conf`, `/etc/nsswitch.conf`,
  `/etc/resolv.conf`, `/usr/share/mime/mime.cache`, and
  `/usr/share/fontconfig/conf.avail`; lists `/dev/dri` and the Vulkan
  configuration under `/etc/vulkan` and `/usr/share/vulkan`; writes
  `/proc/<pid>/oom_score_adj` for its renderers; and creates IPv4 and IPv6 UDP
  sockets.
- Playwright's Node.js driver reads `/etc/resolv.conf` and the memory limits
  under `/sys/fs/cgroup`, and calls `io_uring_setup`.

No command repeats that observation. Landlock denies an access with an error
and cannot terminate the process, and the kernel records denied attempts only
in its audit log (Linux 6.15 or newer), which needs administrator rights. The
macOS version of this project had a kill-on-access `audit` command; Linux has
no unprivileged equivalent, so the command was removed.

The Python archive download, extraction, and `.venv/` creation in
`scripts/setup` run before the sandbox applies, using `/bin/sh`, `/bin/mkdir`,
`/usr/bin/uname`, `/usr/bin/curl`, `/usr/bin/sha256sum`, `/usr/bin/tar`, and
`/usr/bin/env` by absolute path.

### Storyboard import

`build` first reads the storyboard file, checks it against
`schemas/storyboard.schema.json`, and writes `runs/<id>/storyboard.json`: the
same scenes, with an ID for every sentence (`<scene>.n<number>`), the text
Kokoro speaks, the SHA-256 of every slide image, and an estimate of the length.
The estimate uses the speech rate measured in earlier runs with the same voice
and speed, or 150 words per minute until a minute of narration exists.
`runs/<id>/script.md` renders the result for reading and is delivered as
`transcript.md`. Nothing here reads the wiki or compares the storyboard with a
document.

Display text is what the screen and captions show. Spoken text comes from
`pronunciation/en.yaml`: identifiers are split into words, acronyms are spelled
or given a spoken form, and operators become words.

### Kokoro narration

The tool splits dictionary-generated speech at clauses and at 28-word limits.
It synthesizes every Kokoro chunk in order, caches 24 kHz mono WAV units by
exact TTS text and asset versions, and inserts sentence and scene pauses. The
raw master is normalized with FFmpeg's two-pass `loudnorm` at -16 LUFS and
-1.5 dBTP by default. The run contains `narration/units/`,
`narration/master-raw.wav`, `narration/master.wav`,
`narration/audio-map.json`, and `narration/narration-report.md`. The map records
each unit's sample range on the continuous audio clock for timing.

To repeat the audio stage or regenerate a unit after listening:

```sh
/path/to/postgres-videos/scripts/pgvideo narrate --request <id>
/path/to/postgres-videos/scripts/pgvideo narrate --request <id> --refresh-unit opening.n1.u1
```

Manually written TTS stays in one audio unit.

### Timing and subtitles

After narration, the tool measures the normalized master's sample count and
checks every audio unit against the storyboard. It writes `timeline.json` with
scene sample positions and contiguous 30 fps frame ranges. The last visual
frame covers any fraction of a frame after the audio ends. `captions.srt` and
`captions.vtt` use the measured spoken unit boundaries; scene and sentence
pauses remain in the timeline without subtitle text. To rebuild these files
without resynthesizing audio:

```sh
/path/to/postgres-videos/scripts/pgvideo timing --request <id>
```

### Rendering, checks, and delivery

After timing, Playwright renders each storyboard scene to a PNG using the
bundled fonts and a reusable slide template. It rejects overflow, missing
images, and fonts outside the bundle. The renderer holds each PNG for the
scene's measured frame count, then encodes `render/draft.mp4` with H.264 video
at 30 fps and Opus mono audio at 48 kHz. `render.json` records the input and
artifact hashes, and `references.md` lists the page and each scene's citations.
The checks fully decode the draft, verify its streams, timing, caption
coverage, spoken units, silence, and loudness, and then copy the MP4 and its
accompanying files to `output/<id>/`. The run's `quality-report.json` records
the measurements and delivery hashes. These are checks of the media; none of
them looks at what the video says.

The audio is encoded with libopus at 192 kb/s by default. A lower bitrate adds
more to the narration master's true peak (about 0.1 dB at 192 kb/s; 0.5 to
0.8 dB at 128 kb/s and below), toward the true-peak limit that the checks
enforce. Opus in MP4 plays in Chrome, Edge, and Firefox. Apple platforms decode
it from iOS 17; earlier versions play the video without sound.

When a stage runs again, the manifest drops the records of every later stage,
including an earlier validation, so it never describes media that was built
from older inputs. Importing a storyboard also drops the reuse lookup, which
belongs to one storyboard.

### Reuse of validated videos

Before narrating, `build` looks for a validated video with the same key. The
key is the SHA-256 of every input that decides the video:

- the imported storyboard, without its request ID, time, source file name,
  length estimates, and issues. It includes the title, the document's path and
  version, which the slides and references show, every scene's screen and
  narration, and the SHA-256 of every slide image;
- the pronunciation dictionary;
- the voice, language, speed, loudness target, and true-peak limit, and the
  Kokoro model, configuration, and voice files;
- the width, height, frame rate, CRF, and audio bitrate;
- `tools.lock` and `requirements.lock`, which pin the Kokoro assets, eSpeak NG,
  FFmpeg, Chromium, fonts, and Python packages; the slide template and fonts;
  and the code of the speech, narration, timing, rendering, and validation
  modules.

Validation registers each delivered video as
`cache/videos/<key>/<request-id>.json`, with the SHA-256 of its audio map,
render record, unit WAVs, masters, slides, MP4, and references. It registers a
video only when the narration, timing, and render stages ran with the same
tools and code as the validation. A lookup verifies every listed file in the
earlier request's run directory, copies the narration and MP4 into the new
request, and then runs the new request's own timing and validation, so the
delivered video is checked again. A request that is built again without a
change finds its own video and copies nothing. An entry whose files are missing
or changed is reported, skipped, and removed from the index. If the copied
narration or MP4 cannot be used, that stage is built instead. A lookup never
creates, changes, or delivers another request.

The manifest's `reuse` record keeps the key, its components, the lookup's
result, and whether the video was registered. Reused stages name their source
request in `reused_from`, as does the quality report. Commands for one stage
(`narrate`, `timing`, `render`, and `validate`) always repeat it, although
narration units still come from the unit cache when their TTS text and
provenance match. `--no-reuse` builds a fresh video, which is registered in
turn.

### Tests

```sh
/path/to/postgres-videos/scripts/pgvideo test
```

The suite runs inside the offline sandbox in about a minute and a half. Tests
create their temporary fixtures under `.runtime/tmp/`, including the
directories used to simulate escaping paths.

- **Environment:** the sandbox probes, including UDP sockets; the sandbox
  profile and the seccomp filter's verdicts; hostile inherited settings,
  including temporary, cache, model, browser, font, and eSpeak NG paths outside
  the project; tools on `PATH`, and no tools on `PATH` at all; a missing
  project-local ffprobe with a decoy on `PATH`; ELF dependency resolution;
  archive extraction; and the bootstrap pins in `scripts/setup`.
- **Storyboards** (`test_storyboard.py`) cover the import of a storyboard that
  uses every layout, sentence IDs and spoken text, the transcript, the issues
  narration and rendering depend on, the schema as the whole format, slide
  images, the digest that keys a video, and length estimates. They also show
  that changed values, wording, edge directions, and sources import unchanged,
  that the plan schema describes a plan and no code reads one, and that the
  pronunciation rules make identifiers, code, and prose speakable.
- **Builds** (`test_build.py`) run `build` end to end with real FFmpeg and
  Chromium and a deterministic stand-in for Kokoro: the delivered files and the
  JSON result, a request rebuilt in place and from a new storyboard revision,
  reuse between requests, every input that changes the key, changed or missing
  files, tampered index entries, a run directory that already holds the
  downloaded wiki, a storyboard that cannot be narrated, and invalid requests.
- **Timing, rendering, and validation** cover frame-exact timelines and
  captions, slides and references, the media checks, and delivery paths that
  must stay inside the project.
- **Integration** (`test_integration.py`) narrates a three-scene storyboard
  with the real Kokoro model and follows every sample from its chunks to the
  delivered MP4.
