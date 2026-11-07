from entities import (
    core_key,
    extract_company_names,
    group_variants,
    same_entity,
)


def test_extract_company_names_basic():
    text = "本项目由北京华信科技有限公司负责，联合北京华信科技有限责任公司协作。"
    names = extract_company_names(text)
    assert "北京华信科技有限公司" in names
    assert "北京华信科技有限责任公司" in names


def test_extract_company_names_ignores_plain_text():
    assert extract_company_names("这是一段普通说明文字。") == []


def test_connector_inside_company_name_is_not_trimmed():
    # 「为」「和」也是字号的一部分，不能把「华为技术」裁成「技术」
    assert extract_company_names("华为技术有限公司") == ["华为技术有限公司"]
    assert extract_company_names("北京和信科技有限公司") == ["北京和信科技有限公司"]


def test_trim_picks_longest_qualifying_cut():
    # 「由」切出 6 字、「和」只切出 3 字，取更长的那个
    assert extract_company_names("本项目由北京和兴科技有限公司编制") == [
        "北京和兴科技有限公司"
    ]


def test_extract_company_names_skips_split_form_word():
    # 「股份有限公司」不是主体名，是形式词被从中间切开的结果
    names = extract_company_names("中标候选人：中信建设集团股份有限公司")
    assert "股份有限公司" not in names
    assert "中信建设集团" in names


def test_core_key_strips_suffix_and_region():
    assert core_key("北京华信科技有限公司") == "华信科技"
    assert core_key("华信科技有限公司") == "华信科技"


def test_core_key_keeps_industry_word():
    # 行业词参与主体区分，不剥离
    assert core_key("华信信息科技有限公司") == "华信信息科技"
    assert core_key("北京华信科技有限公司") != core_key("北京华信信息技术有限公司")


def test_same_entity_detects_prefix_short_form():
    assert same_entity("北京华信科技有限公司", "北京华信")


def test_same_entity_rejects_different_companies():
    assert not same_entity("北京华信科技有限公司", "上海远大信息技术有限公司")


def test_group_variants_clusters_by_core():
    names = ["北京华信科技有限公司", "北京华信科技有限责任公司", "上海远大信息技术有限公司"]
    groups = group_variants(names)
    sizes = sorted(len(g["names"]) for g in groups)
    assert sizes == [1, 2]
    two = next(g for g in groups if len(g["names"]) == 2)
    assert set(two["names"]) == {"北京华信科技有限公司", "北京华信科技有限责任公司"}
