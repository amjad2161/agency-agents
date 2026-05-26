# JARVIS SINGULARITY KIT v1.2

Unifies AGENCY + KIMI Agent JARVIS Audit + JARVIS forks → single canonical folder.

## Files

| File | Purpose |
|---|---|
| `MERGE_SINGULARITY.ps1` | Core merge engine — newest-wins, hash-dedup, exclusions, git init |
| `LAUNCH_MERGE.cmd` | Run merge (live) |
| `LAUNCH_DRYRUN.cmd` | Dry-run — stats only, no writes |
| `VERIFY_SINGULARITY.ps1` | Post-merge structural sanity + Python smoke test |
| `LAUNCH_VERIFY.cmd` | Run verifier |
| `POST_MERGE_SETUP.ps1` | Bootstrap venv, install runtime, smoke imports |
| `LAUNCH_POST_MERGE_SETUP.cmd` | Run setup |
| `RUN_FULL_PIPELINE.cmd` | Run merge + verify + setup back-to-back |
| `SINGULARITY.md` | Master architecture doc — layout, rules, quick start |
| `README.md` | This file |

## Quick start

```cmd
:: One-shot: merge + verify + setup
RUN_FULL_PIPELINE.cmd

:: Or step by step:
LAUNCH_DRYRUN.cmd                  :: stats first
LAUNCH_MERGE.cmd                   :: live merge
LAUNCH_VERIFY.cmd                  :: structural checks
LAUNCH_POST_MERGE_SETUP.cmd        :: venv + deps
```

## Outputs (in `C:\Users\User\JARVIS_SINGULARITY`)

| File | Content |
|---|---|
| `MERGE_REPORT.md` | Stats + source priority + exclusion summary |
| `_MANIFEST.csv` | Per-file decision log: src, hash, action, reason |
| `_MERGE.log` | Run log with timestamps |
| `.gitignore` | Standard ignores |
| `.git/` | Local git, single initial commit, no remote |

## Rules

- **Newest-wins** by mtime (UTC) when path collides
- **Hash-dedup** SHA-256, identical → one copy
- **Cap 100 MB** — drops Ollama blobs, model weights, big zips
- **Exclude dirs** `.git`, `.venv`, `venv`, `env`, `node_modules`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.tox`, `.cache`, `dist`, `build`, `*.egg-info`, `blobs`, `.next`, `.nuxt`, `target`, `bin`, `obj`, `.idea`
- **Exclude files** `*.pyc`, `*.gguf`, `*.bin`, `*.pt`, `*.pth`, `*.safetensors`, `*.onnx`, `*.bundle`, `*.iso`, `*.exe`, `*.msi`, `sha256-*`
- **Resumable** — re-run any time, only updates new/newer/different files

## Source priority

1. `C:\Users\User\agency` (active spine)
2. `C:\Users\User\Downloads\Kimi_Agent_Full JARVIS Project Audit`
3. `C:\Users\User\Downloads\jarvis brainiac`
4. `C:\Users\User\Downloads\agency-agents-main`
5. `C:\Users\User\Downloads\jarvis`
6. `C:\Users\User\Downloads\Kimi_Agent_Full JARVIS Project Audit000. (2)`

## Destination

`C:\Users\User\JARVIS_SINGULARITY`

## Rollback

```cmd
rmdir /s /q C:\Users\User\JARVIS_SINGULARITY
```

Sources are never modified — safe.
