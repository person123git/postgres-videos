# Phase prompt: bounded repair

Use this after pgvideo reports `failed` or `needs_review` for a plan, a storyboard, or its content review.

Input: the findings in `runs/<request-id>/plan-report.md` or `script.md` (deterministic checks) or
`content-report.md` (the separate review), the current file you imported (your latest revision in
`.scratch/<id>/`), the accepted plan, and the evidence packet.

## Patch the file; never retype it

A repair changes a few values. Writing the whole file again costs thousands of output tokens, can exceed your
output limit, and ends the turn with nothing written. Write only the changes:

1. Write a patch of at most 40 lines, such as `.scratch/<id>/fix1.json`: a JSON list of operations.
2. Apply it to your latest revision. `revise` writes a new file and leaves the old one unchanged:
   `scripts/pgvideo revise --from .scratch/<id>/plan.v1.json --patch .scratch/<id>/fix1.json --out .scratch/<id>/plan.v2.json --json`
3. Import the new revision with the stage's command. If more issues remain, patch that revision into the next.

| Operation | Effect |
| --- | --- |
| `{"op": "set", "path": P, "value": V}` | Put `V` at `P`. The last key may be new. |
| `{"op": "add", "path": P, "value": V}` (or `"values": [..]`) | Append to the list at `P`. |
| `{"op": "remove", "path": P}` | Delete the entries or keys at `P`. |
| `{"op": "replace", "path": P, "find": A, "with": B}` | Replace text `A` by `B` in the strings at `P`. |

A path is keys joined by dots. After a list, a selector in brackets picks entries: `[*]` every entry, `[2]` one
position, `[id=size-sets-slot]` entries whose key has that value, `[=short-answer.1.s1]` entries equal to a
value. Examples: `claims[id=size-sets-slot].sources`, `claims[*].assessment.glossary`,
`scenes[id=answer].narration[1].text`, `omissions[section=details].reason`.

- Use one operation with `[*]` for a mistake repeated in every entry. Never write one operation per entry.
- An operation that matches nothing fails and nothing is written. Read the message, correct the path, and
  write the patch under a new filename.
- A result folds repeated issues into one, with a `count`, the IDs it names, and `examples`. Fix the rule the
  examples show. The report file lists every issue; search it with `rg` when you need one.

## Plan repair

- IDs. You choose a claim's `id` and an outline item's `id`: lowercase letters, digits, and hyphens. A document
  unit ID in `sources` or `evidence`, such as `short-answer.1.s1`, is copied from the packet with its dots. When
  the schema rejects an `id`, change that `id` and every place that names it (`outline[*].claims`,
  `main_answer.claims`, `required_caveats[*].claim`, `depends_on`). Do not change `sources`.
- Unaccounted sections. First repair the claims' `sources`, so selected sections count. Then run
  `scripts/pgvideo packet --request <id> --omissions-template --plan <your plan> > .scratch/<id>/omit.json`.
  Its patch omits every eligible section the plan does not select, each with an empty reason. Apply it with
  `revise`. Then set the reasons with a second patch: the sections that need their own reason first
  (`omissions[section=<id>].reason`), then `omissions[reason=].reason` for those that share one. An empty reason
  fails the import. Sections the template lists under `essential` cannot be omitted: select claims from them.
  Before omitting a section it lists under `caveats`, confirm no kept claim needs its qualification.
- A fix never adds content. A claim the evidence does not support is removed, with a reason in `omissions`.

## Storyboard repair

1. Change only the scenes, sentences, screen lines, or edges the findings name. `revise` keeps everything else
   as it was, so unchanged narration reuses its cached audio.
2. Fix the cause, not the symptom: restore a dropped condition, reverse an edge to match its sentence, replace an
   unsupported paraphrase with the source's wording, or remove a claim the evidence does not support.
3. Never weaken a required caveat or the main answer to pass a check. If a fix needs content the plan does not
   select, revise and re-import the plan instead; then patch the storyboard's `plan_digest` and affected scenes.
4. Import the revision with `scripts/pgvideo script --request <id> --storyboard <file> --json`, set
   `producer.prompt` to `prompts/repair.md`, and run a new separate review of the result. A repaired storyboard
   is never accepted on the old review.

Budgets: two storyboard repair rounds after a failed content review, and one rewrite after the measured
narration missed its target (`--duration-rewrite`, which shortens optional detail only). When a budget is used,
stop and report the remaining findings with the request ID; a person decides next (`--human-revision` imports a
revision a person made).
