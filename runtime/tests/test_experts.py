"""Tests for the 8 JARVIS expert domain modules."""
from __future__ import annotations

import pytest

from runtime.agency.experts import (
    get_chemistry,
    get_clinician,
    get_contracts_law,
    get_economics,
    get_mathematics,
    get_neuroscience,
    get_physics,
    get_psychology_cbt,
)
from runtime.agency.experts.expert_chemistry import ChemistryExpert, ChemistryResult
from runtime.agency.experts.expert_clinician import ClinicianExpert, ClinicianResult
from runtime.agency.experts.expert_contracts_law import (
    ContractsLawExpert,
    ContractsLawResult,
)
from runtime.agency.experts.expert_economics import EconomicsExpert, EconomicsResult
from runtime.agency.experts.expert_mathematics import (
    MathematicsExpert,
    MathematicsResult,
)
from runtime.agency.experts.expert_neuroscience import (
    NeuroscienceExpert,
    NeuroscienceResult,
)
from runtime.agency.experts.expert_physics import PhysicsExpert, PhysicsResult
from runtime.agency.experts.expert_psychology_cbt import (
    PsychologyCBTExpert,
    PsychologyCBTResult,
)


# ============================================================
# Singleton tests
# ============================================================

def test_clinician_singleton():
    assert get_clinician() is get_clinician()


def test_contracts_law_singleton():
    assert get_contracts_law() is get_contracts_law()


def test_mathematics_singleton():
    assert get_mathematics() is get_mathematics()


def test_physics_singleton():
    assert get_physics() is get_physics()


def test_psychology_cbt_singleton():
    assert get_psychology_cbt() is get_psychology_cbt()


def test_economics_singleton():
    assert get_economics() is get_economics()


def test_chemistry_singleton():
    assert get_chemistry() is get_chemistry()


def test_neuroscience_singleton():
    assert get_neuroscience() is get_neuroscience()


def test_experts_package_imports_all_eight():
    from runtime.agency import experts as pkg

    for name in (
        "get_clinician", "get_contracts_law", "get_mathematics", "get_physics",
        "get_psychology_cbt", "get_economics", "get_chemistry", "get_neuroscience",
    ):
        assert hasattr(pkg, name)


# ============================================================
# Status() tests — every expert
# ============================================================

@pytest.mark.parametrize("getter", [
    get_clinician, get_contracts_law, get_mathematics, get_physics,
    get_psychology_cbt, get_economics, get_chemistry, get_neuroscience,
])
def test_status_returns_ok_true(getter):
    s = getter().status()
    assert s["ok"] is True
    assert "domain" in s
    assert "version" in s


@pytest.mark.parametrize("getter,expected_domain", [
    (get_clinician, "clinician"),
    (get_contracts_law, "contracts_law"),
    (get_mathematics, "mathematics"),
    (get_physics, "physics"),
    (get_psychology_cbt, "psychology_cbt"),
    (get_economics, "economics"),
    (get_chemistry, "chemistry"),
    (get_neuroscience, "neuroscience"),
])
def test_domain_constant_matches(getter, expected_domain):
    e = getter()
    assert e.DOMAIN == expected_domain
    assert e.status()["domain"] == expected_domain


# ============================================================
# can_handle() returns float in [0, 1]
# ============================================================

@pytest.mark.parametrize("getter,query", [
    (get_clinician, "patient with fever and cough"),
    (get_contracts_law, "review the indemnification clause"),
    (get_mathematics, "solve 3x + 2 = 11"),
    (get_physics, "convert 5 km to m"),
    (get_psychology_cbt, "I feel anxious every day"),
    (get_economics, "GDP growth and inflation"),
    (get_chemistry, "molarity of NaCl solution"),
    (get_neuroscience, "amygdala and fear processing"),
])
def test_can_handle_returns_float(getter, query):
    score = getter().can_handle(query)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0
    assert score > 0.0


@pytest.mark.parametrize("getter", [
    get_clinician, get_contracts_law, get_mathematics, get_physics,
    get_psychology_cbt, get_economics, get_chemistry, get_neuroscience,
])
def test_can_handle_zero_for_irrelevant(getter):
    assert getter().can_handle("xyzzy quark blortz unrelated") == 0.0


# ============================================================
# analyze() returns correct result type with confidence
# ============================================================

