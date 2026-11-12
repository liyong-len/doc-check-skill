#!/usr/bin/env bash
# doc-check 一键安装引导脚本
#
# 用法（macOS / Linux / Windows 上的 Git Bash）：
#   curl -fsSL https://raw.githubusercontent.com/liyong-len/doc-check-skill/main/install/bootstrap.sh | bash
#
# 带参数（先把脚本存下来再跑，管道里传不了参数）：
#   curl -fsSL -o bootstrap.sh https://raw.githubusercontent.com/liyong-len/doc-check-skill/main/install/bootstrap.sh
#   bash bootstrap.sh --target-root /tmp/scratch-home
#
# 这个脚本只做两件事：
#   1. 把仓库取到 ~/.doc-check/repo（更新时保留已有的 .venv）
#   2. 调用仓库里的 install/install.sh 完成真正的安装
#
# 参数原样转交给 install/install.sh：--update、--dry-run、--status、--target-root。
#
# 环境变量：
#   DOC_CHECK_HOME         仓库存放目录的父目录，默认 ~/.doc-check
#   DOC_CHECK_REPO_URL     仓库压缩包的下载地址，默认 GitHub 上的 main 分支
#
# 注意：虚拟环境建在 ~/.doc-check/repo/.venv 里，技能目录里的 python-path.txt
# 指向它。删掉 ~/.doc-check 会让已装的技能失效——要换机器就重跑一次本脚本。
set -euo pipefail

REPO_SLUG="liyong-len/doc-check-skill"
DEFAULT_BRANCH="main"
TARBALL_URL="${DOC_CHECK_REPO_URL:-https://codeload.github.com/$REPO_SLUG/tar.gz/refs/heads/$DEFAULT_BRANCH}"

# 家目录。Windows 的 Git Bash 里 HOME 通常有；没有就用 USERPROFILE。
_home() {
    if [ -n "${HOME:-}" ]; then
        printf '%s' "$HOME"
    elif [ -n "${USERPROFILE:-}" ]; then
        printf '%s' "$USERPROFILE"
    else
        printf '%s' "$(cd ~ && pwd)"
    fi
}

INSTALL_ROOT="${DOC_CHECK_HOME:-$(_home)/.doc-check}"
REPO_DIR="$INSTALL_ROOT/repo"

usage() {
    printf '%s\n' \
        '用法：doc-check 引导安装 [选项]' \
        '  --update      覆盖已安装的副本，并清理已从仓库删除的文件' \
        '  --dry-run     只打印将写入的目录，不写任何文件' \
        '  --status      打印家目录根、各智能体目录与残留情况' \
        '  --target-root <路径>  改「~ 展开到哪个根目录」，不改 HOME/USERPROFILE' \
        '  -h, --help    显示本帮助并退出' \
        '' \
        '本脚本会先把仓库下载到：' \
        "  $REPO_DIR" \
        '然后调用仓库里的 install/install.sh 完成安装。'
}

ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --target-root)
            if [ $# -lt 2 ]; then
                echo "缺少 --target-root 的路径参数" >&2
                usage >&2
                exit 2
            fi
            ARGS+=(--target-root "$2"); shift 2 ;;
        --update|--dry-run|--status)
            ARGS+=("$1"); shift ;;
        -h|--help)
            usage; exit 0 ;;
        *)
            echo "未知参数：$1" >&2
            echo "可用参数：--update、--dry-run、--status、--target-root" >&2
            usage >&2
            exit 2 ;;
    esac
done

# --- 下载器 ---
# curl 与 wget 至少要有一个。Git Bash 自带 curl，macOS 一般也有。
#
# 下载目标用相对文件名，目录靠 cd 进去确定：
# Windows 上装着的 curl 是原生程序，不认 MSYS 的 /tmp 路径，
# 拿 "/tmp/xxx/repo.tar.gz" 当输出文件名，它会写到 C:\tmp\xxx\repo.tar.gz，
# 而 tar 读的是 MSYS 映射的那个路径——两个不同的文件，下一步就报「不是 gzip 格式」。
# 先进目录再写相对名，两边指向同一个文件。
if command -v curl >/dev/null 2>&1; then
    download() { curl -fsSL -o "repo.tar.gz" "$1"; }
elif command -v wget >/dev/null 2>&1; then
    download() { wget -q -O "repo.tar.gz" "$1"; }
else
    echo "未找到 curl 或 wget。请先安装其中之一再运行本脚本。" >&2
    exit 1
fi

# --- 把仓库取到 REPO_DIR ---
#
# 更新时保留已有的 .venv：虚拟环境里的脚本记着它自己的绝对路径，
# 而这个路径（~/.doc-check/repo/.venv）前后不变，所以搬回去还能用。
# 换句话说：先搬走，再换掉仓库目录，再搬回来。
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

echo "== doc-check 引导安装 =="
echo "仓库目录：$REPO_DIR"
echo "下载地址：$TARBALL_URL"

mkdir -p "$TMP/extract"
echo "下载仓库 ..."
if ! ( cd "$TMP" && download "$TARBALL_URL" ); then
    echo "下载失败：$TARBALL_URL" >&2
    echo "网络不通就重试几次；国内网络访问 GitHub 不稳时尤其常见。" >&2
    exit 1
fi

echo "解压 ..."
tar -xzf "$TMP/repo.tar.gz" -C "$TMP/extract"

# 压缩包里的顶层目录名带分支名（doc-check-skill-main/），不写死。
# 按「哪一层放着 install/install.sh」定位，比猜目录名可靠：
# GitHub 的压缩包是「顶层一个目录」，自制的可能是「直接铺在根上」。
SRC=""
for candidate in "$TMP/extract" "$TMP"/extract/*/; do
    if [ -f "$candidate/install/install.sh" ]; then
        SRC="${candidate%/}"
        break
    fi
done
if [ -z "$SRC" ]; then
    echo "压缩包内容不对：找不到 install/install.sh。" >&2
    exit 1
fi

VENV_STASH="$TMP/venv"
HAD_VENV=0
if [ -d "$REPO_DIR/.venv" ]; then
    mv "$REPO_DIR/.venv" "$VENV_STASH"
    HAD_VENV=1
fi

rm -rf "$REPO_DIR"
mkdir -p "$(dirname "$REPO_DIR")"
mv "$SRC" "$REPO_DIR"

if [ "$HAD_VENV" = "1" ]; then
    mv "$VENV_STASH" "$REPO_DIR/.venv"
    echo "已保留原有虚拟环境。"
fi

# --- 真正的安装 ---
echo ""
bash "$REPO_DIR/install/install.sh" ${ARGS[@]+"${ARGS[@]}"}

echo ""
echo "仓库位置：$REPO_DIR"
echo "技能依赖该目录下的虚拟环境，请勿删除。"
