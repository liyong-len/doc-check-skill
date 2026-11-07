"""finding 结构校验。consistency.json 与 findings.json 共用同一套 schema。

id 是派生字段（见 derive_ids），模型不必写，校验也不要求。
"""
from __future__ import annotations

import re

from common import finding_id

SEVERITIES = ["P0", "P1", "P2", "P3"]
CONFIDENCES = ["确定", "疑似 · 需人工核实"]
DETECTORS = ["deterministic", "llm"]
REQUIRED_FIELDS = [
    "severity", "category", "detector", "confidence",
    "file", "locator", "quote", "description", "suggestion",
]
# id 是派生字段：由 file + category + locator + quote 算出来。
# 模型写不写、写什么都不影响结果，校验时不再要求。
OPTIONAL_FIELDS = ["id"]

# 可选字段的取值类型。id 由渲染器重算，模型写了也以重算为准，
# 但它必须是字符串——写成数字或对象说明模型误解了这个字段。
OPTIONAL_FIELD_TYPES = {"id": str}

# 类别必须是中文标签。一个字都不含中文的类别不是合法字面量，
# 多半是模型自造的英文标签（「typo」「format」）。
# 把它显示成「未分类」等于把模型的错误藏起来：报告看起来像没有这一类问题，
# 读的人不会想到模型写错了。这里直接报出来，让模型改对。
_CJK_RE = re.compile(r"[一-鿿]")


def make_finding(**fields) -> dict:
    f = {
        "id": "",
        "severity": "P3",
        "category": "",
        "detector": "llm",
        "confidence": "疑似 · 需人工核实",
        "file": "",
        "locator": {"type": "file"},
        "quote": "",
        "description": "",
        "suggestion": "",
    }
    f.update(fields)
    f["id"] = finding_id(f["file"], f["category"], f["locator"], f["quote"])
    return f


def fingerprint(finding: dict) -> str:
    loc = finding.get("locator")
    if not isinstance(loc, dict):
        loc = {"type": "file"}
    return finding_id(
        finding.get("file", ""),
        finding.get("category", ""),
        loc,
        finding.get("quote", ""),
    )


def derive_ids(findings: list) -> list:
    """给 findings 补上派生 id。

    id 是由 file + category + locator + quote 算出来的指纹，不是模型要填的
    字段：合同（references/content-rules.md 的写作要求）里从没要求过它，
    按合同写出来的 findings.json 不该因为缺 id 而整份被拒。
    这里统一重算，模型写了也以这里为准。
    """
    out = []
    for f in findings or []:
        if not isinstance(f, dict):
            out.append(f)
            continue
        item = dict(f)
        item["id"] = fingerprint(item)
        out.append(item)
    return out


def validate_findings(data: list[dict]) -> list[str]:
    """返回错误字符串列表。空列表表示通过。"""
    errors: list[str] = []
    if not isinstance(data, list):
        return ["findings 必须是数组"]
    for i, f in enumerate(data):
        prefix = f"第 {i + 1} 条"
        if not isinstance(f, dict):
            errors.append(f"{prefix}：不是对象")
            continue
        for key in REQUIRED_FIELDS:
            if key not in f:
                errors.append(f"{prefix}：缺少字段 {key}")
        if f.get("severity") not in SEVERITIES:
            errors.append(f"{prefix}：severity 非法 {f.get('severity')!r}，允许 {SEVERITIES}")
        if f.get("detector") not in DETECTORS:
            errors.append(f"{prefix}：detector 非法 {f.get('detector')!r}，允许 {DETECTORS}")
        if f.get("confidence") not in CONFIDENCES:
            errors.append(f"{prefix}：confidence 非法 {f.get('confidence')!r}，允许 {CONFIDENCES}")
        category = str(f.get("category", "") or "").strip()
        if "category" in f and not _CJK_RE.search(category):
            errors.append(
                f"{prefix}：category 非法 {category!r}，"
                "只能取 content-rules.md 固定清单里的中文类别"
            )
        for key in OPTIONAL_FIELDS:
            if key in f and not isinstance(f[key], OPTIONAL_FIELD_TYPES[key]):
                errors.append(
                    f"{prefix}：字段 {key} 类型非法，"
                    f"应为 {OPTIONAL_FIELD_TYPES[key].__name__}"
                )
        loc = f.get("locator")
        if not isinstance(loc, dict) or not loc.get("type"):
            errors.append(f"{prefix}：locator 必须含 type")
    return errors
