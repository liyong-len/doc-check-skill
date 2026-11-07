import json

import docx

from prepare import prepare


def _make_docx(path, text="正文内容。"):
    d = docx.Document()
    d.add_heading("标题", level=1)
    d.add_paragraph(text)
    d.save(str(path))
    return path


def test_prepare_writes_four_json_files(tmp_path):
    src = _make_docx(tmp_path / "a.docx")
    work = tmp_path / "work"
    result = prepare([src], "standard", work)
    for name in ("docs.json", "consistency.json", "chunks.json", "manifest.json"):
        assert (work / name).exists(), name
    assert result["documents"] == 1


def test_prepare_records_failure_and_continues(tmp_path):
    src = _make_docx(tmp_path / "a.docx")
    bad = tmp_path / "b.docx"
    bad.write_text("not a docx", encoding="utf-8")
    work = tmp_path / "work"
    result = prepare([src, bad], "standard", work)
    assert result["documents"] == 1
    assert result["failures"][0]["file"] == "b.docx"
    assert result["failures"][0]["reason"]


def test_prepare_docs_json_has_blocks(tmp_path):
    src = _make_docx(tmp_path / "a.docx")
    work = tmp_path / "work"
    prepare([src], "standard", work)
    docs = json.loads((work / "docs.json").read_text(encoding="utf-8"))
    assert docs["documents"][0]["blocks"]


def test_prepare_consistency_json_has_issues_list(tmp_path):
    src = _make_docx(tmp_path / "a.docx")
    work = tmp_path / "work"
    prepare([src], "standard", work)
    cons = json.loads((work / "consistency.json").read_text(encoding="utf-8"))
    assert "issues" in cons
    assert "style_profile" in cons


def test_prepare_promotes_ocr_document_to_failure():
    from prepare import _ocr_failure
    doc = {
        "file": "scan.pdf", "path": "scan.pdf",
        "notes": ["第 1 页无文本层，疑似扫描件，需 OCR"],
        "blocks": [{"kind": "paragraph", "text": ""}],
    }
    failure, has_text = _ocr_failure(doc)
    assert failure is not None
    assert "需 OCR，当前不支持" in failure["reason"]
    assert has_text is False


def test_prepare_keeps_partially_scanned_document():
    from prepare import _ocr_failure
    doc = {
        "file": "mixed.pdf", "path": "mixed.pdf",
        "notes": ["第 2 页无文本层，疑似扫描件，需 OCR"],
        "blocks": [{"kind": "paragraph", "text": "有文字"}],
    }
    failure, has_text = _ocr_failure(doc)
    assert failure is not None
    assert has_text is True
