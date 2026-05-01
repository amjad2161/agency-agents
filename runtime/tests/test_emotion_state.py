"""Tests for emotion_state.py — Emotion, EmotionState."""

from __future__ import annotations

import pytest

from agency.emotion_state import Emotion, EmotionState


@pytest.fixture
def state():
    return EmotionState()


# ------------------------------------------------------------------
# Enum tests
# ------------------------------------------------------------------

def test_emotion_values():
    assert Emotion.CURIOUS == "curious"
    assert Emotion.FOCUSED == "focused"
    assert Emotion.ALERT == "alert"
    assert Emotion.SATISFIED == "satisfied"
    assert Emotion.CONFUSED == "confused"
    assert Emotion.EXCITED == "excited"


def test_emotion_is_str():
    assert isinstance(Emotion.CURIOUS, str)


# ------------------------------------------------------------------
# EmotionState.set / get
# ------------------------------------------------------------------

def test_default_emotion_is_focused(state):
    assert state.get() == Emotion.FOCUSED


def test_set_emotion_enum(state):
    state.set(Emotion.CURIOUS)
    assert state.get() == Emotion.CURIOUS


def test_set_emotion_string(state):
    state.set("alert")
    assert state.get() == Emotion.ALERT


def test_set_all_emotions(state):
    for e in Emotion:
        state.set(e)
        assert state.get() == e


def test_set_invalid_emotion_raises(state):
    with pytest.raises(ValueError):
        state.set("angry")  # not in enum


# ------------------------------------------------------------------
# Hebrew
# ------------------------------------------------------------------

def test_hebrew_focused(state):
    state.set(Emotion.FOCUSED)
    assert state.hebrew() == "ממוקד"


def test_hebrew_curious(state):
    state.set(Emotion.CURIOUS)
    assert state.hebrew() == "סקרן"


def test_hebrew_alert(state):
    state.set(Emotion.ALERT)
    assert state.hebrew() == "עירני"


def test_hebrew_satisfied(state):
    state.set(Emotion.SATISFIED)
    assert state.hebrew() == "מרוצה"


def test_hebrew_confused(state):
    state.set(Emotion.CONFUSED)
    assert state.hebrew() == "מבולבל"


def test_hebrew_excited(state):
    state.set(Emotion.EXCITED)
    assert state.hebrew() == "נרגש"


# ------------------------------------------------------------------
# Transition
# ------------------------------------------------------------------

def test_transition_error_gives_alert(state):
    e = state.transition("there was an error in the code")
    assert e == Emotion.ALERT


def test_transition_success_gives_satisfied(state):
    e = state.transition("task success")
    assert e == Emotion.SATISFIED


def test_transition_question_gives_curious(state):
    e = state.transition("question about this")
    assert e == Emotion.CURIOUS


def test_transition_wow_gives_excited(state):
    e = state.transition("wow that is incredible")
    assert e == Emotion.EXCITED


def test_transition_confuse_gives_confused(state):
    e = state.transition("this is confusing and unclear")
    assert e == Emotion.CONFUSED


def test_transition_focus_gives_focused(state):
    s = EmotionState()
    s.set(Emotion.CURIOUS)
    e = s.transition("focus on the task")
    assert e == Emotion.FOCUSED


def test_transition_no_match_unchanged(state):
    state.set(Emotion.SATISFIED)
    e = state.transition("blah blah unrecognized words xyz")
    assert e == Emotion.SATISFIED


def test_transition_same_state_no_history_entry(state):
    state.set(Emotion.ALERT)
    h_before = len(state.history())
    state.transition("another error")  # ALERT → ALERT (no change)
    h_after = len(state.history())
    assert h_after == h_before  # no new history entry if no change


# ------------------------------------------------------------------
# History
# ------------------------------------------------------------------

def test_history_empty_initially(state):
    assert state.history() == []


def test_history_after_set(state):
    state.set(Emotion.CURIOUS)
    h = state.history()
    assert len(h) == 1
    assert "focused" in h[0]
    assert "curious" in h[0]


def test_history_limit(state):
    for e in list(Emotion) * 5:
        state.set(e)
    h = state.history(n=3)
    assert len(h) == 3


def test_history_default_limit_10(state):
    for e in list(Emotion) * 5:
        state.set(e)
    h = state.history()
    assert len(h) <= 10


def test_history_records_transitions(state):
    state.set(Emotion.ALERT)
    state.set(Emotion.SATISFIED)
    state.set(Emotion.EXCITED)
    h = state.history()
    assert len(h) == 3
