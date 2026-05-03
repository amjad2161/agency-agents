#!/usr/bin/env bash
# Ω-SINGULARITY launcher — POSIX
set -e
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "python3 required"; exit 1; }
if [ "$#" -eq 0 ]; then
    python3 omega.py stats
else
    python3 omega.py "$@"
fi
