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

from common import force_utf8_stdio, normalize_text


def _key(item: dict) -> str:
    """匹配键：文件 + 类别 + 归一化后的引文。

    归一化做 NFKC 并折叠空白，因此全角半角与空格差异不影响匹配。
    """
    return "|".join([
        item.get("file", ""),
        item.get("category", ""),
        normalize_text(item.get("quote", "")),
    ])


def _group(items: list[dict]) -> dict[str, list[dict]]:
    """按匹配键分组，保留出现顺序与重复条目。"""
    groups: dict[str, list[dict]] = {}
    for item in items:
        groups.setdefault(_key(item), []).append(item)
    return groups


def _stable_key(item: dict) -> tuple:
    """配对时的稳定排序键。

    配对结果不能取决于输入顺序：金标里没写 severity 的条目配上哪一条预测，
    按列表顺序取第一条就成了「谁排在前面谁被认」。同一批内容换个顺序进来，
    指标就变，这是评测工具自己制造出来的噪声。
    """
    return (
        str(item.get("severity") or ""),
        normalize_text(str(item.get("quote") or "")),
        str(item.get("description") or ""),
        str(item.get("suggestion") or ""),
    )


def _pair(gold_items: list[dict], pred_items: list[dict]):
    """把同一匹配键下的金标与预测配对。

    返回 (干净命中数, 级别不符列表, 漏报列表, 多余预测列表)。

    先配 severity 相同的那一对：同一个匹配键下金标可能有多条且级别不同
    （同一处问题定过不同的级），按顺序硬配会把「级别相同」的那条判成级别不符。
    金标没写 severity 时不判级别——能配上就算干净命中。

    两边都先按内容排序再配对：配对结果与输入顺序无关。
    """
    gold = sorted(gold_items, key=_stable_key)
    remaining = sorted(pred_items, key=_stable_key)
    unmatched_gold: list[dict] = []
    matched = 0

    for g in [x for x in gold if x.get("severity")]:
        idx = next(
            (i for i, p in enumerate(remaining)
             if p.get("severity") == g.get("severity")),
            None,
        )
        if idx is None:
            unmatched_gold.append(g)
            continue
        remaining.pop(idx)
        matched += 1

    for g in [x for x in gold if not x.get("severity")]:
        if remaining:
            remaining.pop(0)
            matched += 1
        else:
            unmatched_gold.append(g)

    severity_mismatch: list[dict] = []
    pairs = min(len(unmatched_gold), len(remaining))
    for i in range(pairs):
        severity_mismatch.append(
            {"gold": unmatched_gold[i], "predicted": remaining[i]}
        )
    return (
        matched,
        severity_mismatch,
        unmatched_gold[pairs:],
        remaining[pairs:],
    )


def evaluate(gold: list[dict], predicted: list[dict]) -> dict:
    """比对金标与模型输出，返回召回率、精确率与各类明细。

    计数按**原始条目数**，不去重：同一处问题被模型报了三次，就是三条预测，
    三条都进分母，多的两条进误报清单。去重计数会让「重复报三遍」与
    「报一遍」得到同一个精确率——指标看不见这种退化，输出却写着 100%。

    匹配键相同但 severity 不同的，算「级别不符」：问题找对了，定级错了，
    不算干净命中，但也不算漏报，单列出来。
    """
    gold_groups = _group(gold)
    pred_groups = _group(predicted)

    matched = 0
    severity_mismatch: list[dict] = []
    missing: list[dict] = []
    false_positives: list[dict] = []

    for key, gold_items in gold_groups.items():
        hit, mismatch, missed, extra = _pair(
            gold_items, pred_groups.get(key, [])
        )
        matched += hit
        severity_mismatch.extend(mismatch)
        missing.extend(missed)
        false_positives.extend(extra)

    for key, pred_items in pred_groups.items():
        if key not in gold_groups:
            false_positives.extend(pred_items)

    gold_total = len(gold)
    pred_total = len(predicted)
    found = matched + len(severity_mismatch)
    recall = found / gold_total if gold_total else 1.0
    precision = found / pred_total if pred_total else 0.0
    return {
        "recall": round(recall, 4),
        "precision": round(precision, 4),
        "matched": matched,
        "gold_total": gold_total,
        "predicted_total": pred_total,
        "severity_mismatch": severity_mismatch,
        "missing": missing,
        "false_positives": false_positives,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="doc-check 金标评估")
    parser.add_argument("--gold", required=True, help="金标 JSON 路径")
    parser.add_argument("--predicted", required=True, help="模型输出 findings.json 路径")
    args = parser.parse_args(argv)

    force_utf8_stdio()
    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))
    gold_items = gold["items"] if isinstance(gold, dict) else gold
    predicted = json.loads(Path(args.predicted).read_text(encoding="utf-8"))
    predicted_items = predicted["findings"] if isinstance(predicted, dict) else predicted

    r = evaluate(gold_items, predicted_items)
    mismatch = r["severity_mismatch"]
    found = r["matched"] + len(mismatch)
    print(f"召回率：{r['recall']:.2%}（找到 {found}/{r['gold_total']} 条问题："
          f"干净命中 {r['matched']}、级别不符 {len(mismatch)}）")
    print(f"精确率：{r['precision']:.2%}（{found}/{r['predicted_total']}）")
    if r["missing"]:
        print("\n漏报：")
        for m in r["missing"]:
            print(f"  - [{m.get('category')}] {m.get('file')}：{m.get('quote')}")
    if mismatch:
        print("\n级别不符（问题找对了，定级与金标不一致）：")
        for m in mismatch:
            g, p = m["gold"], m["predicted"]
            print(f"  - [{g.get('category')}] {g.get('file')}：{g.get('quote')}"
                  f"（金标 {g.get('severity')} / 模型 {p.get('severity')}）")
    if r["false_positives"]:
        print("\n误报：")
        for f in r["false_positives"]:
            print(f"  - [{f.get('category')}] {f.get('file')}：{f.get('quote')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
