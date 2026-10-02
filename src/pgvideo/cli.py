"""The pgvideo command-line interface.

Every new video request is orchestrated by an LLM harness that follows the root
AGENTS.md. pgvideo supplies the bounded stages it calls: `prepare` snapshots and
checks the sources and writes the evidence packet; `plan`, `script`, and
`review` import and validate the content the harness writes; `build` narrates,
times, renders, and validates the accepted storyboard; `status` reports where a
request stands and what may happen next. With --json, each of these prints one
structured result (schemas/stage-result.schema.json) and keeps it in
runs/<request-id>/last-result.json.

Requests made before the harness workflow keep their original extractive
provenance; `resume`, `script`, and the media commands replay them as before.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .paths import REQUEST_ID, project_directory, project_root
from .assets import AssetError, local_selection
from .sources import DEFAULT_REF, FALLBACK_REF, REPOSITORY, SourceError, resolve_document

# Exit status for a request that needs a documented resolution before it can continue.
NEEDS_REVIEW = 3
# Narration and encoding settings that build, resume, and script use; a reuse lookup plans with them.
LUFS, TRUE_PEAK, CRF, AUDIO_BITRATE = -16.0, -1.5, 20, 128
NO_REUSE = ("build the narration and MP4 even when a validated video with the same inputs exists; "
            "it is registered for reuse afterwards")
JSON_HELP = "print one structured stage result as JSON on standard output; progress goes to standard error"
EXIT = {"passed": 0, "completed": 0, "needs_review": NEEDS_REVIEW, "failed": 1}
LINES = re.compile(r"(\d+)-(\d+)")


def even_dimension(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive even integer") from error
    if number <= 0 or number % 2:
        raise argparse.ArgumentTypeError("must be a positive even integer")
    return number


def positive_speed(value: str) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive finite number") from error
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a positive finite number")
    return number


def target_minutes(value: str) -> float:
    number = positive_speed(value)
    if number > 180:
        raise argparse.ArgumentTypeError("must be at most 180 minutes")
    return number


def parser() -> argparse.ArgumentParser:
    # Imported here because it needs .venv packages; main() rejects other interpreters before parsing.
    from .document import DEFAULT_DETAIL, DETAILS
    from .orchestration import DEFAULT_AUDIENCE, DEFAULT_TARGET_MINUTES

    command = argparse.ArgumentParser(prog="pgvideo")
    subcommands = command.add_subparsers(dest="command", required=True)

    def request_command(name: str, help_text: str, *, json_output: bool = True) -> argparse.ArgumentParser:
        sub = subcommands.add_parser(name, help=help_text)
        sub.add_argument("--request", required=True, help="request ID, the directory name under runs/")
        if json_output:
            sub.add_argument("--json", action="store_true", help=JSON_HELP)
        return sub

    prepare = subcommands.add_parser(
        "prepare", help="create a harness request for one document: snapshot, parse, match and cross-check the "
                        "glossary, and write the evidence packet; stops before any content is written")
    prepare.add_argument("--document", required=True, help="wiki-relative .md path or GitHub blob URL")
    prepare.add_argument(
        "--ref", help=f"branch, tag, or commit (defaults to {DEFAULT_REF}; tries {FALLBACK_REF} if missing)"
    )
    prepare.add_argument("--voice", default="af_heart", help="Kokoro voice (default: af_heart)")
    prepare.add_argument("--language", default="a", help="Kokoro language code (default: a, American English)")
    prepare.add_argument("--speed", type=positive_speed, default=1.0, help="speaking speed (default: 1.0)")
    prepare.add_argument(
        "--detail", choices=DETAILS, default=DEFAULT_DETAIL,
        help="summary (the main answer and its qualifications), standard (the mechanism and useful examples), or "
             f"full (every eligible section, no duration ceiling) (default: {DEFAULT_DETAIL})")
    prepare.add_argument("--audience", help=f"who the video is for (default: {DEFAULT_AUDIENCE})")
    prepare.add_argument("--target-minutes", type=target_minutes,
                         help="duration target, kept within ±15%% (defaults: "
                              + ", ".join(f"{k} {v:g}" for k, v in DEFAULT_TARGET_MINUTES.items() if v)
                              + "; none for full)")
    prepare.add_argument("--width", type=even_dimension, default=1920, help="video width (default: 1920)")
    prepare.add_argument("--height", type=even_dimension, default=1080, help="video height (default: 1080)")
    prepare.add_argument(
        "--output", type=Path, default=Path("output"),
        help="video output directory inside the project (relative to the project root)")
    prepare.add_argument("--json", action="store_true", help=JSON_HELP)

    request_command("status", "report a request's stages, artifacts, unresolved issues, and legal next steps")
    plan = request_command("plan", "import and check the content plan the harness wrote from the evidence packet")
    plan.add_argument("--file", type=Path, required=True, help="plan file (JSON or YAML) inside the project")

    script = request_command(
        "script", "import and check the storyboard the harness wrote from the accepted plan (for an older request: "
                  "redraft its extractive storyboard, or validate an edited scene file or a drafter's output)")
    source = script.add_mutually_exclusive_group()
    source.add_argument("--storyboard", type=Path, help="scene file (JSON or YAML) inside the project")
    source.add_argument("--drafter-command", type=Path,
                        help="executable inside the project that reads draft-input.json on stdin and writes scenes "
                             "on stdout (an optional adapter)")
    script.add_argument("--duration-rewrite", action="store_true",
                        help="this storyboard shortens optional detail after the measured narration missed the target")
    script.add_argument("--human-revision", action="store_true",
                        help="a person revised this storyboard after the automatic repair budget was used")
    script.add_argument("--no-reuse", action="store_true", help=NO_REUSE + " (older requests only)")

    review = request_command("review", "import the separate semantic review of the storyboard and decide the "
                                       "content gate")
    review.add_argument("--file", type=Path, required=True, help="review file (JSON or YAML) inside the project")

    build = request_command("build", "narrate, time, render, and validate an accepted storyboard, reusing "
                                     "matching narration and media")
    build.add_argument("--no-reuse", action="store_true", help=NO_REUSE)
    build.add_argument("--accept-duration", action="store_true",
                       help="the user accepts a measured length outside the target after the rewrite budget is used")

    resume = request_command(
        "resume", "repeat the glossary cross-check with the request's resolutions; for a harness request, rebuild "
                  "the evidence packet and revalidate its saved plan, storyboard, and review")
    resume.add_argument("--no-reuse", action="store_true", help=NO_REUSE + " (older requests only)")
    replay = request_command("replay", "revalidate another request's accepted plan, storyboard, and review for this "
                                       "request without new inference, when the evidence and policy match")
    replay.add_argument("--from", dest="source", required=True, help="request ID whose accepted content to replay")
    excerpt = request_command("excerpt", "print lines of a PostgreSQL file from the request's snapshot, with its "
                                         "evidence ID")
    excerpt.add_argument("--path", required=True, help="file path in the PostgreSQL snapshot, such as "
                                                       "src/backend/utils/misc/guc_tables.c")
    excerpt.add_argument("--lines", required=True, help="line range such as 120-160")
    request_command("baseline", "draft the extractive regression baseline for comparison; never narrated")
    note = request_command("note", "record a visual or listening check of the rendered video that was actually "
                                   "performed")
    note.add_argument("--kind", choices=("visual", "listening"), required=True)
    note.add_argument("--text", required=True, help="what was inspected and what was found")

    narrate = request_command("narrate", "generate or refresh Kokoro narration for an accepted storyboard",
                              json_output=False)
    narrate.add_argument("--lufs", type=float, default=LUFS, help="integrated loudness target (default: -16)")
    narrate.add_argument("--true-peak", type=float, default=TRUE_PEAK, help="maximum true peak in dBTP (default: -1.5)")
    narrate.add_argument("--refresh-unit", action="append", default=[],
                         help="resynthesize one unit or sentence ID, even if it is cached; repeat as needed")
    request_command("timing", "rebuild scene timing and captions from passed narration", json_output=False)
    render = request_command("render", "render, validate, and deliver the MP4 from passed timing", json_output=False)
    render.add_argument("--crf", type=int, default=CRF, help="H.264 constant rate factor (default: 20)")
    render.add_argument("--audio-bitrate", type=int, default=AUDIO_BITRATE, help="AAC bitrate in kb/s (default: 128)")
    request_command("validate", "validate and deliver an existing rendered request", json_output=False)
    return command


def create_request(args: argparse.Namespace, *, workspace: Path | None = None) -> Path:
    """Validate a new harness request and write request.json, manifest.json, and orchestration.json."""
    from .orchestration import DEFAULT_AUDIENCE, DEFAULT_TARGET_MINUTES, WORKFLOW, instructions, start_record

    if not args.voice.strip() or not args.language.strip():
        raise ValueError("Voice and language must be nonempty.")
    audience = (args.audience or DEFAULT_AUDIENCE).strip()
    if not audience or len(audience) > 200:
        raise ValueError("The audience must be 1 to 200 characters.")
    if args.detail == "full" and args.target_minutes is not None:
        raise ValueError("Full detail covers every eligible section and has no duration target.")
    target = args.target_minutes if args.target_minutes is not None else DEFAULT_TARGET_MINUTES[args.detail]
    root = project_root()
    base = project_directory(root, workspace if workspace is not None else root, label="Workspace")
    runbook = instructions(base)
    project_directory(base, args.output, label="Output")
    project_directory(base, Path("runs"), label="Request")
    document = resolve_document(args.document, args.ref)

    now = datetime.now(timezone.utc)
    request_id = f"{now:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:12]}"
    # Recheck after the network operation, before recording paths or writing.
    output_dir = project_directory(base, args.output, label="Output")
    run_dir = project_directory(base, Path("runs") / request_id, label="Request")
    request = {
        "request_id": request_id,
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "status": "validated",
        "repository": REPOSITORY,
        "document": {"path": document.path, "ref": document.ref, "url": document.url},
        "workflow": {"kind": WORKFLOW, "instructions": runbook},
        "settings": {
            "voice": args.voice.strip(),
            "language": args.language.strip(),
            "speed": args.speed,
            "detail": args.detail,
            "audience": audience,
            "target_minutes": target,
            "width": args.width,
            "height": args.height,
            "output_dir": str(output_dir),
        },
    }
    run_dir.mkdir(parents=True, exist_ok=False)
    destination = run_dir / "request.json"
    temporary = run_dir / ".request.json.tmp"
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(request, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(destination)
        manifest = {"request_id": request_id, "workflow": WORKFLOW}
        report_path = root / ".runtime" / "environment-report.json"
        if report_path.is_file():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if report.get("status") != "passed" or report.get("project_root") != str(root):
                raise ValueError("The local environment report is stale or failed; run scripts/pgvideo doctor.")
            manifest["environment"] = {
                "python": report["python"],
                "platform": report["platform"],
                "checks": report["checks"],
                "artifacts": report.get("artifacts", {}),
                "isolation": report.get("isolation", {}),
                "os_requirements": report["os_requirements"],
                "isolation_limitations": report["isolation_limitations"],
                "tools_lock_sha256": hashlib.sha256((root / "tools.lock").read_bytes()).hexdigest(),
                "requirements_lock_sha256": hashlib.sha256((root / "requirements.lock").read_bytes()).hexdigest(),
            }
        (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        start_record(base, run_dir, request)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


# Structured results --------------------------------------------------------------------------------


def _emit(root: Path, args: argparse.Namespace, result: dict, stdout) -> int:
    """Keep the result on disk, print it, and return its exit status."""
    from .orchestration import write_result

    run_dir = root / "runs" / result["request_id"] if result.get("request_id") else None
    if run_dir is not None and (run_dir / "manifest.json").is_file():
        write_result(root, run_dir, result)
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, ensure_ascii=False), file=stdout)
    else:
        # Errors and review stops go to standard error, like every other pgvideo failure.
        problems = sys.stderr if result["status"] in ("failed", "needs_review") else stdout
        print(result["message"], file=problems)
        for issue in result["issues"]:
            if issue.get("severity") == "blocking":
                where = " · ".join(filter(None, [issue.get("scene"), issue.get("narration"), issue.get("target"),
                                                 issue.get("claim"), issue.get("section")]))
                print(f"  blocking {issue['code']}" + (f" ({where})" if where else "") + f": {issue['message']}",
                      file=problems)
        for action in result["next_actions"]:
            print(f"Next ({action['action']}): " + (f"{action['command']} — " if action.get("command") else "")
                  + action["reason"], file=stdout)
    return EXIT[result["status"]]


def _harness_command(root: Path, args: argparse.Namespace, stage: str, work) -> int:
    """Run one harness-facing stage and report it as a structured result.

    In JSON mode, progress lines go to standard error so standard output holds
    only the result. An error becomes a `failed` result with the message.
    """
    from .orchestration import check_instructions, is_harness, stage_result

    stdout = sys.stdout
    with contextlib.redirect_stdout(sys.stderr if getattr(args, "json", False) else sys.stdout):
        try:
            run_dir, _manifest = _request(root, args.request)
        except (ValueError, OSError) as error:
            result = {"request_id": None, "stage": stage, "status": "failed", "artifacts": [],
                      "issues": [{"severity": "blocking", "code": "request", "message": str(error)}],
                      "next_actions": [], "message": f"pgvideo: {error}"}
            return _emit(root, args, result, stdout)
        notes = []
        try:
            if is_harness(run_dir):
                notes = check_instructions(root, run_dir)
            status, message, *extra = work(run_dir)
        except (ValueError, OSError, KeyError, TypeError) as error:
            status, message, extra = "failed", f"pgvideo: {error}", []
        result = stage_result(run_dir, stage, status, " ".join([*notes, message]))
        for fields in extra:
            result.update(fields)
        if status == "failed" and not any(i["severity"] == "blocking" for i in result["issues"]):
            result["issues"].insert(0, {"severity": "blocking", "code": "stage_failed", "message": message})
    return _emit(root, args, result, stdout)


# Prepare -----------------------------------------------------------------------------------------


def prepare(args: argparse.Namespace, root: Path) -> int:
    """Create a harness request and run every evidence stage; stop before any content is written."""
    from .orchestration import stage_result

    stdout = sys.stdout
    with contextlib.redirect_stdout(sys.stderr if args.json else sys.stdout):
        try:
            local_selection(language=args.language, voice=args.voice)
            request_path = create_request(args, workspace=root)
        except (AssetError, SourceError, ValueError, OSError) as error:
            result = {"request_id": None, "stage": "request", "status": "failed", "artifacts": [],
                      "issues": [{"severity": "blocking", "code": "request", "message": str(error)}],
                      "next_actions": [], "message": f"pgvideo: {error}"}
            return _emit(root, args, result, stdout)
        print(f"Validated request: {request_path}")
        run_dir = request_path.parent
        stage, status, message = _prepare_stages(root, run_dir)
        result = stage_result(run_dir, stage, status, message)
        if status == "passed":
            from .reuse import find_content

            if found := find_content(root, run_dir):
                result["replay_available"] = found
                result["next_actions"].insert(0, {
                    "action": "run", "command": f"scripts/pgvideo replay --request {run_dir.name} --from {found[0]}",
                    "reason": f"Request {found[0]} has accepted content made from the same evidence, prompts, and "
                              "review policy; replaying it needs no new inference. Skip this to write new content."})
    return _emit(root, args, result, stdout)


def _prepare_stages(root: Path, run_dir: Path) -> tuple[str, str, str]:
    from .crosscheck import check_glossary
    from .document import parse_document
    from .evidence import build_evidence
    from .glossary import match_glossary
    from .snapshot import snapshot_sources

    request = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
    try:
        sources = snapshot_sources(root, run_dir, request)
    except (SourceError, ValueError, OSError) as error:
        return "sources", "failed", f"pgvideo: {error}"
    wiki, postgres = sources["wiki"], sources["postgres"]
    print(f"Wiki commit: {wiki['commit']} (ref {wiki['requested_ref']})")
    if postgres.get("commit"):
        print(f"PostgreSQL {postgres['version']} source commit: {postgres['commit']}")
    print(f"Source report: {run_dir / sources['report']}")
    if sources["status"] == "needs_review":
        return "sources", "needs_review", (f"Needs review: {sources['issues']['blocking']} blocking issue(s) in "
                                           f"{run_dir / sources['report']}.")
    try:
        document = parse_document(root, run_dir)
    except (ValueError, OSError) as error:
        return "document", "failed", f"pgvideo: {error}"
    coverage = document["coverage"]
    print(f"Document structure: {run_dir / document['record']}")
    print(f"Coverage map: {run_dir / coverage['file']} ({coverage['decisions']['explain']} sections eligible for the "
          f"harness plan, about {coverage['full_minutes']} minutes of narration in full)")
    if document["status"] == "needs_review":
        return "document", "needs_review", (f"Needs review: {document['issues']['blocking']} blocking issue(s) in "
                                            f"{run_dir / coverage['file']}.")
    try:
        glossary = match_glossary(root, run_dir)
    except (ValueError, OSError) as error:
        return "glossary", "failed", f"pgvideo: {error}"
    counts, index = glossary["counts"], glossary["index"]
    print(f"Glossary index: {run_dir / index['path']} ({index['entries']} entries, built from the glossary "
          "downloaded for this request)")
    print(f"Glossary matches: {run_dir / glossary['record']} ({counts['matched']} entries: {counts['central']} "
          f"central, {counts['supporting']} supporting, {counts['peripheral']} peripheral; "
          f"{counts['ambiguous']} ambiguous, {counts['unmatched']} unmatched terms)")
    try:
        check = check_glossary(root, run_dir)
    except (ValueError, OSError) as error:
        return "glossary_check", "failed", f"pgvideo: {error}"
    if _report_check(run_dir, check) != 0:
        return "glossary_check", "needs_review", (f"Needs review: {check['issues']['blocking']} blocking issue(s) in "
                                                  f"{run_dir / check['report']}.")
    try:
        evidence = build_evidence(root, run_dir)
    except (ValueError, OSError, KeyError) as error:
        return "evidence", "failed", f"pgvideo: {error}"
    counts = evidence["counts"]
    return "evidence", "passed", (
        f"Evidence packet: {run_dir / evidence['record']} ({counts['eligible_sections']} eligible sections, "
        f"{counts['units']} sentences and rows, {counts['excerpts']} source excerpts, {counts['missing']} missing "
        f"citations, {counts['settings']} configuration facts; digest {evidence['digest'][:12]}). Speech rate: "
        f"{evidence['speech']['words_per_minute']} words per minute ({evidence['speech']['basis']}).")


# Harness stages ----------------------------------------------------------------------------------


def status(args: argparse.Namespace, root: Path) -> int:
    from .orchestration import request_status

    try:
        run_dir, _manifest = _request(root, args.request)
        result = request_status(root, run_dir)
    except (ValueError, OSError, KeyError) as error:
        result = {"request_id": None, "stage": "status", "status": "failed", "artifacts": [],
                  "issues": [{"severity": "blocking", "code": "request", "message": str(error)}],
                  "next_actions": [], "message": f"pgvideo: {error}"}
        return _emit(root, args, result, sys.stdout)
    if not args.json:
        for stage in result["stages"]:
            print(f"{stage['stage']}: {stage['status']}")
    # Reporting status never changes the request, so it is not kept as the last result.
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(result["message"])
        for action in result["next_actions"]:
            print(f"Next ({action['action']}): " + (f"{action['command']} — " if action.get("command") else "")
                  + action["reason"])
    return EXIT.get(result["status"], 0)


def _require_harness(run_dir: Path, command: str) -> None:
    from .orchestration import is_harness

    if not is_harness(run_dir):
        raise ValueError(f"Request {run_dir.name} predates the harness workflow; `{command}` is for requests made "
                         "with `prepare`.")


def plan(args: argparse.Namespace, root: Path) -> int:
    from .planning import import_plan

    def work(run_dir: Path) -> tuple[str, str]:
        _require_harness(run_dir, "plan")
        record = import_plan(root, run_dir, args.file)
        estimate = record["estimate"]
        return record["status"], (f"Plan {record['status']}: {record['counts']['claims']} claims in "
                                  f"{record['counts']['outline']} outline items, {record['counts']['omissions']} "
                                  f"omissions, {estimate['budget_seconds']} seconds budgeted "
                                  f"({record['issues']['blocking']} blocking, {record['issues']['warning']} "
                                  f"warnings). Report: {run_dir / record['report']}.")

    return _harness_command(root, args, "plan", work)


def review(args: argparse.Namespace, root: Path) -> int:
    from .review import import_review

    def work(run_dir: Path) -> tuple[str, str]:
        _require_harness(run_dir, "review")
        record = import_review(root, run_dir, args.file)
        verdicts = record["counts"]["verdicts"]
        return record["status"], (f"Content gate {record['status']}: {record['counts']['targets']} targets, "
                                  f"{verdicts['supported']} supported, {verdicts['contradicted']} contradicted, "
                                  f"{verdicts['insufficient_evidence']} with insufficient evidence; "
                                  f"{record['counts']['material']} material and {record['counts']['minor']} minor "
                                  f"finding(s). Report: {run_dir / record['report']}.")

    return _harness_command(root, args, "content_review", work)


def _import_storyboard(root: Path, run_dir: Path, **options) -> tuple[str, str]:
    from .script import create_script

    record = create_script(root, run_dir, **options)
    counts, estimate = record["counts"], record["estimate"]
    return record["status"], (f"Storyboard {record['status']}: {counts['scenes']} scenes, {counts['sentences']} "
                              f"narrated sentences, about {estimate['minutes']} minutes "
                              f"({record['issues']['blocking']} blocking, {record['issues']['warning']} warnings). "
                              f"Script: {run_dir / record['script']}.")


def build(args: argparse.Namespace, root: Path) -> int:
    def work(run_dir: Path) -> tuple[str, str]:
        from .orchestration import require_content_gate

        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        if (manifest.get("script") or {}).get("status") != "passed":
            raise ValueError(f"The storyboard has status '{(manifest.get('script') or {}).get('status')}'.")
        require_content_gate(run_dir, manifest)
        code = _build(root, run_dir, reuse=not args.no_reuse, accept_duration=args.accept_duration)
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        validation = manifest.get("validation") or {}
        if code == 0:
            output = root / validation["output"]
            quality = json.loads((run_dir / "quality-report.json").read_text(encoding="utf-8"))
            delivery = {"directory": str(output), "video": str(output / validation["video"]),
                        "files": [{"path": str(output / name), "sha256": digest}
                                  for name, digest in quality["delivery"]["files"].items()]}
            return "completed", (f"Delivered {output / validation['video']} ({validation['duration_seconds']:.1f} "
                                 "seconds) with its transcript, captions, references, glossary and content reports, "
                                 "and quality report. No listening review has been recorded; record one you "
                                 "actually made with `note`."), {"delivery": delivery}
        if code == NEEDS_REVIEW:
            return "needs_review", "Build stopped for review; see the issues and next actions."
        return "failed", "Build failed; the error is above."

    return _harness_command(root, args, "validation", work)


def replay(args: argparse.Namespace, root: Path) -> int:
    def work(run_dir: Path) -> tuple[str, str]:
        from .orchestration import record_event

        _require_harness(run_dir, "replay")
        if not REQUEST_ID.fullmatch(args.source) or args.source == run_dir.name:
            raise ValueError(f"--from must name another request under runs/, not '{args.source}'.")
        source = project_directory(root, Path("runs") / args.source, label="Request")
        if not (source / "manifest.json").is_file():
            raise ValueError(f"No request '{args.source}' in {root / 'runs'}.")
        # Recorded first: the replayed files name their original request, which this request now accepts.
        record_event(root, run_dir, stage="replay", status="started", replayed_from=args.source, inference="none")
        return _revalidate(root, run_dir, source, replayed_from=args.source)

    return _harness_command(root, args, "content_review", work)


def _revalidate(root: Path, run_dir: Path, source: Path, *, replayed_from: str | None = None) -> tuple[str, str]:
    """Import saved plan, storyboard, and review files in order through the ordinary validators.

    No inference happens: the files are the exact bytes a harness wrote and
    pgvideo accepted before. Each import stops the sequence unless it passes.
    """
    from .orchestration import AUTHORED, record_event
    from .planning import import_plan
    from .review import import_review
    from .script import create_script
    from .sources import write_atomic

    authored = project_directory(root, (source / AUTHORED).relative_to(root), label="Request")
    steps = [("plan", "plan.json"), ("script", "storyboard.json"), ("content_review", "review.json")]
    done = []
    for stage, name in steps:
        path = authored / name
        if path.is_symlink() or not path.is_file():
            if replayed_from:
                raise ValueError(f"Request {source.name} has no accepted {AUTHORED}/{name} to replay.")
            break
        if replayed_from:
            # Import a copy kept in this request, so its record names a file this request owns.
            path = write_atomic(root, run_dir.relative_to(root) / "replay" / name, path.read_bytes(), label="Request")
        if stage == "plan":
            record = import_plan(root, run_dir, path)
        elif stage == "script":
            record = create_script(root, run_dir, storyboard=path)
        else:
            record = import_review(root, run_dir, path)
        done.append(f"{stage} {record['status']}")
        if record["status"] != "passed":
            break
    if replayed_from:
        record_event(root, run_dir, stage="replay", status="passed" if len(done) == len(steps) and
                     done[-1].endswith("passed") else "needs_review", replayed_from=replayed_from, inference="none")
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    last = next((manifest[stage] for stage in ("content_review", "script", "plan") if manifest.get(stage)), None)
    status = (last or {}).get("status") or "passed"
    what = f"from request {replayed_from} " if replayed_from else ""
    return (status if status in EXIT else "failed",
            f"Revalidated saved content {what}without inference: " + (", ".join(done) or "nothing saved yet") + ".")


def excerpt(args: argparse.Namespace, root: Path) -> int:
    """Print snapshot lines and their evidence ID; a file outside the snapshot is reported as missing evidence."""
    from .evidence import Resolver

    try:
        run_dir, _ = _request(root, args.request)
        match = LINES.fullmatch(args.lines.strip())
        if not match:
            raise ValueError("--lines must be a range such as 120-160.")
        found = Resolver(root, run_dir).excerpt(args.path, int(match.group(1)), int(match.group(2)))
    except (ValueError, OSError, KeyError) as error:
        if args.json:
            print(json.dumps({"request_id": args.request, "stage": "excerpt", "status": "failed", "artifacts": [],
                              "issues": [{"severity": "blocking", "code": "missing_evidence", "message": str(error)}],
                              "next_actions": [], "message": f"pgvideo: {error}"}, indent=2, ensure_ascii=False))
        else:
            print(f"pgvideo: {error}", file=sys.stderr)
        return 1
    message = f"Evidence ID {found['id']} (SHA-256 {found['sha256'][:12]}, pin {found['commit'][:12]})."
    if args.json:
        # Reading evidence changes nothing, so the result is not kept as the request's last result.
        print(json.dumps({"request_id": run_dir.name, "stage": "excerpt", "status": "passed", "artifacts": [],
                          "issues": [], "next_actions": [], "message": message, "excerpt": found},
                         indent=2, ensure_ascii=False))
    else:
        print(found["text"])
        print(message, file=sys.stderr)
    return 0


def baseline(args: argparse.Namespace, root: Path) -> int:
    from .script import create_baseline

    def work(run_dir: Path) -> tuple[str, str]:
        record = create_baseline(root, run_dir)
        return "passed", (f"Extractive baseline for comparison: {run_dir / record['script']} "
                          f"({record['counts']['scenes']} scenes, about {record['estimate']['minutes']} minutes, "
                          f"baseline status {record['status']}). It is never narrated or delivered.")

    return _harness_command(root, args, "baseline", work)


def note(args: argparse.Namespace, root: Path) -> int:
    from .orchestration import ORCHESTRATION, load_record, save_record

    def work(run_dir: Path) -> tuple[str, str]:
        _require_harness(run_dir, "note")
        text = " ".join(args.text.split())
        if not text or len(text) > 2000:
            raise ValueError("--text must be 1 to 2000 characters.")
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        if (manifest.get("validation") or {}).get("status") != "completed":
            raise ValueError("Record a media check after `build` delivered the video.")
        record = load_record(run_dir)
        record.setdefault("media_reviews", []).append({
            "at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "kind": args.kind, "text": text,
            "video_sha256": manifest["render"]["draft_sha256"]})
        save_record(root, run_dir, record)
        delivery = root / manifest["validation"]["output"]
        if (delivery / ORCHESTRATION).is_file():
            (delivery / ORCHESTRATION).write_bytes((run_dir / ORCHESTRATION).read_bytes())
        return "passed", f"Recorded the {args.kind} check in {run_dir / ORCHESTRATION}."

    return _harness_command(root, args, "note", work)


# Media stages ------------------------------------------------------------------------------------


def _script(root: Path, run_dir: Path, *, storyboard: Path | None = None, command: Path | None = None,
            reuse: bool = True) -> int:
    """Draft or import an older request's script, then reuse or build its video when validation passes."""
    from .script import DRAFT_INPUT, create_script

    try:
        script = create_script(root, run_dir, storyboard=storyboard, command=command)
    except (ValueError, OSError) as error:
        print(f"pgvideo: {error}", file=sys.stderr)
        return 1
    counts, estimate, drafter = script["counts"], script["estimate"], script["drafter"]
    checks = counts["checks"]
    print(f"Draft input: {run_dir / DRAFT_INPUT}")
    print(f"Storyboard: {run_dir / script['record']} ({counts['scenes']} scenes, {counts['sentences']} narrated "
          f"sentences, about {estimate['minutes']} minutes; drafted by {drafter['kind']} {drafter['name']})")
    print(f"Narration checks: {checks['unchanged']} unchanged from the document, {checks['rechecked']} rechecked, "
          f"{checks['glossary']} glossary definitions, {checks['framing']} framing, {checks['failed']} failed")
    print(f"Script: {run_dir / script['script']}")
    if script["status"] == "needs_review":
        print(f"pgvideo: needs review: {script['issues']['blocking']} blocking issue(s) in {script['script']}. "
              f"Edit a copy of {script['record']}, then run: scripts/pgvideo script --request {run_dir.name} "
              "--storyboard <file>", file=sys.stderr)
        return NEEDS_REVIEW
    return _build(root, run_dir, reuse=reuse)


