# Phase prompt: finished-video review

Input: current `status.media_review_input`, the accepted storyboard, rendered slides, caption files, finished
`render/draft.mp4`, and quality report. Read `schemas/media-review.schema.json` before writing the review.
Output: one JSON file imported with `scripts/pgvideo media-review --request <id> --file <file> --json`.

Inspect every scene visually for readability, diagram meaning, correct content, and agreement with narration.
Listen to all narration for pronunciation, clarity, omissions, clipped sentences, and artifacts. Play the finished
MP4 from beginning to end with captions to assess pacing, synchronization, transitions, and ending.
Text, transcripts, loudness measurements, and slide images do not establish a listening or playback check.

Copy the exact `request_id`, `video_sha256`, `storyboard_digest`, and scene IDs from current tool results.
Use `producer.prompt: "prompts/media-review.md"` and report only known producer metadata.
Write exactly one `scenes` entry per scene, with `visual`, `listening`, and `captions` verdicts and a specific
`message`. Add `checks.playback`, `transitions`, `pacing`, `ending`, and `caption_sync`, each with a `verdict`
and `message`. Verdicts are `passed`, `failed`, or `unavailable`. A passed verdict requires actually performing
that check on the named MP4. Record unavailable capabilities honestly; unavailable or failed checks block delivery.

Keep the first draft at `.scratch/<id>/media/<video-sha256>/review.v1.json`. Correct an existing JSON draft with
`revise`; a changed video gets a new first draft. Do not turn a failed finding into passed without checking the
fixed artifact. Content repairs need a new independent semantic review and build; media repairs need revalidation
and inspection of the resulting video. Honor the existing repair budgets and stop conditions.
