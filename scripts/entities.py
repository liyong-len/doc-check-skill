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
#
# 省级行政区之外，地级市与计划单列市也要在列：简称规则靠它判断
# 「像不像简称」（「北京华信」像简称，「深圳华信」以前不像），
# 通用片段规则也靠它判断名字是不是「只有行业词」——
# 两处规则对城市一视同仁，不能只认直辖市。
_REGIONS = [
    "内蒙古自治区", "内蒙古", "黑龙江", "新疆维吾尔自治区", "新疆", "西藏",
    "宁夏回族自治区", "宁夏", "青海", "甘肃", "陕西", "山西", "河北", "河南",
    "湖南", "湖北", "安徽", "浙江", "江苏", "山东", "江西", "福建", "广东",
    "海南", "四川", "贵州", "云南", "辽宁", "吉林", "北京", "上海", "天津",
    "重庆", "台湾", "香港", "澳门",
    # 计划单列市
    "深圳", "大连", "青岛", "宁波", "厦门",
    # 地级市
    "石家庄", "唐山", "秦皇岛", "邯郸", "保定", "张家口", "承德", "廊坊",
    "沧州", "邢台", "衡水", "太原", "大同", "长治", "晋城", "临汾", "运城",
    "鞍山", "抚顺", "丹东", "锦州", "营口", "阜新", "盘锦", "铁岭",
    "四平", "通化", "延边", "齐齐哈尔", "大庆", "牡丹江", "佳木斯",
    "南京", "无锡", "徐州", "常州", "苏州", "南通", "连云港", "淮安",
    "盐城", "扬州", "镇江", "泰州", "宿迁", "杭州", "温州", "嘉兴",
    "湖州", "绍兴", "金华", "衢州", "舟山", "台州", "丽水", "合肥",
    "芜湖", "蚌埠", "福州", "泉州", "漳州", "南平", "三明", "龙岩",
    "南昌", "九江", "赣州", "宜春", "上饶", "吉安", "抚州", "萍乡",
    "济南", "烟台", "潍坊", "淄博", "临沂", "济宁", "泰安", "威海",
    "德州", "聊城", "滨州", "菏泽", "枣庄", "日照", "郑州", "洛阳",
    "开封", "南阳", "新乡", "许昌", "焦作", "平顶山", "安阳", "商丘",
    "信阳", "周口", "驻马店", "武汉", "宜昌", "襄阳", "荆州", "黄石",
    "十堰", "鄂州", "孝感", "荆门", "咸宁", "黄冈", "长沙", "株洲",
    "湘潭", "衡阳", "邵阳", "岳阳", "常德", "益阳", "郴州", "永州",
    "成都", "绵阳", "德阳", "自贡", "攀枝花", "泸州", "乐山", "眉山",
    "南充", "宜宾", "广元", "达州", "贵阳", "遵义", "安顺", "毕节",
    "昆明", "大理", "曲靖", "玉溪", "保山", "南宁", "柳州", "桂林",
    "梧州", "北海", "钦州", "防城港", "玉林", "百色", "贺州", "崇左",
    "海口", "三亚", "儋州", "乌鲁木齐", "克拉玛依", "喀什", "阿克苏",
    "吐鲁番", "哈密", "兰州", "天水", "白银", "酒泉", "庆阳", "西安",
    "咸阳", "宝鸡", "渭南", "汉中", "延安", "银川",
    "石嘴山", "吴忠", "固原", "西宁", "海东", "格尔木", "呼和浩特",
    "包头", "赤峰", "通辽", "鄂尔多斯", "呼伦贝尔", "巴彦淖尔",
    "乌兰察布", "拉萨", "日喀则", "林芝", "昌都",
    "中山", "东莞", "佛山", "珠海", "惠州", "汕头", "湛江", "江门",
    "茂名", "肇庆", "清远", "韶关", "河源", "阳江", "云浮", "潮州",
    "揭阳", "汕尾", "台北", "高雄",
]

