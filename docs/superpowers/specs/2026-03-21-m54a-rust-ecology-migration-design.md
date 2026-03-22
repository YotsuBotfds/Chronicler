# M54a: Rust Ecology Migration — Design Spec

> **Status:** Design-ahead while M53 gate remains blocked. Implementation cannot begin until M53 merges to main.
> **Branch:** TBD (will branch from main after M53 merges)
> **Depends on:** M53 (depth tuning pass) — M53 tuning complete but validation gate failed; M54a blocked pending follow-on closure effort
> **Estimated days:** 8-11
> **Roadmap ref:** `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md` — Scale Track

---

## Goal

Migrate Phase 9 ecology computation from Python to Rust with rayon parallelism, establishing the Arrow-batch-in / Arrow-batch-out FFI pattern that M54b (economy) and M54c (politics) will follow. Python's turn loop becomes orchestration; Rust executes the hot path.

At current region counts (10-30), the parallelism benefit is minimal. This milestone is about:
1. Establishing the migration pattern and FFI surface
2. Validating determinism under parallel execution
3. Removing Python as the bottleneck for ecology computation at future scale (500K-1M agents)

---

## Scope

### What moves to Rust

- Three-variable ecology tick: soil, water, forest_cover — per-region, controlled and uncontrolled paths
- Disease severity computation: flare triggers (overcrowding, army passage, water quality, seasonal peak), decay, pandemic suppression
- Cross-effects: forest → soil bonus
- River deforestation cascade: two-pass sequential (gather upstream state, apply downstream deltas, second clamp)
- Resource yield computation: ecology × climate × season × reserve modifiers → ephemeral `current_turn_yields`
- Depletion feedback / streak updates: soil pressure streaks, overextraction streaks, yield penalties, event emission
- Ecology clamping: terrain caps and floors
- `prev_turn_water` persistence

### What stays in Python

- Famine detection and application (population drain, stability drain, accumulator routing)
- Refugee flow to adjacent regions
- `famine_cooldown` management (skip-on-cooldown, set-to-5, decrement-each-turn)
- `apply_soil_floor()` (traditions)
- Terrain succession counters (`low_forest_turns`, `forest_regrowth_turns`) and `_update_ecology_counters()`
- `tick_terrain_succession()` — checks counters and applies terrain transitions. Mutates `terrain`, `carrying_capacity`, `soil`, `forest_cover` on affected regions. These mutations flow back to Rust via `apply_region_postpass_patch()`.
- `sync_all_populations()`
- Event materialization: Rust returns typed triggers, Python builds `Event` objects with names/descriptions/actors

### What gets deleted after all consumers are switched (including `--agents=off` mode)

- `_tick_soil()`, `_tick_water()`, `_tick_forest()`, `_apply_cross_effects()`, `_clamp_ecology()`
- `compute_disease_severity()`
- `compute_resource_yields()`, `update_depletion_feedback()`
- `_last_region_yields` module-level cache
- River cascade loop in `tick_ecology()`

Deletion is gated on both hybrid-mode and off-mode being wired through Rust ecology. See `--agents=off` mode section below.

### What `tick_ecology()` becomes

A thin Python orchestration function:
1. Call Rust `tick_ecology()`
2. Write returned region state back onto Python `Region` objects
3. Materialize ecology trigger events into `Event` objects
4. Run Python post-pass: famine → soil floor → terrain counters → terrain succession → population sync
5. (Agent tick sees post-ecology yields via `RegionState.resource_yields` without extra plumbing)

### `--agents=off` mode

Today, `--agents=off` does not instantiate `AgentBridge` or `AgentSimulator`, but Phase 9 ecology still runs in every mode via Python `tick_ecology()`. Since M54a places ecology computation on `AgentSimulator`, the design must handle off-mode explicitly.

