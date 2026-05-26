---
title: JARVIS BRAINIAC — Weekly Deep Audit
week: 2026-W19
date: 2026-05-06 (Wednesday — scheduled-task autonomous run, supersedes Tue draft → weekly-2026-W19-tue.md)
operator: Amjad Mobarsham (mobarsham@gmail.com)
project: amjad2161/agency-agents · spine `C:\Users\User\agency`
HEAD: 30cd506 (fix: W18-12 layout-agnostic CLI smoke)
upstream: origin/main · ahead 1 / behind 0
generator: scheduled-task `jarvis-weekly-deep-audit` · sandbox kind-lucid-heisenberg
---

# JARVIS BRAINIAC — Weekly Deep Audit · 2026-W19 (Wed re-run)

## 0. Run metadata
- ISO Week 19, Year 2026 · 2026-05-06 05:08 UTC
- Operator absent (autonomous scheduled run); reasonable-choice mode active
- Prior W19 audit (Tue 2026-05-05) preserved as `weekly-2026-W19-tue.md`
- Sandbox limitations called out inline; nothing skipped silently

## 1. Executive summary
| Metric | Status | Δ vs W18 |
|---|---|---|
| Secret patterns (sk-ant, sk-proj, ghp_, ghs_, AKIA, PEM) in *.py/*.md/*.json/*.env | ✅ 0 hits | = |
| Agents with valid frontmatter (322 division .md, JARVIS/README.md excluded) | ✅ 321 / 322 | = |
| Duplicate `name:` across catalog | ✅ 0 | = |
| README.md orphans (agent name not referenced) | 🟡 133 / 322 (41%) | = (carried) |
| Vulture dead-code @100% confidence | 🟡 50 hits | = |
| Vulture dead-code @≥80% confidence | 🟡 164 hits | = |
| Pytest collection (runtime/tests) | ✅ 3 627 cases collected | new metric |
| `git fsck --full --strict` | ✅ no broken refs (dangling-only) | = |
| `.git` size | ✅ 113 MB (cap 500 MB) | = |
| Working tree drift | 🔴 91 modified, 53 untracked | (drift growing) |
| HEAD vs origin/main | 🟡 ahead 1 (Tue audit commit not pushed) | = |

**Risk colour**: 🟡 amber — no security blockers, but working-tree drift + orphan ratio + dead-code backlog need disposition.

---

## 2. Security scan
### 2.1 Method
```
grep -rEln 'sk-ant-[A-Za-z0-9_-]{20,}|sk-proj-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{36}|ghs_[A-Za-z0-9]{36}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]+PRIVATE KEY-----' \
  --include=*.py --include=*.md --include=*.json --include=*.env  ~/agency
```
### 2.2 Result
- **0 hits** across tracked source.
- `.env.template` reviewed manually → placeholder vars only, no live secrets.
- Recommendation: add `gitleaks` pre-commit hook to lock this metric at zero (next sprint).

---

## 3. Dependency health
### 3.1 Method
- `pip list --outdated` against sandbox base (Python 3.10.12) — **NOT** the production .venv on Windows.
- `requirements.txt` and `runtime/pyproject.toml` reviewed for pin drift.

### 3.2 Findings (sandbox baseline only — informational)
Unbounded floors on critical libs (`anthropic>=0.39.0`, `fastapi>=0.110.0`, `uvicorn>=0.27.0`, `pydantic>=2.6.0`, `httpx>=0.27.0`, `numpy>=1.24`).  No upper caps → reproducible-build risk. Sample outdated in sandbox base: cryptography 46→48, jinja2 3.0.3→3.1.6, jsonschema 3.2.0→4.26.0, importlib-metadata 4.6.4→9.0.0.

### 3.3 Recommendations
1. Run `pip list --outdated` inside the production Windows `.venv` and append the output to `audits/deps-w19.txt` next cycle.
2. Add `pip-audit` (PyPI) and cross-reference https://osv.dev/list?ecosystem=PyPI for live CVEs — sandbox WebFetch was not exercised this run to keep run under timeout.
3. Pin upper bounds in `runtime/pyproject.toml` (e.g. `anthropic>=0.39,<1.0`, `pydantic>=2.6,<3.0`).
4. Schedule a `dependabot.yml` for weekly PRs — single-file ROI > manual scan.

---

## 4. Dead-code detection (vulture)
### 4.1 Artifacts
- `audits/vulture-100-w19.txt` — 50 high-confidence (100%) findings
- `audits/vulture-80-w19.txt` — 164 ≥80% confidence findings

### 4.2 Top files by 100% confidence count
| Count | File |
|---|---|
| 6 | runtime/agency/multi_agent_orchestrator.py |
| 6 | runtime/agency/local_vision.py |
| 6 | runtime/agency/external_integrations/gemini_computer_use_bridge.py |
| 6 | runtime/agency/external_integrations/autogpt_bridge.py |
| 4 | runtime/agency/expert_personas.py |
| 3 | runtime/agency/hybrid_cloud.py |
| 3 | runtime/agency/external_integrations/supersplat_bridge.py |
| 2 | runtime/agency/financial_dominance.py |
| 1 | runtime/agency/supreme_main.py |
| 1 | runtime/agency/simple_server.py |

### 4.3 Pattern observed
- Most are unused `__exit__` parameters (`exc_type`, `exc_val`, `exc_tb`) → safe to silence with `_` prefix; no logic change.
- A handful are unused imports in bridges (defensive imports for optional features) → keep, document with `# noqa: F401`.

### 4.4 Action — **DO NOT auto-delete** (per task spec)
Open PR `chore/dead-code-w19` with two commits:
1. Rename `__exit__` placeholders to `_exc_type`/`_exc_val`/`_exc_tb` across `autogpt_bridge.py`, `gemini_computer_use_bridge.py`, `multi_agent_orchestrator.py`. ~24 LOC delta, zero behavioral change.
2. Annotate intentional unused-imports with `# noqa: F401  # optional-dep guard`.

Defer `expert_personas.py` unreachable-`else` (4 hits) to a focused review — likely refactor of a `match` block.

---

## 5. Agent catalog integrity
### 5.1 Per-division counts (top-level dirs only)
```
engineering         38
design               9
product              6
marketing           30
sales                8
finance              6
support              7
testing              9
specialized         52
JARVIS             109
academic             9
project-management   6
spatial-computing    6
paid-media           7
game-development    20
                  ─── total 322
```

### 5.2 Frontmatter
- 322 / 322 contain `name:` and `description:` fields.
- 1 file (`JARVIS/README.md`) lacks `---`-delimited frontmatter — **expected** (it's a division README, not an agent). Not flagged.

### 5.3 Duplicates
- `awk` over `name:` field across 322 files → **0 duplicates**.

### 5.4 README orphans
- 133 of 322 agent `name:` strings do not appear in `README.md`.
- Likely the active README still reflects the original ~140-agent roster and has not been re-generated since the JARVIS division blew up to 109 sub-agents.
- **Action**: regenerate README division tables from the catalog (script `scripts/render_readme.py` if present, else add).

---

## 6. Test coverage
### 6.1 Inventory
- 67 `test_*.py` files in `runtime/tests/`
- **3 627 test cases collectable** after installing missing runtime deps in sandbox (`anthropic`, `fastapi`, `uvicorn`, `pydantic`, `httpx`, `pyyaml`).
- This is the inventory; live `--cov` could not run inside the 45s/call sandbox window.

### 6.2 Sandbox limitation
- The 45-second-per-call sandbox cap rules out a full `pytest --cov` pass (3 627 cases would exceed the budget). Run on the operator's Windows `.venv` for the canonical coverage delta.
- Recommended invocation:
  ```
  cd C:\Users\User\agency
  .\.venv\Scripts\pytest runtime/tests --cov=runtime/agency --cov-report=term-missing --cov-report=json:audits/coverage-w19.json
  ```

### 6.3 Top-5 modules to prioritise tests for (heuristic — no live coverage this run)
Based on (a) LOC, (b) presence in vulture findings (= likely under-exercised), (c) bridge-criticality:
1. `runtime/agency/windows_god_mode.py` (2 380 LOC) — no dedicated test file in inventory
2. `runtime/agency/window_manager_3d.py` (1 621 LOC) — same
3. `runtime/agency/vr_perception_engine.py` (1 330 LOC) — `test_vr_perception.py` not present
4. `runtime/agency/external_integrations/autogpt_bridge.py` — 6 dead-code hits, signals stale tests
5. `runtime/agency/external_integrations/gemini_computer_use_bridge.py` — same pattern

---

## 7. Git health
| Check | Result |
|---|---|
| `git fsck --full --strict` | ✅ no broken refs |
| Dangling objects | 15+ dangling commits/blobs (from rebases) — non-fatal |
| `.git` size | 113 MB (cap 500 MB) — healthy |
| Branch | `main` |
| Remote | `https://github.com/amjad2161/agency-agents.git` |
| HEAD | `30cd506` (W18-12 fix) |
| HEAD vs origin/main | **ahead 1, behind 0** — Tue audit commit needs push |
| Working-tree drift | 🔴 91 modified files + 53 untracked (high) |

### 7.1 Action
1. `git push origin main` to flush the 1 ahead commit.
2. Triage the 91 modified / 53 untracked working-tree entries — many are sandbox cache artefacts (`.coverage*`, `__pycache__`, `:memory:`, `audits/weekly-*.md` re-edits). Add tighter `.gitignore` rules in next sprint.
3. Optional `git gc --prune=now --aggressive` after dangling-commit triage; not urgent at 113 MB.
4. BFG cleanup **not** required (well under 500 MB threshold).

---

## 8. Recent commit log (HEAD-8)
```
30cd506 fix: W18-12 — make test_jarvis_pass8::TestCLISmoke layout-agnostic
8646dff audit: W18 + 5 F821 + 12 W18-10 bandit HIGH fixes (24→12)
6b9e6e4 audit: weekly deep audit week 2026-W18 + 5 F821 fixes
87a55c7 feat: 100% v33 integrated + HUD + 5 satellites + audit verification + 1458 tests pass
436df69 fix: replace CI workflow with minimal version; update status to v28.29 final
2f283e8 feat(nav): R29 — BathymetricMapMatcher, TerrainReferencingNavigator, ...
2921bc2 feat(nav): R28 — WiFiRTTPositioner, BLEBeaconPositioner, PedestrianDeadReckoning, ...
8dd490d feat(nav): R27 — RadioBeaconTriangulator, GravityAnomalyNavigator, PoseGraphSLAM, ...
```

---

## 9. Disposition / next-week W20 punch list
| # | Item | Owner | Priority |
|---|---|---|---|
| 1 | Push pending HEAD to origin/main | scheduler | P0 |
| 2 | Open PR `chore/dead-code-w19` (50 high-conf vulture hits) | scheduler | P1 |
| 3 | Regenerate README division tables (close 133 orphans) | operator | P1 |
| 4 | Add `pip-audit` + `dependabot.yml` | operator | P1 |
| 5 | Pin upper bounds on critical deps in `runtime/pyproject.toml` | operator | P2 |
| 6 | Run live `pytest --cov` on Windows venv → `audits/coverage-w19.json` | operator | P2 |
| 7 | Triage working-tree drift (91 modified / 53 untracked) | operator | P2 |
| 8 | Add `gitleaks` pre-commit hook | scheduler | P2 |
| 9 | Carry-over: 12 outstanding W18-10 bandit MED items | operator | P2 |

---

## 10. Sandbox-honesty appendix
What I could **not** verify inside the 45 s/bash sandbox cap:
1. Live `pytest --cov` execution (3 627 cases > budget).
2. Live OSV.dev cross-reference for CVE matches (timeout risk).
3. Production `.venv` outdated-package list (Windows-only path).
4. `git push` to remote (deferred to §11 with explicit best-effort).

Each of the above is addressable on the operator's Windows host with the commands listed in §3.3, §6.2, §7.1.

## 11. Auto-commit attempt — ⚠️ BLOCKED
- `git add` and `git commit` both returned `fatal: Unable to create '.git/index.lock': File exists.`
- Lock file: `.git/index.lock` (0 bytes), timestamp **2026-05-03 20:43** — i.e. 3 days stale.
- Sandbox `rm -f` returned **`Operation not permitted`** on this OneDrive-mounted path; the lock is held at the Windows ACL layer.
- Resolution requires one Windows-side command — full instructions and a copy-paste block live in `audits/NOTIFY-W19-deep.md` (mirror) and the operator-facing notification.
- Net: report and artefacts are written and ready to commit; commit + push are deferred to the operator (≤ 60 s of work).

## 12. Operator notification
Written to:
- `C:\Users\User\OneDrive\מסמכים\Claude\Projects\jarvis brainiac\audits\NOTIFY-W19-deep.md`

Includes: TL;DR, headline metrics, the unblock-and-push PowerShell block, and the W20 top-5 punch list.
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           