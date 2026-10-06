"""Read a storyboard file and prepare it for narration and rendering.

A storyboard is the whole input of a video: what each screen shows and what is
said over it (schemas/storyboard.schema.json). Whoever makes the video writes it;
pgvideo does not compare it with any document and does not judge what it says.

Importing a storyboard checks its structure, gives every sentence an ID, derives
the text Kokoro speaks from the display text with pronunciation/en.yaml (unless a
sentence supplies its own), and estimates the length. The only issues reported
are the ones narration and rendering depend on: text Kokoro cannot say, a diagram
edge without its nodes, an image that is not in the project, and screens too
dense to read. runs/<id>/storyboard.json holds the result and script.md renders
it for reading; script.md is delivered as the transcript.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from . import contracts
from .paths import project_directory, write_atomic
from .reuse import script_sha256
from .speech import Pronunciation, PronunciationError, unspeakable
from .stages import invalidate_after

SCHEMA_VERSION = 3
STORYBOARD = "storyboard.json"
SCRIPT = "script.md"
SEVERITIES = ("blocking", "warning", "note")
LAYOUTS = ("title", "question", "bullets", "steps", "code", "table", "diagram", "terms", "image", "credits")
# What a layout shows besides its heading and lines.
LAYOUT_CONTENT = {"code": "code", "table": "table", "diagram": "diagram", "terms": "terms", "image": "image"}
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")

# Screen sizes that stay readable; larger screens are reported, not refused.
MAX_SCREEN_LINES = 5
MAX_LINE_CHARS = 180
MAX_HEADING_CHARS = 80
MAX_CODE_LINES = 16
MAX_CODE_WIDTH = 90
MAX_TABLE_ROWS = 6
MAX_TABLE_COLUMNS = 5
# Used only to estimate length; narration inserts and measures the real pauses.
WORDS_PER_MINUTE = 150
SENTENCE_PAUSE = 0.35
SCENE_PAUSE = 0.8
# Measured speech needs at least this much audio before it replaces the default rate.
MIN_MEASURED_SECONDS = 60
MAX_MEASURED_RUNS = 30


def _plain(text: str) -> str:
    return (text or "").replace("`", "")


def spoken_words(tts: str) -> float:
    """Estimate spoken length in words: a spelled letter, as in "P G stat", takes about half a word."""
    return sum(0.5 if len(word.strip(",.;:!?")) == 1 and word[0].isupper() else 1 for word in tts.split())


def speech_rate(root: Path, voice: str, speed: float) -> dict:
    """Words per minute of Kokoro speech for this voice and speed, measured from earlier narration when possible.

    Words are counted as an estimate counts them, from the TTS text, so the rate
    predicts what an estimate in the same words will measure. Pauses are excluded.
    """
    words = seconds = 0.0
    runs = 0
    maps = sorted((root / "runs").glob("*/narration/audio-map.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in maps[:MAX_MEASURED_RUNS * 3]:
        try:
            audio = json.loads(path.read_text(encoding="utf-8"))
            settings, rate = audio["settings"], audio["sample_rate"]
            if settings.get("voice") != voice or float(settings.get("speed", 1.0)) != float(speed):
                continue
            for scene in audio["scenes"]:
                for unit in scene["units"]:
                    words += spoken_words(unit["tts"])
                    seconds += unit["samples"] / rate
        except (OSError, ValueError, KeyError, TypeError):
            continue
        runs += 1
        if runs >= MAX_MEASURED_RUNS:
            break
    if seconds >= MIN_MEASURED_SECONDS and words:
        return {"words_per_minute": round(words / seconds * 60, 1), "basis": "measured"}
    return {"words_per_minute": WORDS_PER_MINUTE * float(speed), "basis": "default"}


def import_storyboard(root: Path, run_dir: Path, path: Path) -> dict:
    """Write storyboard.json and script.md for a request; return the manifest's record.

    The record's status is 'passed', or 'needs_review' when narration or rendering
    cannot handle something in the file. A missing or malformed file marks the
    stage 'failed' and raises ValueError.
    """
    try:
        return _import(root, run_dir, path)
    except (ValueError, OSError) as error:
        _update_manifest(root, run_dir, status="failed", error=str(error))
        raise


def _import(root: Path, run_dir: Path, path: Path) -> dict:
    file = contracts.project_file(root, path, label="Storyboard file")
    data = file.read_bytes()
    where = file.relative_to(root).as_posix()
    raw = contracts.parse(data, where)
    contracts.require(root, "storyboard", raw, where)
    try:
        pronunciation = Pronunciation.load(root)
    except PronunciationError as error:
        raise ValueError(str(error)) from error
    settings = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))["settings"]
    rate = speech_rate(root, settings["voice"], settings["speed"])
    record = _Storyboard(root, pronunciation, rate["words_per_minute"]).build(raw)
    record = {"schema": SCHEMA_VERSION, "request_id": run_dir.name,
              "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
              "source": {"file": where, "sha256": hashlib.sha256(data).hexdigest()},
              "pronunciation": {"file": pronunciation.path, "sha256": pronunciation.sha256,
                                "language": pronunciation.language},
              "settings": {"words_per_minute": rate["words_per_minute"], "rate_basis": rate["basis"],
                           "sentence_pause_seconds": SENTENCE_PAUSE, "scene_pause_seconds": SCENE_PAUSE},
              **record}
    body = (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    relative = run_dir.relative_to(root)
    write_atomic(root, relative / STORYBOARD, body, label="Request")
    rendered = _render(record).encode("utf-8")
    write_atomic(root, relative / SCRIPT, rendered, label="Request")
    return _update_manifest(root, run_dir, status=record["status"], record=record,
                            sha=hashlib.sha256(body).hexdigest(), script=hashlib.sha256(rendered).hexdigest())


class _Storyboard:
    """Normalize the scenes, derive TTS text, and report what narration and rendering cannot handle."""

    def __init__(self, root: Path, pronunciation: Pronunciation, words_per_minute: float):
        self.root, self.speech, self.rate = root, pronunciation, words_per_minute
        self.issues: list[dict] = []

    def issue(self, severity: str, code: str, message: str, *, scene: str | None = None,
              narration: str | None = None, action: str | None = None) -> None:
        self.issues.append({"severity": severity, "code": code, "message": message, "scene": scene,
                            "narration": narration, "action": action})

    def build(self, raw: dict) -> dict:
        seen: set[str] = set()
        scenes = []
        for number, scene in enumerate(raw["scenes"], 1):
            if scene["id"] in seen:
                raise ValueError(f"Scene {number}: the id {scene['id']} is used twice.")
            seen.add(scene["id"])
            scenes.append(self._scene(number, scene))
        sentences = [item for scene in scenes for item in scene["narration"]]
        total = sum(scene["estimated_seconds"] for scene in scenes)
        return {
            "status": "needs_review" if any(i["severity"] == "blocking" for i in self.issues) else "passed",
            "title": raw["title"].strip(),
            "document": {"path": raw["document"]["path"], "version": raw["document"]["version"],
                         "url": raw["document"].get("url")},
            "estimate": {"words": round(sum(item["words"] for item in sentences)), "seconds": round(total, 1),
                         "minutes": round(total / 60, 1)},
            "scenes": scenes,
            "counts": {"scenes": len(scenes), "sentences": len(sentences),
                       "layouts": {layout: sum(s["screen"]["layout"] == layout for s in scenes) for layout in LAYOUTS
                                   if any(s["screen"]["layout"] == layout for s in scenes)}},
            "issues": self.issues,
        }

    def _scene(self, number: int, scene: dict) -> dict:
        identifier = scene["id"]
        screen = self._screen(f"Scene {number} ({identifier})", identifier, scene["screen"])
        items = [self._narration(identifier, f"{identifier}.n{k}", item)
                 for k, item in enumerate(scene["narration"], 1)]
        sources = list(scene.get("sources", []))
        for item in items:
            sources += [source for source in item["sources"] if source not in sources]
        words = round(sum(item["words"] for item in items), 1)
        seconds = words / self.rate * 60 + SENTENCE_PAUSE * (len(items) - 1) + SCENE_PAUSE
        return {"id": identifier, "part": scene["part"], "title": scene["title"].strip(), "screen": screen,
                "visual": (scene.get("visual") or "").strip() or _visual(screen), "narration": items,
                "sources": sources, "citations": [dict(citation) for citation in scene.get("citations", [])],
                "words": words, "estimated_seconds": round(seconds, 1)}

    def _narration(self, scene: str, identifier: str, item: dict) -> dict:
        text = " ".join(item["text"].split())
        manual = item.get("tts_source") == "manual"
        if manual and not (item.get("tts") or "").strip():
            raise ValueError(f"Sentence {identifier}: tts_source manual needs nonempty tts text.")
        tts = " ".join(item["tts"].split()) if manual else self.speech.speak(text)
        if bad := unspeakable(tts):
            self.issue("blocking", "unspeakable_tts", f"The TTS text contains {', '.join(bad)}, which Kokoro would "
                                                      "read aloud or drop.", scene=scene, narration=identifier,
                       action="Add a pronunciation to pronunciation/en.yaml or write tts with tts_source: manual.")
        return {"id": identifier, "text": text, "tts": tts, "tts_source": "manual" if manual else "dictionary",
                **({"origin": item["origin"]} if item.get("origin") else {}),
                "sources": list(item.get("sources", [])), "words": round(spoken_words(tts), 1)}

    def _screen(self, where: str, scene: str, screen: dict) -> dict:
        layout = screen["layout"]
        needed = LAYOUT_CONTENT.get(layout)
        if needed and not screen.get(needed):
            raise ValueError(f"{where}: a {layout} layout needs screen.{needed}.")
        result = {"layout": layout, "heading": screen.get("heading") or "", "lines": list(screen.get("lines", []))}
        for key in ("footer", "code", "table", "diagram", "terms"):
            if screen.get(key):
                result[key] = screen[key]
        issue = {"scene": scene}
        if len(_plain(result["heading"])) > MAX_HEADING_CHARS * (2 if layout == "title" else 1):
            self.issue("warning", "long_heading", f"The screen heading is longer than {MAX_HEADING_CHARS} "
                                                  "characters.", **issue)
        if len(result["lines"]) > MAX_SCREEN_LINES:
            self.issue("warning", "dense_screen", f"The screen has {len(result['lines'])} lines; split the scene "
                                                  f"to keep {MAX_SCREEN_LINES} or fewer.", **issue)
        for line in result["lines"]:
            if len(_plain(line)) > MAX_LINE_CHARS and layout not in ("question", "credits"):
                self.issue("warning", "long_line", f"A screen line is longer than {MAX_LINE_CHARS} characters: "
                                                   f"{_plain(line)[:60]}…", **issue)
        if code := result.get("code"):
            shown = code["content"].rstrip("\n").split("\n")
            if len(shown) > MAX_CODE_LINES:
                self.issue("warning", "long_code", f"The code excerpt has {len(shown)} lines; at most "
                                                   f"{MAX_CODE_LINES} stay readable.", **issue)
            if any(len(line.expandtabs(4)) > MAX_CODE_WIDTH for line in shown):
                self.issue("warning", "wide_code", f"A code line is wider than {MAX_CODE_WIDTH} characters and may "
                                                   "be cropped or wrapped.", **issue)
        if table := result.get("table"):
            if len(table["rows"]) > MAX_TABLE_ROWS:
                self.issue("warning", "dense_table", f"The table shows {len(table['rows'])} rows; split it to keep "
                                                     f"{MAX_TABLE_ROWS} or fewer.", **issue)
            if len(table["header"]) > MAX_TABLE_COLUMNS:
                self.issue("warning", "dense_table", f"The table has {len(table['header'])} columns; more than "
                                                     f"{MAX_TABLE_COLUMNS} may be unreadable.", **issue)
        if diagram := result.get("diagram"):
            ids = {node["id"] for node in diagram["nodes"]}
            for edge in diagram["edges"]:
                if edge["from"] not in ids or edge["to"] not in ids:
                    self.issue("blocking", "diagram_edge", f"A diagram edge joins unknown nodes {edge['from']} and "
                                                           f"{edge['to']}.", **issue)
        if image := screen.get("image"):
            result["image"] = {"path": image["path"], "alt": image.get("alt") or "",
                               "sha256": self._image(image["path"], issue)}
        if layout in ("bullets", "steps", "question") and not result["lines"]:
            self.issue("note", "empty_screen", "The screen has no text lines.", **issue)
        return result

    def _image(self, path: str, issue: dict) -> str | None:
        """Return the SHA-256 of a slide image, which must be a file inside the project."""
        try:
            if path.startswith(("http:", "https:", "/")):
                raise ValueError("it is not a path inside the project")
            file = project_directory(self.root, Path(path).parent, label="Image") / Path(path).name
            if file.is_symlink() or not file.is_file() or file.suffix.lower() not in IMAGE_SUFFIXES:
                raise ValueError(f"it is not a {', '.join(IMAGE_SUFFIXES)} file in the project")
        except ValueError as error:
            self.issue("blocking", "missing_image", f"The slide image {path} cannot be shown: {error}.", **issue,
                       action="Give the image's path from the project root, such as "
                              "runs/<id>/wiki_content/v18/images/figure.png.")
            return None
        return hashlib.sha256(file.read_bytes()).hexdigest()


def _visual(screen: dict) -> str:
    layout = screen["layout"]
    heading = _plain(screen.get("heading") or "")
    if layout == "title":
        return f"Title slide: “{heading}”" + (f", with {', '.join(_plain(l) for l in screen['lines'])}."
                                               if screen["lines"] else ".")
    if layout == "question":
        return f"The question under the heading “{heading}”."
    if layout == "terms":
        return "Term cards for " + ", ".join(t["term"] for t in screen["terms"]) + ", each with its definition."
    if layout == "code":
        count = screen["code"]["content"].rstrip("\n").count("\n") + 1
        return f"{(screen['code'].get('language') or 'Code').upper()} excerpt of {count} line(s) under “{heading}”."
    if layout == "table":
        table = screen["table"]
        return f"Table with {len(table['rows'])} row(s): {', '.join(_plain(h) for h in table['header'])}."
    if layout == "diagram":
        diagram = screen["diagram"]
        labels = {node["id"]: _plain(node["label"]) for node in diagram["nodes"]}
        return "Diagram: " + "; ".join(f"{labels.get(e['from'], e['from'])} {e['label']} "
                                       f"{labels.get(e['to'], e['to'])}" for e in diagram["edges"]) + "."
    if layout == "image":
        return f"The figure {screen['image']['path']} under “{heading}”."
    if layout == "credits":
        return "Closing slide with the sources."
    kind = "Numbered steps" if layout == "steps" else "Bullet points"
    return f"{kind} under “{heading}”: {len(screen['lines'])} short line(s)."


# Manifest and report ----------------------------------------------------------------------------


def _update_manifest(root: Path, run_dir: Path, *, status: str, record: dict | None = None, sha: str | None = None,
                     script: str | None = None, error: str | None = None) -> dict:
    path = run_dir / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    manifest["status"] = {"passed": "script_ready"}.get(status, status)
    invalidate_after(manifest, "script")
    entry: dict = {"status": status}
    if error:
        entry["error"] = error
    if record:
        entry.update({
            "record": STORYBOARD, "sha256": sha, "script": SCRIPT, "script_sha256": script,
            "created_at": record["created_at"], "schema": record["schema"], "source": record["source"],
            "pronunciation": record["pronunciation"], "estimate": record["estimate"], "counts": record["counts"],
            "digest": script_sha256(record),
            "issues": {severity: sum(issue["severity"] == severity for issue in record["issues"])
                       for severity in SEVERITIES},
        })
    manifest["script"] = entry
    write_atomic(root, run_dir.relative_to(root) / "manifest.json",
                 (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"), label="Request")
    return entry


def _cell(text) -> str:
    return " ".join(str(text if text is not None else "—").split()).replace("|", "\\|")


def _render(record: dict) -> str:
    document, estimate, counts = record["document"], record["estimate"], record["counts"]
    lines = [
        f"# Script: {record['title']}",
        "",
        f"- Document: " + (f"[{document['path']}]({document['url']})" if document.get("url") else
                           f"`{document['path']}`") + f", PostgreSQL {document['version']}",
        f"- Storyboard: `{record['source']['file']}` (`{record['source']['sha256'][:12]}`)",
        f"- Pronunciation: `{record['pronunciation']['file']}` (`{(record['pronunciation']['sha256'] or '')[:12]}`)",
        f"- {counts['scenes']} scenes, {counts['sentences']} narrated sentences, {estimate['words']} spoken words, "
        f"about {estimate['minutes']} minutes",
        "",
        "Display text is what the screen and captions show. TTS text is what Kokoro reads. pgvideo narrates and "
        "renders the storyboard as written; it does not compare it with the document.",
        "",
    ]
    if record["issues"]:
        lines += ["## Issues", ""]
        for severity in SEVERITIES:
            for issue in (i for i in record["issues"] if i["severity"] == severity):
                where = " · ".join(filter(None, [issue.get("scene"), issue.get("narration")]))
                lines.append(f"- **{severity}** `{issue['code']}`" + (f" ({where})" if where else "")
                             + f": {issue['message']}" + (f" {issue['action']}" if issue.get("action") else ""))
        lines.append("")
    lines += ["## Scenes", ""]
    for number, scene in enumerate(record["scenes"], 1):
        screen = scene["screen"]
        lines += [f"### {number}. {scene['title']}", "",
                  f"`{scene['id']}` · {scene['part']} · {screen['layout']} · about "
                  f"{scene['estimated_seconds']} s", ""]
        if scene["sources"]:
            lines += ["Sources: " + ", ".join(f"`{s}`" for s in scene["sources"]), ""]
        if scene["citations"]:
            lines += ["Citations: " + ", ".join(f"[{c.get('text') or c['url']}]({c['url']})"
                                                for c in scene["citations"]), ""]
        lines += [f"**Visual:** {scene['visual']}", "", f"**Screen:** {screen['heading']}", ""]
        for line in screen["lines"]:
            lines.append(f"- {line}")
        if code := screen.get("code"):
            fence = "````" if "```" in code["content"] else "```"
            lines += ["", fence + (code.get("language") or ""), code["content"], fence]
        if table := screen.get("table"):
            lines += ["", "| " + " | ".join(_cell(h) for h in table["header"]) + " |",
                      "|" + "---|" * len(table["header"])]
            lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in table["rows"]]
        if diagram := screen.get("diagram"):
            labels = {node["id"]: node["label"] for node in diagram["nodes"]}
            lines += [f"- {labels.get(e['from'], e['from'])} → {e['label']} → {labels.get(e['to'], e['to'])}"
                      for e in diagram["edges"]]
        for term in screen.get("terms", []):
            lines.append(f"- **{term['term']}**: {term['definition']}")
        if image := screen.get("image"):
            lines.append(f"- Image: `{image['path']}`")
        if screen.get("footer"):
            lines += ["", f"_{screen['footer']}_"]
        lines += ["", "**Narration:**", ""]
        for item in scene["narration"]:
            note = "; ".join(filter(None, [item.get("origin"),
                                           "from " + ", ".join(item["sources"]) if item["sources"] else None]))
            lines.append(f"1. {item['text']}" + (f" _({note})_" if note else ""))
        lines += ["", "<details><summary>TTS text</summary>", ""]
        lines += [f"1. {item['tts']}" for item in scene["narration"]]
        lines += ["", "</details>", ""]
    return "\n".join(lines).rstrip() + "\n"
