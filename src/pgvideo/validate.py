"""Validate a rendered request and publish its local delivery package."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .paths import project_directory, write_atomic
from .reuse import register, stage_fingerprint
from .stages import invalidate_after
from .timing import _timestamp


class NeedsReview(ValueError):
    """Media is valid, but measured presentation quality needs attention."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(args: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise ValueError(f"Media check failed ({Path(args[0]).name}): {result.stderr[-1600:]}")
    return result


def _loudness(ffmpeg: Path, video: Path) -> dict:
    result = _run([str(ffmpeg), "-hide_banner", "-nostdin", "-i", str(video), "-map", "0:a:0",
                   "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"])
    matches = re.findall(r"\{\s*\"input_i\".*?\}", result.stderr, re.S)
    if not matches:
        raise ValueError("FFmpeg did not return audio loudness measurements")
    values = json.loads(matches[-1])
    return {"integrated_lufs": float(values["input_i"]),
            "true_peak_dbtp": float(values["input_tp"])}


def _stream_end(stream: dict) -> float:
    """Read an end time without substituting the container's duration for either track."""
    if "duration" in stream:
        end = float(stream.get("start_time", 0)) + float(stream["duration"])
    else:
        # FFmpeg's Matroska muxer writes the last timestamp + packet duration
        # in DURATION, already relative to the container origin.
        tag = stream.get("tags", {}).get("DURATION", "")
        if not re.fullmatch(r"\d+:\d{2}:\d{2}(?:\.\d+)?", tag):
            raise ValueError("Encoded stream has no valid duration or DURATION tag")
        hours, minutes, seconds = tag.split(":")
        if int(minutes) >= 60 or float(seconds) >= 60:
            raise ValueError("Encoded stream has an invalid DURATION tag")
        end = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    if not math.isfinite(end) or end <= 0:
        raise ValueError("Encoded stream end time must be finite and positive")
    return end


def _captions(run_dir: Path, timeline: dict, audio_map: dict, storyboard: dict) -> dict:
    scenes, cues = timeline["scenes"], timeline["captions"]
    if not scenes or [s["id"] for s in scenes] != [s["id"] for s in storyboard["scenes"]]:
        raise ValueError("Timeline does not cover every storyboard scene")
    if [s["id"] for s in scenes] != [s["id"] for s in audio_map["scenes"]]:
        raise ValueError("Timeline and audio map scene order differ")
    expected_units = [u for s in audio_map["scenes"] for u in s["units"]]
    if len(cues) != len(expected_units) or not cues:
        raise ValueError("Captions do not cover every audio unit")
    previous = 0
    for cue, unit in zip(cues, expected_units):
        if (cue["id"] != unit["id"] or cue["sentence_id"] != unit["sentence_id"] or
                cue["start_sample"] != unit["start_sample"] or cue["end_sample"] != unit["end_sample"] or
                cue["start_ms"] < previous or cue["end_ms"] <= cue["start_ms"] or
                not cue["text"].strip()):
            raise ValueError(f"Caption order or audio coverage is invalid at {unit['id']}")
        previous = cue["end_ms"]
    if cues[-1]["scene_id"] != scenes[-1]["id"] or cues[-1]["end_sample"] > scenes[-1]["end_sample"]:
        raise ValueError("The last spoken sentence is outside the final scene")
    srt = "".join(f"{i}\n{_timestamp(c['start_ms'], vtt=False)} --> "
                  f"{_timestamp(c['end_ms'], vtt=False)}\n{c['text']}\n\n" for i, c in enumerate(cues, 1))
    vtt = "WEBVTT\n\n" + "".join(f"{_timestamp(c['start_ms'], vtt=True)} --> "
                            f"{_timestamp(c['end_ms'], vtt=True)}\n{c['text']}\n\n" for c in cues)
    if (run_dir / "captions.srt").read_text() != srt or (run_dir / "captions.vtt").read_text() != vtt:
        raise ValueError("Caption files differ from the validated timeline")
    return {"cues": len(cues), "scenes": len(scenes), "last_unit": cues[-1]["id"],
            "last_caption_end_seconds": cues[-1]["end_ms"] / 1000}


