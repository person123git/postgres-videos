"""Input readers accept complete files without byte or character ceilings."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pgvideo import contracts
from pgvideo.crosscheck import _load_resolutions
from pgvideo.markdown import split_front_matter
from pgvideo.script import _load_scenes, _run_drafter
from pgvideo.speech import Pronunciation
from test_sources import PROJECT_ROOT


class ReadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pgvideo-reads-", dir=PROJECT_ROOT / ".runtime" / "tmp")
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)

    def test_large_authored_inputs_and_drafter_responses_are_read_completely(self):
        data = b'{"schema": 1, "scenes": []}' + b" " * (17 * 1024 * 1024)
        path = self.workspace / "storyboard.json"
        path.write_bytes(data)
        self.assertEqual(contracts.project_file(self.workspace, path, label="Plan"), path)
        self.assertEqual(contracts.parse(path.read_bytes(), str(path)), {"schema": 1, "scenes": []})
        path.chmod(0o700)
        with patch("pgvideo.script.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = data
            output = _run_drafter(self.workspace, path, b"{}")
        self.assertEqual(_load_scenes(output, str(path)), {"scenes": []})

    def test_large_front_matter_preserves_the_metadata_and_body(self):
        notes = "x" * (65 * 1024)
        metadata, body = split_front_matter(f"---\nnotes: {notes}\n---\n# Body\n")
        self.assertEqual(metadata, {"notes": notes})
        self.assertEqual(body, "\n\n\n# Body\n")

    def test_large_resolution_and_pronunciation_files_load(self):
        (self.workspace / "resolutions.yaml").write_text(
            "#" + "x" * (1024 * 1024) + "\nresolutions: []\n", encoding="utf-8")
        self.assertEqual(_load_resolutions(self.workspace)["resolutions"], [])
        pronunciation = self.workspace / "pronunciation"
        pronunciation.mkdir()
        (pronunciation / "en.yaml").write_text(
            "#" + "x" * (257 * 1024) + "\nschema: 1\nterms:\n  PostgreSQL: postgres\n", encoding="utf-8")
        with patch("pgvideo.glossary.english_words", return_value=frozenset()):
            dictionary = Pronunciation.load(self.workspace)
        self.assertEqual(dictionary.speak("PostgreSQL"), "postgres")
