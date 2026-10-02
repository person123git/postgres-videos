"""Step 12 focused checks: small fixture pages for the failures most likely to mislead a video.

tests/fixtures/wiki/ is served as the wiki repository at one commit, and
tests/fixtures/postgres/ as the PostgreSQL source at the pages' pinned commit. Each
page under wiki/v18/checks/ exercises one case through `prepare`: request
validation, a consistent page, an alias that two glossary entries claim, a central
term that neither the glossary nor the evidence supports, a default that contradicts
the glossary, the same default settled by the pinned source, an entry that the
glossary marks as not present in the page's version, and evidence that is missing at
the pin.
"""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pgvideo.cli import NEEDS_REVIEW, parser, prepare
from pgvideo.script import create_baseline
from test_sources import PIN, POSTGRES, PROJECT_ROOT, WIKI, WIKI_COMMIT, FakeGitHub, install_project_files

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CHECKS = "wiki/v18/checks"
BLOB = f"https://github.com/{WIKI}/blob/master/{CHECKS}"
# Ordinary English words for these checks, in place of Kokoro's lexicon.
ENGLISH = frozenset({"row", "path", "cost"})


def tree(name: str) -> dict[str, bytes]:
    base = FIXTURES / name
    return {path.relative_to(base).as_posix(): path.read_bytes() for path in sorted(base.rglob("*")) if path.is_file()}


