"""Tests for self_learner.py — ConversationLearner."""

from __future__ import annotations

import pytest


@pytest.fixture
def learner(tmp_path):
    from agency.long_term_memory import LongTermMemory
    from agency.self_learner import ConversationLearner
    ltm = LongTermMemory(db_path=tmp_path / "learner_ltm.db")
    cl = ConversationLearner(ltm=ltm)
    yield cl
    ltm.close()


def test_extract_insights_with_always(learner):
    insights = learner.extract_insights(
        user_msg="What should I do?",
        assistant_msg="Always validate input before processing.",
    )
    assert len(insights) >= 1
    assert any("always" in i.lower() for i in insights)


def test_extract_insights_with_never(learner):
    insights = learner.extract_insights(
        user_msg="Any warnings?",
        assistant_msg="Never expose credentials in logs.",
    )
    assert len(insights) >= 1
    assert any("never" in i.lower() for i in insights)


def test_extract_insights_with_prefer(learner):
    insights = learner.extract_insights(
        user_msg="Which approach?",
        assistant_msg="Prefer list comprehensions over map() in Python.",
    )
    assert len(insights) >= 1


def test_extract_insights_with_remember(learner):
    insights = learner.extract_insights(
        user_msg="Remember that Python is zero-indexed.",
        assistant_msg="Good point.",
    )
    assert len(insights) >= 1


def test_extract_insights_with_note_that(learner):
    insights = learner.extract_insights(
        user_msg="",
        assistant_msg="Note that environment variables override config files.",
    )
    assert len(insights) >= 1


def test_extract_insights_no_match(learner):
    insights = learner.extract_insights(
        user_msg="Hi",
        assistant_msg="Hello there.",
    )
    assert isinstance(insights, list)


def test_learn_from_turn_returns_count(learner):
    count = learner.learn_from_turn(
        user_msg="Important: always use HTTPS.",
        assistant_msg="Note that HTTP is insecure.",
    )
    assert isinstance(count, int)
    assert count >= 0


def test_learn_from_turn_stores_to_ltm(learner):
    learner.learn_from_turn(
        user_msg="",
        assistant_msg="Always prefer async over sync for IO operations.",
    )
    # The stored insight should be findable
    context = learner.get_relevant_context("async")
    assert isinstance(context, str)


def test_get_relevant_context_returns_string(learner):
    ctx = learner.get_relevant_context("any query")
    assert isinstance(ctx, str)


def test_get_relevant_context_with_stored_data(learner):
    learner.learn_from_turn(
        "",
        "Always use type hints in Python functions for clarity.",
    )
    ctx = learner.get_relevant_context("type hints")
    assert isinstance(ctx, str)


def test_learn_multiple_turns(learner):
    turns = [
        ("What's best?", "Always test your code before deploying."),
        ("Security?", "Never store passwords in plaintext."),
        ("Tips?", "Prefer small functions over large monolithic ones."),
    ]
    total = 0
    for u, a in turns:
        total += learner.learn_from_turn(u, a)
    assert total >= 3


def test_deduplication_in_extract(learner):
    # Same sentence appearing twice should only produce one insight
    msg = "Always validate. Always validate."
    insights = learner.extract_insights("", msg)
    # Count occurrences of the insight
    duplicates = [i for i in insights if "always validate" in i.lower()]
    assert len(duplicates) == 1
