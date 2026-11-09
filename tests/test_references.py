from pathlib import Path
import json
import re

import schema

REF = Path(__file__).resolve().parent.parent / "references"

# 语义层（阶段②）固定类别
SEMANTIC_CATEGORIES = [
    "错别字用词", "标点格式", "前后矛盾", "主体名误用", "引用张冠李戴",
    "待补充内容", "数字逻辑", "表述不清", "术语一致性",
]

# 确定性层（阶段①）类别，语义层不得使用
DETERMINISTIC_CATEGORIES = [
    "字体一致性", "段落格式一致性", "标题层级体例", "图表题注体例", "表格体例",
    "列表与编号", "引用标记", "数字与单位", "主体名称", "主体串写", "术语与缩写",
]

# 缩写停用表，scripts/analyze.py 的 _ABBR_STOPLIST
ABBR_STOPLIST = [
    "PDF", "ISO", "XML", "HTML", "URL", "API", "KPI", "ROI", "TBD", "CPU",
    "RAM", "SSD", "LED", "CAD", "CAM", "PLC", "TCP", "UDP", "HTTP", "HTTPS",
]


def _read(name):
    return (REF / name).read_text(encoding="utf-8")


def test_all_reference_files_exist():
    for name in ["content-rules.md", "format-rules.md", "severity.md", "report-spec.md"]:
        assert (REF / name).exists(), name


def test_severity_doc_lists_all_severities():
    text = _read("severity.md")
    for s in schema.SEVERITIES:
        assert s in text


def test_severity_doc_lists_all_confidences():
    text = _read("severity.md")
    for c in schema.CONFIDENCES:
        assert c in text


def test_severity_doc_has_findings_schema():
    text = _read("severity.md")
    for field in ["id", "severity", "category", "detector", "confidence",
                  "file", "locator", "quote", "description", "suggestion"]:
        assert field in text


def test_content_rules_cover_all_nine_categories():
    text = _read("content-rules.md")
    for cat in ["错别字", "标点", "前后矛盾", "主体串写",
                "张冠李戴", "待补充", "数字逻辑", "表述不清", "术语"]:
        assert cat in text, cat


def test_severity_doc_introduces_no_extra_confidence_literals():
    # 参考文档不得自造 schema 里没有的置信度字面量：
    # 渲染器是按字面量分类展示的，文档与代码不一致会静默漏项
    text = _read("severity.md")
    for literal in set(re.findall(r"「(确定[^」]*)」", text)):
        assert literal in schema.CONFIDENCES, literal


def test_content_rules_fixed_category_list_excludes_deterministic_category():
    # 语义层的「主体名误用」与确定性层的「主体串写」是两个类别，
    # 固定清单里若出现「主体串写」，智能体会对同一问题报两次
    text = _read("content-rules.md")
    line = [l for l in text.splitlines() if l.startswith("- category 取值固定为")]
    assert line, "找不到固定类别清单"
    assert "主体串写" not in line[0]
    assert "主体名误用" in line[0]
    assert "待补充内容" in line[0]   # render.py §5 按这个字面量过滤


def test_format_rules_cover_all_ten_categories():
    text = _read("format-rules.md")
    for cat in ["字体一致性", "段落格式一致性", "标题层级体例", "图表题注体例",
                "表格体例", "主体名称", "数字与单位", "引用标记",
                "列表与编号", "术语与缩写"]:
        assert cat in text, cat


# --- 复查轮次 1：参考文档必须描述实际跑的检查，且不得把智能体引到确定性层类别上 ---


def test_severity_example_uses_semantic_category_and_llm_detector():
    # 示例是最容易被照抄的东西：示例里若是确定性层的类别，
    # 智能体照抄就会把脚本已经报过的问题再报一遍
    text = _read("severity.md")
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    assert m, "severity.md 里找不到 findings.json 示例"
    example = json.loads(m.group(1))
    assert example["category"] in SEMANTIC_CATEGORIES, example["category"]
    assert example["detector"] == "llm", example["detector"]


def test_severity_doc_does_not_point_at_format_rules():
    # format-rules.md 里的十一个类别全是确定性层的，
    # 字段说明不得把智能体指向那里
    text = _read("severity.md")
    assert "format-rules.md" not in text


def test_severity_doc_marks_deterministic_categories_as_script_only():
    text = _read("severity.md")
    for cat in DETERMINISTIC_CATEGORIES:
        assert cat in text, cat
    assert "不要在 findings.json 里写" in text


def test_reference_docs_describe_consistency_json_keys():
    # SKILL.md 要求智能体拿阶段①的结论当「确定」的依据，
    # 就必须知道 consistency.json 里有哪些键
    text = _read("severity.md")
    for key in ["style_profile", "issues", "per_file", "stats"]:
        assert key in text, key


