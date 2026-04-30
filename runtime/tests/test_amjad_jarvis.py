"""Tests for the Amjad Jarvis Meta-Orchestrator.

Covers:
- AmjadProfile creation, persistence, and system-prompt generation
- Trust mode and permission helpers
- AmjadJarvisMetaOrchestrator context injection and routing
- Multi-agent workflow execution (parallel and sequential)
- CLI command registration under ``agency amjad``
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from agency.amjad_jarvis_meta_orchestrator import (
    AmjadJarvisMetaOrchestrator,
    AmjadProfile,
    MetaOrchestratorConfig,
    init_jarvis,
    jarvis,
)
from agency.cli import main
from agency.executor import ExecutionResult, Usage
from agency.memory import MemoryStore
from agency.skills import Skill, SkillRegistry


# ---------------------------------------------------------------------------
# Env isolation
# ---------------------------------------------------------------------------
# The orchestrator's permission helpers (`set_trust_mode`, `enable_shell`,
# `enable_web_search`, ...) write directly to `os.environ`. `monkeypatch`
# only tracks values it set itself, so without this fixture those writes
# leak into other test modules — `test_tools.py::test_web_fetch_*` would
# then see `AGENCY_TRUST_MODE=...` from a previous run and refuse the
# wrong way. Snapshot every key the orchestrator might touch and restore
# at teardown.

_AGENCY_ENV_KEYS = (
    "AGENCY_TRUST_MODE",
    "AGENCY_ALLOW_SHELL",
    "AGENCY_ENABLE_WEB_SEARCH",
    "AGENCY_ENABLE_CODE_EXECUTION",
    "AGENCY_ENABLE_COMPUTER_USE",
)


@pytest.fixture(autouse=True)
def _isolate_agency_env():
    snapshot = {k: os.environ.get(k) for k in _AGENCY_ENV_KEYS}
    for k in _AGENCY_ENV_KEYS:
        os.environ.pop(k, None)
    try:
        yield
    finally:
        for k, v in snapshot.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_skill(slug: str = "test-agent", category: str = "engineering") -> Skill:
    return Skill(
        slug=slug,
        name=slug.replace("-", " ").title(),
        description="A test agent.",
        category=category,
        color="blue",
        emoji="🤖",
        vibe="test vibe",
        body="You are a test agent.",
        path=Path(f"/fake/{slug}.md"),
        extra={},
    )


def _fake_registry(*slugs: str) -> SkillRegistry:
    return SkillRegistry([_fake_skill(s) for s in (slugs or ("test-agent",))])


def _fake_result(text: str = "ok") -> ExecutionResult:
    return ExecutionResult(text=text, turns=1, events=[], usage=Usage())


@dataclass
class _TextBlock:
    text: str
    type: str = "text"


@dataclass
class _FakeUsage:
    input_tokens: int = 5
    output_tokens: int = 5
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class _Resp:
    content: list
    stop_reason: str
    usage: Any = None


class _ScriptedLLM:
    def __init__(self, responses: list[_Resp]):
        self._responses = list(responses)
        self.calls: list[dict] = []

        @dataclass
        class _Cfg:
            model: str = "fake"
            planner_model: str = "fake-haiku"
            max_tokens: int = 1024

        self.config = _Cfg()

    @staticmethod
    def cached_system(text: str):
        return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]

    def messages_create(self, **kwargs):
        import copy
        self.calls.append({k: copy.deepcopy(v) for k, v in kwargs.items()})
        if not self._responses:
            raise AssertionError("_ScriptedLLM ran out of responses")
        return self._responses.pop(0)


# ---------------------------------------------------------------------------
# AmjadProfile tests
# ---------------------------------------------------------------------------


class TestAmjadProfile:
    def test_default_profile_has_expected_fields(self):
        p = AmjadProfile()
        assert p.name == "Amjad"
        assert p.role == "Founder & Tech Lead"
        assert isinstance(p.personality_traits, list) and p.personality_traits
        assert isinstance(p.technical_stack, list) and p.technical_stack
        assert isinstance(p.work_values, list) and p.work_values
        assert isinstance(p.preferences, dict)
        assert isinstance(p.constraints, dict)

    def test_to_system_prompt_prefix_contains_key_fields(self):
        p = AmjadProfile()
        prefix = p.to_system_prompt_prefix()
        assert "Amjad" in prefix
        assert "Founder" in prefix
        assert "Trust Mode" in prefix
        assert "Shell Access" in prefix

    def test_save_and_load_roundtrip(self, tmp_path: Path):
        p = AmjadProfile(name="TestUser", role="CTO")
        path = tmp_path / "profile.json"
        p.save(path)

        loaded = AmjadProfile.load_or_create(path)
        assert loaded.name == "TestUser"
        assert loaded.role == "CTO"

    def test_load_or_create_creates_default_when_missing(self, tmp_path: Path):
        path = tmp_path / "nonexistent.json"
        p = AmjadProfile.load_or_create(path)
        assert p.name == "Amjad"

    def test_load_or_create_handles_corrupt_json(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("not json {")
        p = AmjadProfile.load_or_create(path)
        assert p.name == "Amjad"

    def test_save_creates_parent_directories(self, tmp_path: Path):
        path = tmp_path / "deep" / "nested" / "profile.json"
        AmjadProfile().save(path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["name"] == "Amjad"


# ---------------------------------------------------------------------------
# AmjadJarvisMetaOrchestrator tests
# ---------------------------------------------------------------------------


class TestAmjadJarvisMetaOrchestrator:
    def _make_orchestrator(self, *agent_slugs: str) -> AmjadJarvisMetaOrchestrator:
        registry = _fake_registry(*agent_slugs) if agent_slugs else _fake_registry()
        llm = _ScriptedLLM([
            _Resp(stop_reason="end_turn", content=[_TextBlock("response")],
                  usage=_FakeUsage()),
        ] * 20)
        return AmjadJarvisMetaOrchestrator(
            config=MetaOrchestratorConfig(),
            registry=registry,
            llm=llm,
        )

    def test_init_loads_default_profile(self):
        orch = self._make_orchestrator()
        assert orch.amjad.name == "Amjad"

    def test_set_trust_mode_updates_preference_and_env(self, monkeypatch):
        orch = self._make_orchestrator()
        monkeypatch.delenv("AGENCY_TRUST_MODE", raising=False)
        orch.set_trust_mode("yolo")
        assert orch.amjad.preferences["trust_mode"] == "yolo"
        assert os.environ.get("AGENCY_TRUST_MODE") == "yolo"

    def test_enable_shell_sets_env(self, monkeypatch):
        orch = self._make_orchestrator()
        monkeypatch.delenv("AGENCY_ALLOW_SHELL", raising=False)
        orch.enable_shell(True)
        assert os.environ.get("AGENCY_ALLOW_SHELL") == "1"
        assert orch.amjad.preferences["shell_access"] is True

        orch.enable_shell(False)
        assert "AGENCY_ALLOW_SHELL" not in os.environ
        assert orch.amjad.preferences["shell_access"] is False

    def test_enable_web_search_sets_env(self, monkeypatch):
        orch = self._make_orchestrator()
        monkeypatch.delenv("AGENCY_ENABLE_WEB_SEARCH", raising=False)
        orch.enable_web_search(True)
        assert os.environ.get("AGENCY_ENABLE_WEB_SEARCH") == "1"
        orch.enable_web_search(False)
        assert "AGENCY_ENABLE_WEB_SEARCH" not in os.environ

    def test_enable_code_execution_sets_env(self, monkeypatch):
        orch = self._make_orchestrator()
        monkeypatch.delenv("AGENCY_ENABLE_CODE_EXECUTION", raising=False)
        orch.enable_code_execution(True)
        assert os.environ.get("AGENCY_ENABLE_CODE_EXECUTION") == "1"
        orch.enable_code_execution(False)
        assert "AGENCY_ENABLE_CODE_EXECUTION" not in os.environ

    def test_enable_computer_use_sets_env(self, monkeypatch):
        orch = self._make_orchestrator()
        monkeypatch.delenv("AGENCY_ENABLE_COMPUTER_USE", raising=False)
        orch.enable_computer_use(True)
        assert os.environ.get("AGENCY_ENABLE_COMPUTER_USE") == "1"
        orch.enable_computer_use(False)
        assert "AGENCY_ENABLE_COMPUTER_USE" not in os.environ

    def test_set_amjad_preference_updates_known_key(self):
        orch = self._make_orchestrator()
        orch.set_amjad_preference("trust_mode", "off")
        assert orch.amjad.preferences["trust_mode"] == "off"

    def test_set_amjad_preference_ignores_unknown_key(self):
        orch = self._make_orchestrator()
        orch.set_amjad_preference("totally_unknown_key", "value")
        assert "totally_unknown_key" not in orch.amjad.preferences


class TestContextInjection:
    def test_create_context_aware_executor_returns_enhanced_skill(self):
        registry = _fake_registry("my-agent")
        llm = _ScriptedLLM([])
        orch = AmjadJarvisMetaOrchestrator(
            config=MetaOrchestratorConfig(),
            registry=registry,
            llm=llm,
        )
        skill = registry.by_slug("my-agent")
        assert skill is not None

        executor, enhanced_skill = orch._create_context_aware_executor(skill)

        # Enhanced skill body should contain Amjad's context prefix
        assert "Amjad" in enhanced_skill.body
        assert "Founder" in enhanced_skill.body
        # …followed by the original prompt
        assert "You are a test agent." in enhanced_skill.body
        # Slug/name unchanged
        assert enhanced_skill.slug == skill.slug
        assert enhanced_skill.name == skill.name

    def test_create_context_aware_executor_replaces_skill_in_registry(self):
        registry = _fake_registry("my-agent", "other-agent")
        llm = _ScriptedLLM([])
        orch = AmjadJarvisMetaOrchestrator(
            config=MetaOrchestratorConfig(),
            registry=registry,
            llm=llm,
        )
        skill = registry.by_slug("my-agent")
        executor, enhanced_skill = orch._create_context_aware_executor(skill)

        reg_skill = executor.registry.by_slug("my-agent")
        assert reg_skill is not None
        assert "Amjad" in reg_skill.body
        # Other agent should still be present
        assert executor.registry.by_slug("other-agent") is not None

    def test_execute_unified_request_passes_enhanced_skill_to_run(self, tmp_path: Path):
        """The system prompt sent to the LLM must include Amjad's context prefix."""
        registry = _fake_registry("test-agent")
        llm = _ScriptedLLM([
            _Resp(stop_reason="end_turn", content=[_TextBlock("answer")],
                  usage=_FakeUsage()),
        ])
        orch = AmjadJarvisMetaOrchestrator(
            config=MetaOrchestratorConfig(),
            registry=registry,
            llm=llm,
        )

        result = orch.execute_unified_request("do something", primary_agent_slug="test-agent")

        assert result.text == "answer"
        assert len(llm.calls) == 1
        system = llm.calls[0]["system"]
        # system is a list of blocks; the text must contain the Amjad prefix
        system_text = "".join(
            b["text"] for b in system if isinstance(b, dict) and b.get("type") == "text"
        )
        assert "Amjad" in system_text
        assert "Founder" in system_text


