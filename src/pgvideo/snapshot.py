"""Snapshot the selected document, the glossary, and cited PostgreSQL sources (Step 3)."""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .markdown import MarkdownError, outline, split_front_matter, table_after_heading
from .paths import project_directory
from .sources import COMMIT, POSTGRES_REPOSITORY, CommitFiles, SourceError, resolve_commit, write_atomic
from .stages import invalidate_after

GLOSSARY = "wiki/glossary.md"
SOURCE_TREE = re.compile(r"raw/postgres-(\d+)(?:/(.*))?")
WIKI_VERSION = re.compile(r"wiki/v(\d+)/")
LINE_ANCHOR = re.compile(r"L(\d+)(?:-L(\d+))?")
CONFIGURE_VERSION = re.compile(rb"AC_INIT\(\[PostgreSQL\],\s*\[((\d+)[^\]]*)\]")
# PostgreSQL 12 names its Autoconf input configure.in.
CONFIGURE_FILES = ("configure.ac", "configure.in")
# Reference lists repeat the answer's citations and are not narrated, so a broken
# citation that appears only in one of them is a warning rather than a blocker.
REFERENCE_SECTIONS = {"contents", "context reviewed", "source references", "navigation"}
DOWNLOAD_WORKERS = 8


class Report:
    """Issues found while taking the snapshot, most severe first when rendered."""

    ORDER = ("blocking", "warning", "note")

    def __init__(self):
        self.issues: list[dict] = []

    def add(self, severity: str, code: str, message: str, action: str | None = None, lines=()) -> None:
        self.issues.append({
            "severity": severity, "code": code, "message": message, "action": action,
            "lines": sorted({line for line in lines if line}),
        })

    def count(self, severity: str) -> int:
        return sum(issue["severity"] == severity for issue in self.issues)

    def sorted(self) -> list[dict]:
        return sorted(self.issues, key=lambda issue: self.ORDER.index(issue["severity"]))


def snapshot_sources(root: Path, run_dir: Path, request: dict) -> dict:
    """Retrieve the request's inputs from one resolved wiki commit and check their versions.

    Saves read-only copies under inputs/, then sources.json and source-report.md in the
    run directory, and records provenance in manifest.json. Returns the manifest's
    sources record, whose status is 'passed' or 'needs_review'. A retrieval or path
    failure marks the manifest 'failed' and raises.
    """
    try:
        return _snapshot(root, run_dir, request)
    except (ValueError, OSError) as error:
        _update_manifest(root, run_dir, request, status="failed", error=str(error))
        raise


def _snapshot(root: Path, run_dir: Path, request: dict) -> dict:
    report = Report()
    inputs = _Inputs(root, run_dir)
    repository = request["repository"]
    path = request["document"]["path"]
    ref = request["document"]["ref"]

    commit = resolve_commit(repository, ref)
    wiki = CommitFiles.open(root, repository, commit)
    if wiki is None:
        raise SourceError(f"GitHub has no commit {commit} in {repository}.")
    if wiki.kind(path) != "file":
        raise SourceError(
            f"Document '{path}' is not a regular file at {repository}@{commit}; "
            f"ref '{ref}' may have moved since the request was validated."
        )
    data = wiki.read(path)
    document = inputs.add("document", wiki, path, data)
    front, body = _markdown(data, path, report)
    document["front_matter"] = front
    if body is None:
        metadata = {"type": None, "version": None, "path_version": None, "pinned_commit": None,
                    "verification": {}}
    else:
        document.update(outline(body))
        metadata = _metadata(path, front, report)
    document.update(metadata)
    document["links"] = resolve_links(path, document.get("links", []), document.get("headings", []))

    glossary = _glossary(inputs, wiki, metadata["version"], report)
    _check_links(wiki, document, glossary, inputs, report)
    postgres = _evidence(root, inputs, document, metadata, report)
    _notes(document, glossary, postgres, report)

    status = "needs_review" if report.count("blocking") else "passed"
    record = {
        "request_id": request["request_id"],
        "status": status,
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "wiki": {"repository": repository, "requested_ref": ref, "commit": commit,
                 "committed_at": wiki.info.get("committed_at"), "tree": wiki.info["tree"]},
        "document": document,
        "glossary": glossary,
        "postgres": postgres,
        "images": [entry for entry in inputs.records if entry["role"] == "image"],
        "issues": report.sorted(),
    }
    write_atomic(root, run_dir.relative_to(root) / "sources.json", _json_bytes(record), label="Request")
    write_atomic(root, run_dir.relative_to(root) / "source-report.md",
                 _render_report(record).encode("utf-8"), label="Request")
    return _update_manifest(root, run_dir, request, status=status, record=record, inputs=inputs.records)


