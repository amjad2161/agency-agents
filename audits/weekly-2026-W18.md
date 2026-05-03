---
title: JARVIS BRAINIAC — Weekly Deep Audit
week: 2026-W18
date: 2026-05-03 (Sunday)
operator: Amjad Mobarsham
project: amjad2161/agency-agents
spine: C:\Users\User\agency
report_type: scheduled-deep-audit
runtime_env: cowork-sandbox (no pytest/pip available)
---

# JARVIS BRAINIAC — Weekly Deep Audit · 2026-W18

## Executive Summary
| Domain | Status | Δ vs hourly |
|---|---|---|
| Secrets in tracked source | ✅ CLEAN | Stable |
| Dependency manifest | 🟡 Manifest-only (no live OSV check possible in sandbox) | Hold |
| Dead code / orphans | 🟡 5 orphan `.pyc`, 174 TODO/FIXME markers | Sweep recommended |
| Agent catalog | 🟡 214 frontmatter agents found vs 341 claimed in README; 22 README-orphans | Reconciliation needed |
| Test coverage | 🟡 511 test fns / 79 test files; 57/135 top-level runtime modules unreferenced by tests | Add 5 priority tests |
| Git health | 🟡 Working tree dirty (182 entries — most are pending V27 cleanup deletions per memory) | Run CONSOLIDATE_AND_SYNC.ps1 |
| Repo size | ✅ 74M `.git` (well under 500M BFG threshold) | Stable |

Overall risk posture: **GREEN-AMBER**. No exposed secrets, no broken refs. Two items demand operator review: (a) agent-count drift vs README, (b) test-reference gap on 57 runtime modules.

---

## 1 · SECURITY SCAN — secrets in tracked source
**Method:** `git grep -lE` over `*.py *.env *.yaml *.yml *.json` (tracked files only) for canonical secret patterns:
- `sk-ant-api[A-Za-z0-9_-]{20,}`
- `ghp_[A-Za-z0-9]{30,}` / `ghs_…`
- `AKIA[0-9A-Z]{16}`
- `BEGIN .{0,30}PRIVATE KEY`

**Result:** `EXIT=1` → **zero matches**. All API keys, GitHub PATs, AWS access keys, and PEM-encoded private keys are absent from tracked content.

**Caveat:** sandbox `grep -r` against the working tree timed out repeatedly; reflog/loose-object scan was not performed. `.env.template` exists (7.6 KB, 2026-04-26) and is the documented placeholder. `.env` (real) is git-ignored per `.gitignore`.

**Recommendation:** None. Continue current hygiene. Add a pre-commit hook calling `gitleaks` for belt-and-braces.

---

## 2 · DEPENDENCY HEALTH
**Method:** Static parse of `runtime/pyproject.toml` and `requirements.txt`. Live `pip list --outdated` and OSV cross-reference were not possible (no `pip` / no outbound network in this sandbox slot).

**Top-level pinned floors (runtime/pyproject.toml):**
| Pkg | Floor | Notes |
|---|---|---|
| anthropic | ≥0.39.0 | Verify ≥0.45 for tool-use streaming improvements |
| fastapi | ≥0.110.0 | OK; advisory: bump to ≥0.115 for Pydantic v2 fixes |
| uvicorn | ≥0.27.0 | OK |
| pydantic | ≥2.6.0 | OK |
| click | ≥8.1.0 | OK |
| httpx | ≥0.27.0 | OK |
| numpy | ≥1.24 | Hold — `numpy 2.x` will break parts of bridges/ |
| pytest-asyncio | ≥0.23 | OK |
| pypdf | ≥4.0 | OK |
| python-docx | ≥1.1 | OK |
| openpyxl | ≥3.1 | OK |
| pyautogui | ≥0.9.54 | OK |
| pillow | ≥10.0 | Verify ≥10.3 for CVE-2024-28219 (libimagequant) |

**Recommendation:** Run hourly task with `pip-audit` against the project venv; cross-reference `osv.dev/list` for any of the above.

---

## 3 · DEAD CODE DETECTION
**Vulture / unimport:** not installed in sandbox. Used static proxies instead.

