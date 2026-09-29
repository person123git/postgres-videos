"""Index the glossary and select the entries relevant to the selected document (Step 5).

Every request builds its own index from the run's read-only snapshot copy of
wiki/glossary.md, which Step 3 downloaded for that request, and saves it as
glossary-index.json in the run directory; an index built for another request is
never used. It depends only on the glossary's bytes: each entry under `## Terms`
keeps its heading anchor, canonical term, aliases, definition, checked versions,
version notes, and evidence links, and PostgreSQL URLs come from the glossary's own
Source Pins table. Commit-specific wiki URLs are added when the document is matched.

Matching reads document.json. Candidate entries come from explicit glossary links
and from entry names, aliases, acronyms, and identifiers in the narrated and
displayed text. Distinctive forms, such as `pg_stat_activity` or "free space map",
match on their own, and so do single words that are PostgreSQL jargon rather than
English, such as "autovacuum". Ordinary English words (those in Kokoro's English
pronunciation lexicon), short aliases, two-letter acronyms, and code words such as
`auto` also need context from the glossary's own structure: a source file that both
the paragraph and the entry cite, a symbol from the entry's definition, or a related
entry already matched in the same paragraph. Each matched entry is ranked by where
it occurs and resolved to the document's PostgreSQL version through its version
notes. glossary-matches.json also records ambiguous occurrences and the document's
terms that no entry covers.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .document import (CITE, CITE_END, CODE, CODE_END, LINE_BREAK, _leaves, _render, _sentence_spans,
                       _snapshot_text)
from .markdown import block_tree, split_front_matter, table_after_heading
from .snapshot import GLOSSARY, resolve_links
from .sources import COMMIT, POSTGRES_REPOSITORY, blob_url, write_atomic
from .stages import invalidate_after

SCHEMA_VERSION = 1
INDEX_SCHEMA = 1
INDEX = "glossary-index.json"
# Modules whose code shapes the index; the manifest records their digest as the index's builder.
BUILDER_SOURCES = ("glossary.py", "document.py", "markdown.py")
# Kokoro's English pronunciation lexicons, from its misaki package. A single-word name or alias they list is an
# ordinary English word, such as "path" or "cost", and needs context; one they lack is jargon.
LEXICON_PACKAGE, LEXICON_FILES = "misaki", ("data/us_gold.json", "data/us_silver.json")
# Words and code words this short need context even when they are not English, such as "xid" or `jit`.
SHORT_FORM = 3

# Placeholder patterns such as `WITH (...)` need context unless they keep this many literal characters.
PATTERN_LITERAL = 8
DECISION_WEIGHTS = {"explain": 1.0, "summarize": 0.5, "omit": 0.2, "exclude": 0.1}
CENTRAL_WEIGHT, CENTRAL_LIMIT, LINK_WEIGHT = 3, 3, 2
TIERS = ("central", "supporting", "peripheral")
SUPPORT_LEVELS = {"link": 4, "specific": 3, "form": 3, "context": 2, "discourse": 1, None: 0}
CONFIDENCE = {"link": "high", "specific": "high", "form": "medium", "context": "medium", "discourse": "medium"}
OCCURRENCE_SAMPLE = 10

NOTE = re.compile(r"PostgreSQL\s+(\d+)\s*:\s*(Holds|Differs|Not present)\b[\s.,;:]*(.*)", re.DOTALL)
NOTE_STATUS = {"Holds": "holds", "Differs": "differs", "Not present": "not_present"}
# Words by which a Holds note names an exception to the main paragraph.
EXCEPTION = re.compile(r"(?i)\b(?:except|apart from|but|however|unlike|instead|no longer)\b")
# A note that borrows another version's note or the main paragraph: "as in 18", "the same way as 12",
# "the same function set as 18", "match 17", "as 12 does", "the 18 ones".
REFERENCE = re.compile(
    r"\b(?:[Aa]s in|[Tt]he same way as|[Ll]ike|[Mm]atch(?:es)?|[Ss]ame\s+(?:[^\s.;:]+\s+){0,4}?as)"
    r"\s+(?:PostgreSQL\s+|v)?(\d{1,2})\b"
    r"|\b[Aa]s\s+(?:PostgreSQL\s+)?(\d{1,2})\s+(?:does|did)\b"
    r"|\bthe\s+(\d{1,2})\s+ones?\b"
)
OPENING_VERSION = re.compile(r"^(?:In\s+)?PostgreSQL\s+(\d+)\b")
# A trailing parenthetical outside code: "(contrast)", "(PostgreSQL 12 and 14)", or an expansion.
QUALIFIER = re.compile(r"(?P<base>.+?)\s*\((?P<qualifier>(?:[^()`]|`[^`]*`)+)\)")
VERSION_QUALIFIER = re.compile(r"PostgreSQL\s+\d+(?:\s*(?:,|and|or)\s*\d+)*")
ACRONYM = re.compile(r"(?=(?:[^A-Z]*[A-Z]){2})[A-Z0-9][A-Z0-9/&+-]*")
# Shapes that ordinary English words lack: underscores, digits, dots, calls, camel case, capital runs.
DISTINCTIVE = re.compile(r"[_$.()\[\]/\\\d\s]|[a-z][A-Z]|[A-Z]{2}")
# Code forms with inner spaces, brackets, wildcards, or placeholders get their own expressions.
COMPLEX_CODE = re.compile(r"[\s()\[\]]")
PATTERN_TOKEN = re.compile(r"\.\.\.|\*|\s+|[()]|[^\s()*.]+|\.")
CODE_SPAN = re.compile(r"(`+)(.+?)\1(?!`)")
# Source symbols used as context: identifiers with an underscore, a digit, or camel case.
SYMBOL = re.compile(r"(?<![\w$])[A-Za-z_][\w$]*(?![\w$])")
SYMBOL_SHAPE = re.compile(r"_|\d|[a-z][A-Z]")

# Document term kinds that name a concept the glossary could define.
CONCEPT_KINDS = ("setting", "function", "constant", "identifier", "qualified_name", "acronym", "glossary_link")
GENERIC_ACRONYMS = {"SQL", "ID", "IDS", "API", "ASCII", "JSON", "UTF", "URL", "HTTP", "HTTPS", "CPU", "OS", "RAM",
                    "TCP", "UDP", "IP", "HTML", "XML", "CSV", "UUID", "UTC", "GB", "MB", "KB", "TB", "PID", "FAQ"}


def match_glossary(root: Path, run_dir: Path) -> dict:
    """Write glossary-matches.json for a run whose parsed document passed.

    Returns the manifest's glossary record, whose status is 'passed'. A missing
    or altered input marks the manifest 'failed' and raises.
    """
    try:
        return _match(root, run_dir)
    except (ValueError, OSError) as error:
        _update_manifest(root, run_dir, status="failed", error=str(error))
        raise


def _match(root: Path, run_dir: Path) -> dict:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    parsed = manifest.get("document") or {}
    if parsed.get("status") != "passed":
        raise ValueError(f"The parsed document has status '{parsed.get('status')}'; resolve coverage.md first.")
    data = (run_dir / "document.json").read_bytes()
    if hashlib.sha256(data).hexdigest() != parsed.get("sha256"):
        raise ValueError("document.json does not match the SHA-256 recorded in manifest.json.")
    sources = json.loads((run_dir / "sources.json").read_text(encoding="utf-8"))
    index, built = index_glossary(root, run_dir, sources)
    record = _Selector(index, json.loads(data), sources, built).build()
    output = (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    write_atomic(root, run_dir.relative_to(root) / "glossary-matches.json", output, label="Request")
    return _update_manifest(root, run_dir, status=record["status"], record=record,
                            digest=hashlib.sha256(output).hexdigest())


# Index -----------------------------------------------------------------------------------------


def index_glossary(root: Path, run_dir: Path, sources: dict) -> tuple[dict, dict]:
    """Build the index of the run's glossary snapshot, save it in the run, and return it with its record.

    The snapshot copy is the glossary that Step 3 downloaded for this request, and it is
    checked against its recorded SHA-256 first. No index built for another request is used.
    """
    entry = sources.get("glossary")
    if not entry:
        raise ValueError("The source snapshot has no glossary; resolve source-report.md first.")
    builder = _builder_digest()
    index = build_index(_snapshot_text(root, run_dir, entry), digest=entry["sha256"], builder=builder)
    encoded = (json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    write_atomic(root, run_dir.relative_to(root) / INDEX, encoded, label="Request")
    if entry.get("term_count") is not None and len(index["entries"]) != entry["term_count"]:
        raise ValueError(f"The glossary index has {len(index['entries'])} entries, but the source snapshot "
                         f"counted {entry['term_count']} under `## Terms`.")
    return index, {"path": INDEX, "sha256": hashlib.sha256(encoded).hexdigest(), "schema": INDEX_SCHEMA,
                   "builder": builder, "built_at": index["built_at"], "entries": len(index["entries"])}


def _builder_digest() -> str:
    digest = hashlib.sha256()
    for path in [*(Path(__file__).parent / name for name in BUILDER_SOURCES), *_lexicon_files()]:
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _lexicon_files() -> list[Path]:
    spec = importlib.util.find_spec(LEXICON_PACKAGE)
    if spec is None or not spec.submodule_search_locations:
        raise ValueError(f"The local {LEXICON_PACKAGE} package is missing; run scripts/setup.")
    base = Path(next(iter(spec.submodule_search_locations)))
    files = [base / name for name in LEXICON_FILES]
    if missing := [str(path) for path in files if not path.is_file()]:
        raise ValueError(f"The English lexicon files are missing: {', '.join(missing)}; run scripts/setup.")
    return files


def english_words() -> frozenset[str]:
    """Return the lowercase words of Kokoro's English pronunciation lexicons."""
    words: set[str] = set()
    for path in _lexicon_files():
        words.update(word.lower() for word in json.loads(path.read_bytes()))
    return frozenset(words)


