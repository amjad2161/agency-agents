"""Cost-aware model router — optimize $/quality across Claude tiers.

Pairs a complexity signal with a budget-per-call to recommend the
cheapest model whose tier can plausibly handle the task. Tracks
spend per session and supports hard ceilings ("fail above $X").

Pricing data is configurable; defaults track public Anthropic prices
for the 4.x family (USD per million tokens). Update when pricing
changes — pricing is data, not logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .supreme_brainiac import Complexity, ComplexityClassifier


@dataclass(frozen=True)
class ModelTier:
    """Pricing + capability tier for a single model."""

    name: str
    input_per_mtok: float   # USD per million input tokens
    output_per_mtok: float  # USD per million output tokens
    capability_score: float  # 0..1, relative quality vs flagship

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        in_cost = (input_tokens / 1_000_000) * self.input_per_mtok
        out_cost = (output_tokens / 1_000_000) * self.output_per_mtok
        return round(in_cost + out_cost, 6)


# Default tier table — keep ordered cheapest → flagship. Pricing values are
# representative of the Claude 4.x family at GA; callers should override
# when prices change.
DEFAULT_TIERS: tuple[ModelTier, ...] = (
    ModelTier("claude-haiku-4-5", input_per_mtok=1.0, output_per_mtok=5.0, capability_score=0.78),
    ModelTier("claude-sonnet-4-6", input_per_mtok=3.0, output_per_mtok=15.0, capability_score=0.92),
    ModelTier("claude-opus-4-7", input_per_mtok=15.0, output_per_mtok=75.0, capability_score=1.0),
)


# Minimum capability score required for each complexity bucket. Anything
# below this score for the bucket is filtered out before cost-sorting.
MIN_CAPABILITY: dict[Complexity, float] = {
    Complexity.TRIVIAL: 0.0,
    Complexity.SIMPLE: 0.7,
    Complexity.MEDIUM: 0.85,
    Complexity.COMPLEX: 0.9,
    Complexity.VERY_COMPLEX: 0.99,
}


@dataclass
class RouteDecision:
    model: str
    complexity: Complexity
    estimated_cost: float
    rationale: str
    fallback_chain: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "complexity": self.complexity.value,
            "estimated_cost": self.estimated_cost,
            "rationale": self.rationale,
            "fallback_chain": list(self.fallback_chain),
        }


class CostBudgetExceeded(RuntimeError):
    """Raised when a routing decision would push spend past the cap."""


class CostAwareRouter:
    """Pick the cheapest model whose tier covers the task.

    Usage::

        router = CostAwareRouter(spend_cap_usd=1.0)
        decision = router.recommend("Write a one-paragraph summary",
                                    expected_input_tokens=400,
                                    expected_output_tokens=100)
        router.record_actual_spend(0.0006)
    """

    def __init__(
        self,
        tiers: Iterable[ModelTier] | None = None,
        classifier: ComplexityClassifier | None = None,
        spend_cap_usd: float | None = None,
    ) -> None:
        self.tiers = tuple(tiers) if tiers is not None else DEFAULT_TIERS
        self.classifier = classifier or ComplexityClassifier()
        self.spend_cap_usd = spend_cap_usd
        self._spend_so_far: float = 0.0

    # ------------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------------

    def recommend(
        self,
        text: str,
        expected_input_tokens: int = 1000,
        expected_output_tokens: int = 500,
        force_complexity: Complexity | None = None,
    ) -> RouteDecision:
        complexity = force_complexity or self.classifier.classify(text)
        threshold = MIN_CAPABILITY[complexity]
        eligible = [t for t in self.tiers if t.capability_score >= threshold]
        if not eligible:
            # No tier is capable enough: fall back to flagship.
            eligible = [max(self.tiers, key=lambda t: t.capability_score)]

        # Cheapest eligible first.
        eligible_sorted = sorted(
            eligible,
            key=lambda t: t.estimate_cost(expected_input_tokens, expected_output_tokens),
        )
        chosen = eligible_sorted[0]
        cost = chosen.estimate_cost(expected_input_tokens, expected_output_tokens)

        if self.spend_cap_usd is not None and (self._spend_so_far + cost) > self.spend_cap_usd:
            raise CostBudgetExceeded(
                f"would exceed cap: {self._spend_so_far + cost:.4f} > {self.spend_cap_usd:.4f}"
            )

        rationale = (
            f"complexity={complexity.value}; min_capability={threshold:.2f}; "
            f"chose cheapest eligible tier ({chosen.name}, est ${cost:.4f})"
        )
        return RouteDecision(
            model=chosen.name,
            complexity=complexity,
            estimated_cost=cost,
            rationale=rationale,
            fallback_chain=[t.name for t in eligible_sorted[1:]],
        )

    # ------------------------------------------------------------------
    # Spend tracking
    # ------------------------------------------------------------------

    @property
    def spend_so_far(self) -> float:
        return round(self._spend_so_far, 6)

    @property
    def remaining_budget(self) -> float | None:
        if self.spend_cap_usd is None:
            return None
        return round(max(0.0, self.spend_cap_usd - self._spend_so_far), 6)

    def record_actual_spend(self, usd: float) -> float:
        if usd < 0:
            raise ValueError("usd must be >= 0")
        self._spend_so_far += usd
        return self._spend_so_far

    def reset_spend(self) -> None:
        """Reset the running spend counter to zero."""
        self._spend_so_far = 0.0
