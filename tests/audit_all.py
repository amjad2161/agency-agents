"""
Full audit script — runs all verifications on JARVIS BRAINIAC project.
Execute with:
    python tests/audit_all.py
from the project root (C:\\Users\\Mobar\\jarvis-brainiac).
"""
from __future__ import annotations

import sys
import json
import sqlite3
import tempfile
import importlib
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "runtime") not in sys.path:
    sys.path.insert(0, str(ROOT / "runtime"))

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m!\033[0m"

results: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> bool:
    try:
        fn()
        results.append((name, True, ""))
        print(f"  {PASS} {name}")
        return True
    except Exception as exc:
        msg = str(exc)
        results.append((name, False, msg))
        print(f"  {FAIL} {name}: {msg}")
        return False


print("\n══════════════════════════════════════════")
print("  JARVIS BRAINIAC — Full Audit")
print("══════════════════════════════════════════\n")

# ── 1. Python imports ─────────────────────────────────────────────────────────
print("1. Imports")

check("import jarvis_brainiac.memory", lambda: importlib.import_module("jarvis_brainiac.memory"))
check("import jarvis_brainiac.agent_registry", lambda: importlib.import_module("jarvis_brainiac.agent_registry"))
check("import jarvis_brainiac.heartbeat", lambda: importlib.import_module("jarvis_brainiac.heartbeat"))
check("import godskill_server.server (Flask app)", lambda: importlib.import_module("godskill_server.server"))

# ── 2. UnifiedMemory ─────────────────────────────────────────────────────────
print("\n2. UnifiedMemory")

from jarvis_brainiac.memory import UnifiedMemory, MemoryEntry

def _test_remember_recall():
    with tempfile.TemporaryDirectory() as tmp:
        mem = UnifiedMemory(tmp)
        assert mem._mode in ("sqlite-fts5", "jsonl"), f"Unknown mode: {mem._mode}"
        entry = mem.remember("semantic", "test content", tags=["testtag"])
        assert entry.id is not None or mem._mode == "jsonl"
        results_list = mem.recall("testtag")
        assert len(results_list) > 0, "recall returned empty list"
        assert results_list[0].content == "test content"

def _test_forget():
    with tempfile.TemporaryDirectory() as tmp:
        mem = UnifiedMemory(tmp)
        if mem._mode != "sqlite-fts5":
            return  # skip for JSONL mode
        entry = mem.remember("semantic", "to be deleted", tags=["delete-me"])
        assert entry.id is not None
        deleted = mem.forget(entry.id)
        assert deleted is True
        remaining = mem.recall("delete-me")
        assert all(r.id != entry.id for r in remaining)

def _test_stats():
    with tempfile.TemporaryDirectory() as tmp:
        mem = UnifiedMemory(tmp)
        mem.remember("semantic", "stat entry 1", tags=["a"])
        mem.remember("episodic", "stat entry 2", tags=["b"])
        s = mem.stats()
        assert s["total"] == 2
        assert s["mode"] in ("sqlite-fts5", "jsonl")

def _test_isolation_level():
    """Verify that isolation_level=None is in effect (autocommit)."""
    with tempfile.TemporaryDirectory() as tmp:
        mem = UnifiedMemory(tmp)
        if mem._mode != "sqlite-fts5":
            return
        con = mem._connect()
        assert con.isolation_level is None, f"Expected autocommit, got isolation_level={con.isolation_level!r}"
        con.close()

check("remember + recall round-trip", _test_remember_recall)
check("forget by id", _test_forget)
check("stats()", _test_stats)
check("autocommit (isolation_level=None)", _test_isolation_level)

# ── 3. Flask server endpoints ─────────────────────────────────────────────────
print("\n3. Flask server endpoints")

from unittest.mock import patch
from godskill_server.server import app
import godskill_server.server as _srv

app.config["TESTING"] = True

def _test_health():
    with app.test_client() as c:
        r = c.get("/api/health")
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["status"] == "online"

def _test_memory_api():
    with tempfile.TemporaryDirectory() as tmp:
        mem = UnifiedMemory(tmp)
        with patch.object(_srv, "unified_memory", mem):
            with app.test_client() as c:
                # remember
                r = c.post("/api/memory/remember",
                           data=json.dumps({"kind": "semantic", "content": "api test", "tags": ["apitest"]}),
                           content_type="application/json")
                assert r.status_code == 200
                data = json.loads(r.data)
                assert data["content"] == "api test"
                # recall
                r2 = c.post("/api/memory/recall",
                            data=json.dumps({"query": "apitest", "limit": 5}),
                            content_type="application/json")
                assert r2.status_code == 200
                recall_data = json.loads(r2.data)
                assert len(recall_data) > 0, "Recall returned empty"

def _test_remember_validation():
    with tempfile.TemporaryDirectory() as tmp:
        mem = UnifiedMemory(tmp)
        with patch.object(_srv, "unified_memory", mem):
            with app.test_client() as c:
                r = c.post("/api/memory/remember",
                           data=json.dumps({"kind": "semantic"}),  # missing content
                           content_type="application/json")
                assert r.status_code == 400

def _test_recall_validation():
    with tempfile.TemporaryDirectory() as tmp:
        mem = UnifiedMemory(tmp)
        with patch.object(_srv, "unified_memory", mem):
            with app.test_client() as c:
                r = c.post("/api/memory/recall",
                           data=json.dumps({"limit": 5}),  # missing query
                           content_type="application/json")
                assert r.status_code == 400

check("GET /api/health", _test_health)
check("POST /api/memory/remember + recall", _test_memory_api)
check("remember validation (missing content → 400)", _test_remember_validation)
check("recall validation (missing query → 400)", _test_recall_validation)

# ── 4. AgentRegistry ─────────────────────────────────────────────────────────
print("\n4. AgentRegistry")

from jarvis_brainiac.agent_registry import AgentRegistry

def _test_registry_discover():
    reg = AgentRegistry(ROOT)
    agents = reg.discover()
    assert isinstance(agents, dict)
    assert len(agents) > 0, "No agents discovered — check division dirs exist"

def _test_registry_find():
    reg = AgentRegistry(ROOT)
    reg.discover()
    results_list = reg.find("code review")
    assert isinstance(results_list, list)

def _test_registry_stats():
    reg = AgentRegistry(ROOT)
    reg.discover()
    s = reg.stats()
    assert "total_agents" in s
    assert s["total_agents"] > 0

check("discover() finds agents", _test_registry_discover)
check("find() returns list", _test_registry_find)
check("stats() returns totals", _test_registry_stats)

# ── 5. SQLite FTS5 availability ───────────────────────────────────────────────
print("\n5. SQLite features")

def _test_fts5():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE VIRTUAL TABLE t USING fts5(content)")
    con.execute("INSERT INTO t VALUES ('hello world')")
    rows = con.execute("SELECT * FROM t WHERE t MATCH 'hello'").fetchall()
    assert len(rows) == 1
    con.close()

def _test_sqlite_version():
    ver = sqlite3.sqlite_version_info
    assert ver >= (3, 35, 0), f"SQLite {ver} too old — need 3.35+"

check("FTS5 virtual table", _test_fts5)
check("SQLite version >= 3.35", _test_sqlite_version)

# ── 6. Summary ────────────────────────────────────────────────────────────────
print("\n══════════════════════════════════════════")
total = len(results)
passed = sum(1 for _, ok, _ in results if ok)
failed = total - passed

if failed == 0:
    print(f"  {PASS} ALL {total} CHECKS PASSED")
else:
    print(f"  {FAIL} {failed}/{total} CHECKS FAILED")
    print("\nFailed checks:")
    for name, ok, msg in results:
        if not ok:
            print(f"  - {name}: {msg}")

print("══════════════════════════════════════════\n")
sys.exit(0 if failed == 0 else 1)