class _Inputs:
    """Read-only copies of every retrieved file, kept under the run's inputs/ directory."""

    def __init__(self, root: Path, run_dir: Path):
        self.root = root
        self.base = run_dir.relative_to(root) / "inputs"
        self.records: list[dict] = []
        self.saved: dict[tuple[str, str], dict] = {}

    def add(self, role: str, files: CommitFiles, path: str, data: bytes) -> dict:
        if (files.repository, path) in self.saved:
            return dict(self.saved[files.repository, path])
        prefix = "wiki" if files.repository != POSTGRES_REPOSITORY else "postgres"
        relative = self.base / prefix / Path(*path.split("/"))
        parent = project_directory(self.root, relative.parent, label="Request input")
        parent.mkdir(parents=True, exist_ok=True)
        target = parent / relative.name
        try:
            with target.open("xb") as stream:
                stream.write(data)
        except FileExistsError as error:
            # Only possible when two repository paths differ by case on a case-insensitive disk.
            raise SourceError(f"Two inputs map to the same file on this disk: {target}") from error
        target.chmod(0o444)
        record = {
            "role": role, "repository": files.repository, "commit": files.commit, "path": path,
            "url": files.url(path), "raw_url": files.raw_url(path),
            "input": relative.relative_to(self.base.parent).as_posix(), "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "git_blob_sha": files.blob_sha(path),
        }
        self.records.append(record)
        self.saved[files.repository, path] = record
        return dict(record)


def _markdown(data: bytes, path: str, report: Report) -> tuple[dict | None, str | None]:
    try:
        text = data.decode("utf-8").removeprefix("﻿")
    except UnicodeDecodeError as error:
        report.add("blocking", "not_utf8", f"'{path}' is not valid UTF-8 ({error}).",
                   "Save the file as UTF-8 in the wiki repository.")
        return None, None
    try:
        return split_front_matter(text)
    except MarkdownError as error:
        report.add("blocking", "front_matter_invalid", f"'{path}' has unreadable front matter: {error}.",
                   "Fix the YAML front matter between the opening and closing '---' lines.", [1])
        return None, None


