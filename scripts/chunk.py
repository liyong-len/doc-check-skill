"""把文档切成模型可读的片段，附邻接上下文与预标注实体。"""
from __future__ import annotations

import re

from entities import extract_company_names

DEPTH_PARAMS = {
    "quick": {"max_chars": 3000, "neighbor_window": 0},
    "standard": {"max_chars": 3000, "neighbor_window": 1},
    "deep": {"max_chars": 1200, "neighbor_window": 3},
}

_NUMBER_RE = re.compile(r"(\d[\d,，.]*)\s*(?:%|万元|元|个|台|套|人|年|月|日)?")
_CITATION_RE = re.compile(r"文献\[\d+\]|\[\d+(?:[-–—,，]\d+)*\]|[（(]\d+[）)]|如图\s*[\d.\-－]+[所示]*")


def _citations(text: str) -> list[str]:
    out = []
    for m in _CITATION_RE.finditer(text or ""):
        out.append(m.group(0))
    return out


def _numbers(text: str) -> list[str]:
    """抽取数字。

    每个匹配给出两种写法：原样（含单位，如「1,200.00 元」）与裸数字
    （如「1,200.00」）。裸数字便于跨文档比对同一个数值，单位则保留量纲——
    少了它，「1,200 元」与「1,200 万元」在提示里就分不开了。
    """
    out = []
    for m in _NUMBER_RE.finditer(text or ""):
        token = m.group(0).strip()
        if not any(ch.isdigit() for ch in token) or len(token) <= 1:
            continue
        out.append(token)
        number = m.group(1).strip()
        if len(number) > 1 and number != token:
            out.append(number)
    return out


def _block_text(block: dict) -> str:
    if block.get("kind") == "table":
        cells = []
        for row in block.get("rows", []):
            cells.append(" | ".join(c.get("text", "") for c in row))
        return "\n".join(cells)
    return block.get("text", "")


def _neighbors(blocks: list[dict], first: int, last: int, window: int) -> dict:
    """分片两侧各取 window 个块的原文，作为跨片衔接的上下文。

    邻块取自分片**之外**：分片之前的是 first 之前的块，之后的是 last 之后的块。
    若按分片最后一个块取前邻，前邻就会落在分片内部，既重复分片已有的正文，
    又拿不到真正的前文（多块分片时尤其如此），邻接上下文也就失去了意义。
    """
    if window <= 0:
        return {"prev": "", "next": ""}
    prev_text = ""
    next_text = ""
    for j in range(max(0, first - window), first):
        prev_text += _block_text(blocks[j]) + "\n"
    for j in range(last + 1, min(len(blocks), last + 1 + window)):
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
                "neighbors": _neighbors(
                    blocks, buffer[0]["index"], buffer[-1]["index"], window
                ),
                "entities": sorted(set(entities)),
                "numbers": sorted(set(numbers)),
                "citations": sorted(set(citations)),
                "block_indexes": [b["index"] for b in buffer],
            })
            seq += 1

        for block in blocks:
            text = _block_text(block)
            if buf_len and buf_len + len(text) > max_chars:
                flush(buffer)
                buffer = []
                buf_len = 0
            buffer.append(block)
            buf_len += len(text) + 1
        flush(buffer)
    return chunks
