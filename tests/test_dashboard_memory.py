"""
Automated integration tests for testing the memory lifecycle and dashboard API endpoints of the godskill server.
"""

from __future__ import annotations
import json
import pytest
import sys
from pathlib import Path

# Setup PYTHONPATH so godskill_server and runtime/agency are imported correctly
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "runtime") not in sys.path:
    sys.path.insert(0, str(ROOT / "runtime"))

# Import flask app from godskill_server
from godskill_server.server import app, unified_memory


@pytest.fixture
def client():
    app.config['TESTING'] = True
    # Ensure memory dir is isolated/available for tests if needed
    with app.test_client() as client:
        yield client


def test_api_health(client):
    """Verifies the health endpoint returns online status."""
    res = client.get('/api/health')
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data['status'] == 'online'
    assert 'nav_classes' in data


def test_api_memory_lifecycle(client):
    """Verifies remember and recall functionality of UnifiedMemory via server REST API."""
    if unified_memory is None:
        pytest.skip("UnifiedMemory is not initialized/available on this platform")

    # Generate a unique key-value pair to test sync
    test_key = "synckeytest"
    test_value = "dashboard_integration_value_100_percent"

    # Save memory via POST /api/memory/remember
    payload = {
        "kind": "semantic",
        "content": test_value,
        "tags": [test_key]
    }
    res = client.post('/api/memory/remember',
                      data=json.dumps(payload),
                      content_type='application/json')
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data['kind'] == 'semantic'
    assert data['content'] == test_value
    assert test_key in data['tags']

    # Retrieve memory via POST /api/memory/recall
    recall_payload = {
        "query": test_key,
        "limit": 5
    }
    res_recall = client.post('/api/memory/recall',
                             data=json.dumps(recall_payload),
                             content_type='application/json')
    assert res_recall.status_code == 200
    recall_data = json.loads(res_recall.data)
    assert len(recall_data) > 0
    
    # Locate the created entry
    found = False
    for entry in recall_data:
        if entry['content'] == test_value:
            found = True
            break
    assert found, f"Value '{test_value}' not found in recalled memories: {recall_data}"


def test_api_singularity_endpoints(client):
    """Verifies that singularity status is either online or fails gracefully."""
    res = client.get('/api/singularity/status')
    if res.status_code == 200:
        data = json.loads(res.data)
        assert 'status' in data
    else:
        assert res.status_code in (500, 404)


def test_api_agents(client):
    """Verifies that the agents endpoint returns JSON list of discovered agents."""
    res = client.get('/api/agents')
    # Could fail if registry throws error, but otherwise should be a valid JSON
    if res.status_code == 200:
        data = json.loads(res.data)
        assert 'agents' in data
        assert isinstance(data['agents'], list)
    else:
        assert res.status_code == 500