def build_index(text: str, *, digest: str, builder: str | None = None,
                english: frozenset[str] | None = None) -> dict:
    """Parse the glossary's entries under `## Terms` into a JSON-ready index.

    `english` is the set of ordinary English words; it defaults to Kokoro's lexicon.
    """
    english = english_words() if english is None else english
    front, body = split_front_matter(text)
    tree = block_tree(body)
    headings = tree["headings"]
    terms = next((n for n, heading in enumerate(headings) if heading["level"] == 2 and heading["text"] == "Terms"),
                 None)
    if terms is None:
        raise ValueError(f"{GLOSSARY} has no `## Terms` section.")
    pins = {}
    for row in table_after_heading(body, "Source Pins"):
        commit = (row.get("pinned commit") or "").strip().lower()
        if row.get("version", "").isdigit() and COMMIT.fullmatch(commit):
            pins[row["version"]] = commit
    blocks = defaultdict(list)
    for block in tree["blocks"]:
        blocks[block["heading"]].append(block)
    entries = [_Entry(heading, blocks[n], pins, english).build() for n, heading in enumerate(headings)
               if heading["parent"] == terms]
    # Related entries, in either direction, supply context for each other.
    anchors = {entry["anchor"] for entry in entries}
    neighbors = defaultdict(set)
    for entry in entries:
        for anchor in entry.pop("_linked"):
            if anchor in anchors and anchor != entry["anchor"]:
                neighbors[entry["anchor"]].add(anchor)
                neighbors[anchor].add(entry["anchor"])
    for entry in entries:
        entry["neighbors"] = sorted(neighbors[entry["anchor"]])
    issues = []
    if not pins:
        issues.append({"code": "source_pins_missing",
                       "message": "The glossary has no readable Source Pins table; evidence links have no URLs."})
    return {
        "schema": INDEX_SCHEMA, "builder": builder, "glossary_sha256": digest,
        "built_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "path": GLOSSARY, "title": next((h["text"] for h in headings if h["level"] == 1), None),
        "front_matter": front, "source_pins": pins,
        "anchors": [heading["anchor"] for heading in headings],
        "entries": entries, "issues": issues,
    }


