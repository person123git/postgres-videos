"""The pgvideo command-line interface: narrate a storyboard and render it as a video.

pgvideo is a media utility. Whoever makes a video writes its storyboard
(schemas/storyboard.schema.json); `build` reads that file, synthesizes the
narration with the local Kokoro model, times it, renders the slides and the WebM,
checks the media, and delivers the files. `narrate`, `timing`, `render`, and
`validate` repeat one of those stages. No command reads the wiki, judges what a
storyboard says, or calls a language model.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .assets import AssetError, local_selection
from .paths import REQUEST_ID, project_directory, project_root, write_atomic
from .stages import STAGES

# Exit status for a build that stopped on something the storyboard's author or the operator must fix.
NEEDS_REVIEW = 3
# Narration and encoding settings that build uses; a reuse lookup plans with them.
# At 192 kb/s libopus adds about 0.1 dB to the narration master's true peak; at 64 kb/s it adds about 0.8 dB,
# nearly all of the headroom under validation's limit.
LUFS, TRUE_PEAK, CRF, AUDIO_BITRATE = -16.0, -1.5, 40, 192
DEFAULTS = {"voice": "af_heart", "language": "a", "speed": 1.0, "width": 1920, "height": 1080, "output": "output"}
# A result folds more issues of one severity and code than this into a single issue.
ISSUE_GROUP_LIMIT = 3
ISSUE_EXAMPLES = 3
JSON_HELP = "print one result as JSON on standard output; progress goes to standard error"
EXIT = {"completed": 0, "needs_review": NEEDS_REVIEW, "failed": 1}


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
    command = argparse.ArgumentParser(prog="pgvideo", description="Narrate a storyboard and render it as a video.")
    subcommands = command.add_subparsers(dest="command", required=True)

    build = subcommands.add_parser(
        "build", help="narrate, time, render, check, and deliver a storyboard, reusing matching narration and media")
    build.add_argument("--storyboard", type=Path,
                       help="storyboard file (JSON or YAML) inside the project; without it, the request's imported "
                            "storyboard is built again")
    build.add_argument("--request",
                       help="name of the request, the directory under runs/ and output/; a new name starts a "
                            "request, an existing one is rebuilt (default: a generated ID)")
    build.add_argument("--voice", help=f"Kokoro voice (default: {DEFAULTS['voice']})")
    build.add_argument("--language", help=f"Kokoro language code (default: {DEFAULTS['language']}, American English)")
    build.add_argument("--speed", type=positive_speed, help=f"speaking speed (default: {DEFAULTS['speed']})")
    build.add_argument("--width", type=even_dimension, help=f"video width (default: {DEFAULTS['width']})")
    build.add_argument("--height", type=even_dimension, help=f"video height (default: {DEFAULTS['height']})")
    build.add_argument("--output", type=Path,
                       help=f"output directory inside the project (default: {DEFAULTS['output']})")
    build.add_argument("--no-reuse", action="store_true",
                       help="build the narration and WebM even when a validated video with the same inputs exists; "
                            "it is registered for reuse afterwards")
    build.add_argument("--json", action="store_true", help=JSON_HELP)

    def stage(name: str, help_text: str) -> argparse.ArgumentParser:
        sub = subcommands.add_parser(name, help=help_text)
        sub.add_argument("--request", required=True, help="request name, the directory under runs/")
        return sub

    narrate = stage("narrate", "generate or refresh Kokoro narration for a request's storyboard, then continue")
    narrate.add_argument("--lufs", type=float, default=LUFS, help="integrated loudness target (default: -16)")
    narrate.add_argument("--true-peak", type=float, default=TRUE_PEAK, help="maximum true peak in dBTP (default: -1.5)")
    narrate.add_argument("--refresh-unit", action="append", default=[],
                         help="resynthesize one unit or sentence ID, even if it is cached; repeat as needed")
    stage("timing", "rebuild scene timing and captions from the narration, then continue")
    render = stage("render", "render, check, and deliver the WebM from the timing")
    render.add_argument("--crf", type=int, default=CRF, help="SVT-AV1 constant rate factor, 0–63 (default: 40)")
    render.add_argument("--audio-bitrate", type=int, default=AUDIO_BITRATE, help="Opus bitrate in kb/s (default: 192)")
    stage("validate", "check and deliver an existing rendered request")
    return command


# Requests -----------------------------------------------------------------------------------------


def open_request(root: Path, args: argparse.Namespace) -> Path:
    """Return the request's directory, creating it for a new name, and record the settings given."""
    name = args.request or f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:12]}"
    if not REQUEST_ID.fullmatch(name):
        raise ValueError(f"Request name '{name}' must be one directory name: letters, digits, dots, hyphens, and "
                         "underscores.")
    run_dir = project_directory(root, Path("runs") / name, label="Request")
    path = run_dir / "request.json"
    request = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {
        "request_id": name, "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "settings": {}}
    settings = dict(request["settings"])
    for key, default in DEFAULTS.items():
        given = getattr(args, key)
        stored = "output_dir" if key == "output" else key
        if key == "output":
            # Kept as the directory itself, so a later rebuild delivers to the same place.
            if given is not None or stored not in settings:
                settings[stored] = str(project_directory(root, given if given is not None else Path(default),
                                                         label="Output"))
        elif given is not None or stored not in settings:
            settings[stored] = given if given is not None else default
    if not str(settings["voice"]).strip() or not str(settings["language"]).strip():
        raise ValueError("Voice and language must be nonempty.")
    local_selection(language=settings["language"], voice=settings["voice"])
    if settings != request["settings"] or not path.is_file():
        request["settings"] = settings
        write_atomic(root, run_dir.relative_to(root) / "request.json",
                     (json.dumps(request, indent=2, ensure_ascii=False) + "\n").encode("utf-8"), label="Request")
    if not (run_dir / "manifest.json").is_file():
        write_atomic(root, run_dir.relative_to(root) / "manifest.json",
                     (json.dumps({"request_id": name}, indent=2) + "\n").encode("utf-8"), label="Request")
    return run_dir


def _request(root: Path, request: str) -> Path:
    if not REQUEST_ID.fullmatch(request):
        raise ValueError(f"Request name '{request}' must be one directory name under runs/.")
    run_dir = project_directory(root, Path("runs") / request, label="Request")
    if not (run_dir / "manifest.json").is_file():
        raise ValueError(f"No request '{request}' in {root / 'runs'}.")
    return run_dir


# Build --------------------------------------------------------------------------------------------


def compact_issues(issues: list[dict]) -> list[dict]:
    """Fold issues that share a severity and code into one, when there are more than ISSUE_GROUP_LIMIT.

    A result is read by a model with a small context, and one mistake repeated in
    every scene otherwise fills it. The folded issue keeps the count, every scene
    it names, the first messages as examples, and the first action. script.md
    lists each issue.
    """
    groups: dict[tuple, list[dict]] = {}
    for issue in issues:
        groups.setdefault((issue.get("severity"), issue.get("code")), []).append(issue)
    compacted = []
    for (severity, code), same in groups.items():
        if len(same) <= ISSUE_GROUP_LIMIT:
            compacted += [{key: value for key, value in issue.items() if value is not None} for issue in same]
            continue
        examples = list(dict.fromkeys(issue["message"] for issue in same))[:ISSUE_EXAMPLES]
        folded = {"severity": severity, "code": code, "count": len(same),
                  "message": f"{len(same)} issues with this code; `examples` holds the first {len(examples)}. "
                             "script.md lists each one.",
                  "examples": examples,
                  "scenes": list(dict.fromkeys(issue["scene"] for issue in same if issue.get("scene")))}
        if action := next((issue["action"] for issue in same if issue.get("action")), None):
            folded["action"] = action
        compacted.append(folded)
    return compacted


def _storyboard_issues(run_dir: Path) -> list[dict]:
    path = run_dir / "storyboard.json"
    if not path.is_file():
        return []
    issues = json.loads(path.read_text(encoding="utf-8")).get("issues", [])
    return compact_issues([issue for issue in issues if issue["severity"] in ("blocking", "warning")])


def _stopped(run_dir: Path) -> tuple[str, str]:
    """Name the stage a build stopped at and why, from the request's records."""
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    for stage in STAGES:
        record = manifest.get(stage) or {}
        if record.get("status") in ("failed", "needs_review"):
            return stage, record.get("error") or f"see {run_dir / 'quality-report.json'}"
    return "build", "the error is above"


def build(args: argparse.Namespace, root: Path) -> int:
    """Import the storyboard, build its video, and print where the files were delivered."""
    from .storyboard import import_storyboard

    stdout = sys.stdout
    result: dict = {"request_id": None, "stage": "request", "status": "failed", "issues": []}
    with contextlib.redirect_stdout(sys.stderr if args.json else sys.stdout):
        try:
            run_dir = open_request(root, args)
            result["request_id"] = run_dir.name
            print(f"Request: {run_dir}")
            result["stage"] = "storyboard"
            if args.storyboard is not None:
                record = import_storyboard(root, run_dir, args.storyboard)
                counts, estimate = record["counts"], record["estimate"]
                print(f"Storyboard: {run_dir / record['record']} ({counts['scenes']} scenes, {counts['sentences']} "
                      f"narrated sentences, about {estimate['minutes']} minutes)")
                print(f"Script: {run_dir / record['script']}")
            else:
                record = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8")).get("script") or {}
                if not record:
                    raise ValueError(f"Request {run_dir.name} has no storyboard yet; give one with --storyboard.")
            result["issues"] = _storyboard_issues(run_dir)
            if record.get("status") != "passed":
                result.update(status="needs_review" if record.get("status") == "needs_review" else "failed",
                              message=(f"The storyboard cannot be narrated or rendered as it is: "
                                       f"{record['issues']['blocking']} blocking issue(s), listed in "
                                       f"{run_dir / 'script.md'}." if record.get("status") == "needs_review" else
                                       f"The storyboard was not imported: {record.get('error')}"))
            else:
                code = _build(root, run_dir, reuse=not args.no_reuse)
                manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
                if code == 0:
                    validation = manifest["validation"]
                    output = root / validation["output"]
                    quality = json.loads((run_dir / "quality-report.json").read_text(encoding="utf-8"))
                    result.update(
                        stage="validation", status="completed", duration_seconds=validation["duration_seconds"],
                        delivery={"directory": str(output), "video": str(output / validation["video"]),
                                  "files": [{"path": str(output / name), "sha256": digest}
                                            for name, digest in quality["delivery"]["files"].items()]},
                        message=(f"Delivered {output / validation['video']} ({validation['duration_seconds']:.1f} "
                                 "seconds) with its transcript, captions, references, and quality report."))
                else:
                    stage, reason = _stopped(run_dir)
                    result.update(stage=stage, status="needs_review" if code == NEEDS_REVIEW else "failed",
                                  message=f"The build stopped at {stage}: {reason}")
        except (AssetError, ValueError, OSError, KeyError, TypeError) as error:
            result.update(status="failed", message=f"pgvideo: {error}")
        if result["status"] == "failed" and not any(i["severity"] == "blocking" for i in result["issues"]):
            result["issues"].insert(0, {"severity": "blocking", "code": "failed", "message": result["message"]})
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False), file=stdout)
    else:
        # Errors go to standard error, like every other pgvideo failure.
        problems = stdout if result["status"] == "completed" else sys.stderr
        print(result["message"], file=problems)
        for issue in result["issues"]:
            if issue["severity"] == "blocking" and issue["code"] != "failed":
                where = " · ".join(filter(None, [issue.get("scene"), issue.get("narration")]))
                print(f"  blocking {issue['code']}" + (f" ({where})" if where else "") + f": {issue['message']}",
                      file=problems)
    return EXIT[result["status"]]


