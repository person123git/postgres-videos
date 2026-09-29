"""Parse the selected document into sections, blocks, and extracted facts (Step 4).

The parser reads the run's read-only snapshot copy of the document, never the
network. Every section and block gets a stable ID and its original line range.
Prose is split into sentences. A sentence's display text keeps inline code in
backticks and drops citation links, which it records by link ID instead. Its
spoken text also drops bare URLs, and it is null when the sentence is not for
narration: maintenance instructions, navigation, reference lists, and front
matter never reach the narration.

document.json then lists the central question, conclusions, technical terms,
numerical claims, examples, version restrictions, and open questions, each
linked to the sentence or block it came from, plus a coverage map that decides
which sections the narration explains, summarizes, or omits. coverage.md
renders the map for review.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .markdown import block_tree, split_front_matter
from .paths import project_directory
from .snapshot import resolve_links
from .sources import POSTGRES_REPOSITORY, blob_url, write_atomic
from .stages import invalidate_after

SCHEMA_VERSION = 1
# How much of the page a request narrates (`generate --detail`). A summary keeps the key points, the
# standard level condenses pages that exceed its target, and full detail narrates every section.
DETAILS = ("summary", "standard", "full")
DEFAULT_DETAIL = "standard"
WORDS_PER_MINUTE = 150
TARGET_MINUTES = (6, 10)
SUMMARY_TARGET_MINUTES = (1, 3)
# Spoken words planned for explaining one displayed code block or image. A table is planned at the words
# the drafter reads from its rows.
DISPLAY_WORDS = 25
SUMMARY_RATIO = 0.25
SUMMARY_MIN_WORDS = 40
SUMMARY_MAX_WORDS = 150
# The question and the open questions are explained in full up to these lengths and summarized beyond them.
QUESTION_WORDS = 150
OPEN_QUESTION_WORDS = 80

# Top-level wiki headings with a fixed purpose. Subsections inherit their parent's role,
# and any other top-level heading is content.
ROLES = {
    "question": "question", "questions": "question",
    "short answer": "summary", "answer up front": "summary", "summary": "summary", "definition": "summary",
    "open questions": "open_questions",
    "measurement script": "measurement",
    "context reviewed": "reference", "evidence map": "reference", "source references": "reference",
    "source pin": "reference", "source pins": "reference",
    "contents": "navigation", "table of contents": "navigation", "navigation": "navigation",
    "related pages": "navigation",
}
DECISIONS = ("explain", "summarize", "omit", "exclude")

# Wiki upkeep rather than subject matter: agent instructions, prompt-hygiene records, and tooling.
MAINTENANCE_SENTENCE = re.compile(
    r"(?i:agents\.md|wiki_lint|verified_by_agent|\blog\.md\b|prompt[- ]hygiene"
    r"|\b(?:user|asker)\b[^.]{0,40}\bapprov|\bthe asker\b)|\bMANDATORY [A-Z]"
)
MAINTENANCE_PARAGRAPH = re.compile(
    r"(?i)^(?:prompt[- ]hygiene note|prompt note|review prompt|follow-up note|filed after|(?:light-)?copyedit note"
    r"|the prompt is restated|the original (?:prompt|request)|every prompt on this page|scope,? settled)"
)
# Records of how the prompt was filed. Matched only in Question sections, where the wiki keeps them;
# the same words elsewhere can be subject matter.
PROMPT_RECORD = re.compile(
    r"(?i)\bscoping answers?\b|\bscope,? settled\b|\bsettled the scope\b|\bcorrected (?:and restated|silently"
    r"|text|form|wording|the same way)\b|\brestate(?:d|ment)\b|\bprompts? (?:read|wrote|was filed|were filed"
    r"|drove)\b|^filed\b|\b(?:is|was|were) filed\b|copy-?edit|\byou approved\b|\bno meaning was changed\b"
    r"|\.wiki-runtime|\bthe (?:original|first|second|third|fourth|fifth|follow-up) (?:prompt|request)\b"
    r"|\bdefects were\b|\bits defects\b"
)
# Headings of sections that state a limit or exception; they are summarized at least, even over the target.
CAVEAT_HEADING = re.compile(
    r"(?i)\b(?:caveats?|limitations?|limits|pitfalls?|traps?|gotchas?|edge cases?|warnings?|restrictions?"
    r"|unsafe|known issues?)\b|\bdoes not (?:cover|work)\b"
)
SUPPORTING_HEADING = re.compile(
    r"(?i)\b(?:tests?|testing|measured|measurement|history|commits?|appendix|reproduction|harness"
    r"|fixtures?|methodology|oracle)\b"
)
NONE_ITEM = re.compile(r"(?i)^(?:none|n/a|no open questions)\W*$")
# Rendered text kept only while extracting; see _render.
PRIVATE_KEYS = ("_plain", "_prose", "_numeric", "_codes")

# Private-use markers for inline code and citations while sentences are split.
CODE, CODE_END, CITE, CITE_END = "\ue000", "\ue001", "\ue002", "\ue003"
# Numeric inline code, such as `1024`, stays between these markers in the text searched for quantities.
NUMERIC_START, NUMERIC_END = "\ue004", "\ue005"
CODE_MARK = re.compile(f"{CODE}(\\d+){CODE_END}")
CITE_MARK = re.compile(f"{CITE}(\\d+){CITE_END}")
BOUNDARY = re.compile(r"[.!?][\"'”’)\]]*\s+")
SENTENCE_START = f"\"'“‘([*_{CODE}{CITE}"
ABBREVIATIONS = {"e.g", "i.e", "etc", "vs", "cf", "approx", "fig", "al", "incl", "resp"}
LINE_BREAK = re.compile(r"(?i)<br\s*/?>")
URL = re.compile(r"(?i)\b(?:https?://|www\.)\S+")

SQL_KEYWORDS = {
    "SELECT", "INSERT", "UPDATE", "DELETE", "MERGE", "CREATE", "DROP", "ALTER", "INDEX", "TABLE", "VACUUM",
    "ANALYZE", "ANALYSE", "EXPLAIN", "REINDEX", "CLUSTER", "TRUNCATE", "FULL", "CONCURRENTLY", "NULL", "WHERE",
    "FROM", "JOIN", "RESET", "SHOW", "WITH", "GROUP", "ORDER", "LIMIT", "UNION", "VALUES", "BEGIN", "COMMIT",
    "ROLLBACK", "COPY", "GRANT", "REVOKE", "LOCK", "PREPARE", "EXECUTE", "DEALLOCATE", "LISTEN", "NOTIFY",
    "CHECKPOINT", "REFRESH", "MATERIALIZED", "VIEW", "PARTITION", "ATTACH", "DETACH", "PRIMARY", "FOREIGN",
    "REFERENCES", "UNIQUE", "DEFAULT", "BUFFERS", "COSTS", "TIMING", "VERBOSE", "REPACK", "USING", "INCLUDE",
    "TRUE", "FALSE", "EXISTS", "CASE", "WHEN", "THEN", "ELSE", "DISTINCT", "HAVING", "OVER", "RETURNING",
    "TEMP", "TEMPORARY", "UNLOGGED", "SEQUENCE", "SCHEMA", "DATABASE", "ROLE", "USER", "POLICY", "FUNCTION",
    "PROCEDURE", "TRIGGER", "EXTENSION", "TYPE", "DOMAIN", "CALL", "LOAD", "DISCARD", "SECURITY", "LABEL",
    "COMMENT", "IMPORT", "CAST", "BETWEEN", "LIKE", "ILIKE", "ROWS", "ONLY", "NOWAIT", "SKIP", "LOCKED",
    "SHARE", "EXCLUSIVE", "ACCESS", "MODE", "INTO", "TABLESPACE", "OWNER", "RENAME", "COLUMN", "CONSTRAINT",
    "CHECK", "BIGINT", "INTEGER", "TEXT", "BOOLEAN", "NUMERIC", "SERIAL",
}
# Short capitalized words that are SQL connectives rather than terms.
SHORT_WORDS = {"SET", "OR", "AND", "NOT", "DO", "ON", "IN", "IS", "AS", "BY", "ALL", "ANY", "FOR", "KEY", "ROW",
               "END", "ADD", "USE", "NO", "IF", "OF", "TO", "AT"}
SQL_START = re.compile(r"(?i)^(?:SELECT|INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|VACUUM|ANALY[SZ]E|EXPLAIN"
                       r"|REINDEX|CLUSTER|TRUNCATE|WITH|SET|RESET|SHOW|BEGIN|COMMIT|COPY|GRANT|REVOKE|LOCK"
                       r"|PREPARE|EXECUTE|CALL|DO|REFRESH|CHECKPOINT|REPACK)\b")
# Box-drawing characters and arrows that mark a plain-text block as a diagram.
DIAGRAM = re.compile(r"[─│┌┐└┘├┤┬┴┼═║╔╗╚╝→←↑↓▶▼►◄]|-->|==>|\+--")
FILE_EXTENSIONS = {"c", "h", "y", "l", "sgml", "sql", "out", "conf", "sample", "dat", "md", "pl", "pm", "py",
                   "sh", "txt", "json", "yaml", "control", "spec", "source", "in", "ac", "mk", "build"}
PROPER_NAMES = {"PostgreSQL", "GitHub", "macOS", "JavaScript", "TypeScript", "iOS", "YouTube", "OpenSSL"}
# Identifier shapes worth listing when they appear outside inline code.
SNAKE_CASE = re.compile(r"(?<![\w.$/-])[a-z][a-z0-9]*(?:_[a-z0-9]+)+(?:\(\))?(?![\w$/-])")
CAMEL_CASE = re.compile(
    r"(?<![\w.$/-])(?:[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+|[a-z]+(?:[A-Z][a-z0-9]*)+)(?:\(\))?(?![\w$/-])")
CONSTANT = re.compile(r"(?<![\w$])[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+(?![\w$])")
ACRONYM = re.compile(r"(?<![\w/])(?:I/O|[A-Z]{2,}[0-9]*)(?=s?(?![\w/]))")
CODE_IDENTIFIER = re.compile(r"(?<![\w$])[A-Za-z_][\w$]*(?![\w$])(\s*\()?")
TERM_KINDS = ("setting", "function", "constant", "qualified_name", "identifier", "path", "sql", "sql_keyword",
              "acronym", "literal", "glossary_link")

UNITS = {
    "%": "%", "percent": "%", "B": "bytes", "byte": "bytes", "bytes": "bytes", "kB": "kB", "KB": "kB",
    "KiB": "kB", "MB": "MB", "MiB": "MB", "GB": "GB", "GiB": "GB", "TB": "TB", "TiB": "TB", "bit": "bits",
    "bits": "bits", "ms": "ms", "millisecond": "ms", "milliseconds": "ms", "us": "us", "µs": "us",
    "microsecond": "us", "microseconds": "us", "s": "s", "sec": "s", "second": "s", "seconds": "s",
    "min": "min", "minute": "min", "minutes": "min", "h": "h", "hour": "h", "hours": "h", "day": "days",
    "days": "days", "page": "pages", "pages": "pages", "block": "blocks", "blocks": "blocks", "row": "rows",
    "rows": "rows", "tuple": "tuples", "tuples": "tuples", "entry": "entries", "entries": "entries",
    "buffer": "buffers", "buffers": "buffers", "slot": "slots", "slots": "slots", "connection": "connections",
    "connections": "connections", "backend": "backends", "backends": "backends", "process": "processes",
    "processes": "processes", "worker": "workers", "workers": "workers", "partition": "partitions",
    "partitions": "partitions", "item": "items", "items": "items", "key": "keys", "keys": "keys",
    "column": "columns", "columns": "columns", "character": "characters", "characters": "characters",
    "char": "characters", "chars": "characters", "times": "times", "x": "times", "×": "times",
    "line": "lines", "lines": "lines", "file": "files", "files": "files", "segment": "segments",
    "segments": "segments", "index": "indexes", "indexes": "indexes", "table": "tables", "tables": "tables",
}
UNIT = re.compile(f"{NUMERIC_END}?" + r"\s?-?(%|×|[A-Za-zµ]+)(?![\w-])")
NUMBER = re.compile(f"(?:(?<={NUMERIC_START})-(?=\\d)|" + r"(?<![\w.$#@/\\-]))(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
NUMERIC_CODE = re.compile(r"-?\d[\d,]*(?:\.\d+)?(?:\s?-?(?:%|[A-Za-zµ]+))?")
# Words after which a bare number labels or dates something rather than counting it.
LABEL_BEFORE = re.compile(
    r"(?i)\b(?:postgresql|postgres|pg|versions?|releases?|v|rules?|famil(?:y|ies)|tests?|phases?|steps?|stages?"
    r"|sections?|figures?|fig|tables?|lines?|commits?|items?|legs?|runs?|rounds?|patch(?:es)?|options?|cases?"
    r"|examples?|quer(?:y|ies)|questions?|parts?|chapters?|appendix|number|issues?|bugs?|levels?|pass(?:es)?|attempts?"
    r"|majors?|minors?|since|before|after|until|in)\s*[#:]?\s*$"
)
DATE_OR_TIME = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?Z?)?\b|\b\d{1,2}:\d{2}(?::\d{2})?\b")

VERSION_ITEM = r"(?:PostgreSQL\s?|Postgres\s?|PG\s?|v)?\d{1,2}(?:\.\d{1,2})?(?![\d.]*\d)"
VERSION_LIST = rf"(?:(?:\s*,\s*|\s*/\s*|\s+(?:and|or|to|through|vs\.?|versus)\s+){VERSION_ITEM})*"
VERSION = re.compile(
    rf"\b(?:PostgreSQL|Postgres|PG)\s?\d{{1,2}}(?:\.\d{{1,2}})?(?![\d.]*\d){VERSION_LIST}"
    rf"|\bv\d{{1,2}}(?:\.\d{{1,2}})?\b{VERSION_LIST}"
    rf"|\b(?:[Vv]ersions?|[Rr]eleases?|[Mm]ajors?)\s+\d{{1,2}}(?:\.\d{{1,2}})?(?![\d.]*\d){VERSION_LIST}"
    r"|\bREL_?\d{1,2}(?:_\d+)?_STABLE\b"
    r"|\b(?:[Ss]ince|[Bb]efore|[Aa]fter|[Uu]ntil|[Aa]s of|[Pp]rior to|[Ss]tarting (?:with|in)|[Ii]ntroduced in"
    r"|[Aa]dded in|[Rr]emoved in|[Cc]hanged in|[Nn]ew in)\s+\d{1,2}(?:\.\d{1,2})?(?![\d.]*\d)(?!\s*(?:%|[A-Za-z]))"
)
VERSION_NUMBER = re.compile(r"(?<![\w.])(?:REL_?)?(\d{1,2}(?:\.\d{1,2})?)(?![\d])")
VERSION_QUALIFIER = re.compile(
    r"(?i)\b(since|before|after|until|as of|prior to|starting|from|through|up to|introduced|added|removed"
    r"|changed|new in|older|newer|earlier|later|both|between|unlike|differs?)\b"
)

GUC_SOURCES = {
    "src/backend/utils/misc/guc_tables.c": re.compile(rb'\{\s*"([A-Za-z_][A-Za-z0-9_.]*)"\s*,\s*PGC_[A-Z_]+'),
    "src/backend/utils/misc/guc.c": re.compile(rb'\{\s*"([A-Za-z_][A-Za-z0-9_.]*)"\s*,\s*PGC_[A-Z_]+'),
    "src/backend/utils/misc/guc_parameters.dat": re.compile(rb"\bname\s*=>\s*'([A-Za-z_][A-Za-z0-9_.]*)'"),
    "src/backend/utils/misc/postgresql.conf.sample": re.compile(rb"(?m)^#?([a-z_][a-z0-9_]*)\s*="),
}
SETTING_CONTEXT = re.compile(r"\b(?:GUCs?|settings?|parameters?|configuration)\b", re.IGNORECASE)


def parse_document(root: Path, run_dir: Path) -> dict:
    """Write document.json and coverage.md for a run whose source snapshot passed.

    Returns the manifest's document record, whose status is 'passed', or
    'needs_review' when the document has nothing to narrate. A missing or
    altered snapshot copy marks the manifest 'failed' and raises.
    """
    try:
        return _parse(root, run_dir)
    except (ValueError, OSError) as error:
        _update_manifest(root, run_dir, status="failed", error=str(error))
        raise


def _parse(root: Path, run_dir: Path) -> dict:
    sources = json.loads((run_dir / "sources.json").read_text(encoding="utf-8"))
    if sources.get("status") != "passed":
        raise ValueError(f"The source snapshot has status '{sources.get('status')}'; resolve source-report.md first.")
    body = _snapshot_text(root, run_dir, sources["document"])
    _front, body = split_front_matter(body)
    builder = _Builder(sources, body, _setting_names(root, run_dir, sources), detail=_detail(run_dir))
    record = builder.build()
    data = (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    relative = run_dir.relative_to(root)
    write_atomic(root, relative / "document.json", data, label="Request")
    write_atomic(root, relative / "coverage.md", _render_coverage(record).encode("utf-8"), label="Request")
    return _update_manifest(root, run_dir, status=record["status"], record=record,
                            digest=hashlib.sha256(data).hexdigest())


def _detail(run_dir: Path) -> str:
    """Return the request's level of detail; requests made before the setting existed use the default."""
    path = run_dir / "request.json"
    settings = (json.loads(path.read_text(encoding="utf-8")).get("settings") or {}) if path.is_file() else {}
    detail = settings.get("detail", DEFAULT_DETAIL)
    if detail not in DETAILS:
        raise ValueError(f"request.json asks for an unknown level of detail {detail!r}; "
                         f"use one of {', '.join(DETAILS)}.")
    return detail


