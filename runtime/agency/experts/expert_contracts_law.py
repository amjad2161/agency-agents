"""JARVIS Expert: Contracts & Law (legal analysis)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContractsLawQuery:
    query: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContractsLawResult:
    answer: str
    confidence: float
    domain: str
    sources: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


_KEYWORDS = (
    "contract", "agreement", "clause", "liability", "indemn", "warrant",
    "breach", "termination", "jurisdiction", "governing law", "arbitration",
    "nda", "non-disclosure", "non-compete", "ip ", "intellectual property",
    "license", "lessor", "lessee", "tenant", "landlord", "lawsuit", "tort",
    "statute", "regulation", "compliance", "gdpr", "hipaa", "ccpa", "sox",
    "litigation", "settlement", "damages", "force majeure",
)

_RISK_CLAUSES = {
    "unlimited liability": "HIGH — no liability cap exposes party to uncapped damages",
    "no termination": "HIGH — perpetual obligation without exit",
    "auto-renewal": "MEDIUM — auto-renewal without notice may trap party",
    "indemnify": "MEDIUM — indemnification scope must be reviewed",
    "as-is": "MEDIUM — disclaims warranties, limits remedies",
    "non-compete": "MEDIUM — enforceability varies by jurisdiction",
    "liquidated damages": "MEDIUM — must be reasonable, not a penalty",
    "exclusive": "LOW — exclusivity may limit options",
    "assignable": "LOW — assignment rights affect counterparty stability",
}

_JURISDICTIONS = {
    "delaware": "US — common Delaware choice for corporate matters",
    "new york": "US — financial / commercial contracts",
    "california": "US — strict consumer protections, non-competes generally void",
    "england": "UK — common law, English law often used internationally",
    "singapore": "SG — common arbitration seat for Asia",
    "switzerland": "CH — neutral arbitration seat",
}

_FRAMEWORKS = {
    "gdpr": "EU privacy regulation (Regulation 2016/679)",
    "hipaa": "US health information privacy (45 CFR 160-164)",
    "ccpa": "California Consumer Privacy Act",
    "sox": "Sarbanes-Oxley Act — financial reporting controls",
    "pci-dss": "Payment Card Industry Data Security Standard",
    "iso 27001": "Information security management standard",
    "soc 2": "AICPA service organization controls",
}


class ContractsLawExpert:
    """JARVIS expert for contract and legal analysis."""

    DOMAIN = "contracts_law"
    VERSION = "1.0.0"

    def analyze(self, query: str, context: dict[str, Any] | None = None) -> ContractsLawResult:
        ctx = context or {}
        confidence = self.can_handle(query)
        sources: list[str] = []
        meta: dict[str, Any] = {}
        parts: list[str] = []

        clauses = self.extract_clauses(query)
        if clauses:
            meta["clauses"] = clauses
            parts.append(f"Clauses identified: {', '.join(clauses)}.")

        risks = self.flag_risks(query)
        if risks:
            meta["risks"] = risks
            sources.append("risk-clause-db")
            parts.append("Risk flags: " + "; ".join(risks) + ".")

        jx = self.detect_jurisdiction(query)
        if jx:
            meta["jurisdiction"] = jx
            sources.append("jurisdiction-db")
            parts.append(f"Jurisdiction: {jx['name']} — {jx['note']}.")

        comp = self.compliance_check(query)
        if comp:
            meta["compliance"] = comp
            sources.append("compliance-frameworks")
            parts.append("Compliance frameworks: " + ", ".join(comp) + ".")

        if not parts:
            parts.append("Legal query received. No clauses, risks, or jurisdictions detected. "
                         "Provide contract text or specific clause for review.")
            confidence = min(confidence, 0.3)

        return ContractsLawResult(
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

    def extract_clauses(self, query: str) -> list[str]:
        q = query.lower()
        types = ["liability", "indemnification", "termination", "confidentiality",
                 "non-compete", "warranty", "force majeure", "arbitration",
                 "governing law", "ip assignment", "payment terms"]
        return [t for t in types if t.split()[0] in q or t in q]

    def flag_risks(self, query: str) -> list[str]:
        q = query.lower()
        out: list[str] = []
        for phrase, msg in _RISK_CLAUSES.items():
            if phrase in q:
                out.append(f"'{phrase}' → {msg}")
        return out

    def detect_jurisdiction(self, query: str) -> dict[str, str] | None:
        q = query.lower()
        for name, note in _JURISDICTIONS.items():
            if name in q:
                return {"name": name.title(), "note": note}
        return None

    def compliance_check(self, query: str) -> list[str]:
        q = query.lower()
        return [f"{k.upper()}: {v}" for k, v in _FRAMEWORKS.items() if k in q]

    def parse_legal_language(self, text: str) -> dict[str, Any]:
        out: dict[str, Any] = {
            "shall_count": len(re.findall(r"\bshall\b", text, re.IGNORECASE)),
            "must_count": len(re.findall(r"\bmust\b", text, re.IGNORECASE)),
            "may_count": len(re.findall(r"\bmay\b", text, re.IGNORECASE)),
            "defined_terms": re.findall(r'"([A-Z][A-Za-z ]+)"', text),
            "section_refs": re.findall(r"[Ss]ection\s+\d+(?:\.\d+)*", text),
        }
        return out

    def severity_level(self, risk_message: str) -> str:
        m = risk_message.upper()
        if "HIGH" in m:
            return "HIGH"
        if "MEDIUM" in m:
            return "MEDIUM"
        if "LOW" in m:
            return "LOW"
        return "UNKNOWN"

    def suggest_redlines(self, query: str) -> list[str]:
        q = query.lower()
        out: list[str] = []
        if "unlimited liability" in q:
            out.append("Cap liability at fees paid in trailing 12 months.")
        if "indemnify" in q and "mutual" not in q:
            out.append("Negotiate mutual indemnification.")
        if "auto-renewal" in q:
            out.append("Add 30-90 day non-renewal notice carve-out.")
        if "non-compete" in q:
            out.append("Limit duration ≤12 months and define geography narrowly.")
        return out

    def status(self) -> dict[str, Any]:
        return {
            "domain": self.DOMAIN,
            "version": self.VERSION,
            "ok": True,
            "risk_clauses": len(_RISK_CLAUSES),
            "jurisdictions": len(_JURISDICTIONS),
            "frameworks": list(_FRAMEWORKS.keys()),
        }


_singleton: ContractsLawExpert | None = None


def get_expert() -> ContractsLawExpert:
    global _singleton
    if _singleton is None:
        _singleton = ContractsLawExpert()
    return _singleton
