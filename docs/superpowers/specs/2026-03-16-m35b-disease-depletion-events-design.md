# M35b: Disease, Depletion & Environmental Events

> **Status:** Design approved. Ready for implementation planning.
>
> **Depends on:** M34 (resources & seasons) for resource types, yield arrays, seasonal enum, reserves field. M35a (rivers & trade corridors) for `river_mask` (flood event targeting), water quality baseline. M32 (utility-based decisions) for agent decision framework. M18 (emergence) for existing black swan pipeline, `world.pandemic_state`, and climate system's per-region `disaster_cooldowns`.
>
> **Scope:** Endemic disease as ongoing demographic pressure, resource depletion feedback loops, and condition-triggered environmental events. ~250-325 lines across 8 files (Python + Rust + tests).

---

## Overview

M34 introduced concrete resources and seasonal yields. M35a added rivers as geographic topology. But the simulation's demographic and ecological systems lack persistent pressure — population dynamics respond only to carrying capacity and ecological stress, and environmental disruption comes only from random M18 black swans.

M35b adds three interlocking systems that create ongoing, terrain-specific demographic pressure:

1. **Endemic disease** — persistent per-region disease state that fluctuates based on conditions (overcrowding, army movement, water quality, season), feeding directly into agent mortality.
2. **Resource depletion feedback** — population pressure on soil and overextraction of resources that permanently degrade yields, creating historical scars on the landscape.
3. **Environmental events** — condition-triggered events (locust swarms, floods, mine collapses, drought intensification) integrated into the existing emergence pipeline.

**Design principle:** All three systems are Python-primary. Disease severity is computed per-region in the ecology tick and passed to Rust as a single `f32` on `RegionState`. Rust's only change is reading that number in `mortality_rate()`. This preserves the M27 FFI boundary: Python computes region state, Rust consumes it for agent effects.

---

## Design Decisions

### Decision 1: Mortality-Only — No Satisfaction Wire

Disease affects agent mortality directly. It does not penalize agent satisfaction.

**Why:** The -0.4 non-ecological satisfaction budget (Decision 10) is scarce, shared across M36 (cultural identity), M37 (belief systems), and M38b (persecution). These are permanent societal forces that shape behavior every turn. Disease is episodic. Burning budget on a transient effect means less room for the systems that define Phase 6's identity.

**Why indirect works:** Disease kills agents -> population drops -> economic output drops -> civ-level stability hit -> satisfaction drops through existing channels. The behavioral response (migration, reduced rebellion) emerges from the population shock without a direct satisfaction wire. This is the kind of emergence Chronicler is built to produce.

**Calibration advantage:** Mortality-only gives M47 one knob per effect. Mortality rate controls demographic impact, existing satisfaction channels handle behavioral response. No tuning collision between disease severity and satisfaction impact.

### Decision 2: Fluctuating Endemic — Baseline + Flares + Decay

Disease is neither constant nor purely episodic. Each region has a terrain-determined baseline (persistent regional character) and condition-triggered flares (short-duration severity spikes with narratable causes).

**Why not constant:** A constant 0.02 mortality drain is invisible. It adjusts population equilibrium and disappears into the noise. Nobody reads a 500-turn chronicle and says "the tropical fever shaped this civilization's history." If you can't narrate it, it shouldn't be a system.

**Why not episodic-only:** Dropping the endemic baseline removes terrain identity from demographics. Coast vs. Desert vs. Swamp should feel different for population dynamics. Without endemic, a Plains region and a Tropical region with identical ecology stats produce identical demographics.

**Why fluctuating works:** The baseline encodes terrain character (compounds over 100+ turns into meaningful regional population differences). The flares provide narrative moments with concrete causality ("the army's march through the lowlands brought fever"). The decay ensures flares are temporary — the region isn't permanently scarred, but the flare left a demographic dent.

### Decision 3: Environmental Events in Existing Emergence Pipeline

New condition-triggered events added to `emergence.py`, using the same fire/resolve/emit pipeline as M18 black swans.

