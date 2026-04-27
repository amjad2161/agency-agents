"""Prompt optimization — DSPy-style signatures, modules, and bootstrapping.

A `PromptSignature` declares input/output fields and instructions. A
`PromptModule` compiles a signature plus few-shot examples into a
final prompt string. `BootstrapFewShot` runs an iterative search that
picks the best subset of examples by a user-provided metric.
"""

from __future__ import annotations

import hashlib
import json
import random
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from .logging import get_logger

log = get_logger()


@dataclass
class PromptSignature:
    """Declarative spec for a prompt's contract."""

    input_fields: list[str]
    output_fields: list[str]
    instructions: str = ""
    name: str = "Module"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "input_fields": list(self.input_fields),
            "output_fields": list(self.output_fields),
            "instructions": self.instructions,
        }


class PromptCache:
    """SHA256-keyed cache for compiled prompts."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._lock = threading.RLock()

    @staticmethod
    def key_for(signature: PromptSignature, examples: list[dict[str, Any]]) -> str:
        payload = {
            "sig": signature.to_dict(),
            "examples": examples,
        }
        s = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(s.encode()).hexdigest()

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._store.get(key)

    def put(self, key: str, value: str) -> None:
        with self._lock:
            self._store[key] = value

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


class PromptModule:
    """Compiled prompt with few-shot examples."""

    def __init__(
        self,
        signature: PromptSignature,
        cache: PromptCache | None = None,
    ) -> None:
        self.signature = signature
        self.examples: list[dict[str, Any]] = []
        self._compiled: str | None = None
        self.cache = cache if cache is not None else PromptCache()

    def add_example(self, example: dict[str, Any]) -> "PromptModule":
        self.examples.append(example)
        self._compiled = None
        return self

    def compile(self, examples: list[dict[str, Any]] | None = None) -> str:
        """Build the full prompt template from the signature and
        accumulated few-shot examples. Cached by hash of inputs."""
        if examples is not None:
            self.examples = list(examples)
            self._compiled = None
        key = self.cache.key_for(self.signature, self.examples)
        cached = self.cache.get(key)
        if cached is not None:
            self._compiled = cached
            return cached

        parts: list[str] = []
        parts.append(f"# {self.signature.name}")
        if self.signature.instructions:
            parts.append(self.signature.instructions.strip())
        parts.append(
            f"Inputs: {', '.join(self.signature.input_fields)}"
        )
        parts.append(
            f"Outputs: {', '.join(self.signature.output_fields)}"
        )
        if self.examples:
            parts.append("\n# Examples")
            for i, ex in enumerate(self.examples, start=1):
                block = [f"## Example {i}"]
                for f in self.signature.input_fields:
                    block.append(f"{f}: {ex.get(f, '')}")
                for f in self.signature.output_fields:
                    block.append(f"{f}: {ex.get(f, '')}")
                parts.append("\n".join(block))
        parts.append("\n# Task")
        for f in self.signature.input_fields:
            parts.append(f"{f}: {{" + f + "}}")
        compiled = "\n".join(parts)
        self.cache.put(key, compiled)
        self._compiled = compiled
        return compiled

    def __call__(self, inputs: dict[str, Any]) -> str:
        compiled = self._compiled or self.compile()
        out = compiled
        for f in self.signature.input_fields:
            out = out.replace("{" + f + "}", str(inputs.get(f, "")))
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "signature": self.signature.to_dict(),
            "examples": self.examples,
        }


class BootstrapFewShot:
    """Iterative few-shot bootstrap optimizer.

    On each iteration: sample a subset of `train_data`, compile the
    module with that subset, score all train examples via `metric_fn`,
    and keep the subset with the best score.
    """

    def __init__(self, max_demos: int = 4, seed: int | None = None) -> None:
        self.max_demos = max_demos
        self.rng = random.Random(seed)

    def optimize(
        self,
        module: PromptModule,
        train_data: list[dict[str, Any]],
        metric_fn: Callable[[PromptModule, dict[str, Any]], float],
        iterations: int = 10,
    ) -> PromptModule:
        if not train_data:
            return module
        best_score = -1.0
        best_demos = list(module.examples)
        n = len(train_data)
        k = min(self.max_demos, n)
        for it in range(iterations):
            demos = self.rng.sample(train_data, k)
            module.examples = demos
            module._compiled = None
            module.compile()
            scores = [metric_fn(module, ex) for ex in train_data]
            avg = sum(scores) / len(scores) if scores else 0.0
            log.debug("bootstrap iter=%d avg=%.3f", it, avg)
            if avg > best_score:
                best_score = avg
                best_demos = list(demos)
        module.examples = best_demos
        module._compiled = None
        module.compile()
        return module


__all__ = [
    "PromptSignature",
    "PromptCache",
    "PromptModule",
    "BootstrapFewShot",
]
