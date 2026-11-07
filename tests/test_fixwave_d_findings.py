"""修复波 D 的回归测试：finding 的类别与建议。

覆盖：
- I-4 类别校验放过中英混写的标签，英文类别一路进到报告里
- M-4 在两个注册过的全称之间随便挑一个当「建议统一成」
"""
from __future__ import annotations

from analyze import analyze
from schema import validate_findings


def _doc(name, texts):
    blocks = [
        {"index": i, "kind": "paragraph", "text": t, "style": None,
         "section_path": "第一章"}
        for i, t in enumerate(texts)
    ]
    return {
        "file": name, "type": "docx", "sha256": "0" * 64, "title": "",
        "stats": {"paragraphs": len(blocks), "tables": 0, "pages": 1,
                  "words": 50, "rows": 0, "sheets": 0},
        "sections": [], "blocks": blocks,
        "entities": [], "citations": [], "numbers": [], "notes": [],
    }


# --- I-4：类别校验 ---


def _finding(category):
    return {
        "severity": "P1", "category": category, "detector": "llm",
        "confidence": "确定", "file": "a.docx",
        "locator": {"type": "paragraph", "index": 0},
        "quote": "原文", "description": "描述", "suggestion": "建议",
    }


def test_mixed_language_categories_are_rejected():
    """中英混写的类别不是合法字面量，必须在写 findings.json 时就被拦下。"""
    for category in ["typo错别字", "format 格式", "typo", "format", "错别字 typo"]:
        errors = validate_findings([_finding(category)])
        assert errors, category


def test_legal_categories_pass():
    """清单里的类别必须能过。"""
    from categories import ALL_CATEGORIES
    for category in ALL_CATEGORIES:
        assert validate_findings([_finding(category)]) == [], category


def test_the_category_list_matches_the_reference_documents():
    """references 下的两份文档与 scripts/categories.py 必须一致。"""
    from pathlib import Path
    from categories import ALL_CATEGORIES, SEMANTIC_CATEGORIES
    ref = Path(__file__).resolve().parent.parent / "references"
    content = (ref / "content-rules.md").read_text(encoding="utf-8")
    for category in SEMANTIC_CATEGORIES:
        assert category in content, category
    severity = (ref / "severity.md").read_text(encoding="utf-8")
    for category in ALL_CATEGORIES:
        assert category in severity, category


# --- M-4：两个注册名称之间不挑一个当「建议统一成」 ---


def test_no_arbitrary_pick_between_two_registered_names():
    """两个都是注册过的全称时，文档里没有依据判断哪一个才是正式写法。"""
    docs = [_doc("a.docx", [
        "本项目由北京华信科技有限公司负责。",
        "北京华信科技有限责任公司将提供支持。",
    ])]
    result = analyze(docs)
    issue = next(i for i in result["issues"] if i["category"] == "主体名称")
    assert "统一为正式全称「" not in issue["suggestion"], issue["suggestion"]
    assert "需人工核实" in issue["suggestion"], issue["suggestion"]


def test_a_non_enterprise_form_still_points_at_the_full_name():
    """只有一种写法是企业形式的全称时，建议统一成它是有依据的。

    「中国建筑设计院」是组织形式词，不是企业形式；
    「中国建筑设计院有限公司」才是企业全称。前者不是另一个注册名称，
    统一成后者有依据。
    """
    docs = [_doc("a.docx", [
        "本项目由中国建筑设计院编制。",
        "中国建筑设计院有限公司承担实施。",
    ])]
    result = analyze(docs)
    issue = next(i for i in result["issues"] if i["category"] == "主体名称")
    assert "统一为正式全称「中国建筑设计院有限公司」" in issue["suggestion"], \
        issue["suggestion"]