def _build(root: Path, run_dir: Path, *, reuse: bool, accept_duration: bool = False) -> int:
    """Reuse a validated video with the same inputs, or narrate, time, render, and validate the script."""
    from .reuse import find_video

    try:
        video, record = find_video(root, run_dir, enabled=reuse, loudness=LUFS, peak=TRUE_PEAK, crf=CRF,
                                   audio_bitrate=AUDIO_BITRATE)
    except (ValueError, OSError) as error:
        print(f"pgvideo: {error}", file=sys.stderr)
        return 1
    lookup = record["lookup"]
    key = f" (key {record['key'][:12]})" if record.get("key") else ""
    for rejected in lookup.get("rejected", []):
        print(f"Reuse: skipped the video of request {rejected['request_id']}: {rejected['reason']}")
    if video is None:
        reason = {"disabled": "--no-reuse was given", "not_found": "no validated video has the same inputs",
                  "unavailable": f"the lookup failed: {lookup.get('reason')}"}[lookup["status"]]
        print(f"Reuse: building the narration and MP4{key}; {reason}.")
        return _narrate(root, run_dir, accept_duration=accept_duration)
    print(f"Reuse: request {video.request_id} has a validated video with the same inputs{key}.")
    return _reuse_narration(root, run_dir, video, accept_duration=accept_duration)