class _Entry:
    """Parse one `### Term` entry: header line, definition, version notes, and related entries."""

    def __init__(self, heading: dict, blocks: list[dict], pins: dict[str, str], english: frozenset[str]):
        self.heading = heading
        self.blocks = blocks
        self.pins = pins
        self.english = english
        self.issues: list[dict] = []

    def build(self) -> dict:
        name = _render(*_markers(self.heading["inline"])[:2])["text"]
        header, paragraphs, note_items, related = None, [], [], []
        in_notes = False
        for block in self.blocks:
            if block["type"] == "paragraph":
                paragraph = self._paragraph(block["inline"], block["lines"])
                if header is None and not paragraphs and re.match(r"(?:Aliases|Checked on):", paragraph["text"]):
                    header = paragraph
                elif paragraph["text"].startswith("Version notes:"):
                    in_notes = True
                elif paragraph["text"].startswith("Related:"):
                    related = paragraph["links"]["entries"]
                else:
                    paragraphs.append(paragraph)
                    in_notes = False
            elif block["type"] == "list" and in_notes:
                note_items += block["items"]
            else:
                paragraphs += self._other(block)
        aliases, checked = self._header(header)
        notes = self._notes(note_items, checked)
        forms = self._forms(name, aliases)
        main, source = self._main_version(paragraphs, checked, notes)
        lead = [s for p in paragraphs[:1] for s in p["_sentences"][:1]]
        last = max((block["lines"][1] for block in self.blocks if block.get("lines")), default=self.heading["line"])
        links = {"entries": [], "pages": []}
        for paragraph in [*paragraphs, *(note["_paragraph"] for note in notes.values())]:
            for key in links:
                links[key] += [target for target in paragraph["links"][key] if target not in links[key]]
        return {
            "anchor": self.heading["anchor"], "term": name, "lines": [self.heading["line"], last],
            "aliases": [{key: alias[key] for key in ("text", "relation", "versions")} for alias in aliases],
            "forms": forms, "checked_on": checked, "main_version": main, "main_version_source": source,
            "summary": lead[0]["text"] if lead else None,
            "spoken_summary": lead[0]["spoken"] if lead else None,
            "definition": [_public(paragraph) for paragraph in paragraphs],
            "notes": {version: {key: value for key, value in note.items() if key != "_paragraph"}
                      for version, note in notes.items()},
            "related": related, "links": links,
            "symbols": sorted({symbol for text in [*(f["text"] for f in forms if f["kind"] == "code"),
                                                   *(code for p in paragraphs for code in p["_codes"])]
                               for symbol in _symbols(text)}),
            "evidence_files": sorted({c["path"] for p in [*paragraphs, *notes.values()] for c in p["citations"]
                                      if c.get("path")}),
            "issues": self.issues,
            "_linked": list(dict.fromkeys([*related, *links["entries"]])),
        }

    def _issue(self, code: str, message: str) -> None:
        self.issues.append({"code": code, "message": message})

    def _paragraph(self, inline: dict, lines) -> dict:
        text, codes, links = _markers(inline)
        whole = _render(text, codes)
        sentences = [_render(text[start:end], codes) for start, end in _sentence_spans(text)]
        return {
            "lines": lines, "text": whole["text"],
            "citations": [self._citation(links[n]) for n in whole["citations"]],
            "links": {"entries": [link["fragment"] for link in links if link.get("kind") == "anchor"
                                  and link.get("fragment")],
                      "pages": [link["target"] for link in links if link.get("kind") == "wiki"]},
            "_sentences": [sentence for sentence in sentences if sentence["text"]], "_codes": whole["_codes"],
        }

    def _other(self, block: dict) -> list[dict]:
        """Render a list, table, or code block inside a definition as paragraphs."""
        if block["type"] == "list":
            return [paragraph for item in block["items"] for child in item["blocks"]
                    for paragraph in self._other(child)]
        if block["type"] == "paragraph":
            return [self._paragraph(block["inline"], block["lines"])]
        if block["type"] == "table":
            rows = [[self._paragraph(cell, block["lines"]) for cell in cells]
                    for cells in [block["header"], *(row["cells"] for row in block["rows"])]]
            cells = [cell for row in rows for cell in row]
            return [{"lines": block["lines"], "text": "\n".join(" | ".join(c["text"] for c in row) for row in rows),
                     "citations": [c for cell in cells for c in cell["citations"]],
                     "links": {key: [t for cell in cells for t in cell["links"][key]] for key in ("entries", "pages")},
                     "_sentences": [], "_codes": [code for cell in cells for code in cell["_codes"]]}]
        if block["type"] == "code":
            return [{"lines": block["lines"], "text": block["content"].rstrip("\n"), "citations": [],
                     "links": {"entries": [], "pages": []}, "_sentences": [], "_codes": []}]
        return []

    def _citation(self, link: dict) -> dict:
        record = {"label": link["text"], "href": link["href"]}
        if link.get("kind") != "citation":
            return record | {"kind": link.get("kind")}
        version, path, lines = link["postgres_version"], link["source_path"], link.get("lines")
        pin = self.pins.get(str(version))
        if pin is None:
            url = None
        elif not path:
            url = f"https://github.com/{POSTGRES_REPOSITORY}/tree/{pin}"
        else:
            url = blob_url(POSTGRES_REPOSITORY, pin, path, tuple(lines) if lines else None)
        return record | {"version": version, "path": path, "lines": lines, "url": url}

    def _header(self, header: dict | None) -> tuple[list[dict], list[int]]:
        if header is None:
            self._issue("header_missing", "The entry has no **Aliases:** or **Checked on:** line.")
            return [], []
        aliases_text, found, checked_text = header["text"].partition("Checked on:")
        checked = sorted({int(v) for v in re.findall(r"\d+", checked_text)})
        if not found or not checked:
            self._issue("checked_on_missing", "The entry does not state the versions it was checked on.")
        aliases_text = aliases_text.strip().removeprefix("Aliases:").strip().removesuffix(".")
        return [_alias(text) for text in _split_aliases(aliases_text)], checked

    def _notes(self, items: list[dict], checked: list[int]) -> dict[str, dict]:
        notes: dict[str, dict] = {}
        for item in items:
            paragraphs = [p for child in item["blocks"] for p in self._other(child)]
            if not paragraphs:
                continue
            paragraph = paragraphs[0]
            text = " ".join(p["text"] for p in paragraphs)
            match = NOTE.match(text)
            if not match:
                self._issue("note_unreadable", f"Version note on line {paragraph['lines'][0]} does not open with "
                                               "'PostgreSQL NN: Holds', 'Differs', or 'Not present'.")
                continue
            version, status, body = int(match.group(1)), NOTE_STATUS[match.group(2)], match.group(3)
            citations = [c for p in paragraphs for c in p["citations"]]
            references = []
            for groups in REFERENCE.findall(body):
                other = int(next(group for group in groups if group))
                if other != version and other in checked and other not in references:
                    references.append(other)
            if version not in checked:
                self._issue("note_version_unchecked",
                            f"The entry has a PostgreSQL {version} note but does not list {version} as checked.")
            cited = sorted({c["version"] for c in citations if "version" in c} - {version})
            if cited:
                self._issue("note_cites_other_version", f"The PostgreSQL {version} note also cites the "
                            + ", ".join(f"raw/postgres-{v}/" for v in cited) + " checkout.")
            notes[str(version)] = {
                "version": version, "status": status,
                "exceptions": status == "holds" and bool(EXCEPTION.search(body)),
                "references": references, "lines": [paragraphs[0]["lines"][0], paragraphs[-1]["lines"][1]],
                "text": text, "citations": citations, "_paragraph": paragraph,
            }
        return notes

    def _forms(self, name: str, aliases: list[dict]) -> list[dict]:
        forms: list[dict] = []
        seen: set[tuple[str, str]] = set()

        def add(display: str, source: str, relation: str = "synonym", versions: list[int] | None = None) -> None:
            for variant in _variants(display):
                form = _form(variant, source, relation, versions, self.english)
                if form and (key := (_matcher_kind(form), _key(form))) not in seen:
                    seen.add(key)
                    forms.append(form)

        add(name, "name")
        for part in _name_parts(name):
            add(part, "name")
        for alias in aliases:
            for display in alias["forms"]:
                add(display, "alias", alias["relation"], alias["versions"])
        return forms

    def _main_version(self, paragraphs: list[dict], checked: list[int], notes: dict) -> tuple[int | None, str | None]:
        """Return the version the main paragraph describes, and how it was determined.

        The glossary's scope says each other checked version has its own note, so
        the one checked version without a note is the main paragraph's. Citations,
        then an opening "In PostgreSQL NN", decide when the notes do not.
        """
        unnoted = [version for version in checked if str(version) not in notes]
        cited = sorted({c["version"] for p in paragraphs for c in p["citations"] if "version" in c})
        opening = OPENING_VERSION.match(paragraphs[0]["text"]) if paragraphs else None
        if len(unnoted) == 1:
            main, source = unnoted[0], "notes"
        elif len(cited) == 1:
            main, source = cited[0], "citations"
        elif opening:
            main, source = int(opening.group(1)), "opening"
        else:
            main, source = None, None
            self._issue("main_version_unknown", "Cannot tell which version the main paragraph describes: "
                        f"checked on {_versions(checked)}, with notes for {_versions(sorted(map(int, notes)))}.")
        if main is not None:
            if checked and main not in checked:
                self._issue("main_version_unchecked", f"The main paragraph cites PostgreSQL {main}, which the "
                            "entry does not list as checked.")
            for version in unnoted:
                if version != main:
                    self._issue("version_note_missing", f"PostgreSQL {version} is listed as checked but has no note.")
            if cited and cited != [main]:
                self._issue("definition_cites_other_version", f"The main paragraph describes PostgreSQL {main} "
                            f"but cites the {_versions(cited)} checkouts.")
        return main, source


def _markers(inline: dict) -> tuple[str, list[str], list[dict]]:
    """Flatten inline runs into text with code and citation markers, as document.py does."""
    links = [resolve_links(GLOSSARY, [{"href": link["href"], "section": None}], [])[0] for link in inline["links"]]
    for number, link in enumerate(links):
        link["text"] = " ".join("".join(run["text"] for run in inline["runs"] if run["link"] == number).split())
    text, codes, cited = "", [], set()
    for run in inline["runs"]:
        number = run["link"]
        if run["kind"] == "image":
            continue
        if number is not None and links[number].get("kind") == "citation":
            if number not in cited:
                cited.add(number)
                text += f"{CITE}{number}{CITE_END}"
            continue
        if run["kind"] == "code":
            codes.append(run["text"])
            text += f"{CODE}{len(codes) - 1}{CODE_END}"
        elif run["kind"] == "html":
            text += " " if LINE_BREAK.fullmatch(run["text"].strip()) else ""
        else:
            text += run["text"]
    return text, codes, links


def _public(paragraph: dict) -> dict:
    return {key: value for key, value in paragraph.items() if not key.startswith("_")}


