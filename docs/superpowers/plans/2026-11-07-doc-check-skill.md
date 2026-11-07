# doc-check 技能实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付一个可上传 GitHub、一键安装到 Claude Code / Codex / WorkBuddy / DSH 等任意智能体的文档检查技能，对投标文档做格式体例与内容语义两类检查，产出单文件自包含 HTML 报告。

**Architecture:** 双层架构。脚本层（Python）负责确定性抽取、统计与报告渲染；智能体层负责语义判定。三阶段协议：① `prepare.py` 产出 docs.json / consistency.json / chunks.json，② 智能体读 chunks.json 按 references 规则写出 findings.json，③ `render.py` 渲染 HTML。跨智能体契约只有「跑 python / 读 json / 写 json」三项能力。

**Tech Stack:** Python 3.9+、python-docx、openpyxl、pdfplumber、lxml、pytest、reportlab（仅测试生成样本）

**Spec:** `docs/superpowers/specs/2026-11-07-doc-check-skill-design.md`

## Global Constraints

以下约束来自 spec，适用于每一个任务，不再逐任务重复：

- Python 版本下限 3.9。所有源文件首行使用 `from __future__ import annotations`，允许 `str | None` 注解写法。
- 运行时依赖仅四项：`python-docx`、`openpyxl`、`pdfplumber`、`lxml`。不得引入其他第三方运行时依赖。
- **绝不修改用户文档。** 全部脚本只读输入文件。
- HTML 报告必须是**单个文件**，CSS 内联，不引用任何 CDN、外部字体或 JavaScript 库。
- 不联网。不调用任何外部大模型 API。语义判断由运行技能的智能体自身完成。
- 不做 OCR。扫描版 PDF 标记为「需 OCR，当前不支持」，不做内容判定。
- 全部输出与文档内容使用中文；代码标识符、JSON 键名、命令使用英文。
- 报告必须固定包含一条局限声明：本工具未核实外部事实，相关结论标注「需人工核实」。
- 智能体适配表 `install/adapters.json` 中已确认的路径：Claude Code `~/.claude/skills/doc-check`、Codex `~/.codex/skills/doc-check`、WorkBuddy `~/DoubaoWork/skills/doc-check`。DSH 路径 `~/.dsh/skills/doc-check` 为未确认候选值。
- 统一 finding 结构，`deterministic` 与 `llm` 两个来源共用同一套 schema。
- 每完成一个任务必须提交，提交信息使用 Conventional Commits。

## 数据契约（所有任务共同遵守）

### 文档结构（docs.json 中每个元素）

```python
{
  "file": "a.docx",                      # 相对工作目录的文件名
  "path": "D:/x/a.docx",                 # 绝对路径
  "type": "docx",                        # docx | xlsx | pdf | md | txt
  "sha256": "…",
  "title": "投标文件",
  "stats": {"paragraphs": 120, "tables": 3, "pages": 12, "words": 5600, "rows": 0, "sheets": 0},
  "sections": [
    {"path": "第三章/3.2 报价说明", "level": 2, "heading": "3.2 报价说明", "start": 40, "end": 58}
  ],
  "blocks": [
    {"index": 0, "kind": "paragraph", "text": "…", "section_path": "…", "style": {…}},
    {"index": 1, "kind": "table", "section_path": "…",
     "rows": [[{"text": "…", "style": {…}}, …], …]}
  ],
  "entities": ["北京华信科技有限公司"],
  "citations": ["[3]", "如图3-1所示"],
  "numbers": ["1,200.00", "15%"],
  "notes": []
}
```

### 段落样式结构（`style` 字典，抽取器与 analyze 共同使用）

```python
{
  "font_latin": "Times New Roman", "font_ea": "宋体",
  "size_pt": 12.0, "bold": False, "italic": False,
  "align": "both", "indent_left_pt": 0.0, "indent_first_pt": 24.0,
  "line_spacing": 1.5, "space_before_pt": 0.0, "space_after_pt": 0.0,
  "style_name": "正文", "is_heading": False, "heading_level": 0,
  "list_numbered": False, "confidence": "high"
}
```

`confidence` 取值 `high`（docx / xlsx）或 `low`（pdf）。md / txt 无样式，`style` 为 `None`。

### finding 结构（consistency.json 与 findings.json 共用）

```python
{
  "id": "ab12cd34ef567890",
  "severity": "P2",                       # P0 | P1 | P2 | P3
  "category": "字体一致性",
  "detector": "deterministic",           # deterministic | llm
  "confidence": "确定",                   # 确定 | 疑似 · 需人工核实
  "file": "a.docx",
  "locator": {"type": "paragraph", "index": 42, "section_path": "第三章/3.2 报价说明"},
  "quote": "…",
  "description": "…",
  "suggestion": "…"
}
```

`locator.type` 取值：`paragraph`（带 `index` 与 `section_path`）、`table`（带 `row` 与 `col`）、`file`（文件级问题）、`section`（带 `section_path`）。

---

## Task 1: 仓库骨架、依赖声明与 common.py

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.gitignore`
- Create: `LICENSE`
- Create: `scripts/common.py`
- Create: `tests/test_common.py`
- Create: `tests/conftest.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `common.SCRIPT_VERSION: str`
  - `common.repo_root() -> Path`
  - `common.work_dir(base: str | None = None) -> Path`
  - `common.write_json(path: Path, data: Any) -> None`
  - `common.read_json(path: Path) -> Any`
  - `common.sha256_file(path: Path) -> str`
  - `common.normalize_text(s: str) -> str`
  - `common.normalize_name(s: str) -> str`
  - `common.finding_id(file: str, category: str, locator: dict, quote: str) -> str`

- [ ] **Step 1: 写依赖声明与忽略规则**

`requirements.txt`:
```
python-docx>=1.1.0
openpyxl>=3.1.2
pdfplumber>=0.11.0
lxml>=5.1.0
```

`requirements-dev.txt`:
```
-r requirements.txt
pytest>=8.0.0
reportlab>=4.1.0
```

`.gitignore`:
```
.venv/
.doc-check-work/
__pycache__/
*.pyc
.pytest_cache/
report.html
```

`LICENSE` 内容为 MIT 许可证全文，版权行写 `Copyright (c) 2026 doc-check contributors`。

- [ ] **Step 2: 写失败的测试**

`tests/conftest.py`:
```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
```

`tests/test_common.py`:
```python
import json
from pathlib import Path

import hashlib

from common import (
    finding_id,
    normalize_name,
    normalize_text,
    read_json,
    repo_root,
    sha256_file,
    work_dir,
    write_json,
)


def test_repo_root_contains_scripts(tmp_path):
    assert (repo_root() / "scripts").is_dir()


def test_work_dir_creates_directory(tmp_path):
    d = work_dir(str(tmp_path / "w"))
    assert d.is_dir()


def test_write_and_read_json_roundtrip(tmp_path):
    p = tmp_path / "a" / "b.json"
    write_json(p, {"名称": "值"})
    assert read_json(p) == {"名称": "值"}
    assert "名称" in p.read_text(encoding="utf-8")


def test_sha256_file_is_stable(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"abc")
    assert sha256_file(p) == sha256_file(p)
    assert len(sha256_file(p)) == 64
    assert sha256_file(p) == hashlib.sha256(b"abc").hexdigest()


def test_normalize_text_collapses_whitespace_and_fullwidth():
    assert normalize_text("  甲　乙  ") == "甲 乙"
    assert normalize_text("ＡＢＣ") == "ABC"


def test_normalize_name_strips_all_whitespace():
    assert normalize_name("北京 华信　科技 有限公司") == "北京华信科技有限公司"


def test_finding_id_is_stable_and_length_16():
    loc = {"type": "paragraph", "index": 3}
    a = finding_id("a.docx", "字体一致性", loc, "正文 片段")
    b = finding_id("a.docx", "字体一致性", loc, "正文  片段")
    assert a == b
    assert len(a) == 16


def test_finding_id_distinguishes_distinct_findings():
    cat = "字体一致性"
    loc = {"type": "paragraph", "index": 3}
    base = finding_id("a.docx", cat, loc, "正文")
    assert finding_id("b.docx", cat, loc, "正文") != base
    assert finding_id("a.docx", "段落格式一致性", loc, "正文") != base
    assert finding_id("a.docx", cat, {"type": "paragraph", "index": 4}, "正文") != base
    assert finding_id("a.docx", cat, {**loc, "sheet": "s"}, "正文") != base


def test_finding_id_is_stable_across_locator_key_order():
    a = finding_id("a.docx", "字体一致性",
                   {"type": "paragraph", "index": 3, "section_path": "第一章"}, "正文")
    b = finding_id("a.docx", "字体一致性",
                   {"section_path": "第一章", "index": 3, "type": "paragraph"}, "正文")
    assert a == b
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python -m pytest tests/test_common.py -v`
Expected: FAIL，错误为 `ModuleNotFoundError: No module named 'common'`

- [ ] **Step 4: 实现 common.py**

`scripts/common.py`:
```python
"""共享工具：路径、JSON 读写、哈希、文本归一化、finding 指纹。"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "0.1.0"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def work_dir(base: str | None = None) -> Path:
    p = Path(base).resolve() if base else Path(".doc-check-work").resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_text(s: str) -> str:
    """NFKC 归一 + 空白折叠，用于文本比对。"""
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_name(s: str) -> str:
    """主体名归一化：NFKC + 去掉所有空白（含全角空格）。"""
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"[\s　]+", "", s).strip()


def finding_id(file: str, category: str, locator: dict, quote: str) -> str:
    raw = "|".join(
        [
            file,
            category,
            category_key(locator),
            normalize_text(quote),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def category_key(locator: dict) -> str:
    """locator 的稳定字符串形式，用于指纹计算。

    取全部 locator 键并按键名排序，避免固定白名单丢掉信息导致不同问题撞指纹。
    """
    parts = [str(locator.get("type", ""))]
    parts += [
        f"{key}={_locator_value(locator[key])}"
        for key in sorted(locator)
        if key != "type" and locator[key] is not None
    ]
    return "/".join(parts)


def _locator_value(value) -> str:
    """locator 值的稳定字符串形式。容器按键名排序，避免插入顺序影响指纹。"""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return str(value)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_common.py -v`
Expected: PASS，7 passed

- [ ] **Step 6: 提交**

```bash
git add requirements.txt requirements-dev.txt .gitignore LICENSE scripts/common.py tests/
git commit -m "feat: scaffold repo with shared common utilities"
```

---

## Task 2: docx 抽取器

**Files:**
- Create: `scripts/extractors/__init__.py`
- Create: `scripts/extractors/docx.py`
- Create: `tests/test_extract_docx.py`

**Interfaces:**
- Consumes: `common.normalize_text`
- Produces:
  - `extractors.docx.extract_docx(path: Path) -> dict` — 返回统一文档结构（见数据契约）
  - `extractors.docx._paragraph_style(paragraph, doc) -> dict` — 段落有效样式
  - `extractors.docx._heading_level(style_name: str) -> int`
  - `extractors.docx._section_path_stack(blocks) -> list[dict]`

- [ ] **Step 1: 写失败的测试**

`tests/test_extract_docx.py`:
```python
import docx
from docx.shared import Pt

from extractors.docx import extract_docx


def _make_doc(tmp_path):
    d = docx.Document()
    d.add_heading("投标文件", level=1)
    d.add_heading("技术方案", level=2)
    p = d.add_paragraph("本公司具备相关资质。")
    run = p.runs[0]
    run.font.size = Pt(10.5)
    run.font.name = "Times New Roman"
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text = "项目"
    t.cell(0, 1).text = "数量"
    t.cell(1, 0).text = "设备"
    t.cell(1, 1).text = "10"
    path = tmp_path / "a.docx"
    d.save(str(path))
    return path


def test_extract_docx_basic_structure(tmp_path):
    doc = extract_docx(_make_doc(tmp_path))
    assert doc["type"] == "docx"
    assert doc["stats"]["tables"] == 1
    assert doc["stats"]["paragraphs"] >= 3
    assert doc["sha256"] and len(doc["sha256"]) == 64


def test_extract_docx_sections_and_blocks(tmp_path):
    doc = extract_docx(_make_doc(tmp_path))
    paths = [s["path"] for s in doc["sections"]]
    assert "投标文件/技术方案" in paths
    texts = [b.get("text", "") for b in doc["blocks"]]
    assert "本公司具备相关资质。" in texts
    assert any(b["kind"] == "table" for b in doc["blocks"])


def test_extract_docx_reads_run_size_and_font(tmp_path):
    doc = extract_docx(_make_doc(tmp_path))
    para = next(
        b for b in doc["blocks"]
        if b.get("text") == "本公司具备相关资质。"
    )
    assert para["style"]["size_pt"] == 10.5
    assert para["style"]["font_latin"] == "Times New Roman"
    assert para["style"]["confidence"] == "high"


def test_extract_docx_heading_level_parsed(tmp_path):
    doc = extract_docx(_make_doc(tmp_path))
    headings = [b for b in doc["blocks"] if b["kind"] == "paragraph" and b["style"]["is_heading"]]
    levels = sorted({h["style"]["heading_level"] for h in headings})
    assert levels == [1, 2]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_extract_docx.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'extractors'`

- [ ] **Step 3: 创建 extractors 包与 docx 抽取器**

`scripts/extractors/__init__.py`:
```python
"""各文件格式抽取器。每个抽取器返回统一文档结构。"""
from __future__ import annotations
```

`scripts/extractors/docx.py`:
```python
"""docx 抽取器。"""
from __future__ import annotations

import re
from pathlib import Path

import docx
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from common import sha256_file

_HEADING_RE = re.compile(r"(?:Heading|标题)\s*(\d+)\s*$")


def _heading_level(style_name: str | None) -> int:
    if not style_name:
        return 0
    m = _HEADING_RE.search(style_name.strip())
    return int(m.group(1)) if m else 0


def _run_style(run) -> dict:
    rPr = getattr(run._element, "rPr", None)
    east_asia = None
    if rPr is not None:
        rFonts = getattr(rPr, "rFonts", None)
        if rFonts is not None:
            east_asia = rFonts.get(qn("w:eastAsia"))
    size = run.font.size
    return {
        "font_latin": run.font.name,
        "font_ea": east_asia,
        "size_pt": size.pt if size is not None else None,
        "bold": bool(run.bold),
        "italic": bool(run.italic),
    }


def _paragraph_style(paragraph, doc) -> dict:
    pf = paragraph.paragraph_format
    align = pf.alignment
    align_val = None if align is None else str(align)
    if align_val is not None and "." in align_val:
        align_val = align_val.split(".")[-1]
    ls = pf.line_spacing
    line_spacing = ls if isinstance(ls, (int, float)) else (ls.pt / 12.0 if ls is not None else None)
    sb, sa = pf.space_before, pf.space_after
    style_name = paragraph.style.name if paragraph.style is not None else None
    level = _heading_level(style_name)

    run = None
    for r in paragraph.runs:
        if r.text.strip():
            run = r
            break
    rs = _run_style(run) if run is not None else {
        "font_latin": None, "font_ea": None,
        "size_pt": None, "bold": False, "italic": False,
    }

    pPr = getattr(paragraph._p, "pPr", None)
    numbered = False
    if pPr is not None:
        numbered = pPr.find(qn("w:numPr")) is not None

    return {
        "font_latin": rs["font_latin"],
        "font_ea": rs["font_ea"],
        "size_pt": rs["size_pt"],
        "bold": rs["bold"],
        "italic": rs["italic"],
        "align": align_val,
        "indent_left_pt": pf.left_indent.pt if pf.left_indent is not None else 0.0,
        "indent_first_pt": pf.first_line_indent.pt if pf.first_line_indent is not None else 0.0,
        "line_spacing": line_spacing,
        "space_before_pt": sb.pt if sb is not None else 0.0,
        "space_after_pt": sa.pt if sa is not None else 0.0,
        "style_name": style_name,
        "is_heading": level > 0,
        "heading_level": level,
        "list_numbered": numbered,
        "confidence": "high",
    }


def _iter_body(doc):
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield Table(child, doc)


def _section_path_stack(blocks) -> list[dict]:
    stack = []
    sections = []
    for b in blocks:
        st = b.get("style") or {}
        if b["kind"] == "paragraph" and st.get("is_heading"):
            level = st.get("heading_level", 1)
            while stack and stack[-1]["level"] >= level:
                stack.pop()
            stack.append({"level": level, "heading": b.get("text", "").strip()})
        b["section_path"] = "/".join(s["heading"] for s in stack)
        if stack:
            last = stack[-1]
            for s in sections:
                if s["path"] == b["section_path"]:
                    last = s
                    break
            else:
                s = {
                    "path": b["section_path"],
                    "level": last["level"],
                    "heading": last["heading"],
                    "start": b["index"],
                    "end": b["index"],
                }
                sections.append(s)
            last["end"] = b["index"]
    return sections


def _cell_style(cell) -> dict:
    ps = cell.paragraphs
    if not ps:
        return {}
    p = ps[0]
    style = _paragraph_style(p, None)
    return {
        "font_latin": style["font_latin"],
        "font_ea": style["font_ea"],
        "size_pt": style["size_pt"],
        "bold": style["bold"],
        "align": style["align"],
    }


def extract_docx(path: Path) -> dict:
    path = Path(path)
    doc = docx.Document(str(path))
    blocks = []
    index = 0
    paragraphs = 0
    tables = 0
    for item in _iter_body(doc):
        if isinstance(item, Paragraph):
            text = item.text
            blocks.append({
                "index": index,
                "kind": "paragraph",
                "text": text,
                "style": _paragraph_style(item, doc),
            })
            paragraphs += 1
        else:
            rows = []
            for row in item.rows:
                rows.append([
                    {"text": c.text, "style": _cell_style(c)} for c in row.cells
                ])
            blocks.append({
                "index": index,
                "kind": "table",
                "text": "",
                "rows": rows,
            })
            tables += 1
        index += 1

    sections = _section_path_stack(blocks)

    words = 0
    for b in blocks:
        if b["kind"] == "paragraph":
            words += len(b["text"])
        else:
            for r in b.get("rows", []):
                for c in r:
                    words += len(c["text"])

    title = ""
    try:
        title = doc.core_properties.title or ""
    except Exception:
        title = ""

    return {
        "file": path.name,
        "path": str(path.resolve()),
        "type": "docx",
        "sha256": sha256_file(path),
        "title": title,
        "stats": {
            "paragraphs": paragraphs,
            "tables": tables,
            "pages": 0,
            "words": words,
            "rows": 0,
            "sheets": 0,
        },
        "sections": sections,
        "blocks": blocks,
        "entities": [],
        "citations": [],
        "numbers": [],
        "notes": [],
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_extract_docx.py -v`
Expected: PASS，4 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/extractors/ tests/test_extract_docx.py
git commit -m "feat: add docx extractor with style and section extraction"
```

---

## Task 3: xlsx 抽取器

**Files:**
- Create: `scripts/extractors/xlsx.py`
- Create: `tests/test_extract_xlsx.py`

**Interfaces:**
- Consumes: `common.sha256_file`
- Produces: `extractors.xlsx.extract_xlsx(path: Path) -> dict`

- [ ] **Step 1: 写失败的测试**

`tests/test_extract_xlsx.py`:
```python
import openpyxl

from extractors.xlsx import extract_xlsx