def _reuse_narration(root: Path, run_dir: Path, video, *, accept_duration: bool = False) -> int:
    from .reuse import reuse_narration

    try:
        result = reuse_narration(root, run_dir, video)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"pgvideo: cannot reuse the narration of request {video.request_id} ({error}); synthesizing it.",
              file=sys.stderr)
        return _narrate(root, run_dir, accept_duration=accept_duration)
    _print_narration(run_dir, result)
    if not _duration_ok(root, run_dir, accept_duration):
        return NEEDS_REVIEW
    return _timing(root, run_dir, video=video)


def _duration_ok(root: Path, run_dir: Path, accept: bool) -> bool:
    """Stop a harness request whose measured narration missed its target, unless the user accepted the length."""
    from .orchestration import load_record, record_event, save_record
    from .sources import write_atomic

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    check = (manifest.get("narration") or {}).get("duration_check")
    if not check:
        return True
    print(f"Duration: {check['message']}")
    if check["status"] != "needs_review":
        return True
    if not accept:
        print(f"pgvideo: needs review: {check['message']} Run scripts/pgvideo status --request {run_dir.name} for "
              "the next step.", file=sys.stderr)
        return False
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    check.update(status="accepted", accepted_at=now)
    write_atomic(root, run_dir.relative_to(root) / "manifest.json",
                 (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"), label="Request")
    record = load_record(run_dir)
    record["accepted_duration"] = {"at": now, "measured_seconds": check["measured_seconds"],
                                   "storyboard_digest": manifest["script"].get("digest")}
    save_record(root, run_dir, record)
    record_event(root, run_dir, stage="narration", status="duration_accepted", measured=check["measured_seconds"])
    return True


def _print_narration(run_dir: Path, result: dict) -> None:
    source = f", reused from request {result['reused_from']}" if result.get("reused_from") else ""
    print(f"Narration master: {run_dir / result['master']} ({result['duration_seconds']} seconds{source})")
    print(f"Audio map: {run_dir / result['record']} ({result['units']} units)")
    print(f"Narration report: {run_dir / result['report']}")


def _narrate(root: Path, run_dir: Path, *, lufs: float = LUFS, true_peak: float = TRUE_PEAK,
             refresh: set[str] | None = None, accept_duration: bool = False) -> int:
    from .narration import create_narration

    if not math.isfinite(lufs) or not -70 <= lufs <= -5 or not math.isfinite(true_peak) or not -9 <= true_peak <= 0:
        print("pgvideo: loudness must be -70 to -5 LUFS and true peak -9 to 0 dBTP.", file=sys.stderr)
        return 1
    try:
        result = create_narration(root, run_dir, loudness=lufs, peak=true_peak, refresh=refresh)
    except (ValueError, OSError) as error:
        print(f"pgvideo: narration failed: {error}", file=sys.stderr)
        return 1
    _print_narration(run_dir, result)
    if not _duration_ok(root, run_dir, accept_duration):
        return NEEDS_REVIEW
    return _timing(root, run_dir)


def _timing(root: Path, run_dir: Path, *, video=None) -> int:
    """Time the narration, then render the MP4 or reuse the one registered for `video`."""
    from .timing import create_timing

    try:
        result = create_timing(root, run_dir)
    except (ValueError, OSError, KeyError, TypeError) as error:
        if video is not None:
            print(f"pgvideo: the narration reused from request {video.request_id} does not fit this script "
                  f"({error}); synthesizing it.", file=sys.stderr)
            return _narrate(root, run_dir)
        print(f"pgvideo: timing failed: {error}", file=sys.stderr)
        return 1
    print(f"Timeline: {run_dir / result['record']} ({result['frames']} frames, "
          f"{result['duration_seconds']:.3f} seconds)")
    print(f"Captions: {run_dir / result['srt']} and {run_dir / result['vtt']} "
          f"({result['captions']} cues)")
    if video is not None:
        return _reuse_render(root, run_dir, video)
    return _render(root, run_dir)


def _reuse_render(root: Path, run_dir: Path, video) -> int:
    from .reuse import reuse_render

    try:
        result = reuse_render(root, run_dir, video)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"pgvideo: cannot reuse the MP4 of request {video.request_id} ({error}); rendering it.",
              file=sys.stderr)
        return _render(root, run_dir)
    _print_render(run_dir, result)
    return _validate(root, run_dir)


def _print_render(run_dir: Path, result: dict) -> None:
    source = f", reused from request {result['reused_from']}" if result.get("reused_from") else ""
    print(f"Draft MP4: {run_dir / result['draft']} ({result['frames']} frames{source})")
    print(f"Render record: {run_dir / result['record']}")


def _render(root: Path, run_dir: Path, *, crf: int = CRF, audio_bitrate: int = AUDIO_BITRATE) -> int:
    from .render import create_render

    try:
        result = create_render(root, run_dir, crf=crf, audio_bitrate=audio_bitrate)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"pgvideo: rendering failed: {error}", file=sys.stderr)
        return 1
    _print_render(run_dir, result)
    return _validate(root, run_dir)


