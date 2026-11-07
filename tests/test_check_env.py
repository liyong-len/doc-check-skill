import sys
from pathlib import Path

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


def test_check_python_matches_running_interpreter():
    r = check()
    assert r["python"].split(".")[:2] == [str(sys.version_info[0]), str(sys.version_info[1])]


def test_check_venv_path_exists_when_found():
    r = check()
    if r["venv"] is not None:
        assert Path(r["venv"]).exists(), r["venv"]
