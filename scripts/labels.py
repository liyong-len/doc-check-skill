"""报告里的字面量：内部枚举 → 中文显示。

报告是给人读的，全部输出必须是中文。finding 里的枚举值是英文
（detector 是 deterministic / llm，locator.type 是 file / paragraph /
table / section），直接透出到 HTML 就成了「来源标签 deterministic」
「位置: file」这样的夹生词。这里集中做一次映射。

映射表之外的值一律给出中文兜底，不把来路不明的英文标签漏进报告。
"""
from __future__ import annotations

from categories import ALL_CATEGORIES

# 来源：确定性检查 / 模型
DETECTOR_LABELS = {
    "deterministic": "确定性",
    "llm": "模型",
}

# 位置类型
LOCATOR_TYPE_LABELS = {
    "file": "全文（整篇）",
    "paragraph": "段落",
    "table": "表格",
    "section": "章节",
}

# 置信度（合法值本身就是中文，这里只是兜底）
CONFIDENCE_LABELS = {
    "确定": "确定",
    "疑似 · 需人工核实": "疑似 · 需人工核实",
}

def detector_label(value) -> str:
    """来源标签。"""
    return DETECTOR_LABELS.get(str(value or ""), "未标注来源")


def locator_type_label(value) -> str:
    """位置类型标签。文件级的问题显示为「全文（整篇）」。"""
    return LOCATOR_TYPE_LABELS.get(str(value or ""), "位置未标注")


def confidence_label(value) -> str:
    """置信度标签。"""
    return CONFIDENCE_LABELS.get(str(value or ""), "未标注置信度")


def category_label(value) -> str:
    """问题类别。

    合法类别（固定清单里的中文名）原样显示；空值显示「未分类」。
    不在清单里的类别不是合法字面量——多半是模型自造的英文标签
    （「typo」「format」）或中英混写（「typo错别字」）。
    这种值显示成「未分类（类别非规范）」：报告全是中文，不能把英文标签
    漏进去；但也不能一声不响地当成「未分类」——那等于把模型的错误藏起来，
    读者只会以为文档里没有这一类问题。

    正常路径上这类值到不了渲染器：validate_findings 会先把 findings.json
    拦下来并报出错误（见 schema.py），模型的错误不会被藏起来。
    """
    text = str(value or "").strip()
    if not text:
        return "未分类"
    if text not in ALL_CATEGORIES:
        return "未分类（类别非规范）"
    return text
