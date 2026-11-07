# doc-check 使用说明

本目录含一个文档检查技能，位于 `SKILL.md`。智能体应先读 `SKILL.md`，按其中描述的三个阶段执行。

## 用法

1. 确认环境已安装（Python 3.9+ 与四个依赖）。若仓库包含 `install/` 目录，安装脚本会创建 `.venv` 并装好依赖。
2. 在项目根目录执行阶段①。命令里的 `python` 必须是**装了四个依赖的那个解释器**，也就是仓库根目录 `.venv` 里的那个（Windows 是 `.venv\Scripts\python.exe`，macOS / Linux 是 `.venv/bin/python`）：

```bash
.venv/Scripts/python.exe scripts/prepare.py --files 文档1.docx 文档2.docx --depth standard --work .doc-check-work
```

3. 读取 `.doc-check-work/chunks.json` 与 `references/content-rules.md`，做语义判定，把结果写入 `.doc-check-work/findings.json`，结构见 `references/severity.md`。
4. 渲染报告：

```bash
.venv/Scripts/python.exe scripts/render.py --work .doc-check-work --out report.html
```

技能被安装到智能体目录后，入口文件 `SKILL.md` 里的命令已经被改写成绝对路径（解释器与脚本都指向技能目录），照抄即可，不必按上面的相对路径拼装。

## 约束

- 绝不修改用户的原始文档。
- 只写真实存在的问题，不要为凑数编造条目。
- 无法确认的结论标为「疑似 · 需人工核实」，不要伪装成确定结论。
- 未能抽取的文件必须在回复中如实说明。
