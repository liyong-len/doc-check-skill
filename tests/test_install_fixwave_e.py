"""修复波 E 的回归测试：安装器的横幅与家目录隔离。

覆盖：
- 写入真实家目录之前必须先打印横幅，横幅点名绝对路径
- 横幅只是一段提示，不是一道闸：不给任何参数也能装成
- 两个安装器（install.sh / install.ps1）的横幅是同一段文字
- I-c 安装测试不得写进用户的真实家目录

所有安装都对着临时的 HOME 跑，绝不碰用户的智能体目录。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "install"

BANNER = "即将写入你的真实家目录"


def _run(args, env=None):
    proc = subprocess.run(
        [sys.executable, str(INSTALL / "install_skill.py"),
         "--repo-root", str(ROOT), "--venv-py", sys.executable] + list(args),
        capture_output=True, env=env, cwd=str(ROOT),
    )
    return proc, proc.stdout.decode("utf-8", "replace")


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


# --- 1. 写进真实家目录之前要有横幅 ---


def test_the_banner_is_printed_before_the_first_write(tmp_path):
    """横幅必须在第一次写盘之前出现。

    装完了再喊，等于没喊：看的人已经没法回头确认装到哪儿去了。
    """
    home = _scratch_home(tmp_path)
    proc, text = _run([], env=_env_for(home))
    assert proc.returncode == 0, text
    assert BANNER in text, text
    assert text.index(BANNER) < text.index("== 安装完成 =="), text


def test_the_banner_names_the_absolute_target_path(tmp_path):
    """横幅必须点名要写的绝对路径。"""
    home = _scratch_home(tmp_path)
    proc, text = _run([], env=_env_for(home))
    assert proc.returncode == 0, text
    target = home / ".claude" / "skills" / "doc-check"
    assert str(target) in text, text


def test_the_banner_says_it_is_the_real_home(tmp_path):
    """横幅要说明这是用户的真实家目录，不只是「一个路径」。"""
    home = _scratch_home(tmp_path)
    proc, text = _run([], env=_env_for(home))
    assert proc.returncode == 0, text
    assert "真实家目录" in text, text
    assert "Ctrl-C" in text, text


def test_the_banner_is_not_a_gate(tmp_path):
    """横幅是提示，不是闸：不给任何参数也照样装成。

    加一道「必须显式 --yes」的闸会挡住同事的正常使用。
    """
    home = _scratch_home(tmp_path)
    proc, text = _run([], env=_env_for(home))
    assert proc.returncode == 0, text
    assert (home / ".claude" / "skills" / "doc-check" / "SKILL.md").exists()


def test_no_banner_when_the_target_root_is_redirected(tmp_path):
    """指定了目标根目录就不该再喊「写真实家目录」。"""
    target = tmp_path / "target"
    (target / ".claude").mkdir(parents=True)
    home = _scratch_home(tmp_path)
    proc, text = _run(["--target-root", str(target)], env=_env_for(home))
    assert proc.returncode == 0, text
    assert BANNER not in text, text


def test_no_banner_in_dry_run_or_status(tmp_path):
    """试运行不写任何文件，状态查询只读，两条路上都不必喊。"""
    home = _scratch_home(tmp_path)
    env = _env_for(home)
    proc, text = _run(["--dry-run"], env=env)
    assert proc.returncode == 0, text
    assert BANNER not in text, text

    proc, text = _run(["--status"], env=env)
    assert proc.returncode == 0, text
    assert BANNER not in text, text


# --- 2. 两个安装器的横幅是同一段文字 ---


def test_the_banner_text_lives_in_exactly_one_place():
    """横幅只能在共享的那份实现里写一次。

    install.sh 与 install.ps1 都调用 install_skill.py，横幅写在
    install_skill.py 里，两个安装器的横幅因此不会分叉。
    """
    shared = (INSTALL / "install_skill.py").read_text(encoding="utf-8")
    assert shared.count(BANNER) == 1, shared.count(BANNER)
    for name in ("install.sh", "install.ps1"):
        text = (INSTALL / name).read_text(encoding="utf-8-sig")
        assert BANNER not in text, f"{name} 里另写了一份横幅，会与共享实现分叉"


def _repo_copy(tmp_path: Path) -> Path:
    """仓库副本：安装器要读 install/、scripts/、references/、SKILL.md。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copytree(INSTALL, repo / "install")
    shutil.copytree(ROOT / "scripts", repo / "scripts")
    shutil.copytree(ROOT / "references", repo / "references")
    shutil.copy2(ROOT / "SKILL.md", repo / "SKILL.md")
    shutil.copy2(ROOT / "requirements.txt", repo / "requirements.txt")
    return repo


