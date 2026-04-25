# Agency Runtime

A Python orchestration runtime that turns the persona markdown files in this
repo into runnable skills. Pick (or auto-route to) any of the 180+ agents,
hand it a request, and the runtime drives a Claude tool-use loop with file IO,
sandboxed shell, and web fetch.

## What this is — and isn't

- **Is:** a thin runtime that *uses* the existing `*.md` persona library as
  system prompts, plus a planner, executor, CLI, and web UI.
- **Isn't:** a replacement for the existing installer scripts. They still copy
  agent files into Claude Code, Cursor, etc. This adds a runtime so you can run
  the agents directly from this repo.

## Install

```bash
pip install -e runtime            # base runtime
pip install -e 'runtime[docs]'    # add PDF / DOCX / XLSX extraction
pip install -e 'runtime[dev]'     # add pytest
export ANTHROPIC_API_KEY=sk-ant-...
```

### Config via env

| Variable | Effect |
|---|---|
| `AGENCY_MODEL` | Override execution model (default `claude-opus-4-7`). |
| `AGENCY_PLANNER_MODEL` | Override planner model (default `claude-haiku-4-5`). |
| `AGENCY_MAX_TOKENS` | Per-request `max_tokens` (default 16000). |
| `AGENCY_TASK_BUDGET` | If ≥ 20000, pass `output_config.task_budget` (Opus 4.7 beta). Agent self-moderates within this token budget across a loop. |
| `AGENCY_MCP_SERVERS` | JSON list of MCP server configs. When set, the runtime switches to `client.beta.messages` with the `mcp-client-2025-11-20` beta header. |
| `AGENCY_ENABLE_WEB_SEARCH=1` | Register Anthropic's hosted `web_search_20260209` tool. |
| `AGENCY_ENABLE_CODE_EXECUTION=1` | Register the hosted Python sandbox `code_execution_20260120`. |
| `AGENCY_ENABLE_COMPUTER_USE=1` | Enable mouse/keyboard/screenshot via `pip install -e 'runtime[computer]'`. Requires a display. |
| `AGENCY_ALLOW_SHELL=1` | Opt into the allowlisted shell tool. |
| `AGENCY_NO_NETWORK=1` | Disable `web_fetch`. |
| `AGENCY_TOOL_TIMEOUT` | Per-tool wall-clock seconds (default 30). |
| `AGENCY_DISABLE_HEALTH=1` | Don't register `/api/health`. Set this if you bind 0.0.0.0 on an untrusted network and don't want the diagnostic snapshot exposed. |
| `AGENCY_PROFILE` | Override the profile file path (default `~/.agency/profile.md`). |
| `AGENCY_TRUST_MODE` | `off` (default), `on-my-machine`, or `yolo`. See **Trust modes** below. |

Example MCP config:

```bash
export AGENCY_MCP_SERVERS='[
  {"type": "url", "name": "github", "url": "https://api.githubcopilot.com/mcp/"}
]'
```

## Use

### Browse skills

```bash
agency list
agency list --category engineering
agency list --search "frontend"
```

### See who would handle a request

```bash
agency plan "design a brand identity for a B2B SaaS startup"
```

### Run a request end to end

```bash
agency run "review the security of this code base"
agency run "..." --skill engineering-frontend-developer   # force a skill
agency run "..." --session my-project                    # remember context
agency run "..." --show-usage                            # print token totals
```

### Scaffold a new persona

```bash
agency init my-slug --name "My Agent" --category specialized --emoji 🎯
```

### Diagnose the environment

```bash
agency doctor
```

Shows loaded skills per category, which env flags are set, which optional
deps (`[docs]`, `[computer]`) are installed, and the tool context defaults.
Run it first if something isn't working.

### Logging

Off by default. Turn on with `AGENCY_LOG=info` (or `debug`) or pass
`-v` / `-vv` to the CLI. Records:

- `plan.picked slug=<...> reason=<...>` — every routing decision
- `llm.create elapsed_ms=<...> model=<...> stop=<...>` — every API call
- `llm.usage input=<...> output=<...> cache_w=<...> cache_r=<...>` — token spend per call
- `tool.run elapsed_ms=<...> name=<...> is_error=<...>` — every tool invocation
  (additional `tool.error` / `tool.permission_error` / `tool.unhandled` records when something fails)

```bash
agency -v run "summarize the README"
agency -vv run ...        # DEBUG
AGENCY_LOG=info agency serve
```

### Programmatic examples

`runtime/examples/` has runnable scripts: list skills, route a prompt,
stream a full run, drive multi-skill delegation. See
[`runtime/examples/README.md`](examples/README.md).

