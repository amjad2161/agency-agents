#!/bin/bash
# JARVIS BRAINIAC — Linux/macOS Installer
# Run: chmod +x install.sh && ./install.sh

set -e

echo "============================================"
echo "  JARVIS BRAINIAC v28.0 — Installer"
echo "============================================"
echo ""

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
REQUIRED="3.10"

if [ "$(printf '%s\n' "$REQUIRED" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED" ]; then
    echo "❌ Python 3.10+ required. Found: $PYTHON_VERSION"
    exit 1
fi
echo "✅ Python $PYTHON_VERSION detected"

# Check git
if ! command -v git &> /dev/null; then
    echo "❌ Git not found. Please install git."
    exit 1
fi
echo "✅ Git detected"

# Create virtual environment (optional)
read -p "Create virtual environment? (y/n): " venv_answer
if [ "$venv_answer" = "y" ]; then
    python3 -m venv .venv
    source .venv/bin/activate
    echo "✅ Virtual environment created"
fi

# Install dependencies
echo ""
echo "[1/5] Installing core dependencies..."
pip install -q click numpy pandas Pillow matplotlib pytest

# Install optional dependencies
echo "[2/5] Installing optional dependencies..."
pip install -q ollama chromadb faiss-cpu sentence-transformers || echo "⚠️ Some optional deps failed (OK)"

# Install development dependencies
echo "[3/5] Installing dev dependencies..."
pip install -q pytest black flake8 mypy

# Run bootstrap
echo ""
echo "[4/5] Running bootstrap..."
python jarvis_bootstrap.py

# Run tests
echo ""
echo "[5/5] Running tests..."
pytest runtime/tests/ -q

echo ""
echo "============================================"
echo "  ✅ JARVIS BRAINIAC installed successfully!"
echo "============================================"
echo ""
echo "Next steps:"
echo "  • Start CLI:     python -m runtime.agency.cli"
echo "  • Start server:  python -m runtime.agency.server"
echo "  • Run demo:      python -c 'from runtime.agency.real_demo import get_real_demo; get_real_demo().run_all_demos()'"
echo "  • Read README:   cat README.md"
echo ""
echo "Optional: Install Ollama for local LLM:"
echo "  curl -fsSL https://ollama.com/install.sh | sh"
echo "  ollama pull llama3"
echo ""
