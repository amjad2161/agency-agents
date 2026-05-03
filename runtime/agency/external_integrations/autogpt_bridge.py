#!/usr/bin/env python3
"""
AutoGPT Platform Integration Bridge for JARVIS
===============================================

A production-ready async adapter for the AutoGPT Platform REST API.
Enables JARVIS to orchestrate AutoGPT agents, graphs, blocks, and executions.

Target API Version: AutoGPT Platform v0.6.57+
License: Polyform Shield License (ensure compliance)
Repository: https://github.com/Significant-Gravitas/AutoGPT

Usage:
    bridge = AutoGPTBridge(base_url="http://localhost:8000", api_key="...")
    agents = await bridge.list_agents()
    result = await bridge.execute_graph(graph_id="...", inputs={"prompt": "Hello"})
"""

from __future__ import annotations

__version__ = "1.0.0"
__author__ = "JARVIS Integration Team"

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import (
    Any,
    AsyncIterator,
    Dict,
    List,
    Optional,
    Protocol,
    Union,
)
from urllib.parse import urljoin

import httpx

logger = logging.getLogger("jarvis.autogpt_bridge")

# ---------------------------------------------------------------------------
# Constants & Configuration
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 3
RETRY_DELAY_BASE = 1.0  # seconds, exponential backoff


class AutoGPTError(Exception):
    """Base exception for AutoGPT bridge errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_body: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class AuthenticationError(AutoGPTError):
    """Raised when API authentication fails (401/403)."""


class NotFoundError(AutoGPTError):
    """Raised when a requested resource is not found (404)."""


class ValidationError(AutoGPTError):
    """Raised when request validation fails (422)."""


class ServerError(AutoGPTError):
    """Raised when AutoGPT server encounters an error (5xx)."""


# ---------------------------------------------------------------------------
# Domain Models
# ---------------------------------------------------------------------------

class GraphStatus(str, Enum):
    """Execution status of a graph/run."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class BlockType(str, Enum):
    """Common block types available in AutoGPT Platform."""

    LLM = "llm"
    HTTP_REQUEST = "http_request"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    TEXT_CONCAT = "text_concat"
    CONDITIONAL = "conditional"
    LOOP = "loop"
    AGENT = "agent"
    CUSTOM = "custom"


@dataclass
class Agent:
    """Represents an AutoGPT agent configuration."""

    id: str
    name: str
    description: str
    graph_id: Optional[str] = None
    owner_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_public: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "Agent":
        return cls(
            id=data["id"],
            name=data.get("name", "Unnamed Agent"),
            description=data.get("description", ""),
            graph_id=data.get("graphId") or data.get("graph_id"),
            owner_id=data.get("ownerId") or data.get("owner_id"),
            created_at=_parse_datetime(data.get("createdAt") or data.get("created_at")),
            updated_at=_parse_datetime(data.get("updatedAt") or data.get("updated_at")),
            is_public=data.get("isPublic", data.get("is_public", False)),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Graph:
    """Represents an AutoGPT workflow graph (DAG of blocks)."""

    id: str
    name: str
    description: str
    nodes: List[Dict[str, Any]] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)
    owner_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_public: bool = False
    version: int = 1

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "Graph":
        return cls(
            id=data["id"],
            name=data.get("name", "Unnamed Graph"),
            description=data.get("description", ""),
            nodes=data.get("nodes", []),
            edges=data.get("edges", []),
            owner_id=data.get("ownerId") or data.get("owner_id"),
            created_at=_parse_datetime(data.get("createdAt") or data.get("created_at")),
            updated_at=_parse_datetime(data.get("updatedAt") or data.get("updated_at")),
            is_public=data.get("isPublic", data.get("is_public", False)),
            version=data.get("version", 1),
        )


@dataclass
class Block:
    """Represents a reusable block/action in the AutoGPT platform."""

    id: str
    name: str
    description: str
    block_type: str
    category: str = "general"
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    config_schema: Dict[str, Any] = field(default_factory=dict)
    is_public: bool = True

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "Block":
        return cls(
            id=data["id"],
            name=data.get("name", "Unnamed Block"),
            description=data.get("description", ""),
            block_type=data.get("blockType") or data.get("block_type", BlockType.CUSTOM),
            category=data.get("category", "general"),
            input_schema=data.get("inputSchema") or data.get("input_schema", {}),
            output_schema=data.get("outputSchema") or data.get("output_schema", {}),
            config_schema=data.get("configSchema") or data.get("config_schema", {}),
            is_public=data.get("isPublic", data.get("is_public", True)),
        )


