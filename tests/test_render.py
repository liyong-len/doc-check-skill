import json

from render import build_html, render


def _consistency():
    return {
        "style_profile": {
            "font_ea": {"label": "中文字体", "dominant": "宋体", "count": 40, "total": 42},
        },
        "issues": [
            {
                "id": "a" * 16, "severity": "P0", "category": "主体串写",
                "detector": "deterministic", "confidence": "疑似 · 需人工核实",
                "file": "a.docx", "locator": {"type": "file"},
                "quote": "北京华信科技有限公司",
                "description": "出现两个主体", "suggestion": "确认归属",
            }
        ],
        "entities": {
            "names": [
                {"name": "北京华信科技有限公司", "core": "华信科技",
                 "count": 3, "files": ["a.docx", "b.docx"]},
            ],
            "variants": [{"core": "华信科技",
                          "names": ["北京华信科技有限公司", "北京华信科技有限责任公司"]}],
        },
        "stats": {"documents": 2, "issues": 1},
    }


def _findings():
    return [
        {
            "id": "b" * 16, "severity": "P1", "category": "前后矛盾",
            "detector": "llm", "confidence": "疑似 · 需人工核实",
            "file": "a.docx",
            "locator": {"type": "paragraph", "index": 7, "section_path": "第二章"},
            "quote": "工期为 90 日历天",
            "description": "与前文 60 天矛盾", "suggestion": "统一为 60 天",
        }
    ]


def _manifest():
    return {
        "script_version": "0.1.0", "depth": "standard",
        "generated_at": "2026-11-07T10:00:00+08:00",
        "documents": [
            {"file": "a.docx", "type": "docx", "sha256": "c" * 64,
             "stats": {"paragraphs": 100, "tables": 2, "pages": 12,
                       "words": 5000, "rows": 0, "sheets": 0},
             "entities": ["北京华信科技有限公司"], "notes": []},
        ],
        "failures": [
            {"file": "b.pdf", "path": "b.pdf", "reason": "需 OCR，当前不支持"},
        ],
    }


def _write_work(tmp_path, *, findings=None, consistency=None, manifest=None):
    """造一个阶段①的工作目录。findings=None 表示不写 findings.json。"""
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    (work / "manifest.json").write_text(
        json.dumps(manifest or _manifest(), ensure_ascii=False), encoding="utf-8"
    )
    (work / "consistency.json").write_text(
        json.dumps(consistency or _consistency(), ensure_ascii=False), encoding="utf-8"
    )
    if findings is not None:
        (work / "findings.json").write_text(
            json.dumps(findings, ensure_ascii=False), encoding="utf-8"
        )
    return work


def test_build_html_contains_core_sections():
    html = build_html({
        "manifest": _manifest(),
        "consistency": _consistency(),
        "findings": _findings(),
        "baseline_diff": None,
    })
    for marker in ["检查范围与未能检查项", "结论概览", "硬伤速览", "按文件明细"]:
        assert marker in html, marker


def test_build_html_escapes_content():
    html = build_html({
        "manifest": _manifest(),
        "consistency": _consistency(),
        "findings": [{
            "id": "c" * 16, "severity": "P2", "category": "错别字",
            "detector": "llm", "confidence": "确定", "file": "<script>x</script>",
            "locator": {"type": "file"}, "quote": "<b>bold</b>",
            "description": "描述", "suggestion": "建议",
        }],
        "baseline_diff": None,
    })
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html


def test_build_html_shows_p0_in_quick_view():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": _findings(), "baseline_diff": None,
    })
    assert "主体串写" in html
    assert "P0" in html


def test_build_html_includes_limitations_statement():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": _findings(), "baseline_diff": None,
    })
    assert "未核实外部事实" in html


def test_build_html_no_external_resources():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": _findings(), "baseline_diff": None,
    })
    assert "http://" not in html
    assert "https://" not in html
    assert "<link" not in html


def test_build_html_groups_issues_by_file():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": _findings(), "baseline_diff": None,
    })
    assert "a.docx" in html
    assert "工期为 90 日历天" in html


def test_build_html_escapes_locator_text():
    """locator 的 section_path 来自文档标题，必须转义后输出。"""
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": [{
            "id": "e" * 16, "severity": "P2", "category": "错别字",
            "detector": "llm", "confidence": "确定", "file": "a.docx",
            "locator": {"type": "paragraph", "index": 3,
                        "section_path": "<script>alert(1)</script>"},
            "quote": "正文", "description": "描述", "suggestion": "建议",
        }],
        "baseline_diff": None,
    })
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_build_html_severity_total_matches_displayed_counts():
    """非法 severity 不得让 banner 总数超过逐级之和。"""
    html = build_html({
        "manifest": _manifest(),
        "consistency": {"style_profile": {}, "issues": [], "entities": {}, "stats": {}},
        "findings": [
            {"id": "f" * 16, "severity": "P0", "category": "前后矛盾",
             "detector": "llm", "confidence": "确定", "file": "a.docx",
             "locator": {"type": "file"}, "quote": "正文",
             "description": "描述", "suggestion": "建议"},
            {"id": "g" * 16, "severity": "P9", "category": "前后矛盾",
             "detector": "llm", "confidence": "确定", "file": "a.docx",
             "locator": {"type": "file"}, "quote": "另段",
             "description": "描述", "suggestion": "建议"},
        ],
        "baseline_diff": None,
    })
    assert "共 2 个问题" in html
    assert "P0 1 ｜ P1 0 ｜ P2 0 ｜ P3 1" in html


