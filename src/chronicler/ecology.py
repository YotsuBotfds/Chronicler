"""Coupled ecology system --- three-variable tick replacing single fertility.

Public API: tick_ecology(), effective_capacity()
No state. All functions operate on WorldState/Region passed in.

M54a: Core ecology math (soil/water/forest ticks, disease severity, resource
yields, depletion feedback) migrated to Rust.  This module retains orchestration,
famine checks, terrain succession helpers, and the effective_capacity formula
used widely by other Python modules.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from chronicler.models import ClimatePhase, Event, FOOD_TYPES, RegionEcology
from chronicler.tuning import (
    K_FAMINE_YIELD_THRESHOLD, K_SUBSISTENCE_BASELINE,
    K_FAMINE_POP_LOSS, K_FAMINE_REFUGEE_POP,
    K_WATER_FACTOR_DENOMINATOR,
    get_override,
)
from chronicler.resources import (
    CLIMATE_CLASS_MOD,
    _CLIMATE_PHASE_INDEX,
)
from chronicler.utils import civ_index

if TYPE_CHECKING:
    from chronicler.models import Region, WorldState

TERRAIN_ECOLOGY_DEFAULTS: dict[str, RegionEcology] = {
    "plains":    RegionEcology(soil=0.90, water=0.60, forest_cover=0.20),
    "forest":    RegionEcology(soil=0.70, water=0.70, forest_cover=0.90),
    "mountains": RegionEcology(soil=0.40, water=0.80, forest_cover=0.30),
    "coast":     RegionEcology(soil=0.70, water=0.80, forest_cover=0.30),
    "desert":    RegionEcology(soil=0.20, water=0.10, forest_cover=0.05),
    "tundra":    RegionEcology(soil=0.15, water=0.50, forest_cover=0.10),
}

TERRAIN_ECOLOGY_CAPS: dict[str, dict[str, float]] = {
    "plains":    {"soil": 0.95, "water": 0.70, "forest_cover": 0.40},
    "forest":    {"soil": 0.80, "water": 0.80, "forest_cover": 0.95},
    "mountains": {"soil": 0.50, "water": 0.90, "forest_cover": 0.40},
    "coast":     {"soil": 0.80, "water": 0.90, "forest_cover": 0.40},
    "desert":    {"soil": 0.30, "water": 0.20, "forest_cover": 0.10},
    "tundra":    {"soil": 0.20, "water": 0.60, "forest_cover": 0.15},
}

_FLOOR_SOIL = 0.05
_FLOOR_WATER = 0.10
_FLOOR_FOREST = 0.00
_MIN_TUNING_DENOMINATOR = 0.001


def effective_capacity(region: Region, world: "WorldState | None" = None) -> int:
    soil = region.ecology.soil
    water_denom = max(
        get_override(world, K_WATER_FACTOR_DENOMINATOR, 0.5) if world else 0.5,
        _MIN_TUNING_DENOMINATOR,
    )
    water_factor = min(1.0, region.ecology.water / water_denom)
    cap_mod = region.capacity_modifier
    return max(int(region.carrying_capacity * cap_mod * soil * water_factor), 1)




def check_food_yield(
    region: "Region",
    yields: list[float],
    climate_phase: "ClimatePhase",
    threshold: float = 0.12,
    subsistence_base: float = 0.15,
) -> bool:
    """Return True if region should enter famine (food yield below threshold)."""
    phase_idx = _CLIMATE_PHASE_INDEX.get(climate_phase.value, 0)
    crop_climate_mod = CLIMATE_CLASS_MOD[0][phase_idx]  # Crop class index = 0

    # Check if region has any food slots
    has_food_slot = any(rtype in FOOD_TYPES for rtype in region.resource_types)

    if has_food_slot:
        # Use max food yield from slots
        food_yield = max(
            (y for rtype, y in zip(region.resource_types, yields) if rtype in FOOD_TYPES),
            default=0.0,
        )
        # Fall back to subsistence if all food slots suspended (e.g., wildfire)
        if food_yield == 0.0:
            food_yield = subsistence_base * crop_climate_mod
    else:
        # Subsistence baseline affected by climate (for non-food terrains)
        food_yield = subsistence_base * crop_climate_mod

    return food_yield < threshold


def _check_famine_yield(
    world: WorldState,
    region_yields: dict[str, list[float]],
    climate_phase: ClimatePhase,
    threshold: float,
    subsistence_base: float,
    acc=None,
) -> list[Event]:
    """M34: Region-level famine check based on food yield."""
    from chronicler.utils import drain_region_pop, sync_civ_population, add_region_pop, clamp, STAT_FLOOR
    from chronicler.emergence import get_severity_multiplier

    events: list[Event] = []
    for region in world.regions:
        if region.controller is None or region.famine_cooldown > 0:
            continue
        if region.population <= 0:
            continue

        yields = region_yields.get(region.name, [0.0, 0.0, 0.0])
        if not check_food_yield(region, yields, climate_phase, threshold, subsistence_base):
            continue  # No famine

        civ = next((c for c in world.civilizations if c.name == region.controller), None)
        if civ is None:
            continue

        # --- Famine effects ---
        mult = get_severity_multiplier(civ, world)

        # C-3 fix: Always apply famine population loss as a direct mutation,
        # not through the accumulator.  "guard" category is skipped in hybrid
        # mode, but refugee additions (below) are always direct mutations.
        # Routing the loss through guard created a conservation violation:
        # hybrid mode gained population (refugees) without the matching loss.
        famine_pop = int(get_override(world, K_FAMINE_POP_LOSS, 5))
        drain_region_pop(region, famine_pop)
        sync_civ_population(civ, world)
        drain = int(get_override(world, "stability.drain.famine_immediate", 3))
        if acc is not None:
            civ_idx = civ_index(world, civ.name)
            acc.add(civ_idx, civ, "stability", -int(drain * mult), "signal")
        else:
            civ.stability = clamp(civ.stability - int(drain * mult), STAT_FLOOR["stability"], 100)
        region.famine_cooldown = 5

        for adj_name in region.adjacencies:
            adj = next((r for r in world.regions if r.name == adj_name), None)
            if adj and adj.controller and adj.controller != civ.name:
                neighbor = next((c for c in world.civilizations if c.name == adj.controller), None)
                if neighbor:
                    refugee_pop = int(get_override(world, K_FAMINE_REFUGEE_POP, 5))
                    add_region_pop(adj, refugee_pop)
                    sync_civ_population(neighbor, world)
                    neighbor_mult = get_severity_multiplier(neighbor, world)
                    if acc is not None:
                        neighbor_idx = civ_index(world, neighbor.name)
                        acc.add(neighbor_idx, neighbor, "stability", -int(5 * neighbor_mult), "signal")
                    else:
                        neighbor.stability = clamp(neighbor.stability - int(5 * neighbor_mult), STAT_FLOOR["stability"], 100)

        events.append(Event(
            turn=world.turn, event_type="famine", actors=[civ.name],
            description=f"Famine strikes {region.name}, devastating {civ.name}.",
            importance=8,
        ))
    return events


def _update_ecology_counters(world: WorldState) -> None:
    """Update low_forest_turns and forest_regrowth_turns for terrain succession."""
    for region in world.regions:
        if region.ecology.forest_cover < 0.2:
            region.low_forest_turns += 1
        else:
            region.low_forest_turns = 0
        if region.ecology.forest_cover > 0.35 and region.population < 5:
            region.forest_regrowth_turns += 1
        else:
            region.forest_regrowth_turns = 0


def disease_vector_label(region: "Region") -> str:
    """Derive disease vector label for narration. Not stored — deterministic."""
    if region.terrain == "desert":
        return "cholera"
    elif region.disease_baseline >= 0.02:
        return "fever"
    else:
        return "plague"


def _collect_pandemic_mask(world: "WorldState") -> list[bool]:
    """Build per-region bool mask: True if region has an active pandemic."""
    pandemic_regions: set[str] = set()
    if hasattr(world, "pandemic_state"):
        for p in world.pandemic_state:
            pandemic_regions.add(p.region_name)
    return [r.name in pandemic_regions for r in world.regions]


def _collect_army_arrived_mask(world: "WorldState") -> list[bool]:
    """Build per-region bool mask: True if military agents migrated in last turn."""
    mask = [False] * len(world.regions)
    prev_turn = world.turn - 1
    if hasattr(world, "agent_events_raw") and world.agent_events_raw:
        for e in world.agent_events_raw:
            if (e.event_type == "migration"
                    and e.occupation == 1
                    and e.turn == prev_turn
                    and 0 <= e.target_region < len(mask)):
                mask[e.target_region] = True
    return mask


_TERRAIN_FROM_U8 = {0: "plains", 1: "mountains", 2: "coast", 3: "forest", 4: "desert", 5: "tundra"}


def _write_back_ecology(world: "WorldState", region_batch) -> dict[str, list[float]]:
    """Write Rust ecology tick results back onto Python Region models.

    Returns {region_name: [yield0, yield1, yield2]} for famine checks.
    """
    region_yields: dict[str, list[float]] = {}
    n = region_batch.num_rows
    soils = region_batch.column("soil").to_pylist()
    waters = region_batch.column("water").to_pylist()
    forests = region_batch.column("forest_cover").to_pylist()
    severities = region_batch.column("endemic_severity").to_pylist()
    prev_waters = region_batch.column("prev_turn_water").to_pylist()
    soil_streaks = region_batch.column("soil_pressure_streak").to_pylist()
    over0 = region_batch.column("overextraction_streak_0").to_pylist()
    over1 = region_batch.column("overextraction_streak_1").to_pylist()
    over2 = region_batch.column("overextraction_streak_2").to_pylist()
    res0 = region_batch.column("resource_reserve_0").to_pylist()
    res1 = region_batch.column("resource_reserve_1").to_pylist()
    res2 = region_batch.column("resource_reserve_2").to_pylist()
    ey0 = region_batch.column("resource_effective_yield_0").to_pylist()
    ey1 = region_batch.column("resource_effective_yield_1").to_pylist()
    ey2 = region_batch.column("resource_effective_yield_2").to_pylist()
    cy0 = region_batch.column("current_turn_yield_0").to_pylist()
    cy1 = region_batch.column("current_turn_yield_1").to_pylist()
    cy2 = region_batch.column("current_turn_yield_2").to_pylist()

    for i in range(n):
        if i >= len(world.regions):
            break
        region = world.regions[i]

        # H-16: Validate/clamp Rust ecology write-back values to [0.0, 1.0]
        # and respect terrain-specific caps
        caps = TERRAIN_ECOLOGY_CAPS.get(region.terrain, TERRAIN_ECOLOGY_CAPS["plains"])
        region.ecology.soil = max(_FLOOR_SOIL, min(caps["soil"], max(0.0, soils[i])))
        region.ecology.water = max(_FLOOR_WATER, min(caps["water"], max(0.0, waters[i])))
        region.ecology.forest_cover = max(_FLOOR_FOREST, min(caps["forest_cover"], max(0.0, forests[i])))
        # These fields are on Region, not RegionEcology
        region.endemic_severity = severities[i]
        region.prev_turn_water = prev_waters[i]
        region.soil_pressure_streak = soil_streaks[i]
        region.overextraction_streaks = {0: over0[i], 1: over1[i], 2: over2[i]}
        region.resource_reserves = [res0[i], res1[i], res2[i]]
        region.resource_effective_yields = [ey0[i], ey1[i], ey2[i]]
        region.resource_current_yields = [cy0[i], cy1[i], cy2[i]]
        region_yields[region.name] = [cy0[i], cy1[i], cy2[i]]

    return region_yields


def _materialize_ecology_events(event_batch, world: "WorldState") -> list[Event]:
    """Convert Rust ecology event batch rows into Python Event objects."""
    events: list[Event] = []
    if event_batch.num_rows == 0:
        return events
    etypes = event_batch.column("event_type").to_pylist()
    rids = event_batch.column("region_id").to_pylist()
    # slots and magnitudes available but not needed for Event construction
    for i in range(event_batch.num_rows):
        rid = rids[i]
        region = world.regions[rid] if rid < len(world.regions) else None
        controller = region.controller if region else None
        actors = [controller] if controller else []
        rname = region.name if region else f"region_{rid}"
        if etypes[i] == 0:
            events.append(Event(
                turn=world.turn,
                event_type="soil_exhaustion",
                actors=actors,
                description=f"The fields of {rname} show signs of exhaustion from decades of intensive cultivation",
                importance=6,
            ))
        elif etypes[i] == 1:
            events.append(Event(
                turn=world.turn,
                event_type="resource_depletion",
                actors=actors,
                description=f"Overextraction has degraded {rname}'s resources",
                importance=7,
            ))
    return events


# ---- Climate phase to u8 mapping for FFI ----
_CLIMATE_PHASE_TO_U8 = {"temperate": 0, "warming": 1, "drought": 2, "cooling": 3}


def tick_ecology(world: WorldState, climate_phase: ClimatePhase, acc=None,
                 ecology_runtime=None) -> list[Event]:
    """Phase 9 ecology tick.

    Delegates the core ecology math to Rust via ecology_runtime
    (AgentSimulator or EcologySimulator), then runs Python-only post-pass
    (famine, refugees, soil floor, counters, terrain succession).

    If ecology_runtime is None, creates a transient EcologySimulator
    automatically (used by tests and simple callers).
    """
    if ecology_runtime is None:
        ecology_runtime = _make_transient_ecology_runtime(world)
    return _tick_ecology_rust(world, climate_phase, acc, ecology_runtime)


def _make_transient_ecology_runtime(world: "WorldState"):
    """Create and initialize a one-shot EcologySimulator for this tick.

    Used when tick_ecology is called without an explicit ecology_runtime
    (e.g., tests, simple scripts).  Creates the simulator, syncs region
    state, and configures river topology + ecology config.
    """
    from chronicler_agents import EcologySimulator
    from chronicler.agent_bridge import build_region_batch, configure_ecology_runtime

    eco_sim = EcologySimulator()
    # Wire river topology and ecology config from tuning overrides
    configure_ecology_runtime(eco_sim, world)
    # Sync region state
    eco_sim.set_region_state(build_region_batch(world))
    return eco_sim


def _tick_ecology_rust(world: WorldState, climate_phase: ClimatePhase, acc,
                       ecology_runtime) -> list[Event]:
    """Rust-backed ecology tick with Python post-pass."""
    # 1. Rust ecology tick
    climate_u8 = _CLIMATE_PHASE_TO_U8.get(climate_phase.value, 0)
    pandemic_mask = _collect_pandemic_mask(world)
    army_arrived_mask = _collect_army_arrived_mask(world)
    region_batch, event_batch = ecology_runtime.tick_ecology(
        world.turn, climate_u8, pandemic_mask, army_arrived_mask,
    )

    # 2. Write-back to Python Region (also sets region.resource_current_yields)
    region_yields = _write_back_ecology(world, region_batch)

    # 3. Materialize Rust ecology events
    rust_events = _materialize_ecology_events(event_batch, world)

    # 4. Python famine / soil floor / counters / terrain succession / population sync
    from chronicler.resources import get_season_id
    season_id = get_season_id(world.turn)

    subsistence_base = get_override(world, K_SUBSISTENCE_BASELINE, 0.15)
    famine_threshold = get_override(world, K_FAMINE_YIELD_THRESHOLD, 0.12)

    # Match pre-M54a semantics: abandoned regions do not cool down while uncontrolled.
    for region in world.regions:
        if region.controller is None:
            continue
        if region.famine_cooldown > 0:
            region.famine_cooldown -= 1

    famine_events = _check_famine_yield(
        world, region_yields, climate_phase, famine_threshold, subsistence_base, acc,
    )

    from chronicler.traditions import apply_soil_floor
    apply_soil_floor(world)

    _update_ecology_counters(world)

    # Terrain succession (was previously a separate call after tick_ecology in simulation.py)
    from chronicler.emergence import tick_terrain_succession
    terrain_events = tick_terrain_succession(world)

    from chronicler.utils import sync_all_populations
    sync_all_populations(world)

    # M35b: Store post-tick water for next turn's delta detection
    for region in world.regions:
        region.prev_turn_water = region.ecology.water

    # 5. Narrow post-pass patch back to Rust
    from chronicler.agent_bridge import build_region_postpass_patch_batch
    patch = build_region_postpass_patch_batch(world)
    ecology_runtime.apply_region_postpass_patch(patch)

    return famine_events + rust_events + terrain_events


def clamp_ecology(region: Region) -> None:
    """Clamp ecology values to terrain-specific floors and caps.

    Extracted as a public helper for use by scenario.py river bonuses.
    The core ecology tick in Rust handles clamping internally; this is
    only needed for one-off Python mutations (e.g., scenario setup).
    """
    caps = TERRAIN_ECOLOGY_CAPS.get(region.terrain, TERRAIN_ECOLOGY_CAPS["plains"])
    region.ecology.soil = max(_FLOOR_SOIL, min(caps["soil"], round(region.ecology.soil, 4)))
    region.ecology.water = max(_FLOOR_WATER, min(caps["water"], round(region.ecology.water, 4)))
    region.ecology.forest_cover = max(_FLOOR_FOREST, min(caps["forest_cover"], round(region.ecology.forest_cover, 4)))