def _version(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def _metadata(path: str, front: dict | None, report: Report) -> dict:
    front = front or {}
    match = WIKI_VERSION.match(path)
    path_version = int(match.group(1)) if match else None
    declared = front.get("version")
    version = _version(declared)
    if declared is not None and version is None:
        report.add("blocking", "version_invalid", f"Front matter version {declared!r} is not a major version number.",
                   "Set `version:` to the PostgreSQL major version, such as 18.")
    if version is not None and path_version is not None and version != path_version:
        report.add("blocking", "version_mismatch",
                   f"Front matter says PostgreSQL {version}, but the document is under wiki/v{path_version}/.",
                   "Correct the front matter version or move the page to the matching wiki/vNN/ directory.")
        version = None
    elif version is None and declared is None:
        if path_version is None:
            report.add("blocking", "version_missing",
                       "The document declares no PostgreSQL version and is not under wiki/vNN/.",
                       "Choose a versioned wiki page, or add `version:` and `pinned_commit:` front matter.")
        else:
            version = path_version
            report.add("warning", "version_not_declared",
                       f"Front matter has no `version:`; using PostgreSQL {version} from the wiki/v{version}/ path.",
                       f"Add `version: {version}` to the front matter.")
    elif path_version is None and version is not None:
        report.add("note", "version_path_missing",
                   f"The document is not under wiki/vNN/; PostgreSQL {version} comes from its front matter only.")

    declared_pin = front.get("pinned_commit")
    pin = declared_pin.strip().lower() if isinstance(declared_pin, str) else None
    if declared_pin is None:
        report.add("blocking", "pinned_commit_missing",
                   "Front matter has no `pinned_commit:` for the PostgreSQL source the page cites.",
                   "Record the full 40-character PostgreSQL commit the citations were checked against.")
    elif pin is None or not COMMIT.fullmatch(pin):
        report.add("blocking", "pinned_commit_invalid",
                   f"Front matter pinned_commit {declared_pin!r} is not a full 40-character commit SHA.",
                   "Record the full 40-character PostgreSQL commit the citations were checked against.")
        pin = None
    return {
        "type": front.get("type"), "version": version, "path_version": path_version, "pinned_commit": pin,
        "verification": {key: value for key, value in front.items() if key.startswith("verified")},
    }


def resolve_links(path: str, links: list[dict], headings: list[dict]) -> list[dict]:
    """Resolve each link against the document's location in the repository."""
    resolved = []
    for link in links:
        entry = dict(link)
        href = link["href"] or ""
        parts = urlsplit(href)
        fragment = unquote(parts.fragment) or None
        entry["fragment"] = fragment
        entry["reference_section"] = _in_reference_section(headings, link["section"])
        if parts.scheme or parts.netloc:
            entry["kind"] = "external"
        elif not parts.path:
            entry.update(kind="anchor", target=path)
        else:
            relative = unquote(parts.path)
            # GitHub resolves a leading slash from the repository root.
            joined = relative.lstrip("/") if relative.startswith("/") else posixpath.join(
                posixpath.dirname(path), relative)
            target = posixpath.normpath(joined)
            entry["target"] = target
            source = SOURCE_TREE.fullmatch(target)
            if target == ".." or target.startswith("../"):
                entry["kind"] = "outside"
            elif source:
                entry.update(kind="citation", postgres_version=int(source.group(1)),
                             source_path=source.group(2) or "")
                lines = LINE_ANCHOR.fullmatch(fragment or "")
                if lines:
                    entry["lines"] = [int(lines.group(1)), int(lines.group(2) or lines.group(1))]
            elif target == GLOSSARY:
                entry["kind"] = "glossary"
            else:
                entry["kind"] = "wiki"
        resolved.append(entry)
    return resolved


def _in_reference_section(headings: list[dict], section: int | None) -> bool:
    while section is not None:
        if headings[section]["text"].strip().lower() in REFERENCE_SECTIONS:
            return True
        section = headings[section]["parent"]
    return False


def _glossary(inputs: _Inputs, wiki: CommitFiles, version: int | None, report: Report) -> dict | None:
    if wiki.kind(GLOSSARY) != "file":
        report.add("blocking", "glossary_missing", f"{GLOSSARY} is missing at wiki commit {wiki.commit}.",
                   "Use a wiki ref that contains the glossary; the cross-check needs it.")
        return None
    # Every new request downloads the glossary again rather than using a copy cached by an earlier one.
    data = wiki.read(GLOSSARY, refresh=True)
    glossary = inputs.add("glossary", wiki, GLOSSARY, data)
    front, body = _markdown(data, GLOSSARY, report)
    glossary["front_matter"] = front
    if body is None:
        return glossary
    structure = outline(body)
    glossary["title"] = structure["title"]
    glossary["anchors"] = sorted({heading["anchor"] for heading in structure["headings"]})
    terms = next((heading for heading in structure["headings"] if heading["text"] == "Terms"), None)
    glossary["term_count"] = sum(heading["parent"] == terms["id"] for heading in structure["headings"]) if terms else 0
    if not glossary["term_count"]:
        report.add("blocking", "glossary_unreadable", f"{GLOSSARY} has no entries under a `Terms` heading.",
                   "Use a wiki ref whose glossary lists its entries under `## Terms`.")
    pins = {}
    for row in table_after_heading(body, "Source Pins"):
        if row.get("version", "").isdigit():
            pins[row["version"]] = {"checkout": row.get("checkout"), "branch": row.get("branch"),
                                    "commit": row.get("pinned commit")}
    glossary["source_pins"] = pins
    if version is not None and (pin := pins.get(str(version))) is None:
        report.add("warning", "glossary_version_unchecked",
                   f"The glossary's Source Pins table has no PostgreSQL {version} checkout.",
                   f"Glossary definitions may not have been checked on {version}; treat matches as coverage gaps.")
    elif version is not None:
        glossary["pin_for_version"] = pin
    return glossary


def _check_links(wiki: CommitFiles, document: dict, glossary: dict | None, inputs: _Inputs,
                 report: Report) -> None:
    """Check non-citation links and retrieve images stored in the wiki."""
    anchors = {heading["anchor"] for heading in document.get("headings", [])}
    glossary_anchors = set(glossary.get("anchors", [])) if glossary else set()
    problems: dict[tuple[str, str], list[int]] = {}
    retrieved: set[str] = set()
    for link in document["links"]:
        kind, target, fragment = link["kind"], link.get("target"), link["fragment"]
        if kind == "anchor" and fragment and fragment not in anchors:
            problems.setdefault(("anchor_missing", f"#{fragment}"), []).append(link["line"])
        elif kind == "glossary" and glossary and fragment and fragment not in glossary_anchors:
            problems.setdefault(("glossary_anchor_missing", fragment), []).append(link["line"])
        elif kind == "outside":
            problems.setdefault(("link_outside_repository", link["href"]), []).append(link["line"])
        elif kind == "external" and link["image"]:
            problems.setdefault(("external_image", link["href"]), []).append(link["line"])
        elif kind == "wiki":
            found = target == "." or wiki.kind(target) is not None
            link["exists"] = found
            if not found:
                code = "image_missing" if link["image"] else "link_target_missing"
                problems.setdefault((code, target), []).append(link["line"])
            elif link["image"] and wiki.kind(target) == "file" and target not in retrieved:
                inputs.add("image", wiki, target, wiki.read(target))
                retrieved.add(target)
    messages = {
        "anchor_missing": ("links to {} but the document has no such heading.", "Fix the anchor or heading."),
        "glossary_anchor_missing": ("links to glossary entry #{} which does not exist at this commit.",
                                    "Fix the link or add the glossary entry."),
        "link_outside_repository": ("links to {} which resolves outside the repository.", "Fix the relative path."),
        "external_image": ("shows the external image {}, which is not retrieved or reproducible.",
                           "Store the image in the wiki repository if the video should show it."),
        "image_missing": ("shows the image {} which is missing at this commit.", "Fix the image path."),
        "link_target_missing": ("links to {} which is missing at this commit.", "Fix the link."),
    }
    for (code, target), lines in problems.items():
        message, action = messages[code]
        report.add("warning", code, "The document " + message.format(target), action, lines)


def _evidence(root: Path, inputs: _Inputs, document: dict, metadata: dict, report: Report) -> dict:
    """Check that citations use the document's version and exist at its pinned source commit."""
    version, pin = metadata["version"], metadata["pinned_commit"]
    citations = [link for link in document["links"] if link["kind"] == "citation"]
    record = {"repository": POSTGRES_REPOSITORY, "version": version, "commit": pin,
              "citations": len(citations), "files": []}
    others: dict[int, list[int]] = {}
    for link in citations:
        if version is not None and link["postgres_version"] != version:
            others.setdefault(link["postgres_version"], []).append(link["line"])
    for other, lines in sorted(others.items()):
        report.add("blocking", "citation_version_mismatch",
                   f"{len(lines)} citation(s) point into raw/postgres-{other}/, but the document is for "
                   f"PostgreSQL {version} and records only a {version} source commit.",
                   f"Cite the raw/postgres-{version}/ checkout, or move the cross-version material to a page "
                   f"that records the PostgreSQL {other} pin.", lines)
    if version is not None and not any(link["postgres_version"] == version for link in citations):
        report.add("blocking", "no_citations",
                   f"The document cites no files under raw/postgres-{version}/.",
                   "Choose a page whose claims cite the pinned PostgreSQL source.")
    if version is None or pin is None:
        record["checked"] = False
        return record

    postgres = CommitFiles.open(root, POSTGRES_REPOSITORY, pin)
    if postgres is None:
        report.add("blocking", "pinned_commit_not_found",
                   f"PostgreSQL commit {pin} does not exist in {POSTGRES_REPOSITORY}.",
                   "Correct `pinned_commit:` to the commit of the raw/postgres-NN/ checkout the page cites.")
        record["checked"] = False
        return record
    record.update(checked=True, committed_at=postgres.info.get("committed_at"),
                  url=f"https://github.com/{POSTGRES_REPOSITORY}/commit/{pin}")

    configure_path = next((path for path in CONFIGURE_FILES if postgres.kind(path) == "file"), None)
    if configure_path:
        configure = postgres.read(configure_path)
        record["version_file"] = inputs.add("version", postgres, configure_path, configure)
        match = CONFIGURE_VERSION.search(configure)
        record["source_version"] = match.group(1).decode("ascii") if match else None
        if match and int(match.group(2)) != version:
            report.add("blocking", "source_version_mismatch",
                       f"Pinned commit {pin} is PostgreSQL {record['source_version']}, not {version}.",
                       f"Pin the page to a REL_{version}_STABLE commit, or correct its version.")
    if not record.get("source_version"):
        report.add("blocking", "source_version_unknown",
                   f"Cannot read the PostgreSQL version from configure.ac or configure.in at {pin}.",
                   "Check that `pinned_commit:` names a PostgreSQL source commit.")

    cited = [link for link in citations if link["postgres_version"] == version]
    files = sorted({link["source_path"] for link in cited if postgres.kind(link["source_path"]) == "file"})
    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
        contents = dict(zip(files, pool.map(postgres.read, files)))
    line_counts = {}
    for path in files:
        data = contents[path]
        line_counts[path] = data.count(b"\n") + (0 if not data or data.endswith(b"\n") else 1)
        record["files"].append(inputs.add("evidence", postgres, path, data) | {"lines": line_counts[path]})

    problems: dict[tuple[str, str], dict] = {}
    for link in cited:
        path, lines = link["source_path"], link.get("lines")
        kind = "directory" if path == "" else postgres.kind(path)
        link["exists"] = kind in ("file", "directory")
        code = None
        if kind is None:
            code = "evidence_missing"
        elif kind == "other":
            code = "evidence_not_regular"
        elif lines and (kind != "file" or not 1 <= lines[0] <= lines[1] <= line_counts[path]):
            code = "evidence_range_invalid"
        if code:
            problem = problems.setdefault((code, path), {"essential": False, "lines": [], "ranges": set()})
            problem["essential"] |= not link["reference_section"]
            problem["lines"].append(link["line"])
            if lines:
                problem["ranges"].add(f"L{lines[0]}-L{lines[1]}")
    for (code, path), problem in problems.items():
        severity = "blocking" if problem["essential"] else "warning"
        where = f"raw/postgres-{version}/{path}"
        if code == "evidence_missing":
            message = f"Cited file {where} does not exist at PostgreSQL commit {pin}."
        elif code == "evidence_not_regular":
            message = f"Cited path {where} is a symlink or submodule at PostgreSQL commit {pin}."
        else:
            size = f"{line_counts[path]} lines" if path in line_counts else "not a file"
            message = f"Cited range(s) {', '.join(sorted(problem['ranges']))} of {where} are invalid ({size})."
        if not problem["essential"]:
            message += " It is cited only in reference lists."
        report.add(severity, code, message,
                   "Correct the citation against the pinned checkout, or repin the page and recheck its claims.",
                   problem["lines"])
    return record


def _notes(document: dict, glossary: dict | None, postgres: dict, report: Report) -> None:
    glossary_pin = ((glossary or {}).get("pin_for_version") or {}).get("commit")
    if glossary_pin and postgres["commit"] and glossary_pin != postgres["commit"]:
        report.add("warning", "glossary_pin_differs",
                   f"The glossary checked PostgreSQL {postgres['version']} at {glossary_pin}, "
                   f"but this page cites {postgres['commit']}.",
                   "Confirm glossary definitions against the page's own pinned source during the cross-check.")
    if glossary and (glossary.get("front_matter") or {}).get("verified") is False:
        report.add("note", "glossary_unverified",
                   "The glossary declares `verified: false`. Its entries supply vocabulary, not proof; "
                   "narrated claims must rest on the document's matching-version citations.")
    if document.get("verification", {}).get("verified") is False:
        report.add("note", "document_unverified", "The document declares `verified: false`.")


def _update_manifest(root: Path, run_dir: Path, request: dict, *, status: str, record: dict | None = None,
                     inputs: list[dict] | None = None, error: str | None = None) -> dict:
    path = run_dir / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    manifest["request_id"] = request["request_id"]
    manifest["status"] = {"passed": "sources_ready"}.get(status, status)
    invalidate_after(manifest, "sources")
    sources: dict = {"status": status}
    if error:
        sources["error"] = error
    if record:
        postgres = record["postgres"]
        sources.update({
            "record": "sources.json",
            "report": "source-report.md",
            "retrieved_at": record["retrieved_at"],
            "wiki": record["wiki"],
            "postgres": {key: postgres.get(key) for key in
                         ("repository", "version", "commit", "committed_at", "source_version")},
            "document": {"path": record["document"]["path"], "url": record["document"]["url"],
                         "title": record["document"].get("title")},
            "inputs": [{key: entry[key] for key in
                        ("role", "repository", "commit", "path", "input", "size", "sha256", "git_blob_sha")}
                       for entry in inputs or []],
            "issues": {severity: sum(issue["severity"] == severity for issue in record["issues"])
                       for severity in Report.ORDER},
        })
    manifest["sources"] = sources
    write_atomic(root, run_dir.relative_to(root) / "manifest.json", _json_bytes(manifest), label="Request")
    return sources


def _json_bytes(data: dict) -> bytes:
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _render_report(record: dict) -> str:
    document, wiki, postgres, glossary = record["document"], record["wiki"], record["postgres"], record["glossary"]
    blocking = sum(issue["severity"] == "blocking" for issue in record["issues"])
    lines = [
        "# Source Snapshot Report", "",
        f"- Request: `{record['request_id']}`",
        f"- Status: **{record['status']}**" + (
            f": resolve {blocking} blocking issue(s) before narration." if blocking else ""),
        f"- Document: [`{document['path']}`]({document['url']}) at wiki commit `{wiki['commit']}` "
        f"(requested ref `{wiki['requested_ref']}`)",
    ]
    if document.get("title"):
        lines.append(f"- Title: {document['title']}")
    if postgres.get("commit"):
        version = f"PostgreSQL {postgres['version']}" if postgres.get("version") else "Unresolved version"
        source = f" (source reports {postgres['source_version']})" if postgres.get("source_version") else ""
        lines.append(f"- {version} source commit: `{postgres['commit']}`{source}, "
                     f"{len(postgres['files'])} cited file(s) retrieved from `{postgres['repository']}`")
    if glossary:
        verified = (glossary.get("front_matter") or {}).get("verified")
        lines.append(f"- Glossary: [`{glossary['path']}`]({glossary['url']}) at the same wiki commit, "
                     f"{glossary.get('term_count', 0)} terms, `verified: {json.dumps(verified)}`")
    for severity, heading in (("blocking", "Blocking Issues"), ("warning", "Warnings"), ("note", "Notes")):
        issues = [issue for issue in record["issues"] if issue["severity"] == severity]
        if not issues:
            continue
        lines += ["", f"## {heading}", ""]
        for issue in issues:
            where = ""
            if issue["lines"]:
                shown = ", ".join(map(str, issue["lines"][:10]))
                more = f" and {len(issue['lines']) - 10} more" if len(issue["lines"]) > 10 else ""
                where = f" (document line{'s' if len(issue['lines']) > 1 else ''} {shown}{more})"
            lines.append(f"- `{issue['code']}`{where}: {issue['message']}")
            if issue["action"]:
                lines.append(f"  Action: {issue['action']}")
    lines += ["", "## Inputs", "", "| Role | Repository | Path | Commit | SHA-256 |", "|---|---|---|---|---|"]
    entries = {(entry["repository"], entry["path"]): entry for entry in [
        document, glossary, *record["images"], postgres.get("version_file"), *postgres["files"]] if entry}
    for entry in entries.values():
        lines.append(f"| {entry['role']} | `{entry['repository']}` | [`{entry['path']}`]({entry['url']}) | "
                     f"`{entry['commit'][:12]}` | `{entry['sha256']}` |")
    return "\n".join(lines) + "\n"
