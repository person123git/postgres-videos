import contextlib
import hashlib
import shutil
import io
import json
import re
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.parse import unquote, urlsplit

from pgvideo.cli import NEEDS_REVIEW, parser, prepare
from pgvideo.sources import SourceError, _http_get, git_blob_sha
from pgvideo.snapshot import snapshot_sources


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WIKI = "person123git/postgres-llm-wiki"
POSTGRES = "postgres/postgres"
WIKI_COMMIT = "a" * 40
PIN = "b" * 40
DOCUMENT = "wiki/v18/questions/observability/example.md"
RAW = "../../../../raw/postgres-18"

DOCUMENT_TEXT = f"""---
type: question
version: 18
pinned_commit: {PIN}
verified: false
verified_by_agent: not yet
---

# How Example Works in PostgreSQL 18 (unverified)

## Question

What does a [backend](../../../glossary.md#backend) report?

## Short Answer

It is set in [guc.c#setting]({RAW}/src/backend/guc.c#L2-L3) and read in [status.c#reader]({RAW}/src/status.c#L1).

| Claim | Source |
|---|---|
| Size | [status.c#size]({RAW}/src/status.c#L2-L3) |

![Flow](images/flow.svg)

See [the answer](#short-answer) and [another page](../other.md).

```text
[not a link]({RAW}/src/missing.c#L1)
```

## Source References

- [guc.c]({RAW}/src/backend/guc.c)
"""

GLOSSARY_TEXT = f"""---
type: glossary
verified: false
verified_by_agent: not yet
---

# Wiki Glossary (unverified)

## Scope

A glossary link supplies vocabulary, not proof.

## Source Pins

| Version | Checkout | Branch | Pinned commit |
|---|---|---|---|
| 18 | `raw/postgres-18/` | `REL_18_STABLE` | `{PIN}` |

## Terms

### Backend

**Aliases:** backend process. **Checked on:** PostgreSQL 18.

A backend is the server process that serves one client connection.
"""


def install_project_files(workspace: Path) -> None:
    """Copy the committed project files that a request reads: pronunciation, the runbook, prompts, and schemas."""
    target = workspace / "pronunciation"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PROJECT_ROOT / "pronunciation" / "en.yaml", target / "en.yaml")
    shutil.copyfile(PROJECT_ROOT / "AGENTS.md", workspace / "AGENTS.md")
    for directory in ("prompts", "schemas"):
        shutil.copytree(PROJECT_ROOT / directory, workspace / directory, dirs_exist_ok=True)


def wiki_files(document=DOCUMENT_TEXT, glossary=GLOSSARY_TEXT):
    files = {
        DOCUMENT: document.encode(),
        "wiki/v18/questions/observability/images/flow.svg": b"<svg/>",
        "wiki/v18/questions/other.md": b"# Other\n",
    }
    if glossary is not None:
        files["wiki/glossary.md"] = glossary.encode()
    return files


def postgres_files(configure_version="18.6"):
    return {
        "configure.ac": f"AC_INIT([PostgreSQL], [{configure_version}], [pgsql-bugs@lists.postgresql.org])\n".encode(),
        "src/backend/guc.c": b"line 1\nline 2\nline 3\n",
        "src/status.c": b"a\nb\nc",
    }


