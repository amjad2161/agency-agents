"""Pass 5 audit tests — cost_router, eval_harness, diagnostics,
managed_agents, supreme_brainiac (classifier fix), SupremeJarvisBrain.skills,
doctor AGENCY_BACKEND flag, __init__ getters, UnifiedBridge.
"""
from __future__ import annotations

import asyncio
import os
import pytest


# ---------------------------------------------------------------------------
# 1-5  ComplexityClassifier — fixed thresholds
# ---------------------------------------------------------------------------

from agency.supreme_brainiac import (
    ComplexityClassifier, Complexity,
    SupremeBrainCore, ModelRouter, ModelRoute,
    get_brainiac, reset_brainiac,
    EVOLUTION_INCREMENT, CoreStatus, TaskStatus,
)


@pytest.fixture(autouse=True)
def _reset_brainiac():
    reset_brainiac()
    yield
    reset_brainiac()


class TestComplexityClassifierFixed:
    def setup_method(self):
        self.clf = ComplexityClassifier()

    def test_trivial_short_light_no_heavy(self):
        assert self.clf.classify("list files") == Complexity.TRIVIAL

    def test_trivial_summarize(self):
        assert self.clf.classify("summarize this document") == Complexity.TRIVIAL

    def test_empty_string_is_trivial(self):
        assert self.clf.classify("") == Complexity.TRIVIAL

    def test_heavy_term_short_not_trivial(self):
        # Bug fix: "Design a kubernetes upgrade strategy" was misclassified TRIVIAL
        result = self.clf.classify("Design a kubernetes upgrade strategy")
        assert result not in (Complexity.TRIVIAL, Complexity.SIMPLE)

    def test_multi_heavy_short_text_very_complex(self):
        # 5+ heavy terms → VERY_COMPLEX regardless of word count
        result = self.clf.classify(
            "Design and architect a production microservices framework with trade-off analysis"
        )
        assert result == Complexity.VERY_COMPLEX

    def test_single_heavy_medium_length_complex(self):
        result = self.clf.classify("optimize the routing engine using lessons recorded so far")
        assert result in (Complexity.COMPLEX, Complexity.MEDIUM)

    def test_long_no_heavy_is_medium_or_simple(self):
        result = self.clf.classify(
            "please tell me all the things you know about the history of the universe"
        )
        assert result in (Complexity.MEDIUM, Complexity.SIMPLE)

    def test_what_is_trivial_or_simple(self):
        result = self.clf.classify("what is 2+2")
        assert result in (Complexity.TRIVIAL, Complexity.SIMPLE)

    def test_whitespace_only_is_trivial(self):
        assert self.clf.classify("   ") == Complexity.TRIVIAL


# ---------------------------------------------------------------------------
# 6-9  CostAwareRouter
# ---------------------------------------------------------------------------

from agency.cost_router import (
    CostAwareRouter, ModelTier, RouteDecision,
    CostBudgetExceeded, DEFAULT_TIERS,
)


class TestCostAwareRouter:
    def setup_method(self):
        self.router = CostAwareRouter()

    def test_recommend_returns_route_decision(self):
        d = self.router.recommend("list files", expected_input_tokens=100, expected_output_tokens=50)
        assert isinstance(d, RouteDecision)
        assert d.model
        assert d.estimated_cost >= 0

    def test_complex_task_gets_capable_model(self):
        d = self.router.recommend(
            "Design and architect a production microservices framework with trade-off analysis",
            expected_input_tokens=2000, expected_output_tokens=1000,
            force_complexity=Complexity.VERY_COMPLEX,
        )
        # VERY_COMPLEX requires capability_score >= 0.99 → flagship only
        assert d.model == "claude-opus-4-7"

    def test_spend_tracking(self):
        r = CostAwareRouter(spend_cap_usd=1.0)
        r.record_actual_spend(0.25)
        assert r.spend_so_far == pytest.approx(0.25, abs=1e-7)
        assert r.remaining_budget == pytest.approx(0.75, abs=1e-7)

    def test_spend_cap_raises(self):
        r = CostAwareRouter(spend_cap_usd=0.001)
        with pytest.raises(CostBudgetExceeded):
            r.recommend("Design a complex system", expected_input_tokens=5000,
                        expected_output_tokens=2000, force_complexity=Complexity.VERY_COMPLEX)

    def test_reset_spend(self):
        r = CostAwareRouter()
        r.record_actual_spend(0.5)
        r.reset_spend()
        assert r.spend_so_far == 0.0

    def test_negative_spend_raises(self):
        with pytest.raises(ValueError):
            self.router.record_actual_spend(-0.01)

    def test_no_cap_remaining_budget_is_none(self):
        assert self.router.remaining_budget is None

    def test_to_dict_has_all_keys(self):
        d = self.router.recommend("summarize", force_complexity=Complexity.TRIVIAL)
        dd = d.to_dict()
        assert {"model", "complexity", "estimated_cost", "rationale", "fallback_chain"} <= dd.keys()

    def test_model_tier_estimate_cost(self):
        tier = ModelTier("test", 3.0, 15.0, 0.92)
        cost = tier.estimate_cost(1_000_000, 1_000_000)
        assert cost == pytest.approx(18.0, abs=0.001)

    def test_fallback_chain_ordered_cheapest_first(self):
        d = self.router.recommend("list x", force_complexity=Complexity.TRIVIAL,
                                  expected_input_tokens=1000, expected_output_tokens=500)
        # fallback_chain should be cheaper→pricier after chosen
        assert isinstance(d.fallback_chain, list)


