"""
OpenJarvis Bridge Adapter
==========================
Integration adapter for the OpenJarvis local-first personal AI framework.

Provides a typed Python client for OpenJarvis server endpoints including:
  - Agent lifecycle management (CRUD + messaging)
  - OpenAI-compatible chat completions
  - Memory storage / search / indexing
  - Skill catalog operations
  - Health & diagnostics probing

External Ref: https://github.com/open-jarvis/OpenJarvis
API Surface  : FastAPI server (src/openjarvis/server/)
Schema       : Pydantic models (src/openjarvis/server/models.py)

Usage:
    from openjarvis_bridge import OpenJarvisBridge, OJConfig

    cfg = OJConfig(base_url="http://localhost:8000", timeout=30.0)
    bridge = OpenJarvisBridge(cfg)

    # Chat completion
    resp = bridge.chat_completion(
        model="qwen3.5:4b",
        messages=[{"role": "user", "content": "Hello!"}],
        stream=False,
    )

    # Agent management
    agent = bridge.create_agent("orchestrator", tools=["web_search", "memory"])
    reply = bridge.send_message(agent.agent_id, "Summarize my emails")

    # Memory
    bridge.memory_store("User prefers concise answers", metadata={"topic": "preferences"})
    results = bridge.memory_search("concise answers", top_k=3)
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import (
    Any,
    AsyncIterator,
    Dict,
    Iterator,
    List,
    Literal,
    Optional,
    Union,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

try:
    import httpx
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "The 'httpx' package is required for OpenJarvisBridge. "
        "Install it with: pip install httpx>=0.27"
    ) from exc

try:
    from pydantic import BaseModel, Field, validator
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "The 'pydantic' package is required for OpenJarvisBridge. "
        "Install it with: pip install pydantic>=2"
    ) from exc

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AGENT_TYPES = frozenset(
    {
        "simple",
        "native_react",
        "orchestrator",
        "native_openhands",
        "deep_research",
        "morning_digest",
        "operative",
        "monitor_operative",
    }
)

DEFAULT_AGENT_TYPE: Literal["orchestrator"] = "orchestrator"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class OJConfig:
    """Connection configuration for an OpenJarvis server instance."""

    base_url: str = "http://localhost:8000"
    """Root URL of the OpenJarvis FastAPI server."""

    api_key: Optional[str] = None
    """Optional API key for authentication (sent as Bearer token)."""

    timeout: float = 30.0
    """Default request timeout in seconds."""

    max_retries: int = 3
    """Number of retries for idempotent requests."""

    retry_delay: float = 1.0
    """Base delay between retries (exponential backoff)."""

    headers: Dict[str, str] = field(default_factory=dict)
    """Additional static headers to send with every request."""


# ---------------------------------------------------------------------------
# Pydantic Models (mirror src/openjarvis/server/models.py & api_routes.py)
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str
    content: str = ""
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: float = 0.7
    max_tokens: int = 1024
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChoiceMessage(BaseModel):
    role: str = "assistant"
    content: Optional[str] = ""
    tool_calls: Optional[List[Dict[str, Any]]] = None


class Choice(BaseModel):
    index: int = 0
    message: ChoiceMessage
    finish_reason: str = "stop"


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Choice]
    usage: UsageInfo


class AgentCreateRequest(BaseModel):
    agent_type: str = DEFAULT_AGENT_TYPE
    tools: Optional[List[str]] = None
    agent_id: Optional[str] = None

    @validator("agent_type")
    def _valid_type(cls, v: str) -> str:  # noqa: N805
        if v not in AGENT_TYPES:
            raise ValueError(f"Unknown agent type {v!r}. Choose from: {sorted(AGENT_TYPES)}")
        return v


class AgentInfo(BaseModel):
    agent_id: str
    agent_type: str
    tools: List[str] = Field(default_factory=list)
    created_at: Optional[str] = None


class AgentMessageResponse(BaseModel):
    agent_id: str
    response: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    usage: Optional[UsageInfo] = None


class MemoryStoreRequest(BaseModel):
    content: str
    metadata: Optional[Dict[str, Any]] = None


class MemorySearchRequest(BaseModel):
    query: str
    top_k: int = 5


class MemoryEntry(BaseModel):
    id: Optional[str] = None
    content: str
    metadata: Optional[Dict[str, Any]] = None
    score: Optional[float] = None


class SkillInfo(BaseModel):
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    source: Optional[str] = None


class HealthStatus(BaseModel):
    status: str
    version: Optional[str] = None
    uptime_seconds: Optional[float] = None
    engine: Optional[str] = None
    default_model: Optional[str] = None


class DiagnosticsReport(BaseModel):
    healthy: bool
    checks: Dict[str, Union[bool, str]]
    recommendations: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class OpenJarvisError(Exception):
    """Base exception for OpenJarvis bridge errors."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class OJConnectionError(OpenJarvisError):
    """Raised when the bridge cannot reach the OpenJarvis server."""


