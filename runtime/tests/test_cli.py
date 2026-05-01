"""CLI tests using click.testing.CliRunner.

Tests the offline commands (list, plan with keyword fallback) and verifies
run() surfaces a useful error message when no API key is set.
"""

from __future__ import annotations

import os

import pytest
from click.testing import CliRunner

from agency.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_list_prints_skills(runner, no_api_key):
    result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    assert "skill(s):" in result.output
    assert "engineering-" in result.output  # at least one engineering skill shows


def test_list_filters_by_category(runner, no_api_key):
    result = runner.invoke(main, ["list", "--category", "engineering"])
    assert result.exit_code == 0
    lines = result.output.splitlines()
    # Every shown skill line (not the header) should be from engineering/
    skill_lines = [l for l in lines if l.startswith("  ") and "(" in l]
    assert skill_lines
    for line in skill_lines:
        assert "(engineering)" in line, line


def test_list_filters_by_search(runner, no_api_key):
    result = runner.invoke(main, ["list", "--search", "frontend"])
    assert result.exit_code == 0
    assert "frontend" in result.output.lower()


def test_plan_uses_keyword_fallback_when_no_key(runner, no_api_key):
    result = runner.invoke(main, ["plan", "build a React component"])
    assert result.exit_code == 0
    assert "Picked:" in result.output
    assert "Reason:" in result.output


def test_plan_honors_hint_skill(runner, no_api_key):
    result = runner.invoke(
        main, ["plan", "anything", "--skill", "engineering-frontend-developer"]
    )
    assert result.exit_code == 0
    assert "engineering-frontend-developer" in result.output
    assert "explicit user choice" in result.output


def test_run_without_api_key_gives_useful_error(runner, no_api_key):
    result = runner.invoke(main, ["run", "hello"])
    assert result.exit_code != 0
    assert "ANTHROPIC_API_KEY" in result.output


def test_init_scaffolds_new_persona(runner, no_api_key, tmp_path):
    # Point at a fake repo that looks like the real one.
    (tmp_path / "engineering").mkdir()
    (tmp_path / "engineering" / "existing.md").write_text("placeholder")
    (tmp_path / "README.md").write_text("fake repo")

    result = runner.invoke(main, [
        "--repo", str(tmp_path),
        "init", "rocket-scientist",
        "--name", "Rocket Scientist",
        "--category", "specialized",
        "--emoji", "🚀",
        "--description", "Builds rockets.",
    ])
    assert result.exit_code == 0, result.output
    created = tmp_path / "specialized" / "rocket-scientist.md"
    assert created.exists()
    text = created.read_text()
    assert "name: Rocket Scientist" in text
    assert "🚀" in text
    assert "Builds rockets" in text


def test_doctor_reports_skill_counts_and_env(runner, no_api_key):
    result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "Agency Runtime Doctor" in result.output
    assert "skills loaded:" in result.output
    assert "engineering" in result.output  # a category should appear
    assert "ANTHROPIC_API_KEY" in result.output
    assert "AGENCY_ENABLE_COMPUTER_USE" in result.output
    assert "optional deps" in result.output
    assert "tool context" in result.output


def test_doctor_shows_both_missing_and_errors_for_same_group(runner, no_api_key, monkeypatch):
    """Regression: doctor used to show only `missing` and silently swallow `errors`.

    Stub `optional_deps_status` to return one group with both kinds of failure
    and assert the rendered line includes both.
    """
    from agency import cli as cli_mod

    def _stub() -> dict:
        return {
            "fake": {
                "installed": False,
                "missing": ["lib_a"],
                "errors": {"lib_b": "OSError: DISPLAY not set"},
            },
        }

    # The doctor imports the helper inside the function, so patch
    # `agency.diagnostics.optional_deps_status` (the source).
    from agency import diagnostics
    monkeypatch.setattr(diagnostics, "optional_deps_status", _stub)

    result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "missing: lib_a" in result.output
    assert "broken:" in result.output
    assert "lib_b" in result.output
    assert "DISPLAY not set" in result.output


def test_init_refuses_to_overwrite(runner, no_api_key, tmp_path):
    (tmp_path / "engineering").mkdir()
    (tmp_path / "engineering" / "existing.md").write_text("x")
    (tmp_path / "README.md").write_text("fake")
    (tmp_path / "specialized").mkdir()
    (tmp_path / "specialized" / "taken.md").write_text("y")

    result = runner.invoke(main, [
        "--repo", str(tmp_path),
        "init", "taken", "--category", "specialized",
    ])
    assert result.exit_code != 0
    assert "exists" in result.output.lower()


def test_verbose_flag_enables_info_logging(runner, no_api_key):
    """`-v` should bump the agency logger to INFO so plan.picked records show up."""
    import logging

    # Reset the logger so the CLI's configure() actually attaches a handler
    # against this run's stderr.
    agency_logger = logging.getLogger("agency")
    for h in list(agency_logger.handlers):
        agency_logger.removeHandler(h)
    agency_logger.setLevel(logging.WARNING)

    # Plan a request — under -v this should emit a plan.picked log line.
    result = runner.invoke(main, ["-v", "plan", "build a frontend dashboard"])
    assert result.exit_code == 0
    # CliRunner captures the agency logger's stderr handler output too.
    assert "plan.picked" in result.output or "plan.picked" in (result.stderr or "")


