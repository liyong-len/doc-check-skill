"""生成含故意埋错的测试样本。用法：python tests/make_samples.py

样本里埋的问题分两类：

确定性层能查出来的（阶段①必须检出）
- 字体字号偏离正文：某段用了仿宋 10.5pt，正文是宋体 12pt
- 货币单位混用：「万元」与「元」
- 日期格式混用：「2024年1月1日」与「2024-01-01」
- 同一层级两种标题编号写法：「（一）式」与「1.1 式」
- 同一文件出现两个不同主体：疑似混主体（文件级 P0）

语义层能查出来的（错别字、前后矛盾、待补充内容、标点格式）留给智能体或金标评估，
确定性层不会报，也不该由脚本代劳。

正文与标题都显式设置字体字号：一致性检查只比对 run 上的直接格式，
不继承段落样式，若正文不写死格式，标题就会以「未设置」混进主流值里，
真正的埋错反倒被淹没。
"""
from __future__ import annotations

from pathlib import Path

import docx
import openpyxl
from docx.oxml.ns import qn
from docx.shared import Pt

SAMPLES = Path(__file__).resolve().parent / "samples"

# 正文字体字号。埋错段落用别的字体与字号，好让主流值计算有明确的对照。
BODY_FONT = "宋体"
BODY_SIZE_PT = 12


def _set_font(run, name: str, size_pt: float) -> None:
    """设置 run 的西文字体、中文字体与字号。

    python-docx 的 run.font.name 只写 w:ascii/w:hAnsi，中文字体要自己写
    w:eastAsia，否则抽取器读到的中文字体恒为「未设置」。
    """
    run.font.name = name
    run.font.size = Pt(size_pt)
    r_fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    r_fonts.set(qn("w:eastAsia"), name)


def _body(document, text: str):
    """加一个正文段落，字体字号取正文值。返回段落对象。"""
    paragraph = document.add_paragraph(text)
    for run in paragraph.runs:
        _set_font(run, BODY_FONT, BODY_SIZE_PT)
    return paragraph


def _heading(document, text: str, level: int) -> None:
    """加一个标题段落。保留 Heading 样式（结构靠它），字体字号与正文一致。"""
    paragraph = document.add_heading(text, level=level)
    for run in paragraph.runs:
        _set_font(run, BODY_FONT, BODY_SIZE_PT)


def make_docx(path: Path) -> None:
    d = docx.Document()
    _heading(d, "第一章 投标文件", 1)
    _heading(d, "技术方案", 2)
    _body(d, "本文件由北京华信科技有限公司编制。")
    # 埋错（语义层）：「帐号」应为「账号」
    _body(d, "本公司具备相关资质，帐号信息见附件。")
    # 埋错（确定性层）：同一文件出现第二个主体，疑似混主体
    _body(d, "协作方为上海远大信息技术有限公司。")
    # 埋错（确定性层）：同一层级混用两种标题编号写法（（一）式与 1.1 式）
    _body(d, "一、总体要求")
    _body(d, "1. 适用范围")
    _body(d, "（一）背景说明")
    _body(d, "1.1 实施进度")
    _body(d, "本项目工期为 60 日历天。")
    _body(d, "相关依据[1]说明本方案满足要求。")
    _body(d, "如图1-1所示的设备清单。")
    # 埋错（确定性层）：字体与字号偏离正文（仿宋 10.5pt，正文宋体 12pt）
    p = _body(d, "本项目工期为 90 日历天。")
    _set_font(p.runs[0], "仿宋", 10.5)
    # 埋错（确定性层）：货币单位混用
    _body(d, "本项目金额为 120 万元。")
    _body(d, "本次费用 3000 元。")
    # 埋错（确定性层）：日期格式混用
    _body(d, "签署日期 2024年1月1日，生效日期 2024-01-01。")
    # 埋错（语义层）：指向外部却未给出内容
    _body(d, "具体内容详见附件。")
    # 埋错（语义层）：中文句子里混用半角逗号
    _body(d, "本项目服务期限为12个月,含一年质保。")
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text = "项目"
    t.cell(0, 1).text = "数量"
    t.cell(1, 0).text = "设备"
    t.cell(1, 1).text = "10"
    d.save(str(path))


def make_xlsx(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "报价表"
    ws["A1"] = "项目"
    ws["B1"] = "数量"
    ws["A2"] = "设备"
    ws["B2"] = 10
    ws["B2"].number_format = "#,##0.00"
    ws["A3"] = "服务"
    ws["B3"] = 5
    ws["B3"].number_format = "General"
    ws2 = wb.create_sheet("明细")
    ws2["A1"] = "名称"
    ws2["B1"] = "金额"
    ws2["A2"] = "设备"
    ws2["B2"] = 1200000
    wb.save(str(path))


def make_md(path: Path) -> None:
    path.write_text(
        "# 投标文件\n\n## 技术方案\n\n"
        "本项目由北京华信科技有限公司负责。\n\n"
        "| 项目 | 数量 |\n| --- | --- |\n| 设备 | 10 |\n",
        encoding="utf-8",
    )


def main() -> None:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    make_docx(SAMPLES / "sample_company.docx")
    make_xlsx(SAMPLES / "sample_price.xlsx")
    make_md(SAMPLES / "sample_note.md")
    print(f"样本已生成到 {SAMPLES}")


if __name__ == "__main__":
    main()
