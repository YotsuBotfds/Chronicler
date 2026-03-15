"""Event counting, traditions, and folk heroes."""
from __future__ import annotations

from chronicler.models import WorldState, Civilization, Event, NamedEvent, GreatPerson, Disposition


# --- Task 19: Event counts tracking ---

def update_event_counts(world: WorldState) -> None:
    """Update event_counts and war_win_turns for all civs based on this turn's events."""
    turn_events = [e for e in world.events_timeline if e.turn == world.turn]
    for event in turn_events:
        if not event.actors:
            continue
        civ_name = event.actors[0]
        civ = next((c for c in world.civilizations if c.name == civ_name), None)
        if not civ:
            continue
        if event.event_type == "war" and "attacker_wins" in event.description:
            civ.event_counts["wars_won"] = civ.event_counts.get("wars_won", 0) + 1
            civ.war_win_turns.append(world.turn)
        elif event.event_type == "famine":
            civ.event_counts["famines_survived"] = civ.event_counts.get("famines_survived", 0) + 1

    # Prune old war wins (only keep last 20 turns — matches _WAR_WIN_WINDOW in great_persons.py)
    for civ in world.civilizations:
        civ.war_win_turns = [t for t in civ.war_win_turns if t >= world.turn - 20]

    # Track high economy turns
    for civ in world.civilizations:
        if civ.economy >= 80:
            civ.event_counts["high_economy_turns"] = civ.event_counts.get("high_economy_turns", 0) + 1
        else:
            civ.event_counts["high_economy_turns"] = 0

    # Track high trade route turns
    for civ in world.civilizations:
        active_routes = sum(
            1 for other_name, rel in world.relationships.get(civ.name, {}).items()
            if hasattr(rel, "trade_volume") and rel.trade_volume > 0
        )
        if active_routes >= 4:
            civ.event_counts["high_trade_route_turns"] = civ.event_counts.get("high_trade_route_turns", 0) + 1
        else:
            civ.event_counts["high_trade_route_turns"] = 0

    # Track federation membership turns
    for fed in world.federations:
        for member_name in fed.members:
            civ = next((c for c in world.civilizations if c.name == member_name), None)
            if civ:
                civ.event_counts["federation_turns"] = civ.event_counts.get("federation_turns", 0) + 1

    # Track capital recovery: a civ that previously lost their capital and now wins a war
    for event in turn_events:
        if event.event_type == "war" and "attacker_wins" in event.description and event.actors:
            civ_name = event.actors[0]
            civ = next((c for c in world.civilizations if c.name == civ_name), None)
            if civ and civ.event_counts.get("capital_lost", 0) > 0:
                civ.event_counts["capital_recovered"] = civ.event_counts.get("capital_recovered", 0) + 1


# --- Task 20: Traditions ---

TRADITION_DIRECT_TRIGGERS: dict = {
    "martial": lambda civ: civ.event_counts.get("wars_won", 0) >= 5,
    "food_stockpiling": lambda civ: civ.event_counts.get("famines_survived", 0) >= 3,
    "resilience": lambda civ: civ.event_counts.get("capital_recovered", 0) >= 1,
    "diplomatic": lambda civ: civ.event_counts.get("federation_turns", 0) >= 30,
}

TRADITION_CRYSTALLIZATION: dict = {
    "martial": ("military", 3),
    "food_stockpiling": ("golden_age", 2),
    "diplomatic": ("fracture", 2),
    "resilience": ("shame", 3),
}

MAX_TRADITIONS = 4


def check_tradition_acquisition(world: WorldState) -> list[tuple[str, str]]:
    """Check and grant new traditions to civs based on event counts and legacy.

    Returns list of (civ_name, tradition_name) pairs.
    """
    granted: list[tuple[str, str]] = []
    for civ in world.civilizations:
        if len(civ.traditions) >= MAX_TRADITIONS:
            continue
        for tradition, trigger in TRADITION_DIRECT_TRIGGERS.items():
            if len(civ.traditions) >= MAX_TRADITIONS:
                break
            if tradition in civ.traditions:
                continue
            if trigger(civ):
                civ.traditions.append(tradition)
                granted.append((civ.name, tradition))
                continue
            legacy_key, threshold = TRADITION_CRYSTALLIZATION[tradition]
            if civ.legacy_counts.get(legacy_key, 0) >= threshold:
                if tradition not in civ.traditions:
                    civ.traditions.append(tradition)
                    granted.append((civ.name, tradition))
    return granted


