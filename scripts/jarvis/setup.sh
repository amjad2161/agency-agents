#!/usr/bin/env bash
# ============================================================
# scripts/jarvis/setup.sh — One-click setup for JARVIS One
# Cross-platform companion to setup.bat. Re-run to upgrade deps.
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME="$ROOT/runtime"

echo
echo "  [JARVIS] One — Setup"
echo "  ===================================="
echo

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
    PY="python"
fi
if ! command -v "$PY" >/dev/null 2>&1; then
    echo "[ERROR] Python not found. Install Python 3.10+." >&2
    exit 1
fi

"$PY" --version

# Sanity-check version >= 3.10
"$PY" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" || {
    echo "[ERROR] Python 3.10+ required." >&2
    exit 1
}

if [ ! -d "$ROOT/.venv" ]; then
    echo "[SETUP] Creating virtual environment..."
    "$PY" -m venv "$ROOT/.venv"
fi

# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"

echo "[SETUP] Upgrading pip..."
pip install --upgrade pip --quiet

echo "[SETUP] Installing agency runtime (pip install -e runtime[dev])..."
pip install -e "$RUNTIME[dev]" --quiet

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "[WARN] ANTHROPIC_API_KEY is not set."
    echo "       export ANTHROPIC_API_KEY=sk-ant-..."
else
    echo "[OK] ANTHROPIC_API_KEY is set."
fi

echo
echo "  ===================================="
echo "  [JARVIS] Setup complete."
echo "  Run scripts/jarvis/start.sh to launch."
echo "  ===================================="
