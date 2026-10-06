"""Serve complete views of the evidence packet.

`view` returns the index (the request, the document, and one row per section),
one or more sections with the IDs of the evidence and glossary entries their units
use, the whole eligible document, evidence excerpts by ID, glossary entries, or the
configuration facts. `text` renders sections for reading in page order: one sentence,
table row, or block per line with its unit ID.

Nothing here selects or summarizes: text is returned exactly as the packet holds
it, and only fields that do not fit a view (a glossary entry's full occurrence
list, an indexed section's blocks) are replaced by counts.
"""

from __future__ import annotations

# Fields of the packet included in the index.
HEADER = ("notice", "lexical_notice", "document", "request", "speech", "review_state", "digests")
INDEX_ROW = ("id", "heading", "level", "parent", "role", "eligible", "caveat", "reason", "words")
GLOSSARY_ROW = ("id", "term", "tier", "result", "allowed_in_narration", "definition", "version")


def _in_section(unit: str, section: str) -> bool:
    return unit == section or unit.startswith(section + ".")


def _index(packet: dict) -> dict:
    glossary, evidence = packet["glossary"], packet["evidence"]
    view = {name: packet[name] for name in HEADER if name in packet}
    view["counts"] = {
        "sections": len(packet["sections"]), "eligible": sum(1 for s in packet["sections"] if s["eligible"]),
        "glossary_entries": len(glossary["entries"]), "glossary_ambiguous": len(glossary["ambiguous"]),
        "excerpts": len(evidence["excerpts"]), "whole_files": len(evidence["whole_files"]),
        "missing": len(evidence["missing"]), "settings": len(evidence["settings"])}
    # Files cited whole or absent from the snapshot have no excerpt to fetch, so the index lists them.
    view.update({name: evidence[name] for name in ("whole_files", "missing") if evidence[name]})
    rows = [{**{name: section[name] for name in INDEX_ROW}, "blocks": len(section["blocks"])}
            for section in packet["sections"]]
    return {**view, "sections": rows}


def _section(packet: dict, name: str) -> dict:
    section = next((s for s in packet["sections"] if s["id"] == name), None)
    if section is None:
        raise ValueError(f"The packet has no section '{name}'; list the section IDs with `packet` and no selector.")
    view = {name_: value for name_, value in section.items() if name_ != "blocks"}
    view["evidence"] = sorted(e["id"] for e in packet["evidence"]["excerpts"]
                              if any(_in_section(unit, name) for unit in e["cited_by"]))
    view["glossary"] = sorted(e["id"] for e in packet["glossary"]["entries"]
                              if any(_in_section(unit, name) for unit in e["occurrences"]))
    return {"section": view, "blocks": section["blocks"]}


def served(packet: dict) -> list[str]:
    """The sections the packet holds content for, in page order."""
    return [s["id"] for s in packet["sections"] if s["eligible"] and s["blocks"]]


def _sections(packet: dict, names: list[str]) -> dict:
    """One section keeps the single-section shape; several are returned in the order asked."""
    if len(names) == 1:
        return _section(packet, names[0])
    return {"sections": [_section(packet, name) for name in dict.fromkeys(names)]}


def _document(packet: dict) -> dict:
    """Every section with content, and the sections the packet leaves out with the reason."""
    kept = set(served(packet))
    return {"sections": [_section(packet, name) for name in served(packet)],
            "not_served": [{name: section[name] for name in ("id", "heading", "role", "eligible", "reason")}
                           for section in packet["sections"] if section["id"] not in kept]}


def _flags(unit: dict, marks: dict[str, str]) -> str:
    """What a reader must know about one unit beyond its text."""
    notes = [marks[unit["id"]]] if unit["id"] in marks else []
    lexical = unit.get("lexical") or {}
    if lexical.get("status") == "unconfirmed":
        notes.append("lexical unconfirmed" + (": " + ", ".join(lexical["not_found"]) + " not found"
                                              if lexical.get("not_found") else ""))
    if unit.get("corrections"):
        notes.append("correction " + ", ".join(unit["corrections"]))
    if unit.get("omitted_by_review"):
        notes.append("omitted by a recorded resolution")
    return "".join(f" [{note}]" for note in notes)


def _one_line(value: str) -> str:
    return " ".join(str(value).split())


def tidy(lines: list[str]) -> str:
    """Join lines into text, keeping one blank line between parts and code blocks as they are."""
    kept, fenced = [], False
    for line in lines:
        if line.lstrip().startswith("```"):
            fenced = not fenced
        if line or fenced or (kept and kept[-1]):
            kept.append(line)
    return "\n".join(kept).rstrip() + "\n"