def test_clinician_analyze_returns_result():
    r = get_clinician().analyze("patient has fever and cough")
    assert isinstance(r, ClinicianResult)
    assert 0.0 <= r.confidence <= 1.0
    assert r.domain == "clinician"


def test_contracts_law_analyze_returns_result():
    r = get_contracts_law().analyze("the unlimited liability clause is concerning")
    assert isinstance(r, ContractsLawResult)
    assert 0.0 <= r.confidence <= 1.0
    assert r.domain == "contracts_law"


def test_mathematics_analyze_returns_result():
    r = get_mathematics().analyze("solve 2x + 3 = 9")
    assert isinstance(r, MathematicsResult)
    assert 0.0 <= r.confidence <= 1.0
    assert r.domain == "mathematics"


def test_physics_analyze_returns_result():
    r = get_physics().analyze("kinetic energy of 2 kg moving at 10 m/s")
    assert isinstance(r, PhysicsResult)
    assert 0.0 <= r.confidence <= 1.0
    assert r.domain == "physics"


def test_psychology_cbt_analyze_returns_result():
    r = get_psychology_cbt().analyze("I always fail at everything")
    assert isinstance(r, PsychologyCBTResult)
    assert 0.0 <= r.confidence <= 1.0
    assert r.domain == "psychology_cbt"


def test_economics_analyze_returns_result():
    r = get_economics().analyze("inflation and GDP growth")
    assert isinstance(r, EconomicsResult)
    assert 0.0 <= r.confidence <= 1.0
    assert r.domain == "economics"


def test_chemistry_analyze_returns_result():
    r = get_chemistry().analyze("molecular weight of H2O")
    assert isinstance(r, ChemistryResult)
    assert 0.0 <= r.confidence <= 1.0
    assert r.domain == "chemistry"


def test_neuroscience_analyze_returns_result():
    r = get_neuroscience().analyze("hippocampus and memory")
    assert isinstance(r, NeuroscienceResult)
    assert 0.0 <= r.confidence <= 1.0
    assert r.domain == "neuroscience"


# ============================================================
# Clinician domain tests
# ============================================================

def test_clinician_extracts_symptoms():
    e = get_clinician()
    syms = e.extract_symptoms("patient has cough, dyspnea, and chest pain")
    assert "cough" in syms
    assert "dyspnea" in syms
    assert "chest pain" in syms


def test_clinician_classifies_icd11_buckets():
    e = get_clinician()
    buckets = e.classify_icd11(["cough", "dyspnea"])
    assert "respiratory" in buckets


def test_clinician_differential_diagnosis_chest_pain():
    e = get_clinician()
    ddx = e.differential_diagnosis(["chest pain"])
    assert any("acute coronary" in d.lower() for d in ddx)


def test_clinician_drug_interaction_warfarin_aspirin():
    e = get_clinician()
    out = e.check_drug_interactions(["warfarin", "aspirin"])
    assert out
    assert "bleeding" in out[0].lower()


def test_clinician_dsm5_match_depression():
    e = get_clinician()
    matches = e.match_dsm5("patient has depressed mood, anhedonia, fatigue")
    assert any("major_depressive" in m for m in matches)


def test_clinician_extract_drugs():
    e = get_clinician()
    drugs = e.extract_drugs("patient takes warfarin and ibuprofen")
    assert "warfarin" in drugs
    assert "ibuprofen" in drugs


def test_clinician_workup_chest_pain():
    e = get_clinician()
    labs = e.suggest_workup(["chest pain"])
    assert "troponin" in labs
    assert "ECG" in labs


def test_clinician_evidence_level_rct():
    e = get_clinician()
    assert e.evidence_level("RCT meta-analysis") == "Level I"
    assert e.evidence_level("expert opinion") == "Level IV"


def test_clinician_analyze_no_signal_low_confidence():
    e = get_clinician()
    r = e.analyze("medical question please help")
    assert r.confidence <= 0.5


# ============================================================
# Contracts/Law domain tests
# ============================================================

def test_contracts_extracts_clauses():
    e = get_contracts_law()
    clauses = e.extract_clauses("the indemnification and termination clauses are key")
    assert "indemnification" in clauses or "termination" in clauses


def test_contracts_flag_unlimited_liability():
    e = get_contracts_law()
    risks = e.flag_risks("there is unlimited liability in this contract")
    assert any("HIGH" in r for r in risks)


