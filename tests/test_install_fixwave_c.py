"""修复波 C 的回归测试：安装器。

覆盖：
- I-4 技能目录里的**子目录**没有被清理（仓库里删掉的文件留在技能目录里）
- I-5 安装器的输出是 GBK、install_skill.py 的输出是 UTF-8，两段拼在同一条
      stdout 上，整条流既不是 GBK 也不是 UTF-8

所有安装都对着临时的 HOME 与临时的仓库副本跑，绝不碰用户的智能体目录。
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

PS51 = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")


def _powershell_exe() -> Path | None:
    if PS51.exists():
        return PS51
    pwsh = shutil.which("pwsh")
    return Path(pwsh) if pwsh else None


# --- I-4：技能目录里的子目录也要清理 ---


def _install_skill(tmp_path: Path) -> Path:
    """把技能装到临时 HOME 下的 Claude Code 技能目录，返回技能目录。"""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    proc = subprocess.run(
        [sys.executable, str(INSTALL / "install_skill.py"),
         "--repo-root", str(ROOT), "--venv-py", sys.executable],
        capture_output=True, env=env, cwd=str(tmp_path),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return home / ".claude" / "skills" / "doc-check"


def test_installed_skill_prunes_stale_files_in_subdirectories(tmp_path):
    """仓库里删掉的文件不能永远留在技能目录里——子目录里也一样。

    `scripts/extractors/` 是最容易变动的子目录。原来同步目录时只清理
    顶层，删掉的文件会一直留在安装出来的技能里。
    """
    skill_dir = _install_skill(tmp_path)
    stale = skill_dir / "scripts" / "extractors" / "stale_nested.py"
    stale.write_text("# 仓库里已经没有这个脚本了\n", encoding="utf-8")

    _install_skill(tmp_path)

    assert not stale.exists(), "子目录里的过时文件没有被清理"


def test_installed_skill_prunes_stale_subdirectory(tmp_path):
    """仓库里整个删掉的子目录也不能留在技能目录里。"""
    skill_dir = _install_skill(tmp_path)
    stale_dir = skill_dir / "scripts" / "stale_pkg"
    stale_dir.mkdir()
    (stale_dir / "mod.py").write_text("# 过时\n", encoding="utf-8")

    _install_skill(tmp_path)

    assert not stale_dir.exists(), "过时的子目录没有被清理"


# --- I-5：安装器的输出与 Python 的输出是同一套编码 ---


def _make_cmd_stub(path: Path, version: str) -> None:
    """Windows 批处理桩：只用来让安装器选中一个解释器。"""
    path.write_text(
        "\r\n".join(["@echo off", f"echo {version}", "exit /b 0"]) + "\r\n",
        encoding="ascii",
    )


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

    真的去建虚拟环境要联网装依赖，测试里不能干这件事。这个假环境：
    - pip 是个空壳（安装依赖那一步直接成功）
    - 四个依赖各是一个空模块（依赖自检那一步直接成功）
    - 解释器是真的（venv 里的 python.exe + pyvenv.cfg）
    安装器因此能一路走到 install_skill.py，输出也就能和安装器自己的
    输出拼在同一条流上。
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


@pytest.mark.skipif(_powershell_exe() is None, reason="没有 PowerShell")
def test_installer_output_and_python_output_share_one_encoding(tmp_path):
    """安装器与 install_skill.py 的输出拼在同一条 stdout 上，整条流必须是 UTF-8。

    Write-Host 默认按控制台代码页（中文 Windows 是 GBK）输出，
    install_skill.py 按 UTF-8 输出：两段拼在一起，整条流既不是 GBK
    也不是 UTF-8，读的人只能看到一半乱码。
    """
    shell = _powershell_exe()
    repo = _repo_copy(tmp_path)
    venv = _fake_venv(repo)

    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    _make_cmd_stub(stub_dir / "python.cmd", "3.14")

    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["PATH"] = str(stub_dir)

    proc = subprocess.run(
        [str(shell), "-ExecutionPolicy", "Bypass",
         "-File", str(repo / "install" / "install.ps1")],
        capture_output=True, env=env, cwd=str(tmp_path),
    )
    data = proc.stdout + proc.stderr

    # 两段输出确实在同一条流上
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AssertionError(
            f"安装器的输出不是 UTF-8：{exc}\n原始字节：{data!r}"
        ) from exc
    assert "== doc-check 安装器 ==" in text, text
    assert "== 安装完成 ==" in text, text
    assert venv.exists()