def _snapshot_input(root: Path, run_dir: Path, entry: dict) -> bytes:
    """Read a run input, checking its location and its recorded SHA-256."""
    relative = run_dir.relative_to(root) / Path(*entry["input"].split("/"))
    parent = project_directory(root, relative.parent, label="Request input")
    data = (parent / relative.name).read_bytes()
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise ValueError(f"The snapshot copy {entry['input']} does not match its recorded SHA-256.")
    return data


def _snapshot_text(root: Path, run_dir: Path, entry: dict) -> str:
    return _snapshot_input(root, run_dir, entry).decode("utf-8").removeprefix("\ufeff")


def _setting_names(root: Path, run_dir: Path, sources: dict) -> tuple[set[str], list[str]]:
    """Return the configuration parameter names defined in cited GUC sources at the pinned commit."""
    names: set[str] = set()
    used = []
    for entry in (sources.get("postgres") or {}).get("files", []):
        pattern = GUC_SOURCES.get(entry["path"])
        if pattern:
            names.update(name.decode("ascii") for name in pattern.findall(_snapshot_input(root, run_dir, entry)))
            used.append(entry["path"])
    return names, used


def _backticks(code: str) -> str:
    fence = "``" if "`" in code else "`"
    padding = " " if code.startswith("`") or code.endswith("`") else ""
    return f"{fence}{padding}{code}{padding}{fence}"


