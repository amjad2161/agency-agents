"""Tests for agency.supreme_brainiac.SupremeBrainCore."""

from __future__ import annotations

import asyncio

import pytest

from agency.supreme_brainiac import (
    Complexity,
    ComplexityClassifier,
    ModelRouter,
    ModelRoute,
    SupremeBrainCore,
    Task,
    TaskStatus,
    CoreStatus,
    EVOLUTION_INCREMENT,
    get_brainiac,
)


# ---------------------------------------------------------------------------
# ComplexityClassifier
# ---------------------------------------------------------------------------


@pytest.fixture
def classifier():
    return ComplexityClassifier()


def test_classifier_empty_text_is_trivial(classifier):
    assert classifier.classify("") == Complexity.TRIVIAL
    assert classifier.classify("   ") == Complexity.TRIVIAL


def test_classifier_short_light_query(classifier):
    assert classifier.classify("list users") == Complexity.TRIVIAL


def test_classifier_simple_short_query(classifier):
    assert classifier.classify("plot the sales numbers") in {
        Complexity.SIMPLE,
        Complexity.TRIVIAL,
    }


def test_classifier_medium_query(classifier):
    text = (
        "Pull last quarter sales numbers by region and contrast them with the "
        "previous fiscal year then plot the variance broken down by month and product line"
    )
    assert classifier.classify(text) in {Complexity.MEDIUM, Complexity.COMPLEX}


def test_classifier_very_complex_text(classifier):
    text = (
        "Design and architect an end-to-end production system that "
        "synthesizes streaming data, evaluates trade-offs across "
        "multiple deployment strategies, and optimizes for latency. "
        "Compare against existing frameworks."
    )
    assert classifier.classify(text) == Complexity.VERY_COMPLEX


# ---------------------------------------------------------------------------
# ModelRouter
# ---------------------------------------------------------------------------


def test_router_defaults_haiku_for_trivial():
    r = ModelRouter().route(Complexity.TRIVIAL)
    assert r.model == "claude-haiku-4-5"
    assert "complexity=trivial" in r.rationale


def test_router_defaults_opus_for_very_complex():
    r = ModelRouter().route(Complexity.VERY_COMPLEX)
    assert r.model == "claude-opus-4-7"


def test_router_defaults_sonnet_for_medium():
    r = ModelRouter().route(Complexity.MEDIUM)
    assert r.model == "claude-sonnet-4-6"


def test_router_overrides_apply():
    r = ModelRouter(overrides={Complexity.TRIVIAL: "claude-haiku-future"})
    assert r.route(Complexity.TRIVIAL).model == "claude-haiku-future"


def test_router_model_for_text_uses_classifier():
    r = ModelRouter()
    out = r.model_for_text("list users")
    assert out.model == "claude-haiku-4-5"


def test_evolution_increment_is_complete():
    for c in Complexity:
        assert c in EVOLUTION_INCREMENT
        assert EVOLUTION_INCREMENT[c] > 0


# ---------------------------------------------------------------------------
# Task dataclass
# ---------------------------------------------------------------------------


def test_task_to_dict_contains_keys():
    t = Task(task_id="abc", text="hi", complexity=Complexity.SIMPLE, model="m")
    d = t.to_dict()
    for k in ("task_id", "text", "complexity", "model", "status", "cycles"):
        assert k in d
    assert d["complexity"] == "simple"


# ---------------------------------------------------------------------------
# SupremeBrainCore — async behavior
# ---------------------------------------------------------------------------


def test_core_starts_idle():
    core = SupremeBrainCore()
    assert core.status == CoreStatus.IDLE
    assert core.evolution_score == 0.0
    assert core.tasks == []


def test_ingest_directive_creates_tasks():
    core = SupremeBrainCore()

    async def go():
        return await core.ingest_directive("Audit the system. Optimize the routing.")

    tasks = asyncio.run(go())
    assert len(tasks) == 2
    assert core.status == CoreStatus.INITIALIZED
    for t in tasks:
        assert t.status == TaskStatus.QUEUED
        assert t.model


def test_ingest_directive_empty_returns_no_tasks():
    core = SupremeBrainCore()
    out = asyncio.run(core.ingest_directive("   "))
    assert out == []
    assert core.status == CoreStatus.IDLE


def test_run_cycles_marks_tasks_done():
    core = SupremeBrainCore()

    async def go():
        await core.ingest_directive("Audit system. Synthesize cross-domain insights.")
        return await core.run_recursive_cycles(cycles=1)

    snap = asyncio.run(go())
    assert snap["task_status_breakdown"]["done"] == 2
    assert core.evolution_score > 0


def test_run_cycles_increments_evolution_score():
    core = SupremeBrainCore()

    async def go():
        await core.ingest_directive("Optimize routing. Synthesize knowledge. Audit subsystems.")
        await core.run_recursive_cycles(cycles=1)
        first = core.evolution_score
        await core.ingest_directive("Add more directives. Run again.")
        await core.run_recursive_cycles(cycles=1)
        return first, core.evolution_score

    first, second = asyncio.run(go())
    assert second > first


def test_run_cycles_with_executor():
    core = SupremeBrainCore()

    async def exec_fn(task):
        return f"executed:{task.task_id}"

    async def go():
        await core.ingest_directive("First directive. Second directive.")
        return await core.run_recursive_cycles(cycles=1, executor=exec_fn)

    asyncio.run(go())
    for t in core.tasks:
        assert t.result is not None
        assert "executed:" in t.result


def test_run_cycles_zero_raises():
    core = SupremeBrainCore()

    async def go():
        return await core.run_recursive_cycles(cycles=0)

    with pytest.raises(ValueError):
        asyncio.run(go())


def test_initialize_omega_premium_seeds_five_tasks():
    core = SupremeBrainCore()

    async def go():
        return await core.initialize_omega_premium()

    tasks = asyncio.run(go())
    assert len(tasks) == 5
    assert len(core.tasks) == 5


def test_evolution_score_capped_at_100():
    core = SupremeBrainCore()
    # Manually push score near cap.
    core._evolution_score = 99.5  # type: ignore[attr-defined]

    async def go():
        await core.ingest_directive("Audit system. Synthesize. Optimize.")
        return await core.run_recursive_cycles(cycles=5)

    asyncio.run(go())
    assert core.evolution_score <= core.EVOLUTION_CAP


def test_get_brainiac_singleton():
    a = get_brainiac()
    b = get_brainiac()
    assert a is b


def test_snapshot_breakdown_keys():
    core = SupremeBrainCore()
    snap = core.snapshot()
    for k in ("queued", "running", "done", "skipped", "error"):
        assert k in snap["task_status_breakdown"]


def test_task_by_id():
    core = SupremeBrainCore()

    async def go():
        return await core.ingest_directive("First.")

    tasks = asyncio.run(go())
    assert core.task_by_id(tasks[0].task_id) is tasks[0]
    assert core.task_by_id("nonexistent") is None