def validate_video(root: Path, run_dir: Path) -> dict:
    """Check the complete draft and atomically publish one request's deliverables."""
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    invalidate_after(manifest, "validation")
    report: dict = {"schema": 2, "request_id": run_dir.name,
                    "created_at": datetime.now(timezone.utc).isoformat(), "status": "failed", "checks": {}}
    try:
        for stage in ("render", "timing", "narration", "script"):
            if (manifest.get(stage) or {}).get("status") != "passed":
                raise ValueError(f"The {stage} stage must pass before validation")
        render = json.loads((run_dir / "render.json").read_text())
        timeline = json.loads((run_dir / "timeline.json").read_text())
        audio_map = json.loads((run_dir / "narration/audio-map.json").read_text())
        storyboard = json.loads((run_dir / "storyboard.json").read_text())
        draft = run_dir / "render/draft.webm"
        checks = (("render.json", manifest["render"]["sha256"]),
                  ("render/draft.webm", manifest["render"]["draft_sha256"]),
                  ("timeline.json", manifest["timing"]["sha256"]),
                  ("narration/audio-map.json", manifest["narration"]["sha256"]),
                  ("storyboard.json", manifest["script"]["sha256"]),
                  ("references.md", render["references_sha256"]),
                  ("captions.srt", manifest["timing"]["srt_sha256"]),
                  ("captions.vtt", manifest["timing"]["vtt_sha256"]))
        for name, digest in checks:
            if _sha(run_dir / name) != digest:
                raise ValueError(f"Validated input changed: {name}")
        if render["sha256"] != _sha(draft) or render["frames"] != timeline["total_frames"]:
            raise ValueError("Render record does not match the draft or timeline")
        request = json.loads((run_dir / "request.json").read_text())
        ffmpeg, ffprobe = root / ".runtime/bin/ffmpeg", root / ".runtime/bin/ffprobe"
        probe = json.loads(_run([str(ffprobe), "-v", "error", "-count_frames", "-show_streams",
                                 "-show_format", "-of", "json", str(draft)]).stdout)
        streams = probe["streams"]
        video = [s for s in streams if s["codec_type"] == "video"]
        sound = [s for s in streams if s["codec_type"] == "audio"]
        if len(streams) != 2 or len(video) != 1 or len(sound) != 1:
            raise ValueError("WebM must have exactly one video and one audio stream")
        video, sound = video[0], sound[0]
        width, height = request["settings"]["width"], request["settings"]["height"]
        if ("webm" not in probe["format"]["format_name"].split(",") or
                (video["codec_name"], video["pix_fmt"], video["width"], video["height"],
                 video["avg_frame_rate"], int(video.get("nb_read_frames", -1))) !=
                ("av1", "yuv420p", width, height, "30/1", timeline["total_frames"]) or
                (sound["codec_name"], sound["sample_rate"], sound["channels"]) !=
                ("opus", "48000", 1)):
            raise ValueError("WebM container, codecs, dimensions, rate, or frame count differ from the request")
        video_end = _stream_end(video)
        audio_end = _stream_end(sound)
        duration = float(probe["format"]["duration"])
        if (abs(video_end - audio_end) > 0.100 or
                abs(video_end - timeline["video_duration_seconds"]) > 0.050 or
                abs(audio_end - timeline["audio_duration_seconds"]) > 0.100 or
                abs(duration - max(video_end, audio_end)) > 0.050):
            raise ValueError("Audio, video, and timeline end times differ beyond 100 ms")
        report["checks"]["media"] = {"container": "webm", "video_codec": "av1", "audio_codec": "opus",
                                      "width": width, "height": height, "fps": 30,
                                      "frames": timeline["total_frames"], "duration_seconds": duration,
                                      "video_end_seconds": video_end, "audio_end_seconds": audio_end,
                                      "end_difference_seconds": abs(video_end - audio_end)}
        # Decode both streams, including the last frame and the last Opus packet.
        _run([str(ffmpeg), "-v", "error", "-xerror", "-nostdin", "-i", str(draft),
              "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"])
        report["checks"]["complete_decode"] = "passed"
        report["checks"]["captions"] = _captions(run_dir, timeline, audio_map, storyboard)
        # Decode audio to a bounded project-local file for sample-level checks.
        pcm = run_dir / "render/validation-audio.f32"
        try:
            _run([str(ffmpeg), "-v", "error", "-nostdin", "-y", "-i", str(draft),
                  "-map", "0:a:0", "-f", "f32le", "-acodec", "pcm_f32le", "-ar", "24000",
                  "-ac", "1", str(pcm)])
            samples = np.fromfile(pcm, dtype="<f4")
            if abs(len(samples) - audio_map["total_samples"]) > 2400:
                raise ValueError("Decoded audio length differs from the audio map by over 100 ms")
            quiet = []
            longest = 0.0
            for scene in audio_map["scenes"]:
                for unit in scene["units"]:
                    clip = samples[unit["start_sample"]:unit["end_sample"]]
                    if not len(clip) or not np.isfinite(clip).all():
                        raise ValueError(f"Missing or invalid decoded audio for {unit['id']}")
                    rms = float(np.sqrt(np.mean(np.square(clip.astype(np.float64)))))
                    if rms < 10 ** (-50 / 20):
                        quiet.append(unit["id"])
                    # A sustained gap inside a spoken unit is not an intentional scene pause.
                    window, stride = 2 * 24000, 12000
                    for start in range(0, max(0, len(clip) - window + 1), stride):
                        piece = clip[start:start + window].astype(np.float64)
                        if float(np.sqrt(np.mean(np.square(piece)))) < 10 ** (-50 / 20):
                            raise NeedsReview(f"Unintended silence over 2 seconds in {unit['id']}")
                    longest = max(longest, unit["pause_after_samples"] / audio_map["sample_rate"])
            if quiet:
                raise NeedsReview(f"Spoken audio units are silent or too quiet: {', '.join(quiet[:5])}")
            if longest > 2.0:
                raise NeedsReview(f"Unintended long pause of {longest:.2f} seconds in the audio map")
            report["checks"]["audio_units"] = {"count": sum(len(s["units"]) for s in audio_map["scenes"]),
                                                 "silent_units": 0, "longest_planned_pause_seconds": longest,
                                                 "last_unit": audio_map["scenes"][-1]["units"][-1]["id"]}
        finally:
            pcm.unlink(missing_ok=True)
        loudness = _loudness(ffmpeg, draft)
        if (not math.isfinite(loudness["integrated_lufs"]) or
                not -23 <= loudness["integrated_lufs"] <= -10 or
                not math.isfinite(loudness["true_peak_dbtp"]) or loudness["true_peak_dbtp"] > -0.5):
            raise NeedsReview(f"Encoded audio loudness is outside delivery limits: {loudness}")
        report["checks"]["loudness"] = loudness
        output_base = project_directory(root, Path(request["settings"]["output_dir"]), label="Output")
        destination = project_directory(root, output_base / run_dir.name, label="Output")
        destination.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", Path(storyboard["document"]["path"]).stem.lower()).strip("-") or "video"
        files = {f"{slug}.webm": draft, "transcript.md": run_dir / "script.md",
                 "captions.srt": run_dir / "captions.srt", "captions.vtt": run_dir / "captions.vtt",
                 "references.md": run_dir / "references.md"}
        for name, source in files.items():
            target = destination / name
            temporary = destination / f".{name}.tmp"
            if target.is_symlink() or temporary.is_symlink():
                raise ValueError(f"Delivery path is a symlink: {name}")
            shutil.copyfile(source, temporary)
            temporary.replace(target)
        report["status"] = "completed"
        report["delivery"] = {"directory": str(destination), "files": {name: _sha(destination / name)
                                                                   for name in files}}
        report["document"] = {"path": storyboard["document"]["path"], "url": storyboard["document"].get("url"),
                              "postgresql_version": storyboard["document"]["version"]}
        report["duration_seconds"] = duration
        report["fingerprint"] = stage_fingerprint(root)
        if manifest["render"].get("reused_from"):
            # The draft came from an earlier request with the same inputs; every check above ran on it here.
            report["reused_from"] = manifest["render"]["reused_from"]
        write_atomic(root, run_dir.relative_to(root) / "quality-report.json",
                     (json.dumps(report, indent=2) + "\n").encode(), label="Request")
        shutil.copyfile(run_dir / "quality-report.json", destination / "quality-report.json")
        manifest["status"] = "completed"
        manifest["validation"] = {"status": report["status"], "record": "quality-report.json",
                                  "sha256": _sha(run_dir / "quality-report.json"),
                                  "output": str(destination.relative_to(root)), "video": f"{slug}.webm",
                                  "duration_seconds": duration}
        manifest["reuse"] = register(root, run_dir, manifest, storyboard=storyboard, audio_map=audio_map,
                                     render=render)
        write_atomic(root, run_dir.relative_to(root) / "manifest.json",
                     (json.dumps(manifest, indent=2) + "\n").encode(), label="Request")
        shutil.copyfile(run_dir / "manifest.json", destination / "manifest.json")
        return manifest["validation"]
    except Exception as error:
        report["status"] = "needs_review" if isinstance(error, NeedsReview) else "failed"
        report["error"] = str(error)
        write_atomic(root, run_dir.relative_to(root) / "quality-report.json",
                     (json.dumps(report, indent=2) + "\n").encode(), label="Request")
        manifest["status"] = report["status"]
        manifest["validation"] = {"status": report["status"], "record": "quality-report.json",
                                  "error": str(error)}
        write_atomic(root, run_dir.relative_to(root) / "manifest.json",
                     (json.dumps(manifest, indent=2) + "\n").encode(), label="Request")
        raise
