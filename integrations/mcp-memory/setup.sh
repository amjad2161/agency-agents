#!/usr/bin/env bash
#
# setup.sh -- Set up persistent memory for Claude Desktop (and other MCP clients).
#
# Usage:
#   ./integrations/mcp-memory/setup.sh                       # generic / Claude Code
#   ./integrations/mcp-memory/setup.sh --claude-desktop      # memory only
#   ./integrations/mcp-memory/setup.sh --claude-desktop --advanced
#                                                            # memory + sequential-thinking
#                                                            # + filesystem + puppeteer + everything
#   ./integrations/mcp-memory/setup.sh --prewarm             # pre-download MCP servers
#                                                            # for faster cold starts
#
# Requirements: Node.js 18+

set -euo pipefail

CLAUDE_DESKTOP=false
ADVANCED=false
PREWARM=false
DOCTOR=false
UNINSTALL=false

for arg in "$@"; do
  case "$arg" in
    --claude-desktop) CLAUDE_DESKTOP=true ;;
    --advanced)       ADVANCED=true ;;
    --prewarm)        PREWARM=true ;;
    --doctor)         DOCTOR=true ;;
    --uninstall)      UNINSTALL=true ;;
    -h|--help)
      echo "Usage: $0 [--claude-desktop] [--advanced] [--prewarm] [--doctor] [--uninstall]"
      echo ""
      echo "  --claude-desktop   Patch the Claude Desktop config file with the memory server."
      echo "                     Config path is detected automatically per OS."
      echo "  --advanced         Install the Super-Brain stack (memory + sequential-thinking"
      echo "                     + filesystem + puppeteer + everything). Implies --claude-desktop."
      echo "  --prewarm          Pre-download MCP server packages so Claude Desktop boots"
      echo "                     instantly the first time. Speeds up cold starts."
      echo "  --doctor           Run a health check against your current setup and exit."
      echo "  --uninstall        Remove the memory server from Claude Desktop config. With"
      echo "                     --advanced, also remove the full Super-Brain stack. Other"
      echo "                     mcpServers entries are preserved."
      exit 0
      ;;
  esac
done

# --advanced implies --claude-desktop
if [ "$ADVANCED" = true ]; then
  CLAUDE_DESKTOP=true
fi

echo "MCP Memory Integration Setup"
echo "=============================="
echo ""

# ---------------------------------------------------------------------------
# 1. Verify Node.js is available (npx ships with Node 18+)
# ---------------------------------------------------------------------------

if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: Node.js is not installed."
  echo ""
  echo "Install it from https://nodejs.org/ (version 18 or later),"
  echo "then re-run this script."
  exit 1
fi

NODE_MAJOR=$(node --version 2>/dev/null | sed -E 's/^[^0-9]*([0-9]+).*/\1/')
if ! [[ "$NODE_MAJOR" =~ ^[0-9]+$ ]] || [ "$NODE_MAJOR" -lt 18 ]; then
  echo "ERROR: Node.js 18+ is required (found $(node --version 2>/dev/null || echo 'unknown'))."
  echo "Upgrade at https://nodejs.org/"
  exit 1
fi

echo "Node.js $(node --version) detected."
echo ""

# ---------------------------------------------------------------------------
# 2. Verify the memory server package is reachable on npm
# ---------------------------------------------------------------------------

echo "Verifying @modelcontextprotocol/server-memory is resolvable via npm..."
if npm show @modelcontextprotocol/server-memory version >/dev/null 2>&1; then
  echo "Package verified ($(npm show @modelcontextprotocol/server-memory version 2>/dev/null))."
else
  echo "WARNING: Could not reach npm registry."
  echo "The package will be downloaded on first use by npx (this is normal in offline environments)."
fi
echo ""

# ---------------------------------------------------------------------------
# 2b. Speed: pre-warm npx cache for instant Claude Desktop boot
# ---------------------------------------------------------------------------

ADVANCED_PACKAGES=(
  "@modelcontextprotocol/server-memory"
  "@modelcontextprotocol/server-sequential-thinking"
  "@modelcontextprotocol/server-filesystem"
  "@modelcontextprotocol/server-puppeteer"
  "@modelcontextprotocol/server-everything"
)

if [ "$PREWARM" = true ]; then
  echo "Pre-warming MCP server packages (speeds up Claude Desktop cold start)..."
  PKGS=("@modelcontextprotocol/server-memory")
  if [ "$ADVANCED" = true ]; then
    PKGS=("${ADVANCED_PACKAGES[@]}")
  fi
  for pkg in "${PKGS[@]}"; do
    printf "  · %s ... " "$pkg"
    if npm cache add "$pkg" >/dev/null 2>&1; then
      echo "cached"
    else
      echo "skipped (offline or not yet published)"
    fi
  done
  echo ""
