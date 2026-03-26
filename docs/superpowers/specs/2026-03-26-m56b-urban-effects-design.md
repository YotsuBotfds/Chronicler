# M56b: Urban Effects — Design Spec

> Date: 2026-03-26
> Status: Design approved, pending implementation plan
> Depends on: M56a (Settlement Detection) — implemented on `feat/m56a-settlement-detection`
> Gate: Urban/rural effects are measurable and legible without destabilizing unrelated needs or economy baselines.

---

## 1. Overview

M56b converts M56a's settlement detection into mechanical consequences. Agents inside settlement footprints become "urban" and receive modified needs restoration, satisfaction inputs, cultural drift, and conversion exposure. Rural agents (outside all footprints) behave identically to pre-M56b baseline — zero regression risk.

**Scope:**
- In: Per-agent urban classification via Rust-side assignment, behavioral modifiers in needs/satisfaction/culture/conversion, narrator context enrichment.
- Out: Wealth/income modifiers (overlaps M58), demographics modifiers (calibration-heavy), new event types or curator logic, viewer/bundle schema redesign.

**Dependencies noted but out of spec scope:**
- Workstream 0 (hybrid smoke blocker: `set_economy_config` AttributeError) — must be fixed before hybrid integration tests can run.
- Workstream 3 (calibration/regression gate) — deferred to M61b.

---

## 2. Classification Layer

### 2.1 Signal Shape

Per-agent `settlement_id: u16`. Value `0` = rural (no settlement). Value `>0` = urban (assigned settlement). Downstream code derives `is_urban = settlement_id != 0`.

Rationale: `settlement_id` preserves M56a's spatial precision at agent resolution and is future-proof for settlement-specific mechanics beyond a boolean urban/rural split.

### 2.2 Footprint Data FFI

**New Arrow batch:** `build_settlement_batch()` in `agent_bridge.py` produces a flat Arrow RecordBatch:

| Column | Type | Description |
|--------|------|-------------|
| `region_id` | `u16` | Numeric region index (not name) |
| `settlement_id` | `u16` | From `Settlement.settlement_id` |
| `cell_x` | `u8` | Footprint cell x coordinate (0–9) |
| `cell_y` | `u8` | Footprint cell y coordinate (0–9) |

One row per occupied cell per settlement. Includes **ACTIVE and DISSOLVING** settlements (not just active) to prevent abrupt classification drops during grace period.

**Row sort:** Deterministic `(region_id, settlement_id, cell_y, cell_x)` before FFI transfer.

**Overflow guard:** `build_settlement_batch()` checks `world.next_settlement_id > 65535` as the primary fail-fast condition and raises `ValueError` before emitting any rows. This catches overflow at the allocation point, not after settlement creation.

**Off-mode:** When `--agents=off`, `build_settlement_batch()` is not called. No batch is produced.

### 2.3 Rust-Side Grid Construction

On each tick, Rust consumes the settlement batch and builds a per-region lookup grid:

```
settlement_grids: Vec<[u16; 100]>   // one 10×10 grid per region
```

Index formula: `grid[region_id][cell_y * 10 + cell_x]`. Value = `settlement_id` (0 = no settlement).

**Tie-break:** If multiple rows map to the same `(region_id, cell_x, cell_y)`, **lowest `settlement_id` wins**. Built during grid construction by processing rows in batch sort order (already sorted by settlement_id ascending).

**Grid size coupling:** Both Python (`settlements.py:GRID_SIZE = 10`) and Rust (hardcoded grid size 10, array `[u16; 100]`) must agree. This is a cross-boundary invariant — the spec mandates a Rust constant `SETTLEMENT_GRID_SIZE = 10` mirroring the Python constant, with a comment linking to this spec.

### 2.4 Dual-Pass Assignment

Settlement assignment runs twice per tick to match the tick phase ordering in `tick_agents()` (`tick.rs:44`):

**Pass A — pre-needs/satisfaction** (between wealth_tick and update_needs):
- For each alive agent: compute cell from current (pre-migration) position using `cell_x = min((x * 10) as u8, 9)`, `cell_y = min((y * 10) as u8, 9)`.
- Write `pool.settlement_ids[slot] = settlement_grids[region][cell]`.
- Feeds: `update_needs()` (step 0.75), `update_satisfaction()` (step 1).

