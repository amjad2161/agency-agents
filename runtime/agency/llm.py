"""Anthropic Claude client wrapper used by the agency runtime."""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass, field
from typing import Any

from .logging import get_logger, timed

# ---------------------------------------------------------------------------
# Retry / backoff constants
# ---------------------------------------------------------------------------

_RETRY_RATE_LIMIT_MAX = 3       # 429 / 529 — up to 3 retries
_RETRY_SERVER_ERROR_MAX = 2     # 5xx       — up to 2 retries
_RETRY_BASE_DELAY_S = 1.0       # 1 → 2 → 4 seconds + jitter
_RETRY_JITTER_S = 0.5           # random uniform [0, 0.5] added each wait


def _backoff_delay(attempt: int) -> float:
    """Return exponential backoff delay in seconds for *attempt* (0-indexed)."""
    base = _RETRY_BASE_DELAY_S * (2 ** attempt)
    jitter = random.uniform(0, _RETRY_JITTER_S)
    return base + jitter


def _http_status(exc: Exception) -> int | None:
    """Extract HTTP status code from an anthropic API exception, or None."""
    # anthropic SDK raises APIStatusError subclasses (BadRequestError,
    # RateLimitError, OverloadedError, InternalServerError, …).
    # All of them carry a `.status_code` attribute.
    return getattr(exc, "status_code", None)


def _is_retryable_rate_limit(exc: Exception) -> bool:
    status = _http_status(exc)
    return status in (429, 529)


def _is_retryable_server_error(exc: Exception) -> bool:
    status = _http_status(exc)
    return status is not None and 500 <= status < 600 and status not in (529,)


def _is_auth_error(exc: Exception) -> bool:
    return _http_status(exc) == 401


def _call_with_retry(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Call *fn* with retry logic for rate-limit and server errors.

    Raises immediately on 401 (auth) with a Hebrew-language error message.
    Retries up to _RETRY_RATE_LIMIT_MAX times on 429/529 with exponential
    backoff, and up to _RETRY_SERVER_ERROR_MAX times on 5xx errors.
    All other exceptions propagate immediately.
    """
    log = get_logger()
    rate_limit_attempts = 0
    server_error_attempts = 0

    while True:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            if _is_auth_error(exc):
                raise LLMError(
                    "שגיאת אימות: מפתח ה-API אינו תקין או פג תוקפו. "
                    "בדוק את ANTHROPIC_API_KEY."
                ) from exc

            if _is_retryable_rate_limit(exc):
                rate_limit_attempts += 1
                if rate_limit_attempts > _RETRY_RATE_LIMIT_MAX:
                    raise
                delay = _backoff_delay(rate_limit_attempts - 1)
                log.warning(
                    "llm.retry rate_limit attempt=%d/%d delay=%.1fs status=%s",
                    rate_limit_attempts, _RETRY_RATE_LIMIT_MAX, delay,
                    _http_status(exc),
                )
                time.sleep(delay)
                continue

            if _is_retryable_server_error(exc):
                server_error_attempts += 1
                if server_error_attempts > _RETRY_SERVER_ERROR_MAX:
                    raise
                delay = _backoff_delay(server_error_attempts - 1)
                log.warning(
                    "llm.retry server_error attempt=%d/%d delay=%.1fs status=%s",
                    server_error_attempts, _RETRY_SERVER_ERROR_MAX, delay,
                    _http_status(exc),
                )
                time.sleep(delay)
                continue

            # Not retryable
            raise

DEFAULT_MODEL = "claude-opus-4-7"
PLANNER_MODEL = "claude-haiku-4-5"  # cheap model for routing decisions
DEFAULT_MAX_TOKENS = 16000
DEFAULT_PLANNER_MAX_TOKENS = 1024


class LLMError(RuntimeError):
    """Raised when the LLM client is misconfigured or a call fails."""


def _truthy_env(name: str) -> bool:
    return (os.environ.get(name, "") or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class LLMConfig:
    model: str = DEFAULT_MODEL
    planner_model: str = PLANNER_MODEL
    max_tokens: int = DEFAULT_MAX_TOKENS
    api_key: str | None = None
    extra_headers: dict[str, str] = field(default_factory=dict)
    # Optional task budget for Opus 4.7 agentic loops.
    # When set, we pass output_config.task_budget and add the beta header.
    task_budget_tokens: int | None = None  # >= 20_000 per Anthropic spec
    betas: list[str] = field(default_factory=list)
    # MCP server passthrough (beta). Each entry is a dict per Anthropic's schema.
    mcp_servers: list[dict] = field(default_factory=list)
    # Opt-in server-side tools that run on Anthropic infra. When enabled, their
    # tool declarations are appended to every request.
    enable_web_search: bool = False
    enable_code_execution: bool = False

    @classmethod
    def from_env(cls) -> "LLMConfig":
        import json, os
        cfg = cls()
        if (m := os.environ.get("AGENCY_MODEL")):
            cfg.model = m
        if (m := os.environ.get("AGENCY_PLANNER_MODEL")):
            cfg.planner_model = m
        if (mt := os.environ.get("AGENCY_MAX_TOKENS")):
            try:
                cfg.max_tokens = int(mt)
            except ValueError:
                pass
        if (tb := os.environ.get("AGENCY_TASK_BUDGET")):
            try:
                cfg.task_budget_tokens = int(tb)
            except ValueError:
                pass
        if (mcp := os.environ.get("AGENCY_MCP_SERVERS")):
            try:
                servers = json.loads(mcp)
                if isinstance(servers, list):
                    cfg.mcp_servers = servers
            except json.JSONDecodeError:
                pass
        cfg.enable_web_search = _truthy_env("AGENCY_ENABLE_WEB_SEARCH")
        cfg.enable_code_execution = _truthy_env("AGENCY_ENABLE_CODE_EXECUTION")
        return cfg


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
        kwargs, use_beta = self._build_kwargs(
            system=system, messages=messages, tools=tools,
            model=model, max_tokens=max_tokens, thinking=thinking,
        )
        target = client.beta.messages if use_beta else client.messages
        log = get_logger()
        with timed("llm.create", model=kwargs.get("model"), beta=use_beta,
                   tools=len(kwargs.get("tools") or []),
                   messages=len(kwargs.get("messages") or [])) as fields:
            response = _call_with_retry(target.create, **kwargs)
            fields["stop"] = getattr(response, "stop_reason", None)
        usage = getattr(response, "usage", None)
        if usage is not None:
            log.info(
                "llm.usage input=%s output=%s cache_w=%s cache_r=%s stop=%s",
                getattr(usage, "input_tokens", None),
                getattr(usage, "output_tokens", None),
                getattr(usage, "cache_creation_input_tokens", None),
                getattr(usage, "cache_read_input_tokens", None),
                getattr(response, "stop_reason", None),
            )
            try:
                from .stats import record_usage
                record_usage(usage)
            except Exception:  # noqa: BLE001
                pass  # stats tracking must never crash the main path
        return response

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
    