"""Character relationships: rivalry, mentorship, marriage alliance, hostage exchanges."""
from __future__ import annotations

import random

from chronicler.models import GreatPerson, WorldState

# M40: Relationship type constants (match Rust RelationshipType repr(u8))
REL_MENTOR = 0
REL_RIVAL = 1
REL_MARRIAGE = 2
REL_EXILE_BOND = 3
REL_CORELIGIONIST = 4


def dissolve_edges(
    edges: list[tuple],
    active_agent_ids: set[int],
    belief_by_agent: dict[int, int] | None = None,
) -> tuple[list[tuple], list[tuple]]:
    """Dissolve stale edges. Returns (surviving, dissolved).

    Dissolution rules:
    - All types: dissolve if either party not in active_agent_ids (death)
    - CoReligionist: also dissolve if beliefs now differ
    """
    surviving = []
    dissolved = []
    for edge in edges:
        agent_a, agent_b, rel_type, formed_turn = edge
        if agent_a not in active_agent_ids or agent_b not in active_agent_ids:
            dissolved.append(edge)
            continue
        if rel_type == REL_CORELIGIONIST and belief_by_agent is not None:
            belief_a = belief_by_agent.get(agent_a)
            belief_b = belief_by_agent.get(agent_b)
            if belief_a is not None and belief_b is not None and belief_a != belief_b:
                dissolved.append(edge)
                continue
        surviving.append(edge)
    return surviving, dissolved


# --- Rivalry ---

def check_rivalry_formation(world: WorldState, existing_edges: list[tuple]) -> list[tuple]:
    """Form rivalries between same-role agent-source great persons on opposing war sides.
    Returns list of (agent_a, agent_b, REL_RIVAL, formed_turn) tuples.
    agent_a < agent_b by convention (symmetric).
    """
    new_edges = []
    existing_pairs = {(e[0], e[1]) for e in existing_edges if e[2] == REL_RIVAL}
    for war_pair in world.active_wars:
        civ1_name, civ2_name = war_pair
        civ1 = next((c for c in world.civilizations if c.name == civ1_name), None)
        civ2 = next((c for c in world.civilizations if c.name == civ2_name), None)
        if not civ1 or not civ2:
            continue
        for gp1 in civ1.great_persons:
            if not gp1.active or gp1.agent_id is None or gp1.role in ("exile", "hostage"):
                continue
            for gp2 in civ2.great_persons:
                if not gp2.active or gp2.agent_id is None or gp2.role in ("exile", "hostage"):
                    continue
                if gp1.role != gp2.role:
                    continue
                a, b = min(gp1.agent_id, gp2.agent_id), max(gp1.agent_id, gp2.agent_id)
                if (a, b) in existing_pairs:
                    continue
                edge = (a, b, REL_RIVAL, world.turn)
                new_edges.append(edge)
                existing_pairs.add((a, b))
    return new_edges


def dissolve_dead_relationships(world: WorldState, dead_names: set) -> list[dict]:
    """Remove all relationships involving any of the dead persons."""
    dissolved = []
    remaining = []
    for rel in world.character_relationships:
        if rel["person_a"] in dead_names or rel["person_b"] in dead_names:
            dissolved.append(rel)
        else:
            remaining.append(rel)
    world.character_relationships = remaining
    return dissolved


# --- Mentorship ---

MENTORSHIP_COMPATIBLE: dict[str, set] = {
    "general": {"conqueror", "warlike"},
    "scientist": {"builder", "merchant"},
}


def check_mentorship_formation(world: WorldState) -> list[dict]:
    """Form mentorships between a great person and a leader with compatible secondary trait."""
    new_mentorships = []
    existing_mentored = {r["person_b"] for r in world.character_relationships if r["type"] == "mentorship"}
    for civ in world.civilizations:
        if not civ.leader or not civ.leader.secondary_trait:
            continue
        if civ.leader.name in existing_mentored:
            continue
        for gp in civ.great_persons:
            if not gp.active or gp.role in ("exile", "hostage"):
                continue
            compatible = MENTORSHIP_COMPATIBLE.get(gp.role, set())
            if civ.leader.secondary_trait in compatible:
                rel = {
                    "type": "mentorship",
                    "person_a": gp.name,
                    "person_b": civ.leader.name,
                    "civ_a": civ.name,
                    "civ_b": civ.name,
                    "formed_turn": world.turn,
                }
                world.character_relationships.append(rel)
                new_mentorships.append(rel)
                break
    return new_mentorships


