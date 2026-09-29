"""Validate document locations and retrieve verified files from GitHub."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode, urlsplit
from urllib.request import Request, urlopen

from .paths import project_directory

REPOSITORY = "person123git/postgres-llm-wiki"
# GitHub's mirror of git.postgresql.org, which rate-limits automated downloads.
POSTGRES_REPOSITORY = "postgres/postgres"
DEFAULT_REF = "master"
API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
API_ROOT = f"{API}/repos/{REPOSITORY}/contents"
GITHUB_HOSTS = {"api.github.com", "raw.githubusercontent.com"}
COMMIT = re.compile(r"[0-9a-f]{40}")
REGULAR_FILE_MODES = {"100644", "100755"}
MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024
ATTEMPTS = 3


class SourceError(ValueError):
    """An invalid or unavailable document selection."""


@dataclass(frozen=True)
class Document:
    path: str
    ref: str

    @property
    def url(self) -> str:
        return blob_url(REPOSITORY, self.ref, self.path)


def blob_url(repository: str, ref: str, path: str, lines: tuple[int, int] | None = None) -> str:
    url = f"https://github.com/{repository}/blob/{quote(ref, safe='/')}/{quote(path, safe='/')}"
    if lines:
        url += f"#L{lines[0]}" if lines[0] == lines[1] else f"#L{lines[0]}-L{lines[1]}"
    return url


def git_blob_sha(data: bytes) -> str:
    """Return Git's SHA-1 object ID for a file's bytes."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


def _check_path(path: str) -> str:
    if not path or path.startswith("/") or "\\" in path:
        raise SourceError("Document must be one repository-relative file path.")
    if any(part in ("", ".", "..") for part in path.split("/")):
        raise SourceError("Document path must not contain empty, '.' or '..' segments.")
    if any(character in path for character in "*?[]"):
        raise SourceError("Document must name one file; globs are not supported.")
    if any(ord(character) < 32 for character in path):
        raise SourceError("Document path contains a control character.")
    return path


def _check_ref(ref: str) -> str:
    if not ref or ref.startswith("/") or ref.endswith("/"):
        raise SourceError("Repository ref must be a nonempty branch, tag, or commit.")
    if any(part in ("", ".", "..") for part in ref.split("/")):
        raise SourceError("Repository ref contains an invalid path segment.")
    if any(character in ref for character in "*?[]\\") or any(
        ord(character) < 32 for character in ref
    ):
        raise SourceError("Repository ref contains an invalid character.")
    return ref


def _http_get(url: str, *, accept: str | None = None, timeout: float = 30) -> bytes | None:
    """Fetch one GitHub URL; return None when GitHub reports that it does not exist."""
    request = Request(url, headers={"User-Agent": "pgvideo/0.1"})
    if accept:
        request.add_header("Accept", accept)
    token = os.environ.get("GITHUB_TOKEN")
    if token and urlsplit(url).hostname in GITHUB_HOSTS:
        # Unredirected, so a redirect to another host does not receive the token.
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                data = response.read(MAX_DOWNLOAD_BYTES + 1)
            if len(data) > MAX_DOWNLOAD_BYTES:
                raise SourceError(f"GitHub response exceeds {MAX_DOWNLOAD_BYTES} bytes: {url}")
            return data
        except HTTPError as error:
            if error.code in (404, 422):
                return None
            if error.code in (401, 403):
                raise SourceError(
                    f"GitHub denied {url} (HTTP {error.code}); check GITHUB_TOKEN or API rate limits."
                ) from error
            if (error.code != 429 and error.code < 500) or attempt == ATTEMPTS:
                raise SourceError(f"GitHub request failed (HTTP {error.code}): {url}") from error
        except (URLError, TimeoutError, ConnectionError) as error:
            if attempt == ATTEMPTS:
                raise SourceError(f"Cannot reach GitHub for {url}: {error}.") from error
        time.sleep(attempt)
    raise AssertionError("unreachable")


def _github_json(url: str, *, timeout: float = 30) -> dict | list | None:
    data = _http_get(url, accept="application/vnd.github+json", timeout=timeout)
    if data is None:
        return None
    try:
        return json.loads(data)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise SourceError(f"GitHub returned an unreadable response for {url}.") from error


def _github_contents(path: str, ref: str) -> dict | list | None:
    return _github_json(f"{API_ROOT}/{quote(path, safe='/')}?{urlencode({'ref': ref})}", timeout=15)