**Pass B — post-migration/demographics** (between death cleanup sweep and cultural drift):
- Same assignment logic, but agent positions reflect post-migration state.
- Write `pool.settlement_ids[slot]` with updated values (includes newborns).
- Feeds: `culture_tick()` (step 6), `conversion_tick()` (step 7).
- This value persists into the snapshot export.

**Exact tick insertion points** (referencing `tick.rs` step numbers):
```
  0.5  Wealth tick
  >>>  Pass A: assign settlement_id (pre-movement)
  0.75 Needs restoration          ← reads settlement_id
  1.   Satisfaction update         ← reads settlement_id via SatisfactionInputs.is_urban
  ...
  3-4. Decisions + migrations
  4.5. Spatial drift
  5.   Demographics (births/deaths)
  5.1  Death cleanup sweep
  >>>  Pass B: reassign settlement_id (post-movement)
  6.   Cultural drift              ← reads settlement_id
  7.   Conversion                  ← reads settlement_id
```

### 2.5 AgentPool Field

Add `pub settlement_ids: Vec<u16>` to `AgentPool` (`pool.rs:17`). SoA field, initialized to `0` for all slots. Updated by dual-pass assignment each tick. 2 bytes per agent — matches the Phase 7 memory budget table allocation.

Included in snapshot export: add `Field::new("settlement_id", DataType::UInt16, false)` to `snapshot_schema()` (`ffi.rs:64`) and corresponding builder in `to_record_batch()` (`pool.rs:476`).

---

## 3. Behavioral Modifiers

All constants marked `[CALIBRATE M61b]`. Rural agents (settlement_id == 0) receive no modification — all multipliers are 1.0x / additive 0 for rural.

### 3.1 Needs Restoration (`needs.rs`)

Multiplicative modifiers on per-need restoration delta, applied inside `restore_needs()` (`needs.rs:183`).

The 6 needs are: `safety`, `material`, `social`, `spiritual`, `autonomy`, `purpose` (pool.rs:63-68). There is no separate food need — food sufficiency contributes to safety and material restoration as an input factor.

**Safety and Social** — total-delta multipliers (applied to the computed `delta` for each need):

| Need | Urban Multiplier | Constant Name |
|------|-----------------|---------------|
| Safety | 0.90 | `URBAN_SAFETY_RESTORATION_MULT` |
| Social | 1.08 | `URBAN_SOCIAL_RESTORATION_MULT` |
| Spiritual | 1.0 | — (no M56b effect) |
| Autonomy | 1.0 | — (no M56b effect) |
| Purpose | 1.0 | — (no M56b effect) |

Applied as: `delta *= mult` when `pool.settlement_ids[slot] != 0`.

**Material** — per-term multipliers (no overlapping effects). Material restoration has two additive terms (needs.rs:228-244): a food-sufficiency contribution and a wealth-percentile contribution. Each gets its own modifier:

| Term | Urban Multiplier | Constant Name |
|------|-----------------|---------------|
| Food-sufficiency contribution | 0.92 | `URBAN_FOOD_SUFFICIENCY_MULT` |
| Wealth-percentile contribution | 1.10 | `URBAN_WEALTH_RESTORATION_MULT` |

Explicit formula for urban material restoration:
```
food_term  = MATERIAL_RESTORE_FOOD * food_sufficiency * deficit * URBAN_FOOD_SUFFICIENCY_MULT
wealth_term = MATERIAL_RESTORE_WEALTH * wealth_percentile * deficit * URBAN_WEALTH_RESTORATION_MULT
delta = food_term + wealth_term
```

For rural agents (settlement_id == 0), both multipliers are 1.0 — no change from current behavior. This avoids the overlapping-multiply problem where a single total-delta multiplier would net the food term back above baseline (`1.10 * 0.92 = 1.012`).

### 3.2 Satisfaction (`satisfaction.rs`)

**SatisfactionInputs extension:** Add `is_urban: bool` field to `SatisfactionInputs` struct (`satisfaction.rs:132`). Follows the established pattern of extending the struct, not adding positional params.

