"""Ten-phase simulation engine for the civilization chronicle.

Turn phases:
1. Environment — climate, conditions, terrain transitions
2. Economy — trade routes, goods production, income, tribute, treasury
3. Politics — governing costs, vassal checks, congress, secession
4. Military — maintenance, war costs, mercenaries
5. Diplomacy — disposition drift, federation checks, peace
6. Culture — prestige, value drift, assimilation, movements
7. Tech — advancement rolls, focus selection, focus effects
8. Action selection + resolution (action engine)
9. Ecology — soil/water/forest tick, terrain transitions, famine checks
--- Agent tick (between Phase 9 and 10) ---
10. Consequences — emergence, factions, succession, named events, snapshot

The engine is deterministic given a seed. LLM narrates, never decides.
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
    CivShock,
    Disposition,
    EMPTY_SLOT,
    Event,
    Leader,
    NamedEvent,
    TechEra,
    WorldState,
)
from chronicler.accumulator import normalize_shock
from chronicler.tech import check_tech_advancement
from chronicler.utils import (
    civ_index,
    clamp,
    get_civ,
    STAT_FLOOR,
    sync_civ_population,
    sync_all_populations,
    distribute_pop_loss,
    drain_region_pop,
    add_region_pop,
)
from chronicler.emergence import get_severity_multiplier
from chronicler.leaders import (
    generate_successor, apply_leader_legacy, check_trait_evolution,
    check_rival_fall,
)
from chronicler.named_events import generate_tech_breakthrough_name
from chronicler.tech_focus import TechFocus, select_tech_focus, apply_focus_effects, remove_focus_effects
from chronicler.action_engine import resolve_action
from chronicler.succession import (
    compute_crisis_probability, trigger_crisis, tick_crisis,
    resolve_crisis, is_in_crisis, decay_grudges,
    apply_exile_pretender_drain, check_exile_restoration,
)
from chronicler.culture import tick_prestige, apply_value_drift, tick_cultural_assimilation, check_cultural_victories
from chronicler.movements import tick_movements
from chronicler.tuning import (
    K_DROUGHT_STABILITY, K_DROUGHT_ONGOING, K_PLAGUE_STABILITY,
    K_FAMINE_STABILITY, K_WAR_COST_STABILITY,
    K_CONDITION_ONGOING_DRAIN,
    K_MILITARY_FREE_THRESHOLD,
    K_REBELLION_STABILITY, K_LEADER_DEATH_STABILITY,
    K_BORDER_INCIDENT_STABILITY, K_RELIGIOUS_MOVEMENT_STABILITY,
    K_MIGRATION_STABILITY, K_STABILITY_RECOVERY,
    get_override,
)


# --- Type aliases for callbacks ---

ActionSelector = Callable[[Civilization, WorldState], ActionType]
Narrator = Callable[[WorldState, list[Event]], str]


# --- Phase 1: Environment ---

def phase_environment(world: WorldState, seed: int, acc=None) -> list[Event]:
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
        # M35b: Reset capacity_modifier when all disaster cooldowns expire
        if not region.disaster_cooldowns and region.capacity_modifier != 1.0:
            region.capacity_modifier = 1.0
        for k in list(region.resource_suspensions):
            region.resource_suspensions[k] -= 1
        region.resource_suspensions = {k: v for k, v in region.resource_suspensions.items() if v > 0}
        for k in list(region.route_suspensions):
            region.route_suspensions[k] -= 1
        region.route_suspensions = {k: v for k, v in region.route_suspensions.items() if v > 0}

    disaster_events = check_disasters(world, climate_phase)
    events.extend(disaster_events)

    migration_events = process_migration(world, acc=acc)
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
                mult = get_severity_multiplier(civ)
                drain = int(get_override(world, K_DROUGHT_STABILITY, 3))
                if acc is not None:
                    civ_idx = civ_index(world, civ.name)
                    acc.add(civ_idx, civ, "stability", -drain, "signal")
                    acc.add(civ_idx, civ, "economy", -int(10 * mult), "signal")
                else:
                    civ.stability = clamp(civ.stability - drain, STAT_FLOOR["stability"], 100)
                    civ.economy = clamp(civ.economy - int(10 * mult), STAT_FLOOR["economy"], 100)
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
                mult = get_severity_multiplier(civ)
                civ_idx = civ_index(world, civ.name)
                if acc is not None:
                    acc.add(civ_idx, civ, "population", -int(10 * mult), "guard")
                else:
                    civ_regions = [r for r in world.regions if r.controller == civ.name]
                    distribute_pop_loss(civ_regions, int(10 * mult))
                    sync_civ_population(civ, world)
                drain = int(get_override(world, K_PLAGUE_STABILITY, 3))
                if acc is not None:
                    acc.add(civ_idx, civ, "stability", -drain, "signal")
                else:
                    civ.stability = clamp(civ.stability - drain, STAT_FLOOR["stability"], 100)
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
                mult = get_severity_multiplier(civ)
                if acc is not None:
                    civ_idx = civ_index(world, civ.name)
                    acc.add(civ_idx, civ, "economy", -int(10 * mult), "signal")
                else:
                    civ.economy = clamp(civ.economy - int(10 * mult), STAT_FLOOR["economy"], 100)

        world.event_probabilities = apply_probability_cascade(
            event.event_type, world.event_probabilities
        )
        events.append(event)

    return events


# --- Phase 2: Automatic Effects ---

def apply_automatic_effects(world: WorldState, acc=None) -> list[Event]:
    """Phase 2: Automatic per-turn effects — maintenance, trade, specialization, mercs."""
    from chronicler.resources import get_active_trade_routes, get_self_trade_civs
    from chronicler.infrastructure import tick_infrastructure
    events: list[Event] = []

    # 0. Infrastructure tick (advance pending builds, mine degradation)
    infra_events = tick_infrastructure(world)
    events.extend(infra_events)

    # 1. Military maintenance: free up to threshold, then (mil-threshold)//10 per turn
    free_threshold = int(get_override(world, K_MILITARY_FREE_THRESHOLD, 30))
    for civ_idx, civ in enumerate(world.civilizations):
        if civ.military > free_threshold:
            cost = (civ.military - free_threshold) // 10
            if acc is not None:
                acc.add(civ_idx, civ, "treasury", -cost, "keep")
            else:
                civ.treasury -= cost

    # 2. Trade income
    cross_routes = get_active_trade_routes(world)
    for civ_a, civ_b in cross_routes:
        a = get_civ(world, civ_a)
        b = get_civ(world, civ_b)
        if a:
            if acc is not None:
                a_idx = civ_index(world, a.name)
                acc.add(a_idx, a, "treasury", 2, "keep")
            else:
                a.treasury += 2
        if b:
            if acc is not None:
                b_idx = civ_index(world, b.name)
                acc.add(b_idx, b, "treasury", 2, "keep")
            else:
                b.treasury += 2
    for civ_name in get_self_trade_civs(world):
        c = get_civ(world, civ_name)
        if c:
            if acc is not None:
                c_idx = next(i for i, cc in enumerate(world.civilizations) if cc.name == c.name)
                acc.add(c_idx, c, "treasury", 3, "keep")
            else:
                c.treasury += 3

    # Embargo set — used by both specialization and black market sections
    embargo_set = {(a, b) for a, b in world.embargoes} | {(b, a) for a, b in world.embargoes}

    # 3. Economic specialization
    for civ_idx, civ in enumerate(world.civilizations):
        controlled = [r for r in world.regions if r.controller == civ.name]
        if not controlled:
            continue
        resource_counts: dict = {}
        for r in controlled:
            for rtype in r.resource_types:
                if rtype == EMPTY_SLOT:
                    continue
                resource_counts[rtype] = resource_counts.get(rtype, 0) + 1
        if not resource_counts:
            continue
        primary = max(resource_counts, key=lambda r: resource_counts[r])
        civ_routes = [(a, b) for a, b in cross_routes if civ.name in (a, b)]
        if not civ_routes:
            continue
        primary_routes = 0
        for a, b in civ_routes:
            route_regions = [r for r in world.regions
                            if r.controller in (a, b) and primary in r.resource_types]
            if route_regions:
                primary_routes += 1
        if len(civ_routes) > 0 and primary_routes / len(civ_routes) > 0.6:
            embargoed_routes = [(a, b) for a, b in civ_routes
                               if (a, b) in embargo_set or (b, a) in embargo_set]
            if embargoed_routes:
                penalty = int(civ.economy * 0.20)
                if acc is not None:
                    acc.add(civ_idx, civ, "treasury", -penalty, "keep")
                else:
                    civ.treasury -= penalty
            else:
                bonus = int(civ.economy * 0.15)
                if acc is not None:
                    acc.add(civ_idx, civ, "treasury", bonus, "keep")
                else:
                    civ.treasury += bonus

    # 4. Black market leakage for embargoed civs
    for civ_idx, civ in enumerate(world.civilizations):
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
                        if acc is not None:
                            acc.add(civ_idx, civ, "treasury", 1, "keep")
                            acc.add(civ_idx, civ, "stability", -3, "signal")
                        else:
                            civ.treasury += 1  # 30% of normal trade (2), min 1
                            civ.stability = clamp(civ.stability - 3, STAT_FLOOR["stability"], 100)
                        break  # Only one black market route per civ per turn
            break  # Only check first controlled region for simplicity

    # 5. Ongoing war costs: -3/turn per active war
    for war in world.active_wars:
        for civ_name in war:
            c = get_civ(world, civ_name)
            if c:
                if acc is not None:
                    c_idx = next(i for i, cc in enumerate(world.civilizations) if cc.name == c.name)
                    acc.add(c_idx, c, "treasury", -3, "keep")
                    if c.treasury <= 0:
                        drain = int(get_override(world, K_WAR_COST_STABILITY, 2))
                        acc.add(c_idx, c, "stability", -drain, "signal")
                else:
                    c.treasury -= 3
                    if c.treasury <= 0:
                        drain = int(get_override(world, K_WAR_COST_STABILITY, 2))
                        c.stability = clamp(c.stability - drain, STAT_FLOOR["stability"], 100)

    # 6. Mercenary system
    MAX_MERCS = 3
    for civ_idx, civ in enumerate(world.civilizations):
        # Check merc pressure: military >> income
        if civ.military > 30 and civ.last_income > 0 and civ.military > civ.last_income * 3:
            civ.merc_pressure_turns += 1
        else:
            civ.merc_pressure_turns = max(0, civ.merc_pressure_turns - 1)
        # Spawn mercenary company after 3 turns of pressure
        if civ.merc_pressure_turns >= 3 and len(world.mercenary_companies) < MAX_MERCS:
            strength = min(10, civ.military // 5)
            if acc is not None:
                acc.add(civ_idx, civ, "military", -strength, "guard")
            else:
                civ.military = clamp(civ.military - strength, STAT_FLOOR["military"], 100)
            region = civ.regions[0] if civ.regions else "unknown"
            world.mercenary_companies.append({
                "strength": strength, "origin_civ": civ.name,
                "location": region, "available": True, "hired_by": None,
            })
            events.append(Event(
                turn=world.turn, event_type="mercenary_spawned",
                actors=[civ.name],
                description=f"A mercenary company forms from {civ.name}'s overextended military.",
                importance=5,
            ))
            civ.merc_pressure_turns = 0
    # Mercenary hiring: underdog priority in active wars
    for merc in world.mercenary_companies:
        if not merc["available"] or merc["hired_by"]:
            continue
        # Find weakest belligerent with treasury
        candidates = []
        for war in world.active_wars:
            for civ_name in war:
                c = get_civ(world, civ_name)
                if c and c.treasury >= 10:
                    candidates.append(c)
        if candidates:
            candidates.sort(key=lambda c: (c.military, -c.treasury))
            hirer = candidates[0]
            if acc is not None:
                hirer_idx = next(i for i, cc in enumerate(world.civilizations) if cc.name == hirer.name)
                acc.add(hirer_idx, hirer, "treasury", -10, "keep")
                acc.add(hirer_idx, hirer, "military", merc["strength"], "guard")
            else:
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
    events.extend(apply_governing_costs(world, acc=acc))
    events.extend(collect_tribute(world, acc=acc))
    events.extend(apply_proxy_wars(world, acc=acc))
    events.extend(apply_exile_effects(world, acc=acc))
    events.extend(apply_balance_of_power(world))
    events.extend(apply_fallen_empire(world, acc=acc))
    events.extend(apply_twilight(world, acc=acc))
    events.extend(apply_long_peace(world, acc=acc))
    update_peak_regions(world)

    # Trade knowledge sharing (fog of war)
    from chronicler.exploration import tick_trade_knowledge_sharing
    knowledge_events = tick_trade_knowledge_sharing(world)
    events.extend(knowledge_events)

    # M17b: Exile pretender stability drain
    apply_exile_pretender_drain(world, acc=acc)

    # M17d: Tradition ongoing effects
    from chronicler.traditions import apply_tradition_effects
    apply_tradition_effects(world)

    # M17c: Hostage turn ticking
    from chronicler.relationships import tick_hostages
    tick_hostages(world)

    # M18: Pandemic tick
    from chronicler.emergence import tick_pandemic
    events.extend(tick_pandemic(world, acc=acc))

    return events


# --- Phase 3: Production ---

def phase_production(world: WorldState, acc=None) -> None:
    """Generate income and adjust population for each civilization."""
    from chronicler.ecology import effective_capacity
    for civ_idx, civ in enumerate(world.civilizations):
        # Base income
        income = civ.economy // 5 + len(civ.regions) * 2
        # Condition penalty
        penalty = sum(c.severity for c in world.active_conditions if civ.name in c.affected_civs)
        if acc is not None:
            acc.add(civ_idx, civ, "treasury", max(0, income - penalty), "keep")
        else:
            civ.treasury += max(0, income - penalty)
        # Track last_income for mercenary spawn
        civ.last_income = max(0, income - penalty)
        # Population
        region_capacity = sum(
            effective_capacity(r)
            for r in world.regions if r.controller == civ.name
        )
        max_pop = min(1000, region_capacity)
        civ_regions = [r for r in world.regions if r.controller == civ.name]
        if civ.economy > civ.population // 3 and civ.stability > 10 and civ.population < max_pop:
            if civ_regions:
                growth = max(5, 5 * len(civ_regions))
                per_region = max(1, growth // len(civ_regions))
                if acc is not None:
                    acc.add(civ_idx, civ, "population", per_region * len(civ_regions), "guard")
                else:
                    for r in civ_regions:
                        add_region_pop(r, per_region)
                    sync_civ_population(civ, world)
        elif civ.stability <= 5 and civ.population > 1:
            if civ_regions:
                if acc is not None:
                    acc.add(civ_idx, civ, "population", -5, "guard")
                else:
                    target = max(civ_regions, key=lambda r: r.population)
                    drain_region_pop(target, 5)
                    sync_civ_population(civ, world)
        # Passive repopulation: empty controlled regions slowly recover
        if civ_regions:
            empty_count = sum(1 for r in civ_regions if r.population == 0)
            if acc is not None:
                if empty_count > 0:
                    acc.add(civ_idx, civ, "population", 3 * empty_count, "guard")
            else:
                for r in civ_regions:
                    if r.population == 0:
                        add_region_pop(r, 3)
                sync_civ_population(civ, world)

        # M21: MECHANIZATION gives +2 treasury per active mine
        if civ.active_focus == "mechanization":
            from chronicler.models import InfrastructureType
            mine_count = sum(
                1 for r in world.regions if r.controller == civ.name
                for i in r.infrastructure if i.type == InfrastructureType.MINES and i.active
            )
            if mine_count > 0:
                if acc is not None:
                    acc.add(civ_idx, civ, "treasury", mine_count * 2, "keep")
                else:
                    civ.treasury += mine_count * 2
                world.events_timeline.append(Event(
                    turn=world.turn, event_type="capability_mechanization",
                    actors=[civ.name], description=f"{civ.name} mechanization yields {mine_count * 2} from mines",
                    importance=1,
                ))

    # Stability recovery: passive per-turn recovery, halved during severe conditions
    for civ_idx, civ in enumerate(world.civilizations):
        if civ.stability < 50:
            base_recovery = int(get_override(world, K_STABILITY_RECOVERY, 20))
            has_severe_condition = any(
                c.severity >= 50 and civ.name in c.affected_civs
                for c in world.active_conditions
            )
            recovery = base_recovery // 2 if has_severe_condition else base_recovery
            if acc is not None:
                acc.add(civ_idx, civ, "stability", recovery, "guard")
            else:
                civ.stability = clamp(civ.stability + recovery, STAT_FLOOR["stability"], 100)

    # M16a: Prestige decay and trade bonus
    tick_prestige(world, acc=acc)


# --- Phase 5: Action ---

_CRISIS_HALVED_STATS = ("economy", "culture", "military", "stability", "population")


def phase_action(
    world: WorldState,
    action_selector: ActionSelector,
    acc=None,
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
        event = resolve_action(civ, action, world, acc=acc)

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

def apply_asabiya_dynamics(world: WorldState, acc=None) -> None:
    """Update asabiya (collective solidarity) for each civilization."""
    r0 = 0.05   # Growth rate at frontiers
    delta = 0.02  # Decay rate in interior

    disp_threat = {Disposition.HOSTILE, Disposition.SUSPICIOUS}

    for civ_idx, civ in enumerate(world.civilizations):
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

        new_asabiya = round(max(0.0, min(1.0, s)), 4)
        if acc is not None:
            delta_val = new_asabiya - civ.asabiya
            acc.add(civ_idx, civ, "asabiya", delta_val, "keep")
        else:
            civ.asabiya = new_asabiya


# --- Phase 7: Random events ---

def phase_random_events(world: WorldState, seed: int, acc=None) -> list[Event]:
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

        affected_civ = get_civ(world, event.actors[0])
        if affected_civ:
            _apply_event_effects(event.event_type, affected_civ, world, acc=acc)

        events.append(event)

    from chronicler.politics import check_congress
    events.extend(check_congress(world, acc=acc))
    return events


def _apply_event_effects(event_type: str, civ: Civilization, world: WorldState, acc=None) -> None:
    """Apply mechanical stat changes for a random event."""
    civ_idx = civ_index(world, civ.name)
    if event_type == "leader_death":
        import random as _random
        old_leader = civ.leader
        old_leader.alive = False
        mult = get_severity_multiplier(civ)
        drain = int(get_override(world, K_LEADER_DEATH_STABILITY, 4))
        if acc is not None:
            acc.add(civ_idx, civ, "stability", -int(drain * mult), "signal")
        else:
            civ.stability = clamp(civ.stability - int(drain * mult), STAT_FLOOR["stability"], 100)
        apply_leader_legacy(civ, old_leader, world)
        check_rival_fall(civ, old_leader.name, world)
        # Check whether death triggers a succession crisis instead of immediate succession
        crisis_prob = compute_crisis_probability(civ, world)
        rng = _random.Random(world.seed + world.turn + hash(civ.name))
        if crisis_prob > 0.0 and rng.random() < crisis_prob and not is_in_crisis(civ):
            trigger_crisis(civ, world)
            world.events_timeline.append(Event(
                turn=world.turn, event_type="succession_crisis",
                actors=[civ.name],
                description=f"A succession crisis erupts in {civ.name} after the death of {old_leader.name}.",
                importance=8,
            ))
        else:
            new_leader = generate_successor(civ, world, seed=world.turn * 100)
            from chronicler.succession import inherit_grudges
            inherit_grudges(old_leader, new_leader)
            civ.leader = new_leader
    elif event_type == "rebellion":
        mult = get_severity_multiplier(civ)
        drain = int(get_override(world, K_REBELLION_STABILITY, 4))
        if acc is not None:
            acc.add(civ_idx, civ, "stability", -int(drain * mult), "signal")
            acc.add(civ_idx, civ, "military", -int(10 * mult), "signal")
        else:
            civ.stability = clamp(civ.stability - int(drain * mult), STAT_FLOOR["stability"], 100)
            civ.military = clamp(civ.military - int(10 * mult), STAT_FLOOR["military"], 100)
    elif event_type == "discovery":
        if acc is not None:
            acc.add(civ_idx, civ, "culture", 10, "guard-shock")
            acc.add(civ_idx, civ, "economy", 10, "guard-shock")
        else:
            civ.culture = clamp(civ.culture + 10, STAT_FLOOR["culture"], 100)
            civ.economy = clamp(civ.economy + 10, STAT_FLOOR["economy"], 100)
    elif event_type == "religious_movement":
        mult = get_severity_multiplier(civ)
        drain = int(get_override(world, K_RELIGIOUS_MOVEMENT_STABILITY, 4))
        if acc is not None:
            acc.add(civ_idx, civ, "culture", 10, "guard-shock")
            acc.add(civ_idx, civ, "stability", -int(drain * mult), "signal")
        else:
            civ.culture = clamp(civ.culture + 10, STAT_FLOOR["culture"], 100)
            civ.stability = clamp(civ.stability - int(drain * mult), STAT_FLOOR["stability"], 100)
    elif event_type == "cultural_renaissance":
        if acc is not None:
            acc.add(civ_idx, civ, "culture", 20, "guard-shock")
            acc.add(civ_idx, civ, "stability", 10, "guard-shock")
        else:
            civ.culture = clamp(civ.culture + 20, STAT_FLOOR["culture"], 100)
            civ.stability = clamp(civ.stability + 10, STAT_FLOOR["stability"], 100)
    elif event_type == "migration":
        from chronicler.ecology import effective_capacity
        civ_regions = [r for r in world.regions if r.controller == civ.name]
        if civ_regions:
            if acc is not None:
                acc.add(civ_idx, civ, "population", 10, "guard")
            else:
                target = max(civ_regions, key=lambda r: effective_capacity(r) - r.population)
                add_region_pop(target, 10)
                sync_civ_population(civ, world)
        mult = get_severity_multiplier(civ)
        drain = int(get_override(world, K_MIGRATION_STABILITY, 4))
        if acc is not None:
            acc.add(civ_idx, civ, "stability", -int(drain * mult), "signal")
        else:
            civ.stability = clamp(civ.stability - int(drain * mult), STAT_FLOOR["stability"], 100)
    elif event_type == "border_incident":
        mult = get_severity_multiplier(civ)
        drain = int(get_override(world, K_BORDER_INCIDENT_STABILITY, 2))
        if acc is not None:
            acc.add(civ_idx, civ, "stability", -int(drain * mult), "signal")
        else:
            civ.stability = clamp(civ.stability - int(drain * mult), STAT_FLOOR["stability"], 100)


def apply_injected_event(
    event_type: str, target_civ_name: str, world: WorldState, acc=None
) -> list[Event]:
    """Process a manually injected event targeting a single civ."""
    civ = get_civ(world, target_civ_name)
    if civ is None:
        return []

    civ_idx = civ_index(world, civ.name)

    event = Event(
        turn=world.turn,
        event_type=event_type,
        actors=[target_civ_name],
        description=f"[Injected] {event_type} strikes {target_civ_name}",
        importance=7,
    )

    if event_type == "drought":
        if acc is not None:
            acc.add(civ_idx, civ, "stability", -10, "signal")
            acc.add(civ_idx, civ, "economy", -10, "signal")
        else:
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
        if acc is not None:
            acc.add(civ_idx, civ, "population", -10, "guard")
        else:
            civ_regions = [r for r in world.regions if r.controller == civ.name]
            if civ_regions:
                target_r = max(civ_regions, key=lambda r: r.population)
                drain_region_pop(target_r, 10)
                sync_civ_population(civ, world)
        if acc is not None:
            acc.add(civ_idx, civ, "stability", -10, "signal")
        else:
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
        if acc is not None:
            acc.add(civ_idx, civ, "economy", -10, "signal")
        else:
            civ.economy = clamp(civ.economy - 10, STAT_FLOOR["economy"], 100)
    else:
        _apply_event_effects(event_type, civ, world, acc=acc)

    world.event_probabilities = apply_probability_cascade(
        event_type, world.event_probabilities
    )

    return [event]


# --- Phase 10: Consequences ---

def phase_consequences(world: WorldState, acc=None) -> list[Event]:
    """Resolve cascading effects and tick condition durations. Returns collapse events."""
    for condition in world.active_conditions:
        condition.duration -= 1
        for civ_name in condition.affected_civs:
            civ = get_civ(world, civ_name)
            if civ and condition.severity >= 50:
                civ_idx = civ_index(world, civ.name)
                mult = get_severity_multiplier(civ)
                if condition.condition_type == "drought":
                    drain = int(get_override(world, K_DROUGHT_ONGOING, 2))
                else:
                    drain = int(get_override(world, K_CONDITION_ONGOING_DRAIN, 1))
                if world.agent_mode == "hybrid":
                    world.pending_shocks.append(CivShock(civ_idx,
                        stability_shock=normalize_shock(int(drain * mult), civ.stability)))
                elif acc is not None:
                    acc.add(civ_idx, civ, "stability", -int(drain * mult), "signal")
                else:
                    civ.stability = clamp(civ.stability - int(drain * mult), STAT_FLOOR["stability"], 100)

    world.active_conditions = [c for c in world.active_conditions if c.duration > 0]

    # M16b: Movement lifecycle (runs before value drift — movements feed disposition)
    tick_movements(world)

    # M16a: Cultural effects (order matters — assimilation drain feeds asabiya)
    _snap = getattr(world, '_agent_snapshot', None)
    apply_value_drift(world, agent_snapshot=_snap)
    tick_cultural_assimilation(world, acc=acc, agent_snapshot=_snap)

    # M16c: Cultural victory tracking (runs LAST in culture effects)
    check_cultural_victories(world)

    # M37: Religion computations for next turn's Rust tick
    _persecution_events: list[Event] = []
    _snap = getattr(world, '_agent_snapshot', None)
    if _snap is not None and world.belief_registry:
        from chronicler.religion import (
            compute_majority_belief, compute_civ_majority_faith,
            compute_conversion_signals, decay_conquest_boosts,
            compute_persecution, compute_martyrdom_boosts,
        )
        majority_beliefs = compute_majority_belief(_snap)
        civ_majority_with_ratio = compute_civ_majority_faith(_snap)

        # Store majority_belief on regions
        for rid, maj in majority_beliefs.items():
            if rid < len(world.regions):
                world.regions[rid].majority_belief = maj

        # Store civ_majority_faith and ratio on civilizations
        for cid, civ in enumerate(world.civilizations):
            entry = civ_majority_with_ratio.get(cid)
            if entry is not None:
                civ.civ_majority_faith, civ._majority_faith_ratio = entry

        # Build plain faith-id dict for downstream callers
        civ_faiths = {cid: faith_id for cid, (faith_id, _ratio) in civ_majority_with_ratio.items()}

        # Build civ lookup for conversion signal computation
        civ_name_to_id = {c.name: i for i, c in enumerate(world.civilizations)}

        # Compute conversion signals (reads conquest_conversion_active one-shot)
        signals = compute_conversion_signals(
            world.regions, majority_beliefs, world.belief_registry, _snap,
            named_agents=getattr(world, '_named_agents', None),
            civ_majority_faiths=civ_faiths,
            civ_name_to_id=civ_name_to_id,
        )
        # Signals are written directly to region fields by compute_conversion_signals

        # Decay conquest conversion boosts
        decay_conquest_boosts(world.regions)

        # M38b: Persecution
        if not hasattr(world, '_persecuted_regions'):
            world._persecuted_regions = set()
        _persecution_events = compute_persecution(
            world.regions, world.civilizations, world.belief_registry,
            _snap, world.turn, world._persecuted_regions,
        )
        compute_martyrdom_boosts(
            world.regions,
            getattr(world, '_dead_agents_this_turn', None),
        )

        # M38b: Schisms
        from chronicler.religion import detect_schisms, detect_reformation
        schism_events = detect_schisms(
            world.regions, world.civilizations, world.belief_registry,
            _snap, world.turn,
        )
        _persecution_events.extend(schism_events)
        reformation_events = detect_reformation(
            world.civilizations, world.belief_registry,
        )
        _persecution_events.extend(reformation_events)

        # M38b: Pilgrimages
        from chronicler.great_persons import check_pilgrimages
        all_temples = [
            (r.name, inf)
            for r in world.regions
            for inf in getattr(r, 'infrastructure', [])
            if getattr(inf, 'faith_id', -1) >= 0
        ]
        all_great_persons = [
            gp
            for c in world.civilizations
            for gp in getattr(c, 'great_persons', [])
        ]
        pilgrimage_events = check_pilgrimages(
            all_great_persons, all_temples, _snap, world.turn,
            world.belief_registry,
        )
        _persecution_events.extend(pilgrimage_events)
    elif world.belief_registry:
        # --agents=off: default civ_majority_faith to founding faith
        for i, civ in enumerate(world.civilizations):
            if i < len(world.belief_registry):
                civ.civ_majority_faith = world.belief_registry[i].faith_id

    # M38a: Build conversion_deltas and priest counts for tick_factions
    conversion_deltas = None
    region_populations = None
    prev_priest_counts = getattr(world, '_prev_priest_counts', None)
    curr_priest_counts = None
    if _snap is not None:
        # Build per-region belief distribution
        region_col = _snap.column("region").to_pylist()
        belief_col = _snap.column("belief").to_pylist()
        current_beliefs = {}
        for rid, bid in zip(region_col, belief_col):
            if rid not in current_beliefs:
                current_beliefs[rid] = {}
            current_beliefs[rid][bid] = current_beliefs[rid].get(bid, 0) + 1

        prev_beliefs = getattr(world, '_prev_belief_distribution', {})
        civ_majority_faiths = {c.name: getattr(c, 'civ_majority_faith', -1) for c in world.civilizations}

        from chronicler.religion import compute_conversion_deltas
        conversion_deltas = compute_conversion_deltas(
            current_beliefs, prev_beliefs, civ_majority_faiths, world.regions
        )
        region_populations = {rid: sum(dist.values()) for rid, dist in current_beliefs.items()}
        world._prev_belief_distribution = current_beliefs

        # Priest counts for EVT_PRIEST_LOSS
        occ_col = _snap.column("occupation").to_pylist()
        civ_col = _snap.column("civ_affinity").to_pylist()
        curr_priest_counts = {}
        for occ, civ_id in zip(occ_col, civ_col):
            if occ == 4:  # priest
                # Need to map civ_id to civ_name
                if civ_id < len(world.civilizations):
                    civ_name = world.civilizations[civ_id].name
                    curr_priest_counts[civ_name] = curr_priest_counts.get(civ_name, 0) + 1
        world._prev_priest_counts = curr_priest_counts

    apply_asabiya_dynamics(world)

    from chronicler.politics import (
        check_capital_loss, check_secession, check_vassal_rebellion,
        check_federation_formation, check_federation_dissolution, update_allied_turns,
    )
    collapse_events: list[Event] = []
    # M38b: flush buffered persecution events (computed in religion block above)
    collapse_events.extend(_persecution_events)
    collapse_events.extend(check_capital_loss(world, acc=acc))
    collapse_events.extend(check_secession(world, acc=acc))
    update_allied_turns(world)
    collapse_events.extend(check_vassal_rebellion(world, acc=acc))
    collapse_events.extend(check_federation_formation(world))
    collapse_events.extend(check_federation_dissolution(world, acc=acc))
    from chronicler.politics import check_proxy_detection, check_restoration
    from chronicler.politics import check_twilight_absorption, update_decline_tracking
    collapse_events.extend(check_proxy_detection(world, acc=acc))
    collapse_events.extend(check_restoration(world))
    collapse_events.extend(check_twilight_absorption(world))
    update_decline_tracking(world)
    for civ in world.civilizations:
        if civ.asabiya < 0.1 and civ.stability <= 20:
            if len(civ.regions) > 1:
                civ_idx = civ_index(world, civ.name)
                lost = civ.regions[1:]
                civ.regions = civ.regions[:1]
                for region in world.regions:
                    if region.name in lost:
                        region.controller = None
                if world.agent_mode == "hybrid":
                    world.pending_shocks.append(CivShock(civ_idx,
                        military_shock=-0.5, economy_shock=-0.5))
                else:
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
    acquired_traditions = check_tradition_acquisition(world)
    for civ_name, trad_name in acquired_traditions:
        collapse_events.append(Event(
            turn=world.turn, event_type="tradition_acquired",
            actors=[civ_name],
            description=f"{civ_name} acquires the tradition of {trad_name}.",
            importance=5,
        ))

    # --- M17: Great Person Consequences ---
    from chronicler.great_persons import check_great_person_generation, check_lifespan_expiry
    for civ in world.civilizations:
        if not civ.regions:
            continue
        new_persons = check_great_person_generation(civ, world)
        for gp in new_persons:
            collapse_events.append(Event(
                turn=world.turn, event_type="great_person_born",
                actors=[civ.name],
                description=f"A great {gp.role} emerges in {civ.name}: {gp.name}.",
                importance=6,
            ))
        check_lifespan_expiry(civ, world)

    # M17b: Exile restoration checks
    collapse_events.extend(check_exile_restoration(world))

    # M22: Faction tick — influence shifts, power struggles
    from chronicler.factions import tick_factions
    _economy_result = getattr(world, '_economy_result', None)
    collapse_events.extend(tick_factions(world, acc=acc,
                                         conversion_deltas=conversion_deltas,
                                         region_populations=region_populations,
                                         prev_priest_counts=prev_priest_counts,
                                         curr_priest_counts=curr_priest_counts,
                                         economy_result=_economy_result))

    # M38a: Temple prestige tick
    from chronicler.infrastructure import tick_temple_prestige
    tick_temple_prestige(world)

    return collapse_events


# --- Phase 4: Technology ---

def phase_technology(world: WorldState, acc=None) -> list[Event]:
    """Phase 4: Check tech advancement for each civ."""
    events = []
    for civ in world.civilizations:
        event = check_tech_advancement(civ, world, acc=acc)
        if event:
            events.append(event)
            # M21: Remove old focus effects, select and apply new
            if civ.active_focus:
                old_focus = TechFocus(civ.active_focus)
                remove_focus_effects(civ, old_focus)
            new_focus = select_tech_focus(civ, world)
            if new_focus:
                apply_focus_effects(civ, new_focus)
                events.append(Event(
                    turn=world.turn, event_type="tech_focus_selected",
                    actors=[civ.name],
                    description=f"{civ.name} develops {new_focus.value} specialization",
                    importance=6,
                ))
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


def phase_cultural_milestones(world: WorldState, acc=None) -> list[Event]:
    """Check cultural milestone thresholds for named works."""
    from chronicler.named_events import generate_cultural_work
    events = []
    for civ_idx, civ in enumerate(world.civilizations):
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
                if acc is not None:
                    acc.add(civ_idx, civ, "asabiya", 0.05, "keep")
                    acc.add(civ_idx, civ, "culture", 5, "guard-shock")
                    acc.add(civ_idx, civ, "prestige", 2, "keep")
                else:
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
                from chronicler.factions import resolve_crisis_with_factions
                crisis_events = resolve_crisis_with_factions(civ, world)
                events.extend(crisis_events)

        # Grudge decay — per-grudge rival alive status handled inside decay_grudges
        if civ.leader.grudges:
            decay_grudges(civ.leader, current_turn=world.turn, world=world)

    return events


    # NOTE: phase_fertility and _check_famine deleted by M23 — replaced by ecology.tick_ecology


def get_civ_capacities(world: WorldState) -> dict[int, int]:
    """Get total carrying capacity per civ for demand signal normalization."""
    region_map = {r.name: r for r in world.regions}
    return {
        i: sum(region_map[rn].carrying_capacity for rn in civ.regions if rn in region_map)
        for i, civ in enumerate(world.civilizations)
    }


# --- Turn orchestrator ---

def run_turn(
    world: WorldState,
    action_selector: ActionSelector,
    narrator: Narrator,
    seed: int = 0,
    agent_bridge: object | None = None,
    economy_tracker: object | None = None,
) -> str:
    """Execute one complete turn of the simulation. Returns chronicle text."""
    from chronicler.accumulator import StatAccumulator

    turn_events: list[Event] = []
    acc = StatAccumulator()

    # --- M18: Start-of-turn snapshots ---
    for civ in world.civilizations:
        civ.regions_start_of_turn = len(civ.regions)
        civ.was_in_twilight = civ.decline_turns > 0
        civ.capital_start_of_turn = civ.capital_region

    # Phase 1: Environment
    turn_events.extend(phase_environment(world, seed=seed, acc=acc))

    # M18: Black swan check (after climate disasters)
    from chronicler.emergence import check_black_swans
    turn_events.extend(check_black_swans(world, seed=seed, acc=acc))

    # M35b: Environmental events (condition-triggered, same phase)
    from chronicler.emergence import check_environmental_events
    import random as _random_m35b
    env_rng = _random_m35b.Random(seed + world.turn * 1013)
    turn_events.extend(check_environmental_events(world, env_rng))

    # --- M42: Goods economy (Phase 2 sub-sequence) ---
    economy_result = None
    if agent_bridge is not None:
        from chronicler.economy import compute_economy
        region_map = {r.name: r for r in world.regions}
        snapshot = agent_bridge.get_snapshot()
        if snapshot is not None:
            from chronicler.resources import get_active_trade_routes
            active_routes = get_active_trade_routes(world)
            economy_result = compute_economy(
                world, snapshot, region_map, agent_mode=True,
                active_trade_routes=active_routes,
            )
            agent_bridge.set_economy_result(economy_result)

            # M43b: Update tracker EMAs and detect supply shocks
            if economy_tracker is not None:
                from chronicler.economy import detect_supply_shocks, CATEGORY_GOODS
                for region in world.regions:
                    rname = region.name
                    for cat, goods in CATEGORY_GOODS.items():
                        stock_total = sum(region.stockpile.goods.get(g, 0.0) for g in goods)
                        economy_tracker.update_stockpile(rname, cat, stock_total)
                        imports_total = economy_result.imports_by_region.get(rname, {}).get(cat, 0.0)
                        economy_tracker.update_imports(rname, cat, imports_total)

                stockpiles = {r.name: r.stockpile for r in world.regions}
                shock_events = detect_supply_shocks(
                    world, stockpiles, economy_tracker, economy_result, region_map,
                )
                turn_events.extend(shock_events)

    # Phase 2: Automatic Effects (NEW)
    turn_events.extend(apply_automatic_effects(world, acc=acc))

    # M42: Apply treasury tax (keep category)
    if economy_result and acc is not None:
        for civ_idx, tax in economy_result.treasury_tax.items():
            if civ_idx < len(world.civilizations):
                acc.add(civ_idx, world.civilizations[civ_idx], "treasury", int(tax), "keep")

    # Phase 3: Production
    phase_production(world, acc=acc)

    # Phase 4: Technology
    turn_events.extend(phase_technology(world, acc=acc))

    # Phase 5: Action (selection + resolution)
    turn_events.extend(phase_action(world, action_selector=action_selector, acc=acc))

    conquered_civs = getattr(world, '_conquered_this_turn', set())
    world._conquered_this_turn = set()  # clear BEFORE passing to bridge (transient signal rule)
    conquered_dict = {i: True for i in conquered_civs}

    # Phase 6: Cultural Milestones
    turn_events.extend(phase_cultural_milestones(world, acc=acc))

    # Phase 7: Random Events
    turn_events.extend(phase_random_events(world, seed=seed + 100, acc=acc))

    # Phase 8: Leader Dynamics
    turn_events.extend(phase_leader_dynamics(world, seed=seed))

    # Phase 9: Ecology (M23 — replaces phase_fertility)
    from chronicler.ecology import tick_ecology
    from chronicler.climate import get_climate_phase
    climate_phase = get_climate_phase(world.turn, world.climate_config)
    turn_events.extend(tick_ecology(world, climate_phase, acc=acc))

    # M18: Terrain succession (uses low_forest_turns updated by tick_ecology)
    from chronicler.emergence import tick_terrain_succession
    turn_events.extend(tick_terrain_succession(world))

    # Apply accumulated stat mutations and route agent signals
    if world.agent_mode == "hybrid" and agent_bridge is not None:
        acc.apply_keep(world)  # Apply treasury, asabiya, prestige
        shocks = acc.to_shock_signals()
        demands = acc.to_demand_signals(get_civ_capacities(world))
        # Fold pending_shocks from last turn's Phase 10
        shocks.extend(world.pending_shocks)
        world.pending_shocks.clear()
        # Tick existing demand signals (decay), then add new ones for next turn
        demand_shifts = agent_bridge._demand_manager.tick()
        for ds in demands:
            agent_bridge._demand_manager.add(ds)
        # Run agent tick with shock and demand data
        turn_events.extend(agent_bridge.tick(world, shocks=shocks, demands=demand_shifts, conquered=conquered_dict))
    else:
        acc.apply(world)
        # Existing agent_bridge.tick() call for non-hybrid modes
        if agent_bridge is not None:
            turn_events.extend(agent_bridge.tick(world, conquered=conquered_dict))

    # M36: Stash snapshot for Phase 10 culture functions
    world._agent_snapshot = None
    if agent_bridge is not None:
        try:
            world._agent_snapshot = agent_bridge._sim.get_snapshot()
        except Exception:
            pass

    # M37: Stash named_agents for Phase 10 religion computations
    world._named_agents = agent_bridge.named_agents if agent_bridge else None

    # M42: Stash economy_result for Phase 10 tick_factions
    world._economy_result = economy_result

    # Phase 10: Consequences
    # In hybrid mode, pass acc so Phase 10 guards can route to pending_shocks.
    # In aggregate mode, pass acc=None so Phase 10 uses direct mutation (acc already applied).
    phase10_acc = acc if world.agent_mode == "hybrid" else None
    turn_events.extend(phase_consequences(world, acc=phase10_acc))

    # M40: Unified relationship formation and dissolution
    # One-turn latency: agent tick ran between Phase 9 and 10.
    # Rust reads edges from the previous turn's Phase 10 output. Intentional.
    if agent_bridge is not None:
        from chronicler.relationships import form_and_sync_relationships, compute_belief_data, REL_RIVAL

        # Build active agent IDs from all living named characters
        active_ids = set()
        for civ in world.civilizations:
            for gp in civ.great_persons:
                if gp.active and gp.agent_id is not None:
                    active_ids.add(gp.agent_id)

        # Build belief data from the agent snapshot via bridge
        try:
            snap = agent_bridge.get_snapshot()
        except Exception:
            snap = None
        belief_by_agent, region_belief_fractions = compute_belief_data(
            snap, active_ids, world.regions,
        )

        dissolved = form_and_sync_relationships(
            world, agent_bridge, active_ids, belief_by_agent, region_belief_fractions,
        )
        if dissolved:
            # dissolved_edges_by_turn: at most ~10 edges/turn × 500 turns = ~5000 entries.
            # Cleaned up when world is garbage-collected (exclude=True, not serialized).
            world.dissolved_edges_by_turn[world.turn] = dissolved

        # Generate rivalry events for curator
        new_edges = agent_bridge.read_social_edges()
        gp_by_id = {}
        for civ in world.civilizations:
            for gp in civ.great_persons:
                if gp.agent_id is not None:
                    gp_by_id[gp.agent_id] = gp
        for edge in new_edges:
            if edge[2] == REL_RIVAL and edge[3] == world.turn:
                gp_a = gp_by_id.get(edge[0])
                gp_b = gp_by_id.get(edge[1])
                actors = []
                if gp_a:
                    actors.append(gp_a.civilization)
                if gp_b:
                    actors.append(gp_b.civilization)
                turn_events.append(Event(
                    turn=world.turn, event_type="rivalry_formed",
                    actors=actors,
                    description="A rivalry forms between great persons of opposing civilizations.",
                    importance=5,
                ))

    # --- M18: Tech regression (after consequences, before stress) ---
    from chronicler.emergence import check_tech_regression
    from chronicler.emergence import BLACK_SWAN_EVENT_TYPES
    black_swan_this_turn = any(e.event_type in BLACK_SWAN_EVENT_TYPES for e in turn_events)
    turn_events.extend(check_tech_regression(world, black_swan_fired=black_swan_this_turn))

    # --- M18: Stress computation (feeds next turn) ---
    from chronicler.emergence import compute_all_stress
    compute_all_stress(world)

    # --- M18: Decrement black swan cooldown ---
    if world.black_swan_cooldown > 0:
        world.black_swan_cooldown -= 1

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
