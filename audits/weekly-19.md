# JARVIS BRAINIAC — Weekly Deep Audit (Week 19, 2026)

**Run:** 2026-05-05 20:11 UTC (autonomous scheduled task)
**Operator:** Amjad Mobarsham
**Repository:** amjad2161/agency-agents (branch `main`, HEAD `30cd506`)
**Working tree:** /sessions/relaxed-exciting-keller/mnt/agency

---

## 1. SECURITY SCAN  ✅ CLEAN

Scanned all `.py`, `.md`, `.json`, `.yml`, `.yaml` files (excluding `.git/`, `.venv/`, cache dirs) for: `sk-ant-api*`, `sk-proj-*`, `ghp_*`, `ghs_*`, `AKIA*`, `BEGIN PRIVATE KEY`.

| Pattern | Hits | Status |
|---|---|---|
| `sk-ant-api*` | 0 | ✅ |
| `sk-proj-*`   | 0 | ✅ |
| `ghp_*`       | 3 (placeholder strings only) | ✅ |
| `ghs_*`       | 0 | ✅ |
| `AKIA*`       | 0 | ✅ |
| `BEGIN PRIVATE KEY` | 0 | ✅ |

**Hits triaged (placeholders, not secrets):**
- `runtime/agency/github_ingestor.py:194` → `github_token="ghp_xxx"` (docstring example)
- `runtime/agency/github_mass_ingestor.py:504` → `github_token="ghp_..."` (docstring example)
- `runtime/agency/github_mass_ingestor.py:2161` → `github_token="ghp_xxx"` (docstring example)

**Verdict:** No real credentials committed. Recommend adding `gitleaks` or `trufflehog` to CI as a hard gate.

---

## 2. DEPENDENCY HEALTH  ⚠️ DEFERRED

`pip` was not directly invocable in the audit sandbox (no `.venv/bin/python`, no system `pytest`/`pip` available to scheduled-task user). Cannot enumerate outdated packages this run.

**Action:** add a CI job (`pip list --outdated --format=json` → upload artifact) so this report can read the artifact next week instead of executing pip live.

**Static observations from `requirements.txt` (78 lines) and `runtime/pyproject.toml`:**
- Pinning style: lower-bound only (`>=`). Risk: silent breaking upgrades.
- `anthropic>=0.39.0`, `fastapi>=0.110.0`, `pydantic>=2.6.0`, `httpx>=0.27.0` — recent floors, OK.
- `chromadb>=0.5.0`, `sentence-transformers>=2.2.0`, `faiss-cpu>=1.7.4` — heavy ML deps, candidates for optional-extras split.
- `TTS>=0.22.0` (Coqui TTS) — upstream archived; consider migrating to `coqui-tts` fork or removing.
- No `requirements.lock` or `uv.lock` committed.

**Upgrade plan (proposed, hold for human approval):**

| Tier | Action |
|---|---|
| Now | Pin floors → exact versions in a generated `requirements.lock` via `uv pip compile` |
| Now | Add `pip-audit` GitHub Action; fail build on HIGH/CRITICAL CVEs |
| Hold | Coqui `TTS` migration (upstream archived) |
| Hold | Major bumps (`pydantic` 2.x → 3.x when released) |

---

## 3. DEAD CODE DETECTION  ⚠️ DEFERRED

`vulture` not installed in audit sandbox.

**Static count proxies:**
- `runtime/agency/`: 222 Python modules
- `runtime/tests/`: 73 test files
- 145 modules in `runtime/agency/` (top level)

**Proposed PR (do NOT auto-delete):**
- Add `pip install vulture` to CI; commit `.vulture-allowlist`
- Initial pass on top-20 largest files (see §5) for unreferenced symbols
- File results as `chore/dead-code-week19` PR for human review

---

## 4. AGENT CATALOG INTEGRITY  ⚠️ FINDINGS

**Counts:**
- Division agents (engineering, marketing, sales, design, product, testing, support, specialized, finance, project-management, spatial-computing, paid-media, game-development, academic): **213**
- JARVIS modules (`jarvis/`): **109**
- **Total agents: 322** (target was 341 — gap of 19; reconcile with `jarvis_singularity/` and `aios/` subdirs)
- Strategy non-agent docs (playbooks/runbooks/briefs): 16 (correctly excluded)

