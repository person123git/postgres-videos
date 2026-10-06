"""The storyboard and plan formats, and what importing a storyboard prepares for narration and rendering.

pgvideo checks that a storyboard matches its schema and can be narrated and rendered.
It does not compare what a storyboard says with any document, and it reads no plan:
the plan schema is only the format a plan is written in.
"""

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from pgvideo import contracts, reuse
from pgvideo.speech import Pronunciation, PronunciationError, unspeakable
from pgvideo.storyboard import import_storyboard, speech_rate
from support import FIGURE, PROJECT_ROOT, install_project_files, plan, storyboard, write


class StoryboardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pgvideo-storyboard-", dir=PROJECT_ROOT / ".runtime" / "tmp")
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name).resolve() / "project"
        self.workspace.mkdir()
        install_project_files(self.workspace)
        self.run_dir = self.workspace / "runs" / "sample"
        write(self.run_dir / "request.json", {"request_id": "sample", "settings": {"voice": "af_heart", "speed": 1.0}})
        write(self.run_dir / "manifest.json", {"request_id": "sample"})

    def imported(self, board: dict) -> tuple[dict, dict]:
        """Import a storyboard; return the manifest's record and storyboard.json."""
        record = import_storyboard(self.workspace, self.run_dir, write(self.workspace / "work/storyboard.json", board))
        return record, json.loads((self.run_dir / "storyboard.json").read_text(encoding="utf-8"))

    def changed(self, change) -> tuple[dict, dict]:
        board = storyboard()
        change(board)
        return self.imported(board)

    @staticmethod
    def codes(record: dict, severity: str) -> set[str]:
        return {issue["code"] for issue in record["issues"] if issue["severity"] == severity}

    @staticmethod
    def scene(board: dict, identifier: str) -> dict:
        return next(scene for scene in board["scenes"] if scene["id"] == identifier)

    def test_a_storyboard_is_prepared_for_narration_and_rendering(self):
        entry, record = self.imported(storyboard())
        self.assertEqual((entry["status"], record["status"], record["issues"]), ("passed", "passed", []))
        self.assertEqual((record["schema"], record["request_id"], record["title"]),
                         (3, "sample", "How example_size is used"))
        self.assertEqual(record["document"], storyboard()["document"])
        self.assertEqual(record["source"]["file"], "work/storyboard.json")
        self.assertEqual(record["pronunciation"]["file"], "pronunciation/en.yaml")
        answer = self.scene(record, "answer")
        self.assertEqual([item["id"] for item in answer["narration"]], ["answer.n1", "answer.n2"])
        first = answer["narration"][0]
        # Display text keeps its code spans; the spoken text comes from the pronunciation dictionary.
        self.assertEqual(first["text"], "`example_size` sets the byte size of each slot behind `pg_stat_activity`.")
        self.assertEqual((first["tts"], first["tts_source"]),
                         ("example size sets the byte size of each slot behind P G stat activity.", "dictionary"))
        self.assertEqual((first["origin"], first["sources"]), ("document", ["Short Answer"]))
        self.assertEqual(answer["sources"], ["Short Answer", "Details"])
        self.assertEqual(answer["citations"], storyboard()["scenes"][2]["citations"])
        for scene in record["scenes"]:
            self.assertTrue(scene["visual"], scene["id"])
            self.assertGreater(scene["estimated_seconds"], 0)
            for item in scene["narration"]:
                self.assertEqual(unspeakable(item["tts"]), [], item["tts"])
        self.assertEqual(self.scene(record, "figure")["screen"]["image"]["path"], FIGURE)
        self.assertEqual(len(self.scene(record, "figure")["screen"]["image"]["sha256"]), 64)
        self.assertEqual((record["counts"]["scenes"], record["counts"]["sentences"]), (10, 11))
        self.assertEqual(set(record["counts"]["layouts"]), {"title", "question", "bullets", "steps", "code", "table",
                                                            "diagram", "terms", "image", "credits"})
        self.assertEqual(record["settings"]["rate_basis"], "default")
        self.assertEqual(record["estimate"]["minutes"], round(record["estimate"]["seconds"] / 60, 1))

        manifest = json.loads((self.run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((manifest["status"], manifest["script"]["status"]), ("script_ready", "passed"))
        self.assertEqual(manifest["script"]["digest"], reuse.script_sha256(record))
        # Importing a storyboard never starts narration.
        self.assertNotIn("narration", manifest)
        rendered = (self.run_dir / "script.md").read_text(encoding="utf-8")
        for expected in ("# Script: How example_size is used", "does not compare it with the document",
                         "<summary>TTS text</summary>", "_(document; from Short Answer)_",
                         "[guc_tables.c:120](https://example.org/postgres/guc_tables.c#L120)", f"Image: `{FIGURE}`"):
            self.assertIn(expected, rendered)

    def test_what_a_storyboard_says_is_not_judged(self):
        # No sources, no origin, any wording, any value, either edge direction, and any section left out.
        def reverse(board):
            edge = self.scene(board, "read-path")["screen"]["diagram"]["edges"][0]
            edge["from"], edge["to"] = edge["to"], edge["from"]

        content = {
            "another value": lambda b: self.scene(b, "answer")["narration"][1].update(text="It defaults to `4096`."),
            "a name the page lacks": lambda b: self.scene(b, "answer")["narration"][0].update(
                text="`example_size` sets the size of `made_up_buffer` slots."),
            "no sources or origin": lambda b: self.scene(b, "answer").update(
                narration=[{"text": "Slots are sized at startup."}], sources=[]),
            "a reversed edge": reverse,
            "a technical framing sentence": lambda b: b["scenes"][0]["narration"].append(
                {"text": "It reserves 64 megabytes in PostgreSQL 17.", "origin": "framing"}),
            "no opening or credits": lambda b: b.update(scenes=b["scenes"][2:4]),
            "no version on screen": lambda b: b["scenes"][0]["screen"].update(lines=[]),
        }
        for name, change in content.items():
            with self.subTest(change=name):
                entry, record = self.changed(change)
                self.assertEqual((entry["status"], self.codes(record, "blocking")), ("passed", set()))

    def test_what_cannot_be_narrated_or_rendered_is_reported(self):
        outside = self.workspace.parent / "outside.png"
        outside.write_bytes(b"png")
        (self.workspace / "notes.txt").write_text("not an image")
        cases = {
            "unspeakable_tts": lambda b: self.scene(b, "answer")["narration"][0].update(
                tts="example_size sets the size.", tts_source="manual"),
            "diagram_edge": lambda b: self.scene(b, "read-path")["screen"]["diagram"]["edges"][0].update(to="absent"),
            "missing_image": lambda b: self.scene(b, "figure")["screen"]["image"].update(
                path="runs/sample/wiki_content/no.png"),
        }
        for path in ("https://example.org/figure.png", str(outside), "../outside.png", "notes.txt"):
            cases[f"missing_image ({path})"] = lambda b, path=path: self.scene(b, "figure")["screen"]["image"].update(
                path=path)
        for name, change in cases.items():
            with self.subTest(case=name):
                entry, record = self.changed(change)
                self.assertEqual((entry["status"], self.codes(record, "blocking")),
                                 ("needs_review", {name.split(" ")[0]}))
        manifest = json.loads((self.run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((manifest["status"], manifest["script"]["status"]), ("needs_review", "needs_review"))
        self.assertIn("**blocking** `missing_image` (figure)", (self.run_dir / "script.md").read_text())

        # A manual TTS text is kept when it is speakable.
        _entry, record = self.changed(lambda b: self.scene(b, "answer")["narration"][0].update(
            tts="example size sets the size of each slot.", tts_source="manual"))
        self.assertEqual(self.scene(record, "answer")["narration"][0]["tts"],
                         "example size sets the size of each slot.")

        # Screens that are hard to read are warnings; the storyboard still passes.
        warnings = {
            "dense_screen": lambda b: self.scene(b, "answer")["screen"].update(lines=[f"Line {n}" for n in range(7)]),
            "long_line": lambda b: self.scene(b, "answer")["screen"].update(lines=["word " * 50]),
            "long_heading": lambda b: self.scene(b, "answer")["screen"].update(heading="heading " * 15),
            "long_code": lambda b: self.scene(b, "query")["screen"]["code"].update(content="SELECT 1;\n" * 20),
            "wide_code": lambda b: self.scene(b, "query")["screen"]["code"].update(content="SELECT " + "x, " * 40),
            "dense_table": lambda b: self.scene(b, "defaults")["screen"]["table"].update(rows=[["a", "b"]] * 8),
        }
        for code, change in warnings.items():
            with self.subTest(warning=code):
                entry, record = self.changed(change)
                self.assertEqual((entry["status"], self.codes(record, "warning")), ("passed", {code}))
        _entry, record = self.changed(lambda b: self.scene(b, "answer")["screen"].pop("lines"))
        self.assertEqual(self.codes(record, "note"), {"empty_screen"})

    def test_the_schema_is_the_storyboard_format(self):
        cases = {
            "'title' is a required property": lambda b: b.pop("title"),
            "'document' is a required property": lambda b: b.pop("document"),
            "'version' is a required property": lambda b: b["document"].pop("version"),
            "'pgvideo/storyboard/v3' was expected": lambda b: b.update(schema="pgvideo/storyboard/v2"),
            "'status' was unexpected": lambda b: b.update(status="passed"),
            # Fields of the removed plan, review, and evidence stages are not part of the format.
            "'plan_digest' was unexpected": lambda b: b.update(plan_digest="0" * 64),
            "'request_id' was unexpected": lambda b: b.update(request_id="sample"),
            "'producer' was unexpected": lambda b: b.update(producer={"harness": {"name": "recorded"}}),
            "'claims' was unexpected": lambda b: b["scenes"][2]["narration"][0].update(claims=["c001"]),
            "'evidence' was unexpected": lambda b: b["scenes"][2]["narration"][0].update(evidence=["guc:x"]),
            # Derived fields are computed, never accepted.
            "'id' was unexpected": lambda b: b["scenes"][2]["narration"][0].update(id="answer.n1"),
            "is not one of": lambda b: b["scenes"][2]["screen"].update(layout="slideshow"),
            "should be non-empty": lambda b: b["scenes"][2].update(narration=[]),
            "'title' is a required property (scene)": lambda b: b["scenes"][2].pop("title"),
            "a code layout needs screen.code": lambda b: b["scenes"][2]["screen"].update(layout="code"),
            "the id answer is used twice": lambda b: b["scenes"][3].update(id="answer"),
            "tts_source manual needs nonempty tts text": lambda b: b["scenes"][2]["narration"][0].update(
                tts_source="manual"),
        }
        for message, change in cases.items():
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message.split(" (")[0]):
                self.changed(change)
        manifest = json.loads((self.run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((manifest["status"], manifest["script"]["status"]), ("failed", "failed"))
        with self.assertRaisesRegex(ValueError, "must be a regular file inside the project"):
            import_storyboard(self.workspace, self.run_dir, Path("work/absent.json"))
        # One mistake in every scene is one schema line.
        board = storyboard()
        for scene in board["scenes"]:
            scene["id"] = scene["id"].upper()
        with self.assertRaisesRegex(ValueError, r"scenes/\*/id \(10 places, first scenes/0/id\)"):
            self.imported(board)

    def test_the_digest_covers_what_is_shown_and_said(self):
        _entry, record = self.imported(storyboard())
        digest = reuse.script_sha256(record)
        other = dict(record, request_id="two", created_at="later", source={"file": "elsewhere.json"},
                     settings={"words_per_minute": 170}, estimate={}, counts={}, issues=[], status="needs_review")
        other["scenes"] = [dict(scene, estimated_seconds=0) for scene in record["scenes"]]
        self.assertEqual(reuse.script_sha256(other), digest)
        for name, change in (("text", lambda r: r["scenes"][0]["narration"][0].update(text="Other.")),
                             ("spoken text", lambda r: r["scenes"][0]["narration"][0].update(tts="Other.")),
                             ("screen", lambda r: r["scenes"][0]["screen"].update(heading="Other")),
                             ("title", lambda r: r.update(title="Other")),
                             ("document", lambda r: r["document"].update(version=17))):
            with self.subTest(change=name):
                changed = copy.deepcopy(record)
                change(changed)
                self.assertNotEqual(reuse.script_sha256(changed), digest)
        # The image's bytes are part of the storyboard record, so a changed figure is a changed video.
        (self.workspace / FIGURE).write_bytes(b"<svg xmlns='http://www.w3.org/2000/svg'/>")
        _entry, again = self.imported(storyboard())
        self.assertNotEqual(reuse.script_sha256(again), digest)

    def test_estimates_use_measured_speech_when_there_is_enough(self):
        self.assertEqual(speech_rate(self.workspace, "af_heart", 1.0), {"words_per_minute": 150.0, "basis": "default"})
        self.assertEqual(speech_rate(self.workspace, "af_heart", 1.2)["words_per_minute"], 180.0)
        units = [{"tts": "one two three four", "samples": 24000}] * 70
        write(self.workspace / "runs/earlier/narration/audio-map.json", {
            "settings": {"voice": "af_heart", "speed": 1.0}, "sample_rate": 24000, "scenes": [{"units": units}]})
        self.assertEqual(speech_rate(self.workspace, "af_heart", 1.0), {"words_per_minute": 240.0, "basis": "measured"})
        self.assertEqual(speech_rate(self.workspace, "af_heart", 0.9)["basis"], "default")


class PlanFormatTests(unittest.TestCase):
    def test_the_plan_schema_describes_a_plan_and_nothing_reads_one(self):
        self.assertEqual(contracts.errors(PROJECT_ROOT, "plan", plan()), [])
        for change, message in ((lambda p: p.pop("main_answer"), "'main_answer' is a required property"),
                                (lambda p: p.update(evidence_digest="0" * 64), "'evidence_digest' was unexpected"),
                                (lambda p: p["claims"][0].update(id="Size.Sets"), "does not match")):
            changed = plan()
            change(changed)
            self.assertIn(message, " ".join(contracts.errors(PROJECT_ROOT, "plan", changed)))
        # An assessment is the author's own note; a claim without one is still a claim.
        bare = plan()
        bare["claims"][0].pop("assessment")
        self.assertEqual(contracts.errors(PROJECT_ROOT, "plan", bare), [])
        package = PROJECT_ROOT / "src" / "pgvideo"
        self.assertEqual([path.name for path in package.glob("*.py") if "plan.schema" in path.read_text()], [])
        self.assertEqual(sorted(path.name for path in (PROJECT_ROOT / "schemas").iterdir()),
                         ["plan.schema.json", "storyboard.schema.json"])


class ReadTests(unittest.TestCase):
    def test_large_files_are_read_completely(self):
        with tempfile.TemporaryDirectory(prefix="pgvideo-reads-", dir=PROJECT_ROOT / ".runtime" / "tmp") as directory:
            workspace = Path(directory)
            data = b'{"schema": 1, "scenes": []}' + b" " * (17 * 1024 * 1024)
            path = workspace / "storyboard.json"
            path.write_bytes(data)
            self.assertEqual(contracts.project_file(workspace, path, label="Storyboard file"), path)
            self.assertEqual(contracts.parse(path.read_bytes(), str(path)), {"schema": 1, "scenes": []})
            (workspace / "pronunciation").mkdir()
            (workspace / "pronunciation" / "en.yaml").write_text(
                "#" + "x" * (257 * 1024) + "\nschema: 1\nterms:\n  PostgreSQL: postgres\n", encoding="utf-8")
            self.assertEqual(Pronunciation.load(workspace).speak("PostgreSQL"), "postgres")
            with self.assertRaisesRegex(ValueError, "must not use YAML aliases"):
                contracts.parse(b"scenes:\n  - &a {id: x}\n  - *a\n", "alias.yaml")


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
