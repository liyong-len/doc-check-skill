"""金标评估：统计模型输出的召回率与误报率。

用法：
    python scripts/evaluate.py --gold tests/gold/gold_set.json --predicted .doc-check-work/findings.json

比对的是模型的 findings.json（阶段②产物）。阶段①的确定性检查结论在
consistency.json 里，类别与模型层不同，不混进同一份金标。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import normalize_text


def _key(item: dict) -> str:
    """匹配键：文件 + 类别 + 归一化后的引文。

    归一化做 NFKC 并折叠空白，因此全角半角与空格差异不影响匹配。
    """
    return "|".join([
        item.get("file", ""),
        item.get("category", ""),
        normalize_text(item.get("quote", "")),
    ])


def evaluate(gold: list[dict], predicted: list[dict]) -> dict:
    """比对金标与模型输出，返回召回率、精确率与漏报、误报清单。"""
    gold_map = {_key(g): g for g in gold}
    pred_map = {_key(p): p for p in predicted}

    matched = [k for k in gold_map if k in pred_map]
    missing = [gold_map[k] for k in gold_map if k not in pred_map]
    false_positives = [pred_map[k] for k in pred_map if k not in gold_map]

    gold_total = len(gold_map)
    pred_total = len(pred_map)
    recall = len(matched) / gold_total if gold_total else 1.0
    precision = len(matched) / pred_total if pred_total else 0.0
    return {
        "recall": round(recall, 4),
        "precision": round(precision, 4),
        "matched": len(matched),
        "gold_total": gold_total,
        "predicted_total": pred_total,
        "missing": missing,
        "false_positives": false_positives,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="doc-check 金标评估")
    parser.add_argument("--gold", required=True, help="金标 JSON 路径")
    parser.add_argument("--predicted", required=True, help="模型输出 findings.json 路径")
    args = parser.parse_args(argv)

    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))
    gold_items = gold["items"] if isinstance(gold, dict) else gold
    predicted = json.loads(Path(args.predicted).read_text(encoding="utf-8"))
    predicted_items = predicted["findings"] if isinstance(predicted, dict) else predicted

    r = evaluate(gold_items, predicted_items)
    print(f"召回率：{r['recall']:.2%}（命中 {r['matched']}/{r['gold_total']}）")
    print(f"精确率：{r['precision']:.2%}（{r['matched']}/{r['predicted_total']}）")
    if r["missing"]:
        print("\n漏报：")
        for m in r["missing"]:
            print(f"  - [{m.get('category')}] {m.get('file')}：{m.get('quote')}")
    if r["false_positives"]:
        print("\n误报：")
        for f in r["false_positives"]:
            print(f"  - [{f.get('category')}] {f.get('file')}：{f.get('quote')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
