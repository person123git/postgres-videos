import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pgvideo.cli import NEEDS_REVIEW, parser, resume, script
from pgvideo.crosscheck import RESOLUTIONS, check_glossary
from pgvideo.document import _leaves, _table_words, parse_document
from pgvideo.glossary import match_glossary
from pgvideo.script import DRAFT_INPUT, SCRIPT, STORYBOARD, bullet, create_script, edges, short_sentences
from pgvideo.snapshot import snapshot_sources
from pgvideo.speech import Pronunciation, PronunciationError, unspeakable
from test_crosscheck import BLOCKING, ENGLISH, GLOSSARY, STATUS_CITE, VIEWS_CITE, guc, postgres_snapshot
from test_sources import DOCUMENT, PIN, POSTGRES, PROJECT_ROOT, WIKI, FakeGitHub, install_project_files, wiki_files

# A page with every kind of scene: the question, a summary with a pinned-source correction, a relationship
# diagram, an ordered list, a table and a code block with their introductions, a caveat, and an open question.
PAGE = f"""---
type: question
version: 18
pinned_commit: {PIN}
verified: false
---

# How `example_size` Is Used in PostgreSQL 18 (unverified)

## Question

In PostgreSQL 18, how is `example_size` used?

## Short Answer

`example_size` sets the byte size of each slot behind `pg_stat_activity` {guc("example_size")}; it defaults to `1024` bytes and is stored in `pgstat_example_size` {guc("example_size")}.

The setting is `PGC_POSTMASTER`, so a change needs a restart {guc("example_size")}.

## Read Path

`pg_stat_activity` is a SQL view over `pg_stat_get_activity(NULL)` {VIEWS_CITE}. `pg_stat_get_activity()` then uses `example_widget` to read the slots {STATUS_CITE} {VIEWS_CITE}.

1. The backend writes its slot first {STATUS_CITE}.
2. A reader copies the slot afterward {STATUS_CITE}.

## Details

`example_flag` is off by default {guc("example_flag")}.

`example_timeout` limits each wait only when `example_flag` is on {guc("example_timeout")}.

The defaults are:

| Parameter | Default |
|---|---|
| `example_size` | `1024` |
| `example_timeout` | `1000` |

The query below reads the slots:

```sql
SELECT query
FROM pg_stat_activity;
```

The `query` column shows the slot text {VIEWS_CITE}.

## Known Limitations

`example_size` does not change `example_timeout` {guc("example_size")}.

## Open Questions

- No test for a large `example_size` was found.

## Source References

- [guc_tables.c#example_size]({guc("example_size").split("](")[1][:-1]})
"""

DRAFTER = """#!/bin/sh
# Test drafter: keep the draft input it receives and answer with a fixed scene file, using shell builtins only.
dir=${0%/*}
while IFS= read -r line || [ -n "$line" ]; do printf '%s\\n' "$line"; done > "$dir/received.json"
while IFS= read -r line || [ -n "$line" ]; do printf '%s\\n' "$line"; done < "$dir/scenes.yaml"
"""


class ScriptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pgvideo-test-", dir=PROJECT_ROOT / ".runtime" / "tmp")
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name).resolve() / "project"
        self.workspace.mkdir()
        install_project_files(self.workspace)
        self.github = FakeGitHub()
        self.github.add(POSTGRES, PIN, postgres_snapshot())
        self.enterContext(patch("pgvideo.sources._http_get", side_effect=self.github))
        self.enterContext(patch("pgvideo.glossary.english_words", return_value=ENGLISH))
        self.runs = 0

    def checked(self, document=PAGE, glossary=GLOSSARY, detail=None) -> Path:
        """Run Steps 3 to 6 on a document and return its run directory."""
        self.runs += 1
        self.github.add(WIKI, f"{self.runs:040x}", wiki_files(document=document, glossary=glossary), refs=["master"])
        run_dir = self.workspace / "runs" / f"request-{self.runs}"
        run_dir.mkdir(parents=True)
        request = {"request_id": run_dir.name, "repository": WIKI, "document": {"path": DOCUMENT, "ref": "master"},
                   "settings": {"voice": "af_heart", "language": "a", **({"detail": detail} if detail else {})}}
        (run_dir / "request.json").write_text(json.dumps(request), encoding="utf-8")
        self.assertEqual(snapshot_sources(self.workspace, run_dir, request)["status"], "passed",
                         (run_dir / "source-report.md").read_text())
        self.assertEqual(parse_document(self.workspace, run_dir)["status"], "passed")
        match_glossary(self.workspace, run_dir)
        return run_dir

    def draft(self, document=PAGE, detail=None, **options) -> tuple[dict, dict, Path]:
        """Run Steps 3 to 7 and return the manifest record, the storyboard, and the run directory."""
        run_dir = self.checked(document, detail=detail)
        check = check_glossary(self.workspace, run_dir)
        self.assertEqual(check["status"], "passed", (run_dir / "glossary-check.md").read_text())
        return self.redraft(run_dir, **options)

    def redraft(self, run_dir: Path, **options) -> tuple[dict, dict, Path]:
        result = create_script(self.workspace, run_dir, **options)
        return result, json.loads((run_dir / STORYBOARD).read_text(encoding="utf-8")), run_dir

    def edit(self, run_dir: Path, storyboard: dict, change) -> tuple[dict, dict]:
        """Import a changed copy of a storyboard; return the result and the codes of its blocking issues."""
        edited = copy.deepcopy(storyboard)
        change(edited)
        path = run_dir / "edited.json"
        path.write_text(json.dumps(edited), encoding="utf-8")
        result, record, _run_dir = self.redraft(run_dir, storyboard=path)
        return record, {issue["code"] for issue in record["issues"] if issue["severity"] == "blocking"}

    @staticmethod
    def scenes(record: dict) -> dict:
        return {scene["id"]: scene for scene in record["scenes"]}

    @staticmethod
    def find(record: dict, predicate) -> dict:
        return next(scene for scene in record["scenes"] if predicate(scene))

    def test_builtin_draft_traces_every_scene_to_the_document(self):
        result, record, run_dir = self.draft()
        self.assertEqual(result["status"], "passed", [i for i in record["issues"] if i["severity"] == "blocking"])
        for name in (DRAFT_INPUT, STORYBOARD, SCRIPT):
            self.assertTrue((run_dir / name).is_file(), name)
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((manifest["status"], manifest["script"]["status"]), ("script_ready", "passed"))
        self.assertEqual(manifest["script"]["drafter"], {"kind": "builtin", "name": "builtin-extractive",
                                                         "version": 1})
        self.assertEqual(manifest["script"]["pronunciation"]["file"], "pronunciation/en.yaml")
        self.assertEqual(record["inputs"]["glossary_check"], manifest["glossary_check"]["sha256"])

        parts = [scene["part"] for scene in record["scenes"]]
        self.assertEqual(parts[0], "opening")
        self.assertEqual(parts[-2:], ["recap", "credits"])
        order = ["opening", "question", "terminology", "answer", "mechanism", "caveat", "open_questions", "recap",
                 "credits"]
        self.assertEqual([p for p in dict.fromkeys(parts) if p in order], order)
        opening = record["scenes"][0]
        self.assertIn("PostgreSQL 18", opening["screen"]["lines"])
        document = json.loads((run_dir / "document.json").read_text(encoding="utf-8"))
        ids = {section["id"] for section in document["sections"]}
        for section in document["sections"]:
            for block in section["blocks"]:
                ids.add(block["id"])
                ids.update(s["id"] for s in block.get("sentences", []))
                ids.update(row["id"] for row in block.get("rows", []))
                for item in block.get("items", []):
                    ids.add(item["id"])
                    for child in item["blocks"]:
                        ids.add(child["id"])
                        ids.update(s["id"] for s in child.get("sentences", []))
        for scene in record["scenes"]:
            self.assertTrue(scene["visual"])
            if scene["part"] not in ("opening", "credits"):
                self.assertTrue(scene["sources"] or scene["glossary"], scene["id"])
            self.assertLessEqual(set(scene["sources"]), ids, scene["id"])
            for item in scene["narration"]:
                self.assertEqual(unspeakable(item["tts"]), [], item["tts"])
                if item["origin"] in ("document", "table", "correction"):
                    self.assertTrue(item["sources"], item)
                self.assertNotEqual(item["check"]["status"], "failed", item)

        question = self.find(record, lambda s: s["part"] == "question")
        self.assertEqual(question["screen"]["lines"], ["In PostgreSQL 18, how is `example_size` used?"])
        terms = self.find(record, lambda s: s["part"] == "terminology")
        self.assertEqual([t["anchor"] for t in terms["screen"]["terms"]], ["pg_stat_activity"])
        self.assertEqual([n["origin"] for n in terms["narration"]], ["framing", "glossary"])

        answer = self.find(record, lambda s: s["part"] == "answer")
        texts = [n["text"] for n in answer["narration"]]
        # The semicolon splits one long sentence into two spoken sentences with the same words.
        self.assertEqual(texts[:2], ["`example_size` sets the byte size of each slot behind `pg_stat_activity`.",
                                     "It defaults to `1024` bytes and is stored in `pgstat_example_size`."])
        self.assertEqual({n["check"]["status"] for n in answer["narration"]}, {"unchanged"})
        self.assertEqual(answer["narration"][0]["tts"],
                         "example size sets the byte size of each slot behind P G stat activity.")

        diagram = self.find(record, lambda s: s["screen"]["layout"] == "diagram")
        labels = {node["id"]: node["label"] for node in diagram["screen"]["diagram"]["nodes"]}
        self.assertEqual([(labels[e["from"]], e["label"], labels[e["to"]]) for e in diagram["screen"]["diagram"]["edges"]],
                         [("`pg_stat_activity`", "view over", "`pg_stat_get_activity()`"),
                          ("`pg_stat_get_activity()`", "uses", "`example_widget`")])
        steps = self.find(record, lambda s: s["screen"]["layout"] == "steps")
        self.assertEqual(steps["screen"]["lines"], ["The backend writes its slot first",
                                                    "A reader copies the slot afterward"])

        # The pinned GUC table says example_flag is on by default; the script says so, and the snapshot is unchanged.
        corrected = next(n for s in record["scenes"] for n in s["narration"] if n.get("correction"))
        self.assertEqual(corrected["text"], "`example_flag` is on by default.")
        self.assertEqual(corrected["check"]["status"], "rechecked")
        self.assertEqual([c["applied"] for c in record["corrections"]], [True])

        table = self.find(record, lambda s: s["screen"]["layout"] == "table")
        self.assertEqual(table["screen"]["table"]["rows"], [["`example_size`", "`1024`"],
                                                           ["`example_timeout`", "`1000`"]])
        self.assertEqual([n["text"] for n in table["narration"]],
                         ["The defaults are.", "`example_size`: default `1024`.", "`example_timeout`: default `1000`."])
        self.assertEqual([n["check"]["status"] for n in table["narration"][1:]], ["unchanged", "unchanged"])
        code = self.find(record, lambda s: s["screen"]["layout"] == "code")
        self.assertEqual(code["screen"]["code"]["content"], "SELECT query\nFROM pg_stat_activity;")
        self.assertEqual([n["text"] for n in code["narration"]], ["The query below reads the slots.",
                                                                  "The `query` column shows the slot text."])
        self.assertEqual(code["part"], "example")

        caveat = self.find(record, lambda s: s["part"] == "caveat")
        self.assertEqual(caveat["screen"]["heading"], "Known Limitations")
        # A negated sentence keeps its whole wording on screen.
        self.assertEqual(caveat["screen"]["lines"], ["`example_size` does not change `example_timeout`"])
        open_questions = self.find(record, lambda s: s["part"] == "open_questions")
        self.assertEqual(open_questions["narration"][0]["text"], "The page leaves one point open.")
        covered = {row["section"]: row for row in record["coverage"]}
        for section in ("question", "short-answer", "read-path", "details", "known-limitations", "open-questions"):
            self.assertTrue(covered[section]["scenes"], section)
            self.assertEqual(covered[section]["narrated"], covered[section]["narratable"], section)
        self.assertEqual(covered["source-references"]["scenes"], [])

        draft_input = json.loads((run_dir / DRAFT_INPUT).read_text(encoding="utf-8"))
        self.assertEqual(draft_input["document"]["version"], 18)
        self.assertNotIn("source-references", [s["id"] for s in draft_input["sections"]])
        allowed = {e["anchor"]: e["allowed"] for e in draft_input["glossary"]["entries"]}
        self.assertTrue(allowed["pg_stat_activity"])
        rendered = (run_dir / SCRIPT).read_text(encoding="utf-8")
        self.assertIn("- Status: **passed**", rendered)
        self.assertIn("<summary>TTS text</summary>", rendered)
        self.assertIn("## Coverage", rendered)

        # The built-in drafter is deterministic.
        _result, again, _run_dir = self.redraft(run_dir)
        self.assertEqual(again["scenes"], record["scenes"])

    def test_edited_scenes_are_rechecked_against_their_sources_and_the_pinned_evidence(self):
        _result, record, run_dir = self.draft()
        answer = next(s["id"] for s in record["scenes"] if s["part"] == "answer")
        read = next(s["id"] for s in record["scenes"] if s["screen"]["layout"] == "diagram")
        table = next(s["id"] for s in record["scenes"] if s["screen"]["layout"] == "table")
        code = next(s["id"] for s in record["scenes"] if s["screen"]["layout"] == "code")
        caveat = next(s["id"] for s in record["scenes"] if s["part"] == "caveat")
        terms = next(s["id"] for s in record["scenes"] if s["part"] == "terminology")

        def scene(identifier):
            return lambda edited: self.scenes(edited)[identifier]

        def sentence(identifier, number, text):
            return lambda edited: scene(identifier)(edited)["narration"][number].update(text=text)

        def replace(prefix, text):
            return lambda edited: next(n for s in edited["scenes"] for n in s["narration"]
                                       if n["text"].startswith(prefix)).update(text=text)

        # An unchanged copy passes, and a shortened sentence with the same facts is rechecked and passes.
        edited, blocking = self.edit(run_dir, record, lambda edited: None)
        self.assertEqual(blocking, set())
        self.assertEqual(edited["drafter"]["kind"], "file")
        edited, blocking = self.edit(run_dir, record, sentence(
            answer, 0, "`example_size` sets the size in bytes of each slot behind `pg_stat_activity`."))
        self.assertEqual(blocking, set())
        check = self.scenes(edited)[answer]["narration"][0]["check"]
        self.assertEqual((check["status"], check["claim"]), ("rechecked", "verified"))
        # A verbatim prefix is unchanged, unless what it leaves out limits the statement.
        edited, blocking = self.edit(run_dir, record, sentence(answer, 0, "`example_size` sets the byte size."))
        self.assertEqual(blocking, set())
        self.assertEqual(self.scenes(edited)[answer]["narration"][0]["check"]["status"], "unchanged")

        cases = {
            "fact_contradicts_source": sentence(answer, 1, "It defaults to `2048` bytes."),
            "qualifier_dropped": replace("`example_timeout` limits", "`example_timeout` limits each wait."),
            "polarity_changed": sentence(caveat, 0, "`example_size` changes `example_timeout`."),
            "unsupported_edit": sentence(answer, 0, "`example_size` sets the size of `made_up_buffer` slots."),
            "correction_not_applied": replace("`example_flag` is", "`example_flag` is off by default."),
            "framing_claim": lambda edited: edited["scenes"][0]["narration"].append(
                {"text": "It reserves 64 MB in PostgreSQL 17.", "origin": "framing"}),
            "missing_sources": lambda edited: edited["scenes"][0]["narration"].append(
                {"text": "Slots are sized at startup.", "origin": "document"}),
            "screen_untraceable": lambda edited: scene(answer)(edited)["screen"]["lines"].append(
                "Also sets `shared_buffers`"),
            "table_mismatch": lambda edited: scene(table)(edited)["screen"]["table"]["rows"][0].__setitem__(
                1, "`2048`"),
            "code_mismatch": lambda edited: scene(code)(edited)["screen"]["code"].update(content="SELECT 1;"),
            "diagram_untraceable": lambda edited: scene(read)(edited)["screen"]["diagram"]["edges"][0].update(
                source=None),
            "definition_changed": lambda edited: scene(terms)(edited)["screen"]["terms"][0].update(
                definition="`pg_stat_activity` is a table."),
            "definition_not_allowed": lambda edited: scene(terms)(edited)["narration"].append(
                {"text": "The slot scanner walks every slot.", "origin": "glossary", "glossary": ["slot-scanner"]}),
            "unknown_source": lambda edited: scene(answer)(edited)["narration"][0].update(sources=["no-such-id"]),
            "unknown_citation": lambda edited: scene(answer)(edited).update(citations=[9999]),
            "excluded_source": lambda edited: scene(answer)(edited)["sources"].append("source-references"),
            "section_not_covered": lambda edited: edited["scenes"].remove(scene(caveat)(edited)),
            "unspeakable_tts": lambda edited: scene(answer)(edited)["narration"][0].update(
                tts="example_size sets the size.", tts_source="manual"),
            "version_missing": lambda edited: edited["scenes"][0]["screen"].update(lines=[], heading="Slots"),
            "no_opening": lambda edited: edited["scenes"].insert(0, edited["scenes"].pop(1)),
        }
        for code_name, change in cases.items():
            with self.subTest(code=code_name):
                edited, blocking = self.edit(run_dir, record, change)
                self.assertIn(code_name, blocking)
                self.assertEqual(edited["status"], "needs_review")
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((manifest["status"], manifest["script"]["status"]), ("needs_review", "needs_review"))

        # A manual TTS text is kept when it is speakable; a section can be left out with a recorded reason.
        def override(edited):
            edited["scenes"].remove(scene(caveat)(edited))
            edited["coverage_overrides"] = [{"section": "known-limitations", "reason": "Shown in the next video."}]
            scene(answer)(edited)["narration"][0].update(tts="example size sets the size of each slot.",
                                                         tts_source="manual")

        edited, blocking = self.edit(run_dir, record, override)
        self.assertEqual(blocking, set())
        self.assertIn("section_left_out", {issue["code"] for issue in edited["issues"]})
        self.assertEqual(self.scenes(edited)[answer]["narration"][0]["tts"], "example size sets the size of each slot.")

    def test_invalid_scene_files_fail_clearly(self):
        _result, record, run_dir = self.draft()
        outside = Path(tempfile.mkdtemp(prefix="pgvideo-outside-", dir=PROJECT_ROOT / ".runtime" / "tmp"))
        self.addCleanup(lambda: [p.unlink() for p in outside.iterdir()] and None or outside.rmdir())
        (outside / "scenes.json").write_text(json.dumps(record), encoding="utf-8")
        (run_dir / "link.json").symlink_to(outside / "scenes.json")
        yaml_alias = "scenes:\n  - &a {id: x, title: t, screen: {layout: bullets}, narration: [hi]}\n  - *a\n"
        (run_dir / "alias.yaml").write_text(yaml_alias, encoding="utf-8")
        cases = {
            "unknown keys: extra": lambda r: r["scenes"][0].update(extra=1),
            "nonempty narration": lambda r: r["scenes"][0].update(narration=[]),
            "used twice": lambda r: r["scenes"][1].update(id=r["scenes"][0]["id"]),
            "screen layout must be one of": lambda r: r["scenes"][0]["screen"].update(layout="slideshow"),
            "citations must be link IDs": lambda r: r["scenes"][0].update(citations=["guc.c"]),
            "origin must be one of": lambda r: r["scenes"][0]["narration"][0].update(origin="model"),
            "tts_source manual needs": lambda r: r["scenes"][0]["narration"][0].update(tts="", tts_source="manual"),
            "part must be one of": lambda r: r["scenes"][0].update(part="intro"),
            "nonempty `scenes` list": lambda r: r.update(scenes=[]),
            "coverage_overrides item 1": lambda r: r.update(coverage_overrides=[{"section": "x", "reason": "y"}]),
        }
        for message, change in cases.items():
            with self.subTest(message=message):
                edited = copy.deepcopy(record)
                change(edited)
                (run_dir / "bad.json").write_text(json.dumps(edited), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    create_script(self.workspace, run_dir, storyboard=Path("runs") / run_dir.name / "bad.json")
        for path, message in ((run_dir / "alias.yaml", "must not use YAML aliases"),
                              (run_dir / "link.json", "Scene file"),
                              (outside / "scenes.json", "Scene file"),
                              (run_dir / "missing.json", "must be a regular file")):
            with self.subTest(path=path.name):
                with self.assertRaisesRegex(ValueError, message):
                    create_script(self.workspace, run_dir, storyboard=path)
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((manifest["status"], manifest["script"]["status"]), ("failed", "failed"))

    def test_drafter_command_receives_the_draft_input(self):
        _result, record, run_dir = self.draft()
        drafters = self.workspace / "drafters"
        drafters.mkdir()
        command = drafters / "draft.sh"
        command.write_text(DRAFTER, encoding="utf-8")
        command.chmod(0o755)
        opening = record["scenes"][0]
        answer = next(s for s in record["scenes"] if s["part"] == "answer")
        scenes = {"scenes": [
            {key: opening[key] for key in ("id", "part", "title", "screen", "narration")},
            {"id": "answer", "part": "answer", "title": "Short Answer",
             "screen": {"layout": "bullets", "heading": "Short Answer", "lines": ["The setting is `PGC_POSTMASTER`"]},
             "narration": [{"text": n["text"], "sources": n["sources"]} for n in answer["narration"]]},
        ]}
        (drafters / "scenes.yaml").write_text(json.dumps(scenes), encoding="utf-8")
        result, drafted, _run_dir = self.redraft(run_dir, command=Path("drafters/draft.sh"))
        self.assertEqual(json.loads((drafters / "received.json").read_text(encoding="utf-8")),
                         json.loads((run_dir / DRAFT_INPUT).read_text(encoding="utf-8")))
        self.assertEqual(drafted["drafter"]["kind"], "command")
        self.assertEqual(drafted["drafter"]["name"], "drafters/draft.sh")
        # The external draft leaves out sections that the coverage map explains.
        self.assertEqual(result["status"], "needs_review")
        blocking = [i for i in drafted["issues"] if i["severity"] == "blocking"]
        self.assertEqual({i["code"] for i in blocking}, {"section_not_covered"})
        self.assertEqual({i["message"].split("section ")[1].split(" ")[0] for i in blocking},
                         {"question", "known-limitations", "open-questions"})
        self.assertEqual(self.scenes(drafted)["answer"]["narration"][0]["origin"], "document")

        command.write_text("#!/bin/sh\necho 'drafter failed' >&2\nexit 7\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "exited with status 7: drafter failed"):
            self.redraft(run_dir, command=Path("drafters/draft.sh"))
        command.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "is not executable"):
            self.redraft(run_dir, command=Path("drafters/draft.sh"))
        with self.assertRaisesRegex(ValueError, "not both"):
            create_script(self.workspace, run_dir, command=command, storyboard=command)

    def test_long_documents_are_summarized_within_the_coverage_budget(self):
        filler = " ".join(f"Sentence {n} explains another detail of the slot mechanism." for n in range(40))
        sections = ["## Background Part {}\n\n`example_size` matters here. {}".format(n, filler) for n in range(1, 12)]
        # Open questions longer than the coverage map explains in full are condensed like other sections.
        known = "- No test for a large `example_size` was found.\n"
        questions = "".join(f"- Whether workload {n} needs a larger slot has not been measured.\n"
                            for n in range(1, 13))
        page = PAGE.replace("## Known Limitations", "\n\n".join(sections) + "\n\n## Known Limitations").replace(
            known, known + questions)
        result, record, run_dir = self.draft(page)
        document = json.loads((run_dir / "document.json").read_text(encoding="utf-8"))
        coverage = {entry["section"]: entry for entry in document["coverage"]["sections"]}
        self.assertTrue(document["coverage"]["long_document"])
        rows = {row["section"]: row for row in record["coverage"]}
        for section, entry in coverage.items():
            if entry["decision"] == "summarize":
                self.assertTrue(rows[section]["scenes"], section)
                self.assertLess(rows[section]["narrated"], rows[section]["narratable"], section)
                words = sum(len(n["text"].split()) for s in record["scenes"] for n in s["narration"]
                            if any(src.startswith(section + ".") for src in n["sources"]))
                self.assertLessEqual(words, entry["planned_words"] + 15, section)
            elif entry["decision"] == "omit":
                self.assertEqual(rows[section]["scenes"], [], section)
        self.assertIn("summarize", {entry["decision"] for entry in coverage.values()})
        self.assertEqual(coverage["open-questions"]["decision"], "summarize")
        # The framing counts the page's open points, not only the ones the video narrates.
        opening = self.find(record, lambda scene: scene["part"] == "open_questions")["narration"][0]
        self.assertEqual(opening["text"], "The page leaves some points open.")
        self.assertEqual(rows["known-limitations"]["narrated"], rows["known-limitations"]["narratable"])
        # The coverage map already condensed a long document, so its length is only reported.
        self.assertNotIn(("warning", "long_script"), {(i["severity"], i["code"]) for i in record["issues"]})
        self.assertEqual(result["status"], "passed")

    def test_summary_narrates_the_kept_sentences_without_a_recap(self):
        result, record, run_dir = self.draft(detail="summary")
        self.assertEqual(result["status"], "passed", [i for i in record["issues"] if i["severity"] == "blocking"])
        self.assertEqual((result["detail"], record["settings"]["detail"], record["settings"]["target_minutes"]),
                         ("summary", "summary", [1, 3]))
        opening = record["scenes"][0]
        self.assertEqual(opening["screen"]["lines"][:2], ["PostgreSQL 18", "Summary"])
        self.assertIn("This video summarizes the page's main points.", [n["text"] for n in opening["narration"]])
        parts = [scene["part"] for scene in record["scenes"]]
        self.assertNotIn("recap", parts)
        self.assertEqual(parts[-1], "credits")
        # Sections reduced to their lead sentence narrate only it, without the tables and code they display.
        self.assertFalse({"code", "table"} & {scene["screen"]["layout"] for scene in record["scenes"]})
        rows = {row["section"]: row for row in record["coverage"]}
        document = json.loads((run_dir / "document.json").read_text(encoding="utf-8"))
        coverage = {entry["section"]: entry for entry in document["coverage"]["sections"]}
        for section in ("read-path", "details", "known-limitations"):
            keep = coverage[section]["keep"]
            narrated = [source for scene in record["scenes"] for n in scene["narration"] for source in n["sources"]
                        if source.startswith(section + ".")]
            self.assertEqual(sorted(set(narrated)), keep, section)
            self.assertEqual(rows[section]["narrated"], 1, section)
        for section in ("read-path", "details"):
            self.assertLess(rows[section]["narrated"], rows[section]["narratable"], section)
        self.assertEqual(rows["short-answer"]["narrated"], rows["short-answer"]["narratable"])
        draft_input = json.loads((run_dir / DRAFT_INPUT).read_text(encoding="utf-8"))
        self.assertEqual(draft_input["constraints"]["detail"], "summary")
        self.assertIn("summarizes this document", draft_input["purpose"])
        self.assertEqual({s["id"]: s["keep"] for s in draft_input["sections"]}["read-path"],
                         coverage["read-path"]["keep"])
        self.assertIn("- Level of detail: summary", (run_dir / SCRIPT).read_text(encoding="utf-8"))

        # A kept sentence that a review omits gives way to the section's next sentence.
        (run_dir / RESOLUTIONS).write_text(
            "resolutions:\n  - id: claim@read-path.1.s1\n    decision: omit\n    reason: Not needed.\n",
            encoding="utf-8")
        check = check_glossary(self.workspace, run_dir)
        self.assertEqual(check["status"], "passed", (run_dir / "glossary-check.md").read_text())
        result, record, _run_dir = self.redraft(run_dir)
        self.assertEqual(result["status"], "passed")
        narrated = {source for scene in record["scenes"] for n in scene["narration"] for source in n["sources"]
                    if source.startswith("read-path.")}
        self.assertTrue(narrated)
        self.assertNotIn("read-path.1.s1", narrated)

    def test_full_detail_has_no_length_target(self):
        filler = " ".join(f"Sentence {n} explains another detail of the slot mechanism." for n in range(40))
        sections = ["## Background Part {}\n\n`example_size` matters here. {}".format(n, filler) for n in range(1, 12)]
        page = PAGE.replace("## Known Limitations", "\n\n".join(sections) + "\n\n## Known Limitations")
        result, record, run_dir = self.draft(page, detail="full")
        self.assertEqual(result["status"], "passed")
        self.assertEqual((record["settings"]["detail"], record["settings"]["target_minutes"]), ("full", None))
        self.assertGreater(record["estimate"]["minutes"], 10)
        codes = {issue["code"] for issue in record["issues"]}
        self.assertFalse({"long_script", "short_script"} & codes)
        self.assertEqual(record["scenes"][0]["screen"]["lines"][:2], ["PostgreSQL 18", "Full detail"])
        self.assertIn("recap", [scene["part"] for scene in record["scenes"]])
        for row in record["coverage"]:
            if row["decision"] == "explain":
                self.assertEqual(row["narrated"], row["narratable"], row["section"])

    def test_tables_are_read_as_planned_and_condensed_to_their_first_rows(self):
        # An explained table is read row by row, as many words as the coverage map planned for it.
        _result, record, run_dir = self.draft()
        document = json.loads((run_dir / "document.json").read_text(encoding="utf-8"))
        (table,) = [block for section in document["sections"] if section["id"] == "details"
                    for block in _leaves(section["blocks"]) if block["type"] == "table"]
        read = sum(len(n["text"].split()) for scene in record["scenes"] for n in scene["narration"]
                   if n["origin"] == "table")
        self.assertEqual(read, _table_words(table))

        # A long table that is the whole of a caveat section is condensed to its first rows.
        filler = " ".join(f"Sentence {n} explains another detail of the slot mechanism." for n in range(40))
        sections = ["## Background Part {}\n\n`example_size` matters here. {}".format(n, filler) for n in range(1, 12)]
        issues = "".join(f"| Case {n} | Explains another case of the mechanism |\n" for n in range(1, 41))
        page = PAGE.replace("## Known Limitations", "\n\n".join(sections) + "\n\n## Known Issues\n\n"
                            "| Name | Description |\n|---|---|\n" + issues + "\n## Known Limitations")
        result, record, run_dir = self.draft(page)
        self.assertEqual(result["status"], "passed", [i for i in record["issues"] if i["severity"] == "blocking"])
        document = json.loads((run_dir / "document.json").read_text(encoding="utf-8"))
        keep = {e["section"]: e for e in document["coverage"]["sections"]}["known-issues"]["keep"]
        scenes = [scene for scene in record["scenes"] if scene["title"].startswith("Known Issues")]
        self.assertTrue(scenes)
        self.assertTrue(all(scene["screen"]["layout"] == "table" for scene in scenes))
        shown = [row[0] for scene in scenes for row in scene["screen"]["table"]["rows"]]
        self.assertEqual(shown, [f"Case {n}" for n in range(1, len(keep) + 1)])
        narration = [n for scene in scenes for n in scene["narration"]]
        self.assertEqual([n["sources"] for n in narration if n["origin"] == "table"], [[row] for row in keep])
        self.assertEqual((narration[-1]["text"], narration[-1]["origin"]),
                         ("The table on the page has more rows.", "framing"))
        row = {row["section"]: row for row in record["coverage"]}["known-issues"]
        self.assertEqual((row["narrated"], row["narratable"]), (len(keep), 40))

    def test_review_omissions_and_resume_redraft_the_script(self):
        run_dir = self.checked(BLOCKING)
        self.assertEqual(check_glossary(self.workspace, run_dir)["status"], "needs_review")
        with self.assertRaisesRegex(ValueError, "glossary_check stage has status 'needs_review'"):
            create_script(self.workspace, run_dir)
        record = json.loads((run_dir / "glossary-check.json").read_text(encoding="utf-8"))
        blocking = {issue["ids"][0] for issue in record["issues"] if issue["severity"] == "blocking"}
        (run_dir / RESOLUTIONS).write_text(json.dumps({"resolutions": [
            {"id": identifier, "decision": "omit", "reason": "Left out of the video."} for identifier in blocking]}),
            encoding="utf-8")
        self.enterContext(patch("pgvideo.cli.project_root", return_value=self.workspace))
        self.enterContext(patch("pgvideo.cli._narrate", return_value=0))

        def run(command, *argv):
            args = parser().parse_args([command, "--request", run_dir.name, *argv])
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                status = (resume if command == "resume" else script)(args, self.workspace)
            return status, stdout.getvalue(), stderr.getvalue()

        status, stdout, stderr = run("resume")
        self.assertEqual(status, 0, stderr)
        self.assertIn("Storyboard:", stdout)
        storyboard = json.loads((run_dir / STORYBOARD).read_text(encoding="utf-8"))
        check = json.loads((run_dir / "glossary-check.json").read_text(encoding="utf-8"))
        omitted = {at for omission in check["omissions"] for at in omission["at"]}
        self.assertTrue(omitted)
        used = {source for scene in storyboard["scenes"] for source in scene["sources"]}
        self.assertEqual(used & omitted, set())
        self.assertEqual(len(storyboard["omissions"]), len(check["omissions"]))

        # A scene file that brings an omitted sentence back needs review; resume reads the same file again.
        edited = copy.deepcopy(storyboard)
        sentence = sorted(omitted)[0]
        edited["scenes"][1]["narration"].append({"text": "A sentence.", "sources": [sentence]})
        (run_dir / "edited.json").write_text(json.dumps(edited), encoding="utf-8")
        status, _stdout, stderr = run("script", "--storyboard", f"runs/{run_dir.name}/edited.json")
        self.assertEqual(status, NEEDS_REVIEW)
        self.assertIn(f"scripts/pgvideo script --request {run_dir.name} --storyboard <file>", stderr)
        status, stdout, _stderr = run("resume")
        self.assertEqual(status, NEEDS_REVIEW)
        self.assertIn(f"drafted by file runs/{run_dir.name}/edited.json", stdout)
        self.assertIn("omitted_by_review", (run_dir / SCRIPT).read_text(encoding="utf-8"))
        status, stdout, _stderr = run("script")
        self.assertEqual(status, 0)
        self.assertIn("drafted by builtin", stdout)
        status, _stdout, stderr = run("script", "--storyboard", "missing.json")
        self.assertEqual(status, 1)
        self.assertIn("must be a regular file inside the project", stderr)

        manifest_path = run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["glossary_check"]["status"] = "needs_review"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        status, _stdout, stderr = run("script")
        self.assertEqual(status, 1)
        self.assertIn("has not passed the step before the script", stderr)

    def test_altered_inputs_fail_and_are_recorded(self):
        _result, _record, run_dir = self.draft()
        path = run_dir / "glossary-check.json"
        original = path.read_bytes()
        path.write_text(original.decode().replace("example_size", "example_sizes"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "glossary-check.json does not match"):
            create_script(self.workspace, run_dir)
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((manifest["status"], manifest["script"]["status"]), ("failed", "failed"))
        path.write_bytes(original)
        (self.workspace / "pronunciation" / "en.yaml").unlink()
        with self.assertRaisesRegex(ValueError, "pronunciation/en.yaml is missing"):
            create_script(self.workspace, run_dir)


class TextTests(unittest.TestCase):
    def test_long_sentences_split_only_where_both_sides_stand_alone(self):
        self.assertEqual(short_sentences("`a_b` sets the slot size for readers; it defaults to `1024` bytes in total."),
                         ["`a_b` sets the slot size for readers.", "It defaults to `1024` bytes in total."])
        self.assertEqual(short_sentences("It enforces the byte limit when it writes: it computes the length first."),
                         ["It enforces the byte limit when it writes.", "It computes the length first."])
        # A colon that introduces a list, a short side, and punctuation inside code stay whole.
        self.assertEqual(short_sentences("The view has three columns: pid, query, and state of the slot."),
                         ["The view has three columns: pid, query, and state of the slot."])
        self.assertEqual(short_sentences("It is short; so is this."), ["It is short; so is this."])
        self.assertEqual(short_sentences("It builds `autovacuum: VACUUM; ANALYZE` strings for every worker it runs."),
                         ["It builds `autovacuum: VACUUM; ANALYZE` strings for every worker it runs."])
        self.assertEqual(short_sentences("The values are:"), ["The values are."])

    def test_bullets_keep_whole_clauses_and_never_drop_a_negation(self):
        self.assertEqual(bullet("It defaults to `1024` bytes."), "It defaults to `1024` bytes")
        self.assertEqual(bullet("It defaults to `1024` bytes, has a minimum of `100` and a maximum of `1048576`, and "
                                "is stored in the global `pgstat_track_activity_query_size` variable."),
                         "It defaults to `1024` bytes, has a minimum of `100` and a maximum of `1048576`")
        self.assertEqual(bullet("During shared-memory initialization, PostgreSQL creates the buffer with that total "
                                "size, zeroes it, and assigns each pointer to the next chunk of the buffer."),
                         "During shared-memory initialization, PostgreSQL creates the buffer with that total size")
        # Stopping before "but it does not" would reverse the sentence; a bare list of names would hide the "not".
        self.assertIsNone(bullet("Changing `a_size` can make `pg_stat_activity.query` show more or less text, but it "
                                 "does not change `pg_stat_activity.query_id`, `pg_stat_statements.queryid`, or the "
                                 "hash key."))
        self.assertEqual(bullet("The hooks receive the source text (`p_sourcetext`, `query_string`, or `sourceText`) "
                                "and pass that text to `pgss_store()` for storage in the shared hash table."),
                         "`p_sourcetext` · `query_string` · `sourceText`")

    def test_edges_come_from_named_components_only(self):
        self.assertEqual(edges("`pg_stat_activity` is a SQL view over `pg_stat_get_activity(NULL)`."),
                         [("pg_stat_activity", "pg_stat_get_activity()", "view over")])
        self.assertEqual(edges("`DeadLockReport()` appends each activity by calling `pgstat_get_activity(pid)`."),
                         [("DeadLockReport()", "pgstat_get_activity()", "calls")])
        self.assertEqual(edges("`a_reader()` allocates `a_size * slots` bytes."), [])
        self.assertEqual(edges("It uses `a_reader()` then `b_reader()`."), [])


class SpeechTests(unittest.TestCase):
    def setUp(self):
        self.speech = Pronunciation({"schema": 1, "terms": {"PostgreSQL": "Postgres Q L", "SQL": "S Q L"},
                                     "parts": {"pg": "P G", "pgstat": "P G stat", "cmd": "command", "str": "string",
                                               "num": "num"},
                                     "abbreviations": {"e.g.": "for example"}, "units": {"MB": "megabytes",
                                                                                          "GB": "gigabytes"}},
                                    words=frozenset({"has"}))

    def test_identifiers_code_and_prose_become_speakable(self):
        cases = {
            "`pg_stat_activity.query`": "P G stat activity dot query",
            "`BackendStatusShmemSize()` runs": "Backend Status Shmem Size runs",
            "`track_activity_query_size * (MaxBackends + NUM_AUXILIARY_PROCS)`":
                "track activity query size times, Max Backends plus num auxiliary procs",
            "`Min(strlen(cmd_str), pgstat_size - 1)`": "Min of strlen of command string, P G stat size minus 1",
            "`state = 'active'`": "state equals active",
            "`\"<insufficient privilege>\"`": "insufficient privilege",
            "`BackendStatusArray[i].st_activity_raw`": "Backend Status Array at index i dot S T activity raw",
            "the last byte is `\\0`": "the last byte is backslash zero",
            "`HAS_PGSTAT_PERMISSIONS` and `PGC_SUSET`": "has P G stat permissions and P G C suset",
            "`src/backend/utils/misc/guc_tables.c`": "S R C slash backend slash utils slash misc slash guc tables dot C",
            "`SELECT count(*) FROM pg_stat_activity`": "select count of star from P G stat activity",
            "It can exceed 1GB, e.g. with `128MB` slots.":
                "It can exceed 1 gigabyte, for example with 128 megabytes slots.",
            "PostgreSQL 18 and SQL, parser/planner/executor.": "Postgres Q L 18 and S Q L, parser, planner, executor.",
            "`-1` disables it": "minus 1 disables it",
        }
        for display, spoken in cases.items():
            with self.subTest(display=display):
                self.assertEqual(self.speech.speak(display), spoken)
                self.assertEqual(unspeakable(self.speech.speak(display)), [])
        self.assertEqual(unspeakable("see `a_b` at https://x"), ["_", "`", "https://"])

    def test_dictionary_is_validated(self):
        for data, message in (({"schema": 2}, "schema: 1"), ({"schema": 1, "extra": {}}, "unknown keys"),
                              ({"schema": 1, "terms": {"A": ""}}, "nonempty strings"),
                              ({"schema": 1, "terms": {"A": "a_b"}}, "symbol Kokoro")):
            with self.subTest(message=message):
                with self.assertRaisesRegex(PronunciationError, message):
                    Pronunciation(data)
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / ".runtime" / "tmp") as directory:
            root = Path(directory)
            with self.assertRaisesRegex(PronunciationError, "is missing"):
                Pronunciation.load(root)
            (root / "pronunciation").mkdir()
            (root / "pronunciation" / "en.yaml").write_text("schema: 1\nterms: &t {A: a}\nparts: *t\n",
                                                            encoding="utf-8")
            with self.assertRaisesRegex(PronunciationError, "aliases"):
                Pronunciation.load(root)
        loaded = Pronunciation.load(PROJECT_ROOT)
        self.assertEqual(len(loaded.sha256), 64)
        self.assertEqual(loaded.speak("`pgstat_report_activity()`"), "P G stat report activity")
        self.assertTrue(os.path.samefile(PROJECT_ROOT / loaded.path, PROJECT_ROOT / "pronunciation" / "en.yaml"))


if __name__ == "__main__":
    unittest.main()
