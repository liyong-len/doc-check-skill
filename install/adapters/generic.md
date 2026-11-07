# 通用智能体接入说明

把下面这段加入你的智能体项目说明文件（如 AGENTS.md、CLAUDE.md、.cursorrules、.windsurfrules）：

---
本项目使用 doc-check 技能检查文档。仓库根目录：{{REPO_ROOT}}

先阅读 {{REPO_ROOT}}/SKILL.md，按其中三阶段流程执行：
1. python "{{REPO_ROOT}}/scripts/prepare.py" --files <文件...> --depth standard --work .doc-check-work
2. 读 .doc-check-work/chunks.json 与 {{REPO_ROOT}}/references/content-rules.md，写 .doc-check-work/findings.json
3. python "{{REPO_ROOT}}/scripts/render.py" --work .doc-check-work --out report.html

绝不修改用户的原始文档。
---
