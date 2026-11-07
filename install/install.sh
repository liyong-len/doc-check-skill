#!/usr/bin/env bash
# doc-check 安装器
# 用法：bash install/install.sh [--update] [--dry-run] [--status] [--target-root <路径>]
set -euo pipefail

# 脚本自身所在目录与仓库根目录。只用内建命令算出来：
# 解释器探测之前不能依赖 PATH 里的任何外部程序，否则在一台什么都没装的
# 机器上会在探测之前就因为「找不到 dirname」而失败，压根走不到那句提示。
#
# Windows 上用绝对路径调用时，BASH_SOURCE 里是反斜杠（D:\...\install\install.sh）。
# 反斜杠在 bash 里是转义符，${_src%/*} 取不到目录部分，脚本会跑错目录。
# 先统一成斜杠，两种写法都能用。
_src="${BASH_SOURCE[0]//\\//}"
case "$_src" in
    */*) SCRIPT_DIR="$(cd "${_src%/*}" && pwd)" ;;
    *)   SCRIPT_DIR="$(pwd)" ;;
esac
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALL_DIR="$SCRIPT_DIR"
VENV_DIR="$REPO_ROOT/.venv"

UPDATE=0
DRY_RUN=0
STATUS=0
TARGET_ROOT=""

usage() {
    printf '%s\n' \
        '用法：doc-check 安装器 [选项]' \
        '  --update      覆盖已安装的副本，并清理已从仓库删除的文件' \
        '  --dry-run     只打印将要写入的目录，不写任何文件' \
        '  --status      打印家目录根、各智能体目录与残留情况' \
        '  --target-root <路径>  改「~ 展开到哪个根目录」，不改 HOME/USERPROFILE' \
        '  -h, --help    显示本帮助并退出'
}

# 参数是显式的：--update 有明确含义，拼错的参数直接报错退出，
# 不会被静默当成「正常安装」。
while [ $# -gt 0 ]; do
    case "$1" in
        --update) UPDATE=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        --status) STATUS=1; shift ;;
        --target-root)
            if [ $# -lt 2 ]; then
                echo "缺少 --target-root 的路径参数" >&2
                usage >&2
                exit 2
            fi
            TARGET_ROOT="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *)
            echo "未知参数：$1" >&2
            echo "可用参数：--update、--dry-run、--status、--target-root、-h/--help" >&2
            usage >&2
            exit 2
            ;;
    esac
done

echo "== doc-check 安装器 =="
echo "仓库目录：$REPO_ROOT"
if [ "$STATUS" -eq 1 ]; then
    echo "模式：查看安装状态（不装任何东西）"
elif [ "$DRY_RUN" -eq 1 ]; then
    echo "模式：试运行（只打印将写入的目录，不写任何文件）"
elif [ "$UPDATE" -eq 1 ]; then
    echo "模式：更新（覆盖已安装的副本，并清理已从仓库删除的文件）"
else
    echo "模式：安装（写入技能目录，已存在的同名文件会被覆盖）"
fi

# --- 1. 选择解释器 ---
#
# 候选顺序与 install.ps1 完全一致：先用启动器指定版本，再试带版本号的可执行名，
# 最后才是通用的 python3 / python / py -3。优先 3.11 与 3.12，
# 因为 lxml 与 pdfplumber 在这些版本上的预编译轮子最完整。
#
# 判定只看两样：退出码必须是 0，标准输出里必须有一行正好是「主.次」。
# 标准错误上的任何内容都不参与判断——解释器在 stderr 上打一句提醒，
# 不该让一个能用的 Python 被判成「没装 Python」。
CANDIDATES=(
    "py:-3.12"
    "py:-3.11"
    "py:-3.13"
    "python3.12:"
    "python3.11:"
    "python3.13:"
    "python3:"
    "python:"
    "py:-3"
)

PY_EXE=""
PY_ARGS=""
PY_VER=""
for cand in "${CANDIDATES[@]}"; do
    exe="${cand%%:*}"
    args="${cand#*:}"
    if ! command -v "$exe" >/dev/null 2>&1; then continue; fi
    out="$("$exe" $args -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)" && code=0 || code=$?
    [ "$code" -eq 0 ] || continue
    ver=""
    while IFS= read -r line; do
        line="${line//$'\r'/}"
        if [[ "$line" =~ ^[0-9]+\.[0-9]+$ ]]; then ver="$line"; break; fi
    done <<< "$out"
    [ -n "$ver" ] || continue
    major="${ver%%.*}"
    minor="${ver#*.}"
    if [ "$major" -lt 3 ]; then continue; fi
    if [ "$major" -eq 3 ] && [ "$minor" -lt 9 ]; then continue; fi
    label="$exe"
    if [ -n "$args" ]; then label="$exe $args"; fi
    echo "使用解释器：$label  (Python $ver)"
    PY_EXE="$exe"
    PY_ARGS="$args"
    PY_VER="$ver"
    break
done

if [ -z "$PY_EXE" ]; then
    echo "未找到 Python 3.9 及以上解释器。请安装 Python 3.11 或 3.12 后重试。" >&2
    exit 1
fi

# --- 2. 查看安装状态 / 试运行 ---
#
# 这两条路都不建虚拟环境、不装依赖、不写任何文件：
# 它们要回答的是「机器上现在是什么样」「会写到哪儿去」，
# 而这两件事都不需要先往仓库里装一遍依赖。
if [ "$STATUS" -eq 1 ] || [ "$DRY_RUN" -eq 1 ]; then
    EXTRA=()
    if [ "$STATUS" -eq 1 ]; then EXTRA=(--status); else EXTRA=(--dry-run); fi
    ROOT_ARGS=()
    if [ -n "$TARGET_ROOT" ]; then ROOT_ARGS=(--target-root "$TARGET_ROOT"); fi
    "$PY_EXE" $PY_ARGS "$INSTALL_DIR/install_skill.py" --repo-root "$REPO_ROOT" \
        --venv-py "$VENV_DIR/bin/python" "${EXTRA[@]}" "${ROOT_ARGS[@]}" ||
        { echo "安装器自检失败。" >&2; exit 1; }
    exit 0
fi

# --- 3. 创建虚拟环境 ---
if [ ! -d "$VENV_DIR" ]; then
    echo "创建虚拟环境 .venv ..."
    "$PY_EXE" $PY_ARGS -m venv "$VENV_DIR" || true
fi
# 虚拟环境解释器。Windows 上（在 Git Bash 里跑本脚本时）布局是 Scripts/，
# POSIX 上是 bin/，两个都认。
VENV_PY=""
for cand_py in "$VENV_DIR/bin/python" "$VENV_DIR/Scripts/python.exe"; do
    if [ -x "$cand_py" ]; then VENV_PY="$cand_py"; break; fi
done
if [ -z "$VENV_PY" ]; then
    echo "虚拟环境创建失败：$VENV_DIR/bin/python 不存在" >&2
    exit 1
fi

# --- 4. 安装依赖 ---
echo "安装依赖 ..."
"$VENV_PY" -m pip install --upgrade pip >/dev/null || true
if ! "$VENV_PY" -m pip install -r "$REPO_ROOT/requirements.txt"; then
    echo "依赖安装失败。Python $PY_VER 可能缺少预编译轮子，请改用 Python 3.11 或 3.12。" >&2
    exit 1
fi

# --- 5. 依赖自检 ---
if ! "$VENV_PY" -c "import docx, openpyxl, pdfplumber, lxml"; then
    echo "依赖导入自检失败，请换用 Python 3.11 或 3.12 重建虚拟环境。" >&2
    exit 1
fi
echo "依赖自检通过。"

# --- 6. 安装到各智能体 ---
#
# 装到智能体目录这一步由 install/install_skill.py 完成：
# install.ps1 调用的是同一个文件，两个安装器的行为因此一致。
ROOT_ARGS=()
if [ -n "$TARGET_ROOT" ]; then ROOT_ARGS=(--target-root "$TARGET_ROOT"); fi
if [ "$UPDATE" -eq 1 ]; then
    "$VENV_PY" "$INSTALL_DIR/install_skill.py" --repo-root "$REPO_ROOT" --venv-py "$VENV_PY" --update "${ROOT_ARGS[@]}" ||
        { echo "安装到智能体目录失败。" >&2; exit 1; }
else
    "$VENV_PY" "$INSTALL_DIR/install_skill.py" --repo-root "$REPO_ROOT" --venv-py "$VENV_PY" "${ROOT_ARGS[@]}" ||
        { echo "安装到智能体目录失败。" >&2; exit 1; }
fi
