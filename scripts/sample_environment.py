"""Offline narration, slide, and WebM smoke check; outputs stay in .runtime/tmp.

Doctor runs this inside the offline sandbox and records the JSON line it prints.
"""

from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import jinja2
import numpy as np
import soundfile as sf
import yaml
from markdown_it import MarkdownIt
from playwright.sync_api import sync_playwright
from pgvideo.assets import local_kokoro
from pgvideo.cli import CRF

ROOT = Path(__file__).resolve().parents[1]
TEMP = ROOT / ".runtime" / "tmp"
FFMPEG = ROOT / ".runtime" / "bin" / "ffmpeg"
FFPROBE = ROOT / ".runtime" / "bin" / "ffprobe"
BUNDLED_FONTS = {"Inter", "Noto Sans Mono"}
OS_IMAGE_PREFIXES = ("/usr/lib/", "/usr/lib64/", "/lib/", "/lib64/")


def synthesize() -> dict:
    pipeline, voice = local_kokoro()
    chunks = list(pipeline("PostgreSQL stores data safely. Each chunk is kept in order.", voice=voice, speed=1.0))
    if not chunks or any(chunk.audio is None or len(chunk.audio) == 0 for chunk in chunks):
        raise RuntimeError("Kokoro returned no audio")
    audio = TEMP / "sample-kokoro.wav"
    sf.write(audio, np.concatenate([np.asarray(chunk.audio) for chunk in chunks]), 24000)
    info = sf.info(audio)
    if info.samplerate != 24000 or info.frames == 0:
        raise RuntimeError("Kokoro sample has invalid audio")
    return {"file": str(audio.relative_to(ROOT)), "sample_rate": info.samplerate, "frames": info.frames,
            "chunks": len(chunks)}


def render() -> dict:
    font = (ROOT / "assets/fonts/Inter.ttf").as_uri()
    mono = (ROOT / "assets/fonts/NotoSansMono.ttf").as_uri()
    template = jinja2.Environment(autoescape=True).from_string("""<!doctype html>
<html><head><meta charset="utf-8"><style>
@font-face { font-family: Inter; src: url('{{ font }}'); font-weight: 100 900; }
@font-face { font-family: NotoMono; src: url('{{ mono }}'); font-weight: 100 900; }
body { margin: 0; background: #0c1b2a; color: white; font-family: Inter; }
main { padding: 90px; } h1 { font-size: 72px; margin: 0 0 40px; }
p { font-size: 38px; } code { font-family: NotoMono; color: #92d7ff; }
</style></head><body><main><h1>{{ title }}</h1><p>Local narration and rendering</p>
<p><code>SELECT version();</code></p></main></body></html>""")
    html = TEMP / "sample-slide.html"
    html.write_text(template.render(font=font, mono=mono, title="PostgreSQL sample"), encoding="utf-8")
    image = TEMP / "sample-slide.png"
    with tempfile.TemporaryDirectory(prefix="pgvideo-browser-", dir=TEMP) as workspace:
        workspace = Path(workspace)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(workspace / "profile"), headless=True, viewport={"width": 1920, "height": 1080},
                accept_downloads=False, downloads_path=str(workspace / "downloads"),
                traces_dir=str(workspace / "traces"),
                args=["--disable-background-networking", "--disable-component-update", "--no-first-run"],
            )
            page = context.new_page()
            page.route("http://**/*", lambda route: route.abort())
            page.route("https://**/*", lambda route: route.abort())
            page.goto(html.as_uri(), wait_until="load")
            page.evaluate("document.fonts.ready")
            if not page.evaluate("document.fonts.check('600 72px Inter') && document.fonts.check('400 38px NotoMono')"):
                raise RuntimeError("bundled fonts did not load")
            fonts = rendered_fonts(context.new_cdp_session(page))
            page.screenshot(path=str(image))
            context.close()
    with image.open("rb") as stream:
        header = stream.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n" or struct.unpack(">II", header[16:24]) != (1920, 1080):
        raise RuntimeError("sample slide did not render at 1920x1080")
    return {"file": str(image.relative_to(ROOT)), "width": 1920, "height": 1080, "fonts": fonts}


def rendered_fonts(session) -> list[str]:
    """Return the fonts Chromium drew text with; installed system fonts are rejected."""
    session.send("DOM.enable")
    session.send("CSS.enable")
    document = session.send("DOM.getDocument", {"depth": -1})
    nodes = session.send("DOM.querySelectorAll", {"nodeId": document["root"]["nodeId"], "selector": "h1, p, code"})
    used = set()
    for node in nodes["nodeIds"]:
        for font in session.send("CSS.getPlatformFontsForNode", {"nodeId": node})["fonts"]:
            used.add((font["familyName"], font["isCustomFont"]))
    outside = sorted(family for family, custom in used if not custom or family not in BUNDLED_FONTS)
    if not used or outside:
        raise RuntimeError(f"slide text used fonts that are not bundled in assets/fonts: {outside}")
    return sorted(family for family, _ in used)


