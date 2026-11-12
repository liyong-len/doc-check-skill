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


# --- 样式继承 ---

def test_extract_docx_resolves_alignment_from_style(tmp_path):
    """段落没直接写对齐方式时，取样式里的值。

    Normal 样式通常设了两端对齐。段落不写 = 继承 = 两端对齐，
    与另一段显式写「两端对齐」渲染结果完全一样。
    只看直接格式会把继承来的值当成「没设置」，
    于是「显式写了 both」被报成「单独设了 both」——看不见的差异。
    """
    d = docx.Document()
    normal = d.styles["Normal"]
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    inherited = d.add_paragraph("继承对齐方式的段落。")
    explicit = d.add_paragraph("显式写了两端对齐的段落。")
    explicit.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    path = tmp_path / "inherit_align.docx"
    d.save(str(path))

    doc = extract_docx(path)
    a = next(b for b in doc["blocks"] if b.get("text") == "继承对齐方式的段落。")
    b = next(b for b in doc["blocks"] if b.get("text") == "显式写了两端对齐的段落。")
    assert a["style"]["align"] == "both", a["style"]["align"]
    assert b["style"]["align"] == "both", b["style"]["align"]


def test_extract_docx_resolves_indent_from_style(tmp_path):
    """段落没直接写缩进时，取样式链上的值。"""
    d = docx.Document()
    normal = d.styles["Normal"]
    normal.paragraph_format.left_indent = Pt(21)
    normal.paragraph_format.first_line_indent = Pt(12)
    d.add_paragraph("继承缩进的段落。")
    path = tmp_path / "inherit_indent.docx"
    d.save(str(path))

    doc = extract_docx(path)
    para = next(b for b in doc["blocks"] if b.get("text") == "继承缩进的段落。")
    assert para["style"]["indent_left_pt"] == 21.0, para["style"]["indent_left_pt"]
    assert para["style"]["indent_first_pt"] == 12.0, para["style"]["indent_first_pt"]


def test_extract_docx_direct_format_wins_over_style(tmp_path):
    """段落自己写的格式优先于样式里的。"""
    d = docx.Document()
    normal = d.styles["Normal"]
    normal.paragraph_format.left_indent = Pt(21)
    p = d.add_paragraph("自己写了左缩进的段落。")
    p.paragraph_format.left_indent = Pt(45)
    path = tmp_path / "direct_indent.docx"
    d.save(str(path))

    doc = extract_docx(path)
    para = next(b for b in doc["blocks"] if b.get("text") == "自己写了左缩进的段落。")
    assert para["style"]["indent_left_pt"] == 45.0, para["style"]["indent_left_pt"]


def test_extract_docx_resolves_line_spacing_from_style(tmp_path):
    """段落没直接写行距时，取样式里的值。"""
    d = docx.Document()
    normal = d.styles["Normal"]
    normal.paragraph_format.line_spacing = 1.5
    d.add_paragraph("继承行距的段落。")
    path = tmp_path / "inherit_spacing.docx"
    d.save(str(path))

    doc = extract_docx(path)
    para = next(b for b in doc["blocks"] if b.get("text") == "继承行距的段落。")
    assert para["style"]["line_spacing"] == 1.5, para["style"]["line_spacing"]
