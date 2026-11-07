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
    reason += (
        "该文档无文本层，未做任何内容判定。"
        if not has_text
        else " " + " ".join(notes)
    )
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
                "path": str(path),
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
        # failures 返回清单本身（不是条数），调用方才能逐条看失败原因。
        "failures": failures,
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
    print(f"已抽取 {result['documents']} 份文档，{len(result['failures'])} 份失败")
    print(f"确定性检查发现 {result['issues']} 个问题，分片 {result['chunks']} 片")
    print(f"工作目录：{result['work']}")
    if result["failures"]:
        print("未能检查的文件见 manifest.json 的 failures 字段", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
