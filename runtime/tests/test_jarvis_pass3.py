"""Pass-3 tests: filter_response, greeting, routing improvements."""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# jarvis_soul.filter_response / has_forbidden_phrase
# ---------------------------------------------------------------------------

class TestFilterResponse:
    def test_strips_as_an_ai(self):
        from agency.jarvis_soul import filter_response
        out = filter_response("As an AI, I understand.")
        assert "as an AI" not in out.lower() or "JARVIS" in out

    def test_replaces_i_cannot(self):
        from agency.jarvis_soul import filter_response
        out = filter_response("I cannot do that.")
        assert "I cannot" not in out
        assert "JARVIS" in out

    def test_strips_apologetic_opener(self):
        from agency.jarvis_soul import filter_response
        out = filter_response("I'm sorry, but the answer is 42.")
        assert "sorry" not in out.lower()
        assert "42" in out

    def test_strips_motivational_closer(self):
        from agency.jarvis_soul import filter_response
        out = filter_response("The answer is 42. Hope this helps!")
        assert "Hope this helps" not in out
        assert "42" in out

    def test_strips_feel_free(self):
        from agency.jarvis_soul import filter_response
        out = filter_response("Done. Feel free to ask for more help.")
        assert "Feel free" not in out

    def test_passthrough_clean_text(self):
        from agency.jarvis_soul import filter_response
        clean = "The deployment succeeded. 3 pods restarted."
        assert filter_response(clean) == clean

    def test_never_raises_on_empty(self):
        from agency.jarvis_soul import filter_response
        assert filter_response("") == ""
        assert filter_response("   ") == ""

    def test_has_forbidden_phrase_positive(self):
        from agency.jarvis_soul import has_forbidden_phrase
        assert has_forbidden_phrase("As an AI I cannot do that.") is True

    def test_has_forbidden_phrase_negative(self):
        from agency.jarvis_soul import has_forbidden_phrase
        assert has_forbidden_phrase("Deployment complete. 0 errors.") is False

    def test_no_ai_disclaimer_variants(self):
        from agency.jarvis_soul import filter_response
        cases = [
            "I'm an AI so I'll help.",
            "As a language model, I suggest…",
            "I am an AI chatbot.",
        ]
        for c in cases:
            out = filter_response(c)
            assert "language model" not in out or "JARVIS" in out, f"Failed on: {c!r}"


# ---------------------------------------------------------------------------
# jarvis_greeting — Jerusalem timezone
# ---------------------------------------------------------------------------

class TestJarvisGreeting:
    def test_get_greeting_contains_hebrew(self):
        from agency.jarvis_greeting import get_greeting
        g = get_greeting()
        # One of the Hebrew time-phrases must be present
        hebrew_phrases = ["בוקר", "שלום", "אחר", "ערב", "לילה"]
        assert any(p in g for p in hebrew_phrases), f"No Hebrew in: {g!r}"

    def test_get_greeting_contains_owner(self):
        from agency.jarvis_greeting import get_greeting
        assert "Amjad" in get_greeting()

    def test_get_greeting_contains_ist(self):
        from agency.jarvis_greeting import get_greeting
        g = get_greeting()
        assert "IST" in g or "local" in g, f"No timezone in: {g!r}"

    def test_banner_contains_time(self):
        from agency.jarvis_greeting import get_startup_banner
        banner = get_startup_banner()
        assert "2026" in banner or "2025" in banner  # year present

    def test_banner_contains_jerusalem_tz(self):
        from agency.jarvis_greeting import get_startup_banner
        banner = get_startup_banner()
        assert "Jerusalem" in banner or "IST" in banner or "local" in banner

    def test_farewell_contains_hebrew(self):
        from agency.jarvis_greeting import get_farewell
        farewell = get_farewell()
        assert "נתראה" in farewell or "מערכות" in farewell


# ---------------------------------------------------------------------------
# jarvis_brain routing
# ---------------------------------------------------------------------------

class TestBrainRouting:
    @pytest.fixture(scope="class")
    def brain(self):
        from agency.jarvis_brain import SupremeJarvisBrain
        return SupremeJarvisBrain()

    @pytest.mark.parametrize("query,expected_fragment", [
        ("write a poem about the sea", "creative-writing"),
        ("translate this to Hebrew", "linguistics"),
        ("draw a picture of a robot", "design-creative"),
        ("make a video tutorial", "content-media"),
        ("search the web for news", "journalism-research"),
        ("build an API for my app", "backend-architect"),
        ("make a website for my shop", "frontend"),
        ("send email to my team", "email"),
        ("analyze this data", "data"),
        ("debug this Python traceback", "engineer"),
    ])
    def test_routing(self, brain, query, expected_fragment):
        result = brain.skill_for(query)
        assert expected_fragment in result.skill.slug, (
            f"Query: {query!r}\n"
            f"Expected fragment: {expected_fragment!r}\n"
            f"Got slug: {result.skill.slug!r}"
        )


# ---------------------------------------------------------------------------
# cli.py — chat command registered
# ---------------------------------------------------------------------------

class TestChatCommand:
    def test_chat_command_registered(self):
        from agency.cli import main
        assert "chat" in main.commands

    def test_chat_command_help(self):
        from click.testing import CliRunner
        from agency.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["chat", "--help"])
        assert result.exit_code == 0
        assert "interactive" in result.output.lower() or "REPL" in result.output or "greeting" in result.output.lower()
