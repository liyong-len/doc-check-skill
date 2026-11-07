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

SAMPLE_FILES = [
    SAMPLES / "sample_company.docx",
    SAMPLES / "sample_price.xlsx",
    SAMPLES / "sample_note.md",
]

# 阶段②（智能体产物）在测试里的替身。
# locator 指向样本里的真实位置：「本项目工期为 90 日历天。」是第 12 段（0 起），
# 在「第一章 投标文件 / 技术方案」之下。
FINDING = {
    "id": "e" * 16, "severity": "P1", "category": "前后矛盾",
    "detector": "llm", "confidence": "疑似 · 需人工核实",
    "file": "sample_company.docx",
    "locator": {"type": "paragraph", "index": 12,
                "section_path": "第一章 投标文件/技术方案"},
    "quote": "本项目工期为 90 日历天。",
    "description": "与前文 60 日历天矛盾",
    "suggestion": "统一为 60 日历天",
}


def _ensure_samples():
    if not (SAMPLES / "sample_company.docx").exists():
        subprocess.run(
            [sys.executable, str(ROOT / "tests" / "make_samples.py")],
            check=True, cwd=str(ROOT),
        )


def _prepare(tmp_path, files=None):
    """跑阶段①，返回工作目录与结果。"""
    from prepare import prepare

    work = tmp_path / "work"
    result = prepare(files if files is not None else SAMPLE_FILES, "standard", work)
    return work, result


def test_end_to_end_pipeline(tmp_path):
    _ensure_samples()
    from render import render

    work, result = _prepare(tmp_path)
    out = tmp_path / "report.html"
    assert result["documents"] == 3
    # prepare 返回的 failures 是清单本身（不是条数），空清单才算没有失败项。
    assert result["failures"] == []
    assert result["failure_count"] == 0

    (work / "findings.json").write_text(
        json.dumps([FINDING], ensure_ascii=False), encoding="utf-8"
    )

    render(work, out)
    html = out.read_text(encoding="utf-8")

    assert "文档检查报告" in html
    # 能力边界声明是报告规范的要求（references/report-spec.md）。
    assert "未核实外部事实" in html

    # 断言必须打在「只有这条 finding 才有」的文字上。
    # 「文档检查报告」是静态标题，「前后矛盾」是 §7 规则表里的一行，
    # 「未核实外部事实」在静态页脚里——finding 被整个丢掉时它们照样在，
    # 断言它们等于没断言。
    assert FINDING["description"] in html
    assert FINDING["suggestion"] in html
    # §3 按文件明细里的类别小标题带条数，只有这条 finding 在时才是「前后矛盾（1）」。
    # 光断言「前后矛盾」没有用：§7 规则表里那一行恒在。
    assert "前后矛盾（1）" in html
    # 引文本身不能当证据：确定性层的字体偏离报的是同一段文字，
    # 同一个引文在没有这条 finding 时也在报告里。负对照见下一个测试。
    assert FINDING["quote"] in html

    assert (work / "last-findings.json").exists()


def test_end_to_end_report_drops_finding_when_findings_empty(tmp_path):
    """负对照：findings.json 为空时，这条 finding 的文字必须从报告里消失。

    没有这条对照，正向断言仍然分不清「finding 真的进了报告」与
    「同样的字恰好在静态模板或别的检查项里」。
    """
    _ensure_samples()
    from render import render

    work, _ = _prepare(tmp_path)
    out = tmp_path / "report.html"
    (work / "findings.json").write_text("[]", encoding="utf-8")

    render(work, out)
    html = out.read_text(encoding="utf-8")

    assert FINDING["description"] not in html
    assert FINDING["suggestion"] not in html
    assert "前后矛盾（1）" not in html
    # 确定性层的结论仍在：报告不是空的，只是少了模型侧的条目。
    # 断言必须打在「只有这条确定性发现才有」的文字上：
    # 「字体一致性」是 §7 规则表里的一行，恒在，断言它等于没断言；
    # 「本处为「10.5」」是字号偏离那条确定性发现的说明，别的条目不会带它。
    assert "本处为「10.5」" in html


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
