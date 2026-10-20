import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from pgvideo.timing import create_timing

ROOT = Path(__file__).resolve().parents[1]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class TimingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pgvideo-timing-", dir=ROOT / ".runtime/tmp")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.run = self.root / "runs" / "sample"
        (self.run / "narration/units").mkdir(parents=True)
        self.storyboard = {"scenes": [
            {"id": "s1", "narration": [{"id": "s1.n1", "text": "One `term`, then another."}]},
            {"id": "s2", "narration": [{"id": "s2.n1", "text": "The final scene."}]},
        ]}
        script_bytes = (json.dumps(self.storyboard) + "\n").encode()
        (self.run / "storyboard.json").write_bytes(script_bytes)
        self.audio_map = {"storyboard_sha256": digest(script_bytes), "sample_rate": 24000,
                          "total_samples": 0, "master": {}, "scenes": []}
        clock = 0
        parts = [
            ("s1", [("s1.n1.u1", "One `term`,", 12001, 0),
                    ("s1.n1.u2", "then another.", 8001, 19200)]),
            ("s2", [("s2.n1.u1", "The final scene.", 13003, 0)]),
        ]
        for scene_id, entries in parts:
            start = clock
            units = []
            for unit_id, value, samples, pause in entries:
                path = self.run / "narration/units" / f"{unit_id}.wav"
                sf.write(path, np.zeros(samples, dtype=np.float32), 24000, subtype="PCM_24")
                units.append({"id": unit_id, "sentence_id": unit_id.rsplit(".u", 1)[0],
                              "text": value, "file": path.relative_to(self.run).as_posix(),
                              "sha256": digest(path.read_bytes()), "start_sample": clock,
                              "end_sample": clock + samples, "samples": samples,
                              "pause_after_samples": pause})
                clock += samples + pause
            self.audio_map["scenes"].append({"id": scene_id, "start_sample": start,
                                             "end_sample": clock, "units": units})
        self.audio_map["total_samples"] = clock
        master = self.run / "narration/master.wav"
        sf.write(master, np.zeros(clock, dtype=np.float32), 24000, subtype="PCM_24")
        self.audio_map["master"] = {"sha256": digest(master.read_bytes())}
        self.save_map()
        self.manifest = {"script": {"status": "passed", "sha256": digest(script_bytes)},
                         "narration": {"status": "passed", "sha256": digest(self.map_bytes),
                                       "master_sha256": digest(master.read_bytes())}}
        self.save_manifest()

    def save_map(self):
        self.map_bytes = (json.dumps(self.audio_map) + "\n").encode()
        (self.run / "narration/audio-map.json").write_bytes(self.map_bytes)

    def save_manifest(self):
        (self.run / "manifest.json").write_text(json.dumps(self.manifest))

    def test_frames_pauses_captions_and_final_tail(self):
        result = create_timing(self.root, self.run)
        timeline = json.loads((self.run / "timeline.json").read_text())
        first, last = timeline["scenes"]
        self.assertEqual(first["end_sample"], last["start_sample"])
        self.assertEqual(first["end_frame"], last["start_frame"])
        self.assertEqual(last["end_frame"], result["frames"])
        self.assertEqual(result["frames"], (timeline["audio_samples"] * 30 + 23999) // 24000)
        self.assertGreaterEqual(timeline["tail_padding_seconds"], 0)
        self.assertLess(timeline["tail_padding_seconds"], 1 / 30)
        cues = timeline["captions"]
        self.assertEqual(len(cues), 3)
        self.assertEqual(cues[0]["text"], "One term,")
        self.assertEqual(cues[1]["start_sample"], cues[0]["end_sample"])
        self.assertGreater(cues[2]["start_ms"], cues[1]["end_ms"])
        srt = (self.run / "captions.srt").read_text()
        vtt = (self.run / "captions.vtt").read_text()
        self.assertIn("00:00:00,000 --> 00:00:00,500", srt)
        self.assertIn("00:00:00.000 --> 00:00:00.500", vtt)
        self.assertEqual(self.manifest["narration"]["sha256"],
                         json.loads((self.run / "manifest.json").read_text())["narration"]["sha256"])

    def test_new_timing_drops_the_render_and_validation_built_from_the_old_one(self):
        self.manifest.update(render={"status": "passed"}, validation={"status": "completed"}, status="completed")
        self.save_manifest()
        create_timing(self.root, self.run)
        manifest = json.loads((self.run / "manifest.json").read_text())
        self.assertEqual(manifest["status"], "timing_ready")
        self.assertNotIn("render", manifest)
        self.assertNotIn("validation", manifest)

    def test_rejects_changed_unit_and_script_text(self):
        unit = self.run / self.audio_map["scenes"][0]["units"][0]["file"]
        unit.write_bytes(unit.read_bytes() + b"x")
        with self.assertRaisesRegex(ValueError, "changed after narration"):
            create_timing(self.root, self.run)
        self.assertEqual(json.loads((self.run / "manifest.json").read_text())["timing"]["status"], "failed")

        sf.write(unit, np.zeros(12001, dtype=np.float32), 24000, subtype="PCM_24")
        self.audio_map["scenes"][0]["units"][0]["text"] = "Wrong term,"
        self.save_map()
        self.manifest["narration"]["sha256"] = digest(self.map_bytes)
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "canonical script"):
            create_timing(self.root, self.run)


if __name__ == "__main__":
    unittest.main()
