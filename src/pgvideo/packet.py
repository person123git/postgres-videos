"""Serve the evidence packet in bounded pieces.

A packet for a long page is far larger than a model's context window, so a
harness never opens evidence-packet.json itself. `view` returns one piece at a
time: the index (the request, the document, and one row per section), one
section with the IDs of the evidence and glossary entries its units use,
evidence excerpts by ID, glossary entries, or the configuration facts. Every
piece is cut into pages of at most MAX_BYTES of compact JSON; a page always
holds at least one item, so a single item larger than that is still served.

Nothing here selects or summarizes: text is returned exactly as the packet holds
it, and only fields that do not fit a view (a glossary entry's full occurrence
list, an indexed section's blocks) are replaced by counts.
"""

from __future__ import annotations

import json

MAX_BYTES = 24_000
# Fields of the packet that every index page repeats; together they are a few kilobytes.
HEADER = ("notice", "lexical_notice", "document", "request", "speech", "review_state", "digests")
INDEX_ROW = ("id", "heading", "level", "parent", "role", "eligible", "caveat", "reason", "words")
GLOSSARY_ROW = ("id", "term", "tier", "result", "allowed_in_narration", "definition", "version")


def _size(value) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def _pages(items: list, budget: int) -> list[list]:
    """Split items, in order, into pages whose compact JSON fits the budget; an oversized item gets its own page."""
    pages, current, used = [], [], 0
    for item in items:
        size = _size(item) + 1
        if current and used + size > budget:
            pages.append(current)
            current, used = [], 0
        current.append(item)
        used += size
    return pages + [current] if current or not pages else pages


def _paged(view: dict, key: str, items: list, page: int) -> dict:
    pages = _pages(items, max(MAX_BYTES - _size(view), MAX_BYTES // 4))
    if not 1 <= page <= len(pages):
        raise ValueError(f"--page must be between 1 and {len(pages)} for this view.")
    return {**view, key: pages[page - 1], "page": page, "pages": len(pages)}


def _in_section(unit: str, section: str) -> bool:
    return unit == section or unit.startswith(section + ".")


def _index(packet: dict, page: int) -> dict:
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
    return _paged(view, "sections", rows, page)


def _section(packet: dict, name: str, page: int) -> dict:
    section = next((s for s in packet["sections"] if s["id"] == name), None)
    if section is None:
        raise ValueError(f"The packet has no section '{name}'; list the section IDs with `packet` and no selector.")
    view = {name_: value for name_, value in section.items() if name_ != "blocks"}
    view["evidence"] = sorted(e["id"] for e in packet["evidence"]["excerpts"]
                              if any(_in_section(unit, name) for unit in e["cited_by"]))
    view["glossary"] = sorted(e["id"] for e in packet["glossary"]["entries"]
                              if any(_in_section(unit, name) for unit in e["occurrences"]))
    return _paged({"section": view}, "blocks", section["blocks"], page)


def _evidence(packet: dict, names: list[str], page: int) -> dict:
    evidence = packet["evidence"]
    known = {e["id"]: e for e in evidence["excerpts"]} | {e["id"]: e for e in evidence["settings"]}
    absent = [name for name in names if name not in known]
    if absent:
        raise ValueError(f"The packet has no evidence {', '.join(absent)}. A section view lists the IDs its units "
                         "cite; `excerpt` serves other line ranges of a snapshot file.")
    return _paged({"repository": evidence["repository"], "commit": evidence["commit"]}, "evidence",
                  [known[name] for name in dict.fromkeys(names)], page)


def _glossary(packet: dict, terms: list[str], page: int) -> dict:
    glossary = packet["glossary"]
    view = {"verified": glossary["verified"]}
    if not terms:
        # Entries first, then the candidates of each ambiguous term, then the terms that matched nothing.
        items = [{"entry": {name: e[name] for name in GLOSSARY_ROW}} for e in glossary["entries"]]
        items += [{"ambiguous": a} for a in glossary["ambiguous"]]
        items += [{"unmatched": glossary["unmatched"]}] if glossary["unmatched"] else []
        return _paged(view, "glossary", items, page)
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
    return _paged(view, "glossary", items, page)


def view(packet: dict, *, section: str | None = None, evidence: list[str] | None = None,
         glossary: list[str] | None = None, settings: bool = False, page: int = 1) -> dict:
    """Return one bounded page of the packet: the index by default, or the piece one selector names."""
    if section is not None:
        return _section(packet, section, page)
    if evidence is not None:
        return _evidence(packet, evidence, page)
    if glossary is not None:
        return _glossary(packet, glossary, page)
    if settings:
        return _paged({}, "settings", packet["evidence"]["settings"], page)
    return _index(packet, page)
