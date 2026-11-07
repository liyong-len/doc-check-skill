from manifest import build_manifest


def test_build_manifest_records_failures(tmp_path):
    docs = [{"file": "a.docx", "type": "docx", "sha256": "x" * 64,
             "stats": {"paragraphs": 1, "tables": 0, "pages": 0, "words": 10,
                       "rows": 0, "sheets": 0}}]
    failures = [{"file": "b.pdf", "path": "b.pdf", "reason": "需 OCR，当前不支持"}]
    m = build_manifest(docs, failures, "standard", tmp_path)
    assert m["depth"] == "standard"
    assert len(m["documents"]) == 1
    assert m["failures"][0]["file"] == "b.pdf"
    assert m["script_version"]
