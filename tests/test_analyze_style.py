from analyze import analyze


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
        "bold": False, "italic": False, "align": "both",
        "indent_left_pt": 0.0, "indent_first_pt": 24.0, "line_spacing": 1.5,
        "space_before_pt": 0.0, "space_after_pt": 0.0, "style_name": "正文",
        "is_heading": False, "heading_level": 0, "list_numbered": False,
        "confidence": "high",
    }
    base.update(kw)
    return base


def _para(text, style):
    return {"index": 0, "kind": "paragraph", "text": text, "style": style,
            "section_path": "第一章"}


def test_analyze_reports_font_deviation():
    docs = [
        _doc("a.docx", [
            _para("正常段落一", _style()),
            _para("正常段落二", _style()),
            _para("异常字体段落", _style(font_ea="仿宋")),
        ])
    ]
    result = analyze(docs)
    cats = [i["category"] for i in result["issues"]]
    assert "字体一致性" in cats
    issue = next(i for i in result["issues"] if i["category"] == "字体一致性")
    assert issue["file"] == "a.docx"
    assert issue["severity"] == "P2"
    assert issue["detector"] == "deterministic"


def test_analyze_no_issue_when_all_same():
    docs = [_doc("a.docx", [_para(f"段落{i}", _style()) for i in range(5)])]
    result = analyze(docs)
    assert result["issues"] == []


def test_analyze_reports_line_spacing_deviation():
    docs = [
        _doc("a.docx", [
            _para("正常", _style()),
            _para("正常", _style()),
            _para("行距不同", _style(line_spacing=1.0)),
        ])
    ]
    result = analyze(docs)
    assert any(i["category"] == "段落格式一致性" for i in result["issues"])


def test_analyze_ignores_low_confidence_styles():
    docs = [_doc("a.pdf", [_para("页内容", _style(confidence="low", font_ea=None))])]
    result = analyze(docs)
    assert result["issues"] == []
