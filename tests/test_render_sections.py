from render import build_html


def _consistency():
    return {
        "style_profile": {
            "font_ea": {"label": "中文字体", "dominant": "宋体", "count": 40, "total": 42},
            "size_pt": {"label": "字号", "dominant": 12.0, "count": 40, "total": 42},
        },
        "issues": [],
        "entities": {
            "names": [
                {"name": "北京华信科技有限公司", "core": "华信科技",
                 "count": 3, "files": ["a.docx", "b.docx"]},
            ],
            "variants": [{"core": "华信科技",
                          "names": ["北京华信科技有限公司", "北京华信科技有限责任公司"]}],
        },
        "stats": {"documents": 2, "issues": 0},
    }


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


def _finding(category, severity="P2", confidence="疑似 · 需人工核实"):
    return {
        "id": "d" * 16, "severity": severity, "category": category,
        "detector": "llm", "confidence": confidence, "file": "a.docx",
        "locator": {"type": "paragraph", "index": 3, "section_path": "第一章"},
        "quote": "缺少资质证明材料", "description": "描述", "suggestion": "补充",
    }


def test_section4_style_profile_table():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": [], "baseline_diff": None,
    })
    assert "一致性差异" in html
    assert "中文字体" in html
    assert "宋体" in html


def test_section4_entity_variants_table():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": [], "baseline_diff": None,
    })
    assert "主体名" in html
    assert "北京华信科技有限责任公司" in html


def test_section5_todo_list():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": [_finding("待补充内容")], "baseline_diff": None,
    })
    assert "待补充与待核实" in html
    assert "缺少资质证明材料" in html


def test_section6_absent_without_baseline():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": [], "baseline_diff": None,
    })
    assert "复查对比" not in html


def test_section6_present_with_baseline():
    diff = {
        "findings": {
            "new": [_finding("错别字")],
            "fixed": [_finding("主体名称")],
            "unchanged": [],
        },
        "files": [{"file": "a.docx", "old_sha": "x", "new_sha": "y", "changed": True}],
    }
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": [], "baseline_diff": diff,
    })
    assert "复查对比" in html
    assert "新增" in html and "已修复" in html
    assert "文件已修改" in html


def test_section7_appendix_has_rules_and_fingerprints():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": [], "baseline_diff": None,
    })
    assert "附录" in html
    assert "检查规则" in html
    assert "c" * 64 in html
