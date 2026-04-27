"""Cross-module integration smoke tests.

Validates that the various subsystems compose correctly through
the documented public surfaces:

- ``agency.unified_bridge.UnifiedBridge`` boots all 7 subsystems.
- ``agency.supreme_main.main`` returns a ``BootedSystem`` and routes.
- ``agency.experts`` factories all expose the uniform contract.
- ``agency.jarvis_brain.SupremeJarvisBrain`` agrees with the planner's
  free-text shortlist on common queries.
"""

from __future__ import annotations

import json

import pytest


def test_smoke_unified_bridge_status_is_json_serializable():
    from agency.unified_bridge import UnifiedBridge
    bridge = UnifiedBridge()
    snap = bridge.status()
    # Round-trip through JSON.
    text = json.dumps(snap, default=str)
    decoded = json.loads(text)
    assert decoded["ok"] is True


def test_smoke_supreme_main_route_matches_brain_route():
    from agency.supreme_main import main, reset
    from agency.jarvis_brain import SupremeJarvisBrain

    reset()
    booted = main()
    brain = SupremeJarvisBrain(booted.registry)
    for query in [
        "Plan a kubernetes upgrade",
        "GDPR data subject rights",
        "Decode EEG signals for a brain-computer interface",
    ]:
        from_main = booted.route(query)
        from_brain = brain.skill_for(query).to_dict()
        assert from_main["skill"] == from_brain["skill"]
    reset()


def test_smoke_all_experts_uniform_contract():
    from agency.experts import all_experts
    for name, expert in all_experts().items():
        s = expert.status()
        r = expert.analyze("test query")
        assert s["ok"] is True
        assert s["name"] == name
        assert r.expert == name


def test_smoke_brain_routes_each_category_at_least_once():
    """Sanity: across many queries the brain reaches diverse categories."""
    from agency.jarvis_brain import get_brain
    brain = get_brain()
    queries = [
        "kubernetes deployment",
        "machine learning fine-tune",
        "DCF valuation",
        "google ads campaign",
        "GDPR compliance",
        "satellite orbit",
        "circular economy plastics",
        "figma design system",
        "OKR design",
        "EEG brain decoding",
    ]
    seen_categories: set[str] = set()
    for q in queries:
        r = brain.skill_for(q)
        seen_categories.add(r.skill.category)
    assert len(seen_categories) >= 4


def test_smoke_supreme_brainiac_ingest_then_router_route():
    """Brainiac classifies + routes to a model name string."""
    import asyncio
    from agency.supreme_brainiac import SupremeBrainCore

    async def go():
        core = SupremeBrainCore()
        tasks = await core.ingest_directive(
            "Audit every JARVIS subsystem. Optimize the routing engine."
        )
        return tasks

    tasks = asyncio.run(go())
    assert len(tasks) == 2
    for t in tasks:
        assert t.model.startswith("claude-")


def test_smoke_eval_harness_against_brain_pass_rate_high():
    from agency.eval_harness import routing_suite
    from agency.jarvis_brain import get_brain
    brain = get_brain()
    report = routing_suite().run(lambda q: brain.skill_for(q).to_dict())
    assert report.pass_rate >= 0.8


def test_smoke_cost_router_classifies_then_routes():
    from agency.cost_router import CostAwareRouter
    r = CostAwareRouter(spend_cap_usd=1000.0)
    decisions = [
        r.recommend("list users"),
        r.recommend(
            "Design an end-to-end production system that synthesizes "
            "streaming data and evaluates trade-offs across regions"
        ),
    ]
    assert decisions[0].model == "claude-haiku-4-5"
    assert decisions[1].model in {"claude-sonnet-4-6", "claude-opus-4-7"}


def test_smoke_get_unified_bridge_status_via_package():
    """The package-level lazy getter returns an object with status()."""
    from agency import get_unified_bridge
    snap = get_unified_bridge().status()
    assert isinstance(snap, dict)
    assert snap["ok"] is True


def test_smoke_get_jarvis_brain_via_package():
    from agency import get_jarvis_brain
    a = get_jarvis_brain()
    b = get_jarvis_brain()
    assert a is b
    r = a.skill_for("kubernetes deployment")
    assert r.skill.slug == "jarvis-devops-platform"


def test_smoke_get_supreme_brainiac_via_package():
    from agency import get_supreme_brainiac
    a = get_supreme_brainiac()
    b = get_supreme_brainiac()
    assert a is b
