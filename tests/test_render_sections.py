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


# --- 复查修复轮新增 ---

def test_section0_lists_inferred_entity_names():
    manifest = _manifest()
    manifest["documents"][0]["entities"] = ["北京华信科技有限公司"]
    html = build_html({
        "manifest": manifest, "consistency": _consistency(),
        "findings": [], "baseline_diff": None,
    })
    assert "推断出的主体名" in html
    assert "北京华信科技有限公司" in html


def test_section3_opens_with_file_summary():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": [_finding("前后矛盾")], "baseline_diff": None,
    })
    assert "规模：" in html
    assert "主体名：" in html
    assert "5000 字" in html


def test_section5_todo_table_is_checkable_and_explains_why():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": [_finding("待补充内容")], "baseline_diff": None,
    })
    assert "☐" in html
    assert "为何需要" in html
    assert "缺失内容" in html


def test_section5_quick_depth_states_category_not_covered():
    manifest = _manifest()
    manifest["depth"] = "quick"
    html = build_html({
        "manifest": manifest, "consistency": _consistency(),
        "findings": [], "baseline_diff": None,
    })
    assert "未覆盖「待补充内容」这一类别" in html
    assert "未发现待补充内容" not in html


def test_section5_standard_depth_states_nothing_found():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": [], "baseline_diff": None,
    })
    assert "未发现待补充内容" in html


def test_section7_declares_depth_and_coverage():
    manifest = _manifest()
    manifest["depth"] = "quick"
    html = build_html({
        "manifest": manifest, "consistency": _consistency(),
        "findings": [], "baseline_diff": None,
    })
    assert "本次检查范围" in html
    assert "检查档位" in html
    assert "quick" in html
    assert "未覆盖" in html


def test_section4_variants_use_canonical_writings():
    """按规范写法判定变体：原文不同但规范写法相同不算变体。"""
    cons = _consistency()
    cons["entities"]["variants"] = [
        {"core": "远大信息",
         "names": ["与上海远大信息技术有限公司", "上海远大信息技术有限公司"],
         "canonicals": ["上海远大信息技术有限公司"]},
    ]
    html = build_html({
        "manifest": _manifest(), "consistency": cons,
        "findings": [], "baseline_diff": None,
    })
    assert "未发现同一主体的多种写法" in html


def test_section4_variants_list_multiple_canonicals():
    cons = _consistency()
    cons["entities"]["variants"] = [
        {"core": "远大信息",
         "names": ["上海远大信息技术有限公司", "上海远大信息有限责任公司"],
         "canonicals": ["上海远大信息技术有限公司", "上海远大信息有限责任公司"]},
    ]
    html = build_html({
        "manifest": _manifest(), "consistency": cons,
        "findings": [], "baseline_diff": None,
    })
    assert "上海远大信息技术有限公司" in html
    assert "上海远大信息有限责任公司" in html


def test_section6_distinguishes_added_removed_and_modified_files():
    diff = {
        "findings": {"new": [], "fixed": [], "unchanged": []},
        "files": [
            {"file": "a.docx", "old_sha": "x", "new_sha": "y", "changed": True},
            {"file": "b.docx", "old_sha": "", "new_sha": "z", "changed": True},
            {"file": "c.docx", "old_sha": "w", "new_sha": "", "changed": True},
        ],
    }
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": [], "baseline_diff": diff,
    })
    assert "已修改" in html
    assert "新增" in html
    assert "已删除" in html


def test_section4_2_headers_match_content():
    """§4.2 的列名要如实描述列内容。"""
    cons = _consistency()
    cons["issues"] = [{
        "id": "i" * 16, "severity": "P2", "category": "字体一致性",
        "detector": "deterministic", "confidence": "确定", "file": "a.docx",
        "locator": {"type": "paragraph", "index": 3},
        "quote": "本段正文摘录", "description": "本处为「黑体」，主流值为「宋体」",
        "suggestion": "统一改为「宋体」",
    }]
    html = build_html({
        "manifest": _manifest(), "consistency": cons,
        "findings": [], "baseline_diff": None,
    })
    # 取 §4.2 那一节里的表头行，逐格核对列名
    section = html.split("4.2 样式偏离明细")[1].split("<h3>4.3")[0]
    header = section.split("</thead>")[0]
    assert "<th>原文摘录</th>" in header
    assert "<th>说明</th>" in header
    assert "<th>实际情况</th>" not in header
    assert "<th>主流值</th>" not in header


def test_build_html_escapes_numeric_cells():
    """§4.1 / §4.4 的计数单元格也必须转义。"""
    cons = _consistency()
    cons["style_profile"]["font_ea"]["count"] = "<script>x</script>"
    cons["entities"]["names"][0]["count"] = "<script>y</script>"
    html = build_html({
        "manifest": _manifest(), "consistency": cons,
        "findings": [], "baseline_diff": None,
    })
    assert "<script>x</script>" not in html
    assert "<script>y</script>" not in html
    assert "&lt;script&gt;x&lt;/script&gt;" in html
    assert "&lt;script&gt;y&lt;/script&gt;" in html


def test_build_html_tolerates_non_dict_locator():
    """locator 不是字典时不得抛 AttributeError。"""
    html = build_html({
        "manifest": _manifest(),
        "consistency": {"style_profile": {}, "issues": [], "entities": {}, "stats": {}},
        "findings": [{
            "id": "j" * 16, "severity": "P2", "category": "错别字",
            "detector": "llm", "confidence": "确定", "file": "a.docx",
            "locator": "不是字典", "quote": "正文",
            "description": "描述", "suggestion": "建议",
        }],
        "baseline_diff": None,
    })
    assert "错别字" in html