def _validate(root: Path, run_dir: Path) -> int:
    from .validate import NeedsReview, validate_video

    try:
        result = validate_video(root, run_dir)
    except NeedsReview as error:
        print(f"pgvideo: needs review: {error}", file=sys.stderr)
        print(f"Quality report: {run_dir / 'quality-report.json'}", file=sys.stderr)
        return NEEDS_REVIEW
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"pgvideo: validation failed: {error}", file=sys.stderr)
        print(f"Quality report: {run_dir / 'quality-report.json'}", file=sys.stderr)
        return 1
    output = root / result["output"]
    report = json.loads((run_dir / result["record"]).read_text())
    reuse = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8")).get("reuse") or {}
    print(f"Video: {output / result['video']} ({result['duration_seconds']:.3f} seconds)")
    print(f"Document: {report['document']['url']} (PostgreSQL {report['document']['postgresql_version']})")
    extra = ", ".join(str(output / name) for name in ("content-report.md", "plan.md", "orchestration.json")
                      if (output / name).is_file())
    print(f"Accompanying files: {output / 'transcript.md'}, {output / 'captions.srt'}, "
          f"{output / 'captions.vtt'}, {output / 'references.md'}, {output / 'glossary-check.md'}, "
          f"{output / 'quality-report.json'}, {output / 'manifest.json'}" + (f", {extra}" if extra else ""))
    if reuse.get("registered"):
        print(f"Reuse index: {root / reuse['index']}")
    else:
        print(f"Reuse index: not registered ({reuse.get('reason')})")
    return 0


