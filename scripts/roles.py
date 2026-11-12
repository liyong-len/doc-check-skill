"""段落角色：判断一个段落「是什么」，用来决定它该跟谁比格式。

**为什么需要角色**：一份中文文档里，标题是 16pt 黑体、正文是 12pt 宋体——
这是正确的排版，不是「不一致」。把所有段落混在一起算一个主流值，
标题就会因为「不是 12pt 宋体」而每一条都被报成偏离。
实测一份格式完全正确的四文档材料，按全文主流值比对报出 478 条
「字体/段落格式不一致」，其中 456 条落在标题上。

按角色分组后，同一角色内部才互相比：标题与标题比，正文与正文比。
实测同一份材料降到 2 条（那 2 条是公函体首行不缩进，确实值得看）。

**角色的判定顺序**（先命中先算）：

1. 图表题注：「表3」「图 2-1」这类题注行
2. 编号标题：第一章式 / 一、式 / 1. 式 / （一）式 / 1.1 式，
   **并记下它是否加粗**——编号相同但一个是标题、一个是正文列举项时，
   两者本就该长得不一样（「（一）重大变更：包括……」在正文里就不是标题）
3. 无编号但加粗且居中：文档标题
4. 无编号但加粗：小标题
5. 无编号但居中：题注性居中段落
6. 其余：正文

**角色是段落的「身份」，不是「样式」**：角色本身不含任何字号字体信息，
同一个角色里的段落才是可比的一群。
"""
from __future__ import annotations

import re

# 编号标题体系。层级数字沿用 analyze.py 的口径：
# 「第一章 / 一、 / 1. /（一）」是标准的四级结构。
_NUMBER_PATTERNS = (
    (re.compile(r"^第[一二三四五六七八九十百]+章"), "第一章式"),
    (re.compile(r"^[一二三四五六七八九十]+、"), "一、式"),
    (re.compile(r"^\d+[.、]\s"), "1. 式"),
    (re.compile(r"^[（(][一二三四五六七八九十]+[）)]"), "（一）式"),
    (re.compile(r"^\d+\.\d+[.、]?\s"), "1.1 式"),
)

# 图表题注：「表3」「图 2-1」「表 3-1 流程图」这类行。
#
# 序号后面若紧跟量词或量类（个/条/节/页…），那不是编号，
# 「见图 3 节」这类会被误判成题注或引用——与 analyze.py 的同一处守卫一致。
_NOT_A_NUMBER_TAIL = r"(?!\s*[个条项处次段章节份件标页类])"
_CAPTION_RE = re.compile(
    r"^[（(]?[表图]\s*\d+(?:[-－]\d+)?" + _NOT_A_NUMBER_TAIL
)

# 角色标识。用字符串而不是元组，便于直接进 JSON 与报告表格。
ROLE_CAPTION = "图表题注"
ROLE_DOC_TITLE = "文档标题"
ROLE_SUBHEADING = "小标题"
ROLE_CENTERED = "居中段落"
ROLE_LIST_ITEM = "列表项"
ROLE_BODY = "正文"

# 角色在报告里的显示名。角色标识本身是内部用的，这里给出人读的写法。
ROLE_LABELS = {
    ROLE_CAPTION: "图表题注",
    ROLE_DOC_TITLE: "文档标题",
    ROLE_SUBHEADING: "小标题",
    ROLE_CENTERED: "居中段落",
    ROLE_LIST_ITEM: "列表项",
    ROLE_BODY: "正文",
}


def _caption_role(text: str) -> str | None:
    if _CAPTION_RE.match(text):
        return ROLE_CAPTION
    return None


