"""主体名抽取与变体聚类。

本工具不引入外部依据，主体信息全部从文档内推导。
"""
from __future__ import annotations

import re
from pathlib import Path

from common import normalize_name

# 词尾（长词优先，保证先匹配到「有限责任公司」而非「有限公司」）
# 注意：「中心」「工程中心」不在此列。「中心」是普通名词而非企业形式，
# 若当作形式词，投标文档里 ubiquitous 的「技术中心」「研发中心」会被抽成企业名，
# 凭空造出第二个主体字号，触发假的 P0「疑似混主体」。
_SUFFIXES = [
    "股份有限公司", "有限责任公司", "集团有限公司", "有限公司",
    "集团", "研究院", "研究所", "设计院", "事务所",
]

# 行政区划表放在数据文件里，不写在代码里。
#
# 名单有两百多个地名，写在代码里既难核对也不好维护：少一个城市就有一条
# 规则失效——「中标人：和广州华信科技有限公司」里的「和」只有在其后是
# 行政区划时才会被裁掉，广州不在表里就裁不掉，于是抽出一个并不存在的
# 「和广州华信科技有限公司」。
#
# 数据文件随 scripts/ 一起装进技能目录，路径由 __file__ 决定，
# 与当前工作目录无关。
_REGION_FILE = Path(__file__).resolve().parent / "data" / "regions.txt"


def _load_regions() -> list[str]:
    """读行政区划表，按长度降序（长的先匹配）。

    「内蒙古自治区」必须比「内蒙古」先匹配，否则剥行政区划时会剩下
    「自治区科技有限公司」。
    """
    names: set[str] = set()
    for line in _REGION_FILE.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.add(line)
    return sorted(names, key=lambda n: (-len(n), n))


_REGIONS = _load_regions()

# 国家前缀（不是行政区划，单独一张表）。
#
# 「中国」「中华」是**国家的名字**，不是行政区划，因此不能放进 regions.txt：
# 放进去会让「中国建筑」被当成「以行政区划开头的简称」，
# same_entity("中国建筑", "中国建筑科技") 就变成 True——那是两家公司。
#
# 但国家前缀与行政区划前缀在**区分标志**这件事上作用相同：
# 「中国联合网络通信集团有限公司」与「联合网络通信有限公司」是
# 集团公司与子公司，两家不同的公司，不能并成一家。
#
# 与行政区划前缀一样，在两处检查：
#   1. _extra_head_is_clean：多出来的那部分是国家前缀 → 不是同一主体；
#   2. _connector_cut_allowed：连接词前面那段是国家前缀 **而且本身是一个完整字号**
#      → 连接词是字号的一部分。
# 两处都用同一张表，避免「这里当区分标志、那里当句子碎片」的分叉。
_COUNTRY_PREFIXES = ("中国", "中华")

# 国家前缀那一段什么时候算「完整的字号」（wordmark）。
#
# 头部长这样时，句子级连接词是字号的一部分，不能裁。
#
# 「中国联通本次项目」**不是**完整字号——「本次项目」是一个开放从句。
# 只要头部以国家前缀开头就一律不裁，会把从句连同它后面那家公司一起吞进来：
# 「中国联通本次项目由华为技术有限公司」会被抽成一个并不存在的公司名，
# 真正存在的「华为技术有限公司」反而整条抽不出来。
#
# 因此国家前缀这一条只在头部**本身就是一个完整字号**时才生效。
#
# 形式词用抽取器自己认的那一套（_SUFFIXES）：只有完整的企业/组织形式词
# 才算「完整字号」。**没有**把光秃秃的「公司」「有限」「股份」算进去——
# 那三个是半截形式词，以它们结尾的头部（如「中国石油有限」「中国分公司」）
# **不是**完整字号，拿它挡住裁剪会发布一个并不存在的公司名
# （「中国石油有限由华为技术有限公司」），那正是这一波要治的病。
#
# 补一句实话——这条守卫的实际覆盖面比看上去小得多：
#
#   头部是 prefix[:idx]，即**连接词前面那一段**；而正则的 pre 组
#   非贪婪，止于**第一个形式词之前**。因此普通散文里的头部里
#   根本不出现完整的形式词，「中国联通集团」这种写法**到不了**
#   这个分支（pre 组是「中国联通」，形式词「集团」在 pre 组之外）。
#   穷举过各种构造与随机串，这条分支只在**头部带括号**时才会触发：
#   形式词被拆进括号里（`中国(集团由华为技术)有限公司`），头部就成了
#   「中国(集团」——它以形式词结尾，守卫因此生效，连接词不被裁掉。
#
#   所以这条分支的实际作用是**保护带括号的头部**，不是识别完整字号。
#   去掉它，`中国(集团由华为技术)有限公司` 会被裁成
#   `华为技术)有限公司`——一个括号都不配平的错名字。留着它。
#
# 结论：这条守卫**不会**在普通字号散文上生效，以国家前缀开头的开放从句
# 一律照裁。
_COUNTRY_WORDMARK_TAILS = tuple(_SUFFIXES)

