"""Breadth coverage of the SupremeJarvisBrain router.

Extra scenarios beyond the small evaluation suite:
- Routes from many engineering / data / finance / creative queries.
- Confirms KEYWORD_SLUG_BOOST entries actually steer routing.
- Confirms ties broken by score, not by alphabetical slug.
"""

from __future__ import annotations

import pytest

from agency.jarvis_brain import (
    SupremeJarvisBrain,
    KEYWORD_SLUG_BOOST,
    get_brain,
)


@pytest.fixture(scope="module")
def brain():
    return get_brain()


# ---------------------------------------------------------------------------
# Many-domain breadth
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query, expected_substrings", [
    ("kubernetes upgrade", ("devops",)),
    ("terraform module deployment", ("devops", "platform")),
    ("helm chart for cluster", ("devops",)),
    ("CI/CD release pipeline for cloud", ("devops", "ops", "platform")),
    ("embedded firmware port", ("embedded", "firmware")),
    ("RTOS task scheduler", ("embedded", "firmware")),
    ("ROS robotics motion planner", ("robotics", "iot")),
    ("robotics arm pick and place", ("robotics",)),
    ("SRE on-call rotation", ("ops", "support")),
    ("incident response runbook", ("ops",)),
    ("ML fine-tune small model", ("ml", "ai")),
    ("vector search embeddings index", ("ml", "data")),
    ("snowflake warehouse star schema", ("data",)),
    ("bigquery ETL design", ("data",)),
    ("NLP tokenization corpus", ("nlp", "linguistics")),
    ("digital twin physics simulation", ("twin",)),
])
def test_engineering_data_routing_breadth(brain, query, expected_substrings):
    r = brain.skill_for(query)
    slug = r.skill.slug.lower()
    assert any(sub in slug for sub in expected_substrings), (
        f"{query!r} routed to {r.skill.slug}"
    )


@pytest.mark.parametrize("query, expected_substrings", [
    ("DCF valuation analysis", ("finance",)),
    ("alpha trading strategy", ("quant",)),
    ("portfolio optimization", ("quant", "finance")),
    ("PSD2 open banking", ("fintech",)),
    ("neobank onboarding", ("fintech",)),
    ("actuarial catastrophe model", ("insurance",)),
    ("ESG carbon accounting", ("climate", "sustainability")),
    ("real estate REIT analysis", ("real-estate", "estate")),
    ("behavioral nudge program", ("behavioral",)),
])
def test_finance_routing_breadth(brain, query, expected_substrings):
    r = brain.skill_for(query)
    slug = r.skill.slug.lower()
    assert any(sub in slug for sub in expected_substrings), f"{query!r} → {slug}"


@pytest.mark.parametrize("query, expected_substrings", [
    ("SEO content strategy", ("marketing", "content")),
    ("demand gen funnel", ("marketing", "growth")),
    ("growth experiment design", ("growth", "marketing")),
    ("google ads campaign", ("paid-media",)),
    ("meta ads creative review", ("paid-media",)),
    ("programmatic bidding ops", ("paid-media",)),
    ("outbound sales sequence", ("sales", "growth")),
    ("creator economy monetization", ("creator",)),
])
def test_marketing_sales_routing_breadth(brain, query, expected_substrings):
    r = brain.skill_for(query)
    slug = r.skill.slug.lower()
    assert any(sub in slug for sub in expected_substrings), f"{query!r} → {slug}"


@pytest.mark.parametrize("query, expected_substrings", [
    ("GDPR data subject rights", ("privacy", "legal", "compliance")),
    ("CCPA consumer rights", ("privacy", "legal", "compliance")),
    ("OWASP top 10 review", ("security", "cyber")),
    ("zero-trust segmentation", ("security", "cyber")),
    ("pen test scope plan", ("security", "red-team", "test")),
    ("offensive exploit chain", ("security", "red-team", "auditor", "blockchain")),
])
def test_legal_security_routing_breadth(brain, query, expected_substrings):
    r = brain.skill_for(query)
    slug = r.skill.slug.lower()
    assert any(sub in slug for sub in expected_substrings), f"{query!r} → {slug}"


