# Changelog

All notable changes to the agency runtime, newest first.

## Unreleased

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

### Intentionally not included
- **Computer use.** The `computer_20250124` tool needs a display-enabled
  container with client-side screenshot/mouse/keyboard handlers. Adding a
  stub that crashes at runtime would be worse than not adding it. If you
  have the infra, you can pass the declaration via a future
  `enable_computer_use` option — I'll wire it when there's a real target.

## 0.1.0

Initial runtime: skill loader, planner, executor with tool-use loop,
file IO + allowlisted shell + web fetch, memory store, Click CLI,
FastAPI + chat UI, pytest suite.
