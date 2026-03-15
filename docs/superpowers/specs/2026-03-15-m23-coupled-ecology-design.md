# M23: Coupled Ecology — Design Spec

**Date:** 2026-03-15
**Status:** Draft
**Prerequisites:** P4 (Regional Population) landed; M21, M22 landed
**Estimated size:** ~350 lines production, ~200 lines tests

## Overview

Replace the single `fertility: float` field on Region with a three-variable coupled ecology system: **soil**, **water**, and **forest_cover**. Each variable has distinct degradation sources, recovery mechanics, and cross-effects. The system produces discrete threshold-crossing events (famine, migration, terrain transition) that feed naturally into the M20a curator pipeline and M22 faction influence shifts.

M23 does not modify the curator, faction, or succession systems. It produces richer ecology events; existing downstream consumers (curator scoring, faction shift table, M18 terrain succession) process them without new code.

### Design Principles

1. **One driver per direction per variable.** Each ecology variable has one primary degradation source and one primary recovery source. No stacking of independent systems on the same variable.
2. **Threshold crossings over gradual slopes.** The simulation should produce discrete political moments, not background noise. Threshold-based formulas generate important events that the curator scores highly.
3. **Pressure-gated recovery.** Recovery rate scales inversely with population pressure, preventing mathematical death while keeping active exploitation costly.

## Data Model

### RegionEcology (models.py)

New Pydantic model replacing `fertility`:

```python
class RegionEcology(BaseModel):
    soil: float = Field(default=0.8, ge=0.0, le=1.0)
    water: float = Field(default=0.6, ge=0.0, le=1.0)
    forest_cover: float = Field(default=0.3, ge=0.0, le=1.0)
```

### Region (models.py)

Field changes:

```python
# REMOVE:
fertility: float = Field(default=0.8, ge=0.0, le=1.0)
low_fertility_turns: int = 0

# ADD:
ecology: RegionEcology = Field(default_factory=RegionEcology)
low_forest_turns: int = 0  # M18: consecutive turns with forest_cover < 0.2
forest_regrowth_turns: int = 0  # M18: consecutive turns with forest_cover > 0.7 AND population < 5
```

### TurnSnapshot (models.py)

Field change:

```python
# REMOVE:
fertility: dict[str, float] = Field(default_factory=dict)

# ADD:
ecology: dict[str, dict[str, float]] = Field(default_factory=dict)
# Maps region_name → {"soil": float, "water": float, "forest_cover": float}
```

### TerrainTransitionRule (models.py)

Update existing condition value:

```python
# CHANGE condition from "low_fertility" to "low_forest"
# Update default deforestation rule threshold check accordingly
```

## Terrain Defaults

Initial ecology values assigned in `world_gen.py` based on terrain type:

| Terrain    | soil | water | forest_cover |
|------------|------|-------|--------------|
| plains     | 0.90 | 0.60  | 0.20         |
| forest     | 0.70 | 0.70  | 0.90         |
| mountains  | 0.40 | 0.80  | 0.30         |
| coast      | 0.70 | 0.80  | 0.30         |
| desert     | 0.20 | 0.10  | 0.05         |
| tundra     | 0.15 | 0.50  | 0.10         |

Stored as `TERRAIN_ECOLOGY_DEFAULTS: dict[str, RegionEcology]` in ecology.py.

## Effective Capacity Formula

Single source of truth, replaces `terrain.py:effective_capacity`:

```python
def effective_capacity(region: Region) -> int:
    """Capacity = carrying_capacity × soil × water_factor.

    Water factor uses a threshold model: water only constrains below 0.5.
    Floor of 1 prevents division-by-zero.
    """
    soil = region.ecology.soil
    water_factor = min(1.0, region.ecology.water / 0.5)
    return max(int(region.carrying_capacity * soil * water_factor), 1)
```

The `terrain_fertility_cap` concept is removed. Soil and water have their own ceilings per terrain (see Degradation/Recovery Caps below).

## Variable Interaction Table

### Degradation Sources

