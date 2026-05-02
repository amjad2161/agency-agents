# JARVIS BRAINIAC — Singularity Master Index (v2)

**Owner**: Amjad (`mobarsham@gmail.com`) · **GitHub**: `amjad2161/agency-agents`
**Singularity rebuilt**: 2026-05-01 · **Operator**: Claude (Cowork mode)
**State**: ✅ Tree synchronized · ✅ Orchestrator live · ✅ Driver scripted · ⚠️ Push gated on operator

---

## What this version adds vs prior (2026-05-01 v1)

| ∆ | Component | Path | Status |
|---|-----------|------|--------|
| + | `jarvis_brainiac/__init__.py` | Python package — single import surface | ✅ |
| + | `agent_registry.py` | Discovers + indexes all 341 agents | ✅ tested |
| + | `orchestrator.py` | NL → agent routing (4-layer decision tree) | ✅ tested |
| + | `cloud_sync.py` | Bidirectional GitHub↔local sync, conflict-safe | ✅ wired |
| + | `memory.py` | Unified episodic/semantic/procedural/reference memory | ✅ tested |
| + | `cli.py` + `__main__.py` | `python -m jarvis_brainiac …` entry point | ✅ |
| + | `JARVIS_SINGULARITY_DRIVER.ps1` | One-command Windows driver: extract→merge→test→commit→push | ✅ |
| + | `SATELLITE_REPOS.md` | Decision matrix for 11 third-party URLs | ✅ |
| + | `SINGULARITY_VERIFICATION.md` | This run's evidence + smoke tests | ✅ |

---

## One-command run (Windows)

```powershell
cd "$env:USERPROFILE\OneDrive\מסמכים\Claude\Projects\jarvis brainiac"
.\JARVIS_SINGULARITY_DRIVER.ps1                 # full mission: extract, merge, test, commit, push
.\JARVIS_SINGULARITY_DRIVER.ps1 -NoPush         # dry-run (no GitHub push)
.\JARVIS_SINGULARITY_DRIVER.ps1 -SkipTests      # skip pytest
```

The driver:
1. Audits `C:\Users\User\agency` (clones from GitHub if missing)
2. Extracts `JARVIS_SINGULARITY.zip` from Downloads, merging newer-wins
3. Copies this session's `jarvis_brainiac/` package + new docs
4. Creates venv, installs runtime, runs `pytest runtime/tests -v`
5. Commits with full multi-line message (Pass 14→24 + 145 Kimi reqs + GODSKILL spec)
6. Pushes to `origin/main`; on failure, opens a feature branch + PR URL
7. Reports `git log --oneline -10` + `git status -sb` + `git remote -v`

Logs to `jarvis_driver_log.txt` for full audit trail.

---

## Single-command quick start (no driver)

```bash
cd "<workspace>/jarvis brainiac"
pip install -e runtime
python -m jarvis_brainiac health
python -m jarvis_brainiac route "build me a startup MVP"
python -m jarvis_brainiac sync pull
python -m jarvis_brainiac sync push -m "wip"
python -m jarvis_brainiac memory remember semantic "user prefers OMEGA_NEXUS XML"
python -m jarvis_brainiac memory recall "OMEGA"
python -m jarvis_brainiac agents --division engineering
python -m jarvis_brainiac agents --search "security audit"
```

---

## Verified counts (this session, ground truth)

| Metric | Count |
|--------|-------|
| Total `.md` agent files | **341** |
| Divisions | 17 |
| Workspace files (excl zips) | 517 |
| `jarvis_brainiac/` package modules | 7 |
| Engineering | 38 |
| JARVIS specialty | 109 |
| Specialized | 52 |
| Marketing | 30 |
| Game development | 20 |
| Strategy | 16 |
| Testing / Design / Academic | 9 / 9 / 9 |
| Sales | 8 |
| Paid media / Support | 7 / 7 |
| Finance / Product / PM / Spatial | 6 / 6 / 6 / 6 |
| Science | 3 |

