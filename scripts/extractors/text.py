"""md / txt 抽取器。无样式概念，style 为 None。"""
from __future__ import annotations

import re
from pathlib import Path

from common import sha256_file

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def _parse_lines(lines: list[str]) -> tuple[list[dict], list[dict]]:
    blocks: list[dict] = []
    i = 0
    in_code = False
    stack: list[dict] = []
    sections: list[dict] = []
    index = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            i += 1
            continue
        if in_code:
            i += 1
            continue
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            heading = m.group(2)
            while stack and stack[-1]["level"] >= level:
                stack.pop()
            stack.append({"level": level, "heading": heading})
            blocks.append({
                "index": index, "kind": "paragraph", "text": heading,
                "section_path": "/".join(s["heading"] for s in stack), "style": None,
                "is_heading_md": True, "heading_level": level,
            })
            sections.append({
                "path": "/".join(s["heading"] for s in stack),
                "level": level, "heading": heading,
                "start": index, "end": index,
            })
            index += 1
            i += 1
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            rows = []
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                raw = lines[j].strip().strip("|")
                cells = [c.strip() for c in raw.split("|")]
                if not all(set(c) <= set("-: ") for c in cells):
                    rows.append(cells)
                j += 1
            blocks.append({
                "index": index, "kind": "table", "text": "",
                "section_path": "/".join(s["heading"] for s in stack),
                "rows": [[{"text": c, "style": {}} for c in r] for r in rows],
            })
            index += 1
            i = j
            continue
        if stripped:
            blocks.append({
                "index": index, "kind": "paragraph", "text": stripped,
                "section_path": "/".join(s["heading"] for s in stack), "style": None,
                "list_numbered": bool(_LIST_RE.match(line)),
            })
            index += 1
        i += 1
    return blocks, sections


def extract_text(path: Path) -> dict:
    path = Path(path)
    raw = path.read_text(encoding="utf-8", errors="replace")
    blocks, sections = _parse_lines(raw.splitlines())
    for b in blocks:
        if b["kind"] == "paragraph" and "list_numbered" not in b:
            b["list_numbered"] = False
    suffix = path.suffix.lower().lstrip(".")
    return {
        "file": path.name,
        "path": str(path.resolve()),
        "type": suffix if suffix in ("md", "txt") else "txt",
        "sha256": sha256_file(path),
        "title": "",
        "stats": {
            "paragraphs": sum(1 for b in blocks if b["kind"] == "paragraph"),
            "tables": sum(1 for b in blocks if b["kind"] == "table"),
            "pages": 0,
            "words": sum(len(b["text"]) for b in blocks),
            "rows": 0,
            "sheets": 0,
        },
        "sections": sections,
        "blocks": blocks,
        "entities": [],
        "citations": [],
        "numbers": [],
        "notes": [],
    }
