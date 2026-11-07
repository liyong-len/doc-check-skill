"""金标评估的单元测试。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import schema
from evaluate import evaluate
from evaluate import main as evaluate_main

GOLD = Path(__file__).resolve().parent / "gold" / "gold_set.json"
SAMPLES = Path(__file__).resolve().parent / "samples"
ROOT = Path(__file__).resolve().parent.parent


def _semantic_categories() -> set[str]:
    """从 references/content-rules.md 解析语义层固定类别清单。

    硬编码一份清单，两处迟早漂移：文档改了、测试没改，测试就成了摆设。
    """
    text = (ROOT / "references" / "content-rules.md").read_text(encoding="utf-8")
    line = next(
        l for l in text.splitlines() if l.startswith("- category 取值固定为")
    )
    body = line.split("：", 1)[1].strip().rstrip("。")
    return {c.strip() for c in body.split("、")}


def _g(file="a.docx", category="错别字用词", quote="帐号", severity=None):
    item = {"file": file, "category": category, "quote": quote}
    if severity:
        item["severity"] = severity
    return item


def _p(file="a.docx", category="错别字用词", quote="帐号", severity="P2"):
    return {
        "id": "f" * 16, "severity": severity, "category": category,
        "detector": "llm", "confidence": "确定", "file": file,
        "locator": {"type": "paragraph", "index": 1},
        "quote": quote, "description": "d", "suggestion": "s",
    }


def _write_json(path: Path, data) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


# --- 计数口径 ---


def test_evaluate_perfect_match():
    r = evaluate([_g()], [_p()])
    assert r["recall"] == 1.0
    assert r["precision"] == 1.0
    assert r["matched"] == 1
    assert r["missing"] == []
    assert r["false_positives"] == []
    assert r["severity_mismatch"] == []


def test_evaluate_detects_miss():
    r = evaluate([_g(), _g(quote="错别")], [_p()])
    assert r["recall"] == 0.5
    assert len(r["missing"]) == 1


def test_evaluate_detects_false_positive():
    r = evaluate([_g()], [_p(), _p(quote="多出来的")])
    assert r["precision"] == 0.5
    assert len(r["false_positives"]) == 1


def test_evaluate_empty_gold():
    r = evaluate([], [_p()])
    assert r["recall"] == 1.0
    assert r["precision"] == 0.0


def test_evaluate_ignores_whitespace_difference():
    """引文前后的空白差异不应影响匹配。"""
    r = evaluate([_g(quote="帐号信息见附件")], [_p(quote=" 帐号信息见附件 ")])
    assert r["matched"] == 1
    assert r["missing"] == []
    assert r["false_positives"] == []


def test_evaluate_counts_duplicate_predictions_against_raw_total():
    """重复报的同一处问题必须计入分母。

    去重计数会让「同一处问题报三遍」与「报一遍」得到同一个精确率，
    指标看不见这种退化，而输出却写着 100%。
    """
    gold = [_g()]
    pred = [_p(), _p(), _p(), _p(quote="多出来的")]
    r = evaluate(gold, pred)
    assert r["gold_total"] == 1
    assert r["predicted_total"] == 4
    assert r["matched"] == 1
    assert r["recall"] == 1.0
    assert r["precision"] == 0.25
    # 两份重复 + 一条无关的，都得出现在误报清单里
    assert len(r["false_positives"]) == 3


def test_evaluate_counts_duplicate_gold_items_against_raw_total():
    """金标里重复的条目也不能被悄悄丢掉。"""
    r = evaluate([_g(), _g()], [_p()])
    assert r["gold_total"] == 2
    assert r["predicted_total"] == 1
    assert r["matched"] == 1
    assert len(r["missing"]) == 1
    assert r["recall"] == 0.5
    assert r["precision"] == 1.0


def test_evaluate_reports_severity_mismatch_separately():
    """问题找对但定级错，不算干净命中，但要单列出来。"""
    r = evaluate([_g(severity="P1")], [_p(severity="P2")])
    assert r["matched"] == 0
    assert len(r["severity_mismatch"]) == 1
    assert r["severity_mismatch"][0]["gold"]["severity"] == "P1"
    assert r["severity_mismatch"][0]["predicted"]["severity"] == "P2"
    # 找到了就不是漏报，也没多报
    assert r["missing"] == []
    assert r["false_positives"] == []
    assert r["recall"] == 1.0
    assert r["precision"] == 1.0


def test_evaluate_ignores_severity_when_gold_has_none():
    """金标没写级别时不判级别不符。"""
    r = evaluate([_g()], [_p(severity="P0")])
    assert r["matched"] == 1
    assert r["severity_mismatch"] == []


def test_evaluate_prefers_same_severity_when_pairing():
    """同一匹配键下有多条金标时，先配 severity 相同的那条。

    按出现顺序硬配会把「级别相同」的那一条判成级别不符，
    明明定级一致却记成了错。
    """
    gold = [_g(severity="P1"), _g(severity="P2")]
    r = evaluate(gold, [_p(severity="P2")])
    assert r["matched"] == 1
    assert r["severity_mismatch"] == []
    assert len(r["missing"]) == 1
    assert r["gold_total"] == 2
    assert r["recall"] == 0.5


# --- 命令行 ---


def test_evaluate_main_prints_metrics_and_lists(tmp_path, capsys):
    gold = _write_json(
        tmp_path / "gold.json",
        {"items": [_g(severity="P1"), _g(quote="漏掉的", severity="P2")]},
    )
    pred = _write_json(
        tmp_path / "findings.json",
        [_p(severity="P1"), _p(quote="多出来的")],
    )
    assert evaluate_main(["--gold", str(gold), "--predicted", str(pred)]) == 0
    out = capsys.readouterr().out
    assert "召回率" in out
    assert "精确率" in out
    assert "漏报" in out
    assert "误报" in out


def test_evaluate_main_prints_severity_mismatch(tmp_path, capsys):
    gold = _write_json(tmp_path / "gold.json", {"items": [_g(severity="P1")]})
    pred = _write_json(tmp_path / "findings.json", [_p(severity="P3")])
    assert evaluate_main(["--gold", str(gold), "--predicted", str(pred)]) == 0
    out = capsys.readouterr().out
    assert "级别不符" in out
    assert "P1" in out and "P3" in out


def test_evaluate_main_accepts_bare_lists_and_findings_dict(tmp_path, capsys):
    gold = _write_json(tmp_path / "gold.json", [_g()])
    pred = _write_json(tmp_path / "findings.json", {"findings": [_p()]})
    assert evaluate_main(["--gold", str(gold), "--predicted", str(pred)]) == 0
    assert "100.00%" in capsys.readouterr().out


def test_evaluate_main_requires_arguments():
    with pytest.raises(SystemExit):
        evaluate_main([])


# --- 仓库里的金标本身 ---


def _sample_paragraphs() -> list[str]:
    """读出样本文档的段落文本。样本缺失时先生成。"""
    import docx

    path = SAMPLES / "sample_company.docx"
    if not path.exists():
        import make_samples

        make_samples.SAMPLES.mkdir(parents=True, exist_ok=True)
        make_samples.make_docx(path)
    return [p.text for p in docx.Document(str(path)).paragraphs]


def test_gold_set_only_contains_semantic_categories():
    """金标只收语义层类别。确定性类别混进来会把「模型不该报」算成漏报。"""
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    categories = _semantic_categories()
    assert gold["items"], "金标不能为空"
    for item in gold["items"]:
        assert item["category"] in categories, item
        assert item["file"] and item["quote"], item
        assert item["severity"] in schema.SEVERITIES, item


def test_gold_set_quotes_exist_in_sample():
    """金标引文必须真实存在于样本里，否则永远匹配不上。"""
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    texts = _sample_paragraphs()
    for item in gold["items"]:
        assert any(item["quote"] in t for t in texts), item