class TestExecuteUnifiedRequest:
    def test_returns_execution_result(self):
        registry = _fake_registry("test-agent")
        llm = _ScriptedLLM([
            _Resp(stop_reason="end_turn", content=[_TextBlock("hello")], usage=_FakeUsage()),
        ])
        orch = AmjadJarvisMetaOrchestrator(
            config=MetaOrchestratorConfig(),
            registry=registry,
            llm=llm,
        )
        result = orch.execute_unified_request("say hello", primary_agent_slug="test-agent")
        assert result.text == "hello"
        assert result.turns == 1

    def test_session_id_creates_session_with_skill_slug(self, tmp_path: Path):
        registry = _fake_registry("test-agent")
        llm = _ScriptedLLM([
            _Resp(stop_reason="end_turn", content=[_TextBlock("hi")], usage=_FakeUsage()),
        ])
        memory = MemoryStore(tmp_path / "sessions")
        orch = AmjadJarvisMetaOrchestrator(
            config=MetaOrchestratorConfig(),
            registry=registry,
            llm=llm,
            memory=memory,
        )
        result = orch.execute_unified_request(
            "say hi",
            primary_agent_slug="test-agent",
            session_id="test-session",
        )
        assert result.text == "hi"
        saved = memory.load("test-session")
        assert saved is not None
        assert [t.text for t in saved.turns] == ["say hi", "hi"]

    def test_unknown_hint_slug_raises_value_error(self):
        registry = _fake_registry("test-agent")
        llm = _ScriptedLLM([])
        orch = AmjadJarvisMetaOrchestrator(
            config=MetaOrchestratorConfig(),
            registry=registry,
            llm=llm,
        )
        with pytest.raises(ValueError, match="Unknown skill slug"):
            orch.execute_unified_request("x", primary_agent_slug="no-such-agent")


