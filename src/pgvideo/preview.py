"""Render every scene's slide and contact sheets for review, without narration (harness requests).

A reviewer otherwise reads the screens as JSON. `create_preview` renders the
accepted storyboard's slides exactly as `render` does (same template, fonts, and
size) into runs/<id>/preview/slides/ and lays them out nine to a page as contact
sheets in runs/<id>/preview/sheets/, each slide labeled with its number and scene
ID. Once the request has a rendered video of the same storyboard, the sheets are
built from the rendered slides instead, so a finished-video review looks at the
frames that are in the MP4.

A preview needs an accepted storyboard, not the content gate: nothing in it is
delivered, and preview.json records which storyboard it shows.
"""

from __future__ import annotations

import hashlib
import html
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .crosscheck import _recorded
from .paths import project_directory
from .sources import write_atomic

RECORD = "preview/preview.json"
PER_SHEET, COLUMNS = 9, 3
SHEET_WIDTH = 1920
SHEET = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><style>
@font-face {{ font-family: Inter; src: url('{font}'); font-weight: 100 900; }}
html, body {{ margin: 0; background: #0b1420; color: #e8eef5; font-family: Inter, sans-serif; }}
.sheet {{ display: grid; grid-template-columns: repeat({columns}, 1fr); gap: 14px; padding: 18px;
          width: {width}px; box-sizing: border-box; }}
figure {{ margin: 0; min-width: 0; }}
img {{ width: 100%; display: block; border: 1px solid #36506a; }}
figcaption {{ font-size: 20px; padding: 6px 2px 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
figcaption b {{ color: #76cbe9; }}
</style></head><body><div class="sheet">
{figures}
</div></body></html>
"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current(run_dir: Path, manifest: dict) -> dict | None:
    """Where the preview of the current storyboard is; None when there is none or it shows another storyboard."""
    path = run_dir / RECORD
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if record.get("storyboard_sha256") != (manifest.get("script") or {}).get("sha256"):
        return None
    return {"source": record["source"], "record": str(path), "slides": len(record["slides"]),
            "slides_directory": str((run_dir / record["slides"][0]["file"]).parent),
            "sheets": [str(run_dir / sheet["file"]) for sheet in record["sheets"]]}


def rendered_sheets(run_dir: Path, manifest: dict) -> list[str] | None:
    """The contact sheets of the slides in the current rendered video, when a preview was made from them."""
    path, render = run_dir / RECORD, run_dir / "render.json"
    if not (path.is_file() and render.is_file()):
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        slides = json.loads(render.read_text(encoding="utf-8"))["slides"]
    except (OSError, ValueError, KeyError):
        return None
    if (record.get("source") != "render" or record.get("video_sha256") != (manifest.get("render") or {}).get(
            "draft_sha256") or [s["sha256"] for s in record["slides"]] != [s["sha256"] for s in slides]):
        return None
    return [str(run_dir / sheet["file"]) for sheet in record["sheets"]]


def _rendered(run_dir: Path, manifest: dict) -> list[dict] | None:
    """The slides of the request's rendered video, when it shows the current storyboard and they are intact."""
    stage = manifest.get("render") or {}
    if stage.get("status") != "passed" or not (run_dir / "render.json").is_file():
        return None
    render = json.loads((run_dir / "render.json").read_text(encoding="utf-8"))
    if render.get("storyboard_sha256") != manifest["script"]["sha256"]:
        return None
    for slide in render["slides"]:
        path = run_dir / slide["file"]
        if path.is_symlink() or not path.is_file() or _sha(path) != slide["sha256"]:
            return None
    return render["slides"]


def _sheets(root: Path, run_dir: Path, directory: Path, storyboard: dict, slides: list[dict]) -> list[dict]:
    from playwright.sync_api import sync_playwright

    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True)
    scenes = {scene["id"]: scene for scene in storyboard["scenes"]}
    font = (root / "assets/fonts/Inter.ttf").as_uri()
    sheets = []
    with tempfile.TemporaryDirectory(prefix="pgvideo-preview-", dir=root / ".runtime/tmp") as browser_dir:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(Path(browser_dir) / "profile"), headless=True,
                viewport={"width": SHEET_WIDTH, "height": 1080}, device_scale_factor=1,
                accept_downloads=False, downloads_path=str(Path(browser_dir) / "downloads"),
                args=["--disable-background-networking", "--disable-component-update", "--no-first-run"],
            )
            try:
                page = context.new_page()
                page.route("http://**/*", lambda route: route.abort())
                page.route("https://**/*", lambda route: route.abort())
                for first in range(0, len(slides), PER_SHEET):
                    group = slides[first:first + PER_SHEET]
                    figures = "\n".join(
                        f'<figure><img src="{(run_dir / slide["file"]).as_uri()}" alt="">'
                        f"<figcaption><b>{first + offset:03d}</b> · {html.escape(slide['id'])} · "
                        f"{html.escape(scenes[slide['id']]['part'])}</figcaption></figure>"
                        for offset, slide in enumerate(group, 1))
                    number = first // PER_SHEET + 1
                    page_file = directory / f"sheet-{number:02d}.html"
                    page_file.write_text(SHEET.format(font=font, columns=COLUMNS, width=SHEET_WIDTH, figures=figures),
                                         encoding="utf-8")
                    page.goto(page_file.as_uri(), wait_until="load")
                    loaded = page.evaluate("[...document.images].every(image => image.complete && image.naturalWidth)")
                    if not loaded:
                        raise ValueError(f"Contact sheet {number} could not load a slide image.")
                    image = directory / f"sheet-{number:02d}.png"
                    page.screenshot(path=str(image), full_page=True)
                    sheets.append({"file": str(image.relative_to(run_dir)), "sha256": _sha(image),
                                   "first": first + 1, "last": first + len(group),
                                   "scenes": [slide["id"] for slide in group]})
            finally:
                context.close()
    return sheets


def create_preview(root: Path, run_dir: Path) -> dict:
    """Write the slides (unless the rendered ones are used), the contact sheets, and preview.json."""
    # Playwright and Jinja load only when slides are rendered.
    from .render import _render_slides

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    script = manifest.get("script") or {}
    if script.get("status") != "passed":
        raise ValueError(f"The storyboard has status '{script.get('status')}'; a preview shows an accepted storyboard.")
    storyboard = json.loads(_recorded(run_dir, "storyboard.json", script))
    settings = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))["settings"]
    directory = project_directory(root, run_dir / "preview", label="Preview")
    try:
        slides = _rendered(run_dir, manifest)
        source = "render" if slides else "storyboard"
        if not slides:
            shutil.rmtree(directory / "slides", ignore_errors=True)
            # A slide does not depend on timing; the renderer only copies each scene's frame count.
            timeline = {"scenes": [{"frames": 0} for _scene in storyboard["scenes"]]}
            slides = _render_slides(root, run_dir, storyboard, timeline, directory, settings["width"],
                                    settings["height"])
        sheets = _sheets(root, run_dir, directory / "sheets", storyboard, slides)
    except (ValueError, OSError):
        raise
    except Exception as error:  # Playwright reports its own error types.
        raise ValueError(f"The preview could not be rendered: {error}") from error
    record = {
        "schema": 1, "request_id": run_dir.name,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": source, "storyboard_sha256": script["sha256"], "storyboard_digest": script.get("digest"),
        **({"video_sha256": manifest["render"]["draft_sha256"]} if source == "render" else {}),
        "width": settings["width"], "height": settings["height"],
        "slides": [{"number": number, "scene": slide["id"], "file": slide["file"], "sha256": slide["sha256"]}
                   for number, slide in enumerate(slides, 1)],
        "sheets": sheets,
    }
    write_atomic(root, run_dir.relative_to(root) / RECORD,
                 (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8"), label="Request")
    return record
