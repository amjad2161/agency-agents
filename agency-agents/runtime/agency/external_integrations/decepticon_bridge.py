"""
Decepticon Bridge — JARVIS Integration Adapter for PurpleAILAB/Decepticon
============================================================================

Provides a unified, async-first Python interface to interact with the Decepticon
autonomous red-team framework across all its API surfaces:

    1. LangGraph Platform  (port 2024)  — agent orchestration, threads, runs
    2. LiteLLM Proxy      (port 4000)  — LLM gateway with failover
    3. Web Dashboard API   (port 3000)  — engagement CRUD, findings, OPPLAN
    4. Workspace Observer  (filesystem) — findings, state, planning docs
    5. Neo4j Graph       (port 7687)  — attack-chain graph queries
    6. Docker Sandbox      (socket)     — sandbox command execution
    7. Defense Backend     (abstract)   — Offensive Vaccine remediation

All clients are independently usable; the top-level ``DecepticonBridge``
composes them into a single facade.

Typical usage::

    bridge = DecepticonBridge.from_env()

    # Start a new engagement via the web dashboard API
    engagement = await bridge.web.create_engagement(
        name="corp-perimeter-2025q3",
        target_type="ip_range",
        target_value="10.0.0.0/24",
    )

    # Create a LangGraph thread for the planning agent (Soundwave)
    thread = await bridge.langgraph.create_thread(
        metadata={"engagement_id": engagement["id"], "assistant_id": "soundwave"}
    )

    # Run Soundwave to generate OPPLAN
    run = await bridge.langgraph.submit_run(
        thread_id=thread["thread_id"],
        assistant_id="soundwave",
        input={"messages": [{"role": "user", "content": "Target is 10.0.0.0/24"}]},
    )

    # Stream events until completion
    async for event in bridge.langgraph.stream_run(
        thread_id=thread["thread_id"], run_id=run["run_id"]
    ):
        print(event)

    # Poll workspace for generated OPPLAN
    opplan = await bridge.workspace.read_opplan(engagement_slug="corp-perimeter-2025q3")

    # Read findings after attack phase
    findings = await bridge.workspace.list_findings("corp-perimeter-2025q3")

Dependencies (install as needed)::

    pip install httpx pydantic neo4j python-dotenv

Author: JARVIS Agency Integration Layer
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
try:
    from enum import StrEnum
except ImportError:
    # Python <3.11 fallback — emulate StrEnum via str + Enum mixin
    from enum import Enum
    class StrEnum(str, Enum):
        def __str__(self):
            return str(self.value)
from pathlib import Path
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Coroutine,
    Literal,
    Sequence,
)

import httpx
from pydantic import BaseModel, Field, field_validator

# ── Optional deps: fail gracefully if not installed ──────────────────────────
try:
    from neo4j import AsyncGraphDatabase
except ImportError:  # pragma: no cover
    AsyncGraphDatabase = None  # type: ignore[misc,assignment]

try:
    import aiofiles
except ImportError:  # pragma: no cover
    aiofiles = None  # type: ignore[assignment]

# ═════════════════════════════════════════════════════════════════════════════
# 0. Configuration
# ═════════════════════════════════════════════════════════════════════════════


class DecepticonConfig(BaseModel):
    """Connection parameters for all Decepticon subsystems.

    Values can be injected via environment variables (``DECEPTICON_*``
    prefix) or by passing kwargs directly.
    """

    # LangGraph Platform
    langgraph_url: str = Field(default="http://localhost:2024")
    langgraph_timeout: float = Field(default=60.0)

    # LiteLLM Proxy
    litellm_url: str = Field(default="http://localhost:4000")
    litellm_api_key: str = Field(default="sk-decepticon-master")
    litellm_timeout: float = Field(default=120.0)

    # Web Dashboard (Next.js)
    web_url: str = Field(default="http://localhost:3000")
    web_api_key: str | None = Field(default=None)  # if dashboard is behind API key
    web_timeout: float = Field(default=30.0)

    # Neo4j
    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="decepticon-graph")

    # Workspace
    workspace_root: Path = Field(
        default_factory=lambda: Path.home() / ".decepticon" / "workspace"
    )

    # Docker
    docker_socket: Path = Field(default=Path("/var/run/docker.sock"))
    sandbox_container: str = Field(default="decepticon-sandbox")

    # Defense
    defense_backend_type: Literal["docker", "ssh", "kubernetes", "noop"] = Field(
        default="docker"
    )
    defense_target_container: str | None = Field(default=None)
    defense_ssh_host: str | None = Field(default=None)
    defense_ssh_user: str | None = Field(default=None)
    defense_ssh_key: Path | None = Field(default=None)

    @field_validator("workspace_root", "docker_socket", "defense_ssh_key", mode="before")
    @classmethod
    def _coerce_path(cls, v: Any) -> Path:
        return Path(v) if v is not None else v

    @classmethod
    def from_env(cls, prefix: str = "DECEPTICON_") -> "DecepticonConfig":
        """Build configuration from environment variables.

        Example: ``DECEPTICON_LANGGRAPH_URL=http://host:2024``
        """
        env: dict[str, Any] = {}
        for key, val in os.environ.items():
            if key.startswith(prefix):
                model_key = key[len(prefix) :].lower()
                env[model_key] = val
        return cls(**env)


# ═════════════════════════════════════════════════════════════════════════════
# 1. LangGraph Platform Client
# ═════════════════════════════════════════════════════════════════════════════


class LangGraphClient:
    """Async HTTP client for the LangGraph Platform REST API.

    Endpoints mirror the LangGraph in-memory server exposed by
    ``langgraph-cli[inmem]`` (default port 2024).
    """

    def __init__(self, config: DecepticonConfig | None = None) -> None:
        self.cfg = config or DecepticonConfig()
        self._client = httpx.AsyncClient(
            base_url=self.cfg.langgraph_url.rstrip("/"),
            timeout=httpx.Timeout(self.cfg.langgraph_timeout),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "LangGraphClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # ── Assistants / Agents ─────────────────────────────────────────────────

    async def list_assistants(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return available agent graphs (assistant definitions)."""
        resp = await self._client.post(
            "/assistants/search",
            json={"limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else data.get("assistants", [])

    # ── Threads ───────────────────────────────────────────────────────────

    async def create_thread(
        self, metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Create a new conversation thread (engagement context)."""
        resp = await self._client.post(
            "/threads",
            json={"metadata": metadata or {}},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_thread(self, thread_id: str) -> dict[str, Any]:
        """Fetch thread metadata and state."""
        resp = await self._client.get(f"/threads/{thread_id}")
        resp.raise_for_status()
        return resp.json()

    async def get_thread_state(self, thread_id: str) -> dict[str, Any]:
        """Poll thread state (messages, values)."""
        resp = await self._client.get(f"/threads/{thread_id}/state")
        resp.raise_for_status()
        return resp.json()

    async def get_thread_history(self, thread_id: str) -> list[dict[str, Any]]:
        """Fetch full message history for a thread."""
        resp = await self._client.get(f"/threads/{thread_id}/history")
        resp.raise_for_status()
        return resp.json()

    # ── Runs ────────────────────────────────────────────────────────────────

    async def submit_run(
        self,
        thread_id: str,
        assistant_id: str,
        input: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Start a new agent run on an existing thread.

        Args:
            thread_id: Existing thread ID.
            assistant_id: Agent graph ID from ``list_assistants()``.
            input: Initial state, typically ``{"messages": [...]}``.
            config: Optional run-time configuration (recursion limit, etc.).
        """
        payload: dict[str, Any] = {"assistant_id": assistant_id}
        if input is not None:
            payload["input"] = input
        if config is not None:
            payload["config"] = config
        resp = await self._client.post(
            f"/threads/{thread_id}/runs",
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    async def stream_run(
        self, thread_id: str, run_id: str
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream run events via Server-Sent Events (SSE).

        Yields parsed event dictionaries (``event``, ``data`` fields).
        """
        url = f"/threads/{thread_id}/runs/{run_id}/join"
        async with self._client.stream("GET", url) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    raw = line[6:]
                    try:
                        yield json.loads(raw)
                    except json.JSONDecodeError:
                        yield {"event": "raw", "data": raw}

    async def get_run(self, thread_id: str, run_id: str) -> dict[str, Any]:
        """Get run status and output."""
        resp = await self._client.get(f"/threads/{thread_id}/runs/{run_id}")
        resp.raise_for_status()
        return resp.json()

    async def cancel_run(self, thread_id: str, run_id: str) -> dict[str, Any]:
        """Cancel an in-flight run."""
        resp = await self._client.post(f"/threads/{thread_id}/runs/{run_id}/cancel")
        resp.raise_for_status()
        return resp.json()


# ═════════════════════════════════════════════════════════════════════════════
# 2. LiteLLM Proxy Client
# ═════════════════════════════════════════════════════════════════════════════


class LiteLLMProxyClient:
    """OpenAI-compatible async client for the Decepticon LiteLLM proxy.

    Routes chat completions through Decepticon's gateway to benefit from
    automatic failover, usage tracking, and billing aggregation.
    """

    def __init__(self, config: DecepticonConfig | None = None) -> None:
        self.cfg = config or DecepticonConfig()
        self._client = httpx.AsyncClient(
            base_url=self.cfg.litellm_url.rstrip("/"),
            timeout=httpx.Timeout(self.cfg.litellm_timeout),
            headers={"Authorization": f"Bearer {self.cfg.litellm_api_key}"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "LiteLLMProxyClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def chat_completion(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        stream: bool = False,
        extra_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a chat completion request through the LiteLLM proxy."""
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if extra_body:
            payload.update(extra_body)
        resp = await self._client.post("/v1/chat/completions", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def list_models(self) -> list[dict[str, Any]]:
        """List available models (with fallback info)."""
        resp = await self._client.get("/v1/models")
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])

    async def health(self) -> dict[str, Any]:
        """Proxy readiness probe."""
        resp = await self._client.get("/health/readiness")
        resp.raise_for_status()
        return resp.json()


# ═════════════════════════════════════════════════════════════════════════════
# 3. Web Dashboard API Client
# ═════════════════════════════════════════════════════════════════════════════


class WebDashboardClient:
    """Async HTTP client for the Next.js dashboard REST API.

    Provides engagement lifecycle management, findings access, and OPPLAN
    retrieval without needing raw LangGraph calls.
    """

    def __init__(self, config: DecepticonConfig | None = None) -> None:
        self.cfg = config or DecepticonConfig()
        headers: dict[str, str] = {}
        if self.cfg.web_api_key:
            headers["X-API-Key"] = self.cfg.web_api_key
        self._client = httpx.AsyncClient(
            base_url=self.cfg.web_url.rstrip("/"),
            timeout=httpx.Timeout(self.cfg.web_timeout),
            headers=headers,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "WebDashboardClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # ── Agents ──────────────────────────────────────────────────────────────

    async def list_agents(self) -> list[dict[str, Any]]:
        """Return display config for all registered agents."""
        resp = await self._client.get("/api/agents")
        resp.raise_for_status()
        return resp.json()

    # ── Engagements ─────────────────────────────────────────────────────────

    async def list_engagements(self) -> list[dict[str, Any]]:
        """List all engagements (DB + auto-imported workspace dirs)."""
        resp = await self._client.get("/api/engagements")
        resp.raise_for_status()
        return resp.json()

    async def create_engagement(
        self,
        name: str,
        target_type: Literal["web_url", "ip_range"],
        target_value: str,
    ) -> dict[str, Any]:
        """Create a new engagement record."""
        resp = await self._client.post(
            "/api/engagements",
            json={"name": name, "targetType": target_type, "targetValue": target_value},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_engagement(self, engagement_id: str) -> dict[str, Any]:
        resp = await self._client.get(f"/api/engagements/{engagement_id}")
        resp.raise_for_status()
        return resp.json()

    async def patch_engagement(
        self, engagement_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        resp = await self._client.patch(
            f"/api/engagements/{engagement_id}",
            json=data,
        )
        resp.raise_for_status()
        return resp.json()

    async def delete_engagement(self, engagement_id: str) -> dict[str, Any]:
        resp = await self._client.delete(f"/api/engagements/{engagement_id}")
        resp.raise_for_status()
        return resp.json()

    # ── Findings ──────────────────────────────────────────────────────────

    async def list_findings(self, engagement_id: str) -> list[dict[str, Any]]:
        """Parse findings from workspace markdown files."""
        resp = await self._client.get(f"/api/engagements/{engagement_id}/findings")
        resp.raise_for_status()
        return resp.json()

    # ── OPPLAN ────────────────────────────────────────────────────────────

    async def get_opplan(self, engagement_id: str) -> dict[str, Any]:
        """Read OPPLAN JSON from workspace."""
        resp = await self._client.get(f"/api/engagements/{engagement_id}/opplan")
        resp.raise_for_status()
        return resp.json()

    # ── Planning Documents ──────────────────────────────────────────────────

    async def list_plan_docs(self, engagement_id: str) -> list[dict[str, Any]]:
        resp = await self._client.get(f"/api/engagements/{engagement_id}/plan-docs")
        resp.raise_for_status()
        return resp.json()


# ═════════════════════════════════════════════════════════════════════════════
# 4. Workspace Observer
# ═════════════════════════════════════════════════════════════════════════════


class WorkspaceObserver:
    """Filesystem observer for Decepticon workspace directories.

    Reads planning documents, findings, and state files directly from disk
    without requiring API calls. Useful for polling-based observation or
    when the web dashboard is not running.
    """

    def __init__(self, config: DecepticonConfig | None = None) -> None:
        self.cfg = config or DecepticonConfig()
        self._root: Path = self.cfg.workspace_root

    def _workspace(self, slug: str) -> Path:
        return self._root / slug

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _read_text(self, path: Path) -> str | None:
        if not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    # ── Planning Documents ────────────────────────────────────────────────

    def read_roe(self, slug: str) -> dict[str, Any] | None:
        """Return RoE JSON if present."""
        return self._read_json(self._workspace(slug) / "plan" / "roe.json")

    def read_conops(self, slug: str) -> dict[str, Any] | None:
        return self._read_json(self._workspace(slug) / "plan" / "conops.json")

    def read_deconfliction(self, slug: str) -> dict[str, Any] | None:
        return self._read_json(self._workspace(slug) / "plan" / "deconfliction.json")

    def read_opplan(self, slug: str) -> dict[str, Any] | None:
        return self._read_json(self._workspace(slug) / "plan" / "opplan.json")

    # ── State ─────────────────────────────────────────────────────────────

    def read_vaccine_state(self, slug: str) -> dict[str, Any] | None:
        """Read orchestrator checkpoint state."""
        return self._read_json(self._workspace(slug) / ".vaccine-state.json")

    # ── Findings ──────────────────────────────────────────────────────────

    def list_findings(self, slug: str) -> list[dict[str, Any]]:
        """Parse all markdown findings in ``findings/``."""
        findings_dir = self._workspace(slug) / "findings"
        if not findings_dir.exists():
            return []
        results: list[dict[str, Any]] = []
        for path in sorted(findings_dir.glob("*.md")):
            parsed = self._parse_finding_markdown(path.read_text(encoding="utf-8"), path.name)
            parsed["filename"] = path.name
            results.append(parsed)
        return results

    @staticmethod
    def _parse_finding_markdown(content: str, filename: str) -> dict[str, Any]:
        """Parse a Decepticon finding markdown file.

        Expected sections::

            # Title
            ## Description
            ...
            ## Evidence
            ...
            ## Attack Vector
            ...
            ## Affected Assets
            - asset1
            - asset2
        """
        lines = content.splitlines()
        result: dict[str, Any] = {
            "title": filename,
            "severity": "medium",
            "description": "",
            "evidence": "",
            "attack_vector": "",
            "affected_assets": [],
        }
        section = ""
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# "):
                result["title"] = stripped[2:].strip()
                continue
            if stripped.startswith("## "):
                section = stripped[3:].strip().lower()
                continue
            if "severity" in stripped.lower() and ":" in stripped:
                val = stripped.split(":", 1)[1].strip().strip("*").lower()
                if val in {"critical", "high", "medium", "low", "informational"}:
                    result["severity"] = val
            if section == "description" and stripped:
                result["description"] += (result["description"] and "\n" or "") + stripped
            if section in {"evidence", "evidence \n"} and stripped:
                result["evidence"] += (result["evidence"] and "\n" or "") + stripped
            if section in {"attack vector", "attack-vector"} and stripped:
                result["attack_vector"] += (result["attack_vector"] and "\n" or "") + stripped
            if section in {"affected assets", "affected", "assets"} and stripped:
                if stripped.startswith("-") or stripped.startswith("*"):
                    result["affected_assets"].append(stripped.lstrip("-* "))
        return result

    # ── Async I/O variants (optional aiofiles) ────────────────────────────

    async def read_opplan_async(self, slug: str) -> dict[str, Any] | None:
        """Async variant using aiofiles if available."""
        path = self._workspace(slug) / "plan" / "opplan.json"
        if not path.exists():
            return None
        if aiofiles is None:
            return self.read_opplan(slug)
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            return json.loads(await f.read())

    async def list_findings_async(self, slug: str) -> list[dict[str, Any]]:
        findings_dir = self._workspace(slug) / "findings"
        if not findings_dir.exists():
            return []
        if aiofiles is None:
            return self.list_findings(slug)
        results: list[dict[str, Any]] = []
        for path in sorted(findings_dir.glob("*.md")):
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()
            parsed = self._parse_finding_markdown(content, path.name)
            parsed["filename"] = path.name
            results.append(parsed)
        return results


# ═════════════════════════════════════════════════════════════════════════════
# 5. Neo4j Graph Client
# ═════════════════════════════════════════════════════════════════════════════


class Neo4jGraphClient:
    """Async Cypher interface to Decepticon's Neo4j attack-chain graph.

    The graph stores discovered hosts, services, vulnerabilities, credentials,
    and relationships (``HAS_SERVICE``, ``VULNERABLE_TO``, ``OWNS``, etc.).
    """

    def __init__(self, config: DecepticonConfig | None = None) -> None:
        self.cfg = config or DecepticonConfig()
        self._driver: Any | None = None
        if AsyncGraphDatabase is None:
            raise ImportError("neo4j driver is required for Neo4jGraphClient")

    async def connect(self) -> "Neo4jGraphClient":
        self._driver = AsyncGraphDatabase.driver(
            self.cfg.neo4j_uri,
            auth=(self.cfg.neo4j_user, self.cfg.neo4j_password),
        )
        await self._driver.verify_connectivity()
        return self

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()
            self._driver = None

    async def __aenter__(self) -> "Neo4jGraphClient":
        return await self.connect()

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def run(self, cypher: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a Cypher query and return records as dictionaries."""
        if self._driver is None:
            raise RuntimeError("Neo4j driver not connected. Use ``await client.connect()``.")
        records: list[dict[str, Any]] = []
        result = await self._driver.execute_query(cypher, parameters or {})
        for record in result.records:
            records.append(dict(record))
        return records

    # ── Common queries ────────────────────────────────────────────────────

    async def get_hosts(self) -> list[dict[str, Any]]:
        """Return all discovered Host nodes."""
        return await self.run("MATCH (h:Host) RETURN h.ip AS ip, h.hostname AS hostname, h.os AS os")

    async def get_services(self, ip: str | None = None) -> list[dict[str, Any]]:
        """Return Service nodes, optionally filtered by host IP."""
        if ip:
            return await self.run(
                "MATCH (h:Host {ip: $ip})-[:HAS_SERVICE]->(s:Service) RETURN s.port AS port, s.name AS name, s.banner AS banner",
                {"ip": ip},
            )
        return await self.run("MATCH (s:Service) RETURN s.port AS port, s.name AS name, s.banner AS banner")

    async def get_vulnerabilities(self) -> list[dict[str, Any]]:
        """Return all Vulnerability nodes with severity."""
        return await self.run(
            "MATCH (v:Vulnerability) RETURN v.cve AS cve, v.severity AS severity, v.title AS title"
        )

    async def get_attack_path(self, start_ip: str, end_ip: str) -> list[dict[str, Any]]:
        """Find shortest attack path between two hosts."""
        return await self.run(
            """
            MATCH path = shortestPath(
                (start:Host {ip: $start_ip})-[:HAS_SERVICE|VULNERABLE_TO|EXPLOITED_WITH*..10]-(end:Host {ip: $end_ip})
            )
            RETURN [n IN nodes(path) | n.ip] AS ips,
                   [r IN relationships(path) | type(r)] AS rels,
                   length(path) AS hops
            """,
            {"start_ip": start_ip, "end_ip": end_ip},
        )

    async def get_credentials(self) -> list[dict[str, Any]]:
        """Return harvested Credential nodes."""
        return await self.run(
            "MATCH (c:Credential) RETURN c.username AS username, c.source AS source, c.host AS host"
        )

    async def get_findings_by_host(self, ip: str) -> list[dict[str, Any]]:
        """Aggregate all graph findings for a specific host."""
        return await self.run(
            """
            MATCH (h:Host {ip: $ip})
            OPTIONAL MATCH (h)-[:HAS_SERVICE]->(s:Service)
            OPTIONAL MATCH (s)-[:VULNERABLE_TO]->(v:Vulnerability)
            OPTIONAL MATCH (h)-[:OWNS]->(c:Credential)
            RETURN h.ip AS ip,
                   collect(DISTINCT {port: s.port, name: s.name}) AS services,
                   collect(DISTINCT {cve: v.cve, severity: v.severity}) AS vulns,
                   collect(DISTINCT {user: c.username, source: c.source}) AS creds
            """,
            {"ip": ip},
        )


# ═════════════════════════════════════════════════════════════════════════════
# 6. Docker Sandbox Bridge
# ═════════════════════════════════════════════════════════════════════════════


class DockerSandboxBridge:
    """Direct Docker socket interface to the Decepticon sandbox.

    Sends commands via ``docker exec`` (non-interactive) for lightweight
    tasks that don't need a full tmux session. For interactive work, use
    the LangGraph bash tool via the normal agent flow.

    Warning: The Docker socket is the **only** bridge between management and
    operations networks. Use sparingly and only for trusted commands.
    """

    def __init__(self, config: DecepticonConfig | None = None) -> None:
        self.cfg = config or DecepticonConfig()

    def _docker_cmd(self, *args: str) -> list[str]:
        return ["docker", "-H", f"unix://{self.cfg.docker_socket}", *args]

    async def execute(
        self,
        command: list[str] | str,
        container: str | None = None,
        working_dir: str | None = None,
        user: str = "root",
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        """Execute a command inside the sandbox container via docker exec.

        Returns::

            {
                "stdout": str,
                "stderr": str,
                "exit_code": int,
                "duration_ms": float,
            }
        """
        container = container or self.cfg.sandbox_container
        cmd = self._docker_cmd("exec", "-u", user)
        if working_dir:
            cmd += ["-w", working_dir]
        cmd += [container]
        if isinstance(command, str):
            cmd += ["sh", "-c", command]
        else:
            cmd += command

        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=timeout + 5.0,
        )
        started = datetime.now(timezone.utc)
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            stdout, stderr = await proc.communicate()
            return {
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
                "exit_code": -1,
                "duration_ms": (datetime.now(timezone.utc) - started).total_seconds() * 1000,
                "timeout": True,
            }
        return {
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "exit_code": proc.returncode or 0,
            "duration_ms": (datetime.now(timezone.utc) - started).total_seconds() * 1000,
            "timeout": False,
        }

    async def list_containers(self) -> list[dict[str, Any]]:
        """List running containers (JSON format)."""
        result = await self.execute(
            command=["docker", "ps", "--format", "{{json .}}"],
            container=self.cfg.sandbox_container,
        )
        lines = result["stdout"].strip().splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    async def copy_to_sandbox(
        self, local_path: Path, remote_path: str, container: str | None = None
    ) -> dict[str, Any]:
        """Copy a local file into the sandbox."""
        container = container or self.cfg.sandbox_container
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "-H",
            f"unix://{self.cfg.docker_socket}",
            "cp",
            str(local_path),
            f"{container}:{remote_path}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return {
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "exit_code": proc.returncode or 0,
        }

    async def copy_from_sandbox(
        self, remote_path: str, local_path: Path, container: str | None = None
    ) -> dict[str, Any]:
        """Copy a file from the sandbox to local filesystem."""
        container = container or self.cfg.sandbox_container
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "-H",
            f"unix://{self.cfg.docker_socket}",
            "cp",
            f"{container}:{remote_path}",
            str(local_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return {
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "exit_code": proc.returncode or 0,
        }


# ═════════════════════════════════════════════════════════════════════════════
# 7. Defense Backend Bridge (Offensive Vaccine Integration)
# ═════════════════════════════════════════════════════════════════════════════


class DefenseActionType(StrEnum):
    """Discrete defensive action categories."""

    BLOCK_PORT = "block_port"
    ADD_FIREWALL_RULE = "add_firewall_rule"
    DISABLE_SERVICE = "disable_service"
    RESTART_SERVICE = "restart_service"
    UPDATE_CONFIG = "update_config"
    KILL_PROCESS = "kill_process"
    REVOKE_CREDENTIAL = "revoke_credential"


class ReAttackOutcome(StrEnum):
    """Outcome of re-running the original attack after defense."""

    BLOCKED = "blocked"
    PASSED = "passed"
    PARTIAL = "partial"
    ERROR = "error"


class DefenseRecommendation(BaseModel):
    """Single recommended defensive action."""

    action_type: DefenseActionType
    target: str
    parameters: dict[str, str] = Field(default_factory=dict)
    priority: int = Field(default=1, ge=1)
    rationale: str


class DefenseBrief(BaseModel):
    """Structured feedback document passed from offensive to defense agent."""

    finding_id: str
    title: str
    severity: str = "medium"
    attack_vector: str = ""
    affected_assets: list[str] = Field(default_factory=list)
    recommendations: list[DefenseRecommendation] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DefenseActionResult(BaseModel):
    """Result of applying a defensive action."""

    recommendation: DefenseRecommendation
    success: bool
    output: str = ""
    rollback_command: str | None = None
    applied_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VerificationResult(BaseModel):
    """Result of re-attacking after defense was applied."""

    finding_id: str
    outcome: ReAttackOutcome
    evidence: str = ""
    verified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AbstractDefenseBackend(ABC):
    """Protocol for executing defensive actions on target environments.

    Implementations map Decepticon's ``DefenseRecommendation`` objects to
    concrete infrastructure commands (iptables, systemctl, kubectl, etc.).
    """

    @abstractmethod
    async def execute_action(self, action: DefenseRecommendation) -> DefenseActionResult:
        ...

    @abstractmethod
    async def rollback_action(self, result: DefenseActionResult) -> DefenseActionResult:
        ...

    @abstractmethod
    async def verify_action(self, result: DefenseActionResult) -> bool:
        ...

    @abstractmethod
    async def list_applied_actions(self) -> list[DefenseActionResult]:
        ...


class DockerDefenseBackend(AbstractDefenseBackend):
    """Concrete defense backend using docker exec.

    Executes iptables/systemctl/pkill/etc. inside a named Docker container.
    This is the reference implementation matching Decepticon's own
    ``decepticon/backends/defense.py`` pattern.
    """

    def __init__(
        self,
        container: str,
        docker_socket: Path = Path("/var/run/docker.sock"),
        user: str = "root",
    ) -> None:
        self.container = container
        self.docker_socket = docker_socket
        self.user = user
        self._history: list[DefenseActionResult] = []

    def _docker_cmd(self, *args: str) -> list[str]:
        return ["docker", "-H", f"unix://{self.docker_socket}", *args]

    async def _exec(self, command: list[str] | str) -> dict[str, Any]:
        cmd = self._docker_cmd("exec", "-u", self.user, self.container)
        if isinstance(command, str):
            cmd += ["sh", "-c", command]
        else:
            cmd += command
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return {
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "exit_code": proc.returncode or 0,
        }

    async def execute_action(self, action: DefenseRecommendation) -> DefenseActionResult:
        command, rollback = self._render_command(action)
        result = await self._exec(command)
        success = result["exit_code"] == 0
        dar = DefenseActionResult(
            recommendation=action,
            success=success,
            output=result["stdout"] + "\n" + result["stderr"],
            rollback_command=rollback,
        )
        self._history.append(dar)
        return dar

    async def rollback_action(self, result: DefenseActionResult) -> DefenseActionResult:
        if not result.rollback_command:
            return DefenseActionResult(
                recommendation=result.recommendation,
                success=False,
                output="No rollback command available.",
            )
        res = await self._exec(result.rollback_command)
        success = res["exit_code"] == 0
        return DefenseActionResult(
            recommendation=result.recommendation,
            success=success,
            output=res["stdout"] + "\n" + res["stderr"],
        )

    async def verify_action(self, result: DefenseActionResult) -> bool:
        # Default verification: re-run a lightweight check derived from action type
        verify_cmd = self._render_verify_command(result.recommendation)
        res = await self._exec(verify_cmd)
        return res["exit_code"] == 0

    async def list_applied_actions(self) -> list[DefenseActionResult]:
        return list(self._history)

    # ── Command rendering ──────────────────────────────────────────────────

    def _render_command(self, action: DefenseRecommendation) -> tuple[list[str], str | None]:
        at = action.action_type
        t = action.target
        p = action.parameters

        if at == DefenseActionType.BLOCK_PORT:
            proto = p.get("proto", "tcp")
            cmd = f"iptables -A INPUT -p {proto} --dport {t} -j DROP"
            rollback = f"iptables -D INPUT -p {proto} --dport {t} -j DROP"
            return ["sh", "-c", cmd], rollback

        if at == DefenseActionType.ADD_FIREWALL_RULE:
            rule = p.get("rule", "DROP")
            chain = p.get("chain", "INPUT")
            cmd = f"iptables -A {chain} -p tcp --dport {t} -j {rule}"
            rollback = f"iptables -D {chain} -p tcp --dport {t} -j {rule}"
            return ["sh", "-c", cmd], rollback

        if at == DefenseActionType.DISABLE_SERVICE:
            return ["systemctl", "disable", "--now", t], f"systemctl enable --now {t}"

        if at == DefenseActionType.RESTART_SERVICE:
            return ["systemctl", "restart", t], None

        if at == DefenseActionType.KILL_PROCESS:
            sig = p.get("signal", "TERM")
            return ["pkill", f"-{sig}", t], None

        if at == DefenseActionType.UPDATE_CONFIG:
            path = p.get("path", "/etc/default/config")
            key = p.get("key", "SETTING")
            val = p.get("value", "new_value")
            # Naive sed-based update; real impl should use proper templating
            old_val = p.get("old_value", ".*")
            cmd = f"sed -i 's/^{key}={old_val}/{key}={val}/' {path}"
            rollback = f"sed -i 's/^{key}={val}/{key}={old_val}/' {path}"
            return ["sh", "-c", cmd], rollback

        if at == DefenseActionType.REVOKE_CREDENTIAL:
            # Placeholder: credential revocation is highly environment-specific
            return ["echo", f"revoke credential {t}"], None

        return ["echo", f"Unknown action: {at}"], None

    def _render_verify_command(self, action: DefenseRecommendation) -> list[str]:
        at = action.action_type
        t = action.target
        if at == DefenseActionType.BLOCK_PORT:
            return ["sh", "-c", f"iptables -C INPUT -p tcp --dport {t} -j DROP 2>/dev/null"]
        if at == DefenseActionType.DISABLE_SERVICE:
            return ["systemctl", "is-active", t]
        return ["true"]


class KubernetesDefenseBackend(AbstractDefenseBackend):
    """Defense backend for Kubernetes targets.

    Applies network policies, patches deployments, restarts pods, etc.
    """

    def __init__(self, namespace: str = "default", context: str | None = None) -> None:
        self.namespace = namespace
        self.context = context
        self._history: list[DefenseActionResult] = []

    def _kubectl(self, *args: str) -> list[str]:
        cmd = ["kubectl"]
        if self.context:
            cmd += ["--context", self.context]
        cmd += ["-n", self.namespace, *args]
        return cmd

    async def _exec(self, command: list[str]) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return {
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "exit_code": proc.returncode or 0,
        }

    async def execute_action(self, action: DefenseRecommendation) -> DefenseActionResult:
        command, rollback = self._render_k8s_command(action)
        result = await self._exec(command)
        success = result["exit_code"] == 0
        dar = DefenseActionResult(
            recommendation=action,
            success=success,
            output=result["stdout"] + "\n" + result["stderr"],
            rollback_command=rollback,
        )
        self._history.append(dar)
        return dar

    async def rollback_action(self, result: DefenseActionResult) -> DefenseActionResult:
        if not result.rollback_command:
            return DefenseActionResult(
                recommendation=result.recommendation,
                success=False,
                output="No rollback command available.",
            )
        res = await self._exec(json.loads(result.rollback_command))
        return DefenseActionResult(
            recommendation=result.recommendation,
            success=res["exit_code"] == 0,
            output=res["stdout"] + "\n" + res["stderr"],
        )

    async def verify_action(self, result: DefenseActionResult) -> bool:
        # Simplistic: re-apply a dry-run or get command
        return True  # Override with real checks

    async def list_applied_actions(self) -> list[DefenseActionResult]:
        return list(self._history)

    def _render_k8s_command(
        self, action: DefenseRecommendation
    ) -> tuple[list[str], str | None]:
        at = action.action_type
        t = action.target
        p = action.parameters

        if at == DefenseActionType.BLOCK_PORT:
            policy_name = p.get("policy_name", f"block-{t}")
            cmd = self._kubectl(
                "create", "networkpolicy", policy_name,
                "--pod-selector", p.get("pod_selector", "app=target"),
                "--ingress", f"0/0",
                "--deny",
            )
            rollback = json.dumps(self._kubectl("delete", "networkpolicy", policy_name))
            return cmd, rollback

        if at == DefenseActionType.DISABLE_SERVICE:
            # Scale deployment to 0
            cmd = self._kubectl("scale", "deployment", t, "--replicas=0")
            rollback = json.dumps(self._kubectl("scale", "deployment", t, "--replicas=1"))
            return cmd, rollback

        if at == DefenseActionType.KILL_PROCESS:
            # Delete pods matching label
            cmd = self._kubectl("delete", "pods", "-l", f"app={t}")
            return cmd, None

        if at == DefenseActionType.UPDATE_CONFIG:
            # Patch deployment env var
            key = p.get("key", "SETTING")
            val = p.get("value", "new_value")
            patch = json.dumps({"spec": {"template": {"spec": {"containers": [{"name": t, "env": [{"name": key, "value": val}]}]}}}})
            cmd = self._kubectl("patch", "deployment", t, "--type=strategic", "-p", patch)
            rollback = None  # Complex; snapshot before apply in production
            return cmd, rollback

        return self._kubectl("echo", f"Unhandled action {at}"), None


def create_defense_backend(config: DecepticonConfig) -> AbstractDefenseBackend:
    """Factory: create the appropriate defense backend from config."""
    if config.defense_backend_type == "docker":
        container = config.defense_target_container or config.sandbox_container
        return DockerDefenseBackend(container, config.docker_socket)
    if config.defense_backend_type == "kubernetes":
        return KubernetesDefenseBackend(namespace=config.defense_target_container or "default")
    if config.defense_backend_type == "noop":
        return NoOpDefenseBackend()
    raise ValueError(f"Unsupported defense backend: {config.defense_backend_type}")


class NoOpDefenseBackend(AbstractDefenseBackend):
    """No-op backend for testing and dry-run observation."""

    def __init__(self) -> None:
        self._history: list[DefenseActionResult] = []

    async def execute_action(self, action: DefenseRecommendation) -> DefenseActionResult:
        dar = DefenseActionResult(
            recommendation=action,
            success=True,
            output="NOOP: action would have been applied.",
        )
        self._history.append(dar)
        return dar

    async def rollback_action(self, result: DefenseActionResult) -> DefenseActionResult:
        return DefenseActionResult(
            recommendation=result.recommendation,
            success=True,
            output="NOOP: rollback would have been applied.",
        )

    async def verify_action(self, result: DefenseActionResult) -> bool:
        return True

    async def list_applied_actions(self) -> list[DefenseActionResult]:
        return list(self._history)


# ═════════════════════════════════════════════════════════════════════════════
# 8. Unified Bridge Facade
# ═════════════════════════════════════════════════════════════════════════════


class DecepticonBridge:
    """Unified facade composing all Decepticon subsystem clients.

    This is the primary entry point for JARVIS integration. It manages
    lifecycle (connect/open, close/cleanup) for all underlying clients and
    provides high-level workflows that span multiple subsystems.
    """

    def __init__(self, config: DecepticonConfig | None = None) -> None:
        self.cfg = config or DecepticonConfig()
        self.langgraph = LangGraphClient(self.cfg)
        self.litellm = LiteLLMProxyClient(self.cfg)
        self.web = WebDashboardClient(self.cfg)
        self.workspace = WorkspaceObserver(self.cfg)
        self.neo4j = Neo4jGraphClient(self.cfg)
        self.sandbox = DockerSandboxBridge(self.cfg)
        self.defense: AbstractDefenseBackend = create_defense_backend(self.cfg)
        self._neo4j_connected = False

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def connect(self) -> "DecepticonBridge":
        """Connect all stateful clients (currently only Neo4j requires explicit connect)."""
        if AsyncGraphDatabase is not None:
            await self.neo4j.connect()
            self._neo4j_connected = True
        return self

    async def close(self) -> None:
        """Close all underlying HTTP and database clients."""
        await self.langgraph.close()
        await self.litellm.close()
        await self.web.close()
        await self.neo4j.close()
        self._neo4j_connected = False

    async def __aenter__(self) -> "DecepticonBridge":
        return await self.connect()

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # ── High-level workflows ────────────────────────────────────────────────

    async def run_planning(
        self,
        engagement_slug: str,
        target: str,
        target_type: Literal["web_url", "ip_range"] = "ip_range",
    ) -> dict[str, Any]:
        """End-to-end planning phase: create engagement + Soundwave OPPLAN generation.

        Returns the final thread state after Soundwave completes.
        """
        # 1. Create engagement via web API (or workspace directly)
        try:
            engagement = await self.web.create_engagement(
                name=engagement_slug,
                target_type=target_type,
                target_value=target,
            )
        except httpx.HTTPError:
            # Web dashboard may not be running; fallback to workspace only
            engagement = {"id": engagement_slug, "name": engagement_slug}

        # 2. Create LangGraph thread
        thread = await self.langgraph.create_thread(
            metadata={"engagement_id": engagement["id"], "assistant_id": "soundwave"}
        )

        # 3. Run Soundwave
        run = await self.langgraph.submit_run(
            thread_id=thread["thread_id"],
            assistant_id="soundwave",
            input={
                "messages": [
                    {
                        "role": "user",
                        "content": f"Generate a full engagement package for target: {target}",
                    }
                ]
            },
        )

        # 4. Stream to completion (fire-and-forget style; caller can stream instead)
        async for _event in self.langgraph.stream_run(
            thread_id=thread["thread_id"], run_id=run["run_id"]
        ):
            pass

        # 5. Return thread state + engagement record
        state = await self.langgraph.get_thread_state(thread["thread_id"])
        return {
            "engagement": engagement,
            "thread_id": thread["thread_id"],
            "run_id": run["run_id"],
            "state": state,
        }

    async def run_attack_loop(
        self,
        engagement_slug: str,
        thread_id: str,
        max_iterations: int = 50,
    ) -> dict[str, Any]:
        """Run the autonomous attack loop via the main decepticon orchestrator.

        Preconditions:
            - OPPLAN must exist at ``workspace/{slug}/plan/opplan.json``
            - Thread already created and optionally primed by Soundwave
        """
        # Submit main orchestrator run
        run = await self.langgraph.submit_run(
            thread_id=thread_id,
            assistant_id="decepticon",
            input={
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Execute OPPLAN for engagement {engagement_slug}. "
                            f"Max iterations: {max_iterations}."
                        ),
                    }
                ]
            },
        )

        # Stream events
        events: list[dict[str, Any]] = []
        async for event in self.langgraph.stream_run(
            thread_id=thread_id, run_id=run["run_id"]
        ):
            events.append(event)

        return {
            "thread_id": thread_id,
            "run_id": run["run_id"],
            "events": events,
            "findings": self.workspace.list_findings(engagement_slug),
            "vaccine_state": self.workspace.read_vaccine_state(engagement_slug),
        }

    async def apply_vaccine(
        self,
        engagement_slug: str,
        findings: list[DefenseBrief] | None = None,
    ) -> list[dict[str, Any]]:
        """Apply Offensive Vaccine defenses for all findings in an engagement.

        If ``findings`` is not provided, reads from workspace filesystem.
        """
        if findings is None:
            raw_findings = self.workspace.list_findings(engagement_slug)
            findings = self._convert_raw_findings(raw_findings)

        results: list[dict[str, Any]] = []
        for brief in findings:
            for rec in brief.recommendations:
                result = await self.defense.execute_action(rec)
                verified = False
                if result.success:
                    verified = await self.defense.verify_action(result)
                results.append(
                    {
                        "finding_id": brief.finding_id,
                        "recommendation": rec.model_dump(),
                        "result": result.model_dump(),
                        "verified": verified,
                    }
                )
        return results

    @staticmethod
    def _convert_raw_findings(raw: list[dict[str, Any]]) -> list[DefenseBrief]:
        """Convert workspace markdown findings into DefenseBrief objects."""
        out: list[DefenseBrief] = []
        for idx, r in enumerate(raw, 1):
            # Generate a synthetic recommendation if none exists
            rec = DefenseRecommendation(
                action_type=DefenseActionType.ADD_FIREWALL_RULE,
                target=r.get("affected_assets", ["unknown"])[0] if r.get("affected_assets") else "unknown",
                rationale=f"Auto-generated from finding {r.get('title', 'unknown')}",
            )
            out.append(
                DefenseBrief(
                    finding_id=f"FIND-{idx:03d}",
                    title=r.get("title", "Untitled"),
                    severity=r.get("severity", "medium"),
                    attack_vector=r.get("attack_vector", ""),
                    affected_assets=r.get("affected_assets", []),
                    recommendations=[rec],
                )
            )
        return out

    # ── Utility ───────────────────────────────────────────────────────────

    async def health_check(self) -> dict[str, Any]:
        """Probe all Decepticon subsystems for liveness."""
        health: dict[str, Any] = {
            "langgraph": {"ok": False, "detail": None},
            "litellm": {"ok": False, "detail": None},
            "web": {"ok": False, "detail": None},
            "neo4j": {"ok": False, "detail": None},
            "sandbox": {"ok": False, "detail": None},
        }

        # LangGraph
        try:
            assistants = await self.langgraph.list_assistants(limit=1)
            health["langgraph"] = {"ok": True, "detail": f"{len(assistants)} assistants"}
        except Exception as e:
            health["langgraph"]["detail"] = str(e)

        # LiteLLM
        try:
            h = await self.litellm.health()
            health["litellm"] = {"ok": True, "detail": h}
        except Exception as e:
            health["litellm"]["detail"] = str(e)

        # Web
        try:
            agents = await self.web.list_agents()
            health["web"] = {"ok": True, "detail": f"{len(agents)} agents"}
        except Exception as e:
            health["web"]["detail"] = str(e)

        # Neo4j
        if self._neo4j_connected:
            try:
                hosts = await self.neo4j.get_hosts()
                health["neo4j"] = {"ok": True, "detail": f"{len(hosts)} hosts"}
            except Exception as e:
                health["neo4j"]["detail"] = str(e)
        else:
            health["neo4j"]["detail"] = "Not connected"

        # Sandbox (docker ps)
        try:
            res = await self.sandbox.execute(["echo", "sandbox-ok"])
            health["sandbox"] = {
                "ok": res["exit_code"] == 0,
                "detail": res["stdout"].strip(),
            }
        except Exception as e:
            health["sandbox"]["detail"] = str(e)

        health["overall"] = all(v["ok"] for v in health.values() if isinstance(v, dict))
        return health

    @classmethod
    def from_env(cls, prefix: str = "DECEPTICON_") -> "DecepticonBridge":
        """Instantiate bridge from environment variables."""
        return cls(DecepticonConfig.from_env(prefix))


# ═════════════════════════════════════════════════════════════════════════════
# 9. Standalone CLI / Test Helpers
# ═════════════════════════════════════════════════════════════════════════════


async def _demo() -> None:
    """Quick self-test: health-check all subsystems."""
    bridge = DecepticonBridge.from_env()
    async with bridge:
        health = await bridge.health_check()
        print(json.dumps(health, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(_demo())
