"""FastAPI endpoint tests. Uses the TestClient — no network calls."""

from __future__ import annotations

import os

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agency.server import build_app


# /api/trust set writes directly to os.environ so the change is
# visible to subsequent in-process calls. monkeypatch can't track
# that write — so without this fixture, AGENCY_TRUST_MODE would leak
# from one test_server case into test_tools and flip its expectations
# on web_fetch / shell. Snapshot + restore at the boundary.
@pytest.fixture(autouse=True)
def _isolate_trust_env():
    keys = ("AGENCY_TRUST_MODE", "AGENCY_TRUST_CONF",
            "AGENCY_LESSONS", "AGENCY_PROFILE", "AGENCY_VECTOR_DB")
    snap = {k: os.environ.get(k) for k in keys}
    yield
    for k, v in snap.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_api_skills_returns_count_and_list():
    app = build_app()
    client = TestClient(app)
    resp = client.get("/api/skills")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] > 0
    assert all({"slug", "name", "category", "description", "emoji"} <= set(s) for s in data["skills"][:3])


def test_api_skills_graph_returns_categories_and_hubs():
    app = build_app()
    client = TestClient(app)
    resp = client.get("/api/skills/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_skills"] > 0
    assert isinstance(data["categories"], list) and data["categories"]
    cat = data["categories"][0]
    assert {"name", "count", "top_slugs"} <= set(cat)
    assert isinstance(cat["top_slugs"], list)
    # delegation hubs: with the current registry this should pick up
    # at least jarvis-core and elder-sage.
    hub_slugs = [h["slug"] for h in data["delegation_hubs"]]
    assert any("core" in s or "elder" in s or "omega" in s for s in hub_slugs)


