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
from chronicler.tuning import (
    K_DISASTER_COOLDOWN, K_EARTHQUAKE_SOIL_LOSS,
    K_FLOOD_WATER_GAIN, K_WILDFIRE_FOREST_LOSS,
    K_WILDFIRE_SUSPENSION_TURNS, K_SANDSTORM_SUSPENSION_TURNS,
    K_MIGRATION_CAPACITY_RATIO,
    get_override,
)
from chronicler.utils import civ_index, stable_hash_int
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
    period = max(int(config.period), 1)
    threshold_shift = int(PHASE_SCHEDULE[phase_idx][0] * period)
    shifted_turn = turn + threshold_shift
    position = (shifted_turn % period) / period
    phase = ClimatePhase.TEMPERATE
    for threshold, p in PHASE_SCHEDULE:
        if position >= threshold:
            phase = p
    return phase


# --- Regional climate (2026-10, docs/integration/farmland-climate.md) --------
#
# Correction. The phase above is one schedule for the whole world, so its
# drought and cooling (40% of every cycle) cut every region's crops and water
# at once, and long world-wide famines followed. The global phase is kept as
# the long trend at CLIMATE_TREND_SHARE of its crop and water effects; the
# rest of the same climate pressure comes as regional harvest shocks. Regions
# are grouped into clusters of neighbours (``climate_clusters``). Each
# cluster's harvest years (HARVEST_YEAR turns) are good or bad: a two-state
# chain in which a bad year follows a bad one with BAD_YEAR_PERSISTENCE and a
# good one with the probability that keeps the stationary share of bad years
# at ``bad_year_share``. A bad year takes a depth drawn from BAD_YEAR_DEPTH off
# the region's crop climate factor and dries its land. The shares are derived
# so that the mean crop climate factor and the water lost over a cycle match
# the global schedule's. Every draw is a namespaced ``stable_hash_int`` of the
# world seed, the cluster's founding region and the year: no state, no RNG.
# ``climate.trend_share`` 1.0 restores the global schedule alone.

CLIMATE_TREND_SHARE = 0.5
HARVEST_YEAR = 12          # turns: the season calendar (resources.get_season_id)
BAD_YEAR_PERSISTENCE = 0.4  # P(bad | bad): a run of bad years, rarely more than three
BAD_YEAR_DEPTH = (0.2, 0.6)  # crop loss of a bad year, uniform
CLIMATE_CLUSTER_SIZE = 3   # a region and up to two of its neighbours
_CROP_PHASE_MOD = {
    ClimatePhase.TEMPERATE: 1.0, ClimatePhase.WARMING: 0.9,
    ClimatePhase.DROUGHT: 0.5, ClimatePhase.COOLING: 0.7,
}  # resources.CLIMATE_CLASS_MOD crop row (checked by the tests)


def _phase_shares() -> dict[ClimatePhase, float]:
    bounds = [t for t, _ in PHASE_SCHEDULE] + [1.0]
    return {p: bounds[i + 1] - bounds[i] for i, (_, p) in enumerate(PHASE_SCHEDULE)}


def climate_trend_share(world) -> float:
    """Share of the global phase's crop and water effects (1.0: no regional climate)."""
    from chronicler.tuning import K_CLIMATE_TREND_SHARE
    return min(1.0, max(0.0, float(get_override(world, K_CLIMATE_TREND_SHARE, CLIMATE_TREND_SHARE))))


def mean_harvest_shock(trend_share: float) -> float:
    """Mean shock depth that keeps the cycle-mean crop climate factor: the
    regional share of the global schedule's mean crop loss."""
    shares = _phase_shares()
    mean_loss = sum(shares[p] * (1.0 - m) for p, m in _CROP_PHASE_MOD.items())
    return (1.0 - trend_share) * mean_loss


def bad_year_share(trend_share: float) -> float:
    """Stationary share of bad harvest years (mean depth x share = mean shock)."""
    lo, hi = BAD_YEAR_DEPTH
    return min(0.95, mean_harvest_shock(trend_share) / (0.5 * (lo + hi)))


