# Changelog

All notable changes to the agency runtime, newest first.

## Unreleased

### Fixed
- **Installer hardening (Windows).** Multiple real bugs that could
  silently break the install flow:
  - `scripts/install.bat` and `scripts/install.ps1` are now stored
    with CRLF line endings (Windows cmd.exe is finicky with LF-only
    .bat files); `.gitattributes` enforces CRLF for `*.bat`,
    `*.cmd`, `*.ps1`, `*.psm1` so this can't regress.
  - Removed `--quiet` from every `pip install` call — a silent dep
    failure looked like the script hung; user now sees pip's
    progress and any real error is surfaced with `$LASTEXITCODE`
    checks.
  - Auto-install of Git via `winget install Git.Git` if it's
    missing, mirroring the existing Python.Python.3.13 path.
    Falls back to a manual-install message only if winget itself
    is unavailable.
  - `Get-RealPythonExe` now also scans canonical install paths
    (`%LOCALAPPDATA%\Programs\Python\Python313\python.exe`,
    `%ProgramFiles%\Python313\python.exe`, x86 variant) — `winget`
    can complete a Python install before the in-session PATH
    refresh sees the new directory.
  - Browser launch no longer races the server: a background job
    polls TCP 127.0.0.1:8765 and only opens the browser once the
    server is actually listening, replacing the previous
    `Start-Sleep 1; Start-Process` which sometimes loaded the
    page before `agency serve` bound the port.

### Added
- **One-shot Windows installer.** `scripts/install.ps1` (PowerShell)
  + `scripts/install.bat` (double-click wrapper) bootstrap the
  runtime end-to-end on a fresh machine: disables the broken
  Microsoft-Store Python aliases, installs Python 3.13 via winget
  if needed, clones the repo, builds a venv, installs the runtime
  with `[docs]` and `[computer]` extras, prompts for and persists
  `ANTHROPIC_API_KEY`, sets `AGENCY_TRUST_MODE=yolo`, enables
  `AGENCY_ENABLE_COMPUTER_USE`, lays down starter `profile.md` and
  `lessons.md`, runs `agency doctor`, and launches `agency serve`.
  Idempotent (re-runs update). One-line bootstrap from PowerShell:
  `iwr -UseBasicParsing https://raw.githubusercontent.com/amjad2161/agency-agents/main/scripts/install.ps1 | iex`.
- **Cross-session lessons journal.** `~/.agency/lessons.md` (path
  override `AGENCY_LESSONS`) is loaded on every executor run and
  injected as a system block alongside the always-on profile, so the
  agent has a durable cross-session memory without re-training. The
  loader keeps the most recent `MAX_LESSONS_BYTES` if the file grows
  past the cap (recency wins). New CLI: `agency lessons {show, path,
  edit, add <text>, clear}`. Subagents inherit the same lessons
  string via the executor delegation path.
- **Persistent trust mode.** `agency trust set <off|on-my-machine|yolo>`
  writes `~/.agency/trust.conf` so a personal machine can be marked
  once and runs in the chosen mode on every subsequent invocation —
  no env var, no shell-rc edit. `agency trust clear` removes it. The
  env var (`AGENCY_TRUST_MODE`) still wins when set so per-shell
  overrides keep working. Default mode stays `off` so fresh clones in
  CI / Docker / shared hosts don't silently grant the agent
  everything.
- **Per-skill tool policy.** A persona's YAML frontmatter can declare
  `tools_allowed: [...]` and/or `tools_denied: [...]`. When set, the
  executor filters its tool list per skill before each API call, so
  e.g. a marketing skill can be denied `run_shell` while
  engineering-security keeps it. Defense at the declaration layer:
  disallowed tools are never advertised to the model. Backwards-
  compatible — skills without either field see every builtin tool.

### Added (post-merge)
- **`GET /api/health`** — diagnostic snapshot returning 200 with
  status, runtime version, skills count + categories, model defaults,
  API-key presence, feature-flag state, MCP server count, and which
  optional-deps groups (`docs`, `computer`) are installed. Suitable
  for k8s readiness probes and "why isn't it working" debugging
  without shelling into the container.
- **`GET /api/version`** — minimal `{"name", "version"}` response.
- **User profile (always-on context).** `~/.agency/profile.md` (or
  `AGENCY_PROFILE`-pointed path) is loaded and prepended as a separate
  cached system block before every persona's body. Subagents launched
  via `delegate_to_skill` inherit the same profile. New `agency profile`
  CLI subgroup: `show` / `path` / `edit` / `clear`.
- **Spatial HUD.** `GET /spatial` serves a self-contained page that runs
  MediaPipe Hands in the browser, classifies pinch / open-palm / fist /
  point gestures, and routes them over a `WS /ws/spatial` WebSocket into
  the same Executor the chat UI uses. A Three.js scene
  renders an over-the-camera HUD with a cursor sphere on the index
  fingertip. The WebSocket protocol accepts only a closed set of
  events (`hello`, `gesture`, `run`, `ping`); arbitrary "action"
  strings are rejected. Backend handler in `agency/spatial.py`,
  frontend in `agency/static/spatial.html`. The spatial UI doesn't
  add authority — it produces the same `run` events the chat UI does
  and passes through the existing per-skill tool policy.
