#!/bin/bash
# JARVIS BRAINIAC — Linux/macOS Entry Point
# Usage: ./jarvis.sh [command]

cd "$(dirname "$0")"
python3 jarvis.py "$@"
