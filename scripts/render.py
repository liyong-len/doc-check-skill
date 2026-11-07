"""阶段③：把 consistency.json 与 findings.json 渲染为单文件 HTML 报告。

用法：
    python scripts/render.py --work .doc-check-work --out report.html [--baseline prev.json]
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import fmt_value, force_utf8_stdio, read_json, write_json
from labels import (
    category_label,
    confidence_label,
    detector_label,
    locator_type_label,
)
from report_style import CSS
from schema import derive_ids, validate_findings

SEVERITY_ORDER = ["P0", "P1", "P2", "P3"]

# last-findings.json 的格式版本。旧版本没有这个键，也没有确定性层的问题，
# 与它对比时不能把今天跑出来的确定性问题说成「新增」。
BASELINE_FORMAT_VERSION = 2


def esc(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def _file_label(file_id: str) -> str:
    """文件在报告里的显示名。

    file 字段是文件标识，不只是文件名：不同目录下的两个 report.docx
    会被分配成 a/report.docx 与 b/report.docx，靠它区分。
    显示时原样给出——相对路径正是区分它们的依据，截成文件名就把
    两份文档又混成了一份。
    """
    return str(file_id or "")


def _locator_text(loc: dict) -> str:
    if not isinstance(loc, dict):
        return ""
    t = loc.get("type", "")
    parts = []
    if loc.get("section_path"):
        parts.append(str(loc["section_path"]))
    if "index" in loc:
        parts.append(f"段序 {loc['index']}")
    if "row" in loc:
        parts.append(f"表第 {loc['row']} 行")
    if "col" in loc:
        parts.append(f"第 {loc['col']} 列")
    if parts:
        return " / ".join(parts)
    # 没有更细的位置时显示位置类型的中文名，不显示 file / paragraph 这类英文枚举
    return locator_type_label(t)


def _severity(f: dict) -> str:
    """取问题级别。非法或缺失的级别归入 P3，保证各处显示与总数一致。"""
    sev = f.get("severity")
    return sev if sev in SEVERITY_ORDER else "P3"


def _issue_list(container: dict, key: str) -> list:
    """取一组问题。字段缺失或为 null 时返回空列表，不得抛 TypeError。

    consistency.json 与基线 JSON 都可能被人手改过，某个列表字段写成 null
    不该让整个渲染崩掉。
    """
    value = container.get(key)
    return value if isinstance(value, list) else []


def _issue_card(f: dict) -> str:
    sev = _severity(f)
    loc = f.get("locator") or {}
    if not isinstance(loc, dict):
        loc = {}
    extra = ""
    if loc.get("abbreviation"):
        # 缩写类 finding 的判别信息在 locator 里，quote 为空
        extra = f" · 缩写 {esc(loc['abbreviation'])}"
    quote = f.get("quote", "")
    # 引文就是有问题的那一段，用 <mark> 把它标出来（规范 §8.2 §3
    # 「原文摘录并在问题片段处高亮」）。不能只靠 .quote 的底色，
    # 那样整块都是底色，等于没有标出片段。
    quote_html = f'<div class="quote"><mark>{esc(quote)}</mark></div>' if quote else ""
    return (
        f'<div class="issue {esc(sev)}">'
        f'<div><span class="badge {esc(sev)}">{esc(sev)}</span>'
        f'<span class="tag">{esc(category_label(f.get("category")))}</span>'
        f'<span class="tag">{esc(detector_label(f.get("detector")))}</span>'
        f'<span class="tag">{esc(confidence_label(f.get("confidence")))}</span></div>'
        f'<div class="loc">{esc(_file_label(f.get("file", "")))} · {esc(_locator_text(loc))}{extra}</div>'
        f'{quote_html}'
        f'<div>{esc(f.get("description", ""))}</div>'
        f'<div class="fix">建议：{esc(f.get("suggestion", ""))}</div>'
        f"</div>"
    )


def _table(headers: list[str], rows: list[list[str]]) -> str:
    """渲染表格。rows 的每个单元格按已转义的 HTML 处理，调用方需自行 esc()。"""
    if not rows:
        return '<p class="muted">无</p>'
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    trs = []
    for r in rows:
        trs.append("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
    return f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(trs)}</tbody></table>"


def _count_severity(issues: list[dict]) -> dict[str, int]:
    """按级别统计问题数。非法级别归入 P3，保证总数与逐级显示一致。"""
    counts = {s: 0 for s in SEVERITY_ORDER}
    for f in issues:
        counts[_severity(f)] += 1
    return counts


def _manifest_with_entities(manifest: dict, consistency: dict) -> dict:
    """补全 manifest 里每个文档的主体名，返回 manifest 的副本。

    阶段①目前不把主体名回写进 manifest.documents[].entities，该字段恒为空；
    真正的主体名在 consistency.entities.per_file 里（有重复项，按出现顺序去重）。
    不补的话 §0 的「推断出的主体名」列与 §3 的主体名摘要永远显示「未识别」。
    """
    per_file = (consistency.get("entities") or {}).get("per_file") or {}
    documents = []
    for d in manifest.get("documents", []):
        doc = dict(d)
        if not doc.get("entities"):
            names: list[str] = []
            for n in per_file.get(doc.get("file", ""), []):
                if n not in names:
                    names.append(n)
            doc["entities"] = names
        documents.append(doc)
    out = dict(manifest)
    out["documents"] = documents
    return out


def _section_0(manifest: dict) -> str:
    rows = []
    for d in manifest.get("documents", []):
        st = d.get("stats", {})
        rows.append([
            esc(_file_label(d.get("file", ""))),
            esc(d.get("type", "")),
            esc(st.get("pages", 0)),
            esc(st.get("words", 0)),
            esc(st.get("paragraphs", 0)),
            esc(st.get("tables", 0)),
            esc("、".join(d.get("entities", [])) or "未识别"),
            esc(d.get("sha256", "")[:12]),
        ])
    out = [f"<h2 id='s0'>§0 检查范围与未能检查项</h2>"]
    out.append(_table(
        ["文件", "类型", "页数", "字数", "段落", "表格", "推断出的主体名", "SHA256 前缀"],
        rows,
    ))
    fails = manifest.get("failures", [])
    if fails:
        out.append("<h3>未能检查的文件</h3>")
        out.append(_table(
            ["文件", "原因"],
            [[esc(_file_label(f.get("file", ""))), esc(f.get("reason", ""))]
             for f in fails],
        ))
    else:
        out.append("<p>全部文件均已完成检查。</p>")
    return "".join(out)


def _section_1(consistency, findings, counts) -> str:
    all_issues = _issue_list(consistency, "issues") + list(findings)
    total = sum(counts.values()) or 1
    bars = []
    for s in SEVERITY_ORDER:
        w = int(counts[s] / total * 220)
        bars.append(
            f'<div style="margin:4px 0"><span class="badge {s}">{s}</span>'
            f'<span class="bar" style="width:{w}px"></span> {counts[s]}</div>'
        )
    cats: dict[str, int] = {}
    for f in all_issues:
        key = category_label(f.get("category"))
        cats[key] = cats.get(key, 0) + 1
    cat_rows = [[esc(k), str(v)] for k, v in sorted(cats.items(), key=lambda kv: -kv[1])]
    file_counts: dict[str, int] = {}
    for f in all_issues:
        key = f.get("file", "")
        file_counts[key] = file_counts.get(key, 0) + 1

    entity_names = consistency.get("entities", {}).get("names", [])
    todo = [f for f in all_issues if f.get("category") == "待补充内容"]
    # 两个粒度不同的类别不能相加：确定性层报的是「这个文件有多个主体」，
    # 语义层报的是「这一句里的名字不对」。同一个文件同时命中两层时，
    # 相加会让读者以为有两个独立的混主体问题。
    mixed_file = sum(1 for f in all_issues if f.get("category") == "主体串写")
    mixed_para = sum(1 for f in all_issues if f.get("category") == "主体名误用")

    out = [f"<h2 id='s1'>§1 结论概览</h2>"]
    out.append('<div class="counts">')
    for s in SEVERITY_ORDER:
        out.append(f"<div><span class='badge {s}'>{s}</span><b>{counts[s]}</b></div>")
    out.append("</div>")
    out.append("".join(bars))
    out.append("<h3>按类别分布</h3>")
    out.append(_table(["类别", "数量"], cat_rows))
    out.append("<h3>按文件分布</h3>")
    out.append(_table(["文件", "问题数"],
                      [[esc(k), str(v)] for k, v in sorted(file_counts.items(), key=lambda kv: -kv[1])]))
    out.append("<h3>重点提示</h3>")
    out.append(
        f"<p>识别到主体名称 {len(entity_names)} 个，"
        f"疑似混主体（文件级）{mixed_file} 处，"
        f"主体名误用（段落级）{mixed_para} 处，"
        f"待补充内容 {len(todo)} 处。</p>"
    )
    return "".join(out)


def _section_2(consistency, findings) -> str:
    hard = [f for f in _issue_list(consistency, "issues") + list(findings)
            if _severity(f) in ("P0", "P1")]
    hard.sort(key=lambda f: (_severity(f), f.get("file", "")))
    out = ["<h2 id='s2'>§2 硬伤速览（P0 / P1）</h2>"]
    if not hard:
        out.append("<p>未发现 P0 或 P1 级问题。</p>")
        return "".join(out)
    rows = []
    for f in hard:
        loc = _locator_text(f.get("locator", {}))
        rows.append([
            f'<span class="badge {esc(_severity(f))}">{esc(_severity(f))}</span>',
            esc(_file_label(f.get("file", ""))),
            esc(loc),
            esc(f.get("description", "")),
        ])
    out.append(_table(["级别", "文件", "位置", "问题"], rows))
    return "".join(out)


def _section_3(consistency, findings, manifest) -> str:
    by_file: dict[str, list[dict]] = {}
    for f in _issue_list(consistency, "issues") + list(findings):
        by_file.setdefault(f.get("file", ""), []).append(f)
    out = ["<h2 id='s3'>§3 按文件明细</h2>"]
    if not by_file:
        out.append("<p>未发现问题。</p>")
        return "".join(out)
    for fname in sorted(by_file):
        items = by_file[fname]
        out.append(
            f"<details open><summary>{esc(_file_label(fname))}"
            f"（{len(items)} 个问题）</summary>"
        )
        out.append(_file_summary(manifest, fname))
        groups: dict[str, list[dict]] = {}
        for f in items:
            groups.setdefault(category_label(f.get("category")), []).append(f)
        for cat in sorted(groups):
            out.append(f"<h3>{esc(cat)}（{len(groups[cat])}）</h3>")
            for f in groups[cat]:
                out.append(_issue_card(f))
        out.append("</details>")
    return "".join(out)


def _file_summary(manifest: dict, fname: str) -> str:
    """文件摘要：规模、结构、主体名。

    风格指纹是全文口径，出现在 §4.1，不在每个文件里重复。
    """
    doc = next(
        (d for d in manifest.get("documents", []) if d.get("file") == fname),
        None,
    )
    if not doc:
        return ""
    st = doc.get("stats", {})
    bits = [
        f"规模：{st.get('words', 0)} 字 / {st.get('paragraphs', 0)} 段 / {st.get('tables', 0)} 表",
        f"结构：{st.get('tables', 0)} 表 / {st.get('rows', 0)} 行 / {st.get('sheets', 0)} 个工作表",
    ]
    # 主体名来自文档内容，必须转义后输出
    names = doc.get("entities", [])
    bits.append("主体名：" + esc("、".join(names) if names else "未识别"))
    return f'<div class="muted">{"　｜　".join(bits)}</div>'


_LIMITATION = (
    "本工具仅做文档内互查，未核实外部事实。企业名称是否真实存在、"
    "引用文献是否真实存在、法规是否现行有效，均需人工核实；"
    "相关结论已标注「疑似 · 需人工核实」。"
)


_STYLE_CATEGORIES = ("字体一致性", "段落格式一致性")
_CONVENTION_CATEGORIES = (
    "标题层级体例", "图表题注体例", "表格体例", "列表与编号",
    "引用标记", "数字与单位", "主体名称",
)


def _section_4(consistency: dict) -> str:
    out = ["<h2 id='s4'>§4 一致性差异</h2>"]
    profile = consistency.get("style_profile", {})
    issues = _issue_list(consistency, "issues")

    out.append("<h3>4.1 样式主流值</h3>")
    if profile:
        rows = []
        for key, v in profile.items():
            rows.append([
                esc(v.get("label", key)),
                # 主流值可能是 None（这一项多数段落没设置）。空单元格读起来
                # 像坏掉的表格，写「未设置」才是事实。
                esc(fmt_value(v.get("dominant"))),
                esc(v.get("count", 0)),
                esc(v.get("total", 0)),
            ])
        out.append(_table(["项目", "主流值", "出现次数", "统计段落数"], rows))
    else:
        out.append("<p class='muted'>无可统计的样式数据（文档可能不含结构化样式）。</p>")

    out.append("<h3>4.2 样式偏离明细</h3>")
    style_issues = [i for i in issues if i.get("category") in _STYLE_CATEGORIES]
    if style_issues:
        out.append(_table(
            ["文件", "位置", "项目", "原文摘录", "说明"],
            [[esc(_file_label(i.get("file", ""))), esc(_locator_text(i.get("locator", {}))),
              esc(category_label(i.get("category"))), esc(i.get("quote", "")),
              esc(i.get("description", ""))] for i in style_issues],
        ))
    else:
        out.append("<p class='muted'>未发现样式偏离。</p>")

    out.append("<h3>4.3 体例差异</h3>")
    conv_issues = [i for i in issues if i.get("category") in _CONVENTION_CATEGORIES]
    if conv_issues:
        out.append(_table(
            ["文件", "类别", "问题"],
            [[esc(_file_label(i.get("file", ""))), esc(category_label(i.get("category"))),
              esc(i.get("description", ""))] for i in conv_issues],
        ))
    else:
        out.append("<p class='muted'>未发现体例差异。</p>")

    entities = consistency.get("entities", {})
    names = entities.get("names", [])
    out.append("<h3>4.4 主体名分布与写法变体</h3>")
    if names:
        out.append(_table(
            ["主体名", "核心字号", "出现次数", "涉及文件"],
            [[esc(n.get("name", "")), esc(n.get("core", "")), esc(n.get("count", 0)),
              esc("、".join(n.get("files", [])))] for n in names],
        ))
    else:
        out.append("<p class='muted'>未识别到公司类名称。</p>")
    variants = entities.get("variants", [])
    # 按**规范写法**判定变体，不能按原始写法：
    # 「与上海远大信息技术有限公司」与「上海远大信息技术有限公司」
    # 规范写法相同，确定性检查刻意视为同一种写法，这里若按原始写法
    # 就会报出一条与检查结论相矛盾的「写法变体」。
    multi = [
        v for v in variants
        if len(v.get("canonicals") or v.get("names", [])) > 1
    ]
    if multi:
        out.append(_table(
            ["核心字号", "写法变体"],
            [[esc(v.get("core", "")),
              esc("、".join(v.get("canonicals") or v.get("names", [])))]
             for v in multi],
        ))
    else:
        out.append("<p class='muted'>未发现同一主体的多种写法。</p>")
    return "".join(out)


def _section_5(findings: list[dict], depth: str = "",
               deterministic_issues: list[dict] | None = None) -> str:
    todo = [f for f in findings if f.get("category") == "待补充内容"]
    # 需人工核实项必须覆盖两层：确定性层的 P0 主体串写也是「疑似」，
    # 只筛模型侧会让 §5 印出「无。」而同一个 P0 在 §2/§3 里挂着。
    verify = [f for f in list(findings) + list(deterministic_issues or [])
              if f.get("confidence") == "疑似 · 需人工核实"]
    out = ["<h2 id='s5'>§5 待补充与待核实</h2>"]
    out.append("<h3>待补充内容</h3>")
    if todo:
        out.append(_table(
            ["☐", "文件", "位置", "缺失内容", "为何需要", "建议"],
            [["☐", esc(_file_label(f.get("file", ""))), esc(_locator_text(f.get("locator", {}))),
              esc(f.get("quote", "")), esc(f.get("description", "")),
              esc(f.get("suggestion", ""))] for f in todo],
        ))
    elif depth == "quick":
        out.append("<p class='muted'>本次档位为 quick，未覆盖「待补充内容」这一类别。</p>")
    else:
        out.append("<p class='muted'>未发现待补充内容。</p>")
    out.append("<h3>需人工核实项</h3>")
    if verify:
        out.append(_table(
            ["☐", "文件", "位置", "问题", "为何需要", "建议"],
            [["☐", esc(_file_label(f.get("file", ""))), esc(_locator_text(f.get("locator", {}))),
              esc(f.get("quote", "")), esc(f.get("description", "")),
              esc(f.get("suggestion", ""))] for f in verify],
        ))
    else:
        out.append("<p class='muted'>无。</p>")
    return "".join(out)


def _file_state(row: dict) -> str:
    """判断一个文件相对上次基线的状态。"""
    state = row.get("state")
    if state in ("added", "removed", "modified", "unchanged"):
        return state
    old = row.get("old_sha", "")
    new = row.get("new_sha", "")
    if not old and new:
        return "added"
    if old and not new:
        return "removed"
    return "modified" if old != new else "unchanged"


def _section_6(baseline_diff: dict) -> str:
    if not baseline_diff:
        return ""
    fd = baseline_diff.get("findings", {})
    out = ["<h2 id='s6'>§6 复查对比</h2>"]
    if baseline_diff.get("baseline_old_format"):
        # 旧格式的基线里没有确定性层的问题，它与今天的确定性层无从对比。
        # 把今天跑出来的确定性问题说成「新增」是在这一章里说假话，
        # 必须写明这一章只覆盖了语义层。
        out.append(
            "<div class='limit'>基线来自旧版本格式，确定性层问题无法对比。"
            "下面的「新增 / 已修复 / 未修复」只覆盖语义层（findings）的问题，"
            "确定性层的问题请看 §3 与 §4。</div>"
        )
    rows = baseline_diff.get("files", [])
    modified = [r.get("file", "") for r in rows if _file_state(r) == "modified"]
    added = [r.get("file", "") for r in rows if _file_state(r) == "added"]
    removed = [r.get("file", "") for r in rows if _file_state(r) == "removed"]
    if modified:
        out.append(
            "<div class='limit'>以下文件已修改，部分对比结果可能不适用："
            + esc("、".join(modified))
            + "</div>"
        )
    if added:
        out.append(
            "<div class='limit'>以下文件为本次新增，没有上次基线可比："
            + esc("、".join(added))
            + "</div>"
        )
    if removed:
        out.append(
            "<div class='limit'>以下文件已删除，本次不再检查，其上次的基线不再适用："
            + esc("、".join(removed))
            + "</div>"
        )
    for title, key in (("新增问题", "new"), ("已修复问题", "fixed"), ("未修复问题", "unchanged")):
        items = fd.get(key, [])
        out.append(f"<h3>{title}（{len(items)}）</h3>")
        if items:
            out.append(_table(
                ["级别", "文件", "位置", "类别", "问题"],
                [[f'<span class="badge {esc(_severity(f))}">{esc(_severity(f))}</span>',
                  esc(_file_label(f.get("file", ""))), esc(_locator_text(f.get("locator", {}))),
                  esc(category_label(f.get("category"))), esc(f.get("description", ""))]
                 for f in items],
            ))
        else:
            out.append("<p class='muted'>无</p>")
    return "".join(out)


_RULES = [
    ("字体一致性", "字体、字号与全文主流值不一致的段落"),
    ("段落格式一致性", "行距、缩进、对齐、段间距与主流值不一致的段落"),
    ("标题层级体例", "同一层级内标题编号写法混用、标题层级跳级"),
    ("图表题注体例", "同一文件内图表题注写法混用、图与表编号缺号"),
    ("表格体例", "各表首行的加粗写法不统一"),
    ("主体名称", "同一主体出现多种名称写法"),
    ("主体串写", "同一文件内出现多个不同主体名称（确定性层，文件级 P0）"),
    ("主体名误用", "段落或句子中出现了疑似属于另一主体的名称、地址、资质、业绩或联系方式（语义层，段落级）"),
    ("数字与单位", "货币单位、日期格式混用"),
    ("引用标记", "引用标记写法混用"),
    ("列表与编号", "有序列表编号方式混用"),
    ("术语与缩写", "缩写首次出现未给出全称"),
    ("错别字用词", "错别字、形近词误用"),
    ("标点格式", "标点与空格使用不规范"),
    ("前后矛盾", "同一事实在文档两处描述冲突"),
    ("引用张冠李戴", "引用处语境与被引内容主题不符"),
    ("待补充内容", "缺失数据、空白字段、应附材料"),
    ("数字逻辑", "合计与分项不符、比例关系不成立"),
    ("表述不清", "表述不清或语义歧义"),
    ("术语一致性", "同义异形术语混用"),
]


_DEPTH_COVERAGE = {
    "quick": "阶段①全量确定性检查（含主体串写、主体名称、字体与体例检查）已做；"
             "阶段②只做了错别字与标点扫描。"
             "未做语义互查：前后矛盾、主体名误用、引用张冠李戴、待补充内容、"
             "数字逻辑、表述不清、术语一致性等类别本次未覆盖。",
    "standard": "阶段①全量确定性检查 + 阶段②九类语义检查全做。",
    "deep": "阶段①全量确定性检查 + 阶段②逐段细读，邻接窗口更大，跨片对照加强。",
}


def _section_7(manifest: dict) -> str:
    out = ["<h2 id='s7'>§7 附录</h2>"]
    depth = manifest.get("depth", "")
    out.append("<h3>本次检查范围</h3>")
    out.append(_table(
        ["项目", "内容"],
        [
            ["检查档位", esc(depth or "未知")],
            ["覆盖范围", esc(_DEPTH_COVERAGE.get(
                depth, "未知档位，请核对 scripts/chunk.py 的 DEPTH_PARAMS。"))],
        ],
    ))
    out.append("<h3>检查规则与判定标准</h3>")
    out.append(_table(["类别", "判定标准"], [[esc(a), esc(b)] for a, b in _RULES]))
    out.append("<h3>文件指纹</h3>")
    out.append(_table(
        ["文件", "SHA256"],
        [[esc(_file_label(d.get("file", ""))), esc(d.get("sha256", ""))]
         for d in manifest.get("documents", [])],
    ))
    return "".join(out)


def build_html(data: dict) -> str:
    manifest = data.get("manifest", {})
    consistency = data.get("consistency", {})
    findings = data.get("findings", [])
    baseline_diff = data.get("baseline_diff")

    counts = _count_severity(_issue_list(consistency, "issues") + list(findings))
    manifest = _manifest_with_entities(manifest, consistency)

    toc = [
        ("§0 检查范围", "s0"),
        ("§1 结论概览", "s1"),
        ("§2 硬伤速览", "s2"),
        ("§3 按文件明细", "s3"),
        ("§4 一致性差异", "s4"),
        ("§5 待补充与待核实", "s5"),
    ]
    if baseline_diff:
        toc.append(("§6 复查对比", "s6"))
    toc.append(("§7 附录", "s7"))

    nav = "".join(f"<a href='#{i}'>{t}</a>" for t, i in toc)

    body = "".join([
        _section_0(manifest),
        _section_1(consistency, findings, counts),
        _section_2(consistency, findings),
        _section_3(consistency, findings, manifest),
        _section_4(consistency),
        _section_5(findings, manifest.get("depth", ""), _issue_list(consistency, "issues")),
        _section_6(baseline_diff),
        _section_7(manifest),
    ])

    return (
        "<!DOCTYPE html>\n"
        "<html lang='zh-CN'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>文档检查报告</title>"
        f"<style>{CSS}</style></head><body><div class='wrap'>"
        "<header class='top'>"
        "<h1>文档检查报告</h1>"
        f"<div class='sub'>生成时间 {esc(manifest.get('generated_at', ''))} ｜ "
        f"检查深度 {esc(manifest.get('depth', ''))} ｜ "
        f"脚本版本 {esc(manifest.get('script_version', ''))}</div>"
        f"<div class='banner'>共 {sum(counts.values())} 个问题："
        f"P0 {counts['P0']} ｜ P1 {counts['P1']} ｜ P2 {counts['P2']} ｜ P3 {counts['P3']}</div>"
        "</header>"
        f"<nav class='toc'>{nav}</nav>"
        f"{body}"
        f"<div class='limit'><b>能力边界</b><br>{esc(_LIMITATION)}</div>"
        "</div></body></html>"
    )


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(2)


def _read_json_or_fail(path: Path, what: str, hint: str = "") -> object:
    """读 JSON 并给出中文错误提示。文件缺失或格式非法时以退出码 2 结束。"""
    try:
        return read_json(path)
    except FileNotFoundError:
        _fail(f"缺少 {what}：{path}。{hint}")
    except json.JSONDecodeError as exc:
        _fail(f"{what} 不是合法的 JSON：{path}（{exc}）。")
    except UnicodeDecodeError:
        _fail(f"{what} 不是 UTF-8 文本：{path}。")
    return {}


def _read_dict_or_fail(path: Path, what: str, hint: str = "") -> dict:
    data = _read_json_or_fail(path, what, hint)
    if not isinstance(data, dict):
        _fail(f"{what} 应当是一个 JSON 对象：{path}。")
    return data


def _baseline_format_version(prev: dict) -> int:
    """基线 JSON 的格式版本。没有这个键的就是旧格式（版本 0）。"""
    try:
        return int(prev.get("format_version", 0))
    except (TypeError, ValueError):
        return 0


def _baseline_has_det_layer(prev: dict) -> bool:
    """基线里有没有确定性层的问题。

    确定性层的问题要能被对比，基线里必须带着它们。本版本写出的基线
    带 format_version 标记，也带 issues 数组；早于这个标记的旧基线
    只带 findings（有的连 issues 键都没有），拿它对比确定性层只会得到
    「今天跑出来的确定性问题全是新增」——文档一个字没改也不该这么说。
    """
    if "issues" in prev:
        return True
    return _baseline_format_version(prev) >= BASELINE_FORMAT_VERSION


def render(work: Path, out: Path, baseline: Path | None = None) -> Path:
    work = Path(work)
    prepare_hint = "请先运行 scripts/prepare.py 生成工作目录。"
    manifest = _read_dict_or_fail(work / "manifest.json", "manifest.json", prepare_hint)
    consistency = _read_dict_or_fail(work / "consistency.json", "consistency.json", prepare_hint)

    findings_path = work / "findings.json"
    findings: list = []
    if findings_path.exists():
        findings = _read_json_or_fail(findings_path, "findings.json", prepare_hint)
    errors = validate_findings(findings)
    if errors:
        for e in errors:
            print(f"findings.json 校验失败：{e}", file=sys.stderr)
        raise SystemExit(2)
    # id 是派生字段，渲染器自己算。合同（content-rules.md 的写作要求）
    # 从没要求模型写它，缺 id 的 findings.json 不是错误。
    findings = derive_ids(findings)

    baseline_diff = None
    if baseline is not None:
        from baseline import diff_findings, diff_manifests

        prev = _read_dict_or_fail(Path(baseline), "基线文件")
        # 复查对比必须覆盖**两层**：模型写的 findings 与确定性层的 issues。
        # 只比模型侧，新出现的 P0 混主体会在 §2/§3 显示却不被计入 §6，
        # 等于在专门用来追踪变化的章节里说了假话。
        old_format = not _baseline_has_det_layer(prev)
        current_all = list(findings) + _issue_list(consistency, "issues")
        prev_all = _issue_list(prev, "findings") + _issue_list(prev, "issues")
        if old_format:
            # 旧格式的基线里没有确定性层的问题（连 issues 键都没有）。
            # 拿今天的确定性问题去和它比，只会得到「全部新增」——
            # 文档一个字没改也说它新增了 7 个问题。
            # 与其说假话，不如只比语义层，并在 §6 里写明这件事。
            current_all = list(findings)
            prev_all = _issue_list(prev, "findings")
        baseline_diff = {
            "findings": diff_findings(current_all, prev_all),
            "files": diff_manifests(manifest, prev.get("manifest") or {}),
            "baseline_old_format": old_format,
        }

    html_text = build_html({
        "manifest": manifest,
        "consistency": consistency,
        "findings": findings,
        "baseline_diff": baseline_diff,
    })

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text, encoding="utf-8")

    write_json(work / "last-findings.json", {
        "format_version": BASELINE_FORMAT_VERSION,
        "generated_at": manifest.get("generated_at", ""),
        "findings": findings,
        "issues": _issue_list(consistency, "issues"),
        "manifest": manifest,
    })
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="doc-check 阶段③：渲染 HTML 报告")
    parser.add_argument("--work", default=".doc-check-work", help="工作目录")
    parser.add_argument("--out", default="report.html", help="输出 HTML 路径")
    parser.add_argument("--baseline", default=None, help="上次运行的 last-findings.json")
    args = parser.parse_args(argv)

    force_utf8_stdio()
    out = render(Path(args.work), Path(args.out),
                 Path(args.baseline) if args.baseline else None)
    print(f"报告已生成：{out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
