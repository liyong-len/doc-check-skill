"""修复波 C 的回归测试：确定性检查层。

覆盖：
- I-1  正文里的交叉引用被当成另一种题注写法，报出确定级的假问题
- I-2  文件名里的公司名掩盖了文件里另一家公司，混主体被漏掉
- 确定性结论与输入顺序无关（consistency.json 逐字节相同）
- M-1  主体名与写法变体两处的 core 口径一致
- 引用引导词落在词边界上（「意见（2）」不是引用，「参考文献（1）」是）
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import docx

from analyze import analyze

ROOT = Path(__file__).resolve().parent.parent


def _doc(name, texts, sections=None):
    blocks = [
        {"index": i, "kind": "paragraph", "text": t, "style": None,
         "section_path": "第一章"}
        for i, t in enumerate(texts)
    ]
    return {
        "file": name, "type": "docx", "sha256": "0" * 64, "title": "",
        "stats": {"paragraphs": len(blocks), "tables": 0, "pages": 1,
                  "words": 50, "rows": 0, "sheets": 0},
        "sections": sections or [], "blocks": blocks,
        "entities": [], "citations": [], "numbers": [], "notes": [],
    }


def _categories(result):
    return [i["category"] for i in result["issues"]]


# --- I-1：正文里的交叉引用不是题注写法 ---


def test_prose_cross_reference_is_not_a_second_caption_style():
    """「设备如图 3 所示。」是正文里的交叉引用，不是第二种题注写法。"""
    docs = [_doc("a.docx", [
        "设备如图 3 所示。",
        "图3 流程图",
    ])]
    result = analyze(docs)
    assert "图表题注体例" not in _categories(result)


def test_bare_caption_with_and_without_space_is_one_style():
    docs = [_doc("a.docx", [
        "图 3 流程图",
        "图3 架构图",
    ])]
    result = analyze(docs)
    assert "图表题注体例" not in _categories(result)


def test_space_in_numbered_caption_is_still_a_distinct_writing():
    """规范里的例子：「图1-1」与「图 1-1」是两种写法，仍要能查出来。"""
    docs = [_doc("a.docx", [
        "图1-1 流程图",
        "图 1-1 架构图",
    ])]
    result = analyze(docs)
    issues = [i for i in result["issues"] if i["category"] == "图表题注体例"]
    assert len(issues) == 1
    assert "2 种写法" in issues[0]["description"]


def test_table_cross_reference_is_not_a_second_caption_style():
    docs = [_doc("a.docx", [
        "清单见表 2 所示。",
        "表2 明细表",
    ])]
    result = analyze(docs)
    assert "图表题注体例" not in _categories(result)


# --- I-2：文件名只能解释它点到的那家公司 ---


def test_header_core_does_not_explain_another_company():
    """文件名里的「华信科技」不能替「上海华信科技有限公司」解释。

    去掉行政区划的核心字号在文件名里恰好也出现了，
    用它去匹配会把没被点名的公司也当成被区分了，混主体就漏掉了。
    """
    doc = _doc("北京华信科技有限公司投标文件.docx", [
        "本文件由北京华信科技有限公司编制。",
        "协作方为上海华信科技有限公司。",
    ])
    result = analyze([doc])
    issues = [i for i in result["issues"] if i["category"] == "主体串写"]
    assert len(issues) == 1
    assert "上海华信科技有限公司" in issues[0]["description"]


def test_header_naming_every_company_still_suppresses_the_p0():
    doc = _doc("北京华信科技有限公司投标文件.docx", [
        "本文件由北京华信科技有限公司编制。",
        "协作方为上海远大信息技术有限公司。",
    ])
    doc["sections"] = [{"path": "上海远大信息技术有限公司", "level": 1,
                        "heading": "上海远大信息技术有限公司", "start": 0, "end": 1}]
    result = analyze([doc])
    assert [i for i in result["issues"] if i["category"] == "主体串写"] == []


# --- 确定性：结论与输入顺序无关 ---


def _make_docx(path: Path, texts: list[str]) -> Path:
    d = docx.Document()
    for text in texts:
        d.add_paragraph(text)
    d.save(str(path))
    return path


def test_consistency_json_is_identical_in_two_file_orders(tmp_path):
    """同样两批文档换个 --files 顺序跑，consistency.json 必须逐字节相同。

    否则复查对比会凭空多出「新增问题」与「已修复问题」：
    文件没变，结论却变了。
    """
    a = _make_docx(tmp_path / "a.docx", [
        "本文件由北京华信科技有限公司编制。",
        "协作方为上海远大信息技术有限公司。",
    ])
    b = _make_docx(tmp_path / "b.docx", [
        "北京华信科技有限责任公司参与实施。",
        "本项目工期为 90 日历天。",
    ])

    outputs = []
    for order, tag in (([a, b], "ab"), ([b, a], "ba")):
        work = tmp_path / f"work-{tag}"
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "prepare.py"),
             "--files", *[str(p) for p in order],
             "--depth", "standard", "--work", str(work)],
            capture_output=True, cwd=str(ROOT),
        )
        assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
        outputs.append((work / "consistency.json").read_bytes())

    assert outputs[0] == outputs[1], "consistency.json 与输入顺序有关"


def test_entity_names_are_sorted():
    docs = [
        _doc("b.docx", ["上海远大信息技术有限公司负责实施。"]),
        _doc("a.docx", ["北京华信科技有限公司负责实施。"]),
    ]
    result = analyze(docs)
    cores = [n["core"] for n in result["entities"]["names"]]
    assert cores == sorted(cores)


def test_issue_attribution_does_not_depend_on_input_order():
    """同一主体出现在两个文件里时，归属哪个文件与输入顺序无关。"""
    docs = [
        _doc("b.docx", ["北京华信科技有限公司负责实施。"]),
        _doc("a.docx", ["北京华信科技有限责任公司负责实施。"]),
    ]
    first = analyze(docs)
    second = analyze(list(reversed(docs)))
    ids = lambda r: [i["id"] for i in r["issues"]]
    assert ids(first) == ids(second)
    assert first["issues"] == second["issues"]


# --- M-1：两处 core 是同一个口径 ---


def test_name_and_variant_core_use_the_same_definition():
    docs = [_doc("a.docx", ["北京华信科技有限公司负责实施。"])]
    result = analyze(docs)
    name_core = result["entities"]["names"][0]["core"]
    variant_core = result["entities"]["variants"][0]["core"]
    assert name_core == variant_core
    # 规范核心字号保留行政区划
    assert name_core == "北京华信科技"


# --- 引用引导词要在词边界上 ---


def test_opinion_parenthesis_is_not_a_citation():
    """「意见（2）」里的括号是枚举序号，不是引用标记。"""
    docs = [_doc("a.docx", [
        "根据甲方意见（2），本项目应当调整。",
        "相关依据[1]说明本方案满足要求。",
    ])]
    result = analyze(docs)
    assert [i for i in result["issues"] if i["category"] == "引用标记"] == []


def test_reference_with_lead_in_word_is_a_citation():
    docs = [_doc("a.docx", [
        "参考文献（1）指出本项目应当调整。",
        "相关依据[1]说明本方案满足要求。",
    ])]
    result = analyze(docs)
    issues = [i for i in result["issues"] if i["category"] == "引用标记"]
    assert len(issues) == 1


def test_data_parenthesis_is_not_a_citation():
    docs = [_doc("a.docx", [
        "采集数据（1）与数据（2）。",
        "相关依据[1]说明本方案满足要求。",
    ])]
    result = analyze(docs)
    assert [i for i in result["issues"] if i["category"] == "引用标记"] == []


# --- M-2：模型自造的类别不能被藏起来 ---


def test_non_standard_category_is_marked_not_hidden():
    from labels import category_label

    assert category_label("前后矛盾") == "前后矛盾"
    assert category_label("") == "未分类"
    assert category_label("typo") == "未分类（类别非规范）"


def test_render_refuses_a_finding_with_an_english_category(tmp_path):
    """英文类别一律拦下来：报告里不会出现英文类别，也不会一声不响。"""
    import pytest

    from render import render

    work = tmp_path / "work"
    work.mkdir()
    (work / "manifest.json").write_text(
        json.dumps({"script_version": "0.1.0", "depth": "standard",
                    "generated_at": "2026-11-07T10:00:00+08:00",
                    "documents": [], "failures": []}, ensure_ascii=False),
        encoding="utf-8")
    (work / "consistency.json").write_text(
        json.dumps({"style_profile": {}, "issues": [],
                    "entities": {"names": [], "variants": [], "per_file": {}},
                    "stats": {"documents": 0, "issues": 0}}, ensure_ascii=False),
        encoding="utf-8")
    (work / "findings.json").write_text(
        json.dumps([{
            "severity": "P2", "category": "typo", "detector": "llm",
            "confidence": "确定", "file": "a.docx",
            "locator": {"type": "file"}, "quote": "",
            "description": "描述", "suggestion": "建议",
        }], ensure_ascii=False),
        encoding="utf-8")

    with pytest.raises(SystemExit):
        render(work, tmp_path / "report.html")
    assert not (tmp_path / "report.html").exists()
