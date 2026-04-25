"""FastAPI endpoint tests. Uses the TestClient — no network calls."""

from __future__ import annotations

from fastapi.testclient import TestClient

from agency.server import build_app


def test_api_skills_returns_count_and_list():
    app = build_app()
    client = TestClient(app)
    resp = client.get("/api/skills")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] > 0
    assert all({"slug", "name", "category", "description", "emoji"} <= set(s) for s in data["skills"][:3])


def test_api_plan_falls_back_to_keyword_match_without_api_key(monkeypatch):
    # Force _maybe_llm to return None so the planner takes the offline path.
    from agency import server as server_mod
    monkeypatch.setattr(server_mod, "_maybe_llm", lambda: None)

    app = build_app()
    client = TestClient(app)
    resp = client.post("/api/plan", json={"message": "build me a React component"})
    assert resp.status_code == 200
    data = resp.json()
    assert "skill" in data
    assert "slug" in data["skill"] and "name" in data["skill"]
    assert data["candidates"]


def test_api_run_returns_503_when_no_api_key(monkeypatch):
    from agency import server as server_mod
    from agency.llm import LLMError

    def _boom() -> None:
        raise LLMError("ANTHROPIC_API_KEY not set")
    monkeypatch.setattr(server_mod, "_require_llm", _boom)

    app = build_app()
    client = TestClient(app)
    resp = client.post("/api/run", json={"message": "anything"})
    assert resp.status_code == 503
    assert "ANTHROPIC_API_KEY" in resp.text


def test_api_run_stream_returns_503_when_no_api_key(monkeypatch):
    from agency import server as server_mod
    from agency.llm import LLMError

    def _boom() -> None:
        raise LLMError("ANTHROPIC_API_KEY not set")
    monkeypatch.setattr(server_mod, "_require_llm", _boom)

    app = build_app()
    client = TestClient(app)
    resp = client.post("/api/run/stream", json={"message": "anything"})
    assert resp.status_code == 503


def test_index_serves_html():
    app = build_app()
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Agency" in resp.text
    assert "/api/run/stream" in resp.text  # UI talks to the streaming endpoint


def test_version_endpoint():
    from agency import __version__
    app = build_app()
    client = TestClient(app)
    resp = client.get("/api/version")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "agency-runtime"
    assert data["version"] == __version__


def test_health_endpoint_status_ok_with_skills_and_features(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AGENCY_ENABLE_WEB_SEARCH", raising=False)
    monkeypatch.delenv("AGENCY_ENABLE_CODE_EXECUTION", raising=False)
    monkeypatch.delenv("AGENCY_ENABLE_COMPUTER_USE", raising=False)
    monkeypatch.delenv("AGENCY_ALLOW_SHELL", raising=False)
    monkeypatch.delenv("AGENCY_MCP_SERVERS", raising=False)
    monkeypatch.delenv("AGENCY_TASK_BUDGET", raising=False)

    app = build_app()
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["skills"]["count"] > 0
    assert "engineering" in data["skills"]["categories"]
    assert data["api_key_set"] is False
    assert data["features"]["web_search"] is False
    assert data["features"]["code_execution"] is False
    assert data["features"]["computer_use"] is False
    assert data["features"]["shell_allowed"] is False
    assert data["features"]["mcp_servers"] == 0
    assert data["features"]["task_budget_tokens"] is None
    # optional_deps shape
    assert "docs" in data["optional_deps"]
    assert "computer" in data["optional_deps"]
    assert "installed" in data["optional_deps"]["docs"]
    assert "missing" in data["optional_deps"]["docs"]


def test_health_endpoint_reflects_feature_flags(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    monkeypatch.setenv("AGENCY_ENABLE_WEB_SEARCH", "1")
    monkeypatch.setenv("AGENCY_ENABLE_CODE_EXECUTION", "yes")
    monkeypatch.setenv("AGENCY_ENABLE_COMPUTER_USE", "true")
    monkeypatch.setenv("AGENCY_ALLOW_SHELL", "1")
    monkeypatch.setenv("AGENCY_TASK_BUDGET", "50000")
    monkeypatch.setenv("AGENCY_MCP_SERVERS", '[{"type":"url","name":"a","url":"https://x"}]')

    app = build_app()
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["api_key_set"] is True
    assert data["features"]["web_search"] is True
    assert data["features"]["code_execution"] is True
    assert data["features"]["computer_use"] is True
    assert data["features"]["shell_allowed"] is True
    assert data["features"]["task_budget_tokens"] == 50000
    assert data["features"]["mcp_servers"] == 1


def test_health_endpoint_can_be_disabled(monkeypatch):
    """AGENCY_DISABLE_HEALTH=1 unregisters the route entirely."""
    monkeypatch.setenv("AGENCY_DISABLE_HEALTH", "1")
    app = build_app()
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 404


def test_health_endpoint_returns_200_even_when_internals_blow_up(monkeypatch):
    """The always-200 contract: a broken probe returns status='error', not HTTP 500."""
    from agency import server as server_mod

    def _boom() -> dict:
        raise RuntimeError("optional dep broke")
    monkeypatch.setattr(server_mod, "optional_deps_status", _boom)

    app = build_app()
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert "optional dep broke" in data["error"]
    assert data["version"]


def test_optional_deps_status_reports_errors_separately():
    """A non-ImportError at import time should land in errors, not missing."""
    import sys
    from agency.diagnostics import optional_deps_status, OPTIONAL_DEP_GROUPS

    # Build a fake import that raises a non-ImportError when imported.
    class _ExplodingFinder:
        def find_spec(self, name, *a, **k):
            if name == "pyautogui":
                # Return a loader that raises on exec.
                from importlib.machinery import ModuleSpec
                from importlib.abc import Loader

                class _Boom(Loader):
                    def create_module(self, spec): return None
                    def exec_module(self, module):
                        raise OSError("DISPLAY not set, cannot init pyautogui")
                return ModuleSpec(name, _Boom())
            return None

    # Drop any previously cached pyautogui import.
    sys.modules.pop("pyautogui", None)
    finder = _ExplodingFinder()
    sys.meta_path.insert(0, finder)
    try:
        result = optional_deps_status()
    finally:
        sys.meta_path.remove(finder)
        sys.modules.pop("pyautogui", None)

    assert "pyautogui" in result["computer"]["errors"]
    assert "DISPLAY not set" in result["computer"]["errors"]["pyautogui"]
    assert result["computer"]["installed"] is False
