import json
from pathlib import Path

import docx

from prepare import main, prepare


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


def test_prepare_ocr_reason_does_not_repeat_need_ocr():
    """扫描件原因只说一次「需 OCR」，其余说明不能重复同一句话。"""
    from prepare import _ocr_failure
    doc = {
        "file": "scan.pdf", "path": "scan.pdf",
        "notes": [
            "第 1 页无文本层，疑似扫描件，需 OCR",
            "全文无文本层，疑似扫描件，需 OCR，当前不做内容判定",
        ],
        "blocks": [{"kind": "paragraph", "text": ""}],
    }
    failure, has_text = _ocr_failure(doc)
    reason = failure["reason"]
    assert reason.count("需 OCR") == 1, reason
    assert "第 1 页无文本层" in reason
    assert "全文无文本层" not in reason
    assert "未做任何内容判定" in reason


def test_prepare_ocr_reason_lists_pages_of_partial_scan():
    """部分有文本层的文档要点名缺文本层的页。"""
    from prepare import _ocr_failure
    doc = {
        "file": "mixed.pdf", "path": "mixed.pdf",
        "notes": [
            "第 2 页无文本层，疑似扫描件，需 OCR",
            "第 3 页无文本层，疑似扫描件，需 OCR",
        ],
        "blocks": [{"kind": "paragraph", "text": "有文字"}],
    }
    failure, has_text = _ocr_failure(doc)
    reason = failure["reason"]
    assert reason.count("需 OCR") == 1, reason
    assert "第 2 页无文本层" in reason
    assert "第 3 页无文本层" in reason
    assert "该文档无文本层" not in reason


def test_prepare_excludes_textless_pdf_from_documents(tmp_path, monkeypatch):
    """无文本层的扫描件不得被当成已检查文档——这是整批任务的核心要求。"""
    import prepare as prepare_module

    scanned = {
        "file": "scan.pdf", "path": str(tmp_path / "scan.pdf"), "type": "pdf",
        "sha256": "0" * 64, "title": "",
        "stats": {"paragraphs": 1, "tables": 0, "pages": 1, "words": 0,
                  "rows": 0, "sheets": 0},
        "sections": [],
        "blocks": [{"index": 0, "kind": "paragraph", "text": "",
                    "section_path": "第 1 页", "style": {}}],
        "entities": [], "citations": [], "numbers": [],
        "notes": ["第 1 页无文本层，疑似扫描件，需 OCR"],
    }
    monkeypatch.setattr(prepare_module, "extract_document", lambda path: scanned)

    src = tmp_path / "scan.pdf"
    src.write_bytes(b"%PDF-1.4")
    work = tmp_path / "work"
    result = prepare([src], "standard", work)

    manifest = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
    docs = json.loads((work / "docs.json").read_text(encoding="utf-8"))
    assert manifest["failures"][0]["file"] == "scan.pdf"
    assert "需 OCR，当前不支持" in manifest["failures"][0]["reason"]
    assert [d["file"] for d in docs["documents"]] == []
    assert [d["file"] for d in manifest["documents"]] == []
    assert result["documents"] == 0
    assert result["failure_count"] == 1


def test_prepare_records_missing_file_as_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    work = tmp_path / "work"
    result = prepare([Path("missing.docx")], "standard", work)
    assert result["documents"] == 0
    assert result["failures"][0]["file"] == "missing.docx"
    assert result["failures"][0]["reason"] == "文件不存在"
    assert Path(result["failures"][0]["path"]).is_absolute()


def test_main_returns_zero_and_prints_stats(tmp_path, capsys):
    src = _make_docx(tmp_path / "a.docx")
    code = main(["--files", str(src), "--depth", "quick",
                 "--work", str(tmp_path / "work")])
    out = capsys.readouterr().out
    assert code == 0
    assert "已抽取 1 份文档" in out
    assert (tmp_path / "work" / "manifest.json").exists()


def test_main_returns_nonzero_when_nothing_checked(tmp_path):
    code = main(["--files", str(tmp_path / "missing.docx"),
                 "--work", str(tmp_path / "work")])
    assert code == 1


def test_same_basename_files_get_distinct_ids(tmp_path):
    # 两个目录下的 report.docx：清单里要有两条不同记录，
    # 分片 id 不能撞车，per_file 不能丢一份
    a_dir = tmp_path / "a"
    b_dir = tmp_path / "b"
    a_dir.mkdir()
    b_dir.mkdir()
    a = _make_docx(a_dir / "report.docx", "本文件由北京华信科技有限公司编制。")
    b = _make_docx(b_dir / "report.docx", "本文件由上海远大信息技术有限公司编制。")
    work = tmp_path / "work"
    prepare([a, b], "standard", work)
    manifest = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
    files = [d["file"] for d in manifest["documents"]]
    assert len(files) == 2
    assert len(set(files)) == 2
    chunks = json.loads((work / "chunks.json").read_text(encoding="utf-8"))
    ids = [c["chunk_id"] for c in chunks["chunks"]]
    assert len(ids) == len(set(ids))
    cons = json.loads((work / "consistency.json").read_text(encoding="utf-8"))
    assert len(cons["entities"]["per_file"]) == 2
