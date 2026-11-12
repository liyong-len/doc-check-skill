"""引导安装脚本的测试。

引导脚本（install/bootstrap.sh、install/bootstrap.ps1）是「发个 GitHub 地址
就能装完」这条承诺的唯一入口，所以它的行为要真的跑一遍，不能靠 grep 源码。

跑法上有一个绕不开的限制：引导脚本要从一个 URL 下载仓库。测试用本地
HTTP 服务提供压缩包，走的是与线上完全相同的下载路径（curl / Invoke-WebRequest
→ 解压 → 调安装器），只有地址换成了 127.0.0.1。
"""
from __future__ import annotations

import http.server
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import threading
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "install"

BOOTSTRAP_SH = INSTALL / "bootstrap.sh"
BOOTSTRAP_PS1 = INSTALL / "bootstrap.ps1"


# --- 运行环境探针 ---


def _bash_exe() -> str | None:
    """Git Bash 的 bash。MSYS 路径 Windows 进程起不来，要用 cygpath 换。"""
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


def _powershell_exes() -> list[Path]:
    """本机可用的 PowerShell。PS 5.1 是 README 里写的受支持路径。"""
    shells: list[Path] = []
    ps51 = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    if ps51.exists():
        shells.append(ps51)
    pwsh = shutil.which("pwsh")
    if pwsh:
        shells.append(Path(pwsh))
    return shells


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


# --- 本地压缩包与 HTTP 服务 ---


def _make_tarball(target: Path) -> None:
    """把工作树打成 tar.gz，形状与 GitHub 的压缩包一致：顶层一个目录。"""
    stage = target.parent / "stage"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    repo = stage / "doc-check-skill-main"
    repo.mkdir()
    for name in ["install", "scripts", "references"]:
        shutil.copytree(ROOT / name, repo / name)
    for name in ["SKILL.md", "AGENTS.md", "requirements.txt"]:
        shutil.copy2(ROOT / name, repo / name)
    with tarfile.open(target, "w:gz") as tar:
        tar.add(repo, arcname="doc-check-skill-main")


def _make_zip(target: Path) -> None:
    """同样的内容打成 zip，形状与 GitHub 的 zip 一致。"""
    stage = target.parent / "stage-zip"
    if stage.exists():
        shutil.rmtree(stage)
    repo = stage / "doc-check-skill-main"
    repo.mkdir(parents=True)
    for name in ["install", "scripts", "references"]:
        shutil.copytree(ROOT / name, repo / name)
    for name in ["SKILL.md", "AGENTS.md", "requirements.txt"]:
        shutil.copy2(ROOT / name, repo / name)
    with zipfile.ZipFile(target, "w") as zf:
        for path in sorted(repo.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(stage))


class _Server:
    """在后台提供压缩包。"""

    def __init__(self, directory: Path):
        self._directory = directory
        self._port = _free_port()
        handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(  # noqa: E731
            *a, directory=str(directory), **kw
        )
        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", self._port), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def __enter__(self) -> " _Server":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=10)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._port}"


# --- 文件形态 ---


def test_bootstrap_scripts_exist():
    assert BOOTSTRAP_SH.exists(), BOOTSTRAP_SH
    assert BOOTSTRAP_PS1.exists(), BOOTSTRAP_PS1


def test_bootstrap_sh_has_no_carriage_return():
    """CRLF 的 shell 脚本在 Git Bash 与 Linux 下会因为 shebang 多一个 \\r 而跑不起来。"""
    assert b"\r" not in BOOTSTRAP_SH.read_bytes()


def test_bootstrap_ps1_keeps_utf8_bom():
    """Windows PowerShell 5.1 读无 BOM 的文件时按系统 ANSI 码页解码，中文会成乱码。"""
    data = BOOTSTRAP_PS1.read_bytes()
    assert data.startswith(b"\xef\xbb\xbf"), "bootstrap.ps1 必须带 UTF-8 BOM"


