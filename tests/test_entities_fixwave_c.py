"""修复波 C 的回归测试：主体名的抽取与聚类。

覆盖：
- C-1 名字延伸跨过连接词，把两家公司并成一个名字
- C-2 通用片段规则把真实存在的公司名丢掉
- I-3  裸字号与多个公司共用前缀时，把两家公司并成一组
- 行政区划补齐地级市（简称规则与通用片段规则对城市一视同仁）
"""
from entities import (
    canonical_core,
    core_key,
    extract_company_names,
    group_variants,
    same_entity,
)


# --- C-1：延伸不能跨过两个主体之间的连接词 ---


def test_two_companies_joined_by_he_stay_separate():
    """「和」后面是另一个公司时，名字不能延伸过去。

    延伸过去会得到一个并不存在的公司名「北京华信科技有限公司和华为技术有限公司」，
    两个真正的公司反而不见了。
    """
    names = extract_company_names(
        "本项目由北京华信科技有限公司和华为技术有限公司联合承担。"
    )
    assert names == ["北京华信科技有限公司", "和华为技术有限公司"]


def test_two_companies_joined_by_yu_stay_separate():
    names = extract_company_names(
        "本项目由北京华信科技有限公司与上海远大信息技术有限公司联合承担。"
    )
    assert names == ["北京华信科技有限公司", "上海远大信息技术有限公司"]


def test_two_companies_joined_by_he_are_not_invented_as_one():
    """不能凭空造出一个并合出来的公司名。"""
    names = extract_company_names(
        "本项目由北京华信科技有限公司和华为技术有限公司联合承担。"
    )
    assert "北京华信科技有限公司和华为技术有限公司" not in names
    assert len(names) == 2, names


def test_connector_inside_a_company_name_keeps_one_name():
    """「和」「联合」「同」也是字号的一部分，不能当成两个主体。"""
    assert extract_company_names("和而泰智能控制股份有限公司") == [
        "和而泰智能控制股份有限公司"
    ]
    assert extract_company_names("中国联合网络通信集团有限公司") == [
        "中国联合网络通信集团有限公司"
    ]
    assert extract_company_names("清华同方科技股份有限公司") == [
        "清华同方科技股份有限公司"
    ]


def test_plain_company_names_are_unchanged():
    assert extract_company_names("北京华信科技有限公司") == ["北京华信科技有限公司"]
    assert extract_company_names("华为技术有限公司") == ["华为技术有限公司"]


def test_name_still_extends_over_an_inner_form_word():
    """名字里自带形式词时，延伸照旧（《华夏集团工程咨询有限公司》）。"""
    assert extract_company_names("华夏集团工程咨询有限公司") == [
        "华夏集团工程咨询有限公司"
    ]
    assert extract_company_names("中铁建工集团北京工程有限公司") == [
        "中铁建工集团北京工程有限公司"
    ]


def test_group_after_the_boundary_is_split_in_two():
    """集团 + 连接词 + 另一个公司：三个字都在，边界也要认。"""
    names = extract_company_names("北京华信集团有限公司和华为技术有限公司")
    assert names == ["北京华信集团有限公司", "和华为技术有限公司"]


# --- C-2：通用片段不能把真实公司名丢掉 ---


# 这些都是注册过的普通公司名。字号本身就是行业词，不是「通用片段」。
REAL_COMPANY_NAMES = [
    "北京工程咨询有限公司",
    "北京科技发展有限公司",
    "北京贸易有限公司",
    "北京投资有限公司",
    "北京信息技术有限公司",
    "北京网络科技有限公司",
    "北京建设工程有限公司",
    "北京建设集团有限公司",
]


def test_real_company_names_are_extracted():
    for name in REAL_COMPANY_NAMES:
        assert extract_company_names(name) == [name], name


def test_form_word_only_name_is_not_extracted():
    """字号整个就是形式词、没有任何自己的字：不是公司名。"""
    assert extract_company_names("研究院有限公司") == []
    assert extract_company_names("设计院有限公司") == []


def test_industry_only_name_without_region_is_not_extracted():
    """没有字号、只有行业词的名字不是任何一家公司的名字。"""
    assert extract_company_names("工程咨询有限公司") == []


def test_real_company_name_is_not_swallowed_by_a_generic_one():
    """抽出真实公司名之后，文档里就不止一个主体，混主体检查才不会被吞掉。"""
    names = extract_company_names(
        "本项目由北京工程咨询有限公司编制，上海远大信息技术有限公司协作。"
    )
    assert "北京工程咨询有限公司" in names
    assert "上海远大信息技术有限公司" in names


# --- I-3：裸字号只有在不歧义时才是简称 ---


def test_bare_字号_is_a_short_form_when_unambiguous():
    groups = group_variants(["北京华信", "北京华信科技有限公司"])
    assert len(groups) == 1


def test_parent_group_and_tech_subsidiary_are_two_groups():
    """母公司与科技子公司是两家不同的公司，不能并成一组。"""
    groups = group_variants(["北京华信集团有限公司", "北京华信科技有限公司"])
    assert len(groups) == 2
    assert {g["names"][0] for g in groups} == {
        "北京华信集团有限公司", "北京华信科技有限公司",
    }


def test_ambiguous_bare_字号_merges_with_nothing():
    """裸字号指向哪一家没有依据时，它谁也不代表，也不报写法不统一。"""
    groups = group_variants([
        "北京华信", "北京华信集团有限公司", "北京华信科技有限公司",
    ])
    assert len(groups) == 3
    for g in groups:
        assert len(g["canonicals"]) == 1, "歧义的裸字号不能产生写法不统一的结论"


def test_two_full_names_with_a_shared_prefix_are_not_merged():
    assert not same_entity("北京华信集团有限公司", "北京华信科技有限公司")


def test_short_form_pair_is_still_the_same_entity():
    assert same_entity("北京华信科技有限公司", "北京华信")


# --- 行政区划：地级市与直辖市一视同仁 ---


def test_prefecture_city_is_a_region():
    assert canonical_core("深圳工程咨询有限公司") == "深圳工程咨询"
    assert core_key("深圳工程咨询有限公司") == "工程咨询"


def test_prefecture_city_short_form_is_recognised():
    """「深圳华信」与「北京华信」一样是简称，不能只认直辖市。"""
    assert same_entity("深圳华信科技有限公司", "深圳华信")


def test_city_prefixed_industry_name_is_extracted():
    for name in [
        "深圳工程咨询有限公司",
        "广州贸易有限公司",
        "厦门网络科技有限公司",
        "青岛建设工程有限公司",
        "苏州科技发展有限公司",
    ]:
        assert extract_company_names(name) == [name], name
