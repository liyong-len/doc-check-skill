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
