"""M18 Emergence and Chaos — black swans, stress, regression, ecological succession.

All cross-system emergence logic centralized in one module. Called from
existing turn phases via distributed hooks in simulation.py.
"""
from __future__ import annotations

import random

from chronicler.models import (
    ActiveCondition, Civilization, ClimatePhase, EMPTY_SLOT, Event, PandemicRegion, Region,
    ResourceType, TechEra, WorldState,
)
from chronicler.resources import get_active_trade_routes
from chronicler.tech import _prev_era, remove_era_bonus
from chronicler.tuning import (
    K_BLACK_SWAN_BASE_PROB, K_BLACK_SWAN_COOLDOWN,
    K_REGRESSION_CAPITAL_COLLAPSE, K_REGRESSION_TWILIGHT, K_REGRESSION_BLACK_SWAN,
    K_REGRESSION_CULTURE_RESISTANCE_FLOOR, K_REGRESSION_CULTURE_RESISTANCE_DIVISOR,
    K_LOCUST_PROBABILITY, K_FLOOD_PROBABILITY, K_COLLAPSE_PROBABILITY,
    K_DROUGHT_INTENSIFICATION_PROBABILITY, K_COLLAPSE_MORTALITY_SPIKE,
    K_ECOLOGICAL_RECOVERY_PROBABILITY, K_ECOLOGICAL_RECOVERY_FRACTION,
    K_SEVERITY_STRESS_DIVISOR, K_SEVERITY_STRESS_SCALE, K_SEVERITY_CAP,
    K_STRESS_WAR_WEIGHT, K_STRESS_FAMINE_WEIGHT, K_STRESS_SECESSION_RISK,
    K_STRESS_PANDEMIC_WEIGHT, K_STRESS_TWILIGHT_WEIGHT,
    K_STRESS_OVEREXTENSION_THRESHOLD,
    K_VOLCANO_POP_DRAIN, K_VOLCANO_STABILITY_DRAIN, K_VOLCANIC_WINTER_DURATION,
    K_PANDEMIC_LEADER_KILL_PROB,
    K_TECH_ACCIDENT_SOIL_LOSS, K_TECH_ACCIDENT_NEIGHBOR_SOIL_LOSS,
    get_override,
)
from chronicler.utils import (
    civ_index,
    clamp,
    get_region_map,
    stable_hash_int,
    STAT_FLOOR,
    distribute_pop_loss,
    drain_region_pop,
    sync_civ_population,
)


# ---------------------------------------------------------------------------
# Stress Index & Cascade Severity
# ---------------------------------------------------------------------------

def compute_civ_stress(civ: Civilization, world: WorldState) -> int:
    """Compute per-civ stress from current world state. Returns 0-20."""
    stress = 0

    # Active wars: per war weight
    war_weight = int(get_override(world, K_STRESS_WAR_WEIGHT, 3))
    stress += sum(1 for w in world.active_wars if civ.name in w) * war_weight

    # Famine in controlled regions: per famine region
    famine_weight = int(get_override(world, K_STRESS_FAMINE_WEIGHT, 2))
    stress += sum(
        1 for r in world.regions
        if r.controller == civ.name and r.famine_cooldown > 0
    ) * famine_weight

    # Active secession risk: if stability < 20 with 3+ regions
    secession_risk = int(get_override(world, K_STRESS_SECESSION_RISK, 4))
    if civ.stability < 20 and len(civ.regions) >= 3:
        stress += secession_risk

    # Active pandemic in controlled regions: per infected region
    pandemic_weight = int(get_override(world, K_STRESS_PANDEMIC_WEIGHT, 2))
    infected_region_names = {p.region_name for p in world.pandemic_state}
    stress += sum(
        1 for r in world.regions
        if r.controller == civ.name and r.name in infected_region_names
    ) * pandemic_weight

    # Recent turbulent succession: 2 if general/usurper within last 5 turns
    if (civ.leader.succession_type in ("general", "usurper")
            and world.turn - civ.leader.reign_start <= 5):
        stress += 2

    # In twilight
    twilight_weight = int(get_override(world, K_STRESS_TWILIGHT_WEIGHT, 3))
    if civ.decline_turns > 0:
        stress += twilight_weight

    # Active disaster conditions: 2 per qualifying condition
    stress += sum(
        1 for c in world.active_conditions
        if civ.name in c.affected_civs
        and c.condition_type in ("drought", "volcanic_winter")
    ) * 2

    # Overextension: 1 per region beyond threshold
    overext_thresh = int(get_override(world, K_STRESS_OVEREXTENSION_THRESHOLD, 6))
    stress += max(0, len(civ.regions) - overext_thresh)

    return min(stress, 20)


