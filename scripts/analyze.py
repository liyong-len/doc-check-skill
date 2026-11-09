"""确定性检查：样式一致性、段落格式一致性、体例规则、主体名。

本模块只做不依赖外部依据的机械检查，不联网、不调用模型。
所有问题都经 schema.make_finding 产出，置信度只有「确定」一种，
唯一的例外是 P0「主体串写」——没有外部依据，无法确认哪个名称才是对的。
"""
from __future__ import annotations

import re
from collections import Counter

from common import fmt_value as _fmt
from entities import (
    canonical_core,
    canonical_name,
    extract_company_occurrences,
    group_variants,
    is_full_company_name,
)
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
            if main_value is None:
                # 主流值是「未设置」时，说「主流值为未设置」没有可操作性：
                # 多数段落本来就没写这一项，该改的是这一段。
                description = (
                    f"{_FIELD_LABELS.get(key, key)}多数段落未显式设置"
                    f"（{main_count}/{total} 段），此处单独设为「{_fmt(actual)}」。"
                )
                suggestion = "删除此处的单独设置，或将其推广到全文。"
            else:
                description = (
                    f"{_FIELD_LABELS.get(key, key)}与全文主流值不一致："
                    f"本处为「{_fmt(actual)}」，主流值为「{_fmt(main_value)}」"
                    f"（{main_count}/{total} 段）。"
                )
                suggestion = f"统一改为「{_fmt(main_value)}」。"
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
                    "field": key,
                },
                quote=block.get("text", "")[:60],
                description=description,
                suggestion=suggestion,
            ))
    return issues


# 标题编号体系，附「隐含层级」。
#
# 同一层级用两种写法才是体例不一致；不同层级出现不同写法是正常结构。
# 「第一章 / 一、 / 1. /（一）」是标准的四级结构，跨层比较写法
# 会把每一份结构正常的中文文档都报成体例不一致。
_HEADING_PATTERNS = [
    ("第一章式", re.compile(r"^第[一二三四五六七八九十百]+章"), 1),
    ("一、式", re.compile(r"^[一二三四五六七八九十]+、"), 2),
    ("1. 式", re.compile(r"^\d+[.、]\s"), 3),
    ("（一）式", re.compile(r"^[（(][一二三四五六七八九十]+[）)]"), 4),
    ("1.1 式", re.compile(r"^\d+\.\d+[.、]?\s"), 4),
]

# 图表题注写法
#
# 序号后面若紧跟量词或量类（个/条/节/页…），那不是编号，
# 「见图 3 节」「（2）个标段」这类会被误判成题注或引用。
_NOT_A_NUMBER_TAIL = r"(?!\s*[个条项处次段章节份件标页类])"

# 题注写法按对象类型分组：图与表是两套独立的编号体系，
# 「图3-1 流程图」与「表3-1 清单」是正确写法，不是混用。
# 数字前有没有空格也算写法差异（「图1-1」与「图 1-1」）。
# 写法清单里的空格是实打实的空格，不是排版占位。
#
# 不带章节号的题注（「图3」「图 3」）算**一种**写法：正文里的交叉引用
# 「设备如图 3 所示。」与题注「图3 流程图」会同时出现在一份文件里，
# 把它们分成两种写法就报出一条确定级的假问题。带章节号的写法仍然分
# 「图 N-N」与「图N-N」两种——规范里的例子就是这一对。
_CAPTION_PATTERNS = [
    ("图 N-N", re.compile(r"图\s+\d+[-－]\d+" + _NOT_A_NUMBER_TAIL), "图"),
    ("图N-N", re.compile(r"图\d+[-－]\d+" + _NOT_A_NUMBER_TAIL), "图"),
    ("图 N.N", re.compile(r"图\s+\d+\.\d+"), "图"),
    ("图N.N", re.compile(r"图\d+\.\d+"), "图"),
    ("图N", re.compile(r"图\s*\d+" + _NOT_A_NUMBER_TAIL), "图"),
    ("表 N-N", re.compile(r"表\s+\d+[-－]\d+" + _NOT_A_NUMBER_TAIL), "表"),
    ("表N-N", re.compile(r"表\d+[-－]\d+" + _NOT_A_NUMBER_TAIL), "表"),
    ("表 N.N", re.compile(r"表\s+\d+\.\d+"), "表"),
    ("表N.N", re.compile(r"表\d+\.\d+"), "表"),
    ("表N", re.compile(r"表\s*\d+" + _NOT_A_NUMBER_TAIL), "表"),
]