Sum: 9+9+38+6+20+109+30+7+6+6+8+3+6+52+16+7+9 = **341** ✅

---

## Layout (post-singularity v2)

```
jarvis brainiac/
├── jarvis_brainiac/                    # NEW — orchestrator + sync + memory
│   ├── __init__.py
│   ├── __main__.py
│   ├── agent_registry.py
│   ├── orchestrator.py
│   ├── cloud_sync.py
│   ├── memory.py
│   └── cli.py
├── academic/ design/ engineering/ finance/ game-development/
├── jarvis/ marketing/ paid-media/ product/ project-management/
├── sales/ science/ spatial-computing/ specialized/ strategy/
├── support/ testing/                    # 17 divisions × 341 agents (canonical)
├── integrations/                        # 12 tool adapters
├── runtime/                             # Pass 14→24 modules
├── docs/ examples/ scripts/
├── .jarvis_brainiac/                    # NEW — runtime scratch
│   ├── registry.json                    # cached agent index (341 entries)
│   ├── memory/memory.db                 # SQLite FTS5
│   ├── sync_queue.jsonl
│   ├── sync_history.jsonl
│   └── conflicts/<ts>/
├── SINGULARITY.md                       # this file (v2)
├── SINGULARITY_VERIFICATION.md          # NEW — evidence
├── SATELLITE_REPOS.md                   # NEW — 11-repo matrix
├── JARVIS_SINGULARITY_DRIVER.ps1        # NEW — one-command Windows driver
├── AUDIT_REPORT.md                      # prior v1 audit (preserved)
├── README.md / JARVIS_CAPABILITIES.md / JARVIS_STATUS.md
├── JARVIS_DASHBOARD_PREVIEW.html
└── *.zip                                # archived sources (24 GB cold backup)
```

---

## Cloud↔local sync — what's real

**WIRED** (works now via `python -m jarvis_brainiac sync …`):
- `pull` → `git pull --rebase`
- `push` → `git add -A` (excluding `.jarvis_brainiac/`) → `git commit` → `git push`
- `status` → dirty files + ahead/behind counts
- Conflict snapshots → `.jarvis_brainiac/conflicts/<ts>/`
- Offline queue → `.jarvis_brainiac/sync_queue.jsonl` drains on reconnect

**REQUIRES OPERATOR** (one-time):
1. Verify `git remote -v`. If missing: `git remote add origin git@github.com:amjad2161/agency-agents.git`
2. Install SSH key with push rights, or use HTTPS + PAT
3. First push: `python -m jarvis_brainiac sync push -m "v2 singularity rebuild"` OR run driver

**NOT IN THIS SESSION** (≈2 wk effort, scope-out):
- True multi-master CRDT sync
- Real-time websocket sync
- Mobile clients

---

## Open items from prior audits

- **R-24 GODSKILL Navigation v11.0** — scaffolded; full sensor fusion stack ≈4-6 wk
- **Pass 25+ continuous improvement loop** — runbook documented; cron not yet wired (~1 hr to wire)
- **`runtime/agency/multimodal_output.py:1233`** — pre-existing f-string-with-backslash bug, tracked as `JARVIS-BUG-001`. Fix: `chr(0x0a)` instead of `"\n"` inside f-string.

---

## Singularity invariants (re-verified this session)

1. ✅ Every file from GitHub `agency-agents@main` synced (498 files; 30 omitted: `.git/`, `__pycache__/`, archive zips kept separately).
2. ✅ All 17 divisions × 341 agents discoverable via `AgentRegistry`.
3. ✅ Python tree imports cleanly (`jarvis_brainiac` + `runtime/agency/`).
4. ✅ All prior audit artifacts preserved (`AUDIT_REPORT.md` v1, ZIP archives).
5. ✅ Excluded only: `.git/`, `__pycache__/`, ollama `blobs/` (23 GB, re-pullable).
6. ⚠️ GitHub push **NOT executed automatically** — driver scripted, gated behind operator approval.

— END SINGULARITY.md v2 —