def harvest_shock_water_loss(world, trend_share: float) -> float:
    """Water a region loses per turn and unit of shock depth: the regional
    share of the water the global drought and cooling take over a cycle,
    spread over the mean shock."""
    from chronicler.tuning import K_COOLING_WATER_LOSS, K_WATER_DROUGHT
    mean_shock = mean_harvest_shock(trend_share)
    if mean_shock <= 0.0:
        return 0.0
    shares = _phase_shares()
    per_turn = (shares[ClimatePhase.DROUGHT] * get_override(world, K_WATER_DROUGHT, 0.04)
                + shares[ClimatePhase.COOLING] * get_override(world, K_COOLING_WATER_LOSS, 0.02))
    return (1.0 - trend_share) * per_turn / mean_shock


_YEAR_CACHE: dict[tuple, list[float]] = {}


def harvest_shock(seed: int, cluster: str, turn: int, trend_share: float = CLIMATE_TREND_SHARE) -> float:
    """Pure. Crop loss of ``cluster``'s harvest year at ``turn`` (0.0 in a good
    year). ``cluster`` names the cluster's founding region."""
    if trend_share >= 1.0 or turn < 0:
        return 0.0
    pi = bad_year_share(trend_share)
    if pi <= 0.0:
        return 0.0
    rho = BAD_YEAR_PERSISTENCE
    q = pi * (1.0 - rho) / (1.0 - pi)
    lo, hi = BAD_YEAR_DEPTH
    year = turn // HARVEST_YEAR
    key = (int(seed), cluster, round(pi, 12))
    years = _YEAR_CACHE.setdefault(key, [])
    while len(years) <= year:
        y = len(years)
        h = stable_hash_int("climate.harvest_year", int(seed), cluster, y)
        u = (h >> 32) / 4294967296.0
        prev_bad = years[-1] > 0.0 if years else None
        p_bad = pi if prev_bad is None else (rho if prev_bad else q)
        years.append(lo + (hi - lo) * ((h & 0xFFFFFFFF) / 4294967296.0) if u < p_bad else 0.0)
    if len(_YEAR_CACHE) > 4096:  # many worlds in one process (tests): start afresh
        _YEAR_CACHE.clear()
        _YEAR_CACHE[key] = years
    return years[year]


_CLUSTER_CACHE: dict[tuple, tuple[str, ...]] = {}


def climate_clusters(world) -> tuple[str, ...]:
    """Pure in the world's seed and geography. The founding region's name of
    each region's climate cluster (by region index): regions taken in hashed
    order found a cluster with up to ``CLIMATE_CLUSTER_SIZE - 1`` of their
    unassigned neighbours."""
    names = tuple(r.name for r in world.regions)
    key = (int(world.seed), names)
    cached = _CLUSTER_CACHE.get(key)
    if cached is not None:
        return cached
    index = {name: i for i, name in enumerate(names)}
    rank = {name: stable_hash_int("climate.cluster", int(world.seed), name) for name in names}
    founder: list[str | None] = [None] * len(names)
    for i in sorted(range(len(names)), key=lambda k: (rank[names[k]], names[k])):
        if founder[i] is not None:
            continue
        founder[i] = names[i]
        free = sorted((index[a] for a in world.regions[i].adjacencies
                       if a in index and founder[index[a]] is None),
                      key=lambda k: (rank[names[k]], names[k]))
        for j in free[:CLIMATE_CLUSTER_SIZE - 1]:
            founder[j] = names[i]
    out = tuple(f or n for f, n in zip(founder, names))
    if len(_CLUSTER_CACHE) > 256:
        _CLUSTER_CACHE.clear()
    _CLUSTER_CACHE[key] = out
    return out


def region_harvest_shocks(world, turn: int | None = None) -> list[float]:
    """Harvest shock of every region (by index) at ``turn`` (default: now)."""
    trend = climate_trend_share(world)
    if trend >= 1.0:
        return [0.0] * len(world.regions)
    t = world.turn if turn is None else turn
    return [harvest_shock(world.seed, c, t, trend) for c in climate_clusters(world)]


def region_harvest_shock(world, region) -> float:
    """Harvest shock of one region now (0.0 without regional climate)."""
    if world is None:
        return 0.0
    trend = climate_trend_share(world)
    if trend >= 1.0:
        return 0.0
    clusters = climate_clusters(world)
    for i, r in enumerate(world.regions):
        if r is region or r.name == region.name:
            return harvest_shock(world.seed, clusters[i], world.turn, trend)
    return 0.0


