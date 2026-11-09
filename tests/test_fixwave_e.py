"""修复波 E 的回归测试：国家前缀与文档口径。

覆盖：
- C-a 「中国」前缀的公司与它的无前缀对应公司被并成一家
      （集团公司与子公司是两家不同的公司，不能并成一家）
- I-a / I-b 已知局限与规则文档的措辞必须与代码的实际行为一致
- 「中标人为XX公司」这一类抽出来的名字带一个「为」（已知局限，本波只记录不修）
- M-b / M-c / M-d 几处注释与数据文件的小毛病
"""
from __future__ import annotations

from pathlib import Path

from analyze import analyze
from entities import extract_company_names, group_variants, same_entity

ROOT = Path(__file__).resolve().parent.parent
FORMAT_RULES = ROOT / "references" / "format-rules.md"


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


# --- C-a：国家前缀与行政区划前缀一样是区分标志 ---


def test_a_country_prefix_blocks_the_merge():
    """「中国」前缀的公司与它的无前缀对应公司是两家不同的公司。

    「中国联合网络通信集团有限公司」是集团公司，「联合网络通信有限公司」
    是它的子公司。把它们并成一家，报出来的就是一条「统一名称写法」的
    确定级建议——让用户去统一两家公司的名字。
    """
    assert not same_entity(
        "中国联合网络通信集团有限公司", "联合网络通信有限公司")
    assert not same_entity(
        "中国石油化工集团有限公司", "石油化工有限公司")
    assert not same_entity(
        "中国移动通信集团有限公司", "移动通信有限公司")


def test_the_country_prefix_does_not_swallow_the_existing_distinctions():
    """既有的判定一条都不能被带偏。"""
    # 「中国建筑」不是「中国建筑科技」的简称（国家前缀不是行政区划）
    assert not same_entity("中国建筑", "中国建筑科技")
    # 句子级连接词仍然可以并
    assert same_entity("北京华信科技有限公司", "由北京华信科技有限公司")
    # 字号级连接词仍然分得开
    assert not same_entity("联合网络通信有限公司", "网络通信有限公司")


def test_the_parent_group_and_its_counterpart_land_in_two_groups():
    """归组结果必须与 same_entity 一致：两组，不是一组。"""
    groups = group_variants([
        "中国联合网络通信集团有限公司", "联合网络通信有限公司",
    ])
    assert len(groups) == 2, groups
    names = {n for g in groups for n in g["names"]}
    assert names == {"中国联合网络通信集团有限公司", "联合网络通信有限公司"}


def test_a_parent_group_and_its_counterpart_produce_a_p0_not_a_p1():
    """母公司与子公司同时出现：报 P0 主体串写，不报 P1 主体名称。

    修复前这两家被并成一家，P0 被吞掉，还多出一条确定级的
    「同一主体出现 2 种名称写法」——那是最坏的一种假问题。
    """
    docs = [_doc("中国联合网络通信集团有限公司投标文件.docx", [
        "本项目由中国联合网络通信集团有限公司负责实施。",
        "联合网络通信有限公司负责本地交付。",
    ])]
    issues = analyze(docs)["issues"]

    mixed = [i for i in issues if i["category"] == "主体串写"]
    assert len(mixed) == 1, issues
    assert mixed[0]["severity"] == "P0"
    assert mixed[0]["confidence"] == "疑似 · 需人工核实"

    assert [i for i in issues if i["category"] == "主体名称"] == [], issues


def test_the_subject_count_is_not_undercounted():
    """主体数不能少算。

    修复前母子公司被并成一家，四份主体只报出三个。
    """
    docs = [_doc("中国联合网络通信集团有限公司投标文件.docx", [
        "本项目由中国联合网络通信集团有限公司负责实施。",
        "联合网络通信有限公司负责本地交付。",
        "北京华信科技有限公司提供设备。",
        "上海华信科技有限公司提供施工。",
    ])]
    issues = analyze(docs)["issues"]

    mixed = [i for i in issues if i["category"] == "主体串写"]
    assert len(mixed) == 1, issues
    assert "该文件出现 4 个不同主体" in mixed[0]["description"], \
        mixed[0]["description"]
    assert [i for i in issues if i["category"] == "主体名称"] == [], issues


def test_a_parent_group_and_its_counterpart_in_a_real_docx(tmp_path):
    """真实 .docx 端到端：文件名点明母公司时，子公司仍要报出来。

    文件名提到甲公司，只说明甲公司被显式区分了，文件里的乙公司仍然
    没有任何依据，仍要报。
    """
    import json
    import docx
    from prepare import prepare

    path = tmp_path / "中国联合网络通信集团有限公司投标文件.docx"
    document = docx.Document()
    document.add_paragraph("本项目由中国联合网络通信集团有限公司负责实施。")
    document.add_paragraph("联合网络通信有限公司负责本地交付。")
    document.save(str(path))

    work = tmp_path / "work"
    prepare([path], "standard", work)
    consistency = json.loads(
        (work / "consistency.json").read_text(encoding="utf-8"))
    issues = consistency["issues"]

    cats = {i["category"] for i in issues}
    assert "主体串写" in cats, issues
    assert "主体名称" not in cats, issues

    mixed = next(i for i in issues if i["category"] == "主体串写")
    assert mixed["severity"] == "P0"
    assert mixed["confidence"] == "疑似 · 需人工核实"
    assert "联合网络通信有限公司" in mixed["description"]


# --- 已知局限：连接词裁剪的残余代价 ---