- **Trust modes (`AGENCY_TRUST_MODE`).** New `agency.trust` module that
  every tool consults instead of its own ad-hoc gates. Three values:
  - `off` (default) — current behavior. Shell needs `AGENCY_ALLOW_SHELL=1`
    + allowlist; file paths sandboxed under workdir; `web_fetch` refuses
    private / loopback / metadata IPs.
  - `on-my-machine` — agent's reach == user's reach. Shell on; allowlist
    replaced with a tiny catastrophic-typo denylist (`rm -rf /`, fork
    bombs, `mkfs /dev/...`, `dd of=/dev/...`, `chmod 000 /`). File paths
    can be anywhere. `web_fetch` can hit loopback / private IPs (cloud
    instance metadata stays blocked unless `yolo`).
  - `yolo` — same as `on-my-machine` but with the denylist empty and
    metadata IPs reachable.
  New `agency trust` CLI subcommand prints the active gate. `agency
  doctor` also surfaces the mode. README has a side-by-side capability
  table.
- **Structured logging.** A single `agency` named logger (`runtime/agency/logging.py`).
  Off by default; enable with `AGENCY_LOG=info` / `debug` or CLI `-v` / `-vv`.
  Emits records for every routing decision, LLM call (with timings + token
  usage), and tool invocation (`tool.run` with `elapsed_ms` and `is_error`,
  plus separate `tool.error` / `tool.permission_error` / `tool.unhandled`
  events for error detail). The `timed()` helper short-circuits when INFO
  logging is disabled, so wrapping every tool / LLM call costs near-zero
  in production with logging off.
- **Runnable examples.** `runtime/examples/` ships four scripts that exercise
  the programmatic API: list skills, route a prompt (no key), stream a full
  run, and drive cross-skill delegation. See `runtime/examples/README.md`.

### Added
- **Server-side tool handling.** Executor now recognizes `server_tool_use`,
  `mcp_tool_use`, and `*_tool_result` response blocks and surfaces them on
  the event stream without misinterpreting them as client-side tool calls.
  `pause_turn` stop reason resumes the loop instead of exiting.
- **Opt-in Anthropic hosted tools.** `AGENCY_ENABLE_WEB_SEARCH=1` and
  `AGENCY_ENABLE_CODE_EXECUTION=1` register the server-hosted web search
  and Python sandbox. No client-side infra required — Anthropic runs them.
- **MCP server passthrough.** `AGENCY_MCP_SERVERS` (JSON list) forwards to
  `client.beta.messages` with the `mcp-client-2025-11-20` beta header.
- **Task budgets.** `AGENCY_TASK_BUDGET=N` (N ≥ 20 000) adds
  `output_config.task_budget` so Opus 4.7 can self-moderate multi-turn
  agentic loops.
- **Parallel tool fan-out.** Read-only tools (`read_file`, `list_dir`,
  `extract_doc`, `web_fetch`, `list_skills`) in the same turn execute
  concurrently via a thread pool; mutating tools stay serial; model
  ordering is preserved.
- **Token usage tracking.** `ExecutionResult.usage` accumulates
  input/output/cache tokens across every turn; emitted as a final `usage`
  event on the stream. `agency run --show-usage` prints totals.
- **`edit_file` tool** — str_replace semantics modelled on Anthropic's
  `text_editor_20250728`.
- **`extract_doc` tool** — reads PDF / DOCX / XLSX / text via optional
  `[docs]` extra (pypdf, python-docx, openpyxl). Missing deps surface a
  clear install hint.
- **`plan` tool** — persistent per-session markdown scratchpad at
  `~/.agency/plans/<session_id>.md` (Manus-style). Actions:
  view / write / append / clear.
- **`delegate_to_skill` tool** — any agent can invoke another skill as a
  sub-agent. Recursion capped at depth 2.
- **`agency init <slug>`** — scaffold a new persona markdown file.
- **Real streaming.** `Executor.stream` uses `client.messages.stream` and
  yields `text_delta` events as tokens arrive; `POST /api/run/stream` is
  an SSE endpoint; the chat UI renders incrementally.
- **Dockerfile** and **CI** (`runtime-tests.yml` on Python 3.10 / 3.11 /
  3.12, plus a no-key CLI smoke test).

### Added (continued)
- **Opt-in `computer_use` tool.** Implements Anthropic's
  `computer_20250124` client side via pyautogui: screenshot,
  cursor_position, mouse_move, left/right/middle/double click, drag,
  type, key (chord), scroll. Off by default. Enable with
  `AGENCY_ENABLE_COMPUTER_USE=1` + `pip install -e 'runtime[computer]'`
  + a display (X11/Wayland/macOS/Windows). Gives the agent full UI
  control — only enable in a sandbox or dedicated VM.
- **`agency doctor`** diagnostic command: prints loaded skills per
  category, env flags, optional-deps install status, and tool context.
- **Integration test** that keeps `DEFAULT_CATEGORIES` in sync with the
  real top-level persona folders in the repo — catches drift when a new
  category is added.

## 0.1.0

Initial runtime: skill loader, planner, executor with tool-use loop,
file IO + allowlisted shell + web fetch, memory store, Click CLI,
FastAPI + chat UI, pytest suite.