@dataclass
class GraphExecution:
    """Represents a single execution (run) of a graph."""

    id: str
    graph_id: str
    status: GraphStatus
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "GraphExecution":
        return cls(
            id=data["id"],
            graph_id=data.get("graphId") or data.get("graph_id", ""),
            status=GraphStatus(data.get("status", "PENDING")),
            inputs=data.get("inputs", {}),
            outputs=data.get("outputs", {}),
            error_message=data.get("errorMessage") or data.get("error_message"),
            started_at=_parse_datetime(data.get("startedAt") or data.get("started_at")),
            completed_at=_parse_datetime(data.get("completedAt") or data.get("completed_at")),
            duration_ms=data.get("durationMs") or data.get("duration_ms"),
        )

    @property
    def is_done(self) -> bool:
        return self.status in (GraphStatus.SUCCESS, GraphStatus.FAILED, GraphStatus.CANCELLED)

    @property
    def is_success(self) -> bool:
        return self.status == GraphStatus.SUCCESS


@dataclass
class ExecutionLog:
    """Detailed log entry for a node execution within a graph run."""

    id: str
    execution_id: str
    node_id: str
    block_name: str
    status: GraphStatus
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    logs: str = ""
    timestamp: Optional[datetime] = None
    duration_ms: Optional[int] = None

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "ExecutionLog":
        return cls(
            id=data["id"],
            execution_id=data.get("executionId") or data.get("execution_id", ""),
            node_id=data.get("nodeId") or data.get("node_id", ""),
            block_name=data.get("blockName") or data.get("block_name", "unknown"),
            status=GraphStatus(data.get("status", "PENDING")),
            input_data=data.get("inputData") or data.get("input_data", {}),
            output_data=data.get("outputData") or data.get("output_data", {}),
            logs=data.get("logs", ""),
            timestamp=_parse_datetime(data.get("timestamp")),
            duration_ms=data.get("durationMs") or data.get("duration_ms"),
        )