class OJAuthenticationError(OpenJarvisError):
    """Raised on 401/403 responses."""


class OJNotFoundError(OpenJarvisError):
    """Raised on 404 responses."""


class OJValidationError(OpenJarvisError):
    """Raised on 422 responses or local validation failures."""


class OJServerError(OpenJarvisError):
    """Raised on 5xx responses."""


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------


def _raise_for_status(resp: httpx.Response) -> None:
    """Map HTTP status codes to typed exceptions."""
    if resp.status_code < 400:
        return
    body = resp.text
    msg = f"OpenJarvis API error {resp.status_code}: {resp.reason_phrase}"
    try:
        payload = resp.json()
        if "detail" in payload:
            msg = f"{msg} — {payload['detail']}"
    except Exception:
        pass
    kwargs = {"status_code": resp.status_code, "response_body": body}
    if resp.status_code == 401 or resp.status_code == 403:
        raise OJAuthenticationError(msg, **kwargs)
    if resp.status_code == 404:
        raise OJNotFoundError(msg, **kwargs)
    if resp.status_code == 422:
        raise OJValidationError(msg, **kwargs)
    if resp.status_code >= 500:
        raise OJServerError(msg, **kwargs)
    raise OpenJarvisError(msg, **kwargs)


def _unix_now() -> int:
    return int(time.time())


# ---------------------------------------------------------------------------
# Bridge Implementation
# ---------------------------------------------------------------------------