def render(args: argparse.Namespace, root: Path) -> int:
    try:
        run_dir, _ = _request(root, args.request)
    except (ValueError, OSError) as error:
        print(f"pgvideo: {error}", file=sys.stderr)
        return 1
    return _render(root, run_dir, crf=args.crf, audio_bitrate=args.audio_bitrate)


def validate(args: argparse.Namespace, root: Path) -> int:
    try:
        run_dir, _ = _request(root, args.request)
    except (ValueError, OSError) as error:
        print(f"pgvideo: {error}", file=sys.stderr)
        return 1
    return _validate(root, run_dir)


def timing(args: argparse.Namespace, root: Path) -> int:
    try:
        run_dir, _ = _request(root, args.request)
    except (ValueError, OSError) as error:
        print(f"pgvideo: {error}", file=sys.stderr)
        return 1
    return _timing(root, run_dir)


def narrate(args: argparse.Namespace, root: Path) -> int:
    try:
        run_dir, _ = _request(root, args.request)
    except (ValueError, OSError) as error:
        print(f"pgvideo: {error}", file=sys.stderr)
        return 1
    return _narrate(root, run_dir, lufs=args.lufs, true_peak=args.true_peak,
                    refresh=set(args.refresh_unit))


def _report_check(run_dir: Path, check: dict) -> int:
    counts = check["counts"]
    claims = counts["claims"]
    print(f"Glossary check: {run_dir / check['record']} ({counts['consistent']} consistent, {counts['conflict']} "
          f"conflict, {counts['version_mismatch']} version mismatch, {counts['ambiguous']} ambiguous, "
          f"{counts['not_in_glossary']} not in glossary; {counts['resolved']} resolved, "
          f"{counts['corrections']} correction(s) for the script)")
    # Identifier lookups only; the meaning of a claim is judged separately.
    print(f"Lexical claim lookups: {claims['verified']} verified, {claims['supported']} supported, "
          f"{claims['cited']} cited, {claims['unconfirmed']} unconfirmed, {claims['uncited']} uncited")
    print(f"Glossary check report: {run_dir / check['report']}")
    if check["status"] == "needs_review":
        print(f"pgvideo: needs review: {check['issues']['blocking']} blocking issue(s) in {check['report']}. "
              f"Record resolutions in {run_dir / 'resolutions.yaml'}, then run: "
              f"scripts/pgvideo resume --request {run_dir.name}", file=sys.stderr)
        return NEEDS_REVIEW
    return 0


