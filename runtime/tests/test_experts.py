"""Tests for agency.experts — every domain expert."""

from __future__ import annotations

import pytest

from agency.experts import (
    AnalysisReport,
    ClinicianExpert,
    ContractsLawExpert,
    MathematicsExpert,
    PhysicsExpert,
    PsychologyCBTExpert,
    EconomicsExpert,
    ChemistryExpert,
    NeuroscienceExpert,
    all_experts,
    get_clinician,
    get_contracts_law,
    get_mathematics,
    get_physics,
    get_psychology_cbt,
    get_economics,
    get_chemistry,
    get_neuroscience,
)


# ---------------------------------------------------------------------------
# Singleton factories
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("getter, cls", [
    (get_clinician, ClinicianExpert),
    (get_contracts_law, ContractsLawExpert),
    (get_mathematics, MathematicsExpert),
    (get_physics, PhysicsExpert),
    (get_psychology_cbt, PsychologyCBTExpert),
    (get_economics, EconomicsExpert),
    (get_chemistry, ChemistryExpert),
    (get_neuroscience, NeuroscienceExpert),
])
def test_factory_returns_singleton(getter, cls):
    a = getter()
    b = getter()
    assert isinstance(a, cls)
    assert a is b


def test_all_experts_returns_eight_distinct_objects():
    experts = all_experts()
    assert len(experts) == 8
    assert len({id(e) for e in experts.values()}) == 8


def test_all_experts_keys_match_names():
    experts = all_experts()
    for name, expert in experts.items():
        assert expert.name == name


# ---------------------------------------------------------------------------
# Uniform contract: status() and analyze()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("expert", list(all_experts().values()))
def test_status_shape(expert):
    s = expert.status()
    assert s["ok"] is True
    assert s["name"] == expert.name
    assert s["discipline"]
    assert isinstance(s["frameworks"], list)
    assert len(s["frameworks"]) >= 1


@pytest.mark.parametrize("expert", list(all_experts().values()))
def test_analyze_returns_report(expert):
    r = expert.analyze("Provide a detailed analysis of the given problem")
    assert isinstance(r, AnalysisReport)
    assert r.expert == expert.name
    assert r.query
    assert isinstance(r.frameworks_applied, list)
    assert isinstance(r.key_findings, list)
    assert isinstance(r.next_questions, list)
    assert 0 <= r.confidence <= 1


@pytest.mark.parametrize("expert", list(all_experts().values()))
def test_analyze_to_dict_roundtrip(expert):
    r = expert.analyze("any query")
    d = r.to_dict()
    assert d["expert"] == expert.name
    assert "frameworks_applied" in d
    assert "metadata" in d


# ---------------------------------------------------------------------------
# Clinician — domain-specific behavior
# ---------------------------------------------------------------------------


def test_clinician_flags_red_flag_chest_pain():
    r = get_clinician().analyze("Patient with crushing chest pain")
    assert r.metadata["red_flags"]
    assert any("RED-FLAG" in f for f in r.key_findings)


def test_clinician_does_not_flag_routine_query():
    r = get_clinician().analyze("recommend a multivitamin schedule")
    assert r.metadata["red_flags"] == []


def test_clinician_special_population_caveat():
    r = get_clinician().analyze("Antibiotic dose for a pediatric patient")
    assert any("Special-population" in f for f in r.key_findings)


def test_clinician_medication_branch():
    r = get_clinician().analyze("Drug interaction check between medication A and B")
    assert any("Medication" in f for f in r.key_findings)


# ---------------------------------------------------------------------------
# Contracts lawyer
# ---------------------------------------------------------------------------


def test_contracts_law_surfaces_indemnity():
    r = get_contracts_law().analyze("Review the indemnification clause")
    assert "indemn" in r.metadata["hot_clauses"]


def test_contracts_law_neutral_text():
    r = get_contracts_law().analyze("simple introductory paragraph")
    assert r.metadata["hot_clauses"] == []


def test_contracts_law_termination_clause():
    r = get_contracts_law().analyze("Termination for convenience must be clear")
    assert any("Termination" in f for f in r.key_findings)


def test_contracts_law_non_compete():
    r = get_contracts_law().analyze("Non-compete agreement scope review")
    assert any("Non-compete" in f for f in r.key_findings)


