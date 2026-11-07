"""xlsx 抽取器。"""
from __future__ import annotations

import datetime
from pathlib import Path

import openpyxl

from common import sha256_file


def _jsonable(value):
    """把单元格值转成可 JSON 序列化的形式（日期等非原生类型转字符串）。"""
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, datetime.timedelta):
        return str(value)
    return value


def _fill_value(cell):
    """填充色。主题色/索引色没有 rgb 值，此时退回 theme/indexed 标记。"""
    fill = cell.fill
    if not fill:
        return None
    fg = fill.fgColor
    if not fg:
        return None
    if fg.type == "rgb":
        return fg.rgb
    if fg.type == "theme":
        return f"theme:{fg.theme}"
    if fg.type == "indexed":
        return f"indexed:{fg.indexed}"
    return None


def _cell_payload(cell, formula_wb) -> dict:
    value = cell.value
    formula = None
    if isinstance(value, str) and value.startswith("="):
        formula = value
        try:
            cached = formula_wb[cell.parent.title][cell.coordinate].value
        except Exception:
            cached = None
        value = cached
    font = cell.font
    return {
        "value": _jsonable(value),
        "formula": formula,
        "number_format": cell.number_format,
        "font": {
            "name": font.name,
            "size": font.sz,
            "bold": bool(font.bold),
            "italic": bool(font.italic),
        },
        "alignment": {
            "horizontal": cell.alignment.horizontal,
            "vertical": cell.alignment.vertical,
            "wrap_text": bool(cell.alignment.wrap_text),
        },
        "fill": _fill_value(cell),
        "border": {
            side: getattr(cell.border, side).style
            for side in ("left", "right", "top", "bottom")
        },
    }


def _infer_header_row(rows: list[list[dict]]) -> int:
    """首行非空且下方存在数据的行视为表头；否则返回 0。"""
    if not rows:
        return 0
    first = rows[0]
    if not any(c["value"] not in (None, "") for c in first):
        return 0
    if len(rows) < 2:
        return 0
    return 1


def _cell_style(cell: dict) -> dict:
    """单元格样式。

    字体与对齐信息抽取器已经拿到了，写进块里丢掉的话，
    表格体例检查就永远看不见 xlsx 的表格。
    """
    font = cell.get("font") or {}
    align = cell.get("alignment") or {}
    return {
        "font_latin": font.get("name"),
        "font_ea": font.get("name"),
        "size_pt": font.get("size"),
        "bold": bool(font.get("bold")),
        "align": align.get("horizontal"),
    }


def extract_xlsx(path: Path) -> dict:
    path = Path(path)
    wb = openpyxl.load_workbook(str(path), data_only=False)
    formula_wb = openpyxl.load_workbook(str(path), data_only=True)

    sheets = []
    blocks = []
    index = 0
    total_rows = 0
    for ws in wb.worksheets:
        grid = []
        for row in ws.iter_rows():
            cells = [_cell_payload(c, formula_wb) for c in row]
            grid.append(cells)
        nonempty_rows = [r for r in grid if any(c["value"] not in (None, "") for c in r)]
        total_rows += len(nonempty_rows)

        cell_map = {}
        for ri, row in enumerate(ws.iter_rows(), start=1):
            for c in row:
                payload = _cell_payload(c, formula_wb)
                if payload["value"] not in (None, "") or payload["formula"]:
                    cell_map[c.coordinate] = payload

        header_row = _infer_header_row(grid)
        sheets.append({
            "name": ws.title,
            "max_row": ws.max_row,
            "max_column": ws.max_column,
            "merged_ranges": [str(r) for r in ws.merged_cells.ranges],
            "header_row": header_row,
            "headers": [str(c["value"]) for c in grid[header_row - 1]] if header_row else [],
            "cells": cell_map,
        })

        table_rows = []
        for r in grid:
            table_rows.append([
                {
                    "text": "" if c["value"] is None else str(c["value"]),
                    "style": _cell_style(c),
                }
                for c in r
            ])
        if table_rows:
            blocks.append({
                "index": index,
                "kind": "table",
                "text": "",
                "section_path": ws.title,
                "rows": table_rows,
            })
            index += 1

    return {
        "file": path.name,
        "path": str(path.resolve()),
        "type": "xlsx",
        "sha256": sha256_file(path),
        "title": "",
        "stats": {
            "paragraphs": 0,
            "tables": len(sheets),
            "pages": 0,
            "words": 0,
            "rows": total_rows,
            "sheets": len(sheets),
        },
        "sections": [
            {"path": s["name"], "level": 1, "heading": s["name"], "start": 0, "end": 0}
            for s in sheets
        ],
        "blocks": blocks,
        "sheets": sheets,
        "entities": [],
        "citations": [],
        "numbers": [],
        "notes": [],
    }