**Approach:** In `--agents=off` mode, Python instantiates a lightweight `AgentSimulator` (or a new `EcologySimulator` wrapper) solely for ecology computation — no agent pool, no agent tick. The same `set_region_state()` → `tick_ecology()` → write-back → post-pass → patch path executes. The agent `tick()` call (step 6) is skipped. This preserves the repo invariant that `--agents=off` produces valid Phase 9 output.

**Alternative:** Keep the old Python ecology code alive as the off-mode path. This is simpler but means maintaining two ecology implementations indefinitely and makes the "delete Python ecology functions" step conditional rather than clean. Not recommended.

**Implication for deletion:** The "delete Python ecology functions" step can only happen after the off-mode path is wired through Rust. Until then, Python ecology code must remain as the off-mode fallback. The implementation plan should sequence this: wire off-mode through Rust early (after step 11), verify with existing off-mode tests, then delete.

### What M54a does NOT include

- Demographics model changes (Siler, Gompertz-Makeham) — separate enrichment
- Spatial sort infrastructure — deferred to M54c per roadmap
- Agent-level ecology (per-agent environmental effects) — M55+
- Economy migration — M54b
- Politics migration — M54c
- Performance benchmarking with criterion/iai-callgrind — worth adding but not a gate

---

## State Ownership

The ownership rule: **if Phase 9 Rust mutates it, Rust owns and returns it. If another Python phase owns it, Rust reads it.**

### Rust-owned (returned in region-state batch)

| Field | Type | Notes |
|---|---|---|
| `soil` | `f32` | Core ecology |
| `water` | `f32` | Core ecology |
| `forest_cover` | `f32` | Core ecology |
| `endemic_severity` | `f32` | Disease state |
| `prev_turn_water` | `f32` | Python mirrors back onto Region |
| `soil_pressure_streak` | `i32` | Depletion counter |
| `overextraction_streak_0..2` | `i32` × 3 | Fixed slot columns, not dict |
| `resource_reserve_0..2` | `f32` × 3 | Mineral depletion |
| `resource_effective_yield_0..2` | `f32` × 3 | Persistent degradation track; only changes when degradation/recovery mechanics fire, not from seasonal recomputation |
| `current_turn_yield_0..2` | `f32` × 3 | Ephemeral, return-only; not stored on RegionState; computed into side `Vec<[f32; 3]>` and serialized into return batch |

### Read-only inputs (sent via `set_region_state()`)

| Field | Type | Notes |
|---|---|---|
| `disease_baseline` | `f32` | Set by world_gen |
| `capacity_modifier` | `f32` | Set by climate phase |
| `resource_base_yields` | `[f32; 3]` | Set by world_gen |
| `resource_suspensions` | `[bool; 3]` | Per-slot "is suspended?" — **Python pre-computes** from dict keyed by resource type enum, translating to positional slot booleans before sending to Rust |
| `has_irrigation` | `bool` | Derived from infrastructure |
| `has_mines` | `bool` | Derived from infrastructure |
| `active_focus` | `u8` | Civ tech focus (TechFocus enum) |
| `terrain` | `u8` | Already sent |
| `population` | `u16` | Already sent |
| `carrying_capacity` | `u16` | Already sent |

### Python post-pass fields (not in Rust)

| Field | Notes |
|---|---|
| `famine_cooldown` | Skip/set/decrement in Python famine pass. **Controlled regions only** — uncontrolled regions never have cooldown decremented (matches current Python behavior where decrement runs inside the controlled-region loop). Python post-pass must replicate this. |
| `low_forest_turns` | Terrain succession counter |
| `forest_regrowth_turns` | Terrain succession counter |

---

## FFI Contract

### Call Sequence

```
1. set_region_state(full_batch)          — all per-region fields including new ones
2. tick_ecology(turn, climate_phase,     — mutates Rust region state in-place
     pandemic_mask,                      — per-region disease suppression
     army_arrived_mask)                  — per-region army passage flag
       → (region_batch, event_batch)     — returns ecology state + trigger events
3. Python write-back                     — mirrors returned state onto Region
4. Python post-pass                      — famine, soil floor, terrain counters,
                                            terrain succession (mutates terrain,
                                            carrying_capacity, soil, forest_cover)
5. apply_region_postpass_patch(batch)    — sends population/soil/terrain/ecology
                                            changes from post-pass back to Rust
6. tick(turn, civ_signals)               — agent tick sees post-ecology state
```

