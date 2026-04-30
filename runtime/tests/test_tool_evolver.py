"""Tests for the proactive tool-evolution daemon."""

from __future__ import annotations

from pathlib import Path

import pytest

from agency.daemons.tool_evolver import (
    BenchResult,
    ToolReport,
    bench_tool,
    discover_tool_files,
    evolve_all,
    tools_dir,
)


@pytest.fixture
def tools_path(tmp_path, monkeypatch):
    d = tmp_path / "tools"
    d.mkdir()
    monkeypatch.setenv("AGENCY_TOOLS_DIR", str(d))
    return d


# ----- discovery ----------------------------------------------------


def test_discover_finds_only_py_files(tools_path):
    (tools_path / "a.py").write_text("def run(input): return 1\nBENCH=[]")
    (tools_path / "b.py").write_text("def run(input): return 2\nBENCH=[]")
    (tools_path / "ignore.txt").write_text("nope")
    (tools_path / "__init__.py").write_text("# skip")
    (tools_path / ".hidden.py").write_text("# skip")
    files = discover_tool_files()
    names = sorted(f.name for f in files)
    assert names == ["a.py", "b.py"]


def test_discover_returns_empty_when_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_TOOLS_DIR", str(tmp_path / "nonexistent"))
    assert discover_tool_files() == []


def test_tools_dir_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_TOOLS_DIR", str(tmp_path / "custom"))
    assert tools_dir() == tmp_path / "custom"


# ----- bench_tool ---------------------------------------------------


def test_bench_skips_module_without_run(tools_path):
    (tools_path / "no_run.py").write_text("BENCH = []")
    files = discover_tool_files()
    r = bench_tool(files[0])
    assert "no run" in (r.skipped_reason or "").lower()


def test_bench_skips_module_without_bench(tools_path):
    (tools_path / "no_bench.py").write_text(
        "def run(input): return 'ok'"
    )
    files = discover_tool_files()
    r = bench_tool(files[0])
    assert "bench" in (r.skipped_reason or "").lower()


def test_bench_runs_each_case_repeats_times(tools_path):
    (tools_path / "ok.py").write_text(
        "def run(input):\n"
        "    return 'hello ' + str(input.get('name', 'world'))\n"
        "BENCH = [\n"
        "    {'name': 'a', 'input': {'name': 'amjad'}, 'expect_contains': 'amjad'},\n"
        "    {'name': 'b', 'input': {}, 'expect_contains': 'world'},\n"
        "]\n"
    )
    files = discover_tool_files()
    r = bench_tool(files[0], repeats=3)
    assert r.skipped_reason is None
    # 2 cases × 3 repeats = 6 runs
    assert len(r.runs) == 6
    assert all(run.ok for run in r.runs)


def test_bench_marks_failure_when_expect_substring_missing(tools_path):
    (tools_path / "wrong.py").write_text(
        "def run(input): return 'unrelated'\n"
        "BENCH = [{'input': {}, 'expect_contains': 'expected'}]\n"
    )
    files = discover_tool_files()
    r = bench_tool(files[0])
    assert any(not run.ok for run in r.runs)


def test_bench_records_exception_as_failed_run(tools_path):
    (tools_path / "boom.py").write_text(
        "def run(input): raise RuntimeError('boom')\n"
        "BENCH = [{'input': {}}]\n"
    )
    files = discover_tool_files()
    r = bench_tool(files[0])
    assert all(not run.ok for run in r.runs)
    assert "RuntimeError" in (r.runs[0].error or "")


def test_bench_handles_import_error(tools_path):
    (tools_path / "broken.py").write_text("import nonexistent_module_xyz")
    files = discover_tool_files()
    r = bench_tool(files[0])
    assert "import failed" in (r.skipped_reason or "").lower()


# ----- ToolReport properties ----------------------------------------


def test_median_elapsed_with_odd_count():
    r = ToolReport(path=Path("/tmp/x.py"))
    r.runs = [
        BenchResult("a", 0.1, True), BenchResult("a", 0.2, True),
        BenchResult("a", 0.3, True),
    ]
    assert r.median_elapsed_s == 0.2


def test_median_elapsed_with_even_count():
    r = ToolReport(path=Path("/tmp/x.py"))
    r.runs = [
        BenchResult("a", 0.1, True), BenchResult("a", 0.3, True),
    ]
    assert r.median_elapsed_s == 0.2


def test_median_excludes_failed_runs():
    r = ToolReport(path=Path("/tmp/x.py"))
    r.runs = [
        BenchResult("a", 0.1, True),
        BenchResult("a", 99.0, False),  # not counted
        BenchResult("a", 0.3, True),
    ]
    assert r.median_elapsed_s == 0.2


def test_is_slow_threshold(monkeypatch):
    monkeypatch.setenv("AGENCY_EVOLVE_SLOW_S", "0.05")
    # Reload to pick up the new threshold
    import importlib
    import agency.daemons.tool_evolver as te
    importlib.reload(te)
    try:
        r = te.ToolReport(path=Path("/tmp/x.py"))
        r.runs = [te.BenchResult("a", 0.1, True)]  # 100ms > 50ms threshold
        assert r.is_slow
        r.runs = [te.BenchResult("a", 0.01, True)]  # 10ms < 50ms threshold
        assert not r.is_slow
    finally:
        importlib.reload(te)


# ----- evolve_all integration --------------------------------------


def test_evolve_all_yields_one_report_per_file(tools_path):
    (tools_path / "a.py").write_text(
        "def run(input): return 'ok'\nBENCH=[{'input':{},'expect_contains':'ok'}]"
    )
    (tools_path / "b.py").write_text(
        "def run(input): return 'ok'\nBENCH=[{'input':{},'expect_contains':'ok'}]"
    )
    reports = list(evolve_all(llm=None))
    assert len(reports) == 2


def test_evolve_all_with_no_llm_does_not_rewrite(tools_path):
    """Force a slow tool: median > threshold. Without an LLM the
    rewrite path is skipped entirely (rewrite_attempted stays False)."""
    (tools_path / "slow.py").write_text(
        "import time\n"
        "def run(input):\n"
        "    time.sleep(1.0)\n"
        "    return 'done'\n"
        "BENCH = [{'input': {}, 'expect_contains': 'done'}]\n"
    )
    # Run with low threshold so this counts as slow.
    import os as _os
    _os.environ["AGENCY_EVOLVE_SLOW_S"] = "0.05"
    import importlib
    import agency.daemons.tool_evolver as te
    importlib.reload(te)
    try:
        reports = list(te.evolve_all(llm=None))
        assert len(reports) == 1
        assert reports[0].is_slow  # confirmed slow
        assert not reports[0].rewrite_attempted  # no LLM, no rewrite
    finally:
        _os.environ.pop("AGENCY_EVOLVE_SLOW_S", None)
        importlib.reload(te)
