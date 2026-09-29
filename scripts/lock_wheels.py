"""Refresh the platform-specific hash lock from a fully resolved wheelhouse.

Run only when intentionally updating requirements.in. Setup never writes locks.
"""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEELS = ROOT / "cache" / "wheels"


def metadata(wheel: Path) -> tuple[str, str]:
    with zipfile.ZipFile(wheel) as archive:
        members = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA") and name.count("/") == 1]
        if len(members) != 1:
            raise ValueError(f"{wheel.name}: expected one wheel metadata file")
        lines = archive.read(members[0]).decode("utf-8").splitlines()
    fields = dict(line.split(": ", 1) for line in lines if line.startswith(("Name: ", "Version: ")))
    return fields["Name"], fields["Version"]


def main() -> None:
    records: dict[str, tuple[str, str, str]] = {}
    for wheel in WHEELS.glob("*.whl"):
        name, version = metadata(wheel)
        key = name.lower().replace("_", "-").replace(".", "-")
        if key in records:
            raise ValueError(f"multiple wheels for {name}; remove unused artifacts before locking")
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        records[key] = (name, version, digest)
    if not records:
        raise ValueError("wheelhouse is empty")
    lines = [
        "# CPython 3.11, macOS arm64. Every direct, transitive, and build wheel is pinned.",
        "# Generated from requirements.in with scripts/lock_wheels.py.",
        "--only-binary=:all:",
    ]
    lines += [f"{name}=={version} --hash=sha256:{digest}" for name, version, digest in (records[key] for key in sorted(records))]
    (ROOT / "requirements.lock").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Locked {len(records)} wheels")


if __name__ == "__main__":
    main()