def _tidy(text: str) -> str:
    """Normalize spacing and punctuation left behind by removed citations."""
    text = re.sub(r"\s+", " ", text)
    # Brackets left empty by removed citations; `f()` and `a[]` keep theirs.
    text = re.sub(r"(?<![\w)\]])\(\s*(?:(?:see|also|and|or|cf\.)\s*|[,;]\s*)*\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<![\w)\]])\[\s*(?:[,;]\s*)*\]", "", text)
    text = re.sub(r"\s+([,.;:!?)\]])", r"\1", text)
    text = re.sub(r"([(\[])\s+", r"\1", text)
    text = re.sub(r"([,;])(?:\s*[,;])+", r"\1", text)
    text = re.sub(r"[,;]([.!?)\]])", r"\1", text)
    return text.strip()


def _words(text: str | None) -> int:
    return len(text.split()) if text else 0


def _heading_key(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().rstrip(":").lower()


class _Builder:
    """Build the structured record for one document."""

    def __init__(self, sources: dict, body: str, settings: tuple[set[str], list[str]], *,
                 detail: str = DEFAULT_DETAIL):
        self.sources = sources
        self.detail = detail
        self.entry = sources["document"]
        self.wiki = sources["wiki"]
        self.version = self.entry.get("version")
        self.pin = self.entry.get("pinned_commit")
        self.body_lines = body.split("\n")
        self.tree = block_tree(body)
        self.settings, self.setting_sources = settings
        self.links: list[dict] = []
        # Sentences, table rows, and headings in document order, for extraction.
        self.units: list[dict] = []
        self.sections = self._sections()
        self.by_id = {section["id"]: section for section in self.sections}

    # Structure ---------------------------------------------------------------------------------

    def _sections(self) -> list[dict]:
        headings = self.tree["headings"]
        sections: list[dict] = []
        lines = [heading["line"] for heading in headings]
        for index, heading in enumerate(headings):
            parent = sections[heading["parent"]] if heading["parent"] is not None else None
            own_end = lines[index + 1] - 1 if index + 1 < len(lines) else len(self.body_lines)
            later = [other["line"] for other in headings[index + 1:] if other["level"] <= heading["level"]]
            subtree_end = later[0] - 1 if later else len(self.body_lines)
            if parent is None and heading["level"] == 1 and not any(s["role"] == "title" for s in sections):
                role = "title"
            elif parent is None or parent["role"] == "title":
                role = ROLES.get(_heading_key(heading["text"]), "content")
            else:
                role = parent["role"]
            section = {
                "id": heading["anchor"] or f"section-{index + 1}", "heading": heading["text"], "text": None,
                "level": heading["level"], "parent": parent["id"] if parent else None, "role": role,
                "lines": [heading["line"], self._trim(heading["line"], own_end)],
                "subtree_lines": [heading["line"], self._trim(heading["line"], subtree_end)],
                "url": self._wiki_url(self.entry["path"], heading["anchor"]),
                "children": [], "blocks": [], "_index": index, "_inline": heading["inline"],
            }
            if parent:
                parent["children"].append(section["id"])
            sections.append(section)
        if any(block["heading"] is None for block in self.tree["blocks"]):
            first = next((block["lines"][0] for block in self.tree["blocks"] if block["lines"]), 1)
            end = lines[0] - 1 if lines else len(self.body_lines)
            identifier = "preamble" if "preamble" not in {s["id"] for s in sections} else "preamble-body"
            sections.insert(0, {
                "id": identifier, "heading": None, "text": None, "level": 0, "parent": None, "role": "content",
                "lines": [first, self._trim(first, end)], "subtree_lines": [first, self._trim(first, end)],
                "url": self._wiki_url(self.entry["path"]), "children": [], "blocks": [], "_index": None,
                "_inline": None,
            })
        return sections

    def _trim(self, start: int, end: int) -> int:
        while end > start and not self.body_lines[end - 1].strip():
            end -= 1
        return end

    def _wiki_url(self, path: str, fragment: str | None = None) -> str:
        url = blob_url(self.wiki["repository"], self.wiki["commit"], path)
        return f"{url}#{fragment}" if fragment else url

    def build(self) -> dict:
        offset = 1 if self.sections and self.sections[0]["_index"] is None else 0
        for section in self.sections:
            if section["_inline"] is not None:
                heading = self._fragment(section["_inline"], section["id"], section, section["id"])
                section["text"] = heading["text"]
                if section["role"] not in ("reference", "navigation"):
                    self._unit("heading", section["id"], section, section["id"], heading, [section["lines"][0]] * 2)
        counters: dict[str, int] = {}
        for block in self.tree["blocks"]:
            section = self.sections[block["heading"] + offset if block["heading"] is not None else 0]
            counters[section["id"]] = counters.get(section["id"], 0) + 1
            section["blocks"].append(self._block(block, f"{section['id']}.{counters[section['id']]}", section))
        self.units.sort(key=lambda unit: unit["lines"][0] or 0)

        terms = self._terms()
        subject = self._subject(terms)
        conclusions = self._conclusions()
        numbers = self._numbers()
        versions = self._versions()
        examples = self._examples()
        open_questions = self._open_questions()
        coverage = self._coverage(terms, subject, conclusions)
        issues = self._issues(subject, conclusions, coverage)
        for section in self.sections:
            for key in ("_index", "_inline"):
                section.pop(key)
        postgres = self.sources.get("postgres") or {}
        return {
            "schema": SCHEMA_VERSION,
            "request_id": self.sources["request_id"],
            "status": "needs_review" if any(issue["severity"] == "blocking" for issue in issues) else "passed",
            "parsed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "document": {
                "path": self.entry["path"], "url": self.entry["url"], "wiki_commit": self.wiki["commit"],
                "input": self.entry["input"], "sha256": self.entry["sha256"], "title": self.entry.get("title"),
                "type": self.entry.get("type"), "version": self.version, "pinned_commit": self.pin,
                "source_version": postgres.get("source_version"), "verification": self.entry.get("verification", {}),
                "front_matter": self.entry.get("front_matter"),
                "lines": len(self.body_lines) - (1 if self.body_lines[-1] == "" else 0),
            },
            "subject": subject,
            "conclusions": conclusions,
            "version_scope": {
                "version": self.version, "pinned_commit": self.pin, "source_version": postgres.get("source_version"),
                "other_versions_mentioned": sorted({v for entry in versions for v in entry["other_versions"]},
                                                   key=_version_key),
            },
            "version_restrictions": versions,
            # Cited PostgreSQL files whose GUC definitions identified settings among the terms.
            "setting_sources": self.setting_sources,
            "terms": terms,
            "numbers": numbers,
            "examples": examples,
            "open_questions": open_questions,
            "related_pages": self._related_pages(),
            "coverage": coverage,
            "issues": issues,
            "sections": self.sections,
            "links": self.links,
        }

    def _use(self, section: dict, kind: str) -> tuple[str, str | None]:
        """Return how a block may be used: kind is 'prose', 'display', or another block type."""
        role = section["role"]
        if kind not in ("prose", "display"):
            return "exclude", kind
        if role == "navigation":
            return "exclude", "navigation"
        if role == "reference":
            return "reference", "citation list"
        return ("narrate" if kind == "prose" else "display"), None

    def _block(self, block: dict, block_id: str, section: dict) -> dict:
        kind = block["type"]
        record: dict = {"id": block_id, "type": kind, "lines": block["lines"]}
        if kind == "list":
            record.update(ordered=block["ordered"], start=block["start"], items=[])
            for number, item in enumerate(block["items"], 1):
                item_id = f"{block_id}.{number}"
                record["items"].append({"id": item_id, "lines": item["lines"], "blocks": [
                    self._block(child, f"{item_id}.{position}", section)
                    for position, child in enumerate(item["blocks"], 1)]})
            return record
        if kind == "blockquote":
            record["blocks"] = [self._block(child, f"{block_id}.{position}", section)
                                for position, child in enumerate(block["blocks"], 1)]
            return record
        if kind in ("paragraph", "heading"):
            return self._paragraph(block, record, section)
        if kind == "code":
            use, reason = self._use(section, "display")
            content = block["content"]
            record.update(use=use, language=block["language"], info=block["info"], fenced=block["fenced"],
                          kind=_code_kind(block["language"], content),
                          line_count=content.count("\n") + (0 if content.endswith("\n") or not content else 1),
                          content=content)
        elif kind == "table":
            use, reason = self._use(section, "display")
            record["use"] = use
            record["align"] = block["align"]
            record["header"] = [self._cell(cell, f"{block_id}.h.c{n}", section, block_id, use)
                                for n, cell in enumerate(block["header"], 1)]
            record["rows"] = []
            for number, row in enumerate(block["rows"], 1):
                row_id = f"{block_id}.r{number}"
                cells = [self._cell(cell, f"{row_id}.c{n}", section, block_id, use)
                         for n, cell in enumerate(row["cells"], 1)]
                record["rows"].append({"id": row_id, "line": row["line"], "cells": cells})
                if use in ("narrate", "display"):
                    self._unit("row", row_id, section, block_id, {
                        "text": " | ".join(cell["text"] for cell in cells),
                        "spoken": " | ".join(cell["spoken"] or "" for cell in cells),
                        "citations": [c for cell in cells for c in cell["citations"]],
                        **{key: " | ".join(cell[key] for cell in cells) for key in ("_plain", "_prose", "_numeric")},
                        "_codes": [code for cell in cells for code in cell["_codes"]],
                    }, [row["line"], row["line"]])
            for cell in [*record["header"], *(c for row in record["rows"] for c in row["cells"])]:
                for key in PRIVATE_KEYS:
                    cell.pop(key)
        else:
            use, reason = self._use(section, kind)
            record["use"] = use
            if kind == "html":
                record["content"] = block["content"]
        if reason:
            record["reason"] = reason
        return record

    def _paragraph(self, block: dict, record: dict, section: dict) -> dict:
        sentences, images, citations = self._prose(block["inline"], record["id"], section)
        if block["type"] == "heading":
            record.update(level=block["level"], anchor=block["anchor"])
        if images and not sentences:
            record["type"] = "image"
        use, reason = self._use(section, "display" if record["type"] == "image" else "prose")
        if use == "narrate":
            first = sentences[0]["_plain"] if sentences else ""
            whole = bool(MAINTENANCE_PARAGRAPH.match(first))
            for sentence in sentences:
                if whole or (section["role"] == "question" and PROMPT_RECORD.search(sentence["_plain"])):
                    sentence["maintenance"], sentence["spoken"] = True, None
            if sentences and all(sentence["maintenance"] for sentence in sentences):
                use, reason = "exclude", "maintenance"
            elif not sentences:
                use, reason = "exclude", "citations only"
        if use not in ("narrate", "display"):
            for sentence in sentences:
                sentence["spoken"] = None
        record["use"] = use
        if reason:
            record["reason"] = reason
        if images:
            record["images"] = images
        record["citations"] = citations
        record["sentences"] = sentences
        for sentence in sentences:
            if use in ("narrate", "display") and not sentence["maintenance"]:
                self._unit("sentence", sentence["id"], section, record["id"], sentence, sentence["lines"])
            for key in PRIVATE_KEYS:
                sentence.pop(key)
        return record

    def _unit(self, kind: str, identifier: str, section: dict, block_id: str, content: dict, lines) -> None:
        """Record a sentence, table row, or heading for extraction."""
        self.units.append({
            "kind": kind, "id": identifier, "section": section["id"], "role": section["role"], "block": block_id,
            "lines": list(lines), "text": content["text"], "spoken": content.get("spoken"),
            "citations": content["citations"], "plain": content["_plain"], "prose": content["_prose"],
            "numeric": content["_numeric"], "codes": content["_codes"],
        })

    # Inline content ------------------------------------------------------------------------------

    def _inline_links(self, inline: dict, block_id: str, section: dict) -> list[dict]:
        records = []
        for local, link in enumerate(inline["links"]):
            text = "".join(run["text"] for run in inline["runs"] if run["link"] == local)
            entry = {"href": link["href"], "text": re.sub(r"\s+", " ", text).strip(), "image": link["image"],
                     "line": link["line"], "section": section["_index"]}
            resolved = resolve_links(self.entry["path"], [entry], self.tree["headings"])[0]
            resolved.update(id=len(self.links), block=block_id, section=section["id"])
            resolved["url"] = self._link_url(resolved)
            self.links.append(resolved)
            records.append(resolved)
        return records

    def _link_url(self, link: dict) -> str | None:
        kind = link.get("kind")
        if kind == "citation" and self.pin and link["postgres_version"] == self.version:
            if not link["source_path"]:
                return f"https://github.com/{POSTGRES_REPOSITORY}/tree/{self.pin}"
            lines = tuple(link["lines"]) if link.get("lines") else None
            return blob_url(POSTGRES_REPOSITORY, self.pin, link["source_path"], lines)
        if kind in ("anchor", "glossary", "wiki"):
            return self._wiki_url(link["target"], link.get("fragment"))
        if kind == "external":
            return link["href"]
        return None

    def _stream(self, inline: dict, block_id: str, section: dict) -> dict:
        """Flatten inline runs into text with code and citation markers.

        Also returns the source line of each piece's offset, and the offset where
        each link starts so the link can be traced to its sentence.
        """
        links = self._inline_links(inline, block_id, section)
        stream = {"text": "", "offsets": [], "lines": [], "codes": [], "images": [], "links": {}}
        for run in inline["runs"]:
            link = links[run["link"]] if run["link"] is not None else None
            if link is not None:
                stream["links"].setdefault(link["id"], len(stream["text"]))
            if run["kind"] == "image":
                stream["images"].append(link["id"])
                continue
            if link is not None and link.get("kind") == "citation":
                if stream["links"][link["id"]] != len(stream["text"]):
                    continue
                piece = f"{CITE}{link['id']}{CITE_END}"
            elif run["kind"] == "code":
                stream["codes"].append(run["text"])
                piece = f"{CODE}{len(stream['codes']) - 1}{CODE_END}"
            elif run["kind"] == "html":
                piece = " " if LINE_BREAK.fullmatch(run["text"].strip()) else ""
            else:
                piece = run["text"]
            stream["offsets"].append(len(stream["text"]))
            stream["lines"].append(run["line"])
            stream["text"] += piece
        return stream

    def _prose(self, inline: dict, block_id: str, section: dict) -> tuple[list[dict], list[int], list[int]]:
        """Split a paragraph into sentences; return them, its images, and all its citations."""
        stream = self._stream(inline, block_id, section)
        text = stream["text"]
        sentences: list[dict] = []
        owners: list[tuple[int, int | None]] = []  # (span start, index of the sentence holding the span)
        for start, end in _sentence_spans(text):
            sentence = _render(text[start:end], stream["codes"])
            sentence["lines"] = _line_range(text, start, end, stream["offsets"], stream["lines"])
            leading = re.match(rf"\s*(?:{CITE}\d+{CITE_END}\s*)+", text[start:end])
            if sentences and (leading or not sentence["text"]):
                # A citation placed after the closing punctuation belongs to the previous sentence.
                moved = [int(x) for x in CITE_MARK.findall(leading.group(0) if leading else text[start:end])]
                previous = sentences[-1]
                previous["citations"] += [c for c in moved if c not in previous["citations"]]
                sentence["citations"] = [c for c in sentence["citations"] if c not in moved]
            if sentence["text"]:
                sentences.append(sentence)
            owners.append((start, len(sentences) - 1 if sentences else None))
        for number, sentence in enumerate(sentences, 1):
            sentence["id"] = f"{block_id}.s{number}"
        for link_id, offset in stream["links"].items():
            owner = next((index for start, index in reversed(owners) if start <= offset), None)
            self.links[link_id]["at"] = sentences[owner]["id"] if owner is not None else block_id
        citations = sorted(link_id for link_id in stream["links"] if self.links[link_id].get("kind") == "citation")
        fields = ("id", "lines", "text", "spoken", "citations", "maintenance", *PRIVATE_KEYS)
        return [{key: sentence[key] for key in fields} for sentence in sentences], stream["images"], citations

    def _fragment(self, inline: dict, identifier: str, section: dict, block_id: str) -> dict:
        """Render inline content that is not split into sentences: a heading or a table cell."""
        stream = self._stream(inline, block_id, section)
        for link_id in stream["links"]:
            self.links[link_id]["at"] = identifier
        return _render(stream["text"], stream["codes"])

    def _cell(self, inline: dict, identifier: str, section: dict, block_id: str, use: str) -> dict:
        cell = self._fragment(inline, identifier, section, block_id)
        return {"text": cell["text"], "spoken": cell["spoken"] if use in ("narrate", "display") else None,
                "citations": cell["citations"], **{key: cell[key] for key in PRIVATE_KEYS}}

    # Extraction ----------------------------------------------------------------------------------

    def _terms(self) -> list[dict]:
        found: dict[str, dict] = {}

        def add(name: str, kind: str, unit: dict) -> None:
            key = name.removesuffix("()")
            if not key or key in PROPER_NAMES:
                return
            term = found.setdefault(key, {"term": key, "kind": kind, "forms": [], "count": 0, "sections": [],
                                          "occurrences": [], "glossary_anchors": []})
            if TERM_KINDS.index(kind) < TERM_KINDS.index(term["kind"]):
                term["kind"] = kind
            if name not in term["forms"]:
                term["forms"].append(name)
            term["count"] += 1
            if unit["section"] not in term["sections"]:
                term["sections"].append(unit["section"])
            occurrence = {"at": unit["id"], "line": unit["lines"][0]}
            if occurrence not in term["occurrences"]:
                term["occurrences"].append(occurrence)
            if kind == "identifier" and SETTING_CONTEXT.search(unit["prose"]):
                term["_setting_context"] = True

        for unit in self.units:
            for code in unit["codes"]:
                for name, kind in _code_terms(code):
                    add(name, kind, unit)
            prose = unit["prose"]
            for pattern, kind in ((SNAKE_CASE, "identifier"), (CAMEL_CASE, "identifier"), (CONSTANT, "constant")):
                for match in pattern.finditer(prose):
                    name = match.group(0)
                    add(name, "function" if name.endswith("()") else kind, unit)
            for match in ACRONYM.finditer(prose):
                word = match.group(0)
                if word in SQL_KEYWORDS:
                    add(word, "sql_keyword", unit)
                elif word not in SHORT_WORDS and word not in UNITS:
                    add(word, "acronym", unit)
        # Links to a glossary entry name terms; links to the glossary page itself are navigation.
        units = {unit["id"]: unit for unit in self.units}
        for link in self.links:
            unit = units.get(link.get("at"))
            if link.get("kind") != "glossary" or not link.get("fragment") or not link["text"] or unit is None:
                continue
            key = link["text"].removesuffix("()")
            match = found.get(key) or next((t for t in found.values() if t["term"].lower() == key.lower()), None)
            if match is None:
                add(link["text"], "glossary_link", unit)
                match = found[key]
            if link["fragment"] not in match["glossary_anchors"]:
                match["glossary_anchors"].append(link["fragment"])
        for term in found.values():
            if term["kind"] == "identifier" and term["term"] in self.settings:
                term["kind"], term["setting_source"] = "setting", "pinned_source"
            elif (term["kind"] == "identifier" and not self.settings and term.get("_setting_context")
                  and SNAKE_CASE.fullmatch(term["term"])):
                # Without a cited GUC table, a snake_case name described as a setting is only a hint.
                term["kind"], term["setting_source"] = "setting", "context"
            term.pop("_setting_context", None)
        return sorted(found.values(), key=lambda term: (-term["count"], term["occurrences"][0]["line"] or 0))

    def _subject(self, terms: list[dict]) -> dict:
        title_section = next((s for s in self.sections if s["role"] == "title"), None)
        title = title_section["text"] if title_section else self.entry.get("title")
        display_title = re.sub(r"\s*\(unverified\)\s*$", "", title or "").strip() or None
        spoken_title = _speakable(display_title.replace("`", "")) if display_title else None
        # The first Question section with narratable text states the question; later ones hold
        # follow-up prompts.
        units = [u for u in self.units if u["role"] == "question" and u["kind"] == "sentence" and u["spoken"]]
        first = units[0]["section"] if units else None
        question_units = [u for u in units if u["section"] == first]
        question: dict | None = None
        if question_units:
            question = {"section": first, "sentences": [u["id"] for u in question_units],
                        "text": " ".join(u["text"] for u in question_units),
                        "spoken": " ".join(u["spoken"] for u in question_units)}
        else:
            # Some pages quote the prompt in a plain text block.
            for section in (s for s in self.sections if s["role"] == "question"):
                blocks = [b for b in _leaves(section["blocks"]) if b["type"] == "code"
                          and b["language"] in (None, "text", "txt", "plain", "markdown", "md")]
                text = " ".join(" ".join(b["content"].split()) for b in blocks)
                kept = [text[a:b].strip() for a, b in _sentence_spans(text)
                        if not MAINTENANCE_SENTENCE.search(text[a:b]) and not PROMPT_RECORD.search(text[a:b])]
                if kept:
                    question = {"section": section["id"], "blocks": [b["id"] for b in blocks],
                                "text": " ".join(kept), "spoken": _speakable(" ".join(kept))}
                    break
        focus_at = {u["id"] for u in question_units} | ({title_section["id"]} if title_section else set())
        focus = [term["term"] for term in terms if any(o["at"] in focus_at for o in term["occurrences"])
                 and term["kind"] not in ("sql_keyword", "literal")]
        return {"title": title, "display_title": display_title, "spoken_title": spoken_title,
                "unverified": bool(title and display_title != title), "version": self.version,
                "question": question, "focus_terms": focus}

    def _conclusions(self) -> dict:
        narrated = [u for u in self.units if u["kind"] == "sentence" and u["spoken"]]
        summary = [u for u in narrated if u["role"] == "summary"]
        if summary:
            chosen, source = summary, "summary"
        else:
            answer = next((s for s in self.sections if s["role"] == "content" and s["heading"]
                           and _heading_key(s["heading"]) == "answer"), None)
            candidates = [u for u in narrated if u["role"] == "content"]
            source = "first_content"
            if answer:
                subtree = self._subtree(answer["id"])
                candidates = [u for u in narrated if u["section"] in subtree]
                source = "answer_lead"
            block = next((u["block"] for u in candidates), None)
            chosen = [u for u in candidates if u["block"] == block]
        return {"source": source if chosen else None, "sentences": [
            {"id": u["id"], "section": u["section"], "lines": u["lines"], "text": u["text"], "spoken": u["spoken"],
             "citations": u["citations"]} for u in chosen]}

    def _subtree(self, section_id: str) -> set[str]:
        result, pending = set(), [section_id]
        while pending:
            current = pending.pop()
            result.add(current)
            pending.extend(self.by_id[current]["children"])
        return result

    def _numbers(self) -> list[dict]:
        claims = []
        for unit in self.units:
            if unit["kind"] == "heading" or unit["role"] in ("reference", "navigation"):
                continue
            values = _quantities(unit["numeric"])
            if values:
                claims.append({"id": unit["id"], "section": unit["section"], "lines": unit["lines"],
                               "text": unit["text"], "values": values, "citations": unit["citations"]})
        return claims

    def _versions(self) -> list[dict]:
        found = []
        for unit in self.units:
            if unit["role"] in ("reference", "navigation"):
                continue
            versions, qualifiers = [], []
            for match in VERSION.finditer(unit["plain"]):
                for number in VERSION_NUMBER.findall(match.group(0)):
                    major = _major(number)
                    if major and major not in versions:
                        versions.append(major)
                nearby = unit["plain"][max(0, match.start() - 40):match.end() + 25]
                qualifiers += [q.lower() for q in VERSION_QUALIFIER.findall(nearby) if q.lower() not in qualifiers]
            if versions:
                versions.sort(key=_version_key)
                found.append({"id": unit["id"], "kind": unit["kind"], "section": unit["section"],
                              "lines": unit["lines"], "text": unit["text"], "versions": versions,
                              "other_versions": [v for v in versions if v != str(self.version)],
                              "qualifiers": qualifiers, "citations": unit["citations"]})
        return found

    def _examples(self) -> list[dict]:
        examples = []
        for section in self.sections:
            if section["role"] in ("reference", "navigation"):
                continue
            if section["heading"] and re.search(r"(?i)\b(?:examples?|worked|walkthrough|demo)\b", section["heading"]):
                examples.append({"id": section["id"], "type": "section", "section": section["id"],
                                 "lines": section["subtree_lines"], "heading": section["text"]})
            for block in _leaves(section["blocks"]):
                if block["type"] != "code":
                    continue
                role = {"question": "question", "measurement": "measurement"}.get(section["role"], "example")
                examples.append({"id": block["id"], "type": "code", "section": section["id"],
                                 "lines": block["lines"], "language": block["language"], "kind": block["kind"],
                                 "role": role, "line_count": block["line_count"]})
        return examples

    def _open_questions(self) -> list[dict]:
        items = []
        for section in self.sections:
            if section["role"] != "open_questions":
                continue
            for block in _leaves(section["blocks"]):
                sentences = [s for s in block.get("sentences", []) if s["spoken"]]
                text = " ".join(s["text"] for s in sentences)
                if not sentences or NONE_ITEM.match(text):
                    continue
                items.append({"id": block["id"], "section": section["id"], "lines": block["lines"], "text": text,
                              "spoken": " ".join(s["spoken"] for s in sentences),
                              "citations": sorted({c for s in sentences for c in s["citations"]})})
        return items

    def _related_pages(self) -> list[dict]:
        pages: dict[str, dict] = {}
        for link in self.links:
            target = link.get("target")
            if link.get("kind") != "wiki" or link["image"] or target == self.entry["path"] or not target:
                continue
            page = pages.setdefault(target, {"target": target, "text": link["text"], "url": self._wiki_url(target),
                                             "sections": []})
            if link["section"] not in page["sections"]:
                page["sections"].append(link["section"])
        return list(pages.values())

    # Coverage ------------------------------------------------------------------------------------

    def _coverage(self, terms: list[dict], subject: dict, conclusions: dict) -> dict:
        conclusion_ids = {sentence["id"] for sentence in conclusions["sentences"]}
        question_section = (subject["question"] or {}).get("section")
        focus = set(subject["focus_terms"]) | {
            term["term"] for term in terms if term["kind"] not in ("sql_keyword", "literal", "acronym")
            and any(o["at"] in conclusion_ids for o in term["occurrences"])}
        section_terms: dict[str, set[str]] = {}
        for term in terms:
            for section in term["sections"]:
                section_terms.setdefault(section, set()).add(term["term"])
        entries = []
        for order, section in enumerate(self.sections):
            leaves = [b for b in _leaves(section["blocks"])]
            words = sum(_words(s["spoken"]) for b in leaves if b.get("use") == "narrate"
                        for s in b.get("sentences", []))
            displays = sum(1 for b in leaves if b.get("use") == "display" and b["type"] != "table")
            words += sum(_table_words(b) for b in leaves if b.get("use") == "display" and b["type"] == "table")
            matched = sorted(section_terms.get(section["id"], set()) & focus)
            entries.append({
                "section": section["id"], "heading": section["text"], "level": section["level"],
                "lines": section["lines"], "role": section["role"], "decision": None, "reason": None,
                "words": words + DISPLAY_WORDS * displays, "planned_words": 0, "relevance": len(matched),
                "focus_terms": matched, "_order": order,
                "_tier": 0 if section["heading"] and CAVEAT_HEADING.search(section["heading"]) else
                2 if section["heading"] and SUPPORTING_HEADING.search(section["heading"]) else 1,
            })

        def decide(entry, decision, planned, reason, keep=None):
            entry.update(decision=decision, planned_words=planned, reason=reason)
            # The exact sentences or table rows a condensed section narrates; the drafter keeps these
            # instead of choosing its own.
            if keep is None:
                entry.pop("keep", None)
            else:
                entry["keep"] = keep

        def condense(entry, planned, reason):
            """Condense a section's prose, or else read only the first rows of its table."""
            section = self.by_id[entry["section"]]
            if self._lead(section):
                decide(entry, "summarize", planned, reason)
            else:
                rows = self._first_rows(section, planned)
                decide(entry, "summarize", sum(words for _row, words in rows),
                       reason + " Only the first rows of its table are read.", keep=[row for row, _words in rows])

        content = []
        for entry in entries:
            role, words = entry["role"], entry["words"]
            if role == "navigation":
                decide(entry, "exclude", 0, "Navigation list; not narrated.")
            elif role == "reference":
                decide(entry, "exclude", 0, "Citation list; used for evidence checks and references, not narrated.")
            elif role == "measurement":
                decide(entry, "omit", 0, "Measurement script: supporting detail, listed in the references.")
            elif role == "title":
                decide(entry, "explain", words, "Title and PostgreSQL version on the opening slide.")
            elif self.detail == "full" and words:
                decide(entry, "explain", words, "Full detail: every section is narrated.")
            elif role == "question" and words:
                lead = self._lead(self.by_id[entry["section"]]) if self.detail == "summary" else None
                if entry["section"] == question_section and words <= QUESTION_WORDS:
                    decide(entry, "explain", words, "The central question.")
                elif entry["section"] == question_section and lead:
                    decide(entry, "summarize", _words(lead["spoken"]), "The central question, reduced to its lead "
                           "sentence.", keep=[lead["id"]])
                elif entry["section"] == question_section:
                    decide(entry, "summarize", _summary_words(words),
                           "The central question, condensed from a long prompt.")
                elif self.detail == "summary":
                    decide(entry, "omit", 0, "Follow-up prompt; left out of the summary.")
                else:
                    decide(entry, "summarize", _summary_words(words), "Follow-up prompt; condensed.")
            elif role in ("summary", "open_questions") and self.detail == "summary":
                if words:
                    content.append(entry)
            elif role == "summary":
                decide(entry, "explain", words, "The document's own summary of its conclusions.")
            elif role == "open_questions":
                if words <= OPEN_QUESTION_WORDS:
                    decide(entry, "explain", words, "Unresolved questions are material caveats.")
                else:
                    decide(entry, "summarize", _summary_words(words), "Unresolved questions are material caveats.")
            elif words:
                content.append(entry)
        fixed = sum(entry["planned_words"] for entry in entries)
        full = sum(entry["words"] for entry in entries
                   if entry["role"] not in ("navigation", "reference", "measurement"))
        # Full detail has no length target: every section with narration was explained above.
        target = None if self.detail == "full" else \
            SUMMARY_TARGET_MINUTES if self.detail == "summary" else TARGET_MINUTES
        budget = target[1] * WORDS_PER_MINUTE if target else 0
        long_document = bool(target) and fixed + sum(entry["words"] for entry in content) > budget
        if self.detail == "summary":
            self._summarize(content, conclusions, fixed, budget, decide)
        elif not long_document:
            for entry in content:
                decide(entry, "explain", entry["words"], "Fits within the length target.")
        else:
            # Caveat sections are always kept, so their summaries are reserved first. Sections that
            # mention the subject's terms are explained first; supporting detail such as tests ranks last.
            ranked = sorted(content, key=lambda e: (e["_tier"] == 2, -e["relevance"], e["_order"]))
            # A condensed section keeps its prose, or else the first rows of its table. Code or a figure
            # alone has nothing to condense.
            condensable = {e["section"] for e in content if self._lead(self.by_id[e["section"]])
                           or self._first_rows(self.by_id[e["section"]], 0)}
            used = fixed + sum(_summary_words(e["words"]) for e in content
                               if e["_tier"] == 0 and e["section"] in condensable)
            for entry in ranked:
                words, summary = entry["words"], _summary_words(entry["words"])
                reserved = summary if entry["_tier"] == 0 and entry["section"] in condensable else 0
                if entry["relevance"] and used - reserved + words <= budget:
                    decide(entry, "explain", words, "Mentions " + ", ".join(entry["focus_terms"][:4]) + ".")
                    used += words - reserved
                elif entry["section"] not in condensable and used + words <= budget:
                    decide(entry, "explain", words, "Nothing to condense; it fits within the length target.")
                    used += words
                elif entry["section"] not in condensable:
                    decide(entry, "omit", 0, "Nothing to condense and beyond the length target; kept in the "
                           "references.")
                elif entry["_tier"] == 0:
                    condense(entry, summary, "Caveat: kept at least in condensed form.")
                    used += entry["planned_words"] - summary
                elif used + summary <= budget:
                    condense(entry, summary, "Condensed to fit the length target.")
                    used += entry["planned_words"]
                else:
                    decide(entry, "omit", 0, "Supporting detail beyond the length target; kept in the references."
                           if entry["_tier"] == 2 else "Beyond the length target; kept in the references.")
            for entry in ranked:
                extra = entry["words"] - entry["planned_words"]
                if entry["decision"] == "summarize" and used + extra <= budget:
                    decide(entry, "explain", entry["words"], "Fits within the length target.")
                    used += extra
        # A heading without text of its own follows its subsections.
        for entry in reversed(entries):
            if entry["decision"] is None:
                children = [e for e in entries if self.by_id[e["section"]]["parent"] == entry["section"]]
                best = min((DECISIONS.index(e["decision"]) for e in children if e["decision"]), default=2)
                decide(entry, DECISIONS[best], 0, "Heading only; follows its subsections.")
        for entry in entries:
            entry.pop("_order")
            entry.pop("_tier")
        planned = sum(entry["planned_words"] for entry in entries)
        return {
            "detail": self.detail,
            "words_per_minute": WORDS_PER_MINUTE, "target_minutes": list(target) if target else None,
            "display_words": DISPLAY_WORDS, "long_document": long_document,
            "full_words": full, "planned_words": planned,
            "full_minutes": round(full / WORDS_PER_MINUTE, 1), "planned_minutes": round(planned / WORDS_PER_MINUTE, 1),
            "decisions": {decision: sum(e["decision"] == decision for e in entries) for decision in DECISIONS},
            "sections": entries,
        }

    def _summarize(self, content: list[dict], conclusions: dict, used: int, budget: int, decide) -> None:
        """Plan the summary, content, and open-questions sections of a summary.

        The page's own summary is narrated without its tables and code, which the drafter would
        read row by row. The conclusions, one sentence from each caveat, and the first open
        question are always kept. The lead sentences of other sections follow while they fit the
        budget: main sections before their subsections, then sections that name the subject's
        terms, in page order, and then the other open questions. Tests, history, and other
        supporting detail are left out.
        """
        # Without a summary section, the conclusions are the first paragraph of the answer.
        answer = None if conclusions["source"] == "summary" else \
            next((sentence["section"] for sentence in conclusions["sentences"]), None)
        leads, open_questions = [], []
        for entry in content:
            section = self.by_id[entry["section"]]
            kind = self._kind(section)
            if entry["role"] == "open_questions":
                open_questions.append(entry)
                continue
            # A summary section, or a "Short answer" or "Answer Up Front" under "## Answer".
            if entry["role"] == "summary" or (entry["level"] <= 3 and kind != "supporting" and
                                              ROLES.get(_heading_key(section["heading"] or "")) == "summary"):
                prose = self._narrated(section)
                if not any(block.get("use") == "display" for block in _leaves(section["blocks"])):
                    decide(entry, "explain", entry["words"], "The document's own summary of its conclusions.")
                elif prose:
                    decide(entry, "summarize", sum(_words(s["spoken"]) for s in prose),
                           "The document's own summary, without its tables and code.", keep=[s["id"] for s in prose])
                elif conclusions["sentences"] and entry["section"] != answer:
                    decide(entry, "omit", 0, "The document's own summary is a table or code; the summary "
                           "narrates the conclusions instead.")
                else:
                    decide(entry, "explain", entry["words"], "The document's own summary of its conclusions.")
            elif entry["section"] == answer:
                kept = [s for s in conclusions["sentences"] if s["section"] == answer]
                decide(entry, "summarize", sum(_words(s["spoken"]) for s in kept), "Keeps the page's conclusions.",
                       keep=[s["id"] for s in kept])
            elif kind == "supporting":
                decide(entry, "omit", 0, "Supporting detail; left out of the summary.")
            elif kind == "caveat" and (lead := self._lead(section)):
                decide(entry, "summarize", _words(lead["spoken"]), "Caveat: its lead sentence is kept.",
                       keep=[lead["id"]])
            elif kind == "caveat":
                # Such as a table of exceptions, which the drafter would read row by row.
                decide(entry, "omit", 0, "Caveat with no sentence that states it alone; kept in the references.")
            else:
                leads.append(entry)
                continue
            used += entry["planned_words"]
        if open_questions:
            first = open_questions.pop(0)
            lead = self._lead(self.by_id[first["section"]])
            if first["words"] <= OPEN_QUESTION_WORDS or not lead:
                decide(first, "explain", first["words"], "Unresolved questions are material caveats.")
            else:
                decide(first, "summarize", _words(lead["spoken"]), "Unresolved questions are material caveats; "
                       "its lead sentence is kept.", keep=[lead["id"]])
            used += first["planned_words"]
        for entry in sorted(leads, key=lambda e: (e["level"], -e["relevance"], e["_order"])) + open_questions:
            lead = self._lead(self.by_id[entry["section"]])
            words = _words(lead["spoken"]) if lead else 0
            if lead and used + words <= budget:
                decide(entry, "summarize", words, "Its lead sentence gives one of the page's open questions."
                       if entry["role"] == "open_questions" else
                       "Its lead sentence gives one of the page's main points.", keep=[lead["id"]])
                used += words
            else:
                decide(entry, "omit", 0, "Beyond the summary's length; kept in the references." if lead else
                       "No sentence states its point alone; kept in the references.")

    def _kind(self, section: dict) -> str | None:
        """Return 'caveat' or 'supporting' when the section or one it belongs to has such a heading."""
        headings = []
        while section:
            if section["level"] >= 2 and section["heading"]:
                headings.append(section["heading"])
            section = self.by_id.get(section["parent"]) if section["parent"] else None
        if any(CAVEAT_HEADING.search(heading) for heading in headings):
            return "caveat"
        if any(SUPPORTING_HEADING.search(heading) for heading in headings):
            return "supporting"
        return None

    @staticmethod
    def _first_rows(section: dict, words: int) -> list[tuple[str, int]]:
        """Return the IDs and spoken words of the first table rows that fit `words`, and at least one row."""
        rows, used = [], 0
        for block in _leaves(section["blocks"]):
            if block["type"] != "table" or block.get("use") != "display":
                continue
            header = [cell["text"] for cell in block["header"]]
            for row in block["rows"]:
                spoken = _row_words(header, [cell["text"] for cell in row["cells"]])
                if not spoken:
                    continue
                if rows and used + spoken > words:
                    return rows
                rows.append((row["id"], spoken))
                used += spoken
        return rows

    @staticmethod
    def _narrated(section: dict) -> list[dict]:
        """Return the sentences of the section's own blocks that the narration may use."""
        return [sentence for block in _leaves(section["blocks"]) if block.get("use") == "narrate"
                for sentence in block.get("sentences", []) if sentence["spoken"] and not sentence["maintenance"]]

    @classmethod
    def _lead(cls, section: dict) -> dict | None:
        """Return the section's first narrated sentence that says something without what follows it."""
        # An introduction to a list, table, or code, or a label such as "Response.", needs its context.
        return next((sentence for sentence in cls._narrated(section)
                     if not sentence["text"].rstrip().endswith(":") and _words(sentence["text"]) >= 3), None)

    def _issues(self, subject: dict, conclusions: dict, coverage: dict) -> list[dict]:
        issues = []
        narrated = [u for u in self.units if u["kind"] == "sentence" and u["spoken"] and u["role"] not in
                    ("reference", "navigation")]
        if not narrated:
            issues.append({"severity": "blocking", "code": "no_narration", "lines": [],
                           "message": "The document has no prose that can be narrated.",
                           "action": "Choose a wiki page with an explanation, not only lists or code."})
        # Common concept pages define a concept instead of answering a question.
        if subject["question"] is None and self.entry.get("type") != "common-concept":
            issues.append({"severity": "warning", "code": "question_missing", "lines": [],
                           "message": "No `## Question` section with narratable text; the title states the subject.",
                           "action": None})
        if not conclusions["sentences"]:
            issues.append({"severity": "warning", "code": "conclusions_missing", "lines": [],
                           "message": "No summary or answer lead was found to state the main conclusions.",
                           "action": None})
        maintenance = [s for section in self.sections for b in _leaves(section["blocks"])
                       for s in b.get("sentences", []) if s["maintenance"]]
        if maintenance:
            issues.append({"severity": "note", "code": "maintenance_excluded",
                           "lines": sorted({s["lines"][0] for s in maintenance if s["lines"][0]}),
                           "message": f"{len(maintenance)} maintenance sentence(s), such as agent instructions and "
                                      "prompt-hygiene notes, are excluded from narration.", "action": None})
        decisions = coverage["decisions"]
        if coverage["detail"] == "summary":
            issues.append({"severity": "note", "code": "summary", "lines": [],
                           "message": f"The summary plans about {coverage['planned_minutes']} of the page's "
                                      f"{coverage['full_minutes']} minutes of narration: {decisions['summarize']} "
                                      f"section(s) are reduced to their key sentences and {decisions['omit']} are "
                                      "left out.", "action": None})
        elif coverage["detail"] == "full" and coverage["planned_minutes"] > TARGET_MINUTES[1]:
            issues.append({"severity": "note", "code": "full_detail", "lines": [],
                           "message": f"Full detail narrates every section, about {coverage['planned_minutes']} "
                                      f"minutes; the standard level would condense this page to about "
                                      f"{TARGET_MINUTES[1]} minutes.", "action": None})
        elif coverage["long_document"]:
            issues.append({"severity": "note", "code": "long_document", "lines": [],
                           "message": f"The full narration would take about {coverage['full_minutes']} minutes; "
                                      f"{decisions['summarize']} section(s) are summarized and {decisions['omit']} "
                                      "omitted as supporting detail.", "action": None})
        return issues


