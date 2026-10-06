"""The harness workflow: request mode, the orchestration record, stage results, and the content gate.

Every request made with `prepare` is a harness request. An LLM harness that
follows the root AGENTS.md writes its content plan, storyboard, and a separate
semantic review; pgvideo imports each one, validates it, and alone records stage
statuses in manifest.json. Requests made before this workflow keep their original
provenance: they have no `workflow` record and are replayed as extractive requests.

orchestration.json records the instructions and prompts a request ran under, who
produced each accepted artifact (as far as the harness reports it), the repair
rounds used, and any media inspection that was actually performed. It is a trace,
not proof of authorship; the gates below are enforced in code either way.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from .sources import write_atomic
from .stages import STAGES, invalidate_after

WORKFLOW = "harness"
INSTRUCTIONS = "AGENTS.md"
ORCHESTRATION = "orchestration.json"
LAST_RESULT = "last-result.json"
# Exact bytes of the plan, storyboard, and review files the harness submitted and pgvideo accepted.
AUTHORED = "authored"
PROMPTS = ("prompts/plan.md", "prompts/draft.md", "prompts/review.md", "prompts/repair.md", "prompts/media-review.md")
SCHEMAS = ("schemas/plan.schema.json", "schemas/storyboard.schema.json", "schemas/review.schema.json",
           "schemas/stage-result.schema.json", "schemas/media-review.schema.json")
VERSION_LINE = re.compile(r"(?m)^<!-- instructions-version: (\d+) -->\s*$")
# Bump when the review rules change; an accepted review under an older policy must be repeated.
REVIEW_POLICY = 3
# Storyboard revisions allowed after a failed content review, and rewrites after a measured-duration miss.
MAX_REPAIR_ROUNDS = 2
# A plan repair stops when this many imports in a row have not passed, or this many judged imports in a row
# report one blocking issue. A harness that cannot fix an issue otherwise imports revisions without end.
MAX_PLAN_IMPORTS = 10
MAX_SAME_BLOCKER = 3
# A result folds more issues of one severity and code than this into a single issue.
ISSUE_GROUP_LIMIT = 3
ISSUE_EXAMPLES = 3
ISSUE_SUBJECTS = ("scene", "narration", "target", "claim", "section")
STAGE_REPORTS = {"plan": "plan-report.md", "script": "script.md", "content_review": "content-report.md",
                 "media_review": "media-review.json"}
MAX_DURATION_REWRITES = 1
DURATION_TOLERANCE = 0.15
DEFAULT_AUDIENCE = "PostgreSQL users and administrators who know SQL"
DEFAULT_TARGET_MINUTES = {"summary": 3.0, "standard": 8.0, "full": None}
UNAVAILABLE = "unavailable"
STATUSES = ("passed", "completed", "needs_review", "failed")
PRODUCER_KEYS = {"harness", "model", "prompt", "parameters", "usage", "latency_seconds", "replayed_from"}


class RepairStopped(ValueError):
    """An import pgvideo refuses because the repair is not converging; a person decides what happens next."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(value) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def canonical_digest(value: dict, *, exclude=()) -> str:
    """Hash a record without its request-specific fields, so equal content has equal digests across requests."""
    content = {key: item for key, item in value.items() if key not in exclude}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


# Request mode ------------------------------------------------------------------------------------


def request(run_dir: Path) -> dict:
    path = run_dir / "request.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def is_harness(run_dir: Path) -> bool:
    """A request made by `prepare`; a request without a workflow record predates the harness workflow."""
    return (request(run_dir).get("workflow") or {}).get("kind") == WORKFLOW


def instructions(root: Path) -> dict:
    """Return the root runbook's path, declared version, and SHA-256."""
    path = root / INSTRUCTIONS
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{INSTRUCTIONS} is missing from the project root; the harness workflow needs it.")
    text = path.read_text(encoding="utf-8")
    match = VERSION_LINE.search(text)
    if not match:
        raise ValueError(f"{INSTRUCTIONS} must declare `<!-- instructions-version: N -->`.")
    return {"file": INSTRUCTIONS, "version": int(match.group(1)), "sha256": _sha(path)}