def test_contracts_detect_jurisdiction():
    e = get_contracts_law()
    jx = e.detect_jurisdiction("governed by Delaware law")
    assert jx is not None
    assert jx["name"] == "Delaware"


def test_contracts_compliance_gdpr():
    e = get_contracts_law()
    out = e.compliance_check("must comply with GDPR")
    assert any("GDPR" in s for s in out)


def test_contracts_parse_legal_language():
    e = get_contracts_law()
    out = e.parse_legal_language("Section 1.2 The Party shall perform. The Lessee must pay.")
    assert out["shall_count"] == 1
    assert out["must_count"] == 1
    assert "Section 1.2" in out["section_refs"]


def test_contracts_severity_level():
    e = get_contracts_law()
    assert e.severity_level("HIGH risk") == "HIGH"
    assert e.severity_level("MEDIUM risk") == "MEDIUM"
    assert e.severity_level("LOW risk") == "LOW"


def test_contracts_redline_unlimited_liability():
    e = get_contracts_law()
    out = e.suggest_redlines("there is unlimited liability and auto-renewal")
    assert len(out) >= 2


# ============================================================
# Mathematics domain tests
# ============================================================

def test_math_solve_linear_simple():
    e = get_mathematics()
    sol = e.solve_linear("2x + 3 = 9")
    assert sol == 3


def test_math_solve_linear_negative():
    e = get_mathematics()
    sol = e.solve_linear("2x - 4 = 0")
    assert sol == 2


def test_math_evaluate_arithmetic():
    e = get_mathematics()
    assert e.evaluate_arithmetic("3 + 4 * 5") == 23.0


def test_math_solve_quadratic():
    e = get_mathematics()
    roots = e.solve_quadratic("1x^2 - 5x + 6 = 0")
    assert roots is not None
    assert sorted(roots) == [2.0, 3.0]


def test_math_derivative_polynomial():
    e = get_mathematics()
    assert e.derivative("d/dx x^3") == "3*x^2"


def test_math_derivative_constant():
    e = get_mathematics()
    assert e.derivative("d/dx 5") == "0"


def test_math_factor_integer():
    e = get_mathematics()
    assert sorted(e.factor_integer(60)) == [2, 2, 3, 5]


def test_math_gcd_lcm():
    e = get_mathematics()
    assert e.gcd(12, 18) == 6
    assert e.lcm(4, 6) == 12


def test_math_is_prime():
    e = get_mathematics()
    assert e.is_prime(13)
    assert not e.is_prime(15)
    assert not e.is_prime(1)


def test_math_integrate_polynomial():
    e = get_mathematics()
    # integrate 1 + 2x  -> 0 + 1*x + 1*x^2  i.e. coeffs [0, 1, 1]
    coeffs = e.integrate_polynomial([1, 2])
    assert coeffs == [0.0, 1.0, 1.0]


def test_math_parse_latex():
    e = get_mathematics()
    assert e.parse_latex("the equation $x^2 + 1$ holds") == "x^2 + 1"


def test_math_matrix_determinant_2x2():
    e = get_mathematics()
    assert e.matrix_determinant_2x2([[1, 2], [3, 4]]) == -2


# ============================================================
# Physics domain tests
# ============================================================

def test_physics_unit_conversion_km_to_m():
    e = get_physics()
    out = e.parse_unit_conversion("convert 5 km to m")
    assert out is not None
    assert out["result"] == pytest.approx(5000.0)


def test_physics_unit_conversion_inch_to_cm():
    e = get_physics()
    out = e.parse_unit_conversion("convert 1 inch to cm")
    assert out is not None
    assert out["result"] == pytest.approx(2.54, rel=1e-3)


def test_physics_lookup_speed_of_light():
    e = get_physics()
    out = e.lookup_constant("speed of light")
    assert out is not None
    assert out["symbol"] == "c"
    assert out["value"] == 299_792_458.0


def test_physics_kinetic_energy():
    e = get_physics()
    assert e.kinetic_energy(2.0, 10.0) == 100.0


def test_physics_potential_energy_gravity():
    e = get_physics()
    assert e.potential_energy_gravity(2.0, 5.0, g=10.0) == 100.0


def test_physics_momentum():
    e = get_physics()
    assert e.momentum(2.0, 3.0) == 6.0