fi

# ---------------------------------------------------------------------------
# 3. Resolve Claude Desktop config path
# ---------------------------------------------------------------------------

_claude_desktop_config_path() {
  case "$(uname -s)" in
    Darwin)
      echo "$HOME/Library/Application Support/Claude/claude_desktop_config.json"
      ;;
    Linux)
      echo "$HOME/.config/Claude/claude_desktop_config.json"
      ;;
    MINGW*|MSYS*|CYGWIN*|Windows_NT)
      # Git-Bash / MSYS on Windows
      echo "${APPDATA:-$HOME/AppData/Roaming}/Claude/claude_desktop_config.json"
      ;;
    *)
      echo "$HOME/.config/Claude/claude_desktop_config.json"
      ;;
  esac
}

# ---------------------------------------------------------------------------
# 3b. --doctor: diagnose the current setup and exit
# ---------------------------------------------------------------------------

if [ "$DOCTOR" = true ]; then
  echo "🩺 Running health check..."
  echo ""

  CFG="$(_claude_desktop_config_path)"
  MEM="${MEMORY_FILE_PATH:-$HOME/.claude-memory/memory.json}"
  # Expand a leading ~ that the env var may carry
  MEM="${MEM/#~/$HOME}"

  STATUS=0
  ok()    { echo "  ✓ $*"; }
  warn()  { echo "  ⚠ $*"; }
  fail()  { echo "  ✗ $*"; STATUS=1; }

  echo "Node.js"
  ok "$(node --version) (npx ships with Node 18+)"

  echo ""
  echo "npm registry"
  if npm show @modelcontextprotocol/server-memory version >/dev/null 2>&1; then
    ok "@modelcontextprotocol/server-memory reachable ($(npm show @modelcontextprotocol/server-memory version 2>/dev/null))"
  else
    warn "Could not reach npm registry (may be offline; npx will fetch on first use)"
  fi

  echo ""
  echo "Claude Desktop config"
  if [ -f "$CFG" ]; then
    ok "Config file exists: $CFG"
    if CFG_PATH="$CFG" node -e 'JSON.parse(require("fs").readFileSync(process.env.CFG_PATH,"utf8"))' >/dev/null 2>&1; then
      ok "Config is valid JSON"
      # List configured servers + flag PyPI-only-via-npx (`if` consumes set -e)
      if CFG_PATH="$CFG" node - <<'NODEEOF'
const cfg = JSON.parse(require('fs').readFileSync(process.env.CFG_PATH,'utf8'));
const servers = (cfg && cfg.mcpServers) || {};
const names = Object.keys(servers);
if (!names.length) { console.log('  ⚠ No mcpServers configured'); process.exit(0); }
console.log('  ✓ ' + names.length + ' MCP server(s) configured: ' + names.join(', '));
const pypi = ['@modelcontextprotocol/server-fetch','@modelcontextprotocol/server-time','@modelcontextprotocol/server-git'];
let bad = 0;
for (const [n, s] of Object.entries(servers)) {
  if (s.command === 'npx' && Array.isArray(s.args) && s.args.some(a => pypi.includes(a))) {
    console.log('  ✗ Server "' + n + '" launches a PyPI-only package via npx — it will fail. Use uvx instead.');
    bad++;
  }
}
process.exit(bad ? 1 : 0);
NODEEOF
      then : ; else STATUS=1 ; fi
    else
      fail "Config file is NOT valid JSON"
    fi
  else
    warn "Config file not found: $CFG (run without --doctor to create it)"
  fi

  echo ""
  echo "Memory file"
  if [ -f "$MEM" ]; then
    ok "Memory file exists: $MEM"
    SIZE=$(wc -c < "$MEM" | tr -d ' ')
    ok "Size: $SIZE bytes"
    # Memory is JSONL (one entity/relation per line); validate each line
    if MEM_PATH="$MEM" node - <<'NODEEOF'
const fs = require('fs');
const text = fs.readFileSync(process.env.MEM_PATH,'utf8');
const lines = text.split(/\r?\n/).filter(l => l.trim().length);
let entities = 0, relations = 0, bad = 0;
for (const l of lines) {
  try {
    const o = JSON.parse(l);
    if (o.type === 'entity')   entities++;
    if (o.type === 'relation') relations++;
  } catch (_) { bad++; }
}
if (bad) { console.error('bad lines: ' + bad); process.exit(1); }
console.log('  ✓ ' + entities + ' entities · ' + relations + ' relations (JSONL parse OK)');
NODEEOF
    then : ; else fail "Memory file has malformed JSONL line(s)"; fi
  else
    warn "Memory file not yet created (will be on Claude's first 'remember' command)"
  fi

  echo ""
  if [ "$STATUS" -eq 0 ]; then
    echo "✅ All checks passed."
  else
    echo "❌ One or more checks failed — see above."
  fi
  exit $STATUS
