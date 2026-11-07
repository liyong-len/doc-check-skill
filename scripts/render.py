"""阶段③：把 consistency.json 与 findings.json 渲染为单文件 HTML 报告。

用法：
    python scripts/render.py --work .doc-check-work --out report.html [--baseline prev.json]
"""
from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import read_json, write_json
from report_style import CSS
from schema import validate_findings

SEVERITY_ORDER = ["P0", "P1", "P2", "P3"]


def esc(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


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
    return " / ".join(parts) if parts else t


def _issue_card(f: dict) -> str:
    sev = f.get("severity", "P3")
    loc = f.get("locator", {}) or {}
    extra = ""
    if loc.get("abbreviation"):
        # 缩写类 finding 的判别信息在 locator 里，quote 为空
        extra = f" · 缩写 {esc(loc['abbreviation'])}"
    quote = f.get("quote", "")
    quote_html = f'<div class="quote">{esc(quote)}</div>' if quote else ""
    return (
        f'<div class="issue {esc(sev)}">'
        f'<div><span class="badge {esc(sev)}">{esc(sev)}</span>'
        f'<span class="tag">{esc(f.get("category", ""))}</span>'
        f'<span class="tag">{esc(f.get("detector", ""))}</span>'
        f'<span class="tag">{esc(f.get("confidence", ""))}</span></div>'
        f'<div class="loc">{esc(f.get("file", ""))} · {_locator_text(loc)}{extra}</div>'
        f'{quote_html}'
        f'<div>{esc(f.get("description", ""))}</div>'
        f'<div class="fix">建议：{esc(f.get("suggestion", ""))}</div>'
        f"</div>"
    )


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return '<p class="muted">无</p>'
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    trs = []
    for r in rows:
        trs.append("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
    return f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(trs)}</tbody></table>"


def _section_0(manifest: dict) -> str:
    rows = []
    for d in manifest.get("documents", []):
        st = d.get("stats", {})
        rows.append([
            esc(d.get("file", "")),
            esc(d.get("type", "")),
            esc(st.get("pages", 0)),
            esc(st.get("words", 0)),
            esc(st.get("paragraphs", 0)),
            esc(st.get("tables", 0)),
            esc(d.get("sha256", "")[:12]),
        ])
    out = [f"<h2 id='s0'>§0 检查范围与未能检查项</h2>"]
    out.append(_table(["文件", "类型", "页数", "字数", "段落", "表格", "SHA256 前缀"], rows))
    fails = manifest.get("failures", [])
    if fails:
        out.append("<h3>未能检查的文件</h3>")
        out.append(_table(
            ["文件", "原因"],
            [[esc(f.get("file", "")), esc(f.get("reason", ""))] for f in fails],
        ))
    else:
        out.append("<p>全部文件均已完成检查。</p>")
    return "".join(out)


def _section_1(manifest, consistency, findings) -> str:
    all_issues = list(consistency.get("issues", [])) + list(findings)
    counts = {s: 0 for s in SEVERITY_ORDER}
    for f in all_issues:
        counts[f.get("severity", "P3")] = counts.get(f.get("severity", "P3"), 0) + 1
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
        cats[f.get("category", "未分类")] = cats.get(f.get("category", "未分类"), 0) + 1
    cat_rows = [[esc(k), str(v)] for k, v in sorted(cats.items(), key=lambda kv: -kv[1])]
    file_counts: dict[str, int] = {}
    for f in all_issues:
        key = f.get("file", "")
        file_counts[key] = file_counts.get(key, 0) + 1

    entity_names = consistency.get("entities", {}).get("names", [])
    todo = [f for f in all_issues if f.get("category") == "待补充内容"]

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
        f"疑似混主体问题 {sum(1 for f in all_issues if f.get('category') == '主体串写')} 处，"
        f"待补充内容 {len(todo)} 处。</p>"
    )
    return "".join(out)


