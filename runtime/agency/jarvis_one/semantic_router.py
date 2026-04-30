"""Semantic router — inspired by aurelio-labs/semantic-router.

Routes a free-text utterance to one of several declared intents using
embedding-free overlap scoring. No LLM call required, so routing is
free at runtime. Routes are described as ``(name, sample_phrases)``.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

_TOKEN = re.compile(r"[\w\u0590-\u05FF]+", re.UNICODE)


def _vec(text: str) -> Counter[str]:
    return Counter(t.lower() for t in _TOKEN.findall(text or ""))


def _score(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    if not common:
        return 0.0
    dot = sum(a[t] * b[t] for t in common)
    import math
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb)


@dataclass
class Route:
    name: str
    samples: tuple[str, ...]
    threshold: float = 0.15
    _vecs: list[Counter[str]] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        self._vecs = [_vec(s) for s in self.samples]

    def best_match(self, utterance: str) -> float:
        v = _vec(utterance)
        return max((_score(v, sv) for sv in self._vecs), default=0.0)


@dataclass
class RouteHit:
    name: str | None
    confidence: float
    above_threshold: bool


class SemanticRouter:
    """LLM-free intent router."""

    def __init__(self, routes: Iterable[Route] = ()) -> None:
        self.routes: list[Route] = list(routes)

    def add(self, route: Route) -> None:
        self.routes.append(route)

    def route(self, utterance: str) -> RouteHit:
        if not self.routes:
            return RouteHit(name=None, confidence=0.0, above_threshold=False)
        scored = [(r, r.best_match(utterance)) for r in self.routes]
        scored.sort(key=lambda x: -x[1])
        best, score = scored[0]
        return RouteHit(
            name=best.name, confidence=round(score, 3),
            above_threshold=score >= best.threshold,
        )