### Return type

Tuple of two `PyRecordBatch` values from one Rust entry point:

**Batch 1: Region-state batch** (one row per region)
- `region_id`, `soil`, `water`, `forest_cover`, `endemic_severity`, `prev_turn_water`
- `soil_pressure_streak`
- `overextraction_streak_0`, `overextraction_streak_1`, `overextraction_streak_2`
- `resource_reserve_0`, `resource_reserve_1`, `resource_reserve_2`
- `resource_effective_yield_0`, `resource_effective_yield_1`, `resource_effective_yield_2`
- `current_turn_yield_0`, `current_turn_yield_1`, `current_turn_yield_2`

**Batch 2: Ecology-event batch** (one row per event, variable length)
- `event_type: u8` — 0 = soil_exhaustion, 1 = resource_depletion
- `region_id: u16`
- `slot: u8` — resource slot (255 = N/A for soil_exhaustion)
- `magnitude: f32` — severity/penalty value

Events sorted by `(region_id, event_type, slot)` for deterministic ordering. Rust does not return narrated description/actor strings — Python materializes `Event` objects.

### Patch batch schema (step 5, narrow)

`region_id: u16`, `population: u16`, `soil: f32`, `water: f32`, `forest_cover: f32`, `terrain: u8`, `carrying_capacity: u16`

Does NOT include yield columns — `tick_ecology()` already wrote `current_turn_yields` into `RegionState.resource_yields`, so the agent tick sees post-ecology yields without patch interference.

### Same-turn yield visibility

`tick_ecology()` writes computed `current_turn_yields` into `RegionState.resource_yields` (the existing field on the Rust side). The agent tick reads these directly. `apply_region_postpass_patch()` does not include yield columns, so post-pass changes cannot accidentally overwrite them.

### River topology

Loaded once via `set_river_topology(rivers: list[list[int]])` on `AgentSimulator`. Stored as `RiverTopology` struct. Region paths expressed as `region_id` indices, not names. Not resent per turn.

```rust
pub struct RiverTopology {
    pub rivers: Vec<Vec<u16>>,
}
```

---

## Tuning & Configuration

### `EcologyConfig` struct

Stored once on `AgentSimulator`. Constructed Python-side from tuning YAML overrides. Rust receives already-resolved typed values — no YAML parsing or key lookup on the Rust side. Python remains the source of truth for mapping tuning keys to config fields, including `K_RESOURCE_ABUNDANCE` which comes from the multiplier path rather than the normal override path.