# 引用标记写法。序号限三位数，避免把年份「（2024）」当引用。
#
# 「（n）」在中文文档里最常见的是枚举序号（「（1）」「（2）」），
# 不是引用标记。因此这种写法要求前面有引用引导词
# （参考文献/文献/见/据…），否则不参与写法混用的判定。
#
# 单字引导词「见」「据」本身也是普通词的一部分：
# 「意见（2）」「详见（3）」「数据（1）」「根据（2）」里的括号是枚举序号，
# 不是引用标记。中文没有词边界可依，这里用「常见的以它结尾的词」来挡：
# 这些词里出现的见/据不算引用引导词。
# 完整词（参考文献、文献、参见、引自、依据、如表）不受这条限制。
_CITATION_LEADIN_BLOCKERS = {
    "见": "意解常少不只偏遇听看详阅省可想未已闻",
    "据": "数根依证票收凭单即说此称报失",
}

_CITATION_CONTEXT = (
    r"(?:参考文献|文献|参见|引自|依据|如表"
    r"|(?<![" + _CITATION_LEADIN_BLOCKERS["见"] + r"])[见]"
    r"|(?<![" + _CITATION_LEADIN_BLOCKERS["据"] + r"])[据]"
    r")"
)
_CITATION_PATTERNS = [
    ("文献[n]", re.compile(r"文献\[\d+\]"), "引用"),
    ("[n]", re.compile(r"\[\d+(?:[-–—,，]\d+)*\]"), "引用"),
    ("（n）", re.compile(
        _CITATION_CONTEXT + r"\s*[（(]\d{1,3}[）)]" + _NOT_A_NUMBER_TAIL), "引用"),
]