def _hashes(root: Path, names) -> dict:
    return {name: _sha(root / name) if (root / name).is_file() else None for name in names}


def prompt_hashes(root: Path) -> dict:
    return _hashes(root, PROMPTS)


def schema_hashes(root: Path) -> dict:
    return _hashes(root, SCHEMAS)


# Orchestration record ----------------------------------------------------------------------------


def load_record(run_dir: Path) -> dict:
    path = run_dir / ORCHESTRATION
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def save_record(root: Path, run_dir: Path, record: dict) -> None:
    write_atomic(root, run_dir.relative_to(root) / ORCHESTRATION, _json(record), label="Request")


def start_record(root: Path, run_dir: Path, request_record: dict) -> dict:
    record = {
        "schema": 1,
        "request_id": request_record["request_id"],
        "created_at": _now(),
        "workflow": WORKFLOW,
        "instructions": {**instructions(root), "recorded_at": _now(), "history": []},
        "prompts": prompt_hashes(root),
        "schemas": schema_hashes(root),
        "review_policy": REVIEW_POLICY,
        "constraints": {key: request_record["settings"].get(key)
                        for key in ("detail", "audience", "target_minutes", "voice", "language", "speed")},
        "repairs": {"storyboard": 0, "duration": 0, "plan_imports": 0},
        "events": [],
        "media_reviews": [],
        "note": "Producer metadata is what the harness reported; unreported values are marked unavailable. "
                "A declaration here does not prove which model wrote an artifact.",
    }
    save_record(root, run_dir, record)
    return record


def record_event(root: Path, run_dir: Path, *, stage: str, status: str, artifact: str | None = None,
                 sha256: str | None = None, producer: dict | None = None, **extra) -> dict:
    record = load_record(run_dir)
    event = {"at": _now(), "stage": stage, "status": status}
    if artifact:
        event["artifact"] = {"file": artifact, "sha256": sha256}
    if producer is not None:
        event["producer"] = producer
    event.update({key: value for key, value in extra.items() if value is not None})
    record.setdefault("events", []).append(event)
    save_record(root, run_dir, record)
    return event


def producer(root: Path, value, *, phase: str) -> dict:
    """Normalize the producer block of a harness artifact; never invent metadata the harness did not report."""
    if value is None:
        value = {}
    if not isinstance(value, dict) or set(value) - PRODUCER_KEYS:
        raise ValueError(f"`producer` must be a mapping with only {', '.join(sorted(PRODUCER_KEYS))}.")
    harness = value.get("harness")
    if not isinstance(harness, dict) or not isinstance(harness.get("name"), str) or not harness["name"].strip():
        raise ValueError("`producer.harness.name` must name the harness that produced this artifact.")
    model = value.get("model", UNAVAILABLE)
    if model != UNAVAILABLE and not (isinstance(model, dict) and set(model) <= {"requested", "resolved", "provider"}
                                     and all(isinstance(v, str) for v in model.values())):
        raise ValueError("`producer.model` must be `unavailable` or {requested, resolved, provider} strings.")
    prompt = value.get("prompt")
    expected = f"prompts/{phase}.md"
    prompt_record = None
    if prompt is not None:
        if prompt not in PROMPTS:
            raise ValueError(f"`producer.prompt` must be one of {', '.join(PROMPTS)}.")
        # The hash is computed here, not taken from the harness.
        prompt_record = {"file": prompt, "sha256": _sha(root / prompt) if (root / prompt).is_file() else None,
                         "expected": prompt == expected or phase == "repair"}
    latency = value.get("latency_seconds", UNAVAILABLE)
    if latency != UNAVAILABLE and (isinstance(latency, bool) or not isinstance(latency, (int, float))
                                   or not math.isfinite(latency) or latency < 0):
        raise ValueError("`producer.latency_seconds` must be a nonnegative number or `unavailable`.")
    usage = value.get("usage", UNAVAILABLE)
    if usage != UNAVAILABLE and not (isinstance(usage, dict) and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in usage.values())):
        raise ValueError("`producer.usage` must be numeric counters, such as input_tokens, or `unavailable`.")
    parameters = value.get("parameters", UNAVAILABLE)
    if parameters != UNAVAILABLE and not isinstance(parameters, dict):
        raise ValueError("`producer.parameters` must be a mapping or `unavailable`.")
    result = {"harness": {"name": harness["name"].strip(), "version": str(harness.get("version") or UNAVAILABLE)},
              "model": model, "prompt": prompt_record or UNAVAILABLE, "parameters": parameters, "usage": usage,
              "latency_seconds": latency}
    if value.get("replayed_from"):
        result["replayed_from"] = str(value["replayed_from"])
    return result