```rust
#[derive(Clone, Debug)]
pub struct EcologyConfig {
    // Soil
    pub soil_degradation: f32,              // K_SOIL_DEGRADATION, default 0.005
    pub soil_recovery: f32,                 // K_SOIL_RECOVERY, default 0.05
    pub mine_soil_degradation: f32,         // K_MINE_SOIL_DEGRADATION, default 0.03
    pub soil_recovery_pop_ratio: f32,       // K_SOIL_RECOVERY_POP_RATIO, default 0.75
    pub agriculture_soil_bonus: f32,        // K_AGRICULTURE_SOIL_BONUS, default 0.02
    pub metallurgy_mine_reduction: f32,     // K_METALLURGY_MINE_REDUCTION, default 0.5
    pub mechanization_mine_mult: f32,       // K_MECHANIZATION_MINE_MULT, default 2.0
    pub soil_pressure_threshold: f32,       // K_SOIL_PRESSURE_THRESHOLD, default 0.7
    pub soil_pressure_streak_limit: i32,    // K_SOIL_PRESSURE_STREAK_LIMIT, default 30
    pub soil_pressure_degradation_mult: f32,// K_SOIL_PRESSURE_DEGRADATION_MULT, default 2.0

    // Water
    pub water_drought: f32,                 // K_WATER_DROUGHT, default 0.04
    pub water_recovery: f32,                // K_WATER_RECOVERY, default 0.03
    pub irrigation_water_bonus: f32,        // K_IRRIGATION_WATER_BONUS, default 0.03
    pub irrigation_drought_mult: f32,       // K_IRRIGATION_DROUGHT_MULT, default 1.5
    pub cooling_water_loss: f32,            // K_COOLING_WATER_LOSS, default 0.02
    pub warming_tundra_water_gain: f32,     // K_WARMING_TUNDRA_WATER_GAIN, default 0.05
    pub water_factor_denominator: f32,      // K_WATER_FACTOR_DENOMINATOR, default 0.5

    // Forest
    pub forest_clearing: f32,               // K_FOREST_CLEARING, default 0.02
    pub forest_regrowth: f32,               // K_FOREST_REGROWTH, default 0.01
    pub cooling_forest_damage: f32,         // K_COOLING_FOREST_DAMAGE, default 0.01
    pub forest_pop_ratio: f32,              // K_FOREST_POP_RATIO, default 0.5
    pub forest_regrowth_water_gate: f32,    // K_FOREST_REGROWTH_WATER_GATE, default 0.3
    pub cross_effect_forest_soil: f32,      // K_CROSS_EFFECT_FOREST_SOIL, default 0.01
    pub cross_effect_forest_threshold: f32, // K_CROSS_EFFECT_FOREST_THRESHOLD, default 0.5

    // Disease
    pub disease_severity_cap: f32,          // K_DISEASE_SEVERITY_CAP, default 0.15
    pub disease_decay_rate: f32,            // K_DISEASE_DECAY_RATE, default 0.25
    pub flare_overcrowding_threshold: f32,  // K_FLARE_OVERCROWDING_THRESHOLD, default 0.8
    pub flare_overcrowding_spike: f32,      // K_FLARE_OVERCROWDING_SPIKE, default 0.04
    pub flare_army_spike: f32,              // K_FLARE_ARMY_SPIKE, default 0.03
    pub flare_water_spike: f32,             // K_FLARE_WATER_SPIKE, default 0.02
    pub flare_season_spike: f32,            // K_FLARE_SEASON_SPIKE, default 0.02

    // Depletion & yields
    pub depletion_rate: f32,                // K_DEPLETION_RATE, default 0.009
    pub exhausted_trickle_fraction: f32,    // K_EXHAUSTED_TRICKLE_FRACTION, default 0.04
    pub reserve_ramp_threshold: f32,        // K_RESERVE_RAMP_THRESHOLD, default 0.25
    pub resource_abundance_multiplier: f32, // K_RESOURCE_ABUNDANCE, default 1.0
    pub overextraction_streak_limit: i32,   // K_OVEREXTRACTION_STREAK_LIMIT, default 35
    pub overextraction_yield_penalty: f32,  // K_OVEREXTRACTION_YIELD_PENALTY, default 0.10
    pub workers_per_yield_unit: i32,        // K_WORKERS_PER_YIELD_UNIT, default 200

    // River cascade
    pub deforestation_threshold: f32,       // K_DEFORESTATION_THRESHOLD, default 0.2
    pub deforestation_water_loss: f32,      // K_DEFORESTATION_WATER_LOSS, default 0.05
}

impl Default for EcologyConfig {
    fn default() -> Self {
        Self {
            soil_degradation: 0.005,
            soil_recovery: 0.05,
            mine_soil_degradation: 0.03,
            soil_recovery_pop_ratio: 0.75,
            agriculture_soil_bonus: 0.02,
            metallurgy_mine_reduction: 0.5,
            mechanization_mine_mult: 2.0,
            soil_pressure_threshold: 0.7,
            soil_pressure_streak_limit: 30,
            soil_pressure_degradation_mult: 2.0,
            water_drought: 0.04,
            water_recovery: 0.03,
            irrigation_water_bonus: 0.03,
            irrigation_drought_mult: 1.5,
            cooling_water_loss: 0.02,
            warming_tundra_water_gain: 0.05,
            water_factor_denominator: 0.5,
            forest_clearing: 0.02,
            forest_regrowth: 0.01,
            cooling_forest_damage: 0.01,
            forest_pop_ratio: 0.5,
            forest_regrowth_water_gate: 0.3,
            cross_effect_forest_soil: 0.01,
            cross_effect_forest_threshold: 0.5,
            disease_severity_cap: 0.15,
            disease_decay_rate: 0.25,
            flare_overcrowding_threshold: 0.8,
            flare_overcrowding_spike: 0.04,
            flare_army_spike: 0.03,
            flare_water_spike: 0.02,
            flare_season_spike: 0.02,
            depletion_rate: 0.009,
            exhausted_trickle_fraction: 0.04,
            reserve_ramp_threshold: 0.25,
            resource_abundance_multiplier: 1.0,
            overextraction_streak_limit: 35,
            overextraction_yield_penalty: 0.10,
            workers_per_yield_unit: 200,
            deforestation_threshold: 0.2,
            deforestation_water_loss: 0.05,
        }
    }
}
```

