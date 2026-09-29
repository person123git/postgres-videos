"""Build a frame-aligned scene timeline and subtitles from measured audio samples."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import soundfile as sf

from .reuse import stage_fingerprint
from .sources import write_atomic
from .stages import invalidate_after

TIMELINE = "timeline.json"
SRT = "captions.srt"
VTT = "captions.vtt"
FPS = 30


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _timestamp(milliseconds: int, *, vtt: bool) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, fraction = divmod(remainder, 1000)
    separator = "." if vtt else ","
    return f"{hours:02}:{minutes:02}:{seconds:02}{separator}{fraction:03}"


def _milliseconds(sample: int, rate: int) -> int:
    return (sample * 1000 + rate // 2) // rate


def _caption_text(value: str) -> str:
    # Backticks mark code in the canonical script; the term inside is retained.
    words = re.sub(r"\s+", " ", value.replace("`", "")).strip().split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > 42:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return "\n".join(lines)


def create_timing(root: Path, run_dir: Path) -> dict:
    """Validate the audio map and emit contiguous video frames and caption cues."""
    try:
        return _create_timing(root, run_dir)
    except (ValueError, OSError, KeyError, TypeError) as error:
        path = run_dir / "manifest.json"
        if path.is_file():
            manifest = json.loads(path.read_text(encoding="utf-8"))
            invalidate_after(manifest, "timing")
            manifest["status"] = "failed"
            manifest["timing"] = {"status": "failed", "error": str(error)}
            write_atomic(root, run_dir.relative_to(root) / "manifest.json",
                         (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode(), label="Request")
        raise


def _create_timing(root: Path, run_dir: Path) -> dict:
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    narration = manifest.get("narration") or {}
    script = manifest.get("script") or {}
    if narration.get("status") != "passed" or script.get("status") != "passed":
        raise ValueError("The script and narration must pass before timing")
    map_path = run_dir / "narration/audio-map.json"
    storyboard_path = run_dir / "storyboard.json"
    master_path = run_dir / "narration/master.wav"
    if _sha(map_path) != narration["sha256"] or _sha(storyboard_path) != script["sha256"]:
        raise ValueError("The audio map or storyboard changed after validation; rerun narration")
    audio_map = json.loads(map_path.read_text(encoding="utf-8"))
    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    if audio_map["storyboard_sha256"] != script["sha256"]:
        raise ValueError("The audio map belongs to a different storyboard")
    if _sha(master_path) != audio_map["master"]["sha256"] or _sha(master_path) != narration["master_sha256"]:
        raise ValueError("The normalized master changed after narration")
    info = sf.info(master_path)
    rate = audio_map["sample_rate"]
    total = audio_map["total_samples"]
    if rate != 24000 or info.samplerate != rate or info.channels != 1 or info.frames != total or total <= 0:
        raise ValueError("The normalized master does not match the 24 kHz mono sample map")
    if len(audio_map["scenes"]) != len(storyboard["scenes"]) or not audio_map["scenes"]:
        raise ValueError("The audio map does not cover every storyboard scene")

    scenes = []
    cues = []
    clock = 0
    for mapped, scripted in zip(audio_map["scenes"], storyboard["scenes"]):
        if mapped["id"] != scripted["id"] or mapped["start_sample"] != clock:
            raise ValueError("Audio scene order or start sample differs from the storyboard")
        units = mapped["units"]
        if not units:
            raise ValueError(f"Scene {mapped['id']} has no audio units")
        by_sentence: dict[str, list[str]] = {}
        expected_ids = [item["id"] for item in scripted["narration"]]
        actual_ids: list[str] = []
        for unit in units:
            start, end = unit["start_sample"], unit["end_sample"]
            pause = unit["pause_after_samples"]
            if (start != clock or not isinstance(end, int) or end <= start or
                    not isinstance(pause, int) or pause < 0 or unit["samples"] != end - start):
                raise ValueError(f"Invalid sample positions for audio unit {unit['id']}")
            unit_path = run_dir / unit["file"]
            if (unit_path.parent != run_dir / "narration/units" or
                    _sha(unit_path) != unit["sha256"] or
                    sf.info(unit_path).frames != unit["samples"]):
                raise ValueError(f"Audio unit {unit['id']} changed after narration")
            sentence_id = unit["sentence_id"]
            if not actual_ids or actual_ids[-1] != sentence_id:
                actual_ids.append(sentence_id)
            by_sentence.setdefault(sentence_id, []).append(unit["text"])
            begin_ms, end_ms = _milliseconds(start, rate), _milliseconds(end, rate)
            if end_ms <= begin_ms or (cues and begin_ms < cues[-1]["end_ms"]):
                raise ValueError(f"Audio unit {unit['id']} cannot form a nonoverlapping caption")
            cues.append({"id": unit["id"], "scene_id": mapped["id"], "sentence_id": sentence_id,
                         "start_sample": start, "end_sample": end, "start_ms": begin_ms,
                         "end_ms": end_ms, "text": _caption_text(unit["text"])})
            clock = end + pause
        if actual_ids != expected_ids:
            raise ValueError(f"Audio units in scene {mapped['id']} differ from the storyboard")
        for item in scripted["narration"]:
            spoken = " ".join(" ".join(by_sentence[item["id"]]).split())
            canonical = " ".join(item["text"].split())
            if spoken != canonical:
                raise ValueError(f"Audio unit text differs from canonical script: {item['id']}")
        if mapped["end_sample"] != clock:
            raise ValueError(f"Audio scene {mapped['id']} does not include its pauses")
        start_frame = (mapped["start_sample"] * FPS + rate - 1) // rate
        end_frame = (clock * FPS + rate - 1) // rate
        if (scenes and start_frame != scenes[-1]["end_frame"]) or end_frame <= start_frame:
            raise ValueError("Audio scenes cannot form contiguous video frames")
        scenes.append({"id": mapped["id"], "start_sample": mapped["start_sample"],
                       "end_sample": clock, "start_seconds": mapped["start_sample"] / rate,
                       "end_seconds": clock / rate, "start_frame": start_frame,
                       "end_frame": end_frame, "frames": end_frame - start_frame})
    if clock != total:
        raise ValueError("Audio map does not cover the normalized master")
    frame_count = scenes[-1]["end_frame"]
    record = {"schema": 1, "request_id": run_dir.name, "created_at": datetime.now(timezone.utc).isoformat(),
              "status": "passed", "sample_rate": rate, "audio_samples": total,
              "audio_duration_seconds": total / rate, "fps": FPS, "total_frames": frame_count,
              "video_duration_seconds": frame_count / FPS,
              "tail_padding_seconds": frame_count / FPS - total / rate,
              "audio_map_sha256": narration["sha256"], "storyboard_sha256": script["sha256"],
              "fingerprint": stage_fingerprint(root), "scenes": scenes, "captions": cues}
    srt = "".join(f"{index}\n{_timestamp(cue['start_ms'], vtt=False)} --> "
                  f"{_timestamp(cue['end_ms'], vtt=False)}\n{cue['text']}\n\n"
                  for index, cue in enumerate(cues, 1))
    vtt = "WEBVTT\n\n" + "".join(f"{_timestamp(cue['start_ms'], vtt=True)} --> "
                                  f"{_timestamp(cue['end_ms'], vtt=True)}\n{cue['text']}\n\n" for cue in cues)
    data = (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode()
    write_atomic(root, run_dir.relative_to(root) / TIMELINE, data, label="Request")
    write_atomic(root, run_dir.relative_to(root) / SRT, srt.encode(), label="Request")
    write_atomic(root, run_dir.relative_to(root) / VTT, vtt.encode(), label="Request")
    manifest["status"] = "timing_ready"
    invalidate_after(manifest, "timing")
    manifest["timing"] = {"status": "passed", "record": TIMELINE, "sha256": hashlib.sha256(data).hexdigest(),
                          "srt": SRT, "srt_sha256": hashlib.sha256(srt.encode()).hexdigest(),
                          "vtt": VTT, "vtt_sha256": hashlib.sha256(vtt.encode()).hexdigest(),
                          "frames": frame_count, "captions": len(cues),
                          "duration_seconds": record["video_duration_seconds"],
                          "fingerprint": record["fingerprint"]}
    write_atomic(root, run_dir.relative_to(root) / "manifest.json",
                 (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode(), label="Request")
    return manifest["timing"]
