"""Integration check: real Kokoro audio, from its chunks to the delivered WebM.

A three-scene storyboard is narrated with the local Kokoro model, timed, rendered,
and validated. One hand-written unit is longer than Kokoro's 510-phoneme limit, so
the model returns it in several chunks. The checks follow every sample: chunks to
unit WAVs, units and pauses to the master, the master to caption cues and scene
frames, and the master to the WebM's decoded audio and video, where dropped audio or
timing drift would show.
"""

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

from pgvideo.assets import local_kokoro
from pgvideo.narration import RATE, SCENE_PAUSE, SENTENCE_PAUSE, create_narration
from pgvideo.render import create_render
from pgvideo.timing import FPS, create_timing
from pgvideo.validate import validate_video

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / ".runtime/bin/ffmpeg"
LONG = ("Kokoro splits long input into chunks of at most five hundred and ten phonemes. This unit keeps a hand "
        "written text in one piece, so the model must return several chunks for it. Every chunk has to arrive in "
        "order, and none of them may be dropped. The narration stage joins the chunks into one lossless file. The "
        "timing stage then places the next caption after the whole unit and its pause. If a chunk went missing, "
        "the unit would be shorter than the audio the model produced, and every later caption would start too "
        "early. The video would drift away from its subtitles. This paragraph is long enough to need at least two "
        "chunks.")
CLAUSES = ("The first clause of this sentence is long enough to stand as its own spoken unit on screen, "
           "and the second clause follows it after no pause at all because both clauses belong to one sentence.")


def save(path: Path, value) -> str:
    data = (json.dumps(value, indent=2) + "\n").encode()
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def sentence(identifier: str, text: str, *, manual: bool = False) -> dict:
    return {"id": identifier, "text": text, "tts": text, "tts_source": "manual" if manual else "dictionary"}


class Recorder:
    """Wrap the real Kokoro pipeline and keep a copy of every chunk it yields, in order."""

    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.calls: list[tuple[str, list[np.ndarray]]] = []

    def __call__(self, text, voice, speed):
        chunks: list[np.ndarray] = []
        self.calls.append((text, chunks))
        for result in self.pipeline(text, voice=voice, speed=speed):
            chunks.append(np.asarray(result.audio, dtype=np.float32).reshape(-1).copy())
            yield result

    def chunks(self, text: str) -> list[np.ndarray]:
        # A retry after clipping synthesizes the same text again; the last call wrote the file.
        return [chunks for called, chunks in self.calls if called == text][-1]


def rms_db(samples: np.ndarray) -> float:
    return 20 * np.log10(max(float(np.sqrt(np.mean(np.square(samples.astype(np.float64))))), 1e-12))