def check_instructions(root: Path, run_dir: Path) -> list[str]:
    """Record a change to AGENTS.md since the request started; a new version reopens the content stages.

    Returns messages for the stage result. A changed hash with the same version is
    recorded only. A new version drops the accepted plan and everything built on
    it, so `resume` revalidates the saved files under the new policy.
    """
    record = load_record(run_dir)
    if not record:
        return []
    current = instructions(root)
    recorded = record["instructions"]
    if current["sha256"] == recorded["sha256"]:
        return []
    change = {"at": _now(), "from": {"version": recorded["version"], "sha256": recorded["sha256"]},
              "to": {"version": current["version"], "sha256": current["sha256"]}}
    messages = [f"{INSTRUCTIONS} changed since this request started (version {recorded['version']} → "
                f"{current['version']})."]
    if current["version"] != recorded["version"]:
        manifest_path = run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("plan"):
            invalidate_after(manifest, "evidence")
            manifest["status"] = "evidence_ready"
            write_atomic(root, run_dir.relative_to(root) / "manifest.json", _json(manifest), label="Request")
        change["invalidated"] = "plan and later stages"
        messages.append("The instruction version changed, so the accepted plan, storyboard, review, and media "
                        f"must be revalidated: run scripts/pgvideo resume --request {run_dir.name}.")
    record["instructions"] = {**current, "recorded_at": _now(), "history": [*recorded.get("history", []), change]}
    record["prompts"], record["schemas"] = prompt_hashes(root), schema_hashes(root)
    save_record(root, run_dir, record)
    return messages


def accepted_request_ids(run_dir: Path) -> set[str]:
    """This request, and any request whose accepted content it replays; saved files may name either."""
    events = load_record(run_dir).get("events", [])
    return {run_dir.name, *(event["replayed_from"] for event in events
                            if event.get("stage") == "replay" and event.get("replayed_from"))}


def repairs(run_dir: Path) -> dict:
    return load_record(run_dir).get("repairs") or {"storyboard": 0, "duration": 0}


def count_repair(root: Path, run_dir: Path, kind: str) -> int:
    record = load_record(run_dir)
    record.setdefault("repairs", {"storyboard": 0, "duration": 0})
    record["repairs"][kind] = record["repairs"].get(kind, 0) + 1
    if kind == "duration":
        record.pop("pending_duration_check", None)
    save_record(root, run_dir, record)
    return record["repairs"][kind]


def remember_duration_miss(root: Path, run_dir: Path, manifest: dict) -> None:
    """Preserve the measured miss when a needed plan/script revision invalidates narration."""
    check = (manifest.get("narration") or {}).get("duration_check") or {}
    if check.get("status") == "needs_review":
        record = load_record(run_dir)
        record["pending_duration_check"] = check
        save_record(root, run_dir, record)


def plan_repair_stopped(run_dir: Path) -> str | None:
    """Why pgvideo stopped this request's plan repair, or None while the repair may continue."""
    return load_record(run_dir).get("plan_stopped")