def _request(root: Path, request: str) -> tuple[Path, dict]:
    if not REQUEST_ID.fullmatch(request):
        raise ValueError(f"Request ID '{request}' must be one directory name under runs/.")
    run_dir = project_directory(root, Path("runs") / request, label="Request")
    if not (run_dir / "manifest.json").is_file():
        raise ValueError(f"No request '{request}' in {root / 'runs'}.")
    return run_dir, json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))


def resume(args: argparse.Namespace, root: Path) -> int:
    """Repeat the glossary cross-check with the request's resolutions, then continue from saved work."""
    from .crosscheck import check_glossary
    from .orchestration import is_harness

    try:
        run_dir, manifest = _request(root, args.request)
    except (ValueError, OSError) as error:
        print(f"pgvideo: {error}", file=sys.stderr)
        return 1
    if is_harness(run_dir):
        return _harness_command(root, args, "resume", lambda run: _resume_harness(root, run))
    try:
        for stage, report in (("sources", "source-report.md"), ("document", "coverage.md"),
                              ("glossary", "glossary-matches.json")):
            status = (manifest.get(stage) or {}).get("status")
            if status != "passed":
                raise ValueError(
                    f"Request {args.request} stopped before the glossary cross-check: its {stage} stage has status "
                    f"'{status}' (see {report}). Only the cross-check can be resumed; fix the wiki page and create "
                    "a new request.")
        print(f"Resuming request: {run_dir}")
        # Redraft with the drafter the request last used; a scene file or command is read again.
        drafter = (manifest.get("script") or {}).get("drafter") or {}
        check = check_glossary(root, run_dir)
    except (ValueError, OSError) as error:
        print(f"pgvideo: {error}", file=sys.stderr)
        return 1
    status = _report_check(run_dir, check)
    if status != 0:
        return status
    named = Path(drafter["name"]) if drafter.get("kind") in ("file", "command") else None
    return _script(root, run_dir, storyboard=named if drafter.get("kind") == "file" else None,
                   command=named if drafter.get("kind") == "command" else None, reuse=not args.no_reuse)


