"""finding 的类别清单。

报告里出现的类别只有两套固定清单，合起来就是这个模块里的全部取值：

- **语义层**（阶段②，模型产出）九个类别。写在 references/content-rules.md 里，
  智能体按那份清单写 findings.json。
- **确定性层**（阶段①，脚本产出）十一个类别。写在 references/format-rules.md 里，
  语义层不重复报。

清单放在代码里而不是散在文档里，是为了校验能按字面量做：
模型自造的英文标签（「typo」「format」）必须在写 findings.json 时就被拦下来，
不能一路走到报告里显示成「未分类」。references/ 下两份文档里的清单
由 tests/test_fixwave_d_findings.py::test_the_category_list_matches_the_reference_documents
与本模块对照，文档改了而代码没改，测试会失败。
"""
from __future__ import annotations

# 语义层（阶段②）九个类别。
SEMANTIC_CATEGORIES = [
    "错别字用词",
    "标点格式",
    "前后矛盾",
    "主体名误用",
    "引用张冠李戴",
    "待补充内容",
    "数字逻辑",
    "表述不清",
    "术语一致性",
]

# 确定性层（阶段①）十一个类别。语义层不得使用。
DETERMINISTIC_CATEGORIES = [
    "字体一致性",
    "段落格式一致性",
    "标题层级体例",
    "图表题注体例",
    "表格体例",
    "列表与编号",
    "引用标记",
    "数字与单位",
    "主体名称",
    "主体串写",
    "术语与缩写",
]

# 报告里允许出现的全部类别。
ALL_CATEGORIES = SEMANTIC_CATEGORIES + DETERMINISTIC_CATEGORIES


def is_known_category(value: object) -> bool:
    """这个类别是不是清单里的合法取值。"""
    return str(value or "").strip() in ALL_CATEGORIES


def normalize_category(value: object) -> str:
    """类别字面量：去掉首尾空白。"""
    return str(value or "").strip()