def _fake_venv(repo: Path) -> Path:
    """在仓库副本里造一个能跑完整安装流程的假虚拟环境。

    真的去建虚拟环境要联网装依赖，测试里不能干这件事。
    """
    prefix = Path(sys.prefix)
    base = Path(sys.base_prefix)
    if prefix == base:
        pytest.skip("当前解释器不在虚拟环境里，造不出假虚拟环境")
    cfg = prefix / "pyvenv.cfg"
    if not cfg.exists() or not Path(sys.executable).exists():
        pytest.skip("当前虚拟环境不完整，造不出假虚拟环境")

    venv = repo / ".venv"
    (venv / "Scripts").mkdir(parents=True)
    shutil.copy2(Path(sys.executable), venv / "Scripts" / "python.exe")
    shutil.copy2(cfg, venv / "pyvenv.cfg")

    site = venv / "Lib" / "site-packages"
    (site / "pip").mkdir(parents=True)
    (site / "pip" / "__init__.py").write_text("", encoding="utf-8")
    (site / "pip" / "__main__.py").write_text(
        "import sys\nsys.exit(0)\n", encoding="utf-8")
    for module in ("docx", "openpyxl", "pdfplumber", "lxml"):
        (site / f"{module}.py").write_text("", encoding="utf-8")
    return venv


def _make_sh_stub(path: Path, version: str) -> None:
    """POSIX shell 桩：只用来让安装器选中一个解释器。"""
    path.write_text(
        "#!/bin/sh\n" f"echo '{version}'\n" "exit 0\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _make_cmd_stub(path: Path, version: str) -> None:
    """Windows 批处理桩：只用来让安装器选中一个解释器。"""
    path.write_text(
        "\r\n".join(["@echo off", f"echo {version}", "exit /b 0"]) + "\r\n",
        encoding="ascii",
    )


def _bash_exe() -> str | None:
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


def test_the_bash_installer_prints_the_banner(tmp_path):
    """install.sh 走到安装那一步时，横幅必须出现。"""
    bash = _bash_exe()
    if not bash:
        pytest.skip("没有 bash")
    repo = _repo_copy(tmp_path)
    _fake_venv(repo)

    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    _make_sh_stub(stub_dir / "python", "3.14")

    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["PATH"] = str(stub_dir)
    env.pop("DOC_CHECK_TARGET_ROOT", None)

    proc = subprocess.run(
        [bash, str(repo / "install" / "install.sh")],
        capture_output=True, env=env, cwd=str(tmp_path),
    )
    text = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 0, text + proc.stderr.decode("utf-8", "replace")
    assert BANNER in text, text
    assert str(home / ".claude" / "skills" / "doc-check") in text, text


def test_the_powershell_installer_prints_the_banner(tmp_path):
    """install.ps1 走到安装那一步时，横幅必须出现。"""
    shell = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    if not shell.exists():
        pytest.skip("没有 PowerShell")
    repo = _repo_copy(tmp_path)
    _fake_venv(repo)

    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    _make_cmd_stub(stub_dir / "python.cmd", "3.14")

    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["PATH"] = str(stub_dir)
    env.pop("DOC_CHECK_TARGET_ROOT", None)

    proc = subprocess.run(
        [str(shell), "-ExecutionPolicy", "Bypass",
         "-File", str(repo / "install" / "install.ps1")],
        capture_output=True, env=env, cwd=str(tmp_path),
    )
    text = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 0, text + proc.stderr.decode("utf-8", "replace")
    assert BANNER in text, text
    assert str(home / ".claude" / "skills" / "doc-check") in text, text


# --- 3. I-c：安装测试不得写进用户的真实家目录 ---


def test_the_env_var_never_reaches_the_home(tmp_path):
    """DOC_CHECK_TARGET_ROOT 生效时，HOME 下面一个字节都不许写。

    这个测试曾经真的写进过用户的真实家目录：那时候安装器还不认
    DOC_CHECK_TARGET_ROOT，就退回了真实 HOME，而测试照样通过。
    """
    home = tmp_path / "home"
    home.mkdir()
    target = tmp_path / "target"
    (target / ".claude").mkdir(parents=True)

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["DOC_CHECK_TARGET_ROOT"] = str(target)

    proc, text = _run([], env=env)
    assert proc.returncode == 0, text
    assert (target / ".claude" / "skills" / "doc-check").exists()
    for name in (".claude", ".codex", "DoubaoWork", ".dsh"):
        assert not (home / name).exists(), f"不该在 HOME 下面创建 {name}"
