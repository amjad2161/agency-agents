# J.A.R.V.I.S One — The Singularity

> **One brain. One CLI. One dashboard. One identity.**
>
> JARVIS One unifies the 22+ persona categories, the runtime, and every
> Pass-24/BRAINIAC subsystem into a single project under a single
> entry point: `agency singularity`.

This document is the master reference for JARVIS One — identity,
capabilities, current status, and how to run it. It supersedes
`JARVIS_STATUS.md` and `JARVIS_CAPABILITIES.md`, which are kept only as
historical archives.

---

## 1. Identity

| | |
|---|---|
| **Name** | J.A.R.V.I.S One — OMEGA_NEXUS |
| **Owner** | Amjad Mobarsham (sole owner) |
| **Surface** | `agency` CLI · `runtime/agency` Python package · FastAPI server |
| **Tongue** | Hebrew-first, English-second; auto-detected per turn |
| **Posture** | 100% local-friendly with optional cloud fallbacks; no new dependencies |

### GOD-MODE entry point

```python
from agency.jarvis_one import build_default_interface

jarvis = build_default_interface()
jarvis.ask("Draft a software-consulting contract")     # 1. ask
jarvis.chat("שלום, מה שלומך?")                          # 2. chat
jarvis.create("flowchart of the deployment", want=["text", "diagram"])  # 3. create
jarvis.orchestrate("Plan a launch: legal + engineering + marketing")    # 4. orchestrate
jarvis.plan("Ship v2 by Friday")                       # 5. plan
jarvis.collaborate("debate", "monorepo vs polyrepo")   # 6. collaborate
jarvis.react("find the failing test")                  # 7. react
jarvis.route("change the homepage hero copy")          # 8. route
jarvis.remember("user prefers SI units")               # 9. remember
jarvis.recall("units")                                 #    recall
jarvis.status()                                        # 10. status
jarvis.personas()                                      # 11. personas
jarvis.gesture(my_frame)                               # 12. gesture
jarvis.reload()                                        # 13. reload
```

These 13 methods cover the whole capability surface — everything else
in the package is wired through one of them.

---

## 2. One-command boot — `agency singularity`

```bash
# Hermetic check (CI-friendly): boots, prints the bilingual banner,
# verifies that skills + personas loaded, exits 0/1.
agency singularity --check

# Full boot: dashboard + browser + chat REPL all in one command.
agency singularity

# Headless server only.
agency singularity --no-browser --no-chat --port 8765
```

What `agency singularity` does, in order:

1. Loads every skill via the unified `SkillRegistry` (~22 categories,
   300+ persona files including the JARVIS-core meta-router).
2. Prints a bilingual greeting banner with live status counts.
3. Mounts the FastAPI server (`/dashboard`, `/singularity`,
   `/api/jarvis/*`, `/ws/jarvis`) on `127.0.0.1:8765` by default.
4. Opens the browser at `http://127.0.0.1:8765/dashboard`.
5. Drops you into the chat REPL — every turn flows through the
   `JARVISInterface` and is mirrored to the dashboard via WebSocket.

---

## 3. Dashboard — one URL

`http://localhost:8765/dashboard`

* **Left column**
  * Live runtime stats — skill count, categories, personas, version.
  * Agent grid — every category as a tile; the **JARVIS-core**
    category is highlighted at the centre as the meta-router.
  * Senior expert personas catalogue.
  * Spatial HUD pulse embedded inline (`<iframe src="/spatial">`).
* **Right column**
  * Chat panel that talks to the server-side REPL via
    `/ws/jarvis`. Every reply carries persona, sentiment, and a
    crisis flag from the advisor brain.

---

## 4. Subsystem map (`runtime/agency/jarvis_one/`)

