# M58b Closeout Handoff (Land + Milestone Closure)

## Scope

This handoff is for the next agent to finish M58b by:
1. validating runtime/tooling alignment,
2. running the staged convergence gate,
3. committing only M58b code/test changes,
4. merging/pushing, and
5. marking milestone closure artifacts.

Date: 2026-03-30

## Current State (already patched in working tree)

### Files patched in this pass

- `src/chronicler/economy.py`
  - Added strict hybrid-mode oracle schema validation in `reconstruct_economy_result(..., require_oracle_shadow=True)`.
  - Fail-fast error if oracle columns are missing (prevents silent 0.0 fallback corruption).
- `src/chronicler/simulation.py`
  - Calls `reconstruct_economy_result(..., require_oracle_shadow=(world.agent_mode == "hybrid"))`.
- `scripts/m58b_convergence_gate.py`
  - Missing price/volume/food comparison data now fails per-seed explicitly.
  - Removed pass-like default behavior for empty volume ratios (`[1.0]`).
  - Catastrophic-tail check now ignores `None` crisis deltas.
- `tests/test_economy_bridge.py`
  - Added strict-oracle-column fail-fast test.
- `tests/test_m58b_gate.py`
  - Updated fixtures to include 3 regions (allows rank-corr path).
  - Added explicit failure test for missing price/volume data.

### Validation already run in this pass

- `./.venv/Scripts/python.exe -m pytest -q tests/test_merchant_mobility.py tests/test_economy_bridge.py tests/test_oracle_gate.py tests/test_m58b_gate.py`
  - 54 passed
- `cargo test --test test_merchant --quiet`
  - 24 passed
- `cargo test --test test_economy --quiet`
  - 19 passed

## Critical Operational Note

Use the project venv interpreter consistently (`.venv\Scripts\python.exe`).

There are multiple Python interpreters on this machine; using the wrong one can load a stale `chronicler_agents` extension and trigger hybrid oracle schema failures.

## Closeout Procedure

### 1) Rebuild/install Rust extension into the same interpreter used for gate runs

From repo root:

```powershell
cd chronicler-agents
..\.venv\Scripts\python.exe -m maturin develop --release
cd ..
```

### 2) Sanity check extension schema (quick)

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe - <<'PY'
from chronicler.world_gen import generate_world
from chronicler.agent_bridge import AgentBridge
from chronicler.resources import get_active_trade_routes, get_season_id
from chronicler.economy import build_economy_region_input_batch, build_economy_trade_route_batch
from chronicler.tuning import get_multiplier, K_TRADE_FRICTION

w = generate_world(seed=1)
b = AgentBridge(w, mode='hybrid')
b.sync_regions(w)
b.tick_agents(w, conquered={})
ri = build_economy_region_input_batch(w)
tr = build_economy_trade_route_batch(w, active_trade_routes=get_active_trade_routes(w))
sid = get_season_id(w.turn)
obs = b._sim.tick_economy(ri, tr, sid, sid == 3, get_multiplier(w, K_TRADE_FRICTION))[2]
print(obs.schema.names)
PY
```

Expected schema includes:
- `oracle_margin`
- `oracle_food_sufficiency`

### 3) Run staged convergence gate (required milestone criterion)

Smoke first (20 seeds):

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe scripts/m58b_convergence_gate.py --smoke --turns 500 --parallel 24 --output output/m58b_gate_smoke
```

If smoke passes, run full gate (200 seeds):

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe scripts/m58b_convergence_gate.py --seeds 200 --turns 500 --parallel 24 --output output/m58b_gate_full
```

### 4) Interpret gate failures correctly

- If failures are mostly `insufficient_price_*` / `insufficient_volume_ratio_data`:
  - first suspect runtime mismatch / stale extension,
  - verify Step 2 schema sanity check,
  - verify gate is executed with `.venv\Scripts\python.exe`.
- If failures are real metric misses (non-insufficiency reasons), treat as calibration/convergence work, not closure.

### 5) Commit only relevant M58b files

Stage only:

- `scripts/m58b_convergence_gate.py`
- `src/chronicler/economy.py`
- `src/chronicler/simulation.py`
- `tests/test_economy_bridge.py`
- `tests/test_m58b_gate.py`

Do not include unrelated dirty docs/untracked paths in this commit.

### 6) Merge/push and closeout docs

After gate pass + commit:

1. Merge to target branch
2. Push
3. Update progress tracker with:
   - gate run IDs/output directories,
   - smoke/full pass status,
   - commit hash,
   - explicit statement that M58b close criteria are satisfied.

## Definition of Done for M58b

- Hybrid runtime uses oracle shadow columns correctly (no silent fallback).
- Staged gate executed with required seed counts.
- Gate passes per M58b acceptance thresholds.
- `--agents=off` behavior unaffected.
- M58b implementation commit merged and pushed.
- Progress document updated with closure evidence.
