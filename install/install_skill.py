"""智能体安装阶段。install.sh 与 install.ps1 共用本文件。

两个安装脚本各自负责「选解释器 → 建虚拟环境 → 装依赖 → 依赖自检」，
装到各智能体目录这一步交给本文件。两个脚本调用同一份代码做同一件事，
行为就不会因为 shell 语法不同而分叉——这是「两个安装器行为一致」这条约束
最直接的落地方式：一致的不是两份脚本，是一份实现。

用法：
    python install/install_skill.py --repo-root <仓库根目录> --venv-py <解释器绝对路径> [--update]
                                    [--dry-run] [--target-root <路径>] [--status]

三个安全阀：
    --dry-run      只解析目标目录并打印，不写任何文件
    --target-root  改「~ 展开到哪个根目录」，不必动 HOME/USERPROFILE
    --status       打印家目录根、各适配项的目标路径与残留情况

另外：没给 --target-root / DOC_CHECK_TARGET_ROOT 时，写入真实家目录之前
会先打印一段横幅（见 print_home_banner）。install.sh 与 install.ps1 都调用
本文件，两个安装器的横幅因此是同一段文字。
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


def target_root(explicit: str | None = None) -> Path:
    """`~` 展开到的根目录。

    优先级：--target-root > 环境变量 DOC_CHECK_TARGET_ROOT > 用户主目录。

    有了它就不必改 HOME/USERPROFILE 就能把技能装到别处。改环境变量装到
    真实用户目录去的事故已经发生过两次：装完再去删，删没删干净也没人说得清。
    """
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("DOC_CHECK_TARGET_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return home_dir()


def expand_home(path: str, home: Path) -> Path:
    """把 `~` 展开成主目录。非 `~` 开头的路径原样返回。"""
    if path == "~":
        return home
    if path.startswith("~/"):
        return home / path[2:]
    return Path(path)


# 已知的智能体技能根目录（相对于家目录根）。
#
# --status 要把「哪里有残留」说清楚，不能只报本次要写的那一个：
# 装过又忘了删的残留目录往往在别的适配项下面。
KNOWN_SKILL_ROOTS = [
    ".claude/skills",
    ".codex/skills",
    "DoubaoWork/skills",
    ".dsh/skills",
]


def skill_targets(adapters: dict, root: Path) -> list[tuple[dict, Path]]:
    """每个适配项的目标目录（绝对路径）。跳过「手动接入」那一项。"""
    rows = []
    for agent in adapters["agents"]:
        if agent.get("mode") == "manual":
            continue
        rows.append((agent, expand_home(agent["skill_dir"], root)))
    return rows


def leftover_dirs(root: Path) -> list[Path]:
    """已知智能体根目录下残留的 doc-check 目录。"""
    out = []
    for rel in KNOWN_SKILL_ROOTS:
        candidate = root / rel / "doc-check"
        if candidate.exists():
            out.append(candidate)
    return out


def _install_note(redirected: bool, dry_run: bool, status: bool) -> str:
    """安装提示语：说清楚这一次会不会写真实家目录。

    只读的那两种模式（试运行、状态查询）不写任何文件，
    说「将写入真实家目录」是假的——它们说的是**正式安装**会写。
    """
    if redirected:
        return ("（由 --target-root / DOC_CHECK_TARGET_ROOT 指定，"
                "不会写入真实家目录）")
    if dry_run:
        return ("（未指定 --target-root / DOC_CHECK_TARGET_ROOT；"
                "正式安装会写入真实家目录，本次试运行不写入任何文件）")
    if status:
        return ("（未指定 --target-root / DOC_CHECK_TARGET_ROOT；"
                "正式安装会写入真实家目录，本次状态查询只读，不写入任何文件）")
    return ("（未指定 --target-root / DOC_CHECK_TARGET_ROOT，"
            "将写入真实家目录）")


def print_status(adapters: dict, root: Path, repo_root: Path,
                 note: str = "") -> int:
    """打印安装状态：家目录根、各适配项的目标路径、残留情况。

    输出的最后一行是机器可读的结论（干净 / 残留 N 处），
    一条命令就能判断机器上到底有没有残留，不必靠人回忆。

    note 是跟在根目录后面的一句话（说明这一次会不会写真实家目录）。
    它排在根目录**之后**：先把解析出来的根目录摆出来，再说话。
    """
    print("== doc-check 安装状态 ==")
    print(f"根目录（~ 展开到）：{root}")
    if note:
        print(f"  {note}")
    print(f"仓库目录：{repo_root}")
    print("")
    print("已知智能体目录：")
    for agent, target in skill_targets(adapters, root):
        state = "已安装" if target.exists() else "未安装"
        print(f"  [{state}] {agent['name']}  {target}")
    print("")
    leftovers = leftover_dirs(root)
    print("残留的 doc-check 目录：")
    if leftovers:
        for path in leftovers:
            print(f"  [残留] {path}")
    else:
        print("  （无）")
    print("")
    if leftovers:
        print(f"doc-check 安装状态：残留 {len(leftovers)} 处")
    else:
        print("doc-check 安装状态：干净")
    return 0


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


def print_home_banner(to_install: list[tuple[dict, Path]]) -> None:
    """写入真实家目录之前，先把这件事明明白白地说出来。

    没有它，最危险的那条路（一条命令直接装进用户自己的家目录）
    恰好是唯一没有提示的一条路：输出里有目标路径，却没有一句话
    说明「这就是你的真家目录」。

    这是一段提示，不是一道闸：不需要任何参数，照常一条命令就能装。
    install.sh 与 install.ps1 都调用本文件，因此两个安装器的横幅
    是同一段文字，不会分叉。
    """
    if not to_install:
        return
    print("")
    print("⚠ 即将写入你的真实家目录")
    for agent, target in to_install:
        print(f"  {agent['name']} -> {target}")
    print("  （若这是误操作，按 Ctrl-C 取消，或用 --dry-run 先看会写到哪里）")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="doc-check 智能体安装阶段")
    parser.add_argument("--repo-root", required=True, help="仓库根目录")
    parser.add_argument("--venv-py", required=True, help="虚拟环境解释器的绝对路径")
    parser.add_argument("--update", action="store_true", help="覆盖已安装的副本")
    parser.add_argument("--dry-run", action="store_true",
                        help="只解析目标目录并打印，不写任何文件")
    parser.add_argument("--target-root", default=None,
                        help="改「~ 展开到哪个根目录」，不必改 HOME/USERPROFILE")
    parser.add_argument("--status", action="store_true",
                        help="打印家目录根、各适配项的目标路径与残留情况")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    venv_py = args.venv_py
    root = target_root(args.target_root)
    redirected = bool(args.target_root or os.environ.get("DOC_CHECK_TARGET_ROOT"))

    adapters = json.loads(
        (repo_root / "install" / "adapters.json").read_text(encoding="utf-8")
    )

    if args.status:
        # 状态查询只读：先把**解析出来的根目录**印出来，
        # 「本次只读」那句话跟在根目录后面——话要跟在事实后面。
        return print_status(adapters, root, repo_root,
                            note=_install_note(redirected, False, True))

    print("== doc-check 智能体安装阶段 ==")
    print(f"根目录（~ 展开到）：{root}")
    print(f"  {_install_note(redirected, args.dry_run, False)}")
    print(f"仓库目录：{repo_root}")

    rows = skill_targets(adapters, root)
    to_install = [(agent, target) for agent, target in rows if detect(agent, root)]

    # 目标路径在**第一次写盘之前**就打印出来。
    # 装完了再打印，看的人已经没法回头确认装到哪儿去了。
    print("")
    if args.dry_run:
        print("== 试运行（--dry-run）：不会写入任何文件 ==")
    else:
        # 只有真的写进真实家目录时才喊。
        # 试运行不写任何文件，状态查询只读，两条路上都不必喊。
        if not redirected:
            print_home_banner(to_install)
    print("本次将写入以下目录：")
    for agent, target in rows:
        if (agent, target) in to_install:
            print(f"  [将写入] {agent['name']} -> {target}")
        else:
            print(f"  [将跳过] {agent['name']} -> {target}（未检测到该智能体）")
    print("")

    if args.dry_run:
        print("试运行结束：没有写入任何文件。")
        return 0

    installed: list[tuple[str, str, str]] = []
    skipped: list[str] = []

    for agent in adapters["agents"]:
        if agent.get("mode") == "manual":
            skipped.append(agent["name"])
            continue
        if not detect(agent, root):
            skipped.append(agent["name"])
            continue
        target = expand_home(agent["skill_dir"], root)
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
    # 回执里再写一遍目标路径：检测是全局的（PATH 上的 claude 命令与家目录无关），
    # 安装不是。读回执的人必须一眼看出东西装到了哪儿。
    print("本次写入的目录：")
    for _, path, _ in installed:
        print(f"  {path}")
    if not installed:
        print("  （无）")
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
