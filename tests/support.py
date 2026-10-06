"""Shared fixtures: a project with the files the media stages read, a stand-in for Kokoro, and a storyboard."""

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# The committed files that importing, narrating, and rendering a storyboard read.
PROJECT_FILES = ("pronunciation/en.yaml", "schemas/storyboard.schema.json", "schemas/plan.schema.json", "tools.lock",
                 "requirements.lock", "templates/slide.html", "assets/fonts/Inter.ttf",
                 "assets/fonts/NotoSansMono.ttf")
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="36"><rect width="64" height="36" fill="#5ad"/></svg>'
PAGE = "wiki/v18/questions/example.md"
FIGURE = "work/figures/flow.svg"


def install_project_files(workspace: Path) -> None:
    """Give a fixture project the dictionary, schemas, locks, template, fonts, tools, and one figure."""
    for name in PROJECT_FILES:
        target = workspace / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT_ROOT / name, target)
    (workspace / ".runtime/bin").mkdir(parents=True)
    (workspace / ".runtime/tmp").mkdir()
    for tool in ("ffmpeg", "ffprobe"):
        (workspace / ".runtime/bin" / tool).symlink_to(PROJECT_ROOT / ".runtime/bin" / tool)
    (workspace / FIGURE).parent.mkdir(parents=True)
    (workspace / FIGURE).write_bytes(SVG)


def write(path: Path, value) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")
    return path


class FakeKokoro:
    """Yield one deterministic tone per call; longer text gives longer audio."""

    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, text, voice, speed):
        self.calls.append(text)
        samples = int((4800 + 900 * len(text.split())) / speed)
        tone = 0.2 * np.sin(2 * np.pi * 220 * np.arange(samples) / 24000)
        yield SimpleNamespace(audio=tone.astype(np.float32))


def storyboard() -> dict:
    """A storyboard that uses every layout."""
    return {
        "schema": "pgvideo/storyboard/v3",
        "title": "How example_size is used",
        "document": {"path": PAGE, "version": 18, "url": "https://example.org/wiki/v18/questions/example.md"},
        "scenes": [
            {"id": "opening", "part": "opening", "title": "How example_size is used",
             "screen": {"layout": "title", "heading": "How `example_size` is used", "lines": ["PostgreSQL 18"]},
             "narration": [{"text": "How `example_size` is used.", "origin": "framing"}]},
            {"id": "question", "part": "question", "title": "The question",
             "screen": {"layout": "question", "heading": "The question",
                        "lines": ["In PostgreSQL 18, how is `example_size` used?"]},
             "narration": [{"text": "In PostgreSQL 18, how is `example_size` used?", "origin": "document",
                            "sources": ["Question"]}]},
            {"id": "answer", "part": "answer", "title": "Short answer",
             "screen": {"layout": "bullets", "heading": "Short answer",
                        "lines": ["`example_size` sets the slot size", "It defaults to `1024` bytes"]},
             "narration": [{"text": "`example_size` sets the byte size of each slot behind `pg_stat_activity`.",
                            "origin": "document", "sources": ["Short Answer"]},
                           {"text": "It defaults to `1024` bytes.", "origin": "paraphrase",
                            "sources": ["Short Answer", "Details"]}],
             "sources": ["Short Answer"],
             "citations": [{"text": "guc_tables.c:120", "url": "https://example.org/postgres/guc_tables.c#L120"}]},
            {"id": "read-path", "part": "mechanism", "title": "Read path",
             "screen": {"layout": "diagram", "heading": "Read path", "diagram": {
                 "nodes": [{"id": "view", "label": "`pg_stat_activity`"},
                           {"id": "function", "label": "`pg_stat_get_activity()`"}],
                 "edges": [{"from": "view", "to": "function", "label": "view over"}]}},
             "narration": [{"text": "`pg_stat_activity` is a view over `pg_stat_get_activity()`."}]},
            {"id": "steps", "part": "mechanism", "title": "Write path",
             "screen": {"layout": "steps", "heading": "Write path",
                        "lines": ["The backend writes its slot first", "A reader copies the slot afterward"]},
             "narration": [{"text": "The backend writes its slot first, and a reader copies it afterward."}]},
            {"id": "defaults", "part": "example", "title": "Defaults",
             "screen": {"layout": "table", "heading": "Defaults", "table": {
                 "header": ["Setting", "Default"], "rows": [["`example_size`", "`1024`"]]}},
             "narration": [{"text": "The table lists the default.", "origin": "table"}]},
            {"id": "query", "part": "example", "title": "Query",
             "screen": {"layout": "code", "heading": "Query",
                        "code": {"language": "sql", "content": "SELECT query\nFROM pg_stat_activity;"}},
             "narration": [{"text": "The query below reads the slots."}]},
            {"id": "figure", "part": "supporting", "title": "Flow",
             "screen": {"layout": "image", "heading": "Flow", "image": {"path": FIGURE, "alt": "The flow"}},
             "narration": [{"text": "The page shows the flow in a figure."}]},
            {"id": "terms", "part": "terminology", "title": "Terms",
             "screen": {"layout": "terms", "heading": "Terms", "terms": [
                 {"term": "backend", "definition": "The server process that serves one client connection."}]},
             "narration": [{"text": "A backend is the server process that serves one client connection.",
                            "origin": "glossary"}]},
            {"id": "credits", "part": "credits", "title": "Sources",
             "screen": {"layout": "credits", "heading": "Sources", "lines": [f"Wiki page: {PAGE}"]},
             "narration": [{"text": "The references list the page and its citations.", "origin": "framing"}]},
        ]}


def plan() -> dict:
    """A plan in the documented format; no command reads a plan."""
    return {
        "schema": "pgvideo/plan/v2",
        "document": {"path": PAGE, "version": 18},
        "audience": "PostgreSQL users and administrators who know SQL", "detail": "summary", "target_minutes": 3,
        "main_answer": {"text": "`example_size` sets the size of each slot.", "claims": ["size-sets-slot"]},
        "learning_objectives": ["Say what `example_size` controls."],
        "claims": [{"id": "size-sets-slot", "text": "`example_size` sets the byte size of each slot.",
                    "kind": "answer", "sources": ["Short Answer"],
                    "assessment": {"source_support": "supported", "evidence": ["guc_tables.c#L120-L160"],
                                   "justification": "The cited lines define the setting.",
                                   "glossary": "not_applicable"}}],
        "outline": [{"id": "answer", "part": "answer", "title": "Short answer", "purpose": "State the answer.",
                     "claims": ["size-sets-slot"], "budget_seconds": 20}],
        "required_caveats": [],
        "omissions": [{"section": "Tests And Documentation", "reason": "Beyond a summary."}],
        "feasibility": {"status": "feasible"},
    }
