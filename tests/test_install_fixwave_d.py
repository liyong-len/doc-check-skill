"""修复波 D 的回归测试：安装器的四个安全阀。

覆盖：
- --dry-run 只解析目标目录，不写任何文件
- --target-root 改「~ 展开到哪个根目录」，不必改 HOME/USERPROFILE，
  而且只装到那里，别处一个字节都不写
- 目标路径在第一次写盘**之前**就打印出来
- --status 给出机器可读的结论（干净 / 残留 N 处），并点名残留目录

所有安装都对着临时的根目录跑，绝不碰用户的智能体目录。
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


# --- 1. --dry-run 什么都不写 ---


def test_dry_run_writes_nothing(tmp_path):
    """试运行只打印将写入的目录，一个文件都不写。"""
    root = _scratch_home(tmp_path)
    proc, text = _run(["--dry-run", "--target-root", str(root)])
    assert proc.returncode == 0, text
    assert "不会写入任何文件" in text
    target = root / ".claude" / "skills" / "doc-check"
    assert str(target) in text, "试运行必须把将写入的路径打印出来"
    assert not target.exists(), "试运行写出了文件"


def test_dry_run_does_not_create_the_skills_directory(tmp_path):
    """连父目录都不许建。"""
    root = tmp_path / "home"
    (root / ".claude").mkdir(parents=True)
    proc, _ = _run(["--dry-run", "--target-root", str(root)])
    assert proc.returncode == 0
    assert not (root / ".claude" / "skills").exists()


# --- 2. --target-root 只装到那里 ---


def test_target_root_installs_there_and_nowhere_else(tmp_path):
    """--target-root 改的是「~ 展开到哪个根目录」。

    HOME/USERPROFILE 一动不动，技能只装到 target-root 下面；
    HOME 下面不能出现任何 doc-check 目录。
    """
    fake_home = _scratch_home(tmp_path)
    target = tmp_path / "target"
    (target / ".claude").mkdir(parents=True)

    env = dict(os.environ)
    env["HOME"] = str(fake_home)
    env["USERPROFILE"] = str(fake_home)

    proc, text = _run(["--target-root", str(target)], env=env)
    assert proc.returncode == 0, text

    installed = target / ".claude" / "skills" / "doc-check"
    assert installed.exists(), "技能没有装到 target-root 下面"
    assert (installed / "SKILL.md").exists()
    assert not (fake_home / ".claude" / "skills" / "doc-check").exists(), \
        "技能被装到了 HOME 下面"


def test_target_root_banner_names_the_root(tmp_path):
    """横幅与回执都要写明目标根目录。

    检测是全局的（PATH 上的 claude 命令与家目录无关），安装不是。
    读输出的人必须一眼看出东西装到了哪儿。
    """
    target = tmp_path / "target"
    (target / ".claude").mkdir(parents=True)
    proc, text = _run(["--target-root", str(target)])
    assert proc.returncode == 0
    assert str(target) in text, "横幅里没有目标根目录"
    assert "本次写入的目录" in text, "回执里没有回显写入的目录"
    assert str(target / ".claude" / "skills" / "doc-check") in text


def test_target_root_env_var_works_too(tmp_path):
    """环境变量与命令行参数等价。"""
    target = tmp_path / "target"
    (target / ".claude").mkdir(parents=True)
    env = dict(os.environ)
    env["DOC_CHECK_TARGET_ROOT"] = str(target)
    proc, text = _run([], env=env)
    assert proc.returncode == 0, text
    assert (target / ".claude" / "skills" / "doc-check").exists()


# --- 3. 目标路径在第一次写盘之前打印 ---


def test_targets_are_printed_before_the_first_write(tmp_path):
    """写完之后再打印路径，看的人已经没法回头确认装到哪儿了。"""
    root = _scratch_home(tmp_path)
    proc, text = _run(["--target-root", str(root)])
    assert proc.returncode == 0, text
    announced = text.find("本次将写入以下目录")
    finished = text.find("== 安装完成 ==")
    assert announced >= 0, text
    assert finished >= 0, text
    assert announced < finished, "目标路径在写完之后才打印"


# --- 4. --status 给出机器可读的结论 ---


def test_status_reports_clean_on_a_scratch_home(tmp_path):
    """干净的家目录上，结论是「干净」。"""
    root = _scratch_home(tmp_path)
    proc, text = _run(["--status", "--target-root", str(root)])
    assert proc.returncode == 0, text
    assert "doc-check 安装状态：干净" in text
    assert str(root) in text, "状态里没有写明家目录根"


def test_status_names_every_leftover(tmp_path):
    """残留的 doc-check 目录要一个不漏地点名。"""
    root = tmp_path / "home"
    (root / ".claude" / "skills" / "doc-check").mkdir(parents=True)
    (root / ".codex" / "skills" / "doc-check").mkdir(parents=True)
    proc, text = _run(["--status", "--target-root", str(root)])
    assert proc.returncode == 0, text
    assert "doc-check 安装状态：残留 2 处" in text
    assert str(root / ".claude" / "skills" / "doc-check") in text
    assert str(root / ".codex" / "skills" / "doc-check") in text


def test_status_writes_nothing(tmp_path):
    """--status 是只读的。"""
    root = _scratch_home(tmp_path)
    proc, _ = _run(["--status", "--target-root", str(root)])
    assert proc.returncode == 0
    assert not (root / ".claude" / "skills").exists()


# --- 两个安装脚本必须把新参数转发下去 ---


def _powershell_exe() -> Path | None:
    ps51 = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    if ps51.exists():
        return ps51
    pwsh = shutil.which("pwsh")
    return Path(pwsh) if pwsh else None


def _env_with_python() -> dict:
    """PATH 里要有真的 python：安装脚本要靠它跑 install_skill.py。"""
    env = dict(os.environ)
    scripts = str(Path(sys.executable).resolve().parent)
    env["PATH"] = scripts + os.pathsep + env.get("PATH", "")
    return env


@pytest.mark.skipif(_powershell_exe() is None, reason="没有 PowerShell")
def test_powershell_installer_forwards_the_new_flags(tmp_path):
    """install.ps1 必须把 --status / --dry-run / --target-root 转发下去。

    用户敲的是 install.ps1，不是 install_skill.py。参数在中间那一层被丢掉，
    用户看到的就还是「一条命令装好」——装到哪儿去了没人知道。
    """
    shell = _powershell_exe()
    root = _scratch_home(tmp_path)
    env = _env_with_python()

    proc = subprocess.run(
        [str(shell), "-ExecutionPolicy", "Bypass",
         "-File", str(INSTALL / "install.ps1"),
         "--status", "--target-root", str(root)],
        capture_output=True, env=env, cwd=str(ROOT),
    )
    text = proc.stdout.decode("utf-8", "replace")
    assert "doc-check 安装状态：干净" in text, text
    assert not (root / ".claude" / "skills").exists()

    proc = subprocess.run(
        [str(shell), "-ExecutionPolicy", "Bypass",
         "-File", str(INSTALL / "install.ps1"),
         "--dry-run", "--target-root", str(root)],
        capture_output=True, env=env, cwd=str(ROOT),
    )
    text = proc.stdout.decode("utf-8", "replace")
    assert "不会写入任何文件" in text, text
    assert str(root / ".claude" / "skills" / "doc-check") in text, text
    assert not (root / ".claude" / "skills").exists()


def test_bash_installer_forwards_the_new_flags(tmp_path):
    """install.sh 同样要转发新参数。"""
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("没有 bash")
    root = _scratch_home(tmp_path)
    env = _env_with_python()

    proc = subprocess.run(
        [bash, str(INSTALL / "install.sh"),
         "--status", "--target-root", str(root)],
        capture_output=True, env=env, cwd=str(ROOT),
    )
    text = proc.stdout.decode("utf-8", "replace")
    assert "doc-check 安装状态：干净" in text, text
    assert not (root / ".claude" / "skills").exists()
