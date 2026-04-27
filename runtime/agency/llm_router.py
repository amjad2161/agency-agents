"""Multi-provider LLM router with fallback chain.

Inspired by LiteLLM. Tries providers in priority order, falls back on
error. All backend SDKs (openai, anthropic, litellm) are optional —
imported lazily so the module loads cleanly without them.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .logging import get_logger

log = get_logger()


@dataclass
class LLMProvider:
    """One provider in the fallback chain."""

    name: str
    model: str
    priority: int = 0
    cost_per_1k_tokens: float = 0.0
    max_tokens: int = 4096
    api_key_env: str | None = None
    backend: str = "anthropic"  # anthropic | openai | litellm | echo
    extra: dict[str, Any] = field(default_factory=dict)

    def cost_for(self, prompt_tokens: int, completion_tokens: int) -> float:
        total = prompt_tokens + completion_tokens
        return (total / 1000.0) * self.cost_per_1k_tokens


class LLMRouterError(RuntimeError):
    """All providers failed."""


class LLMRouter:
    """Routes completion calls through providers ordered by priority.

    Lower priority value = tried first. Each provider call is wrapped
    in try/except so a single backend failure (rate-limit, network,
    missing dep) falls through to the next.
    """

    def __init__(self, providers: list[LLMProvider]) -> None:
        if not providers:
            raise ValueError("LLMRouter requires at least one provider")
        self.providers: list[LLMProvider] = sorted(providers, key=lambda p: p.priority)
        self.last_provider: LLMProvider | None = None
        self.failures: dict[str, int] = {}

    def cheapest_provider(self) -> LLMProvider:
        return min(self.providers, key=lambda p: p.cost_per_1k_tokens)

    def cost_estimate(self, prompt_tokens: int, completion_tokens: int) -> float:
        p = self.cheapest_provider()
        return p.cost_for(prompt_tokens, completion_tokens)

    def complete(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        last_err: Exception | None = None
        for provider in self.providers:
            try:
                out = self._call_provider(provider, prompt, max_tokens, temperature)
                self.last_provider = provider
                return out
            except Exception as e:
                self.failures[provider.name] = self.failures.get(provider.name, 0) + 1
                last_err = e
                log.warning("provider %s failed: %s", provider.name, e)
                continue
        raise LLMRouterError(
            f"all {len(self.providers)} providers failed; last error: {last_err}"
        )

    def _call_provider(
        self,
        provider: LLMProvider,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        backend = provider.backend.lower()
        if backend == "anthropic":
            return self._call_anthropic(provider, prompt, max_tokens, temperature)
        if backend == "openai":
            return self._call_openai(provider, prompt, max_tokens, temperature)
        if backend == "litellm":
            return self._call_litellm(provider, prompt, max_tokens, temperature)
        if backend == "echo":
            return f"[echo:{provider.name}] {prompt[:200]}"
        raise ValueError(f"unknown backend: {backend}")

    def _call_anthropic(
        self, provider: LLMProvider, prompt: str, max_tokens: int, temperature: float
    ) -> str:
        try:
            import anthropic  # type: ignore
        except ImportError as e:
            raise RuntimeError(f"anthropic SDK not installed: {e}")
        api_key = os.environ.get(provider.api_key_env or "ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=provider.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        # Anthropic SDK returns a list of content blocks
        out_parts = []
        for block in resp.content:
            text = getattr(block, "text", None)
            if text:
                out_parts.append(text)
        return "".join(out_parts)

    def _call_openai(
        self, provider: LLMProvider, prompt: str, max_tokens: int, temperature: float
    ) -> str:
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as e:
            raise RuntimeError(f"openai SDK not installed: {e}")
        api_key = os.environ.get(provider.api_key_env or "OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=provider.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""

    def _call_litellm(
        self, provider: LLMProvider, prompt: str, max_tokens: int, temperature: float
    ) -> str:
        try:
            import litellm  # type: ignore
        except ImportError as e:
            raise RuntimeError(f"litellm not installed: {e}")
        resp = litellm.completion(
            model=provider.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp["choices"][0]["message"]["content"]

    def add_provider(self, provider: LLMProvider) -> None:
        self.providers.append(provider)
        self.providers.sort(key=lambda p: p.priority)

    def remove_provider(self, name: str) -> bool:
        before = len(self.providers)
        self.providers = [p for p in self.providers if p.name != name]
        return len(self.providers) < before

    def stats(self) -> dict[str, Any]:
        return {
            "providers": [p.name for p in self.providers],
            "failures": dict(self.failures),
            "last_provider": self.last_provider.name if self.last_provider else None,
        }


def default_router() -> LLMRouter:
    """Build a sane default router with echo fallback (always works)."""
    providers = [
        LLMProvider(
            name="anthropic-sonnet",
            model="claude-sonnet-4-5",
            priority=0,
            cost_per_1k_tokens=0.003,
            backend="anthropic",
        ),
        LLMProvider(
            name="echo",
            model="echo",
            priority=99,
            cost_per_1k_tokens=0.0,
            backend="echo",
        ),
    ]
    return LLMRouter(providers)


__all__ = ["LLMProvider", "LLMRouter", "LLMRouterError", "default_router"]
