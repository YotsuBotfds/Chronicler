"""M22: Faction system — influence, power struggles, weight modifiers, succession."""
from __future__ import annotations

import random

from chronicler.models import (
    ActionType,
    Disposition,
    Event,
    FactionType,
    FactionState,
    Civilization,
    Leader,
    WorldState,
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

FACTION_CANDIDATE_TYPE: dict[FactionType, str] = {
    FactionType.MILITARY: "general",
    FactionType.MERCHANT: "elected",
    FactionType.CULTURAL: "heir",
}

GP_ROLE_TO_FACTION: dict[str, FactionType] = {
    "general": FactionType.MILITARY,
    "merchant": FactionType.MERCHANT,
    "prophet": FactionType.CULTURAL,
}

GP_SUCCESSION_TYPE: dict[str, str] = {
    "general": "general",
    "merchant": "elected",
    "prophet": "heir",
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
    # Iteratively enforce floor of 0.10: clamp undervalued factions and
    # redistribute the "borrowed" share from overvalued ones
    floor = 0.10
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
    if top[1] - second[1] < 0.15 and second[1] > 0.40:
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
    shift_faction_influence(civ.factions, winner, +0.35)  # M19b: power struggle resolution shift
    civ.factions.power_struggle = False
    civ.factions.power_struggle_turns = 0
    civ.factions.power_struggle_cooldown = 10  # M19b: immune for 10 turns
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

            # M19b iter4: all event shifts halved for slower faction evolution
            if event.event_type == "war" and len(event.actors) >= 2:
                is_attacker = event.actors[0] == civ.name
                if (is_attacker and "attacker_wins" in event.description) or \
                   (not is_attacker and "defender_wins" in event.description):
                    # War win
                    civ.factions.influence[FactionType.MILITARY] += 0.05
                else:
                    # War loss — merchants profit from power vacuums
                    civ.factions.influence[FactionType.MILITARY] -= 0.05
                    civ.factions.influence[FactionType.MERCHANT] += 0.035
                    civ.factions.influence[FactionType.CULTURAL] += 0.01

            elif event.event_type == "trade" and len(event.actors) >= 2:
                civ.factions.influence[FactionType.MERCHANT] += 0.04

            elif event.event_type == "expand" and event.importance >= 5:
                civ.factions.influence[FactionType.MILITARY] += 0.025
                civ.factions.influence[FactionType.MERCHANT] += 0.015

            elif event.event_type in ("cultural_work", "movement_adoption"):
                civ.factions.influence[FactionType.CULTURAL] += 0.04

            elif event.event_type == "famine":
                civ.factions.influence[FactionType.MILITARY] -= 0.015
                civ.factions.influence[FactionType.MERCHANT] -= 0.015
                civ.factions.influence[FactionType.CULTURAL] += 0.015

            elif event.event_type == "tech_focus_selected":
                focus_name = civ.active_focus
                if focus_name and focus_name in FOCUS_FACTION_MAP:
                    civ.factions.influence[FOCUS_FACTION_MAP[focus_name]] += 0.025

        # 3. State-based shifts (halved)
        if civ.treasury <= 0:
            civ.factions.influence[FactionType.MERCHANT] -= 0.075
            civ.factions.influence[FactionType.CULTURAL] += 0.01

        if civ.last_income > civ.military:
            civ.factions.influence[FactionType.MERCHANT] += 0.04

        # 4. GP per-turn bonuses (halved)
        for gp in civ.great_persons:
            if not gp.alive or not gp.active:
                continue
            if gp.role == "general":
                civ.factions.influence[FactionType.MILITARY] += 0.015
            elif gp.role == "merchant":
                civ.factions.influence[FactionType.MERCHANT] += 0.015
            elif gp.role == "prophet":
                civ.factions.influence[FactionType.CULTURAL] += 0.015
            elif gp.role == "scientist":
                if civ.active_focus and civ.active_focus in FOCUS_FACTION_MAP:
                    civ.factions.influence[FOCUS_FACTION_MAP[civ.active_focus]] += 0.01

        # 5. Normalize influence
        normalize_influence(civ.factions)

        # 5b. Apply pending succession faction shift AFTER normalization.
        # Raw add WITHOUT re-normalizing — normalization's floor enforcement
        # absorbs all shifts when dominant is at ceiling (0.80 with floor 0.10).
        # The raw shift is visible in the snapshot; next turn's normalize cleans up.
        if civ.factions.pending_faction_shift:
            winning_ft = FactionType(civ.factions.pending_faction_shift)
            civ.factions.influence[winning_ft] += 0.20
            civ.factions.pending_faction_shift = None

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
                importance=5,
            ))

        # 7. Power struggle processing
        # M19b: Decrement cooldown
        if civ.factions.power_struggle_cooldown > 0:
            civ.factions.power_struggle_cooldown -= 1

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
        elif civ.factions.power_struggle_cooldown <= 0:
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


