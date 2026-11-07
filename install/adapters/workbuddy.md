---
name: doc-check
description: 检查一组投标文档的内容与格式问题，产出单文件 HTML 报告。当用户要求检查文档、审阅标书、核对投标文件、排查错别字、企业名称写错、引用张冠李戴、体例混乱、前后矛盾、多主体写混或字体排版不一致时使用。
---

# 文档检查技能（WorkBuddy）

技能说明见同目录下的 `references/` 与 `SKILL.md`。

技能目录：{{SKILL_DIR}}

`SKILL.md` 是智能体真正读取的入口文件，里面的命令已被安装器改写成绝对路径：
解释器是同目录 `python-path.txt` 里指向的虚拟环境，脚本在本目录的 `scripts/` 下。
执行前先完整阅读 `SKILL.md`，按其中描述的三阶段流程执行：

1. 用 `{{SKILL_DIR}}/python-path.txt` 里的解释器运行 `{{SKILL_DIR}}/scripts/prepare.py`
2. 读 `.doc-check-work/chunks.json` 与 `{{SKILL_DIR}}/references/content-rules.md`，写 `.doc-check-work/findings.json`
3. 用同一个解释器运行 `{{SKILL_DIR}}/scripts/render.py`

绝不修改用户的原始文档。
