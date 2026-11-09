"""主体名的实际行为，与 references/format-rules.md 写下的边界必须对得上。

**这些测试钉的是当前的（有限的）行为，不是理想行为。**
代码一旦变了，它们会失败——那正是要提醒人把文档一起改掉的时候：
文档把一条边界写错或写漏，恰恰是这个项目反复吃过亏的地方
（写错的文档比不写更坏，把 bug 写成「本来如此」是最坏的一种）。

每条测试的 docstring 里标着对应的文档位置。
"""
from analyze import check_entities
from entities import (
    _COMPLETE_SENTENCE_CONNECTORS,
    _COPULAS,
    extract_company_names,
    extract_company_occurrences,
)


def _doc(file_id, texts):
    """造一个只含段落块的文档。"""
    return {
        "file": file_id,
        "sections": [{"heading": ""}],
        "blocks": [
            {"kind": "paragraph", "index": i, "text": t, "section_path": ""}
            for i, t in enumerate(texts)
        ],
    }


# --- 角色词前面带填充词时，两家不同的公司会静默合并 ---
#
# 文档：format-rules.md「已知局限」里「角色词前面带填充词时，
# 两家不同的公司会被并成一家，而且一条 finding 都不报」那一条。


def test_filler_before_the_role_word_merges_two_companies():
    """`本项目中标为北京…` 与 `本项目中标为上海…` 合并成一个主体，且一条 finding 都不报。

    这是漏报（假阴性）。条款 (b) 要求角色词位于名字串的开头，
    「本项目中标为」不满足，于是两句都只剩 `空间科技有限公司`。
    """
    docs = [_doc("a.docx", [
        "本项目中标为北京自由空间科技有限公司。",
        "本项目中标为上海自由空间科技有限公司。",
    ])]
    issues, summary = check_entities(docs)
    assert summary["per_file"]["a.docx"] == [
        "空间科技有限公司", "空间科技有限公司",
    ]
    assert len(summary["variants"]) == 1, summary["variants"]
    assert issues == [], "文档里写混了两家公司，混主体的检查却失效了"


def test_role_word_at_the_start_of_the_run_keeps_the_two_companies_apart():
    """对照：角色词位于名字串开头时，两家公司分得开，报疑似级的 P0。"""
    docs = [_doc("a.docx", [
        "中标人为北京自由空间科技有限公司。",
        "中标人为上海自由空间科技有限公司。",
    ])]
    issues, summary = check_entities(docs)
    assert set(summary["per_file"]["a.docx"]) == {
        "北京自由空间科技有限公司", "上海自由空间科技有限公司",
    }
    assert len(summary["variants"]) == 2
    assert [i["category"] for i in issues] == ["主体串写"]
    assert issues[0]["severity"] == "P0"
    assert issues[0]["confidence"] == "疑似 · 需人工核实"


# --- 条款 (b) 的第三条守卫只检查「开头」，会还原出句子碎片 ---
#
# 文档：format-rules.md「已知局限」里「条款 (b) 的第三条守卫只检查开头，
# 会还原出句子碎片」那一条。


def test_guard_three_only_checks_the_head():
    """角色词与误切点之间那一段只要以行政区划开头就通过，不管它是不是字号的开头。"""
    occ = extract_company_occurrences("乙方为北京分公司确认自由空间科技有限公司。")
    assert occ == [(
        "空间科技有限公司",
        "北京分公司确认自由空间科技有限公司",
    )], occ


def test_a_restored_fragment_does_not_merge_with_the_real_company():
    """碎片不会被并进真字号——它只到疑似级，不产生确定级断言。"""
    docs = [_doc("a.docx", [
        "乙方为北京分公司确认自由空间科技有限公司。",
        "北京自由空间科技有限公司负责本项目。",
    ])]
    issues, summary = check_entities(docs)
    assert len(summary["variants"]) == 2, summary["variants"]
    assert [i["category"] for i in issues] == ["主体串写"]
    assert issues[0]["confidence"] == "疑似 · 需人工核实"


# --- 通用片段判定用的是裁剪后的名字，整家公司可能被丢掉 ---
#
# 文档：format-rules.md「已知局限」里「通用片段判定用的是裁剪后的名字，
# 整家公司可能被丢掉」那一条。


def test_a_company_can_be_dropped_entirely_in_prose():
    """`本项目中标为青岛自由贸易服务有限公司。` 一条名字都不发布。"""
    assert extract_company_names("本项目中标为青岛自由贸易服务有限公司。") == []
    # 对照：同一家公司作为裸字符串出现时是对的
    assert extract_company_names("青岛自由贸易服务有限公司") == [
        "青岛自由贸易服务有限公司",
    ]


def test_the_dropped_company_is_also_missing_from_the_report():
    """丢掉的不只是抽取结果，报告里的主体清单里也没有它。"""
    docs = [_doc("a.docx", ["本项目中标为青岛自由贸易服务有限公司。"])]
    issues, summary = check_entities(docs)
    assert summary["per_file"]["a.docx"] == []
    assert summary["names"] == []
    assert issues == []


# --- 系词表只有「是」「为」 ---
#
# 文档：format-rules.md「角色词后面可以跟一个系词」那一段。


def test_the_copula_set_is_shi_and_wei_only():
    assert _COPULAS == ("是", "为")


def test_a_non_listed_copula_blocks_the_restoration():
    """`中标人系…` / `中标人即…` 里的系词不在表内，条款 (b) 不成立。"""
    for text in ("中标人系北京自由空间科技有限公司。",
                 "中标人即北京自由空间科技有限公司。"):
        occ = extract_company_occurrences(text)
        assert occ == [("空间科技有限公司", "空间科技有限公司")], (text, occ)


# --- 角色词表里收着「由」，它不是角色词 ---
#
# 文档：format-rules.md「角色词表里也收了「由」」那一段。


def test_the_role_word_table_contains_you():
    assert "由" in _COMPLETE_SENTENCE_CONNECTORS


def test_you_only_fires_when_the_run_starts_with_it():
    """`本项目由…` 的名字串不是以「由」开头，条款 (b) 的这条路不进。"""
    occ = extract_company_occurrences("本项目由北京自由空间科技有限公司。")
    assert occ == [(
        "空间科技有限公司", "北京自由空间科技有限公司",
    )], occ
