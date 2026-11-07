from pathlib import Path

import schema

REF = Path(__file__).resolve().parent.parent / "references"


def _read(name):
    return (REF / name).read_text(encoding="utf-8")


def test_all_reference_files_exist():
    for name in ["content-rules.md", "format-rules.md", "severity.md", "report-spec.md"]:
        assert (REF / name).exists(), name


def test_severity_doc_lists_all_severities():
    text = _read("severity.md")
    for s in schema.SEVERITIES:
        assert s in text


def test_severity_doc_lists_all_confidences():
    text = _read("severity.md")
    for c in schema.CONFIDENCES:
        assert c in text


def test_severity_doc_has_findings_schema():
    text = _read("severity.md")
    for field in ["id", "severity", "category", "detector", "confidence",
                  "file", "locator", "quote", "description", "suggestion"]:
        assert field in text


def test_content_rules_cover_all_nine_categories():
    text = _read("content-rules.md")
    for cat in ["错别字", "标点", "前后矛盾", "主体串写",
                "张冠李戴", "待补充", "数字逻辑", "表述不清", "术语"]:
        assert cat in text, cat


def test_severity_doc_introduces_no_extra_confidence_literals():
    # 参考文档不得自造 schema 里没有的置信度字面量：
    # 渲染器是按字面量分类展示的，文档与代码不一致会静默漏项
    import re
    text = _read("severity.md")
    for literal in set(re.findall(r"「(确定[^」]*)」", text)):
        assert literal in schema.CONFIDENCES, literal


def test_content_rules_fixed_category_list_excludes_deterministic_category():
    # 语义层的「主体名误用」与确定性层的「主体串写」是两个类别，
    # 固定清单里若出现「主体串写」，智能体会对同一问题报两次
    text = _read("content-rules.md")
    line = [l for l in text.splitlines() if l.startswith("- category 取值固定为")]
    assert line, "找不到固定类别清单"
    assert "主体串写" not in line[0]
    assert "主体名误用" in line[0]
    assert "待补充内容" in line[0]   # render.py §5 按这个字面量过滤


def test_format_rules_cover_all_ten_categories():
    text = _read("format-rules.md")
    for cat in ["字体一致性", "段落格式一致性", "标题层级体例", "图表题注体例",
                "表格体例", "主体名称", "数字与单位", "引用标记",
                "列表与编号", "术语与缩写"]:
        assert cat in text, cat
