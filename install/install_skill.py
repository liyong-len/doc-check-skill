"""智能体安装阶段。install.sh 与 install.ps1 共用本文件。

两个安装脚本各自负责「选解释器 → 建虚拟环境 → 装依赖 → 依赖自检」，
装到各智能体目录这一步交给本文件。两个脚本调用同一份代码做同一件事，
行为就不会因为 shell 语法不同而分叉——这是「两个安装器行为一致」这条约束
最直接的落地方式：一致的不是两份脚本，是一份实现。

用法：
    python install/install_skill.py --repo-root <仓库根目录> --venv-py <解释器绝对路径> [--update]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# 装到智能体目录的内容。目录按目录同步：仓库里删掉的文件会从安装目录里清掉，
# 否则仓库里删掉的脚本会永远留在 ~/.claude/skills/doc-check/scripts/ 里。
MANAGED_DIRS = ("references", "scripts")
MANAGED_FILES = ("requirements.txt",)

# 入口文件里要改写的字面量。
#
# 仓库里的 SKILL.md 写的是相对路径（python scripts/prepare.py），
# 装到智能体目录后那套相对路径指向的是用户当前的工作目录，不是技能目录，
# 智能体照抄执行必然失败。安装时把命令改成绝对路径：
# 解释器取自 python-path.txt 指向的虚拟环境，脚本取自技能目录本身。
COMMAND_REWRITES = (
    ("python scripts/prepare.py", '"{python}" "{skill_dir}/scripts/prepare.py"'),
    ("python scripts/render.py", '"{python}" "{skill_dir}/scripts/render.py"'),
)

# 规则文档的引用同样改成绝对路径，否则智能体会在用户目录里找 references/。
DOC_REWRITES = (
    ("references/content-rules.md", "{skill_dir}/references/content-rules.md"),
    ("references/severity.md", "{skill_dir}/references/severity.md"),
    ("references/report-spec.md", "{skill_dir}/references/report-spec.md"),
)

# 写给智能体的补充说明里，解释器与脚本的位置。
AGENTS_NOTE = """# doc-check 技能（本目录）

本目录是 doc-check 技能的完整副本。智能体真正读取的入口是本目录下的 `SKILL.md`，
请完整读完后按其中描述的三阶段流程执行。

- 解释器：`python-path.txt` 里的绝对路径（装了 python-docx、openpyxl、pdfplumber、lxml 的那个）
- 脚本：本目录的 `scripts/`
- 规则文档：本目录的 `references/`