def text(packet: dict, names: list[str] | None = None, *, marks: dict[str, str] | None = None) -> str:
    """Render sections as text to read in page order; every sentence, row, and block keeps its unit ID.

    `names` selects sections (all sections with content when omitted). `marks` adds a note to a unit,
    such as that no scene cites it.
    """
    marks = marks or {}
    document = packet["document"]
    lines = [f"# {document.get('title') or document['path']}", "",
             f"PostgreSQL {document['version']} · {document['path']} at wiki commit "
             f"{document['wiki_commit'][:12]}" + (" · the page is marked unverified" if document.get("unverified")
                                                    else ""),
             "", packet["notice"], ""]
    for name in (served(packet) if names is None else list(dict.fromkeys(names))):
        found = _section(packet, name)
        section = found["section"]
        about = [f"`{section['id']}`", f"level {section['level']}"]
        about += [f"under `{section['parent']}`"] if section.get("parent") else []
        about += [f"role {section['role']}"] if section.get("role") else []
        about += ["caveat section"] if section.get("caveat") else []
        about += [f"not eligible: {section['reason']}"] if not section["eligible"] else []
        lines += [f"## {section['heading']}", "", " · ".join(about), ""]
        for block in found["blocks"]:
            if block["type"] == "paragraph":
                lines += [f"- `{unit['id']}` {_one_line(unit['text'])}{_flags(unit, marks)}"
                          for unit in block["sentences"]]
            elif block["type"] == "table":
                lines += [f"- `{block['id']}` table: " + " | ".join(_one_line(cell) for cell in block["header"])]
                lines += [f"  - `{row['id']}` " + " | ".join(_one_line(cell) for cell in row["cells"])
                          + _flags(row, marks) for row in block["rows"]]
            elif block["type"] == "code":
                fence = "````" if "```" in block["content"] else "```"
                label = block.get("language") or block.get("kind") or ""
                lines += [f"- `{block['id']}` code" + (f" ({label})" if label else "") + _flags(block, marks), "",
                          fence + (block.get("language") or ""), block["content"].rstrip("\n"), fence, ""]
            elif block["type"] == "image":
                shown = ", ".join(f"{image.get('path')}" + (f" ({image['alt']})" if image.get("alt") else "")
                                  for image in block.get("images", []))
                lines.append(f"- `{block['id']}` image: {shown}{_flags(block, marks)}")
        cited: dict[str, list[str]] = {}
        for excerpt in packet["evidence"]["excerpts"]:
            for unit in excerpt["cited_by"]:
                if _in_section(unit, name) and unit not in cited.setdefault(excerpt["id"], []):
                    cited[excerpt["id"]].append(unit)
        cited = {identifier: units for identifier, units in cited.items() if units}
        if cited:
            lines += ["", "Evidence its units cite (fetch with `packet --evidence <id>`):", ""]
            lines += [f"- `{identifier}` ← {', '.join(units)}" for identifier, units in cited.items()]
        if section["glossary"]:
            lines += ["", "Glossary entries its units use: " + ", ".join(f"`{g}`" for g in section["glossary"])]
        lines.append("")
    if names is None:
        left_out = _document(packet)["not_served"]
        if left_out:
            lines += ["## Sections the packet does not serve", ""]
            lines += [f"- `{s['id']}` {s['heading']}: " + (s["reason"] or ("no content of its own" if s["eligible"]
                                                                          else f"role {s['role']}"))
                      for s in left_out]
            lines.append("")
    return tidy(lines)


def _evidence(packet: dict, names: list[str]) -> dict:
    evidence = packet["evidence"]
    known = {e["id"]: e for e in evidence["excerpts"]} | {e["id"]: e for e in evidence["settings"]}
    absent = [name for name in names if name not in known]
    if absent:
        raise ValueError(f"The packet has no evidence {', '.join(absent)}. A section view lists the IDs its units "
                         "cite; `excerpt` serves other line ranges of a snapshot file.")
    return {"repository": evidence["repository"], "commit": evidence["commit"],
            "evidence": [known[name] for name in dict.fromkeys(names)]}


def _glossary(packet: dict, terms: list[str]) -> dict:
    glossary = packet["glossary"]
    view = {"verified": glossary["verified"]}
    if not terms:
        # Entries first, then the candidates of each ambiguous term, then the terms that matched nothing.
        items = [{"entry": {name: e[name] for name in GLOSSARY_ROW}} for e in glossary["entries"]]
        items += [{"ambiguous": a} for a in glossary["ambiguous"]]
        items += [{"unmatched": glossary["unmatched"]}] if glossary["unmatched"] else []
        return {**view, "glossary": items}
    wanted = {term.casefold() for term in terms}

    def names(entry: dict) -> set[str]:
        return {str(entry.get(name, "")).casefold() for name in ("id", "anchor", "term")} | \
               {form.casefold() for form in entry.get("forms", [])}

    items = [{"entry": {**{k: v for k, v in e.items() if k != "occurrences"}, "occurrences": len(e["occurrences"])}}
             for e in glossary["entries"] if names(e) & wanted]
    items += [{"ambiguous": a} for a in glossary["ambiguous"] if a["term"].casefold() in wanted]
    if not items:
        raise ValueError(f"The glossary candidates have no entry for {', '.join(terms)}; `packet --glossary` lists "
                         "them. A term that is not a candidate must not be defined in the video.")
    return {**view, "glossary": items}


def view(packet: dict, *, section: str | list[str] | None = None, evidence: list[str] | None = None,
         glossary: list[str] | None = None, settings: bool = False, document: bool = False) -> dict:
    """Return a complete view of the packet: the index by default, or the selected content."""
    if document:
        return _document(packet)
    if section is not None:
        return _sections(packet, [section] if isinstance(section, str) else section)
    if evidence is not None:
        return _evidence(packet, evidence)
    if glossary is not None:
        return _glossary(packet, glossary)
    if settings:
        return {"settings": packet["evidence"]["settings"]}
    return _index(packet)
