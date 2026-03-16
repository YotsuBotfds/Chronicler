# M34: Regional Resources & Seasons

> **Status:** Design approved. Ready for implementation planning.
>
> **Depends on:** M32 (utility-based decisions) for agent satisfaction integration. M23 (coupled ecology) for soil/water/forest_cover stats.
>
> **Scope:** Concrete resource types per region, seasonal yield cycle, mineral depletion, famine trigger migration. ~400 lines Python, ~50 lines Rust (RegionState extensions + satisfaction formula changes).

---

## Overview

M23 introduced coupled ecology (soil, water, forest_cover) as abstract floats that drive carrying capacity. Agents interact with these indirectly — farmer satisfaction reads an ecology-derived score, not a concrete "how much grain did this region produce."

M34 replaces abstract ecology-driven economy with concrete resource production. Each region produces specific goods (grain, timber, ore) whose yields depend on terrain, season, climate, and ecology health. The famine trigger migrates from a raw water sentinel to crop yield shortfall. Mineral resources deplete over time, creating boom-bust cycles that drive migration and trade.

**Design principle:** Ecology stats (soil, water, forest_cover) remain the substrate. Resources are a *lens* on ecology — the yield formula reads ecology stats, not the other way around. Infrastructure modifies ecology; ecology modifies yields. No shortcuts, no double-dipping.

---

## Design Decisions

### 8 Resource Types, Collapsed by Mechanical Equivalence

The Phase 6 roadmap sketches 13 resource types. M34 collapses to 8 by merging types that never produce different agent decisions, yield formulas, or trade outcomes:

| Type | ID | Merges | Mechanical Class |
|------|----|--------|-----------------|
| Grain | 0 | Wheat + Barley | Crop |
| Timber | 1 | — | Forestry |
| Botanicals | 2 | Herbs + Spices | Crop |
| Fish | 3 | — | Marine |
| Salt | 4 | — | Evaporite |
| Ore | 5 | Iron + Copper | Mineral |
| Precious | 6 | Silver + Gold | Mineral |
| Exotic | 7 | Dates + Furs | Crop |

**Why not keep all 13:** The Rust-side enum overhead compounds with seasons — 13 types × 4 seasons × satisfaction formulas is a large tuning surface for M47. The narrative distinction (wheat vs. barley) doesn't require a mechanical distinction; the LLM narrator can flavor freely.

**Why not collapse further to 5 classes:** Loses terrain specificity. The point of resources is that Desert feels different from Coast. Five abstract classes would need terrain-specific yield modifiers to recreate the differentiation, reinventing the type system through the back door.

**Critical merge boundary:** Ore (Iron + Copper) must stay separate from Precious (Silver + Gold). These have different downstream effects — Ore feeds military capacity, Precious feeds wealth and luxury trade. Collapsing them would erase a meaningful simulation distinction.

### 5 Mechanical Classes

Each class determines which formula branch runs — ecology_mod computation, depletion behavior, and satisfaction mapping:

| Class | Types | ecology_mod | Depletes? | Satisfaction target |
|-------|-------|-------------|-----------|-------------------|
| Crop | Grain, Botanicals, Exotic | soil × water | No | Farmer |
| Forestry | Timber | forest_cover | No | Farmer |
| Marine | Fish | 1.0 | No | Farmer |
| Mineral | Ore, Precious | 1.0 (uses reserve ramp) | Yes | Farmer (as miner) |
| Evaporite | Salt | 1.0 | No | Merchant (trade good) |

**Fish ecology_mod = 1.0:** Coastal fishing isn't structurally affected by soil or drought at the resolution this simulation operates. This creates natural famine resistance for coastal regions — a historically accurate asymmetry that emerges from the formula without special cases.

**Farmer-as-miner:** Agents with farmer occupation in mineral-producing regions are treated as miners for extraction. The occupation represents labor allocation, not crop-specific work. Forward dependency: M41 (Wealth) must dispatch wealth calculation by resource type, not just occupation.

### Hybrid Resource Assignment (Deterministic Primary, Probabilistic Secondary)

Every region gets exactly 1 guaranteed primary resource (terrain-locked), up to 1 probabilistic secondary, and a rare chance at a tertiary:

- **Slot 1 (primary):** Terrain-locked, always present. Looked up from `TERRAIN_PRIMARY_RESOURCE` constant. No RNG.
- **Slot 2 (secondary):** Rolls from `TERRAIN_SECONDARY_POOL` with per-terrain probabilities. May be empty (255).
- **Slot 3 (tertiary):** Very low probability from a cross-terrain pool. The "geologically lucky" slot.

**Why deterministic primary:** The farmer satisfaction formula reads slot 1's yield. A Plains region with no Grain creates a degenerate satisfaction case that must be guarded everywhere. Deterministic primary eliminates that bug class entirely.

**Why probabilistic secondary:** The current `resources.py` already works this way. Two Plains regions differing in secondary resource produce different trade specialization over 500 turns — meaningful variation, not noise.

### 3 Slots Per Region

The byte savings of dropping to 2 slots (750 bytes at 150 regions) don't motivate the cut. Desert specifically earns the third slot — Exotic (dates) + Salt (evaporation) + Precious (rare silver) is historically authentic and narratively important. Collapsing to 2 forces a choice between Salt and Precious, weakening desert trade stories.

### 12-Step Seasonal Clock, 4 Mechanical Seasons

The clock ticks once per turn (`season_step = turn % 12`). Season is derived: `season_id = season_step // 3`. The 12-step clock is a **scheduling mechanism**, not a yield dimension — yield modifiers are flat within a season.

**Why not 12 distinct steps:** The simulation's turn resolution doesn't support "early Spring vs. mid Spring" precision. With 8 types × 4 seasons × 3 intra-season steps, the calibration surface drowns signal in noise.

**Why keep 12 steps instead of just 4:** The 48-turn macro cycle (4 climate phases × 12 seasonal steps) produces statistically stable season×climate co-occurrence in 200-seed runs. Compressing to 16 turns loses that stability.

### Linear Depletion with Continuous Ramp

Mineral reserves decrease linearly per turn. The last 25% of reserves produce diminishing yields via a continuous ramp (not a binary threshold jump):

```python
reserve_ramp = min(1.0, reserves / 0.25)
```

**Why linear (not diminishing returns):** The ramp already creates the narrative cliff — "the mines started to fail" emerges naturally as reserves cross 0.25. Adding a curve exponent creates a parameter that fights the ramp. One fewer tuning dimension.

**Salt exempt from depletion.** Salt flats and brine springs are renewable on civilizational timescales. `reserves` stays 1.0, never decremented.

### Permanent Exhaustion, Recovery via Emergence Only

Once reserves < 0.01, the mine produces a trickle (base_yield × 0.04) indefinitely. No built-in recovery mechanic.

**Why no `EXHAUSTION_RECOVERY_CHANCE`:** It mutes the migration pressure that makes depletion interesting, and creates a constant that exists to fight another constant — tuning against yourself in M47.

**Discovery events** belong in Phase 10 emergence as occasional black swans that partially restore reserves (30-50%). Rare, meaningful, narratively framed ("prospectors struck a new vein"), and already wired through the existing emergence event system.

### Famine Trigger Migrated to Crop Yield

Old (M23): `famine if water < 0.20`. New (M34): `famine if food_yield < FAMINE_YIELD_THRESHOLD`.

**Why migrate:** Famine is lack of food, not lack of water. The whole point of M34 is distinguishing "no water" from "no food." Keeping the water sentinel creates disconnects where a coastal Fish region has drought but abundant food (no famine should fire), or a Plains region has good water but degraded soil (famine should fire).

Routing famine through yields validates the M34 architecture — the new system actually bears load.

### Subsistence Baseline for Non-Food Terrains