| Tier | Module | Role |
|---|---|---|
| 1 | `unified_interface.py` | GOD-MODE `JARVISInterface` — 13 methods |
| 2 | `multi_agent_orchestrator.py` | Split → fan out → merge across personas |
| 2 | `expert_personas.py` | 6 senior personas covering 125+ domains |
| 2 | `collaborative_workflow.py` | peer-review, brainstorm, debate, sequential, parallel |
| 2 | `task_planner.py` | DAG scheduler + critical-path analysis |
| 3 | `multimodal_output.py` | text + diagram + audio + document bundles |
| 3 | `document_generator.py` | Markdown / HTML / PDF / DOCX / PPTX / XLSX, 7 templates |
| 3 | `drawing_engine.py` | 12 diagram families, 4 colour schemes, SVG output |
| 4 | `advisor_brain.py` | Emotional companion + crisis detection (HE/EN/AR) |
| 5 | `local_brain.py` | Ollama / vLLM gateway with self-healing fallback |
| 5 | `local_voice.py` | Faster-Whisper STT + XTTSv2 TTS (mock-first) |
| 5 | `local_vision.py` | MediaPipe Holistic + 7 known gestures |
| 5 | `local_memory.py` | Vector memory with disk persistence |
| 5 | `local_os.py` | Trust-gated OS bridge |
| 5 | `local_skill_engine.py` | Hot-swap wrapper around `SkillRegistry` |
| 5 | `react_loop.py` | Bounded Observe → Reason → Act → Learn |
| 5 | `vr_interface.py` | Gesture → OS intent mapping |
| 6 | `decision_engine.py` | Confidence routing + Hebrew clarification |
| 6 | `api_gateway.py` | VAD → NLU → decision → skill → TTS pipeline |
| 6 | `hot_reload.py` | Polling watcher → reload registry |
| 6 | `task_executor.py` | Priority queue with optional worker threads |
| 6 | `context_manager.py` | Thread-local scoped context stack |
| 6 | `world_model.py` | 3-D object tracking with confidence decay |
| 7 | `unified_bridge.py` | Aggregator hub for every subsystem |

### Inspired-by reference modules (pure Python, no new deps)

| Module | Inspired by | Purpose |
|---|---|---|
| `llm_router.py` | LiteLLM | Multi-backend router + token-cost ledger |
| `tracing.py` | Langfuse + OTEL | Span tree + JSON exporter |
| `vector_store.py` | ChromaDB | Multi-collection vector store |
| `tool_registry.py` | MCP | JSON-schema-typed tool registry |
| `evals.py` | DeepEval + RAGAS | Relevance / factuality / length metrics |
| `semantic_router.py` | aurelio-labs/semantic-router | LLM-free intent routing |
| `prompt_optimizer.py` | DSPy | Few-shot mining + greedy selection |
| `sandbox.py` | E2B | Trust-gated subprocess sandbox |
| `tui.py` | Rich | ANSI tables, panels, progress |
| `multi_agent_dag.py` | LangGraph | DAG runner with conditional edges |
| `aios_bridge.py` | AIOS | Syscall-style bridge to OS / memory |
| `channels.py` | OpenClaw plugins | DingTalk / Lark / Weibo / WeCom / WeChat / QQ adapters |
| `robotics.py` | PyBullet / MuJoCo / Webots / Isaac / YOLO | Humanoid simulator facade |

Every adapter ships a deterministic, in-memory **mock** so tests stay
hermetic and the singularity boots offline. Real backends (Whisper,
PyBullet, Chroma, …) are loaded lazily *only* when the optional
dependency is installed; no new dependency was added by JARVIS One.

---

## 5. CLI surface

```text
agency singularity [--check] [--no-browser] [--no-chat] [--host …] [--port …]
agency map         [--json]
agency jarvis      ask    <message…> [--persona SLUG] [--json]
agency jarvis      create <request…> [--want text|diagram|audio|document] [--out DIR]
agency jarvis      chat   [--turns N]
agency jarvis      run    [--mode supreme_brainiac] [--serve]
agency jarvis      status
agency jarvis      personas
```

`agency jarvis run` is the backwards-compatible shim that keeps
`supreme_main.py` working. `supreme_main.py` itself remains importable
and forwards to the new entry point.

---

## 6. HTTP / WebSocket surface

```text
GET  /dashboard           → Singularity dashboard (HTML)
GET  /singularity         → Unified registry + subsystem snapshot (JSON)
POST /api/jarvis/ask      → Single-shot Q&A
POST /api/jarvis/create   → Multimodal artefact bundle
WS   /ws/jarvis           → Streaming chat REPL
GET  /spatial, WS /ws/spatial → existing spatial HUD (unchanged)
GET  /, /api/* …          → existing chat/skills/sessions APIs (unchanged)
```

---

## 7. Test status

* `pytest runtime/tests/` — must stay green; the JARVIS One suites
  add `test_singularity.py` plus per-subsystem tests under
  `runtime/tests/test_jarvis_one_*.py`.

Run:

```bash
cd runtime
pytest -q
```

---

## 8. Final deliverables

* Clean repo root: `runtime/`, the 22 persona category folders,
  `scripts/`, `docs/`, `integrations/`, `JARVIS.md`, `README.md`,
  `LICENSE`, `ATTRIBUTIONS.md`, `SECURITY.md`, `CONTRIBUTING*.md`.
* One command to rule them all: `agency singularity`.
* One dashboard at `http://localhost:8765/dashboard` showing every
  agent live.
* One markdown file telling the whole story — this one.

— *Amjad Mobarsham, sole owner.*
