"""金标评估的单元测试。"""
from __future__ import annotations

import json
from pathlib import Path

from evaluate import evaluate

GOLD = Path(__file__).resolve().parent / "gold" / "gold_set.json"
SAMPLES = Path(__file__).resolve().parent / "samples"

# 语义层的九个类别。阶段①的确定性类别由单元测试覆盖，不该进金标。
SEMANTIC_CATEGORIES = {
    "错别字用词", "标点格式", "前后矛盾", "主体名误用", "引用张冠李戴",
    "待补充内容", "数字逻辑", "表述不清", "术语一致性",
}


def _g(file="a.docx", category="错别字用词", quote="帐号"):
    return {"file": file, "category": category, "quote": quote}


def _p(file="a.docx", category="错别字用词", quote="帐号"):
    return {
        "id": "f" * 16, "severity": "P2", "category": category,
        "detector": "llm", "confidence": "确定", "file": file,
        "locator": {"type": "paragraph", "index": 1},
        "quote": quote, "description": "d", "suggestion": "s",
    }


def test_evaluate_perfect_match():
    r = evaluate([_g()], [_p()])
    assert r["recall"] == 1.0
    assert r["precision"] == 1.0
    assert r["missing"] == []


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
    assert gold["items"], "金标不能为空"
    for item in gold["items"]:
        assert item["category"] in SEMANTIC_CATEGORIES, item
        assert item["file"] and item["quote"], item
        assert item["severity"] in ("P0", "P1", "P2", "P3"), item


def test_gold_set_quotes_exist_in_sample():
    """金标引文必须真实存在于样本里，否则永远匹配不上。"""
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    texts = _sample_paragraphs()
    for item in gold["items"]:
        assert any(item["quote"] in t for t in texts), item
