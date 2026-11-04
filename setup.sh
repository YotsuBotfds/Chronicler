#!/usr/bin/env bash
# Chronicler setup script — installs all dependencies and builds components.
# Usage: bash setup.sh
#
# Options:
#   --no-rust     Skip Rust agent crate build; .venv is verified to hold none
#   --native-venv Build the agent crate into a separate native venv instead of
#                 .venv, keeping .venv extension-free for the no-Rust and
#                 offline test lanes (development; see docs/DEVELOPMENT.md)
#   --api         Install Claude API narration support
#   --gemini      Install Gemini API narration support
#
# With uv (https://docs.astral.sh/uv/) the default .venv is installed exactly
# from uv.lock (`uv sync --frozen`, like CI). Without uv it falls back to an
# UNLOCKED `pip install -e .` and says so. Any chronicler_agents already in
# .venv is removed first, so the extension present afterwards is the one this
# run built (or none), and scripts/check_python_env.py verifies that at the end.
#
# Environment overrides:
#   CHRONICLER_PYTHON       interpreter to use (default: python3.13, python3, python)
#   UV_PROJECT_ENVIRONMENT  default venv path (default: .venv)
#   CHRONICLER_NATIVE_VENV  native venv path (default: ~/.venvs/chronicler-native)

set -euo pipefail

NO_RUST=0
SEPARATE_NATIVE=0
INSTALL_API=0
INSTALL_GEMINI=0

for arg in "$@"; do
    case "$arg" in
        --no-rust)   NO_RUST=1 ;;
        --native-venv) SEPARATE_NATIVE=1 ;;
        --api)       INSTALL_API=1 ;;
        --gemini)    INSTALL_GEMINI=1 ;;
        *) echo "Unknown option: $arg"; exit 1 ;;
    esac
done

cd "$(dirname "${BASH_SOURCE[0]}")"

VENV="${UV_PROJECT_ENVIRONMENT:-.venv}"
NATIVE_VENV="${CHRONICLER_NATIVE_VENV:-$HOME/.venvs/chronicler-native}"
EXTRAS=()
if [ "$INSTALL_API" -eq 1 ]; then EXTRAS+=(api); fi
if [ "$INSTALL_GEMINI" -eq 1 ]; then EXTRAS+=(gemini); fi

venv_python() {
    if [ -x "$1/bin/python" ]; then echo "$1/bin/python"
    elif [ -x "$1/Scripts/python.exe" ]; then echo "$1/Scripts/python.exe"
    else echo "ERROR: no Python in virtual environment $1. Remove it and rerun setup." >&2; return 1
    fi
}

venv_activate() {
    if [ -f "$1/bin/activate" ]; then echo "$1/bin/activate"
    elif [ -f "$1/Scripts/activate" ]; then echo "$1/Scripts/activate"
    else echo "ERROR: virtual environment activation script not found in $1. Remove it and rerun setup." >&2; return 1
    fi
}

# Locked when uv is available: an exact sync of uv.lock (it also uninstalls
# anything the lock does not list, such as a stale chronicler_agents).
# Otherwise an unlocked editable pip install of the same project and extras.
install_env() {
    local env=$1 python
    if [ "$USE_UV" -eq 1 ]; then
        local uv_extras=()
        for extra in ${EXTRAS[@]+"${EXTRAS[@]}"}; do uv_extras+=(--extra "$extra"); done
        UV_PROJECT_ENVIRONMENT="$env" uv sync --frozen --python "$PYTHON" ${uv_extras[@]+"${uv_extras[@]}"}
    else
        [ -d "$env" ] || "$PYTHON" -m venv "$env"
        python=$(venv_python "$env")
        local spec="."
        if [ "${#EXTRAS[@]}" -gt 0 ]; then spec=".[$(IFS=,; echo "${EXTRAS[*]}")]"; fi
        "$python" -m pip install -e "$spec" pytest pytest-asyncio --quiet
    fi
}

echo "=== Chronicler Setup ==="
echo ""

# Check Python: CHRONICLER_PYTHON, else the first 3.13+ of python3.13, python3, python.
python_ok() {
    command -v "$1" &>/dev/null && "$1" -c 'import sys; raise SystemExit(sys.version_info < (3, 13))' 2>/dev/null
}
PYTHON=""
for candidate in ${CHRONICLER_PYTHON:+"$CHRONICLER_PYTHON"} python3.13 python3 python; do
    if python_ok "$candidate"; then PYTHON=$candidate; break; fi
    if [ -n "${CHRONICLER_PYTHON:-}" ]; then break; fi
