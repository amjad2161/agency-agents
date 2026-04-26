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
    # Optional: list of image URLs OR base64 data URLs
    # ("data:image/png;base64,...") to attach to the user turn.
    # Anthropic API accepts both shapes natively in image content blocks.
    images: list[str] | None = None


class PlanRequestBody(BaseModel):
    message: str


class LessonAppend(BaseModel):
    text: str


class TrustSet(BaseModel):
    mode: str


class ProfileWrite(BaseModel):
    text: str


def build_app(repo: Path | None = None) -> FastAPI:
    root = repo if repo else discover_repo_root()
    registry = SkillRegistry.load(root)
    memory = MemoryStore(Path.home() / ".agency" / "sessions")

    app = FastAPI(title="Agency Runtime", version="0.1.0")

    # Locate the chat HUD asset (separate file under static/ — keeps
    # server.py focused on routing instead of inlining ~700 lines of
    # HTML/CSS/JS). Falls back to the embedded _CHAT_HTML constant if
    # the file is missing (developer-mode fallback).
    _chat_html_path = Path(__file__).parent / "static" / "chat.html"

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        try:
            return _chat_html_path.read_text(encoding="utf-8")
        except FileNotFoundError:
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

    @app.get("/api/skills/graph")
    def skills_graph() -> dict[str, Any]:
        """Compact category + relationship view for the HUD sidebar.

        Returns:
          - total_skills: int
          - categories: [{name, count, top_slugs: [...]}]
          - delegation_hubs: slugs that other skills are most likely to
            delegate to (currently a heuristic: anything with `core`,
            `master`, `orchestrator`, `omega` in the slug — the
            registry doesn't carry explicit delegation edges yet).
        """
        skills = registry.all()
        cats: dict[str, list[Any]] = {}
        for s in skills:
            cats.setdefault(s.category, []).append(s)

        hub_keywords = ("core", "brainiac", "elder", "omega",
                        "orchestrator", "master", "research-director",
                        "goal-decomposer")
        hubs = [
            {"slug": s.slug, "name": s.name, "emoji": s.emoji,
             "category": s.category}
            for s in skills
            if any(k in s.slug.lower() for k in hub_keywords)
        ][:20]

        return {
            "total_skills": len(skills),
            "categories": [
                {
                    "name": cat,
                    "count": len(items),
                    "top_slugs": [s.slug for s in items[:5]],
                }
                for cat, items in sorted(cats.items())
            ],
            "delegation_hubs": hubs,
        }

    @app.get("/api/lessons")
    def lessons_get() -> dict[str, Any]:
        """Return the cross-session lessons journal contents."""
        from .lessons import lessons_path, load_lessons_text
        text = load_lessons_text() or ""
        p = lessons_path()
        return {
            "path": str(p),
            "exists": p.exists() and p.is_file(),
            "size_bytes": (p.stat().st_size if p.exists() and p.is_file() else 0),
            "text": text,
        }

    @app.post("/api/lessons")
    def lessons_append(body: LessonAppend) -> dict[str, Any]:
        """Append a single timestamped lesson entry."""
        from datetime import datetime, timezone
        from .lessons import ensure_default_lessons

        line = (body.text or "").strip()
        if not line:
            raise HTTPException(400, "text cannot be empty")
        p = ensure_default_lessons()
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        with p.open("a", encoding="utf-8") as f:
            f.write(f"\n## {stamp} · note from HUD\n\n{line}\n")
        return {"appended": True, "path": str(p), "timestamp": stamp}

    @app.get("/api/trust")
    def trust_get() -> dict[str, Any]:
        """Snapshot of the active trust gate."""
        from dataclasses import asdict
        from .trust import current, gate, trust_conf_path
        g = gate()
        return {
            "mode": current().value,
            "gate": {k: v for k, v in asdict(g).items() if k != "mode"},
            "config_file": str(trust_conf_path()),
            "config_present": trust_conf_path().exists(),
        }

    @app.post("/api/trust")
    def trust_set(body: TrustSet) -> dict[str, Any]:
        """Persist the trust mode to ~/.agency/trust.conf so subsequent
        runs pick it up without an env var."""
        from .trust import trust_conf_path

        mode = (body.mode or "").strip().lower()
        if mode not in ("off", "on-my-machine", "yolo"):
            raise HTTPException(400,
                f"unrecognized mode: {body.mode!r}. "
                "Choose off | on-my-machine | yolo.")
        p = trust_conf_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            f"# Agency trust mode for this machine.\n"
            f"# Values: off | on-my-machine | yolo.\n"
            f"{mode}\n",
            encoding="utf-8",
        )
        # Refresh in-process env so subsequent calls in THIS server pick
        # up the change without restart.
        import os as _os
        _os.environ["AGENCY_TRUST_MODE"] = mode
        return {"mode": mode, "config_file": str(p), "applied": True}

    @app.get("/api/sessions")
    def sessions_list() -> dict[str, Any]:
        """List recent saved sessions (filenames + last-modified time)."""
        sess_dir = Path.home() / ".agency" / "sessions"
        if not sess_dir.is_dir():
            return {"path": str(sess_dir), "sessions": []}
        sessions = []
        for f in sorted(sess_dir.glob("*.jsonl"),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True)[:50]:
            try:
                stat = f.stat()
                sessions.append({
                    "id": f.stem,
                    "size_bytes": stat.st_size,
                    "modified": stat.st_mtime,
                })
            except OSError:
                continue
        return {"path": str(sess_dir), "sessions": sessions}

    @app.get("/api/sessions/{session_id}/export")
    def session_export(session_id: str) -> dict[str, Any]:
        """Export a saved session as a self-contained markdown transcript.

        Reads the JSONL turns under ~/.agency/sessions/<id>.jsonl and
        renders user/assistant messages as a single markdown blob the
        user can save, paste into a doc, or share.
        """
        # Defensive: don't let arbitrary paths leak — only resolve under
        # the sessions dir, no `..` allowed.
        if not session_id or "/" in session_id or "\\" in session_id or ".." in session_id:
            raise HTTPException(400, "invalid session id")
        sess_dir = Path.home() / ".agency" / "sessions"
        path = sess_dir / f"{session_id}.jsonl"
        if not path.is_file():
            raise HTTPException(404, f"session not found: {session_id}")
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            raise HTTPException(500, f"could not read session: {e}")
        out = [f"# Session · {session_id}\n",
               f"_{path}_\n"]
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                turn = json.loads(raw)
            except json.JSONDecodeError:
                continue
            role = turn.get("role", "?")
            content = turn.get("content", turn.get("text", ""))
            if isinstance(content, list):
                content = "\n".join(
                    str(b.get("text", b)) if isinstance(b, dict) else str(b)
                    for b in content
                )
            out.append(f"\n## {role}\n\n{content}\n")
        return {
            "session_id": session_id,
            "markdown": "\n".join(out),
            "size_bytes": path.stat().st_size,
        }

    @app.get("/api/profile")
    def profile_get() -> dict[str, Any]:
        """Return the always-on user profile contents."""
        from .profile import load_profile_text, profile_path
        text = load_profile_text() or ""
        p = profile_path()
        return {
            "path": str(p),
            "exists": p.exists() and p.is_file(),
            "size_bytes": (p.stat().st_size if p.exists() and p.is_file() else 0),
            "text": text,
        }

    @app.post("/api/profile")
    def profile_write(body: ProfileWrite) -> dict[str, Any]:
        """Replace the entire profile body. Empty text deletes the file."""
        from .profile import profile_path
        p = profile_path()
        text = body.text or ""
        if not text.strip():
            if p.exists():
                p.unlink()
            return {"deleted": True, "path": str(p)}
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return {"saved": True, "path": str(p), "size_bytes": p.stat().st_size}

    @app.get("/api/mcp")
    def mcp_list() -> dict[str, Any]:
        """Return the configured MCP servers from `AGENCY_MCP_SERVERS`.

        Reflects what the runtime would forward to Anthropic on the
        `mcp-client-2025-11-20` beta. Doesn't make a network call —
        just shows the parsed config.
        """
        import os as _os
        raw = _os.environ.get("AGENCY_MCP_SERVERS", "").strip()
        if not raw:
            return {"configured": False, "servers": [],
                    "note": "Set AGENCY_MCP_SERVERS to a JSON list to enable."}
        try:
            servers = json.loads(raw)
        except json.JSONDecodeError as e:
            return {"configured": True, "servers": [], "parse_error": str(e)}
        if not isinstance(servers, list):
            return {"configured": True, "servers": [],
                    "parse_error": "AGENCY_MCP_SERVERS must be a JSON list"}
        # Strip any field that smells like a secret before returning.
        safe = []
        for s in servers:
            if not isinstance(s, dict):
                continue
            redacted = {k: v for k, v in s.items()
                        if k.lower() not in ("authorization", "api_key", "token",
                                              "secret", "password")}
            for k in s:
                if k.lower() in ("authorization", "api_key", "token", "secret",
                                  "password"):
                    redacted[k] = "(redacted)"
            safe.append(redacted)
        return {"configured": True, "servers": safe}

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
        try:
            # Planner.plan raises ValueError for an unknown hint slug.
            # Surface as 400 (bad input from the client) instead of letting
            # FastAPI render the default 500.
            plan = planner.plan(body.message, hint_slug=body.skill)
        except ValueError as e:
            raise HTTPException(400, str(e))

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
                for event in executor.stream(plan.skill, body.message, session=session, images=body.images):
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
        try:
            plan = planner.plan(body.message, hint_slug=body.skill)
        except ValueError as e:
            raise HTTPException(400, str(e))

        session: Session | None = None
        if body.session_id:
            session = memory.load(body.session_id) or Session(
                session_id=body.session_id, skill_slug=plan.skill.slug
            )

        executor = Executor(registry, llm, memory=memory)
        result = executor.run(plan.skill, body.message, session=session, images=body.images)
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
