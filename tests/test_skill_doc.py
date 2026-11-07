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


# --- 复查轮次 1 ---


def test_skill_md_stage_two_reads_consistency_json():
    # 「确定」的依据来自阶段①，智能体必须读到 consistency.json
    text = _read("SKILL.md")
    stage2 = text.split("### 阶段②")[1].split("### 阶段③")[0]
    assert "consistency.json" in stage2


def test_skill_md_points_at_report_spec():
    # report-spec.md 写着「哪张表按字面量筛」，智能体不读就会写错字面量
    text = _read("SKILL.md")
    assert "references/report-spec.md" in text


def test_skill_md_does_not_claim_stage_one_does_arithmetic():
    # analyze.py 里没有算术校验，合计与分项是语义层自己的活
    text = _read("SKILL.md")
    assert "算术校验一致" not in text
    assert "阶段①不做算术校验" in text
    assert "合计与分项" in text


def test_skill_md_makes_install_reference_conditional():
    # README.md 与 install/ 都是后续任务才有的产物
    text = _read("SKILL.md")
    assert "install/" in text
    assert "README" not in text


def test_agents_md_makes_install_reference_conditional():
    text = _read("AGENTS.md")
    assert "install/" in text
    assert "README" not in text


# --- 修复波 B2：R65 语义层的定级口径与 R73 入口文件的自给自足 ---


def test_skill_md_confidence_does_not_depend_on_stage_one():
    """阶段①不产出九类语义类别，拿它当门槛会让语义层永远写不出「确定」。"""
    text = _read("SKILL.md")
    assert "不以阶段①有没有对应依据为准" in text
    assert "若在阶段①有对应依据" not in text
    assert "证据链" in text


def test_skill_md_explains_how_to_resolve_interpreter_and_scripts():
    """入口文件必须说清楚解释器与脚本在哪儿，否则智能体会用错解释器。"""
    text = _read("SKILL.md")
    assert "python-path.txt" in text
    assert "scripts/" in text
    assert "references/" in text
    assert ".venv" in text
