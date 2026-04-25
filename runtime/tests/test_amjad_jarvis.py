"""Tests for the Amjad Jarvis meta-orchestrator.

The original autonomous-agent-generated test file at the top-level `tests/`
had literal `\\n` escape sequences instead of newlines and was completely
unparseable. This is a rewritten, working version that lives where the rest
of the suite does (under `runtime/tests/`) so pytest discovers it.

Tests exercise:
- Profile loading / saving / round-trip
- System-prompt prefix generation
- Trust-mode and capability-toggle setters (env-var side effects)
- The global jarvis() singleton
- The context-aware executor factory wires correctly

Anything that requires a live Anthropic call is mocked.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


_AGENCY_ENV_KEYS = (
    "AGENCY_TRUST_MODE", "AGENCY_ALLOW_SHELL",
    "AGENCY_ENABLE_WEB_SEARCH", "AGENCY_ENABLE_CODE_EXECUTION",
    "AGENCY_ENABLE_COMPUTER_USE", "AGENCY_NO_NETWORK",
)


@pytest.fixture(autouse=True)
def _isolate_agency_env():
    """Snapshot + restore AGENCY_* env vars around every test in this file.

    The orchestrator's setters mutate `os.environ` directly (e.g.
    `os.environ["AGENCY_TRUST_MODE"] = "yolo"`). monkeypatch only tracks
    changes made *through* its own API, so those direct writes leaked
    into later test files — turning trust mode on globally and breaking
    test_tools.py's safe_path / shell-allowlist / web_fetch assertions.

    This fixture snapshots the keys we care about, deletes them so each
    orchestrator test gets a clean baseline, then restores the original
    values at teardown.
    """
    import os
    saved = {k: os.environ.get(k) for k in _AGENCY_ENV_KEYS}
    for k in _AGENCY_ENV_KEYS:
        os.environ.pop(k, None)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


from agency.amjad_jarvis_meta_orchestrator import (
    AmjadJarvisMetaOrchestrator,
    AmjadProfile,
    MetaOrchestratorConfig,
    init_jarvis,
    jarvis,
)
from agency.llm import AnthropicLLM
from agency.skills import Skill, SkillRegistry


# ----- AmjadProfile -------------------------------------------------------


def test_default_profile_creation():
    profile = AmjadProfile()
    assert profile.name == "Amjad"
    assert profile.role == "Founder & Tech Lead"
    assert len(profile.personality_traits) > 0
    assert len(profile.technical_stack) > 0


def test_profile_system_prompt_includes_overrides():
    profile = AmjadProfile(name="TestAmjad", personality_traits=["Direct", "Pragmatic"])
    prompt = profile.to_system_prompt_prefix()
    assert "TestAmjad" in prompt
    assert "Direct" in prompt
    assert "Pragmatic" in prompt


def test_profile_round_trip(tmp_path: Path):
    p = tmp_path / "profile.json"
    a = AmjadProfile(name="Amjad", role="Test Role")
    a.preferences["trust_mode"] = "yolo"
    a.save(p)
    b = AmjadProfile.load_or_create(p)
    assert b.name == "Amjad"
    assert b.role == "Test Role"
    assert b.preferences["trust_mode"] == "yolo"


def test_profile_constraints_present():
    profile = AmjadProfile()
    assert profile.constraints["no_real_security_breaches"] is True
    assert profile.constraints["respect_external_apis"] is True
    assert profile.constraints["no_illegal_activities"] is True


# NOTE: AmjadProfile carries `constraints` as data but doesn't currently
# render them into the system-prompt prefix. If/when that lands, add a
# regression test here. The original autogen test asserted the rendered
# behavior and was already broken on the day it was written.


# ----- Orchestrator setters / env wiring ---------------------------------


@pytest.fixture
def orchestrator():
    """Mock-backed orchestrator that doesn't need an LLM."""
    registry = MagicMock(spec=SkillRegistry)
    registry.all.return_value = []
    registry.search.return_value = []
    config = MetaOrchestratorConfig(amjad_profile=AmjadProfile(name="TestAmjad"))
    return AmjadJarvisMetaOrchestrator(
        config=config,
        registry=registry,
        llm=MagicMock(spec=AnthropicLLM),
    )