def count_plan_import(root: Path, run_dir: Path, *, status: str, blockers: list[str] | None = None) -> str | None:
    """Count a plan import toward the repair limit; return why the repair stops, when this import ends it.

    A pass clears the count. `blockers` names the blocking issues of an import the
    checks judged; None is an import that failed before them, such as a schema
    error. The repair stops when MAX_SAME_BLOCKER judged imports in a row report
    one blocker, or MAX_PLAN_IMPORTS imports in a row have not passed. A stopped
    repair stays stopped until a plan passes.
    """
    record = load_record(run_dir)
    used = record.setdefault("repairs", {"storyboard": 0, "duration": 0})
    if status == "passed":
        used["plan_imports"] = 0
        record.pop("plan_blockers", None)
        record.pop("plan_stopped", None)
        save_record(root, run_dir, record)
        return None
    used["plan_imports"] = used.get("plan_imports", 0) + 1
    stopped = None
    if blockers is not None:
        history = [*record.get("plan_blockers", []), sorted(set(blockers))][-MAX_SAME_BLOCKER:]
        record["plan_blockers"] = history
        same = sorted(set(history[0]).intersection(*history[1:])) if len(history) == MAX_SAME_BLOCKER else []
        if same:
            stopped = (f"the last {MAX_SAME_BLOCKER} plan imports report the same blocking issue: "
                       + ", ".join(same[:ISSUE_EXAMPLES])
                       + (f", and {len(same) - ISSUE_EXAMPLES} more" if len(same) > ISSUE_EXAMPLES else ""))
    if not stopped and used["plan_imports"] >= MAX_PLAN_IMPORTS:
        stopped = f"{used['plan_imports']} plan imports in a row have not passed"
    if stopped:
        record["plan_stopped"] = stopped
    save_record(root, run_dir, record)
    return stopped


def save_authored(root: Path, run_dir: Path, name: str, data: bytes) -> dict:
    """Keep the exact bytes of an accepted harness file, so resume and replay revalidate the same content."""
    relative = run_dir.relative_to(root) / AUTHORED / name
    write_atomic(root, relative, data, label="Request")
    return {"file": f"{AUTHORED}/{name}", "sha256": hashlib.sha256(data).hexdigest()}


# Content gate ------------------------------------------------------------------------------------


def require_content_gate(run_dir: Path, manifest: dict) -> None:
    """Refuse media work for a harness request until its plan and a separate review accept this storyboard.

    Narration, timing, rendering, validation, and media reuse call this, so a
    media command run directly cannot bypass the gate. Older requests keep
    their extractive provenance and are not gated.
    """
    if not is_harness(run_dir):
        return
    plan, script, review = (manifest.get(stage) or {} for stage in ("plan", "script", "content_review"))
    if plan.get("status") != "passed":
        raise ValueError(f"Content gate: the content plan has status '{plan.get('status')}'; import an accepted "
                         f"plan with scripts/pgvideo plan --request {run_dir.name} --file <plan>.")
    if script.get("status") != "passed":
        raise ValueError(f"Content gate: the storyboard has status '{script.get('status')}'.")
    if review.get("status") != "passed":
        raise ValueError(f"Content gate: the semantic content review has status '{review.get('status')}'; import a "
                         f"separate review with scripts/pgvideo review --request {run_dir.name} --file <review>.")
    if review.get("storyboard_sha256") != script.get("sha256") or review.get("plan_sha256") != plan.get("sha256"):
        raise ValueError("Content gate: the accepted review is for another storyboard or plan; review the current "
                         "storyboard.")
    if review.get("policy") != REVIEW_POLICY:
        raise ValueError(f"Content gate: the review used review policy {review.get('policy')}, and the current policy "
                         f"is {REVIEW_POLICY}; review the storyboard again.")


def duration_check(run_dir: Path, seconds: float, storyboard_digest: str | None = None) -> dict | None:
    """Compare measured narration with the request's target; None for an older request.

    A length the user accepted stays accepted when the same storyboard content is
    narrated again to within half a second.
    """
    if not is_harness(run_dir):
        return None
    target = (request(run_dir).get("settings") or {}).get("target_minutes")
    if not target:
        return {"status": "not_applicable", "measured_seconds": round(seconds, 2),
                "message": "Full detail has no duration target."}
    low, high = target * 60 * (1 - DURATION_TOLERANCE), target * 60 * (1 + DURATION_TOLERANCE)
    result = {"measured_seconds": round(seconds, 2), "target_seconds": round(target * 60, 1),
              "tolerance": DURATION_TOLERANCE, "range_seconds": [round(low, 1), round(high, 1)]}
    if low <= seconds <= high:
        return result | {"status": "passed", "message": f"The narration measures {seconds:.1f} seconds, within "
                                                         f"{low:.0f}–{high:.0f} seconds."}
    message = (f"The narration measures {seconds:.1f} seconds; the {target}-minute target allows "
               f"{low:.0f}–{high:.0f} seconds.")
    accepted = load_record(run_dir).get("accepted_duration") or {}
    if storyboard_digest and accepted.get("storyboard_digest") == storyboard_digest \
            and abs(accepted.get("measured_seconds", -1) - seconds) <= 0.5:
        return result | {"status": "accepted", "accepted_at": accepted["at"],
                         "message": message + " The user accepted this length."}
    return result | {"status": "needs_review", "direction": "short" if seconds < low else "long", "message": message}


