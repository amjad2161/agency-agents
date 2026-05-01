"""Tests for AuditLog chain-hash (Pass 16)."""
import json
from pathlib import Path
import pytest
from agency.audit_log import AuditLog


@pytest.fixture()
def log(tmp_path):
    return AuditLog(path=tmp_path / "audit.jsonl")


def test_empty_chain_valid(log):
    assert log.verify_chain() is True


def test_single_entry(log):
    entry = log.log("test.event", {"key": "val"})
    assert entry["event"] == "test.event"
    assert "hash" in entry
    assert "ts" in entry


def test_chain_valid_after_entries(log):
    for i in range(5):
        log.log(f"event.{i}", {"i": i})
    assert log.verify_chain() is True


def test_tail_returns_last_n(log):
    for i in range(10):
        log.log(f"ev{i}", {})
    tail = log.tail(3)
    assert len(tail) == 3
    assert tail[-1]["event"] == "ev9"


def test_tail_fewer_than_n(log):
    log.log("only", {})
    tail = log.tail(10)
    assert len(tail) == 1


def test_tamper_detection(log):
    log.log("first", {})
    log.log("second", {})
    # Tamper: overwrite the first line with modified data
    lines = log._path.read_text().splitlines()
    first = json.loads(lines[0])
    first["data"] = {"hacked": True}
    lines[0] = json.dumps(first)
    log._path.write_text("\n".join(lines) + "\n")
    assert log.verify_chain() is False


def test_each_entry_has_unique_hash(log):
    e1 = log.log("a", {})
    e2 = log.log("b", {})
    assert e1["hash"] != e2["hash"]
