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
            document = {"path": "wiki/v18/sample.md", "version": 18,
                        "url": "https://example.org/wiki/v18/sample.md"}
            scenes = [
                {"id": "first", "part": "opening", "title": "Sample", "screen": {"layout": "title",
                 "heading": "Sample", "lines": ["PostgreSQL 18"]}, "narration": [],
                 "citations": [{"text": "guc_tables.c", "url": "https://example.org/guc_tables.c"}]},
                {"id": "second", "part": "credits", "title": "Credits", "screen": {"layout": "credits",
                 "heading": "Credits", "lines": ["Sources"]}, "narration": [],
                 "citations": [{"url": "https://example.org/guc_tables.c"}, {"url": "https://example.org/other.c"}]},
            ]
            storyboard_hash = save(run / "storyboard.json", {"title": "Sample", "document": document,
                                                             "scenes": scenes})
            timeline_hash = save(run / "timeline.json", {"fps": 30, "total_frames": 6,
                "storyboard_sha256": storyboard_hash, "scenes": [
                    {"id": "first", "frames": 3}, {"id": "second", "frames": 3}]})
            save(run / "request.json", {"settings": {"width": 640, "height": 360}})
            save(run / "manifest.json", {"script": {"status": "passed", "sha256": storyboard_hash},
                "timing": {"status": "passed", "sha256": timeline_hash}})
            result = create_render(ROOT, run)
            self.assertEqual(result["frames"], 6)
            self.assertTrue((run / result["draft"]).is_file())
            # Each link is listed once, under the first scene that cites it.
            self.assertEqual((run / "references.md").read_text(encoding="utf-8"),
                             "# References — Sample\n\nDocument: https://example.org/wiki/v18/sample.md "
                             "(PostgreSQL 18)\n\n## Sample\n\n- [guc_tables.c](https://example.org/guc_tables.c)\n\n"
                             "## Credits\n\n- [https://example.org/other.c](https://example.org/other.c)\n\n")
            # Every slide names the PostgreSQL version and, in its footer, the page.
            page = (run / "render/slides/001.html").read_text(encoding="utf-8")
            self.assertIn("PostgreSQL 18 · opening", page)
            self.assertIn("<footer>wiki/v18/sample.md</footer>", page)
            decoded = subprocess.run([str(ROOT / ".runtime/bin/ffmpeg"), "-v", "error", "-i",
                str(run / result["draft"]), "-map", "0:v", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                capture_output=True, check=True).stdout
            frames = np.frombuffer(decoded, dtype=np.uint8).reshape(6, 360, 640, 3).astype(np.int16)
            changes = [np.abs(frames[i] - frames[i - 1]).mean() for i in range(1, 6)]
            self.assertLess(max(changes[0], changes[1], changes[3], changes[4]), 1, changes)
            self.assertGreater(changes[2], 1, changes)

    def test_a_diagram_slide_names_edge_ends_by_their_labels(self):
        from pgvideo.render import _render_slides

        with tempfile.TemporaryDirectory(prefix="pgvideo-render-test-", dir=ROOT / ".runtime/tmp") as temporary:
            run = Path(temporary)
            document = {"path": "wiki/v18/sample.md", "version": 18}
            screen = {"layout": "diagram", "heading": "Who calls whom", "lines": [], "diagram": {
                "nodes": [{"id": "n1", "label": "`pg_stat_get_activity()`"}, {"id": "n2", "label": "Shared memory"}],
                "edges": [{"from": "n1", "to": "n2", "label": "reads"}]}}
            storyboard = {"title": "Sample", "document": document, "scenes": [
                {"id": "flow", "part": "mechanism", "title": "Flow", "screen": screen, "narration": []}]}
            _render_slides(ROOT, run, storyboard, {"scenes": [{"frames": 1}]}, run / "render", 640, 360)
            page = (run / "render/slides/001.html").read_text(encoding="utf-8")
            # An edge reads as label, verb, label; the slide shows the labels, not node IDs.
            self.assertIn("<code>pg_stat_get_activity()</code> → Shared memory: reads", page)
            self.assertNotIn("n1 → n2", page)
            self.assertIn('<span class="node"><code>pg_stat_get_activity()</code></span>', page)


if __name__ == "__main__":
    unittest.main()
