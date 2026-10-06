"""Write what a separate reviewer reads before judging a storyboard (harness requests).

`write` builds these files under runs/<id>/review-input/ from the accepted plan,
the accepted storyboard, and the evidence packet:

- video.md: everything a viewer sees and hears, in playback order, each element
  with the ID of its review target, after the plan at a glance and a map with one
  line per scene;
- document.md: the page's sections as text with unit IDs, marking the units that
  no scene cites;
- coverage.md: per section, how many units the scenes cite and the text of those
  none cites;
- checks.md: the warnings of pgvideo's own checks that ask for a judgment, the
  corrections, and the length estimates;
- plan.json: the accepted plan without the writer's claim assessments, with
  pgvideo's estimate and section map;
- review-template.json: a review in which every target, section, and whole-video
  check is still pending, holding the findings carried from this request's
  previous review.

The files leave out the writer's assessments and the lexical status of each
sentence, so the review stays independent. They exist so that a reviewer can read
the whole video and the whole page before judging single targets; nothing in them
is a judgment.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .crosscheck import _recorded
from .orchestration import DURATION_TOLERANCE, request
from .review import OVERALL, PENDING, carry_over, targets
from .sources import write_atomic

DIRECTORY = "review-input"
FILES = {"video": "video.md", "document": "document.md", "coverage": "coverage.md", "checks": "checks.md",
         "plan": "plan.json", "template": "review-template.json"}
INDEX = "index.json"
PLAN_KEYS = ("schema", "request_id", "audience", "detail", "target_minutes", "main_answer", "learning_objectives",
             "outline", "required_caveats", "omissions")
CLAIM_KEYS = ("id", "text", "kind", "sources", "glossary", "depends_on")
UNCITED = "no scene cites this"


def _clock(seconds: float) -> str:
    whole = int(seconds)
    hours, minutes, rest = whole // 3600, whole % 3600 // 60, whole % 60
    return f"{hours}:{minutes:02d}:{rest:02d}" if hours else f"{minutes}:{rest:02d}"


def _one_line(value) -> str:
    return " ".join(str(value).split())


def _cell(value) -> str:
    return _one_line(value).replace("|", "\\|")


def _tidy(lines: list[str]) -> str:
    """Join lines into text, keeping one blank line between parts and code blocks as they are."""
    kept, fenced = [], False
    for line in lines:
        if line.lstrip().startswith("```"):
            fenced = not fenced
        if line or fenced or (kept and kept[-1]):
            kept.append(line)
    return "\n".join(kept).rstrip() + "\n"


def _in_section(unit: str, section: str) -> bool:
    return unit == section or unit.startswith(section + ".")


def _flags(unit: dict, marks: dict[str, str]) -> str:
    """What a reader must know about one unit beyond its text."""
    notes = [marks[unit["id"]]] if unit["id"] in marks else []
    lexical = unit.get("lexical") or {}
    if lexical.get("status") == "unconfirmed":
        notes.append("lexical unconfirmed" + (": " + ", ".join(lexical["not_found"]) + " not found"
                                              if lexical.get("not_found") else ""))
    if unit.get("corrections"):
        notes.append("correction " + ", ".join(unit["corrections"]))
    if unit.get("omitted_by_review"):
        notes.append("omitted by a recorded resolution")
    return "".join(f" [{note}]" for note in notes)


def _page(packet: dict, marks: dict[str, str]) -> str:
    """Render the packet's sections as text to read in page order; every sentence, row, and block keeps its unit ID.

    Nothing is selected or summarized: text is as the packet holds it. `marks` adds a note to a unit, such as
    that no scene cites it. The sections the packet holds no content for are listed at the end with the reason.
    """
    document = packet["document"]
    lines = [f"# {document.get('title') or document['path']}", "",
             f"PostgreSQL {document['version']} · {document['path']} at wiki commit "
             f"{document['wiki_commit'][:12]}" + (" · the page is marked unverified" if document.get("unverified")
                                                    else ""),
             "", packet["notice"], ""]
    held = [section for section in packet["sections"] if section["eligible"] and section["blocks"]]
    for section in held:
        name = section["id"]
        about = [f"`{name}`", f"level {section['level']}"]
        about += [f"under `{section['parent']}`"] if section.get("parent") else []
        about += [f"role {section['role']}"] if section.get("role") else []
        about += ["caveat section"] if section.get("caveat") else []
        lines += [f"## {section['heading']}", "", " · ".join(about), ""]
        for block in section["blocks"]:
            if block["type"] == "paragraph":
                lines += [f"- `{unit['id']}` {_one_line(unit['text'])}{_flags(unit, marks)}"
                          for unit in block["sentences"]]
            elif block["type"] == "table":
                lines += [f"- `{block['id']}` table: " + " | ".join(_one_line(cell) for cell in block["header"])]
                lines += [f"  - `{row['id']}` " + " | ".join(_one_line(cell) for cell in row["cells"])
                          + _flags(row, marks) for row in block["rows"]]
            elif block["type"] == "code":
                fence = "````" if "```" in block["content"] else "```"
                label = block.get("language") or block.get("kind") or ""
                lines += [f"- `{block['id']}` code" + (f" ({label})" if label else "") + _flags(block, marks), "",
                          fence + (block.get("language") or ""), block["content"].rstrip("\n"), fence, ""]
            elif block["type"] == "image":
                shown = ", ".join(f"{image.get('path')}" + (f" ({image['alt']})" if image.get("alt") else "")
                                  for image in block.get("images", []))
                lines.append(f"- `{block['id']}` image: {shown}{_flags(block, marks)}")
        cited: dict[str, list[str]] = {}
        for excerpt in packet["evidence"]["excerpts"]:
            for unit in excerpt["cited_by"]:
                if _in_section(unit, name) and unit not in cited.setdefault(excerpt["id"], []):
                    cited[excerpt["id"]].append(unit)
        cited = {identifier: units for identifier, units in cited.items() if units}
        if cited:
            lines += ["", "Evidence its units cite (`evidence.excerpts` in `evidence-packet.json`, by `id`):", ""]
            lines += [f"- `{identifier}` ← {', '.join(units)}" for identifier, units in cited.items()]
        glossary = sorted(entry["id"] for entry in packet["glossary"]["entries"]
                          if any(_in_section(unit, name) for unit in entry["occurrences"]))
        if glossary:
            lines += ["", "Glossary entries its units use: " + ", ".join(f"`{g}`" for g in glossary)]
        lines.append("")
    names = {section["id"] for section in held}
    left_out = [section for section in packet["sections"] if section["id"] not in names]
    if left_out:
        lines += ["## Sections the packet holds no content for", ""]
        lines += [f"- `{s['id']}` {s['heading']}: " + (s["reason"] or ("no content of its own" if s["eligible"]
                                                                      else f"role {s['role']}"))
                  for s in left_out]
        lines.append("")
    return _tidy(lines)


def _scene_claims(scene: dict) -> set[str]:
    claims = {claim for item in scene["narration"] for claim in item.get("claims", [])}
    return claims | {claim for edge in (scene["screen"].get("diagram") or {}).get("edges", [])
                     for claim in edge.get("claims", [])}


def plan_view(plan: dict) -> dict:
    """The accepted plan as the reviewer may see it: no claim assessments, no lexical status."""
    view = {key: plan[key] for key in PLAN_KEYS}
    view["claims"] = [{key: claim[key] for key in CLAIM_KEYS if key in claim} for claim in plan["claims"]]
    # Computed by pgvideo, not judged by the writer.
    view["estimate"] = plan["estimate"]
    view["sections"] = [{key: row[key] for key in ("section", "heading", "eligible", "caveat", "claims", "omitted")}
                        for row in plan["coverage"]]
    return view


def section_coverage(packet: dict, storyboard: dict, plan: dict) -> list[dict]:
    """For every section with content: its units, the scenes that cite them, and the units no scene cites.

    A scene cites a unit by its own ID, its block's ID, or its section's ID.
    """
    planned = {row["section"]: row for row in plan["coverage"]}
    order = {scene["id"]: number for number, scene in enumerate(storyboard["scenes"])}
    cited: dict[str, list[str]] = {}
    for scene in storyboard["scenes"]:
        for source in scene["sources"]:
            cited.setdefault(source, []).append(scene["id"])
    rows = []
    for section in packet["sections"]:
        if not (section["eligible"] and section["blocks"]):
            continue
        units = []
        for block in section["blocks"]:
            if block["type"] == "paragraph":
                units += [(unit["id"], block["id"], unit["text"]) for unit in block["sentences"]]
            elif block["type"] == "table":
                units += [(row["id"], block["id"], " | ".join(row["cells"])) for row in block["rows"]]
            else:
                units.append((block["id"], block["id"], f"({block['type']} block)"))
        scenes, uncited = set(), []
        for unit, block, text in units:
            by = {scene for name in (unit, block, section["id"]) for scene in cited.get(name, [])}
            scenes |= by
            if not by:
                uncited.append({"id": unit, "text": _one_line(text)})
        row = planned.get(section["id"]) or {}
        rows.append({"section": section["id"], "heading": section["heading"], "caveat": section["caveat"],
                     "units": len(units), "cited": len(units) - len(uncited),
                     "scenes": sorted(scenes, key=order.get), "uncited": uncited,
                     "claims": row.get("claims", []), "omitted": row.get("omitted")})
    return rows


def _video(run_dir: Path, digests: dict, storyboard: dict, plan: dict, found: dict, carried: set[str]) -> str:
    document, estimate, counts = storyboard["document"], storyboard["estimate"], storyboard["counts"]
    scenes = storyboard["scenes"]
    by_kind: dict[str, int] = {}
    for info in found.values():
        by_kind[info["kind"]] = by_kind.get(info["kind"], 0) + 1
    target = plan["target_minutes"]
    narrates: dict[str, list[str]] = {}
    for scene in scenes:
        for claim in _scene_claims(scene):
            narrates.setdefault(claim, []).append(scene["id"])
    # A scene belongs to the plan items whose claims it narrates; one without claims, such as the opening or the
    # credits, to the claimless items of its part.
    items = {scene["id"]: [item["id"] for item in plan["outline"] if set(item["claims"]) & _scene_claims(scene)]
             or [item["id"] for item in plan["outline"]
                 if not item["claims"] and not _scene_claims(scene) and item["part"] == scene["part"]]
             for scene in scenes}

    def mark(identifier: str) -> str:
        return f"`{identifier}`" + (" [carried]" if identifier in carried else "")

    def where(claims: list[str]) -> str:
        shown = list(dict.fromkeys(scene for claim in claims for scene in narrates.get(claim, [])))
        return "scenes " + ", ".join(f"`{s}`" for s in shown) if shown else "no scene"

    lines = [
        f"# The video as text: {document['title']}", "",
        f"- Request `{run_dir.name}`; storyboard `{digests['storyboard_digest'][:12]}`, plan "
        f"`{digests['plan_digest'][:12]}`, evidence `{digests['evidence_digest'][:12]}`",
        f"- Requested: detail {plan['detail']}; audience: {plan['audience']}; length: "
        + (f"{target:g} minutes, within {int(DURATION_TOLERANCE * 100)}% either way" if target
           else "no length target (full detail)"),
        f"- Storyboard: {counts['scenes']} scenes, {counts['sentences']} narration items, {estimate['words']} spoken "
        f"words, about {estimate['minutes']} minutes at {storyboard['settings']['words_per_minute']} words per minute",
        f"- {len(found)} review targets: " + ", ".join(f"{count} {kind}" for kind, count in by_kind.items())
        + (f"; {len(carried)} carried from the previous review, {len(found) - len(carried)} to judge" if carried
           else ""),
        "",
        "Everything a viewer sees and hears is below, in playback order. Each element starts with the ID of its review",
        "target. One slide stays on screen for the whole of its scene's narration, and each narration item becomes one",
        f"or more caption cues. Lists of sources and evidence are left out; `runs/{run_dir.name}/storyboard.json`",
        "holds them. A narration item there lists every source of its claims, so a source it does not speak is not",
        "by itself an omission: `coverage.md` shows what no scene cites.", "",
        "## The plan at a glance", "",
        f"**Main answer:** {_one_line(plan['main_answer']['text'])} ({where(plan['main_answer']['claims'])})", "",
        "Learning objectives:", "",
        *(f"{number}. {_one_line(objective)}" for number, objective in enumerate(plan["learning_objectives"], 1)), "",
    ]
    if plan.get("required_caveats"):
        lines += ["Required caveats:", ""]
        lines += [f"- `{caveat['claim']}` in {where([caveat['claim']])}: {_one_line(caveat['reason'])}"
                  for caveat in plan["required_caveats"]]
        lines.append("")
    if plan["omissions"]:
        lines += ["Sections the plan omits:", ""]
        lines += [f"- `{item['section']}` ({_one_line(item.get('heading') or '')}): {_one_line(item['reason'])}"
                  for item in plan["omissions"]]
        lines.append("")
    lines += ["## Map", "", "| # | Starts | Seconds | Scene | Part | Layout | Plan item | Heading |",
              "|---|---|---|---|---|---|---|---|"]
    clock, starts = 0.0, {}
    for number, scene in enumerate(scenes, 1):
        starts[scene["id"]] = clock
        lines.append(f"| {number} | {_clock(clock)} | {scene['estimated_seconds']:g} | `{scene['id']}` | "
                     f"{scene['part']} | {scene['screen']['layout']} | "
                     f"{', '.join(items[scene['id']]) or '—'} | "
                     f"{_cell(scene['screen']['heading'] or scene['title'])} |")
        clock += scene["estimated_seconds"]
    lines += ["", "## Plan items against the storyboard", "",
              "| Plan item | Part | Title | Budget (s) | Estimated (s) | Scenes |", "|---|---|---|---|---|---|"]
    for item in plan["outline"]:
        used = [scene for scene in scenes if item["id"] in items[scene["id"]]]
        lines.append(f"| `{item['id']}` | {item['part']} | {_cell(item['title'])} | {item['budget_seconds']:g} | "
                     f"{sum(scene['estimated_seconds'] for scene in used):g} | "
                     f"{', '.join(scene['id'] for scene in used) or '—'} |")
    lines += ["", "## Scenes", ""]
    for number, scene in enumerate(scenes, 1):
        identifier, screen = scene["id"], scene["screen"]
        lines += [f"### {number}. `{identifier}`: {_one_line(scene['title'])}", "",
                  f"{scene['part']} · {screen['layout']} · about {scene['estimated_seconds']:g} s from "
                  f"{_clock(starts[identifier])}"
                  + (" · plan item " + ", ".join(f"`{i}`" for i in items[identifier]) if items[identifier] else ""),
                  "", "Screen:", ""]
        for position, line in enumerate([screen["heading"], *screen["lines"]]):
            lines.append(f"- {mark(f'screen:{identifier}:{position}')} {_one_line(line)}")
        diagram = screen.get("diagram") or {}
        labels = {node["id"]: node["label"] for node in diagram.get("nodes", [])}
        for position, node in enumerate(diagram.get("nodes", []), 1):
            lines.append(f"- {mark(f'node:{identifier}:{position}')} {_one_line(node['label'])}")
        if code := screen.get("code"):
            fence = "````" if "```" in code["content"] else "```"
            lines += [f"- {mark(f'code:{identifier}:1')} code from `{code['source']}`, from its line "
                      f"{code['first_line']}:", "",
                      f"  {fence}{code.get('language') or ''}",
                      *(f"  {row}" for row in code["content"].rstrip("\n").split("\n")), f"  {fence}", ""]
        if table := screen.get("table"):
            lines += [f"- {mark(f'table:{identifier}:1')} table from `{table['source']}`:", "",
                      "  | " + " | ".join(_cell(cell) for cell in table["header"]) + " |",
                      "  |" + "---|" * len(table["header"]),
                      *("  | " + " | ".join(_cell(cell) for cell in row) + " |" for row in table["rows"]), ""]
        for position, term in enumerate(screen.get("terms", []), 1):
            lines.append(f"- {mark(f'term:{identifier}:{position}')} **{_one_line(term['term'])}**: "
                         f"{_one_line(term['definition'])}")
        for position, edge in enumerate(diagram.get("edges", []), 1):
            lines.append(f"- {mark(f'edge:{identifier}:{position}')} {_one_line(labels.get(edge['from']))} → "
                         f"{_one_line(edge['label'])} → {_one_line(labels.get(edge['to']))} (claims "
                         f"{', '.join(edge.get('claims', [])) or 'none'}; stated by `{edge.get('source')}`)")
        if image := screen.get("image"):
            lines.append(f"- image: {image.get('path')}"
                         + (f" ({_one_line(image['alt'])})" if image.get("alt") else ""))
        if screen.get("footer"):
            lines.append(f"- footer: {_one_line(screen['footer'])}")
        lines += ["", "Narration:", ""]
        for item in scene["narration"]:
            about = [item["origin"]]
            about += ["glossary " + ", ".join(f"#{anchor}" for anchor in item["glossary"])] \
                if item["origin"] == "glossary" and item.get("glossary") else []
            about += ["claims " + ", ".join(item["claims"])] if item.get("claims") else []
            lines.append(f"- {mark('narration:' + item['id'])} ({'; '.join(about)}) {_one_line(item['text'])}")
            if item["tts_source"] == "manual":
                lines.append(f"- {mark('tts:' + item['id'])} spoken as: {_one_line(item['tts'])}")
        lines.append("")
    return _tidy(lines)


def _coverage(rows: list[dict], storyboard: dict) -> str:
    total, cited = sum(row["units"] for row in rows), sum(row["cited"] for row in rows)
    lines = [f"# Source-to-video coverage: {storyboard['document']['title']}", "",
             f"Scenes cite {cited} of the {total} sentences, table rows, and blocks in {len(rows)} sections with "
             f"content; {sum(1 for row in rows if row['uncited'])} sections have a unit that no scene cites.", "",
             "A unit that no scene cites is a place to look, not a verdict. A fact has one home in the video, so",
             "another unit may already teach it; and a cited unit is not proof that its content is narrated.",
             "Judge each section against `video.md`. `document.md` has every unit in page order.", ""]
    for row in rows:
        plan = ("omitted by the plan: " + _one_line(row["omitted"]) if row["omitted"]
                else "claims " + ", ".join(row["claims"]) if row["claims"] else "no claim selects it")
        lines += [f"## {_one_line(row['heading'])}", "",
                  f"`{row['section']}`" + (" · caveat section" if row["caveat"] else "")
                  + f" · {row['cited']} of {row['units']} units cited · {plan}",
                  "Scenes: " + (", ".join(f"`{scene}`" for scene in row["scenes"]) or "none"), ""]
        if row["uncited"]:
            lines += ["Units no scene cites:", ""]
            lines += [f"- `{unit['id']}` {unit['text']}" for unit in row["uncited"]]
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _checks(storyboard: dict, plan: dict) -> str:
    def grouped(issues: list[dict], subjects: tuple[str, ...]) -> list[str]:
        kept = [issue for issue in issues if issue["severity"] in ("warning", "note")]
        codes = list(dict.fromkeys(issue["code"] for issue in kept))
        found = []
        for code in codes:
            same = [issue for issue in kept if issue["code"] == code]
            found += [f"### `{code}` ({len(same)})", ""]
            for issue in same:
                about = " · ".join(f"{name} `{issue[name]}`" for name in subjects if issue.get(name))
                found.append("- " + (f"{about}: " if about else "") + _one_line(issue["message"]))
            found.append("")
        return found or ["None.", ""]

    estimate, budget = storyboard["estimate"], plan["estimate"]
    target = plan["target_minutes"]
    lines = [f"# What pgvideo's checks leave to the review: {storyboard['document']['title']}", "",
             "pgvideo looks up names, numbers, and quoted strings in the pinned source, and checks IDs and limits. It",
             "does not judge meaning. Every warning below passed those checks and still needs your judgment; several",
             "say so. Settle each one in the finding of the target it names, or in an editorial finding.", "",
             "## From the plan check", "", *grouped(plan["issues"], ("claim", "section")),
             "## From the storyboard check", "", *grouped(storyboard["issues"], ("scene", "narration")),
             "## Corrections and recorded resolutions", ""]
    lines += [f"- correction `{c['id']}` ({'applied in the storyboard' if c['applied'] else 'not used'}): "
              + _one_line(c.get("instruction") or c.get("corrected") or "") for c in storyboard["corrections"]]
    lines += [f"- left out by resolution `{o['id']}`: {_one_line(o['reason'])} ({', '.join(o['at'])})"
              for o in storyboard["omissions"]]
    if not (storyboard["corrections"] or storyboard["omissions"]):
        lines.append("None.")
    lines += ["", "## Length", "",
              f"- Plan: {budget['budget_seconds']:g} s budgeted; its claims alone take about "
              f"{budget['claim_seconds']:g} s at {budget['words_per_minute']:g} words per minute "
              f"({budget['rate_basis']} rate)",
              f"- Storyboard: about {estimate['seconds']:g} s ({estimate['minutes']:g} minutes), {estimate['words']} "
              "spoken words",
              "- Target: " + (f"{target:g} minutes, so {target * 60 * (1 - DURATION_TOLERANCE):.0f} to "
                              f"{target * 60 * (1 + DURATION_TOLERANCE):.0f} s. `build` measures the real length."
                              if target else "none (full detail)")]
    return "\n".join(lines).rstrip() + "\n"


def _template(run_dir: Path, digests: dict, found: dict, rows: list[dict], carried: dict | None) -> dict:
    kept = (carried or {}).get("findings", {})
    template = {
        "schema": "pgvideo/review/v1", "request_id": run_dir.name, **digests,
        "reviewer": {"separation": PENDING, "writer_context_shared": None, "writer_self_assessment_seen": None},
        "producer": {"harness": {"name": PENDING}, "model": "unavailable", "prompt": "prompts/review.md"},
        "summary": PENDING,
        "overall": {name: {"verdict": PENDING, "message": PENDING} for name in OVERALL},
        "editorial": [],
        "coverage": [{"section": row["section"], "verdict": PENDING, "justification": PENDING} for row in rows],
    }
    if kept:
        template["carried"] = {"from_storyboard_digest": carried["from_storyboard_digest"], "targets": list(kept)}
    template["findings"] = [kept.get(target) or {"target": target, "factual": None, "verdict": PENDING, "evidence": [],
                                                 "justification": PENDING, "issues": []} for target in found]
    return template


def write(root: Path, run_dir: Path) -> dict:
    """Write the reviewer's files for the current storyboard; return their paths, the digests, and counts."""
    from .preview import current as current_preview

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    for stage in ("evidence", "plan", "script"):
        if (manifest.get(stage) or {}).get("status") != "passed":
            raise ValueError(f"The {stage} stage must pass before obtaining review input.")
    plan = json.loads(_recorded(run_dir, "plan.json", manifest["plan"]))
    storyboard = json.loads(_recorded(run_dir, "storyboard.json", manifest["script"]))
    packet = json.loads(_recorded(run_dir, "evidence-packet.json", manifest["evidence"]))
    digests = {f"{name}_digest": manifest[stage]["digest"]
               for name, stage in (("storyboard", "script"), ("plan", "plan"), ("evidence", "evidence"))}
    found = targets(storyboard)
    carried = carry_over(run_dir, manifest, storyboard, plan)
    rows = section_coverage(packet, storyboard, plan)
    marks = {unit["id"]: UNCITED for row in rows for unit in row["uncited"]}
    bodies = {
        "video": _video(run_dir, digests, storyboard, plan, found, set((carried or {}).get("findings", {}))),
        "document": _page(packet, marks),
        "coverage": _coverage(rows, storyboard),
        "checks": _checks(storyboard, plan),
        "plan": json.dumps(plan_view(plan), indent=2, ensure_ascii=False) + "\n",
        "template": json.dumps(_template(run_dir, digests, found, rows, carried), indent=2, ensure_ascii=False) + "\n",
    }
    relative = run_dir.relative_to(root) / DIRECTORY
    files = {}
    for name, body in bodies.items():
        data = body.encode("utf-8")
        path = write_atomic(root, relative / FILES[name], data, label="Request")
        files[name] = {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "lines": body.count("\n"),
                       "bytes": len(data)}
    settings = request(run_dir).get("settings") or {}
    warnings = {"plan": sum(issue["severity"] in ("warning", "note") for issue in plan["issues"]),
                "storyboard": sum(issue["severity"] in ("warning", "note") for issue in storyboard["issues"])}
    index = {
        "request_id": run_dir.name,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "digests": digests,
        "document": {key: storyboard["document"].get(key) for key in ("title", "path", "version", "url")},
        "request": {key: settings.get(key) for key in ("detail", "audience", "target_minutes", "voice", "language",
                                                        "speed")},
        "counts": {"scenes": len(storyboard["scenes"]), "narration_items": storyboard["counts"]["sentences"],
                   "estimated_minutes": storyboard["estimate"]["minutes"], "targets": len(found),
                   "carried": len((carried or {}).get("findings", {})),
                   "to_judge": len(found) - len((carried or {}).get("findings", {})),
                   "sections": len(rows), "units": sum(row["units"] for row in rows),
                   "units_cited": sum(row["cited"] for row in rows), "warnings": warnings},
        "carried_from_storyboard_digest": (carried or {}).get("from_storyboard_digest"),
        "files": files,
        "storyboard": str(run_dir / "storyboard.json"),
        "preview": current_preview(run_dir, manifest),
        "read_in_order": ["video", "document", "coverage", "checks"],
    }
    write_atomic(root, relative / INDEX, (json.dumps(index, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
                 label="Request")
    return index
