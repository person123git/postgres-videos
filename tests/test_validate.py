import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pgvideo.validate import validate_video
from pgvideo.narration import _units
from pgvideo.speech import Pronunciation


ROOT = Path(__file__).resolve().parents[1]


def save(path, value):
    data = (json.dumps(value) + "\n").encode()
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def delivery_fixture(run: Path, output: Path, detail: str | None = None) -> None:
    """Write a one-second draft and the passed records that Step 11 validates and delivers."""
    (run / "render").mkdir(parents=True)
    (run / "narration").mkdir()
    ffmpeg = ROOT / ".runtime/bin/ffmpeg"
    draft = run / "render/draft.mp4"
    subprocess.run([str(ffmpeg), "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=blue:s=640x360:r=30:d=1", "-f", "lavfi", "-i",
                    "sine=frequency=440:sample_rate=24000:duration=1", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-ac", "1", "-frames:v", "30", str(draft)], check=True)
    document = {"path": "wiki/v18/sample.md", "version": 18,
                "url": "https://github.com/example/wiki/blob/" + "a" * 40 + "/wiki/v18/sample.md"}
    script_hash = save(run / "storyboard.json", {"document": document,
        **({"settings": {"detail": detail}} if detail else {}),
        "scenes": [{"id": "s1", "narration": [{"id": "n1", "text": "Sample."}]}]})
    audio_map_hash = save(run / "narration/audio-map.json", {"sample_rate": 24000,
        "total_samples": 24000, "scenes": [{"id": "s1", "units": [{"id": "n1.u1",
        "sentence_id": "n1", "start_sample": 0, "end_sample": 24000,
        "pause_after_samples": 0}]}]})
    timeline_hash = save(run / "timeline.json", {"total_frames": 30,
        "video_duration_seconds": 1.0, "audio_duration_seconds": 1.0,
        "scenes": [{"id": "s1", "end_sample": 24000}],
        "captions": [{"id": "n1.u1", "sentence_id": "n1", "scene_id": "s1",
        "start_sample": 0, "end_sample": 24000, "start_ms": 0, "end_ms": 1000,
        "text": "Sample."}]})
    (run / "captions.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nSample.\n\n")
    (run / "captions.vtt").write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nSample.\n\n")
    (run / "references.md").write_text("# References\n")
    (run / "script.md").write_text("# Sample\n")
    (run / "glossary-check.md").write_text("# Passed\n")
    render_hash = save(run / "render.json", {"sha256": digest(draft), "frames": 30,
        "references_sha256": digest(run / "references.md")})
    save(run / "request.json", {"settings": {"width": 640, "height": 360,
        "output_dir": str(output)}, "document": document})
    save(run / "manifest.json", {"render": {"status": "passed", "sha256": render_hash,
        "draft_sha256": digest(draft)}, "timing": {"status": "passed", "sha256": timeline_hash,
        "srt_sha256": digest(run / "captions.srt"), "vtt_sha256": digest(run / "captions.vtt")},
        "narration": {"status": "passed", "sha256": audio_map_hash},
        "script": {"status": "passed", "sha256": script_hash},
        "sources": {"status": "passed"}, "glossary_check": {"status": "passed"}})


class ValidationTests(unittest.TestCase):
    def test_harness_validation_prepares_the_package_without_publishing_it(self):
        with tempfile.TemporaryDirectory(prefix="pgvideo-validate-", dir=ROOT / ".runtime/tmp") as temporary:
            run = Path(temporary) / "run"
            output = Path(temporary) / "output"
            output.mkdir()
            delivery_fixture(run, output)
            request = json.loads((run / "request.json").read_text())
            request["workflow"] = {"kind": "harness"}
            save(run / "request.json", request)
            manifest = json.loads((run / "manifest.json").read_text())
            for stage, name in (("plan", "plan.json"), ("content_review", "content-review.json"),
                                ("evidence", "evidence-packet.json")):
                manifest[stage] = {"sha256": save(run / name, {}), "digest": "0" * 64}
            manifest["content_review"].update(policy=2, reviewer={"separation": "fresh_context"},
                                            counts={"verdicts": {}, "minor": 0})
            (run / "content-report.md").write_text("# Recorded content review\n")
            (run / "plan-report.md").write_text("# Recorded plan\n")
            save(run / "orchestration.json", {})
            save(run / "manifest.json", manifest)
            # Content/duration gates are tested in test_harness; this isolates actual FFmpeg validation and publication.
            with patch("pgvideo.validate.require_content_gate"), patch("pgvideo.validate.require_duration"):
                result = validate_video(ROOT, run)
            self.assertEqual(result["status"], "passed")
            self.assertTrue((run / "delivery/sample.mp4").is_file())
            self.assertFalse((output / run.name).exists())
            self.assertEqual(json.loads((run / "manifest.json").read_text())["status"], "media_review_pending")
            self.assertEqual(json.loads((run / "quality-report.json").read_text())["media_review"], "pending")

    def test_audio_unit_split_keeps_punctuation_after_inline_code(self):
        text = ("When a backend initializes its status entry, it clears the activity string and "
                "forces the last byte of the slot to `\\0`, "
                "using `pgstat_track_activity_query_size - 1` as the last valid index.")
        item = {"text": text, "tts": text, "tts_source": "dictionary"}
        units = _units(item, Pronunciation.load(ROOT))
        self.assertEqual(" ".join(part for part, _ in units), text)

    def test_complete_video_is_delivered(self):
        with tempfile.TemporaryDirectory(prefix="pgvideo-validate-", dir=ROOT / ".runtime/tmp") as temporary:
            run = Path(temporary) / "run"
            output = Path(temporary) / "output"
            output.mkdir()
            delivery_fixture(run, output)
            result = validate_video(ROOT, run)
            self.assertEqual(result["status"], "completed")
            # Records from before Step 12 carry no tools digest, so the video is delivered but not registered.
            reuse = json.loads((run / "manifest.json").read_text())["reuse"]
            self.assertEqual((reuse["registered"], reuse["reason"]), (False, "the narration, timing, and render "
                             "stages recorded no tools digest; repeat them to register the video"))
            delivery = output / run.name
            self.assertTrue((delivery / "sample.mp4").is_file())
            self.assertEqual(json.loads((delivery / "manifest.json").read_text())["status"], "completed")
            self.assertEqual(json.loads((delivery / "quality-report.json").read_text())["status"], "completed")

    def test_summary_and_full_detail_videos_name_their_level(self):
        for detail, name in (("standard", "sample.mp4"), ("summary", "sample-summary.mp4"),
                             ("full", "sample-full.mp4")):
            with tempfile.TemporaryDirectory(prefix="pgvideo-validate-", dir=ROOT / ".runtime/tmp") as temporary:
                run = Path(temporary) / "run"
                output = Path(temporary) / "output"
                output.mkdir()
                delivery_fixture(run, output, detail)
                self.assertEqual(validate_video(ROOT, run)["video"], name)
                self.assertEqual(sorted(path.name for path in (output / run.name).glob("*.mp4")), [name])

    def test_delivery_rejects_output_paths_that_leave_the_project(self):
        with tempfile.TemporaryDirectory(prefix="pgvideo-validate-", dir=ROOT / ".runtime/tmp") as temporary:
            base = Path(temporary)
            outside = base / "outside"
            outside.mkdir()
            (base / "project/.runtime/bin").mkdir(parents=True)
            for tool in ("ffmpeg", "ffprobe"):
                (base / "project/.runtime/bin" / tool).symlink_to(ROOT / ".runtime/bin" / tool)
            # The project here is base/project; its request names an output directory in another place.
            for name, output in (("elsewhere", outside), ("linked", base / "project/output")):
                with self.subTest(name=name):
                    run = base / "project/runs" / name
                    if name == "linked":
                        (base / "project/output").symlink_to(outside, target_is_directory=True)
                    delivery_fixture(run, output)
                    with self.assertRaisesRegex(ValueError, "must stay inside the project"):
                        validate_video(base / "project", run)
                    manifest = json.loads((run / "manifest.json").read_text())
                    self.assertEqual((manifest["status"], manifest["validation"]["status"]), ("failed", "failed"))
            self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
