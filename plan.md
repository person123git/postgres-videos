# Plan: generate narrated PostgreSQL videos on demand

Create a tool that generates **one narrated MP4 from one Markdown document specified by the user**. Each request must cross-check the document's subject, terminology, and version-specific explanations against the repository's glossary. Use **Kokoro** for narration.

This file describes the implementation plan. The commands, modules, and configuration below are proposed interfaces to build. Steps 1–13 are built. Their sections below end with implementation notes that record decisions and departures from the original proposal.

## Implementation status

| Step | Status | Notes |
| --- | --- | --- |
| 1. Define the on-demand request | Done | `scripts/pgvideo generate` validates one document and writes `runs/<request-id>/request.json`. |
| 2. Set up a project-contained environment | Done | macOS arm64 only. Every command runs under a macOS Seatbelt sandbox, and `doctor --sample` passes offline. |
| 3. Snapshot the document and glossary together | Done | One resolved wiki commit, a verified PostgreSQL source snapshot, `sources.json`, `source-report.md`, and manifest provenance. |
| 4. Parse the selected document | Done | `document.json` with stable section, block, and sentence IDs and extracted facts, plus a coverage map in `document.json` and `coverage.md`. |
| 5. Index the glossary and select relevant entries | Done | A glossary index built for each request from the glossary it downloaded, and `glossary-matches.json` with ranked, version-scoped matches, ambiguous occurrences, and unmatched terms. |
| 6. Cross-check the subject and claims | Done | `glossary-check.json` and `glossary-check.md` with a result for every matched entry, ambiguous term, and uncovered concept; parameter facts checked against the pinned GUC table; every narrated sentence checked against its citations; and `resolutions.yaml` with `scripts/pgvideo resume` for documented resolutions. |
| 7. Create the narration and storyboard | Done | `draft-input.json`, `storyboard.json`, and `script.md` from a deterministic built-in drafter, a drafter command, or an edited scene file; every scene traced to the document and validated, rewritten sentences rechecked, and TTS text kept apart from display text through `pronunciation/en.yaml`. |
| 8. Generate Kokoro narration | Done | Cached 24 kHz sentence/clause WAVs, deliberate pauses, two-pass loudness normalization, and a sample map. |
| 9. Build timing and subtitles from the audio | Done | Validated sample map, frame aligned scene timeline, and SRT/WebVTT captions. |
| 10. Render visuals and encode the MP4 | Done | Scene PNGs, references, and a frame-aligned draft MP4; Step 11 will validate and finalize delivery. |
| 11. Validate and return the requested video | Done | Full media and quality checks, `quality-report.json`, and a local delivery package. |
| 12. Add reuse and focused implementation checks | Done | Validated videos keyed by every input and reused only on an exact match, stale stage records dropped, small-fixture checks, a real-Kokoro integration check, a full trial, and a kill-on-access isolation audit. |
| 13. Choose the level of detail | Done | `generate --detail summary\|standard\|full`: a summary of the page's key points, the standard condensed video, or every section, planned in the coverage map and followed by every later step. Tables are planned at the words read from their rows, and a condensed table keeps its first rows. |

As of 2026-09-29, `generate` runs through Step 11 and exits with status 0 when every step passes, 3 for `needs_review`, and 1 for errors. `resume --request <id>` repeats Steps 6–11 for an existing request, `script --request <id>` repeats Steps 7–11, `narrate --request <id>` repeats Steps 8–11, `timing --request <id>` repeats Steps 9–11, `render --request <id>` repeats Steps 10–11, and `validate --request <id>` repeats Step 11. After the script passes, `generate`, `resume`, and `script` reuse a validated video with the same inputs unless `--no-reuse` is given. `audit` repeats `setup --offline` and the offline sample under a kill-on-access sandbox profile. `generate --detail summary` or `--detail full` makes a summary of the page's key points or a video of every section instead of the standard condensed video (Step 13).

## Requirements and starting defaults