### Debug the tool-use loop

```bash
agency debug "list the files in this repo"
```

### Web UI

```bash
agency serve --port 8765
# open http://127.0.0.1:8765         # the chat UI
# open http://127.0.0.1:8765/spatial # the webcam + 3D HUD
```

API endpoints:
- `GET /api/health` — diagnostic snapshot: skills count, model defaults,
  API-key presence, feature-flag state, optional-deps install status
- `GET /api/version` — runtime name + version
- `GET /api/skills` — list loaded skills
- `POST /api/plan` — `{"message": "..."}` → which skill the planner picks
- `POST /api/run` — `{"message": "...", "skill"?: "...", "session_id"?: "..."}` → final text
- `POST /api/run/stream` — same body, streamed as Server-Sent Events
  (`plan`, `text_delta`, `tool_use`, `tool_result`, `stop`, `done`, `error`)
- `GET /spatial` — single-page MediaPipe + Three.js 3D HUD that drives the runtime via webcam gestures
- `WS /ws/spatial` — bidirectional WebSocket the HUD speaks. Closed event vocabulary:
  - client → server: `hello`, `gesture`, `run`, `ping`
  - server → client: `hello`, `gesture_ack`, `plan`, `stream`, `done`, `error`, `pong`

### Spatial HUD

`GET /spatial` serves a self-contained page that runs **MediaPipe Hands** in
the browser, feeds detected landmarks through a small gesture classifier
(pinch / open palm / fist / point), and routes high-confidence gestures over
WebSocket to the same executor the chat UI uses. Gestures map to a fixed
allowlist of UI actions (e.g. open palm → send the current message); the
backend never accepts a free-form "action" string from the client. A
**Three.js** scene renders the HUD over a transparent canvas, with a cursor
sphere tracking the index fingertip and a slowly rotating ring as a focus
indicator.

What the spatial UI is and isn't:
- **Is:** a webcam-driven control surface for the same runtime everything
  else uses. Same skills, same tool sandbox, same per-skill tool policy.
- **Isn't:** new authority. A pinch can't make the agent run a tool the
  current skill's `tools_allowed` policy already forbids. A spoken "rm -rf"
  can't bypass `AGENCY_ALLOW_SHELL`. Browser-side detection just produces
  the same `run` event the chat UI does.

## Architecture

```
runtime/agency/
  skills.py     — discover *.md persona files, parse frontmatter
  llm.py        — Anthropic SDK wrapper (caches the persona system prompt,
                  task-budget + MCP passthrough, config from env)
  tools.py      — read_file, write_file, edit_file, list_dir, extract_doc,
                  run_shell, web_fetch, list_skills, plan, delegate_to_skill
  planner.py    — keyword shortlist → Haiku picks the best skill
  executor.py   — tool-use loop (streaming + non-streaming), parallel-safe
                  tool fan-out, usage tracking, plan binding, memory
  memory.py     — JSONL session store under ~/.agency/sessions/
  cli.py        — Click CLI: list, plan, run, debug, serve, init
  server.py     — FastAPI + streaming chat UI
```

### Defaults

- **Models:** `claude-opus-4-7` for execution, `claude-haiku-4-5` for planning.
- **Prompt caching:** the persona body is sent as a cached system prompt, so
  subsequent turns of a session are billed at the cache-read rate.
- **Tool sandbox:** all file paths are resolved against the workdir and
  rejected if they escape it. Shell is off by default; when enabled, only
  commands whose head is in the allowlist (`ls`, `cat`, `git`, `grep`,
  `python3`, etc.) run.

## Tests

```bash
cd runtime && python3 -m pytest
```

The test suite covers the skill loader, planner (parser + LLM wiring with a
stub), the file-IO + shell-allowlist tool sandbox, edit_file, extract_doc,
the plan tool, the executor's non-streaming and streaming tool-use loops,
token-usage accumulation, parallel-safe tool fan-out, session-memory
round-trips, delegation between skills, LLM config + task-budget + MCP
routing, the CLI (Click `CliRunner`), and the server endpoints (FastAPI
`TestClient`).

## Per-skill tool policy

A persona's frontmatter can constrain which tools that skill is allowed
to use. The two knobs:

```yaml
---
name: Marketing Strategist
tools_denied: [run_shell, edit_file, computer_use]
---
```

```yaml
---
name: Read-only Researcher
tools_allowed: [read_file, list_dir, web_fetch, list_skills]
---
```

- If `tools_allowed` is set, **only** those tool names are exposed.
- If `tools_denied` is set, those tool names are removed from the
  default set.