def compute_all_stress(world: WorldState) -> None:
    """Recompute stress for all civs and set global aggregate."""
    for civ in world.civilizations:
        civ.civ_stress = compute_civ_stress(civ, world)
    if world.civilizations:
        world.stress_index = max(c.civ_stress for c in world.civilizations)
    else:
        world.stress_index = 0


def get_severity_multiplier(civ: Civilization, world: "WorldState | None" = None) -> float:
    """Return cascade severity multiplier. Composed with tuning multiplier, capped at 2.0."""
    divisor = get_override(world, K_SEVERITY_STRESS_DIVISOR, 20) if world else 20
    scale = get_override(world, K_SEVERITY_STRESS_SCALE, 0.5) if world else 0.5
    cap = get_override(world, K_SEVERITY_CAP, 2.0) if world else 2.0
    base = 1.0 + (civ.civ_stress / divisor) * scale
    if world is not None:
        from chronicler.tuning import get_multiplier, K_SEVERITY_MULTIPLIER
        return min(base * get_multiplier(world, K_SEVERITY_MULTIPLIER), cap)
    return base


# ---------------------------------------------------------------------------
# Black Swan Events
# ---------------------------------------------------------------------------

_BLACK_SWAN_BASE_PROB = 0.005  # 0.5% per turn
_DEFAULT_COOLDOWN = 30

# Event type names (shared constant for detection in simulation.py)
BLACK_SWAN_EVENT_TYPES = frozenset({"pandemic", "supervolcano", "resource_discovery", "tech_accident"})

# Weights for event type selection
_EVENT_WEIGHTS = {
    "pandemic": 3,
    "supervolcano": 2,
    "resource_discovery": 2,
    "tech_accident": 1,
}


def _count_trade_partners(civ_name: str, world: WorldState) -> int:
    """Count distinct trading partners for a civ."""
    routes = get_active_trade_routes(world)
    partners = set()
    for a, b in routes:
        if a == civ_name:
            partners.add(b)
        elif b == civ_name:
            partners.add(a)
    # M17: merchant great person adds +1 to partner count
    civ_by_name = getattr(world, "civ_map", None)
    if not isinstance(civ_by_name, dict):
        civ_by_name = {c.name: c for c in world.civilizations}
    civ = civ_by_name.get(civ_name)
    if civ is not None:
        for gp in civ.great_persons:
            if gp.role == "merchant" and gp.active:
                return len(partners) + 1
    return len(partners)


def _find_volcano_triples(world: WorldState) -> list[tuple[Region, Region, Region]]:
    """Find all region triples where each pair is adjacent and at least one is controlled."""
    regions = world.regions
    triples = []
    for i, a in enumerate(regions):
        for j, b in enumerate(regions):
            if j <= i:
                continue
            if b.name not in a.adjacencies:
                continue
            for k, c in enumerate(regions):
                if k <= j:
                    continue
                if c.name not in a.adjacencies or c.name not in b.adjacencies:
                    continue
                if a.controller or b.controller or c.controller:
                    triples.append((a, b, c))
    return triples


def _get_eligible_types(world: WorldState) -> dict[str, int]:
    """Return eligible black swan types with their weights."""
    eligible = {}

    # Pandemic: any civ has 3+ distinct trading partners
    for civ in world.civilizations:
        if _count_trade_partners(civ.name, world) >= 3:
            eligible["pandemic"] = _EVENT_WEIGHTS["pandemic"]
            break

    # Supervolcano: any cluster of 3 mutually adjacent regions with at least one controlled
    if _find_volcano_triples(world):
        eligible["supervolcano"] = _EVENT_WEIGHTS["supervolcano"]

    # Resource discovery: any region with no resource types assigned
    if any(r.resource_types[0] == EMPTY_SLOT for r in world.regions):
        eligible["resource_discovery"] = _EVENT_WEIGHTS["resource_discovery"]

    # Tech accident: any civ at INDUSTRIAL+
    industrial_plus = {TechEra.INDUSTRIAL, TechEra.INFORMATION}
    if any(c.tech_era in industrial_plus for c in world.civilizations):
        eligible["tech_accident"] = _EVENT_WEIGHTS["tech_accident"]

    return eligible


