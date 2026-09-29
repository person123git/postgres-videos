"""Shared setup, launcher, test, and doctor environment for this checkout.

This file uses only the standard library so it can validate paths before
loading any project dependency. It must be run by the project's .venv Python.
Every command re-executes itself under a macOS Seatbelt profile that confines
file access to the project and a documented set of operating system paths.
"""

from __future__ import annotations

import ctypes
import hashlib
import importlib.metadata
import json
import os
import platform
import pwd
import re
import shutil
import socket
import ssl
import stat
import struct
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
PYTHON = VENV / "bin" / "python"
SITE = VENV / "lib" / "python3.11" / "site-packages"
CA_BUNDLE = SITE / "certifi" / "cacert.pem"
LOCK = ROOT / "tools.lock"
REPORT = ROOT / ".runtime" / "environment-report.json"
SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")
LIBSYSTEM = "/usr/lib/libSystem.B.dylib"

DIRECTORIES = (
    ".runtime/python", ".runtime/bin", ".runtime/lib", ".runtime/share",
    ".runtime/browsers", ".runtime/home", ".runtime/config",
    ".runtime/data", ".runtime/state", ".runtime/tmp", "cache",
    "cache/downloads", "cache/wheels", "cache/pip", "cache/huggingface",
    "cache/torch", "cache/sources", "cache/glossary", "cache/narration", "cache/videos", "cache/models",
    "cache/pycache",
    "assets/fonts", "runs", "output",
)
PASSTHROUGH = ("GITHUB_TOKEN", "HF_TOKEN", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY",
               "https_proxy", "http_proxy", "no_proxy")

# Commands that download; every other command, and setup --offline, runs with IP networking denied.
NETWORK_COMMANDS = {"setup", "generate"}
# Operating system locations a sandboxed command may use besides the project.
# Seatbelt matches canonical paths, so /etc and /tmp appear as /private/...
OS_READS = (
    ('(literal "/")', "the root directory listing"),
    ('(require-all (subpath "/System") (require-not (subpath "/System/Volumes/Data")))',
     "/System frameworks and the dyld shared cache, excluding the data volume"),
    ('(subpath "/usr/lib")', "/usr/lib system libraries"),
    ('(subpath "/usr/share/zoneinfo")', "/usr/share/zoneinfo time zone data"),
    ('(subpath "/usr/share/icu")', "/usr/share/icu Unicode data"),
    ('(subpath "/usr/share/locale")', "/usr/share/locale locale data"),
    ('(subpath "/private/var/db/timezone")', "/private/var/db/timezone time zone data"),
    ('(subpath "/dev")', "/dev devices"),
)
OS_WRITES = (
    ('(literal "/dev/null")', "/dev/null"),
    ('(literal "/dev/dtracehelper")', "/dev/dtracehelper"),
    ('(regex #"^/dev/tty")', "/dev/tty* terminals"),
    ('(regex #"^/dev/fd/")', "/dev/fd/* inherited descriptors"),
)
# /bin/sh runs the shell selected by /private/var/select/sh.
OS_EXECUTABLES = ("/bin/sh", "/bin/bash", "/bin/dash", "/bin/zsh")
# Attempts outside the project that kill-on-access audits of setup --offline and the offline sample
# found on macOS 27.0 (arm64). The project sandbox denies each one, and setup and the sample pass
# without them. The audit profile denies them without terminating the process.
AUDIT_KNOWN_READS = (
    ('(literal "/private/etc")', "the /private/etc directory listing (Chromium, through macOS frameworks)"),
    ('(literal "/private/etc/hosts")', "/private/etc/hosts (Chromium, and doctor's read probe)"),
    ('(literal "/Library/Preferences/com.apple.networkd.plist")',
     "/Library/Preferences/com.apple.networkd.plist (Chromium)"),
    ('(subpath "/private/var/db/mds")', "/private/var/db/mds (Chromium)"),
    ('(subpath (string-append (param "USER_HOME") "/Library/Keyboard Layouts"))',
     "~/Library/Keyboard Layouts (Chromium)"),
    ('(subpath (string-append (param "USER_HOME") "/Library/Input Methods"))', "~/Library/Input Methods (Chromium)"),
    ('(subpath (string-append (param "USER_HOME") "/Library/Autosave Information"))',
     "~/Library/Autosave Information (Chromium)"),
    ('(literal "/private/tmp")', "the /private/tmp directory listing (PyTorch's bundled OpenMP runtime)"),
    ('(literal "/bin") ' + " ".join(f'(literal "{path}")' for path in OS_EXECUTABLES),
     "the /bin directory listing and the contents of " + ", ".join(OS_EXECUTABLES) + " (read whenever one of "
     "these shells starts, such as for scripts/espeak-ng-runtime)"),
)
AUDIT_KNOWN_WRITES = (
    ('(regex #"^/private/tmp/__KMP_REGISTERED_LIB_")',
     "/private/tmp/__KMP_REGISTERED_LIB_<pid> (PyTorch's bundled OpenMP runtime)"),
    ('(regex #"^/private/tmp/pgvideo-sandbox-probe-")', "/private/tmp/pgvideo-sandbox-probe-<pid> (doctor's write probe)"),
)
AUDIT_KNOWN_EXECUTABLES = (('(literal "/usr/bin/true")', "/usr/bin/true (doctor's execution probe)"),)
BOOTSTRAP_TOOLS = ("/bin/sh", "/bin/mkdir", "/usr/bin/uname", "/usr/bin/curl",
                   "/usr/bin/shasum", "/usr/bin/tar", "/usr/bin/env")

LC_REQ_DYLD = 0x80000000
DYLIB_COMMANDS = {0xC: False, 0x18 | LC_REQ_DYLD: True, 0x1F | LC_REQ_DYLD: False,
                  0x20: False, 0x23 | LC_REQ_DYLD: False}  # command -> weak link
