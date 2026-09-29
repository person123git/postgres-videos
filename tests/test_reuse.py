"""Step 12: completed videos are keyed by their inputs and reused only when every input matches.

The end-to-end tests run the real FFmpeg, Chromium, timing, and validation stages on a
small request. A deterministic stand-in replaces Kokoro, whose chunks, pauses, and
timing test_integration.py checks with the real model.
"""

import contextlib
import copy
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from pgvideo import cli, reuse
from pgvideo import render as render_module
from pgvideo.stages import STAGES, invalidate_after
from test_sources import DOCUMENT, GLOSSARY_TEXT, PIN, POSTGRES, PROJECT_ROOT, WIKI, WIKI_COMMIT, FakeGitHub, \
    install_project_files, postgres_files, wiki_files

MEDIA_FILES = ("tools.lock", "requirements.lock", "templates/slide.html", "assets/fonts/Inter.ttf",
               "assets/fonts/NotoSansMono.ttf")
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="36"><rect width="64" height="36" fill="#5ad"/></svg>'
# The same document, with Backend absent from PostgreSQL 18 in a later glossary snapshot.
ABSENT_GLOSSARY = GLOSSARY_TEXT.replace(
    "**Aliases:** backend process. **Checked on:** PostgreSQL 18.",
    "**Aliases:** backend process. **Checked on:** PostgreSQL 17, 18.",
).replace(
    "A backend is the server process that serves one client connection.\n",
    "A backend is the server process that serves one client connection.\n\n**Version notes:**\n"
    "- PostgreSQL 18: Not present in PostgreSQL 18.\n",
)
COMMANDS = {"generate": cli.generate, "resume": cli.resume, "script": cli.script, "narrate": cli.narrate,
            "timing": cli.timing, "render": cli.render, "validate": cli.validate}


def install_media_files(workspace: Path) -> None:
    """Give a fixture project the locks, template, fonts, and tools that narration and rendering read."""
    install_project_files(workspace)
    for name in MEDIA_FILES:
        target = workspace / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT_ROOT / name, target)
    (workspace / ".runtime/bin").mkdir(parents=True)
    (workspace / ".runtime/tmp").mkdir()
    for tool in ("ffmpeg", "ffprobe"):
        (workspace / ".runtime/bin" / tool).symlink_to(PROJECT_ROOT / ".runtime/bin" / tool)


class FakeKokoro:
    """Yield one deterministic tone per call; longer text gives longer audio."""

    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, text, voice, speed):
        self.calls.append(text)
        samples = int((4800 + 900 * len(text.split())) / speed)
        tone = 0.2 * np.sin(2 * np.pi * 220 * np.arange(samples) / 24000)
        yield SimpleNamespace(audio=tone.astype(np.float32))


def components() -> dict:
    """Return the key components of a small video, as they would be computed for a request."""
    manifest = {"sources": {
        "wiki": {"commit": WIKI_COMMIT},
        "postgres": {"version": 18, "commit": PIN},
        "inputs": [
            {"role": "document", "repository": WIKI, "commit": WIKI_COMMIT, "path": DOCUMENT, "sha256": "1" * 64},
            {"role": "glossary", "repository": WIKI, "commit": WIKI_COMMIT, "path": "wiki/glossary.md",
             "sha256": "2" * 64},
            {"role": "evidence", "repository": POSTGRES, "commit": PIN, "path": "src/status.c", "sha256": "3" * 64},
        ]}}
    storyboard = {"request_id": "one", "created_at": "2026-09-29T00:00:00Z", "drafter": {"kind": "builtin"},
                  "inputs": {"document": "4" * 64}, "document": {"path": DOCUMENT, "wiki_commit": WIKI_COMMIT},
                  "pronunciation": {"file": "pronunciation/en.yaml", "sha256": "5" * 64},
                  "scenes": [{"id": "s01", "narration": [{"id": "s01.n1", "text": "One.", "tts": "One."}]}]}
    return reuse.components(
        manifest, storyboard,
        narration={"voice": "af_heart", "language": "a", "speed": 1.0, "loudness_lufs": -16.0,
                   "true_peak_dbtp": -1.5, "model": "6" * 64, "config": "7" * 64, "voice_asset": "8" * 64},
        render={"width": 1920, "height": 1080, "fps": 30, "crf": 20, "audio_bitrate_kbps": 128},
        tools=reuse.tools(PROJECT_ROOT))