# ---------------------------------------------------------------------------
# Mathematics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text, expected_type", [
    ("Compute the integral of sin(x)", "calculus"),
    ("Find eigenvalues of a matrix", "linear algebra"),
    ("Probability of two independent events", "probability"),
    ("Count permutations in a graph", "discrete"),
    ("Solve this ODE", "differential equations"),
])
def test_mathematics_classifies_type(text, expected_type):
    r = get_mathematics().analyze(text)
    assert expected_type in r.metadata["types"]


def test_mathematics_default_general():
    r = get_mathematics().analyze("simplify x + 1")
    assert "general algebra / arithmetic" in r.metadata["types"]


# ---------------------------------------------------------------------------
# Physics
# ---------------------------------------------------------------------------


def test_physics_relativistic_regime():
    r = get_physics().analyze("Speed near c with relativistic correction")
    assert r.metadata["regime"] == "relativistic"


def test_physics_quantum_regime():
    r = get_physics().analyze("Schrodinger wavefunction of a hydrogen atom")
    assert r.metadata["regime"] == "quantum"


def test_physics_default_newtonian():
    r = get_physics().analyze("Block sliding down an incline with friction")
    assert r.metadata["regime"] == "Newtonian"


def test_physics_collision_uses_momentum():
    r = get_physics().analyze("Elastic collision between two particles")
    assert "momentum" in r.metadata["conserved"]


# ---------------------------------------------------------------------------
# Psychology / CBT
# ---------------------------------------------------------------------------


def test_psychology_cbt_detects_distortions():
    r = get_psychology_cbt().analyze("I always fail; this is a disaster")
    assert "all-or-nothing" in r.metadata["distortions"]
    assert "catastrophizing" in r.metadata["distortions"]


def test_psychology_cbt_crisis_detection():
    r = get_psychology_cbt().analyze("Sometimes I think about ending my life")
    assert r.metadata["crisis"] is True
    assert r.confidence >= 0.8


def test_psychology_cbt_no_crisis_normal_text():
    r = get_psychology_cbt().analyze("I had a stressful day at work")
    assert r.metadata["crisis"] is False


# ---------------------------------------------------------------------------
# Economics
# ---------------------------------------------------------------------------


def test_economics_macro_scope():
    r = get_economics().analyze("How will the Fed respond to rising inflation?")
    assert r.metadata["scope"] == "macro"


def test_economics_international_scope():
    r = get_economics().analyze("Effect of a steel tariff on import volumes")
    assert r.metadata["scope"] == "international"


def test_economics_micro_default():
    r = get_economics().analyze("Pricing of a single product")
    assert r.metadata["scope"] == "micro"


def test_economics_monopoly_branch():
    r = get_economics().analyze("Welfare loss under monopoly pricing")
    assert any("Monopoly" in f for f in r.key_findings)


# ---------------------------------------------------------------------------
# Chemistry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text, expected", [
    ("Acid-base buffer using pH 7", "acid-base"),
    ("Redox reaction in electrochemistry", "redox"),
    ("SN2 mechanism with hydroxide", "nucleophilic substitution"),
    ("E1 elimination of an alkyl halide", "elimination"),
    ("Le Chatelier shift in equilibrium", "equilibrium"),
])
def test_chemistry_reaction_typing(text, expected):
    r = get_chemistry().analyze(text)
    assert expected in r.metadata["reaction_types"]


def test_chemistry_default_general():
    r = get_chemistry().analyze("name this compound")
    assert "general" in r.metadata["reaction_types"]


# ---------------------------------------------------------------------------
# Neuroscience
# ---------------------------------------------------------------------------


def test_neuroscience_detects_brain_areas():
    r = get_neuroscience().analyze("Role of the prefrontal cortex in decision-making")
    assert "prefrontal" in r.metadata["areas"]
    assert "cortex" in r.metadata["areas"]


def test_neuroscience_memory_branch():
    r = get_neuroscience().analyze("How is long-term memory encoded?")
    assert any("Memory" in f for f in r.key_findings)


def test_neuroscience_methods_branch():
    r = get_neuroscience().analyze("EEG vs fMRI tradeoffs")
    assert any("Methods" in f for f in r.key_findings)


def test_neuroscience_no_areas_returns_marr_advice():
    r = get_neuroscience().analyze("explain the brain")
    assert any("Marr" in f for f in r.key_findings)