**Why not a separate system:** `emergence.py` already has severity multiplier integration, event emission with type/region/turn, cooldown tracking, interaction with StatAccumulator routing, and curator pipeline pickup. A second event system reimplements all of that. And M47 would have to calibrate two independent event frequency distributions that interact.

**Why not folding into ecology:** Events that silently modify yields are indistinguishable from droughts in the data bundle. The narrator can't tell the story if it can't see the event. Named events with `event_type` values flow through the curator and narrator pipelines for free.

### Decision 4: Permanent Depletion with Emergence Recovery

Resource depletion is permanent. Recovery comes only through rare emergence black swan events.

**Why permanent:** Environmental scars are the most memorable features of a civilization chronicle. "The cedars of the northern coast were felled for the great fleet and never grew back" is the kind of sentence that makes a 500-turn history feel like history. Reversible degradation produces forgettable midgame dips.

**Why emergence recovery:** M34's spec already establishes emergence-driven mineral recovery as precedent. The same mechanism handles yield recovery — a rare "ecological_recovery" event partially restores `resource_effective_yields`. Default state is permanent damage; exception is narratively framed recovery.

### Decision 5: Layer M18 Pandemics — Additive, Untouched

M18 pandemic black swans remain as-is. Their severity adds to endemic severity in the mortality function. M18 code is not modified.

**Why layering:** M18 pandemics are stable, tested, merged code that has survived three tuning passes. Refactoring them into the flare system means re-validating pandemic frequency, severity distribution, and interaction with the severity multiplier — all for zero new capability.

**Why narratively correct:** M18 pandemics are random — the plague comes without warning, not as a consequence of overcrowding. Endemic flares have rational causes (army passage, water quality). The distinction between causal (M35b) and acausal (M18) disease is narratively valuable. Two systems producing the same mortality number for different narrative reasons is correct, not redundant.

**Cooldown interaction:** M18 pandemics use a separate mechanism: `world.black_swan_cooldown` (global int) and `world.pandemic_state` (list of active `PandemicRegion`). M35b environmental events use per-region `region.disaster_cooldowns` (same dict as the climate system). To prevent stacking disease flares with active pandemics, the flare trigger check skips regions where the region name appears in `world.pandemic_state` (a pandemic is already active there). This reads M18 state without modifying M18 code. Environmental events use `disaster_cooldowns` exclusively — no interaction with `world.black_swan_cooldown`.

### Decision 6: Python-Primary Computation

Disease severity computed entirely in Python's ecology tick. Rust reads one `f32` from RegionState.

**Why:** Disease is per-region, not per-agent. The ecology tick is per-region. The trigger data (army movement, water quality, overcrowding) is all Python-side. Putting per-region computation into a per-agent Rust loop is architecturally backwards. This preserves the M27 FFI boundary: Python computes region state, Rust consumes it for agent effects.

### Decision 7: Soil Exhaustion — Population-Pressure Trigger

The original monoculture penalty (single crop for N turns) was replaced with population-pressure-based soil exhaustion.

**Why:** M34's resource assignment is immutable after world-gen. Most crop-producing regions have exactly 1 Crop-class resource because M34's slot system assigns at most 1-2 crops and the secondary is probabilistic. The monoculture penalty would fire on ~80% of crop regions by turn 30, with no mechanic for crop rotation to reset it. The penalty punished a condition the simulation can't correct.

**Population pressure is actionable:** Migration reduces population, relieving pressure. Disease can reduce population. Wars can depopulate. The simulation has levers to self-correct.

### Decision 8: Population-Based Extraction Pressure

Overfishing/overgrazing uses worker count vs. sustainable worker count, not yield vs. threshold.

**Why:** M34 defines extraction rate only for minerals. For Crop and Marine resources, there's no extraction rate concept — yield is computed from `base x season x climate x ecology`. Using `current_yield` as proxy would flag every healthy region in Autumn as "overextracting" (seasonal multiplier pushes yield above 70% of base). The metric must be population-based: too many workers extracting from a finite resource.

