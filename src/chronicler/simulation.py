"""Nine-phase simulation engine for the civilization chronicle.

Turn phases:
1. Environment — natural events (drought, plague, earthquake)
2. Production — income, population growth
3. Technology — tech advancement checks
4+5. Action — each civ takes one action from constrained menu
6. Cultural Milestones — check cultural threshold for named works
7. Random Events — 0-1 external events from cascading probability table
8. Leader Dynamics — trait evolution for all living leaders
9. Consequences — resolve cascading effects, tick condition durations

The engine is deterministic given a seed, except for Phase 4 (action
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
from chronicler.tech import check_tech_advancement, tech_war_multiplier
from chronicler.utils import clamp
from chronicler.leaders import (
    generate_successor, apply_leader_legacy, check_trait_evolution,
    check_rival_fall, update_rivalries,
)
from chronicler.named_events import generate_battle_name, generate_treaty_name, generate_tech_breakthrough_name


# --- Type aliases for callbacks ---

ActionSelector = Callable[[Civilization, WorldState], ActionType]
Narrator = Callable[[WorldState, list[Event]], str]

# --- Constants ---

DISPOSITION_ORDER: dict[Disposition, int] = {
    Disposition.HOSTILE: 0, Disposition.SUSPICIOUS: 1,
    Disposition.NEUTRAL: 2, Disposition.FRIENDLY: 3, Disposition.ALLIED: 4,
}

DISPOSITION_UPGRADE: dict[Disposition, Disposition] = {
    Disposition.HOSTILE: Disposition.SUSPICIOUS,
    Disposition.SUSPICIOUS: Disposition.NEUTRAL,
    Disposition.NEUTRAL: Disposition.FRIENDLY,
    Disposition.FRIENDLY: Disposition.ALLIED,
    Disposition.ALLIED: Disposition.ALLIED,
}

# --- Helpers ---



_ERA_ORDER = list(TechEra)


def _era_at_least(era: TechEra, minimum: TechEra) -> bool:
    return _ERA_ORDER.index(era) >= _ERA_ORDER.index(minimum)


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
            civ.stability = clamp(civ.stability - 1, 1, 10)
            civ.economy = clamp(civ.economy - 1, 1, 10)
        world.active_conditions.append(
            ActiveCondition(
                condition_type="drought",
                affected_civs=event.actors,
                duration=3,
                severity=5,
            )
        )
    elif event.event_type == "plague":
        for civ in affected:
            civ.population = clamp(civ.population - 1, 1, 10)
            civ.stability = clamp(civ.stability - 1, 1, 10)
        world.active_conditions.append(
            ActiveCondition(
                condition_type="plague",
                affected_civs=event.actors,
                duration=4,
                severity=6,
            )
        )
    elif event.event_type == "earthquake":
        for civ in affected:
            civ.economy = clamp(civ.economy - 1, 1, 10)

    # Cascade probabilities
    world.event_probabilities = apply_probability_cascade(
        event.event_type, world.event_probabilities
    )

    return [event]


# --- Phase 2: Production ---

def phase_production(world: WorldState) -> None:
    """Generate income and adjust population for each civilization."""
    for civ in world.civilizations:
        # Income: base from economy, bonus from trade, penalty from conditions
        income = civ.economy + len(civ.regions)
        condition_penalty = sum(
            c.severity // 3
            for c in world.active_conditions
            if civ.name in c.affected_civs
        )
        civ.treasury += max(0, income - condition_penalty)

        # Military maintenance
        maintenance = civ.military // 2
        civ.treasury = max(0, civ.treasury - maintenance)

        # Treasury cap: scales with economy to preserve tension
        treasury_cap = 10 + civ.economy * 3
        civ.treasury = min(civ.treasury, treasury_cap)

        # Population growth: if economy > population and stability > 3
        region_capacity = sum(
            r.carrying_capacity
            for r in world.regions
            if r.controller == civ.name
        )
        max_pop = min(10, region_capacity)
        if civ.economy > civ.population and civ.stability > 3 and civ.population < max_pop:
            civ.population = clamp(civ.population + 1, 1, 10)
        # Population decline if stability very low
        elif civ.stability <= 2 and civ.population > 1:
            civ.population = clamp(civ.population - 1, 1, 10)


# --- Phase 3: Action ---

def phase_action(
    world: WorldState,
    action_selector: ActionSelector,
) -> list[Event]:
    """Each civilization takes one action from the constrained menu."""
    events: list[Event] = []

    for civ in world.civilizations:
        action = action_selector(civ, world)
        event = _resolve_action(civ, action, world)

        # Track action in history (for streak breaker)
        history = world.action_history.setdefault(civ.name, [])
        history.append(action.value)
        if len(history) > 5:
            world.action_history[civ.name] = history[-5:]

        # Track action counts (for trait evolution)
        civ.action_counts[action.value] = civ.action_counts.get(action.value, 0) + 1

        events.append(event)

    return events


def _resolve_action(civ: Civilization, action: ActionType, world: WorldState) -> Event:
    """Resolve a single civilization's action and return the event."""
    if action == ActionType.DEVELOP:
        return _resolve_develop(civ, world)
    elif action == ActionType.EXPAND:
        return _resolve_expand(civ, world)
    elif action == ActionType.TRADE:
        return _resolve_trade_action(civ, world)
    elif action == ActionType.DIPLOMACY:
        return _resolve_diplomacy(civ, world)
    elif action == ActionType.WAR:
        return _resolve_war_action(civ, world)
    else:
        return Event(
            turn=world.turn,
            event_type="action",
            actors=[civ.name],
            description=f"{civ.name} rests.",
            importance=1,
        )


