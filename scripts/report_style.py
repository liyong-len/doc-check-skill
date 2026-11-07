"""报告内联样式。CSS 以常量形式保存，保证输出为单文件自包含 HTML。"""
from __future__ import annotations

CSS = """
:root {
  --p0: #b3261e; --p1: #c77700; --p2: #2f6fb0; --p3: #6b7280;
  --ink: #1f2328; --muted: #6b7280; --line: #e5e7eb; --bg: #ffffff;
  --soft: #f7f8fa;
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 0 24px 64px;
  font-family: -apple-system, "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif;
  color: var(--ink); background: var(--bg); line-height: 1.65; font-size: 14px;
}
.wrap { max-width: 1080px; margin: 0 auto; }
header.top { padding: 28px 0 16px; border-bottom: 2px solid var(--ink); }
h1 { font-size: 24px; margin: 0 0 8px; }
.sub { color: var(--muted); font-size: 13px; }
.banner {
  margin: 16px 0; padding: 12px 16px; border-left: 4px solid var(--p0);
  background: var(--soft); border-radius: 4px;
}
nav.toc { margin: 16px 0 28px; padding: 12px 16px; background: var(--soft); border-radius: 4px; }
nav.toc a { color: var(--p2); text-decoration: none; margin-right: 16px; display: inline-block; }
h2 { font-size: 18px; margin: 32px 0 12px; padding-bottom: 6px; border-bottom: 1px solid var(--line); }
h3 { font-size: 15px; margin: 20px 0 8px; }
table { border-collapse: collapse; width: 100%; margin: 10px 0 18px; font-size: 13px; }
th, td { border: 1px solid var(--line); padding: 6px 9px; text-align: left; vertical-align: top; }
th { background: var(--soft); font-weight: 600; }
.badge {
  display: inline-block; padding: 1px 8px; border-radius: 10px;
  font-size: 12px; font-weight: 600; color: #fff; margin-right: 6px;
}
.badge.P0 { background: var(--p0); } .badge.P1 { background: var(--p1); }
.badge.P2 { background: var(--p2); } .badge.P3 { background: var(--p3); }
.tag { display: inline-block; padding: 1px 7px; border: 1px solid var(--line);
  border-radius: 4px; font-size: 12px; color: var(--muted); margin-right: 6px; }
.bar { height: 18px; background: var(--p3); border-radius: 3px; display: inline-block; }
.counts { display: flex; gap: 18px; flex-wrap: wrap; margin: 10px 0; }
.counts div { font-size: 13px; }
.counts b { font-size: 18px; display: block; }
.issue { border: 1px solid var(--line); border-left-width: 4px; border-radius: 4px;
  padding: 10px 14px; margin: 10px 0; background: var(--soft); }
.issue.P0 { border-left-color: var(--p0); } .issue.P1 { border-left-color: var(--p1); }
.issue.P2 { border-left-color: var(--p2); } .issue.P3 { border-left-color: var(--p3); }
.issue .quote { background: #fbfbfd; border-left: 3px solid #d7dbe2;
  padding: 6px 10px; margin: 8px 0; white-space: pre-wrap; }
/* 问题片段高亮：引文本身是有问题的那一段，用 <mark> 把它标出来。
   整块底色标不出片段——整块都是底色等于没标。 */
.issue .quote mark { background: #ffe8a3; color: inherit; padding: 0 2px;
  border-radius: 2px; }
.issue .loc { color: var(--muted); font-size: 12px; }
.issue .fix { color: #166534; }
details { margin: 8px 0; }
summary { cursor: pointer; font-weight: 600; }
.muted { color: var(--muted); }
.limit { border: 1px dashed var(--p1); padding: 12px 16px; border-radius: 4px; background: #fffaf0; }
@media print {
  body { padding: 0; font-size: 11px; }
  nav.toc { display: none; }
  .issue { break-inside: avoid; }
  h2 { break-after: avoid; }
}
"""
