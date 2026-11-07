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
