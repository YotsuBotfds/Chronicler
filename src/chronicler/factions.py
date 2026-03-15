"""M22: Faction system — influence, power struggles, weight modifiers, succession."""
from __future__ import annotations

from chronicler.models import (
    ActionType,
    Event,
    FactionType,
    FactionState,
    Civilization,
    Leader,
)

# ---------------------------------------------------------------------------
# Mapping tables
# ---------------------------------------------------------------------------

TRAIT_FACTION_MAP: dict[str, FactionType] = {
    "aggressive": FactionType.MILITARY,
    "bold": FactionType.MILITARY,
    "ambitious": FactionType.MILITARY,
    "cautious": FactionType.MERCHANT,
    "calculating": FactionType.MERCHANT,
    "shrewd": FactionType.MERCHANT,
    "visionary": FactionType.CULTURAL,
    "zealous": FactionType.CULTURAL,
}

FOCUS_FACTION_MAP: dict[str, FactionType] = {
    "navigation": FactionType.MERCHANT,
    "commerce": FactionType.MERCHANT,
    "banking": FactionType.MERCHANT,
    "agriculture": FactionType.MERCHANT,
    "mechanization": FactionType.MERCHANT,
    "railways": FactionType.MERCHANT,
    "networks": FactionType.MERCHANT,
    "metallurgy": FactionType.MILITARY,
    "fortification": FactionType.MILITARY,
    "naval_power": FactionType.MILITARY,
    "exploration": FactionType.MILITARY,
    "surveillance": FactionType.MILITARY,
    "scholarship": FactionType.CULTURAL,
    "printing": FactionType.CULTURAL,
    "media": FactionType.CULTURAL,
}

# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def normalize_influence(factions: FactionState) -> None:
    # First pass: normalize to sum-to-1
    total = sum(factions.influence.values())
    if total > 0:
        for ft in FactionType:
            factions.influence[ft] /= total
    # Iteratively enforce floor of 0.05: clamp undervalued factions and
    # redistribute the "borrowed" share from overvalued ones
    floor = 0.05
    for _ in range(10):
        under = [ft for ft in FactionType if factions.influence[ft] < floor]
        if not under:
            break
        deficit = sum(floor - factions.influence[ft] for ft in under)
        over = [ft for ft in FactionType if factions.influence[ft] > floor]
        over_total = sum(factions.influence[ft] for ft in over)
        for ft in under:
            factions.influence[ft] = floor
        for ft in over:
            factions.influence[ft] -= deficit * (factions.influence[ft] / over_total)
    # Final renormalize for floating-point safety
    total = sum(factions.influence.values())
    for ft in FactionType:
        factions.influence[ft] /= total


def shift_faction_influence(factions: FactionState, faction_type: FactionType, amount: float) -> None:
    factions.influence[faction_type] += amount
    normalize_influence(factions)


def get_dominant_faction(factions: FactionState) -> FactionType:
    return max(factions.influence, key=factions.influence.get)


def get_leader_faction_alignment(leader: Leader, factions: FactionState) -> float:
    leader_faction = TRAIT_FACTION_MAP.get(leader.trait)
    if leader_faction is None:
        return 0.5
    return factions.influence.get(leader_faction, 0.33)


def _event_is_win(event: Event, civ: Civilization, faction_type: FactionType) -> bool:
    if civ.name not in event.actors:
        return False
    if faction_type == FactionType.MILITARY:
        if event.event_type == "war" and len(event.actors) >= 2:
            is_attacker = event.actors[0] == civ.name
            if (is_attacker and "attacker_wins" in event.description) or \
               (not is_attacker and "defender_wins" in event.description):
                return True
        elif event.event_type == "expand" and event.importance >= 5:
            return True
    elif faction_type == FactionType.MERCHANT:
        if event.event_type == "trade" and len(event.actors) >= 2:
            return True
    elif faction_type == FactionType.CULTURAL:
        if event.event_type in ("cultural_work", "movement_adoption"):
            return True
    return False


