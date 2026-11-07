"""各文件格式抽取器。每个抽取器返回统一文档结构。"""
from __future__ import annotations

from pathlib import Path


def extract_document(path: Path) -> dict:
    """按扩展名分派到具体抽取器。"""
    from .docx import extract_docx
    from .pdf import extract_pdf
    from .text import extract_text
    from .xlsx import extract_xlsx

    suffix = Path(path).suffix.lower()
    if suffix == ".docx":
        return extract_docx(path)
    if suffix == ".xlsx":
        return extract_xlsx(path)
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix in (".md", ".markdown", ".txt"):
        return extract_text(path)
    raise ValueError(f"不支持的文件类型：{suffix}（支持 .docx/.xlsx/.pdf/.md/.txt）")
