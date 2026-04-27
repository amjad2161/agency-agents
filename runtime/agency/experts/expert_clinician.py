"""JARVIS Expert: Clinician (medical/clinical reasoning)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClinicianQuery:
    query: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ClinicianResult:
    answer: str
    confidence: float
    domain: str
    sources: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


_KEYWORDS = (
    "symptom", "diagnosis", "drug", "medication", "treatment", "patient",
    "clinical", "disease", "syndrome", "icd", "dsm", "prognosis", "doctor",
    "medical", "therapy", "dose", "dosage", "contraindication", "side effect",
    "fever", "pain", "rash", "cough", "infection", "allergy", "hypertension",
    "diabetes", "depression", "anxiety", "cancer",
)

_DRUG_INTERACTIONS = {
    ("warfarin", "aspirin"): "high bleeding risk — concomitant use increases hemorrhage",
    ("ssri", "maoi"): "serotonin syndrome — contraindicated, requires 14-day washout",
    ("ace inhibitor", "potassium"): "hyperkalemia risk — monitor serum potassium",
    ("statin", "fibrate"): "rhabdomyolysis risk — increased myopathy",
    ("nsaid", "lithium"): "lithium toxicity — reduces renal clearance",
}

_ICD11_BUCKETS = {
    "respiratory": ["cough", "dyspnea", "wheeze", "pneumonia", "asthma", "copd"],
    "cardiovascular": ["chest pain", "palpitation", "hypertension", "syncope"],
    "neurological": ["headache", "seizure", "vertigo", "weakness", "paresthesia"],
    "gastrointestinal": ["nausea", "vomiting", "diarrhea", "abdominal pain"],
    "dermatological": ["rash", "pruritus", "lesion", "urticaria"],
    "psychiatric": ["depression", "anxiety", "psychosis", "mania", "insomnia"],
}

_DSM5_CRITERIA = {
    "major_depressive": ["depressed mood", "anhedonia", "weight change", "insomnia",
                          "psychomotor", "fatigue", "worthlessness", "concentration", "suicidal"],
    "generalized_anxiety": ["excessive worry", "restlessness", "fatigue", "concentration",
                             "irritability", "muscle tension", "sleep"],
    "ptsd": ["intrusion", "avoidance", "negative cognition", "arousal"],
}


class ClinicianExpert:
    """JARVIS expert for medical and clinical reasoning."""

    DOMAIN = "clinician"
    VERSION = "1.0.0"

    def analyze(self, query: str, context: dict[str, Any] | None = None) -> ClinicianResult:
        ctx = context or {}
        q = query.lower()
        confidence = self.can_handle(query)
        sources: list[str] = []
        meta: dict[str, Any] = {}
        parts: list[str] = []

        symptoms = self.extract_symptoms(query)
        if symptoms:
            meta["symptoms"] = symptoms
            buckets = self.classify_icd11(symptoms)
            meta["icd11_buckets"] = buckets
            sources.append("ICD-11")
            parts.append(f"Identified symptoms: {', '.join(symptoms)}.")
            if buckets:
                parts.append(f"Likely ICD-11 chapter(s): {', '.join(buckets)}.")
            ddx = self.differential_diagnosis(symptoms)
            if ddx:
                meta["differential"] = ddx
                parts.append("Differential: " + "; ".join(ddx[:5]) + ".")

        drugs = self.extract_drugs(query)
        if drugs:
            meta["drugs"] = drugs
            interactions = self.check_drug_interactions(drugs)
            if interactions:
                meta["interactions"] = interactions
                sources.append("drug-interaction-db")
                parts.append("Drug interactions: " + "; ".join(interactions) + ".")

        dsm = self.match_dsm5(query)
        if dsm:
            meta["dsm5_match"] = dsm
            sources.append("DSM-5")
            parts.append(f"DSM-5 pattern match: {', '.join(dsm)}.")

        if not parts:
            parts.append("Clinical query received. Insufficient signal for ddx — "
                         "request more clinical context (history, exam, labs).")
            confidence = min(confidence, 0.3)

        return ClinicianResult(
            answer=" ".join(parts),
            confidence=confidence,
            domain=self.DOMAIN,
            sources=sources,
            metadata=meta,
        )

    def can_handle(self, query: str) -> float:
        q = query.lower()
        hits = sum(1 for kw in _KEYWORDS if kw in q)
        if hits == 0:
            return 0.0
        return min(1.0, 0.3 + 0.15 * hits)

    def extract_symptoms(self, query: str) -> list[str]:
        q = query.lower()
        symptoms: list[str] = []
        for bucket_syms in _ICD11_BUCKETS.values():
            for s in bucket_syms:
                if s in q and s not in symptoms:
                    symptoms.append(s)
        return symptoms

    def classify_icd11(self, symptoms: list[str]) -> list[str]:
        buckets: list[str] = []
        for chapter, syms in _ICD11_BUCKETS.items():
            if any(s in symptoms for s in syms):
                buckets.append(chapter)
        return buckets

    def differential_diagnosis(self, symptoms: list[str]) -> list[str]:
        ddx: list[str] = []
        s = set(symptoms)
        if {"cough", "dyspnea"} & s:
            ddx.extend(["pneumonia", "asthma exacerbation", "COPD", "pulmonary embolism"])
        if "chest pain" in s:
            ddx.extend(["acute coronary syndrome", "GERD", "costochondritis", "pulmonary embolism"])
        if {"headache", "vertigo"} & s:
            ddx.extend(["migraine", "tension headache", "vestibular dysfunction"])
        if {"depressed mood", "anhedonia", "fatigue"} & s:
            ddx.append("major depressive disorder")
        if "fever" in s:
            ddx.extend(["viral syndrome", "bacterial infection", "sepsis"])
        return ddx

    def extract_drugs(self, query: str) -> list[str]:
        q = query.lower()
        drugs: list[str] = []
        candidates = ["warfarin", "aspirin", "ssri", "maoi", "ace inhibitor", "potassium",
                      "statin", "fibrate", "nsaid", "lithium", "metformin", "insulin",
                      "ibuprofen", "acetaminophen", "amoxicillin"]
        for d in candidates:
            if d in q and d not in drugs:
                drugs.append(d)
        return drugs

    def check_drug_interactions(self, drugs: list[str]) -> list[str]:
        out: list[str] = []
        s = set(drugs)
        for (a, b), msg in _DRUG_INTERACTIONS.items():
            if a in s and b in s:
                out.append(f"{a}+{b}: {msg}")
        return out

    def match_dsm5(self, query: str) -> list[str]:
        q = query.lower()
        matches: list[str] = []
        for disorder, criteria in _DSM5_CRITERIA.items():
            hits = sum(1 for c in criteria if c in q)
            if hits >= 2:
                matches.append(f"{disorder} ({hits}/{len(criteria)} criteria)")
        return matches

    def suggest_workup(self, symptoms: list[str]) -> list[str]:
        s = set(symptoms)
        labs: list[str] = ["CBC", "BMP"]
        if "chest pain" in s:
            labs.extend(["troponin", "ECG", "chest x-ray"])
        if "cough" in s or "dyspnea" in s:
            labs.append("chest x-ray")
        if "fever" in s:
            labs.extend(["blood culture", "urinalysis"])
        return labs

    def evidence_level(self, source: str) -> str:
        s = source.lower()
        if "rct" in s or "meta-analysis" in s or "cochrane" in s:
            return "Level I"
        if "cohort" in s or "case-control" in s:
            return "Level II"
        if "case series" in s or "case report" in s:
            return "Level III"
        if "expert" in s or "opinion" in s:
            return "Level IV"
        return "unclassified"

    def status(self) -> dict[str, Any]:
        return {
            "domain": self.DOMAIN,
            "version": self.VERSION,
            "ok": True,
            "frameworks": ["DSM-5", "ICD-11"],
            "interactions_db": len(_DRUG_INTERACTIONS),
        }


_singleton: ClinicianExpert | None = None


def get_expert() -> ClinicianExpert:
    global _singleton
    if _singleton is None:
        _singleton = ClinicianExpert()
    return _singleton