def _validate_file(path: str, ref: str) -> None:
    result = _github_contents(path, ref)
    if result is None:
        raise SourceError(f"Document '{path}' was not found at ref '{ref}'.")
    if isinstance(result, list) or result.get("type") == "dir":
        raise SourceError(f"Document '{path}' is a directory; select one Markdown file.")
    if result.get("type") != "file" or result.get("path") != path:
        raise SourceError(f"Document '{path}' is not a regular file at ref '{ref}'.")
    if not path.lower().endswith(".md"):
        raise SourceError(f"Document '{path}' is not a Markdown (.md) file.")


def resolve_document(value: str, explicit_ref: str | None = None) -> Document:
    """Resolve one relative path or GitHub blob URL and verify it exists."""
    if explicit_ref is not None:
        _check_ref(explicit_ref)
    if "://" not in value:
        path = _check_path(value)
        ref = explicit_ref or DEFAULT_REF
        _validate_file(path, ref)
        return Document(path, ref)

    url = urlsplit(value)
    if url.scheme != "https" or url.netloc.lower() != "github.com":
        raise SourceError("Document URL must be an HTTPS GitHub blob URL for the configured repository.")
    pieces = url.path.strip("/").split("/")
    if len(pieces) < 5 or "/".join(pieces[:2]).lower() != REPOSITORY.lower():
        raise SourceError(f"Document URL must belong to github.com/{REPOSITORY}.")
    if pieces[2] != "blob":
        raise SourceError("Document URL must use the GitHub /blob/<ref>/<path> form.")

    remainder = [unquote(piece) for piece in pieces[3:]]
    if any(character in piece for piece in remainder for character in "*?[]"):
        raise SourceError("Document must name one file; globs are not supported.")
    matches: list[Document] = []
    for boundary in range(1, len(remainder)):
        ref = "/".join(remainder[:boundary])
        path = "/".join(remainder[boundary:])
        try:
            _check_ref(ref)
            _check_path(path)
        except SourceError:
            continue
        result = _github_contents(path, ref)
        if isinstance(result, dict) and result.get("type") == "file" and result.get("path") == path:
            matches.append(Document(path, ref))
        elif isinstance(result, list) or (isinstance(result, dict) and result.get("type") == "dir"):
            if boundary == 1:
                raise SourceError(f"Document '{path}' is a directory; select one Markdown file.")

    if not matches:
        raise SourceError("Document from GitHub blob URL was not found at any valid ref/path split.")
    if len(matches) > 1:
        raise SourceError("GitHub blob URL is ambiguous between refs; use a repository-relative path and --ref.")
    document = matches[0]
    if explicit_ref is not None and explicit_ref != document.ref:
        raise SourceError(f"--ref '{explicit_ref}' conflicts with URL ref '{document.ref}'.")
    if not document.path.lower().endswith(".md"):
        raise SourceError(f"Document '{document.path}' is not a Markdown (.md) file.")
    return document


def resolve_commit(repository: str, ref: str) -> str:
    """Resolve a branch, tag, or commit to the full commit SHA it names now."""
    _check_ref(ref)
    data = _http_get(
        f"{API}/repos/{repository}/commits/{quote(ref, safe='')}", accept="application/vnd.github.sha"
    )
    if data is None:
        raise SourceError(f"Ref '{ref}' does not name a commit in {repository}.")
    commit = data.decode("ascii", errors="replace").strip()
    if not COMMIT.fullmatch(commit):
        raise SourceError(f"GitHub returned an invalid commit for ref '{ref}' in {repository}.")
    return commit


