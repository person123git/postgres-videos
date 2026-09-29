"""The pgvideo command-line interface."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .paths import REQUEST_ID, project_directory, project_root
from .assets import AssetError, local_selection
from .sources import REPOSITORY, SourceError, resolve_document

# Exit status for a request that needs a documented resolution before it can continue.
NEEDS_REVIEW = 3
# Narration and encoding settings that generate, resume, and script use; a reuse lookup plans with them.
LUFS, TRUE_PEAK, CRF, AUDIO_BITRATE = -16.0, -1.5, 20, 128
NO_REUSE = ("build the narration and MP4 even when a validated video with the same inputs exists; "
            "it is registered for reuse afterwards")


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


def parser() -> argparse.ArgumentParser:
    # Imported here because it needs .venv packages; main() rejects other interpreters before parsing.
    from .document import DEFAULT_DETAIL, DETAILS

    command = argparse.ArgumentParser(prog="pgvideo")
    subcommands = command.add_subparsers(dest="command", required=True)
    generate = subcommands.add_parser(
        "generate", help="validate one document and deliver a narrated MP4"
    )
    generate.add_argument("--document", required=True, help="wiki-relative .md path or GitHub blob URL")
    generate.add_argument("--ref", help="branch, tag, or commit (defaults to master for relative paths)")
    generate.add_argument("--voice", default="af_heart", help="Kokoro voice (default: af_heart)")
    generate.add_argument("--language", default="a", help="Kokoro language code (default: a, American English)")
    generate.add_argument("--speed", type=positive_speed, default=1.0, help="speaking speed (default: 1.0)")
    generate.add_argument(
        "--detail", choices=DETAILS, default=DEFAULT_DETAIL,
        help="how much of the page to narrate: summary (the question, the page's own summary, and one sentence "
             "per main point, a few minutes), standard (condenses pages longer than about 10 minutes of "
             f"narration), or full (every section, no length limit) (default: {DEFAULT_DETAIL})",
    )
    generate.add_argument("--width", type=even_dimension, default=1920, help="video width (default: 1920)")
    generate.add_argument("--height", type=even_dimension, default=1080, help="video height (default: 1080)")
    generate.add_argument(
        "--output", type=Path, default=Path("output"),
        help="video output directory inside the project (relative to the project root)",
    )
    generate.add_argument("--no-reuse", action="store_true", help=NO_REUSE)
    resume = subcommands.add_parser(
        "resume", help="repeat the glossary cross-check of an existing request, applying its resolutions, "
                       "then redraft and narrate its script"
    )
    resume.add_argument("--request", required=True, help="request ID, the directory name under runs/")
    resume.add_argument("--no-reuse", action="store_true", help=NO_REUSE)
    script = subcommands.add_parser(
        "script", help="draft and narrate the storyboard of a request whose cross-check passed, or "
                       "validate an edited scene file or a drafter command's output"
    )
    script.add_argument("--request", required=True, help="request ID, the directory name under runs/")
    source = script.add_mutually_exclusive_group()
    source.add_argument("--storyboard", type=Path,
                        help="scene file (JSON or YAML) inside the project, such as an edited copy of storyboard.json")
    source.add_argument("--drafter-command", type=Path,
                        help="executable inside the project that reads draft-input.json on stdin and writes scenes "
                             "on stdout")
    script.add_argument("--no-reuse", action="store_true", help=NO_REUSE)
    narrate = subcommands.add_parser("narrate", help="generate or refresh Kokoro narration for a passed storyboard")
    narrate.add_argument("--request", required=True, help="request ID under runs/")
    narrate.add_argument("--lufs", type=float, default=LUFS, help="integrated loudness target (default: -16)")
    narrate.add_argument("--true-peak", type=float, default=TRUE_PEAK, help="maximum true peak in dBTP (default: -1.5)")
    narrate.add_argument("--refresh-unit", action="append", default=[],
                         help="resynthesize one unit or sentence ID, even if it is cached; repeat as needed")
    timing = subcommands.add_parser("timing", help="rebuild scene timing and captions from passed narration")
    timing.add_argument("--request", required=True, help="request ID under runs/")
    render = subcommands.add_parser("render", help="render, validate, and deliver the MP4 from passed timing")
    render.add_argument("--request", required=True, help="request ID under runs/")
    render.add_argument("--crf", type=int, default=CRF, help="H.264 constant rate factor (default: 20)")
    render.add_argument("--audio-bitrate", type=int, default=AUDIO_BITRATE, help="AAC bitrate in kb/s (default: 128)")
    validate = subcommands.add_parser("validate", help="validate and deliver an existing rendered request")
    validate.add_argument("--request", required=True, help="request ID under runs/")
    return command


def create_request(args: argparse.Namespace, *, workspace: Path | None = None) -> Path:
    if not args.voice.strip() or not args.language.strip():
        raise ValueError("Voice and language must be nonempty.")
    root = project_root()
    base = project_directory(root, workspace if workspace is not None else root, label="Workspace")
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
        "settings": {
            "voice": args.voice.strip(),
            "language": args.language.strip(),
            "speed": args.speed,
            "detail": args.detail,
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
        report_path = root / ".runtime" / "environment-report.json"
        if report_path.is_file():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if report.get("status") != "passed" or report.get("project_root") != str(root):
                raise ValueError("The local environment report is stale or failed; run scripts/pgvideo doctor.")
            manifest = {
                "request_id": request_id,
                "environment": {
                    "python": report["python"],
                    "platform": report["platform"],
                    "checks": report["checks"],
                    "artifacts": report.get("artifacts", {}),
                    "isolation": report.get("isolation", {}),
                    "os_requirements": report["os_requirements"],
                    "isolation_limitations": report["isolation_limitations"],
                    "tools_lock_sha256": hashlib.sha256((root / "tools.lock").read_bytes()).hexdigest(),
                    "requirements_lock_sha256": hashlib.sha256((root / "requirements.lock").read_bytes()).hexdigest(),
                },
            }
            (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def generate(args: argparse.Namespace, root: Path) -> int:
    """Validate the request, cross-check its sources, draft its script, and reuse or build its video."""
    # Imported here because they need .venv packages; main() must first reject other interpreters.
    from .crosscheck import check_glossary
    from .document import parse_document
    from .glossary import match_glossary
    from .snapshot import snapshot_sources

    try:
        local_selection(language=args.language, voice=args.voice)
        request_path = create_request(args, workspace=root)
        print(f"Validated request: {request_path}")
        request = json.loads(request_path.read_text(encoding="utf-8"))
        sources = snapshot_sources(root, request_path.parent, request)
    except (AssetError, SourceError, ValueError, OSError) as error:
        print(f"pgvideo: {error}", file=sys.stderr)
        return 1
    run_dir = request_path.parent
    wiki, postgres = sources["wiki"], sources["postgres"]
    print(f"Wiki commit: {wiki['commit']} (ref {wiki['requested_ref']})")
    if postgres.get("commit"):
        print(f"PostgreSQL {postgres['version']} source commit: {postgres['commit']}")
    print(f"Source snapshot: {run_dir / sources['record']}")
    print(f"Source report: {run_dir / sources['report']}")
    if sources["status"] == "needs_review":
        print(
            f"pgvideo: needs review: {sources['issues']['blocking']} blocking issue(s) in the source report.",
            file=sys.stderr,
        )
        return NEEDS_REVIEW
    try:
        document = parse_document(root, run_dir)
    except (ValueError, OSError) as error:
        print(f"pgvideo: {error}", file=sys.stderr)
        return 1
    coverage = document["coverage"]
    decisions = coverage["decisions"]
    print(f"Document structure: {run_dir / document['record']}")
    print(f"Coverage map: {run_dir / coverage['file']} ({coverage['detail']} detail: "
          f"{decisions['explain']} explained, {decisions['summarize']} summarized, {decisions['omit']} omitted; "
          f"about {coverage['planned_minutes']} minutes of narration planned)")
    if document["status"] == "needs_review":
        print(f"pgvideo: needs review: {document['issues']['blocking']} blocking issue(s) in the coverage map.",
              file=sys.stderr)
        return NEEDS_REVIEW
    try:
        glossary = match_glossary(root, run_dir)
    except (ValueError, OSError) as error:
        print(f"pgvideo: {error}", file=sys.stderr)
        return 1
    counts, index = glossary["counts"], glossary["index"]
    print(f"Glossary index: {run_dir / index['path']} ({index['entries']} entries, built from the glossary "
          "downloaded for this request)")
    print(f"Glossary matches: {run_dir / glossary['record']} ({counts['matched']} entries: {counts['central']} "
          f"central, {counts['supporting']} supporting, {counts['peripheral']} peripheral; "
          f"{counts['ambiguous']} ambiguous, {counts['unmatched']} unmatched terms)")
    try:
        check = check_glossary(root, run_dir)
    except (ValueError, OSError) as error:
        print(f"pgvideo: {error}", file=sys.stderr)
        return 1
    status = _report_check(run_dir, check)
    if status != 0:
        return status
    return _script(root, run_dir, reuse=not args.no_reuse)


def _script(root: Path, run_dir: Path, *, storyboard: Path | None = None, command: Path | None = None,
            reuse: bool = True) -> int:
    """Draft or import the script, then reuse or build its video when validation passes."""
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


def _build(root: Path, run_dir: Path, *, reuse: bool) -> int:
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
        return _narrate(root, run_dir)
    print(f"Reuse: request {video.request_id} has a validated video with the same inputs{key}.")
    return _reuse_narration(root, run_dir, video)


def _reuse_narration(root: Path, run_dir: Path, video) -> int:
    from .reuse import reuse_narration

    try:
        result = reuse_narration(root, run_dir, video)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"pgvideo: cannot reuse the narration of request {video.request_id} ({error}); synthesizing it.",
              file=sys.stderr)
        return _narrate(root, run_dir)
    _print_narration(run_dir, result)
    return _timing(root, run_dir, video=video)


def _print_narration(run_dir: Path, result: dict) -> None:
    source = f", reused from request {result['reused_from']}" if result.get("reused_from") else ""
    print(f"Narration master: {run_dir / result['master']} ({result['duration_seconds']} seconds{source})")
    print(f"Audio map: {run_dir / result['record']} ({result['units']} units)")
    print(f"Narration report: {run_dir / result['report']}")


def _narrate(root: Path, run_dir: Path, *, lufs: float = LUFS, true_peak: float = TRUE_PEAK,
             refresh: set[str] | None = None) -> int:
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
    print(f"Accompanying files: {output / 'transcript.md'}, {output / 'captions.srt'}, "
          f"{output / 'captions.vtt'}, {output / 'references.md'}, {output / 'glossary-check.md'}, "
          f"{output / 'quality-report.json'}, {output / 'manifest.json'}")
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
    print(f"Narrated claims: {claims['verified']} verified, {claims['supported']} supported, {claims['cited']} cited, "
          f"{claims['unconfirmed']} unconfirmed, {claims['uncited']} uncited")
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
    """Repeat the glossary cross-check of an existing request with its documented resolutions, then the script."""
    from .crosscheck import check_glossary

    try:
        run_dir, manifest = _request(root, args.request)
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


def script(args: argparse.Namespace, root: Path) -> int:
    """Draft the script of a request whose cross-check passed, or validate an edited or externally drafted one."""
    try:
        run_dir, manifest = _request(root, args.request)
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
    if args.command == "generate":
        return generate(args, root)
    if args.command == "resume":
        return resume(args, root)
    if args.command == "script":
        return script(args, root)
    if args.command == "narrate":
        return narrate(args, root)
    if args.command == "timing":
        return timing(args, root)
    if args.command == "render":
        return render(args, root)
    if args.command == "validate":
        return validate(args, root)
    return 2
