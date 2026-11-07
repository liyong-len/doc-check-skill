"""环境自检。检查 Python 版本、依赖导入、虚拟环境。"""
from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import force_utf8_stdio

REQUIRED_MODULES = ["docx", "openpyxl", "pdfplumber", "lxml"]
MIN_PYTHON = (3, 9)

# 探测依赖时用的子进程程序。只输出 ASCII：子进程用系统码页写 stdout，
# 中文括号会被写成乱码，父进程再自己拼提示文字。
_PROBE_SOURCE = """
import importlib
missing = []
for name in {modules!r}:
    try:
        importlib.import_module(name)
    except Exception as exc:
        missing.append(name + "\\t" + type(exc).__name__)
print("\\n".join(missing))
"""


def _find_venv(repo: Path) -> str | None:
    """找虚拟环境解释器。

    仓库内的 .venv 是开发时用的。技能被装进智能体目录后，仓库不在本地，
    安装器会把虚拟环境解释器的绝对路径写进技能目录下的 python-path.txt，
    那个才是运行时真正用的解释器。
    """
    for candidate in (repo / ".venv" / "Scripts" / "python.exe", repo / ".venv" / "bin" / "python"):
        if candidate.exists():
            return str(candidate)
    pointer = repo / "python-path.txt"
    if pointer.exists():
        text = pointer.read_text(encoding="utf-8").strip()
        if text:
            return text
    return None


def _missing_in_current_interpreter() -> list[str]:
    """当前解释器里缺哪些依赖。"""
    missing: list[str] = []
    for name in REQUIRED_MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:
            missing.append(f"{name}（{type(exc).__name__}）")
    return missing


def _missing_in_other_interpreter(venv: str) -> list[str] | None:
    """换用另一个解释器探测依赖。

    技能被装进智能体目录后，调用 check_env.py 的解释器往往不是装依赖的那个
    （智能体手里只有系统 python）。这时必须用 python-path.txt 指向的解释器去探测，
    否则会一边打印虚拟环境路径，一边说「缺少依赖：docx」，自相矛盾。
    返回 None 表示探测不了（解释器路径失效或执行失败）。
    """
    code = _PROBE_SOURCE.format(modules=REQUIRED_MODULES)
    try:
        proc = subprocess.run(
            [venv, "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    missing: list[str] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        name, _, kind = line.partition("\t")
        missing.append(f"{name}（{kind or 'ImportError'}）")
    return missing


def check() -> dict:
    notes: list[str] = []
    problems: list[str] = []
    missing: list[str] = []

    version = ".".join(str(v) for v in sys.version_info[:3])
    if sys.version_info[:2] < MIN_PYTHON:
        problems.append(f"Python {version} 低于要求的 3.9")

    repo = Path(__file__).resolve().parent.parent
    venv = _find_venv(repo)

    if venv is None:
        missing = _missing_in_current_interpreter()
        problems.append(
            "未找到 .venv 或 python-path.txt，若依赖未装入当前解释器，"
            "请运行 install/install.ps1（Windows）或 install/install.sh（macOS/Linux）"
        )
    elif not Path(venv).exists():
        missing = _missing_in_current_interpreter()
        problems.append(f"虚拟环境解释器路径已失效：{venv}，请重跑安装器")
    elif Path(venv) != Path(sys.executable):
        probed = _missing_in_other_interpreter(venv)
        if probed is None:
            missing = _missing_in_current_interpreter()
            problems.append(
                f"虚拟环境解释器无法执行（{venv}），下面的依赖结论按当前解释器给出"
            )
        else:
            missing = probed
            notes.append(
                f"依赖检查用的是虚拟环境解释器 {venv}，不是当前解释器 {sys.executable}"
            )
    else:
        missing = _missing_in_current_interpreter()

    return {
        "ok": not missing and not problems,
        "python": version,
        "missing": missing,
        "venv": venv,
        "notes": notes,
        "problems": problems,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="doc-check 环境自检")
    parser.parse_args(argv)
    force_utf8_stdio()
    r = check()
    print(f"Python：{r['python']}")
    print(f"虚拟环境：{r['venv'] or '未找到'}")
    if r["missing"]:
        print("缺少依赖：" + "、".join(r["missing"]))
    for p in r["problems"]:
        print("问题：" + p)
    for n in r["notes"]:
        print("提示：" + n)
    print("环境自检通过。" if r["ok"] else "环境自检未通过，请先解决上面的问题。")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
