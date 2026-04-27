#!/usr/bin/env bash
#
# setup.sh -- Set up persistent memory for Claude Desktop (and other MCP clients).
#
# Usage:
#   ./integrations/mcp-memory/setup.sh               # Claude Code / generic MCP client
#   ./integrations/mcp-memory/setup.sh --claude-desktop  # Claude Desktop (recommended)
#
# Requirements: Node.js 18+

set -euo pipefail

CLAUDE_DESKTOP=false

for arg in "$@"; do
  case "$arg" in
    --claude-desktop) CLAUDE_DESKTOP=true ;;
    -h|--help)
      echo "Usage: $0 [--claude-desktop]"
      echo ""
      echo "  --claude-desktop   Patch the Claude Desktop config file with the memory server."
      echo "                     Config path is detected automatically per OS."
      exit 0
      ;;
  esac
done

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

NODE_MAJOR=$(node --version | sed 's/v\([0-9]*\).*/\1/')
if [ "$NODE_MAJOR" -lt 18 ]; then
  echo "ERROR: Node.js 18+ is required (found $(node --version))."
  echo "Upgrade at https://nodejs.org/"
  exit 1
fi

echo "Node.js $(node --version) detected."
echo ""

# ---------------------------------------------------------------------------
# 2. Smoke-test the memory server package (dry-run via npx --dry-run)
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

  echo "Claude Desktop mode"
  echo "Config path: $CONFIG_PATH"
  echo ""

  mkdir -p "$CONFIG_DIR"

  if [ -f "$CONFIG_PATH" ]; then
    # Validate existing JSON
    if ! CONFIG_FILE="$CONFIG_PATH" node -e "JSON.parse(require('fs').readFileSync(process.env.CONFIG_FILE,'utf8'))" 2>/dev/null; then
      echo "ERROR: Existing config file is not valid JSON: $CONFIG_PATH"
      echo "Please fix or remove it, then re-run this script."
      exit 1
    fi

    # Check if 'memory' key already present
    if CONFIG_FILE="$CONFIG_PATH" node -e "const c=JSON.parse(require('fs').readFileSync(process.env.CONFIG_FILE,'utf8')); process.exit(c.mcpServers && c.mcpServers.memory ? 0 : 1);" 2>/dev/null; then
      echo "Memory server entry already exists in $CONFIG_PATH — no changes needed."
    else
      echo "Patching existing config to add the memory server..."
      # Use Node to merge the memory entry into the existing config
      CONFIG_FILE="$CONFIG_PATH" node <<'NODEEOF'
const fs = require('fs');
const path = process.env.CONFIG_FILE;
const config = JSON.parse(fs.readFileSync(path, 'utf8'));
config.mcpServers = config.mcpServers || {};
config.mcpServers.memory = {
  command: 'npx',
  args: ['-y', '@modelcontextprotocol/server-memory'],
  env: { MEMORY_FILE_PATH: '~/.claude-memory/memory.json' }
};
fs.writeFileSync(path, JSON.stringify(config, null, 2) + '\n');
console.log('Done.');
NODEEOF
      echo "Config updated: $CONFIG_PATH"
    fi
  else
    echo "Creating new config at $CONFIG_PATH..."
    cat > "$CONFIG_PATH" <<'EOF'
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
EOF
    echo "Config created: $CONFIG_PATH"
  fi

  echo ""
  echo "Next steps:"
  echo "  1. Fully quit and reopen Claude Desktop"
  echo "  2. Ask Claude: 'Do you have access to a memory tool?'"
  echo "  3. Start storing memories: 'Remember that I prefer TypeScript'"
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

if [ -f "$HOME/.config/claude/mcp.json" ]; then
  echo "Found Claude Code MCP config at: ~/.config/claude/mcp.json"
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