def test_physics_force():
    e = get_physics()
    assert e.force(5.0, 9.8) == pytest.approx(49.0)


def test_physics_relativistic_gamma():
    e = get_physics()
    assert e.relativistic_gamma(0.0) == 1.0
    assert e.relativistic_gamma(0.5 * 299_792_458.0) > 1.15


def test_physics_relativistic_gamma_at_c_raises():
    e = get_physics()
    with pytest.raises(ValueError):
        e.relativistic_gamma(299_792_458.0)


def test_physics_photon_energy_from_wavelength():
    e = get_physics()
    energy = e.photon_energy_from_wavelength(500e-9)  # 500 nm green light
    assert 3e-19 < energy < 5e-19


def test_physics_classify_domain_quantum():
    e = get_physics()
    assert e.classify_domain("Schrodinger equation for a quantum particle") == "quantum"


def test_physics_classify_domain_relativistic():
    e = get_physics()
    assert e.classify_domain("special relativity Lorentz") == "relativistic"


def test_physics_classify_domain_thermodynamic():
    e = get_physics()
    assert e.classify_domain("entropy and temperature changes") == "thermodynamic"


def test_physics_classify_domain_classical_default():
    e = get_physics()
    assert e.classify_domain("a ball rolling down a ramp") == "classical"


# ============================================================
# Psychology / CBT domain tests
# ============================================================

def test_psych_detects_all_or_nothing():
    e = get_psychology_cbt()
    out = e.detect_distortions("I always fail at everything")
    assert any(d["key"] == "all_or_nothing" for d in out)


def test_psych_detects_should_statement():
    e = get_psychology_cbt()
    out = e.detect_distortions("I should be perfect")
    assert any(d["key"] == "shoulds" for d in out)


def test_psych_detects_catastrophizing():
    e = get_psychology_cbt()
    out = e.detect_distortions("this is a disaster, I can't handle it")
    assert any(d["key"] == "catastrophizing" for d in out)


def test_psych_detects_labeling():
    e = get_psychology_cbt()
    out = e.detect_distortions("I'm a loser")
    assert any(d["key"] == "labeling" for d in out)


def test_psych_suggests_techniques_for_anxiety():
    e = get_psychology_cbt()
    out = e.suggest_techniques("I have panic attacks and anxiety")
    assert any("xposure" in t for t in out)


def test_psych_psychoeducation_anxiety():
    e = get_psychology_cbt()
    out = e.psychoeducation("I have anxiety")
    assert out is not None
    assert "threat" in out.lower() or "avoidance" in out.lower()


def test_psych_thought_record_structure():
    e = get_psychology_cbt()
    rec = e.thought_record("met boss", "they hate me", "anxious", 80)
    assert rec["intensity_0_100"] == 80
    assert rec["situation"] == "met boss"


def test_psych_thought_record_clamps_intensity():
    e = get_psychology_cbt()
    rec = e.thought_record("x", "y", "z", 999)
    assert rec["intensity_0_100"] == 100
    rec2 = e.thought_record("x", "y", "z", -10)
    assert rec2["intensity_0_100"] == 0


def test_psych_estimate_mood_negative():
    e = get_psychology_cbt()
    score = e.estimate_mood("I feel sad and anxious and hopeless")
    assert score is not None
    assert score < 0


def test_psych_estimate_mood_positive():
    e = get_psychology_cbt()
    score = e.estimate_mood("I feel happy and grateful and calm")
    assert score is not None
    assert score > 0


def test_psych_severity_levels():
    e = get_psychology_cbt()
    assert e.severity_level(-0.9) == "severe"
    assert e.severity_level(-0.5) == "moderate"
    assert e.severity_level(-0.1) == "mild"
    assert e.severity_level(0.5) == "stable"


def test_psych_crisis_check_flags():
    e = get_psychology_cbt()
    assert e.crisis_check("I want to kill myself") is True
    assert e.crisis_check("I had a great day") is False


# ============================================================
# Economics domain tests
# ============================================================

def test_econ_classify_macro():
    e = get_economics()
    assert e.classify_scope("GDP and inflation rose") == "macro"


def test_econ_classify_game_theory():
    e = get_economics()
    assert e.classify_scope("nash equilibrium prisoner's dilemma") == "game-theory"


