import pytest

reportlab = pytest.importorskip("reportlab")

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
