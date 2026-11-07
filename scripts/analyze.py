"""确定性检查：样式一致性、段落格式一致性、体例规则、主体名。

本文件在后续任务中继续扩展，先落地样式与段落格式两块。
"""
from __future__ import annotations

import re
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


# 标题编号体系
_HEADING_PATTERNS = [
    ("第一章式", re.compile(r"^第[一二三四五六七八九十百]+章")),
    ("一、式", re.compile(r"^[一二三四五六七八九十]+、")),
    ("（一）式", re.compile(r"^[（(][一二三四五六七八九十]+[）)]")),
    ("1. 式", re.compile(r"^\d+[.、]\s")),
    ("1.1 式", re.compile(r"^\d+\.\d+[.、]?\s")),
]

# 图表题注写法（题注常出现在段落中间，如「如图1-1所示」，故不锚定行首）
_CAPTION_PATTERNS = [
    ("图N-N", re.compile(r"图\s*\d+[-－]\d+")),
    ("图N.N", re.compile(r"图\s*\d+\.\d+")),
    ("图N", re.compile(r"图\s*\d+")),
    ("表N-N", re.compile(r"表\s*\d+[-－]\d+")),
    ("表N.N", re.compile(r"表\s*\d+\.\d+")),
    ("表N", re.compile(r"表\s*\d+")),
]

# 引用标记写法（引用标记常嵌在句子中间，故不锚定行首）
_CITATION_PATTERNS = [
    ("文献[n]", re.compile(r"文献\[\d+\]")),
    ("[n]", re.compile(r"\[\d+\]")),
    ("（n）", re.compile(r"[（(]\d+[）)]")),
]

