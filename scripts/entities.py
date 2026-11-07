"""主体名抽取与变体聚类。

本工具不引入外部依据，主体信息全部从文档内推导。
"""
from __future__ import annotations

import re

from common import normalize_name

# 词尾（长词优先，保证先匹配到「有限责任公司」而非「有限公司」）
_SUFFIXES = [
    "股份有限公司", "有限责任公司", "集团有限公司", "有限公司",
    "集团", "研究院", "研究所", "设计院", "事务所", "工程中心", "中心",
]

# 行政区划前缀（按长度降序）
_REGIONS = [
    "内蒙古自治区", "内蒙古", "黑龙江", "新疆维吾尔自治区", "新疆", "西藏",
    "宁夏回族自治区", "宁夏", "青海", "甘肃", "陕西", "山西", "河北", "河南",
    "湖南", "湖北", "安徽", "浙江", "江苏", "山东", "江西", "福建", "广东",
    "海南", "四川", "贵州", "云南", "辽宁", "吉林", "北京", "上海", "天津",
    "重庆", "台湾", "香港", "澳门",
]

# 连接词：用于把「本项目由北京华信科技有限公司」中的前缀裁掉
_CONNECTORS = [
    "以及", "并且", "联合", "协作", "采购方", "招标人", "招标代理", "甲方", "乙方",
    "受托", "委托", "由", "是", "与", "和", "及", "向", "为", "对", "给", "经", "从",
    "同", "并", "或",
]

_NAME_RE = re.compile(
    r"(?P<pre>[一-龥A-Za-z0-9·]{2,30}?)"
    r"(?P<suf>股份有限公司|有限责任公司|集团有限公司|有限公司|集团|研究院|研究所|设计院|事务所|工程中心|中心)"
)


def _is_form_fragment(prefix: str) -> bool:
    """字号是否只是公司形式词的一段（如「股份」「有限」「责任」）。

    正则的非贪婪匹配可能把形式词从中间切开，例如
    「中信建设集团股份有限公司」会先切出「中信建设集团」，余下「股份有限公司」
    又被当作一个名称切出「股份」+「有限公司」。这样的字号不是真实主体名。
    """
    for s in _SUFFIXES:
        if 2 <= len(prefix) <= len(s) and s.startswith(prefix):
            return True
    return False


def _trim_prefix(prefix: str) -> str:
    """切掉前缀中的最后一个连接词，取其后的部分作为字号主体。"""
    cut = -1
    for conn in _CONNECTORS:
        idx = prefix.rfind(conn)
        if idx >= 0:
            cut = max(cut, idx + len(conn))
    if cut >= 0:
        prefix = prefix[cut:]
    return prefix.strip()


def extract_company_names(text: str) -> list[str]:
    """抽取公司类名称，按出现顺序去重。"""
    out: list[str] = []
    seen: set[str] = set()
    for m in _NAME_RE.finditer(text or ""):
        prefix = _trim_prefix(m.group("pre"))
        if len(prefix) < 2:
            continue
        if _is_form_fragment(prefix):
            continue
        name = prefix + m.group("suf")
        key = normalize_name(name)
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def _strip_suffix(name: str) -> str:
    for s in _SUFFIXES:
        if name.endswith(s):
            return name[: -len(s)]
    return name


def _strip_region(name: str) -> str:
    for r in _REGIONS:
        if name.startswith(r):
            return name[len(r):]
    return name


def core_key(name: str) -> str:
    """核心字号：去掉公司词尾与行政区划前缀后的剩余部分。

    刻意不剥离行业词。行业词参与主体区分：
    「华信科技」与「华信信息技术」是两个不同主体，剥掉行业词会把它们混为一谈。
    """
    n = normalize_name(name)
    n = _strip_suffix(n)
    n = _strip_region(n)
    return n


def same_entity(a: str, b: str) -> bool:
    """两个名称是否指向同一主体。"""
    ca, cb = core_key(a), core_key(b)
    if not ca or not cb:
        return False
    if ca == cb:
        return True
    shorter, longer = sorted([ca, cb], key=len)
    # 简称下限为 2 个汉字：「北京华信」的核心字号是「华信」，应与「北京华信科技
    # 有限公司」判为同一主体。下限再低会命中「北京」这类纯行政区划（其核心字号
    # 为空，已在上一步排除）。
    if len(shorter) >= 2 and longer.startswith(shorter):
        return True
    return False


def group_variants(names: list[str]) -> list[dict]:
    """按核心字号聚类。返回 [{core, names}]，names 按首次出现排序。"""
    groups: list[dict] = []
    for name in names:
        placed = False
        for g in groups:
            if same_entity(name, g["names"][0]):
                g["names"].append(name)
                placed = True
                break
        if not placed:
            groups.append({"core": core_key(name), "names": [name]})
    return groups
