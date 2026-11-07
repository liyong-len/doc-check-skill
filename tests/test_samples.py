"""提交的样本必须与生成器产出的样本一致。

样本是二进制文件（docx/xlsx 是 zip），逐字节比对没有意义：
zip 里的时间戳每次生成都不一样。要比的是内容。
"""
from __future__ import annotations

from pathlib import Path

import docx
import openpyxl

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


def test_committed_samples_exist():
    for name in ["sample_company.docx", "sample_price.xlsx", "sample_note.md"]:
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