done
if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.13+ is required but not found${CHRONICLER_PYTHON:+ (CHRONICLER_PYTHON=$CHRONICLER_PYTHON)}."
    echo "  Install from: https://www.python.org/downloads/"
    exit 1
fi
PYTHON=$("$PYTHON" -c 'import sys; print(sys.executable)')
PY_VERSION=$("$PYTHON" -c 'import platform; print(platform.python_version())')
echo "[1/4] Found Python $PY_VERSION ($PYTHON)"

if command -v uv &>/dev/null; then
    USE_UV=1
    echo "[2/4] Installing locked Python dependencies into $VENV (uv sync --frozen)..."
    uv lock --check --python "$PYTHON"
else
    USE_UV=0
    echo "[2/4] WARNING: uv not found; falling back to an UNLOCKED pip install into $VENV."
    echo "  Versions are whatever the package index serves today, not uv.lock, so this"
    echo "  environment may differ from CI. For the locked setup install uv and rerun:"
    echo "  https://docs.astral.sh/uv/getting-started/installation/"
fi
install_env "$VENV"
DEFAULT_PY=$(venv_python "$VENV")
if [ "$USE_UV" -eq 0 ] && "$DEFAULT_PY" -m pip show chronicler-agents &>/dev/null; then
    echo "  Removing the previously installed chronicler_agents from $VENV"
    "$DEFAULT_PY" -m pip uninstall -y chronicler-agents --quiet
fi

# Build the Rust agent crate into $VENV, or with --native-venv into the
# separate native venv so that $VENV stays extension-free.
BUILT_NATIVE=0
if [ "$SEPARATE_NATIVE" -eq 1 ]; then TARGET_VENV=$NATIVE_VENV; else TARGET_VENV=$VENV; fi
if [ "$NO_RUST" -eq 0 ]; then
    if command -v cargo &>/dev/null; then
        echo "[3/4] Building Rust agent crate into $TARGET_VENV..."
        if [ "$SEPARATE_NATIVE" -eq 1 ]; then install_env "$NATIVE_VENV"; fi
        NATIVE_PY=$(venv_python "$TARGET_VENV")
        MATURIN_FLAGS=()
        if [ "$USE_UV" -eq 1 ]; then
            uv pip install --quiet --python "$NATIVE_PY" "maturin>=1.5,<2"
            MATURIN_FLAGS=(--uv)  # a uv venv has no pip
        fi
        (
            # Activation sets VIRTUAL_ENV, which maturin develop installs into.
            # shellcheck disable=SC1090
            source "$(venv_activate "$TARGET_VENV")"
            if [ "$USE_UV" -eq 0 ]; then
                python -m pip install "maturin>=1.5,<2" --quiet
            fi
            cd chronicler-agents
            python -m maturin develop --release --locked ${MATURIN_FLAGS[@]+"${MATURIN_FLAGS[@]}"}
        )
        BUILT_NATIVE=1
    else
        echo "[3/4] Rust toolchain not found — skipping agent crate"
        echo "  Install from: https://rustup.rs/"
        echo "  Agent mode (--agents) will not be available"
    fi
else
    echo "[3/4] Skipping Rust agent crate (--no-rust)"
fi

echo "[4/4] Verifying environments..."
if [ "$BUILT_NATIVE" -eq 0 ] || [ "$SEPARATE_NATIVE" -eq 1 ]; then
    if ! "$DEFAULT_PY" scripts/check_python_env.py --expect no-native; then
        echo "ERROR: $VENV is not a clean no-native environment for this checkout (see above)."
        exit 1
    fi
fi
if [ "$BUILT_NATIVE" -eq 1 ] && ! "$NATIVE_PY" scripts/check_python_env.py --expect native; then
    echo "ERROR: $TARGET_VENV does not hold a compiled chronicler_agents for this checkout (see above)."
    exit 1
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To get started:"
echo "  source $(venv_activate "$VENV")"
echo "  chronicler --seed 42 --turns 50 --simulate-only"
if [ "$BUILT_NATIVE" -eq 1 ] && [ "$SEPARATE_NATIVE" -eq 1 ]; then
    echo ""
    echo "Agent mode (--agents) runs from the native venv:"
    echo "  source $(venv_activate "$NATIVE_VENV")"
    echo "  chronicler --seed 42 --turns 100 --agents hybrid --simulate-only"
elif [ "$BUILT_NATIVE" -eq 1 ]; then
    echo "  chronicler --seed 42 --turns 100 --agents hybrid --simulate-only"
    echo "  (a later \`uv sync\` removes the extension from $VENV; rerun setup to rebuild)"
fi
echo ""
echo "For narration, run LM Studio with a model loaded, then:"
echo "  chronicler --seed 42 --turns 50"