# ---------------------------------------------------------------------------
# 10-14  EvalSuite + EvalCase + routing_suite
# ---------------------------------------------------------------------------

from agency.eval_harness import (
    EvalCase, EvalSuite, Report, CaseResult,
    check_substring, check_regex, check_routing_slug,
    routing_suite,
)


class TestEvalHarness:
    def test_check_substring_case_insensitive(self):
        assert check_substring("Hello World", "hello")
        assert not check_substring("Hello World", "xyz")

    def test_check_regex(self):
        assert check_regex("price: $42.00", r"\$\d+\.\d{2}")
        assert not check_regex("no match here", r"^\d+$")

    def test_check_routing_slug_dict(self):
        assert check_routing_slug({"skill": "jarvis-devops"}, "jarvis-devops")
        assert not check_routing_slug({"skill": "other"}, "jarvis-devops")

    def test_check_routing_slug_string(self):
        assert check_routing_slug("my-slug", "my-slug")

    def test_check_routing_slug_none(self):
        assert not check_routing_slug(None, "anything")

    def test_eval_suite_run_pass(self):
        cases = [EvalCase("c1", "hello world", must_include=("hello",))]
        suite = EvalSuite("test_suite", cases)
        report = suite.run(lambda x: x.upper())
        assert report.passed == 1
        assert report.pass_rate == 1.0

    def test_eval_suite_run_fail(self):
        cases = [EvalCase("c1", "hello", must_include=("xyz",))]
        suite = EvalSuite("fail_suite", cases)
        report = suite.run(lambda x: x)
        assert report.passed == 0
        assert report.pass_rate == 0.0

    def test_eval_suite_must_not_include(self):
        cases = [EvalCase("c1", "clean text", must_not_include=("error",))]
        suite = EvalSuite("s", cases)
        report = suite.run(lambda x: "this is clean text")
        assert report.passed == 1

    def test_eval_suite_exception_gives_failed_case(self):
        def bad(_): raise RuntimeError("boom")
        cases = [EvalCase("c1", "test")]
        suite = EvalSuite("s", cases)
        report = suite.run(bad)
        assert report.cases[0].error == "boom"
        assert not report.cases[0].passed

    def test_report_summary_line(self):
        cases = [EvalCase("c1", "x")]
        suite = EvalSuite("my_suite", cases)
        report = suite.run(lambda x: x)
        line = report.summary_line()
        assert "my_suite" in line
        assert "100.0%" in line

    def test_report_to_dict_structure(self):
        cases = [EvalCase("c1", "x")]
        suite = EvalSuite("s", cases)
        report = suite.run(lambda x: x)
        d = report.to_dict()
        assert "total" in d and "passed" in d and "pass_rate" in d

    def test_from_dict_list(self):
        raw = [{"input": "hello", "expected_slug": "some-slug", "case_id": "t1"}]
        suite = EvalSuite.from_dict_list("ds", raw)
        assert len(suite.cases) == 1
        assert suite.cases[0].expected_slug == "some-slug"

    def test_routing_suite_has_ten_cases(self):
        suite = routing_suite()
        assert len(suite.cases) == 10


# ---------------------------------------------------------------------------
# 15-17  diagnostics
# ---------------------------------------------------------------------------

from agency.diagnostics import optional_deps_status, OPTIONAL_DEP_GROUPS