def _split_aliases(text: str) -> list[str]:
    """Split an alias list at commas outside code spans and parentheses."""
    parts, current, depth, code = [], "", 0, False
    for character in text:
        if character == "`":
            code = not code
        elif not code and character in "()":
            depth = max(depth + (1 if character == "(" else -1), 0)
        if character == "," and not code and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += character
    return [part.strip() for part in [*parts, current] if part.strip()]


def _alias(text: str) -> dict:
    """Interpret an alias: a contrast, a version-limited name, or a name with its expansion."""
    alias = {"text": text, "relation": "synonym", "versions": None, "forms": [text]}
    match = QUALIFIER.fullmatch(text)
    if match and match.group("base").count("`") % 2 == 0:
        base, qualifier = match.group("base").strip(), match.group("qualifier").strip()
        if qualifier.lower() == "contrast":
            alias.update(relation="contrast", forms=[base])
        elif VERSION_QUALIFIER.fullmatch(qualifier):
            alias.update(versions=sorted({int(v) for v in re.findall(r"\d+", qualifier)}), forms=[base])
        else:
            alias["forms"] = [base, qualifier]
    return alias


def _name_parts(name: str) -> list[str]:
    """Split a paired heading such as "Custom and generic plan" into "Custom plan" and "generic plan"."""
    left, separator, right = name.partition(" and ")
    if not separator or " and " in right:
        return []
    right_words = right.split()
    if len(left.split()) == 1 and len(right_words) > 1 and not DISTINCTIVE.search(left.replace("`", "")):
        left = f"{left} {right_words[-1]}"
    return [left, right]


def _variants(display: str) -> list[str]:
    """Return a form, plus the distinctive code span inside a phrase such as "`enable_*` penalty"."""
    spans = re.findall(r"`([^`]+)`", display)
    rest = re.sub(r"`[^`]+`", "", display).strip()
    if len(spans) == 1 and rest and (DISTINCTIVE.search(spans[0]) or "*" in spans[0]):
        return [display, f"`{spans[0]}`"]
    return [display]


def _form(display: str, source: str, relation: str, versions: list[int] | None,
          english: frozenset[str]) -> dict | None:
    """Classify a name or alias by how it may be matched in a document."""
    text = " ".join(display.replace("`", "").split())
    if not re.search(r"\w", text):
        return None
    code = bool(re.fullmatch(r"`[^`]+`", display.strip()))
    if "*" in text or "..." in text:
        kind = "pattern"
        needs_context = len(re.sub(r"\.\.\.|[*()\s]", "", text)) < PATTERN_LITERAL
    elif code:
        kind = "code"
        needs_context = not DISTINCTIVE.search(text) and (len(text) <= SHORT_FORM or text.lower() in english)
    elif ACRONYM.fullmatch(text):
        kind, needs_context = "acronym", sum(character.isalpha() for character in text) <= 2
    elif " " in text:
        kind, needs_context = "phrase", False
    elif DISTINCTIVE.search(text):
        kind, needs_context = "code", False
    else:
        kind, needs_context = "word", len(text) <= SHORT_FORM or text.lower() in english
    return {"text": text, "kind": kind, "code": code, "needs_context": needs_context,
            # A code word such as `auto` matches only where the document also marks it as code.
            "code_only": kind == "code" and needs_context, "source": source, "relation": relation,
            "versions": versions}


def _matcher_kind(form: dict) -> str:
    """Return 'exact' (case-sensitive), 'folded' (case- and hyphen-insensitive), or 'pattern'."""
    if form["kind"] == "pattern" or (form["kind"] == "code" and COMPLEX_CODE.search(form["text"].removesuffix("()"))):
        return "pattern"
    return "exact" if form["kind"] in ("code", "acronym") else "folded"


def _key(form: dict) -> str:
    kind = _matcher_kind(form)
    if kind == "exact":
        return form["text"].removesuffix("()")
    return _fold(form["text"]) if kind == "folded" else form["text"]


def _fold(text: str) -> str:
    return re.sub(r"[\s-]+", " ", text.lower()).strip()


def _symbols(text: str) -> set[str]:
    return {symbol for symbol in SYMBOL.findall(text) if SYMBOL_SHAPE.search(symbol)}


def _versions(versions) -> str:
    versions = [str(version) for version in versions]
    if len(versions) < 2:
        return versions[0] if versions else "no versions"
    return ", ".join(versions[:-1]) + " and " + versions[-1]


# Matching --------------------------------------------------------------------------------------


class _Matcher:
    """Find glossary names and aliases in document text.

    Literal forms are compiled into two prefix-trie expressions that return the
    longest form at each position: a case-sensitive one for identifiers and
    acronyms, and one for words and phrases that runs on lowercased text with
    hyphens and spaces interchangeable. Forms with wildcards, placeholders, or
    spaces inside code get their own expressions.
    """

    def __init__(self, entries: list[dict]):
        self.exact: dict[str, list] = defaultdict(list)
        self.folded: dict[str, list] = defaultdict(list)
        patterns: dict[tuple[str, bool], list] = defaultdict(list)
        for number, entry in enumerate(entries):
            for form in entry["forms"]:
                kind = _matcher_kind(form)
                if kind == "pattern":
                    patterns[form["text"], form["code"]].append((number, form))
                else:
                    (self.exact if kind == "exact" else self.folded)[_key(form)].append((number, form))
        self.exact_pattern = re.compile(
            r"(?<![\w$])" + _trie(self.exact, re.escape) + r"(?:s|\(\))?(?![\w$])") if self.exact else None
        self.folded_pattern = re.compile(
            r"(?<![\w-])" + _trie(self.folded, lambda c: r"[\s-]+" if c == " " else re.escape(c))
            + r"(?:e?s)?(?![\w-])") if self.folded else None
        self.patterns = [(_pattern(text, code), code, owners) for (text, code), owners in patterns.items()]

    def find(self, text: str, *, code_block: bool) -> list[tuple[int, int, list]]:
        """Return (start, end, owners) for every candidate form; owners are (entry number, form) pairs."""
        found = []
        if self.exact_pattern:
            for match in self.exact_pattern.finditer(text):
                if owners := self._owners(self.exact, match.group(), folded=False):
                    found.append((match.start(), match.end(), owners))
        if self.folded_pattern and not code_block:
            lowered = text.lower()
            if len(lowered) != len(text):
                lowered = "".join(c.lower() if len(c.lower()) == 1 else c for c in text)
            for match in self.folded_pattern.finditer(lowered):
                if owners := self._owners(self.folded, match.group(), folded=True):
                    found.append((match.start(), match.end(), owners))
        for pattern, case_sensitive, owners in self.patterns:
            if case_sensitive or not code_block:
                found += [(match.start(), match.end(), owners) for match in pattern.finditer(text)]
        return found

    @staticmethod
    def _owners(table: dict, matched: str, *, folded: bool) -> list:
        """Look up a match, allowing a plural on words, phrases, and acronyms, and `()` on code."""
        if folded:
            key = _fold(matched)
            for candidate in (key, key[:-2] if key.endswith("es") else None, key[:-1] if key.endswith("s") else None):
                if candidate and candidate in table:
                    return table[candidate]
            return []
        if matched in table:
            return table[matched]
        if matched.endswith("()") and matched[:-2] in table:
            return [owner for owner in table[matched[:-2]] if owner[1]["kind"] == "code"]
        if matched.endswith("s") and matched[:-1] in table:
            return [owner for owner in table[matched[:-1]] if owner[1]["kind"] == "acronym"]
        return []