LC_RPATH = 0x1C | LC_REQ_DYLD
MH_MAGIC_64 = 0xFEEDFACF
MH_EXECUTE = 2
FAT_MAGICS = {0xCAFEBABE: ">iiIII", 0xCAFEBABF: ">iiQQII"}
CPU_TYPE_ARM64 = 0x0100000C
OS_LIBRARY_PREFIXES = ("/System/Library/", "/usr/lib/")


class EnvironmentError(RuntimeError):
    pass


def local_path(relative: str) -> Path:
    path = ROOT / relative
    resolved = path.resolve(strict=False)
    if not resolved.is_relative_to(ROOT):
        raise EnvironmentError(f"configured path escapes the project: {relative}")
    return resolved


def create_directories() -> None:
    for relative in DIRECTORIES:
        path = local_path(relative)
        if path.exists() and not path.is_dir():
            raise EnvironmentError(f"expected a directory: {path}")
        path.mkdir(parents=True, exist_ok=True)


def controlled_environment() -> dict[str, str]:
    root = str(ROOT)
    env = {
        "PATH": f"{root}/.runtime/bin:/usr/bin:/bin",
        "HOME": f"{root}/.runtime/home",
        "XDG_CONFIG_HOME": f"{root}/.runtime/config",
        "XDG_DATA_HOME": f"{root}/.runtime/data",
        "XDG_STATE_HOME": f"{root}/.runtime/state",
        "XDG_CACHE_HOME": f"{root}/cache",
        "TMPDIR": f"{root}/.runtime/tmp",
        "TMP": f"{root}/.runtime/tmp",
        "TEMP": f"{root}/.runtime/tmp",
        # Chromium ignores TMPDIR on macOS and uses the per-user /var/folders directory.
        "MAC_CHROMIUM_TMPDIR": f"{root}/.runtime/tmp",
        "TZ": "UTC",
        # CoreFoundation otherwise reads ~/.CFUserTextEncoding from the real home directory.
        "__CF_USER_TEXT_ENCODING": f"0x{os.getuid():X}:0x0:0x0",
        "SSL_CERT_FILE": str(CA_BUNDLE),
        "SSL_CERT_DIR": str(CA_BUNDLE.parent),
        # Keep OpenSSL from loading the host's /private/etc/ssl/openssl.cnf.
        "OPENSSL_CONF": os.devnull,
        "VIRTUAL_ENV": f"{root}/.venv",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPYCACHEPREFIX": f"{root}/cache/pycache",
        "PIP_CONFIG_FILE": os.devnull,
        "PIP_CACHE_DIR": f"{root}/cache/pip",
        "PIP_REQUIRE_VIRTUALENV": "true",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_NO_INPUT": "1",
        "PIP_INDEX_URL": "https://pypi.org/simple",
        "HF_HOME": f"{root}/cache/huggingface",
        "HF_HUB_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "TORCH_HOME": f"{root}/cache/torch",
        "PLAYWRIGHT_BROWSERS_PATH": f"{root}/.runtime/browsers",
        "PLAYWRIGHT_SKIP_BROWSER_GC": "1",
        "PHONEMIZER_ESPEAK_LIBRARY": f"{root}/.runtime/lib/libespeak-ng.dylib",
        "PHONEMIZER_ESPEAK_DATA_PATH": f"{root}/.runtime/share/espeak-ng-data",
        "ESPEAK_DATA_PATH": f"{root}/.runtime/share/espeak-ng-data",
        "MPLCONFIGDIR": f"{root}/cache/matplotlib",
        "NUMBA_CACHE_DIR": f"{root}/cache/numba",
        "NLTK_DATA": f"{root}/cache/nltk",
        "CCACHE_DIR": f"{root}/cache/ccache",
        "CARGO_HOME": f"{root}/cache/cargo",
        "RUSTUP_HOME": f"{root}/cache/rustup",
        "DO_NOT_TRACK": "1",
        "PGVIDEO_LOCAL_ENV": root,
        "PGVIDEO_ENV_READY": "1",
        "LANG": "en_US.UTF-8",
    }
    for name in PASSTHROUGH:
        if name in os.environ:
            env[name] = os.environ[name]
    return env


def child_environment() -> dict[str, str]:
    return controlled_environment() | {"PGVIDEO_SANDBOX": os.environ.get("PGVIDEO_SANDBOX", "")}


def seatbelt_profile(*, network: bool) -> str:
    """Return the Seatbelt policy applied to every command in this project."""
    project = '(subpath (param "PROJECT_ROOT"))'
    executables = " ".join(f'(literal "{path}")' for path in OS_EXECUTABLES)
    rules = [
        "(version 1)",
        "(allow default)",
        f"(deny file-read-data (require-not (require-any {project} {' '.join(rule for rule, _ in OS_READS)})))",
        f"(deny file-write* (require-not (require-any {project} {' '.join(rule for rule, _ in OS_WRITES)})))",
        f"(deny process-exec* (require-not (require-any {project} {executables})))",
    ]
    if not network:
        rules.append("(deny network-outbound (remote ip))")
    return "\n".join(rules) + "\n"


def audit_profile() -> str:
    """Return the audit policy: any access outside the project and the OS paths terminates the process.

    Seatbelt applies the last matching rule, so the documented attempts listed after each kill
    rule are denied without terminating the process, as the project sandbox denies them.
    """
    project = '(subpath (param "PROJECT_ROOT"))'
    executables = " ".join(f'(literal "{path}")' for path in OS_EXECUTABLES)
    rules = ["(version 1)", "(allow default)"]
    for operation, allowed, known in (
            ("file-read-data", " ".join(rule for rule, _ in OS_READS), AUDIT_KNOWN_READS),
            ("file-write*", " ".join(rule for rule, _ in OS_WRITES), AUDIT_KNOWN_WRITES),
            ("process-exec*", executables, AUDIT_KNOWN_EXECUTABLES)):
        outside = f"(require-not (require-any {project} {allowed}))"
        rules.append(f"(deny {operation} {outside} (with send-signal SIGKILL))")
        rules.append(f"(deny {operation} (require-all {outside} (require-any {' '.join(rule for rule, _ in known)})))")
    rules.append("(deny network-outbound (remote ip) (with send-signal SIGKILL))")
    # Doctor's network probe connects to port 9 of a TEST-NET address; Seatbelt names hosts only as * or localhost.
    rules.append('(deny network-outbound (remote ip "*:9"))')
    return "\n".join(rules) + "\n"


