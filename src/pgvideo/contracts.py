"""Load harness-authored files and validate them against the versioned JSON Schemas in schemas/.

A schema says an artifact is well formed; it does not make its content correct.
pgvideo's own checks resolve every ID, compare quotes and values with the
snapshot, and assign every status after the schema passes.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from .markdown import MarkdownError, _FrontMatterLoader
from .paths import project_directory

MAX_ERRORS = 25


def schema(root: Path, name: str) -> dict:
    path = root / "schemas" / f"{name}.schema.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"The JSON Schema schemas/{name}.schema.json is missing.")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(loaded)
    return loaded


def _registry(root: Path) -> Registry:
    """Every schema in schemas/ under its $id; a reference outside them fails instead of being fetched."""
    resources = []
    for path in sorted((root / "schemas").glob("*.schema.json")):
        loaded = schema(root, path.name.removesuffix(".schema.json"))
        resources.append((loaded["$id"], Resource.from_contents(loaded, default_specification=DRAFT202012)))
    return Registry().with_resources(resources)


def errors(root: Path, name: str, value) -> list[str]:
    """Return schema violations as `path: message` lines, at most MAX_ERRORS of them.

    Violations of one rule at the same place in different list entries are one line: the
    path with `*` for the entry, how many places break the rule, and the first as an example.
    A rule's `description` in the schema follows its message.
    """
    validator = Draft202012Validator(schema(root, name), registry=_registry(root))
    found = sorted(validator.iter_errors(value), key=lambda error: [str(p) for p in error.absolute_path])
    groups: dict[tuple, list] = {}
    for error in found:
        rule = "/".join("*" if isinstance(part, int) else str(part) for part in error.absolute_path)
        groups.setdefault((rule, error.validator, json.dumps(error.validator_value, sort_keys=True, default=str)),
                          []).append(error)
    lines = []
    for (rule, _validator, _value), same in list(groups.items())[:MAX_ERRORS]:
        first = same[0]
        path = "/".join(str(part) for part in first.absolute_path) or "(top level)"
        note = first.schema.get("description") if isinstance(first.schema, dict) else None
        where = path if len(same) == 1 else f"{rule} ({len(same)} places, first {path})"
        lines.append(f"{where}: {first.message}" + (f" ({note})" if note else ""))
    if len(groups) > MAX_ERRORS:
        lines.append(f"… and {len(groups) - MAX_ERRORS} more rules")
    return lines


def require(root: Path, name: str, value, where: str) -> None:
    if problems := errors(root, name, value):
        raise ValueError(f"{where} does not match schemas/{name}.schema.json:\n  " + "\n  ".join(problems))


def project_file(root: Path, path: Path, *, label: str) -> Path:
    """Resolve a file argument against the project root and reject paths or symlinks that leave it."""
    candidate = path if path.is_absolute() else root / path
    parent = project_directory(root, candidate.parent, label=label)
    resolved = parent / candidate.name
    if resolved.is_symlink() or not resolved.is_file():
        raise ValueError(f"{label} {path} must be a regular file inside the project.")
    return resolved


def parse(data: bytes, where: str):
    """Parse JSON, or YAML without aliases."""
    try:
        text = data.decode("utf-8").removeprefix("﻿")
    except UnicodeDecodeError as error:
        raise ValueError(f"{where} is not UTF-8.") from error
    try:
        return json.loads(text) if text.lstrip().startswith("{") else yaml.load(text, Loader=_FrontMatterLoader)
    except MarkdownError as error:
        raise ValueError(f"{where} must not use YAML aliases.") from error
    except (json.JSONDecodeError, yaml.YAMLError) as error:
        raise ValueError(f"{where} is not valid JSON or YAML: {error}") from error
