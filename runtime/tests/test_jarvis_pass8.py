"""Pass 8 — CI health, integration paths, and final hardening.

Covers:
- Full routing pipeline: input → RouteResult → valid slug
- Full filter pipeline: forbidden phrases in → clean output
- Memory persistence: write → read back from disk
- Trust mode: env var → TrustMode enum
- Greeting: get_greeting() structure (Hebrew, time, owner name)
- Banner: get_startup_banner() contains expected fields
- CLI --help exits 0
- 20 diverse routing queries all return non-None slugs
- Hebrew-script query routes without crashing
- Very long query (10 KB) doesn't raise
- filter_response never raises on adversarial input
- AmjadMemory hard facts immutable baseline
- AmjadMemory dynamic override shadows hard fact
- AmjadMemory reset_dynamic reverts overrides
- has_forbidden_phrase detects forbidden text
- JARVIS_SOUL contains required identity keys
- get_farewell returns owner name and Hebrew
- get_mode_transition_message arrow format
- get_alert_banner level injection
- RouteResult.to_dict is JSON-serialisable
- SupremeJarvisBrain.unified_prompt respects max_chars
- by_slug returns None for unknown slug
- top_k length ≤ k
- _tokenize strips stopwords
- _bigrams returns correct pairs
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def brain():
    from agency.jarvis_brain import SupremeJarvisBrain
    return SupremeJarvisBrain()


@pytest.fixture
def mem(tmp_path):
    from agency.amjad_memory import AmjadMemory
    return AmjadMemory(prefs_path=tmp_path / "prefs.json")


# ---------------------------------------------------------------------------
# 1. Full routing pipeline
# ---------------------------------------------------------------------------


class TestRoutingPipeline:

    def test_route_returns_non_none_skill(self, brain):
        result = brain.skill_for("build a React component")
        assert result is not None
        assert result.skill is not None

    def test_route_returns_non_empty_slug(self, brain):
        result = brain.skill_for("debug a Python traceback")
        assert result.skill.slug
        assert len(result.skill.slug) > 0

    def test_route_score_positive(self, brain):
        result = brain.skill_for("analyse data with SQL BigQuery")
        assert result.score > 0

    def test_route_candidates_non_empty(self, brain):
        result = brain.skill_for("write a React frontend app")
        assert len(result.candidates) >= 1

    def test_route_rationale_non_empty(self, brain):
        result = brain.skill_for("build kubernetes helm charts")
        assert result.rationale
        assert len(result.rationale) > 0

    def test_route_to_dict_is_json_serialisable(self, brain):
        result = brain.skill_for("design a REST API microservice")
        d = result.to_dict()
        serialised = json.dumps(d)  # must not raise
        parsed = json.loads(serialised)
        assert parsed["skill"] == result.skill.slug
        assert "score" in parsed
        assert "rationale" in parsed

    def test_empty_request_raises_value_error(self, brain):
        with pytest.raises(ValueError):
            brain.skill_for("")

    def test_whitespace_only_raises_value_error(self, brain):
        with pytest.raises(ValueError):
            brain.skill_for("   ")

    # 20 diverse queries — all must return a valid slug
    @pytest.mark.parametrize("query", [
        "build a react component with TypeScript",
        "debug this python traceback AttributeError",
        "translate hello to Hebrew",
        "analyse data with SQL and BigQuery",
        "write a poem about the moon",
        "deploy kubernetes helm chart to production",
        "create a video about product launch",
        "design a landing page with Tailwind CSS",
        "machine learning model training pipeline",
        "send an email to the team",
        "pen test the web application OWASP",
        "write a short story about space exploration",
        "fix a bug in the authentication flow",
        "manage OKRs and performance reviews",
        "CRISPR genomics research paper summary",
        "dashboard for sales pipeline metrics",
        "build a REST API with FastAPI",
        "create a Figma design system component",
        "quantitative trading alpha strategy",
        "smart city IoT sensor integration",
    ])
    def test_diverse_query_routes_to_valid_slug(self, brain, query):
        result = brain.skill_for(query)
        assert result.skill.slug, f"no slug for: {query!r}"


# ---------------------------------------------------------------------------
# 2. Filter pipeline
# ---------------------------------------------------------------------------


class TestFilterPipeline:

    def test_strips_certainly_phrase(self):
        from agency.jarvis_soul import filter_response
        text = "Certainly! Here is the answer."
        out = filter_response(text)
        assert "Certainly!" not in out

    def test_strips_of_course_phrase(self):
        from agency.jarvis_soul import filter_response
        text = "Of course! I am happy to help you with that."
        out = filter_response(text)
        assert "Of course!" not in out

    def test_strips_hope_this_helps(self):
        from agency.jarvis_soul import filter_response
        text = "Here is the code. Hope this helps!"
        out = filter_response(text)
        assert "Hope this helps" not in out

    def test_passthrough_clean_text(self):
        from agency.jarvis_soul import filter_response
        text = "Deploy with: kubectl apply -f deploy.yaml"
        out = filter_response(text)
        assert "kubectl" in out

    def test_empty_string_passthrough(self):
        from agency.jarvis_soul import filter_response
        assert filter_response("") == ""

    def test_never_raises_on_adversarial_input(self):
        from agency.jarvis_soul import filter_response
        # None-like, unicode, very long
        assert filter_response("a" * 50_000) is not None
        assert filter_response("الله أكبر مرحبا") is not None
        assert filter_response("\x00\x01\x02") is not None

    def test_has_forbidden_phrase_detects(self):
        from agency.jarvis_soul import has_forbidden_phrase
        assert has_forbidden_phrase("Certainly! Let me help you.")

    def test_has_forbidden_phrase_clean(self):
        from agency.jarvis_soul import has_forbidden_phrase
        assert not has_forbidden_phrase("Run: python main.py")


# ---------------------------------------------------------------------------
# 3. Memory persistence
# ---------------------------------------------------------------------------


class TestMemoryPersistence:

    def test_hard_fact_name(self, mem):
        assert mem.get_hard_fact("name") == "Amjad"

    def test_hard_fact_email(self, mem):
        assert mem.get_hard_fact("email") == "mobarsham@gmail.com"

    def test_dynamic_override_write_read(self, mem):
        mem.update("test_key", "test_value")
        assert mem.get("test_key") == "test_value"

    def test_dynamic_persists_to_disk(self, tmp_path):
        from agency.amjad_memory import AmjadMemory
        p = tmp_path / "prefs.json"
        m1 = AmjadMemory(prefs_path=p)
        m1.update("colour", "blue")
        # Re-open from same path
        m2 = AmjadMemory(prefs_path=p)
        assert m2.get("colour") == "blue"

    def test_dynamic_shadows_hard_fact(self, mem):
        original = mem.get_hard_fact("preferred_language")
        mem.update("preferred_language", "klingon")
        assert mem.get("preferred_language") == "klingon"
        # Hard fact unchanged
        assert mem.get_hard_fact("preferred_language") == original

    def test_reset_dynamic_reverts(self, mem):
        mem.update("preferred_language", "klingon")
        mem.reset_dynamic()
        assert mem.get("preferred_language") == mem.get_hard_fact("preferred_language")

    def test_get_context_contains_all_keys(self, mem):
        ctx = mem.get_context()
        for key in ("name", "email", "preferred_language", "dislikes", "loves"):
            assert key in ctx, f"missing key: {key}"

    def test_owner_name(self, mem):
        assert mem.owner_name() == "Amjad"

    def test_primary_language(self, mem):
        assert mem.primary_language() == "hebrew"


# ---------------------------------------------------------------------------
# 4. Trust mode via env var
# ---------------------------------------------------------------------------


class TestTrustMode:

    def test_off_by_default(self, monkeypatch):
        from agency.trust import current, TrustMode
        monkeypatch.delenv("AGENCY_TRUST_MODE", raising=False)
        monkeypatch.setenv("AGENCY_TRUST_CONF", "/nonexistent/path/trust.conf")
        mode = current()
        assert mode == TrustMode.OFF

    def test_on_my_machine_via_env(self, monkeypatch):
        from agency.trust import current, TrustMode
        monkeypatch.setenv("AGENCY_TRUST_MODE", "on-my-machine")
        mode = current()
        assert mode == TrustMode.ON_MY_MACHINE

    def test_yolo_via_env(self, monkeypatch):
        from agency.trust import current, TrustMode
        monkeypatch.setenv("AGENCY_TRUST_MODE", "yolo")
        mode = current()
        assert mode == TrustMode.YOLO

    def test_unknown_env_falls_back_to_off(self, monkeypatch):
        from agency.trust import current, TrustMode
        monkeypatch.setenv("AGENCY_TRUST_MODE", "ultra-godmode")
        monkeypatch.setenv("AGENCY_TRUST_CONF", "/nonexistent/path/trust.conf")
        mode = current()
        assert mode == TrustMode.OFF


# ---------------------------------------------------------------------------
# 5. Greeting
# ---------------------------------------------------------------------------


class TestGreeting:

    def test_greeting_contains_owner(self):
        from agency.jarvis_greeting import get_greeting
        g = get_greeting("Amjad")
        assert "Amjad" in g

    def test_greeting_contains_hebrew(self):
        from agency.jarvis_greeting import get_greeting
        g = get_greeting("Amjad")
        # Hebrew characters in the greeting (טוב, שלום, לילה, etc.)
        assert any(ord(c) > 0x0590 for c in g), "expected Hebrew characters in greeting"

    def test_greeting_contains_time_marker(self):
        from agency.jarvis_greeting import get_greeting
        g = get_greeting("Amjad")
        # Format is HH:MM IST or HH:MM local
        assert ":" in g

    def test_greeting_ends_with_mochen(self):
        from agency.jarvis_greeting import get_greeting
        g = get_greeting("Amjad")
        assert "מוכן" in g


# ---------------------------------------------------------------------------
# 6. Startup banner
# ---------------------------------------------------------------------------


class TestStartupBanner:

    def test_banner_contains_jarvis(self):
        from agency.jarvis_greeting import get_startup_banner
        b = get_startup_banner()
        assert "J.A.R.V.I.S" in b

    def test_banner_contains_owner(self):
        from agency.jarvis_greeting import get_startup_banner
        b = get_startup_banner()
        assert "Amjad" in b

    def test_banner_contains_mode(self):
        from agency.jarvis_greeting import get_startup_banner
        b = get_startup_banner({"mode": "supreme_brainiac"})
        assert "supreme_brainiac" in b

    def test_banner_contains_systems_count(self):
        from agency.jarvis_greeting import get_startup_banner
        b = get_startup_banner({"systems_ok": 7, "systems_total": 9})
        assert "7/9" in b

    def test_banner_subsystem_healthy_marker(self):
        from agency.jarvis_greeting import get_startup_banner
        b = get_startup_banner({
            "subsystems": {"routing": {"healthy": True, "detail": "ok"}},
        })
        assert "✓" in b

    def test_banner_is_multiline(self):
        from agency.jarvis_greeting import get_startup_banner
        b = get_startup_banner()
        assert b.count("\n") >= 5

    def test_farewell_contains_owner(self):
        from agency.jarvis_greeting import get_farewell
        f = get_farewell("Amjad")
        assert "Amjad" in f

    def test_farewell_contains_hebrew(self):
        from agency.jarvis_greeting import get_farewell
        f = get_farewell("Amjad")
        assert any(ord(c) > 0x0590 for c in f)

    def test_mode_transition_message_arrow(self):
        from agency.jarvis_greeting import get_mode_transition_message
        msg = get_mode_transition_message("guardian", "executor")
        assert "→" in msg
        assert "GUARDIAN" in msg
        assert "EXECUTOR" in msg

    def test_alert_banner_level(self):
        from agency.jarvis_greeting import get_alert_banner
        b = get_alert_banner("disk full", level="CRITICAL")
        assert "CRITICAL" in b
        assert "disk full" in b


# ---------------------------------------------------------------------------
# 7. JARVIS_SOUL structure
# ---------------------------------------------------------------------------


class TestJarvisSoul:

    def test_soul_has_owner(self):
        from agency.jarvis_soul import JARVIS_SOUL
        assert JARVIS_SOUL["owner"] == "Amjad"

    def test_soul_has_personality_traits(self):
        from agency.jarvis_soul import JARVIS_SOUL
        assert len(JARVIS_SOUL["personality_traits"]) > 0

    def test_soul_has_signature_phrases(self):
        from agency.jarvis_soul import JARVIS_SOUL
        assert len(JARVIS_SOUL["signature_phrases"]) > 0

    def test_soul_has_forbidden_behaviors(self):
        from agency.jarvis_soul import JARVIS_SOUL
        assert len(JARVIS_SOUL["forbidden_behaviors"]) > 0

    def test_soul_has_core_mission(self):
        from agency.jarvis_soul import JARVIS_SOUL
        assert "Amjad" in JARVIS_SOUL["core_mission"]


# ---------------------------------------------------------------------------
# 8. Brain helpers
# ---------------------------------------------------------------------------


class TestBrainHelpers:

    def test_by_slug_returns_skill(self, brain):
        # Pick a slug we know exists (grab the first one)
        first = list(brain.registry.all())[0]
        found = brain.by_slug(first.slug)
        assert found is not None
        assert found.slug == first.slug

    def test_by_slug_unknown_returns_none(self, brain):
        assert brain.by_slug("this-slug-does-not-exist-xyz") is None

    def test_top_k_length(self, brain):
        results = brain.top_k("python backend microservices", k=3)
        assert len(results) <= 3

    def test_top_k_sorted_descending(self, brain):
        results = brain.top_k("kubernetes devops pipeline", k=5)
        scores = [sc for _, sc in results]
        assert scores == sorted(scores, reverse=True)

    def test_unified_prompt_max_chars(self, brain):
        p = brain.unified_prompt(max_chars=500)
        assert len(p) <= 500

    def test_unified_prompt_with_request(self, brain):
        p = brain.unified_prompt(request="build a React dashboard", max_chars=20_000)
        assert "Activated Specialists" in p

    def test_very_long_query_no_crash(self, brain):
        long_q = ("build a scalable system " * 420).strip()  # ~10 KB
        result = brain.skill_for(long_q)
        assert result is not None

    def test_hebrew_script_query_no_crash(self, brain):
        # Hebrew in query shouldn't explode the tokenizer
        result = brain.skill_for("תרגם את הטקסט הזה לאנגלית translate")
        assert result is not None


# ---------------------------------------------------------------------------
# 9. Tokenization helpers (unit)
# ---------------------------------------------------------------------------


class TestTokenizationHelpers:

    def test_tokenize_strips_stopwords(self):
        from agency.jarvis_brain import _tokenize
        tokens = _tokenize("the quick brown fox")
        assert "the" not in tokens
        assert "brown" in tokens

    def test_tokenize_lowercase(self):
        from agency.jarvis_brain import _tokenize
        tokens = _tokenize("REACT TypeScript")
        assert "react" in tokens
        assert "typescript" in tokens

    def test_bigrams_correct_pairs(self):
        from agency.jarvis_brain import _bigrams
        bg = _bigrams(["a", "b", "c"])
        assert bg == ["a b", "b c"]

    def test_bigrams_empty(self):
        from agency.jarvis_brain import _bigrams
        assert _bigrams([]) == []

    def test_bigrams_single_token(self):
        from agency.jarvis_brain import _bigrams
        assert _bigrams(["x"]) == []


# ---------------------------------------------------------------------------
# 10. CLI smoke
# ---------------------------------------------------------------------------


class TestCLISmoke:

    def test_cli_help_exits_zero(self):
        result = subprocess.run(
            [sys.executable, "-m", "agency.cli", "--help"],
            capture_output=True, text=True, check=False, timeout=15,
        )
        assert result.returncode == 0, (
            f"--help exited {result.returncode}\n{result.stderr[:300]}"
        )

    def test_cli_module_importable(self):
        mod = importlib.import_module("agency.cli")
        assert hasattr(mod, "app") or hasattr(mod, "main") or hasattr(mod, "cli")
