"""按角色分组算样式主流值的测试。

**这些测试在防什么**：把标题与正文混在一起算一个主流值，
格式完全正确的文档会报出几百条「不一致」——标题是 16pt 黑体、
正文是 12pt 宋体，这是正确排版，不是问题。

真实样本：一份四文档的投标材料，混算报出 478 条样式偏离，
其中 456 条落在标题上。按角色分组后只剩 2 条（公函体首行不缩进，确实该看）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from analyze import analyze
from roles import paragraph_role, role_label


def _doc(name, blocks):
    return {
        "file": name, "type": "docx", "sha256": "0" * 64, "title": "",
        "stats": {"paragraphs": len(blocks), "tables": 0, "pages": 1,
                  "words": 100, "rows": 0, "sheets": 0},
        "sections": [], "blocks": blocks,
        "entities": [], "citations": [], "numbers": [], "notes": [],
    }


def _style(**kw):
    base = {
        "font_latin": "Times New Roman", "font_ea": "宋体", "size_pt": 12.0,
        "bold": False, "italic": False, "align": None,
        "indent_left_pt": 0.0, "indent_first_pt": 24.0, "line_spacing": 1.5,
        "space_before_pt": 0.0, "space_after_pt": 0.0, "style_name": "Normal",
        "is_heading": False, "heading_level": 0, "list_numbered": False,
        "confidence": "high",
    }
    base.update(kw)
    return base


def _para(text, style):
    return {"index": 0, "kind": "paragraph", "text": text, "style": style,
            "section_path": ""}


def _style_issues(result):
    return [i for i in result["issues"]
            if i["category"] in ("字体一致性", "段落格式一致性")]


# --- 角色判定 ---


def test_body_paragraph_is_body_role():
    assert paragraph_role("这是一段正文内容。", _style()) == "正文"


def test_bold_centered_paragraph_is_document_title():
    assert paragraph_role("技术应答", _style(bold=True, align="center")) == "文档标题"


def test_numbered_paragraph_records_its_numbering_style():
    """编号段落要记住加粗与否。

    同一个编号体系下，加粗的与不加粗的可能是两种东西：
    「（一）重大变更：包括……」在正文里是列举项，不是标题。
    混在一群里比会互相报偏离。
    """
    assert paragraph_role("一、项目简介", _style(bold=True)) == "一、式·加粗"
    assert paragraph_role("一、项目简介", _style(bold=False)) == "一、式·不加粗"


def test_caption_paragraph_is_recognised():
    assert paragraph_role("表3 演练科目设计", _style(bold=True, align="center")) == "图表题注"
    assert paragraph_role("图 2-1 网络拓扑", _style()) == "图表题注"


def test_word_heading_style_is_recognised_as_heading():
    """抽取器认出来的标题（Word 标题样式）就是标题。

    文本里没有编号的标题（「平台优势」「技术可行性分析」）靠文本判断会漏掉，
    它们会被当成正文，标题的段间距与缩进就被拿去和正文比，报出假偏离。
    """
    style = _style(is_heading=True, heading_level=3)
    assert paragraph_role("平台优势", style) == "标题3级"


def test_list_item_has_its_own_role():
    """列表项单独成类。

    列表项的缩进与段间距由列表层级决定，与正文段落本来就不是一套。
    """
    style = _style(list_numbered=True)
    assert paragraph_role("富媒体专项指标（图片 / 音频 / 视频 / 卡片）", style) == "列表项"


def test_list_item_is_not_compared_with_body_text():
    """列表项的缩进层级不同，不该被判成偏离正文缩进。"""
    blocks = []
    for i in range(4):
        blocks.append(_para(f"正文段落{i}", _style()))
    for i in range(3):
        blocks.append(_para(f"一级列表项{i}", _style(
            list_numbered=True, indent_left_pt=21.0, indent_first_pt=-21.0)))
    for i in range(3):
        blocks.append(_para(f"二级列表项{i}", _style(
            list_numbered=True, indent_left_pt=45.0, indent_first_pt=-45.0)))
    result = analyze([_doc("a.docx", blocks)])
    issues = [i for i in _style_issues(result)
              if i["locator"]["field"] == "indent_left_pt"]
    assert issues == [], issues


def test_empty_paragraph_has_no_role():
    assert paragraph_role("   ", _style()) == ""


def test_role_labels_are_readable():
    """角色标识是内部的，报告里显示的必须是中文。"""
    assert role_label("正文") == "正文"
    assert role_label("文档标题") == "文档标题"
    assert role_label("一、式·加粗") == "一、式·加粗"


# --- 主流值按角色分组 ---


def test_heading_size_differing_from_body_is_not_a_deviation():
    """标题 16pt 黑体、正文 12pt 宋体是正确排版，不该报偏离。"""
    blocks = []
    for i in range(5):
        blocks.append(_para(f"一、第{i}章标题", _style(
            size_pt=16.0, font_ea="黑体", bold=True, indent_first_pt=0.0)))
        blocks.append(_para(f"这是第{i}章的正文内容。", _style()))
    result = analyze([_doc("a.docx", blocks)])
    assert _style_issues(result) == [], _style_issues(result)


def test_same_role_deviation_is_still_reported():
    """同一角色内部不一致仍要报出来——分组不是把检查关掉。"""
    blocks = [_para(f"正常段落{i}", _style()) for i in range(5)]
    blocks.append(_para("这一段用了仿宋", _style(font_ea="仿宋")))
    result = analyze([_doc("a.docx", blocks)])
    issues = _style_issues(result)
    assert issues, "正文里混入不同字体应当报出"
    issue = next(i for i in issues if i["locator"]["field"] == "font_ea")
    assert issue["confidence"] == "确定"
    assert "仿宋" in issue["description"]


def test_deviation_description_names_the_role():
    """问题描述要说明是跟哪一类比的。"""
    blocks = [_para(f"正常段落{i}", _style()) for i in range(5)]
    blocks.append(_para("这一段用了仿宋", _style(font_ea="仿宋")))
    result = analyze([_doc("a.docx", blocks)])
    issue = next(i for i in _style_issues(result)
                 if i["locator"]["field"] == "font_ea")
    assert "正文" in issue["description"]


def test_deviation_locator_carries_the_role():
    blocks = [_para(f"正常段落{i}", _style()) for i in range(5)]
    blocks.append(_para("这一段用了仿宋", _style(font_ea="仿宋")))
    result = analyze([_doc("a.docx", blocks)])
    issue = next(i for i in _style_issues(result)
                 if i["locator"]["field"] == "font_ea")
    assert issue["locator"]["role"] == "正文"


def test_two_files_with_different_styles_are_not_cross_compared():
    """不同文件可以有不同的排版风格。

    拿 A 文件的正文主流值去要求 B 文件的正文，是把「风格差异」
    报成「不一致」。B 文件里每一个段落都不该被判为偏离。
    """
    a_blocks = [_para(f"A文件正文{i}", _style()) for i in range(5)]
    b_blocks = [_para(f"B文件正文{i}", _style(font_ea="仿宋", size_pt=10.5))
                for i in range(5)]
    result = analyze([_doc("a.docx", a_blocks), _doc("b.docx", b_blocks)])
    assert _style_issues(result) == [], _style_issues(result)


def test_inherited_value_is_not_treated_as_a_deviation():
    """「未显式设置」的段落不参与比对。

    None 的含义是「继承样式里的值」，拿它跟显式设了 12pt 的段落比，
    比的是看不见的差异——读者按报告去改，改不出任何变化。
    """
    blocks = [_para(f"显式设了字号的段落{i}", _style(size_pt=12.0))
              for i in range(5)]
    blocks.append(_para("这一段没有显式设置字号", _style(size_pt=None)))
    result = analyze([_doc("a.docx", blocks)])
    issues = [i for i in _style_issues(result)
              if i["locator"]["field"] == "size_pt"]
    assert issues == [], issues


def test_explicit_value_against_inherited_majority_is_reported():
    """多数段落未显式设置时，单独设了值的那段要报出来。

    这一条与上一条方向相反：不是「继承的跟显式的比」，
    而是「多数继承的背景下，这几段单独设了」——渲染结果确实可能不同。
    """
    blocks = [_para(f"没有显式设置字体的段落{i}", _style(font_ea=None))
              for i in range(5)]
    blocks.append(_para("这一段单独设了仿宋", _style(font_ea="仿宋")))
    result = analyze([_doc("a.docx", blocks)])
    issues = [i for i in _style_issues(result)
              if i["locator"]["field"] == "font_ea"]
    assert issues, "单独设了字体的段落应当报出来"
    assert "未显式设置" in issues[0]["description"]
    # 括号里的两个数是「未显式设置的段数 / 总段数」，次序不能反
    assert "（5/6 段）" in issues[0]["description"], issues[0]["description"]


# --- 样式主流值按角色给出 ---


def test_style_profile_is_grouped_by_role():
    blocks = []
    for i in range(5):
        blocks.append(_para(f"一、第{i}章标题", _style(
            size_pt=16.0, font_ea="黑体", bold=True, indent_first_pt=0.0)))
        blocks.append(_para(f"这是第{i}章的正文内容。", _style()))
    result = analyze([_doc("a.docx", blocks)])
    profile = result["style_profile"]
    assert "正文" in profile
    assert "一、式·加粗" in profile
    # 角色各自的流��值必须不同，否则分组没起作用
    assert profile["正文"]["files"]["a.docx"]["size_pt"]["dominant"] == 12.0
    assert profile["一、式·加粗"]["files"]["a.docx"]["size_pt"]["dominant"] == 16.0


def test_style_profile_is_per_file():
    """主流值按文件分别给出。"""
    a_blocks = [_para(f"A正文{i}", _style()) for i in range(5)]
    b_blocks = [_para(f"B正文{i}", _style(size_pt=10.5)) for i in range(5)]
    result = analyze([_doc("a.docx", a_blocks), _doc("b.docx", b_blocks)])
    profile = result["style_profile"]["正文"]["files"]
    assert profile["a.docx"]["size_pt"]["dominant"] == 12.0
    assert profile["b.docx"]["size_pt"]["dominant"] == 10.5


def test_analyze_is_order_independent():
    """文档顺序不影响结论。"""
    a_blocks = [_para(f"正文{i}", _style()) for i in range(5)]
    b_blocks = [_para(f"另一份{i}", _style(font_ea="仿宋")) for i in range(5)]
    one = analyze([_doc("a.docx", a_blocks), _doc("b.docx", b_blocks)])
    two = analyze([_doc("b.docx", b_blocks), _doc("a.docx", a_blocks)])
    assert one == two


# --- 样本回归 ---


def test_mixed_document_reports_only_real_deviations():
    """一份格式正确的混合文档：标题与正文各按自己的写法，不报偏离。

    这份样本的形态取自真实投标材料——文档标题 18pt 黑体、
    一级标题 16pt 黑体、二级标题 14pt 黑体、正文 12pt 宋体缩进 24。
    改动前它会报出 100 多条「不一致」，改动后应当只剩真正的偏离。
    """
    blocks = []
    blocks.append(_para("技术应答", _style(
        size_pt=18.0, font_ea="黑体", bold=True, align="center",
        indent_first_pt=0.0)))
    for i in range(3):
        blocks.append(_para(f"一、第{i}章标题", _style(
            size_pt=16.0, font_ea="黑体", bold=True, indent_first_pt=0.0)))
        for j in range(3):
            blocks.append(_para(f"（{j}）二级标题", _style(
                size_pt=14.0, font_ea="黑体", bold=True, indent_first_pt=0.0)))
            for k in range(3):
                blocks.append(_para(f"这是正文段落{i}{j}{k}，内容足够长以便形成主流值。",
                                    _style()))
    result = analyze([_doc("a.docx", blocks)])
    assert _style_issues(result) == [], _style_issues(result)
