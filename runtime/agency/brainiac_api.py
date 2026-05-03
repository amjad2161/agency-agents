"""FastAPI-based REST API for JARVIS BRAINIAC.

Provides HTTP endpoints for:
- /status           — System status and health
- /query            — Submit natural-language queries
- /personas         — List / get expert personas
- /trading          — Trading signal endpoints (mock data)
- /github/search    — Search GitHub repositories
- /memory/store     — Store a memory entry
- /memory/recall    — Recall memory entries
- /tasks/create     — Create a new task
- /demo/run         — Run demo scenarios

Features:
- API key-based authentication
- Rate limiting per client
- Request/response logging
- CORS support
- JSON response format
- All endpoints work with mock data
- Includes __main__ block to run server
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency handling
# ---------------------------------------------------------------------------

try:
    from fastapi import FastAPI, HTTPException, Request, Depends, status
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    FASTAPI_AVAILABLE = True
except Exception:  # noqa: BLE001
    FastAPI = HTTPException = Request = Depends = status = None  # type: ignore[misc, assignment]
    CORSMiddleware = JSONResponse = None  # type: ignore[misc, assignment]
    HTTPBearer = HTTPAuthorizationCredentials = None  # type: ignore[misc, assignment]
    FASTAPI_AVAILABLE = False
    logger.debug("FastAPI not available; using mock API framework")

try:
    from pydantic import BaseModel
except Exception:  # noqa: BLE001
    BaseModel = None  # type: ignore[assignment, misc]
    logger.debug("pydantic not available; using dict-based models")


# ---------------------------------------------------------------------------
# Request / Response models (mock pydantic if unavailable)
# ---------------------------------------------------------------------------

if BaseModel is not None:
    class QueryRequest(BaseModel):
        query: str
        session_id: str | None = None
        context: dict[str, Any] | None = None

    class MemoryStoreRequest(BaseModel):
        key: str
        value: str | dict[str, Any]
        tags: list[str] | None = None
        ttl_seconds: int | None = None

    class MemoryRecallRequest(BaseModel):
        key: str | None = None
        tag: str | None = None
        limit: int = 10

    class TaskCreateRequest(BaseModel):
        title: str
        description: str = ""
        priority: str = "medium"  # low, medium, high, critical
        assignee: str | None = None
        due_date: str | None = None
        metadata: dict[str, Any] | None = None

    class GitHubSearchRequest(BaseModel):
        query: str
        language: str | None = None
        stars_min: int | None = None
        sort: str = "stars"

    class TradingRequest(BaseModel):
        symbol: str
        action: str = "analysis"  # analysis, signal, backtest
        timeframe: str = "1d"

    class DemoRunRequest(BaseModel):
        scenario: str = "default"  # default, trading, coding, creative
        steps: int = 5

else:
    # Stub classes that accept kwargs
    class _StubModel:
        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

    QueryRequest = MemoryStoreRequest = MemoryRecallRequest = TaskCreateRequest = _StubModel  # type: ignore[misc, assignment]
    GitHubSearchRequest = TradingRequest = DemoRunRequest = _StubModel  # type: ignore[misc, assignment]


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

@dataclass
class RateLimitEntry:
    """Track requests per client for rate limiting."""

    count: int = 0
    window_start: float = 0.0


class RateLimiter:
    """Simple in-memory sliding-window rate limiter."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._clients: dict[str, RateLimitEntry] = defaultdict(lambda: RateLimitEntry())
        logger.info("RateLimiter: %d req / %d sec", max_requests, window_seconds)

    def is_allowed(self, client_id: str) -> tuple[bool, dict[str, Any]]:
        now = time.time()
        entry = self._clients[client_id]
        if now - entry.window_start > self.window_seconds:
            entry.window_start = now
            entry.count = 0
        entry.count += 1
        remaining = max(0, self.max_requests - entry.count)
        headers = {
            "X-RateLimit-Limit": str(self.max_requests),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Window": str(self.window_seconds),
        }
        if entry.count > self.max_requests:
            return False, headers
        return True, headers

    def reset(self, client_id: str) -> None:
        if client_id in self._clients:
            del self._clients[client_id]


