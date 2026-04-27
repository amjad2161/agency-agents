"""JARVIS Expert: Physics (classical, relativistic, quantum)."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PhysicsQuery:
    query: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class PhysicsResult:
    answer: str
    confidence: float
    domain: str
    sources: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


_KEYWORDS = (
    "force", "mass", "velocity", "acceleration", "energy", "momentum",
    "physics", "newton", "einstein", "quantum", "relativity", "wavelength",
    "frequency", "voltage", "current", "resistance", "charge", "field",
    "gravity", "gravitational", "kinetic", "potential", "thermodynamic",
    "entropy", "temperature", "pressure", "volume", "joule", "watt",
    "newton's", "kepler", "schrodinger", "planck", "photon", "electron",
    "convert", "meter", "kilometer", "second", "kilogram",
)

# SI base + derived
_CONSTANTS = {
    "c": (299_792_458.0, "m/s", "speed of light"),
    "h": (6.626_070_15e-34, "J·s", "Planck constant"),
    "hbar": (1.054_571_817e-34, "J·s", "reduced Planck constant"),
    "k_B": (1.380_649e-23, "J/K", "Boltzmann constant"),
    "G": (6.674_30e-11, "m³/(kg·s²)", "gravitational constant"),
    "g": (9.806_65, "m/s²", "standard gravity"),
    "e": (1.602_176_634e-19, "C", "elementary charge"),
    "m_e": (9.109_383_7015e-31, "kg", "electron mass"),
    "m_p": (1.672_621_923_69e-27, "kg", "proton mass"),
    "N_A": (6.022_140_76e23, "1/mol", "Avogadro"),
    "R": (8.314_462_618, "J/(mol·K)", "gas constant"),
    "epsilon_0": (8.854_187_8128e-12, "F/m", "vacuum permittivity"),
    "mu_0": (1.256_637_062_12e-6, "N/A²", "vacuum permeability"),
}

# Length conversion factors to meters
_LENGTH_TO_M = {
    "m": 1.0, "meter": 1.0, "meters": 1.0,
    "km": 1000.0, "kilometer": 1000.0,
    "cm": 0.01, "centimeter": 0.01,
    "mm": 0.001, "millimeter": 0.001,
    "um": 1e-6, "micrometer": 1e-6,
    "nm": 1e-9, "nanometer": 1e-9,
    "in": 0.0254, "inch": 0.0254, "inches": 0.0254,
    "ft": 0.3048, "foot": 0.3048, "feet": 0.3048,
    "mile": 1609.344, "miles": 1609.344, "mi": 1609.344,
}

_TIME_TO_S = {
    "s": 1.0, "second": 1.0, "seconds": 1.0, "sec": 1.0,
    "ms": 1e-3, "millisecond": 1e-3,
    "us": 1e-6, "microsecond": 1e-6,
    "ns": 1e-9, "nanosecond": 1e-9,
    "min": 60.0, "minute": 60.0, "minutes": 60.0,
    "h": 3600.0, "hr": 3600.0, "hour": 3600.0, "hours": 3600.0,
    "day": 86400.0, "days": 86400.0,
}

_MASS_TO_KG = {
    "kg": 1.0, "kilogram": 1.0,
    "g": 1e-3, "gram": 1e-3, "grams": 1e-3,
    "mg": 1e-6, "milligram": 1e-6,
    "lb": 0.453_592_37, "pound": 0.453_592_37, "pounds": 0.453_592_37,
    "oz": 0.028_349_523_125, "ounce": 0.028_349_523_125,
}


class PhysicsExpert:
    """JARVIS expert for physics reasoning."""

    DOMAIN = "physics"
    VERSION = "1.0.0"

    def analyze(self, query: str, context: dict[str, Any] | None = None) -> PhysicsResult:
        confidence = self.can_handle(query)
        sources: list[str] = []
        meta: dict[str, Any] = {}
        parts: list[str] = []

        domain = self.classify_domain(query)
        meta["physics_domain"] = domain
        parts.append(f"Physics domain: {domain}.")

        # Newton F=ma
        ma = re.search(r"f\s*=\s*ma|force.*mass.*accel", query, re.IGNORECASE)
        if ma:
            parts.append("Newton's second law: F = m·a.")
            sources.append("newtonian-mechanics")

        # Kinetic energy
        if "kinetic" in query.lower():
            parts.append("Kinetic energy: KE = ½·m·v².")
            sources.append("classical-mechanics")

        # Conversion attempt
        conv = self.parse_unit_conversion(query)
        if conv is not None:
            meta["conversion"] = conv
            parts.append(f"Conversion: {conv['value']} {conv['from']} = {conv['result']:.6g} {conv['to']}.")
            sources.append("unit-converter")

        # Constant lookup
        const = self.lookup_constant(query)
        if const:
            meta["constant"] = const
            parts.append(f"Constant {const['symbol']} = {const['value']} {const['unit']} ({const['name']}).")
            sources.append("CODATA")

        # Dimensional analysis
        dims = self.dimensional_analysis(query)
        if dims:
            meta["dimensions"] = dims

        if not parts or len(parts) == 1:
            parts.append("No quantitative pattern matched. Try 'convert 5 km to m', "
                         "'kinetic energy of 2 kg at 10 m/s', or 'lookup planck'.")
            confidence = min(confidence, 0.4)

        return PhysicsResult(
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
        return min(1.0, 0.3 + 0.12 * hits)

    def classify_domain(self, query: str) -> str:
        q = query.lower()
        if any(w in q for w in ["quantum", "schrodinger", "wavefunction", "qubit", "planck"]):
            return "quantum"
        if any(w in q for w in ["relativity", "einstein", "lorentz", "spacetime"]):
            return "relativistic"
        if any(w in q for w in ["entropy", "thermodynamic", "temperature", "heat"]):
            return "thermodynamic"
        if any(w in q for w in ["voltage", "current", "resistance", "magnetic", "electric"]):
            return "electromagnetic"
        return "classical"

    def parse_unit_conversion(self, query: str) -> dict[str, Any] | None:
        m = re.search(
            r"(-?\d+(?:\.\d+)?)\s*([a-zA-Z]+)\s+(?:to|in)\s+([a-zA-Z]+)",
            query,
        )
        if not m:
            return None
        try:
            value = float(m.group(1))
        except ValueError:
            return None
        u_from = m.group(2).lower()
        u_to = m.group(3).lower()

        for table in (_LENGTH_TO_M, _TIME_TO_S, _MASS_TO_KG):
            if u_from in table and u_to in table:
                base = value * table[u_from]
                return {
                    "value": value, "from": u_from, "to": u_to,
                    "result": base / table[u_to],
                }
        return None

    def lookup_constant(self, query: str) -> dict[str, Any] | None:
        q = query.lower()
        names = {
            "speed of light": "c", "planck": "h", "boltzmann": "k_B",
            "gravitational": "G", "gravity": "g", "electron mass": "m_e",
            "proton mass": "m_p", "avogadro": "N_A", "gas constant": "R",
        }
        for k, sym in names.items():
            if k in q:
                v, u, n = _CONSTANTS[sym]
                return {"symbol": sym, "value": v, "unit": u, "name": n}
        return None

    def kinetic_energy(self, mass_kg: float, velocity_mps: float) -> float:
        return 0.5 * mass_kg * velocity_mps ** 2

    def potential_energy_gravity(self, mass_kg: float, height_m: float, g: float = 9.80665) -> float:
        return mass_kg * g * height_m

    def momentum(self, mass_kg: float, velocity_mps: float) -> float:
        return mass_kg * velocity_mps

    def force(self, mass_kg: float, acceleration_mps2: float) -> float:
        return mass_kg * acceleration_mps2

    def relativistic_gamma(self, velocity_mps: float) -> float:
        c = _CONSTANTS["c"][0]
        if abs(velocity_mps) >= c:
            raise ValueError("v must be < c")
        return 1.0 / math.sqrt(1.0 - (velocity_mps / c) ** 2)

    def photon_energy_from_wavelength(self, wavelength_m: float) -> float:
        h = _CONSTANTS["h"][0]
        c = _CONSTANTS["c"][0]
        return h * c / wavelength_m

    def dimensional_analysis(self, query: str) -> list[str] | None:
        q = query.lower()
        if "f = ma" in q or "newton's second" in q:
            return ["[F] = kg·m/s²"]
        if "kinetic" in q:
            return ["[E] = kg·m²/s² = J"]
        if "ohm" in q or "v = ir" in q:
            return ["[V] = Ω·A = J/C"]
        return None

    def status(self) -> dict[str, Any]:
        return {
            "domain": self.DOMAIN,
            "version": self.VERSION,
            "ok": True,
            "constants": list(_CONSTANTS.keys()),
            "domains": ["classical", "relativistic", "quantum",
                        "thermodynamic", "electromagnetic"],
        }


_singleton: PhysicsExpert | None = None


def get_expert() -> PhysicsExpert:
    global _singleton
    if _singleton is None:
        _singleton = PhysicsExpert()
    return _singleton