def _trie(keys, escape) -> str:
    """Compile keys into one expression that prefers the longest key at each position."""
    trie: dict = {}
    for key in keys:
        node = trie
        for character in key:
            node = node.setdefault(character, {})
        node[""] = {}

    def render(node: dict) -> str:
        branches = [escape(character) + render(child) for character, child in sorted(node.items()) if character]
        if not branches:
            return ""
        body = branches[0] if len(branches) == 1 else "(?:" + "|".join(branches) + ")"
        return f"(?:{body})?" if "" in node else body

    return render(trie)


def _pattern(text: str, case_sensitive: bool) -> re.Pattern:
    """Compile a form with `*` wildcards, `...` placeholders, spaces, or parentheses."""
    body = text.removesuffix("()")
    pieces = []
    for token in PATTERN_TOKEN.findall(body):
        if token == "...":
            pieces.append(r".{1,80}?")
        elif token == "*":
            pieces.append(r"[\w$]+")
        elif token.isspace():
            pieces.append(r"\s+")
        elif token in "()":
            pieces.append(r"\s*\(\s*" if token == "(" else r"\s*\)")
        else:
            pieces.append(re.escape(token))
    if body != text:
        pieces.append(r"(?:\(\))?")
    before = r"(?<![\w$])" if re.match(r"[\w$*]", body) else ""
    after = r"(?![\w$])" if re.search(r"[\w$*)]$", text) else ""
    return re.compile(before + "".join(pieces) + after, 0 if case_sensitive else re.IGNORECASE)


def _plain(display: str) -> tuple[str, list[tuple[int, int]]]:
    """Remove the backticks from display text and return the code spans' positions in the result."""
    pieces, spans, position, length = [], [], 0, 0
    for match in CODE_SPAN.finditer(display):
        before = display[position:match.start()]
        code = match.group(2)
        if len(code) > 2 and code.startswith(" ") and code.endswith(" "):
            code = code[1:-1]
        pieces += [before, code]
        length += len(before)
        spans.append((length, length + len(code)))
        length += len(code)
        position = match.end()
    pieces.append(display[position:])
    return "".join(pieces), spans


def _norm(text: str) -> str:
    return text.strip().removesuffix("()").lower()


