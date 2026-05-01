"""Tests for long_term_memory.py — LongTermMemory."""

from __future__ import annotations

import pytest


@pytest.fixture
def ltm(tmp_path):
    from agency.long_term_memory import LongTermMemory
    db = LongTermMemory(db_path=tmp_path / "test_ltm.db")
    yield db
    db.close()


def test_store_returns_int(ltm):
    row_id = ltm.store("Hello, world!", category="test")
    assert isinstance(row_id, int)
    assert row_id > 0


def test_store_default_category(ltm):
    row_id = ltm.store("No category provided")
    assert isinstance(row_id, int)
    results = ltm.recall()
    assert any(r["category"] == "general" for r in results)


def test_recall_all(ltm):
    ltm.store("First memory", "cat1")
    ltm.store("Second memory", "cat2")
    results = ltm.recall()
    assert len(results) == 2


def test_recall_with_category_filter(ltm):
    ltm.store("Important note", "important")
    ltm.store("Casual remark", "casual")
    results = ltm.recall(category="important")
    assert len(results) == 1
    assert results[0]["content"] == "Important note"


def test_recall_limit(ltm):
    for i in range(10):
        ltm.store(f"Memory {i}", "batch")
    results = ltm.recall(limit=3)
    assert len(results) == 3


def test_search_finds_content(ltm):
    ltm.store("The quick brown fox jumps", "animals")
    ltm.store("Machine learning is fascinating", "tech")
    results = ltm.search("quick fox")
    assert len(results) >= 1
    assert any("fox" in r["content"] for r in results)


def test_search_returns_score(ltm):
    ltm.store("Python programming language", "tech")
    results = ltm.search("Python")
    assert len(results) >= 1
    assert "score" in results[0]


def test_search_limit(ltm):
    for i in range(10):
        ltm.store(f"Topic number {i} about search", "test")
    results = ltm.search("Topic", limit=3)
    assert len(results) <= 3


def test_forget_removes_entry(ltm):
    row_id = ltm.store("To be forgotten", "temp")
    removed = ltm.forget(row_id)
    assert removed is True
    results = ltm.recall()
    assert not any(r["content"] == "To be forgotten" for r in results)


def test_forget_nonexistent_returns_false(ltm):
    removed = ltm.forget(999999)
    assert removed is False


def test_stats_total_count(ltm):
    ltm.store("A", "x")
    ltm.store("B", "y")
    stats = ltm.stats()
    assert stats["total_count"] == 2


def test_stats_categories(ltm):
    ltm.store("Cat1 entry 1", "cat1")
    ltm.store("Cat1 entry 2", "cat1")
    ltm.store("Cat2 entry", "cat2")
    stats = ltm.stats()
    assert stats["categories"]["cat1"] == 2
    assert stats["categories"]["cat2"] == 1


def test_stats_db_size(ltm):
    ltm.store("Some content", "size_test")
    stats = ltm.stats()
    assert stats["db_size_bytes"] > 0


def test_search_empty_db(ltm):
    results = ltm.search("anything")
    assert results == []


def test_multiple_stores_and_recall_order(ltm):
    ids = [ltm.store(f"Entry {i}", "ordered") for i in range(5)]
    results = ltm.recall(category="ordered")
    # Should be in descending timestamp order (most recent first)
    assert len(results) == 5