**Two additive terms** in `compute_satisfaction_with_culture()`:

| Term | Value | Constant Name | Budget |
|------|-------|---------------|--------|
| Material bonus | +0.02 | `URBAN_MATERIAL_SATISFACTION_BONUS` | Outside penalty cap (positive) |
| Safety penalty | -0.04 | `URBAN_SAFETY_SATISFACTION_PENALTY` | Inside -0.40 non-ecological cap |

**Priority clamp order** (within the -0.40 non-ecological cap, from `compute_satisfaction_with_culture()`):
1. Cultural mismatch + Religious mismatch + Persecution (the existing `three_term`)
2. **Urban safety penalty** ← new, clamped to remaining budget after three_term
3. Class tension — clamped to remaining budget after three_term + urban
4. Memory (M48) — clamped to remaining budget after three_term + urban + class tension

The urban safety penalty slots between the existing `three_term` block and class tension. If cultural + religious + persecution already consume most of the -0.40 budget, the urban penalty is reduced first, then class tension, then memory. This preserves the existing priority ordering — class tension and memory shift down one position but keep their relative order.

### 3.3 Cultural Drift (`culture_tick.rs`)

```
URBAN_CULTURE_DRIFT_MULT = 1.15   [CALIBRATE M61b]
```

Applied inside `culture_tick()`: when processing each agent's drift roll, multiply the effective drift rate by `URBAN_CULTURE_DRIFT_MULT` if `pool.settlement_ids[slot] != 0`.

Urban agents drift toward controller values ~15% faster — cosmopolitan mixing in dense settlements.

### 3.4 Conversion Exposure (`conversion_tick.rs`)

```
URBAN_CONVERSION_MULT = 1.06   [CALIBRATE M61b]
```

Applied inside `conversion_tick()`: multiply the per-agent conversion probability by `URBAN_CONVERSION_MULT` if `pool.settlement_ids[slot] != 0`.

Deliberately lower than the culture drift multiplier (1.06 vs 1.15) to avoid culture + conversion stacking overpowering the milestone's behavioral signal.

---

## 4. Narrator Integration (Context Enrichment)

No new event types. No new curator logic. Enrich existing narration context so the LLM can organically reference urbanization.

### 4.1 Narration Context Payload

Urbanization data reaches the narrator through two existing paths:

**Via `CivSnapshot` (already in `TurnSnapshot.civ_stats`, section 5.1):**
- `urban_agents: int`, `urban_fraction: float` — available on every turn snapshot the narrator receives.

**Via `AgentContext` (`models.py:868`) — new fields:**
- `urban_fraction_delta_20t: float` — change in urban_fraction over last 20 turns (0.0 if < 20 turns)
- `top_settlements: list[SettlementSummary]` — up to 3 largest settlements by population for the relevant civ

No new per-region narration fields. Per-region `urban_fraction` is derivable from the agent snapshot if needed, but not pre-aggregated for the narrator in M56b.

### 4.2 Delta Computation

`urban_fraction_delta_20t` is computed when building narration context by scanning the turn history list for the snapshot whose `snapshot.turn == current_turn - 20`. If found, compute `current_urban_fraction - past_urban_fraction`. If no snapshot with that turn exists (fewer than 20 turns of history, or gaps from save/load), default `0.0`. Lookup is by `snapshot.turn` field, not by list index. No new transient state on WorldState.

### 4.3 Existing Event Types

M56a already landed `settlement_founded` and `settlement_dissolved` event types. M56b does not add new event types. Threshold-based urbanization trend events (e.g., "civilization becomes majority-urban") are explicitly deferred to post-M61b calibration, at which point they should include hysteresis + persistence-window guards to prevent chatter during tuning.

---

## 5. Analytics & Snapshot

### 5.1 TurnSnapshot Additions

Add to `TurnSnapshot` (`models.py:792`):
- `urban_agent_count: int = 0` — total urban agents across all civs
- `urban_fraction: float = 0.0` — global urban fraction

Add to `CivSnapshot` (`models.py:748`):
- `urban_agents: int = 0`
- `urban_fraction: float = 0.0`

These are computed from the post-tick agent snapshot's `settlement_id` column during snapshot aggregation in `main.py`.

