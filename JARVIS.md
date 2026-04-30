# J.A.R.V.I.S — Singularity

> **Just A Rather Very Intelligent System** — one runtime, one registry, one dashboard, one brand. This file is the single source of truth for what JARVIS is, how to run it, and what it's built from.

---

## 1. Identity

JARVIS is the unified persona that drives the **Agency Runtime** in this repository. The runtime loads every persona markdown file under the 17 top-level category folders as a runnable `Skill`, and the JARVIS persona (under `jarvis/`) acts as the meta-router: every request is scored by the keyword-weighted `SupremeJarvisBrain` and dispatched to the best specialist.

- **Owner**: Amjad Mobarsham
- **Voice**: Steve Jobs-caliber product taste, Linus Torvalds-grade engineering rigor.
- **Languages**: bilingual greeting and chat support (Hebrew + English, Asia/Jerusalem timezone).
- **License**: MIT (see `LICENSE`).

---

## 2. One Command to Rule Them All

```bash
agency singularity
```

That single command:

1. Loads every skill in the repo (currently **323** persona files across **16** active categories — see `agency map`).
2. Prints the bilingual JARVIS greeting (Hebrew morning/afternoon/evening + English).
3. Boots the FastAPI server on `http://127.0.0.1:8765`.
4. Opens the **Singularity Dashboard** at `http://127.0.0.1:8765/dashboard` in your default browser.
5. Drops you into the JARVIS chat REPL.

Useful flags:

| Flag                | What it does                                                  |
|---------------------|---------------------------------------------------------------|
| `--check`           | Validate registry + endpoints + repo hygiene, then exit.      |
| `--no-browser`      | Skip the auto-open of the dashboard.                          |
| `--no-server`       | REPL-only mode (no FastAPI server, no dashboard).             |
| `--host` / `--port` | Override the bind address (default `127.0.0.1:8765`).         |

---

## 3. CLI singularity — `agency` is the only entry point

| Command                 | Purpose                                                                  |
|-------------------------|--------------------------------------------------------------------------|
| `agency singularity`    | Boot everything (server + dashboard + REPL).                             |
| `agency map`            | Print the unified `categories \| agents | total` view.                   |
| `agency jarvis run`     | Boot the JARVIS persona runtime (replaces `python -m agency.supreme_main`). |
| `agency jarvis status`  | JSON snapshot of the persona/character/memory subsystems.                |
| `agency chat`           | Interactive REPL only (no server).                                       |
| `agency serve`          | Start the FastAPI server only.                                           |
| `agency list / plan / run / debug` | Original skill-running CLI.                                  |
| `agency doctor`         | Diagnose the runtime: skills loaded, env flags, optional deps.           |

`runtime/agency/supreme_main.py` is preserved as a backward-compatible shim that internally calls `agency jarvis run`. New code should always use the `agency` CLI.

---

## 4. The Singularity Dashboard

`http://127.0.0.1:8765/dashboard` — single HTML page that renders:

- **All 340 agents** in a category-grouped grid, with `jarvis-core` / `jarvis-core-brain` highlighted as the meta-router.
- **Live runtime status** fed from `GET /singularity` (skills loaded, categories, JARVIS specialists, routing-domain count, execution + planner models, trust mode, last lesson).
- **Chat field** that streams into the same `/api/run/stream` executor the CLI uses.
- **Spatial HUD pulse** embedded as an iframe of `/spatial`.

Programmatic clients should consume `GET /singularity` instead of scraping the HTML — it returns the full `categories[]`, `routing_table`, `runtime` block, and `totals` in one JSON payload.

---

## 5. Repo Layout (canonical)