def test_orchestrator_initialization(orchestrator):
    assert orchestrator.amjad.name == "TestAmjad"


def test_set_trust_mode_updates_env(monkeypatch, orchestrator):
    monkeypatch.delenv("AGENCY_TRUST_MODE", raising=False)
    orchestrator.set_trust_mode("yolo")
    assert orchestrator.amjad.preferences["trust_mode"] == "yolo"
    assert os.environ.get("AGENCY_TRUST_MODE") == "yolo"


def test_enable_shell_toggles_env(monkeypatch, orchestrator):
    monkeypatch.delenv("AGENCY_ALLOW_SHELL", raising=False)
    orchestrator.enable_shell(True)
    assert orchestrator.amjad.preferences["shell_access"] is True
    assert os.environ.get("AGENCY_ALLOW_SHELL") == "1"
    orchestrator.enable_shell(False)
    assert orchestrator.amjad.preferences["shell_access"] is False
    assert "AGENCY_ALLOW_SHELL" not in os.environ


def test_enable_code_execution_toggles_env(monkeypatch, orchestrator):
    monkeypatch.delenv("AGENCY_ENABLE_CODE_EXECUTION", raising=False)
    orchestrator.enable_code_execution(True)
    assert orchestrator.amjad.preferences["code_execution"] is True
    assert os.environ.get("AGENCY_ENABLE_CODE_EXECUTION") == "1"


def test_enable_computer_use_toggles_env(monkeypatch, orchestrator):
    monkeypatch.delenv("AGENCY_ENABLE_COMPUTER_USE", raising=False)
    orchestrator.enable_computer_use(True)
    assert orchestrator.amjad.preferences["computer_use"] is True
    assert os.environ.get("AGENCY_ENABLE_COMPUTER_USE") == "1"


def test_set_amjad_preference(orchestrator):
    orchestrator.set_amjad_preference("trust_mode", "off")
    assert orchestrator.amjad.preferences["trust_mode"] == "off"


# ----- Context injection --------------------------------------------------


def test_context_aware_executor_constructed(orchestrator):
    test_skill = Skill(
        slug="test",
        name="Test Skill",
        description="Test",
        category="testing",
        color="#000",
        emoji="🧪",
        vibe="test",
        body="Original prompt",
        path=Path("test.md"),
    )
    executor = orchestrator._create_context_aware_executor(test_skill)
    assert executor is not None


# ----- Global singleton ---------------------------------------------------


def test_jarvis_returns_singleton():
    j1 = jarvis()
    j2 = jarvis()
    assert j1 is j2


def test_init_jarvis_replaces_singleton():
    config = MetaOrchestratorConfig(amjad_profile=AmjadProfile(name="InitTest"))
    j = init_jarvis(config)
    assert j.amjad.name == "InitTest"


# ----- End-to-end orchestrator flows --------------------------------------


def test_multiple_preference_changes_persist(monkeypatch):
    monkeypatch.delenv("AGENCY_TRUST_MODE", raising=False)
    monkeypatch.delenv("AGENCY_ALLOW_SHELL", raising=False)
    config = MetaOrchestratorConfig(amjad_profile=AmjadProfile())
    o = AmjadJarvisMetaOrchestrator(config=config)
    o.set_trust_mode("off")
    o.enable_shell(False)
    assert o.amjad.preferences["trust_mode"] == "off"
    assert o.amjad.preferences["shell_access"] is False
    o.set_trust_mode("yolo")
    o.enable_shell(True)
    assert o.amjad.preferences["trust_mode"] == "yolo"
    assert o.amjad.preferences["shell_access"] is True


def test_profile_persistence_through_orchestrator():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "amjad-profile.json"
        config = MetaOrchestratorConfig(amjad_profile=AmjadProfile.load_or_create(p))
        o = AmjadJarvisMetaOrchestrator(config=config)
        o.set_trust_mode("yolo")
        o.enable_shell(True)
        o.amjad.save(p)
        loaded = AmjadProfile.load_or_create(p)
        assert loaded.preferences["trust_mode"] == "yolo"
        assert loaded.preferences["shell_access"] is True
