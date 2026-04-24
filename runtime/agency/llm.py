"""Anthropic Claude client wrapper used by the agency runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

DEFAULT_MODEL = "claude-opus-4-7"
PLANNER_MODEL = "claude-haiku-4-5"  # cheap model for routing decisions
DEFAULT_MAX_TOKENS = 16000
DEFAULT_PLANNER_MAX_TOKENS = 1024


class LLMError(RuntimeError):
    """Raised when the LLM client is misconfigured or a call fails."""


@dataclass
class LLMConfig:
    model: str = DEFAULT_MODEL
    planner_model: str = PLANNER_MODEL
    max_tokens: int = DEFAULT_MAX_TOKENS
    api_key: str | None = None
    extra_headers: dict[str, str] = field(default_factory=dict)


class AnthropicLLM:
    """Thin wrapper around the Anthropic Python SDK.

    Imports `anthropic` lazily so `agency list` and unit tests can run without it.
    """

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError as e:
            raise LLMError(
                "The 'anthropic' package is required. Install runtime deps: "
                "pip install -e runtime"
            ) from e
        api_key = self.config.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY is not set. Export it in your shell or pass "
                "api_key= to LLMConfig."
            )
        self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def messages_create(
        self,
        *,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        thinking: dict[str, Any] | None = None,
    ) -> Any:
        """Direct call to messages.create with sensible defaults."""
        client = self._ensure_client()
        kwargs = self._build_kwargs(
            system=system, messages=messages, tools=tools,
            model=model, max_tokens=max_tokens, thinking=thinking,
        )
        return client.messages.create(**kwargs)

    def messages_stream(
        self,
        *,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        thinking: dict[str, Any] | None = None,
    ) -> Any:
        """Open a streaming response. Returns the SDK's stream context manager.

        Use as: `with llm.messages_stream(...) as stream: ...`
        Stream exposes `.text_stream`, iterable events, and `.get_final_message()`.
        """
        client = self._ensure_client()
        kwargs = self._build_kwargs(
            system=system, messages=messages, tools=tools,
            model=model, max_tokens=max_tokens, thinking=thinking,
        )
        return client.messages.stream(**kwargs)

    def _build_kwargs(self, **opts: Any) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": opts["model"] or self.config.model,
            "max_tokens": opts["max_tokens"] or self.config.max_tokens,
            "system": opts["system"],
            "messages": opts["messages"],
        }
        if opts["tools"]:
            kwargs["tools"] = opts["tools"]
        if opts["thinking"]:
            kwargs["thinking"] = opts["thinking"]
        if self.config.extra_headers:
            kwargs["extra_headers"] = self.config.extra_headers
        return kwargs

    @staticmethod
    def cached_system(text: str) -> list[dict[str, Any]]:
        """Build a system prompt list with a cache_control breakpoint at the end.

        The persona body is reused on every turn, so caching it pays for itself
        after the second request.
        """
        return [
            {
                "type": "text",
                "text": text,
                "cache_control": {"type": "ephemeral"},
            }
        ]