### 5.2 Analytics Extractor

Extend `extract_settlement_diagnostics()` (`analytics.py:1862`) with:
- Per-civ urban fraction time series (derived from `CivSnapshot.urban_fraction` across turns)
- Global urbanization trend

**Deferred:** Urban/rural satisfaction split and need fulfillment comparison analytics. These require per-turn aggregates not currently available in `CivSnapshot`. Raw data exists in agent snapshots for ad-hoc analysis. Defer structured split analytics to a dedicated analytics milestone or M61b.

### 5.3 Rust Snapshot Schema

Add `settlement_id: UInt16` to:
- `snapshot_schema()` (`ffi.rs:64`) — new field after `y`
- `to_record_batch()` (`pool.rs:476`) — new UInt16Builder

Python snapshot consumers (`agent_bridge.py`) parse the new column for aggregation.

---

## 6. Constraints & Guards

| Constraint | Preservation strategy |
|------------|----------------------|
| **-0.40 non-ecological satisfaction cap** | Urban safety penalty (-0.04) enters priority clamp after three_term (cultural+religious+persecution), before class tension and memory. No new budget — fits within existing -0.40 total. See section 3.2 for full priority order. |
| **Off-mode (`--agents=off`)** | No settlement batch built, no assignment, no modifier application. Entire M56b codepath gated on agent mode. Settlement detection (M56a) is already no-op in off-mode. |
| **Determinism** | Flat grid lookup (no HashMap), deterministic batch row sort, lowest-ID tie-break, dual-pass assignment in fixed tick order. No new RNG sources. |
| **Transient signal rule** | Settlement grids rebuilt from batch every tick (no stale carry-over). No new persistent transient state on WorldState. |
| **SatisfactionInputs pattern** | New `is_urban: bool` field on struct, not positional parameter. |
| **RNG stream offsets** | No new RNG sources — all modifiers are deterministic multipliers on existing values. No offset reservation needed. |
| **Memory budget** | 2 bytes (u16) per agent for `settlement_id`. Matches Phase 7 roadmap table allocation. |
| **Grid size cross-boundary invariant** | Python `GRID_SIZE = 10` and Rust `SETTLEMENT_GRID_SIZE = 10` must match. Both constants linked by comment to this spec. |
| **u16 overflow** | Python `build_settlement_batch()` fails fast if `world.next_settlement_id > 65535`. |

---

## 7. File Touch Map

### Python
| File | Changes |
|------|---------|
| `src/chronicler/agent_bridge.py` | `build_settlement_batch()`, settlement grid FFI, snapshot `settlement_id` parsing, urban aggregation |
| `src/chronicler/simulation.py` | Wire settlement batch into bridge tick call |
| `src/chronicler/models.py` | `CivSnapshot.urban_agents/urban_fraction`, `TurnSnapshot.urban_agent_count/urban_fraction`, `AgentContext.urban_fraction_delta_20t/top_settlements` |
| `src/chronicler/main.py` | Urban fraction aggregation during snapshot build |
| `src/chronicler/narrative.py` | Urbanization fields in narration context |
| `src/chronicler/analytics.py` | Extend `extract_settlement_diagnostics()` with urbanization series |

### Rust
| File | Changes |
|------|---------|
| `chronicler-agents/src/pool.rs` | `settlement_ids: Vec<u16>` SoA field, snapshot builder addition |
| `chronicler-agents/src/ffi.rs` | Settlement batch ingestion, `snapshot_schema()` addition, settlement grid construction |
| `chronicler-agents/src/tick.rs` | Dual-pass `assign_settlement_ids()` at steps 0.5→0.75 and 5.1→6 |
| `chronicler-agents/src/needs.rs` | Urban restoration multipliers in `restore_needs()` |
| `chronicler-agents/src/satisfaction.rs` | `is_urban` on `SatisfactionInputs`, material bonus + safety penalty in `compute_satisfaction_with_culture()` |
| `chronicler-agents/src/culture_tick.rs` | Urban drift multiplier in `culture_tick()` |
| `chronicler-agents/src/conversion_tick.rs` | Urban conversion multiplier in `conversion_tick()` |
| `chronicler-agents/src/agent.rs` | Urban modifier constants |

