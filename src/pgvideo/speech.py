"""Turn a script sentence's display text into the text Kokoro speaks (Step 7).

The script keeps two texts for every narrated sentence. Display text is the
canonical spelling that the screen and the captions show, with inline code in
backticks. TTS text is what Kokoro reads: identifiers are split into words,
acronyms are spelled or given a spoken form, operators become words, and
nothing is left that a speech model would read as punctuation noise. The rules
live in pronunciation/en.yaml, whose SHA-256 the storyboard records.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml

from .markdown import MarkdownError, _FrontMatterLoader

DICTIONARY = Path("pronunciation") / "en.yaml"
MAX_DICTIONARY_BYTES = 256 * 1024
SECTIONS = ("terms", "parts", "abbreviations", "units")

CODE_SPAN = re.compile(r"(`+)(.+?)\1(?!`)")
VOWELS = set("aeiouyAEIOUY")
# Pieces of an identifier: acronym runs before a capitalized word, words, capitals, and digits.
PIECE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
# Tokens of inline code.
CODE_TOKEN = re.compile(
    r"\"[^\"]*\"|'[^']*'|<[A-Za-z][\w -]*>|\\[0-9a-z]|\.\.\.|->|::|==|!=|<>|<=|>=|&&|\|\||"
    r"\d[\d,]*(?:\.\d+)?|[A-Za-z_][\w$]*|\$\d+|\S")
OPERATORS = {
    "->": "arrow", "::": "cast to", "==": "equals", "!=": "is not equal to", "<>": "is not equal to",
    "<=": "is at most", ">=": "is at least", "&&": "and", "||": "or", "=": "equals", "<": "is less than",
    ">": "is greater than", "+": "plus", "-": "minus", "/": "divided by", "%": "modulo", "&": "and", "|": "or",
    "!": "not", "~": "tilde", "^": "caret", "#": "hash", "@": "at", "?": "question mark",
}
# Two-letter capital words that are read as words, as in SQL: `IS NOT NULL`, `ON CONFLICT`.
CONNECTIVES = {"ON", "OR", "IN", "IS", "AS", "BY", "IF", "OF", "TO", "AT", "DO", "NO"}
ESCAPES = {"\\0": "backslash zero", "\\n": "backslash N", "\\t": "backslash T", "\\r": "backslash R"}
PROSE_SYMBOLS = {"&": " and ", "×": " times ", "→": " to ", "←": " from ", "≈": " about ", "≤": " at most ",
                 "≥": " at least ", "±": " plus or minus ", "%": " percent", "~": " about ", "…": "."}
IDENTIFIER = re.compile(
    r"(?<![\w$.])(?:[A-Za-z_][\w$]*_[\w$]*|[a-z]+[A-Z][\w$]*|[A-Z][a-z0-9]+[A-Z][\w$]*)(?:\.[A-Za-z_][\w$]*)*(?:\(\))?")
WORD = re.compile(r"[A-Za-z][A-Za-z0-9/+-]*[A-Za-z0-9+]|[A-Za-z]")
# Characters that must not reach Kokoro: they are either read aloud as symbols or dropped unpredictably.
UNSPEAKABLE = re.compile(r"[`_*\\{}\[\]<>|#$@^~=]|https?://|www\.")


class PronunciationError(ValueError):
    """The pronunciation dictionary is missing or invalid."""


class Pronunciation:
    """The spoken forms of terms, identifier pieces, abbreviations, and units."""

    def __init__(self, data: dict, *, path: str = str(DICTIONARY), sha256: str | None = None,
                 words: frozenset[str] = frozenset()):
        if not isinstance(data, dict) or data.get("schema") != 1:
            raise PronunciationError(f"{path} must be a mapping with `schema: 1`.")
        unknown = set(data) - {"schema", "language", *SECTIONS}
        if unknown:
            raise PronunciationError(f"{path} has unknown keys: {', '.join(sorted(unknown))}.")
        for section in SECTIONS:
            table = data.get(section) or {}
            if not isinstance(table, dict) or not all(
                    isinstance(key, str) and isinstance(value, str) and key and value.strip()
                    for key, value in table.items()):
                raise PronunciationError(f"{path}: `{section}` must map nonempty strings to nonempty strings.")
            for key, value in table.items():
                if UNSPEAKABLE.search(value):
                    raise PronunciationError(f"{path}: the spoken form of {key!r} contains a symbol Kokoro would "
                                             "read aloud or drop.")
        self.path, self.sha256, self.language = path, sha256, data.get("language")
        # Kokoro's English lexicon: a three-letter capital piece that is a word there, such as HAS, is read as one.
        self.words = words
        self.terms: dict[str, str] = dict(data.get("terms") or {})
        self.parts = {key.lower(): value for key, value in (data.get("parts") or {}).items()}
        self.abbreviations: dict[str, str] = dict(data.get("abbreviations") or {})
        self.units: dict[str, str] = dict(data.get("units") or {})
        # Whole-term replacements in prose, longest first so `JSONB` wins over `JSON`.
        keys = sorted(self.terms, key=len, reverse=True)
        self._terms = re.compile(r"(?<![\w$/.-])(" + "|".join(map(re.escape, keys)) + r")(s?)(?![\w$/])") \
            if keys else None
        abbreviations = sorted(self.abbreviations, key=len, reverse=True)
        self._abbreviations = re.compile(
            r"(?<![\w.])(" + "|".join(map(re.escape, abbreviations)) + r")(?=[\s,;:)]|$)") if abbreviations else None
        units = sorted(self.units, key=len, reverse=True)
        self._units = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s?(" + "|".join(map(re.escape, units))
                                 + r")(?![\w/])") if units else None

    @classmethod
    def load(cls, root: Path) -> "Pronunciation":
        path = root / DICTIONARY
        if path.is_symlink() or not path.is_file():
            raise PronunciationError(f"The pronunciation dictionary {DICTIONARY} is missing.")
        data = path.read_bytes()
        if len(data) > MAX_DICTIONARY_BYTES:
            raise PronunciationError(f"{DICTIONARY} is larger than {MAX_DICTIONARY_BYTES} bytes.")
        try:
            loaded = yaml.load(data.decode("utf-8"), Loader=_FrontMatterLoader)
        except MarkdownError as error:
            raise PronunciationError(f"{DICTIONARY} must not use YAML aliases.") from error
        except (yaml.YAMLError, UnicodeDecodeError) as error:
            raise PronunciationError(f"{DICTIONARY} is not valid UTF-8 YAML: {error}") from error
        from .glossary import english_words

        try:
            words = english_words()
        except ValueError as error:
            raise PronunciationError(str(error)) from error
        return cls(loaded, path=DICTIONARY.as_posix(), sha256=hashlib.sha256(data).hexdigest(), words=words)

    # Spoken text ---------------------------------------------------------------------------------

    def speak(self, display: str) -> str:
        """Return the TTS text for display text with inline code in backticks."""
        pieces, last = [], 0
        for match in CODE_SPAN.finditer(display):
            pieces.append(self._prose(display[last:match.start()]))
            pieces.append(" " + self.code(match.group(2).strip()) + " ")
            last = match.end()
        pieces.append(self._prose(display[last:]))
        return _tidy("".join(pieces))

    def _prose(self, text: str) -> str:
        if self._abbreviations:
            text = self._abbreviations.sub(lambda m: self.abbreviations[m.group(1)], text)
        if self._units:
            text = self._units.sub(lambda m: f"{m.group(1)} {self._unit(m.group(1), m.group(2))}", text)
        # Identifiers written without backticks, such as pg_stat_activity in a heading.
        text = IDENTIFIER.sub(lambda m: " " + self.code(m.group(0)) + " ", text)
        if self._terms:
            text = self._terms.sub(lambda m: self._term(m.group(1), m.group(2)), text)
        # "parser/planner/executor" reads as a list; "I/O" was handled as a term.
        text = re.sub(r"(?<=[A-Za-z])/(?=[A-Za-z])", ", ", text)
        for symbol, spoken in PROSE_SYMBOLS.items():
            text = text.replace(symbol, spoken)
        text = WORD.sub(lambda m: self._capitals(m.group(0)), text)
        return UNSPEAKABLE.sub(" ", text)

    def _unit(self, number: str, unit: str) -> str:
        spoken = self.units[unit]
        return spoken.removesuffix("s") if number == "1" and spoken.endswith("s") else spoken

    def _term(self, term: str, plural: str) -> str:
        return self.terms[term] + ("s" if plural else "")

    def _capitals(self, word: str) -> str:
        """Speak an all-capital word that no term covers: spell short ones, read words and SQL keywords as words."""
        if not (word.isupper() and word.isalpha() and len(word) > 1):
            return word
        if len(word) <= 3 and not self._word(word):
            return " ".join(word)
        return word.lower() if set(word) & VOWELS else " ".join(word)

    def _word(self, capitals: str) -> bool:
        """Whether a short capital piece is read as a word: a two-letter connective or a three-letter word."""
        if len(capitals) == 2:
            return capitals in CONNECTIVES
        return len(capitals) == 3 and bool(set(capitals) & VOWELS) and capitals.lower() in self.words

    def code(self, code: str) -> str:
        """Speak one inline code span: an identifier, a call, a path, an expression, or a literal."""
        if code in self.terms:
            return self.terms[code]
        if "/" in code and " " not in code and not re.search(r"[*+=<>()]", code):
            return " slash ".join(self._path_part(part) for part in code.split("/") if part)
        tokens = CODE_TOKEN.findall(code)
        words: list[str] = []
        depth: list[bool] = []  # whether each open parenthesis belongs to a call
        for index, token in enumerate(tokens):
            before = tokens[index - 1] if index else None
            after = tokens[index + 1] if index + 1 < len(tokens) else None
            if token[0] in "\"'":
                inner = token[1:-1].replace("...", " ").strip()
                words.append(self._prose(inner) if inner else "empty string")
            elif token.startswith("<") and token.endswith(">") and len(token) > 2:
                # A placeholder such as `pg_<subscription-oid>` names what goes there.
                words.append(" ".join(self.identifier(part) for part in re.split(r"[\s-]+", token[1:-1]) if part))
            elif token in ESCAPES:
                words.append(ESCAPES[token])
            elif re.fullmatch(r"\d[\d,]*(?:\.\d+)?", token):
                unit = after if after in self.units else None
                words.append(token.replace(",", "") + (f" {self._unit(token, unit)}" if unit else ""))
            elif re.fullmatch(r"[A-Za-z_][\w$]*|\$\d+", token):
                if before and re.fullmatch(r"\d[\d,]*(?:\.\d+)?", before) and token in self.units:
                    continue
                words.append(self.identifier(token))
            elif token == "(":
                call = bool(before and re.fullmatch(r"[A-Za-z_][\w$]*", before))
                depth.append(call)
                if after == ")":
                    continue
                words.append("of" if call else ",")
            elif token == ")":
                call = depth.pop() if depth else False
                # A call's arguments end without a pause; a grouping ends like a clause.
                if before != "(" and not call:
                    words.append(",")
            elif token == "*":
                if before in (None, "(", ",") and after in (None, ")", ","):
                    words.append("star")
                elif before in (None, "(", ",", "=", "*"):
                    continue  # a pointer dereference
                else:
                    words.append("times")
            elif token == ".":
                words.append("dot")
            elif token == "[":
                words.append("at index")
            elif token in ("]", ";", "{", "}", "...", "`"):
                continue
            elif token == ",":
                words.append(",")
            elif token == ":":
                words.append(":")
            elif token == "-" and (before is None or before in OPERATORS or before in ("(", ",", "=")):
                words.append("minus")
            elif token in OPERATORS:
                words.append(OPERATORS[token])
        return _tidy(" ".join(words).replace(" ,", ",").replace(" :", ":"))

    def _path_part(self, part: str) -> str:
        stem, dot, extension = part.rpartition(".")
        if dot and stem and extension.isalnum():
            return f"{self.identifier(stem)} dot {self._letters(extension)}"
        return self.identifier(part)

    def _letters(self, extension: str) -> str:
        spoken = self.parts.get(extension.lower())
        if spoken:
            return spoken
        return " ".join(extension.upper()) if len(extension) <= 2 or not set(extension) & VOWELS else extension

    def identifier(self, name: str) -> str:
        """Speak an identifier: split snake_case and CamelCase, then speak each piece."""
        name = name.removesuffix("()")
        if name in self.terms:
            return self.terms[name]
        words = []
        for chunk in re.split(r"[_$.]+", name):
            if not chunk:
                continue
            if chunk in self.terms:
                words.append(self.terms[chunk])
                continue
            if chunk.lower() in self.parts:
                words.append(self.parts[chunk.lower()])
                continue
            for piece in PIECE.findall(chunk):
                words.append(self._piece(piece))
        return " ".join(words)

    def _piece(self, piece: str) -> str:
        lower = piece.lower()
        if lower in self.parts:
            return self.parts[lower]
        if piece.isdigit():
            return piece
        if piece.isupper() and piece in self.terms:
            return self.terms[piece]
        if not set(piece) & VOWELS or (piece.isupper() and len(piece) <= 2):
            return " ".join(piece.upper())
        if piece.isupper() and len(piece) <= 3 and not self._word(piece):
            return " ".join(piece)
        return lower if piece.isupper() else piece


def unspeakable(text: str) -> list[str]:
    """Return the characters or URL fragments in TTS text that Kokoro should never receive."""
    return sorted({match.group(0) for match in UNSPEAKABLE.finditer(text)})


def _tidy(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:!?)])", r"\1", text)
    text = re.sub(r"([(])\s+", r"\1", text)
    text = re.sub(r"([,;:])(?:\s*[,;:])+", r"\1", text)
    text = re.sub(r"^[,;:\s]+", "", text)
    text = re.sub(r"[,;:]+(?=[.!?]|$)", "", text)
    text = re.sub(r"\(\s*\)", "", text)
    return text.strip()
