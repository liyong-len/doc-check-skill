from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# 用户的真实家目录里，技能可能被装到的位置。
_REAL_HOME_MARKERS = (
    ".claude/skills/doc-check",
    ".codex/skills/doc-check",
    "DoubaoWork/skills/doc-check",
    ".dsh/skills/doc-check",
)


def _real_home() -> Path:
    value = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    return Path(value) if value else Path.home()


@pytest.fixture(scope="session", autouse=True)
def no_writes_to_the_real_home():
    """测试套件不得在用户的真实家目录里留下任何 doc-check 副本。

    这个项目已经因为「某个安装测试没有隔离 HOME」在真实家目录里
    装过好几次：装完再去删，删没删干净也没人说得清。
    每一条安装测试都必须自己隔离 HOME/USERPROFILE；这一条守卫是最后一道，
    真装进去了，整个测试会话就红。

    判据是「会话前后多出来的目录」：本来就有的残留不算测试的锅。
    """
    home = _real_home()
    before = {m for m in _REAL_HOME_MARKERS if (home / m).exists()}
    yield
    after = {m for m in _REAL_HOME_MARKERS if (home / m).exists()}
    new = after - before
    assert not new, f"测试往真实家目录里写了东西：{sorted(new)}"