def check_black_swans(world: WorldState, seed: int, acc=None) -> list[Event]:
    """Roll for black swan event. Called after Phase 1 (Environment)."""
    if world.black_swan_cooldown > 0:
        return []

    rng = random.Random(seed + world.turn * 997)
    prob = get_override(world, K_BLACK_SWAN_BASE_PROB, _BLACK_SWAN_BASE_PROB) * world.chaos_multiplier
    if rng.random() >= prob:
        return []

    # Roll succeeded — check eligibility
    eligible = _get_eligible_types(world)
    if not eligible:
        return []  # No eligible types, roll wasted, no cooldown set

    # Weighted selection
    types = list(eligible.keys())
    weights = [eligible[t] for t in types]
    chosen = rng.choices(types, weights=weights, k=1)[0]

    # Set cooldown
    world.black_swan_cooldown = int(get_override(world, K_BLACK_SWAN_COOLDOWN, world.black_swan_cooldown_turns))

    # Dispatch to specific handler
    if chosen == "supervolcano":
        return _apply_supervolcano(world, seed, acc=acc)
    handlers = {
        "pandemic": _apply_pandemic_origin,
        "resource_discovery": _apply_resource_discovery,
        "tech_accident": _apply_tech_accident,
    }
    return handlers[chosen](world, seed)