def _resolve_develop(civ: Civilization, world: WorldState) -> Event:
    """Invest in infrastructure: spend treasury to boost economy or culture."""
    cost = 3
    if civ.treasury >= cost:
        civ.treasury -= cost
        if civ.economy <= civ.culture:
            civ.economy = clamp(civ.economy + 1, 1, 10)
            target = "economy"
        else:
            civ.culture = clamp(civ.culture + 1, 1, 10)
            target = "culture"
        return Event(
            turn=world.turn, event_type="develop", actors=[civ.name],
            description=f"{civ.name} invested in {target}.", importance=3,
        )
    return Event(
        turn=world.turn, event_type="develop", actors=[civ.name],
        description=f"{civ.name} attempted development but lacked funds.", importance=2,
    )


HARSH_TERRAINS = {"tundra", "desert"}


def _resolve_expand(civ: Civilization, world: WorldState) -> Event:
    """Claim an uncontrolled region."""
    civ_index = next((i for i, c in enumerate(world.civilizations) if c.name == civ.name), 0)
    rng = random.Random(world.turn * 1000 + civ_index)
    unclaimed = [r for r in world.regions if r.controller is None]
    # Filter out harsh terrain if below IRON era
    if not _era_at_least(civ.tech_era, TechEra.IRON):
        unclaimed = [r for r in unclaimed if r.terrain not in HARSH_TERRAINS]
    if unclaimed and civ.military >= 3:
        target = rng.choice(unclaimed)
        target.controller = civ.name
        civ.regions.append(target.name)
        civ.military = clamp(civ.military - 1, 1, 10)  # Expansion stretches forces
        return Event(
            turn=world.turn, event_type="expand", actors=[civ.name],
            description=f"{civ.name} expanded into {target.name}.", importance=6,
        )
    return Event(
        turn=world.turn, event_type="expand", actors=[civ.name],
        description=f"{civ.name} could not expand — no available territory or insufficient military.",
        importance=2,
    )


def _resolve_trade_action(civ: Civilization, world: WorldState) -> Event:
    """Initiate trade with the friendliest neighbor."""
    best_partner = None
    best_disp = -1
    if civ.name in world.relationships:
        for other_name, rel in world.relationships[civ.name].items():
            d = DISPOSITION_ORDER.get(rel.disposition, 0)
            if d > best_disp:
                best_disp = d
                best_partner = _get_civ(world, other_name)

    if best_partner and best_disp >= 2:  # At least neutral
        resolve_trade(civ, best_partner, world)
        return Event(
            turn=world.turn, event_type="trade", actors=[civ.name, best_partner.name],
            description=f"{civ.name} traded with {best_partner.name}.", importance=3,
        )
    return Event(
        turn=world.turn, event_type="trade", actors=[civ.name],
        description=f"{civ.name} found no willing trade partners.", importance=2,
    )


