"""提交的样本必须与生成器产出的样本一致。

样本是二进制文件（docx/xlsx/pdf 是 zip 或带时间戳的容器），逐字节比对没有意义：
zip 里的时间戳每次生成都不一样。要比的是内容。
"""
from __future__ import annotations

import warnings
from pathlib import Path

import docx
import openpyxl
import pytest
from docx.oxml.ns import qn

import make_samples

SAMPLES = Path(__file__).resolve().parent / "samples"


def _docx_content(path: Path) -> list[str]:
    """docx 的段落与表格单元格文本。"""
    d = docx.Document(str(path))
    out = [p.text for p in d.paragraphs]
    for table in d.tables:
        for row in table.rows:
            out.append(" | ".join(c.text for c in row.cells))
    return out


def _xlsx_content(path: Path) -> list[tuple]:
    """xlsx 的非空单元格：工作表、坐标、值、数字格式。"""
    wb = openpyxl.load_workbook(str(path))
    out = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is not None:
                    out.append(
                        (ws.title, cell.coordinate, str(cell.value), cell.number_format)
                    )
    return out


def _pdf_content(path: Path) -> list[str]:
    """pdf 每一页抽出来的文本。"""
    import pdfplumber

    out = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            out.append(page.extract_text() or "")
    return out


def _east_asia_font(run) -> str | None:
    """run 的中文字体。python-docx 的 run.font.name 只写 ascii/hAnsi。"""
    rpr = run._element.rPr
    if rpr is None:
        return None
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        return None
    return fonts.get(qn("w:eastAsia"))


def _size_pt(run) -> float | None:
    return None if run.font.size is None else run.font.size.pt


def test_committed_samples_exist():
    for name in ["sample_company.docx", "sample_price.xlsx", "sample_note.md",
                 "sample_notice.pdf"]:
        assert (SAMPLES / name).exists(), name


def test_committed_docx_matches_generator(tmp_path):
    fresh = tmp_path / "sample_company.docx"
    make_samples.make_docx(fresh)
    assert _docx_content(fresh) == _docx_content(SAMPLES / "sample_company.docx")


def test_committed_xlsx_matches_generator(tmp_path):
    fresh = tmp_path / "sample_price.xlsx"
    make_samples.make_xlsx(fresh)
    assert _xlsx_content(fresh) == _xlsx_content(SAMPLES / "sample_price.xlsx")


def test_committed_md_matches_generator(tmp_path):
    fresh = tmp_path / "sample_note.md"
    make_samples.make_md(fresh)
    assert fresh.read_text(encoding="utf-8") == (
        SAMPLES / "sample_note.md"
    ).read_text(encoding="utf-8")


def test_committed_pdf_matches_generator(tmp_path):
    """PDF 样本的正文必须与生成器一致。

    PDF 容器里带创建时间，逐字节比对没有意义，比的是抽出来的文本。
    """
    try:
        import reportlab  # noqa: F401
    except ImportError:
        warnings.warn(
            "reportlab 没装，PDF 样本的重生成比对被跳过。"
            "reportlab 是开发依赖（requirements-dev.txt），"
            "只装 requirements.txt 的环境跑不了这一步。"
            "请执行：pip install -r requirements-dev.txt"
        )
        pytest.skip("reportlab 没装（开发依赖），无法重新生成 PDF 样本")
    fresh = tmp_path / "sample_notice.pdf"
    make_samples.make_pdf(fresh)
    assert _pdf_content(fresh) == _pdf_content(SAMPLES / "sample_notice.pdf")


def test_committed_docx_keeps_planted_font_defect():
    """样本里埋的字体缺陷必须还在二进制里。

    只比抽出来的文本，比不出字体与字号：把埋错段落的仿宋 10.5pt 改成
    宋体 12.1pt，文本一个字不变，上面的比对照样通过，但样本不再有缺陷，
    确定性层的字体检查也就失去了对照物。
    """
    d = docx.Document(str(SAMPLES / "sample_company.docx"))
    planted = [p for p in d.paragraphs if p.text == "本项目工期为 90 日历天。"]
    assert len(planted) == 1, "埋错段落应当恰好一个"
    run = planted[0].runs[0]
    assert _east_asia_font(run) == "仿宋"
    assert _size_pt(run) == 10.5


def test_committed_docx_body_font_is_songti_12pt():
    """正文的主流写法必须还是宋体 12pt，埋错段落才有对照。"""
    d = docx.Document(str(SAMPLES / "sample_company.docx"))
    body = [p for p in d.paragraphs if p.text == "本项目工期为 60 日历天。"]
    assert body
    run = body[0].runs[0]
    assert _east_asia_font(run) == "宋体"
    assert _size_pt(run) == 12
