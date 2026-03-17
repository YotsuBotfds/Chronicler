"""Coupled ecology system --- three-variable tick replacing single fertility.

Public API: tick_ecology(), effective_capacity()
No state. All functions operate on WorldState/Region passed in.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from chronicler.models import ClimatePhase, Event, InfrastructureType, RegionEcology
from chronicler.models import EMPTY_SLOT, FOOD_TYPES, MINERAL_TYPES, ResourceType
from chronicler.tuning import (
    K_SOIL_DEGRADATION, K_SOIL_RECOVERY, K_MINE_SOIL_DEGRADATION,
    K_WATER_DROUGHT, K_WATER_RECOVERY,
    K_FOREST_CLEARING, K_FOREST_REGROWTH, K_COOLING_FOREST_DAMAGE,
    K_IRRIGATION_WATER_BONUS, K_IRRIGATION_DROUGHT_MULT,
    K_AGRICULTURE_SOIL_BONUS, K_MECHANIZATION_MINE_MULT,
    K_FAMINE_WATER_THRESHOLD, K_DEPLETION_RATE,
    K_SUBSISTENCE_BASELINE, K_FAMINE_YIELD_THRESHOLD,
    K_DEFORESTATION_THRESHOLD, K_DEFORESTATION_WATER_LOSS,
    K_DISEASE_SEVERITY_CAP, K_DISEASE_DECAY_RATE,
    K_FLARE_OVERCROWDING_THRESHOLD, K_FLARE_OVERCROWDING_SPIKE,
    K_FLARE_ARMY_SPIKE, K_FLARE_WATER_SPIKE, K_FLARE_SEASON_SPIKE,
    K_SOIL_PRESSURE_THRESHOLD, K_SOIL_PRESSURE_STREAK_LIMIT,
    K_OVEREXTRACTION_STREAK_LIMIT, K_OVEREXTRACTION_YIELD_PENALTY,
    K_WORKERS_PER_YIELD_UNIT,
    get_override,
)
from chronicler.resources import (
    CLIMATE_CLASS_MOD, SEASON_MOD,
    _CLIMATE_PHASE_INDEX, resource_class_index,
)

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


def effective_capacity(region: Region) -> int:
    soil = region.ecology.soil
    water_factor = min(1.0, region.ecology.water / 0.5)
    cap_mod = getattr(region, 'capacity_modifier', 1.0)
    return max(int(region.carrying_capacity * cap_mod * soil * water_factor), 1)


def compute_resource_yields(
    region: "Region",
    season_id: int,
    climate_phase: "ClimatePhase",
    worker_count: int,
    world: "WorldState | None" = None,
) -> list[float]:
    """Compute current yield per resource slot. Mutates resource_reserves for minerals."""
    phase_idx = _CLIMATE_PHASE_INDEX.get(climate_phase.value, 0)
    yields = [0.0, 0.0, 0.0]

    for slot in range(3):
        rtype = region.resource_types[slot]
        if rtype == EMPTY_SLOT:
            continue

        # Suspension check
        if rtype in region.resource_suspensions:
            continue

        base = region.resource_base_yields[slot]
        season_mod = SEASON_MOD[rtype][season_id]
        class_idx = resource_class_index(rtype)
        climate_mod = CLIMATE_CLASS_MOD[class_idx][phase_idx]

        # ecology_mod by class
        if class_idx == 0:  # Crop
            ecology_mod = region.ecology.soil * region.ecology.water
        elif class_idx == 1:  # Forestry
            ecology_mod = region.ecology.forest_cover
        else:  # Marine, Mineral, Evaporite
            ecology_mod = 1.0

        # reserve_ramp (minerals only)
        reserve_ramp = 1.0
        if rtype in MINERAL_TYPES:
            reserves = region.resource_reserves[slot]
            # Depletion — only if there are workers and reserves remain
            if reserves > 0.01 and worker_count > 0:
                target_workers = max(1, effective_capacity(region) // 3)
                extraction = base * (worker_count / target_workers)
                depletion_rate = get_override(world, K_DEPLETION_RATE, 0.009) if world else 0.009
                region.resource_reserves[slot] = max(0.0, reserves - extraction * depletion_rate)
            reserves = region.resource_reserves[slot]
            if reserves < 0.01:
                yields[slot] = base * 0.04  # Exhausted trickle
                continue
            reserve_ramp = min(1.0, reserves / 0.25)

        yields[slot] = base * season_mod * climate_mod * ecology_mod * reserve_ramp

    return yields


# Module-level storage for Arrow bridge to read yields after tick_ecology
_last_region_yields: dict[str, list[float]] = {}


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


def _pressure_multiplier(region: Region) -> float:
    eff = effective_capacity(region)
    if eff <= 0:
        return 1.0
    return max(0.1, 1.0 - region.population / eff)


def _tick_soil(region: Region, civ, climate_phase: ClimatePhase, world: WorldState) -> None:
    eff = effective_capacity(region)

    # Degradation: overpopulation
    if region.population > eff:
        rate = get_override(world, K_SOIL_DEGRADATION, 0.005)
        region.ecology.soil -= rate

    # Degradation: active mines
    has_mine = any(
        i.type == InfrastructureType.MINES and i.active for i in region.infrastructure
    )
    if has_mine:
        mine_rate = get_override(world, K_MINE_SOIL_DEGRADATION, 0.03)
        if civ and civ.active_focus == "metallurgy":
            mine_rate *= 0.5
            world.events_timeline.append(Event(
                turn=world.turn, event_type="capability_metallurgy",
                actors=[civ.name],
                description=f"{civ.name} metallurgy reduces mine degradation",
                importance=1,
            ))
        elif civ and civ.active_focus == "mechanization":
            mine_rate *= get_override(world, K_MECHANIZATION_MINE_MULT, 2.0)
        region.ecology.soil -= mine_rate

    # Recovery: pressure-gated
    if region.population < eff * 0.75:
        rate = get_override(world, K_SOIL_RECOVERY, 0.05)
        rate *= _pressure_multiplier(region)
        if civ and civ.active_focus == "agriculture":
            rate += get_override(world, K_AGRICULTURE_SOIL_BONUS, 0.02)
        region.ecology.soil += rate


def _tick_water(region: Region, civ, climate_phase: ClimatePhase, world: WorldState) -> None:
    has_irrigation = any(
        i.type == InfrastructureType.IRRIGATION and i.active for i in region.infrastructure
    )

    # Degradation / phase effects
    if climate_phase == ClimatePhase.DROUGHT:
        rate = get_override(world, K_WATER_DROUGHT, 0.04)
        if has_irrigation:
            rate *= get_override(world, K_IRRIGATION_DROUGHT_MULT, 1.5)
        region.ecology.water -= rate
    elif climate_phase == ClimatePhase.COOLING:
        region.ecology.water -= 0.02
    elif climate_phase == ClimatePhase.WARMING:
        if region.terrain == "tundra":
            region.ecology.water += 0.05

    # Recovery
    if climate_phase == ClimatePhase.TEMPERATE:
        rate = get_override(world, K_WATER_RECOVERY, 0.03)
        rate *= _pressure_multiplier(region)
        region.ecology.water += rate

    # Irrigation bonus (always, not just temperate, but not during drought)
    if has_irrigation and climate_phase != ClimatePhase.DROUGHT:
        bonus = get_override(world, K_IRRIGATION_WATER_BONUS, 0.03)
        bonus *= _pressure_multiplier(region)
        region.ecology.water += bonus


def _tick_forest(region: Region, civ, climate_phase: ClimatePhase, world: WorldState) -> None:
    if region.population > region.carrying_capacity * 0.5:
        rate = get_override(world, K_FOREST_CLEARING, 0.02)
        region.ecology.forest_cover -= rate

    if climate_phase == ClimatePhase.COOLING:
        region.ecology.forest_cover -= get_override(world, K_COOLING_FOREST_DAMAGE, 0.01)

    if region.population < region.carrying_capacity * 0.5 and region.ecology.water >= 0.3:
        rate = get_override(world, K_FOREST_REGROWTH, 0.01)
        rate *= _pressure_multiplier(region)
        region.ecology.forest_cover += rate


def _apply_cross_effects(region: Region) -> None:
    if region.ecology.forest_cover > 0.5:
        region.ecology.soil += 0.01


def _clamp_ecology(region: Region) -> None:
    caps = TERRAIN_ECOLOGY_CAPS.get(region.terrain, TERRAIN_ECOLOGY_CAPS["plains"])
    region.ecology.soil = max(_FLOOR_SOIL, min(caps["soil"], round(region.ecology.soil, 4)))
    region.ecology.water = max(_FLOOR_WATER, min(caps["water"], round(region.ecology.water, 4)))
    region.ecology.forest_cover = max(_FLOOR_FOREST, min(caps["forest_cover"], round(region.ecology.forest_cover, 4)))


def _check_famine_legacy(world: WorldState, acc=None) -> list[Event]:
    """Legacy region-level famine check: water < threshold. Preserved but no longer called."""
    from chronicler.utils import drain_region_pop, sync_civ_population, add_region_pop, clamp, STAT_FLOOR
    from chronicler.emergence import get_severity_multiplier

    events: list[Event] = []
    threshold = get_override(world, K_FAMINE_WATER_THRESHOLD, 0.20)

    for region in world.regions:
        if region.controller is None or region.famine_cooldown > 0:
            continue
        if region.ecology.water >= threshold:
            continue
        if region.population <= 0:
            continue

        civ = next((c for c in world.civilizations if c.name == region.controller), None)
        if civ is None:
            continue

        mult = get_severity_multiplier(civ)
        if acc is not None:
            civ_idx = next(i for i, c in enumerate(world.civilizations) if c.name == civ.name)
            acc.add(civ_idx, civ, "population", -int(5 * mult), "guard")
        else:
            drain_region_pop(region, int(5 * mult))
            sync_civ_population(civ, world)
        drain = int(get_override(world, "stability.drain.famine_immediate", 3))
        if acc is not None:
            civ_idx = next(i for i, c in enumerate(world.civilizations) if c.name == civ.name)
            acc.add(civ_idx, civ, "stability", -int(drain * mult), "signal")
        else:
            civ.stability = clamp(civ.stability - int(drain * mult), STAT_FLOOR["stability"], 100)
        region.famine_cooldown = 5

        for adj_name in region.adjacencies:
            adj = next((r for r in world.regions if r.name == adj_name), None)
            if adj and adj.controller and adj.controller != civ.name:
                neighbor = next((c for c in world.civilizations if c.name == adj.controller), None)
                if neighbor:
                    add_region_pop(adj, 5)
                    sync_civ_population(neighbor, world)
                    if acc is not None:
                        neighbor_idx = next(i for i, c in enumerate(world.civilizations) if c.name == neighbor.name)
                        acc.add(neighbor_idx, neighbor, "stability", -5, "signal")
                    else:
                        neighbor.stability = clamp(neighbor.stability - 5, STAT_FLOOR["stability"], 100)

        events.append(Event(
            turn=world.turn, event_type="famine", actors=[civ.name],
            description=f"Famine strikes {region.name}, devastating {civ.name}.",
            importance=8,
        ))
    return events


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

        # --- Effects below are identical to _check_famine_legacy ---
        mult = get_severity_multiplier(civ)
        if acc is not None:
            civ_idx = next(i for i, c in enumerate(world.civilizations) if c.name == civ.name)
            acc.add(civ_idx, civ, "population", -int(5 * mult), "guard")
        else:
            drain_region_pop(region, int(5 * mult))
            sync_civ_population(civ, world)
        drain = int(get_override(world, "stability.drain.famine_immediate", 3))
        if acc is not None:
            civ_idx = next(i for i, c in enumerate(world.civilizations) if c.name == civ.name)
            acc.add(civ_idx, civ, "stability", -int(drain * mult), "signal")
        else:
            civ.stability = clamp(civ.stability - int(drain * mult), STAT_FLOOR["stability"], 100)
        region.famine_cooldown = 5

        for adj_name in region.adjacencies:
            adj = next((r for r in world.regions if r.name == adj_name), None)
            if adj and adj.controller and adj.controller != civ.name:
                neighbor = next((c for c in world.civilizations if c.name == adj.controller), None)
                if neighbor:
                    add_region_pop(adj, 5)
                    sync_civ_population(neighbor, world)
                    if acc is not None:
                        neighbor_idx = next(i for i, c in enumerate(world.civilizations) if c.name == neighbor.name)
                        acc.add(neighbor_idx, neighbor, "stability", -5, "signal")
                    else:
                        neighbor.stability = clamp(neighbor.stability - 5, STAT_FLOOR["stability"], 100)

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
        if region.ecology.forest_cover > 0.7 and region.population < 5:
            region.forest_regrowth_turns += 1
        else:
            region.forest_regrowth_turns = 0


def compute_disease_severity(
    region: "Region",
    world: "WorldState | None",
    pre_water: float,
    season_id: int = 0,
) -> None:
    """Update region.endemic_severity based on flare triggers or decay.

    Must be called at the top of the ecology tick, before water/soil updates.
    pre_water is the region's current water value at tick start.
    """
    cap = get_override(world, K_DISEASE_SEVERITY_CAP, 0.15) if world else 0.15
    decay_rate = get_override(world, K_DISEASE_DECAY_RATE, 0.25) if world else 0.25
    overcrowding_thresh = get_override(world, K_FLARE_OVERCROWDING_THRESHOLD, 0.8) if world else 0.8
    overcrowding_spike = get_override(world, K_FLARE_OVERCROWDING_SPIKE, 0.04) if world else 0.04
    army_spike = get_override(world, K_FLARE_ARMY_SPIKE, 0.03) if world else 0.03
    water_spike = get_override(world, K_FLARE_WATER_SPIKE, 0.02) if world else 0.02
    season_spike = get_override(world, K_FLARE_SEASON_SPIKE, 0.02) if world else 0.02

    baseline = region.disease_baseline
    severity = region.endemic_severity
    triggered = False

    # --- Overcrowding ---
    if region.carrying_capacity > 0 and region.population > overcrowding_thresh * region.carrying_capacity:
        severity += overcrowding_spike
        triggered = True

    # --- Army passage (previous turn) ---
    if world is not None and hasattr(world, "agent_events_raw") and world.agent_events_raw:
        prev_turn = world.turn - 1
        region_idx = next((i for i, r in enumerate(world.regions) if r is region), None)
        if region_idx is not None:
            army_arrived = any(
                e.event_type == "migration"
                and e.occupation == 1
                and e.target_region == region_idx
                for e in world.agent_events_raw
                if e.turn == prev_turn
            )
            if army_arrived:
                severity += army_spike
                triggered = True

    # --- Water quality: low water on non-desert terrain ---
    if region.terrain != "desert" and pre_water < 0.3:
        severity += water_spike
        triggered = True

    # --- Water quality: inter-turn water drop > 0.1 ---
    if region.terrain != "desert" and region.prev_turn_water >= 0:
        water_delta = region.prev_turn_water - pre_water
        if water_delta > 0.1 and not (pre_water < 0.3):  # Don't double-count with low-water
            severity += water_spike
            triggered = True

    # --- Seasonal peak ---
    is_fever = region.disease_baseline >= 0.02
    is_cholera = region.terrain == "desert"
    if is_fever and not is_cholera and season_id == 1:  # Summer for Fever
        severity += season_spike
        triggered = True
    elif not is_fever and not is_cholera and region.disease_baseline <= 0.01 and season_id == 3:  # Winter for Plague
        severity += season_spike
        triggered = True

    # --- Pandemic skip: don't flare during active M18 pandemic ---
    if world is not None and hasattr(world, "pandemic_state"):
        if any(p.region_name == region.name for p in world.pandemic_state):
            severity = region.endemic_severity  # Reset to pre-trigger value
            triggered = False

    if triggered:
        region.endemic_severity = min(severity, cap)
    else:
        region.endemic_severity -= decay_rate * (region.endemic_severity - baseline)

    # Floor at baseline
    if region.endemic_severity < baseline:
        region.endemic_severity = baseline


def tick_ecology(world: WorldState, climate_phase: ClimatePhase, acc=None) -> list[Event]:
    """Phase 9 ecology tick. Replaces phase_fertility."""
    from chronicler.resources import get_season_id as _get_season_id_fn
    current_season_id = _get_season_id_fn(world.turn)

    for region in world.regions:
        if region.controller is None:
            continue
        civ = next((c for c in world.civilizations if c.name == region.controller), None)
        if civ is None:
            continue

        # M35b: Disease computation — before ecology updates
        pre_water = region.ecology.water
        compute_disease_severity(region, world, pre_water, season_id=current_season_id)

        _tick_soil(region, civ, climate_phase, world)
        _tick_water(region, civ, climate_phase, world)
        _tick_forest(region, civ, climate_phase, world)
        _apply_cross_effects(region)
        _clamp_ecology(region)

        if region.famine_cooldown > 0:
            region.famine_cooldown -= 1

    # Uncontrolled regions: natural recovery + climate effects only (no civ bonuses)
    for region in world.regions:
        if region.controller is not None:
            continue
        # M35b: Disease for uncontrolled regions
        pre_water = region.ecology.water
        compute_disease_severity(region, world, pre_water, season_id=current_season_id)
        # Natural soil recovery (no civ bonuses)
        eff = effective_capacity(region)
        if region.population < eff * 0.75:
            rate = get_override(world, K_SOIL_RECOVERY, 0.05)
            rate *= _pressure_multiplier(region)
            region.ecology.soil += rate
        # Water: climate effects only
        if climate_phase == ClimatePhase.DROUGHT:
            region.ecology.water -= get_override(world, K_WATER_DROUGHT, 0.04)
        elif climate_phase == ClimatePhase.COOLING:
            region.ecology.water -= 0.02
        elif climate_phase == ClimatePhase.WARMING and region.terrain == "tundra":
            region.ecology.water += 0.05
        elif climate_phase == ClimatePhase.TEMPERATE:
            rate = get_override(world, K_WATER_RECOVERY, 0.03)
            rate *= _pressure_multiplier(region)
            region.ecology.water += rate
        # Forest: natural regrowth (water gate applies)
        if region.population < region.carrying_capacity * 0.5 and region.ecology.water >= 0.3:
            rate = get_override(world, K_FOREST_REGROWTH, 0.01)
            rate *= _pressure_multiplier(region)
            region.ecology.forest_cover += rate
        if climate_phase == ClimatePhase.COOLING:
            region.ecology.forest_cover -= get_override(world, K_COOLING_FOREST_DAMAGE, 0.01)
        _apply_cross_effects(region)
        _clamp_ecology(region)

    # --- M35a: Upstream deforestation cascade ---
    if world.rivers:
        deforest_thresh = get_override(world, K_DEFORESTATION_THRESHOLD, 0.2)
        deforest_loss = get_override(world, K_DEFORESTATION_WATER_LOSS, 0.05)
        region_map = {r.name: r for r in world.regions}
        cascade_affected: set[str] = set()
        seen: set[tuple[str, str]] = set()
        for river in world.rivers:
            for i, rname in enumerate(river.path):
                region = region_map[rname]
                if region.ecology.forest_cover < deforest_thresh:
                    for downstream_name in river.path[i + 1:]:
                        if (rname, downstream_name) not in seen:
                            seen.add((rname, downstream_name))
                            region_map[downstream_name].ecology.water -= deforest_loss
                            cascade_affected.add(downstream_name)
        # Phoebe N-1: second clamp pass for cascade-affected regions
        for rname in cascade_affected:
            _clamp_ecology(region_map[rname])

    # --- M34: Compute resource yields for all regions ---
    from chronicler.resources import get_season_id
    season_id = get_season_id(world.turn)
    _last_region_yields.clear()
    subsistence_base = get_override(world, K_SUBSISTENCE_BASELINE, 0.15)
    famine_threshold = get_override(world, K_FAMINE_YIELD_THRESHOLD, 0.12)
    for region in world.regions:
        worker_count = region.population // 5 if region.population > 0 else 0
        yields = compute_resource_yields(region, season_id, climate_phase, worker_count, world)
        _last_region_yields[region.name] = yields

    # M34: Yield-based famine (replaces water-sentinel _check_famine_legacy)
    events = _check_famine_yield(world, _last_region_yields, climate_phase, famine_threshold, subsistence_base, acc)

    from chronicler.traditions import apply_soil_floor
    apply_soil_floor(world)

    _update_ecology_counters(world)

    from chronicler.utils import sync_all_populations
    sync_all_populations(world)

    # M35b: Store post-tick water for next turn's delta detection
    for region in world.regions:
        region.prev_turn_water = region.ecology.water

    return events
