"""Synthesize a storyboard with local Kokoro and preserve sample accurate unit positions."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import soundfile as sf

from .assets import _checked_path, local_kokoro, local_selection
from .reuse import stage_fingerprint
from .sources import write_atomic
from .speech import Pronunciation
from .stages import invalidate_after

RATE = 24000
UNIT_WORDS = 28
SENTENCE_PAUSE = 0.35
SCENE_PAUSE = 0.8
MASTER = "narration/master.wav"
RAW_MASTER = "narration/master-raw.wav"
MAP = "narration/audio-map.json"
REPORT = "narration/narration-report.md"
# Unit WAVs keyed by their exact TTS text and the synthesis provenance.
CACHE = Path("cache/narration")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _units(item: dict, pronunciation: Pronunciation) -> list[tuple[str, str]]:
    """Split dictionary text at clauses; keep manually tuned TTS intact."""
    if item["tts_source"] == "manual":
        return [(item["text"], item["tts"])]
    text = item["text"].strip()
    clauses = []
    start = 0
    code = False
    for index, character in enumerate(text):
        if character == "`":
            code = not code
        if not code and character in ",;:" and index + 1 < len(text) and text[index + 1].isspace():
            clauses.append(text[start:index + 1].strip())
            start = index + 1
    clauses.append(text[start:].strip())
    result: list[str] = []
    current = ""
    for clause in clauses:
        if current and len((current + " " + clause).split()) > UNIT_WORDS:
            result.append(current)
            current = clause
        else:
            current = (current + " " + clause).strip()
    if current:
        result.append(current)
    # Long clauses without punctuation still need short subtitle units.
    split: list[str] = []
    for part in result:
        # Keep punctuation attached to an inline-code token when splitting.
        tokens = re.findall(r"`[^`]+`\S*|\S+", part)
        split.extend(" ".join(tokens[i:i + UNIT_WORDS]) for i in range(0, len(tokens), UNIT_WORDS))
    if len(split) == 1:
        return [(text, item["tts"])]
    return [(part, pronunciation.speak(part)) for part in split]


def _audio(path: Path) -> np.ndarray:
    data, rate = sf.read(path, dtype="float32", always_2d=False)
    if rate != RATE or data.ndim != 1 or not len(data) or not np.isfinite(data).all():
        raise ValueError(f"Invalid 24 kHz mono Kokoro audio: {path}")
    return data


def _synthesize(pipeline, voice: str, text: str, speed: float, path: Path) -> int:
    for attempt in range(2):
        chunks = []
        for chunk in pipeline(text, voice=voice, speed=speed):
            if chunk.audio is None:
                raise ValueError(f"Kokoro returned an empty chunk for {text[:80]!r}")
            audio = np.asarray(chunk.audio, dtype=np.float32).reshape(-1)
            if not len(audio) or not np.isfinite(audio).all():
                raise ValueError(f"Kokoro returned invalid audio for {text[:80]!r}")
            chunks.append(audio)
        if not chunks:
            raise ValueError(f"Kokoro returned no audio for {text[:80]!r}")
        complete = np.concatenate(chunks)
        if np.max(np.abs(complete)) >= 0.999:
            if attempt == 0:
                continue
            raise ValueError(f"Kokoro audio clips for {text[:80]!r}; edit the TTS text and retry")
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(path, complete, RATE, subtype="PCM_24")
        return len(complete)
    raise AssertionError("unreachable")


def _normalize(root: Path, raw: Path, target: Path, samples: int, loudness: float, peak: float) -> dict:
    ffmpeg = root / ".runtime/bin/ffmpeg"
    base = [str(ffmpeg), "-hide_banner", "-nostdin", "-i", str(raw), "-vn"]
    first = subprocess.run(base + ["-af", f"loudnorm=I={loudness}:TP={peak}:LRA=11:print_format=json",
                                   "-f", "null", "-"], capture_output=True, text=True)
    if first.returncode:
        raise ValueError(f"FFmpeg loudness measurement failed: {first.stderr[-1500:]}")
    match = re.search(r"\{\s*\"input_i\".*?\}", first.stderr, re.DOTALL)
    if not match:
        raise ValueError("FFmpeg did not report first-pass loudness measurements")
    stats = json.loads(match.group())
    required = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    if any(key not in stats or not np.isfinite(float(stats[key])) for key in required):
        raise ValueError("FFmpeg returned invalid loudness measurements")
    filter_spec = (f"loudnorm=I={loudness}:TP={peak}:LRA=11:"
                   f"measured_I={stats['input_i']}:measured_TP={stats['input_tp']}:"
                   f"measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}:"
                   f"offset={stats['target_offset']}:linear=true:print_format=json,"
                   f"aresample={RATE},atrim=end_sample={samples},apad=whole_len={samples}")
    temporary = target.with_suffix(".tmp.wav")
    second = subprocess.run(base + ["-af", filter_spec, "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s24le",
                                    "-y", str(temporary)], capture_output=True, text=True)
    if second.returncode:
        raise ValueError(f"FFmpeg loudness normalization failed: {second.stderr[-1500:]}")
    if sf.info(temporary).frames != samples:
        raise ValueError("Normalized master has a different sample count")
    temporary.replace(target)
    output_match = re.search(r"\{\s*\"input_i\".*?\}", second.stderr, re.DOTALL)
    return {"target_lufs": loudness, "target_true_peak_dbtp": peak, "first_pass": stats,
            "second_pass": json.loads(output_match.group()) if output_match else {}}


def create_narration(root: Path, run_dir: Path, *, loudness: float = -16.0, peak: float = -1.5,
                     refresh: set[str] | None = None) -> dict:
    """Write unit WAVs, a normalized master, and a sample map for a passed storyboard."""
    try:
        return _create_narration(root, run_dir, loudness=loudness, peak=peak, refresh=refresh)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        manifest_path = run_dir / "manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["status"] = "failed"
            invalidate_after(manifest, "narration")
            manifest["narration"] = {"status": "failed", "error": str(error)}
            write_atomic(root, run_dir.relative_to(root) / "manifest.json",
                         (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode(), label="Request")
        raise


def _create_narration(root: Path, run_dir: Path, *, loudness: float, peak: float,
                      refresh: set[str] | None) -> dict:
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("script", {}).get("status") != "passed":
        raise ValueError("The script must pass before narration; review script.md")
    storyboard_path = run_dir / "storyboard.json"
    if _sha(storyboard_path) != manifest["script"]["sha256"]:
        raise ValueError("storyboard.json changed after validation; rerun the script stage")
    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    if not storyboard.get("scenes") or any(not scene.get("narration") for scene in storyboard["scenes"]):
        raise ValueError("Every storyboard scene must contain narration")
    pronunciation_path = root / storyboard["pronunciation"]["file"]
    if _sha(pronunciation_path) != storyboard["pronunciation"]["sha256"]:
        raise ValueError("The pronunciation dictionary changed; rerun the script stage")
    request = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
    settings = request["settings"]
    _, assets = local_selection(language=settings["language"], voice=settings["voice"])
    for name in ("model", "config", "voice"):
        _checked_path(root, assets[name])
    provenance = {"model": assets["model"]["sha256"], "config": assets["config"]["sha256"],
                  "voice_asset": assets["voice"]["sha256"],
                  "kokoro": importlib.metadata.version("kokoro"),
                  "misaki": importlib.metadata.version("misaki"),
                  "torch": importlib.metadata.version("torch"),
                  "pronunciation": storyboard["pronunciation"]["sha256"],
                  "voice": settings["voice"], "language": settings["language"], "speed": settings["speed"]}
    pronunciation = Pronunciation.load(root)
    available = {f"{item['id']}.u{i}" for scene in storyboard["scenes"] for item in scene["narration"]
                 for i in range(1, len(_units(item, pronunciation)) + 1)}
    available.update(item["id"] for scene in storyboard["scenes"] for item in scene["narration"])
    unknown = (refresh or set()) - available
    if unknown:
        raise ValueError(f"Unknown narration unit(s): {', '.join(sorted(unknown))}")
    cache = root / CACHE
    (run_dir / "narration/units").mkdir(parents=True, exist_ok=True)
    scenes = []
    clock = 0
    pipeline = voice = None
    reused = created = 0
    for scene_index, scene in enumerate(storyboard["scenes"]):
        scene_start = clock
        items = []
        for sentence_index, item in enumerate(scene["narration"]):
            parts = _units(item, pronunciation)
            for unit_index, (display, tts) in enumerate(parts, 1):
                unit_id = f"{item['id']}.u{unit_index}"
                key = hashlib.sha256(json.dumps({"text": tts, **provenance}, sort_keys=True).encode()).hexdigest()
                cache_path = cache / key[:2] / f"{key}.wav"
                if refresh and (unit_id in refresh or item["id"] in refresh):
                    cache_path.unlink(missing_ok=True)
                try:
                    frames = len(_audio(cache_path)) if cache_path.is_file() else 0
                except ValueError:
                    cache_path.unlink(missing_ok=True)
                    frames = 0
                if not frames:
                    if pipeline is None:
                        pipeline, voice = local_kokoro(language=settings["language"], voice=settings["voice"])
                    frames = _synthesize(pipeline, voice, tts, settings["speed"], cache_path)
                    created += 1
                else:
                    reused += 1
                unit_path = run_dir / "narration/units" / f"{unit_id}.wav"
                unit_path.write_bytes(cache_path.read_bytes())
                items.append({"id": unit_id, "sentence_id": item["id"], "text": display, "tts": tts,
                              "file": unit_path.relative_to(run_dir).as_posix(), "sha256": _sha(unit_path),
                              "cache_key": key, "start_sample": clock, "end_sample": clock + frames,
                              "samples": frames})
                clock += frames
                if unit_index == len(parts):
                    pause = SCENE_PAUSE if sentence_index == len(scene["narration"]) - 1 else SENTENCE_PAUSE
                    if scene_index == len(storyboard["scenes"]) - 1:
                        pause = 0
                    pause_samples = round(pause * RATE)
                    items[-1]["pause_after_samples"] = pause_samples
                    clock += pause_samples
                else:
                    items[-1]["pause_after_samples"] = 0
        scenes.append({"id": scene["id"], "start_sample": scene_start, "end_sample": clock, "units": items})
    if not clock:
        raise ValueError("The storyboard contains no narration audio")
    raw = run_dir / RAW_MASTER
    with sf.SoundFile(raw, mode="w", samplerate=RATE, channels=1, subtype="PCM_24") as output:
        for scene in scenes:
            for unit in scene["units"]:
                output.write(_audio(run_dir / unit["file"]))
                if unit["pause_after_samples"]:
                    output.write(np.zeros(unit["pause_after_samples"], dtype=np.float32))
    if sf.info(raw).frames != clock:
        raise ValueError("The assembled master does not match the unit sample map")
    master = run_dir / MASTER
    normalization = _normalize(root, raw, master, clock, loudness, peak)
    record = {"schema": 1, "request_id": run_dir.name, "created_at": datetime.now(timezone.utc).isoformat(),
              "status": "passed", "sample_rate": RATE, "total_samples": clock,
              "duration_seconds": round(clock / RATE, 3), "storyboard_sha256": _sha(storyboard_path),
              "pronunciation_sha256": _sha(pronunciation_path), "settings": settings,
              "assets": provenance, "normalization": normalization, "scenes": scenes,
              "master": {"file": MASTER, "sha256": _sha(master)},
              "raw_master": {"file": RAW_MASTER, "sha256": _sha(raw)},
              "cache": {"created": created, "reused": reused}, "fingerprint": stage_fingerprint(root)}
    return publish(root, run_dir, manifest, record)


def publish(root: Path, run_dir: Path, manifest: dict, record: dict) -> dict:
    """Write the audio map and report, and record them as the request's narration stage."""
    data = (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode()
    write_atomic(root, run_dir.relative_to(root) / MAP, data, label="Request")
    units = sum(len(s["units"]) for s in record["scenes"])
    reused_from = (record.get("reused_from") or {}).get("request_id")
    normalization = record["normalization"]
    report = (f"# Narration report\n\nStatus: passed\n\n"
              f"{len(record['scenes'])} scenes, {units} units, "
              f"{record['total_samples'] / RATE:.2f} seconds at {RATE} Hz.\n\n"
              + (f"Reused the validated narration of request {reused_from}, whose inputs match.\n\n"
                 if reused_from else "") +
              f"Cached units reused: {record['cache']['reused']}; synthesized: {record['cache']['created']}.\n\n"
              f"Target: {normalization['target_lufs']} LUFS, {normalization['target_true_peak_dbtp']} dBTP. "
              "Review technical pronunciations by listening; "
              "edit pronunciation/en.yaml or a scene's TTS text and rerun the script and narration stages.\n")
    write_atomic(root, run_dir.relative_to(root) / REPORT, report.encode(), label="Request")
    manifest["status"] = "narration_ready"
    invalidate_after(manifest, "narration")
    manifest["narration"] = {"status": "passed", "record": MAP, "sha256": hashlib.sha256(data).hexdigest(),
                              "master": MASTER, "master_sha256": record["master"]["sha256"],
                              "report": REPORT, "duration_seconds": record["duration_seconds"],
                              "units": units, "fingerprint": record.get("fingerprint")}
    if reused_from:
        manifest["narration"]["reused_from"] = reused_from
    write_atomic(root, run_dir.relative_to(root) / "manifest.json",
                 (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode(), label="Request")
    return manifest["narration"]
