"""M22: Faction system — influence, power struggles, weight modifiers, succession."""
from __future__ import annotations

from chronicler.models import (
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