Mountains have no food resource in any slot. ~50% of Forest regions (when Botanicals doesn't roll) have only Timber. With the famine trigger migrated to food yield, these regions would be in permanent famine — not "migration pressure," but uninhabitable.

**Resolution: every region gets a subsistence food baseline** representing foraging, hunting, small gardens, and terraced farming — independent of resource slots:

```python
SUBSISTENCE_BASELINE = 0.15  # [CALIBRATE]
subsistence = SUBSISTENCE_BASELINE * climate_mod_for_crops
food_yield = max(subsistence, max((y for ... if food_type), default=0.0))
```

This is historically accurate — mountain villages survived on terrace agriculture and herding; forest communities foraged. The baseline is modified by climate phase (same crop modifier), so drought reaches foragers: temperate = `0.15 × 1.0 = 0.15` (above threshold), drought = `0.15 × 0.5 = 0.075 < 0.12` → famine. See Famine Mechanics section for full pseudocode.

**Why not add food to mountain/forest pools instead:** Inflates the tuning surface and changes the terrain identity. Mountains should be mineral regions, not grain regions with a side of ore.

### Infrastructure Modifies Ecology Only

IRRIGATION gives +0.03 water recovery. This already boosts crop yields because it sustains the water multiplier in ecology_mod near 1.0 during drought. Adding a direct yield bonus would double-dip.

The causal chain: Infrastructure → ecology stat → yield formula. No shortcuts. This means "the aqueducts kept the fields green" emerges from the math, not from a scripted bonus.

---

## Terrain-Resource Assignment Table

| Terrain | Slot 1 (locked) | Slot 2 (probabilistic) | Slot 3 (rare) |
|---------|-----------------|------------------------|----------------|
| Plains | Grain | Botanicals (30%) | Precious (5%) |
| Forest | Timber | Botanicals (50%) | Ore (10%) |
| Mountains | Ore | Precious (40%) | Salt (10%) |
| Coast | Fish | Salt (60%) | Botanicals (15%) |
| Desert | Exotic | Salt (50%) | Precious (20%) |
| Tundra | Exotic | Ore (15%) | — |
| River | Grain | Fish (40%) | Botanicals (20%) |
| Hills | Grain | Ore (30%) | Timber (20%) |

All 8 terrain types from the existing `TERRAIN_RESOURCE_PROBS` are covered. River and Hills are used in scenarios and the adjacency system (`SEA_ROUTE_TERRAINS` includes river).

All probabilities `[CALIBRATE]` for M47. Assignment runs once at world-gen in Python (`resources.py`), replacing the current `assign_resources()`.

---

## Seasonal Cycle

### Season Table

| Season | ID | Turns | Mechanical Role |
|--------|----|-------|-----------------|
| Spring | 0 | 0-2 | Planting. Soil recovery boost. |
| Summer | 1 | 3-5 | Peak water demand. Drought risk amplified. |
| Autumn | 2 | 6-8 | Harvest. Peak crop yields. Trade peak. |
| Winter | 3 | 9-11 | Reduced yields. Mortality pressure. Migration pressure. |

### Intra-Season Positions

Only two matter mechanically:

| Position | Turn within season | Effect |
|----------|-------------------|--------|
| Open (turn 0) | First turn of season | Demand signal spike (farmer occupation demand adjusts) |
| Close (turn 2) | Last turn of season | Harvest event fires. Yield delivered to civ-level stats. Narrator hook. |
| Mid (turn 1) | Middle | No special effect. Season modifier runs normally. |

The Autumn close is a **narrative hook and accounting moment**, not a mechanical spike. The yield formula runs identically every turn. No stockpile mechanism in M34 — that's M42 (Goods Production & Trade) scope.

### Season Modifier Table

Flat within a season — no intra-season curves:

| Season | Grain | Timber | Botanicals | Fish | Salt | Ore | Precious | Exotic |
|--------|-------|--------|------------|------|------|-----|----------|--------|
| Spring | 0.8 | 0.6 | 1.2 | 1.0 | 0.8 | 0.9 | 0.9 | 1.0 |
| Summer | 1.2 | 1.0 | 0.8 | 1.0 | 1.2 | 1.0 | 1.0 | 0.8 |
| Autumn | 1.5 | 1.2 | 0.6 | 0.8 | 1.0 | 1.0 | 1.0 | 1.2 |
| Winter | 0.3 | 0.8 | 0.2 | 0.6 | 1.0 | 0.9 | 1.0 | 0.6 |

All `[CALIBRATE]`. Key shapes: Grain peaks at Autumn harvest, crashes in Winter. Salt and Precious near-flat (extraction doesn't care about seasons). Botanicals inverse to Grain — thrive in Spring, dormant in Winter.

### Climate Interaction

Orthogonal multiplier layer, applied on top of season. Per mechanical class (not per type):

| Climate Phase | Crop | Forestry | Marine | Mineral | Evaporite |
|---------------|------|----------|--------|---------|-----------|
| TEMPERATE | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| WARMING | 0.9 | 0.9 | 1.0 | 1.0 | 1.1 |
| DROUGHT | 0.5 | 0.7 | 0.8 | 1.0 | 1.2 |
| COOLING | 0.7 | 0.8 | 0.9 | 1.0 | 0.9 |

DROUGHT devastates crops (0.5), barely touches minerals, and boosts Salt (evaporation concentrates brine). The 48-turn macro cycle creates the key asymmetry: Summer drought (`1.2 × 0.5 = 0.6` Grain) is survivable. Winter drought (`0.3 × 0.5 = 0.15` Grain) is catastrophic.

### Harvest Boundary Events

Fire at season close (turn 2 of each season):

| Event | Season | Effect |
|-------|--------|--------|
| Planting report | Spring close | Demand signals locked for the season |
| Mid-year yield check | Summer close | Early famine warning if yields trending low |
| **Harvest** | Autumn close | Primary yield delivery, trade surplus calculated, narrator hook |
| **Winter toll** | Winter close | Mortality spike if food insufficient, migration cascade check |

---

## Yield Formulas

### Master Formula

One formula, resource-class-specific terms default to 1.0:

```
current_yield = base_yield × season_mod × climate_mod × ecology_mod × reserve_ramp
```

Per-class breakdown:

| Term | Crop | Forestry | Marine | Mineral | Evaporite |
|------|------|----------|--------|---------|-----------|
| `base_yield` | Set at world-gen | Set at world-gen | Set at world-gen | Set at world-gen | Set at world-gen |
| `season_mod` | From season table | From season table | From season table | From season table | From season table |
| `climate_mod` | From climate table | From climate table | From climate table | 1.0 | From climate table |
| `ecology_mod` | soil × water | forest_cover | 1.0 | 1.0 | 1.0 |
| `reserve_ramp` | 1.0 | 1.0 | 1.0 | min(1.0, reserves/0.25) | 1.0 |

### Base Yield Generation

At world-gen:

```python
base_yield = RESOURCE_BASE[resource_type] × (1.0 + variance)
```

Where `variance ~ Uniform(-0.2, +0.2)` gives ±20% inter-region differentiation. `RESOURCE_BASE` is a constant table, one value per resource type `[CALIBRATE]`.

### Mineral Extraction and Depletion

```python
extraction_rate = base_yield × (worker_count / target_worker_count)
reserves -= extraction_rate × DEPLETION_RATE       # [CALIBRATE] ~0.009/turn
reserve_ramp = min(1.0, reserves / 0.25)
current_yield = base_yield × season_mod × reserve_ramp
```

- `worker_count`: agents with farmer occupation in the region (farmer-as-miner). Empty regions have `worker_count = 0`, giving `extraction_rate = 0` — no miners, no depletion.
- `target_worker_count = max(1, effective_capacity(region) // 3)`: one-third of the region's effective carrying capacity. At full staffing (`worker_count >= target`), depletion runs at baseline rate. Under-populated regions deplete proportionally slower.
- At `reserves < 0.01`: clamp to exhausted (`current_yield = base_yield × 0.04`). Near-zero trickle, not zero.
- Salt exempt: `reserves` always 1.0, never decremented.
- Target: rich mineral regions reach exhaustion in 80-150 turns at full exploitation.

### Famine Mechanics

```python
# Compute max food yield across food-type slots, with subsistence floor
# FOOD_TYPES = {GRAIN, FISH, BOTANICALS, EXOTIC}
slot_food = max((y for rtype, y in zip(region.resource_types, yields)
                 if rtype in FOOD_TYPES), default=0.0)

# Subsistence baseline affected by climate — drought hits foragers too
subsistence = SUBSISTENCE_BASELINE * climate_mod_for_crops
food_yield = max(subsistence, slot_food)

if food_yield < FAMINE_YIELD_THRESHOLD:
    emit FAMINE event
```

The `default=0.0` handles regions with zero food slots (Mountains, some Forests). `climate_mod_for_crops` applies to the baseline so drought reaches foragers: temperate subsistence = `0.15 × 1.0 = 0.15` (above threshold), drought subsistence = `0.15 × 0.5 = 0.075` (below threshold → famine).

`FAMINE_YIELD_THRESHOLD` `[CALIBRATE]`: must sit below `base × 0.3 × 1.0 × healthy_ecology` (normal Winter — no famine) but above `base × 0.3 × 0.5 × degraded_ecology` (drought Winter with stress — famine). Target: 5-15% of turns during drought phases, near-zero during temperate.

Multi-food regions use `max()` over food-type slots — the better crop saves you. Coastal Fish regions naturally resist drought famine (ecology_mod = 1.0).

**Botanicals-only regions are Winter-fragile by design.** A Forest region whose only food source is Botanicals (secondary slot) has Winter season_mod = 0.2 — very low famine resistance. This is intentional: Forest primary is Timber (not food), so a forest region without Grain secondary is subsistence-marginal in winter. This creates migration pressure toward mixed-resource regions, which is correct behavior.

Famine effects unchanged from M23: population drain, stability hit, refugee flow to adjacent regions. Event type stays `FAMINE`.

---

## Data Model

### Rust-Side RegionState Extensions

New columns in the Arrow RecordBatch:

```rust
// Added to RegionState (region.rs)
pub resource_types: [u8; 3],      // Resource enum IDs; 255 = empty slot
pub resource_yields: [f32; 3],    // Current yield per slot (computed Python-side each turn)
pub resource_reserves: [f32; 3],  // Depletion state; 1.0 = full/renewable, 0.0 = exhausted
pub season: u8,                   // 0-11 (current position in 12-step clock)
pub season_id: u8,                // 0-3 (Spring/Summer/Autumn/Winter)
```

Total addition: 29 bytes per region. At ~150 regions: ~4.3 KB. `climate_phase` already on RegionState from M23.

### Python-Side Model Extensions

New fields on the Region model (`models.py`), not RegionEcology:

```python
resource_types: list[int]         # Length 3, set at world-gen, immutable after
resource_base_yields: list[float] # Length 3, set at world-gen (with ±20% variance)
resource_reserves: list[float]    # Length 3, mutated by tick_ecology each turn
```

RegionEcology stays untouched — soil/water/forest_cover unchanged. Resources are a property of the region, not the ecology. Ecology feeds into yields but doesn't own them.

`current_yield` is **not stored** on the Python model — computed fresh each turn in `tick_ecology()` and written directly to Arrow columns. No stale state.

### Data Flow Per Turn

```
Phase 9 (tick_ecology):
  1. Compute season = turn % 12, season_id = season // 3
  2. Read climate_phase (already computed in Phase 1)
  3. For each region, for each resource slot:
     a. Look up season_mod[resource_type][season_id]
     b. Look up climate_mod[resource_class][climate_phase]
     c. Compute ecology_mod by resource class
     d. Compute reserve_ramp, apply depletion if mineral
     e. current_yield = base × season × climate × ecology × ramp
  4. Famine check: max food yield < threshold → emit FAMINE event
  5. Write resource_yields, resource_reserves, season, season_id
     into Arrow RecordBatch columns

agent_bridge.py (between Phase 9 and Rust tick):
  - RecordBatch already passes RegionState to Rust
  - New columns added to schema: resource_types, resource_yields,
    resource_reserves, season, season_id
  - No new FFI mechanism — just wider RecordBatch

Rust agent tick:
  - satisfaction.rs reads resource_yields from RegionState
  - behavior.rs reads season_id for migration utility (M32 hook)
```

---

## Agent Integration

### Farmer Satisfaction

Replaces current ecology-derived satisfaction component with concrete yield read:

```rust
fn resource_satisfaction(region: &RegionState) -> f32 {
    let primary_yield = region.resource_yields[0];
    let sat = (primary_yield - FAMINE_YIELD_THRESHOLD)
            / (PEAK_YIELD - FAMINE_YIELD_THRESHOLD);
    sat.clamp(0.0, 1.0)
}
```

The farmer doesn't care *why* yields are low (drought? bad soil? winter?) — they see the number. All causal complexity lives Python-side; Rust stays simple.

**Intentional decoupling: satisfaction measures labor productivity, not food supply.** A Mountain farmer with high Ore yield has high satisfaction (productive mining) even if the region relies on subsistence food. Famine is a separate system — it fires from the Python-side food yield check, not from Rust satisfaction. This means "high satisfaction + active famine" can co-occur in mineral regions during drought, which is correct: the miners are productive but the food supply failed. The two signals drive different agent behaviors (satisfaction → stay/switch, famine → population drain + migration). M42 (Goods Production) can later couple food availability into satisfaction if needed.

### Merchant Satisfaction

Reads trade good availability:

```rust
fn trade_satisfaction(region: &RegionState) -> f32 {
    let mut trade_score: f32 = 0.0;
    for (&rtype, &yield_val) in region.resource_types.iter()
        .zip(region.resource_yields.iter())
    {
        if rtype != 255 && yield_val > 0.0 {
            // Non-food resources contribute more to trade satisfaction
            let weight = if is_food(rtype) { 0.15 } else { 0.35 };
            trade_score += weight;
        }
    }
    trade_score.clamp(0.1, 1.0)
}
```

Continuous rather than step-function — avoids 0.4 satisfaction jumps from gaining/losing a single trade good. Non-food resources (Ore, Precious, Salt) contribute more than food. Mountains with Ore + Precious = 0.7. Tundra with only Exotic (food) = 0.15. Coast with Fish + Salt = 0.50. Desert with Exotic + Salt + Precious = 0.85.

### Occupation Demand Shifts

Computed Python-side, fed through existing `StatAccumulator` demand signal path:

- Mineral-producing region: soldier demand +1 tier (protection), merchant demand +1 tier (trade)
- Multi-resource region (2+ filled slots): merchant demand +1 tier
- Single-food region: no shift (baseline)

No new mechanism — uses M27's demand signal infrastructure.

### M32 Integration Hook

Migration utility in `behavior.rs` can optionally read `season_id`:

```rust
let season_push = if region.season_id == 3 { WINTER_MIGRATION_BOOST } else { 0.0 };
```

Forward hook — M32 can wire it or defer. The data is on RegionState either way.

---

## Validation

### Tier 1: Structural Unit Tests

Deterministic, no RNG, fast.

| Test | Assertion |
|------|-----------|
| Resource assignment coverage | Every region has slot 1 filled. No slot 1 = 255. |
| Terrain-primary mapping | Plains→Grain, Forest→Timber, Mountains→Ore, Coast→Fish, Desert→Exotic, Tundra→Exotic, River→Grain, Hills→Grain. All 8 terrains covered. |
| Yield formula per class | Given fixed inputs (base=1.0, season=Autumn, climate=TEMPERATE, soil=0.8, water=0.7), assert expected output for each of 5 resource classes. |
| Depletion math | Starting reserves=1.0, N turns extraction at full workers. Reserves decrease linearly. Ramp kicks in at 0.25. Exhaustion floor at reserves < 0.01. |
| Season clock | `turn % 12 → season`, `season // 3 → season_id`. Boundary: turn 2 → Spring close, turn 3 → Summer open. |
| Famine trigger | Food yield 0.01 below threshold → FAMINE event. Food yield 0.01 above → no event. |
| Salt exemption | Salt after 500 turns extraction: reserves still 1.0. |
| Multi-food fallback | Coast with Fish + Botanicals: famine reads max(Fish yield, Botanicals yield). |
| ecology_mod correctness | Crop soil=0.5, water=0.6 → 0.3. Timber forest=0.4 → 0.4. Ore → 1.0. |
| Subsistence baseline | Mountains (no food slots): food_yield = SUBSISTENCE_BASELINE (0.15), not 0.0. No crash. |
| Subsistence + drought | Mountains during DROUGHT: subsistence × 0.5 = 0.075 < 0.12 → FAMINE. |

### Tier 2: Behavioral Regression (200 Seeds)

Run 200 seeds × 200 turns with `--agents=off`:

| Metric | Acceptance Criterion |
|--------|---------------------|
| Resource distribution | All 8 types appear. No terrain has > 10% empty slot-1 (should be 0%). |
| Seasonal yield range | Grain yield CV across 12-turn cycle ≥ 0.25. |
| Winter mortality | Mean Winter mortality > mean Summer mortality. |
| Depletion timeline | Mineral regions at full exploitation exhaust between turns 80-150. Mean in range, std dev < 20. |
| Famine frequency | DROUGHT phases: 5-15% famine turns. TEMPERATE: < 2%. |
| Aggregate economy regression | Total economy across 200 seeds within ±10% of M23 baseline. |

### Tier 3: Agent-Mode Characterization (Post-M32)

Run 200 seeds × 300 turns with `--agents=shadow`:

| Metric | What It Reveals |
|--------|-----------------|
| Coastal famine resistance | Coast regions ≥ 30% fewer famine events than Plains during drought. |
| Mining boom-bust | Mineral regions show population peak then decline correlated with reserve depletion. |
| Trade hub formation | Regions with 2+ tradeable resources have higher merchant population. |
| Seasonal migration | Winter turns show elevated migration events vs. Summer. |
| Resource satisfaction gradient | Agent satisfaction in high-yield regions > low-yield regions. |

Tier 3 is characterization, not pass/fail. Generates report for M47 calibration. Assertions are directional.

### `--agents=off` Regression Contract

`--agents=off` produces resource yields identically (same Python formula). The difference: agent satisfaction and behavior don't execute. Economy phase reads civ-level resource output (sum of yields across controlled regions). Famine fires identically. Depletion runs identically. No code paths gated behind `--agents` flag in the ecology tick.

---

## Constants

All `[CALIBRATE]` for M47:

| Constant | Default | Purpose |
|----------|---------|---------|
| `RESOURCE_BASE[8]` | 1.0 (all types) | Base yield per resource type. Uniform starting point; modifier tables are the primary levers. |
| `SEASON_MOD[8][4]` | See season table | Season × resource yield modifier |
| `CLIMATE_MOD[5][4]` | See climate table | Class × climate phase yield modifier |
| `DEPLETION_RATE` | ~0.009 | Per-turn mineral reserve drain at full exploitation |
| `SUBSISTENCE_BASELINE` | 0.15 | Food floor for non-food terrains (Mountains, some Forests). Above famine threshold (0.12) in temperate; below in drought (0.075). |
| `FAMINE_YIELD_THRESHOLD` | 0.12 | Below this food yield → famine event. Sits below normal Winter Grain (0.168 at healthy ecology) but above drought Winter Grain (0.084). |
| `PEAK_YIELD` | 1.0 | Yield ceiling for satisfaction normalization. Autumn Grain peak (~0.84) maps to sat ~0.82; normal Winter Grain (0.168) maps to sat ~0.05. |

Note: `WINTER_MIGRATION_BOOST` removed from M34 scope — it is a forward hook for M32 to optionally wire. Defining it here would imply M34 must set it, contradicting the "optional" designation. The `season_id` field on RegionState provides the data; M32 decides whether to use it.

---

## File Changes

| File | Change | Lines (est.) |
|------|--------|-------------|
| `resources.py` | Replace `assign_resources()` with deterministic-primary + probabilistic-secondary scheme. Add `ResourceType` int enum (replaces old `Resource` str enum), terrain mapping tables, base yield generation. | ~120 |
| `ecology.py` | Extend `tick_ecology()`: compute season, yield formula per resource per region, famine trigger migration (replaces `water < 0.20` sentinel), resource suspension check. Add season/climate modifier tables. | ~160 |
| `models.py` | Add `resource_types`, `resource_base_yields`, `resource_reserves` to Region model. Keep `specialized_resources` as deprecated (auto-populated from `resource_types` for backward compat; removed in M47). Add `ResourceType` int enum. Split `resource_suspensions: dict[str, int]` into `resource_suspensions: dict[int, int]` + `route_suspensions: dict[str, int]`. | ~30 |
| `agent_bridge.py` | Extend Arrow RecordBatch schema with resource/season columns. | ~20 |
| `region.rs` | Add `resource_types`, `resource_yields`, `resource_reserves`, `season`, `season_id` to RegionState. | ~15 |
| `satisfaction.rs` | Add `resource_satisfaction()`, `trade_satisfaction()`. Wire into farmer/merchant satisfaction. | ~40 |
| `tech.py` | Migrate `RESOURCE_REQUIREMENTS` from old `Resource` enum to new `ResourceType` IDs. `IRON` → `ORE`, `FUEL` → `TIMBER`, `STONE` → `ORE`, `RARE_MINERALS` → `PRECIOUS`. | ~15 |
| `tech_focus.py` | Migrate `_count_resource()` to read `resource_types` list instead of `specialized_resources`. | ~10 |
| `simulation.py` | Migrate trade route economy calculations to use `resource_types` and `resource_yields` instead of `specialized_resources`. | ~15 |
| `emergence.py` | Migrate barren-region check from `len(specialized_resources) == 0` to `resource_types[0] == 255`. Resource discovery event assigns new resource type IDs. | ~15 |
| `scenario.py` | Support both old string-based and new int-based resource overrides for backward compat. | ~10 |
| `climate.py` | Wildfire writes `ResourceType.TIMBER` to `resource_suspensions` (int key). Sandstorm writes `"trade_route"` to `route_suspensions` (string key). | ~10 |
| Tests (Python) | Tier 1 unit tests, Tier 2 regression harness. | ~150 |
| Tests (Rust) | Satisfaction formula unit tests. | ~30 |

**Total:** ~475 lines Python, ~85 lines Rust, ~180 lines tests.

### Legacy Resource System Migration

M34 introduces the new `ResourceType` int enum and `resource_types` list as the canonical resource system. The old `Resource` string enum and `specialized_resources` field are **deprecated but retained** in M34 for backward compatibility — `specialized_resources` is auto-populated from `resource_types` via a migration helper at world-gen and scenario load. All internal systems migrate to read `resource_types`; `specialized_resources` is removed in M47 cleanup. The migration mapping:

| Old `Resource` | New `ResourceType` | Rationale |
|----------------|-------------------|-----------|
| `GRAIN` | `GRAIN (0)` | Direct mapping |
| `TIMBER` | `TIMBER (1)` | Direct mapping |
| `IRON` | `ORE (5)` | Iron is a mineral ore |
| `FUEL` | `TIMBER (1)` | Fuel was wood/charcoal at pre-industrial tech levels |
| `STONE` | `ORE (5)` | Stone quarrying is mechanically equivalent to mining |
| `RARE_MINERALS` | `PRECIOUS (6)` | Rare minerals map to precious metals/gems |

**`resource_suspensions` split:** The existing `resource_suspensions: dict[str, int]` mixes resource keys (`"timber"`) with non-resource keys (`"trade_route"`). M34 splits this into two clean dicts:

- `resource_suspensions: dict[int, int]` — keyed by `ResourceType` int ID, checked in yield formula
- `route_suspensions: dict[str, int]` — keyed by route name string, checked in trade route calculation

```python
# In tick_ecology, per resource slot:
if resource_type in region.resource_suspensions:
    current_yield = 0.0  # Suspended by disaster

# In trade route calculation:
if "trade_route" in region.route_suspensions:
    # skip this route
```

`climate.py` updated to write `ResourceType.TIMBER` (int) to `resource_suspensions` on wildfire, and `"trade_route"` to `route_suspensions` on sandstorm. The `simulation.py` countdown loop iterates both dicts.

### What Doesn't Change

- `RegionEcology` model — soil/water/forest_cover unchanged
- `terrain.py` — terrain effects unchanged
- `PendingDecisions` struct — same fields
- `behavior.rs` — decision logic unchanged (reads satisfaction, which reads yields)
- Bundle format — stays at current version
- Narrator/curator — no new moment types (harvest events are narrator hooks, not new event categories)

---

## Forward Dependencies

| Milestone | How M34 Enables It |
|-----------|-------------------|
| M35a (Rivers & Trade) | Trade routes become resource-type-aware. Rivers extend trade reach for specific goods. |
| M35b (Disease, Depletion & Events) | Disaster events interact with resource yields (wildfire suspends Timber, flood disrupts Fish). Environmental hazards may occupy resource slots. |
| M41 (Wealth & Markets) | Wealth dispatch must route by resource type — a farmer mining Precious earns at mineral rate, not crop rate. The farmer-as-miner abstraction defers this to M41. |
| M42 (Goods Production) | Stockpile mechanism (deferred from M34) lives here. Autumn surplus carries into Winter. |
| M47 (Tuning Pass) | All `[CALIBRATE]` constants tuned here. Tier 3 characterization report provides starting data. |