# --- Marriage Alliance ---

def check_marriage_formation(world: WorldState) -> list[dict]:
    """Form marriage alliances between great persons of long-allied civs."""
    from chronicler.models import Disposition
    new_marriages = []
    married_persons = (
        {r["person_a"] for r in world.character_relationships if r["type"] == "marriage"}
        | {r["person_b"] for r in world.character_relationships if r["type"] == "marriage"}
    )
    checked_pairs = {(r["civ_a"], r["civ_b"]) for r in world.character_relationships if r["type"] == "marriage"}
    for i, civ1 in enumerate(world.civilizations):
        for civ2 in world.civilizations[i + 1:]:
            pair = (civ1.name, civ2.name)
            if pair in checked_pairs or (civ2.name, civ1.name) in checked_pairs:
                continue
            rel12 = world.relationships.get(civ1.name, {}).get(civ2.name)
            if not rel12 or rel12.disposition != Disposition.ALLIED or rel12.allied_turns < 10:
                continue
            gp1_candidates = [
                gp for gp in civ1.great_persons
                if gp.active and gp.name not in married_persons and gp.role not in ("exile", "hostage")
            ]
            gp2_candidates = [
                gp for gp in civ2.great_persons
                if gp.active and gp.name not in married_persons and gp.role not in ("exile", "hostage")
            ]
            if not gp1_candidates or not gp2_candidates:
                continue
            rng = random.Random(world.seed + world.turn + hash(pair))
            if rng.random() < 0.30:
                gp1, gp2 = gp1_candidates[0], gp2_candidates[0]
                rel = {
                    "type": "marriage",
                    "person_a": gp1.name,
                    "person_b": gp2.name,
                    "civ_a": civ1.name,
                    "civ_b": civ2.name,
                    "formed_turn": world.turn,
                }
                world.character_relationships.append(rel)
                new_marriages.append(rel)
    return new_marriages


# --- Hostage Exchanges ---

def capture_hostage(
    loser: "Civilization",
    winner: "Civilization",
    world: WorldState,
    contested_region: str | None = None,
) -> GreatPerson | None:
    """Take a hostage from the loser and move them to the winner's great persons list."""
    candidates = [gp for gp in loser.great_persons if gp.active and not gp.is_hostage]
    if not candidates:
        import random as _random
        rng = _random.Random(world.seed + world.turn + hash(loser.name))
        from chronicler.leaders import _pick_name
        name = _pick_name(loser, world, rng)
        hostage = GreatPerson(
            name=name,
            role="hostage",
            trait="cautious",
            civilization=winner.name,
            origin_civilization=loser.name,
            born_turn=world.turn,
            is_hostage=True,
            region=contested_region,
        )
        winner.great_persons.append(hostage)
        return hostage
    youngest = max(candidates, key=lambda gp: gp.born_turn)
    loser.great_persons.remove(youngest)
    youngest.civilization = winner.name
    youngest.captured_by = winner.name
    youngest.is_hostage = True
    youngest.hostage_turns = 0
    youngest.region = contested_region
    winner.great_persons.append(youngest)
    return youngest


def tick_hostages(world: WorldState) -> list[GreatPerson]:
    """Advance hostage turns, apply cultural conversion at 10, auto-release at 15."""
    released = []
    for civ in world.civilizations:
        for gp in list(civ.great_persons):
            if not gp.is_hostage:
                continue
            gp.hostage_turns += 1
            if gp.hostage_turns >= 10 and gp.cultural_identity != civ.name:
                gp.cultural_identity = civ.name
            if gp.hostage_turns >= 15:
                origin = next((c for c in world.civilizations if c.name == gp.origin_civilization), None)
                if origin:
                    release_hostage(gp, civ, origin, world)
                    released.append(gp)
    return released


def release_hostage(
    gp: GreatPerson,
    captor: "Civilization",
    origin: "Civilization",
    world: WorldState,
) -> None:
    """Release a hostage back to their origin civilization."""
    if gp in captor.great_persons:
        captor.great_persons.remove(gp)
    gp.is_hostage = False
    gp.civilization = origin.name
    gp.captured_by = None
    gp.region = origin.capital_region or (origin.regions[0] if origin.regions else None)
    origin.great_persons.append(gp)
    if origin.treasury >= 10:
        origin.treasury -= 10
