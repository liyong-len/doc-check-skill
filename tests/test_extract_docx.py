import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from extractors.docx import extract_docx


def _make_doc(tmp_path):
    d = docx.Document()
    d.add_heading("投标文件", level=1)
    d.add_heading("技术方案", level=2)
    p = d.add_paragraph("本公司具备相关资质。")
    run = p.runs[0]
    run.font.size = Pt(10.5)
    run.font.name = "Times New Roman"
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text = "项目"
    t.cell(0, 1).text = "数量"
    t.cell(1, 0).text = "设备"
    t.cell(1, 1).text = "10"
    path = tmp_path / "a.docx"
    d.save(str(path))
    return path


def test_extract_docx_basic_structure(tmp_path):
    doc = extract_docx(_make_doc(tmp_path))
    assert doc["type"] == "docx"
    assert doc["stats"]["tables"] == 1
    assert doc["stats"]["paragraphs"] >= 3
    assert doc["sha256"] and len(doc["sha256"]) == 64


def test_extract_docx_sections_and_blocks(tmp_path):
    doc = extract_docx(_make_doc(tmp_path))
    paths = [s["path"] for s in doc["sections"]]
    assert "投标文件/技术方案" in paths
    texts = [b.get("text", "") for b in doc["blocks"]]
    assert "本公司具备相关资质。" in texts
    assert any(b["kind"] == "table" for b in doc["blocks"])


def test_extract_docx_reads_run_size_and_font(tmp_path):
    doc = extract_docx(_make_doc(tmp_path))
    para = next(
        b for b in doc["blocks"]
        if b.get("text") == "本公司具备相关资质。"
    )
    assert para["style"]["size_pt"] == 10.5
    assert para["style"]["font_latin"] == "Times New Roman"
    assert para["style"]["confidence"] == "high"


def test_extract_docx_heading_level_parsed(tmp_path):
    doc = extract_docx(_make_doc(tmp_path))
    headings = [b for b in doc["blocks"] if b["kind"] == "paragraph" and b["style"]["is_heading"]]
    levels = sorted({h["style"]["heading_level"] for h in headings})
    assert levels == [1, 2]


def test_extract_docx_align_uses_xml_value(tmp_path):
    d = docx.Document()
    p = d.add_paragraph("两端对齐段落。")
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    path = tmp_path / "align.docx"
    d.save(str(path))
    doc = extract_docx(path)
    para = next(b for b in doc["blocks"] if b.get("text") == "两端对齐段落。")
    assert para["style"]["align"] == "both"


def test_extract_docx_exact_line_spacing_is_ratio(tmp_path):
    d = docx.Document()
    p = d.add_paragraph("固定行距段落。")
    p.paragraph_format.line_spacing = Pt(18)
    path = tmp_path / "spacing.docx"
    d.save(str(path))
    doc = extract_docx(path)
    para = next(b for b in doc["blocks"] if b.get("text") == "固定行距段落。")
    assert para["style"]["line_spacing"] == 1.5
