"""Ten-phase simulation engine for the civilization chronicle.

Turn phases:
1. Environment — natural events (drought, plague, earthquake)
2. Automatic Effects — military maintenance, trade income (NEW)
3. Production — income, population growth
4. Technology — tech advancement checks
5. Action — each civ takes one action from constrained menu
6. Cultural Milestones — check cultural threshold for named works
7. Random Events — 0-1 external events from cascading probability table
8. Leader Dynamics — trait evolution for all living leaders
9. Fertility — fertility degradation/recovery, famine checks (NEW)
10. Consequences — resolve cascading effects, tick condition durations

The engine is deterministic given a seed, except for Phase 5 (action
selection) and narration which accept callbacks.
"""
from __future__ import annotations

import random
from typing import Callable, Protocol

from chronicler.events import (
    ENVIRONMENT_EVENTS,
    apply_probability_cascade,
    roll_for_event,
)
from chronicler.models import (
    ActionType,
    ActiveCondition,
    Civilization,
    Disposition,
    Event,
    Leader,
    NamedEvent,
    TechEra,
    WorldState,
)
from chronicler.tech import check_tech_advancement
from chronicler.utils import clamp, STAT_FLOOR
from chronicler.leaders import (
    generate_successor, apply_leader_legacy, check_trait_evolution,
    check_rival_fall,
)
from chronicler.named_events import generate_tech_breakthrough_name
from chronicler.action_engine import resolve_action
from chronicler.succession import (
    compute_crisis_probability, trigger_crisis, tick_crisis,
    resolve_crisis, is_in_crisis, decay_grudges,
    apply_exile_pretender_drain, check_exile_restoration,
)
from chronicler.culture import tick_prestige, apply_value_drift, tick_cultural_assimilation, check_cultural_victories
from chronicler.movements import tick_movements


# --- Type aliases for callbacks ---

ActionSelector = Callable[[Civilization, WorldState], ActionType]
Narrator = Callable[[WorldState, list[Event]], str]


# --- Helpers ---

def _get_civ(world: WorldState, name: str) -> Civilization | None:
    for c in world.civilizations:
        if c.name == name:
            return c
    return None


# --- Phase 1: Environment ---

