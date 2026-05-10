#!/usr/bin/env bash
# Chronicler setup script — installs all dependencies and builds components.
# Usage: bash setup.sh
#
# Options:
#   --no-rust     Skip Rust agent crate build
#   --api         Install Claude API narration support
#   --gemini      Install Gemini API narration support

set -euo pipefail

NO_RUST=0
INSTALL_API=0
INSTALL_GEMINI=0

for arg in "$@"; do
    case "$arg" in
        --no-rust)   NO_RUST=1 ;;
        --api)       INSTALL_API=1 ;;
        --gemini)    INSTALL_GEMINI=1 ;;
        *) echo "Unknown option: $arg"; exit 1 ;;
    esac
done

echo "=== Chronicler Setup ==="
echo ""

# Check Python
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "ERROR: Python 3.13+ is required but not found."
    echo "  Install from: https://www.python.org/downloads/"
    exit 1
fi

PYTHON=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
PY_VERSION=$($PYTHON --version 2>&1 | sed 's/[^0-9]*\([0-9]*\.[0-9]*\).*/\1/')
echo "[1/4] Found Python $PY_VERSION"

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "[2/4] Creating virtual environment..."
    $PYTHON -m venv .venv
else
    echo "[2/4] Virtual environment already exists"
fi

# Activate
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
else
    echo "ERROR: Virtual environment activation script not found. Remove .venv and rerun setup."
    exit 1
fi

# Install Python dependencies
echo "[3/4] Installing Python dependencies..."
python -m pip install -e . --quiet

if [ "$INSTALL_API" -eq 1 ]; then
    echo "  Installing Claude API support..."
    python -m pip install -e ".[api]" --quiet
fi

if [ "$INSTALL_GEMINI" -eq 1 ]; then
    echo "  Installing Gemini API support..."
    python -m pip install -e ".[gemini]" --quiet
fi

# Build Rust agent crate
if [ "$NO_RUST" -eq 0 ]; then
    if command -v cargo &>/dev/null; then
        echo "[4/4] Building Rust agent crate..."
        python -m pip install "maturin>=1.5,<2" --quiet
        cd chronicler-agents
        python -m maturin develop --release
        cd ..
    else
        echo "[4/4] Rust toolchain not found — skipping agent crate"
        echo "  Install from: https://rustup.rs/"
        echo "  Agent mode (--agents) will not be available"
    fi
else
    echo "[4/4] Skipping Rust agent crate (--no-rust)"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To get started:"
echo "  source .venv/bin/activate"
echo "  chronicler --seed 42 --turns 50 --simulate-only"
echo ""
echo "For narration, run LM Studio with a model loaded, then:"
echo "  chronicler --seed 42 --turns 50"
