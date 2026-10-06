"""Render the storyboard's scenes as slides and assemble a frame-aligned draft MP4."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape
from playwright.sync_api import sync_playwright

from .paths import project_directory, write_atomic
from .reuse import stage_fingerprint
from .stages import invalidate_after

RECORD = "render.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inline_code(value: str) -> Markup:
    """Render the storyboard's simple Markdown code spans without exposing HTML."""
    parts = value.split("`")
    if len(parts) % 2 == 0:
        return escape(value)
    return Markup("".join(str(escape(part)) if index % 2 == 0 else
                          f"<code>{escape(part)}</code>" for index, part in enumerate(parts)))


def _run(args: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise ValueError(f"{' '.join(args[:2])} failed: {result.stderr[-2000:]}")
    return result


def _image(root: Path, screen: dict) -> str | None:
    """Return the file URL of a slide's image, which is the project file the storyboard import recorded."""
    image = screen.get("image")
    if not image:
        return None
    path = image.get("path")
    if not isinstance(path, str) or not path or path.startswith(("http:", "https:", "/")):
        raise ValueError("A slide image must be a file inside the project")
    file = project_directory(root, Path(path).parent, label="Image") / Path(path).name
    if file.is_symlink() or not file.is_file() or _sha(file) != image.get("sha256"):
        raise ValueError(f"The slide image {path} is missing or changed after the storyboard was imported")
    return file.as_uri()


def _references(storyboard: dict) -> str:
    document = storyboard["document"]
    lines = [f"# References — {storyboard['title']}", "",
             f"Document: {document.get('url') or document['path']} (PostgreSQL {document['version']})", ""]
    seen = set()
    for scene in storyboard["scenes"]:
        links = [item for item in scene.get("citations", []) if isinstance(item, dict)]
        fresh = []
        for link in links:
            url = link.get("url")
            if url and url not in seen:
                seen.add(url)
                fresh.append(link)
        if fresh:
            lines += [f"## {scene['title']}", ""]
            lines += [f"- [{link.get('text') or link['url']}]({link['url']})" for link in fresh]
            lines.append("")
    return "\n".join(lines) + "\n"


def _check_rendered_fonts(page, scene_id: str) -> None:
    session = page.context.new_cdp_session(page)
    try:
        session.send("DOM.enable")
        session.send("CSS.enable")
        document = session.send("DOM.getDocument", {"depth": -1})
        nodes = session.send("DOM.querySelectorAll", {"nodeId": document["root"]["nodeId"],
                                                  "selector": "main *"})["nodeIds"]
        used = set()
        for node in nodes:
            for font in session.send("CSS.getPlatformFontsForNode", {"nodeId": node})["fonts"]:
                used.add((font["familyName"], font["isCustomFont"]))
        if not used or any(not custom or family not in {"Inter", "NotoMono", "Noto Sans Mono"}
                           for family, custom in used):
            raise ValueError(f"Slide {scene_id} used a font outside assets/fonts: {sorted(used)}")
    finally:
        session.detach()


def _render_slides(root: Path, run_dir: Path, storyboard: dict, timeline: dict, render_dir: Path,
                   width: int, height: int) -> list[dict]:
    environment = Environment(loader=FileSystemLoader(root / "templates"),
                              autoescape=select_autoescape(["html"]))
    environment.filters["inline_code"] = _inline_code
    template = environment.get_template("slide.html")
    slides_dir = project_directory(root, render_dir / "slides", label="Render slides")
    slides_dir.mkdir(parents=True, exist_ok=True)
    font_url = (root / "assets/fonts/Inter.ttf").as_uri()
    mono_url = (root / "assets/fonts/NotoSansMono.ttf").as_uri()
    results = []
    with tempfile.TemporaryDirectory(prefix="pgvideo-render-", dir=root / ".runtime/tmp") as browser_dir:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(Path(browser_dir) / "profile"), headless=True,
                viewport={"width": width, "height": height}, device_scale_factor=1,
                accept_downloads=False, downloads_path=str(Path(browser_dir) / "downloads"),
                args=["--disable-background-networking", "--disable-component-update", "--no-first-run"],
            )
            try:
                page = context.new_page()
                page.route("http://**/*", lambda route: route.abort())
                page.route("https://**/*", lambda route: route.abort())
                for index, (scene, timing) in enumerate(zip(storyboard["scenes"], timeline["scenes"]), 1):
                    screen = scene["screen"]
                    image_url = _image(root, screen)
                    note = storyboard["document"]["path"]
                    # An edge names its nodes by ID; the slide shows their labels.
                    node_labels = {node["id"]: node["label"]
                                   for node in (screen.get("diagram") or {}).get("nodes", [])}
                    html = template.render(font_url=font_url, mono_url=mono_url, layout=screen["layout"],
                                           screen=screen, title=scene["title"], part=scene["part"],
                                           version=storyboard["document"]["version"], source_note=note,
                                           image_url=image_url, node_labels=node_labels)
                    html_path = slides_dir / f"{index:03d}.html"
                    html_path.write_text(html, encoding="utf-8")
                    page.goto(html_path.as_uri(), wait_until="load")
                    page.evaluate("Promise.all([document.fonts.load('600 32px Inter'), document.fonts.load('400 20px NotoMono')])")
                    if not page.evaluate("document.fonts.check('600 32px Inter') && document.fonts.check('400 20px NotoMono')"):
                        raise ValueError(f"Bundled fonts failed to load in scene {scene['id']}")
                    state = page.evaluate("""() => {
                      const all = [...document.querySelectorAll('main, h1, .content, .line, pre, table, .term, footer')];
                      const overflow = all.filter(el => el.scrollWidth > el.clientWidth + 2 ||
                        el.scrollHeight > el.clientHeight + 2).map(el => el.tagName.toLowerCase());
                      const image = document.querySelector('img');
                      return {overflow, imageLoaded: !image || (image.complete && image.naturalWidth > 0)};
                    }""")
                    if state["overflow"] or not state["imageLoaded"]:
                        raise ValueError(f"Slide {scene['id']} has overflow, cropped content, or a missing image: {state}")
                    _check_rendered_fonts(page, scene["id"])
                    png = slides_dir / f"{index:03d}.png"
                    page.screenshot(path=str(png))
                    header = png.read_bytes()[:24]
                    if header[:8] != b"\x89PNG\r\n\x1a\n" or struct.unpack(">II", header[16:24]) != (width, height):
                        raise ValueError(f"Slide {scene['id']} has incorrect PNG dimensions")
                    results.append({"id": scene["id"], "file": str(png.relative_to(run_dir)),
                                    "sha256": _sha(png), "frames": timing["frames"]})
            finally:
                context.close()
    return results


