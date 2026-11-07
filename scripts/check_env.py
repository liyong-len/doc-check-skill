"""环境自检。检查 Python 版本、依赖导入、虚拟环境。"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import force_utf8_stdio

REQUIRED_MODULES = ["docx", "openpyxl", "pdfplumber", "lxml"]
MIN_PYTHON = (3, 9)


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


def check() -> dict:
    notes: list[str] = []
    missing: list[str] = []

    version = ".".join(str(v) for v in sys.version_info[:3])
    if sys.version_info[:2] < MIN_PYTHON:
        notes.append(f"Python {version} 低于要求的 3.9")

    for name in REQUIRED_MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:
            missing.append(f"{name}（{type(exc).__name__}）")

    repo = Path(__file__).resolve().parent.parent
    venv = _find_venv(repo)
    if venv is None:
        notes.append("未找到仓库内的 .venv，若依赖未装入当前解释器，请运行 install/install.ps1")

    return {
        "ok": not missing and not notes,
        "python": version,
        "missing": missing,
        "venv": venv,
        "notes": notes,
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
    for n in r["notes"]:
        print("提示：" + n)
    print("环境自检通过。" if r["ok"] else "环境自检未通过，请先解决上面的问题。")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
