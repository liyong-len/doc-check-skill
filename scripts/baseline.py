"""基线对比：新增、已修复、未修复，以及文件是否改动。"""
from __future__ import annotations

from schema import fingerprint


def diff_findings(current: list[dict], baseline: list[dict]) -> dict:
    cur = {fingerprint(f): f for f in current if isinstance(f, dict)}
    base = {fingerprint(f): f for f in baseline if isinstance(f, dict)}
    return {
        "new": [cur[k] for k in cur if k not in base],
        "fixed": [base[k] for k in base if k not in cur],
        "unchanged": [cur[k] for k in cur if k in base],
    }


def diff_manifests(current: dict, baseline: dict) -> list[dict]:
    cur = {d.get("file"): d.get("sha256", "") for d in current.get("documents", [])}
    base = {d.get("file"): d.get("sha256", "") for d in baseline.get("documents", [])}
    out = []
    for name in sorted(set(cur) | set(base)):
        old = base.get(name, "")
        new = cur.get(name, "")
        out.append({"file": name, "old_sha": old, "new_sha": new, "changed": old != new})
    return out
