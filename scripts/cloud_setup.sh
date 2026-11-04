#!/usr/bin/env bash
# Chronicler setup for Claude Code cloud sessions (or any fresh Linux checkout).
# Installs locked dependencies; does not build the native extension.
# Each step warns instead of aborting so a transient network failure does not
# block the session; look for "!!" in the log. See docs/DEVELOPMENT.md.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 0

step() { local name=$1; shift; echo "== $name"; "$@" || echo "!! setup step failed (continuing): $name"; }

# Default .venv from uv.lock: the offline/no-Rust lane. It must never contain
# chronicler_agents (CI asserts it is absent).
step "uv lock --check" uv lock --check
step "uv sync (.venv)" uv sync --frozen --python python3.13

# Viewer dependencies from package-lock.json.
step "npm ci (viewer)" npm ci --prefix viewer --no-audit --no-fund

# Prefetch Rust crates for native builds and cargo test.
step "cargo fetch" cargo fetch --locked --manifest-path chronicler-agents/Cargo.toml

# Separate native venv outside the repo: dependencies and maturin, no extension.
NATIVE="${CHRONICLER_NATIVE_VENV:-$HOME/.venvs/chronicler-native}"
step "native venv" uv venv -q --allow-existing --python python3.13 "$NATIVE"
step "native deps" env VIRTUAL_ENV="$NATIVE" uv sync -q --frozen --active
step "maturin" uv pip install -q --python "$NATIVE/bin/python" "maturin>=1.5,<2"

echo "== Chronicler setup done"