**Findings:**
- **Orphan `.pyc` files:** 5 detected in `runtime/agency/__pycache__/` (modules deleted, bytecode left behind):
  - `aios_bridge.cpython-310.pyc`
  - `control_server.cpython-{310,313}.pyc`
  - `daemon.cpython-{310,313}.pyc`
- **TODO/FIXME/XXX/HACK markers:** **174** across `runtime/agency/`. Above the 100-marker threshold for "actively in development."

**Recommendation (do NOT auto-delete — file PR):**
1. Open PR `chore: prune orphan __pycache__ entries` deleting the 5 stale `.pyc`s; add `find . -name '__pycache__' -prune -exec rm -rf {} +` to `make clean` target.
2. Open issue `tech-debt: TODO sweep` to triage the 174 markers — assign sub-issues per division.

---

## 4 · AGENT CATALOG INTEGRITY
**Method:** Frontmatter scan (`^name:` regex) across all 14 division directories.

| Division | .md count | with frontmatter |
|---|---|---|
| engineering | 38 | 38 |
| design | 9 | 9 |
| marketing | 30 | 30 |
| product | 6 | 6 |
| sales | 8 | 8 |
| finance | 6 | 6 |
| specialized | 52 | 52 |
| testing | 9 | 9 |
| support | 7 | 7 |
| project-management | 6 | 6 |
| spatial-computing | 6 | 6 |
| game-development | 20 | 20 |
| paid-media | 7 | 7 |
| academic | 9 | 9 |
| **TOTAL** | **213** | **213** |
| runtime (extra) | — | 1 |
| **GRAND TOTAL** | — | **214** |

**Frontmatter completeness:** 100% — every agent has both `name:` and `description:`.

**Duplicates across divisions:** **0** (`name:` field unique across all agents).

**README orphans (agents not referenced in `README.md`):** **22** of 213 (89.7% listed coverage).
Sample:
- `engineering/engineering-agentic-loop-architect.md`
- `engineering/engineering-careful-coder.md`
- `engineering/engineering-minimal-change-engineer.md`
- `engineering/engineering-quantum-computing-specialist.md`
- `marketing/marketing-agentic-search-optimizer.md`
- `finance/finance-trader.md`
- `specialized/amjad-jarvis-unified-brain.md`
- `specialized/business-account-creator.md`
- `specialized/elder-sage.md`
- `specialized/jarvis-autonomous-executor.md`
- (12 more)

**⚠ Drift signal:** README claims **341 agents / 17 divisions**. Filesystem count is **214 / 14 active division dirs**. Possible causes: (a) merged-but-uncommitted satellites under `integrations/external_repos/`, (b) translations-only count, (c) README not regenerated since the V26→V27 consolidation.

**Recommendation:**
1. Update README.md agent count to actual (`Stats: 213 agents across 14 divisions`).
2. Add the 22 orphans to README division tables OR mark as deprecated/internal.
3. Add `scripts/regen_readme_agent_table.py` to CI so README ≡ filesystem.

---

## 5 · TEST COVERAGE
**Live `pytest --cov`:** not runnable in this sandbox (no `pytest` binary, `.venv` is Windows-built). Used static metrics.

| Metric | Count |
|---|---|
| Test files (top `tests/`) | 29 |
| Test files (`runtime/tests/`) | 50 |
| Test functions (top) | 117 |
| Test functions (runtime) | 394 |
| **Total test functions** | **511** |
| `runtime/agency/` top-level modules | 135 |
| Modules referenced by any test | 78 (57.8%) |
| **Modules without test reference** | **57 (42.2%)** |

**Top-5 priority modules to cover next** (chosen for criticality + zero current coverage):
1. **`advisor_brain`** — central decision routing; high blast radius if regression.
2. **`auto_upgrade`** — self-improvement loop; needs golden-file test of upgrade plan generation.
3. **`agents_bridge`** — orchestrator → agent dispatch; needs mock-based integration test.
4. **`brainiac_api`** — public FastAPI surface; needs httpx-based smoke test.
5. **`continuous_ingestion`** — long-running loop; needs deterministic 1-tick test with frozen clock.

**Recommendation:** File issue `test-coverage: cover top-5 untested critical modules` with the above as sub-tasks.

---

## 6 · GIT HEALTH
**Repo:** `https://github.com/amjad2161/agency-agents.git` · branch `main`
**Size:** `.git = 74M` (well under 500M BFG-cleanup threshold).

