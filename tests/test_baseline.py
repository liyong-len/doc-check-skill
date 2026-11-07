from baseline import diff_findings, diff_manifests


def _f(id_suffix, file="a.docx", quote="正文"):
    return {
        "id": id_suffix * 16, "severity": "P2", "category": "字体一致性",
        "detector": "deterministic", "confidence": "确定", "file": file,
        "locator": {"type": "paragraph", "index": 1},
        "quote": quote, "description": "描述", "suggestion": "建议",
    }


def test_diff_findings_detects_new_and_fixed():
    base = [_f("a"), _f("b", quote="另一段")]
    cur = [_f("a"), _f("c", quote="新段")]
    d = diff_findings(cur, base)
    assert len(d["unchanged"]) == 1
    assert len(d["new"]) == 1
    assert len(d["fixed"]) == 1
    assert d["new"][0]["quote"] == "新段"


def test_diff_findings_empty_baseline():
    d = diff_findings([_f("a")], [])
    assert len(d["new"]) == 1
    assert d["fixed"] == []


def test_diff_manifests_flags_changed_file():
    cur = {"documents": [{"file": "a.docx", "sha256": "new"}]}
    base = {"documents": [{"file": "a.docx", "sha256": "old"}]}
    rows = diff_manifests(cur, base)
    assert rows[0]["changed"] is True
    assert rows[0]["old_sha"] == "old"
    assert rows[0]["new_sha"] == "new"
    assert rows[0]["state"] == "modified"


def test_diff_manifests_marks_added_and_removed():
    cur = {"documents": [{"file": "b.docx", "sha256": "new"}]}
    base = {"documents": [{"file": "a.docx", "sha256": "old"}]}
    rows = {r["file"]: r for r in diff_manifests(cur, base)}
    assert rows["b.docx"]["state"] == "added"
    assert rows["b.docx"]["old_sha"] == ""
    assert rows["a.docx"]["state"] == "removed"
    assert rows["a.docx"]["new_sha"] == ""


def test_diff_manifests_marks_unchanged():
    cur = {"documents": [{"file": "a.docx", "sha256": "same"}]}
    base = {"documents": [{"file": "a.docx", "sha256": "same"}]}
    rows = diff_manifests(cur, base)
    assert rows[0]["changed"] is False
    assert rows[0]["state"] == "unchanged"


def test_diff_findings_keeps_duplicate_fingerprints():
    """同一指纹出现多次时不得悄悄丢掉，否则 §6 的计数会少报。"""
    a = _f("a")
    a2 = dict(a, description="另一条描述")
    base = [_f("a")]
    cur = [_f("a"), a2]
    d = diff_findings(cur, base)
    assert len(d["unchanged"]) == 1
    assert len(d["new"]) == 1
    assert d["new"][0]["description"] == "另一条描述"


def test_diff_findings_counts_duplicates_on_both_sides():
    a = _f("a")
    base = [_f("a"), dict(a, description="基线上的第二条")]
    cur = [_f("a")]
    d = diff_findings(cur, base)
    assert len(d["unchanged"]) == 1
    assert len(d["fixed"]) == 1