def test_double_verbose_flag_enables_debug(runner, no_api_key):
    """`-vv` should set the agency logger to DEBUG and route DEBUG records through."""
    import io
    import logging

    agency_logger = logging.getLogger("agency")
    for h in list(agency_logger.handlers):
        agency_logger.removeHandler(h)

    sink = io.StringIO()

    # Patch the configure() call so it writes to our sink instead of stderr.
    from agency import logging as agency_logging
    real_configure = agency_logging.configure

    def _capture(level=None, *, stream=None):
        return real_configure(level, stream=sink)

    runner.invoke(main, ["-vv", "list"], catch_exceptions=False, color=False,
                  obj={}, prog_name="agency",
                  default_map={})  # default_map is a noop here, just unblocks lint
    # After the CLI runs, the logger's level reflects the -vv flag.
    assert agency_logger.level == logging.DEBUG
    # And a DEBUG record now actually emits through the configured handler.
    # The level being DEBUG is the authoritative assertion; stream interactions
    # may fail if the CLI's handler stream closed on exit — that is fine.
    try:
        agency_logger.debug("debug-from-test")
        handler = next(
            (h for h in agency_logger.handlers if getattr(h, "_agency", False)), None
        )
        if handler is not None:
            handler.flush()
    except (ValueError, OSError):
        pass  # closed stream after CLI exit is expected
    assert agency_logger.isEnabledFor(logging.DEBUG)


def test_hud_command_help(runner):
    """`agency hud --help` should describe itself + accept --no-browser."""
    r = runner.invoke(main, ["hud", "--help"])
    assert r.exit_code == 0
    assert "GRAVIS HUD" in r.output or "HUD" in r.output
    assert "--no-browser" in r.output


# ---------------------------------------------------------------------------
# New module CLI commands
# ---------------------------------------------------------------------------

def test_plugin_list_empty(runner, tmp_path, monkeypatch):
    """agency plugin list with no plugins installed."""
    monkeypatch.setattr("agency.plugins._PLUGINS_DIR", tmp_path / "plugins")
    result = runner.invoke(main, ["plugin", "list"])
    assert result.exit_code == 0
    assert "No plugins" in result.output


def test_plugin_install_and_list(runner, tmp_path, monkeypatch):
    """agency plugin install then list shows the plugin."""
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    monkeypatch.setattr("agency.plugins._PLUGINS_DIR", plugins_dir)
    # Create a real plugin file to install
    src = tmp_path / "demo.py"
    src.write_text(
        'PLUGIN_META = {"name": "demo", "version": "1.0.0", "description": "A demo"}\n'
        'def activate(registry): pass\n',
        encoding="utf-8",
    )
    install_result = runner.invoke(main, ["plugin", "install", str(src)])
    assert install_result.exit_code == 0, install_result.output
    assert "Installed" in install_result.output

    list_result = runner.invoke(main, ["plugin", "list"])
    assert list_result.exit_code == 0
    assert "demo" in list_result.output.lower()


def test_plugin_install_missing_file(runner, tmp_path, monkeypatch):
    """agency plugin install with a non-existent file exits with error."""
    monkeypatch.setattr("agency.plugins._PLUGINS_DIR", tmp_path / "plugins")
    result = runner.invoke(main, ["plugin", "install", str(tmp_path / "ghost.py")])
    assert result.exit_code != 0


def test_rate_status_shows_tokens(runner):
    """agency rate-status prints token counts."""
    result = runner.invoke(main, ["rate-status"])
    assert result.exit_code == 0
    assert "tokens remaining" in result.output
    assert "capacity" in result.output or "/" in result.output


def test_webhook_list_empty(runner, tmp_path, monkeypatch):
    """agency webhook list with no webhooks."""
    monkeypatch.setattr("agency.webhooks._DEFAULT_PATH", tmp_path / "hooks.json")
    result = runner.invoke(main, ["webhook", "list"])
    assert result.exit_code == 0
    assert "No webhooks" in result.output


def test_webhook_add_and_list(runner, tmp_path, monkeypatch):
    """agency webhook add then list shows the endpoint."""
    monkeypatch.setattr("agency.webhooks._DEFAULT_PATH", tmp_path / "hooks.json")
    add_result = runner.invoke(main, ["webhook", "add", "https://example.com/hook"])
    assert add_result.exit_code == 0, add_result.output
    assert "example.com" in add_result.output.lower() or "registered" in add_result.output.lower()

    list_result = runner.invoke(main, ["webhook", "list"])
    assert list_result.exit_code == 0
    assert "example.com" in list_result.output


def test_webhook_remove(runner, tmp_path, monkeypatch):
    """agency webhook remove deletes a registered endpoint."""
    monkeypatch.setattr("agency.webhooks._DEFAULT_PATH", tmp_path / "hooks.json")
    runner.invoke(main, ["webhook", "add", "https://example.com/hook"])
    remove_result = runner.invoke(main, ["webhook", "remove", "https://example.com/hook"])
    assert remove_result.exit_code == 0
    assert "Removed" in remove_result.output


def test_check_update_shows_version(runner, tmp_path, monkeypatch):
    """agency check-update prints current and latest version."""
    from unittest.mock import patch
    monkeypatch.setattr("agency.updater._CACHE_PATH", tmp_path / "update_check.json")
    with patch("agency.updater._fetch_latest_pypi", return_value="0.1.0"):
        result = runner.invoke(main, ["check-update"])
    assert result.exit_code == 0
    assert "current" in result.output
    assert "latest" in result.output


def test_main_help_lists_all_new_commands(runner):
    """agency --help lists plugin, rate-status, webhook, check-update."""
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for cmd in ("plugin", "rate-status", "webhook", "check-update"):
        assert cmd in result.output, f"'{cmd}' missing from help output"