def webm_elements(path: Path) -> list[int]:
    """Read Segment child IDs through the first Cluster, skipping element payloads."""
    def vint(stream, *, identifier=False):
        first = stream.read(1)
        if not first or not first[0]:
            raise RuntimeError("truncated or invalid WebM element header")
        width = 9 - first[0].bit_length()
        if identifier and width > 4:
            raise RuntimeError("invalid WebM element ID")
        rest = stream.read(width - 1)
        if len(rest) != width - 1:
            raise RuntimeError("truncated WebM element header")
        value = int.from_bytes(first + rest, "big")
        if identifier:
            return value
        value &= (1 << (7 * width)) - 1
        return None if value == (1 << (7 * width)) - 1 else value

    elements = []
    end = path.stat().st_size
    with path.open("rb") as stream:
        in_segment = False
        while stream.tell() < end:
            kind, size = vint(stream, identifier=True), vint(stream)
            if not in_segment and kind == 0x18538067:  # Segment
                in_segment = True
                if size is not None:
                    end = min(end, stream.tell() + size)
                continue
            if in_segment:
                elements.append(kind)
                if kind == 0x1F43B675:  # Cluster
                    return elements
            if size is None or stream.tell() + size > end:
                raise RuntimeError("invalid WebM element size")
            stream.seek(size, 1)
    raise RuntimeError("sample WebM has no Cluster")


def encode(audio: Path, image: Path) -> dict:
    video = TEMP / "sample-video.webm"
    subprocess.run([str(FFMPEG), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                    "-loop", "1", "-framerate", "30", "-i", str(image), "-i", str(audio),
                    "-map", "0:v", "-map", "1:a", "-shortest",
                    "-c:v", "libsvtav1", "-preset", "8", "-crf", str(CRF), "-pix_fmt", "yuv420p", "-r", "30",
                    "-af", "loudnorm=I=-16:TP=-1.5,aresample=48000",
                    "-c:a", "libopus", "-b:a", "192k", "-ar", "48000", "-ac", "1",
                    "-f", "webm", "-cues_to_front", "1", str(video)], check=True)
    probe = json.loads(subprocess.run([str(FFPROBE), "-v", "error", "-show_streams", "-show_format", "-of", "json",
                                       str(video)], check=True, capture_output=True, text=True).stdout)
    streams = {stream["codec_type"]: stream for stream in probe["streams"]}
    found = (streams["video"]["codec_name"], streams["video"]["pix_fmt"], streams["video"]["width"],
             streams["video"]["height"], streams["video"]["r_frame_rate"], streams["audio"]["codec_name"],
             streams["audio"]["sample_rate"], streams["audio"]["channels"])
    if found != ("av1", "yuv420p", 1920, 1080, "30/1", "opus", "48000", 1):
        raise RuntimeError(f"sample WebM has unexpected streams: {found}")
    elements = webm_elements(video)
    if 0x1C53BB6B not in elements[:-1]:  # Cues must precede the first Cluster.
        raise RuntimeError(f"sample WebM is not optimized for streaming: {elements}")
    decoded = subprocess.run([str(FFMPEG), "-v", "error", "-nostdin", "-i", str(video), "-f", "null", "-"],
                             check=True, capture_output=True, text=True)
    if decoded.stderr.strip():
        raise RuntimeError(f"sample WebM failed to decode cleanly: {decoded.stderr.strip()}")
    return {"file": str(video.relative_to(ROOT)), "video": "av1 yuv420p 1920x1080 30 fps",
            "audio": "opus 48 kHz mono", "duration": float(probe["format"]["duration"])}


def loaded_images() -> dict:
    """Require every native image in this process to come from the project or the system libraries."""
    names = set()
    # Each line names a mapped range, its permissions, offset, device, inode, and, for a file, its path.
    for line in Path("/proc/self/maps").read_text(encoding="utf-8").splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) == 6 and "x" in fields[1] and fields[5].startswith("/"):
            names.add(fields[5])
    project = [name for name in names if Path(name).resolve().is_relative_to(ROOT)]
    outside = [name for name in names if name not in project
               and not str(Path(name).resolve()).startswith(OS_IMAGE_PREFIXES)]
    if outside:
        raise RuntimeError(f"native libraries loaded from outside the project: {outside}")
    return {"project": len(project), "os": len(names) - len(project)}


def main() -> None:
    parser = MarkdownIt("commonmark").enable("table")
    if not any(token.type == "table_open" for token in parser.parse("| A | B |\n|---|---|\n| 1 | 2 |")):
        raise RuntimeError("Markdown table syntax is unavailable")
    if yaml.safe_load("title: sample")["title"] != "sample":
        raise RuntimeError("safe YAML parsing is unavailable")
    narration = synthesize()
    slide = render()
    video = encode(ROOT / narration["file"], ROOT / slide["file"])
    print(json.dumps({"narration": narration, "slide": slide, "video": video, "native_images": loaded_images()}))


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(f"sample: {error}", file=sys.stderr)
        raise SystemExit(1)
