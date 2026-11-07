from schema import make_finding, validate_findings


def _valid():
    return make_finding(
        severity="P2", category="字体一致性", detector="deterministic",
        confidence="确定", file="a.docx",
        locator={"type": "paragraph", "index": 3, "section_path": "第一章"},
        quote="正文片段", description="描述", suggestion="建议",
    )


def test_make_finding_sets_id():
    f = _valid()
    assert len(f["id"]) == 16
    assert f["id"] == make_finding(
        severity="P2", category="字体一致性", detector="deterministic",
        confidence="确定", file="a.docx",
        locator={"type": "paragraph", "index": 3, "section_path": "第一章"},
        quote="正文片段", description="描述", suggestion="建议",
    )["id"]


def test_validate_accepts_valid():
    assert validate_findings([_valid()]) == []


def test_validate_reports_bad_severity():
    f = _valid()
    f["severity"] = "P9"
    errs = validate_findings([f])
    assert len(errs) == 1
    assert "P9" in errs[0]


def test_validate_reports_missing_field():
    f = _valid()
    del f["suggestion"]
    errs = validate_findings([f])
    assert any("suggestion" in e for e in errs)


def test_validate_reports_locator_without_type():
    f = _valid()
    f["locator"] = {"index": 1}
    errs = validate_findings([f])
    assert any("locator" in e for e in errs)
