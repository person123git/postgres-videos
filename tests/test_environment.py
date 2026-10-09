import importlib.util
import json
import os
import re
import socket
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

_sample_spec = importlib.util.spec_from_file_location("pgvideo_sample", ROOT / "scripts/sample_environment.py")
sample = importlib.util.module_from_spec(_sample_spec)
_sample_spec.loader.exec_module(sample)


def fixture_directory(test: unittest.TestCase) -> Path:
    temporary = tempfile.TemporaryDirectory(prefix="pgvideo-test-", dir=ROOT / ".runtime" / "tmp")
    test.addCleanup(temporary.cleanup)
    return Path(temporary.name).resolve()


def write_elf(path: Path, *, needed=(), runpaths=(), machine=62) -> Path:
    """Write a minimal x86_64 shared object with the given needed libraries and library search paths."""
    strings, entries = b"\0", []
    for tag, values in ((1, needed), (29, [":".join(runpaths)] if runpaths else [])):
        for value in values:
            entries.append((tag, len(strings)))
            strings += value.encode() + b"\0"
    dynamic_offset = 64 + 2 * 56
    strings_offset = dynamic_offset + (len(entries) + 2) * 16
    dynamic = b"".join(struct.pack("<qQ", *entry) for entry in (*entries, (5, strings_offset), (0, 0)))
    size = strings_offset + len(strings)
    header = struct.pack("<16sHHIQQQIHHHHHH", b"\x7fELF\x02\x01\x01", 3, machine, 1, 0, 64, 0, 0, 64, 56, 2, 64, 0, 0)
    segments = (struct.pack("<IIQQQQQQ", 1, 4, 0, 0, 0, size, size, 4096)
                + struct.pack("<IIQQQQQQ", 2, 4, dynamic_offset, dynamic_offset, dynamic_offset,
                              len(dynamic), len(dynamic), 8))
    path.write_bytes(header + segments + dynamic + strings)
    return path


def run_filter(program: bytes, *, architecture: int, number: int, family: int = 0) -> int:
    """Return the seccomp verdict of a filter built from the load, compare, and return instructions."""
    data = struct.pack("<iIQ6Q", number, architecture, 0, family, 0, 0, 0, 0, 0)
    instructions = [struct.unpack_from("HBBI", program, offset) for offset in range(0, len(program), 8)]
    accumulator = position = 0
    while True:
        code, jump_true, jump_false, value = instructions[position]
        position += 1
        if code == 0x06:
            return value
        if code == 0x20:
            (accumulator,) = struct.unpack_from("<I", data, value)
        else:
            matched = accumulator == value if code == 0x15 else accumulator >= value
            position += jump_true if matched else jump_false