### Lifecycle

- `set_ecology_config(config)` called once after simulator creation
- Optional `set_ecology_config()` for mid-run updates (unused in normal flow)
- `tick_ecology()` reads config from stored reference

### Per-turn dynamic inputs (method arguments)

- `turn: u32`
- `climate_phase: u8` (enum-mapped)
- `pandemic_mask: Vec<bool>` (one per region, length-validated against internal region array at FFI boundary)
- `army_arrived_mask: Vec<bool>` (one per region — Python pre-computes from `world.agent_events_raw` by checking previous-turn migration events with `occupation == soldier` targeting each region; required for disease army-passage flare trigger)

### Terrain ecology tables

Caps, defaults, and floors compiled into Rust as module constants, mirroring `TERRAIN_ECOLOGY_DEFAULTS`, `TERRAIN_ECOLOGY_CAPS`, and floor values from `ecology.py`. Not configurable via tuning.

### Season/climate modifier tables

`SEASON_MOD` and `CLIMATE_CLASS_MOD` from `resources.py` compiled into Rust as module constants or static functions. Not runtime state.

---

## Rust Internal Architecture

### New file: `chronicler-agents/src/ecology.rs`

All ecology computation lives here. Pure Rust with rayon — no PyO3. FFI entry point in `ffi.rs` delegates to this module.

### Core function

```rust
pub fn tick_ecology(
    regions: &mut [RegionState],
    config: &EcologyConfig,
    turn: u32,
    climate_phase: u8,
    pandemic_mask: &[bool],
    army_arrived_mask: &[bool],
    river_topology: &RiverTopology,
) -> (Vec<[f32; 3]>, Vec<EcologyEvent>)
//    ^ current_turn_yields   ^ ecology events
```

Returns `current_turn_yields` as a side vector (not stored on `RegionState`) and ecology events. The function also mutates `RegionState` fields in-place for Rust-owned state.

After `tick_ecology()` returns, the FFI wrapper writes `current_turn_yields` into `RegionState.resource_yields` so the agent tick sees post-ecology yields.

### Controlled vs. uncontrolled region handling

Regions with `controller_civ == 255` (uncontrolled) get a **different** tick than controlled regions, matching the current Python behavior in `ecology.py` lines 506-566 vs 532-566:

- **Uncontrolled regions:** No mine degradation, no tech focus bonuses (`active_focus` ignored), no infrastructure checks (`has_irrigation`/`has_mines` ignored). Only natural soil recovery (pressure-gated, no civ bonuses), climate-driven water effects, natural forest regrowth (water-gated), and cooling forest damage. Disease severity still ticks.
- **Controlled regions:** Full tick with all modifiers.