def test_format_rules_states_region_retaining_rule():
    # 归组基准是 canonical_core：保留行政区划前缀。
    # 按 core_key 写会把北京与上海的两家同名公司并成一家
    text = _read("format-rules.md")
    assert "保留行政区划" in text
    assert "北京华信" in text and "上海华信" in text


def test_format_rules_states_suffix_condition():
    # 互为后缀还要多出来的那部分不含字号级连接词、也不是行政区划，
    # 否则「联合网络通信」会被并进「网络通信」，
    # 「上海华为技术有限公司」会被并进「华为技术有限公司」
    text = _read("format-rules.md")
    assert "不含字号级连接词" in text
    assert "也不是行政区划" in text


def test_format_rules_states_the_unified_connector_rule():
    """连接词只有一张表，分两类，抽取与归组用的是同一条规则。

    两套词各用一套的代价是「和」「同」在两处行为不一致：
    抽取时把「和深圳华信科技」的「和」裁掉，规范核心字号却留着它，
    同一个主体的两种写法因此对不上号。
    """
    text = _read("format-rules.md")
    assert "句子级" in text
    assert "字号级" in text
    # 两组词都要列全
    assert (
        "以及、并且、我方、贵司、双方、各方、甲方、乙方、中标人、投标人、供应商、"
        "承包人、采购方、招标人、招标代理、受托、委托、由"
    ) in text
    assert "联合、协作、为、和、同、经、并、及、与、是、从、给、向、对、或、代理" in text
    # 规则本身：位置决定，不看字本身
    assert "后面紧跟" in text


def test_format_rules_states_min_prefix_len_guard():
    """连接词不是无条件裁的：裁完至少要剩下 4 个字。"""
    text = _read("format-rules.md")
    assert "_MIN_PREFIX_LEN = 4" in text


def test_format_rules_has_known_limitations_section():
    text = _read("format-rules.md")
    parts = text.split("## 已知局限")
    assert len(parts) == 2, "缺少「已知局限」小节"
    body = parts[1]
    assert "嵌套" in body          # 嵌套括号
    assert "括号" in body           # 形式词被括号拆开
    assert "30" in body             # 字号长度上限
    assert "停用表" in body         # 缩写停用表


def test_format_rules_lists_abbreviation_stoplist():
    text = _read("format-rules.md")
    for abbr in ABBR_STOPLIST:
        assert abbr in text, abbr


def test_format_rules_does_not_push_abbreviations_to_semantic_layer():
    text = _read("format-rules.md")
    assert "脚本只提供候选缩写" not in text
    assert "语义层只需核对" not in text


def test_format_rules_says_citation_gaps_need_human_check():
    text = _read("format-rules.md")
    assert "越界" in text
    assert "人工核对" in text


def test_format_rules_limits_caption_gap_check_to_hyphenated_numbers():
    text = _read("format-rules.md")
    assert "不参与缺号检查" in text
    assert "图N.N" in text


# --- 修复波 B1：合同要写清 id 是派生字段、file 是文件标识 ---


def test_severity_doc_says_id_is_optional_and_derived():
    # id 是渲染器自己算的指纹。合同里没写清楚，智能体就会因为漏写它
    # 而把一整份 findings.json 交不出去
    text = _read("severity.md")
    assert "派生" in text
    assert "可省略" in text or "不必写" in text
    assert "渲染器" in text


def test_content_rules_says_not_to_write_id():
    text = _read("content-rules.md")
    assert "id" in text
    assert "派生" in text
    assert "不要写" in text


def test_reference_docs_explain_relative_file_identity():
    # 同名文件在不同目录下时 file 是相对路径，智能体照抄即可
    for name in ("severity.md", "content-rules.md"):
        text = _read(name)
        assert "report.docx" in text, name
        assert "相对路径" in text, name


# --- 修复波 B2：R65 / R67 语义层定级与 consistency.json 的键要说准 ---


def test_severity_doc_does_not_require_stage_one_evidence_for_certain():
    """阶段①不产出九类语义类别，拿它当门槛会让语义层永远写不出「确定」。

    判定口径是「能指出文档内的证据链」，不是「阶段①有没有对应依据」。
    """
    text = _read("severity.md")
    assert "不以阶段①有没有对应依据为准" in text
    assert "要能在阶段①的结论里找到依据" not in text


def test_severity_doc_states_evidence_chain_rule():
    text = _read("severity.md")
    assert "证据链" in text
    assert "合计与分项" in text
    assert "文档外的事实" in text


