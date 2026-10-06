"""Read front matter, headings, and links from wiki Markdown."""

from __future__ import annotations

import datetime
import re

import yaml
from markdown_it import MarkdownIt


class MarkdownError(ValueError):
    """Front matter that cannot be read safely."""


class _FrontMatterLoader(yaml.SafeLoader):
    """A safe loader that also rejects aliases, which can expand exponentially."""

    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise MarkdownError("front matter must not use YAML aliases")
        return super().compose_node(parent, index)


def parser() -> MarkdownIt:
    """CommonMark plus the pipe tables the wiki uses."""
    return MarkdownIt("commonmark").enable("table")


def split_front_matter(text: str) -> tuple[dict | None, str]:
    """Return the YAML front matter and the body with those lines blanked.

    Blanking instead of removing the lines keeps parser line numbers equal to
    the original file's line numbers.
    """
    lines = text.split("\n")
    if lines[0].rstrip("\r") != "---":
        return None, text
    for end in range(1, len(lines)):
        if lines[end].rstrip("\r") in ("---", "..."):
            break
    else:
        raise MarkdownError("front matter starting on line 1 has no closing '---' line")
    source = "\n".join(lines[1:end])
    try:
        data = yaml.load(source, Loader=_FrontMatterLoader)
    except yaml.YAMLError as error:
        raise MarkdownError(f"front matter is not valid YAML: {error}") from error
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise MarkdownError("front matter must be a YAML mapping")
    return _json_safe(data), "\n" * (end + 1) + "\n".join(lines[end + 1:])


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def github_anchor(text: str) -> str:
    """Approximate GitHub's heading anchor: lowercase, drop punctuation, hyphenate spaces."""
    return re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")


def unique_anchor(anchors: dict[str, int], text: str) -> str:
    """Return a heading's anchor, numbering repeated anchors in document order as GitHub does."""
    anchor = base = github_anchor(text)
    if base in anchors:
        anchors[base] += 1
        anchor = f"{base}-{anchors[base]}"
    anchors.setdefault(anchor, 0)
    return anchor


def _plain_text(tokens) -> str:
    parts = []
    for token in tokens:
        if token.type in ("text", "code_inline"):
            parts.append(token.content)
        elif token.type in ("softbreak", "hardbreak"):
            parts.append(" ")
        elif token.type == "image":
            parts.append(_plain_text(token.children or []))
    return "".join(parts).strip()


def outline(body: str) -> dict:
    """Return the title, headings, and links of a Markdown body.

    Headings are numbered in document order and record their parent heading.
    Each link records the lines of its enclosing block and its nearest heading.
    Line numbers are 1-based.
    """
    headings: list[dict] = []
    links: list[dict] = []
    anchors: dict[str, int] = {}
    stack: list[dict] = []
    tokens = parser().parse(body)
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            level = int(token.tag[1:])
            text = _plain_text(tokens[index + 1].children or [])
            anchor = unique_anchor(anchors, text)
            while stack and stack[-1]["level"] >= level:
                stack.pop()
            heading = {
                "id": len(headings), "level": level, "text": text, "anchor": anchor,
                "line": token.map[0] + 1, "parent": stack[-1]["id"] if stack else None,
            }
            headings.append(heading)
            stack.append(heading)
        elif token.type == "inline" and token.children:
            section = stack[-1]["id"] if stack else None
            lines = (token.map[0] + 1, token.map[1]) if token.map else (None, None)
            children = token.children
            for position, child in enumerate(children):
                if child.type == "link_open":
                    depth, end = 1, position + 1
                    while end < len(children) and depth:
                        depth += {"link_open": 1, "link_close": -1}.get(children[end].type, 0)
                        end += 1
                    links.append({
                        "text": _plain_text(children[position + 1:end - 1]), "href": child.attrGet("href"),
                        "image": False, "line": lines[0], "end_line": lines[1], "section": section,
                    })
                elif child.type == "image":
                    links.append({
                        "text": _plain_text(child.children or []), "href": child.attrGet("src"),
                        "image": True, "line": lines[0], "end_line": lines[1], "section": section,
                    })
    title = next((heading["text"] for heading in headings if heading["level"] == 1), None)
    return {"title": title, "headings": headings, "links": links}


def block_tree(body: str) -> dict:
    """Return the top-level headings and the nested blocks of a Markdown body.

    Headings outside lists and block quotes divide the body into sections; each
    heading records its parent heading's index. Each top-level block records the
    index of the heading it follows, or None before the first heading. List items
    and block quotes hold their own blocks, and a heading inside them is a block.
    Line ranges are 1-based and inclusive, without trailing blank lines.

    Inline content is a list of runs (text, code, html, image, or break), each
    with its source line and the index of its enclosing link in the inline's own
    link list. Emphasis markers are dropped.
    """
    return _BlockWalker(parser().parse(body), body.split("\n")).document()


