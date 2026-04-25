"""FastAPI server with a minimal chat UI for the agency runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import json

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from . import __version__
from .diagnostics import optional_deps_status
from .executor import Executor
from .llm import AnthropicLLM, LLMConfig, LLMError
from .memory import MemoryStore, Session
from .planner import Planner
from .skills import SkillRegistry, discover_repo_root
from .spatial import spatial_ws_handler


class RunRequest(BaseModel):
    message: str
    skill: str | None = None
    session_id: str | None = None


class PlanRequestBody(BaseModel):
    message: str


def build_app(repo: Path | None = None) -> FastAPI:
    root = repo if repo else discover_repo_root()
    registry = SkillRegistry.load(root)
    memory = MemoryStore(Path.home() / ".agency" / "sessions")

    app = FastAPI(title="Agency Runtime", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _CHAT_HTML

    @app.get("/api/version")
    def version_endpoint() -> dict[str, str]:
        return {"name": "agency-runtime", "version": __version__}

    import os as _os
    health_disabled = (_os.environ.get("AGENCY_DISABLE_HEALTH", "").strip().lower()
                       in ("1", "true", "yes", "on"))
    if not health_disabled:
        @app.get("/api/health")
        def health_endpoint() -> dict[str, Any]:
            """Liveness + diagnostic snapshot.

            Always responds 200 with a JSON body — k8s readiness probes can
            key on `status="ok"` for healthy and `status="error"` if any
            diagnostic step blew up. Body includes enough to debug "why
            isn't it working" without shelling in.

            Note: this endpoint reveals model defaults, feature-flag state,
            and whether an API key is configured. The CLI binds to
            127.0.0.1 by default so it's local-only out of the box; if you
            bind 0.0.0.0 on an untrusted network, set
            `AGENCY_DISABLE_HEALTH=1` to turn this off, or front the
            server with auth.
            """
            try:
                cfg = LLMConfig.from_env()
                return {
                    "status": "ok",
                    "version": __version__,
                    "skills": {
                        "count": len(registry),
                        "categories": registry.categories(),
                    },
                    "models": {
                        "execution": cfg.model,
                        "planner": cfg.planner_model,
                    },
                    "api_key_set": bool(_os.environ.get("ANTHROPIC_API_KEY")),
                    "features": {
                        "web_search": cfg.enable_web_search,
                        "code_execution": cfg.enable_code_execution,
                        "computer_use": (_os.environ.get("AGENCY_ENABLE_COMPUTER_USE", "")
                                         .strip().lower() in ("1", "true", "yes", "on")),
                        "task_budget_tokens": cfg.task_budget_tokens,
                        "mcp_servers": len(cfg.mcp_servers),
                        "shell_allowed": (_os.environ.get("AGENCY_ALLOW_SHELL", "")
                                          .strip().lower() in ("1", "true", "yes", "on")),
                    },
                    "optional_deps": optional_deps_status(),
                }
            except Exception as e:  # noqa: BLE001 — true always-200 contract
                return {
                    "status": "error",
                    "error": f"{type(e).__name__}: {e}",
                    "version": __version__,
                }

    @app.get("/spatial", response_class=HTMLResponse)
    def spatial_index() -> str:
        """Serve the webcam-driven 3D holographic HUD."""
        html_path = Path(__file__).parent / "static" / "spatial.html"
        return html_path.read_text(encoding="utf-8")

    @app.websocket("/ws/spatial")
    async def spatial_ws(ws: WebSocket) -> None:
        """Bidirectional WebSocket for the spatial HUD.

        Accepts a closed set of typed events (hello / gesture / run /
        hologram_action / ping). Anything else is rejected.
        See `agency.spatial` for the full protocol.
        """
        await spatial_ws_handler(
            ws, registry=registry, memory=memory, llm_factory=_require_llm,
        )

    @app.get("/api/skills")
    def list_skills() -> dict[str, Any]:
        return {
            "count": len(registry),
            "skills": [
                {
                    "slug": s.slug,
                    "name": s.name,
                    "category": s.category,
                    "description": s.description,
                    "emoji": s.emoji,
                }
                for s in registry.all()
            ],
        }

    @app.post("/api/plan")
    def plan_endpoint(body: PlanRequestBody) -> dict[str, Any]:
        llm = _maybe_llm()
        planner = Planner(registry, llm=llm)
        plan = planner.plan(body.message)
        return {
            "skill": {"slug": plan.skill.slug, "name": plan.skill.name},
            "rationale": plan.rationale,
            "candidates": [{"slug": c.slug, "name": c.name} for c in plan.candidates],
        }

    @app.post("/api/run/stream")
    def run_stream_endpoint(body: RunRequest) -> StreamingResponse:
        try:
            llm = _require_llm()
        except LLMError as e:
            raise HTTPException(503, str(e))
        planner = Planner(registry, llm=llm)
        plan = planner.plan(body.message, hint_slug=body.skill)

        session: Session | None = None
        if body.session_id:
            session = memory.load(body.session_id) or Session(
                session_id=body.session_id, skill_slug=plan.skill.slug
            )

        executor = Executor(registry, llm, memory=memory)

        def gen():
            yield _sse("plan", {
                "skill": {"slug": plan.skill.slug, "name": plan.skill.name, "emoji": plan.skill.emoji},
                "rationale": plan.rationale,
            })
            try:
                for event in executor.stream(plan.skill, body.message, session=session):
                    yield _sse(event.kind, event.payload)
            except Exception as e:  # noqa: BLE001 - surface to the client
                yield _sse("error", {"message": str(e)})
            yield _sse("done", {})

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/api/run")
    def run_endpoint(body: RunRequest) -> dict[str, Any]:
        try:
            llm = _require_llm()
        except LLMError as e:
            raise HTTPException(503, str(e))
        planner = Planner(registry, llm=llm)
        plan = planner.plan(body.message, hint_slug=body.skill)

        session: Session | None = None
        if body.session_id:
            session = memory.load(body.session_id) or Session(
                session_id=body.session_id, skill_slug=plan.skill.slug
            )

        executor = Executor(registry, llm, memory=memory)
        result = executor.run(plan.skill, body.message, session=session)
        return {
            "skill": {"slug": plan.skill.slug, "name": plan.skill.name, "emoji": plan.skill.emoji},
            "rationale": plan.rationale,
            "text": result.text,
            "turns": result.turns,
            "session_id": session.session_id if session else None,
        }

    return app


def _sse(event_kind: str, payload: Any) -> str:
    return f"event: {event_kind}\ndata: {json.dumps(payload, default=str)}\n\n"


def _maybe_llm() -> AnthropicLLM | None:
    try:
        llm = AnthropicLLM(LLMConfig.from_env())
        llm._ensure_client()  # noqa: SLF001
        return llm
    except LLMError:
        return None


def _require_llm() -> AnthropicLLM:
    llm = AnthropicLLM(LLMConfig.from_env())
    llm._ensure_client()  # noqa: SLF001
    return llm


_CHAT_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Agency Runtime</title>
  <style>
    :root { color-scheme: light dark; }
    body { font: 15px/1.5 system-ui, sans-serif; max-width: 820px; margin: 0 auto; padding: 24px; }
    h1 { margin: 0 0 4px; }
    .sub { color: #888; margin-bottom: 16px; }
    .row { display: flex; gap: 8px; margin: 12px 0; }
    select, input, textarea, button {
      font: inherit; padding: 8px 10px; border-radius: 6px; border: 1px solid #999;
      background: transparent; color: inherit;
    }
    textarea { width: 100%; min-height: 80px; }
    button { cursor: pointer; }
    button:disabled { opacity: 0.6; cursor: not-allowed; }
    #log { margin-top: 16px; border: 1px solid #444; border-radius: 6px; padding: 12px;
           white-space: pre-wrap; min-height: 200px; }
    .meta { color: #888; font-size: 13px; }
  </style>
</head>
<body>
  <h1>The Agency</h1>
  <div class="sub">Pick a skill or let the planner choose, then send a request.</div>
  <div class="row">
    <select id="skill"><option value="">(auto-route)</option></select>
    <input id="session" placeholder="session id (optional)" />
  </div>
  <textarea id="msg" placeholder="What would you like the agent to do?"></textarea>
  <div class="row">
    <button id="send">Send</button>
    <span id="status" class="meta"></span>
  </div>
  <div id="log"></div>
<script>
  async function loadSkills() {
    const r = await fetch("/api/skills");
    const data = await r.json();
    const sel = document.getElementById("skill");
    for (const s of data.skills) {
      const opt = document.createElement("option");
      opt.value = s.slug;
      opt.textContent = `${s.emoji} ${s.name} (${s.category})`;
      sel.appendChild(opt);
    }
    document.getElementById("status").textContent = `${data.count} skills loaded`;
  }
  function appendLog(s) { document.getElementById("log").textContent += s; }
  function setStatus(s) { document.getElementById("status").textContent = s; }

  function parseSSE(buf) {
    // Returns [events, leftover]. Each event = {event, data}.
    const events = [];
    let idx;
    while ((idx = buf.indexOf("\\n\\n")) !== -1) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = "message", data = "";
      for (const line of block.split("\\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      try { events.push({event, data: JSON.parse(data)}); }
      catch { events.push({event, data}); }
    }
    return [events, buf];
  }

  async function send() {
    const btn = document.getElementById("send");
    const msg = document.getElementById("msg").value.trim();
    if (!msg) return;
    btn.disabled = true;
    setStatus("thinking…");
    document.getElementById("log").textContent = "";
    try {
      const r = await fetch("/api/run/stream", {
        method: "POST",
        headers: { "content-type": "application/json", "accept": "text/event-stream" },
        body: JSON.stringify({
          message: msg,
          skill: document.getElementById("skill").value || null,
          session_id: document.getElementById("session").value || null,
        }),
      });
      if (!r.ok) { appendLog(`Error ${r.status}: ${await r.text()}`); return; }

      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let events;
        [events, buf] = parseSSE(buf);
        for (const ev of events) {
          if (ev.event === "plan") {
            appendLog(`→ ${ev.data.skill.emoji} ${ev.data.skill.name} (${ev.data.skill.slug})\\n   ${ev.data.rationale}\\n\\n`);
          } else if (ev.event === "text_delta") {
            appendLog(ev.data);
          } else if (ev.event === "tool_use") {
            appendLog(`\\n[tool] ${ev.data.name}(${JSON.stringify(ev.data.input)})\\n`);
          } else if (ev.event === "tool_result") {
            const tag = ev.data.is_error ? "tool_error" : "tool_result";
            const preview = String(ev.data.content).slice(0, 300);
            appendLog(`[${tag}] ${preview}\\n`);
          } else if (ev.event === "stop") {
            appendLog(`\\n\\n[stop: ${ev.data}]`);
          } else if (ev.event === "error") {
            appendLog(`\\n[error] ${ev.data.message}`);
          } else if (ev.event === "done") {
            setStatus("done");
          }
        }
      }
    } catch (e) {
      appendLog(`\\nNetwork error: ${e}`);
    } finally {
      btn.disabled = false;
    }
  }
  document.getElementById("send").addEventListener("click", send);
  loadSkills();
</script>
</body>
</html>
"""
