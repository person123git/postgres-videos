# Phase prompt: bounded repair

Use this for targeted revisions after authoring self-checks, required pre-import checks, or pgvideo findings.
Pre-import assembly and self-checks need no failed result. After import, follow findings and `next_actions`.
Only the isolated reviewer may correct a review; the writer may relay deterministic errors and the current
review contract but may not change review judgments or provide a self-assessment.

Input: the findings in `runs/<request-id>/plan-report.md` or `script.md` (deterministic checks) or
`content-report.md` (the separate review), the current file you imported (your latest revision in
`.scratch/<id>/`), the accepted plan, and the evidence packet.

## Patch the file; never retype it

**A plan, storyboard, or review that parses as JSON MUST be changed with `scripts/pgvideo revise`.**
A schema failure still uses `revise`. Never regenerate the input with a helper script or write its full
replacement, even in chunks or under a new filename. Follow
[AGENTS.md's recovery rules](../AGENTS.md#mandatory-file-writing-and-recovery) for a failed write or JSON
syntax error. Check what was actually saved; a failed call does not prove that nothing was written.

1. Read the findings and locate affected entries. Read `scripts/pgvideo revise --help` before first use.
2. Write a small JSON list of operations to `.scratch/<id>/fix1.json`.
3. Run `jq empty .scratch/<id>/fix1.json`. Fix any syntax error in the patch before continuing.
4. Apply it to your latest valid revision with a new output filename. `revise` preserves the source:

   ```sh
   scripts/pgvideo revise --from .scratch/<id>/plan.v1.json --patch .scratch/<id>/fix1.json --out .scratch/<id>/plan.v2.json --json
   ```

5. Read `status`, `issues`, `next_actions`, and `changes`; require `passed` and the intended matches.
   Validate the new revision with `jq empty` and inspect the changed entries. Record its path in state.
6. Import with `plan --file`, `script --storyboard`, or `review --file`, using `--request <id>` and `--json`.
   A passed `revise` has not passed the stage. Read the import result before continuing.

If the patch is too large, split it and apply the smaller patches sequentially, each to a new revision.
Import after all required fixes. A failed `revise` requires a corrected patch or command, never a full rewrite.

Example: use this patch only if the findings confirm that source IDs incorrectly use `_` instead of `.`:

```json
[
  {"op": "replace", "path": "claims[*].sources[*]", "find": "_", "with": "."}
]
```

| Operation | Effect |
| --- | --- |
| `{"op": "set", "path": P, "value": V}` | Put `V` at `P`. The last key may be new. |
| `{"op": "add", "path": P, "value": V}` (or `"values": [..]`) | Append to the list at `P`. |
| `{"op": "remove", "path": P}` | Delete the entries or keys at `P`. |
| `{"op": "replace", "path": P, "find": A, "with": B}` | Replace text `A` by `B` in the strings at `P`. |

A path is keys joined by dots. After a list, a selector in brackets picks entries: `[*]` every entry, `[2]` one
position, `[id=size-sets-slot]` entries whose key has that value, `[target~screen:*:0]` entries whose key
matches a pattern (`*` any text, `?` one character), `[=short-answer.1.s1]` entries equal to a value.
Examples: `claims[id=size-sets-slot].sources`, `claims[*].assessment.glossary`,
`scenes[id=answer].narration[1].text`, `omissions[section=details].reason`, `findings[verdict=pending]`.

- Use one operation with `[*]` when the same correction applies to every selected entry. Otherwise select
  only the affected IDs; do not change unrelated entries to make one wildcard operation work.
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
  fails the import. Sections the template lists under `essential` cannot be omitted: cite one of each section's
  unit IDs in a claim's `sources`. `essential_omitted` reports such a section, omitted or not, and names a unit.
  Before omitting a section it lists under `caveats`, confirm no kept claim needs its qualification.
- A fix never adds content. A claim the evidence does not support is removed, with a reason in `omissions`.

## Storyboard repair

1. Change only the scenes, sentences, screen lines, or edges the findings name. `revise` keeps everything else
   as it was, so unchanged narration reuses its cached audio.
2. Fix the cause, not the symptom: restore a dropped condition, reverse an edge to match its sentence, replace an
   unsupported paraphrase with the source's wording, or remove a claim the evidence does not support.
3. Never weaken a required caveat or the main answer to pass a check. If a fix needs content the plan does not
   select, revise and re-import the plan instead; then patch the storyboard's `plan_digest` and affected scenes.
4. Include a `set` operation for `producer.prompt` with value `prompts/repair.md` in the patch. Apply and
   validate it before importing with `scripts/pgvideo script --request <id> --storyboard <file> --json`.
5. Run a new separate review of the result. A repaired storyboard is never accepted on the old review.

Budgets: a plan repair is stopped when three imports in a row report the same blocking issue, or ten in a row
have not passed. A storyboard gets two repair rounds after a failed content review, and one rewrite after the
measured narration missed its target (`--duration-rewrite`). Shorten optional detail when long; when short,
expand using unused allowed source content and revise the plan first if needed. Report infeasibility if no
allowed content remains. Keep fixed speech settings and avoid repeated explanations or pause padding. Make duration
changes with `revise` too. If another repair is needed after a budget is exhausted, follow `next_actions` and
stop. Report the remaining findings with the request ID; a person decides next. `--human-revision` is only for
a revision a person made.