| Variable       | Primary driver                | Rate       | Condition                     |
|----------------|-------------------------------|------------|-------------------------------|
| soil           | Population pressure           | -0.005/turn | population > effective_capacity |
| soil           | Tech focus (Metallurgy/Mech.) | -0.03/turn  | active mine in region          |
| water          | Drought climate phase         | -0.04/turn  | climate_phase == DROUGHT       |
| water          | Irrigation drought penalty    | ×1.5       | irrigated region during drought |
| forest_cover   | Population clearing           | -0.02/turn  | population > 0.5 × carrying_capacity |

### Recovery Sources

| Variable       | Primary driver                       | Base rate  | Condition                          |
|----------------|--------------------------------------|------------|------------------------------------|
| soil           | Pressure-gated natural recovery      | +0.05/turn | population < 0.75 × eff_capacity  |
| soil           | Agriculture tech focus bonus         | +0.02/turn | controlling civ has agriculture focus |
| water          | Temperate climate recovery            | +0.03/turn | climate_phase == TEMPERATE            |
| water          | Irrigation infrastructure bonus      | +0.03/turn | active irrigation in region        |
| forest_cover   | Natural regrowth                     | +0.01/turn | population < 0.5 × carrying_capacity |

### Cross-Effects

| Source variable | Target variable | Effect                                          |
|-----------------|-----------------|--------------------------------------------------|
| forest_cover    | soil            | Forest provides soil recovery bonus: +0.01/turn when forest_cover > 0.5 |
| water           | forest_cover    | Low water inhibits forest growth: no forest recovery when water < 0.3 |

### Pressure-Gated Recovery

All recovery rates are multiplied by:

```python
pressure_multiplier = max(0.1, 1.0 - region.population / effective_capacity(region))
```

When population is at capacity, recovery runs at 10% of base rate — not zero, but minimal. When population drops to half capacity, recovery jumps to ~50% of base rate. When abandoned, full recovery. The 0.1 floor prevents mathematical death.

## Variable Floors and Ceilings

### Floors

| Variable       | Floor | Rationale                                          |
|----------------|-------|----------------------------------------------------|
| soil           | 0.05  | Zero soil is mathematically unrecoverable           |
| water          | 0.10  | Zero water stops all events; threshold model needs headroom |
| forest_cover   | 0.00  | True zero is valid — deserts, tundra, steppe        |

### Ceilings (per terrain)

Soil and water have terrain-specific caps that prevent unrealistic values:

| Terrain    | soil_cap | water_cap | forest_cap |
|------------|----------|-----------|------------|
| plains     | 0.95     | 0.70      | 0.40       |
| forest     | 0.80     | 0.80      | 0.95       |
| mountains  | 0.50     | 0.90      | 0.40       |
| coast      | 0.80     | 0.90      | 0.40       |
| desert     | 0.30     | 0.20      | 0.10       |
| tundra     | 0.20     | 0.60      | 0.15       |

Stored as `TERRAIN_ECOLOGY_CAPS` in ecology.py.

## Climate Phase Integration

Climate phases affect water degradation/recovery, replacing the old `climate_degradation_multiplier` on fertility:

| Phase      | Water effect                          | Forest effect                         |
|------------|---------------------------------------|---------------------------------------|
| TEMPERATE  | +0.03/turn recovery                   | No modifier                           |
| WARMING    | Tundra: water +0.05 (melt); Coast: flood risk doubles | Wildfire risk doubles (existing disaster spec) |
| DROUGHT    | -0.04/turn degradation; irrigated ×1.5 | No forest recovery (water < 0.3 cross-effect) |
| COOLING    | -0.02/turn degradation (freezing)     | -0.01/turn (frost damage)             |

The `climate_degradation_multiplier` function is retired. Climate effects are applied directly inside `tick_ecology()` based on phase.

## Irrigation Infrastructure

`InfrastructureType.IRRIGATION` already exists in models.py. M23 changes its mechanical effect:

**Current behavior (phase_fertility):** Irrigation adds +0.15 to fertility cap.

