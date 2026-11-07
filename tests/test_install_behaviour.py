"""安装器的行为测试。

这些测试跑真实的安装脚本（Windows PowerShell 5.1 与 bash），不靠 grep 脚本源码：
字符串 grep 只能证明「脚本里写着这句话」，证明不了「脚本真的这么做」——
`AGENT.md` 就算只出现在注释里，grep 也能过。

所有安装都对着临时的 HOME 与临时的仓库副本跑，绝不碰用户的智能体目录。
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "install"
SAMPLES = Path(__file__).resolve().parent / "samples"

PS51 = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")

NO_PYTHON_MESSAGE = "未找到 Python 3.9 及以上解释器。请安装 Python 3.11 或 3.12 后重试。"


# --- 运行环境探针 ---


def _has_powershell() -> bool:
    return bool(_powershell_exes())


def _powershell_exes() -> list[Path]:
    """本机可用的 PowerShell。

    Windows PowerShell 5.1 是 README 里写的受支持路径（`powershell
    -ExecutionPolicy Bypass -File install/install.ps1`），pwsh 7 也要能用。
    """
    shells: list[Path] = []
    if PS51.exists():
        shells.append(PS51)
    pwsh = shutil.which("pwsh")
    if pwsh:
        shells.append(Path(pwsh))
    return shells


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


def _text(data: bytes) -> str:
    """把子进程的输出解成文本。PowerShell 重定向时可能用系统码页。"""
    for encoding in ("utf-8", "gbk", "mbcs"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


# --- 测试用的假解释器 ---


def _make_cmd_stub(path: Path, version: str | None, stderr_line: str = "") -> None:
    """Windows 批处理桩。版本打到 stdout，可选再往 stderr 写一行。"""
    lines = ["@echo off"]
    if stderr_line:
        lines.append(f"echo {stderr_line} 1>&2")
    if version:
        lines.append(f"echo {version}")
    lines.append("exit /b 0")
    path.write_text("\r\n".join(lines) + "\r\n", encoding="ascii")


def _make_sh_stub(path: Path, version: str | None, stderr_line: str = "") -> None:
    """POSIX shell 桩。版本打到 stdout，可选再往 stderr 写一行。"""
    lines = ["#!/bin/sh"]
    if stderr_line:
        lines.append(f"echo '{stderr_line}' >&2")
    if version:
        lines.append(f"echo '{version}'")
    lines.append("exit 0")
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    path.chmod(0o755)


# 候选解释器的假版本。顺序写错时，两个安装器会挑到不同的那个。
STUB_VERSIONS = {
    "py": "3.14",
    "python3.12": "3.12",
    "python3.11": "3.11",
    "python3.13": "3.13",
    "python3": "3.10",
    "python": "3.9",
}


def _stub_env(home: Path, path_value: str) -> dict:
    """子进程环境：HOME 与 USERPROFILE 指向临时目录，PATH 只留桩目录。"""
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["PATH"] = path_value
    return env


def _repo_copy(tmp_path: Path, name: str = "repo") -> Path:
    """把 install/ 复制到临时目录，仓库根目录随之变成临时目录。"""
    repo = tmp_path / name
    shutil.copytree(INSTALL, repo / "install")
    return repo


def _assert_nothing_installed(home: Path, repo: Path) -> None:
    """安装没走到装技能那一步时，什么都不该留下。"""
    assert not (repo / ".venv").exists(), "不该留下虚拟环境"
    for name in (".claude", ".codex", "DoubaoWork", ".dsh"):
        assert not (home / name).exists(), f"不该创建 {name}"


# --- 解释器探测 ---


@pytest.mark.skipif(not _has_powershell(), reason="没有 PowerShell")
@pytest.mark.parametrize("shell", _powershell_exes(), ids=lambda p: p.name)
def test_powershell_accepts_chatty_but_working_interpreter(tmp_path, shell):
    """PS 5.1 下，stderr 上写一句提醒的 Python 必须被接受。

    Windows PowerShell 5.1 把原生命令的 stderr 变成终止性的 NativeCommandError，
    $ErrorActionPreference=\"Stop\" 时整个探测会被当成失败：
    一个只是「启动时提醒一句」的 Python 就被判成没装 Python。
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    _make_cmd_stub(stub_dir / "python.cmd", "3.14", stderr_line="benign startup notice")
    home = tmp_path / "home"
    home.mkdir()
    repo = _repo_copy(tmp_path)

    proc = subprocess.run(
        [str(shell), "-ExecutionPolicy", "Bypass", "-File", str(repo / "install" / "install.ps1")],
        capture_output=True,
        env=_stub_env(home, str(stub_dir)),
        cwd=str(tmp_path),
    )
    out = _text(proc.stdout) + _text(proc.stderr)

    assert NO_PYTHON_MESSAGE not in out, out
    assert "使用解释器：python  (Python 3.14)" in out, out
    # 探测通过之后才会往下走：虚拟环境建不出来是下一步的事。
    assert "虚拟环境创建失败" in out, out
    _assert_nothing_installed(home, repo)


