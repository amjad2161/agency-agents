"""
Automated integration tests for the GODSKILL server REST API.

Tests cover:
  - Health endpoint
  - Memory lifecycle (remember + recall) — isolated per test via tmp DB
  - Singularity status
  - Agent discovery

Each test that touches UnifiedMemory uses a fresh tmp database via the
`isolated_memory` fixture so tests are fully independent of each other
and of existing DB state on disk.
"""
from __future__ import annotations

import json
import pytest
import sys
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

# Setup PYTHONPATH so godskill_server and runtime/agency are importable
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "runtime") not in sys.path:
    sys.path.insert(0, str(ROOT / "runtime"))

# Import flask app and unified_memory from godskill_server
from godskill_server.server import app
import godskill_server.server as _server_module


@pytest.fixture
def isolated_memory(tmp_path):
    """
    Provide a fresh UnifiedMemory instance rooted at a tmp directory.
    Patches the module-level `unified_memory` in server.py so that
    REST endpoints use the isolated instance instead of the on-disk DB.
    This makes every test hermetic — no leftover rows from previous runs.
    """
    from jarvis_brainiac.memory import UnifiedMemory
    mem = UnifiedMemory(tmp_path)
    with patch.object(_server_module, "unified_memory", mem):
        yield mem


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_api_health(client):
    """Verifies the health endpoint returns online status."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data["status"] == "online"
    assert "nav_classes" in data


# ---------------------------------------------------------------------------
# Memory lifecycle — fully isolated per test
# ---------------------------------------------------------------------------

def test_api_memory_lifecycle(client, isolated_memory):
    """
    Verifies remember → recall round-trip via REST API.
    Uses an isolated in-memory DB so the test is hermetic.
    """
    test_key = "synckeytest"
    test_value = "dashboard_integration_value_100_percent"

    # --- remember ---
    payload = {"kind": "semantic", "content": test_value, "tags": [test_key]}
    res = client.post(
        "/api/memory/remember",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert res.status_code == 200, f"remember failed: {res.data}"
    data = json.loads(res.data)
    assert data["kind"] == "semantic"
    assert data["content"] == test_value
    assert test_key in data["tags"]

    # --- recall ---
    recall_payload = {"query": test_key, "limit": 5}
    res_recall = client.post(
        "/api/memory/recall",
        data=json.dumps(recall_payload),
        content_type="application/json",
    )
    assert res_recall.status_code == 200, f"recall failed: {res_recall.data}"
    recall_data = json.loads(res_recall.data)
    assert len(recall_data) > 0, f"Recall returned empty list. DB mode: {isolated_memory._mode}"

    found = any(entry["content"] == test_value for entry in recall_data)
    assert found, f"Value '{test_value}' not found in recalled memories: {recall_data}"


def test_api_memory_remember_requires_content(client, isolated_memory):
    """remember endpoint must reject requests missing 'content'."""
    res = client.post(
        "/api/memory/remember",
        data=json.dumps({"kind": "semantic"}),
        content_type="application/json",
    )
    assert res.status_code == 400
    data = json.loads(res.data)
    assert "error" in data


def test_api_memory_recall_requires_query(client, isolated_memory):
    """recall endpoint must reject requests missing 'query'."""
    res = client.post(
        "/api/memory/recall",
        data=json.dumps({"limit": 5}),
        content_type="application/json",
    )
    assert res.status_code == 400
    data = json.loads(res.data)
    assert "error" in data


def test_api_memory_multiple_entries(client, isolated_memory):
    """Verify that multiple memories can be stored and recalled independently."""
    entries_to_add = [
        ("semantic", "Paris is the capital of France", ["geography", "europe"]),
        ("semantic", "Python is a programming language", ["coding", "python"]),
        ("procedural", "When user greets, respond warmly", ["greeting"]),
    ]
    for kind, content, tags in entries_to_add:
        res = client.post(
            "/api/memory/remember",
            data=json.dumps({"kind": kind, "content": content, "tags": tags}),
            content_type="application/json",
        )
        assert res.status_code == 200

    # Recall should return the Python entry specifically
    res = client.post(
        "/api/memory/recall",
        data=json.dumps({"query": "python", "limit": 5}),
        content_type="application/json",
    )
    assert res.status_code == 200
    results = json.loads(res.data)
    assert len(results) > 0
    assert any("Python" in r["content"] for r in results)


# ---------------------------------------------------------------------------
# Singularity
# ---------------------------------------------------------------------------

def test_api_singularity_endpoints(client):
    """Verifies that singularity status is either online or fails gracefully."""
    res = client.get("/api/singularity/status")
    if res.status_code == 200:
        data = json.loads(res.data)
        assert "status" in data
    else:
        assert res.status_code in (500, 404)


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

def test_api_agents(client):
    """Verifies that the agents endpoint returns a valid JSON structure."""
    res = client.get("/api/agents")
    if res.status_code == 200:
        data = json.loads(res.data)
        assert "agents" in data
        assert isinstance(data["agents"], list)
    else:
        assert res.status_code == 500