class FakeGitHub:
    """Serve the GitHub API and raw file URLs for in-memory repository commits."""

    def __init__(self):
        self.commits: dict[tuple[str, str], dict[str, bytes]] = {}
        self.refs: dict[tuple[str, str], str] = {}
        self.served: dict[tuple[str, str, str], bytes] = {}
        self.urls: list[str] = []

    def add(self, repository, commit, files, refs=()):
        self.commits[repository, commit] = files
        for ref in refs:
            self.refs[repository, ref] = commit

    @staticmethod
    def tree_sha(commit):
        return hashlib.sha1(f"tree {commit}".encode()).hexdigest()

    def __call__(self, url, *, accept=None, timeout=30):
        self.urls.append(url)
        parts = urlsplit(url)
        if parts.hostname == "raw.githubusercontent.com":
            owner, name, commit, path = parts.path.lstrip("/").split("/", 3)
            repository, path = f"{owner}/{name}", unquote(path)
            if (repository, commit, path) in self.served:
                return self.served[repository, commit, path]
            return self.commits.get((repository, commit), {}).get(path)
        if match := re.fullmatch(r"/repos/([^/]+/[^/]+)/commits/(.+)", parts.path):
            repository, ref = match.group(1), unquote(match.group(2))
            commit = self.refs.get((repository, ref), ref)
            return commit.encode() if (repository, commit) in self.commits else None
        if match := re.fullmatch(r"/repos/([^/]+/[^/]+)/git/commits/(\w+)", parts.path):
            repository, commit = match.groups()
            if (repository, commit) not in self.commits:
                return None
            return json.dumps({"sha": commit, "tree": {"sha": self.tree_sha(commit)},
                               "committer": {"date": "2026-09-01T00:00:00Z"}}).encode()
        if match := re.fullmatch(r"/repos/([^/]+/[^/]+)/git/trees/(\w+)", parts.path):
            repository, tree = match.groups()
            commit = next(c for (r, c) in self.commits if r == repository and self.tree_sha(c) == tree)
            entries, directories = [], set()
            for path, data in self.commits[repository, commit].items():
                entries.append({"path": path, "mode": "100644", "type": "blob",
                                "sha": git_blob_sha(data), "size": len(data)})
                directories.update("/".join(path.split("/")[:end]) for end in range(1, path.count("/") + 1))
            entries += [{"path": path, "mode": "040000", "type": "tree", "sha": "0" * 40} for path in directories]
            return json.dumps({"sha": tree, "tree": entries, "truncated": False}).encode()
        raise AssertionError(f"unexpected URL {url}")

    def count(self, pattern):
        return sum(bool(re.search(pattern, url)) for url in self.urls)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pgvideo-test-", dir=PROJECT_ROOT / ".runtime" / "tmp")
        self.addCleanup(temporary.cleanup)
        self.fixture_root = Path(temporary.name).resolve()
        self.workspace = self.fixture_root / "project"
        self.workspace.mkdir()
        self.outside = self.fixture_root / "outside"
        self.outside.mkdir()
        self.github = FakeGitHub()
        self.github.add(WIKI, WIKI_COMMIT, wiki_files(), refs=["master"])
        self.github.add(POSTGRES, PIN, postgres_files())
        self.enterContext(patch("pgvideo.sources._http_get", side_effect=self.github))
        self.runs = 0

    def snapshot(self):
        self.runs += 1
        run_dir = self.workspace / "runs" / f"request-{self.runs}"
        run_dir.mkdir(parents=True)
        request = {"request_id": run_dir.name, "repository": WIKI,
                   "document": {"path": DOCUMENT, "ref": "master"}}
        return snapshot_sources(self.workspace, run_dir, request), run_dir

    def replace_wiki(self, files=None, **changes):
        """Move master to a new commit, since a commit's files never change."""
        self.commits = getattr(self, "commits", 0) + 1
        commit = f"{self.commits:040x}"
        self.github.add(WIKI, commit, files or wiki_files(**changes), refs=["master"])
        return commit

    def issues(self, run_dir, severity):
        record = json.loads((run_dir / "sources.json").read_text(encoding="utf-8"))
        return {issue["code"]: issue for issue in record["issues"] if issue["severity"] == severity}

    def test_snapshot_reads_document_and_glossary_from_one_resolved_commit(self):
        sources, run_dir = self.snapshot()
        self.assertEqual(sources["status"], "passed")
        self.assertEqual(self.github.count(r"/commits/master$"), 1)
        raw_wiki = [url for url in self.github.urls if url.startswith(f"https://raw.githubusercontent.com/{WIKI}/")]
        self.assertEqual(len(raw_wiki), 3)
        self.assertTrue(all(f"/{WIKI_COMMIT}/" in url for url in raw_wiki))

        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "sources_ready")
        self.assertEqual(manifest["sources"]["wiki"]["commit"], WIKI_COMMIT)
        self.assertEqual(manifest["sources"]["wiki"]["requested_ref"], "master")
        self.assertEqual(manifest["sources"]["postgres"]["commit"], PIN)
        self.assertEqual(manifest["sources"]["postgres"]["source_version"], "18.6")
        inputs = {entry["path"]: entry for entry in manifest["sources"]["inputs"]}
        self.assertEqual(set(inputs), {
            DOCUMENT, "wiki/glossary.md", "wiki/v18/questions/observability/images/flow.svg",
            "configure.ac", "src/backend/guc.c", "src/status.c",
        })
        self.assertEqual({inputs[path]["commit"] for path in (DOCUMENT, "wiki/glossary.md")}, {WIKI_COMMIT})
        self.assertEqual(inputs["src/status.c"]["commit"], PIN)
        for path, entry in inputs.items():
            saved = run_dir / entry["input"]
            data = saved.read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])
            self.assertEqual(git_blob_sha(data), entry["git_blob_sha"])
            self.assertFalse(saved.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        self.assertEqual((run_dir / inputs[DOCUMENT]["input"]).read_bytes(), DOCUMENT_TEXT.encode())

    def test_snapshot_preserves_structure_and_resolves_relative_links(self):
        _sources, run_dir = self.snapshot()
        record = json.loads((run_dir / "sources.json").read_text(encoding="utf-8"))
        document = record["document"]
        self.assertEqual(document["title"], "How Example Works in PostgreSQL 18 (unverified)")
        self.assertEqual(document["version"], 18)
        self.assertEqual(document["pinned_commit"], PIN)
        self.assertEqual(document["verification"], {"verified": False, "verified_by_agent": "not yet"})
        self.assertEqual([(h["level"], h["text"], h["line"]) for h in document["headings"]], [
            (1, "How Example Works in PostgreSQL 18 (unverified)", 9), (2, "Question", 11),
            (2, "Short Answer", 15), (2, "Source References", 31),
        ])
        links = {(link["kind"], link.get("target"), link["fragment"]): link for link in document["links"]}
        self.assertEqual(links["glossary", "wiki/glossary.md", "backend"]["line"], 13)
        citation = links["citation", "raw/postgres-18/src/backend/guc.c", "L2-L3"]
        self.assertEqual((citation["source_path"], citation["lines"], citation["line"]),
                         ("src/backend/guc.c", [2, 3], 17))
        self.assertFalse(citation["reference_section"])
        self.assertTrue(links["citation", "raw/postgres-18/src/backend/guc.c", None]["reference_section"])
        self.assertEqual(links["citation", "raw/postgres-18/src/status.c", "L2-L3"]["line"], 21)
        self.assertIn(("wiki", "wiki/v18/questions/other.md", None), links)
        self.assertNotIn("raw/postgres-18/src/missing.c", {link.get("target") for link in document["links"]})
        self.assertEqual([image["path"] for image in record["images"]],
                         ["wiki/v18/questions/observability/images/flow.svg"])
        self.assertEqual(record["glossary"]["source_pins"]["18"]["commit"], PIN)
        self.assertEqual(record["glossary"]["term_count"], 1)
        self.assertEqual(set(self.issues(run_dir, "note")), {"glossary_unverified", "document_unverified"})
        self.assertEqual(self.issues(run_dir, "warning"), {})

    def test_cache_is_reused_by_commit_and_path_and_rechecked(self):
        self.snapshot()
        cache = self.workspace / "cache" / "sources"
        self.assertTrue((cache / WIKI / WIKI_COMMIT / "files" / "wiki" / "glossary.md").is_file())
        cached = cache / POSTGRES / PIN / "files" / "src" / "status.c"
        self.assertEqual(cached.read_bytes(), b"a\nb\nc")

        # A later request resolves the ref and downloads the glossary again; everything else is cached.
        self.github.urls.clear()
        self.snapshot()
        self.assertEqual(self.github.urls, [f"https://api.github.com/repos/{WIKI}/commits/master",
                                            f"https://raw.githubusercontent.com/{WIKI}/{WIKI_COMMIT}/wiki/glossary.md"])

        cached.write_bytes(b"tampered")
        self.github.urls.clear()
        sources, _run_dir = self.snapshot()
        self.assertEqual(sources["status"], "passed")
        self.assertEqual(self.github.count(f"raw.githubusercontent.com/{POSTGRES}/"), 1)
        self.assertEqual(cached.read_bytes(), b"a\nb\nc")

    def test_every_request_downloads_the_glossary_again(self):
        self.snapshot()
        cached = self.workspace / "cache" / "sources" / WIKI / WIKI_COMMIT / "files" / "wiki" / "glossary.md"
        self.assertEqual(cached.read_bytes(), GLOSSARY_TEXT.encode())

        # A download that does not match the commit fails the request, although the cached copy is intact.
        self.github.served[WIKI, WIKI_COMMIT, "wiki/glossary.md"] = b"not the committed glossary"
        with self.assertRaisesRegex(SourceError, "wiki/glossary.md' does not match its Git blob"):
            self.snapshot()
        self.assertEqual(cached.read_bytes(), GLOSSARY_TEXT.encode())

        del self.github.served[WIKI, WIKI_COMMIT, "wiki/glossary.md"]
        self.github.urls.clear()
        sources, run_dir = self.snapshot()
        self.assertEqual(sources["status"], "passed")
        self.assertEqual(self.github.count("raw.githubusercontent.com"), 1)
        self.assertEqual(self.github.count(r"/wiki/glossary\.md$"), 1)
        glossary = next(entry for entry in sources["inputs"] if entry["role"] == "glossary")
        self.assertEqual((run_dir / glossary["input"]).read_bytes(), GLOSSARY_TEXT.encode())

    def test_version_and_pin_conflicts_need_review_before_narration(self):
        cases = {
            "version_mismatch": DOCUMENT_TEXT.replace("version: 18", "version: 17"),
            "version_invalid": DOCUMENT_TEXT.replace("version: 18", "version: eighteen"),
            "citation_version_mismatch": DOCUMENT_TEXT.replace("postgres-18/src/status.c#L1", "postgres-17/src/status.c#L1"),
            "pinned_commit_missing": DOCUMENT_TEXT.replace(f"pinned_commit: {PIN}\n", ""),
            "pinned_commit_invalid": DOCUMENT_TEXT.replace(f"pinned_commit: {PIN}", "pinned_commit: abc123"),
            "pinned_commit_not_found": DOCUMENT_TEXT.replace(PIN, "d" * 40),
            "no_citations": DOCUMENT_TEXT.split("It is set in")[0],
            "front_matter_invalid": DOCUMENT_TEXT.replace("type: question", "type: [question"),
            "not_utf8": None,
        }
        for code, document in cases.items():
            with self.subTest(code=code):
                files = wiki_files() if document is None else wiki_files(document=document)
                if document is None:
                    files[DOCUMENT] = b"\xff\xfe not utf-8"
                self.replace_wiki(files)
                sources, run_dir = self.snapshot()
                self.assertEqual(sources["status"], "needs_review")
                self.assertIn(code, self.issues(run_dir, "blocking"))
                self.assertIsNotNone(self.issues(run_dir, "blocking")[code]["action"])
                report = (run_dir / "source-report.md").read_text(encoding="utf-8")
                self.assertIn(f"`{code}`", report)
                self.assertIn("Action:", report)
                manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest["status"], "needs_review")

    def test_pinned_source_must_report_the_document_version(self):
        self.github.add(POSTGRES, PIN, postgres_files(configure_version="17.2"))
        sources, run_dir = self.snapshot()
        self.assertEqual(sources["status"], "needs_review")
        self.assertIn("17.2", self.issues(run_dir, "blocking")["source_version_mismatch"]["message"])

    def test_postgres_12_source_version_comes_from_configure_in(self):
        files = postgres_files()
        files["configure.in"] = files.pop("configure.ac").replace(b"18.6", b"18.0")
        self.github.add(POSTGRES, PIN, files)
        sources, _run_dir = self.snapshot()
        self.assertEqual((sources["status"], sources["postgres"]["source_version"]), ("passed", "18.0"))

    def test_unavailable_evidence_blocks_unless_cited_only_in_reference_lists(self):
        document = DOCUMENT_TEXT.replace("src/status.c#L1)", "src/gone.c#L1)").replace(
            "src/status.c#L2-L3)", "src/status.c#L2-L4)"
        ) + f"- [old.c]({RAW}/src/old.c#L1)\n- [status.c#late]({RAW}/src/status.c#L9)\n"
        self.replace_wiki(document=document)
        sources, run_dir = self.snapshot()
        self.assertEqual(sources["status"], "needs_review")
        blocking, warnings = self.issues(run_dir, "blocking"), self.issues(run_dir, "warning")
        self.assertEqual(set(blocking), {"evidence_missing", "evidence_range_invalid"})
        self.assertIn("src/gone.c", blocking["evidence_missing"]["message"])
        self.assertEqual(blocking["evidence_range_invalid"]["lines"], [21, 35])
        self.assertIn("3 lines", blocking["evidence_range_invalid"]["message"])
        self.assertIn("src/old.c", warnings["evidence_missing"]["message"])
        self.assertIn("reference lists", warnings["evidence_missing"]["message"])

    def test_broken_non_evidence_links_are_warnings(self):
        document = DOCUMENT_TEXT.replace("#short-answer", "#missing-heading").replace(
            "glossary.md#backend", "glossary.md#no-such-term").replace("../other.md", "../gone.md")
        self.replace_wiki(document=document)
        sources, run_dir = self.snapshot()
        self.assertEqual(sources["status"], "passed")
        self.assertEqual(set(self.issues(run_dir, "warning")),
                         {"anchor_missing", "glossary_anchor_missing", "link_target_missing"})

    def test_glossary_is_required_and_its_version_pin_is_compared(self):
        self.replace_wiki(glossary=GLOSSARY_TEXT.replace(PIN, "e" * 40))
        sources, run_dir = self.snapshot()
        self.assertEqual(sources["status"], "passed")
        self.assertIn("glossary_pin_differs", self.issues(run_dir, "warning"))

        self.replace_wiki(glossary=GLOSSARY_TEXT.replace("| 18 |", "| 17 |"))
        sources, run_dir = self.snapshot()
        self.assertIn("glossary_version_unchecked", self.issues(run_dir, "warning"))

        self.replace_wiki(glossary=None)
        sources, run_dir = self.snapshot()
        self.assertEqual(sources["status"], "needs_review")
        self.assertIn("glossary_missing", self.issues(run_dir, "blocking"))

    def test_tampered_download_fails_without_caching(self):
        self.github.served[POSTGRES, PIN, "src/status.c"] = b"not the committed file"
        with self.assertRaisesRegex(SourceError, "does not match its Git blob"):
            self.snapshot()
        run_dir = self.workspace / "runs" / "request-1"
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "failed")
        self.assertIn("src/status.c", manifest["sources"]["error"])
        self.assertFalse((self.workspace / "cache" / "sources" / POSTGRES / PIN / "files" / "src" / "status.c").exists())

    def test_document_missing_at_resolved_commit_fails(self):
        files = wiki_files()
        del files[DOCUMENT]
        self.replace_wiki(files)
        with self.assertRaisesRegex(SourceError, "may have moved"):
            self.snapshot()

    def test_cache_symlink_escape_is_rejected_before_writing(self):
        (self.workspace / "cache").symlink_to(self.outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "inside the project"):
            self.snapshot()
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_existing_manifest_keeps_its_environment_record(self):
        run_dir = self.workspace / "runs" / "request-1"
        run_dir.mkdir(parents=True)
        (run_dir / "manifest.json").write_text(json.dumps({"request_id": "request-1", "environment": {"x": 1}}))
        request = {"request_id": "request-1", "repository": WIKI, "document": {"path": DOCUMENT, "ref": "master"}}
        snapshot_sources(self.workspace, run_dir, request)
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["environment"], {"x": 1})
        self.assertEqual(manifest["sources"]["wiki"]["commit"], WIKI_COMMIT)

    def test_prepare_command_reports_status(self):
        def contents(path, ref):
            if ref == "main":
                return None
            return {"type": "file", "path": path}

        self.enterContext(patch("pgvideo.cli.project_root", return_value=self.workspace))
        self.enterContext(patch("pgvideo.cli.local_selection"))
        self.enterContext(patch("pgvideo.cli._narrate", return_value=0))
        self.enterContext(patch("pgvideo.sources._github_contents", side_effect=contents))
        install_project_files(self.workspace)
        args = parser().parse_args(["prepare", "--document", DOCUMENT])
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(prepare(args, self.workspace), 0, stderr.getvalue())
        self.assertIn(f"Wiki commit: {WIKI_COMMIT} (ref master)", stdout.getvalue())
        self.assertIn(f"PostgreSQL 18 source commit: {PIN}", stdout.getvalue())

        self.replace_wiki(document=DOCUMENT_TEXT.replace("version: 18", "version: 17"))
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(prepare(args, self.workspace), NEEDS_REVIEW)
        self.assertIn("Needs review: 1 blocking issue", stderr.getvalue())
        self.assertIn("source-report.md", stdout.getvalue())