class _Selector:
    """Find, disambiguate, rank, and version-scope the glossary entries for one document."""

    def __init__(self, index: dict, document: dict, sources: dict, built: dict):
        self.index = index
        self.document = document
        self.sources = sources
        self.built = built
        self.entries = index["entries"]
        self.by_anchor = {entry["anchor"]: number for number, entry in enumerate(self.entries)}
        self.version = document["document"]["version"]
        self.sections = {section["id"]: section for section in document["sections"]}
        self.decisions = {entry["section"]: entry["decision"] for entry in document["coverage"]["sections"]}
        question = document["subject"].get("question") or {}
        self.central = {*question.get("sentences", []), *question.get("blocks", []),
                        *(s["id"] for s in document["conclusions"]["sentences"])}
        self.units = self._units()
        self.unit_by_id = {unit["id"]: unit for unit in self.units}
        self.matcher = _Matcher(self.entries)

    def _units(self) -> list[dict]:
        """Return the headings, sentences, table rows, and code blocks that are narrated or shown.

        Each unit records the blocks whose context applies to it: its own block, or
        for a heading, every block of its section and subsections.
        """
        units, files, symbols = [], defaultdict(set), defaultdict(set)
        for section in self.document["sections"]:
            role = section["role"]
            if role in ("reference", "navigation"):
                continue
            base = {"section": section["id"], "role": role, "decision": self.decisions.get(section["id"])}
            if section["text"]:
                units.append(base | {"id": section["id"], "kind": "heading", "block": section["id"],
                                     "line": section["lines"][0], "text": section["text"],
                                     "central": role == "title"})
            for block in _leaves(section["blocks"]):
                if block.get("use") not in ("narrate", "display"):
                    continue
                citations = block.get("citations", [])
                if block["type"] == "code":
                    # A prompt quoted in a plain-text block is prose; other code is matched as code.
                    prompt = block["id"] in self.central
                    units.append(base | {"id": block["id"], "kind": "prompt" if prompt else "code",
                                         "block": block["id"], "text": block["content"], "central": prompt,
                                         "line": block["lines"][0] + (1 if block["fenced"] else 0)})
                elif block["type"] == "table":
                    rows = [(f"{block['id']}.h", block["lines"][0], block["header"]),
                            *((row["id"], row["line"], row["cells"]) for row in block["rows"])]
                    citations = [c for _id, _line, cells in rows for cell in cells for c in cell["citations"]]
                    for row_id, line, cells in rows:
                        units.append(base | {"id": row_id, "kind": "row", "block": block["id"], "line": line,
                                             "text": " | ".join(cell["text"] for cell in cells), "central": False})
                else:
                    for sentence in block.get("sentences", []):
                        if not sentence["maintenance"]:
                            units.append(base | {"id": sentence["id"], "kind": "sentence", "block": block["id"],
                                                 "line": sentence["lines"][0], "text": sentence["text"],
                                                 "central": sentence["id"] in self.central})
                files[block["id"]] |= {link["source_path"] for link in map(self.document["links"].__getitem__,
                                                                            citations)
                                       if link.get("kind") == "citation" and link.get("source_path")}
        for unit in units:
            if unit["kind"] == "code":
                unit["plain"], unit["code_spans"] = unit["text"], [(0, len(unit["text"]))]
            else:
                unit["plain"], unit["code_spans"] = _plain(unit["text"])
            symbols[unit["block"]] |= _symbols(unit["plain"])
        blocks_by_section = defaultdict(set)
        for unit in units:
            if unit["kind"] != "heading":
                blocks_by_section[unit["section"]].add(unit["block"])
        for unit in units:
            unit["context_blocks"] = sorted(set().union(*(blocks_by_section[section] for section in
                                                          self._subtree(unit["section"])))
                                            if unit["kind"] == "heading" else {unit["block"]})
        self.block_files, self.block_symbols = files, symbols
        return units

    def _subtree(self, section_id: str) -> list[str]:
        found, pending = [], [section_id]
        while pending:
            current = pending.pop()
            found.append(current)
            pending += self.sections[current]["children"]
        return found

    # Candidates ------------------------------------------------------------------------------

    def _scan(self) -> list[dict]:
        found = []
        for unit in self.units:
            code_block = unit["kind"] == "code"
            spans: dict[tuple[int, int], list] = defaultdict(list)
            for start, end, owners in self.matcher.find(unit["plain"], code_block=code_block):
                in_code = code_block or any(a < end and start < b for a, b in unit["code_spans"])
                spans[start, end] += [owner for owner in owners if in_code or not owner[1]["code_only"]]
            chosen: list[tuple[int, int]] = []
            # The longest match wins where forms overlap, such as "HOT-blocking column" over "HOT".
            for start, end in sorted((span for span, owners in spans.items() if owners),
                                     key=lambda span: (span[0] - span[1], span[0])):
                if all(end <= a or b <= start for a, b in chosen):
                    chosen.append((start, end))
            for start, end in sorted(chosen):
                forms: dict[int, dict] = {}
                for number, form in spans[start, end]:
                    if number not in forms or _form_rank(form) > _form_rank(forms[number]):
                        forms[number] = form
                found.append({"unit": unit, "start": start, "end": end, "text": unit["plain"][start:end],
                              "in_code": code_block or any(a < end and start < b for a, b in unit["code_spans"]),
                              "forms": forms})
        return found

    def _links(self) -> tuple[list[dict], list[dict]]:
        """Return occurrences for explicit glossary links, and links to anchors the glossary lacks."""
        occurrences, missing = [], []
        headings = set(self.index["anchors"])
        for link in self.document["links"]:
            if link.get("kind") != "glossary" or not link.get("fragment"):
                continue
            number = self.by_anchor.get(link["fragment"])
            if number is None:
                if link["fragment"] not in headings:
                    missing.append(link)
                continue
            unit = self._unit_at(link.get("at") or "")
            section = self.sections.get(link["section"], {})
            occurrences.append({
                "entry": number, "at": link.get("at"), "section": link["section"], "line": link["line"],
                "text": link["text"], "form": link["text"], "method": "link", "support": "link", "context": [],
                "in_code": False, "central": bool(unit and unit["central"]), "role": section.get("role"),
                "decision": self.decisions.get(link["section"]), "relation": "synonym",
                "block": unit["block"] if unit else link["section"],
            })
        return occurrences, missing

    def _unit_at(self, identifier: str) -> dict | None:
        """Return the unit holding a link: its sentence, or the row or block that contains its cell."""
        while identifier:
            if identifier in self.unit_by_id:
                return self.unit_by_id[identifier]
            identifier = identifier.rpartition(".")[0]
        return None

    # Selection -------------------------------------------------------------------------------

    def build(self) -> dict:
        """Decide every candidate occurrence, then write the record.

        An occurrence is accepted when exactly one candidate entry has the best
        support. Support comes from an explicit link to the entry, a distinctive
        form, another distinctive form of the same entry in the same section, or
        context in the same block: a source file that the block and the entry
        both cite, a symbol from the entry's definition, or a related entry already
        accepted there. Acceptance repeats until nothing changes. Only entries
        accepted without help from other related entries count as related context,
        so generic words cannot vouch for each other. A word left without support
        follows the entry that the same word was accepted for elsewhere in the
        document (one sense per discourse), but a code value such as `auto` does
        not, because different settings share such values; otherwise it is ambiguous.
        """
        candidates = self._scan()
        link_occurrences, missing_links = self._links()
        linked = {occurrence["entry"] for occurrence in link_occurrences}
        # Sections where an entry has an unambiguous distinctive form; a contrast names another concept.
        specific: dict[int, set[str]] = defaultdict(set)
        for candidate in candidates:
            if len(candidate["forms"]) == 1:
                (number, form), = candidate["forms"].items()
                if not form["needs_context"] and form["relation"] == "synonym":
                    specific[number].add(candidate["unit"]["section"])
        accepted = list(link_occurrences)
        concepts: dict[str, set[str]] = defaultdict(set)
        for occurrence in accepted:
            concepts[occurrence["block"]].add(self.entries[occurrence["entry"]]["anchor"])
        undecided, changed = candidates, True
        while changed:
            changed, waiting = False, []
            for candidate in undecided:
                supports = {number: self._support(number, form, candidate["unit"], linked, specific, concepts)
                            for number, form in candidate["forms"].items()}
                ranked = sorted(supports, key=lambda n: _score(supports[n], candidate["forms"][n]), reverse=True)
                best = _score(supports[ranked[0]], candidate["forms"][ranked[0]])
                top = [n for n in ranked if _score(supports[n], candidate["forms"][n]) == best]
                if supports[ranked[0]][0] is None or len(top) > 1:
                    waiting.append((candidate, supports, ranked, top))
                    continue
                level, context = supports[top[0]]
                accepted.append(self._accept(candidate, top[0], supports[top[0]], ranked))
                if level != "context" or any(not reason.startswith("entry:") for reason in context):
                    concepts[candidate["unit"]["block"]].add(self.entries[top[0]]["anchor"])
                changed = True
            undecided = [item[0] for item in waiting]
        established = {(o["entry"], _fold(o["form"])) for o in accepted if o["method"] != "link"}
        ambiguous = []
        for candidate, supports, ranked, top in waiting:
            if supports[ranked[0]][0] is not None:
                senses, reason = top, "collision"
            else:
                senses = [n for n in ranked if candidate["forms"][n]["kind"] != "code"
                          and (n, _fold(candidate["forms"][n]["text"])) in established]
                if len(senses) == 1:
                    accepted.append(self._accept(candidate, senses[0], ("discourse", []), ranked))
                    continue
                reason = "collision" if senses else "needs_context"
            ambiguous.append(self._occurrence(candidate) | {"reason": reason, "candidates": [
                {"entry": n, "form": candidate["forms"][n], "support": supports[n][0], "context": supports[n][1]}
                for n in (senses or ranked)]})
        return self._record(accepted, ambiguous, missing_links)

    def _support(self, number: int, form: dict, unit: dict, linked: set, specific: dict[int, set[str]],
                 concepts: dict[str, set[str]]) -> tuple[str | None, list[str]]:
        """Return how an occurrence is supported, and the context found for its entry around it."""
        entry = self.entries[number]
        blocks = unit["context_blocks"]
        files = set().union(*(self.block_files[block] for block in blocks)) & set(entry["evidence_files"])
        symbols = (set().union(*(self.block_symbols[block] for block in blocks)) & set(entry["symbols"])) - {
            form["text"].removesuffix("()")}
        related = set().union(*(concepts[block] for block in blocks)) & set(entry["neighbors"])
        context = ([f"file:{path}" for path in sorted(files)] + [f"symbol:{name}" for name in sorted(symbols)]
                   + [f"entry:{anchor}" for anchor in sorted(related)])
        if number in linked:
            return "link", context
        if not form["needs_context"]:
            return "specific", context
        sections = self._subtree(unit["section"]) if unit["kind"] == "heading" else [unit["section"]]
        if specific[number].intersection(sections):
            return "form", context
        return ("context" if context else None), context

    def _occurrence(self, candidate: dict) -> dict:
        unit = candidate["unit"]
        offset = unit["plain"][:candidate["start"]].count("\n") if unit["kind"] == "code" else 0
        return {"at": unit["id"], "section": unit["section"], "block": unit["block"], "role": unit["role"],
                "line": unit["line"] + offset, "text": candidate["text"], "in_code": candidate["in_code"],
                "central": unit["central"], "decision": unit["decision"]}

    def _accept(self, candidate: dict, number: int, support: tuple[str, list[str]], ranked: list[int]) -> dict:
        form = candidate["forms"][number]
        occurrence = self._occurrence(candidate) | {
            "entry": number, "form": form["text"], "method": _method(form), "support": support[0],
            "context": support[1][:5], "relation": form["relation"]}
        if form["versions"]:
            occurrence["alias_versions"] = form["versions"]
        if len(ranked) > 1:
            occurrence["alternatives"] = [self.entries[n]["anchor"] for n in ranked if n != number]
        return occurrence

    # Output ----------------------------------------------------------------------------------

    def _record(self, accepted: list[dict], ambiguous: list[dict], missing_links: list[dict]) -> dict:
        by_entry: dict[int, list[dict]] = defaultdict(list)
        seen = set()
        for occurrence in accepted:
            key = (occurrence["entry"], occurrence["at"], _norm(occurrence["text"]))
            if key in seen:
                continue
            seen.add(key)
            by_entry[occurrence["entry"]].append(occurrence)
        matches = sorted((self._entry(number, occurrences) for number, occurrences in by_entry.items()),
                         key=lambda m: (TIERS.index(m["tier"]), -m["relevance"], m["occurrences"][0]["line"] or 0))
        for rank, match in enumerate(matches, 1):
            match["rank"] = rank
        ambiguity = self._ambiguous(ambiguous)
        unmatched = self._unmatched(accepted, ambiguous, missing_links)
        document = self.document["document"]
        glossary = self.sources["glossary"]
        issues = self._issues(matches, ambiguity, unmatched, missing_links)
        return {
            "schema": SCHEMA_VERSION,
            "request_id": self.document["request_id"],
            "status": "passed",
            "matched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "document": {"path": document["path"], "url": document["url"], "sha256": document["sha256"],
                         "version": self.version, "wiki_commit": document["wiki_commit"]},
            "glossary": {
                "path": glossary["path"], "url": glossary["url"], "sha256": glossary["sha256"],
                "verified": (self.index.get("front_matter") or {}).get("verified"),
                "entries": len(self.entries), "source_pin": (glossary.get("pin_for_version") or {}).get("commit"),
                "index": self.built,
            },
            "version": self.version,
            "subject": self._subject(accepted, ambiguous),
            "counts": {
                "matched": len(matches), **{tier: sum(m["tier"] == tier for m in matches) for tier in TIERS},
                "ambiguous": len(ambiguity), "unmatched": len(unmatched),
            },
            "matches": matches,
            "ambiguous": ambiguity,
            "unmatched": unmatched,
            # A semantic matcher may propose further entries later; each proposal must cite a supporting passage.
            "semantic_matching": {"used": False, "reason": "Matches come only from explicit links, names, aliases, "
                                                           "acronyms, and identifiers found in the document."},
            "issues": issues,
        }

    def _entry(self, number: int, occurrences: list[dict]) -> dict:
        entry = self.entries[number]
        occurrences.sort(key=lambda o: (o["line"] or 0, o["at"] or ""))
        central = sum(o["central"] for o in occurrences)
        linked = any(o["method"] == "link" for o in occurrences)
        weight = sum(DECISION_WEIGHTS.get(o["decision"], 0.1) for o in occurrences)
        if central:
            tier = "central"
        elif any(o["decision"] in ("explain", "summarize") for o in occurrences):
            tier = "supporting"
        else:
            tier = "peripheral"
        best = max((o["support"] for o in occurrences), key=lambda level: SUPPORT_LEVELS[level])
        public = [{key: value for key, value in o.items() if key not in ("entry", "block", "role")}
                  for o in occurrences]
        return {
            "rank": None, "anchor": entry["anchor"], "term": entry["term"], "url": self._entry_url(entry),
            "glossary_lines": entry["lines"], "tier": tier,
            "relevance": round(CENTRAL_WEIGHT * min(central, CENTRAL_LIMIT) + LINK_WEIGHT * linked + weight, 2),
            "confidence": CONFIDENCE[best],
            "relation": "synonym" if any(o["relation"] == "synonym" for o in occurrences) else "contrast",
            "linked": linked, "methods": sorted({o["method"] for o in occurrences}),
            "forms": list(dict.fromkeys(o["text"] for o in occurrences)),
            "count": len(occurrences), "sections": list(dict.fromkeys(o["section"] for o in occurrences)),
            "occurrences": public,
            "summary": entry["summary"], "spoken_summary": entry["spoken_summary"],
            "definition": entry["definition"],
            "version_scope": version_scope(entry, self.version),
            "note_statuses": {version: note["status"] for version, note in entry["notes"].items()},
            "related": entry["related"], "aliases": entry["aliases"], "issues": entry["issues"],
        }

    def _entry_url(self, entry: dict) -> str:
        glossary = self.sources["glossary"]
        return f"{blob_url(glossary['repository'], glossary['commit'], glossary['path'])}#{entry['anchor']}"

    def _ambiguous(self, ambiguous: list[dict]) -> list[dict]:
        groups: dict[tuple, dict] = {}
        for occurrence in ambiguous:
            key = (occurrence["reason"], tuple((self.entries[c["entry"]]["anchor"], _fold(c["form"]["text"]))
                                               for c in occurrence["candidates"]))
            group = groups.setdefault(key, {
                "text": occurrence["text"], "reason": occurrence["reason"], "central": False, "count": 0,
                "candidates": [{
                    "anchor": self.entries[c["entry"]]["anchor"], "term": self.entries[c["entry"]]["term"],
                    "url": self._entry_url(self.entries[c["entry"]]), "form": c["form"]["text"],
                    "form_kind": c["form"]["kind"], "relation": c["form"]["relation"], "support": c["support"],
                    "context": c["context"][:5], "summary": self.entries[c["entry"]]["summary"],
                    "version_status": version_scope(self.entries[c["entry"]], self.version)["status"],
                } for c in occurrence["candidates"]],
                "occurrences": [],
            })
            group["count"] += 1
            group["central"] |= occurrence["central"]
            if len(group["occurrences"]) < OCCURRENCE_SAMPLE:
                group["occurrences"].append({key: occurrence[key] for key in
                                             ("at", "section", "line", "text", "in_code", "central", "decision")})
        return sorted(groups.values(), key=lambda g: (not g["central"], g["reason"] != "collision", -g["count"],
                                                       g["occurrences"][0]["line"] or 0))

    def _unmatched(self, accepted: list[dict], ambiguous: list[dict], missing_links: list[dict]) -> list[dict]:
        """Return the document's concept terms that no glossary entry matched."""
        covered = {_norm(o["text"]) for o in [*accepted, *ambiguous]}
        missing = {link["fragment"] for link in missing_links}
        focus = set(self.document["subject"]["focus_terms"])
        result = []
        for term in self.document["terms"]:
            name, kind = term["term"], term["kind"]
            if kind not in CONCEPT_KINDS or (kind == "acronym" and name in GENERIC_ACRONYMS):
                continue
            anchors = term.get("glossary_anchors") or []
            if any(anchor in self.by_anchor for anchor in anchors):
                continue
            key = _norm(name)
            if key in covered or any(key.startswith(c + ".") for c in covered):
                continue
            ids = [o["at"] for o in term["occurrences"]]
            result.append({
                "term": name, "kind": kind, "reason": "glossary_anchor_missing" if set(anchors) & missing
                else "no_entry", "count": term["count"], "sections": term["sections"],
                "central": name in focus or any(i in self.central for i in ids),
                "first": term["occurrences"][0], **({"setting_source": term["setting_source"]}
                                                    if "setting_source" in term else {}),
            })
        return sorted(result, key=lambda t: (not t["central"], CONCEPT_KINDS.index(t["kind"]), -t["count"]))

    def _subject(self, accepted: list[dict], ambiguous: list[dict]) -> dict:
        """Map the subject's focus terms to glossary entries."""
        subject = self.document["subject"]
        focus = []
        for term in subject["focus_terms"]:
            key = _norm(term)

            def names(o, key=key):
                text = _norm(o["text"])
                return text == key or key.startswith(text + ".")

            anchors = list(dict.fromkeys(self.entries[o["entry"]]["anchor"] for o in accepted if names(o)))
            status = "matched" if anchors else "ambiguous" if any(names(o) for o in ambiguous) else "not_in_glossary"
            focus.append({"term": term, "status": status, "anchors": anchors})
        central = list(dict.fromkeys(self.entries[o["entry"]]["anchor"] for o in accepted if o["central"]))
        return {"title": subject["display_title"], "question": (subject.get("question") or {}).get("text"),
                "focus_terms": focus, "central_entries": central}

    def _issues(self, matches: list[dict], ambiguity: list[dict], unmatched: list[dict],
                missing_links: list[dict]) -> list[dict]:
        issues = []

        def add(severity, code, message, action=None, lines=()):
            issues.append({"severity": severity, "code": code, "message": message, "action": action,
                           "lines": sorted({line for line in lines if line})})

        version = self.version
        if (self.index.get("front_matter") or {}).get("verified") is False:
            add("note", "glossary_unverified", "The glossary declares `verified: false`; matched definitions supply "
                "vocabulary for the cross-check, not proof.")
        if missing_links:
            add("warning", "glossary_anchor_missing", "The document links to glossary anchors that do not exist: "
                + ", ".join(sorted({f"#{link['fragment']}" for link in missing_links})) + ".",
                "Fix the link or add the entry; the linked concept is listed as unmatched.",
                [link["line"] for link in missing_links])
        relevant = [m for m in matches if m["tier"] != "peripheral"]
        scopes = (
            ("not_present", "warning", "concept_not_present",
             "The glossary says these concepts do not exist in PostgreSQL {v}: {terms}.",
             "Check the document's PostgreSQL {v} evidence for these terms before narrating them."),
            ("differs", "note", "definition_differs",
             "These definitions differ in PostgreSQL {v}; use the {v} note, not the main paragraph: {terms}.", None),
            ("holds_with_exceptions", "note", "definition_has_exceptions",
             "These definitions hold in PostgreSQL {v} apart from the exceptions in their notes: {terms}.", None),
            ("unchecked", "warning", "definition_unchecked",
             "These entries were not checked on PostgreSQL {v}; treat them as coverage gaps: {terms}.",
             "Check these terms against the document's own PostgreSQL {v} citations."),
            ("unknown", "warning", "version_note_missing",
             "These entries list PostgreSQL {v} as checked but give no {v} note: {terms}.",
             "Check these terms against the document's own PostgreSQL {v} citations."),
        )
        for status, severity, code, message, action in scopes:
            found = [m for m in relevant if m["version_scope"]["status"] == status]
            if found:
                terms = ", ".join(f"{m['term']} (#{m['anchor']})" for m in found)
                add(severity, code, message.format(v=version, terms=terms), action and action.format(v=version),
                    [o["line"] for m in found for o in m["occurrences"][:1]])
        other = [(m, o) for m in matches for o in m["occurrences"]
                 if o.get("alias_versions") and version not in o["alias_versions"]]
        if other:
            add("note", "alias_other_version", "Some terms match aliases that the glossary limits to other versions: "
                + ", ".join(sorted({f"{o['text']} ({_versions(o['alias_versions'])})" for _m, o in other})) + ".",
                None, [o["line"] for _m, o in other])
        central = [group for group in ambiguity if group["central"]]
        if central:
            add("warning", "ambiguous_central", "Terms in the title, question, or conclusions match glossary entries "
                "ambiguously: " + ", ".join(sorted({group["text"] for group in central})) + ".",
                "The cross-check must resolve these before narration.",
                [o["line"] for group in central for o in group["occurrences"]])
        if len(ambiguity) > len(central):
            add("note", "ambiguous_terms", f"{len(ambiguity) - len(central)} other term(s) match glossary entries only "
                "ambiguously and are listed for review.")
        gaps = [term for term in unmatched if term["central"]]
        if gaps:
            add("note", "central_terms_not_in_glossary", "No glossary entry covers these central terms: "
                + ", ".join(f"`{term['term']}`" for term in gaps) + ".",
                "The cross-check records them as `not_in_glossary` and relies on the document's own evidence.",
                [term["first"]["line"] for term in gaps])
        structure = [m for m in relevant if m["issues"]]
        if structure:
            add("note", "glossary_entry_issues", "Some matched entries have structural issues: " + "; ".join(
                f"#{m['anchor']}: " + " ".join(issue["message"] for issue in m["issues"]) for m in structure))
        return sorted(issues, key=lambda issue: ("blocking", "warning", "note").index(issue["severity"]))


