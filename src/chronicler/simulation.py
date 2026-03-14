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
    event = roll_for_event(
        world.event_probabilities,
        turn=world.turn,
        seed=seed,
        allowed_types=ENVIRONMENT_EVENTS,
    )
    if event is None:
        return []

    # Apply effects based on event type
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

    # Cascade probabilities
    world.event_probabilities = apply_probability_cascade(
        event.event_type, world.event_probabilities
    )

    return [event]


# --- Phase 2: Automatic Effects ---

def apply_automatic_effects(world: WorldState) -> list[Event]:
    """Phase 2: Automatic per-turn effects — maintenance, trade income."""
    events: list[Event] = []
    for civ in world.civilizations:
        # Military maintenance: free up to 30, then (mil-30)//10 per turn
        if civ.military > 30:
            cost = (civ.military - 30) // 10
            civ.treasury -= cost
    # Trade income placeholder — no-op until M13a provides get_active_trade_routes
    return events


# --- Phase 3: Production ---

def phase_production(world: WorldState) -> None:
    """Generate income and adjust population for each civilization."""
    for civ in world.civilizations:
        # Income: base from economy, bonus from trade, penalty from conditions
        income = civ.economy + len(civ.regions) * 10
        condition_penalty = sum(
            c.severity
            for c in world.active_conditions
            if civ.name in c.affected_civs
        )
        civ.treasury += max(0, income - condition_penalty)

        # Military maintenance
        maintenance = civ.military // 2
        civ.treasury = max(0, civ.treasury - maintenance)

        # Treasury cap: scales with economy to preserve tension
        treasury_cap = 100 + civ.economy * 3
        civ.treasury = min(civ.treasury, treasury_cap)

        # Population growth: if economy > population and stability > 30
        region_capacity = sum(
            r.carrying_capacity
            for r in world.regions
            if r.controller == civ.name
        )
        max_pop = min(100, region_capacity)
        if civ.economy > civ.population and civ.stability > 30 and civ.population < max_pop:
            civ.population = clamp(civ.population + 5, STAT_FLOOR["population"], 100)
        # Population decline if stability very low
        elif civ.stability <= 20 and civ.population > 1:
            civ.population = clamp(civ.population - 5, STAT_FLOOR["population"], 100)


# --- Phase 5: Action ---

def phase_action(
    world: WorldState,
    action_selector: ActionSelector,
) -> list[Event]:
    """Each civilization takes one action from the constrained menu."""
    events: list[Event] = []

    for civ in world.civilizations:
        action = action_selector(civ, world)
        event = resolve_action(civ, action, world)

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

        civ.asabiya = round(max(0.0, min(1.0, s)), 4)


# --- Phase 7: Random events ---

def phase_random_events(world: WorldState, seed: int) -> list[Event]:
    """Roll for 0-1 random external events (non-environment)."""
    non_env = [k for k in world.event_probabilities if k not in ENVIRONMENT_EVENTS]
    event = roll_for_event(
        world.event_probabilities,
        turn=world.turn,
        seed=seed,
        allowed_types=non_env,
    )
    if event is None:
        return []

    rng = random.Random(seed + 2)
    event.actors = [rng.choice(world.civilizations).name]

    world.event_probabilities = apply_probability_cascade(
        event.event_type, world.event_probabilities
    )

    affected_civ = _get_civ(world, event.actors[0])
    if affected_civ:
        _apply_event_effects(event.event_type, affected_civ, world)

    return [event]


def _apply_event_effects(event_type: str, civ: Civilization, world: WorldState) -> None:
    """Apply mechanical stat changes for a random event."""
    if event_type == "leader_death":
        old_leader = civ.leader
        old_leader.alive = False
        civ.stability = clamp(civ.stability - 20, STAT_FLOOR["stability"], 100)
        apply_leader_legacy(civ, old_leader, world)
        check_rival_fall(civ, old_leader.name, world)
        new_leader = generate_successor(civ, world, seed=world.turn * 100)
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

    apply_asabiya_dynamics(world)

    collapse_events: list[Event] = []
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

    return collapse_events


# --- Phase 4: Technology ---

def phase_technology(world: WorldState) -> list[Event]:
    """Phase 4: Check tech advancement for each civ."""
    events = []
    for civ in world.civilizations:
        event = check_tech_advancement(civ, world)
        if event:
            events.append(event)
            name = generate_tech_breakthrough_name(civ.tech_era)
            world.named_events.append(NamedEvent(
                name=name, event_type="tech_breakthrough", turn=world.turn,
                actors=[civ.name], description=event.description, importance=7,
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
                events.append(Event(
                    turn=world.turn, event_type="cultural_work", actors=[civ.name],
                    description=ne.description, importance=6,
                ))
    return events


def phase_leader_dynamics(world: WorldState, seed: int) -> list[Event]:
    """Phase 8: Handle trait evolution for all living leaders."""
    events = []
    for civ in world.civilizations:
        secondary = check_trait_evolution(civ, world)
        if secondary:
            events.append(Event(
                turn=world.turn, event_type="trait_evolution", actors=[civ.name],
                description=f"{civ.leader.name} of {civ.name} has become known as a {secondary}",
                importance=4,
            ))
    return events


# --- Phase 9: Fertility ---

def phase_fertility(world: WorldState) -> None:
    """Phase 9: Fertility tick — no-op until M13a."""
    pass


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

    # Phase 9: Fertility (NEW — no-op until M13a)
    phase_fertility(world)

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
