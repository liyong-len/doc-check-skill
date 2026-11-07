import datetime
import json

import openpyxl
from openpyxl.styles import Color, PatternFill

from extractors.xlsx import extract_xlsx


def _make_xlsx(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "报价表"
    ws["A1"] = "项目"
    ws["B1"] = "数量"
    ws["A2"] = "设备"
    ws["B2"] = 10
    ws["B2"].number_format = "#,##0.00"
    ws2 = wb.create_sheet("说明")
    ws2["A1"] = "备注"
    path = tmp_path / "b.xlsx"
    wb.save(str(path))
    return path


def test_extract_xlsx_sheets_and_rows(tmp_path):
    doc = extract_xlsx(_make_xlsx(tmp_path))
    assert doc["type"] == "xlsx"
    assert doc["stats"]["sheets"] == 2
    assert doc["stats"]["rows"] == 3


def test_extract_xlsx_number_format_kept(tmp_path):
    doc = extract_xlsx(_make_xlsx(tmp_path))
    sheets = {s["name"]: s for s in doc["sheets"]}
    cell = sheets["报价表"]["cells"]["B2"]
    assert cell["value"] == 10
    assert cell["number_format"] == "#,##0.00"


def test_extract_xlsx_header_row_inferred(tmp_path):
    doc = extract_xlsx(_make_xlsx(tmp_path))
    sheets = {s["name"]: s for s in doc["sheets"]}
    assert sheets["报价表"]["header_row"] == 1


def test_extract_xlsx_blocks_have_table_kind(tmp_path):
    doc = extract_xlsx(_make_xlsx(tmp_path))
    assert any(b["kind"] == "table" for b in doc["blocks"])


def test_extract_xlsx_date_cell_is_json_serializable(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = datetime.datetime(2024, 1, 1)
    ws["A2"] = datetime.date(2024, 1, 2)
    path = tmp_path / "dates.xlsx"
    wb.save(str(path))
    doc = extract_xlsx(path)
    cells = doc["sheets"][0]["cells"]
    assert cells["A1"]["value"] == "2024-01-01T00:00:00"
    assert cells["A2"]["value"] == "2024-01-02T00:00:00"
    json.dumps(doc, ensure_ascii=False)


def test_extract_xlsx_theme_fill_is_json_serializable(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "表头"
    ws["A1"].fill = PatternFill("solid", fgColor=Color(theme=4, tint=0.5))
    path = tmp_path / "theme.xlsx"
    wb.save(str(path))
    doc = extract_xlsx(path)
    cell = doc["sheets"][0]["cells"]["A1"]
    assert isinstance(cell["fill"], str)
    json.dumps(doc, ensure_ascii=False)


def test_extract_xlsx_cells_keep_style(tmp_path):
    # 单元格样式不能丢：丢了表格体例检查就永远看不见 xlsx 的表格
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "报价表"
    ws["A1"] = "项目"
    ws["A1"].font = openpyxl.styles.Font(bold=True, name="宋体", size=12)
    path = tmp_path / "bold.xlsx"
    wb.save(str(path))
    doc = extract_xlsx(path)
    table = next(b for b in doc["blocks"] if b["kind"] == "table")
    cell = table["rows"][0][0]
    assert cell["style"]["bold"] is True
    assert cell["style"]["font_latin"] == "宋体"
    assert cell["style"]["size_pt"] == 12