def _resume_harness(root: Path, run_dir: Path) -> tuple[str, str]:
    """Repeat the cross-check and the evidence packet, then revalidate the request's saved content."""
    from .crosscheck import check_glossary
    from .evidence import build_evidence

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    for stage in ("sources", "document", "glossary"):
        if (manifest.get(stage) or {}).get("status") != "passed":
            raise ValueError(f"The {stage} stage has status '{(manifest.get(stage) or {}).get('status')}'; only the "
                             "cross-check and later stages can be resumed. Fix the wiki page and prepare a new "
                             "request.")
    print(f"Resuming request: {run_dir}")
    if _report_check(run_dir, check_glossary(root, run_dir)) != 0:
        return "needs_review", "The cross-check still has unresolved blocking issues."
    evidence = build_evidence(root, run_dir)
    print(f"Evidence packet: {run_dir / evidence['record']} (digest {evidence['digest'][:12]})")
    status_, message = _revalidate(root, run_dir, run_dir)
    return status_, message + " Media is rebuilt or reused by `build`."


def script(args: argparse.Namespace, root: Path) -> int:
    """Import a harness storyboard; for an older request, draft or import its script and build its video."""
    from .orchestration import is_harness

    try:
        run_dir, manifest = _request(root, args.request)
    except (ValueError, OSError) as error:
        print(f"pgvideo: {error}", file=sys.stderr)
        return 1
    if is_harness(run_dir):
        options = {"storyboard": args.storyboard, "command": args.drafter_command,
                   "revision": "human" if args.human_revision else None, "duration_rewrite": args.duration_rewrite}
        return _harness_command(root, args, "script", lambda run: _import_storyboard(root, run, **options))
    if args.duration_rewrite or args.human_revision:
        print("pgvideo: --duration-rewrite and --human-revision are for harness requests.", file=sys.stderr)
        return 1
    try:
        for stage, report in (("sources", "source-report.md"), ("document", "coverage.md"),
                              ("glossary", "glossary-matches.json"), ("glossary_check", "glossary-check.md")):
            status = (manifest.get(stage) or {}).get("status")
            if status != "passed":
                raise ValueError(
                    f"Request {args.request} has not passed the step before the script: its {stage} stage has "
                    f"status '{status}' (see {report}).")
    except (ValueError, OSError) as error:
        print(f"pgvideo: {error}", file=sys.stderr)
        return 1
    return _script(root, run_dir, storyboard=args.storyboard, command=args.drafter_command,
                   reuse=not args.no_reuse)


COMMANDS = {"prepare": prepare, "status": status, "plan": plan, "script": script, "review": review, "build": build,
            "resume": resume, "replay": replay, "excerpt": excerpt, "baseline": baseline, "note": note,
            "narrate": narrate, "timing": timing, "render": render, "validate": validate}


def main(argv: list[str] | None = None) -> int:
    try:
        root = project_root()
    except ValueError as error:
        print(f"pgvideo: {error}", file=sys.stderr)
        return 1
    if (
        Path(sys.executable).resolve() != (root / ".venv" / "bin" / "python").resolve()
        or Path(sys.base_prefix).resolve() != (root / ".runtime" / "python").resolve()
        or os.environ.get("PGVIDEO_LOCAL_ENV") != str(root)
    ):
        print("pgvideo: use scripts/pgvideo to run with the project-local environment.", file=sys.stderr)
        return 1
    args = parser().parse_args(argv)
    command = COMMANDS.get(args.command)
    return command(args, root) if command else 2
