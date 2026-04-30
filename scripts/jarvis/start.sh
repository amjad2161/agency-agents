#!/usr/bin/env bash
# JARVIS — launch the unified runtime (Linux / macOS).
# Activates the venv created by setup.sh and runs `agency singularity` by
# default; pass any other agency subcommand to run it directly.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="${ROOT}/.venv"

if [ ! -x "${VENV}/bin/python" ]; then
    echo "[ERROR] Virtual environment not found. Run scripts/jarvis/setup.sh first." >&2
    exit 1
fi

# Auto-load .env if present (KEY=VALUE pairs only).
if [ -f "${ROOT}/.env" ]; then
    set -a
    # shellcheck disable=SC1090
    . "${ROOT}/.env"
    set +a
fi

# shellcheck disable=SC1091
. "${VENV}/bin/activate"

if [ "$#" -eq 0 ]; then
    exec agency singularity
else
    exec agency "$@"
fi
