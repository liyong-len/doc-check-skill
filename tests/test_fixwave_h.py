"""修复波 H 的回归测试。

覆盖：
- C-1 还原名把句子碎片还原成了公司名（`方是北京华信科技有限公司`、
      `要求由北京华信科技有限公司`）：还原名只认**切在同一个连接词上**
      的那个更宽候选。
- C-2 还原名仍会把两家不同的公司并成一家
      （`北方自由贸易港城有限公司` 与 `贸易港城有限公司`）：
      多出来的那部分是一段专有名词时不合并，只报疑似级的 P0。
- I-1 一家公司、多种句子前缀，不得报出假的 P0「主体串写」。
- I-3 install.ps1 不得把 PIP_CACHE_DIR 留在调用方的会话里。
- M-4 还原名必须是一个像公司名的名字，不能是句子碎片。
- C-3 规则文档按代码的实际行为重写：还原名的选择规则、还原名
      「不等于公司名」、残余污染的已知局限。

安装相关的测试一律对着临时的 HOME 与仓库副本跑，绝不碰用户的智能体目录。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from analyze import analyze
from entities import (
    _NAME_CONNECTORS,
    _SENTENCE_CONNECTORS,
    extract_company_names,
    extract_company_occurrences,
    group_variants,
    same_entity,
)

ROOT = Path(__file__).resolve().parent.parent
FORMAT_RULES = ROOT / "references" / "format-rules.md"
INSTALL = ROOT / "install"

PS51 = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")


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


# 一家真公司，十二种句子里常见的写法。
# 每一句里出现的公司全称都是同一个。
COMPANY = "北京华信科技有限公司"
PROSE_CASES = [
    "本文件由北京华信科技有限公司编制。",
    "受托方是北京华信科技有限公司。",
    "根据采购方要求由北京华信科技有限公司负责实施。",
    "经甲方确认后由北京华信科技有限公司实施。",
    "甲方指定的实施单位为北京华信科技有限公司。",
    "乙方认可后由北京华信科技有限公司提供。",
    "北京华信科技有限公司的联系方式如下。",
    "中标人为北京华信科技有限公司。",
    "本项目的实施单位是北京华信科技有限公司。",
    "联系方式：北京华信科技有限公司。",
    "投标人：北京华信科技有限公司。",
    "乙方：北京华信科技有限公司。",
]


# --- C-1：还原名不得把句子碎片还原成公司名 ---


def test_the_extractor_never_publishes_a_sentence_fragment_as_a_name():
    """四种写法里，抽出来的名字必须就是那家公司。

    修复前：
    - `受托方是北京华信科技有限公司` 还原出 `方是北京华信科技有限公司`
    - `根据采购方要求由北京华信科技有限公司负责实施` 还原出
      `要求由北京华信科技有限公司`

    还原名是**同一个前缀有不止一个合格切分**时更宽的那一个。两个字号的
    两个切点落在同一个连接词上（`本项目由中国自由贸易港城` 的两个「由」），
    才说明更宽的那一段是同一个字号的更宽视角；切点落在**不同**的连接词上
    （`受托方是北京华信科技` 的「受托」与「是」），更宽的那一段是另一段
    句子碎片，还原它就凭空造出了一个并不存在的公司。
    """
    assert extract_company_names("本文件由北京华信科技有限公司编制。") == [
        "北京华信科技有限公司"
    ]
    assert extract_company_names("受托方是北京华信科技有限公司。") == [
        "北京华信科技有限公司"
    ]
    assert extract_company_names(
        "根据采购方要求由北京华信科技有限公司负责实施。") == [
        "北京华信科技有限公司"
    ]
    # 合法的还原必须原样保留：两个字号的两个切点切在同一个「由」上。
    assert extract_company_names("本项目由中国自由贸易港城有限公司中标。") == [
        "贸易港城有限公司"
    ]
    assert extract_company_occurrences(
        "本项目由中国自由贸易港城有限公司中标。") == [
        ("贸易港城有限公司", "中国自由贸易港城有限公司")
    ]


def test_the_restored_name_of_a_polluted_prefix_is_not_published():
    """两个被污染的还原名，一个都不许出现。"""
    for sentence in (
        "受托方是北京华信科技有限公司。",
        "根据采购方要求由北京华信科技有限公司负责实施。",
    ):
        for _trimmed, restored in extract_company_occurrences(sentence):
            assert restored == "北京华信科技有限公司", (sentence, restored)


# --- M-4：还原名必须是一个像公司名的名字 ---


def test_the_restored_name_must_be_a_plausible_company_name():
    """还原名必须等于那个像公司名的全称，不能是句子碎片。

    修复前 `受托方是北京华信科技有限公司` 的还原名是
    `方是北京华信科技有限公司`：它是句子碎片，不是公司名——它会让工具
    报出一条确定级的「同一主体出现 2 种名称写法」，让用户去统一一个
    并不存在的公司。

    这里用「等于那个全称」作判据，而不是查词表：句子碎片与字号的差别
    在中文里常常只是「由」在「自由」里的位置，词表判不了。
    """
    for sentence in PROSE_CASES:
        occurrences = extract_company_occurrences(sentence)
        assert occurrences, sentence
        for trimmed, restored in occurrences:
            expected = COMPANY if COMPANY in sentence else None
            if expected is None:
                continue
            assert restored == expected, (sentence, trimmed, restored)


def test_a_restored_name_must_not_carry_a_connector_or_a_fragment():
    """还原名与裁剪后的名字不同时，多出来的那一段不得是句子碎片。

    这是给「还原名必须像公司名」加的一道网：多出来的那一段里
    不该出现字号级连接词（「是」「和」「为」…），整段里也不该出现
    句子级连接词（「由」除外——它在「自由」这类字号中间）。
    """
    for sentence in PROSE_CASES + [
        "本项目由中国自由贸易港城有限公司中标。",
        "本项目由北方自由贸易港城有限公司中标。",
    ]:
        for trimmed, restored in extract_company_occurrences(sentence):
            if restored == trimmed:
                continue
            assert restored.endswith(trimmed), (sentence, trimmed, restored)
            head = restored[: len(restored) - len(trimmed)]
            assert not any(w in head for w in _NAME_CONNECTORS), (
                sentence, restored, head)
            assert not any(
                w in restored for w in _SENTENCE_CONNECTORS if w != "由"
            ), (sentence, restored)


# --- I-1：一家公司、多种句子前缀，不得报出假的 P0 ---


def test_one_company_with_many_sentence_prefixes_is_one_subject():
    """七句话、十二种前缀，同一家公司：一个主体，没有 P0，也没有 P1。

    修复前，句子前缀被还原成了公司名的一部分（`方是北京华信科技…`），
    文档因此被拆成几个主体，报出一条假的 P0「主体串写」，还附带一条
    确定级的 P1「主体名称」——后者正是本工具明令禁止的确定级假阳性。
    """
    docs = [_doc("a.docx", PROSE_CASES)]
    result = analyze(docs)

    per_file = result["entities"]["per_file"]["a.docx"]
    assert set(per_file) == {COMPANY}, per_file

    groups = result["entities"]["variants"]
    assert len(groups) == 1, groups
    assert groups[0]["names"] == [COMPANY], groups

    issues = result["issues"]
    assert [i for i in issues if i["category"] == "主体串写"] == [], issues
    assert [i for i in issues if i["category"] == "主体名称"] == [], issues


# --- C-2：两家不同的公司不能被并成一家 ---


def test_the_truncated_name_and_the_restored_name_stay_separate():
    """散文里还原出来的名字与裸字符串裁出来的残缺名，必须是两家。

    `本项目由北方自由贸易港城有限公司中标。` 还原出
    `北方自由贸易港城有限公司`；`中国自由贸易港城有限公司的联系方式如下。`
    是裸字符串，还原不出来，只能用 `贸易港城有限公司`。

    修复前两者被并成一个主体（多出来的 `北方自由` 被当成「干净的」头部），
    报出确定级的 P1「主体名称」，让用户去统一两家不同的公司。
    """
    docs = [_doc("a.docx", [
        "本项目由北方自由贸易港城有限公司中标。",
        "中国自由贸易港城有限公司的联系方式如下。",
    ])]
    result = analyze(docs)

    per_file = result["entities"]["per_file"]["a.docx"]
    assert per_file == [
        "北方自由贸易港城有限公司", "贸易港城有限公司",
    ], per_file

    groups = result["entities"]["variants"]
    assert len(groups) == 2, groups

    issues = result["issues"]
    assert [i for i in issues if i["category"] == "主体名称"] == [], issues

    mixed = [i for i in issues if i["category"] == "主体串写"]
    assert len(mixed) == 1, issues
    assert mixed[0]["severity"] == "P0"
    assert mixed[0]["confidence"] == "疑似 · 需人工核实"
    assert "北方自由贸易港城有限公司" in mixed[0]["description"], mixed[0]


def test_a_proper_noun_head_is_not_a_writing_difference():
    """多出来的那部分是一段专有名词时，不是同一家公司。

    `北方自由` 是另一家公司的字号的一部分，文档里没有任何依据说
    `北方自由贸易港城有限公司` 与 `贸易港城有限公司` 是同一家。
    """
    assert not same_entity("北方自由贸易港城有限公司", "贸易港城有限公司")
    groups = group_variants([
        "北方自由贸易港城有限公司", "贸易港城有限公司",
    ])
    assert len(groups) == 2, groups


def test_a_fragment_head_is_still_a_writing_difference():
    """多出来的那部分确实是句子碎片时，仍然算同一家公司。

    这条不能跟着一起改：文档里 `甲方指定的北京华信科技有限公司` 与
    `北京华信科技有限公司` 说的是同一家公司。
    """
    assert same_entity("指定的北京华信科技有限公司", "北京华信科技有限公司")


# --- I-3：install.ps1 不得把 PIP_CACHE_DIR 留在调用方的会话里 ---


def _powershell_exe() -> Path | None:
    if PS51.exists():
        return PS51
    found = shutil.which("pwsh")
    return Path(found) if found else None


def _make_cmd_stub(path: Path, version: str) -> None:
    path.write_bytes(
        ("@echo off\r\necho %s\r\nexit /b 0\r\n" % version).encode("ascii")
    )


def _installer_probe(installer: Path) -> str:
    """在**同一个会话**里调用安装器，之后读会话里的 PIP_CACHE_DIR。

    安装器里有 `exit`，直接用 `-Command "& install.ps1; ..."` 调用时
    整个会话会被带走，读不到变量。因此把安装器放进一个 runspace 里跑：
    runspace 与外层共享同一个进程的环境，`exit` 只结束 runspace 里的
    那段脚本。
    """
    return (
        "$ErrorActionPreference = 'Continue'\n"
        "$rs = [runspacefactory]::CreateRunspace()\n"
        "$rs.Open()\n"
        "$ps = [powershell]::Create()\n"
        "$ps.Runspace = $rs\n"
        "$null = $ps.AddScript(\"& '%s'\")\n"
        "$null = $ps.Invoke()\n"
        "$ps.Dispose()\n"
        "$rs.Close()\n"
        "Write-Output ('AFTER=[' + $env:PIP_CACHE_DIR + ']')\n"
        % installer
    )


@pytest.mark.skipif(_powershell_exe() is None, reason="没有 PowerShell")
@pytest.mark.parametrize("caller_value", [None, "调用方原来的值"])
def test_the_powershell_installer_does_not_leak_the_pip_cache_dir(
        tmp_path, caller_value):
    """install.ps1 用完 PIP_CACHE_DIR 必须把它还原回去。

    在 PowerShell 里给 $env: 赋值改的是**进程**的环境。脚本被
    `powershell -Command "& install.ps1; ..."` 这样调用时，脚本与调用方
    在同一个会话里，变量就留在调用方的会话里了——安装器不该改调用方的
    环境。

    install.sh 用的是 export，那边是子进程的环境，天然不漏；两个安装器
    在这一条上**本来就不一样**。
    """
    shell = _powershell_exe()
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    _make_cmd_stub(stub_dir / "python.cmd", "3.14")

    repo = tmp_path / "repo"
    shutil.copytree(INSTALL, repo / "install")
    # 虚拟环境已经存在，但里面的解释器是那个跑不起来的桩：
    # 安装器走到装依赖那一步就跑不动了，正好停在钉缓存目录之后。
    (repo / ".venv" / "Scripts").mkdir(parents=True)
    shutil.copyfile(stub_dir / "python.cmd",
                    repo / ".venv" / "Scripts" / "python.exe")

    home = tmp_path / "home"
    home.mkdir()

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["PATH"] = str(stub_dir) + os.pathsep + env.get("PATH", "")
    env.pop("DOC_CHECK_TARGET_ROOT", None)
    if caller_value is None:
        env.pop("PIP_CACHE_DIR", None)
    else:
        env["PIP_CACHE_DIR"] = caller_value

    probe = tmp_path / "probe.ps1"
    probe.write_text(
        _installer_probe(repo / "install" / "install.ps1"),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [str(shell), "-NoProfile", "-File", str(probe)],
        capture_output=True, env=env, cwd=str(tmp_path),
    )
    out = (proc.stdout.decode("utf-8", "replace")
           + proc.stderr.decode("utf-8", "replace"))

    expected = "AFTER=[%s]" % (caller_value or "")
    assert expected in out, out
    # 桩解释器跑不起来，什么都不该被装到用户的家目录里去
    for name in (".claude", ".codex", "DoubaoWork", ".dsh"):
        assert not (home / name).exists(), f"不该创建 {name}"


def test_the_powershell_installer_restores_the_cache_dir_in_the_script():
    """静态检查：变量必须在 try 里设、在 finally 里还原。

    行为测试（上面那条）证明脚本跑完之后调用方的环境是干净的；这一条
    保证还原动作写在脚本里，而不是靠碰巧。
    """
    text = (INSTALL / "install.ps1").read_text(encoding="utf-8-sig")
    assert "Test-Path Env:PIP_CACHE_DIR" in text
    assert "SetEnvironmentVariable('PIP_CACHE_DIR'" in text
    # 钉缓存目录的那一行必须在**最后那个** finally（还原用的那个）之前
    assert text.index("$env:PIP_CACHE_DIR = ") < text.rindex("} finally {")


# --- C-3：规则文档按代码的实际行为重写 ---


def test_the_rules_describe_the_same_connector_selection_rule():
    """文档要写清楚还原名的选择规则是「更宽**且切在同一个连接词上**」。"""
    text = _format_rules()
    assert "切在同一个连接词上" in text
    # 旧的说法（「更宽的那一段」）单独出现时会误导人
    assert "把**更宽的那一段**还回来当还原名" not in text
    assert "把更宽的那一段还回来" not in text


def test_the_rules_do_not_claim_the_restored_name_is_always_a_company_name():
    """文档不得再说「还原名不会报出确定级的建议」这种话。

    还原名是文档里逐字存在的字符串，**不等于**它是一个公司名；
    确定级的 P1「主体名称」确实可能出现。
    """
    text = _format_rules()
    assert "两个名字都是文档里逐字存在的字符串，还原名不是凭空造出来的" not in text
    assert "还原名是文档里逐字存在的字符串，不等于它是一个公司名" in text
    assert "确定级的 P1「主体名称」" in text
    # 旧的说法：把「不会报出确定级建议」当成还原名的一般性质
    assert "也**不会**报出确定级的「统一名称写法」建议" not in text


def test_the_known_limitations_record_the_residual_pollution():
    """残余污染必须有已知局限条目，不能只写在正文里。"""
    body = _known_limitations()
    assert "还原名仍可能是句子碎片" in body
    assert "受托方是北京华信科技有限公司" in body
    assert "要求由北京华信科技有限公司" in body


def test_the_known_limitations_state_the_registry_distinct_enterprise_forms():
    """有限公司与有限责任公司在登记实践上是不同的企业形式。

    确定级的「统一名称写法」建议对这类情况可能是错的：那是两家
    分别注册的独立公司，只能由人工核对企业登记信息。
    """
    body = _known_limitations()
    assert "登记实践" in body
    assert "不同的企业形式" in body
    assert "人工核对企业登记信息" in body


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
