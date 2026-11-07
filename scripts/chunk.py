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

    尾随的标点不算数字的一部分：「见 12.」的数字是 12，不是 12.。
    """
    out = []
    for m in _NUMBER_RE.finditer(text or ""):
        token = m.group(0).strip().rstrip(".,，")
        if len(token) <= 1:
            continue
        out.append(token)
        number = m.group(1).strip().rstrip(".,，")
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
        # 行的实际长度含单元格分隔符「 | 」与行分隔符，估算时一并计入，
        # 否则拆出来的块会比 max_chars 长出一截，deep 档位就名不副实了。
        row_len = (
            sum(len(c.get("text", "")) for c in row)
            + 3 * max(0, len(row) - 1)
            + 1
        )
        if current and size + row_len > max_chars:
            parts.append({**block, "rows": current})
            current = []
            size = 0
        current.append(row)
        size += row_len
    if current:
        parts.append({**block, "rows": current})
    return parts


def _neighbors(blocks: list[dict], first: int, last: int, window: int) -> dict:
    """分片两侧各取 window 个块的原文，作为跨片衔接的上下文。

    邻块取自分片**之外**：分片之前的是 first 之前的块，之后的是 last 之后的块。
    若按分片最后一个块取前邻，前邻就会落在分片内部，既重复分片已有的正文，
    又拿不到真正的前文（多块分片时尤其如此），邻接上下文也就失去了意义。

    blocks 是切分后的块序列（超长表格已按行拆成多块），因此这里的邻块
    与分片里的块首尾相接，表格拆出来的各段之间也有上下文。
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
        # 超长表格先按行拆开，否则一个 xlsx sheet 会成为唯一一块超大分片
        pieces: list[dict] = []
        for block in doc.get("blocks", []):
            pieces.extend(_split_table(block, max_chars))

        buffer: list[dict] = []
        buf_len = 0
        buf_start = 0
        seq = 0

        def flush():
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
                    pieces, buf_start, buf_start + len(buffer) - 1, window
                ),
                "entities": sorted(set(entities)),
                "numbers": sorted(set(numbers)),
                "citations": sorted(set(citations)),
                "block_indexes": [b["index"] for b in buffer],
            })
            seq += 1

        for pos, piece in enumerate(pieces):
            text = _block_text(piece)
            if buf_len and buf_len + len(text) > max_chars:
                flush()
                buffer = []
                buf_len = 0
                buf_start = pos
            buffer.append(piece)
            buf_len += len(text) + 1
        flush()
    return chunks
