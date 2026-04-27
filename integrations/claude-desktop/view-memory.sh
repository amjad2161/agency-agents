#!/usr/bin/env bash
#
# view-memory.sh -- Inspect Claude's memory: open the 3D Brain Visualizer,
# or query / back up the memory file from the command line.
#
# Usage:
#   ./integrations/claude-desktop/view-memory.sh                # open visualizer (default)
#   ./integrations/claude-desktop/view-memory.sh --stats        # entity/relation counts + top hubs
#   ./integrations/claude-desktop/view-memory.sh --types        # list entity types with counts
#   ./integrations/claude-desktop/view-memory.sh --search QUERY # text search across memory
#   ./integrations/claude-desktop/view-memory.sh --backup       # timestamped backup copy
#   ./integrations/claude-desktop/view-memory.sh --help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HTML="$SCRIPT_DIR/brain-visualizer.html"
MEM="${MEMORY_FILE_PATH:-$HOME/.claude-memory/memory.json}"
MEM="${MEM/#~/$HOME}"

usage() {
  cat <<'USAGE'
view-memory.sh -- Inspect Claude's memory: open the 3D Brain Visualizer,
or query / back up the memory file from the command line.

Usage:
  view-memory.sh                # open visualizer (default)
  view-memory.sh --stats        # entity/relation counts + top hubs
  view-memory.sh --types        # list entity types with counts
  view-memory.sh --search QUERY # text search across memory
  view-memory.sh --backup       # timestamped backup copy
  view-memory.sh --help

Memory path is taken from $MEMORY_FILE_PATH or defaults to
~/.claude-memory/memory.json (the MCP memory server's default).
USAGE
}

# Common Node helper: emit a streamable JSONL entity/relation parser.
# Reads $MEM_PATH, prints to stdout in a useful shape per --mode.
_inspect() {
  MEM_PATH="$MEM" MODE="$1" QUERY="${2:-}" node - <<'NODEEOF'
const fs = require('fs');
const path = process.env.MEM_PATH;
const mode = process.env.MODE;
const query = (process.env.QUERY || '').toLowerCase();

if (!fs.existsSync(path)) {
  console.error('Memory file not found: ' + path);
  console.error('It will be created on Claude\'s first "remember" command.');
  process.exit(2);
}
const text = fs.readFileSync(path, 'utf8');
const lines = text.split(/\r?\n/).filter(l => l.trim().length);

const entities = [];
const relations = [];
let bad = 0;
for (const l of lines) {
  try {
    const o = JSON.parse(l);
    if (o.type === 'entity')   entities.push(o);
    if (o.type === 'relation') relations.push(o);
  } catch (_) { bad++; }
}

const obsCount = entities.reduce(
  (s, e) => s + (Array.isArray(e.observations) ? e.observations.length : 0), 0);

function pad(s, n) { s = String(s); return s + ' '.repeat(Math.max(0, n - s.length)); }

if (mode === 'stats') {
  console.log('🧠 Memory stats — ' + path);
  console.log('');
  console.log('  Entities:     ' + entities.length);
  console.log('  Relations:    ' + relations.length);
  console.log('  Observations: ' + obsCount);
  if (bad) console.log('  Bad lines:    ' + bad + ' (skipped)');
  console.log('');
  const types = new Map();
  for (const e of entities) {
    const t = e.entityType || 'entity';
    types.set(t, (types.get(t) || 0) + 1);
  }
  const topTypes = [...types.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
  if (topTypes.length) {
    console.log('Top entity types:');
    for (const [t, n] of topTypes) console.log('  ' + pad(t, 24) + n);
    console.log('');
  }
  const degree = new Map();
  for (const r of relations) {
    degree.set(r.from, (degree.get(r.from) || 0) + 1);
    degree.set(r.to,   (degree.get(r.to)   || 0) + 1);
  }
  const hubs = [...degree.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
  if (hubs.length) {
    console.log('Most-connected entities:');
    for (const [name, n] of hubs)
      console.log('  ' + pad(name, 32) + n + ' link' + (n === 1 ? '' : 's'));
  }
} else if (mode === 'types') {
  const types = new Map();
  for (const e of entities) {
    const t = e.entityType || 'entity';
    types.set(t, (types.get(t) || 0) + 1);
  }
  const sorted = [...types.entries()].sort((a, b) => b[1] - a[1]);
  if (!sorted.length) {
    console.log('(no entity types yet)');
  } else {
    for (const [t, n] of sorted) console.log(pad(t, 28) + n);
  }
} else if (mode === 'search') {
  if (!query) { console.error('Usage: --search QUERY'); process.exit(64); }
  let hits = 0;
  for (const e of entities) {
    const inName = e.name && e.name.toLowerCase().includes(query);
    const inType = e.entityType && e.entityType.toLowerCase().includes(query);
    const matches = (e.observations || []).filter(
      o => String(o).toLowerCase().includes(query));
    if (inName || inType || matches.length) {
      hits++;
      console.log('• ' + e.name + '  (' + (e.entityType || 'entity') + ')');
      for (const m of matches.slice(0, 3)) {
        const t = String(m);
        console.log('    ↳ ' + (t.length > 120 ? t.slice(0, 117) + '…' : t));
      }
    }
  }
  const relHits = relations.filter(r =>
    (r.from && r.from.toLowerCase().includes(query)) ||
    (r.to && r.to.toLowerCase().includes(query)) ||
    (r.relationType && r.relationType.toLowerCase().includes(query)));
  if (relHits.length) {
    console.log('');
    console.log('Matching relations:');
    for (const r of relHits.slice(0, 20))
      console.log('  ' + r.from + '  --[' + r.relationType + ']-->  ' + r.to);
  }
  console.log('');
  console.log(hits + ' entit' + (hits === 1 ? 'y' : 'ies') + ' matched');
  if (!hits && !relHits.length) process.exit(1);
} else {
  console.error('Unknown mode: ' + mode);
  process.exit(64);
}
NODEEOF
}

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
  --stats)
    _inspect stats
    exit 0
    ;;
  --types)
    _inspect types
    exit 0
    ;;
  --search)
    if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
      echo "Usage: $0 --search QUERY" >&2
      exit 64
    fi
    _inspect search "$2"
    exit 0
    ;;
  --backup)
    if [ ! -f "$MEM" ]; then
      echo "Memory file not found: $MEM" >&2
      exit 2
    fi
    BACKUP_DIR="$(dirname "$MEM")/backups"
    mkdir -p "$BACKUP_DIR"
    TS=$(date -u +"%Y%m%dT%H%M%SZ")
    DEST="$BACKUP_DIR/memory-$TS.json"
    cp "$MEM" "$DEST"
    SIZE=$(wc -c < "$DEST" | tr -d ' ')
    echo "✓ Backed up $SIZE bytes → $DEST"
    exit 0
    ;;
  ""|--open)
    # Default: open the 3D visualizer
    ;;
  *)
    echo "Unknown option: $1" >&2
    echo ""
    usage
    exit 64
    ;;
esac

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
echo "  $MEM"
echo ""
echo "Or run from CLI: $0 --stats | --types | --search Q | --backup"
