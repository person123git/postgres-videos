"""Key completed videos by their inputs and reuse one only when every input matches (Step 12).

Accepted harness content is keyed separately (see the end of this module): its
key covers the evidence, the phase prompts, the schemas, and the review policy,
never the request, so a later request can replay the accepted plan, storyboard,
and review through the ordinary validators without new inference. A video's key
covers only what the media depends on, so identical accepted scenes reuse media
while a changed review policy still forces a new content review first.


A video's key covers the snapshot inputs (the document, the glossary, wiki images,
and the cited PostgreSQL files, with the wiki commit and the source pin), the
storyboard without its request-specific fields, the pronunciation dictionary, the
voice, speed, and loudness settings, the Kokoro assets, the render settings, and
the SHA-256 of the locks, template, fonts, and media code. Step 11 registers each
validated video as cache/videos/<key>/<request-id>.json. When a later script has
the same key, the registered narration and MP4 are verified, copied into the new
request, and checked again by that request's own timing and validation stages.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .orchestration import AUTHORED, REVIEW_POLICY, prompt_hashes, require_content_gate, schema_hashes
from .paths import REQUEST_ID, project_directory
from .sources import write_atomic

SCHEMA = 1
INDEX = Path("cache/videos")
AUDIO_MAP = "narration/audio-map.json"
RENDER = "render.json"
RECORDS = (AUDIO_MAP, RENDER)
# The locks, templates, fonts, and modules that decide how a storyboard becomes the delivered media.
LOCKS = ("tools.lock", "requirements.lock")
PROJECT_FILES = ("templates/slide.html", "assets/fonts/Inter.ttf", "assets/fonts/NotoSansMono.ttf")
MODULES = ("assets.py", "speech.py", "narration.py", "timing.py", "render.py", "validate.py")
# Stages that record the tools they ran with; validation compares them with its own.
RECORDED_STAGES = ("narration", "timing", "render")
# Storyboard fields that differ between requests for the same content.
REQUEST_FIELDS = ("request_id", "created_at", "drafter", "inputs")
# A harness storyboard's estimates follow the measured speech rate, which changes as more narration is measured;
# they are left out so the same accepted scenes keep one digest, one review, and one video.
ESTIMATE_FIELDS = ("status", "settings", "estimate", "counts", "issues", "semantic_review")
MEDIA_FILE = re.compile(r"narration/(?:units/[A-Za-z0-9][A-Za-z0-9._-]*\.wav|master(?:-raw)?\.wav)"
                        r"|render/(?:slides/\d{3,4}\.(?:png|html)|slides\.ffconcat|draft\.mp4)|references\.md")
REQUIRED_FILES = ("narration/master.wav", "narration/master-raw.wav", "render/draft.mp4", "references.md")


class ReuseError(ValueError):
    """A registered video cannot be reused for this request."""


@dataclass(frozen=True)
class Video:
    """A registered video whose files were verified against its index entry."""

    key: str
    request_id: str
    run_dir: Path
    entry: dict


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _digest(value) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def video_key(parts: dict) -> str:
    """Return the key of a video with these components."""
    return _digest(parts)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


# Key --------------------------------------------------------------------------------------------


def tools(root: Path) -> dict:
    """Return the SHA-256 of each file that turns a storyboard into audio, captions, slides, and the MP4.

    tools.lock and requirements.lock stand for the Kokoro assets, eSpeak NG, FFmpeg,
    Chromium, fonts, and Python packages, which doctor verifies against them before
    every command.
    """
    package = Path(__file__).resolve().parent
    files = {name: _sha(root / name) for name in (*LOCKS, *PROJECT_FILES)}
    files.update({f"pgvideo/{name}": _sha(package / name) for name in MODULES})
    return {"sha256": _digest(files), "files": files}


def stage_fingerprint(root: Path) -> str | None:
    """Return the tools digest a media stage records, or None when one of the files is missing."""
    try:
        return tools(root)["sha256"]
    except OSError:
        return None


def script_sha256(storyboard: dict) -> str:
    """Hash a storyboard without the fields that differ between requests for the same content.

    The storyboard's document record keeps the wiki commit, which the slides and
    references show, so a video is reused only for the same wiki commit.
    """
    content = {key: value for key, value in storyboard.items() if key not in REQUEST_FIELDS}
    if storyboard.get("workflow") == "harness":
        content = {key: value for key, value in content.items() if key not in ESTIMATE_FIELDS}
        content["scenes"] = [{key: value for key, value in scene.items() if key != "estimated_seconds"}
                             for scene in content.get("scenes", [])]
    return _digest(content)


def _one(inputs: list[dict], role: str) -> dict:
    found = [entry for entry in inputs if entry["role"] == role]
    if len(found) != 1:
        raise ValueError(f"The source snapshot records {len(found)} {role} input(s).")
    return found[0]


def components(manifest: dict, storyboard: dict, *, narration: dict, render: dict, tools: dict) -> dict:
    """Return every input a completed video depends on; the video's key is their SHA-256."""
    sources = manifest["sources"]
    inputs = sorted(({key: entry[key] for key in ("role", "repository", "commit", "path", "sha256")}
                     for entry in sources["inputs"]), key=lambda entry: (entry["repository"], entry["path"]))
    document, glossary = _one(inputs, "document"), _one(inputs, "glossary")
    return {
        "schema": SCHEMA,
        "document": {"path": document["path"], "sha256": document["sha256"]},
        "glossary": {"path": glossary["path"], "sha256": glossary["sha256"]},
        "sources": {"wiki_commit": sources["wiki"]["commit"],
                    "postgres": {"version": sources["postgres"].get("version"),
                                 "commit": sources["postgres"].get("commit")},
                    "inputs": inputs},
        "script": script_sha256(storyboard),
        "pronunciation": storyboard["pronunciation"]["sha256"],
        "narration": narration,
        "render": render,
        "tools": tools,
    }


