import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

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


def delivery_fixture(run: Path, output: Path) -> None:
    """Write a one-second draft and the passed records that validation checks and delivers."""
    (run / "render").mkdir(parents=True)
    (run / "narration").mkdir()
    ffmpeg = ROOT / ".runtime/bin/ffmpeg"
    draft = run / "render/draft.mp4"
    subprocess.run([str(ffmpeg), "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=blue:s=640x360:r=30:d=1", "-f", "lavfi", "-i",
                    "sine=frequency=440:sample_rate=24000:duration=1", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "libopus", "-b:a", "192k", "-ar", "48000",
                    "-ac", "1", "-frames:v", "30", str(draft)], check=True)
    document = {"path": "wiki/v18/sample.md", "version": 18,
                "url": "https://example.org/wiki/v18/sample.md"}
    script_hash = save(run / "storyboard.json", {"title": "Sample", "document": document,
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
    render_hash = save(run / "render.json", {"sha256": digest(draft), "frames": 30,
        "references_sha256": digest(run / "references.md")})
    save(run / "request.json", {"settings": {"width": 640, "height": 360, "output_dir": str(output)}})
    save(run / "manifest.json", {"render": {"status": "passed", "sha256": render_hash,
        "draft_sha256": digest(draft)}, "timing": {"status": "passed", "sha256": timeline_hash,
        "srt_sha256": digest(run / "captions.srt"), "vtt_sha256": digest(run / "captions.vtt")},
        "narration": {"status": "passed", "sha256": audio_map_hash},
        "script": {"status": "passed", "sha256": script_hash}})


class ValidationTests(unittest.TestCase):
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
            # Records without a tools digest are delivered but not registered for reuse.
            reuse = json.loads((run / "manifest.json").read_text())["reuse"]
            self.assertEqual((reuse["registered"], reuse["reason"]), (False, "the narration, timing, and render "
                             "stages recorded no tools digest; repeat them to register the video"))
            delivery = output / run.name
            self.assertTrue((delivery / "sample.mp4").is_file())
            self.assertEqual(json.loads((delivery / "manifest.json").read_text())["status"], "completed")
            quality = json.loads((delivery / "quality-report.json").read_text())
            self.assertEqual((quality["status"], quality["document"]["path"]),
                             ("completed", "wiki/v18/sample.md"))
            self.assertEqual(sorted(path.name for path in delivery.iterdir()),
                             ["captions.srt", "captions.vtt", "manifest.json", "quality-report.json", "references.md",
                              "sample.mp4", "transcript.md"])

    def test_every_stage_must_pass_before_validation(self):
        with tempfile.TemporaryDirectory(prefix="pgvideo-validate-", dir=ROOT / ".runtime/tmp") as temporary:
            run = Path(temporary) / "run"
            output = Path(temporary) / "output"
            output.mkdir()
            delivery_fixture(run, output)
            manifest = json.loads((run / "manifest.json").read_text())
            manifest["script"]["status"] = "needs_review"
            save(run / "manifest.json", manifest)
            with self.assertRaisesRegex(ValueError, "The script stage must pass before validation"):
                validate_video(ROOT, run)
            self.assertEqual(list(output.iterdir()), [])

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
