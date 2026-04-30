"""Anthropic Managed Agents backend.

Optional alternative LLM/runner that delegates an entire request to
Anthropic's hosted agent infrastructure (the `managed-agents-2026-04-01`
beta). Where the default backend runs the tool-use loop locally and
calls Anthropic just for token generation, this backend creates a
managed agent + environment + session and lets Anthropic run the
container, the bash tool, the file tool — and just streams the events
back to us.

Why this matters:

  - Code that the agent writes runs in **Anthropic's container**, not
    on the user's machine. Useful when the local trust mode is `off`
    (CI, Docker, shared host) but the user still wants the model to
    execute things.
  - Built-in tools (`agent_toolset_20260401`) cover bash, file ops,
    web search — no need to wire them locally.
  - Sessions are persistent on Anthropic's side; the user can reattach
    to a long-running agent via `session_id`.

Activation:

    AGENCY_BACKEND=managed_agents
    AGENCY_MANAGED_AGENT_NAME="my-jarvis"   # optional, default is the persona name
    AGENCY_MANAGED_AGENT_BETA="managed-agents-2026-04-01"

If `AGENCY_BACKEND` is unset (default), the local executor is used.

This module is **lazy-loaded** — importing `agency.managed_agents`
without setting the env var costs nothing at startup. It only
activates when the executor explicitly asks for it.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Iterator

# Anthropic SDK is required for both backends — no extra dependency.
try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None  # type: ignore

DEFAULT_BETA = "managed-agents-2026-04-01"


@dataclass
class ManagedAgentEvent:
    """A single event from a managed-agent stream, normalized to the
    same shape our local Executor emits so the rest of the runtime
    doesn't need to care which backend produced it.
    """
    kind: str  # "text" | "tool_use" | "tool_result" | "stop" | "error" | "status"
    payload: Any = None


def is_enabled() -> bool:
    """True if AGENCY_BACKEND requests the managed-agents path."""
    return (os.environ.get("AGENCY_BACKEND", "").strip().lower()
            in ("managed_agents", "managed-agents", "managed"))


def _client() -> "Anthropic":
    if Anthropic is None:
        raise RuntimeError(
            "anthropic SDK is not installed; "
            "run `pip install anthropic` to use the managed-agents backend."
        )
    return Anthropic()


@dataclass
class ManagedAgentBackend:
    """Lazily-created managed-agent backed by Anthropic's hosted infra.

    A single instance can host many sessions; we cache the agent + env
    on first use and reuse them across requests. Call `close()` to
    release the local references — Anthropic-side cleanup happens
    automatically when sessions go idle.
    """

    name: str = "agency-runtime"
    model: str = "claude-opus-4-7"
    system: str = "You are a helpful assistant."
    beta: str = DEFAULT_BETA
    networking: str = "unrestricted"

    _agent_id: str | None = field(default=None, init=False, repr=False)
    _agent_version: int | None = field(default=None, init=False, repr=False)
    _env_id: str | None = field(default=None, init=False, repr=False)
    _client_obj: Any = field(default=None, init=False, repr=False)

    # ----- lazy init ----------------------------------------------

    def _ensure_agent(self) -> str:
        if self._agent_id:
            return self._agent_id
        c = self._get_client()
        agent = c.beta.agents.create(
            name=self.name,
            model=self.model,
            system=self.system,
            tools=[{"type": "agent_toolset_20260401"}],
            extra_headers={"anthropic-beta": self.beta},
        )
        self._agent_id = agent.id
        self._agent_version = getattr(agent, "version", None)
        return self._agent_id

    def _ensure_env(self) -> str:
        if self._env_id:
            return self._env_id
        c = self._get_client()
        env = c.beta.environments.create(
            name=f"{self.name}-env",
            config={
                "type": "cloud",
                "networking": {"type": self.networking},
            },
            extra_headers={"anthropic-beta": self.beta},
        )
        self._env_id = env.id
        return self._env_id

    def _get_client(self):
        if self._client_obj is None:
            self._client_obj = _client()
        return self._client_obj

    # ----- public API ---------------------------------------------

    def run(self, user_message: str,
            session_id: str | None = None) -> Iterator[ManagedAgentEvent]:
        """Execute a single request through a managed session and yield
        normalized events as they arrive. The caller decides when to
        stop iterating; we always emit a final "stop" event before
        returning unless the SDK errors out.
        """
        c = self._get_client()
        agent_id = self._ensure_agent()
        env_id = self._ensure_env()

        # Either resume an existing session by ID or start a new one.
        if session_id:
            sess_id = session_id
        else:
            sess = c.beta.sessions.create(
                agent=agent_id,
                environment_id=env_id,
                title=self.name,
                extra_headers={"anthropic-beta": self.beta},
            )
            sess_id = sess.id
            yield ManagedAgentEvent("status", {"session_id": sess_id})

        # Open the SSE stream THEN send the user message so we don't
        # miss buffered events at the start of execution.
        try:
            stream_ctx = c.beta.sessions.events.stream(
                sess_id,
                extra_headers={"anthropic-beta": self.beta},
            )
        except AttributeError:
            # Older SDK shape: stream method may live elsewhere; fall
            # back to a raw httpx call.
            yield from self._stream_raw(sess_id, user_message)
            return

        with stream_ctx as stream:
            c.beta.sessions.events.send(
                sess_id,
                events=[{
                    "type": "user.message",
                    "content": [{"type": "text", "text": user_message}],
                }],
                extra_headers={"anthropic-beta": self.beta},
            )

            for event in stream:
                etype = getattr(event, "type", None)
                if etype == "agent.message":
                    text = "".join(getattr(b, "text", "") for b in
                                   getattr(event, "content", []))
                    yield ManagedAgentEvent("text", text)
                elif etype == "agent.tool_use":
                    yield ManagedAgentEvent("tool_use", {
                        "name": getattr(event, "name", "unknown"),
                        "input": getattr(event, "input", {}),
                    })
                elif etype == "agent.tool_result":
                    yield ManagedAgentEvent("tool_result", {
                        "name": getattr(event, "name", "unknown"),
                        "content": str(getattr(event, "content", "")),
                        "is_error": bool(getattr(event, "is_error", False)),
                    })
                elif etype == "session.status_idle":
                    yield ManagedAgentEvent("stop", "session_idle")
                    return
                elif etype and "error" in etype:
                    yield ManagedAgentEvent("error", {
                        "message": str(getattr(event, "message", event)),
                    })
                    return

        yield ManagedAgentEvent("stop", "stream_ended")

    def _stream_raw(self, sess_id: str,
                    user_message: str) -> Iterator[ManagedAgentEvent]:
        """Fallback for older SDKs that don't expose `events.stream` as
        a context manager. Uses the underlying httpx client directly
        with manual SSE parsing.
        """
        c = self._get_client()
        # Send the user message
        c.beta.sessions.events.send(
            sess_id,
            events=[{
                "type": "user.message",
                "content": [{"type": "text", "text": user_message}],
            }],
            extra_headers={"anthropic-beta": self.beta},
        )

        # Open the stream as a raw SSE
        url = f"{c.base_url}v1/sessions/{sess_id}/stream"
        with c._client.stream(
            "GET", url,
            headers={
                "x-api-key": c.api_key,
                "anthropic-version": "2023-06-01",
                "anthropic-beta": self.beta,
                "Accept": "text/event-stream",
            },
        ) as resp:
            buf = ""
            for chunk in resp.iter_text():
                buf += chunk
                while "\n\n" in buf:
                    block, buf = buf.split("\n\n", 1)
                    payload = ""
                    for line in block.splitlines():
                        if line.startswith("data:"):
                            payload += line[5:].strip()
                    if not payload:
                        continue
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    etype = data.get("type")
                    if etype == "agent.message":
                        text = "".join(b.get("text", "")
                                       for b in data.get("content", []))
                        yield ManagedAgentEvent("text", text)
                    elif etype == "agent.tool_use":
                        yield ManagedAgentEvent("tool_use", {
                            "name": data.get("name"),
                            "input": data.get("input", {}),
                        })
                    elif etype == "agent.tool_result":
                        yield ManagedAgentEvent("tool_result", {
                            "name": data.get("name"),
                            "content": str(data.get("content", "")),
                            "is_error": bool(data.get("is_error", False)),
                        })
                    elif etype == "session.status_idle":
                        yield ManagedAgentEvent("stop", "session_idle")
                        return

        yield ManagedAgentEvent("stop", "stream_ended")

    def close(self) -> None:
        """Drop local references. Anthropic-side cleanup is automatic."""
        self._agent_id = None
        self._env_id = None
        self._client_obj = None


# ----- module-level convenience -------------------------------------

_default_backend: ManagedAgentBackend | None = None


def default_backend(name: str = "agency-runtime",
                    model: str = "claude-opus-4-7",
                    system: str = "") -> ManagedAgentBackend:
    """Return the process-wide default backend, creating it on first use."""
    global _default_backend
    if _default_backend is None:
        _default_backend = ManagedAgentBackend(
            name=name, model=model, system=system or "You are a helpful assistant.",
        )
    return _default_backend