def _narration(settings: dict, *, loudness: float, peak: float, assets: dict) -> dict:
    return {"voice": settings["voice"], "language": settings["language"], "speed": settings["speed"],
            "loudness_lufs": float(loudness), "true_peak_dbtp": float(peak),
            "model": assets["model"], "config": assets["config"], "voice_asset": assets["voice_asset"]}


def _render(width: int, height: int, fps: int, crf: int, audio_bitrate: int) -> dict:
    return {"width": width, "height": height, "fps": fps, "crf": crf, "audio_bitrate_kbps": audio_bitrate}


def planned_key(root: Path, run_dir: Path, manifest: dict, *, loudness: float, peak: float, crf: int,
                audio_bitrate: int) -> tuple[str, dict]:
    """Return the key and components of the video this request's passed script would produce now."""
    from .timing import FPS

    storyboard = _verified_json(run_dir / "storyboard.json", (manifest.get("script") or {}).get("sha256"))
    settings = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))["settings"]
    kokoro = json.loads((root / "tools.lock").read_text(encoding="utf-8"))["kokoro"]
    assets = {"model": kokoro["model"]["sha256"], "config": kokoro["config"]["sha256"],
              "voice_asset": kokoro["voice"]["sha256"]}
    parts = components(manifest, storyboard,
                       narration=_narration(settings, loudness=loudness, peak=peak, assets=assets),
                       render=_render(settings["width"], settings["height"], FPS, crf, audio_bitrate),
                       tools=tools(root))
    return video_key(parts), parts


# Lookup -----------------------------------------------------------------------------------------


def find_video(root: Path, run_dir: Path, *, enabled: bool = True, loudness: float, peak: float, crf: int,
               audio_bitrate: int) -> tuple[Video | None, dict]:
    """Find a registered video with this request's key and verify its files.

    Records the lookup as the manifest's `reuse` record and returns the video, or
    None, with that record. Index entries whose files are missing or changed are
    removed. The lookup reads only the index and the runs it names; it never
    creates or changes another request.
    """
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    key = parts = found = None
    if not enabled:
        lookup: dict = {"status": "disabled"}
    else:
        try:
            key, parts = planned_key(root, run_dir, manifest, loudness=loudness, peak=peak, crf=crf,
                                     audio_bitrate=audio_bitrate)
            found, rejected = _search(root, run_dir, key)
        except (ValueError, OSError, KeyError, TypeError) as error:
            lookup = {"status": "unavailable", "reason": str(error)}
        else:
            lookup = {"status": "found" if found else "not_found",
                      "request_id": found.request_id if found else None, "rejected": rejected}
    manifest["reuse"] = {"key": key, "components": parts, "lookup": lookup}
    write_atomic(root, run_dir.relative_to(root) / "manifest.json", _json_bytes(manifest), label="Request")
    return found, manifest["reuse"]


