"""Logging configuration + integration tests."""

from __future__ import annotations

import io
import logging

from agency.logging import configure, get_logger, timed, LOGGER_NAME


def _reset_logger():
    """Pytest may run tests in arbitrary order; clear handlers before each."""
    logger = logging.getLogger(LOGGER_NAME)
    for h in list(logger.handlers):
        logger.removeHandler(h)
    logger.setLevel(logging.WARNING)
    logger.propagate = False


def test_configure_attaches_one_handler_idempotently():
    _reset_logger()
    sink = io.StringIO()
    configure("INFO", stream=sink)
    configure("INFO", stream=sink)
    configure("DEBUG", stream=sink)
    logger = get_logger()
    handlers = [h for h in logger.handlers if getattr(h, "_agency", False)]
    assert len(handlers) == 1


def test_configure_respects_level():
    _reset_logger()
    sink = io.StringIO()
    configure("WARNING", stream=sink)
    log = get_logger()
    log.info("should not appear")
    log.warning("should appear")
    output = sink.getvalue()
    assert "should not appear" not in output
    assert "should appear" in output


def test_configure_uses_env_var_default(monkeypatch):
    _reset_logger()
    monkeypatch.setenv("AGENCY_LOG", "info")
    sink = io.StringIO()
    configure(stream=sink)
    log = get_logger()
    log.info("info from env")
    assert "info from env" in sink.getvalue()


def test_timed_context_emits_elapsed_ms():
    _reset_logger()
    sink = io.StringIO()
    configure("INFO", stream=sink)
    with timed("widget.op", id=7, kind="grok"):
        pass
    out = sink.getvalue()
    assert "widget.op elapsed_ms=" in out
    assert "id=7" in out
    assert "kind=grok" in out


def test_planner_logs_pick(monkeypatch):
    """Planner should log which slug it picked when it runs."""
    from agency.planner import Planner
    from agency.skills import SkillRegistry, discover_repo_root

    _reset_logger()
    sink = io.StringIO()
    configure("INFO", stream=sink)

    reg = SkillRegistry.load(discover_repo_root())
    planner = Planner(reg, llm=None)
    planner.plan("frontend developer")

    out = sink.getvalue()
    assert "plan.picked" in out
    assert "slug=" in out


def test_executor_logs_tool_run(tmp_path):
    """A tool invocation should produce a tool.run record with elapsed_ms."""
    from agency.executor import Executor
    from agency.skills import SkillRegistry, discover_repo_root
    from agency.tools import builtin_tools

    _reset_logger()
    sink = io.StringIO()
    configure("INFO", stream=sink)

    reg = SkillRegistry.load(discover_repo_root())
    skill = reg.all()[0]
    # Invoke a builtin tool directly via the executor's _run_tool path.
    executor = Executor(reg, llm=type("LLM", (), {})(), workdir=tmp_path,
                        tools=builtin_tools())
    (tmp_path / "x.txt").write_text("hi")
    result = executor._run_tool("read_file", {"path": "x.txt"})
    assert not result.is_error
    out = sink.getvalue()
    assert "tool.run" in out
    assert "name=read_file" in out
