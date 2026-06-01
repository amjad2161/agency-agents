# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

Two distinct but linked things live in one repo:

1. **The Agency** — a curated library of **341+ AI agent persona files** (Markdown with YAML frontmatter), organized into category directories (`engineering/`, `marketing/`, `design/`, `jarvis/`, etc.). These are the actual product: hand-crafted system prompts, each a specialized expert with identity, workflows, and deliverables.
2. **The Agency Runtime** (`runtime/`) — a Python package (`agency` CLI) that loads those same persona files as runnable *skills*, routes a request to the best one via a planner, and drives it through a Claude tool-use loop (file IO, sandboxed shell, web fetch, skill delegation). There is also a large **JARVIS** subsystem (humanoid-robot-brain experiment) layered on top of the runtime.

The persona files are the source of truth. Everything else (runtime, installers, multi-tool converters) consumes them.

## Repository layout

```
<category>/*.md          Agent persona files. Filename is prefixed with the category,
                         e.g. engineering/engineering-frontend-developer.md
runtime/agency/          The Python runtime package (the `agency` CLI lives here)
runtime/tests/           Runtime pytest suite (~56 test files)
runtime/examples/        Runnable example scripts for the runtime API
scripts/                 convert.sh, install.sh, lint-agents.sh, smoke_*.py, build_capabilities.py
integrations/<tool>/     Generated tool-specific exports (produced by scripts/convert.sh — do not hand-edit)
tests/                   Top-level JARVIS / nav-improvement test suite
.github/workflows/       lint-agents.yml (PR), runtime-tests.yml (push/PR)
```

Agent category directories (kept in sync across `scripts/convert.sh`, `scripts/lint-agents.sh`, and `.github/workflows/lint-agents.yml`):
`academic design engineering finance game-development jarvis marketing paid-media product project-management sales science spatial-computing specialized strategy support testing`

Note: there is a nested `agency-agents/` directory and many `JARVIS_*` / `*.ps1` Windows launcher and report files at the repo root. These are largely standalone artifacts; the active codebase is the persona dirs + `runtime/`.

## Common commands

### Working with the runtime
```bash
pip install -e runtime              # base runtime
pip install -e 'runtime[docs]'      # + PDF/DOCX/XLSX extraction
pip install -e 'runtime[computer]'  # + browser/desktop automation
pip install -e 'runtime[dev]'       # + pytest
export ANTHROPIC_API_KEY=sk-ant-...

agency list                         # browse all loaded skills
agency list --category engineering  # filter by category
agency plan "design a brand identity"   # show which skill the planner picks (no execution)
agency run "review this repo"       # auto-route + execute
agency run "..." --skill engineering-frontend-developer   # force a skill
agency run "..." --session my-proj  # persist session context
agency debug "list files"           # verbose tool-use loop
agency doctor                       # diagnose env: skills, flags, optional deps
agency serve --port 8765            # FastAPI chat UI + /spatial HUD
agency init my-slug --name "My Agent" --category specialized --emoji 🎯   # scaffold a persona
```

### Tests
```bash
cd runtime && python3 -m pytest          # runtime suite (preferred)
python -m pytest runtime/ tests/ -q --timeout=30 --tb=short -p no:warnings   # what CI runs
cd runtime && python3 -m pytest tests/test_executor.py            # single file
cd runtime && python3 -m pytest tests/test_executor.py::test_name # single test
```
CI (`runtime-tests.yml`) runs with `PYTHONPATH=<repo>/runtime:<repo>` and an empty `ANTHROPIC_API_KEY` — tests must pass with **no API key and no optional deps** (they stub the LLM). `conftest.py` at both repo root and `runtime/` already wires `sys.path` to include `runtime/`.

### Linting agent persona files
```bash
./scripts/lint-agents.sh                          # lint every agent file
./scripts/lint-agents.sh engineering/foo.md       # lint specific files
```
This is what `lint-agents.yml` runs on PRs that touch agent dirs. **Errors** (block merge): missing frontmatter `---` delimiters, missing required fields `name` / `description` / `color`. **Warnings**: missing recommended sections (`Identity`, `Core Mission`, `Critical Rules`), body < 50 words, or no section headers that map to the convert.sh SOUL/AGENTS split.

### Multi-tool export / install
```bash
./scripts/convert.sh                 # regenerate integrations/<tool>/ for all supported tools
./scripts/convert.sh --tool cursor   # one tool (antigravity, gemini-cli, opencode, cursor, aider, windsurf, openclaw, qwen, kimi)
./scripts/install.sh --tool claude-code   # install personas into a tool's config dir
```
`convert.sh` reads the persona frontmatter and splits each agent's `##` sections into "SOUL" (identity/communication/rules) vs "AGENTS" (everything else) using a header classifier — keep that classifier (`classify_header_target` in lint-agents.sh) in mind when naming sections.

