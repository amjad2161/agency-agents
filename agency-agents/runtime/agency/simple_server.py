"""Simple Flask-based REST API for the Agency runtime.

Provides a minimal surface for programmatic access:
  GET  /health          {"status": "ok", "version": "..."}
  GET  /skills          {"skills": [...]}
  GET  /stats           token usage stats
  POST /chat            {"prompt": "...", "model": "...", "stream": false}
                     -> {"response": "..."}

Auth: if AGENCY_API_TOKEN env var is set, every request must carry
  Authorization: Bearer <token>

Start via CLI: agency serve [--port 8080] [--host 0.0.0.0]
or programmatically: run_server(host, port)
"""

from __future__ import annotations

import os
import signal
import threading
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, Response

from . import __version__
from .stats import get_stats
from .skills import SkillRegistry, discover_repo_root


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(repo: Path | None = None) -> Flask:
    """Create and return a configured Flask application."""
    root = repo if repo else discover_repo_root()
    registry = SkillRegistry.load(root)

    app = Flask(__name__)
    app.config["REGISTRY"] = registry

    # ------------------------------------------------------------------
    # Auth middleware
    # ------------------------------------------------------------------

    def _check_auth() -> Response | None:
        """Return 401 Response if token check fails, else None."""
        expected = os.environ.get("AGENCY_API_TOKEN", "").strip()
        if not expected:
            return None  # auth disabled
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "missing or malformed Authorization header"}), 401  # type: ignore[return-value]
        token = auth_header[len("Bearer "):]
        if token != expected:
            return jsonify({"error": "invalid token"}), 401  # type: ignore[return-value]
        return None

    @app.before_request
    def auth_middleware() -> Response | None:
        return _check_auth()

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.get("/health")
    def health() -> tuple[Any, int]:
        return jsonify({"status": "ok", "version": __version__}), 200

    @app.get("/skills")
    def skills_list() -> tuple[Any, int]:
        skills = [
            {
                "slug": s.slug,
                "name": s.name,
                "category": s.category,
                "description": s.description,
                "emoji": getattr(s, "emoji", ""),
            }
            for s in registry.all()
        ]
        return jsonify({"count": len(skills), "skills": skills}), 200

    @app.get("/stats")
    def stats_endpoint() -> tuple[Any, int]:
        return jsonify(get_stats()), 200

    @app.post("/chat")
    def chat_endpoint() -> tuple[Any, int]:
        body = request.get_json(silent=True) or {}
        prompt = (body.get("prompt") or "").strip()
        if not prompt:
            return jsonify({"error": "prompt is required"}), 400

        model = body.get("model") or os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")
        stream = body.get("stream", False)

        # Attempt to use the real LLM if an API key is configured.
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            return jsonify({"error": "ANTHROPIC_API_KEY not configured"}), 503

        try:
            from .llm import AnthropicLLM, LLMConfig, LLMError
            cfg = LLMConfig.from_env()
            if model:
                cfg = LLMConfig(
                    model=model,
                    planner_model=cfg.planner_model,
                    max_tokens=cfg.max_tokens,
                    task_budget_tokens=cfg.task_budget_tokens,
                    enable_web_search=cfg.enable_web_search,
                    enable_code_execution=cfg.enable_code_execution,
                    mcp_servers=cfg.mcp_servers,
                )
            llm = AnthropicLLM(cfg)
            messages = [{"role": "user", "content": prompt}]
            response_text = llm.complete(messages)
            return jsonify({"response": response_text, "model": model}), 200
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 500

    return app


# ---------------------------------------------------------------------------
# Server runner with graceful shutdown
# ---------------------------------------------------------------------------

def run_server(host: str = "127.0.0.1", port: int = 8080, repo: Path | None = None) -> None:
    """Start the Flask development server with SIGTERM / SIGINT graceful shutdown.

    In production, use a WSGI server (gunicorn, waitress) instead.
    """
    app = create_app(repo=repo)
    _shutdown_event = threading.Event()

    def _handle_signal(signum: int, frame: Any) -> None:  # noqa: ARG001
        print("\n⏹  Shutting down Agency server…", flush=True)
        _shutdown_event.set()
        # Flask dev server doesn't have a clean stop API; os._exit is the
        # accepted workaround for signal-driven shutdown.
        os._exit(0)  # noqa: SLF001

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    print(f"🚀  Agency REST server listening on http://{host}:{port}", flush=True)
    app.run(host=host, port=port, debug=False, use_reloader=False)
