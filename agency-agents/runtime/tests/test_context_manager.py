"""Tests for context_manager.py — ContextManager + ContextEntry."""

from __future__ import annotations

import time
import tempfile
from pathlib import Path

import pytest
from agency.context_manager import ContextManager, ContextEntry


@pytest.fixture
def tmp_cm(tmp_path):
    """ContextManager backed by a temp file."""
    return ContextManager(store_path=tmp_path / "ctx.json")


# ── ContextEntry ──────────────────────────────────────────────────────────────

def test_context_entry_not_expired_no_ttl():
    e = ContextEntry(key="k", value="v", domain="d")
    assert not e.is_expired()


def test_context_entry_expired_ttl():
    e = ContextEntry(key="k", value="v", ttl_seconds=0.01)
    e.created_at = time.time() - 1.0
    assert e.is_expired()


def test_context_entry_to_dict():
    e = ContextEntry(key="foo", value=42, domain="test")
    d = e.to_dict()
    assert d["key"] == "foo"
    assert d["value"] == 42


def test_context_entry_from_dict_roundtrip():
    e = ContextEntry(key="x", value="y", domain="z", tags=["a", "b"])
    e2 = ContextEntry.from_dict(e.to_dict())
    assert e2.key == e.key
    assert e2.value == e.value
    assert e2.tags == e.tags


# ── store / recall ─────────────────────────────────────────────────────────────

def test_store_and_recall(tmp_cm):
    tmp_cm.store("goal", "build something", domain="engineering")
    val = tmp_cm.recall("goal", domain="engineering")
    assert val == "build something"


def test_recall_missing_key_returns_none(tmp_cm):
    assert tmp_cm.recall("nonexistent") is None


def test_store_overwrite(tmp_cm):
    tmp_cm.store("k", "v1", domain="d")
    tmp_cm.store("k", "v2", domain="d")
    assert tmp_cm.recall("k", domain="d") == "v2"


def test_store_different_domains_separate(tmp_cm):
    tmp_cm.store("k", "eng_val", domain="engineering")
    tmp_cm.store("k", "fin_val", domain="finance")
    assert tmp_cm.recall("k", domain="engineering") == "eng_val"
    assert tmp_cm.recall("k", domain="finance") == "fin_val"


def test_store_dict_value(tmp_cm):
    tmp_cm.store("config", {"key": "value", "n": 42}, domain="system")
    val = tmp_cm.recall("config", domain="system")
    assert val["n"] == 42


def test_recall_expired_returns_none(tmp_cm):
    tmp_cm.store("exp_key", "exp_val", domain="d", ttl_seconds=0.01)
    time.sleep(0.05)
    assert tmp_cm.recall("exp_key", domain="d") is None


# ── recall_recent ──────────────────────────────────────────────────────────────

def test_recall_recent_all(tmp_cm):
    tmp_cm.store("a", 1, domain="x")
    tmp_cm.store("b", 2, domain="x")
    entries = tmp_cm.recall_recent(n=10)
    assert len(entries) >= 2


def test_recall_recent_domain_filter(tmp_cm):
    tmp_cm.store("k1", 1, domain="eng")
    tmp_cm.store("k2", 2, domain="fin")
    entries = tmp_cm.recall_recent(domain="eng", n=10)
    assert all(e.domain == "eng" for e in entries)


def test_recall_recent_respects_n(tmp_cm):
    for i in range(10):
        tmp_cm.store(f"k{i}", i, domain="d")
    entries = tmp_cm.recall_recent(n=3)
    assert len(entries) <= 3


# ── search_by_tag ──────────────────────────────────────────────────────────────

def test_search_by_tag(tmp_cm):
    tmp_cm.store("a", "val", domain="d", tags=["important", "ai"])
    tmp_cm.store("b", "val2", domain="d", tags=["ai"])
    results = tmp_cm.search_by_tag("ai")
    assert len(results) >= 2


def test_search_by_tag_no_match(tmp_cm):
    results = tmp_cm.search_by_tag("nonexistent_tag_xyz")
    assert results == []


# ── forget ─────────────────────────────────────────────────────────────────────

def test_forget_existing(tmp_cm):
    tmp_cm.store("del_k", "v", domain="d")
    assert tmp_cm.forget("del_k", domain="d") is True
    assert tmp_cm.recall("del_k", domain="d") is None


def test_forget_missing(tmp_cm):
    assert tmp_cm.forget("ghost_key") is False


# ── purge_expired ──────────────────────────────────────────────────────────────

def test_purge_expired(tmp_cm):
    tmp_cm.store("e1", "v", domain="d", ttl_seconds=0.01)
    tmp_cm.store("e2", "v", domain="d", ttl_seconds=0.01)
    tmp_cm.store("live", "v", domain="d")
    time.sleep(0.05)
    removed = tmp_cm.purge_expired()
    assert removed >= 2
    assert tmp_cm.recall("live", domain="d") == "v"


# ── dump_domain / clear_domain ─────────────────────────────────────────────────

def test_dump_domain(tmp_cm):
    tmp_cm.store("x", 1, domain="alpha")
    tmp_cm.store("y", 2, domain="alpha")
    dump = tmp_cm.dump_domain("alpha")
    assert dump["x"] == 1
    assert dump["y"] == 2


def test_clear_domain(tmp_cm):
    tmp_cm.store("x", 1, domain="beta")
    tmp_cm.store("y", 2, domain="beta")
    count = tmp_cm.clear_domain("beta")
    assert count == 2
    assert tmp_cm.recall("x", domain="beta") is None


# ── all_domains ────────────────────────────────────────────────────────────────

def test_all_domains(tmp_cm):
    tmp_cm.store("k", "v", domain="d1")
    tmp_cm.store("k", "v", domain="d2")
    domains = tmp_cm.all_domains()
    assert "d1" in domains
    assert "d2" in domains


# ── persistence across instances ──────────────────────────────────────────────

def test_persistence_across_instances(tmp_path):
    path = tmp_path / "persistent.json"
    cm1 = ContextManager(store_path=path)
    cm1.store("persistent_key", "persistent_value", domain="test")

    cm2 = ContextManager(store_path=path)
    val = cm2.recall("persistent_key", domain="test")
    assert val == "persistent_value"
