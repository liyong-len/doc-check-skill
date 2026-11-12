"""样式问题聚合渲染的测试。

**这些测试在防什么**：同一批样式偏离在 §3 逐条展开、在 §4.2 又铺一遍，
一份四文档材料能因此产出 451KB 的报告，其中 95% 是同一件事
（某文件正文字体不统一）。聚合之后：§3 不再逐条展开样式问题，
§4.2 按「文件 + 角色 + 项目 + 实际情况」聚合成组。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from render import build_html


def _manifest():
    return {
        "script_version": "0.1.0", "depth": "standard",
        "generated_at": "2026-11-07T10:00:00+08:00",
        "documents": [
            {"file": "a.docx", "type": "docx", "sha256": "c" * 64,
             "stats": {"paragraphs": 100, "tables": 2, "pages": 12,
                       "words": 5000, "rows": 0, "sheets": 0},
             "entities": [], "notes": []},
        ],
        "failures": [],
    }


def _style_issue(index, field="font_ea", role="正文", value="仿宋",
                  file="a.docx", section=""):
    return {
        "id": "i" * 16, "severity": "P2", "category": "字体一致性",
        "detector": "deterministic", "confidence": "确定", "file": file,
        "locator": {"type": "paragraph", "index": index,
                    "section_path": section, "field": field, "role": role},
        "quote": f"第 {index} 段摘录",
        "description": f"中文字体与「{role}」的主流值不一致：本处为「{value}」，主流值为「宋体」（40/42 段）。",
        "suggestion": "统一改为「宋体」。",
    }


def _semantic_finding():
    return {
        "id": "s" * 16, "severity": "P1", "category": "前后矛盾",
        "detector": "llm", "confidence": "确定", "file": "a.docx",
        "locator": {"type": "paragraph", "index": 5, "section_path": ""},
        "quote": "前文写 60 日历天，后文写 90 日历天",
        "description": "工期前后不一致", "suggestion": "统一为 60 日历天",
    }


def _html(issues=None, findings=None):
    return build_html({
        "manifest": _manifest(),
        "consistency": {"style_profile": {}, "issues": issues or [],
                        "entities": {}, "stats": {"documents": 1, "issues": 0}},
        "findings": findings or [], "baseline_diff": None,
    })


def _section(html, start, end):
    return html.split(start)[1].split(end)[0]


# --- §3 不再逐条展开样式问题 ---


def test_section3_does_not_expand_style_issues_one_by_one():
    """样式问题不在 §3 逐条展开。"""
    issues = [_style_issue(i) for i in range(20)]
    html = _html(issues=issues)
    s3 = _section(html, "id='s3'", "id='s4'")
    # 一条卡片都不该出现（§3 里样式问题只是「另有 N 处」的提示）
    assert "class=\"issue P2\"" not in s3
    assert "20 处样式问题" in s3


def test_section3_still_expands_semantic_findings():
    """语义层问题仍在 §3 逐条展开——那是要逐条读的。"""
    html = _html(findings=[_semantic_finding()])
    s3 = _section(html, "id='s3'", "id='s4'")
    assert "class=\"issue P1\"" in s3
    assert "工期前后不一致" in s3


def test_section3_keeps_other_deterministic_categories():
    """确定性层的其余类别（表格体例等）仍在 §3 逐条展开。"""
    issue = _style_issue(1)
    issue["category"] = "表格体例"
    issue["description"] = "该表首行加粗写法不一致"
    html = _html(issues=[issue])
    s3 = _section(html, "id='s3'", "id='s4'")
    assert "class=\"issue P2\"" in s3


def test_section3_counts_style_issues_in_file_total():
    """文件标题处的问题总数要把样式问题算进去。"""
    issues = [_style_issue(i) for i in range(5)]
    html = _html(issues=issues)
    s3 = _section(html, "id='s3'", "id='s4'")
    assert "5 个问题" in s3


# --- §4.2 聚合 ---


def test_section4_2_aggregates_same_kind_into_one_row():
    """同一 (文件, 角色, 项目, 实际情况) 的偏离合成一行。"""
    issues = [_style_issue(i) for i in range(10)]
    html = _html(issues=issues)
    s42 = _section(html, "4.2 样式偏离明细", "<h3>4.3")
    assert s42.count("<tr>") == 2, "十处同类偏离应合成一行（表头 + 一行数据）"
    assert "共 10 处偏离" in s42
    assert "聚合为 1 组" in s42


def test_section4_2_separates_different_roles():
    """角色不同的偏离不合并——它们是不同的事。"""
    issues = [_style_issue(1, role="正文"), _style_issue(2, role="小标题")]
    html = _html(issues=issues)
    s42 = _section(html, "4.2 样式偏离明细", "<h3>4.3")
    assert s42.count("<tr>") == 3, "两组不同角色应合成两行"
    assert "正文" in s42
    assert "小标题" in s42


def test_section4_2_shows_count_and_locations():
    """聚合行要给出处数与位置，读者据此去改。

    位置并进说明列的下半部分（带底色），不再单独占一列。
    """
    issues = [_style_issue(i) for i in range(3)]
    html = _html(issues=issues)
    s42 = _section(html, "4.2 样式偏离明细", "<h3>4.3")
    assert "<th>处数</th>" in s42
    # 位置不再是一列，而是说明单元格里的一段。
    assert "<th>位置</th>" not in s42
    assert "loc-list" in s42
    assert "段序 0" in s42
    assert "段序 2" in s42


def test_section4_2_locations_are_highlighted():
    """位置清单用底色标出来，与说明文字区分开。"""
    html = _html(issues=[_style_issue(1)])
    s42 = _section(html, "4.2 样式偏离明细", "<h3>4.3")
    assert "<div class='loc-list'>" in s42
    assert "loc-desc" in s42


def test_section4_2_lists_paragraph_indexes():
    """位置列要给出可定位的段序。"""
    issues = [_style_issue(7), _style_issue(9)]
    html = _html(issues=issues)
    s42 = _section(html, "4.2 样式偏离明细", "<h3>4.3")
    assert "段序 7" in s42
    assert "段序 9" in s42


def test_section4_2_shows_role_column():
    """聚合行要说明是哪个角色的问题。"""
    issues = [_style_issue(1, role="正文")]
    html = _html(issues=issues)
    s42 = _section(html, "4.2 样式偏离明细", "<h3>4.3")
    assert "<th>角色</th>" in s42
    assert "正文" in s42


def test_section4_2_empty_when_no_style_issue():
    html = _html(issues=[])
    s42 = _section(html, "4.2 样式偏离明细", "<h3>4.3")
    assert "未发现样式偏离" in s42


# --- §4.1 按角色给出主流值 ---


def test_section4_1_lists_role_column():
    profile = {
        "正文": {"files": {"a.docx": {
            "font_ea": {"label": "中文字体", "dominant": "宋体",
                        "count": 40, "total": 42},
        }}},
        "一、式·加粗": {"files": {"a.docx": {
            "font_ea": {"label": "中文字体", "dominant": "黑体",
                        "count": 12, "total": 12},
        }}},
    }
    html = build_html({
        "manifest": _manifest(),
        "consistency": {"style_profile": profile, "issues": [],
                        "entities": {}, "stats": {"documents": 1, "issues": 0}},
        "findings": [], "baseline_diff": None,
    })
    s41 = _section(html, "4.1 样式主流值", "4.2")
    assert "<th>角色</th>" in s41
    assert "正文" in s41
    assert "一、式·加粗" in s41
    assert "黑体" in s41


def test_section4_1_only_lists_roles_with_deviations():
    """只列有偏离的角色×文件。

    一份四文档材料的「角色 × 文件 × 字段」组合有上百个，
    全列出来没人看得下去；没有偏离的角色不需要占表格位置。
    """
    profile = {
        "正文": {"files": {"a.docx": {
            "font_ea": {"label": "中文字体", "dominant": "宋体",
                        "count": 40, "total": 42},
        }}},
        "小标题": {"files": {"a.docx": {
            "font_ea": {"label": "中文字体", "dominant": "黑体",
                        "count": 12, "total": 12},
        }}},
    }
    issue = _style_issue(1, role="正文")
    html = build_html({
        "manifest": _manifest(),
        "consistency": {"style_profile": profile, "issues": [issue],
                        "entities": {}, "stats": {"documents": 1, "issues": 1}},
        "findings": [], "baseline_diff": None,
    })
    s41 = _section(html, "4.1 样式主流值", "4.2")
    assert "正文" in s41
    assert "小标题" not in s41



# --- 章节折叠 ---

def test_every_section_is_a_collapsible_block():
    """每一节都是可折叠的块，默认收起。

    报告太长，收起后能一眼看完概况，再逐节展开细看。
    """
    html = _html(findings=[_semantic_finding()])
    for sec in ("s0", "s1", "s2", "s3", "s4", "s5", "s7"):
        assert f"class='sec' id='sec-{sec}'" in html, sec


def test_sections_are_collapsed_by_default_except_overview():
    """默认收起，但 §0 与 §1 结论概览例外——它们是读者打开报告第一眼要看的东西。

    §0 说了受检了哪些文件、有没有没能检查的；§1 说了问题总数与分布。
    把它们收起来，读者得先点两下才知道报告里有什么。
    """
    import re
    html = _html(findings=[_semantic_finding()])
    blocks = dict(re.findall(
        r"<details class='sec' id='sec-(s\d)'([^>]*)>", html))
    assert set(blocks) >= {"s0", "s1", "s2", "s3", "s4", "s5", "s7"}
    for sec, attrs in blocks.items():
        if sec in ("s0", "s1"):
            assert "open" in attrs, f"{sec} 应当默认展开"
        else:
            assert "open" not in attrs, f"{sec} 应当默认收起"


def test_section_titles_stay_visible_when_collapsed():
    """收起时标题与该节的条目数仍要看得见。

    收起不能把「这一节里有什么」也藏掉——不然读者只剩一排标题。
    """
    html = _html(findings=[_semantic_finding()])
    s3 = _section(html, "id='s3'", "id='s4'")
    assert "§3 按文件明细" in s3
    assert "sec-count" in s3


def test_section_has_fold_marker():
    """标题旁有一个折叠标记。"""
    html = _html(findings=[_semantic_finding()])
    assert "class='fold'" in html


def test_report_expands_all_sections_when_printing():
    """打印时全部展开：纸上要看到全部内容。

    收起的小节在打印时是空的，脚本在 beforeprint 里展开。
    """
    html = _html(findings=[_semantic_finding()])
    assert "beforeprint" in html
    assert "afterprint" in html


def test_report_opens_section_targeted_by_anchor():
    """从目录点进来要展开对应的小节。

    链接指向的是收起状态的标题，不展开的话读者点完看到一片空白。
    """
    html = _html(findings=[_semantic_finding()])
    assert "hashchange" in html
    assert "openTarget" in html


def test_section4_2_groups_locations_by_section():
    """同一章的段序归到一起，章名只写一次。

    逐条写成「第三部分 / 段序 62、第三部分 / 段序 52、…」时章名重复几十遍，
    位置反而看不清。
    """
    issues = [
        _style_issue(3, section="第一章"),
        _style_issue(5, section="第一章"),
        _style_issue(9, section="第二章"),
    ]
    html = _html(issues=issues)
    s42 = _section(html, "4.2 样式偏离明细", "<h3>4.3")
    # 段序按章归组，章名各出现一次。
    assert "第一章：段序 3、段序 5" in s42, s42
    assert "第二章：段序 9" in s42, s42
    assert s42.count("第一章") == 1, s42
