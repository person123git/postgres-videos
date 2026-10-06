"""`build` turns a storyboard file into a delivered video, and reuses media only when every input matches.

The end-to-end tests run the real FFmpeg, Chromium, timing, and validation stages on a
small storyboard. A deterministic stand-in replaces Kokoro, whose chunks, pauses, and
timing test_integration.py checks with the real model.
"""

import contextlib
import copy
import inspect
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pgvideo import cli, reuse
from pgvideo import narration as narration_module
from pgvideo import render as render_module
from pgvideo.stages import STAGES, invalidate_after
from support import FIGURE, PROJECT_ROOT, SVG, FakeKokoro, install_project_files, storyboard, write


def components() -> dict:
    """Return the key components of a small video, as they would be computed for a request."""
    board = {"request_id": "one", "created_at": "2026-09-29T00:00:00Z", "title": "One",
             "document": {"path": "wiki/v18/one.md", "version": 18},
             "pronunciation": {"file": "pronunciation/en.yaml", "sha256": "5" * 64},
             "scenes": [{"id": "s01", "narration": [{"id": "s01.n1", "text": "One.", "tts": "One."}]}]}
    return reuse.components(
        board,
        narration={"voice": "af_heart", "language": "a", "speed": 1.0, "loudness_lufs": -16.0,
                   "true_peak_dbtp": -1.5, "model": "6" * 64, "config": "7" * 64, "voice_asset": "8" * 64},
        render={"width": 1920, "height": 1080, "fps": 30, "crf": 20, "audio_bitrate_kbps": 192},
        tools=reuse.tools(PROJECT_ROOT))


class KeyTests(unittest.TestCase):
    def test_every_listed_input_changes_the_key(self):
        base = components()
        key = reuse.video_key(base)
        changes = {
            "storyboard": ("script",), "pronunciation rules": ("pronunciation",), "voice": ("narration", "voice"),
            "speed": ("narration", "speed"), "loudness": ("narration", "loudness_lufs"),
            "model asset": ("narration", "model"), "voice asset": ("narration", "voice_asset"),
            "width": ("render", "width"), "CRF": ("render", "crf"), "audio bitrate": ("render", "audio_bitrate_kbps"),
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
        # Nothing outside the storyboard and the media settings is part of the key.
        self.assertEqual(set(base), {"schema", "script", "pronunciation", "narration", "render", "tools"})

    def test_tools_cover_locks_templates_fonts_and_media_code(self):
        files = reuse.tools(PROJECT_ROOT)["files"]
        self.assertLessEqual({"tools.lock", "requirements.lock", "templates/slide.html", "assets/fonts/Inter.ttf",
                              "assets/fonts/NotoSansMono.ttf", "pgvideo/narration.py", "pgvideo/speech.py",
                              "pgvideo/timing.py", "pgvideo/render.py", "pgvideo/validate.py"}, set(files))
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / ".runtime/tmp") as empty:
            self.assertIsNone(reuse.stage_fingerprint(Path(empty)))

    def test_stage_defaults_are_the_settings_build_looks_up(self):
        """`build` keys its lookup with cli's settings; a stage with another default builds a video it never finds."""
        narration = inspect.signature(narration_module.create_narration).parameters
        render = inspect.signature(render_module.create_render).parameters
        self.assertEqual((narration["loudness"].default, narration["peak"].default), (cli.LUFS, cli.TRUE_PEAK))
        self.assertEqual((render["crf"].default, render["audio_bitrate"].default), (cli.CRF, cli.AUDIO_BITRATE))


class StageTests(unittest.TestCase):
    def test_a_repeated_stage_drops_every_record_built_from_it(self):
        self.assertEqual(STAGES, ("script", "narration", "timing", "render", "validation"))
        completed = {stage: {"status": "passed"} for stage in STAGES} | {"reuse": {"key": "k"}, "request_id": "r"}
        for stage in STAGES:
            with self.subTest(stage=stage):
                manifest = copy.deepcopy(completed)
                invalidate_after(manifest, stage)
                later = STAGES[STAGES.index(stage) + 1:]
                self.assertFalse(set(later) & set(manifest))
                self.assertLessEqual({"request_id", *STAGES[:STAGES.index(stage) + 1]}, set(manifest))
                # The reuse lookup belongs to a storyboard; narration and later stages keep it.
                self.assertEqual("reuse" in manifest, stage != "script")


