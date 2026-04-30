#!/usr/bin/env bash
# JARVIS — one-shot setup (Linux / macOS).
# Creates .venv at the repo root and installs the agency runtime in editable
# mode. Re-run safely to upgrade dependencies.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RUNTIME="${ROOT}/runtime"
VENV="${ROOT}/.venv"

echo
echo " [JARVIS] Supreme Brainiac — Setup"
echo " ==================================="
echo

if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] python3 not found. Install Python 3.10+." >&2
    exit 1
fi

PYVER=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
PYMAJ=${PYVER%%.*}
PYMIN=${PYVER#*.}
if [ "${PYMAJ}" -lt 3 ] || { [ "${PYMAJ}" -eq 3 ] && [ "${PYMIN}" -lt 10 ]; }; then
    echo "[ERROR] Python 3.10+ required. Found ${PYVER}" >&2
    exit 1
fi

if [ ! -d "${VENV}" ]; then
    echo "[SETUP] Creating virtual environment at ${VENV}..."
    python3 -m venv "${VENV}"
    echo "[OK] Virtual environment created."
else
    echo "[OK] Virtual environment already exists."
fi

# shellcheck disable=SC1091
. "${VENV}/bin/activate"
echo "[SETUP] Upgrading pip..."
pip install --upgrade pip --quiet
echo "[SETUP] Installing agency runtime (pip install -e runtime[dev])..."
pip install -e "${RUNTIME}[dev]" --quiet
echo "[OK] Runtime installed."

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo
    echo "[WARN] ANTHROPIC_API_KEY is not set."
    echo "       export ANTHROPIC_API_KEY=sk-ant-..."
else
    echo "[OK] ANTHROPIC_API_KEY is set."
fi

echo
echo " ==================================="
echo " [JARVIS] Setup complete."
echo " Run scripts/jarvis/start.sh to launch."
echo " ==================================="
