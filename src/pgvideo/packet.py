"""Serve complete views of the evidence packet.

`view` returns the index (the request, the document, and one row per section),
one section with the IDs of the evidence and glossary entries its units use,
evidence excerpts by ID, glossary entries, or the configuration facts.

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


def view(packet: dict, *, section: str | None = None, evidence: list[str] | None = None,
         glossary: list[str] | None = None, settings: bool = False) -> dict:
    """Return a complete view of the packet: the index by default, or the selected content."""
    if section is not None:
        return _section(packet, section)
    if evidence is not None:
        return _evidence(packet, evidence)
    if glossary is not None:
        return _glossary(packet, glossary)
    if settings:
        return {"settings": packet["evidence"]["settings"]}
    return _index(packet)
