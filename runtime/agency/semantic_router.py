"""Semantic routing — match a query to a route by similarity.

Inspired by the `semantic-router` library. Backends:
- tfidf (default, no deps)
- sentence_transformers (optional)
- openai_embeddings (optional)

Each route carries a list of utterances. The router embeds them once
and compares each query against the centroid (mean) of each route.
"""

from __future__ import annotations

import math
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .logging import get_logger

log = get_logger()

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


@dataclass
class Route:
    """One named intent with example utterances."""

    name: str
    utterances: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def _vec_tfidf(text: str, idf: dict[str, float]) -> dict[str, float]:
    toks = _tokenize(text)
    if not toks:
        return {}
    tf = Counter(toks)
    n = len(toks)
    return {t: (c / n) * idf.get(t, 1.0) for t, c in tf.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    small, large = (a, b) if len(a) <= len(b) else (b, a)
    dot = sum(v * large.get(k, 0.0) for k, v in small.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class SemanticRouter:
    """Route a query to the closest registered Route."""

    def __init__(self, backend: str = "tfidf") -> None:
        self.backend = backend
        self.routes: list[Route] = []
        self._idf: dict[str, float] = {}
        self._route_vecs: dict[str, list[dict[str, float]]] = {}
        self._st_model = None
        self._st_route_emb: dict[str, list[list[float]]] = {}
        if backend == "sentence_transformers":
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore

                self._st_model = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception as e:  # pragma: no cover
                log.warning("sentence_transformers unavailable, falling back to tfidf: %s", e)
                self.backend = "tfidf"

    def add_route(self, route: Route) -> None:
        self.routes.append(route)
        self._rebuild_index()

    def add_routes(self, routes: list[Route]) -> None:
        self.routes.extend(routes)
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        if self.backend == "tfidf":
            self._build_tfidf()
        elif self.backend == "sentence_transformers" and self._st_model is not None:
            self._build_st()  # pragma: no cover

    def _build_tfidf(self) -> None:
        # Document frequency across all utterances
        df: Counter[str] = Counter()
        all_utts = []
        for route in self.routes:
            for utt in route.utterances:
                all_utts.append(utt)
                for term in set(_tokenize(utt)):
                    df[term] += 1
        n = max(1, len(all_utts))
        self._idf = {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in df.items()}
        self._route_vecs = {
            r.name: [_vec_tfidf(u, self._idf) for u in r.utterances] for r in self.routes
        }

    def _build_st(self) -> None:  # pragma: no cover
        for r in self.routes:
            if r.utterances:
                self._st_route_emb[r.name] = [
                    list(map(float, v)) for v in self._st_model.encode(r.utterances)
                ]

    def route(self, query: str) -> tuple[Route, float]:
        if not self.routes:
            raise RuntimeError("no routes registered")
        if self.backend == "sentence_transformers" and self._st_model is not None:
            return self._route_st(query)  # pragma: no cover
        return self._route_tfidf(query)

    def _route_tfidf(self, query: str) -> tuple[Route, float]:
        qvec = _vec_tfidf(query, self._idf)
        best: tuple[Route, float] | None = None
        for route in self.routes:
            vecs = self._route_vecs.get(route.name, [])
            if not vecs:
                continue
            score = max(_cosine(qvec, v) for v in vecs)
            if best is None or score > best[1]:
                best = (route, score)
        if best is None:
            return (self.routes[0], 0.0)
        return best

    def _route_st(self, query: str) -> tuple[Route, float]:  # pragma: no cover
        import numpy as np  # type: ignore

        qemb = np.array(self._st_model.encode([query])[0])
        qn = qemb / (np.linalg.norm(qemb) or 1.0)
        best: tuple[Route, float] | None = None
        for route in self.routes:
            embs = self._st_route_emb.get(route.name, [])
            if not embs:
                continue
            for e in embs:
                ev = np.array(e)
                en = ev / (np.linalg.norm(ev) or 1.0)
                score = float(qn @ en)
                if best is None or score > best[1]:
                    best = (route, score)
        if best is None:
            return (self.routes[0], 0.0)
        return best

    def route_name(self, query: str) -> str:
        return self.route(query)[0].name


def jarvis_routes() -> list[Route]:
    """Pre-built routes for the JARVIS persona surface."""
    return [
        Route(
            name="code",
            utterances=[
                "write a python function",
                "fix this bug in my code",
                "refactor this typescript module",
                "debug the failing test",
                "implement this feature",
                "review my pull request",
            ],
        ),
        Route(
            name="research",
            utterances=[
                "find papers about transformers",
                "research market trends",
                "look up recent developments in",
                "summarize this paper",
                "give me sources on",
            ],
        ),
        Route(
            name="creative",
            utterances=[
                "write a poem about",
                "draft a short story",
                "come up with a tagline",
                "brainstorm names for",
                "design a logo concept",
            ],
        ),
        Route(
            name="analysis",
            utterances=[
                "analyze this dataset",
                "what are the trends in",
                "interpret these results",
                "compare these options",
                "evaluate this proposal",
            ],
        ),
        Route(
            name="medical",
            utterances=[
                "what does this lab result mean",
                "symptoms of",
                "drug interactions between",
                "side effects of",
                "clinical guidelines for",
            ],
        ),
        Route(
            name="legal",
            utterances=[
                "what does this contract clause mean",
                "is this term enforceable",
                "review this agreement",
                "regulatory requirements for",
                "intellectual property concerns",
            ],
        ),
        Route(
            name="math",
            utterances=[
                "solve this equation",
                "derivative of",
                "integral of",
                "prove this theorem",
                "calculate the probability",
            ],
        ),
        Route(
            name="finance",
            utterances=[
                "valuation of this company",
                "should I buy or sell",
                "calculate npv",
                "expected return on",
                "risk-adjusted performance",
            ],
        ),
        Route(
            name="conversation",
            utterances=[
                "hi how are you",
                "let's chat about",
                "tell me a joke",
                "what's your opinion on",
                "good morning",
            ],
        ),
        Route(
            name="task_execution",
            utterances=[
                "run this command",
                "execute the script",
                "deploy to production",
                "open this file",
                "schedule this for later",
            ],
        ),
    ]


def default_router() -> SemanticRouter:
    r = SemanticRouter(backend="tfidf")
    r.add_routes(jarvis_routes())
    return r


__all__ = ["Route", "SemanticRouter", "jarvis_routes", "default_router"]