def _section_2(consistency, findings) -> str:
    hard = [f for f in list(consistency.get("issues", [])) + list(findings)
            if f.get("severity") in ("P0", "P1")]
    hard.sort(key=lambda f: (f.get("severity", "P3"), f.get("file", "")))
    out = ["<h2 id='s2'>§2 硬伤速览（P0 / P1）</h2>"]
    if not hard:
        out.append("<p>未发现 P0 或 P1 级问题。</p>")
        return "".join(out)
    rows = []
    for f in hard:
        loc = _locator_text(f.get("locator", {}))
        rows.append([
            f'<span class="badge {esc(f.get("severity", ""))}">{esc(f.get("severity", ""))}</span>',
            esc(f.get("file", "")),
            esc(loc),
            esc(f.get("description", "")),
        ])
    out.append(_table(["级别", "文件", "位置", "问题"], rows))
    return "".join(out)


def _section_3(consistency, findings) -> str:
    by_file: dict[str, list[dict]] = {}
    for f in list(consistency.get("issues", [])) + list(findings):
        by_file.setdefault(f.get("file", ""), []).append(f)
    out = ["<h2 id='s3'>§3 按文件明细</h2>"]
    if not by_file:
        out.append("<p>未发现问题。</p>")
        return "".join(out)
    for fname in sorted(by_file):
        items = by_file[fname]
        out.append(f"<details open><summary>{esc(fname)}（{len(items)} 个问题）</summary>")
        groups: dict[str, list[dict]] = {}
        for f in items:
            groups.setdefault(f.get("category", "未分类"), []).append(f)
        for cat in sorted(groups):
            out.append(f"<h3>{esc(cat)}（{len(groups[cat])}）</h3>")
            for f in groups[cat]:
                out.append(_issue_card(f))
        out.append("</details>")
    return "".join(out)


_LIMITATION = (
    "本工具仅做文档内互查，未核实外部事实。企业名称是否真实存在、"
    "引用文献是否真实存在、法规是否现行有效，均需人工核实；"
    "相关结论已标注「疑似 · 需人工核实」。"
)


def build_html(data: dict) -> str:
    manifest = data.get("manifest", {})
    consistency = data.get("consistency", {})
    findings = data.get("findings", [])
    baseline_diff = data.get("baseline_diff")

    counts = {s: 0 for s in SEVERITY_ORDER}
    for f in list(consistency.get("issues", [])) + list(findings):
        sev = f.get("severity", "P3")
        counts[sev] = counts.get(sev, 0) + 1

    toc = [
        ("§0 检查范围", "s0"),
        ("§1 结论概览", "s1"),
        ("§2 硬伤速览", "s2"),
        ("§3 按文件明细", "s3"),
    ]
    if baseline_diff:
        toc.append(("§6 复查对比", "s6"))

    nav = "".join(f"<a href='#{i}'>{t}</a>" for t, i in toc)

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
        f"{_section_0(manifest)}"
        f"{_section_1(manifest, consistency, findings)}"
        f"{_section_2(consistency, findings)}"
        f"{_section_3(consistency, findings)}"
        f"<div class='limit'><b>能力边界</b><br>{esc(_LIMITATION)}</div>"
        "</div></body></html>"
    )


def render(work: Path, out: Path, baseline: Path | None = None) -> Path:
    work = Path(work)
    manifest = read_json(work / "manifest.json")
    consistency = read_json(work / "consistency.json")
    findings_path = work / "findings.json"
    findings = read_json(findings_path) if findings_path.exists() else []
    errors = validate_findings(findings)
    if errors:
        for e in errors:
            print(f"findings.json 校验失败：{e}", file=sys.stderr)
        raise SystemExit(2)

    baseline_diff = None
    if baseline is not None:
        from baseline import diff_findings, diff_manifests

        prev = read_json(Path(baseline))
        baseline_diff = {
            "findings": diff_findings(findings, prev.get("findings", [])),
            "files": diff_manifests(manifest, prev.get("manifest", {})),
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
        "generated_at": manifest.get("generated_at", ""),
        "findings": findings,
        "manifest": manifest,
    })
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="doc-check 阶段③：渲染 HTML 报告")
    parser.add_argument("--work", default=".doc-check-work", help="工作目录")
    parser.add_argument("--out", default="report.html", help="输出 HTML 路径")
    parser.add_argument("--baseline", default=None, help="上次运行的 last-findings.json")
    args = parser.parse_args(argv)

    out = render(Path(args.work), Path(args.out),
                 Path(args.baseline) if args.baseline else None)
    print(f"报告已生成：{out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
