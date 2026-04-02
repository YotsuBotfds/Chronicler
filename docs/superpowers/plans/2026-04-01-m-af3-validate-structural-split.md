# M-AF3: `validate.py` Structural Split

**Goal:** Split the oversized validation runner into clearer modules without changing the public `python -m chronicler.validate` entry point or breaking the existing import surface used by tests and operator scripts.

**Architecture:** Keep `src/chronicler/validate.py` as the public CLI facade and backwards-compatible import surface. Move batch/sidecar loading and dependency-preflight logic into `src/chronicler/validation_io.py`, and move oracle algorithms plus per-oracle runner functions into `src/chronicler/validation_oracles.py`.

**Why this seam:**
- `validate.py` was already heavily touched by `M-AF2`.
- The loader/dependency logic and the oracle algorithms are separable without reopening simulation code.
- The facade approach preserves all existing `from chronicler.validate import ...` imports while materially shrinking the main module.

## Split Shape

### `src/chronicler/validation_io.py`

- Bundle loading and seed-run assembly
- Arrow / JSON sidecar readers
- fail-closed dependency preflight
- shared statistical and trajectory helpers consumed by oracle runners
- validation exceptions and shared constants

### `src/chronicler/validation_oracles.py`

- community / needs / cohort / era / artifact / arc algorithms
- determinism gate
- per-oracle runner functions

### `src/chronicler/validate.py`

- CLI parser
- oracle selection / dispatch
- JSON report emission and exit codes
- backwards-compatible re-exports from the two split modules

## Tasks

- [x] Extract validation IO helpers into `validation_io.py`
- [x] Extract oracle algorithms and runner functions into `validation_oracles.py`
- [x] Reduce `validate.py` to a facade/CLI layer with re-exports
- [x] Preserve the existing `run_oracles()` / `main()` behavior from `M-AF2`
- [x] Keep `tests/test_validate.py` green without import churn

## Verification

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_validate.py`
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_live.py tests/test_live_integration.py tests/test_validate.py tests/test_analytics.py tests/test_shadow_oracle.py tests/test_main.py tests/test_bundle.py tests/test_agent_bridge_legacy_migration.py tests/test_curator_legacy_migration.py tests/test_narrative_legacy_migration.py tests/test_infrastructure_legacy_migration.py`