def write_atomic(root: Path, relative: Path, data: bytes, *, label: str) -> Path:
    """Write bytes under a project directory checked for escapes, replacing any old file."""
    parent = project_directory(root, relative.parent, label=label)
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / relative.name
    descriptor, temporary = tempfile.mkstemp(dir=parent, prefix=f".{relative.name[:40]}.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return target


class CommitFiles:
    """One commit of a GitHub repository, with downloads verified and cached by commit and path.

    Cached files live under cache/sources/<owner>/<repository>/<commit>/. Each file
    is checked against the Git blob ID in the commit's tree whenever it is read, so
    a corrupt or tampered cache entry is downloaded again.
    """

    def __init__(self, root: Path, repository: str, commit: str, *, info: dict, tree: dict):
        self.root = root
        self.repository = repository
        self.commit = commit
        self.info = info
        self.tree = tree

    @classmethod
    def open(cls, root: Path, repository: str, commit: str) -> CommitFiles | None:
        """Load a commit's metadata and tree; return None if the repository lacks the commit."""
        if not COMMIT.fullmatch(commit):
            raise SourceError(f"'{commit}' is not a full 40-character commit SHA.")
        cache = Path("cache/sources", *repository.split("/"), commit)
        info = cls._cached_json(root, cache / "commit.json")
        if info is None:
            data = _github_json(f"{API}/repos/{repository}/git/commits/{commit}")
            if data is None:
                return None
            if not isinstance(data, dict) or data.get("sha") != commit or not COMMIT.fullmatch(
                str(data.get("tree", {}).get("sha", ""))
            ):
                raise SourceError(f"GitHub returned unexpected metadata for {repository}@{commit}.")
            committer = data.get("committer") or {}
            info = {"commit": commit, "tree": data["tree"]["sha"], "committed_at": committer.get("date")}
            write_atomic(root, cache / "commit.json", _json_bytes(info), label="Source cache")
        tree = cls._cached_json(root, cache / "tree.json")
        if tree is None:
            data = _github_json(f"{API}/repos/{repository}/git/trees/{info['tree']}?recursive=1", timeout=120)
            if not isinstance(data, dict) or data.get("sha") != info["tree"] or not isinstance(
                data.get("tree"), list
            ):
                raise SourceError(f"GitHub returned an unreadable tree for {repository}@{commit}.")
            if data.get("truncated"):
                raise SourceError(f"GitHub truncated the file list for {repository}@{commit}.")
            tree = {
                "commit": commit,
                "entries": {
                    entry["path"]: [entry["mode"], entry["type"], entry["sha"], entry.get("size")]
                    for entry in data["tree"]
                },
            }
            write_atomic(root, cache / "tree.json", _json_bytes(tree), label="Source cache")
        return cls(root, repository, commit, info=info, tree=tree["entries"])

    @staticmethod
    def _cached_json(root: Path, relative: Path) -> dict | None:
        path = project_directory(root, relative.parent, label="Source cache") / relative.name
        if not path.is_file() or path.is_symlink():
            return None
        try:
            return json.loads(path.read_bytes())
        except (json.JSONDecodeError, UnicodeError):
            return None

    def kind(self, path: str) -> str | None:
        """Return 'file', 'directory', 'other', or None for a path in this commit."""
        entry = self.tree.get(path)
        if entry is None:
            return None
        mode, kind = entry[0], entry[1]
        if kind == "blob" and mode in REGULAR_FILE_MODES:
            return "file"
        return "directory" if kind == "tree" else "other"

    def blob_sha(self, path: str) -> str:
        if self.kind(path) != "file":
            raise SourceError(f"'{path}' is not a regular file in {self.repository}@{self.commit}.")
        return self.tree[path][2]

    def url(self, path: str, lines: tuple[int, int] | None = None) -> str:
        return blob_url(self.repository, self.commit, path, lines)

    def raw_url(self, path: str) -> str:
        return f"{RAW}/{self.repository}/{self.commit}/{quote(path, safe='/')}"

    def read(self, path: str, *, refresh: bool = False) -> bytes:
        """Return a regular file's bytes, downloading it on a cache miss or whenever `refresh` is set."""
        _check_path(path)
        expected = self.blob_sha(path)
        relative = Path("cache/sources", *self.repository.split("/"), self.commit, "files", *path.split("/"))
        cached = project_directory(self.root, relative.parent, label="Source cache") / relative.name
        if not refresh and cached.is_file() and not cached.is_symlink():
            data = cached.read_bytes()
            if git_blob_sha(data) == expected:
                return data
        data = _http_get(self.raw_url(path), timeout=60)
        if data is None:
            raise SourceError(f"GitHub did not serve '{path}' from {self.repository}@{self.commit}.")
        if git_blob_sha(data) != expected:
            raise SourceError(
                f"Downloaded '{path}' does not match its Git blob {expected} in {self.repository}@{self.commit}."
            )
        write_atomic(self.root, relative, data, label="Source cache")
        return data


def _json_bytes(data: dict) -> bytes:
    return (json.dumps(data, indent=1, sort_keys=True) + "\n").encode("utf-8")
