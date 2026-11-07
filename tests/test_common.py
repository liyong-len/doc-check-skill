import hashlib
import json
from pathlib import Path

from common import (
    finding_id,
    normalize_name,
    normalize_text,
    read_json,
    repo_root,
    sha256_file,
    work_dir,
    write_json,
)


def test_repo_root_contains_scripts(tmp_path):
    assert (repo_root() / "scripts").is_dir()


def test_work_dir_creates_directory(tmp_path):
    d = work_dir(str(tmp_path / "w"))
    assert d.is_dir()


def test_write_and_read_json_roundtrip(tmp_path):
    p = tmp_path / "a" / "b.json"
    write_json(p, {"名称": "值"})
    assert read_json(p) == {"名称": "值"}
    assert "名称" in p.read_text(encoding="utf-8")


def test_sha256_file_is_stable(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"abc")
    assert sha256_file(p) == sha256_file(p)
    assert len(sha256_file(p)) == 64
    assert sha256_file(p) == hashlib.sha256(b"abc").hexdigest()


def test_normalize_text_collapses_whitespace_and_fullwidth():
    assert normalize_text("  甲　乙  ") == "甲 乙"
    assert normalize_text("ＡＢＣ") == "ABC"


def test_normalize_name_strips_all_whitespace():
    assert normalize_name("北京 华信　科技 有限公司") == "北京华信科技有限公司"


def test_finding_id_is_stable_and_length_16():
    loc = {"type": "paragraph", "index": 3}
    a = finding_id("a.docx", "字体一致性", loc, "正文 片段")
    b = finding_id("a.docx", "字体一致性", loc, "正文  片段")
    assert a == b
    assert len(a) == 16


def test_finding_id_distinguishes_distinct_findings():
    """不同问题必须得到不同 id，否则 findings.json 会出现重复 id。"""
    base = finding_id("a.docx", "字体一致性", {"type": "paragraph", "index": 3}, "片段")
    # 不同文件
    assert base != finding_id("b.docx", "字体一致性", {"type": "paragraph", "index": 3}, "片段")
    # 不同 locator
    assert base != finding_id("a.docx", "字体一致性", {"type": "paragraph", "index": 4}, "片段")
    # locator 多带一个键，信息量不同，指纹也必须不同
    assert base != finding_id(
        "a.docx", "字体一致性", {"type": "paragraph", "index": 3, "section_path": "第一章"}, "片段"
    )
    # 白名单之外的键同样参与指纹（例如表格定位到具体 sheet）
    assert finding_id(
        "a.docx", "表格对齐", {"type": "table", "row": 1}, ""
    ) != finding_id(
        "a.docx", "表格对齐", {"type": "table", "row": 1, "sheet": "报价表"}, ""
    )


def test_finding_id_is_stable_across_locator_key_order():
    """locator 的键插入顺序不影响指纹。"""
    a = finding_id("a.docx", "字体一致性", {"type": "paragraph", "index": 3, "row": 1}, "片段")
    b = finding_id("a.docx", "字体一致性", {"row": 1, "index": 3, "type": "paragraph"}, "片段")
    assert a == b
