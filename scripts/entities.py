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
    "投标人", "供应商", "承包人", "采购方", "招标人", "招标代理",
    "受托", "委托", "由",
]
_WEAK_CONNECTORS = [
    "联合", "协作", "为", "和", "同", "经", "并", "及", "与", "是", "从",
    "给", "向", "对", "或", "代理",
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

# 行业词全集。字号以行业词结尾时，它描述的是经营范围而不是字号本身，
# 因此不能拿它当简称（「北京华信科技」不是「北京华信科技有限公司」的简称，
# 是另一家公司）。「服务」「咨询」也计入：把它们当成简称会把
# 「北京华信科技服务有限公司」并进「北京华信科技有限公司」。
_INDUSTRY_WORDS = _NON_NAME_WORDS | {"服务", "咨询"}

# 企业形式词：剥掉之后剩下的才是字号
_ENTERPRISE_SUFFIXES = [
    "股份有限公司", "有限责任公司", "集团有限公司", "有限公司",
]

# 组织形式词：不是企业形式，但单独作为字号时是通用片段
# （「研究院有限公司」「设计院有限公司」不是公司名）
_ORG_FORM_WORDS = {"研究院", "研究所", "设计院", "事务所", "集团"}

# 括号组整体进入字号：括号里的「集团」是字号的一部分，不能当成公司词尾，
# 否则「北京华信(集团)有限公司」会被切成「北京华信(集团」。
_NAME_RE = re.compile(
    r"(?P<pre>[一-龥A-Za-z0-9·](?:[一-龥A-Za-z0-9·]|\([^()（）]{1,20}\)|（[^()（）]{1,20}）){1,29}?)"
    r"(?P<suf>" + "|".join(map(re.escape, _SUFFIXES)) + r")"
)

# 「名字串」的一个片段：单个名字字符，或一整组括号
_NAME_CHUNK_RE = re.compile(
    r"[一-龥A-Za-z0-9·]|\([^()（）]{1,20}\)|（[^()（）]{1,20}）"
)

# 在一段文字里找公司形式词
_SUFFIX_SEARCH_RE = re.compile("|".join(map(re.escape, _SUFFIXES)))


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


def _segment_end(text: str, start: int) -> int:
    """从 start 开始，「名字串」能延伸到哪儿（标点、空白处为止）。

    名字串由名字字符与整组括号拼成，「）」这种落单的括号不算名字字符。
    """
    i = start
    n = len(text)
    while i < n:
        m = _NAME_CHUNK_RE.match(text, i)
        if not m:
            break
        i = m.end()
    return i


def _has_name_boundary(text: str) -> bool:
    """片段里是否出现了「另一个主体的起点」。

    强连接词后面必然是新主体；弱连接词后面紧跟行政区划时也是新主体
    （「北京华信科技有限公司和上海远大信息技术有限公司」是两个主体）。
    """
    for conn in _STRONG_CONNECTORS:
        if conn in text:
            return True
    for conn in _WEAK_CONNECTORS:
        idx = text.find(conn)
        while idx >= 0:
            if _starts_with_region(text[idx + len(conn):]):
                return True
            idx = text.find(conn, idx + 1)
    return False


def _extend_over_suffix(text: str, end: int) -> int:
    """把名字延伸过紧跟其后的公司形式词，以及同一串里更靠后的形式词。

    「中国建筑设计院有限公司」的非贪婪匹配会停在「设计院」，
    余下的「有限公司」才是真正的企业形式词。

    「北京华信集团研究院有限公司」「中铁建工集团北京工程有限公司」
    这类名字里，字号本身还含有形式词或行业词，最外层的形式词才是名字的
    终点。因此名字要一直延伸到本串里最后一个形式词为止——
    中间那段文字若出现了新主体的起点（连接词），就到此为止。
    """
    n = len(text)
    changed = True
    while changed:
        changed = False
        for s in _SUFFIXES:
            if text.startswith(s, end):
                end += len(s)
                changed = True
                break
        if changed:
            continue
        seg_end = _segment_end(text, end)
        seg = text[end:seg_end]
        m = _SUFFIX_SEARCH_RE.search(seg)
        if m and not _has_name_boundary(seg[:m.start()]):
            end += m.end()
            changed = True
    return end


def _is_in_bracket(text: str, start: int, end: int) -> bool:
    """候选名是否整个落在一对括号里（注解括号）。"""
    if start <= 0 or end >= len(text):
        return False
    for op, cl in (("(", ")"), ("（", "）")):
        if text[start - 1] == op and text[end] == cl:
            return True
    return False


def _generic_fragment(name: str) -> bool:
    """这个名字是不是通用片段，而不是公司名。

    两种情形：
    - 字号本身就是形式词：「研究院有限公司」「设计院有限公司」
    - 字号剥掉行政区划后只剩行业词：「工程咨询有限公司」「北京工程有限公司」
    """
    core = name
    for s in _ENTERPRISE_SUFFIXES:
        if core.endswith(s) and len(core) > len(s):
            core = core[: -len(s)]
            break
    if core != name and core in _ORG_FORM_WORDS:
        return True
    rest = core
    for r in _REGIONS:
        if rest.startswith(r):
            rest = rest[len(r):]
            break
    if not rest:
        return False
    while rest:
        for w in sorted(_INDUSTRY_WORDS, key=len, reverse=True):
            if rest.startswith(w):
                rest = rest[len(w):]
                break
        else:
            return False
    return True


def extract_company_names(text: str) -> list[str]:
    """抽取公司类名称，按出现顺序去重。

    扫描是「跳到延伸后的末尾再继续」，不是 finditer 的逐个匹配：
    名字延伸过去的那截文字若被重新匹配一次，就会凭空多出半个公司名
    （「北京华信集团研究院有限公司」曾被切成「北京华信集团研究院」
    与「研究院有限公司」两个名字）。
    """
    out: list[str] = []
    seen: set[str] = set()
    text = text or ""
    pos = 0
    n = len(text)
    while pos < n:
        m = _NAME_RE.search(text, pos)
        if not m:
            break
        end = _extend_over_suffix(text, m.end())
        # 跳到延伸后的末尾，延伸过去的那截不再重新匹配
        pos = max(end, m.end())
        prefix = _trim_prefix(m.group("pre"))
        if len(prefix) < 2:
            continue
        if _is_form_fragment(prefix) or prefix in _NON_NAME_WORDS:
            continue
        name = _strip_unbalanced_parens(prefix + text[m.start("suf"):end])
        if _generic_fragment(name):
            continue
        if _is_in_bracket(text, m.start(), end) and _ends_with_org_form(name):
            # 注解括号里的内容不是主体：「（华信集团）北京华信科技有限公司」
            continue
        key = normalize_name(name)
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def _ends_with_org_form(name: str) -> bool:
    for s in _ORG_FORM_WORDS:
        if name.endswith(s):
            return True
    return False


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
    """同一主体的规范写法：归一化后去掉开头的弱连接词。

    必须与 canonical_core 用同一套归一化，否则全角半角括号、
    空白差异会被当成两种写法，报出假的「同一主体出现多种写法」。
    """
    for s in _SUFFIXES:
        if name.endswith(s):
            return _strip_leading_weak(normalize_name(name[: -len(s)])) + s
    return _strip_leading_weak(normalize_name(name))


def _extra_head_is_clean(longer: str, shorter: str) -> bool:
    """较长的核心字号比短的多出来的部分不含弱连接词。

    「联合网络通信」与「网络通信」多出来的「联合」是字号的一部分，
    不是句子碎片，不能算同一主体。而「由北京华信科技」多出来的「由」
    是强连接词，是句子碎片，应该算同一主体。
    """
    head = longer[: len(longer) - len(shorter)]
    if any(w in head for w in _WEAK_CONNECTORS):
        return False
    return not _ends_with_industry_word(head)


def _ends_with_industry_word(core: str) -> bool:
    return any(core.endswith(w) for w in _INDUSTRY_WORDS)


def _is_plausible_short_form(core: str) -> bool:
    """短的一方是不是像简称。

    字号以行业词结尾时，它描述的是经营范围而不是字号本身，不能当简称：
    「北京华信科技」不是「北京华信科技服务有限公司」的简称，是另一家公司。
    其余情况要求短的一方真的像简称：不超过 3 个字，或以行政区划开头。
    「中国建筑」既不短也不带行政区划，因此不能与「中国建筑科技」合并。
    """
    if _ends_with_industry_word(core):
        return False
    if len(core) <= 3:
        return True
    return _starts_with_region(core)


def same_entity(a: str, b: str) -> bool:
    """两个名称是否指向同一主体。

    核心字号相等即同一主体。此外两种关系也算：
    - 互为**后缀**且多出来的部分不含弱连接词：带连接词前缀的同一写法与干净写法
      （「由北京华信科技」）。多出来的若是「联合」「和」这类字号常用字
      （「联合网络通信」之于「网络通信」），则不是同一主体
    - 互为**前缀**且较短一方像简称：不超过 3 个字，或以行政区划开头，
      且不以行业词结尾（否则是经营范围不同，不是简称）

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
    if longer.endswith(shorter) and _extra_head_is_clean(longer, shorter):
        return True
    if longer.startswith(shorter) and _is_plausible_short_form(shorter):
        return True
    return False


def _groups_mergeable(a: dict, b: dict) -> bool:
    """两组能否合并：两两互为同一主体。

    这条规则与输入顺序无关：合并与否只取决于两组成员之间的两两关系，
    不取决于谁先来。比「先到先得」严，不会因为先来的名字把后来的名字吸进来。
    """
    return all(
        same_entity(x, y) for x in a["names"] for y in b["names"]
    )


def _canonicals(members: list[str]) -> list[str]:
    """成员去弱连接词后的规范写法，按首次出现排序。"""
    out: list[str] = []
    for n in members:
        c = canonical_name(n)
        if c not in out:
            out.append(c)
    return out


def group_variants(names: list[str]) -> list[dict]:
    """按主体聚类。

    聚类结果与输入顺序无关。同样的名字集合，无论顺序如何，分组都一样——
    否则同一批文档换个顺序跑，报告的结论就会变。

    返回 [{core, names, canonicals}]：
    - names      该主体的原始写法，按首次出现排序
    - canonicals 去掉弱连接词前缀后的写法集合。同一写法只算一种，
                 用来判断「同一主体是否出现了多种写法」——
                 「与上海远大信息技术有限公司」和「上海远大信息技术有限公司」
                 规范写法相同，不算两种写法
    - core       成员中最长的核心字号

    先按规范核心字号精确分组，再按显式的、顺序无关的规则跨组合并：
    两组之间每一对名字都互为同一主体时才合并。
    """
    unique = list(dict.fromkeys(names))
    order = {n: i for i, n in enumerate(unique)}

    def sort_key(n: str) -> tuple:
        return (canonical_core(n), canonical_name(n), n)

    buckets: dict[str, list[str]] = {}
    for n in sorted(unique, key=sort_key):
        buckets.setdefault(canonical_core(n), []).append(n)

    groups: list[dict] = []
    for core in sorted(buckets):
        members = sorted(buckets[core], key=lambda n: order[n])
        groups.append({
            "core": core,
            "names": members,
            "canonicals": _canonicals(members),
        })

    # 跨组合并：候选对按 core 排序，合并结果与输入顺序无关
    while True:
        best = None
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                if not _groups_mergeable(groups[i], groups[j]):
                    continue
                key = (groups[i]["core"], groups[j]["core"])
                if best is None or key < best[0]:
                    best = (key, i, j)
        if best is None:
            break
        _, i, j = best
        merged = sorted(groups[i]["names"] + groups[j]["names"],
                        key=lambda n: order[n])
        groups[i] = {
            "core": min(groups[i]["core"], groups[j]["core"]),
            "names": merged,
            "canonicals": _canonicals(merged),
        }
        del groups[j]

    for g in groups:
        g["core"] = max((core_key(n) for n in g["names"]), key=len)
    groups.sort(key=lambda g: g["core"])
    return groups
