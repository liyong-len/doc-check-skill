"""端到端测试：生成样本 → 阶段① → 阶段②（手写 findings.json）→ 阶段③。

阶段②在真实使用中由智能体完成，这里用手写的 findings.json 代替，
验证的是三个脚本之间的接口与报告渲染，不验证模型输出。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = Path(__file__).resolve().parent / "samples"


def _ensure_samples():
    if not (SAMPLES / "sample_company.docx").exists():
        subprocess.run(
            [sys.executable, str(ROOT / "tests" / "make_samples.py")],
            check=True, cwd=str(ROOT),
        )


def test_end_to_end_pipeline(tmp_path):
    _ensure_samples()
    from prepare import prepare
    from render import render

    work = tmp_path / "work"
    out = tmp_path / "report.html"
    files = [
        SAMPLES / "sample_company.docx",
        SAMPLES / "sample_price.xlsx",
        SAMPLES / "sample_note.md",
    ]
    result = prepare(files, "standard", work)
    assert result["documents"] == 3
    # prepare 返回的 failures 是清单本身（不是条数），空清单才算没有失败项。
    assert result["failures"] == []
    assert result["failure_count"] == 0

    findings = [
        {
            "id": "e" * 16, "severity": "P1", "category": "前后矛盾",
            "detector": "llm", "confidence": "疑似 · 需人工核实",
            "file": "sample_company.docx",
            "locator": {"type": "paragraph", "index": 5, "section_path": "技术方案"},
            "quote": "本项目工期为 90 日历天。",
            "description": "与前文 60 日历天矛盾",
            "suggestion": "统一为 60 日历天",
        }
    ]
    (work / "findings.json").write_text(
        json.dumps(findings, ensure_ascii=False), encoding="utf-8"
    )

    render(work, out)
    html = out.read_text(encoding="utf-8")
    assert "文档检查报告" in html
    assert "前后矛盾" in html
    assert "未核实外部事实" in html
    assert (work / "last-findings.json").exists()


def test_end_to_end_catches_known_defects(tmp_path):
    _ensure_samples()
    from prepare import prepare

    work = tmp_path / "work"
    prepare([SAMPLES / "sample_company.docx"], "standard", work)
    consistency = json.loads((work / "consistency.json").read_text(encoding="utf-8"))
    cats = {i["category"] for i in consistency["issues"]}
    assert "字体一致性" in cats
    assert "数字与单位" in cats
    assert "标题层级体例" in cats
    # 样本里埋了第二个主体名，混主体（文件级 P0）必须被检出。
    assert "主体串写" in cats
