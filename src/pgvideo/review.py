"""Import the separate semantic content review and decide the content gate (harness requests).

The harness reviews the accepted storyboard in a context separate from the one
that wrote it, with the original evidence and without the writer's
self-assessment. The review first judges the video as a whole: the `overall`
checks, editorial findings, and source-to-video coverage. It then classifies every
narration item as factual or not (independently of its `origin` label) and judges
each factual item, screen line, diagram edge, glossary paraphrase, and manually
written TTS text against the evidence: supported, contradicted, or
insufficient_evidence, with evidence IDs and a short justification.

pgvideo checks that the review names this request's current storyboard, plan,
and evidence; that it declares a separate pass; that nothing in it is still
pending; that it has exactly one finding for every target; and that every
evidence ID resolves. The gate then passes only when every whole-video check
passes, every factual target is supported, and no finding is material. The
reviewer's words are findings, never statuses, and no confidence score is read.
A lexical `verified` from Step 6 is kept apart from these semantic verdicts.

Each imported review is also kept by storyboard digest. When a storyboard changes,
the findings of targets that show and say the same thing, from the same claims and
evidence, are carried into the next review; `carried` names them and the import
verifies each one. The whole-video judgments are never carried.
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
REQUEST_FIELDS = ("request_id", "created_at", "producer", "authored")
# The whole-video checks, in the order a reviewer makes them.
OVERALL = ("answer", "objectives", "order", "repetition", "caveats", "scope", "visuals", "closing")
# What a review template holds wherever the reviewer has not judged yet.
PENDING = "pending"
# One file per reviewed storyboard digest: its findings and what each target showed, said, and claimed.
ARCHIVE = "reviews"
FINDING_KEYS = ("target", "factual", "verdict", "evidence", "justification", "issues")


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
        for number, line in enumerate([screen["heading"], *screen["lines"]]):
            found[f"screen:{scene['id']}:{number}"] = {"scene": scene["id"], "kind": "screen", "text": line}
        for number, node in enumerate((screen.get("diagram") or {}).get("nodes", []), 1):
            found[f"node:{scene['id']}:{number}"] = {"scene": scene["id"], "kind": "node", "text": node["label"]}
        for kind in ("code", "table"):
            if content := screen.get(kind):
                found[f"{kind}:{scene['id']}:1"] = {"scene": scene["id"], "kind": kind,
                                                    "text": json.dumps(content, ensure_ascii=False)}
        for number, term in enumerate(screen.get("terms", []), 1):
            found[f"term:{scene['id']}:{number}"] = {"scene": scene["id"], "kind": "term",
                                                     "text": f"{term['term']}: {term['definition']}"}
        for number, edge in enumerate((screen.get("diagram") or {}).get("edges", []), 1):
            labels = {node["id"]: node["label"] for node in screen["diagram"]["nodes"]}
            found[f"edge:{scene['id']}:{number}"] = {
                "scene": scene["id"], "kind": "edge",
                "text": f"{labels.get(edge['from'])} {edge['label']} {labels.get(edge['to'])}",
                "claims": edge.get("claims", [])}
    return found


def signatures(storyboard: dict, plan: dict) -> dict[str, str]:
    """A digest per target of what it shows or says and of the plan claims behind it.

    Two storyboards give a target the same signature only when its kind, text, origin, manual TTS
    text, and the wording and sources of its claims are the same. A finding is carried from one
    review to the next only for such a target.
    """
    claims = {claim["id"]: {key: claim.get(key) for key in ("text", "kind", "sources", "glossary")}
              for claim in plan["claims"]}
    return {target: canonical_digest({"kind": info["kind"], "text": info["text"], "origin": info.get("origin"),
                                      "tts": info.get("tts"),
                                      "claims": {claim: claims.get(claim) for claim in info.get("claims", [])}})
            for target, info in targets(storyboard).items()}


def archived(root: Path, run_dir: Path, digest: str) -> dict | None:
    """The kept review of one storyboard digest, from this request or one whose accepted content it replays."""
    for name in sorted(accepted_request_ids(run_dir), key=lambda name: name != run_dir.name):
        path = root / "runs" / name / ARCHIVE / f"{digest}.json"
        if path.is_file() and not path.is_symlink():
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def carry_over(run_dir: Path, manifest: dict, storyboard: dict, plan: dict) -> dict | None:
    """The findings of this request's latest review of another storyboard that still hold for this one.

    A finding is carried when the review used the current policy and evidence and the target's
    signature is unchanged. Returns the earlier storyboard's digest and the findings by target.
    """
    directory = run_dir / ARCHIVE
    kept = []
    for path in sorted(directory.glob("*.json")) if directory.is_dir() else []:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (record.get("policy") == REVIEW_POLICY and record.get("evidence_digest") == manifest["evidence"]["digest"]
                and record.get("storyboard_digest") != manifest["script"]["digest"]):
            kept.append(record)
    if not kept:
        return None
    latest = max(kept, key=lambda record: record["created_at"])
    current = signatures(storyboard, plan)
    findings = {target: latest["findings"][target] for target, signature in current.items()
                if latest["signatures"].get(target) == signature and target in latest["findings"]}
    return {"from_storyboard_digest": latest["storyboard_digest"], "findings": findings} if findings else None


def unfinished(raw) -> list[str]:
    """Say what a review made from the template still leaves pending; nothing for a finished review."""
    if not isinstance(raw, dict):
        return []

    def waiting(key: str, name: str) -> list[str]:
        items = raw.get(key)
        return [str(item.get(name)) for item in items if isinstance(item, dict) and item.get("verdict") == PENDING] \
            if isinstance(items, list) else []

    left = []
    for key, name, label in (("findings", "target", "finding"), ("coverage", "section", "coverage judgment")):
        if found := waiting(key, name):
            left.append(f"{len(found)} {label}(s), such as " + ", ".join(found[:5]))
    overall = raw.get("overall") if isinstance(raw.get("overall"), dict) else {}
    if checks := [name for name, check in overall.items()
                  if isinstance(check, dict) and check.get("verdict") == PENDING]:
        left.append("the whole-video check(s) " + ", ".join(checks))
    reviewer = raw.get("reviewer") if isinstance(raw.get("reviewer"), dict) else {}
    if any(key in reviewer and reviewer[key] in (None, PENDING)
           for key in ("separation", "writer_context_shared", "writer_self_assessment_seen")):
        left.append("the `reviewer` block")
    producer_ = raw.get("producer") if isinstance(raw.get("producer"), dict) else {}
    if isinstance(producer_.get("harness"), dict) and producer_["harness"].get("name") == PENDING:
        left.append("`producer.harness.name`")
    if raw.get("summary") == PENDING:
        left.append("the `summary`")
    return left


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
    if left := unfinished(raw):
        raise ValueError(f"{where} is not a finished review. Still pending: " + "; ".join(left) + ". Judge each "
                         "one, set it with `scripts/pgvideo revise`, and import the new revision.")
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
                         "not count as its own review: review again in a fresh context with only the files from "
                         "`review-input`, the storyboard, and the evidence.")
    made_by = producer(root, raw["producer"], phase="review")
    plan = json.loads(_recorded(run_dir, "plan.json", manifest["plan"]))
    record = _Gate(root, run_dir, raw, storyboard, plan).build()
    _keep(root, run_dir, record, raw, storyboard, plan)
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


def _keep(root: Path, run_dir: Path, record: dict, raw: dict, storyboard: dict, plan: dict) -> None:
    """Keep a review by storyboard digest, so the review of a revised storyboard can carry what did not change."""
    kept = {"schema": SCHEMA_VERSION, "request_id": run_dir.name, "created_at": record["created_at"],
            "status": record["status"], "policy": REVIEW_POLICY,
            **{key: record[key] for key in ("storyboard_digest", "plan_digest", "evidence_digest")},
            "signatures": signatures(storyboard, plan),
            "findings": {finding["target"]: {key: finding[key] for key in FINDING_KEYS}
                         for finding in raw["findings"]}}
    write_atomic(root, run_dir.relative_to(root) / ARCHIVE / f"{record['storyboard_digest']}.json",
                 (json.dumps(kept, indent=2, ensure_ascii=False) + "\n").encode("utf-8"), label="Request")


class _Gate:
    def __init__(self, root: Path, run_dir: Path, raw: dict, storyboard: dict, plan: dict):
        self.raw, self.storyboard, self.plan, self.root, self.run_dir = raw, storyboard, plan, root, run_dir
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
                             + ", ".join(missing[:5]) + ". Every narration item, screen heading and line, diagram "
                             "node and edge, excerpt, glossary card, and manual TTS text needs one finding.")
        carried = self._carried(findings)
        for name in OVERALL:
            check = self.raw["overall"][name]
            if check["verdict"] == "failed":
                self.issue("blocking", f"overall_{name}", check["message"], scene="*")
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
            if info["kind"] in ("edge", "tts", "code", "table", "term") and not finding["factual"]:
                kind = "diagram edge" if info["kind"] == "edge" else info["kind"]
                self.issue("blocking", "inconsistent_finding", f"A {kind} target is always judged against its "
                           "evidence.", **where)
            for issue in finding["issues"]:
                self.issue("blocking" if issue["severity"] == "material" else "warning", issue["code"],
                           issue["message"], **where)
        scenes = {scene["id"] for scene in self.storyboard["scenes"]}
        for item in self.raw["editorial"]:
            if unknown := [scene for scene in (item["scene"], *item.get("related", []))
                           if scene not in scenes and scene != "*"]:
                raise ValueError(f"An editorial finding names unknown scene {unknown[0]}.")
            self.issue("blocking" if item["severity"] == "material" else "warning", f"editorial_{item['code']}",
                       item["message"], scene=item["scene"])
        self._coverage()
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
            "counts": {"targets": len(self.targets), "carried": len(carried), "verdicts": verdicts,
                       "factual": sum(f["factual"] for f in findings.values()),
                       "material": sum(i["severity"] == "blocking" for i in self.issues),
                       "minor": sum(i["severity"] == "warning" for i in self.issues)},
            "findings": [findings[target] | {"scene": self.targets[target]["scene"],
                                             "kind": self.targets[target]["kind"]} for target in self.targets],
            "overall": self.raw["overall"],
            **({"carried": {"from_storyboard_digest": self.raw["carried"]["from_storyboard_digest"],
                            "targets": sorted(carried)}} if carried else {}),
            "editorial": self.raw["editorial"],
            "coverage": self.raw["coverage"],
            "summary": self.raw["summary"],
            "issues": self.issues,
        }

    def _carried(self, findings: dict[str, dict]) -> set[str]:
        """Check that each finding the review carries is the earlier review's finding for an unchanged target."""
        claimed = self.raw.get("carried")
        if not claimed:
            return set()
        digest = claimed["from_storyboard_digest"]
        earlier = archived(self.root, self.run_dir, digest)
        if earlier is None:
            raise ValueError(f"The review carries findings from the review of storyboard {digest[:12]}, which this "
                             "request does not hold. Start from the template that `review-input` writes.")
        if earlier["policy"] != REVIEW_POLICY or earlier["evidence_digest"] != self.raw["evidence_digest"]:
            raise ValueError(f"The review of storyboard {digest[:12]} used another review policy or other "
                             "evidence; its findings cannot be carried. Judge every target again.")
        current = signatures(self.storyboard, self.plan)
        for target in claimed["targets"]:
            if target not in current:
                raise ValueError(f"The review carries a finding for {target}, which is not a target of the "
                                 "current storyboard.")
            if earlier["signatures"].get(target) != current[target]:
                raise ValueError(f"{target} changed since the review of storyboard {digest[:12]}; its finding "
                                 "cannot be carried. Remove it from `carried.targets` and judge it.")
            if {key: findings[target][key] for key in FINDING_KEYS} != earlier["findings"].get(target):
                raise ValueError(f"The carried finding for {target} differs from the review of storyboard "
                                 f"{digest[:12]}. To judge it again, remove it from `carried.targets`.")
        return set(claimed["targets"])

    def _coverage(self) -> None:
        manifest = json.loads((self.run_dir / "manifest.json").read_text(encoding="utf-8"))
        packet = json.loads(_recorded(self.run_dir, "evidence-packet.json", manifest["evidence"]))
        sections = {s["id"] for s in packet["sections"] if s["eligible"] and s["blocks"]}
        plan = self.plan
        omitted = {s["section"] for s in plan["omissions"]}
        seen = set()
        for item in self.raw["coverage"]:
            section = item["section"]
            if section not in sections or section in seen:
                raise ValueError(f"Coverage names an unknown or duplicate eligible section: {section}.")
            seen.add(section)
            if item["verdict"] == "missing_content" or (item["verdict"] == "allowed_omission" and
                    (plan["detail"] == "full" or section not in omitted)):
                self.issue("blocking", "missing_content", f"Section {section}: {item['justification']}")
        if missing := sections - seen:
            raise ValueError("The review leaves eligible sections unchecked: " + ", ".join(sorted(missing)))


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
             "not factual"
             + (f"; {counts['carried']} of these findings are carried unchanged from the review of storyboard "
                f"`{record['carried']['from_storyboard_digest'][:12]}`, whose targets, claims, and evidence are "
                "the same" if counts.get("carried") else ""),
             f"- Repair rounds used: {record['repairs']['used']} of {record['repairs']['max']}",
             "", "Semantic verdicts come from a separate model review against the evidence. Lexical results come from "
             "pgvideo's lookups of names, numbers, and quoted strings in the pinned source; they are shown apart and "
             "never count as approval of a whole sentence. Neither is a substitute for a person's listening review.",
             "", f"**Reviewer summary:** {record['summary']}", "",
             "## Whole-video review", "",
             *(f"- **{record['overall'][name]['verdict']}** `{name}` — {record['overall'][name]['message']}"
               for name in OVERALL), ""]
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
        lines += [f"- {e['severity']} `{e['code']}` ({', '.join([e['scene'], *e.get('related', [])])}): "
                  f"{e['message']}" for e in record["editorial"]]
    lines += ["", "## Source-to-video coverage", ""]
    lines += [f"- `{c['section']}`: **{c['verdict']}** — {c['justification']}" for c in record["coverage"]]
    return "\n".join(lines).rstrip() + "\n"
