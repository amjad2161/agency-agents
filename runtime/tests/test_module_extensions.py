"""Tests for the new public APIs added to existing capability modules.

Covers:
- ``SelfLearnerEngine.lessons`` and ``.lessons_path`` properties
- ``AutonomousLoop.is_running``, ``.max_iterations``, ``.runs_path``,
  ``.registered_executors()``
- ``KnowledgeExpansion.entry_count()``, ``.list_sources()``, ``.clear()``
- ``MultimodalProcessor.available_backends()`` and ``.has_backend()``
"""

from __future__ import annotations

import threading
import time

import pytest


# ---------------------------------------------------------------------------
# Self-learner extensions
# ---------------------------------------------------------------------------


def test_self_learner_lessons_property_returns_list(tmp_path):
    from agency.self_learner_engine import SelfLearnerEngine

    eng = SelfLearnerEngine(lessons_path=tmp_path / "lessons.jsonl")
    assert isinstance(eng.lessons, list)
    assert eng.lessons == []


def test_self_learner_lessons_path_property(tmp_path):
    from agency.self_learner_engine import SelfLearnerEngine

    p = tmp_path / "lessons.jsonl"
    eng = SelfLearnerEngine(lessons_path=p)
    assert eng.lessons_path == p


def test_self_learner_lessons_property_returns_copy(tmp_path):
    from agency.self_learner_engine import SelfLearnerEngine

    eng = SelfLearnerEngine(lessons_path=tmp_path / "lessons.jsonl")
    a = eng.lessons
    a.append("dummy")  # mutate the returned list
    assert eng.lessons == []  # internal state untouched


def test_self_learner_records_a_lesson_then_lessons_property_reflects_it(tmp_path):
    from agency.self_learner_engine import SelfLearnerEngine

    eng = SelfLearnerEngine(lessons_path=tmp_path / "lessons.jsonl")
    eng.record_interaction(
        request="describe a hash table",
        response="A hash table is a data structure that maps keys to values",
        routed_to="jarvis-engineering",
        feedback="great",
    )
    # property reflects the on-disk state lazily
    eng2 = SelfLearnerEngine(lessons_path=eng.lessons_path)
    assert len(eng2.lessons) == 1


# ---------------------------------------------------------------------------
# AutonomousLoop extensions
# ---------------------------------------------------------------------------


def test_autonomous_loop_max_iterations_default():
    from agency.autonomous_loop import AutonomousLoop

    loop = AutonomousLoop()
    assert loop.max_iterations >= 1


def test_autonomous_loop_runs_path_returns_path(tmp_path):
    from agency.autonomous_loop import AutonomousLoop

    p = tmp_path / "runs.jsonl"
    loop = AutonomousLoop(runs_path=p)
    assert loop.runs_path == p


def test_autonomous_loop_register_and_list_executors():
    from agency.autonomous_loop import AutonomousLoop

    loop = AutonomousLoop()
    loop.register_executor("alpha", lambda action, ctx: "ok")
    loop.register_executor("beta", lambda action, ctx: "ok")
    names = loop.registered_executors()
    assert "alpha" in names
    assert "beta" in names


def test_autonomous_loop_idle_is_running_false():
    from agency.autonomous_loop import AutonomousLoop

    loop = AutonomousLoop(max_iterations=1)
    assert loop.is_running is False


def test_autonomous_loop_is_running_during_run(tmp_path):
    """is_running flips true while a run is in flight."""
    from agency.autonomous_loop import AutonomousLoop

    seen_running: list[bool] = []
    loop = AutonomousLoop(max_iterations=2, runs_path=tmp_path / "runs.jsonl")

    def slow(action, ctx):
        # capture flag from background thread before returning
        seen_running.append(loop.is_running)
        return "DONE: ok"

    loop.register_executor("default", slow)
    run = loop.run("any goal")
    assert run is not None
    assert any(seen_running)
    # After the run completes, flag clears.
    assert loop.is_running is False


# ---------------------------------------------------------------------------
# KnowledgeExpansion extensions
# ---------------------------------------------------------------------------


def test_knowledge_expansion_entry_count_starts_zero():
    from agency.knowledge_expansion import KnowledgeExpansion

    ke = KnowledgeExpansion()
    assert ke.entry_count() == 0


def test_knowledge_expansion_list_sources_starts_empty():
    from agency.knowledge_expansion import KnowledgeExpansion

    ke = KnowledgeExpansion()
    assert ke.list_sources() == []


def test_knowledge_expansion_after_ingest_entry_count_grows():
    from agency.knowledge_expansion import KnowledgeExpansion

    ke = KnowledgeExpansion(chunk_size=10, chunk_overlap=2)
    ke.ingest_text(
        "alpha beta gamma delta epsilon zeta eta theta iota kappa "
        "lambda mu nu xi omicron pi rho sigma tau upsilon",
        source="doc.md",
        domain="general",
    )
    assert ke.entry_count() >= 1
    assert "doc.md" in ke.list_sources()


def test_knowledge_expansion_clear_removes_chunks():
    from agency.knowledge_expansion import KnowledgeExpansion

    ke = KnowledgeExpansion()
    ke.ingest_text("a b c d", source="x", domain="g")
    assert ke.entry_count() == 1
    removed = ke.clear()
    assert removed == 1
    assert ke.entry_count() == 0


# ---------------------------------------------------------------------------
# MultimodalProcessor extensions
# ---------------------------------------------------------------------------


def test_multimodal_default_backends_empty():
    from agency.multimodal import MultimodalProcessor

    mp = MultimodalProcessor()
    assert mp.available_backends() == []
    assert mp.has_backend("ocr") is False


def test_multimodal_with_ocr_backend():
    from agency.multimodal import MultimodalProcessor

    def fake_ocr(_raw, _mime):
        return "fake text"

    mp = MultimodalProcessor(ocr_backend=fake_ocr)
    assert "ocr" in mp.available_backends()
    assert mp.has_backend("ocr") is True
    assert mp.has_backend("transcription") is False


def test_multimodal_with_transcription_backend():
    from agency.multimodal import MultimodalProcessor

    def fake_transcribe(_raw, _mime):
        return "fake transcript"

    mp = MultimodalProcessor(transcription_backend=fake_transcribe)
    assert "transcription" in mp.available_backends()


def test_multimodal_with_both_backends():
    from agency.multimodal import MultimodalProcessor

    mp = MultimodalProcessor(
        ocr_backend=lambda r, m: "x",
        transcription_backend=lambda r, m: "y",
    )
    backends = mp.available_backends()
    assert set(backends) == {"ocr", "transcription"}