def test_econ_classify_international():
    e = get_economics()
    assert e.classify_scope("trade tariff and exchange rate") == "international"


def test_econ_classify_micro_default():
    e = get_economics()
    assert e.classify_scope("widget supply curve") == "micro"


def test_econ_parse_elasticity():
    e = get_economics()
    elast = e.parse_elasticity(
        "demand fell by 20% after price rose by 10%"
    )
    assert elast == pytest.approx(2.0)


def test_econ_elasticity_classification():
    e = get_economics()
    assert e.elasticity_classification(0.5) == "inelastic"
    assert e.elasticity_classification(2.0) == "elastic"
    assert e.elasticity_classification(1.0) == "unit-elastic"


def test_econ_lookup_indicator_gdp():
    e = get_economics()
    out = e.lookup_indicator("GDP measure")
    assert out is not None
    assert out["symbol"] == "GDP"


def test_econ_detect_prisoners_dilemma():
    e = get_economics()
    out = e.detect_game_theory("the prisoner's dilemma example")
    assert out is not None
    assert "Nash" in out or "defect" in out


def test_econ_consumer_surplus():
    e = get_economics()
    assert e.consumer_surplus(100.0, 60.0) == 40.0
    assert e.consumer_surplus(60.0, 100.0) == 0.0


def test_econ_producer_surplus():
    e = get_economics()
    assert e.producer_surplus(80.0, 50.0) == 30.0


def test_econ_gdp_growth():
    e = get_economics()
    assert e.gdp_growth(110.0, 100.0) == pytest.approx(10.0)


def test_econ_real_interest_rate():
    e = get_economics()
    # 5% nominal, 2% inflation -> ~2.94%
    r = e.real_interest_rate(0.05, 0.02)
    assert r == pytest.approx(0.0294, rel=1e-3)


def test_econ_compound_interest():
    e = get_economics()
    assert e.compound_interest(1000.0, 0.05, 1) == pytest.approx(1050.0)


def test_econ_present_value():
    e = get_economics()
    assert e.present_value(110.0, 0.10, 1) == pytest.approx(100.0)


def test_econ_gini_equal_income_zero():
    e = get_economics()
    assert e.gini_coefficient([10.0, 10.0, 10.0, 10.0]) == pytest.approx(0.0, abs=0.01)


def test_econ_gini_unequal_positive():
    e = get_economics()
    score = e.gini_coefficient([1.0, 1.0, 1.0, 100.0])
    assert score > 0.5


def test_econ_policy_impact_rate_hike():
    e = get_economics()
    out = e.policy_impact("the central bank will raise interest rate")
    assert out is not None
    assert "inflation" in out.lower() or "demand" in out.lower()


# ============================================================
# Chemistry domain tests
# ============================================================

def test_chem_parse_formula_water():
    e = get_chemistry()
    out = e.parse_formula("H2O")
    assert out == {"H": 2, "O": 1}


def test_chem_parse_formula_glucose():
    e = get_chemistry()
    out = e.parse_formula("C6H12O6")
    assert out == {"C": 6, "H": 12, "O": 6}


def test_chem_molecular_weight_water():
    e = get_chemistry()
    mw = e.molecular_weight("H2O")
    assert mw is not None
    assert mw == pytest.approx(18.015, abs=0.01)


def test_chem_molecular_weight_co2():
    e = get_chemistry()
    mw = e.molecular_weight("CO2")
    assert mw == pytest.approx(44.01, abs=0.05)


def test_chem_molecular_weight_invalid():
    e = get_chemistry()
    assert e.molecular_weight("Zz") is None


def test_chem_balance_h2_o2_h2o():
    e = get_chemistry()
    out = e.balance_simple("H2", "H2O")
    assert out is not None
    assert out["H2"] == 2
    assert out["O2"] == 1
    assert out["H2O"] == 2


def test_chem_grams_to_moles():
    e = get_chemistry()
    out = e.stoichiometry_grams_to_moles(18.0, "H2O")
    assert out is not None
    assert out == pytest.approx(1.0, rel=0.01)


def test_chem_moles_to_grams():
    e = get_chemistry()
    out = e.stoichiometry_moles_to_grams(1.0, "H2O")
    assert out == pytest.approx(18.015, abs=0.01)


def test_chem_molarity():
    e = get_chemistry()
    assert e.molarity(0.5, 0.5) == 1.0


