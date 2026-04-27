"""Tests for the cross-session lessons journal.

The lessons file is the durable-memory companion to the profile —
loaded on every executor instantiation, injected as a system block
alongside the profile, persisted across sessions.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import click.testing

from agency.cli import main
from agency.lessons import (
    ensure_default_lessons,
    lessons_path,
    load_lessons_text,
    MAX_LESSONS_BYTES,
)


@pytest.fixture(autouse=True)
def _isolate_lessons_path(tmp_path: Path, monkeypatch):
    """Point AGENCY_LESSONS at a tmp file so a developer's real journal
    doesn't leak into tests and tests don't write to their real journal."""
    monkeypatch.setenv("AGENCY_LESSONS", str(tmp_path / "lessons.md"))


# ----- path resolution ---------------------------------------------------


def test_path_honors_env_override(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENCY_LESSONS", str(tmp_path / "alt.md"))
    assert lessons_path() == tmp_path / "alt.md"


def test_path_falls_back_to_home_when_env_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("AGENCY_LESSONS", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert lessons_path() == tmp_path / ".agency" / "lessons.md"


# ----- load_lessons_text -------------------------------------------------


def test_load_returns_none_when_missing():
    assert load_lessons_text() is None


def test_load_returns_none_when_empty():
    lessons_path().write_text("", encoding="utf-8")
    assert load_lessons_text() is None


def test_load_returns_none_when_whitespace_only():
    lessons_path().write_text("   \n\n  ", encoding="utf-8")
    assert load_lessons_text() is None


def test_load_returns_text_when_present():
    lessons_path().write_text("WORKED: shipping the trust gate.\n", encoding="utf-8")
    text = load_lessons_text()
    assert text == "WORKED: shipping the trust gate."


def test_load_keeps_tail_when_oversized():
    """Recency wins — the loader keeps the last MAX_LESSONS_BYTES, not the
    first, and prepends a marker so the agent knows it's seeing a window."""
    p = lessons_path()
    # Write more than the cap; the prefix should be dropped.
    body = (
        ("# old, should be dropped\n" * 3000)
        + "MARKER_THAT_MUST_SURVIVE\n"
    )
    assert len(body.encode()) > MAX_LESSONS_BYTES
    p.write_text(body, encoding="utf-8")
    text = load_lessons_text()
    assert text is not None
    assert "MARKER_THAT_MUST_SURVIVE" in text
    assert "[lessons file truncated" in text
    # The marker should appear near the end, not the beginning.
    assert text.rfind("MARKER_THAT_MUST_SURVIVE") > len(text) // 2


def test_load_handles_unreadable_path(tmp_path: Path, monkeypatch):
    """A directory at the configured path doesn't raise; we return None."""
    p = tmp_path / "lessons-as-dir"
    p.mkdir()
    monkeypatch.setenv("AGENCY_LESSONS", str(p))
    assert load_lessons_text() is None


# ----- ensure_default_lessons -------------------------------------------


def test_ensure_creates_file_when_missing():
    p = lessons_path()
    assert not p.exists()
    out = ensure_default_lessons()
    assert out == p
    assert p.exists()
    assert "Lessons learned" in p.read_text(encoding="utf-8")


def test_ensure_is_idempotent_when_file_exists():
    p = lessons_path()
    p.write_text("custom content\n", encoding="utf-8")
    ensure_default_lessons()
    assert p.read_text(encoding="utf-8") == "custom content\n"  # untouched


def test_ensure_raises_when_path_is_directory(tmp_path: Path, monkeypatch):
    p = tmp_path / "lessons-as-dir"
    p.mkdir()
    monkeypatch.setenv("AGENCY_LESSONS", str(p))
    with pytest.raises(ValueError, match="not a regular file"):
        ensure_default_lessons()


# ----- CLI: agency lessons {show,path,add,clear,edit} ------------------


def test_cli_show_when_missing():
    runner = click.testing.CliRunner()
    r = runner.invoke(main, ["lessons", "show"])
    assert r.exit_code == 0
    assert "No lessons file" in r.output


def test_cli_show_when_present():
    lessons_path().write_text("WORKED: x\n", encoding="utf-8")
    runner = click.testing.CliRunner()
    r = runner.invoke(main, ["lessons", "show"])
    assert r.exit_code == 0
    assert "WORKED: x" in r.output


def test_cli_path():
    runner = click.testing.CliRunner()
    r = runner.invoke(main, ["lessons", "path"])
    assert r.exit_code == 0
    assert str(lessons_path()) in r.output


def test_cli_add_creates_file_and_appends():
    runner = click.testing.CliRunner()
    r = runner.invoke(main, ["lessons", "add", "ship the lessons feature"])
    assert r.exit_code == 0
    body = lessons_path().read_text(encoding="utf-8")
    assert "ship the lessons feature" in body
    # Should include a UTC timestamp header.
    assert "## " in body and "UTC" in body


def test_cli_add_rejects_empty_lesson():
    runner = click.testing.CliRunner()
    r = runner.invoke(main, ["lessons", "add", "   "])
    assert r.exit_code != 0


def test_cli_clear_removes_file():
    p = lessons_path()
    p.write_text("anything\n", encoding="utf-8")
    runner = click.testing.CliRunner()
    r = runner.invoke(main, ["lessons", "clear"])
    assert r.exit_code == 0
    assert not p.exists()


def test_cli_clear_when_already_missing():
    runner = click.testing.CliRunner()
    r = runner.invoke(main, ["lessons", "clear"])
    assert r.exit_code == 0
    assert "nothing to remove" in r.output


def test_bare_lessons_invokes_show():
    """Running `agency lessons` with no subcommand should invoke `show`."""
    runner = click.testing.CliRunner()
    r = runner.invoke(main, ["lessons"])
    assert r.exit_code == 0


# ----- integration: cached_system + Executor wiring --------------------


def test_cached_system_includes_lessons_block():
    from agency.llm import AnthropicLLM

    blocks = AnthropicLLM.cached_system(
        "persona body", profile="hi I'm Amjad", lessons="never use the word leverage",
    )
    # Order: profile, lessons, persona (with breakpoint).
    assert len(blocks) == 3
    assert "hi I'm Amjad" in blocks[0]["text"]
    assert "never use the word leverage" in blocks[1]["text"]
    assert blocks[2]["text"] == "persona body"
    assert blocks[2].get("cache_control", {}).get("type") == "ephemeral"
    # Profile and lessons blocks DO NOT carry their own breakpoints.
    assert "cache_control" not in blocks[0]
    assert "cache_control" not in blocks[1]


def test_cached_system_works_without_lessons():
    """Backwards-compat: cached_system with no lessons matches prior shape."""
    from agency.llm import AnthropicLLM

    blocks = AnthropicLLM.cached_system("persona body", profile="hi")
    assert len(blocks) == 2  # profile + persona
    assert "hi" in blocks[0]["text"]
    assert blocks[1]["text"] == "persona body"


def test_cached_system_works_without_anything():
    """Bare cached_system still returns a single persona block."""
    from agency.llm import AnthropicLLM

    blocks = AnthropicLLM.cached_system("persona body")
    assert len(blocks) == 1
    assert blocks[0]["text"] == "persona body"
