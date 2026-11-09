#!/usr/bin/env bash
# Chronicler setup for Claude Code cloud sessions (or any fresh Linux checkout).
# Installs locked dependencies; does not build the native extension.
# Each step warns instead of aborting so a transient network failure does not
# block the session; look for "!!" in the log. See docs/DEVELOPMENT.md.
set -uo pipefail
# Resolve the script directory with builtins so a broken PATH cannot land us elsewhere.
SCRIPT_DIR=.; case "${BASH_SOURCE[0]}" in */*) SCRIPT_DIR=${BASH_SOURCE[0]%/*} ;; esac
cd "$SCRIPT_DIR/.." || { echo "!! cannot enter repo root"; exit 1; }

FAILED=()
step() { local name=$1; shift; echo "== $name"; "$@" || { echo "!! setup step failed (continuing): $name"; FAILED+=("$name"); }; }

# Record missing tools before use; the steps that need them fail as well.
for tool in uv npm cargo; do
    command -v "$tool" >/dev/null 2>&1 || { echo "!! required tool not on PATH: $tool"; FAILED+=("command -v $tool"); }
done

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

# Report both environments (scripts/check_python_env.py). The default .venv
# must have no chronicler_agents; the native venv has none until you build it.
step "check .venv (no native)" .venv/bin/python scripts/check_python_env.py --expect no-native
step "check native venv" "$NATIVE/bin/python" scripts/check_python_env.py

# Summary. The default exit is 0 so a failed step never stops a cloud session
# from starting; CHRONICLER_SETUP_STRICT=1 exits 1 when any step failed.
echo "== setup summary"
if [ ${#FAILED[@]} -eq 0 ]; then
    echo "all setup steps passed"
else
    for name in "${FAILED[@]}"; do echo "!! failed: $name"; done
fi
[ "${CHRONICLER_SETUP_STRICT:-0}" = 1 ] && [ ${#FAILED[@]} -gt 0 ] && exit 1
echo "== Chronicler setup done"
exit 0
