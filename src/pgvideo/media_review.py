"""Require recorded inspection of the exact finished video before final delivery."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import contracts
from .crosscheck import _recorded
from .orchestration import (is_harness, producer, record_event, require_content_gate, require_duration,
                            save_authored)
from .sources import write_atomic

RECORD = "media-review.json"


def inspection_inputs(run_dir: Path, manifest: dict) -> dict:
    """Keep the inspected content and captions bound to the automated validation records."""
    for stage, name in (("plan", "plan.json"), ("content_review", "content-review.json"),
                        ("evidence", "evidence-packet.json")):
        _recorded(run_dir, name, manifest[stage])
    for kind in ("srt", "vtt"):
        _recorded(run_dir, f"captions.{kind}", {"sha256": manifest["timing"][f"{kind}_sha256"]})
    return json.loads(_recorded(run_dir, "storyboard.json", manifest["script"]))


def import_media_review(root: Path, run_dir: Path, path: Path) -> dict:
    """Check coverage and artifact identity; a successful review releases the prepared package."""
    try:
        return _import(root, run_dir, path)
    except (ValueError, OSError, KeyError, TypeError) as error:
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        manifest["media_review"] = {"status": "failed", "error": str(error)}
        manifest["status"] = "failed"
        write_atomic(root, run_dir.relative_to(root) / "manifest.json",
                     (json.dumps(manifest, indent=2) + "\n").encode(), label="Request")
        raise


def _import(root: Path, run_dir: Path, path: Path) -> dict:
    if not is_harness(run_dir):
        raise ValueError("Finished-video reviews are for harness requests.")
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if (manifest.get("validation") or {}).get("status") not in ("passed", "completed"):
        raise ValueError("The automated media validation must pass before finished-video review.")
    require_content_gate(run_dir, manifest)
    require_duration(run_dir, manifest)
    storyboard = inspection_inputs(run_dir, manifest)
    file = contracts.project_file(root, path, label="Media review file")
    data = file.read_bytes()
    raw = contracts.parse(data, str(file.relative_to(root)))
    contracts.require(root, "media-review", raw, str(file.relative_to(root)))
    if raw["request_id"] != run_dir.name:
        raise ValueError("The media review belongs to another request.")
    video = contracts.project_file(root, run_dir / "render/draft.mp4", label="Inspected video")
    actual_video = hashlib.sha256(video.read_bytes()).hexdigest()
    if raw["video_sha256"] != manifest["render"]["draft_sha256"] or raw["video_sha256"] != actual_video:
        raise ValueError("The media review names another video or the video changed after validation.")
    if raw["storyboard_digest"] != manifest["script"]["digest"]:
        raise ValueError("The media review names another storyboard.")
    scenes = {s["id"] for s in storyboard["scenes"]}
    seen, issues = set(), []
    for item in raw["scenes"]:
        scene = item["scene"]
        if scene not in scenes or scene in seen:
            raise ValueError(f"The media review names an unknown or duplicate scene: {scene}.")
        seen.add(scene)
        for kind in ("visual", "listening", "captions"):
            if item[kind] != "passed":
                issues.append({"severity": "blocking", "code": f"media_{kind}", "scene": scene,
                               "unavailable": item[kind] == "unavailable",
                               "message": f"{kind}: {item[kind]}. {item['message']}"})
    if missing := scenes - seen:
        raise ValueError("The media review leaves scenes unchecked: " + ", ".join(sorted(missing)))
    for kind, check in raw["checks"].items():
        if check["verdict"] != "passed":
            issues.append({"severity": "blocking", "code": f"media_{kind}",
                           "unavailable": check["verdict"] == "unavailable",
                           "message": f"{kind}: {check['verdict']}. {check['message']}"})
    made_by = producer(root, raw["producer"], phase="media-review")
    status = "needs_review" if issues else "passed"
    record = {**raw, "status": status, "issues": issues, "producer": made_by,
              "authored": save_authored(root, run_dir, RECORD, data)}
    body = (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode()
    write_atomic(root, run_dir.relative_to(root) / RECORD, body, label="Request")
    entry = {"status": status, "record": RECORD, "sha256": hashlib.sha256(body).hexdigest(),
             "unavailable_checks": any(i["unavailable"] for i in issues),
             "video_sha256": raw["video_sha256"], "storyboard_digest": raw["storyboard_digest"]}
    manifest["media_review"] = entry
    manifest["status"] = "media_reviewed" if status == "passed" else status
    write_atomic(root, run_dir.relative_to(root) / "manifest.json",
                 (json.dumps(manifest, indent=2) + "\n").encode(), label="Request")
    record_event(root, run_dir, stage="media_review", status=status, artifact=RECORD,
                 sha256=entry["sha256"], producer=made_by)
    if status == "passed":
        from .validate import deliver_reviewed

        return deliver_reviewed(root, run_dir)
    return entry
