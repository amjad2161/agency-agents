# 🧠 Claude Desktop Brain / Memory Integration

> **Give Claude Desktop a persistent local memory + a Super-Brain stack of MCP abilities + an interactive 3D knowledge-graph visualizer.** Fewer repeated explanations = fewer tokens burned = lower credit usage.

```
            ┌───────────────────────────────────────────┐
            │           CLAUDE DESKTOP                  │
            └─────────────────────┬─────────────────────┘
                                  │ MCP (stdio, all via npx)
        ┌──────────────┬──────────┼──────────┬──────────────┐
        │              │          │          │              │
        ▼              ▼          ▼          ▼              ▼
  ┌─────────┐   ┌──────────┐ ┌────────┐ ┌──────────┐ ┌─────────────┐
  │ memory  │   │sequential│ │filesys-│ │puppeteer │ │ everything  │
  │ (graph) │   │ thinking │ │  tem   │ │ headless │ │ demo server │
  └────┬────┘   └──────────┘ └────────┘ │ Chrome   │ └─────────────┘
       │                                └──────────┘
       ▼
  ~/.claude-memory/memory.json   ◄── 3D Brain Visualizer
                                     (zero-install WebGL)
```

[![Local](https://img.shields.io/badge/storage-100%25%20local-1e88e5)]() [![Speed](https://img.shields.io/badge/credit%20savings-50–80%25-43a047)]() [![No install](https://img.shields.io/badge/install-zero-9c27b0)]() [![3D](https://img.shields.io/badge/visualizer-3D%20WebGL-ff7043)]()

---

## ✨ What you get

| Ability | What it does | Saves credits because… |
|---|---|---|
| 🧠 **Persistent Memory** | Knowledge graph of you, your projects, and decisions | No re-pasting context every session |
| 🤔 **Sequential Thinking** | Structured step-by-step reasoning tool | Claude branches less, retries less |
| 📁 **Filesystem** | Direct read/write to `~/Documents` and `~/Desktop` | No copy-paste of file contents |
| 🤖 **Puppeteer** | Headless-Chrome browser automation: navigate, screenshot, click, fill, scrape, fetch | No manual browser steps; one server replaces a generic HTTP fetcher |
| 🧪 **Everything** | Demo server exposing every MCP feature (tools, resources, prompts) | Great for verifying setup + learning what MCP can do |
| 🌌 **3D Visualizer** | WebGL knowledge-graph explorer with type filters, hover peek, screenshot export, keyboard shortcuts | See/audit/prune your memory |

> 🐍 **Want `fetch` / `time` / `git`?** Those MCP servers are published as Python packages, not npm — see [Python add-ons](#-python-add-ons-uvx) below.

---

## 🚀 Quick Start (60 seconds)

### 🧠 Memory only (minimal)

```bash
./integrations/mcp-memory/setup.sh --claude-desktop
```

### ⚡ Super-Brain (memory + reasoning + filesystem + puppeteer + everything)

```bash
./integrations/mcp-memory/setup.sh --claude-desktop --advanced
```

All five servers are published to npm and run via `npx` — no separate install steps.

### 🚀 Super-Brain + Speed pre-warm (instant cold-start)

```bash
./integrations/mcp-memory/setup.sh --claude-desktop --advanced --prewarm
```

`--prewarm` downloads every MCP server package into your local npm cache **before** Claude Desktop needs them, so the first conversation doesn't pause while npx fetches packages.

Then **fully quit and reopen Claude Desktop**.

> Requires [Node.js](https://nodejs.org/) 18+. Verify with `node --version`.

---

## 🌌 3D Brain Visualizer

A built-in WebGL viewer that renders your memory as an interactive knowledge graph.

```bash
./integrations/claude-desktop/view-memory.sh
```

**Features**
- 🌐 Force-distributed 3D layout (Fibonacci-sphere, even on a giant graph)
- 🎨 Auto color-coded by `entityType` with a dynamic legend (click a type to mute/unmute)
- 🔍 Real-time fuzzy search across entities + observations
- 🪄 Hover any node → peek tooltip; click → full details + connected edges glow
- 📁 Drag-and-drop your own `memory.json` (or it auto-loads sample data)
- 📸 One-click PNG screenshot export (or press `S`)
- ⌨ Keyboard shortcuts: `R` reset · `Space` pause · `F` focus selected · `S` screenshot · `Esc` deselect · `?` help
- 🎬 Auto-orbit camera, pause/resume, reset view
- ⚡ Throttled hover raycast (30 Hz) keeps interaction smooth on large graphs
- 🚀 Zero install — pure HTML + Three.js via CDN, opens in any browser

> 📄 File: [`brain-visualizer.html`](./brain-visualizer.html). Open it directly in your browser, or run `view-memory.sh` to launch.

### 🔬 CLI inspection (no browser needed)

`view-memory.sh` doubles as a CLI tool for inspecting/backing up your memory:

```bash
# Quick stats: entity / relation / observation counts, top types, top hubs
./integrations/claude-desktop/view-memory.sh --stats

# List all entity types with counts
./integrations/claude-desktop/view-memory.sh --types

# Text search across names, types, observations, and relations
./integrations/claude-desktop/view-memory.sh --search "TypeScript"

# Timestamped backup → ~/.claude-memory/backups/memory-<UTC>.json
./integrations/claude-desktop/view-memory.sh --backup
```

### 🩺 Health check

Diagnose your install in one command:

```bash
./integrations/mcp-memory/setup.sh --doctor
```

Verifies Node.js version, npm reachability, config file presence + JSON validity, lists configured MCP servers, flags the [PyPI-via-npx footgun](#-python-add-ons-uvx), and validates the memory file's JSONL format. Exits non-zero when anything is wrong, so it's safe to wire into your own scripts or CI.

---

## 📦 Manual Configuration

If you'd rather edit the config by hand, the config path differs per OS:

| OS | Config path |
|----|-------------|
| **macOS** | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| **Windows** | `%APPDATA%\Claude\claude_desktop_config.json` |
| **Linux** | `~/.config/Claude/claude_desktop_config.json` |

### Minimal (memory only)

📄 Source: [`claude_desktop_config.json`](./claude_desktop_config.json)

```json
{
  "mcpServers": {
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"],
      "env": {
        "MEMORY_FILE_PATH": "~/.claude-memory/memory.json"
      }
    }
  }
}
```

### Super-Brain (recommended)

📄 Source: [`claude_desktop_config.advanced.json`](./claude_desktop_config.advanced.json)

```json
{
  "mcpServers": {
    "memory":              { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory"],
                             "env": { "MEMORY_FILE_PATH": "~/.claude-memory/memory.json" } },
    "sequential-thinking": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"] },
    "filesystem":          { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "~/Documents", "~/Desktop"] },
    "puppeteer":           { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-puppeteer"] },
    "everything":          { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-everything"] }
  }
}
```

### 🐍 Python add-ons (uvx)

A few popular MCP servers are only published to PyPI. If you want them, install [`uv`](https://docs.astral.sh/uv/) (`brew install uv` / `pipx install uv`) and add any of these entries to your config — `uvx` will fetch and run them on demand the same way `npx` does for npm packages:

```json
{
  "mcpServers": {
    "fetch": { "command": "uvx", "args": ["mcp-server-fetch"] },
    "time":  { "command": "uvx", "args": ["mcp-server-time"] },
    "git":   { "command": "uvx", "args": ["mcp-server-git"] }
  }
}
```

> ⚠️ **Filesystem scoping**: the `filesystem` server is restricted to `~/Documents` and `~/Desktop` by default. **Never** pass `/` or `~` directly — it would expose your entire home directory. Edit those paths to match what you want Claude to see.

---

## 🏎️ Speed Tips

| Tip | Effect |
|-----|--------|
| Run `setup.sh --prewarm` | First Claude Desktop conversation boots instantly (no npx download pause) |
| Use the Super-Brain stack | Sequential-thinking reduces "let me try again" loops, cutting total tokens |
| Trim memory regularly | Open the 3D Visualizer, find stale entities, ask Claude to delete them |
| Pin Node LTS | `nvm install --lts && nvm alias default lts/*` keeps `npx` fast and predictable |

---

## 🖥️ Platform-Specific Notes

### macOS

```bash
# Open config in your default editor
open -e "$HOME/Library/Application Support/Claude/claude_desktop_config.json" 2>/dev/null \
  || open -e "$HOME/Library/Application Support/Claude/"
```

If Claude Desktop hasn't been launched yet, the directory may not exist:

```bash
mkdir -p "$HOME/Library/Application Support/Claude"
```

### Windows (PowerShell)

```powershell
explorer $env:APPDATA\Claude
New-Item -ItemType Directory -Force -Path "$env:APPDATA\Claude"
node --version  # if missing: winget install OpenJS.NodeJS.LTS
```

### Linux

```bash
mkdir -p "$HOME/.config/Claude"
"${EDITOR:-nano}" "$HOME/.config/Claude/claude_desktop_config.json"
```

---

## 💬 Using Memory in Conversations

```
Remember that I prefer TypeScript over JavaScript in all new projects.
```

```
Remember: my main project is "Helios", uses React 18 + Node 20 + PostgreSQL.
```

In any future conversation:

```
What do you know about my project setup?
```

### Suggested First-Run Memories

```
Please remember the following about me and my projects:
- Name: [your name]
- Main stack: [e.g., TypeScript + React]
- Current project: [project name + brief description]
- Coding style: [e.g., functional patterns, strict ESLint]
- Things I never want to do: [e.g., use class components]
```

---

## 🔒 Privacy & Safety

- **100% local**: memory is stored at `~/.claude-memory/memory.json` — no cloud service involved
- **Inspect anytime**: `cat ~/.claude-memory/memory.json` or open the 3D Visualizer
- **Wipe anytime**: `rm ~/.claude-memory/memory.json`
- **No secrets**: don't tell Claude to remember API keys, passwords, or tokens — they'd live in plain JSON
- **Filesystem server**: scoped to `~/Documents` and `~/Desktop` by default. Edit the args to broaden or narrow

---

## 🛠️ Troubleshooting

| Problem | Fix |
|---------|-----|
| `npx: command not found` | Install Node.js 18+ from [nodejs.org](https://nodejs.org/) |
| Memory tools don't appear | **Fully quit** and reopen Claude Desktop (not just close the window) |
| First message takes 30+ seconds | Run `setup.sh --prewarm` to cache packages ahead of time |
| `ENOENT` on config path | Create the directory manually (see Platform Notes) |
| JSON parse error | Validate at [jsonlint.com](https://jsonlint.com); the setup script does this for you |
| Memories not persisting | Check `MEMORY_FILE_PATH` is a writable directory |
| Visualizer shows sample data | Click 📁 and pick `~/.claude-memory/memory.json` |

---

## 📚 Further Reading

- 📘 [MCP Memory Integration guide](../mcp-memory/README.md) — using memory with Claude Code / other tools
- 📘 [Full MCP guide](../mcp.md) — wiring any MCP server to The Agency's agents
- 📘 [Official MCP memory server](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) — upstream source
- 📘 [Sequential Thinking server](https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking) — structured reasoning
- 📘 [Filesystem server](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem) — sandboxed file access
