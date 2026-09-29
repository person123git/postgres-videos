"""Load the pinned, local Kokoro assets without repository downloads."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .paths import project_root


class AssetError(ValueError):
    """A required narration asset is missing or differs from the lock."""


def _checked_path(root: Path, record: dict) -> Path:
    path = (root / record["path"]).resolve(strict=False)
    if not path.is_relative_to(root) or not path.is_file():
        raise AssetError(f"missing project-local asset {record['path']}; run scripts/setup")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != record["sha256"]:
        raise AssetError(f"asset checksum mismatch: {record['path']}; rerun scripts/setup")
    return path


def local_selection(*, language: str = "a", voice: str = "af_heart") -> tuple[Path, dict]:
    """Validate that a requested language and voice are provisioned locally."""
    root = project_root()
    if os.environ.get("PGVIDEO_LOCAL_ENV") != str(root):
        raise AssetError("use scripts/pgvideo to load narration assets")
    lock = json.loads((root / "tools.lock").read_text(encoding="utf-8"))
    selected = lock["kokoro"]
    if language != "a" or voice != selected["voice"]["name"]:
        raise AssetError(f"{language}/{voice} is not provisioned; add its pinned assets to tools.lock and rerun setup")
    return root, selected


def local_kokoro(*, language: str = "a", voice: str = "af_heart"):
    """Return a CPU pipeline and voice path for the assets recorded in tools.lock."""
    root, selected = local_selection(language=language, voice=voice)
    lock = json.loads((root / "tools.lock").read_text(encoding="utf-8"))
    config = _checked_path(root, selected["config"])
    model_path = _checked_path(root, selected["model"])
    voice_path = _checked_path(root, selected["voice"])
    library = root / lock["espeak_ng"]["library"]
    data = root / lock["espeak_ng"]["data"]
    if not library.is_file() or not data.is_dir():
        raise AssetError("project-local eSpeak NG is missing; run scripts/setup")

    from kokoro import KModel, KPipeline
    from phonemizer.backend.espeak.wrapper import EspeakWrapper

    # misaki imports espeakng-loader and resets these locations on import.
    # Set them after importing Kokoro so phonemization uses the .runtime copy.
    EspeakWrapper.set_library(str(library))
    EspeakWrapper.set_data_path(str(data))
    model = KModel(repo_id=selected["repository"], config=str(config), model=str(model_path)).to("cpu").eval()
    pipeline = KPipeline(lang_code=language, repo_id=selected["repository"], model=model, device="cpu")
    return pipeline, str(voice_path)
