#!/usr/bin/env bash
#
# view-memory.sh -- Open the 3D Brain Visualizer in your default browser.
#
# Usage:
#   ./integrations/claude-desktop/view-memory.sh
#
# Loads the visualizer next to your local memory.json so you can explore
# the knowledge graph Claude has built about you/your projects.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HTML="$SCRIPT_DIR/brain-visualizer.html"

if [ ! -f "$HTML" ]; then
  echo "ERROR: $HTML not found." >&2
  exit 1
fi

# Build the URL with a hint about the local memory file
URL="file://$HTML"

case "$(uname -s)" in
  Darwin)        open "$URL" ;;
  Linux)         (xdg-open "$URL" >/dev/null 2>&1 || sensible-browser "$URL" 2>/dev/null) & ;;
  MINGW*|MSYS*|CYGWIN*|Windows_NT) start "$URL" ;;
  *)             echo "Open this file in your browser: $URL" ;;
esac

echo "🧠 Brain Visualizer opened."
echo ""
echo "Tip: click 📁 to load your own memory file:"
echo "  ~/.claude-memory/memory.json"
