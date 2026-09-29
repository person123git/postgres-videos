"""Cross-check the document's subject and claims against the glossary (Step 6).

Inputs are the run's verified records: document.json, glossary-matches.json, and the
snapshot copies of the PostgreSQL files the document cites at its pinned commit. No
network and no language model are used; every comparison is deterministic.

Each matched glossary entry, each ambiguous term, and each concept the glossary lacks
gets a result: consistent, conflict, version_mismatch, ambiguous, or not_in_glossary.
Results compare the document with the statements that apply to its PostgreSQL
version: the entry's version scope from Step 5, configuration parameter facts
(context, default, minimum, and maximum), acronym expansions, and the role a sentence
gives a component ("`pg_stat_activity` is a view"). Glossary agreement is a
consistency result, not proof, because the glossary is unverified. Each narrated
sentence is therefore also checked against its own citations: its identifiers,
numeric code, and quoted strings must appear in the cited files at the pin.

A discrepancy that the pinned source settles is resolved, and when the document is
wrong the correction is recorded for the script; the snapshot is never changed.
Unresolved conflicts and version mismatches in narrated text, ambiguous central
terms, and unsupported central claims or concepts return needs_review. A reviewer
records resolutions in the run's resolutions.yaml, and `pgvideo resume` repeats this
check for the same request.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .document import (ABBREVIATIONS, CAMEL_CASE, CONSTANT, PROPER_NAMES, SNAKE_CASE, VERSION, _code_terms, _leaves,
                       _major, _snapshot_input)
from .glossary import ACRONYM, CODE_SPAN, NOTE, _alias, _fold, _plain
from .markdown import MarkdownError, _FrontMatterLoader
from .sources import POSTGRES_REPOSITORY, blob_url, write_atomic
from .stages import invalidate_after

SCHEMA_VERSION = 1
RESULTS = ("consistent", "conflict", "version_mismatch", "ambiguous", "not_in_glossary")
# Worst first: an entry's overall result is the worst result among its checks.
WORST = ("conflict", "version_mismatch", "ambiguous", "not_in_glossary", "consistent")
SEVERITIES = ("blocking", "warning", "note")
CLAIM_STATUSES = ("verified", "supported", "cited", "unconfirmed", "uncited")
RESOLUTIONS = "resolutions.yaml"
MAX_RESOLUTIONS_BYTES = 1024 * 1024
# Coverage decisions whose sections reach the narration or the screen.
NARRATED = ("explain", "summarize")
# Section roles whose sentences are claims; the question and open questions are not.
CLAIM_ROLES = ("summary", "content")
PASSAGE_SAMPLE = 5
# A passage longer than this, such as a whole code block, is cut to the line or window around its match.
PASSAGE_CHARS = 400
# Citations listed per claim; a section's citations can number in the dozens.
CITATION_SAMPLE = 8
# Where an item was found in the pinned evidence, strongest first: the cited lines, the rest of a cited
# file, or another file the document cites. Each level tries an exact match, then a case-insensitive one.
FOUND = ("range", "file", "evidence")
# Decisions a reviewer may record for each kind of result, and which of them need evidence.
DECISIONS = {
    "conflict": ("use_document", "use_glossary", "omit"),
    "version_mismatch": ("use_document", "omit"),
    "ambiguous": ("choose_entry", "use_document", "omit"),
    "not_in_glossary": ("use_document", "omit"),
    "claim": ("use_document", "omit"),
}
EVIDENCE_DECISIONS = {"use_document", "use_glossary"}
EVIDENCE_REFERENCE = re.compile(
    r"(?:https://github\.com/postgres/postgres/blob/(?P<commit>[0-9a-f]{40})/|raw/postgres-(?P<version>\d+)/)?"
    r"(?P<path>[\w.+-]+(?:/[\w.+-]+)*)(?:#L(?P<start>\d+)(?:-L(?P<end>\d+))?)?")

# Configuration parameters: contexts, and how the pinned GUC tables record them.
CONTEXTS = {"PGC_INTERNAL": "internal", "PGC_POSTMASTER": "postmaster", "PGC_SIGHUP": "sighup",
            "PGC_SU_BACKEND": "superuser-backend", "PGC_BACKEND": "backend", "PGC_SUSET": "superuser",
            "PGC_USERSET": "user"}
GUC_TABLES = ("src/backend/utils/misc/guc_tables.c", "src/backend/utils/misc/guc.c")
GUC_DATA = "src/backend/utils/misc/guc_parameters.dat"
GUC_SAMPLE = "src/backend/utils/misc/postgresql.conf.sample"
GUC_ARRAY = re.compile(r"\bstruct\s+config_(bool|int|real|string|enum)\s+ConfigureNames\w*\s*\[\]")
GUC_ENTRY = re.compile(r'\{\s*"([A-Za-z_][\w.]*)"\s*,\s*(PGC_[A-Z_]+)\s*,')
GUC_VARIABLE = re.compile(r"&\s*[A-Za-z_][\w.>-]*\s*,")
GUC_RECORD = re.compile(r"\{[^{}]*\}")
GUC_FIELD = re.compile(r"(\w+)\s*=>\s*(?:'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\")")
GUC_SAMPLE_LINE = re.compile(r"(?m)^#?([a-z_][a-z0-9_]*)\s*=\s*('[^'\n]*'|[^\s#]+)")
VALUE_COUNTS = {"bool": 1, "string": 1, "enum": 1, "int": 3, "real": 3}
# Units of GUC_UNIT_* flags; block sizes assume the default 8 kB BLCKSZ and XLOG_BLCKSZ.
UNIT_FLAGS = {"GUC_UNIT_BYTE": ("memory", 1, "bytes"), "GUC_UNIT_KB": ("memory", 1024, "kB"),
              "GUC_UNIT_MB": ("memory", 1024 ** 2, "MB"), "GUC_UNIT_BLOCKS": ("memory", 8192, "8 kB blocks"),
              "GUC_UNIT_XBLOCKS": ("memory", 8192, "8 kB WAL blocks"), "GUC_UNIT_MS": ("time", 1, "ms"),
              "GUC_UNIT_S": ("time", 1000, "s"), "GUC_UNIT_MIN": ("time", 60000, "min")}
TEXT_UNITS = {name: (dimension, factor, label) for names, dimension, factor, label in (
    (("B", "byte", "bytes"), "memory", 1, "bytes"),
    (("kB", "KB", "KiB", "kilobyte", "kilobytes"), "memory", 1024, "kB"),
    (("MB", "MiB", "megabyte", "megabytes"), "memory", 1024 ** 2, "MB"),
    (("GB", "GiB", "gigabyte", "gigabytes"), "memory", 1024 ** 3, "GB"),
    (("TB", "TiB", "terabyte", "terabytes"), "memory", 1024 ** 4, "TB"),
    (("ms", "millisecond", "milliseconds"), "time", 1, "ms"),
    (("s", "sec", "secs", "second", "seconds"), "time", 1000, "s"),
    (("min", "mins", "minute", "minutes"), "time", 60000, "min"),
    (("h", "hour", "hours"), "time", 3600000, "h"),
    (("d", "day", "days"), "time", 86400000, "d"),
    # Assumes the default 8 kB BLCKSZ, as the GUC_UNIT_BLOCKS flag does.
    (("block", "blocks", "page", "pages", "buffer", "buffers"), "memory", 8192, "8 kB blocks"),
) for name in names}
SYMBOL_VALUES = {"INT_MAX": 2147483647}
BOOLS = {"on": "on", "true": "on", "enabled": "on", "off": "off", "false": "off", "disabled": "off"}

# Facts in prose. Keywords must be outside inline code; a word value must be inline code or a boolean.
_UNIT = "|".join(sorted(map(re.escape, TEXT_UNITS), key=len, reverse=True))
_NUMBER = r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
VALUE = rf"(?:(?P<number>{_NUMBER})(?:\s?(?P<unit>{_UNIT})(?![\w-]))?|(?P<word>[A-Za-z_][\w-]*))"
PGC = re.compile(r"\bPGC_(?:INTERNAL|POSTMASTER|SIGHUP|SU_BACKEND|BACKEND|SUSET|USERSET)\b")
_CONTEXT_NAME = r"(?P<name>superuser-backend|internal|postmaster|sighup|backend|superuser|user)"
CONTEXT_BEFORE = re.compile(rf"(?i:\bcontext\b(?:\s+(?:is|of|was))?(?:\s+still)?\s+){_CONTEXT_NAME}(?![\w-])")
CONTEXT_AFTER = re.compile(rf"(?<![\w-]){_CONTEXT_NAME}\s+(?i:context)\b")
DEFAULT = re.compile(rf"(?i:\bdefaults?\b(?:\s+value)?(?:\s+(?:is|was|of|to)|\s*[:=])?\s+(?:set\s+to\s+)?){VALUE}")
DEFAULT_AFTER = re.compile(rf"{VALUE}\s*\((?i:the\s+)?(?i:default)\)")
DEFAULT_BY = re.compile(r"(?i)\b(?P<word>enabled|disabled|on|off)\s+by\s+default\b")
MINMAX = re.compile(rf"(?i:\b(?P<which>minimum|maximum|min|max)\b(?:\s+value)?(?:\s+(?:is|of)|\s*[:=])?\s+){VALUE}")
RANGE = re.compile(
    rf"(?i:\b(?:accepts|allows|ranges?\s+from|(?:valid|allowed)?\s*range\s+(?:is\s+|of\s+)(?:from\s+)?)\s*)"
    rf"(?P<low>{_NUMBER})(?:\s?(?P<lowunit>{_UNIT}))?"
    rf"\s*(?i:to|and|through|–|-)\s*(?P<high>{_NUMBER})(?:\s?(?P<unit>{_UNIT})(?![\w-]))?")
# Parameters or values joined into a list, whose facts cannot be paired reliably.
COORDINATED = re.compile(r"\s*(?:,\s*)?(?:and|or|&|,)\s*(?:the\s+)?")
VALUE_LIST = re.compile(rf"\s*(?:,|and\b|or\b)\s*(?:{_NUMBER}|on\b|off\b)")
# A sentence that refers back to the setting the document is about.
PRONOUN = re.compile(r"^\W*(?:It|Its|This|These|(?:The|This)\s+(?:setting|parameter|GUC|option|value))\b")
IDENTIFIER_TOKEN = re.compile(r"(?<![\w$.])[A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)*(?:\(\))?(?![\w$])")
IDENTIFIER_SHAPE = re.compile(r"_|\d|[a-z][A-Z]|\.")

# Roles in "X is a view" sentences, grouped into classes that must agree.
ROLE_CLASSES = {
    "guc": "setting", "setting": "setting", "parameter": "setting", "view": "view", "function": "function",
    "process": "process", "backend": "process", "worker": "process", "catalog": "catalog", "extension": "extension",
    "module": "extension", "struct": "struct", "structure": "struct", "macro": "macro", "hook": "hook",
    "column": "column", "table": "table", "variable": "variable", "lock": "lock",
}
ROLE = re.compile(
    r"^\W*(?:(?:the|a|an)\s+)?(?P<subject>`[^`]+`|[A-Za-z][\w/-]*(?:\s+[A-Za-z][\w/-]*){0,3}?)"
    r"\s+(?:itself\s+|also\s+|still\s+)?(?:is|are)\s+(?:a|an|the|one)\s+(?P<words>(?:[\w-]+\s+){0,3}?)"
    r"(?P<role>" + "|".join(sorted(ROLE_CLASSES, key=len, reverse=True)) + r")s?\b(?!['’])", re.IGNORECASE)
ACRONYM_AFTER = re.compile(r"\((?P<acronym>[A-Z][A-Za-z0-9/&-]*[A-Z0-9])s?\)")
ACRONYM_BEFORE = re.compile(r"(?<![\w/-])(?P<acronym>[A-Z][A-Z0-9/&-]*[A-Z0-9])s?\s+\((?P<long>[^()]{3,80})\)")
# Words that mark a sentence as describing another version or the past.
HISTORICAL = re.compile(
    r"(?i)\b(?:gone|removed|replaced|no longer|formerly|previously|used to|older|earlier|legacy|obsolete"
    r"|renamed|before PostgreSQL|until PostgreSQL|prior to|pre-\d+)\b")
SENTENCE_END = re.compile(r"[.!?][\"')\]]*\s+(?=[A-Z0-9`\"'(\[])")
# An identifier the sentence says is absent: "PostgreSQL 18 has no dedicated `vacuum_hook`".
NEGATION = re.compile(r"(?i)\b(?:no|not|never|without|neither|nor|lacks?|absent)\b[^.;:!?]{0,40}$")
WILDCARD = re.compile(r"[A-Za-z_][\w$]*\*[\w$*]*|\*[A-Za-z_][\w$]*")
GIT_REF = re.compile(r"REL_?\d+(?:_\d+)*(?:_(?:STABLE|BETA\d*|RC\d*|ALPHA\d*))?(?:-[\w.-]+)?")
PLATFORMS = {"x86_64", "x86", "i386", "i686", "amd64", "arm64", "aarch64", "ppc64", "ppc64le", "s390x", "riscv64",
             "win32", "win64", "x64"}
COMMIT_HASH = re.compile(r"(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}")


def check_glossary(root: Path, run_dir: Path) -> dict:
    """Write glossary-check.json and glossary-check.md for a run whose glossary matches passed.

    Applies the run's resolutions.yaml when it exists. Returns the manifest's
    record, whose status is 'passed' or 'needs_review'. A missing or altered
    input, or an invalid resolution, marks the manifest 'failed' and raises.
    """
    try:
        return _check(root, run_dir)
    except (ValueError, OSError) as error:
        _update_manifest(root, run_dir, status="failed", error=str(error))
        raise


def _check(root: Path, run_dir: Path) -> dict:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    for stage, report in (("sources", "source-report.md"), ("document", "coverage.md"),
                          ("glossary", "glossary-matches.json")):
        if (manifest.get(stage) or {}).get("status") != "passed":
            raise ValueError(f"The {stage} stage has status '{(manifest.get(stage) or {}).get('status')}'; "
                             f"resolve {report} first.")
    document = json.loads(_recorded(run_dir, "document.json", manifest["document"]))
    matches = json.loads(_recorded(run_dir, "glossary-matches.json", manifest["glossary"]))
    sources = json.loads((run_dir / "sources.json").read_text(encoding="utf-8"))
    evidence = _Evidence(root, run_dir, sources, document)
    resolutions = _load_resolutions(run_dir)
    checker = _Checker(document, matches, evidence)
    record = checker.build()
    checker.resolve(record, resolutions)
    checker.finish(record)
    relative = run_dir.relative_to(root)
    data = (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    write_atomic(root, relative / "glossary-check.json", data, label="Request")
    write_atomic(root, relative / "glossary-check.md", _render(record).encode("utf-8"), label="Request")
    return _update_manifest(root, run_dir, status=record["status"], record=record,
                            digest=hashlib.sha256(data).hexdigest())


def _recorded(run_dir: Path, name: str, stage: dict) -> bytes:
    data = (run_dir / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != stage.get("sha256"):
        raise ValueError(f"{name} does not match the SHA-256 recorded in manifest.json.")
    return data


# Evidence ----------------------------------------------------------------------------------------


class _Evidence:
    """The document's cited PostgreSQL files at its pinned commit, from the run's verified copies."""

    def __init__(self, root: Path, run_dir: Path, sources: dict, document: dict):
        postgres = sources.get("postgres") or {}
        self.version = document["document"]["version"]
        self.pin = postgres.get("commit")
        self.links = {link["id"]: link for link in document["links"]}
        self.lines: dict[str, list[str]] = {}
        self.text: dict[str, str] = {}
        for entry in [*postgres.get("files", []), *filter(None, [postgres.get("version_file")])]:
            text = _snapshot_input(root, run_dir, entry).decode("utf-8", errors="replace")
            self.text[entry["path"]], self.lines[entry["path"]] = text, text.split("\n")
        self.lowered = {path: text.lower() for path, text in self.text.items()}
        self.settings = _pinned_settings(self)

    def url(self, path: str, lines=None) -> str | None:
        if not self.pin:
            return None
        return blob_url(POSTGRES_REPOSITORY, self.pin, path, tuple(lines) if lines else None)

    def cited(self, link_ids) -> list[dict]:
        """Return the citations into the document's own version's source tree."""
        found = []
        for number in link_ids:
            link = self.links.get(number)
            if (link and link.get("kind") == "citation" and link.get("postgres_version") == self.version
                    and link.get("source_path")):
                found.append({"path": link["source_path"], "lines": link.get("lines"), "url": link.get("url")})
        return list({(c["path"], tuple(c["lines"] or ())): c for c in found}.values())

    def find(self, item: dict, cited: list[dict]) -> dict:
        """Find an item in the cited lines, the rest of the cited files, then the other evidence files.

        Each level tries an exact match first and then a case-insensitive one bounded by
        non-alphanumerics, so `track_activity_query_size` is found inside the C variable
        `pgstat_track_activity_query_size`.
        """
        # Each pattern carries a fixed substring, checked first because most files lack it.
        patterns = [(item["pattern"], item["needle"], True)]
        if item.get("loose"):
            patterns.append((item["loose"], item["needle"].lower(), False))
        available = [c for c in cited if c["path"] in self.lines]
        for pattern, needle, exact in patterns:
            for citation in available:
                if citation["lines"]:
                    first, last = citation["lines"]
                    segment = "\n".join(self.lines[citation["path"]][first - 1:last])
                    segment = segment if exact else segment.lower()
                    if needle in segment and (match := pattern.search(segment)):
                        return self._found("range", exact, citation["path"],
                                           first + segment.count("\n", 0, match.start()))
        paths = list(dict.fromkeys(c["path"] for c in available))
        others = [path for path in self.text if path not in paths]
        for level, candidates in (("file", paths), ("evidence", others)):
            for pattern, needle, exact in patterns:
                for path in candidates:
                    text = self.text[path] if exact else self.lowered[path]
                    if needle in text and (match := pattern.search(text)):
                        return self._found(level, exact, path, text.count("\n", 0, match.start()) + 1)
        return {"level": None}

    def _found(self, level: str, exact: bool, path: str, line: int) -> dict:
        return {"level": level, "exact": exact, "path": path, "line": line, "url": self.url(path, (line, line))}


def _item(text: str, kind: str) -> dict:
    """Compile how an item is searched: a number, a quoted string, or an identifier.

    An identifier may be a pattern, such as `pg_analyze_and_rewrite_*`, or a fragment
    such as `shared_blk_` or `_ext` that another name completes.
    """
    needle = max(text.split("*"), key=len)
    if kind == "number":
        pattern = re.compile(rf"(?<![\w.]){re.escape(text)}(?![\w]|\.\d)")
        return {"text": text, "kind": kind, "pattern": pattern, "needle": needle}
    if kind == "literal":
        return {"text": text, "kind": kind, "pattern": re.compile(re.escape(text)), "needle": needle,
                "loose": re.compile(rf"(?<![a-z0-9]){re.escape(text.lower())}(?![a-z0-9])")}

    def compile_(name: str, boundary: str) -> str:
        body = r"[\w$]*".join(re.escape(piece) for piece in name.split("*"))
        before = "" if name.startswith(("_", "*")) else rf"(?<!{boundary})"
        after = "" if name.endswith(("_", "*")) else rf"(?!{boundary})"
        return before + body + after

    return {"text": text, "kind": kind, "needle": needle, "pattern": re.compile(compile_(text, r"[\w$]")),
            "loose": re.compile(compile_(text.lower(), r"[a-z0-9]"))}


def _items(text: str) -> list[dict]:
    """Return what a sentence's citations should contain: identifiers, numeric code, and quoted strings."""
    found: dict[tuple[str, str], dict] = {}

    def add(name: str, kind: str) -> None:
        if (name and (name, kind) not in found and not COMMIT_HASH.fullmatch(name) and not GIT_REF.fullmatch(name)
                and name.lower() not in PLATFORMS):
            found[name, kind] = _item(name, kind)

    for match in CODE_SPAN.finditer(text):
        code = match.group(2).strip()
        if re.fullmatch(r"-?\d+(?:\.\d+)?", code):
            add(code.lstrip("-"), "number")
            continue
        for literal in re.findall(r'"([^"\n]{3,80})"', code):
            # An elided message such as "entry already dropped: ..." is searched by its longest part.
            piece = max(literal.split("..."), key=len).strip()
            if len(piece) >= 3:
                add(piece, "literal")
        code = re.sub(r'"[^"\n]*"', " ", code)
        for wildcard in WILDCARD.findall(code):
            if IDENTIFIER_SHAPE.search(wildcard.replace("*", "")):
                add(wildcard, "identifier")
        for name, kind in _code_terms(WILDCARD.sub(" ", code)):
            name = name.removesuffix("()")
            if kind == "qualified_name":
                for part in name.split("."):
                    if IDENTIFIER_SHAPE.search(part):
                        add(part, "identifier")
            elif kind in ("function", "identifier", "constant") and IDENTIFIER_SHAPE.search(name):
                add(name, "identifier")
    prose = CODE_SPAN.sub(" ", text)
    for pattern in (SNAKE_CASE, CAMEL_CASE, CONSTANT):
        for match in pattern.finditer(prose):
            name = match.group(0).removesuffix("()")
            if name not in PROPER_NAMES:
                add(name, "identifier")
    return list(found.values())