### Decision 9: Two Yield Arrays

Immutable `resource_base_yields` (world-gen original) + mutable `resource_effective_yields` (working copy, degraded by depletion).

**Why:** Depletion reduces the working yield. Recovery restores toward the original. Without the immutable original, there's no ceiling for recovery and no way to measure degradation severity. `resource_effective_yields` initialized as a copy of `resource_base_yields` at world-gen.

### Decision 10: Regression Contract

- **Yield formula regression:** M34 yield computation produces identical results when no M35b events are active (disease doesn't touch yields, depletion streaks start at 0).
- **Environmental events are additive:** New event types, not modifications of existing events. Existing M34 tests pass unchanged — their controlled conditions don't trigger M35b events.
- **Disease in `--agents=off`:** `endemic_severity` computed and stored on Region regardless of mode, but has no population effect. Aggregate mode uses StatAccumulator guards, not per-agent mortality. Disease is visible state with no aggregate-mode consumer.

---

## Endemic Disease System

### Data Model

Two new fields on `Region` (Python) and one on `RegionState` (Rust FFI):

| Field | Type | Set | Mutated | Location |
|-------|------|-----|---------|----------|
| `disease_baseline` | `float` | World-gen (terrain/climate lookup) | Immutable | Python: `models.py` |
| `endemic_severity` | `float` | World-gen (= baseline) | Every ecology tick | Python: `models.py`, Rust: `region.rs` as `f32` |

The disease vector label (Fever, Cholera, Plague) is **derived at narration time**, not stored. The mapping is deterministic:

```python
def disease_vector_label(region) -> str:
    if region.terrain == "desert":
        return "cholera"
    elif region.disease_baseline >= 0.02:
        return "fever"
    else:
        return "plague"
```

### Baseline Assignment (World-Gen)

Computed in `world_gen.py` during region initialization, after ecology defaults are set:

| Condition | Terrains (typical) | Vector | Baseline |
|-----------|-------------------|--------|----------|
| water > 0.6 AND soil > 0.5 | coast, forest, river (M34) | Fever | 0.02 |
| terrain == `desert` | desert | Cholera | 0.015 |
| Default | plains, mountains, tundra, hills (M34) | Plague | 0.01 |

Priority: Fever > Cholera > Plague (first match wins). Tundra falls to Plague default — cholera is a warm-climate waterborne disease, historically incorrect for cold-arid environments.

### Flare Triggers (Ecology Tick)

Computed per-region in `ecology.py`, at the top of the ecology tick **before** water/soil/forest updates run (disease reads current state, then ecology mutates it):

| Trigger | Condition | Severity Spike |
|---------|-----------|---------------|
| Overcrowding | population > 0.8 x carrying_capacity | +0.04 |
| Army passage | any agent with occupation == 1 (soldier) migrated into this region this turn | +0.03 |
| Water quality drop | water < 0.3 (non-arid terrain) OR water decreased by > 0.1 since tick start | +0.02 |
| Seasonal peak | Summer for Fever regions, Winter for Plague regions | +0.02 |

**Army passage predicate** — exact specification:

```python
army_arrived = any(
    e.event_type == "migration"
    and e.occupation == 1          # soldier
    and e.target_region == region.id
    for e in world.agent_events_raw
    if e.turn == world.turn - 1
)
```

Reads from `agent_events_raw` using **previous turn's** events. The ecology tick is Phase 9; the agent tick runs after Phase 9 (between Phase 9 and 10). When `tick_ecology` executes, current-turn agent events haven't been generated yet. The one-turn delay is narratively correct — disease incubation follows the army's march ("fever followed in the army's wake"). Invisible at simulation scale.

**Water quality delta** — computed inside `tick_ecology`, zero storage. Read `region.ecology.water` at the top of the ecology tick before any water updates. Disease trigger check uses this pre-update value. No `prev_water` field needed. Same pattern as existing soil degradation (reads forest_cover before updating it).

**Cholera: no seasonal modifier.** Cholera outbreaks are driven by water contamination events (army passage, water quality drops), not seasonal cycles. The seasonal peak trigger explicitly covers only Fever (Summer) and Plague (Winter).

**Triggers are additive.** Overcrowding + army passage in summer in a Fever region: 0.02 + 0.04 + 0.03 + 0.02 = 0.11.

**Severity cap:** 0.15. Prevents runaway stacking.

### Decay

Each ecology tick where no trigger fires, `endemic_severity` decays toward `disease_baseline` by 25% of the gap:

```python
severity -= 0.25 * (severity - baseline)
```

A 0.11 spike decays as: 0.11 -> 0.088 -> 0.074 -> 0.065 -> ... back near baseline in ~6-8 turns. High-severity window is ~4-6 turns, tail back to baseline ~12-15 turns.

### Mortality Integration (Rust)

`mortality_rate()` signature in `demographics.rs` changes from:

```rust
fn mortality_rate(age: u16, eco_stress: f32, is_soldier_at_war: bool) -> f32
```

to:

```rust
fn mortality_rate(age: u16, eco_stress: f32, is_soldier_at_war: bool, disease_severity: f32) -> f32
```

`disease_severity` is the `endemic_severity` f32 read from RegionState. The existing `is_soldier_at_war` parameter is preserved — it applies a 2x mortality multiplier for soldiers on active fronts (M26). `disease_severity` is additive in the mortality computation alongside `eco_stress`. Rust doesn't compute disease — it consumes one number.

Note: M18 pandemic mortality is handled separately via `StatAccumulator` population drains in `tick_pandemic()`, not through this function. The `disease_severity` parameter carries only endemic severity (M35b).

### Disease Severity Summary Table

| System | Trigger | Severity Range | Duration | Mortality Path |
|--------|---------|---------------|----------|----------------|
| Endemic baseline | Terrain + climate (world-gen) | 0.01-0.02 | Permanent | `disease_severity` param in `mortality_rate()` |
| Endemic flare | Overcrowding, army, water quality, season | 0.08-0.15 (baseline + triggers, capped) | 3-8 turns (decay) | `disease_severity` param in `mortality_rate()` |
| M18 pandemic | Random black swan (unchanged) | 0.10-0.20 | Existing | StatAccumulator population drain (unchanged) |

Endemic disease feeds into per-agent mortality via `disease_severity`. M18 pandemics apply population loss through StatAccumulator (unchanged). Flare triggers skip regions with active M18 pandemics (read `world.pandemic_state`, no M18 code modification). Environmental events use per-region `disaster_cooldowns` to prevent stacking.

---

## Environmental Events

Four condition-triggered events added to `emergence.py`. All use per-region `region.disaster_cooldowns` (same dict as the climate system's earthquake/volcanic events). M18 black swans use a separate global cooldown (`world.black_swan_cooldown`) and are not affected.

### New Function

`check_environmental_events(world, rng)` called alongside `check_black_swans()` in the emergence phase.

### Event Check Pattern

```python
for region in world.regions:
    if region.disaster_cooldowns:
        continue  # shared cooldown -- no stacking with any active disaster

    for event_check in [_check_locust, _check_flood, _check_collapse, _check_drought]:
        if event_check(region, world, rng):
            break  # fired, cooldown set, done with this region
```

Independent checks — each event gets its own probability roll. First to succeed fires and sets cooldown. No suppression of independent events on failed rolls. The shared cooldown prevents stacking after the first event fires.

### Event Definitions

| Event | Trigger Condition | Effect | Duration | Prob |
|-------|-------------------|--------|----------|------|
| **Locust Swarm** | terrain in {plains, desert} AND season in {Summer, Autumn} AND has Grain resource AND soil > 0.4 | All Crop-class yields (Grain, Botanicals) -> 0. Exotic unaffected. | 2-3 turns | 15% |
| **Flood** | river_mask != 0 (M35a) AND season = Spring AND water > 0.8 | Carrying capacity reduced 15% for duration; +0.15 soil after (silt deposit) | 1-2 turns | 20% |
| **Mine Collapse** | terrain = mountains AND has mineral resource AND reserves < 0.3 (M34) | Mineral extraction halved; mortality spike (see below) | 3-5 turns (extraction); 1 turn (mortality) | 10% |
| **Drought Intensification** | active DROUGHT event AND season = Summer AND water < 0.25 | Carrying capacity halved in region + adjacent Desert regions | 4-8 turns | 25% |

### Mine Collapse: Two-Duration Split

Mine collapse has two separate effects with different durations:

- **Extraction penalty:** mineral extraction halved for 3-5 turns, tracked via `disaster_cooldowns["mine_collapse"] > 0`. The extraction-halving check reads this key.
- **Mortality spike:** one-time write to `endemic_severity` at fire time. Severity spike of 0.08-0.12, producing ~5-10 deaths at typical region population (~200-400 agents). Actual deaths vary with population. Decays through the normal endemic decay path (25% per turn toward baseline). In `--agents=off` mode, population drain via `StatAccumulator.add(civ, "population", -N, "guard")` instead.

Routing mortality through `endemic_severity` avoids new FFI surface for a rare event. The narrator distinguishes mine collapse from disease via `event_type = "mine_collapse"` in the timeline.

### Locust Swarm Scope

Trigger requires Grain presence (locusts are attracted by grain fields). Effect zeroes all Crop-class yields: Grain and Botanicals. Exotic yields are unaffected — different agricultural practice (spices, dates, tree crops are locust-resistant or harvested differently).

### Drought Adjacent Regions

"Adjacent Desert regions" means terrain == `desert` only. Tundra is cold-arid, not heat-drought. The drought intensification spreads to neighboring Desert regions, not all arid terrains.

### Event Emission

Each event writes to `world.events_timeline` using the existing `Event` model with new `event_type` values: `"locust_swarm"`, `"flood"`, `"mine_collapse"`, `"drought_intensification"`. The curator and narrator pick these up through existing pipelines.

### Duration Tracking

Environmental events use `region.disaster_cooldowns` (per-region, type-keyed dict). Entry format: `{"event_type": turns_remaining}`. Each turn, the emergence phase decrements and removes expired entries. During the active window, the event's mechanical effect applies.

### Dependencies (All Landed)

All M35b dependencies are implemented and merged:

| Dependency | Source | Status |
|------------|--------|--------|
| `river_mask` | M35a | Merged — use directly |
| Season enum | M34 | Merged — use directly |
| Resource types (Grain, mineral) | M34 | Merged — use directly |
| `reserves` field | M34 | Merged — use directly |

No stubs needed. Implementation should use M34/M35a APIs directly.

---

## Resource Depletion Feedback

Two feedback loops computed per-region in `ecology.py` during the ecology tick.

### Soil Exhaustion (Population Pressure)

**Condition:** `population > 0.7 x carrying_capacity` in a region with at least 1 Crop-class resource, for 30+ consecutive turns.

**Tracking:** `soil_pressure_streak: int` on Region. Incremented each ecology tick when overcrowded AND crop-producing. Reset to 0 when population drops below `0.7 x carrying_capacity`.

**Effect at streak >= 30:**

- Soil degradation rate doubles (2x normal per-turn soil loss from population pressure)
- Event emitted: `"soil_exhaustion"` with region name ("The fields of {region} show signs of exhaustion from decades of intensive cultivation")

**Recovery:** When population drops below threshold, streak resets, degradation returns to normal rate. Soil damage already done is permanent (soil only recovers via forest regrowth in the existing ecology model, which is slow).

### Overextraction (Overfishing / Overgrazing)

**Condition:** More workers extracting than the resource can sustain, for 35 consecutive turns.

```python
sustainable_workers = resource_effective_yield * WORKERS_PER_YIELD_UNIT
extraction_pressure = worker_count / max(1, sustainable_workers)
overextracting = extraction_pressure > 1.0
```

Where `worker_count` is the number of agents with the relevant occupation in the region. `WORKERS_PER_YIELD_UNIT` (default: 200 `[CALIBRATE]`) is a single constant in `ecology.py`, tunable in M47. At this default, a region with effective_yield 0.8 sustains 160 workers; a population of 200+ workers in that region produces extraction_pressure > 1.0.

**Tracking:** `overextraction_streaks: dict[int, int]` on Region, keyed by resource slot index. Each depletable resource tracks its own streak independently. Incremented per-resource when `overextracting` is True for that resource. Reset to 0 when extraction drops below sustainable yield. A region with both Grain and Fish tracks two independent streaks — Grain can be overextracted while Fish is sustainable.

**Applies to:** Depletable resource classes only — Crop (Grain, Botanicals), Marine (Fish), Mineral (already has extraction mechanics in M34). Not Exotic (trade goods, not extraction-limited).

**Effect at streak >= 35 (per resource):**

- `resource_effective_yields[resource]` permanently decreases by 10%
- `overextraction_streaks[resource]` resets to 0 (can degrade again if overextraction continues)
- Event emitted: `"resource_depletion"` with resource type and region

### Yield Arrays

| Field | Type | Mutability | Purpose |
|-------|------|------------|---------|
| `resource_base_yields` | `list[float]` | Immutable after world-gen | Original ceiling for recovery comparison |
| `resource_effective_yields` | `list[float]` | Mutable | Working yields, degraded by depletion |

`resource_effective_yields` initialized as a shallow copy of `resource_base_yields` at world-gen.

All gameplay systems read `resource_effective_yields`. Degradation reduces `effective`. Recovery restores `effective` toward `base`, never exceeding it.

### Ecological Recovery (Emergence Black Swan)

New entry in the emergence black swan table: `"ecological_recovery"`.

- **Probability:** ~2% per eligible turn
- **Eligibility:** any resource in region where `effective_yield < 0.8 x base_yield`
- **Effect:** restore up to 50% of lost yield (never exceeding base)
- **Narration:** "After decades of neglect, the reefs off the southern coast began to recover"

Uses the existing emergence pipeline. No new mechanism.

---

## Data Model

### Python (`models.py`)

| Field | Type | On | Default | Purpose |
|-------|------|----|---------|---------|
| `disease_baseline` | `float` | Region | 0.01 | Terrain-determined endemic floor |
| `endemic_severity` | `float` | Region | 0.01 | Current effective disease severity (fluctuates) |
| `soil_pressure_streak` | `int` | Region | 0 | Consecutive turns of overcrowded crop production |
| `overextraction_streaks` | `dict[int, int]` | Region | `{}` | Per-resource consecutive turns of unsustainable worker pressure, keyed by slot index |
| `resource_effective_yields` | `list[float]` | Region | Copy of `resource_base_yields` | Mutable working yields |

### Rust (`region.rs`)

```rust
pub endemic_severity: f32,  // 0.0-0.15, read from Python via Arrow
```

Total Rust addition: 4 bytes per region. At ~150 regions: ~600 bytes. Negligible.

### Data Flow Per Turn

```
Phase 9 (tick_ecology):
  1. Read current water value (pre-update, for disease triggers)
  2. Compute endemic_severity:
     a. Check flare triggers (overcrowding, army passage, water quality, season)
     b. If any trigger: spike severity (additive, cap 0.15)
     c. If no trigger: decay toward baseline (25% of gap)
  3. Compute depletion feedback:
     a. Check soil_pressure_streak (overcrowded crop regions)
     b. Check overextraction_streak (worker count vs sustainable workers)
     c. Apply degradation if streaks exceed thresholds
  4. Run existing soil/water/forest updates
  5. _clamp_ecology() runs

Emergence phase:
  6. check_environmental_events() alongside check_black_swans()
     - Each region checked if no active disaster_cooldowns
     - Independent event checks with break on first fire
     - Events write to events_timeline and disaster_cooldowns

agent_bridge.py:
  7. endemic_severity column added to region state RecordBatch

Rust agent tick:
  8. demographics.rs reads endemic_severity from RegionState
     - mortality_rate(age, eco_stress, is_soldier_at_war, disease_severity)
```

---

## Constants

All `[CALIBRATE]` for M47:

| Constant | Default | Location | Purpose |
|----------|---------|----------|---------|
| `DISEASE_BASELINE_FEVER` | 0.02 | Python (ecology) | Endemic floor for tropical/wet regions |
| `DISEASE_BASELINE_CHOLERA` | 0.015 | Python (ecology) | Endemic floor for desert regions |
| `DISEASE_BASELINE_PLAGUE` | 0.01 | Python (ecology) | Endemic floor for temperate/default regions |
| `DISEASE_SEVERITY_CAP` | 0.15 | Python (ecology) | Maximum endemic_severity |
| `DISEASE_DECAY_RATE` | 0.25 | Python (ecology) | Per-tick decay fraction toward baseline |
| `FLARE_OVERCROWDING_THRESHOLD` | 0.8 | Python (ecology) | Population / capacity ratio triggering overcrowding flare |
| `FLARE_OVERCROWDING_SPIKE` | 0.04 | Python (ecology) | Severity spike from overcrowding |
| `FLARE_ARMY_SPIKE` | 0.03 | Python (ecology) | Severity spike from army passage |
| `FLARE_WATER_SPIKE` | 0.02 | Python (ecology) | Severity spike from water quality drop |
| `FLARE_SEASON_SPIKE` | 0.02 | Python (ecology) | Severity spike from seasonal peak |
| `SOIL_PRESSURE_THRESHOLD` | 0.7 | Python (ecology) | Population / capacity ratio for soil exhaustion |
| `SOIL_PRESSURE_STREAK_LIMIT` | 30 | Python (ecology) | Turns before soil degradation doubles |
| `OVEREXTRACTION_STREAK_LIMIT` | 35 | Python (ecology) | Turns before permanent yield reduction |
| `OVEREXTRACTION_YIELD_PENALTY` | 0.10 | Python (ecology) | Fraction of effective_yield lost per event |
| `WORKERS_PER_YIELD_UNIT` | 200 | Python (ecology) | Sustainable worker count per unit of effective yield |
| `LOCUST_PROBABILITY` | 0.15 | Python (emergence) | Per-eligible-turn chance of locust swarm |
| `FLOOD_PROBABILITY` | 0.20 | Python (emergence) | Per-eligible-turn chance of flood |
| `COLLAPSE_PROBABILITY` | 0.10 | Python (emergence) | Per-eligible-turn chance of mine collapse |
| `DROUGHT_INTENSIFICATION_PROBABILITY` | 0.25 | Python (emergence) | Per-eligible-turn chance of drought intensification |
| `COLLAPSE_MORTALITY_SPIKE` | 0.10 | Python (emergence) | Severity spike from mine collapse (midpoint of 0.08-0.12) |
| `ECOLOGICAL_RECOVERY_PROBABILITY` | 0.02 | Python (emergence) | Per-eligible-turn chance of yield recovery |
| `ECOLOGICAL_RECOVERY_FRACTION` | 0.50 | Python (emergence) | Max fraction of lost yield restored |

Constants location: all 21 constants defined in `tuning.py` with `KNOWN_OVERRIDES` registration, following the exact pattern from M34 (`K_DEPLETION_RATE`, etc.) and M35a (`K_RIVER_WATER_BONUS`, etc.). This enables scenario-level override via YAML. Functions in `ecology.py` and `emergence.py` read constants via `get_override(world, K_CONSTANT_NAME, default)`.

---

## File Changes

| File | Change | Lines (est.) |
|------|--------|-------------|
| `ecology.py` | `compute_disease_severity()`: baseline lookup, flare trigger checks, additive spikes, cap, decay. Soil exhaustion loop: streak tracking, degradation doubling. Overextraction loop: worker pressure computation, yield degradation. | +80-100 |
| `emergence.py` | `check_environmental_events()`: 4 event check functions with condition gates + probability rolls. Break-on-first-fire loop. `ecological_recovery` black swan entry. | +60-80 |
| `demographics.rs` | `mortality_rate()` signature: add `disease_severity: f32` parameter (existing `is_soldier_at_war` preserved). Additive mortality computation. | +5-10 |
| `region.rs` | Add `endemic_severity: f32` to `RegionState` struct. | +3 |
| `agent_bridge.py` | Pass `endemic_severity` to Rust via region state Arrow RecordBatch. | +3-5 |
| `models.py` | New fields on Region: `disease_baseline`, `endemic_severity`, `soil_pressure_streak`, `overextraction_streaks`, `resource_effective_yields`. | +10-15 |
| `world_gen.py` | Initialize `disease_baseline` (terrain lookup), `endemic_severity` (= baseline), `resource_effective_yields` (copy of `resource_base_yields`) at world-gen. | +10-15 |
| Tests | Disease demographics, flare trigger gate tests, environmental event condition gates, depletion streak tests, cap enforcement, regression checks. | +80-100 |

**Total: ~250-325 lines across Python + Rust + tests.**

### What Doesn't Change

- `agent.rs` -- no per-agent disease state
- `satisfaction.rs` -- disease has no satisfaction effect (Decision 1)
- `behavior.rs` -- no disease influence on decision-making
- `tick.rs` -- no new tick phase; disease is consumed in existing demographics phase
- M18 pandemic code -- untouched (Decision 5)

---

## Validation

Phase 6 validation is internal consistency, not oracle comparison.

### Disease

- Regions with high endemic baseline (Fever, 0.02) show 2-5% higher cumulative mortality than low-baseline regions (Plague, 0.01) over 500 turns
- Flare triggers produce measurable mortality spikes: a region that receives army passage shows elevated mortality for 3-8 turns following the event
- `endemic_severity` stays within [`disease_baseline`, `DISEASE_SEVERITY_CAP` (0.15)] at all times

### Environmental Events

- Each event type fires at least once in a 500-turn run with appropriate terrain/conditions present
- No event fires when its condition gate is false (locust never fires in mountains, flood never fires without `river_mask`)
- Shared cooldown prevents stacking: no region has two disaster events active simultaneously
- Event emission appears in `events_timeline` with correct `event_type` for curator/narrator pickup

### Depletion

- Overcrowded crop regions (pop > 0.7 x capacity for 30+ turns) show measurably faster soil degradation than non-overcrowded crop regions
- Overextracted resources show permanent `effective_yield` reduction after 35-turn streak
- `resource_effective_yields[i]` never exceeds `resource_base_yields[i]` for any resource (ceiling enforcement)
- Ecological recovery emergence event restores yield toward base, never exceeding it

### Regression

- **Yield formula regression:** M34 yield computation identical when no M35b events active. Existing M34 tests pass unchanged (controlled conditions don't trigger M35b events).
- **Environmental events are additive:** New event types, not modifications of existing events. No existing emergence behavior changes.
- **Disease in `--agents=off`:** `endemic_severity` computed and stored on Region regardless of mode. No population effect in aggregate mode — aggregate mode uses StatAccumulator guards, not per-agent mortality. Tests verify severity is computed but population is unaffected in `--agents=off`.
- **`--agents=shadow`:** Shadow comparison within tolerance bands established by M28.

---

## Forward Dependencies

| M35b Provides | Consumed By |
|---------------|-------------|
| `endemic_severity` on RegionState | M36 (cultural identity -- regions with chronic disease develop different cultural traits) |
| `resource_effective_yields` | M41 (wealth -- economic output reads effective, not base) |
| Environmental event types in timeline | M44 (API narration -- narrator can frame floods, locusts, collapses) |
| `disease_baseline` terrain mapping | M46 (viewer -- disease heatmap layer reads baseline for color scale) |
| Soil exhaustion / depletion events | M47 (tuning -- depletion rates calibrated against 500-turn population outcomes) |
