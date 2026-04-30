#!/usr/bin/env bash
# ============================================================
# scripts/jarvis/start.sh — Launch JARVIS One singularity
# Requires scripts/jarvis/setup.sh to have been run first.
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [ ! -d "$ROOT/.venv" ]; then
    echo "[ERROR] Virtual environment not found. Run scripts/jarvis/setup.sh first." >&2
    exit 1
fi

# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"

# Load .env if present
if [ -f "$ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$ROOT/.env"
    set +a
fi

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "[WARN] ANTHROPIC_API_KEY not set — chat will fail until configured."
    echo "       export ANTHROPIC_API_KEY=sk-ant-... or create $ROOT/.env"
fi

cat <<'BANNER'

  ============================================================
    J.A.R.V.I.S  ONE  —  Singularity
    Owner: Amjad Mobarsham  |  mobarsham@gmail.com
  ============================================================

BANNER

if [ "$#" -eq 0 ]; then
    exec agency singularity
else
    exec agency "$@"
fi