class OpenJarvisBridge:
    """Synchronous client for an OpenJarvis server.

    All public methods are blocking. For async usage, see :class:`AsyncOpenJarvisBridge`.
    """

    __slots__ = ("_cfg", "_client", "_closed")

    def __init__(self, cfg: OJConfig) -> None:
        self._cfg = cfg
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **cfg.headers,
        }
        if cfg.api_key:
            headers["Authorization"] = f"Bearer {cfg.api_key}"
        self._client = httpx.Client(
            base_url=cfg.base_url.rstrip("/"),
            headers=headers,
            timeout=cfg.timeout,
        )
        self._closed = False
        logger.info("OpenJarvisBridge initialised — %s", cfg.base_url)

    # -- Lifecycle ----------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP client and release resources."""
        if not self._closed:
            self._client.close()
            self._closed = True
            logger.debug("OpenJarvisBridge closed")

    def __enter__(self) -> "OpenJarvisBridge":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ) -> httpx.Response:
        if self._closed:
            raise RuntimeError("Bridge has been closed")
        url = f"{self._cfg.base_url.rstrip('/')}/{path.lstrip('/')}"
        last_err: Optional[Exception] = None
        for attempt in range(1, self._cfg.max_retries + 1):
            try:
                resp = self._client.request(
                    method, url, json=json, params=params, timeout=self._cfg.timeout
                )
                _raise_for_status(resp)
                return resp
            except (
                httpx.ConnectError,
                httpx.TimeoutException,
                httpx.NetworkError,
            ) as exc:
                last_err = OJConnectionError(
                    f"Connection failed (attempt {attempt}/{self._cfg.max_retries}): {exc}"
                )
                wait = self._cfg.retry_delay * (2 ** (attempt - 1))
                logger.warning("Retrying %s %s in %.1fs …", method, path, wait)
                time.sleep(wait)
            except (
                OJAuthenticationError,
                OJValidationError,
                OJNotFoundError,
            ):
                raise
            except OpenJarvisError:
                raise
        assert last_err is not None
        raise last_err

    # -- Health & Diagnostics -----------------------------------------------

    def health(self) -> HealthStatus:
        """Probe the server health endpoint."""
        try:
            resp = self._request("GET", "/health")
            data = resp.json()
        except OJNotFoundError:
            # Fallback: try root
            resp = self._request("GET", "/")
            data = {"status": "ok", **resp.json()}
        return HealthStatus(**data)

    def ready(self) -> bool:
        """Return ``True`` if the server reports healthy."""
        try:
            return self.health().status.lower() in ("ok", "healthy", "up")
        except OJConnectionError:
            return False

    def diagnostics(self) -> DiagnosticsReport:
        """Run a comprehensive diagnostic probe.

        Performs health check, model-list fetch, and a minimal chat completion
        to verify end-to-end functionality.
        """
        checks: Dict[str, Union[bool, str]] = {}
        recommendations: List[str] = []

        # 1. Connectivity
        try:
            hv = self.health()
            checks["health"] = True
            checks["version"] = hv.version or "unknown"
            checks["engine"] = hv.engine or "unknown"
            checks["default_model"] = hv.default_model or "unknown"
        except Exception as exc:
            checks["health"] = False
            checks["error"] = str(exc)
            recommendations.append(f"Server unreachable: {exc}")
            return DiagnosticsReport(healthy=False, checks=checks, recommendations=recommendations)

        # 2. Chat completion sanity check (tiny non-streaming call)
        try:
            test_resp = self.chat_completion(
                model=checks.get("default_model", "qwen3.5:4b"),  # type: ignore[arg-type]
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
                temperature=0.0,
            )
            checks["chat_completion"] = bool(test_resp.choices)
        except Exception as exc:
            checks["chat_completion"] = False
            checks["chat_error"] = str(exc)
            recommendations.append(f"Chat completion failed: {exc}")

        # 3. List agent types
        try:
            types = self.list_agent_types()
            checks["agent_types_count"] = len(types)
        except Exception as exc:
            checks["agent_types_count"] = 0
            recommendations.append(f"Agent type listing failed: {exc}")

        healthy = all(
            v is True for k, v in checks.items() if k in ("health", "chat_completion")
        )
        return DiagnosticsReport(
            healthy=healthy,
            checks=checks,
            recommendations=recommendations,
        )

    # -- OpenAI-Compatible Chat ---------------------------------------------

    def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> ChatCompletionResponse:
        """Send a chat completion request (non-streaming).

        Args:
            model: Model identifier, e.g. ``"qwen3.5:4b"`` or ``"gpt-4o"``.
            messages: List of ``{"role": "…", "content": "…"}`` dicts.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            stream: If ``True``, use :meth:`chat_completion_stream` instead.
            tools: Optional list of tool schema dicts.

        Returns:
            Parsed :class:`ChatCompletionResponse`.
        """
        if stream:
            raise ValueError(
                "For streaming, call chat_completion_stream() instead."
            )
        msgs = [ChatMessage(**m) for m in messages]
        payload = ChatCompletionRequest(
            model=model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            tools=tools,
        )
        resp = self._request("POST", "/v1/chat/completions", json=payload.dict())
        return ChatCompletionResponse(**resp.json())

    def chat_completion_stream(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Iterator[str]:
        """Send a chat completion request (streaming).

        Yields raw SSE chunks as strings.  The caller is responsible for
        parsing ``data: …`` lines.
        """
        msgs = [ChatMessage(**m) for m in messages]
        payload = ChatCompletionRequest(
            model=model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            tools=tools,
        )
        resp = self._request(
            "POST",
            "/v1/chat/completions",
            json=payload.dict(),
            stream=True,
        )
        for line in resp.iter_lines():
            if line:
                yield line

    # -- Agent Management ---------------------------------------------------

    def create_agent(
        self,
        agent_type: str = DEFAULT_AGENT_TYPE,
        *,
        tools: Optional[List[str]] = None,
        agent_id: Optional[str] = None,
    ) -> AgentInfo:
        """Create a new agent instance on the server.

        Args:
            agent_type: One of the built-in agent types.
            tools: List of tool names to bind.
            agent_id: Optional explicit UUID/slug.

        Returns:
            :class:`AgentInfo` with the server-assigned (or provided) ID.
        """
        payload = AgentCreateRequest(
            agent_type=agent_type, tools=tools, agent_id=agent_id
        )
        resp = self._request("POST", "/api/agents", json=payload.dict())
        return AgentInfo(**resp.json())

    def list_agents(self) -> List[AgentInfo]:
        """List all active agent instances."""
        resp = self._request("GET", "/api/agents")
        return [AgentInfo(**a) for a in resp.json()]

    def get_agent(self, agent_id: str) -> AgentInfo:
        """Fetch metadata for a single agent."""
        resp = self._request("GET", f"/api/agents/{agent_id}")
        return AgentInfo(**resp.json())

    def send_message(
        self,
        agent_id: str,
        message: str,
    ) -> AgentMessageResponse:
        """Send a text message to an agent and wait for its response.

        Args:
            agent_id: Target agent identifier.
            message: Plain-text user message.

        Returns:
            :class:`AgentMessageResponse` containing the agent reply.
        """
        resp = self._request(
            "POST",
            f"/api/agents/{agent_id}/message",
            json={"message": message},
        )
        return AgentMessageResponse(**resp.json())

    def delete_agent(self, agent_id: str) -> None:
        """Terminate and delete an agent instance."""
        self._request("DELETE", f"/api/agents/{agent_id}")

    def list_agent_types(self) -> List[str]:
        """Return the set of agent types supported by this server."""
        resp = self._request("GET", "/api/agents/types")
        payload = resp.json()
        if isinstance(payload, dict) and "types" in payload:
            return payload["types"]
        if isinstance(payload, list):
            return payload
        return []

    # -- Memory Operations --------------------------------------------------

    def memory_store(
        self,
        content: str,
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store a memory fragment.

        Returns:
            The memory entry ID assigned by the server.
        """
        payload = MemoryStoreRequest(content=content, metadata=metadata)
        resp = self._request("POST", "/api/memory/store", json=payload.dict())
        data = resp.json()
        return data.get("id", "")

    def memory_search(
        self,
        query: str,
        *,
        top_k: int = 5,
    ) -> List[MemoryEntry]:
        """Full-text search over stored memories.

        Args:
            query: Free-text search query.
            top_k: Maximum number of results.

        Returns:
            List of matching :class:`MemoryEntry` objects, ordered by relevance.
        """
        payload = MemorySearchRequest(query=query, top_k=top_k)
        resp = self._request("POST", "/api/memory/search", json=payload.dict())
        return [MemoryEntry(**e) for e in resp.json()]

    def memory_index(self, path: str) -> Dict[str, Any]:
        """Index documents on disk into the memory store.

        Args:
            path: Absolute or relative path to a file or directory.

        Returns:
            Server response dict (typically contains ``indexed_count`` or similar).
        """
        resp = self._request(
            "POST", "/api/memory/index", json={"path": path}
        )
        return resp.json()

    # -- Skill Operations ---------------------------------------------------

    def list_skills(self) -> List[SkillInfo]:
        """List installed skills."""
        resp = self._request("GET", "/api/skills")
        return [SkillInfo(**s) for s in resp.json()]

    def install_skill(
        self,
        source: str,
        *,
        category: Optional[str] = None,
    ) -> SkillInfo:
        """Install a skill from a public source.

        Args:
            source: Skill locator, e.g. ``"hermes:arxiv"`` or a GitHub URL.
            category: Optional category tag for organisation.

        Returns:
            Metadata for the installed skill.
        """
        payload: Dict[str, Any] = {"source": source}
        if category:
            payload["category"] = category
        resp = self._request("POST", "/api/skills/install", json=payload)
        return SkillInfo(**resp.json())

    def remove_skill(self, name: str) -> None:
        """Remove an installed skill by name."""
        self._request("POST", "/api/skills/remove", json={"name": name})

    def search_skills(self, query: str) -> List[SkillInfo]:
        """Search the skill catalog without installing."""
        resp = self._request("POST", "/api/skills/search", json={"query": query})
        return [SkillInfo(**s) for s in resp.json()]

    def sync_skills(
        self,
        source: str,
        *,
        category: Optional[str] = None,
    ) -> List[SkillInfo]:
        """Bulk-sync skills from a catalog source.

        Args:
            source: Catalog name, e.g. ``"hermes"``.
            category: Optional category filter.

        Returns:
            List of skills that were added/updated.
        """
        payload: Dict[str, Any] = {"source": source}
        if category:
            payload["category"] = category
        resp = self._request("POST", "/api/skills/sync", json=payload)
        return [SkillInfo(**s) for s in resp.json()]

    # -- Workflows ----------------------------------------------------------

    def list_workflows(self) -> List[Dict[str, Any]]:
        """List registered workflows."""
        resp = self._request("GET", "/api/workflows")
        return resp.json()

    def trigger_workflow(
        self,
        workflow_id: str,
        *,
        inputs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Trigger a workflow by ID with optional input parameters."""
        resp = self._request(
            "POST",
            f"/api/workflows/{workflow_id}/trigger",
            json=inputs or {},
        )
        return resp.json()

    # -- Feedback & Traces --------------------------------------------------

    def submit_feedback(
        self,
        trace_id: str,
        score: float,
        *,
        source: str = "api",
    ) -> None:
        """Submit a feedback score for a trace.

        Args:
            trace_id: Trace identifier returned by a previous agent run.
            score: Numeric score (typically 0.0–1.0).
            source: Feedback origin label.
        """
        self._request(
            "POST",
            "/api/traces/feedback",
            json={"trace_id": trace_id, "score": score, "source": source},
        )

    def get_trace(self, trace_id: str) -> Dict[str, Any]:
        """Retrieve a full trace by ID."""
        resp = self._request("GET", f"/api/traces/{trace_id}")
        return resp.json()


# ---------------------------------------------------------------------------
# Async Bridge
# ---------------------------------------------------------------------------


class AsyncOpenJarvisBridge:
    """Asynchronous client for an OpenJarvis server.

    Mirrors :class:`OpenJarvisBridge` but uses ``httpx.AsyncClient``.
    All public methods are ``async``.
    """

    __slots__ = ("_cfg", "_client", "_closed")

    def __init__(self, cfg: OJConfig) -> None:
        self._cfg = cfg
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **cfg.headers,
        }
        if cfg.api_key:
            headers["Authorization"] = f"Bearer {cfg.api_key}"
        self._client = httpx.AsyncClient(
            base_url=cfg.base_url.rstrip("/"),
            headers=headers,
            timeout=cfg.timeout,
        )
        self._closed = False
        logger.info("AsyncOpenJarvisBridge initialised — %s", cfg.base_url)

    async def close(self) -> None:
        if not self._closed:
            await self._client.aclose()
            self._closed = True
            logger.debug("AsyncOpenJarvisBridge closed")

    async def __aenter__(self) -> "AsyncOpenJarvisBridge":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def _arequest(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        if self._closed:
            raise RuntimeError("Bridge has been closed")
        url = f"{self._cfg.base_url.rstrip('/')}/{path.lstrip('/')}"
        last_err: Optional[Exception] = None
        for attempt in range(1, self._cfg.max_retries + 1):
            try:
                resp = await self._client.request(
                    method, url, json=json, params=params, timeout=self._cfg.timeout
                )
                _raise_for_status(resp)
                return resp
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
                last_err = OJConnectionError(
                    f"Connection failed (attempt {attempt}/{self._cfg.max_retries}): {exc}"
                )
                wait = self._cfg.retry_delay * (2 ** (attempt - 1))
                logger.warning("Retrying %s %s in %.1fs …", method, path, wait)
                await __import__("asyncio").sleep(wait)
            except (OJAuthenticationError, OJValidationError, OJNotFoundError):
                raise
            except OpenJarvisError:
                raise
        assert last_err is not None
        raise last_err

    # -- Health -------------------------------------------------------------

    async def health(self) -> HealthStatus:
        try:
            resp = await self._arequest("GET", "/health")
            data = resp.json()
        except OJNotFoundError:
            resp = await self._arequest("GET", "/")
            data = {"status": "ok", **resp.json()}
        return HealthStatus(**data)

    async def ready(self) -> bool:
        try:
            h = await self.health()
            return h.status.lower() in ("ok", "healthy", "up")
        except OJConnectionError:
            return False

    # -- Chat ---------------------------------------------------------------

    async def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> ChatCompletionResponse:
        if stream:
            raise ValueError("For streaming, use chat_completion_stream().")
        msgs = [ChatMessage(**m) for m in messages]
        payload = ChatCompletionRequest(
            model=model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            tools=tools,
        )
        resp = await self._arequest("POST", "/v1/chat/completions", json=payload.dict())
        return ChatCompletionResponse(**resp.json())

    async def chat_completion_stream(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[str]:
        msgs = [ChatMessage(**m) for m in messages]
        payload = ChatCompletionRequest(
            model=model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            tools=tools,
        )
        resp = await self._arequest(
            "POST", "/v1/chat/completions", json=payload.dict()
        )
        async for line in resp.aiter_lines():
            if line:
                yield line

    # -- Agents -------------------------------------------------------------

    async def create_agent(
        self,
        agent_type: str = DEFAULT_AGENT_TYPE,
        *,
        tools: Optional[List[str]] = None,
        agent_id: Optional[str] = None,
    ) -> AgentInfo:
        payload = AgentCreateRequest(
            agent_type=agent_type, tools=tools, agent_id=agent_id
        )
        resp = await self._arequest("POST", "/api/agents", json=payload.dict())
        return AgentInfo(**resp.json())

    async def list_agents(self) -> List[AgentInfo]:
        resp = await self._arequest("GET", "/api/agents")
        return [AgentInfo(**a) for a in resp.json()]

    async def get_agent(self, agent_id: str) -> AgentInfo:
        resp = await self._arequest("GET", f"/api/agents/{agent_id}")
        return AgentInfo(**resp.json())

    async def send_message(self, agent_id: str, message: str) -> AgentMessageResponse:
        resp = await self._arequest(
            "POST",
            f"/api/agents/{agent_id}/message",
            json={"message": message},
        )
        return AgentMessageResponse(**resp.json())

    async def delete_agent(self, agent_id: str) -> None:
        await self._arequest("DELETE", f"/api/agents/{agent_id}")

    async def list_agent_types(self) -> List[str]:
        resp = await self._arequest("GET", "/api/agents/types")
        payload = resp.json()
        if isinstance(payload, dict) and "types" in payload:
            return payload["types"]
        if isinstance(payload, list):
            return payload
        return []

    # -- Memory -------------------------------------------------------------

    async def memory_store(
        self,
        content: str,
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        payload = MemoryStoreRequest(content=content, metadata=metadata)
        resp = await self._arequest("POST", "/api/memory/store", json=payload.dict())
        return resp.json().get("id", "")

    async def memory_search(
        self,
        query: str,
        *,
        top_k: int = 5,
    ) -> List[MemoryEntry]:
        payload = MemorySearchRequest(query=query, top_k=top_k)
        resp = await self._arequest("POST", "/api/memory/search", json=payload.dict())
        return [MemoryEntry(**e) for e in resp.json()]

    async def memory_index(self, path: str) -> Dict[str, Any]:
        resp = await self._arequest("POST", "/api/memory/index", json={"path": path})
        return resp.json()

    # -- Skills -------------------------------------------------------------

    async def list_skills(self) -> List[SkillInfo]:
        resp = await self._arequest("GET", "/api/skills")
        return [SkillInfo(**s) for s in resp.json()]

    async def install_skill(
        self,
        source: str,
        *,
        category: Optional[str] = None,
    ) -> SkillInfo:
        payload: Dict[str, Any] = {"source": source}
        if category:
            payload["category"] = category
        resp = await self._arequest("POST", "/api/skills/install", json=payload)
        return SkillInfo(**resp.json())

    async def remove_skill(self, name: str) -> None:
        await self._arequest("POST", "/api/skills/remove", json={"name": name})

    async def search_skills(self, query: str) -> List[SkillInfo]:
        resp = await self._arequest("POST", "/api/skills/search", json={"query": query})
        return [SkillInfo(**s) for s in resp.json()]

    async def sync_skills(
        self,
        source: str,
        *,
        category: Optional[str] = None,
    ) -> List[SkillInfo]:
        payload: Dict[str, Any] = {"source": source}
        if category:
            payload["category"] = category
        resp = await self._arequest("POST", "/api/skills/sync", json=payload)
        return [SkillInfo(**s) for s in resp.json()]

    # -- Workflows ----------------------------------------------------------

    async def list_workflows(self) -> List[Dict[str, Any]]:
        resp = await self._arequest("GET", "/api/workflows")
        return resp.json()

    async def trigger_workflow(
        self,
        workflow_id: str,
        *,
        inputs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        resp = await self._arequest(
            "POST",
            f"/api/workflows/{workflow_id}/trigger",
            json=inputs or {},
        )
        return resp.json()

    # -- Feedback -----------------------------------------------------------

    async def submit_feedback(
        self,
        trace_id: str,
        score: float,
        *,
        source: str = "api",
    ) -> None:
        await self._arequest(
            "POST",
            "/api/traces/feedback",
            json={"trace_id": trace_id, "score": score, "source": source},
        )

    async def get_trace(self, trace_id: str) -> Dict[str, Any]:
        resp = await self._arequest("GET", f"/api/traces/{trace_id}")
        return resp.json()


# ---------------------------------------------------------------------------
# Factory Helpers
# ---------------------------------------------------------------------------


def from_env() -> OpenJarvisBridge:
    """Create a bridge from environment variables.

    Reads:
        - ``OPENJARVIS_URL``  (default: http://localhost:8000)
        - ``OPENJARVIS_API_KEY`` (optional)
        - ``OPENJARVIS_TIMEOUT`` (default: 30.0)
    """
    import os

    cfg = OJConfig(
        base_url=os.getenv("OPENJARVIS_URL", "http://localhost:8000"),
        api_key=os.getenv("OPENJARVIS_API_KEY") or None,
        timeout=float(os.getenv("OPENJARVIS_TIMEOUT", "30.0")),
    )
    return OpenJarvisBridge(cfg)


def from_env_async() -> AsyncOpenJarvisBridge:
    """Async variant of :func:`from_env`."""
    import os

    cfg = OJConfig(
        base_url=os.getenv("OPENJARVIS_URL", "http://localhost:8000"),
        api_key=os.getenv("OPENJARVIS_API_KEY") or None,
        timeout=float(os.getenv("OPENJARVIS_TIMEOUT", "30.0")),
    )
    return AsyncOpenJarvisBridge(cfg)
