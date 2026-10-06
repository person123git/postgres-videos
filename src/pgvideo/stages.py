"""The order of a request's stages and the manifest records that depend on each one."""

from __future__ import annotations

# `script` is the imported storyboard; the media stages follow it.
STAGES = ("script", "narration", "timing", "render", "validation")


def invalidate_after(manifest: dict, stage: str) -> None:
    """Drop the records of every stage built from `stage`'s previous output."""
    for later in STAGES[STAGES.index(stage) + 1:]:
        manifest.pop(later, None)
    # The reuse lookup describes one storyboard, so it is dropped whenever the storyboard can change.
    if stage == "script":
        manifest.pop("reuse", None)