@pytest.mark.skipif(not _has_powershell(), reason="没有 PowerShell")
@pytest.mark.parametrize("shell", _powershell_exes(), ids=lambda p: p.name)
def test_powershell_ignores_version_printed_on_stderr(tmp_path, shell):
    """版本号只出现在 stderr 上时必须判为不可用。

    判定依据只有标准输出里的版本号：stderr 上的任何内容都不参与判断。
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    _make_cmd_stub(stub_dir / "python.cmd", None, stderr_line="3.14")
    home = tmp_path / "home"
    home.mkdir()
    repo = _repo_copy(tmp_path)

    proc = subprocess.run(
        [str(shell), "-ExecutionPolicy", "Bypass", "-File", str(repo / "install" / "install.ps1")],
        capture_output=True,
        env=_stub_env(home, str(stub_dir)),
        cwd=str(tmp_path),
    )
    out = _text(proc.stdout) + _text(proc.stderr)

    assert proc.returncode == 1
    assert NO_PYTHON_MESSAGE in out, out
    _assert_nothing_installed(home, repo)


def test_bash_accepts_chatty_but_working_interpreter(tmp_path):
    """bash 侧同样的场景：stderr 上有话不影响判定。"""
    bash = _bash_exe()
    if not bash:
        pytest.skip("没有 bash")
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    _make_sh_stub(stub_dir / "python", "3.14", stderr_line="benign startup notice")
    home = tmp_path / "home"
    home.mkdir()
    repo = _repo_copy(tmp_path)

    proc = subprocess.run(
        [bash, str(repo / "install" / "install.sh")],
        capture_output=True,
        env=_stub_env(home, str(stub_dir)),
        cwd=str(tmp_path),
    )
    out = _text(proc.stdout) + _text(proc.stderr)

    assert NO_PYTHON_MESSAGE not in out, out
    assert "使用解释器：python  (Python 3.14)" in out, out
    _assert_nothing_installed(home, repo)


# --- 一个 Python 都没有时什么都不该留下 ---


def test_bash_without_python_creates_nothing(tmp_path):
    """探测不到 Python 时，安装器必须什么都不做就退出。"""
    bash = _bash_exe()
    if not bash:
        pytest.skip("没有 bash")
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    repo = _repo_copy(tmp_path)

    proc = subprocess.run(
        [bash, str(repo / "install" / "install.sh")],
        capture_output=True,
        env=_stub_env(home, str(empty_bin)),
        cwd=str(tmp_path),
    )
    out = _text(proc.stdout) + _text(proc.stderr)

    assert proc.returncode == 1
    assert NO_PYTHON_MESSAGE in out, out
    _assert_nothing_installed(home, repo)


@pytest.mark.skipif(not _has_powershell(), reason="没有 PowerShell")
@pytest.mark.parametrize("shell", _powershell_exes(), ids=lambda p: p.name)
def test_powershell_without_python_creates_nothing(tmp_path, shell):
    """PowerShell 侧同上：探测不到 Python 时什么都不做就退出。"""
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    repo = _repo_copy(tmp_path)

    proc = subprocess.run(
        [str(shell), "-ExecutionPolicy", "Bypass", "-File", str(repo / "install" / "install.ps1")],
        capture_output=True,
        env=_stub_env(home, str(empty_bin)),
        cwd=str(tmp_path),
    )
    out = _text(proc.stdout) + _text(proc.stderr)

    assert proc.returncode == 1
    assert NO_PYTHON_MESSAGE in out, out
    _assert_nothing_installed(home, repo)


# --- 两个安装器挑同一个解释器 ---


def test_both_installers_pick_the_same_candidate(tmp_path):
    """两个安装器必须按同一个顺序挑解释器。

    顺序不一致的后果很具体：Windows 上先撞上 python3（常常是 3.13/3.14），
    「优先 3.11/3.12」就没了，而 lxml 与 pdfplumber 恰恰在最新版本上缺轮子。
    """
    bash = _bash_exe()
    home = tmp_path / "home"
    home.mkdir()

    results = {}

    for shell in _powershell_exes():
        stub_dir = tmp_path / f"ps-bin-{shell.name}"
        stub_dir.mkdir()
        for name, version in STUB_VERSIONS.items():
            _make_cmd_stub(stub_dir / f"{name}.cmd", version)
        repo = _repo_copy(tmp_path, f"repo-{shell.name}")
        proc = subprocess.run(
            [str(shell), "-ExecutionPolicy", "Bypass", "-File",
             str(repo / "install" / "install.ps1")],
            capture_output=True,
            env=_stub_env(home, str(stub_dir)),
            cwd=str(tmp_path),
        )
        results[f"install.ps1 ({shell.name})"] = _text(proc.stdout) + _text(proc.stderr)

    if bash:
        stub_dir = tmp_path / "sh-bin"
        stub_dir.mkdir()
        for name, version in STUB_VERSIONS.items():
            _make_sh_stub(stub_dir / name, version)
        repo = tmp_path / "repo-sh"
        shutil.copytree(INSTALL, repo / "install")
        proc = subprocess.run(
            [bash, str(repo / "install" / "install.sh")],
            capture_output=True,
            env=_stub_env(home, str(stub_dir)),
            cwd=str(tmp_path),
        )
        results["install.sh"] = _text(proc.stdout) + _text(proc.stderr)

    assert results, "两个安装器都没能运行"
    for name, out in results.items():
        assert "使用解释器：py -3.12  (Python 3.14)" in out, f"{name}: {out}"

    picked = {
        re.search(r"使用解释器：(\S+)", out).group(1) for out in results.values()
    }
    assert len(picked) == 1, f"两个安装器挑到了不同的解释器：{results}"


# --- 参数是显式的 ---


def _run_sh(repo: Path, home: Path, args: list[str]) -> subprocess.CompletedProcess:
    bash = _bash_exe()
    empty = home / "empty-bin"
    empty.mkdir(exist_ok=True)
    return subprocess.run(
        [bash, str(repo / "install" / "install.sh"), *args],
        capture_output=True,
        env=_stub_env(home, str(empty)),
        cwd=str(repo.parent),
    )


def test_bash_rejects_unknown_argument(tmp_path):
    """拼错的参数必须报错退出，不能被静默当成正常安装。"""
    bash = _bash_exe()
    if not bash:
        pytest.skip("没有 bash")
    home = tmp_path / "home"
    home.mkdir()
    repo = _repo_copy(tmp_path)

    proc = _run_sh(repo, home, ["--updtae"])
    out = _text(proc.stdout) + _text(proc.stderr)
    assert proc.returncode == 2, out
    assert "未知参数：--updtae" in out, out


@pytest.mark.skipif(not _has_powershell(), reason="没有 PowerShell")
@pytest.mark.parametrize("shell", _powershell_exes(), ids=lambda p: p.name)
def test_powershell_rejects_unknown_argument(tmp_path, shell):
    """拼错的参数必须报错退出，不能被静默当成正常安装。"""
    home = tmp_path / "home"
    home.mkdir()
    repo = _repo_copy(tmp_path)
    empty = tmp_path / "empty-bin"
    empty.mkdir()

    proc = subprocess.run(
        [str(shell), "-ExecutionPolicy", "Bypass", "-File",
         str(repo / "install" / "install.ps1"), "--updtae"],
        capture_output=True,
        env=_stub_env(home, str(empty)),
        cwd=str(tmp_path),
    )
    out = _text(proc.stdout) + _text(proc.stderr)
    assert proc.returncode == 2, out
    assert "未知参数：--updtae" in out, out


def test_bash_update_flag_is_accepted_and_announced(tmp_path):
    """--update 必须被明确接受，并说清楚自己在干什么。"""
    bash = _bash_exe()
    if not bash:
        pytest.skip("没有 bash")
    home = tmp_path / "home"
    home.mkdir()
    repo = _repo_copy(tmp_path)

    proc = _run_sh(repo, home, ["--update"])
    out = _text(proc.stdout) + _text(proc.stderr)
    # 没有 Python 时会停在探测那一步，但模式说明必须已经打出来。
    assert "更新" in out, out
    assert proc.returncode == 1, out


# --- 文件编码 ---


def test_install_ps1_keeps_utf8_bom():
    """Windows PowerShell 5.1 读无 BOM 的文件时按系统 ANSI 码页解码，中文会成乱码。"""
    data = (INSTALL / "install.ps1").read_bytes()
    assert data.startswith(b"\xef\xbb\xbf"), "install.ps1 必须带 UTF-8 BOM"


def test_install_sh_has_no_carriage_return():
    """CRLF 的 shell 脚本在 Git Bash 与 Linux 下会因为 shebang 多一个 \\r 而跑不起来。"""
    assert b"\r" not in (INSTALL / "install.sh").read_bytes()


def test_install_sh_is_executable_in_git():
    """install.sh 必须带可执行位入库，否则 ./install/install.sh 报 Permission denied。

    Windows 上文件系统没有可执行位，只能看仓库里记录的模式。
    """
    git = shutil.which("git")
    if not git:
        pytest.skip("没有 git")
    proc = subprocess.run(
        [git, "ls-files", "-s", "install/install.sh"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.split()[0] == "100755", proc.stdout


def test_installed_files_have_no_bom(tmp_path):
    """安装器写出来的文件不带 BOM。"""
    skill_dir = _install_skill(tmp_path)
    for name in ["SKILL.md", "AGENT.md", "AGENTS.md", "python-path.txt"]:
        data = (skill_dir / name).read_bytes()
        assert not data.startswith(b"\xef\xbb\xbf"), f"{name} 不该带 BOM"


def test_copied_text_files_have_no_bom():
    """被复制的规则文档与脚本本身也不带 BOM（复制是逐字节的，源头不能带）。"""
    for path in sorted((ROOT / "scripts").rglob("*.py")):
        assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path
    for path in sorted((ROOT / "references").glob("*.md")):
        assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


# --- 装出来的技能必须能用 ---


def _install_skill(tmp_path: Path, venv_py: str | None = None) -> Path:
    """把技能装到临时 HOME 下的 Claude Code 技能目录，返回技能目录。"""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    interpreter = venv_py or sys.executable
    proc = subprocess.run(
        [interpreter, str(INSTALL / "install_skill.py"),
         "--repo-root", str(ROOT), "--venv-py", interpreter],
        capture_output=True,
        env=env,
        cwd=str(tmp_path),
    )
    assert proc.returncode == 0, _text(proc.stdout) + _text(proc.stderr)
    return home / ".claude" / "skills" / "doc-check"


def test_installed_entry_file_points_at_interpreter_and_scripts(tmp_path):
    """装好的入口文件必须自带绝对路径的解释器与脚本位置。

    仓库里的 SKILL.md 写的是相对路径（python scripts/prepare.py）：
    装到智能体目录后那套相对路径指向用户当前的工作目录，智能体照抄必然失败。
    """
    skill_dir = _install_skill(tmp_path)
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")

    match = re.search(r'"([^"]+)"\s+"([^"]+)/scripts/prepare\.py"', text)
    assert match, "入口文件里的阶段①命令没有绝对路径"
    interpreter, script_root = match.groups()
    assert Path(interpreter).exists(), interpreter
    assert Path(script_root) == skill_dir, script_root
    assert (skill_dir / "scripts" / "prepare.py").exists()

    # python-path.txt 里就是同一个解释器。
    pointer = (skill_dir / "python-path.txt").read_text(encoding="utf-8").strip()
    assert Path(pointer).resolve() == Path(interpreter).resolve()


def test_installed_entry_command_runs_from_any_working_directory(tmp_path):
    """把装好的入口文件里的阶段①命令搬出来跑，必须能出结果。"""
    skill_dir = _install_skill(tmp_path)
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")

    command = text.split("```bash")[1].split("```")[0].strip()
    command = command.replace("<文件1>", (SAMPLES / "sample_company.docx").as_posix())
    command = command.replace("<文件2>", "")
    command = command.replace("<档位>", "standard")

    work = tmp_path / "elsewhere"
    work.mkdir()
    proc = subprocess.run(
        shlex.split(command, posix=True),
        capture_output=True,
        cwd=str(work),
    )
    assert proc.returncode == 0, _text(proc.stdout) + _text(proc.stderr)
    assert (work / ".doc-check-work" / "chunks.json").exists()


def test_installed_skill_prunes_stale_files(tmp_path):
    """仓库里删掉的文件不能永远留在技能目录里。"""
    skill_dir = _install_skill(tmp_path)
    stale = skill_dir / "scripts" / "stale_script.py"
    stale.write_text("# 仓库里已经没有这个脚本了\n", encoding="utf-8")

    _install_skill(tmp_path)

    assert not stale.exists(), "过时文件没有被清理"


def test_installed_skill_writes_both_agent_note_files(tmp_path):
    """AGENT.md 与 AGENTS.md 都要有，且指向装好的副本。

    AGENT.md 不是任何工具认的约定名，AGENTS.md 才是；
    两个都写，Claude Code 读 SKILL.md，读 AGENTS.md 约定的工具也能找到入口。
    """
    skill_dir = _install_skill(tmp_path)
    note = (skill_dir / "AGENT.md").read_text(encoding="utf-8")
    assert "{{SKILL_DIR}}" not in note
    assert str(skill_dir).replace("\\", "/") in note

    agents = (skill_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert "SKILL.md" in agents
    assert "python-path.txt" in agents