```
agency-agents/
├── runtime/                  # the agency runtime (Python package + tests)
│   └── agency/
│       ├── cli.py            # `agency` entry-point (the only CLI)
│       ├── server.py         # FastAPI app: /, /dashboard, /singularity, /spatial, /api/*
│       ├── skills.py         # SkillRegistry — loads every category folder
│       ├── jarvis_brain.py   # SupremeJarvisBrain — keyword-weighted routing
│       ├── supreme_main.py   # backward-compat shim → `agency jarvis run`
│       └── static/
│           ├── chat.html
│           ├── dashboard.html  # singularity dashboard
│           └── spatial.html
├── jarvis/                   # 109 JARVIS persona files (incl. jarvis-core-brain)
├── academic/, engineering/, marketing/, …  # 16 other agent category folders
├── scripts/
│   ├── jarvis/               # the only supported launchers (start/setup × .sh + .ps1)
│   ├── dev/                  # commit/push helpers (NOT part of the launch path)
│   ├── install.sh / install.ps1 / install.bat
│   ├── lint-agents.sh, convert.sh
│   └── smoke_*.py, build_capabilities.py, enumerate_domains.py
├── docs/
├── integrations/
├── JARVIS.md                 # this file
├── README.md                 # short pitch + pointer to JARVIS.md
├── ATTRIBUTIONS.md, SECURITY.md, CONTRIBUTING*.md, LICENSE
```

Anything else at the root (zip artifacts, stray `.bat` files, status-of-the-day markdown) is non-canonical and should be either removed or moved into `scripts/dev/` or `docs/`.

---

## 6. Subsystems

| Subsystem                | Lives in                                | Status |
|--------------------------|-----------------------------------------|--------|
| `SkillRegistry`          | `runtime/agency/skills.py`              | ✅      |
| `SupremeJarvisBrain`     | `runtime/agency/jarvis_brain.py`        | ✅      |
| `Planner` (LLM-backed)   | `runtime/agency/planner.py`             | ✅      |
| `Executor` + tools       | `runtime/agency/executor.py`, `tools.py`| ✅      |
| `AnthropicLLM`           | `runtime/agency/llm.py`                 | ✅      |
| `MemoryStore` (sessions) | `runtime/agency/memory.py`              | ✅      |
| `VectorMemory`           | `runtime/agency/vector_memory.py`       | ✅      |
| `PersonaEngine`          | `runtime/agency/persona_engine.py`      | ✅      |
| `CharacterState`         | `runtime/agency/character_state.py`     | ✅      |
| `AmjadMemory`            | `runtime/agency/amjad_memory.py`        | ✅      |
| `JarvisGreeting` / `JarvisSoul` | `runtime/agency/jarvis_*.py`     | ✅      |
| `SelfLearnerEngine`      | `runtime/agency/self_learner_engine.py` | ✅      |
| `MetaReasoningEngine`    | `runtime/agency/meta_reasoner.py`       | ✅      |
| `ContextManager`         | `runtime/agency/context_manager.py`     | ✅      |
| `KnowledgeExpansion`     | `runtime/agency/knowledge_expansion.py` | ✅      |
| `Spatial HUD`            | `runtime/agency/spatial.py` + `/spatial`| ✅      |
| `Singularity Dashboard`  | `runtime/agency/static/dashboard.html`  | ✅      |
| `TrustLayer`             | `runtime/agency/trust.py`               | ✅      |
| `CostAwareRouter`        | `runtime/agency/cost_router.py`         | ✅      |

---

## 7. Test Status

- **Suite**: `pytest runtime/tests/` — covers the runtime, CLI, server, JARVIS brain, persona engine, lessons, profile, trust, tools, vector memory, spatial, and singularity wiring.
- **Singularity-specific test**: `test_singularity.py` enforces (a) `agency singularity --check` exits 0, (b) `GET /singularity` returns every category + the JARVIS-core slug, (c) the repo root is free of `.zip` artifacts and stray `.bat` scripts.
- **Public APIs that must NOT break**: `Executor`, `SkillRegistry`, `JarvisBrain`, `AnthropicLLM`. All other surfaces are internal.

---

## 8. How to Run It (Setup)

### Linux / macOS

```bash
./scripts/jarvis/setup.sh     # one-shot venv + install
./scripts/jarvis/start.sh     # → agency singularity
```

### Windows (PowerShell)

```powershell
.\scripts\jarvis\setup.ps1
.\scripts\jarvis\start.ps1
```

### Manual

```bash
pip install -e runtime[dev]
export ANTHROPIC_API_KEY=sk-ant-...
agency singularity
```

---

## 9. What JARVIS Does NOT Do

- It is **not** a chatbot. It is an orchestration runtime that dispatches to specialists.
- It does **not** ship plugins. New skills are markdown files added under the existing category folders.
- It does **not** run distributed. Everything is in-process; if you want a queue, wire one in.
- It does **not** persist a vector index across hosts by default — `VectorMemory` is local.

For everything else, run `agency singularity` and start asking questions.