class EnvironmentTests(unittest.TestCase):
    def test_webm_cues_check_reads_element_boundaries(self):
        # Payload bytes that resemble Cues must not count as a Segment child.
        cues, cluster = b"\x1c\x53\xbb\x6b", b"\x1f\x43\xb6\x75"
        with tempfile.TemporaryDirectory(dir=ROOT / ".runtime/tmp") as directory:
            path = Path(directory) / "sample.webm"
            for size in (b"\xff", b"\x8b"):  # unknown and finite Segment sizes
                path.write_bytes(b"\x18\x53\x80\x67" + size + cues + b"\x80" + cluster + b"\x81\x00")
                self.assertEqual(sample.webm_elements(path), [0x1C53BB6B, 0x1F43B675])
            path.write_bytes(b"\x18\x53\x80\x67\xff\xec\x84" + cues + cluster + b"\x80")
            self.assertEqual(sample.webm_elements(path), [0xEC, 0x1F43B675])
            path.write_bytes(b"\x18\x53\x80\x67\xff\x00")
            with self.assertRaisesRegex(RuntimeError, "invalid WebM element header"):
                sample.webm_elements(path)

    def test_unprovisioned_voice_fails_before_synthesis(self):
        with self.assertRaisesRegex(AssetError, "not provisioned"):
            local_selection(voice="af_missing")

    def test_tests_run_inside_offline_project_sandbox(self):
        self.assertTrue(environment.sandboxed())
        self.assertEqual(environment.sandbox_probes("offline"), {
            "write /tmp": "denied",
            "read /etc/passwd": "denied",
            "execute /usr/bin/true": "denied",
            "connect 192.0.2.1:9": "denied",
        })
        # Landlock covers only TCP; the seccomp filter keeps UDP sockets from existing at all.
        for family in (socket.AF_INET, socket.AF_INET6):
            with self.subTest(family=family), self.assertRaises(PermissionError):
                socket.socket(family, socket.SOCK_DGRAM)
        socket.socket(socket.AF_UNIX, socket.SOCK_STREAM).close()

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
            "HOME": "/tmp/pgvideo-hostile-home",
            "PYTHONPATH": "/tmp/pgvideo-hostile-imports",
            "PYTHONHOME": "/tmp/pgvideo-hostile-python",
            "PIP_CONFIG_FILE": "/tmp/pgvideo-hostile-pip.conf",
            "PIP_EXTRA_INDEX_URL": "https://invalid.example/simple",
            "VIRTUAL_ENV": "/tmp/pgvideo-hostile-venv",
            "LD_LIBRARY_PATH": "/tmp/pgvideo-hostile-lib",
            "SSL_CERT_FILE": "/tmp/pgvideo-hostile-cert.pem",
            "OPENSSL_CONF": "/tmp/pgvideo-hostile-openssl.cnf",
            "FONTCONFIG_FILE": "/tmp/pgvideo-hostile-fonts.conf",
            "TMPDIR": "/tmp/pgvideo-hostile-tmp",
            "XDG_CACHE_HOME": "/tmp/pgvideo-hostile-cache",
            "PIP_CACHE_DIR": "/tmp/pgvideo-hostile-pip-cache",
            "HF_HOME": "/tmp/pgvideo-hostile-hf",
            "HF_HUB_OFFLINE": "0",
            "TORCH_HOME": "/tmp/pgvideo-hostile-torch",
            "PLAYWRIGHT_BROWSERS_PATH": "/tmp/pgvideo-hostile-browsers",
            "PHONEMIZER_ESPEAK_LIBRARY": "/tmp/pgvideo-hostile-espeak.so",
            "PGVIDEO_SANDBOX": "network",
            "PATH": f"{fake_tools}:/usr/local/bin:/usr/bin:/bin",
        })
        result = subprocess.run([str(ROOT / "scripts/pgvideo"), "doctor"],
                                env=hostile, cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists(), "the launcher ran a tool from the inherited PATH")
        report = json.loads((ROOT / ".runtime/environment-report.json").read_text())
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["environment_paths"]["HOME"], str(ROOT / ".runtime/home"))
        for name in ("TMPDIR", "XDG_CACHE_HOME", "PIP_CACHE_DIR", "HF_HOME", "TORCH_HOME", "PLAYWRIGHT_BROWSERS_PATH",
                     "PHONEMIZER_ESPEAK_LIBRARY", "FONTCONFIG_FILE"):
            with self.subTest(name=name):
                self.assertTrue(Path(report["environment_paths"][name]).is_relative_to(ROOT))
        self.assertEqual(report["environment_paths"]["HF_HUB_OFFLINE"], "1")
        self.assertEqual(report["isolation"]["policy"], "inherited")
        self.assertEqual(set(report["isolation"]["probes"].values()), {"denied"})
        self.assertNotIn("/tmp/pgvideo-hostile", json.dumps(report))
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

    def test_sandbox_profile_confines_access_to_the_project_and_documented_paths(self):
        offline = environment.sandbox_profile(network=False)
        network = environment.sandbox_profile(network=True)
        rules = offline["landlock"]["rules"]
        self.assertEqual(rules[0], {"path": str(ROOT), "access": ["read", "write", "create", "execute"]})
        self.assertEqual(sorted(rule["path"] for rule in rules[1:] if "write" in rule["access"]),
                         sorted(path for path, _ in environment.OS_WRITES))
        self.assertEqual([rule["path"] for rule in rules if "execute" in rule["access"]],
                         [str(ROOT), *environment.OS_EXECUTABLES])
        self.assertFalse(any("create" in rule["access"] for rule in rules[1:]))
        # Every right is handled, so whatever no rule grants is denied.
        self.assertEqual(set(offline["landlock"]["handled_access"]), set(environment.LANDLOCK_FS))
        for outside in ("/tmp/probe", environment.SANDBOX_CANARY, "/usr/bin/true", "/home", "/etc/hosts"):
            with self.subTest(outside=outside):
                self.assertFalse(any(Path(outside).is_relative_to(rule["path"]) for rule in rules))
        self.assertEqual(offline["landlock"]["tcp_bind_and_connect"], "denied")
        self.assertEqual(offline["seccomp"]["socket_families_denied"], ["AF_INET", "AF_INET6"])
        # Only the commands that download may read the resolver configuration and reach the network.
        self.assertEqual({rule["path"] for rule in network["landlock"]["rules"]} - {rule["path"] for rule in rules},
                         {path for path, _ in environment.NETWORK_READS})
        self.assertEqual((network["landlock"]["tcp_bind_and_connect"], network["seccomp"]), ("allowed", None))

    def test_seccomp_filter_denies_only_ip_sockets_and_io_uring(self):
        program = environment.seccomp_filter()
        denied = environment.SECCOMP_RET_ERRNO | 13
        unavailable = environment.SECCOMP_RET_ERRNO | 38
        native = environment.AUDIT_ARCH_X86_64
        cases = {
            "IPv4 socket": ({"number": 41, "family": socket.AF_INET}, denied),
            "IPv6 socket": ({"number": 41, "family": socket.AF_INET6}, denied),
            "Unix socket": ({"number": 41, "family": socket.AF_UNIX}, environment.SECCOMP_RET_ALLOW),
            "netlink socket": ({"number": 41, "family": socket.AF_NETLINK}, environment.SECCOMP_RET_ALLOW),
            "io_uring_setup": ({"number": 425}, unavailable),
            "x32 socket": ({"number": environment.X32_SYSCALL_BIT | 41, "family": socket.AF_INET}, unavailable),
            # openat has number 257; a call that shares no number with the denied ones passes.
            "openat": ({"number": 257, "family": socket.AF_INET}, environment.SECCOMP_RET_ALLOW),
        }
        for name, (call, verdict) in cases.items():
            with self.subTest(name):
                self.assertEqual(run_filter(program, architecture=native, **call), verdict)
        # The 32-bit entry point numbers its system calls differently, so it is not filtered but refused.
        self.assertEqual(run_filter(program, architecture=0x40000003, number=359, family=socket.AF_INET),
                         environment.SECCOMP_RET_KILL_PROCESS)

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
        torch_cpu = ROOT / ".venv/lib/python3.11/site-packages/torch/lib/libtorch_cpu.so"
        needed, paths, interpreter = environment.elf_dynamic(torch_cpu)
        self.assertIn("libc10.so", needed)
        self.assertEqual((paths, interpreter), (["$ORIGIN"], None))
        self.assertEqual(environment.check_native_binary(torch_cpu), [])
        self.assertEqual(environment.elf_dynamic(ROOT / ".venv/bin/python")[2], "/lib64/ld-linux-x86-64.so.2")
        self.assertIsNone(environment.check_native_binary(ROOT / "pyproject.toml"))

        fixtures = fixture_directory(self)
        (fixtures / "libok.so").write_bytes(b"")
        (fixtures / "hosts").write_bytes(b"")
        local = write_elf(fixtures / "local.so", needed=["libok.so", "libc.so.6", "$ORIGIN/libok.so"],
                          runpaths=["$ORIGIN"])
        self.assertEqual(environment.check_native_binary(local), [])
        unused = write_elf(fixtures / "unused.so", runpaths=["/tmp/pgvideo-build/lib"])
        self.assertEqual(environment.check_native_binary(unused), ["/tmp/pgvideo-build/lib"])
        cases = {
            "absolute": ({"needed": ["/etc/hosts"]}, "escapes project"),
            "shadowed": ({"needed": ["hosts"], "runpaths": ["/etc", "$ORIGIN"]}, "escapes project"),
            "missing": ({"needed": ["libmissing.so"], "runpaths": ["$ORIGIN"]}, "missing"),
            "foreign": ({"machine": 183}, "not x86_64"),
        }
        for name, (contents, message) in cases.items():
            with self.subTest(name), self.assertRaisesRegex(environment.EnvironmentError, message):
                environment.check_native_binary(write_elf(fixtures / f"{name}.so", **contents))
        # A library that the project ships in another directory can only come from the project.
        self.assertEqual(environment.check_native_binary(fixtures / "missing.so", frozenset({"libmissing.so"})), [])

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

        for name, target in {"parent": None, "absolute-link": "/etc", "parent-link": "../../.."}.items():
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