class CommandTests(unittest.TestCase):
    def test_the_only_commands_narrate_and_render(self):
        self.assertEqual(set(cli.COMMANDS), {"build", "narrate", "timing", "render", "validate"})
        gone = (["prepare", "--document", "wiki/v18/page.md"], ["status", "--request", "r"],
                ["plan", "--request", "r", "--file", "plan.json"], ["script", "--request", "r", "--storyboard", "s"],
                ["review", "--request", "r", "--file", "review.json"], ["review-input", "--request", "r"],
                ["media-review", "--request", "r", "--file", "review.json"], ["preview", "--request", "r"],
                ["resume", "--request", "r"], ["replay", "--request", "r", "--from", "other"],
                ["excerpt", "--request", "r", "--path", "x", "--lines", "1-2"],
                ["omissions-template", "--request", "r"], ["revise", "--from", "a", "--patch", "b", "--out", "c"],
                ["baseline", "--request", "r"], ["note", "--request", "r", "--kind", "visual", "--text", "Seen."],
                ["build", "--request", "r", "--accept-duration"], ["build", "--request", "r", "--target-minutes", "3"])
        for argv in gone:
            with self.subTest(argv=argv[0] + " " + argv[-2]), self.assertRaises(SystemExit), \
                    contextlib.redirect_stderr(io.StringIO()):
                cli.parser().parse_args(argv)
        package = PROJECT_ROOT / "src" / "pgvideo"
        self.assertEqual(sorted(path.name for path in package.glob("*.py")),
                         ["__init__.py", "__main__.py", "assets.py", "cli.py", "contracts.py", "narration.py",
                          "paths.py", "render.py", "reuse.py", "speech.py", "stages.py", "storyboard.py", "timing.py",
                          "validate.py"])


class BuildTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pgvideo-build-", dir=PROJECT_ROOT / ".runtime" / "tmp")
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name).resolve() / "project"
        self.workspace.mkdir()
        install_project_files(self.workspace)
        self.kokoro = FakeKokoro()
        self.enterContext(patch("pgvideo.narration.local_kokoro", return_value=(self.kokoro, "voice.pt")))
        # The fixture project has no Kokoro model files; the stand-in above never reads them.
        self.enterContext(patch("pgvideo.narration._checked_path"))
        self.slides = self.enterContext(patch("pgvideo.render._render_slides", wraps=render_module._render_slides))
        self.source = write(self.workspace / "work/storyboard.json", storyboard())

    def run_command(self, *argv):
        args = cli.parser().parse_args(list(argv))
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = cli.COMMANDS[argv[0]](args, self.workspace)
        return status, stdout.getvalue(), stderr.getvalue()

    def build(self, name, *options, source=None, expect=0):
        """Build a request from a storyboard file; return its run directory and the command's output."""
        status, stdout, stderr = self.run_command("build", "--request", name, "--storyboard",
                                                  str(source or self.source), "--width", "640", "--height", "360",
                                                  *options)
        self.assertEqual(status, expect, stderr)
        return self.workspace / "runs" / name, stdout + stderr

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

    def test_build_delivers_a_video_and_its_files_from_a_storyboard(self):
        status, stdout, stderr = self.run_command("build", "--request", "first", "--storyboard", str(self.source),
                                                  "--width", "640", "--height", "360", "--json")
        self.assertEqual(status, 0, stderr)
        result = json.loads(stdout)
        self.assertEqual((result["request_id"], result["stage"], result["status"], result["issues"]),
                         ("first", "validation", "completed", []))
        self.assertEqual(set(result), {"request_id", "stage", "status", "issues", "message", "delivery",
                                       "duration_seconds"})
        delivery = self.workspace / "output" / "first"
        self.assertEqual((result["delivery"]["directory"], result["delivery"]["video"]),
                         (str(delivery), str(delivery / "example.mp4")))
        self.assertEqual(sorted(path.name for path in delivery.iterdir()),
                         ["captions.srt", "captions.vtt", "example.mp4", "manifest.json", "quality-report.json",
                          "references.md", "transcript.md"])
        self.assertEqual(sorted(Path(file["path"]).name for file in result["delivery"]["files"]),
                         ["captions.srt", "captions.vtt", "example.mp4", "references.md", "transcript.md"])
        # Progress goes to standard error, so standard output is the result alone.
        self.assertIn("Narration master:", stderr)
        run_dir = self.workspace / "runs" / "first"
        request = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
        self.assertEqual(request["settings"], {"voice": "af_heart", "language": "a", "speed": 1.0, "width": 640,
                                               "height": 360, "output_dir": str(self.workspace / "output")})
        manifest = self.manifest(run_dir)
        self.assertEqual((manifest["status"], manifest["reuse"]["registered"]), ("completed", True))
        self.assertEqual([stage for stage in STAGES if manifest[stage]["status"] in ("passed", "completed")],
                         list(STAGES))
        quality = json.loads((delivery / "quality-report.json").read_text(encoding="utf-8"))
        self.assertEqual(quality["status"], "completed")
        self.assertEqual(set(quality["checks"]), {"media", "complete_decode", "captions", "audio_units", "loudness"})
        self.assertEqual(quality["document"]["postgresql_version"], 18)
        # 192 kb/s leaves libopus the most headroom under validation's true-peak limit.
        self.assertEqual(json.loads((run_dir / "render.json").read_text(encoding="utf-8"))["audio_bitrate_kbps"], 192)
        references = (delivery / "references.md").read_text(encoding="utf-8")
        self.assertIn("# References — How example_size is used", references)
        self.assertIn("- [guc_tables.c:120](https://example.org/postgres/guc_tables.c#L120)", references)
        self.assertIn("It defaults to 1024 bytes.", (delivery / "captions.srt").read_text(encoding="utf-8"))
        self.assertEqual((delivery / "transcript.md").read_bytes(), (run_dir / "script.md").read_bytes())
        # Nothing but the request's own records is written: no evidence, plan, review, or orchestration files.
        self.assertEqual(sorted(path.name for path in run_dir.iterdir()),
                         ["captions.srt", "captions.vtt", "manifest.json", "narration", "quality-report.json",
                          "references.md", "render", "render.json", "request.json", "script.md", "storyboard.json",
                          "timeline.json"])
        # Every slide shows its scene, and the figure is the project's file.
        slides = sorted((run_dir / "render/slides").glob("*.html"))
        self.assertEqual(len(slides), len(storyboard()["scenes"]))
        self.assertIn((self.workspace / FIGURE).as_uri(),
                      slides[7].read_text(encoding="utf-8"))

    def test_identical_storyboard_reuses_the_validated_video(self):
        first, output = self.build("first")
        self.assertIn("no validated video has the same inputs", output)
        built = self.manifest(first)
        key = built["reuse"]["key"]
        self.assertEqual(built["reuse"]["lookup"]["status"], "not_found")
        self.assertEqual(self.index(key), ["first"])
        calls, renders = len(self.kokoro.calls), self.slides.call_count
        self.assertGreater(calls, 0)

        second, output = self.build("second", "--output", "elsewhere")
        self.assertIn("Reuse: request first has a validated video with the same inputs", output)
        self.assertIn("reused from request first", output)
        self.assertEqual((len(self.kokoro.calls), self.slides.call_count), (calls, renders))
        reused = self.manifest(second)
        self.assertEqual(reused["status"], "completed")
        self.assertEqual((reused["narration"]["reused_from"], reused["render"]["reused_from"]), ("first", "first"))
        self.assertNotIn("reused_from", reused["timing"])
        self.assertEqual(reused["reuse"]["key"], key)
        self.assertEqual(reused["reuse"]["lookup"], {"status": "found", "request_id": "first", "rejected": []})
        self.assertEqual(self.delivered(second, "elsewhere"), self.delivered(first))
        for name in ("captions.srt", "captions.vtt", "references.md"):
            self.assertEqual((second / name).read_bytes(), (first / name).read_bytes(), name)
        # The copied records now describe the new request; its own timing and validation ran on them.
        audio_map = json.loads((second / "narration/audio-map.json").read_text(encoding="utf-8"))
        self.assertEqual((audio_map["request_id"], audio_map["storyboard_sha256"]),
                         ("second", reused["script"]["sha256"]))
        quality = json.loads((second / "quality-report.json").read_text(encoding="utf-8"))
        self.assertEqual((quality["status"], quality["reused_from"]), ("completed", "first"))
        self.assertEqual(self.index(key), ["first", "second"])
        self.assertEqual(self.runs(), ["first", "second"])

    def test_changed_inputs_and_no_reuse_build_a_new_video(self):
        first, _output = self.build("first")
        key = self.manifest(first)["reuse"]["key"]

        forced, output = self.build("forced", "--no-reuse")
        self.assertIn("--no-reuse was given", output)
        manifest = self.manifest(forced)
        self.assertEqual((manifest["reuse"]["key"], manifest["reuse"]["lookup"]), (key, {"status": "disabled"}))
        self.assertNotIn("reused_from", manifest["narration"])
        self.assertNotIn("reused_from", manifest["render"])

        calls = len(self.kokoro.calls)
        slower, output = self.build("slower", "--speed", "0.9")
        self.assertIn("no validated video has the same inputs", output)
        self.assertGreater(len(self.kokoro.calls), calls, "the speed is part of each unit's cache key")
        changed = self.manifest(slower)["reuse"]
        self.assertNotEqual(changed["key"], key)
        self.assertEqual(changed["components"]["narration"]["speed"], 0.9)

        # One changed sentence is a new video; only that sentence is synthesized again.
        board = storyboard()
        board["scenes"][-1]["narration"][0]["text"] = "The references list the page."
        calls = len(self.kokoro.calls)
        edited, output = self.build("edited", source=write(self.workspace / "work/storyboard.v2.json", board))
        self.assertIn("no validated video has the same inputs", output)
        self.assertEqual(self.kokoro.calls[calls:], ["The references list the page."])
        self.assertNotEqual(self.manifest(edited)["reuse"]["key"], key)
        self.assertEqual(self.index(key), ["first", "forced"])

    def test_a_request_is_rebuilt_in_place_from_its_name(self):
        first, _output = self.build("first")
        calls, renders = len(self.kokoro.calls), self.slides.call_count
        # Without a storyboard file the request's imported storyboard is built again, and its video is reused.
        for argv in (["build", "--request", "first"],
                     ["build", "--request", "first", "--storyboard", str(self.source)]):
            with self.subTest(argv=argv[3:4]):
                status, stdout, stderr = self.run_command(*argv)
                self.assertEqual(status, 0, stderr)
                self.assertIn("Reuse: request first has a validated video with the same inputs", stdout)
                manifest = self.manifest(first)
                self.assertEqual((manifest["status"], manifest["render"]["reused_from"]), ("completed", "first"))
        self.assertEqual((len(self.kokoro.calls), self.slides.call_count), (calls, renders))
        # The settings given once are the request's: the rebuild kept its size.
        self.assertEqual(json.loads((first / "render.json").read_text())["width"], 640)

        # A new revision of the storyboard replaces the request's video; unchanged sentences come from the cache.
        board = storyboard()
        board["scenes"][0]["narration"][0]["text"] = "A new opening sentence."
        status, stdout, stderr = self.run_command("build", "--request", "first", "--storyboard",
                                                  str(write(self.workspace / "work/storyboard.v2.json", board)))
        self.assertEqual(status, 0, stderr)
        self.assertEqual(self.kokoro.calls[calls:], ["A new opening sentence."])
        self.assertNotIn("reused_from", self.manifest(first)["render"])
        self.assertIn("A new opening sentence.", (self.workspace / "output/first/transcript.md").read_text())
        self.assertEqual(self.runs(), ["first"])

        # Explicit stage commands repeat their stage; the unit cache still avoids synthesis.
        calls, renders = len(self.kokoro.calls), self.slides.call_count
        status, _stdout, stderr = self.run_command("narrate", "--request", "first")
        self.assertEqual(status, 0, stderr)
        self.assertEqual((len(self.kokoro.calls), self.slides.call_count), (calls, renders + 1))
        self.assertTrue(self.manifest(first)["reuse"]["registered"])
        for command in ("timing", "render", "validate"):
            with self.subTest(command=command):
                status, _stdout, stderr = self.run_command(command, "--request", "first")
                self.assertEqual(status, 0, stderr)
        status, _stdout, stderr = self.run_command("render", "--request", "absent")
        self.assertEqual(status, 1)
        self.assertIn("No request 'absent'", stderr)

    def test_a_storyboard_that_cannot_be_narrated_stops_before_narration(self):
        board = storyboard()
        spoken = [item for scene in board["scenes"] for item in scene["narration"]]
        for item in spoken:
            item.update(tts="not_speakable", tts_source="manual")
        status, stdout, stderr = self.run_command("build", "--request", "bad", "--storyboard",
                                                  str(write(self.workspace / "work/bad.json", board)), "--json")
        result = json.loads(stdout)
        self.assertEqual((status, result["stage"], result["status"]), (3, "storyboard", "needs_review"))
        self.assertNotIn("delivery", result)
        # One mistake repeated in every sentence is one issue with examples; script.md lists each one.
        (issue,) = result["issues"]
        self.assertEqual((issue["code"], issue["count"], len(issue["examples"])), ("unspeakable_tts", len(spoken), 1))
        self.assertEqual(issue["scenes"], [scene["id"] for scene in board["scenes"]])
        self.assertEqual((self.workspace / "runs/bad/script.md").read_text().count("`unspeakable_tts`"), len(spoken))
        self.assertEqual(self.kokoro.calls, [])
        self.assertFalse((self.workspace / "output/bad").exists())
        self.assertNotIn("narration", self.manifest(self.workspace / "runs/bad"))
        # The same request builds once the storyboard is fixed.
        _run_dir, output = self.build("bad")
        self.assertIn("Video:", output)

    def test_invalid_requests_fail_and_say_why(self):
        outside = self.workspace.parent / "outside"
        outside.mkdir()
        broken = self.workspace / "work/broken.json"
        broken.write_text('{"schema": "pgvideo/storyboard/v3", "scenes": [', encoding="utf-8")
        cases = (
            (["--request", "new"], "has no storyboard yet"),
            (["--request", "../escape", "--storyboard", str(self.source)], "must be one directory name"),
            (["--request", "new", "--storyboard", "work/absent.json"], "must be a regular file inside the project"),
            (["--request", "new", "--storyboard", str(broken)], "is not valid JSON or YAML"),
            (["--request", "new", "--storyboard", str(self.source), "--output", str(outside)],
             "must stay inside the project"),
            (["--request", "new", "--storyboard", str(self.source), "--voice", "bm_george"], "is not provisioned"),
        )
        for argv, message in cases:
            with self.subTest(message=message):
                status, stdout, _stderr = self.run_command("build", *argv, "--json")
                result = json.loads(stdout)
                self.assertEqual((status, result["status"]), (1, "failed"), result)
                self.assertIn(message, result["message"])
                self.assertEqual(result["issues"][0]["severity"], "blocking")
        self.assertEqual(self.kokoro.calls, [])
        self.assertEqual(list(outside.iterdir()), [])
        # Without --request a new request gets a generated name.
        status, stdout, stderr = self.run_command("build", "--storyboard", str(self.source), "--width", "640",
                                                  "--height", "360", "--json")
        self.assertEqual(status, 0, stderr)
        self.assertRegex(json.loads(stdout)["request_id"], r"^\d{8}T\d{6}Z-[0-9a-f]{12}$")

    def test_changed_or_missing_files_are_not_reused(self):
        first, _output = self.build("first")
        key = self.manifest(first)["reuse"]["key"]
        draft = first / "render/draft.mp4"
        draft.write_bytes(draft.read_bytes() + b"\0")
        second, output = self.build("second")
        self.assertIn("Reuse: skipped the video of request first: render/draft.mp4 in request first changed after "
                      "validation", output)
        self.assertIn("no validated video has the same inputs", output)
        self.assertNotIn("reused_from", self.manifest(second)["render"])
        self.assertEqual(self.index(key), ["second"])

        (second / "narration/master-raw.wav").unlink()
        _third, output = self.build("third")
        self.assertIn("narration/master-raw.wav is missing from second", output)
        self.assertEqual(self.index(key), ["third"])

    def test_videos_from_other_tools_are_not_registered(self):
        first, _output = self.build("first")
        key = self.manifest(first)["reuse"]["key"]
        template = self.workspace / "templates/slide.html"
        template.write_text(template.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        status, stdout, stderr = self.run_command("validate", "--request", "first")
        self.assertEqual(status, 0, stderr)
        self.assertIn("Reuse index: not registered (the narration, timing, and render stages ran with other tools "
                      "or code than this validation)", stdout)
        self.assertFalse(self.manifest(first)["reuse"]["registered"])
        second, output = self.build("second")
        self.assertNotEqual(self.manifest(second)["reuse"]["key"], key)
        self.assertIn("no validated video has the same inputs", output)

    def test_tampered_index_entries_and_escaping_caches_are_rejected(self):
        first, _output = self.build("first")
        key = self.manifest(first)["reuse"]["key"]
        entry = json.loads((self.workspace / "cache/videos" / key / "first.json").read_text())
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
        (self.workspace / "cache/videos" / key / "first.json").unlink()
        _second, output = self.build("second")
        for name in cases:
            self.assertIn(f"Reuse: skipped the video of request {name}:", output)
        self.assertEqual(self.index(key), ["second"])
        self.assertEqual(list(outside.iterdir()), [])

        shutil.rmtree(self.workspace / "cache/videos")
        (self.workspace / "cache/videos").symlink_to(outside, target_is_directory=True)
        third, output = self.build("third")
        self.assertIn("the lookup failed: Video cache path", output)
        manifest = self.manifest(third)
        self.assertEqual((manifest["status"], manifest["reuse"]["registered"]), ("completed", False))
        self.assertEqual(list(outside.iterdir()), [])

    def test_a_request_directory_that_holds_the_downloaded_wiki_is_built(self):
        # The harness downloads the wiki into runs/<id>/wiki_content/ before anything else exists there.
        wiki = self.workspace / "runs/first/wiki_content"
        figure = wiki / "v18/questions/images/flow.svg"
        figure.parent.mkdir(parents=True)
        figure.write_bytes(SVG)
        (wiki / "glossary.md").write_text("# Glossary\n", encoding="utf-8")
        board = storyboard()
        next(scene for scene in board["scenes"] if scene["id"] == "figure")["screen"]["image"]["path"] = \
            "runs/first/wiki_content/v18/questions/images/flow.svg"
        run_dir, output = self.build("first", source=write(self.workspace / "work/wiki-storyboard.json", board))
        self.assertIn("Video:", output)
        self.assertTrue((run_dir / "request.json").is_file())
        slides = sorted((run_dir / "render/slides").glob("*.html"))
        self.assertIn(figure.as_uri(), slides[7].read_text(encoding="utf-8"))
        # A rebuild, and a build from a changed storyboard, leave the download as it is.
        board["scenes"][0]["narration"][0]["text"] = "A new opening sentence."
        self.build("first", source=write(self.workspace / "work/wiki-storyboard.json", board))
        self.assertEqual(sorted(path.relative_to(wiki).as_posix() for path in wiki.rglob("*") if path.is_file()),
                         ["glossary.md", "v18/questions/images/flow.svg"])
        self.assertEqual(figure.read_bytes(), SVG)
        self.assertEqual(self.runs(), ["first"])

    def test_a_changed_slide_image_stops_the_render(self):
        first, _output = self.build("first")
        (self.workspace / FIGURE).write_bytes(SVG.replace(b"#5ad", b"#d5a"))
        status, stdout, stderr = self.run_command("build", "--request", "first", "--no-reuse", "--json")
        result = json.loads(stdout)
        self.assertEqual((status, result["stage"], result["status"]), (1, "render", "failed"), stderr)
        self.assertIn("missing or changed after the storyboard was imported", result["message"])
        # Importing the storyboard again records the new image.
        _run_dir, output = self.build("first")
        self.assertIn("Video:", output)


if __name__ == "__main__":
    unittest.main()