绝不修改用户的原始文档。
"""


def home_dir() -> Path:
    """用户主目录。

    Windows 用 USERPROFILE，POSIX 用 HOME。两个安装器用同一条规则，
    同一个 `~` 不会在两个脚本里指向不同目录。
    """
    if os.name == "nt":
        value = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    else:
        value = os.environ.get("HOME")
    if value:
        return Path(value)
    return Path.home()


def expand_home(path: str, home: Path) -> Path:
    """把 `~` 展开成主目录。非 `~` 开头的路径原样返回。"""
    if path == "~":
        return home
    if path.startswith("~/"):
        return home / path[2:]
    return Path(path)


def detect(agent: dict, home: Path) -> bool:
    """该智能体是否装在本机：适配项声明的目录存在，或其命令在 PATH 里。"""
    for raw in agent.get("detect_paths", []):
        if expand_home(raw, home).exists():
            return True
    for command in agent.get("detect_commands", []):
        if shutil.which(command):
            return True
    return False


def write_text_no_bom(path: Path, text: str) -> None:
    """写 UTF-8 文本，不带 BOM，行尾固定 LF。

    带 BOM 的 Markdown 在部分读取器里会多出一个看不见的字符；
    行尾跟着平台走会让「同一份文件」在不同机器上不是同一份。
    """
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def sync_dir(src: Path, dst: Path) -> int:
    """把 src 同步到 dst：复制新增文件，删除 dst 里多出来的旧文件。

    子目录**整体替换**，不合并：合并（dirs_exist_ok=True）只会覆盖同名文件，
    仓库里删掉的文件会永远留在安装目录里。`scripts/extractors/` 正是这种
    最容易变动的子目录，「仓库里删掉的文件会从技能目录里清掉」这条承诺
    必须在每一层都成立。
    """
    dst.mkdir(parents=True, exist_ok=True)
    removed = 0
    for child in sorted(dst.iterdir()):
        if child.name == "__pycache__" or child.suffix == ".pyc":
            _remove(child)
            removed += 1
            continue
        source = src / child.name
        if child.is_dir():
            if not source.is_dir():
                shutil.rmtree(child, ignore_errors=True)
                removed += 1
        elif not source.exists():
            child.unlink(missing_ok=True)
            removed += 1
    for child in sorted(src.iterdir()):
        if child.name == "__pycache__":
            continue
        target = dst / child.name
        if child.is_dir():
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(
                child,
                target,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        else:
            shutil.copy2(child, target)
    return removed


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def build_entry_text(entry_path: Path, skill_dir: Path, venv_py: str) -> str:
    """把仓库里的入口文件改写成装好之后的绝对路径版本。"""
    text = entry_path.read_text(encoding="utf-8-sig")
    values = {"python": Path(venv_py).as_posix(), "skill_dir": skill_dir.as_posix()}
    for old, new in COMMAND_REWRITES + DOC_REWRITES:
        if old not in text:
            raise SystemExit(
                f"入口文件 {entry_path} 里找不到待改写的片段「{old}」，"
                "安装器与仓库内容已经不一致，请先修好入口文件。"
            )
        text = text.replace(old, new.format(**values))
    return text


def install_agent(
    repo_root: Path,
    agent: dict,
    target: Path,
    venv_py: str,
) -> None:
    """把技能装进一个智能体目录。"""
    target.mkdir(parents=True, exist_ok=True)

    # 入口文件：智能体真正读的是它，命令必须是绝对路径。
    entry = agent.get("entry", "SKILL.md")
    write_text_no_bom(
        target / entry,
        build_entry_text(repo_root / entry, target, venv_py),
    )

    for name in MANAGED_DIRS:
        sync_dir(repo_root / name, target / name)
    for name in MANAGED_FILES:
        shutil.copy2(repo_root / name, target / name)

    # 解释器的绝对路径：智能体与 check_env.py 都靠它找到装了依赖的那个 Python。
    write_text_no_bom(target / "python-path.txt", venv_py)

    # AGENT.md：本智能体的补充说明，指向装好之后的这份副本，而不是仓库。
    template = repo_root / "install" / "adapters" / f"{agent['id']}.md"
    if template.exists():
        body = template.read_text(encoding="utf-8-sig")
        body = body.replace("{{SKILL_DIR}}", target.as_posix())
        body = body.replace("{{REPO_ROOT}}", repo_root.as_posix())
        write_text_no_bom(target / "AGENT.md", body)

    # AGENTS.md：AGENTS.md 是很多工具认的约定名，AGENT.md 不是。
    write_text_no_bom(target / "AGENTS.md", AGENTS_NOTE)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="doc-check 智能体安装阶段")
    parser.add_argument("--repo-root", required=True, help="仓库根目录")
    parser.add_argument("--venv-py", required=True, help="虚拟环境解释器的绝对路径")
    parser.add_argument("--update", action="store_true", help="覆盖已安装的副本")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    venv_py = args.venv_py
    home = home_dir()

    adapters = json.loads(
        (repo_root / "install" / "adapters.json").read_text(encoding="utf-8")
    )

    installed: list[tuple[str, str, str]] = []
    skipped: list[str] = []

    for agent in adapters["agents"]:
        if agent.get("mode") == "manual":
            skipped.append(agent["name"])
            continue
        if not detect(agent, home):
            skipped.append(agent["name"])
            continue
        target = expand_home(agent["skill_dir"], home)
        install_agent(repo_root, agent, target, venv_py)
        installed.append((agent["name"], str(target), agent.get("usage", "")))

    print("")
    print("== 安装完成 ==")
    for name, path, usage in installed:
        print(f"[已安装] {name} -> {path}")
        print(f"          用法：{usage}")
    if skipped:
        print("")
        print(f"未检测到（已跳过）：{'、'.join(skipped)}")
    print("")
    print(f"通用接入方式见 {(repo_root / 'install' / 'adapters' / 'generic.md').as_posix()}")
    print(f"仓库目录：{repo_root}")
    return 0


if __name__ == "__main__":
    # 两条流都要是 UTF-8：安装器（install.ps1）的提示与这里的输出
    # 写进同一个 stdout，两边编码不一致，整条流就解码不出来。
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    raise SystemExit(main())