@dataclass
class PageResult:
    """Paginated API response wrapper."""

    items: List[Any]
    total: int
    page: int
    page_size: int
    has_more: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO datetime string to datetime object."""
    if not value:
        return None
    try:
        # Handle both 'Z' suffix and '+00:00'
        value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _raise_for_status(response: httpx.Response) -> None:
    """Map HTTP status codes to typed exceptions."""
    if response.status_code < 400:
        return
    body = response.text
    if response.status_code in (401, 403):
        raise AuthenticationError(f"Authentication failed: {body}", response.status_code, body)
    if response.status_code == 404:
        raise NotFoundError(f"Resource not found: {body}", response.status_code, body)
    if response.status_code == 422:
        raise ValidationError(f"Validation error: {body}", response.status_code, body)
    if response.status_code >= 500:
        raise ServerError(f"AutoGPT server error: {body}", response.status_code, body)
    raise AutoGPTError(f"HTTP {response.status_code}: {body}", response.status_code, body)


# ---------------------------------------------------------------------------
# Core Bridge
# ---------------------------------------------------------------------------

class AutoGPTBridge:
    """Async bridge to the AutoGPT Platform REST API.

    This class provides typed, retry-aware access to all major AutoGPT
    Platform endpoints: agents, graphs, blocks, executions, and marketplace.

    Example:
        async with AutoGPTBridge("http://localhost:8000", api_key="sk-...") as bridge:
            # List available agents
            agents = await bridge.list_agents()

            # Execute a graph with inputs
            execution = await bridge.execute_graph(
                graph_id="graph-uuid",
                inputs={"user_prompt": "Summarize the latest news"},
            )

            # Poll until complete
            execution = await bridge.wait_for_execution(execution.id)
            print(execution.outputs)
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        retry_delay: float = RETRY_DELAY_BASE,
    ):
        """Initialize the bridge.

        Args:
            base_url: The AutoGPT Platform backend URL (e.g., http://localhost:8000).
            api_key: API key or Bearer token. Falls back to AUTOGPT_API_KEY env var.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retries on transient failures.
            retry_delay: Base delay between retries (exponential backoff).
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("AUTOGPT_API_KEY", "")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"jarvis-autogpt-bridge/{__version__}",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=httpx.Timeout(timeout),
        )

    # -- Lifecycle ----------------------------------------------------------

    async def __aenter__(self) -> "AutoGPTBridge":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
        logger.debug("AutoGPTBridge client closed.")

    async def health_check(self) -> Dict[str, Any]:
        """Check if the AutoGPT Platform backend is reachable.

        Returns:
            JSON response from the health endpoint.
        """
        response = await self._client.get("/health")
        return response.json() if response.status_code == 200 else {"status": "unhealthy"}

    # -- Internal request helper --------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        retryable: bool = True,
    ) -> Any:
        """Execute an HTTP request with retries and error handling.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: API path (appended to base_url).
            params: Query parameters.
            json_data: JSON request body.
            retryable: If True, retry on transient errors (5xx, timeouts).

        Returns:
            Parsed JSON response.

        Raises:
            AutoGPTError and subclasses on failure.
        """
        last_error: Optional[Exception] = None
        attempt = 0

        while attempt <= self.max_retries:
            try:
                response = await self._client.request(
                    method=method,
                    url=path,
                    params=params,
                    json=json_data,
                )
                _raise_for_status(response)
                if response.status_code == 204:
                    return None
                return response.json()
            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
                last_error = exc
                if retryable and attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)
                    logger.warning("Request %s %s failed (%s), retrying in %.1fs...", method, path, exc, delay)
                    await asyncio.sleep(delay)
                else:
                    raise AutoGPTError(f"Network error after {attempt + 1} attempts: {exc}") from exc
            except AutoGPTError:
                raise  # Don't retry on 4xx errors
            except Exception as exc:
                raise AutoGPTError(f"Unexpected error: {exc}") from exc
            finally:
                attempt += 1

        raise AutoGPTError(f"Max retries exceeded. Last error: {last_error}")

    # =====================================================================
    # AGENTS
    # =====================================================================

    async def list_agents(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        owned_only: bool = False,
    ) -> PageResult:
        """List agents accessible to the current user.

        Args:
            page: Page number (1-indexed).
            page_size: Items per page.
            search: Optional search string for name/description.
            owned_only: If True, return only agents owned by the user.

        Returns:
            Paginated list of Agent objects.
        """
        params: Dict[str, Any] = {"page": page, "pageSize": page_size}
        if search:
            params["search"] = search
        if owned_only:
            params["ownedOnly"] = "true"

        data = await self._request("GET", "/api/agents", params=params)
        items = [Agent.from_api(item) for item in data.get("items", data if isinstance(data, list) else [])]
        total = data.get("total", len(items))
        return PageResult(items=items, total=total, page=page, page_size=page_size, has_more=total > page * page_size)

    async def get_agent(self, agent_id: str) -> Agent:
        """Get a single agent by ID.

        Args:
            agent_id: UUID of the agent.

        Returns:
            Agent object.

        Raises:
            NotFoundError: If agent doesn't exist.
        """
        data = await self._request("GET", f"/api/agents/{agent_id}")
        return Agent.from_api(data)

    async def create_agent(
        self,
        name: str,
        description: str = "",
        graph_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        is_public: bool = False,
    ) -> Agent:
        """Create a new agent.

        Args:
            name: Human-readable agent name.
            description: What the agent does.
            graph_id: Associated workflow graph ID (optional).
            metadata: Arbitrary key-value metadata.
            is_public: Whether the agent is publicly discoverable.

        Returns:
            The newly created Agent.
        """
        payload = {
            "name": name,
            "description": description,
            "isPublic": is_public,
        }
        if graph_id:
            payload["graphId"] = graph_id
        if metadata:
            payload["metadata"] = metadata

        data = await self._request("POST", "/api/agents", json_data=payload)
        return Agent.from_api(data)

    async def update_agent(
        self,
        agent_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        graph_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        is_public: Optional[bool] = None,
    ) -> Agent:
        """Update an existing agent.

        Only provided fields are updated; others remain unchanged.

        Returns:
            Updated Agent object.
        """
        payload: Dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if graph_id is not None:
            payload["graphId"] = graph_id
        if metadata is not None:
            payload["metadata"] = metadata
        if is_public is not None:
            payload["isPublic"] = is_public

        data = await self._request("PUT", f"/api/agents/{agent_id}", json_data=payload)
        return Agent.from_api(data)

    async def delete_agent(self, agent_id: str) -> None:
        """Delete an agent.

        Args:
            agent_id: UUID of the agent to delete.
        """
        await self._request("DELETE", f"/api/agents/{agent_id}")
        logger.info("Deleted agent %s", agent_id)

    async def execute_agent(
        self,
        agent_id: str,
        inputs: Dict[str, Any],
        *,
        wait: bool = False,
        timeout: Optional[float] = None,
    ) -> GraphExecution:
        """Trigger an agent execution.

        Args:
            agent_id: The agent to run.
            inputs: Key-value inputs required by the agent's graph.
            wait: If True, block until execution completes.
            timeout: Max seconds to wait (only used if wait=True).

        Returns:
            GraphExecution object representing the run.
        """
        payload = {"inputs": inputs}
        data = await self._request("POST", f"/api/agents/{agent_id}/execute", json_data=payload)
        execution = GraphExecution.from_api(data)

        if wait:
            execution = await self.wait_for_execution(execution.id, timeout=timeout)
        return execution

    # =====================================================================
    # GRAPHS (Workflows)
    # =====================================================================

    async def list_graphs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
    ) -> PageResult:
        """List workflow graphs.

        Returns:
            Paginated list of Graph objects.
        """
        params: Dict[str, Any] = {"page": page, "pageSize": page_size}
        if search:
            params["search"] = search

        data = await self._request("GET", "/api/graphs", params=params)
        items = [Graph.from_api(item) for item in data.get("items", data if isinstance(data, list) else [])]
        total = data.get("total", len(items))
        return PageResult(items=items, total=total, page=page, page_size=page_size, has_more=total > page * page_size)

    async def get_graph(self, graph_id: str) -> Graph:
        """Get a graph by ID.

        Args:
            graph_id: UUID of the graph.

        Returns:
            Graph object including nodes and edges.
        """
        data = await self._request("GET", f"/api/graphs/{graph_id}")
        return Graph.from_api(data)

    async def create_graph(
        self,
        name: str,
        description: str = "",
        nodes: Optional[List[Dict[str, Any]]] = None,
        edges: Optional[List[Dict[str, Any]]] = None,
        is_public: bool = False,
    ) -> Graph:
        """Create a new workflow graph.

        Args:
            name: Graph name.
            description: What the workflow does.
            nodes: List of block nodes (each with id, blockId, config, coords).
            edges: List of connections (source -> target with port mappings).
            is_public: Whether the graph is publicly discoverable.

        Returns:
            The newly created Graph.
        """
        payload: Dict[str, Any] = {
            "name": name,
            "description": description,
            "isPublic": is_public,
            "nodes": nodes or [],
            "edges": edges or [],
        }
        data = await self._request("POST", "/api/graphs", json_data=payload)
        return Graph.from_api(data)

    async def update_graph(
        self,
        graph_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        nodes: Optional[List[Dict[str, Any]]] = None,
        edges: Optional[List[Dict[str, Any]]] = None,
        is_public: Optional[bool] = None,
    ) -> Graph:
        """Update an existing graph.

        Returns:
            Updated Graph object.
        """
        payload: Dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if nodes is not None:
            payload["nodes"] = nodes
        if edges is not None:
            payload["edges"] = edges
        if is_public is not None:
            payload["isPublic"] = is_public

        data = await self._request("PUT", f"/api/graphs/{graph_id}", json_data=payload)
        return Graph.from_api(data)

    async def delete_graph(self, graph_id: str) -> None:
        """Delete a graph.

        Args:
            graph_id: UUID of the graph to delete.
        """
        await self._request("DELETE", f"/api/graphs/{graph_id}")
        logger.info("Deleted graph %s", graph_id)

    async def execute_graph(
        self,
        graph_id: str,
        inputs: Dict[str, Any],
        *,
        wait: bool = False,
        timeout: Optional[float] = None,
    ) -> GraphExecution:
        """Execute a graph directly with the given inputs.

        Args:
            graph_id: The workflow graph to run.
            inputs: Key-value inputs matching the graph's input schema.
            wait: If True, block until execution completes.
            timeout: Max seconds to wait (only used if wait=True).

        Returns:
            GraphExecution object.
        """
        payload = {"inputs": inputs}
        data = await self._request("POST", f"/api/graphs/{graph_id}/execute", json_data=payload)
        execution = GraphExecution.from_api(data)

        if wait:
            execution = await self.wait_for_execution(execution.id, timeout=timeout)
        return execution

    # =====================================================================
    # BLOCKS
    # =====================================================================

    async def list_blocks(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        category: Optional[str] = None,
        search: Optional[str] = None,
    ) -> PageResult:
        """List available blocks in the platform.

        Args:
            page: Page number.
            page_size: Items per page.
            category: Filter by block category.
            search: Search by name/description.

        Returns:
            Paginated list of Block objects.
        """
        params: Dict[str, Any] = {"page": page, "pageSize": page_size}
        if category:
            params["category"] = category
        if search:
            params["search"] = search

        data = await self._request("GET", "/api/blocks", params=params)
        items = [Block.from_api(item) for item in data.get("items", data if isinstance(data, list) else [])]
        total = data.get("total", len(items))
        return PageResult(items=items, total=total, page=page, page_size=page_size, has_more=total > page * page_size)

    async def get_block(self, block_id: str) -> Block:
        """Get a single block definition by ID.

        Returns:
            Block object with full schema definitions.
        """
        data = await self._request("GET", f"/api/blocks/{block_id}")
        return Block.from_api(data)

    # =====================================================================
    # EXECUTIONS
    # =====================================================================

    async def list_executions(
        self,
        *,
        graph_id: Optional[str] = None,
        status: Optional[GraphStatus] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PageResult:
        """List graph executions.

        Args:
            graph_id: Filter by graph ID.
            status: Filter by execution status.
            page: Page number.
            page_size: Items per page.

        Returns:
            Paginated list of GraphExecution objects.
        """
        params: Dict[str, Any] = {"page": page, "pageSize": page_size}
        if graph_id:
            params["graphId"] = graph_id
        if status:
            params["status"] = status.value

        data = await self._request("GET", "/api/executions", params=params)
        items = [GraphExecution.from_api(item) for item in data.get("items", data if isinstance(data, list) else [])]
        total = data.get("total", len(items))
        return PageResult(items=items, total=total, page=page, page_size=page_size, has_more=total > page * page_size)

    async def get_execution(self, execution_id: str) -> GraphExecution:
        """Get execution status and results by ID.

        Args:
            execution_id: UUID of the execution.

        Returns:
            GraphExecution with current status and outputs.
        """
        data = await self._request("GET", f"/api/executions/{execution_id}")
        return GraphExecution.from_api(data)

    async def get_execution_logs(self, execution_id: str) -> List[ExecutionLog]:
        """Get detailed per-node execution logs.

        Args:
            execution_id: UUID of the execution.

        Returns:
            List of ExecutionLog entries ordered by timestamp.
        """
        data = await self._request("GET", f"/api/executions/{execution_id}/logs")
        items = data.get("items", data if isinstance(data, list) else [])
        return [ExecutionLog.from_api(item) for item in items]

    async def cancel_execution(self, execution_id: str) -> GraphExecution:
        """Cancel a running execution.

        Args:
            execution_id: UUID of the execution to cancel.

        Returns:
            Updated GraphExecution with CANCELLED status.
        """
        data = await self._request("POST", f"/api/executions/{execution_id}/cancel")
        return GraphExecution.from_api(data)

    async def wait_for_execution(
        self,
        execution_id: str,
        *,
        poll_interval: float = 2.0,
        timeout: Optional[float] = None,
    ) -> GraphExecution:
        """Poll an execution until it completes or times out.

        Args:
            execution_id: UUID of the execution to monitor.
            poll_interval: Seconds between status checks.
            timeout: Maximum seconds to wait (None = no limit).

        Returns:
            Final GraphExecution object.

        Raises:
            TimeoutError: If timeout is reached before completion.
            AutoGPTError: If the execution fails.
        """
        start = time.monotonic()
        while True:
            execution = await self.get_execution(execution_id)
            if execution.is_done:
                if execution.status == GraphStatus.FAILED:
                    raise AutoGPTError(
                        f"Execution {execution_id} failed: {execution.error_message}",
                    )
                return execution
            if timeout and (time.monotonic() - start) > timeout:
                raise TimeoutError(f"Execution {execution_id} did not complete within {timeout}s")
            await asyncio.sleep(poll_interval)

    async def stream_execution(
        self,
        execution_id: str,
        *,
        poll_interval: float = 1.0,
    ) -> AsyncIterator[GraphExecution]:
        """Async generator that yields execution status updates until completion.

        Yields:
            GraphExecution on each status change or poll interval.

        Example:
            async for update in bridge.stream_execution(exec_id):
                print(update.status, update.outputs)
        """
        last_status: Optional[GraphStatus] = None
        while True:
            execution = await self.get_execution(execution_id)
            if execution.status != last_status:
                last_status = execution.status
                yield execution
            if execution.is_done:
                break
            await asyncio.sleep(poll_interval)

    # =====================================================================
    # MARKETPLACE
    # =====================================================================

    async def list_marketplace_agents(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        category: Optional[str] = None,
        search: Optional[str] = None,
    ) -> PageResult:
        """Browse the public agent marketplace.

        Args:
            page: Page number.
            page_size: Items per page.
            category: Filter by category.
            search: Search query.

        Returns:
            Paginated list of public Agent objects.
        """
        params: Dict[str, Any] = {"page": page, "pageSize": page_size}
        if category:
            params["category"] = category
        if search:
            params["search"] = search

        data = await self._request("GET", "/api/marketplace/agents", params=params)
        items = [Agent.from_api(item) for item in data.get("items", data if isinstance(data, list) else [])]
        total = data.get("total", len(items))
        return PageResult(items=items, total=total, page=page, page_size=page_size, has_more=total > page * page_size)

    async def install_marketplace_agent(self, agent_id: str) -> Agent:
        """Install a public marketplace agent into the user's workspace.

        Args:
            agent_id: UUID of the public agent.

        Returns:
            The newly installed Agent (private copy).
        """
        data = await self._request("POST", f"/api/marketplace/agents/{agent_id}/install")
        return Agent.from_api(data)

    # =====================================================================
    # COPILOT / CHAT
    # =====================================================================

    async def send_copilot_message(
        self,
        message: str,
        *,
        conversation_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send a message to the AutoGPT Copilot (AI assistant).

        Args:
            message: User message text.
            conversation_id: Optional conversation thread ID.
            context: Additional context (e.g., current graph ID).

        Returns:
            Copilot response with message and any actions.
        """
        payload: Dict[str, Any] = {"message": message}
        if conversation_id:
            payload["conversationId"] = conversation_id
        if context:
            payload["context"] = context

        return await self._request("POST", "/api/copilot/chat", json_data=payload)

    # =====================================================================
    # UTILITY / HELPERS
    # =====================================================================

    def build_graph_payload(
        self,
        name: str,
        blocks_config: List[Dict[str, Any]],
        connections: List[Dict[str, Any]],
        description: str = "",
    ) -> Dict[str, Any]:
        """Helper to construct a valid graph payload from simplified config.

        Args:
            name: Graph name.
            blocks_config: List of node configs, each with:
                - id: unique node id
                - block_id: registered block type ID
                - config: block-specific configuration
                - x, y: optional canvas coordinates
            connections: List of edge configs, each with:
                - source: source node id
                - target: target node id
                - source_port: output port name
                - target_port: input port name
            description: Graph description.

        Returns:
            Dict ready for create_graph() or update_graph().
        """
        nodes = []
        for cfg in blocks_config:
            node = {
                "id": cfg["id"],
                "blockId": cfg["block_id"],
                "config": cfg.get("config", {}),
            }
            if "x" in cfg and "y" in cfg:
                node["coords"] = {"x": cfg["x"], "y": cfg["y"]}
            nodes.append(node)

        edges = []
        for conn in connections:
            edges.append({
                "source": conn["source"],
                "target": conn["target"],
                "sourcePort": conn.get("source_port", "output"),
                "targetPort": conn.get("target_port", "input"),
            })

        return {
            "name": name,
            "description": description,
            "nodes": nodes,
            "edges": edges,
        }


