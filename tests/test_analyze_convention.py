from analyze import analyze


def _doc(name, blocks):
    return {
        "file": name, "type": "docx", "sha256": "0" * 64, "title": "",
        "stats": {"paragraphs": len(blocks), "tables": 0, "pages": 1,
                  "words": 100, "rows": 0, "sheets": 0},
        "sections": [], "blocks": blocks,
        "entities": [], "citations": [], "numbers": [], "notes": [],
    }


def _p(text):
    return {"index": 0, "kind": "paragraph", "text": text, "style": None,
            "section_path": "第一章"}


def _cats(result):
    return [i["category"] for i in result["issues"]]


def test_heading_numbering_systems_mixed():
    docs = [_doc("a.docx", [
        _p("第一章 总则"),
        _p("一、总体要求"),
        _p("1. 适用范围"),
        _p("（一）背景说明"),
    ])]
    result = analyze(docs)
    issue = next(i for i in result["issues"] if i["category"] == "标题层级体例")
    assert "编号体系" in issue["description"]


def test_figure_caption_styles_mixed():
    docs = [_doc("a.docx", [
        _p("如图1-1所示"),
        _p("如图 1-2 所示"),
        _p("如图1.3所示"),
    ])]
    result = analyze(docs)
    assert "图表题注体例" in _cats(result)


def test_citation_marker_styles_mixed():
    docs = [_doc("a.docx", [
        _p("相关依据[1]说明"),
        _p("相关规定（2）明确"),
        _p("文献[3]指出"),
    ])]
    result = analyze(docs)
    assert "引用标记" in _cats(result)


def test_currency_unit_mixed():
    docs = [_doc("a.docx", [
        _p("合同金额 120 万元。"),
        _p("本次费用 3000 元。"),
    ])]
    result = analyze(docs)
    assert "数字与单位" in _cats(result)


def test_date_format_mixed():
    docs = [_doc("a.docx", [
        _p("签署日期 2024年1月1日。"),
        _p("生效日期 2024-01-01。"),
    ])]
    result = analyze(docs)
    assert "数字与单位" in _cats(result)


def test_uniform_document_has_no_convention_issue():
    docs = [_doc("a.docx", [
        _p("1. 适用范围"),
        _p("如图1-1所示"),
        _p("依据[1]说明"),
    ])]
    result = analyze(docs)
    assert _cats(result) == []


def _table(rows):
    return {
        "index": 0, "kind": "table", "text": "",
        "rows": [[{"text": c, "style": {"bold": b}} for c, b in row]
                 for row in rows],
    }


def test_table_header_style_inconsistent():
    doc = _doc("a.docx", [])
    doc["blocks"] = [
        _table([[("项目", True), ("数量", True)], [("设备", False), ("10", False)]]),
        _table([[("名称", True), ("数量", True)], [("设备", False), ("10", False)]]),
        _table([[("序号", False), ("数量", False)], [("设备", False), ("10", False)]]),
    ]
    result = analyze([doc])
    assert "表格体例" in _cats(result)


def test_list_numbering_style_mixed():
    doc = _doc("a.docx", [])
    doc["blocks"] = [
        {"index": 0, "kind": "paragraph", "text": "1. 第一项", "style": None,
         "section_path": "第一章", "list_numbered": True},
        {"index": 1, "kind": "paragraph", "text": "2. 第二项", "style": None,
         "section_path": "第一章", "list_numbered": True},
        {"index": 2, "kind": "paragraph", "text": "一、第三项", "style": None,
         "section_path": "第一章", "list_numbered": True},
    ]
    result = analyze([doc])
    assert "列表与编号" in _cats(result)


def test_undefined_abbreviation_flagged():
    doc = _doc("a.docx", [
        _p("本项目严格执行 GB 标准执行。"),
    ])
    result = analyze([doc])
    issue = next(i for i in result["issues"] if i["category"] == "术语与缩写")
    assert "GB" in issue["description"]


def test_defined_abbreviation_not_flagged():
    doc = _doc("a.docx", [
        _p("国家标准（GB）为行业通用标准。"),
    ])
    result = analyze([doc])
    assert [i for i in result["issues"] if i["category"] == "术语与缩写"] == []
