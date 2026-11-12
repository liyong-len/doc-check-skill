"""docx 抽取器。"""
from __future__ import annotations

import re
from pathlib import Path

import docx
from docx.oxml.ns import qn
from docx.shared import Length
from docx.table import Table
from docx.text.paragraph import Paragraph

from common import sha256_file

_HEADING_RE = re.compile(r"(?:Heading|标题)\s*(\d+)\s*$")


def _heading_level(style_name: str | None) -> int:
    if not style_name:
        return 0
    m = _HEADING_RE.search(style_name.strip())
    return int(m.group(1)) if m else 0


def _run_style(run) -> dict:
    rPr = getattr(run._element, "rPr", None)
    east_asia = None
    if rPr is not None:
        rFonts = getattr(rPr, "rFonts", None)
        if rFonts is not None:
            east_asia = rFonts.get(qn("w:eastAsia"))
    size = run.font.size
    return {
        "font_latin": run.font.name,
        "font_ea": east_asia,
        "size_pt": size.pt if size is not None else None,
        "bold": bool(run.bold),
        "italic": bool(run.italic),
    }


def _style_chain(style):
    """样式继承链：段落自己的样式 → 它的基样式 → …

    文档里绝大多数段落不直接写格式，格式来自样式（Normal、Body Text Indent…）。
    只看直接格式，等于把「继承来的」当成「没设置」——
    而这两种在渲染结果上可能完全一样。
    """
    chain = []
    current = style
    while current is not None:
        chain.append(current)
        current = getattr(current, "base_style", None)
    return chain


def _inherited(paragraph, attr: str):
    """沿样式继承链找第一个有值的属性。"""
    for style in _style_chain(paragraph.style):
        value = getattr(style.paragraph_format, attr)
        if value is not None:
            return value
    return None


def _paragraph_style(paragraph, doc) -> dict:
    pf = paragraph.paragraph_format
    # 直接格式优先，没有就沿样式继承链找。
    #
    # 段落格式几乎都写在样式里（Normal 设 jc=both，Body Text Indent 设缩进），
    # 段落自己往往一个字都不写。只看直接格式的话，继承来的值会被当成
    # 「没设置」，而「没设置」与「显式设成同一个值」在渲染结果上完全一样——
    # 实测一份真实投标材料，202 个段落被判成「对齐方式未显式设置」，
    # 另有 40 个段落显式写了 both，两边其实渲染一致，却被报成 40 处「不一致」。
    align = pf.alignment if pf.alignment is not None else _inherited(paragraph, "alignment")
    # 用 xml_value（"both"/"center"/"left"…），与数据契约的 align 取值一致。
    align_val = None if align is None else getattr(align, "xml_value", None)
    ls = pf.line_spacing
    if ls is None:
        ls = _inherited(paragraph, "line_spacing")
    # line_spacing 可能是倍数（float）或绝对值（Length，后者是 int 子类，
    # 必须先判 Length，否则绝对行距会被误当作倍数）。
    if ls is None:
        line_spacing = None
    elif isinstance(ls, Length):
        line_spacing = ls.pt / 12.0
    else:
        line_spacing = ls
    sb, sa = pf.space_before, pf.space_after
    if sb is None:
        sb = _inherited(paragraph, "space_before")
    if sa is None:
        sa = _inherited(paragraph, "space_after")
    left_indent = pf.left_indent if pf.left_indent is not None else _inherited(paragraph, "left_indent")
    first_indent = (pf.first_line_indent if pf.first_line_indent is not None
                    else _inherited(paragraph, "first_line_indent"))
    style_name = paragraph.style.name if paragraph.style is not None else None
    level = _heading_level(style_name)

    run = None
    for r in paragraph.runs:
        if r.text.strip():
            run = r
            break
    rs = _run_style(run) if run is not None else {
        "font_latin": None, "font_ea": None,
        "size_pt": None, "bold": False, "italic": False,
    }

    pPr = getattr(paragraph._p, "pPr", None)
    numbered = False
    if pPr is not None:
        numbered = pPr.find(qn("w:numPr")) is not None

    return {
        "font_latin": rs["font_latin"],
        "font_ea": rs["font_ea"],
        "size_pt": rs["size_pt"],
        "bold": rs["bold"],
        "italic": rs["italic"],
        "align": align_val,
        "indent_left_pt": left_indent.pt if left_indent is not None else 0.0,
        "indent_first_pt": first_indent.pt if first_indent is not None else 0.0,
        "line_spacing": line_spacing,
        "space_before_pt": sb.pt if sb is not None else 0.0,
        "space_after_pt": sa.pt if sa is not None else 0.0,
        "style_name": style_name,
        "is_heading": level > 0,
        "heading_level": level,
        "list_numbered": numbered,
        "confidence": "high",
    }


def _iter_body(doc):
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield Table(child, doc)


def _section_path_stack(blocks) -> list[dict]:
    stack = []
    sections = []
    for b in blocks:
        st = b.get("style") or {}
        if b["kind"] == "paragraph" and st.get("is_heading"):
            level = st.get("heading_level", 1)
            while stack and stack[-1]["level"] >= level:
                stack.pop()
            stack.append({"level": level, "heading": b.get("text", "").strip()})
        b["section_path"] = "/".join(s["heading"] for s in stack)
        if stack:
            last = stack[-1]
            for s in sections:
                if s["path"] == b["section_path"]:
                    last = s
                    break
            else:
                s = {
                    "path": b["section_path"],
                    "level": last["level"],
                    "heading": last["heading"],
                    "start": b["index"],
                    "end": b["index"],
                }
                sections.append(s)
            last["end"] = b["index"]
    return sections


def _cell_style(cell) -> dict:
    ps = cell.paragraphs
    if not ps:
        return {}
    p = ps[0]
    style = _paragraph_style(p, None)
    return {
        "font_latin": style["font_latin"],
        "font_ea": style["font_ea"],
        "size_pt": style["size_pt"],
        "bold": style["bold"],
        "align": style["align"],
    }


def extract_docx(path: Path) -> dict:
    path = Path(path)
    doc = docx.Document(str(path))
    blocks = []
    index = 0
    paragraphs = 0
    tables = 0
    for item in _iter_body(doc):
        if isinstance(item, Paragraph):
            text = item.text
            blocks.append({
                "index": index,
                "kind": "paragraph",
                "text": text,
                "style": _paragraph_style(item, doc),
            })
            paragraphs += 1
        else:
            rows = []
            for row in item.rows:
                rows.append([
                    {"text": c.text, "style": _cell_style(c)} for c in row.cells
                ])
            blocks.append({
                "index": index,
                "kind": "table",
                "text": "",
                "rows": rows,
            })
            tables += 1
        index += 1

    sections = _section_path_stack(blocks)

    words = 0
    for b in blocks:
        if b["kind"] == "paragraph":
            words += len(b["text"])
        else:
            for r in b.get("rows", []):
                for c in r:
                    words += len(c["text"])

    title = ""
    try:
        title = doc.core_properties.title or ""
    except Exception:
        title = ""

    return {
        "file": path.name,
        "path": str(path.resolve()),
        "type": "docx",
        "sha256": sha256_file(path),
        "title": title,
        "stats": {
            "paragraphs": paragraphs,
            "tables": tables,
            "pages": 0,
            "words": words,
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