def test_chem_molarity_zero_volume_raises():
    e = get_chemistry()
    with pytest.raises(ValueError):
        e.molarity(1.0, 0.0)


def test_chem_parse_ph():
    e = get_chemistry()
    assert e.parse_ph("the pH=7.4 of blood") == 7.4


def test_chem_classify_ph():
    e = get_chemistry()
    assert e.classify_ph(2.0) == "strong acid"
    assert e.classify_ph(7.0) == "neutral"
    assert e.classify_ph(13.0) == "strong base"


def test_chem_check_reaction_balanced_h2o():
    e = get_chemistry()
    # 2 H2 + O2 -> 2 H2O is balanced; H + O on each side
    out = e.check_reaction_balanced("2H2 + O2 -> 2H2O")
    assert out is True


def test_chem_check_reaction_unbalanced():
    e = get_chemistry()
    out = e.check_reaction_balanced("H2 + O2 -> H2O")
    assert out is False


def test_chem_hazard_lookup():
    e = get_chemistry()
    out = e.hazard_lookup("we use H2SO4 in the lab")
    assert "H2SO4" in out


def test_chem_iupac_carbon_count():
    e = get_chemistry()
    assert e.iupac_carbon_count("methane") == 1
    assert e.iupac_carbon_count("hexane") == 6


def test_chem_periodic_lookup():
    e = get_chemistry()
    out = e.periodic_lookup("Fe")
    assert out is not None
    assert out["atomic_weight"] == pytest.approx(55.845, abs=0.01)


# ============================================================
# Neuroscience domain tests
# ============================================================

def test_neuro_lookup_regions_amygdala():
    e = get_neuroscience()
    out = e.lookup_regions("amygdala drives fear processing")
    assert "amygdala" in out


def test_neuro_lookup_regions_hippocampus():
    e = get_neuroscience()
    out = e.lookup_regions("the hippocampus encodes memory")
    assert "hippocampus" in out


def test_neuro_lookup_neurotransmitters_dopamine():
    e = get_neuroscience()
    out = e.lookup_neurotransmitters("dopamine pathways")
    assert "dopamine" in out
    assert "function" in out["dopamine"]


def test_neuro_lookup_condition_alzheimer():
    e = get_neuroscience()
    out = e.lookup_condition("alzheimer's disease pathology")
    assert out is not None
    assert "amyloid" in out["description"].lower() or "tau" in out["description"].lower()


def test_neuro_lookup_cognitive_function_memory():
    e = get_neuroscience()
    out = e.lookup_cognitive_function("memory")
    assert out is not None
    assert any("hippocampus" in s for s in out["substrates"])


def test_neuro_receptor_for_dopamine():
    e = get_neuroscience()
    out = e.receptor_for_neurotransmitter("dopamine")
    assert "D1" in out
    assert "D2" in out


def test_neuro_receptor_for_unknown():
    e = get_neuroscience()
    assert e.receptor_for_neurotransmitter("notreal") == []


def test_neuro_summarize_paper():
    e = get_neuroscience()
    abstract = "We studied dopamine signaling in mice. Dopamine release was measured."
    out = e.summarize_paper(abstract)
    assert out["word_count"] > 0
    assert "first_sentence" in out


def test_neuro_imaging_modality_function():
    e = get_neuroscience()
    assert e.imaging_modality_for("function") == "fMRI (BOLD)"
    assert e.imaging_modality_for("white matter") == "DTI"


# ============================================================
# UnifiedBridge integration / routing
# ============================================================

@pytest.fixture
def bridge():
    """Build a minimal UnifiedBridge for expert routing tests.

    The full bridge is heavy (LLM router, vector store, tracer, etc) so
    we instantiate UnifiedBridge directly with default lazy components
    here. This validates the experts wiring without exercising the LLM.
    """
    from runtime.agency.unified_bridge import UnifiedBridge
    from runtime.agency import get_experts_dict
    return UnifiedBridge(experts=get_experts_dict())


def test_bridge_has_all_eight_experts(bridge):
    assert "clinician" in bridge.experts
    assert "contracts_law" in bridge.experts
    assert "mathematics" in bridge.experts
    assert "physics" in bridge.experts
    assert "psychology_cbt" in bridge.experts
    assert "economics" in bridge.experts
    assert "chemistry" in bridge.experts
    assert "neuroscience" in bridge.experts