### Tests
| File | Changes |
|------|---------|
| `tests/test_agent_bridge.py` | Settlement batch construction, urban aggregation |
| `tests/test_narrative.py` | Urbanization fields in narration context |
| `tests/test_analytics.py` | Extended settlement diagnostics |
| `chronicler-agents/tests/` | Grid construction, dual-pass assignment, needs/satisfaction/culture/conversion directional tests, determinism, cap preservation |

---

## 8. Validation & Test Plan

### 8.1 Unit Tests (no hybrid dependency)

**Grid & assignment:**
- Deterministic grid construction from settlement footprints
- Agent at (0.35, 0.72) in settlement footprint → correct `settlement_id`
- Agent outside all footprints → `settlement_id = 0`
- Tie-break: overlapping cells → lowest `settlement_id` wins
- Dissolving settlement footprints included in grid
- `u16` overflow guard fires when `world.next_settlement_id > 65535`
- Batch row sort is deterministic

**Directional behavior (Rust unit tests):**
- Urban agent: safety need restores slower than rural baseline (0.90x total delta)
- Urban agent: social need restores faster than rural baseline (1.08x total delta)
- Urban agent: material wealth-percentile contribution restores faster (1.10x per-term)
- Urban agent: material food-sufficiency contribution is reduced (0.92x per-term)
- Urban agent: material food term is below rural baseline (no overlapping multiply)
- Urban agent: satisfaction includes material bonus (+0.02 delta)
- Urban agent: satisfaction includes safety penalty (-0.04 delta)
- Rural agent: all values identical to pre-M56b baseline (zero-change test)
- Satisfaction cap: urban safety penalty doesn't breach -0.40 total when other penalties are at budget

**Culture & conversion:**
- Urban agent: culture drift rate > rural (1.15x)
- Urban agent: conversion probability > rural (1.06x)
- Rural agent: drift rate and conversion probability unchanged

**Dual-pass consistency:**
- Pass A assignment matches pre-movement position
- Pass B assignment matches post-movement position
- Agent migrating from urban cell to rural cell: needs/satisfaction used urban (Pass A), culture/conversion used rural (Pass B)

### 8.2 Integration Tests (require hybrid fix — Workstream 0)

- Multi-turn hybrid run: urban agents emerge where settlements exist
- Urbanization metrics appear in snapshot (`urban_agent_count`, `urban_fraction`)
- Same seed → identical urban assignments and downstream outcomes across runs
- Off-mode 30-turn run: zero urban metrics, no crashes
- Urban fraction appears in narration context for civs with settlements

### 8.3 Merge Gates

1. All unit + directional tests green
2. Off-mode 30-turn run clean (`--agents=off --seed 42 --turns 30 --simulate-only`)
3. Hybrid 30-turn run clean (`--agents hybrid --seed 42 --turns 30 --simulate-only`) — **blocked until Workstream 0 (hybrid smoke fix) is resolved**
4. 200-seed regression sweep — **deferred to M61b calibration pass**

---

## 9. Constants Summary

All `[CALIBRATE M61b]`. Rural = baseline.

| Constant | Value | Location |
|----------|-------|----------|
| `URBAN_SAFETY_RESTORATION_MULT` | 0.90 | `agent.rs` |
| `URBAN_SOCIAL_RESTORATION_MULT` | 1.08 | `agent.rs` |
| `URBAN_FOOD_SUFFICIENCY_MULT` | 0.92 | `agent.rs` |
| `URBAN_WEALTH_RESTORATION_MULT` | 1.10 | `agent.rs` |
| `URBAN_MATERIAL_SATISFACTION_BONUS` | 0.02 | `agent.rs` |
| `URBAN_SAFETY_SATISFACTION_PENALTY` | 0.04 | `agent.rs` (stored positive, applied as negative) |
| `URBAN_CULTURE_DRIFT_MULT` | 1.15 | `agent.rs` |
| `URBAN_CONVERSION_MULT` | 1.06 | `agent.rs` |
| `SETTLEMENT_GRID_SIZE` | 10 | `agent.rs` (mirrors `settlements.py:GRID_SIZE`) |
