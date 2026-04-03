"""Character relationships: rivalry, mentorship, marriage alliance, hostage exchanges."""
from __future__ import annotations

import random
from collections import defaultdict

from chronicler.models import GreatPerson, WorldState
from chronicler.utils import stable_hash_int

# M40: Relationship type constants (match Rust RelationshipType repr(u8))
REL_MENTOR = 0
REL_RIVAL = 1
REL_MARRIAGE = 2
REL_EXILE_BOND = 3
REL_CORELIGIONIST = 4

REL_OP_UPSERT_DIRECTED = 0
REL_OP_UPSERT_SYMMETRIC = 1
REL_OP_REMOVE_DIRECTED = 2
REL_OP_REMOVE_SYMMETRIC = 3

_LEGACY_REL_SENTIMENT = 50
_HOSTAGE_ROLE_BY_FACTION = {
    "military": "general",
    "merchant": "merchant",
    "cultural": "scientist",
    "clergy": "prophet",
}


def _edge_op_type(rel_type: int, *, remove: bool) -> int:
    if rel_type == REL_MENTOR:
        return REL_OP_REMOVE_DIRECTED if remove else REL_OP_UPSERT_DIRECTED
    return REL_OP_REMOVE_SYMMETRIC if remove else REL_OP_UPSERT_SYMMETRIC


def _default_hostage_role(civ) -> str:
    """Pick a deterministic non-hostage role for synthetic or restored hostages."""
    influence = getattr(getattr(civ, "factions", None), "influence", {}) or {}
    if influence:
        dominant = max(influence, key=influence.get)
        dominant_name = getattr(dominant, "value", dominant)
        mapped = _HOSTAGE_ROLE_BY_FACTION.get(str(dominant_name).lower())
        if mapped is not None:
            return mapped
    return "general"


def _restore_hostage_role(gp: GreatPerson, fallback_civ) -> None:
    restored_role = gp.pre_hostage_role
    if restored_role in (None, "", "hostage"):
        restored_role = _default_hostage_role(fallback_civ)
    gp.role = restored_role
    gp.pre_hostage_role = None


def _clear_hostage_state(gp: GreatPerson, fallback_civ) -> None:
    gp.is_hostage = False
    gp.hostage_turns = 0
    gp.captured_by = None
    _restore_hostage_role(gp, fallback_civ)


def _sync_relationship_edges(bridge, current_edges: list[tuple], next_edges: list[tuple]) -> None:
    """Apply relationship diffs through ops when available.

    Falls back to the legacy full-graph replace shim for older test doubles.
    """
    apply_ops = getattr(bridge, "apply_relationship_ops", None)
    if not callable(apply_ops):
        bridge.replace_social_edges(next_edges)
        return

    current_by_key = {(a, b, rel): (a, b, rel, formed_turn) for a, b, rel, formed_turn in current_edges}
    next_by_key = {(a, b, rel): (a, b, rel, formed_turn) for a, b, rel, formed_turn in next_edges}

    ops: list[dict] = []
    for key in sorted(current_by_key.keys() - next_by_key.keys()):
        agent_a, agent_b, rel_type = key
        ops.append({
            "op_type": _edge_op_type(rel_type, remove=True),
            "agent_a": agent_a,
            "agent_b": agent_b,
            "bond_type": rel_type,
            "sentiment": _LEGACY_REL_SENTIMENT,
            "formed_turn": current_by_key[key][3],
        })
    for key in sorted(next_by_key.keys() - current_by_key.keys()):
        agent_a, agent_b, rel_type = key
        ops.append({
            "op_type": _edge_op_type(rel_type, remove=False),
            "agent_a": agent_a,
            "agent_b": agent_b,
            "bond_type": rel_type,
            "sentiment": _LEGACY_REL_SENTIMENT,
            "formed_turn": next_by_key[key][3],
        })

    if ops:
        apply_ops(ops)


