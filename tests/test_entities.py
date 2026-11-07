from entities import (
    canonical_core,
    canonical_name,
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
    # 「股份」是「股份有限公司」的严格前缀，是片段：不会单独抽出一个
    # 叫「股份有限公司」的主体（名字整体延伸到「股份有限公司」）
    names = extract_company_names("中信建设集团股份有限公司")
    assert "股份有限公司" not in names
    assert names == ["中信建设集团股份有限公司"]


def test_bare_form_word_is_not_a_company_name():
    # 字号本身就是形式词时，这是通用片段不是公司名。
    # 「设计院有限公司」「研究院有限公司」都不是公司名，真实的公司名
    # 字号更长时不受影响
    assert extract_company_names("中国建筑设计院有限公司") == ["中国建筑设计院有限公司"]
    assert extract_company_names("设计院有限公司") == []
    assert extract_company_names("研究院有限公司") == []
    assert extract_company_names("事务所有限公司") == []


def test_generic_industry_fragment_is_not_a_company_name():
    # 字号剥掉行政区划后只剩行业词，是通用片段
    assert extract_company_names("工程咨询有限公司") == []
    assert extract_company_names("北京工程有限公司") == []
    # 字号里还有实义词就不是片段
    assert extract_company_names("华信工程咨询有限公司") == ["华信工程咨询有限公司"]


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


def test_org_form_suffix_is_not_stripped():
    # 研究院/设计院不是企业形式，剥掉会把不同主体并到一起
    assert canonical_core("中国建筑设计院有限公司") == "中国建筑设计院"
    assert canonical_core("中国建筑设计院") == "中国建筑设计院"
    assert canonical_core("中国建筑有限公司") == "中国建筑"


def test_organization_connectors_are_not_stripped_from_canonical():
    # 同/和/联合/协作在字号里太常见，不能剥
    assert canonical_core("联合网络通信有限公司") == "联合网络通信"
    assert canonical_core("和信科技有限公司") == "和信科技"
    assert canonical_core("同创股份有限公司") == "同创"


def test_extract_company_names_skips_split_form_word():
    # 「股份有限公司」不会单独成为一个主体名
    names = extract_company_names("中标候选人：中信建设集团股份有限公司")
    assert "股份有限公司" not in names
    assert names == ["中信建设集团股份有限公司"]


def test_weak_prefixed_core_is_not_merged_by_suffix_relation():
    # 多出来的「联合」是字号的一部分，不是句子碎片
    assert not same_entity("联合网络通信有限公司", "网络通信有限公司")
    assert not same_entity("和信科技有限公司", "信科技有限公司")


def test_strong_prefixed_core_is_still_merged():
    assert same_entity("由北京华信科技有限公司", "北京华信科技有限公司")


def test_name_extends_over_a_following_form_word():
    assert extract_company_names("中国建筑设计院有限公司") == ["中国建筑设计院有限公司"]
    assert extract_company_names("中信建设集团股份有限公司") == ["中信建设集团股份有限公司"]


def test_leading_annotation_parens_are_not_part_of_the_name():
    # 注解与编号括号不是字号的一部分
    assert extract_company_names("（招标人）北京华信科技有限公司") == ["北京华信科技有限公司"]
    assert extract_company_names("（1）北京华信科技有限公司") == ["北京华信科技有限公司"]


def test_agent_word_inside_a_company_name_is_not_a_connector():
    # 「代理记账」「代理财务」里的「代理」是字号的一部分
    assert extract_company_names("深圳市代理记账服务有限公司") == ["深圳市代理记账服务有限公司"]
    assert extract_company_names("深圳代理财务咨询有限公司") == ["深圳代理财务咨询有限公司"]


def test_canonical_name_normalizes_width_and_whitespace():
    assert canonical_name("北京华信（集团）有限公司") == canonical_name("北京华信(集团)有限公司")
    assert canonical_name("北京 华信科技有限公司") == "北京华信科技有限公司"


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


# --- 复查轮次：主体抽取与聚类的 Critical 缺陷 ---

def test_name_is_not_split_at_an_inner_form_word():
    # 「研究院」在名字中间，它是字号的一部分。
    # 延伸过去的尾巴若被重新匹配一次，就会多出半个公司名。
    assert extract_company_names("北京华信集团研究院有限公司") == [
        "北京华信集团研究院有限公司"
    ]
    assert extract_company_names("中铁建工集团北京工程有限公司") == [
        "中铁建工集团北京工程有限公司"
    ]
    assert extract_company_names("华夏集团工程咨询有限公司") == [
        "华夏集团工程咨询有限公司"
    ]


def test_two_names_in_one_run_are_not_merged():
    # 两个字之间有连接词，是两个主体，不能延伸成一个名字
    assert extract_company_names(
        "北京华信科技有限公司和上海远大信息技术有限公司联合实施"
    ) == ["北京华信科技有限公司", "上海远大信息技术有限公司"]


def test_industry_variant_is_a_different_company():
    # 经营范围不同的两家公司，不能因为一个以行业词结尾就并成一家
    assert not same_entity("北京华信科技有限公司", "北京华信科技服务有限公司")
    assert not same_entity("北京华信科技有限公司", "北京华信科技发展有限公司")
    # 真·简称仍然合并
    assert same_entity("北京华信科技有限公司", "北京华信")
    # 行业词开头的「中国建筑」不是「中国建筑科技」的简称
    assert not same_entity("中国建筑", "中国建筑科技")


def test_group_variants_partition_is_order_independent():
    # 同样的名字集合，顺序不同不能得出不同的分组
    import itertools

    names = [
        "北京华信科技有限公司",
        "北京华信科技服务有限公司",
        "北京华信科技发展有限公司",
    ]
    partitions = set()
    for perm in itertools.permutations(names):
        groups = group_variants(list(perm))
        partitions.add(frozenset(frozenset(g["names"]) for g in groups))
    assert len(partitions) == 1, "聚类结果随输入顺序变化"
    groups = group_variants(names)
    assert len(groups) == 3
    for g in groups:
        assert len(g["names"]) == 1


def test_agent_word_is_a_weak_connector():
    # 「代理」是字号的一部分（「深圳市代理记账服务有限公司」），
    # 但句子层面的「代理」后面跟的是主体，要裁掉
    assert extract_company_names("深圳市代理记账服务有限公司") == [
        "深圳市代理记账服务有限公司"
    ]
    assert extract_company_names("我方代理北京华信科技有限公司") == [
        "北京华信科技有限公司"
    ]


def test_annotation_bracket_content_is_not_a_second_entity():
    # 注解括号里的「华信集团」不是主体，不能当成第二个主体名
    assert extract_company_names("（华信集团）北京华信科技有限公司") == [
        "北京华信科技有限公司"
    ]
