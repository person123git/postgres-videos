# Phase prompt: bounded repair

Use this after pgvideo reports `needs_review` for a storyboard or its content review.

Input: the findings in `runs/<request-id>/script.md` (deterministic checks) or `content-report.md` (the
separate review), the current storyboard file you imported (`runs/<id>/authored/storyboard.json`), the accepted
plan, and the evidence packet.

1. Change only the scenes, sentences, screen lines, or edges the findings name. Keep everything else byte for
   byte, so unchanged narration reuses its cached audio.
2. Fix the cause, not the symptom: restore a dropped condition, reverse an edge to match its sentence, replace an
   unsupported paraphrase with the source's wording, or remove a claim the evidence does not support.
3. Never weaken a required caveat or the main answer to pass a check. If a fix needs content the plan does not
   select, revise and re-import the plan instead; then write the storyboard again.
4. Import the revision with `scripts/pgvideo script --request <id> --storyboard <file> --json`, set
   `producer.prompt` to `prompts/repair.md`, and run a new separate review of the result. A repaired storyboard
   is never accepted on the old review.

Budgets: two storyboard repair rounds after a failed content review, and one rewrite after the measured
narration missed its target (`--duration-rewrite`, which shortens optional detail only). When a budget is used,
stop and report the remaining findings with the request ID; a person decides next (`--human-revision` imports a
revision a person made).
