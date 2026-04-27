"""Tests for agency.cost_router."""

from __future__ import annotations

import pytest

from agency.cost_router import (
    CostAwareRouter,
    CostBudgetExceeded,
    DEFAULT_TIERS,
    MIN_CAPABILITY,
    ModelTier,
    RouteDecision,
)
from agency.supreme_brainiac import Complexity


# ---------------------------------------------------------------------------
# ModelTier
# ---------------------------------------------------------------------------


def test_default_tiers_ordered_by_cost():
    costs = [t.estimate_cost(1000, 500) for t in DEFAULT_TIERS]
    assert costs == sorted(costs)


def test_min_capability_covers_every_complexity():
    for c in Complexity:
        assert c in MIN_CAPABILITY


def test_estimate_cost_arithmetic():
    tier = ModelTier("foo", input_per_mtok=1.0, output_per_mtok=2.0, capability_score=0.8)
    # 1M input @ $1, 1M output @ $2 → $3
    assert tier.estimate_cost(1_000_000, 1_000_000) == pytest.approx(3.0, abs=1e-6)


def test_estimate_cost_zero_tokens_is_zero():
    tier = ModelTier("foo", input_per_mtok=10, output_per_mtok=10, capability_score=1.0)
    assert tier.estimate_cost(0, 0) == 0


# ---------------------------------------------------------------------------
# CostAwareRouter — selection logic
# ---------------------------------------------------------------------------


def test_router_picks_haiku_for_trivial():
    r = CostAwareRouter()
    decision = r.recommend(
        "list users", expected_input_tokens=200, expected_output_tokens=80,
        force_complexity=Complexity.TRIVIAL,
    )
    assert decision.model == "claude-haiku-4-5"


def test_router_picks_opus_for_very_complex():
    r = CostAwareRouter()
    decision = r.recommend("anything", force_complexity=Complexity.VERY_COMPLEX)
    assert decision.model == "claude-opus-4-7"


def test_router_decision_includes_fallback_chain():
    r = CostAwareRouter()
    decision = r.recommend("anything", force_complexity=Complexity.MEDIUM)
    assert decision.fallback_chain  # non-empty
    # Cheapest first chosen → fallback chain is the rest, also sorted.
    assert all(isinstance(m, str) for m in decision.fallback_chain)


def test_router_decision_has_rationale():
    r = CostAwareRouter()
    d = r.recommend("anything", force_complexity=Complexity.SIMPLE)
    assert "complexity=simple" in d.rationale
    assert "cheapest eligible" in d.rationale


def test_route_decision_to_dict():
    r = CostAwareRouter()
    d = r.recommend("anything", force_complexity=Complexity.MEDIUM)
    out = d.to_dict()
    for k in ("model", "complexity", "estimated_cost", "rationale", "fallback_chain"):
        assert k in out


# ---------------------------------------------------------------------------
# Budget tracking
# ---------------------------------------------------------------------------


def test_record_actual_spend_accumulates():
    r = CostAwareRouter()
    r.record_actual_spend(0.5)
    r.record_actual_spend(0.25)
    assert r.spend_so_far == pytest.approx(0.75)


def test_record_actual_spend_negative_raises():
    r = CostAwareRouter()
    with pytest.raises(ValueError):
        r.record_actual_spend(-1.0)


def test_reset_spend_zeros_counter():
    r = CostAwareRouter()
    r.record_actual_spend(1.0)
    r.reset_spend()
    assert r.spend_so_far == 0.0


def test_remaining_budget_none_when_no_cap():
    r = CostAwareRouter()
    assert r.remaining_budget is None


def test_remaining_budget_subtracts_spend():
    r = CostAwareRouter(spend_cap_usd=2.0)
    r.record_actual_spend(0.5)
    assert r.remaining_budget == pytest.approx(1.5)


def test_remaining_budget_floored_at_zero():
    r = CostAwareRouter(spend_cap_usd=1.0)
    r.record_actual_spend(2.0)
    assert r.remaining_budget == 0.0


# ---------------------------------------------------------------------------
# Cap enforcement
# ---------------------------------------------------------------------------


def test_recommend_under_cap_succeeds():
    r = CostAwareRouter(spend_cap_usd=10.0)
    d = r.recommend("simple text", force_complexity=Complexity.TRIVIAL,
                    expected_input_tokens=100, expected_output_tokens=100)
    assert d.estimated_cost < 10.0


def test_recommend_over_cap_raises():
    r = CostAwareRouter(spend_cap_usd=0.000_001)  # absurdly small
    with pytest.raises(CostBudgetExceeded):
        r.recommend("anything", force_complexity=Complexity.VERY_COMPLEX,
                    expected_input_tokens=1_000_000, expected_output_tokens=1_000_000)


# ---------------------------------------------------------------------------
# Forced complexity respects MIN_CAPABILITY
# ---------------------------------------------------------------------------


def test_recommend_uses_classifier_by_default():
    r = CostAwareRouter()
    d = r.recommend("list users")
    # Trivial → haiku
    assert d.model == "claude-haiku-4-5"


def test_recommend_complex_text_picks_capable_model():
    r = CostAwareRouter()
    d = r.recommend(
        "Design a fault-tolerant distributed trading system architecture and "
        "evaluate trade-offs"
    )
    # Either sonnet or opus, not haiku.
    assert d.model in {"claude-sonnet-4-6", "claude-opus-4-7"}