class TestMultiAgentWorkflow:
    def _orch_with_agents(self, *slugs: str) -> AmjadJarvisMetaOrchestrator:
        registry = _fake_registry(*slugs)
        # Provide enough responses for all agents
        llm = _ScriptedLLM([
            _Resp(stop_reason="end_turn",
                  content=[_TextBlock(f"result-from-{slug}")],
                  usage=_FakeUsage())
            for slug in slugs
        ])
        return AmjadJarvisMetaOrchestrator(
            config=MetaOrchestratorConfig(),
            registry=registry,
            llm=llm,
        )

    def test_parallel_workflow_returns_results_for_all_agents(self):
        orch = self._orch_with_agents("agent-a", "agent-b", "agent-c")
        results = orch.execute_multi_agent_workflow(
            workflow_name="test",
            primary_request="do stuff",
            agent_sequence=["agent-a", "agent-b", "agent-c"],
            parallel=True,
        )
        assert set(results.keys()) == {"agent-a", "agent-b", "agent-c"}
        for slug, result in results.items():
            assert isinstance(result, ExecutionResult)

    def test_sequential_workflow_returns_results_for_all_agents(self):
        orch = self._orch_with_agents("agent-a", "agent-b")
        results = orch.execute_multi_agent_workflow(
            workflow_name="test",
            primary_request="do stuff",
            agent_sequence=["agent-a", "agent-b"],
            parallel=False,
        )
        assert set(results.keys()) == {"agent-a", "agent-b"}

    def test_unknown_agent_slug_raises_value_error(self):
        orch = self._orch_with_agents("agent-a")
        with pytest.raises(ValueError, match="Unknown agent slug"):
            orch.execute_multi_agent_workflow(
                workflow_name="bad",
                primary_request="x",
                agent_sequence=["no-such-agent"],
            )

    def test_workflow_without_sequence_auto_identifies_agents(self):
        orch = self._orch_with_agents("frontend-developer", "backend-architect")
        # Provide extra responses in case auto-identification picks more agents.
        orch.llm._responses.extend([
            _Resp(stop_reason="end_turn", content=[_TextBlock("extra")], usage=_FakeUsage()),
        ] * 4)
        results = orch.execute_multi_agent_workflow(
            workflow_name="auto",
            primary_request="frontend developer backend architect",
        )
        assert isinstance(results, dict)


