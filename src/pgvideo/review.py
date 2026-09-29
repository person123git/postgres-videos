"""Import the separate semantic content review and decide the content gate (harness requests).

The harness reviews the accepted storyboard in a context separate from the one
that wrote it, with the original evidence and without the writer's
self-assessment. The review classifies every narration item as factual or not
(independently of its `origin` label) and judges each factual item, screen line,
diagram edge, glossary paraphrase, and manually written TTS text against the
evidence: supported, contradicted, or insufficient_evidence, with evidence IDs
and a short justification. Editorial findings cover clarity, missing caveats,
repetition, ordering, and whether the visuals agree with the narration.

pgvideo checks that the review names this request's current storyboard, plan,
and evidence; that it declares a separate pass; that it has exactly one finding
for every target; and that every evidence ID resolves. The gate then passes only
when every factual target is supported and no finding is material. The
reviewer's words are findings, never statuses, and no confidence score is read.
A lexical `verified` from Step 6 is kept apart from these semantic verdicts.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from . import contracts
from .crosscheck import _recorded
from .evidence import Resolver
from .orchestration import (MAX_REPAIR_ROUNDS, REVIEW_POLICY, accepted_request_ids, canonical_digest, is_harness,
                            producer, record_event, repairs, save_authored)
from .sources import write_atomic
from .stages import invalidate_after

SCHEMA_VERSION = 1
RECORD = "content-review.json"
REPORT = "content-report.md"
SEVERITIES = ("blocking", "warning", "note")
# Screens whose lines are the writer's own assertions; code, tables, and glossary cards are checked verbatim.
ASSERTING_LAYOUTS = ("question", "bullets", "steps", "diagram", "image")
REQUEST_FIELDS = ("request_id", "created_at", "producer", "authored")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def targets(storyboard: dict) -> dict[str, dict]:
    """Every target a review must judge, with what it shows or says."""
    found: dict[str, dict] = {}
    for scene in storyboard["scenes"]:
        for item in scene["narration"]:
            found[f"narration:{item['id']}"] = {"scene": scene["id"], "kind": "narration", "text": item["text"],
                                                "origin": item["origin"], "claims": item.get("claims", [])}
            if item["tts_source"] == "manual":
                found[f"tts:{item['id']}"] = {"scene": scene["id"], "kind": "tts", "text": item["text"],
                                              "tts": item["tts"]}
        screen = scene["screen"]
        if screen["layout"] in ASSERTING_LAYOUTS:
            for number, line in enumerate(screen["lines"], 1):
                found[f"screen:{scene['id']}:{number}"] = {"scene": scene["id"], "kind": "screen", "text": line}
        for number, edge in enumerate((screen.get("diagram") or {}).get("edges", []), 1):
            labels = {node["id"]: node["label"] for node in screen["diagram"]["nodes"]}
            found[f"edge:{scene['id']}:{number}"] = {
                "scene": scene["id"], "kind": "edge",
                "text": f"{labels.get(edge['from'])} {edge['label']} {labels.get(edge['to'])}",
                "claims": edge.get("claims", [])}
    return found


def import_review(root: Path, run_dir: Path, path: Path) -> dict:
    """Validate a review file and record the content gate; return the manifest record.

    The status is 'passed' or 'needs_review'. A malformed review, a review of
    another storyboard, or a review that is not a separate pass marks the stage
    'failed' and raises ValueError.
    """
    try:
        return _import(root, run_dir, path)
    except (ValueError, OSError) as error:
        _update_manifest(root, run_dir, status="failed", error=str(error))
        raise


def _import(root: Path, run_dir: Path, path: Path) -> dict:
    if not is_harness(run_dir):
        raise ValueError(f"Request {run_dir.name} predates the harness workflow; it has no content review stage.")
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    for stage in ("evidence", "plan", "script"):
        if (manifest.get(stage) or {}).get("status") != "passed":
            raise ValueError(f"The {stage} stage has status '{(manifest.get(stage) or {}).get('status')}'; a review "
                             "needs an accepted plan and a storyboard that passed its checks.")
    storyboard = json.loads(_recorded(run_dir, "storyboard.json", manifest["script"]))
    file = contracts.project_file(root, path, label="Review file")
    data = file.read_bytes()
    where = file.relative_to(root).as_posix()
    raw = contracts.parse(data, where)
    contracts.require(root, "review", raw, where)
    if raw["request_id"] not in accepted_request_ids(run_dir):
        raise ValueError(f"{where} is for request {raw['request_id']}, not {run_dir.name}.")
    expected = {"storyboard_digest": manifest["script"]["digest"], "plan_digest": manifest["plan"]["digest"],
                "evidence_digest": manifest["evidence"]["digest"]}
    for key, value in expected.items():
        if raw[key] != value:
            raise ValueError(f"{where} reviews another {key.removesuffix('_digest')} ({raw[key][:12]}); the current "
                             f"one has digest {value[:12]}. Review the current storyboard; `status` lists the digests.")
    reviewer = raw["reviewer"]
    if reviewer["writer_context_shared"] or reviewer["writer_self_assessment_seen"]:
        raise ValueError("The review shared the writer's context or saw its self-assessment. A drafting pass does "
                         "not count as its own review: review again in a fresh context with only the storyboard, the "
                         "plan, and the evidence.")
    made_by = producer(root, raw["producer"], phase="review")
    record = _Gate(root, run_dir, raw, storyboard).build()
    record["reviewer"] = reviewer
    record["producer"] = made_by
    record["authored"] = save_authored(root, run_dir, "review.json", data)
    record["repairs"] = {"used": repairs(run_dir).get("storyboard", 0), "max": MAX_REPAIR_ROUNDS}
    body = (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    relative = run_dir.relative_to(root)
    write_atomic(root, relative / RECORD, body, label="Request")
    write_atomic(root, relative / REPORT, _render(record, storyboard).encode("utf-8"), label="Request")
    sha = hashlib.sha256(body).hexdigest()
    entry = _update_manifest(root, run_dir, status=record["status"], record=record, sha=sha,
                             digest=canonical_digest(record, exclude=REQUEST_FIELDS),
                             storyboard_sha256=manifest["script"]["sha256"], plan_sha256=manifest["plan"]["sha256"])
    record_event(root, run_dir, stage="content_review", status=record["status"], artifact=RECORD, sha256=sha,
                 producer=made_by, authored=record["authored"], separation=reviewer["separation"])
    if record["status"] == "passed":
        from .reuse import register_content

        register_content(root, run_dir)
    return entry


class _Gate:
    def __init__(self, root: Path, run_dir: Path, raw: dict, storyboard: dict):
        self.raw, self.storyboard, self.run_dir = raw, storyboard, run_dir
        self.resolver = Resolver(root, run_dir)
        self.targets = targets(storyboard)
        self.issues: list[dict] = []

    def issue(self, severity: str, code: str, message: str, *, target: str | None = None,
              scene: str | None = None) -> None:
        self.issues.append({"severity": severity, "code": code, "message": message, "target": target,
                            "scene": scene})

    def build(self) -> dict:
        findings: dict[str, dict] = {}
        for finding in self.raw["findings"]:
            target = finding["target"]
            if target not in self.targets:
                raise ValueError(f"The review names {target}, which is not a target of the current storyboard.")
            if target in findings:
                raise ValueError(f"The review judges {target} twice.")
            findings[target] = finding
        missing = [target for target in self.targets if target not in findings]
        if missing:
            raise ValueError(f"The review leaves {len(missing)} target(s) unjudged, such as "
                             + ", ".join(missing[:5]) + ". Every narration item, asserting screen line, diagram edge, "
                             "and manual TTS text needs one finding.")
        verdicts = {"supported": 0, "contradicted": 0, "insufficient_evidence": 0, "not_factual": 0}
        for target, finding in findings.items():
            info = self.targets[target]
            verdict = finding["verdict"]
            verdicts[verdict] += 1
            where = {"target": target, "scene": info["scene"]}
            for reference in finding["evidence"]:
                if problem := self.resolver.problem(reference):
                    self.issue("blocking", "unresolved_evidence", problem, **where)
            if finding["factual"] and verdict == "not_factual":
                self.issue("blocking", "inconsistent_finding", "A factual target needs a supported, contradicted, "
                           "or insufficient_evidence verdict.", **where)
            elif not finding["factual"] and verdict != "not_factual":
                self.issue("blocking", "inconsistent_finding", "A target judged not factual has the verdict "
                           "not_factual.", **where)
            elif verdict == "supported" and not finding["evidence"]:
                self.issue("blocking", "unsupported_verdict", "A supported verdict needs the evidence IDs that support "
                           "it.", **where)
            elif verdict == "contradicted":
                self.issue("blocking", "contradicted", f"The review finds the evidence contradicts this "
                           f"{info['kind']}: {finding['justification']}", **where)
            elif verdict == "insufficient_evidence":
                self.issue("blocking", "insufficient_evidence", f"The evidence does not establish this "
                           f"{info['kind']}: {finding['justification']}", **where)
            if info["kind"] == "narration" and info["origin"] == "framing" and finding["factual"]:
                self.issue("note" if verdict == "supported" else "warning", "framing_is_factual",
                           "The writer labeled this sentence framing, but the review finds a technical claim in it.",
                           **where)
            if info["kind"] in ("edge", "tts") and not finding["factual"]:
                kind = "diagram edge" if info["kind"] == "edge" else "TTS"
                self.issue("blocking", "inconsistent_finding", f"A {kind} target is always judged against its "
                           "evidence.", **where)
            for issue in finding["issues"]:
                self.issue("blocking" if issue["severity"] == "material" else "warning", issue["code"],
                           issue["message"], **where)
        scenes = {scene["id"] for scene in self.storyboard["scenes"]}
        for item in self.raw["editorial"]:
            if item["scene"] not in scenes and item["scene"] != "*":
                raise ValueError(f"An editorial finding names unknown scene {item['scene']}.")
            self.issue("blocking" if item["severity"] == "material" else "warning", f"editorial_{item['code']}",
                       item["message"], scene=item["scene"])
        status = "needs_review" if any(i["severity"] == "blocking" for i in self.issues) else "passed"
        return {
            "schema": SCHEMA_VERSION,
            "request_id": self.run_dir.name,
            "created_at": _now(),
            "status": status,
            "policy": REVIEW_POLICY,
            "storyboard_digest": self.raw["storyboard_digest"],
            "plan_digest": self.raw["plan_digest"],
            "evidence_digest": self.raw["evidence_digest"],
            "counts": {"targets": len(self.targets), "verdicts": verdicts,
                       "factual": sum(f["factual"] for f in findings.values()),
                       "material": sum(i["severity"] == "blocking" for i in self.issues),
                       "minor": sum(i["severity"] == "warning" for i in self.issues)},
            "findings": [findings[target] | {"scene": self.targets[target]["scene"],
                                             "kind": self.targets[target]["kind"]} for target in self.targets],
            "editorial": self.raw["editorial"],
            "summary": self.raw["summary"],
            "issues": self.issues,
        }


def _update_manifest(root: Path, run_dir: Path, *, status: str, record: dict | None = None, sha: str | None = None,
                     digest: str | None = None, storyboard_sha256: str | None = None, plan_sha256: str | None = None,
                     error: str | None = None) -> dict:
    path = run_dir / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    manifest["status"] = {"passed": "content_accepted"}.get(status, status)
    invalidate_after(manifest, "content_review")
    entry: dict = {"status": status}
    if error:
        entry["error"] = error
    if record:
        entry.update({"record": RECORD, "report": REPORT, "sha256": sha, "digest": digest, "policy": REVIEW_POLICY,
                      "storyboard_sha256": storyboard_sha256, "plan_sha256": plan_sha256,
                      "storyboard_digest": record["storyboard_digest"], "created_at": record["created_at"],
                      "reviewer": record["reviewer"], "authored": record["authored"], "counts": record["counts"],
                      "issues": {severity: sum(i["severity"] == severity for i in record["issues"])
                                 for severity in SEVERITIES}})
    manifest["content_review"] = entry
    write_atomic(root, run_dir.relative_to(root) / "manifest.json",
                 (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"), label="Request")
    return entry


def _render(record: dict, storyboard: dict) -> str:
    """The content report delivered with the video: semantic verdicts next to the lexical checks."""
    counts, reviewer, made = record["counts"], record["reviewer"], record["producer"]
    model = made["model"] if isinstance(made["model"], str) else (
        made["model"].get("resolved") or made["model"].get("requested") or "unavailable")
    verdicts = counts["verdicts"]
    lines = [f"# Content report: {storyboard['document']['title']}", "",
             f"- Content gate: **{record['status']}** (review policy {record['policy']})",
             f"- Reviewer: {made['harness']['name']}, model {model}; separation: {reviewer['separation']}; the "
             "writer's context and self-assessment were not shared",
             f"- {counts['targets']} targets: {verdicts['supported']} supported, {verdicts['contradicted']} "
             f"contradicted, {verdicts['insufficient_evidence']} insufficient evidence, {verdicts['not_factual']} "
             "not factual",
             f"- Repair rounds used: {record['repairs']['used']} of {record['repairs']['max']}",
             "", "Semantic verdicts come from a separate model review against the evidence. Lexical results come from "
             "pgvideo's lookups of names, numbers, and quoted strings in the pinned source; they are shown apart and "
             "never count as approval of a whole sentence. Neither is a substitute for a person's listening review.",
             "", f"**Reviewer summary:** {record['summary']}", ""]
    if record["issues"]:
        lines += ["## Findings that need attention", ""]
        for severity in SEVERITIES:
            for issue in (i for i in record["issues"] if i["severity"] == severity):
                label = {"blocking": "material", "warning": "minor", "note": "note"}[severity]
                where = " · ".join(filter(None, [issue.get("target"), issue.get("scene")]))
                lines.append(f"- **{label}** `{issue['code']}`" + (f" ({where})" if where else "")
                             + f": {issue['message']}")
        lines.append("")
    else:
        lines += ["No material or minor findings.", ""]
    narration = {f"narration:{n['id']}": n for scene in storyboard["scenes"] for n in scene["narration"]}
    lines += ["## Verdicts by scene", ""]
    current = None
    for finding in record["findings"]:
        if finding["scene"] != current:
            current = finding["scene"]
            lines += ["", f"### `{current}`", ""]
        item = narration.get(finding["target"]) or {}
        lexical = (item.get("check") or {}).get("claim")
        lexical_note = f"; lexical {lexical}" if lexical and lexical not in ("not_a_claim",) else ""
        lines.append(f"- `{finding['target']}`: **{finding['verdict']}**{lexical_note}"
                     + (f" — {finding['justification']}" if finding["justification"] else "")
                     + (f" (evidence: {', '.join(finding['evidence'])})" if finding["evidence"] else ""))
    if record["editorial"]:
        lines += ["", "## Editorial review", ""]
        lines += [f"- {e['severity']} `{e['code']}` ({e['scene']}): {e['message']}" for e in record["editorial"]]
    return "\n".join(lines).rstrip() + "\n"
