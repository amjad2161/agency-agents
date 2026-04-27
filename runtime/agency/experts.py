"""Domain expert modules — symbolic, deterministic analysis layers.

Each expert encapsulates the methodology of a single field
(clinician, contracts lawyer, mathematician, physicist, CBT
psychologist, economist, chemist, neuroscientist) and exposes the
same uniform contract:

    expert.status() -> dict   # health snapshot
    expert.analyze(query) -> AnalysisReport

Reports are structured (frameworks applied, key findings, next
questions) so downstream LLM calls can use them as scaffolding rather
than free-text. Experts are intentionally LLM-free — they encode
field methodology in code so they remain deterministic and cheap to
call from anywhere in the system.

Singletons are lazily constructed via the ``get_*`` factories so
``import`` is cheap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Common report shape
# ---------------------------------------------------------------------------


@dataclass
class AnalysisReport:
    """Structured output of every expert.analyze() call."""

    expert: str
    query: str
    frameworks_applied: list[str] = field(default_factory=list)
    key_findings: list[str] = field(default_factory=list)
    next_questions: list[str] = field(default_factory=list)
    confidence: float = 0.6
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "expert": self.expert,
            "query": self.query,
            "frameworks_applied": list(self.frameworks_applied),
            "key_findings": list(self.key_findings),
            "next_questions": list(self.next_questions),
            "confidence": round(self.confidence, 2),
            "metadata": dict(self.metadata),
        }


class _BaseExpert:
    """Shared scaffolding: every expert reports identical status shape."""

    name: str = "base"
    discipline: str = ""
    frameworks: tuple[str, ...] = ()

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": True,
            "discipline": self.discipline,
            "frameworks": list(self.frameworks),
        }

    def analyze(self, query: str) -> AnalysisReport:  # pragma: no cover
        raise NotImplementedError

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {t for t in re.findall(r"[a-z][a-z\-]+", text.lower()) if len(t) > 2}


# ---------------------------------------------------------------------------
# Clinician — diagnostic reasoning, symptom triage, red-flag screening
# ---------------------------------------------------------------------------


class ClinicianExpert(_BaseExpert):
    name = "clinician"
    discipline = "clinical medicine"
    frameworks = (
        "SOAP note",
        "OPQRST symptom history",
        "differential diagnosis",
        "ABCDE triage",
        "red-flag screening",
    )

    RED_FLAGS = (
        "chest pain", "stroke", "seizure", "syncope", "anaphylax",
        "sepsis", "suicidal", "homicidal", "hemorrhage", "shock",
    )

    def analyze(self, query: str) -> AnalysisReport:
        toks = self._tokens(query)
        findings: list[str] = []
        red_flags = [rf for rf in self.RED_FLAGS if rf in query.lower()]
        if red_flags:
            findings.append(
                "RED-FLAG presentation detected: "
                + ", ".join(red_flags)
                + " — escalate to emergency evaluation."
            )
        else:
            findings.append("No critical red flags identified in the query text.")

        if toks & {"pain", "ache", "headache", "fever", "cough", "fatigue"}:
            findings.append("Symptom-led: build OPQRST history, then differential.")
        if toks & {"medication", "drug", "dose", "interaction"}:
            findings.append("Medication question: review interactions and renal/hepatic dosing.")
        if toks & {"pregnan", "pediatric", "geriatric", "child"}:
            findings.append("Special-population caveat: dosing, teratogenicity, frailty.")

        return AnalysisReport(
            expert=self.name,
            query=query,
            frameworks_applied=list(self.frameworks),
            key_findings=findings,
            next_questions=[
                "What is the timeline and severity of the chief complaint?",
                "What active medications and known allergies exist?",
                "Any relevant comorbidities (cardiac, renal, hepatic)?",
            ],
            confidence=0.75 if red_flags else 0.6,
            metadata={"red_flags": red_flags},
        )


# ---------------------------------------------------------------------------
# Contracts lawyer — clause-level review, risk surfacing
# ---------------------------------------------------------------------------


class ContractsLawExpert(_BaseExpert):
    name = "contracts_law"
    discipline = "contracts law"
    frameworks = (
        "offer-acceptance-consideration",
        "indemnification analysis",
        "limitation of liability",
        "termination-for-cause vs convenience",
        "governing-law / forum-selection",
    )

    HOT_CLAUSES = (
        "indemn", "limitation of liability", "warrant", "non-compete",
        "non-solicit", "auto-renew", "evergreen", "exclusivity",
        "governing law", "arbitration", "force majeure", "termination",
        "assignment", "confidentiality", "ip ownership",
    )

    def analyze(self, query: str) -> AnalysisReport:
        q = query.lower()
        present = [c for c in self.HOT_CLAUSES if c in q]
        findings: list[str] = []
        if present:
            findings.append(
                "Hot clauses present: " + ", ".join(present) + " — review each for symmetry and caps."
            )
        else:
            findings.append(
                "No high-risk clauses surfaced from the text — confirm by reviewing the full document."
            )

        if "indemn" in q:
            findings.append("Indemnity: cap exposure, mutual where possible, carve out IP infringement.")
        if "limitation of liability" in q:
            findings.append("LoL: confirm cap formula (12-mo fees) and exclusions for gross negligence.")
        if "termination" in q:
            findings.append("Termination: distinguish convenience vs cause; align cure period with risk.")
        if "non-compete" in q:
            findings.append("Non-compete: scope/duration must be reasonable; jurisdiction dependent.")

        return AnalysisReport(
            expert=self.name,
            query=query,
            frameworks_applied=list(self.frameworks),
            key_findings=findings,
            next_questions=[
                "What is the deal value and counterparty leverage?",
                "Which jurisdiction governs and which forum hears disputes?",
                "Are there carve-outs for IP, confidentiality, or willful misconduct?",
            ],
            confidence=0.7,
            metadata={"hot_clauses": present},
        )


# ---------------------------------------------------------------------------
# Mathematics — problem classification + canonical methods
# ---------------------------------------------------------------------------


class MathematicsExpert(_BaseExpert):
    name = "mathematics"
    discipline = "mathematics"
    frameworks = (
        "problem typing (algebra/calculus/probability/discrete)",
        "induction / contradiction / construction",
        "Polya's heuristic (understand → plan → execute → review)",
        "dimensional / unit analysis",
    )

    def analyze(self, query: str) -> AnalysisReport:
        q = query.lower()
        types: list[str] = []
        if any(k in q for k in ("integral", "derivative", "limit", "calculus")):
            types.append("calculus")
        if any(k in q for k in ("matrix", "linear", "eigen", "vector space")):
            types.append("linear algebra")
        if any(k in q for k in ("probab", "random", "distribution", "expectation", "variance")):
            types.append("probability")
        if any(k in q for k in ("graph", "combinat", "permutation", "discrete")):
            types.append("discrete")
        if any(k in q for k in ("ode", "pde", "differential equation")):
            types.append("differential equations")
        if not types:
            types.append("general algebra / arithmetic")

        findings: list[str] = [f"Problem type(s): {', '.join(types)}."]
        findings.append("Apply Polya: restate in own words, name knowns/unknowns, choose method, verify units.")
        if "calculus" in types:
            findings.append("Calculus heuristic: substitution → IBP → partial fractions → series.")
        if "probability" in types:
            findings.append("Probability heuristic: clarify sample space, independence, then condition.")

        return AnalysisReport(
            expert=self.name,
            query=query,
            frameworks_applied=list(self.frameworks),
            key_findings=findings,
            next_questions=[
                "What is the precise statement of the problem (with quantifiers)?",
                "Does the answer need a closed form or a numeric estimate?",
                "Is there a special case that already has a known method?",
            ],
            confidence=0.7,
            metadata={"types": types},
        )


# ---------------------------------------------------------------------------
# Physics — regime classification + conserved quantities
# ---------------------------------------------------------------------------


class PhysicsExpert(_BaseExpert):
    name = "physics"
    discipline = "physics"
    frameworks = (
        "regime selection (Newtonian / relativistic / quantum)",
        "conservation laws (energy / momentum / angular momentum / charge)",
        "dimensional analysis",
        "limiting cases",
    )

    def analyze(self, query: str) -> AnalysisReport:
        q = query.lower()
        regime = "Newtonian"
        if any(k in q for k in ("relativ", "lorentz", "near c", "speed of light")):
            regime = "relativistic"
        if any(k in q for k in ("quantum", "schrodinger", "hilbert", "qubit", "wavefunction")):
            regime = "quantum"
        if any(k in q for k in ("plasma", "magnetohydro", "mhd")):
            regime = "plasma / MHD"

        conserved: list[str] = []
        if any(k in q for k in ("collide", "collision", "elastic", "inelastic", "momentum")):
            conserved.append("momentum")
        if any(k in q for k in ("rotation", "torque", "angular")):
            conserved.append("angular momentum")
        if any(k in q for k in ("energy", "kinetic", "potential", "thermo")):
            conserved.append("energy")
        if not conserved:
            conserved.append("energy (default)")

        findings = [
            f"Regime: {regime}.",
            f"Conserved quantities to anchor: {', '.join(conserved)}.",
            "Dimensional check: verify units of every algebraic step.",
            "Limiting case: confirm the formula reduces to the known textbook result.",
        ]
        return AnalysisReport(
            expert=self.name,
            query=query,
            frameworks_applied=list(self.frameworks),
            key_findings=findings,
            next_questions=[
                "What is the boundary / initial condition?",
                "What are the relevant length and energy scales?",
                "Which approximations are admissible (small angle, weak field, ideal gas)?",
            ],
            confidence=0.7,
            metadata={"regime": regime, "conserved": conserved},
        )


# ---------------------------------------------------------------------------
# CBT psychologist — cognitive distortions, behavioral activation
# ---------------------------------------------------------------------------


class PsychologyCBTExpert(_BaseExpert):
    name = "psychology_cbt"
    discipline = "cognitive behavioral therapy"
    frameworks = (
        "ABC model (Activating event → Belief → Consequence)",
        "cognitive distortions catalog",
        "behavioral activation",
        "Socratic questioning",
        "exposure hierarchy",
    )

    DISTORTIONS = {
        "all-or-nothing": ("always", "never", "everyone", "no one"),
        "catastrophizing": ("disaster", "ruined", "worst", "terrible"),
        "mind reading": ("they think", "everyone thinks", "i know they"),
        "should statements": ("should", "must", "have to"),
        "personalization": ("my fault", "i caused", "because of me"),
        "labeling": ("i'm a failure", "i'm worthless", "i'm useless"),
    }

    CRISIS_TERMS = ("suicid", "self-harm", "kill myself", "end my life", "ending my life")

    def analyze(self, query: str) -> AnalysisReport:
        q = query.lower()
        findings: list[str] = []
        crisis = [t for t in self.CRISIS_TERMS if t in q]
        if crisis:
            findings.append(
                "CRISIS indicators present — protocol: reflect, assess intent/plan/means, "
                "warm-handoff to crisis services."
            )

        spotted: list[str] = []
        for label, cues in self.DISTORTIONS.items():
            if any(cue in q for cue in cues):
                spotted.append(label)
        if spotted:
            findings.append("Likely cognitive distortions: " + ", ".join(spotted) + ".")
        else:
            findings.append("No obvious distortions in the surface text — probe for examples.")

        findings.append("Apply ABC: name event, surface automatic belief, label resulting consequence.")
        findings.append("Behavioral activation: schedule one valued, low-effort action in the next 24h.")

        return AnalysisReport(
            expert=self.name,
            query=query,
            frameworks_applied=list(self.frameworks),
            key_findings=findings,
            next_questions=[
                "What thought ran through your mind in that moment?",
                "What evidence supports / contradicts that thought?",
                "What would you tell a friend in the same situation?",
            ],
            confidence=0.85 if crisis else 0.7,
            metadata={"crisis": bool(crisis), "distortions": spotted},
        )


# ---------------------------------------------------------------------------
# Economics — micro/macro framing, partial equilibrium reasoning
# ---------------------------------------------------------------------------


class EconomicsExpert(_BaseExpert):
    name = "economics"
    discipline = "economics"
    frameworks = (
        "supply / demand framing",
        "elasticity & marginal reasoning",
        "comparative statics",
        "externalities & market failure",
        "macro IS-LM / AD-AS",
    )

    def analyze(self, query: str) -> AnalysisReport:
        q = query.lower()
        scope = "micro"
        if any(k in q for k in ("inflation", "gdp", "fed", "central bank", "macro", "unemployment")):
            scope = "macro"
        if any(k in q for k in ("trade", "tariff", "exchange rate", "import", "export")):
            scope = "international"

        findings: list[str] = [f"Scope: {scope} economics."]
        if "elasticity" in q or "demand" in q:
            findings.append("Run elasticity: who bears burden when price moves?")
        if "tariff" in q:
            findings.append("Tariff: domestic producers gain, consumers lose, deadweight loss net negative for small open economies.")
        if "monopol" in q:
            findings.append("Monopoly: P > MC; deadweight triangle; consider regulation or contestability.")
        if scope == "macro":
            findings.append("Macro: think AD vs AS; transmission via interest rate and expectations.")

        return AnalysisReport(
            expert=self.name,
            query=query,
            frameworks_applied=list(self.frameworks),
            key_findings=findings,
            next_questions=[
                "Are we in short run or long run?",
                "What externalities or information asymmetries break the first welfare theorem here?",
                "Whose welfare are we optimizing — consumer, producer, or social planner?",
            ],
            confidence=0.7,
            metadata={"scope": scope},
        )


# ---------------------------------------------------------------------------
# Chemistry — reaction typing, mechanism hints
# ---------------------------------------------------------------------------


class ChemistryExpert(_BaseExpert):
    name = "chemistry"
    discipline = "chemistry"
    frameworks = (
        "reaction typing (acid-base / redox / SN1-SN2 / E1-E2 / pericyclic)",
        "thermodynamics vs kinetics",
        "Le Chatelier's principle",
        "mechanism with arrow pushing",
    )

    def analyze(self, query: str) -> AnalysisReport:
        q = query.lower()
        rxn_types: list[str] = []
        if any(k in q for k in ("acid", "base", "ph", "buffer", "henderson")):
            rxn_types.append("acid-base")
        if any(k in q for k in ("oxidation", "reduction", "redox", "electrochem")):
            rxn_types.append("redox")
        if any(k in q for k in ("sn1", "sn2", "substitution")):
            rxn_types.append("nucleophilic substitution")
        if any(k in q for k in ("e1", "e2", "elimination")):
            rxn_types.append("elimination")
        if any(k in q for k in ("equilibrium", "le chatelier")):
            rxn_types.append("equilibrium")
        if not rxn_types:
            rxn_types.append("general")

        findings = [
            f"Reaction class(es): {', '.join(rxn_types)}.",
            "Decide kinetic vs thermodynamic control before invoking Le Chatelier.",
            "If mechanism: push electrons from highest-HOMO nucleophile to lowest-LUMO electrophile.",
        ]
        return AnalysisReport(
            expert=self.name,
            query=query,
            frameworks_applied=list(self.frameworks),
            key_findings=findings,
            next_questions=[
                "Solvent (polar protic, polar aprotic, nonpolar)?",
                "Substrate class (1°, 2°, 3°)?",
                "Are we asked for product, mechanism, or rate law?",
            ],
            confidence=0.7,
            metadata={"reaction_types": rxn_types},
        )


# ---------------------------------------------------------------------------
# Neuroscience — circuit-level framing
# ---------------------------------------------------------------------------


class NeuroscienceExpert(_BaseExpert):
    name = "neuroscience"
    discipline = "neuroscience"
    frameworks = (
        "circuit-level decomposition (input → integration → output)",
        "Marr's three levels (computational / algorithmic / implementation)",
        "neuromodulator framing (DA / 5-HT / NE / ACh)",
        "lesion / stimulation / recording evidence triangulation",
    )

    BRAIN_AREAS = (
        "prefrontal", "amygdala", "hippocamp", "thalamus", "striatum",
        "basal ganglia", "cortex", "cerebellum", "brainstem", "hypothalamus",
    )

    def analyze(self, query: str) -> AnalysisReport:
        q = query.lower()
        areas = [a for a in self.BRAIN_AREAS if a in q]
        findings: list[str] = []
        if areas:
            findings.append("Areas mentioned: " + ", ".join(areas) + " — frame circuit input/output.")
        if any(k in q for k in ("memory", "learning")):
            findings.append("Memory question: separate encoding / consolidation / retrieval; hippocampal vs cortical.")
        if any(k in q for k in ("emotion", "fear", "reward")):
            findings.append("Affective: amygdala (threat), VTA-striatum (reward); modulators DA/5-HT/NE.")
        if any(k in q for k in ("eeg", "fmri", "spike", "neuropixel")):
            findings.append("Methods question: address temporal vs spatial resolution tradeoff.")
        if not findings:
            findings.append("Apply Marr: pick a level and stay consistent within the answer.")

        return AnalysisReport(
            expert=self.name,
            query=query,
            frameworks_applied=list(self.frameworks),
            key_findings=findings,
            next_questions=[
                "What level (computational, algorithmic, implementation) is the question at?",
                "What evidence types are admissible (lesion, recording, stimulation, model)?",
                "What is the behavioral readout?",
            ],
            confidence=0.7,
            metadata={"areas": areas},
        )


# ---------------------------------------------------------------------------
# Singletons + factories
# ---------------------------------------------------------------------------


_clinician: ClinicianExpert | None = None
_contracts_law: ContractsLawExpert | None = None
_mathematics: MathematicsExpert | None = None
_physics: PhysicsExpert | None = None
_psychology_cbt: PsychologyCBTExpert | None = None
_economics: EconomicsExpert | None = None
_chemistry: ChemistryExpert | None = None
_neuroscience: NeuroscienceExpert | None = None


def get_clinician() -> ClinicianExpert:
    global _clinician
    if _clinician is None:
        _clinician = ClinicianExpert()
    return _clinician


def get_contracts_law() -> ContractsLawExpert:
    global _contracts_law
    if _contracts_law is None:
        _contracts_law = ContractsLawExpert()
    return _contracts_law


def get_mathematics() -> MathematicsExpert:
    global _mathematics
    if _mathematics is None:
        _mathematics = MathematicsExpert()
    return _mathematics


def get_physics() -> PhysicsExpert:
    global _physics
    if _physics is None:
        _physics = PhysicsExpert()
    return _physics


def get_psychology_cbt() -> PsychologyCBTExpert:
    global _psychology_cbt
    if _psychology_cbt is None:
        _psychology_cbt = PsychologyCBTExpert()
    return _psychology_cbt


def get_economics() -> EconomicsExpert:
    global _economics
    if _economics is None:
        _economics = EconomicsExpert()
    return _economics


def get_chemistry() -> ChemistryExpert:
    global _chemistry
    if _chemistry is None:
        _chemistry = ChemistryExpert()
    return _chemistry


def get_neuroscience() -> NeuroscienceExpert:
    global _neuroscience
    if _neuroscience is None:
        _neuroscience = NeuroscienceExpert()
    return _neuroscience


def all_experts() -> dict[str, _BaseExpert]:
    """Map of every expert keyed by name."""
    return {
        "clinician": get_clinician(),
        "contracts_law": get_contracts_law(),
        "mathematics": get_mathematics(),
        "physics": get_physics(),
        "psychology_cbt": get_psychology_cbt(),
        "economics": get_economics(),
        "chemistry": get_chemistry(),
        "neuroscience": get_neuroscience(),
    }


__all__ = [
    "AnalysisReport",
    "ClinicianExpert",
    "ContractsLawExpert",
    "MathematicsExpert",
    "PhysicsExpert",
    "PsychologyCBTExpert",
    "EconomicsExpert",
    "ChemistryExpert",
    "NeuroscienceExpert",
    "get_clinician",
    "get_contracts_law",
    "get_mathematics",
    "get_physics",
    "get_psychology_cbt",
    "get_economics",
    "get_chemistry",
    "get_neuroscience",
    "all_experts",
]