_DATE_PATTERNS = [
    ("2024年1月1日", re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日")),
    ("2024-01-01", re.compile(r"\d{4}-\d{2}-\d{2}")),
    ("2024/01/01", re.compile(r"\d{4}/\d{2}/\d{2}")),
    ("2024.01.01", re.compile(r"\d{4}\.\d{2}\.\d{2}")),
]

_CURRENCY_RE = re.compile(r"\d[\d,，.]*\s*(万元|元)")


def _text_blocks(documents):
    for doc in documents:
        for b in doc.get("blocks", []):
            if b.get("kind") == "paragraph" and b.get("text"):
                yield doc, b


def _classify(text, patterns):
    for label, rx in patterns:
        if rx.search(text.strip()):
            return label
    return None


def _mixed_style_issue(documents, category, patterns, severity, sample=3, prefix=""):
    """若同一文件内出现两种以上写法，报告一次文件级问题。"""
    issues = []
    for doc in documents:
        seen: dict[str, list[str]] = {}
        for _, b in _text_blocks([doc]):
            label = _classify(b["text"], patterns)
            if label:
                seen.setdefault(label, []).append(b["text"].strip()[:40])
        if len(seen) < 2:
            continue
        labels = sorted(seen)
        sample_texts = [t for v in seen.values() for t in v][:sample]
        issues.append(make_finding(
            severity=severity,
            category=category,
            detector="deterministic",
            confidence="确定",
            file=doc["file"],
            locator={"type": "file"},
            quote=sample_texts[0] if sample_texts else "",
            description=(
                f"{prefix}在同一文件内出现 {len(labels)} 种写法："
                + "、".join(labels)
                + "。示例：" + "；".join(sample_texts)
            ),
            suggestion="统一为其中一种写法，全套文档保持一致。",
        ))
    return issues


_ABBR_RE = re.compile(r"(?<![A-Za-z])[A-Z]{2,6}(?![A-Za-z])")
_DEFINED_ABBR_RE = re.compile(r"[（(]([A-Z]{2,6})[）)]")
# 通用缩写不算「未给全称」，避免误报
_ABBR_STOPLIST = {
    "PDF", "ISO", "XML", "HTML", "URL", "API", "KPI", "ROI", "TBD", "CPU",
    "RAM", "SSD", "LED", "CAD", "CAM", "PLC", "TCP", "UDP", "HTTP", "HTTPS",
}


def check_tables(documents: list[dict]) -> list[dict]:
    """表格体例：各表首行的加粗写法应一致。"""
    issues = []
    signatures = []
    for doc in documents:
        for b in doc.get("blocks", []):
            if b.get("kind") != "table":
                continue
            rows = b.get("rows") or []
            if not rows:
                continue
            first = rows[0]
            if not any((c.get("style") or {}).get("bold") is not None for c in first):
                continue
            sig = tuple(bool((c.get("style") or {}).get("bold")) for c in first)
            signatures.append((doc["file"], b["index"], sig))
    if len(signatures) < 2:
        return issues
    counts = Counter(sig for _, _, sig in signatures)
    main_sig, main_count = counts.most_common(1)[0]
    if main_count / len(signatures) < 0.6:
        return issues
    for fname, idx, sig in signatures:
        if sig == main_sig:
            continue
        issues.append(make_finding(
            severity="P2", category="表格体例", detector="deterministic",
            confidence="确定", file=fname,
            locator={"type": "table", "index": idx, "row": 1},
            quote="",
            description=(
                f"该表首行样式与全文主流写法不一致：主流为 "
                f"{'加粗' if any(main_sig) else '不加粗'}，本表为 "
                f"{'加粗' if any(sig) else '不加粗'}。"
            ),
            suggestion="统一表头行的加粗写法。",
        ))
    return issues


def check_list_numbering(documents: list[dict]) -> list[dict]:
    """列表与编号：有序列表的编号方式应一致。"""
    issues = []
    for doc in documents:
        styles: dict[str, list[str]] = {}
        for b in doc.get("blocks", []):
            if b.get("kind") != "paragraph":
                continue
            if not ((b.get("style") or {}).get("list_numbered") or b.get("list_numbered")):
                continue
            label = _classify(b.get("text", ""), _HEADING_PATTERNS)
            if label:
                styles.setdefault(label, []).append(b["text"].strip()[:40])
        if len(styles) < 2:
            continue
        labels = sorted(styles)
        issues.append(make_finding(
            severity="P2", category="列表与编号", detector="deterministic",
            confidence="确定", file=doc["file"], locator={"type": "file"},
            quote=list(styles.values())[0][0],
            description=(
                f"有序列表的编号方式混用：{'、'.join(labels)}。"
            ),
            suggestion="统一有序列表的编号方式。",
        ))
    return issues


def check_abbreviations(documents: list[dict]) -> list[dict]:
    """术语与缩写：英文缩写首次出现应给出全称。"""
    issues = []
    for doc in documents:
        defined: set[str] = set()
        seen: dict[str, str] = {}
        order: list[str] = []
        for _, b in _text_blocks([doc]):
            text = b.get("text", "")
            for m in _DEFINED_ABBR_RE.finditer(text):
                defined.add(m.group(1))
            for m in _ABBR_RE.finditer(text):
                token = m.group(0)
                if token in _ABBR_STOPLIST:
                    continue
                if token not in seen:
                    seen[token] = text.strip()[:60]
                    order.append(token)
        for token in order:
            if token in defined:
                continue
            issues.append(make_finding(
                severity="P3", category="术语与缩写", detector="deterministic",
                confidence="确定", file=doc["file"], locator={"type": "file"},
                quote=seen[token],
                description=(
                    f"缩写「{token}」在文中出现但未给出全称。"
                ),
                suggestion=f"首次出现时写为「中文全称（{token}）」。",
            ))
    return issues


def check_conventions(documents: list[dict]) -> list[dict]:
    issues = []
    issues += _mixed_style_issue(
        documents, "标题层级体例", _HEADING_PATTERNS, "P2", prefix="标题编号体系"
    )
    issues += _mixed_style_issue(
        documents, "图表题注体例", _CAPTION_PATTERNS, "P2", prefix="图表题注写法"
    )
    issues += _mixed_style_issue(
        documents, "引用标记", _CITATION_PATTERNS, "P2", prefix="引用标记写法"
    )
    issues += check_tables(documents)
    issues += check_list_numbering(documents)
    issues += check_abbreviations(documents)

    for doc in documents:
        currencies: dict[str, list[str]] = {}
        dates: dict[str, list[str]] = {}
        for _, b in _text_blocks([doc]):
            for m in _CURRENCY_RE.finditer(b["text"]):
                currencies.setdefault(m.group(1), []).append(m.group(0))
            for label, rx in _DATE_PATTERNS:
                hit = rx.search(b["text"])
                if hit:
                    dates.setdefault(label, []).append(hit.group(0))
        if len(currencies) >= 2:
            issues.append(make_finding(
                severity="P1", category="数字与单位", detector="deterministic",
                confidence="确定", file=doc["file"], locator={"type": "file"},
                quote=list(currencies.values())[0][0],
                description=(
                    "同一文件内货币单位混用："
                    + "、".join(f"{k}（{len(v)} 处）" for k, v in sorted(currencies.items()))
                    + "。单位混用可能导致金额理解偏差。"
                ),
                suggestion="统一使用「万元」或「元」，并在文档开头注明单位口径。",
            ))
        if len(dates) >= 2:
            issues.append(make_finding(
                severity="P2", category="数字与单位", detector="deterministic",
                confidence="确定", file=doc["file"], locator={"type": "file"},
                quote=list(dates.values())[0][0],
                description=(
                    "同一文件内日期格式混用："
                    + "、".join(sorted(dates))
                    + "。"
                ),
                suggestion="统一日期格式，建议全文使用「2024年1月1日」。",
            ))
    return issues


def analyze(documents: list[dict]) -> dict:
    issues = []
    issues += _collect_deviations(documents, _FONT_KEYS, "字体一致性", "P2")
    issues += _collect_deviations(documents, _PARA_KEYS, "段落格式一致性", "P2")
    issues += check_conventions(documents)

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