- Both can take a YAML list or a comma-separated string.
- If neither is present, the skill gets every builtin tool (status quo).

The filter is applied at the request level — the disallowed tools
are never declared to the API for that skill, so the model can't
call them.

## User profile (always-on context)

`~/.agency/profile.md` — if it exists — is sent to every agent as
background context (a separate cached system block, prepended before
the persona body). It's the difference between an agent that has to
re-learn who you are every session and one that already knows your
name, role, and preferences.

```bash
agency profile          # show current
agency profile path     # print where it lives
agency profile edit     # open in $EDITOR (creates a starter template if missing)
agency profile clear    # delete it
```

Set `AGENCY_PROFILE` to override the path. Subagents (via
`delegate_to_skill`) inherit the same profile so the context stays
consistent across hops.

## Trust modes

By default the runtime is conservative — shell access is opt-in and
allowlisted, file paths are sandboxed under the workdir, and `web_fetch`
refuses private/loopback addresses. That's the right default for
shared/CI/Docker contexts.

For *"the agent is running on my machine and I trust it the way I trust
myself"*, set `AGENCY_TRUST_MODE`:

| Capability | `off` (default) | `on-my-machine` | `yolo` |
|---|---|---|---|
| Shell tool | needs `AGENCY_ALLOW_SHELL=1` + allowlist | on, denylisted | on, no denylist |
| File paths | sandboxed under workdir | anywhere on disk | anywhere on disk |
| `web_fetch` to loopback / RFC1918 | refused (SSRF block) | allowed | allowed |
| `web_fetch` to cloud metadata IP (169.254.169.254) | refused | refused (credential exfil block) | allowed |
| Catastrophic-typo denylist (`rm -rf /`, fork bombs, `mkfs /dev/...`, `dd of=/dev/...`, `chmod 000 /`) | n/a | enforced | empty |

### Per-shell (one-off)

```bash
export AGENCY_TRUST_MODE=on-my-machine     # or: yolo, off
agency trust    # show the active gate
```

### Persistent (your laptop, set once)

```bash
agency trust set yolo            # writes ~/.agency/trust.conf
agency trust                     # confirms the new mode
agency trust path                # prints the file location
agency trust clear               # removes the file (back to off)
```

After `agency trust set yolo` the runtime reads that file on every
subsequent run — no env var needed, no shell-rc edit. The env var still
wins when set, so a one-off `AGENCY_TRUST_MODE=off agency run ...` can
downgrade for a single command without touching the persistent config.

Resolution order: `AGENCY_TRUST_MODE` env var → `~/.agency/trust.conf` →
`off`. The default stays `off` so a fresh clone in CI / Docker / a
shared host doesn't silently grant the agent everything; personal
machines opt in via either knob.

The denylist on `on-my-machine` exists because LLMs hallucinate
variables — `rm -rf $UNDEFINED/path` expands to `rm -rf /path`, and
that's almost never what you meant. The cloud-metadata block stays on
because the IAM-credential exfil pathway is rarely worth lifting. You
retain full ability to run those commands yourself; if you want the
agent to as well, use `yolo`.

## Delegation

Agents can hand off to each other via the `delegate_to_skill` tool. The
executor exposes it by default. Delegation is capped at depth 2 so a chain
like *strategy → engineering → writing* is allowed but can't recurse
indefinitely.

## Persistent plan (per-session scratchpad)

When a session id is set, agents get a `plan` tool that reads/writes a
markdown file under `~/.agency/plans/<session_id>.md`. Use it for long
tasks: the agent decomposes the work up front, checks items off as it
goes, and re-reads the plan between turns so it stays on track.

Actions: `view`, `write`, `append`, `clear`.
Inspired by the Manus-style planning pattern.

## Docker

```bash
docker build -f runtime/Dockerfile -t agency-runtime .
docker run --rm -p 8765:8765 -e ANTHROPIC_API_KEY=... agency-runtime
# CLI usage:
docker run --rm -e ANTHROPIC_API_KEY=... agency-runtime agency list
```

## Extending

- **Add a tool:** append to `builtin_tools()` in `agency/tools.py`. Each tool
  is a `Tool(name, description, input_schema, func)`.
- **Add a skill:** drop a markdown file in any category folder with the same
  YAML frontmatter as the existing personas. The loader picks it up on next
  start.
- **Swap the LLM backend:** `AnthropicLLM` is the only consumer of the SDK.
  Subclass or replace it with anything that exposes `messages_create(...)`
  returning blocks with `.type`, `.text`, `.name`, `.input`, `.id`.