The Rust tick branches on `controller_civ == 255` to replicate this divergence. All read-only input fields (`active_focus`, `has_irrigation`, `has_mines`) are sent as their default/false values for uncontrolled regions by Python, but Rust must also guard against using them.

### Execution order

1. **Disease severity** — per-region (both controlled and uncontrolled), reads own state + `pandemic_mask` + `army_arrived_mask`. No cross-region dependency.
2. **Depletion feedback / streak updates** — per-region (controlled only). Mutates persistent counters, emits `EcologyEvent` triggers.
3. **Soil/water/forest tick** — per-region. Controlled: full tick with infrastructure/focus modifiers. Uncontrolled: natural recovery/climate effects only.
4. **Cross-effects** — per-region (both). Forest → soil bonus.
5. **Clamp** — per-region (both). Terrain caps/floors. Applies `round(x, 4)` quantization matching Python's `_clamp_ecology()` behavior (intentional, not cosmetic).
6. **River cascade** — sequential two-pass:
   - Pass 1: gather `(upstream_id, downstream_id, applies)` from topology, reading upstream `forest_cover` against `deforestation_threshold`.
   - Pass 2: apply water deltas to downstream regions in deterministic `region_id` order.
   - Pass 3: second clamp for cascade-affected regions only.
7. **Resource yield computation** — per-region. Computes `current_turn_yields` into side vector. Updates `resource_reserves` (mineral depletion). Carries forward `resource_effective_yields`, only modifying when degradation/recovery mechanics fire. Reads `season_id` from existing `RegionState.season_id` field (already sent in region batch).
8. **Finalize** — per-region (both). Set `prev_turn_water` = current `water`.

### Rust helper functions

- `effective_capacity(region: &RegionState, config: &EcologyConfig) -> u16` — replaces Python's `effective_capacity()`. Used in soil recovery gating, forest clearing thresholds, depletion computation, and pressure multiplier.
- `pressure_multiplier(region: &RegionState, config: &EcologyConfig) -> f32` — replaces Python's `_pressure_multiplier()`. Uses `effective_capacity`.

### Parallelism model

Steps 1-5, 7-8 are embarrassingly parallel — use `par_iter_mut` over `&mut [RegionState]`. Step 6 is sequential by design (cross-region writes).

Implementation starts with plain iterators. Switch to rayon once parity tests are green. Determinism is mandatory regardless.

### `EcologyEvent` struct

```rust
#[derive(Clone, Debug, PartialEq)]
pub struct EcologyEvent {
    pub event_type: u8,    // 0 = soil_exhaustion, 1 = resource_depletion
    pub region_id: u16,
    pub slot: u8,          // resource slot (255 = N/A for soil_exhaustion)
    pub magnitude: f32,    // severity/penalty value
}
```

Events sorted by `(region_id, event_type, slot)` before return for deterministic ordering.

### `TechFocus` encoding

```rust
#[repr(u8)]
pub enum TechFocus {
    None = 0, Agriculture = 1, Metallurgy = 2, Mechanization = 3,
    // Other focuses mapped but unused by ecology
}
```

Python-side mapper is single source of truth. Rust enum has explicit round-trip test.

---

## Testing Strategy

Three layers, each proving a different guarantee.

### Layer 1: Rust determinism tests (`chronicler-agents/tests/test_ecology.rs`)

- Run `tick_ecology()` with identical inputs at 1, 4, 8, 16 threads (via `rayon::ThreadPoolBuilder`)
- **Exact comparison** for cross-thread determinism (no epsilon)
- Compare region-state fields field-for-field
- Compare `EcologyEvent` vectors row-for-row, in order
- Compare `current_turn_yields` element-for-element

**Scenario fixtures:**
- Basic: plains region, no rivers, no infrastructure
- River cascade: 3-region river, upstream deforestation triggers downstream water loss
- Disease flare: overcrowding + army passage + water quality triggers
- Mineral depletion: reserves approaching exhaustion
- Soil pressure streak: at and beyond streak limit
- Overextraction: at and beyond streak limit with yield penalty
- Pandemic suppression: flare triggers present but suppressed
- Mixed terrain: verify caps/floors per terrain type

