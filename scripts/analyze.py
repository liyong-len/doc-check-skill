"""确定性检查：样式一致性、段落格式一致性、体例规则、主体名。

本文件在后续任务中继续扩展，先落地样式与段落格式两块。
"""
from __future__ import annotations

from collections import Counter

from schema import make_finding

# 参与一致性比对的样式字段
_FONT_KEYS = ("font_latin", "font_ea", "size_pt")
_PARA_KEYS = ("align", "indent_left_pt", "indent_first_pt",
              "line_spacing", "space_before_pt", "space_after_pt")

_FIELD_LABELS = {
    "font_latin": "西文字体",
    "font_ea": "中文字体",
    "size_pt": "字号",
    "align": "对齐方式",
    "indent_left_pt": "左缩进",
    "indent_first_pt": "首行缩进",
    "line_spacing": "行距",
    "space_before_pt": "段前距",
    "space_after_pt": "段后距",
}


def _iter_paragraph_blocks(documents):
    for doc in documents:
        for b in doc.get("blocks", []):
            if b.get("kind") != "paragraph":
                continue
            style = b.get("style")
            if not style or style.get("confidence") != "high":
                continue
            yield doc, b, style


def dominant(documents, key: str) -> tuple[object, int, int]:
    """返回 (主流值, 主流值出现次数, 参与统计的段落总数)。"""
    counter: Counter = Counter()
    total = 0
    for _, _, style in _iter_paragraph_blocks(documents):
        total += 1
        counter[style.get(key)] += 1
    if not counter:
        return None, 0, 0
    value, count = counter.most_common(1)[0]
    return value, count, total


def style_fingerprint(style: dict) -> tuple:
    return tuple(style.get(k) for k in _FONT_KEYS + _PARA_KEYS)


def _fmt(value) -> str:
    if value is None:
        return "未设置"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _collect_deviations(documents, keys, category, severity, min_ratio=0.6):
    """统计偏离主流值的段落。偏离比例低于 min_ratio 的字段不报，避免个别段落误报。"""
    issues = []
    for key in keys:
        counter: Counter = Counter()
        total = 0
        for _, _, style in _iter_paragraph_blocks(documents):
            total += 1
            counter[style.get(key)] += 1
        if total < 3:
            continue
        main_value, main_count = counter.most_common(1)[0]
        if main_count / total < min_ratio:
            continue
        for doc, block, style in _iter_paragraph_blocks(documents):
            actual = style.get(key)
            if actual == main_value:
                continue
            issues.append(make_finding(
                severity=severity,
                category=category,
                detector="deterministic",
                confidence="确定",
                file=doc["file"],
                locator={
                    "type": "paragraph",
                    "index": block["index"],
                    "section_path": block.get("section_path", ""),
                },
                quote=block.get("text", "")[:60],
                description=(
                    f"{_FIELD_LABELS.get(key, key)}与全文主流值不一致："
                    f"本处为「{_fmt(actual)}」，主流值为「{_fmt(main_value)}」"
                    f"（{main_count}/{total} 段）。"
                ),
                suggestion=f"统一改为「{_fmt(main_value)}」。",
            ))
    return issues


def analyze(documents: list[dict]) -> dict:
    issues = []
    issues += _collect_deviations(documents, _FONT_KEYS, "字体一致性", "P2")
    issues += _collect_deviations(documents, _PARA_KEYS, "段落格式一致性", "P2")

    profile = {}
    for key in _FONT_KEYS + _PARA_KEYS:
        value, count, total = dominant(documents, key)
        profile[key] = {
            "label": _FIELD_LABELS.get(key, key),
            "dominant": value,
            "count": count,
            "total": total,
        }

    return {
        "style_profile": profile,
        "issues": issues,
        "entities": {},
        "stats": {"documents": len(documents), "issues": len(issues)},
    }
