"""修复波 D 的回归测试。

覆盖：
- C-1 连接词开头的字号被吃掉（第二个公司名的位置）
- C-2 行政区划前缀被当成后缀差异，两家公司被并成一家
- C-3 句子级连接词出现在字号中间，把名字劈开
- I-1 地级市不全，弱连接词裁不掉
"""
from __future__ import annotations

from analyze import analyze
from entities import (
    canonical_core,
    extract_company_names,
    same_entity,
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


# --- C-1：连接词开头的字号在第二个公司名的位置上也必须整体保留 ---


def test_connector_started_字号_survives_in_the_second_name_position():
    """「和而泰」是字号的一部分，不能被吃掉。

    连接词在**名字的开头**时是字号的一部分，在**两个公司之间**时是分隔符。
    这两件事靠位置区分。修复前，第二个公司名前面的连接词被当成分隔符
    吃掉，抽出一个并不存在的「而泰智能控制股份有限公司」，
    真正的「和而泰智能控制股份有限公司」反而不见了。
    """
    names = extract_company_names(
        "北京华信科技有限公司和而泰智能控制股份有限公司"
    )
    assert names == ["北京华信科技有限公司", "和而泰智能控制股份有限公司"]


def test_two_companies_are_not_merged_into_one_name():
    """两个字号的第二个公司不能与第一个公司并成一个名字。"""
    names = extract_company_names(
        "甲有限公司和而泰智能控制股份有限公司"
    )
    assert names == ["甲有限公司", "和而泰智能控制股份有限公司"]


def test_connector_started_字号_reads_the_same_alone_and_after_another_company():
    """同一个名字单独出现与跟在另一家公司后面时，读法必须一致。

    「和而泰智能控制股份有限公司」单独出现时整体保留，
    跟在另一家公司后面时也必须整体保留。
    """
    alone = extract_company_names("和而泰智能控制股份有限公司")
    paired = extract_company_names(
        "北京华信科技有限公司和而泰智能控制股份有限公司"
    )
    assert alone == ["和而泰智能控制股份有限公司"]
    assert paired[-1] == alone[0]


def test_a_connector_before_a_region_is_still_a_separator():
    """连接词后面是行政区划时，它仍然是分隔符。"""
    names = extract_company_names(
        "北京华信科技有限公司和深圳远大信息技术有限公司"
    )
    assert names == ["北京华信科技有限公司", "深圳远大信息技术有限公司"]


def test_standalone_and_paired_readings_of_a_connector_agree():
    """「和华为技术有限公司」单独与成对出现时读法一致。

    「和」在两个公司之间与在字号开头，结构上分不开：
    「北京华信科技有限公司**和**华为技术有限公司」里的「和」与
    「北京华信科技有限公司**和**而泰智能控制股份有限公司」里的「和」
    位置完全一样。脚本只有一条规则，因此两处读法必须一致。
    """
    alone = extract_company_names("和华为技术有限公司")
    paired = extract_company_names(
        "北京华信科技有限公司和华为技术有限公司"
    )
    assert alone == ["和华为技术有限公司"]
    assert paired[-1] == alone[0]


# --- C-2：行政区划前缀不能被当成句子碎片 ---


def test_a_region_prefix_blocks_the_merge():
    """「上海华为技术有限公司」与「华为技术有限公司」是两家不同的公司。"""
    assert not same_entity("华为技术有限公司", "上海华为技术有限公司")
    assert not same_entity("中兴通讯股份有限公司", "深圳市中兴通讯股份有限公司")


def test_region_prefix_in_the_head_is_not_a_particle():
    """多出来的那部分是行政区划时，不能算同一主体。"""
    assert not same_entity("北京华信科技有限公司", "上海北京华信科技有限公司")


def test_sentence_particles_still_merge():
    """「由」与「联合」的行为不受影响。"""
    # 「由北京华信科技」与「北京华信科技」是同一主体
    assert same_entity("由北京华信科技有限公司", "北京华信科技有限公司")
    # 「联合网络通信」与「网络通信」不是同一主体
    assert not same_entity("联合网络通信有限公司", "网络通信有限公司")


def test_two_different_companies_are_not_merged_end_to_end():
    """端到端：两家不同的公司不能被并成一个主体。

    修复前这两句会被判成「同一主体出现 2 种名称写法」，
    并给出确定级的建议「统一为正式全称「华为技术有限公司」」——
    让用户去统一两家不同公司的名字。
    """
    docs = [_doc("a.docx", [
        "本文件由华为技术有限公司编制。",
        "上海华为技术有限公司负责本地实施。",
    ])]
    result = analyze(docs)
    issues = result["issues"]
    # P0 混主体必须还在
    mixed = [i for i in issues if i["category"] == "主体串写"]
    assert len(mixed) == 1, issues
    assert mixed[0]["severity"] == "P0"
    assert mixed[0]["confidence"] == "疑似 · 需人工核实"
    # 不得有「写法不统一」的确定级结论
    assert [i for i in issues if i["category"] == "主体名称"] == []
    names = {n["name"] for n in result["entities"]["names"]}
    assert "华为技术有限公司" in names
    assert "上海华为技术有限公司" in names


# --- C-3：句子级连接词出现在字号中间 ---


def test_a_strong_connector_inside_a_字号_does_not_cut_the_name():
    """「自由」里的「由」是字号的一部分，不能把名字劈开。"""
    assert extract_company_names("海南自由贸易港城有限公司") == [
        "海南自由贸易港城有限公司"
    ]
    assert extract_company_names("自由贸易港城有限公司") == [
        "自由贸易港城有限公司"
    ]


def test_a_strong_connector_before_a_region_is_still_cut():
    """「由北京华信科技」里的「由」仍然要裁掉。"""
    assert extract_company_names("由北京华信科技有限公司") == [
        "北京华信科技有限公司"
    ]
    assert extract_company_names("本项目由北京华信科技有限公司负责") == [
        "北京华信科技有限公司"
    ]


def test_a_strong_connector_in_sentence_context_is_still_cut():
    """「本文件由华为技术有限公司」里的「由」是句子成分，要裁掉。

    「由」前面是句子碎片（「本文件」）时它是分隔符；
    「由」前面只有一个字（「自由」）时它与那个字同属字号。
    """
    assert extract_company_names("本文件由华为技术有限公司编制。") == [
        "华为技术有限公司"
    ]


def test_two_different_companies_in_a_real_docx_are_not_merged(tmp_path):
    """真实 .docx 端到端：两家不同的公司不能被并成一个主体。

    修复前这份文档报出的是「同一主体出现 2 种名称写法」，
    并且建议「统一为正式全称「华为技术有限公司」」——
    P0 混主体被吞掉，还多了一条确定级的假问题。
    """
    import json
    import docx
    from prepare import prepare

    path = tmp_path / "a.docx"
    document = docx.Document()
    document.add_paragraph("本文件由华为技术有限公司编制。")
    document.add_paragraph("上海华为技术有限公司负责本地实施。")
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
    assert "华为技术有限公司" in mixed["description"]


# --- I-1：地级市必须齐全 ---


def test_prefecture_cities_are_regions():
    """省级之外，地级市一个都不能少。"""
    for city in ["广州", "梅州", "沈阳", "长春", "哈尔滨", "西宁", "遵义",
                 "大理", "嘉峪关", "吐鲁番", "喀什", "延边", "凉山"]:
        assert canonical_core(f"{city}华信科技有限公司") == f"{city}华信科技", city


def test_a_weak_connector_before_a_prefecture_city_is_cut():
    """少一个城市就会多抽出一个并不存在的公司名。"""
    assert extract_company_names("中标人：和广州华信科技有限公司") == [
        "广州华信科技有限公司"
    ]
    assert extract_company_names("中标人：和深圳华信科技有限公司") == [
        "深圳华信科技有限公司"
    ]


def test_the_region_list_is_a_data_file():
    """行政区划名单放在数据文件里，不写在代码里。"""
    from pathlib import Path
    import entities
    data = Path(entities.__file__).resolve().parent / "data" / "regions.txt"
    assert data.exists(), "行政区划数据文件不见了"
    text = data.read_text(encoding="utf-8")
    for city in ["广州", "梅州", "沈阳", "长春", "哈尔滨"]:
        assert city in text, city


