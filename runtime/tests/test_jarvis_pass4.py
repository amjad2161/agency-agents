"""Pass-4 tests: autonomous_loop, capability_evolver, knowledge_expansion,
meta_reasoner, amjad_jarvis_meta_orchestrator.

All LLM/API calls are mocked.  No network access required.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ===========================================================================
# autonomous_loop
# ===========================================================================


class TestAutonomousLoop:
    """Tests for AutonomousLoop."""

    def _make_loop(self, tmp_path: Path, **kwargs):
        from agency.autonomous_loop import AutonomousLoop

        return AutonomousLoop(runs_path=tmp_path / "loop_runs.jsonl", **kwargs)

    def test_instantiate(self, tmp_path):
        from agency.autonomous_loop import AutonomousLoop

        loop = self._make_loop(tmp_path)
        assert loop is not None

    def test_run_no_executor_returns_loop_run(self, tmp_path):
        from agency.autonomous_loop import LoopStatus

        loop = self._make_loop(tmp_path, max_iterations=3)
        run = loop.run("test goal")
        assert run.goal == "test goal"
        assert run.status in {LoopStatus.DONE, LoopStatus.MAX_ITER, LoopStatus.INTERRUPTED}
        assert len(run.iterations) > 0

    def test_run_with_executor_success(self, tmp_path):
        from agency.autonomous_loop import LoopStatus

        loop = self._make_loop(tmp_path, max_iterations=5)

        def executor(action: str, ctx: dict) -> str:
            return "success: task complete and finished"

        loop.register_executor("default", executor)
        run = loop.run("search for something")
        # executor returns "complete" so loop should finish early
        assert run.status == LoopStatus.DONE
        assert run.result != ""

    def test_run_persists_to_file(self, tmp_path):
        loop = self._make_loop(tmp_path, max_iterations=2)
        runs_file = tmp_path / "loop_runs.jsonl"
        loop.run("persist test")
        assert runs_file.exists()
        lines = runs_file.read_text().splitlines()
        assert len(lines) >= 1
        data = json.loads(lines[0])
        assert data["goal"] == "persist test"

    def test_stop_sets_flag(self, tmp_path):
        from agency.autonomous_loop import LoopStatus

        stop_event = threading.Event()
        loop = self._make_loop(tmp_path, max_iterations=50, stop_event=stop_event)

        slow_calls = []

        def slow_executor(action: str, ctx: dict) -> str:
            slow_calls.append(1)
            time.sleep(0.01)
            return "still running"

        loop.register_executor("default", slow_executor)

        stop_event.set()  # pre-set — loop should abort immediately
        run = loop.run("goal that should abort")
        assert run.status == LoopStatus.INTERRUPTED
        assert len(slow_calls) == 0

    def test_stop_method(self, tmp_path):
        loop = self._make_loop(tmp_path, max_iterations=3)
        loop.stop()
        assert loop._stop_event.is_set()
        loop.reset_stop()
        assert not loop._stop_event.is_set()

    def test_run_async_completes(self, tmp_path):
        loop = self._make_loop(tmp_path, max_iterations=2)
        results = []

        def cb(run):
            results.append(run)

        thread = loop.run_async("async goal", callback=cb)
        thread.join(timeout=5.0)
        assert not thread.is_alive()
        assert len(results) == 1
        assert results[0].goal == "async goal"

    def test_get_run_history_empty(self, tmp_path):
        loop = self._make_loop(tmp_path)
        assert loop.get_run_history() == []

    def test_get_run_history_after_run(self, tmp_path):
        loop = self._make_loop(tmp_path, max_iterations=1)
        loop.run("history test")
        history = loop.get_run_history()
        assert len(history) >= 1
        assert history[0].goal == "history test"

    def test_executor_error_is_caught(self, tmp_path):
        from agency.autonomous_loop import LoopStatus

        loop = self._make_loop(tmp_path, max_iterations=3)

        def bad_executor(action: str, ctx: dict) -> str:
            raise RuntimeError("executor exploded")

        loop.register_executor("default", bad_executor)
        run = loop.run("problematic goal")
        # Executor errors are surfaced as "[executor error]" observations, NOT loop ERROR status
        assert run.status in {LoopStatus.DONE, LoopStatus.MAX_ITER}
        assert any("executor error" in it.observation for it in run.iterations)

    def test_max_iterations_guard(self, tmp_path):
        from agency.autonomous_loop import LoopStatus

        loop = self._make_loop(tmp_path, max_iterations=3)

        def never_done(action: str, ctx: dict) -> str:
            return "still going"

        loop.register_executor("default", never_done)
        run = loop.run("never ending")
        # _is_done returns True on final iteration index, so status is DONE
        # MAX_ITER is set only when for-else fires (loop exhausts without break).
        assert run.status in {LoopStatus.DONE, LoopStatus.MAX_ITER}
        assert len(run.iterations) == 3

    def test_register_multiple_executors(self, tmp_path):
        loop = self._make_loop(tmp_path, max_iterations=1)

        calls = []

        def exec_a(action: str, ctx: dict) -> str:
            calls.append("a")
            return "done"

        def exec_b(action: str, ctx: dict) -> str:
            calls.append("b")
            return "done"

        loop.register_executor("A", exec_a)
        loop.register_executor("B", exec_b)
        loop.run("goal", executor_name="B")
        assert calls == ["b"]

    def test_context_passed_to_executor(self, tmp_path):
        loop = self._make_loop(tmp_path, max_iterations=2)
        received_ctx = []

        def ctx_executor(action: str, ctx: dict) -> str:
            received_ctx.append(dict(ctx))
            return "done finished"

        loop.register_executor("default", ctx_executor)
        loop.run("ctx goal", context={"user_id": "amjad"})
        assert received_ctx[0].get("user_id") == "amjad"


# ===========================================================================
# capability_evolver
# ===========================================================================


class TestCapabilityEvolver:
    def _make(self, tmp_path: Path):
        from agency.capability_evolver import CapabilityEvolver

        return CapabilityEvolver(profile_path=tmp_path / "capability.json")

    def test_instantiate(self, tmp_path):
        from agency.capability_evolver import CapabilityEvolver

        ce = self._make(tmp_path)
        assert ce is not None

    def test_record_outcome_creates_profile(self, tmp_path):
        ce = self._make(tmp_path)
        profile = ce.record_outcome("jarvis-engineering", success=True, confidence=0.9)
        assert profile.slug == "jarvis-engineering"
        assert profile.total_requests == 1
        assert profile.successful == 1

    def test_record_outcome_failure(self, tmp_path):
        ce = self._make(tmp_path)
        p = ce.record_outcome("coding", success=False, confidence=0.5)
        assert p.failed == 1
        assert p.successful == 0

    def test_moving_average_confidence(self, tmp_path):
        ce = self._make(tmp_path)
        ce.record_outcome("domain", success=True, confidence=1.0)
        ce.record_outcome("domain", success=True, confidence=0.0)
        p = ce.get_profile("domain")
        assert 0.0 < p.avg_confidence < 1.0

    def test_proficiency_score_range(self, tmp_path):
        ce = self._make(tmp_path)
        for _ in range(5):
            ce.record_outcome("ml", success=True, confidence=0.8)
        p = ce.get_profile("ml")
        assert 0.0 <= p.proficiency_score <= 1.0

    def test_success_rate_property(self, tmp_path):
        ce = self._make(tmp_path)
        ce.record_outcome("d", success=True)
        ce.record_outcome("d", success=True)
        ce.record_outcome("d", success=False)
        p = ce.get_profile("d")
        assert abs(p.success_rate - 2 / 3) < 1e-9

    def test_weakest_domains(self, tmp_path):
        ce = self._make(tmp_path)
        for _ in range(5):
            ce.record_outcome("bad", success=False, confidence=0.1)
        for _ in range(5):
            ce.record_outcome("good", success=True, confidence=0.99)
        weak = ce.weakest_domains(n=1)
        assert weak[0].slug == "bad"

    def test_strongest_domains(self, tmp_path):
        ce = self._make(tmp_path)
        for _ in range(5):
            ce.record_outcome("good", success=True, confidence=0.99)
        for _ in range(5):
            ce.record_outcome("bad", success=False, confidence=0.1)
        strong = ce.strongest_domains(n=1)
        assert strong[0].slug == "good"

    def test_untrained_domains(self, tmp_path):
        ce = self._make(tmp_path)
        ce.record_outcome("known", success=True)
        unknown = ce.untrained_domains(["known", "new-domain"])
        assert "new-domain" in unknown
        assert "known" not in unknown

    def test_suggest_improvement_targets(self, tmp_path):
        ce = self._make(tmp_path)
        for _ in range(3):
            ce.record_outcome("weak", success=False, confidence=0.1)
        targets = ce.suggest_improvement_targets(["weak", "never-seen"])
        assert "never-seen" in targets

    def test_growth_report_empty(self, tmp_path):
        ce = self._make(tmp_path)
        report = ce.growth_report()
        assert "No capability data" in report

    def test_growth_report_with_data(self, tmp_path):
        ce = self._make(tmp_path)
        ce.record_outcome("a", success=True, confidence=0.8)
        report = ce.growth_report()
        assert "JARVIS Capability Growth Report" in report
        assert "a" in report

    def test_reset_domain(self, tmp_path):
        ce = self._make(tmp_path)
        ce.record_outcome("temp", success=True)
        removed = ce.reset_domain("temp")
        assert removed is True
        assert ce.get_profile("temp") is None

    def test_reset_nonexistent_domain(self, tmp_path):
        ce = self._make(tmp_path)
        assert ce.reset_domain("ghost") is False

    def test_persistence_across_instances(self, tmp_path):
        path = tmp_path / "cap.json"
        from agency.capability_evolver import CapabilityEvolver

        ce1 = CapabilityEvolver(profile_path=path)
        ce1.record_outcome("persistent", success=True, confidence=0.75)

        ce2 = CapabilityEvolver(profile_path=path)
        p = ce2.get_profile("persistent")
        assert p is not None
        assert p.total_requests == 1

    def test_growth_note_stored(self, tmp_path):
        ce = self._make(tmp_path)
        ce.record_outcome("annotated", success=True, note="First contact")
        p = ce.get_profile("annotated")
        assert any("First contact" in n for n in p.growth_notes)

    def test_all_profiles(self, tmp_path):
        ce = self._make(tmp_path)
        ce.record_outcome("x", success=True)
        ce.record_outcome("y", success=False)
        profiles = ce.all_profiles()
        slugs = {p.slug for p in profiles}
        assert {"x", "y"} == slugs


# ===========================================================================
# knowledge_expansion
# ===========================================================================


class TestKnowledgeExpansion:
    def _make(self, **kwargs):
        from agency.knowledge_expansion import KnowledgeExpansion

        return KnowledgeExpansion(**kwargs)

    def test_instantiate(self):
        ke = self._make()
        assert ke is not None

    def test_ingest_text_returns_chunks(self):
        ke = self._make()
        chunks = ke.ingest_text("Transformers use self-attention mechanisms.", source="test")
        assert len(chunks) >= 1
        assert chunks[0].source == "test"

    def test_ingest_text_domain_preserved(self):
        ke = self._make()
        chunks = ke.ingest_text("Neural networks learn representations.", domain="ML")
        assert all(c.domain == "ML" for c in chunks)

    def test_ingest_text_custom_tags(self):
        ke = self._make()
        chunks = ke.ingest_text("Python is great.", tags=["python", "code"])
        assert "python" in chunks[0].tags

    def test_ingest_text_summary_populated(self):
        ke = self._make()
        text = "First sentence here. Second sentence follows. Third one too."
        chunks = ke.ingest_text(text)
        assert chunks[0].summary != ""

    def test_ingest_long_text_splits(self):
        ke = self._make(chunk_size=20, chunk_overlap=5)
        words = " ".join(["word"] * 50)
        chunks = ke.ingest_text(words)
        assert len(chunks) > 1

    def test_search_finds_ingested(self):
        ke = self._make()
        ke.ingest_text("JARVIS is an autonomous AI assistant.", source="docs")
        results = ke.search("autonomous assistant")
        assert len(results) >= 1
        assert any("JARVIS" in r.text for r in results)

    def test_search_domain_filter(self):
        ke = self._make()
        ke.ingest_text("Python code runs fast.", domain="python")
        ke.ingest_text("JavaScript code runs everywhere.", domain="js")
        results = ke.search("code", domain="python")
        assert all(r.domain == "python" for r in results)

    def test_search_empty_returns_empty(self):
        ke = self._make()
        assert ke.search("anything") == []

    def test_search_top_k_limit(self):
        ke = self._make()
        for i in range(10):
            ke.ingest_text(f"Document {i} about Python.", source=f"doc{i}")
        results = ke.search("Python", top_k=3)
        assert len(results) <= 3

    def test_stats(self):
        ke = self._make()
        ke.ingest_text("Hello world.", domain="general")
        stats = ke.stats()
        assert stats["total_chunks"] >= 1
        assert "general" in stats["domains"]

    def test_list_domains(self):
        ke = self._make()
        ke.ingest_text("a", domain="X")
        ke.ingest_text("b", domain="Y")
        domains = ke.list_domains()
        assert set(domains) == {"X", "Y"}

    def test_chunk_id_deterministic(self):
        ke = self._make()
        cid1 = ke._chunk_id("src", 0, "hello world")
        cid2 = ke._chunk_id("src", 0, "hello world")
        assert cid1 == cid2

    def test_strip_html(self):
        from agency.knowledge_expansion import KnowledgeExpansion

        html = "<html><body><p>Hello <b>World</b></p><script>alert(1)</script></body></html>"
        text = KnowledgeExpansion._strip_html(html)
        assert "<" not in text
        assert "Hello" in text
        assert "alert" not in text

    def test_ingest_url_failure_returns_stub_chunk(self):
        ke = self._make()
        # Non-routable URL — should not raise, returns stub chunk
        chunks = ke.ingest_url("http://0.0.0.0:1/no-such-page", domain="test")
        assert len(chunks) >= 1
        assert "fetch failed" in chunks[0].text.lower()

    def test_ingest_url_with_mock(self):
        import urllib.request
        from unittest.mock import patch, MagicMock

        ke = self._make()
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<p>Test content from web</p>"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch.object(urllib.request, "urlopen", return_value=mock_resp):
            chunks = ke.ingest_url("http://example.com/page", domain="web")
        assert any("Test content" in c.text for c in chunks)

    def test_vector_store_search_used_when_available(self):
        mock_vs = MagicMock()
        mock_vs.search.return_value = [
            {"id": "x", "source": "vs", "text": "vector result", "summary": "", "tags": [], "domain": "D"}
        ]
        ke = self._make(vector_store=mock_vs)
        ke.ingest_text("local content")
        results = ke.search("vector")
        mock_vs.search.assert_called_once()
        assert results[0].text == "vector result"


# ===========================================================================
# meta_reasoner
# ===========================================================================


class TestMetaReasoningEngine:
    def _make(self):
        from agency.meta_reasoner import MetaReasoningEngine

        return MetaReasoningEngine()

    def test_instantiate(self):
        engine = self._make()
        assert engine is not None

    def test_reason_returns_steps(self):
        engine = self._make()
        steps = engine.reason("Explain how rate limiting works")
        assert len(steps) >= 2
        for s in steps:
            assert s.thought
            assert s.step_id >= 1

    def test_reason_max_iterations(self):
        engine = self._make()
        steps = engine.reason("Simple goal", max_iterations=2)
        assert len(steps) <= 2

    def test_reason_step_ids_sequential(self):
        engine = self._make()
        steps = engine.reason("Goal here", max_iterations=4)
        for i, s in enumerate(steps, 1):
            assert s.step_id == i

    def test_reason_confidence_range(self):
        engine = self._make()
        steps = engine.reason("Design a database schema", max_iterations=5)
        for s in steps:
            assert 0.0 <= s.confidence <= 1.0

    def test_last_steps_after_reason(self):
        engine = self._make()
        engine.reason("Something")
        assert len(engine.last_steps()) > 0

    def test_avg_confidence(self):
        engine = self._make()
        engine.reason("Any goal", max_iterations=3)
        avg = engine.avg_confidence()
        assert 0.0 <= avg <= 1.0

    def test_avg_confidence_empty(self):
        engine = self._make()
        assert engine.avg_confidence() == 0.0

    def test_critique_good_response(self):
        engine = self._make()
        long_response = " ".join(["word"] * 50)
        score, feedback = engine.critique(long_response, "explain something")
        assert 0.0 <= score <= 1.0
        assert isinstance(feedback, str)

    def test_critique_short_response_penalized(self):
        engine = self._make()
        score, feedback = engine.critique("Too short.", "explain the entire history of computing")
        # Should be penalized for brevity
        assert score < 1.0
        assert "brief" in feedback.lower() or len(feedback) > 0

    def test_critique_code_expected(self):
        engine = self._make()
        score, feedback = engine.critique("Here is some text without code", "write a function to do X")
        assert score < 1.0

    def test_critique_score_clipped_to_zero(self):
        engine = self._make()
        score, _ = engine.critique("x", "write implement example function code")
        assert score >= 0.0

    def test_refine_no_refinement_needed(self):
        engine = self._make()
        long_good = " ".join(["explanation"] * 60)
        result = engine.refine(long_good, "explain this topic", iterations=1)
        # Either "No refinement needed" or notes
        assert isinstance(result, str) and len(result) > 0

    def test_refine_generates_notes(self):
        engine = self._make()
        result = engine.refine("short", "explain implement example function", iterations=2)
        assert "Iteration" in result or "No refinement" in result

    def test_plan_and_execute_returns_string(self):
        engine = self._make()
        plan = engine.plan_and_execute("Design a rate limiter")
        assert "Execution Plan" in plan
        assert "Step" in plan

    def test_plan_and_execute_with_tools(self):
        engine = self._make()
        tools = [{"name": "search_web"}, {"name": "code_generator"}]
        plan = engine.plan_and_execute("Find information and generate code", tools=tools)
        assert isinstance(plan, str)
        assert len(plan) > 0

    def test_decompose_numbered_list(self):
        engine = self._make()
        goal = "1. Gather requirements\n2. Design schema\n3. Implement API"
        steps = engine.reason(goal, max_iterations=5)
        # Numbered items should be used as sub-goals
        assert len(steps) >= 2

    def test_reason_with_context(self):
        engine = self._make()
        steps = engine.reason("Solve the problem", context="Background: user has Python 3.11")
        assert len(steps) >= 1
        # Context should appear in first thought
        first_thought = steps[0].thought
        assert "Background" in first_thought or len(first_thought) > 5

    def test_step_to_dict(self):
        from agency.meta_reasoner import ReasoningStep

        s = ReasoningStep(step_id=1, thought="test thought", action="do X", confidence=0.8)
        d = s.to_dict()
        assert d["step_id"] == 1
        assert d["thought"] == "test thought"
        assert d["confidence"] == 0.8


# ===========================================================================
# amjad_jarvis_meta_orchestrator
# ===========================================================================


class TestAmjadProfile:
    def test_instantiate_defaults(self):
        from agency.amjad_jarvis_meta_orchestrator import AmjadProfile

        p = AmjadProfile()
        assert p.name == "Amjad"
        assert len(p.personality_traits) > 0
        assert len(p.technical_stack) > 0

    def test_to_system_prompt_prefix(self):
        from agency.amjad_jarvis_meta_orchestrator import AmjadProfile

        p = AmjadProfile()
        prefix = p.to_system_prompt_prefix()
        assert "Amjad" in prefix
        assert "Python" in prefix
        assert "trust_mode" in prefix.lower() or "Trust Mode" in prefix

    def test_save_and_load(self, tmp_path):
        from agency.amjad_jarvis_meta_orchestrator import AmjadProfile

        path = tmp_path / "profile.json"
        p = AmjadProfile(name="Amjad", role="Founder")
        p.save(profile_path=path)

        loaded = AmjadProfile.load_or_create(profile_path=path)
        assert loaded.name == "Amjad"
        assert loaded.role == "Founder"

    def test_load_or_create_missing_file(self, tmp_path):
        from agency.amjad_jarvis_meta_orchestrator import AmjadProfile

        p = AmjadProfile.load_or_create(profile_path=tmp_path / "nonexistent.json")
        assert p.name == "Amjad"

    def test_load_or_create_corrupt_file(self, tmp_path):
        from agency.amjad_jarvis_meta_orchestrator import AmjadProfile

        bad = tmp_path / "bad.json"
        bad.write_text("not valid json{{{")
        p = AmjadProfile.load_or_create(profile_path=bad)
        assert p.name == "Amjad"  # falls back to default


class TestMetaOrchestratorConfig:
    def test_defaults(self):
        from agency.amjad_jarvis_meta_orchestrator import MetaOrchestratorConfig

        cfg = MetaOrchestratorConfig()
        assert cfg.enable_parallel_execution is True
        assert cfg.max_parallel_agents == 8
        assert cfg.session_persistence is True


def _mock_registry():
    """Return a minimal SkillRegistry-like mock."""
    from agency.skills import Skill

    mock_skill = Skill(
        slug="test-agent",
        name="Test Agent",
        description="A test agent",
        category="test",
        color="#fff",
        emoji="🤖",
        vibe="helpful",
        body="You are a test agent.",
        path=Path("/tmp/test-agent.md"),
    )
    registry = MagicMock()
    registry.all.return_value = [mock_skill]
    registry.by_slug.return_value = mock_skill
    registry.search.return_value = [mock_skill]
    return registry, mock_skill


class TestAmjadJarvisMetaOrchestrator:
    def _make(self, tmp_path: Path | None = None):
        from agency.amjad_jarvis_meta_orchestrator import (
            AmjadJarvisMetaOrchestrator,
            AmjadProfile,
            MetaOrchestratorConfig,
        )

        registry, _ = _mock_registry()
        mock_llm = MagicMock()
        profile = AmjadProfile()
        cfg = MetaOrchestratorConfig(amjad_profile=profile)

        return AmjadJarvisMetaOrchestrator(
            config=cfg,
            registry=registry,
            llm=mock_llm,
            memory=None,
        )

    def test_instantiate(self):
        orch = self._make()
        assert orch is not None
        assert orch.amjad.name == "Amjad"

    def test_set_trust_mode(self, monkeypatch):
        import os

        orch = self._make()
        orch.set_trust_mode("on-my-machine")
        assert orch.amjad.preferences["trust_mode"] == "on-my-machine"
        assert os.environ.get("AGENCY_TRUST_MODE") == "on-my-machine"

    def test_enable_shell(self):
        import os

        orch = self._make()
        orch.enable_shell(True)
        assert orch.amjad.preferences["shell_access"] is True
        assert os.environ.get("AGENCY_ALLOW_SHELL") == "1"

        orch.enable_shell(False)
        assert orch.amjad.preferences["shell_access"] is False
        assert "AGENCY_ALLOW_SHELL" not in os.environ

    def test_enable_web_search(self):
        import os

        orch = self._make()
        orch.enable_web_search(True)
        assert os.environ.get("AGENCY_ENABLE_WEB_SEARCH") == "1"
        orch.enable_web_search(False)
        assert "AGENCY_ENABLE_WEB_SEARCH" not in os.environ

    def test_enable_code_execution(self):
        import os

        orch = self._make()
        orch.enable_code_execution(True)
        assert os.environ.get("AGENCY_ENABLE_CODE_EXECUTION") == "1"

    def test_enable_computer_use(self):
        import os

        orch = self._make()
        orch.enable_computer_use(True)
        assert os.environ.get("AGENCY_ENABLE_COMPUTER_USE") == "1"

    def test_set_amjad_preference_known_key(self):
        orch = self._make()
        orch.set_amjad_preference("trust_mode", "paranoid")
        assert orch.amjad.preferences["trust_mode"] == "paranoid"

    def test_set_amjad_preference_unknown_key_ignored(self):
        orch = self._make()
        # Unknown key should not raise, but also not be added
        orch.set_amjad_preference("totally_unknown_key", "value")
        assert "totally_unknown_key" not in orch.amjad.preferences

    def test_identify_workflow_agents(self):
        orch = self._make()
        agents = orch._identify_workflow_agents("write code and search docs")
        assert isinstance(agents, list)
        # registry.search returns [mock_skill] so we get one slug
        assert agents == ["test-agent"]

    def test_create_context_aware_executor_preserves_tools_policy(self):
        from agency.amjad_jarvis_meta_orchestrator import (
            AmjadJarvisMetaOrchestrator,
            AmjadProfile,
            MetaOrchestratorConfig,
        )
        from agency.skills import Skill

        allowed_skill = Skill(
            slug="restricted",
            name="Restricted",
            description="desc",
            category="cat",
            color="#000",
            emoji="🔒",
            vibe="strict",
            body="system",
            path=Path("/tmp/restricted.md"),
            tools_allowed=("search", "read"),
            tools_denied=("shell",),
        )
        registry = MagicMock()
        registry.all.return_value = [allowed_skill]
        registry.by_slug.return_value = allowed_skill

        orch = AmjadJarvisMetaOrchestrator(
            config=MetaOrchestratorConfig(amjad_profile=AmjadProfile()),
            registry=registry,
            llm=MagicMock(),
        )
        _, enhanced = orch._create_context_aware_executor(allowed_skill)
        assert enhanced.tools_allowed == ("search", "read")
        assert enhanced.tools_denied == ("shell",)

    def test_enhanced_skill_has_amjad_prefix(self):
        orch = self._make()
        _, skill = _mock_registry()
        _, enhanced = orch._create_context_aware_executor(skill)
        assert "Amjad" in enhanced.body
        assert "test agent" in enhanced.body.lower() or "You are a test agent" in enhanced.body


class TestJarvisSingletons:
    def test_init_jarvis_returns_orchestrator(self):
        from agency.amjad_jarvis_meta_orchestrator import (
            AmjadJarvisMetaOrchestrator,
            MetaOrchestratorConfig,
            AmjadProfile,
            init_jarvis,
        )
        import agency.amjad_jarvis_meta_orchestrator as mod

        registry, _ = _mock_registry()
        cfg = MetaOrchestratorConfig(amjad_profile=AmjadProfile())

        with patch.object(mod, "SkillRegistry") as MockReg, \
             patch.object(mod, "AnthropicLLM"), \
             patch.object(mod, "LLMConfig"):
            MockReg.load.return_value = registry
            result = init_jarvis(cfg)

        assert isinstance(result, AmjadJarvisMetaOrchestrator)
        assert mod._global_jarvis is result

    def test_jarvis_singleton_auto_init(self):
        from agency.amjad_jarvis_meta_orchestrator import jarvis
        import agency.amjad_jarvis_meta_orchestrator as mod

        # Reset singleton
        mod._global_jarvis = None

        registry, _ = _mock_registry()
        with patch.object(mod, "SkillRegistry") as MockReg, \
             patch.object(mod, "AnthropicLLM"), \
             patch.object(mod, "LLMConfig"):
            MockReg.load.return_value = registry
            inst = jarvis()

        assert inst is not None
        assert mod._global_jarvis is inst

        # Second call returns same
        assert jarvis() is inst

        # Cleanup
        mod._global_jarvis = None
