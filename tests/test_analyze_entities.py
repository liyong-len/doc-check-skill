from analyze import analyze


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


def test_name_variant_mismatch_is_p1():
    docs = [_doc("a.docx", [
        "本项目由北京华信科技有限公司负责。",
        "北京华信科技有限责任公司将提供支持。",
    ])]
    result = analyze(docs)
    issue = next(i for i in result["issues"] if i["category"] == "主体名称")
    assert issue["severity"] == "P1"
    assert issue["confidence"] == "确定"


def test_two_entities_in_one_file_flagged_p0():
    docs = [_doc("a.docx", [
        "北京华信科技有限公司为主体。",
        "上海远大信息技术有限公司为协作方。",
    ])]
    result = analyze(docs)
    issue = next(i for i in result["issues"] if i["category"] == "主体串写")
    assert issue["severity"] == "P0"
    assert issue["confidence"] == "疑似 · 需人工核实"


def test_entity_summary_returned():
    docs = [_doc("a.docx", ["北京华信科技有限公司负责本项目。"])]
    result = analyze(docs)
    names = [n["name"] for n in result["entities"]["names"]]
    assert "北京华信科技有限公司" in names
    assert result["entities"]["names"][0]["count"] == 1
    assert result["entities"]["names"][0]["files"] == ["a.docx"]


def test_no_entity_no_issue():
    docs = [_doc("a.docx", ["本段落不含任何公司名称。"])]
    result = analyze(docs)
    assert [i for i in result["issues"] if i["category"] in ("主体名称", "主体串写")] == []


def test_leading_weak_connector_is_not_a_second_entity():
    # 「与上海远大信息技术有限公司」与「上海远大信息技术有限公司」是同一主体，
    # 不能触发混主体，也不能触发写法不统一
    docs = [_doc("a.docx", [
        "本项目与上海远大信息技术有限公司共同承担。",
        "上海远大信息技术有限公司负责实施。",
    ])]
    result = analyze(docs)
    assert [i for i in result["issues"] if i["category"] in ("主体名称", "主体串写")] == []


def test_file_name_distinguishes_only_the_entity_it_names():
    # 文件名里出现了其中一个主体，只说明那个主体被显式区分了；
    # 文件里另一个主体仍然没有任何依据，仍要报疑似混主体
    doc = _doc("北京华信科技有限公司投标文件.docx", [
        "北京华信科技有限公司为主体。",
        "上海远大信息技术有限公司为协作方。",
    ])
    result = analyze([doc])
    issues = [i for i in result["issues"] if i["category"] == "主体串写"]
    assert len(issues) == 1
    assert "上海远大信息技术有限公司" in issues[0]["description"]


def test_section_heading_distinguishes_only_the_entity_it_names():
    doc = _doc("a.docx", [
        "北京华信科技有限公司为主体。",
        "上海远大信息技术有限公司为协作方。",
    ])
    doc["sections"] = [{"path": "上海远大信息技术有限公司", "level": 1,
                        "heading": "上海远大信息技术有限公司", "start": 0, "end": 1}]
    result = analyze([doc])
    issues = [i for i in result["issues"] if i["category"] == "主体串写"]
    assert len(issues) == 1
    assert "北京华信科技有限公司" in issues[0]["description"]


def test_no_p0_when_header_names_every_entity():
    # 文件名与章节标题把两个主体都点明了，才真的无从怀疑
    doc = _doc("北京华信科技有限公司投标文件.docx", [
        "北京华信科技有限公司为主体。",
        "上海远大信息技术有限公司为协作方。",
    ])
    doc["sections"] = [{"path": "上海远大信息技术有限公司", "level": 1,
                        "heading": "上海远大信息技术有限公司", "start": 0, "end": 1}]
    result = analyze([doc])
    assert [i for i in result["issues"] if i["category"] == "主体串写"] == []


def test_entity_in_a_table_cell_is_found():
    # 确定性层不能只看段落：第二家公司只在表格里出现过，
    # 只看段落就会完全查不到（模型层却能从表格里抽到，两层口径不一致）
    doc = _doc("a.docx", ["本文件由北京华信科技有限公司编制。"])
    doc["blocks"].append({
        "index": 1, "kind": "table", "text": "",
        "rows": [[{"text": "协作方", "style": {}},
                  {"text": "上海远大信息技术有限公司", "style": {}}]],
    })
    result = analyze([doc])
    names = [n["name"] for n in result["entities"]["names"]]
    assert "上海远大信息技术有限公司" in names
    issues = [i for i in result["issues"] if i["category"] == "主体串写"]
    assert len(issues) == 1