## Persona file format (the core convention)

Every agent file begins with YAML frontmatter, then a Markdown body:

```markdown
---
name: Frontend Developer          # required
description: One-paragraph summary  # required (used by the planner to route)
color: "#7C3AED"                  # required (name or hex)
emoji: 🎯                          # optional
vibe: One-line personality hook    # optional
tools_allowed: [read_file, ...]    # optional — whitelist; only these tools exposed
tools_denied: [run_shell, ...]     # optional — blacklist; removed from default set
services: ...                      # optional — only if the agent needs external services
---

# <Agent Name> Agent
You are **<Name>**, ...

## 🧠 Your Identity & Memory
## 🎯 Your Core Mission
## Critical Rules
...
```

Key rules:
- **Filename prefix = category**: `marketing/marketing-foo.md`, `engineering/engineering-bar.md`.
- The `description` field is what the runtime planner keyword-matches against, so write it to surface the agent for relevant requests.
- `tools_allowed` / `tools_denied` are enforced at the API request level by the runtime — disallowed tools are never declared to the model, so the persona genuinely cannot call them. Use these to constrain read-only researchers, etc.
- Use `agency init` or copy an existing file in the same category as a template; don't author frontmatter from scratch.

## Runtime architecture (the big picture)

```
runtime/agency/
  skills.py     — discover *.md persona files across category dirs, parse frontmatter → Skill objects
  planner.py    — keyword shortlist → Haiku model picks the best skill for a request
  llm.py        — Anthropic SDK wrapper. Caches the persona body as a cached system prompt;
                  passes through task-budget + MCP config; all config comes from env vars
  tools.py      — builtin tool set: read_file, write_file, edit_file, list_dir, extract_doc,
                  run_shell, web_fetch, list_skills, plan, delegate_to_skill
  executor.py   — the tool-use loop (streaming + non-streaming), parallel-safe tool fan-out,
                  usage tracking, plan binding, session memory
  memory.py     — JSONL session store under ~/.agency/sessions/
  cli.py        — Click CLI (list, plan, run, debug, serve, init, doctor, trust, profile, lessons, ...)
  server.py     — FastAPI app + streaming chat UI + /spatial WebSocket HUD
```

Request flow: `cli/server` → `planner` picks a skill (unless `--skill` forces one) → `executor` runs the Claude tool-use loop with that persona's body as the cached system prompt and its allowed tool set → tools resolve against the sandboxed workdir → result streamed back. Skills can call `delegate_to_skill` to hand off to another persona.

Defaults: execution model `claude-opus-4-7`, planner model `claude-haiku-4-5`, `max_tokens` 16000. Override via `AGENCY_MODEL`, `AGENCY_PLANNER_MODEL`, `AGENCY_MAX_TOKENS`.

### Tool sandbox & trust
- All file paths are resolved against the workdir and **rejected if they escape it**.
- Shell is **off by default**; enable with `AGENCY_ALLOW_SHELL=1`, and even then only commands whose head is in an allowlist (`ls`, `cat`, `git`, `grep`, `python3`, …) run.
- Trust modes (`AGENCY_TRUST_MODE` = `off` / `on-my-machine` / `yolo`, or `agency trust set`) gate higher-privilege tool use; persisted in `~/.agency/trust.conf`.
- Feature flags are env-gated: `AGENCY_ENABLE_COMPUTER_USE`, `AGENCY_ENABLE_WEB_SEARCH`, `AGENCY_ENABLE_CODE_EXECUTION`, `AGENCY_NO_NETWORK`, `AGENCY_MCP_SERVERS`. Run `agency doctor` to see current state.

### Always-on context
- `~/.agency/profile.md` (if present) is prepended to every agent as a separate cached system block — who the user is.
- `~/.agency/lessons.md` is a cross-session memory journal (`agency lessons add ...`).

## Conventions & gotchas

- When adding or renaming a category, update **all three** in-sync lists: `AGENT_DIRS` in `scripts/convert.sh`, `AGENT_DIRS` in `scripts/lint-agents.sh`, and the `paths:` + `git diff` globs in `.github/workflows/lint-agents.yml`.
- Don't hand-edit anything under `integrations/<tool>/` — it is generated by `convert.sh`. Edit the source persona file and regenerate.
- Runtime code must degrade gracefully without optional deps and without an API key (CI proves this). Guard imports of `anthropic`, doc-extraction libs, vision/voice/robotics libs behind try/except or optional-dependency checks.
- The `jarvis/` persona dir and the root-level `JARVIS_*.py` / `*.ps1` files are a separate experimental subsystem; changes there don't affect the core persona-library + runtime path.
- This is a Claude-first project: when adding LLM features, default to the latest Claude models and use prompt caching (the runtime already caches persona system prompts).
