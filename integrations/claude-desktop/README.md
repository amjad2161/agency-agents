# 🧠 Claude Desktop Brain / Memory Integration

> **Give Claude Desktop a persistent memory** — so it remembers your projects, preferences, and past decisions across every conversation. Fewer repeated explanations = fewer tokens burned = lower credit usage.

---

## What It Does

By default, Claude Desktop starts fresh every conversation. You re-explain your stack, your preferences, your project context — every single time. A local MCP memory server fixes that:

| Without memory | With memory |
|---|---|
| Re-paste project context every session | Claude recalls it automatically |
| Re-explain coding conventions each time | Recalled on first message |
| Lost decisions after a conversation ends | Stored and searchable forever |
| Large system prompts burn credits fast | Only relevant memories are loaded |

**Credit savings**: Instead of a 2,000-token system prompt every turn, Claude pulls only the ~200 tokens of context that matter right now. On an active project, this can cut input-token usage by 50–80%.

---

## Quick Start (copy-paste friendly)

### Step 1 — Install the memory server

Requires [Node.js](https://nodejs.org/) 18+.

```bash
# Verify Node is available
node --version
```

The server runs on-demand via `npx` — no permanent install needed.

### Step 2 — Add to Claude Desktop config

Open (or create) your Claude Desktop MCP config file:

| OS | Config path |
|----|-------------|
| **macOS** | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| **Windows** | `%APPDATA%\Claude\claude_desktop_config.json` |
| **Linux** | `~/.config/Claude/claude_desktop_config.json` |

Add the `memory` entry (or merge it into an existing `mcpServers` block):

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

> 📄 See [`claude_desktop_config.json`](./claude_desktop_config.json) in this directory for a ready-to-copy example.

### Step 3 — Restart Claude Desktop

Fully quit and reopen Claude Desktop. The memory tools will appear automatically.

### Step 4 — Verify it works

Ask Claude:

```
Do you have access to a memory tool?
```

Claude should confirm it can store and retrieve memories.

---

## Automated Setup Script

Run the setup script from the repo root — it detects your OS, locates the Claude Desktop config, and patches it in place:

```bash
./integrations/mcp-memory/setup.sh --claude-desktop
```

---

## Platform-Specific Notes

### macOS

```bash
# Open config in your default editor
open -e "$HOME/Library/Application Support/Claude/claude_desktop_config.json" 2>/dev/null \
  || open -e "$HOME/Library/Application Support/Claude/"
```

If Claude Desktop hasn't been launched yet, the directory may not exist. Create it:

```bash
mkdir -p "$HOME/Library/Application Support/Claude"
```

### Windows (PowerShell)

```powershell
# Open config directory
explorer $env:APPDATA\Claude

# Create if missing
New-Item -ItemType Directory -Force -Path "$env:APPDATA\Claude"

# Verify Node is installed
node --version
# If not: winget install OpenJS.NodeJS.LTS
```

### Linux

```bash
# Create config dir if missing
mkdir -p "$HOME/.config/Claude"

# Open config
"${EDITOR:-nano}" "$HOME/.config/Claude/claude_desktop_config.json"
```

---

## Example: Full Config with Memory + Filesystem

If you already have other MCP servers configured, merge like this:

```json
{
  "mcpServers": {
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"],
      "env": {
        "MEMORY_FILE_PATH": "~/.claude-memory/memory.json"
      }
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/you/projects"]
    }
  }
}
```

---

## How to Use Memory in Conversations

Once configured, instruct Claude naturally:

```
Remember that I prefer TypeScript over JavaScript in all new projects.
```

```
Remember: my main project is called "Helios" and it uses React 18 + Node 20 + PostgreSQL.
```

In a future conversation:

```
What do you know about my project setup?
```

Claude will recall stored facts without you repeating them.

### Suggested First Memories

Run these in your first session to prime the memory:

```
Please remember the following about me and my projects:
- Name: [your name]
- Main language/framework: [e.g., TypeScript + React]
- Current project: [project name and brief description]
- Coding style preferences: [e.g., functional patterns, strict ESLint]
- Things I never want to do: [e.g., use class components, skip error handling]
```

---

## Memory File Location

By default the memory server stores data at:

```
~/.claude-memory/memory.json
```

This is a plain JSON file on your local machine. **Nothing is sent to any cloud service.** You can inspect, edit, or delete it at any time:

```bash
# View stored memories
cat ~/.claude-memory/memory.json

# Clear all memories (start fresh)
rm ~/.claude-memory/memory.json
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `npx: command not found` | Install Node.js 18+ from [nodejs.org](https://nodejs.org/) |
| Memory tools don't appear | Fully quit and reopen Claude Desktop (not just close the window) |
| `ENOENT` on config path | Create the directory manually (see platform notes above) |
| JSON parse error | Validate your config at [jsonlint.com](https://jsonlint.com) |
| Memories not persisting | Check `MEMORY_FILE_PATH` is a writable directory |

---

## Further Reading

- [MCP Memory Integration guide](../mcp-memory/README.md) — using memory with Claude Code / other tools
- [Full MCP guide](../mcp.md) — wiring any MCP server to The Agency's agents
- [Official MCP memory server](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) — upstream source
