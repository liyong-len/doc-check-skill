"""finding 结构校验。consistency.json 与 findings.json 共用同一套 schema。"""
from __future__ import annotations

from common import finding_id

SEVERITIES = ["P0", "P1", "P2", "P3"]
CONFIDENCES = ["确定", "疑似 · 需人工核实"]
DETECTORS = ["deterministic", "llm"]
REQUIRED_FIELDS = [
    "id", "severity", "category", "detector", "confidence",
    "file", "locator", "quote", "description", "suggestion",
]


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
    return finding_id(
        finding.get("file", ""),
        finding.get("category", ""),
        finding.get("locator") or {"type": "file"},
        finding.get("quote", ""),
    )


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
        loc = f.get("locator")
        if not isinstance(loc, dict) or not loc.get("type"):
            errors.append(f"{prefix}：locator 必须含 type")
    return errors
