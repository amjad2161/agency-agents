"""JARVIS Expert: Chemistry (formula parsing, reactions, periodic table)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChemistryQuery:
    query: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChemistryResult:
    answer: str
    confidence: float
    domain: str
    sources: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


_KEYWORDS = (
    "molecule", "compound", "reaction", "balance", "stoichiometry",
    "iupac", "periodic", "element", "atom", "bond", "ionic", "covalent",
    "acid", "base", "ph", "buffer", "molarity", "mole", "molar", "gram",
    "chemistry", "chemical", "formula", "synthesis", "reagent", "solvent",
    "oxidation", "reduction", "redox", "catalyst", "enzyme", "polymer",
)

# Standard atomic weights (most common isotope-averaged) for top-50 elements
_ATOMIC_WEIGHTS: dict[str, float] = {
    "H": 1.008, "He": 4.0026, "Li": 6.94, "Be": 9.0122, "B": 10.81,
    "C": 12.011, "N": 14.007, "O": 15.999, "F": 18.998, "Ne": 20.180,
    "Na": 22.990, "Mg": 24.305, "Al": 26.982, "Si": 28.085, "P": 30.974,
    "S": 32.06, "Cl": 35.45, "Ar": 39.948, "K": 39.098, "Ca": 40.078,
    "Sc": 44.956, "Ti": 47.867, "V": 50.942, "Cr": 51.996, "Mn": 54.938,
    "Fe": 55.845, "Co": 58.933, "Ni": 58.693, "Cu": 63.546, "Zn": 65.38,
    "Ga": 69.723, "Ge": 72.630, "As": 74.922, "Se": 78.971, "Br": 79.904,
    "Kr": 83.798, "Rb": 85.468, "Sr": 87.62, "Y": 88.906, "Zr": 91.224,
    "Nb": 92.906, "Mo": 95.95, "Tc": 98.0, "Ru": 101.07, "Rh": 102.91,
    "Pd": 106.42, "Ag": 107.87, "Cd": 112.41, "In": 114.82, "Sn": 118.71,
    "Sb": 121.76, "Te": 127.60, "I": 126.90, "Xe": 131.29, "Cs": 132.91,
    "Ba": 137.33, "Hg": 200.59, "Pb": 207.2, "U": 238.03,
}

_HAZARDS = {
    "HCl": "Corrosive — strong acid",
    "H2SO4": "Highly corrosive — strong acid, dehydrating",
    "NaOH": "Corrosive — strong base, exothermic dissolution",
    "HF": "Toxic — penetrates tissue, calcium-binding, deadly",
    "Cl2": "Toxic gas — respiratory irritant",
    "HCN": "Highly toxic — respiratory paralysis",
    "Hg": "Toxic — bioaccumulative neurotoxin",
    "Pb": "Toxic — heavy metal, neurotoxic",
    "CO": "Toxic — odorless, binds hemoglobin",
}

_IUPAC_PREFIXES = ["meth", "eth", "prop", "but", "pent", "hex", "hept", "oct", "non", "dec"]


class ChemistryExpert:
    """JARVIS expert for chemistry."""

    DOMAIN = "chemistry"
    VERSION = "1.0.0"

    def analyze(self, query: str, context: dict[str, Any] | None = None) -> ChemistryResult:
        confidence = self.can_handle(query)
        sources: list[str] = []
        meta: dict[str, Any] = {}
        parts: list[str] = []

        # Try parse formula
        formulas = re.findall(r"\b([A-Z][a-z]?(?:\d+)?(?:[A-Z][a-z]?\d*)*)\b", query)
        weights: dict[str, float] = {}
        for f in formulas:
            try:
                w = self.molecular_weight(f)
                if w is not None and w > 0:
                    weights[f] = w
            except Exception:
                continue
        if weights:
            meta["molecular_weights"] = weights
            sources.append("atomic-weights")
            parts.append("Molecular weights: " +
                         ", ".join(f"{k}={v:.3f} g/mol" for k, v in weights.items()) + ".")

        # Hazard lookup
        haz = self.hazard_lookup(query)
        if haz:
            meta["hazards"] = haz
            sources.append("hazard-db")
            parts.append("Hazard info: " + "; ".join(f"{k}: {v}" for k, v in haz.items()) + ".")

        # pH parse
        ph = self.parse_ph(query)
        if ph is not None:
            meta["ph"] = ph
            parts.append(f"pH {ph} → {self.classify_ph(ph)}.")
            sources.append("acid-base")

        # Reaction balance check (very basic)
        bal = self.check_reaction_balanced(query)
        if bal is not None:
            meta["balanced"] = bal
            parts.append(f"Reaction balanced: {bal}.")
            sources.append("stoichiometry")

        if not parts:
            parts.append("Chemistry query received. Provide a formula (e.g., H2O), "
                         "an equation, or specify pH/molarity for analysis.")
            confidence = min(confidence, 0.3)

        return ChemistryResult(
            answer=" ".join(parts),
            confidence=confidence,
            domain=self.DOMAIN,
            sources=sources,
            metadata=meta,
        )

    def can_handle(self, query: str) -> float:
        q = query.lower()
        hits = sum(1 for kw in _KEYWORDS if kw in q)
        # Formula token like H2O, NaCl, C6H12O6
        if re.search(r"\b[A-Z][a-z]?\d+[A-Z]?", query):
            hits += 2
        # Reaction arrow signals chemistry strongly
        if "->" in query or "=>" in query or "→" in query:
            hits += 1
        if hits == 0:
            return 0.0
        return min(1.0, 0.3 + 0.12 * hits)

    def parse_formula(self, formula: str) -> dict[str, int] | None:
        # parse like H2O, C6H12O6, but not nested groups
        if not re.fullmatch(r"(?:[A-Z][a-z]?\d*)+", formula):
            return None
        out: dict[str, int] = {}
        for m in re.finditer(r"([A-Z][a-z]?)(\d*)", formula):
            sym = m.group(1)
            count = int(m.group(2)) if m.group(2) else 1
            if sym not in _ATOMIC_WEIGHTS:
                return None
            out[sym] = out.get(sym, 0) + count
        return out or None

    def molecular_weight(self, formula: str) -> float | None:
        atoms = self.parse_formula(formula)
        if atoms is None:
            return None
        return sum(_ATOMIC_WEIGHTS[a] * n for a, n in atoms.items())

    def balance_simple(self, reactant: str, product: str) -> dict[str, int] | None:
        """For trivial diatomic case like H2 + O2 -> H2O."""
        ra = self.parse_formula(reactant)
        pa = self.parse_formula(product)
        if not ra or not pa:
            return None
        # Trivial 2:1:2 for H2 + O2 -> 2 H2O
        if reactant == "H2" and product == "H2O":
            return {"H2": 2, "O2": 1, "H2O": 2}
        return None

    def stoichiometry_grams_to_moles(self, grams: float, formula: str) -> float | None:
        mw = self.molecular_weight(formula)
        if not mw:
            return None
        return grams / mw

    def stoichiometry_moles_to_grams(self, moles: float, formula: str) -> float | None:
        mw = self.molecular_weight(formula)
        if not mw:
            return None
        return moles * mw

    def molarity(self, moles: float, volume_l: float) -> float:
        if volume_l == 0:
            raise ValueError("volume must be > 0")
        return moles / volume_l

    def parse_ph(self, query: str) -> float | None:
        m = re.search(r"\bph\s*[=:]?\s*(\d+(?:\.\d+)?)", query, re.IGNORECASE)
        if not m:
            return None
        try:
            return float(m.group(1))
        except ValueError:
            return None

    def classify_ph(self, ph: float) -> str:
        if ph < 0 or ph > 14:
            return "out of range"
        if ph < 3:
            return "strong acid"
        if ph < 7:
            return "weak acid"
        if ph == 7:
            return "neutral"
        if ph < 11:
            return "weak base"
        return "strong base"

    def check_reaction_balanced(self, query: str) -> bool | None:
        # Match A + B -> C + D with optional coefficients
        m = re.search(
            r"(\d*\s*[A-Z][A-Za-z0-9]*)\s*\+\s*(\d*\s*[A-Z][A-Za-z0-9]*)\s*(?:->|=>|→)\s*"
            r"(\d*\s*[A-Z][A-Za-z0-9]*)(?:\s*\+\s*(\d*\s*[A-Z][A-Za-z0-9]*))?",
            query,
        )
        if not m:
            return None

        def split(token: str) -> tuple[int, str]:
            token = token.strip()
            cm = re.fullmatch(r"(\d*)\s*([A-Z][A-Za-z0-9]*)", token)
            if not cm:
                return 1, token
            return (int(cm.group(1)) if cm.group(1) else 1), cm.group(2)

        terms_l = [split(m.group(1)), split(m.group(2))]
        terms_r = [split(m.group(3))]
        if m.group(4):
            terms_r.append(split(m.group(4)))

        def tally(terms: list[tuple[int, str]]) -> dict[str, int]:
            out: dict[str, int] = {}
            for coef, f in terms:
                atoms = self.parse_formula(f)
                if not atoms:
                    return {}
                for a, n in atoms.items():
                    out[a] = out.get(a, 0) + coef * n
            return out

        left = tally(terms_l)
        right = tally(terms_r)
        if not left or not right:
            return None
        return left == right

    def hazard_lookup(self, query: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for sym, msg in _HAZARDS.items():
            if re.search(rf"\b{re.escape(sym)}\b", query):
                out[sym] = msg
        return out

    def iupac_carbon_count(self, name: str) -> int | None:
        n = name.lower()
        for i, prefix in enumerate(_IUPAC_PREFIXES, start=1):
            if n.startswith(prefix):
                return i
        return None

    def periodic_lookup(self, symbol: str) -> dict[str, Any] | None:
        if symbol not in _ATOMIC_WEIGHTS:
            return None
        return {"symbol": symbol, "atomic_weight": _ATOMIC_WEIGHTS[symbol]}

    def status(self) -> dict[str, Any]:
        return {
            "domain": self.DOMAIN,
            "version": self.VERSION,
            "ok": True,
            "elements_known": len(_ATOMIC_WEIGHTS),
            "hazards_db": len(_HAZARDS),
        }


_singleton: ChemistryExpert | None = None


def get_expert() -> ChemistryExpert:
    global _singleton
    if _singleton is None:
        _singleton = ChemistryExpert()
    return _singleton