# ---------------------------------------------------------------------------
# Succession integration — candidates, resolution, grudge inheritance
# ---------------------------------------------------------------------------

def generate_faction_candidates(civ: Civilization, world: WorldState) -> list[dict]:
    """Create faction-weighted succession candidates.

    - One internal candidate per faction with influence >= 0.15
    - External candidates from allied/friendly civs
    - GP candidates from active general/merchant/prophet
    """
    candidates: list[dict] = []

    # Internal candidates: one per faction with sufficient influence
    for ft in FactionType:
        if civ.factions.influence.get(ft, 0) >= 0.15:
            candidates.append({
                "faction": ft.value,
                "type": FACTION_CANDIDATE_TYPE[ft],
                "source": "internal",
                "weight": civ.factions.influence[ft],
            })

    # External candidates from allied/friendly civs
    for other in world.civilizations:
        if other.name == civ.name or not other.regions:
            continue
        rel = world.relationships.get(civ.name, {}).get(other.name)
        if rel and rel.disposition in (Disposition.ALLIED, Disposition.FRIENDLY):
            other_dominant = get_dominant_faction(other.factions)
            candidates.append({
                "type": FACTION_CANDIDATE_TYPE[other_dominant],
                "faction": other_dominant.value,
                "weight": 0.1,
                "backer_civ": other.name,
            })

    # GP candidates from active general/merchant/prophet
    dominant = get_dominant_faction(civ.factions)
    for gp in civ.great_persons:
        if not gp.active or not gp.alive:
            continue
        if gp.role not in GP_ROLE_TO_FACTION:
            continue
        gp_faction = GP_ROLE_TO_FACTION[gp.role]
        weight = civ.factions.influence.get(gp_faction, 0)
        if gp_faction == dominant:
            weight += 0.10
        candidates.append({
            "faction": gp_faction.value,
            "type": GP_SUCCESSION_TYPE[gp.role],
            "source": "great_person",
            "gp_name": gp.name,
            "gp_trait": gp.trait,
            "weight": weight,
        })

    return candidates


def inherit_grudges_with_factions(
    old_leader: Leader, new_leader: Leader, factions: FactionState
) -> None:
    """Transfer grudges from old leader to new leader at faction-variable rate.

    - Same faction (both traits map to same FactionType): 0.7
    - Different faction: 0.3
    - Neutral trait (not in TRAIT_FACTION_MAP): 0.5
    - Filters out grudges with inherited intensity < 0.01
    """
    old_faction = TRAIT_FACTION_MAP.get(old_leader.trait)
    new_faction = TRAIT_FACTION_MAP.get(new_leader.trait)

    if old_faction is None or new_faction is None:
        rate = 0.5
    elif old_faction == new_faction:
        rate = 0.7
    else:
        rate = 0.3

    for g in old_leader.grudges:
        inherited_intensity = g["intensity"] * rate
        if inherited_intensity >= 0.01:
            new_leader.grudges.append({**g, "intensity": inherited_intensity})


