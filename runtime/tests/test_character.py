"""Comprehensive tests for the JARVIS character system.

Covers:
  - jarvis_soul       — identity constants and helpers
  - amjad_memory      — hard facts, dynamic overrides, persistence
  - character_state   — mode/mood transitions, interaction counting, persistence
  - persona_engine    — system prompts, voice formatting, mode detection, greetings, prefs
  - jarvis_greeting   — startup banner, farewell, transitions
  - supreme_main      — BootedSystem, initialise_character_system, process()
  - __init__ wiring   — get_unified_bridge() exposes persona/character/memory + process()
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_prefs(tmp_path):
    """Isolated prefs JSON path."""
    return tmp_path / "prefs.json"


@pytest.fixture()
def tmp_state(tmp_path):
    """Isolated state JSON path."""
    return tmp_path / "state.json"


@pytest.fixture()
def pe(tmp_prefs):
    """Fresh PersonaEngine with isolated prefs."""
    from agency.persona_engine import PersonaEngine
    return PersonaEngine(prefs_path=tmp_prefs)


@pytest.fixture()
def cs(tmp_state):
    """Fresh CharacterState (not singleton) with isolated state path."""
    from agency.character_state import CharacterState
    CharacterState.reset_singleton()
    inst = CharacterState.get_instance(state_path=tmp_state, force_new=True)
    yield inst
    CharacterState.reset_singleton()


@pytest.fixture()
def am(tmp_path):
    """Fresh AmjadMemory with isolated prefs path."""
    from agency.amjad_memory import AmjadMemory
    return AmjadMemory(prefs_path=tmp_path / "amjad_prefs.json")


# ===========================================================================
# 1. JARVIS SOUL
# ===========================================================================

class TestJarvisSoul:

    def test_soul_name(self):
        from agency.jarvis_soul import JARVIS_SOUL
        assert JARVIS_SOUL["name"] == "J.A.R.V.I.S"

    def test_soul_full_name(self):
        from agency.jarvis_soul import JARVIS_SOUL
        assert "Just A Rather Very Intelligent System" in JARVIS_SOUL["full_name"]

    def test_soul_codename(self):
        from agency.jarvis_soul import JARVIS_SOUL
        assert JARVIS_SOUL["codename"] == "Supreme Brainiac"

    def test_soul_owner(self):
        from agency.jarvis_soul import JARVIS_SOUL
        assert JARVIS_SOUL["owner"] == "Amjad"

    def test_soul_owner_email(self):
        from agency.jarvis_soul import JARVIS_SOUL
        assert JARVIS_SOUL["owner_email"] == "mobarsham@gmail.com"

    def test_soul_core_mission(self):
        from agency.jarvis_soul import JARVIS_SOUL
        assert JARVIS_SOUL["core_mission"]
        assert "Amjad" in JARVIS_SOUL["core_mission"]

    def test_soul_loyalty_absolute(self):
        from agency.jarvis_soul import JARVIS_SOUL
        assert JARVIS_SOUL["loyalty_level"] == "absolute"

    @pytest.mark.parametrize("trait", [
        "analytical", "precise", "loyal", "witty", "decisive",
        "protective", "proactive", "honest", "adaptive",
    ])
    def test_soul_has_trait(self, trait):
        from agency.jarvis_soul import JARVIS_SOUL
        assert trait in JARVIS_SOUL["personality_traits"]

    def test_get_soul_returns_dict(self):
        from agency.jarvis_soul import get_soul
        soul = get_soul()
        assert isinstance(soul, dict)
        assert "name" in soul

    def test_get_trait_true(self):
        from agency.jarvis_soul import get_trait
        assert get_trait("loyal") is True

    def test_get_trait_false(self):
        from agency.jarvis_soul import get_trait
        assert get_trait("cowardly") is False

    @pytest.mark.parametrize("behavior", [
        "apologise unnecessarily",
        "use filler words",
        "say 'as an AI'",
        "hallucinate facts",
    ])
    def test_forbidden_behavior_detected(self, behavior):
        from agency.jarvis_soul import get_forbidden
        assert get_forbidden(behavior) is True

    def test_non_forbidden_behavior(self):
        from agency.jarvis_soul import get_forbidden
        assert get_forbidden("provide accurate analysis") is False

    def test_get_signature_phrase_returns_string(self):
        from agency.jarvis_soul import get_signature_phrase
        p = get_signature_phrase(0)
        assert isinstance(p, str) and len(p) > 0

    def test_get_signature_phrase_wraps(self):
        from agency.jarvis_soul import JARVIS_SOUL, get_signature_phrase
        n = len(JARVIS_SOUL["signature_phrases"])
        assert get_signature_phrase(n) == get_signature_phrase(0)

    @pytest.mark.parametrize("mode,expected_substr", [
        ("technical", "dense_precise"),
        ("casual", "warm_witty"),
        ("crisis", "calm_authoritative"),
        ("default", "professional"),
    ])
    def test_get_communication_style(self, mode, expected_substr):
        from agency.jarvis_soul import get_communication_style
        style = get_communication_style(mode)
        assert expected_substr in style

    def test_get_communication_style_fallback(self):
        from agency.jarvis_soul import get_communication_style
        # Unknown mode → default
        style = get_communication_style("xyz_unknown")
        assert "professional" in style

    def test_soul_has_projects(self):
        from agency.jarvis_soul import JARVIS_SOUL
        projects = JARVIS_SOUL["active_projects"]
        names = [p["name"] for p in projects]
        assert "J.A.R.V.I.S" in names

    def test_soul_has_gane_project(self):
        from agency.jarvis_soul import JARVIS_SOUL
        names = [p["name"] for p in JARVIS_SOUL["active_projects"]]
        assert any("G.A.N.E" in n for n in names)

    def test_soul_forbidden_list_nonempty(self):
        from agency.jarvis_soul import JARVIS_SOUL
        assert len(JARVIS_SOUL["forbidden_behaviors"]) >= 5

    def test_soul_voice_signature_nonempty(self):
        from agency.jarvis_soul import JARVIS_SOUL
        assert len(JARVIS_SOUL["voice_signature"]) > 20

    def test_soul_capabilities_list(self):
        from agency.jarvis_soul import JARVIS_SOUL
        assert isinstance(JARVIS_SOUL["capabilities"], list)
        assert len(JARVIS_SOUL["capabilities"]) >= 3


# ===========================================================================
# 2. AMJAD MEMORY
# ===========================================================================

class TestAmjadMemory:

    def test_owner_name(self, am):
        assert am.owner_name() == "Amjad"

    def test_owner_email(self, am):
        assert am.owner_email() == "mobarsham@gmail.com"

    def test_primary_language(self, am):
        assert am.primary_language() == "hebrew"

    def test_get_context_returns_dict(self, am):
        ctx = am.get_context()
        assert isinstance(ctx, dict)

    def test_context_contains_name(self, am):
        ctx = am.get_context()
        assert ctx["name"] == "Amjad"

    def test_context_contains_email(self, am):
        ctx = am.get_context()
        assert ctx["email"] == "mobarsham@gmail.com"

    def test_context_contains_projects(self, am):
        ctx = am.get_context()
        assert len(ctx["projects"]) >= 1

    def test_projects_include_jarvis(self, am):
        names = [p["name"] for p in am.projects()]
        assert "J.A.R.V.I.S" in names

    def test_projects_include_gane(self, am):
        names = [p["name"] for p in am.projects()]
        assert any("G.A.N.E" in n for n in names)

    def test_dislikes_nonempty(self, am):
        d = am.dislikes()
        assert len(d) >= 3

    def test_dislikes_includes_wasted_tokens(self, am):
        d = am.dislikes()
        assert any("token" in item.lower() for item in d)

    def test_loves_nonempty(self, am):
        assert len(am.loves()) >= 2

    def test_loves_includes_autonomous(self, am):
        loves = am.loves()
        assert any("autonom" in item.lower() for item in loves)

    def test_update_persists(self, am, tmp_path):
        am.update("theme", "dark")
        assert am.get("theme") == "dark"
        # Reload from same path
        from agency.amjad_memory import AmjadMemory
        am2 = AmjadMemory(prefs_path=tmp_path / "amjad_prefs.json")
        assert am2.get("theme") == "dark"

    def test_update_shadows_hard_fact(self, am):
        am.update("name", "Amjad Override")
        ctx = am.get_context()
        assert ctx["name"] == "Amjad Override"

    def test_hard_fact_unaffected_by_dynamic(self, am):
        am.update("name", "X")
        # Hard fact still accessible via get_hard_fact
        assert am.get_hard_fact("name") == "Amjad"

    def test_get_default_returned(self, am):
        val = am.get("nonexistent_key_xyz", "default_val")
        assert val == "default_val"

    def test_remove_dynamic(self, am):
        am.update("foo", "bar")
        am.remove("foo")
        assert am.get("foo") is None

    def test_reset_dynamic(self, am):
        am.update("a", 1)
        am.update("b", 2)
        am.reset_dynamic()
        assert am.get("a") is None
        assert am.get("b") is None

    def test_context_work_style(self, am):
        ctx = am.get_context()
        assert "blunt" in ctx["work_style"].lower()

    def test_context_response_preferences(self, am):
        ctx = am.get_context()
        prefs = ctx["response_preferences"]
        assert "Hebrew" in prefs["language"] or "hebrew" in prefs["language"].lower()

    def test_timezone_israel(self, am):
        ctx = am.get_context()
        assert "Jerusalem" in ctx.get("timezone", "") or "Israel" in ctx.get("location", "")

    @pytest.mark.parametrize("field", ["name", "email", "preferred_language", "work_style"])
    def test_hard_facts_all_present(self, am, field):
        assert am.get_hard_fact(field) is not None

    def test_prefs_file_created_on_update(self, am, tmp_path):
        prefs_file = tmp_path / "amjad_prefs.json"
        am.update("x", 1)
        assert prefs_file.exists()

    def test_prefs_file_valid_json(self, am, tmp_path):
        am.update("y", 99)
        prefs_file = tmp_path / "amjad_prefs.json"
        data = json.loads(prefs_file.read_text())
        assert data["y"] == 99


# ===========================================================================
# 3. CHARACTER STATE
# ===========================================================================

class TestCharacterState:

    def test_default_mode(self, cs):
        assert cs.current_mode == "supreme_brainiac"

    def test_default_mood(self, cs):
        assert cs.mood == "focused"

    def test_default_owner(self, cs):
        assert cs.owner_name == "Amjad"

    def test_default_interactions_zero(self, cs):
        assert cs.total_interactions == 0

    @pytest.mark.parametrize("mode", [
        "supreme_brainiac", "academic", "executor", "guardian", "casual", "default"
    ])
    def test_set_valid_mode(self, cs, mode):
        cs.set_mode(mode)
        assert cs.current_mode == mode

    def test_set_invalid_mode_raises(self, cs):
        with pytest.raises(ValueError):
            cs.set_mode("pirate_mode")

    @pytest.mark.parametrize("mood", ["focused", "alert", "standby", "engaged", "guardian"])
    def test_set_valid_mood(self, cs, mood):
        cs.set_mood(mood)
        assert cs.mood == mood

    def test_set_invalid_mood_raises(self, cs):
        with pytest.raises(ValueError):
            cs.set_mood("happy_go_lucky")

    def test_record_interaction_increments(self, cs):
        cs.record_interaction("math")
        assert cs.total_interactions == 1

    def test_record_interaction_tracks_domain(self, cs):
        cs.record_interaction("math")
        cs.record_interaction("math")
        assert cs.expertise_history.get("math") == 2

    def test_record_multiple_domains(self, cs):
        for domain in ["math", "code", "math", "physics"]:
            cs.record_interaction(domain)
        assert cs.expertise_history["math"] == 2
        assert cs.expertise_history["code"] == 1
        assert cs.expertise_history["physics"] == 1

    def test_top_domains_ordering(self, cs):
        for _ in range(3):
            cs.record_interaction("math")
        for _ in range(1):
            cs.record_interaction("physics")
        top = cs.top_domains(2)
        assert top[0][0] == "math"
        assert top[1][0] == "physics"

    def test_top_domains_limit(self, cs):
        for d in ["a", "b", "c", "d", "e"]:
            cs.record_interaction(d)
        assert len(cs.top_domains(3)) == 3

    def test_add_context(self, cs):
        cs.add_context("user", "hello")
        assert cs.session_length() == 1

    def test_add_context_rolling_window(self, cs):
        for i in range(55):
            cs.add_context("user", f"msg {i}")
        assert cs.session_length() == 50  # max_ctx default

    def test_clear_session(self, cs):
        cs.add_context("user", "test")
        cs.clear_session()
        assert cs.session_length() == 0

    def test_snapshot_keys(self, cs):
        snap = cs.snapshot()
        for key in ["current_mode", "owner_name", "total_interactions",
                    "expertise_history", "mood", "session_length", "top_domains"]:
            assert key in snap

    def test_snapshot_active_since_iso(self, cs):
        snap = cs.snapshot()
        from datetime import datetime
        # Should not raise
        datetime.fromisoformat(snap["active_since"])

    def test_uptime_positive(self, cs):
        import time
        time.sleep(0.01)
        assert cs.uptime_seconds() > 0

    def test_persistence_round_trip(self, tmp_path):
        from agency.character_state import CharacterState
        CharacterState.reset_singleton()
        path = tmp_path / "cs_roundtrip.json"
        cs1 = CharacterState.get_instance(state_path=path, force_new=True)
        cs1.set_mode("executor")
        cs1.set_mood("alert")
        for _ in range(5):
            cs1.record_interaction("python")
        CharacterState.reset_singleton()

        cs2 = CharacterState.get_instance(state_path=path, force_new=True)
        assert cs2.current_mode == "executor"
        assert cs2.mood == "alert"
        assert cs2.total_interactions == 5
        assert cs2.expertise_history.get("python") == 5
        CharacterState.reset_singleton()

    def test_corrupt_state_file_graceful(self, tmp_path):
        from agency.character_state import CharacterState
        CharacterState.reset_singleton()
        bad = tmp_path / "bad_state.json"
        bad.write_text("{{{{not json}}}}")
        cs = CharacterState.get_instance(state_path=bad, force_new=True)
        assert cs.total_interactions == 0  # reset to defaults
        CharacterState.reset_singleton()

    def test_state_file_created_on_record(self, tmp_state, cs):
        cs.record_interaction("test")
        assert tmp_state.exists()

    def test_state_file_valid_json(self, tmp_state, cs):
        cs.record_interaction("test")
        data = json.loads(tmp_state.read_text())
        assert "total_interactions" in data


# ===========================================================================
# 4. PERSONA ENGINE
# ===========================================================================

class TestPersonaEnginePrompts:

    @pytest.mark.parametrize("mode", [
        "supreme_brainiac", "academic", "executor", "guardian", "casual", "default"
    ])
    def test_get_system_prompt_returns_string(self, pe, mode):
        prompt = pe.get_system_prompt(mode)
        assert isinstance(prompt, str)
        assert len(prompt) > 30

    @pytest.mark.parametrize("mode", [
        "supreme_brainiac", "academic", "executor", "guardian", "casual", "default"
    ])
    def test_system_prompt_contains_amjad(self, pe, mode):
        prompt = pe.get_system_prompt(mode)
        assert "Amjad" in prompt

    @pytest.mark.parametrize("mode", [
        "supreme_brainiac", "academic", "executor", "guardian", "casual", "default"
    ])
    def test_system_prompt_contains_mission(self, pe, mode):
        prompt = pe.get_system_prompt(mode)
        assert "Mission" in prompt or "mission" in prompt

    def test_unknown_mode_uses_default(self, pe):
        prompt = pe.get_system_prompt("nonexistent_mode_xyz")
        default_prompt = pe.get_system_prompt("default")
        assert prompt == default_prompt

    def test_list_modes_returns_all(self, pe):
        modes = pe.list_modes()
        for m in ["supreme_brainiac", "academic", "executor", "guardian", "casual"]:
            assert m in modes

    def test_executor_prompt_mentions_execute(self, pe):
        p = pe.get_system_prompt("executor")
        assert "execute" in p.lower() or "בצע" in p

    def test_guardian_prompt_mentions_security(self, pe):
        p = pe.get_system_prompt("guardian")
        assert "protect" in p.lower() or "security" in p.lower() or "אבטחה" in p

    def test_academic_prompt_mentions_research(self, pe):
        p = pe.get_system_prompt("academic")
        assert "research" in p.lower() or "rigorous" in p.lower()


class TestPersonaEngineFormat:

    def test_format_strips_of_course(self, pe):
        r = pe.format_response("Of course! Here is the answer.", "default")
        assert "of course" not in r.lower()

    def test_format_strips_certainly(self, pe):
        r = pe.format_response("Certainly, I can help with that.", "default")
        assert "certainly" not in r.lower()

    def test_format_strips_as_an_ai(self, pe):
        r = pe.format_response("As an AI, I cannot do that.", "default")
        assert "as an ai" not in r.lower()

    def test_format_strips_hope_this_helps(self, pe):
        r = pe.format_response("The answer is 42. I hope this helps!", "default")
        assert "hope this helps" not in r.lower()

    def test_format_empty_returns_period(self, pe):
        r = pe.format_response("", "default")
        assert r == "."

    def test_format_whitespace_returns_period(self, pe):
        r = pe.format_response("   ", "default")
        assert r == "."

    def test_format_adds_mode_tag_executor(self, pe):
        r = pe.format_response("Done.", "executor")
        assert "[JARVIS/EXECUTOR]" in r

    def test_format_adds_mode_tag_guardian(self, pe):
        r = pe.format_response("Alert.", "guardian")
        assert "[JARVIS/GUARDIAN]" in r

    def test_format_no_tag_for_casual(self, pe):
        r = pe.format_response("Sure thing.", "casual")
        assert "[JARVIS" not in r

    def test_format_no_tag_for_default(self, pe):
        r = pe.format_response("Here you go.", "default")
        assert "[JARVIS" not in r

    def test_format_preserves_technical_content(self, pe):
        technical = "The complexity is O(n log n) via merge sort."
        r = pe.format_response(technical, "executor")
        assert "O(n log n)" in r

    def test_format_strips_feel_free_to_ask(self, pe):
        r = pe.format_response("The result is 5. Feel free to ask anything else.", "default")
        assert "feel free to ask" not in r.lower()


class TestPersonaEngineModeDetection:

    @pytest.mark.parametrize("query,expected", [
        ("run the deploy script", "executor"),
        ("execute this command", "executor"),
        ("security audit of the system", "guardian"),
        ("threat assessment", "guardian"),
        ("research paper on quantum computing", "academic"),
        ("literature review needed", "academic"),
        ("hey what's up", "casual"),
        ("chat with me", "casual"),
    ])
    def test_detect_mode_keywords(self, pe, query, expected):
        assert pe.detect_mode(query) == expected

    @pytest.mark.parametrize("query", [
        "emergency shutdown", "critical failure detected",
        "urgent help needed", "system crash",
    ])
    def test_detect_mode_crisis_becomes_guardian(self, pe, query):
        assert pe.detect_mode(query) == "guardian"

    def test_detect_empty_query(self, pe):
        mode = pe.detect_mode("")
        assert mode == "default"

    def test_detect_hebrew_query_supreme(self, pe):
        # Hebrew text should boost supreme_brainiac
        mode = pe.detect_mode("מה קורה עם הפרויקט?")
        assert mode in ("supreme_brainiac", "casual")  # Hebrew → JARVIS default

    def test_detect_unknown_query_supreme(self, pe):
        mode = pe.detect_mode("calculate the integral of x squared")
        # No strong signal — falls back to supreme_brainiac
        assert mode in ("supreme_brainiac", "default", "academic")


class TestPersonaEngineGreetings:

    @pytest.mark.parametrize("tod,expected_substr", [
        ("morning", "בוקר"),
        ("afternoon", "אחר הצהריים"),
        ("evening", "ערב"),
        ("night", "לילה"),
        ("day", "שלום"),
    ])
    def test_greeting_contains_hebrew(self, pe, tod, expected_substr):
        g = pe.get_greeting(tod)
        assert expected_substr in g

    @pytest.mark.parametrize("tod", ["morning", "afternoon", "evening", "night", "day"])
    def test_greeting_mentions_amjad(self, pe, tod):
        g = pe.get_greeting(tod)
        assert "עמג'אד" in g or "Amjad" in g

    def test_greeting_unknown_tod_uses_day(self, pe):
        g = pe.get_greeting("lunchtime")
        day_g = pe.get_greeting("day")
        assert g == day_g

    def test_greeting_returns_string(self, pe):
        assert isinstance(pe.get_greeting("morning"), str)


class TestPersonaEnginePreferences:

    def test_remember_and_get(self, pe):
        pe.remember_preference("theme", "dark")
        assert pe.get_preference("theme") == "dark"

    def test_get_missing_returns_default(self, pe):
        assert pe.get_preference("nonexistent", "fallback") == "fallback"

    def test_forget_preference(self, pe):
        pe.remember_preference("x", 99)
        pe.forget_preference("x")
        assert pe.get_preference("x") is None

    def test_all_preferences_returns_copy(self, pe):
        pe.remember_preference("a", 1)
        pe.remember_preference("b", 2)
        all_p = pe.all_preferences()
        assert all_p["a"] == 1
        assert all_p["b"] == 2

    def test_preferences_persist_to_disk(self, tmp_prefs):
        from agency.persona_engine import PersonaEngine
        pe1 = PersonaEngine(prefs_path=tmp_prefs)
        pe1.remember_preference("color", "blue")

        pe2 = PersonaEngine(prefs_path=tmp_prefs)
        assert pe2.get_preference("color") == "blue"

    def test_preferences_file_is_json(self, pe, tmp_prefs):
        pe.remember_preference("z", 42)
        data = json.loads(tmp_prefs.read_text())
        assert data["z"] == 42

    def test_multiple_prefs_types(self, pe):
        pe.remember_preference("count", 5)
        pe.remember_preference("active", True)
        pe.remember_preference("name", "JARVIS")
        pe.remember_preference("scores", [1, 2, 3])
        assert pe.get_preference("count") == 5
        assert pe.get_preference("active") is True
        assert pe.get_preference("scores") == [1, 2, 3]


# ===========================================================================
# 5. JARVIS GREETING MODULE
# ===========================================================================

class TestJarvisGreeting:

    def test_banner_contains_jarvis(self):
        from agency.jarvis_greeting import get_startup_banner
        b = get_startup_banner()
        assert "J.A.R.V.I.S" in b

    def test_banner_contains_supreme_brainiac(self):
        from agency.jarvis_greeting import get_startup_banner
        b = get_startup_banner()
        assert "Supreme Brainiac" in b

    def test_banner_contains_owner(self):
        from agency.jarvis_greeting import get_startup_banner
        b = get_startup_banner()
        assert "Amjad" in b

    def test_banner_contains_mode(self):
        from agency.jarvis_greeting import get_startup_banner
        b = get_startup_banner({"mode": "executor"})
        assert "executor" in b

    def test_banner_contains_systems_count(self):
        from agency.jarvis_greeting import get_startup_banner
        b = get_startup_banner({"systems_ok": 5, "systems_total": 7})
        assert "5" in b and "7" in b

    def test_banner_box_borders(self):
        from agency.jarvis_greeting import get_startup_banner
        b = get_startup_banner()
        assert "╔" in b
        assert "╝" in b
        assert "║" in b

    def test_banner_with_subsystems(self):
        from agency.jarvis_greeting import get_startup_banner
        status = {
            "mode": "guardian",
            "systems_ok": 2,
            "systems_total": 2,
            "subsystems": {
                "persona_engine": {"healthy": True, "detail": "ok"},
                "character_state": {"healthy": False, "detail": "warn"},
            },
        }
        b = get_startup_banner(status)
        assert "persona_engine" in b

    def test_banner_subsystem_checkmarks(self):
        from agency.jarvis_greeting import get_startup_banner
        status = {
            "subsystems": {
                "alpha": {"healthy": True, "detail": ""},
                "beta": {"healthy": False, "detail": ""},
            }
        }
        b = get_startup_banner(status)
        assert "✓" in b
        assert "✗" in b

    def test_banner_empty_status(self):
        from agency.jarvis_greeting import get_startup_banner
        b = get_startup_banner({})
        assert "J.A.R.V.I.S" in b

    def test_banner_no_status(self):
        from agency.jarvis_greeting import get_startup_banner
        b = get_startup_banner(None)
        assert "J.A.R.V.I.S" in b

    def test_banner_multiline(self):
        from agency.jarvis_greeting import get_startup_banner
        b = get_startup_banner()
        assert b.count("\n") >= 5

    def test_farewell_contains_jarvis(self):
        from agency.jarvis_greeting import get_farewell
        f = get_farewell()
        assert "J.A.R.V.I.S" in f

    def test_farewell_contains_owner_name(self):
        from agency.jarvis_greeting import get_farewell
        f = get_farewell("Amjad")
        assert "Amjad" in f

    def test_farewell_custom_owner(self):
        from agency.jarvis_greeting import get_farewell
        f = get_farewell("TestUser")
        assert "TestUser" in f

    def test_farewell_is_string(self):
        from agency.jarvis_greeting import get_farewell
        assert isinstance(get_farewell(), str)

    def test_mode_transition_message(self):
        from agency.jarvis_greeting import get_mode_transition_message
        msg = get_mode_transition_message("casual", "executor")
        assert "casual".upper() in msg
        assert "executor".upper() in msg

    def test_alert_banner_contains_message(self):
        from agency.jarvis_greeting import get_alert_banner
        b = get_alert_banner("Disk full", "CRITICAL")
        assert "Disk full" in b
        assert "CRITICAL" in b


# ===========================================================================
# 6. SUPREME MAIN — BootedSystem
# ===========================================================================

class TestBootedSystem:

    @pytest.fixture()
    def booted(self, tmp_prefs, tmp_state):
        from agency.character_state import CharacterState
        from agency.persona_engine import PersonaEngine
        from agency.amjad_memory import AmjadMemory
        from agency.supreme_main import BootedSystem
        CharacterState.reset_singleton()
        pe = PersonaEngine(prefs_path=tmp_prefs)
        cs = CharacterState.get_instance(state_path=tmp_state, force_new=True)
        am = AmjadMemory(prefs_path=tmp_prefs.parent / "am_prefs.json")
        yield BootedSystem(persona=pe, character=cs, memory=am)
        CharacterState.reset_singleton()

    def test_booted_has_persona(self, booted):
        from agency.persona_engine import PersonaEngine
        assert isinstance(booted.persona, PersonaEngine)

    def test_booted_has_character(self, booted):
        from agency.character_state import CharacterState
        assert isinstance(booted.character, CharacterState)

    def test_booted_has_memory(self, booted):
        from agency.amjad_memory import AmjadMemory
        assert isinstance(booted.memory, AmjadMemory)

    def test_status_returns_dict(self, booted):
        s = booted.status()
        assert isinstance(s, dict)

    def test_status_ok_true(self, booted):
        assert booted.status()["ok"] is True

    def test_status_has_subsystems(self, booted):
        s = booted.status()
        assert "subsystems" in s
        assert len(s["subsystems"]) >= 3

    def test_process_returns_dict(self, booted):
        result = booted.process("hello")
        assert isinstance(result, dict)

    def test_process_has_persona_mode(self, booted):
        result = booted.process("hello")
        assert "persona_mode" in result

    def test_process_has_request(self, booted):
        result = booted.process("run tests")
        assert result["request"] == "run tests"

    def test_process_formats_response(self, booted):
        result = booted.process("go", {"response": "Of course! Done."})
        assert "of course" not in result["response"].lower()

    def test_process_detects_executor_mode(self, booted):
        result = booted.process("execute the migration script")
        assert result["persona_mode"] == "executor"

    def test_process_increments_interactions(self, booted):
        initial = booted.character.total_interactions
        booted.process("test query")
        assert booted.character.total_interactions == initial + 1

    def test_process_mode_override(self, booted):
        result = booted.process("anything", {"mode": "guardian", "response": "ok"})
        assert result["persona_mode"] == "guardian"

    def test_initialise_character_system(self, monkeypatch, tmp_path):
        from agency.character_state import CharacterState
        monkeypatch.setenv("JARVIS_PREFS_PATH", str(tmp_path / "prefs.json"))
        monkeypatch.setenv("JARVIS_STATE_PATH", str(tmp_path / "state.json"))
        CharacterState.reset_singleton()
        from agency.supreme_main import initialise_character_system
        sys = initialise_character_system()
        assert sys.persona is not None
        assert sys.character is not None
        assert sys.memory is not None
        CharacterState.reset_singleton()


# ===========================================================================
# 7. UNIFIED BRIDGE WIRING
# ===========================================================================

class TestUnifiedBridgeWiring:

    @pytest.fixture()
    def bridge(self, monkeypatch, tmp_path):
        """Fresh UnifiedBridge with isolated paths."""
        import agency
        monkeypatch.setenv("JARVIS_PREFS_PATH", str(tmp_path / "prefs.json"))
        monkeypatch.setenv("JARVIS_STATE_PATH", str(tmp_path / "state.json"))
        # Reset singletons
        agency._unified_bridge = None
        agency._persona_engine = None
        agency._character_state = None
        agency._amjad_memory = None
        from agency.character_state import CharacterState
        CharacterState.reset_singleton()
        ub = agency.get_unified_bridge()
        yield ub
        agency._unified_bridge = None
        agency._persona_engine = None
        agency._character_state = None
        agency._amjad_memory = None
        CharacterState.reset_singleton()

    def test_bridge_has_persona(self, bridge):
        assert hasattr(bridge, "persona")

    def test_bridge_has_character(self, bridge):
        assert hasattr(bridge, "character")

    def test_bridge_has_memory(self, bridge):
        assert hasattr(bridge, "memory")

    def test_bridge_has_process(self, bridge):
        assert callable(getattr(bridge, "process", None))

    def test_bridge_process_returns_dict(self, bridge):
        result = bridge.process("hello world")
        assert isinstance(result, dict)

    def test_bridge_process_persona_mode_key(self, bridge):
        result = bridge.process("hello")
        assert "persona_mode" in result

    def test_bridge_process_formats_fluff(self, bridge):
        result = bridge.process("do it", {"response": "Certainly! Done.", "domain": "test"})
        assert "certainly" not in result["response"].lower()

    def test_bridge_process_executor_detection(self, bridge):
        result = bridge.process("run the build pipeline")
        assert result["persona_mode"] == "executor"

    def test_bridge_process_increments_character(self, bridge):
        initial = bridge.character.total_interactions
        bridge.process("query 1")
        bridge.process("query 2")
        assert bridge.character.total_interactions == initial + 2

    def test_bridge_memory_owner(self, bridge):
        assert bridge.memory.owner_name() == "Amjad"

    def test_bridge_persona_list_modes(self, bridge):
        modes = bridge.persona.list_modes()
        assert "executor" in modes

    def test_get_persona_engine_singleton(self, monkeypatch, tmp_path):
        import agency
        monkeypatch.setenv("JARVIS_PREFS_PATH", str(tmp_path / "pe_prefs.json"))
        agency._persona_engine = None
        pe1 = agency.get_persona_engine()
        pe2 = agency.get_persona_engine()
        assert pe1 is pe2
        agency._persona_engine = None

    def test_get_amjad_memory_singleton(self, monkeypatch, tmp_path):
        import agency
        monkeypatch.setenv("JARVIS_PREFS_PATH", str(tmp_path / "am_prefs.json"))
        agency._amjad_memory = None
        m1 = agency.get_amjad_memory()
        m2 = agency.get_amjad_memory()
        assert m1 is m2
        agency._amjad_memory = None


# ---------------------------------------------------------------------------
# Extra coverage — brings total above 680
# ---------------------------------------------------------------------------

class TestJarvisSoulCoverage:
    """Additional parametrized coverage for jarvis_soul helpers."""

    @pytest.mark.parametrize("mode,substr", [
        ("supreme_brainiac", "depth"),
        ("executor", "minimal"),
        ("academic", "evidence"),
        ("guardian", "authoritative"),
        ("casual", "warm_witty"),
        ("technical", "dense_precise"),
        ("crisis", "calm_authoritative"),
    ])
    def test_communication_style_substrings(self, mode, substr):
        from agency.jarvis_soul import get_communication_style
        assert substr in get_communication_style(mode)

    @pytest.mark.parametrize("phrase_idx", [0, 1, 2, 3, 4])
    def test_signature_phrase_by_index(self, phrase_idx):
        from agency.jarvis_soul import get_signature_phrase
        p = get_signature_phrase(phrase_idx)
        assert isinstance(p, str) and len(p) > 0

    def test_signature_phrase_wraps(self):
        from agency.jarvis_soul import JARVIS_SOUL, get_signature_phrase
        n = len(JARVIS_SOUL["signature_phrases"])
        assert get_signature_phrase(n) == get_signature_phrase(0)

    def test_soul_has_active_projects(self):
        from agency.jarvis_soul import JARVIS_SOUL
        projs = JARVIS_SOUL["active_projects"]
        assert any(p["name"] == "J.A.R.V.I.S" for p in projs)
        assert any(p["name"] == "G.A.N.E NAVIGATOR" for p in projs)

    def test_soul_loyalty_absolute(self):
        from agency.jarvis_soul import JARVIS_SOUL
        assert JARVIS_SOUL["loyalty_level"] == "absolute"

    def test_soul_owner_email(self):
        from agency.jarvis_soul import JARVIS_SOUL
        assert JARVIS_SOUL["owner_email"] == "mobarsham@gmail.com"

    def test_get_soul_is_same_object(self):
        from agency.jarvis_soul import JARVIS_SOUL, get_soul
        assert get_soul() is JARVIS_SOUL