def sandboxed() -> bool:
    """Return whether macOS Seatbelt already confines this process."""
    try:
        check = ctypes.CDLL(LIBSYSTEM).sandbox_check
    except (OSError, AttributeError) as error:
        raise EnvironmentError(f"cannot query the macOS sandbox state: {error}") from error
    check.restype = ctypes.c_int
    check.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    result = check(os.getpid(), None, 0)
    if result not in (0, 1):
        raise EnvironmentError("cannot determine whether the macOS sandbox is active")
    return result == 1


def restart_clean(command: str) -> None:
    expected = controlled_environment()
    if os.environ.get("PGVIDEO_ENV_READY") != "1":
        arguments = [str(PYTHON), "-I", str(Path(__file__).resolve()), *sys.argv[1:]]
        if sandboxed():
            # macOS refuses to apply a different profile inside a sandbox, so a command
            # started by a sandboxed parent (the test suite) keeps that policy. Doctor
            # probes it before any command runs.
            expected["PGVIDEO_SANDBOX"] = "inherited"
            os.execve(str(PYTHON), arguments, expected)
        if not SANDBOX_EXEC.is_file():
            raise EnvironmentError(f"{SANDBOX_EXEC} is missing; project containment cannot be enforced")
        parameters = []
        if command == "audit":
            policy, profile = "audit", audit_profile()
            # Chromium reaches ~/Library through macOS frameworks, which use the account's real home.
            parameters = ["-D", f"USER_HOME={pwd.getpwuid(os.getuid()).pw_dir}"]
        else:
            policy = "network" if command in NETWORK_COMMANDS and "--offline" not in sys.argv[2:] else "offline"
            profile = seatbelt_profile(network=policy == "network")
        expected["PGVIDEO_SANDBOX"] = policy
        os.execve(str(SANDBOX_EXEC), [str(SANDBOX_EXEC), "-D", f"PROJECT_ROOT={ROOT}", *parameters, "-p", profile,
                                      *arguments], expected)
    expected["PGVIDEO_SANDBOX"] = os.environ.get("PGVIDEO_SANDBOX", "")
    if expected["PGVIDEO_SANDBOX"] not in {"network", "offline", "audit", "inherited"} or not sandboxed():
        raise EnvironmentError("the project sandbox is not active; run through scripts/pgvideo")
    extras = set(os.environ) - set(expected) - {"LC_CTYPE"}
    mismatches = [key for key, value in expected.items() if os.environ.get(key) != value]
    if extras or mismatches:
        raise EnvironmentError(f"child environment is not controlled: {sorted(extras | set(mismatches))}")


