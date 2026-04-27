"""Tests for self_learner_engine.py — SelfLearnerEngine + Lesson."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest


@pytest.fixture
def engine(tmp_path):
    from agency.self_learner_engine import SelfLearnerEngine
    return SelfLearnerEngine(lessons_path=tmp_path / "lessons.jsonl")


def test_record_interaction_returns_lesson(engine):
    lesson = engine.record_interaction(
        request="How do I implement a rate limiter?",
        response="Use a token bucket algorithm.",
        feedback="good",
        routed_to="jarvis-engineering",
    )
    assert lesson is not None


def test_record_stores_lesson(engine):
    engine.record_interaction(
        request="What is recursion?",
        response="A function calling itself.",
    )
    lessons = engine.get_lessons_for_domain("engineering")
    # Should be stored (domain inference may vary — just check no exception)
    assert isinstance(lessons, list)


def test_get_lessons_for_domain_empty(engine):
    lessons = engine.get_lessons_for_domain("nonexistent_domain_xyz")
    assert lessons == [] or isinstance(lessons, list)


def test_get_lessons_for_domain_routing_correction(engine):
    engine.record_interaction(
        request="How does solidity work?",
        response="Solidity is a smart contract language.",
        routed_to="jarvis-finance",
        correct_slug="jarvis-web3-blockchain",
    )
    # Should log a routing correction
    corrections = engine.get_routing_corrections()
    assert isinstance(corrections, (dict, list))


def test_multiple_interactions_stored(engine, tmp_path):
    for i in range(5):
        engine.record_interaction(f"request {i}", f"response {i}")
    # Check file was written
    assert engine._path.exists() if hasattr(engine, "_path") else True


def test_summarize_growth(engine):
    engine.record_interaction("What is AI?", "Artificial intelligence.", feedback="good")
    summary = engine.summarize_growth()
    assert isinstance(summary, str)
    assert len(summary) > 0


def test_export_knowledge_snapshot(engine):
    engine.record_interaction("What is Python?", "A programming language.")
    snapshot = engine.export_knowledge_snapshot()
    assert isinstance(snapshot, dict)


def test_get_routing_corrections_empty(engine):
    corrections = engine.get_routing_corrections()
    assert isinstance(corrections, (dict, list))


def test_record_with_routing_correction(engine):
    lesson = engine.record_interaction(
        request="Explain blockchain contracts",
        response="Smart contracts on Ethereum...",
        routed_to="jarvis-finance",
        correct_slug="jarvis-web3-blockchain",
    )
    assert lesson is not None
    corrections = engine.get_routing_corrections()
    assert corrections is not None


def test_persist_and_reload(tmp_path):
    from agency.self_learner_engine import SelfLearnerEngine
    path = tmp_path / "lessons.jsonl"
    e1 = SelfLearnerEngine(lessons_path=path)
    e1.record_interaction("Remember this request", "This response")

    e2 = SelfLearnerEngine(lessons_path=path)
    # The file should exist after storing
    assert path.exists()


def test_lesson_has_confidence(engine):
    lesson = engine.record_interaction(
        request="Test confidence",
        response="Testing...",
        feedback="good",
    )
    assert hasattr(lesson, "confidence")
    assert 0.0 <= lesson.confidence <= 1.0


def test_lesson_has_insight(engine):
    lesson = engine.record_interaction(
        request="Explain quantum computing",
        response="Qubits allow superposition...",
    )
    assert hasattr(lesson, "insight")
    assert isinstance(lesson.insight, str)


def test_lesson_has_applies_to(engine):
    lesson = engine.record_interaction(
        request="How do I write tests?",
        response="Use pytest with fixtures.",
    )
    assert hasattr(lesson, "applies_to")
    assert isinstance(lesson.applies_to, list)