def require_duration(run_dir: Path, manifest: dict) -> None:
    check = (manifest.get("narration") or {}).get("duration_check") or {}
    if check.get("status") == "needs_review":
        raise ValueError(f"{check['message']} Rewrite optional detail (scripts/pgvideo script --duration-rewrite), "
                         "or have the user accept the length with scripts/pgvideo build --accept-duration.")


# Stage results -----------------------------------------------------------------------------------


def _artifact(run_dir: Path, name: str | None) -> dict | None:
    if not name:
        return None
    path = run_dir / name
    return {"path": str(path), "sha256": _sha(path) if path.is_file() else None}


STAGE_FILES = {
    "sources": ("sources.json", "source-report.md"), "document": ("document.json", "coverage.md"),
    "glossary": ("glossary-matches.json",), "glossary_check": ("glossary-check.json", "glossary-check.md"),
    "evidence": ("evidence-packet.json",), "plan": ("plan.json", "plan-report.md"),
    "script": ("storyboard.json", "script.md", "draft-input.json"),
    "content_review": ("content-review.json", "content-report.md"),
    "narration": ("narration/audio-map.json", "narration/master.wav"),
    "timing": ("timeline.json", "captions.srt", "captions.vtt"), "render": ("render.json", "render/draft.mp4"),
    "validation": ("quality-report.json",),
    "media_review": ("media-review.json",),
    "review_input": ("review-input/index.json",),
    "preview": ("preview/preview.json",),
}


def stage_artifacts(run_dir: Path, stage: str) -> list[dict]:
    return [a for a in (_artifact(run_dir, name) for name in STAGE_FILES.get(stage, ())) if a and a["sha256"]]


