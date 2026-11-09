"""修复波 I 的回归测试。

覆盖 C-H1：还原名的「切在同一个连接词上」是一条正确但很窄的特例。
散文里的分隔词与字号内部的连接词**不是同一个词**时，那条特例不适用，
真字号被劈掉一半：

    中标人为北京自由空间科技有限公司。
    -> 空间科技有限公司          （was: 北京自由空间科技有限公司）

后果有三个：
- 两家不同的公司被并成一家，**一条 finding 都不报**；
- 一家公司被拆成两个主体，报出一条假的疑似 P0「主体串写」；
- 真公司的全称根本进不了报告。

修法是还原名的**条款 (b)**：更宽的候选被裁掉的那一段整个是一个
完整的角色词（中标人、实施单位、招标人、采购方、乙方、甲方、我方、
贵方、供货商、承接方…）时，那一刀落在词边界上，剩下的是真字号。

条款 (b) 有四道守卫，缺一不可（前缀以角色词开头、那一刀没有把一个
更长的角色词劈成两半、角色词与误切点之间只剩字号本身的开头、候选
不是句子碎片）。这一波**没有**削弱归组规则——两条规则冲突时归组规则
优先，冲突写进 references/format-rules.md。

这一波还改了规则文档里两句不成立的话（见文件末尾的文档测试）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from analyze import analyze
from entities import (
    extract_company_names,
    extract_company_occurrences,
    group_variants,
    same_entity,
)

ROOT = Path(__file__).resolve().parent.parent
FORMAT_RULES = ROOT / "references" / "format-rules.md"

# 企业形式词：全称必须以其中一个结尾。
FORM_WORDS = ("股份有限公司", "有限责任公司", "集团有限公司", "有限公司")

# 句子级连接词：出现在名字里就说明那段是句子的成分而不是字号。
# 「由」除外——它常出现在字号中间（自由、理由、由于）。
SENTENCE_MARKERS = (
    "以及", "并且", "我方", "贵司", "双方", "各方", "甲方", "乙方",
    "中标人", "投标人", "供应商", "承包人", "采购方", "招标人",
    "招标代理", "受托", "委托",
)

# 行业词：字号剥掉行政区划后只剩行业词，说明切错了。
INDUSTRY_WORDS = (
    "科技", "技术", "信息", "网络", "发展", "建设", "投资", "贸易",
    "工程", "服务", "咨询",
)


def _doc(name, texts):
    blocks = [
        {"index": i, "kind": "paragraph", "text": t, "style": None,
         "section_path": "第一章"}
        for i, t in enumerate(texts)
    ]
    return {
        "file": name, "type": "docx", "sha256": "0" * 64, "title": "",
        "stats": {"paragraphs": len(blocks), "tables": 0, "pages": 1,
                  "words": 50, "rows": 0, "sheets": 0},
        "sections": [], "blocks": blocks,
        "entities": [], "citations": [], "numbers": [], "notes": [],
    }


def _format_rules() -> str:
    return FORMAT_RULES.read_text(encoding="utf-8")


def _known_limitations() -> str:
    parts = _format_rules().split("## 已知局限")
    assert len(parts) == 2, "缺少「已知局限」小节"
    return parts[1]


def _restored(sentence: str) -> str:
    occurrences = extract_company_occurrences(sentence)
    assert occurrences, sentence
    return occurrences[0][1]


def _looks_like_a_company_name(name: str) -> bool:
    """这个名字像不像一个公司名（而不是一段句子碎片）。

    判据全是字面上的，不查词表——中文里句子碎片与字号的差别常常只是
    「由」在「自由」里的位置，词表判不了。

    - 以企业形式词结尾（是全称，不是裸字号）；
    - 不以连接词或系词开头（`为北京…`、`方是北京…`）；
    - 不含句子级连接词（「由」除外）；
    - 剥掉形式词与行政区划之后，字号里还有自己的字。
    """
    if not any(name.endswith(w) for w in FORM_WORDS):
        return False
    core = name
    for w in FORM_WORDS:
        if core.endswith(w):
            core = core[: -len(w)]
            break
    if not core:
        return False
    if name[0] in ("为", "是", "方", "要求", "认可"):
        return False
    for marker in SENTENCE_MARKERS:
        if marker in name:
            return False
    # 字号里还有自己的字：不是光秃秃的行业词
    rest = core
    for w in INDUSTRY_WORDS:
        if rest.startswith(w):
            rest = rest[len(w):]
            break
    return bool(rest)


# --- C-H1：角色词前缀下的还原 ---


@pytest.mark.parametrize("sentence,expected", [
    ("中标人为北京自由空间科技有限公司。", "北京自由空间科技有限公司"),
    ("实施单位是广州自由人电子商务有限公司。", "广州自由人电子商务有限公司"),
    ("乙方为北京自由之路文化传媒有限公司。", "北京自由之路文化传媒有限公司"),
    ("实施单位是中国自由贸易港城有限公司。", "中国自由贸易港城有限公司"),
    ("本项目由中国自由贸易港城有限公司中标。", "中国自由贸易港城有限公司"),
])
def test_the_restored_name_keeps_the_whole_company_name(sentence, expected):
    """散文里的分隔词与字号内部的连接词不是同一个词时，也还原得回来。

    修复前：这一句还原出的是 `空间科技有限公司`、`人电子商务有限公司`
    这样的残缺名，真公司的全称进不了报告。
    """
    assert _restored(sentence) == expected


@pytest.mark.parametrize("sentence,forbidden", [
    ("受托方是北京华信科技有限公司。", "方是北京华信科技"),
    ("根据采购方要求由北京华信科技有限公司负责实施。", "要求由北京华信科技"),
])
def test_the_restored_name_is_never_a_sentence_fragment(sentence, forbidden):
    """条款 (b) 的四道守卫：碎片还原不得复活。

    - `受托方是…`：那一刀把角色词「受托方」劈开了，不是词边界；
    - `根据采购方要求由…`：前缀整段是「根据采购方」，带了填充词
      「根据」，不是一个角色词。
    """
    restored = _restored(sentence)
    assert forbidden not in restored, restored
    assert restored == "北京华信科技有限公司", restored


def test_the_restored_name_is_a_plausible_company_name():
    """还原名必须**像**一个公司名，不能只是「一段更长的子串」。

    这是给条款 (b) 加的一道网：一个只按「取更宽的那一段」写的还原，
    会把 `为北京自由空间科技` 这种东西当成公司名发布出去。
    """
    for sentence in (
        "中标人为北京自由空间科技有限公司。",
        "实施单位是广州自由人电子商务有限公司。",
        "乙方为北京自由之路文化传媒有限公司。",
        "实施单位是中国自由贸易港城有限公司。",
        "本项目由中国自由贸易港城有限公司中标。",
        "受托方是北京华信科技有限公司。",
        "根据采购方要求由北京华信科技有限公司负责实施。",
    ):
        restored = _restored(sentence)
        assert _looks_like_a_company_name(restored), (sentence, restored)


def test_the_trimmed_name_is_unchanged():
    """裁剪口径一个字没动：裁剪后的名字仍然取**最短**的合格切分。

    这一条是「不削弱既有口径」的保证——这一波只动还原名。
    """
    assert extract_company_names("中标人为北京自由空间科技有限公司。") == [
        "空间科技有限公司"
    ]
    assert extract_company_names("实施单位是广州自由人电子商务有限公司。") == [
        "人电子商务有限公司"
    ]


# --- C-H1 的三个后果 ---


def test_one_company_across_many_prose_prefixes_is_one_subject():
    """同一家公司、五种散文前缀：一个主体，没有 P0，也没有 P1。

    修复前：这五句被拆成好几个主体，报出一条假的疑似 P0「主体串写」。
    """
    company = "北京自由空间科技有限公司"
    docs = [_doc("a.docx", [
        "实施单位是北京自由空间科技有限公司。",
        "本项目由北京自由空间科技有限公司中标。",
        "中标人为北京自由空间科技有限公司。",
        "乙方为北京自由空间科技有限公司。",
        "北京自由空间科技有限公司的联系方式如下。",
    ])]
    result = analyze(docs)

    per_file = result["entities"]["per_file"]["a.docx"]
    assert set(per_file) == {company}, per_file

    groups = result["entities"]["variants"]
    assert len(groups) == 1, groups
    assert groups[0]["names"] == [company], groups

    issues = result["issues"]
    assert [i for i in issues if i["category"] == "主体串写"] == [], issues
    assert [i for i in issues if i["category"] == "主体名称"] == [], issues


def test_two_different_companies_in_prose_stay_two_subjects():
    """两家不同的公司都在散文里：两个主体，疑似 P0，没有确定级 P1。

    修复前：两家的真名都被劈成 `空间科技有限公司`，并成一家，
    **一条 finding 都不报**——文档里写混了两家公司，工具一声不吭。
    """
    docs = [_doc("a.docx", [
        "中标人为北京自由空间科技有限公司。",
        "中标人为上海自由空间科技有限公司。",
    ])]
    result = analyze(docs)

    per_file = result["entities"]["per_file"]["a.docx"]
    assert set(per_file) == {
        "北京自由空间科技有限公司", "上海自由空间科技有限公司",
    }, per_file

    groups = result["entities"]["variants"]
    assert len(groups) == 2, groups

    issues = result["issues"]
    mixed = [i for i in issues if i["category"] == "主体串写"]
    assert len(mixed) == 1, issues
    assert mixed[0]["severity"] == "P0", mixed[0]
    assert mixed[0]["confidence"] == "疑似 · 需人工核实", mixed[0]
    assert "北京自由空间科技有限公司" in mixed[0]["description"], mixed[0]
    assert "上海自由空间科技有限公司" in mixed[0]["description"], mixed[0]

    # 确定级的「主体名称」绝不能出现：那会让用户去统一两家公司
    assert [i for i in issues if i["category"] == "主体名称"] == [], issues


def test_the_full_company_name_reaches_the_report():
    """真公司的全称必须进得了报告（还原名是报告与聚类用的那个名字）。"""
    docs = [_doc("a.docx", [
        "实施单位是北京自由空间科技有限公司。",
        "本项目由北京自由空间科技有限公司中标。",
    ])]
    result = analyze(docs)

    names = [n["name"] for n in result["entities"]["names"]]
    assert names == ["北京自由空间科技有限公司"], names


# --- 两条取舍不得被这一波削弱 ---


def test_the_grouping_rule_still_splits_a_proper_noun_head():
    """多出来的那部分是一段专有名词时，仍然不合并，只报疑似 P0。

    这一波动了还原名，不能顺手把归组规则放宽——放宽了就会报出确定级的
    P1「主体名称」，让用户去统一两家不同的公司。
    """
    assert not same_entity("北方自由贸易港城有限公司", "贸易港城有限公司")
    groups = group_variants([
        "北方自由贸易港城有限公司", "贸易港城有限公司",
    ])
    assert len(groups) == 2, groups

    docs = [_doc("a.docx", [
        "本项目由北方自由贸易港城有限公司中标。",
        "中国自由贸易港城有限公司的联系方式如下。",
    ])]
    issues = analyze(docs)["issues"]
    assert [i for i in issues if i["category"] == "主体名称"] == [], issues
    mixed = [i for i in issues if i["category"] == "主体串写"]
    assert len(mixed) == 1, issues
    assert mixed[0]["confidence"] == "疑似 · 需人工核实", mixed[0]


def test_the_grouping_rule_still_splits_two_full_names():
    """两个全称差一段专有名词时，仍然不合并。"""
    assert not same_entity("国投华信科技有限公司", "华信科技有限公司")
    groups = group_variants([
        "国投华信科技有限公司", "华信科技有限公司",
    ])
    assert len(groups) == 2, groups


def test_a_prose_mention_and_a_bare_mention_may_report_a_suspicious_p0():
    """散文提法与裸字符串提法对不上时，报的是**疑似** P0。

    这一条是已记录的取舍（`references/format-rules.md`「已知局限」）：
    把它并成一家会报出确定级的 P1「主体名称」，性质更坏。
    """
    docs = [_doc("a.docx", [
        "本项目由中国自由贸易港城有限公司中标。",
        "中国自由贸易港城有限公司的联系方式如下。",
    ])]
    issues = analyze(docs)["issues"]
    assert [i for i in issues if i["category"] == "主体名称"] == [], issues
    mixed = [i for i in issues if i["category"] == "主体串写"]
    assert len(mixed) == 1, issues
    assert mixed[0]["severity"] == "P0", mixed[0]
    assert mixed[0]["confidence"] == "疑似 · 需人工核实", mixed[0]


# --- 规则文档：这一波改掉的两句不成立的话 + 四个小项 ---


def test_the_rules_describe_both_restoration_clauses():
    """文档要写清楚还原名有**两条**规则。

    只写「切在同一个连接词上」会让读者以为散文里的角色词前缀
    （`中标人为…`）与还原名无关——那正是 C-H1 藏了这么久的原因。
    """
    text = _format_rules()
    assert "还原名的两条规则" in text
    assert "条款 (a)" in text and "条款 (b)" in text
    assert "整个是一个完整的角色词" in text


def test_the_rules_do_not_claim_prose_mentions_are_always_separated():
    """文档不得再说「散文里两家不同的公司……不会被并成一家」。

    条款 (b) 要求角色词与误切点之间只剩字号本身的开头（行政区划或
    国家前缀）。冠名不是行政区划时还原不出来，两家不同的公司会被并成
    一家，而且一条 finding 都不报——这句话必须写进「已知局限」。
    """
    text = _format_rules()
    assert (
        "还原名把它们分得开（`中国自由贸易港城有限公司` 与 "
        "`北方自由贸易港城有限公司`）" not in text
    )
    body = _known_limitations()
    assert "散文里还原不出来的情况" in body
    assert "两家不同的公司会被并成一家" in body
    assert "一条 finding 都不报" in body


def test_the_known_limitations_keep_the_bare_string_case():
    """裸字符串还原不出来这一条不能被新条目顶掉。"""
    body = _known_limitations()
    assert "还原不出来的情况是裸字符串" in body


def test_the_rules_list_the_industry_word_condition():
    """M-H3：后缀条件的清单漏了「也不是以行业词结尾」。

    `_extra_head_is_clean` 实际还检查多出来的那部分是不是以行业词结尾，
    文档只列了三条，读者会对不上号。
    """
    text = _format_rules()
    assert "也不是以行业词结尾" in text


def test_the_rules_use_the_real_finding_names():
    """M-H4：P1 的类别是「主体名称」，建议文本要照实写。

    写成「统一名称写法」会让人读成「工具替你挑了一个名字」，而实际的
    建议是「需人工核实后确定」。
    """
    text = _format_rules()
    assert "确定级的 P1「主体名称」" in text
    assert (
        "全套文档统一使用同一名称；文档中没有判断哪一种是正式全称的依据，"
        "需人工核实后确定" in text
    )


def test_the_rules_describe_the_fragment_guard():
    """条款 (b) 的碎片检查（角色词被劈成两半）要写进文档。

    `受托方是北京华信科技有限公司` 那一刀把「受托方」劈开了，
    这一条是它与合法还原之间的分界。
    """
    text = _format_rules()
    assert "劈成两半" in text
    assert "受托方" in text


def test_a_role_word_that_is_not_a_connector_is_published_as_a_fragment():
    """角色词不在连接词表里时，裁不掉，碎片会被当成名字发布出来。

    这是一条**已知边界**（见 `references/format-rules.md`「已知局限」）：
    报告里会出现 `实施单位是华信科技有限公司` 这种读起来很荒唐的名字。
    它**不产生确定级的断言**——只到疑似级的 P0「主体串写」。

    冠名带行政区划时不暴露（`实施单位是北京华信科技有限公司` 照裁），
    冠名不带行政区划时暴露。这条边界这一波没有改（改它要动裁剪口径，
    超出本波范围），但必须写进文档，不能让读者以为角色词前缀都能还原。
    """
    assert extract_company_names("实施单位是华信科技有限公司。") == [
        "实施单位是华信科技有限公司"
    ]
    docs = [_doc("a.docx", [
        "实施单位是华信科技有限公司。",
        "华信科技有限公司的联系方式如下。",
    ])]
    issues = analyze(docs)["issues"]
    assert [i for i in issues if i["category"] == "主体名称"] == [], issues
    mixed = [i for i in issues if i["category"] == "主体串写"]
    assert len(mixed) == 1, issues
    assert mixed[0]["confidence"] == "疑似 · 需人工核实", mixed[0]


def test_the_known_limitations_record_the_role_word_that_is_not_a_connector():
    """「角色词本身不是连接词，裁不掉」这条边界必须有已知局限条目。"""
    body = _known_limitations()
    assert "角色词本身不是连接词，裁不掉" in body
    assert "实施单位是华信科技有限公司" in body


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
