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
