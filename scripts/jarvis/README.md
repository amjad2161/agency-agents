# JARVIS launchers

This directory holds the **only** supported entry-points for booting JARVIS.

| Platform        | Setup (run once)              | Launch                        |
|-----------------|--------------------------------|-------------------------------|
| Linux / macOS   | `scripts/jarvis/setup.sh`      | `scripts/jarvis/start.sh`     |
| Windows         | `scripts/jarvis/setup.ps1`     | `scripts/jarvis/start.ps1`    |

Both `start` scripts default to `agency singularity`, the unified entry-point
that loads every skill, prints the bilingual greeting, opens the dashboard in
a browser, and drops you into the chat REPL. Pass any other `agency`
subcommand (e.g. `start.sh map`, `start.ps1 list --category engineering`) to
run it directly.

The previous `JARVIS_*.bat` / `JARVIS_*.ps1` files at the repo root were
collapsed into the four scripts above. Commit-and-push helpers were moved to
`scripts/dev/` and are **not** part of the normal launch path.