# 连接词分两类。
#
# 强连接词是句子层面的标记，其后几乎必然是字号，可以裁掉前缀：
#   「本项目由北京华信科技有限公司」「甲方及乙方共同委托…」
#
# 切分连接词同时也是字号里常见的字——「和而泰」「中国联合」「清华同方」
# 都是真实字号的一部分。切分连接词单独出现时不能裁，否则真实公司名会被截断
# （「和而泰智能控制股份有限公司」会被截成「而泰智能控制股份有限公司」）。
#
# 它与 _CANONICAL_STRIP_CONNECTORS 是两组不同的词：这里的一组只用来判断
# 「后面是不是另一个主体的起点」，真正裁前缀的是 _CANONICAL_STRIP_CONNECTORS。
_STRONG_CONNECTORS = [
    "以及", "并且", "我方", "贵司", "双方", "各方", "甲方", "乙方", "中标人",
    "投标人", "供应商", "承包人", "采购方", "招标人", "招标代理",
    "受托", "委托", "由",
]
_SPLIT_CONNECTORS = [
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

# 在一段文字里找公司形式词（括号里的形式词不算，见 _find_suffix_outside_brackets）


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
    for conn in _SPLIT_CONNECTORS:
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


def _gap_boundary(gap: str) -> int | None:
    """名字中间那段文字里有没有「另一个主体的起点」，有的话给出它的位置。

    这段文字是「第一个公司形式词」与「同一串里更靠后的形式词」之间的内容。
    判定必须由连接词驱动，不能只靠行政区划：

    - 强连接词（由、甲方、受托…）出现在这段文字里，后面必然是新主体；
    - 弱连接词出现在这段文字的**开头**时，它就是两个主体之间的连接词
      （「北京华信科技有限公司**和**华为技术有限公司」）。字面开头的
      弱连接词是字号的一部分（「和而泰」「中国联合」「清华同方」），
      但那种写法里连接词在名字的开头，不在这段中间文字里——
      区分「连接词」与「字号的一部分」靠的是它在名字里的位置，不是字本身；
    - 弱连接词后面紧跟行政区划时也是新主体（这是行政区划信号，
      作为附加信号保留，不作为唯一判据）。
    """
    best = None
    for conn in _STRONG_CONNECTORS:
        idx = gap.find(conn)
        if idx >= 0 and (best is None or idx < best):
            best = idx
    if best is not None:
        return best
    for conn in _SPLIT_CONNECTORS:
        if gap.startswith(conn):
            return 0
    for conn in _SPLIT_CONNECTORS:
        idx = gap.find(conn)
        while idx >= 0:
            if _starts_with_region(gap[idx + len(conn):]):
                return idx
            idx = gap.find(conn, idx + 1)
    return None


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
    连接词之后开始（连接词本身不是名字的一部分）。
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
            conn = _boundary_connector(gap, boundary)
            return end, end + boundary + len(conn)
        end += found[1]
        changed = True
    return end, None


def _boundary_connector(gap: str, idx: int) -> str:
    """边界处那个连接词本身。"""
    for conn in _STRONG_CONNECTORS:
        if gap.startswith(conn, idx):
            return conn
    for conn in _SPLIT_CONNECTORS:
        if gap.startswith(conn, idx):
            return conn
    return ""


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


def extract_company_names(text: str) -> list[str]:
    """抽取公司类名称，按出现顺序去重。

    扫描是「跳到延伸后的末尾再继续」，不是 finditer 的逐个匹配：
    名字延伸过去的那截文字若被重新匹配一次，就会凭空多出半个公司名
    （「北京华信集团研究院有限公司」曾被切成「北京华信集团研究院」
    与「研究院有限公司」两个名字）。

    延伸遇到下一个主体的起点（连接词）时，名字停在第一个形式词处，
    下一个名字从连接词之后开始——「北京华信科技有限公司和华为技术有限公司」
    是两个公司，不能并成一个。
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
        end, resume = _extend_over_suffix(text, m.end())
        # 跳到延伸后的末尾，延伸过去的那截不再重新匹配
        pos = max(end, m.end())
        if resume is not None:
            pos = max(pos, resume)
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
    if any(w in head for w in _SPLIT_CONNECTORS):
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
    - 互为**后缀**且多出来的部分不含弱连接词：带连接词前缀的同一写法与干净写法
      （「由北京华信科技」）。多出来的若是「联合」「和」这类字号常用字
      （「联合网络通信」之于「网络通信」），则不是同一主体
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