def _make_xlsx(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "报价表"
    ws["A1"] = "项目"
    ws["B1"] = "数量"
    ws["A2"] = "设备"
    ws["B2"] = 10
    ws["B2"].number_format = "#,##0.00"
    ws2 = wb.create_sheet("说明")
    ws2["A1"] = "备注"
    path = tmp_path / "b.xlsx"
    wb.save(str(path))
    return path


def test_extract_xlsx_sheets_and_rows(tmp_path):
    doc = extract_xlsx(_make_xlsx(tmp_path))
    assert doc["type"] == "xlsx"
    assert doc["stats"]["sheets"] == 2
    assert doc["stats"]["rows"] == 3


def test_extract_xlsx_number_format_kept(tmp_path):
    doc = extract_xlsx(_make_xlsx(tmp_path))
    sheets = {s["name"]: s for s in doc["sheets"]}
    cell = sheets["报价表"]["cells"]["B2"]
    assert cell["value"] == 10
    assert cell["number_format"] == "#,##0.00"


def test_extract_xlsx_header_row_inferred(tmp_path):
    doc = extract_xlsx(_make_xlsx(tmp_path))
    sheets = {s["name"]: s for s in doc["sheets"]}
    assert sheets["报价表"]["header_row"] == 1


def test_extract_xlsx_blocks_have_table_kind(tmp_path):
    doc = extract_xlsx(_make_xlsx(tmp_path))
    assert any(b["kind"] == "table" for b in doc["blocks"])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_extract_xlsx.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'extractors.xlsx'`

- [ ] **Step 3: 实现 xlsx 抽取器**

`scripts/extractors/xlsx.py`:
```python
"""xlsx 抽取器。"""
from __future__ import annotations

from pathlib import Path

import openpyxl

from common import sha256_file


def _cell_payload(cell, formula_wb) -> dict:
    value = cell.value
    formula = None
    if isinstance(value, str) and value.startswith("="):
        formula = value
        try:
            cached = formula_wb[cell.parent.title][cell.coordinate].value
        except Exception:
            cached = None
        value = cached
    font = cell.font
    return {
        "value": value,
        "formula": formula,
        "number_format": cell.number_format,
        "font": {
            "name": font.name,
            "size": font.sz,
            "bold": bool(font.bold),
            "italic": bool(font.italic),
        },
        "alignment": {
            "horizontal": cell.alignment.horizontal,
            "vertical": cell.alignment.vertical,
            "wrap_text": bool(cell.alignment.wrap_text),
        },
        "fill": cell.fill.fgColor.rgb if cell.fill and cell.fill.fgColor else None,
        "border": {
            side: getattr(cell.border, side).style
            for side in ("left", "right", "top", "bottom")
        },
    }


def _infer_header_row(rows: list[list[dict]]) -> int:
    """首行非空且下方存在数据的行视为表头；否则返回 0。"""
    if not rows:
        return 0
    first = rows[0]
    if not any(c["value"] not in (None, "") for c in first):
        return 0
    if len(rows) < 2:
        return 0
    return 1


def extract_xlsx(path: Path) -> dict:
    path = Path(path)
    wb = openpyxl.load_workbook(str(path), data_only=False)
    formula_wb = openpyxl.load_workbook(str(path), data_only=True)

    sheets = []
    blocks = []
    index = 0
    total_rows = 0
    for ws in wb.worksheets:
        grid = []
        for row in ws.iter_rows():
            cells = [_cell_payload(c, formula_wb) for c in row]
            grid.append(cells)
        nonempty_rows = [r for r in grid if any(c["value"] not in (None, "") for c in r)]
        total_rows += len(nonempty_rows)

        cell_map = {}
        for ri, row in enumerate(ws.iter_rows(), start=1):
            for c in row:
                payload = _cell_payload(c, formula_wb)
                if payload["value"] not in (None, "") or payload["formula"]:
                    cell_map[c.coordinate] = payload

        header_row = _infer_header_row(grid)
        sheets.append({
            "name": ws.title,
            "max_row": ws.max_row,
            "max_column": ws.max_column,
            "merged_ranges": [str(r) for r in ws.merged_cells.ranges],
            "header_row": header_row,
            "headers": [str(c["value"]) for c in grid[header_row - 1]] if header_row else [],
            "cells": cell_map,
        })

        table_rows = []
        for r in grid:
            table_rows.append([
                {"text": "" if c["value"] is None else str(c["value"]), "style": {}}
                for c in r
            ])
        if table_rows:
            blocks.append({
                "index": index,
                "kind": "table",
                "text": "",
                "section_path": ws.title,
                "rows": table_rows,
            })
            index += 1

    return {
        "file": path.name,
        "path": str(path.resolve()),
        "type": "xlsx",
        "sha256": sha256_file(path),
        "title": "",
        "stats": {
            "paragraphs": 0,
            "tables": len(sheets),
            "pages": 0,
            "words": 0,
            "rows": total_rows,
            "sheets": len(sheets),
        },
        "sections": [
            {"path": s["name"], "level": 1, "heading": s["name"], "start": 0, "end": 0}
            for s in sheets
        ],
        "blocks": blocks,
        "sheets": sheets,
        "entities": [],
        "citations": [],
        "numbers": [],
        "notes": [],
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_extract_xlsx.py -v`
Expected: PASS，4 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/extractors/xlsx.py tests/test_extract_xlsx.py
git commit -m "feat: add xlsx extractor with style and header inference"
```

---

## Task 4: pdf 抽取器

**Files:**
- Create: `scripts/extractors/pdf.py`
- Create: `tests/test_extract_pdf.py`

**Interfaces:**
- Consumes: `common.sha256_file`
- Produces: `extractors.pdf.extract_pdf(path: Path) -> dict`

- [ ] **Step 1: 写失败的测试**

`tests/test_extract_pdf.py`:
```python
import pytest

reportlab = pytest.importorskip("reportlab")

from extractors.pdf import extract_pdf


def _make_pdf(tmp_path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    path = tmp_path / "c.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica", 12)
    c.drawString(72, 760, "Beijing Huaxin Technology Co., Ltd.")
    c.drawString(72, 730, "Tender document section one.")
    c.showPage()
    c.setFont("Helvetica", 10)
    c.drawString(72, 760, "Page two content.")
    c.save()
    return path


def test_extract_pdf_pages_and_text(tmp_path):
    doc = extract_pdf(_make_pdf(tmp_path))
    assert doc["type"] == "pdf"
    assert doc["stats"]["pages"] == 2
    assert "Tender document" in " ".join(b["text"] for b in doc["blocks"])


def test_extract_pdf_confidence_is_low(tmp_path):
    doc = extract_pdf(_make_pdf(tmp_path))
    assert doc["blocks"][0]["style"]["confidence"] == "low"


def test_extract_pdf_font_stats_present(tmp_path):
    doc = extract_pdf(_make_pdf(tmp_path))
    assert doc["font_stats"]
    assert any(f["size"] for f in doc["font_stats"])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_extract_pdf.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'extractors.pdf'`

- [ ] **Step 3: 实现 pdf 抽取器**

`scripts/extractors/pdf.py`:
```python
"""pdf 抽取器。样式置信度低，格式类结论需谨慎使用。"""
from __future__ import annotations

from pathlib import Path

import pdfplumber

from common import sha256_file


def _font_stats(chars: list[dict]) -> list[dict]:
    counts: dict[tuple[str, float], int] = {}
    for ch in chars:
        key = (ch.get("fontname") or "unknown", round(float(ch.get("size") or 0), 2))
        counts[key] = counts.get(key, 0) + 1
    return [
        {"font": name, "size": size, "count": n}
        for (name, size), n in sorted(counts.items(), key=lambda kv: -kv[1])
    ]


def extract_pdf(path: Path) -> dict:
    path = Path(path)
    blocks = []
    font_stats: list[dict] = []
    pages = 0
    notes: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        pages = len(pdf.pages)
        for pi, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip():
                notes.append(f"第 {pi} 页无文本层，疑似扫描件，需 OCR")
            for f in _font_stats(page.chars):
                font_stats.append(f)
            blocks.append({
                "index": pi - 1,
                "kind": "paragraph",
                "text": text,
                "section_path": f"第 {pi} 页",
                "style": {
                    "font_latin": None,
                    "font_ea": None,
                    "size_pt": None,
                    "bold": False,
                    "italic": False,
                    "align": None,
                    "indent_left_pt": 0.0,
                    "indent_first_pt": 0.0,
                    "line_spacing": None,
                    "space_before_pt": 0.0,
                    "space_after_pt": 0.0,
                    "style_name": None,
                    "is_heading": False,
                    "heading_level": 0,
                    "list_numbered": False,
                    "confidence": "low",
                },
            })
    merged: dict[tuple[str, float], int] = {}
    for f in font_stats:
        key = (f["font"], f["size"])
        merged[key] = merged.get(key, 0) + f["count"]
    font_summary = [
        {"font": k[0], "size": k[1], "count": v}
        for k, v in sorted(merged.items(), key=lambda kv: -kv[1])
    ]
    if pages == 0:
        notes.append("PDF 没有页面，无法读取，需 OCR，当前不支持")
    elif all(not b["text"].strip() for b in blocks):
        notes.append("全文无文本层，疑似扫描件，需 OCR，当前不做内容判定")

    return {
        "file": path.name,
        "path": str(path.resolve()),
        "type": "pdf",
        "sha256": sha256_file(path),
        "title": "",
        "stats": {
            "paragraphs": len(blocks),
            "tables": 0,
            "pages": pages,
            "words": sum(len(b["text"]) for b in blocks),
            "rows": 0,
            "sheets": 0,
        },
        "sections": [],
        "blocks": blocks,
        "font_stats": font_summary,
        "entities": [],
        "citations": [],
        "numbers": [],
        "notes": notes,
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_extract_pdf.py -v`
Expected: PASS，3 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/extractors/pdf.py tests/test_extract_pdf.py
git commit -m "feat: add pdf extractor with low-confidence style metadata"
```

---

## Task 5: md/txt 抽取器、调度层与 manifest

**Files:**
- Create: `scripts/extractors/text.py`
- Modify: `scripts/extractors/__init__.py`
- Create: `scripts/manifest.py`
- Create: `tests/test_extract_text.py`
- Create: `tests/test_manifest.py`

**Interfaces:**
- Consumes: `common.sha256_file`, `common.normalize_text`
- Produces:
  - `extractors.text.extract_text(path: Path) -> dict`
  - `extractors.extract_document(path: Path) -> dict` — 按扩展名分派
  - `manifest.build_manifest(documents: list[dict], failures: list[dict], depth: str, work: Path) -> dict`

- [ ] **Step 1: 写失败的测试**

`tests/test_extract_text.py`:
```python
from extractors.text import extract_text


def test_extract_text_md_headings_and_table(tmp_path):
    p = tmp_path / "a.md"
    p.write_text(
        "# 投标文件\n\n## 技术方案\n\n正文内容。\n\n| 项目 | 数量 |\n| --- | --- |\n| 设备 | 10 |\n",
        encoding="utf-8",
    )
    doc = extract_text(p)
    assert doc["type"] == "md"
    paths = [s["path"] for s in doc["sections"]]
    assert "投标文件/技术方案" in paths
    assert any(b["kind"] == "table" for b in doc["blocks"])


def test_extract_text_txt_has_no_style(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("纯文本内容。\n", encoding="utf-8")
    doc = extract_text(p)
    assert doc["type"] == "txt"
    assert doc["blocks"][0]["style"] is None
```

`tests/test_manifest.py`:
```python
from manifest import build_manifest


def test_build_manifest_records_failures(tmp_path):
    docs = [{"file": "a.docx", "type": "docx", "sha256": "x" * 64,
             "stats": {"paragraphs": 1, "tables": 0, "pages": 0, "words": 10,
                       "rows": 0, "sheets": 0}}]
    failures = [{"file": "b.pdf", "path": "b.pdf", "reason": "需 OCR，当前不支持"}]
    m = build_manifest(docs, failures, "standard", tmp_path)
    assert m["depth"] == "standard"
    assert len(m["documents"]) == 1
    assert m["failures"][0]["file"] == "b.pdf"
    assert m["script_version"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_extract_text.py tests/test_manifest.py -v`
Expected: FAIL，模块不存在

- [ ] **Step 3: 实现 text 抽取器**

`scripts/extractors/text.py`:
```python
"""md / txt 抽取器。无样式概念，style 为 None。"""
from __future__ import annotations

import re
from pathlib import Path

from common import sha256_file

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def _parse_lines(lines: list[str]) -> list[dict]:
    blocks: list[dict] = []
    i = 0
    in_code = False
    stack: list[dict] = []
    sections: list[dict] = []
    index = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            i += 1
            continue
        if in_code:
            i += 1
            continue
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            heading = m.group(2)
            while stack and stack[-1]["level"] >= level:
                stack.pop()
            stack.append({"level": level, "heading": heading})
            blocks.append({
                "index": index, "kind": "paragraph", "text": heading,
                "section_path": "/".join(s["heading"] for s in stack), "style": None,
                "is_heading_md": True, "heading_level": level,
            })
            sections.append({
                "path": "/".join(s["heading"] for s in stack),
                "level": level, "heading": heading,
                "start": index, "end": index,
            })
            index += 1
            i += 1
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            rows = []
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                raw = lines[j].strip().strip("|")
                cells = [c.strip() for c in raw.split("|")]
                if not all(set(c) <= set("-: ") for c in cells):
                    rows.append(cells)
                j += 1
            blocks.append({
                "index": index, "kind": "table", "text": "",
                "section_path": "/".join(s["heading"] for s in stack),
                "rows": [[{"text": c, "style": {}} for c in r] for r in rows],
            })
            index += 1
            i = j
            continue
        if stripped:
            blocks.append({
                "index": index, "kind": "paragraph", "text": stripped,
                "section_path": "/".join(s["heading"] for s in stack), "style": None,
                "list_numbered": bool(_LIST_RE.match(line)),
            })
            index += 1
        i += 1
    return blocks, sections


def extract_text(path: Path) -> dict:
    path = Path(path)
    raw = path.read_text(encoding="utf-8", errors="replace")
    blocks, sections = _parse_lines(raw.splitlines())
    for b in blocks:
        if b["kind"] == "paragraph" and "list_numbered" not in b:
            b["list_numbered"] = False
    suffix = path.suffix.lower().lstrip(".")
    return {
        "file": path.name,
        "path": str(path.resolve()),
        "type": suffix if suffix in ("md", "txt") else "txt",
        "sha256": sha256_file(path),
        "title": "",
        "stats": {
            "paragraphs": sum(1 for b in blocks if b["kind"] == "paragraph"),
            "tables": sum(1 for b in blocks if b["kind"] == "table"),
            "pages": 0,
            "words": sum(len(b["text"]) for b in blocks),
            "rows": 0,
            "sheets": 0,
        },
        "sections": sections,
        "blocks": blocks,
        "entities": [],
        "citations": [],
        "numbers": [],
        "notes": [],
    }
```

- [ ] **Step 4: 实现调度层与 manifest**

`scripts/extractors/__init__.py` 追加：
```python
"""各文件格式抽取器。每个抽取器返回统一文档结构。"""
from __future__ import annotations

from pathlib import Path


def extract_document(path: Path) -> dict:
    """按扩展名分派到具体抽取器。"""
    from .docx import extract_docx
    from .pdf import extract_pdf
    from .text import extract_text
    from .xlsx import extract_xlsx

    suffix = Path(path).suffix.lower()
    if suffix == ".docx":
        return extract_docx(path)
    if suffix == ".xlsx":
        return extract_xlsx(path)
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix in (".md", ".markdown", ".txt"):
        return extract_text(path)
    raise ValueError(f"不支持的文件类型：{suffix}（支持 .docx/.xlsx/.pdf/.md/.txt）")
```

`scripts/manifest.py`:
```python
"""manifest.json 构造。记录文件清单、统计、指纹、失败项。"""
from __future__ import annotations

from pathlib import Path

from common import SCRIPT_VERSION


def build_manifest(documents: list[dict], failures: list[dict], depth: str, work: Path) -> dict:
    return {
        "script_version": SCRIPT_VERSION,
        "depth": depth,
        "generated_at": _now(),
        "work_dir": str(Path(work).resolve()),
        "documents": [
            {
                "file": d["file"],
                "type": d["type"],
                "sha256": d["sha256"],
                "stats": d["stats"],
                "entities": d.get("entities", []),
                "notes": d.get("notes", []),
            }
            for d in documents
        ],
        "failures": failures,
    }


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_extract_text.py tests/test_manifest.py -v`
Expected: PASS，4 passed

- [ ] **Step 6: 提交**

```bash
git add scripts/extractors/ scripts/manifest.py tests/test_extract_text.py tests/test_manifest.py
git commit -m "feat: add text extractor, dispatcher and manifest builder"
```

---

## Task 6: entities.py — 主体名发现

**Files:**
- Create: `scripts/entities.py`
- Create: `tests/test_entities.py`

**Interfaces:**
- Consumes: `common.normalize_name`
- Produces:
  - `entities.extract_company_names(text: str) -> list[str]`
  - `entities.core_key(name: str) -> str`
  - `entities.canonical_core(name: str) -> str`
  - `entities.canonical_name(name: str) -> str`
  - `entities.group_variants(names: list[str]) -> list[dict]`
  - `entities.same_entity(a: str, b: str) -> bool`

- [ ] **Step 1: 写失败的测试**

`tests/test_entities.py`:
```python
from entities import (
    canonical_core,
    core_key,
    extract_company_names,
    group_variants,
    same_entity,
)


def test_extract_company_names_basic():
    text = "本项目由北京华信科技有限公司负责，联合北京华信科技有限责任公司协作。"
    names = extract_company_names(text)
    assert "北京华信科技有限公司" in names
    assert "北京华信科技有限责任公司" in names


def test_extract_company_names_ignores_plain_text():
    assert extract_company_names("这是一段普通说明文字。") == []


def test_connector_inside_company_name_is_not_trimmed():
    # 「为」「和」也是字号的一部分，不能把「华为技术」裁成「技术」
    assert extract_company_names("华为技术有限公司") == ["华为技术有限公司"]
    assert extract_company_names("北京和信科技有限公司") == ["北京和信科技有限公司"]


def test_trim_skips_cut_that_leaves_too_little():
    # 「由」切出 6 字、「和」只切出 3 字（不足 4 字），跳过「和」取「由」
    assert extract_company_names("本项目由北京和兴科技有限公司编制") == [
        "北京和兴科技有限公司"
    ]


def test_trim_picks_last_qualifying_connector():
    # 候选长度随连接词右移而变短，取最短合格切分 = 取最靠后的合格连接词，
    # 这样句子碎片（甲方、乙方、委托）不会带进名字
    assert extract_company_names("由甲方及乙方共同委托北京华信科技有限公司") == [
        "北京华信科技有限公司"
    ]


def test_center_is_not_a_company_form():
    # 「中心」是普通名词不是企业形式，技术中心不该被抽成企业名
    assert extract_company_names("本项目技术中心负责实施") == []
    assert extract_company_names("数据中心有限公司") == ["数据中心有限公司"]


def test_form_fragment_guard_keeps_equal_length_names():
    # 形式词的严格前缀才是片段，长度相等的是真实字号
    assert extract_company_names("研究中心有限公司") == ["研究中心有限公司"]
    assert extract_company_names("设计院有限公司") == ["设计院有限公司"]
    # 「股份」是「股份有限公司」的严格前缀，是片段，不应单独成一个名字
    names = extract_company_names("中信建设集团股份有限公司")
    assert names == ["中信建设集团股份有限公司"]
    assert "股份有限公司" not in names


def test_core_key_strips_suffix_and_region():
    assert core_key("北京华信科技有限公司") == "华信科技"
    assert core_key("华信科技有限公司") == "华信科技"


def test_core_key_keeps_industry_word():
    # 行业词参与主体区分，不剥离
    assert core_key("华信信息科技有限公司") == "华信信息科技"
    assert core_key("北京华信科技有限公司") != core_key("北京华信信息技术有限公司")


def test_same_entity_detects_prefix_short_form():
    assert same_entity("北京华信科技有限公司", "北京华信")


def test_same_entity_rejects_different_companies():
    assert not same_entity("北京华信科技有限公司", "上海远大信息技术有限公司")


def test_group_variants_clusters_by_core():
    names = ["北京华信科技有限公司", "北京华信科技有限责任公司", "上海远大信息技术有限公司"]
    groups = group_variants(names)
    sizes = sorted(len(g["names"]) for g in groups)
    assert sizes == [1, 2]
    two = next(g for g in groups if len(g["names"]) == 2)
    assert set(two["names"]) == {"北京华信科技有限公司", "北京华信科技有限责任公司"}


def test_weak_connector_characters_inside_names_are_preserved():
    assert extract_company_names("和而泰智能控制股份有限公司") == ["和而泰智能控制股份有限公司"]
    assert extract_company_names("中国联合网络通信集团有限公司") == ["中国联合网络通信集团有限公司"]
    assert extract_company_names("清华同方能源环保股份有限公司") == ["清华同方能源环保股份有限公司"]


def test_same_entity_uses_suffix_not_prefix():
    # 带连接词前缀的同一写法与干净写法同属一个主体
    assert same_entity("由北京华信科技有限公司", "北京华信科技有限公司")
    # 前缀关系会误并这两个不同主体
    assert not same_entity("中国建筑", "中国建筑科技")
    assert not same_entity("华信科技有限公司", "华信科技信息有限公司")


def test_short_form_and_full_name_are_same_entity():
    assert same_entity("北京华信", "北京华信科技有限公司")


def test_repeated_suffix_layer_is_one_entity():
    assert same_entity("中国建筑集团股份有限公司", "中国建筑集团")


def test_leading_weak_connector_only_stripped_when_long_enough():
    # 真实字号以弱连接词开头时不能被裁
    assert canonical_core("与信科技有限公司") == "与信科技"
    assert canonical_core("同创股份有限公司") == "同创"
    # 连接词后是行政区划开头时才裁
    assert canonical_core("与上海远大信息技术有限公司") == "上海远大信息技术"


def test_paren_group_is_consumed_atomically():
    assert extract_company_names("北京华信(集团)有限公司") == ["北京华信(集团)有限公司"]
    assert extract_company_names("北京华信（集团）科技有限公司") == ["北京华信（集团）科技有限公司"]
    assert extract_company_names("（北京华信科技有限公司）") == ["北京华信科技有限公司"]


def test_leading_annotation_parens_are_not_part_of_the_name():
    # 注解与编号括号不是字号的一部分
    assert extract_company_names("（招标人）北京华信科技有限公司") == ["北京华信科技有限公司"]
    assert extract_company_names("（1）北京华信科技有限公司") == ["北京华信科技有限公司"]


def test_agent_word_inside_a_company_name_is_not_a_connector():
    # 「代理记账」「代理财务」里的「代理」是字号的一部分
    assert extract_company_names("深圳市代理记账服务有限公司") == ["深圳市代理记账服务有限公司"]
    assert extract_company_names("深圳代理财务咨询有限公司") == ["深圳代理财务咨询有限公司"]


def test_canonical_name_normalizes_width_and_whitespace():
    assert canonical_name("北京华信（集团）有限公司") == canonical_name("北京华信(集团)有限公司")
    assert canonical_name("北京 华信科技有限公司") == "北京华信科技有限公司"


def test_org_form_suffix_is_not_stripped():
    # 研究院/设计院不是企业形式，剥掉会把不同主体并到一起
    assert canonical_core("中国建筑设计院有限公司") == "中国建筑设计院"
    assert canonical_core("中国建筑设计院") == "中国建筑设计院"
    assert canonical_core("中国建筑有限公司") == "中国建筑"


def test_organization_connectors_are_not_stripped_from_canonical():
    # 同/和/联合/协作在字号里太常见，不能剥
    assert canonical_core("联合网络通信有限公司") == "联合网络通信"
    assert canonical_core("和信科技有限公司") == "和信科技"
    assert canonical_core("同创股份有限公司") == "同创"


def test_weak_prefixed_core_is_not_merged_by_suffix_relation():
    # 多出来的「联合」是字号的一部分，不是句子碎片
    assert not same_entity("联合网络通信有限公司", "网络通信有限公司")
    assert not same_entity("和信科技有限公司", "信科技有限公司")


def test_strong_prefixed_core_is_still_merged():
    assert same_entity("由北京华信科技有限公司", "北京华信科技有限公司")


def test_name_extends_over_a_following_form_word():
    assert extract_company_names("中国建筑设计院有限公司") == ["中国建筑设计院有限公司"]
    assert extract_company_names("中信建设集团股份有限公司") == ["中信建设集团股份有限公司"]


def test_parentheses_in_company_names():
    assert extract_company_names("北京华信(集团)有限公司") == ["北京华信(集团)有限公司"]
    assert extract_company_names("北京华信（集团）科技有限公司") == ["北京华信（集团）科技有限公司"]
    assert extract_company_names("（北京华信科技有限公司）") == ["北京华信科技有限公司"]


def test_group_variants_keeps_distinct_cores_apart():
    groups = group_variants(["华信科技有限公司", "华信科技信息有限公司"])
    assert len(groups) == 2


def test_group_variants_canonicals_ignore_leading_weak_connector():
    groups = group_variants(["与上海远大信息技术有限公司", "上海远大信息技术有限公司"])
    assert len(groups) == 1
    assert groups[0]["canonicals"] == ["上海远大信息技术有限公司"]


def test_canonical_core_collapses_weak_prefix():
    assert canonical_core("与上海远大信息技术有限公司") == "上海远大信息技术"
    assert canonical_core("上海远大信息技术有限公司") == "上海远大信息技术"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_entities.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'entities'`

- [ ] **Step 3: 实现 entities.py**

`scripts/entities.py`:
```python
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

_NAME_RE = re.compile(
    r"(?P<pre>[一-龥A-Za-z0-9·](?:[一-龥A-Za-z0-9·]|\([^()（）]{1,20}\)|（[^()（）]{1,20}）){1,29}?)"
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

    强连接词（由/甲方/乙方/受托/委托…）其后几乎必然是字号，随时可裁。
    弱连接词（与/和/同/联合/为…）本身也是字号的一部分，
    只有在裁完剩下的是行政区划开头时才裁——
    否则「和而泰」「中国联合」「清华同方」这类字号会被截断。

    候选长度随连接词位置右移而变短，取最短即取最靠后的合格连接词。
    """
    best = None
    for conn in _STRONG_CONNECTORS:
        start = 0
        while True:
            idx = prefix.find(conn, start)
            if idx < 0:
                break
            candidate = prefix[idx + len(conn):].strip()
            if len(candidate) >= _MIN_PREFIX_LEN:
                if best is None or len(candidate) < len(best):
                    best = candidate
            start = idx + 1
    for conn in _WEAK_CONNECTORS:
        start = 0
        while True:
            idx = prefix.find(conn, start)
            if idx < 0:
                break
            candidate = prefix[idx + len(conn):].strip()
            if len(candidate) >= _MIN_PREFIX_LEN and _starts_with_region(candidate):
                if best is None or len(candidate) < len(best):
                    best = candidate
            start = idx + 1
    if best is None:
        return prefix.strip()
    return best


def _extend_over_suffix(text: str, end: int) -> int:
    """词尾后紧跟另一个词尾时，把名字延伸过去。

    「中国建筑设计院有限公司」的非贪婪匹配会停在「设计院」，
    余下的「有限公司」才是真正的企业形式词。
    """
    for s in _SUFFIXES:
        if text.startswith(s, end):
            return end + len(s)
    return end


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
        end = _extend_over_suffix(text, m.end())
        name = _strip_unbalanced_parens(prefix + text[m.start("suf"):end])
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
    """主体标识：去掉公司词尾，再去掉开头的弱连接词。**保留行政区划前缀**。

    保留区划是为了区分「中国建筑」与「中国建筑科技」：
    两者字号互为前缀，只有保留区划才能看出前者不是简称。
    """
    n = normalize_name(name)
    n = _strip_suffix(n)
    n = _strip_leading_weak(n)
    return n


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
    return not any(w in head for w in _WEAK_CONNECTORS)


def same_entity(a: str, b: str) -> bool:
    """两个名称是否指向同一主体。

    核心字号相等即同一主体。此外两种关系也算：
    - 互为**后缀**且多出来的部分不含弱连接词：
      带连接词前缀的同一写法与干净写法（「由北京华信科技」）
    - 互为**前缀**且较短一方像简称（≤3 字，或以行政区划开头）：
      「北京华信」与「北京华信科技有限公司」

    前缀关系不加限制会误并「中国建筑」与「中国建筑科技」，
    所以要求较短一方是简称形态。后缀关系不加限制会误并
    「联合网络通信」与「网络通信」，所以要求多出来的部分不含弱连接词。
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_entities.py -v`
Expected: PASS，6 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/entities.py tests/test_entities.py
git commit -m "feat: add company name extraction and variant clustering"
```

---

## Task 7: schema.py — finding 结构校验

**Files:**
- Create: `scripts/schema.py`
- Create: `tests/test_schema.py`

**Interfaces:**
- Consumes: `common.finding_id`
- Produces:
  - `schema.SEVERITIES: list[str]` = `["P0", "P1", "P2", "P3"]`
  - `schema.CONFIDENCES: list[str]` = `["确定", "疑似 · 需人工核实"]`
  - `schema.DETECTORS: list[str]` = `["deterministic", "llm"]`
  - `schema.validate_findings(data: list[dict]) -> list[str]` — 返回错误字符串列表，空列表表示通过
  - `schema.make_finding(**fields) -> dict` — 构造并补齐 `id`
  - `schema.fingerprint(finding: dict) -> str`

- [ ] **Step 1: 写失败的测试**

`tests/test_schema.py`:
```python
from schema import make_finding, validate_findings


def _valid():
    return make_finding(
        severity="P2", category="字体一致性", detector="deterministic",
        confidence="确定", file="a.docx",
        locator={"type": "paragraph", "index": 3, "section_path": "第一章"},
        quote="正文片段", description="描述", suggestion="建议",
    )


def test_make_finding_sets_id():
    f = _valid()
    assert len(f["id"]) == 16
    assert f["id"] == make_finding(
        severity="P2", category="字体一致性", detector="deterministic",
        confidence="确定", file="a.docx",
        locator={"type": "paragraph", "index": 3, "section_path": "第一章"},
        quote="正文片段", description="描述", suggestion="建议",
    )["id"]


def test_validate_accepts_valid():
    assert validate_findings([_valid()]) == []


def test_validate_reports_bad_severity():
    f = _valid()
    f["severity"] = "P9"
    errs = validate_findings([f])
    assert len(errs) == 1
    assert "P9" in errs[0]


def test_validate_reports_missing_field():
    f = _valid()
    del f["suggestion"]
    errs = validate_findings([f])
    assert any("suggestion" in e for e in errs)


def test_validate_reports_locator_without_type():
    f = _valid()
    f["locator"] = {"index": 1}
    errs = validate_findings([f])
    assert any("locator" in e for e in errs)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_schema.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'schema'`

- [ ] **Step 3: 实现 schema.py**

`scripts/schema.py`:
```python
"""finding 结构校验。consistency.json 与 findings.json 共用同一套 schema。"""
from __future__ import annotations

from common import finding_id

SEVERITIES = ["P0", "P1", "P2", "P3"]
CONFIDENCES = ["确定", "疑似 · 需人工核实"]
DETECTORS = ["deterministic", "llm"]
REQUIRED_FIELDS = [
    "id", "severity", "category", "detector", "confidence",
    "file", "locator", "quote", "description", "suggestion",
]


def make_finding(**fields) -> dict:
    f = {
        "id": "",
        "severity": "P3",
        "category": "",
        "detector": "llm",
        "confidence": "疑似 · 需人工核实",
        "file": "",
        "locator": {"type": "file"},
        "quote": "",
        "description": "",
        "suggestion": "",
    }
    f.update(fields)
    f["id"] = finding_id(f["file"], f["category"], f["locator"], f["quote"])
    return f


def fingerprint(finding: dict) -> str:
    return finding_id(
        finding.get("file", ""),
        finding.get("category", ""),
        finding.get("locator") or {"type": "file"},
        finding.get("quote", ""),
    )


def validate_findings(data) -> list[str]:
    """返回错误字符串列表。空列表表示通过。"""
    errors: list[str] = []
    if not isinstance(data, list):
        return ["findings 必须是数组"]
    for i, f in enumerate(data):
        prefix = f"第 {i + 1} 条"
        if not isinstance(f, dict):
            errors.append(f"{prefix}：不是对象")
            continue
        for key in REQUIRED_FIELDS:
            if key not in f:
                errors.append(f"{prefix}：缺少字段 {key}")
        if f.get("severity") not in SEVERITIES:
            errors.append(f"{prefix}：severity 非法 {f.get('severity')!r}，允许 {SEVERITIES}")
        if f.get("detector") not in DETECTORS:
            errors.append(f"{prefix}：detector 非法 {f.get('detector')!r}，允许 {DETECTORS}")
        if f.get("confidence") not in CONFIDENCES:
            errors.append(f"{prefix}：confidence 非法 {f.get('confidence')!r}，允许 {CONFIDENCES}")
        loc = f.get("locator")
        if not isinstance(loc, dict) or not loc.get("type"):
            errors.append(f"{prefix}：locator 必须含 type")
    return errors
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_schema.py -v`
Expected: PASS，5 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/schema.py tests/test_schema.py
git commit -m "feat: add finding schema validation shared by both detectors"
```

---

## Task 8: analyze.py — 样式与段落格式一致性

**Files:**
- Create: `scripts/analyze.py`
- Create: `tests/test_analyze_style.py`

**Interfaces:**
- Consumes: `schema.make_finding`, `common.normalize_text`
- Produces:
  - `analyze.analyze(documents: list[dict]) -> dict` — 返回 `{style_profile, issues, entities, stats}`
  - `analyze.style_fingerprint(style: dict) -> tuple`
  - `analyze.dominant(blocks, key) -> dict` — 取值频次最高的值

- [ ] **Step 1: 写失败的测试**

`tests/test_analyze_style.py`:
```python
from analyze import analyze


def _doc(name, blocks):
    return {
        "file": name, "type": "docx", "sha256": "0" * 64, "title": "",
        "stats": {"paragraphs": len(blocks), "tables": 0, "pages": 1,
                  "words": 100, "rows": 0, "sheets": 0},
        "sections": [], "blocks": blocks,
        "entities": [], "citations": [], "numbers": [], "notes": [],
    }


def _style(**kw):
    base = {
        "font_latin": "Times New Roman", "font_ea": "宋体", "size_pt": 12.0,
        "bold": False, "italic": False, "align": "both",
        "indent_left_pt": 0.0, "indent_first_pt": 24.0, "line_spacing": 1.5,
        "space_before_pt": 0.0, "space_after_pt": 0.0, "style_name": "正文",
        "is_heading": False, "heading_level": 0, "list_numbered": False,
        "confidence": "high",
    }
    base.update(kw)
    return base


def _para(text, style):
    return {"index": 0, "kind": "paragraph", "text": text, "style": style,
            "section_path": "第一章"}


def test_analyze_reports_font_deviation():
    docs = [
        _doc("a.docx", [
            _para("正常段落一", _style()),
            _para("正常段落二", _style()),
            _para("异常字体段落", _style(font_ea="仿宋")),
        ])
    ]
    result = analyze(docs)
    cats = [i["category"] for i in result["issues"]]
    assert "字体一致性" in cats
    issue = next(i for i in result["issues"] if i["category"] == "字体一致性")
    assert issue["file"] == "a.docx"
    assert issue["severity"] == "P2"
    assert issue["detector"] == "deterministic"


def test_analyze_no_issue_when_all_same():
    docs = [_doc("a.docx", [_para(f"段落{i}", _style()) for i in range(5)])]
    result = analyze(docs)
    assert result["issues"] == []


def test_analyze_reports_line_spacing_deviation():
    docs = [
        _doc("a.docx", [
            _para("正常", _style()),
            _para("正常", _style()),
            _para("行距不同", _style(line_spacing=1.0)),
        ])
    ]
    result = analyze(docs)
    assert any(i["category"] == "段落格式一致性" for i in result["issues"])


def test_analyze_ignores_low_confidence_styles():
    docs = [_doc("a.pdf", [_para("页内容", _style(confidence="low", font_ea=None))])]
    result = analyze(docs)
    assert result["issues"] == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_analyze_style.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'analyze'`

- [ ] **Step 3: 实现 analyze.py 的样式部分**

`scripts/analyze.py`:
```python
"""确定性检查：样式一致性、段���格式一致性、体例规则、主体名。

本文件在后续任务中继续扩展，先落地样式与段落格式两块。
"""
from __future__ import annotations

from collections import Counter

from schema import make_finding

# 参与一致性比对的样式字段
_FONT_KEYS = ("font_latin", "font_ea", "size_pt")
_PARA_KEYS = ("align", "indent_left_pt", "indent_first_pt",
              "line_spacing", "space_before_pt", "space_after_pt")

_FIELD_LABELS = {
    "font_latin": "西文字体",
    "font_ea": "中文字体",
    "size_pt": "字号",
    "align": "对齐方式",
    "indent_left_pt": "左缩进",
    "indent_first_pt": "首行缩进",
    "line_spacing": "行距",
    "space_before_pt": "段前距",
    "space_after_pt": "段后距",
}


def _iter_paragraph_blocks(documents):
    for doc in documents:
        for b in doc.get("blocks", []):
            if b.get("kind") != "paragraph":
                continue
            style = b.get("style")
            if not style or style.get("confidence") != "high":
                continue
            yield doc, b, style


def dominant(documents, key: str) -> tuple[object, int, int]:
    """返回 (主流值, 主流值出现次数, 参与统计的段落总数)。"""
    counter: Counter = Counter()
    total = 0
    for _, _, style in _iter_paragraph_blocks(documents):
        total += 1
        counter[style.get(key)] += 1
    if not counter:
        return None, 0, 0
    value, count = counter.most_common(1)[0]
    return value, count, total


def style_fingerprint(style: dict) -> tuple:
    return tuple(style.get(k) for k in _FONT_KEYS + _PARA_KEYS)


def _fmt(value) -> str:
    if value is None:
        return "未设置"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _collect_deviations(documents, keys, category, severity, min_ratio=0.6):
    """统计偏离主流值的段落。偏离比例低于 min_ratio 的字段不报，避免个别段落误报。"""
    issues = []
    for key in keys:
        counter: Counter = Counter()
        total = 0
        for _, _, style in _iter_paragraph_blocks(documents):
            total += 1
            counter[style.get(key)] += 1
        if total < 3:
            continue
        main_value, main_count, _ = counter.most_common(1)[0]
        if main_count / total < min_ratio:
            continue
        for doc, block, style in _iter_paragraph_blocks(documents):
            actual = style.get(key)
            if actual == main_value:
                continue
            issues.append(make_finding(
                severity=severity,
                category=category,
                detector="deterministic",
                confidence="确定",
                file=doc["file"],
                locator={
                    "type": "paragraph",
                    "index": block["index"],
                    "section_path": block.get("section_path", ""),
                    "field": key,
                },
                quote=block.get("text", "")[:60],
                description=(
                    f"{_FIELD_LABELS.get(key, key)}与全文主流值不一致："
                    f"本处为「{_fmt(actual)}」，主流值为「{_fmt(main_value)}」"
                    f"（{main_count}/{total} 段）。"
                ),
                suggestion=f"统一改为「{_fmt(main_value)}」。",
            ))
    return issues


def analyze(documents: list[dict]) -> dict:
    issues = []
    issues += _collect_deviations(documents, _FONT_KEYS, "字体一致性", "P2")
    issues += _collect_deviations(documents, _PARA_KEYS, "段落格式一致性", "P2")

    profile = {}
    for key in _FONT_KEYS + _PARA_KEYS:
        value, count, total = dominant(documents, key)
        profile[key] = {
            "label": _FIELD_LABELS.get(key, key),
            "dominant": value,
            "count": count,
            "total": total,
        }

    return {
        "style_profile": profile,
        "issues": issues,
        "entities": {},
        "stats": {"documents": len(documents), "issues": len(issues)},
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_analyze_style.py -v`
Expected: PASS，4 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/analyze.py tests/test_analyze_style.py
git commit -m "feat: add deterministic style and paragraph format checks"
```

---

## Task 9: analyze.py — 体例规则

**Files:**
- Modify: `scripts/analyze.py`
- Create: `tests/test_analyze_convention.py`

**Interfaces:**
- Consumes: `schema.make_finding`, `analyze.analyze`
- Produces: `analyze.check_conventions(documents: list[dict]) -> list[dict]`

规则编号体系：`1.` / `一、` / `（一）` / `第一章`
图表题注：`图1-1` / `图 1-1` / `图1.1` / `图1－1` / `Figure`
引用标记：`[1]` / `（1）` / `文献[1]` / `[1-3]`
数字单位：`万元` / `元`；日期 `2024年1月1日` / `2024-01-01` / `2024/01/01`

本任务覆盖 spec §5.3 的六类：标题层级体例、图表题注体例、引用标记、数字与单位、表格体例、列表与编号。术语与缩写一并在此实现。

- [ ] **Step 1: 写失败的测试**

`tests/test_analyze_convention.py`:
```python
from analyze import analyze


def _doc(name, blocks):
    return {
        "file": name, "type": "docx", "sha256": "0" * 64, "title": "",
        "stats": {"paragraphs": len(blocks), "tables": 0, "pages": 1,
                  "words": 100, "rows": 0, "sheets": 0},
        "sections": [], "blocks": blocks,
        "entities": [], "citations": [], "numbers": [], "notes": [],
    }


def _p(text):
    return {"index": 0, "kind": "paragraph", "text": text, "style": None,
            "section_path": "第一章"}


def _cats(result):
    return [i["category"] for i in result["issues"]]


def test_heading_numbering_systems_mixed():
    # 「1.1 式」与「（一）式」都在第 4 层，同层混用才是体例不一致
    docs = [_doc("a.docx", [
        _p("第一章 总则"),
        _p("一、总体要求"),
        _p("1. 适用范围"),
        _p("（一）背景说明"),
        _p("1.1 实施进度"),
    ])]
    result = analyze(docs)
    issue = next(i for i in result["issues"] if i["category"] == "标题层级体例")
    assert "编号体系" in issue["description"]


def test_standard_four_level_structure_is_not_flagged():
    # 标准的四级结构不是体例不一致，不能每份文档都报
    docs = [_doc("a.docx", [
        _p("第一章 总则"),
        _p("一、总体要求"),
        _p("1. 适用范围"),
        _p("（一）背景说明"),
    ])]
    result = analyze(docs)
    assert [i for i in result["issues"] if i["category"] == "标题层级体例"] == []


def test_heading_level_jump_is_flagged():
    doc = _doc("a.docx", [])
    doc["blocks"] = [
        {"index": 0, "kind": "paragraph", "text": "第一章 总则", "section_path": "",
         "style": {"is_heading": True, "heading_level": 1}},
        {"index": 1, "kind": "paragraph", "text": "3.1 实施", "section_path": "",
         "style": {"is_heading": True, "heading_level": 3}},
    ]
    result = analyze([doc])
    issue = next(i for i in result["issues"] if i["category"] == "标题层级体例")
    assert "跳级" in issue["description"]


def test_figure_numbering_gap_is_flagged():
    docs = [_doc("a.docx", [
        _p("图1-1 总体架构"),
        _p("图1-3 数据流"),
    ])]
    result = analyze(docs)
    issue = next(i for i in result["issues"] if i["category"] == "图表题注体例")
    assert "缺号" in issue["description"]


def test_caption_number_not_followed_by_counter_is_ignored():
    # 「见图 3 节」「（2）个标段」「（2024）」都不是编号
    docs = [_doc("a.docx", [
        _p("见图 3 节可知。"),
        _p("本项目分为（2）个标段。"),
        _p("签署时间（2024）。"),
    ])]
    result = analyze(docs)
    cats = [i["category"] for i in result["issues"]]
    assert "图表题注体例" not in cats
    assert "引用标记" not in cats


def test_figure_caption_styles_mixed():
    docs = [_doc("a.docx", [
        _p("如图1-1所示"),
        _p("如图 1-2 所示"),
        _p("如图1.3所示"),
    ])]
    result = analyze(docs)
    assert "图表题注体例" in _cats(result)


def test_citation_marker_styles_mixed():
    docs = [_doc("a.docx", [
        _p("相关依据[1]说明"),
        _p("相关规定（2）明确"),
        _p("文献[3]指出"),
    ])]
    result = analyze(docs)
    assert "引用标记" in _cats(result)


def test_currency_unit_mixed():
    docs = [_doc("a.docx", [
        _p("合同金额 120 万元。"),
        _p("本次费用 3000 元。"),
    ])]
    result = analyze(docs)
    assert "数字与单位" in _cats(result)


def test_date_format_mixed():
    docs = [_doc("a.docx", [
        _p("签署日期 2024年1月1日。"),
        _p("生效日期 2024-01-01。"),
    ])]
    result = analyze(docs)
    assert "数字与单位" in _cats(result)


def test_currency_regex_only_matches_yuan():
    # 「3单元」「100美元」不是人民币金额，不该触发货币混用
    docs = [_doc("a.docx", [
        _p("本项目分为 3单元。"),
        _p("合同金额 100美元。"),
    ])]
    result = analyze(docs)
    assert "数字与单位" not in _cats(result)


def test_uniform_document_has_no_convention_issue():
    docs = [_doc("a.docx", [
        _p("1. 适用范围"),
        _p("如图1-1所示"),
        _p("依据[1]说明"),
    ])]
    result = analyze(docs)
    assert _cats(result) == []


def _table(rows):
    return {
        "index": 0, "kind": "table", "text": "",
        "rows": [[{"text": c, "style": {"bold": b}} for c, b in row]
                 for row in rows],
    }


def test_table_header_style_inconsistent():
    doc = _doc("a.docx", [])
    doc["blocks"] = [
        _table([[("项目", True), ("数量", True)], [("设备", False), ("10", False)]]),
        _table([[("名称", True), ("数量", True)], [("设备", False), ("10", False)]]),
        _table([[("序号", False), ("数量", False)], [("设备", False), ("10", False)]]),
    ]
    result = analyze([doc])
    assert "表格体例" in _cats(result)


def test_list_numbering_style_mixed():
    doc = _doc("a.docx", [])
    doc["blocks"] = [
        {"index": 0, "kind": "paragraph", "text": "1. 第一项", "style": None,
         "section_path": "第一章", "list_numbered": True},
        {"index": 1, "kind": "paragraph", "text": "2. 第二项", "style": None,
         "section_path": "第一章", "list_numbered": True},
        {"index": 2, "kind": "paragraph", "text": "一、第三项", "style": None,
         "section_path": "第一章", "list_numbered": True},
    ]
    result = analyze([doc])
    assert "列表与编号" in _cats(result)


def test_undefined_abbreviation_flagged():
    doc = _doc("a.docx", [
        _p("本项目严格执行 GB 标准执行。"),
    ])
    result = analyze([doc])
    issue = next(i for i in result["issues"] if i["category"] == "术语与缩写")
    assert "GB" in issue["description"]


def test_defined_abbreviation_not_flagged():
    doc = _doc("a.docx", [
        _p("国家标准（GB）为行业通用标准。"),
    ])
    result = analyze([doc])
    assert [i for i in result["issues"] if i["category"] == "术语与缩写"] == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_analyze_convention.py -v`
Expected: FAIL，测试用例失败（缺少对应 category）

- [ ] **Step 3: 实现体例规则**

在 `scripts/analyze.py` 顶部追加常量与规则函数：

```python
import re

# 标题编号体系，附「隐含层级」。
#
# 同一层级用两种写法才是体例不一致；不同层级出现不同写法是正常结构。
# 「第一章 / 一、 / 1. /（一）」是标准的四级结构，跨层比较写法
# 会把每一份结构正常的中文文档都报成体例不一致。
_HEADING_PATTERNS = [
    ("第一章式", re.compile(r"^第[一二三四五六七八九十百]+章"), 1),
    ("一、式", re.compile(r"^[一二三四五六七八九十]+、"), 2),
    ("1. 式", re.compile(r"^\d+[.、]\s"), 3),
    ("（一）式", re.compile(r"^[（(][一二三四五六七八九十]+[）)]"), 4),
    ("1.1 式", re.compile(r"^\d+\.\d+[.、]?\s"), 4),
]

# 图表题注写法
#
# 序号后面若紧跟量词或量类（个/条/节/页…），那不是编号，
# 「见图 3 节」「（2）个标段」这类会被误判成题注或引用。
_NOT_A_NUMBER_TAIL = r"(?!\s*[个条项处次段章节份件标页类])"

_CAPTION_PATTERNS = [
    ("图N-N", re.compile(r"图\s*\d+[-－]\d+" + _NOT_A_NUMBER_TAIL)),
    ("图N.N", re.compile(r"图\s*\d+\.\d+")),
    ("图N", re.compile(r"图\s*\d+" + _NOT_A_NUMBER_TAIL)),
    ("表N-N", re.compile(r"表\s*\d+[-－]\d+" + _NOT_A_NUMBER_TAIL)),
    ("表N.N", re.compile(r"表\s*\d+\.\d+")),
    ("表N", re.compile(r"表\s*\d+" + _NOT_A_NUMBER_TAIL)),
]

# 引用标记写法。序号限三位数，避免把年份「（2024）」当引用。
_CITATION_PATTERNS = [
    ("文献[n]", re.compile(r"文献\[\d+\]")),
    ("[n]", re.compile(r"\[\d+(?:[-–—,，]\d+)*\]")),
    ("（n）", re.compile(r"[（(]\d{1,3}[）)]" + _NOT_A_NUMBER_TAIL)),
]

_DATE_PATTERNS = [
    ("2024年1月1日", re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日")),
    ("2024-01-01", re.compile(r"\d{4}-\d{2}-\d{2}")),
    ("2024/01/01", re.compile(r"\d{4}/\d{2}/\d{2}")),
    ("2024.01.01", re.compile(r"\d{4}\.\d{2}\.\d{2}")),
]

_CURRENCY_RE = re.compile(r"\d[\d,，.]*\s*(万元|元)")


def _text_blocks(documents):
    for doc in documents:
        for b in doc.get("blocks", []):
            if b.get("kind") == "paragraph" and b.get("text"):
                yield doc, b


def _classify(text, patterns):
    """返回匹配到的体系名。patterns 的元素为 (label, regex) 或 (label, regex, depth)。

    用 search 而非 match：图表题注与引用标记常出现在句子中间
    （「如图1-1所示」），锚在行首会让这两条规则永远不触发。
    标题规则自带 ^，search 对它们仍然等价于行首匹配。
    """
    for item in patterns:
        label, rx = item[0], item[1]
        if rx.search(text.strip()):
            return label
    return None


def _classify_depth(text, patterns):
    """返回 (体系名, 隐含层级)。patterns 元素为 (label, regex, depth)。"""
    for label, rx, depth in patterns:
        if rx.search(text.strip()):
            return label, depth
    return None, None


def _mixed_style_issue(documents, category, patterns, severity, sample=3, prefix=""):
    """若同一文件内出现两种以上写法，报告一次文件级问题。"""
    issues = []
    for doc in documents:
        seen: dict[str, list[str]] = {}
        for _, b in _text_blocks([doc]):
            label = _classify(b["text"], patterns)
            if label:
                seen.setdefault(label, []).append(b["text"].strip()[:40])
        if len(seen) < 2:
            continue
        labels = sorted(seen)
        sample_texts = [t for v in seen.values() for t in v][:sample]
        issues.append(make_finding(
            severity=severity,
            category=category,
            detector="deterministic",
            confidence="确定",
            file=doc["file"],
            locator={"type": "file"},
            quote=sample_texts[0] if sample_texts else "",
            description=(
                f"{prefix}在同一文件内出现 {len(labels)} 种写法："
                + "、".join(labels)
                + "。示例：" + "；".join(sample_texts)
            ),
            suggestion=f"统一为其中一种写法，全套文档保持一致。",
        ))
    return issues


_ABBR_RE = re.compile(r"(?<![A-Za-z])[A-Z]{2,6}(?![A-Za-z])")
_DEFINED_ABBR_RE = re.compile(r"[（(]([A-Z]{2,6})[）)]")
# 通用缩写不算「未给全称」，避免误报
_ABBR_STOPLIST = {
    "PDF", "ISO", "XML", "HTML", "URL", "API", "KPI", "ROI", "TBD", "CPU",
    "RAM", "SSD", "LED", "CAD", "CAM", "PLC", "TCP", "UDP", "HTTP", "HTTPS",
}


_HEADER_LABELS = {
    "bold": "全部加粗",
    "not-bold": "不加粗",
    "mixed": "部分加粗",
    "empty": "空表头",
}


def _header_signature(first: list[dict]) -> str:
    """表头样式指纹：只看加粗与否，不看列数。

    列数不同的表，其表头写法可能完全一致；把列数算进指纹会把
    宽度不同的表误报成体例不一致，描述还会自相矛盾
    （「主流为 加粗，本表为 加粗」）。
    """
    if not first:
        return "empty"
    bold = sum(1 for c in first if (c.get("style") or {}).get("bold"))
    if bold == 0:
        return "not-bold"
    if bold == len(first):
        return "bold"
    return "mixed"


def check_tables(documents: list[dict]) -> list[dict]:
    """表格体例：各表首行的加粗写法应一致。"""
    issues = []
    signatures = []
    for doc in documents:
        for b in doc.get("blocks", []):
            if b.get("kind") != "table":
                continue
            rows = b.get("rows") or []
            if not rows:
                continue
            first = rows[0]
            if not any((c.get("style") or {}).get("bold") is not None for c in first):
                continue
            signatures.append((doc["file"], b["index"], _header_signature(first)))
    if len(signatures) < 2:
        return issues
    counts = Counter(sig for _, _, sig in signatures)
    main_sig, main_count = counts.most_common(1)[0]
    if main_count / len(signatures) < 0.6:
        return issues
    for fname, idx, sig in signatures:
        if sig == main_sig:
            continue
        issues.append(make_finding(
            severity="P2", category="表格体例", detector="deterministic",
            confidence="确定", file=fname,
            locator={"type": "table", "index": idx, "row": 1},
            quote="",
            description=(
                f"该表首行样式与全文主流写法不一致：主流为「{_HEADER_LABELS[main_sig]}」，"
                f"本表为「{_HEADER_LABELS[sig]}」。"
            ),
            suggestion="统一表头行的加粗写法。",
        ))
    return issues


def check_list_numbering(documents: list[dict]) -> list[dict]:
    """列表与编号：有序列表的编号方式应一致。"""
    issues = []
    for doc in documents:
        styles: dict[str, list[str]] = {}
        for b in doc.get("blocks", []):
            if b.get("kind") != "paragraph":
                continue
            if not ((b.get("style") or {}).get("list_numbered") or b.get("list_numbered")):
                continue
            label = _classify(b.get("text", ""), _HEADING_PATTERNS)
            if label:
                styles.setdefault(label, []).append(b["text"].strip()[:40])
        if len(styles) < 2:
            continue
        labels = sorted(styles)
        issues.append(make_finding(
            severity="P2", category="列表与编号", detector="deterministic",
            confidence="确定", file=doc["file"], locator={"type": "file"},
            quote=list(styles.values())[0][0],
            description=(
                f"有序列表的编号方式混用：{'、'.join(labels)}。"
            ),
            suggestion="统一有序列表的编号方式。",
        ))
    return issues


def check_abbreviations(documents: list[dict]) -> list[dict]:
    """术语与缩写：英文缩写首次出现应给出全称。

    「首次出现时应给出全称」——定义出现在首次出现之后的段落不算数。
    缩写本身放进 locator，避免同一段里两个缩写撞指纹。
    """
    issues = []
    for doc in documents:
        para_defs: list[set[str]] = []
        para_tokens: list[list[str]] = []
        for _, b in _text_blocks([doc]):
            text = b.get("text", "")
            para_defs.append({m.group(1) for m in _DEFINED_ABBR_RE.finditer(text)})
            para_tokens.append([
                m.group(0) for m in _ABBR_RE.finditer(text)
                if m.group(0) not in _ABBR_STOPLIST
            ])

        defined_upto: set[str] = set()
        reported: set[str] = set()
        for i, tokens in enumerate(para_tokens):
            defined_upto |= para_defs[i]   # 本段给出的定义也算
            for token in tokens:
                if token in reported:
                    continue
                reported.add(token)
                if token in defined_upto:
                    continue
                issues.append(make_finding(
                    severity="P3", category="术语与缩写", detector="deterministic",
                    confidence="确定", file=doc["file"],
                    locator={"type": "file", "abbreviation": token},
                    quote="",
                    description=f"缩写「{token}」首次出现时未给出全称。",
                    suggestion=f"首次出现时写为「中文全称（{token}）」。",
                ))
    return issues


def check_heading_numbering(documents: list[dict]) -> list[dict]:
    """标题层级体例：同一层级的编号写法必须一致。

    不同层级出现不同写法是正常结构（第一章 / 一、 / 1. /（一）），
    只有同一层级混用两种写法才是体例不一致。
    """
    issues = []
    for doc in documents:
        by_depth: dict[int, dict[str, list[str]]] = {}
        for _, b in _text_blocks([doc]):
            label, depth = _classify_depth(b.get("text", ""), _HEADING_PATTERNS)
            if label is None:
                continue
            by_depth.setdefault(depth, {}).setdefault(label, []).append(
                b.get("text", "").strip()[:40]
            )
        for depth, styles in sorted(by_depth.items()):
            if len(styles) < 2:
                continue
            labels = sorted(styles)
            samples = [t for v in styles.values() for t in v][:3]
            issues.append(make_finding(
                severity="P2", category="标题层级体例", detector="deterministic",
                confidence="确定", file=doc["file"], locator={"type": "file"},
                quote=samples[0],
                description=(
                    f"同一层级的标题编号体系混用：{'、'.join(labels)}。"
                    f"示例：{'；'.join(samples)}"
                ),
                suggestion="统一同一层级的标题编号写法。",
            ))
    return issues


_FIG_NUM_RE = re.compile(r"[图表]\s*(\d+)[-－](\d+)")


def check_heading_level_jumps(documents: list[dict]) -> list[dict]:
    """标题层级体例：标题层级不得跳级（如 H1 直接跳 H3）。"""
    issues = []
    for doc in documents:
        prev_level = 0
        prev_heading = ""
        for _, b in _text_blocks([doc]):
            style = b.get("style") or {}
            if not style.get("is_heading"):
                continue
            level = int(style.get("heading_level") or 0)
            if level <= 0:
                continue
            if prev_level and level > prev_level + 1:
                issues.append(make_finding(
                    severity="P2", category="标题层级体例", detector="deterministic",
                    confidence="确定", file=doc["file"],
                    locator={"type": "paragraph", "index": b.get("index", 0),
                             "section_path": b.get("section_path", "")},
                    quote=b.get("text", "")[:60],
                    description=(
                        f"标题层级跳级：上一级标题是第 {prev_level} 级"
                        f"（{prev_heading}），本处直接是第 {level} 级。"
                    ),
                    suggestion="补齐缺失的中间层级，或调整本标题的级别。",
                ))
            prev_level = level
            prev_heading = b.get("text", "").strip()[:20]
    return issues


def check_figure_numbering_gaps(documents: list[dict]) -> list[dict]:
    """图表题注体例：图表编号应连续，不应跳号。"""
    issues = []
    for doc in documents:
        by_chapter: dict[str, list[int]] = {}
        for _, b in _text_blocks([doc]):
            for m in _FIG_NUM_RE.finditer(b.get("text", "")):
                by_chapter.setdefault(m.group(1), []).append(int(m.group(2)))
        for chapter, nums in sorted(by_chapter.items()):
            uniq = sorted(set(nums))
            if len(uniq) < 2:
                continue
            missing = [n for n in range(1, uniq[-1] + 1) if n not in uniq]
            if not missing:
                continue
            issues.append(make_finding(
                severity="P2", category="图表题注体例", detector="deterministic",
                confidence="确定", file=doc["file"], locator={"type": "file"},
                quote=f"图{chapter}-{uniq[0]}",
                description=(
                    f"第 {chapter} 章的图表编号不连续，缺号："
                    + "、".join(str(n) for n in missing)
                    + f"（现有编号到 {uniq[-1]}）。"
                ),
                suggestion="补齐缺号，或重新连续编号。",
            ))
    return issues


def check_conventions(documents: list[dict]) -> list[dict]:
    issues = []
    issues += check_heading_numbering(documents)
    issues += check_heading_level_jumps(documents)
    issues += check_figure_numbering_gaps(documents)
    issues += _mixed_style_issue(
        documents, "图表题注体例", _CAPTION_PATTERNS, "P2", prefix="图表题注写法"
    )
    issues += _mixed_style_issue(
        documents, "引用标记", _CITATION_PATTERNS, "P2", prefix="引用标记写法"
    )
    issues += check_tables(documents)
    issues += check_list_numbering(documents)
    issues += check_abbreviations(documents)

    for doc in documents:
        currencies: dict[str, list[str]] = {}
        dates: dict[str, list[str]] = {}
        for _, b in _text_blocks([doc]):
            for m in _CURRENCY_RE.finditer(b["text"]):
                currencies.setdefault(m.group(1), []).append(m.group(0))
            for label, rx in _DATE_PATTERNS:
                hit = rx.search(b["text"])
                if hit:
                    dates.setdefault(label, []).append(hit.group(0))
        if len(currencies) >= 2:
            issues.append(make_finding(
                severity="P1", category="数字与单位", detector="deterministic",
                confidence="确定", file=doc["file"], locator={"type": "file"},
                quote=list(currencies.values())[0][0],
                description=(
                    "同一文件内货币单位混用："
                    + "、".join(f"{k}（{len(v)} 处）" for k, v in sorted(currencies.items()))
                    + "。单位混用可能导致金额理解偏差。"
                ),
                suggestion="统一使用「万元」或「元」，并在文档开头注明单位口径。",
            ))
        if len(dates) >= 2:
            issues.append(make_finding(
                severity="P2", category="数字与单位", detector="deterministic",
                confidence="确定", file=doc["file"], locator={"type": "file"},
                quote=list(dates.values())[0][0],
                description=(
                    "同一文件内日期格式混用："
                    + "、".join(sorted(dates))
                    + "。"
                ),
                suggestion="统一日期格式，建议全文使用「2024年1月1日」。",
            ))
    return issues
```

在 `analyze()` 函数中追加调用：

```python
    issues += check_conventions(documents)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_analyze_convention.py tests/test_analyze_style.py -v`
Expected: PASS，14 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/analyze.py tests/test_analyze_convention.py
git commit -m "feat: add convention checks for headings captions citations and units"
```

---

## Task 10: analyze.py — 主体名发现与混主体判定

**Files:**
- Modify: `scripts/analyze.py`
- Create: `tests/test_analyze_entities.py`

**Interfaces:**
- Consumes: `entities.extract_company_names`, `entities.group_variants`, `schema.make_finding`
- Produces: `analyze.check_entities(documents: list[dict]) -> tuple[list[dict], dict]`

规则：

- 同一主体出现 ≥2 种写法变体 → category「主体名称」，severity P1，confidence「确定」
- 同一文件内出现 ≥2 个不同核心字号的主体名 → category「主体串写」，severity P0，confidence「疑似 · 需人工核实」
- 同一主体名在 ≥2 个文件出现但写法变体并存 → P1 跨文件不一致

- [ ] **Step 1: 写失败的测试**

`tests/test_analyze_entities.py`:
```python
from analyze import analyze


def _doc(name, texts):
    blocks = [
        {"index": i, "kind": "paragraph", "text": t, "style": None,
         "section_path": "第一章"}
        for i, t in enumerate(texts)
    ]
    return {
        "file": name, "type": "docx", "sha256": "0" * 64, "title": "",
        "stats": {"paragraphs": len(blocks), "tables": 0, "pages": 1,
                  "words": 50, "rows": 0, "sheets": 0},
        "sections": [], "blocks": blocks,
        "entities": [], "citations": [], "numbers": [], "notes": [],
    }


def test_name_variant_mismatch_is_p1():
    docs = [_doc("a.docx", [
        "本项目由北京华信科技有限公司负责。",
        "北京华信科技有限责任公司将提供支持。",
    ])]
    result = analyze(docs)
    issue = next(i for i in result["issues"] if i["category"] == "主体名称")
    assert issue["severity"] == "P1"
    assert issue["confidence"] == "确定"


def test_two_entities_in_one_file_flagged_p0():
    docs = [_doc("a.docx", [
        "北京华信科技有限公司为主体。",
        "上海远大信息技术有限公司为协作方。",
    ])]
    result = analyze(docs)
    issue = next(i for i in result["issues"] if i["category"] == "主体串写")
    assert issue["severity"] == "P0"
    assert issue["confidence"] == "疑似 · 需人工核实"


def test_entity_summary_returned():
    docs = [_doc("a.docx", ["北京华信科技有限公司负责本项目。"])]
    result = analyze(docs)
    names = [n["name"] for n in result["entities"]["names"]]
    assert "北京华信科技有限公司" in names
    assert result["entities"]["names"][0]["count"] == 1
    assert result["entities"]["names"][0]["files"] == ["a.docx"]


def test_no_entity_no_issue():
    docs = [_doc("a.docx", ["本段落不含任何公司名称。"])]
    result = analyze(docs)
    assert [i for i in result["issues"] if i["category"] in ("主体名称", "主体串写")] == []


def test_leading_weak_connector_is_not_a_second_entity():
    # 「与上海远大信息技术有限公司」与「上海远大信息技术有限公司」是同一主体，
    # 不能触发混主体，也不能触发写法不统一
    docs = [_doc("a.docx", [
        "本项目与上海远大信息技术有限公司共同承担。",
        "上海远大信息技术有限公司负责实施。",
    ])]
    result = analyze(docs)
    assert [i for i in result["issues"] if i["category"] in ("主体名称", "主体串写")] == []


def test_file_name_distinguishes_entities():
    # 文件名里出现了其中一个主体，说明这些主体是被显式区分的，不报混主体
    doc = _doc("北京华信科技有限公司投标文件.docx", [
        "北京华信科技有限公司为主体。",
        "上海远大信息技术有限公司为协作方。",
    ])
    result = analyze([doc])
    assert [i for i in result["issues"] if i["category"] == "主体串写"] == []


def test_section_heading_distinguishes_entities():
    doc = _doc("a.docx", [
        "北京华信科技有限公司为主体。",
        "上海远大信息技术有限公司为协作方。",
    ])
    doc["sections"] = [{"path": "上海远大信息技术有限公司", "level": 1,
                        "heading": "上海远大信息技术有限公司", "start": 0, "end": 1}]
    result = analyze([doc])
    assert [i for i in result["issues"] if i["category"] == "主体串写"] == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_analyze_entities.py -v`
Expected: FAIL，找不到对应 category

- [ ] **Step 3: 实现主体名检查**

在 `scripts/analyze.py` 追加：

```python
from entities import canonical_core, extract_company_names, group_variants


def check_entities(documents: list[dict]) -> tuple[list[dict], dict]:
    issues: list[dict] = []
    names: dict[str, dict] = {}
    per_file: dict[str, list[str]] = {}
    all_names: list[str] = []
    seen_names: set[str] = set()

    for doc in documents:
        found: list[str] = []
        for _, b in _text_blocks([doc]):
            found.extend(extract_company_names(b.get("text", "")))
        per_file[doc["file"]] = found
        for name in found:
            if name not in seen_names:
                seen_names.add(name)
                all_names.append(name)
            key = canonical_core(name)
            if key not in names:
                names[key] = {"name": name, "core": key, "count": 0, "files": []}
            names[key]["count"] += 1
            if doc["file"] not in names[key]["files"]:
                names[key]["files"].append(doc["file"])

    # 变体聚类必须基于全部原始写法，不能基于按主体标识归并后的名单：
    # 「北京华信科技有限公司」与「北京华信科技有限责任公司」的主体标识相同，
    # 归并后只剩一个名字，写法不统一就再也查不出来了。
    variants = group_variants(all_names)

    for group in variants:
        writings = group.get("canonicals") or group["names"]
        if len(writings) < 2:
            continue
        issues.append(make_finding(
            severity="P1", category="主体名称", detector="deterministic",
            confidence="确定", file=_first_file_for(names, group["names"]),
            locator={"type": "file"},
            quote=group["names"][0],
            description=(
                f"同一主体出现 {len(writings)} 种名称写法："
                + "、".join(writings)
                + "。全套文档应统一使用同一名称。"
            ),
            suggestion=f"统一为正式全称「{writings[0]}」。",
        ))

    for doc in documents:
        groups = group_variants(per_file[doc["file"]])
        if len(groups) >= 2:
            shown = [g["names"][0] for g in groups]
            if _distinguished_by_header(doc, groups):
                continue
            issues.append(make_finding(
                severity="P0", category="主体串写", detector="deterministic",
                confidence="疑似 · 需人工核实", file=doc["file"],
                locator={"type": "file"},
                quote=shown[0],
                description=(
                    f"该文件出现 {len(groups)} 个不同主体："
                    + "、".join(shown[:5])
                    + "。文件名与章节标题中未出现这些主体名称，无法据此区分，疑似写混。"
                ),
                suggestion="确认每个名称的归属，删除与本文件主体无关的名称。",
            ))

    summary = {
        "names": [
            {
                "name": v["name"], "core": v["core"], "count": v["count"],
                "files": v["files"],
            }
            for v in names.values()
        ],
        "variants": variants,
        "per_file": per_file,
    }
    return issues, summary


def _first_file_for(names: dict, group_names: list[str]) -> str:
    for v in names.values():
        if v["name"] in group_names:
            return v["files"][0] if v["files"] else ""
    return ""


def _distinguished_by_header(doc: dict, groups: list[dict]) -> bool:
    """文件名或章节标题中出现了某个主体名，说明这些主体是被显式区分的。

    规范 §5.4：疑似混主体的前提是「未由文件名或章节标题显式区分」。
    """
    header = doc.get("file", "") + " " + " ".join(
        str(s.get("heading", "")) for s in doc.get("sections", [])
    )
    for g in groups:
        candidates = list(g.get("names", []))
        if g.get("core"):
            candidates.append(g["core"])
        for name in candidates:
            if name and name in header:
                return True
    return False
```

在 `analyze()` 中追加调用：

```python
    entity_issues, entity_summary = check_entities(documents)
    issues += entity_issues
```

并把返回值的 `"entities"` 改为 `entity_summary`。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_analyze_entities.py -v`
Expected: PASS，4 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/analyze.py tests/test_analyze_entities.py
git commit -m "feat: add company name discovery and mixed-entity detection"
```

---

## Task 11: chunk.py 分片

**Files:**
- Create: `scripts/chunk.py`
- Create: `tests/test_chunk.py`

**Interfaces:**
- Consumes: `entities.extract_company_names`
- Produces:
  - `chunk.DEPTH_PARAMS: dict[str, dict]` — 每档的 `max_chars` 与 `neighbor_window`
  - `chunk.build_chunks(documents: list[dict], depth: str = "standard") -> list[dict]`

深度参数：

| depth | max_chars | neighbor_window |
|---|---|---|
| quick | 3000 | 0 |
| standard | 3000 | 1 |
| deep | 1200 | 3 |

- [ ] **Step 1: 写失败的测试**

`tests/test_chunk.py`:
```python
from chunk import DEPTH_PARAMS, build_chunks


def _doc(name, texts):
    blocks = [
        {"index": i, "kind": "paragraph", "text": t, "style": None,
         "section_path": "第一章/1.1 节"}
        for i, t in enumerate(texts)
    ]
    return {
        "file": name, "type": "docx", "sha256": "0" * 64, "title": "",
        "stats": {"paragraphs": len(blocks), "tables": 0, "pages": 1,
                  "words": 10, "rows": 0, "sheets": 0},
        "sections": [], "blocks": blocks,
        "entities": [], "citations": [], "numbers": [], "notes": [],
    }


def test_depth_params_defined():
    assert set(DEPTH_PARAMS) == {"quick", "standard", "deep"}
    assert DEPTH_PARAMS["deep"]["max_chars"] < DEPTH_PARAMS["standard"]["max_chars"]


def test_build_chunks_respects_max_chars():
    doc = _doc("a.docx", [f"第{i}段内容。" * 20 for i in range(20)])
    chunks = build_chunks([doc], "standard")
    assert chunks
    assert all(len(c["text"]) <= DEPTH_PARAMS["standard"]["max_chars"] + 200 for c in chunks)


def test_build_chunks_has_neighbors_and_hints():
    doc = _doc("a.docx", ["北京华信科技有限公司负责，金额 1,200.00 元，见[3]。",
                          "第二段。", "第三段。"])
    chunks = build_chunks([doc], "standard")
    first = chunks[0]
    assert "neighbors" in first
    assert "prev" in first["neighbors"] and "next" in first["neighbors"]
    assert "北京华信科技有限公司" in first["entities"]
    assert "1,200.00" in first["numbers"]
    assert "[3]" in first["citations"]


def test_chunk_has_section_path_and_file():
    doc = _doc("a.docx", ["内容。"])
    chunk = build_chunks([doc], "standard")[0]
    assert chunk["file"] == "a.docx"
    assert chunk["section_path"] == "第一章/1.1 节"
    assert chunk["chunk_id"].startswith("a.docx:")


def test_deep_mode_smaller_chunks():
    doc = _doc("a.docx", [f"第{i}段内容。" * 20 for i in range(20)])
    deep = build_chunks([doc], "deep")
    standard = build_chunks([doc], "standard")
    assert len(deep) > len(standard)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_chunk.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'chunk'`

- [ ] **Step 3: 实现 chunk.py**

`scripts/chunk.py`:
```python
"""把文档切成模型可读的片段，附邻接上下文与预标注实体。"""
from __future__ import annotations

import re

from entities import extract_company_names

DEPTH_PARAMS = {
    "quick": {"max_chars": 3000, "neighbor_window": 0},
    "standard": {"max_chars": 3000, "neighbor_window": 1},
    "deep": {"max_chars": 1200, "neighbor_window": 3},
}

_NUMBER_RE = re.compile(r"\d[\d,，.]*\s*(?:%|万元|元|个|台|套|人|年|月|日)?")
_CITATION_RE = re.compile(r"文献\[\d+\]|\[\d+(?:[-–—,，]\d+)*\]|[（(]\d+[）)]|如图\s*[\d.\-－]+[所示]*")


def _citations(text: str) -> list[str]:
    out = []
    for m in _CITATION_RE.finditer(text or ""):
        out.append(m.group(0))
    return out


def _numbers(text: str) -> list[str]:
    out = []
    for m in _NUMBER_RE.finditer(text or ""):
        s = m.group(0).strip()
        if any(ch.isdigit() for ch in s) and len(s) > 1:
            out.append(s)
    return out


def _block_text(block: dict) -> str:
    if block.get("kind") == "table":
        cells = []
        for row in block.get("rows", []):
            cells.append(" | ".join(c.get("text", "") for c in row))
        return "\n".join(cells)
    return block.get("text", "")


def _split_table(block: dict, max_chars: int) -> list[dict]:
    """把超出上限的表格按行拆成多块。

    xlsx 的一个 sheet 就是一个表格块，几千行的表在 deep 档位下
    会成为唯一一块超大分片，模型一次读不完。
    """
    text = _block_text(block)
    if len(text) <= max_chars:
        return [block]
    rows = block.get("rows") or []
    if len(rows) < 2:
        return [block]
    parts: list[dict] = []
    current: list[list[dict]] = []
    size = 0
    for row in rows:
        row_len = sum(len(c.get("text", "")) for c in row) + len(row)
        if current and size + row_len > max_chars:
            parts.append({**block, "rows": current})
            current = []
            size = 0
        current.append(row)
        size += row_len
    if current:
        parts.append({**block, "rows": current})
    return parts


def _neighbors(blocks: list[dict], i: int, window: int) -> dict:
    if window <= 0:
        return {"prev": "", "next": ""}
    prev_text = ""
    next_text = ""
    for j in range(max(0, i - window), i):
        prev_text += _block_text(blocks[j]) + "\n"
    for j in range(i + 1, min(len(blocks), i + 1 + window)):
        next_text += _block_text(blocks[j]) + "\n"
    return {"prev": prev_text.strip(), "next": next_text.strip()}


def build_chunks(documents: list[dict], depth: str = "standard") -> list[dict]:
    params = DEPTH_PARAMS.get(depth, DEPTH_PARAMS["standard"])
    max_chars = params["max_chars"]
    window = params["neighbor_window"]

    chunks: list[dict] = []
    for doc in documents:
        blocks = doc.get("blocks", [])
        buffer: list[dict] = []
        buf_len = 0
        seq = 0

        def flush(buffer):
            nonlocal seq
            if not buffer:
                return
            text_parts = []
            entities: list[str] = []
            numbers: list[str] = []
            citations: list[str] = []
            for b in buffer:
                t = _block_text(b)
                text_parts.append(t)
                entities.extend(extract_company_names(t))
                numbers.extend(_numbers(t))
                citations.extend(_citations(t))
            text = "\n".join(p for p in text_parts if p)
            chunks.append({
                "chunk_id": f"{doc['file']}:{seq}",
                "file": doc["file"],
                "section_path": buffer[0].get("section_path", ""),
                "kind": buffer[0].get("kind", "paragraph"),
                "text": text,
                "style": buffer[0].get("style"),
                "neighbors": _neighbors(blocks, buffer[-1]["index"], window),
                "entities": sorted(set(entities)),
                "numbers": sorted(set(numbers)),
                "citations": sorted(set(citations)),
                "block_indexes": [b["index"] for b in buffer],
            })
            seq += 1

        for block in blocks:
            for piece in _split_table(block, max_chars):
                text = _block_text(piece)
                if buf_len and buf_len + len(text) > max_chars:
                    flush(buffer)
                    buffer = []
                    buf_len = 0
                buffer.append(piece)
                buf_len += len(text) + 1
        flush(buffer)
    return chunks
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_chunk.py -v`
Expected: PASS，5 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/chunk.py tests/test_chunk.py
git commit -m "feat: add chunking with neighbors and entity hints"
```

---

## Task 12: prepare.py — 阶段① CLI

**Files:**
- Create: `scripts/prepare.py`
- Create: `tests/test_prepare.py`

**Interfaces:**
- Consumes: `extractors.extract_document`, `analyze.analyze`, `chunk.build_chunks`, `manifest.build_manifest`
- Produces: `prepare.prepare(files: list[Path], depth: str, work: Path) -> dict`
- CLI: `python scripts/prepare.py --files a.docx b.xlsx [--depth standard] [--work .doc-check-work]`

- [ ] **Step 1: 写失败的测试**

`tests/test_prepare.py`:
```python
import json

import docx

from prepare import prepare


def _make_docx(path, text="正文内容。"):
    d = docx.Document()
    d.add_heading("标题", level=1)
    d.add_paragraph(text)
    d.save(str(path))
    return path


def test_prepare_writes_four_json_files(tmp_path):
    src = _make_docx(tmp_path / "a.docx")
    work = tmp_path / "work"
    result = prepare([src], "standard", work)
    for name in ("docs.json", "consistency.json", "chunks.json", "manifest.json"):
        assert (work / name).exists(), name
    assert result["documents"] == 1


def test_prepare_records_failure_and_continues(tmp_path):
    src = _make_docx(tmp_path / "a.docx")
    bad = tmp_path / "b.docx"
    bad.write_text("not a docx", encoding="utf-8")
    work = tmp_path / "work"
    result = prepare([src, bad], "standard", work)
    assert result["documents"] == 1
    assert result["failures"][0]["file"] == "b.docx"
    assert result["failures"][0]["reason"]


def test_prepare_docs_json_has_blocks(tmp_path):
    src = _make_docx(tmp_path / "a.docx")
    work = tmp_path / "work"
    prepare([src], "standard", work)
    docs = json.loads((work / "docs.json").read_text(encoding="utf-8"))
    assert docs["documents"][0]["blocks"]


def test_prepare_consistency_json_has_issues_list(tmp_path):
    src = _make_docx(tmp_path / "a.docx")
    work = tmp_path / "work"
    prepare([src], "standard", work)
    cons = json.loads((work / "consistency.json").read_text(encoding="utf-8"))
    assert "issues" in cons
    assert "style_profile" in cons


def test_prepare_promotes_ocr_document_to_failure():
    from prepare import _ocr_failure
    doc = {
        "file": "scan.pdf", "path": "scan.pdf",
        "notes": ["第 1 页无文本层，疑似扫描件，需 OCR"],
        "blocks": [{"kind": "paragraph", "text": ""}],
    }
    failure, has_text = _ocr_failure(doc)
    assert failure is not None
    assert "需 OCR，当前不支持" in failure["reason"]
    assert has_text is False


def test_prepare_keeps_partially_scanned_document():
    from prepare import _ocr_failure
    doc = {
        "file": "mixed.pdf", "path": "mixed.pdf",
        "notes": ["第 2 页无文本层，疑似扫描件，需 OCR"],
        "blocks": [{"kind": "paragraph", "text": "有文字"}],
    }
    failure, has_text = _ocr_failure(doc)
    assert failure is not None
    assert has_text is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_prepare.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'prepare'`

- [ ] **Step 3: 实现 prepare.py**

`scripts/prepare.py`:
```python
"""阶段①：抽取 → 确定性检查 → 分片。

用法：
    python scripts/prepare.py --files a.docx b.xlsx --depth standard --work .doc-check-work
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyze import analyze
from chunk import build_chunks
from common import write_json
from extractors import extract_document
from manifest import build_manifest


def _ocr_failure(doc: dict) -> tuple[dict | None, bool]:
    """扫描件判定。返回 (失败条目, 是否有文本层)。

    无文本层的扫描件完全不可判定，不计入已检查文档；
    部分无文本层的文档仍计入，但要在失败清单里点名受影响的页。
    """
    notes = [n for n in doc.get("notes", []) if "需 OCR" in n]
    if not notes:
        return None, True
    has_text = any(
        (b.get("text") or "").strip()
        for b in doc.get("blocks", [])
        if b.get("kind") == "paragraph"
    )
    reason = "需 OCR，当前不支持。"
    if not has_text:
        reason += "该文档无文本层，未做任何内容判定。"
    reason += " " + " ".join(notes)
    return {"file": doc["file"], "path": doc["path"], "reason": reason}, has_text


def prepare(files: list[Path], depth: str, work: Path) -> dict:
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)

    documents = []
    failures = []
    for f in files:
        path = Path(f)
        if not path.exists():
            failures.append({
                "file": path.name,
                "path": str(path.resolve()),
                "reason": "文件不存在",
            })
            continue
        try:
            doc = extract_document(path)
        except Exception as exc:  # 单文件失败不中断整体
            failures.append({
                "file": path.name,
                "path": str(path.resolve()),
                "reason": f"抽取失败：{type(exc).__name__}: {exc}",
            })
            continue
        ocr, has_text = _ocr_failure(doc)
        if ocr is not None:
            failures.append(ocr)
            if not has_text:
                continue  # 完全无文本层，不算已检查
        documents.append(doc)

    consistency = analyze(documents)
    chunks = build_chunks(documents, depth)
    manifest = build_manifest(documents, failures, depth, work)

    write_json(work / "docs.json", {"documents": documents})
    write_json(work / "consistency.json", consistency)
    write_json(work / "chunks.json", {"chunks": chunks})
    write_json(work / "manifest.json", manifest)

    return {
        "documents": len(documents),
        "failures": failures,
        "failure_count": len(failures),
        "chunks": len(chunks),
        "issues": len(consistency.get("issues", [])),
        "work": str(work.resolve()),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="doc-check 阶段①：抽取与统计")
    parser.add_argument("--files", nargs="+", required=True, help="待检查的文件路径")
    parser.add_argument(
        "--depth", default="standard",
        choices=["quick", "standard", "deep"], help="检查深度档位",
    )
    parser.add_argument("--work", default=".doc-check-work", help="工作目录")
    args = parser.parse_args(argv)

    result = prepare([Path(f) for f in args.files], args.depth, Path(args.work))
    print(f"已抽取 {result['documents']} 份文档，{result['failure_count']} 份失败")
    print(f"确定性检查发现 {result['issues']} 个问题，分片 {result['chunks']} 片")
    print(f"工作目录：{result['work']}")
    if result["failures"]:
        print("未能检查的文件见 manifest.json 的 failures 字段", file=sys.stderr)
    if result["documents"] == 0 and result["failures"]:
        return 1   # 一份都没检查成功，调用方必须能察觉
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_prepare.py -v`
Expected: PASS，4 passed

- [ ] **Step 5: 冒烟测试 CLI**

Run: `python scripts/prepare.py --files <一个真实 docx 路径> --depth quick --work .doc-check-work`
Expected: 输出三行统计，工作目录下生成四个 JSON 文件

- [ ] **Step 6: 提交**

```bash
git add scripts/prepare.py tests/test_prepare.py
git commit -m "feat: add stage one CLI producing docs consistency chunks manifest"
```

---

## Task 13: report_style.py 与 render.py §0–§3

**Files:**
- Create: `scripts/baseline.py`
- Create: `scripts/report_style.py`
- Create: `scripts/render.py`
- Create: `tests/test_baseline.py`
- Create: `tests/test_render.py`

**Interfaces:**
- Consumes: `schema.validate_findings`, `schema.fingerprint`, `common.read_json`
- Produces:
  - `report_style.CSS: str`
  - `baseline.diff_findings(current: list[dict], baseline: list[dict]) -> dict` — 返回 `{"new": [...], "fixed": [...], "unchanged": [...]}`
  - `baseline.diff_manifests(current: dict, baseline: dict) -> list[dict]` — 返回 `[{"file", "old_sha", "new_sha", "changed"}]`
  - `render.render(work: Path, out: Path, baseline: Path | None = None) -> Path`
  - `render.build_html(data: dict) -> str` — `data` 键为 `manifest` / `consistency` / `findings` / `baseline_diff`

基线文件格式（由 render 自动写出的 `work/last-findings.json`）：

```json
{
  "generated_at": "2026-11-07T10:00:00+08:00",
  "findings": [ ... ],
  "manifest": { ... }
}
```

- [ ] **Step 1: 写失败的测试**

`tests/test_render.py`:
```python
import json

from render import build_html


def _consistency():
    return {
        "style_profile": {
            "font_ea": {"label": "中文字体", "dominant": "宋体", "count": 40, "total": 42},
        },
        "issues": [
            {
                "id": "a" * 16, "severity": "P0", "category": "主体串写",
                "detector": "deterministic", "confidence": "疑似 · 需人工核实",
                "file": "a.docx", "locator": {"type": "file"},
                "quote": "北京华信科技有限公司",
                "description": "出现两个主体", "suggestion": "确认归属",
            }
        ],
        "entities": {
            "names": [
                {"name": "北京华信科技有限公司", "core": "华信科技",
                 "count": 3, "files": ["a.docx", "b.docx"]},
            ],
            "variants": [{"core": "华信科技",
                          "names": ["北京华信科技有限公司", "北京华信科技有限责任公司"]}],
        },
        "stats": {"documents": 2, "issues": 1},
    }


def _findings():
    return [
        {
            "id": "b" * 16, "severity": "P1", "category": "前后矛盾",
            "detector": "llm", "confidence": "疑似 · 需人工核实",
            "file": "a.docx",
            "locator": {"type": "paragraph", "index": 7, "section_path": "第二章"},
            "quote": "工期为 90 日历天",
            "description": "与前文 60 天矛盾", "suggestion": "统一为 60 天",
        }
    ]


def _manifest():
    return {
        "script_version": "0.1.0", "depth": "standard",
        "generated_at": "2026-11-07T10:00:00+08:00",
        "documents": [
            {"file": "a.docx", "type": "docx", "sha256": "c" * 64,
             "stats": {"paragraphs": 100, "tables": 2, "pages": 12,
                       "words": 5000, "rows": 0, "sheets": 0},
             "entities": ["北京华信科技有限公司"], "notes": []},
        ],
        "failures": [
            {"file": "b.pdf", "path": "b.pdf", "reason": "需 OCR，当前不支持"},
        ],
    }


def test_build_html_contains_core_sections():
    html = build_html({
        "manifest": _manifest(),
        "consistency": _consistency(),
        "findings": _findings(),
        "baseline_diff": None,
    })
    for marker in ["检查范围与未能检查项", "结论概览", "硬伤速览", "按文件明细"]:
        assert marker in html, marker


def test_build_html_escapes_content():
    html = build_html({
        "manifest": _manifest(),
        "consistency": _consistency(),
        "findings": [{
            "id": "c" * 16, "severity": "P2", "category": "错别字",
            "detector": "llm", "confidence": "确定", "file": "<script>x</script>",
            "locator": {"type": "file"}, "quote": "<b>bold</b>",
            "description": "描述", "suggestion": "建议",
        }],
        "baseline_diff": None,
    })
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html


def test_build_html_shows_p0_in_quick_view():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": _findings(), "baseline_diff": None,
    })
    assert "主体串写" in html
    assert "P0" in html


def test_build_html_includes_limitations_statement():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": _findings(), "baseline_diff": None,
    })
    assert "未核实外部事实" in html


def test_build_html_no_external_resources():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": _findings(), "baseline_diff": None,
    })
    assert "http://" not in html
    assert "https://" not in html
    assert "<link" not in html


def test_build_html_groups_issues_by_file():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": _findings(), "baseline_diff": None,
    })
    assert "a.docx" in html
    assert "工期为 90 日历天" in html
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_render.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'render'`

- [ ] **Step 3: 实现 report_style.py**

`scripts/report_style.py`:
```python
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
.issue .quote { background: #fff8e1; border-left: 3px solid #f0c36d;
  padding: 6px 10px; margin: 8px 0; white-space: pre-wrap; }
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
```

- [ ] **Step 4: 实现 render.py**

`scripts/render.py`:
```python
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

from common import read_json
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


def _section_3(consistency, findings, manifest) -> str:
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
        out.append(_file_summary(manifest, fname))
        groups: dict[str, list[dict]] = {}
        for f in items:
            groups.setdefault(f.get("category", "未分类"), []).append(f)
        for cat in sorted(groups):
            out.append(f"<h3>{esc(cat)}（{len(groups[cat])}）</h3>")
            for f in groups[cat]:
                out.append(_issue_card(f))
        out.append("</details>")
    return "".join(out)


def _file_summary(manifest: dict, fname: str) -> str:
    """文件摘要：规模、结构、主体名、风格指纹。"""
    doc = next(
        (d for d in manifest.get("documents", []) if d.get("file") == fname),
        None,
    )
    if not doc:
        return ""
    st = doc.get("stats", {})
    bits = [
        f"规模：{st.get('words', 0)} 字 / {st.get('paragraphs', 0)} 段 / {st.get('tables', 0)} 表",
        f"主体名：{'、'.join(doc.get('entities', [])) or '未识别'}",
    ]
    return f'<div class="muted">{"　｜　".join(bits)}</div>'


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
        f"{_section_3(consistency, findings, manifest)}"
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
        # 复查对比必须覆盖**两层**：模型写的 findings 与确定性层的 issues。
        # 只比模型侧，新出现的 P0 混主体会在 §2/§3 显示却不被计入 §6，
        # 等于在专门用来追踪变化的章节里说了假话。
        current_all = list(findings) + list(consistency.get("issues", []))
        prev_all = list(prev.get("findings", [])) + list(prev.get("issues", []))
        baseline_diff = {
            "findings": diff_findings(current_all, prev_all),
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
        "issues": consistency.get("issues", []),
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
```

- [ ] **Step 5: 写 baseline.py**

`scripts/baseline.py`:
```python
"""基线对比：新增、已修复、未修复，以及文件是否改动。"""
from __future__ import annotations

from schema import fingerprint


def diff_findings(current: list[dict], baseline: list[dict]) -> dict:
    cur = {fingerprint(f): f for f in current if isinstance(f, dict)}
    base = {fingerprint(f): f for f in baseline if isinstance(f, dict)}
    return {
        "new": [cur[k] for k in cur if k not in base],
        "fixed": [base[k] for k in base if k not in cur],
        "unchanged": [cur[k] for k in cur if k in base],
    }


def diff_manifests(current: dict, baseline: dict) -> list[dict]:
    cur = {d.get("file"): d.get("sha256", "") for d in current.get("documents", [])}
    base = {d.get("file"): d.get("sha256", "") for d in baseline.get("documents", [])}
    out = []
    for name in sorted(set(cur) | set(base)):
        old = base.get(name, "")
        new = cur.get(name, "")
        out.append({"file": name, "old_sha": old, "new_sha": new, "changed": old != new})
    return out
```

- [ ] **Step 6: 写 baseline 的测试**

`tests/test_baseline.py`:
```python
from baseline import diff_findings, diff_manifests


def _f(id_suffix, file="a.docx", quote="正文"):
    return {
        "id": id_suffix * 16, "severity": "P2", "category": "字体一致性",
        "detector": "deterministic", "confidence": "确定", "file": file,
        "locator": {"type": "paragraph", "index": 1},
        "quote": quote, "description": "描述", "suggestion": "建议",
    }


def test_diff_findings_detects_new_and_fixed():
    base = [_f("a"), _f("b", quote="另一段")]
    cur = [_f("a"), _f("c", quote="新段")]
    d = diff_findings(cur, base)
    assert len(d["unchanged"]) == 1
    assert len(d["new"]) == 1
    assert len(d["fixed"]) == 1
    assert d["new"][0]["quote"] == "新段"


def test_diff_findings_empty_baseline():
    d = diff_findings([_f("a")], [])
    assert len(d["new"]) == 1
    assert d["fixed"] == []


def test_diff_manifests_flags_changed_file():
    cur = {"documents": [{"file": "a.docx", "sha256": "new"}]}
    base = {"documents": [{"file": "a.docx", "sha256": "old"}]}
    rows = diff_manifests(cur, base)
    assert rows[0]["changed"] is True
    assert rows[0]["old_sha"] == "old"
    assert rows[0]["new_sha"] == "new"
```

- [ ] **Step 7: 运行测试确认通过**

Run: `python -m pytest tests/test_baseline.py tests/test_render.py -v`
Expected: PASS，11 passed

- [ ] **Step 8: 提交**

```bash
git add scripts/baseline.py scripts/report_style.py scripts/render.py tests/test_baseline.py tests/test_render.py
git commit -m "feat: add baseline diff and single-file HTML report renderer"
```

---

## Task 14: render.py 扩展 §4–§7

**Files:**
- Modify: `scripts/render.py`
- Create: `tests/test_render_sections.py`

**Interfaces:**
- Consumes: `render.build_html` 的 `data` 字典，新增键 `baseline_diff`
- Produces: `render._section_4(consistency) -> str`、`render._section_5(findings, depth) -> str`、`render._section_6(baseline_diff) -> str`、`render._section_7(manifest) -> str`

- [ ] **Step 1: 写失败的测试**

`tests/test_render_sections.py`:
```python
from render import build_html


def _consistency():
    return {
        "style_profile": {
            "font_ea": {"label": "中文字体", "dominant": "宋体", "count": 40, "total": 42},
            "size_pt": {"label": "字号", "dominant": 12.0, "count": 40, "total": 42},
        },
        "issues": [],
        "entities": {
            "names": [
                {"name": "北京华信科技有限公司", "core": "华信科技",
                 "count": 3, "files": ["a.docx", "b.docx"]},
            ],
            "variants": [{"core": "华信科技",
                          "names": ["北京华信科技有限公司", "北京华信科技有限责任公司"]}],
        },
        "stats": {"documents": 2, "issues": 0},
    }


def _manifest():
    return {
        "script_version": "0.1.0", "depth": "standard",
        "generated_at": "2026-11-07T10:00:00+08:00",
        "documents": [
            {"file": "a.docx", "type": "docx", "sha256": "c" * 64,
             "stats": {"paragraphs": 100, "tables": 2, "pages": 12,
                       "words": 5000, "rows": 0, "sheets": 0},
             "entities": [], "notes": []},
        ],
        "failures": [],
    }


def _finding(category, severity="P2", confidence="疑似 · 需人工核实"):
    return {
        "id": "d" * 16, "severity": severity, "category": category,
        "detector": "llm", "confidence": confidence, "file": "a.docx",
        "locator": {"type": "paragraph", "index": 3, "section_path": "第一章"},
        "quote": "缺少资质证明材料", "description": "描述", "suggestion": "补充",
    }


def test_section4_style_profile_table():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": [], "baseline_diff": None,
    })
    assert "一致性差异" in html
    assert "中文字体" in html
    assert "宋体" in html


def test_section4_entity_variants_table():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": [], "baseline_diff": None,
    })
    assert "主体名" in html
    assert "北京华信科技有限责任公司" in html


def test_section5_todo_list():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": [_finding("待补充内容")], "baseline_diff": None,
    })
    assert "待补充与待核实" in html
    assert "缺少资质证明材料" in html


def test_section6_absent_without_baseline():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": [], "baseline_diff": None,
    })
    assert "复查对比" not in html


def test_section6_present_with_baseline():
    diff = {
        "findings": {
            "new": [_finding("错别字")],
            "fixed": [_finding("主体名称")],
            "unchanged": [],
        },
        "files": [{"file": "a.docx", "old_sha": "x", "new_sha": "y", "changed": True}],
    }
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": [], "baseline_diff": diff,
    })
    assert "复查对比" in html
    assert "新增" in html and "已修复" in html
    assert "文件已修改" in html


def test_section7_appendix_has_rules_and_fingerprints():
    html = build_html({
        "manifest": _manifest(), "consistency": _consistency(),
        "findings": [], "baseline_diff": None,
    })
    assert "附录" in html
    assert "检查规则" in html
    assert "c" * 64 in html
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_render_sections.py -v`
Expected: FAIL，缺少 §4 §5 §6 §7 章节标记

- [ ] **Step 3: 实现 §4–§7**

在 `scripts/render.py` 的 `_section_3` 之后插入：

```python
_STYLE_CATEGORIES = ("字体一致性", "段落格式一致性")
_CONVENTION_CATEGORIES = (
    "标题层级体例", "图表题注体例", "表格体例", "列表与编号",
    "引用标记", "数字与单位", "主体名称",
)


def _section_4(consistency: dict) -> str:
    out = ["<h2 id='s4'>§4 一致性差异</h2>"]
    profile = consistency.get("style_profile", {})
    issues = consistency.get("issues", [])

    out.append("<h3>4.1 样式主流值</h3>")
    if profile:
        rows = []
        for key, v in profile.items():
            rows.append([
                esc(v.get("label", key)),
                esc(v.get("dominant")),
                str(v.get("count", 0)),
                str(v.get("total", 0)),
            ])
        out.append(_table(["项目", "主流值", "出现次数", "统计段落数"], rows))
    else:
        out.append("<p class='muted'>无可统计的样式数据（文档可能不含结构化样式）。</p>")

    out.append("<h3>4.2 样式偏离明细</h3>")
    style_issues = [i for i in issues if i.get("category") in _STYLE_CATEGORIES]
    if style_issues:
        out.append(_table(
            ["文件", "位置", "项目", "实际情况", "主流值"],
            [[esc(i.get("file", "")), esc(_locator_text(i.get("locator", {}))),
              esc(i.get("category", "")), esc(i.get("quote", "")),
              esc(i.get("description", ""))] for i in style_issues],
        ))
    else:
        out.append("<p class='muted'>未发现样式偏离。</p>")

    out.append("<h3>4.3 体例差异</h3>")
    conv_issues = [i for i in issues if i.get("category") in _CONVENTION_CATEGORIES]
    if conv_issues:
        out.append(_table(
            ["文件", "类别", "问题"],
            [[esc(i.get("file", "")), esc(i.get("category", "")),
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
            [[esc(n.get("name", "")), esc(n.get("core", "")), str(n.get("count", 0)),
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


def _section_5(findings: list[dict], depth: str = "") -> str:
    todo = [f for f in findings if f.get("category") == "待补充内容"]
    verify = [f for f in findings if f.get("confidence") == "疑似 · 需人工核实"]
    out = ["<h2 id='s5'>§5 待补充与待核实</h2>"]
    out.append("<h3>待补充内容</h3>")
    if todo:
        out.append(_table(
            ["☐", "文件", "位置", "缺失内容", "为何需要", "建议"],
            [["☐", esc(f.get("file", "")), esc(_locator_text(f.get("locator", {}))),
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
            ["文件", "位置", "问题", "建议"],
            [[esc(f.get("file", "")), esc(_locator_text(f.get("locator", {}))),
              esc(f.get("description", "")), esc(f.get("suggestion", ""))] for f in verify],
        ))
    else:
        out.append("<p class='muted'>无。</p>")
    return "".join(out)


def _section_6(baseline_diff: dict) -> str:
    if not baseline_diff:
        return ""
    fd = baseline_diff.get("findings", {})
    out = ["<h2 id='s6'>§6 复查对比</h2>"]
    changed = [f for f in baseline_diff.get("files", []) if f.get("changed")]
    if changed:
        out.append(
            "<div class='limit'>以下文件在上次检查后已被修改，部分对比结果可能不适用："
            + esc("、".join(f.get("file", "") for f in changed))
            + "</div>"
        )
    for title, key in (("新增问题", "new"), ("已修复问题", "fixed"), ("未修复问题", "unchanged")):
        items = fd.get(key, [])
        out.append(f"<h3>{title}（{len(items)}）</h3>")
        if items:
            out.append(_table(
                ["级别", "文件", "位置", "类别", "问题"],
                [[f'<span class="badge {esc(f.get("severity", ""))}">{esc(f.get("severity", ""))}</span>',
                  esc(f.get("file", "")), esc(_locator_text(f.get("locator", {}))),
                  esc(f.get("category", "")), esc(f.get("description", ""))]
                 for f in items],
            ))
        else:
            out.append("<p class='muted'>无</p>")
    return "".join(out)


_RULES = [
    ("字体一致性", "字体、字号与全文主流值不一致的段落"),
    ("段落格式一致性", "行距、缩进、对齐、段间距与主流值不一致的段落"),
    ("标题层级体例", "同一文件内标题编号体系混用"),
    ("图表题注体例", "同一文件内图表题注写法混用"),
    ("表格体例", "表头写法不统一、缺重复表头"),
    ("主体名称", "同一主体出现多种名称写法"),
    ("主体串写", "同一文件内出现多个不同主体名称"),
    ("数字与单位", "货币单位、日期格式混用"),
    ("引用标记", "引用标记写法混用、编号越界"),
    ("列表与编号", "有序列表编号方式混用"),
    ("术语与缩写", "缩写首次出现未给出全称"),
    ("错别字用词", "错别字、形近词误用"),
    ("标点格式", "标点与空格使用不规范"),
    ("前后矛盾", "同一事实在文档两处描述冲突"),
    ("引用张冠李戴", "引用处语境与被引内容主题不符"),
    ("待补充内容", "缺失数据、空白字段、应附材料"),
    ("数字逻辑", "合计与分项不符、比例关系不成立"),
    ("表述歧义", "表述不清或语义歧义"),
    ("术语一致性", "同义异形术语混用"),
]


_DEPTH_COVERAGE = {
    "quick": "阶段①全量确定性检查 + 阶段②仅做错别字与标点扫描。"
             "未做语义互查：前后矛盾、主体串写、引用张冠李戴、待补充内容等类别本次未覆盖。",
    "standard": "阶段①全量确定性检查 + 阶段②九类语义检查全做。",
    "deep": "阶段①全量确定性检查 + 阶段②逐段细读，邻接窗口更大。",
}


def _section_7(manifest: dict) -> str:
    out = ["<h2 id='s7'>§7 附录</h2>"]
    depth = manifest.get("depth", "")
    out.append("<h3>本次检查范围</h3>")
    out.append(_table(
        ["项目", "内容"],
        [
            ["检查档位", depth or "未知"],
            ["覆盖范围", _DEPTH_COVERAGE.get(depth, "未知档位，请核对 scripts/chunk.py 的 DEPTH_PARAMS。")],
        ],
    ))
    out.append("<h3>检查规则与判定标准</h3>")
    out.append(_table(["类别", "判定标准"], [[esc(a), esc(b)] for a, b in _RULES]))
    out.append("<h3>文件指纹</h3>")
    out.append(_table(
        ["文件", "SHA256"],
        [[esc(d.get("file", "")), esc(d.get("sha256", ""))]
         for d in manifest.get("documents", [])],
    ))
    return "".join(out)
```

在 `build_html` 中，把结尾的组装部分改为：

```python
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
        _section_1(manifest, consistency, findings),
        _section_2(consistency, findings),
        _section_3(consistency, findings, manifest),
        _section_4(consistency),
        _section_5(findings, manifest.get("depth", "")),
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
        "</div></body></html>"
    )
```

`_section_7` 中不再重复能力边界声明，因为页脚已固定包含该声明。页脚仍保留在 `build_html` 的 body 之后，`"</div></body></html>"` 之前：

```python
        f"{body}"
        f"<div class='limit'><b>能力边界</b><br>{esc(_LIMITATION)}</div>"
        "</div></body></html>"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_render_sections.py tests/test_render.py tests/test_baseline.py -v`
Expected: PASS，15 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/render.py tests/test_render_sections.py
git commit -m "feat: extend report with consistency todo baseline and appendix sections"
```

---

## Task 15: references 语义层规则文档

**Files:**
- Create: `references/content-rules.md`
- Create: `references/format-rules.md`
- Create: `references/severity.md`
- Create: `references/report-spec.md`
- Create: `tests/test_references.py`

**Interfaces:**
- Consumes: `schema.SEVERITIES`、`schema.CONFIDENCES`、Task 8/9/10 中的类别名
- Produces: 四份参考文档，供智能体在阶段②读取

- [ ] **Step 1: 写失败的测试**

`tests/test_references.py`:
```python
from pathlib import Path

import schema

REF = Path(__file__).resolve().parent.parent / "references"


def _read(name):
    return (REF / name).read_text(encoding="utf-8")


def test_all_reference_files_exist():
    for name in ["content-rules.md", "format-rules.md", "severity.md", "report-spec.md"]:
        assert (REF / name).exists(), name


def test_severity_doc_lists_all_severities():
    text = _read("severity.md")
    for s in schema.SEVERITIES:
        assert s in text


def test_severity_doc_lists_all_confidences():
    text = _read("severity.md")
    for c in schema.CONFIDENCES:
        assert c in text


def test_severity_doc_has_findings_schema():
    text = _read("severity.md")
    for field in ["id", "severity", "category", "detector", "confidence",
                  "file", "locator", "quote", "description", "suggestion"]:
        assert field in text


def test_content_rules_cover_all_nine_categories():
    text = _read("content-rules.md")
    for cat in ["错别字", "标点", "前后矛盾", "主体串写",
                "张冠李戴", "待补充", "数字逻辑", "表述不清", "术语"]:
        assert cat in text, cat


def test_severity_doc_introduces_no_extra_confidence_literals():
    # 参考文档不得自造 schema 里没有的置信度字面量：
    # 渲染器是按字面量分类展示的，文档与代码不一致会静默漏项
    import re
    text = _read("severity.md")
    for literal in set(re.findall(r"「(确定[^」]*)」", text)):
        assert literal in schema.CONFIDENCES, literal


def test_content_rules_fixed_category_list_excludes_deterministic_category():
    # 语义层的「主体名误用」与确定性层的「主体串写」是两个类别，
    # 固定清单里若出现「主体串写」，智能体会对同一问题报两次
    text = _read("content-rules.md")
    line = [l for l in text.splitlines() if l.startswith("- category 取值固定为")]
    assert line, "找不到固定类别清单"
    assert "主体串写" not in line[0]
    assert "主体名误用" in line[0]
    assert "待补充内容" in line[0]   # render.py §5 按这个字面量过滤


def test_format_rules_cover_all_ten_categories():
    text = _read("format-rules.md")
    for cat in ["字体一致性", "段落格式一致性", "标题层级体例", "图表题注体例",
                "表格体例", "主体名称", "数字与单位", "引用标记",
                "列表与编号", "术语与缩写"]:
        assert cat in text, cat
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_references.py -v`
Expected: FAIL，references 目录不存在

- [ ] **Step 3: 写 references/severity.md**

```markdown
# 严重级别、置信度与 findings 结构

## 严重级别

| 级别 | 定义 | 典型例子 |
|---|---|---|
| P0 | 硬伤，可能导致废标或事实错误 | 同一文件混用多个主体名称、金额合计与分项不符、引用了不存在的编号 |
| P1 | 严重问题，影响评审判断 | 前后矛盾、同一主体多种名称写法、错别字改变原意、货币单位混用 |
| P2 | 体例与格式不一致 | 字体字号不统一、行距不一致、标题编号体系混用、图表题注写法混用、日期格式不统一 |
| P3 | 优化建议 | 表述可更精炼、缩写未给全称、术语未统一 |

判定原则：先看是否影响评审结论，再看是否影响可读性，最后才是风格偏好。

## 置信度

| 取值 | 含义 |
|---|---|
| 确定 | 有程序化依据，或有文档内明确证据链。确定性检查产出的一律为确定。 |
| 疑似 · 需人工核实 | 仅由模型语义推断，或需要外部事实才能确认。 |

主体名称「同一主体多种写法」为确定。「疑似混主体」为疑似 · 需人工核实。

## findings.json 结构

```json
{
  "id": "ab12cd34ef567890",
  "severity": "P2",
  "category": "字体一致性",
  "detector": "llm",
  "confidence": "确定",
  "file": "a.docx",
  "locator": {"type": "paragraph", "index": 42, "section_path": "第三章/3.2 报价说明"},
  "quote": "原文摘录",
  "description": "问题描述",
  "suggestion": "修改建议"
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| id | 由 file + category + locator + quote 哈希得到的 16 位指纹。同一问题在文档未改动时保持稳定，用于复查对比。 |
| severity | P0 / P1 / P2 / P3 |
| category | 问题类别，取值见 content-rules.md 与 format-rules.md |
| detector | deterministic 或 llm。模型写出的必须是 llm。 |
| confidence | 确定 或 疑似 · 需人工核实 |
| file | 文件名，与 docs.json 中的 file 字段一致 |
| locator | 定位信息，type 取 paragraph / table / file / section |
| quote | 原文摘录，尽量取完整的句子或短语，不要改写 |
| description | 问题描述，说明为什么不妥 |
| suggestion | 可直接执行的修改建议，不要写「建议优化」这类空话 |

写入规则：

1. 只输出真实存在的问题。没有问题就不写条目，不要为了凑数编造。
2. quote 必须是原文中确实存在的片段。
3. locator.index 用 chunks.json 中 block_indexes 的首个下标。
4. 同一问题只写一条，不要在不同类别下重复。
```

- [ ] **Step 4: 写 references/content-rules.md**

```markdown
# 语义层检查规则（阶段②使用）

你正在检查一批投标文档。输入是 chunks.json 中的分片，每个分片含原文、章节路径、前后邻接文本，以及脚本预标注的主体名、数字、引用标记。

只写确实存在的问题。没有问题就不写。不要为了凑数编造条目。

## 检查项

### 1. 错别字用词
错别字、形近字误用、同音字误用、专业术语写错、量词搭配不当。
例：「帐号」应为「账号」；「帐户」应为「账户」；「既往史」写成「继往史」。

### 2. 标点格式
中英文标点混用、全角半角混用、书名号与引号误用、标点多余或缺失、连续标点、括号不配对、编号后缺顿号。

### 3. 前后矛盾
同一事实在文档不同位置描述冲突。判据：数字不同、时间不同、数量不同、状态不同、承诺不同。
必须结合 neighbors 的前后文判断，不要凭单句臆断。例：前文「工期 60 日历天」，后文「本项目工期为 90 日历天」。

### 4. 主体名误用
段落或句子中出现了疑似属于另一主体的名称、地址、资质、业绩或联系方式。

**与确定性层的分工**：确定性层按**文件级主体集合**判定，产出 P0「主体串写」
（该文件出现多个主体，且文件名与章节标题都未指明归属）。语义层按**段落级上下文**判定，
只报**能指出具体哪一句写错了**的情况。

因此：**不要**重复报告「这个文件出现了多个主体」——确定性层已经报了。
只有当你能指出具体段落、具体句子里的名称与该文件应有的主体不符时，才写这一条。
分片中的 entities 是脚本预标注的主体名。若某主体名与该文档其余部分的主体名不同，
且文内没有明确的「协作方」「分包方」等说明，标记为疑似 · 需人工核实。

### 5. 引用张冠李戴
引用标记指向的内容与引用处语境不符。判据：正文说「见图 3-2 的曲线走势」，而文中 3-2 图讲的是设备清单。
只依据文档内可核对的信息判断，不推测文档外的事实。分片中出现的引用标记可能只是目录、图表题注，不一定是正文引用，需结合上下文。

### 6. 待补充内容
明确指向外部却未给出内容：「详见附件」「见后文」「见另册」；缺少应有数据：合同金额、期限、联系人；应有而未附的材料：资质证书、业绩证明、检测报告、承诺函。

### 7. 数字逻辑
合计与分项不符、比例关系不成立、单位换算错误、百分比超过 100%、金额小数位前后不一致。
能做算术验算的必须验算。

### 8. 表述不清
语义歧义、指代不明、成分残缺、句子结构混乱导致读者需要回读。

### 9. 术语一致性
同一概念在文中使用多个名称，如「项目负责人」与「项目经理」混用。判定前先确认两者确实指同一概念。

## 写作要求

- category 取值固定为：错别字用词、标点格式、前后矛盾、主体名误用、引用张冠李戴、待补充内容、数字逻辑、表述不清、术语一致性。
  注意「主体名误用」与确定性层的「主体串写」是两个类别：后者是文件级 P0，由脚本产出；前者是段落级，由你产出。不要用「主体串写」这个 category。
- severity 与 confidence 的判定标准见 severity.md。
- locator.type 取 paragraph，index 取该分片 block_indexes 的首个下标。
- description 写清为什么不妥，suggestion 给出可直接执行的改法。
```

- [ ] **Step 5: 写 references/format-rules.md**

```markdown
# 格式与体例层规则（阶段①确定性检查产出，供核对与排查）

以下问题由脚本判定，置信度为「确定」。本文件记录判定标准，供人工复核与规则调整时参考。

## 字体一致性
中文字体、西文字体、字号与全文主流值不一致。主流值定义为出现次数最多的取值，且其占比不低于 60%，否则不报。偏离段落逐条列出文件名、段序、实际值与主流值。段落样式取首个非空 run 的属性，run 未设置时取段落样式继承值。

## 段落格式一致性
对齐方式、左缩进、首行缩进、行距、段前距、段后距与主流值不一致。判定规则同字体一致性。

## 标题层级体例
同一文件内出现两种以上标题编号体系即报。体系清单：第一章式、一、式、（一）式、1. 式、1.1 式。

## 图表题注体例
同一文件内出现两种以上题注写法即报。写法清单：图N-N、图N.N、图N、表N-N、表N.N、表N。

## 表格体例
表头行写法不统一、跨页表格缺少重复表头。xlsx 的表头行取首行非空且下方存在数据的行。

## 主体名称
同一主体出现两种以上名称写法。变体判定基于核心字号：名称去掉公司词尾与行政区划前缀后的剩余部分；核心字号相同，或较短者是较长者的前缀且不短于 3 个字符，视为同一主体。行业词不剥离，「华信科技」与「华信信息技术」是两个不同主体。

## 主体串写
同一文件内出现两个及以上不同核心字号的主体名称即报。因无外部依据，置信度为「疑似 · 需人工核实」，不升级为确定。

## 数字与单位
同一文件内货币单位（元、万元）混用报 P1。日期格式（2024年1月1日、2024-01-01、2024/01/01、2024.01.01）混用报 P2。

## 引用标记
同一文件内引用标记写法（文献[n]、[n]、（n））混用即报。编号越界与参考文献表缺项由智能体在语义层核对。

## 列表与编号
有序列表编号方式混用即报。

## 术语与缩写
缩写首次出现时未给出全称。这项由智能体在语义层判定，脚本只提供候选缩写。

## 置信度标注
pdf 抽取的样式数据置信度为低，不参与一致性统计，相关结论不产出。md 与 txt 无样式概念，格式类检查项标为「不适用」。
```

- [ ] **Step 6: 写 references/report-spec.md**

```markdown
# HTML 报告结构规范

报告为单个 HTML 文件，CSS 内联，不引用任何 CDN、外部字体或 JavaScript 库。可离线打开、可邮件附件发送、可长期归档。附打印样式。

## 章节

| 章节 | 内容 |
|---|---|
| §0 检查范围与未能检查项 | 受检文件清单（类型、页数、字数、段落数、表格数、SHA256 前缀）；未能检查的文件与原因 |
| §1 结论概览 | 严重级分布条、类别分布、文件分布、重点提示（主体数、混主体数、待补充数） |
| §2 硬伤速览 | 仅 P0 与 P1，一行一条：级别、文件、位置、问题 |
| §3 按文件明细 | 每文件一组，按类别分组，每条含级别徽章、类别、来源、置信度、位置、原文摘录、描述、建议 |
| §4 一致性差异 | 4.1 样式主流值；4.2 主体名分布与写法变体 |
| §5 待补充与待核实 | 待补充内容表；需人工核实项表 |
| §6 复查对比 | 仅在使用 --baseline 时出现。新增、已修复、未修复三表，外加文件改动提示 |
| §7 附录 | 检查规则与判定标准、文件 SHA256、能力边界声明 |

## 固定声明

每份报告必须包含能力边界声明：本工具仅做文档内互查，未核实外部事实。企业名称是否真实存在、引用文献是否真实存在、法规是否现行有效，均需人工核实。

## 转义

所有来自文档与模型的文本必须 HTML 转义后再输出。
```

- [ ] **Step 7: 运行测试确认通过**

Run: `python -m pytest tests/test_references.py -v`
Expected: PASS，7 passed

- [ ] **Step 8: 提交**

```bash
git add references/ tests/test_references.py
git commit -m "docs: add reference rules for content format severity and report"
```

---

## Task 16: SKILL.md 与 AGENTS.md

**Files:**
- Create: `SKILL.md`
- Create: `AGENTS.md`
- Create: `tests/test_skill_doc.py`

**Interfaces:**
- Consumes: `references/*.md`、脚本 CLI 参数
- Produces: `SKILL.md`（智能体主指令）与 `AGENTS.md`（通用入口）

- [ ] **Step 1: 写失败的测试**

`tests/test_skill_doc.py`:
```python
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_skill_md_has_frontmatter():
    text = _read("SKILL.md")
    assert text.startswith("---\n")
    assert "name: doc-check" in text
    assert "description:" in text


def test_skill_md_documents_three_stages():
    text = _read("SKILL.md")
    assert "prepare.py" in text
    assert "findings.json" in text
    assert "render.py" in text


def test_skill_md_lists_depth_options():
    text = _read("SKILL.md")
    for d in ["quick", "standard", "deep"]:
        assert d in text


def test_skill_md_forbids_modifying_documents():
    text = _read("SKILL.md")
    assert "不得修改" in text or "绝不修改" in text


def test_skill_md_lists_categories():
    text = _read("SKILL.md")
    for cat in ["错别字", "前后矛盾", "张冠李戴", "待补充"]:
        assert cat in text, cat


def test_skill_md_points_at_content_rules():
    text = _read("SKILL.md")
    assert "references/content-rules.md" in text
    assert "references/severity.md" in text


def test_agents_md_points_to_skill():
    text = _read("AGENTS.md")
    assert "SKILL.md" in text
    assert "prepare.py" in text
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_skill_doc.py -v`
Expected: FAIL，SKILL.md 不存在

- [ ] **Step 3: 写 SKILL.md**

````markdown
---
name: doc-check
description: 检查一组投标文档的内容与格式问题，产出单文件 HTML 报告。当用户要求检查文档、审阅标书、核对投标文件、排查错别字、企业名称写错、引用张冠李戴、体例混乱、前后矛盾、多主体写混或字体排版不一致时使用。也适用于「检查这批文档」「审一下这几份文件」「看看有没有写错的地方」这类请求。
---

# 文档检查技能

对指定的多个文档做系统检查，产出 HTML 报告。**绝不修改用户的任何文档。**

## 何时使用

用户给出一份或多份文档（docx / xlsx / pdf / md / txt），希望检查其中的错别字、名称错误、引用问题、体例混乱、前后矛盾、待补充内容、多主体写混、字体排版不一致。

## 三阶段执行流程

必须严格按三阶段执行。不要跳过阶段①直接读原始文档，不要自己编造阶段①的统计结果。

### 阶段① 确定性抽取与统计

```bash
python scripts/prepare.py --files <文件1> <文件2> --depth <档位> --work .doc-check-work
```

- `--depth` 三档：`quick`（仅错别字与标点）、`standard`（默认，九类语义检查全做）、`deep`（逐段细读）
- 产出四个 JSON：`docs.json`、`consistency.json`、`chunks.json`、`manifest.json`
- 有文件抽取失败时，`manifest.json` 的 `failures` 字段会列出原因。**必须在最终回复中告知用户哪些文件没被检查及原因**，不要假装全部检查过。

### 阶段② 语义判定

1. 读 `references/content-rules.md`，这是语义检查的规则与定级标准。
2. 读 `references/severity.md`，确认 severity 与 confidence 的判定口径。
3. 读 `.doc-check-work/chunks.json`，逐片检查。
4. 把结果写入 `.doc-check-work/findings.json`，结构见 `references/severity.md`。

检查纪律：

- 只写真实存在的问题。没有问题就不写条目，不要为了凑数编造。
- `quote` 必须是原文中确实存在的片段，不要改写。
- `locator.index` 用该分片的 `block_indexes` 首个下标。
- 同一问题只写一条，不要在不同类别下重复。
- 阶段①的 `consistency.json` 里已有确定性问题，**不要在 findings.json 里重复写一遍**。findings.json 只放语义层的问题。语义层发现的问题若在阶段①有对应依据（如主体名命中、算术校验一致），confidence 写「确定」，否则写「疑似 · 需人工核实」。

分片很多时，分批读取分批写入，不要一次性把全部 findings 攒在上下文里。

### 阶段③ 渲染报告

```bash
python scripts/render.py --work .doc-check-work --out report.html
```

复查模式（改完一轮再查）：

```bash
python scripts/render.py --work .doc-check-work --out report.html --baseline .doc-check-work/last-findings.json
```

渲染后把 `report.html` 的绝对路径告诉用户。

## 深度档位的差别

| 档位 | 覆盖内容 |
|---|---|
| quick | 阶段①全量 + 错别字、标点、表述不清、术语一致性 |
| standard | 阶段①全量 + 九类语义检查全做 |
| deep | 阶段①全量 + 逐段细读，邻接窗口更大 |

选档位时，用户明确指定就照办；没指定用 standard。文档很多或很长时主动提示用户可选 quick 先过一遍。

## 能力边界

本工具只做文档内互查，不核实外部事实。以下三类无法确认，相关结论必须标为「疑似 · 需人工核实」：

- 企业名称在现实中是否真实存在、是否为正确主体
- 引用的文献是否真实存在、内容是否与引用处一致
- 引用的法规、标准是否现行有效

「同一主体出现多种名称写法」可以确定判定；「疑似把两家企业写混」不能。

## 常见问题

**扫描版 PDF 怎么办？** 阶段①会报「需 OCR，当前不支持」。如实告知用户该文件未被检查，不要编造检查结果。

**没有 Python 环境怎么办？** 告知用户需要 Python 3.9 及以上，并指向 README 的安装章节。

**上下文放不下怎么办？** 按 chunk 顺序处理，findings 分批落盘到 findings.json，不要一次性载入全部原文。

**用户只给了一个文件？** 照样可以检查，但跨文档一致性类检查（主体串写、字体统一）失去意义，需在回复中说明。
````

- [ ] **Step 4: 写 AGENTS.md**

````markdown
# doc-check 使用说明

本目录含一个文档检查技能，位于 `SKILL.md`。

## 用法

1. 确认环境已安装（Python 3.9+ 与四个依赖）。安装脚本会创建 `.venv` 并装好依赖。
2. 在项目根目录执行阶段①：

```bash
python scripts/prepare.py --files 文档1.docx 文档2.docx --depth standard --work .doc-check-work
```

3. 读取 `.doc-check-work/chunks.json` 与 `references/content-rules.md`，做语义判定，把结果写入 `.doc-check-work/findings.json`，结构见 `references/severity.md`。
4. 渲染报告：

```bash
python scripts/render.py --work .doc-check-work --out report.html
```

## 约束

- 绝不修改用户的原始文档。
- 只写真实存在的问题，不要为凑数编造条目。
- 无法确认的结论标为「疑似 · 需人工核实」，不要伪装成确定结论。
- 未能抽取的文件必须在回复中如实说明。
````

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_skill_doc.py -v`
Expected: PASS，6 passed

- [ ] **Step 6: 提交**

```bash
git add SKILL.md AGENTS.md tests/test_skill_doc.py
git commit -m "docs: add skill instructions and generic agent entry point"
```

---

## Task 17: 安装器与 adapters

**Files:**
- Create: `install/adapters.json`
- Create: `install/adapters/claude-code.md`
- Create: `install/adapters/codex.md`
- Create: `install/adapters/workbuddy.md`
- Create: `install/adapters/dsh.md`
- Create: `install/adapters/generic.md`
- Create: `install/adapters/README.md`
- Create: `install/install.ps1`
- Create: `install/install.sh`
- Create: `tests/test_install_assets.py`

**Interfaces:**
- Consumes: `install/adapters.json`
- Produces: `install/install.ps1` 与 `install/install.sh`，二者行为一致

- [ ] **Step 1: 写失败的测试**

`tests/test_install_assets.py`:
```python
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "install"


def _adapters():
    return json.loads((INSTALL / "adapters.json").read_text(encoding="utf-8"))


def test_adapters_file_valid():
    data = _adapters()
    assert data["version"] == 1
    assert len(data["agents"]) >= 4


def test_known_agents_have_skill_dir():
    by_id = {a["id"]: a for a in _adapters()["agents"]}
    assert by_id["claude-code"]["skill_dir"] == "~/.claude/skills/doc-check"
    assert by_id["codex"]["skill_dir"] == "~/.codex/skills/doc-check"
    assert by_id["workbuddy"]["skill_dir"] == "~/DoubaoWork/skills/doc-check"
    assert by_id["dsh"]["skill_dir"] == "~/.dsh/skills/doc-check"


def test_every_agent_has_detect_paths_and_usage():
    for a in _adapters()["agents"]:
        assert "detect_paths" in a, a["id"]
        assert a.get("usage"), a["id"]
        assert a.get("mode") in ("skill_dir", "manual"), a["id"]


def test_generic_agent_is_manual():
    by_id = {a["id"]: a for a in _adapters()["agents"]}
    assert by_id["generic"]["mode"] == "manual"


def test_every_agent_has_template_file():
    for a in _adapters()["agents"]:
        if a["mode"] == "manual":
            continue
        p = INSTALL / "adapters" / f"{a['id']}.md"
        assert p.exists(), p


def test_install_scripts_exist():
    assert (INSTALL / "install.ps1").exists()
    assert (INSTALL / "install.sh").exists()


def test_install_scripts_mention_interpreter_candidates():
    for name in ["install.ps1", "install.sh"]:
        text = (INSTALL / name).read_text(encoding="utf-8")
        assert "3.12" in text
        assert "3.11" in text
        assert "requirements.txt" in text
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_install_assets.py -v`
Expected: FAIL，install 目录不存在

- [ ] **Step 3: 写 install/adapters.json**

```json
{
  "version": 1,
  "agents": [
    {
      "id": "claude-code",
      "name": "Claude Code",
      "detect_paths": ["~/.claude"],
      "detect_commands": ["claude"],
      "mode": "skill_dir",
      "skill_dir": "~/.claude/skills/doc-check",
      "entry": "SKILL.md",
      "usage": "/doc-check 或直接说「检查这批文档」"
    },
    {
      "id": "codex",
      "name": "Codex CLI",
      "detect_paths": ["~/.codex"],
      "detect_commands": ["codex"],
      "mode": "skill_dir",
      "skill_dir": "~/.codex/skills/doc-check",
      "entry": "SKILL.md",
      "usage": "/doc-check"
    },
    {
      "id": "workbuddy",
      "name": "WorkBuddy",
      "detect_paths": ["~/DoubaoWork", "~/AppData/Local/DoubaoWork"],
      "detect_commands": [],
      "mode": "skill_dir",
      "skill_dir": "~/DoubaoWork/skills/doc-check",
      "entry": "SKILL.md",
      "usage": "直接说「检查这批文档」"
    },
    {
      "id": "dsh",
      "name": "DSH",
      "detect_paths": ["~/.dsh", "~/AppData/Roaming/DSH", "~/AppData/Local/DSH"],
      "detect_commands": [],
      "mode": "skill_dir",
      "skill_dir": "~/.dsh/skills/doc-check",
      "entry": "SKILL.md",
      "usage": "直接说「检查这批文档」"
    },
    {
      "id": "generic",
      "name": "通用（任意智能体）",
      "detect_paths": [],
      "detect_commands": [],
      "mode": "manual",
      "usage": "把 install/adapters/generic.md 的片段与仓库绝对路径贴进你的智能体项目说明"
    }
  ]
}
```

- [ ] **Step 4: 写各智能体入口模板**

`install/adapters/claude-code.md`:
```markdown
---
name: doc-check
description: 检查一组投标文档的内容与格式问题，产出单文件 HTML 报告。当用户要求检查文档、审阅标书、核对投标文件、排查错别字、企业名称写错、引用张冠李戴、体例混乱、前后矛盾、多主体写混或字体排版不一致时使用。
---

# 文档检查技能

技能说明见同目录下的 `references/` 与 `SKILL.md`。

仓库根目录：{{REPO_ROOT}}

执行前先阅读 `SKILL.md`，按其中描述的三阶段流程执行：

1. `python "{{REPO_ROOT}}/scripts/prepare.py" --files <文件...> --depth standard --work .doc-check-work`
2. 读 `.doc-check-work/chunks.json` 与 `{{REPO_ROOT}}/references/content-rules.md`，写 `.doc-check-work/findings.json`
3. `python "{{REPO_ROOT}}/scripts/render.py" --work .doc-check-work --out report.html`

绝不修改用户的原始文档。
```

`install/adapters/codex.md` 与 `install/adapters/workbuddy.md` 与 `install/adapters/dsh.md` 内容与 claude-code.md 相同，仅首行标题分别改为 `# 文档检查技能（Codex CLI）`、`# 文档检查技能（WorkBuddy）`、`# 文档检查技能（DSH）`。

`install/adapters/generic.md`:
```markdown
# 通用智能体接入说明

把下面这段加入你的智能体项目说明文件（如 AGENTS.md、CLAUDE.md、.cursorrules、.windsurfrules）：

---
本项目使用 doc-check 技能检查文档。仓库根目录：{{REPO_ROOT}}

先阅读 {{REPO_ROOT}}/SKILL.md，按其中三阶段流程执行：
1. python "{{REPO_ROOT}}/scripts/prepare.py" --files <文件...> --depth standard --work .doc-check-work
2. 读 .doc-check-work/chunks.json 与 {{REPO_ROOT}}/references/content-rules.md，写 .doc-check-work/findings.json
3. python "{{REPO_ROOT}}/scripts/render.py" --work .doc-check-work --out report.html

绝不修改用户的原始文档。
---
```

`install/adapters/README.md`:
```markdown
# 新增一个智能体适配

需要改三处：

1. `install/adapters.json` 增加一个条目，写明 `id`、`name`、`detect_paths`（用于探测该智能体是否安装）、`mode`（`skill_dir` 或 `manual`）、`skill_dir`（技能安装目录）、`entry`（入口文件名）、`usage`（用法提示）。
2. `install/adapters/<id>.md` 写该智能体的入口模板，模板中的 `{{REPO_ROOT}}` 会被安装器替换成仓库绝对路径。
3. 若该智能体的技能格式与 `SKILL.md` 不同，需要在模板中改写 frontmatter，并在 `scripts/` 旁加一段适配说明。

安装器无需改代码即可支持新适配项。

## 已确认的路径

| 智能体 | 路径 | 核实状态 |
|---|---|---|
| Claude Code | `~/.claude/skills/doc-check` | 已确认 |
| Codex CLI | `~/.codex/skills/doc-check` | 已确认，与 Claude Code 同用 SKILL.md frontmatter |
| WorkBuddy | `~/DoubaoWork/skills/doc-check` | 路径已确认，技能文件格式待验证 |
| DSH | `~/.dsh/skills/doc-check` | 未确认，候选值 |
```

- [ ] **Step 5: 写 install/install.ps1**

```powershell
# doc-check 安装器
# 用法：pwsh install/install.ps1  或  powershell -ExecutionPolicy Bypass -File install/install.ps1
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$InstallDir = Join-Path $RepoRoot "install"
$VenvDir = Join-Path $RepoRoot ".venv"

Write-Host "== doc-check 安装器 ==" -ForegroundColor Cyan
Write-Host "仓库目录：$RepoRoot"

# --- 1. 选择解释器 ---
$Candidates = @(
    @{ Exe = "py";    Args = @("-3.12") },
    @{ Exe = "py";    Args = @("-3.11") },
    @{ Exe = "py";    Args = @("-3.13") },
    @{ Exe = "python3"; Args = @() },
    @{ Exe = "python";  Args = @() },
    @{ Exe = "py";    Args = @("-3") }
)

$PyExe = $null
foreach ($c in $Candidates) {
    $cmd = Get-Command $c.Exe -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    try {
        $ver = & $c.Exe @($c.Args) -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    } catch { continue }
    if ($LASTEXITCODE -ne 0 -or -not $ver) { continue }
    $parts = $ver.Trim().Split('.')
    if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 9)) { continue }
    Write-Host "使用解释器：$($c.Exe) $($c.Args -join ' ')  (Python $ver)"
    $PyExe = @{ Exe = $c.Exe; Args = $c.Args; Ver = $ver }
    break
}

if (-not $PyExe) {
    Write-Host "未找到 Python 3.9 及以上解释器。请安装 Python 3.11 或 3.12 后重试。" -ForegroundColor Red
    exit 1
}

# --- 2. 创建虚拟环境 ---
if (-not (Test-Path $VenvDir)) {
    Write-Host "创建虚拟环境 .venv ..."
    & $PyExe.Exe @($PyExe.Args) -m venv $VenvDir
}
$VenvPy = Join-Path $VenvDir "Scripts/python.exe"
if (-not (Test-Path $VenvPy)) {
    Write-Host "虚拟环境创建失败：$VenvPy 不存在" -ForegroundColor Red
    exit 1
}

# --- 3. 安装依赖 ---
Write-Host "安装依赖 ..."
& $VenvPy -m pip install --upgrade pip | Out-Null
& $VenvPy -m pip install -r (Join-Path $RepoRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Host "依赖安装失败。Python $($PyExe.Ver) 可能缺少预编译轮子，请改用 Python 3.11 或 3.12。" -ForegroundColor Red
    exit 1
}

# --- 4. 依赖自检 ---
& $VenvPy -c "import docx, openpyxl, pdfplumber, lxml"
if ($LASTEXITCODE -ne 0) {
    Write-Host "依赖导入自检失败，请换用 Python 3.11 或 3.12 重建虚拟环境。" -ForegroundColor Red
    exit 1
}
Write-Host "依赖自检通过。"

# --- 5. 安装到各智能体 ---
$Adapters = Get-Content (Join-Path $InstallDir "adapters.json") -Raw | ConvertFrom-Json
$Installed = @()
$Skipped = @()

foreach ($a in $Adapters.agents) {
    if ($a.mode -eq "manual") { $Skipped += $a.name; continue }

    $found = $false
    foreach ($p in $a.detect_paths) {
        $expanded = [Environment]::ExpandEnvironmentVariables(
            $p.Replace("~", $env:USERPROFILE))
        if (Test-Path $expanded) { $found = $true; break }
    }
    if (-not $found) {
        foreach ($cmdName in $a.detect_commands) {
            if (Get-Command $cmdName -ErrorAction SilentlyContinue) { $found = $true; break }
        }
    }
    if (-not $found) { $Skipped += $a.name; continue }

    $target = [Environment]::ExpandEnvironmentVariables(
        $a.skill_dir.Replace("~", $env:USERPROFILE))
    New-Item -ItemType Directory -Force -Path $target | Out-Null

    foreach ($item in @("SKILL.md", "references", "scripts", "requirements.txt")) {
        $src = Join-Path $RepoRoot $item
        if (Test-Path $src) {
            Copy-Item $src -Destination $target -Recurse -Force
        }
    }

    Set-Content -Path (Join-Path $target "python-path.txt") -Value $VenvPy -Encoding UTF8

    $templatePath = Join-Path $InstallDir "adapters/$($a.id).md"
    if (Test-Path $templatePath) {
        $template = (Get-Content $templatePath -Raw).Replace("{{REPO_ROOT}}", $RepoRoot.Replace("\", "/"))
        Set-Content -Path (Join-Path $target $a.entry) -Value $template -Encoding UTF8
    }

    $Installed += [pscustomobject]@{ Name = $a.name; Path = $target; Usage = $a.usage }
}

# --- 6. 输出结果 ---
Write-Host ""
Write-Host "== 安装完成 ==" -ForegroundColor Green
foreach ($i in $Installed) {
    Write-Host "[已安装] $($i.Name) -> $($i.Path)" -ForegroundColor Green
    Write-Host "          用法：$($i.Usage)"
}
if ($Skipped.Count -gt 0) {
    Write-Host ""
    Write-Host "未检测到（已跳过）：$($Skipped -join '、')" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "通用接入方式见 install/adapters/generic.md"
Write-Host "仓库目录：$RepoRoot"
```

- [ ] **Step 6: 写 install/install.sh**

```bash
#!/usr/bin/env bash
# doc-check 安装器
# 用法：bash install/install.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$REPO_ROOT/.venv"

echo "== doc-check 安装器 =="
echo "仓库目录：$REPO_ROOT"

# --- 1. 选择解释器 ---
PY_EXE=""
PY_ARGS=()
for cand in "python3.12:" "python3.11:" "python3.13:" "python3:" "python:" "py:-3"; do
    exe="${cand%%:*}"
    args="${cand#*:}"
    if ! command -v "$exe" >/dev/null 2>&1; then continue; fi
    ver="$("$exe" $args -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
    [ -n "$ver" ] || continue
    major="${ver%%.*}"
    minor="${ver#*.}"
    if [ "$major" -lt 3 ]; then continue; fi
    if [ "$major" -eq 3 ] && [ "$minor" -lt 9 ]; then continue; fi
    echo "使用解释器：$exe $args  (Python $ver)"
    PY_EXE="$exe"
    PY_ARGS="$args"
    break
done

if [ -z "$PY_EXE" ]; then
    echo "未找到 Python 3.9 及以上解释器。请安装 Python 3.11 或 3.12 后重试。" >&2
    exit 1
fi

# --- 2. 创建虚拟环境 ---
if [ ! -d "$VENV_DIR" ]; then
    echo "创建虚拟环境 .venv ..."
    "$PY_EXE" $PY_ARGS -m venv "$VENV_DIR"
fi
VENV_PY="$VENV_DIR/bin/python"
if [ ! -x "$VENV_PY" ]; then
    echo "虚拟环境创建失败：$VENV_PY 不存在" >&2
    exit 1
fi

# --- 3. 安装依赖 ---
echo "安装依赖 ..."
"$VENV_PY" -m pip install --upgrade pip >/dev/null
"$VENV_PY" -m pip install -r "$REPO_ROOT/requirements.txt"

# --- 4. 依赖自检 ---
"$VENV_PY" -c "import docx, openpyxl, pdfplumber, lxml"
echo "依赖自检通过。"

# --- 5. 安装到各智能体 ---
installed_names=""
skipped_names=""

"$PY_EXE" $PY_ARGS - "$REPO_ROOT" "$VENV_PY" <<'PYEOF'

import json, os, shutil, sys
from pathlib import Path

repo_root = Path(sys.argv[1])
venv_py = sys.argv[2]
install_dir = repo_root / "install"
adapters = json.loads((install_dir / "adapters.json").read_text(encoding="utf-8"))

installed, skipped = [], []
for a in adapters["agents"]:
    if a["mode"] == "manual":
        skipped.append(a["name"])
        continue
    found = False
    for p in a.get("detect_paths", []):
        if Path(os.path.expanduser(p)).exists():
            found = True
            break
    if not found:
        for c in a.get("detect_commands", []):
            if shutil.which(c):
                found = True
                break
    if not found:
        skipped.append(a["name"])
        continue
    target = Path(os.path.expanduser(a["skill_dir"]))
    target.mkdir(parents=True, exist_ok=True)
    for item in ("SKILL.md", "references", "scripts", "requirements.txt"):
        src = repo_root / item
        if src.is_dir():
            shutil.copytree(src, target / item, dirs_exist_ok=True)
        elif src.exists():
            shutil.copy2(src, target / item)
    (target / "python-path.txt").write_text(venv_py, encoding="utf-8")
    tpl = install_dir / "adapters" / f"{a['id']}.md"
    if tpl.exists():
        (target / a["entry"]).write_text(
            tpl.read_text(encoding="utf-8").replace("{{REPO_ROOT}}", repo_root.as_posix()),
            encoding="utf-8",
        )
    installed.append((a["name"], str(target), a.get("usage", "")))

print("")
print("== 安装完成 ==")
for name, path, usage in installed:
    print(f"[已安装] {name} -> {path}")
    print(f"          用法：{usage}")
if skipped:
    print("")
    print(f"未检测到（已跳过）：{'、'.join(skipped)}")
print("")
print("通用接入方式见 install/adapters/generic.md")
print(f"仓库目录：{repo_root}")
PYEOF
```

- [ ] **Step 7: 运行测试确认通过**

Run: `python -m pytest tests/test_install_assets.py -v`
Expected: PASS，7 passed

- [ ] **Step 8: 冒烟测试安装器（不实际安装到智能体目录）**

Run: `bash -n install/install.sh`（语法检查）与 `pwsh -NoProfile -Command "& { $errors = $null; [System.Management.Automation.Language.Parser]::ParseFile('install/install.ps1', [ref]$null, [ref]$errors); if ($errors) { $errors | Out-String; exit 1 } else { 'PowerShell 语法 OK' } }"`

Expected: 两个脚本语法检查通过。若环境无 pwsh，改用 `powershell -NoProfile -Command "..."` 做同样的解析检查。

- [ ] **Step 9: 提交**

```bash
git add install/ tests/test_install_assets.py
git commit -m "feat: add cross-agent installer with adapter map"
```

---

## Task 18: check_env.py

**Files:**
- Create: `scripts/check_env.py`
- Create: `tests/test_check_env.py`

**Interfaces:**
- Consumes: 无
- Produces: `check_env.check() -> dict`，返回 `{"ok": bool, "python": str, "missing": list[str], "venv": str | None, "notes": list[str]}`

- [ ] **Step 1: 写失败的测试**

`tests/test_check_env.py`:
```python
from check_env import check


def test_check_returns_keys():
    r = check()
    for key in ["ok", "python", "missing", "venv", "notes"]:
        assert key in r


def test_check_ok_is_bool():
    r = check()
    assert isinstance(r["ok"], bool)


def test_check_missing_is_list():
    r = check()
    assert isinstance(r["missing"], list)
    assert isinstance(r["notes"], list)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_check_env.py -v`
Expected: FAIL，模块不存在

- [ ] **Step 3: 实现 check_env.py**

`scripts/check_env.py`:
```python
"""环境自检。检查 Python 版本、依赖导入、虚拟环境。"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

REQUIRED_MODULES = ["docx", "openpyxl", "pdfplumber", "lxml"]
MIN_PYTHON = (3, 9)


def check() -> dict:
    notes: list[str] = []
    missing: list[str] = []

    version = ".".join(str(v) for v in sys.version_info[:3])
    if sys.version_info[:2] < MIN_PYTHON:
        notes.append(f"Python {version} 低于要求的 3.9")

    for name in REQUIRED_MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:
            missing.append(f"{name}（{type(exc).__name__}）")

    repo = Path(__file__).resolve().parent.parent
    venv_candidates = [
        repo / ".venv" / "Scripts" / "python.exe",
        repo / ".venv" / "bin" / "python",
    ]
    venv = None
    for c in venv_candidates:
        if c.exists():
            venv = str(c)
            break
    if venv is None:
        notes.append("未找到仓库内的 .venv，若依赖未装入当前解释器，请运行 install/install.ps1")

    return {
        "ok": not missing and not notes,
        "python": version,
        "missing": missing,
        "venv": venv,
        "notes": notes,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="doc-check 环境自检")
    parser.parse_args(argv)
    r = check()
    print(f"Python：{r['python']}")
    print(f"虚拟环境：{r['venv'] or '未找到'}")
    if r["missing"]:
        print("缺少依赖：" + "、".join(r["missing"]))
    for n in r["notes"]:
        print("提示：" + n)
    print("环境自检通过。" if r["ok"] else "环境自检未通过，请先解决上面的问题。")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_check_env.py -v`
Expected: PASS，3 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/check_env.py tests/test_check_env.py
git commit -m "feat: add environment self-check"
```

---

## Task 19: README、样本生成与端到端测试

**Files:**
- Create: `README.md`
- Create: `tests/make_samples.py`
- Create: `tests/test_end_to_end.py`

**Interfaces:**
- Consumes: `prepare.prepare`、`render.render`、`analyze.analyze`
- Produces: `tests/samples/` 下的埋错样本与一条端到端流水线测试

- [ ] **Step 1: 写样本生成脚本**

`tests/make_samples.py`:
```python
"""生成含故意埋错的测试样本。用法：python tests/make_samples.py"""
from __future__ import annotations

from pathlib import Path

import docx
import openpyxl
from docx.shared import Pt

SAMPLES = Path(__file__).resolve().parent / "samples"


def make_docx(path: Path) -> None:
    d = docx.Document()
    d.add_heading("第一章 投标文件", level=1)
    d.add_heading("技术方案", level=2)
    d.add_paragraph("本文件由北京华信科技有限公司编制。")
    p = d.add_paragraph("本公司具备相关资质，帐号信息见附件。")
    p.runs[0].font.size = Pt(12)
    d.add_paragraph("一、总体要求")
    d.add_paragraph("1. 适用范围")
    d.add_paragraph("（一）背景说明")
    d.add_paragraph("1.1 实施进度")
    d.add_paragraph("本项目工期为 60 日历天。")
    d.add_paragraph("相关依据[1]说明本方案满足要求。")
    d.add_paragraph("如图1-1所示的设备清单。")
    p2 = d.add_paragraph("本项目工期为 90 日历天。")
    p2.runs[0].font.size = Pt(10.5)
    p2.runs[0].font.name = "仿宋"
    d.add_paragraph("本项目金额为 120 万元。")
    d.add_paragraph("本次费用 3000 元。")
    d.add_paragraph("签署日期 2024年1月1日，生效日期 2024-01-01。")
    d.add_paragraph("具体内容详见附件。")
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text = "项目"
    t.cell(0, 1).text = "数量"
    t.cell(1, 0).text = "设备"
    t.cell(1, 1).text = "10"
    d.save(str(path))


def make_xlsx(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "报价表"
    ws["A1"] = "项目"
    ws["B1"] = "数量"
    ws["A2"] = "设备"
    ws["B2"] = 10
    ws["B2"].number_format = "#,##0.00"
    ws["A3"] = "服务"
    ws["B3"] = 5
    ws["B3"].number_format = "General"
    ws2 = wb.create_sheet("明细")
    ws2["A1"] = "名称"
    ws2["B1"] = "金额"
    ws2["A2"] = "设备"
    ws2["B2"] = 1200000
    wb.save(str(path))


def make_md(path: Path) -> None:
    path.write_text(
        "# 投标文件\n\n## 技术方案\n\n"
        "本项目由北京华信科技有限公司负责。\n\n"
        "| 项目 | 数量 |\n| --- | --- |\n| 设备 | 10 |\n",
        encoding="utf-8",
    )


def main() -> None:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    make_docx(SAMPLES / "sample_company.docx")
    make_xlsx(SAMPLES / "sample_price.xlsx")
    make_md(SAMPLES / "sample_note.md")
    print(f"样本已生成到 {SAMPLES}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 写端到端测试**

`tests/test_end_to_end.py`:
```python
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = Path(__file__).resolve().parent / "samples"


def _ensure_samples():
    if not (SAMPLES / "sample_company.docx").exists():
        subprocess.run(
            [sys.executable, str(ROOT / "tests" / "make_samples.py")],
            check=True, cwd=str(ROOT),
        )


def test_end_to_end_pipeline(tmp_path):
    _ensure_samples()
    from prepare import prepare
    from render import render

    work = tmp_path / "work"
    out = tmp_path / "report.html"
    files = [
        SAMPLES / "sample_company.docx",
        SAMPLES / "sample_price.xlsx",
        SAMPLES / "sample_note.md",
    ]
    result = prepare(files, "standard", work)
    assert result["documents"] == 3
    assert result["failures"] == 0

    findings = [
        {
            "id": "e" * 16, "severity": "P1", "category": "前后矛盾",
            "detector": "llm", "confidence": "疑似 · 需人工核实",
            "file": "sample_company.docx",
            "locator": {"type": "paragraph", "index": 5, "section_path": "技术方案"},
            "quote": "本项目工期为 90 日历天。",
            "description": "与前文 60 日历天矛盾",
            "suggestion": "统一为 60 日历天",
        }
    ]
    (work / "findings.json").write_text(
        json.dumps(findings, ensure_ascii=False), encoding="utf-8"
    )

    render(work, out)
    html = out.read_text(encoding="utf-8")
    assert "文档检查报告" in html
    assert "前后矛盾" in html
    assert "未核实外部事实" in html
    assert (work / "last-findings.json").exists()


def test_end_to_end_catches_known_defects(tmp_path):
    _ensure_samples()
    from prepare import prepare

    work = tmp_path / "work"
    prepare([SAMPLES / "sample_company.docx"], "standard", work)
    consistency = json.loads((work / "consistency.json").read_text(encoding="utf-8"))
    cats = {i["category"] for i in consistency["issues"]}
    assert "字体一致性" in cats
    assert "数字与单位" in cats
    assert "标题层级体例" in cats
```

- [ ] **Step 3: 运行端到端测试确认通过**

Run: `python -m pytest tests/test_end_to_end.py -v`
Expected: PASS，2 passed

若 `test_end_to_end_catches_known_defects` 失败，按实际输出调整样本或判定阈值，不要放宽断言掩盖问题。

- [ ] **Step 4: 写 README.md**

```markdown
# doc-check

对一组投标文档做内容与格式检查，产出单文件 HTML 报告。

可安装到 Claude Code、Codex CLI、WorkBuddy、DSH 等任意能执行脚本并读写文件的智能体。

## 它检查什么

格式与体例（脚本判定，结果确定）：字体字号一致性、段落格式一致性、标题层级体例、图表题注体例、表格体例、主体名称写法一致性、数字与单位、引用标记、列表与编号、术语与缩写。

内容与逻辑（模型判定）：错别字用词、标点格式、前后矛盾、主体串写、引用张冠李戴、待补充内容、数字逻辑、表述不清、术语一致性。

## 它不做什么

不修改任何原始文档。不联网。不调用外部大模型 API。不做 OCR。

**不核实外部事实。** 企业名称在现实中是否真实存在、引用文献是否真实存在、法规是否现行有效，都无法确认，相关结论一律标注「疑似 · 需人工核实」。

## 安装

Windows：

```powershell
powershell -ExecutionPolicy Bypass -File install/install.ps1
```

macOS / Linux：

```bash
bash install/install.sh
```

安装器会：挑一个可用的 Python（优先 3.11 / 3.12，因为依赖在最新 Python 上可能没有预编译轮子）、在仓库内建 `.venv`、装四个依赖、探测本机装了哪些智能体并把技能装进去。

装完会打印每个智能体的用法。若你的智能体没被检测到，用通用接入方式：把 `install/adapters/generic.md` 里的片段贴进你的智能体项目说明。

## 用法

在智能体里说「检查这几个文档」并给出文件路径，或直接调用 `/doc-check`。命令行手工跑：

```bash
python scripts/prepare.py --files 投标文件.docx 报价表.xlsx --depth standard --work .doc-check-work
# 读 .doc-check-work/chunks.json 与 references/content-rules.md
# 写 .doc-check-work/findings.json
python scripts/render.py --work .doc-check-work --out report.html
```

复查模式（改完一轮再查，只看新增与未修复）：

```bash
python scripts/render.py --work .doc-check-work --out report.html --baseline .doc-check-work/last-findings.json
```

## 深度档位

| 档位 | 覆盖 |
|---|---|
| quick | 阶段①全量 + 错别字、标点、表述不清、术语一致性 |
| standard | 阶段①全量 + 九类语义检查全做（默认） |
| deep | 阶段①全量 + 逐段细读，邻接窗口更大 |

## 输出

单个 HTML 文件，CSS 内联，无外部依赖，可离线打开、邮件转发、长期归档。含打印样式。

章节：检查范围与未能检查项、结论概览、硬伤速览、按文件明细、一致性差异、待补充与待核实、复查对比、附录。

## 目录结构

```
SKILL.md            智能体主指令
AGENTS.md           通用接入说明
scripts/            抽取、统计、分片、渲染
references/         语义规则、格式规则、严重级别与 schema、报告规范
install/            安装器与智能体适配表
tests/              单元测试、端到端测试、样本生成
```

## 开发

```bash
python -m pytest -v
python tests/make_samples.py
```

模型层不进 CI（输出有不确定性）。评估方法：准备一批人工标注的样本文档，统计模型在样本上的召回率与误报率，见 `tests/gold/README.md`。

## 许可

MIT
```

- [ ] **Step 5: 运行全部测试**

Run: `python -m pytest -v`
Expected: 全部 PASS，无 error

- [ ] **Step 6: 提交**

```bash
git add README.md tests/make_samples.py tests/test_end_to_end.py tests/samples/
git commit -m "docs: add readme with samples and end-to-end pipeline test"
```

---

## Task 20: 金标评估脚本

**Files:**
- Create: `tests/gold/README.md`
- Create: `tests/gold/gold_set.json`
- Create: `scripts/evaluate.py`
- Create: `tests/test_evaluate.py`

**Interfaces:**
- Consumes: `schema.fingerprint`
- Produces: `evaluate.evaluate(gold: list[dict], predicted: list[dict]) -> dict`，返回 `{"recall", "precision", "matched", "gold_total", "predicted_total", "missing", "false_positives"}`

金标格式（`tests/gold/gold_set.json`）：

```json
{
  "note": "人工标注的样本问题集合。匹配依据为 file + category + quote 归一化后的指纹。",
  "items": [
    {
      "file": "sample_company.docx",
      "category": "错别字用词",
      "quote": "帐号信息见附件",
      "severity": "P2"
    }
  ]
}
```

- [ ] **Step 1: 写失败的测试**

`tests/test_evaluate.py`:
```python
from evaluate import evaluate


def _g(file="a.docx", category="错别字用词", quote="帐号"):
    return {"file": file, "category": category, "quote": quote}


def _p(file="a.docx", category="错别字用词", quote="帐号"):
    return {
        "id": "f" * 16, "severity": "P2", "category": category,
        "detector": "llm", "confidence": "确定", "file": file,
        "locator": {"type": "paragraph", "index": 1},
        "quote": quote, "description": "d", "suggestion": "s",
    }


def test_evaluate_perfect_match():
    r = evaluate([_g()], [_p()])
    assert r["recall"] == 1.0
    assert r["precision"] == 1.0
    assert r["missing"] == []


def test_evaluate_detects_miss():
    r = evaluate([_g(), _g(quote="错别")], [_p()])
    assert r["recall"] == 0.5
    assert len(r["missing"]) == 1


def test_evaluate_detects_false_positive():
    r = evaluate([_g()], [_p(), _p(quote="多出来的")])
    assert r["precision"] == 0.5
    assert len(r["false_positives"]) == 1


def test_evaluate_empty_gold():
    r = evaluate([], [_p()])
    assert r["recall"] == 1.0
    assert r["precision"] == 0.0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_evaluate.py -v`
Expected: FAIL，模块不存在

- [ ] **Step 3: 实现 evaluate.py**

`scripts/evaluate.py`:
```python
"""金标评估：统计模型输出的召回率与误报率。

用法：
    python scripts/evaluate.py --gold tests/gold/gold_set.json --predicted .doc-check-work/findings.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import normalize_text


def _key(item: dict) -> str:
    return "|".join([
        item.get("file", ""),
        item.get("category", ""),
        normalize_text(item.get("quote", "")),
    ])


def evaluate(gold: list[dict], predicted: list[dict]) -> dict:
    gold_map = {_key(g): g for g in gold}
    pred_map = {_key(p): p for p in predicted}

    matched = [k for k in gold_map if k in pred_map]
    missing = [gold_map[k] for k in gold_map if k not in pred_map]
    false_positives = [pred_map[k] for k in pred_map if k not in gold_map]

    gold_total = len(gold_map)
    pred_total = len(pred_map)
    recall = len(matched) / gold_total if gold_total else 1.0
    precision = len(matched) / pred_total if pred_total else 0.0
    return {
        "recall": round(recall, 4),
        "precision": round(precision, 4),
        "matched": len(matched),
        "gold_total": gold_total,
        "predicted_total": pred_total,
        "missing": missing,
        "false_positives": false_positives,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="doc-check 金标评估")
    parser.add_argument("--gold", required=True, help="金标 JSON 路径")
    parser.add_argument("--predicted", required=True, help="模型输出 findings.json 路径")
    args = parser.parse_args(argv)

    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))
    gold_items = gold["items"] if isinstance(gold, dict) else gold
    predicted = json.loads(Path(args.predicted).read_text(encoding="utf-8"))
    predicted_items = predicted["findings"] if isinstance(predicted, dict) else predicted

    r = evaluate(gold_items, predicted_items)
    print(f"召回率：{r['recall']:.2%}（命中 {r['matched']}/{r['gold_total']}）")
    print(f"准确率：{r['precision']:.2%}（{r['matched']}/{r['predicted_total']}）")
    if r["missing"]:
        print("\n漏报：")
        for m in r["missing"]:
            print(f"  - [{m.get('category')}] {m.get('file')}：{m.get('quote')}")
    if r["false_positives"]:
        print("\n误报：")
        for f in r["false_positives"]:
            print(f"  - [{f.get('category')}] {f.get('file')}：{f.get('quote')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 写 tests/gold/README.md 与初始金标**

`tests/gold/README.md`:
```markdown
# 金标评估

模型输出有不确定性，不进 CI。改用金标评估来判断规则与提示词是否需要调整。

## 做法

1. 准备一批带已知问题的文档（可用 `tests/make_samples.py` 生成的样本，也可另备真实文档）。
2. 人工标注所有已知问题，填入 `gold_set.json`。每条包含 `file`、`category`、`quote`、`severity`。`quote` 必须是原文片段。
3. 跑一次完整检查，得到 `findings.json`。
4. 执行：

```bash
python scripts/evaluate.py --gold tests/gold/gold_set.json --predicted .doc-check-work/findings.json
```

5. 记录召回率与准确率。漏报多的类别优先补规则，误报多的类别优先收紧判定条件。

## 匹配依据

`file` + `category` + 归一化后的 `quote` 三元组。引号差异与空白差异不会影响匹配。

## 样本量建议

起步 10 至 15 份文档、约 100 条标注。样本量小于 30 条时，召回率的波动会很大，只用于发现明显缺口，不用于比较版本优劣。
```

`tests/gold/gold_set.json`:
```json
{
  "note": "人工标注的样本问题集合。匹配依据为 file + category + quote 归一化后的指纹。",
  "items": [
    {
      "file": "sample_company.docx",
      "category": "错别字用词",
      "quote": "帐号信息见附件",
      "severity": "P2"
    },
    {
      "file": "sample_company.docx",
      "category": "前后矛盾",
      "quote": "本项目工期为 60 日历天。",
      "severity": "P1"
    },
    {
      "file": "sample_company.docx",
      "category": "待补充内容",
      "quote": "具体内容详见附件。",
      "severity": "P2"
    },
    {
      "file": "sample_company.docx",
      "category": "数字与单位",
      "quote": "本次费用 3000 元。",
      "severity": "P1"
    }
  ]
}
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_evaluate.py -v`
Expected: PASS，4 passed

- [ ] **Step 6: 跑一次完整测试套件**

Run: `python -m pytest -v`
Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add scripts/evaluate.py tests/gold/ tests/test_evaluate.py
git commit -m "feat: add gold set evaluation harness"
```

---

## 实施顺序与验收

### 任务顺序

Task 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15 → 16 → 17 → 18 → 19 → 20

Task 2、3、4、5 可并行开发（各自独立）。Task 6 依赖 Task 1。Task 8 依赖 Task 7。Task 12 依赖 Task 5、8、9、10、11。Task 13 依赖 Task 7。Task 14 依赖 Task 13。Task 16 依赖 Task 12、13、14。Task 17 与 Task 18 可并行。

### 整体验收标准

全部完成后，以下必须成立：

```bash
python -m pytest -v            # 全部 PASS，无 error
python scripts/check_env.py     # 环境自检通过
```

且以下手工验证必须成立：

1. `python scripts/prepare.py --files <真实投标文档> --depth standard --work .doc-check-work` 生成四个 JSON，失败文件在 manifest 的 failures 中被如实记录。
2. 人工按 `references/content-rules.md` 写一份 findings.json，`python scripts/render.py --work .doc-check-work --out report.html` 生成的 HTML 在浏览器中打开正常，全部 8 个章节可见，无外部资源请求。
3. 报告中的样式问题在 docx 样本文档上被正确检出（字体一致性、标题层级体例、数字与单位）。
4. `bash install/install.sh` 在 POSIX 环境跑通；`powershell -ExecutionPolicy Bypass -File install/install.ps1` 在 Windows 环境跑通，且不破坏已装的 Claude Code 与 Codex 技能。
5. 技能装到 `~/.claude/skills/doc-check` 后，在 Claude Code 中说「检查这批文档」能走完三阶段并产出 HTML 报告。
6. 同一批文档在 Claude Code 与 Codex 中跑出的 `consistency.json` 完全一致（确定性层的跨智能体一致性保证）。