def test_render_writes_report_and_baseline_file(tmp_path):
    work = _write_work(tmp_path, findings=_findings())
    out = tmp_path / "report.html"
    render(work, out)
    assert out.exists()
    baseline = work / "last-findings.json"
    assert baseline.exists()
    data = json.loads(baseline.read_text(encoding="utf-8"))
    assert len(data["findings"]) == 1
    assert "issues" in data


def test_render_baseline_covers_deterministic_layer(tmp_path):
    """确定性层的问题也进基线，复查时才算得进「新增」。"""
    work = _write_work(tmp_path)
    render(work, tmp_path / "r1.html")
    baseline = json.loads((work / "last-findings.json").read_text(encoding="utf-8"))
    assert len(baseline["issues"]) == 1
    assert baseline["findings"] == []

    cons = _consistency()
    cons["issues"].append({
        "id": "h" * 16, "severity": "P0", "category": "主体串写",
        "detector": "deterministic", "confidence": "疑似 · 需人工核实",
        "file": "a.docx", "locator": {"type": "file"},
        "quote": "上海远大信息技术有限公司",
        "description": "出现第三个主体", "suggestion": "确认归属",
    })
    (work / "consistency.json").write_text(
        json.dumps(cons, ensure_ascii=False), encoding="utf-8"
    )
    render(work, tmp_path / "r2.html", baseline=work / "last-findings.json")
    html = (tmp_path / "r2.html").read_text(encoding="utf-8")
    assert "复查对比" in html
    assert "新增问题（1）" in html


def test_render_tolerates_missing_findings_file(tmp_path):
    work = _write_work(tmp_path)
    out = tmp_path / "report.html"
    render(work, out)
    assert out.exists()
    data = json.loads((work / "last-findings.json").read_text(encoding="utf-8"))
    assert data["findings"] == []


def test_render_rejects_malformed_findings_file(tmp_path, capsys):
    work = _write_work(tmp_path)
    (work / "findings.json").write_text("{不是合法 JSON", encoding="utf-8")
    out = tmp_path / "report.html"
    try:
        render(work, out)
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("非法 findings.json 应当以退出码 2 结束")
    assert not out.exists()
    assert "findings.json" in capsys.readouterr().err


def test_render_rejects_schema_invalid_findings_file(tmp_path):
    work = _write_work(tmp_path, findings=[{"id": "x", "severity": "P0"}])
    out = tmp_path / "report.html"
    try:
        render(work, out)
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("不合法的 finding 应当以退出码 2 结束")
    assert not out.exists()


def test_render_reports_missing_manifest(tmp_path, capsys):
    work = tmp_path / "work"
    work.mkdir()
    try:
        render(work, tmp_path / "report.html")
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("缺少 manifest.json 应当以退出码 2 结束")
    err = capsys.readouterr().err
    assert "manifest.json" in err
    assert "prepare.py" in err


def test_render_reports_missing_consistency(tmp_path, capsys):
    work = tmp_path / "work"
    work.mkdir()
    (work / "manifest.json").write_text(
        json.dumps(_manifest(), ensure_ascii=False), encoding="utf-8"
    )
    try:
        render(work, tmp_path / "report.html")
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("缺少 consistency.json 应当以退出码 2 结束")
    assert "consistency.json" in capsys.readouterr().err


def test_render_reports_non_dict_manifest(tmp_path, capsys):
    work = tmp_path / "work"
    work.mkdir()
    (work / "manifest.json").write_text("[1, 2]", encoding="utf-8")
    try:
        render(work, tmp_path / "report.html")
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("manifest.json 不是对象时应当以退出码 2 结束")
    assert "JSON 对象" in capsys.readouterr().err


def test_render_reports_missing_baseline(tmp_path, capsys):
    work = _write_work(tmp_path)
    try:
        render(work, tmp_path / "report.html", baseline=tmp_path / "nope.json")
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("基线文件缺失时应当以退出码 2 结束")
    assert "基线文件" in capsys.readouterr().err


def test_render_tolerates_null_baseline_fields(tmp_path):
    """基线 JSON 里 findings/issues 为 null 时不得抛 TypeError。"""
    work = _write_work(tmp_path, findings=_findings())
    baseline = tmp_path / "prev.json"
    baseline.write_text(
        json.dumps({"generated_at": "", "findings": None, "issues": None,
                    "manifest": None}, ensure_ascii=False),
        encoding="utf-8",
    )
    out = tmp_path / "report.html"
    render(work, out, baseline=baseline)
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "复查对比" in html
    # 基线为空，两层的全部问题都算新增：模型侧 1 条 + 确定性层 1 条
    assert "新增问题（2）" in html


def test_render_tolerates_null_consistency_issues(tmp_path):
    """consistency.json 的 issues 为 null 时不得抛 TypeError。"""
    cons = _consistency()
    cons["issues"] = None
    work = _write_work(tmp_path, findings=_findings(), consistency=cons)
    out = tmp_path / "report.html"
    render(work, out)
    assert out.exists()
    assert "文档检查报告" in out.read_text(encoding="utf-8")
