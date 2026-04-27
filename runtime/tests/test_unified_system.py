"""End-to-end smoke tests for the unified JARVIS runtime."""

from __future__ import annotations

from agency import (
    get_aios_bridge,
    get_evals,
    get_llm_router,
    get_semantic_router,
    get_tool_registry,
    get_tracer_singleton,
    get_unified_bridge,
    get_vector_store,
)
from agency.tool_registry import get_registry


def test_full_pipeline() -> None:
    bridge = get_unified_bridge()
    out = bridge.process("write a python hello world")
    assert isinstance(out, dict)
    assert "response" in out
    assert "domain" in out
    assert "memory_id" in out
    assert "latency_ms" in out
    assert "tokens_used" in out
    assert "confidence" in out
    assert out["latency_ms"] >= 0


def test_all_subsystems_status() -> None:
    bridge = get_unified_bridge()
    status = bridge.status()
    assert isinstance(status, dict)
    assert "subsystems" in status
    expected = {
        "llm_router", "semantic_router", "memory", "tool_registry",
        "tracer", "eval_suite", "console", "self_learner",
        "meta_reasoner", "context_manager", "aios_bridge",
    }
    assert expected <= set(status["subsystems"].keys())
    for name, info in status["subsystems"].items():
        assert "status" in info
        assert info["status"] in {"green", "yellow", "red"}


def test_semantic_routing_to_medical() -> None:
    router = get_semantic_router()
    route, _score = router.route("symptoms of high blood pressure")
    assert route.name == "medical"


def test_memory_persistence_round_trip() -> None:
    memory = get_vector_store()
    eid = memory.store("the mitochondria is the powerhouse of the cell")
    assert isinstance(eid, str) and eid
    results = memory.search("mitochondria")
    assert results, "expected memory.search to recall stored entry"


def test_tool_execution_via_registry() -> None:
    registry = get_tool_registry()

    def double(n: int) -> int:
        return n * 2

    registry.register(double, name="unified_double")
    assert registry.execute("unified_double", n=21) == 42


def test_singletons_are_consistent() -> None:
    assert get_unified_bridge() is get_unified_bridge()
    assert get_llm_router() is get_llm_router()
    assert get_tracer_singleton() is get_tracer_singleton()
    assert get_aios_bridge() is get_aios_bridge()
    assert get_evals() is get_evals()


def test_bridge_uses_singleton_subsystems() -> None:
    bridge = get_unified_bridge()
    assert bridge.tool_registry is get_tool_registry()
    assert bridge.memory is get_vector_store()
    assert bridge.semantic_router is get_semantic_router()


def test_bridge_status_lists_thirteen_subsystems() -> None:
    bridge = get_unified_bridge()
    subsystems = bridge.status()["subsystems"]
    assert len(subsystems) >= 13


def test_registry_alias_helper() -> None:
    """Confirm helper resolves singleton."""
    assert get_registry() is get_tool_registry()
