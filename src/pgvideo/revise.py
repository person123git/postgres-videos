"""Apply a small patch to a harness input file and write the result as a new revision.

A repair changes a few values of a plan, storyboard, or review. Typing the whole
file again costs a model thousands of output tokens and can exceed its output
limit, so the harness writes only the changes: a short list of operations, each
naming a place by path. `revise` applies them to a copy and writes it under a new
filename. The source file is never changed, and nothing is written unless every
operation applies.

A path is keys joined by dots, with selectors in brackets after a list:
`[3]` one entry by position, `[*]` every entry, `[id=size-sets-slot]` the entries
whose key has that value, `[target~screen:*:0]` the entries whose key matches a
pattern (`*` any text, `?` one character), and `[=short-answer.1.s1]` the entries
equal to a value. A selector's value may contain dots. For example:

    claims[id=size-sets-slot].sources          one claim's source list
    claims[*].assessment.glossary              that field of every claim
    omissions[section=details]                 one omission entry
    findings[target~screen:*:0].verdict        that field of every screen heading's finding

Operations:

    {"op": "set", "path": P, "value": V}                 put V at P; the last key may be new
    {"op": "add", "path": P, "value": V}                 append V to the list at P
    {"op": "add", "path": P, "values": [V, ...]}         append several
    {"op": "remove", "path": P}                          delete the entries or keys at P
    {"op": "replace", "path": P, "find": A, "with": B}   replace text A by B in the strings at P

An operation that matches nothing is an error; nothing is guessed. The patch
file is a JSON or YAML list of operations, or an object with the list under `patch`.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from fnmatch import fnmatchcase
from pathlib import Path

from . import contracts
from .paths import project_directory
from .sources import write_atomic

OPS = ("set", "add", "remove", "replace")
# Directories pgvideo owns; a revision is the harness's own input and is written elsewhere.
OWNED = ("runs", "output")
_STEP = re.compile(r"\.?([^.\[\]]+)|\[([^\]]*)\]")
_INDEX = re.compile(r"-?\d+")


def _steps(path: str) -> list[tuple[str, str]]:
    """Split `claims[id=a.b].sources[*]` into ("key", name) and ("select", selector) steps."""
    steps, position = [], 0
    while position < len(path):
        match = _STEP.match(path, position)
        if not match:
            raise ValueError(f"The path '{path}' is malformed at character {position + 1}.")
        steps.append(("key", match.group(1)) if match.group(1) is not None else ("select", match.group(2)))
        position = match.end()
    if not steps:
        raise ValueError("An operation's path must not be empty.")
    return steps


def _children(node, step: tuple[str, str], path: str, *, last: bool = False) -> list[tuple]:
    """Return the (container, key) pairs one step names inside a node."""
    kind, name = step
    if kind == "key":
        if not isinstance(node, dict):
            raise ValueError(f"{path}: '{name}' is a key, but the value there is not an object.")
        return [(node, name)] if last or name in node else []
    if not isinstance(node, list):
        raise ValueError(f"{path}: [{name}] selects list entries, but the value there is not a list.")
    if name == "*":
        return [(node, index) for index in range(len(node))]
    if _INDEX.fullmatch(name):
        index = int(name) + (len(node) if int(name) < 0 else 0)
        return [(node, index)] if 0 <= index < len(node) else []
    # The first `=` or `~` separates the key from an exact value or a pattern.
    cut = min((position for position in (name.find("="), name.find("~")) if position >= 0), default=-1)
    if cut < 0:
        raise ValueError(f"{path}: [{name}] must be a position, *, key=value, key~pattern, or =value.")
    key, value = name[:cut], name[cut + 1:]
    same = (lambda found: str(found) == value) if name[cut] == "=" else (
        lambda found: fnmatchcase(str(found), value))
    if key:
        return [(node, index) for index, entry in enumerate(node)
                if isinstance(entry, dict) and key in entry and same(entry[key])]
    return [(node, index) for index, entry in enumerate(node)
            if not isinstance(entry, (dict, list)) and same(entry)]


def _targets(document, path: str) -> list[tuple]:
    """Every (container, key) a path names; only its last key may be absent."""
    steps = _steps(path)
    nodes = [document]
    for step in steps[:-1]:
        nodes = [container[key] for node in nodes for container, key in _children(node, step, path)]
    return [pair for node in nodes for pair in _children(node, steps[-1], path, last=True)]


def _apply(document, number: int, operation) -> dict:
    if not isinstance(operation, dict) or operation.get("op") not in OPS or not isinstance(operation.get("path"), str):
        raise ValueError(f"Operation {number} needs an `op` ({', '.join(OPS)}) and a `path`.")
    kind, path = operation["op"], operation["path"]
    targets = _targets(document, path)
    matched = len(targets)
    if kind == "set":
        if "value" not in operation:
            raise ValueError(f"Operation {number} (set {path}) needs a `value`.")
        for container, key in targets:
            container[key] = copy.deepcopy(operation["value"])
    elif kind == "add":
        if ("value" in operation) == ("values" in operation) or not isinstance(operation.get("values", []), list):
            raise ValueError(f"Operation {number} (add {path}) needs either a `value` or a list of `values`.")
        values = operation["values"] if "values" in operation else [operation["value"]]
        targets = [(container, key) for container, key in targets if isinstance(container, list) or key in container]
        matched = len(targets) if values else 0
        for container, key in targets:
            if not isinstance(container[key], list):
                raise ValueError(f"Operation {number} (add {path}): the value there is not a list.")
            container[key].extend(copy.deepcopy(values))
    elif kind == "remove":
        targets = [(container, key) for container, key in targets if isinstance(container, list) or key in container]
        matched = len(targets)
        # Later list positions first, so the earlier ones still name the same entries.
        for container, key in sorted(targets, key=lambda pair: pair[1] if isinstance(pair[1], int) else 0,
                                     reverse=True):
            del container[key]
    else:
        find, replacement = operation.get("find"), operation.get("with")
        if not isinstance(find, str) or not find or not isinstance(replacement, str):
            raise ValueError(f"Operation {number} (replace {path}) needs the strings `find` and `with`.")
        matched = 0
        for container, key in targets:
            text = container.get(key) if isinstance(container, dict) else container[key]
            if not isinstance(text, str):
                raise ValueError(f"Operation {number} (replace {path}): the value there is not a string.")
            if find in text:
                container[key] = text.replace(find, replacement)
                matched += 1
    if not matched:
        raise ValueError(f"Operation {number} ({kind} {path}) matches nothing, so nothing was written. Check the "
                         "path against the file; an ID in a selector is copied exactly.")
    return {"op": kind, "path": path, "matched": matched}


def apply(document, operations: list) -> list[dict]:
    """Apply the operations in order to the document, in place; return what each one matched."""
    return [_apply(document, number, operation) for number, operation in enumerate(operations, 1)]


def revise(root: Path, source: Path, patch: Path, out: Path) -> dict:
    """Write `out` as `source` with the patch applied; return the new file, its SHA-256, and the changes."""
    file = contracts.project_file(root, source, label="Source file")
    document = contracts.parse(file.read_bytes(), file.relative_to(root).as_posix())
    patch_file = contracts.project_file(root, patch, label="Patch file")
    where = patch_file.relative_to(root).as_posix()
    loaded = contracts.parse(patch_file.read_bytes(), where)
    operations = loaded.get("patch") if isinstance(loaded, dict) else loaded
    if not isinstance(operations, list) or not operations:
        raise ValueError(f"{where} must hold a non-empty list of operations, or an object with the list under "
                         "`patch`.")
    candidate = out if out.is_absolute() else root / out
    target = project_directory(root, candidate.parent, label="Revision") / candidate.name
    relative = target.relative_to(root)
    if relative.parts[0] in OWNED:
        raise ValueError(f"pgvideo owns {relative.parts[0]}/; write the revision under .scratch/<id>/ and import it.")
    if target.suffix != ".json":
        raise ValueError(f"The revision {out} must be a .json file.")
    if target.exists() or target.is_symlink():
        raise ValueError(f"{relative.as_posix()} already exists. Use a new filename for each revision, such as "
                         "plan.v2.json.")
    changes = apply(document, operations)
    body = (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    write_atomic(root, relative, body, label="Revision")
    return {"file": relative.as_posix(), "sha256": hashlib.sha256(body).hexdigest(), "changes": changes}
