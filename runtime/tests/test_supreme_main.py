"""Tests for agency.supreme_main."""

from __future__ import annotations

import pytest

from agency.supreme_main import BootedSystem, main, reset


@pytest.fixture(autouse=True)
def _reset_after():
    yield
    reset()


def test_main_returns_booted_system():
    sys = main()
    assert isinstance(sys, BootedSystem)
    assert sys.bridge is not None
    assert sys.brain is not None
    assert sys.registry is not None
    assert isinstance(sys.experts, dict)


def test_main_is_idempotent():
    a = main()
    b = main()
    assert a is b


def test_main_reload_returns_fresh_instance():
    a = main()
    b = main(reload=True)
    assert a is not b


def test_status_reports_skills_loaded():
    sys = main()
    s = sys.status()
    assert s["skills_loaded"] > 200
    assert s["categories"] >= 10


def test_status_reports_experts_status():
    sys = main()
    s = sys.status()
    assert len(s["experts"]) == 8
    for name, expert_status in s["experts"].items():
        assert expert_status["ok"] is True
        assert expert_status["name"] == name


def test_status_aggregate_ok_true_with_no_errors():
    sys = main()
    assert sys.status()["ok"] is True


def test_route_returns_dict_for_request():
    sys = main()
    out = sys.route("Plan a kubernetes deployment")
    assert "skill" in out
    assert "score" in out
    assert "candidates" in out


def test_route_picks_devops_for_kubernetes():
    sys = main()
    out = sys.route("Kubernetes terraform helm pipeline")
    assert out["skill"] == "jarvis-devops-platform"


def test_boot_log_contains_subsystems():
    sys = main()
    log_blob = "\n".join(sys.boot_log)
    assert "skills loaded" in log_blob
    assert "jarvis_brain" in log_blob
    assert "unified_bridge" in log_blob
    assert "experts" in log_blob


def test_reset_clears_cached_boot():
    a = main()
    reset()
    b = main()
    assert a is not b