def lag(reference: np.ndarray, signal: np.ndarray, start: int, *, window: int = RATE // 2,
        search: int = RATE // 20) -> int:
    """Return the offset in samples at which `signal` best matches `reference` around `start`."""
    piece = reference[start:start + window].astype(np.float64)
    best, offset = -np.inf, 0
    for shift in range(-search, search + 1):
        if start + shift < 0 or start + shift + window > len(signal):
            continue
        other = signal[start + shift:start + shift + window].astype(np.float64)
        score = float(np.dot(piece, other) / (np.linalg.norm(piece) * np.linalg.norm(other) + 1e-12))
        if score > best:
            best, offset = score, shift
    return offset


class KokoroIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pipeline, cls.voice = local_kokoro()
        cls.recorder = Recorder(pipeline)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pgvideo-integration-", dir=ROOT / ".runtime/tmp")
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.run_dir = base / "runs" / "integration"
        self.run_dir.mkdir(parents=True)
        (base / "output").mkdir()
        # A fresh unit cache inside the fixture makes Kokoro synthesize every unit.
        self.enterContext(patch("pgvideo.narration.CACHE", base.relative_to(ROOT) / "cache"))
        self.enterContext(patch("pgvideo.narration.local_kokoro", return_value=(self.recorder, self.voice)))
        document = {"path": "wiki/v18/integration.md", "version": 18}
        pronunciation = ROOT / "pronunciation/en.yaml"
        self.storyboard = {"title": "Integration check", "document": document, "pronunciation": {
            "file": "pronunciation/en.yaml", "sha256": hashlib.sha256(pronunciation.read_bytes()).hexdigest(),
            "language": "a"}, "scenes": [
            {"id": "s01-title", "part": "opening", "title": "Integration check",
             "screen": {"layout": "title", "heading": "Integration check", "lines": ["PostgreSQL 18"]},
             "narration": [sentence("s01-title.n1", "This check narrates three scenes.")]},
            {"id": "s02-units", "part": "mechanism", "title": "Units and chunks",
             "screen": {"layout": "bullets", "heading": "Units and chunks",
                        "lines": ["Clauses become units", "Long hand-written text becomes chunks"]},
             "narration": [sentence("s02-units.n1", CLAUSES), sentence("s02-units.n2", LONG, manual=True)]},
            {"id": "s03-credits", "part": "credits", "title": "Sources",
             "screen": {"layout": "credits", "heading": "Sources", "lines": ["Integration fixture"]},
             "narration": [sentence("s03-credits.n1", "The final scene ends the video.")]},
        ]}
        script = save(self.run_dir / "storyboard.json", self.storyboard)
        save(self.run_dir / "request.json", {
            "settings": {"voice": "af_heart", "language": "a", "speed": 1.0, "width": 640, "height": 360,
                         "output_dir": str(base / "output")}})
        save(self.run_dir / "manifest.json", {"script": {"status": "passed", "sha256": script}})
        (self.run_dir / "script.md").write_text("# Integration check\n")

    def test_chunks_pauses_captions_and_the_last_scene_reach_the_webm(self):
        create_narration(ROOT, self.run_dir)
        audio_map = json.loads((self.run_dir / "narration/audio-map.json").read_text())
        units = [unit for scene in audio_map["scenes"] for unit in scene["units"]]
        self.assertEqual([unit["id"] for unit in units], [
            "s01-title.n1.u1", "s02-units.n1.u1", "s02-units.n1.u2", "s02-units.n2.u1", "s03-credits.n1.u1"])

        # Every chunk Kokoro returned is in its unit's lossless WAV, in order.
        for unit in units:
            chunks = self.recorder.chunks(unit["tts"])
            audio, rate = sf.read(self.run_dir / unit["file"], dtype="float32")
            with self.subTest(unit=unit["id"]):
                self.assertEqual((rate, len(audio), unit["samples"]), (RATE, sum(map(len, chunks)), len(audio)))
                np.testing.assert_allclose(audio, np.concatenate(chunks), atol=2 ** -22)
        self.assertGreaterEqual(len(self.recorder.chunks(LONG)), 2, "the long unit must span several chunks")

        # Pauses: none inside a sentence, a sentence pause, a scene pause, and none after the last unit.
        pauses = [unit["pause_after_samples"] for unit in units]
        self.assertEqual(pauses, [round(SCENE_PAUSE * RATE), 0, round(SENTENCE_PAUSE * RATE),
                                  round(SCENE_PAUSE * RATE), 0])
        for previous, unit in zip(units, units[1:]):
            self.assertEqual(unit["start_sample"], previous["end_sample"] + previous["pause_after_samples"])
        total = units[-1]["end_sample"]
        self.assertEqual(audio_map["total_samples"], total)
        master, _ = sf.read(self.run_dir / "narration/master.wav", dtype="float32")
        raw, _ = sf.read(self.run_dir / "narration/master-raw.wav", dtype="float32")
        self.assertEqual((len(master), len(raw)), (total, total))
        for unit in units:
            with self.subTest(unit=unit["id"]):
                self.assertGreater(rms_db(master[unit["start_sample"]:unit["end_sample"]]), -40)
                gap = unit["pause_after_samples"]
                if gap:
                    middle = master[unit["end_sample"] + gap // 10:unit["end_sample"] + gap - gap // 10]
                    self.assertLess(float(np.max(np.abs(middle))), 1e-3, "a pause must stay silent")
                # Loudness normalization keeps every unit where the sample map puts it.
                self.assertEqual(lag(raw, master, unit["start_sample"]), 0)

        create_timing(ROOT, self.run_dir)
        timeline = json.loads((self.run_dir / "timeline.json").read_text())
        cues = timeline["captions"]
        self.assertEqual([cue["id"] for cue in cues], [unit["id"] for unit in units])
        for cue, unit in zip(cues, units):
            self.assertEqual((cue["start_sample"], cue["end_sample"]), (unit["start_sample"], unit["end_sample"]))
            self.assertEqual((cue["start_ms"], cue["end_ms"]),
                             ((unit["start_sample"] * 1000 + RATE // 2) // RATE,
                              (unit["end_sample"] * 1000 + RATE // 2) // RATE))
        self.assertEqual(cues[2]["start_ms"], cues[1]["end_ms"], "units of one sentence are contiguous")
        self.assertEqual(cues[3]["start_ms"] - cues[2]["end_ms"], round(SENTENCE_PAUSE * 1000))
        frames = -(-total * FPS // RATE)
        scenes = timeline["scenes"]
        self.assertEqual((timeline["total_frames"], scenes[-1]["end_frame"], cues[-1]["scene_id"]),
                         (frames, frames, "s03-credits"))
        self.assertEqual([scene["start_frame"] for scene in scenes],
                         [-(-scene["start_sample"] * FPS // RATE) for scene in scenes])
        srt = (self.run_dir / "captions.srt").read_text()
        self.assertTrue(srt.rstrip().endswith("The final scene ends the video."))

        create_render(ROOT, self.run_dir)
        result = validate_video(ROOT, self.run_dir)
        self.assertEqual(result["status"], "completed")
        quality = json.loads((self.run_dir / "quality-report.json").read_text())
        self.assertLessEqual(quality["checks"]["media"]["end_difference_seconds"], 0.1)
        self.assertEqual(quality["checks"]["audio_units"]["last_unit"], "s03-credits.n1.u1")

        # The WebM's decoded audio lines up with the master from the first unit to the last.
        video = self.run_dir / "render/draft.webm"
        decoded = np.frombuffer(subprocess.run(
            [str(FFMPEG), "-v", "error", "-nostdin", "-i", str(video), "-map", "0:a:0", "-f", "f32le",
             "-ac", "1", "-ar", str(RATE), "-"], capture_output=True, check=True).stdout, dtype="<f4")
        self.assertLessEqual(abs(len(decoded) - total), RATE // 10)
        second_chunk = units[3]["start_sample"] + len(self.recorder.chunks(LONG)[0])
        for name, start in (("first unit", units[0]["start_sample"]), ("second chunk", second_chunk),
                            ("last unit", units[-1]["start_sample"])):
            with self.subTest(position=name):
                self.assertLessEqual(abs(lag(master, decoded, start)), RATE // 500, "audio drifted from the map")
        last = units[-1]
        self.assertGreater(rms_db(decoded[last["start_sample"]:last["end_sample"]]), -40, "the last unit is missing")

        # Each slide changes exactly at its scene's first frame, and the last frames show the final scene.
        pixels = np.frombuffer(subprocess.run(
            [str(FFMPEG), "-v", "error", "-nostdin", "-i", str(video), "-map", "0:v:0", "-vf", "scale=32:18",
             "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout, dtype=np.uint8)
        pixels = pixels.reshape(-1, 18 * 32).astype(np.int16)
        self.assertEqual(len(pixels), frames)
        changes = [index for index in range(1, frames) if np.abs(pixels[index] - pixels[index - 1]).mean() > 1]
        self.assertEqual(changes, [scene["start_frame"] for scene in scenes[1:]])


if __name__ == "__main__":
    unittest.main()