def _search(root: Path, run_dir: Path, key: str) -> tuple[Video | None, list[dict]]:
    directory = project_directory(root, INDEX / key, label="Video cache")
    if not directory.is_dir():
        return None, []
    entries = [path for path in directory.glob("*.json") if path.is_file() and not path.is_symlink()]
    # Prefer this request's own earlier video, which needs no copying, then the newest.
    entries.sort(key=lambda path: (path.stem != run_dir.name, -path.stat().st_mtime))
    rejected = []
    for path in entries:
        try:
            return _verify(root, key, path), rejected
        except (ValueError, OSError, KeyError, TypeError) as error:
            rejected.append({"request_id": path.stem, "reason": str(error)})
            # Removing a stale entry is the only cache maintenance; it never creates a request.
            path.unlink(missing_ok=True)
    return None, rejected


def _verify(root: Path, key: str, path: Path) -> Video:
    entry = json.loads(path.read_bytes())
    if not isinstance(entry, dict) or entry.get("schema") != SCHEMA or entry.get("key") != key:
        raise ReuseError("the index entry is for another key or schema")
    request_id = entry.get("request_id")
    if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id) or request_id != path.stem:
        raise ReuseError("the index entry names an invalid request")
    if video_key(entry.get("components")) != key:
        raise ReuseError("the index entry's inputs do not produce its key")
    files, records = entry.get("files"), entry.get("records")
    if not isinstance(files, dict) or not isinstance(records, dict) or set(records) != set(RECORDS) \
            or not set(REQUIRED_FILES) <= set(files):
        raise ReuseError("the index entry does not list the video's files")
    source = project_directory(root, Path("runs") / request_id, label="Request")
    for relative, digest in {**records, **files}.items():
        if _sha(_member(root, source, relative)) != digest:
            raise ReuseError(f"{relative} in request {request_id} changed after validation")
    return Video(key=key, request_id=request_id, run_dir=source, entry=entry)


def _member(root: Path, base: Path, relative) -> Path:
    """Return a registered file of a run, rejecting other names, escapes, and symlinks."""
    if not isinstance(relative, str) or not (MEDIA_FILE.fullmatch(relative) or relative in RECORDS):
        raise ReuseError(f"{relative!r} is not a narration, render, or reference file")
    path = Path(relative)
    member = project_directory(root, base / path.parent, label="Request") / path.name
    if member.is_symlink() or not member.is_file():
        raise ReuseError(f"{relative} is missing from {base.name}")
    return member


def _verified_json(path: Path, digest: str | None, *, recorded_in: str = "manifest.json") -> dict:
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ReuseError(f"{path.name} does not match the SHA-256 recorded in {recorded_in}")
    return json.loads(data)


def _source_record(root: Path, video: Video, relative: str) -> dict:
    return _verified_json(_member(root, video.run_dir, relative), video.entry["records"][relative],
                          recorded_in=f"the reuse index entry of request {video.request_id}")


def _copy(root: Path, video: Video, run_dir: Path, relative: str) -> None:
    """Copy one registered file into this request, verifying the bytes that arrive."""
    digest = video.entry["files"][relative]
    source = _member(root, video.run_dir, relative)
    path = Path(relative)
    parent = project_directory(root, run_dir / path.parent, label="Request")
    target = parent / path.name
    if target == source:
        if _sha(source) != digest:
            raise ReuseError(f"{relative} changed after validation")
        return
    if target.is_symlink():
        raise ReuseError(f"{relative} is a symlink in this request")
    parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=parent, prefix=f".{path.name[:40]}.", suffix=".tmp")
    try:
        copied = hashlib.sha256()
        with os.fdopen(descriptor, "wb") as output, source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                copied.update(chunk)
                output.write(chunk)
        if copied.hexdigest() != digest:
            raise ReuseError(f"{relative} changed while it was copied from request {video.request_id}")
        Path(temporary).chmod(0o644)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


# Reuse ------------------------------------------------------------------------------------------


