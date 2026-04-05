"""Succession crisis mechanics, exiled leaders, legacy expansion."""
from __future__ import annotations

import random

from chronicler.models import Civilization, Event, GreatPerson, Leader, NamedEvent, WorldState
from chronicler.models import Disposition
from chronicler.utils import civ_index, stable_hash_int
from chronicler.emergence import get_severity_multiplier
from chronicler.leaders import strip_title, _compose_regnal_name, TITLES


# Disposition ordering used for host-selection in exile logic.
# Imported from action_engine if available; defined locally as fallback.
try:
    from chronicler.action_engine import DISPOSITION_ORDER
except ImportError:
    DISPOSITION_ORDER: dict[Disposition, int] = {
        Disposition.HOSTILE: 0,
        Disposition.SUSPICIOUS: 1,
        Disposition.NEUTRAL: 2,
        Disposition.FRIENDLY: 3,
        Disposition.ALLIED: 4,
    }


# ---------------------------------------------------------------------------
# Task 8: Crisis probability formula
# ---------------------------------------------------------------------------

def compute_crisis_probability(civ: Civilization, world: WorldState) -> float:
    """Return probability [0.05, 0.40] of succession crisis, or 0.0 if ineligible."""
    if len(civ.regions) < 3:
        return 0.0

    base = 0.15
    region_factor = len(civ.regions) / 5
    instability_factor = 1 - (civ.stability / 100)

    leader_reign = world.turn - civ.leader.reign_start
    has_active_vassals = any(vr.overlord == civ.name for vr in world.vassal_relations)

    modifiers = 1.0
    if civ.leader.succession_type != "heir":
        modifiers *= 1.5
    if has_active_vassals:
        modifiers *= 1.3
    if leader_reign < 5:
        modifiers *= 1.2
    if civ.asabiya > 0.7:
        modifiers *= 0.6
    if "martial" in civ.traditions:
        modifiers *= 0.8
    if "resilience" in civ.traditions:
        modifiers *= 0.8
    if leader_reign > 15:
        modifiers *= 0.7

    # Faction modifiers
    from chronicler.factions import get_leader_faction_alignment
    if civ.factions.power_struggle:
        modifiers *= 1.4
    alignment = get_leader_faction_alignment(civ.leader, civ.factions)
    if alignment > 0.5:
        modifiers *= 0.8
    elif alignment < 0.2:
        modifiers *= 1.3

    return max(0.05, min(0.40, base * region_factor * instability_factor * modifiers))


# ---------------------------------------------------------------------------
# Task 9: Multi-turn crisis state machine
# ---------------------------------------------------------------------------

def is_in_crisis(civ: Civilization) -> bool:
    """Return True if the civilization is currently in a succession crisis."""
    return civ.succession_crisis_turns_remaining > 0