def sandbox_probes(policy: str) -> dict[str, str]:
    """Attempt representative access outside the project; each attempt must be denied."""
    results = {}
    advice = "; run scripts/pgvideo outside other sandboxes" if policy == "inherited" else ""
    sandbox = f"the {policy} sandbox"
    probe = Path("/private/tmp") / f"pgvideo-sandbox-probe-{os.getpid()}"
    try:
        descriptor = os.open(probe, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except PermissionError:
        results["write /private/tmp"] = "denied"
    else:
        os.close(descriptor)
        probe.unlink()
        raise EnvironmentError(f"{sandbox} allowed a write outside the project{advice}")
    try:
        Path("/private/etc/hosts").read_bytes()
    except PermissionError:
        results["read /private/etc/hosts"] = "denied"
    else:
        raise EnvironmentError(f"{sandbox} allowed reading a file outside the project{advice}")
    try:
        subprocess.run(["/usr/bin/true"], env=controlled_environment(), check=False)
    except PermissionError:
        results["execute /usr/bin/true"] = "denied"
    else:
        raise EnvironmentError(f"{sandbox} allowed running a host executable{advice}")
    if policy != "network":
        try:
            # TEST-NET-1 (RFC 5737) is never routed, so an unsandboxed probe sends nothing useful.
            socket.create_connection(("192.0.2.1", 9), timeout=1).close()
        except PermissionError:
            results["connect 192.0.2.1:9"] = "denied"
        except OSError:
            if policy in ("offline", "audit"):
                raise EnvironmentError(f"the {policy} sandbox did not deny outbound network access")
            results["connect 192.0.2.1:9"] = "not denied by the inherited sandbox"
    return results


def read_lock() -> dict:
    if not LOCK.is_file():
        raise EnvironmentError("tools.lock is missing")
    return json.loads(LOCK.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_hash(relative: str, expected: str) -> Path:
    path = local_path(relative)
    if not path.is_file():
        raise EnvironmentError(f"missing local artifact: {relative}; run scripts/setup")
    if sha256(path) != expected:
        raise EnvironmentError(f"checksum mismatch: {relative}; remove the bad artifact and rerun scripts/setup")
    return path


def tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for file in sorted(child for child in path.rglob("*") if child.is_file()):
        if not file.resolve().is_relative_to(ROOT):
            raise EnvironmentError(f"artifact symlink escapes project: {file}")
        digest.update(file.relative_to(path).as_posix().encode() + b"\0")
        digest.update(bytes.fromhex(sha256(file)))
    return digest.hexdigest()


def environment_fingerprint() -> str:
    """Identify the locks and scripts that a recorded sample result applies to."""
    digest = hashlib.sha256()
    for name in ("tools.lock", "requirements.lock", "scripts/environment.py", "scripts/sample_environment.py",
                 "scripts/sitecustomize.py"):
        digest.update(name.encode() + b"\0" + bytes.fromhex(sha256(ROOT / name)))
    return digest.hexdigest()


def validate_python(lock: dict) -> None:
    if Path(sys.executable).resolve() != PYTHON.resolve():
        raise EnvironmentError(f"wrong interpreter: use {PYTHON} through scripts/pgvideo")
    if Path(sys.prefix).resolve() != VENV or Path(sys.base_prefix).resolve() != local_path(".runtime/python"):
        raise EnvironmentError(".venv is not backed by the project's Python runtime; recreate it with scripts/setup")
    if platform.system() != lock["platform"]["system"] or platform.machine() != lock["platform"]["architecture"]:
        raise EnvironmentError("this tools.lock supports macOS arm64 only")
    if int(platform.mac_ver()[0].split(".")[0]) < int(lock["platform"]["minimum_macos"].split(".")[0]):
        raise EnvironmentError("macOS is older than the pinned wheel and browser requirements")
    if platform.python_version() != lock["python"]["version"]:
        raise EnvironmentError("local Python version differs from tools.lock")
    config = (VENV / "pyvenv.cfg").read_text(encoding="utf-8")
    if not re.search(r"(?im)^include-system-site-packages\s*=\s*false\s*$", config):
        raise EnvironmentError(".venv must disable system site packages")
    if not re.search(r"(?im)^home\s*=\s*" + re.escape(str(local_path(".runtime/python/bin"))) + r"\s*$", config):
        raise EnvironmentError(".venv points to a foreign base Python")
    for path in sys.path:
        if path and not Path(path).resolve(strict=False).is_relative_to(ROOT):
            raise EnvironmentError(f"Python import path escapes the project: {path}")
    check_hash(lock["python"]["archive"], lock["python"]["sha256"])
    check_hash(lock["python"]["executable"], lock["python"]["executable_sha256"])
    check_hash(lock["python"]["shared_library"], lock["python"]["shared_library_sha256"])


def run_local(arguments: list[str], *, capture: bool = False, stdout: int | None = None,
              check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(arguments, cwd=ROOT, env=child_environment(), check=check,
                          text=True, capture_output=capture, stdout=stdout)


def https_context() -> ssl.SSLContext:
    if not CA_BUNDLE.is_file():
        raise EnvironmentError("the locked certifi CA bundle is missing; rerun scripts/setup")
    return ssl.create_default_context(cafile=str(CA_BUNDLE))


def download(record: dict, destination_key: str, *, offline: bool = False) -> Path:
    path = local_path(record[destination_key])
    if path.is_file() and sha256(path) == record["sha256"]:
        return path
    if path.exists():
        raise EnvironmentError(f"checksum mismatch: {path}; remove the bad artifact before setup")
    if offline:
        raise EnvironmentError(f"offline setup needs {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=local_path(".runtime/tmp"), delete=False) as stream:
        temporary = Path(stream.name)
    try:
        headers = {"User-Agent": "pgvideo-setup/0.1"}
        if "huggingface.co" in record["url"] and os.environ.get("HF_TOKEN"):
            headers["Authorization"] = "Bearer " + os.environ["HF_TOKEN"]
        request = urllib.request.Request(record["url"], headers=headers)
        with urllib.request.urlopen(request, timeout=90, context=https_context()) as response:
            with temporary.open("wb") as output:
                shutil.copyfileobj(response, output)
        if sha256(temporary) != record["sha256"]:
            raise EnvironmentError(f"download checksum mismatch for {record['url']}")
        temporary.chmod(0o644)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def extract_zip(archive: Path, destination: Path) -> None:
    """Extract an archive with its file modes and symlinks, never leaving destination."""
    destination.mkdir(parents=True)
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            name = PurePosixPath(member.filename)
            if name.is_absolute() or ".." in name.parts:
                raise EnvironmentError(f"archive member escapes its directory: {archive.name}: {member.filename}")
            target = destination.joinpath(*name.parts)
            if not target.parent.resolve().is_relative_to(destination):
                raise EnvironmentError(f"archive member escapes through a symlink: {archive.name}: {member.filename}")
            mode = member.external_attr >> 16
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif stat.S_ISLNK(mode):
                link = source.read(member).decode("utf-8")
                if os.path.isabs(link) or not Path(os.path.normpath(target.parent / link)).is_relative_to(destination):
                    raise EnvironmentError(f"archive symlink escapes its directory: {archive.name}: {member.filename}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(link)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(member) as input_stream, target.open("xb") as output_stream:
                    shutil.copyfileobj(input_stream, output_stream)
                target.chmod(stat.S_IMODE(mode) or 0o644)


def install_ffmpeg(lock: dict, *, offline: bool) -> None:
    for name in ("ffmpeg", "ffprobe"):
        record = lock["ffmpeg"][name]
        target = local_path(record["executable"])
        if target.is_file() and sha256(target) == record["binary_sha256"]:
            continue
        archive = download(record, "archive", offline=offline)
        with zipfile.ZipFile(archive) as source:
            if source.namelist() != [name]:
                raise EnvironmentError(f"unexpected {name} archive contents")
            with source.open(name) as input_stream, target.open("wb") as output_stream:
                shutil.copyfileobj(input_stream, output_stream)
        target.chmod(0o755)
        check_hash(record["executable"], record["binary_sha256"])


def install_sitecustomize() -> None:
    shutil.copyfile(ROOT / "scripts" / "sitecustomize.py", SITE / "sitecustomize.py")


def check_sitecustomize() -> None:
    installed = SITE / "sitecustomize.py"
    if not installed.is_file() or sha256(installed) != sha256(ROOT / "scripts" / "sitecustomize.py"):
        raise EnvironmentError(".venv sitecustomize.py differs from scripts/sitecustomize.py; rerun scripts/setup")


def install_espeak(lock: dict) -> None:
    record = lock["espeak_ng"]
    check_hash("cache/wheels/" + record["source_wheel"], record["source_sha256"])
    site = SITE / "espeakng_loader"
    if not site.is_dir():
        raise EnvironmentError("espeakng-loader is missing from the local environment")
    for source in site.glob("libespeak-ng*.dylib"):
        shutil.copy2(source, local_path(".runtime/lib") / source.name)
    shutil.copytree(site / "espeak-ng-data", local_path(record["data"]), dirs_exist_ok=True)
    executable = local_path(".runtime/bin/espeak-ng")
    shutil.copy2(ROOT / "scripts" / "espeak-ng-runtime", executable)
    executable.chmod(0o755)
    check_hash(record["library"], record["library_sha256"])
    if tree_hash(local_path(record["data"])) != record["data_tree_sha256"]:
        raise EnvironmentError("local espeak-ng pronunciation data differs from tools.lock")


def browser_hashes(lock: dict) -> None:
    record = lock["browser"]["headless_shell"]
    check_hash(record["binary"], record["binary_sha256"])
    if tree_hash(local_path(record["root"])) != record["tree_sha256"]:
        raise EnvironmentError(f"headless Chromium files differ from tools.lock; remove {record['root']} "
                               "and rerun scripts/setup")


def install_browser(lock: dict, *, offline: bool) -> None:
    """Install Playwright's headless Chromium from the archive recorded in tools.lock."""
    record = lock["browser"]["headless_shell"]
    target = local_path(record["root"])
    if target.exists():
        browser_hashes(lock)
        return
    archive = download(record, "archive", offline=offline)
    with tempfile.TemporaryDirectory(prefix="browser-", dir=local_path(".runtime/tmp")) as staging:
        staged = Path(staging) / target.name
        extract_zip(archive, staged)
        # Playwright writes these markers after installing a browser.
        for marker in record["markers"]:
            (staged / marker).touch()
        if tree_hash(staged) != record["tree_sha256"]:
            raise EnvironmentError("extracted headless Chromium differs from tools.lock")
        staged.rename(target)
    browser_hashes(lock)


def requirements() -> dict[str, tuple[str, str]]:
    records = {}
    for line in (ROOT / "requirements.lock").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^ ]+) --hash=sha256:([0-9a-f]{64})", line)
        if match:
            name, version, digest = match.groups()
            records[name.lower().replace("_", "-").replace(".", "-")] = (version, digest)
    if not records:
        raise EnvironmentError("requirements.lock has no pinned packages")
    return records


def wheelhouse_digests() -> set[str]:
    return {sha256(path) for path in local_path("cache/wheels").glob("*.whl")}


def wheelhouse_complete() -> bool:
    return {digest for _, digest in requirements().values()}.issubset(wheelhouse_digests())


def install_ca_bundle(*, offline: bool) -> None:
    """Install the locked certifi wheel so later downloads never read host certificates."""
    line = next((line for line in (ROOT / "requirements.lock").read_text(encoding="utf-8").splitlines()
                 if line.lower().startswith("certifi==")), None)
    if line is None:
        raise EnvironmentError("requirements.lock does not pin certifi")
    wheelhouse = local_path("cache/wheels")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", dir=local_path(".runtime/tmp"), delete=False) as stream:
        stream.write(line + "\n")
        requirement = stream.name
    try:
        if not offline and line.rsplit(":", 1)[1] not in wheelhouse_digests():
            run_local([str(PYTHON), "-I", "-m", "pip", "download", "--only-binary=:all:", "--no-deps",
                       "--dest", str(wheelhouse), "-r", requirement])
        run_local([str(PYTHON), "-I", "-m", "pip", "install", "--no-index", "--no-deps",
                   "--find-links", str(wheelhouse), "--require-hashes", "-r", requirement])
    finally:
        Path(requirement).unlink(missing_ok=True)


def macho_load_commands(path: Path) -> tuple[int, list[tuple[str, bool]], list[str]] | None:
    """Return the file type, linked libraries, and rpaths of an arm64 Mach-O file.

    Reading load commands directly keeps doctor independent of Xcode's otool.
    Files that are not Mach-O return None.
    """
    with path.open("rb") as stream:
        header = stream.read(8)
        if len(header) < 8:
            return None
        offset = 0
        magic, count = struct.unpack(">II", header)
        if magic in FAT_MAGICS:
            if count >= 20:  # Java class files share the universal-binary magic number.
                return None
            entry = FAT_MAGICS[magic]
            slices = [struct.unpack(entry, stream.read(struct.calcsize(entry))) for _ in range(count)]
            offsets = [item[2] for item in slices if item[0] == CPU_TYPE_ARM64]
            if not offsets:
                raise EnvironmentError(f"universal binary has no arm64 code: {path}")
            offset = offsets[0]
        stream.seek(offset)
        header = stream.read(32)
        if len(header) < 32 or struct.unpack_from("<I", header)[0] != MH_MAGIC_64:
            if offset:
                raise EnvironmentError(f"invalid arm64 slice: {path}")
            return None
        _, cpu, _, file_type, command_count, commands_size, _, _ = struct.unpack("<IiiIIIII", header)
        if cpu != CPU_TYPE_ARM64:
            raise EnvironmentError(f"native binary is not arm64: {path}")
        commands = stream.read(commands_size)
    dependencies, rpaths, position = [], [], 0
    for _ in range(command_count):
        command, size = struct.unpack_from("<II", commands, position)
        if command in DYLIB_COMMANDS or command == LC_RPATH:
            (name_offset,) = struct.unpack_from("<I", commands, position + 8)
            name = commands[position + name_offset:position + size].split(b"\0", 1)[0].decode("utf-8")
            if command == LC_RPATH:
                rpaths.append(name)
            else:
                dependencies.append((name, DYLIB_COMMANDS[command]))
        position += size
    return file_type, dependencies, rpaths


def native_binaries(lock: dict):
    roots = (".runtime/python", ".runtime/bin", ".runtime/lib", lock["browser"]["headless_shell"]["root"], ".venv")
    for relative in roots:
        for directory, _, names in os.walk(local_path(relative)):
            for name in names:
                path = Path(directory, name)
                if path.is_symlink() or not path.is_file():
                    continue
                if path.suffix in {".so", ".dylib"} or os.access(path, os.X_OK):
                    yield path


def resolve_dependency(binary: Path, file_type: int, name: str, weak: bool, search: list[Path]) -> None:
    if name.startswith(OS_LIBRARY_PREFIXES):
        return  # Served from the dyld shared cache.
    if name.startswith("@rpath/"):
        candidates = [directory / name.removeprefix("@rpath/") for directory in search]
    elif name.startswith("@loader_path/"):
        candidates = [binary.parent / name.removeprefix("@loader_path/")]
    elif name.startswith("@executable_path/") and file_type == MH_EXECUTE:
        candidates = [binary.parent / name.removeprefix("@executable_path/")]
    elif name.startswith("/"):
        candidates = [Path(name)]
    else:
        raise EnvironmentError(f"cannot resolve native dependency {name} of {binary}")
    for candidate in candidates:
        if candidate.exists():
            if not candidate.resolve().is_relative_to(ROOT):
                raise EnvironmentError(f"native dependency escapes project: {binary}: {candidate}")
            return
    if not weak:
        raise EnvironmentError(f"native dependency is missing: {binary}: {name}")


def check_native_binary(binary: Path) -> list[str] | None:
    """Resolve a binary's libraries the way dyld would and require them inside the project.

    Returns rpaths outside the project that no dependency uses, or None for non-Mach-O files.
    """
    parsed = macho_load_commands(binary)
    if parsed is None:
        return None
    file_type, dependencies, rpaths = parsed
    search = []
    for rpath in rpaths:
        if rpath.startswith("@loader_path"):
            search.append(binary.parent / rpath.removeprefix("@loader_path").lstrip("/"))
        elif rpath.startswith("@executable_path"):
            if file_type == MH_EXECUTE:
                search.append(binary.parent / rpath.removeprefix("@executable_path").lstrip("/"))
        else:
            search.append(Path(rpath))
    for name, weak in dependencies:
        resolve_dependency(binary, file_type, name, weak, search)
    if any(name.startswith("@rpath/") for name, _ in dependencies):
        return []
    return [str(directory) for directory in search if not directory.resolve(strict=False).is_relative_to(ROOT)]


def check_native_libraries(lock: dict) -> dict:
    checked, unused_rpaths = 0, {}
    for binary in native_binaries(lock):
        external = check_native_binary(binary)
        if external is None:
            continue
        checked += 1
        for directory in external:
            unused_rpaths.setdefault(directory, []).append(str(binary.relative_to(ROOT)))
    return {"binaries": checked, "unused_external_rpaths": unused_rpaths}


def isolation_policy() -> dict:
    policy = os.environ.get("PGVIDEO_SANDBOX", "")
    return {
        "enforcement": "macOS Seatbelt through /usr/bin/sandbox-exec",
        "policy": policy,
        "network": {"network": "allowed", "offline": "IP connections denied",
                    "audit": "IP connections terminate the process"}.get(policy, "inherited from parent"),
        "project_access": "read, write, and execute",
        "os_reads": [description for _, description in OS_READS],
        "os_writes": [description for _, description in OS_WRITES],
        "os_executables": list(OS_EXECUTABLES),
        "profile": (audit_profile() if policy == "audit" else
                    seatbelt_profile(network=policy == "network") if policy in {"network", "offline"} else None),
    }


def run_sample() -> dict:
    result = run_local([str(PYTHON), "-I", str(ROOT / "scripts" / "sample_environment.py")], stdout=subprocess.PIPE)
    details = json.loads(result.stdout.strip().splitlines()[-1])
    return {"status": "passed", "policy": os.environ.get("PGVIDEO_SANDBOX", ""),
            "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "fingerprint": environment_fingerprint(), **details}


def recorded_sample() -> dict:
    """Keep the last sample result while the locks and scripts it covered are unchanged."""
    try:
        sample = json.loads(REPORT.read_text(encoding="utf-8"))["isolation"]["sample"]
        if sample.get("status") == "passed" and sample.get("fingerprint") == environment_fingerprint():
            return sample
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return {"status": "not run for this environment; run scripts/pgvideo doctor --sample"}


def recorded_audit() -> dict:
    """Keep the last audit result while the locks and scripts it covered are unchanged."""
    try:
        audit = json.loads(REPORT.read_text(encoding="utf-8"))["isolation"]["audit"]
        if audit.get("fingerprint") == environment_fingerprint():
            if audit.get("status") == "running" and os.environ.get("PGVIDEO_SANDBOX") != "audit":
                return audit | {"status": "incomplete", "error": "the audit stopped before it finished; a process "
                                "may have been terminated for an undocumented access. Run scripts/pgvideo audit "
                                "again and watch which step it stops in."}
            return audit
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return {"status": "not run for this environment; run scripts/pgvideo audit"}


def record_audit(result: dict) -> None:
    try:
        report = json.loads(REPORT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        report = {"status": "not checked", "isolation": {}}
    report.setdefault("isolation", {})["audit"] = result
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def audit(lock: dict) -> None:
    """Repeat setup --offline and the offline sample under the kill-on-access audit profile.

    Any read, write, or execution outside the project and the documented operating system
    paths, and any IP connection, terminates the process that attempts it, so a passing
    audit shows that nothing else is accessed. Only the documented attempts listed in
    AUDIT_KNOWN_* are denied without terminating.
    """
    if os.environ.get("PGVIDEO_SANDBOX") != "audit":
        raise EnvironmentError("audit must start from scripts/pgvideo outside other sandboxes")
    record = {"status": "running", "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
              "fingerprint": environment_fingerprint(), "profile": audit_profile(),
              "steps": ["setup --offline", "doctor --sample: Kokoro synthesis, Chromium slide, FFmpeg encode and "
                        "decode"],
              "terminates_on": ["reading file contents, writing, or executing outside the project and the "
                                "operating system paths in os_requirements", "any outbound IP connection"],
              "denied_without_termination": [description for _, description in
                                             (*AUDIT_KNOWN_READS, *AUDIT_KNOWN_WRITES, *AUDIT_KNOWN_EXECUTABLES)]}
    record_audit(record)
    try:
        print("Audit: setup --offline under the kill-on-access profile", flush=True)
        setup(lock, offline=True)
        print("Audit: doctor --sample (Kokoro synthesis, Chromium slide, FFmpeg encode and decode)", flush=True)
        doctor(lock, sample=True, announce=False)
    except (EnvironmentError, OSError, subprocess.CalledProcessError) as error:
        record_audit(record | {"status": "failed", "error": str(error)})
        raise
    record_audit(record | {"status": "passed",
                           "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")})
    print(f"Audit passed: {REPORT}")


def setup(lock: dict, *, offline: bool) -> None:
    wheelhouse = local_path("cache/wheels")
    install_sitecustomize()
    install_ca_bundle(offline=offline)
    download(lock["spacy_model"], "path", offline=offline)
    if not offline and not wheelhouse_complete():
        run_local([str(PYTHON), "-I", "-m", "pip", "download", "--only-binary=:all:",
                   "--dest", str(wheelhouse), "--find-links", str(wheelhouse),
                   "-r", str(ROOT / "requirements.lock")])
    run_local([str(PYTHON), "-I", "-m", "pip", "install", "--no-index", "--no-build-isolation",
               "--find-links", str(wheelhouse), "--require-hashes", "-r", str(ROOT / "requirements.lock")])
    run_local([str(PYTHON), "-I", "-m", "pip", "install", "--no-index", "--no-build-isolation",
               "--no-deps", "--editable", str(ROOT)])
    for record in lock["fonts"].values():
        if isinstance(record, dict):
            download(record, "path", offline=offline)
    for record in lock["kokoro"].values():
        if isinstance(record, dict):
            download(record, "path", offline=offline)
    install_ffmpeg(lock, offline=offline)
    install_espeak(lock)
    install_browser(lock, offline=offline)
    doctor(lock, sample=False)


def doctor(lock: dict, *, sample: bool, announce: bool = True) -> None:
    problems = []
    checks = {}
    isolation = isolation_policy()
    sample_result = recorded_sample()
    try:
        validate_python(lock)
        checks["python"] = "passed"
        isolation["probes"] = sandbox_probes(isolation["policy"])
        installed = {}
        for name, (version, _) in requirements().items():
            dist = importlib.metadata.distribution(name)
            if dist.version != version or not Path(dist.locate_file("")).resolve().is_relative_to(SITE):
                raise EnvironmentError(f"package {name} is outside the project or has the wrong version")
            installed[name] = dist.version
        checks["packages"] = installed
        check_sitecustomize()
        run_local([str(PYTHON), "-I", "-m", "pip", "check"], capture=True)
        for name in ("ffmpeg", "ffprobe"):
            record = lock["ffmpeg"][name]
            check_hash(record["executable"], record["binary_sha256"])
        result = run_local([str(local_path(".runtime/bin/ffmpeg")), "-hide_banner", "-encoders"], capture=True)
        if "libx264" not in result.stdout or not re.search(r"\baac\b", result.stdout):
            raise EnvironmentError("local FFmpeg lacks libx264 or AAC encoding")
        result = run_local([str(local_path(".runtime/bin/ffmpeg")), "-hide_banner", "-filters"], capture=True)
        if "loudnorm" not in result.stdout or "aresample" not in result.stdout:
            raise EnvironmentError("local FFmpeg lacks required audio filters")
        checks["ffmpeg"] = lock["ffmpeg"]["version"]
        check_hash(lock["espeak_ng"]["library"], lock["espeak_ng"]["library_sha256"])
        if tree_hash(local_path(lock["espeak_ng"]["data"])) != lock["espeak_ng"]["data_tree_sha256"]:
            raise EnvironmentError("espeak-ng data checksum mismatch")
        executable = local_path(".runtime/bin/espeak-ng")
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise EnvironmentError("project-local eSpeak NG entry point is missing")
        version = run_local([str(executable), "--version"], capture=True)
        if "1.52.0" not in version.stdout:
            raise EnvironmentError("project-local eSpeak NG version is wrong")
        checks["espeak_ng"] = lock["espeak_ng"]["version"]
        browser_hashes(lock)
        checks["browser"] = lock["browser"]["chromium_version"]
        checks["native_binaries"] = check_native_libraries(lock)
        if not wheelhouse_complete():
            raise EnvironmentError("wheelhouse is missing a locked artifact")
        checks["wheelhouse"] = "passed"
        for record in lock["kokoro"].values():
            if isinstance(record, dict):
                check_hash(record["path"], record["sha256"])
        for record in lock["fonts"].values():
            if isinstance(record, dict):
                check_hash(record["path"], record["sha256"])
        checks["assets"] = "passed"
        for relative in DIRECTORIES:
            path = local_path(relative)
            if not path.is_dir() or not os.access(path, os.W_OK):
                raise EnvironmentError(f"project directory is not writable: {relative}")
            with tempfile.NamedTemporaryFile(prefix=".pgvideo-write-", dir=path) as probe:
                probe.write(b"ok")
                probe.flush()
        checks["directories"] = "passed"
        if sample:
            sample_result = run_sample()
    except (EnvironmentError, OSError, ValueError, subprocess.CalledProcessError,
            importlib.metadata.PackageNotFoundError) as error:
        message = str(error)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr and error.stderr.strip():
            message += ": " + error.stderr.strip().splitlines()[-1]
        problems.append(message)
        if sample:
            sample_result = {"status": "failed", "error": message}
    isolation["sample"] = sample_result
    isolation["audit"] = recorded_audit()
    report = {
        "status": "passed" if not problems else "failed",
        "project_root": str(ROOT),
        "platform": {"system": platform.system(), "release": platform.release(), "architecture": platform.machine()},
        "python": {"executable": sys.executable, "version": platform.python_version(), "base_prefix": sys.base_prefix,
                   "prefix": sys.prefix, "import_paths": sys.path},
        "environment_paths": {key: value for key, value in controlled_environment().items() if key not in PASSTHROUGH},
        "checks": checks,
        "isolation": isolation,
        "artifacts": {
            "ffmpeg": {"version": lock["ffmpeg"]["version"],
                       "executable": str(ROOT / lock["ffmpeg"]["ffmpeg"]["executable"]),
                       "ffprobe": str(ROOT / lock["ffmpeg"]["ffprobe"]["executable"])},
            "espeak_ng": {"version": lock["espeak_ng"]["version"],
                          "executable": str(ROOT / lock["espeak_ng"]["executable"]),
                          "library": str(ROOT / lock["espeak_ng"]["library"]),
                          "data": str(ROOT / lock["espeak_ng"]["data"])},
            "browser": {"version": lock["browser"]["chromium_version"],
                        "headless": str(ROOT / lock["browser"]["headless_shell"]["binary"])},
            "kokoro": {name: str(ROOT / record["path"]) for name, record in lock["kokoro"].items()
                       if isinstance(record, dict)},
            "fonts": {name: str(ROOT / record["path"]) for name, record in lock["fonts"].items()
                      if isinstance(record, dict)},
        },
        "errors": problems,
        "os_requirements": [
            "macOS kernel, dyld, and Seatbelt enforcement through /usr/bin/sandbox-exec",
            "reading " + ", ".join(description for _, description in OS_READS),
            "writing " + ", ".join(description for _, description in OS_WRITES),
            "running " + ", ".join(OS_EXECUTABLES) + " for the launcher scripts",
            "system services reached over Mach IPC, such as DNS, proxy settings, and fonts",
            "network access for setup and generate: GitHub, PyPI, Hugging Face, the Playwright CDN, and the FFmpeg build host",
            "bootstrap before the sandbox starts: " + ", ".join(BOOTSTRAP_TOOLS),
            "the platform null device for PIP_CONFIG_FILE and OPENSSL_CONF",
        ],
        "isolation_limitations": [
            "Seatbelt restricts reading file contents, but not metadata lookups such as stat of parent directories.",
            "Mach IPC is not restricted; system services such as DNS, proxy configuration, and font services act for the process.",
            "Seatbelt does not log denied attempts on this host. scripts/pgvideo audit repeats setup --offline and "
            "the sample under a profile that terminates any process reading, writing, or executing outside the "
            "project and the paths above, or opening an IP connection; only the attempts listed in "
            "isolation.audit.denied_without_termination are denied without terminating.",
            "The audit does not cover metadata lookups, Mach IPC, the bootstrap in scripts/setup, or the network "
            "retrieval of setup and generate.",
            "scripts/setup downloads, verifies, and unpacks the Python runtime and creates .venv before the sandbox applies.",
            "sandbox-exec is deprecated by Apple; if it is removed, commands fail instead of running unconfined.",
        ],
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if problems:
        raise EnvironmentError("doctor failed: " + "; ".join(problems))
    if announce:
        if sample:
            files = (sample_result[name]["file"] for name in ("narration", "slide", "video"))
            print("Offline sample: " + ", ".join(str(ROOT / file) for file in files))
        print(f"Environment ready: {REPORT}")


def main() -> int:
    if not sys.argv[1:]:
        raise EnvironmentError("use scripts/pgvideo doctor, test, audit, generate --document ..., "
                               "resume --request ..., or script --request ...")
    create_directories()
    restart_clean(sys.argv[1])
    lock = read_lock()
    validate_python(lock)
    command = sys.argv[1]
    if command == "setup":
        if sys.argv[2:] not in ([], ["--offline"]):
            raise EnvironmentError("setup accepts only --offline")
        setup(lock, offline="--offline" in sys.argv[2:])
        return 0
    if command == "doctor":
        if sys.argv[2:] not in ([], ["--sample"]):
            raise EnvironmentError("doctor accepts only --sample")
        doctor(lock, sample="--sample" in sys.argv[2:])
        return 0
    if command == "audit":
        if sys.argv[2:]:
            raise EnvironmentError("audit accepts no arguments")
        audit(lock)
        return 0
    if command == "test":
        if sys.argv[2:]:
            raise EnvironmentError("test accepts no arguments")
        doctor(lock, sample=False, announce=False)
        return run_local([str(PYTHON), "-I", "-m", "unittest", "discover", "-s", "tests", "-v"],
                         check=False).returncode
    doctor(lock, sample=False, announce=False)
    # Pass the application's exit status through; it reports its own errors.
    return run_local([str(PYTHON), "-I", "-m", "pgvideo", *sys.argv[1:]], check=False).returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EnvironmentError, OSError, subprocess.CalledProcessError) as error:
        print(f"pgvideo environment: {error}", file=sys.stderr)
        raise SystemExit(1)