def compute_belief_data(
    snap, active_ids: set[int], regions: list,
) -> tuple[dict[int, int], dict[str, dict[int, float]]]:
    """Extract per-agent beliefs and per-region belief fractions from agent snapshot.
    Returns (belief_by_agent, region_belief_fractions).
    """
    belief_by_agent: dict[int, int] = {}
    region_belief_fractions: dict[str, dict[int, float]] = {}
    if snap is None:
        return belief_by_agent, region_belief_fractions

    from collections import Counter, defaultdict

    belief_col = snap.column("belief").to_pylist()
    region_col = snap.column("region").to_pylist()
    agent_id_col = snap.column("id").to_pylist()

    for aid, bel in zip(agent_id_col, belief_col):
        if aid in active_ids:
            belief_by_agent[aid] = bel

    region_counts: dict[int, int] = Counter()
    region_belief_counts: dict[int, Counter] = defaultdict(Counter)
    for reg, bel in zip(region_col, belief_col):
        region_counts[reg] += 1
        region_belief_counts[reg][bel] += 1

    region_map = {i: r.name for i, r in enumerate(regions)}
    for reg_idx, total in region_counts.items():
        rname = region_map.get(reg_idx, "")
        if rname and total > 0:
            region_belief_fractions[rname] = {
                bel: cnt / total
                for bel, cnt in region_belief_counts[reg_idx].items()
            }

    return belief_by_agent, region_belief_fractions


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


# --- Mentorship ---

def check_mentorship_formation(world: WorldState, existing_edges: list[tuple]) -> list[tuple]:
    """Form mentorships between agent-source named characters with same role, co-located.
    Mentor = agent_a (senior by born_turn), apprentice = agent_b.
    born_turn is used as seniority proxy for skill gap.
    """
    new_edges = []
    mentored = set()
    for e in existing_edges:
        if e[2] == REL_MENTOR:
            mentored.add(e[0])
            mentored.add(e[1])

    candidates = []
    for civ in world.civilizations:
        for gp in civ.great_persons:
            if not gp.active or gp.agent_id is None or gp.role in ("exile", "hostage"):
                continue
            if gp.agent_id in mentored:
                continue
            candidates.append(gp)

    candidates.sort(key=lambda gp: (gp.born_turn, gp.agent_id or 0))
    paired = set()
    for i, senior in enumerate(candidates):
        if senior.agent_id in paired:
            continue
        for junior in candidates[i + 1:]:
            if junior.agent_id in paired:
                continue
            if senior.role != junior.role:
                continue
            if senior.region != junior.region or senior.region is None:
                continue
            edge = (senior.agent_id, junior.agent_id, REL_MENTOR, world.turn)
            new_edges.append(edge)
            paired.add(senior.agent_id)
            paired.add(junior.agent_id)
            break
    return new_edges


# --- Marriage Alliance ---

def check_marriage_formation(world: WorldState, existing_edges: list[tuple]) -> list[tuple]:
    """DEPRECATED (M57a): Marriage formation is now Rust-native via marriage_scan()
    in formation.rs. This Python-side helper is frozen — do not extend.
    Retained for fallback/test compatibility when Rust does not own formation.

    Original: Form marriage alliances between agent-source great persons of long-allied civs.
    agent_a < agent_b by convention. RNG seed uses civ-name pair for determinism stability.
    """
    from chronicler.models import Disposition
    new_edges = []
    married_agents = set()
    for e in existing_edges:
        if e[2] == REL_MARRIAGE:
            married_agents.add(e[0])
            married_agents.add(e[1])

    checked_pairs = set()
    for i, civ1 in enumerate(world.civilizations):
        for civ2 in world.civilizations[i + 1:]:
            pair = (civ1.name, civ2.name)
            if pair in checked_pairs or (civ2.name, civ1.name) in checked_pairs:
                continue
            checked_pairs.add(pair)
            rel12 = world.relationships.get(civ1.name, {}).get(civ2.name)
            if not rel12 or rel12.disposition != Disposition.ALLIED or rel12.allied_turns < 10:
                continue
            gp1_candidates = [
                gp for gp in civ1.great_persons
                if gp.active and gp.agent_id is not None
                and gp.agent_id not in married_agents
                and gp.role not in ("exile", "hostage")
            ]
            gp2_candidates = [
                gp for gp in civ2.great_persons
                if gp.active and gp.agent_id is not None
                and gp.agent_id not in married_agents
                and gp.role not in ("exile", "hostage")
            ]
            if not gp1_candidates or not gp2_candidates:
                continue
            rng = random.Random(
                stable_hash_int("marriage", world.seed, world.turn, pair)
            )
            if rng.random() < 0.30:
                gp1, gp2 = gp1_candidates[0], gp2_candidates[0]
                a, b = min(gp1.agent_id, gp2.agent_id), max(gp1.agent_id, gp2.agent_id)
                edge = (a, b, REL_MARRIAGE, world.turn)
                new_edges.append(edge)
                married_agents.add(a)
                married_agents.add(b)
    return new_edges