def create_render(root: Path, run_dir: Path, *, crf: int = 20, audio_bitrate: int = 192) -> dict:
    """Build a draft MP4; validation checks it before delivery."""
    # libopus accepts at most 256 kb/s for one channel.
    if not 0 <= crf <= 51 or not 32 <= audio_bitrate <= 256:
        raise ValueError("CRF must be 0–51 and audio bitrate must be 32–256 kb/s")
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    try:
        timing_stage, script_stage = manifest.get("timing") or {}, manifest.get("script") or {}
        if timing_stage.get("status") != "passed" or script_stage.get("status") != "passed":
            raise ValueError("The storyboard and timing must pass before rendering")
        timeline_path, storyboard_path = run_dir / "timeline.json", run_dir / "storyboard.json"
        if _sha(timeline_path) != timing_stage["sha256"] or _sha(storyboard_path) != script_stage["sha256"]:
            raise ValueError("Storyboard or timeline changed after validation; rerun timing")
        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
        storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
        if len(timeline["scenes"]) != len(storyboard["scenes"]) or not timeline["scenes"]:
            raise ValueError("Timeline does not cover every storyboard scene")
        if timeline["fps"] != 30 or timeline["storyboard_sha256"] != script_stage["sha256"]:
            raise ValueError("Timeline is not a 30 fps match for this storyboard")
        if any(t["id"] != s["id"] or t["frames"] <= 0 for t, s in zip(timeline["scenes"], storyboard["scenes"])):
            raise ValueError("Timeline scene order differs from storyboard")
        request = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
        width, height = request["settings"]["width"], request["settings"]["height"]
        if not all(isinstance(n, int) and n > 0 and n % 2 == 0 for n in (width, height)):
            raise ValueError("Video dimensions must be positive even integers")
        render_dir = project_directory(root, run_dir / "render", label="Render")
        render_dir.mkdir(parents=True, exist_ok=True)
        slides = _render_slides(root, run_dir, storyboard, timeline, render_dir, width, height)
        concat = render_dir / "slides.ffconcat"
        lines = ["ffconcat version 1.0"]
        for slide in slides:
            lines += [f"file 'slides/{Path(slide['file']).name}'", "option framerate 30",
                      f"duration {slide['frames'] / 30:.9f}"]
        lines += [f"file 'slides/{Path(slides[-1]['file']).name}'", "option framerate 30"]
        concat.write_text("\n".join(lines) + "\n", encoding="utf-8")
        references = _references(storyboard)
        write_atomic(root, run_dir.relative_to(root) / "references.md", references.encode(), label="Request")
        ffmpeg = root / ".runtime/bin/ffmpeg"
        draft = render_dir / "draft.mp4"
        audio = run_dir / "narration/master.wav"
        _run([str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
              "-safe", "0", "-f", "concat", "-i", str(concat), "-i", str(audio),
              "-map", "0:v:0", "-map", "1:a:0", "-vf", "fps=30", "-frames:v", str(timeline["total_frames"]),
              "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p",
              "-r", "30", "-c:a", "libopus", "-b:a", f"{audio_bitrate}k", "-ar", "48000", "-ac", "1",
              "-movflags", "+faststart", str(draft)])
        probe = json.loads(_run([str(root / ".runtime/bin/ffprobe"), "-v", "error", "-count_frames",
                                 "-show_streams", "-show_format", "-of", "json", str(draft)]).stdout)
        streams = {s["codec_type"]: s for s in probe["streams"]}
        video, sound = streams["video"], streams["audio"]
        if (video["codec_name"], video["pix_fmt"], video["width"], video["height"],
            video["r_frame_rate"], int(video.get("nb_read_frames", -1)), sound["codec_name"],
            sound["sample_rate"], sound["channels"]) != (
                "h264", "yuv420p", width, height, "30/1", timeline["total_frames"],
                "opus", "48000", 1):
            raise ValueError("Encoded streams do not match the requested format or frame count")
        record = {"status": "passed", "created_at": datetime.now(timezone.utc).isoformat(),
                  "draft": str(draft.relative_to(run_dir)), "sha256": _sha(draft),
                  "slides": slides, "frames": timeline["total_frames"], "width": width, "height": height,
                  "fps": 30, "crf": crf, "audio_bitrate_kbps": audio_bitrate,
                  "template_sha256": _sha(root / "templates/slide.html"),
                  "references": "references.md", "references_sha256": hashlib.sha256(references.encode()).hexdigest(),
                  "timeline_sha256": timing_stage["sha256"], "storyboard_sha256": script_stage["sha256"],
                  "fingerprint": stage_fingerprint(root)}
        return publish(root, run_dir, manifest, record)
    except Exception as error:
        manifest["status"] = "failed"
        invalidate_after(manifest, "render")
        manifest["render"] = {"status": "failed", "error": str(error)}
        write_atomic(root, run_dir.relative_to(root) / "manifest.json",
                     (json.dumps(manifest, indent=2) + "\n").encode(), label="Request")
        raise


def publish(root: Path, run_dir: Path, manifest: dict, record: dict) -> dict:
    """Write render.json and record it as the request's render stage."""
    data = (json.dumps(record, indent=2) + "\n").encode()
    write_atomic(root, run_dir.relative_to(root) / RECORD, data, label="Request")
    manifest["render"] = {"status": "passed", "record": RECORD, "sha256": hashlib.sha256(data).hexdigest(),
                          "draft": record["draft"], "draft_sha256": record["sha256"], "frames": record["frames"],
                          "fingerprint": record.get("fingerprint")}
    reused_from = (record.get("reused_from") or {}).get("request_id")
    if reused_from:
        manifest["render"]["reused_from"] = reused_from
    manifest["status"] = "render_ready"
    invalidate_after(manifest, "render")
    write_atomic(root, run_dir.relative_to(root) / "manifest.json",
                 (json.dumps(manifest, indent=2) + "\n").encode(), label="Request")
    return manifest["render"]