def _resolve_diplomacy(civ: Civilization, world: WorldState) -> Event:
    """Attempt to improve relations with the most hostile neighbor."""
    worst_name = None
    worst_disp = 5
    if civ.name in world.relationships:
        for other_name, rel in world.relationships[civ.name].items():
            d = DISPOSITION_ORDER.get(rel.disposition, 2)
            if d < worst_disp:
                worst_disp = d
                worst_name = other_name

    if worst_name and civ.culture >= 3:
        # Improve relationship in both directions
        rel_out = world.relationships[civ.name][worst_name]
        rel_out.disposition = DISPOSITION_UPGRADE[rel_out.disposition]
        if worst_name in world.relationships and civ.name in world.relationships[worst_name]:
            rel_in = world.relationships[worst_name][civ.name]
            rel_in.disposition = DISPOSITION_UPGRADE[rel_in.disposition]
        new_disp = rel_out.disposition
        # Generate named treaty for significant upgrades (requires CLASSICAL+ era)
        if new_disp in (Disposition.FRIENDLY, Disposition.ALLIED) and _era_at_least(civ.tech_era, TechEra.CLASSICAL):
            treaty_name = generate_treaty_name(civ.name, worst_name, world, seed=world.seed)
            world.named_events.append(NamedEvent(
                name=treaty_name, event_type="treaty", turn=world.turn,
                actors=[civ.name, worst_name],
                description=f"{civ.name} and {worst_name} sign {treaty_name}", importance=5,
            ))
        return Event(
            turn=world.turn, event_type="diplomacy", actors=[civ.name, worst_name],
            description=f"{civ.name} improved relations with {worst_name}.", importance=4,
        )
    return Event(
        turn=world.turn, event_type="diplomacy", actors=[civ.name],
        description=f"{civ.name} attempted diplomacy without success.", importance=2,
    )


def _resolve_war_action(civ: Civilization, world: WorldState) -> Event:
    """Declare war on the most hostile neighbor."""
    target_name = None
    worst_disp = None
    if civ.name in world.relationships:
        for other_name, rel in world.relationships[civ.name].items():
            if rel.disposition not in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                continue
            d = DISPOSITION_ORDER[rel.disposition]
            if worst_disp is None or d < worst_disp:
                worst_disp = d
                target_name = other_name

    if target_name is None:
        # No HOSTILE/SUSPICIOUS target exists — fall back to peaceful action
        return _resolve_develop(civ, world)

    defender = _get_civ(world, target_name)
    if defender:
        result = resolve_war(civ, defender, world, seed=world.turn)
        # Generate named battle for decisive outcomes
        if result in ("attacker_wins", "defender_wins"):
            # Pick a region for the battle name
            battle_region = None
            if defender.regions:
                battle_region = defender.regions[0]
            elif civ.regions:
                battle_region = civ.regions[0]
            if battle_region:
                battle_name = generate_battle_name(battle_region, civ.tech_era, world, seed=world.seed)
                world.named_events.append(NamedEvent(
                    name=battle_name, event_type="battle", turn=world.turn,
                    actors=[civ.name, target_name], region=battle_region,
                    description=f"{civ.name} vs {target_name}: {result}", importance=7,
                ))
            # Update rivalries
            update_rivalries(civ, defender, world)
        return Event(
            turn=world.turn, event_type="war", actors=[civ.name, target_name],
            description=f"{civ.name} attacked {target_name}: {result}.", importance=8,
        )
    return Event(
        turn=world.turn, event_type="war", actors=[civ.name],
        description=f"{civ.name} prepared for war but found no target.", importance=3,
    )


# --- Combat resolution (simplified Lanchester) ---

def resolve_war(
    attacker: Civilization,
    defender: Civilization,
    world: WorldState,
    seed: int = 0,
) -> str:
    """Resolve combat between two civilizations. Returns outcome string."""
    rng = random.Random(seed)

    # Lanchester-inspired: effective power = military^2 * asabiya + random factor
    att_asabiya = attacker.asabiya
    def_asabiya = defender.asabiya

    # MEDIEVAL+ defender bonus: +0.2 asabiya (capped at 1.0)
    if _era_at_least(defender.tech_era, TechEra.MEDIEVAL):
        def_asabiya = min(def_asabiya + 0.2, 1.0)

    att_power = (attacker.military ** 2) * att_asabiya + rng.uniform(0, 3)
    def_power = (defender.military ** 2) * def_asabiya + rng.uniform(0, 3)

    # Apply tech disparity multiplier
    att_power *= tech_war_multiplier(attacker.tech_era, defender.tech_era)
    def_power *= tech_war_multiplier(defender.tech_era, attacker.tech_era)

    # War costs treasury regardless of outcome
    attacker.treasury = max(0, attacker.treasury - 2)
    defender.treasury = max(0, defender.treasury - 1)

    if att_power > def_power * 1.3:
        # Attacker wins — seize a region if possible
        defender_regions = [r for r in world.regions if r.controller == defender.name]
        if defender_regions:
            seized = rng.choice(defender_regions)
            seized.controller = attacker.name
            attacker.regions.append(seized.name)
            defender.regions = [r for r in defender.regions if r != seized.name]
        attacker.military = clamp(attacker.military - 1, 1, 10)
        defender.military = clamp(defender.military - 2, 1, 10)
        defender.stability = clamp(defender.stability - 1, 1, 10)
        return "attacker_wins"
    elif def_power > att_power * 1.3:
        # Defender wins
        attacker.military = clamp(attacker.military - 2, 1, 10)
        defender.military = clamp(defender.military - 1, 1, 10)
        attacker.stability = clamp(attacker.stability - 1, 1, 10)
        return "defender_wins"
    else:
        # Stalemate — both sides lose
        attacker.military = clamp(attacker.military - 1, 1, 10)
        defender.military = clamp(defender.military - 1, 1, 10)
        return "stalemate"


