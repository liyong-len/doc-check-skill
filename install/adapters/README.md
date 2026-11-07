# 新增一个智能体适配

需要改三处：

1. `install/adapters.json` 增加一个条目，写明 `id`、`name`、`detect_paths`（用于探测该智能体是否安装）、`mode`（`skill_dir` 或 `manual`）、`skill_dir`（技能安装目录）、`entry`（入口文件名）、`usage`（用法提示）。
2. `install/adapters/<id>.md` 写该智能体的入口模板，模板中的 `{{REPO_ROOT}}` 会被安装器替换成仓库绝对路径。
3. 若该智能体的技能格式与 `SKILL.md` 不同，需要在模板中改写 frontmatter，并在 `scripts/` 旁加一段适配说明。

安装器无需改代码即可支持新适配项。

## 装完之后技能目录里有什么

| 文件 | 来源 | 作用 |
|---|---|---|
| `SKILL.md` | 仓库原件（`entry` 指定的入口文件） | 智能体真正读取的入口，含完整三阶段流程 |
| `AGENT.md` | `install/adapters/<id>.md` 模板 | 本智能体的补充说明，`{{REPO_ROOT}}` 已替换为仓库绝对路径 |
| `references/`、`scripts/`、`requirements.txt` | 仓库原件 | 规则文档与脚本 |
| `python-path.txt` | 安装器写入 | 虚拟环境里 Python 解释器的绝对路径 |

模板写的是 `AGENT.md` 而不是 `SKILL.md`：入口文件 `SKILL.md` 里是完整的执行流程，
被模板覆盖后智能体只会读到一段指路文字，反而干不了活。

## 已确认的路径

| 智能体 | 路径 | 核实状态 |
|---|---|---|
| Claude Code | `~/.claude/skills/doc-check` | 已确认 |
| Codex CLI | `~/.codex/skills/doc-check` | 已确认，与 Claude Code 同用 SKILL.md frontmatter |
| WorkBuddy | `~/DoubaoWork/skills/doc-check` | 路径已确认，技能文件格式待验证 |
| DSH | `~/.dsh/skills/doc-check` | 未确认，候选值 |
