"""The order of a request's stages and the manifest records that depend on each one."""

from __future__ import annotations

# A harness request adds the evidence packet, the accepted content plan, and the separate content review.
# A request made before the harness workflow has none of them; its records simply lack those stages.
STAGES = ("sources", "document", "glossary", "glossary_check", "evidence", "plan", "script", "content_review",
          "narration", "timing", "render", "validation", "media_review")
# The reuse lookup describes one storyboard, so it is dropped whenever the storyboard can change.
STORYBOARD_STAGES = STAGES[:STAGES.index("script") + 1]


def invalidate_after(manifest: dict, stage: str) -> None:
    """Drop the records of every stage built from `stage`'s previous output."""
    for later in STAGES[STAGES.index(stage) + 1:]:
        manifest.pop(later, None)
    if stage in STORYBOARD_STAGES:
        manifest.pop("reuse", None)
