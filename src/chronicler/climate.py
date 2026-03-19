"""Climate cycles, natural disasters, and migration.

Climate phase is a pure function of turn number — no mutable state.
Disasters use hashlib for deterministic probability rolls.
Migration cascades one wave per turn (next-turn continuation, not recursive).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chronicler.models import Civilization, Region, WorldState

from chronicler.models import ClimateConfig, ClimatePhase, Event, InfrastructureType, Disposition, ResourceType
from chronicler.utils import civ_index
from chronicler.emergence import get_severity_multiplier


PHASE_SCHEDULE: list[tuple[float, ClimatePhase]] = [
    (0.0, ClimatePhase.TEMPERATE),
    (0.4, ClimatePhase.WARMING),
    (0.6, ClimatePhase.DROUGHT),
    (0.8, ClimatePhase.COOLING),
]


def get_climate_phase(turn: int, config: ClimateConfig) -> ClimatePhase:
    """Pure function. Deterministic from turn + config."""
    phase_idx = config.phase_offset % len(PHASE_SCHEDULE)
    threshold_shift = int(PHASE_SCHEDULE[phase_idx][0] * config.period)
    shifted_turn = turn + threshold_shift
    position = (shifted_turn % config.period) / config.period
    phase = ClimatePhase.TEMPERATE
    for threshold, p in PHASE_SCHEDULE:
        if position >= threshold:
            phase = p
    return phase


# Base degradation multipliers by terrain x phase.
_BASE_MULTIPLIERS: dict[str, dict[ClimatePhase, float]] = {
    "plains":    {ClimatePhase.TEMPERATE: 1.0, ClimatePhase.WARMING: 1.0, ClimatePhase.DROUGHT: 2.0,  ClimatePhase.COOLING: 1.25},
    "forest":    {ClimatePhase.TEMPERATE: 1.0, ClimatePhase.WARMING: 1.0, ClimatePhase.DROUGHT: 1.4,  ClimatePhase.COOLING: 1.25},
    "coast":     {ClimatePhase.TEMPERATE: 1.0, ClimatePhase.WARMING: 1.0, ClimatePhase.DROUGHT: 1.0,  ClimatePhase.COOLING: 1.25},
    "desert":    {ClimatePhase.TEMPERATE: 1.0, ClimatePhase.WARMING: 1.0, ClimatePhase.DROUGHT: 1.0,  ClimatePhase.COOLING: 1.25},
    "tundra":    {ClimatePhase.TEMPERATE: 1.0, ClimatePhase.WARMING: 0.5, ClimatePhase.DROUGHT: 1.0,  ClimatePhase.COOLING: 3.3},
    "mountains": {ClimatePhase.TEMPERATE: 1.0, ClimatePhase.WARMING: 1.0, ClimatePhase.DROUGHT: 1.0,  ClimatePhase.COOLING: 1.25},
}


def climate_degradation_multiplier(
    terrain: str, phase: ClimatePhase, severity: float,
) -> float:
    """Multiplier applied directly to degradation rate during phase 9."""
    terrain_map = _BASE_MULTIPLIERS.get(terrain, _BASE_MULTIPLIERS["plains"])
    base = terrain_map.get(phase, 1.0)
    return 1.0 + (base - 1.0) * severity


@dataclass(frozen=True)
class DisasterSpec:
    terrain: str
    base_prob: float
    climate_double: ClimatePhase | None


DISASTER_SPECS: dict[str, DisasterSpec] = {
    "earthquake": DisasterSpec(terrain="mountains", base_prob=0.02, climate_double=None),
    "flood":      DisasterSpec(terrain="coast",     base_prob=0.03, climate_double=ClimatePhase.WARMING),
    "wildfire":   DisasterSpec(terrain="forest",    base_prob=0.02, climate_double=ClimatePhase.DROUGHT),
    "sandstorm":  DisasterSpec(terrain="desert",    base_prob=0.03, climate_double=None),
}


def _disaster_probability(
    disaster_type: str, terrain: str, phase: ClimatePhase, severity: float,
) -> float:
    """Compute disaster probability for a terrain/phase/severity combo."""
    spec = DISASTER_SPECS.get(disaster_type)
    if spec is None or spec.terrain != terrain:
        return 0.0
    prob = spec.base_prob * severity
    if spec.climate_double and phase == spec.climate_double:
        prob *= 2
    return prob


def _deterministic_roll(seed: int, region_name: str, turn: int, disaster_type: str) -> float:
    """Deterministic random value in [0, 1) using SHA256."""
    data = f"{seed}:{region_name}:{turn}:{disaster_type}"
    return int(hashlib.sha256(data.encode()).hexdigest(), 16) % 10000 / 10000


def check_disasters(world: WorldState, climate_phase: ClimatePhase) -> list[Event]:
    """Called from environment phase (phase 1)."""
    events: list[Event] = []
    severity = world.climate_config.severity

    for region in world.regions:
        for dtype, spec in DISASTER_SPECS.items():
            if spec.terrain != region.terrain:
                continue
            if dtype in region.disaster_cooldowns:
                continue

            prob = _disaster_probability(dtype, region.terrain, climate_phase, severity)
            if prob <= 0:
                continue

            roll = _deterministic_roll(world.seed, region.name, world.turn, dtype)
            if roll >= prob:
                continue

            region.disaster_cooldowns[dtype] = 10

            if dtype == "earthquake":
                region.ecology.soil = max(0.05, region.ecology.soil - 0.2)
                active_infra = [i for i in region.infrastructure if i.active]
                if active_infra:
                    idx = int(_deterministic_roll(
                        world.seed, region.name, world.turn, "eq_target"
                    ) * len(active_infra))
                    idx = min(idx, len(active_infra) - 1)
                    active_infra[idx].active = False
                events.append(Event(
                    turn=world.turn, event_type="earthquake",
                    actors=[region.controller or "nature"],
                    description=f"Earthquake strikes {region.name}",
                    importance=7,
                ))

            elif dtype == "flood":
                region.ecology.water = min(1.0, region.ecology.water + 0.1)
                for i in region.infrastructure:
                    if i.type == InfrastructureType.PORTS and i.active:
                        i.active = False
                events.append(Event(
                    turn=world.turn, event_type="flood",
                    actors=[region.controller or "nature"],
                    description=f"Flooding devastates {region.name}",
                    importance=6,
                ))

            elif dtype == "wildfire":
                region.ecology.forest_cover = max(0.0, region.ecology.forest_cover - 0.3)
                region.resource_suspensions[ResourceType.TIMBER] = 10
                events.append(Event(
                    turn=world.turn, event_type="wildfire",
                    actors=[region.controller or "nature"],
                    description=f"Wildfire sweeps through {region.name}",
                    importance=6,
                ))

            elif dtype == "sandstorm":
                region.route_suspensions["trade_route"] = 5
                events.append(Event(
                    turn=world.turn, event_type="sandstorm",
                    actors=[region.controller or "nature"],
                    description=f"Sandstorm disrupts {region.name}",
                    importance=4,
                ))

    return events


def process_migration(world: WorldState, acc=None) -> list[Event]:
    """Called at end of phase 1, after disasters."""
    from chronicler.ecology import effective_capacity
    from chronicler.utils import add_region_pop, sync_all_populations

    events: list[Event] = []

    for region in world.regions:
        if region.controller is None:
            continue

        civ = next((c for c in world.civilizations if c.name == region.controller), None)
        if civ is None or not civ.regions:
            continue

        region_pop = region.population
        eff_cap = effective_capacity(region)

        if eff_cap >= region_pop * 0.5:
            continue

        surplus = region_pop - eff_cap
        if surplus <= 0:
            continue

        eligible: list[tuple] = []
        for adj_name in region.adjacencies:
            adj_region = next((r for r in world.regions if r.name == adj_name), None)
            if adj_region is None:
                continue
            if adj_region.controller is None:
                eligible.append((adj_region, None))
                continue
            src_rels = world.relationships.get(region.controller, {})
            rel = src_rels.get(adj_region.controller)
            if rel and rel.disposition == Disposition.HOSTILE:
                continue
            eligible.append((adj_region, adj_region.controller))

        if eligible:
            share = surplus // len(eligible) if len(eligible) > 0 else 0
            remainder = surplus - share * len(eligible)
            for adj_region, ctrl_name in eligible:
                amount = share + (1 if remainder > 0 else 0)
                if remainder > 0:
                    remainder -= 1
                add_region_pop(adj_region, amount)
                if ctrl_name is not None:
                    recv_civ = next(
                        (c for c in world.civilizations if c.name == ctrl_name), None
                    )
                    if recv_civ:
                        mult = get_severity_multiplier(recv_civ, world)
                        if acc is not None:
                            recv_idx = civ_index(world, recv_civ.name)
                            acc.add(recv_idx, recv_civ, "stability", -int(3 * mult), "signal")
                        else:
                            recv_civ.stability = max(recv_civ.stability - int(3 * mult), 0)

            region.population = max(region.population - surplus, 0)
            importance = min(5 + surplus // 10, 9)
            events.append(Event(
                turn=world.turn, event_type="migration",
                actors=[civ.name],
                description=f"Population flees {region.name} ({surplus} displaced)",
                importance=importance,
            ))
        else:
            region.population = max(region.population - surplus, 0)
            events.append(Event(
                turn=world.turn, event_type="famine_starvation",
                actors=[civ.name],
                description=f"Population starves in {region.name} — nowhere to flee",
                importance=min(5 + surplus // 10, 9),
            ))

    sync_all_populations(world)
    return events