def _leaves(blocks: list[dict]):
    """Yield leaf blocks in document order."""
    for block in blocks:
        if block["type"] == "list":
            for item in block["items"]:
                yield from _leaves(item["blocks"])
        elif block["type"] == "blockquote":
            yield from _leaves(block["blocks"])
        else:
            yield block


def _sentence_spans(stream: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    for match in BOUNDARY.finditer(stream):
        following = stream[match.end():match.end() + 1]
        if not following or not (following.isupper() or following.isdigit() or following in SENTENCE_START):
            continue
        word = re.search(r"(\S+)$", stream[start:match.start()])
        if word and word.group(1).lower().lstrip("([\"'“‘") in ABBREVIATIONS:
            continue
        spans.append((start, match.end()))
        start = match.end()
    if stream[start:].strip():
        spans.append((start, len(stream)))
    return spans


def _render(raw: str, codes: list[str]) -> dict:
    """Return display, plain, and spoken text for a span with code and citation markers.

    The underscored keys feed extraction and are not saved: `_prose` blanks inline
    code, and `_numeric` keeps only numeric inline code, between markers.
    """
    citations = list(dict.fromkeys(int(x) for x in CITE_MARK.findall(raw)))
    body = _tidy(CITE_MARK.sub("", raw))
    display = CODE_MARK.sub(lambda m: _backticks(codes[int(m.group(1))]), body)
    plain = CODE_MARK.sub(lambda m: codes[int(m.group(1))], body)
    maintenance = bool(MAINTENANCE_SENTENCE.search(plain))

    def numeric(match: re.Match) -> str:
        code = codes[int(match.group(1))].strip()
        return f"{NUMERIC_START}{code}{NUMERIC_END}" if NUMERIC_CODE.fullmatch(code) else f" {CODE} "

    return {"text": display, "spoken": None if maintenance else _speakable(plain), "citations": citations,
            "maintenance": maintenance, "_plain": plain, "_prose": CODE_MARK.sub(f" {CODE} ", body),
            "_numeric": CODE_MARK.sub(numeric, body), "_codes": [codes[int(x)] for x in CODE_MARK.findall(body)]}


def _speakable(text: str) -> str | None:
    spoken = _tidy(URL.sub("", text))
    return spoken if re.search(r"\w", spoken) else None


def _line_range(stream: str, start: int, end: int, offsets: list[int], lines: list[int | None]) -> list:
    text = stream[start:end]
    first = start + len(text) - len(text.lstrip())
    last = start + len(text.rstrip()) - 1

    def line_at(position: int):
        index = bisect.bisect_right(offsets, position) - 1
        return lines[max(index, 0)] if lines else None

    return [line_at(first), line_at(max(last, first))]


def _code_kind(language: str | None, content: str) -> str:
    language = (language or "").lower()
    if language in {"sql", "psql", "pgsql", "plpgsql", "postgresql"}:
        return "sql"
    if language in {"bash", "sh", "shell", "console", "zsh", "shell-session"}:
        return "shell"
    if language in {"mermaid", "dot", "graphviz", "plantuml"}:
        return "diagram"
    if language in {"c", "h", "cpp"}:
        return "c"
    if language in {"conf", "ini", "toml", "yaml", "yml", "properties"}:
        return "config"
    if language == "json":
        return "data"
    if DIAGRAM.search(content):
        return "diagram"
    if SQL_START.match(content.lstrip()):
        return "sql"
    if re.search(r"^-+\+-+|^\(\d+ rows?\)$", content, re.MULTILINE):
        return "output"
    return "text" if language in ("", "text", "txt", "plain", "plaintext", "none") else "other"


def _code_terms(code: str) -> list[tuple[str, str]]:
    """Classify an inline code span and return the terms it names."""
    text = code.strip()
    if not text or NUMERIC_CODE.fullmatch(text):
        return []
    if re.fullmatch(r"(['\"]).*\1", text):
        return [(text, "literal")]
    if re.fullmatch(r"[A-Za-z_][\w$]*\(\)", text):
        return [(text, "function")]
    if SQL_START.match(text) and " " in text:
        return [(text, "sql"), *_code_identifiers(text)]
    if match := re.fullmatch(r"([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)*)\s*\((.*)\)", text, re.DOTALL):
        return [(match.group(1) + "()", "function"), *_code_identifiers(match.group(2))]
    if "/" in text and " " not in text:
        return [(text, "path")]
    if re.fullmatch(r"[A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)+", text):
        return [(text, "path" if text.rsplit(".", 1)[1] in FILE_EXTENSIONS else "qualified_name")]
    if CONSTANT.fullmatch(text):
        return [(text, "constant")]
    if re.fullmatch(r"[A-Z][A-Z0-9]+", text):
        return [(text, "sql_keyword" if text in SQL_KEYWORDS else "acronym")]
    if re.fullmatch(r"[A-Za-z_][\w$]*", text):
        return [(text, "identifier")]
    return _code_identifiers(text)


def _code_identifiers(text: str) -> list[tuple[str, str]]:
    """Return distinctive identifiers inside a code expression: snake, camel, or constant case."""
    terms = []
    for match in CODE_IDENTIFIER.finditer(text):
        name = match.group(0).rstrip("( \t")
        call = bool(match.group(1))
        if CONSTANT.fullmatch(name):
            terms.append((name, "constant"))
        elif "_" in name.strip("_") or re.search(r"[a-z][A-Z]", name):
            terms.append((name + "()" if call else name, "function" if call else "identifier"))
    return terms


def _row_words(header: list[str], cells: list[str]) -> int:
    """Return the words of a table row read aloud, as script._row_sentence reads it."""
    if not any(cell.strip() for cell in cells):
        return 0
    # "First cell: header cell, header cell."
    return _words(cells[0]) + sum(_words(name) + _words(cell) for name, cell in zip(header[1:], cells[1:])
                                  if cell.strip())


def _table_words(block: dict) -> int:
    """Return the words the drafter reads for a table, one row at a time."""
    header = [cell["text"] for cell in block["header"]]
    return sum(_row_words(header, [cell["text"] for cell in row["cells"]]) for row in block["rows"])


def _summary_words(words: int) -> int:
    return min(words, max(SUMMARY_MIN_WORDS, min(SUMMARY_MAX_WORDS, round(words * SUMMARY_RATIO))))


def _major(number: str) -> str | None:
    """Return a PostgreSQL major version from a matched number, or None if it cannot be one."""
    whole, _, fraction = number.partition(".")
    major = int(whole)
    if 10 <= major <= 40:
        return str(major)
    if 6 <= major <= 9 and fraction:
        return f"{major}.{fraction}"
    return None


def _version_key(version: str) -> tuple[int, int]:
    whole, _, fraction = version.partition(".")
    return int(whole), int(fraction or 0)


def _quantities(text: str) -> list[dict]:
    """Return the quantities in extraction text, skipping versions, dates, labels, and code expressions.

    The text keeps numeric inline code between NUMERIC_START and NUMERIC_END and
    blanks other inline code, so digits inside identifiers are never read as claims.
    """
    skipped = [(m.start(), m.end()) for pattern in (VERSION, DATE_OR_TIME) for m in pattern.finditer(text)]
    values = []
    for match in NUMBER.finditer(text):
        start, end = match.span()
        if any(a <= start < b for a, b in skipped):
            continue
        raw = match.group(0)
        unit_match = UNIT.match(text, end)
        word = unit_match.group(1) if unit_match else ""
        unit = UNITS.get(word) or (UNITS.get(word.lower()) if len(word) > 2 else None)
        following = text[end:end + 1]
        if unit is None and (following.isalnum() or following == "_"):
            continue  # part of an identifier or a hash
        in_code = text[start - 1:start] == NUMERIC_START
        if unit is None and not in_code:
            digits = raw.replace(",", "")
            if LABEL_BEFORE.search(text[max(0, start - 20):start]):
                continue
            if "." not in digits and (len(digits) < 2 or 1900 <= int(digits) <= 2099):
                continue
        number = raw.replace(",", "")
        value = float(number) if "." in number else int(number)
        shown = text[start:unit_match.end()] if unit else raw
        values.append({"raw": " ".join(shown.replace(NUMERIC_END, "").split()), "value": value, "unit": unit})
    return values


def _update_manifest(root: Path, run_dir: Path, *, status: str, record: dict | None = None,
                     digest: str | None = None, error: str | None = None) -> dict:
    path = run_dir / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    manifest["status"] = {"passed": "document_ready"}.get(status, status)
    invalidate_after(manifest, "document")
    entry: dict = {"status": status}
    if error:
        entry["error"] = error
    if record:
        coverage = record["coverage"]
        entry.update({
            "record": "document.json", "sha256": digest,
            "parsed_at": record["parsed_at"], "schema": record["schema"],
            "input": {"path": record["document"]["path"], "sha256": record["document"]["sha256"]},
            "counts": {
                "sections": len(record["sections"]),
                "sentences": sum(len(b.get("sentences", [])) for s in record["sections"] for b in _leaves(s["blocks"])),
                "links": len(record["links"]), "conclusions": len(record["conclusions"]["sentences"]),
                "terms": len(record["terms"]), "numbers": len(record["numbers"]),
                "examples": len(record["examples"]), "version_restrictions": len(record["version_restrictions"]),
                "open_questions": len(record["open_questions"]),
            },
            "coverage": {"file": "coverage.md", **{key: coverage[key] for key in
                                                   ("detail", "long_document", "full_minutes", "planned_minutes",
                                                    "decisions")}},
            "issues": {severity: sum(issue["severity"] == severity for issue in record["issues"])
                       for severity in ("blocking", "warning", "note")},
        })
    manifest["document"] = entry
    write_atomic(root, run_dir.relative_to(root) / "manifest.json",
                 (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"), label="Request")
    return entry


def _cell_text(text: str | None) -> str:
    return (text or "").replace("|", "\\|")


def _render_coverage(record: dict) -> str:
    document, subject, coverage = record["document"], record["subject"], record["coverage"]
    version = f"PostgreSQL {document['version']}" if document.get("version") else "Unknown version"
    decisions = coverage["decisions"]
    lines = [
        "# Document Coverage Map", "",
        f"- Request: `{record['request_id']}`",
        f"- Status: **{record['status']}**",
        f"- Document: [`{document['path']}`]({document['url']}) at wiki commit `{document['wiki_commit']}`",
        f"- Subject: {subject['display_title'] or '(untitled)'} ({version}, source pin "
        f"`{(document.get('pinned_commit') or 'none')[:12]}`)",
    ]
    if subject["question"]:
        lines.append(f"- Question: {subject['question']['text']}")
    if subject["focus_terms"]:
        lines.append("- Focus terms: " + ", ".join(f"`{term}`" for term in subject["focus_terms"]))
    target = coverage["target_minutes"]
    lines += [
        f"- Level of detail: {coverage['detail']}",
        f"- Narration estimate: {coverage['full_minutes']} minutes for every narratable section, "
        f"{coverage['planned_minutes']} minutes planned ("
        + (f"target {target[0]}–{target[1]} minutes" if target else "no length target")
        + f" at {coverage['words_per_minute']} words per minute)",
        f"- Sections: {decisions['explain']} explained, {decisions['summarize']} summarized, "
        f"{decisions['omit']} omitted as supporting detail, {decisions['exclude']} excluded from narration",
        f"- Extracted: {len(record['conclusions']['sentences'])} conclusion sentence(s), {len(record['terms'])} terms, "
        f"{len(record['numbers'])} numerical claim(s), {len(record['examples'])} example(s), "
        f"{len(record['version_restrictions'])} version mention(s), {len(record['open_questions'])} open question(s)",
        "", "## Sections", "",
        "| Section | Lines | Role | Decision | Words (full → planned) | Reason |", "|---|---|---|---|---|---|",
    ]
    sections = {section["id"]: section for section in record["sections"]}
    for entry in coverage["sections"]:
        section = sections[entry["section"]]
        name = _cell_text(entry["heading"] or "(before the first heading)")
        indent = "&emsp;" * max(entry["level"] - 2, 0)
        lines.append(
            f"| {indent}[{name}]({section['url']}) | {entry['lines'][0]}–{entry['lines'][1]} | {entry['role']} | "
            f"**{entry['decision']}** | {entry['words']} → {entry['planned_words']} | "
            f"{_cell_text(entry['reason'])} |")
    kept = [(entry, unit_id) for entry in coverage["sections"] for unit_id in entry.get("keep", [])]
    if kept:
        units = {}
        for section in record["sections"]:
            for block in _leaves(section["blocks"]):
                units |= {s["id"]: (s["lines"][0], s["text"]) for s in block.get("sentences", [])}
                units |= {row["id"]: (row["line"], " | ".join(cell["text"] for cell in row["cells"]))
                          for row in block.get("rows", [])}
        lines += ["", "## Kept Sentences And Table Rows", "",
                  "A condensed section with this list narrates only these; the drafter keeps them.", ""]
        for entry, unit_id in kept:
            line, text = units[unit_id]
            lines.append(f"- {entry['heading'] or '(before the first heading)'}, line {line} (`{unit_id}`): {text}")
    if record["conclusions"]["sentences"]:
        lines += ["", "## Conclusions", ""]
        for sentence in record["conclusions"]["sentences"]:
            lines.append(f"- Line {sentence['lines'][0]} (`{sentence['id']}`): {sentence['text']}")
    if record["open_questions"]:
        lines += ["", "## Open Questions", ""]
        for item in record["open_questions"]:
            lines.append(f"- Line {item['lines'][0]} (`{item['id']}`): {item['text']}")
    others = record["version_scope"]["other_versions_mentioned"]
    if others:
        lines += ["", "## Other PostgreSQL Versions Mentioned", ""]
        for entry in record["version_restrictions"]:
            if entry["other_versions"]:
                lines.append(f"- Line {entry['lines'][0]} (`{entry['id']}`), PostgreSQL "
                             f"{', '.join(entry['other_versions'])}: {entry['text']}")
    excluded = [(s, b) for section in record["sections"] for b in _leaves(section["blocks"])
                for s in b.get("sentences", []) if s["maintenance"]]
    if excluded:
        lines += ["", "## Maintenance Text Excluded From Narration", ""]
        for sentence, _block in excluded:
            lines.append(f"- Line {sentence['lines'][0]} (`{sentence['id']}`): {sentence['text']}")
    if record["related_pages"]:
        lines += ["", "## Linked Wiki Pages Not Included", "",
                  "The video covers only the requested document; these linked pages are not narrated.", ""]
        for page in record["related_pages"]:
            lines.append(f"- [`{page['target']}`]({page['url']})")
    if record["issues"]:
        lines += ["", "## Issues", ""]
        for issue in record["issues"]:
            lines.append(f"- {issue['severity']} `{issue['code']}`: {issue['message']}")
            if issue.get("action"):
                lines.append(f"  Action: {issue['action']}")
    return "\n".join(lines) + "\n"