# ---------------------------------------------------------------------------
# Global singleton tests
# ---------------------------------------------------------------------------


class TestGlobalSingleton:
    def test_jarvis_returns_same_instance_on_repeated_calls(self):
        import agency.amjad_jarvis_meta_orchestrator as mod
        mod._global_jarvis = None  # reset
        j1 = jarvis()
        j2 = jarvis()
        assert j1 is j2

    def test_init_jarvis_replaces_global_instance(self):
        import agency.amjad_jarvis_meta_orchestrator as mod
        mod._global_jarvis = None
        j1 = init_jarvis()
        j2 = init_jarvis()
        assert j1 is not j2


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestAmjadCLI:
    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def no_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def test_amjad_group_registered_on_main(self, runner, no_api_key):
        result = runner.invoke(main, ["amjad", "--help"])
        assert result.exit_code == 0
        assert "amjad" in result.output.lower() or "orchestrator" in result.output.lower()

    def test_amjad_profile_show(self, runner, no_api_key):
        result = runner.invoke(main, ["amjad", "profile", "show"])
        assert result.exit_code == 0
        assert "Amjad" in result.output
        assert "PREFERENCES" in result.output

    def test_amjad_profile_set_known_key(self, runner, no_api_key, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        import agency.amjad_jarvis_meta_orchestrator as mod
        mod._global_jarvis = None
        result = runner.invoke(main, ["amjad", "profile", "set", "trust_mode", "off"])
        assert result.exit_code == 0
        assert "trust_mode" in result.output or "off" in result.output

    def test_amjad_profile_set_unknown_key(self, runner, no_api_key):
        result = runner.invoke(main, ["amjad", "profile", "set", "unknown_key_xyz", "value"])
        assert result.exit_code == 0
        assert "Unknown" in result.output

    def test_amjad_trust_command(self, runner, no_api_key):
        result = runner.invoke(main, ["amjad", "trust", "on-my-machine"])
        assert result.exit_code == 0
        assert "on-my-machine" in result.output

    def test_amjad_trust_off(self, runner, no_api_key):
        result = runner.invoke(main, ["amjad", "trust", "off"])
        assert result.exit_code == 0
        assert "off" in result.output

    def test_amjad_trust_yolo(self, runner, no_api_key):
        result = runner.invoke(main, ["amjad", "trust", "yolo"])
        assert result.exit_code == 0
        assert "yolo" in result.output

    def test_amjad_shell_on(self, runner, no_api_key):
        result = runner.invoke(main, ["amjad", "shell", "on"])
        assert result.exit_code == 0
        assert "enabled" in result.output

    def test_amjad_shell_off(self, runner, no_api_key):
        result = runner.invoke(main, ["amjad", "shell", "off"])
        assert result.exit_code == 0
        assert "disabled" in result.output

    def test_amjad_shell_status(self, runner, no_api_key):
        result = runner.invoke(main, ["amjad", "shell", "status"])
        assert result.exit_code == 0
        assert "Shell" in result.output or "enabled" in result.output or "disabled" in result.output

    def test_amjad_web_search_on(self, runner, no_api_key):
        result = runner.invoke(main, ["amjad", "web-search", "on"])
        assert result.exit_code == 0
        assert "enabled" in result.output

    def test_amjad_web_search_off(self, runner, no_api_key):
        result = runner.invoke(main, ["amjad", "web-search", "off"])
        assert result.exit_code == 0
        assert "disabled" in result.output

    def test_amjad_code_exec_on(self, runner, no_api_key):
        result = runner.invoke(main, ["amjad", "code-exec", "on"])
        assert result.exit_code == 0
        assert "enabled" in result.output

    def test_amjad_code_exec_off(self, runner, no_api_key):
        result = runner.invoke(main, ["amjad", "code-exec", "off"])
        assert result.exit_code == 0
        assert "disabled" in result.output

    def test_amjad_computer_use_on(self, runner, no_api_key):
        result = runner.invoke(main, ["amjad", "computer-use", "on"])
        assert result.exit_code == 0
        assert "enabled" in result.output

    def test_amjad_computer_use_off(self, runner, no_api_key):
        result = runner.invoke(main, ["amjad", "computer-use", "off"])
        assert result.exit_code == 0
        assert "disabled" in result.output

    def test_amjad_status(self, runner, no_api_key):
        result = runner.invoke(main, ["amjad", "status"])
        assert result.exit_code == 0
        assert "STATUS" in result.output
        assert "Trust mode" in result.output
        assert "Agents loaded" in result.output

    def test_amjad_run_requires_api_key(self, runner, no_api_key):
        """``agency amjad run`` should fail gracefully when no API key is set."""
        result = runner.invoke(main, ["amjad", "run", "do something"])
        # Either a non-zero exit or an error message mentioning the API key
        assert result.exit_code != 0 or "ANTHROPIC_API_KEY" in result.output or "error" in result.output.lower()
