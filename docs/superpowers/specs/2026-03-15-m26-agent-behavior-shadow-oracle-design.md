# M26: Agent Behavior + Shadow Oracle — Design Spec

**Date:** 2026-03-15
**Status:** Draft
**Prerequisites:** M25 Rust Core + Arrow Bridge (complete)
**Estimated size:** ~1,400 lines Rust, ~300 lines Python
**Phase:** 5 (Agent-Based Population Model) — second milestone

## Overview

Add agent decision-making (satisfaction, rebellion, migration, occupation switching, loyalty drift), satisfaction-gated fertility, and the updated ecological stress formula. Run agents in **shadow mode** alongside the aggregate Python model — agent outputs are discarded but compared against aggregate stats via an oracle framework. Shadow logs use Arrow IPC (improvement note #8).

M26 does not wire agent aggregates into the Python turn loop (M27), does not run the full oracle gate validation (M28), and does not optimize for scale (M29).

### Design Principles

1. **Shadow mode isolates behavior bugs from integration bugs.** Agent tick runs, produces aggregates, but the aggregate model still drives all civ stats. If agent-derived distributions diverge, it's a behavior-model problem — not an integration wiring problem.
2. **Satisfaction before fertility.** M25 deferred fertility because satisfaction was static. Now satisfaction is real, fertility has feedback to key off of.
3. **Branchless satisfaction for auto-vectorization.** Replace `max(0, x)` with `x * (x > 0.0) as i32 as f32` patterns. Compute all bonuses/penalties unconditionally and zero irrelevant ones with masks. This lets LLVM auto-vectorize without explicit SIMD intrinsics.
4. **Arrow IPC shadow logs.** 50 seeds x 500 turns x ~10 civs = ~60MB. Arrow IPC compresses ~4:1 and loads directly into polars for analysis. No JSON serialization per turn.
5. **Events RecordBatch populated.** M25 defined the schema with zero rows. M26 fills it with rebellion, migration, death, birth, occupation_switch, and loyalty_flip events.

### Design Decisions

**civ_affinity stays u8 internal, u16 Arrow schema.** 24 regions produce at most ~24 civs (one per region at genesis, reduced by conquest). u8 (max 255) is sufficient. A compile-time assert `const _: () = assert!(MAX_CIVS <= 255)` guards this. The Arrow schema uses UInt16 for forward-compatibility — if a future phase needs >255 civs, only pool.rs storage changes; the FFI boundary is already u16. No M26 code change needed from M25's approach.

**Ecological stress formula replaces M25's.** M25: `1.0 + 2.0 * (1.0 - (soil + water) / 2.0)` (range 1.0–3.0). M26: `1.0 + max(0, 0.5 - soil) + max(0, 0.5 - water)` (range 1.0–2.0). The per-variable formula is more nuanced — a region with good soil but bad water has moderate stress, not averaged-away stress. The range change (3.0 → 2.0 max) reduces peak mortality; fertility compensates. Shadow oracle baseline uses the new formula from turn 1.

---

## Crate Structure Changes

M25's `chronicler-agents/src/` gains four new files. `tick.rs` and `pool.rs` are modified.

```
chronicler-agents/src/
├── lib.rs              # unchanged
├── agent.rs            # add fertility constants, MAX_CIVS assert
├── pool.rs             # add satisfaction/loyalty/occupation setters, skill update
├── ffi.rs              # add signals RecordBatch input, populate events output
├── tick.rs             # orchestrate: satisfaction → decisions → demographics
├── region.rs           # add adjacency_mask field to RegionState
├── satisfaction.rs     # NEW: branchless satisfaction formula
├── behavior.rs         # NEW: decision model (rebel → migrate → switch → drift)
├── demographics.rs     # NEW: mortality (updated formula) + fertility
└── signals.rs          # NEW: parse Python signals into Rust-side structs
```

Python side:
```
src/chronicler/
├── agent_bridge.py     # add build_signals(), shadow mode, mode="shadow"
├── shadow.py           # NEW: shadow mode wiring, Arrow IPC log writer
└── shadow_oracle.py    # NEW: KS/AD comparison framework, report generation
```

---

## Data Structures

### `agent.rs` — New Constants

```rust
pub const MAX_CIVS: usize = 255;
const _: () = assert!(MAX_CIVS <= u8::MAX as usize);

// Fertility
pub const FERTILITY_AGE_MIN: u16 = 16;
pub const FERTILITY_AGE_MAX: u16 = 45;
pub const FERTILITY_BASE_FARMER: f32 = 0.03;
pub const FERTILITY_BASE_OTHER: f32 = 0.015;
pub const FERTILITY_SATISFACTION_THRESHOLD: f32 = 0.4;

// Decision thresholds
pub const REBEL_LOYALTY_THRESHOLD: f32 = 0.2;
pub const REBEL_SATISFACTION_THRESHOLD: f32 = 0.2;
pub const REBEL_MIN_COHORT: usize = 5;
pub const MIGRATE_SATISFACTION_THRESHOLD: f32 = 0.3;
pub const OCCUPATION_SWITCH_UNDERSUPPLY: f32 = 1.5;
pub const OCCUPATION_SWITCH_OVERSUPPLY: f32 = 0.5;
pub const LOYALTY_DRIFT_RATE: f32 = 0.02;
pub const LOYALTY_FLIP_THRESHOLD: f32 = 0.3;

// Skill
pub const SKILL_RESET_ON_SWITCH: f32 = 0.3;
pub const SKILL_GROWTH_PER_TURN: f32 = 0.05;
pub const SKILL_MAX: f32 = 1.0;

// War
pub const WAR_CASUALTY_MULTIPLIER: f32 = 2.0;
```

### `region.rs` — Adjacency

```rust
pub struct RegionState {
    pub region_id: u16,
    pub terrain: u8,
    pub carrying_capacity: u16,
    pub population: u16,
    pub soil: f32,
    pub water: f32,
    pub forest_cover: f32,
    // M26 additions
    pub adjacency_mask: u32,     // bitmask: bit i = 1 means adjacent to region i (supports ≤32 regions)
    pub controller_civ: u8,      // civ_id that controls this region (255 = uncontrolled)
    pub trade_route_count: u8,   // active trade routes in this region
}
```

Adjacency as a bitmask rather than `Vec<u16>` — 24 regions fit in a u32, avoids heap allocation per region, and adjacency checks are a single bitwise AND. `adjacency_mask` is built once during `set_region_state` from the Python-side adjacency lists.

### `signals.rs` — Per-Tick Signals from Python

Signals are world-state context that the Rust tick reads but doesn't modify. Passed as Arrow RecordBatches each tick.

```rust
/// Per-civ signals from Python.
pub struct CivSignals {
    pub civ_id: u8,
    pub stability: u8,          // 0–100
    pub is_at_war: bool,
    pub dominant_faction: u8,   // 0=military, 1=merchant, 2=cultural
    pub faction_military: f32,  // influence 0.0–1.0
    pub faction_merchant: f32,
    pub faction_cultural: f32,
}

/// Per-region signals extending RegionState.
/// (RegionState already carries ecology; these add control/war context.)
pub struct RegionSignals {
    pub region_id: u16,
    pub is_contested: bool,     // true if region is contested in an active war
}

/// Parsed from two Arrow RecordBatches: civ_signals and region_signals.
pub struct TickSignals {
    pub civs: Vec<CivSignals>,
    pub contested_regions: Vec<bool>,  // indexed by region_id
}
```

### Arrow Schemas — New Signal Inputs

**Civ signals schema** (`set_civ_signals` input):

| Column | Arrow Type | Notes |
|--------|-----------|-------|
| `civ_id` | `UInt8` | |
| `stability` | `UInt8` | 0–100 |
| `is_at_war` | `Boolean` | any active war involving this civ |
| `dominant_faction` | `UInt8` | 0=military, 1=merchant, 2=cultural |
| `faction_military` | `Float32` | influence 0.0–1.0 |
| `faction_merchant` | `Float32` | influence 0.0–1.0 |
| `faction_cultural` | `Float32` | influence 0.0–1.0 |

**Region state schema** (extends M25 — add columns):

| Column | Arrow Type | Notes |
|--------|-----------|-------|
| `region_id` | `UInt16` | existing |
| `terrain` | `UInt8` | existing |
| `carrying_capacity` | `UInt16` | existing |
| `population` | `UInt16` | existing |
| `soil` | `Float32` | existing |
| `water` | `Float32` | existing |
| `forest_cover` | `Float32` | existing |
| `controller_civ` | `UInt8` | **new** — 255 = uncontrolled |
| `adjacency_mask` | `UInt32` | **new** — bitmask of adjacent region indices |
| `trade_route_count` | `UInt8` | **new** |
| `is_contested` | `Boolean` | **new** — true if region in active war |

---

## Satisfaction Formula

**File:** `satisfaction.rs`

```rust
/// Compute satisfaction for a single agent. All inputs pre-fetched.
/// Branchless: no if/else — multiply by bool-as-f32 masks.
pub fn compute_satisfaction(
    occupation: u8,
    soil: f32,
    water: f32,
    civ_stability: u8,
    demand_supply_ratio: f32,   // (demand - supply) / max(supply, 1)
    pop_over_capacity: f32,     // population / carrying_capacity
    civ_at_war: bool,
    region_contested: bool,
    occ_matches_faction: bool,
    is_displaced: bool,          // displacement_turn > 0 AND region != origin_region
    trade_routes: u8,
    faction_influence: f32,      // influence of the faction matching this occupation
) -> f32 {
    // Base satisfaction by occupation
    let base = match occupation {
        0 => 0.4 + soil * 0.3 + water * 0.2,                      // Farmer
        1 => 0.5 + faction_influence * 0.3,                        // Soldier
        2 => 0.4 + (trade_routes as f32 / 3.0).min(1.0) * 0.3,   // Merchant
        3 => 0.5 + faction_influence * 0.2,                        // Scholar
        _ => 0.6 - (1.0 - civ_stability as f32 / 100.0) * 0.2,   // Priest
    };

    let stability_bonus = civ_stability as f32 / 200.0;

    let ds_raw = demand_supply_ratio * 0.2;
    let ds_bonus = ds_raw.clamp(-0.2, 0.2);

    let overcrowding_raw = (pop_over_capacity - 1.0) * 0.3;
    let overcrowding = overcrowding_raw * (overcrowding_raw > 0.0) as i32 as f32;

    let war_pen = 0.15 * civ_at_war as i32 as f32
                + 0.10 * region_contested as i32 as f32;

    let faction_bonus = 0.05 * occ_matches_faction as i32 as f32;

    let displacement_pen = 0.10 * is_displaced as i32 as f32;

    (base + stability_bonus + ds_bonus - overcrowding - war_pen + faction_bonus - displacement_pen)
        .clamp(0.0, 1.0)
}
```

### Occupation–Faction Alignment

| Occupation | Aligns with Faction |
|-----------|-------------------|
| Farmer | — (no faction alignment bonus) |
| Soldier | Military (0) |
| Merchant | Merchant (1) |
| Scholar | Cultural (2) |
| Priest | — (no faction alignment bonus) |

### Demand/Supply Computation

Per-region, per-occupation: count agents of that occupation vs. a target ratio derived from terrain + ecology.

```rust
fn target_occupation_ratio(terrain: u8, soil: f32, water: f32) -> [f32; 5] {
    // Base ratios (sum to 1.0): farmer 0.60, soldier 0.15, merchant 0.10, scholar 0.10, priest 0.05
    let mut ratios = [0.60, 0.15, 0.10, 0.10, 0.05];

    // Terrain adjustments
    match terrain {
        1 => { ratios[1] += 0.05; ratios[0] -= 0.05; }  // Mountains: more soldiers
        2 => { ratios[2] += 0.05; ratios[0] -= 0.05; }  // Coast: more merchants
        3 => { ratios[0] += 0.05; ratios[2] -= 0.05; }  // Forest: more farmers
        4 => { ratios[1] += 0.05; ratios[0] -= 0.10; ratios[4] += 0.05; } // Desert: fewer farmers
        _ => {}
    }

    // Ecology pressure: bad soil shifts demand away from farmers
    if soil < 0.3 {
        ratios[0] -= 0.10;
        ratios[1] += 0.05;
        ratios[4] += 0.05;
    }

    ratios
}
```

---

## Decision Model

**File:** `behavior.rs`

Each tick, after satisfaction update, every alive agent evaluates decisions in priority order. First triggered decision executes; rest skipped.

### 1. Rebel

```
IF loyalty < 0.2 AND satisfaction < 0.2
AND count(same-region agents with loyalty < 0.2 AND satisfaction < 0.2) >= 5:
    emit rebellion event
    // Agent stays in place — rebellion is a signal, not immediate removal
```

Implementation: pre-compute a per-region rebel-eligible count before the agent loop. Agents check the count, not each other individually (O(n) per region, not O(n^2)).

### 2. Migrate

```
IF satisfaction < 0.3
AND any adjacent region (same or different civ) exists:
    pick adjacent region with highest expected satisfaction (from previous turn's data)
    IF expected_satisfaction > current_satisfaction + 0.05:
        move agent: regions[slot] = target_region
        displacement_turns[slot] = 1 (if civ changed) or 0 (same civ)
        emit migration event
```

Expected satisfaction for the target region: use mean satisfaction of agents in that region **from the current tick's satisfaction update** (step 1 of tick orchestration). No circular dependency — satisfaction is computed for all agents *before* any migration decisions run (step 3). `compute_region_stats` (step 2) reads the already-updated satisfaction values and caches per-region means. Migration decisions then compare the agent's own current satisfaction against target region means from `region_stats`. This is a snapshot of current-tick state, not previous-turn data.

### 3. Switch Occupation

```
IF current occupation's supply > demand × 2.0 (oversupplied)
AND alternative occupation's demand > supply × 1.5 (undersupplied):
    switch to undersupplied occupation
    skills[slot * 5 + new_occ] = max(skills[slot * 5 + new_occ], 0.3)
    emit occupation_switch event
```

Supply = count of agents with that occupation in region.
Demand = target_occupation_ratio[occ] × region_population.

### 4. Loyalty Drift

```
IF region borders another civ (adjacency_mask & regions_of_other_civ != 0):
    IF mean satisfaction of other-civ agents in this region > mean satisfaction of own-civ agents:
        loyalty -= 0.02
    ELSE:
        loyalty += 0.01  // recovery is slower than drift
    IF loyalty < 0.3:
        civ_affinity = dominant civ in this region (by agent count)
        loyalty = 0.5  // reset after flip
        emit loyalty_flip event
```

---

## Demographics

**File:** `demographics.rs`

Runs after decisions within the same tick.

### Mortality (Updated Formula)

```rust
fn ecological_stress(region: &RegionState) -> f32 {
    let soil_stress = (0.5 - region.soil) * ((0.5 - region.soil) > 0.0) as i32 as f32;
    let water_stress = (0.5 - region.water) * ((0.5 - region.water) > 0.0) as i32 as f32;
    1.0 + soil_stress + water_stress
    // Range: 1.0 (healthy) to 2.0 (both soil and water below 0.5)
}

/// War casualty multiplier applies to all soldier age brackets — intentional divergence
/// from roadmap draft which restricted to 20–60. Rationale: soldiers of any age on
/// an active front face elevated mortality regardless of bracket. The base rate still
/// differentiates (young 0.5%, adult 1%, elder 5%); the 2× multiplier is uniform.
fn mortality_rate(age: u16, eco_stress: f32, is_soldier_at_war: bool) -> f32 {
    let base = match age {
        0..AGE_ADULT => MORTALITY_YOUNG,
        AGE_ADULT..AGE_ELDER => MORTALITY_ADULT,
        _ => MORTALITY_ELDER,
    };
    let war_mult = 1.0 + (WAR_CASUALTY_MULTIPLIER - 1.0) * is_soldier_at_war as i32 as f32;
    base * eco_stress * war_mult
}
```

### Fertility

```rust
fn fertility_rate(
    age: u16,
    satisfaction: f32,
    occupation: u8,
    soil: f32,
) -> f32 {
    let eligible = (age >= FERTILITY_AGE_MIN
        && age <= FERTILITY_AGE_MAX
        && satisfaction > FERTILITY_SATISFACTION_THRESHOLD) as i32 as f32;
    let base = if occupation == 0 { FERTILITY_BASE_FARMER } else { FERTILITY_BASE_OTHER };
    let ecology_mod = 0.5 + soil * 0.5;  // range 0.5–1.0
    base * ecology_mod * eligible
}
```

Newborn attributes:
- `age = 0`
- `origin_region = parent's region`
- `civ_affinity = parent's civ_affinity`
- `occupation = Farmer` (all newborns start as farmers)
- `skill = 0.1` (all occupation slots)
- `loyalty = parent's loyalty`
- `satisfaction = 0.5` (neutral)

---

## Tick Orchestration

**File:** `tick.rs` (replaces M25 age+die-only tick)

```rust
pub fn tick_agents(
    pool: &mut AgentPool,
    regions: &[RegionState],
    signals: &TickSignals,
    master_seed: [u8; 32],
    turn: u32,
) -> Vec<AgentEvent> {
    // 0. Skill growth (all alive agents: +0.05 to current occupation skill, capped at 1.0)
    grow_skills(pool);

    // 1. Update satisfaction (per-region parallel)
    update_satisfaction(pool, regions, signals);

    // 2. Pre-compute per-region stats for decision model
    let region_stats = compute_region_stats(pool, regions, signals);

    // 3. Decisions (per-region parallel, deterministic via RNG stream splitting)
    let pending = run_decisions(pool, regions, signals, &region_stats, master_seed, turn);

    // 4. Apply decisions sequentially (deterministic order)
    let mut events = apply_decisions(pool, pending);

    // 5. Demographics: mortality + fertility (per-region parallel)
    let demo_pending = run_demographics(pool, regions, signals, master_seed, turn);
    events.extend(apply_demographics(pool, demo_pending));

    events
}
```

**Signature change from M25:** `tick_agents` now takes `&TickSignals` and returns `Vec<AgentEvent>` instead of `()`. The FFI layer converts `Vec<AgentEvent>` to Arrow RecordBatch with the events schema.

### AgentEvent

```rust
pub struct AgentEvent {
    pub agent_id: u32,
    pub event_type: u8,     // 0=death, 1=rebellion, 2=migration, 3=occ_switch, 4=loyalty_flip, 5=birth
    pub region: u16,
    pub target_region: u16, // migration destination, 0 otherwise
    pub civ_affinity: u8,   // agent's civ at time of event (u8 internal, u16 in Arrow)
    pub turn: u32,
}
```

### PendingEvents (Extended from M25)

```rust
struct PendingDecisions {
    rebellions: Vec<(usize, u16)>,          // (slot, region)
    migrations: Vec<(usize, u16, u16)>,     // (slot, from_region, to_region)
    occupation_switches: Vec<(usize, u8)>,  // (slot, new_occupation)
    loyalty_flips: Vec<(usize, u8)>,        // (slot, new_civ_affinity)
}

struct PendingDemographics {
    deaths: Vec<usize>,
    births: Vec<(u16, u8, u8, f32)>,  // (region, civ, occupation, parent_loyalty)
    aged: Vec<usize>,
}
```

---

## FFI Changes

### `ffi.rs` — Updated Tick Signature

```rust
/// Advance simulation by one turn.
/// `signals` is a civ-signals Arrow RecordBatch.
/// Returns an events RecordBatch (populated, not empty).
pub fn tick(&mut self, turn: u32, signals: PyRecordBatch) -> PyResult<PyRecordBatch> {
    if !self.initialized {
        return Err(PyValueError::new_err("tick() called before set_region_state()"));
    }
    self.turn = turn;

    let tick_signals = parse_signals(signals, &self.regions)?;
    let events = crate::tick::tick_agents(
        &mut self.pool, &self.regions, &tick_signals, self.master_seed, turn,
    );

    // Convert Vec<AgentEvent> → Arrow RecordBatch
    Ok(PyRecordBatch::new(events_to_batch(&events)?))
}
```

### `set_region_state` — Extended Schema

Adds `controller_civ`, `adjacency_mask`, `trade_route_count`, `is_contested` columns. Backward-compatible: checks for column existence so M25-format batches still work (columns default to 255/0/0/false).

### `compute_aggregates` — Populated

M26 populates all five aggregate columns:

| Column | Source |
|--------|--------|
| `population` | Count of alive agents per civ |
| `military` | Sum of soldier.skill per civ, normalized 0–100 |
| `economy` | Sum of merchant.skill per civ, normalized 0–100 |
| `culture` | Sum of (scholar.skill + priest.skill × 0.3) per civ, normalized 0–100 |
| `stability` | Mean(satisfaction) × Mean(loyalty) × 100 per civ |

Normalization: raw value / (civ_carrying_capacity × max_skill × occupation_fraction) × 100, clamped to 0–100.

### Worked Normalization Example

A civ controls 2 regions with carrying capacity 40 + 20 = 60. It has 55 alive agents:
- 8 soldiers with skills [0.8, 0.6, 0.5, 0.4, 0.3, 0.2, 0.2, 0.1] → sum = 3.1
- 6 merchants with skills [0.7, 0.5, 0.4, 0.3, 0.2, 0.1] → sum = 2.2
- 5 scholars with skills [0.6, 0.4, 0.3, 0.2, 0.1] → sum = 1.6
- 3 priests with skills [0.5, 0.3, 0.2] → sum = 1.0

**military** = sum(soldier.skill) / (civ_capacity × SKILL_MAX × soldier_fraction) × 100
= 3.1 / (60 × 1.0 × 0.15) × 100 = 3.1 / 9.0 × 100 = **34**

**economy** = sum(merchant.skill) / (60 × 1.0 × 0.10) × 100
= 2.2 / 6.0 × 100 = **37**

**culture** = sum(scholar.skill + priest.skill × 0.3) / (60 × 1.0 × 0.13) × 100
= (1.6 + 1.0 × 0.3) / 7.8 × 100 = 1.9 / 7.8 × 100 = **24**

**stability** = mean(satisfaction) × mean(loyalty) × 100
= 0.55 × 0.65 × 100 = **36**

All values clamped to [0, 100]. A fully staffed civ with max skills and max satisfaction/loyalty scores 100 on all axes — matching Phase 4's scale.

### `build_signals` — Python-Side Signal Construction

```python
FACTION_MAP = {"military": 0, "merchant": 1, "cultural": 2}

def build_signals(world: WorldState) -> pa.RecordBatch:
    """Build civ-signals Arrow RecordBatch from current WorldState."""
    from chronicler.factions import get_dominant_faction

    war_civs = set()
    for attacker, defender in world.active_wars:
        war_civs.add(attacker)
        war_civs.add(defender)

    civ_ids, stabilities, at_wars = [], [], []
    dom_factions, fac_mil, fac_mer, fac_cul = [], [], [], []

    for i, civ in enumerate(world.civilizations):
        civ_ids.append(i)
        stabilities.append(min(civ.stability, 100))
        at_wars.append(civ.name in war_civs)
        dominant = get_dominant_faction(civ.factions)
        dom_factions.append(FACTION_MAP[dominant.value])
        fac_mil.append(civ.factions.influence.get(FactionType.MILITARY, 0.33))
        fac_mer.append(civ.factions.influence.get(FactionType.MERCHANT, 0.33))
        fac_cul.append(civ.factions.influence.get(FactionType.CULTURAL, 0.34))

    return pa.record_batch({
        "civ_id": pa.array(civ_ids, type=pa.uint8()),
        "stability": pa.array(stabilities, type=pa.uint8()),
        "is_at_war": pa.array(at_wars, type=pa.bool_()),
        "dominant_faction": pa.array(dom_factions, type=pa.uint8()),
        "faction_military": pa.array(fac_mil, type=pa.float32()),
        "faction_merchant": pa.array(fac_mer, type=pa.float32()),
        "faction_cultural": pa.array(fac_cul, type=pa.float32()),
    })
```

---

## Shadow Mode — Python Side

### `shadow.py` — Shadow Mode Wiring

```python
import pyarrow as pa
import pyarrow.ipc as ipc
from pathlib import Path

class ShadowLogger:
    """Writes per-turn shadow comparison data as Arrow IPC."""

    def __init__(self, output_path: Path):
        self._path = output_path
        self._writer: ipc.RecordBatchFileWriter | None = None
        self._schema = pa.schema([
            ("turn", pa.uint32()),
            ("civ_id", pa.uint16()),
            # Agent-derived
            ("agent_population", pa.uint32()),
            ("agent_military", pa.uint32()),
            ("agent_economy", pa.uint32()),
            ("agent_culture", pa.uint32()),
            ("agent_stability", pa.uint32()),
            # Aggregate-derived
            ("agg_population", pa.uint32()),
            ("agg_military", pa.uint32()),
            ("agg_economy", pa.uint32()),
            ("agg_culture", pa.uint32()),
            ("agg_stability", pa.uint32()),
        ])

    def log_turn(self, turn: int, agent_aggs: pa.RecordBatch, world) -> None:
        if self._writer is None:
            sink = pa.OSFile(str(self._path), "wb")
            self._writer = ipc.new_file(sink, self._schema)
        batch = self._build_comparison_batch(turn, agent_aggs, world)
        self._writer.write_batch(batch)

    def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
```

### `agent_bridge.py` — Shadow Mode Integration

```python
class AgentBridge:
    def __init__(self, world: WorldState, mode: str = "demographics-only"):
        self._sim = AgentSimulator(num_regions=len(world.regions), seed=world.seed)
        self._mode = mode
        self._shadow_logger: ShadowLogger | None = None

    def tick(self, world: WorldState) -> list[Event]:
        self._sim.set_region_state(build_region_batch(world))
        signals = build_signals(world)
        agent_events = self._sim.tick(world.turn, signals)

        if self._mode == "shadow":
            agent_aggs = self._sim.get_aggregates()
            if self._shadow_logger:
                self._shadow_logger.log_turn(world.turn, agent_aggs, world)
            return []  # discard — aggregate model drives
        elif self._mode == "demographics-only":
            self._apply_demographics_clamp(world)
            return []
```

### `shadow_oracle.py` — Comparison Framework

```python
from scipy.stats import ks_2samp, anderson_ksamp
import numpy as np
import pyarrow.ipc as ipc

def shadow_oracle_report(shadow_ipc_paths: list[Path]) -> OracleReport:
    """Compare agent-derived and aggregate stat distributions at checkpoints."""
    checkpoints = [100, 250, 500]
    metrics = ["population", "military", "economy", "culture", "stability"]
    bonferroni_alpha = 0.05 / (len(metrics) * len(checkpoints))  # 0.003

    # Load all shadow logs from Arrow IPC
    all_data = load_shadow_data(shadow_ipc_paths)

    results = []
    for metric in metrics:
        for turn in checkpoints:
            agent_vals = extract_at_turn(all_data, f"agent_{metric}", turn)
            agg_vals = extract_at_turn(all_data, f"agg_{metric}", turn)
            ks_stat, ks_p = ks_2samp(agent_vals, agg_vals)
            ad_stat, _, ad_p = anderson_ksamp([agent_vals, agg_vals])
            results.append(OracleResult(metric, turn, ks_stat, ks_p, ad_p, bonferroni_alpha))

    # Correlation structure validation
    correlation_checks = [("military", "economy"), ("culture", "stability")]
    for m1, m2 in correlation_checks:
        for turn in checkpoints:
            agent_m1 = extract_at_turn(all_data, f"agent_{m1}", turn)
            agent_m2 = extract_at_turn(all_data, f"agent_{m2}", turn)
            agg_m1 = extract_at_turn(all_data, f"agg_{m1}", turn)
            agg_m2 = extract_at_turn(all_data, f"agg_{m2}", turn)
            corr_delta = abs(
                np.corrcoef(agent_m1, agent_m2)[0, 1]
                - np.corrcoef(agg_m1, agg_m2)[0, 1]
            )
            results.append(CorrelationResult(m1, m2, turn, corr_delta))

    return OracleReport(results)
```

**Exit criteria:** 15 KS+AD comparisons (5 metrics × 3 checkpoints), Bonferroni-corrected α = 0.003. Pass if >= 12/15 pass both tests AND all correlation deltas < 0.15.

---

## Testing Strategy

### Rust Tests

1. **Satisfaction unit tests** (`satisfaction.rs`) — known inputs → expected satisfaction values for each occupation type. Edge cases: max overcrowding, war + contested, displaced merchant.

2. **Decision model tests** (`behavior.rs`) — pre-loaded pool with specific satisfaction/loyalty values → verify correct decisions fire in priority order. Test short-circuiting: agent that would both rebel and migrate only rebels.

3. **Demographics tests** (`demographics.rs`) — ecological stress formula: soil=0.3, water=0.2 → stress = 1.0 + 0.2 + 0.3 = 1.5. Fertility: satisfaction=0.5, age=25, farmer → birth probability > 0. Satisfaction=0.3 → no birth.

4. **Tick integration test** — 100 agents across 3 regions, 10 turns with fixed signals. Determinism: two identical runs produce identical pool state.

5. **Events population test** — tick with agents that meet rebellion/migration thresholds → events RecordBatch has rows with correct event_type values.

6. **Aggregates population test** — pool with known occupation/skill distribution → military/economy/culture/stability values match hand-computed expectations.

### Python Tests

7. **Shadow logger test** — write 5 turns of shadow data to Arrow IPC, read back, verify schema and row count.

8. **Signal building test** — `build_signals(world)` with known WorldState → verify Arrow schema and values (war state, faction dominance, etc.).

9. **Shadow mode integration test** — 20-turn shadow run with real WorldState. Verify: shadow log written, aggregate model still drives civ stats (agent aggs discarded), no crashes.

10. **Oracle framework test** — synthetic shadow data with known distributions → verify KS test pass/fail determination and Bonferroni correction.

### Benchmark

- 6,000 agents with full decision model + demographics < 3ms/tick on 9950X (32 threads)
- Compare against M25 baseline (~174μs age+die only, measured under ECM with ~50% CPU load)
- M26 benchmarks must document: thread count (`RAYON_NUM_THREADS`), CPU load condition, and whether jemalloc is active (WSL/Linux only). Numbers without context are not comparable.

---

## Implementation Ordering

Risk-mitigation sequence. New Rust modules first (pure logic, no FFI risk), then FFI changes, then Python wiring.

1. **Ecological stress formula swap** — update `tick.rs`, fix M25 tests. Smallest possible change, validates immediately.
2. **Satisfaction module** — `satisfaction.rs` with branchless formula, unit tests. Pure computation, no pool mutations.
3. **Demographics module** — `demographics.rs` with updated mortality + fertility. Extends PendingEvents with births.
4. **Behavior module** — `behavior.rs` with decision model. Depends on satisfaction being computed. Most complex new code.
5. **Tick orchestration** — update `tick.rs` to call satisfaction → decisions → demographics in order. Integration tests.
6. **Signals parsing** — `signals.rs` + FFI changes to accept civ signals and extended region state.
7. **Aggregates population** — update `pool.rs compute_aggregates()` to fill military/economy/culture/stability.
8. **Events population** — update FFI to return populated events RecordBatch.
9. **Python shadow mode** — `shadow.py`, `shadow_oracle.py`, updated `agent_bridge.py`.
10. **Determinism + benchmark** — full determinism test, performance validation.

---

## What This Milestone Does NOT Do

- No integration with Python turn loop (M27) — agent aggregates are discarded in shadow mode
- No 200-seed oracle gate validation (M28) — the framework is built, but the full gate runs in M28
- No scale optimization (M29) — no SIMD, no BitVec, no compaction
- No named characters or narrative (M30)
- No signal protocol for war outcomes (M27) — M26 reads `is_at_war` boolean, not detailed war results

## What M27 Will Build On

- Shadow mode proves agent behavior produces compatible distributions
- `compute_aggregates` provides the stat derivation M27 will wire into civ objects
- Events RecordBatch provides rebellion/migration events M27 will merge into world.events_timeline
- Signal protocol established — M27 extends with war outcomes, not replaces
