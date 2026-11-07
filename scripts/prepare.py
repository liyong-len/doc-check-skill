"""阶段①：抽取 → 确定性检查 → 分片。

用法：
    python scripts/prepare.py --files a.docx b.xlsx --depth standard --work .doc-check-work
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyze import analyze
from chunk import build_chunks
from common import force_utf8_stdio, write_json
from extractors import extract_document
from manifest import build_manifest


def _ocr_reason(doc: dict, has_text: bool) -> str:
    """扫描件未检查原因。

    抽取器给的 notes 是一页一条（如「第 1 页无文本层，疑似扫描件，需 OCR」），
    外加一条全文级的说明。直接把它们全拼上去，同一句「需 OCR」会在一个
    单元格里出现三次，读者看不出到底缺什么。这里合成一句话：
    总述一次，逐页的只说哪几页缺文本层。
    """
    parts = ["需 OCR，当前不支持。"]
    if not has_text:
        parts.append("该文档无文本层，未做任何内容判定。")
    page_notes: list[str] = []
    for note in doc.get("notes", []):
        if "无文本层" in note and note.startswith("第"):
            # 「，需 OCR」与总述重复
            page_notes.append(note.replace("，需 OCR", ""))
        elif "没有页面" in note:
            page_notes.append("PDF 没有页面，无法读取。")
        elif "全文无文本层" in note:
            # 全文级说明已由「该文档无文本层」覆盖，不重复
            if has_text:
                page_notes.append(note.replace("，需 OCR", ""))
    seen: list[str] = []
    for n in page_notes:
        if n not in seen:
            seen.append(n)
    if seen:
        parts.append("；".join(seen) + "。")
    return " ".join(parts)


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
    reason = _ocr_reason(doc, has_text)
    return {"file": doc["file"], "path": doc["path"], "reason": reason}, has_text


def _file_ids(paths: list[str]) -> list[str]:
    """给一组文件路径分配互不相同的文件标识。

    两个不同目录下的 report.docx 若都叫 report.docx，清单里会出现
    两条同名记录，分片 id 也撞车（「report.docx:0」出现两次），
    其中一份从报告里消失，每条问题还都会重复一遍。
    同名的用相对路径（a/report.docx）区分，不名的保持文件名。
    """
    names = [Path(p).name for p in paths]
    by_name: dict[str, list[int]] = {}
    for i, name in enumerate(names):
        by_name.setdefault(name, []).append(i)
    out = list(names)
    for name, idxs in by_name.items():
        if len(idxs) < 2:
            continue
        group = [paths[i] for i in idxs]
        for i, file_id in zip(idxs, _disambiguate(group)):
            out[i] = file_id
    return out


def _disambiguate(paths: list[str]) -> list[str]:
    """一组同名文件的互不相同 id：先相对路径，再加序号。"""
    resolved = [Path(p).resolve() for p in paths]
    try:
        common = Path(os.path.commonpath([str(p) for p in resolved]))
    except ValueError:      # 不在同一个盘上
        common = resolved[0].parent
    ids = []
    for p in resolved:
        try:
            rel = p.relative_to(common)
        except ValueError:
            rel = None
        if rel is None or str(rel) == ".":
            ids.append(p.name)      # 同一个文件被传了两次
        else:
            ids.append(rel.as_posix())
    counts: dict[str, int] = {}
    for i in ids:
        counts[i] = counts.get(i, 0) + 1
    seen: dict[str, int] = {}
    out = []
    for i in ids:
        if counts[i] > 1:
            seen[i] = seen.get(i, 0) + 1
            out.append(f"{i} ({seen[i]})")
        else:
            out.append(i)
    return out


def prepare(files: list[Path], depth: str, work: Path) -> dict:
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)

    documents = []
    failures = []
    # 文件标识在抽取之前就定下来：抽取失败的文件也要有同一个标识，
    # 否则 §0 的「未能检查的文件」里显示的是另一个名字。
    file_ids = _file_ids([str(f) for f in files])
    for path, file_id in zip(files, file_ids):
        path = Path(path)
        if not path.exists():
            failures.append({
                "file": file_id,
                "path": str(path.resolve()),
                "reason": "文件不存在",
            })
            continue
        try:
            doc = extract_document(path)
        except Exception as exc:  # 单文件失败不中断整体
            failures.append({
                "file": file_id,
                "path": str(path.resolve()),
                "reason": f"抽取失败：{type(exc).__name__}: {exc}",
            })
            continue
        doc["file"] = file_id
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
        # failures 返回清单本身（不是条数），调用方才能逐条看失败原因。
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

    force_utf8_stdio()
    result = prepare([Path(f) for f in args.files], args.depth, Path(args.work))
    print(f"已抽取 {result['documents']} 份文档，{result['failure_count']} 份失败")
    print(f"确定性检查发现 {result['issues']} 个问题，分片 {result['chunks']} 片")
    print(f"工作目录：{result['work']}")
    if result["failures"]:
        print("未能检查的文件见 manifest.json 的 failures 字段", file=sys.stderr)
    if result["documents"] == 0 and result["failures"]:
        return 1  # 一份都没检查成功，调用方必须能察觉
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
