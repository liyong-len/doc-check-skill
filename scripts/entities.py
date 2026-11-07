"""主体名抽取与变体聚类。

本工具不引入外部依据，主体信息全部从文档内推导。
"""
from __future__ import annotations

import re

from common import normalize_name

# 词尾（长词优先，保证先匹配到「有限责任公司」而非「有限公司」）
# 注意：「中心」「工程中心」不在此列。「中心」是普通名词而非企业形式，
# 若当作形式词，投标文档里 ubiquitous 的「技术中心」「研发中心」会被抽成企业名，
# 凭空造出第二个主体字号，触发假的 P0「疑似混主体」。
_SUFFIXES = [
    "股份有限公司", "有限责任公司", "集团有限公司", "有限公司",
    "集团", "研究院", "研究所", "设计院", "事务所",
]

# 行政区划前缀（按长度降序）
_REGIONS = [
    "内蒙古自治区", "内蒙古", "黑龙江", "新疆维吾尔自治区", "新疆", "西藏",
    "宁夏回族自治区", "宁夏", "青海", "甘肃", "陕西", "山西", "河北", "河南",
    "湖南", "湖北", "安徽", "浙江", "江苏", "山东", "江西", "福建", "广东",
    "海南", "四川", "贵州", "云南", "辽宁", "吉林", "北京", "上海", "天津",
    "重庆", "台湾", "香港", "澳门",
]

# 连接词分两类。
#
# 强连接词是句子层面的标记，其后几乎必然是字号，可以裁掉前缀：
#   「本项目由北京华信科技有限公司」「甲方及乙方共同委托…」
#
# 弱连接词同时也是字号里常见的字——「和而泰」「中国联合」「清华同方」
# 都是真实字号的一部分。弱连接词单独出现时不能裁，否则真实公司名会被截断
# （「和而泰智能控制股份有限公司」会被截成「而泰智能控制股份有限公司」）。
_STRONG_CONNECTORS = [
    "以及", "并且", "我方", "贵司", "双方", "各方", "甲方", "乙方", "中标人",
    "投标人", "供应商", "承包人", "采购方", "招标人", "招标代理", "代理",
    "受托", "委托", "由",
]
_WEAK_CONNECTORS = [
    "联合", "协作", "为", "和", "同", "经", "并", "及", "与", "是", "从",
    "给", "向", "对", "或",
]

# 裁剪后至少要剩下的字号长度。太短说明连接词本身是字号的一部分
# （「华为技术」中的「为」），此时不裁剪。
_MIN_PREFIX_LEN = 4

# 计算核心字号时剥离的词尾：只有企业形式词。
# 研究院/研究所/设计院/事务所不是企业形式，剥它们会把
# 「中国建筑设计院」与「中国建筑」并成同一个主体。
_CORE_SUFFIXES = [
    "股份有限公司", "有限责任公司", "集团有限公司", "有限公司", "集团",
]

# 计算规范写法时可以剥掉的弱连接词。
# 「同」「和」「联合」「协作」在字号里极常见（和而泰、中国联合、清华同方），
# 剥掉它们会把「联合网络通信」缩成「网络通信」，与真·子公司「网络通信」撞车。
_CANONICAL_STRIP_CONNECTORS = [
    "为", "经", "并", "及", "与", "是", "从", "给", "向", "对", "或",
]

# 纯行业词，不能单独作为字号。出现「科技有限公司」这种名字说明是切错了。
_NON_NAME_WORDS = {
    "科技", "技术", "信息", "网络", "发展", "建设", "投资", "贸易", "工程",
}

# 括号组整体进入字号：括号里的「集团」是字号的一部分，不能当成公司词尾，
# 否则「北京华信(集团)有限公司」会被切成「北京华信(集团」。
_NAME_RE = re.compile(
    r"(?P<pre>(?:[一-龥A-Za-z0-9·]|\([^()（）]{1,20}\)|（[^()（）]{1,20}）){2,30}?)"
    r"(?P<suf>" + "|".join(map(re.escape, _SUFFIXES)) + r")"
)