def test_severity_doc_describes_entities_names_keyed_by_core():
    """entities.names 按规范核心字号归并：同一主体的两种写法只留一条。"""
    text = _read("severity.md")
    row = [line for line in text.splitlines() if "entities.names" in line]
    assert row, "severity.md 里没有 entities.names 那一行"
    assert "canonical_core" in row[0] or "规范核心字号" in row[0]


def test_severity_doc_says_per_file_is_not_deduplicated():
    """entities.per_file 只在段内去重，跨段落不合并。"""
    text = _read("severity.md")
    row = [line for line in text.splitlines() if "entities.per_file" in line]
    assert row, "severity.md 里没有 entities.per_file 那一行"
    assert "去重" in row[0]
    assert "跨段落不合并" in row[0] or "自己先去重" in row[0]


def test_format_rules_states_truncation_boundary():
    """字号长度的实测口径：30 个字完整匹配，31 个字起丢开头的字。"""
    text = _read("format-rules.md")
    assert "30 个字仍能完整匹配" in text
    assert "31 个字起丢开头的字" in text
    assert "不会导致整条抽不到" in text


# --- 文档修正波：文档必须与代码的实际行为一致 ---
#
# 这些断言盯的是「文档里写下的那条边界还在不在」。
# 边界一旦被改回去（或者代码变了而文档没跟着改），这里会失败。


def test_format_rules_documents_the_silent_merge_limitation():
    """角色词前面带填充词时，两家公司会静默合并——文档必须写明这一条。

    旧版文档写的是「冠名是行政区划时两家不同的公司分得开，不会静默合并」，
    那句话对带填充词的写法是假的：触发条件其实是**角色词是不是名字串的开头**。
    """
    text = _read("format-rules.md")
    assert "角色词前面带填充词时，两家不同的公司会被并成一家" in text
    assert "本项目中标为北京自由空间科技有限公司" in text
    assert "本项目中标为上海自由空间科技有限公司" in text
    # 「冠名是行政区划就分得开」这句必须带上限定条件，不能再是裸承诺
    assert "两家不同的公司分得开，报的是疑似级的 P0「主体串写」，不会静默合并" not in text
    assert "在角色词位于名字串开头时" in text


def test_format_rules_states_the_real_trigger_of_the_restoration():
    """条款 (b) 的触发点是「角色词位于名字串开头」，不是「冠名是不是行政区划」。"""
    text = _read("format-rules.md")
    assert "还原名的覆盖面" in text
    assert "角色词位于名字串开头" in text


def test_format_rules_describes_guard_three_as_the_code_does():
    """第三条守卫只检查「以行政区划或国家前缀开头」，不检查是不是字号本身的开头。"""
    text = _read("format-rules.md")
    assert "以行政区划或国家前缀开头" in text
    # 旧说法：条款 (b) 会保证剩下的是「字号本身的开头」
    assert "只剩**字号本身的开头**" not in text
    assert "北京分公司确认自由空间科技有限公司" in text


def test_format_rules_states_the_copula_set():
    """系词表只有「是」「为」；「系」「即」不处理。"""
    text = _read("format-rules.md")
    assert '_COPULAS = ("是", "为")' in text
    assert "中标人系北京自由空间科技有限公司" in text


def test_format_rules_documents_the_role_word_table_oddities():
    """角色词表里收着「由」，而它不是角色词；碎片守卫的适用范围也要写明。"""
    text = _read("format-rules.md")
    assert "角色词表里也收了「由」" in text
    assert "_splits_a_connector_word" in text


def test_format_rules_documents_the_dropped_company_limitation():
    """通用片段判定用的是裁剪后的名字，整家公司可能被丢掉——要写明它的交互。"""
    text = _read("format-rules.md")
    assert "通用片段判定用的是裁剪后的名字，整家公司可能被丢掉" in text
    assert "本项目中标为青岛自由贸易服务有限公司" in text
    assert "通用片段不是名字" in text


def test_severity_doc_does_not_overstate_the_entity_list():
    """entities.names 的归并键是核心字号，不是「是不是同一家公司」。"""
    text = _read("severity.md")
    row = [line for line in text.splitlines() if "entities.names" in line]
    assert row, "severity.md 里没有 entities.names 那一行"
    assert "同一个主体只有一条" not in row[0]
    assert "核心字号" in row[0]


def test_reference_docs_say_the_entity_list_has_gaps():
    """主体名清单本身有缺口：报告里没有的名字不等于文档里没有这家公司。"""
    for name in ("severity.md", "content-rules.md", "report-spec.md"):
        text = _read(name)
        assert "不等于文档里没有这家公司" in text, name