### Layer 2: Python round-trip integration tests (`tests/test_ecology_bridge.py`)

Full call sequence: `set_region_state()` → `tick_ecology()` → write-back → post-pass → `apply_region_postpass_patch()` → agent `tick()`

**Verifies:**
- Schema matches: all columns present, correct types, correct row counts
- Write-back completeness: every Rust-returned field reflected on Python `Region`
- Patch correctness: post-pass changes visible in Rust after patch
- No field dropped: round-trip through 3 turns, all persistent fields survive
- Event materialization: Rust triggers → Python `Event` objects
- Most assertions before agent tick; one smoke assertion that patched state is visible to agent tick

Narrow: ~5-10 turns, not full runs.

### Layer 3: Temporary Python parity suite (`tests/test_ecology_parity.py`)

Runs old Python `tick_ecology()` and new Rust path on identical world state. Migration safety net.

**Comparison rules:**
- **Exact equality:** integer/bool/state-machine fields (`soil_pressure_streak`, `overextraction_streaks`, event triggers)
- **Field-specific tight epsilon:** clamped ecology fields (`soil`, `water`, `forest_cover`) — f32 vs f64 rounding
- **Slightly looser epsilon over 50 turns:** reserves, yields — accumulation drift tolerance
- **Exact equality:** post-pass-visible state (population, terrain) after Python finishes famine/succession

**Scenario fixtures:**
- No rivers, no famine (baseline)
- River cascade world (3+ rivers, upstream deforestation active)
- Mineral depletion world (reserves near zero)
- Soil-exhaustion streak world (streak at/near limit)
- Pandemic suppression world
- Soil-floor tradition world
- Famine/refugee world through Python post-pass

**Duration:** 1-turn focused tests per scenario + one 50-turn multi-turn parity test for persistence drift.

**Lifecycle:** Temporary — removed after M54a is validated and Python ecology code is deleted. A few representative golden scenario regression tests are kept permanently.

### Determinism gate (merge requirement)

- All Layer 1 tests pass at 1/4/8/16 threads
- All Layer 2 tests pass
- All Layer 3 parity tests pass within defined tolerance budget
- 200-seed regression at 200 turns (milestone completion / pre-main merge gate): no distribution shift in satisfaction, rebellion rate, population, Gini vs. pre-M54a baseline

---

## Migration Strategy

### Implementation order

1. Extend `RegionState` — add missing fields
2. Extend `set_region_state()` — accept and parse new columns
3. `EcologyConfig` struct — with `Default` impl, PyO3 constructor, stored on `AgentSimulator`
4. `RiverTopology` — struct + `set_river_topology()` method
5. `ecology.rs` core — soil/water/forest tick, disease, cross-effects, clamp (plain iterators)
6. Depletion feedback — streak updates, event emission
7. River cascade — two-pass sequential
8. Yield computation — `current_turn_yields` + reserve depletion
9. FFI entry point — `tick_ecology()` on `AgentSimulator`, returns tuple of two batches
10. `apply_region_postpass_patch()` — new FFI method for narrow post-pass sync
11. Python orchestration — rewrite `tick_ecology()` as thin wrapper
12. Layer 1 tests — Rust determinism
13. Layer 2 tests — Python round-trip integration
14. Layer 3 tests — temporary parity suite
15. Switch to rayon — once parity is green
16. Re-run determinism tests — verify rayon doesn't break
17. 200-seed regression — merge gate
18. Cleanup — delete dead Python ecology functions, remove `_last_region_yields`, keep golden scenario tests

### Risk table