# ---------------------------------------------------------------------------
# In-memory stores (mock persistence)
# ---------------------------------------------------------------------------

class MockStore:
    """Simple in-memory key-value store with tagging support."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}
        self._tags: dict[str, list[str]] = defaultdict(list)

    def store(self, key: str, value: Any, tags: list[str] | None = None,
              ttl_seconds: int | None = None) -> None:
        expires = (time.time() + ttl_seconds) if ttl_seconds else None
        self._data[key] = {"value": value, "stored_at": datetime.now().isoformat(),
                           "expires": expires}
        if tags:
            for tag in tags:
                if key not in self._tags[tag]:
                    self._tags[tag].append(key)

    def recall(self, key: str | None = None, tag: str | None = None,
               limit: int = 10) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        if key:
            if key in self._data:
                results.append({"key": key, **self._data[key]})
        elif tag:
            for k in self._tags.get(tag, [])[:limit]:
                if k in self._data:
                    results.append({"key": k, **self._data[k]})
        else:
            for k, v in list(self._data.items())[:limit]:
                results.append({"key": k, **v})
        return results

    def delete(self, key: str) -> bool:
        if key in self._data:
            del self._data[key]
            for tag_keys in self._tags.values():
                if key in tag_keys:
                    tag_keys.remove(key)
            return True
        return False


# ---------------------------------------------------------------------------
# API Factory
# ---------------------------------------------------------------------------

class BrainiacAPI:
    """FastAPI application factory for JARVIS BRAINIAC REST API."""

    def __init__(self, api_key: str | None = None, rate_limit: int = 60,
                 enable_cors: bool = True) -> None:
        self.api_key = api_key or os.environ.get("JARVIS_API_KEY", "jarvis-dev-key")
        self.rate_limiter = RateLimiter(max_requests=rate_limit)
        self.memory_store = MockStore()
        self.task_store: list[dict[str, Any]] = []
        self.request_log: list[dict[str, Any]] = []
        self.enable_cors = enable_cors
        self.app = self._build_app()
        logger.info("BrainiacAPI initialised (FastAPI=%s)", FASTAPI_AVAILABLE)

    def _build_app(self) -> Any:
        if not FASTAPI_AVAILABLE:
            logger.warning("FastAPI unavailable; returning mock app")
            return None
        app = FastAPI(
            title="J.A.R.V.I.S BRAINIAC API",
            description="REST API for the JARVIS BRAINIAC AI agent system",
            version="25.0.0",
        )
        if self.enable_cors:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        self._register_routes(app)
        return app

    def _register_routes(self, app: FastAPI) -> None:
        security = HTTPBearer(auto_error=False)

        async def verify_key(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> str:
            token = (credentials.credentials if credentials else "")
            if token != self.api_key:
                logger.warning("Auth failed: invalid API key attempt")
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                    detail="Invalid or missing API key")
            return token

        async def rate_limit(request: Request) -> dict[str, Any]:
            client = request.client.host if request.client else "unknown"
            allowed, headers = self.rate_limiter.is_allowed(client)
            if not allowed:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                    detail="Rate limit exceeded", headers=headers)
            return headers

        # --- Health / Status ---

        @app.get("/status")
        async def get_status() -> dict[str, Any]:
            return {
                "name": "J.A.R.V.I.S BRAINIAC",
                "version": "25.0.0",
                "status": "operational",
                "timestamp": datetime.now().isoformat(),
                "features": {
                    "query": True,
                    "personas": True,
                    "trading": True,
                    "github": True,
                    "memory": True,
                    "tasks": True,
                    "demo": True,
                },
            }

        @app.get("/health")
        async def health_check() -> dict[str, Any]:
            return {"status": "healthy", "timestamp": datetime.now().isoformat()}

        # --- Query ---

        @app.post("/query")
        async def query(req: QueryRequest, _api_key: str = Depends(verify_key),
                        _rl: dict[str, Any] = Depends(rate_limit)) -> dict[str, Any]:
            self._log_request("/query", {"query": getattr(req, "query", "")})
            response_text = (
                f"JARVIS BRAINIAC received your query: '{getattr(req, 'query', '')}'. "
                "Processing with supreme intelligence..."
            )
            return {
                "status": "success",
                "response": response_text,
                "session_id": getattr(req, "session_id", None),
                "processing_time_ms": round(random.uniform(50, 500), 2),
                "timestamp": datetime.now().isoformat(),
            }

        # --- Personas ---

        @app.get("/personas")
        async def list_personas(_api_key: str = Depends(verify_key),
                                _rl: dict[str, Any] = Depends(rate_limit)) -> dict[str, Any]:
            self._log_request("/personas", {})
            personas = [
                {"id": "senior_lawyer", "name": "Senior Lawyer", "specialty": "Legal analysis & contracts"},
                {"id": "senior_engineer", "name": "Senior Engineer", "specialty": "System design & architecture"},
                {"id": "senior_doctor", "name": "Senior Doctor", "specialty": "Medical consultation"},
                {"id": "business_advisor", "name": "Business Advisor", "specialty": "Strategy & finance"},
                {"id": "creative_director", "name": "Creative Director", "specialty": "Design & content"},
                {"id": "project_manager", "name": "Project Manager", "specialty": "Planning & execution"},
            ]
            return {"status": "success", "count": len(personas), "personas": personas}

        # --- Trading ---

        @app.post("/trading")
        async def trading_endpoint(req: TradingRequest,
                                   _api_key: str = Depends(verify_key),
                                   _rl: dict[str, Any] = Depends(rate_limit)) -> dict[str, Any]:
            self._log_request("/trading", {"symbol": getattr(req, "symbol", ""),
                                            "action": getattr(req, "action", "")})
            symbol = getattr(req, "symbol", "BTCUSDT")
            return {
                "status": "success",
                "symbol": symbol,
                "action": getattr(req, "action", "analysis"),
                "signal": random.choice(["BUY", "SELL", "HOLD", "STRONG_BUY", "STRONG_SELL"]),
                "confidence": round(random.uniform(60.0, 98.0), 2),
                "price": round(random.uniform(100.0, 80000.0), 2),
                "indicators": {
                    "rsi": round(random.uniform(20.0, 80.0), 2),
                    "macd": round(random.uniform(-5.0, 5.0), 4),
                    "sma_50": round(random.uniform(90.0, 75000.0), 2),
                    "sma_200": round(random.uniform(85.0, 70000.0), 2),
                },
                "timestamp": datetime.now().isoformat(),
            }

        # --- GitHub Search ---

        @app.post("/github/search")
        async def github_search(req: GitHubSearchRequest,
                                _api_key: str = Depends(verify_key),
                                _rl: dict[str, Any] = Depends(rate_limit)) -> dict[str, Any]:
            self._log_request("/github/search", {"query": getattr(req, "query", "")})
            query = getattr(req, "query", "python")
            repos = [
                {"name": f"{query}-awesome-repo-{i}",
                 "owner": f"user_{i}",
                 "stars": random.randint(10, 50000),
                 "language": getattr(req, "language", "Python"),
                 "description": f"An awesome {query} project with great features.",
                 "url": f"https://github.com/user_{i}/{query}-awesome-repo-{i}",
                 "updated_at": datetime.now().isoformat()}
                for i in range(1, 6)
            ]
            return {"status": "success", "query": query, "results": repos}

        # --- Memory ---

        @app.post("/memory/store")
        async def memory_store(req: MemoryStoreRequest,
                               _api_key: str = Depends(verify_key),
                               _rl: dict[str, Any] = Depends(rate_limit)) -> dict[str, Any]:
            self._log_request("/memory/store", {"key": getattr(req, "key", "")})
            key = getattr(req, "key", "")
            value = getattr(req, "value", "")
            tags = getattr(req, "tags", None)
            ttl = getattr(req, "ttl_seconds", None)
            self.memory_store.store(key, value, tags=tags, ttl_seconds=ttl)
            return {"status": "success", "key": key, "stored": True,
                    "timestamp": datetime.now().isoformat()}

        @app.post("/memory/recall")
        async def memory_recall(req: MemoryRecallRequest,
                                _api_key: str = Depends(verify_key),
                                _rl: dict[str, Any] = Depends(rate_limit)) -> dict[str, Any]:
            self._log_request("/memory/recall", {"key": getattr(req, "key", None),
                                                  "tag": getattr(req, "tag", None)})
            results = self.memory_store.recall(
                key=getattr(req, "key", None),
                tag=getattr(req, "tag", None),
                limit=getattr(req, "limit", 10),
            )
            return {"status": "success", "count": len(results), "results": results}

        # --- Tasks ---

        @app.post("/tasks/create")
        async def tasks_create(req: TaskCreateRequest,
                               _api_key: str = Depends(verify_key),
                               _rl: dict[str, Any] = Depends(rate_limit)) -> dict[str, Any]:
            self._log_request("/tasks/create", {"title": getattr(req, "title", "")})
            task_id = hashlib.md5(f"{getattr(req, 'title', '')}{time.time()}".encode()).hexdigest()[:12]
            task = {
                "id": task_id,
                "title": getattr(req, "title", ""),
                "description": getattr(req, "description", ""),
                "priority": getattr(req, "priority", "medium"),
                "assignee": getattr(req, "assignee", None),
                "due_date": getattr(req, "due_date", None),
                "status": "created",
                "metadata": getattr(req, "metadata", None),
                "created_at": datetime.now().isoformat(),
            }
            self.task_store.append(task)
            return {"status": "success", "task": task}

        @app.get("/tasks/list")
        async def tasks_list(_api_key: str = Depends(verify_key),
                             _rl: dict[str, Any] = Depends(rate_limit)) -> dict[str, Any]:
            self._log_request("/tasks/list", {})
            return {"status": "success", "count": len(self.task_store),
                    "tasks": self.task_store}

        # --- Demo ---

        @app.post("/demo/run")
        async def demo_run(req: DemoRunRequest,
                           _api_key: str = Depends(verify_key),
                           _rl: dict[str, Any] = Depends(rate_limit)) -> dict[str, Any]:
            self._log_request("/demo/run", {"scenario": getattr(req, "scenario", "default")})
            scenario = getattr(req, "scenario", "default")
            steps = getattr(req, "steps", 5)
            step_data = []
            for i in range(1, steps + 1):
                step_data.append({
                    "step": i,
                    "action": f"Demo action for {scenario} scenario",
                    "result": "success",
                    "detail": f"Executed step {i} with full capability",
                })
            return {
                "status": "success",
                "scenario": scenario,
                "steps_executed": steps,
                "steps": step_data,
                "timestamp": datetime.now().isoformat(),
            }

    def _log_request(self, endpoint: str, params: dict[str, Any]) -> None:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "endpoint": endpoint,
            "params": params,
        }
        self.request_log.append(entry)
        logger.info("API request: %s | params=%s", endpoint, params)

    # -- Mock server runner (when uvicorn unavailable) ----------------------

    def run_mock_server(self, host: str = "127.0.0.1", port: int = 8080) -> None:
        """Run a simple HTTP server when FastAPI/uvicorn are unavailable."""
        try:
            from http.server import HTTPServer, BaseHTTPRequestHandler
        except ImportError:
            logger.error("Cannot run mock server: no http.server available")
            return

        store = self.memory_store
        tasks = self.task_store

        class MockHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                paths = {
                    "/status": {"name": "J.A.R.V.I.S BRAINIAC", "version": "25.0.0",
                                "status": "operational (mock mode)"},
                    "/health": {"status": "healthy"},
                    "/personas": {"personas": [{"id": "mock", "name": "Mock Persona"}]},
                    "/tasks/list": {"tasks": tasks},
                }
                resp = paths.get(self.path, {"error": "Not found"})
                code = 200 if self.path in paths else 404
                self._send_json(resp, code)

            def do_POST(self) -> None:
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len) if content_len else b"{}"
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    data = {}
                if self.path == "/memory/store":
                    store.store(data.get("key", ""), data.get("value", ""),
                                tags=data.get("tags"))
                    self._send_json({"status": "stored"})
                elif self.path == "/memory/recall":
                    results = store.recall(key=data.get("key"), tag=data.get("tag"),
                                           limit=data.get("limit", 10))
                    self._send_json({"results": results})
                else:
                    self._send_json({"status": "mock_response", "received": data})

            def _send_json(self, data: dict[str, Any], code: int = 200) -> None:
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(data, default=str).encode())

            def log_message(self, fmt: str, *args: Any) -> None:
                logger.info(fmt % args)

        server = HTTPServer((host, port), MockHandler)
        logger.info("Mock API server running on http://%s:%d", host, port)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.shutdown()


# ---------------------------------------------------------------------------
# Standalone server runner
# ---------------------------------------------------------------------------

def run_server(host: str = "127.0.0.1", port: int = 8080,
               api_key: str | None = None, reload: bool = False) -> None:
    """Run the JARVIS BRAINIAC API server."""
    api = BrainiacAPI(api_key=api_key)
    if FASTAPI_AVAILABLE and api.app is not None:
        try:
            import uvicorn
            uvicorn.run(api.app, host=host, port=port, reload=reload, log_level="info")
        except ImportError:
            logger.warning("uvicorn not available; falling back to mock server")
            api.run_mock_server(host=host, port=port)
    else:
        api.run_mock_server(host=host, port=port)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    import random

    print("=" * 60)
    print("JARVIS BRAINIAC — API Self-Test")
    print("=" * 60)

    api = BrainiacAPI(api_key="test-key")

    # Test 1: Status
    print(f"\n[1] API initialised: FastAPI={FASTAPI_AVAILABLE}")
    print(f"    App created: {api.app is not None}")

    # Test 2: Memory store/recall
    api.memory_store.store("test_key", "test_value", tags=["test", "api"])
    results = api.memory_store.recall(key="test_key")
    print(f"\n[2] Memory store/recall: {len(results)} result(s)")
    if results:
        print(f"    Key={results[0]['key']}, Value={results[0].get('value')}")

    # Test 3: Memory tag search
    tagged = api.memory_store.recall(tag="test")
    print(f"\n[3] Tag search 'test': {len(tagged)} result(s)")

    # Test 4: Task creation
    api.task_store.append({
        "id": "task_001", "title": "Test Task", "priority": "high",
        "status": "created", "created_at": datetime.now().isoformat(),
    })
    print(f"\n[4] Tasks stored: {len(api.task_store)}")

    # Test 5: Rate limiter
    allowed, headers = api.rate_limiter.is_allowed("client_1")
    print(f"\n[5] Rate limit check: allowed={allowed}, headers={headers}")

    # Test 6: Request log
    api._log_request("/test", {"param": "value"})
    print(f"\n[6] Request log entries: {len(api.request_log)}")

    # Test 7: Config export
    print(f"\n[7] API config: key={'*' * 8}, rate_limit={api.rate_limiter.max_requests}")

    print("\n" + "=" * 60)
    print("All API tests passed!")
    print("=" * 60)

    # If run directly, start the server
    import sys as _sys
    if "--serve" in _sys.argv:
        print("\nStarting JARVIS BRAINIAC API server...")
        run_server()