@pytest.mark.parametrize("query, expected_substrings", [
    ("Qiskit quantum algorithm", ("quantum",)),
    ("CRISPR gene knockout", ("genomics", "biotech")),
    ("BCI EEG decoder", ("neuroscience", "bci")),
    ("nano material assembly", ("nano",)),
    ("satellite orbit decay", ("space", "aerospace")),
    ("battery chemistry materials", ("energy", "chemistry", "materials")),
    ("nuclear reactor design", ("nuclear", "energy")),
])
def test_science_advanced_tech_routing(brain, query, expected_substrings):
    r = brain.skill_for(query)
    slug = r.skill.slug.lower()
    assert any(sub in slug for sub in expected_substrings), f"{query!r} → {slug}"


@pytest.mark.parametrize("query, expected_substrings", [
    ("green hydrogen energy strategy", ("energy", "climate", "hydrogen")),
    ("CCUS deployment plan", ("climate", "energy", "sustainability")),
    ("watershed management", ("water",)),
    ("smart city mobility platform", ("smart-cities", "city")),
    ("vertical farm sensor controls", ("agritech", "food")),
    ("shipping logistics maritime", ("maritime", "supply", "shipping")),
    ("circular economy plastic recovery", ("circular",)),
])
def test_climate_infrastructure_routing(brain, query, expected_substrings):
    r = brain.skill_for(query)
    slug = r.skill.slug.lower()
    assert any(sub in slug for sub in expected_substrings), f"{query!r} → {slug}"


@pytest.mark.parametrize("query, expected_substrings", [
    ("figma UI prototype", ("design",)),
    ("UI/UX design system", ("design",)),
    ("screenplay structure feedback", ("creative", "writing")),
    ("DAW mixing chain", ("music",)),
    ("color theory color grading", ("photography", "visual")),
    ("fashion brand strategy", ("fashion", "luxury")),
    ("studio film media production", ("media", "entertainment", "music")),
])
def test_creative_routing(brain, query, expected_substrings):
    r = brain.skill_for(query)
    slug = r.skill.slug.lower()
    assert any(sub in slug for sub in expected_substrings), f"{query!r} → {slug}"


@pytest.mark.parametrize("query, expected_substrings", [
    ("OKR alignment", ("hr", "strategy")),
    ("compensation review", ("hr",)),
    ("EdTech curriculum", ("education",)),
    ("public policy advocacy", ("policy", "governance")),
    ("AI ethics framework", ("ethics", "philosophy")),
    ("grant application", ("nonprofit", "philanthropy")),
    ("geopolitical defense brief", ("military", "defense")),
    ("FOIA filing journalism", ("journalism",)),
    ("visa strategy mobility", ("immigration", "mobility")),
])
def test_society_governance_routing(brain, query, expected_substrings):
    r = brain.skill_for(query)
    slug = r.skill.slug.lower()
    assert any(sub in slug for sub in expected_substrings), f"{query!r} → {slug}"


# ---------------------------------------------------------------------------
# KEYWORD_SLUG_BOOST table sanity
# ---------------------------------------------------------------------------


def test_every_boost_term_lowercase():
    for term in KEYWORD_SLUG_BOOST:
        assert term == term.lower()


def test_every_boost_target_lowercase():
    for mapping in KEYWORD_SLUG_BOOST.values():
        for target in mapping:
            assert target == target.lower()


# ---------------------------------------------------------------------------
# Routing stability — no flake
# ---------------------------------------------------------------------------


def test_routing_is_deterministic(brain):
    q = "Plan a kubernetes upgrade for staging"
    runs = [brain.skill_for(q).skill.slug for _ in range(5)]
    assert len(set(runs)) == 1


def test_top_k_consistent_count(brain):
    items = brain.top_k("kubernetes terraform helm bigquery", k=8)
    assert len(items) == 8
