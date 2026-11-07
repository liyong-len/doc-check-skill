"""修复波 B1 的回归测试：渲染器与 CLI。

覆盖：I1（id 可缺省）、I5（英文枚举不得进报告）、I7（问题片段高亮）、
I8（旧基线不得把确定性问题说成新增）、I10（命令行输出必须是 UTF-8）、
M3（主流值为空显示「未设置」）、M12（主体名必须转义），
以及文件标识改成相对路径后渲染器的表现。
"""
from __future__ import annotations

import json
from pathlib import Path

import schema
from render import build_html, render

# --- 测试夹具 ---


def _finding(**over):
    f = {
        "severity": "P1", "category": "前后矛盾",
        "detector": "llm", "confidence": "疑似 · 需人工核实",
        "file": "a.docx",
        "locator": {"type": "paragraph", "index": 7, "section_path": "第二章"},
        "quote": "工期为 90 日历天",
        "description": "与前文 60 天矛盾", "suggestion": "统一为 60 天",
    }
    f.update(over)
    return f


def _det_issue(**over):
    f = {
        "severity": "P0", "category": "主体串写",
        "detector": "deterministic", "confidence": "疑似 · 需人工核实",
        "file": "a.docx", "locator": {"type": "file"},
        "quote": "北京华信科技有限公司",
        "description": "出现两个主体", "suggestion": "确认归属",
    }
    f.update(over)
    return f


def _consistency(issues=None, profile=None):
    return {
        "style_profile": profile if profile is not None else {
            "font_ea": {"label": "中文字体", "dominant": "宋体",
                        "count": 40, "total": 42},
        },
        "issues": issues if issues is not None else [],
        "entities": {"names": [], "variants": [], "per_file": {}},
        "stats": {"documents": 1, "issues": 0},
    }


def _manifest(files=None, entities=None):
    docs = []
    for name in (files or ["a.docx"]):
        docs.append({
            "file": name, "type": "docx", "sha256": "c" * 64,
            "stats": {"paragraphs": 100, "tables": 2, "pages": 12,
                      "words": 5000, "rows": 0, "sheets": 0},
            "entities": list(entities or []), "notes": [],
        })
    return {
        "script_version": "0.1.0", "depth": "standard",
        "generated_at": "2026-11-07T10:00:00+08:00",
        "documents": docs, "failures": [],
    }


def _write_work(tmp_path, *, findings=None, consistency=None, manifest=None):
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    (work / "manifest.json").write_text(
        json.dumps(manifest or _manifest(), ensure_ascii=False), encoding="utf-8")
    (work / "consistency.json").write_text(
        json.dumps(consistency or _consistency(), ensure_ascii=False),
        encoding="utf-8")
    if findings is not None:
        (work / "findings.json").write_text(
            json.dumps(findings, ensure_ascii=False), encoding="utf-8")
    return work


def _html(findings=None, consistency=None, manifest=None, baseline_diff=None):
    return build_html({
        "manifest": manifest or _manifest(),
        "consistency": consistency or _consistency(),
        "findings": findings or [],
        "baseline_diff": baseline_diff,
    })


# --- I1：id 是派生字段，缺了也要出报告 ---


def test_render_accepts_findings_without_id(tmp_path):
    """合同（content-rules.md 的写作要求）从没要求写 id，缺 id 不是错误。"""
    work = _write_work(tmp_path, findings=[_finding()])
    out = tmp_path / "report.html"
    render(work, out)
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "工期为 90 日历天" in html


def test_render_fills_in_missing_id(tmp_path):
    work = _write_work(tmp_path, findings=[_finding()])
    render(work, tmp_path / "report.html")
    baseline = json.loads((work / "last-findings.json").read_text(encoding="utf-8"))
    found = baseline["findings"][0]
    assert found["id"]
    assert found["id"] == schema.fingerprint(found)


def test_render_recomputes_model_supplied_id(tmp_path):
    """模型写的 id 不作数，渲染器自己算。"""
    work = _write_work(tmp_path, findings=[_finding(id="x" * 16)])
    render(work, tmp_path / "report.html")
    baseline = json.loads((work / "last-findings.json").read_text(encoding="utf-8"))
    found = baseline["findings"][0]
    assert found["id"] != "x" * 16
    assert found["id"] == schema.fingerprint(found)


def test_schema_does_not_require_id():
    """id 不在必填字段里。"""
    assert "id" not in schema.REQUIRED_FIELDS
    assert "id" in schema.OPTIONAL_FIELDS
    errors = schema.validate_findings([_finding()])
    assert errors == []


# --- I5：报告里不得出现英文枚举 ---


def test_report_shows_chinese_source_label():
    html = _html(findings=[_finding(detector="llm")],
                 consistency=_consistency(issues=[_det_issue()]))
    assert "确定性" in html
    assert "模型" in html
    assert "deterministic" not in html
    assert "llm" not in html


def test_report_shows_chinese_locator_for_file_level_issues():
    """文件级问题的位置不得显示成「file」。"""
    html = _html(consistency=_consistency(issues=[_det_issue()]))
    assert "全文（整篇）" in html
    assert "· file" not in html
    assert "位置: file" not in html


def test_no_english_enum_reaches_the_report():
    """§2 §3 §4.3 §6 都不得出现原始英文枚举。"""
    html = _html(
        findings=[_finding(detector="llm",
                           locator={"type": "file"})],
        consistency=_consistency(issues=[
            _det_issue(),
            _det_issue(category="标题层级体例",
                       locator={"type": "paragraph", "index": 3}),
        ]),
        baseline_diff={
            "findings": {"new": [_det_issue()], "fixed": [], "unchanged": []},
            "files": [],
        },
    )
    for token in ("deterministic", "llm", "paragraph", "section"):
        assert token not in html, token
    assert "全文（整篇）" in html
    assert "确定性" in html


