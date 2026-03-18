"""M45: Character arc classification.

Pure-function classifier that pattern-matches structured event data
to assign trajectory states (arc_phase) and archetype labels (arc_type)
to named characters. Stateless — re-derived each turn from full event history.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chronicler.dynasties import Dynasty, DynastyRegistry
    from chronicler.models import Event, GreatPerson

# --- Calibration constants [CALIBRATE] for M47 ---

RISING_CAREER_THRESHOLD: int = 20
TRAGIC_HERO_LIFESPAN_THRESHOLD: int = 35
MARTYR_LIFESPAN_THRESHOLD: int = 35

# --- Archetype names (exact string constants) ---

ARC_RISE_AND_FALL = "Rise-and-Fall"
ARC_EXILE_AND_RETURN = "Exile-and-Return"
ARC_DYNASTY_FOUNDER = "Dynasty-Founder"
ARC_TRAGIC_HERO = "Tragic-Hero"
ARC_WANDERER = "Wanderer"
ARC_DEFECTOR = "Defector"
ARC_PROPHET = "Prophet"
ARC_MARTYR = "Martyr"


def classify_arc(
    gp: GreatPerson,
    events: list[Event],
    dynasty_registry: DynastyRegistry | None,
    current_turn: int,
) -> tuple[str | None, str | None]:
    """Classify a character's arc from their event history.

    Pure function — stateless re-derivation each turn.

    Returns:
        (arc_phase, arc_type) — either or both may be None.
    """
    # Filter events to this character
    char_events = [e for e in events if gp.name in e.actors]

    # Collect matches: list of (arc_phase, arc_type, condition_count)
    matches: list[tuple[str | None, str | None, int]] = []

    # --- Check each archetype ---
    _check_rise_and_fall(gp, char_events, current_turn, matches)
    _check_exile_and_return(gp, char_events, matches)
    _check_dynasty_founder(gp, dynasty_registry, matches)
    _check_tragic_hero(gp, matches)
    _check_wanderer(gp, char_events, matches)
    _check_defector(gp, char_events, matches)
    _check_prophet(gp, char_events, matches)
    _check_martyr(gp, char_events, matches)

    if not matches:
        return None, None

    # Priority: complete matches (arc_type not None) first, then by condition count.
    # Tie-break: later in list wins (later-checked archetypes are more narratively
    # relevant per spec). Index-based secondary key ensures last-of-equals wins.
    complete = [(ph, at, cnt, i) for i, (ph, at, cnt) in enumerate(matches) if at is not None]
    if complete:
        best = max(complete, key=lambda x: (x[2], x[3]))
        return best[0], best[1]

    # Partial only: highest condition count, latest tie-break
    partial = [(ph, at, cnt, i) for i, (ph, at, cnt) in enumerate(matches)]
    best = max(partial, key=lambda x: (x[2], x[3]))
    return best[0], None


def _check_rise_and_fall(
    gp: GreatPerson,
    char_events: list[Event],
    current_turn: int,
    matches: list[tuple[str | None, str | None, int]],
) -> None:
    career_length = (
        (gp.death_turn - gp.born_turn)
        if gp.death_turn is not None
        else (current_turn - gp.born_turn)
    )
    if career_length < RISING_CAREER_THRESHOLD:
        return

    has_death = any(e.event_type == "character_death" for e in char_events)
    # Exile only counts as "fallen" for Rise-and-Fall when the character is no longer
    # active — an active exiled character may still return (Exile-and-Return arc).
    has_exile_fallen = (
        any(e.event_type == "conquest_exile" for e in char_events) and not gp.active
    )

    if has_death or has_exile_fallen:
        matches.append(("fallen", ARC_RISE_AND_FALL, 2))
    elif gp.active:
        matches.append(("rising", None, 1))


def _check_exile_and_return(
    gp: GreatPerson,
    char_events: list[Event],
    matches: list[tuple[str | None, str | None, int]],
) -> None:
    has_exile = any(e.event_type == "conquest_exile" for e in char_events)
    has_return = any(e.event_type == "exile_return" for e in char_events)

    if not has_exile:
        return

    if has_return:
        # Count both exile and return conditions — gives cnt=3 so Exile-and-Return
        # beats other cnt=2 complete matches (e.g. Wanderer) on priority tie-break.
        matches.append((None, ARC_EXILE_AND_RETURN, 3))
    else:
        matches.append(("exiled", None, 1))


def _check_dynasty_founder(
    gp: GreatPerson,
    dynasty_registry: DynastyRegistry | None,
    matches: list[tuple[str | None, str | None, int]],
) -> None:
    if dynasty_registry is None or gp.agent_id is None or gp.dynasty_id is None:
        return

    # Iterate registry to find dynasty by ID (avoids private _find() which raises ValueError)
    dynasty = None
    for d in dynasty_registry.dynasties:
        if d.dynasty_id == gp.dynasty_id:
            dynasty = d
            break
    if dynasty is None or dynasty.founder_id != gp.agent_id:
        return

    if len(dynasty.members) >= 2:
        matches.append(("founding", ARC_DYNASTY_FOUNDER, 2))
    else:
        matches.append(("founding", None, 1))


def _check_tragic_hero(
    gp: GreatPerson,
    matches: list[tuple[str | None, str | None, int]],
) -> None:
    if gp.trait != "bold":
        return

    if gp.fate == "dead" and gp.death_turn is not None:
        career = gp.death_turn - gp.born_turn
        if career < TRAGIC_HERO_LIFESPAN_THRESHOLD:
            matches.append(("embattled", ARC_TRAGIC_HERO, 2))
            return

    if gp.active:
        matches.append(("embattled", None, 1))


def _check_wanderer(
    gp: GreatPerson,
    char_events: list[Event],
    matches: list[tuple[str | None, str | None, int]],
) -> None:
    migration_count = sum(
        1 for e in char_events if e.event_type == "notable_migration"
    )

    if migration_count >= 3:
        matches.append(("wandering", ARC_WANDERER, 2))
    elif migration_count >= 2:
        matches.append(("wandering", None, 1))


def _check_defector(
    gp: GreatPerson,
    char_events: list[Event],
    matches: list[tuple[str | None, str | None, int]],
) -> None:
    if gp.civilization == gp.origin_civilization:
        return

    has_secession = any(e.event_type == "secession_defection" for e in char_events)
    has_exile = any(e.event_type == "conquest_exile" for e in char_events)

    if has_secession or has_exile:
        matches.append(("defecting", ARC_DEFECTOR, 2))
    else:
        matches.append(("defecting", None, 1))


def _check_prophet(
    gp: GreatPerson,
    char_events: list[Event],
    matches: list[tuple[str | None, str | None, int]],
) -> None:
    has_return = any(e.event_type == "pilgrimage_return" for e in char_events)

    if has_return:
        matches.append(("converting", ARC_PROPHET, 2))
    elif gp.pilgrimage_return_turn is not None:
        # Currently mid-pilgrimage
        matches.append(("converting", None, 1))


def _check_martyr(
    gp: GreatPerson,
    char_events: list[Event],
    matches: list[tuple[str | None, str | None, int]],
) -> None:
    if gp.role != "prophet":
        return

    if gp.fate == "dead" and gp.death_turn is not None:
        career = gp.death_turn - gp.born_turn
        if career < MARTYR_LIFESPAN_THRESHOLD:
            matches.append(("persecuted", ARC_MARTYR, 2))
            return

    # Partial: prophet displaced by conquest
    has_exile = any(e.event_type == "conquest_exile" for e in char_events)
    if has_exile:
        matches.append(("persecuted", None, 1))
