#!/usr/bin/env bash
# doc-check 安装器
# 用法：bash install/install.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$REPO_ROOT/.venv"

echo "== doc-check 安装器 =="
echo "仓库目录：$REPO_ROOT"

# --- 1. 选择解释器 ---
PY_EXE=""
PY_ARGS=""
PY_VER=""
for cand in "python3.12:" "python3.11:" "python3.13:" "python3:" "python:" "py:-3"; do
    exe="${cand%%:*}"
    args="${cand#*:}"
    if ! command -v "$exe" >/dev/null 2>&1; then continue; fi
    ver="$("$exe" $args -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
    [ -n "$ver" ] || continue
    [[ "$ver" =~ ^[0-9]+\.[0-9]+$ ]] || continue
    major="${ver%%.*}"
    minor="${ver#*.}"
    if [ "$major" -lt 3 ]; then continue; fi
    if [ "$major" -eq 3 ] && [ "$minor" -lt 9 ]; then continue; fi
    echo "使用解释器：$exe $args  (Python $ver)"
    PY_EXE="$exe"
    PY_ARGS="$args"
    PY_VER="$ver"
    break
done

if [ -z "$PY_EXE" ]; then
    echo "未找到 Python 3.9 及以上解释器。请安装 Python 3.11 或 3.12 后重试。" >&2
    exit 1
fi

# --- 2. 创建虚拟环境 ---
if [ ! -d "$VENV_DIR" ]; then
    echo "创建虚拟环境 .venv ..."
    "$PY_EXE" $PY_ARGS -m venv "$VENV_DIR" || true
fi
VENV_PY="$VENV_DIR/bin/python"
if [ ! -x "$VENV_PY" ]; then
    echo "虚拟环境创建失败：$VENV_PY 不存在" >&2
    exit 1
fi

# --- 3. 安装依赖 ---
echo "安装依赖 ..."
"$VENV_PY" -m pip install --upgrade pip >/dev/null || true
if ! "$VENV_PY" -m pip install -r "$REPO_ROOT/requirements.txt"; then
    echo "依赖安装失败。Python $PY_VER 可能缺少预编译轮子，请改用 Python 3.11 或 3.12。" >&2
    exit 1
fi

# --- 4. 依赖自检 ---
if ! "$VENV_PY" -c "import docx, openpyxl, pdfplumber, lxml"; then
    echo "依赖导入自检失败，请换用 Python 3.11 或 3.12 重建虚拟环境。" >&2
    exit 1
fi
echo "依赖自检通过。"

# --- 5. 安装到各智能体 ---
"$PY_EXE" $PY_ARGS - "$REPO_ROOT" "$VENV_PY" <<'PYEOF'
"""doc-check 安装器的智能体安装阶段。"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
venv_py = sys.argv[2]
install_dir = repo_root / "install"
adapters = json.loads((install_dir / "adapters.json").read_text(encoding="utf-8"))

# 本脚本其余部分直接输出 UTF-8 字节，这里也统一成 UTF-8，
# 否则在 Windows 的 Git Bash 里中文会按系统码页输出成乱码。
sys.stdout.reconfigure(encoding="utf-8")

installed, skipped = [], []
for a in adapters["agents"]:
    if a["mode"] == "manual":
        skipped.append(a["name"])
        continue
    found = False
    for p in a.get("detect_paths", []):
        if Path(os.path.expanduser(p)).exists():
            found = True
            break
    if not found:
        for c in a.get("detect_commands", []):
            if shutil.which(c):
                found = True
                break
    if not found:
        skipped.append(a["name"])
        continue
    target = Path(os.path.expanduser(a["skill_dir"]))
    target.mkdir(parents=True, exist_ok=True)
    # 入口文件取仓库原件：SKILL.md 里有完整的三阶段流程，
    # 智能体真正读的是它，不能被下面的适配模板覆盖。
    for item in (a["entry"], "references", "scripts", "requirements.txt"):
        src = repo_root / item
        if src.is_dir():
            shutil.copytree(
                src,
                target / item,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        elif src.exists():
            shutil.copy2(src, target / item)
    (target / "python-path.txt").write_text(venv_py, encoding="utf-8")
    tpl = install_dir / "adapters" / f"{a['id']}.md"
    if tpl.exists():
        (target / "AGENT.md").write_text(
            tpl.read_text(encoding="utf-8").replace("{{REPO_ROOT}}", repo_root.as_posix()),
            encoding="utf-8",
        )
    installed.append((a["name"], str(target), a.get("usage", "")))

print("")
print("== 安装完成 ==")
for name, path, usage in installed:
    print(f"[已安装] {name} -> {path}")
    print(f"          用法：{usage}")
if skipped:
    print("")
    print(f"未检测到（已跳过）：{'、'.join(skipped)}")
print("")
print("通用接入方式见 install/adapters/generic.md")
print(f"仓库目录：{repo_root}")
PYEOF