fi

# ---------------------------------------------------------------------------
# 3c. --uninstall: remove memory (and optionally the Super-Brain stack)
# ---------------------------------------------------------------------------

if [ "$UNINSTALL" = true ]; then
  CONFIG_FILE="$(_claude_desktop_config_path)"
  if [ ! -f "$CONFIG_FILE" ]; then
    echo "Nothing to uninstall — no Claude Desktop config at:"
    echo "  $CONFIG_FILE"
    exit 0
  fi

  # Take a timestamped backup of the config before mutating it
  TS=$(date -u +"%Y%m%dT%H%M%SZ")
  BACKUP="$CONFIG_FILE.bak.$TS"
  cp "$CONFIG_FILE" "$BACKUP"
  echo "Backed up config → $BACKUP"

  # Decide which servers to remove
  if [ "$ADVANCED" = true ]; then
    REMOVE_KEYS='["memory","sequential-thinking","filesystem","puppeteer","everything"]'
    echo "Removing Super-Brain stack (memory, sequential-thinking, filesystem, puppeteer, everything)..."
  else
    REMOVE_KEYS='["memory"]'
    echo "Removing memory server..."
  fi

  CONFIG_FILE="$CONFIG_FILE" REMOVE_KEYS="$REMOVE_KEYS" node - <<'NODEEOF'
const fs = require('fs');
const cfgPath = process.env.CONFIG_FILE;
const remove = JSON.parse(process.env.REMOVE_KEYS);
let cfg;
try {
  cfg = JSON.parse(fs.readFileSync(cfgPath,'utf8'));
} catch (e) {
  console.error('Config is not valid JSON; aborting uninstall to avoid data loss.');
  console.error(e.message);
  process.exit(1);
}
if (!cfg || typeof cfg !== 'object' || !cfg.mcpServers) {
  console.log('No mcpServers section — nothing to do.');
  process.exit(0);
}
const before = Object.keys(cfg.mcpServers).length;
const removed = [];
for (const k of remove) {
  if (Object.prototype.hasOwnProperty.call(cfg.mcpServers, k)) {
    delete cfg.mcpServers[k];
    removed.push(k);
  }
}
// Preserve all other entries; if mcpServers is now empty, leave it as {}
fs.writeFileSync(cfgPath, JSON.stringify(cfg, null, 2) + '\n');
const after = Object.keys(cfg.mcpServers).length;
if (!removed.length) {
  console.log('  (no matching servers were configured)');
} else {
  console.log('  ✓ removed: ' + removed.join(', '));
}
console.log('  ' + before + ' → ' + after + ' server(s) remain in config');
NODEEOF

  echo ""
  echo "✅ Uninstall complete. Restart Claude Desktop to pick up the change."
  echo "   To restore: cp \"$BACKUP\" \"$CONFIG_FILE\""
  exit 0
fi

# ---------------------------------------------------------------------------
# 4. Claude Desktop mode: patch the config file
# ---------------------------------------------------------------------------

MEMORY_SNIPPET='{
  "mcpServers": {
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"],
      "env": {
        "MEMORY_FILE_PATH": "~/.claude-memory/memory.json"
      }
    }
  }
}'

if [ "$CLAUDE_DESKTOP" = true ]; then
  CONFIG_PATH="$(_claude_desktop_config_path)"
  CONFIG_DIR="$(dirname "$CONFIG_PATH")"

  if [ "$ADVANCED" = true ]; then
    echo "Claude Desktop mode (Super-Brain stack: memory + sequential-thinking + filesystem + puppeteer + everything)"
  else
    echo "Claude Desktop mode (memory only)"
  fi
  echo "Config path: $CONFIG_PATH"
  echo ""

  mkdir -p "$CONFIG_DIR"

  # Build the merge payload as a JSON string for Node to read from env
  if [ "$ADVANCED" = true ]; then
    MERGE_JSON='{
      "memory": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"],
        "env": { "MEMORY_FILE_PATH": "~/.claude-memory/memory.json" }
      },
      "sequential-thinking": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
      },
      "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "~/Documents", "~/Desktop"]
      },
      "puppeteer": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-puppeteer"]
      },
      "everything": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-everything"]
      }
    }'
  else
    MERGE_JSON='{
      "memory": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"],
        "env": { "MEMORY_FILE_PATH": "~/.claude-memory/memory.json" }
      }
    }'
  fi

  if [ -f "$CONFIG_PATH" ]; then
    # Validate existing JSON
    if ! CONFIG_FILE="$CONFIG_PATH" node -e "JSON.parse(require('fs').readFileSync(process.env.CONFIG_FILE,'utf8'))" 2>/dev/null; then
      echo "ERROR: Existing config file is not valid JSON: $CONFIG_PATH"
      echo "Please fix or remove it, then re-run this script."
      exit 1
    fi

    echo "Merging server entries into existing config..."
    CONFIG_FILE="$CONFIG_PATH" MERGE_JSON="$MERGE_JSON" node <<'NODEEOF'
