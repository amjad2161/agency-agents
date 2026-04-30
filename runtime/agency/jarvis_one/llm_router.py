"""LLM router — inspired by LiteLLM.

Multi-backend LLM gateway with a token-cost ledger. Backends are pluggable
adapters; the bundled in-memory adapter is deterministic. No new
dependencies; the LiteLLM wire protocol is mirrored only at the surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

# Cost in USD per 1K tokens; values match commonly published list prices
# at 2026-04 (input / output). Update as needed.
DEFAULT_COSTS: dict[str, dict[str, float]] = {
    "claude-sonnet-4.5": {"in": 0.003, "out": 0.015},
    "claude-opus-4.5":   {"in": 0.015, "out": 0.075},
    "gpt-5.5":           {"in": 0.005, "out": 0.025},
    "llama3-local":      {"in": 0.0,   "out": 0.0},
}


# A backend is callable(prompt, **opts) -> dict with keys: text, tokens_in, tokens_out
Backend = Callable[..., dict[str, Any]]


def _mock_backend(model: str) -> Backend:
    def _call(prompt: str, **opts: Any) -> dict[str, Any]:
        text = f"[{model}-mock] {prompt[:200]}"
        return {"text": text, "tokens_in": max(1, len(prompt) // 4),
                "tokens_out": max(1, len(text) // 4), "model": model}
    return _call


@dataclass
class CallRecord:
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    cached: bool = False


@dataclass
class LLMRouter:
    backends: dict[str, Backend] = field(default_factory=dict)
    costs: dict[str, dict[str, float]] = field(default_factory=lambda: dict(DEFAULT_COSTS))
    fallback_chain: tuple[str, ...] = ("claude-sonnet-4.5", "llama3-local")
    history: list[CallRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        for model in self.fallback_chain:
            self.backends.setdefault(model, _mock_backend(model))

    # ------------------------------------------------------------------
    def register(self, model: str, backend: Backend, *,
                 cost_in: float = 0.0, cost_out: float = 0.0) -> None:
        self.backends[model] = backend
        self.costs[model] = {"in": cost_in, "out": cost_out}

    def complete(self, prompt: str, *, models: Iterable[str] | None = None,
                 **opts: Any) -> dict[str, Any]:
        chain = tuple(models) if models else self.fallback_chain
        last_err: str | None = None
        for model in chain:
            backend = self.backends.get(model)
            if backend is None:
                last_err = f"unknown model: {model}"
                continue
            try:
                result = backend(prompt, **opts)
                cost = self._cost_for(model, result)
                self.history.append(CallRecord(
                    model=model, tokens_in=result.get("tokens_in", 0),
                    tokens_out=result.get("tokens_out", 0), cost_usd=cost,
                ))
                result.setdefault("cost_usd", cost)
                return result
            except Exception as exc:  # noqa: BLE001 — fallback chain
                last_err = f"{type(exc).__name__}: {exc}"
                continue
        return {"text": f"[router-error] {last_err}", "cost_usd": 0.0,
                "tokens_in": 0, "tokens_out": 0, "model": None}

    def total_cost(self) -> float:
        return round(sum(r.cost_usd for r in self.history), 6)

    def _cost_for(self, model: str, result: dict[str, Any]) -> float:
        rates = self.costs.get(model, {"in": 0.0, "out": 0.0})
        return round(
            (result.get("tokens_in", 0) / 1000.0) * rates["in"]
            + (result.get("tokens_out", 0) / 1000.0) * rates["out"],
            6,
        )
