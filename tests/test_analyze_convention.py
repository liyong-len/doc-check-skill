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
    # 「1.1 式」与「（一）式」都在第 4 层，同层混用才是体例不一致
    docs = [_doc("a.docx", [
        _p("第一章 总则"),
        _p("一、总体要求"),
        _p("1. 适用范围"),
        _p("（一）背景说明"),
        _p("1.1 实施进度"),
    ])]
    result = analyze(docs)
    issue = next(i for i in result["issues"] if i["category"] == "标题层级体例")
    assert "编号体系" in issue["description"]


def test_standard_four_level_structure_is_not_flagged():
    # 标准的四级结构不是体例不一致，不能每份文档都报
    docs = [_doc("a.docx", [
        _p("第一章 总则"),
        _p("一、总体要求"),
        _p("1. 适用范围"),
        _p("（一）背景说明"),
    ])]
    result = analyze(docs)
    assert [i for i in result["issues"] if i["category"] == "标题层级体例"] == []


def test_heading_level_jump_is_flagged():
    doc = _doc("a.docx", [])
    doc["blocks"] = [
        {"index": 0, "kind": "paragraph", "text": "第一章 总则", "section_path": "",
         "style": {"is_heading": True, "heading_level": 1}},
        {"index": 1, "kind": "paragraph", "text": "3.1 实施", "section_path": "",
         "style": {"is_heading": True, "heading_level": 3}},
    ]
    result = analyze([doc])
    issue = next(i for i in result["issues"] if i["category"] == "标题层级体例")
    assert "跳级" in issue["description"]


def test_figure_numbering_gap_is_flagged():
    docs = [_doc("a.docx", [
        _p("图1-1 总体架构"),
        _p("图1-3 数据流"),
    ])]
    result = analyze(docs)
    issue = next(i for i in result["issues"] if i["category"] == "图表题注体例")
    assert "缺号" in issue["description"]


def test_caption_number_not_followed_by_counter_is_ignored():
    # 「见图 3 节」「（2）个标段」「（2024）」都不是编号
    docs = [_doc("a.docx", [
        _p("见图 3 节可知。"),
        _p("本项目分为（2）个标段。"),
        _p("签署时间（2024）。"),
    ])]
    result = analyze(docs)
    cats = [i["category"] for i in result["issues"]]
    assert "图表题注体例" not in cats
    assert "引用标记" not in cats


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


def test_currency_regex_only_matches_yuan():
    # 「3单元」「100美元」不是人民币金额，不该触发货币混用
    docs = [_doc("a.docx", [
        _p("本项目分为 3单元。"),
        _p("合同金额 100美元。"),
    ])]
    result = analyze(docs)
    assert "数字与单位" not in _cats(result)


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


def test_two_abbreviations_in_one_paragraph_have_distinct_ids():
    # 同段里的两个缩写是两条不同的问题，不能落到同一个 finding id 上
    doc = _doc("a.docx", [
        _p("本项目由 GB 与 CTO 共同负责。"),
    ])
    result = analyze([doc])
    issues = [i for i in result["issues"] if i["category"] == "术语与缩写"]
    assert len(issues) == 2
    assert len({i["id"] for i in issues}) == 2


# --- 复查轮次：图表题注与引用标记的 Critical 缺陷 ---


def test_figure_and_table_number_series_are_separate():
    # 图与表各是一套编号序列：第 3 章有图3-1与表3-3是正常的，
    # 合并成一个序列就会报出「缺号 2」这种假问题
    docs = [_doc("a.docx", [
        _p("见图3-1 示意图"),
        _p("见表3-3 明细表"),
    ])]
    result = analyze(docs)
    assert [i for i in result["issues"] if i["category"] == "图表题注体例"] == []


def test_figure_and_table_caption_styles_are_not_mixed():
    # 「图3-1 流程图」与「表3-1 清单」是正确写法，不是体例不一致
    docs = [_doc("a.docx", [
        _p("图3-1 流程图"),
        _p("表3-1 清单"),
    ])]
    result = analyze(docs)
    assert [i for i in result["issues"] if i["category"] == "图表题注体例"] == []


def test_space_in_caption_is_a_distinct_writing():
    # 规范 §5.3 的例子：「图1-1」与「图 1-1」是两种写法，要能查出来
    docs = [_doc("a.docx", [
        _p("图1-1 流程图"),
        _p("图 1-1 架构图"),
    ])]
    result = analyze(docs)
    issues = [i for i in result["issues"] if i["category"] == "图表题注体例"]
    assert len(issues) == 1
    assert "2 种写法" in issues[0]["description"]


def test_chinese_enumeration_is_not_a_citation():
    # 「（1）」「（2）」是中文枚举序号，不是引用标记。
    # 与真的引用标记混在一起会报出「引用标记写法混用」这种假问题。
    docs = [_doc("a.docx", [
        _p("（1）投标文件应当包含资格证明文件。"),
        _p("（2）投标文件应当包含技术方案。"),
        _p("相关依据[1]说明本方案满足要求。"),
    ])]
    result = analyze(docs)
    assert [i for i in result["issues"] if i["category"] == "引用标记"] == []


def test_parenthesised_number_with_citation_context_is_a_citation():
    # 有引用引导词时，「（n）」仍算引用标记写法
    docs = [_doc("a.docx", [
        _p("相关规定见（1）。"),
        _p("相关依据[2]说明本方案满足要求。"),
    ])]
    result = analyze(docs)
    issues = [i for i in result["issues"] if i["category"] == "引用标记"]
    assert len(issues) == 1


def test_abbreviation_defined_in_a_table_is_not_reported():
    # 术语表常在表格里。只看段落就会把正文的 SLA 报成「未给出全称」
    doc = _doc("a.docx", [
        {"index": 0, "kind": "paragraph", "text": "本项目要求达到 SLA 水平。",
         "style": None, "section_path": "第一章"},
    ])
    doc["blocks"].insert(0, {
        "index": 0, "kind": "table", "text": "",
        "rows": [[{"text": "缩略语", "style": {}},
                  {"text": "全称", "style": {}}],
                 [{"text": "服务水平（SLA）", "style": {}},
                  {"text": "Service Level Agreement", "style": {}}]],
    })
    result = analyze([doc])
    assert [i for i in result["issues"] if i["category"] == "术语与缩写"] == []
