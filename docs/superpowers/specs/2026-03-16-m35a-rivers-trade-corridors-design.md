# M35a: Rivers & Trade Corridors

> **Status:** Design approved. Ready for implementation planning.
>
> **Depends on:** M34 (resources & seasons) for resource assignment (Fish slot), ecology stats (soil/water/forest_cover), and carrying capacity. M32 (utility-based decisions) for migration utility integration.
>
> **Scope:** Named river systems as a geographic adjacency layer, upstream-downstream ecological coupling, migration preference along river corridors. ~150 lines across 7 files (Python + Rust).

---

## Overview

M34 introduced concrete resources and seasonal yields, but the landscape is flat — every region relates to its neighbors only through terrain adjacency. Rivers are the most important geographic feature missing: historically, they determined where civilizations formed, how they traded, and how environmental damage cascaded across regions.

M35a adds rivers as a **second relationship layer** on top of terrain adjacency. Rivers are named, ordered paths of regions (headwaters → delta) that provide ecological bonuses, create migration corridors, and couple upstream and downstream regions through deforestation cascading. Rivers don't modify the adjacency graph — they add information to existing adjacency relationships.

**Design principle:** Rivers are immutable topology. The water that flows through them varies (via M34's ecology stats), but the river's existence and connectivity are fixed at world-gen. Dynamic river changes (drying, shifting course) are deferred — if narratively compelling, they slot into M35b's environmental events without requiring the adjacency structure itself to be mutable.

---

## Design Decisions

### Named River Paths, Not Pure Adjacency

Each river is a named entity with an ordered list of regions it passes through. Position in the list implies upstream/downstream direction.

**Why named rivers:** Narrative identity is essential. "The Amber River flooded" is a curator event with a name. "River adjacency bit 3 flooded" is debug output. Named rivers give the narrator and the curator something to work with for free — river names are scenario-defined alongside the region path, so each scenario's geography has character.

**Why ordered paths:** An ordered region list `[R3, R7, R12, R5]` means R3 is the headwaters and R5 is the delta. Upstream/downstream queries are just index comparisons — no elevation model, no per-edge annotations. The deforestation cascade becomes trivial: iterate the list, any region with `forest_cover < 0.2` propagates water loss to all regions at higher indices.

**Why not per-segment metadata:** Per-segment navigability, width, etc. (option C during brainstorming) is premature. M42/M43 can derive what they need from the river's region list and the regions' own terrain properties. A narrow mountain gorge segment doesn't need a `width: f32` — it's implied by the terrain type of the regions at each end. If M43 genuinely needs segment metadata, it can extend the river struct at that point without invalidating M35a's design.

### River ID Bitmask, Not Region-Adjacency Bitmask

The `river_mask: u32` on `RegionState` represents **which rivers touch this region** (bit N = part of river N), not which other regions are river-connected. With named rivers, a typical scenario has 3–6 rivers, so the bitmask tells you which rivers are present at a region. The river's ordered region list tells you who's upstream and downstream.

A region at the confluence of two rivers (e.g., bit 0 and bit 2 set) is identifiable via `popcount(river_mask) > 1`. The 32-river cap is generous enough to never matter in practice — upgrading to `u64` is a one-line change if needed.

### Rivers Follow Existing Adjacency

Consecutive regions in a river path must be terrain-adjacent. Rivers are a subset of the existing adjacency graph, not a superset. Validation at scenario load rejects non-adjacent consecutive path entries.

**Why not create new adjacency:** M35a's two consumers — ecological cascade and migration preference — neither require non-adjacent connections. The cascade iterates the river's region list regardless of terrain adjacency (it's a Python-side computation, not a graph traversal). Migration only considers terrain-adjacent regions and boosts river-connected ones via utility bonus. Creating new adjacency edges would mean the river is doing double duty as both a geographic feature and a topology modifier, complicating everything downstream.

**Forward note:** When M42/M43 need goods to flow along rivers bypassing terrain adjacency for transport, they can treat the river's region path as a transport route without retroactively changing M35a's adjacency model.

### Scenario-Defined Only, No Procedural Generation

Each scenario config lists its rivers explicitly. World-gen reads the list and assigns `river_mask` bits. No procedural river placement.

**Why not procedural:** Chronicler's scenarios are authored artifacts, not procedurally generated worlds. The scenario author already places regions, assigns terrain types, defines adjacency, and (after M34) controls resource assignment probabilities. Rivers are geography — they belong in the same authored layer. A scenario author who hand-places a mountain range and a coastal delta knows where the river should run between them.

If Chronicler ever gets a random map generator, river placement would be part of that system — but it would be a world-gen feature, not an M35a feature.

### Confluence: Bonuses Once, Cascades Union

When a region sits at the junction of two rivers (`popcount(river_mask) > 1`):

- **Bonuses don't stack.** A confluence region gets river bonuses once (+0.15 water, +20% capacity, Fish). All bonus checks use `river_mask != 0`, not per-river iteration.
- **Cascades union.** The region is downstream on both rivers, so it receives water loss from either river's upstream deforestation. Two different deforested regions on different rivers both penalize a shared confluence. A `(source, target)` dedup set prevents the same deforested source from double-penalizing through two shared rivers.

**Why union, not max:** The cascade union creates a natural geographic pressure gradient. Headwater regions are ecologically safe (nothing upstream). Mid-river regions are moderately exposed. Confluence regions are the most vulnerable — fertile and productive, but one careless civ deforesting upstream on either tributary can hurt them. That asymmetry drives interesting strategic behavior without special-case code.

### Migration Preference via Utility Bonus, Not Extended Adjacency

Agents get a flat `+RIVER_MIGRATION_BONUS` (+0.1 `[CALIBRATE]`) when evaluating river-connected neighboring regions for migration. This nudges agents toward river corridors without forcing them.

**Why not a threshold reduction:** A separate threshold mechanism would create a decision path bypassing M32's utility framework. A utility bonus composes with personality modifiers from M33, seasonal push from M34, and everything else downstream. One system, one tuning surface.

**Why not extended adjacency:** Long-distance river migration (jumping from headwaters to delta) is narratively correct but mechanically wrong for M35a. It belongs in M42/M43 where trade routes carry passengers alongside cargo.

**Directional neutrality:** The bonus applies equally to upstream and downstream river neighbors. Agents preferentially flow downstream to deltas and confluences not because the bonus is directional, but because those regions have better base conditions (higher water, higher carrying capacity, more resources). The downstream population flow is emergent from composing M34 ecology with M35a bonuses.

---

## River Definition Format

### Scenario Config

```json
"rivers": [
    {"name": "Amber River", "path": [3, 7, 12, 5]},
    {"name": "Iron Creek", "path": [8, 14, 11]}
]
```

Index 0 in the path is headwaters, last index is delta. World-gen assigns `river_mask` bits: Amber River = bit 0, Iron Creek = bit 1, etc., in definition order.

### Validation at Scenario Load

- Every region ID in a river path must exist in the scenario's region list
- Consecutive regions in the path must be terrain-adjacent
- Max 32 rivers per scenario (u32 bitmask limit)
- River path length must be 2–32 regions (minimum 2 to form a connection)

---

## World-Gen Bonuses

Applied once during world-gen, after M34's `assign_resources()`:

### Water Baseline

For each region where `river_mask != 0`, add `+RIVER_WATER_BONUS` (+0.15 `[CALIBRATE]`) to initial water value. Clamped to [0.0, 1.0].

This is a geographic fact — river regions start wetter. The ecology tick's existing water recovery/loss dynamics operate on this higher baseline naturally. During drought, river regions still lose water, but they start from a higher point, so they cross danger thresholds later. Drought resistance is emergent from the higher baseline, not a special-case per-tick guard.

### Carrying Capacity

For each region where `river_mask != 0`, multiply carrying capacity by `RIVER_CAPACITY_MULTIPLIER` (1.2 `[CALIBRATE]`). Applied once, wherever capacity is currently set. Bonus does not stack for confluence regions — applied based on `river_mask != 0`, not per-river.

### Fish Resource

After M34's `assign_resources()`, for each region where `river_mask != 0`:

- If Fish is already in the region's resource slots: skip
- If an empty slot exists: assign Fish
- If all 3 slots are full: skip (don't displace existing resources)

A Mountain region on a river (gorge) with `[Ore, Precious, Salt]` filling all 3 slots keeps its original resources. Mountain rivers are for water and trade, not fishing. The +0.15 water baseline still applies.

### What Doesn't Happen

- No per-tick bonus reapplication — the higher water baseline is a starting condition, not a perpetual buff
- No double bonuses at confluences — all checks use `river_mask != 0`
- No forced Fish on full-slot regions — mountain gorges keep their Ore/Precious/Salt

---

## Upstream-Downstream Ecological Cascade

Computed per-tick in ecology phase (Phase 9), after existing soil/water/forest updates.

### Mechanism

For each river in `world.rivers`, walk the path from headwaters to delta. Any region with `forest_cover < DEFORESTATION_THRESHOLD` (0.2 `[CALIBRATE]`) inflicts water loss on all downstream regions (higher indices in the path).

### Computation

```python
seen: set[tuple[int, int]] = set()  # (source_region, target_region) dedup
for river in world.rivers:
    for i, region_id in enumerate(river.path):
        region = region_map[region_id]
        if region.ecology.forest_cover < DEFORESTATION_THRESHOLD:
            for downstream_id in river.path[i+1:]:
                if (region_id, downstream_id) not in seen:
                    seen.add((region_id, downstream_id))
                    region_map[downstream_id].ecology.water -= DEFORESTATION_WATER_LOSS
```

### Deduplication

The dedup key is `(source_region_id, target_region_id)`. This ensures:

- A given deforested region penalizes a given downstream region **only once**, even if they share multiple rivers
- Two **different** deforested regions on different rivers **both** penalize a shared downstream region (cascades union)

### Cascade Properties

- **Instant** — no multi-turn propagation delay. Consistent with the ecology system's instantaneous behavior for all other effects.
- **Water clamped** to [0.0, 1.0] after all cascade losses applied. Double-cascade at a confluence naturally can't push below zero.
- **Threshold effect, not proportional** — only triggers on `forest_cover < 0.2`. Moderate forestry (logging down to 0.25) is safe; dropping below 0.2 hits hard. This creates a strategic cliff that civs can learn to respect or ignore at their peril.
- **Headwater regions are immune** (nothing upstream). Delta regions are most exposed.

---

## Migration Preference

Implemented in Rust, in the `migration_opportunity` pre-computation on `RegionStats`.

### Mechanism

When building `migration_opportunity` for each region, candidate neighboring regions that share a river with the source region get `+RIVER_MIGRATION_BONUS` (+0.1 `[CALIBRATE]`) added to their attractiveness score before selecting `best_migration_target`.

### River-Sharing Test

```rust
source.river_mask & candidate.river_mask != 0
```

A single bitwise AND — no river path lookup needed at migration time. Source and candidate must both have `river_mask != 0` and share at least one river.

### What Changes in Rust

- `behavior.rs`: In migration target evaluation loop, after computing base attractiveness for each neighbor, check river-sharing condition and add bonus if true
- New constant: `RIVER_MIGRATION_BONUS: f32 = 0.1`

### What Doesn't Change

- Adjacency graph — rivers don't create new migration edges
- Decision framework — no new utility function, no threshold changes
- Agent struct — no river-awareness per agent, it's all in region-level pre-computation

### Emergent Behavior

River valleys fill up organically. Agents along a river corridor preferentially migrate downstream toward deltas and confluences (which tend to have better conditions + river bonus). Population centers form at river junctions and fertile lowlands without any special-case code.

---

## Data Model

### River Struct (Python-side, `models.py`)

```python
class River:
    name: str           # "Amber River" — narrative identity
    path: list[int]     # Region indices, ordered headwaters → delta
```

Stored on `WorldState` as `rivers: list[River]`. The ecology tick needs river iteration for cascade computation, and the curator/narrator needs river names for events.

### Rust-Side RegionState Extension

```rust
// Added to RegionState (region.rs)
pub river_mask: u32,  // Bit N set = region is part of river N
```

Total addition: 4 bytes per region. At ~150 regions: ~600 bytes. Negligible.

### FFI Extension

`ffi.rs` reads the `river_mask` column from the Arrow RecordBatch into `RegionState`. No new FFI mechanism — just one additional column.

### Data Flow Per Turn

```
Phase 9 (tick_ecology):
  1. Existing soil/water/forest updates run first
  2. Upstream deforestation cascade:
     - For each river, walk path headwaters → delta
     - Deforested upstream regions (forest_cover < 0.2) inflict water loss downstream
     - Dedup via (source, target) seen set
  3. Water clamped to [0.0, 1.0]
  4. Resource yields computed (M34) — now reflecting river water bonuses and cascade losses

agent_bridge.py:
  - river_mask column added to RecordBatch schema
  - No new FFI mechanism — just wider RecordBatch

Rust agent tick:
  - behavior.rs reads river_mask for migration attractiveness bonus
  - satisfaction.rs unchanged — river effects are indirect through better water/capacity/yields
```

---

## Constants

All `[CALIBRATE]` for M47:

| Constant | Default | Location | Purpose |
|----------|---------|----------|---------|
| `RIVER_WATER_BONUS` | 0.15 | Python (ecology/constants) | Water baseline increase for river regions at world-gen |
| `RIVER_CAPACITY_MULTIPLIER` | 1.2 | Python (simulation/constants) | Carrying capacity multiplier for river regions at world-gen |
| `DEFORESTATION_THRESHOLD` | 0.2 | Python (ecology) | Forest cover below which upstream deforestation cascade triggers |
| `DEFORESTATION_WATER_LOSS` | 0.05 | Python (ecology) | Water loss per deforested upstream region per turn |
| `RIVER_MIGRATION_BONUS` | 0.1 | Rust (behavior.rs) | Migration attractiveness bonus for river-connected neighbors. ~20% of stay-vs-migrate gap (STAY_BASE=0.5, MIGRATE_CAP=1.0) |

Constants location: wherever M34's resource constants land. Follow consistency — don't create a new constants home for 5 values.

---

## File Changes

| File | Change | Lines (est.) |
|------|--------|-------------|
| `models.py` | Add `River` class (name + path). Add `rivers: list[River]` to `WorldState`. | ~10 |
| `scenarios.py` | Parse `"rivers"` from scenario config. Validate: region IDs exist, consecutive regions terrain-adjacent. Assign `river_mask` bits in definition order. | ~40 |
| `simulation.py` | In world-gen: apply water baseline bonus, capacity multiplier, Fish resource assignment for river regions (`river_mask != 0`). | ~30 |
| `ecology.py` | In Phase 9, after soil/water/forest updates: upstream deforestation cascade computation with `(source, target)` dedup. | ~50 |
| `region.rs` | Add `river_mask: u32` field to `RegionState`. | ~3 |
| `behavior.rs` | In migration target evaluation: bitwise AND river-sharing check, add `RIVER_MIGRATION_BONUS` to attractiveness. | ~15 |
| `ffi.rs` | Read `river_mask` column from Arrow RecordBatch into `RegionState`. | ~5 |

**Total: ~150 lines across 7 files.**

### What Doesn't Change

- `agent.rs` — no per-agent river state
- `demographics.rs` — no river effect on birth/death (M35b disease territory)
- `satisfaction.rs` — rivers affect satisfaction indirectly through better water/capacity/resources, not via a direct satisfaction term
- `emergence.py` — no river-specific emergence events in M35a (floods are M35b)
- `narrative.py` / `curator.py` — no new narration hooks needed; river names are available on `WorldState` for M35b events

---

## Validation

### Tier 1: Structural (Unit Tests)

| Test | Assertion |
|------|-----------|
| River assignment | River regions have `river_mask != 0` after world-gen. |
| Water baseline | River regions start with water ≥ `RIVER_WATER_BONUS` higher than equivalent non-river terrain. |
| Carrying capacity | River regions have carrying capacity `1.2×` non-river equivalent. |
| Fish assignment | River regions with empty resource slot get Fish assigned. |
| Full-slot preservation | Full-slot river regions keep original resources (no Fish forced). |
| Confluence bitmask | Confluence regions (2+ rivers) have multiple bits set but receive bonuses only once. |
| Scenario validation: bad ID | Reject river path containing region ID not in scenario. |
| Scenario validation: non-adjacent | Reject river path with non-adjacent consecutive entries. |

### Tier 2: Behavioral (Integration Tests, Multi-Turn Runs)

| Test | Assertion |
|------|-----------|
| Cascade triggers | Deforest upstream region below 0.2 → downstream regions lose water at 0.05/turn. |
| Cascade dedup | Shared upstream region across two rivers penalizes downstream region only once per source. |
| Cascade union | Two different deforested regions on different rivers both penalize shared confluence. |
| No cascade when healthy | All upstream regions `forest_cover ≥ 0.2` → zero cascade water loss. |
| Migration preference | Over N turns, agents migrate along river corridors at measurably higher rate than equivalent non-river paths (statistical — Gumbel noise means individual decisions vary). |
| Water clamp | Cascade losses don't push water below 0.0. |

### Tier 3: Narrative (Scenario Regression, Manual Inspection)

Run default scenario with rivers defined. Verify:

- River valley regions develop higher populations than comparable inland regions
- Upstream deforestation visibly impacts downstream water levels in turn logs
- Migration flow trends along river corridors over 100+ turns

Not automated — these are "does the simulation tell a coherent geographic story" checks.

### What M35a Does NOT Validate (Deferred)

- Disease effects on river regions (M35b)
- Flood events (M35b)
- Trade cost reduction along rivers (M42)
- River-based goods transport (M43)

---

## Forward Dependencies

| Milestone | How M35a Enables It |
|-----------|-------------------|
| M35b (Disease, Depletion & Events) | Flood events target river regions. Water quality (river water baseline) feeds disease severity computation. River names available for environmental event narration. |
| M42 (Goods Production & Trade) | River-connected regions get trade cost reduction (0.5×). Trade routes follow river paths for goods transport. |
| M43 (Supply Chains & Transport) | River paths serve as transport corridors. Can extend `River` struct with per-segment metadata if needed without invalidating M35a's design. |
| M47 (Full System Tuning) | All 5 `[CALIBRATE]` constants tuned here. Tier 2/3 characterization provides starting data. |
