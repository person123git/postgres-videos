import importlib.util
import json
import os
import re
import stat
import struct
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from pgvideo.assets import AssetError, local_selection
from pgvideo.validate import validate_video
from test_validate import delivery_fixture


ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("pgvideo_environment", ROOT / "scripts" / "environment.py")
environment = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(environment)


def fixture_directory(test: unittest.TestCase) -> Path:
    temporary = tempfile.TemporaryDirectory(prefix="pgvideo-test-", dir=ROOT / ".runtime" / "tmp")
    test.addCleanup(temporary.cleanup)
    return Path(temporary.name).resolve()


def write_macho(path: Path, *, dylibs=(), rpaths=()) -> Path:
    """Write a minimal arm64 dylib header with the given load commands."""
    commands = b""
    for name in dylibs:
        raw = name.encode() + b"\0"
        size = (24 + len(raw) + 7) // 8 * 8
        commands += struct.pack("<6I", 0xC, size, 24, 0, 0, 0) + raw.ljust(size - 24, b"\0")
    for name in rpaths:
        raw = name.encode() + b"\0"
        size = (12 + len(raw) + 7) // 8 * 8
        commands += struct.pack("<3I", 0x8000001C, size, 12) + raw.ljust(size - 12, b"\0")
    header = struct.pack("<IiiIIIII", 0xFEEDFACF, 0x0100000C, 0, 6,
                         len(dylibs) + len(rpaths), len(commands), 0, 0)
    path.write_bytes(header + commands)
    return path


