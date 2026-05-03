"""
auto_browser_bridge.py — Integration adapter for the auto-browser MCP-native browser control plane.

Provides a structured, async-first bridge between the Jarvis agency runtime and the
auto-browser controller REST API / MCP endpoints.

Target repo: https://github.com/LvcidPsyche/auto-browser (auto-browser v1.0.2+)
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Literal, Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config & constants
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = os.getenv("AUTO_BROWSER_URL", "http://127.0.0.1:8000")
DEFAULT_TOKEN = os.getenv("AUTO_BROWSER_TOKEN", "")
DEFAULT_TIMEOUT = float(os.getenv("AUTO_BROWSER_TIMEOUT", "60.0"))
DEFAULT_MAX_RETRIES = int(os.getenv("AUTO_BROWSER_MAX_RETRIES", "3"))


class PerceptionPreset(str, Enum):
    FAST = "fast"      # screenshot only
    NORMAL = "normal"  # default balanced view
    RICH = "rich"      # extended DOM + OCR + accessibility


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class IsolationMode(str, Enum):
    SHARED = "shared"
    DOCKER_EPHEMERAL = "docker_ephemeral"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AutoBrowserBridgeError(Exception):
    """Base bridge error."""
    def __init__(self, message: str, status_code: int | None = None, detail: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class SessionError(AutoBrowserBridgeError):
    """Session lifecycle or state error."""


class ActionError(AutoBrowserBridgeError):
    """Browser action execution error."""


class ApprovalRequiredError(AutoBrowserBridgeError):
    """Raised when an action requires operator approval."""
    def __init__(self, message: str, approval_id: str | None = None, **kwargs):
        super().__init__(message, **kwargs)
        self.approval_id = approval_id


# ---------------------------------------------------------------------------
# Data models (lightweight, bridge-facing)
# ---------------------------------------------------------------------------

@dataclass
class SessionInfo:
    id: str
    name: str | None
    start_url: str | None
    created_at: str | None
    status: str
    vnc_url: str | None = None
    remote_access: dict | None = None


@dataclass
class Observation:
    url: str
    title: str
    screenshot_b64: str | None
    interactables: list[dict]
    console_messages: list[dict]
    accessibility_outline: str | None = None
    dom_outline: str | None = None
    ocr_excerpts: list[dict] = field(default_factory=list)
    network_summary: list[dict] = field(default_factory=list)

    @property
    def screenshot_bytes(self) -> bytes | None:
        if self.screenshot_b64:
            return base64.b64decode(self.screenshot_b64)
        return None


@dataclass
class ActionResult:
    success: bool
    action_type: str
    before_url: str | None
    after_url: str | None
    before_title: str | None
    after_title: str | None
    screenshot_b64: str | None
    verification: dict | None = None
    error: str | None = None

    @property
    def screenshot_bytes(self) -> bytes | None:
        if self.screenshot_b64:
            return base64.b64decode(self.screenshot_b64)
        return None


@dataclass
class AuthProfile:
    name: str
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class ApprovalItem:
    id: str
    status: ApprovalStatus
    action_type: str | None
    session_id: str | None
    requested_at: str | None = None
    resolved_at: str | None = None
    comment: str | None = None


@dataclass
class AuditEvent:
    id: str
    event_type: str
    session_id: str | None
    operator_id: str | None
    timestamp: str
    payload: dict


# ---------------------------------------------------------------------------
# Core bridge
# ---------------------------------------------------------------------------

class AutoBrowserBridge:
    """
    Async-first bridge to the auto-browser controller.

    Usage:
        bridge = AutoBrowserBridge()
        async with bridge.session(name="demo", start_url="https://example.com") as sess:
            obs = await bridge.observe(sess.id)
            result = await bridge.click(sess.id, selector="button#submit")
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        token: str | None = DEFAULT_TOKEN,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        operator_id: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.max_retries = max_retries
        self.operator_id = operator_id or os.getenv("AUTO_BROWSER_OPERATOR_ID", "jarvis")

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Operator-Id": self.operator_id,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        self._client: httpx.AsyncClient | None = None
        self._headers = headers

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers,
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> AutoBrowserBridge:
        await self._ensure_client()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    # ── Low-level request helpers ───────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        json_body: dict | None = None,
        params: dict | None = None,
        stream: bool = False,
    ) -> Any:
        client = await self._ensure_client()
        url = f"{self.base_url}{path}"
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                if stream:
                    # streaming returns the raw response; caller must close it
                    return await client.stream(method, url, json=json_body, params=params)
                response = await client.request(method, url, json=json_body, params=params)
                if response.status_code == 429:
                    # rate-limited: brief backoff
                    wait = 0.5 * (2 ** attempt)
                    logger.warning("auto-browser rate limited, retrying in %.1fs (attempt %d/%d)", wait, attempt, self.max_retries)
                    await asyncio.sleep(wait)
                    continue
                response.raise_for_status()
                if response.status_code == 204 or not response.content:
                    return {}
                return response.json()
            except httpx.HTTPStatusError as exc:
                detail = self._safe_json(exc.response)
                status = exc.response.status_code
                # If approval required (409/423 or detail contains approval_id)
                approval_id = self._extract_approval_id(detail)
                if approval_id:
                    raise ApprovalRequiredError(
                        f"Approval required for {method} {path}",
                        status_code=status,
                        detail=detail,
                        approval_id=approval_id,
                    ) from exc
                if status >= 500 and attempt < self.max_retries:
                    wait = 0.5 * (2 ** attempt)
                    logger.warning("auto-browser server error %d, retrying in %.1fs (attempt %d/%d)", status, wait, attempt, self.max_retries)
                    await asyncio.sleep(wait)
                    continue
                raise AutoBrowserBridgeError(
                    f"HTTP {status} on {method} {path}", status_code=status, detail=detail
                ) from exc
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_error = exc
                wait = 0.5 * (2 ** attempt)
                logger.warning("auto-browser connection error, retrying in %.1fs (attempt %d/%d): %s", wait, attempt, self.max_retries, exc)
                await asyncio.sleep(wait)
        raise AutoBrowserBridgeError(
            f"Failed after {self.max_retries} attempts: {last_error}"
        ) from last_error

    @staticmethod
    def _safe_json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except Exception:
            return response.text

    @staticmethod
    def _extract_approval_id(detail: Any) -> str | None:
        if isinstance(detail, dict):
            return detail.get("approval_id") or detail.get("approvalId")
        if isinstance(detail, str):
            # naive fallback
            import re
            m = re.search(r'["\']approval_id["\']\s*:\s*["\']([^"\']+)["\']', detail)
            if m:
                return m.group(1)
        return None

    # ── Health & readiness ──────────────────────────────────────────────────

    async def health(self) -> dict:
        """Lightweight liveness probe."""
        return await self._request("GET", "/healthz")

    async def ready(self) -> dict:
        """Readiness probe with controller state summary."""
        return await self._request("GET", "/readyz")

    async def readiness_check(self, mode: Literal["normal", "confidential"] = "normal") -> dict:
        """Deployment readiness advisor."""
        return await self._request("POST", "/readiness", {"mode": mode})

    # ── Sessions ────────────────────────────────────────────────────────────

    async def create_session(
        self,
        *,
        name: str | None = None,
        start_url: str | None = None,
        auth_profile: str | None = None,
        proxy_persona: str | None = None,
        isolation: IsolationMode | str = IsolationMode.SHARED,
    ) -> SessionInfo:
        body: dict[str, Any] = {}
        if name:
            body["name"] = name
        if start_url:
            body["start_url"] = start_url
        if auth_profile:
            body["auth_profile"] = auth_profile
        if proxy_persona:
            body["proxy_persona"] = proxy_persona
        if isolation:
            body["isolation"] = str(isolation)

        data = await self._request("POST", "/sessions", body)
        return self._parse_session(data)

    async def list_sessions(self) -> list[SessionInfo]:
        data = await self._request("GET", "/sessions")
        return [self._parse_session(s) for s in data] if isinstance(data, list) else []

    async def get_session(self, session_id: str) -> SessionInfo:
        data = await self._request("GET", f"/sessions/{session_id}")
        return self._parse_session(data)

    async def close_session(self, session_id: str) -> dict:
        return await self._request("DELETE", f"/sessions/{session_id}")

    async def fork_session(
        self,
        session_id: str,
        *,
        name: str | None = None,
        start_url: str | None = None,
    ) -> SessionInfo:
        body: dict[str, Any] = {}
        if name:
            body["name"] = name
        if start_url:
            body["start_url"] = start_url
        data = await self._request("POST", f"/sessions/{session_id}/fork", body)
        return self._parse_session(data)

    @staticmethod
    def _parse_session(data: dict) -> SessionInfo:
        return SessionInfo(
            id=data.get("id") or data.get("session_id") or "",
            name=data.get("name"),
            start_url=data.get("start_url"),
            created_at=data.get("created_at"),
            status=data.get("status", "unknown"),
            vnc_url=data.get("vnc_url"),
            remote_access=data.get("remote_access"),
        )

    @asynccontextmanager
    async def session(
        self,
        *,
        name: str | None = None,
        start_url: str | None = None,
        auth_profile: str | None = None,
        proxy_persona: str | None = None,
        isolation: IsolationMode | str = IsolationMode.SHARED,
    ) -> AsyncGenerator[SessionInfo, None]:
        """Context manager that creates a session and guarantees cleanup."""
        sess = await self.create_session(
            name=name,
            start_url=start_url,
            auth_profile=auth_profile,
            proxy_persona=proxy_persona,
            isolation=isolation,
        )
        try:
            yield sess
        finally:
            try:
                await self.close_session(sess.id)
            except Exception as exc:
                logger.warning("auto-browser session cleanup error for %s: %s", sess.id, exc)

    # ── Observation ─────────────────────────────────────────────────────────

    async def observe(
        self,
        session_id: str,
        *,
        preset: PerceptionPreset = PerceptionPreset.NORMAL,
        limit: int = 40,
    ) -> Observation:
        data = await self._request(
            "POST",
            f"/sessions/{session_id}/observe",
            {"preset": str(preset), "limit": limit},
        )
        return self._parse_observation(data)

    @staticmethod
    def _parse_observation(data: dict) -> Observation:
        return Observation(
            url=data.get("url", ""),
            title=data.get("title", ""),
            screenshot_b64=data.get("screenshot_b64") or data.get("screenshot"),
            interactables=data.get("interactables") or data.get("elements") or [],
            console_messages=data.get("console_messages") or data.get("console") or [],
            accessibility_outline=data.get("accessibility_outline"),
            dom_outline=data.get("dom_outline") or data.get("dom"),
            ocr_excerpts=data.get("ocr_excerpts") or [],
            network_summary=data.get("network_summary") or data.get("network") or [],
        )

    # ── Screenshots ─────────────────────────────────────────────────────────

    async def screenshot(self, session_id: str, label: str = "manual") -> str:
        """Return base64-encoded screenshot string."""
        data = await self._request(
            "POST", f"/sessions/{session_id}/screenshot", {"label": label}
        )
        return data.get("screenshot_b64") or data.get("screenshot", "")

    async def screenshot_diff(self, session_id: str) -> dict:
        return await self._request("POST", f"/sessions/{session_id}/screenshot/compare")

    # ── Navigation ──────────────────────────────────────────────────────────

    async def navigate(self, session_id: str, url: str) -> ActionResult:
        data = await self._request(
            "POST", f"/sessions/{session_id}/actions/navigate", {"url": url}
        )
        return self._parse_action_result(data, "navigate")

    # ── Interactions ──────────────────────────────────────────────────────────

    async def click(
        self,
        session_id: str,
        *,
        selector: str | None = None,
        element_id: str | None = None,
        x: float | None = None,
        y: float | None = None,
    ) -> ActionResult:
        body: dict[str, Any] = {}
        if selector:
            body["selector"] = selector
        if element_id:
            body["element_id"] = element_id
        if x is not None:
            body["x"] = x
        if y is not None:
            body["y"] = y
        data = await self._request("POST", f"/sessions/{session_id}/actions/click", body)
        return self._parse_action_result(data, "click")

    async def type_text(
        self,
        session_id: str,
        text: str,
        *,
        selector: str | None = None,
        element_id: str | None = None,
        clear_first: bool = True,
    ) -> ActionResult:
        body = {"text": text, "clear_first": clear_first}
        if selector:
            body["selector"] = selector
        if element_id:
            body["element_id"] = element_id
        data = await self._request("POST", f"/sessions/{session_id}/actions/type", body)
        return self._parse_action_result(data, "type")

    async def scroll(
        self,
        session_id: str,
        *,
        delta_x: float = 0,
        delta_y: float = 600,
    ) -> ActionResult:
        data = await self._request(
            "POST",
            f"/sessions/{session_id}/actions/scroll",
            {"delta_x": delta_x, "delta_y": delta_y},
        )
        return self._parse_action_result(data, "scroll")

    async def hover(
        self,
        session_id: str,
        *,
        selector: str | None = None,
        element_id: str | None = None,
        x: float | None = None,
        y: float | None = None,
    ) -> ActionResult:
        body: dict[str, Any] = {}
        if selector:
            body["selector"] = selector
        if element_id:
            body["element_id"] = element_id
        if x is not None:
            body["x"] = x
        if y is not None:
            body["y"] = y
        data = await self._request("POST", f"/sessions/{session_id}/actions/hover", body)
        return self._parse_action_result(data, "hover")

    async def select_option(
        self,
        session_id: str,
        *,
        selector: str | None = None,
        element_id: str | None = None,
        value: str | None = None,
        label: str | None = None,
        index: int | None = None,
    ) -> ActionResult:
        body: dict[str, Any] = {}
        if selector:
            body["selector"] = selector
        if element_id:
            body["element_id"] = element_id
        if value is not None:
            body["value"] = value
        if label is not None:
            body["label"] = label
        if index is not None:
            body["index"] = index
        data = await self._request("POST", f"/sessions/{session_id}/actions/select-option", body)
        return self._parse_action_result(data, "select_option")

    async def wait(self, session_id: str, milliseconds: int) -> ActionResult:
        data = await self._request(
            "POST", f"/sessions/{session_id}/actions/wait", {"wait_ms": milliseconds}
        )
        return self._parse_action_result(data, "wait")

    async def reload(self, session_id: str) -> ActionResult:
        data = await self._request("POST", f"/sessions/{session_id}/actions/reload")
        return self._parse_action_result(data, "reload")

    async def go_back(self, session_id: str) -> ActionResult:
        data = await self._request("POST", f"/sessions/{session_id}/actions/go-back")
        return self._parse_action_result(data, "go_back")

    async def go_forward(self, session_id: str) -> ActionResult:
        data = await self._request("POST", f"/sessions/{session_id}/actions/go-forward")
        return self._parse_action_result(data, "go_forward")

    # ── Advanced actions ──────────────────────────────────────────────────────

    async def eval_js(self, session_id: str, expression: str) -> Any:
        data = await self._request(
            "POST", f"/sessions/{session_id}/actions/eval-js", {"expression": expression}
        )
        return data.get("result", data)

    async def find_elements(
        self, session_id: str, selector: str, limit: int = 20
    ) -> list[dict]:
        data = await self._request(
            "POST",
            f"/sessions/{session_id}/actions/find-elements",
            {"selector": selector, "limit": limit},
        )
        return data.get("elements") or data.get("results") or []

    async def wait_for_selector(
        self,
        session_id: str,
        selector: str,
        *,
        timeout_ms: int = 10000,
        state: Literal["visible", "hidden", "attached", "detached"] = "visible",
    ) -> ActionResult:
        data = await self._request(
            "POST",
            f"/sessions/{session_id}/actions/wait-for-selector",
            {"selector": selector, "timeout_ms": timeout_ms, "state": state},
        )
        return self._parse_action_result(data, "wait_for_selector")

    async def drag_drop(
        self,
        session_id: str,
        *,
        source_selector: str | None = None,
        source_x: float | None = None,
        source_y: float | None = None,
        target_selector: str | None = None,
        target_x: float | None = None,
        target_y: float | None = None,
    ) -> ActionResult:
        body: dict[str, Any] = {}
        if source_selector:
            body["source_selector"] = source_selector
        if source_x is not None:
            body["source_x"] = source_x
        if source_y is not None:
            body["source_y"] = source_y
        if target_selector:
            body["target_selector"] = target_selector
        if target_x is not None:
            body["target_x"] = target_x
        if target_y is not None:
            body["target_y"] = target_y
        data = await self._request("POST", f"/sessions/{session_id}/actions/drag-drop", body)
        return self._parse_action_result(data, "drag_drop")

    async def set_viewport(self, session_id: str, width: int, height: int) -> ActionResult:
        data = await self._request(
            "POST",
            f"/sessions/{session_id}/actions/set-viewport",
            {"width": width, "height": height},
        )
        return self._parse_action_result(data, "set_viewport")

    async def get_cookies(self, session_id: str, urls: list[str] | None = None) -> list[dict]:
        body: dict[str, Any] = {}
        if urls:
            body["urls"] = urls
        data = await self._request("POST", f"/sessions/{session_id}/actions/get-cookies", body)
        return data.get("cookies") or []

    async def set_cookies(self, session_id: str, cookies: list[dict]) -> ActionResult:
        data = await self._request(
            "POST", f"/sessions/{session_id}/actions/set-cookies", {"cookies": cookies}
        )
        return self._parse_action_result(data, "set_cookies")

    async def get_storage(
        self,
        session_id: str,
        storage_type: Literal["local", "session"] = "local",
        key: str | None = None,
    ) -> dict:
        body: dict[str, Any] = {"storage_type": storage_type}
        if key:
            body["key"] = key
        return await self._request("POST", f"/sessions/{session_id}/actions/get-storage", body)

    async def set_storage(
        self,
        session_id: str,
        key: str,
        value: str,
        storage_type: Literal["local", "session"] = "local",
    ) -> ActionResult:
        data = await self._request(
            "POST",
            f"/sessions/{session_id}/actions/set-storage",
            {"storage_type": storage_type, "key": key, "value": value},
        )
        return self._parse_action_result(data, "set_storage")

    @staticmethod
    def _parse_action_result(data: dict, action_type: str) -> ActionResult:
        return ActionResult(
            success=data.get("success", True) and not data.get("error"),
            action_type=action_type,
            before_url=data.get("before_url"),
            after_url=data.get("after_url"),
            before_title=data.get("before_title"),
            after_title=data.get("after_title"),
            screenshot_b64=data.get("screenshot_b64") or data.get("screenshot"),
            verification=data.get("verification"),
            error=data.get("error"),
        )

    # ── Auth profiles ─────────────────────────────────────────────────────────

    async def list_auth_profiles(self) -> list[AuthProfile]:
        data = await self._request("GET", "/auth-profiles")
        return [
            AuthProfile(name=p.get("name", ""), created_at=p.get("created_at"), updated_at=p.get("updated_at"))
            for p in (data if isinstance(data, list) else data.get("profiles", []))
        ]

    async def save_auth_profile(self, session_id: str, profile_name: str) -> AuthProfile:
        data = await self._request(
            "POST", f"/sessions/{session_id}/auth-profiles", {"profile_name": profile_name}
        )
        return AuthProfile(name=data.get("name", profile_name), created_at=data.get("created_at"))

    # ── Approvals ────────────────────────────────────────────────────────────

    async def list_approvals(
        self,
        *,
        status: ApprovalStatus | None = None,
        session_id: str | None = None,
    ) -> list[ApprovalItem]:
        params: dict[str, Any] = {}
        if status:
            params["status"] = str(status)
        if session_id:
            params["session_id"] = session_id
        data = await self._request("GET", "/approvals", params=params)
        return [self._parse_approval(a) for a in (data if isinstance(data, list) else data.get("approvals", []))]

    async def approve(self, approval_id: str, comment: str | None = None) -> ApprovalItem:
        data = await self._request(
            "POST", f"/approvals/{approval_id}/approve", {"comment": comment}
        )
        return self._parse_approval(data)

    async def reject(self, approval_id: str, comment: str | None = None) -> ApprovalItem:
        data = await self._request(
            "POST", f"/approvals/{approval_id}/reject", {"comment": comment}
        )
        return self._parse_approval(data)

    @staticmethod
    def _parse_approval(data: dict) -> ApprovalItem:
        return ApprovalItem(
            id=data.get("id") or data.get("approval_id") or "",
            status=ApprovalStatus(data.get("status", "pending")),
            action_type=data.get("action_type"),
            session_id=data.get("session_id"),
            requested_at=data.get("requested_at"),
            resolved_at=data.get("resolved_at"),
            comment=data.get("comment"),
        )

    # ── Audit ─────────────────────────────────────────────────────────────────

    async def list_audit_events(
        self,
        *,
        limit: int = 50,
        session_id: str | None = None,
    ) -> list[AuditEvent]:
        params: dict[str, Any] = {"limit": limit}
        if session_id:
            params["session_id"] = session_id
        data = await self._request("GET", "/audit/events", params=params)
        return [self._parse_audit_event(e) for e in (data if isinstance(data, list) else data.get("events", []))]

    @staticmethod
    def _parse_audit_event(data: dict) -> AuditEvent:
        return AuditEvent(
            id=data.get("id") or data.get("event_id") or "",
            event_type=data.get("event_type", ""),
            session_id=data.get("session_id"),
            operator_id=data.get("operator_id"),
            timestamp=data.get("timestamp", ""),
            payload=data.get("payload") or data,
        )

    # ── Network inspection ──────────────────────────────────────────────────

    async def get_network_log(
        self,
        session_id: str,
        *,
        limit: int = 100,
        method: str | None = None,
        url_contains: str | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if method:
            params["method"] = method.upper()
        if url_contains:
            params["url_contains"] = url_contains
        data = await self._request("GET", f"/sessions/{session_id}/network-log", params=params)
        return data if isinstance(data, list) else data.get("entries", [])

    # ── Agent / orchestration ─────────────────────────────────────────────────

    async def agent_step(
        self,
        session_id: str,
        *,
        provider: Literal["openai", "claude", "gemini"] = "openai",
        goal: str,
        **kwargs: Any,
    ) -> dict:
        return await self._request(
            "POST",
            f"/sessions/{session_id}/agent/step",
            {"provider": provider, "goal": goal, **kwargs},
        )

    async def agent_run(
        self,
        session_id: str,
        *,
        provider: Literal["openai", "claude", "gemini"] = "openai",
        goal: str,
        max_steps: int = 6,
        **kwargs: Any,
    ) -> dict:
        return await self._request(
            "POST",
            f"/sessions/{session_id}/agent/run",
            {"provider": provider, "goal": goal, "max_steps": max_steps, **kwargs},
        )

    # ── Cron / webhooks ─────────────────────────────────────────────────────

    async def list_cron_jobs(self) -> list[dict]:
        return await self._request("GET", "/crons")

    async def create_cron_job(self, payload: dict) -> dict:
        return await self._request("POST", "/crons", payload)

    async def delete_cron_job(self, job_id: str) -> dict:
        return await self._request("DELETE", f"/crons/{job_id}")

    async def trigger_cron_job(self, job_id: str, webhook_key: str | None = None) -> dict:
        body: dict[str, Any] = {}
        if webhook_key:
            body["webhook_key"] = webhook_key
        return await self._request("POST", f"/crons/{job_id}/trigger", body)

    # ── MCP tool-call passthrough ─────────────────────────────────────────────

    async def mcp_tool_call(self, name: str, arguments: dict[str, Any]) -> dict:
        """
        Call an arbitrary MCP tool by name via the convenience endpoint.
        This is useful for accessing newer or less-common tools without waiting
        for explicit bridge methods.
        """
        return await self._request(
            "POST", "/mcp/tools/call", {"name": name, "arguments": arguments}
        )

    async def list_mcp_tools(self) -> list[dict]:
        """Discover available MCP tools and their schemas."""
        data = await self._request("GET", "/mcp/tools")
        return data if isinstance(data, list) else data.get("tools", [])

    # ── SSE event stream ────────────────────────────────────────────────────

    async def stream_events(self, session_id: str) -> AsyncGenerator[dict, None]:
        """Yield parsed SSE event dicts for a session."""
        client = await self._ensure_client()
        url = f"{self.base_url}/sessions/{session_id}/events"
        async with client.stream("GET", url, timeout=None) as response:
            response.raise_for_status()
            buffer = ""
            async for chunk in response.aiter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    block, buffer = buffer.split("\n\n", 1)
                    for line in block.splitlines():
                        if line.startswith("data: "):
                            payload = line[6:]
                            try:
                                yield json.loads(payload)
                            except json.JSONDecodeError:
                                logger.debug("auto-browser SSE non-JSON payload: %s", payload)

    # ── Share / observer tokens ──────────────────────────────────────────────

    async def share_session(self, session_id: str, ttl_minutes: int = 60) -> dict:
        return await self._request(
            "POST", f"/sessions/{session_id}/share", {"ttl_minutes": ttl_minutes}
        )

    # ── Memory profiles (v0.7.0+) ────────────────────────────────────────────

    async def save_memory_profile(
        self,
        session_id: str,
        profile_name: str,
        *,
        goal_summary: str = "",
        completed_steps: list[str] | None = None,
        discovered_selectors: dict[str, str] | None = None,
        notes: list[str] | None = None,
    ) -> dict:
        body: dict[str, Any] = {"profile_name": profile_name}
        if goal_summary:
            body["goal_summary"] = goal_summary
        if completed_steps:
            body["completed_steps"] = completed_steps
        if discovered_selectors:
            body["discovered_selectors"] = discovered_selectors
        if notes:
            body["notes"] = notes
        return await self.mcp_tool_call("browser.save_memory_profile", body)

    async def get_memory_profile(self, profile_name: str) -> dict:
        return await self.mcp_tool_call("browser.get_memory_profile", {"profile_name": profile_name})

    async def list_memory_profiles(self) -> list[dict]:
        return await self.mcp_tool_call("browser.list_memory_profiles", {})

    async def delete_memory_profile(self, profile_name: str) -> dict:
        return await self.mcp_tool_call("browser.delete_memory_profile", {"profile_name": profile_name})

    # ── Vision targeting (v0.5.0+) ───────────────────────────────────────────

    async def find_by_vision(
        self,
        session_id: str,
        description: str,
        take_screenshot: bool = True,
    ) -> dict:
        return await self.mcp_tool_call(
            "browser.find_by_vision",
            {"session_id": session_id, "description": description, "take_screenshot": take_screenshot},
        )


# ---------------------------------------------------------------------------
# High-level agency helpers
# ---------------------------------------------------------------------------

class BrowserAgent:
    """
    Opinionated high-level wrapper around AutoBrowserBridge for agency runtime use.

    Maintains a single active session, provides a simple Observe -> Decide -> Act loop,
    and tracks action history.
    """

    def __init__(self, bridge: AutoBrowserBridge):
        self.bridge = bridge
        self._session_id: str | None = None
        self._history: list[dict] = []

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def history(self) -> list[dict]:
        return list(self._history)

    async def start(
        self,
        *,
        name: str | None = None,
        start_url: str | None = None,
        auth_profile: str | None = None,
    ) -> SessionInfo:
        sess = await self.bridge.create_session(
            name=name, start_url=start_url, auth_profile=auth_profile
        )
        self._session_id = sess.id
        self._history.clear()
        return sess

    async def stop(self) -> None:
        if self._session_id:
            try:
                await self.bridge.close_session(self._session_id)
            except Exception as exc:
                logger.warning("BrowserAgent stop error: %s", exc)
            finally:
                self._session_id = None

    async def observe(self, preset: PerceptionPreset = PerceptionPreset.NORMAL) -> Observation:
        if not self._session_id:
            raise SessionError("No active session. Call start() first.")
        return await self.bridge.observe(self._session_id, preset=preset)

    async def act(self, action: Callable[..., Any], *args: Any, **kwargs: Any) -> ActionResult:
        """Execute a bridge action and append to history."""
        if not self._session_id:
            raise SessionError("No active session. Call start() first.")
        result = await action(self._session_id, *args, **kwargs)
        self._history.append({
            "action": action.__name__,
            "args": args,
            "kwargs": {k: v for k, v in kwargs.items() if k not in ("password", "totp_secret")},
            "result": result,
        })
        return result

    async def safe_navigate(self, url: str) -> ActionResult:
        """Navigate with a wait for load."""
        result = await self.act(self.bridge.navigate, url=url)
        await self.bridge.wait(self._session_id or "", milliseconds=500)
        return result

    async def safe_click_and_wait(
        self,
        *,
        selector: str | None = None,
        element_id: str | None = None,
        wait_ms: int = 500,
    ) -> ActionResult:
        result = await self.act(self.bridge.click, selector=selector, element_id=element_id)
        await self.bridge.wait(self._session_id or "", milliseconds=wait_ms)
        return result

    async def fill_form(
        self,
        fields: list[tuple[str, str]],
        *,
        submit_selector: str | None = None,
        clear_first: bool = True,
    ) -> list[ActionResult]:
        """Fill a sequence of (selector, value) pairs and optionally submit."""
        results: list[ActionResult] = []
        for selector, value in fields:
            r = await self.act(
                self.bridge.type_text,
                text=value,
                selector=selector,
                clear_first=clear_first,
            )
            results.append(r)
        if submit_selector:
            r = await self.act(self.bridge.click, selector=submit_selector)
            results.append(r)
        return results

    async def export_script(self) -> str:
        """Export the current session's recorded actions as a Playwright Python script."""
        if not self._session_id:
            raise SessionError("No active session.")
        data = await self.bridge._request("GET", f"/sessions/{self._session_id}/export-script")
        return data.get("script") or data.get("content", "")

    async def takeover_url(self) -> str | None:
        """Return the noVNC URL for human takeover, if available."""
        if not self._session_id:
            return None
        sess = await self.bridge.get_session(self._session_id)
        return sess.vnc_url


# ---------------------------------------------------------------------------
# Registry / factory helpers for agency runtime
# ---------------------------------------------------------------------------

_BRIDGE_INSTANCES: dict[str, AutoBrowserBridge] = {}


def get_bridge(name: str = "default", **kwargs: Any) -> AutoBrowserBridge:
    """Get or create a named bridge instance (singleton per name)."""
    if name not in _BRIDGE_INSTANCES:
        _BRIDGE_INSTANCES[name] = AutoBrowserBridge(**kwargs)
    return _BRIDGE_INSTANCES[name]


async def close_all_bridges() -> None:
    """Clean up all registered bridge instances."""
    for name, bridge in list(_BRIDGE_INSTANCES.items()):
        try:
            await bridge.close()
        except Exception as exc:
            logger.warning("Error closing bridge %s: %s", name, exc)
    _BRIDGE_INSTANCES.clear()


# ---------------------------------------------------------------------------
# CLI smoke test (optional)
# ---------------------------------------------------------------------------

async def _smoke() -> None:
    logging.basicConfig(level=logging.INFO)
    async with AutoBrowserBridge() as bridge:
        health = await bridge.health()
        print("Health:", health)
        async with bridge.session(start_url="https://example.com") as sess:
            print("Session:", sess)
            obs = await bridge.observe(sess.id, preset=PerceptionPreset.FAST)
            print("Title:", obs.title, "URL:", obs.url)
            result = await bridge.click(sess.id, selector="a")
            print("Click result:", result.success, result.after_url)


if __name__ == "__main__":
    asyncio.run(_smoke())
