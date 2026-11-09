"""修复波 F 的回归测试：国家前缀守卫收窄 + 安装器的两处小毛病。

覆盖：
- C-1 「中国」前缀的**开放从句**后面那家公司仍然抽得出来。
      早先那一版把头部「中国联通本次项目」当成字号的一部分，不裁连接词，
      结果从句连同后面那家公司一起被吞成一个并不存在的公司名，
      真正的公司名反而整条丢掉，两家不同的公司还会被并成一家。
- C-1 收窄之后仍然成立的判定：完整字号不裁、行政区划不裁、
      母公司与子公司不并成一家。
- I-1 规则文档与「已知局限」写的是代码的实际行为。
- I-2 端到端：两个不同的公司报 P0 主体串写（疑似），不报 P1 主体名称（确定）。
- M-1 pip 的缓存目录钉死，不落在当前工作目录。
- M-2 只读模式（--dry-run / --status）不说「将写入真实家目录」。

安装相关的测试一律对着临时的 HOME 跑，绝不碰用户的智能体目录。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from analyze import analyze
from entities import extract_company_names, same_entity

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


# --- C-1：国家前缀只挡「完整字号」，开放从句照裁 ---


def test_a_company_after_a_country_clause_is_still_extracted():
    """从句后面那家公司必须抽得出来。

    早先那一版：头部只要以国家前缀开头就不裁连接词，于是
    「中国联通本次项目由华为技术有限公司」被抽成一个并不存在的公司名，
    真正的「华为技术有限公司」反而**整条丢掉**（不是截断，是没有）。
    """
    assert extract_company_names("中国联通本次项目由华为技术有限公司") == [
        "华为技术有限公司"
    ]
    assert extract_company_names("中国联通本次项目委托华为技术有限公司实施。") == [
        "华为技术有限公司"
    ]


def test_the_country_clause_does_not_publish_a_company_that_does_not_exist():
    """报告的主体清单里不能出现那个被吞出来的名字。"""
    names = extract_company_names("中国联通本次项目由华为技术有限公司")
    assert names == ["华为技术有限公司"]
    assert "中国联通本次项目由华为技术有限公司" not in names


def test_a_complete_country_wordmark_is_not_cut():
    """完整字号仍然完整：「中国联合网络通信集团有限公司」是一个字号。"""
    assert extract_company_names("中国联合网络通信集团有限公司") == [
        "中国联合网络通信集团有限公司"
    ]


def test_a_region_head_is_still_not_cut():
    """行政区划那条规则没动过：「海南自由贸易港城有限公司」是完整字号。"""
    assert extract_company_names("海南自由贸易港城有限公司") == [
        "海南自由贸易港城有限公司"
    ]


def test_the_country_guard_still_fires_on_a_complete_wordmark():
    """守卫没有删掉，只是收窄了触发条件。

    头部**本身就是一个完整字号**（「中国联通集团」）→ 句子级连接词不裁；
    头部只是「以国家前缀开头的开放从句」（「中国联通本次项目」）→ 照裁。
    """
    from entities import _connector_cut_allowed

    # 头部「中国联通集团」：完整字号，连接词是字号的一部分
    assert _connector_cut_allowed(
        "中国联通集团由", 6, True, "华为技术有限公司") is False
    # 头部「中国联通本次项目」：开放从句，连接词是句子的成分
    assert _connector_cut_allowed(
        "中国联通本次项目由", 8, True, "华为技术有限公司") is True


def test_a_half_form_word_does_not_block_the_cut():
    """半截形式词（「有限」「股份」「公司」）不算完整字号。

    「中国石油有限」不是一个完整字号——拿它挡住裁剪会发布 一个
    并不存在的公司名（「中国石油有限由华为技术有限公司」），那正是
    这一波要治的病。
    """
    for text in ("中国石油有限由华为技术有限公司中标。",
                 "中国石油股份由华为技术有限公司中标。",
                 "中国分公司由华为技术有限公司中标。"):
        assert extract_company_names(text) == ["华为技术有限公司"], text


def test_the_documented_residuals_are_still_there():
    """两条记录在案的残余代价。

    - 「X为YY公司」多出一个「为」；
    - 头部是开放从句时，字号被裁掉一半。

    两条都是**漏报**（假阴性），不是确定级结论。
    """
    assert extract_company_names("中国联通中标人为华为技术有限公司") == [
        "为华为技术有限公司"
    ]
    assert extract_company_names("中国自由贸易港城有限公司") == [
        "贸易港城有限公司"
    ]


def test_the_country_prefix_still_distinguishes_entities():
    """收窄的是「连接词裁不裁」，不是「国家前缀算不算区分标志」。

    归组那一条（_extra_head_is_clean）一个字没动。
    """
    assert not same_entity(
        "中国联合网络通信集团有限公司", "联合网络通信有限公司")
    assert not same_entity(
        "中国石油化工集团有限公司", "石油化工有限公司")
    assert not same_entity(
        "中国移动通信集团有限公司", "移动通信有限公司")
    assert not same_entity("中国建筑", "中国建筑科技")
    assert same_entity("北京华信科技有限公司", "由北京华信科技有限公司")
    assert not same_entity("联合网络通信有限公司", "网络通信有限公司")


# --- I-2：端到端 ---


def test_two_different_companies_produce_a_p0_not_a_p1():
    """两个不同的公司：P0 主体串写（疑似），没有 P1 主体名称（确定）。

    修复前两句话都被吞成「中国联通本次项目由华为技术…有限公司」，
    两个名字的核心字号相同，被并成一家，报出确定级的
    「同一主体出现 2 种名称写法」——让用户去统一两家公司的名字。
    """
    docs = [_doc("a.docx", [
        "中国联通本次项目由华为技术有限公司中标。",
        "中国联通本次项目由中兴通讯股份有限公司中标。",
    ])]
    issues = analyze(docs)["issues"]

    mixed = [i for i in issues if i["category"] == "主体串写"]
    assert len(mixed) == 1, issues
    assert mixed[0]["severity"] == "P0"
    assert mixed[0]["confidence"] == "疑似 · 需人工核实"

    assert [i for i in issues if i["category"] == "主体名称"] == [], issues


def test_two_different_companies_in_a_real_docx(tmp_path):
    """真实 .docx 端到端：两个主体，报 P0，不报 P1。

    主体清单里必须是两个真公司的名字，不能有那个被吞出来的名字。
    """
    import docx
    from prepare import prepare

    path = tmp_path / "投标文件.docx"
    document = docx.Document()
    document.add_paragraph("中国联通本次项目由华为技术有限公司中标。")
    document.add_paragraph("中国联通本次项目由中兴通讯股份有限公司中标。")
    document.save(str(path))

    work = tmp_path / "work"
    prepare([path], "standard", work)
    consistency = json.loads(
        (work / "consistency.json").read_text(encoding="utf-8"))
    issues = consistency["issues"]

    assert [i for i in issues if i["category"] == "主体名称"] == [], issues
    mixed = [i for i in issues if i["category"] == "主体串写"]
    assert len(mixed) == 1, issues
    assert mixed[0]["severity"] == "P0"
    assert mixed[0]["confidence"] == "疑似 · 需人工核实"

    names = {n["name"] for n in consistency["entities"]["names"]}
    assert names == {"华为技术有限公司", "中兴通讯股份有限公司"}, names


def test_the_clause_is_not_swallowed_into_the_name_in_a_real_docx(tmp_path):
    """真实 .docx：抽出来的名字里不能带着前面的从句。"""
    import docx
    from prepare import prepare

    path = tmp_path / "投标文件.docx"
    document = docx.Document()
    document.add_paragraph("中国联通本次项目由华为技术有限公司中标。")
    document.save(str(path))

    work = tmp_path / "work"
    prepare([path], "standard", work)
    consistency = json.loads(
        (work / "consistency.json").read_text(encoding="utf-8"))

    per_file = consistency["entities"]["per_file"]["投标文件.docx"]
    assert per_file == ["华为技术有限公司"], per_file


def test_the_same_wordmark_pair_is_extracted_clean():
    """「华为技术有限公司」与「华为技术有限责任公司」：两个干净的名字。

    这两个字号的写法只差一个「责任」。按项目既定的口径，它们是**同一个
    字号的两种写法**（见 references/format-rules.md「主体名称」一节：
    两种写法都是注册过的全称时，文档里没有依据能判断哪一种才是正式写法），
    因此报的是 P1 主体名称（确定），不是 P0 主体串写。

    这里守住的是**另一件事**：两个名字都必须抽干净，不能带着从句，
    也不能因为句子级连接词而把两个公司并成一个。
    """
    docs = [_doc("a.docx", [
        "中国联通本次项目由华为技术有限公司中标。",
        "中国联通本次项目由华为技术有限责任公司中标。",
    ])]
    result = analyze(docs)

    per_file = result["entities"]["per_file"]["a.docx"]
    assert per_file == ["华为技术有限公司", "华为技术有限责任公司"], per_file
    for name in per_file:
        assert not name.startswith("中国联通本次项目"), name

    variants = result["entities"]["variants"]
    assert [v["names"] for v in variants] == [
        ["华为技术有限公司", "华为技术有限责任公司"]
    ], variants

    # 任何一条结论里都不能出现那个被吞出来的名字
    for issue in result["issues"]:
        assert "中国联通本次项目由" not in issue["description"], issue


# --- I-1：规则文档与已知局限必须与代码一致 ---


def test_the_format_rules_state_the_narrowed_country_rule():
    """第 6 条要写的是**实际规则**：只有完整字号才挡裁剪。"""
    text = _format_rules()
    assert "完整字号" in text
    assert "开放从句" in text
    assert "中国联通本次项目由华为技术有限公司" in text
    # 旧的说法（头部只要以国家前缀开头就不裁）不能留在文档里
    assert "它前面那段文字以**国家前缀**（「中国」「中华」）开头 → **不裁**" \
        not in text


def test_the_known_limitations_state_the_truncation_cost():
    """开放从句被裁掉一半，是记录在案的漏报。"""
    body = _known_limitations()
    assert "中国自由贸易港城有限公司" in body
    assert "贸易港城有限公司" in body
    assert "漏报" in body
    assert "开放从句" in body


def test_the_known_limitations_state_the_residual_costs():
    """两条残余代价都要写清楚，并且写明是假阴性而不是确定级结论。"""
    body = _known_limitations()
    assert "为华为技术有限公司" in body
    assert "假阴性" in body
    assert "疑似 · 需人工核实" in body


# --- M-1：pip 缓存目录不许落在当前工作目录 ---


def test_the_bash_installer_pins_the_pip_cache_dir():
    """install.sh 必须钉死 PIP_CACHE_DIR。

    pip 用 platformdirs 算缓存目录：HOME/USERPROFILE 指向一个还不存在的
    路径时，它算出来的路径会退化成当前工作目录下的相对路径，
    `pip/cache/http-v2/…` 就落在用户执行安装命令的那个目录里。
    """
    text = (INSTALL / "install.sh").read_text(encoding="utf-8")
    assert "export PIP_CACHE_DIR=" in text

    values = [
        line.split("=", 1)[1].strip().strip('"').strip("'")
        for line in text.splitlines()
        if line.strip().startswith("export PIP_CACHE_DIR=")
    ]
    assert values, "没有导出 PIP_CACHE_DIR"
    for value in values:
        # 缓存目录必须在虚拟环境里，不能是相对路径
        assert value.startswith("$VENV_DIR/"), value

    # 虚拟环境目录本身是绝对路径
    assert 'REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"' in text
    assert 'VENV_DIR="$REPO_ROOT/.venv"' in text


def test_the_pip_cache_dir_is_pinned_before_the_venv_is_created():
    """建虚拟环境时 ensurepip 也会用 pip 的缓存，所以导出必须更早。"""
    text = (INSTALL / "install.sh").read_text(encoding="utf-8")
    assert text.index("export PIP_CACHE_DIR=") < text.index("-m venv")


def test_the_bash_installer_is_still_valid_shell():
    """改过的 install.sh 仍然是合法的 shell 脚本。"""
    bash = _bash_exe()
    if not bash:
        pytest.skip("没有 bash")
    proc = subprocess.run(
        [bash, "-n", str(INSTALL / "install.sh").replace("\\", "/")],
        capture_output=True, cwd=str(ROOT),
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")


# --- M-2：只读模式不说「将写入真实家目录」 ---


def _bash_exe() -> str | None:
    """bash 的可执行路径。

    Git Bash 里的 `which bash` 给出的是 MSYS 路径（/usr/bin/bash），
    Windows 的进程起不来这种路径，要用 cygpath 换成 Windows 路径。
    """
    bash = shutil.which("bash")
    if not bash:
        return None
    cygpath = shutil.which("cygpath")
    if cygpath:
        try:
            out = subprocess.run(
                [cygpath, "-w", bash], capture_output=True, text=True, timeout=30
            )
        except OSError:
            return bash
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    return bash


def _scratch_home(tmp_path: Path) -> Path:
    """一个只装了「Claude Code 已安装」痕迹的临时家目录。"""
    root = tmp_path / "home"
    (root / ".claude").mkdir(parents=True, exist_ok=True)
    return root


def _env_for(home: Path) -> dict:
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env.pop("DOC_CHECK_TARGET_ROOT", None)
    return env


def _run_install(args, env=None):
    proc = subprocess.run(
        [sys.executable, str(INSTALL / "install_skill.py"),
         "--repo-root", str(ROOT), "--venv-py", sys.executable] + list(args),
        capture_output=True, env=env, cwd=str(ROOT),
    )
    return proc, proc.stdout.decode("utf-8", "replace")


def test_the_read_only_modes_do_not_say_they_will_write_to_the_real_home(tmp_path):
    """--dry-run 与 --status 不写任何文件，因此不能说「将写入真实家目录」。"""
    home = _scratch_home(tmp_path)
    for mode in (["--dry-run"], ["--status"]):
        proc, text = _run_install(mode, env=_env_for(home))
        assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
        assert "将写入真实家目录" not in text, (mode, text)
        # 还是要说清楚「正式安装会写真实家目录」
        assert "真实家目录" in text, (mode, text)
        # 还要说清楚这一次不写任何文件
        assert "不写入任何文件" in text or "只读" in text, (mode, text)


def test_a_real_install_still_says_it_writes_to_the_real_home(tmp_path):
    """正式安装那一路仍然照实说「将写入真实家目录」。"""
    home = _scratch_home(tmp_path)
    proc, text = _run_install([], env=_env_for(home))
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert "将写入真实家目录" in text, text