def test_bootstrap_sh_is_executable_in_git():
    """带可执行位入库，否则 ./install/bootstrap.sh 报 Permission denied。"""
    git = shutil.which("git")
    if not git:
        pytest.skip("没有 git")
    proc = subprocess.run(
        [git, "ls-files", "-s", "install/bootstrap.sh"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.split()[0] == "100755", proc.stdout


def test_gitattributes_keeps_bootstrap_sh_at_lf():
    """bootstrap.sh 与 install.sh 一样，行尾必须钉死成 LF。"""
    text = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "install/bootstrap.sh text eol=lf" in text


# --- 行为 ---


def _run_bash_bootstrap(args: list[str], env_extra: dict) -> tuple[int, str]:
    bash = _bash_exe()
    if not bash:
        pytest.skip("没有 bash")
    env = dict(os.environ)
    env.update(env_extra)
    proc = subprocess.run(
        [bash, str(BOOTSTRAP_SH), *args],
        capture_output=True, env=env, cwd=str(ROOT.parent),
    )
    return proc.returncode, proc.stdout.decode("utf-8", errors="replace") + \
        proc.stderr.decode("utf-8", errors="replace")


def test_bash_bootstrap_downloads_repo_and_dry_runs(tmp_path):
    """引导脚本必须真的把仓库取下来，再调安装器。"""
    served = tmp_path / "served"
    served.mkdir()
    _make_tarball(served / "repo.tar.gz")
    home = tmp_path / "home"
    home.mkdir()
    target = tmp_path / "target"

    with _Server(served) as server:
        code, out = _run_bash_bootstrap(
            ["--dry-run", "--target-root", str(target)],
            {
                "DOC_CHECK_HOME": str(home / ".doc-check"),
                "DOC_CHECK_REPO_URL": f"{server.base_url}/repo.tar.gz",
            },
        )

    assert code == 0, out
    assert "仓库目录：" in out, out
    # 仓库确实落到了盘上。
    assert (home / ".doc-check" / "repo" / "install" / "install.sh").exists()
    # 试运行不写任何技能目录。
    assert not (target / ".claude").exists()
    assert "试运行结束：没有写入任何文件" in out, out


def test_bash_bootstrap_installs_skill_into_target(tmp_path):
    """完整安装：仓库到位、虚拟环境建好、技能写进目标目录。"""
    served = tmp_path / "served"
    served.mkdir()
    _make_tarball(served / "repo.tar.gz")
    home = tmp_path / "home"
    home.mkdir()
    target = tmp_path / "target"

    with _Server(served) as server:
        code, out = _run_bash_bootstrap(
            ["--target-root", str(target)],
            {
                "DOC_CHECK_HOME": str(home / ".doc-check"),
                "DOC_CHECK_REPO_URL": f"{server.base_url}/repo.tar.gz",
            },
        )

    assert code == 0, out
    repo = home / ".doc-check" / "repo"
    assert (repo / ".venv").exists(), "虚拟环境没有建起来"
    skill = target / ".claude" / "skills" / "doc-check"
    assert (skill / "SKILL.md").exists()
    assert (skill / "python-path.txt").exists()
    # python-path.txt 指向仓库里的虚拟环境，不是系统解释器。
    pointer = (skill / "python-path.txt").read_text(encoding="utf-8").strip()
    assert Path(pointer).exists(), pointer
    assert str(repo).replace("\\", "/") in pointer.replace("\\", "/"), pointer


def test_bash_bootstrap_update_keeps_existing_venv(tmp_path):
    """重跑一次（更新）不能把已有的虚拟环境删掉重装。

    虚拟环境里的脚本记着自己��绝对路径，而这个路径前后不变，
    所以「先搬走、再换仓库、再搬回去」是安全的；直接删了重建则要多等一次装依赖。
    """
    served = tmp_path / "served"
    served.mkdir()
    _make_tarball(served / "repo.tar.gz")
    home = tmp_path / "home"
    home.mkdir()
    target = tmp_path / "target"

    with _Server(served) as server:
        env = {
            "DOC_CHECK_HOME": str(home / ".doc-check"),
            "DOC_CHECK_REPO_URL": f"{server.base_url}/repo.tar.gz",
        }
        code, out = _run_bash_bootstrap(["--target-root", str(target)], env)
        assert code == 0, out

        repo = home / ".doc-check" / "repo"
        venv = repo / ".venv"
        marker = venv / "bootstrap-test-marker.txt"
        marker.write_text("保留这个文件\n", encoding="utf-8")

        code, out = _run_bash_bootstrap(["--update", "--target-root", str(target)], env)

    assert code == 0, out
    assert "已保留原有虚拟环境" in out, out
    assert marker.exists(), "虚拟环境在更新时被重建了"


def test_bash_bootstrap_rejects_unknown_argument(tmp_path):
    """参数是显式的：拼错的参数直接报错退出，不被静默当成「正常安装」。"""
    code, out = _run_bash_bootstrap(["--nope"], {"DOC_CHECK_HOME": str(tmp_path)})
    assert code == 2, out
    assert "未知参数" in out, out


def test_bash_bootstrap_reports_download_failure(tmp_path):
    """下载不通要说清楚是哪一步失败了，而不是留下半个安装。"""
    code, out = _run_bash_bootstrap(
        ["--dry-run"],
        {
            "DOC_CHECK_HOME": str(tmp_path / "home"),
            # 指向一个没有服务的端口。
            "DOC_CHECK_REPO_URL": f"http://127.0.0.1:{_free_port()}/repo.tar.gz",
        },
    )
    assert code != 0, out
    assert "下载失败" in out, out


def _run_ps_bootstrap(shell: Path, args: list[str], env_extra: dict) -> tuple[int, str]:
    env = dict(os.environ)
    env.update(env_extra)
    proc = subprocess.run(
        [str(shell), "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(BOOTSTRAP_PS1), *args],
        capture_output=True, env=env, cwd=str(ROOT.parent),
    )
    output = proc.stdout.decode("utf-8", errors="replace") + \
        proc.stderr.decode("utf-8", errors="replace")
    return proc.returncode, output


@pytest.mark.skipif(not _powershell_exes(), reason="没有 PowerShell")
@pytest.mark.parametrize("shell", _powershell_exes(), ids=lambda p: p.name)
def test_powershell_bootstrap_installs_skill_into_target(tmp_path, shell):
    """PowerShell 引导脚本：下载 zip、解压、调安装器、装出技能。"""
    served = tmp_path / "served"
    served.mkdir()
    _make_zip(served / "repo.zip")
    home = tmp_path / "home"
    home.mkdir()
    target = tmp_path / "target"

    with _Server(served) as server:
        code, out = _run_ps_bootstrap(
            shell,
            ["--target-root", str(target)],
            {
                "DOC_CHECK_HOME": str(home / ".doc-check"),
                "DOC_CHECK_REPO_URL": f"{server.base_url}/repo.zip",
            },
        )

    assert code == 0, out
    repo = home / ".doc-check" / "repo"
    assert (repo / "install" / "install.ps1").exists(), "仓库没解压到位"
    assert (repo / ".venv").exists(), "虚拟环境没有建起来"
    skill = target / ".claude" / "skills" / "doc-check"
    assert (skill / "SKILL.md").exists()
    assert (skill / "python-path.txt").exists()


@pytest.mark.skipif(not _powershell_exes(), reason="没有 PowerShell")
@pytest.mark.parametrize("shell", _powershell_exes(), ids=lambda p: p.name)
def test_powershell_bootstrap_update_keeps_existing_venv(tmp_path, shell):
    """更新时保留已有的虚拟环境。"""
    served = tmp_path / "served"
    served.mkdir()
    _make_zip(served / "repo.zip")
    home = tmp_path / "home"
    home.mkdir()
    target = tmp_path / "target"

    with _Server(served) as server:
        env = {
            "DOC_CHECK_HOME": str(home / ".doc-check"),
            "DOC_CHECK_REPO_URL": f"{server.base_url}/repo.zip",
        }
        code, out = _run_ps_bootstrap(shell, ["--target-root", str(target)], env)
        assert code == 0, out

        repo = home / ".doc-check" / "repo"
        marker = repo / ".venv" / "bootstrap-test-marker.txt"
        marker.write_text("保留这个文件\n", encoding="utf-8")

        code, out = _run_ps_bootstrap(shell, ["--update", "--target-root", str(target)], env)

    assert code == 0, out
    assert "已保留原有虚拟环境" in out, out
    assert marker.exists(), "虚拟环境在更新时被重建了"


@pytest.mark.skipif(not _powershell_exes(), reason="没有 PowerShell")
@pytest.mark.parametrize("shell", _powershell_exes(), ids=lambda p: p.name)
def test_powershell_bootstrap_rejects_unknown_argument(tmp_path, shell):
    code, out = _run_ps_bootstrap(shell, ["--nope"], {"DOC_CHECK_HOME": str(tmp_path)})
    assert code == 2, out
    assert "未知参数" in out, out


@pytest.mark.skipif(not _powershell_exes(), reason="没有 PowerShell")
@pytest.mark.parametrize("shell", _powershell_exes(), ids=lambda p: p.name)
def test_powershell_bootstrap_reports_download_failure(tmp_path, shell):
    code, out = _run_ps_bootstrap(
        shell,
        ["--dry-run"],
        {
            "DOC_CHECK_HOME": str(tmp_path / "home"),
            "DOC_CHECK_REPO_URL": f"http://127.0.0.1:{_free_port()}/repo.zip",
        },
    )
    assert code != 0, out
    assert "下载失败" in out, out