| Item | Requirement or proposed default |
| --- | --- |
| Trigger | An explicit user request with a required source document; no scheduled or automatic repository-wide generation. |
| Source repository | [person123git/postgres-llm-wiki](https://github.com/person123git/postgres-llm-wiki). |
| Input | One repository-relative `.md` path or a GitHub file URL from that repository. |
| Content scope | The selected document supplies the video's subject and outline. Glossary entries and cited evidence support checking and short explanations. |
| Glossary | [wiki/glossary.md](https://github.com/person123git/postgres-llm-wiki/blob/master/wiki/glossary.md), fetched at the same repository commit as the document. |
| Narration | Local Kokoro inference; English initially, with configurable voice and speed. |
| Python environment | Run all project Python commands through `<project>/.venv/`, created from a pinned Python runtime stored inside the project. |
| Dependency isolation | Keep dependencies, executables, models, caches, configuration, temporary files, and outputs inside the project directory. Fail when a required local dependency is missing. |
| Visuals | Slides with concise text, code excerpts, tables, and diagrams where useful. |
| Video | MP4 containing H.264 video and AAC audio; 1920 × 1080, 16:9, 30 fps. |
| Length | Aim for 6–10 minutes initially; allow longer videos when the document needs them. Preserve the main explanation and material caveats. A request may instead ask for a summary of the key points or for every section (Step 13). |
| Delivery | Local MP4, transcript, subtitles, source references, glossary report, and build manifest. |

The glossary currently declares `verified: false`. Its entries include aliases, checked PostgreSQL versions, version notes, and source citations. Its scope also states that glossary links do not prove a page's claims. The implementation must preserve those distinctions. [Glossary snapshot inspected for this plan](https://github.com/person123git/postgres-llm-wiki/blob/ba57f08bdf73d2f8e02a7faab714904d113f4f06/wiki/glossary.md).

## Step 1 — Define the on-demand request

1. Build a command-line entry point named `pgvideo` with a `generate` command.
2. Require `--document` on every generation request. Accept a repository-relative path or a GitHub `blob` URL for the configured repository.
3. Accept optional settings for repository ref, voice, language, speaking speed, video dimensions, and output directory. Resolve filesystem paths from the project root and reject paths outside it, including `..` traversal and symlink escapes, before accessing request inputs or creating files.
4. For a relative path, default the ref to `master`. For a URL, use its ref; reject a conflicting explicit `--ref`.
5. Validate that the request identifies exactly one existing Markdown file. Return a clear error for a missing document, directory, glob, or unsupported repository.
6. Create a request ID and save the normalized request in `request.json`.

Proposed usage after implementation:

```sh
./scripts/pgvideo generate \
  --document wiki/v18/questions/observability/track-activity-query-size.md \
  --ref master \
  --output output/
```

The user chooses the document. The tool must not choose another article, combine articles into one video, or enqueue unrelated documents.

**Deliverable:** a validated request identifying one document and its requested repository ref.

**Status: done.** Implementation notes:

- `src/pgvideo/cli.py` and `src/pgvideo/sources.py` implement the command. A blob URL is tried at every ref/path split, so refs containing slashes work, and an ambiguous split is rejected.
- Document existence is checked through the GitHub contents API, so the request needs network access. `GITHUB_TOKEN` is optional and helps with rate limits.
- `src/pgvideo/paths.py` validates `--output` and `runs/` against the project root before any GitHub access, and again before writing. The check walks each path component, so traversal and symlink escapes are rejected.
- `--output` is recorded for later steps. Width and height must be positive even integers. The voice and language must already be provisioned locally; only `a`/`af_heart` is provisioned now.
- Request IDs have the form `YYYYMMDDTHHMMSSZ-<12 hex>`. `request.json` is written atomically, and the request starts `manifest.json` with the environment snapshot.
- There is no `config/defaults.yaml`; defaults live in the argument parser.

## Step 2 — Set up an environment contained in the project

1. Provision a pinned Python 3.11 distribution, including its standard library, under `.runtime/python/`. Use that interpreter only to create `<project>/.venv/` with `venv`, then run installation, development, tests, and application commands through `.venv/bin/python`. Require `include-system-site-packages = false`. Do not reuse a globally installed Python, another project's environment, or packages from the user's site directory. A virtual environment retains a relationship to its base Python, so copying its executable alone does not meet this requirement. [Python virtual environment documentation](https://docs.python.org/3.11/library/venv.html).
2. Add `scripts/setup` and a `scripts/pgvideo` launcher that derive the project root from their own location. Create and validate the local directories before loading dependencies. Use explicit local executable paths and a controlled subprocess environment; ignore inherited Python import paths, active environments, package installer settings, and tool search paths. Reject execution through the wrong interpreter. Do not require shell activation or modify the user's shell configuration.
3. Lock direct, transitive, development, and build dependencies with versions and artifact hashes. Store downloaded wheels in `cache/wheels/`, install them into `.venv/`, and keep build environments and compiler caches inside the project. Record Python, native tools, browser builds, platform, architecture, download URLs, and checksums in `tools.lock`. Recreate the environment from these records. Do not use global or user installations, `sudo`, Homebrew, system package managers, or a package manager's shared environment/cache. If a compatible local artifact is unavailable, report the missing prerequisite instead of falling back to a host installation.
4. Use `markdown-it-py` for structured Markdown parsing, a safe YAML loader for front matter, and Jinja2 for slide templates. Enable the Markdown table syntax used by the wiki. [Markdown parser documentation](https://markdown-it-py.readthedocs.io/en/latest/using.html).
5. Install the official `kokoro` package, `soundfile`, PyTorch, and their language dependencies into `.venv/`. Place `espeak-ng`, its pronunciation data, and any native libraries not supplied by the wheels under `.runtime/`; configure explicit local library and data paths. Check transitive native dependencies as well as executables. [Kokoro installation and usage](https://github.com/hexgrad/kokoro).
6. Install Playwright into `.venv/` and its matching Chromium build into `.runtime/browsers/`. Use the same browser location during installation and rendering, with profiles and downloads inside `.runtime/tmp/`. Bundle the chosen fonts in `assets/fonts/` and detect missing fonts instead of silently relying on installed desktop fonts. [Playwright browser locations](https://playwright.dev/python/docs/browsers#managing-browser-binaries), [Playwright screenshots](https://playwright.dev/python/docs/screenshots).
7. Provision pinned FFmpeg and ffprobe executables under `.runtime/bin/`, with required libraries inside the project. Invoke them by absolute project-local paths. Check that the chosen build provides H.264 encoding through `libx264`, AAC encoding, and the required audio filters.
8. Download the selected Kokoro model, voice assets, and language resources into `cache/` during setup. Record upstream revisions and file hashes, then require these fixed local assets during synthesis. Disable automatic model downloads during narration and rendering; a missing asset must produce a setup error. Source retrieval in Step 3 remains an explicit network operation. Start with CPU inference; measure optional acceleration later. [Official Kokoro model](https://huggingface.co/hexgrad/Kokoro-82M).
9. Provide `doctor` through the same launcher. Verify the interpreter, base runtime, import paths, package locations, resolved executables, native libraries, fonts, assets, and all writable directories. Reject dependencies and configured paths that resolve outside the project, except the documented operating system requirements below. Save paths, versions, and remaining platform requirements in `.runtime/environment-report.json` and each request's manifest.

The setup script, launcher, and test runner must share one environment configuration. Resolve the following locations to absolute paths under the project, and pass them to every child process:

| Resource | Required project-local location and configuration |
| --- | --- |
| Python packages | `.venv/`; disable user site packages and inherited `PYTHONPATH`/`PYTHONHOME`. |
| Installer cache | `cache/pip/` through `PIP_CACHE_DIR`; require a virtual environment and disable loading user/system pip configuration. |
| Model caches | `cache/huggingface/` through `HF_HOME`, `cache/torch/` through `TORCH_HOME`; explicitly configure any additional library caches. |
| Browser binaries | `.runtime/browsers/` through `PLAYWRIGHT_BROWSERS_PATH` during both setup and execution. |
| User files and settings | A child-process home under `.runtime/home/`, plus `.runtime/config/`, `.runtime/data/`, and `.runtime/state/` for the corresponding XDG paths; keep the developer's shell environment unchanged. |
| General caches | `cache/` through `XDG_CACHE_HOME`; keep Python bytecode, test caches, and tool-specific caches here or elsewhere inside the project. |
| Temporary files | `.runtime/tmp/` through `TMPDIR`, `TMP`, and `TEMP`, including installer builds, browser profiles, and test fixtures. |
| Sources, runs, and delivery | `cache/sources/`, `cache/glossary/`, `runs/`, and `output/`; validate overrides and resolved symlinks against the project root. |

Explicitly disable ambient installer configuration; choosing a local cache alone does not disable pip's user and system configuration files. If this uses the platform null device, record it as an operating system exception. Do not read credentials from home-directory files; accept explicitly supplied credentials through the environment without persisting them in reports. [pip configuration documentation](https://pip.pypa.io/en/stable/topics/configuration/).

Containment applies to project dependencies and application file access. The host kernel, loader, required operating system libraries/frameworks, devices, and network/certificate services remain platform requirements; the bootstrap also needs a documented minimal set of OS tools to download and unpack the local runtime. Inventory those exceptions and minimize them. A virtual environment is not a filesystem sandbox: verify actual access during setup and a sample run, and report any remaining outside access. If strict filesystem denial is required beyond these documented exceptions, add platform sandbox enforcement before claiming that guarantee.

**Deliverable:** a repeatable environment contained in the project that can synthesize a short sample and render one sample slide, with an isolation report documenting any unavoidable operating system access.

**Status: done.** Implementation notes:

- `tools.lock` supports macOS arm64 only, with Python 3.11.16 under `.runtime/python/`. `requirements.in` lists the direct requirements. `requirements.lock` records every wheel with its SHA-256 digest.
- `scripts/setup` and `scripts/pgvideo` share `scripts/environment.py`, which uses only the standard library. After the first run, `scripts/setup --offline` rebuilds `.venv/` and `.runtime/` from `cache/`.
- Every command runs under a macOS Seatbelt profile applied with `/usr/bin/sandbox-exec`. Reads, writes, and executables are limited to the project and a documented set of OS paths. IP networking is allowed only for `setup` and `generate`. Apple has deprecated `sandbox-exec`; if it is removed, commands fail instead of running unconfined.
- `doctor` runs before every command. It checks interpreter and package locations, locked hashes, Mach-O dependencies, FFmpeg capabilities, fonts, and browser files, and it probes four accesses the sandbox must deny. `doctor --sample` synthesizes a Kokoro WAV offline, renders a 1920 × 1080 slide in headless Chromium, and encodes and fully decodes an H.264/AAC MP4.
- `.runtime/environment-report.json` records the operating system requirements and the remaining limitations. Known outside access includes PyTorch's hard-coded `/tmp` OpenMP registration attempt and Chromium's reads through macOS frameworks. The sandbox denies both, and the sample still passes.
- `scripts/pgvideo test` runs the unit tests inside the offline sandbox.
- The launcher passes the application's and the test runner's exit status through; this change was made during Step 3.

## Step 3 — Snapshot the document and glossary together

1. Resolve the requested repository ref to a full commit SHA once at the start of the request.
2. Retrieve the chosen document and `wiki/glossary.md` from that exact commit. Cache downloads by commit and path under `cache/sources/`. Do not read from a sibling wiki checkout or a shared Git cache.
3. Read the document's metadata, including `version`, `pinned_commit`, and verification fields when present. Check that its PostgreSQL version agrees with its `wiki/vNN/` path and cited source trees.
4. Keep the **wiki repository commit** separate from the **PostgreSQL source commit** recorded in the document. Both belong in the manifest.
5. Preserve the original relative path, bytes, hashes, title, headings, and citations. Resolve relative links against the original document location.
6. Retrieve referenced images or source excerpts only when needed for the selected video. If a cited PostgreSQL file is unavailable in the wiki snapshot, retrieve it from the upstream PostgreSQL repository at the document's recorded source commit.
7. If essential version information conflicts or essential evidence is unavailable, return an actionable report before generating narration.

**Deliverable:** immutable inputs and `manifest.json` with provenance sufficient to reproduce this request.

**Status: done.** Implementation notes:

- `src/pgvideo/snapshot.py` runs after Step 1's validation. It resolves the ref to a full SHA once and reads the document and glossary from that commit's tree. If the document is missing from the resolved commit, the request fails, because the ref moved after validation. The resolved commit is recorded in `sources.json` and `manifest.json`; `request.json` keeps only the requested ref.
- `src/pgvideo/sources.py` (`CommitFiles`) fetches each commit's metadata and recursive tree through the GitHub API. It downloads file contents from `raw.githubusercontent.com` and checks every file against its Git blob ID. The cache layout is `cache/sources/<owner>/<repository>/<commit>/{commit.json,tree.json,files/<path>}`. A cached file that fails the check is downloaded again.
- Changed on 2026-09-29: every new request downloads `wiki/glossary.md` again (`CommitFiles.read(..., refresh=True)`), even when the cache holds a valid copy for the commit, so each request's glossary comes from GitHub rather than from an earlier request's download. A failed or mismatched download fails the request. The glossary is still read from the document's resolved commit, and `resume` and the other retry commands keep the request's own snapshot. The download uses `raw.githubusercontent.com`, so the API call count is unchanged.
- The wiki does not contain its `raw/postgres-NN/` checkouts, so every cited file comes from `postgres/postgres`, GitHub's mirror of the upstream repository, at the document's `pinned_commit`. `git.postgresql.org` is not used because it answered automated downloads with HTTP 429.
- The version checks compare the front matter `version`, the `wiki/vNN/` path, and the `raw/postgres-NN/` tree of every citation. They also read the major version from `configure.ac` (`configure.in` for PostgreSQL 12) at the pinned commit, and compare the pin with the glossary's Source Pins row.
- Every cited file of the document's version is retrieved, not only the files a scene will show. Missing evidence has to be detected before narration, and Step 6 needs the files. Images stored in the wiki are retrieved; external images are not, and they produce a warning.
- `src/pgvideo/markdown.py` reads front matter with a safe YAML loader that rejects aliases. It parses with `markdown-it-py` (CommonMark plus tables) and blanks the front matter lines so parser line numbers match the file. Heading anchors follow GitHub's rules.
- The run directory holds read-only copies under `inputs/wiki/` and `inputs/postgres/`, and `sources.json` with front matter, title, headings, resolved links, source pins, and hashes. It also holds `source-report.md`, which lists issues and an input table with commit-specific links. `manifest.json` gains a `sources` record with the wiki commit and the PostgreSQL commit as separate fields.
- These problems block the request with `needs_review` and exit status 3:
  - version conflicts, and cross-version citations;
  - a missing, invalid, or nonexistent pin, or a pin whose source reports another major version;
  - no citations into the document's own source tree;
  - a missing glossary or unreadable front matter.

  A missing cited file or an invalid line range blocks only when the citation appears outside Contents, Context Reviewed, Source References, and Navigation; in those reference lists it is a warning. Broken anchors and wiki links are also warnings. A retrieval, integrity, or path failure marks the manifest `failed` and exits with status 1.
- On the wiki at commit `ba57f08`, all 70 content pages pass. The only pages flagged are the `vNN/index.md` pages and `wiki/versions.md`, which have no pin or citations. Offline tests use an in-memory GitHub fake. They cover single-commit retrieval, cache reuse and repair, tampered downloads, each blocking check, and cache symlink escapes.
- A Step 3 blocker needs a wiki change and a new request. Steps 6–11 can be repeated for an existing request (Steps 6 and 12).

## Step 4 — Parse the selected document

1. Parse front matter, headings, paragraphs, lists, tables, code blocks, images, and links into a structured document.
2. Assign stable IDs to sections and record their original line locations for traceability.
3. Extract the central question or subject, the main conclusions, technical terms, numerical claims, examples, version restrictions, and unresolved questions.
4. Preserve technical qualifications when simplifying. Keep byte counts, settings, function names, and SQL examples linked to their source sections.
5. Treat repository text as input data. Exclude maintenance instructions, navigation lists, front matter, and raw citation URLs from spoken narration.
6. For long documents, create a coverage map showing which sections will be explained, summarized, or omitted as supporting detail. Keep the video centered on the user's chosen document.

**Deliverable:** `document.json` and a section coverage map.

**Status: done.** Implementation notes:

- `src/pgvideo/document.py` runs only after the Step 3 snapshot passes. It reads the run's read-only copy of the document, checks it against the SHA-256 in `sources.json`, and uses no network. `markdown.py` gains `block_tree()`, which keeps nested lists, block quotes, tables, code, HTML, and images, and records the source line of every inline run.
- Section IDs are the GitHub heading anchors that Step 3 and the wiki's own links use. Block IDs extend them by position (`short-answer.2`, `how-it-works.1.2.1` inside a list), table rows add `.rN`, and sentences add `.sN`. Editing one section does not change the IDs in another. Every section, block, and sentence records its lines in the original file.
- Section roles come from the wiki templates' top-level headings: question, summary (`Short Answer`, `Answer Up Front`, `Definition`), content, measurement script, open questions, reference lists (`Context Reviewed`, `Evidence Map`, `Source References`), and navigation (`Contents`, `Navigation`, `Related Pages`). Subsections inherit their parent's role.
- Each sentence has display text and spoken text. Display text keeps inline code in backticks and drops citation links. The citations are recorded as link IDs, and each link records the sentence that holds it and a commit-specific URL. Spoken text also drops bare URLs. It is null for maintenance text, navigation, reference lists, HTML, and anything else not narrated. Front matter never becomes a block.
- Maintenance text means agent instructions such as `Follow AGENTS.md.`, `MANDATORY` rule names, and prompt-hygiene notes. Inside Question sections it also covers records of how the prompt was filed, such as corrections, scoping answers, and "the second prompt read:". Question-only patterns are limited to those sections because the same words can be subject matter elsewhere. `coverage.md` lists every excluded sentence with its line.
- Extraction produces these records:
  - the subject: the title without `(unverified)`, and the question from the first Question section with narratable text or from a plain-text prompt block;
  - conclusions from the summary section, or else the lead of `## Answer`;
  - terms from inline code, identifier-shaped words, acronyms, and glossary entry links;
  - quantities with units;
  - mentions of PostgreSQL versions, flagging other versions and qualifiers such as "since" or "added";
  - code examples by kind and role;
  - open questions.
- A term counts as a setting when the cited `guc_tables.c` (`guc.c` in older versions), `guc_parameters.dat`, or `postgresql.conf.sample` at the pinned commit defines it. Without one of those files, a snake_case name described as a setting is marked `setting_source: context` as a hint only. Quantity extraction skips versions, dates, commit hashes, and labels such as "rule 2". Numeric inline code such as `` `1024` `` counts; digits inside other code do not.
- The coverage map estimates length at 150 spoken words per minute plus 25 words for each displayed table, code block, or image. It explains everything when the narratable text fits in 10 minutes. Otherwise:
  - the question and open questions are explained when short and summarized when long;
  - caveat sections (limitations, edge cases, restrictions) are always summarized at least;
  - sections that mention the question's or conclusions' terms are explained first;
  - tests, history, and measurement detail rank last;
  - summaries take 25% of a section, between 40 and 150 words;
  - the measurement script is omitted, and navigation and reference lists are excluded.

  Across the 82 content pages cached from commit `ba57f08`, the longest took 1.3 seconds to parse and every plan fits in 10 minutes. The Step 1 example plans 8.4 minutes and omits nothing.
- These are the rules of the `standard` level. Step 13 adds `summary` and `full` plans to the same coverage map, plans a table at the words of its rows instead of 25 words, and condenses a section that is only a table to the table's first rows.
- A document with no narratable prose returns `needs_review` (exit status 3). A missing question or conclusions is a warning. A common concept page defines a concept rather than answering a question, so it gets no warning.
- Terms, quantities, and version mentions are deterministic, surface-level extraction. Step 5 matches terms against the glossary, and Step 6 checks meaning. The coverage decisions and word counts plan Step 7's script; Step 9 times the video from measured audio.

## Step 5 — Index the glossary and select relevant entries

1. Parse glossary entries under `Terms`, preserving the canonical term, heading anchor, aliases, definition, checked versions, version notes, and evidence links.
2. Build an index once per glossary hash, then reuse it across requests for that snapshot.
3. Find candidate entries through explicit glossary links, exact terms, aliases, acronyms, and identifiers occurring in the selected document.
4. Use word boundaries and context to disambiguate short aliases. Rank matches by their relevance to the document's central subject and supporting explanations.
5. Apply the entry's stated version rules. A version listed as checked can still have a `Not present` note. A `Holds` note can contain exceptions. Resolve references such as “as in 18” before using a definition for another version.
6. If semantic matching is useful, use it to propose additional matches and require supporting passages for each match. Send only relevant entries to any language model used for this task.

**Deliverable:** `glossary-matches.json`, including ambiguous and unmatched concepts.

**Status: done.** Implementation notes:

- `src/pgvideo/glossary.py` runs after Step 4 passes. It checks `document.json` against the SHA-256 in the manifest and the glossary's snapshot copy against `sources.json`, and it uses no network.
- Changed on 2026-09-29, departing from item 2: every request builds its own index from the glossary it downloaded in Step 3 and saves it as `runs/<request-id>/glossary-index.json`. No index is shared between requests, so a new request never matches against an index built from an earlier download. The index depends only on the glossary's bytes; commit-specific wiki URLs are added when the document is matched. The manifest records the index path, SHA-256, entry count, build time, and builder digest (the code of `glossary.py`, `document.py`, and `markdown.py` and the English lexicon below). `cache/glossary/` is no longer written. Building takes about one second for the 319 entries at `ba57f08`; the index is 3.4 MB, beside a run's roughly 200 MB of media.
- Each entry keeps its anchor, term, aliases, `Checked on:` versions, definition paragraphs with display text and citations, version notes, Related entries, and line range. Citation URLs use the glossary's own Source Pins, not the document's pin. Aliases are interpreted:
  - `(contrast)` marks a contrasting concept, recorded as `relation: contrast`;
  - `(PostgreSQL 12 and 14)` limits an alias to those versions;
  - `CIC (CREATE INDEX CONCURRENTLY)` gives both forms;
  - `` `enable_*` penalty `` gives the phrase and the code pattern.

  Paired headings such as "Custom and generic plan" also match "Custom plan" and "generic plan".
- The main paragraph's version is the one checked version without a note; citations or an opening "In PostgreSQL NN" decide otherwise. All 319 entries resolve through their notes. For the document's version, an entry is `main`, `holds`, `holds_with_exceptions`, `differs`, `not_present`, `unchecked` (not a checked version), or `unknown` (checked but no note). A Holds note that names an exception ("except", "apart from", "but", "unlike", "instead", "no longer") has exceptions. References such as "as in 18", "the same way as 12", "match 17", and "as 12 does" are resolved recursively, so a 19 note that says "as in 18" carries the 18 note's exceptions. The matched entry includes its own note and every note it borrows from.
- Candidates come from explicit glossary links and from names, aliases, acronyms, and identifiers in headings, narrated sentences, displayed table rows, and code blocks. Literal forms are compiled into two prefix-trie expressions: case-sensitive for identifiers and acronyms, and case- and hyphen-insensitive with plurals for words and phrases. Wildcard and placeholder forms such as `` `PgStatShared_*` `` and `` `WITH (...)` `` get their own expressions. Identifier boundaries include `_` and `$`, so `pg_am` does not match `pg_amop`; where matches overlap, the longest wins. Code blocks match only identifiers and acronyms.
- A form needs context when it is an ordinary English word, a word or code value of three characters or fewer, a two-letter acronym, or a short placeholder pattern. "Ordinary English" means listed in Kokoro's English pronunciation lexicons (misaki's `us_gold.json` and `us_silver.json`, already hash-locked), so "path", "cost", and "row" need context while "autovacuum" and "tuple" do not. A code value such as `` `auto` `` must also be marked as code in the document.
- Context comes from the glossary's structure, not from surrounding English words, which proved too noisy on real pages:
  - a source file that both the paragraph and the entry cite;
  - a symbol from the entry's definition;
  - a Related or inline-linked entry already accepted in the same paragraph;
  - an explicit link to the entry anywhere in the document;
  - another distinctive form of the entry in the same section.

  Headings use the context of their whole section. A related entry counts only when it was accepted without help from another related entry, so two generic words cannot vouch for each other. A word left without support follows the entry that the same word was accepted for elsewhere in the document (one sense per discourse), except code values. When several entries share a form, the one with the most support wins; a tie is ambiguous (`collision`), and an unsupported form is ambiguous (`needs_context`).
- Matches are ranked `central` (title, question, or conclusions), `supporting` (explained or summarized sections), or `peripheral`, then by relevance: 3 per central occurrence up to three, 2 for an explicit link, plus 1, 0.5, 0.2, or 0.1 per occurrence by section decision. Each occurrence records its sentence ID, line, matched text, method, support, and context evidence.
- Document terms of concept kinds (settings, functions, constants, identifiers, acronyms, glossary links) that no entry covers are listed as unmatched with their counts and whether they are central; generic acronyms such as SQL are skipped. The subject's focus terms are mapped to entries or marked `not_in_glossary`.
- Warnings and notes in `glossary-matches.json`: `unverified` glossary, missing glossary anchors, relevant entries that are `not_present`, `differs`, `holds_with_exceptions`, `unchecked`, or `unknown` for the document's version, aliases limited to other versions, ambiguous central terms, central terms not in the glossary, and structural issues in matched entries.
- Across the 83 cached content pages at `ba57f08`, matching takes at most 0.6 seconds per page. The Step 1 example matches 23 entries, 5 of them central, and leaves 10 generic words such as "path", "truncation", and `auto` ambiguous.
- Semantic matching is not implemented: no language model is configured, and `glossary-matches.json` records `semantic_matching.used: false`.

## Step 6 — Cross-check the subject and claims

1. Map the document's central subject and each planned technical explanation to relevant glossary entries. Check meanings and relationships as well as terminology.
2. Compare the document's explanation with the applicable version of each matched definition. Check acronym expansions, component roles, feature availability, limits, and explicit exceptions.
3. Record each result as `consistent`, `conflict`, `version_mismatch`, `ambiguous`, or `not_in_glossary`. Missing glossary coverage is a coverage gap; it does not by itself prove a claim is wrong.
4. For each result, retain the document passage, glossary anchor and excerpt, PostgreSQL version, evidence references, and proposed resolution.
5. Treat glossary agreement as a consistency result. Check narrated behavioral claims against the document's cited evidence, with particular attention to definitions introduced from the unverified glossary and any disagreement.
6. Resolve discrepancies with evidence from the matching PostgreSQL source pin. Record corrections in the generated script and report; preserve the input snapshot.
7. Return `needs_review` for unresolved conflicts, ambiguous central concepts, or unsupported central claims. Include the exact issue and evidence needed to continue. Resume the same request after a documented resolution.
8. Allow a concept absent from the glossary when the document's matching-version evidence supports it; record that exception explicitly.

Use deterministic checks for metadata, references, and version compatibility. Meaning comparisons may use a configurable language model or a reviewed script workflow, but a model's confidence score must not count as evidence.

**Deliverable:** `glossary-check.md` and structured results, with no unresolved issues that would make the narrated explanation misleading.

**Status: done.** Implementation notes:

- `src/pgvideo/crosscheck.py` runs after Step 5 passes, without network access or a language model. It checks `document.json` and `glossary-matches.json` against the SHA-256 values in the manifest. It reads the document's cited PostgreSQL files, and `configure.ac`, from the run's verified snapshot copies. `semantic_comparison.used` is `false`, and no confidence score is used. Meaning is compared only through the deterministic checks below, and a reviewer resolves anything they cannot settle.
- Every matched entry, ambiguous term, and uncovered concept gets a result. The result records the document passage, the glossary anchor, excerpt, and version status, the evidence, and a resolution. The checks are:
  - **Version scope.** An entry whose definition applies (`main`, `holds`, `holds_with_exceptions`, or `differs`) is `consistent`. Its `basis` lists the terminology match, the version scope, shared evidence files and symbols, and related entries in the same sentence.
    - A `Not present` entry that the document narrates is a `version_mismatch`. It is resolved when the document's cited PostgreSQL files contain the name as code, or when every mention names another version, uses a historical word such as "removed", or negates it. A narration such as "PostgreSQL 12 has no read-stream layer" agrees with the note and is `consistent`.
    - An alias that the glossary limits to other versions is a `version_mismatch` unless the mention is qualified in the same way.
  - **Parameter facts.** The context, default, minimum, and maximum that the document states for a parameter are compared with the glossary's statements for its version, where a version note overrides the main paragraph. They are also compared with the cited `guc_tables.c`, `guc.c`, `guc_parameters.dat`, or `postgresql.conf.sample` at the pin.
    - Values are compared across units, such as `128MB` and 16384 blocks, assuming an 8 kB `BLCKSZ`. Enum spellings come from the options table.
    - The pinned source settles a disagreement. When it contradicts the document, the correction is recorded for the script and the snapshot is left unchanged. When the document and the glossary disagree and no GUC source is cited, the conflict is unresolved.
    - A fact is attributed only when its parameter is clear: the nearest identifier in the same clause, the subject that opens the previous sentence, or, for "It" and "The setting", the subject's own parameter. Lists such as "`a` and `b` keep defaults of `64MB` and `-1`" are skipped. Range and minimum/maximum statements need an explicit word such as "accepts" or "maximum", so measurements such as "cancelled between 2018 and 2024 ms" are not facts.
  - **Acronyms and roles.** An acronym expansion written as "long form (ACR)" or "ACR (long form)" must match one of the entry's multiword names. A small word variation is allowed, such as "REINDEX INDEX CONCURRENTLY" for RIC, and so is a head noun after the parenthesis, as in "just-in-time (JIT) compilation". A sentence of the form "`X` is a view" must give the role that the entry's lead sentence gives.
  - **Ambiguity and coverage.** An ambiguous group is an `ambiguous` result, and the script must not use its glossary definitions. It blocks only when it is central and two entries claim the same distinctive form, or when a subject focus term is ambiguous. An ordinary word such as "row" in a conclusion is a warning. An unmatched concept, or an entry `unchecked` or `unknown` for the document's version, is `not_in_glossary`. When its narrated mentions appear in the document's pinned evidence, it is allowed and listed in `exceptions`.
- Each narrated sentence and displayed table row in an explained or summarized content section is a claim. Sentences that end in a colon introduce the next block, so they are skipped. The claim's identifiers, numeric inline code, and quoted strings are searched in the cited lines, then the rest of the cited files, then the document's other evidence files. Each search tries an exact match first and then a case-insensitive one bounded by non-alphanumerics, so `track_activity_query_size` is found inside `pgstat_track_activity_query_size`.
  - Citations come from the sentence, else its paragraph, else its section. A claim is `verified`, `supported`, `cited` (nothing to look up), `unconfirmed`, or `uncited`.
  - A name that is missing is not a failure in three cases, and each is reported: the asker used it in the Question, such as a column of the asker's own SQL; the document's own code blocks define it, such as a helper function in a measurement script; or the sentence says it does not exist.
  - Wildcards and fragments such as `pg_analyze_and_rewrite_*()` and `shared_blk_`, elided messages, commit hashes, Git refs, and platform names are handled.
- `needs_review` (exit status 3) comes from four kinds of issue:
  - unresolved conflicts and version mismatches in narrated text;
  - ambiguous central concepts;
  - central claims whose names are missing from the pinned evidence;
  - central concepts that neither the glossary nor the evidence supports.

  A central sentence with nothing to look up and no PostgreSQL citation in its section is a warning, not a block. Such sentences include verdicts that summarize the page's own measurements and descriptions of the wiki's test protocols. They cannot be checked against the source mechanically, and blocking every such sentence made most measurement pages unusable.
- `glossary-check.md` lists each blocking issue with the passages, the glossary excerpt, the proposed resolution, the evidence needed, and a YAML snippet. The reviewer records decisions in the run's `resolutions.yaml` and runs `scripts/pgvideo resume --request <id>`, which repeats Step 6 offline for the same request. The allowed decisions are `use_document`, `use_glossary`, `omit`, and `choose_entry`, depending on the result.
  - `use_document` and `use_glossary` need `raw/postgres-NN/path#Lx-Ly` evidence, or a blob URL, at the document's version and pin. Evidence in the snapshot is checked, including its line range, and its excerpt is saved. Other evidence is recorded as not checked.
  - Unknown IDs, disallowed decisions, missing reasons, YAML aliases, and a symlinked resolutions file fail with status 1. The manifest records the resolutions file's SHA-256.
  - Resuming an earlier stage is not implemented, because Step 3 and Step 4 blockers need a wiki change and a new request.
- The record also carries `corrections`, `omissions`, `exceptions`, per-entry `definition` guidance (`introduce`, `note_only`, `name_only`, or `none`, with caveats from exception notes), and per-section summaries for Step 7.
- Calibration: all 83 content pages at `ba57f08` were run through Steps 3–6 with their pinned PostgreSQL 12, 14, 17, 18, and 19 files. Each page took at most 2.2 seconds. Three pages return `needs_review`, and each for a real reason:
  - the v17 codebase guide narrates "AIO", which the glossary says does not exist in 17;
  - a v12 Short Answer uses the placeholder `referenced_table_tuples`, which is not in its cited source;
  - a v18 Short Answer claims facts about `track_activity_query_size` that it supports only by linking to another wiki page.

  The Step 1 example passes with 29 consistent results, 5 parameter facts confirmed by the pinned `guc_tables.c`, and all 44 checkable claims found in the pinned evidence.
- Step 4's version extraction does not read the number in "v13"-style mentions, because its number pattern rejects a preceding letter. Step 6 reads the numbers itself; `coverage.md` still omits such mentions.

## Step 7 — Create the narration and storyboard

1. Build an outline covering the question, required terminology, the mechanism or explanation, an example where supported, caveats, and a brief recap.
2. Create scenes with these fields: scene ID, title, screen text, visual description, narration, source section IDs, glossary references, and citations.
3. Use short spoken sentences. Introduce unfamiliar terms when needed and preserve the selected PostgreSQL version throughout.
4. Explain code and tables in plain language while displaying the relevant excerpt. Include only examples supported by the document or clearly marked as illustrations of its explanation.
5. Keep screen text concise and split dense material across scenes. Use diagrams for relationships and sequences where they explain more clearly than prose.
6. Support a provider-neutral drafting adapter that accepts the structured document and selected glossary entries and returns the scene schema. Also accept a manually edited script, so no particular text model or cloud service is required.
7. Validate the final script and visual labels against the source coverage map and glossary report. Rerun claim checks after substantive edits.
8. Save canonical display text separately from pronunciation-adjusted TTS text.

**Deliverable:** `script.md` and `storyboard.json`, with every technical scene traceable to the selected document and supporting checks.

**Status: done.** Implementation notes:

- `src/pgvideo/script.py` runs after Step 6 passes, without network access or a language model. It checks `document.json`, `glossary-matches.json`, and `glossary-check.json` against the SHA-256 values in the manifest. It writes `draft-input.json`, `storyboard.json`, and `script.md`, and records a `script` stage in the manifest with the drafter, its input's SHA-256, the pronunciation dictionary's SHA-256, and the storyboard's hash. A passing script sets the manifest status to `script_ready`.
- Three drafters share one scene schema and one validation (item 6):
  - the built-in drafter, `builtin-extractive`, is deterministic and runs by default;
  - `script --drafter-command <file>` runs an executable inside the project inside the offline sandbox. The executable reads `draft-input.json` on standard input and writes JSON or YAML scenes on standard output, with a 900-second limit;
  - `script --storyboard <file>` imports a scene file inside the project, such as an edited copy of `storyboard.json`. Derived fields are recomputed, and `tts_source: manual` keeps a hand-written TTS text.

  The sandbox denies network access to `script`. A drafter that needs a network service runs outside the project on `draft-input.json`, and its output is imported with `--storyboard`. `resume` reuses the drafter that the request last used.
- `draft-input.json` holds the narrated sections with their sentences, code, tables, and images, citations, corrections, omissions, ambiguous terms, length limits, and the scene schema. It includes only the glossary entries the document matched, each marked with whether Step 6 allows its definition, as Step 5's item 6 requires.
- Every scene records the fields in item 2: `id`, `part`, `title`, `screen`, `visual`, `narration`, `sources`, `glossary`, and `citations`.
  - A `part` is one of `opening`, `question`, `terminology`, `answer`, `mechanism`, `example`, `caveat`, `supporting`, `open_questions`, `recap`, or `credits`. It places the scene in the outline of item 1.
  - The screen has a `layout`: `title`, `question`, `bullets`, `steps`, `code`, `table`, `diagram`, `terms`, `image`, or `credits`.
  - Each narrated sentence has display `text`, `tts` text, an `origin`, its sources, glossary entries, and citations, and the result of its check. The origin is `document`, `table`, `correction`, `glossary`, or `framing`.
- The built-in drafter's outline starts with the title, the question, and the central glossary terms. The page's summary and content sections follow in the page's order, because the selected document supplies the outline. The open questions, a recap from the page's conclusions, and the sources close the video.
  - A caveat heading makes its scenes `caveat`, and tests and history make them `supporting`. Code scenes are `example`.
  - Framing sentences introduce, connect, and close, and may name only what the title and the question name. A title such as "Changes Since PostgreSQL 12" may repeat the versions it compares.
- Sentences come from the page, with their words unchanged (item 3):
  - A long sentence is split at semicolons, and at colons followed by a new clause, when both sides have at least five words. Step 8 splits further for subtitles.
  - A summarized section keeps its lead sentence and then its most relevant sentences within the coverage map's word budget. Relevance counts focus terms, first sentences, and conclusions, and labels of one or two words are skipped.
  - Step 6 corrections replace the stated value in place. Step 6 now records the value as stated in each correction. Otherwise the drafter writes a replacement sentence. Sentences omitted by a resolution, and every sentence that names an omitted concept, are left out. A table row with a correction is read as its corrected sentence and not shown.
- The terms scene introduces up to four central entries, other than the subject's focus terms. Each entry must be consistent, Step 6 must allow its definition (`introduce` or `note_only`), and the definition's names must be confirmed in the pinned evidence or absent. The definition must be at most 45 words. The screen marks the definitions as coming from the unverified glossary.
- Screens stay short (item 5):
  - A bullet is a sentence's first whole clause, up to 16 words and 110 characters. It is never cut before a qualifier such as "unless", "but", or "not", inside parentheses, or partway through a list.
  - When no clause stands alone, the bullet lists two or three code names from the sentence. Without a safe line, it shows a whole sentence of up to 26 words, so a negation is never hidden.
  - A scene holds at most four sentences and about 90 words. A list, a code block, and a table start their own scenes.
- Code, tables, and images stay on screen while the sentence that introduces them and the following paragraph are narrated (item 4). A paragraph that ends with a colon belongs to the next display.
  - Code over 16 lines is split at blank lines.
  - Tables show six rows per scene, and each row is read aloud as "`example_size`: default `1024`."
- Diagrams draw only relationships that a sentence states between two named components, such as "`A` is a SQL view over `B`", "`A` then uses `B`", and "by calling `B`". A scene needs two such edges and three nodes. Each edge keeps the ID of the sentence that states it. Ordered lists become numbered steps.
- Validation applies to every drafter (item 7). Structural errors in a scene file fail with exit status 1: unknown keys, bad types, duplicate IDs, empty narration, YAML aliases, and files outside the project. The following issues block and return `needs_review`:
  - unknown, excluded, or omitted sources;
  - an uncovered question, summary, caveat, or open-questions section, unless `coverage_overrides` records a reason (other uncovered sections are warnings);
  - screen text, diagram labels, glossary cards, code, or tables that do not come from the scene's sources;
  - a glossary definition that Step 6 does not allow, or a changed one;
  - a correction that is not applied;
  - technical content in framing sentences;
  - an opening scene without the PostgreSQL version;
  - TTS text with symbols Kokoro would read aloud.
- Claim checks are rerun after edits:
  - A sentence whose letters and digits appear in order in its sources is `unchanged` and keeps its Step 6 claim status. It blocks if the words it leaves out include a limiting word such as "not", "only", "unless", or "when".
  - Any other sentence is `rechecked` through `ClaimRecheck`, which `crosscheck.py` now exposes, using Step 6's claim and parameter checks. Its names, numeric code, quoted strings, numbers, and version mentions must appear in its sources or the pinned evidence. Its parameter facts must match the pinned GUC table, and adding or dropping a negation blocks.
  - Like Step 6, these checks compare names, values, and negation, not full meaning.
- Display and TTS text are kept apart (item 8). `src/pgvideo/speech.py` derives TTS text from `pronunciation/en.yaml`, which holds terms, identifier parts, abbreviations, and units.
  - Identifiers are split at underscores and case changes. A piece without a vowel, or a capital piece of up to three letters that is not a word in Kokoro's English lexicon, is spelled out.
  - Operators become words, and a call reads as "f of x".
  - A placeholder such as `pg_<subscription-oid>` names what it stands for.
  - Step 8 extends the dictionary after listening to Kokoro's output.
- The length estimate counts TTS words at 150 per minute, with a spelled letter as half a word, plus pauses. Spoken identifiers make scripts about half again as long as Step 4 planned. A script over 10 minutes is a warning for a page that fits the target, and a note for a long page that the coverage map already condensed. Step 9 measures the real length.
- Calibration: only the PostgreSQL 18 pin is in the local cache. Of the 14 cached v18 content pages at `ba57f08`, 13 reach Step 7; the other stops at Step 6, as noted there. All 13 built-in drafts pass, in at most 0.2 seconds each.
  - Three scenes have no screen text because none of their sentences yields a safe line.
  - Twelve pages are estimated at 12 to 16 minutes. That gives five warnings for pages that fit the target and seven notes for long pages. The other page is estimated at 6.1 minutes.
  - The Step 1 example gives 28 scenes and 77 sentences: 67 unchanged, 4 glossary definitions, and 6 framing. It has one diagram, and its estimate is 12.9 minutes against 8.4 planned.

## Step 8 — Generate Kokoro narration

1. Start with `KPipeline(lang_code='a')`, voice `af_heart`, and speed `1.0`; expose language, compatible voice, and speed as request settings. These defaults follow the official English example. [Kokoro usage](https://github.com/hexgrad/kokoro#usage).
2. Maintain a pronunciation dictionary for PostgreSQL, acronyms, settings, and identifiers. Use spoken expansions or tested phoneme overrides while retaining canonical spelling on screen.
3. Split narration at natural sentence or clause boundaries into short units suitable for subtitles. Generate every unit with the same voice settings.
4. Consume every audio chunk returned by Kokoro and preserve its order. Save lossless WAV intermediates at Kokoro's documented 24,000 Hz sample rate. [Official model usage](https://huggingface.co/hexgrad/Kokoro-82M#usage).
5. Add deliberate pauses at sentence and scene boundaries. Check for empty output, missing units, clipped words, and pronunciation problems; regenerate only affected units.
6. Assemble a narration master and normalize it consistently. Start with a configurable target of -16 LUFS integrated loudness and a maximum true peak of -1.5 dBTP, using FFmpeg's two-pass `loudnorm` workflow and an explicit final sample rate. [FFmpeg loudnorm documentation](https://ffmpeg.org/ffmpeg-filters.html#loudnorm).
7. Cache narration using the exact TTS text, pronunciation dictionary hash, voice, speed, language, model assets, and relevant dependency versions.

**Deliverable:** narration WAV files, a normalized master, and a complete mapping from spoken units to audio samples.

**Status: done.** Implementation notes:

- `src/pgvideo/narration.py` consumes each Kokoro chunk in order and caches lossless 24 kHz mono unit WAVs under `cache/narration/`. Each key includes the exact TTS text, dictionary hash, model/config/voice hashes, voice, speed, language, and Kokoro, Misaki, and PyTorch versions.
- Dictionary-generated sentences split at clauses and at 28-word limits. Manually edited TTS stays in one unit so its wording is preserved. Pauses are 0.35 seconds after a sentence and 0.8 seconds after a scene, except the final scene.
- `narration/audio-map.json` records scene, sentence, and unit IDs with contiguous sample positions and WAV hashes. `narration/master-raw.wav` and `narration/master.wav` retain the same 24 kHz sample count. FFmpeg runs two-pass `loudnorm` with defaults of -16 LUFS and -1.5 dBTP.
- `scripts/pgvideo narrate --request <id>` reruns this stage. `--refresh-unit <id>` regenerates a named unit or sentence when listening finds a problem; edited pronunciations first require rerunning `script` to revalidate the storyboard.

## Step 9 — Build timing and subtitles from the audio

1. Measure actual sample counts after audio processing. Use these durations to place every scene and caption; word counts are only useful for estimating length before synthesis.
2. Include inserted pauses in the timeline. Accumulate timing from one continuous audio clock so rounding does not drift across scenes.
3. Convert cumulative scene boundaries to video frame positions and cover the entire narration. Pad the final visual or audio tail as needed for frame alignment.
4. Create SRT and WebVTT subtitles from the short spoken units and their measured boundaries. Keep cues readable and avoid overlapping timestamps.
5. Keep subtitle spelling faithful to the canonical script. Phrase boundaries are sufficient initially; add forced alignment only if future requirements call for word-level highlighting.

**Deliverable:** `timeline.json`, `captions.srt`, and `captions.vtt` synchronized with the narration.

**Status: done.** Implementation notes:

- `src/pgvideo/timing.py` checks the storyboard and audio map hashes, every unit WAV hash and sample count, the normalized master's hash and sample count, and exact coverage of all scenes and script sentences before writing the timeline.
- Scene frame boundaries are the ceiling of each cumulative audio sample position at 30 fps. Adjacent scenes share a boundary, and the final frame extends the visual tail by less than one frame.
- SRT and WebVTT cues use each unit's measured start and end sample positions. Pauses stay on the scene clock but outside caption cues. Cues retain script spelling, with code backticks removed for display and long lines wrapped.
- `scripts/pgvideo timing --request <id>` rebuilds this stage from validated narration. Rerunning the script or narration invalidates the previous timing manifest entry.

## Step 10 — Render visuals and encode the MP4

1. Create reusable HTML/CSS templates for titles, explanations, code excerpts, tables, diagrams, and source credits.
2. Render each scene with Playwright to a 1920 × 1080 PNG after fonts and images have loaded. Check for text overflow, cropped code, unreadable tables, and missing assets.
3. Include the PostgreSQL version on the opening slide and concise source references where useful. Provide full commit-specific links in the accompanying references file.
4. Use the audio-derived timeline to hold each scene for the required number of frames. Start with simple cuts; keep each diagram or code excerpt visible throughout its explanation.
5. Assemble the visual stream and mux the continuous narration master into an MP4 with `libx264`, `yuv420p`, constant 30 fps, AAC at 48 kHz, and `+faststart`. Start with CRF 20 and 128 kb/s mono narration as configurable settings. [FFmpeg MP4 and faststart documentation](https://ffmpeg.org/ffmpeg-formats.html#mov_002c-mp4_002c-ismv).
6. Keep subtitles as accompanying files initially. Add an optional MP4 subtitle track or burned captions when requested.
7. Encode to a temporary output inside the project and finalize its filename only after validation succeeds.

**Deliverable:** a complete MP4 containing the selected document's visuals and Kokoro narration.

**Status: done.** Implementation notes:

- `src/pgvideo/render.py` and `templates/slide.html` render the storyboard's title, question, bullet, step, code, table, diagram, term, image, and credit layouts. Chromium loads bundled fonts and local images before capture; the renderer rejects missing images, non-bundled fonts, and overflowing content.
- Scene PNGs use the request's even dimensions. An FFmpeg concat file assigns each PNG the exact frame count from `timeline.json`. Encoding uses local FFmpeg, H.264/yuv420p at 30 fps, AAC mono at 48 kHz, `+faststart`, CRF 20, and 128 kb/s by default. ffprobe checks the streams and exact video frame count.
- `references.md` is stored in the run, with the document's resolved wiki URL and deduplicated scene citations. `render/draft.mp4` remains a draft until Step 11 performs full media validation and finalizes delivery. `render.json` and the manifest record input, template, slide, reference, and draft hashes.
- `scripts/pgvideo render --request <id>` repeats Step 10 with optional `--crf` and `--audio-bitrate`. A short two-scene integration test and a 28-scene smoke render of the existing storyboard passed locally.

## Step 11 — Validate and return the requested video

1. Use ffprobe to verify the container, codecs, dimensions, frame rate, audio stream, and total duration.
2. Decode the complete MP4 with FFmpeg to catch broken media. Confirm that the last spoken sentence and final scene are present and that audio/video end times differ by no more than 100 ms.
3. Check caption ordering, scene coverage, missing audio units, unintended long silence, and audio loudness. Save results in `quality-report.json`.
4. During the first complete implementation trial, watch the video and listen to technical terms, scene transitions, and the ending. Refine templates and pronunciation rules from those concrete findings.
5. Return the MP4 path, duration, document URL at the resolved commit, PostgreSQL version, and paths to accompanying files.
6. Record the final state as `completed`, `needs_review`, or `failed`. Preserve useful intermediate files so a failed stage can be retried within the same request.

**Deliverable:** one validated video package for the explicitly requested document.

**Status: done for automated validation and delivery.** Implementation notes:

- `src/pgvideo/validate.py` checks hashes, MP4 streams, duration and end alignment, full decode, captions against audio units and scenes, decoded unit energy, long silence, and integrated loudness and true peak. It writes `quality-report.json` and records `completed`, `needs_review`, or `failed` in the manifest.
- After validation, the requested output directory contains the MP4, transcript, SRT and WebVTT captions, references, glossary report, quality report, and manifest. `scripts/pgvideo validate --request <id>` repeats validation and delivery without rendering.
- The first complete trial used the existing explicit request for `wiki/v18/questions/observability/track-activity-query-size.md`: 28 scenes, 84 audio units, 840.4 seconds. The trial exposed a punctuation split in narration units and visible Markdown backticks in slides; both were corrected. Opening, technical, and closing slide images were inspected. This interface does not support listening to the audio, so pronunciation still needs a human listening pass.

## Step 12 — Add reuse and focused implementation checks

1. Key reusable artifacts by the document and glossary hashes, source pins, script, pronunciation rules, model and voice assets, rendering configuration, templates, and tool versions.
2. Reuse a completed video only when those inputs match. A new glossary snapshot must invalidate its previous cross-check even when the document itself is unchanged.
3. Test request validation, alias collisions, missing glossary terms, contradictory definitions, version exceptions, and incomplete evidence with small fixtures.
4. Add an integration check covering multiple Kokoro chunks, pauses, subtitle offsets, and the last scene to catch dropped audio and timing drift.
5. Run one full trial with a real document explicitly supplied to the command. The command in Step 1 provides an example; it is not a default source selection.
6. Keep generation tied to explicit requests. Cache maintenance and retries must not create requests for other documents.
7. Run all checks through the local environment with temporary fixtures inside `.runtime/tmp/`. Verify setup and execution when no optional tools or packages are available on the host search path. Cover missing local tools, external output paths, symlink escapes, and inherited settings that point outside the project; each must fail or be replaced with validated local settings before use.
8. Audit filesystem access during setup and a sample synthesis/render on the supported host. Confirm that reads outside the project are limited to the documented OS/bootstrap exceptions and that all application writes remain inside it. Check that rendering and synthesis work without network access after setup. Treat any unverified access as an explicit limitation in the isolation report.

**Deliverable:** repeatable, resumable generation with checks for the failures most likely to affect correctness and playback.

**Status: done.** Implementation notes:

- `src/pgvideo/reuse.py` keys a video by the SHA-256 of its components (items 1 and 2):
  - every snapshot input (the document, the glossary, wiki images, `configure.ac`, and each cited PostgreSQL file) by SHA-256, with the wiki commit and the PostgreSQL pin;
  - the storyboard without `request_id`, `created_at`, `drafter`, and `inputs`. Two requests for the same page at the same commit produce the same hash. The storyboard's document record keeps the URL and wiki commit that the slide footers and references show, so a video is reused only for the same wiki commit. A new wiki commit with identical bytes builds again, with every unit still from the unit cache;
  - the pronunciation dictionary; the voice, language, speed, loudness target, and true-peak limit; the Kokoro model, configuration, and voice hashes; the width, height, frame rate, CRF, and audio bitrate;
  - the tools: `tools.lock` and `requirements.lock`, which doctor verifies against the installed Kokoro assets, eSpeak NG, FFmpeg, Chromium, fonts, and packages before every command; `templates/slide.html` and the fonts; and the code of `assets.py`, `speech.py`, `narration.py`, `timing.py`, `render.py`, and `validate.py`.

  The document and glossary hashes are explicit components, so a new glossary snapshot always changes the key. Cross-checks are never shared between requests: every request checks its own snapshot. `script` now also refuses a `glossary-check.json` whose recorded inputs are not the current `document.json` and `glossary-matches.json`.
- Step 11 registers each delivered video as `cache/videos/<key>/<request-id>.json`. The entry lists the key's components and the SHA-256 of the audio map, the render record, and every unit WAV, master, slide page and PNG, the concat file, the MP4, and the references. The narration, timing, and render stages now record the tools digest they ran with. A video is registered only when all three match the validation's own, so a video built partly before a code or lock change is never offered for reuse. Registration never fails validation; the manifest's `reuse` record states whether the video was registered, or why not.
- After the script passes, `generate`, `resume`, and `script` compute the key with the settings the build would use and look it up. They prefer the request's own earlier video, then the newest. A candidate is used only when its entry is well formed, its components produce its key, and every listed file in its run directory is a regular file inside the project with the recorded SHA-256. A stale entry is reported, skipped, and removed; that is the only cache maintenance, and it never creates a request. On a match, the narration files are copied and verified, and the audio map is rewritten for the new request, with its storyboard hash, settings, and `reused_from`. The request's own timing stage then runs, followed by the copied slides and MP4 with a rewritten render record, and its own full validation. If a copied stage cannot be used, it is built instead. `--no-reuse` skips the lookup; `narrate`, `timing`, `render`, and `validate` never look up, and the unit cache still spares synthesis.
- Every stage writer now drops the records of all later stages through `src/pgvideo/stages.py`. Earlier, a repeated narration, timing, or render stage left the previous `validation` record in place, so a manifest could claim that media built from other inputs was validated. Repeating any stage up to the script also drops the reuse lookup.
- Item 3: `tests/fixtures/` holds a small wiki, with a glossary and one page per case under `wiki/v18/checks/`, and the pinned PostgreSQL files it cites. `tests/test_checks.py` runs each page through `generate`:
  - ten invalid requests fail with status 1 before a request directory exists;
  - a consistent page reaches narration from a path and from a blob URL;
  - an alias that two entries claim, a central term with no support, a default that contradicts the glossary without a GUC source, an entry that the glossary marks as not present in 18, and missing or out-of-range evidence each stop with status 3 at the expected stage, with exactly the expected blocking IDs;
  - the same wrong default is corrected in the script when the page cites the pinned GUC table.
- Item 4: `tests/test_integration.py` narrates a three-scene storyboard with the real Kokoro model. One hand-written unit exceeds Kokoro's 510-phoneme limit and arrives in several chunks. The test compares each unit WAV with the recorded chunks and checks every pause and sample position, normalization alignment by cross-correlation, cue milliseconds, scene frames, the final tail, and the MP4's decoded audio against the master at the first unit, the second chunk, and the last unit, within 2 ms. It also checks the slide cuts at the scene frames. Injected faults each fail it: a dropped chunk, a 5 ms shift in the second normalization pass, and a 50 ms audio offset in the MP4, which Step 11's 100 ms end-time tolerance lets through. It takes about 13 seconds.
- `tests/test_reuse.py` runs `generate` end to end with real FFmpeg, Chromium, timing, and validation and a deterministic stand-in for Kokoro. It covers the key's components, an identical request that reuses the validated video byte for byte, new builds for another speed, a new glossary snapshot, and `--no-reuse`, a glossary snapshot that contradicts the unchanged page, changed and missing files, tampered index entries and an escaping `cache/videos`, retries (`script`, `resume`, `narrate`, `timing`, `render`, `validate`) that create no requests, and videos from other tools, which are not registered. The full suite has 119 tests and runs in about 50 seconds.
- Item 5: the Step 1 example was requested explicitly twice at wiki commit `ba57f08`. The first request built and delivered the 840.4-second, 28-scene video in 113 seconds, with all 84 units from the unit cache. The second found the first request's video (key `1e5d56fc0f33`), copied it, and ran its own timing and full validation in 33 seconds. It delivered a byte-identical MP4 and captions, at −16.15 LUFS with a 0.0-second end difference. Only these two requests were created.
- Item 6: only `generate` creates a request, and only for its `--document`. A reuse lookup reads the index and the run it names, copies files into the current request, and removes stale index entries; it never creates, changes, or delivers another request. The retry commands act only on the request given by `--request`, and Step 3 and Step 8 retries repeat a download or synthesis for the same request. The tests count the run directories after lookups and retries.
- Item 7: the environment tests add inherited `TMPDIR`, cache, model, browser, and eSpeak NG settings that point outside the project. They also run the launcher with no host tools on `PATH` and with no `PATH`, and check that tests' temporary files stay in `.runtime/tmp/`. A request whose project lacks its own ffprobe fails with that path while a decoy `ffprobe` on `PATH` never runs, and delivery rejects output directories outside the project, directly or through a symlink. `scripts/setup --offline` also passed with an empty `PATH` and an otherwise empty environment, started from outside the project.
- Item 8: `scripts/pgvideo audit` applies a profile in which reading file contents, writing, or executing outside the project and the documented OS paths, and any IP connection, send SIGKILL. Seatbelt applies the last matching rule, so documented attempts listed after each kill rule are denied without termination. Under it, the audit runs `setup --offline`, doctor, and `doctor --sample`, and records `isolation.audit` in the environment report and every later manifest. Bisecting with such profiles on macOS 27.0 found a minimal set of attempts:
  - Chromium, through macOS frameworks, lists `/private/etc` and reads `/private/etc/hosts`, `/Library/Preferences/com.apple.networkd.plist`, `/private/var/db/mds`, and three `~/Library` folders;
  - PyTorch's OpenMP runtime lists `/private/tmp` and tries to create its `__KMP_REGISTERED_LIB_<pid>` file;
  - starting any allowed shell lists `/bin` and reads the shell binaries. The first audit found this through `scripts/espeak-ng-runtime`.

  No process ran an outside executable or opened an IP connection. The audit passed on 2026-09-29 in about 10 seconds. It does not cover metadata lookups, Mach IPC, the pre-sandbox bootstrap, or the network retrieval of `setup` and `generate`; the isolation report lists these limitations.

## Step 13 — Choose the level of detail

1. Add `--detail` to `generate` with three levels: `summary`, `standard` (the default), and `full`. Record the level in `request.json`.
2. `standard` keeps the coverage map of Step 4. `summary` narrates the key subjects: the question, the page's own summary or conclusions, its caveats and open questions in brief, and one sentence for each main section that fits a short target. `full` narrates every section without a length target.
3. Decide the level in the coverage map, so that the glossary matches (Step 5), the cross-check (Step 6), and the script (Step 7) follow it without rules of their own.
4. Keep a summary traceable: record the exact sentences it keeps, and give them to every drafter.
5. Keep levels apart: put the level in the reuse key and in the delivered file name.
6. Plan each table at the words the drafter reads from its rows, and condense a long table as long prose is condensed.

**Deliverable:** one request option that makes a short summary, the standard video, or a complete video of the requested page.

**Status: done.** Implementation notes:

- `generate --detail` records `settings.detail` in `request.json`; a request from before this step is `standard`. `document.py` reads the level, and an unknown one fails the request with status 1. The level belongs to the request: `resume`, `script`, and the other retry commands keep it, and another level of the same page needs a new request.
- `standard` keeps its rules. Two fixes found while calibrating the levels change its videos; see the last notes.
- `full` explains every section with narration, including long questions, follow-up prompts, tests, and history. Measurement scripts, navigation, and citation lists stay out, as at every level. `target_minutes` is null, and a plan over 10 minutes gets a `full_detail` note. Across the 82 pages, full detail plans 3.7 to 538 minutes (median 32), and the built-in drafter makes up to 1,177 scenes, so `MAX_SCENES` rises from 300 to 2,000 and `MAX_SCENE_FILE_BYTES` from 4 MB to 16 MB, enough to import an edited storyboard of the longest page.
- `summary` plans 1–3 minutes, a budget of 450 words at 150 words per minute:
  - It always keeps the central question, or its first sentence when the question is longer than 150 words. It keeps the page's own summary: a summary section, or a Short Answer, Answer Up Front, or Definition at most one level under `## Answer`. A summary that shows tables or code keeps only its prose, because the drafter reads every table row aloud; a summary that is only a table is left out when the page has conclusions elsewhere. Without a summary section, the summary keeps the conclusions, the first paragraph of the answer.
  - It also always keeps the first sentence of each caveat section, including subsections of one, and the first open question, whole when it has at most 80 words. A caveat with no such sentence, such as a table of exceptions, is left out.
  - It then adds the first sentence of the other sections while the budget allows: main sections before their subsections, then sections that use the subject's terms, in page order, and then the other open questions. Follow-up prompts and supporting detail (tests, history, and measurement, including subsections of such sections) are left out.
  - A section's first sentence is its first narrated sentence that has at least three words and does not end with a colon, the rule the drafter already used for summaries.
- A coverage entry records `keep` when the plan chooses the exact sentences or table rows to narrate: a summary's kept sentences, and at the standard level a condensed table's first rows. `coverage.md` lists them under "Kept Sentences And Table Rows". A `summary` note replaces the `long_document` note.
- Steps 5 and 6 need no change: matches in left-out sections rank as peripheral, and Step 6 checks every sentence of an explained or summarized section, including sentences that a summary does not narrate.
- Step 7 narrates exactly the kept sentences and table rows of a section. When a Step 6 resolution omitted them, it falls back to its word-budget choice. A condensed table shows and reads only its kept rows, then says "The table on the page has more rows." Open questions also follow `keep`. A summary has no recap. Its opening slide shows "Summary" and its narration says that the video summarizes the page; a full-detail opening shows "Full detail". `draft-input.json` carries the level, each section's `keep`, and a purpose that asks for a summary. The storyboard's settings, the manifest's script record, and `script.md` record the level. A summary over its 3-minute target gets a `long_script` note; full detail gets no length issue.
- Step 11 delivers `<page>-summary.mp4` and `<page>-full.mp4`; `standard` keeps `<page>.mp4`. The level is in the storyboard, so it is part of the reuse key. Because `validate.py` changed, the tools digest changed, and videos registered before this step are not reused; their narration units still come from the unit cache.
- Calibration across the 82 pages: summaries plan 0.6–3.4 minutes (median 2.9), and the built-in drafter narrates 164–582 words (median 504) without the glossary terms scene. Timed against the trial below, that is a video of about 2–6 minutes.
- Trial: the Step 1 example at `ba57f08` with `--detail summary` built in 41 seconds: 13 scenes, 26 sentences, and 222.2 seconds against 840.4 seconds for the standard video. It passed validation, and its opening, content, and closing slides were inspected.
- Fixed during calibration: the drafter narrated every sentence of an open-questions section that the coverage map summarized, so the standard level's "summarized when long" rule for open questions had no effect. It now keeps the lead and most relevant sentences within the planned words, as it does for other summarized sections. On the 56 of 82 pages whose open questions the map condenses, the narrated open questions fell from 33,372 words to 5,672, against 5,938 planned, and the median standard draft fell from 1,892 to 1,661 words; no condensed section is left without narration. The framing sentence ("The page leaves some points open.") still counts all of the section's points. The Step 1 example's open questions are short, so its video is unchanged; 56 pages' standard storyboards change, and with them their reuse keys.
- Fixed during calibration: Step 4 counted a displayed table as 25 words, but the drafter reads every row aloud. Tables supplied 53,553 of the 164,984 words of the 82 standard drafts, and six pages narrated more than twice their plan; the v17 query planner tutorial narrated 20,889 words against 1,487 planned, 19,845 of them from tables. A table is now planned at the words of its rows as `script._row_sentence` reads them ("first cell: header cell, …"); code and images keep the 25-word allowance. A condensed section keeps its prose as before, or, when it is only a table, the table's first rows within the section's summary words, at least one row; the drafter shows and reads only those rows. A section with neither, such as code alone, is explained when it fits and left out otherwise, so a condensed section never narrates nothing. At the standard level, the drafts now narrate 0.90 to 1.16 times their plan (median 1.04), the longest draft has 1,613 words, 27 sections read a condensed table, and a table-only caveat, such as each of the tutorial's 16 "Exceptions and limitations" tables, is kept in condensed form. The Step 1 example has no narrated table, so its plan and video are unchanged. Summaries never read tables and are unchanged; full-detail drafts are unchanged, but their plans now count their tables.
- Eleven tests were added (130 in all): the option and its default; summary and full-detail coverage, including a nested Short answer and the conclusions of a page without a summary section; an unknown level; a summary draft with a review omission; full detail without a length target; the delivered file name of each level; and an end-to-end summary that builds its own video and is reused by a second summary request. The long-document script test now also condenses long open questions, and two tests plan tables at their rows and condense them to their first rows. Each of these fails when its fix is reverted.

## Proposed project layout

Entries marked `(planned)` do not exist yet. Everything else exists as of Step 13.

```text
postgres-videos/
  plan.md
  README.md
  pyproject.toml
  requirements.in                # Direct requirements
  requirements.lock              # Every wheel with its SHA-256 digest
  tools.lock                     # Python, native tools, browser revisions, and hashes
  scripts/
    setup                        # Provision only inside this project
    pgvideo                      # Apply local environment and invoke .venv Python
    environment.py               # Shared setup/launcher/doctor/test environment and sandbox
    sample_environment.py        # doctor --sample: Kokoro WAV, slide PNG, MP4
    sitecustomize.py             # Installed into .venv; keeps mimetypes off host files
    espeak_cli.py, espeak-ng-runtime, lock_wheels.py
  .venv/                         # All project Python packages; no system site packages
  .runtime/                      # Ignored, reproducible runtime and process state
    python/                      # Pinned base interpreter and standard library
    bin/                         # FFmpeg, ffprobe, espeak-ng
    lib/                         # Additional native libraries
    share/                       # Native tool data, including pronunciation data
    browsers/                    # Playwright-managed Chromium
    home/                        # Child-process home
    config/
    data/
    state/
    tmp/                         # Build, browser, and test temporary files
    environment-report.json
  config/defaults.yaml           # (not built; defaults live in cli.py)
  src/pgvideo/
    cli.py                       # generate (Steps 1, 3–11, and --detail of 13), resume (6–11), script (7–11), narrate (8–11), timing (9–11), render (10–11), validate (11)
    paths.py                     # Project root and escape-checked directories
    sources.py                   # GitHub validation, ref resolution, verified commit files
    assets.py                    # Pinned local Kokoro assets
    markdown.py                  # Front matter, headings, links, tables, block tree
    snapshot.py                  # Step 3 source snapshot and checks
    document.py                  # Step 4 structure, extraction, and coverage map; Step 13 levels of detail
    glossary.py                  # Step 5 glossary index, matching, and version scope
    crosscheck.py                # Step 6 cross-check, pinned GUC facts, claim evidence, resolutions
    script.py                    # Step 7 drafters, scene validation, rechecks, storyboard and script
    speech.py                    # Display text to Kokoro TTS text
    narration.py                 # Step 8 Kokoro WAVs, cache, loudness normalization, sample map
    timing.py                    # Step 9 frame timeline and subtitles
    render.py                    # Step 10 slide rendering and draft MP4
    validate.py                  # Step 11 media checks and delivery
    reuse.py                     # Step 12 video keys, the reuse index, verified reuse, registration
    stages.py                    # Stage order; a repeated stage drops the records built from it
  templates/                     # Step 10 slide.html
  assets/fonts/                  # Inter and Noto Sans Mono with their licenses
  pronunciation/en.yaml          # Terms, identifier parts, abbreviations, and units for TTS text
  tests/                         # test_request.py, test_environment.py, test_sources.py, test_document.py,
                                 # test_glossary.py, test_crosscheck.py, test_script.py, test_timing.py,
                                 # test_render.py, test_validate.py, test_checks.py, test_integration.py,
                                 # test_reuse.py
    fixtures/                    # Small wiki (glossary and one page per case) and pinned PostgreSQL files
  cache/                         # Ignored downloads, models, and reusable assets
    pip/
    wheels/
    downloads/
    huggingface/
    torch/
    sources/<owner>/<repository>/<commit>/   # commit.json, tree.json, files/<path>; the glossary is downloaded per request
    narration/<prefix>/<key>.wav              # Step 8 audio cache
    videos/<key>/<request-id>.json           # Step 12 index of validated videos
  runs/<request-id>/              # Inputs, reports, scripts, scenes, audio, and logs
    request.json                 # Step 1
    manifest.json                # Environment snapshot and source provenance
    sources.json                 # Step 3 snapshot record
    source-report.md             # Step 3 checks and required actions
    inputs/wiki/, inputs/postgres/   # Read-only copies of every retrieved file
    document.json                # Step 4 structure, extracted facts, and coverage map
    coverage.md                  # Step 4 coverage map for review
    glossary-index.json          # Step 5 glossary index built for this request
    glossary-matches.json        # Step 5 matched, ambiguous, and unmatched concepts
    glossary-check.json          # Step 6 results, claims, corrections, exceptions, and omissions
    glossary-check.md            # Step 6 report with blocking issues and resolution snippets
    resolutions.yaml             # Reviewer-written Step 6 resolutions, applied by resume
    draft-input.json             # Step 7 input for any drafter
    storyboard.json              # Step 7 scenes, narration with display and TTS text, checks, coverage
    script.md                    # Step 7 script for review
    narration/units/             # Step 8 lossless 24 kHz unit WAVs
    narration/master-raw.wav, narration/master.wav
    narration/audio-map.json, narration/narration-report.md
    timeline.json                # Step 9 sample and frame timing
    captions.srt, captions.vtt   # Step 9 measured unit captions
    render/slides/, render/draft.mp4, render.json, references.md  # Step 10 draft visual package
    quality-report.json          # Step 11 media and quality checks
  output/<request-id>/           # Step 11 delivery package
    <document-slug>.mp4          # <document-slug>-summary.mp4 or -full.mp4 for those levels (Step 13)
    transcript.md
    captions.srt
    captions.vtt
    references.md
    glossary-check.md
    quality-report.json
    manifest.json
```

Keep `.venv/`, `.runtime/`, `cache/`, and generated runs/outputs out of version control. Commit lockfiles and setup configuration. Recreate the environment after moving the project, because virtual environments can contain absolute paths.

## Completion criteria

- [x] Every project Python command uses the local `.venv/`, backed by the project-local Python runtime, with no global/user package imports. (Step 2)
- [x] All application dependencies, tools, models, fonts, caches, configuration, temporary files, and outputs remain inside the project directory. (Step 2; applies to all later steps)
- [x] Missing local dependencies and paths escaping the project fail clearly; no global dependency fallback is used. (Steps 1–3)
- [x] Setup and sample execution pass the isolation audit, with unavoidable operating system access documented in the environment report. (Step 2; `doctor --sample` passed on 2026-09-28)
- [x] A generation request requires one user-specified Markdown document. (Step 1)
- [x] The document and glossary are read from the same resolved wiki commit. (Step 3)
- [x] The subject and narrated terminology are checked against relevant glossary entries with the correct PostgreSQL version scope. (Steps 5 and 6; meaning is compared through deterministic checks only, without a language model.)
- [x] Unresolved material conflicts return an actionable report before narration proceeds. (Steps 3 and 6; `resume` continues the request after documented resolutions.)
- [x] Narration is generated by Kokoro with recorded model and voice settings. (Step 8)
- [x] Visuals and subtitles follow measured audio timing. (Steps 9–10)
- [x] The result is a playable H.264/AAC MP4 with complete narration. (Step 11 automated decode and audio unit checks)
- [x] The user receives the video and its transcript, subtitles, references, and reports. (Step 11 local delivery package)
- [x] The manifest records enough information to reproduce or resume the request. (Step 12: the environment and every Step 3 input with commits and hashes; each stage's input and output hashes, the glossary index, the resolutions file, the drafter, and the pronunciation dictionary; the tools digest of each media stage; and the video's key with all of its components. A stage record is dropped when an earlier stage repeats. Steps 6–11 can be repeated for the same request; a Step 3 or 4 blocker needs a new request.)
- [x] No video is generated without an explicit request specifying its document. (Steps 1 and 11)
- [x] A request chooses how much of its document the video narrates: a summary of the key points, the standard condensed video, or every section. (Step 13)
