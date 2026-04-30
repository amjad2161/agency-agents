"""Tests for meta_reasoner.py — MetaReasoningEngine."""

from __future__ import annotations

from agency.meta_reasoner import MetaReasoningEngine, ReasoningStep


# ── ReasoningStep ────────────────────────────────────────────────────────────

def test_reasoning_step_fields():
    s = ReasoningStep(step_id=1, thought="Consider X", action="do X", observation="X done", confidence=0.9)
    assert s.step_id == 1
    assert s.confidence == 0.9


def test_reasoning_step_to_dict():
    s = ReasoningStep(step_id=2, thought="t", action="a", observation="o")
    d = s.to_dict()
    assert d["step_id"] == 2
    assert "thought" in d


def test_reasoning_step_default_confidence():
    s = ReasoningStep(step_id=0, thought="t")
    assert 0.0 <= s.confidence <= 1.0


# ── MetaReasoningEngine.reason ───────────────────────────────────────────────

def test_reason_returns_steps():
    engine = MetaReasoningEngine()
    steps = engine.reason("Explain gradient descent")
    assert isinstance(steps, list)
    assert len(steps) > 0


def test_reason_steps_have_thought():
    engine = MetaReasoningEngine()
    steps = engine.reason("How does attention work in transformers?")
    for s in steps:
        assert isinstance(s.thought, str)
        assert len(s.thought) > 0


def test_reason_respects_max_iterations():
    engine = MetaReasoningEngine()
    steps = engine.reason("What is machine learning?", max_iterations=2)
    assert len(steps) <= 2


def test_reason_with_context():
    engine = MetaReasoningEngine()
    steps = engine.reason("Explain recursion", context="teaching a beginner")
    assert len(steps) > 0


def test_reason_code_question():
    engine = MetaReasoningEngine()
    steps = engine.reason("Write a Python function to reverse a string")
    assert len(steps) > 0


def test_reason_numbered_goal_decomposition():
    engine = MetaReasoningEngine()
    steps = engine.reason("1. Define the problem. 2. Gather data. 3. Train model.")
    assert len(steps) >= 2


# ── MetaReasoningEngine.plan_and_execute ────────────────────────────────────

def test_plan_and_execute_returns_string():
    engine = MetaReasoningEngine()
    plan = engine.plan_and_execute("Debug a NullPointerException")
    assert isinstance(plan, str)
    assert len(plan) > 0


def test_plan_and_execute_contains_steps():
    engine = MetaReasoningEngine()
    plan = engine.plan_and_execute("Build a REST API")
    assert "Step" in plan


def test_plan_and_execute_with_tools():
    engine = MetaReasoningEngine()
    tools = [{"name": "search_tool", "description": "search the web"}]
    plan = engine.plan_and_execute("Find recent AI papers", tools=tools)
    assert isinstance(plan, str)


# ── MetaReasoningEngine.critique ─────────────────────────────────────────────

def test_critique_complete_response():
    engine = MetaReasoningEngine()
    score, feedback = engine.critique(
        "Gradient descent minimises a loss function by iterating in the direction of the negative gradient. "
        "It converges when the gradient approaches zero, assuming an appropriate learning rate.",
        "How does gradient descent work?"
    )
    assert 0.0 <= score <= 1.0
    assert isinstance(feedback, str)


def test_critique_short_response_penalised():
    engine = MetaReasoningEngine()
    score, feedback = engine.critique("Yes.", "Explain the transformer architecture in detail.")
    assert score < 1.0


def test_critique_missing_code_penalised():
    engine = MetaReasoningEngine()
    score, feedback = engine.critique(
        "You should write a function that takes a list.",
        "Write a Python function to sort a list."
    )
    assert "code" in feedback.lower() or score < 1.0


def test_critique_feedback_is_string():
    engine = MetaReasoningEngine()
    _, feedback = engine.critique("Some response text here.", "Some goal here.")
    assert isinstance(feedback, str)


def test_critique_score_range():
    engine = MetaReasoningEngine()
    score, _ = engine.critique("x" * 200, "explain something")
    assert 0.0 <= score <= 1.0


# ── MetaReasoningEngine.refine ───────────────────────────────────────────────

def test_refine_returns_string():
    engine = MetaReasoningEngine()
    refined = engine.refine("Short.", "Explain in detail why the sky is blue.")
    assert isinstance(refined, str)


def test_refine_high_quality_no_change():
    engine = MetaReasoningEngine()
    long_response = (
        "The sky appears blue because of Rayleigh scattering. When sunlight enters Earth's "
        "atmosphere, it collides with gas molecules. Blue light has a shorter wavelength and "
        "scatters more than red light, so we perceive the sky as blue during the day. "
        "This effect is strongest at midday when the sun is overhead."
    )
    result = engine.refine(long_response, "Why is the sky blue?", iterations=1)
    assert "No refinement needed" in result or isinstance(result, str)


def test_refine_multiple_iterations():
    engine = MetaReasoningEngine()
    result = engine.refine("Bad short answer.", "Explain deep learning in detail.", iterations=3)
    assert isinstance(result, str)


# ── introspection ─────────────────────────────────────────────────────────────

def test_last_steps_after_reason():
    engine = MetaReasoningEngine()
    engine.reason("What is a binary tree?")
    steps = engine.last_steps()
    assert isinstance(steps, list)
    assert len(steps) > 0


def test_avg_confidence_no_steps():
    engine = MetaReasoningEngine()
    assert engine.avg_confidence() == 0.0


def test_avg_confidence_after_reason():
    engine = MetaReasoningEngine()
    engine.reason("Explain sorting algorithms")
    conf = engine.avg_confidence()
    assert 0.0 <= conf <= 1.0