def apply_tradition_effects(world: WorldState) -> None:
    """Phase 2: Apply ongoing tradition effects (e.g. martial disposition drift)."""
    order = [
        Disposition.HOSTILE, Disposition.SUSPICIOUS, Disposition.NEUTRAL,
        Disposition.FRIENDLY, Disposition.ALLIED,
    ]
    for civ in world.civilizations:
        if not civ.regions:
            continue
        if "martial" in civ.traditions and world.turn % 10 == 0:
            for other_name in world.relationships.get(civ.name, {}):
                rel = world.relationships[civ.name][other_name]
                idx = order.index(rel.disposition) if rel.disposition in order else 2
                if idx > 0:
                    rel.disposition = order[idx - 1]


def apply_fertility_floor(world: WorldState) -> None:
    """Phase 9: Apply fertility floor for civs with food_stockpiling tradition."""
    for region in world.regions:
        controller = next(
            (civ for civ in world.civilizations if region.name in civ.regions), None
        )
        if controller and "food_stockpiling" in controller.traditions:
            region.fertility = max(region.fertility, 0.2)


# --- Task 21: Folk heroes ---

MAX_FOLK_HEROES = 5
FOLK_HERO_ASABIYA = 0.03
FOLK_HERO_CHANCE = 0.20


def is_dramatic_death(context: str) -> bool:
    """Return True if the context qualifies as a dramatic death."""
    return context in ("war", "disaster", "succession_crisis", "exile_recognized")


def check_folk_hero(gp: GreatPerson, civ: Civilization, world: WorldState, context: str) -> bool:
    """Check if a dead great person becomes a folk hero. Returns True if they do."""
    if not is_dramatic_death(context):
        return False
    roll = (world.seed + (gp.death_turn or world.turn) + hash(gp.name)) % 100
    if roll < FOLK_HERO_CHANCE * 100:
        _add_folk_hero(gp, civ, context)
        return True
    return False


def _add_folk_hero(gp: GreatPerson, civ: Civilization, context: str) -> None:
    """Add a folk hero entry to the civ, capping at MAX_FOLK_HEROES (FIFO eviction)."""
    hero = {
        "name": gp.name,
        "role": gp.role,
        "death_turn": gp.death_turn or 0,
        "death_context": context,
    }
    if len(civ.folk_heroes) >= MAX_FOLK_HEROES:
        civ.folk_heroes.pop(0)
    civ.folk_heroes.append(hero)


def compute_folk_hero_asabiya_bonus(civ: Civilization) -> float:
    """Return total asabiya bonus from folk heroes."""
    return len(civ.folk_heroes) * FOLK_HERO_ASABIYA


# --- Task 23: Prophet martyrdom ---

def apply_prophet_martyrdom(gp: GreatPerson, civ: Civilization, world: WorldState) -> list:
    """Apply martyrdom effects when a prophet dies: boost movement and upgrade co-adherent relations."""
    events: list = []
    if gp.role != "prophet" or gp.movement_id is None:
        return events

    movement = next((m for m in world.movements if m.id == gp.movement_id), None)
    if not movement:
        return events

    key = f"martyrdom_bonus_movement_{movement.id}"
    civ.event_counts[key] = civ.event_counts.get(key, 0) + 1

    # Disposition upgrade for co-adherents
    order = [
        Disposition.HOSTILE, Disposition.SUSPICIOUS, Disposition.NEUTRAL,
        Disposition.FRIENDLY, Disposition.ALLIED,
    ]
    for other_name in movement.adherents:
        if other_name == civ.name:
            continue
        rel = world.relationships.get(other_name, {}).get(civ.name)
        if rel:
            idx = order.index(rel.disposition) if rel.disposition in order else 2
            if idx < len(order) - 1:
                rel.disposition = order[idx + 1]

    world.named_events.append(NamedEvent(
        name=f"The Martyrdom of {gp.name}",
        event_type="martyrdom",
        turn=world.turn,
        actors=[civ.name],
        description=f"The death of {gp.name} defined the orthodox faith.",
        importance=8,
    ))
    return events
