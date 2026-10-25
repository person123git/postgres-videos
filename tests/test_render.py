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
    def test_av1_crf_range_rejects_out_of_range_values_before_rendering(self):
        for crf in (-1, 64):
            with self.subTest(crf=crf), self.assertRaisesRegex(ValueError, "CRF must be 0–63"):
                create_render(ROOT, ROOT / "runs/unused", crf=crf)

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

    def render_diagram(self, diagram):
        from pgvideo.render import _render_slides

        temporary = tempfile.TemporaryDirectory(prefix="pgvideo-render-test-", dir=ROOT / ".runtime/tmp")
        self.addCleanup(temporary.cleanup)
        run = Path(temporary.name)
        screen = {"layout": "diagram", "heading": "Who calls whom", "lines": [], "diagram": diagram}
        storyboard = {"title": "Sample", "document": {"path": "wiki/v18/sample.md", "version": 18}, "scenes": [
            {"id": "flow", "part": "mechanism", "title": "Flow", "screen": screen, "narration": []}]}
        _render_slides(ROOT, run, storyboard, {"scenes": [{"frames": 1}]}, run / "render", 640, 360)
        return (run / "render/slides/001.html").read_text(encoding="utf-8")

    def render_scene(self, screen, narration, timing, captions):
        from pgvideo.render import _render_slides

        temporary = tempfile.TemporaryDirectory(prefix="pgvideo-render-test-", dir=ROOT / ".runtime/tmp")
        self.addCleanup(temporary.cleanup)
        run = Path(temporary.name)
        storyboard = {"title": "Sample", "document": {"path": "wiki/v18/sample.md", "version": 18}, "scenes": [
            {"id": "s", "part": "example", "title": "Sample", "screen": screen, "narration": narration}]}
        timeline = {"sample_rate": 24000, "scenes": [timing], "captions": captions}
        slides = _render_slides(ROOT, run, storyboard, timeline, run / "render", 640, 360)
        return run, slides[0]

    def test_a_sentence_focus_gets_its_own_image_from_the_start_of_its_audio(self):
        screen = {"layout": "table", "heading": "Rows", "lines": [], "table": {
            "header": ["Name"], "rows": [["one"], ["two"], ["three"]]}}
        # The first sentence shows the whole table; the second highlights row 2, and the third keeps it.
        narration = [{"id": "s.n1", "text": "All."}, {"id": "s.n2", "text": "Two.", "focus": [2]},
                     {"id": "s.n3", "text": "Still two."}]
        captions = [{"sentence_id": "s.n1", "start_sample": 24000}, {"sentence_id": "s.n2", "start_sample": 48800},
                    {"sentence_id": "s.n3", "start_sample": 72000}]
        run, slide = self.render_scene(screen, narration, {"start_frame": 30, "end_frame": 120, "frames": 90},
                                       captions)
        self.assertEqual(slide["frames"], 90)
        self.assertEqual([(Path(image["file"]).name, image["frames"], image.get("focus")) for image in slide["images"]],
                         [("001.png", 31, None), ("001-2.png", 59, [2])])
        self.assertEqual(slide["file"], slide["images"][0]["file"])
        plain = (run / "render/slides/001.html").read_text(encoding="utf-8")
        focused = (run / "render/slides/001-2.html").read_text(encoding="utf-8")
        self.assertNotIn(' class="hot"', plain)
        self.assertIn('<tr class="dim"><td>one</td></tr><tr class="hot"><td>two</td></tr>'
                      '<tr class="dim"><td>three</td></tr>', focused)

    def test_code_lines_and_diagram_nodes_take_a_focus_and_an_empty_focus_clears_it(self):
        code = {"layout": "code", "heading": "Query", "lines": [],
                "code": {"language": "sql", "content": "SELECT 1\nFROM t\nWHERE x;\n"}}
        narration = [{"id": "s.n1", "text": "From.", "focus": [2, 3]}, {"id": "s.n2", "text": "All.", "focus": []}]
        captions = [{"sentence_id": "s.n1", "start_sample": 0}, {"sentence_id": "s.n2", "start_sample": 2400}]
        run, slide = self.render_scene(code, narration, {"start_frame": 0, "end_frame": 6, "frames": 6}, captions)
        self.assertEqual([image["frames"] for image in slide["images"]], [3, 3])
        self.assertIn('<code><span class="cl dim">SELECT 1</span><span class="cl hot">FROM t</span>'
                      '<span class="cl hot">WHERE x;</span></code>',
                      (run / "render/slides/001.html").read_text(encoding="utf-8"))
        self.assertIn('<code><span class="cl">SELECT 1</span>',
                      (run / "render/slides/001-2.html").read_text(encoding="utf-8"))
        diagram = {"layout": "diagram", "heading": "Flow", "lines": [], "diagram": {
            "focus": ["a"], "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]}}
        run, slide = self.render_scene(diagram, [{"id": "s.n1", "text": "B.", "focus": ["b"]}],
                                       {"start_frame": 0, "end_frame": 6, "frames": 6}, captions[:1])
        # One focus for the whole scene is one image; the sentence's focus replaces the diagram's.
        self.assertNotIn("images", slide)
        page = (run / "render/slides/001.html").read_text(encoding="utf-8")
        self.assertIn('<div class="node kind-component dim" data-id="a">', page)
        self.assertIn('<div class="node kind-component hot" data-id="b">', page)
        terms = {"layout": "terms", "heading": "Terms", "lines": ["A line"],
                 "terms": [{"term": "one", "definition": "the first"}, {"term": "two", "definition": "the second"}]}
        run, slide = self.render_scene(terms, [{"id": "s.n1", "text": "Two.", "focus": [3]}],
                                       {"start_frame": 0, "end_frame": 6, "frames": 6}, captions[:1])
        # On a terms slide the numbers count the lines, then the terms.
        page = (run / "render/slides/001.html").read_text(encoding="utf-8")
        self.assertIn('<div class="line dim">A line</div>', page)
        self.assertIn('<div class="term dim"><strong>one</strong>', page)
        self.assertIn('<div class="term hot"><strong>two</strong>', page)

    def test_a_diagram_slide_draws_labelled_nodes_and_edges(self):
        page = self.render_diagram({"direction": "down", "focus": ["n1", "n2"], "nodes": [
            {"id": "n1", "label": "`pg_stat_get_activity()`", "detail": "a function"},
            {"id": "n2", "label": "Shared memory", "kind": "data"}, {"id": "n3", "label": "Other"}],
            "edges": [{"from": "n1", "to": "n2", "label": "reads"},
                      {"from": "n2", "to": "n1", "label": "`answers`", "style": "dashed"},
                      {"from": "n3", "to": "n3", "label": "loops"}]})
        # The slide shows labels, not node IDs; focused nodes and the edges between them are highlighted.
        self.assertIn('<div class="node kind-component hot" data-id="n1"><div class="label">'
                      '<code>pg_stat_get_activity()</code></div><div class="detail">a function</div></div>', page)
        self.assertIn('<div class="node kind-data hot" data-id="n2">', page)
        self.assertIn('<div class="node kind-component dim" data-id="n3">', page)
        self.assertIn('<div class="edge-label hot" data-edge="1"><code>answers</code></div>', page)
        self.assertIn('<div class="edge-label dim" data-edge="2">loops</div>', page)

    def test_any_diagram_renders(self):
        # Nothing about a diagram stops the render: its size, repeated IDs, unknown nodes, or no content.
        nodes = [{"id": f"n{i}", "label": f"A long node label number {i}"} for i in range(9)]
        edges = [{"from": f"n{i}", "to": f"n{i + 1}", "label": "then calls the next one"} for i in range(8)]
        for diagram in ({"nodes": nodes, "edges": edges},
                        {"nodes": nodes[:2] + [{"id": "n0", "label": "Again"}],
                         "edges": [{"from": "n0", "to": "absent"}, {"from": "n0", "to": "n1"}], "focus": ["absent"]},
                        {"nodes": [], "edges": []}, {}):
            with self.subTest(diagram=diagram):
                self.render_diagram(diagram)


if __name__ == "__main__":
    unittest.main()