def test_api_lessons_get_returns_path_and_text(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_LESSONS", str(tmp_path / "lessons.md"))
    (tmp_path / "lessons.md").write_text("# Lessons\n\n## a\n\nx", encoding="utf-8")
    app = build_app()
    client = TestClient(app)
    r = client.get("/api/lessons")
    assert r.status_code == 200
    d = r.json()
    assert d["exists"] is True
    assert "Lessons" in d["text"]


def test_api_lessons_post_appends(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_LESSONS", str(tmp_path / "lessons.md"))
    app = build_app()
    client = TestClient(app)
    r = client.post("/api/lessons", json={"text": "ship the lessons feature"})
    assert r.status_code == 200
    body = (tmp_path / "lessons.md").read_text(encoding="utf-8")
    assert "ship the lessons feature" in body
    assert "## " in body and "UTC" in body


def test_api_lessons_post_rejects_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_LESSONS", str(tmp_path / "lessons.md"))
    app = build_app()
    client = TestClient(app)
    r = client.post("/api/lessons", json={"text": "   "})
    assert r.status_code == 400


def test_api_trust_get_reports_active_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_TRUST_CONF", str(tmp_path / "trust.conf"))
    monkeypatch.setenv("AGENCY_TRUST_MODE", "yolo")
    app = build_app()
    client = TestClient(app)
    r = client.get("/api/trust")
    assert r.status_code == 200
    d = r.json()
    assert d["mode"] == "yolo"
    assert "block_metadata_fetches" in d["gate"]


def test_api_trust_post_persists_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_TRUST_CONF", str(tmp_path / "trust.conf"))
    monkeypatch.delenv("AGENCY_TRUST_MODE", raising=False)
    app = build_app()
    client = TestClient(app)
    r = client.post("/api/trust", json={"mode": "on-my-machine"})
    assert r.status_code == 200
    assert r.json()["mode"] == "on-my-machine"
    contents = (tmp_path / "trust.conf").read_text(encoding="utf-8")
    assert "on-my-machine" in contents


def test_api_trust_post_rejects_unknown(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_TRUST_CONF", str(tmp_path / "trust.conf"))
    app = build_app()
    client = TestClient(app)
    r = client.post("/api/trust", json={"mode": "supreme"})
    assert r.status_code == 400


def test_api_sessions_returns_listing(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    sess_dir = fake_home / ".agency" / "sessions"
    sess_dir.mkdir(parents=True)
    (sess_dir / "abc.jsonl").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    app = build_app()
    client = TestClient(app)
    r = client.get("/api/sessions")
    assert r.status_code == 200
    d = r.json()
    assert any(s["id"] == "abc" for s in d["sessions"])


def test_api_profile_get(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_PROFILE", str(tmp_path / "p.md"))
    (tmp_path / "p.md").write_text("# About me\n\n- Name: Test", encoding="utf-8")
    app = build_app()
    client = TestClient(app)
    r = client.get("/api/profile")
    assert r.status_code == 200
    d = r.json()
    assert d["exists"] is True
    assert "About me" in d["text"]


def test_api_profile_post_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_PROFILE", str(tmp_path / "p.md"))
    app = build_app()
    client = TestClient(app)
    r = client.post("/api/profile", json={"text": "# fresh"})
    assert r.status_code == 200
    assert r.json()["saved"] is True
    assert (tmp_path / "p.md").read_text() == "# fresh"


def test_api_profile_post_empty_deletes(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_PROFILE", str(tmp_path / "p.md"))
    (tmp_path / "p.md").write_text("# old", encoding="utf-8")
    app = build_app()
    client = TestClient(app)
    r = client.post("/api/profile", json={"text": "   "})
    assert r.status_code == 200
    assert r.json()["deleted"] is True
    assert not (tmp_path / "p.md").exists()


def test_api_mcp_returns_unconfigured_by_default(monkeypatch):
    monkeypatch.delenv("AGENCY_MCP_SERVERS", raising=False)
    app = build_app()
    client = TestClient(app)
    r = client.get("/api/mcp")
    assert r.status_code == 200
    d = r.json()
    assert d["configured"] is False
    assert d["servers"] == []


def test_api_mcp_returns_parsed_list(monkeypatch):
    import json as _json
    monkeypatch.setenv(
        "AGENCY_MCP_SERVERS",
        _json.dumps([
            {"type": "url", "name": "github",
             "url": "https://api.githubcopilot.com/mcp/",
             "authorization": "Bearer SECRETSHOULDREDACT"},
        ]),
    )
    app = build_app()
    client = TestClient(app)
    r = client.get("/api/mcp")
    assert r.status_code == 200
    d = r.json()
    assert d["configured"] is True
    assert len(d["servers"]) == 1
    s = d["servers"][0]
    assert s["name"] == "github"
    # secret keys must be redacted
    assert s.get("authorization") == "(redacted)"
    assert "SECRETSHOULDREDACT" not in _json.dumps(d)


def test_api_mcp_handles_bad_json(monkeypatch):
    monkeypatch.setenv("AGENCY_MCP_SERVERS", "{not json")
    app = build_app()
    client = TestClient(app)
    r = client.get("/api/mcp")
    assert r.status_code == 200
    d = r.json()
    assert "parse_error" in d


def test_api_session_export_renders_markdown(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    sess_dir = fake_home / ".agency" / "sessions"
    sess_dir.mkdir(parents=True)
    (sess_dir / "abc.jsonl").write_text(
        '{"role":"user","content":"hello"}\n'
        '{"role":"assistant","content":"world"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    app = build_app()
    client = TestClient(app)
    r = client.get("/api/sessions/abc/export")
    assert r.status_code == 200
    md = r.json()["markdown"]
    assert "## user" in md
    assert "hello" in md
    assert "## assistant" in md
    assert "world" in md


def test_api_session_export_404_for_missing(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / ".agency" / "sessions").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    app = build_app()
    client = TestClient(app)
    r = client.get("/api/sessions/nope/export")
    assert r.status_code == 404


def test_api_session_export_rejects_path_traversal():
    app = build_app()
    client = TestClient(app)
    r = client.get("/api/sessions/..%2Fetc/export")
    # FastAPI normalizes %2F so we may see 400 directly; either way not 200.
    assert r.status_code != 200


def test_api_dashboard_returns_full_snapshot(tmp_path, monkeypatch):
    """One-shot snapshot endpoint for the HUD home view."""
    monkeypatch.setenv("AGENCY_LESSONS", str(tmp_path / "lessons.md"))
    monkeypatch.setenv("AGENCY_PROFILE", str(tmp_path / "profile.md"))
    monkeypatch.setenv("AGENCY_TRUST_CONF", str(tmp_path / "trust.conf"))
    monkeypatch.delenv("AGENCY_TRUST_MODE", raising=False)
    (tmp_path / "lessons.md").write_text("# Lessons\n\n## a\n\nfirst lesson",
                                           encoding="utf-8")
    (tmp_path / "profile.md").write_text("- Name: tester", encoding="utf-8")

    fake_home = tmp_path / "home"
    sess_dir = fake_home / ".agency" / "sessions"
    sess_dir.mkdir(parents=True)
    (sess_dir / "abc.jsonl").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    app = build_app()
    client = TestClient(app)
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    d = r.json()

    assert d["trust_mode"] == "off"  # default
    assert d["trust_yolo_active"] is False
    assert d["skills_total"] > 0
    assert isinstance(d["skills_categories"], list)
    assert d["skills_categories"][0].keys() >= {"name", "count"}
    assert d["profile_present"] is True
    assert d["profile_size_bytes"] > 0
    assert d["lessons_present"] is True
    assert any(s["id"] == "abc" for s in d["sessions_recent"])
    assert d["mcp_servers_count"] == 0
    assert isinstance(d["user_tools"], list)


def test_api_dashboard_handles_missing_files(tmp_path, monkeypatch):
    """Dashboard must work even with no profile/lessons/sessions present."""
    monkeypatch.setenv("AGENCY_LESSONS", str(tmp_path / "lessons.md"))
    monkeypatch.setenv("AGENCY_PROFILE", str(tmp_path / "profile.md"))
    monkeypatch.delenv("AGENCY_TRUST_MODE", raising=False)

    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    app = build_app()
    client = TestClient(app)
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    d = r.json()
    assert d["profile_present"] is False
    assert d["lessons_present"] is False
    assert d["sessions_recent"] == []
    assert d["user_tools"] == []


def test_api_dashboard_reflects_trust_yolo(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_TRUST_CONF", str(tmp_path / "trust.conf"))
    monkeypatch.setenv("AGENCY_TRUST_MODE", "yolo")
    app = build_app()
    client = TestClient(app)
    r = client.get("/api/dashboard")
    d = r.json()
    assert d["trust_mode"] == "yolo"
    assert d["trust_yolo_active"] is True


def test_index_serves_chat_html_from_disk_when_present(tmp_path, monkeypatch):
    """If runtime/agency/static/chat.html exists, GET / serves it."""
    app = build_app()
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.text
    # The new GRAVIS HUD has an obvious marker not present in the old
    # _CHAT_HTML fallback.
    assert "JARVIS" in body or "Agency Runtime" in body


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
    from agency.diagnostics import optional_deps_status

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