def count_faction_wins(world, civ: Civilization, faction_type: FactionType, lookback: int = 10) -> int:
    min_turn = world.turn - lookback
    count = 0
    for event in world.events_timeline:
        if event.turn < min_turn:
            continue
        if _event_is_win(event, civ, faction_type):
            count += 1
    return count


# ---------------------------------------------------------------------------
# Action weight modifier
# ---------------------------------------------------------------------------

FACTION_WEIGHTS: dict[FactionType, dict[ActionType, float]] = {
    FactionType.MILITARY: {
        ActionType.WAR: 1.8, ActionType.EXPAND: 1.5,
        ActionType.DIPLOMACY: 0.6, ActionType.TRADE: 0.7,
    },
    FactionType.MERCHANT: {
        ActionType.TRADE: 1.8, ActionType.BUILD: 1.5,
        ActionType.EMBARGO: 1.3, ActionType.WAR: 0.5,
    },
    FactionType.CULTURAL: {
        ActionType.INVEST_CULTURE: 1.8, ActionType.DIPLOMACY: 1.5,
        ActionType.WAR: 0.4, ActionType.EXPAND: 0.6,
    },
}


def get_faction_weight_modifier(civ: Civilization, action: ActionType) -> float:
    dominant = get_dominant_faction(civ.factions)
    influence = civ.factions.influence[dominant]
    faction_weight = FACTION_WEIGHTS.get(dominant, {}).get(action, 1.0)
    return faction_weight ** influence


# ---------------------------------------------------------------------------
# Power struggle detection and resolution
# ---------------------------------------------------------------------------

def check_power_struggle(factions: FactionState) -> tuple[FactionType, FactionType] | None:
    sorted_factions = sorted(factions.influence.items(), key=lambda x: x[1], reverse=True)
    top, second = sorted_factions[0], sorted_factions[1]
    if top[1] - second[1] < 0.05 and second[1] > 0.30:
        return (top[0], second[0])
    return None


def get_struggling_factions(civ: Civilization) -> tuple[FactionType, FactionType]:
    sorted_factions = sorted(civ.factions.influence.items(), key=lambda x: x[1], reverse=True)
    return (sorted_factions[0][0], sorted_factions[1][0])


def resolve_win_tie(world, civ: Civilization, contenders: tuple[FactionType, FactionType]) -> FactionType:
    min_turn = world.turn - 10
    latest: dict[FactionType, int] = {ft: -1 for ft in contenders}
    for event in world.events_timeline:
        if event.turn < min_turn or civ.name not in event.actors:
            continue
        for ft in contenders:
            if _event_is_win(event, civ, ft):
                latest[ft] = max(latest[ft], event.turn)
    if latest[contenders[0]] != latest[contenders[1]]:
        return max(latest, key=latest.get)
    if FactionType.MILITARY in contenders:
        return FactionType.MILITARY
    return contenders[0]


def resolve_power_struggle(civ: Civilization, world) -> list[Event]:
    contenders = get_struggling_factions(civ)
    wins = {}
    for ft in contenders:
        wins[ft] = count_faction_wins(world, civ, ft, lookback=10)
    if wins[contenders[0]] != wins[contenders[1]]:
        winner = max(wins, key=wins.get)
    else:
        winner = resolve_win_tie(world, civ, contenders)
    turns = civ.factions.power_struggle_turns
    shift_faction_influence(civ.factions, winner, +0.15)
    civ.factions.power_struggle = False
    civ.factions.power_struggle_turns = 0
    return [Event(
        turn=world.turn, event_type="power_struggle_resolved",
        actors=[civ.name],
        description=f"{civ.name}: {winner.value} faction prevails after {turns} turns of infighting.",
        importance=7,
    )]


# ---------------------------------------------------------------------------
# Per-turn faction tick (phase 10 — consequences)
# ---------------------------------------------------------------------------

