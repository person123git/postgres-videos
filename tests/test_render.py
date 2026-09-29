import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from pgvideo.render import create_render


ROOT = Path(__file__).resolve().parents[1]


def save(path, value):
    data = (json.dumps(value) + "\n").encode()
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


class RenderTests(unittest.TestCase):
    def test_two_scenes_have_exact_frame_count_and_audio(self):
        with tempfile.TemporaryDirectory(prefix="pgvideo-render-test-", dir=ROOT / ".runtime/tmp") as temporary:
            run = Path(temporary)
            (run / "narration").mkdir()
            sf.write(run / "narration/master.wav", np.zeros(4800, dtype=np.float32), 24000)
            document = {"title": "Sample", "path": "wiki/v18/sample.md", "version": 18,
                        "wiki_commit": "a" * 40, "pinned_commit": "b" * 40,
                        "url": "https://github.com/example/wiki/blob/" + "a" * 40 + "/wiki/v18/sample.md"}
            scenes = [
                {"id": "first", "part": "opening", "title": "Sample", "screen": {"layout": "title",
                 "heading": "Sample", "lines": ["PostgreSQL 18"]}, "narration": [{"citations": []}]},
                {"id": "second", "part": "credits", "title": "Credits", "screen": {"layout": "credits",
                 "heading": "Credits", "lines": ["Source snapshot"]}, "narration": [{"citations": []}]},
            ]
            storyboard_hash = save(run / "storyboard.json", {"document": document, "scenes": scenes})
            timeline_hash = save(run / "timeline.json", {"fps": 30, "total_frames": 6,
                "storyboard_sha256": storyboard_hash, "scenes": [
                    {"id": "first", "frames": 3}, {"id": "second", "frames": 3}]})
            save(run / "request.json", {"settings": {"width": 640, "height": 360}})
            save(run / "manifest.json", {"script": {"status": "passed", "sha256": storyboard_hash},
                "timing": {"status": "passed", "sha256": timeline_hash}})
            result = create_render(ROOT, run)
            self.assertEqual(result["frames"], 6)
            self.assertTrue((run / result["draft"]).is_file())
            self.assertTrue((run / "references.md").is_file())
            decoded = subprocess.run([str(ROOT / ".runtime/bin/ffmpeg"), "-v", "error", "-i",
                str(run / result["draft"]), "-map", "0:v", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                capture_output=True, check=True).stdout
            frames = np.frombuffer(decoded, dtype=np.uint8).reshape(6, 360, 640, 3).astype(np.int16)
            changes = [np.abs(frames[i] - frames[i - 1]).mean() for i in range(1, 6)]
            self.assertLess(max(changes[0], changes[1], changes[3], changes[4]), 1, changes)
            self.assertGreater(changes[2], 1, changes)


if __name__ == "__main__":
    unittest.main()