_DATE_PATTERNS = [
    ("2024年1月1日", re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日")),
    ("2024-01-01", re.compile(r"\d{4}-\d{2}-\d{2}")),
    ("2024/01/01", re.compile(r"\d{4}/\d{2}/\d{2}")),
    ("2024.01.01", re.compile(r"\d{4}\.\d{2}\.\d{2}")),
]

_CURRENCY_RE = re.compile(r"\d[\d,，.]*\s*(万元|元)")


def _text_blocks(documents, include_tables=False):
    """文档里的正文块。

    include_tables 为真时，表格单元格也作为文本块给出——
    主体名与缩写常常只出现在表格里（名单表、术语表），
    只看段落会让确定性层与模型层对「文档里有哪些主体」各说各话。
    """
    for doc in documents:
        for b in doc.get("blocks", []):
            kind = b.get("kind")
            if kind == "paragraph":
                if b.get("text"):
                    yield doc, b
            elif kind == "table" and include_tables:
                for row in b.get("rows") or []:
                    for cell in row:
                        text = cell.get("text") or ""
                        if text.strip():
                            yield doc, {
                                "kind": "table_cell",
                                "text": text,
                                "index": b.get("index", 0),
                                "section_path": b.get("section_path", ""),
                            }


def _classify(text, patterns):
    """返回匹配到的体系名。patterns 的元素为 (label, regex) 或 (label, regex, depth)。"""
    for item in patterns:
        label, rx = item[0], item[1]
        if rx.search(text.strip()):
            return label
    return None


def _classify_group(text, patterns):
    """返回 (体系名, 对象类型)。对象类型用于分组比较。

    图与表是两套独立的编号体系，写法只在同一类型内部比较。
    """
    for item in patterns:
        label, rx = item[0], item[1]
        group = item[2] if len(item) > 2 else ""
        if rx.search(text.strip()):
            return label, group
    return None, ""


def _classify_depth(text, patterns):
    """返回 (体系名, 隐含层级)。patterns 元素为 (label, regex, depth)。"""
    for label, rx, depth in patterns:
        if rx.search(text.strip()):
            return label, depth
    return None, None


def _mixed_style_issue(documents, category, patterns, severity, sample=3, prefixes=None):
    """若同一文件内同一类对象出现两种以上写法，报告一次文件级问题。

    写法只在同一对象类型内部比较：图与表各是一套编号体系，
    「图3-1」与「表3-1」并存是正确写法，不是混用。
    """
    issues = []
    for doc in documents:
        seen: dict[str, dict[str, list[str]]] = {}
        for _, b in _text_blocks([doc]):
            label, group = _classify_group(b["text"], patterns)
            if label:
                seen.setdefault(group, {}).setdefault(label, []).append(
                    b["text"].strip()[:40]
                )
        for group in sorted(seen):
            labels_map = seen[group]
            if len(labels_map) < 2:
                continue
            labels = sorted(labels_map)
            sample_texts = [t for v in labels_map.values() for t in v][:sample]
            prefix = (prefixes or {}).get(group, "")
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


_HEADER_LABELS = {
    "bold": "全部加粗",
    "not-bold": "不加粗",
    "mixed": "部分加粗",
    "empty": "空表头",
}


def _header_signature(first: list[dict]) -> str:
    """表头样式指纹：只看加粗与否，不看列数。

    列数不同的表，其表头写法可能完全一致；把列数算进指纹会把
    宽度不同的表误报成体例不一致，描述还会自相矛盾
    （「主流为 加粗，本表为 加粗」）。
    """
    if not first:
        return "empty"
    bold = sum(1 for c in first if (c.get("style") or {}).get("bold"))
    if bold == 0:
        return "not-bold"
    if bold == len(first):
        return "bold"
    return "mixed"


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
            signatures.append((doc["file"], b["index"], _header_signature(first)))
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
                f"该表首行样式与全文主流写法不一致：主流为「{_HEADER_LABELS[main_sig]}」，"
                f"本表为「{_HEADER_LABELS[sig]}」。"
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
    """术语与缩写：英文缩写首次出现应给出全称。

    「首次出现时应给出全称」——定义出现在首次出现之后的段落不算数。
    缩写本身放进 locator，避免同一段里两个缩写撞指纹。

    表格也看：术语表（缩略语对照表）常在表格里，段落里看不到它，
    就会把正文里的缩写误报成「未给出全称」。
    """
    issues = []
    for doc in documents:
        para_defs: list[set[str]] = []
        para_tokens: list[list[str]] = []
        for _, b in _text_blocks([doc], include_tables=True):
            text = b.get("text", "")
            para_defs.append({m.group(1) for m in _DEFINED_ABBR_RE.finditer(text)})
            para_tokens.append([
                m.group(0) for m in _ABBR_RE.finditer(text)
                if m.group(0) not in _ABBR_STOPLIST
            ])

        defined_upto: set[str] = set()
        reported: set[str] = set()
        for i, tokens in enumerate(para_tokens):
            defined_upto |= para_defs[i]   # 本段给出的定义也算
            for token in tokens:
                if token in reported:
                    continue
                reported.add(token)
                if token in defined_upto:
                    continue
                issues.append(make_finding(
                    severity="P3", category="术语与缩写", detector="deterministic",
                    confidence="确定", file=doc["file"],
                    locator={"type": "file", "abbreviation": token},
                    quote="",
                    description=f"缩写「{token}」首次出现时未给出全称。",
                    suggestion=f"首次出现时写为「中文全称（{token}）」。",
                ))
    return issues


def check_heading_numbering(documents: list[dict]) -> list[dict]:
    """标题层级体例：同一层级的编号写法必须一致。

    不同层级出现不同写法是正常结构（第一章 / 一、 / 1. /（一）），
    只有同一层级混用两种写法才是体例不一致。
    """
    issues = []
    for doc in documents:
        by_depth: dict[int, dict[str, list[str]]] = {}
        for _, b in _text_blocks([doc]):
            label, depth = _classify_depth(b.get("text", ""), _HEADING_PATTERNS)
            if label is None:
                continue
            by_depth.setdefault(depth, {}).setdefault(label, []).append(
                b.get("text", "").strip()[:40]
            )
        for depth, styles in sorted(by_depth.items()):
            if len(styles) < 2:
                continue
            labels = sorted(styles)
            samples = [t for v in styles.values() for t in v][:3]
            issues.append(make_finding(
                severity="P2", category="标题层级体例", detector="deterministic",
                confidence="确定", file=doc["file"], locator={"type": "file"},
                quote=samples[0],
                description=(
                    f"同一层级的标题编号体系混用：{'、'.join(labels)}。"
                    f"示例：{'；'.join(samples)}"
                ),
                suggestion="统一同一层级的标题编号写法。",
            ))
    return issues


_FIG_NUM_RE = re.compile(r"(?P<kind>[图表])\s*(?P<chapter>\d+)[-－](?P<num>\d+)")


def check_heading_level_jumps(documents: list[dict]) -> list[dict]:
    """标题层级体例：标题层级不得跳级（如 H1 直接跳 H3）。"""
    issues = []
    for doc in documents:
        prev_level = 0
        prev_heading = ""
        for _, b in _text_blocks([doc]):
            style = b.get("style") or {}
            if not style.get("is_heading"):
                continue
            level = int(style.get("heading_level") or 0)
            if level <= 0:
                continue
            if prev_level and level > prev_level + 1:
                issues.append(make_finding(
                    severity="P2", category="标题层级体例", detector="deterministic",
                    confidence="确定", file=doc["file"],
                    locator={"type": "paragraph", "index": b.get("index", 0),
                             "section_path": b.get("section_path", "")},
                    quote=b.get("text", "")[:60],
                    description=(
                        f"标题层级跳级：上一级标题是第 {prev_level} 级"
                        f"（{prev_heading}），本处直接是第 {level} 级。"
                    ),
                    suggestion="补齐缺失的中间层级，或调整本标题的级别。",
                ))
            prev_level = level
            prev_heading = b.get("text", "").strip()[:20]
    return issues


def check_figure_numbering_gaps(documents: list[dict]) -> list[dict]:
    """图表题注体例：图表编号应连续，不应跳号。

    图与表各是一套独立的编号序列：第 3 章有「图3-1」与「表3-3」
    是正常的，不能因为编号不同就报缺号。
    """
    issues = []
    for doc in documents:
        by_series: dict[tuple[str, str], list[int]] = {}
        for _, b in _text_blocks([doc]):
            for m in _FIG_NUM_RE.finditer(b.get("text", "")):
                key = (m.group("kind"), m.group("chapter"))
                by_series.setdefault(key, []).append(int(m.group("num")))
        for (kind, chapter), nums in sorted(by_series.items()):
            uniq = sorted(set(nums))
            if len(uniq) < 2:
                continue
            missing = [n for n in range(1, uniq[-1] + 1) if n not in uniq]
            if not missing:
                continue
            issues.append(make_finding(
                severity="P2", category="图表题注体例", detector="deterministic",
                confidence="确定", file=doc["file"], locator={"type": "file"},
                quote=f"{kind}{chapter}-{uniq[0]}",
                description=(
                    f"第 {chapter} 章的{kind}编号不连续，缺号："
                    + "、".join(str(n) for n in missing)
                    + f"（现有编号到 {uniq[-1]}）。"
                ),
                suggestion="补齐缺号，或重新连续编号。",
            ))
    return issues


def check_conventions(documents: list[dict]) -> list[dict]:
    issues = []
    issues += check_heading_numbering(documents)
    issues += check_heading_level_jumps(documents)
    issues += check_figure_numbering_gaps(documents)
    issues += _mixed_style_issue(
        documents, "图表题注体例", _CAPTION_PATTERNS, "P2",
        prefixes={"图": "图题注写法", "表": "表题注写法"},
    )
    issues += _mixed_style_issue(
        documents, "引用标记", _CITATION_PATTERNS, "P2",
        prefixes={"引用": "引用标记写法"},
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


def check_entities(documents: list[dict]) -> tuple[list[dict], dict]:
    issues: list[dict] = []
    names: dict[str, dict] = {}
    per_file: dict[str, list[str]] = {}
    all_names: list[str] = []
    seen_names: set[str] = set()

    for doc in documents:
        found: list[str] = []
        for _, b in _text_blocks([doc], include_tables=True):
            # 用**还原名**：连接词裁剪把字号劈掉一半时（两家不同的公司
            # 都被裁成「贸易港城有限公司」），只有还原名才分得开是谁是谁。
            found.extend(restored for _name, restored in
                         extract_company_occurrences(b.get("text", "")))
        per_file[doc["file"]] = found

    # 主体清单按文件名排序后建立：同样一批文档换个顺序跑，
    # 结论必须一模一样，否则复查对比会凭空多出「新增问题」。
    for file_id in sorted(per_file):
        found = per_file[file_id]
        for name in found:
            if name not in seen_names:
                seen_names.add(name)
                all_names.append(name)
            key = canonical_core(name)
            if key not in names:
                names[key] = {"name": name, "core": key, "count": 0, "files": []}
            names[key]["count"] += 1
            if file_id not in names[key]["files"]:
                names[key]["files"].append(file_id)

    # 变体聚类必须基于全部原始写法，不能基于按主体标识归并后的名单：
    # 「北京华信科技有限公司」与「北京华信科技有限责任公司」的主体标识相同，
    # 归并后只剩一个名字，写法不统一就再也查不出来了。
    variants = group_variants(all_names)

    for group in variants:
        writings = group.get("canonicals") or group["names"]
        if len(writings) < 2:
            continue
        preferred = _preferred_writing(writings)
        if preferred:
            suggestion = f"统一为正式全称「{preferred}」。"
        else:
            # 两种写法都是注册过的全称时，文档里没有依据能判断哪一个才是
            # 正式写法。不能凭空挑一个，让用户去统一两个注册名称。
            suggestion = (
                "全套文档统一使用同一名称；文档中没有判断哪一种是正式全称的依据，"
                "需人工核实后确定。"
            )
        issues.append(make_finding(
            severity="P1", category="主体名称", detector="deterministic",
            confidence="确定", file=_first_file_for(names, group["names"]),
            locator={"type": "file"},
            quote=group["names"][0],
            description=(
                f"同一主体出现 {len(writings)} 种名称写法："
                + "、".join(writings)
                + "。全套文档应统一使用同一名称。"
            ),
            suggestion=suggestion,
        ))

    for doc in documents:
        groups = group_variants(per_file[doc["file"]])
        if len(groups) < 2:
            continue
        # 文件名与章节标题只能区分它们提到的主体。
        # 一个名字被提到，不代表其余名字也被区分了——
        # 文件名里的那个主体被区分了，文件里的另一个主体仍然没有依据。
        explained = [g for g in groups if _named_in_header(doc, g)]
        unexplained = [g for g in groups if not _named_in_header(doc, g)]
        if not unexplained:
            continue
        shown = [g["names"][0] for g in unexplained]
        if explained:
            description = (
                f"该文件出现 {len(groups)} 个不同主体，其中 {len(unexplained)} 个"
                f"（{'、'.join(shown[:5])}）未在文件名或章节标题中出现，"
                "无法据此区分归属，疑似写混。"
            )
        else:
            description = (
                f"该文件出现 {len(groups)} 个不同主体："
                + "、".join(shown[:5])
                + "。文件名与章节标题中未出现这些主体名称，无法据此区分，疑似写混。"
            )
        issues.append(make_finding(
            severity="P0", category="主体串写", detector="deterministic",
            confidence="疑似 · 需人工核实", file=doc["file"],
            locator={"type": "file"},
            quote=shown[0],
            description=description,
            suggestion="确认每个名称的归属，删除与本文件主体无关的名称。",
        ))

    summary = {
        "names": [
            {
                "name": v["name"], "core": v["core"], "count": v["count"],
                "files": v["files"],
            }
            for _, v in sorted(names.items())
        ],
        "variants": variants,
        "per_file": {k: per_file[k] for k in sorted(per_file)},
    }
    return issues, summary


def _preferred_writing(writings: list[str]) -> str:
    """建议统一成哪一种写法。

    只有一种写法带企业形式词时，它才是「正式全称」，建议统一成它有依据
    （另一个写法是裸字号，裸字号不是正式全称）。

    两种写法都是注册过的全称（「…有限公司」与「…有限责任公司」）时，
    文档里没有任何依据能判断哪一个才是正式写法——那是企业登记信息，
    文档内无从查证。此时不选，让用户自己确认。

    裸字号（「北京华信」）不是正式全称，让用户「统一为北京华信」是错的建议。
    """
    full = [w for w in writings if is_full_company_name(w)]
    if len(full) == 1:
        return full[0]
    return ""


def _first_file_for(names: dict, group_names: list[str]) -> str:
    """这一组主体出现在哪个文件里。

    取文件名最小的那一个：归属必须与输入顺序无关，
    否则同一批文档换个顺序跑，这条问题的 id 就变了。
    """
    files: list[str] = []
    for key in sorted(names):
        v = names[key]
        if v["name"] in group_names:
            files.extend(v["files"])
    return sorted(set(files))[0] if files else ""


def _named_in_header(doc: dict, group: dict) -> bool:
    """这一组主体里，是否有名字出现在文件名或章节标题中。

    规范 §5.4：疑似混主体的前提是「未由文件名或章节标题显式区分」。
    「区分」是对具体主体而言的：文件名提到甲，不等于文件里的乙
    也被区分了。因此这一判定必须按组做，不能整份文件一刀切。

    只按这一组的**实际写法**匹配，不能拿去掉行政区划的核心字号去匹配：
    文件名「北京华信科技有限公司投标文件.docx」里含有「华信科技」，
    用核心字号去匹配，文件里的「上海华信科技有限公司」也会被当成
    「文件名已经点明了」，混主体就被漏掉了。行政区划必须参与比对——
    北京的华信科技与上海的华信科技不是一家。
    """
    header = doc.get("file", "") + " " + " ".join(
        str(s.get("heading", "")) for s in doc.get("sections", [])
    )
    candidates: list[str] = []
    for name in group.get("names", []):
        if not name:
            continue
        candidates.append(name)
        canon = canonical_name(name)
        if canon != name:
            candidates.append(canon)
    for name in candidates:
        if name in header:
            return True
    return False


# 问题排序：先按严重程度，再按文件、类别、指纹。
#
# 结论必须与输入顺序无关。同一批文档换个 --files 顺序跑，
# consistency.json 必须逐字节相同，否则复查对比会凭空多出
# 「新增问题」与「已修复问题」——文件没变，结论却变了。
_SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def _issue_sort_key(issue: dict) -> tuple:
    return (
        _SEVERITY_ORDER.get(str(issue.get("severity", "")), 9),
        str(issue.get("file", "")),
        str(issue.get("category", "")),
        str(issue.get("id", "")),
        str(issue.get("description", "")),
    )


def analyze(documents: list[dict]) -> dict:
    # 文档顺序不影响结论：同样一批文档换个顺序跑，报告必须一模一样。
    documents = sorted(documents, key=lambda d: str(d.get("file", "")))

    issues = []
    issues += _collect_deviations(documents, _FONT_KEYS, "字体一致性", "P2")
    issues += _collect_deviations(documents, _PARA_KEYS, "段落格式一致性", "P2")
    issues += check_conventions(documents)

    entity_issues, entity_summary = check_entities(documents)
    issues += entity_issues

    issues.sort(key=_issue_sort_key)

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
        "entities": entity_summary,
        "stats": {"documents": len(documents), "issues": len(issues)},
    }
