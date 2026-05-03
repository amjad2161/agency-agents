"""Tests for the user-profile module + executor + LLM integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from agency.llm import AnthropicLLM
from agency.profile import (
    PROFILE_TEMPLATE,
    ensure_default_profile,
    load_profile_text,
    profile_path,
)


# ----- module unit tests --------------------------------------------------


def test_profile_path_honors_env_override(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AGENCY_PROFILE", str(tmp_path / "custom.md"))
    assert profile_path() == tmp_path / "custom.md"


def test_load_profile_returns_none_when_missing(tmp_path: Path):
    assert load_profile_text(tmp_path / "absent.md") is None


def test_load_profile_returns_none_when_empty(tmp_path: Path):
    p = tmp_path / "p.md"
    p.write_text("\n   \n")
    assert load_profile_text(p) is None


def test_load_profile_returns_text_when_present(tmp_path: Path):
    p = tmp_path / "p.md"
    p.write_text("Name: Tony\nRole: Engineer\n")
    text = load_profile_text(p)
    assert text == "Name: Tony\nRole: Engineer"


def test_load_profile_truncates_oversized_file(tmp_path: Path):
    from agency.profile import MAX_PROFILE_BYTES
    p = tmp_path / "big.md"
    p.write_text("x" * (MAX_PROFILE_BYTES * 2))
    text = load_profile_text(p)
    assert text is not None
    assert len(text.encode("utf-8")) <= MAX_PROFILE_BYTES + 64  # marker fudge
    assert "[profile truncated to fit]" in text


def test_ensure_default_profile_creates_starter_when_absent(tmp_path: Path):
    p = tmp_path / "fresh.md"
    ensure_default_profile(p)
    assert p.exists()
    assert "About me" in p.read_text()


def test_ensure_default_profile_rejects_non_file_path(tmp_path: Path):
    """If the configured path exists but isn't a regular file (e.g. a dir),
    fail loudly rather than silently skip creation."""
    d = tmp_path / "is-a-directory"
    d.mkdir()
    with pytest.raises(ValueError, match="not a regular file"):
        ensure_default_profile(d)


def test_load_profile_reads_only_up_to_cap(tmp_path: Path, monkeypatch):
    """Sanity-check that we don't slurp a 100 MB file into memory."""
    from agency.profile import MAX_PROFILE_BYTES
    p = tmp_path / "big.md"
    p.write_text("x" * (MAX_PROFILE_BYTES * 4))
    # Patch open() to trip if more than MAX+1 is requested in one read.
    real_open = Path.open

    captured = []

    def _spy_open(self, mode="r", *args, **kwargs):  # type: ignore[no-redef]
        f = real_open(self, mode, *args, **kwargs)
        if "b" in mode:
            real_read = f.read
            def _spy_read(n=-1):
                captured.append(n)
                return real_read(n)
            f.read = _spy_read  # type: ignore[method-assign]
        return f

    monkeypatch.setattr(Path, "open", _spy_open)
    text = load_profile_text(p)
    assert text is not None
    assert "[profile truncated to fit]" in text
    # The first binary read should have asked for at most MAX+1 bytes.
    assert any(0 < n <= MAX_PROFILE_BYTES + 1 for n in captured), captured


def test_ensure_default_profile_doesnt_overwrite(tmp_path: Path):
    p = tmp_path / "existing.md"
    p.write_text("user content")
    ensure_default_profile(p)
    assert p.read_text() == "user content"


# ----- LLM cached_system integration --------------------------------------


def test_cached_system_without_profile_is_unchanged():
    blocks = AnthropicLLM.cached_system("hello")
    assert len(blocks) == 1
    assert blocks[0]["text"] == "hello"
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}


def test_cached_system_prepends_profile_with_breakpoint_on_persona():
    blocks = AnthropicLLM.cached_system("persona body", profile="user info")
    assert len(blocks) == 2
    assert "user info" in blocks[0]["text"]
    assert "cache_control" not in blocks[0]
    assert blocks[1]["text"] == "persona body"
    assert blocks[1]["cache_control"] == {"type": "ephemeral"}


# ----- Executor integration -----------------------------------------------


def test_executor_includes_profile_in_system_prompt(tmp_path: Path, monkeypatch):
    """When profile is set, the system prompt sent to the API has 2 blocks."""
    # Avoid loading the user's real profile during tests.
    monkeypatch.setenv("AGENCY_PROFILE", str(tmp_path / "absent.md"))

    from tests.test_executor import (
        _ScriptedLLM, _Resp, _TextBlock, _registry_with_one_skill,
    )
    from agency.executor import Executor

    reg, skill = _registry_with_one_skill()
    llm = _ScriptedLLM([
        _Resp(stop_reason="end_turn", content=[_TextBlock("ok")]),
    ])
    executor = Executor(reg, llm, workdir=tmp_path, profile="I prefer Python.")
    executor.run(skill, "hi")

    system = llm.calls[0]["system"]
    assert isinstance(system, list)
    assert len(system) == 2
    assert "I prefer Python" in system[0]["text"]
    assert system[1]["cache_control"] == {"type": "ephemeral"}