def _issues(run_dir: Path, stage: str, record: dict) -> list[dict]:
    """Return a stage's blocking issues and warnings from its JSON record, when it keeps them."""
    names = {"document": "document.json", "glossary_check": "glossary-check.json", "plan": "plan.json",
             "script": "storyboard.json", "content_review": "content-review.json", "media_review": "media-review.json"}
    issues = []
    if record.get("error"):
        issues.append({"severity": "blocking", "code": "stage_failed", "message": record["error"]})
    name = names.get(stage)
    if name and (run_dir / name).is_file() and record.get("status") in ("needs_review", "passed"):
        try:
            loaded = json.loads((run_dir / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            loaded = {}
        for issue in loaded.get("issues", []):
            if issue.get("severity") in ("blocking", "warning"):
                issues.append({key: issue.get(key) for key in ("severity", "code", "message", *ISSUE_SUBJECTS,
                                                               "action") if issue.get(key) is not None})
    return compact_issues(issues, report=STAGE_REPORTS.get(stage))


def compact_issues(issues: list[dict], *, report: str | None = None) -> list[dict]:
    """Fold issues that share a severity and code into one, when there are more than ISSUE_GROUP_LIMIT.

    A result is read by a model with a small context, and one mistake repeated in every
    claim or section otherwise fills it. The folded issue keeps the count, every scene,
    claim, or section it names, the first messages as examples, and the first action.
    The stage's record and report keep each issue in full.
    """
    groups: dict[tuple, list[dict]] = {}
    for issue in issues:
        groups.setdefault((issue.get("severity"), issue.get("code")), []).append(issue)
    compacted = []
    for (severity, code), same in groups.items():
        if len(same) <= ISSUE_GROUP_LIMIT:
            compacted += same
            continue
        examples = list(dict.fromkeys(issue["message"] for issue in same))[:ISSUE_EXAMPLES]
        folded = {"severity": severity, "code": code, "count": len(same),
                  "message": f"{len(same)} issues with this code; `examples` holds the first {len(examples)}."
                             + (f" {report} lists each one." if report else ""),
                  "examples": examples}
        for subject in ISSUE_SUBJECTS:
            named = list(dict.fromkeys(issue[subject] for issue in same if issue.get(subject)))
            if named:
                folded[subject + "s"] = named
        action = next((issue["action"] for issue in same if issue.get("action")), None)
        if action:
            folded["action"] = action
        compacted.append(folded)
    return compacted


def next_actions(run_dir: Path, manifest: dict) -> list[dict]:
    """Return the legal next steps for a request, from the stage records alone."""
    rid = run_dir.name
    tool = "scripts/pgvideo"
    harness = is_harness(run_dir)
    record = load_record(run_dir) if harness else {}
    for stage in ("sources", "document", "glossary"):
        status = (manifest.get(stage) or {}).get("status")
        if status != "passed":
            return [{"action": "escalate", "reason": f"The {stage} stage has status '{status}'. The wiki page or its "
                     "sources need a fix; a person must decide, then a new request is prepared."}]
    check = (manifest.get("glossary_check") or {}).get("status")
    if check == "needs_review":
        return [{"action": "escalate", "reason": "The glossary cross-check has unresolved blocking issues. A person "
                 f"records decisions in runs/{rid}/resolutions.yaml; a model may only propose them.",
                 "then": f"{tool} resume --request {rid}"}]
    if check != "passed":
        return [{"action": "run", "command": f"{tool} resume --request {rid}", "reason": "Repeat the cross-check."}]
    if not harness:
        if (manifest.get("validation") or {}).get("status") == "completed":
            return [{"action": "deliver", "reason": "This request predates the harness workflow; its delivery is "
                     "kept for inspection and replay."}]
        return [{"action": "run", "command": f"{tool} resume --request {rid}",
                 "reason": "Replay this request's original extractive workflow."}]
    if (manifest.get("evidence") or {}).get("status") != "passed":
        return [{"action": "run", "command": f"{tool} resume --request {rid}",
                 "reason": "Rebuild the evidence packet."}]
    plan = (manifest.get("plan") or {}).get("status")
    if plan != "passed":
        if record.get("plan_stopped"):
            report = f" and runs/{rid}/{STAGE_REPORTS['plan']}" if (run_dir / STAGE_REPORTS["plan"]).is_file() else ""
            return [{"action": "escalate", "reason": f"The plan repair is not converging: {record['plan_stopped']}. "
                     f"Stop and report the unresolved issues{report} to the user; a person must decide. A plan a "
                     "person revises is imported with --human-revision."}]
        reason = ("Write the content plan with prompts/plan.md and schemas/plan.schema.json from "
                  f"the evidence packet, read in pages with `{tool} packet --request {rid}`." if plan is None else
                  f"Revise the plan from runs/{rid}/plan-report.md with prompts/repair.md: patch it into a new revision "
                  f"with `{tool} revise`, never retype it. Or report an infeasible plan to the user.")
        return [{"action": "author", "phase": "plan", "command": f"{tool} plan --request {rid} --file <plan.json>",
                 "reason": reason}]
    script = (manifest.get("script") or {}).get("status")
    if script != "passed":
        reason = ("Write the storyboard with prompts/draft.md and schemas/storyboard.schema.json from the "
                  f"accepted runs/{rid}/plan.json." if script is None else
                  f"Repair the blocking issues in runs/{rid}/script.md with prompts/repair.md: patch the storyboard "
                  f"into a new revision with `{tool} revise`, never retype it.")
        duration_flag = " --duration-rewrite" if record.get("pending_duration_check") else ""
        return [{"action": "author", "phase": "draft",
                 "command": f"{tool} script --request {rid} --storyboard <storyboard.json>{duration_flag}", "reason": reason}]
    review = manifest.get("content_review") or {}
    if review.get("status") != "passed":
        if review.get("status") == "needs_review":
            used = (record.get("repairs") or {}).get("storyboard", 0)
            if used >= MAX_REPAIR_ROUNDS:
                return [{"action": "escalate", "reason": f"The review still has material issues after {used} repair "
                         f"rounds (runs/{rid}/content-report.md). Report them to the user; a person must decide."}]
            return [{"action": "author", "phase": "repair",
                     "command": f"{tool} script --request {rid} --storyboard <revised.json>",
                     "reason": f"Repair the material findings in runs/{rid}/content-report.md with prompts/repair.md "
                               f"(round {used + 1} of {MAX_REPAIR_ROUNDS}), then review again."}]
        return [{"action": "author", "phase": "review",
                 "command": f"{tool} review --request {rid} --file <review.json>",
                 "reason": "Review the storyboard in a separate context with prompts/review.md, without the writer's "
                           f"self-assessment. The reviewer starts with `{tool} review-input --request {rid}`; run "
                           f"`{tool} preview --request {rid}` first so that it can look at the slides."}]
    duration = (manifest.get("narration") or {}).get("duration_check") or record.get("pending_duration_check") or {}
    if duration.get("status") == "needs_review":
        used = (record.get("repairs") or {}).get("duration", 0)
        if used < MAX_DURATION_REWRITES:
            return [{"action": "author", "phase": "repair",
                     "command": f"{tool} script --request {rid} --storyboard <revised.json> --duration-rewrite",
                     "reason": duration.get("message", "") + (" Expand using unused allowed source content, revising "
                               "the plan first if needed; report infeasibility if none remains." if
                               duration.get("direction") == "short" else " Shorten optional detail, keeping material "
                               "caveats.") + " Use one duration rewrite, review again, then build."}]
        return [{"action": "escalate", "reason": duration.get("message", "") + " The rewrite budget is used; the "
                 f"user may accept the length with {tool} build --request {rid} --accept-duration."}]
    validation = (manifest.get("validation") or {}).get("status")
    if validation in ("passed", "completed"):
        media = manifest.get("media_review") or {}
        if media.get("status") == "completed":
            return [{"action": "deliver", "reason": "Report the reviewed video and delivered files, with any minor "
                     "findings recorded in media-review.json."}]
        if media.get("status") == "needs_review":
            if media.get("unavailable_checks") or (record.get("repairs") or {}).get("storyboard", 0) >= MAX_REPAIR_ROUNDS:
                return [{"action": "escalate", "reason": f"Finished-video inspection has unavailable checks or the "
                         f"content repair budget is exhausted (runs/{rid}/media-review.json). Report the exact "
                         "findings and missing capability; do not deliver the rejected build."}]
            return [{"action": "author", "phase": "repair",
                     "command": f"{tool} script --request {rid} --storyboard <revised.json>",
                     "reason": f"Repair the finished-video findings in runs/{rid}/media-review.json. Content changes "
                               "use revise and the remaining storyboard repair budget, then independent review and "
                               "build. For a media-stage cause, fix that cause and repeat its dependent stages "
                               "instead of importing unchanged content. Inspect the resulting MP4 again."}]
        return [{"action": "author", "phase": "media_review",
                 "command": f"{tool} media-review --request {rid} --file <media-review.json>",
                 "reason": "Inspect every scene visually, listen to all narration, and check captions and complete "
                           "MP4 playback with prompts/media-review.md before final delivery. `status` lists the "
                           f"slides, timeline, and captions; `{tool} preview --request {rid}` makes contact "
                           "sheets of the rendered slides."}]
    if validation == "needs_review":
        return [{"action": "escalate", "reason": f"Media quality needs attention: runs/{rid}/quality-report.json."}]
    return [{"action": "run", "command": f"{tool} build --request {rid}",
             "reason": "Narrate, time, render, and validate the accepted storyboard."}]


def stage_result(run_dir: Path, stage: str, status: str, message: str, *, manifest: dict | None = None,
                 artifacts: list[dict] | None = None, issues: list[dict] | None = None) -> dict:
    manifest = manifest if manifest is not None else (
        json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        if (run_dir / "manifest.json").is_file() else {})
    record = manifest.get(stage) or {}
    return {
        "request_id": run_dir.name,
        "stage": stage,
        "status": status,
        "artifacts": artifacts if artifacts is not None else stage_artifacts(run_dir, stage),
        "issues": issues if issues is not None else _issues(run_dir, stage, record),
        "next_actions": next_actions(run_dir, manifest) if manifest else [],
        "message": message,
    }


def request_status(root: Path, run_dir: Path) -> dict:
    """The inspect-request result: every stage's status, artifacts, unresolved issues, and the legal next steps."""
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    harness = is_harness(run_dir)
    stages, issues, artifacts = [], [], []
    for stage in STAGES:
        record = manifest.get(stage)
        if not record:
            continue
        entry = {"stage": stage, "status": record.get("status")}
        for key in ("sha256", "digest", "error"):
            if record.get(key):
                entry[key] = record[key]
        stages.append(entry)
        artifacts += stage_artifacts(run_dir, stage)
        issues += [issue | {"stage": stage} for issue in _issues(run_dir, stage, record)]
    last = stages[-1] if stages else {"stage": "request", "status": "failed"}
    status = last["status"] if last["status"] in STATUSES else "passed"
    result = {
        "request_id": run_dir.name,
        "stage": "status",
        "status": status,
        "artifacts": artifacts,
        "issues": issues,
        "next_actions": next_actions(run_dir, manifest),
        "message": f"Request {run_dir.name}: last stage {last['stage']} is {last['status']}.",
        "workflow": WORKFLOW if harness else "extractive (made before the harness workflow)",
        "stages": stages,
    }
    if harness:
        record = load_record(run_dir)
        result["settings"] = request(run_dir).get("settings")
        result["repairs"] = {"plan_imports": 0, **(record.get("repairs") or {}), "max_storyboard": MAX_REPAIR_ROUNDS,
                             "max_duration": MAX_DURATION_REWRITES, "max_plan_imports": MAX_PLAN_IMPORTS}
        result["instructions"] = {key: (record.get("instructions") or {}).get(key) for key in ("version", "sha256")}
        # The digests a review must name; they exclude request IDs and timestamps.
        result["digests"] = {key: (manifest.get(stage) or {}).get("digest")
                             for key, stage in (("evidence_digest", "evidence"), ("plan_digest", "plan"),
                                                ("storyboard_digest", "script"))}
        if (manifest.get("script") or {}).get("status") == "passed" and (run_dir / "storyboard.json").is_file():
            from .review import targets

            # Every target the separate review must judge, exactly once.
            storyboard = json.loads((run_dir / "storyboard.json").read_text(encoding="utf-8"))
            result["review_targets"] = list(targets(storyboard))
        if (manifest.get("validation") or {}).get("status") in ("passed", "completed"):
            from .preview import rendered_sheets

            result["media_review_input"] = {"video_sha256": (manifest.get("render") or {}).get("draft_sha256"),
                "storyboard_digest": (manifest.get("script") or {}).get("digest"),
                "video_path": str(run_dir / "render/draft.mp4"),
                "scene_ids": [s["id"] for s in json.loads((run_dir / "storyboard.json").read_text())["scenes"]],
                # render.json maps each scene to its slide; timeline.json gives each scene's and caption's times.
                "slides_directory": str(run_dir / "render/slides"),
                "render_record": str(run_dir / "render.json"), "timeline": str(run_dir / "timeline.json"),
                "captions": [str(run_dir / "captions.srt"), str(run_dir / "captions.vtt")],
                "transcript": str(run_dir / "script.md"),
                "quality_report": str(run_dir / "quality-report.json"),
                # Made by `preview` from the rendered slides; None until it has run for this video.
                "contact_sheets": rendered_sheets(run_dir, manifest)}
    return result


def write_result(root: Path, run_dir: Path, result: dict) -> None:
    """Keep the last structured result on disk, so a new harness session can continue without chat history."""
    if (run_dir / "manifest.json").is_file():
        write_atomic(root, run_dir.relative_to(root) / LAST_RESULT, _json(result), label="Request")