def phase_environment(world: WorldState, seed: int) -> list[Event]:
    """Check for natural disasters. At most one environment event per turn."""
    from chronicler.climate import get_climate_phase, check_disasters, process_migration

    events: list[Event] = []

    # Climate-driven disasters and migration
    climate_phase = get_climate_phase(world.turn, world.climate_config)

    # Decrement disaster cooldowns and resource suspensions
    for region in world.regions:
        for k in list(region.disaster_cooldowns):
            region.disaster_cooldowns[k] -= 1
        region.disaster_cooldowns = {k: v for k, v in region.disaster_cooldowns.items() if v > 0}
        for k in list(region.resource_suspensions):
            region.resource_suspensions[k] -= 1
        region.resource_suspensions = {k: v for k, v in region.resource_suspensions.items() if v > 0}

    disaster_events = check_disasters(world, climate_phase)
    events.extend(disaster_events)

    migration_events = process_migration(world)
    events.extend(migration_events)

    # Legacy environment events (drought, plague, earthquake)
    event = roll_for_event(
        world.event_probabilities,
        turn=world.turn,
        seed=seed,
        allowed_types=ENVIRONMENT_EVENTS,
    )
    if event is not None:
        rng = random.Random(seed + 1)
        affected = rng.sample(
            world.civilizations,
            k=max(1, len(world.civilizations) // 2),
        )
        event.actors = [c.name for c in affected]

        if event.event_type == "drought":
            for civ in affected:
                civ.stability = clamp(civ.stability - 10, STAT_FLOOR["stability"], 100)
                civ.economy = clamp(civ.economy - 10, STAT_FLOOR["economy"], 100)
            world.active_conditions.append(
                ActiveCondition(
                    condition_type="drought",
                    affected_civs=event.actors,
                    duration=3,
                    severity=50,
                )
            )
        elif event.event_type == "plague":
            for civ in affected:
                civ.population = clamp(civ.population - 10, STAT_FLOOR["population"], 100)
                civ.stability = clamp(civ.stability - 10, STAT_FLOOR["stability"], 100)
            world.active_conditions.append(
                ActiveCondition(
                    condition_type="plague",
                    affected_civs=event.actors,
                    duration=4,
                    severity=60,
                )
            )
        elif event.event_type == "earthquake":
            for civ in affected:
                civ.economy = clamp(civ.economy - 10, STAT_FLOOR["economy"], 100)

        world.event_probabilities = apply_probability_cascade(
            event.event_type, world.event_probabilities
        )
        events.append(event)

    return events


# --- Phase 2: Automatic Effects ---

def apply_automatic_effects(world: WorldState) -> list[Event]:
    """Phase 2: Automatic per-turn effects — maintenance, trade, specialization, mercs."""
    from chronicler.resources import get_active_trade_routes, get_self_trade_civs
    from chronicler.infrastructure import tick_infrastructure
    events: list[Event] = []

    # 0. Infrastructure tick (advance pending builds, mine degradation)
    infra_events = tick_infrastructure(world)
    events.extend(infra_events)

    # 1. Military maintenance: free up to 30, then (mil-30)//10 per turn
    for civ in world.civilizations:
        if civ.military > 30:
            cost = (civ.military - 30) // 10
            civ.treasury -= cost

    # 2. Trade income
    cross_routes = get_active_trade_routes(world)
    for civ_a, civ_b in cross_routes:
        a = _get_civ(world, civ_a)
        b = _get_civ(world, civ_b)
        if a:
            a.treasury += 2
        if b:
            b.treasury += 2
    for civ_name in get_self_trade_civs(world):
        c = _get_civ(world, civ_name)
        if c:
            c.treasury += 3

    # Embargo set — used by both specialization and black market sections
    embargo_set = {(a, b) for a, b in world.embargoes} | {(b, a) for a, b in world.embargoes}

    # 3. Economic specialization
    for civ in world.civilizations:
        controlled = [r for r in world.regions if r.controller == civ.name]
        if not controlled:
            continue
        resource_counts: dict = {}
        for r in controlled:
            for res in r.specialized_resources:
                resource_counts[res] = resource_counts.get(res, 0) + 1
        if not resource_counts:
            continue
        from chronicler.models import Resource
        primary = max(resource_counts, key=lambda r: resource_counts[r])
        civ_routes = [(a, b) for a, b in cross_routes if civ.name in (a, b)]
        if not civ_routes:
            continue
        primary_routes = 0
        for a, b in civ_routes:
            route_regions = [r for r in world.regions
                            if r.controller in (a, b) and primary in r.specialized_resources]
            if route_regions:
                primary_routes += 1
        if len(civ_routes) > 0 and primary_routes / len(civ_routes) > 0.6:
            embargoed_routes = [(a, b) for a, b in civ_routes
                               if (a, b) in embargo_set or (b, a) in embargo_set]
            if embargoed_routes:
                penalty = int(civ.economy * 0.20)
                civ.treasury -= penalty
            else:
                bonus = int(civ.economy * 0.15)
                civ.treasury += bonus

    # 4. Black market leakage for embargoed civs
    for civ in world.civilizations:
        if not any(civ.name in pair for pair in embargo_set):
            continue
        # Check for adjacent non-embargoed neighbors
        for r in world.regions:
            if r.controller != civ.name:
                continue
            for adj_name in r.adjacencies:
                adj = next((ar for ar in world.regions if ar.name == adj_name), None)
                if adj and adj.controller and adj.controller != civ.name:
                    pair = tuple(sorted([civ.name, adj.controller]))
                    if pair not in embargo_set:
                        civ.treasury += 1  # 30% of normal trade (2), min 1
                        civ.stability = clamp(civ.stability - 3, STAT_FLOOR["stability"], 100)
                        break  # Only one black market route per civ per turn
            break  # Only check first controlled region for simplicity

    # 5. Ongoing war costs: -3/turn per active war
    for war in world.active_wars:
        for civ_name in war:
            c = _get_civ(world, civ_name)
            if c:
                c.treasury -= 3
                if c.treasury <= 0:
                    c.stability = clamp(c.stability - 5, STAT_FLOOR["stability"], 100)

    # 6. Mercenary system
    MAX_MERCS = 3
    for civ in world.civilizations:
        # Check merc pressure: military >> income
        if civ.military > 30 and civ.last_income > 0 and civ.military > civ.last_income * 3:
            civ.merc_pressure_turns += 1
        else:
            civ.merc_pressure_turns = max(0, civ.merc_pressure_turns - 1)
        # Spawn mercenary company after 3 turns of pressure
        if civ.merc_pressure_turns >= 3 and len(world.mercenary_companies) < MAX_MERCS:
            strength = min(10, civ.military // 5)
            civ.military = clamp(civ.military - strength, STAT_FLOOR["military"], 100)
            region = civ.regions[0] if civ.regions else "unknown"
            world.mercenary_companies.append({
                "strength": strength, "origin_civ": civ.name,
                "location": region, "available": True, "hired_by": None,
            })
            civ.merc_pressure_turns = 0
    # Mercenary hiring: underdog priority in active wars
    for merc in world.mercenary_companies:
        if not merc["available"] or merc["hired_by"]:
            continue
        # Find weakest belligerent with treasury
        candidates = []
        for war in world.active_wars:
            for civ_name in war:
                c = _get_civ(world, civ_name)
                if c and c.treasury >= 10:
                    candidates.append(c)
        if candidates:
            candidates.sort(key=lambda c: (c.military, -c.treasury))
            hirer = candidates[0]
            hirer.treasury -= 10
            hirer.military = clamp(hirer.military + merc["strength"], STAT_FLOOR["military"], 100)
            merc["hired_by"] = hirer.name
            merc["available"] = False
    # Decay unhired mercs
    for merc in world.mercenary_companies:
        if merc["available"] and not merc["hired_by"]:
            merc["strength"] -= 2
    # Disband hired mercs whose war ended
    for merc in list(world.mercenary_companies):
        if merc["hired_by"]:
            still_at_war = any(merc["hired_by"] in w for w in world.active_wars)
            if not still_at_war:
                merc["hired_by"] = None
                merc["available"] = True
    # Remove dead mercs
    world.mercenary_companies = [m for m in world.mercenary_companies if m["strength"] > 0]

    # 7. Reset last_income (re-accumulated during Phase 3)
    for civ in world.civilizations:
        civ.last_income = 0

    from chronicler.politics import apply_governing_costs, collect_tribute
    from chronicler.politics import apply_proxy_wars, apply_exile_effects
    from chronicler.politics import (
        apply_balance_of_power, apply_fallen_empire, apply_twilight,
        apply_long_peace, update_peak_regions,
    )
    events.extend(apply_governing_costs(world))
    events.extend(collect_tribute(world))
    events.extend(apply_proxy_wars(world))
    events.extend(apply_exile_effects(world))
    events.extend(apply_balance_of_power(world))
    events.extend(apply_fallen_empire(world))
    events.extend(apply_twilight(world))
    events.extend(apply_long_peace(world))
    update_peak_regions(world)

    # Trade knowledge sharing (fog of war)
    from chronicler.exploration import tick_trade_knowledge_sharing
    knowledge_events = tick_trade_knowledge_sharing(world)
    events.extend(knowledge_events)

    # M17b: Exile pretender stability drain
    apply_exile_pretender_drain(world)

    # M17d: Tradition ongoing effects
    from chronicler.traditions import apply_tradition_effects
    apply_tradition_effects(world)

    # M17c: Hostage turn ticking
    from chronicler.relationships import tick_hostages
    tick_hostages(world)

    return events


# --- Phase 3: Production ---

def phase_production(world: WorldState) -> None:
    """Generate income and adjust population for each civilization."""
    from chronicler.terrain import effective_capacity
    for civ in world.civilizations:
        # Base income
        income = civ.economy // 5 + len(civ.regions) * 2
        # Condition penalty
        penalty = sum(c.severity for c in world.active_conditions if civ.name in c.affected_civs)
        civ.treasury += max(0, income - penalty)
        # Track last_income for mercenary spawn
        civ.last_income = max(0, income - penalty)
        # Population
        region_capacity = sum(
            effective_capacity(r)
            for r in world.regions if r.controller == civ.name
        )
        max_pop = min(100, region_capacity)
        if civ.economy > civ.population and civ.stability > 20 and civ.population < max_pop:
            civ.population = clamp(civ.population + 5, STAT_FLOOR["population"], 100)
        elif civ.stability <= 10 and civ.population > 1:
            civ.population = clamp(civ.population - 5, STAT_FLOOR["population"], 100)

    # M16a: Prestige decay and trade bonus
    tick_prestige(world)


# --- Phase 5: Action ---

_CRISIS_HALVED_STATS = ("economy", "culture", "military", "stability", "population")


def phase_action(
    world: WorldState,
    action_selector: ActionSelector,
) -> list[Event]:
    """Each civilization takes one action from the constrained menu."""
    events: list[Event] = []

    for civ in world.civilizations:
        # Snapshot stat values before action (for crisis halving)
        in_crisis = is_in_crisis(civ)
        pre_stats: dict[str, int] = {}
        if in_crisis:
            pre_stats = {s: getattr(civ, s) for s in _CRISIS_HALVED_STATS}

        action = action_selector(civ, world)
        event = resolve_action(civ, action, world)

        # Crisis halving: reduce positive stat gains by 50%
        if in_crisis:
            for stat in _CRISIS_HALVED_STATS:
                before = pre_stats[stat]
                after = getattr(civ, stat)
                if after > before:
                    halved = before + (after - before) // 2
                    setattr(civ, stat, max(halved, STAT_FLOOR.get(stat, 0)))

        # Track action in history (for streak breaker)
        history = world.action_history.setdefault(civ.name, [])
        history.append(action.value)
        if len(history) > 5:
            world.action_history[civ.name] = history[-5:]

        # Track action counts (for trait evolution)
        civ.action_counts[action.value] = civ.action_counts.get(action.value, 0) + 1

        events.append(event)

    return events


# --- Asabiya dynamics (Turchin metaethnic frontier model) ---

def apply_asabiya_dynamics(world: WorldState) -> None:
    """Update asabiya (collective solidarity) for each civilization."""
    r0 = 0.05   # Growth rate at frontiers
    delta = 0.02  # Decay rate in interior

    disp_threat = {Disposition.HOSTILE, Disposition.SUSPICIOUS}

    for civ in world.civilizations:
        has_frontier = False
        if civ.name in world.relationships:
            for _other, rel in world.relationships[civ.name].items():
                if rel.disposition in disp_threat:
                    has_frontier = True
                    break

        s = civ.asabiya
        if has_frontier:
            s = s + r0 * s * (1 - s)
        else:
            s = s - delta * s

        # Folk hero asabiya bonus: permanent +0.03 per hero, applied as a floor
        from chronicler.traditions import compute_folk_hero_asabiya_bonus
        folk_bonus = compute_folk_hero_asabiya_bonus(civ)
        if folk_bonus > 0:
            s = s + folk_bonus * 0.1  # scale per-turn contribution

        civ.asabiya = round(max(0.0, min(1.0, s)), 4)


# --- Phase 7: Random events ---

def phase_random_events(world: WorldState, seed: int) -> list[Event]:
    """Roll for 0-1 random external events (non-environment)."""
    events: list[Event] = []
    non_env = [k for k in world.event_probabilities if k not in ENVIRONMENT_EVENTS]
    event = roll_for_event(
        world.event_probabilities,
        turn=world.turn,
        seed=seed,
        allowed_types=non_env,
    )
    if event is not None:
        rng = random.Random(seed + 2)
        event.actors = [rng.choice(world.civilizations).name]

        world.event_probabilities = apply_probability_cascade(
            event.event_type, world.event_probabilities
        )

        affected_civ = _get_civ(world, event.actors[0])
        if affected_civ:
            _apply_event_effects(event.event_type, affected_civ, world)

        events.append(event)

    from chronicler.politics import check_congress
    events.extend(check_congress(world))
    return events


def _apply_event_effects(event_type: str, civ: Civilization, world: WorldState) -> None:
    """Apply mechanical stat changes for a random event."""
    if event_type == "leader_death":
        import random as _random
        old_leader = civ.leader
        old_leader.alive = False
        civ.stability = clamp(civ.stability - 20, STAT_FLOOR["stability"], 100)
        apply_leader_legacy(civ, old_leader, world)
        check_rival_fall(civ, old_leader.name, world)
        # Check whether death triggers a succession crisis instead of immediate succession
        crisis_prob = compute_crisis_probability(civ, world)
        rng = _random.Random(world.seed + world.turn + hash(civ.name))
        if crisis_prob > 0.0 and rng.random() < crisis_prob and not is_in_crisis(civ):
            trigger_crisis(civ, world)
        else:
            new_leader = generate_successor(civ, world, seed=world.turn * 100)
            from chronicler.succession import inherit_grudges
            inherit_grudges(old_leader, new_leader)
            civ.leader = new_leader
    elif event_type == "rebellion":
        civ.stability = clamp(civ.stability - 20, STAT_FLOOR["stability"], 100)
        civ.military = clamp(civ.military - 10, STAT_FLOOR["military"], 100)
    elif event_type == "discovery":
        civ.culture = clamp(civ.culture + 10, STAT_FLOOR["culture"], 100)
        civ.economy = clamp(civ.economy + 10, STAT_FLOOR["economy"], 100)
    elif event_type == "religious_movement":
        civ.culture = clamp(civ.culture + 10, STAT_FLOOR["culture"], 100)
        civ.stability = clamp(civ.stability - 10, STAT_FLOOR["stability"], 100)
    elif event_type == "cultural_renaissance":
        civ.culture = clamp(civ.culture + 20, STAT_FLOOR["culture"], 100)
        civ.stability = clamp(civ.stability + 10, STAT_FLOOR["stability"], 100)
    elif event_type == "migration":
        civ.population = clamp(civ.population + 10, STAT_FLOOR["population"], 100)
        civ.stability = clamp(civ.stability - 10, STAT_FLOOR["stability"], 100)
    elif event_type == "border_incident":
        civ.stability = clamp(civ.stability - 10, STAT_FLOOR["stability"], 100)


def apply_injected_event(
    event_type: str, target_civ_name: str, world: WorldState
) -> list[Event]:
    """Process a manually injected event targeting a single civ."""
    civ = _get_civ(world, target_civ_name)
    if civ is None:
        return []

    event = Event(
        turn=world.turn,
        event_type=event_type,
        actors=[target_civ_name],
        description=f"[Injected] {event_type} strikes {target_civ_name}",
        importance=7,
    )

    if event_type == "drought":
        civ.stability = clamp(civ.stability - 10, STAT_FLOOR["stability"], 100)
        civ.economy = clamp(civ.economy - 10, STAT_FLOOR["economy"], 100)
        world.active_conditions.append(
            ActiveCondition(
                condition_type="drought",
                affected_civs=[target_civ_name],
                duration=3,
                severity=50,
            )
        )
    elif event_type == "plague":
        civ.population = clamp(civ.population - 10, STAT_FLOOR["population"], 100)
        civ.stability = clamp(civ.stability - 10, STAT_FLOOR["stability"], 100)
        world.active_conditions.append(
            ActiveCondition(
                condition_type="plague",
                affected_civs=[target_civ_name],
                duration=4,
                severity=60,
            )
        )
    elif event_type == "earthquake":
        civ.economy = clamp(civ.economy - 10, STAT_FLOOR["economy"], 100)
    else:
        _apply_event_effects(event_type, civ, world)

    world.event_probabilities = apply_probability_cascade(
        event_type, world.event_probabilities
    )

    return [event]


# --- Phase 10: Consequences ---

def phase_consequences(world: WorldState) -> list[Event]:
    """Resolve cascading effects and tick condition durations. Returns collapse events."""
    for condition in world.active_conditions:
        condition.duration -= 1
        for civ_name in condition.affected_civs:
            civ = _get_civ(world, civ_name)
            if civ and condition.severity >= 50:
                civ.stability = clamp(civ.stability - 10, STAT_FLOOR["stability"], 100)

    world.active_conditions = [c for c in world.active_conditions if c.duration > 0]

    # M16b: Movement lifecycle (runs before value drift — movements feed disposition)
    tick_movements(world)

    # M16a: Cultural effects (order matters — assimilation drain feeds asabiya)
    apply_value_drift(world)
    tick_cultural_assimilation(world)

    # M16c: Cultural victory tracking (runs LAST in culture effects)
    check_cultural_victories(world)

    apply_asabiya_dynamics(world)

    from chronicler.politics import (
        check_capital_loss, check_secession, check_vassal_rebellion,
        check_federation_formation, check_federation_dissolution, update_allied_turns,
    )
    collapse_events: list[Event] = []
    collapse_events.extend(check_capital_loss(world))
    collapse_events.extend(check_secession(world))
    update_allied_turns(world)
    collapse_events.extend(check_vassal_rebellion(world))
    collapse_events.extend(check_federation_formation(world))
    collapse_events.extend(check_federation_dissolution(world))
    from chronicler.politics import check_proxy_detection, check_restoration
    from chronicler.politics import check_twilight_absorption, update_decline_tracking
    collapse_events.extend(check_proxy_detection(world))
    collapse_events.extend(check_restoration(world))
    collapse_events.extend(check_twilight_absorption(world))
    update_decline_tracking(world)
    for civ in world.civilizations:
        if civ.asabiya < 0.1 and civ.stability <= 20:
            if len(civ.regions) > 1:
                lost = civ.regions[1:]
                civ.regions = civ.regions[:1]
                for region in world.regions:
                    if region.name in lost:
                        region.controller = None
                civ.military = clamp(civ.military // 2, STAT_FLOOR["military"], 100)
                civ.economy = clamp(civ.economy // 2, STAT_FLOOR["economy"], 100)
                collapse_events.append(Event(
                    turn=world.turn,
                    event_type="collapse",
                    actors=[civ.name],
                    description=f"{civ.name} collapsed under internal pressure.",
                    importance=10,
                ))

    # Depopulation tracking for ruins
    from chronicler.exploration import mark_depopulated
    for region in world.regions:
        if region.controller is None and region.depopulated_since is None:
            mark_depopulated(region, world.turn)
        elif region.controller is not None and region.depopulated_since is not None:
            region.depopulated_since = None
            region.ruin_quality = 0

    # --- M17d: Event counts and tradition acquisition (runs before great person generation) ---
    from chronicler.traditions import update_event_counts, check_tradition_acquisition
    update_event_counts(world)
    check_tradition_acquisition(world)

    # --- M17: Great Person Consequences ---
    from chronicler.great_persons import check_great_person_generation, check_lifespan_expiry
    for civ in world.civilizations:
        if not civ.regions:
            continue
        check_great_person_generation(civ, world)
        check_lifespan_expiry(civ, world)

    # M17b: Exile restoration checks
    collapse_events.extend(check_exile_restoration(world))

    # M17c: Character relationship formation
    from chronicler.relationships import check_rivalry_formation, check_mentorship_formation, check_marriage_formation
    check_rivalry_formation(world)
    check_mentorship_formation(world)
    check_marriage_formation(world)

    return collapse_events


# --- Phase 4: Technology ---

def phase_technology(world: WorldState) -> list[Event]:
    """Phase 4: Check tech advancement for each civ."""
    events = []
    for civ in world.civilizations:
        event = check_tech_advancement(civ, world)
        if event:
            events.append(event)
            # Increment tech_advanced so great person generation can detect era advance
            civ.event_counts["tech_advanced"] = civ.event_counts.get("tech_advanced", 0) + 1
            name = generate_tech_breakthrough_name(civ.tech_era)
            world.named_events.append(NamedEvent(
                name=name, event_type="tech_breakthrough", turn=world.turn,
                actors=[civ.name], description=event.description, importance=7,
            ))
            # M16c: Check for paradigm shift
            from chronicler.tech import ERA_BONUSES
            era_bonuses = ERA_BONUSES.get(civ.tech_era, {})
            has_paradigm_shift = any(
                k in era_bonuses and era_bonuses[k] != 1.0
                for k in ("military_multiplier", "fortification_multiplier", "culture_projection_range")
            )
            if has_paradigm_shift:
                world.named_events.append(NamedEvent(
                    name=f"Paradigm Shift: {civ.tech_era.value.title()} Era",
                    event_type="paradigm_shift",
                    turn=world.turn,
                    actors=[civ.name],
                    description=f"{civ.name} enters the {civ.tech_era.value.title()} era, fundamentally changing the rules of engagement.",
                    importance=7,
                ))
    return events


def phase_cultural_milestones(world: WorldState) -> list[Event]:
    """Check cultural milestone thresholds for named works."""
    from chronicler.named_events import generate_cultural_work
    events = []
    for civ in world.civilizations:
        for threshold in [80, 100]:
            marker = f"culture_{threshold}"
            if civ.culture >= threshold and marker not in civ.cultural_milestones:
                civ.cultural_milestones.append(marker)
                name = generate_cultural_work(civ, world, seed=world.seed)
                ne = NamedEvent(
                    name=name, event_type="cultural_work", turn=world.turn,
                    actors=[civ.name], description=f"{civ.name} produces a cultural masterwork",
                    importance=6,
                )
                world.named_events.append(ne)
                # M16a: Cultural works enhancement
                civ.asabiya = min(1.0, civ.asabiya + 0.05)
                civ.culture = clamp(civ.culture + 5, STAT_FLOOR["culture"], 100)
                civ.prestige += 2
                events.append(Event(
                    turn=world.turn, event_type="cultural_work", actors=[civ.name],
                    description=ne.description, importance=6,
                ))
    return events


def phase_leader_dynamics(world: WorldState, seed: int) -> list[Event]:
    """Phase 8: Handle trait evolution, crisis ticks, grudge decay for all living leaders."""
    events = []
    for civ in world.civilizations:
        secondary = check_trait_evolution(civ, world)
        if secondary:
            events.append(Event(
                turn=world.turn, event_type="trait_evolution", actors=[civ.name],
                description=f"{civ.leader.name} of {civ.name} has become known as a {secondary}",
                importance=4,
            ))

        # Crisis state machine: tick and auto-resolve when timer hits 0
        if is_in_crisis(civ):
            tick_crisis(civ, world)
            if civ.succession_crisis_turns_remaining == 0:
                crisis_events = resolve_crisis(civ, world)
                events.extend(crisis_events)

        # Grudge decay — per-grudge rival alive status handled inside decay_grudges
        if civ.leader.grudges:
            decay_grudges(civ.leader, current_turn=world.turn, world=world)

    return events


# --- Phase 9: Fertility ---

def phase_fertility(world: WorldState) -> list[Event]:
    """Phase 9: Fertility degradation, recovery, and famine checks."""
    from chronicler.terrain import terrain_fertility_cap, effective_capacity
    from chronicler.climate import get_climate_phase, climate_degradation_multiplier
    from chronicler.models import ClimatePhase, InfrastructureType

    climate_phase = get_climate_phase(world.turn, world.climate_config)

    for region in world.regions:
        if region.controller is None:
            continue
        civ = _get_civ(world, region.controller)
        if civ is None or not civ.regions:
            continue

        # Compute fertility cap with climate modifier + irrigation
        base_cap = terrain_fertility_cap(region)
        if region.terrain == "tundra":
            if climate_phase == ClimatePhase.WARMING:
                base_cap = base_cap * 2.0
            elif climate_phase == ClimatePhase.COOLING:
                base_cap = base_cap * 0.3
        irrigation_bonus = 0.15 if any(
            i.type == InfrastructureType.IRRIGATION and i.active
            for i in region.infrastructure
        ) else 0.0
        cap = min(base_cap + irrigation_bonus, 1.0)

        # Climate degradation multiplier
        multiplier = climate_degradation_multiplier(
            region.terrain, climate_phase, world.climate_config.severity
        )

        eff_cap = effective_capacity(region)
        region_pop = civ.population // len(civ.regions) if civ.regions else 0

        if region_pop > eff_cap:
            region.fertility = max(0.0, round(region.fertility - 0.02 * multiplier, 4))
        elif region_pop < eff_cap * 0.5:
            region.fertility = min(cap, round(region.fertility + 0.01, 4))

        if region.famine_cooldown > 0:
            region.famine_cooldown -= 1
    famine_events = _check_famine(world)

    # M17d: Apply fertility floor for food_stockpiling tradition
    from chronicler.traditions import apply_fertility_floor
    apply_fertility_floor(world)

    return famine_events


def _check_famine(world: WorldState) -> list[Event]:
    """Check for famine in low-fertility regions."""
    events = []
    for region in world.regions:
        if region.controller is None or region.fertility >= 0.3 or region.famine_cooldown > 0:
            continue
        civ = _get_civ(world, region.controller)
        if civ is None:
            continue
        civ.population = clamp(civ.population - 15, STAT_FLOOR["population"], 100)
        civ.stability = clamp(civ.stability - 10, STAT_FLOOR["stability"], 100)
        region.famine_cooldown = 5
        for adj_name in region.adjacencies:
            adj = next((r for r in world.regions if r.name == adj_name), None)
            if adj and adj.controller and adj.controller != civ.name:
                neighbor = _get_civ(world, adj.controller)
                if neighbor:
                    neighbor.population = clamp(neighbor.population + 5, STAT_FLOOR["population"], 100)
                    neighbor.stability = clamp(neighbor.stability - 5, STAT_FLOOR["stability"], 100)
        events.append(Event(
            turn=world.turn, event_type="famine", actors=[civ.name],
            description=f"Famine strikes {region.name}, devastating {civ.name}.",
            importance=8,
        ))
    return events


# --- Turn orchestrator ---

def run_turn(
    world: WorldState,
    action_selector: ActionSelector,
    narrator: Narrator,
    seed: int = 0,
) -> str:
    """Execute one complete turn of the simulation. Returns chronicle text."""
    turn_events: list[Event] = []

    # Phase 1: Environment
    turn_events.extend(phase_environment(world, seed=seed))

    # Phase 2: Automatic Effects (NEW)
    turn_events.extend(apply_automatic_effects(world))

    # Phase 3: Production
    phase_production(world)

    # Phase 4: Technology
    turn_events.extend(phase_technology(world))

    # Phase 5: Action (selection + resolution)
    turn_events.extend(phase_action(world, action_selector=action_selector))

    # Phase 6: Cultural Milestones
    turn_events.extend(phase_cultural_milestones(world))

    # Phase 7: Random Events
    turn_events.extend(phase_random_events(world, seed=seed + 100))

    # Phase 8: Leader Dynamics
    turn_events.extend(phase_leader_dynamics(world, seed=seed))

    # Phase 9: Fertility
    turn_events.extend(phase_fertility(world))

    # Phase 10: Consequences
    turn_events.extend(phase_consequences(world))

    # Record events
    world.events_timeline.extend(turn_events)

    # Chronicle (narrative generation)
    chronicle_text = narrator(world, turn_events)

    # Advance turn counter
    world.turn += 1

    return chronicle_text


def get_injectable_event_types() -> list[str]:
    """Return sorted list of event types that can be injected."""
    from chronicler.world_gen import DEFAULT_EVENT_PROBABILITIES
    return sorted(DEFAULT_EVENT_PROBABILITIES.keys())