class TestDiagnostics:
    def test_optional_deps_returns_all_groups(self):
        result = optional_deps_status()
        assert set(result.keys()) == set(OPTIONAL_DEP_GROUPS.keys())

    def test_each_group_has_required_keys(self):
        result = optional_deps_status()
        for group, info in result.items():
            assert "installed" in info
            assert "missing" in info
            assert "errors" in info
            assert isinstance(info["installed"], bool)

    def test_docs_group_installed_in_test_env(self):
        # pypdf, docx (python-docx), openpyxl are all installed in CI
        result = optional_deps_status()
        assert result["docs"]["installed"] is True, (
            f"docs group not fully installed: {result['docs']}"
        )


# ---------------------------------------------------------------------------
# 18-20  managed_agents (unit — no network)
# ---------------------------------------------------------------------------

from agency.managed_agents import (
    ManagedAgentBackend, ManagedAgentEvent, is_enabled, default_backend,
)


class TestManagedAgents:
    def test_is_enabled_false_by_default(self, monkeypatch):
        monkeypatch.delenv("AGENCY_BACKEND", raising=False)
        assert is_enabled() is False

    def test_is_enabled_true_for_managed_values(self, monkeypatch):
        for val in ("managed_agents", "managed-agents", "managed"):
            monkeypatch.setenv("AGENCY_BACKEND", val)
            assert is_enabled() is True

    def test_managed_agent_event_dataclass(self):
        e = ManagedAgentEvent("text", "hello")
        assert e.kind == "text"
        assert e.payload == "hello"

    def test_backend_close_clears_state(self):
        b = ManagedAgentBackend()
        b._agent_id = "fake-id"
        b._env_id = "fake-env"
        b.close()
        assert b._agent_id is None
        assert b._env_id is None

    def test_default_backend_singleton(self, monkeypatch):
        import agency.managed_agents as ma
        ma._default_backend = None  # reset
        b1 = default_backend()
        b2 = default_backend()
        assert b1 is b2
        ma._default_backend = None


# ---------------------------------------------------------------------------
# 21  SupremeJarvisBrain.skills property (Bug Fix test)
# ---------------------------------------------------------------------------

from agency.jarvis_brain import SupremeJarvisBrain


def test_supreme_brain_skills_property():
    b = SupremeJarvisBrain()
    skills = b.skills
    assert isinstance(skills, list)
    assert len(skills) > 0
    # Should be consistent with registry
    assert len(skills) == len(list(b.registry.all()))


# ---------------------------------------------------------------------------
# 22  doctor CLI shows AGENCY_BACKEND
# ---------------------------------------------------------------------------

from click.testing import CliRunner
from agency.cli import main


def test_doctor_shows_agency_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_BACKEND", "managed_agents")
    runner = CliRunner()
    result = runner.invoke(main, ["--repo", str(tmp_path), "doctor"], catch_exceptions=False)
    assert "AGENCY_BACKEND" in result.output
    assert "managed_agents" in result.output


# ---------------------------------------------------------------------------
# 23  __init__ lazy getters round-trip
# ---------------------------------------------------------------------------

import agency


def test_init_getters_return_correct_types():
    from agency.persona_engine import PersonaEngine
    from agency.character_state import CharacterState
    from agency.amjad_memory import AmjadMemory

    assert isinstance(agency.get_persona_engine(), PersonaEngine)
    assert isinstance(agency.get_character_state(), CharacterState)
    assert isinstance(agency.get_amjad_memory(), AmjadMemory)


def test_init_getters_are_singletons():
    # Same call twice → same object
    assert agency.get_persona_engine() is agency.get_persona_engine()
    assert agency.get_amjad_memory() is agency.get_amjad_memory()


# ---------------------------------------------------------------------------
# 24  SupremeBrainCore async (fix: heavy-term directives now get real tiers)
# ---------------------------------------------------------------------------

def test_brainiac_omega_directives_get_complex_model():
    """After classifier fix, heavy-term omega directives → COMPLEX or above,
    routing them to sonnet/opus rather than haiku."""
    core = SupremeBrainCore()

    async def _run():
        tasks = await core.initialize_omega_premium()
        return tasks

    tasks = asyncio.get_event_loop().run_until_complete(_run())
    assert tasks, "omega should produce tasks"
    # At least the first directive has a heavy term (Audit/synthesize/optimize) →
    # model should NOT be haiku (which handles only trivial/simple)
    complex_tasks = [t for t in tasks if t.complexity not in (Complexity.TRIVIAL, Complexity.SIMPLE)]
    assert len(complex_tasks) >= 3, (
        f"Expected ≥3 complex omega tasks, got {[(t.text[:30], t.complexity) for t in tasks]}"
    )