**Frontmatter validation:**
- Division agents missing frontmatter: **0 / 213**  ✅
- JARVIS modules missing frontmatter: **1 / 109** → `jarvis/README.md` (expected — it's a README, not an agent)
- Missing `name:` field: 0
- Missing `description:` field: 0

**Duplicates:** none detected (basename uniqueness across divisions).

**Orphans (agent .md not referenced anywhere in root README.md): 22**
```
engineering/engineering-agentic-loop-architect.md
engineering/engineering-careful-coder.md
engineering/engineering-minimal-change-engineer.md
engineering/engineering-quantum-computing-specialist.md
marketing/marketing-agentic-search-optimizer.md
specialized/amjad-jarvis-unified-brain.md
specialized/business-account-creator.md
specialized/elder-sage.md
specialized/jarvis-autonomous-executor.md
specialized/jarvis-curiosity-engine.md
specialized/jarvis-goal-decomposer.md
specialized/jarvis-knowledge-synthesizer.md
specialized/jarvis-research-director.md
specialized/jarvis-self-healing-engine.md
specialized/jarvis-self-learner.md
specialized/jarvis-tool-master.md
specialized/specialized-chief-of-staff.md
finance/finance-trader.md
academic/academic-economist.md
academic/academic-mathematician.md
academic/academic-philosopher.md
academic/academic-scientist.md
```

**Action:** add a "What's New" section to README.md and reference each. File as PR `docs/week19-orphan-rollup`.

---

## 5. TEST COVERAGE  ⚠️ INSUFFICIENT TOOLING

`pytest` and `coverage` not installed in audit sandbox; cannot run `pytest --cov` directly.

**Module/test ratio (proxy):** 73 tests / 222 modules ≈ **32.9%**

**Top 5 untested modules to prioritize (by LOC, no `test_<module>.py` found):**

| Rank | Module | LOC | Reason |
|---|---|---|---|
| 1 | `runtime/agency/expert_personas.py` | 3,873 | Largest untested; persona dispatch core |
| 2 | `runtime/agency/navigation/fusion.py` | 2,956 | Sensor-fusion core (EKF/UKF/PF) — must be tested |
| 3 | `runtime/agency/navigation/ai_enhance.py` | 2,727 | ML postprocessing layer for navigation |
| 4 | `runtime/agency/windows_god_mode.py` | 2,380 | OS-control surface; security-sensitive |
| 5 | `runtime/agency/navigation/satellite.py` | 2,353 | GNSS multi-constellation parsing |

**Action:** open issues `test/expert_personas`, `test/nav_fusion`, etc. Target: each module to ≥50% line coverage by Week 22.

---

## 6. GIT HEALTH  ✅ HEALTHY (with hygiene flag)

| Check | Result |
|---|---|
| `git fsck --full --strict` | clean (no dangling/broken refs) |
| Total commits | 101 |
| Repo size (`.git`) | **113 MB** (well under 500 MB BFG threshold) |
| Current branch | `main` |
| HEAD | `30cd506 fix: W18-12 — make test_jarvis_pass8::TestCLISmoke layout-agnostic (2 minutes ago)` |
| Remote | `https://github.com/amjad2161/agency-agents.git` |
| **Uncommitted files** | **157** ⚠️ |

**⚠️ Hygiene flag:** 157 unstaged/untracked files in working tree. Recommend running `scripts/CONSOLIDATE_AND_SYNC.ps1` or rolling unstaged work into a chore branch before next audit.

---

## 7. SUMMARY & TOP 5 ACTIONS

| # | Action | Owner | Target |
|---|---|---|---|
| 1 | Add `gitleaks` + `pip-audit` to CI as hard gates | DevOps | W20 |
| 2 | Generate `requirements.lock` via `uv pip compile`; commit | DevOps | W20 |
| 3 | Reference 22 orphan agents in root `README.md` | Docs | W20 |
| 4 | Backfill tests for top-5 largest untested modules | Engineering | W22 |
| 5 | Reduce 157 uncommitted files in working tree to <10 | Operator | W19 |

**Reconciliation:** Counted 322 agents vs reported 341 — 19 missing. Likely live in `jarvis_singularity/` package and `aios/` (which has 0 .md files but may host agents in non-md form). Worth investigating in W20.

---

*Report generated autonomously by JARVIS BRAINIAC weekly-deep-audit scheduled task.*