class HttpTests(unittest.TestCase):
    @staticmethod
    def response(data):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = data
        return response

    def test_download_reads_the_complete_response(self):
        data = b"x" * (64 * 1024 * 1024) + b"end of document"
        with patch("pgvideo.sources.urlopen", return_value=io.BytesIO(data)):
            self.assertEqual(_http_get("https://raw.githubusercontent.com/o/r/c/f"), data)

    def test_token_goes_only_to_github_and_not_through_redirects(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "secret"}), \
                patch("pgvideo.sources.urlopen", return_value=self.response(b"ok")) as opened:
            self.assertEqual(_http_get("https://raw.githubusercontent.com/o/r/c/f"), b"ok")
            request = opened.call_args.args[0]
            self.assertEqual(request.unredirected_hdrs["Authorization"], "Bearer secret")
            self.assertNotIn("Authorization", request.headers)
            _http_get("https://example.com/f")
            self.assertNotIn("Authorization", opened.call_args.args[0].unredirected_hdrs)

    def test_retries_transient_errors_and_reports_denials(self):
        def error(code):
            return HTTPError("https://api.github.com/x", code, "error", {}, None)

        with patch("pgvideo.sources.time.sleep") as slept, patch(
            "pgvideo.sources.urlopen", side_effect=[error(503), error(429), self.response(b"ok")]
        ):
            self.assertEqual(_http_get("https://api.github.com/x"), b"ok")
            self.assertEqual(slept.call_count, 2)
        with patch("pgvideo.sources.urlopen", side_effect=[error(404)]):
            self.assertIsNone(_http_get("https://api.github.com/x"))
        with patch("pgvideo.sources.urlopen", side_effect=[error(403)]), \
                self.assertRaisesRegex(SourceError, "GITHUB_TOKEN"):
            _http_get("https://api.github.com/x")


if __name__ == "__main__":
    unittest.main()
