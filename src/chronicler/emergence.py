"""M18 Emergence and Chaos — black swans, stress, regression, ecological succession.

All cross-system emergence logic centralized in one module. Called from
existing turn phases via distributed hooks in simulation.py.
"""
from __future__ import annotations

import random

from chronicler.models import (
    ActiveCondition, Civilization, Event, PandemicRegion, Region,
    Resource, TechEra, WorldState,
)
from chronicler.resources import get_active_trade_routes
from chronicler.tech import _prev_era, remove_era_bonus
from chronicler.tuning import (
    K_BLACK_SWAN_BASE_PROB, K_BLACK_SWAN_COOLDOWN,
    K_REGRESSION_CAPITAL_COLLAPSE, K_REGRESSION_TWILIGHT, K_REGRESSION_BLACK_SWAN,
    get_override,
)
from chronicler.utils import clamp, STAT_FLOOR


# ---------------------------------------------------------------------------
# Stress Index & Cascade Severity
# ---------------------------------------------------------------------------

def compute_civ_stress(civ: Civilization, world: WorldState) -> int:
    """Compute per-civ stress from current world state. Returns 0-20."""
    stress = 0

    # Active wars: 3 per war (active_wars is list[tuple[str, str]])
    stress += sum(1 for w in world.active_wars if civ.name in w) * 3

    # Famine in controlled regions: 2 per famine region
    stress += sum(
        1 for r in world.regions
        if r.controller == civ.name and r.famine_cooldown > 0
    ) * 2

    # Active secession risk: 4 if stability < 20 with 3+ regions
    if civ.stability < 20 and len(civ.regions) >= 3:
        stress += 4

    # Active pandemic in controlled regions: 2 per infected region
    infected_region_names = {p.region_name for p in world.pandemic_state}
    stress += sum(
        1 for r in world.regions
        if r.controller == civ.name and r.name in infected_region_names
    ) * 2

    # Recent turbulent succession: 2 if general/usurper within last 5 turns
    if (civ.leader.succession_type in ("general", "usurper")
            and world.turn - civ.leader.reign_start <= 5):
        stress += 2

    # In twilight: 3
    if civ.decline_turns > 0:
        stress += 3

    # Active disaster conditions: 2 per qualifying condition
    stress += sum(
        1 for c in world.active_conditions
        if civ.name in c.affected_civs
        and c.condition_type in ("drought", "volcanic_winter")
    ) * 2

    # Overextension: 1 per region beyond 6
    stress += max(0, len(civ.regions) - 6)

    return min(stress, 20)


def compute_all_stress(world: WorldState) -> None:
    """Recompute stress for all civs and set global aggregate."""
    for civ in world.civilizations:
        civ.civ_stress = compute_civ_stress(civ, world)
    if world.civilizations:
        world.stress_index = max(c.civ_stress for c in world.civilizations)
    else:
        world.stress_index = 0


def get_severity_multiplier(civ: Civilization) -> float:
    """Return cascade severity multiplier based on civ stress. Range: 1.0-1.5."""
    return 1.0 + (civ.civ_stress / 20) * 0.5


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
    for civ in world.civilizations:
        if civ.name == civ_name:
            for gp in civ.great_persons:
                if gp.role == "merchant" and gp.active:
                    return len(partners) + 1
            break
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

    # Resource discovery: any region with 0 specialized resources
    if any(len(r.specialized_resources) == 0 for r in world.regions):
        eligible["resource_discovery"] = _EVENT_WEIGHTS["resource_discovery"]

    # Tech accident: any civ at INDUSTRIAL+
    industrial_plus = {TechEra.INDUSTRIAL, TechEra.INFORMATION}
    if any(c.tech_era in industrial_plus for c in world.civilizations):
        eligible["tech_accident"] = _EVENT_WEIGHTS["tech_accident"]

    return eligible