def reuse_narration(root: Path, run_dir: Path, video: Video) -> dict:
    """Copy a registered video's narration into this request and record it as this request's Step 8."""
    from .narration import publish

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    script = manifest.get("script") or {}
    if script.get("status") != "passed":
        raise ReuseError("The script must pass before narration")
    require_content_gate(run_dir, manifest)
    record = _source_record(root, video, AUDIO_MAP)
    for relative in video.entry["files"]:
        if relative.startswith("narration/"):
            _copy(root, video, run_dir, relative)
    settings = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))["settings"]
    units = sum(len(scene["units"]) for scene in record["scenes"])
    record.update(request_id=run_dir.name, created_at=_now(), storyboard_sha256=script["sha256"],
                  settings=settings, cache={"created": 0, "reused": units},
                  reused_from={"request_id": video.request_id, "audio_map_sha256": video.entry["records"][AUDIO_MAP]})
    return publish(root, run_dir, manifest, record)


def reuse_render(root: Path, run_dir: Path, video: Video) -> dict:
    """Copy a registered video's slides and MP4 into this request after its own timing passed."""
    from .render import publish

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    script, timing = manifest.get("script") or {}, manifest.get("timing") or {}
    if script.get("status") != "passed" or timing.get("status") != "passed":
        raise ReuseError("Script and timing must pass before rendering")
    record = _source_record(root, video, RENDER)
    timeline = _verified_json(run_dir / "timeline.json", timing["sha256"])
    settings = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))["settings"]
    if (record["width"], record["height"]) != (settings["width"], settings["height"]):
        raise ReuseError("The registered video has other dimensions")
    if record["frames"] != timeline["total_frames"] or \
            [(slide["id"], slide["frames"]) for slide in record["slides"]] != \
            [(scene["id"], scene["frames"]) for scene in timeline["scenes"]]:
        raise ReuseError("The registered slides do not follow this request's timeline")
    for relative in video.entry["files"]:
        if relative.startswith("render/") or relative == "references.md":
            _copy(root, video, run_dir, relative)
    record.update(created_at=_now(), timeline_sha256=timing["sha256"], storyboard_sha256=script["sha256"],
                  reused_from={"request_id": video.request_id, "render_sha256": video.entry["records"][RENDER]})
    return publish(root, run_dir, manifest, record)


# Registration -----------------------------------------------------------------------------------


def _stages(names: list[str]) -> str:
    listed = names[0] if len(names) == 1 else f"{', '.join(names[:-1])}{',' if len(names) > 2 else ''} and {names[-1]}"
    return f"the {listed} stage{'s' if len(names) > 1 else ''}"


def register(root: Path, run_dir: Path, manifest: dict, *, storyboard: dict, audio_map: dict, render: dict) -> dict:
    """Register a validated video under its key and return the manifest's reuse record.

    The key comes from the settings the stages recorded, so it equals a later
    lookup's key only when that request would build the same video. A video whose
    stages ran with other tools or code than this validation is not registered.
    Registration never fails validation; the record gives the reason instead.
    """
    lookup = (manifest.get("reuse") or {}).get("lookup")
    reuse: dict = {"lookup": lookup} if lookup else {}
    try:
        current = tools(root)
        recorded = {stage: (manifest.get(stage) or {}).get("fingerprint") for stage in RECORDED_STAGES}
        if missing := [stage for stage, digest in recorded.items() if not digest]:
            raise ReuseError(f"{_stages(missing)} recorded no tools digest; repeat {'it' if len(missing) == 1 else 'them'} "
                             "to register the video")
        if stale := [stage for stage, digest in recorded.items() if digest != current["sha256"]]:
            raise ReuseError(f"{_stages(stale)} ran with other tools or code than this validation")
        normalization = audio_map["normalization"]
        parts = components(manifest, storyboard,
                           narration=_narration(audio_map["settings"], loudness=normalization["target_lufs"],
                                                peak=normalization["target_true_peak_dbtp"],
                                                assets=audio_map["assets"]),
                           render=_render(render["width"], render["height"], render["fps"], render["crf"],
                                          render["audio_bitrate_kbps"]),
                           tools=current)
        key = video_key(parts)
        reuse.update(key=key, components=parts)
        files = {unit["file"]: unit["sha256"] for scene in audio_map["scenes"] for unit in scene["units"]}
        for name in ("master", "raw_master"):
            files[audio_map[name]["file"]] = audio_map[name]["sha256"]
        for slide in render["slides"]:
            files[slide["file"]] = slide["sha256"]
            page = Path(slide["file"]).with_suffix(".html").as_posix()
            files[page] = _sha(_member(root, run_dir, page))
        files["render/slides.ffconcat"] = _sha(_member(root, run_dir, "render/slides.ffconcat"))
        files[render["draft"]] = render["sha256"]
        files[render["references"]] = render["references_sha256"]
        records = {AUDIO_MAP: manifest["narration"]["sha256"], RENDER: manifest["render"]["sha256"]}
        for relative, digest in {**records, **files}.items():
            if _sha(_member(root, run_dir, relative)) != digest:
                raise ReuseError(f"{relative} changed after its stage recorded it")
        entry = {"schema": SCHEMA, "key": key, "request_id": run_dir.name, "registered_at": _now(),
                 "components": parts,
                 "document": {name: storyboard["document"].get(name) for name in ("path", "title", "url", "version")},
                 "records": records, "files": files,
                 "video": {"file": render["draft"], "sha256": render["sha256"], "frames": render["frames"]}}
        relative = INDEX / key / f"{run_dir.name}.json"
        write_atomic(root, relative, _json_bytes(entry), label="Video cache")
    except (ValueError, OSError, KeyError, TypeError) as error:
        return reuse | {"registered": False, "reason": str(error)}
    return reuse | {"registered": True, "index": relative.as_posix()}


