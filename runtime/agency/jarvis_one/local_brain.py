"""Local LLM brain (Tier 5).

Wraps Ollama / vLLM style local backends with a deterministic in-process
fallback so the public surface (:meth:`LocalBrain.complete`,
:meth:`LocalBrain.react`) stays available without network access. The mock
is intentionally simple — it echoes the prompt with a structured ReAct
trace so callers can exercise the full pipeline in tests.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"


@dataclass
class LocalBrainConfig:
    backend: str = "auto"        # auto | ollama | vllm | mock
    model: str = "llama3"
    url: str = DEFAULT_OLLAMA_URL
    timeout: float = 30.0
    max_tokens: int = 512
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "LocalBrainConfig":
        return cls(
            backend=os.environ.get("JARVIS_LOCAL_BACKEND", "auto"),
            model=os.environ.get("JARVIS_LOCAL_MODEL", "llama3"),
            url=os.environ.get("JARVIS_LOCAL_URL", DEFAULT_OLLAMA_URL),
            timeout=float(os.environ.get("JARVIS_LOCAL_TIMEOUT", "30")),
            max_tokens=int(os.environ.get("JARVIS_LOCAL_MAX_TOKENS", "512")),
        )


class LocalBrain:
    """Pluggable local LLM gateway with self-healing fallback."""

    def __init__(self, config: LocalBrainConfig | None = None,
                 fetcher: Callable[[str, dict[str, Any], float], str] | None = None) -> None:
        self.config = config or LocalBrainConfig.from_env()
        self._fetch = fetcher or self._default_fetch
        self._healthy = True
        self._last_error: str | None = None

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def complete(self, prompt: str, **kwargs: Any) -> str:
        """Return a completion for *prompt*. Falls back to mock on failure."""
        backend = kwargs.pop("backend", self.config.backend)
        if backend == "mock":
            return self._mock(prompt)
        try:
            payload = {
                "model": kwargs.pop("model", self.config.model),
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": kwargs.pop("max_tokens",
                                                      self.config.max_tokens)},
            }
            text = self._fetch(self.config.url, payload, self.config.timeout)
            self._healthy = True
            return text
        except Exception as exc:  # noqa: BLE001 — graceful degradation
            self._healthy = False
            self._last_error = f"{type(exc).__name__}: {exc}"
            return self._mock(prompt)

    def react(self, observation: str, *, max_steps: int = 4) -> list[dict[str, str]]:
        """Run a tiny Observe→Reason→Act→Learn trace deterministically."""
        steps: list[dict[str, str]] = []
        thought = observation.strip()
        for i in range(max_steps):
            steps.append({
                "step": str(i + 1),
                "observe": thought,
                "reason": f"Reasoning about: {thought[:80]}",
                "act": "noop" if i < max_steps - 1 else "respond",
                "learn": "no-op" if i < max_steps - 1 else "trace-complete",
            })
            thought = f"Reflection #{i+1} on '{observation}'"
        return steps

    def health(self) -> dict[str, Any]:
        return {
            "backend": self.config.backend,
            "model": self.config.model,
            "healthy": self._healthy,
            "last_error": self._last_error,
        }

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    @staticmethod
    def _default_fetch(url: str, payload: dict[str, Any], timeout: float) -> str:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — local
                data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict):
                if "response" in data:
                    return str(data["response"])
                if "text" in data:
                    return str(data["text"])
            return json.dumps(data)
        except urllib.error.URLError as exc:
            raise RuntimeError(f"local LLM unreachable: {exc}") from exc

    @staticmethod
    def _mock(prompt: str) -> str:
        snippet = prompt.strip().splitlines()[-1] if prompt.strip() else ""
        return f"[local-mock] received {len(prompt)} chars; last line: {snippet[:160]}"