def check_black_swans(world: WorldState, seed: int) -> list[Event]:
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
    handlers = {
        "pandemic": _apply_pandemic_origin,
        "supervolcano": _apply_supervolcano,
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


def tick_pandemic(world: WorldState) -> list[Event]:
    """Per-turn pandemic tick: apply damage, spread, decrement timers. Phase 2."""
    if not world.pandemic_state:
        return []

    events: list[Event] = []
    infected_names = {p.region_name for p in world.pandemic_state}
    already_infected_or_recovered = set(infected_names) | set(world.pandemic_recovered)

    # --- Apply per-civ damage (aggregate, not per-region) ---
    civ_max_severity: dict[str, int] = {}
    for p in world.pandemic_state:
        for r in world.regions:
            if r.name == p.region_name and r.controller:
                current = civ_max_severity.get(r.controller, 0)
                civ_max_severity[r.controller] = max(current, p.severity)

    for civ_name, severity in civ_max_severity.items():
        civ = next((c for c in world.civilizations if c.name == civ_name), None)
        if civ is None:
            continue
        pop_loss = min(severity * 3, 12)
        eco_loss = min(severity * 2, 8)
        civ.population = clamp(civ.population - pop_loss, STAT_FLOOR.get("population", 1), 100)
        civ.economy = clamp(civ.economy - eco_loss, STAT_FLOOR.get("economy", 0), 100)

        # Leader kill check: 5% per infected civ
        rng = random.Random(world.seed + world.turn * 1013 + hash(civ_name))
        if rng.random() < 0.05:
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
    routes = get_active_trade_routes(world)
    trade_pairs = set()
    for a, b in routes:
        trade_pairs.add((a, b))
        trade_pairs.add((b, a))

    infected_controllers = set()
    for p in world.pandemic_state:
        for r in world.regions:
            if r.name == p.region_name and r.controller:
                infected_controllers.add(r.controller)

    new_infections: list[PandemicRegion] = []
    rng_spread = random.Random(world.seed + world.turn * 1019)
    for p in world.pandemic_state:
        source_region = next((r for r in world.regions if r.name == p.region_name), None)
        if source_region is None:
            continue
        for adj_name in source_region.adjacencies:
            if adj_name in already_infected_or_recovered:
                continue
            adj_region = next((r for r in world.regions if r.name == adj_name), None)
            if adj_region is None or adj_region.controller is None:
                continue
            adj_ctrl = adj_region.controller
            if any((ctrl, adj_ctrl) in trade_pairs for ctrl in infected_controllers):
                active_infra = len([i for i in adj_region.infrastructure if i.active])
                severity = min(3, 1 + active_infra // 2)
                duration = rng_spread.randint(4, 6)
                target_civ = next((c for c in world.civilizations if c.name == adj_ctrl), None)
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


def _apply_supervolcano(world: WorldState, seed: int) -> list[Event]:
    """Supervolcano: devastate a cluster of 3 adjacent regions."""
    rng = random.Random(seed + world.turn * 1021)

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
        region.fertility = 0.1
        region.infrastructure = []
        region.pending_build = None

        if region.controller:
            affected_civs.add(region.controller)
            civ = next((c for c in world.civilizations if c.name == region.controller), None)
            if civ:
                civ.population = clamp(civ.population - 20, STAT_FLOOR.get("population", 1), 100)
                civ.stability = clamp(civ.stability - 15, STAT_FLOOR.get("stability", 0), 100)

    world.climate_config.phase_offset += 1

    blast_names = {r.name for r in cluster}
    adjacent_civs: set[str] = set()
    for region in cluster:
        for adj_name in region.adjacencies:
            adj = next((r for r in world.regions if r.name == adj_name), None)
            if adj and adj.controller and adj.name not in blast_names:
                adjacent_civs.add(adj.controller)
    all_affected = affected_civs | adjacent_civs
    if all_affected:
        world.active_conditions.append(ActiveCondition(
            condition_type="volcanic_winter",
            affected_civs=list(all_affected),
            duration=5,
            severity=40,
        ))

    # M17: Folk hero asabiya bonus
    for civ_name in affected_civs:
        civ = next((c for c in world.civilizations if c.name == civ_name), None)
        if civ and civ.folk_heroes:
            civ.asabiya = min(1.0, civ.asabiya + 0.05)

    region_names = [r.name for r in cluster]
    events.append(Event(
        turn=world.turn,
        event_type="supervolcano",
        actors=list(affected_civs),
        description=f"A supervolcano erupts, devastating {', '.join(region_names)}",
        importance=10,
    ))

    return events


def _apply_resource_discovery(world: WorldState, seed: int) -> list[Event]:
    """Add strategic resources to a barren region."""
    rng = random.Random(seed + world.turn * 1031)

    barren = [r for r in world.regions if len(r.specialized_resources) == 0]
    if not barren:
        return []

    region = rng.choice(barren)
    count = rng.randint(1, 2)
    new_resources = rng.sample([Resource.FUEL, Resource.RARE_MINERALS], k=count)
    region.specialized_resources.extend(new_resources)

    controller = region.controller
    for adj_name in region.adjacencies:
        adj = next((r for r in world.regions if r.name == adj_name), None)
        if adj is None or adj.controller is None:
            continue
        adj_ctrl = adj.controller
        if controller and adj_ctrl != controller:
            if adj_ctrl in world.relationships and controller in world.relationships[adj_ctrl]:
                world.relationships[adj_ctrl][controller].disposition_drift -= 5
        elif controller is None:
            for other_adj_name in region.adjacencies:
                other_adj = next((r for r in world.regions if r.name == other_adj_name), None)
                if other_adj and other_adj.controller and other_adj.controller != adj_ctrl:
                    if adj_ctrl in world.relationships and other_adj.controller in world.relationships[adj_ctrl]:
                        world.relationships[adj_ctrl][other_adj.controller].disposition_drift -= 5

    resource_names = ", ".join(r.value for r in new_resources)
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

    target.fertility = max(0.0, round(target.fertility - 0.3, 4))

    affected_neighbors: set[str] = set()
    frontier = {target.name}
    for hop in range(max_hops):
        next_frontier: set[str] = set()
        for rname in frontier:
            region = next((r for r in world.regions if r.name == rname), None)
            if region:
                for adj in region.adjacencies:
                    if adj != target.name and adj not in affected_neighbors:
                        next_frontier.add(adj)
                        affected_neighbors.add(adj)
        frontier = next_frontier

    polluter_name = civ.name
    for rname in affected_neighbors:
        region = next((r for r in world.regions if r.name == rname), None)
        if region:
            region.fertility = max(0.0, round(region.fertility - 0.15, 4))
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
        culture_resistance = max(0.2, 1.0 - civ.culture / 200)
        best_prob = max(matching_probs) * culture_resistance
        rng = random.Random(world.seed + world.turn * 1037 + hash(civ.name))
        if rng.random() >= best_prob:
            continue

        old_era = civ.tech_era
        new_era = _prev_era(old_era)
        assert new_era is not None
        remove_era_bonus(civ, old_era)
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

def update_low_fertility_counters(world: WorldState) -> None:
    """Increment or reset low_fertility_turns for all regions. Called in Phase 9."""
    for region in world.regions:
        if region.fertility < 0.3:
            region.low_fertility_turns += 1
        else:
            region.low_fertility_turns = 0


def tick_terrain_succession(world: WorldState) -> list[Event]:
    """Check and apply terrain transitions. Called at end of Phase 9."""
    events: list[Event] = []

    for region in world.regions:
        for rule in world.terrain_transition_rules:
            if region.terrain != rule.from_terrain:
                continue

            if rule.condition == "low_fertility":
                if region.low_fertility_turns >= rule.threshold_turns:
                    _apply_transition(region, rule)
                    events.append(Event(
                        turn=world.turn,
                        event_type="terrain_transition",
                        actors=[region.controller] if region.controller else [],
                        description=f"{region.name} transforms from {rule.from_terrain} to {rule.to_terrain}",
                        importance=6,
                    ))

            elif rule.condition == "depopulated":
                if region.controller is not None:
                    continue
                if region.depopulated_since is None:
                    continue
                if world.turn - region.depopulated_since >= rule.threshold_turns:
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
    """Apply a terrain transition to a region."""
    if rule.from_terrain == "forest" and rule.to_terrain == "plains":
        region.terrain = "plains"
        region.carrying_capacity = min(100, region.carrying_capacity + 20)
        region.fertility = 0.5
        region.low_fertility_turns = 0
    elif rule.from_terrain == "plains" and rule.to_terrain == "forest":
        region.terrain = "forest"
        region.carrying_capacity = max(1, region.carrying_capacity - 10)
        region.fertility = 0.7
        region.depopulated_since = None