def _apply_pandemic_origin(world: WorldState, seed: int) -> list[Event]:
    """Initialize a pandemic originating from the most trade-connected civ."""
    rng = random.Random(seed + world.turn * 1009)

    # Find most connected civ
    best_civ = None
    best_count = 0
    for civ in world.civilizations:
        count = _count_trade_partners(civ.name, world)
        if count > best_count:
            best_count = count
            best_civ = civ

    if best_civ is None:
        return []

    # Select origin region (random among best_civ's controlled regions)
    controlled = [r for r in world.regions if r.controller == best_civ.name]
    if not controlled:
        return []
    origin_region = rng.choice(controlled)

    # Compute severity from active infrastructure
    active_infra = len([i for i in origin_region.infrastructure if i.active])
    severity = min(3, 1 + active_infra // 2)

    # Duration: 4-6, reduced by 1 if scientist great person present
    duration = rng.randint(4, 6)
    has_scientist = any(
        gp.role == "scientist" and gp.active
        for gp in best_civ.great_persons
    )
    if has_scientist:
        duration = max(1, duration - 1)

    world.pandemic_state.append(PandemicRegion(
        region_name=origin_region.name,
        severity=severity,
        turns_remaining=duration,
    ))

    return [Event(
        turn=world.turn,
        event_type="pandemic",
        actors=[best_civ.name],
        description=f"A devastating plague erupts in {origin_region.name}, spreading through {best_civ.name}'s trade network",
        importance=9,
    )]


def tick_pandemic(
    world: WorldState,
    acc=None,
    routes: list[tuple[str, str]] | None = None,
) -> list[Event]:
    """Per-turn pandemic tick: apply damage, spread, decrement timers. Phase 2."""
    if not world.pandemic_state:
        return []

    events: list[Event] = []
    infected_names = {p.region_name for p in world.pandemic_state}
    already_infected_or_recovered = set(infected_names) | set(world.pandemic_recovered)
    region_map = get_region_map(world)
    civ_by_name = getattr(world, "civ_map", None)
    if not isinstance(civ_by_name, dict):
        civ_by_name = {c.name: c for c in world.civilizations}

    # --- Apply per-civ damage (distributed across affected regions) ---
    civ_max_severity: dict[str, int] = {}
    for p in world.pandemic_state:
        region = region_map.get(p.region_name)
        if region and region.controller:
            current = civ_max_severity.get(region.controller, 0)
            civ_max_severity[region.controller] = max(current, p.severity)

    for civ_name, severity in civ_max_severity.items():
        civ = civ_by_name.get(civ_name)
        if civ is None:
            continue
        sev_mult = get_severity_multiplier(civ, world)
        pop_loss = round(min(severity * 3, 12) * sev_mult)
        eco_loss = round(min(severity * 2, 8) * sev_mult)
        affected_regions = [
            r for r in world.regions
            if r.controller == civ_name and r.name in infected_names
        ]
        if not affected_regions:
            affected_regions = [r for r in world.regions if r.controller == civ_name]
        if acc is not None:
            civ_idx = civ_index(world, civ.name)
            acc.add(civ_idx, civ, "population", -pop_loss, "guard")
            acc.add(civ_idx, civ, "economy", -eco_loss, "signal")
        else:
            distribute_pop_loss(affected_regions, pop_loss)
            sync_civ_population(civ, world)
            civ.economy = clamp(civ.economy - eco_loss, STAT_FLOOR.get("economy", 0), 100)

        # Leader kill check: per infected civ
        rng = random.Random(
            stable_hash_int("pandemic_leader_kill", world.seed, world.turn, civ_name)
        )
        leader_kill_prob = get_override(world, K_PANDEMIC_LEADER_KILL_PROB, 0.05)
        if rng.random() < leader_kill_prob:
            from chronicler.succession import trigger_crisis
            old_leader = civ.leader
            old_leader.alive = False
            trigger_crisis(civ, world)
            events.append(Event(
                turn=world.turn, event_type="pandemic_leader_death",
                actors=[civ_name],
                description=f"{old_leader.name} of {civ_name} succumbs to the plague",
                importance=8,
            ))

    # --- Spread to adjacent trade-connected regions ---
    if routes is None:
        routes = get_active_trade_routes(world)
    trade_pairs = set()
    for a, b in routes:
        trade_pairs.add((a, b))
        trade_pairs.add((b, a))

    infected_controllers = set()
    for p in world.pandemic_state:
        region = region_map.get(p.region_name)
        if region and region.controller:
            infected_controllers.add(region.controller)

    new_infections: list[PandemicRegion] = []
    rng_spread = random.Random(world.seed + world.turn * 1019)
    for p in world.pandemic_state:
        source_region = region_map.get(p.region_name)
        if source_region is None:
            continue
        for adj_name in source_region.adjacencies:
            if adj_name in already_infected_or_recovered:
                continue
            adj_region = region_map.get(adj_name)
            if adj_region is None or adj_region.controller is None:
                continue
            adj_ctrl = adj_region.controller
            if any((ctrl, adj_ctrl) in trade_pairs for ctrl in infected_controllers):
                active_infra = len([i for i in adj_region.infrastructure if i.active])
                severity = min(3, 1 + active_infra // 2)
                duration = rng_spread.randint(4, 6)
                target_civ = civ_by_name.get(adj_ctrl)
                if target_civ and any(gp.role == "scientist" and gp.active for gp in target_civ.great_persons):
                    duration = max(1, duration - 1)
                new_infections.append(PandemicRegion(
                    region_name=adj_name, severity=severity, turns_remaining=duration,
                ))
                already_infected_or_recovered.add(adj_name)

    # --- Decrement timers and remove expired ---
    for p in world.pandemic_state:
        p.turns_remaining -= 1
    for p in world.pandemic_state:
        if p.turns_remaining <= 0:
            world.pandemic_recovered.append(p.region_name)
    world.pandemic_state = [p for p in world.pandemic_state if p.turns_remaining > 0]

    # Add newly spread regions
    world.pandemic_state.extend(new_infections)

    # Clear recovered list when pandemic ends
    if not world.pandemic_state:
        world.pandemic_recovered = []

    return events


def _apply_supervolcano(world: WorldState, seed: int, acc=None) -> list[Event]:
    """Supervolcano: devastate a cluster of 3 adjacent regions."""
    rng = random.Random(seed + world.turn * 1021)
    region_map = get_region_map(world)
    civ_by_name = getattr(world, "civ_map", None)
    if not isinstance(civ_by_name, dict):
        civ_by_name = {c.name: c for c in world.civilizations}

    triples = _find_volcano_triples(world)
    if not triples:
        return []

    # Prefer triples containing mountains
    mountain_triples = [t for t in triples if any(r.terrain == "mountains" for r in t)]
    candidates = mountain_triples if mountain_triples else triples
    cluster = rng.choice(candidates)

    events: list[Event] = []
    affected_civs: set[str] = set()

    for region in cluster:
        region.ecology.soil = 0.1
        region.ecology.forest_cover = 0.05
        region.infrastructure = []
        region.pending_build = None

        if region.controller:
            affected_civs.add(region.controller)
            civ = civ_by_name.get(region.controller)
            if civ:
                mult = get_severity_multiplier(civ, world)
                volcano_pop = int(get_override(world, K_VOLCANO_POP_DRAIN, 20))
                volcano_stab = int(get_override(world, K_VOLCANO_STABILITY_DRAIN, 15))
                pop_loss = int(volcano_pop * mult)
                stab_loss = int(volcano_stab * mult)
                if acc is not None:
                    civ_idx = civ_index(world, civ.name)
                    acc.add(civ_idx, civ, "population", -pop_loss, "guard")
                    acc.add(civ_idx, civ, "stability", -stab_loss, "signal")
                else:
                    drain_region_pop(region, pop_loss)
                    sync_civ_population(civ, world)
                    civ.stability = clamp(
                        civ.stability - stab_loss,
                        STAT_FLOOR.get("stability", 0),
                        100,
                    )

    world.climate_config.phase_offset += 1

    blast_names = {r.name for r in cluster}
    adjacent_civs: set[str] = set()
    for region in cluster:
        for adj_name in region.adjacencies:
            adj = region_map.get(adj_name)
            if adj and adj.controller and adj.name not in blast_names:
                adjacent_civs.add(adj.controller)
    all_affected = sorted(affected_civs | adjacent_civs)
    if all_affected:
        winter_duration = int(get_override(world, K_VOLCANIC_WINTER_DURATION, 5))
        world.active_conditions.append(ActiveCondition(
            condition_type="volcanic_winter",
            affected_civs=all_affected,
            duration=winter_duration,
            severity=40,
        ))

    # M17: Folk hero asabiya bonus
    for civ_name in sorted(affected_civs):
        civ = civ_by_name.get(civ_name)
        if civ and civ.folk_heroes:
            from chronicler.simulation import _apply_asabiya_to_regions
            _apply_asabiya_to_regions(world, civ.name, 0.05)

    region_names = [r.name for r in cluster]
    events.append(Event(
        turn=world.turn,
        event_type="supervolcano",
        actors=sorted(affected_civs),
        description=f"A supervolcano erupts, devastating {', '.join(region_names)}",
        importance=10,
    ))

    return events


def _apply_resource_discovery(world: WorldState, seed: int) -> list[Event]:
    """Add strategic resources to a barren region."""
    from chronicler.resources import RESOURCE_BASE, populate_legacy_resources

    rng = random.Random(seed + world.turn * 1031)
    region_map = get_region_map(world)

    barren = [r for r in world.regions if r.resource_types[0] == EMPTY_SLOT]
    if not barren:
        return []

    region = rng.choice(barren)
    count = rng.randint(1, 2)
    new_resource_types = rng.sample([ResourceType.TIMBER, ResourceType.PRECIOUS], k=count)
    for rtype in new_resource_types:
        for slot in range(3):
            if region.resource_types[slot] == EMPTY_SLOT:
                region.resource_types[slot] = rtype
                region.resource_base_yields[slot] = RESOURCE_BASE[rtype] * (1.0 + rng.uniform(-0.2, 0.2))
                break
    populate_legacy_resources([region])

    controller = region.controller
    for adj_name in region.adjacencies:
        adj = region_map.get(adj_name)
        if adj is None or adj.controller is None:
            continue
        adj_ctrl = adj.controller
        if controller and adj_ctrl != controller:
            if adj_ctrl in world.relationships and controller in world.relationships[adj_ctrl]:
                world.relationships[adj_ctrl][controller].disposition_drift -= 5
        elif controller is None:
            for other_adj_name in region.adjacencies:
                other_adj = region_map.get(other_adj_name)
                if other_adj and other_adj.controller and other_adj.controller != adj_ctrl:
                    if adj_ctrl in world.relationships and other_adj.controller in world.relationships[adj_ctrl]:
                        world.relationships[adj_ctrl][other_adj.controller].disposition_drift -= 5

    resource_names = ", ".join(ResourceType(rtype).name.lower() for rtype in new_resource_types)
    return [Event(
        turn=world.turn,
        event_type="resource_discovery",
        actors=[controller] if controller else [],
        description=f"Deposits of {resource_names} discovered in {region.name}!",
        importance=8,
    )]


def _apply_tech_accident(world: WorldState, seed: int) -> list[Event]:
    """Industrial+ era ecological disaster."""
    rng = random.Random(seed + world.turn * 1033)
    region_map = get_region_map(world)

    industrial_plus = {TechEra.INDUSTRIAL, TechEra.INFORMATION}
    industrial_civs = [c for c in world.civilizations if c.tech_era in industrial_plus]
    if not industrial_civs:
        return []

    civ = rng.choice(industrial_civs)

    controlled = [r for r in world.regions if r.controller == civ.name]
    if not controlled:
        return []
    from chronicler.models import InfrastructureType
    mine_regions = [r for r in controlled
                    if any(i.type == InfrastructureType.MINES and i.active for i in r.infrastructure)]
    target = rng.choice(mine_regions if mine_regions else controlled)

    has_scientist = any(gp.role == "scientist" and gp.active for gp in civ.great_persons)
    max_hops = 1 if has_scientist else 2

    accident_soil = get_override(world, K_TECH_ACCIDENT_SOIL_LOSS, 0.3)
    target.ecology.soil = max(0.05, round(target.ecology.soil - accident_soil, 4))

    affected_neighbors: set[str] = set()
    frontier = [target.name]
    for hop in range(max_hops):
        next_frontier: list[str] = []
        for rname in frontier:
            region = region_map.get(rname)
            if region:
                for adj in region.adjacencies:
                    if adj != target.name and adj not in affected_neighbors:
                        next_frontier.append(adj)
                        affected_neighbors.add(adj)
        frontier = next_frontier

    polluter_name = civ.name
    for rname in sorted(affected_neighbors):
        region = region_map.get(rname)
        if region:
            neighbor_soil_loss = get_override(world, K_TECH_ACCIDENT_NEIGHBOR_SOIL_LOSS, 0.15)
            region.ecology.soil = max(0.05, round(region.ecology.soil - neighbor_soil_loss, 4))
            if region.controller and region.controller != polluter_name:
                if region.controller in world.relationships and polluter_name in world.relationships[region.controller]:
                    world.relationships[region.controller][polluter_name].disposition_drift -= 8

    return [Event(
        turn=world.turn,
        event_type="tech_accident",
        actors=[civ.name],
        description=f"Industrial disaster in {target.name} poisons the surrounding lands",
        importance=8,
    )]


# ---------------------------------------------------------------------------
# Technological Regression
# ---------------------------------------------------------------------------

_REGRESSION_TRIGGERS = {
    "capital_collapse": 0.30,
    "entered_twilight": 0.50,
    "black_swan_stressed": 0.20,
}


def check_tech_regression(world: WorldState, black_swan_fired: bool = False) -> list[Event]:
    """Check regression triggers for all civs. Phase 10, after consequences.

    Base regression probabilities are reduced by culture-based resistance:
    effective_prob = base_prob * max(0.2, 1.0 - culture / 200)
    """
    events: list[Event] = []

    for civ in world.civilizations:
        if _prev_era(civ.tech_era) is None:
            continue

        matching_probs: list[float] = []

        # Trigger 1: Capital loss + territorial collapse
        if (civ.capital_start_of_turn is not None
                and civ.capital_region != civ.capital_start_of_turn
                and civ.regions_start_of_turn > 0
                and len(civ.regions) / civ.regions_start_of_turn < 0.5):
            matching_probs.append(
                get_override(world, K_REGRESSION_CAPITAL_COLLAPSE, _REGRESSION_TRIGGERS["capital_collapse"])
            )

        # Trigger 2: Entered twilight this turn
        if civ.decline_turns > 0 and not civ.was_in_twilight:
            matching_probs.append(
                get_override(world, K_REGRESSION_TWILIGHT, _REGRESSION_TRIGGERS["entered_twilight"])
            )

        # Trigger 3: Black swan while critically stressed
        if black_swan_fired and civ.civ_stress >= 15:
            matching_probs.append(
                get_override(world, K_REGRESSION_BLACK_SWAN, _REGRESSION_TRIGGERS["black_swan_stressed"])
            )

        if not matching_probs:
            continue

        # Culture-based resistance: higher culture = lower regression probability
        resist_floor = get_override(world, K_REGRESSION_CULTURE_RESISTANCE_FLOOR, 0.2)
        resist_divisor = get_override(world, K_REGRESSION_CULTURE_RESISTANCE_DIVISOR, 200)
        culture_resistance = max(resist_floor, 1.0 - civ.culture / resist_divisor)
        best_prob = max(matching_probs) * culture_resistance
        rng = random.Random(
            stable_hash_int("tech_regression", world.seed, world.turn, civ.name)
        )
        if rng.random() >= best_prob:
            continue

        old_era = civ.tech_era
        new_era = _prev_era(old_era)
        assert new_era is not None
        remove_era_bonus(civ, old_era)
        # M21: Remove tech focus effects on regression
        if civ.active_focus:
            from chronicler.tech_focus import TechFocus, remove_focus_effects
            remove_focus_effects(civ, TechFocus(civ.active_focus))
            civ.active_focus = None
        civ.tech_era = new_era

        events.append(Event(
            turn=world.turn,
            event_type="tech_regression",
            actors=[civ.name],
            description=f"{civ.name} loses the knowledge of the {old_era.value} era, falling back to {new_era.value}",
            importance=9,
        ))

    return events


# ---------------------------------------------------------------------------
# Ecological Succession
# ---------------------------------------------------------------------------

    # NOTE: update_low_fertility_counters deleted by M23 — replaced by _update_ecology_counters in ecology.py


def tick_terrain_succession(world: WorldState) -> list[Event]:
    """Check and apply terrain transitions. Called at end of Phase 9."""
    events: list[Event] = []

    for region in world.regions:
        for rule in world.terrain_transition_rules:
            if region.terrain != rule.from_terrain:
                continue

            if rule.condition == "low_forest":
                if region.low_forest_turns >= rule.threshold_turns:
                    _apply_transition(region, rule)
                    events.append(Event(
                        turn=world.turn,
                        event_type="terrain_transition",
                        actors=[region.controller] if region.controller else [],
                        description=f"{region.name} transforms from {rule.from_terrain} to {rule.to_terrain}",
                        importance=6,
                    ))

            elif rule.condition == "forest_regrowth":
                if region.forest_regrowth_turns >= rule.threshold_turns:
                    _apply_transition(region, rule)
                    events.append(Event(
                        turn=world.turn,
                        event_type="terrain_transition",
                        actors=[],
                        description=f"{region.name} transforms from {rule.from_terrain} to {rule.to_terrain}",
                        importance=6,
                    ))

    return events


def _apply_transition(region: Region, rule) -> None:
    """Apply a terrain transition to a region.

    H-15: After changing terrain, clamp ecology values to the new terrain's
    TERRAIN_ECOLOGY_CAPS to prevent values exceeding the target caps
    (e.g., forest_cover=0.7 on plains where cap=0.40).
    """
    from chronicler.ecology import clamp_ecology

    if rule.from_terrain == "forest" and rule.to_terrain == "plains":
        region.terrain = "plains"
        region.carrying_capacity = min(100, region.carrying_capacity + 20)
        region.ecology.soil = 0.5
        region.ecology.forest_cover = 0.1
        region.low_forest_turns = 0
    elif rule.from_terrain == "plains" and rule.to_terrain == "forest":
        region.terrain = "forest"
        region.carrying_capacity = max(1, region.carrying_capacity - 10)
        region.ecology.forest_cover = 0.7
        region.forest_regrowth_turns = 0

    # H-15: Clamp all ecology values to the NEW terrain's caps
    clamp_ecology(region)


# ---------------------------------------------------------------------------
# M35b: Environmental Events (condition-triggered)
# ---------------------------------------------------------------------------

def _check_locust(region: Region, world: WorldState, rng) -> bool:
    """Locust swarm: plains/desert, summer/autumn, has Grain, soil > 0.4."""
    from chronicler.resources import get_season_id
    season_id = get_season_id(world.turn)
    if region.terrain not in ("plains", "desert"):
        return False
    if season_id not in (1, 2):  # Summer, Autumn
        return False
    if not any(rtype == ResourceType.GRAIN for rtype in region.resource_types if rtype != EMPTY_SLOT):
        return False
    if region.ecology.soil <= 0.4:
        return False
    prob = get_override(world, K_LOCUST_PROBABILITY, 0.15)
    if rng.random() >= prob:
        return False
    duration = rng.randint(2, 3)
    region.disaster_cooldowns["locust_swarm"] = duration
    for slot in range(3):
        rtype = region.resource_types[slot]
        if rtype in (ResourceType.GRAIN, ResourceType.BOTANICALS):
            region.resource_suspensions[rtype] = duration
    world.events_timeline.append(Event(
        turn=world.turn, event_type="locust_swarm",
        actors=[region.controller] if region.controller else [],
        description=f"A locust swarm descends on {region.name}, devouring the crops",
        importance=7,
    ))
    return True


def _check_flood(region: Region, world: WorldState, rng) -> bool:
    """Flood: river region, spring, water > 0.8."""
    from chronicler.resources import get_season_id
    season_id = get_season_id(world.turn)
    if region.river_mask == 0:
        return False
    if season_id != 0:  # Spring
        return False
    if region.ecology.water <= 0.8:
        return False
    prob = get_override(world, K_FLOOD_PROBABILITY, 0.20)
    if rng.random() >= prob:
        return False
    duration = rng.randint(1, 2)
    region.disaster_cooldowns["flood"] = duration
    region.capacity_modifier = 0.85
    region.ecology.soil = min(1.0, region.ecology.soil + 0.15)
    world.events_timeline.append(Event(
        turn=world.turn, event_type="flood",
        actors=[region.controller] if region.controller else [],
        description=f"The river floods {region.name}, depositing rich silt but damaging infrastructure",
        importance=6,
    ))
    return True


def _check_collapse(region: Region, world: WorldState, rng) -> bool:
    """Mine collapse: mountains, mineral resource, reserves < 0.3."""
    if region.terrain != "mountains":
        return False
    has_mineral = any(
        rtype in (ResourceType.ORE, ResourceType.PRECIOUS)
        for rtype in region.resource_types
        if rtype != EMPTY_SLOT
    )
    if not has_mineral:
        return False
    low_reserves = any(
        region.resource_reserves[slot] < 0.3
        for slot in range(3)
        if region.resource_types[slot] in (ResourceType.ORE, ResourceType.PRECIOUS)
    )
    if not low_reserves:
        return False
    prob = get_override(world, K_COLLAPSE_PROBABILITY, 0.10)
    if rng.random() >= prob:
        return False
    duration = rng.randint(3, 5)
    region.disaster_cooldowns["mine_collapse"] = duration
    spike = get_override(world, K_COLLAPSE_MORTALITY_SPIKE, 0.10)
    region.endemic_severity = min(0.15, region.endemic_severity + spike)
    for slot in range(3):
        if region.resource_types[slot] in (ResourceType.ORE, ResourceType.PRECIOUS):
            region.resource_suspensions[region.resource_types[slot]] = duration
    world.events_timeline.append(Event(
        turn=world.turn, event_type="mine_collapse",
        actors=[region.controller] if region.controller else [],
        description=f"A mine collapses in {region.name}, killing workers and halting extraction",
        importance=8,
    ))
    return True


def _check_drought(region: Region, world: WorldState, rng) -> bool:
    """Drought intensification: active DROUGHT, summer, water < 0.25."""
    from chronicler.resources import get_season_id
    from chronicler.climate import get_climate_phase
    season_id = get_season_id(world.turn)
    climate_phase = get_climate_phase(world.turn, world.climate_config)
    if climate_phase != ClimatePhase.DROUGHT:
        return False
    if season_id != 1:  # Summer
        return False
    if region.ecology.water >= 0.25:
        return False
    prob = get_override(world, K_DROUGHT_INTENSIFICATION_PROBABILITY, 0.25)
    if rng.random() >= prob:
        return False
    duration = rng.randint(4, 8)
    region.disaster_cooldowns["drought_intensification"] = duration
    region.capacity_modifier = 0.5
    region_map = get_region_map(world)
    for adj_name in region.adjacencies:
        adj = region_map.get(adj_name)
        if adj and adj.terrain == "desert" and not adj.disaster_cooldowns:
            adj.capacity_modifier = 0.5
            adj.disaster_cooldowns["drought_intensification"] = duration
    world.events_timeline.append(Event(
        turn=world.turn, event_type="drought_intensification",
        actors=[region.controller] if region.controller else [],
        description=f"The drought intensifies around {region.name}, devastating the region",
        importance=8,
    ))
    return True


def _check_ecological_recovery(region: Region, world: WorldState, rng) -> bool:
    """Ecological recovery: rare event restoring degraded resource yields."""
    prob = get_override(world, K_ECOLOGICAL_RECOVERY_PROBABILITY, 0.02)
    fraction = get_override(world, K_ECOLOGICAL_RECOVERY_FRACTION, 0.50)
    eligible_slots = [
        slot for slot in range(3)
        if region.resource_types[slot] != EMPTY_SLOT
        and region.resource_effective_yields[slot] < 0.8 * region.resource_base_yields[slot]
    ]
    if not eligible_slots:
        return False
    if rng.random() >= prob:
        return False
    slot = min(eligible_slots, key=lambda s: region.resource_effective_yields[s] / max(0.001, region.resource_base_yields[s]))
    base = region.resource_base_yields[slot]
    current = region.resource_effective_yields[slot]
    lost = base - current
    restore = lost * fraction
    region.resource_effective_yields[slot] = min(base, current + restore)
    world.events_timeline.append(Event(
        turn=world.turn, event_type="ecological_recovery",
        actors=[region.controller] if region.controller else [],
        description=f"The degraded resources of {region.name} show signs of recovery",
        importance=5,
    ))
    return True


def check_environmental_events(world: WorldState, rng) -> list[Event]:
    """Check condition-triggered environmental events for all regions.

    Uses per-region disaster_cooldowns (shared with climate system).
    M18 black swans use separate world.black_swan_cooldown.
    """
    initial_event_count = len(world.events_timeline)
    for region in world.regions:
        if region.disaster_cooldowns:
            continue
        fired = False
        for event_check in [_check_locust, _check_flood, _check_collapse, _check_drought]:
            if event_check(region, world, rng):
                fired = True
                break
        if not fired:
            _check_ecological_recovery(region, world, rng)
    return world.events_timeline[initial_event_count:]
