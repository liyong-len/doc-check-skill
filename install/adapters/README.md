# 新增一个智能体适配

需要改三处：

1. `install/adapters.json` 增加一个条目，写明 `id`、`name`、`detect_paths`（用于探测该智能体是否安装）、`mode`（`skill_dir` 或 `manual`）、`skill_dir`（技能安装目录）、`entry`（入口文件名）、`usage`（用法提示）。
2. `install/adapters/<id>.md` 写该智能体的入口模板，模板中的 `{{SKILL_DIR}}` 会被安装器替换成**安装目录**的绝对路径。
3. 若该智能体的技能格式与 `SKILL.md` 不同，需要在模板中改写 frontmatter，并在 `scripts/` 旁加一段适配说明。

安装器无需改代码即可支持新适配项：装到智能体目录这一步由 `install/install_skill.py`
完成，`install.sh` 与 `install.ps1` 调用的是同一个文件。

## 装完之后技能目录里有什么

| 文件 | 来源 | 作用 |
|---|---|---|
| `SKILL.md` | 仓库原件（`entry` 指定的入口文件），安装时改写成绝对路径 | 智能体真正读取的入口，含完整三阶段流程；命令里的解释器与脚本路径都是绝对路径 |
| `AGENT.md` | `install/adapters/<id>.md` 模板 | 本智能体的补充说明，`{{SKILL_DIR}}` 已替换为安装目录的绝对路径 |
| `AGENTS.md` | 安装器生成 | `AGENTS.md` 约定的通用指路：入口是同目录的 `SKILL.md`，解释器见 `python-path.txt` |
| `references/`、`scripts/`、`requirements.txt` | 仓库原件 | 规则文档与脚本；仓库里删掉的文件会从安装目录清掉 |
| `python-path.txt` | 安装器写入 | 虚拟环境里 Python 解释器的绝对路径 |

模板写的是 `AGENT.md` 而不是 `SKILL.md`：入口文件 `SKILL.md` 里是完整的执行流程，
被模板覆盖后智能体只会读到一段指路文字，反而干不了活。

`AGENT.md`（单数）不是任何工具认的约定名，`AGENTS.md`（复数）才是。两个都写：
`AGENT.md` 放本智能体特有的补充说明，`AGENTS.md` 放通用的指路文字，
认 `AGENTS.md` 约定的工具因此也能找到入口。**Claude Code 读的是 `SKILL.md`**，
Codex CLI 读 `~/.codex/skills/<name>/SKILL.md`。

## 装好之后入口文件里的命令长什么样

仓库里的 `SKILL.md` 写的是相对路径（`python scripts/prepare.py`），那是给在仓库里
直接使用的人看的。装到智能体目录后，安装器把它改写成绝对路径：

```bash
"C:/repo/.venv/Scripts/python.exe" "C:/Users/me/.claude/skills/doc-check/scripts/prepare.py" --files ...
```

解释器取自 `python-path.txt`，脚本取自技能目录本身。这样智能体在哪个工作目录下
执行都能跑通——四个依赖只在仓库的 `.venv` 里，系统里那个没装依赖的 `python`
会直接 ImportError。

## 已确认的路径

| 智能体 | 路径 | 核实状态 |
|---|---|---|
| Claude Code | `~/.claude/skills/doc-check` | 已确认 |
| Codex CLI | `~/.codex/skills/doc-check` | 已确认，与 Claude Code 同用 SKILL.md frontmatter |
| WorkBuddy | `~/DoubaoWork/skills/doc-check` | 路径已确认，技能文件格式待验证 |
| DSH | `~/.dsh/skills/doc-check` | 未确认，候选值 |
