"""Locate the project and keep application directories inside it."""

from __future__ import annotations

import re
import sys
from collections import deque
from pathlib import Path

# A request ID names one directory under runs/.
REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def project_root() -> Path:
    """Locate a source checkout or an installation in its local .venv."""
    package = Path(__file__).resolve().parent
    environment = Path(sys.prefix).resolve()
    if package.parent.name == "src":
        root = package.parent.parent
    elif (
        sys.prefix != sys.base_prefix
        and environment.name == ".venv"
        and package.is_relative_to(environment)
    ):
        root = environment.parent
    else:
        raise ValueError("Cannot locate the project; install pgvideo in the project's .venv.")
    if not (root / "pyproject.toml").is_file():
        raise ValueError(f"Project configuration is missing from '{root}'.")
    return root


def project_directory(root: Path, path: Path, *, label: str) -> Path:
    """Resolve a directory, rejecting escapes before following external links.

    Walk each component so a link pointing outside the root is rejected before
    inspecting its target, including links whose targets do not exist yet.
    The root must already be an absolute, resolved project directory.
    """
    message = f"{label} path '{path}' must stay inside the project directory '{root}'."
    candidate = root / path
    if not candidate.is_relative_to(root):
        raise ValueError(message)

    pending = deque(candidate.relative_to(root).parts)
    resolved = root
    followed_links = 0
    while pending:
        part = pending.popleft()
        if part == "..":
            if resolved == root:
                raise ValueError(message)
            resolved = resolved.parent
            continue

        candidate = resolved / part
        if candidate.is_symlink():
            followed_links += 1
            if followed_links > 40:
                raise ValueError(f"{label} path '{path}' has a symlink loop or too many symlinks.")
            target = candidate.parent / candidate.readlink()
            if not target.is_relative_to(root):
                raise ValueError(message)
            pending.extendleft(reversed(target.relative_to(root).parts))
            resolved = root
            continue

        if candidate.exists() and not candidate.is_dir():
            raise ValueError(f"{label} path '{path}' contains a non-directory: '{candidate}'.")
        resolved = candidate
    return resolved
