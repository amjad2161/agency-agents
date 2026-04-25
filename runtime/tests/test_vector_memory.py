"""Tests for the vector memory store."""

from __future__ import annotations

from pathlib import Path

import pytest

from agency.vector_memory import VectorMemory, _tokenize, index_lessons


@pytest.fixture
def vm(tmp_path: Path):
    db = tmp_path / "vec.db"
    store = VectorMemory(db_path=db)
    yield store
    store.close()


# ----- tokenizer ----------------------------------------------------


def test_tokenize_keeps_paths_and_identifiers():
    toks = _tokenize("Loaded /etc/hosts via run_shell tool — 200 chars")
    assert "/etc/hosts" in toks
    assert "run_shell" in toks
    assert "200" in toks
    # short tokens dropped
    assert "—" not in toks


def test_tokenize_empty():
    assert _tokenize("") == []
    assert _tokenize(None) == []


# ----- write + read roundtrip --------------------------------------


def test_upsert_and_get_roundtrip(vm):
    vm.upsert("a", "the trust gate ships well", {"kind": "lesson"})
    text, meta = vm.get("a")
    assert text == "the trust gate ships well"
    assert meta == {"kind": "lesson"}
    assert vm.count() == 1


def test_upsert_replaces_existing(vm):
    vm.upsert("a", "v1")
    vm.upsert("a", "v2")
    text, _ = vm.get("a")
    assert text == "v2"
    assert vm.count() == 1


def test_delete(vm):
    vm.upsert("a", "x")
    vm.upsert("b", "y")
    vm.delete("a")
    assert vm.get("a") is None
    assert vm.get("b") is not None


def test_clear(vm):
    vm.upsert_many([
        ("a", "x", None),
        ("b", "y", None),
    ])
    assert vm.count() == 2
    vm.clear()
    assert vm.count() == 0


# ----- search -------------------------------------------------------


def test_search_returns_relevant_doc(vm):
    vm.upsert("trust", "the trust gate is the right place to lift restrictions")
    vm.upsert("rm", "rm -rf $UNDEFINED expanded to rm -rf / on a fresh box")
    vm.upsert("color", "the color cyan looks great in the HUD")

    hits = vm.search("trust gate restrictions", k=3)
    assert hits[0].id == "trust"
    assert hits[0].score > 0


def test_search_empty_when_no_match(vm):
    vm.upsert("a", "completely unrelated content about kittens")
    hits = vm.search("blockchain quantum entanglement protocol")
    assert hits == [] or hits[0].score < 0.05  # negligible match


def test_search_returns_empty_on_empty_query(vm):
    vm.upsert("a", "anything")
    assert vm.search("") == []
    assert vm.search("   ") == []


def test_search_returns_empty_on_empty_store(vm):
    assert vm.search("anything") == []


def test_search_top_k_respects_k(vm):
    for i in range(20):
        vm.upsert(f"doc-{i}", f"shared term {i}")
    hits = vm.search("shared term", k=5)
    assert len(hits) == 5


def test_search_ranks_more_specific_higher(vm):
    vm.upsert("specific", "deploy stripe webhook for invoice payment")
    vm.upsert("general", "deploy webhook for stripe")
    hits = vm.search("stripe webhook invoice payment", k=2)
    assert hits[0].id == "specific"


# ----- index_lessons ------------------------------------------------


def test_index_lessons_splits_on_h2(vm):
    body = """# Lessons

Some intro text.

## 2026-04-25 12:00 UTC · install

WORKED: setup done

## 2026-04-25 13:00 UTC · deploy

WORKED: vercel went live
COST: 20 minutes on env vars

## 2026-04-25 14:00 UTC · stripe

WORKED: webhook verified
"""
    n = index_lessons(vm, body)
    assert n == 3
    hits = vm.search("vercel deploy", k=2)
    assert hits[0].id.startswith("2026-04-25 13:00")


def test_index_lessons_skips_non_header_text(vm):
    body = "Just plain text with no `## ` headers."
    n = index_lessons(vm, body)
    assert n == 0
    assert vm.count() == 0


# ----- env override -------------------------------------------------


def test_env_override_for_db_path(tmp_path, monkeypatch):
    target = tmp_path / "alt-vec.db"
    monkeypatch.setenv("AGENCY_VECTOR_DB", str(target))
    from agency.vector_memory import _vector_path
    assert _vector_path() == target


# ----- custom embedder hook ----------------------------------------


def test_custom_embedder_overrides_tokenizer(vm):
    """Upserting with a custom embedder should bypass _tokenize."""
    vm.set_embedder(lambda text: {"FIXED": 1.0})
    vm.upsert("a", "anything at all")
    vm.upsert("b", "completely different content")
    # both docs share the FIXED term and only the FIXED term, so any
    # query containing FIXED should return both with equal score.
    hits = vm.search("FIXED", k=2)
    assert len(hits) == 2


# ----- bulk + introspection ----------------------------------------


def test_upsert_many_returns_count(vm):
    n = vm.upsert_many([(f"d{i}", f"text {i}", None) for i in range(7)])
    assert n == 7
    assert vm.count() == 7


def test_all_ids_orders_by_recency(vm):
    import time
    vm.upsert("first", "x")
    time.sleep(0.01)
    vm.upsert("second", "y")
    time.sleep(0.01)
    vm.upsert("third", "z")
    ids = vm.all_ids()
    assert ids[0] == "third"
    assert ids[-1] == "first"