class FixtureChecks(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pgvideo-checks-", dir=PROJECT_ROOT / ".runtime" / "tmp")
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name).resolve() / "project"
        self.workspace.mkdir()
        install_project_files(self.workspace)
        self.wiki = tree("wiki")
        self.github = FakeGitHub()
        self.github.add(WIKI, WIKI_COMMIT, self.wiki, refs=["main", "master"])
        self.github.add(POSTGRES, PIN, tree("postgres"))
        self.enterContext(patch("pgvideo.sources._http_get", side_effect=self.github))
        self.enterContext(patch("pgvideo.sources._github_contents", side_effect=self.contents))
        self.enterContext(patch("pgvideo.cli.project_root", return_value=self.workspace))
        self.enterContext(patch("pgvideo.glossary.english_words", return_value=ENGLISH))
        self.narrate = self.enterContext(patch("pgvideo.cli._narrate", return_value=0))

    def contents(self, path, ref):
        """Answer GitHub's contents API from the fixture tree at main or master."""
        if ref not in {"main", "master"}:
            return None
        if path in self.wiki:
            return {"type": "file", "path": path}
        if any(name.startswith(path + "/") for name in self.wiki):
            return [{"type": "file", "path": name} for name in self.wiki if name.startswith(path + "/")]
        return None

    def prepare(self, document, *options):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = prepare(parser().parse_args(["prepare", "--document", document, *options]), self.workspace)
        run_dir = next((Path(line.removeprefix("Validated request: ")).parent
                        for line in stdout.getvalue().splitlines() if line.startswith("Validated request: ")), None)
        return status, stderr.getvalue(), run_dir

    @staticmethod
    def manifest(run_dir):
        return json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    @staticmethod
    def record(run_dir, name):
        return json.loads((run_dir / name).read_text(encoding="utf-8"))

    def test_invalid_requests_fail_before_creating_a_request(self):
        cases = [
            ((f"{CHECKS}/missing.md",), "was not found at ref 'main'"),
            ((CHECKS,), "is a directory"),
            ((f"{CHECKS}/notes.txt",), "is not a Markdown (.md) file"),
            ((f"{CHECKS}/*.md",), "globs are not supported"),
            ((f"../{CHECKS}/consistent.md",), "must not contain empty, '.' or '..' segments"),
            ((f"https://github.com/other/wiki/blob/master/{CHECKS}/consistent.md",), f"must belong to github.com/{WIKI}"),
            ((f"{BLOB}/consistent.md", "--ref", "other"), "conflicts with URL ref 'master'"),
            ((f"{CHECKS}/consistent.md", "--ref", "missing-branch"), "was not found at ref 'missing-branch'"),
            ((f"{CHECKS}/consistent.md", "--output", "../outside"), "must stay inside the project directory"),
            ((f"{CHECKS}/consistent.md", "--voice", "af_missing"), "a/af_missing is not provisioned"),
        ]
        for (document, *options), message in cases:
            with self.subTest(document=document, options=options):
                status, stderr, run_dir = self.prepare(document, *options)
                self.assertEqual(status, 1)
                self.assertIn(message, stderr)
                self.assertIsNone(run_dir)
        self.assertFalse((self.workspace / "runs").exists())
        self.assertFalse((self.workspace.parent / "outside").exists())
        self.narrate.assert_not_called()
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            parser().parse_args(["prepare", "--document", f"{CHECKS}/consistent.md", "--width", "1919"])

    def test_consistent_page_reaches_the_evidence_packet_from_a_path_or_a_blob_url(self):
        stages = ("sources", "document", "glossary", "glossary_check", "evidence")
        for document in (f"{CHECKS}/consistent.md", f"{BLOB}/consistent.md"):
            with self.subTest(document=document):
                status, stderr, run_dir = self.prepare(document)
                self.assertEqual(status, 0, stderr)
                manifest = self.manifest(run_dir)
                self.assertEqual({stage: manifest[stage]["status"] for stage in stages},
                                 dict.fromkeys(stages, "passed"))
                # The harness writes the content; prepare stops before it.
                self.assertFalse({"plan", "script"} & set(manifest))
                self.narrate.assert_not_called()
                results = {r["id"]: r["result"] for r in self.record(run_dir, "glossary-check.json")["results"]}
                # "PostgreSQL 18 has no slot scanner" agrees with the entry's Not present note.
                self.assertEqual((results["entry:example_size"], results["entry:slot-scanner"]),
                                 ("consistent", "consistent"))

    def test_each_failure_stops_the_request_before_narration(self):
        cases = {
            "alias-collision": ("glossary_check", {"ambiguous:pg_subtrans:slru+subtransaction"}),
            "missing-term": ("glossary_check", {"term:missing_widget", "claim@short-answer.1.s1"}),
            "contradictory-default": ("glossary_check", {"fact:example_size:default@short-answer.1.s1"}),
            "version-exception": ("glossary_check", {"entry:slot-scanner"}),
            "incomplete-evidence": ("sources", {"evidence_range_invalid", "evidence_missing"}),
        }
        for page, (stage, expected) in cases.items():
            with self.subTest(page=page):
                status, stderr, run_dir = self.prepare(f"{CHECKS}/{page}.md")
                self.assertEqual(status, NEEDS_REVIEW, stderr)
                manifest = self.manifest(run_dir)
                self.assertEqual((manifest["status"], manifest[stage]["status"]), ("needs_review", "needs_review"))
                self.assertFalse({"script", "narration", "reuse"} & set(manifest))
                if stage == "sources":
                    issues = self.record(run_dir, "sources.json")["issues"]
                    self.assertEqual({issue["code"] for issue in issues if issue["severity"] == "blocking"}, expected)
                    self.assertFalse((run_dir / "document.json").exists())
                else:
                    issues = self.record(run_dir, "glossary-check.json")["issues"]
                    self.assertEqual({issue["ids"][0] for issue in issues if issue["severity"] == "blocking"},
                                     expected)
        self.narrate.assert_not_called()

    def test_the_pinned_source_settles_a_contradictory_default(self):
        status, stderr, run_dir = self.prepare(f"{CHECKS}/corrected-default.md")
        self.assertEqual(status, 0, stderr)
        check = self.record(run_dir, "glossary-check.json")
        (correction,) = check["corrections"]
        self.assertEqual((correction["setting"], correction["corrected"], correction["source"]),
                         ("example_size", "1024 bytes", "pinned_source"))
        # The evidence packet hands the correction to the harness; the extractive baseline applies it.
        packet = self.record(run_dir, "evidence-packet.json")
        self.assertEqual([c["id"] for c in packet["review_state"]["corrections"]], [correction["id"]])
        create_baseline(self.workspace, run_dir)
        narration = [item["text"] for scene in self.record(run_dir, "baseline/storyboard.json")["scenes"]
                     for item in scene["narration"]]
        self.assertTrue(any("`example_size`" in text and "1024 bytes" in text for text in narration), narration)
        self.assertFalse(any("2048" in text for text in narration))
        # The snapshot keeps the page as published; only the script is corrected.
        self.assertIn(b"defaults to 2048 bytes", (run_dir / f"inputs/wiki/{CHECKS}/corrected-default.md").read_bytes())


if __name__ == "__main__":
    unittest.main()