def paragraph_role(text: str, style: dict) -> str:
    """判断段落角色。

    text 是段落原文，style 是抽取器给出的样式字典。
    空段落（没有文字）返回空字符串——它不该参与任何比对。
    """
    stripped = (text or "").strip()
    if not stripped:
        return ""

    role = _caption_role(stripped)
    if role:
        return role

    bold = bool(style.get("bold"))
    centered = style.get("align") == "center"

    # 抽取器已经认出来的标题（Word 的标题样式）优先。
    #
    # 不看这个信号，光靠文本里的编号判断标题会漏掉一批：
    # 实测一份真实投标材料里，31 个段落用的是 Word 的标题样式
    # （「平台优势」「技术可行性分析」「软件及服务器配置」…），
    # 文本里没有编号，靠文本判断会把它们全当成正文，
    # 于是标题的段间距、缩进被拿去和正文比，报出一堆假偏离。
    level = style.get("heading_level") or 0
    if style.get("is_heading") and level > 0:
        return f"标题{level}级"

    # 列表项单独成类。
    #
    # 列表项的缩进（悬挂缩进）与段间距是由列表层级决定的，
    # 跟正文段落本来就不是一套——「富媒体专项指标（图片 / 音频 / 视频 / 卡片）」
    # 在文档里是编号列表的一级，它的左缩进 21pt、首行缩进 -21pt（悬挂），
    # 正文段落的缩进是 24pt。两者放一群里比，报出来的全是假偏离。
    # 实测一份真实投标材料，203 处样式偏离里 87 处是这个原因。
    if style.get("list_numbered"):
        return ROLE_LIST_ITEM

    for pattern, label in _NUMBER_PATTERNS:
        if pattern.match(stripped):
            # 编号段落记下加粗与否：同一个编号体系下，
            # 加粗的与不加粗的可能是两种东西（标题 vs 正文列举项），
            # 把它们混在一群里比会互相报偏离。
            return f"{label}·{'加粗' if bold else '不加粗'}"

    if bold and centered:
        return ROLE_DOC_TITLE
    if bold:
        return ROLE_SUBHEADING
    if centered:
        return ROLE_CENTERED
    return ROLE_BODY


def role_label(role: str) -> str:
    """角色标识转成报告里显示的名字。"""
    if not role:
        return "空段落"
    if role in ROLE_LABELS:
        return ROLE_LABELS[role]
    return role


def role_sort_key(role: str) -> tuple:
    """角色排序：先按结构层级，再按显示名。

    报告里「文档标题 → 标题 → 小标题 → 正文」这样的顺序比字母序好读。
    """
    order = {
        ROLE_DOC_TITLE: 0,
        "标题1级": 1, "标题2级": 2, "标题3级": 3, "标题4级": 4,
        "标题5级": 5, "标题6级": 6, "标题7级": 7, "标题8级": 8, "标题9级": 9,
        "第一章式·加粗": 10, "第一章式·不加粗": 11,
        "一、式·加粗": 12, "一、式·不加粗": 13,
        "1. 式·加粗": 14, "1. 式·不加粗": 15,
        "（一）式·加粗": 16, "（一）式·不加粗": 17,
        "1.1 式·加粗": 18, "1.1 式·不加粗": 19,
        ROLE_SUBHEADING: 20,
        ROLE_CAPTION: 21,
        ROLE_CENTERED: 22,
        ROLE_LIST_ITEM: 23,
        ROLE_BODY: 24,
    }
    return (order.get(role, 99), role)


# 这些样式字段在抽取器里记 None 的含义是「段落没有显式设置，继承样式里的值」。
#
# 把 None 当成一个普通取值参与主流值比对，会把「继承」判成「偏离」：
# 一段显式设了 12pt，另一段继承（渲染出来可能也是 12pt），
# 却被报成「本处为「未设置」，主流值为「12」」——这是看不见的差异，
# 读者按报告去改，改不出任何变化。
#
# indent_* 与 space_* 不在此列：抽取器已把它们归一成 0.0，
# 0.0 是真实取值（未设置缩进 = 缩进 0），可以照常参与比对。
INHERITABLE_KEYS = frozenset({
    "font_latin", "font_ea", "size_pt", "align", "line_spacing",
})


def is_comparable(style: dict, key: str) -> bool:
    """这个段落在这一项上有没有「可观测的取值」。

    False 表示这一项是继承来的，与别的段落无从比较，不参与主流值统计。
    """
    if key in INHERITABLE_KEYS and style.get(key) is None:
        return False
    return True
