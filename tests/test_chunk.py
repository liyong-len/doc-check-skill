from chunk import DEPTH_PARAMS, build_chunks


def _doc(name, texts):
    blocks = [
        {"index": i, "kind": "paragraph", "text": t, "style": None,
         "section_path": "第一章/1.1 节"}
        for i, t in enumerate(texts)
    ]
    return {
        "file": name, "type": "docx", "sha256": "0" * 64, "title": "",
        "stats": {"paragraphs": len(blocks), "tables": 0, "pages": 1,
                  "words": 10, "rows": 0, "sheets": 0},
        "sections": [], "blocks": blocks,
        "entities": [], "citations": [], "numbers": [], "notes": [],
    }


def test_depth_params_defined():
    assert set(DEPTH_PARAMS) == {"quick", "standard", "deep"}
    assert DEPTH_PARAMS["deep"]["max_chars"] < DEPTH_PARAMS["standard"]["max_chars"]


def test_build_chunks_respects_max_chars():
    doc = _doc("a.docx", [f"第{i}段内容。" * 20 for i in range(20)])
    chunks = build_chunks([doc], "standard")
    assert chunks
    assert all(len(c["text"]) <= DEPTH_PARAMS["standard"]["max_chars"] + 200 for c in chunks)


def test_build_chunks_has_neighbors_and_hints():
    doc = _doc("a.docx", ["北京华信科技有限公司负责，金额 1,200.00 元，见[3]。",
                          "第二段。", "第三段。"])
    chunks = build_chunks([doc], "standard")
    first = chunks[0]
    assert "neighbors" in first
    assert "prev" in first["neighbors"] and "next" in first["neighbors"]
    assert "北京华信科技有限公司" in first["entities"]
    assert "1,200.00" in first["numbers"]
    assert "[3]" in first["citations"]


def test_chunk_has_section_path_and_file():
    doc = _doc("a.docx", ["内容。"])
    chunk = build_chunks([doc], "standard")[0]
    assert chunk["file"] == "a.docx"
    assert chunk["section_path"] == "第一章/1.1 节"
    assert chunk["chunk_id"].startswith("a.docx:")


def test_deep_mode_smaller_chunks():
    doc = _doc("a.docx", [f"第{i}段内容。" * 20 for i in range(20)])
    deep = build_chunks([doc], "deep")
    standard = build_chunks([doc], "standard")
    assert len(deep) > len(standard)


def test_build_chunks_neighbors_span_chunk_boundaries():
    """邻接上下文取自分片之外：前邻是上一分片的末块，后邻是下一分片的首块。"""
    texts = [f"BLOCK{i:02d}" + "x" * 990 for i in range(9)]
    doc = _doc("a.docx", texts)
    chunks = build_chunks([doc], "standard")
    assert len(chunks) == 3
    assert chunks[0]["text"].endswith(texts[2])
    assert chunks[1]["neighbors"]["prev"].endswith(texts[2])
    assert chunks[2]["text"].startswith(texts[6])
    assert chunks[1]["neighbors"]["next"].startswith(texts[6])


def test_build_chunks_splits_oversized_table():
    """xlsx 的一个 sheet 就是一个表格块，超长表格必须按行拆开。"""
    rows = [
        [{"text": f"单元格{i}-{j}", "style": {}} for j in range(3)]
        for i in range(200)
    ]
    doc = {
        "file": "b.xlsx", "type": "xlsx", "sha256": "0" * 64, "title": "",
        "stats": {"paragraphs": 0, "tables": 1, "pages": 1,
                  "words": 10, "rows": 200, "sheets": 1},
        "sections": [], "entities": [], "citations": [], "numbers": [],
        "notes": [],
        "blocks": [{"index": 0, "kind": "table", "text": "", "rows": rows,
                    "style": None, "section_path": "报价表"}],
    }
    chunks = build_chunks([doc], "deep")
    assert len(chunks) > 1
    limit = DEPTH_PARAMS["deep"]["max_chars"]
    assert all(len(c["text"]) <= limit + 200 for c in chunks)


def test_numbers_trim_trailing_punctuation():
    """「见 12.」的数字是 12，不是 12.。"""
    doc = _doc("a.docx", ["见 12.，另见 3.5 万元。"])
    chunk = build_chunks([doc], "standard")[0]
    assert "12" in chunk["numbers"]
    assert "12." not in chunk["numbers"]
