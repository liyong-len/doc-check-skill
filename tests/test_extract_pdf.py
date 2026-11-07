"""PDF 抽取器的测试。

reportlab 是**开发依赖**（requirements-dev.txt），只装 requirements.txt 的环境
里没有它。这里的跳过必须看得见：静默跳过会让「PDF 抽取没人测」这件事
被当成「PDF 抽取测过了」。
"""
import warnings

import pytest

try:
    import reportlab  # noqa: F401
except ImportError:
    warnings.warn(
        "reportlab 没装，本文件的 PDF 测试全部跳过。"
        "reportlab 是开发依赖（requirements-dev.txt），"
        "只装 requirements.txt 的环境跑不了这些测试。"
        "请执行：pip install -r requirements-dev.txt"
    )
    pytest.skip(
        "reportlab 没装（开发依赖），PDF 抽取测试未运行",
        allow_module_level=True,
    )

from extractors.pdf import extract_pdf


def _make_pdf(tmp_path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    path = tmp_path / "c.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica", 12)
    c.drawString(72, 760, "Beijing Huaxin Technology Co., Ltd.")
    c.drawString(72, 730, "Tender document section one.")
    c.showPage()
    c.setFont("Helvetica", 10)
    c.drawString(72, 760, "Page two content.")
    c.save()
    return path


def test_extract_pdf_pages_and_text(tmp_path):
    doc = extract_pdf(_make_pdf(tmp_path))
    assert doc["type"] == "pdf"
    assert doc["stats"]["pages"] == 2
    assert "Tender document" in " ".join(b["text"] for b in doc["blocks"])


def test_extract_pdf_confidence_is_low(tmp_path):
    doc = extract_pdf(_make_pdf(tmp_path))
    assert doc["blocks"][0]["style"]["confidence"] == "low"


def test_extract_pdf_font_stats_present(tmp_path):
    doc = extract_pdf(_make_pdf(tmp_path))
    assert doc["font_stats"]
    assert any(f["size"] for f in doc["font_stats"])


def _make_zero_page_pdf(tmp_path):
    """手工拼一个没有页面的 PDF：reportlab 造不出零页文档。"""
    bodies = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [] /Count 0 >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(bodies, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n" % (len(bodies) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(bodies) + 1, xref))
    path = tmp_path / "empty.pdf"
    path.write_bytes(bytes(out))
    return path


def test_extract_pdf_zero_page_notes_no_content(tmp_path):
    """零页 PDF 读不出内容，必须留下「需 OCR」注记，否则会被当成已检查。"""
    doc = extract_pdf(_make_zero_page_pdf(tmp_path))
    assert doc["stats"]["pages"] == 0
    assert any("需 OCR" in n for n in doc["notes"])