def _form_rank(form: dict) -> tuple:
    return (not form["needs_context"], form["relation"] == "synonym", form["source"] == "name")


def _score(support: tuple[str | None, list[str]], form: dict) -> tuple:
    level, words = support
    return (SUPPORT_LEVELS[level], form["relation"] == "synonym" if level else False, len(words) if level else 0)


def _method(form: dict) -> str:
    if form["kind"] == "acronym":
        return "acronym"
    if form["kind"] in ("code", "pattern"):
        return "identifier"
    return "term" if form["source"] == "name" else "alias"


def version_scope(entry: dict, version: int | None) -> dict:
    """Resolve which of an entry's statements apply to one PostgreSQL version.

    The main paragraph describes `main_version`. Another checked version has a note
    that opens with Holds, Differs, or Not present; a Holds note can still name
    exceptions. A note that says "as in 18" borrows the 18 note, so referenced
    notes are resolved, recursively, before the definition is used.
    """
    checked, main = entry["checked_on"], entry["main_version"]
    scope = {"version": version, "checked_on": checked, "main_version": main, "status": "unknown",
             "definition_applies": False, "note": None, "references": []}
    note = entry["notes"].get(str(version)) if version is not None else None
    if version is None:
        scope["explanation"] = "The document has no PostgreSQL version."
    elif version == main:
        scope.update(status="main", definition_applies=True,
                     explanation=f"The main paragraph describes PostgreSQL {version}.")
    elif note:
        references, resolved = _references(entry, note, {version})
        status = note["status"]
        if status == "holds" and (note["exceptions"] or any(
                ref.get("status") in ("differs", "not_present") or ref.get("exceptions") for ref in references)):
            status = "holds_with_exceptions"
        scope.update(status=status, definition_applies=status in ("holds", "holds_with_exceptions"),
                     note=note, references=references, references_resolved=resolved)
        borrowed = [str(ref["version"]) for ref in references if ref.get("status") != "main"]
        via = f", including what it borrows from the {_versions(borrowed)} note" if borrowed else ""
        scope["explanation"] = {
            "holds": f"The PostgreSQL {version} note says the main paragraph (PostgreSQL {main}) holds{via}.",
            "holds_with_exceptions": f"The main paragraph (PostgreSQL {main}) holds on {version} apart from the "
                                     f"exceptions in the {version} note{via}.",
            "differs": f"The PostgreSQL {version} note says the concept differs from the main paragraph "
                       f"(PostgreSQL {main}){via}; use the note.",
            "not_present": f"The PostgreSQL {version} note says the concept does not exist in PostgreSQL {version}.",
        }[status]
    elif version in checked:
        described = f"describes PostgreSQL {main}" if main is not None else "does not name a version"
        scope["explanation"] = (f"PostgreSQL {version} is listed as checked, but the entry has no {version} note "
                                f"and its main paragraph {described}.")
    elif checked:
        scope.update(status="unchecked", explanation=f"The entry was checked only on PostgreSQL {_versions(checked)}; "
                                                     f"its definition is unverified for {version}.")
    else:
        scope.update(status="unchecked", explanation="The entry does not say which versions it was checked on.")
    return scope