def _is_form_fragment(prefix: str) -> bool:
    """字号是否只是公司形式词的一部分（如「股份」「有限」「责任」）。

    正则的非贪婪匹配可能把形式词从中间切开，例如
    「中信建设集团股份有限公司」会先切出「中信建设集团」，余下「股份有限公司」
    又被当作一个名称切出「股份」+「有限公司」。这样的字号不是真实主体名。

    只拒绝形式词的**严格前缀**。长度相等时不算片段，
    否则「设计院有限公司」「研究中心有限公司」这类真实名称会被误杀。
    """
    for s in _SUFFIXES:
        if 2 <= len(prefix) < len(s) and s.startswith(prefix):
            return True
    return False


def _strip_unbalanced_parens(name: str) -> str:
    """去掉不成对的括号。

    括号被纳入字号字符类后，「（北京华信科技有限公司）」会切出
    「（北京华信科技有限公司」，尾部括号留在名字外面。
    """
    for op, cl in (("(", ")"), ("（", "）")):
        while name.startswith(op) and cl not in name:
            name = name[1:]
        while name.endswith(cl) and op not in name:
            name = name[:-1]
    return name


def _starts_with_region(text: str) -> bool:
    """是否以行政区划开头。"""
    return any(text.startswith(r) for r in _REGIONS)


def _trim_prefix(prefix: str) -> str:
    """切掉前缀中的连接词，取最短的合格切分作为字号主体。

    枚举每个连接词的出现位置，切掉它及其之前的部分，在长度不小于
    _MIN_PREFIX_LEN 的候选中取最短的一个——也就是最靠后的那个连接词，
    同时跳过切完太短的候选。长度都不合格时完全不裁剪。

    强连接词后面几乎必然是字号，可以直接裁。弱连接词同时也是字号的一部分
    （「和而泰」「中国联合」「清华同方」），只有当其后紧跟行政区划时才裁：
    以行政区划开头的主体名几乎必然是真正的主体名，
    这样「联合北京华信科技有限责任公司」能裁掉「联合」，
    而「和而泰智能控制」「中国联合网络通信集团」不会被裁。
    """
    best = None
    for conn in _STRONG_CONNECTORS:
        best = _best_cut(prefix, conn, best, require_region=False)
    for conn in _WEAK_CONNECTORS:
        best = _best_cut(prefix, conn, best, require_region=True)
    if best is None:
        return prefix.strip()
    return best


def _best_cut(prefix: str, conn: str, best: str | None, require_region: bool) -> str | None:
    """在 conn 的所有出现位置上切分，返回目前最短的合格候选。"""
    start = 0
    while True:
        idx = prefix.find(conn, start)
        if idx < 0:
            break
        candidate = prefix[idx + len(conn):].strip()
        if len(candidate) >= _MIN_PREFIX_LEN:
            if require_region and not _starts_with_region(candidate):
                pass  # 弱连接词后面不是行政区划，保留原字号
            elif best is None or len(candidate) < len(best):
                best = candidate
        start = idx + 1
    return best


def extract_company_names(text: str) -> list[str]:
    """抽取公司类名称，按出现顺序去重。"""
    out: list[str] = []
    seen: set[str] = set()
    for m in _NAME_RE.finditer(text or ""):
        prefix = _trim_prefix(m.group("pre"))
        if len(prefix) < 2:
            continue
        if _is_form_fragment(prefix) or prefix in _NON_NAME_WORDS:
            continue
        name = _strip_unbalanced_parens(prefix + m.group("suf"))
        key = normalize_name(name)
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def _strip_suffix(name: str) -> str:
    """去掉公司词尾，可能叠层：「XX集团股份有限公司」→「XX集团」→「XX」。

    只剥企业形式词。研究院/研究所/设计院/事务所不是企业形式，
    剥它们会把「中国建筑设计院」与「中国建筑」并成同一个主体。
    """
    changed = True
    while changed:
        changed = False
        for s in _CORE_SUFFIXES:
            if name.endswith(s) and len(name) > len(s):
                name = name[: -len(s)]
                changed = True
                break
    return name