def test_executor_omits_profile_block_when_none(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENCY_PROFILE", str(tmp_path / "absent.md"))

    from tests.test_executor import (
        _ScriptedLLM, _Resp, _TextBlock, _registry_with_one_skill,
    )
    from agency.executor import Executor

    reg, skill = _registry_with_one_skill()
    llm = _ScriptedLLM([
        _Resp(stop_reason="end_turn", content=[_TextBlock("ok")]),
    ])
    # Explicit None disables the profile entirely.
    executor = Executor(reg, llm, workdir=tmp_path, profile=None)
    executor.run(skill, "hi")

    system = llm.calls[0]["system"]
    assert len(system) == 1


def test_executor_rejects_non_string_profile(tmp_path: Path, monkeypatch):
    """Constructor should TypeError if profile is neither str/None/sentinel."""
    monkeypatch.setenv("AGENCY_PROFILE", str(tmp_path / "absent.md"))
    from tests.test_executor import _registry_with_one_skill
    from agency.executor import Executor

    reg, _ = _registry_with_one_skill()
    with pytest.raises(TypeError, match="profile must be a str"):
        Executor(reg, llm=type("L", (), {})(), workdir=tmp_path,
                 profile=123)  # type: ignore[arg-type]


def test_executor_lazy_profile_load_doesnt_fire_at_construction(
    tmp_path: Path, monkeypatch,
):
    """Construction should NOT touch ~/.agency/profile.md — only run() should."""
    from tests.test_executor import _registry_with_one_skill
    from agency.executor import Executor
    from agency import profile as profile_mod

    monkeypatch.setenv("AGENCY_PROFILE", str(tmp_path / "absent.md"))

    calls = {"n": 0}
    real = profile_mod.load_profile_text

    def _spy(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr("agency.executor.load_profile_text", _spy)

    reg, _ = _registry_with_one_skill()
    Executor(reg, llm=type("L", (), {})(), workdir=tmp_path)
    assert calls["n"] == 0, "profile should not be loaded at __init__"


def test_executor_inherits_profile_in_subagent(tmp_path: Path, monkeypatch):
    """delegate_to_skill should hand the same profile to the sub-executor."""
    monkeypatch.setenv("AGENCY_PROFILE", str(tmp_path / "absent.md"))

    from tests.test_executor import (
        _ScriptedLLM, _Resp, _TextBlock, _ToolUseBlock, _registry_with_one_skill,
    )
    from agency.executor import Executor
    from agency.skills import SkillRegistry, discover_repo_root

    full = SkillRegistry.load(discover_repo_root())
    a, b = full.all()[0], full.all()[1]
    reg = SkillRegistry([a, b])

    llm = _ScriptedLLM([
        _Resp(
            stop_reason="tool_use",
            content=[_ToolUseBlock(
                id="t1", name="delegate_to_skill",
                input={"slug": b.slug, "request": "do thing"},
            )],
        ),
        _Resp(stop_reason="end_turn", content=[_TextBlock("B done")]),
        _Resp(stop_reason="end_turn", content=[_TextBlock("A wraps up")]),
    ])
    executor = Executor(reg, llm, workdir=tmp_path, profile="profile-xyz")
    executor.run(a, "delegate")

    # Three API calls: A turn 1, sub B, A turn 2.
    # Every one of them must include the profile in the system prompt.
    for call in llm.calls:
        system = call["system"]
        assert isinstance(system, list)
        assert len(system) == 2
        assert "profile-xyz" in system[0]["text"]


# ----- CLI tests -----------------------------------------------------------


def test_cli_profile_show_no_file(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AGENCY_PROFILE", str(tmp_path / "absent.md"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from click.testing import CliRunner
    from agency.cli import main
    result = CliRunner().invoke(main, ["profile", "show"])
    assert result.exit_code == 0
    assert "No profile file at" in result.output


def test_cli_profile_show_with_file(monkeypatch, tmp_path: Path):
    p = tmp_path / "p.md"
    p.write_text("Hello, I am Tony.")
    monkeypatch.setenv("AGENCY_PROFILE", str(p))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from click.testing import CliRunner
    from agency.cli import main
    result = CliRunner().invoke(main, ["profile", "show"])
    assert result.exit_code == 0
    assert "Hello, I am Tony." in result.output


def test_cli_profile_path(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AGENCY_PROFILE", str(tmp_path / "x.md"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from click.testing import CliRunner
    from agency.cli import main
    result = CliRunner().invoke(main, ["profile", "path"])
    assert result.exit_code == 0
    assert str(tmp_path / "x.md") in result.output


def test_cli_profile_clear(monkeypatch, tmp_path: Path):
    p = tmp_path / "p.md"
    p.write_text("...")
    monkeypatch.setenv("AGENCY_PROFILE", str(p))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from click.testing import CliRunner
    from agency.cli import main
    result = CliRunner().invoke(main, ["profile", "clear"])
    assert result.exit_code == 0
    assert not p.exists()


def test_cli_profile_default_invokes_show(monkeypatch, tmp_path: Path):
    """`agency profile` with no subcommand should be equivalent to `show`."""
    monkeypatch.setenv("AGENCY_PROFILE", str(tmp_path / "absent.md"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from click.testing import CliRunner
    from agency.cli import main
    result = CliRunner().invoke(main, ["profile"])
    assert result.exit_code == 0
    assert "No profile file at" in result.output