# Accepted harness content -----------------------------------------------------------------------

CONTENT_INDEX = Path("cache/content")
CONTENT_FILES = ("plan.json", "storyboard.json", "review.json")


def content_components(root: Path, manifest: dict) -> dict:
    """What accepted content depends on; the harness model is recorded separately, as it may be unknown."""
    return {"schema": SCHEMA, "evidence": (manifest.get("evidence") or {}).get("digest"),
            "prompts": prompt_hashes(root), "schemas": schema_hashes(root), "review_policy": REVIEW_POLICY}


def register_content(root: Path, run_dir: Path) -> dict:
    """Register a request's accepted plan, storyboard, and review for replay by later requests."""
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    try:
        parts = content_components(root, manifest)
        key = _digest(parts)
        files = {}
        for name in CONTENT_FILES:
            path = _authored(root, run_dir, name)
            files[name] = _sha(path)
        entry = {"schema": SCHEMA, "key": key, "components": parts, "request_id": run_dir.name,
                 "registered_at": _now(), "files": files,
                 "digests": {stage: (manifest.get(stage) or {}).get("digest") for stage in ("plan", "script",
                                                                                              "content_review")}}
        write_atomic(root, CONTENT_INDEX / key / f"{run_dir.name}.json", _json_bytes(entry), label="Content cache")
    except (ValueError, OSError, KeyError, TypeError) as error:
        return {"registered": False, "reason": str(error)}
    return {"registered": True, "key": key}


def find_content(root: Path, run_dir: Path) -> list[str]:
    """Return earlier requests whose accepted content was made from the same evidence, prompts, and policy."""
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if not (manifest.get("evidence") or {}).get("digest"):
        return []
    key = _digest(content_components(root, manifest))
    try:
        directory = project_directory(root, CONTENT_INDEX / key, label="Content cache")
    except ValueError:
        return []
    found = []
    for path in sorted(directory.glob("*.json"), key=lambda p: -p.stat().st_mtime) if directory.is_dir() else []:
        try:
            entry = json.loads(path.read_bytes())
            source = project_directory(root, Path("runs") / entry["request_id"], label="Request")
            if entry.get("key") != key or entry["request_id"] == run_dir.name or entry["request_id"] != path.stem:
                continue
            if all(_sha(_authored(root, source, name)) == digest for name, digest in entry["files"].items()):
                found.append(entry["request_id"])
        except (ValueError, OSError, KeyError, TypeError):
            continue
    return found


def _authored(root: Path, run_dir: Path, name: str) -> Path:
    if name not in CONTENT_FILES:
        raise ReuseError(f"{name!r} is not an accepted harness file")
    path = project_directory(root, run_dir / AUTHORED, label="Request") / name
    if path.is_symlink() or not path.is_file():
        raise ReuseError(f"{AUTHORED}/{name} is missing from {run_dir.name}")
    return path