**New behavior (tick_ecology):**
- **Normal conditions:** +0.03/turn water recovery bonus (additive to base recovery)
- **During drought:** Water degradation multiplied by 1.5× in irrigated regions. The infrastructure itself is NOT destroyed — the penalty is on the region while irrigated during drought. The trap is dependence on artificially boosted water, not infrastructure destruction.
- **Build cost:** Unchanged (mid-cost, existing build pipeline)

## Tech Focus Integration (M21)

Entries added to ecology awareness, not to `FOCUS_EFFECTS` table (which handles stat_modifiers and weight_modifiers). The ecology module reads `civ.active_focus` directly:

| Focus          | Ecology effect                                     |
|----------------|----------------------------------------------------|
| AGRICULTURE    | +0.02/turn soil recovery bonus in controlled regions |
| METALLURGY     | Mine soil degradation halved: -0.015/turn (base -0.03 × 0.5, preserving M21 behavior) |
| MECHANIZATION  | Mine soil degradation doubled: -0.06/turn (base -0.03 × 2.0) |

These are checked inside `tick_ecology()` by reading the controlling civ's `active_focus`. No changes to `tech_focus.py` or `FOCUS_EFFECTS`.

**M21 famine threshold interaction:** The current `_check_famine` halves the famine threshold for Agriculture-focused civs (`threshold *= 0.5`). Under M23, famine triggers on water < threshold. **Discard this behavior.** Agriculture's M23 benefit is +0.02/turn soil recovery — a fundamentally different and stronger lever. Halving a water threshold for an agriculture focus mixes metaphors (agriculture helps soil, not water resilience). The one-driver-per-direction principle says water resilience comes from irrigation, not tech focus.

## Faction Integration (M22)

No new code. Ecology-driven famine events already match M22's shift table patterns:

- Famine event → MIL -0.03, MER -0.03, CUL +0.06 (existing shift entry)
- Migration event → existing shift entries for population loss

The richer event stream from M23 (region-level famine instead of civ-level) means more frequent faction pressure, which naturally feeds power struggle dynamics.

## M18 Ecological Succession Migration

### Counter rename

`Region.low_fertility_turns` → `Region.low_forest_turns`

### Trigger update (emergence.py)

**Deforestation** (forest → plains):
- Old: `fertility < 0.3` for `threshold_turns` consecutive turns
- New: `forest_cover < 0.2` for `threshold_turns` consecutive turns

**Rewilding** (plains → forest):
- Old: region depopulated for `threshold_turns`
- New: `forest_cover > 0.7 AND population < 5` for `threshold_turns` consecutive turns

### Counter logic (emergence.py)

```python
def update_low_forest_counters(world: WorldState) -> None:
    for region in world.regions:
        if region.ecology.forest_cover < 0.2:
            region.low_forest_turns += 1
        else:
            region.low_forest_turns = 0
```

### TerrainTransitionRule conditions

Default rules in `WorldState.terrain_transition_rules` (models.py):

**Deforestation rule:** Change `condition="low_fertility"` to `condition="low_forest"`. The `tick_terrain_succession` function matches this string against the counter.

**Rewilding rule:** Change `condition="depopulated"` to `condition="forest_regrowth"`. The `tick_terrain_succession` function handles this as a compound check: `forest_cover > 0.7 AND population < 5` for `threshold_turns` consecutive turns. This requires a new counter `forest_regrowth_turns` on Region (incremented when both conditions met, reset otherwise), OR reuse `low_forest_turns` as a general ecology counter by inverting the meaning based on condition string. **Recommended:** Add `forest_regrowth_turns: int = 0` to Region and update the counter logic in `update_low_forest_counters` (renamed to `update_ecology_counters`) to also track regrowth.

After terrain transition, `_apply_transition` in emergence.py sets ecology values for new terrain:
- Forest → plains: soil=0.5, water unchanged, forest_cover=0.1, low_forest_turns=0
- Plains → forest: soil unchanged, water unchanged, forest_cover=0.7, forest_regrowth_turns=0