class KeyTests(unittest.TestCase):
    def test_script_hash_ignores_only_request_specific_fields(self):
        storyboard = {"request_id": "one", "created_at": "t1", "drafter": {"kind": "builtin"},
                      "inputs": {"document": "a"}, "document": {"url": "u"}, "scenes": [{"id": "s01"}]}
        other = dict(storyboard, request_id="two", created_at="t2", drafter={"kind": "file"}, inputs={})
        self.assertEqual(reuse.script_sha256(storyboard), reuse.script_sha256(other))
        for change in ({"scenes": [{"id": "s02"}]}, {"document": {"url": "v"}}):
            with self.subTest(change=change):
                self.assertNotEqual(reuse.script_sha256(storyboard), reuse.script_sha256(storyboard | change))

    def test_every_listed_input_changes_the_key(self):
        base = components()
        key = reuse.video_key(base)
        changes = {
            "document hash": ("document", "sha256"), "glossary hash": ("glossary", "sha256"),
            "wiki commit": ("sources", "wiki_commit"), "PostgreSQL pin": ("sources", "postgres", "commit"),
            "script": ("script",), "pronunciation rules": ("pronunciation",), "voice": ("narration", "voice"),
            "speed": ("narration", "speed"), "loudness": ("narration", "loudness_lufs"),
            "model asset": ("narration", "model"), "voice asset": ("narration", "voice_asset"),
            "width": ("render", "width"), "CRF": ("render", "crf"),
            "template": ("tools", "files", "templates/slide.html"), "tool lock": ("tools", "files", "tools.lock"),
            "media code": ("tools", "files", "pgvideo/render.py"),
        }
        for name, path in changes.items():
            with self.subTest(name):
                changed = copy.deepcopy(base)
                parent = changed
                for part in path[:-1]:
                    parent = parent[part]
                parent[path[-1]] = f"changed {parent[path[-1]]}"
                self.assertNotEqual(reuse.video_key(changed), key)
        changed = copy.deepcopy(base)
        changed["sources"]["inputs"][2]["sha256"] = "9" * 64
        self.assertNotEqual(reuse.video_key(changed), key, "a cited PostgreSQL file changed")

    def test_tools_cover_locks_templates_fonts_and_media_code(self):
        files = reuse.tools(PROJECT_ROOT)["files"]
        self.assertLessEqual({"tools.lock", "requirements.lock", "templates/slide.html", "assets/fonts/Inter.ttf",
                              "assets/fonts/NotoSansMono.ttf", "pgvideo/narration.py", "pgvideo/speech.py",
                              "pgvideo/timing.py", "pgvideo/render.py", "pgvideo/validate.py"}, set(files))
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / ".runtime/tmp") as empty:
            self.assertIsNone(reuse.stage_fingerprint(Path(empty)))


class StageTests(unittest.TestCase):
    def test_a_repeated_stage_drops_every_record_built_from_it(self):
        completed = {stage: {"status": "passed"} for stage in STAGES} | {"reuse": {"key": "k"}, "environment": {}}
        for stage in STAGES:
            with self.subTest(stage=stage):
                manifest = copy.deepcopy(completed)
                invalidate_after(manifest, stage)
                later = STAGES[STAGES.index(stage) + 1:]
                self.assertFalse(set(later) & set(manifest))
                self.assertLessEqual({"environment", *STAGES[:STAGES.index(stage) + 1]}, set(manifest))
                # The reuse lookup belongs to a storyboard; timing and later stages keep it.
                self.assertEqual("reuse" in manifest, STAGES.index(stage) > STAGES.index("script"))


class ReuseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pgvideo-reuse-", dir=PROJECT_ROOT / ".runtime" / "tmp")
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name).resolve() / "project"
        self.workspace.mkdir()
        install_media_files(self.workspace)
        self.github = FakeGitHub()
        self.github.add(WIKI, WIKI_COMMIT, self.wiki(), refs=["master"])
        self.github.add(POSTGRES, PIN, postgres_files())
        self.kokoro = FakeKokoro()
        self.enterContext(patch("pgvideo.sources._http_get", side_effect=self.github))
        self.enterContext(patch("pgvideo.sources._github_contents",
                                side_effect=lambda path, ref: {"type": "file", "path": path}))
        self.enterContext(patch("pgvideo.cli.project_root", return_value=self.workspace))
        self.enterContext(patch("pgvideo.narration.local_kokoro", return_value=(self.kokoro, "voice.pt")))
        # The fixture project has no Kokoro model files; the stand-in above never reads them.
        self.enterContext(patch("pgvideo.narration._checked_path"))
        self.slides = self.enterContext(patch("pgvideo.render._render_slides", wraps=render_module._render_slides))

    @staticmethod
    def wiki(**changes):
        files = wiki_files(**changes)
        files["wiki/v18/questions/observability/images/flow.svg"] = SVG
        return files

    def run_command(self, *argv):
        args = cli.parser().parse_args(list(argv))
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = COMMANDS[argv[0]](args, self.workspace)
        return status, stdout.getvalue(), stderr.getvalue()

    def generate(self, *options, expect=0):
        status, stdout, stderr = self.run_command("generate", "--document", DOCUMENT, "--width", "640",
                                                  "--height", "360", *options)
        self.assertEqual(status, expect, stderr)
        line = next(line for line in stdout.splitlines() if line.startswith("Validated request: "))
        return Path(line.removeprefix("Validated request: ")).parent, stdout

    @staticmethod
    def manifest(run_dir):
        return json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    def delivered(self, run_dir, output="output"):
        return (self.workspace / output / run_dir.name / "example.mp4").read_bytes()

    def runs(self):
        return sorted(path.name for path in (self.workspace / "runs").iterdir())

    def index(self, key):
        directory = self.workspace / "cache/videos" / key
        return sorted(path.stem for path in directory.glob("*.json")) if directory.is_dir() else []

    def test_identical_request_reuses_the_validated_video(self):
        first, stdout = self.generate()
        self.assertIn("no validated video has the same inputs", stdout)
        built = self.manifest(first)
        key = built["reuse"]["key"]
        self.assertEqual((built["status"], built["reuse"]["registered"]), ("completed", True))
        self.assertEqual(built["reuse"]["lookup"]["status"], "not_found")
        self.assertEqual(self.index(key), [first.name])
        calls, renders = len(self.kokoro.calls), self.slides.call_count
        self.assertGreater(calls, 0)

        second, stdout = self.generate("--output", "elsewhere")
        self.assertIn(f"Reuse: request {first.name} has a validated video with the same inputs", stdout)
        self.assertIn(f"reused from request {first.name}", stdout)
        self.assertEqual((len(self.kokoro.calls), self.slides.call_count), (calls, renders))
        reused = self.manifest(second)
        self.assertEqual(reused["status"], "completed")
        self.assertEqual((reused["narration"]["reused_from"], reused["render"]["reused_from"]),
                         (first.name, first.name))
        self.assertNotIn("reused_from", reused["timing"])
        self.assertEqual(reused["reuse"]["key"], key)
        self.assertEqual(reused["reuse"]["lookup"], {"status": "found", "request_id": first.name, "rejected": []})
        self.assertEqual(self.delivered(second, "elsewhere"), self.delivered(first))
        for name in ("captions.srt", "captions.vtt", "references.md"):
            self.assertEqual((second / name).read_bytes(), (first / name).read_bytes(), name)
        # The copied records now describe the new request; its own timing and validation ran on them.
        audio_map = json.loads((second / "narration/audio-map.json").read_text(encoding="utf-8"))
        self.assertEqual((audio_map["request_id"], audio_map["storyboard_sha256"]),
                         (second.name, reused["script"]["sha256"]))
        quality = json.loads((second / "quality-report.json").read_text(encoding="utf-8"))
        self.assertEqual((quality["status"], quality["reused_from"]), ("completed", first.name))
        self.assertEqual(self.index(key), sorted([first.name, second.name]))
        self.assertEqual(self.runs(), sorted([first.name, second.name]))

    def test_changed_inputs_and_no_reuse_build_a_new_video(self):
        first, _stdout = self.generate()
        key = self.manifest(first)["reuse"]["key"]

        forced, stdout = self.generate("--no-reuse")
        self.assertIn("--no-reuse was given", stdout)
        manifest = self.manifest(forced)
        self.assertEqual((manifest["reuse"]["key"], manifest["reuse"]["lookup"]), (key, {"status": "disabled"}))
        self.assertNotIn("reused_from", manifest["narration"])
        self.assertNotIn("reused_from", manifest["render"])

        calls = len(self.kokoro.calls)
        slower, stdout = self.generate("--speed", "0.9")
        self.assertIn("no validated video has the same inputs", stdout)
        self.assertGreater(len(self.kokoro.calls), calls, "the speed is part of each unit's cache key")
        changed = self.manifest(slower)["reuse"]
        self.assertNotEqual(changed["key"], key)
        self.assertEqual(changed["components"]["narration"]["speed"], 0.9)
        self.assertEqual(self.index(key), sorted([first.name, forced.name]))

    def test_each_level_of_detail_builds_and_delivers_its_own_video(self):
        standard, _stdout = self.generate()
        key = self.manifest(standard)["reuse"]["key"]

        summary, stdout = self.generate("--detail", "summary")
        self.assertIn("(summary detail: ", stdout)
        self.assertIn("no validated video has the same inputs", stdout)
        built = self.manifest(summary)
        self.assertEqual((built["status"], built["script"]["detail"]), ("completed", "summary"))
        self.assertNotEqual(built["reuse"]["key"], key)
        delivery = self.workspace / "output" / summary.name
        self.assertEqual(sorted(path.name for path in delivery.glob("*.mp4")), ["example-summary.mp4"])
        self.assertLess(built["validation"]["duration_seconds"],
                        self.manifest(standard)["validation"]["duration_seconds"])

        again, stdout = self.generate("--detail", "summary")
        self.assertIn(f"Reuse: request {summary.name} has a validated video with the same inputs", stdout)
        self.assertEqual((self.workspace / "output" / again.name / "example-summary.mp4").read_bytes(),
                         (delivery / "example-summary.mp4").read_bytes())

    def test_new_glossary_snapshot_is_checked_again_for_an_unchanged_document(self):
        first, _stdout = self.generate()
        before = self.manifest(first)
        # A later commit changes only the glossary: the document bytes stay the same.
        self.github.add(WIKI, "c" * 40, self.wiki(glossary=GLOSSARY_TEXT.replace(
            "A backend is the server process", "A backend is the server-side process")), refs=["master"])
        second, stdout = self.generate()
        after = self.manifest(second)
        self.assertEqual(after["reuse"]["components"]["document"], before["reuse"]["components"]["document"])
        self.assertNotEqual(after["reuse"]["components"]["glossary"], before["reuse"]["components"]["glossary"])
        self.assertNotEqual(after["reuse"]["key"], before["reuse"]["key"])
        self.assertIn("no validated video has the same inputs", stdout)
        self.assertEqual(after["glossary"]["glossary"]["sha256"], after["reuse"]["components"]["glossary"]["sha256"])

        # A snapshot whose glossary contradicts the unchanged document stops at the cross-check.
        self.github.add(WIKI, "d" * 40, self.wiki(glossary=ABSENT_GLOSSARY), refs=["master"])
        third, stdout = self.generate(expect=cli.NEEDS_REVIEW)
        manifest = self.manifest(third)
        self.assertEqual(manifest["glossary_check"]["status"], "needs_review")
        self.assertNotIn("reuse", manifest)
        self.assertNotIn("narration", manifest)

    def test_changed_or_missing_files_are_not_reused(self):
        first, _stdout = self.generate()
        key = self.manifest(first)["reuse"]["key"]
        draft = first / "render/draft.mp4"
        draft.write_bytes(draft.read_bytes() + b"\0")
        second, stdout = self.generate()
        self.assertIn(f"Reuse: skipped the video of request {first.name}: render/draft.mp4 in request "
                      f"{first.name} changed after validation", stdout)
        self.assertIn("no validated video has the same inputs", stdout)
        self.assertNotIn("reused_from", self.manifest(second)["render"])
        self.assertEqual(self.index(key), [second.name])

        (second / "narration/master-raw.wav").unlink()
        third, stdout = self.generate()
        self.assertIn(f"narration/master-raw.wav is missing from {second.name}", stdout)
        self.assertEqual(self.index(key), [third.name])

    def test_retries_reuse_their_own_video_and_create_no_requests(self):
        first, _stdout = self.generate()
        calls, renders = len(self.kokoro.calls), self.slides.call_count
        for command in ("script", "resume"):
            with self.subTest(command=command):
                status, stdout, stderr = self.run_command(command, "--request", first.name)
                self.assertEqual(status, 0, stderr)
                self.assertIn(f"Reuse: request {first.name} has a validated video with the same inputs", stdout)
                manifest = self.manifest(first)
                self.assertEqual((manifest["status"], manifest["render"]["reused_from"]), ("completed", first.name))
        self.assertEqual((len(self.kokoro.calls), self.slides.call_count), (calls, renders))
        # Explicit stage commands repeat their stage; the unit cache still avoids synthesis.
        status, stdout, stderr = self.run_command("narrate", "--request", first.name)
        self.assertEqual(status, 0, stderr)
        self.assertEqual((len(self.kokoro.calls), self.slides.call_count), (calls, renders + 1))
        manifest = self.manifest(first)
        self.assertNotIn("reused_from", manifest["narration"])
        self.assertTrue(manifest["reuse"]["registered"])
        for command in ("timing", "render", "validate"):
            with self.subTest(command=command):
                status, _stdout, stderr = self.run_command(command, "--request", first.name)
                self.assertEqual(status, 0, stderr)
        self.assertEqual(self.runs(), [first.name])
        self.assertEqual(self.index(self.manifest(first)["reuse"]["key"]), [first.name])

    def test_videos_from_other_tools_are_not_registered(self):
        first, _stdout = self.generate()
        key = self.manifest(first)["reuse"]["key"]
        template = self.workspace / "templates/slide.html"
        template.write_text(template.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        status, stdout, stderr = self.run_command("validate", "--request", first.name)
        self.assertEqual(status, 0, stderr)
        self.assertIn("Reuse index: not registered (the narration, timing, and render stages ran with other tools "
                      "or code than this validation)", stdout)
        self.assertFalse(self.manifest(first)["reuse"]["registered"])
        second, stdout = self.generate()
        self.assertNotEqual(self.manifest(second)["reuse"]["key"], key)
        self.assertIn("no validated video has the same inputs", stdout)

    def test_tampered_index_entries_and_escaping_caches_are_rejected(self):
        first, _stdout = self.generate()
        key = self.manifest(first)["reuse"]["key"]
        entry = json.loads((self.workspace / "cache/videos" / key / f"{first.name}.json").read_text())
        outside = self.workspace.parent / "outside"
        outside.mkdir()
        cases = {
            "escape": dict(entry, request_id="escape"),
            "traversal": dict(entry, files={**entry["files"], "narration/../../../outside/x.wav": "0" * 64}),
            "absolute": dict(entry, files={**entry["files"], str(outside / "x.wav"): "0" * 64}),
            "rekeyed": dict(entry, components={**entry["components"], "script": "0" * 64}),
        }
        for name, bad in cases.items():
            (self.workspace / "cache/videos" / key / f"{name}.json").write_text(json.dumps(bad))
        (self.workspace / "cache/videos" / key / f"{first.name}.json").unlink()
        second, stdout = self.generate()
        for name in cases:
            self.assertIn(f"Reuse: skipped the video of request {name}:", stdout)
        self.assertEqual(self.index(key), [second.name])
        self.assertEqual(list(outside.iterdir()), [])

        shutil.rmtree(self.workspace / "cache/videos")
        (self.workspace / "cache/videos").symlink_to(outside, target_is_directory=True)
        third, stdout = self.generate()
        self.assertIn("the lookup failed: Video cache path", stdout)
        manifest = self.manifest(third)
        self.assertEqual((manifest["status"], manifest["reuse"]["registered"]), ("completed", False))
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
