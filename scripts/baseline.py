"""基线对比：新增、已修复、未修复，以及文件是否改动。"""
from __future__ import annotations

from schema import fingerprint


def diff_findings(current: list[dict], baseline: list[dict]) -> dict:
    """按指纹对比两组 finding。

    同一个指纹可能对应多条 finding（指纹只由文件、类别、位置、原文片段决定，
    不含描述与建议）。这里按出现次数配对：两边都有多余的算新增/已修复，
    配对上的算未修复。直接用指纹做字典键会把重复项悄悄丢掉，
    §6 的计数就会少报。
    """
    cur: dict[str, list[dict]] = {}
    for f in current or []:
        if isinstance(f, dict):
            cur.setdefault(fingerprint(f), []).append(f)
    base: dict[str, list[dict]] = {}
    for f in baseline or []:
        if isinstance(f, dict):
            base.setdefault(fingerprint(f), []).append(f)

    new: list[dict] = []
    fixed: list[dict] = []
    unchanged: list[dict] = []
    for key, cur_items in cur.items():
        base_items = base.get(key, [])
        common = min(len(cur_items), len(base_items))
        unchanged.extend(cur_items[:common])
        new.extend(cur_items[common:])
    for key, base_items in base.items():
        cur_items = cur.get(key, [])
        common = min(len(cur_items), len(base_items))
        fixed.extend(base_items[common:])
    return {"new": new, "fixed": fixed, "unchanged": unchanged}


def diff_manifests(current: dict, baseline: dict) -> list[dict]:
    """逐文件比对 SHA256。

    state 区分四种情形：modified 内容变了、added 本次新增、removed 上次有本次没有、
    unchanged 没变。added/removed 也是「与上次不同」，但在报告里必须分开说，
    否则会把新增文件说成「已修改」。
    """
    cur = {d.get("file"): d.get("sha256", "") for d in current.get("documents", [])}
    base = {d.get("file"): d.get("sha256", "") for d in baseline.get("documents", [])}
    out = []
    for name in sorted(set(cur) | set(base)):
        old = base.get(name, "")
        new = cur.get(name, "")
        if not old and new:
            state = "added"
        elif old and not new:
            state = "removed"
        elif old != new:
            state = "modified"
        else:
            state = "unchanged"
        out.append({
            "file": name,
            "old_sha": old,
            "new_sha": new,
            "changed": old != new,
            "state": state,
        })
    return out
