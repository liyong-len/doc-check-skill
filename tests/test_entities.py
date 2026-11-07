from entities import (
    canonical_core,
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


def test_trim_skips_cut_that_leaves_too_little():
    # 「由」切出 6 字、「和」只切出 3 字（不足 4 字），跳过「和」取「由」
    assert extract_company_names("本项目由北京和兴科技有限公司编制") == [
        "北京和兴科技有限公司"
    ]


def test_trim_picks_last_qualifying_connector():
    # 候选长度随连接词右移而变短，取最短合格切分 = 取最靠后的合格连接词，
    # 这样句子碎片（甲方、乙方、委托）不会带进名字
    assert extract_company_names("由甲方及乙方共同委托北京华信科技有限公司") == [
        "北京华信科技有限公司"
    ]


def test_center_is_not_a_company_form():
    # 「中心」是普通名词不是企业形式，技术中心不该被抽成企业名
    assert extract_company_names("本项目技术中心负责实施") == []
    assert extract_company_names("数据中心有限公司") == ["数据中心有限公司"]


def test_form_fragment_guard_keeps_equal_length_names():
    # 形式词的严格前缀才是片段，长度相等的是真实字号
    assert extract_company_names("研究中心有限公司") == ["研究中心有限公司"]
    assert extract_company_names("设计院有限公司") == ["设计院有限公司"]
    # 「股份」是「股份有限公司」的严格前缀，是片段
    assert extract_company_names("中信建设集团股份有限公司") == ["中信建设集团"]


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


def test_weak_connector_characters_inside_names_are_preserved():
    assert extract_company_names("和而泰智能控制股份有限公司") == ["和而泰智能控制股份有限公司"]
    assert extract_company_names("中国联合网络通信集团有限公司") == ["中国联合网络通信集团有限公司"]
    assert extract_company_names("清华同方能源环保股份有限公司") == ["清华同方能源环保股份有限公司"]


def test_same_entity_uses_suffix_not_prefix():
    # 带连接词前缀的同一写法与干净写法同属一个主体
    assert same_entity("由北京华信科技有限公司", "北京华信科技有限公司")
    # 前缀关系会误并这两个不同主体
    assert not same_entity("中国建筑", "中国建筑科技")
    assert not same_entity("华信科技有限公司", "华信科技信息有限公司")


def test_short_form_and_full_name_are_same_entity():
    assert same_entity("北京华信", "北京华信科技有限公司")


def test_repeated_suffix_layer_is_one_entity():
    assert same_entity("中国建筑集团股份有限公司", "中国建筑集团")


def test_leading_weak_connector_only_stripped_when_long_enough():
    # 真实字号以弱连接词开头时不能被裁
    assert canonical_core("与信科技有限公司") == "与信科技"
    assert canonical_core("同创股份有限公司") == "同创"
    # 连接词后是行政区划开头时才裁
    assert canonical_core("与上海远大信息技术有限公司") == "上海远大信息技术"


def test_paren_group_is_consumed_atomically():
    # 括号里的「集团」是字号的一部分，不能当成公司词尾切开
    assert extract_company_names("北京华信(集团)有限公司") == ["北京华信(集团)有限公司"]
    assert extract_company_names("北京华信（集团）科技有限公司") == ["北京华信（集团）科技有限公司"]
    assert extract_company_names("（北京华信科技有限公司）") == ["北京华信科技有限公司"]


def test_extract_company_names_skips_split_form_word():
    # 「股份有限公司」不是主体名，是形式词被从中间切开的结果
    names = extract_company_names("中标候选人：中信建设集团股份有限公司")
    assert "股份有限公司" not in names
    assert "中信建设集团" in names


def test_group_variants_keeps_distinct_cores_apart():
    groups = group_variants(["华信科技有限公司", "华信科技信息有限公司"])
    assert len(groups) == 2


def test_group_variants_canonicals_ignore_leading_weak_connector():
    groups = group_variants(["与上海远大信息技术有限公司", "上海远大信息技术有限公司"])
    assert len(groups) == 1
    assert groups[0]["canonicals"] == ["上海远大信息技术有限公司"]


def test_canonical_core_collapses_weak_prefix():
    assert canonical_core("与上海远大信息技术有限公司") == "上海远大信息技术"
    assert canonical_core("上海远大信息技术有限公司") == "上海远大信息技术"
