"""Tests for agency.jarvis_brain.SupremeJarvisBrain."""

from __future__ import annotations

import pytest

from agency.jarvis_brain import (
    SupremeJarvisBrain,
    RouteResult,
    KEYWORD_SLUG_BOOST,
    get_brain,
    _tokenize,
    _bigrams,
)


@pytest.fixture(scope="module")
def brain():
    return SupremeJarvisBrain()


# ---------------------------------------------------------------------------
# Construction & registry
# ---------------------------------------------------------------------------


def test_brain_loads_full_registry(brain):
    assert len(brain.registry) > 200


def test_brain_indexes_by_slug(brain):
    sample = brain.registry.all()[0]
    assert brain.by_slug(sample.slug) is sample


def test_brain_by_slug_returns_none_for_unknown(brain):
    assert brain.by_slug("__nope__") is None


def test_get_brain_singleton():
    a = get_brain()
    b = get_brain()
    assert a is b


# ---------------------------------------------------------------------------
# Routing — high-level
# ---------------------------------------------------------------------------


def test_skill_for_returns_route_result(brain):
    r = brain.skill_for("Plan kubernetes upgrade")
    assert isinstance(r, RouteResult)
    assert r.skill is not None
    assert r.score > 0
    assert r.rationale


def test_skill_for_empty_request_raises(brain):
    with pytest.raises(ValueError):
        brain.skill_for("")
    with pytest.raises(ValueError):
        brain.skill_for("   ")


def test_skill_for_returns_top_k_candidates(brain):
    r = brain.skill_for("kubernetes terraform helm", top_k=5)
    assert len(r.candidates) <= 5
    assert all(sc > 0 for _, sc in r.candidates)
    # Candidates should be sorted descending.
    scores = [sc for _, sc in r.candidates]
    assert scores == sorted(scores, reverse=True)


def test_top_k_returns_list_of_tuples(brain):
    items = brain.top_k("data warehouse", k=3)
    assert len(items) == 3
    assert all(isinstance(t[1], float) for t in items)


# ---------------------------------------------------------------------------
# Routing — domain-specific accuracy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query, expected_slug", [
    ("Plan a kubernetes upgrade", "jarvis-devops-platform"),
    ("Tokenize multilingual NLP corpus", "jarvis-linguistics-nlp"),
    ("GDPR data subject rights", "jarvis-privacy-data-governance"),
    ("Satellite orbit decay calculation", "jarvis-space-aerospace"),
    ("Build an actuarial catastrophe model", "jarvis-insurance-risk"),
    ("Plan a smart city mobility platform", "jarvis-smart-cities"),
    ("Decode EEG signals for a BCI", "jarvis-neuroscience-bci"),
    ("Design a CBT-style intervention", "jarvis-mental-health"),
    ("Design a Qiskit quantum algorithm", "jarvis-quantum-computing"),
])
def test_routing_matches_expected_slug(brain, query, expected_slug):
    r = brain.skill_for(query)
    assert r.skill.slug == expected_slug, (
        f"query={query!r} routed to {r.skill.slug} expected {expected_slug}"
    )


def test_route_result_to_dict_serializes(brain):
    r = brain.skill_for("circular economy plastic waste")
    d = r.to_dict()
    assert d["skill"]
    assert d["score"] > 0
    assert "candidates" in d


# ---------------------------------------------------------------------------
# Mega-prompt assembly
# ---------------------------------------------------------------------------


def test_unified_prompt_contains_identity(brain):
    prompt = brain.unified_prompt()
    assert "JARVIS" in prompt
    assert "Supreme Operational Directives" in prompt
    assert "Full Skill Index" in prompt


def test_unified_prompt_with_request_inlines_specialists(brain):
    prompt = brain.unified_prompt("kubernetes deployment", top_k_full=3)
    assert "Activated Specialists" in prompt
    assert "jarvis-devops" in prompt.lower()


def test_unified_prompt_respects_max_chars(brain):
    short = brain.unified_prompt(max_chars=2_000)
    assert len(short) <= 2_000


def test_unified_prompt_index_lists_categories(brain):
    prompt = brain.unified_prompt()
    for cat in ("engineering", "marketing", "sales", "design"):
        assert f"## {cat}" in prompt


# ---------------------------------------------------------------------------
# KEYWORD_SLUG_BOOST
# ---------------------------------------------------------------------------


def test_keyword_boost_map_is_populated():
    assert len(KEYWORD_SLUG_BOOST) >= 50


def test_keyword_boost_weights_in_expected_range():
    for term, mapping in KEYWORD_SLUG_BOOST.items():
        for target, weight in mapping.items():
            assert 0 < weight <= 10, f"weight for {term!r}->{target!r} is {weight}"


def test_keyword_boost_has_kubernetes_entry():
    assert "kubernetes" in KEYWORD_SLUG_BOOST
    assert "devops" in KEYWORD_SLUG_BOOST["kubernetes"]


# ---------------------------------------------------------------------------
# Tokenizer + bigram helpers
# ---------------------------------------------------------------------------


def test_tokenize_strips_stopwords():
    tokens = _tokenize("plan a deployment for the team")
    assert "the" not in tokens
    assert "a" not in tokens
    assert "plan" in tokens
    assert "deployment" in tokens


def test_tokenize_lowercases():
    tokens = _tokenize("Build A REST API")
    assert "build" in tokens
    assert "rest" in tokens
    assert "api" in tokens


def test_tokenize_preserves_hyphens():
    tokens = _tokenize("zero-trust architecture")
    assert "zero-trust" in tokens


def test_bigrams_pairs_consecutive_tokens():
    bg = _bigrams(["a", "b", "c", "d"])
    assert bg == ["a b", "b c", "c d"]


def test_bigrams_empty_for_short_input():
    assert _bigrams([]) == []
    assert _bigrams(["a"]) == []
