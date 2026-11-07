---
name: doc-check
description: 检查一组投标文档的内容与格式问题，产出单文件 HTML 报告。当用户要求检查文档、审阅标书、核对投标文件、排查错别字、企业名称写错、引用张冠李戴、体例混乱、前后矛盾、多主体写混或字体排版不一致时使用。
---

# 文档检查技能

技能说明见同目录下的 `references/` 与 `SKILL.md`。

仓库根目录：{{REPO_ROOT}}

执行前先阅读 `SKILL.md`，按其中描述的三阶段流程执行：

1. `python "{{REPO_ROOT}}/scripts/prepare.py" --files <文件...> --depth standard --work .doc-check-work`
2. 读 `.doc-check-work/chunks.json` 与 `{{REPO_ROOT}}/references/content-rules.md`，写 `.doc-check-work/findings.json`
3. `python "{{REPO_ROOT}}/scripts/render.py" --work .doc-check-work --out report.html`

绝不修改用户的原始文档。
