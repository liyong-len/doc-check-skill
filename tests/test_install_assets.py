import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "install"

FAILURE_MESSAGES = [
    "未找到 Python 3.9 及以上解释器。请安装 Python 3.11 或 3.12 后重试。",
    "虚拟环境创建失败：",
    "依赖安装失败。Python ",
    "可能缺少预编译轮子，请改用 Python 3.11 或 3.12。",
    "依赖导入自检失败，请换用 Python 3.11 或 3.12 重建虚拟环境。",
    "依赖自检通过。",
]


def _adapters():
    return json.loads((INSTALL / "adapters.json").read_text(encoding="utf-8"))


def test_adapters_file_valid():
    data = _adapters()
    assert data["version"] == 1
    assert len(data["agents"]) >= 4


def test_known_agents_have_skill_dir():
    by_id = {a["id"]: a for a in _adapters()["agents"]}
    assert by_id["claude-code"]["skill_dir"] == "~/.claude/skills/doc-check"
    assert by_id["codex"]["skill_dir"] == "~/.codex/skills/doc-check"
    assert by_id["workbuddy"]["skill_dir"] == "~/DoubaoWork/skills/doc-check"
    assert by_id["dsh"]["skill_dir"] == "~/.dsh/skills/doc-check"


def test_every_agent_has_detect_paths_and_usage():
    for a in _adapters()["agents"]:
        assert "detect_paths" in a, a["id"]
        assert a.get("usage"), a["id"]
        assert a.get("mode") in ("skill_dir", "manual"), a["id"]


def test_generic_agent_is_manual():
    by_id = {a["id"]: a for a in _adapters()["agents"]}
    assert by_id["generic"]["mode"] == "manual"


def test_every_agent_has_template_file():
    for a in _adapters()["agents"]:
        if a["mode"] == "manual":
            continue
        p = INSTALL / "adapters" / f"{a['id']}.md"
        assert p.exists(), p


def test_install_scripts_exist():
    assert (INSTALL / "install.ps1").exists()
    assert (INSTALL / "install.sh").exists()


def test_install_scripts_mention_interpreter_candidates():
    for name in ["install.ps1", "install.sh"]:
        text = (INSTALL / name).read_text(encoding="utf-8")
        assert "3.12" in text
        assert "3.11" in text
        assert "requirements.txt" in text


def test_every_template_has_path_placeholder():
    """装进智能体目录的模板必须指向「装好之后的这份副本」，不是仓库。

    技能目录里就有 scripts/ 与 references/，指向仓库既多余又会失效
    （仓库搬走了或根本没同步过去）。
    """
    for a in _adapters()["agents"]:
        if a["mode"] == "manual":
            continue
        text = (INSTALL / "adapters" / f"{a['id']}.md").read_text(encoding="utf-8")
        assert "{{SKILL_DIR}}" in text, a["id"]


def test_manual_template_points_at_repo():
    """通用接入说明是给没装技能的智能体用的，指向仓库。"""
    text = (INSTALL / "adapters" / "generic.md").read_text(encoding="utf-8")
    assert "{{REPO_ROOT}}" in text


def test_skill_dir_agents_entry_is_skill_md():
    for a in _adapters()["agents"]:
        if a["mode"] != "skill_dir":
            continue
        assert a["entry"] == "SKILL.md", a["id"]


def test_both_installers_show_the_same_failure_messages():
    """两个安装器面向用户的消息必须一致，只有 shell 语法允许不同。"""
    for name in ["install.ps1", "install.sh"]:
        text = (INSTALL / name).read_text(encoding="utf-8")
        for msg in FAILURE_MESSAGES:
            assert msg in text, f"{name}: {msg}"


def test_both_installers_check_python_before_creating_venv():
    """必须先确认有可用的 Python，再建虚拟环境、装依赖、写智能体目录。"""
    for name in ["install.ps1", "install.sh"]:
        text = (INSTALL / name).read_text(encoding="utf-8")
        assert text.index("未找到 Python 3.9 及以上解释器") < text.index("创建虚拟环境"), name


def test_both_installers_share_one_implementation():
    """装到智能体目录这一步必须由同一个文件完成。

    两个安装器各写一份，行为迟早会分叉；共用一个文件，一致性是结构保证的，
    不是靠人记得同步。行为验证见 test_install_behaviour.py。
    """
    for name in ["install.ps1", "install.sh"]:
        text = (INSTALL / name).read_text(encoding="utf-8")
        assert "install_skill.py" in text, name
    shared = (INSTALL / "install_skill.py").read_text(encoding="utf-8")
    # 入口文件是 SKILL.md，适配模板另存为 AGENT.md，不得覆盖它。
    assert "AGENT.md" in shared
    assert "python-path.txt" in shared
    assert "AGENTS.md" in shared
