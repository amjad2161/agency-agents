"""Prompt optimizer — inspired by DSPy.

Few-shot example mining + Bayesian-flavoured score-driven selection. Pure
Python; the optimizer treats the LLM as a black box scored by a metric
callable. No DSPy / Optuna dependency.
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class FewShotExample:
    input: str
    output: str
    score: float = 0.0


# Score a candidate completion (1.0 = perfect)
ScoreFn = Callable[[str, str], float]
# Generate a completion from a prompt
GenFn = Callable[[str], str]


@dataclass
class PromptCandidate:
    template: str
    examples: tuple[FewShotExample, ...]
    score: float = 0.0


@dataclass
class OptimizerResult:
    best: PromptCandidate
    history: list[PromptCandidate] = field(default_factory=list)


class PromptOptimizer:
    """Greedy few-shot selector with deterministic seed."""

    def __init__(self, score_fn: ScoreFn, gen_fn: GenFn, *, seed: int = 0) -> None:
        self.score_fn = score_fn
        self.gen_fn = gen_fn
        self.rng = random.Random(seed)

    def mine(self, examples: list[FewShotExample]) -> list[FewShotExample]:
        """Sort examples by their own self-consistency score."""
        scored: list[FewShotExample] = []
        for ex in examples:
            actual = self.gen_fn(ex.input)
            ex.score = float(self.score_fn(actual, ex.output))
            scored.append(ex)
        scored.sort(key=lambda e: -e.score)
        return scored

    def optimize(self, template: str, examples: list[FewShotExample], *,
                 k: int = 3, max_candidates: int = 12) -> OptimizerResult:
        mined = self.mine(examples)
        pool = mined[: max(k * 2, 4)]
        candidates: list[PromptCandidate] = []
        # Try the top-k subset and a few random subsets of size k.
        for combo in itertools.islice(itertools.combinations(pool, k), max_candidates):
            template_str = self._render(template, combo)
            score = self._score_template(template_str, mined[:5])
            candidates.append(PromptCandidate(
                template=template_str, examples=tuple(combo), score=score,
            ))
        if not candidates:
            best = PromptCandidate(template=template, examples=())
            return OptimizerResult(best=best, history=[])
        candidates.sort(key=lambda c: -c.score)
        return OptimizerResult(best=candidates[0], history=candidates)

    # ------------------------------------------------------------------
    @staticmethod
    def _render(template: str, examples: tuple[FewShotExample, ...]) -> str:
        body = "\n\n".join(
            f"Input: {ex.input}\nOutput: {ex.output}" for ex in examples
        )
        if "{examples}" in template:
            return template.replace("{examples}", body)
        return f"{template}\n\n{body}"

    def _score_template(self, template: str, holdout: list[FewShotExample]) -> float:
        scores: list[float] = []
        for ex in holdout:
            actual = self.gen_fn(f"{template}\n\nInput: {ex.input}\nOutput:")
            scores.append(float(self.score_fn(actual, ex.output)))
        return round(sum(scores) / max(len(scores), 1), 4)
