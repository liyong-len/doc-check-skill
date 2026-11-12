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

/* 章节折叠。
   每一节默认收起，标题旁有一个可点的折叠标记。
   报告要能一眼看完概况，也要能逐节展开细看——全展开的报告太长，
   收起的报告又看不出每节里有什么，所以标题上带一个该节的摘要（问题数）。 */
.sec { margin: 18px 0; border: 1px solid var(--line); border-radius: 6px; }
.sec > summary {
  display: flex; align-items: baseline; gap: 8px; list-style: none;
  padding: 10px 14px; background: var(--soft); border-radius: 5px;
  cursor: pointer;
}
.sec > summary::-webkit-details-marker { display: none; }
.sec > summary::marker { content: ""; }
/* 折叠标记：一个会转的小三角。用 CSS 画，不引图标字体。 */
.sec > summary .fold {
  flex: none; width: 0; height: 0; align-self: center;
  border-left: 6px solid var(--muted);
  border-top: 4px solid transparent; border-bottom: 4px solid transparent;
  transition: transform .12s ease;
}
.sec[open] > summary .fold { transform: rotate(90deg); }
.sec[open] > summary { border-radius: 5px 5px 0 0; border-bottom: 1px solid var(--line); }
/* h2 现在在 summary 里：它仍是文档的章节标题（目录锚点指向它），
   但视觉上要和整行标题齐平，所以去掉它自己的块级边距。 */
.sec > summary h2 {
  margin: 0; padding: 0; border: 0; font-size: 17px; display: inline;
}
.sec > summary .sec-count { color: var(--muted); font-size: 13px; font-weight: 400; }
.sec-body { padding: 4px 14px 12px; }

/* 样式偏离表：位置清单从独立一列挪到说明列下方，用底色标出来。
   位置是一串段序，单独占一列会把表撑得很宽，且与说明割裂。 */
.tbl-style { table-layout: fixed; }
.tbl-style th:nth-child(1), .tbl-style td:nth-child(1) { width: 24%; }
.tbl-style th:nth-child(2), .tbl-style td:nth-child(2) { width: 11%; }
.tbl-style th:nth-child(3), .tbl-style td:nth-child(3) { width: 10%; }
.tbl-style th:nth-child(4), .tbl-style td:nth-child(4) { width: 6%; }
.tbl-style th:nth-child(5), .tbl-style td:nth-child(5) { width: 49%; }
.tbl-style td { vertical-align: top; }
.loc-desc { margin-bottom: 4px; }
.loc-list {
  margin-top: 4px; padding: 6px 9px; border-radius: 3px;
  background: #eef4fb; border-left: 3px solid #9dbfe4;
  font-size: 12px; color: #24456b; word-break: break-all; line-height: 1.5;
}
.loc-list b { color: #16375c; }
.loc-fix { margin-top: 4px; font-size: 12px; color: #166534; }
@media print {
  body { padding: 0; font-size: 11px; }
  nav.toc { display: none; }
  .issue { break-inside: avoid; }
  h2 { break-after: avoid; }
  /* 打印时全部展开：纸上要看到全部内容（展开由脚本在 beforeprint 里做）。 */
  .sec > summary .fold { display: none; }
  .sec { border: 0; }
  .sec > summary { background: none; padding-left: 0; }
}
"""