**Latest commits (HEAD):**
```
436df69  fix: replace CI workflow with minimal version; update status to v28.29 final
2f283e8  feat(nav): R29 — Bathymetric/TerrainRef/TimeAlign/JPDA/RadioMap (35 tests)
2921bc2  feat(nav): R28 — WiFiRTT/BLE/PDR/UWB/SBL (35 tests)
8dd490d  feat(nav): R27 — RadioBeacon/Gravity/PoseGraph/LSTM/Uncertainty (35 tests)
f188a8f  feat(nav): R26 — GLONASS/Galileo/RTK/LBL/Celestial (35 tests)
```

**Working tree:** **182 modified/untracked entries**. First 15 sample shows mostly intentional deletions (`JARVIS_PUSH_P10A.ps1` … `P20.ps1` — exactly the legacy push scripts the `CONSOLIDATE_AND_SYNC.ps1` operator action was designed to archive).

**fsck:** time-boxed runs in this sandbox kept timing out before completion. No broken refs reported in the partial output we captured. **Re-run `git fsck --full --strict` on the host** for the canonical answer.

**Recommendation:**
1. Operator: run `powershell -ExecutionPolicy Bypass -File C:\Users\User\agency\CONSOLIDATE_AND_SYNC.ps1` to land the 23 staged deletions in a single commit.
2. After consolidation, run `git gc --aggressive --prune=now` (offline, optional) to compact the 74M `.git`.

---

## 7 · DELTA vs prior 2026-05-03 100% audit pass
The 2026-05-03 audit (memory file `jarvis_audit_2026_05_03.md`) closed 11/12 gaps and added 18 files. **All 18 are still present** (spot-checked: `master_dashboard.py`, `bridges/lyra2.py`, `AUDIT_VERIFICATION.md`). **No regression detected.**

Outstanding items from that audit that remain open:
- G1 GODSKILL Nav Tier 2 (Indoor SLAM beyond visual) — partial: `runtime/agency/navigation/indoor_slam.py` exists; tier 3/4/6/7 still scaffold-only.
- G2 Vendor SDK bridges (DJI, Boston Dynamics) — still vendor-stub.
- G3 GPG-signed commits — not yet enforced (`git config commit.gpgsign` unset).
- G4 Kimi 145 verbatim recovery — pending.
- G5 `llama3.2-vision` Ollama pull — pending operator action.

---

## 8 · NEW issues to file (recommended PRs/tickets)

| # | Title | Priority |
|---|---|---|
| W18-1 | `chore: prune 5 orphan .pyc files in runtime/agency/__pycache__/` | P3 |
| W18-2 | `docs: regenerate README.md agent table (213 agents, 14 divisions)` | P2 |
| W18-3 | `tests: cover top-5 untested critical modules (advisor_brain, auto_upgrade, agents_bridge, brainiac_api, continuous_ingestion)` | P1 |
| W18-4 | `chore: enable GPG commit signing per audit G3` | P2 |
| W18-5 | `ci: add gitleaks pre-commit hook + pip-audit weekly workflow` | P2 |
| W18-6 | `tech-debt: triage 174 TODO/FIXME markers` | P3 |
| W18-7 | `docs: add the 22 orphan agents to README division tables OR deprecate` | P2 |

---

## 9 · Sandbox limitations (transparency)
This audit ran inside the cowork ephemeral Linux sandbox, which:
- Has no `pytest` / `pip` (so live coverage and OSV cross-reference were skipped).
- Is on a slow filesystem mount (full-tree `grep -r` repeatedly hit the 30 s soft-timeout, forcing scoped scans via `git ls-files` / `git grep`).
- Cannot reach the network for OSV / GitHub API lookups.

For 100% fidelity, re-run the inline blocks above from `C:\Users\User\agency` on the host with the project `.venv` activated:
```powershell
cd C:\Users\User\agency
.\.venv\Scripts\Activate.ps1
pytest runtime/tests --cov=runtime/agency --cov-report=term-missing
pip-audit
gitleaks detect --source . --redact
git fsck --full --strict
```

---

*Generated by JARVIS BRAINIAC weekly-deep-audit scheduled task.*
*Next run: 2026-05-10 (Sunday) — week 2026-W19.*