def total_effective_capacity(civ: Civilization, world) -> int:
    """Sum of effective_capacity across all civ-controlled regions."""
    from chronicler.ecology import effective_capacity
    region_map = {r.name: r for r in world.regions}
    return sum(
        effective_capacity(region_map[rn])
        for rn in civ.regions
        if rn in region_map
    )


def resolve_crisis_with_factions(civ: Civilization, world: WorldState) -> list[Event]:
    """End the crisis using faction-weighted candidate selection.

    Mirrors the full flow of resolve_crisis in succession.py but integrates
    faction candidates, weighted selection, and faction-aware grudge inheritance.
    """
    from chronicler.leaders import generate_successor, apply_leader_legacy
    from chronicler.succession import create_exiled_leader
    from chronicler.culture import upgrade_disposition

    events: list[Event] = []
    rng = random.Random(world.seed + world.turn + hash(civ.name))

    old_leader = civ.leader
    candidates = civ.succession_candidates

    # 1. Select winner from candidates
    winner = None
    if candidates:
        if rng.random() < 0.10:
            winner = rng.choice(candidates)
        else:
            weights = [c["weight"] for c in candidates]
            winner = rng.choices(candidates, weights=weights, k=1)[0]

    # Determine force_type from winner
    force_type: str | None = None
    if winner:
        candidate_type = winner.get("type", "")
        if candidate_type in ("general", "elected", "heir"):
            force_type = candidate_type
        elif candidate_type == "military":
            force_type = "general"
        elif candidate_type == "usurper":
            force_type = "usurper"

    # 2. Mark old leader dead
    old_leader.alive = False

    # 3. Apply legacy
    legacy_event = apply_leader_legacy(civ, old_leader, world)
    if legacy_event:
        events.append(legacy_event)

    # 4. Generate successor
    new_leader = generate_successor(civ, world, seed=world.seed, force_type=force_type)

    # 5. Override grudges: clear the ones from generate_successor, apply faction-aware inheritance
    new_leader.grudges = []
    inherit_grudges_with_factions(old_leader, new_leader, civ.factions)

    # 6. Assign new leader
    civ.leader = new_leader

    # 7. Mark faction shift for post-normalization application in tick_factions
    if winner and winner.get("faction"):
        civ.factions.pending_faction_shift = winner["faction"]

    # 8. Handle GP winner (transfer name/trait, mark gp dead)
    if winner and winner.get("source") == "great_person":
        gp_name = winner.get("gp_name")
        gp_trait = winner.get("gp_trait")
        if gp_name:
            new_leader.name = gp_name
        if gp_trait:
            new_leader.trait = gp_trait
        # Mark the GP dead
        for gp in civ.great_persons:
            if gp.name == gp_name and gp.active:
                gp.active = False
                gp.alive = False
                gp.fate = "ascended_to_leadership"
                break

    # 9. Handle external backer (upgrade disposition)
    if winner and winner.get("backer_civ"):
        backer_name = winner.get("backer_civ")
        if backer_name:
            rel = world.relationships.get(civ.name, {}).get(backer_name)
            if rel:
                rel.disposition = upgrade_disposition(rel.disposition)
            # Upgrade the reverse direction too
            rev_rel = world.relationships.get(backer_name, {}).get(civ.name)
            if rev_rel:
                rev_rel.disposition = upgrade_disposition(rev_rel.disposition)

    # 10. Create exiled leader (call for side effects)
    create_exiled_leader(old_leader, civ, world)

    # 11. Emit event
    events.append(Event(
        turn=world.turn,
        event_type="succession_crisis_resolved",
        actors=[civ.name],
        description=(
            f"The succession crisis in {civ.name} ends: "
            f"{new_leader.name} rises to power after the fall of {old_leader.name}."
        ),
        importance=8,
    ))

    # 12. Clean up crisis state
    civ.succession_crisis_turns_remaining = 0
    civ.succession_candidates = []

    return events