# Pinned configuration parameters --------------------------------------------------------------


def _pinned_settings(evidence: _Evidence) -> dict[str, dict]:
    """Parse the context, default, and limits of each parameter in the cited GUC sources."""
    settings: dict[str, dict] = {}
    for path in GUC_TABLES:
        if path in evidence.text:
            for name, record in _guc_table(path, evidence.text[path]).items():
                settings.setdefault(name, record)
    if GUC_DATA in evidence.text:
        for name, record in _guc_data(GUC_DATA, evidence.text[GUC_DATA]).items():
            settings.setdefault(name, record)
    if GUC_SAMPLE in evidence.text:
        text = evidence.text[GUC_SAMPLE]
        for match in GUC_SAMPLE_LINE.finditer(text):
            name = match.group(1)
            if name not in settings:
                value = _sample_value(match.group(2))
                settings[name] = {"name": name, "path": GUC_SAMPLE, "line": text.count("\n", 0, match.start()) + 1,
                                  "type": None, "unit": None, **({"default": value} if value else {})}
    for record in settings.values():
        record["url"] = evidence.url(record["path"], (record["line"], record["line"]))
    return settings


def _guc_table(path: str, text: str) -> dict[str, dict]:
    arrays = [(match.start(), match.group(1)) for match in GUC_ARRAY.finditer(text)]
    entries = list(GUC_ENTRY.finditer(text))
    found = {}
    for number, match in enumerate(entries):
        name, context = match.groups()
        kind = next((kind for start, kind in reversed(arrays) if start < match.start()), None)
        limit = entries[number + 1].start() if number + 1 < len(entries) else len(text)
        variable = GUC_VARIABLE.search(text, match.end(), limit)
        if kind is None or context not in CONTEXTS or variable is None:
            continue
        end = text.find("}", variable.end(), limit)
        values = _split_values(text[variable.end():end if end >= 0 else limit])
        unit = next((flag for flag in re.findall(r"GUC_UNIT_\w+", text[match.end():variable.start()])
                     if flag in UNIT_FLAGS), None)
        record = {"name": name, "type": kind, "context": {"kind": "context", "value": CONTEXTS[context]},
                  "context_symbol": context, "unit": unit, "path": path,
                  "line": text.count("\n", 0, match.start()) + 1}
        for attribute, raw in zip(("default", "min", "max")[:VALUE_COUNTS[kind]], values):
            record[attribute] = _source_value(raw, kind, unit)
        if kind == "enum" and len(values) > 1 and record["default"]["kind"] == "enum":
            record["default"]["names"] = _enum_names(text, values[1], record["default"]["value"])
        found.setdefault(name, record)
    return found


def _enum_names(text: str, options: str, constant: str) -> list[str] | None:
    """Return the spellings an enum options table accepts for one constant, or None if it is not in the file."""
    table = re.search(rf"\b{re.escape(options)}\s*\[\]\s*=\s*\{{(.*?)\}};", text, re.DOTALL)
    if not table:
        return None
    return [name.lower() for name, value in re.findall(r'\{\s*"([^"]+)"\s*,\s*([A-Za-z_]\w*)\s*,', table.group(1))
            if value == constant]


def _guc_data(path: str, text: str) -> dict[str, dict]:
    found = {}
    for match in GUC_RECORD.finditer(text):
        fields = {field.group(1): field.group(2) if field.group(2) is not None else field.group(3)
                  for field in GUC_FIELD.finditer(match.group(0))}
        name, kind, context = fields.get("name"), fields.get("type"), fields.get("context")
        if not name or kind not in VALUE_COUNTS or context not in CONTEXTS:
            continue
        unit = next((flag for flag in re.findall(r"GUC_UNIT_\w+", fields.get("flags", "")) if flag in UNIT_FLAGS),
                    None)
        record = {"name": name, "type": kind, "context": {"kind": "context", "value": CONTEXTS[context]},
                  "context_symbol": context, "unit": unit, "path": path,
                  "line": text.count("\n", 0, match.start()) + 1}
        for attribute, key in (("default", "boot_val"), ("min", "min"), ("max", "max")):
            if key in fields:
                raw = fields[key] if kind != "string" else json.dumps(fields[key])
                record[attribute] = _source_value(raw, kind, unit)
        found.setdefault(name, record)
    return found


def _split_values(text: str) -> list[str]:
    """Split C initializer values at top-level commas."""
    values, current, depth, quote = [], "", 0, None
    for character in text:
        if quote:
            quote = None if character == quote and not current.endswith("\\") else quote
        elif character in "\"'":
            quote = character
        elif character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        elif character == "," and depth == 0:
            values.append(current.strip())
            current = ""
            continue
        current += character
    if current.strip():
        values.append(current.strip())
    return values


def _source_value(raw: str, kind: str, unit: str | None) -> dict:
    raw = raw.strip()
    if kind == "bool" and raw in ("true", "false"):
        return {"kind": "bool", "value": BOOLS[raw], "raw": raw}
    if kind in ("int", "real"):
        number = _arithmetic(raw)
        if number is not None:
            dimension, factor, label = UNIT_FLAGS.get(unit, (None, None, None))
            return {"kind": "number", "value": number, "unit": label, "dimension": dimension, "factor": factor,
                    "raw": raw}
    if kind == "enum" and re.fullmatch(r"[A-Za-z_]\w*", raw):
        return {"kind": "enum", "value": raw, "raw": raw}
    if kind == "string" and re.fullmatch(r'"(?:[^"\\]|\\.)*"', raw):
        return {"kind": "word", "value": raw[1:-1], "raw": raw}
    return {"kind": "symbol", "value": raw, "raw": raw}


