import json

from render import build_html


def _consistency():
    return {
        "style_profile": {
            "font_ea": {"label": "中文字体", "dominant": "宋体", "count": 40, "total": 42},
        },
        "issues": [
            {
                "id": "a" * 16, "severity": "P0", "category": "主体串写",
                "detector": "deterministic", "confidence": "疑似 · 需人工核实",
                "file": "a.docx", "locator": {"type": "file"},
                "quote": "北京华信科技有限公司",
                "description": "出现两个主体", "suggestion": "确认归属",
            }
        ],
        "entities": {
            "names": [
                {"name": "北京华信科技有限公司", "core": "华信科技",
                 "count": 3, "files": ["a.docx", "b.docx"]},
            ],
            "variants": [{"core": "华信科技",
                          "names": ["北京华信科技有限公司", "北京华信科技有限责任公司"]}],
        },
        "stats": {"documents": 2, "issues": 1},
    }


def _findings():
    return [
        {
            "id": "b" * 16, "severity": "P1", "category": "前后矛盾",
            "detector": "llm", "confidence": "疑似 · 需人工核实",
            "file": "a.docx",
            "locator": {"type": "paragraph", "index": 7, "section_path": "第二章"},
            "quote": "工期为 90 日历天",
            "description": "与前文 60 天矛盾", "suggestion": "统一为 60 天",
        }
    ]


def _manifest():
    return {
        "script_version": "0.1.0", "depth": "standard",
        "generated_at": "2026-11-07T10:00:00+08:00",
        "documents": [
            {"file": "a.docx", "type": "docx", "sha256": "c" * 64,
             "stats": {"paragraphs": 100, "tables": 2, "pages": 12,
                       "words": 5000, "rows": 0, "sheets": 0},
             "entities": ["北京华信科技有限公司"], "notes": []},
        ],
        "failures": [
            {"file": "b.pdf", "path": "b.pdf", "reason": "需 OCR，当前不支持"},
        ],
    }


def test_build_html_contains_core_sections():
    html = build_html({
        "manifest": _manifest(),
        "consistency": _consistency(),
        "findings": _findings(),
        "baseline_diff": None,
    })
    for marker in ["检查范围与未能检查项", "结论概览", "硬伤速览", "按文件明细"]:
        assert marker in html, marker


def test_build_html_escapes_content():
    html = build_html({
        "manifest": _manifest(),
        "consistency": _consistency(),
        "findings": [{
            "id": "c" * 16, "severity": "P2", "category": "错别字",
            "detector": "llm", "confidence": "确定", "file": "<script>x</script>",
            "locator": {"type": "file"}, "quote": "<b>bold</b>",
            "description": "描述", "suggestion": "建议",
        }],
        "baseline_diff": None,
    })
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html


def test_build_html_shows_p0_in_quick_view():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": _findings(), "baseline_diff": None,
    })
    assert "主体串写" in html
    assert "P0" in html


def test_build_html_includes_limitations_statement():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": _findings(), "baseline_diff": None,
    })
    assert "未核实外部事实" in html


def test_build_html_no_external_resources():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": _findings(), "baseline_diff": None,
    })
    assert "http://" not in html
    assert "https://" not in html
    assert "<link" not in html


def test_build_html_groups_issues_by_file():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": _findings(), "baseline_diff": None,
    })
    assert "a.docx" in html
    assert "工期为 90 日历天" in html


def test_build_html_escapes_locator_text():
    """locator 的 section_path 来自文档标题，必须转义后输出。"""
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": [{
            "id": "e" * 16, "severity": "P2", "category": "错别字",
            "detector": "llm", "confidence": "确定", "file": "a.docx",
            "locator": {"type": "paragraph", "index": 3,
                        "section_path": "<script>alert(1)</script>"},
            "quote": "正文", "description": "描述", "suggestion": "建议",
        }],
        "baseline_diff": None,
    })
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
