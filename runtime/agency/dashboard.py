"""JARVIS Web GUI Dashboard — Pass 20.

Flask-based dashboard that exposes runtime stats, history, skills,
robot status, traces, and a chat endpoint.

Routes
------
    GET  /                — main HTML dashboard (dark theme, embedded)
    GET  /api/status      — uptime, model, tokens, memory count, schedule count
    GET  /api/history     — recent sessions (last 20)
    GET  /api/skills      — all loaded skills (name + category)
    GET  /api/robot       — robot status (joint states if module active)
    GET  /api/traces      — recent trace spans (last 50)
    POST /api/chat        — same interface as Pass-14 REST API

CLI
---
    agency dashboard [--port 8081]
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Optional Flask import
# ---------------------------------------------------------------------------

try:
    from flask import Flask, jsonify, request, Response
    _FLASK_AVAILABLE = True
except ImportError:
    _FLASK_AVAILABLE = False
    Flask = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Embedded dashboard HTML (dark theme, single-file)
# ---------------------------------------------------------------------------

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>JARVIS Dashboard</title>
<style>
  :root{--bg:#0d0d0d;--bg2:#1a1a1a;--bg3:#252525;--accent:#00d4ff;
        --accent2:#7c3aed;--green:#10b981;--red:#ef4444;--yellow:#f59e0b;
        --text:#e2e8f0;--muted:#64748b;--border:#2d2d2d;}
  *{box-sizing:border-box;margin:0;padding:0;}
  body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;
       min-height:100vh;}
  header{background:var(--bg2);border-bottom:1px solid var(--border);
         padding:12px 24px;display:flex;align-items:center;gap:16px;}
  header h1{font-size:1.4rem;font-weight:700;color:var(--accent);
            letter-spacing:2px;}
  .badge{background:var(--accent);color:#000;font-size:.65rem;font-weight:700;
         padding:2px 6px;border-radius:4px;letter-spacing:1px;}
  .live-dot{width:8px;height:8px;background:var(--green);border-radius:50%;
            animation:pulse 2s infinite;}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
  main{padding:24px;max-width:1400px;margin:0 auto;}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px;
        margin-bottom:24px;}
  .card{background:var(--bg2);border:1px solid var(--border);border-radius:10px;
        padding:18px;}
  .card .label{font-size:.72rem;color:var(--muted);text-transform:uppercase;
               letter-spacing:1px;margin-bottom:6px;}
  .card .value{font-size:1.8rem;font-weight:700;color:var(--accent);}
  .card .sub{font-size:.75rem;color:var(--muted);margin-top:4px;}
  .panels{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px;}
  @media(max-width:800px){.panels{grid-template-columns:1fr;}}
  .panel{background:var(--bg2);border:1px solid var(--border);border-radius:10px;
         padding:18px;}
  .panel h2{font-size:.9rem;font-weight:600;color:var(--muted);
            text-transform:uppercase;letter-spacing:1px;margin-bottom:12px;}
  .panel-body{max-height:260px;overflow-y:auto;}
  table{width:100%;border-collapse:collapse;font-size:.82rem;}
  th{text-align:left;color:var(--muted);font-weight:500;padding:6px 8px;
     border-bottom:1px solid var(--border);}
  td{padding:6px 8px;border-bottom:1px solid var(--border);vertical-align:top;}
  tr:last-child td{border-bottom:none;}
  .tag{display:inline-block;padding:1px 6px;border-radius:4px;font-size:.7rem;
       font-weight:600;}
  .tag-pass{background:#064e3b;color:var(--green);}
  .tag-fail{background:#450a0a;color:var(--red);}
  .chat-wrap{background:var(--bg2);border:1px solid var(--border);
             border-radius:10px;padding:18px;margin-bottom:24px;}
  .chat-wrap h2{font-size:.9rem;font-weight:600;color:var(--muted);
                text-transform:uppercase;letter-spacing:1px;margin-bottom:12px;}
  #chat-log{height:200px;overflow-y:auto;background:var(--bg3);border-radius:6px;
            padding:10px;font-size:.82rem;margin-bottom:10px;}
  .msg-user{color:var(--accent);margin-bottom:4px;}
  .msg-asst{color:var(--text);margin-bottom:10px;}
  .input-row{display:flex;gap:8px;}
  #chat-input{flex:1;background:var(--bg3);border:1px solid var(--border);
              border-radius:6px;padding:8px 12px;color:var(--text);font-size:.9rem;}
  #chat-input:focus{outline:none;border-color:var(--accent);}
  button{background:var(--accent);color:#000;border:none;border-radius:6px;
         padding:8px 18px;font-weight:700;cursor:pointer;font-size:.9rem;}
  button:hover{opacity:.85;}
  .refresh-btn{background:var(--bg3);color:var(--muted);border:1px solid var(--border);
               font-size:.75rem;padding:4px 10px;margin-left:auto;}
  .panel-header{display:flex;align-items:center;margin-bottom:12px;}
  .panel-header h2{flex:1;}
  .skill-list{font-size:.8rem;column-count:2;column-gap:16px;}
  .skill-item{padding:3px 0;border-bottom:1px solid var(--border);
              white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
  .uptime{font-size:.8rem;color:var(--muted);margin-left:auto;}
</style>
</head>
<body>
<header>
  <span class="live-dot"></span>
  <h1>JARVIS</h1>
  <span class="badge">PASS 20</span>
  <span class="uptime" id="uptime-hdr">--</span>
</header>
<main>
  <!-- Stat cards -->
  <div class="grid" id="stats-grid">
    <div class="card"><div class="label">Tokens Used</div>
      <div class="value" id="stat-tokens">--</div>
      <div class="sub">cumulative</div></div>
    <div class="card"><div class="label">Sessions</div>
      <div class="value" id="stat-sessions">--</div>
      <div class="sub">history files</div></div>
    <div class="card"><div class="label">Skills Loaded</div>
      <div class="value" id="stat-skills">--</div>
      <div class="sub">across all categories</div></div>
    <div class="card"><div class="label">Scheduled Tasks</div>
      <div class="value" id="stat-schedule">--</div>
      <div class="sub">active cron jobs</div></div>
    <div class="card"><div class="label">Robot Mode</div>
      <div class="value" id="stat-robot" style="font-size:1.1rem">--</div>
      <div class="sub">simulation status</div></div>
    <div class="card"><div class="label">Uptime</div>
      <div class="value" id="stat-uptime" style="font-size:1.1rem">--</div>
      <div class="sub">since server start</div></div>
  </div>

  <!-- Chat -->
  <div class="chat-wrap">
    <h2>Live Chat</h2>
    <div id="chat-log"></div>
    <div class="input-row">
      <input id="chat-input" type="text" placeholder="Ask JARVIS..."
             onkeydown="if(event.key==='Enter')sendChat()"/>
      <button onclick="sendChat()">Send</button>
    </div>
  </div>

  <!-- Panels row 1 -->
  <div class="panels">
    <div class="panel">
      <div class="panel-header">
        <h2>Recent History</h2>
        <button class="refresh-btn" onclick="loadHistory()">↺</button>
      </div>
      <div class="panel-body">
        <table><thead><tr><th>Session</th><th>Messages</th></tr></thead>
        <tbody id="history-tbody"></tbody></table>
      </div>
    </div>
    <div class="panel">
      <div class="panel-header">
        <h2>Recent Traces</h2>
        <button class="refresh-btn" onclick="loadTraces()">↺</button>
      </div>
      <div class="panel-body">
        <table><thead><tr><th>Operation</th><th>ms</th><th>Status</th></tr></thead>
        <tbody id="traces-tbody"></tbody></table>
      </div>
    </div>
  </div>

  <!-- Panels row 2 -->
  <div class="panels">
    <div class="panel">
      <div class="panel-header">
        <h2>Skills (first 60)</h2>
        <button class="refresh-btn" onclick="loadSkills()">↺</button>
      </div>
      <div class="panel-body">
        <div class="skill-list" id="skill-list"></div>
      </div>
    </div>
    <div class="panel">
      <div class="panel-header">
        <h2>Robot Status</h2>
        <button class="refresh-btn" onclick="loadRobot()">↺</button>
      </div>
      <div class="panel-body">
        <table><thead><tr><th>Joint</th><th>Position</th></tr></thead>
        <tbody id="robot-tbody"></tbody></table>
      </div>
    </div>
  </div>
</main>

<script>
const _START = Date.now();

function fmtUptime(ms){
  const s=Math.floor(ms/1000);
  const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sec=s%60;
  return [h,m,sec].map(v=>String(v).padStart(2,'0')).join(':');
}
setInterval(()=>{
  const u=fmtUptime(Date.now()-_START);
  document.getElementById('uptime-hdr').textContent=u;
  document.getElementById('stat-uptime').textContent=u;
},1000);

async function api(path){
  try{const r=await fetch(path);return await r.json();}
  catch(e){return null;}
}

async function loadStatus(){
  const d=await api('/api/status');
  if(!d)return;
  document.getElementById('stat-tokens').textContent=
    (d.tokens_used||0).toLocaleString();
  document.getElementById('stat-sessions').textContent=d.sessions||0;
  document.getElementById('stat-skills').textContent=d.skills||0;
  document.getElementById('stat-schedule').textContent=d.schedule_count||0;
  document.getElementById('stat-robot').textContent=d.robot_mode||'inactive';
}

async function loadHistory(){
  const d=await api('/api/history');
  if(!d)return;
  const tb=document.getElementById('history-tbody');
  tb.innerHTML='';
  (d.sessions||[]).slice(0,15).forEach(s=>{
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${s.name||''}</td><td>${s.message_count||0}</td>`;
    tb.appendChild(tr);
  });
}

async function loadSkills(){
  const d=await api('/api/skills');
  if(!d)return;
  const el=document.getElementById('skill-list');
  el.innerHTML='';
  (d.skills||[]).slice(0,60).forEach(s=>{
    const div=document.createElement('div');
    div.className='skill-item';
    div.title=s.description||'';
    div.textContent=s.name||'';
    el.appendChild(div);
  });
}

async function loadRobot(){
  const d=await api('/api/robot');
  if(!d)return;
  const tb=document.getElementById('robot-tbody');
  tb.innerHTML='';
  const joints=d.joint_states||{};
  Object.entries(joints).forEach(([j,v])=>{
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${j}</td><td>${Number(v).toFixed(4)}</td>`;
    tb.appendChild(tr);
  });
  if(!Object.keys(joints).length){
    tb.innerHTML='<tr><td colspan="2" style="color:var(--muted)">No robot active</td></tr>';
  }
}

async function loadTraces(){
  const d=await api('/api/traces');
  if(!d)return;
  const tb=document.getElementById('traces-tbody');
  tb.innerHTML='';
  (d.spans||[]).slice(-20).reverse().forEach(sp=>{
    const ms=sp.duration_ms!=null?sp.duration_ms.toFixed(1):'?';
    const ok=sp.error?
      '<span class="tag tag-fail">ERR</span>':
      '<span class="tag tag-pass">OK</span>';
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${sp.name||''}</td><td>${ms}</td><td>${ok}</td>`;
    tb.appendChild(tr);
  });
}

async function sendChat(){
  const inp=document.getElementById('chat-input');
  const msg=inp.value.trim();
  if(!msg)return;
  inp.value='';
  const log=document.getElementById('chat-log');
  log.innerHTML+=`<div class="msg-user">You: ${msg}</div>`;
  log.scrollTop=log.scrollHeight;
  try{
    const r=await fetch('/api/chat',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message:msg})});
    const d=await r.json();
    const reply=d.response||d.error||'(no response)';
    log.innerHTML+=`<div class="msg-asst">JARVIS: ${reply}</div>`;
    log.scrollTop=log.scrollHeight;
    loadStatus();
  }catch(e){
    log.innerHTML+=`<div class="msg-asst" style="color:var(--red)">Error: ${e}</div>`;
  }
}

// initial load
loadStatus();loadHistory();loadSkills();loadRobot();loadTraces();
setInterval(loadStatus,10000);
setInterval(loadTraces,15000);
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Dashboard app factory
# ---------------------------------------------------------------------------

_SERVER_START = time.time()


def build_dashboard(repo_root: Path | None = None) -> "Flask":
    """Return a configured Flask app for the JARVIS dashboard."""
    if not _FLASK_AVAILABLE:
        raise ImportError(
            "Flask is required for the dashboard: pip install flask"
        )

    app = Flask(__name__, static_folder=None)
    app.config["JSON_SORT_KEYS"] = False

    # Lazy imports to keep startup fast
    def _stats() -> Dict[str, Any]:
        try:
            from .stats import load_stats
            return load_stats()
        except Exception:
            return {}

    def _history_sessions(limit: int = 20) -> List[Dict[str, Any]]:
        try:
            from .history import history_dir
            files = sorted(history_dir().glob("*.jsonl"), reverse=True)[:limit]
            out = []
            for f in files:
                lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
                out.append({"name": f.stem, "message_count": len(lines)})
            return out
        except Exception:
            return []

    def _skills_list(root: Path | None) -> List[Dict[str, str]]:
        try:
            from .skills import SkillRegistry, discover_repo_root
            r = root or discover_repo_root()
            registry = SkillRegistry.load(r)
            return [
                {"name": s.name, "category": s.category,
                 "description": getattr(s, "description", "")}
                for s in registry.all()
            ]
        except Exception:
            return []

    def _schedule_count() -> int:
        try:
            from .scheduler import Scheduler
            sched = Scheduler()
            return len(sched.list_tasks())
        except Exception:
            return 0

    def _robot_status() -> Dict[str, Any]:
        try:
            from .robotics.simulation import MockSimulation
            sim = MockSimulation()
            sim.load_humanoid()
            return {
                "active": False,
                "backend": "mock",
                "joint_states": sim.get_joint_states(),
            }
        except Exception:
            return {"active": False, "backend": "unavailable", "joint_states": {}}

    def _recent_traces(limit: int = 50) -> List[Dict[str, Any]]:
        try:
            from .tracing import get_tracer
            tracer = get_tracer()
            spans = []
            p = tracer._traces_dir / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"
            if p.exists():
                lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
                for line in lines[-limit:]:
                    try:
                        spans.append(json.loads(line))
                    except Exception:
                        pass
            return spans
        except Exception:
            return []

    # ----------------------------------------------------------------
    # Routes
    # ----------------------------------------------------------------

    @app.route("/")
    def index() -> Response:
        return Response(_DASHBOARD_HTML, mimetype="text/html")

    @app.route("/api/status")
    def api_status():
        st = _stats()
        uptime_s = int(time.time() - _SERVER_START)
        h, rem = divmod(uptime_s, 3600)
        m, s = divmod(rem, 60)
        return jsonify({
            "uptime": f"{h:02d}:{m:02d}:{s:02d}",
            "uptime_seconds": uptime_s,
            "model": os.environ.get("AGENCY_MODEL", "claude-sonnet-4-6"),
            "tokens_used": (st.get("input_tokens", 0) +
                            st.get("output_tokens", 0)),
            "input_tokens": st.get("input_tokens", 0),
            "output_tokens": st.get("output_tokens", 0),
            "total_calls": st.get("total_calls", 0),
            "sessions": len(_history_sessions(100)),
            "skills": len(_skills_list(repo_root)),
            "schedule_count": _schedule_count(),
            "robot_mode": "mock",
        })

    @app.route("/api/history")
    def api_history():
        return jsonify({"sessions": _history_sessions(20)})

    @app.route("/api/skills")
    def api_skills():
        return jsonify({"skills": _skills_list(repo_root)})

    @app.route("/api/robot")
    def api_robot():
        return jsonify(_robot_status())

    @app.route("/api/traces")
    def api_traces():
        return jsonify({"spans": _recent_traces(50)})

    @app.route("/api/chat", methods=["POST"])
    def api_chat():
        body = request.get_json(silent=True) or {}
        message = body.get("message", "")
        if not message:
            return jsonify({"error": "message required"}), 400
        try:
            from .multi_agent import MultiAgentOrchestrator
            orch = MultiAgentOrchestrator()
            result = orch.run_task(message)
            return jsonify({
                "response": result.final_output(),
                "success": result.success,
                "steps": len(result.steps),
            })
        except Exception as exc:
            return jsonify({"error": str(exc), "response": str(exc)}), 500

    return app


# ---------------------------------------------------------------------------
# CLI entry-point helper
# ---------------------------------------------------------------------------

def run_dashboard(port: int = 8081, repo_root: Path | None = None,
                  debug: bool = False) -> None:
    """Start the Flask dashboard server (blocking)."""
    app = build_dashboard(repo_root=repo_root)
    print(f"[JARVIS Dashboard] http://localhost:{port}/")
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)
