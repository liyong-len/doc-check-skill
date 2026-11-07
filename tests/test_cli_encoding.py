"""命令行输出必须是 UTF-8 字节（I10）。

Windows 上 sys.stdout.encoding 默认是系统码页（GBK），中文提示会按 GBK
写出去。读进程输出（而不是读 JSON 文件）的智能体拿到的是乱码，
「已抽取 3 份文档，0 份失败」会变成一串问号。
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

# 用 PYTHONIOENCODING 把「平台码页」固定成 GBK，
# 这样测试在任何语言的机器上跑出来的是同一个结果。
GBK_ENV = {**os.environ, "PYTHONIOENCODING": "gbk"}


def _run(script: str, args: list[str]):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True, env=GBK_ENV, cwd=str(ROOT),
    )


def _decode(data: bytes, what: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AssertionError(
            f"{what} 不是 UTF-8 字节，智能体读进程输出会得到乱码：{data[:120]!r}"
        ) from exc


class _FakeStream:
    """记录 reconfigure 调用的假标准流。"""

    def __init__(self):
        self.encoding = "gbk"
        self.calls: list[dict] = []
        self.text = io.StringIO()

    def reconfigure(self, **kwargs):
        self.calls.append(kwargs)
        self.encoding = kwargs.get("encoding", self.encoding)

    def write(self, s):
        return self.text.write(s)

    def flush(self):
        pass

    def isatty(self):
        return False


def _make_docx(path: Path, text="正文内容。"):
    import docx

    d = docx.Document()
    d.add_heading("标题", level=1)
    d.add_paragraph(text)
    d.save(str(path))
    return path


# --- 端到端：进程输出必须是 UTF-8 字节 ---


def test_prepare_cli_stdout_is_utf8(tmp_path):
    src = _make_docx(tmp_path / "a.docx")
    proc = _run("prepare.py", ["--files", str(src), "--work", str(tmp_path / "work")])
    assert proc.returncode == 0, proc.stderr
    out = _decode(proc.stdout, "prepare.py 的 stdout")
    assert "已抽取 1 份文档" in out
    assert "0 份失败" in out


def test_render_cli_stdout_is_utf8(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "manifest.json").write_text(json.dumps({
        "script_version": "0.1.0", "depth": "standard", "generated_at": "",
        "documents": [], "failures": [],
    }, ensure_ascii=False), encoding="utf-8")
    (work / "consistency.json").write_text(json.dumps({
        "style_profile": {}, "issues": [], "entities": {}, "stats": {},
    }, ensure_ascii=False), encoding="utf-8")
    proc = _run("render.py", ["--work", str(work), "--out", str(tmp_path / "r.html")])
    assert proc.returncode == 0, proc.stderr
    out = _decode(proc.stdout, "render.py 的 stdout")
    assert "报告已生成" in out


def test_render_cli_stderr_is_utf8(tmp_path):
    """校验失败的信息走 stderr，也必须是 UTF-8。"""
    work = tmp_path / "work"
    work.mkdir()
    (work / "manifest.json").write_text(json.dumps({
        "script_version": "0.1.0", "depth": "standard", "generated_at": "",
        "documents": [], "failures": [],
    }, ensure_ascii=False), encoding="utf-8")
    (work / "consistency.json").write_text(json.dumps({
        "style_profile": {}, "issues": [], "entities": {}, "stats": {},
    }, ensure_ascii=False), encoding="utf-8")
    (work / "findings.json").write_text(json.dumps(
        [{"severity": "P9", "category": "前后矛盾", "detector": "llm",
          "confidence": "确定", "file": "a.docx", "locator": {"type": "file"},
          "quote": "q", "description": "d", "suggestion": "s"}],
        ensure_ascii=False), encoding="utf-8")
    proc = _run("render.py", ["--work", str(work), "--out", str(tmp_path / "r.html")])
    assert proc.returncode == 2
    err = _decode(proc.stderr, "render.py 的 stderr")
    assert "findings.json 校验失败" in err


def test_check_env_cli_stdout_is_utf8():
    proc = _run("check_env.py", [])
    out = _decode(proc.stdout, "check_env.py 的 stdout")
    assert "Python：" in out


# --- 单元：三处 main() 都要把标准流切成 UTF-8 ---


def test_force_utf8_stdio_reconfigures_both_streams(monkeypatch):
    from common import force_utf8_stdio

    out, err = _FakeStream(), _FakeStream()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    force_utf8_stdio()
    assert out.calls and out.calls[0].get("encoding") == "utf-8"
    assert err.calls and err.calls[0].get("encoding") == "utf-8"


def test_force_utf8_stdio_survives_a_stream_without_reconfigure(monkeypatch):
    """没有 reconfigure 的流（被替换过的 stdout）不能让脚本崩掉。"""
    from common import force_utf8_stdio

    class _Plain:
        def write(self, s):
            return len(s)

    monkeypatch.setattr(sys, "stdout", _Plain())
    monkeypatch.setattr(sys, "stderr", _Plain())
    force_utf8_stdio()   # 不得抛异常


def test_prepare_main_reconfigures_stdout(monkeypatch, tmp_path):
    from prepare import main as prepare_main

    src = _make_docx(tmp_path / "a.docx")
    fake = _FakeStream()
    monkeypatch.setattr(sys, "stdout", fake)
    monkeypatch.setattr(sys, "stderr", fake)
    prepare_main(["--files", str(src), "--work", str(tmp_path / "work")])
    assert any(c.get("encoding") == "utf-8" for c in fake.calls)


def test_render_main_reconfigures_stdout(monkeypatch, tmp_path):
    from render import main as render_main

    work = tmp_path / "work"
    work.mkdir()
    (work / "manifest.json").write_text(json.dumps({
        "script_version": "0.1.0", "depth": "standard", "generated_at": "",
        "documents": [], "failures": [],
    }, ensure_ascii=False), encoding="utf-8")
    (work / "consistency.json").write_text(json.dumps({
        "style_profile": {}, "issues": [], "entities": {}, "stats": {},
    }, ensure_ascii=False), encoding="utf-8")
    fake = _FakeStream()
    monkeypatch.setattr(sys, "stdout", fake)
    monkeypatch.setattr(sys, "stderr", fake)
    render_main(["--work", str(work), "--out", str(tmp_path / "r.html")])
    assert any(c.get("encoding") == "utf-8" for c in fake.calls)


def test_check_env_main_reconfigures_stdout(monkeypatch):
    from check_env import main as check_env_main

    fake = _FakeStream()
    monkeypatch.setattr(sys, "stdout", fake)
    monkeypatch.setattr(sys, "stderr", fake)
    check_env_main([])
    assert any(c.get("encoding") == "utf-8" for c in fake.calls)
