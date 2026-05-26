# JARVIS SINGULARITY - CHANGELOG

All notable merge runs and post-merge operations.

## v0.1.0-singularity - 2026-05-03

### Initial unification

Merged 6 source folders into single canonical destination at `C:\Users\User\JARVIS_SINGULARITY`.

**Sources:**
- agency (4.1 GB) — active spine
- Kimi_Agent_Full JARVIS Project Audit (24 GB) — audit dump
- Downloads/jarvis brainiac (23 GB) — extended fork
- Downloads/agency-agents-main (33 MB) — public stock
- Downloads/jarvis (26 MB) — slim variant
- Downloads/Kimi_Agent…(2) (12 MB) — partial dup

**Stats:**
- Top-level entries: 209
- Files indexed in manifest: ~60,000
- Manifest CSV: 6.3 MB
- Runtime: 14 minutes (17:00 → 17:14)

**Policy:**
- Newest-wins on path collisions
- SHA-256 content hash dedup
- Skip files > 100 MB
- Exclude noise dirs (build/cache/IDE/source-git)

**Dropped:**
- 23 GB Ollama LLM blobs
- 23 GB nested zip backups
- All model weights (.gguf, .bin, .pt, .pth, .safetensors, .onnx)
- All build/cache directories

**Git:**
- Initialized local main branch
- Single commit: `feat: unified singularity merge - agency + kimi + jarvis forks`
- No remote (per user choice)

**Generated artifacts:**
- `MERGE_REPORT.md` — stats summary
- `_MANIFEST.csv` — per-file decision log
- `_MERGE.log` — timestamped run log
- `.gitignore` — standard ignores

**Post-merge docs added:**
- `SINGULARITY.md` — master architecture doc
- `ROADMAP.md` — next-step priorities
- `INDEX.md` — folder navigation map
- `DELIVERY.md` — delivery report

---

## How to add new entries

After every re-merge, append a section here documenting:
- Date + tag (`vX.Y.Z`)
- Sources changed
- Files added/overwritten/dropped (numbers)
- Any new exclusions or policy changes
- Validation pass/fail

Use the script `EXPORT_REPORT.cmd` to snapshot the latest `MERGE_REPORT.md` before re-running.
