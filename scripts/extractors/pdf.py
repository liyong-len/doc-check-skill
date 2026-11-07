"""pdf 抽取器。样式置信度低，格式类结论需谨慎使用。"""
from __future__ import annotations

from pathlib import Path

import pdfplumber

from common import sha256_file


def _font_stats(chars: list[dict]) -> list[dict]:
    counts: dict[tuple[str, float], int] = {}
    for ch in chars:
        key = (ch.get("fontname") or "unknown", round(float(ch.get("size") or 0), 2))
        counts[key] = counts.get(key, 0) + 1
    return [
        {"font": name, "size": size, "count": n}
        for (name, size), n in sorted(counts.items(), key=lambda kv: -kv[1])
    ]


def extract_pdf(path: Path) -> dict:
    path = Path(path)
    blocks = []
    font_stats: list[dict] = []
    pages = 0
    notes: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        pages = len(pdf.pages)
        for pi, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip():
                notes.append(f"第 {pi} 页无文本层，疑似扫描件，需 OCR")
            for f in _font_stats(page.chars):
                font_stats.append(f)
            blocks.append({
                "index": pi - 1,
                "kind": "paragraph",
                "text": text,
                "section_path": f"第 {pi} 页",
                "style": {
                    "font_latin": None,
                    "font_ea": None,
                    "size_pt": None,
                    "bold": False,
                    "italic": False,
                    "align": None,
                    "indent_left_pt": 0.0,
                    "indent_first_pt": 0.0,
                    "line_spacing": None,
                    "space_before_pt": 0.0,
                    "space_after_pt": 0.0,
                    "style_name": None,
                    "is_heading": False,
                    "heading_level": 0,
                    "list_numbered": False,
                    "confidence": "low",
                },
            })
    merged: dict[tuple[str, float], int] = {}
    for f in font_stats:
        key = (f["font"], f["size"])
        merged[key] = merged.get(key, 0) + f["count"]
    font_summary = [
        {"font": k[0], "size": k[1], "count": v}
        for k, v in sorted(merged.items(), key=lambda kv: -kv[1])
    ]
    if pages == 0:
        notes.append("PDF 没有页面，无法读取，需 OCR，当前不支持")
    elif all(not b["text"].strip() for b in blocks):
        notes.append("全文无文本层，疑似扫描件，需 OCR，当前不做内容判定")

    return {
        "file": path.name,
        "path": str(path.resolve()),
        "type": "pdf",
        "sha256": sha256_file(path),
        "title": "",
        "stats": {
            "paragraphs": len(blocks),
            "tables": 0,
            "pages": pages,
            "words": sum(len(b["text"]) for b in blocks),
            "rows": 0,
            "sheets": 0,
        },
        "sections": [],
        "blocks": blocks,
        "font_stats": font_summary,
        "entities": [],
        "citations": [],
        "numbers": [],
        "notes": notes,
    }