class EnvironmentTests(unittest.TestCase):
    def test_unprovisioned_voice_fails_before_synthesis(self):
        with self.assertRaisesRegex(AssetError, "not provisioned"):
            local_selection(voice="af_missing")

    def test_tests_run_inside_offline_project_sandbox(self):
        self.assertTrue(environment.sandboxed())
        self.assertEqual(environment.sandbox_probes("offline"), {
            "write /private/tmp": "denied",
            "read /private/etc/hosts": "denied",
            "execute /usr/bin/true": "denied",
            "connect 192.0.2.1:9": "denied",
        })

    def test_mimetypes_uses_only_the_builtin_table(self):
        import mimetypes

        self.assertEqual(mimetypes.knownfiles, [])
        self.assertEqual(mimetypes.guess_type("slide.html")[0], "text/html")

    def test_launcher_replaces_hostile_environment(self):
        fake_tools = fixture_directory(self)
        marker = fake_tools / "used"
        for tool in ("dirname", "uname", "mkdir", "python3", "ffmpeg"):
            path = fake_tools / tool
            path.write_text(f"#!/bin/sh\necho {tool} >> '{marker}'\nexit 97\n")
            path.chmod(0o755)
        hostile = dict(os.environ)
        hostile.update({
            "HOME": "/private/tmp/pgvideo-hostile-home",
            "PYTHONPATH": "/private/tmp/pgvideo-hostile-imports",
            "PYTHONHOME": "/private/tmp/pgvideo-hostile-python",
            "PIP_CONFIG_FILE": "/private/tmp/pgvideo-hostile-pip.conf",
            "PIP_EXTRA_INDEX_URL": "https://invalid.example/simple",
            "VIRTUAL_ENV": "/private/tmp/pgvideo-hostile-venv",
            "DYLD_LIBRARY_PATH": "/private/tmp/pgvideo-hostile-lib",
            "SSL_CERT_FILE": "/private/tmp/pgvideo-hostile-cert.pem",
            "OPENSSL_CONF": "/private/tmp/pgvideo-hostile-openssl.cnf",
            "MAC_CHROMIUM_TMPDIR": "/private/tmp/pgvideo-hostile-chromium",
            "TMPDIR": "/private/tmp/pgvideo-hostile-tmp",
            "XDG_CACHE_HOME": "/private/tmp/pgvideo-hostile-cache",
            "PIP_CACHE_DIR": "/private/tmp/pgvideo-hostile-pip-cache",
            "HF_HOME": "/private/tmp/pgvideo-hostile-hf",
            "HF_HUB_OFFLINE": "0",
            "TORCH_HOME": "/private/tmp/pgvideo-hostile-torch",
            "PLAYWRIGHT_BROWSERS_PATH": "/private/tmp/pgvideo-hostile-browsers",
            "PHONEMIZER_ESPEAK_LIBRARY": "/private/tmp/pgvideo-hostile-espeak.dylib",
            "PGVIDEO_SANDBOX": "network",
            "PATH": f"{fake_tools}:/opt/homebrew/bin:/usr/bin:/bin",
        })
        result = subprocess.run([str(ROOT / "scripts/pgvideo"), "doctor"],
                                env=hostile, cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists(), "the launcher ran a tool from the inherited PATH")
        report = json.loads((ROOT / ".runtime/environment-report.json").read_text())
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["environment_paths"]["HOME"], str(ROOT / ".runtime/home"))
        for name in ("TMPDIR", "XDG_CACHE_HOME", "PIP_CACHE_DIR", "HF_HOME", "TORCH_HOME", "PLAYWRIGHT_BROWSERS_PATH",
                     "PHONEMIZER_ESPEAK_LIBRARY", "MAC_CHROMIUM_TMPDIR"):
            with self.subTest(name=name):
                self.assertTrue(Path(report["environment_paths"][name]).is_relative_to(ROOT))
        self.assertEqual(report["environment_paths"]["HF_HUB_OFFLINE"], "1")
        self.assertEqual(report["isolation"]["policy"], "inherited")
        self.assertEqual(set(report["isolation"]["probes"].values()), {"denied"})
        self.assertNotIn("/private/tmp/pgvideo-hostile", json.dumps(report))
        self.assertNotIn("invalid.example", json.dumps(report))

    def test_launcher_needs_no_host_tools_on_the_search_path(self):
        empty = fixture_directory(self)
        for path in (str(empty), None):
            with self.subTest(path=path):
                env = {key: value for key, value in os.environ.items() if key != "PATH"}
                if path is not None:
                    env["PATH"] = path
                result = subprocess.run([str(ROOT / "scripts/pgvideo"), "doctor"], env=env, cwd=empty,
                                        text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_fixtures_and_temporary_files_stay_inside_the_project(self):
        self.assertEqual(Path(tempfile.gettempdir()).resolve(), ROOT / ".runtime/tmp")
        self.assertEqual(os.environ["TMPDIR"], str(ROOT / ".runtime/tmp"))
        self.assertTrue(fixture_directory(self).is_relative_to(ROOT / ".runtime/tmp"))

    def test_missing_local_tools_fail_without_host_fallbacks(self):
        with self.assertRaisesRegex(environment.EnvironmentError, "missing local artifact: .runtime/bin/nothing; run "
                                                                  "scripts/setup"):
            environment.check_hash(".runtime/bin/nothing", "0" * 64)
        # A project without its own ffprobe must fail, not run one found on PATH.
        workspace = fixture_directory(self)
        decoys = workspace / "decoys"
        decoys.mkdir()
        marker = workspace / "decoy-ran"
        for tool in ("ffmpeg", "ffprobe"):
            (decoys / tool).write_text(f"#!/bin/sh\necho {tool} >> '{marker}'\nexit 0\n")
            (decoys / tool).chmod(0o755)
        run = workspace / "runs" / "sample"
        (workspace / "output").mkdir()
        delivery_fixture(run, workspace / "output")
        with patch.dict(os.environ, {"PATH": f"{decoys}:{os.environ['PATH']}"}), \
                self.assertRaisesRegex(OSError, re.escape(str(workspace / ".runtime/bin/ffprobe"))):
            validate_video(workspace, run)
        self.assertEqual(json.loads((run / "manifest.json").read_text())["validation"]["status"], "failed")
        self.assertFalse(marker.exists(), "a tool from PATH was used")
        self.assertEqual(list((workspace / "output").iterdir()), [])

    def test_audit_profile_terminates_undocumented_access_after_the_known_exceptions(self):
        profile = environment.audit_profile().splitlines()
        kill = "(with send-signal SIGKILL)"
        for operation in ("file-read-data", "file-write*", "process-exec*"):
            with self.subTest(operation=operation):
                rules = [index for index, rule in enumerate(profile) if rule.startswith(f"(deny {operation} ")]
                # Seatbelt applies the last matching rule, so the documented exception must follow the kill rule.
                self.assertEqual(len(rules), 2)
                self.assertIn(kill, profile[rules[0]])
                self.assertNotIn(kill, profile[rules[1]])
                self.assertIn('(subpath (param "PROJECT_ROOT"))', profile[rules[0]])
        self.assertEqual(profile[-2:], ["(deny network-outbound (remote ip) (with send-signal SIGKILL))",
                                        '(deny network-outbound (remote ip "*:9"))'])
        text = "\n".join(profile)
        for rule, _description in (*environment.AUDIT_KNOWN_READS, *environment.AUDIT_KNOWN_WRITES,
                                   *environment.AUDIT_KNOWN_EXECUTABLES):
            self.assertIn(rule, text)
        self.assertNotIn("/private/tmp", " ".join(rule for rule, _ in environment.OS_READS))

    def test_base_python_cannot_launch_application(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        result = subprocess.run([str(ROOT / ".runtime/python/bin/python3.11"), "-m", "pgvideo", "--help"],
                                env=env, cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("scripts/pgvideo", result.stderr)

    def test_setup_bootstrap_matches_tools_lock(self):
        script = (ROOT / "scripts/setup").read_text()
        values = dict(re.findall(r"^(runtime_\w+)='?([^'\n]+)'?$", script, re.MULTILINE))
        python = environment.read_lock()["python"]
        self.assertEqual(values, {"runtime_archive": python["archive"], "runtime_url": python["url"],
                                  "runtime_sha": python["sha256"]})

    def test_native_dependencies_resolve_inside_project(self):
        torch_cpu = ROOT / ".venv/lib/python3.11/site-packages/torch/lib/libtorch_cpu.dylib"
        _, dependencies, rpaths = environment.macho_load_commands(torch_cpu)
        self.assertIn(("@loader_path/libc10.dylib", False), dependencies)
        self.assertEqual(rpaths, ["@loader_path"])
        self.assertEqual(environment.check_native_binary(torch_cpu), [])
        self.assertIsNone(environment.check_native_binary(ROOT / "pyproject.toml"))

        fixtures = fixture_directory(self)
        (fixtures / "libok.dylib").write_bytes(b"")
        (fixtures / "hosts").write_bytes(b"")
        local = write_macho(fixtures / "local.dylib", dylibs=["@loader_path/libok.dylib", "/usr/lib/libSystem.B.dylib"])
        self.assertEqual(environment.check_native_binary(local), [])
        unused = write_macho(fixtures / "unused.dylib", rpaths=["/private/tmp/pgvideo-build/lib"])
        self.assertEqual(environment.check_native_binary(unused), ["/private/tmp/pgvideo-build/lib"])
        cases = {
            "absolute": ({"dylibs": ["/private/etc/hosts"]}, "escapes project"),
            "shadowed": ({"dylibs": ["@rpath/hosts"], "rpaths": ["/private/etc", "@loader_path"]}, "escapes project"),
            "missing": ({"dylibs": ["@loader_path/libmissing.dylib"]}, "missing"),
        }
        for name, (commands, message) in cases.items():
            with self.subTest(name), self.assertRaisesRegex(environment.EnvironmentError, message):
                environment.check_native_binary(write_macho(fixtures / f"{name}.dylib", **commands))

    def test_archive_extraction_keeps_modes_and_rejects_escapes(self):
        fixtures = fixture_directory(self)
        archive = fixtures / "good.zip"
        with zipfile.ZipFile(archive, "w") as output:
            executable = zipfile.ZipInfo("tool/bin/run")
            executable.external_attr = (stat.S_IFREG | 0o755) << 16
            output.writestr(executable, "#!/bin/sh\n")
            link = zipfile.ZipInfo("tool/current")
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            output.writestr(link, "bin")
        environment.extract_zip(archive, fixtures / "good")
        self.assertEqual(stat.S_IMODE((fixtures / "good/tool/bin/run").stat().st_mode), 0o755)
        self.assertEqual(os.readlink(fixtures / "good/tool/current"), "bin")

        for name, target in {"parent": None, "absolute-link": "/private/etc", "parent-link": "../../.."}.items():
            archive = fixtures / f"{name}.zip"
            with zipfile.ZipFile(archive, "w") as output:
                if target is None:
                    output.writestr("../outside.txt", "x")
                else:
                    link = zipfile.ZipInfo("tool/link")
                    link.external_attr = (stat.S_IFLNK | 0o777) << 16
                    output.writestr(link, target)
            with self.subTest(name), self.assertRaisesRegex(environment.EnvironmentError, "escapes"):
                environment.extract_zip(archive, fixtures / name)
        self.assertFalse((fixtures / "outside.txt").exists())


if __name__ == "__main__":
    unittest.main()