def trigger_crisis(civ: Civilization, world: WorldState) -> None:
    """Begin a succession crisis. Duration scales with region count (1-5 turns)."""
    rng = random.Random(
        stable_hash_int("trigger_crisis", world.seed, world.turn, civ.name)
    )
    duration = min(5, max(1, len(civ.regions) // 2 + rng.randint(1, 2)))
    civ.succession_crisis_turns_remaining = duration

    # Build faction-weighted candidate list
    from chronicler.factions import generate_faction_candidates
    civ.succession_candidates = generate_faction_candidates(civ, world)


def tick_crisis(civ: Civilization, world: WorldState) -> None:
    """Decrement crisis timer by 1 (does not resolve — call resolve_crisis when ready)."""
    if civ.succession_crisis_turns_remaining > 0:
        civ.succession_crisis_turns_remaining -= 1


def resolve_crisis(civ: Civilization, world: WorldState) -> list[Event]:
    """End the crisis, generate a successor, and return narrative events."""
    from chronicler.leaders import generate_successor, apply_leader_legacy

    events: list[Event] = []

    old_leader = civ.leader
    old_leader.alive = False

    # Apply legacy if earned
    legacy_event = apply_leader_legacy(civ, old_leader, world)
    if legacy_event:
        events.append(legacy_event)

    # Determine succession type from candidates if available
    force_type: str | None = None
    if civ.succession_candidates:
        rng = random.Random(
            stable_hash_int("resolve_crisis", world.seed, world.turn, civ.name)
        )
        candidate = rng.choice(civ.succession_candidates)
        candidate_type = candidate.get("type", "")
        if candidate_type == "military":
            force_type = "general"
        elif candidate_type == "usurper":
            force_type = "usurper"

    new_leader = generate_successor(civ, world, seed=world.seed, force_type=force_type)

    # Inherit grudges from old to new leader
    inherit_grudges(old_leader, new_leader)

    civ.leader = new_leader
    civ.succession_crisis_turns_remaining = 0
    civ.succession_candidates = []

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

    return events


# ---------------------------------------------------------------------------
# Task 10: Personal grudges
# ---------------------------------------------------------------------------

def add_grudge(leader: Leader, rival_name: str, rival_civ: str, turn: int) -> None:
    """Add or refresh a grudge against a rival. Refreshes intensity if already tracked."""
    for g in leader.grudges:
        if g["rival_civ"] == rival_civ:
            g["intensity"] = 1.0
            g["origin_turn"] = turn
            g["rival_name"] = rival_name
            return
    leader.grudges.append({
        "rival_name": rival_name,
        "rival_civ": rival_civ,
        "intensity": 1.0,
        "origin_turn": turn,
    })


def decay_grudges(leader: Leader, current_turn: int, rival_alive: bool = True, world=None) -> None:
    """Decay grudge intensity every 5 turns. Removes grudges that drop to near zero.

    If *world* is provided, rival alive status is determined per-grudge from world state.
    Otherwise, the *rival_alive* parameter applies to all grudges.
    """
    to_remove = []
    for g in leader.grudges:
        turns_since = current_turn - g["origin_turn"]
        if turns_since > 0 and turns_since % 5 == 0:
            # Determine per-grudge rival alive status when world is available
            if world is not None:
                rival_civ_name = g.get("rival_civ")
                g_rival_alive = any(
                    c.name == rival_civ_name and c.leader.alive
                    for c in world.civilizations
                )
            else:
                g_rival_alive = rival_alive
            decay = 0.2 if not g_rival_alive else 0.1
            g["intensity"] = max(0, g["intensity"] - decay)
        if g["intensity"] < 0.01:
            to_remove.append(g)
    for g in to_remove:
        leader.grudges.remove(g)


def inherit_grudges(old_leader: Leader, new_leader: Leader) -> None:
    """Transfer grudges from old leader to new leader at 50% intensity."""
    for g in old_leader.grudges:
        inherited_intensity = g["intensity"] * 0.5
        if inherited_intensity >= 0.01:
            new_leader.grudges.append({**g, "intensity": inherited_intensity})


# ---------------------------------------------------------------------------
# Task 11: Exiled leaders
# ---------------------------------------------------------------------------

def create_exiled_leader(
    old_leader: Leader, origin_civ: Civilization, world: WorldState
) -> str | None:
    """Place old_leader as an exile great-person in the most friendly eligible civ.

    Returns the host civ name, or None if no suitable host exists.
    """
    best_host = None
    best_disp = -1
    for civ in world.civilizations:
        if civ.name == origin_civ.name or not civ.regions:
            continue
        rel = world.relationships.get(origin_civ.name, {}).get(civ.name)
        if rel and rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
            continue
        disp_val = DISPOSITION_ORDER.get(rel.disposition, 2) if rel else 2
        if disp_val > best_disp:
            best_disp = disp_val
            best_host = civ

    if best_host is None:
        return None

    exile = GreatPerson(
        name=old_leader.name,
        role="exile",
        trait=old_leader.trait,
        civilization=best_host.name,
        origin_civilization=origin_civ.name,
        born_turn=world.turn,
        region=(
            best_host.capital_region
            or (best_host.regions[0] if best_host.regions else None)
        ),
    )
    best_host.great_persons.append(exile)
    return best_host.name


def apply_exile_pretender_drain(world: WorldState, acc=None) -> None:
    """For each active exile, drain stability from origin civ and boost host culture."""
    for civ in world.civilizations:
        for gp in civ.great_persons:
            if gp.role != "exile" or not gp.active:
                continue
            origin = next(
                (c for c in world.civilizations if c.name == gp.origin_civilization), None
            )
            if origin and origin.regions:
                mult = get_severity_multiplier(origin, world)
                if acc is not None:
                    origin_idx = civ_index(world, origin.name)
                    acc.add(origin_idx, origin, "stability", -int(2 * mult), "signal")
                else:
                    origin.stability = max(origin.stability - int(2 * mult), 0)
            if acc is not None:
                civ_idx = civ_index(world, civ.name)
                acc.add(civ_idx, civ, "culture", 3, "guard-shock")
            else:
                civ.culture = min(civ.culture + 3, 100)


def check_exile_restoration(world: WorldState, acc=None) -> list[Event]:
    """Check whether any exile restores to power in their origin civ.

    Probability scales with recognition count and fires when origin stability < 20.
    """
    events: list[Event] = []
    for civ in world.civilizations:
        for gp in list(civ.great_persons):
            if gp.role != "exile" or not gp.active:
                continue
            origin = next(
                (c for c in world.civilizations if c.name == gp.origin_civilization), None
            )
            if not origin or not origin.regions:
                continue
            if origin.stability >= 20:
                continue
            recognized_count = len(gp.recognized_by)
            base_prob = 0.05 + (0.03 * recognized_count)
            from chronicler.factions import GP_ROLE_TO_FACTION, get_dominant_faction
            exile_faction = GP_ROLE_TO_FACTION.get(gp.role)
            origin_dominant = get_dominant_faction(origin.factions)
            if exile_faction and exile_faction == origin_dominant:
                base_prob *= 0.3
            elif exile_faction:
                base_prob *= 1.5
            rng = random.Random(
                stable_hash_int("exile_restoration", world.seed, world.turn, gp.name)
            )
            if rng.random() < base_prob:
                gp.active = False
                gp.fate = "ascended"
                civ.great_persons.remove(gp)
                world.retired_persons.append(gp)

                # Properly depose the incumbent leader before installing the exile
                from chronicler.leaders import apply_leader_legacy
                incumbent = origin.leader
                incumbent.alive = False
                legacy_event = apply_leader_legacy(origin, incumbent, world)
                if legacy_event:
                    events.append(legacy_event)
                # Deposed incumbent becomes an exile (if eligible host exists)
                create_exiled_leader(incumbent, origin, world)

                # M51: Use gp.base_name as throne_name for regnal naming
                throne_name = getattr(gp, "base_name", None) or strip_title(gp.name)
                count = origin.regnal_name_counts.get(throne_name, 0)
                ordinal = count + 1 if count > 0 else 0  # 0, 2, 3, 4, ...
                origin.regnal_name_counts[throne_name] = count + 1
                title = rng.choice(TITLES)
                display_name = _compose_regnal_name(title, throne_name, ordinal)

                origin.leader = Leader(
                    name=display_name,
                    trait=gp.trait,
                    reign_start=world.turn,
                    succession_type="restoration",
                    throne_name=throne_name,
                    regnal_ordinal=ordinal,
                    predecessor_name=incumbent.name,
                )
                if acc is not None:
                    from chronicler.utils import civ_index
                    origin_idx = civ_index(world, origin.name)
                    acc.add(origin_idx, origin, "stability", 15, "keep")
                else:
                    origin.stability = min(origin.stability + 15, 100)
                events.append(Event(
                    turn=world.turn,
                    event_type="restoration",
                    actors=[origin.name, display_name],
                    description=f"{display_name} restored to power in {origin.name}, deposing {incumbent.name}.",
                    importance=9,
                ))
    return events