def _arithmetic(text: str) -> int | float | None:
    """Evaluate a C constant expression of numbers and INT_MAX; return None for anything else."""
    text = re.sub(r"\b(\d+(?:\.\d+)?)[uUlLfF]+\b", r"\1", text)
    for symbol, value in SYMBOL_VALUES.items():
        text = re.sub(rf"\b{symbol}\b", str(value), text)
    try:
        tree = ast.parse(text, mode="eval").body
    except SyntaxError:
        return None

    def value(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            operand = value(node.operand)
            return None if operand is None else -operand if isinstance(node.op, ast.USub) else operand
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left, right = value(node.left), value(node.right)
            if left is None or right is None or (isinstance(node.op, ast.Div) and right == 0):
                return None
            if isinstance(node.op, ast.Div):
                return left // right if isinstance(left, int) and isinstance(right, int) else left / right
            return {ast.Add: left + right, ast.Sub: left - right, ast.Mult: left * right}[type(node.op)]
        return None

    return value(tree)


def _sample_value(raw: str) -> dict | None:
    raw = raw.strip("'")
    match = re.fullmatch(rf"(?P<number>{_NUMBER})\s?(?P<unit>{_UNIT})?", raw)
    if match:
        return _number(match.group("number"), match.group("unit"), raw)
    return {"kind": "bool", "value": BOOLS[raw.lower()], "raw": raw} if raw.lower() in BOOLS else None


def _number(number: str, unit: str | None, raw: str) -> dict:
    digits = number.replace(",", "")
    value = float(digits) if "." in digits else int(digits)
    dimension, factor, label = TEXT_UNITS.get(unit or "", (None, None, None))
    return {"kind": "number", "value": value, "unit": label, "dimension": dimension, "factor": factor, "raw": raw}


def _same(left: dict | None, right: dict | None) -> bool | None:
    """Compare two parameter values; None when they cannot be compared."""
    if not left or not right or "symbol" in (left["kind"], right["kind"]):
        return None
    kinds = {left["kind"], right["kind"]}
    if kinds == {"number"}:
        if left["dimension"] and right["dimension"]:
            if left["dimension"] != right["dimension"]:
                return None
            return math.isclose(left["value"] * left["factor"], right["value"] * right["factor"], rel_tol=1e-9)
        # A number without a unit is in the parameter's own unit.
        return math.isclose(left["value"], right["value"], rel_tol=1e-9)
    if len(kinds) == 1 and kinds <= {"bool", "context"}:
        return left["value"] == right["value"]
    if "enum" in kinds:
        enum = left if left["kind"] == "enum" else right
        other = right if enum is left else left
        if other["kind"] not in ("word", "bool"):
            return None
        spellings = {other["value"].lower(), str(other.get("raw", "")).strip("`'\"").lower()}
        if enum.get("names") is not None:
            return bool(spellings & set(enum["names"]))
        constant = enum["value"].lower()
        # Without the options table, only a matching constant suffix such as COMPUTE_QUERY_ID_AUTO counts.
        return True if any(constant.endswith("_" + word.replace("-", "_")) for word in spellings if word) else None
    if kinds == {"word"}:
        return left["value"].lower() == right["value"].lower()
    return None


def _in_unit(value: dict | None, source: dict | None) -> dict | None:
    """Give a number stated without a unit the unit of the pinned parameter, such as 16384 8 kB blocks."""
    if (value and source and value["kind"] == "number" == source["kind"] and not value.get("dimension")
            and source.get("dimension")):
        return value | {key: source[key] for key in ("dimension", "factor", "unit")}
    return value


def _display(value: dict | None) -> str:
    if not value:
        return "—"
    if value["kind"] == "number":
        number = f"{value['value']:g}" if isinstance(value["value"], float) else str(value["value"])
        # Negative values such as -1 mean "disabled" or "use another setting", not an amount.
        return f"{number} {value['unit']}" if value.get("unit") and value["value"] >= 0 else number
    if value["kind"] == "enum":
        return f"`{value['value']}`"
    return f"`{value['value']}`" if value["kind"] in ("word", "symbol") else value["value"]


# Facts in prose ---------------------------------------------------------------------------------


def _sentence_facts(plain: str, spans: list[tuple[int, int]]) -> list[dict]:
    """Return the configuration facts a sentence states: context, default, minimum, and maximum."""

    def code(start: int, end: int) -> bool:
        return any(a <= start and end <= b for a, b in spans)

    def value(match: re.Match) -> dict | None:
        number, word = match.group("number"), match.group("word")
        if number is not None:
            end = match.end("unit") if match.group("unit") else match.end("number")
            return _number(number, match.group("unit"), plain[match.start("number"):end])
        if word and word.lower() in BOOLS:
            return {"kind": "bool", "value": BOOLS[word.lower()], "raw": word}
        if word and code(*match.span("word")):
            return {"kind": "word", "value": word, "raw": word}
        return None

    facts = []

    def add(attribute: str, found: dict | None, match: re.Match, keyword: int) -> None:
        if found and not code(keyword, keyword + 1):
            facts.append({"attribute": attribute, "value": found, "raw": match.group(0).strip(),
                          "start": match.start(), "end": match.end()})

    for match in PGC.finditer(plain):
        facts.append({"attribute": "context", "value": {"kind": "context", "value": CONTEXTS[match.group(0)]},
                      "raw": match.group(0), "start": match.start(), "end": match.end()})
    for pattern in (CONTEXT_BEFORE, CONTEXT_AFTER):
        for match in pattern.finditer(plain):
            if code(*match.span("name")):
                keyword = match.start() if pattern is CONTEXT_BEFORE else match.end() - 1
                add("context", {"kind": "context", "value": match.group("name").lower(), "raw": match.group("name")},
                    match, keyword)
    for match in DEFAULT.finditer(plain):
        add("default", value(match), match, match.start())
    for match in DEFAULT_AFTER.finditer(plain):
        add("default", value(match), match, plain.index("(", match.start()))
    for match in DEFAULT_BY.finditer(plain):
        add("default", {"kind": "bool", "value": BOOLS[match.group("word").lower()], "raw": match.group("word")},
            match, match.end() - 1)
    for match in MINMAX.finditer(plain):
        if match.group("number") is not None:
            add("min" if match.group("which").lower().startswith("min") else "max", value(match), match,
                match.start())
    for match in RANGE.finditer(plain):
        unit = match.group("unit")
        add("min", _number(match.group("low"), match.group("lowunit") or unit, match.group("low")), match,
            match.start())
        add("max", _number(match.group("high"), unit, plain[match.start("high"):match.end()].strip()), match,
            match.start())
    unique = {}
    for fact in sorted(facts, key=lambda f: (f["start"], -f["end"])):
        unique.setdefault((fact["attribute"], fact["start"]), fact)
    return list(unique.values())


def _sentences(text: str) -> list[str]:
    """Split display text into sentences outside inline code."""
    spans = [match.span() for match in CODE_SPAN.finditer(text)]
    pieces, start = [], 0
    for match in SENTENCE_END.finditer(text):
        if any(a <= match.start() < b for a, b in spans):
            continue
        word = re.search(r"(\S+)$", text[start:match.start()])
        if word and word.group(1).lower().lstrip("([\"'") in ABBREVIATIONS:
            continue
        pieces.append(text[start:match.end()].strip())
        start = match.end()
    if text[start:].strip():
        pieces.append(text[start:].strip())
    return pieces


def _note_body(text: str | None) -> str:
    match = NOTE.match(text or "")
    return match.group(3).strip() if match else (text or "").strip()


def _expands(short: str, long: str) -> int | None:
    """Return where `long` starts to spell the acronym `short` (Schwartz and Hearst), or None."""
    letters = [c.lower() for c in short if c.isalnum()]
    position = len(long) - 1
    for index in range(len(letters) - 1, -1, -1):
        character = letters[index]
        while position >= 0 and (long[position].lower() != character
                                 or (index == 0 and position > 0 and long[position - 1].isalnum())):
            position -= 1
        if position < 0:
            return None
        position -= 1
    return position + 1


def _expansion_key(text: str) -> list[str]:
    words = re.sub(r"[^\w/ ]", " ", text.lower().replace("-", " ")).split()
    return [word[:-1] if len(word) > 3 and word.endswith("s") else word for word in words]


def _same_expansion(left: str, right: str) -> bool:
    """Compare expansions word by word, allowing plurals, word stems, and one extra inner word."""
    a, b = sorted((_expansion_key(left), _expansion_key(right)), key=len)

    def same(x: str, y: str) -> bool:
        return x == y or (min(len(x), len(y)) >= 3 and (x.startswith(y) or y.startswith(x)))

    if len(a) == len(b):
        return all(same(x, y) for x, y in zip(a, b))
    return (len(b) - len(a) == 1 and len(a) >= 2 and same(a[0], b[0]) and same(a[-1], b[-1])
            and any(all(same(x, y) for x, y in zip(a, b[:n] + b[n + 1:])) for n in range(1, len(b) - 1)))


def _role(text: str | None) -> dict | None:
    match = ROLE.match(text or "")
    if not match:
        return None
    return {"subject": _subject_key(match.group("subject")), "role": ROLE_CLASSES[match.group("role").lower()],
            "word": match.group("role").lower(), "text": match.group(0)}


def _subject_key(text: str) -> str:
    return _fold(text.replace("`", "").removesuffix("()"))


def _qualified(text: str, version: int | None) -> bool:
    """Return whether a sentence scopes itself to another version or to the past."""
    plain, _spans = _plain(text)
    # Numbers are read directly from each version mention, so "v13" counts as well as "PostgreSQL 13".
    others = {_major(number) for match in VERSION.finditer(plain)
              for number in re.findall(r"(?<![\d.])\d{1,2}(?:\.\d{1,2})?(?![\d])", match.group(0))}
    return bool(others - {None, str(version)}) or bool(HISTORICAL.search(plain))


def _negated(text: str, name: str) -> bool:
    """Return whether every mention of `name` in display text follows a negation in the same clause."""
    plain, _spans = _plain(text)
    mentions = list(re.finditer(rf"(?<![\w$]){re.escape(name)}(?![\w$])", plain))
    return bool(mentions) and all(NEGATION.search(plain[max(0, m.start() - 60):m.start()]) for m in mentions)


# Checker ----------------------------------------------------------------------------------------


class _Checker:
    """Build the results, claims, corrections, and exceptions for one document."""

    def __init__(self, document: dict, matches: dict, evidence: _Evidence):
        self.document = document
        self.matches = matches
        self.evidence = evidence
        self.version = document["document"]["version"]
        self.by_anchor = {match["anchor"]: match for match in matches["matches"]}
        self.decisions = {entry["section"]: entry["decision"] for entry in document["coverage"]["sections"]}
        self.conclusions = {sentence["id"] for sentence in document["conclusions"]["sentences"]}
        question = document["subject"].get("question") or {}
        self.question = {*question.get("sentences", []), *question.get("blocks", [])}
        self.units, self.texts = self._units()
        # The asker's own wording, such as an example function name, is not a claim about PostgreSQL's source.
        self.question_text = "\n".join(
            block.get("content") or " ".join(s["text"] for s in block.get("sentences", []))
            for section in document["sections"] if section["role"] == "question"
            for block in _leaves(section["blocks"]))
        self.example_text = "\n".join(block["content"] for section in document["sections"]
                                      for block in _leaves(section["blocks"]) if block["type"] == "code")
        self.section_citations = {section["id"]: [c for block in _leaves(section["blocks"]) for c in (
            block.get("citations", []) + [c for row in block.get("rows", []) for cell in row["cells"]
                                          for c in cell["citations"]])] for section in document["sections"]}
        self.settings = set(evidence.settings) | {term["term"] for term in document["terms"]
                                                  if term["kind"] == "setting"}
        focus = [term for term in document["subject"]["focus_terms"] if term in self.settings]
        self.focus_setting = focus[0] if len(set(focus)) == 1 else None
        self.results: list[dict] = []
        self.corrections: list[dict] = []
        self.exceptions: list[dict] = []
        self.omissions: list[dict] = []

    def _units(self) -> tuple[dict[str, dict], dict[str, str]]:
        """Return the narrated sentences and displayed table rows, and the text of every unit ID."""
        units, texts = {}, {}
        for section in self.document["sections"]:
            decision = self.decisions.get(section["id"])
            if section["text"]:
                texts[section["id"]] = section["text"]
            for block in _leaves(section["blocks"]):
                base = {"section": section["id"], "role": section["role"], "decision": decision, "block": block["id"]}
                if block["type"] == "code":
                    texts[block["id"]] = block["content"]
                elif block["type"] == "table":
                    rows = [(f"{block['id']}.h", block["lines"][0], block["header"]),
                            *((row["id"], row["line"], row["cells"]) for row in block["rows"])]
                    for row_id, line, cells in rows:
                        text = " | ".join(cell["text"] for cell in cells)
                        texts[row_id] = text
                        if block.get("use") == "display" and row_id != f"{block['id']}.h":
                            units[row_id] = base | {"id": row_id, "kind": "row", "line": line, "text": text,
                                                    "citations": [c for cell in cells for c in cell["citations"]],
                                                    "block_citations": []}
                else:
                    for sentence in block.get("sentences", []):
                        texts[sentence["id"]] = sentence["text"]
                        if block.get("use") == "narrate" and sentence["spoken"] and not sentence["maintenance"]:
                            units[sentence["id"]] = base | {
                                "id": sentence["id"], "kind": "sentence", "line": sentence["lines"][0],
                                "text": sentence["text"], "citations": sentence["citations"],
                                "block_citations": block.get("citations", [])}
        return units, texts

    def _cited(self, unit: dict) -> tuple[list[dict], str]:
        """Return the sentence's citations, else its paragraph's, else its section's, and which scope applied."""
        for scope, links in (("sentence", unit["citations"]), ("block", unit["block_citations"]),
                             ("section", self.section_citations.get(unit["section"], []))):
            if cited := self.evidence.cited(links):
                return cited, scope
        return [], "none"

    def _waived(self, text: str, name: str) -> str | None:
        """Return why a name missing from the evidence is not a failure.

        The asker used it, such as a column in their own SQL, the document's own example
        code defines it, such as a helper function in a measurement script, or the
        sentence says it does not exist. Each waiver is reported.
        """
        pattern = rf"(?<![\w$]){re.escape(name)}(?![\w$])"
        if re.search(pattern, self.question_text):
            return "question"
        if re.search(pattern, self.example_text):
            return "example"
        return "negated" if _negated(text, name) else None

    def _narrated(self, occurrence: dict) -> bool:
        return occurrence.get("decision") in NARRATED

    def _passage(self, occurrence: dict) -> dict:
        at, match = occurrence.get("at"), occurrence.get("text") or ""
        text = self.texts.get(at) or match
        if len(text) > PASSAGE_CHARS:
            index = max(text.find(match), 0) if match else 0
            start, end = text.rfind("\n", 0, index) + 1, text.find("\n", index)
            start, end = max(start, index - PASSAGE_CHARS // 2), min(len(text) if end < 0 else end,
                                                                    index + PASSAGE_CHARS // 2)
            text = ("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "")
        return {"at": at, "section": occurrence.get("section"), "line": occurrence.get("line"), "match": match,
                "text": text, "decision": occurrence.get("decision")}

    def _passages(self, occurrences: list[dict]) -> dict:
        narrated = [o for o in occurrences if self._narrated(o)]
        chosen = list({(o.get("at"), o.get("line")): o for o in reversed(narrated or occurrences)}.values())[::-1]
        return {"count": len(occurrences), "narrated": len(narrated),
                "sample": [self._passage(o) for o in chosen[:PASSAGE_SAMPLE]]}

    def _glossary(self, match: dict, *, excerpt: str | None = None, source: str | None = None) -> dict:
        scope = match["version_scope"]
        return {"anchor": match["anchor"], "term": match["term"], "url": match["url"],
                "lines": match["glossary_lines"], "version_status": scope["status"],
                "explanation": scope.get("explanation"), "excerpt": excerpt or match["summary"],
                "source": source or "main"}

    def _add(self, identifier: str, result: str, check: str, *, concept: dict, tier: str, narrated: bool,
             passages: dict, resolution: dict, blocking: bool = False, glossary: dict | None = None,
             evidence: list[dict] | None = None, **details) -> dict:
        record = {"id": identifier, "result": result, "check": check, "concept": concept, "tier": tier,
                  "narrated": narrated, "version": self.version, "passages": passages, "glossary": glossary,
                  "evidence": evidence or [], "resolution": resolution, "blocking": blocking and narrated,
                  **details}
        self.results.append(record)
        return record

    # Build -------------------------------------------------------------------------------------

    def build(self) -> dict:
        claims = self._claims()
        facts = self._facts()
        for match in self.matches["matches"]:
            self._entry(match, facts)
        self._fact_results(facts)
        self._acronyms()
        self._roles()
        self._aliases()
        self._ambiguous()
        self._unmatched()
        document, glossary = self.matches["document"], self.matches["glossary"]
        return {
            "schema": SCHEMA_VERSION,
            "request_id": self.document["request_id"],
            "status": None,
            "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "document": {**document, "pinned_commit": self.evidence.pin},
            "glossary": {key: glossary[key] for key in ("path", "url", "sha256", "verified", "entries")},
            "version": self.version,
            "method": {
                "deterministic": ["version scope of each matched entry", "configuration parameter context, default, "
                                  "minimum, and maximum", "acronym expansions", "component roles",
                                  "glossary relationships", "citations: identifiers, numeric code, and quoted "
                                  "strings in the cited lines at the pin"],
                "pinned_settings": {
                    "files": sorted({record["path"] for record in self.evidence.settings.values()}),
                    "parameters": len(self.evidence.settings)} if self.evidence.settings else None,
                # A model may propose comparisons later; its confidence never counts as evidence.
                "semantic_comparison": {"used": False, "reason": "No language model is configured; meaning is "
                                                                 "compared only through the checks listed here."},
            },
            "subject": None,
            "counts": None,
            "results": self.results,
            "claims": claims,
            "sections": None,
            "corrections": self.corrections,
            "exceptions": self.exceptions,
            "omissions": self.omissions,
            "resolutions": None,
            "issues": [],
        }

    # Claims ------------------------------------------------------------------------------------

    def _claims(self) -> list[dict]:
        occurrences = defaultdict(list)
        for match in self.matches["matches"]:
            for occurrence in match["occurrences"]:
                occurrences[occurrence["at"]].append(match["anchor"])
        claims = []
        for unit in self.units.values():
            # A sentence ending in a colon introduces the table, list, or code shown after it.
            if (unit["role"] not in CLAIM_ROLES or unit["decision"] not in NARRATED
                    or unit["text"].rstrip().endswith(":")):
                continue
            cited, scope = self._cited(unit)
            items, status = self.claim(unit["text"], cited, scope)
            central = unit["id"] in self.conclusions
            claim = {"id": f"claim@{unit['id']}", "at": unit["id"], "section": unit["section"], "line": unit["line"],
                     "central": central, "text": unit["text"], "status": status, "citation_scope": scope,
                     "citation_count": len(cited),
                     "citations": [{key: c[key] for key in ("path", "lines", "url")} for c in cited[:CITATION_SAMPLE]],
                     "items": items, "entries": list(dict.fromkeys(occurrences.get(unit["id"], []))),
                     "resolution": {"status": "not_needed"}, "blocking": False}
            if status in ("uncited", "unconfirmed"):
                missing = [item["text"] for item in items if not item["level"] and not item.get("waived")]
                # Prose with nothing to look up, such as a verdict that summarizes the page's own measurements,
                # cannot be checked against the source; it is reported, but only a failed lookup blocks.
                claim["resolution"] = {
                    "status": "unresolved",
                    "proposal": "Cite the PostgreSQL source that supports this sentence, or leave it out of the "
                                "narration." if status == "uncited" else
                                "Check " + ", ".join(f"`{text}`" for text in missing) + " against the pinned source; "
                                "correct the citation or leave the sentence out of the narration.",
                    "evidence_needed": f"A raw/postgres-{self.version}/ file and line range at the pin that shows "
                                       "this statement."}
                claim["blocking"] = central and status == "unconfirmed"
            claims.append(claim)
        return claims

    def claim(self, text: str, cited: list[dict], scope: str) -> tuple[list[dict], str]:
        """Look up a sentence's identifiers, numeric code, and quoted strings; return them and the claim status."""
        items = []
        for item in _items(text):
            found = self.evidence.find(item, cited)
            if not found["level"] and (waived := self._waived(text, item["text"])):
                found["waived"] = waived
            items.append({"text": item["text"], "kind": item["kind"], **found})
        levels = [item["level"] for item in items if not item.get("waived")]
        if scope == "none" and not levels:
            status = "uncited"
        elif not levels:
            status = "cited"
        elif scope == "none":
            status = "supported" if all(levels) else "unconfirmed"
        elif all(level in ("range", "file") for level in levels):
            status = "verified"
        elif all(levels):
            status = "supported"
        else:
            status = "unconfirmed"
        return items, status

    # Configuration facts ---------------------------------------------------------------------

    def _mentions(self, plain: str, spans: list[tuple[int, int]], excluded: list[tuple[int, int]]) -> list[dict]:
        found = []
        for match in IDENTIFIER_TOKEN.finditer(plain):
            start, end = match.span()
            name = match.group(0).removesuffix("()")
            if any(a <= start < b for a, b in excluded) or PGC.fullmatch(name) or name.startswith("GUC_") \
                    or name in PROPER_NAMES:
                continue
            code = any(a <= start and end <= b for a, b in spans)
            # `role` alone names the parameter; `TO role[, ...]` is SQL syntax that happens to contain the word.
            setting = name in self.settings and (IDENTIFIER_SHAPE.search(name) is not None
                                                 or (start, end) in spans or (start, end - 2) in spans)
            if (setting and code) or IDENTIFIER_SHAPE.search(name):
                found.append({"start": start, "end": end, "name": name, "setting": setting})
        return found

    def _paragraph_facts(self, sentences: list[str], fallback: str | None, pronoun_only: bool) -> list[tuple]:
        """Return (sentence number, fact) pairs, each fact naming the parameter it describes.

        The parameter is the nearest identifier before the fact in the same sentence,
        or the subject that opens the previous sentence with identifiers, or else the
        fallback parameter when the paragraph has named nothing yet.
        """
        unset = object()
        carried: object = unset
        found = []
        for number, text in enumerate(sentences):
            plain, spans = _plain(text)
            facts = _sentence_facts(plain, spans)
            mentions = self._mentions(plain, spans, [(fact["start"], fact["end"]) for fact in facts])
            for fact in facts:
                # "`a` and `b` keep defaults of `64MB` and `-1`" pairs values with parameters; skip such lists.
                if VALUE_LIST.match(plain, fact["end"]):
                    continue
                before = [m for m in mentions if m["end"] <= fact["start"]]
                # "`autovacuum` is `PGC_SIGHUP`; every other setting is `PGC_USERSET`": stay in the fact's clause.
                clause = max(plain.rfind(";", 0, fact["start"]), plain.rfind(":", 0, fact["start"]))
                own = [m for m in before if m["start"] > clause]
                if own:
                    last = own[-1]
                    listed = len(own) > 1 and COORDINATED.fullmatch(plain[own[-2]["end"]:last["start"]])
                    subject = last["name"] if last["setting"] and not listed else None
                elif before:
                    subject = None
                elif carried is not unset:
                    subject = carried
                elif fallback and (not pronoun_only or PRONOUN.match(plain)):
                    subject = fallback
                else:
                    subject = None
                if subject:
                    found.append((number, fact | {"setting": subject}))
            if mentions:
                first = mentions[0]
                opens = plain[:first["start"]].strip(" \"'(").lower() in ("", "the", "a", "an")
                carried = first["name"] if first["setting"] and opens else None
        return found

    def _entry_setting(self, match: dict) -> str | None:
        names = {text.replace("`", "").strip().removesuffix("()")
                 for text in [match["term"], *(alias["text"] for alias in match["aliases"])]}
        settings = names & self.settings
        return next(iter(settings)) if len(settings) == 1 else None

    def _glossary_texts(self, match: dict) -> list[tuple[str, list[str]]]:
        """Return the entry's statements that apply to the document's version, in order of precedence."""
        scope = match["version_scope"]
        main = ("main", [paragraph["text"] for paragraph in match["definition"]])
        texts = []
        if scope.get("note"):
            texts.append((f"note:{scope['note']['version']}", [_note_body(scope["note"]["text"])]))
        for reference in scope.get("references", []):
            if reference.get("status") == "main":
                texts.append(main)
            elif reference.get("text"):
                texts.append((f"note:{reference['version']}", [_note_body(reference["text"])]))
        if scope["status"] in ("main", "holds", "holds_with_exceptions"):
            texts.append(main)
        return texts

    def _facts(self) -> dict:
        """Collect document, glossary, and pinned-source facts about configuration parameters."""
        document = []
        for section in self.document["sections"]:
            for block in _leaves(section["blocks"]):
                ids = [s["id"] for s in block.get("sentences", []) if s["id"] in self.units]
                if not ids:
                    continue
                for number, fact in self._paragraph_facts([self.units[i]["text"] for i in ids], self.focus_setting,
                                                          pronoun_only=True):
                    document.append(fact | {"at": ids[number]})
        glossary: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for match in self.matches["matches"]:
            seen = set()
            for source, paragraphs in self._glossary_texts(match):
                for paragraph in paragraphs:
                    for _number, fact in self._paragraph_facts(_sentences(paragraph), self._entry_setting(match),
                                                               pronoun_only=False):
                        key = (fact["setting"], fact["attribute"])
                        # A version note comes first and takes precedence over the paragraph it amends.
                        if key in seen:
                            continue
                        seen.add(key)
                        glossary[key].append({"anchor": match["anchor"], "value": fact["value"], "raw": fact["raw"],
                                              "source": source})
        return {"document": document, "glossary": glossary}

    def _source(self, setting: str, attribute: str) -> tuple[dict | None, dict | None]:
        record = self.evidence.settings.get(setting)
        if not record or attribute not in record:
            return None, None
        return record[attribute], {"path": record["path"], "line": record["line"], "url": record["url"],
                                   "symbol": record.get("context_symbol") if attribute == "context" else None}

    def _fact_results(self, facts: dict) -> None:
        for fact in facts["document"]:
            unit = self.units[fact["at"]]
            setting, attribute = fact["setting"], fact["attribute"]
            source, where = self._source(setting, attribute)
            value = _in_unit(fact["value"], source)
            comparisons = [g | {"same": _same(value, _in_unit(g["value"], source))}
                           for g in facts["glossary"].get((setting, attribute), [])]
            comparisons = [c for c in comparisons if c["same"] is not None]
            confirmed = _same(value, source)
            differing = [c for c in comparisons if not c["same"]]
            if confirmed is None and not comparisons:
                continue
            anchor = next((c["anchor"] for c in comparisons), None) or next(
                (m["anchor"] for m in self.matches["matches"] if self._entry_setting(m) == setting), None)
            match = self.by_anchor.get(anchor)
            identifier = f"fact:{setting}:{attribute}@{unit['id']}"
            passage = {"count": 1, "narrated": 1, "sample": [{
                "at": unit["id"], "section": unit["section"], "line": unit["line"], "match": fact["raw"],
                "text": unit["text"], "decision": unit["decision"]}]}
            central = unit["id"] in self.conclusions
            details = {"setting": setting, "attribute": attribute, "document_value": _public(value),
                       "glossary_values": [{"anchor": c["anchor"], "value": _public(c["value"]),
                                            "source": c["source"], "same": c["same"]} for c in comparisons],
                       "source_value": _public(source) if source else None}
            evidence = [where] if where else []
            stated = (differing or comparisons)[:1]
            glossary = self._glossary(match, excerpt=stated[0]["raw"] if stated else None,
                                      source=stated[0]["source"] if stated else None) if match else None
            common = {"concept": {"term": setting, "anchor": anchor, "kind": "setting"},
                      "tier": "central" if central else "supporting", "narrated": True, "passages": passage,
                      "glossary": glossary, "evidence": evidence, **details}
            name = {"context": "context", "default": "default", "min": "minimum", "max": "maximum"}[attribute]
            if confirmed is True or (confirmed is None and not differing):
                basis = (["pinned source"] if confirmed else []) + (["glossary"] if comparisons else [])
                if differing:
                    wrong = ", ".join(f"#{c['anchor']} ({c['source']})" for c in differing)
                    self._add(identifier, "conflict", f"fact:{attribute}", resolution={
                        "status": "resolved", "by": "pinned_source", "winner": "document",
                        "proposal": f"Keep the document's {name}; the pinned source agrees with it. The glossary "
                                    f"entry {wrong} states {_display(differing[0]['value'])} for PostgreSQL "
                                    f"{self.version} and should be corrected."}, **common)
                else:
                    self._add(identifier, "consistent", f"fact:{attribute}", resolution={"status": "not_needed"},
                              basis=basis, **common)
            elif confirmed is False:
                winner = "glossary" if any(c["same"] is False and _same(_in_unit(c["value"], source), source)
                                           for c in comparisons) else "pinned_source"
                self._add(identifier, "conflict", f"fact:{attribute}", resolution={
                    "status": "resolved", "by": "pinned_source", "winner": winner,
                    "proposal": f"Narrate the {name} of `{setting}` as {_display(source)}, as the pinned source "
                                f"defines it; the document says {fact['raw']!r}."}, **common)
                self.corrections.append({
                    "id": identifier, "at": unit["id"], "section": unit["section"], "line": unit["line"],
                    "text": unit["text"], "setting": setting, "attribute": attribute,
                    "document": fact["raw"], "value": fact["value"].get("raw"), "corrected": _display(source),
                    "source": "pinned_source",
                    "evidence": evidence,
                    "instruction": f"State the {name} of `{setting}` as {_display(source)}, not {fact['raw']!r}."})
            else:
                values = ", ".join(f"{_display(c['value'])} in #{c['anchor']} ({c['source']})" for c in differing)
                self._add(identifier, "conflict", f"fact:{attribute}", blocking=True, resolution={
                    "status": "unresolved",
                    "proposal": f"The document gives the {name} of `{setting}` as {fact['raw']!r}; the glossary gives "
                                f"{values}. Confirm the value in the PostgreSQL {self.version} GUC table.",
                    "evidence_needed": f"The `{setting}` entry in raw/postgres-{self.version}/{GUC_TABLES[0]} "
                                       "(or guc.c or guc_parameters.dat) at the pin."}, **common)

    # Entries -----------------------------------------------------------------------------------

    def _entry(self, match: dict, facts: dict) -> None:
        scope, status = match["version_scope"], match["version_scope"]["status"]
        occurrences = match["occurrences"]
        narrated = any(self._narrated(o) for o in occurrences)
        passages = self._passages(occurrences)
        definition = self._definition(match, facts)
        concept = {"term": match["term"], "anchor": match["anchor"], "kind": "entry"}
        common = {"concept": concept, "tier": match["tier"], "narrated": narrated, "passages": passages,
                  "definition": definition, "methods": match["methods"], "forms": match["forms"]}
        identifier = f"entry:{match['anchor']}"
        if status in ("main", "holds", "holds_with_exceptions", "differs"):
            note = scope.get("note")
            source = f"note:{note['version']}" if status == "differs" and note else "main"
            excerpt = definition["text"] if status == "differs" else match["summary"]
            basis = self._basis(match)
            strength = "checked" if len(basis) > 2 else "terminology"
            if match["relation"] == "contrast":
                basis.append("contrast: the document names a concept the entry contrasts with")
            self._add(identifier, "consistent", "entry", glossary=self._glossary(match, excerpt=excerpt, source=source),
                      resolution={"status": "not_needed"}, basis=basis, strength=strength, **common)
        elif status == "not_present":
            found = self._occurrence_support(occurrences, code_only=True)
            spoken = [o for o in occurrences if self._narrated(o)]
            negated = [o for o in spoken if _negated(self.texts.get(o["at"], ""), o["text"])]
            qualified = [o for o in spoken if o not in negated
                         and _qualified(self.texts.get(o["at"], ""), self.version)]
            glossary = self._glossary(match, excerpt=_note_body(scope["note"]["text"]),
                                      source=f"note:{self.version}")
            if spoken and len(negated) == len(spoken):
                self._add(identifier, "consistent", "entry", glossary=glossary, resolution={"status": "not_needed"},
                          basis=[f"availability: the document also says {match['term']} is absent in PostgreSQL "
                                 f"{self.version}"], strength="checked", **common)
                return
            evidence = [f["found"] for f in found]
            if not spoken:
                resolution = {"status": "not_needed", "proposal": "Not narrated."}
            elif found:
                resolution = {"status": "resolved", "by": "pinned_source", "winner": "document",
                              "proposal": f"The pinned PostgreSQL {self.version} source contains "
                                          f"`{found[0]['text']}`, so keep the document's statement; the glossary's "
                                          f"PostgreSQL {self.version} note should be checked."}
            elif len(negated) + len(qualified) == len(spoken):
                resolution = {"status": "resolved", "by": "document_qualifier",
                              "proposal": "Every narrated mention is qualified by another version, a historical "
                                          "word, or a negation; keep the qualifier in the script."}
            else:
                resolution = {"status": "unresolved",
                              "proposal": f"The glossary says {match['term']} does not exist in PostgreSQL "
                                          f"{self.version}. Show that the document's PostgreSQL {self.version} "
                                          "evidence contains it, or leave it out of the narration.",
                              "evidence_needed": f"A raw/postgres-{self.version}/ file at the pin that defines "
                                                 f"{match['term']}."}
            self._add(identifier, "version_mismatch", "entry", glossary=glossary, resolution=resolution,
                      evidence=evidence, blocking=resolution["status"] == "unresolved", **common)
        else:
            self._coverage_gap(identifier, match, occurrences, common, gap=status)

    def _definition(self, match: dict, facts: dict) -> dict:
        """Decide how the script may use the entry's definition for the document's version."""
        scope, status = match["version_scope"], match["version_scope"]["status"]
        note = scope.get("note")
        caveats = [_note_body(text) for text in [note and note["text"], *(r.get("text") for r in scope.get(
            "references", []))] if text and _note_body(text)] if status == "holds_with_exceptions" else []
        if match["relation"] == "contrast":
            use, text, reason = "none", None, "The document names a concept that this entry contrasts with."
        elif status in ("main", "holds", "holds_with_exceptions"):
            use, text, reason = "introduce", match["summary"], scope.get("explanation")
        elif status == "differs":
            use, text, reason = "note_only", _note_body(note["text"]) if note else None, scope.get("explanation")
        else:
            use, text, reason = "none", None, scope.get("explanation")
        record = {"use": use, "text": text, "spoken": match["spoken_summary"] if use == "introduce" else None,
                  "reason": reason, "caveats": caveats, "evidence": self._definition_evidence(match, text)}
        contradicted = []
        for (setting, attribute), values in facts["glossary"].items():
            for value in values:
                source, where = self._source(setting, attribute)
                if value["anchor"] == match["anchor"] and _same(_in_unit(value["value"], source), source) is False:
                    contradicted.append({"setting": setting, "attribute": attribute, "glossary": value["raw"],
                                         "source": _display(source), "evidence": where})
        if contradicted and use != "none":
            record.update(use="name_only", contradicted=contradicted,
                          reason="The pinned source contradicts the definition: " + "; ".join(
                              f"{c['attribute']} of `{c['setting']}` is {c['source']}, not {c['glossary']!r}"
                              for c in contradicted) + ".")
        return record

    def _definition_evidence(self, match: dict, text: str | None) -> dict:
        """Check the identifiers of the definition the script may use against the document's pinned files."""
        if not text:
            return {"status": "none", "checked": 0}
        items = _items(text)
        found = [(item, self.evidence.find(item, [])) for item in items]
        missing = [item["text"] for item, result in found if not result["level"]]
        status = "none" if not items else "confirmed" if not missing else "partial" if len(missing) < len(items) \
            else "unconfirmed"
        return {"status": status, "checked": len(items), "missing": missing}

    def _basis(self, match: dict) -> list[str]:
        basis = ["terminology: " + ", ".join(match["methods"]),
                 f"version scope: {match['version_scope']['status']} for PostgreSQL {self.version}"]
        entry_files = {c["path"] for p in match["definition"] for c in p["citations"] if c.get("path")}
        note = match["version_scope"].get("note") or {}
        entry_files |= {c["path"] for c in note.get("citations", []) if c.get("path")}
        cited = set()
        symbols = set()
        for occurrence in match["occurrences"]:
            unit = self.units.get(occurrence["at"])
            if unit:
                cited |= {c["path"] for c in self._cited(unit)[0]}
            symbols |= {c.removeprefix("symbol:") for c in occurrence.get("context", []) if c.startswith("symbol:")}
        if shared := sorted(cited & entry_files):
            basis.append("shared evidence: " + ", ".join(shared[:4]))
        if symbols:
            basis.append("shared symbols: " + ", ".join(sorted(symbols)[:4]))
        related = set(match["related"]) | {m["anchor"] for m in self.matches["matches"]
                                           if match["anchor"] in m["related"]}
        together = set()
        for occurrence in match["occurrences"]:
            if self._narrated(occurrence):
                together |= {m["anchor"] for m in self.matches["matches"] if m["anchor"] in related
                             and any(o["at"] == occurrence["at"] for o in m["occurrences"])}
        if together:
            basis.append("related entries in the same sentence: " + ", ".join(sorted(together)[:4]))
        return basis

    def _occurrence_support(self, occurrences: list[dict], *, code_only: bool = False) -> list[dict]:
        """Return occurrences whose matched text appears in the document's pinned evidence."""
        found = []
        for occurrence in occurrences:
            unit = self.units.get(occurrence["at"])
            if not self._narrated(occurrence) or unit is None:
                continue
            text = occurrence["text"].removesuffix("()")
            code = occurrence.get("in_code") or bool(IDENTIFIER_SHAPE.search(text))
            if code_only and not code:
                continue
            # `IndexStmt.concurrent` is checked through its distinctive parts, which the source names separately.
            parts = [part for part in text.split(".") if IDENTIFIER_SHAPE.search(part)] if code else []
            cited = self._cited(unit)[0]
            results = [self.evidence.find(_item(part, "identifier" if code else "literal"), cited)
                       for part in (parts if "." in text and parts else [text])]
            if all(r["level"] and (not code_only or r["exact"]) for r in results):
                found.append({"text": text, "at": unit["id"], "found": results[0]})
        return found

    def _coverage_gap(self, identifier: str, match: dict | None, occurrences: list[dict], common: dict, *,
                      gap: str, term: dict | None = None) -> None:
        """Record a concept the glossary does not cover for this version, allowed when the evidence supports it."""
        narrated = any(self._narrated(o) for o in occurrences)
        central = (common["tier"] == "central")
        support = self._occurrence_support(occurrences)
        name = match["term"] if match else term["term"]
        explanations = {
            "unchecked": f"The entry was not checked on PostgreSQL {self.version}.",
            "unknown": f"The entry lists PostgreSQL {self.version} as checked but has no {self.version} note.",
            "no_entry": "No glossary entry covers this term.",
            "glossary_anchor_missing": "The document links to a glossary entry that does not exist.",
        }
        if support:
            best = min(support, key=lambda s: FOUND.index(s["found"]["level"]))
            resolution = {"status": "accepted_exception", "by": "document_evidence",
                          "proposal": f"Explain {name} from the document's own PostgreSQL {self.version} evidence, "
                                      "not from the glossary."}
            self.exceptions.append({"id": identifier, "term": name, "anchor": match and match["anchor"],
                                    "gap": gap, "central": central, "reason": explanations[gap],
                                    "evidence": best["found"], "at": best["at"]})
            evidence = [s["found"] for s in support[:3]]
        elif narrated and (waived := self._gap_waived(name, occurrences)):
            resolution = {"status": "not_needed", "by": waived, "proposal": {
                "question": f"The asker named {name}; repeat the name, but explain it only from the document.",
                "example": f"The document's own example code defines {name}; present it as part of the example.",
                "negated": f"The document names {name} only to say it is absent; keep that negation in the script.",
            }[waived]}
            evidence = []
        else:
            resolution = {"status": "unresolved" if narrated else "not_needed",
                          "proposal": f"Cite PostgreSQL {self.version} evidence for {name}, or leave it out of the "
                                      "narration." if narrated else "Not narrated.",
                          **({"evidence_needed": f"A raw/postgres-{self.version}/ file at the pin that shows "
                                                 f"{name}."} if narrated else {})}
            evidence = []
        self._add(identifier, "not_in_glossary", "coverage", resolution=resolution, evidence=evidence, gap=gap,
                  explanation=explanations[gap], blocking=central and resolution["status"] == "unresolved",
                  glossary=self._glossary(match) if match else None, **common)

    def _gap_waived(self, name: str, occurrences: list[dict]) -> str | None:
        reasons = {self._waived(self.texts.get(o["at"], ""), o["text"].removesuffix("()"))
                   for o in occurrences if self._narrated(o)}
        for reason in ("question", "example"):
            if reason in reasons:
                return reason
        return "negated" if reasons == {"negated"} else None

    # Acronyms, roles, and version-limited aliases ----------------------------------------------

    def _acronyms(self) -> None:
        owners: dict[str, list[tuple[dict, list[str]]]] = defaultdict(list)
        for match in self.matches["matches"]:
            forms = [match["term"], *(form for alias in match["aliases"] if alias["relation"] == "synonym"
                                      for form in _alias(alias["text"])["forms"])]
            clean = [" ".join(form.replace("`", "").split()) for form in forms]
            for acronym in {form for form in clean if ACRONYM.fullmatch(form)}:
                expansions = [form for form in clean if not ACRONYM.fullmatch(form) and "_" not in form
                              and len(re.split(r"[\s-]+", form)) > 1 and _expands(acronym, form) == 0
                              and not re.search(rf"(?<!\w){re.escape(acronym)}(?!\w)", form, re.IGNORECASE)]
                if expansions:
                    owners[acronym].append((match, expansions))
        if not owners:
            return
        for unit in self.units.values():
            if unit["kind"] != "sentence" or unit["decision"] not in NARRATED:
                continue
            plain, _spans = _plain(unit["text"])
            for acronym, long, tail in self._expansions(plain):
                if acronym not in owners:
                    continue
                readings = [long] + [f"{long} {' '.join(tail[:n])}" for n in range(1, len(tail) + 1)]
                agreeing = [(m, e) for m, e in owners[acronym]
                            if any(_same_expansion(reading, x) for x in e for reading in readings)]
                match, expansions = (agreeing or owners[acronym])[0]
                central = unit["id"] in self.conclusions or unit["id"] in self.question
                common = {"concept": {"term": acronym, "anchor": match["anchor"], "kind": "acronym"},
                          "tier": "central" if central else match["tier"], "narrated": True,
                          "passages": {"count": 1, "narrated": 1, "sample": [{
                              "at": unit["id"], "section": unit["section"], "line": unit["line"], "match": long,
                              "text": unit["text"], "decision": unit["decision"]}]},
                          "glossary": self._glossary(match, excerpt=", ".join(expansions), source="aliases"),
                          "document_expansion": long, "glossary_expansions": expansions}
                identifier = f"acronym:{acronym}@{unit['id']}"
                if agreeing:
                    self._add(identifier, "consistent", "acronym", resolution={"status": "not_needed"},
                              basis=["acronym expansion"], **common)
                else:
                    self._add(identifier, "conflict", "acronym", blocking=True, resolution={
                        "status": "unresolved",
                        "proposal": f"The document expands {acronym} as {long!r}; the glossary gives "
                                    + " or ".join(repr(e) for e in expansions) + ". Use the glossary's expansion "
                                    "or document why the document's is correct.",
                        "evidence_needed": f"A PostgreSQL {self.version} source or documentation line that "
                                           f"expands {acronym}."}, **common)

    @staticmethod
    def _expansions(plain: str):
        """Yield (acronym, long form, following words) for "long form (ACR)" and "ACR (long form)".

        The following words matter in "just-in-time (JIT) compilation", where the
        expansion continues after the parenthesis.
        """
        for match in ACRONYM_AFTER.finditer(plain):
            acronym = match.group("acronym")
            if not ACRONYM.fullmatch(acronym):
                continue
            letters = sum(c.isalnum() for c in acronym)
            words = plain[:match.start()].rstrip().split()[-min(letters + 5, letters * 2):]
            window = " ".join(words).rstrip(",;:")
            start = _expands(acronym, window)
            if start is not None:
                yield acronym, window[start:].strip(), re.findall(r"[\w-]+", plain[match.end():])[:2]
        for match in ACRONYM_BEFORE.finditer(plain):
            acronym, long = match.group("acronym"), match.group("long").strip()
            if ACRONYM.fullmatch(acronym) and _expands(acronym, long) == 0:
                yield acronym, long, []

    def _roles(self) -> None:
        roles = {}
        for match in self.matches["matches"]:
            role = _role(match["summary"])
            if role and match["relation"] != "contrast":
                roles.setdefault(role["subject"], (match, role))
        table = any(path in self.evidence.text for path in (*GUC_TABLES, GUC_DATA))
        for unit in self.units.values():
            if unit["kind"] != "sentence" or unit["decision"] not in NARRATED:
                continue
            role = _role(unit["text"])
            if not role or role["subject"] not in roles:
                continue
            match, stated = roles[role["subject"]]
            central = unit["id"] in self.conclusions
            common = {"concept": {"term": match["term"], "anchor": match["anchor"], "kind": "entry"},
                      "tier": "central" if central else match["tier"], "narrated": True,
                      "passages": {"count": 1, "narrated": 1, "sample": [{
                          "at": unit["id"], "section": unit["section"], "line": unit["line"], "match": role["text"],
                          "text": unit["text"], "decision": unit["decision"]}]},
                      "glossary": self._glossary(match), "document_role": role["word"],
                      "glossary_role": stated["word"]}
            identifier = f"role:{match['anchor']}@{unit['id']}"
            if role["role"] == stated["role"]:
                self._add(identifier, "consistent", "role", resolution={"status": "not_needed"},
                          basis=[f"role: {role['role']}"], **common)
                continue
            name = match["term"].replace("`", "")
            if table and "setting" in (role["role"], stated["role"]) and re.fullmatch(r"[a-z_][a-z0-9_]*", name):
                record = self.evidence.settings.get(name)
                winner = ("document" if role["role"] == "setting" else "glossary") if record else (
                    "glossary" if role["role"] == "setting" else "document")
                resolution = {"status": "resolved", "by": "pinned_source", "winner": winner,
                              "proposal": f"The pinned GUC table {'defines' if record else 'does not define'} "
                                          f"`{name}`; describe it as {'a' if winner == 'glossary' else 'the'} "
                                          f"{stated['word'] if winner == 'glossary' else role['word']}."}
                evidence = [{"path": record["path"], "line": record["line"], "url": record["url"]}] if record else []
                if winner == "glossary":
                    self.corrections.append({
                        "id": identifier, "at": unit["id"], "section": unit["section"], "line": unit["line"],
                        "text": unit["text"], "document": role["text"], "corrected": stated["word"],
                        "source": "pinned_source", "evidence": evidence,
                        "instruction": f"Describe {name} as a {stated['word']}, not a {role['word']}."})
                self._add(identifier, "conflict", "role", resolution=resolution, evidence=evidence, **common)
            else:
                self._add(identifier, "conflict", "role", blocking=True, resolution={
                    "status": "unresolved",
                    "proposal": f"The document calls {name} a {role['word']}; the glossary calls it a "
                                f"{stated['word']}. Confirm which it is in PostgreSQL {self.version}.",
                    "evidence_needed": f"The PostgreSQL {self.version} definition of {name} at the pin."}, **common)

    def _aliases(self) -> None:
        for match in self.matches["matches"]:
            groups = defaultdict(list)
            for occurrence in match["occurrences"]:
                versions = occurrence.get("alias_versions")
                if versions and self.version not in versions:
                    groups[_fold(occurrence["form"]), tuple(versions)].append(occurrence)
            for (form, versions), occurrences in groups.items():
                narrated = [o for o in occurrences if self._narrated(o)]
                unqualified = [o for o in narrated if not _qualified(self.texts.get(o["at"], ""), self.version)]
                listed = " and ".join(str(v) for v in versions)
                if unqualified:
                    resolution = {"status": "unresolved",
                                  "proposal": f"The glossary uses the name {form!r} only for PostgreSQL {listed}. "
                                              f"Use the PostgreSQL {self.version} name ({match['term']}) or qualify "
                                              "the sentence as history.",
                                  "evidence_needed": f"PostgreSQL {self.version} evidence that {form!r} still names "
                                                     "this component."}
                else:
                    resolution = {"status": "resolved", "by": "document_qualifier",
                                  "proposal": "Each mention is qualified by another version or a historical word; "
                                              "keep the qualifier in the script."}
                self._add(f"alias:{match['anchor']}:{form}", "version_mismatch", "alias_version",
                          concept={"term": form, "anchor": match["anchor"], "kind": "alias"}, tier=match["tier"],
                          narrated=bool(narrated), passages=self._passages(occurrences),
                          glossary=self._glossary(match), resolution=resolution, blocking=bool(unqualified),
                          alias_versions=list(versions))

    # Ambiguous and unmatched terms -------------------------------------------------------------

    def _ambiguous(self) -> None:
        """Record ambiguous terms; a central one blocks when entries collide or the subject names it.

        A central ordinary word that merely lacks context, such as "row" or "page" in a
        conclusion, only keeps its glossary definition out of the script.
        """
        focus = {_fold(term["term"]) for term in self.matches["subject"]["focus_terms"]
                 if term["status"] == "ambiguous"}
        seen = set()
        for group in self.matches["ambiguous"]:
            anchors = [c["anchor"] for c in group["candidates"]]
            identifier = f"ambiguous:{_fold(group['text'])}"
            if identifier in seen or group["reason"] == "collision":
                identifier += ":" + "+".join(anchors)
            seen.add(identifier)
            narrated = any(self._narrated(o) for o in group["occurrences"])
            central = group["central"]
            concept = central and (group["reason"] == "collision" or _fold(group["text"]) in focus)
            candidates = ", ".join(f"#{a}" for a in anchors)
            resolution = {
                "status": "unresolved" if concept else "not_needed",
                "proposal": (f"Choose the entry the document means ({candidates}), explain the term from the "
                             "document alone, or leave it out." if concept else
                             "Do not introduce a glossary definition for this word; explain it from the document."),
            }
            if concept:
                resolution["evidence_needed"] = "The sentence's meaning: which glossary entry, if any, it refers to."
            self._add(identifier, "ambiguous", "ambiguity",
                      concept={"term": group["text"], "anchor": None, "kind": "term"},
                      tier="central" if central else "supporting" if narrated else "peripheral",
                      narrated=narrated, resolution=resolution, blocking=concept,
                      passages={"count": group["count"], "narrated": sum(self._narrated(o)
                                                                         for o in group["occurrences"]),
                                "sample": [self._passage(o) for o in group["occurrences"][:PASSAGE_SAMPLE]]},
                      reason=group["reason"], candidates=[{key: c[key] for key in (
                          "anchor", "term", "url", "form", "relation", "support", "summary", "version_status")}
                          for c in group["candidates"]])

    def _unmatched(self) -> None:
        terms = {term["term"]: term for term in self.document["terms"]}
        matched = defaultdict(list)
        for match in self.matches["matches"]:
            for occurrence in match["occurrences"]:
                matched[occurrence["at"]].append(occurrence["text"])
        for term in self.matches["unmatched"]:
            if COMMIT_HASH.fullmatch(term["term"]) or GIT_REF.fullmatch(term["term"]) \
                    or term["term"].lower() in PLATFORMS:
                continue
            # A term inside a longer matched name, such as TAP in "TAP test", is covered by that entry.
            pattern = re.compile(rf"(?<![\w$]){re.escape(term['term'])}(?![\w$])")
            places = [o["at"] for o in (terms.get(term["term"]) or {}).get("occurrences", [])]
            if places and all(any(pattern.search(text) for text in matched[at]) for at in places):
                continue
            occurrences = []
            for occurrence in (terms.get(term["term"]) or {}).get("occurrences", []):
                unit = self.units.get(occurrence["at"])
                occurrences.append({"at": occurrence["at"], "line": occurrence["line"], "text": term["term"],
                                    "in_code": term["kind"] != "glossary_link",
                                    "section": unit["section"] if unit else None,
                                    "decision": unit["decision"] if unit else None})
            if not occurrences:
                first = term["first"]
                occurrences = [{"at": first["at"], "line": first["line"], "text": term["term"], "in_code": False,
                                "section": None, "decision": None}]
            common = {"concept": {"term": term["term"], "anchor": None, "kind": term["kind"]},
                      "tier": "central" if term["central"] else "supporting"
                      if any(self._narrated(o) for o in occurrences) else "peripheral",
                      "narrated": any(self._narrated(o) for o in occurrences),
                      "passages": self._passages(occurrences)}
            self._coverage_gap(f"term:{term['term']}", None, occurrences, common, gap=term["reason"], term=term)

    # Resolutions -------------------------------------------------------------------------------

    def resolve(self, record: dict, resolutions: dict | None) -> None:
        """Apply a reviewer's documented resolutions, validating each against the result it names."""
        record["resolutions"] = {"file": None, "applied": []}
        if resolutions is None:
            return
        record["resolutions"].update(file=RESOLUTIONS, sha256=resolutions["sha256"])
        items = {item["id"]: ("claim", item) for item in record["claims"]}
        items |= {item["id"]: (item["result"], item) for item in record["results"]}
        seen = set()
        for number, entry in enumerate(resolutions["resolutions"], 1):
            where = f"{RESOLUTIONS} item {number}"
            if not isinstance(entry, dict):
                raise ValueError(f"{where} must be a mapping with id, decision, and reason.")
            unknown = set(entry) - {"id", "decision", "reason", "evidence", "entry", "reviewer"}
            if unknown:
                raise ValueError(f"{where} has unknown keys: {', '.join(sorted(unknown))}.")
            identifier, decision = entry.get("id"), entry.get("decision")
            reason = entry.get("reason")
            if not isinstance(identifier, str) or identifier not in items:
                raise ValueError(f"{where}: id {identifier!r} is not a result or claim in glossary-check.json.")
            if identifier in seen:
                raise ValueError(f"{where}: {identifier} is resolved more than once.")
            seen.add(identifier)
            kind, item = items[identifier]
            if kind not in DECISIONS:
                raise ValueError(f"{where}: {identifier} is {kind} and has nothing to resolve.")
            if decision not in DECISIONS[kind]:
                raise ValueError(f"{where}: decision for {identifier} must be one of "
                                 f"{', '.join(DECISIONS[kind])}, not {decision!r}.")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError(f"{where}: {identifier} needs a nonempty reason.")
            references = entry.get("evidence") or []
            references = [references] if isinstance(references, str) else references
            if not isinstance(references, list) or not all(isinstance(r, str) for r in references):
                raise ValueError(f"{where}: evidence must be a string or a list of strings.")
            if decision in EVIDENCE_DECISIONS and kind != "ambiguous" and not references:
                raise ValueError(f"{where}: {decision} for {identifier} needs PostgreSQL {self.version} evidence, "
                                 f"such as raw/postgres-{self.version}/path/to/file.c#L10-L20.")
            evidence = [self._reference(where, reference) for reference in references]
            chosen = entry.get("entry")
            if decision == "choose_entry":
                anchors = [c["anchor"] for c in item["candidates"]]
                if chosen not in anchors:
                    raise ValueError(f"{where}: choose_entry for {identifier} needs entry: one of "
                                     f"{', '.join(anchors)}.")
            elif chosen is not None:
                raise ValueError(f"{where}: entry is only used with choose_entry.")
            reviewer = entry.get("reviewer")
            item["resolution"] = {"status": "resolved", "by": "reviewer", "decision": decision,
                                  "reason": reason.strip(), "evidence": evidence,
                                  **({"entry": chosen} if chosen else {}),
                                  **({"reviewer": str(reviewer)} if reviewer else {}),
                                  "replaces": item["resolution"]}
            item["blocking"] = False
            self._apply(item, kind, decision, reason.strip(), evidence)
            record["resolutions"]["applied"].append({"id": identifier, "decision": decision,
                                                     **({"entry": chosen} if chosen else {})})

    def _apply(self, item: dict, kind: str, decision: str, reason: str, evidence: list[dict]) -> None:
        identifier = item["id"]
        automatic = [c for c in self.corrections if c["id"] == identifier]
        if decision == "use_document":
            for correction in automatic:
                self.corrections.remove(correction)
        elif decision == "use_glossary" and not automatic:
            passage = item["passages"]["sample"][0]
            self.corrections.append({
                "id": identifier, "at": passage["at"], "section": passage["section"], "line": passage["line"],
                "text": passage["text"], "document": passage["match"],
                "corrected": (item.get("glossary") or {}).get("excerpt"), "source": "reviewer",
                "evidence": evidence, "instruction": f"Use the glossary's statement: {reason}"})
        elif decision == "omit":
            for correction in automatic:
                self.corrections.remove(correction)
            at = [item["at"]] if kind == "claim" else [p["at"] for p in item["passages"]["sample"]]
            self.omissions.append({"id": identifier, "kind": "sentence" if kind == "claim" else "concept",
                                   "term": None if kind == "claim" else item["concept"]["term"], "at": at,
                                   "reason": reason})

    def _reference(self, where: str, reference: str) -> dict:
        match = EVIDENCE_REFERENCE.fullmatch(reference.strip())
        if not match or ".." in match.group("path").split("/"):
            raise ValueError(f"{where}: evidence {reference!r} is not raw/postgres-NN/path#Lx-Ly or a "
                             "github.com/postgres/postgres blob URL.")
        if match.group("version") and int(match.group("version")) != self.version:
            raise ValueError(f"{where}: evidence {reference!r} is not from the document's PostgreSQL "
                             f"{self.version} source tree.")
        if match.group("commit") and match.group("commit") != self.evidence.pin:
            raise ValueError(f"{where}: evidence {reference!r} is not at the document's pinned commit.")
        path = match.group("path")
        lines = [int(match.group("start")), int(match.group("end") or match.group("start"))] \
            if match.group("start") else None
        record = {"reference": reference, "path": path, "lines": lines, "url": self.evidence.url(path, lines),
                  "checked": path in self.evidence.lines}
        if record["checked"] and lines:
            count = len(self.evidence.lines[path]) - (1 if self.evidence.lines[path][-1] == "" else 0)
            if not 1 <= lines[0] <= lines[1] <= count:
                raise ValueError(f"{where}: evidence {reference!r} is outside the file ({count} lines).")
            record["excerpt"] = "\n".join(self.evidence.lines[path][lines[0] - 1:min(lines[1], lines[0] + 4)])
        return record

    # Summary -----------------------------------------------------------------------------------

    def finish(self, record: dict) -> None:
        results, claims = record["results"], record["claims"]
        record["subject"] = self._subject(results)
        record["sections"] = self._sections(results, claims)
        record["counts"] = {
            **{kind: sum(r["result"] == kind for r in results) for kind in RESULTS},
            "resolved": sum(r["resolution"]["status"] == "resolved" for r in results if r["result"] != "consistent"),
            "blocking": sum(r["blocking"] for r in results) + sum(c["blocking"] for c in claims),
            "claims": {status: sum(c["status"] == status for c in claims) for status in CLAIM_STATUSES},
            "corrections": len(self.corrections), "exceptions": len(self.exceptions),
            "omissions": len(self.omissions),
        }
        record["issues"] = self._issues(record)
        record["status"] = "needs_review" if any(i["severity"] == "blocking" for i in record["issues"]) else "passed"

    def _subject(self, results: list[dict]) -> dict:
        subject = self.matches["subject"]
        by_anchor = defaultdict(list)
        for result in results:
            if result["concept"].get("anchor") and result["check"] in ("entry", "coverage"):
                by_anchor[result["concept"]["anchor"]].append(result)
        focus = []
        for term in subject["focus_terms"]:
            related = [r for anchor in term["anchors"] for r in by_anchor[anchor]]
            related += [r for r in results if r["concept"]["kind"] != "entry"
                        and r["check"] in ("coverage", "ambiguity")
                        and _fold(r["concept"]["term"]) == _fold(term["term"])]
            worst = min((r["result"] for r in related), key=WORST.index, default=None)
            focus.append({"term": term["term"], "glossary_status": term["status"], "anchors": term["anchors"],
                          "result": worst, "results": [r["id"] for r in related]})
        return {"title": subject["title"], "question": subject["question"], "focus_terms": focus,
                "central_entries": [{"anchor": anchor, "result": min(
                    (r["result"] for r in results if r["concept"].get("anchor") == anchor), key=WORST.index,
                    default=None)} for anchor in subject["central_entries"]]}

    def _sections(self, results: list[dict], claims: list[dict]) -> list[dict]:
        sections = []
        for entry in self.document["coverage"]["sections"]:
            if entry["decision"] not in NARRATED or entry["role"] in ("reference", "navigation", "title"):
                continue
            section_claims = [c for c in claims if c["section"] == entry["section"]]
            attention = [r["id"] for r in results if r["result"] != "consistent" and r["narrated"]
                         and any(p["section"] == entry["section"] for p in r["passages"]["sample"])]
            sections.append({
                "section": entry["section"], "heading": entry["heading"], "decision": entry["decision"],
                "entries": sorted({m["anchor"] for m in self.matches["matches"] for o in m["occurrences"]
                                   if o["section"] == entry["section"]}),
                "claims": {status: sum(c["status"] == status for c in section_claims) for status in CLAIM_STATUSES},
                "attention": attention,
            })
        return sections

    def _issues(self, record: dict) -> list[dict]:
        issues = []

        def add(severity, code, message, action=None, ids=(), lines=(), evidence_needed=None):
            issues.append({"severity": severity, "code": code, "message": message, "action": action,
                           "evidence_needed": evidence_needed, "ids": list(ids),
                           "lines": sorted({line for line in lines if line})})

        version = self.version
        for result in record["results"]:
            if not result["blocking"]:
                continue
            lines = [p["line"] for p in result["passages"]["sample"]]
            code = {"conflict": "conflict_unresolved", "version_mismatch": "version_mismatch",
                    "ambiguous": "ambiguous_central",
                    "not_in_glossary": "central_concept_unsupported"}[result["result"]]
            add("blocking", code, _headline(result, version), result["resolution"]["proposal"], [result["id"]], lines,
                result["resolution"].get("evidence_needed"))
        for claim in record["claims"]:
            if claim["blocking"]:
                add("blocking", f"central_claim_{claim['status']}",
                    f"Central claim on line {claim['line']} is {claim['status']}: {claim['text']}",
                    claim["resolution"]["proposal"], [claim["id"]], [claim["line"]],
                    claim["resolution"].get("evidence_needed"))
        grouped = [
            ("warning", "correction_from_pinned_source",
             lambda r: r["resolution"].get("by") == "pinned_source" and r["resolution"].get("winner") != "document",
             "The pinned source contradicts {n} narrated statement(s); the script must use the corrected values: "),
            ("warning", "version_mismatch_qualified",
             lambda r: r["result"] == "version_mismatch" and r["resolution"].get("by") == "document_qualifier",
             "{n} term(s) name a concept the glossary limits to other versions; the document qualifies each mention: "),
            ("warning", "conflict_unresolved",
             lambda r: r["result"] == "conflict" and r["resolution"]["status"] == "unresolved" and not r["blocking"],
             "{n} conflict(s) outside the narration are unresolved: "),
            ("warning", "concept_unsupported",
             lambda r: r["result"] == "not_in_glossary" and r["narrated"] and not r["blocking"]
             and r["resolution"]["status"] == "unresolved",
             "The glossary does not cover {n} narrated concept(s) for PostgreSQL {v}, and the document's cited "
             "PostgreSQL {v} files do not show them: "),
            ("note", "glossary_corrected_by_source",
             lambda r: r["resolution"].get("by") == "pinned_source" and r["resolution"].get("winner") == "document",
             "The pinned source supports the document over the glossary in {n} case(s); the glossary should be "
             "corrected: "),
            ("note", "coverage_exceptions",
             lambda r: r["resolution"]["status"] == "accepted_exception" and r["narrated"],
             "{n} narrated concept(s) are not in the glossary for PostgreSQL {v} but appear in the document's "
             "pinned evidence; they are allowed as documented exceptions: "),
            ("warning", "ambiguous_central_words",
             lambda r: r["result"] == "ambiguous" and r["tier"] == "central" and not r["blocking"]
             and r["resolution"].get("by") != "reviewer",
             "{n} ordinary word(s) in the title, question, or conclusions match glossary entries only ambiguously; "
             "the script must explain them from the document, not from the glossary: "),
            ("note", "ambiguous_terms",
             lambda r: r["result"] == "ambiguous" and r["tier"] != "central" and r["narrated"]
             and r["resolution"].get("by") != "reviewer",
             "{n} narrated word(s) match glossary entries only ambiguously; the script must not introduce their "
             "glossary definitions: "),
            ("note", "question_terms",
             lambda r: r["result"] == "not_in_glossary" and r["resolution"].get("by") == "question",
             "{n} term(s) from the question are neither in the glossary nor in the pinned evidence; the script may "
             "repeat them but must explain them only from the document: "),
            ("note", "example_terms",
             lambda r: r["result"] == "not_in_glossary" and r["resolution"].get("by") == "example",
             "{n} term(s) come from the document's own example code rather than PostgreSQL's source: "),
            ("note", "negated_terms",
             lambda r: r["result"] == "not_in_glossary" and r["resolution"].get("by") == "negated",
             "The document names {n} term(s) only to say they are absent: "),
        ]
        for severity, code, test, message in grouped:
            found = [r for r in record["results"] if test(r)]
            if found:
                names = ", ".join(dict.fromkeys(f"`{r['concept']['term']}`" for r in found))
                add(severity, code, message.format(n=len(found), v=version) + names + ".",
                    ids=[r["id"] for r in found], lines=[p["line"] for r in found for p in r["passages"]["sample"][:1]])
        contradicted = [r for r in record["results"] if (r.get("definition") or {}).get("contradicted")]
        if contradicted:
            add("warning", "definition_contradicted", "The pinned source contradicts the glossary definitions of "
                + ", ".join(f"#{r['concept']['anchor']}" for r in contradicted) + "; the script may name these terms "
                "but must not use those definitions.", ids=[r["id"] for r in contradicted])
        claims = [c for c in record["claims"] if not c["blocking"] and c["resolution"].get("by") != "reviewer"]
        for code, severity, test, message in (
            ("central_claims_uncited", "warning", lambda c: c["status"] == "uncited" and c["central"],
             "central sentence(s) name nothing that can be looked up and cite no PostgreSQL source in their "
             "section; the script must keep them as the document's own conclusions, not as source facts."),
            ("claims_unconfirmed", "warning", lambda c: c["status"] == "unconfirmed",
             "narrated sentence(s) are unconfirmed: some identifiers or numbers were not found in the pinned "
             "evidence."),
            ("claims_uncited", "note", lambda c: c["status"] == "uncited" and not c["central"],
             "narrated sentence(s) cite no PostgreSQL source in their section."),
        ):
            found = [c for c in claims if test(c)]
            if found:
                add(severity, code, f"{len(found)} {message}", ids=[c["id"] for c in found],
                    lines=[c["line"] for c in found])
        if self.matches["glossary"].get("verified") is False:
            add("note", "glossary_unverified", "The glossary declares `verified: false`; agreement with it is a "
                "consistency result, and narrated claims rest on the document's PostgreSQL "
                f"{version} citations.")
        applied = record["resolutions"]["applied"]
        if applied:
            add("note", "resolutions_applied", f"{len(applied)} documented resolution(s) from {RESOLUTIONS} were "
                "applied.", ids=[a["id"] for a in applied])
        return sorted(issues, key=lambda issue: SEVERITIES.index(issue["severity"]))


class ClaimRecheck:
    """Repeat the claim and parameter checks for sentences that a script rewrites (Step 7).

    Uses the same verified inputs as the cross-check: document.json and
    glossary-matches.json at the SHA-256 values in the manifest, and the run's
    snapshot copies of the cited PostgreSQL files.
    """

    def __init__(self, root: Path, run_dir: Path):
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        document = json.loads(_recorded(run_dir, "document.json", manifest.get("document") or {}))
        matches = json.loads(_recorded(run_dir, "glossary-matches.json", manifest.get("glossary") or {}))
        sources = json.loads((run_dir / "sources.json").read_text(encoding="utf-8"))
        self.evidence = _Evidence(root, run_dir, sources, document)
        self._checker = _Checker(document, matches, self.evidence)

    def check(self, text: str, *, section: str | None, citations=(), block_citations=()) -> dict:
        """Check display text against its citations: the sentence's own, else its paragraph's, else its section's."""
        unit = {"section": section, "citations": list(citations), "block_citations": list(block_citations)}
        cited, scope = self._checker._cited(unit)
        items, status = self._checker.claim(text, cited, scope)
        facts = []
        for _number, fact in self._checker._paragraph_facts([text], self._checker.focus_setting, pronoun_only=True):
            source, where = self._checker._source(fact["setting"], fact["attribute"])
            if source is None:
                continue
            facts.append({"setting": fact["setting"], "attribute": fact["attribute"], "stated": fact["raw"],
                          "source": _display(source), "same": _same(_in_unit(fact["value"], source), source),
                          "evidence": where})
        return {"status": status, "citation_scope": scope, "citation_count": len(cited), "items": items,
                "facts": facts}

    def find(self, text: str) -> list[dict]:
        """Look up a text's identifiers, numeric code, and quoted strings anywhere in the pinned evidence."""
        return [{"text": item["text"], "kind": item["kind"], **self.evidence.find(item, [])} for item in _items(text)]


def _public(value: dict | None) -> dict | None:
    if not value:
        return None
    return {key: value[key] for key in ("kind", "value", "unit", "raw") if value.get(key) is not None}


def _headline(result: dict, version: int) -> str:
    term = result["concept"]["term"]
    if result["check"].startswith("fact:"):
        return f"`{term}` {result['attribute']}: the document and the glossary disagree."
    return {
        "acronym": f"The document's expansion of {term} differs from the glossary's.",
        "role": f"The document and the glossary give {term} different roles.",
        "entry": f"The glossary says {term} is not present in PostgreSQL {version}, but the document narrates it.",
        "alias_version": f"The glossary limits the name {term!r} to other PostgreSQL versions.",
        "ambiguity": f"The central term {term!r} matches glossary entries ambiguously.",
        "coverage": f"The central concept {term!r} is not in the glossary for PostgreSQL {version}, and the "
                    "document's pinned evidence does not show it.",
    }[result["check"]]


def _load_resolutions(run_dir: Path) -> dict | None:
    path = run_dir / RESOLUTIONS
    if path.is_symlink():
        raise ValueError(f"{RESOLUTIONS} must be a regular file in the run directory, not a symlink.")
    if not path.exists():
        return None
    data = path.read_bytes()
    if len(data) > MAX_RESOLUTIONS_BYTES:
        raise ValueError(f"{RESOLUTIONS} is larger than {MAX_RESOLUTIONS_BYTES} bytes.")
    try:
        loaded = yaml.load(data.decode("utf-8"), Loader=_FrontMatterLoader)
    except MarkdownError as error:
        raise ValueError(f"{RESOLUTIONS} must not use YAML aliases.") from error
    except (yaml.YAMLError, UnicodeDecodeError) as error:
        raise ValueError(f"{RESOLUTIONS} is not valid UTF-8 YAML: {error}") from error
    if loaded is None:
        loaded = {"resolutions": []}
    if not isinstance(loaded, dict) or set(loaded) - {"resolutions"} or not isinstance(
            loaded.get("resolutions", []), list):
        raise ValueError(f"{RESOLUTIONS} must be a mapping with one key, `resolutions`, holding a list.")
    return {"resolutions": loaded.get("resolutions") or [], "sha256": hashlib.sha256(data).hexdigest()}


def _update_manifest(root: Path, run_dir: Path, *, status: str, record: dict | None = None,
                     digest: str | None = None, error: str | None = None) -> dict:
    path = run_dir / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    manifest["status"] = {"passed": "glossary_checked"}.get(status, status)
    invalidate_after(manifest, "glossary_check")
    entry: dict = {"status": status}
    if error:
        entry["error"] = error
    if record:
        entry.update({
            "record": "glossary-check.json", "report": "glossary-check.md", "sha256": digest,
            "checked_at": record["checked_at"], "schema": record["schema"], "version": record["version"],
            "inputs": {"document": manifest.get("document", {}).get("sha256"),
                       "glossary_matches": manifest.get("glossary", {}).get("sha256")},
            "resolutions": record["resolutions"], "counts": record["counts"],
            "issues": {severity: sum(issue["severity"] == severity for issue in record["issues"])
                       for severity in SEVERITIES},
        })
    manifest["glossary_check"] = entry
    write_atomic(root, run_dir.relative_to(root) / "manifest.json",
                 (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"), label="Request")
    return entry


# Report -----------------------------------------------------------------------------------------


def _cell(text) -> str:
    return " ".join(str(text if text is not None else "—").split()).replace("|", "\\|")


def _render(record: dict) -> str:
    document, glossary, counts = record["document"], record["glossary"], record["counts"]
    version = record["version"]
    blocking = [issue for issue in record["issues"] if issue["severity"] == "blocking"]
    claims = counts["claims"]
    lines = [
        "# Glossary Cross-Check", "",
        f"- Request: `{record['request_id']}`",
        f"- Status: **{record['status']}**" + (f": resolve {len(blocking)} blocking issue(s) before narration."
                                               if blocking else ""),
        f"- Document: [`{document['path']}`]({document['url']}) at wiki commit `{document['wiki_commit']}`, "
        f"PostgreSQL {version}, source pin `{(document.get('pinned_commit') or 'none')[:12]}`",
        f"- Glossary: [`{glossary['path']}`]({glossary['url']}), `verified: {json.dumps(glossary['verified'])}`",
        "- Method: deterministic checks only; no language model. Agreement with the glossary is a consistency "
        f"result, not proof; narrated claims rest on the document's PostgreSQL {version} citations.",
        f"- Results: {counts['consistent']} consistent, {counts['conflict']} conflict, {counts['version_mismatch']} "
        f"version mismatch, {counts['ambiguous']} ambiguous, {counts['not_in_glossary']} not in glossary "
        f"({counts['resolved']} resolved)",
        f"- Narrated claims: {claims['verified']} verified in their cited lines or files, {claims['supported']} "
        f"supported by other pinned evidence, {claims['cited']} cited with nothing to check, "
        f"{claims['unconfirmed']} unconfirmed, {claims['uncited']} uncited",
        f"- Script inputs: {counts['corrections']} correction(s), {counts['exceptions']} glossary exception(s), "
        f"{counts['omissions']} omission(s)",
        "- Resolutions: " + (f"`{RESOLUTIONS}` ({len(record['resolutions']['applied'])} applied)"
                             if record["resolutions"]["file"] else f"none (`{RESOLUTIONS}` is absent)"),
    ]
    items = {item["id"]: item for item in [*record["results"], *record["claims"]]}
    for severity, heading in (("blocking", "Blocking Issues"), ("warning", "Warnings"), ("note", "Notes")):
        issues = [issue for issue in record["issues"] if issue["severity"] == severity]
        if not issues:
            continue
        lines += ["", f"## {heading}", ""]
        if severity == "blocking":
            lines += [f"Record a decision for each issue in this run's `{RESOLUTIONS}`, as items of a top-level "
                      "`resolutions:` list, then run `scripts/pgvideo resume --request "
                      f"{record['request_id']}`. Evidence must come from `raw/postgres-{version}/` at the pin.", ""]
        for issue in issues:
            where = f" (line{'s' if len(issue['lines']) > 1 else ''} {', '.join(map(str, issue['lines'][:8]))})" \
                if issue["lines"] else ""
            lines.append(f"- `{issue['code']}`{where}: {issue['message']}")
            if severity != "blocking":
                continue
            item = items[issue["ids"][0]]
            for passage in (item["passages"]["sample"][:2] if "passages" in item else []):
                lines.append(f"  - Document, line {passage['line']} (`{passage['at']}`): {passage['text']}")
            if item.get("glossary"):
                g = item["glossary"]
                lines.append(f"  - Glossary [#{g['anchor']}]({g['url']}) ({g['source']}, {g['version_status']}): "
                             f"{g['excerpt']}")
            if issue["action"]:
                lines.append(f"  - Proposed resolution: {issue['action']}")
            if issue["evidence_needed"]:
                lines.append(f"  - Evidence needed: {issue['evidence_needed']}")
            kind = "claim" if item["id"].startswith("claim@") else item["result"]
            decision = DECISIONS[kind][0]
            lines += ["  - Record a resolution:", "", "    ```yaml", f"    - id: {json.dumps(item['id'])}",
                      f"      decision: {decision}  # or: {', '.join(DECISIONS[kind][1:])}",
                      "      reason: \"...\""]
            if decision in EVIDENCE_DECISIONS and kind != "ambiguous":
                lines.append(f"      evidence: raw/postgres-{version}/path/to/file#L1-L2")
            lines += ["    ```", ""]
    subject = record["subject"]
    lines += ["", "## Subject", "", f"- Title: {subject['title']}"]
    if subject["question"]:
        lines.append(f"- Question: {subject['question']}")
    if subject["focus_terms"]:
        lines += ["", "| Focus term | Glossary | Result |", "|---|---|---|"]
        for term in subject["focus_terms"]:
            entries = ", ".join("#" + anchor for anchor in term["anchors"]) or term["glossary_status"]
            lines.append(f"| `{_cell(term['term'])}` | {_cell(entries)} | {_cell(term['result'])} |")
    entries = [r for r in record["results"] if r["concept"]["kind"] == "entry" and r["check"] in ("entry", "coverage")]
    if entries:
        lines += ["", "## Glossary Entries", "",
                  f"| Entry | Tier | Result | PostgreSQL {version} scope | Definition use | Basis |",
                  "|---|---|---|---|---|---|"]
        for result in entries:
            g = result["glossary"]
            others = [r["result"] for r in record["results"] if r["concept"].get("anchor") == g["anchor"]]
            worst = min(others, key=WORST.index)
            lines.append(f"| [{_cell(g['term'])}]({g['url']}) | {result['tier']} | {worst} | {g['version_status']} | "
                         f"{result['definition']['use']} | {_cell('; '.join(result.get('basis', [])[2:]) or '—')} |")
    facts = [r for r in record["results"] if r["check"].startswith("fact:")]
    if facts:
        lines += ["", "## Configuration Facts", "",
                  "| Line | Parameter | Attribute | Document | Glossary | Pinned source | Result |",
                  "|---|---|---|---|---|---|---|"]
        for result in facts:
            glossary_values = "; ".join(f"{_display(g['value'])} (#{g['anchor']}, {g['source']})"
                                        for g in result["glossary_values"]) or "—"
            source = _display(result["source_value"])
            if result["evidence"]:
                source = f"[{source}]({result['evidence'][0]['url']})"
            outcome = result["result"] + (f", resolved: {result['resolution']['winner']}"
                                          if result["resolution"].get("winner") else "")
            line = result["passages"]["sample"][0]["line"]
            lines.append(f"| {line} | `{result['setting']}` | {result['attribute']} | "
                         f"{_cell(_display(result['document_value']))} | {_cell(glossary_values)} | {_cell(source)} | "
                         f"{outcome} |")
    others = [r for r in record["results"] if r["check"] in ("acronym", "role", "alias_version")]
    if others:
        lines += ["", "## Acronyms, Roles, And Version-Limited Names", ""]
        for result in others:
            passage = result["passages"]["sample"][0]
            lines.append(f"- {result['result']} ({result['check']}), line {passage['line']}: "
                         f"{result['resolution'].get('proposal') or result['concept']['term']}")
    if record["corrections"]:
        lines += ["", "## Corrections For The Script", "",
                  "The input snapshot is unchanged; the script must apply these corrections.", ""]
        for correction in record["corrections"]:
            source = correction["evidence"][0] if correction["evidence"] else None
            link = (f" ([{source['path']}:{source.get('line')}]({source['url']}))"
                    if source and source.get("url") else "")
            lines.append(f"- Line {correction['line']} (`{correction['at']}`): {correction['instruction']}{link}")
    gaps = [r for r in record["results"] if r["result"] == "not_in_glossary" and r["narrated"]]
    if gaps:
        lines += ["", "## Concepts Not In The Glossary", "",
                  "| Concept | Gap | Central | Pinned evidence | Result |", "|---|---|---|---|---|"]
        for result in gaps:
            found = result["evidence"][0] if result["evidence"] else None
            where = (f"[{found['path']}:{found['line']}]({found['url']}) ({found['level']}"
                     f"{'' if found['exact'] else ', case-insensitive'})") if found else "not found"
            status = {"accepted_exception": "allowed exception"}.get(result["resolution"]["status"],
                                                                     result["resolution"]["status"])
            lines.append(f"| `{_cell(result['concept']['term'])}` | {result['gap']} | "
                         f"{'yes' if result['tier'] == 'central' else 'no'} | {_cell(where)} | {status} |")
    ambiguous = [r for r in record["results"] if r["result"] == "ambiguous" and r["narrated"]]
    if ambiguous:
        lines += ["", "## Ambiguous Terms", "", "| Term | Central | Candidates | Occurrences |", "|---|---|---|---|"]
        for result in ambiguous:
            lines.append(f"| {_cell(result['concept']['term'])} | {'yes' if result['tier'] == 'central' else 'no'} | "
                         f"{_cell(', '.join('#' + c['anchor'] for c in result['candidates']))} | "
                         f"{result['passages']['count']} |")
    attention = [c for c in record["claims"] if c["status"] in ("unconfirmed", "uncited")]
    if attention:
        lines += ["", "## Claims Needing Attention", ""]
        for claim in attention:
            missing = [item["text"] for item in claim["items"] if not item["level"]]
            detail = f"; not found at the pin: {', '.join(f'`{m}`' for m in missing)}" if missing else ""
            lines.append(f"- Line {claim['line']} (`{claim['at']}`, {claim['status']}"
                         f"{', central' if claim['central'] else ''}{detail}): {claim['text']}")
    if record["resolutions"]["applied"]:
        lines += ["", "## Resolutions Applied", ""]
        for applied in record["resolutions"]["applied"]:
            item = items[applied["id"]]
            resolution = item["resolution"]
            refs = ", ".join(f"[{e['reference']}]({e['url']})" + ("" if e["checked"] else " (not in the snapshot)")
                             for e in resolution["evidence"])
            lines.append(f"- `{applied['id']}`: {applied['decision']}"
                         + (f" #{applied['entry']}" if applied.get("entry") else "")
                         + f" — {resolution['reason']}" + (f" Evidence: {refs}." if refs else ""))
    return "\n".join(lines) + "\n"