# --- Exile Bond ---

def check_exile_bond_formation(world: WorldState, existing_edges: list[tuple]) -> list[tuple]:
    """Form exile bonds between agent-source named characters who share origin_region
    and are co-located in a region that is NOT their origin.
    agent_a < agent_b by convention (symmetric).
    """
    new_edges = []
    existing_pairs = {(e[0], e[1]) for e in existing_edges if e[2] == REL_EXILE_BOND}

    displaced = []
    for civ in world.civilizations:
        for gp in civ.great_persons:
            if not gp.active or gp.agent_id is None:
                continue
            if gp.origin_region is None or gp.region is None:
                continue
            if gp.region == gp.origin_region:
                continue
            displaced.append(gp)

    groups: dict[tuple[str, str], list] = defaultdict(list)
    for gp in displaced:
        groups[(gp.origin_region, gp.region)].append(gp)

    for key, members in groups.items():
        if len(members) < 2:
            continue
        for i, gp1 in enumerate(members):
            for gp2 in members[i + 1:]:
                a, b = min(gp1.agent_id, gp2.agent_id), max(gp1.agent_id, gp2.agent_id)
                if (a, b) in existing_pairs:
                    continue
                edge = (a, b, REL_EXILE_BOND, world.turn)
                new_edges.append(edge)
                existing_pairs.add((a, b))
    return new_edges


# --- Co-religionist ---

CORELIGIONIST_MINORITY_THRESHOLD = 0.30


def check_coreligionist_formation(
    world: WorldState,
    existing_edges: list[tuple],
    belief_by_agent: dict[int, int],
    region_belief_fractions: dict[str, dict[int, float]],
) -> list[tuple]:
    """Form co-religionist bonds between agent-source named characters sharing
    a minority belief (<30%) in the same region.
    agent_a < agent_b by convention (symmetric).
    """
    new_edges = []
    existing_pairs = {(e[0], e[1]) for e in existing_edges if e[2] == REL_CORELIGIONIST}

    by_region_belief: dict[tuple[str, int], list] = defaultdict(list)
    for civ in world.civilizations:
        for gp in civ.great_persons:
            if not gp.active or gp.agent_id is None or gp.region is None:
                continue
            belief = belief_by_agent.get(gp.agent_id)
            if belief is None:
                continue
            by_region_belief[(gp.region, belief)].append(gp)

    for (region, belief), members in by_region_belief.items():
        if len(members) < 2:
            continue
        fractions = region_belief_fractions.get(region, {})
        fraction = fractions.get(belief, 0.0)
        if fraction >= CORELIGIONIST_MINORITY_THRESHOLD:
            continue
        for i, gp1 in enumerate(members):
            for gp2 in members[i + 1:]:
                a, b = min(gp1.agent_id, gp2.agent_id), max(gp1.agent_id, gp2.agent_id)
                if (a, b) in existing_pairs:
                    continue
                edge = (a, b, REL_CORELIGIONIST, world.turn)
                new_edges.append(edge)
                existing_pairs.add((a, b))
    return new_edges


# --- Coordinator ---

def form_and_sync_relationships(
    world: WorldState,
    bridge,
    active_agent_ids: set[int],
    belief_by_agent: dict[int, int],
    region_belief_fractions: dict[str, dict[int, float]],
) -> list[tuple]:
    """Phase 10 relationship pass: dissolve stale edges, form new ones, sync to Rust.
    Returns dissolved edges (for narration pipeline -- transient, not written to Rust).
    """
    current_edges = bridge.read_social_edges()
    surviving, dissolved_this_turn = dissolve_edges(
        current_edges, active_agent_ids, belief_by_agent=belief_by_agent,
    )
    new_rivals = check_rivalry_formation(world, surviving)
    new_mentors = check_mentorship_formation(world, surviving)
    new_marriages = check_marriage_formation(world, surviving)
    new_exile_bonds = check_exile_bond_formation(world, surviving)
    new_coreligionists = check_coreligionist_formation(
        world, surviving, belief_by_agent, region_belief_fractions,
    )
    all_edges = surviving + new_rivals + new_mentors + new_marriages + new_exile_bonds + new_coreligionists
    _sync_relationship_edges(bridge, current_edges, all_edges)
    return dissolved_this_turn