const fs = require('fs');
const path = process.env.CONFIG_FILE;
const merge = JSON.parse(process.env.MERGE_JSON);
const config = JSON.parse(fs.readFileSync(path, 'utf8'));
config.mcpServers = config.mcpServers || {};
let added = 0, kept = 0;
for (const [k, v] of Object.entries(merge)) {
  if (config.mcpServers[k]) { kept++; continue; }
  config.mcpServers[k] = v;
  added++;
}
fs.writeFileSync(path, JSON.stringify(config, null, 2) + '\n');
console.log(`Added ${added} server(s), kept ${kept} existing server(s).`);
NODEEOF
    echo "Config updated: $CONFIG_PATH"
  else
    echo "Creating new config at $CONFIG_PATH..."
    CONFIG_FILE="$CONFIG_PATH" MERGE_JSON="$MERGE_JSON" node <<'NODEEOF'
const fs = require('fs');
const path = process.env.CONFIG_FILE;
const merge = JSON.parse(process.env.MERGE_JSON);
const config = { mcpServers: merge };
fs.writeFileSync(path, JSON.stringify(config, null, 2) + '\n');
console.log('Created new config.');
NODEEOF
    echo "Config created: $CONFIG_PATH"
  fi

  echo ""
  echo "Next steps:"
  echo "  1. Fully quit and reopen Claude Desktop"
  echo "  2. Ask Claude: 'Do you have access to a memory tool?'"
  echo "  3. Start storing memories: 'Remember that I prefer TypeScript'"
  if [ "$ADVANCED" = true ]; then
    echo "  4. Try the new abilities:"
    echo "       'Think step-by-step about ...' → uses sequential-thinking"
    echo "       'Read the file ~/Documents/notes.md' → uses filesystem"
    echo "       'Take a screenshot of https://example.com' → uses puppeteer"
    echo "       'Show me the example tools' → uses everything (demo server)"
  fi
  echo ""
  echo "🧠 Visualize your memory in 3D (run from the repo root):"
  echo "   ./integrations/claude-desktop/view-memory.sh"
  echo ""
  echo "Memory data is stored locally at ~/.claude-memory/memory.json"
  echo "See integrations/claude-desktop/README.md for full usage guide."
  exit 0
fi

# ---------------------------------------------------------------------------
# 5. Generic mode: show config snippet and detect existing client configs
# ---------------------------------------------------------------------------

echo "Generic MCP client mode"
echo ""
echo "Add the following to your MCP client config (mcpServers block):"
echo ""
echo "$MEMORY_SNIPPET"
echo ""

CONFIG_FOUND=false

CLAUDE_DESKTOP_PATH="$(_claude_desktop_config_path)"
if [ -f "$CLAUDE_DESKTOP_PATH" ]; then
  echo "Found Claude Desktop config at: $CLAUDE_DESKTOP_PATH"
  echo "  Tip: re-run with --claude-desktop to patch it automatically."
  CONFIG_FOUND=true
fi

if [ -f "$HOME/.claude/mcp.json" ]; then
  echo "Found Claude Code MCP config at: ~/.claude/mcp.json"
  CONFIG_FOUND=true
fi

if [ -f "$HOME/.cursor/mcp.json" ]; then
  echo "Found Cursor MCP config at: ~/.cursor/mcp.json"
  CONFIG_FOUND=true
fi

if [ -f ".mcp.json" ]; then
  echo "Found project MCP config at: .mcp.json"
  CONFIG_FOUND=true
fi

if [ "$CONFIG_FOUND" = false ]; then
  echo "No MCP client config found on this machine."
fi

echo ""
echo "Next steps:"
echo "  1. Add the snippet above to your MCP client config"
echo "  2. Restart your MCP client"
echo "  3. Add a Memory Integration section to any agent prompt"
echo "     (see integrations/mcp-memory/README.md for the pattern)"
echo ""
echo "For Claude Desktop, run: $0 --claude-desktop"
echo "For the Super-Brain stack, run: $0 --claude-desktop --advanced"