def test_bridge_status_reports_all_experts(bridge):
    s = bridge.status()
    assert "experts" in s
    for name in ("clinician", "contracts_law", "mathematics", "physics",
                 "psychology_cbt", "economics", "chemistry", "neuroscience"):
        assert name in s["experts"]
        assert s["experts"][name]["ok"] is True


def test_bridge_status_subsystems_includes_expert_rows(bridge):
    s = bridge.status()
    subsystems = s["subsystems"]
    for name in ("clinician", "contracts_law", "mathematics", "physics",
                 "psychology_cbt", "economics", "chemistry", "neuroscience"):
        assert f"expert.{name}" in subsystems
        assert subsystems[f"expert.{name}"]["healthy"] is True


def test_bridge_routes_medical_to_clinician(bridge):
    name, _ = bridge.route_expert("patient has fever, cough, and dyspnea")
    assert name == "clinician"


def test_bridge_routes_contract_to_contracts_law(bridge):
    name, _ = bridge.route_expert(
        "review the indemnification and termination clauses",
    )
    assert name == "contracts_law"


def test_bridge_routes_math_to_mathematics(bridge):
    name, _ = bridge.route_expert("solve the equation 3x + 2 = 11")
    assert name == "mathematics"


def test_bridge_routes_physics_to_physics(bridge):
    name, _ = bridge.route_expert("convert 5 km to m using physics constants")
    assert name == "physics"


def test_bridge_routes_psychology_to_cbt(bridge):
    name, _ = bridge.route_expert(
        "I have anxiety and depression and feel hopeless",
    )
    assert name == "psychology_cbt"


def test_bridge_routes_economics_to_economics(bridge):
    name, _ = bridge.route_expert(
        "the central bank raised interest rate, GDP growth and inflation",
    )
    assert name == "economics"


def test_bridge_routes_chemistry_to_chemistry(bridge):
    name, _ = bridge.route_expert("balance the chemical reaction H2O molecule")
    assert name == "chemistry"


def test_bridge_routes_neuro_to_neuroscience(bridge):
    name, _ = bridge.route_expert("the amygdala and hippocampus brain regions")
    assert name == "neuroscience"


def test_bridge_route_no_match_returns_zero(bridge):
    name, score = bridge.route_expert("zzzzz qqqqq")
    assert name == ""
    assert score == 0.0


def test_bridge_lazy_experts_loads_all_eight():
    """Constructing UnifiedBridge with no `experts=` kwarg should
    auto-load all 8 domain experts via _lazy_experts()."""
    from runtime.agency.unified_bridge import UnifiedBridge
    bridge = UnifiedBridge()
    assert len(bridge.experts) == 8


# ============================================================
# Module-level getter integration with runtime.agency
# ============================================================

@pytest.mark.parametrize("getter_name", [
    "get_clinician", "get_contracts_law", "get_mathematics", "get_physics",
    "get_psychology_cbt", "get_economics", "get_chemistry", "get_neuroscience",
])
def test_agency_package_exposes_getter(getter_name):
    import runtime.agency as agency
    assert hasattr(agency, getter_name)
    fn = getattr(agency, getter_name)
    inst = fn()
    assert inst.status()["ok"] is True


def test_agency_getters_match_expert_singletons():
    import runtime.agency as agency
    assert agency.get_clinician() is get_clinician()
    assert agency.get_chemistry() is get_chemistry()
    assert agency.get_mathematics() is get_mathematics()


# ============================================================
# Result dataclass field checks
# ============================================================

def test_clinician_result_has_required_fields():
    r = get_clinician().analyze("fever and cough")
    assert hasattr(r, "answer") and isinstance(r.answer, str)
    assert hasattr(r, "sources") and isinstance(r.sources, list)
    assert hasattr(r, "metadata") and isinstance(r.metadata, dict)


def test_chemistry_result_has_metadata():
    r = get_chemistry().analyze("molecular weight of H2O")
    assert "molecular_weights" in r.metadata


def test_physics_result_has_domain_classification():
    r = get_physics().analyze("quantum schrodinger equation")
    assert r.metadata.get("physics_domain") == "quantum"


def test_economics_result_has_scope():
    r = get_economics().analyze("GDP and inflation macro")
    assert r.metadata.get("scope") == "macro"