def regional_crop_climate(crop_mod: float, trend_share: float, shock: float) -> float:
    """A region's crop climate factor from the global phase's crop modifier,
    the trend share and its harvest shock (the modifier itself at share 1.0
    without a shock). Mirrors Rust ``ecology::regional_crop_climate``."""
    if trend_share >= 1.0 and shock == 0.0:
        return crop_mod
    return max(0.0, 1.0 - trend_share * (1.0 - crop_mod) - shock)


# Base degradation multipliers by terrain x phase.
_BASE_MULTIPLIERS: dict[str, dict[ClimatePhase, float]] = {
    "plains":    {ClimatePhase.TEMPERATE: 1.0, ClimatePhase.WARMING: 1.0, ClimatePhase.DROUGHT: 2.0,  ClimatePhase.COOLING: 1.25},
    "forest":    {ClimatePhase.TEMPERATE: 1.0, ClimatePhase.WARMING: 1.0, ClimatePhase.DROUGHT: 1.4,  ClimatePhase.COOLING: 1.25},
    "coast":     {ClimatePhase.TEMPERATE: 1.0, ClimatePhase.WARMING: 1.0, ClimatePhase.DROUGHT: 1.0,  ClimatePhase.COOLING: 1.25},
    "desert":    {ClimatePhase.TEMPERATE: 1.0, ClimatePhase.WARMING: 1.0, ClimatePhase.DROUGHT: 1.0,  ClimatePhase.COOLING: 1.25},
    "tundra":    {ClimatePhase.TEMPERATE: 1.0, ClimatePhase.WARMING: 0.5, ClimatePhase.DROUGHT: 1.0,  ClimatePhase.COOLING: 3.3},
    "mountains": {ClimatePhase.TEMPERATE: 1.0, ClimatePhase.WARMING: 1.0, ClimatePhase.DROUGHT: 1.0,  ClimatePhase.COOLING: 1.25},
    "steppe":    {ClimatePhase.TEMPERATE: 1.0, ClimatePhase.WARMING: 1.0, ClimatePhase.DROUGHT: 1.8,  ClimatePhase.COOLING: 1.25},
    "jungle":    {ClimatePhase.TEMPERATE: 1.0, ClimatePhase.WARMING: 1.0, ClimatePhase.DROUGHT: 1.2,  ClimatePhase.COOLING: 1.4},
    "marsh":     {ClimatePhase.TEMPERATE: 1.0, ClimatePhase.WARMING: 1.0, ClimatePhase.DROUGHT: 1.5,  ClimatePhase.COOLING: 1.25},
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
            if region.latitude_band is not None:
                from chronicler.geography import disaster_factor
                prob *= disaster_factor(region.latitude_band, dtype)

            roll = _deterministic_roll(world.seed, region.name, world.turn, dtype)
            if roll >= prob:
                continue

            cooldown = int(get_override(world, K_DISASTER_COOLDOWN, 10))
            region.disaster_cooldowns[dtype] = cooldown

            if dtype == "earthquake":
                eq_soil_loss = get_override(world, K_EARTHQUAKE_SOIL_LOSS, 0.2)
                region.ecology.soil = max(0.05, region.ecology.soil - eq_soil_loss)
                active_infra = [i for i in region.infrastructure if i.active]
                if active_infra:
                    idx = int(_deterministic_roll(
                        world.seed, region.name, world.turn, "eq_target"
                    ) * len(active_infra))
                    idx = min(idx, len(active_infra) - 1)
                    active_infra[idx].active = False
                events.append(Event(
                    turn=world.turn, event_type="earthquake", region=region.name,
                    actors=[region.controller or "nature"],
                    description=f"Earthquake strikes {region.name}",
                    importance=7,
                ))

            elif dtype == "flood":
                from chronicler.ecology import TERRAIN_ECOLOGY_CAPS
                flood_water = get_override(world, K_FLOOD_WATER_GAIN, 0.1)
                caps = TERRAIN_ECOLOGY_CAPS.get(region.terrain, TERRAIN_ECOLOGY_CAPS["plains"])
                region.ecology.water = min(caps["water"], region.ecology.water + flood_water)
                for i in region.infrastructure:
                    if i.type == InfrastructureType.PORTS and i.active:
                        i.active = False
                events.append(Event(
                    turn=world.turn, event_type="flood", region=region.name,
                    actors=[region.controller or "nature"],
                    description=f"Flooding devastates {region.name}",
                    importance=6,
                ))

            elif dtype == "wildfire":
                wildfire_loss = get_override(world, K_WILDFIRE_FOREST_LOSS, 0.3)
                region.ecology.forest_cover = max(0.0, region.ecology.forest_cover - wildfire_loss)
                wildfire_susp = int(get_override(world, K_WILDFIRE_SUSPENSION_TURNS, 10))
                region.resource_suspensions[int(ResourceType.TIMBER)] = wildfire_susp
                events.append(Event(
                    turn=world.turn, event_type="wildfire", region=region.name,
                    actors=[region.controller or "nature"],
                    description=f"Wildfire sweeps through {region.name}",
                    importance=6,
                ))

            elif dtype == "sandstorm":
                sandstorm_susp = int(get_override(world, K_SANDSTORM_SUSPENSION_TURNS, 5))
                region.route_suspensions["trade_route"] = sandstorm_susp
                events.append(Event(
                    turn=world.turn, event_type="sandstorm", region=region.name,
                    actors=[region.controller or "nature"],
                    description=f"Sandstorm disrupts {region.name}",
                    importance=4,
                ))

    return events


def process_migration(world: WorldState, acc=None) -> list[Event]:
    """Called at end of phase 1, after disasters.

    Aggregate overflow migration for Python-owned populations (off and shadow
    modes). In hybrid and demographics-only modes the native agent pool owns
    population and agents migrate themselves, so this is a no-op there.

    Correction (2026-10, food balance): it used to run in every mode. In the
    agent-owned modes it rewrote ``region.population`` for the rest of the
    turn (clamping an overflowing region to its effective capacity and adding
    the "surplus" to neighbours) although no agent moved; the write-back then
    restored the agent count. Phase 2-9 consumers (ecology pressure, soil and
    disease gates, plague crowding, stock caps) therefore read a fictitious
    population, and the turn emitted migration/starvation events and
    receiving-civ stability penalties for moves that never happened.
    """
    from chronicler.ecology import effective_capacity
    from chronicler.utils import add_region_pop, get_region_map, sync_all_populations

    events: list[Event] = []
    if getattr(world, "agent_mode", None) in ("hybrid", "demographics-only"):
        return events
    civ_by_name = getattr(world, "civ_map", None)
    if not isinstance(civ_by_name, dict):
        civ_by_name = {c.name: c for c in world.civilizations}
    region_map = get_region_map(world)

    for region in world.regions:
        if region.controller is None:
            continue

        civ = civ_by_name.get(region.controller)
        if civ is None or not civ.regions:
            continue

        region_pop = region.population
        eff_cap = effective_capacity(region)

        migration_ratio = get_override(world, K_MIGRATION_CAPACITY_RATIO, 0.5)
        if eff_cap >= region_pop * migration_ratio:
            continue

        surplus = region_pop - eff_cap
        if surplus <= 0:
            continue

        eligible: list[tuple] = []
        for adj_name in region.adjacencies:
            adj_region = region_map.get(adj_name)
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
            share = surplus // len(eligible)
            remainder = surplus - share * len(eligible)
            for adj_region, ctrl_name in eligible:
                amount = share + (1 if remainder > 0 else 0)
                if remainder > 0:
                    remainder -= 1
                add_region_pop(adj_region, amount)
                if ctrl_name is not None:
                    recv_civ = civ_by_name.get(ctrl_name)
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
                turn=world.turn, event_type="migration", region=region.name,
                actors=[civ.name],
                description=f"Population flees {region.name} ({surplus} displaced)",
                importance=importance,
            ))
        else:
            region.population = max(region.population - surplus, 0)
            events.append(Event(
                turn=world.turn, event_type="famine_starvation", region=region.name,
                actors=[civ.name],
                description=f"Population starves in {region.name} — nowhere to flee",
                importance=min(5 + surplus // 10, 9),
            ))

    sync_all_populations(world)
    return events