class _BlockWalker:
    def __init__(self, tokens, lines: list[str]):
        self.tokens = tokens
        self.lines = lines
        self.position = 0
        self.anchors: dict[str, int] = {}

    def span(self, token) -> list[int] | None:
        if not token.map:
            return None
        start, end = token.map
        while end > start + 1 and not self.lines[end - 1].strip():
            end -= 1
        return [start + 1, end]

    def document(self) -> dict:
        headings: list[dict] = []
        blocks: list[dict] = []
        stack: list[int] = []
        while self.position < len(self.tokens):
            token = self.tokens[self.position]
            if token.type == "heading_open" and token.level == 0:
                heading = self.heading(token)
                while stack and headings[stack[-1]]["level"] >= heading["level"]:
                    stack.pop()
                heading["parent"] = stack[-1] if stack else None
                headings.append(heading)
                stack.append(len(headings) - 1)
            elif (block := self.block()) is not None:
                block["heading"] = len(headings) - 1 if headings else None
                blocks.append(block)
        return {"headings": headings, "blocks": blocks}

    def heading(self, token) -> dict:
        inline = self.tokens[self.position + 1]
        self.position += 3
        text = _plain_text(inline.children or [])
        return {"level": int(token.tag[1:]), "text": text, "anchor": unique_anchor(self.anchors, text),
                "line": token.map[0] + 1, "inline": self.inline(inline)}

    def children(self, close: str) -> list[dict]:
        blocks = []
        while self.tokens[self.position].type != close:
            if (block := self.block()) is not None:
                blocks.append(block)
        self.position += 1
        return blocks

    def block(self) -> dict | None:
        token = self.tokens[self.position]
        kind, lines = token.type, self.span(token)
        if kind == "paragraph_open":
            inline = self.tokens[self.position + 1]
            self.position += 3
            return {"type": "paragraph", "lines": lines, "inline": self.inline(inline)}
        if kind == "heading_open":
            return {"type": "heading", "lines": lines, **self.heading(token)}
        if kind in ("bullet_list_open", "ordered_list_open"):
            ordered = kind == "ordered_list_open"
            close = kind.replace("_open", "_close")
            self.position += 1
            items = []
            while (item := self.tokens[self.position]).type != close:
                self.position += 1
                items.append({"lines": self.span(item), "blocks": self.children("list_item_close")})
            self.position += 1
            start = int(token.attrGet("start") or 1) if ordered else None
            return {"type": "list", "lines": lines, "ordered": ordered, "start": start, "items": items}
        if kind == "blockquote_open":
            self.position += 1
            return {"type": "blockquote", "lines": lines, "blocks": self.children("blockquote_close")}
        self.position += 1
        if kind in ("fence", "code_block"):
            info = token.info.strip() if kind == "fence" else ""
            return {"type": "code", "lines": lines, "fenced": kind == "fence", "info": info,
                    "language": info.split()[0].lower() if info else None, "content": token.content}
        if kind == "table_open":
            return self.table(lines)
        if kind == "html_block":
            return {"type": "html", "lines": lines, "content": token.content}
        if kind == "hr":
            return {"type": "rule", "lines": lines}
        return None

    def table(self, lines: list[int] | None) -> dict:
        header: list[dict] = []
        rows: list[dict] = []
        align: list[str | None] = []
        row: dict = {}
        in_header = False
        while (token := self.tokens[self.position]).type != "table_close":
            if token.type in ("thead_open", "thead_close"):
                in_header = token.type == "thead_open"
            elif token.type == "tr_open":
                row = {"line": token.map[0] + 1 if token.map else None, "cells": []}
            elif token.type == "th_open":
                style = token.attrGet("style") or ""
                align.append(style.removeprefix("text-align:") or None)
            elif token.type == "inline":
                row["cells"].append(self.inline(token))
            elif token.type == "tr_close":
                if in_header:
                    header = row["cells"]
                else:
                    rows.append(row)
            self.position += 1
        self.position += 1
        return {"type": "table", "lines": lines, "align": align, "header": header, "rows": rows}

    @staticmethod
    def inline(token) -> dict:
        line = token.map[0] + 1 if token.map else None
        runs: list[dict] = []
        links: list[dict] = []
        open_links: list[int] = []
        for child in token.children or []:
            link = open_links[-1] if open_links else None
            if child.type in ("text", "code_inline", "html_inline"):
                kind = {"text": "text", "code_inline": "code", "html_inline": "html"}[child.type]
                runs.append({"kind": kind, "text": child.content, "line": line, "link": link})
            elif child.type in ("softbreak", "hardbreak"):
                runs.append({"kind": "break", "text": " ", "line": line, "link": link})
                line = line + 1 if line is not None else None
            elif child.type == "link_open":
                links.append({"href": child.attrGet("href"), "image": False, "line": line})
                open_links.append(len(links) - 1)
            elif child.type == "link_close" and open_links:
                open_links.pop()
            elif child.type == "image":
                links.append({"href": child.attrGet("src"), "image": True, "line": line})
                runs.append({"kind": "image", "text": _plain_text(child.children or []), "line": line,
                             "link": len(links) - 1})
        return {"runs": runs, "links": links}


def table_after_heading(body: str, heading: str) -> list[dict[str, str]]:
    """Return the rows of the first table under a heading, keyed by lowercase column name."""
    tokens = parser().parse(body)
    inside = False
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            if inside:
                return []
            inside = _plain_text(tokens[index + 1].children or []) == heading
        elif inside and token.type == "table_open":
            header: list[str] = []
            rows: list[dict[str, str]] = []
            current: list[str] = []
            for cell in tokens[index + 1:]:
                if cell.type == "table_close":
                    break
                if cell.type == "inline":
                    current.append(_plain_text(cell.children or []))
                elif cell.type == "tr_close":
                    if header:
                        rows.append(dict(zip(header, current)))
                    else:
                        header = [name.lower() for name in current]
                    current = []
            return rows
    return []
