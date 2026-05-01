"""Tests for Profiler (Pass 16)."""
import time
from pathlib import Path
import pytest
from agency.profiler import Profiler, get_stats, report


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr("agency.profiler._DEFAULT_PATH", tmp_path / "prof.jsonl")


def test_elapsed_positive():
    with Profiler("test_op") as p:
        time.sleep(0.01)
    assert p.elapsed_s > 0


def test_records_entry():
    with Profiler("my_task"):
        pass
    stats = get_stats("my_task")
    assert stats["count"] >= 1


def test_stats_keys():
    with Profiler("op_x"):
        pass
    s = get_stats("op_x")
    assert "mean" in s
    assert "p50" in s
    assert "count" in s


def test_multiple_runs():
    for _ in range(5):
        with Profiler("loop_op"):
            pass
    s = get_stats("loop_op")
    assert s["count"] == 5


def test_report_string():
    with Profiler("rep_op"):
        pass
    r = report()
    assert isinstance(r, str)
    assert len(r) > 0


def test_context_manager_returns_self():
    p = Profiler("ctx_test")
    with p as result:
        pass
    assert result is p


def test_unknown_op_stats():
    s = get_stats("does_not_exist")
    assert s["count"] == 0