def _references(entry: dict, note: dict, visited: set[int]) -> tuple[list[dict], bool]:
    """Return the notes a note borrows from, in the order they are resolved, and whether all were found."""
    found, resolved = [], True
    for other in note["references"]:
        if other in visited:
            continue
        visited.add(other)
        if other == entry["main_version"]:
            found.append({"version": other, "status": "main", "text": None})
        elif str(other) in entry["notes"]:
            borrowed = entry["notes"][str(other)]
            found.append(borrowed)
            deeper, complete = _references(entry, borrowed, visited)
            found += deeper
            resolved &= complete
        else:
            found.append({"version": other, "status": "missing", "text": None})
            resolved = False
    return found, resolved


def _update_manifest(root: Path, run_dir: Path, *, status: str, record: dict | None = None,
                     digest: str | None = None, error: str | None = None) -> dict:
    path = run_dir / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    manifest["status"] = {"passed": "glossary_matched"}.get(status, status)
    invalidate_after(manifest, "glossary")
    entry: dict = {"status": status}
    if error:
        entry["error"] = error
    if record:
        glossary = record["glossary"]
        entry.update({
            "record": "glossary-matches.json", "sha256": digest, "matched_at": record["matched_at"],
            "schema": record["schema"], "version": record["version"],
            "glossary": {"path": glossary["path"], "sha256": glossary["sha256"]},
            "index": glossary["index"],
            "counts": record["counts"],
            "issues": {severity: sum(issue["severity"] == severity for issue in record["issues"])
                       for severity in ("blocking", "warning", "note")},
        })
    manifest["glossary"] = entry
    write_atomic(root, run_dir.relative_to(root) / "manifest.json",
                 (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"), label="Request")
    return entry
