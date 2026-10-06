"""Shared setup, launcher, test, and doctor environment for this checkout.

This file uses only the standard library so it can validate paths before
loading any project dependency. It must be run by the project's .venv Python.
Every command confines itself with Landlock and, when offline, a seccomp
filter, then re-executes; file access is limited to the project and a
documented set of operating system paths.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import importlib.metadata
import json
import os
import platform
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
# Model inference is the external harness's job; no pgvideo command calls a model or carries its credentials.
NETWORK_COMMANDS = {"setup", "prepare"}
# Operating system locations a sandboxed command may use besides the project.
# Landlock attaches a rule to the file or directory a path resolves to, so /lib, /lib64, and /bin
# are covered where they are links into /usr. Paths a host lacks are skipped.
OS_READS = (
    ("/usr/lib", "/usr/lib system libraries, the dynamic loader, and the locale archive"),
    ("/usr/lib64", "/usr/lib64 system libraries"),
    ("/lib", "/lib system libraries"),
    ("/lib64", "/lib64 system libraries"),
    ("/etc/ld.so.cache", "/etc/ld.so.cache, the dynamic loader's library index"),
    ("/usr/share/zoneinfo", "/usr/share/zoneinfo time zone data"),
    # pip names the distribution in its user agent and fails if this file exists but cannot be read.
    ("/etc/debian_version", "/etc/debian_version"),
    ("/proc", "/proc process and kernel information"),
    # Chromium's GPU process exits unless it can list the PCI devices, whose entries link into /sys/devices.
    ("/sys/devices", "/sys/devices hardware description, including processor topology"),
    ("/sys/bus/pci/devices", "/sys/bus/pci/devices, the list of PCI devices"),
    ("/dev/null", "/dev/null"),
    ("/dev/zero", "/dev/zero"),
    ("/dev/random", "/dev/random"),
    ("/dev/urandom", "/dev/urandom"),
    ("/dev/tty", "/dev/tty"),
    ("/dev/pts", "/dev/pts terminals"),
)
# Name resolution for the commands that download. Offline commands cannot read these.
NETWORK_READS = (
    ("/etc/resolv.conf", "/etc/resolv.conf"),
    ("/run/systemd/resolve", "/run/systemd/resolve, where /etc/resolv.conf points under systemd-resolved"),
    ("/etc/hosts", "/etc/hosts"),
    ("/etc/nsswitch.conf", "/etc/nsswitch.conf"),
    ("/etc/host.conf", "/etc/host.conf"),
    ("/etc/gai.conf", "/etc/gai.conf"),
)
OS_WRITES = (
    ("/dev/null", "/dev/null"),
    ("/dev/tty", "/dev/tty"),
    ("/dev/pts", "/dev/pts terminals"),
)
# /bin/sh runs the launcher scripts. The kernel starts every dynamically linked program, including
# the project's Python, through the dynamic loader.
OS_EXECUTABLES = ("/bin/sh", "/bin/bash", "/bin/dash", "/lib64/ld-linux-x86-64.so.2")
BOOTSTRAP_TOOLS = ("/bin/sh", "/bin/mkdir", "/usr/bin/uname", "/usr/bin/curl",
                   "/usr/bin/sha256sum", "/usr/bin/tar", "/usr/bin/env")
# A file every Linux host lets any user read; the project sandbox denies it.
SANDBOX_CANARY = "/etc/passwd"

# glibc has no wrappers for Landlock, so the rules are installed through syscall(2).
SYS_LANDLOCK_CREATE_RULESET, SYS_LANDLOCK_ADD_RULE, SYS_LANDLOCK_RESTRICT_SELF = 444, 445, 446
LANDLOCK_CREATE_RULESET_VERSION = 1
LANDLOCK_RULE_PATH_BENEATH = 1
LANDLOCK_MINIMUM_ABI = 4  # Linux 6.7, the first with TCP rules. The filesystem rights below need ABI 3.
LANDLOCK_FS = {name: 1 << bit for bit, name in enumerate((
    "execute", "write_file", "read_file", "read_dir", "remove_dir", "remove_file", "make_char", "make_dir",
    "make_reg", "make_sock", "make_fifo", "make_block", "make_sym", "refer", "truncate"))}
LANDLOCK_FILE_RIGHTS = ("execute", "write_file", "read_file", "truncate")  # the rights a rule on a file may grant
LANDLOCK_NET_TCP = 0b11  # bind and connect
ACCESS = {
    "read": ("read_file", "read_dir"),
    "write": ("write_file", "truncate"),
    "create": ("remove_dir", "remove_file", "make_char", "make_dir", "make_reg", "make_sock", "make_fifo",
               "make_block", "make_sym", "refer"),
    "execute": ("execute",),
}
PR_SET_SECCOMP, PR_SET_NO_NEW_PRIVS, PR_GET_NO_NEW_PRIVS = 22, 38, 39
SECCOMP_MODE_FILTER = 2
SECCOMP_RET_KILL_PROCESS, SECCOMP_RET_ERRNO, SECCOMP_RET_ALLOW = 0x80000000, 0x00050000, 0x7FFF0000
AUDIT_ARCH_X86_64 = 0xC000003E
X32_SYSCALL_BIT = 0x40000000
SYS_SOCKET, SYS_IO_URING_SETUP = 41, 425

ELF_MAGIC = b"\x7fELF"
ELF_64_BIT_LITTLE_ENDIAN = b"\x02\x01"
EM_X86_64 = 62
PT_LOAD, PT_DYNAMIC, PT_INTERP = 1, 2, 3
DT_NEEDED, DT_STRTAB, DT_RPATH, DT_RUNPATH = 1, 5, 15, 29
# Where the dynamic loader finds a library that no search path of the binary provides.
OS_LIBRARY_DIRECTORIES = ("/lib/x86_64-linux-gnu", "/usr/lib/x86_64-linux-gnu", "/lib64", "/usr/lib64",
                          "/lib", "/usr/lib")
OS_LIBRARY_PREFIXES = ("/usr/lib/", "/usr/lib64/", "/lib/", "/lib64/")


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
        "TZ": "UTC",
        "SSL_CERT_FILE": str(CA_BUNDLE),
        "SSL_CERT_DIR": str(CA_BUNDLE.parent),
        # Keep OpenSSL from loading the host's /etc/ssl/openssl.cnf.
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
        # Chromium loads no font without a Fontconfig configuration; this one lists only the bundled fonts.
        "FONTCONFIG_FILE": f"{root}/assets/fonts/fonts.conf",
        "PHONEMIZER_ESPEAK_LIBRARY": f"{root}/.runtime/lib/libespeak-ng.so",
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


def sandbox_profile(*, network: bool) -> dict:
    """Return the Landlock and seccomp policy applied to every command in this project."""
    reads = (*OS_READS, *NETWORK_READS) if network else OS_READS
    rules = [{"path": str(ROOT), "access": ["read", "write", "create", "execute"]}]
    rules += [{"path": path, "access": ["read"]} for path, _ in reads]
    rules += [{"path": path, "access": ["write"]} for path, _ in OS_WRITES]
    # The kernel opens a program for reading in order to run it, so execution needs both rights.
    rules += [{"path": path, "access": ["read", "execute"]} for path in OS_EXECUTABLES]
    return {
        "landlock": {"handled_access": sorted(LANDLOCK_FS), "rules": rules,
                     "tcp_bind_and_connect": "allowed" if network else "denied"},
        "seccomp": None if network else {"socket_families_denied": ["AF_INET", "AF_INET6"],
                                         "system_calls_denied": ["io_uring_setup"]},
    }


def seccomp_filter() -> bytes:
    """Return the BPF program that keeps an offline command from creating IPv4 or IPv6 sockets."""
    load, equal, at_least, result = 0x20, 0x15, 0x35, 0x06
    program = (
        (load, 0, 0, 4),  # the architecture of the system call
        (equal, 1, 0, AUDIT_ARCH_X86_64),
        (result, 0, 0, SECCOMP_RET_KILL_PROCESS),  # 32-bit entry points number their system calls differently
        (load, 0, 0, 0),  # the system call number
        (at_least, 0, 1, X32_SYSCALL_BIT),
        (result, 0, 0, SECCOMP_RET_ERRNO | errno.ENOSYS),
        (equal, 0, 1, SYS_IO_URING_SETUP),  # io_uring can create a socket without calling socket
        (result, 0, 0, SECCOMP_RET_ERRNO | errno.ENOSYS),
        (equal, 1, 0, SYS_SOCKET),
        (result, 0, 0, SECCOMP_RET_ALLOW),
        (load, 0, 0, 16),  # the address family, socket's first argument
        (equal, 1, 0, socket.AF_INET),
        (equal, 0, 1, socket.AF_INET6),
        (result, 0, 0, SECCOMP_RET_ERRNO | errno.EACCES),
        (result, 0, 0, SECCOMP_RET_ALLOW),
    )
    return b"".join(struct.pack("HBBI", *instruction) for instruction in program)


def apply_sandbox(profile: dict) -> None:
    """Confine this process, and every program it starts, to the profile. This cannot be undone."""
    if platform.machine() != "x86_64":
        raise EnvironmentError("the project sandbox supports Linux x86_64 only")
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    word = ctypes.c_long

    def failed(action: str) -> EnvironmentError:
        return EnvironmentError(f"cannot {action}: {os.strerror(ctypes.get_errno())}; "
                                "project containment cannot be enforced")

    abi = libc.syscall(word(SYS_LANDLOCK_CREATE_RULESET), None, word(0), word(LANDLOCK_CREATE_RULESET_VERSION))
    if abi < LANDLOCK_MINIMUM_ABI:
        raise EnvironmentError(f"this kernel does not provide Landlock ABI {LANDLOCK_MINIMUM_ABI} (Linux 6.7 or "
                               "newer with the landlock security module enabled); project containment cannot "
                               "be enforced")
    landlock = profile["landlock"]
    handled = struct.pack("QQ", sum(LANDLOCK_FS[right] for right in landlock["handled_access"]),
                          0 if landlock["tcp_bind_and_connect"] == "allowed" else LANDLOCK_NET_TCP)
    ruleset = libc.syscall(word(SYS_LANDLOCK_CREATE_RULESET), handled, word(len(handled)), word(0))
    if ruleset < 0:
        raise failed("create the Landlock ruleset")
    try:
        for rule in landlock["rules"]:
            try:
                descriptor = os.open(rule["path"], os.O_PATH | os.O_CLOEXEC)
            except FileNotFoundError:
                continue
            try:
                rights = {right for name in rule["access"] for right in ACCESS[name]}
                if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                    rights &= set(LANDLOCK_FILE_RIGHTS)
                allowed = struct.pack("=Qi", sum(LANDLOCK_FS[right] for right in rights), descriptor)
                if libc.syscall(word(SYS_LANDLOCK_ADD_RULE), word(ruleset), word(LANDLOCK_RULE_PATH_BENEATH),
                                allowed, word(0)):
                    raise failed(f"add the Landlock rule for {rule['path']}")
            finally:
                os.close(descriptor)
        # Required before an unprivileged process may restrict itself; it also disables setuid programs.
        if libc.prctl(word(PR_SET_NO_NEW_PRIVS), word(1), word(0), word(0), word(0)):
            raise failed("set no_new_privs")
        if libc.syscall(word(SYS_LANDLOCK_RESTRICT_SELF), word(ruleset), word(0)):
            raise failed("apply the Landlock ruleset")
    finally:
        os.close(ruleset)
    if profile["seccomp"]:
        instructions = seccomp_filter()
        buffer = ctypes.create_string_buffer(instructions, len(instructions))
        program = struct.pack("HP", len(instructions) // 8, ctypes.addressof(buffer))
        if libc.prctl(word(PR_SET_SECCOMP), word(SECCOMP_MODE_FILTER), program, word(0), word(0)):
            raise failed("install the seccomp filter")


def sandboxed() -> bool:
    """Return whether this process already runs without new privileges and without access to host files."""
    if ctypes.CDLL(None).prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0) != 1:
        return False
    try:
        with open(SANDBOX_CANARY, "rb"):
            return False
    except PermissionError:
        return True
    except OSError as error:
        raise EnvironmentError(f"cannot determine whether the project sandbox is active: {error}") from error


def restart_clean(command: str) -> None:
    expected = controlled_environment()
    if os.environ.get("PGVIDEO_ENV_READY") != "1":
        arguments = [str(PYTHON), "-I", str(Path(__file__).resolve()), *sys.argv[1:]]
        if sandboxed():
            # Another layer could only narrow the sandbox, so a command started by a
            # sandboxed parent (the test suite) keeps that policy. Doctor probes it
            # before any command runs.
            expected["PGVIDEO_SANDBOX"] = "inherited"
            os.execve(str(PYTHON), arguments, expected)
        policy = "network" if command in NETWORK_COMMANDS and "--offline" not in sys.argv[2:] else "offline"
        apply_sandbox(sandbox_profile(network=policy == "network"))
        expected["PGVIDEO_SANDBOX"] = policy
        os.execve(str(PYTHON), arguments, expected)
    expected["PGVIDEO_SANDBOX"] = os.environ.get("PGVIDEO_SANDBOX", "")
    if expected["PGVIDEO_SANDBOX"] not in {"network", "offline", "inherited"} or not sandboxed():
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
    probe = Path("/tmp") / f"pgvideo-sandbox-probe-{os.getpid()}"
    try:
        descriptor = os.open(probe, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except PermissionError:
        results["write /tmp"] = "denied"
    else:
        os.close(descriptor)
        probe.unlink()
        raise EnvironmentError(f"{sandbox} allowed a write outside the project{advice}")
    try:
        Path(SANDBOX_CANARY).read_bytes()
    except PermissionError:
        results[f"read {SANDBOX_CANARY}"] = "denied"
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
            if policy == "offline":
                raise EnvironmentError("the offline sandbox did not deny outbound network access")
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
        raise EnvironmentError("this tools.lock supports Linux x86_64 only")
    try:
        library, version = os.confstr("CS_GNU_LIBC_VERSION").split()
    except (AttributeError, OSError, ValueError) as error:
        raise EnvironmentError("the pinned wheels and Python runtime need glibc") from error
    minimum = lock["platform"]["minimum_glibc"]
    if library != "glibc" or [int(part) for part in version.split(".")] < [int(part) for part in minimum.split(".")]:
        raise EnvironmentError(f"glibc is older than {minimum}, which the pinned wheels require")
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
    for source in site.glob("libespeak-ng.so*"):
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


def elf_dynamic(path: Path) -> tuple[list[str], list[str], str | None] | None:
    """Return the needed libraries, library search paths, and program interpreter of an x86_64 ELF file.

    Reading the dynamic section directly keeps doctor independent of binutils' readelf.
    Files that are not ELF return None.
    """
    with path.open("rb") as stream:
        header = stream.read(64)
        if len(header) < 64 or header[:4] != ELF_MAGIC:
            return None
        if header[4:6] != ELF_64_BIT_LITTLE_ENDIAN or struct.unpack_from("<H", header, 18)[0] != EM_X86_64:
            raise EnvironmentError(f"native binary is not x86_64: {path}")
        (table_offset,) = struct.unpack_from("<Q", header, 32)
        entry_size, count = struct.unpack_from("<HH", header, 54)
        stream.seek(table_offset)
        table = stream.read(entry_size * count)
        # Each program header starts with its type, flags, file offset, address, physical address, and file size.
        segments = [struct.unpack_from("<IIQQQQ", table, index * entry_size) for index in range(count)]

        def text_at(offset: int) -> str:
            stream.seek(offset)
            raw = b""
            while b"\0" not in raw and (block := stream.read(256)):
                raw += block
            return raw.split(b"\0", 1)[0].decode("utf-8")

        interpreter, entries = None, {}
        for kind, _, offset, _, _, size in segments:
            if kind == PT_INTERP:
                interpreter = text_at(offset)
            elif kind == PT_DYNAMIC:
                stream.seek(offset)
                dynamic = stream.read(size)
                for position in range(0, len(dynamic) - 15, 16):
                    tag, value = struct.unpack_from("<qQ", dynamic, position)
                    if tag == 0:
                        break
                    entries.setdefault(tag, []).append(value)
        if DT_STRTAB not in entries:
            return [], [], interpreter  # statically linked
        address = entries[DT_STRTAB][0]
        strings = next((offset + address - start for kind, _, offset, start, _, size in segments
                        if kind == PT_LOAD and start <= address < start + size), None)
        if strings is None:
            raise EnvironmentError(f"invalid dynamic section: {path}")
        needed = [text_at(strings + value) for value in entries.get(DT_NEEDED, [])]
        # The loader ignores DT_RPATH when the file has DT_RUNPATH.
        paths = [text_at(strings + value) for value in entries.get(DT_RUNPATH) or entries.get(DT_RPATH, [])]
    return needed, [item for value in paths for item in value.split(":") if item], interpreter


def native_binaries(lock: dict):
    roots = (".runtime/python", ".runtime/bin", ".runtime/lib", lock["browser"]["headless_shell"]["root"], ".venv")
    for relative in roots:
        for directory, _, names in os.walk(local_path(relative)):
            for name in names:
                path = Path(directory, name)
                if path.is_symlink() or not path.is_file():
                    continue
                if ".so" in path.suffixes or os.access(path, os.X_OK):
                    yield path


def os_library(path: Path) -> bool:
    return str(path.resolve()).startswith(OS_LIBRARY_PREFIXES)


def resolve_dependency(binary: Path, name: str, search: list[Path], bundled: frozenset[str]) -> None:
    if "/" in name:
        if not name.startswith("/"):
            raise EnvironmentError(f"cannot resolve native dependency {name} of {binary}")
        candidates = [Path(os.path.normpath(name))]
    else:
        candidates = [directory / name for directory in search]
    for candidate in candidates:
        if candidate.exists():
            if not candidate.resolve().is_relative_to(ROOT) and not os_library(candidate):
                raise EnvironmentError(f"native dependency escapes project: {binary}: {candidate}")
            return
    if "/" not in name and any(Path(directory, name).exists() for directory in OS_LIBRARY_DIRECTORIES):
        return  # A system library, which the loader finds without a search path.
    if name in bundled:
        # Only a library of the project can satisfy it: one the loading program has already
        # loaded, as Python packages do for their extension modules, or none at all.
        return
    raise EnvironmentError(f"native dependency is missing: {binary}: {name}")


def check_native_binary(binary: Path, bundled: frozenset[str] = frozenset()) -> list[str] | None:
    """Resolve a binary's libraries the way the dynamic loader would and require them inside the project
    or among the system libraries. bundled names the libraries the project ships anywhere.

    Returns search paths outside the project, which provide none of its libraries, or None for non-ELF files.
    """
    parsed = elf_dynamic(binary)
    if parsed is None:
        return None
    needed, paths, interpreter = parsed
    if interpreter is not None and interpreter not in OS_EXECUTABLES:
        raise EnvironmentError(f"native binary needs a loader the sandbox does not run: {binary}: {interpreter}")
    origin = str(binary.parent)
    # The loader replaces $ORIGIN, in search paths and library names alike, with the binary's directory.
    needed, paths = ([item.replace("${ORIGIN}", origin).replace("$ORIGIN", origin) for item in items]
                     for items in (needed, paths))
    search = [Path(os.path.normpath(item)) for item in paths]
    for name in needed:
        resolve_dependency(binary, name, search, bundled)
    return [str(directory) for directory in dict.fromkeys(search)
            if not directory.resolve(strict=False).is_relative_to(ROOT) and not os_library(directory)]


def check_native_libraries(lock: dict) -> dict:
    checked, unused_rpaths = 0, {}
    binaries = list(native_binaries(lock))
    bundled = frozenset(binary.name for binary in binaries)
    for binary in binaries:
        external = check_native_binary(binary, bundled)
        if external is None:
            continue
        checked += 1
        for directory in external:
            unused_rpaths.setdefault(directory, []).append(str(binary.relative_to(ROOT)))
    return {"binaries": checked, "unused_external_rpaths": unused_rpaths}


def isolation_policy() -> dict:
    policy = os.environ.get("PGVIDEO_SANDBOX", "")
    return {
        "enforcement": "Linux Landlock and seccomp, applied by scripts/environment.py before each command",
        "policy": policy,
        "network": {"network": "allowed", "offline": "IP sockets denied"}.get(policy, "inherited from parent"),
        "project_access": "read, write, and execute",
        "os_reads": [description for _, description in OS_READS],
        "network_reads": [description for _, description in NETWORK_READS],
        "os_writes": [description for _, description in OS_WRITES],
        "os_executables": list(OS_EXECUTABLES),
        "profile": sandbox_profile(network=policy == "network") if policy in {"network", "offline"} else None,
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


def setup(lock: dict, *, offline: bool) -> None:
    wheelhouse = local_path("cache/wheels")
    install_sitecustomize()
    install_ca_bundle(offline=offline)
    download(lock["spacy_model"], "path", offline=offline)
    download(lock["torch"], "path", offline=offline)
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
        if "libx264" not in result.stdout or "libopus" not in result.stdout:
            raise EnvironmentError("local FFmpeg lacks libx264 or libopus encoding")
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
            f"Linux x86_64 with Landlock ABI {LANDLOCK_MINIMUM_ABI} (Linux 6.7 or newer), seccomp filters, and glibc "
            f"{lock['platform']['minimum_glibc']} or newer",
            "reading " + ", ".join(description for _, description in OS_READS),
            "reading, for setup and prepare only, " + ", ".join(description for _, description in NETWORK_READS),
            "writing " + ", ".join(description for _, description in OS_WRITES),
            "running " + ", ".join(OS_EXECUTABLES) + " for the launcher scripts and dynamically linked programs",
            "the system libraries headless Chromium links to; checks.native_binaries fails when one is missing",
            "system services reached over Unix-domain sockets, such as systemd-resolved for DNS",
            "network access for setup and prepare: GitHub, PyPI, download.pytorch.org, Hugging Face, the Playwright "
            "CDN, and the FFmpeg build host",
            "bootstrap before the sandbox starts: " + ", ".join(BOOTSTRAP_TOOLS),
            "the platform null device for PIP_CONFIG_FILE and OPENSSL_CONF",
        ],
        "isolation_limitations": [
            "Landlock restricts opening files and listing directories, but not metadata lookups such as stat of "
            "parent directories.",
            "/proc is readable, including the entries other processes leave readable to every user.",
            "Unix-domain sockets, signals, and other local IPC are not restricted; system services such as "
            "systemd-resolved and D-Bus act for the process.",
            "Offline commands cannot create IPv4 or IPv6 sockets and cannot bind or connect TCP sockets; setup and "
            "prepare may reach any host.",
            "Landlock denies an access with an error and does not terminate the process, and only the kernel audit "
            "log, which needs administrator rights, records denied attempts. No command audits them.",
            "scripts/setup downloads, verifies, and unpacks the Python runtime and creates .venv before the sandbox applies.",
            "A kernel without the required Landlock ABI makes commands fail instead of running unconfined.",
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
        raise EnvironmentError("use scripts/pgvideo doctor, test, prepare --document ..., "
                               "status --request ..., or another command in AGENTS.md")
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
    if command == "test":
        test_parser = argparse.ArgumentParser(prog="pgvideo test", description="Run project tests in the local sandbox.")
        test_parser.add_argument("--pattern", default="test*.py", help="unittest discovery filename pattern")
        test_args = test_parser.parse_args(sys.argv[2:])
        doctor(lock, sample=False, announce=False)
        return run_local([str(PYTHON), "-I", "-m", "unittest", "discover", "-s", "tests", "-p", test_args.pattern, "-v"],
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
