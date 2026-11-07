from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_skill_md_has_frontmatter():
    text = _read("SKILL.md")
    assert text.startswith("---\n")
    assert "name: doc-check" in text
    assert "description:" in text


def test_skill_md_documents_three_stages():
    text = _read("SKILL.md")
    assert "prepare.py" in text
    assert "findings.json" in text
    assert "render.py" in text


def test_skill_md_lists_depth_options():
    text = _read("SKILL.md")
    for d in ["quick", "standard", "deep"]:
        assert d in text


def test_skill_md_forbids_modifying_documents():
    text = _read("SKILL.md")
    assert "不得修改" in text or "绝不修改" in text


def test_skill_md_lists_categories():
    text = _read("SKILL.md")
    for cat in ["错别字", "前后矛盾", "张冠李戴", "待补充"]:
        assert cat in text, cat


def test_skill_md_points_at_content_rules():
    text = _read("SKILL.md")
    assert "references/content-rules.md" in text
    assert "references/severity.md" in text


def test_agents_md_points_to_skill():
    text = _read("AGENTS.md")
    assert "SKILL.md" in text
    assert "prepare.py" in text