def tick_factions(world) -> list[Event]:
    """Main per-turn faction tick. Runs in phase 10 (consequences)."""
    events: list[Event] = []
    current_turn = world.turn

    for civ in world.civilizations:
        if not civ.regions:
            continue

        # 1. Record current dominant faction
        old_dominant = get_dominant_faction(civ.factions)

        # 2. Scan current-turn events for influence shifts
        for event in world.events_timeline:
            if event.turn != current_turn:
                continue
            if civ.name not in event.actors:
                continue

            if event.event_type == "war" and len(event.actors) >= 2:
                is_attacker = event.actors[0] == civ.name
                if (is_attacker and "attacker_wins" in event.description) or \
                   (not is_attacker and "defender_wins" in event.description):
                    # War win
                    civ.factions.influence[FactionType.MILITARY] += 0.10
                else:
                    # War loss
                    civ.factions.influence[FactionType.MILITARY] -= 0.10
                    civ.factions.influence[FactionType.MERCHANT] += 0.05
                    civ.factions.influence[FactionType.CULTURAL] += 0.05

            elif event.event_type == "trade" and len(event.actors) >= 2:
                civ.factions.influence[FactionType.MERCHANT] += 0.08

            elif event.event_type == "expand" and event.importance >= 5:
                civ.factions.influence[FactionType.MILITARY] += 0.05
                civ.factions.influence[FactionType.MERCHANT] += 0.03

            elif event.event_type in ("cultural_work", "movement_adoption"):
                civ.factions.influence[FactionType.CULTURAL] += 0.08

            elif event.event_type == "famine":
                civ.factions.influence[FactionType.MILITARY] -= 0.03
                civ.factions.influence[FactionType.MERCHANT] -= 0.03
                civ.factions.influence[FactionType.CULTURAL] += 0.06

            elif event.event_type == "tech_focus_selected":
                focus_name = civ.active_focus
                if focus_name and focus_name in FOCUS_FACTION_MAP:
                    civ.factions.influence[FOCUS_FACTION_MAP[focus_name]] += 0.05

        # 3. State-based shifts
        if civ.treasury <= 0:
            civ.factions.influence[FactionType.MERCHANT] -= 0.15
            civ.factions.influence[FactionType.CULTURAL] += 0.05

        if civ.last_income > civ.military:
            civ.factions.influence[FactionType.MERCHANT] += 0.08

        # 4. GP per-turn bonuses
        for gp in civ.great_persons:
            if not gp.alive or not gp.active:
                continue
            if gp.role == "general":
                civ.factions.influence[FactionType.MILITARY] += 0.03
            elif gp.role == "merchant":
                civ.factions.influence[FactionType.MERCHANT] += 0.03
            elif gp.role == "prophet":
                civ.factions.influence[FactionType.CULTURAL] += 0.03
            elif gp.role == "scientist":
                if civ.active_focus and civ.active_focus in FOCUS_FACTION_MAP:
                    civ.factions.influence[FOCUS_FACTION_MAP[civ.active_focus]] += 0.02

        # 5. Normalize influence
        normalize_influence(civ.factions)

        # 6. Check for dominance shift
        new_dominant = get_dominant_faction(civ.factions)
        if new_dominant != old_dominant:
            events.append(Event(
                turn=current_turn, event_type="faction_dominance_shift",
                actors=[civ.name],
                description=(
                    f"{civ.name}: {new_dominant.value} faction overtakes "
                    f"{old_dominant.value} as dominant influence."
                ),
                importance=6,
            ))

        # 7. Power struggle processing
        if civ.succession_crisis_turns_remaining > 0:
            # Rule 2 — crisis pauses power struggle
            pass
        elif civ.factions.power_struggle:
            civ.factions.power_struggle_turns += 1
            from chronicler.emergence import get_severity_multiplier
            civ.stability -= int(3 * get_severity_multiplier(civ))
            if civ.stability < 0:
                civ.stability = 0
            if civ.factions.power_struggle_turns > 5:
                events.extend(resolve_power_struggle(civ, world))
        else:
            struggle = check_power_struggle(civ.factions)
            if struggle is not None:
                civ.factions.power_struggle = True
                civ.factions.power_struggle_turns = 0
                events.append(Event(
                    turn=current_turn, event_type="power_struggle_started",
                    actors=[civ.name],
                    description=(
                        f"{civ.name}: {struggle[0].value} and {struggle[1].value} "
                        f"factions begin a power struggle."
                    ),
                    importance=6,
                ))

    return events
