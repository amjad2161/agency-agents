"""JARVIS Expert: Economics (micro, macro, game theory)."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EconomicsQuery:
    query: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class EconomicsResult:
    answer: str
    confidence: float
    domain: str
    sources: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


_KEYWORDS = (
    "demand", "supply", "elasticity", "price", "market", "equilibrium",
    "monopoly", "oligopoly", "competition", "gdp", "inflation", "unemploy",
    "interest rate", "monetary", "fiscal", "tax", "policy", "tariff",
    "trade", "currency", "exchange rate", "central bank", "fed", "ecb",
    "recession", "expansion", "growth", "consumer", "producer", "surplus",
    "deficit", "budget", "debt", "game theory", "nash", "prisoner",
    "utility", "marginal", "production", "labor", "capital", "economics",
)

_INDICATORS = {
    "gdp": "Gross Domestic Product — total value of goods and services produced",
    "cpi": "Consumer Price Index — inflation measure of consumer basket",
    "ppi": "Producer Price Index — wholesale price inflation measure",
    "u3": "U-3 unemployment — official unemployment rate",
    "u6": "U-6 unemployment — broader unemployment incl. underemployed",
    "fed funds": "Federal funds rate — overnight interbank rate",
    "yield curve": "Term structure of interest rates — inversion signals recession",
    "pmi": "Purchasing Managers Index — >50 expansion, <50 contraction",
}


class EconomicsExpert:
    """JARVIS expert for economic reasoning."""

    DOMAIN = "economics"
    VERSION = "1.0.0"

    def analyze(self, query: str, context: dict[str, Any] | None = None) -> EconomicsResult:
        confidence = self.can_handle(query)
        sources: list[str] = []
        meta: dict[str, Any] = {}
        parts: list[str] = []

        scope = self.classify_scope(query)
        meta["scope"] = scope
        parts.append(f"Economic scope: {scope}.")

        # Elasticity
        elast = self.parse_elasticity(query)
        if elast is not None:
            meta["elasticity"] = elast
            parts.append(f"Price elasticity: {elast:.3f} ({self.elasticity_classification(elast)}).")
            sources.append("microeconomics")

        # Indicator lookup
        ind = self.lookup_indicator(query)
        if ind:
            meta["indicator"] = ind
            sources.append("macro-indicators")
            parts.append(f"{ind['symbol']}: {ind['description']}.")

        # Game theory check
        gt = self.detect_game_theory(query)
        if gt:
            meta["game_theory"] = gt
            sources.append("game-theory")
            parts.append(f"Game-theory pattern: {gt}.")

        # Policy
        pol = self.policy_impact(query)
        if pol:
            meta["policy_impact"] = pol
            sources.append("policy-analysis")
            parts.append(pol)

        if len(parts) <= 1:
            parts.append("Economic query received. Provide quantities, prices, "
                         "or specific indicator/policy for deeper analysis.")
            confidence = min(confidence, 0.4)

        return EconomicsResult(
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

    def classify_scope(self, query: str) -> str:
        q = query.lower()
        macro_signals = ["gdp", "inflation", "unemployment", "monetary", "fiscal",
                          "central bank", "fed", "recession", "macro"]
        if any(s in q for s in macro_signals):
            return "macro"
        if any(s in q for s in ["nash", "game theory", "prisoner", "auction"]):
            return "game-theory"
        if any(s in q for s in ["trade", "tariff", "exchange rate", "currency"]):
            return "international"
        return "micro"

    def parse_elasticity(self, query: str) -> float | None:
        m = re.search(
            r"(?:demand|quantity)\s+(?:fell|dropped|decreased|rose|increased|grew)\s+by\s+(\d+(?:\.\d+)?)\s*%.*?"
            r"(?:price|cost)\s+(?:fell|dropped|decreased|rose|increased|grew)\s+by\s+(\d+(?:\.\d+)?)\s*%",
            query, re.IGNORECASE,
        )
        if not m:
            return None
        try:
            d_pct = float(m.group(1))
            p_pct = float(m.group(2))
            if p_pct == 0:
                return None
            return d_pct / p_pct
        except Exception:
            return None

    def elasticity_classification(self, elasticity: float) -> str:
        a = abs(elasticity)
        if a == 0:
            return "perfectly inelastic"
        if a < 1:
            return "inelastic"
        if a == 1:
            return "unit-elastic"
        if a < float("inf"):
            return "elastic"
        return "perfectly elastic"

    def lookup_indicator(self, query: str) -> dict[str, str] | None:
        q = query.lower()
        for k, desc in _INDICATORS.items():
            if k in q:
                return {"symbol": k.upper(), "description": desc}
        return None

    def detect_game_theory(self, query: str) -> str | None:
        q = query.lower()
        if "prisoner" in q and "dilemma" in q:
            return "Prisoner's Dilemma — defect-defect is Nash equilibrium, both worse off vs. cooperate-cooperate"
        if "nash" in q:
            return "Nash equilibrium — no player benefits from unilateral deviation"
        if "stag hunt" in q:
            return "Stag Hunt — coordination dilemma between safe (hare) and risky-but-better (stag)"
        if "auction" in q:
            return "Auction theory — first-price vs second-price (Vickrey) bidding strategies differ"
        return None

    def policy_impact(self, query: str) -> str | None:
        q = query.lower()
        if "interest rate" in q and "raise" in q:
            return "Higher rates: reduces aggregate demand, slows inflation, may slow growth and raise unemployment."
        if "interest rate" in q and ("cut" in q or "lower" in q):
            return "Lower rates: stimulates borrowing/investment, raises inflation risk, supports growth."
        if "tariff" in q:
            return "Tariffs: raise domestic prices, may protect local producers but reduce consumer surplus and risk retaliation."
        if "tax cut" in q:
            return "Tax cut: increases disposable income/consumption short-term; long-run impact depends on multiplier and crowding-out."
        if "stimulus" in q:
            return "Fiscal stimulus: boosts AD via spending or transfers; may widen deficit; effective in slack economy."
        return None

    def consumer_surplus(self, willingness_to_pay: float, price: float) -> float:
        return max(0.0, willingness_to_pay - price)

    def producer_surplus(self, price: float, marginal_cost: float) -> float:
        return max(0.0, price - marginal_cost)

    def gdp_growth(self, current: float, previous: float) -> float:
        if previous == 0:
            return 0.0
        return (current - previous) / previous * 100.0

    def real_interest_rate(self, nominal: float, inflation: float) -> float:
        # Fisher equation, exact form
        return (1.0 + nominal) / (1.0 + inflation) - 1.0

    def compound_interest(self, principal: float, rate: float, years: float, n: int = 1) -> float:
        return principal * (1.0 + rate / n) ** (n * years)

    def present_value(self, future_value: float, rate: float, periods: int) -> float:
        if rate == -1:
            return float("inf")
        return future_value / ((1.0 + rate) ** periods)

    def gini_coefficient(self, incomes: list[float]) -> float:
        if not incomes:
            return 0.0
        sorted_incomes = sorted(incomes)
        n = len(sorted_incomes)
        cum = 0.0
        for i, v in enumerate(sorted_incomes, start=1):
            cum += i * v
        total = sum(sorted_incomes)
        if total == 0:
            return 0.0
        return (2 * cum) / (n * total) - (n + 1) / n

    def status(self) -> dict[str, Any]:
        return {
            "domain": self.DOMAIN,
            "version": self.VERSION,
            "ok": True,
            "indicators": list(_INDICATORS.keys()),
            "scopes": ["micro", "macro", "international", "game-theory"],
        }


_singleton: EconomicsExpert | None = None


def get_expert() -> EconomicsExpert:
    global _singleton
    if _singleton is None:
        _singleton = EconomicsExpert()
    return _singleton