| Risk | Mitigation |
|---|---|
| Float parity drift (f64 Python vs f32 Rust) | Field-specific tolerances; clamping reduces accumulation; parity suite catches drift early |
| `set_region_state()` schema change breaks existing agent tick | Schema is additive (new columns); existing columns unchanged; existing tests catch regressions |
| River cascade non-determinism under rayon | Cascade is sequential by design; determinism tests specifically cover river scenarios |
| `active_focus` encoding mismatch | Python-side mapper is single source of truth; Rust `TechFocus` enum has explicit round-trip test |
| Overextraction dict → fixed slots loses data | Current Python dict keys are always 0, 1, or 2 (resource slot indices); no semantic loss |
| Famine post-pass reads stale yield data | `current_turn_yields` returned from Rust before famine runs; write-back order enforced |
| `apply_soil_floor()` clobbers Rust-computed soil | Soil floor runs after write-back; patch sends corrected value back to Rust |
| Two `set_region_state()` calls per turn | No — first call + in-place mutation + narrow patch. No double full-send |
| Full batch and patch schemas drift apart | One shared Python/Rust schema helper per batch family |

### Pre-M54a cleanup (recommended, not gating)

Wave 2 from `docs/superpowers/plans/2026-03-21-post-m51-refactor-waves.md`:
- `codex/refactor-world-indexes`
- `codex/refactor-turn-artifacts`
- `codex/refactor-ffi-contracts`
- `codex/refactor-run-orchestration`

These reduce migration pain but are not hard blockers. M54a can proceed without them if the FFI surface is manageable. However, `RegionState` will grow to ~45+ fields after M54a additions — the `codex/refactor-ffi-contracts` work would genuinely reduce this pain.

### Feasibility notes

**Parity suite epsilon management** will require 2-3 tuning iterations. The f64 (Python) to f32 (Rust) drift interacts with nonlinear functions like `_pressure_multiplier` (which divides population by effective capacity involving soil, water, and carrying_capacity), creating cascading rounding differences. After 50 turns, drift may be oscillatory rather than monotonic (a value clamped in f32 but not in f64 triggers different recovery paths on subsequent turns). The parity tests will likely need per-field per-scenario tolerance values, not blanket epsilons. Budget time for this.

---

## Phoebe Review Log

**Review 1 (2026-03-21):** 3 blocking issues, 5 observations, 1 feasibility concern. All resolved in-spec:

- **[FIXED] B1:** `resource_suspensions` type mismatch — spec now explicitly states Python pre-computes per-slot booleans from dict keyed by resource type enum.
- **[FIXED] B2:** Army passage disease trigger — added `army_arrived_mask: Vec<bool>` as per-turn dynamic input, Python pre-computes from `world.agent_events_raw`.
- **[FIXED] B3:** Uncontrolled region divergent behavior — added "Controlled vs. uncontrolled region handling" section with explicit branching rules.
- **[NOTED] O1:** `effective_capacity` and `pressure_multiplier` listed as Rust helper functions.
- **[NOTED] O2:** `round(x, 4)` quantization in clamp step documented as intentional.
- **[NOTED] O3:** `famine_cooldown` controlled-only decrement documented on the field.
- **[NOTED] O4:** `season_id` reads from existing `RegionState.season_id` field.
- **[NOTED] O5:** RegionState growth to ~45+ fields acknowledged; Wave 2 refactors recommended.
- **[NOTED] F1:** Parity suite epsilon management feasibility documented with budget guidance.

**User review (2026-03-21):** 2 P1 issues, 1 P2. All resolved in-spec:

- **[FIXED] P1:** Terrain succession omitted from post-pass — `tick_terrain_succession()` mutates `terrain`, `carrying_capacity`, `soil`, `forest_cover` after ecology. Added to post-pass sequence, "What stays in Python" section, and call sequence. Patch batch already includes these fields.
- **[FIXED] P1:** `--agents=off` mode not addressed — spec was AgentSimulator-centric but off-mode doesn't instantiate it. Added explicit `--agents=off` mode section with lightweight simulator approach. Deletion of Python ecology gated on off-mode being wired.
- **[FIXED] P2:** Status header misstated readiness — updated to "design-ahead while M53 gate remains blocked" with explicit note about failed validation gate.