# --- Trade resolution ---

def resolve_trade(civ1: Civilization, civ2: Civilization, world: WorldState) -> None:
    """Resolve trade: both sides gain treasury proportional to their economy."""
    gain1 = max(1, civ2.economy // 3)
    gain2 = max(1, civ1.economy // 3)
    civ1.treasury += gain1
    civ2.treasury += gain2
    # Update trade volume in relationships
    if civ1.name in world.relationships and civ2.name in world.relationships[civ1.name]:
        world.relationships[civ1.name][civ2.name].trade_volume += 1
    if civ2.name in world.relationships and civ1.name in world.relationships[civ2.name]:
        world.relationships[civ2.name][civ1.name].trade_volume += 1


# --- Asabiya dynamics (Turchin metaethnic frontier model) ---

def apply_asabiya_dynamics(world: WorldState) -> None:
    """Update asabiya (collective solidarity) for each civilization.

    Frontier civilizations (bordering hostile/suspicious neighbors) gain asabiya.
    Interior civilizations (no hostile borders) lose asabiya through decay.
    """
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
            # Logistic growth: S' = S + r0 * S * (1 - S)
            s = s + r0 * s * (1 - s)
        else:
            # Decay: S' = S - delta * S
            s = s - delta * s

        civ.asabiya = round(max(0.0, min(1.0, s)), 4)


# --- Phase 4: Random events ---

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

    # Assign affected civilizations
    rng = random.Random(seed + 2)
    event.actors = [rng.choice(world.civilizations).name]

    # Apply cascading probabilities
    world.event_probabilities = apply_probability_cascade(
        event.event_type, world.event_probabilities
    )

    # Apply mechanical effects
    affected_civ = _get_civ(world, event.actors[0])
    if affected_civ:
        _apply_event_effects(event.event_type, affected_civ, world)

    return [event]


def _apply_event_effects(event_type: str, civ: Civilization, world: WorldState) -> None:
    """Apply mechanical stat changes for a random event."""
    if event_type == "leader_death":
        old_leader = civ.leader
        old_leader.alive = False
        civ.stability = clamp(civ.stability - 2, 1, 10)
        # Apply legacy if long reign
        apply_leader_legacy(civ, old_leader, world)
        # Check rival fall
        check_rival_fall(civ, old_leader.name, world)
        # Generate successor using leaders module
        new_leader = generate_successor(civ, world, seed=world.turn * 100)
        civ.leader = new_leader
    elif event_type == "rebellion":
        civ.stability = clamp(civ.stability - 2, 1, 10)
        civ.military = clamp(civ.military - 1, 1, 10)
    elif event_type == "discovery":
        civ.culture = clamp(civ.culture + 1, 1, 10)
        civ.economy = clamp(civ.economy + 1, 1, 10)
    elif event_type == "religious_movement":
        civ.culture = clamp(civ.culture + 1, 1, 10)
        civ.stability = clamp(civ.stability - 1, 1, 10)
    elif event_type == "cultural_renaissance":
        civ.culture = clamp(civ.culture + 2, 1, 10)
        civ.stability = clamp(civ.stability + 1, 1, 10)
    elif event_type == "migration":
        civ.population = clamp(civ.population + 1, 1, 10)
        civ.stability = clamp(civ.stability - 1, 1, 10)
    elif event_type == "border_incident":
        civ.stability = clamp(civ.stability - 1, 1, 10)


def apply_injected_event(
    event_type: str, target_civ_name: str, world: WorldState
) -> list[Event]:
    """Process a manually injected event targeting a single civ.

    Unlike natural events which randomly select affected civs,
    injected events affect only the named target. Returns a list
    containing the event (or empty if target civ not found).
    """
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

    # Environment events (drought/plague/earthquake) have special handling
    # that creates ActiveConditions. Replicate that logic for the single target.
    if event_type == "drought":
        civ.stability = clamp(civ.stability - 1, 1, 10)
        civ.economy = clamp(civ.economy - 1, 1, 10)
        world.active_conditions.append(
            ActiveCondition(
                condition_type="drought",
                affected_civs=[target_civ_name],
                duration=3,
                severity=5,
            )
        )
    elif event_type == "plague":
        civ.population = clamp(civ.population - 1, 1, 10)
        civ.stability = clamp(civ.stability - 1, 1, 10)
        world.active_conditions.append(
            ActiveCondition(
                condition_type="plague",
                affected_civs=[target_civ_name],
                duration=4,
                severity=6,
            )
        )
    elif event_type == "earthquake":
        civ.economy = clamp(civ.economy - 1, 1, 10)
    else:
        # Non-environment events use the standard effect handler
        _apply_event_effects(event_type, civ, world)

    # Apply cascading probabilities
    world.event_probabilities = apply_probability_cascade(
        event_type, world.event_probabilities
    )

    return [event]


# --- Phase 5: Consequences ---

def phase_consequences(world: WorldState) -> list[Event]:
    """Resolve cascading effects and tick condition durations. Returns collapse events."""
    # Tick down active conditions
    for condition in world.active_conditions:
        condition.duration -= 1
        # Ongoing damage from conditions
        for civ_name in condition.affected_civs:
            civ = _get_civ(world, civ_name)
            if civ and condition.severity >= 5:
                civ.stability = clamp(civ.stability - 1, 1, 10)

    # Remove expired conditions
    world.active_conditions = [c for c in world.active_conditions if c.duration > 0]

    # Apply Turchin asabiya dynamics
    apply_asabiya_dynamics(world)

    # Check for civilization collapse (asabiya < 0.1 and stability <= 2)
    collapse_events: list[Event] = []
    for civ in world.civilizations:
        if civ.asabiya < 0.1 and civ.stability <= 2:
            # Collapse: lose all but one region, stats halved
            if len(civ.regions) > 1:
                lost = civ.regions[1:]
                civ.regions = civ.regions[:1]
                for region in world.regions:
                    if region.name in lost:
                        region.controller = None
                civ.military = clamp(civ.military // 2, 1, 10)
                civ.economy = clamp(civ.economy // 2, 1, 10)
                collapse_events.append(Event(
                    turn=world.turn,
                    event_type="collapse",
                    actors=[civ.name],
                    description=f"{civ.name} collapsed under internal pressure.",
                    importance=10,
                ))

    return collapse_events


# --- Phase 3: Technology ---

def phase_technology(world: WorldState) -> list[Event]:
    """Phase 3: Check tech advancement for each civ."""
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
        for threshold in [8, 10]:
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
    """Phase 7: Handle trait evolution for all living leaders."""
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
    env_events = phase_environment(world, seed=seed)
    turn_events.extend(env_events)

    # Phase 2: Production
    phase_production(world)

    # Phase 3: Technology (NEW)
    tech_events = phase_technology(world)
    turn_events.extend(tech_events)

    # Phase 4+5: Action (selection + resolution)
    action_events = phase_action(world, action_selector=action_selector)
    turn_events.extend(action_events)

    # Phase 6: Cultural Milestones (NEW)
    cultural_events = phase_cultural_milestones(world)
    turn_events.extend(cultural_events)

    # Phase 7: Random events
    random_events = phase_random_events(world, seed=seed + 100)
    turn_events.extend(random_events)

    # Phase 8: Leader Dynamics (NEW)
    leader_events = phase_leader_dynamics(world, seed=seed)
    turn_events.extend(leader_events)

    # Phase 9: Consequences
    collapse_events = phase_consequences(world)
    turn_events.extend(collapse_events)

    # Record events
    world.events_timeline.extend(turn_events)

    # Chronicle (narrative generation)
    chronicle_text = narrator(world, turn_events)

    # Advance turn counter
    world.turn += 1

    return chronicle_text


def get_injectable_event_types() -> list[str]:
    """Return sorted list of event types that can be injected.

    Single source of truth for both interactive.py and live.py.
    """
    from chronicler.world_gen import DEFAULT_EVENT_PROBABILITIES
    return sorted(DEFAULT_EVENT_PROBABILITIES.keys())
