import pytest

from extractors import extract_document
from extractors.text import extract_text


def test_extract_text_md_headings_and_table(tmp_path):
    p = tmp_path / "a.md"
    p.write_text(
        "# 投标文件\n\n## 技术方案\n\n正文内容。\n\n| 项目 | 数量 |\n| --- | --- |\n| 设备 | 10 |\n",
        encoding="utf-8",
    )
    doc = extract_text(p)
    assert doc["type"] == "md"
    paths = [s["path"] for s in doc["sections"]]
    assert "投标文件/技术方案" in paths
    assert any(b["kind"] == "table" for b in doc["blocks"])


def test_extract_text_txt_has_no_style(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("纯文本内容。\n", encoding="utf-8")
    doc = extract_text(p)
    assert doc["type"] == "txt"
    assert doc["blocks"][0]["style"] is None


def test_extract_document_dispatches_by_suffix(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("# 标题\n", encoding="utf-8")
    doc = extract_document(p)
    assert doc["type"] == "md"


def test_extract_document_rejects_unsupported_suffix(tmp_path):
    p = tmp_path / "a.zzz"
    p.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        extract_document(p)