## Snapshot Builder (main.py)

`main.py:execute_run` builds `TurnSnapshot` objects each turn. Currently does not populate `fertility` (Pydantic default empty dict). Under M23, add ecology snapshot population:

```python
ecology={r.name: r.ecology.model_dump() for r in world.regions}
```

This provides per-region ecology state for M19 analytics.

## Disaster Fertility Writes Migration

Several disaster and emergence functions directly mutate `region.fertility`. All must be migrated to ecology variables:

| File            | Function              | Current write                    | M23 migration                          |
|-----------------|-----------------------|----------------------------------|----------------------------------------|
| `climate.py`    | `check_disasters`     | earthquake: `fertility -= 0.2`   | `ecology.soil -= 0.2`                  |
| `climate.py`    | `check_disasters`     | flood: `fertility -= 0.1`        | `ecology.water += 0.1` (flood raises water temporarily) |
| `climate.py`    | `check_disasters`     | wildfire: `fertility -= 0.15`    | `ecology.forest_cover -= 0.3` (fire burns forest) |
| `emergence.py`  | `_apply_supervolcano` | `fertility = 0.1`               | `ecology.soil = 0.1, ecology.forest_cover = 0.05` |
| `emergence.py`  | `_apply_tech_accident` | target: `fertility -= 0.3`      | `ecology.soil -= 0.3`                  |
| `emergence.py`  | `_apply_tech_accident` | neighbors: `fertility -= 0.15`  | `ecology.soil -= 0.15`                 |

All clamp to floors after mutation. Disaster effects are one-time shocks, not ongoing ticks — they bypass the pressure-gated recovery system and apply directly.

## Traditions Integration

`apply_fertility_floor` in traditions.py (food_stockpiling tradition) currently sets `fertility >= 0.2`.

**Migration:** Change to set `ecology.soil >= 0.2` for controlled regions of civs with food_stockpiling. Semantically equivalent — food stockpiling protects against soil depletion, not water or forest loss.

## Tuning Keys

### Removed

Remove constants `K_FERTILITY_DEGRADATION`, `K_FERTILITY_RECOVERY`, `K_FAMINE_THRESHOLD` from `tuning.py` and their entries in `KNOWN_OVERRIDES`. Any existing YAML tuning files using these keys will generate warnings from the unknown-key validator.

```
fertility.degradation_rate    → replaced by ecology.soil_degradation_rate
fertility.recovery_rate       → replaced by ecology.soil_recovery_rate
fertility.famine_threshold    → replaced by ecology.famine_water_threshold
```

### Added

```
ecology.soil_degradation_rate         = 0.005
ecology.soil_recovery_rate            = 0.05
ecology.water_drought_rate            = 0.04
ecology.water_recovery_rate           = 0.03
ecology.forest_clearing_rate          = 0.02
ecology.forest_regrowth_rate          = 0.01
ecology.irrigation_water_bonus        = 0.03
ecology.irrigation_drought_multiplier = 1.5
ecology.agriculture_soil_bonus        = 0.02
ecology.mechanization_mine_multiplier = 2.0
ecology.famine_water_threshold        = 0.05
```

All tuning keys registered in `tuning.py:KNOWN_OVERRIDES` and accessible via `get_override()`.

## New Module: ecology.py

### Public API

```python
def tick_ecology(
    world: WorldState,
    climate_phase: ClimatePhase,
) -> list[Event]:
    """Phase 9 ecology tick. Replaces phase_fertility.

    For each controlled region:
    1. Compute pressure_multiplier from population / effective_capacity
    2. Apply degradation (soil from overpop + mines, water from drought, forest from clearing)
    3. Apply recovery (soil pressure-gated + agriculture, water + irrigation, forest regrowth)
    4. Apply cross-effects (forest→soil bonus, water→forest gate)
    5. Clamp to floors and terrain caps
    6. Decrement famine_cooldown
    Returns famine events for regions crossing water threshold.
    """
```

### Internal structure