def test_unknown_category_is_not_shown_in_english():
    """模型自造的英文类别不得漏进中文报告。"""
    html = _html(findings=[_finding(category="typo")])
    assert "typo" not in html
    assert "未分类" in html


# --- I7：问题片段高亮 ---


def test_issue_quote_is_highlighted():
    html = _html(findings=[_finding()])
    assert "<mark>" in html
    assert "<mark>工期为 90 日历天</mark>" in html


def test_highlight_keeps_quote_escaped():
    html = _html(findings=[_finding(quote="<b>加粗</b>")])
    assert "<mark>&lt;b&gt;加粗&lt;/b&gt;</mark>" in html
    assert "<b>加粗</b>" not in html


# --- I8：旧格式基线 ---


def test_old_baseline_does_not_report_det_issues_as_new(tmp_path):
    """旧基线没有确定性层的问题，不能把今天的确定性问题说成新增。"""
    work = _write_work(tmp_path, findings=[_finding()],
                       consistency=_consistency(issues=[_det_issue()]))
    render(work, tmp_path / "r1.html")
    old = json.loads((work / "last-findings.json").read_text(encoding="utf-8"))
    old.pop("issues", None)          # 旧格式：没有 issues 键
    old.pop("format_version", None)  # 旧格式：没有格式标记
    base = tmp_path / "old.json"
    base.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")

    render(work, tmp_path / "r2.html", baseline=base)
    html = (tmp_path / "r2.html").read_text(encoding="utf-8")
    assert "基线来自旧版本格式，确定性层问题无法对比" in html
    assert "新增问题（0）" in html
    assert "新增问题（2）" not in html


def test_new_baseline_compares_both_layers(tmp_path):
    """本版本写出的基线带格式标记，确定性层照常对比。"""
    work = _write_work(tmp_path, findings=[_finding()],
                       consistency=_consistency(issues=[_det_issue()]))
    render(work, tmp_path / "r1.html")
    baseline = json.loads((work / "last-findings.json").read_text(encoding="utf-8"))
    assert baseline["format_version"] >= 2

    render(work, tmp_path / "r2.html", baseline=work / "last-findings.json")
    html = (tmp_path / "r2.html").read_text(encoding="utf-8")
    assert "基线来自旧版本格式" not in html
    assert "新增问题（0）" in html


def test_last_findings_carries_format_version(tmp_path):
    work = _write_work(tmp_path, findings=[_finding()])
    render(work, tmp_path / "r.html")
    baseline = json.loads((work / "last-findings.json").read_text(encoding="utf-8"))
    assert "format_version" in baseline


# --- M3：主流值为空 ---


def test_section4_1_shows_unset_instead_of_blank_cell():
    profile = {
        "font_ea": {"label": "中文字体", "dominant": "宋体", "count": 40, "total": 42},
        "align": {"label": "对齐方式", "dominant": None, "count": 18, "total": 18},
    }
    html = _html(consistency=_consistency(profile=profile))
    section = html.split("4.1 样式主流值")[1].split("4.2")[0]
    assert "<td>未设置</td>" in section


# --- M12：主体名必须转义 ---


def test_section3_file_summary_escapes_entity_names():
    html = _html(findings=[_finding()],
                 manifest=_manifest(entities=["<script>x</script>公司"]))
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html


def test_entity_names_from_consistency_are_escaped():
    cons = _consistency()
    cons["entities"]["per_file"] = {"a.docx": ["<img src=x onerror=1>"]}
    html = _html(findings=[_finding()], consistency=cons)
    assert "<img src=x" not in html
    assert "&lt;img" in html


# --- 文件标识是相对路径 ---


def test_report_distinguishes_same_basename_files_by_path():
    """两个目录下的 report.docx 必须在报告里分开。"""
    manifest = _manifest(files=["a/report.docx", "b/report.docx"])
    findings = [
        _finding(file="a/report.docx", quote="甲文件的问题"),
        _finding(file="b/report.docx", quote="乙文件的问题"),
    ]
    html = _html(findings=findings, manifest=manifest)
    assert "a/report.docx" in html
    assert "b/report.docx" in html
    section = html.split("id='s3'")[1].split("id='s4'")[0]
    assert "甲文件的问题" in section
    assert "乙文件的问题" in section
    assert section.count("<details") == 2


def test_section0_lists_relative_paths():
    manifest = _manifest(files=["a/report.docx", "b/report.docx"])
    html = _html(manifest=manifest)
    section = html.split("id='s0'")[1].split("id='s1'")[0]
    assert "a/report.docx" in section
    assert "b/report.docx" in section


def test_chunk_id_uses_the_file_identity(tmp_path):
    """分片 id 用文件标识拼，同名文件不会撞车。"""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from chunk import build_chunks

    docs = [
        {"file": "a/report.docx", "blocks": [
            {"index": 0, "kind": "paragraph", "text": "甲", "section_path": "第一章"},
        ]},
        {"file": "b/report.docx", "blocks": [
            {"index": 0, "kind": "paragraph", "text": "乙", "section_path": "第一章"},
        ]},
    ]
    chunks = build_chunks(docs, "standard")
    ids = [c["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids))
    assert ids[0].startswith("a/report.docx")
    assert ids[1].startswith("b/report.docx")
