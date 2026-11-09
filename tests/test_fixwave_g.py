"""修复波 G 的回归测试。

覆盖：
- I-1 连接词裁剪把字号劈开时，两家不同的公司不能被并成一家：
      撞出来的残缺名（`贸易港城有限公司`）必须还原回各自的全称，
      两组分开，P0「主体串写」（疑似）照报，确定级的 P1「主体名称」
      不得出现。
- I-2 国家前缀守卫是**括号保护**，不是「完整字号」的识别：
      普通字号散文（`中国联通集团…`）到不了那个分支。
- I-3 行政区划那条规则只在「行政区划是前缀部分的开头」时生效；
      放进句子里就不成立。
- M-4 install.ps1 也要把 pip 的缓存目录钉在虚拟环境里。
- M-5 install.sh 的注释不得断言一个在本机复现不出来的机制。
- M-6 状态查询的输出先把根目录印出来，再说「本次只读」。
- 已知局限：字号相同、只差企业形式词的写法会被当成同一个主体
      （`集团` 与 `股份`），这一条只记录不修。

安装相关的测试一律对着临时的 HOME 跑，绝不碰用户的智能体目录。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from analyze import analyze
from entities import (
    extract_company_names,
    extract_company_occurrences,
    group_variants,
)

ROOT = Path(__file__).resolve().parent.parent
FORMAT_RULES = ROOT / "references" / "format-rules.md"
INSTALL = ROOT / "install"


def _doc(name, texts):
    blocks = [
        {"index": i, "kind": "paragraph", "text": t, "style": None,
         "section_path": "第一章"}
        for i, t in enumerate(texts)
    ]
    return {
        "file": name, "type": "docx", "sha256": "0" * 64, "title": "",
        "stats": {"paragraphs": len(blocks), "tables": 0, "pages": 1,
                  "words": 50, "rows": 0, "sheets": 0},
        "sections": [], "blocks": blocks,
        "entities": [], "citations": [], "numbers": [], "notes": [],
    }


def _format_rules() -> str:
    return FORMAT_RULES.read_text(encoding="utf-8")


def _known_limitations() -> str:
    parts = _format_rules().split("## 已知局限")
    assert len(parts) == 2, "缺少「已知局限」小节"
    return parts[1]


# --- I-1：撞出来的残缺名不能把两家不同的公司并成一家 ---


def test_two_raw_names_that_truncate_alike_stay_in_separate_groups():
    """两个不同的原文被裁成同一个残缺名时，必须还是两个主体。

    「本项目由中国自由贸易港城有限公司中标。」
    「本项目由北方自由贸易港城有限公司中标。」
    两句都被裁成 `贸易港城有限公司`。修复前它们塌成一组，
    既没有 P0「主体串写」，也没有 P1——两家不同的公司被静默合并。
    """
    docs = [_doc("a.docx", [
        "本项目由中国自由贸易港城有限公司中标。",
        "本项目由北方自由贸易港城有限公司中标。",
    ])]
    result = analyze(docs)

    per_file = result["entities"]["per_file"]["a.docx"]
    assert per_file == ["中国自由贸易港城有限公司", "北方自由贸易港城有限公司"], \
        per_file

    groups = result["entities"]["variants"]
    assert len(groups) == 2, groups
    assert sorted(g["names"][0] for g in groups) == [
        "中国自由贸易港城有限公司", "北方自由贸易港城有限公司",
    ], groups


def test_the_exact_truncation_collision_reports_a_p0_and_no_p1():
    """撞得一模一样的那一对：报 P0（疑似），不报确定级的 P1。"""
    docs = [_doc("a.docx", [
        "本项目由中国自由贸易港城有限公司中标。",
        "本项目由北方自由贸易港城有限公司中标。",
    ])]
    issues = analyze(docs)["issues"]

    mixed = [i for i in issues if i["category"] == "主体串写"]
    assert len(mixed) == 1, issues
    assert mixed[0]["severity"] == "P0"
    assert mixed[0]["confidence"] == "疑似 · 需人工核实"

    assert [i for i in issues if i["category"] == "主体名称"] == [], issues


def test_the_colliding_stems_with_different_forms_report_a_p0_and_no_p1():
    """撞词干、形式词不同的那一对：同样不报确定级的「统一名称」建议。

    修复前这两个名字的核心字号相同（都是「贸易港城」），被并成一家，
    报出确定级的「同一主体出现 2 种名称写法……全套文档应统一使用同一名称」
    ——那是让用户去统一两家不同的公司。
    """
    docs = [_doc("a.docx", [
        "本项目由中国自由贸易港城有限公司中标。",
        "本项目由北方自由贸易港城集团有限公司中标。",
    ])]
    issues = analyze(docs)["issues"]

    assert [i for i in issues if i["category"] == "主体名称"] == [], issues

    mixed = [i for i in issues if i["category"] == "主体串写"]
    assert len(mixed) == 1, issues
    assert mixed[0]["severity"] == "P0"
    assert mixed[0]["confidence"] == "疑似 · 需人工核实"
    # 报出来的必须是两家真公司的名字，不是同一个残缺名出现两次
    assert "中国自由贸易港城有限公司" in mixed[0]["description"], mixed[0]
    assert "北方自由贸易港城集团有限公司" in mixed[0]["description"], mixed[0]


def test_the_same_company_with_different_sentence_prefixes_is_not_split():
    """同一家公司换个句子前缀，不得被拆成两个主体。

    还原名是「同一个前缀有不止一个合格切分」时更宽的那一个。
    句子前缀不同但字号一样时，还原名必须一样——否则每份文档都会
    平白多出一条「疑似混主体」。
    """
    docs = [_doc("a.docx", [
        "本文件由北京华信科技有限公司编制。",
        "甲方委托北京华信科技有限公司实施。",
        "由甲方及乙方共同委托北京华信科技有限公司",
    ])]
    issues = analyze(docs)["issues"]

    assert [i for i in issues if i["category"] == "主体串写"] == [], issues
    assert [i for i in issues if i["category"] == "主体名称"] == [], issues

    result = analyze(docs)
    # per_file 按出现顺序记每一个块里的名字（可以有重复），
    # 归组之后仍然只有一个主体
    assert set(result["entities"]["per_file"]["a.docx"]) == {
        "北京华信科技有限公司"
    }, result["entities"]["per_file"]
    assert len(result["entities"]["variants"]) == 1, result["entities"]


def test_the_same_truncated_stem_from_the_same_raw_text_stays_one_subject():
    """两个**原文完全一样**的名字是同一个主体，不拆。"""
    docs = [_doc("a.docx", [
        "本项目由中国自由贸易港城有限公司中标。",
        "本次项目由中国自由贸易港城有限公司中标。",
    ])]
    issues = analyze(docs)["issues"]

    assert [i for i in issues if i["category"] == "主体串写"] == [], issues
    assert [i for i in issues if i["category"] == "主体名称"] == [], issues


def test_the_extractor_still_returns_the_truncated_name():
    """抽取器的结果一个字没改：它返回的仍是裁剪之后的那一段。

    还原名是**另外**记下来的信息（`extract_company_occurrences`），
    聚类与报告用它。抽取口径没变。
    """
    assert extract_company_names("本项目由中国自由贸易港城有限公司中标。") == [
        "贸易港城有限公司"
    ]
    assert extract_company_names("中国自由贸易港城有限公司") == [
        "贸易港城有限公司"
    ]
    assert extract_company_names("北方自由贸易港城有限公司") == [
        "贸易港城有限公司"
    ]

    occurrences = extract_company_occurrences(
        "本项目由中国自由贸易港城有限公司中标。")
    assert occurrences == [
        ("贸易港城有限公司", "中国自由贸易港城有限公司")
    ], occurrences


def test_the_restored_name_is_always_a_literal_substring():
    """还原名必须是文档里逐字存在的字符串，不能凭空造名。"""
    text = "本项目由中国自由贸易港城有限公司中标。"
    for name, restored in extract_company_occurrences(text):
        assert name in text, (name, text)
        assert restored in text, (restored, text)


def test_group_variants_still_groups_by_core():
    """归组基准没变：核心字号相同就是同一个主体。"""
    groups = group_variants(["北京华信科技有限公司", "北京华信科技有限责任公司"])
    assert len(groups) == 1, groups
    assert groups[0]["names"] == [
        "北京华信科技有限公司", "北京华信科技有限责任公司",
    ], groups


# --- I-2：国家前缀守卫是括号保护 ---


def test_the_country_guard_protects_a_bracketed_head():
    """形式词被拆进括号里时，守卫必须保住那一整串。

    去掉守卫，`中国(集团由华为技术)有限公司` 会被裁成
    `华为技术)有限公司`——一个括号都不配平的错名字。
    """
    assert extract_company_names("中国(集团由华为技术)有限公司") == [
        "中国(集团由华为技术)有限公司"
    ]


def test_the_country_guard_does_not_fire_on_an_ordinary_wordmark():
    """普通字号散文里，这个分支根本到不了。

    头部是「连接词前面那一段」，而抽取用的前缀部分止于**第一个形式词
    之前**：`中国联通集团由华为技术有限公司中标。` 的头部是「中国联通」，
    「集团」在形式词那一侧，所以「中国联通集团」这样的写法
    **触发不了**这条守卫。
    """
    from entities import _connector_cut_allowed

    assert _connector_cut_allowed(
        "中国联通集团由", 6, True, "华为技术有限公司") is False
    # 头部止于形式词之前：前缀部分是「中国联通」，形式词「集团」不在其中，
    # 于是这一段不是完整字号，守卫不生效，连接词照裁。
    assert _connector_cut_allowed(
        "中国联通由", 4, True, "华为技术有限公司") is True
    assert extract_company_names("中国联通集团由华为技术有限公司中标。") == [
        "中国联通集团", "华为技术有限公司",
    ]


def test_the_format_rules_do_not_claim_a_wordmark_triggers_the_guard():
    """规则文档不得再说「中国联通集团」会触发这条守卫。"""
    text = _format_rules()
    assert "如「中国联通集团」" not in text
    # 说的是「到不了这条规则」，并说明它保护的是括号
    assert "到不了这条规则" in text
    assert "括号" in text


def test_the_known_limitations_state_the_country_guard_is_a_bracket_protection():
    body = _known_limitations()
    assert "括号" in body
    assert "中国联通集团" in body


# --- I-3：行政区划那条规则只在头部生效 ---


def test_the_region_rule_only_applies_when_the_region_is_the_head():
    """行政区划必须在前缀部分的**开头**才挡得住裁剪。

    裸字符串 `海南自由贸易港城有限公司` 的头部是「海南自」，规则生效；
    放进句子里，头部是「本项目由海南自」，行政区划在中间，
    规则不生效——照样被裁。
    """
    assert extract_company_names("海南自由贸易港城有限公司") == [
        "海南自由贸易港城有限公司"
    ]
    assert extract_company_names("本项目由海南自由贸易港城有限公司中标。") == [
        "贸易港城有限公司"
    ]
    assert extract_company_names(
        "中国联通本次项目由海南自由贸易港城有限公司中标。") == [
        "贸易港城有限公司"
    ]


def test_the_format_rules_state_the_region_head_condition():
    """文档要写清楚「行政区划是前缀部分的开头」这个条件。"""
    text = _format_rules()
    assert "行政区划是前缀部分的开头" in text
    assert "本项目由海南自由贸易港城有限公司中标。" in text


# --- 已知局限：字号相同、只差企业形式词 ---


def test_the_equal_core_legal_form_case_is_merged_as_documented():
    """这一条只记录不修：核心字号相同即同一主体，是既定的口径。"""
    for pair in (("中国建筑集团有限公司", "中国建筑股份有限公司"),
                 ("中国石油集团有限公司", "中国石油股份有限公司")):
        groups = group_variants(list(pair))
        assert len(groups) == 1, (pair, groups)
        assert groups[0]["names"] == list(pair), (pair, groups)


def test_the_known_limitations_state_the_equal_core_legal_form_case():
    body = _known_limitations()
    assert "中国建筑集团" in body
    assert "中国建筑股份" in body
    assert "登记" in body
    assert "人工" in body


# --- M-4 / M-5：pip 缓存目录 ---


def test_the_powershell_installer_pins_the_pip_cache_dir():
    """install.ps1 也必须把 pip 的缓存目录钉在虚拟环境里。

    spec §11.1：两个安装器行为一致。install.sh 早就钉了，
    install.ps1 一次也没钉——下一个「pip 把缓存算成 cwd 相对路径」
    的平台上就只会中一个安装器。
    """
    text = (INSTALL / "install.ps1").read_text(encoding="utf-8-sig")
    assert "PIP_CACHE_DIR" in text
    assert "$env:PIP_CACHE_DIR" in text

    values = [
        line.split("=", 1)[1].strip()
        for line in text.splitlines()
        if line.strip().startswith("$env:PIP_CACHE_DIR")
    ]
    assert values, "没有设置 PIP_CACHE_DIR"
    for value in values:
        assert ".pip-cache" in value, value
        assert "$VenvDir" in value, value

    # 必须在建虚拟环境之前设好：venv 自带的 ensurepip 也会用 pip 的缓存
    assert text.index("$env:PIP_CACHE_DIR") < text.index("-m venv")


def test_the_bash_comment_does_not_assert_an_unverified_mechanism():
    """install.sh 的注释不得断言一个在本机复现不出来的机制。

    钉死缓存目录这件事是对的、也与平台无关；但「platformdirs 会退化成
    cwd 相对路径」这个因果解释在 Windows 上复现不出来（pip 26.3 总是
    算出绝对路径），注释不能把它说成本机上确凿的事实。
    """
    text = (INSTALL / "install.sh").read_text(encoding="utf-8")
    assert "export PIP_CACHE_DIR=" in text

    comment = "\n".join(
        line for line in text.splitlines()
        if line.lstrip().startswith("#")
    )
    # 旧写法把这句因果说成了无条件的断言
    assert "pip 用 platformdirs 算缓存目录：当 HOME/USERPROFILE" not in comment, \
        comment
    assert "依平台而异" in comment, comment
    assert "复现不出来" in comment, comment


# --- M-6：状态查询的输出顺序 ---


def _scratch_home(tmp_path: Path) -> Path:
    root = tmp_path / "home"
    (root / ".claude").mkdir(parents=True, exist_ok=True)
    return root


def test_the_status_output_prints_the_root_before_the_caveat(tmp_path):
    """先把解析出来的根目录摆出来，再说「本次只读」。

    话说在事实前面读起来别扭：先看到「未指定 --target-root…」，
    再看到根目录。
    """
    home = _scratch_home(tmp_path)
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env.pop("DOC_CHECK_TARGET_ROOT", None)

    proc = subprocess.run(
        [sys.executable, str(INSTALL / "install_skill.py"),
         "--repo-root", str(ROOT), "--venv-py", sys.executable, "--status"],
        capture_output=True, env=env, cwd=str(ROOT),
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    text = proc.stdout.decode("utf-8", "replace")

    root_at = text.index("根目录（~ 展开到）：")
    caveat_at = text.index("未指定 --target-root")
    assert root_at < caveat_at, text
    assert "doc-check 安装状态：干净" in text or "残留" in text, text


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