# 按首字索引：_starts_with_region 要被调用很多次，逐个比对两百多个地名
# 太慢，先按首字分桶。
_REGIONS_BY_FIRST: dict[str, list[str]] = {}
for _r in _REGIONS:
    _REGIONS_BY_FIRST.setdefault(_r[0], []).append(_r)

# 连接词表。每条词记住它是「句子级」还是「字号级」：
#
#   句子级（强）：甲方、乙方、我方、受托、由…——句子层面的标记，
#                  其后几乎必然是一个主体。
#   字号级（弱）：联合、协作、为、和、同、经…——同时也是字号里常见的字
#                  （和而泰、中国联合、清华同方、代理记账），不能无条件裁。
#
# 这是一张表，不再分两组。抽取时裁前缀（_trim_prefix）与算规范核心字号
# （canonical_core）用的是**同一条规则、同一组词**。分两组各用一套的代价是
# 「和」「同」在两处行为不一致：抽取时把「和深圳华信科技」的「和」裁掉了，
# 规范核心字号却留着它，同一个主体的两种写法因此对不上号。
_CONNECTORS = [
    ("以及", True), ("并且", True), ("我方", True), ("贵司", True),
    ("双方", True), ("各方", True), ("甲方", True), ("乙方", True),
    ("中标人", True), ("投标人", True), ("供应商", True), ("承包人", True),
    ("采购方", True), ("招标人", True), ("招标代理", True),
    ("受托", True), ("委托", True), ("由", True),
    ("联合", False), ("协作", False), ("为", False), ("和", False),
    ("同", False), ("经", False), ("并", False), ("及", False),
    ("与", False), ("是", False), ("从", False), ("给", False),
    ("向", False), ("对", False), ("或", False), ("代理", False),
]

# 字号级连接词：同时也是字号里常见的字。
# 「多出来的部分」里出现这些字，说明多出来的是字号的一部分而不是句子碎片。
_NAME_CONNECTORS = [w for w, s in _CONNECTORS if not s]

# 裁剪后至少要剩下的字号长度。太短说明连接词本身是字号的一部分
# （「华为技术」中的「为」），此时不裁剪。
_MIN_PREFIX_LEN = 4