def test_a_region_head_keeps_the_字号_whole():
    """头部是行政区划时，句子级连接词不裁。

    这一条是 C-a 的修复带来的，一直没变。修复波 F 把**国家前缀**那条
    收窄成「只有完整字号才挡裁剪」之后（「中国自由贸易港城」里连接词
    前面的头部「中国自」是一个开放从句，不是字号），行政区划这条仍然原样。
    「中国自由贸易港城有限公司」现在会被裁成「贸易港城有限公司」——
    那是修复波 F 记录在案的已知局限，见 tests/test_fixwave_f.py。
    """
    assert extract_company_names("海南自由贸易港城有限公司") == [
        "海南自由贸易港城有限公司"
    ]


def test_the_residual_cost_of_the_connector_rule_is_still_there():
    """头部既不是行政区划也不是国家前缀时，句子级连接词照样被裁。

    这是已知局限里写的那一条，代码没有改，文档必须与代码一致。
    """
    assert extract_company_names("北方自由贸易港城有限公司") == [
        "贸易港城有限公司"
    ]
    assert extract_company_names("华夏自由贸易港城有限公司") == [
        "贸易港城有限公司"
    ]


# --- 已知局限：「中标人为XX公司」这一类 ---


def test_the_is_a_company_writing_is_still_there():
    """句子级连接词后面跟「为」时，抽出来的名字带一个「为」。

    这是已知局限里写的那一类，本波**不修**，但文档必须与代码一致。
    """
    assert extract_company_names("中标人为华为技术有限公司") == [
        "为华为技术有限公司"
    ]
    assert extract_company_names("甲方为北方国际股份有限公司") == [
        "为北方国际股份有限公司"
    ]
    assert extract_company_names("供应商为长江有限责任公司") == [
        "供应商为长江有限责任公司"
    ]
    assert extract_company_names("本项目业主为铁建工程有限公司") == [
        "本项目业主为铁建工程有限公司"
    ]


def test_the_is_a_company_writing_stays_at_the_suspected_level():
    """这一类不产生确定级断言：它只到 P0「主体串写」，且是疑似。"""
    docs = [_doc("a.docx", [
        "中标人为华为技术有限公司。",
        "华为技术有限公司负责供货。",
    ])]
    issues = analyze(docs)["issues"]

    for issue in issues:
        if issue["category"] == "主体名称":
            assert issue["confidence"] == "确定", issue
        if issue["category"] == "主体串写":
            assert issue["confidence"] == "疑似 · 需人工核实", issue
    # 文档里逐字存在的字符串：没有凭空造出的名字
    names = {n["name"] for n in analyze(docs)["entities"]["names"]}
    assert "为华为技术有限公司" in names


# --- 规则文档必须与代码一致 ---


def test_the_format_rules_state_the_region_head_rule():
    """「连接词前面是行政区划时不裁」这条必须写进文档。

    这是 C-3 的修复。文档里没有它，维护者照文档写新规则就会把 C-3  undo。
    """
    text = _format_rules()
    assert "海南自由贸易港城" in text
    assert "以**行政区划**开头" in text


def test_the_format_rules_state_the_country_prefix_rule():
    """国家前缀单列一张表，两处都检查。"""
    text = _format_rules()
    assert "_COUNTRY_PREFIXES" in text
    assert "国家前缀" in text
    # 「中国」不在行政区划表里，这句话要写清楚
    assert "名单里没有「中国」" in text


def test_the_known_limitations_state_the_country_prefix_cost():
    """已知局限里必须有国家前缀这一条，且写的是代码的实际行为。"""
    body = _known_limitations()
    assert "国家前缀" in body
    assert "北方自由贸易港城有限公司" in body
    assert "中国自由贸易港城有限公司" in body


def test_the_known_limitations_state_the_is_a_company_cost():
    """已知局限里必须有「X为YY公司」这一条，且写的是代码的实际行为。"""
    body = _known_limitations()
    assert "为华为技术有限公司" in body
    assert "链式裁剪" in body
    assert "本版未实现" in body


def test_the_format_rules_say_core_key_is_only_kept_for_tests():
    """core_key 在流水线里没有调用点，文档不能说它是「展示用」。"""
    assert "只为测试保留" in _format_rules()


# --- M-b / M-c / M-d ---


def test_the_categories_docstring_points_at_the_right_test():
    """categories.py 的注释要指向真正做对照的那个测试文件。"""
    text = (ROOT / "scripts" / "categories.py").read_text(encoding="utf-8")
    assert "test_fixwave_d_findings.py" in text
    assert "test_the_category_list_matches_the_reference_documents" in text
    assert "tests/test_references.py" not in text


def test_core_key_has_no_caller_in_the_pipeline():
    """core_key 只为测试保留：scripts/ 里没有任何地方调用它。"""
    import entities

    assert "只为测试保留" in entities.core_key.__doc__
    scripts_dir = Path(entities.__file__).resolve().parent
    callers = [
        path.name for path in sorted(scripts_dir.rglob("*.py"))
        if path.name != "entities.py"
        and "core_key" in path.read_text(encoding="utf-8")
    ]
    assert callers == [], callers


def test_the_region_list_has_no_duplicate_names():
    """行政区划名单里每个地名只出现一次。"""
    import entities

    data = Path(entities.__file__).resolve().parent / "data" / "regions.txt"
    names = []
    for line in data.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.append(line)
    duplicates = {n for n in names if names.count(n) > 1}
    assert duplicates == set(), duplicates
    # 去重之后名单仍然是原来那份（不能因为去重少掉了哪个地名）
    assert "吉林" in names and "海南" in names
    assert "海南藏族自治州" in names