# Media stages ------------------------------------------------------------------------------------


def _build(root: Path, run_dir: Path, *, reuse: bool) -> int:
    """Reuse a validated video with the same inputs, or narrate, time, render, and validate the storyboard."""
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
        print(f"Reuse: building the narration and WebM{key}; {reason}.")
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
    """Time the narration, then render the WebM or reuse the one registered for `video`."""
    from .timing import create_timing

    try:
        result = create_timing(root, run_dir)
    except (ValueError, OSError, KeyError, TypeError) as error:
        if video is not None:
            print(f"pgvideo: the narration reused from request {video.request_id} does not fit this storyboard "
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
        print(f"pgvideo: cannot reuse the WebM of request {video.request_id} ({error}); rendering it.",
              file=sys.stderr)
        return _render(root, run_dir)
    _print_render(run_dir, result)
    return _validate(root, run_dir)


def _print_render(run_dir: Path, result: dict) -> None:
    source = f", reused from request {result['reused_from']}" if result.get("reused_from") else ""
    print(f"Draft WebM: {run_dir / result['draft']} ({result['frames']} frames{source})")
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
    reuse = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8")).get("reuse") or {}
    print(f"Video: {output / result['video']} ({result['duration_seconds']:.3f} seconds)")
    print(f"Accompanying files: {output / 'transcript.md'}, {output / 'captions.srt'}, "
          f"{output / 'captions.vtt'}, {output / 'references.md'}, {output / 'quality-report.json'}, "
          f"{output / 'manifest.json'}")
    if reuse.get("registered"):
        print(f"Reuse index: {root / reuse['index']}")
    else:
        print(f"Reuse index: not registered ({reuse.get('reason')})")
    return 0


def _stage(args: argparse.Namespace, root: Path, work) -> int:
    try:
        run_dir = _request(root, args.request)
    except (ValueError, OSError) as error:
        print(f"pgvideo: {error}", file=sys.stderr)
        return 1
    return work(run_dir)


def narrate(args: argparse.Namespace, root: Path) -> int:
    return _stage(args, root, lambda run_dir: _narrate(root, run_dir, lufs=args.lufs, true_peak=args.true_peak,
                                                       refresh=set(args.refresh_unit)))


def timing(args: argparse.Namespace, root: Path) -> int:
    return _stage(args, root, lambda run_dir: _timing(root, run_dir))


def render(args: argparse.Namespace, root: Path) -> int:
    return _stage(args, root, lambda run_dir: _render(root, run_dir, crf=args.crf, audio_bitrate=args.audio_bitrate))


def validate(args: argparse.Namespace, root: Path) -> int:
    return _stage(args, root, lambda run_dir: _validate(root, run_dir))


COMMANDS = {"build": build, "narrate": narrate, "timing": timing, "render": render, "validate": validate}


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