# ---------------------------------------------------------------------------
# JARVIS-Specific Integration Layer
# ---------------------------------------------------------------------------

class JARVISAutoGPTIntegration:
    """Higher-level integration layer that connects AutoGPT capabilities
    to JARVIS's agent orchestration and task management systems.

    This class provides simplified workflows for common JARVIS use cases
    and handles mapping between JARVIS task formats and AutoGPT graphs.
    """

    def __init__(self, bridge: AutoGPTBridge):
        self.bridge = bridge

    async def run_task_graph(
        self,
        task_description: str,
        inputs: Dict[str, Any],
        *,
        graph_name: Optional[str] = None,
        timeout: float = 120.0,
    ) -> Dict[str, Any]:
        """Execute a task using an AutoGPT graph, with automatic graph selection
        or creation.

        This is the primary high-level method JARVIS should use to delegate
        complex multi-step tasks to AutoGPT.

        Args:
            task_description: Natural language description of the task.
            inputs: Key-value inputs for the graph.
            graph_name: Optional specific graph to use; auto-selected if None.
            timeout: Max seconds to wait for completion.

        Returns:
            Dict with 'success', 'outputs', 'execution_id', and 'logs'.
        """
        # If graph_name provided, find it; otherwise the caller should
        # have already created/selected a graph.
        graph_id = graph_name  # Assume it's an ID for now
        if graph_id is None:
            # Could integrate with JARVIS's graph registry here
            raise ValueError("graph_name (graph ID) is required for auto-execution")

        try:
            execution = await self.bridge.execute_graph(
                graph_id=graph_id,
                inputs=inputs,
                wait=True,
                timeout=timeout,
            )
            logs = []
            try:
                log_entries = await self.bridge.get_execution_logs(execution.id)
                logs = [log.logs for log in log_entries]
            except AutoGPTError:
                pass  # Logs may not be available for all executions

            return {
                "success": execution.is_success,
                "outputs": execution.outputs,
                "execution_id": execution.id,
                "status": execution.status.value,
                "duration_ms": execution.duration_ms,
                "logs": logs,
            }
        except AutoGPTError as exc:
            logger.error("AutoGPT task execution failed: %s", exc)
            return {
                "success": False,
                "outputs": {},
                "execution_id": None,
                "status": "ERROR",
                "error": str(exc),
                "logs": [],
            }

    async def discover_and_install_agent(self, query: str) -> Optional[Agent]:
        """Search the marketplace for an agent matching the query and install it.

        Args:
            query: Search string (e.g., "reddit video generator").

        Returns:
            The installed Agent, or None if no match found.
        """
        results = await self.bridge.list_marketplace_agents(search=query, page_size=5)
        if not results.items:
            return None

        # Install the top result
        agent = results.items[0]
        installed = await self.bridge.install_marketplace_agent(agent.id)
        logger.info("Installed marketplace agent '%s' (%s)", installed.name, installed.id)
        return installed

    async def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive status of the connected AutoGPT Platform.

        Returns:
            Dict with health, version, agent count, graph count, etc.
        """
        health = await self.bridge.health_check()
        try:
            agents = await self.bridge.list_agents(page_size=1)
            agent_count = agents.total
        except AutoGPTError:
            agent_count = -1
        try:
            graphs = await self.bridge.list_graphs(page_size=1)
            graph_count = graphs.total
        except AutoGPTError:
            graph_count = -1

        return {
            "healthy": health.get("status") == "healthy",
            "health_details": health,
            "agent_count": agent_count,
            "graph_count": graph_count,
            "bridge_version": __version__,
        }


# ---------------------------------------------------------------------------
# Factory / Configuration
# ---------------------------------------------------------------------------

def create_bridge_from_env() -> AutoGPTBridge:
    """Create an AutoGPTBridge configured from environment variables.

    Required:
        AUTOGPT_BASE_URL: URL of the AutoGPT Platform backend.

    Optional:
        AUTOGPT_API_KEY: API key for authentication.
        AUTOGPT_TIMEOUT: Request timeout in seconds (default: 30).
        AUTOGPT_MAX_RETRIES: Max retry attempts (default: 3).

    Returns:
        Configured AutoGPTBridge instance.

    Raises:
        ValueError: If AUTOGPT_BASE_URL is not set.
    """
    base_url = os.environ.get("AUTOGPT_BASE_URL")
    if not base_url:
        raise ValueError("AUTOGPT_BASE_URL environment variable is required")

    return AutoGPTBridge(
        base_url=base_url,
        api_key=os.environ.get("AUTOGPT_API_KEY"),
        timeout=float(os.environ.get("AUTOGPT_TIMEOUT", DEFAULT_TIMEOUT)),
        max_retries=int(os.environ.get("AUTOGPT_MAX_RETRIES", MAX_RETRIES)),
    )


# ---------------------------------------------------------------------------
# Sync Wrapper (for use in non-async contexts)
# ---------------------------------------------------------------------------

class SyncAutoGPTBridge:
    """Synchronous wrapper around AutoGPTBridge for contexts where
    async/await cannot be used directly.

    Example:
        bridge = SyncAutoGPTBridge("http://localhost:8000", api_key="...")
        agents = bridge.list_agents()
        bridge.close()
    """

    def __init__(self, *args, **kwargs):
        self._bridge = AutoGPTBridge(*args, **kwargs)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _run(self, coro):
        try:
            return asyncio.run(coro)
        except RuntimeError:
            # Already in an event loop
            import nest_asyncio
            nest_asyncio.apply()
            return asyncio.get_event_loop().run_until_complete(coro)

    def health_check(self) -> Dict[str, Any]:
        return self._run(self._bridge.health_check())

    def list_agents(self, **kwargs) -> PageResult:
        return self._run(self._bridge.list_agents(**kwargs))

    def get_agent(self, agent_id: str) -> Agent:
        return self._run(self._bridge.get_agent(agent_id))

    def create_agent(self, **kwargs) -> Agent:
        return self._run(self._bridge.create_agent(**kwargs))

    def update_agent(self, agent_id: str, **kwargs) -> Agent:
        return self._run(self._bridge.update_agent(agent_id, **kwargs))

    def delete_agent(self, agent_id: str) -> None:
        return self._run(self._bridge.delete_agent(agent_id))

    def execute_agent(self, agent_id: str, inputs: Dict[str, Any], **kwargs) -> GraphExecution:
        return self._run(self._bridge.execute_agent(agent_id, inputs, **kwargs))

    def list_graphs(self, **kwargs) -> PageResult:
        return self._run(self._bridge.list_graphs(**kwargs))

    def get_graph(self, graph_id: str) -> Graph:
        return self._run(self._bridge.get_graph(graph_id))

    def create_graph(self, **kwargs) -> Graph:
        return self._run(self._bridge.create_graph(**kwargs))

    def update_graph(self, graph_id: str, **kwargs) -> Graph:
        return self._run(self._bridge.update_graph(graph_id, **kwargs))

    def delete_graph(self, graph_id: str) -> None:
        return self._run(self._bridge.delete_graph(graph_id))

    def execute_graph(self, graph_id: str, inputs: Dict[str, Any], **kwargs) -> GraphExecution:
        return self._run(self._bridge.execute_graph(graph_id, inputs, **kwargs))

    def list_blocks(self, **kwargs) -> PageResult:
        return self._run(self._bridge.list_blocks(**kwargs))

    def get_block(self, block_id: str) -> Block:
        return self._run(self._bridge.get_block(block_id))

    def list_executions(self, **kwargs) -> PageResult:
        return self._run(self._bridge.list_executions(**kwargs))

    def get_execution(self, execution_id: str) -> GraphExecution:
        return self._run(self._bridge.get_execution(execution_id))

    def get_execution_logs(self, execution_id: str) -> List[ExecutionLog]:
        return self._run(self._bridge.get_execution_logs(execution_id))

    def cancel_execution(self, execution_id: str) -> GraphExecution:
        return self._run(self._bridge.cancel_execution(execution_id))

    def wait_for_execution(self, execution_id: str, **kwargs) -> GraphExecution:
        return self._run(self._bridge.wait_for_execution(execution_id, **kwargs))

    def list_marketplace_agents(self, **kwargs) -> PageResult:
        return self._run(self._bridge.list_marketplace_agents(**kwargs))

    def install_marketplace_agent(self, agent_id: str) -> Agent:
        return self._run(self._bridge.install_marketplace_agent(agent_id))

    def send_copilot_message(self, message: str, **kwargs) -> Dict[str, Any]:
        return self._run(self._bridge.send_copilot_message(message, **kwargs))

    def close(self) -> None:
        return self._run(self._bridge.close())

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ---------------------------------------------------------------------------
# CLI / Smoke Test
# ---------------------------------------------------------------------------

async def _smoke_test():
    """Quick connectivity and functionality test."""
    import os
    logging.basicConfig(level=logging.DEBUG)

    base_url = os.environ.get("AUTOGPT_BASE_URL", "http://localhost:8000")
    api_key = os.environ.get("AUTOGPT_API_KEY", "")

    print(f"=== AutoGPT Bridge Smoke Test ===")
    print(f"Target: {base_url}")

    async with AutoGPTBridge(base_url, api_key=api_key) as bridge:
        # Health check
        health = await bridge.health_check()
        print(f"Health: {health}")

        # List agents
        try:
            agents = await bridge.list_agents(page_size=5)
            print(f"Agents found: {agents.total}")
            for a in agents.items[:3]:
                print(f"  - {a.name} ({a.id})")
        except AutoGPTError as e:
            print(f"Agent list failed: {e}")

        # List graphs
        try:
            graphs = await bridge.list_graphs(page_size=5)
            print(f"Graphs found: {graphs.total}")
        except AutoGPTError as e:
            print(f"Graph list failed: {e}")

        # List blocks
        try:
            blocks = await bridge.list_blocks(page_size=5)
            print(f"Blocks found: {blocks.total}")
            for b in blocks.items[:3]:
                print(f"  - {b.name} ({b.block_type})")
        except AutoGPTError as e:
            print(f"Block list failed: {e}")

    print("=== Smoke Test Complete ===")


if __name__ == "__main__":
    asyncio.run(_smoke_test())