```python
TERRAIN_ECOLOGY_DEFAULTS: dict[str, RegionEcology]  # Initial values by terrain
TERRAIN_ECOLOGY_CAPS: dict[str, dict[str, float]]    # Per-variable ceilings by terrain

def effective_capacity(region: Region) -> int:
    """Replaces terrain.effective_capacity."""

def _pressure_multiplier(region: Region) -> float:
    """max(0.1, 1.0 - population / effective_capacity)"""

def _tick_soil(region, civ, climate_phase, world) -> None:
    """Soil degradation + recovery + agriculture bonus."""

def _tick_water(region, civ, climate_phase, world) -> None:
    """Water degradation + recovery + irrigation."""

def _tick_forest(region, civ, climate_phase, world) -> None:
    """Forest clearing + regrowth + water gate."""

def _apply_cross_effects(region) -> None:
    """Forest→soil bonus, water→forest gate."""

def _clamp_ecology(region) -> None:
    """Apply floors and terrain caps."""

def _check_famine(world) -> list[Event]:
    """Region-level famine check based on water threshold."""
```

### Famine check migration

Famine currently triggers on `fertility < threshold`. Under M23:
- Famine triggers when `ecology.water < famine_water_threshold` (default 0.05) in a controlled region with population > 0
- Famine events are **region-level**: each affected region emits its own event with the region name in the event description
- Famine cooldown per region is unchanged

## Simulation Phase Integration

### Phase 9 (simulation.py)

```python
# BEFORE (current):
turn_events.extend(phase_fertility(world))
# M18: Terrain succession
from chronicler.emergence import tick_terrain_succession
turn_events.extend(tick_terrain_succession(world))

# AFTER:
from chronicler.ecology import tick_ecology
turn_events.extend(tick_ecology(world, climate_phase))
# M18: Terrain succession (uses low_forest_turns updated by tick_ecology)
from chronicler.emergence import tick_terrain_succession
turn_events.extend(tick_terrain_succession(world))
```

`tick_ecology` calls `update_low_forest_counters` internally before returning, so emergence.py's `tick_terrain_succession` sees the updated counters.

### Infrastructure phase (infrastructure.py)

Remove mine fertility degradation from `tick_infrastructure`. Mine soil degradation is now handled in `ecology.py:_tick_soil` to maintain the one-driver-per-direction principle.

### Effective capacity callers

All callers of `terrain.effective_capacity` must migrate to `ecology.effective_capacity`. Complete list of import sites:

| File              | Sites                                       | Notes                                    |
|-------------------|---------------------------------------------|------------------------------------------|
| `simulation.py`   | line 374, 591, 890 (3 sites)               | phase_fertility removed; other two update |
| `climate.py`      | line 168                                    | migration cascade                        |
| `infrastructure.py` | capacity checks                           | mine degradation moves to ecology.py     |
| `politics.py`     | line 14, 286, 820 (3 sites)               | secession capacity calculations          |
| `factions.py`     | line 437 (`total_effective_capacity`)       | faction influence from capacity           |
| `utils.py`        | line 61 (`add_region_pop`)                 | population helper                         |
| `world_gen.py`    | line 22                                     | initialization                           |
| `scenario.py`     | line 425                                    | scenario override application            |

`terrain.py:effective_capacity` is removed. `terrain.py:terrain_fertility_cap` is removed. `TerrainEffect.fertility_cap` field remains for backward compat in any scenario files but is not used by the simulation.

## Scenario Override Support

`RegionOverride` in scenario.py currently supports `fertility: float | None`. Migration:

```python
# REMOVE:
fertility: float | None = None

# ADD:
ecology: dict[str, float] | None = None
# Keys: "soil", "water", "forest_cover". Partial override supported.
```

Applied in `apply_scenario_overrides`:

```python
if reg_override.ecology is not None:
    for key, value in reg_override.ecology.items():
        setattr(world.regions[target_idx].ecology, key, value)
```

## Backward Compatibility

