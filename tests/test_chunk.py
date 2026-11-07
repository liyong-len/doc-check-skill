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