# --- Hostage Exchanges ---

def capture_hostage(
    loser: "Civilization",
    winner: "Civilization",
    world: WorldState,
    contested_region: str | None = None,
    bridge=None,
) -> GreatPerson | None:
    """Take a hostage from the loser and move them to the winner's great persons list."""
    candidates = [gp for gp in loser.great_persons if gp.active and not gp.is_hostage]
    if not candidates:
        import random as _random
        rng = _random.Random(
            stable_hash_int("hostage", world.seed, world.turn, loser.name)
        )
        from chronicler.leaders import _pick_name
        name = _pick_name(loser, world, rng)
        restored_role = _default_hostage_role(loser)
        hostage = GreatPerson(
            name=name,
            role="hostage",
            trait="cautious",
            civilization=winner.name,
            origin_civilization=loser.name,
            born_turn=world.turn,
            is_hostage=True,
            hostage_turns=0,
            captured_by=winner.name,
            pre_hostage_role=restored_role,
            region=contested_region,
        )
        winner.great_persons.append(hostage)
        return hostage
    youngest = max(candidates, key=lambda gp: gp.born_turn)
    loser.great_persons.remove(youngest)
    youngest.pre_hostage_role = youngest.pre_hostage_role or youngest.role
    youngest.role = "hostage"
    youngest.civilization = winner.name
    youngest.captured_by = winner.name
    youngest.is_hostage = True
    youngest.hostage_turns = 0
    youngest.region = contested_region
    # Sync Rust-side civ affinity in hybrid mode (mirrors apply_conquest_transitions)
    if bridge is not None and youngest.agent_id is not None:
        winner_civ_idx = next(
            (i for i, c in enumerate(world.civilizations) if c.name == winner.name),
            None,
        )
        if winner_civ_idx is not None:
            try:
                bridge._sim.set_agent_civ(youngest.agent_id, winner_civ_idx)
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "Failed to set GP civ during hostage capture (agent_id=%s, civ_idx=%s)",
                    youngest.agent_id,
                    winner_civ_idx,
                )
    winner.great_persons.append(youngest)
    return youngest


def tick_hostages(world: WorldState, acc=None) -> list[GreatPerson]:
    """Advance hostage turns, apply cultural conversion at 10, auto-release at 15."""
    released = []
    for civ in world.civilizations:
        for gp in list(civ.great_persons):
            if not gp.is_hostage:
                continue
            gp.hostage_turns += 1
            if gp.hostage_turns >= 10 and gp.cultural_identity != civ.name:
                gp.cultural_identity = civ.name
            # Free hostage if origin civ is extinct (no regions) — retire in place
            origin = next((c for c in world.civilizations if c.name == gp.origin_civilization), None)
            if origin is None or not origin.regions:
                _clear_hostage_state(gp, origin or civ)
                gp.civilization = civ.name
                released.append(gp)
                continue
            if gp.hostage_turns >= 15:
                release_hostage(gp, civ, origin, world, acc=acc)
                released.append(gp)
    return released


def release_hostage(
    gp: GreatPerson,
    captor: "Civilization",
    origin: "Civilization",
    world: WorldState,
    acc=None,
) -> None:
    """Release a hostage back to their origin civilization."""
    if gp in captor.great_persons:
        captor.great_persons.remove(gp)
    _clear_hostage_state(gp, origin)
    gp.civilization = origin.name
    gp.region = origin.capital_region or (origin.regions[0] if origin.regions else None)
    origin.great_persons.append(gp)
    if origin.treasury >= 10:
        if acc is not None:
            from chronicler.utils import civ_index
            origin_idx = civ_index(world, origin.name)
            acc.add(origin_idx, origin, "treasury", -10, "keep")
        else:
            origin.treasury -= 10