The Region model change from `fertility: float` to `ecology: RegionEcology` breaks deserialization of existing `state.json` save files. **Old saves are not supported after M23.** No migration validator is needed — the simulation does not support mid-run save/load across milestone boundaries.

## Feedback Loops

Three named feedback loops that M19b analytics should monitor:

### 1. Deforestation Spiral
Population pressure → forest clearing → reduced soil recovery (cross-effect lost) → soil degrades → capacity drops → famine → more pressure on remaining forest

**Natural termination:** Population decline from famine reduces pressure, enabling forest regrowth. Pressure-gated recovery ensures this happens. M19b validates termination within 50–100 turns.

### 2. Irrigation Trap
Civ builds irrigation → water recovery boosted → population grows to match new capacity → drought hits → irrigated regions lose water 1.5× faster → sudden capacity collapse → famine cascade

**Natural termination:** Drought is a climate phase (temporary). Water recovers when drought ends. But population may have grown beyond sustainable levels, creating a post-drought famine even after water returns.

### 3. Mining Collapse
Metallurgy/Mechanization focus + active mines → soil degradation -0.03 to -0.06/turn → soil hits floor → effective capacity crashes → region depopulated → recovery begins (slowly, pressure-gated)

**Natural termination:** Depopulation enables recovery. But if the civ switches focus before soil bottoms out, recovery can begin sooner — creating a strategic tension.

## M19 Validation Gate

**Mandatory.** Do not ship M23 without M19 confirming the coupled system produces better behavior than single-fertility.

### Metrics to compare (200 runs each, before/after):

| Metric                              | Target                                    |
|--------------------------------------|-------------------------------------------|
| Famine frequency per 500 turns       | Higher variance, fewer total (threshold effect) |
| Migration cascade length             | Longer chains (regional famine drives multi-hop migration) |
| Ecology variable distributions       | Soil/water bimodal (healthy vs degraded), not uniform |
| Feedback loop convergence            | All three loops terminate within 100 turns |
| Terrain transition frequency         | Deforestation and rewilding both occur     |
| Faction power struggles from ecology | At least 1 per 500 turns from famine events |

## Test Plan

### Model tests
- RegionEcology fields exist with correct defaults
- Terrain defaults applied correctly in world_gen
- Ecology floors enforced (soil ≥ 0.05, water ≥ 0.10, forest_cover ≥ 0.0)
- Terrain caps enforced

### Effective capacity tests
- `soil=1.0, water=1.0` → full capacity
- `soil=0.5, water=1.0` → half capacity (soil scales linearly)
- `soil=1.0, water=0.25` → half capacity (water threshold at 0.5)
- `soil=1.0, water=0.5` → full capacity (water at threshold = no penalty)
- Floor of 1 always maintained

### Degradation tests
- Overpopulation degrades soil at configured rate
- Drought degrades water at -0.04/turn
- Irrigation amplifies drought penalty by 1.5×
- Population pressure clears forest at -0.02/turn
- Metallurgy halves mine degradation (existing M21 behavior preserved)
- Mechanization doubles mine degradation

### Recovery tests
- Pressure-gated recovery: at-capacity = 10% rate, half-capacity = ~50%, abandoned = 100%
- Agriculture focus adds +0.02/turn soil recovery
- Irrigation adds +0.03/turn water recovery
- Temperate phase enables water recovery
- Forest regrowth when population below 50% carrying capacity

### Cross-effect tests
- Forest > 0.5 provides soil recovery bonus
- Water < 0.3 prevents forest regrowth

### Integration tests
- Famine triggers at water threshold crossing
- Famine events are region-level (each region emits own event)
- M18 terrain succession uses low_forest_turns
- Deforestation at forest_cover < 0.2 for threshold_turns
- Rewilding at forest_cover > 0.7 and population < 5
- food_stockpiling tradition applies soil floor 0.2
- Climate phase changes drive water state transitions

### Feedback loop tests (deterministic seed)
- Deforestation spiral terminates when population drops
- Irrigation trap produces famine spike during drought then recovery
- Mining collapse bottoms soil then recovers after depopulation
