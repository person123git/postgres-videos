import io
import json
import tempfile
import unittest
from contextlib import chdir, redirect_stderr
from pathlib import Path
from unittest.mock import call, patch

from pgvideo.cli import create_request, parser
from pgvideo.sources import SourceError, resolve_document
from test_sources import install_project_files


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def fake_contents(path, ref):
    files = {
        ("wiki/example.md", "main"),
        ("wiki/example.md", "master"),
        ("wiki/example.md", "feature/video"),
        ("wiki/example.txt", "main"),
        ("wiki/legacy.md", "master"),
    }
    if path == "wiki" and ref == "main":
        return []
    if (path, ref) in files:
        return {"type": "file", "path": path}
    return None


class RequestTests(unittest.TestCase):
    def setUp(self):
        fixture_parent = (PROJECT_ROOT / ".runtime" / "tmp").resolve()
        if not fixture_parent.is_relative_to(PROJECT_ROOT):
            raise RuntimeError("Test fixtures must stay inside the project directory.")
        fixture_parent.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="pgvideo-test-", dir=fixture_parent)
        self.addCleanup(temporary.cleanup)
        self.fixture_root = Path(temporary.name)
        self.workspace = self.fixture_root / "project"
        self.workspace.mkdir()
        self.outside = self.fixture_root / "outside"
        self.outside.mkdir()
        self.enterContext(patch("pgvideo.cli.project_root", return_value=self.workspace))
        install_project_files(self.workspace)
        # The runbook, prompts, schemas, and pronunciation a request reads; nothing else may appear.
        self.installed = sorted(path.name for path in self.workspace.iterdir())

    def request_args(self, output="output"):
        return parser().parse_args(
            ["prepare", "--document", "wiki/example.md", "--output", str(output)]
        )

    @patch("pgvideo.sources._github_contents", side_effect=fake_contents)
    def test_relative_path_defaults_to_main_and_writes_request(self, lookup):
        request_path = create_request(self.request_args("video-output"), workspace=self.workspace)
        data = json.loads(request_path.read_text(encoding="utf-8"))
        self.assertEqual(data["document"]["path"], "wiki/example.md")
        self.assertEqual(data["document"]["ref"], "main")
        self.assertEqual(data["repository"], "person123git/postgres-llm-wiki")
        self.assertEqual(data["settings"]["voice"], "af_heart")
        self.assertEqual(data["settings"]["output_dir"], str(self.workspace / "video-output"))
        self.assertEqual(request_path.parent.name, data["request_id"])
        self.assertFalse((request_path.parent / ".request.json.tmp").exists())
        self.assertEqual(lookup.call_count, 1)
        lookup.assert_called_once_with("wiki/example.md", "main")

    @patch("pgvideo.sources._github_contents", side_effect=fake_contents)
    def test_level_of_detail_is_recorded_and_defaults_to_standard(self, _lookup):
        data = json.loads(create_request(self.request_args(), workspace=self.workspace).read_text(encoding="utf-8"))
        self.assertEqual(data["settings"]["detail"], "standard")
        for detail in ("summary", "full"):
            args = parser().parse_args(["prepare", "--document", "wiki/example.md", "--detail", detail])
            data = json.loads(create_request(args, workspace=self.workspace).read_text(encoding="utf-8"))
            self.assertEqual(data["settings"]["detail"], detail)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser().parse_args(["prepare", "--document", "wiki/example.md", "--detail", "short"])

    @patch("pgvideo.sources._github_contents", side_effect=fake_contents)
    def test_request_manifest_records_environment_snapshot(self, _lookup):
        report = {
            "status": "passed", "project_root": str(self.workspace),
            "python": {"version": "3.11.16"}, "platform": {"architecture": "arm64"},
            "checks": {"assets": "passed"}, "os_requirements": ["macOS"],
            "isolation_limitations": ["OS framework access"],
        }
        runtime = self.workspace / ".runtime"
        runtime.mkdir()
        (runtime / "environment-report.json").write_text(json.dumps(report))
        (self.workspace / "tools.lock").write_text("{}")
        (self.workspace / "requirements.lock").write_text("locked")
        request_path = create_request(self.request_args(), workspace=self.workspace)
        manifest = json.loads((request_path.parent / "manifest.json").read_text())
        self.assertEqual(manifest["request_id"], json.loads(request_path.read_text())["request_id"])
        self.assertEqual(manifest["environment"]["checks"]["assets"], "passed")
        self.assertEqual(len(manifest["environment"]["tools_lock_sha256"]), 64)

    @patch("pgvideo.sources._github_contents", side_effect=fake_contents)
    def test_request_uses_project_root_from_another_working_directory(self, lookup):
        with chdir(self.outside):
            request_path = create_request(self.request_args())
        data = json.loads(request_path.read_text(encoding="utf-8"))
        self.assertEqual(request_path.parent.parent, self.workspace / "runs")
        self.assertEqual(data["settings"]["output_dir"], str(self.workspace / "output"))
        self.assertEqual(list(self.outside.iterdir()), [])
        lookup.assert_called_once()

    @patch("pgvideo.sources._github_contents", side_effect=fake_contents)
    def test_rejects_output_escapes_before_network_or_writes(self, lookup):
        for output in (
            "../outside/video",
            "new/../../outside/video",
            self.outside / "video",
            self.fixture_root / "project-other" / "video",
        ):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "inside the project"):
                create_request(self.request_args(output), workspace=self.workspace)
        lookup.assert_not_called()
        self.assertEqual(sorted(path.name for path in self.workspace.iterdir()), self.installed)
        self.assertEqual(list(self.outside.iterdir()), [])

    @patch("pgvideo.sources._github_contents", side_effect=fake_contents)
    def test_rejects_external_workspace_before_network_or_writes(self, lookup):
        with self.assertRaisesRegex(ValueError, "inside the project"):
            create_request(self.request_args(), workspace=self.outside)
        lookup.assert_not_called()
        self.assertEqual(list(self.outside.iterdir()), [])

    @patch("pgvideo.sources._github_contents", side_effect=fake_contents)
    def test_rejects_output_symlink_escapes(self, lookup):
        (self.workspace / "external").symlink_to(self.outside, target_is_directory=True)
        (self.workspace / "dangling").symlink_to(self.outside / "missing", target_is_directory=True)
        (self.workspace / "relative").symlink_to("../outside", target_is_directory=True)
        (self.workspace / "chain").symlink_to("external", target_is_directory=True)
        for output in ("external", "external/video", "dangling/video", "relative", "chain/video"):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "inside the project"):
                create_request(self.request_args(output), workspace=self.workspace)
        lookup.assert_not_called()
        self.assertFalse((self.workspace / "runs").exists())
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_rechecks_paths_after_document_lookup(self):
        for name in ("output", "runs"):
            with self.subTest(name=name):
                link = self.workspace / name

                def changed_during_lookup(path, ref):
                    link.symlink_to(self.outside, target_is_directory=True)
                    return fake_contents(path, ref)

                with patch("pgvideo.sources._github_contents", side_effect=changed_during_lookup) as lookup:
                    try:
                        with self.assertRaisesRegex(ValueError, "inside the project"):
                            create_request(self.request_args(), workspace=self.workspace)
                        lookup.assert_called_once()
                    finally:
                        link.unlink(missing_ok=True)
        self.assertEqual(sorted(path.name for path in self.workspace.iterdir()), self.installed)
        self.assertEqual(list(self.outside.iterdir()), [])

    @patch("pgvideo.sources._github_contents", side_effect=fake_contents)
    def test_rejects_runs_symlink_escapes(self, lookup):
        runs = self.workspace / "runs"
        for target in (self.outside, self.outside / "missing"):
            with self.subTest(target=target):
                runs.symlink_to(target, target_is_directory=True)
                try:
                    with self.assertRaisesRegex(ValueError, "inside the project"):
                        create_request(self.request_args(), workspace=self.workspace)
                finally:
                    runs.unlink()
        lookup.assert_not_called()
        self.assertEqual(list(self.outside.iterdir()), [])

    @patch("pgvideo.sources._github_contents", side_effect=fake_contents)
    def test_accepts_local_absolute_paths_and_internal_symlinks(self, lookup):
        destination = self.workspace / "videos"
        destination.mkdir()
        (self.workspace / "linked").symlink_to("videos", target_is_directory=True)
        requests = self.workspace / "requests"
        requests.mkdir()
        (self.workspace / "runs").symlink_to("requests", target_is_directory=True)
        for output in (destination, "linked/./new/../final"):
            with self.subTest(output=output):
                request_path = create_request(self.request_args(output), workspace=self.workspace)
                data = json.loads(request_path.read_text(encoding="utf-8"))
                self.assertEqual(request_path.parent.parent, requests)
                self.assertEqual(data["settings"]["output_dir"], str((self.workspace / output).resolve()))
        self.assertEqual(lookup.call_count, 2)

    @patch("pgvideo.sources._github_contents", side_effect=fake_contents)
    def test_rejects_file_paths_and_symlink_loops_before_network(self, lookup):
        (self.workspace / "file").write_text("existing content", encoding="utf-8")
        (self.workspace / "loop").symlink_to("loop", target_is_directory=True)
        for output in ("file", "file/video", "loop"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                create_request(self.request_args(output), workspace=self.workspace)
        lookup.assert_not_called()
        self.assertFalse((self.workspace / "runs").exists())

    @patch("pgvideo.sources._github_contents", side_effect=fake_contents)
    def test_blob_url_uses_its_ref_including_slashes(self, _lookup):
        document = resolve_document(
            "https://github.com/person123git/postgres-llm-wiki/blob/feature/video/wiki/example.md"
        )
        self.assertEqual((document.path, document.ref), ("wiki/example.md", "feature/video"))
        document = resolve_document(
            "https://github.com/person123git/postgres-llm-wiki/blob/master/wiki/example.md"
        )
        self.assertEqual((document.path, document.ref), ("wiki/example.md", "master"))
        with self.assertRaisesRegex(SourceError, "conflicts"):
            resolve_document(
                "https://github.com/person123git/postgres-llm-wiki/blob/master/wiki/example.md",
                "other",
            )
        with self.assertRaisesRegex(SourceError, "not found"):
            resolve_document(
                "https://github.com/person123git/postgres-llm-wiki/blob/master/wiki/missing.md"
            )
        with self.assertRaisesRegex(SourceError, "globs"):
            resolve_document(
                "https://github.com/person123git/postgres-llm-wiki/blob/master/wiki/%2A.md"
            )

    @patch("pgvideo.sources._github_contents", side_effect=fake_contents)
    def test_explicit_ref_overrides_default_and_is_recorded(self, lookup):
        args = self.request_args()
        args.ref = "master"
        request_path = create_request(args, workspace=self.workspace)
        data = json.loads(request_path.read_text(encoding="utf-8"))
        self.assertEqual(data["document"]["ref"], "master")
        lookup.assert_called_once_with("wiki/example.md", "master")

    @patch("pgvideo.sources._github_contents", side_effect=fake_contents)
    def test_default_ref_falls_back_to_master_when_main_is_missing(self, lookup):
        document = resolve_document("wiki/legacy.md")
        self.assertEqual((document.path, document.ref), ("wiki/legacy.md", "master"))
        self.assertEqual(lookup.call_args_list, [call("wiki/legacy.md", "main"), call("wiki/legacy.md", "master")])

    @patch("pgvideo.sources._github_contents", side_effect=fake_contents)
    def test_rejects_missing_directory_and_non_markdown(self, _lookup):
        for path, message in (
            ("wiki/missing.md", "not found"),
            ("wiki", "directory"),
            ("wiki/example.txt", "not a Markdown"),
            ("wiki/*.md", "globs"),
            ("../wiki/example.md", "segments"),
        ):
            with self.subTest(path=path), self.assertRaisesRegex(SourceError, message):
                resolve_document(path)

    def test_rejects_other_repository_and_requires_document(self):
        with self.assertRaisesRegex(SourceError, "person123git/postgres-llm-wiki"):
            resolve_document("https://github.com/other/repo/blob/master/wiki/example.md")
        with self.assertRaises(SystemExit):
            parser().parse_args(["prepare"])
        with self.assertRaises(SystemExit):
            parser().parse_args(
                ["prepare", "--document", "wiki/example.md", "--width", "1919"]
            )


if __name__ == "__main__":
    unittest.main()
