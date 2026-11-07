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

    收录 locator 的全部键（按键名排序），保证任何携带信息的键都参与指纹，
    避免两个不同问题落到同一个 finding_id 上。键名排序保证不同运行、
    不同字典插入顺序下结果一致。
    """
    parts = [str(locator.get("type", ""))]
    parts += [
        f"{key}={_locator_value(locator[key])}"
        for key in sorted(locator)
        if key != "type" and locator[key] is not None
    ]
    return "/".join(parts)


def _locator_value(value: Any) -> str:
    """locator 值的稳定字符串形式；容器按排序键序列化，避免插入顺序影响指纹。"""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return str(value)
