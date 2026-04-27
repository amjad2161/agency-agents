"""Tests for agency.unified_bridge.UnifiedBridge."""

from __future__ import annotations

import pytest

from agency.unified_bridge import UnifiedBridge, SubsystemStatus


@pytest.fixture
def bridge():
    return UnifiedBridge()


def test_construct_bridge_brings_every_subsystem_online(bridge):
    assert bridge.self_learner is not None
    assert bridge.meta_reasoner is not None
    assert bridge.capability_evolver is not None
    assert bridge.context_manager is not None
    assert bridge.autonomous_loop is not None
    assert bridge.knowledge_expansion is not None
    assert bridge.multimodal is not None


def test_subsystem_names_returns_seven(bridge):
    names = bridge.subsystem_names()
    assert len(names) == 7
    assert set(names) == {
        "self_learner",
        "meta_reasoner",
        "capability_evolver",
        "context_manager",
        "autonomous_loop",
        "knowledge_expansion",
        "multimodal",
    }


def test_status_reports_all_subsystems_ok(bridge):
    status = bridge.status()
    assert status["ok"] is True
    assert status["count"] == 7
    assert {s["name"] for s in status["subsystems"]} == set(bridge.subsystem_names())
    for sub in status["subsystems"]:
        assert sub["ok"] is True


def test_status_each_subsystem_has_detail_dict(bridge):
    for sub in bridge.status()["subsystems"]:
        assert isinstance(sub["detail"], dict)


def test_self_learner_status_includes_lessons_and_path(bridge):
    sub = next(s for s in bridge.status()["subsystems"] if s["name"] == "self_learner")
    assert "lessons" in sub["detail"]
    assert "path" in sub["detail"]
    assert isinstance(sub["detail"]["lessons"], int)


def test_capability_evolver_status_includes_profiles(bridge):
    sub = next(s for s in bridge.status()["subsystems"] if s["name"] == "capability_evolver")
    assert "profiles" in sub["detail"]


def test_context_manager_status_includes_domains(bridge):
    sub = next(s for s in bridge.status()["subsystems"] if s["name"] == "context_manager")
    assert "domains" in sub["detail"]


def test_autonomous_loop_status_includes_running_flag(bridge):
    sub = next(s for s in bridge.status()["subsystems"] if s["name"] == "autonomous_loop")
    assert "running" in sub["detail"]
    assert isinstance(sub["detail"]["running"], bool)


def test_knowledge_expansion_status_includes_entries(bridge):
    sub = next(s for s in bridge.status()["subsystems"] if s["name"] == "knowledge_expansion")
    assert "entries" in sub["detail"]


def test_multimodal_status_includes_backends(bridge):
    sub = next(s for s in bridge.status()["subsystems"] if s["name"] == "multimodal")
    assert "backends" in sub["detail"]
    assert isinstance(sub["detail"]["backends"], list)


def test_meta_reasoner_status_includes_step_count(bridge):
    sub = next(s for s in bridge.status()["subsystems"] if s["name"] == "meta_reasoner")
    assert "steps_recorded" in sub["detail"]
    assert isinstance(sub["detail"]["steps_recorded"], int)


def test_repr_mentions_all_subsystems(bridge):
    text = repr(bridge)
    for name in bridge.subsystem_names():
        # repr uses CamelCase-ish but the bare names are present.
        assert name in text


def test_subsystem_status_to_dict_round_trip():
    s = SubsystemStatus("alpha", True, {"x": 1})
    d = s.to_dict()
    assert d == {"name": "alpha", "ok": True, "detail": {"x": 1}}


def test_status_contains_ok_count_subsystems_keys(bridge):
    status = bridge.status()
    assert set(status.keys()) == {"ok", "count", "subsystems"}


def test_get_unified_bridge_returns_bridge_instance():
    from agency import get_unified_bridge
    b = get_unified_bridge()
    assert hasattr(b, "status")
    snap = b.status()
    assert snap["ok"] is True


def test_get_unified_bridge_singleton():
    from agency import get_unified_bridge
    a = get_unified_bridge()
    b = get_unified_bridge()
    assert a is b
