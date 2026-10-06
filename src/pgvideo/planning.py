"""Import and check the harness-authored content plan (harness requests).

The plan is the harness's editorial decision: the main answer, learning
objectives, the claims to teach in order, the caveats that must survive, a time
budget per outline item, and a reason for every eligible section it leaves out.
Each claim carries the harness's semantic assessment against its evidence.

pgvideo checks what code can check: the file matches schemas/plan.schema.json and
names this request and its current evidence packet; every source and evidence ID
resolves; selected sources are eligible and were not left out by a reviewer's
resolution; the request's audience, detail, and target are unchanged; Step 6
corrections are applied and lexical lookups did not fail; every eligible section
is either selected or omitted with a reason; the question and the page's own
summary are selected by a claim and not omitted; and the budget fits the target
within the tolerance. A contradicted or unsupported claim, or an infeasible plan,
is recorded and the plan needs review; it is never silently dropped or accepted.
A repair that does not converge is stopped after a bounded number of imports.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from . import contracts
from .crosscheck import _recorded
from .evidence import Resolver, packet
from .orchestration import (DURATION_TOLERANCE, RepairStopped, accepted_request_ids, canonical_digest,
                            count_plan_import, is_harness, plan_repair_stopped, producer, record_event, request,
                            save_authored)
from .script import PARTS, _key, _words
from .sources import write_atomic
from .stages import invalidate_after

SCHEMA_VERSION = 1
PLAN = "plan.json"
REPORT = "plan-report.md"
SEVERITIES = ("blocking", "warning", "note")
# Excluded from the plan's content digest: who produced it and when do not change what it says.
REQUEST_FIELDS = ("request_id", "created_at", "producer", "authored")
# An outline item's budget below this share of its claims' spoken length cannot hold them.
MIN_BUDGET_SHARE = 0.5
LATE_PARTS = ("terminology", "mechanism", "example", "supporting")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def import_plan(root: Path, run_dir: Path, path: Path, *, revision: str | None = None, limited: bool = True) -> dict:
    """Validate a plan file and record it as the request's plan stage; return the manifest record.

    The record's status is 'passed' or 'needs_review'. A malformed or stale file
    marks the stage 'failed' and raises ValueError. An import that does not pass
    counts toward the repair limit. Once pgvideo has stopped a repair that is not
    converging, a further import is refused without changing the request, unless
    a person made the revision (`revision="human"`). Revalidating saved content
    (`limited=False`) is neither counted nor refused.
    """
    counted = limited and is_harness(run_dir)
    stopped = plan_repair_stopped(run_dir) if counted and revision != "human" else None
    if stopped:
        report = f" and runs/{run_dir.name}/{REPORT}" if (run_dir / REPORT).is_file() else ""
        raise RepairStopped(f"The plan repair was stopped because it is not converging: {stopped}. Report the "
                            f"unresolved issues{report} to the user; a revision a person makes is imported with "
                            "--human-revision.")
    try:
        return _import(root, run_dir, path, revision=revision, counted=counted)
    except (ValueError, OSError) as error:
        _update_manifest(root, run_dir, status="failed", error=str(error))
        if counted:
            count_plan_import(root, run_dir, status="failed")
        raise


def _blocker(issue: dict) -> str:
    """Name a blocking issue by its code and the section or claim it is about, for the repair limit."""
    subject = issue.get("section") or issue.get("claim")
    return f"{issue['code']} ({subject})" if subject else issue["code"]


def _import(root: Path, run_dir: Path, path: Path, *, revision: str | None = None, counted: bool = True) -> dict:
    if not is_harness(run_dir):
        raise ValueError(f"Request {run_dir.name} predates the harness workflow; it has no plan stage.")
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    evidence = packet(run_dir, manifest)
    file = contracts.project_file(root, path, label="Plan file")
    data = file.read_bytes()
    where = file.relative_to(root).as_posix()
    raw = contracts.parse(data, where)
    contracts.require(root, "plan", raw, where)
    if raw["request_id"] not in accepted_request_ids(run_dir):
        raise ValueError(f"{where} is for request {raw['request_id']}, not {run_dir.name}.")
    if raw["evidence_digest"] != manifest["evidence"]["digest"]:
        raise ValueError(f"{where} was made from other evidence (digest {raw['evidence_digest'][:12]}); the current "
                         f"evidence packet has digest {manifest['evidence']['digest'][:12]}. Plan again from "
                         f"runs/{run_dir.name}/evidence-packet.json.")
    made_by = producer(root, raw["producer"], phase="plan")
    record = _Check(root, run_dir, raw, evidence, manifest).build()
    record["producer"] = made_by
    record["authored"] = save_authored(root, run_dir, "plan.json", data)
    digest = canonical_digest(record, exclude=REQUEST_FIELDS)
    body = (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    relative = run_dir.relative_to(root)
    write_atomic(root, relative / PLAN, body, label="Request")
    write_atomic(root, relative / REPORT, _render(record).encode("utf-8"), label="Request")
    sha = hashlib.sha256(body).hexdigest()
    entry = _update_manifest(root, run_dir, status=record["status"], record=record, sha=sha, digest=digest,
                             evidence_digest=manifest["evidence"]["digest"])
    record_event(root, run_dir, stage="plan", status=record["status"], artifact=PLAN, sha256=sha, producer=made_by,
                 authored=record["authored"], revised_by="human" if revision == "human" else None)
    if counted or record["status"] == "passed":
        count_plan_import(root, run_dir, status=record["status"],
                          blockers=[_blocker(issue) for issue in record["issues"] if issue["severity"] == "blocking"])
    return entry


class _Check:
    def __init__(self, root: Path, run_dir: Path, raw: dict, evidence: dict, manifest: dict):
        self.raw, self.evidence, self.run_dir = raw, evidence, run_dir
        self.resolver = Resolver(root, run_dir)
        self.settings = request(run_dir).get("settings") or {}
        check = json.loads(_recorded(run_dir, "glossary-check.json", manifest["glossary_check"]))
        self.lexical = {claim["at"]: claim for claim in check["claims"]}
        self.corrections: dict[str, list[dict]] = {}
        for correction in check["corrections"]:
            self.corrections.setdefault(correction["at"], []).append(correction)
        self.omitted = {at: omission for omission in check["omissions"] for at in omission["at"]}
        self.sections = {section["id"]: section for section in evidence["sections"]}
        self.entries = {entry["anchor"]: entry for entry in evidence["glossary"]["entries"]}
        self.question = ((evidence["document"].get("question") or {}).get("section"))
        self.issues: list[dict] = []

    def issue(self, severity: str, code: str, message: str, *, claim: str | None = None, section: str | None = None,
              action: str | None = None) -> None:
        self.issues.append({"severity": severity, "code": code, "message": message, "claim": claim,
                            "section": section, "action": action})

    def build(self) -> dict:
        raw = self.raw
        self._constraints()
        claims = self._claims()
        outline = self._outline(claims)
        omissions = self._coverage(claims)
        self._caveats(claims, outline)
        estimate = self._budget(claims, outline)
        return {
            "schema": SCHEMA_VERSION,
            "request_id": self.run_dir.name,
            "created_at": _now(),
            "status": "needs_review" if any(i["severity"] == "blocking" for i in self.issues) else "passed",
            "evidence_digest": raw["evidence_digest"],
            "audience": raw["audience"], "detail": raw["detail"], "target_minutes": raw["target_minutes"],
            "main_answer": raw["main_answer"],
            "learning_objectives": raw["learning_objectives"],
            "claims": list(claims.values()),
            "outline": outline,
            "required_caveats": raw.get("required_caveats", []),
            "omissions": omissions,
            "feasibility": raw["feasibility"],
            "estimate": estimate,
            "coverage": self._sections(claims, omissions),
            "issues": self.issues,
        }

    def _constraints(self) -> None:
        settings, raw = self.settings, self.raw
        wanted = {"audience": settings.get("audience"), "detail": settings.get("detail"),
                  "target_minutes": settings.get("target_minutes")}
        for key, value in wanted.items():
            given = raw[key]
            same = (given is None and value is None) or (
                given is not None and value is not None and (math.isclose(float(given), float(value))
                                                             if key == "target_minutes" else
                                                             str(given).strip() == str(value).strip()))
            if not same:
                self.issue("blocking", "constraint_changed", f"The plan's {key} is {given!r}; the request asks for "
                           f"{value!r}. Explicit user constraints are kept through every retry.",
                           action=f"Plan for {key} {value!r}.")

    def _unit_section(self, unit_id: str) -> str | None:
        return (self.resolver.units.get(unit_id) or {}).get("section")

    def _meant(self, source: str) -> str | None:
        """The one unit ID that differs from a misspelled source only in punctuation or case, if there is one."""
        def squash(text: str) -> str:
            return re.sub(r"[^a-z0-9]+", "-", text.lower())

        found = [unit for unit in self.resolver.units if squash(unit) == squash(source)]
        return found[0] if len(found) == 1 else None

    def _claims(self) -> dict[str, dict]:
        claims: dict[str, dict] = {}
        for item in self.raw["claims"]:
            if item["id"] in claims:
                raise ValueError(f"The plan uses the claim ID {item['id']} twice.")
            claims[item["id"]] = item
        for claim_id, item in claims.items():
            where = {"claim": claim_id}
            for source in item["sources"]:
                unit = self.resolver.units.get(source)
                if not unit:
                    meant = self._meant(source)
                    self.issue("blocking", "unknown_source", f"{source} is not a unit of the document.", **where,
                               action=(f"Cite {meant}. " if meant else "Copy the unit ID from `packet --section`. ")
                               + "Only a claim's own `id` is hyphenated; `sources` keep the document's unit IDs, "
                                 "dots included.")
                    continue
                section = self.sections.get(unit["section"]) or {}
                if not section.get("eligible"):
                    reason = section.get("reason") or "reference, navigation, or title"
                    self.issue("blocking", "ineligible_source", f"{source} is in section {unit['section']}, which is "
                               f"not eligible for narration ({reason}).", **where)
                elif unit.get("maintenance"):
                    self.issue("blocking", "ineligible_source", f"{source} is maintenance text.", **where)
                if source in self.omitted:
                    omission = self.omitted[source]
                    self.issue("blocking", "omitted_by_review", f"{source} was left out by the resolution "
                               f"{omission['id']}: {omission['reason']}", **where)
                lexical = self.lexical.get(source)
                if lexical and lexical["resolution"]["status"] == "unresolved":
                    missing = [i["text"] for i in lexical["items"] if not i["level"] and not i.get("waived")]
                    if lexical["status"] == "unconfirmed":
                        self.issue("blocking", "lexical_unconfirmed", f"{source}: " + ", ".join(
                            f"`{m}`" for m in missing) + " is not in the pinned evidence. An exact lookup is "
                            "authoritative; a model's assessment cannot waive it.", **where,
                            action="Leave the sentence out, or have a person record a resolution.")
                    elif lexical["status"] == "uncited":
                        self.issue("warning", "uncited_source", f"{source} cites no PostgreSQL source; its support "
                                   "rests on the review of the document's own evidence.", **where)
                for correction in self.corrections.get(source, []):
                    if _key(correction.get("corrected") or "") not in _key(item["text"]):
                        self.issue("blocking", "correction_not_applied", f"{source} has the Step 6 correction "
                                   f"{correction['id']}; the claim must state {correction.get('corrected')!r}.",
                                   **where, action=correction.get("instruction"))
            for anchor in item.get("glossary", []):
                entry = self.entries.get(anchor)
                if not entry:
                    self.issue("blocking", "unknown_glossary", f"#{anchor} is not a glossary entry this page "
                               "matched.", **where)
                elif item["kind"] == "definition" and not entry["allowed_in_narration"]:
                    self.issue("blocking", "definition_not_allowed", f"The cross-check does not allow narrating the "
                               f"definition of #{anchor} ({entry['result']}).", **where)
            assessment = item["assessment"]
            for reference in assessment["evidence"]:
                if problem := self.resolver.problem(reference):
                    self.issue("blocking", "unresolved_evidence", problem, **where)
            support = assessment["source_support"]
            if support == "supported" and not assessment["evidence"]:
                self.issue("blocking", "unsupported_assessment", "A supported claim needs the evidence IDs that "
                           "support it.", **where)
            elif support == "contradicted":
                self.issue("blocking", "claim_contradicted", f"The planning assessment finds the evidence contradicts "
                           f"this claim: {assessment['justification']}", **where,
                           action="Leave the claim out and give the omission a reason, or ask a person to record a "
                                  "resolution.")
            elif support == "insufficient_evidence":
                self.issue("blocking", "insufficient_evidence", f"The evidence does not establish this claim: "
                           f"{assessment['justification']}", **where,
                           action="Leave the claim out, or record the missing evidence and request review.")
            if assessment["glossary"] == "inconsistent":
                self.issue("blocking", "glossary_inconsistent", "The planning assessment finds the claim inconsistent "
                           f"with the version-scoped glossary: {assessment['justification']}", **where)
            for dependency in item.get("depends_on", []):
                if dependency not in claims:
                    self.issue("blocking", "unknown_claim", f"depends_on names unknown claim {dependency}.", **where)
        for claim_id in self.raw["main_answer"]["claims"]:
            if claim_id not in claims:
                self.issue("blocking", "unknown_claim", f"The main answer names unknown claim {claim_id}.")
        return {claim_id: item | {"lexical": {source: self.lexical[source]["status"] for source in item["sources"]
                                              if source in self.lexical}}
                for claim_id, item in claims.items()}

    def _outline(self, claims: dict[str, dict]) -> list[dict]:
        seen, used, outline = set(), set(), []
        for item in self.raw["outline"]:
            if item["id"] in seen:
                raise ValueError(f"The plan's outline uses the ID {item['id']} twice.")
            seen.add(item["id"])
            for claim_id in item["claims"]:
                if claim_id not in claims:
                    self.issue("blocking", "unknown_claim", f"Outline item {item['id']} names unknown claim "
                               f"{claim_id}.")
                used.add(claim_id)
            outline.append(item)
        for claim_id in claims:
            if claim_id not in used:
                self.issue("warning", "unplanned_claim", f"Claim {claim_id} is in no outline item and will not be "
                           "narrated.", claim=claim_id)
        answer = set(self.raw["main_answer"]["claims"])
        positions = [n for n, item in enumerate(outline) if answer & set(item["claims"])]
        if not positions:
            self.issue("blocking", "answer_missing", "No outline item narrates the main answer's claims.")
        else:
            earlier = [item["part"] for item in outline[:positions[0]] if item["part"] in LATE_PARTS]
            if earlier:
                self.issue("warning", "answer_late", "The main answer comes after " + ", ".join(dict.fromkeys(earlier))
                           + " content; lead with the answer unless a term is needed to state it.")
        for item in outline:
            if item["part"] not in PARTS:
                raise ValueError(f"Outline item {item['id']} has an unknown part {item['part']}.")
        return outline

    def _selected_sections(self, claims: dict[str, dict]) -> set[str]:
        selected = set()
        for item in claims.values():
            for source in item["sources"]:
                section = self._unit_section(source)
                while section:
                    selected.add(section)
                    section = (self.sections.get(section) or {}).get("parent")
        return selected

    def _coverage(self, claims: dict[str, dict]) -> list[dict]:
        selected = self._selected_sections(claims)
        omissions, seen = [], set()
        for item in self.raw["omissions"]:
            section = self.sections.get(item["section"])
            if not section:
                self.issue("blocking", "unknown_section", f"The omission names unknown section {item['section']}.",
                           section=item["section"])
                continue
            if item["section"] in seen:
                continue
            seen.add(item["section"])
            if item["section"] in selected and any(self._unit_section(s) == item["section"]
                                                   for c in claims.values() for s in c["sources"]):
                self.issue("warning", "omitted_but_selected", f"Section {item['section']} is listed as omitted, but "
                           "the plan selects claims from it.", section=item["section"])
            omissions.append({"section": item["section"], "heading": section["heading"], "reason": item["reason"]})
            if self._is_essential(section):
                self._essential(section, omitted=True, selected=item["section"] in selected)
            elif section["caveat"] or section["role"] == "open_questions":
                self.issue("warning", "caveat_omitted", f"Section {item['section']} ({section['heading']}) holds "
                           f"caveats and is left out: {item['reason']} The content review must confirm no material "
                           "qualification is lost.", section=item["section"])
        for section in self.sections.values():
            if not section["eligible"] or not section["blocks"] or section["id"] in selected or section["id"] in seen:
                continue
            if self._is_essential(section):
                # Reported like an omission: offering to omit it would send the harness back and forth.
                self._essential(section, omitted=False, selected=False)
                continue
            self.issue("blocking", "section_unaccounted", f"Eligible section {section['id']} ({section['heading']}) "
                       "is neither selected nor omitted with a reason.", section=section["id"],
                       action="Select claims from it, or add {section, reason} to omissions. `packet --omissions-template "
                              "--plan <file>` writes the patch that omits every unaccounted section.")
        return omissions

    def _is_essential(self, section: dict) -> bool:
        return section["id"] == self.question or section["role"] == "summary"

    def _essential(self, section: dict, *, omitted: bool, selected: bool) -> None:
        """Report the question or the page's own summary when the plan omits it or no claim selects it.

        Both states are one issue with one fix. A section is selected only by a
        claim that cites one of its units; an outline item does not select it.
        """
        what = "question" if section["id"] == self.question else "own summary"
        state = "It is listed in `omissions`." if omitted else "No claim cites one of its units."
        if selected:
            action = "Remove it from `omissions`; a claim already cites it."
        else:
            units = {unit: info for unit, info in self.resolver.units.items() if info.get("section") == section["id"]}
            sentences = [unit for unit, info in units.items() if info.get("kind") == "sentence"]
            unit = next(iter(sentences or units), None)
            action = ("Cite one of its unit IDs" + (f", such as `{unit}`," if unit else "") + " in the `sources` of a "
                      "claim that an outline item narrates" + (", and remove it from `omissions`" if omitted else "")
                      + ". Only claim `sources` select a section; an outline item's `part` or title does not.")
        self.issue("blocking", "essential_omitted", f"Section {section['id']} ({section['heading']}) is the page's "
                   f"{what}; a video cannot leave it out. {state}", section=section["id"], action=action)

    def _caveats(self, claims: dict[str, dict], outline: list[dict]) -> None:
        planned = {claim_id for item in outline for claim_id in item["claims"]}
        for caveat in self.raw.get("required_caveats", []):
            if caveat["claim"] not in claims:
                self.issue("blocking", "unknown_claim", f"Required caveat {caveat['claim']} is not a claim.")
            elif caveat["claim"] not in planned:
                self.issue("blocking", "caveat_not_planned", f"Required caveat {caveat['claim']} is in no outline "
                           "item.", claim=caveat["claim"])

    def _budget(self, claims: dict[str, dict], outline: list[dict]) -> dict:
        speech = self.evidence["speech"]
        rate = speech["words_per_minute"]
        total = round(sum(item["budget_seconds"] for item in outline), 1)
        spoken = 0.0
        for item in outline:
            words = sum(_words(claims[c]["text"]) for c in item["claims"] if c in claims)
            needed = words / rate * 60
            spoken += needed
            if needed and item["budget_seconds"] < needed * MIN_BUDGET_SHARE:
                self.issue("warning", "budget_too_small", f"Outline item {item['id']} budgets "
                           f"{item['budget_seconds']} seconds for claims that take about {round(needed)} seconds "
                           "to say.")
        target = self.raw["target_minutes"]
        estimate = {"budget_seconds": total, "claim_seconds": round(spoken, 1), "words_per_minute": rate,
                    "rate_basis": speech["basis"], "target_seconds": round(target * 60, 1) if target else None,
                    "tolerance": DURATION_TOLERANCE if target else None}
        feasible = self.raw["feasibility"]["status"] == "feasible"
        if not feasible:
            self.issue("blocking", "infeasible_plan", "The harness reports that the mandatory content does not fit "
                       f"the target: {self.raw['feasibility'].get('note') or '(no note)'}",
                       action="Report this to the user with the saved request ID; do not drop a qualification or "
                              "exceed the target silently.")
        elif target:
            high, low = target * 60 * (1 + DURATION_TOLERANCE), target * 60 * (1 - DURATION_TOLERANCE)
            if total > high:
                self.issue("blocking", "over_budget", f"The outline budgets {total} seconds, more than the "
                           f"{target}-minute target allows ({round(high)} seconds with the tolerance).",
                           action="Shorten optional detail, or mark the plan infeasible with a note.")
            elif total < low:
                self.issue("note", "under_budget", f"The outline budgets {total} seconds, under the {target}-minute "
                           "target; a short page may need less.")
        return estimate

    def _sections(self, claims: dict[str, dict], omissions: list[dict]) -> list[dict]:
        omitted = {item["section"]: item["reason"] for item in omissions}
        used: dict[str, list[str]] = {}
        for claim_id, item in claims.items():
            for source in item["sources"]:
                section = self._unit_section(source)
                if section:
                    used.setdefault(section, [])
                    if claim_id not in used[section]:
                        used[section].append(claim_id)
        return [{"section": s["id"], "heading": s["heading"], "eligible": s["eligible"], "caveat": s["caveat"],
                 "static_decision": (s.get("static_coverage") or {}).get("decision"),
                 "claims": used.get(s["id"], []), "omitted": omitted.get(s["id"])} for s in self.sections.values()]


def omissions_template(root: Path, run_dir: Path, evidence: dict, raw: dict | None = None) -> dict:
    """List the eligible sections a plan leaves unaccounted, as a `revise` patch that omits them.

    Without a plan, every eligible section is listed. Each omission has an empty
    reason, which the plan schema rejects: the harness removes the sections it
    selects claims from and writes the reasons. The question and the page's own
    summary cannot be omitted, so they are named under `essential` instead.
    """
    raw = raw if isinstance(raw, dict) else {}
    units = Resolver(root, run_dir).units
    sections = {section["id"]: section for section in evidence["sections"]}
    question = (evidence["document"].get("question") or {}).get("section")
    accounted = {item.get("section") for item in raw.get("omissions") or [] if isinstance(item, dict)}
    for claim in raw.get("claims") or []:
        for source in (claim.get("sources") or []) if isinstance(claim, dict) else []:
            section = (units.get(source) or {}).get("section") if isinstance(source, str) else None
            while section:
                accounted.add(section)
                section = (sections.get(section) or {}).get("parent")
    open_ = [s for s in sections.values() if s["eligible"] and s["blocks"] and s["id"] not in accounted]
    essential = [s for s in open_ if s["id"] == question or s["role"] == "summary"]
    omit = [s for s in open_ if s not in essential]
    return {
        "notice": "Remove the sections you select claims from, apply the patch with `revise`, then set each reason. "
                  "A section under `caveats` holds qualifications: omit it only if no kept claim needs them.",
        "patch": [{"op": "add", "path": "omissions",
                   "values": [{"section": s["id"], "reason": ""} for s in omit]}] if omit else [],
        "sections": [{"id": s["id"], "heading": s["heading"], "words": s.get("words")} for s in omit],
        "caveats": [s["id"] for s in omit if s["caveat"] or s["role"] == "open_questions"],
        "essential": [s["id"] for s in essential],
    }


def accepted(run_dir: Path, manifest: dict) -> dict:
    """Return the accepted plan of a harness request after checking it against the manifest."""
    record = manifest.get("plan") or {}
    if record.get("status") != "passed":
        raise ValueError(f"The plan stage has status '{record.get('status')}'; import an accepted plan with "
                         f"scripts/pgvideo plan --request {run_dir.name} --file <plan>.")
    if record.get("evidence_digest") != (manifest.get("evidence") or {}).get("digest"):
        raise ValueError("The accepted plan was made from other evidence; plan again.")
    return json.loads(_recorded(run_dir, PLAN, record))


def _update_manifest(root: Path, run_dir: Path, *, status: str, record: dict | None = None, sha: str | None = None,
                     digest: str | None = None, evidence_digest: str | None = None, error: str | None = None) -> dict:
    path = run_dir / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    manifest["status"] = {"passed": "plan_ready"}.get(status, status)
    invalidate_after(manifest, "plan")
    entry: dict = {"status": status}
    if error:
        entry["error"] = error
    if record:
        entry.update({"record": PLAN, "report": REPORT, "sha256": sha, "digest": digest,
                      "evidence_digest": evidence_digest, "created_at": record["created_at"],
                      "schema": record["schema"], "authored": record["authored"], "estimate": record["estimate"],
                      "counts": {"claims": len(record["claims"]), "outline": len(record["outline"]),
                                 "omissions": len(record["omissions"])},
                      "issues": {severity: sum(i["severity"] == severity for i in record["issues"])
                                 for severity in SEVERITIES}})
    manifest["plan"] = entry
    write_atomic(root, run_dir.relative_to(root) / "manifest.json",
                 (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"), label="Request")
    return entry


def _cell(text) -> str:
    return " ".join(str(text if text is not None else "—").split()).replace("|", "\\|")


def _render(record: dict) -> str:
    estimate = record["estimate"]
    lines = [f"# Content plan: request {record['request_id']}", "",
             f"- Status: **{record['status']}**",
             f"- Audience: {record['audience']}; detail: {record['detail']}; target: "
             + (f"{record['target_minutes']} minutes (±{int(estimate['tolerance'] * 100)}%)"
                if record["target_minutes"] else "none (full detail)"),
             f"- Budget: {estimate['budget_seconds']} seconds; the claims alone take about "
             f"{estimate['claim_seconds']} seconds at {estimate['words_per_minute']} words per minute "
             f"({estimate['rate_basis']} rate)",
             f"- Producer: {record['producer']['harness']['name']}, model "
             + (record["producer"]["model"] if isinstance(record["producer"]["model"], str) else
                record["producer"]["model"].get("resolved") or record["producer"]["model"].get("requested") or
                "unavailable"),
             "", f"**Main answer:** {record['main_answer']['text']}", "", "## Learning objectives", ""]
    lines += [f"- {objective}" for objective in record["learning_objectives"]]
    lines.append("")
    if record["issues"]:
        lines += ["## Issues", ""]
        for severity in SEVERITIES:
            for issue in (i for i in record["issues"] if i["severity"] == severity):
                where = " · ".join(filter(None, [issue.get("claim"), issue.get("section")]))
                lines.append(f"- **{severity}** `{issue['code']}`" + (f" ({where})" if where else "")
                             + f": {issue['message']}" + (f" {issue['action']}" if issue.get("action") else ""))
        lines.append("")
    lines += ["## Outline", "", "| Item | Part | Title | Claims | Budget (s) |", "|---|---|---|---|---|"]
    for item in record["outline"]:
        lines.append(f"| `{item['id']}` | {item['part']} | {_cell(item['title'])} | "
                     f"{', '.join(item['claims']) or '—'} | {item['budget_seconds']} |")
    lines += ["", "## Claims", ""]
    for claim in record["claims"]:
        assessment = claim["assessment"]
        lines.append(f"- `{claim['id']}` ({claim['kind']}): {claim['text']}")
        lines.append(f"  - Sources: {', '.join(claim['sources'])}; lexical lookup: "
                     + (", ".join(f"{k} {v}" for k, v in claim["lexical"].items()) or "not a checked claim"))
        lines.append(f"  - Semantic assessment: {assessment['source_support']}, glossary {assessment['glossary']}; "
                     f"evidence {', '.join(assessment['evidence']) or '—'}. {assessment['justification']}")
    lines += ["", "## Section coverage", "", "| Section | Eligible | Old static map | Claims | Omitted because |",
              "|---|---|---|---|---|"]
    for row in record["coverage"]:
        lines.append(f"| {_cell(row['heading'])} (`{row['section']}`) | {'yes' if row['eligible'] else 'no'} | "
                     f"{row['static_decision'] or '—'} | {', '.join(row['claims']) or '—'} | "
                     f"{_cell(row['omitted'])} |")
    return "\n".join(lines) + "\n"