def _strip_region(name: str) -> str:
    for r in _REGIONS:
        if name.startswith(r):
            return name[len(r):]
    return name


def core_key(name: str) -> str:
    """核心字号：去掉公司词尾（可叠层）与行政区划前缀后的剩余部分。

    刻意不剥离行业词。行业词参与主体区分：
    「华信科技」与「华信信息技术」是两个不同主体，剥掉行业词会把它们混为一谈。
    """
    n = normalize_name(name)
    n = _strip_suffix(n)
    n = _strip_region(n)
    return n


def _strip_leading_weak(core: str) -> str:
    """去掉字号开头的弱连接词。

    只有在去掉后仍剩至少 _MIN_PREFIX_LEN 个字时才裁，
    否则「与信科技」「同创」这类真实字号会被裁成「信科技」「创」。

    只剥 _CANONICAL_STRIP_CONNECTORS：「同」「和」「联合」「协作」是字号里
    极常见的字，剥掉会把「联合网络通信」缩成「网络通信」。
    """
    changed = True
    while changed and core:
        changed = False
        for w in _CANONICAL_STRIP_CONNECTORS:
            if core.startswith(w) and len(core) - len(w) >= _MIN_PREFIX_LEN:
                core = core[len(w):]
                changed = True
                break
    return core


def canonical_core(name: str) -> str:
    """主体标识：去掉公司词尾，再去掉开头的弱连接词。

    「与上海远大信息技术有限公司」与「上海远大信息技术有限公司」
    的 canonical_core 相同，判定混主体时不能算成两个主体。

    行政区划保留（「上海远大信息技术」而不是「远大信息技术」）：
    混主体检查要比的就是「是不是同一家」，北京与上海同名不是同一家。
    少了行政区划，两家不同城市的同名企业会被并成一个主体。
    """
    n = normalize_name(name)
    n = _strip_suffix(n)
    return _strip_leading_weak(n)


def canonical_name(name: str) -> str:
    """同一主体的规范写法：去掉开头的弱连接词。"""
    for s in _SUFFIXES:
        if name.endswith(s):
            return _strip_leading_weak(name[: -len(s)]) + s
    return _strip_leading_weak(name)


def same_entity(a: str, b: str) -> bool:
    """两个名称是否指向同一主体。

    核心字号相等即同一主体。此外两种关系也算：
    - 互为**后缀**：带连接词前缀的同一写法与干净写法（「由北京华信科技」）
    - 互为**前缀**且较短一方像简称（≤3 字，或以行政区划开头）：
      「北京华信」与「北京华信科技有限公司」

    前缀关系不加限制会误并「中国建筑」与「中国建筑科技」，
    所以要求较短一方是简称形态。
    """
    ca, cb = canonical_core(a), canonical_core(b)
    if not ca or not cb:
        return False
    if ca == cb:
        return True
    shorter, longer = sorted([ca, cb], key=len)
    if len(shorter) < 2:
        return False
    if longer.endswith(shorter):
        return True
    if longer.startswith(shorter) and (
        len(shorter) <= 3 or _starts_with_region(shorter)
    ):
        return True
    return False


def group_variants(names: list[str]) -> list[dict]:
    """按主体聚类。

    返回 [{core, names, canonicals}]：
    - names      该主体的原始写法，按首次出现排序
    - canonicals 去掉弱连接词前缀后的写法集合。同一写法只算一种，
                 用来判断「同一主体是否出现了多种写法」——
                 「与上海远大信息技术有限公司」和「上海远大信息技术有限公司」
                 规范写法相同，不算两种写法
    - core       成员中最长的核心字号
    """
    groups: list[dict] = []
    for name in names:
        placed = False
        for g in groups:
            if same_entity(name, g["names"][0]):
                g["names"].append(name)
                canon = canonical_name(name)
                if canon not in g["canonicals"]:
                    g["canonicals"].append(canon)
                placed = True
                break
        if not placed:
            groups.append({
                "core": core_key(name),
                "names": [name],
                "canonicals": [canonical_name(name)],
            })
    for g in groups:
        g["core"] = max((core_key(n) for n in g["names"]), key=len)
    return groups