# 计算核心字号时剥离的词尾：只有企业形式词。
# 研究院/研究所/设计院/事务所不是企业形式，剥它们会把
# 「中国建筑设计院」与「中国建筑」并成同一个主体。
_CORE_SUFFIXES = [
    "股份有限公司", "有限责任公司", "集团有限公司", "有限公司", "集团",
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
#
# 「公司形式词」前面允许只有一个字。字号至少两个字是《公司法》的要求，
# 但那一条由抽取后的判断负责，不该由正则负责：正则若要求两个字，
# 「甲有限公司和而泰智能控制股份有限公司」就会越过第一个形式词，
# 整串合成一个名字——两个公司被并成一个。
_NAME_RE = re.compile(
    r"(?P<pre>[一-龥A-Za-z0-9·](?:[一-龥A-Za-z0-9·]|\([^()（）]{1,20}\)|（[^()（）]{1,20}）){0,29}?)"
    r"(?P<suf>" + "|".join(map(re.escape, _SUFFIXES)) + r")"
)

# 「名字串」的一个片段：单个名字字符，或一整组括号
_NAME_CHUNK_RE = re.compile(
    r"[一-龥A-Za-z0-9·]|\([^()（）]{1,20}\)|（[^()（）]{1,20}）"
)

# 汉字。字号里必须有汉字，否则「A有限公司」这种写法会被当成公司名。
_CJK_RE = re.compile(r"[一-龥]")

# 在一段文字里找公司形式词（括号里的形式词不算，见 _find_suffix_outside_brackets）


def _is_form_fragment(prefix: str) -> bool:
    """字号是否只是公司形式词的一部分（如「股份」「有限」「责任」「有」）。

    正则的非贪婪匹配可能把形式词从中间切开，例如
    「中信建设集团股份有限公司」会先切出「中信建设集团」，余下「股份有限公司」
    又被当作一个名称切出「股份」+「有限公司」。这样的字号不是真实主体名。

    只拒绝形式词的**严格前缀**。长度相等时不算片段，
    否则「设计院有限公司」「研究中心有限公司」这类真实名称会被误杀。
    """
    for s in _SUFFIXES:
        if 1 <= len(prefix) < len(s) and s.startswith(prefix):
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
    for r in _REGIONS_BY_FIRST.get(text[:1], ()):
        if text.startswith(r):
            return True
    return False


def _starts_with_country(text: str) -> bool:
    """是否以国家前缀开头（「中国」「中华」）。

    国家前缀不是行政区划，因此单列一张表（见 _COUNTRY_PREFIXES）。
    """
    return text.startswith(_COUNTRY_PREFIXES)


def _is_country_wordmark(head: str) -> bool:
    """以国家前缀开头的那一段本身是不是一个完整的字号。

    「中国联通集团」是完整字号；「中国联通本次项目」不是——后面是一个
    开放从句。以国家前缀开头就一律当字号，会把从句连同它后面那家公司
    一起吞进名字里（见 _connector_cut_allowed）。

    头部长什么样见 _COUNTRY_WORDMARK_TAILS 上面的说明：它止于第一个形式词
    之前，因此普通散文里的头部里没有完整的形式词，这条判定实际只在
    **形式词被拆进括号里**的写法上生效（如 `中国(集团`）。它是括号保护，
    不是「完整字号」的识别。
    """
    return head.endswith(_COUNTRY_WORDMARK_TAILS)


def _connector_cut_allowed(prefix: str, idx: int, sentence_level: bool,
                           candidate: str) -> bool:
    """这一处连接词是不是「两个主体之间的分隔符」。

    抽取时裁前缀与算规范核心字号共用这一条规则：

    - 候选部分以行政区划开头：其后几乎必然是新主体，连接词是分隔符
      （「联合北京华信科技」「和深圳华信科技」）。
    - 句子级连接词，且它前面那段文字是句子碎片：连接词是句子的成分，
      不是字号的一部分（「本文件由华为技术有限公司」）。
      字号至少两个字，因此连接词前面只有一个字时，那个字与连接词同属字号
      （「自由贸易港城」里的「由」）。
      连接词前面那段以**行政区划**开头时同样不裁：
      「海南自由贸易港城」是完整的字号，里面的连接词是字号的一部分。
    - 句子级连接词，且它前面那段以**国家前缀**开头、**并且本身就是一个
      完整字号**（「中国联通集团」）时也不裁。
      只是「以国家前缀开头的从句」（「中国联通本次项目」）时**照裁**：
      从句不是字号，裁掉之后后面那家公司才抽得出来
      （「中国联通本次项目由华为技术有限公司」→「华为技术有限公司」）。
    - 其余情况：连接词是字号的一部分，保留（「和而泰」「中国联合」）。

    候选部分太短说明连接词本身就是字号的一部分（「华为技术」中的「为」）。
    """
    if len(candidate) < _MIN_PREFIX_LEN:
        return False
    if _starts_with_region(candidate):
        return True
    if not sentence_level:
        return False
    head = prefix[:idx]
    if not head:
        return True
    if _starts_with_region(head):
        return False
    if _starts_with_country(head) and _is_country_wordmark(head):
        # 国家前缀 + 完整字号（「中国联通集团」）：
        # 连接词是字号的一部分，不能裁掉。
        return False
    return len(head) >= 2


def _starts_with_connector(text: str) -> bool:
    """这段文字是不是以连接词开头。

    连接词是句子碎片（「甲方」「委托」「及」），不是字号的一部分。
    用来把句子碎片从「更宽的候选」里剔出去。
    """
    return any(text.startswith(w) for w, _level in _CONNECTORS)


# 句子级连接词里「由」是个例外：它常出现在词的中间（自由、由于、理由），
# 不能因为候选里有「由」就断定那一段是句子碎片。
#
# 其余的句子级连接词（甲方、乙方、委托、采购方…）出现在候选里，
# 就说明候选前面还有没裁干净的句子碎片。
_JUNK_MARKERS = tuple(
    w for w, level in _CONNECTORS if level and w != "由"
)


def _is_junk_candidate(text: str) -> bool:
    """这段候选是不是还带着句子碎片。

    「共同委托北京华信科技」不是字号——「共同委托」是句子的成分。
    「中国自由贸易港城」是字号——里面的「由」是「自由」的一半。
    """
    if _starts_with_connector(text):
        return True
    return any(w in text for w in _JUNK_MARKERS)


def _cut_candidates(prefix: str) -> list[str]:
    """连接词裁剪时**所有**合格的切分，按发现顺序。

    _trim_prefix 只取其中最短的一个；这里把全部候选留下来，是为了判断
    **裁剪点是不是落在字号内部**（见 _trim_prefix_details）。
    """
    out: list[str] = []
    for word, sentence_level in _CONNECTORS:
        start = 0
        while True:
            idx = prefix.find(word, start)
            if idx < 0:
                break
            candidate = prefix[idx + len(word):].strip()
            if _connector_cut_allowed(prefix, idx, sentence_level, candidate):
                out.append(candidate)
            start = idx + 1
    return out


def _trim_prefix_details(prefix: str) -> tuple[str, str]:
    """返回 (采用的字号前缀, 更宽的候选)。

    采用的仍然是**最短**的合格切分——这条口径一个字没动。
    第二个返回值是「裁剪点落在字号内部」时更接近真字号的那一个切分。

    为什么会落在字号内部：「本项目由中国自由贸易港城」里有两个「由」，
    第二个是「自由」的一半。合格的切分有两个——「中国自由贸易港城」与
    「贸易港城」——裁剪取最短的那个，于是字号被劈掉一半。另一个切分
    才是完整的字号。

    只认**不以连接词开头**的候选：「甲方及乙方共同委托北京华信科技」
    这种句子碎片不是字号，不能拿来还原。没有这样的候选时，第二个
    返回值与第一个相同（没有可还原的余地）。
    """
    cands = _cut_candidates(prefix)
    if not cands:
        kept = prefix.strip()
        return kept, kept
    kept = cands[0]
    for c in cands[1:]:
        if len(c) < len(kept):
            kept = c
    wider = [c for c in cands
             if len(c) > len(kept) and not _is_junk_candidate(c)]
    if not wider:
        return kept, kept
    return kept, max(wider, key=len)


def _trim_prefix(prefix: str) -> str:
    """切掉前缀中的连接词，取最短的合格切分作为字号主体。

    枚举每个连接词的出现位置，切掉它及其之前的部分，在合格的候选中取最短的
    一个——也就是最靠后的那个连接词。连接词是不是分隔符由
    _connector_cut_allowed 判断（抽取与规范核心字号同一套规则）。
    """
    return _trim_prefix_details(prefix)[0]


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


def _gap_boundary(gap: str) -> int | None:
    """名字中间那段文字里有没有「另一个主体的起点」，有的话给出它的位置。

    这段文字是「第一个公司形式词」与「同一串里更靠后的形式词」之间的内容。
    判定必须由连接词驱动，不能只靠行政区划：

    - 连接词出现在这段文字的**开头**时，它就是两个主体之间的连接词
      （「北京华信科技有限公司**和**华为技术有限公司」）。字面开头的
      连接词也可能是字号的一部分（「和而泰」「中国联合」「清华同方」），
      但那种写法里连接词在名字的开头，不在这段中间文字里——
      区分「连接词」与「字号的一部分」靠的是它在名字里的位置，不是字本身；
      连接词本身要不要裁，交给 _trim_prefix 按统一规则判断；
    - 连接词后面紧跟行政区划时也是新主体（「…工程**与**深圳华信咨询有限公司」）。

    句子级连接词（由、甲方…）出现在这段文字的**中间**时不作为边界：
    「中国石油集团**自由贸易**有限公司」里的「由」是字号的一部分，
    不能把名字劈成两半。
    """
    best = None
    for word, _level in _CONNECTORS:
        if gap.startswith(word):
            return 0
        idx = gap.find(word)
        while idx >= 0:
            if _starts_with_region(gap[idx + len(word):]):
                if best is None or idx < best:
                    best = idx
            idx = gap.find(word, idx + 1)
    return best


def _find_suffix_outside_brackets(seg: str) -> tuple[int, int] | None:
    """在片段里找公司形式词，括号里的不算。

    「北京华信科技有限公司（集团）」里的「集团」在括号里，
    它不是名字的终点，不能把括号一起并进名字里。
    """
    i = 0
    n = len(seg)
    while i < n:
        m = _NAME_CHUNK_RE.match(seg, i)
        if not m:
            break
        if len(m.group(0)) == 1:      # 单个名字字符，括号组整体跳过
            for s in _SUFFIXES:
                if seg.startswith(s, i):
                    return i, i + len(s)
        i = m.end()
    return None


def _extend_over_suffix(text: str, end: int) -> tuple[int, int | None]:
    """把名字延伸过紧跟其后的公司形式词，以及同一串里更靠后的形式词。

    「中国建筑设计院有限公司」的非贪婪匹配会停在「设计院」，
    余下的「有限公司」才是真正的企业形式词。

    「北京华信集团研究院有限公司」「中铁建工集团北京工程有限公司」
    这类名字里，字号本身还含有形式词或行业词，最外层的形式词才是名字的
    终点。因此名字要一直延伸到本串里最后一个形式词为止——
    中间那段文字若出现了新主体的起点（连接词），就到此为止。

    返回 (名字终点, 下一个主体的起点)。第二个返回值非 None 表示中间
    遇到了另一个主体的起点：名字停在第一个形式词处，下一个名字从
    连接词**本身**开始。连接词要不要算进下一个名字，由 _trim_prefix 按
    统一规则判断（「和而泰」整体保留，「和深圳华信」的「和」裁掉）。
    """
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
        found = _find_suffix_outside_brackets(seg)
        if not found:
            break
        gap = seg[:found[0]]
        boundary = _gap_boundary(gap)
        if boundary is not None:
            return end, end + boundary
        end += found[1]
        changed = True
    return end, None


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

    只有一种情形：**字号整个就是形式词**，没有任何自己的字
    （「研究院有限公司」「设计院有限公司」）。

    「字号剥掉行政区划后只剩行业词」不作为拒绝理由：
    「北京工程咨询有限公司」「北京科技发展有限公司」「北京贸易有限公司」
    都是注册过的普通公司名，把它们丢掉，文档看起来就只有一个主体，
    混主体的检查也就跟着失效了。

    没有行政区划前缀、且字号里全是行业词时（「工程咨询有限公司」）
    仍然拒绝：那不是任何一家公司的字号。
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
            # 有行政区划前缀：字号里必然还有自己的字，按普通公司名处理
            return False
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


def extract_company_occurrences(text: str) -> list[tuple[str, str]]:
    """抽出 (裁剪后的名字, 还原名) 对，按出现顺序去重。

    裁剪后的名字是连接词裁剪留下来的那一段；还原名是**裁剪点落在字号
    内部**时更接近真字号的那一段（见 _trim_prefix_details）。两者都是
    文档里逐字存在的字符串。

    「本项目由中国自由贸易港城有限公司」裁出来的是「贸易港城有限公司」，
    还原名是「中国自由贸易港城有限公司」；「中国自由贸易港城有限公司」
    （裸字符串）只有一个合格切分，还原不出来，还原名与裁剪后的名字相同。

    聚类与报告用的是**还原名**：两家不同的公司被裁成同一个名字时
    （「贸易港城有限公司」），只有还原名才分得开是谁是谁。

    扫描是「跳到延伸后的末尾再继续」，不是 finditer 的逐个匹配：
    名字延伸过去的那截文字若被重新匹配一次，就会凭空多出半个公司名
    （「北京华信集团研究院有限公司」曾被切成「北京华信集团研究院」
    与「研究院有限公司」两个名字）。

    延伸遇到下一个主体的起点（连接词）时，名字停在第一个形式词处，
    下一个名字从连接词之后开始——「北京华信科技有限公司和华为技术有限公司」
    是两个公司，不能并成一个。
    """
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    text = text or ""
    pos = 0
    n = len(text)
    while pos < n:
        m = _NAME_RE.search(text, pos)
        if not m:
            break
        end, resume = _extend_over_suffix(text, m.end())
        # 跳到延伸后的末尾，延伸过去的那截不再重新匹配
        pos = max(end, m.end())
        if resume is not None:
            pos = max(pos, resume)
        kept, wider = _trim_prefix_details(m.group("pre"))
        if not kept:
            continue
        if _is_form_fragment(kept) or kept in _NON_NAME_WORDS:
            continue
        if not _CJK_RE.search(kept):
            # 字号里必须有汉字。「A有限公司」不是中文公司名，
            # 把 latin 字母当成字号会凭空造出一个主体。
            continue
        tail = text[m.start("suf"):end]
        name = _strip_unbalanced_parens(kept + tail)
        if _generic_fragment(name):
            continue
        if _is_in_bracket(text, m.start(), end) and _ends_with_org_form(name):
            # 注解括号里的内容不是主体：「（华信集团）北京华信科技有限公司」
            continue
        restored = name
        if wider != kept:
            # 裁剪点落在字号内部：把更宽的那一段还回来。
            candidate = _strip_unbalanced_parens(wider + tail)
            if (candidate != name and _CJK_RE.search(wider)
                    and not _is_form_fragment(wider)
                    and not _generic_fragment(candidate)):
                restored = candidate
        key = (normalize_name(name), normalize_name(restored))
        if key in seen:
            continue
        seen.add(key)
        out.append((name, restored))
    return out


def extract_company_names(text: str) -> list[str]:
    """抽取公司类名称，按出现顺序去重。

    返回的是**连接词裁剪之后**的那一段（可能比真名短，见
    extract_company_occurrences）。聚类与报告用的是还原名，用这个
    函数拿不到——它只是抽取器的原始结果。
    """
    out: list[str] = []
    seen: set[str] = set()
    for name, _restored in extract_company_occurrences(text):
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

    **流水线不用这个口径**：归组基准是 `canonical_core`，它保留行政区划
    （北京与上海同名不是同一家）。本函数**只为测试保留**——
    流水线里没有任何地方调用它，报告里也不出现它。
    「展示用核心字号」曾经被当成归组基准，会把两家同名公司并成一家。

    刻意不剥离行业词。行业词参与主体区分：
    「华信科技」与「华信信息技术」是两个不同主体，剥掉行业词会把它们混为一谈。
    """
    n = normalize_name(name)
    n = _strip_suffix(n)
    n = _strip_region(n)
    return n


def _strip_leading_connector(core: str) -> str:
    """去掉字号开头的连接词。

    与抽取时用的是同一条规则（_connector_cut_allowed），因此同一段文字
    单独出现与成对出现时读法一致：「和而泰智能控制股份有限公司」无论
    单独出现还是跟在另一家公司后面，都整体保留。

    裁完至少要剩 _MIN_PREFIX_LEN 个字，否则连接词本身就是字号的一部分
    （「与信科技」「同创」）。
    """
    changed = True
    while changed and core:
        changed = False
        for word, sentence_level in _CONNECTORS:
            if not core.startswith(word):
                continue
            candidate = core[len(word):].strip()
            if _connector_cut_allowed(core, 0, sentence_level, candidate):
                core = candidate
                changed = True
                break
    return core


def canonical_core(name: str) -> str:
    """主体标识：去掉公司词尾，再去掉开头的连接词。

    「与上海远大信息技术有限公司」与「上海远大信息技术有限公司」
    的 canonical_core 相同，判定混主体时不能算成两个主体。

    去连接词用的是与抽取同一套规则（_connector_cut_allowed），
    因此两种读法对得上号：「和深圳华信科技有限公司」与
    「深圳华信科技有限公司」是同一个主体，「和而泰智能控制股份
    有限公司」与它的单独读法也是同一个主体。

    行政区划保留（「上海远大信息技术」而不是「远大信息技术」）：
    混主体检查要比的就是「是不是同一家」，北京与上海同名不是同一家。
    少了行政区划，两家不同城市的同名企业会被并成一个主体。
    """
    n = normalize_name(name)
    n = _strip_suffix(n)
    return _strip_leading_connector(n)


def canonical_name(name: str) -> str:
    """同一主体的规范写法：归一化后去掉开头的连接词。

    必须与 canonical_core 用同一套归一化，否则全角半角括号、
    空白差异会被当成两种写法，报出假的「同一主体出现多种写法」。
    """
    for s in _SUFFIXES:
        if name.endswith(s):
            return _strip_leading_connector(normalize_name(name[: -len(s)])) + s
    return _strip_leading_connector(normalize_name(name))


def _extra_head_is_clean(longer: str, shorter: str) -> bool:
    """较长的核心字号比短的多出来的部分是不是「同一个主体的写法差异」。

    「联合网络通信」与「网络通信」多出来的「联合」是字号的一部分，
    不是句子碎片，不能算同一主体。而「由北京华信科技」多出来的「由」
    是句子级连接词，是句子碎片，应该算同一主体。

    多出来的部分**以行政区划开头**时也不能算同一主体：
    「华为技术有限公司」与「上海华为技术有限公司」是两家不同的公司，
    行政区划是区分标志，不是语气词。把它们归并会凭空造出一条
    「统一为正式全称」的确定级建议，让用户去统一两家公司的名字。

    多出来的部分**以国家前缀开头**时同样不能算同一主体：
    「中国联合网络通信集团有限公司」与「联合网络通信有限公司」
    是集团公司与子公司，两家不同的公司。国家前缀与行政区划前缀
    在这件事上作用相同，因此同样归入「区分标志」。
    """
    head = longer[: len(longer) - len(shorter)]
    if _starts_with_country(head):
        # 国家前缀与行政区划前缀一样是区分标志
        return False
    if any(w in head for w in _NAME_CONNECTORS):
        return False
    if _starts_with_region(head):
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


def _has_form_word(name: str) -> bool:
    """名字里有没有公司形式词。

    没有形式词的名字是**裸字号**（「北京华信」），它是简称而不是公司全称。
    """
    n = normalize_name(name)
    return any(n.endswith(s) for s in _SUFFIXES)


def is_full_company_name(name: str) -> bool:
    """这个名字是不是带企业形式词的全称（「…有限公司」）。

    用来挑「建议统一成哪一种写法」：裸字号不是正式全称，
    让用户统一成裸字号是错的建议。
    """
    n = normalize_name(name)
    return any(n.endswith(s) for s in _ENTERPRISE_SUFFIXES)


def _is_bare_字号(name: str) -> bool:
    """这个写法是裸字号（没有公司形式词）。"""
    return not _has_form_word(name)


def same_entity(a: str, b: str) -> bool:
    """两个名称是否指向同一主体。

    核心字号相等即同一主体。此外两种关系也算：
    - 互为**后缀**且多出来的部分不含字号级连接词、也不是行政区划：
      带连接词前缀的同一写法与干净写法
      （「由北京华信科技」）。多出来的若是「联合」「和」这类字号常用字
      （「联合网络通信」之于「网络通信」），或是一段行政区划
      （「上海华为技术有限公司」之于「华为技术有限公司」），
      或是一段国家前缀（「中国联合网络通信集团」之于「联合网络通信」），
      则不是同一主体
    - 互为**前缀**且较短一方是**裸字号**：不超过 3 个字，或以行政区划开头，
      且不以行业词结尾（否则是经营范围不同，不是简称）

    前缀关系只对裸字号成立。两个**全称**的核心字号一短一长，
    是两家公司（「北京华信集团有限公司」与「北京华信科技有限公司」：
    集团是母公司的形式词，剥掉之后与简称同形，但它们不是一家）。

    裸字号在文档里指向哪一家要看上下文，这个判定在 group_variants 里做；
    这里只回答「有没有可能是同一家」。
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
    if longer.startswith(shorter):
        short_name = a if canonical_core(a) == shorter else b
        if _is_bare_字号(short_name) and _is_plausible_short_form(shorter):
            return True
    return False


def _is_short_form_of(bare: str, other: str) -> bool:
    """裸字号 bare 可能是 other 的简称吗。"""
    cb, co = canonical_core(bare), canonical_core(other)
    if not cb or not co:
        return False
    if cb == co:
        return True
    if co.startswith(cb):
        return True
    if co.endswith(cb) and _extra_head_is_clean(co, cb):
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
    """成员去连接词后的规范写法，按首次出现排序。"""
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
    - canonicals 去掉连接词前缀后的写法集合。同一写法只算一种，
                 用来判断「同一主体是否出现了多种写法」——
                 「与上海远大信息技术有限公司」和「上海远大信息技术有限公司」
                 规范写法相同，不算两种写法
    - core       规范核心字号（canonical_core），与 entities.names 里的 core
                 同一个口径

    先按规范核心字号精确分组，再按显式的、顺序无关的规则跨组合并：
    两组之间每一对名字都互为同一主体时才合并。

    **裸字号**（没有公司形式词的写法，如「北京华信」）单独处理：
    它只有一种含义时才是简称，候选不唯一时它谁也不代表——
    「北京华信」在「北京华信集团有限公司」与「北京华信科技有限公司」
    同时出现时指的是哪一家，文档本身没有依据。把它并进任何一家都是
    编造依据，因此它单独成组。
    """
    unique = list(dict.fromkeys(names))
    order = {n: i for i, n in enumerate(unique)}

    def sort_key(n: str) -> tuple:
        return (canonical_core(n), canonical_name(n), n)

    full = [n for n in unique if _has_form_word(n)]
    bare = [n for n in unique if not _has_form_word(n)]

    buckets: dict[str, list[str]] = {}
    for n in sorted(full, key=sort_key):
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

    # 裸字号：只有唯一候选时才并入
    for b in sorted(bare, key=lambda n: order[n]):
        cands = []
        if _is_plausible_short_form(canonical_core(b)):
            cands = [
                g for g in groups
                if any(_is_short_form_of(b, m) for m in g["names"])
            ]
        if len(cands) == 1:
            target = cands[0]
            merged = sorted(target["names"] + [b], key=lambda n: order[n])
            target["names"] = merged
            target["canonicals"] = _canonicals(merged)
        else:
            # 没有候选或有多个候选：它谁也不代表，单独成组（不能凭空消失）
            groups.append({
                "core": canonical_core(b),
                "names": [b],
                "canonicals": _canonicals([b]),
            })

    for g in groups:
        g["core"] = max((canonical_core(n) for n in g["names"]), key=len)
    groups.sort(key=lambda g: g["core"])
    return groups
