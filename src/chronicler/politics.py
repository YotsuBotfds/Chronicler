# src/chronicler/politics.py
"""Political topology mechanics for the civilization chronicle generator."""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from chronicler.adjacency import graph_distance
from chronicler.models import (
    ActionType, Civilization, CivShock, Disposition, Event, Leader, NamedEvent,
    ProxyWar, ExileModifier, Relationship, VassalRelation, WorldState,
)
from chronicler.accumulator import normalize_shock
from chronicler.ecology import effective_capacity
from chronicler.tuning import (
    K_GOVERNING_COST,
    K_SECESSION_STABILITY_THRESHOLD, K_SECESSION_SURVEILLANCE_THRESHOLD,
    K_PROXY_WAR_SECESSION_BONUS, K_BALANCE_OF_POWER_DOMINANCE,
    K_BALANCE_OF_POWER_PERIOD, K_VASSAL_TRIBUTE_RATE,
    K_FEDERATION_ALLIED_TURNS, K_CONGRESS_PROBABILITY,
    K_CAPITAL_LOSS_STABILITY, K_FEDERATION_EXIT_STABILITY,
    K_FEDERATION_REMAINING_STABILITY,
    K_EXILE_DURATION, K_VASSAL_REBELLION_BASE_PROB,
    K_VASSAL_REBELLION_REDUCED_PROB,
    K_RESTORATION_BASE_PROB, K_RESTORATION_RECOGNITION_BONUS,
    K_TWILIGHT_DECLINE_TURNS, K_TWILIGHT_ABSORPTION_DECLINE,
    K_TWILIGHT_POP_DRAIN, K_TWILIGHT_CULTURE_DRAIN,
    K_FALLEN_EMPIRE_PEAK_REGIONS, K_FALLEN_EMPIRE_ASABIYA_BOOST,
    K_MOVE_CAPITAL_COST, K_PROXY_WAR_STABILITY_DRAIN,
    K_PROXY_WAR_ECONOMY_DRAIN, K_SECESSION_STABILITY_LOSS,
    get_override,
)
from chronicler.utils import (
    civ_index,
    clamp,
    stable_hash_int,
    STAT_FLOOR,
    sync_civ_population,
    drain_region_pop,
)
from chronicler.intelligence import get_perceived_stat
from chronicler.emergence import get_severity_multiplier
from chronicler.leaders import _pick_regnal_name, _compose_regnal_name

if TYPE_CHECKING:
    pass


SECESSION_GRACE_TURNS = 50


def war_key(a: str, b: str) -> str:
    """Canonical key for a war between two civs (alphabetically sorted)."""
    return ":".join(sorted([a, b]))


def apply_governing_costs(world: WorldState, acc=None) -> list[Event]:
    """Phase 2: Apply governing costs based on empire size and distance from capital."""
    events: list[Event] = []
    for civ in world.civilizations:
        if len(civ.regions) <= 2 or civ.capital_region is None:
            continue
        region_count = len(civ.regions)
        treasury_cost = (region_count - 2) * 2

        stability_cost = 0
        gov_cost_per_dist = int(get_override(world, K_GOVERNING_COST, 0.5))
        for region_name in civ.regions:
            if region_name == civ.capital_region:
                continue
            dist = graph_distance(world.regions, civ.capital_region, region_name)
            if dist < 0:
                dist = 1  # fallback if disconnected
            treasury_cost += dist * 2
            stability_cost += dist * gov_cost_per_dist

        mult = get_severity_multiplier(civ, world)
        if acc is not None:
            civ_idx = civ_index(world, civ.name)
            acc.add(civ_idx, civ, "treasury", -treasury_cost, "keep")
            acc.add(civ_idx, civ, "stability", -int(stability_cost * mult), "signal")
        else:
            civ.treasury -= treasury_cost
            civ.stability = clamp(civ.stability - int(stability_cost * mult), STAT_FLOOR["stability"], 100)
    return events


def resolve_move_capital(civ: Civilization, world: WorldState, acc=None) -> Event:
    """Resolve MOVE_CAPITAL action: relocate capital to most central region."""
    from chronicler.models import ActiveCondition
    move_cost = int(get_override(world, K_MOVE_CAPITAL_COST, 15))
    if acc is not None:
        civ_idx = civ_index(world, civ.name)
        acc.add(civ_idx, civ, "treasury", -move_cost, "keep")
    else:
        civ.treasury -= move_cost

    def avg_distance(candidate: str) -> float:
        distances = []
        for rn in civ.regions:
            if rn != candidate:
                d = graph_distance(world.regions, candidate, rn)
                distances.append(d if d >= 0 else 1)
        return sum(distances) / max(len(distances), 1)

    target = min(civ.regions, key=avg_distance)
    old_capital = civ.capital_region
    civ.capital_region = target

    condition = ActiveCondition(
        condition_type="capital_relocation",
        affected_civs=[civ.name],
        duration=5,
        severity=10,
    )
    world.active_conditions.append(condition)

    return Event(
        turn=world.turn,
        event_type="move_capital",
        actors=[civ.name],
        description=f"{civ.name} relocated capital from {old_capital} to {target}",
        importance=6,
    )


_SECESSION_PREFIXES = [
    "Free", "Eastern", "Western", "Northern", "Southern",
    "New", "Upper", "Lower", "Greater",
]

_TRAIT_POOL = [
    "aggressive", "cautious", "opportunistic", "zealous", "ambitious",
    "calculating", "visionary", "bold", "shrewd", "stubborn",
]


def check_secession(world: WorldState, acc=None) -> list[Event]:
    """Phase 10: Check for civil war / secession in unstable empires."""
    events: list[Event] = []
    new_civs: list[Civilization] = []

    for civ in list(world.civilizations):
        if civ.founded_turn > 0 and (world.turn - civ.founded_turn) < SECESSION_GRACE_TURNS:
            continue
        if civ.active_focus == "surveillance":
            secession_threshold = int(get_override(world, K_SECESSION_SURVEILLANCE_THRESHOLD, 5))  # M47c: 10→5 (proportional to base threshold change)
            world.events_timeline.append(Event(
                turn=world.turn, event_type="capability_surveillance",
                actors=[civ.name], description=f"{civ.name} surveillance lowers secession threshold",
                importance=1,
            ))
        else:
            secession_threshold = int(get_override(world, K_SECESSION_STABILITY_THRESHOLD, 10))  # M47c: 20→10 (hybrid stability ~20-30, old threshold fired constantly)
        if civ.stability >= secession_threshold or len(civ.regions) < 3:
            continue

        prob = (secession_threshold - civ.stability) / 100

        for pw in getattr(world, "proxy_wars", []):
            if pw.target_civ == civ.name:
                prob += get_override(world, K_PROXY_WAR_SECESSION_BONUS, 0.05)
                break

        # M38b: Religious faith mismatch raises secession probability
        from chronicler.religion import SCHISM_SECESSION_MODIFIER
        region_map = {r.name: r for r in world.regions}
        civ_faith = getattr(civ, "civ_majority_faith", 0xFF)
        for region_name in civ.regions:
            region_obj = region_map.get(region_name)
            if region_obj is not None and region_obj.majority_belief != civ_faith:
                prob += SCHISM_SECESSION_MODIFIER / 100
                break  # one modifier per civ per turn

        # M47: Secession likelihood multiplier
        from chronicler.tuning import get_multiplier, K_SECESSION_LIKELIHOOD
        prob *= get_multiplier(world, K_SECESSION_LIKELIHOOD)
        prob = min(prob, 1.0)

        rng = random.Random(
            stable_hash_int("secession", world.seed, world.turn, civ.name)
        )
        if rng.random() >= prob:
            continue

        # Secession fires
        region_map = {r.name: r for r in world.regions}

        def _secession_score(rn: str, _civ=civ) -> float:
            d = graph_distance(world.regions, _civ.capital_region or _civ.regions[0], rn)
            dist = d if d >= 0 else 0
            cap = effective_capacity(region_map[rn]) if rn in region_map else 0
            return dist * 0.7 + cap * 0.3

        sorted_regions = sorted(civ.regions, key=_secession_score, reverse=True)

        breakaway_count = math.ceil(len(civ.regions) / 3)
        breakaway_count = max(1, min(breakaway_count, len(civ.regions) - 1))
        breakaway_regions = sorted_regions[:breakaway_count]
        remaining_regions = [r for r in civ.regions if r not in breakaway_regions]

        ratio = len(breakaway_regions) / len(civ.regions)
        split_pop = sum(
            r.population for r in world.regions if r.name in breakaway_regions
        )
        split_mil = math.floor(civ.military * ratio)
        split_eco = math.floor(civ.economy * ratio)
        split_tre = math.floor(civ.treasury * ratio)

        existing_names = {c.name for c in world.civilizations} | {c.name for c in new_civs}
        prefix = _SECESSION_PREFIXES[rng.randint(0, len(_SECESSION_PREFIXES) - 1)]
        base_name = breakaway_regions[0] if rng.random() < 0.5 else civ.name
        breakaway_name = f"{prefix} {base_name}"
        attempts = 0
        while breakaway_name in existing_names and attempts < len(_SECESSION_PREFIXES):
            prefix = _SECESSION_PREFIXES[attempts]
            breakaway_name = f"{prefix} {base_name}"
            attempts += 1
        if breakaway_name in existing_names:
            breakaway_name = f"{prefix} {base_name} {world.turn}"

        parent_trait = civ.leader.trait
        available_traits = [t for t in _TRAIT_POOL if t != parent_trait]
        new_trait = rng.choice(available_traits) if available_traits else parent_trait

        new_values = list(civ.values)
        if new_values:
            _VALUE_POOL = [
                "freedom", "order", "tradition", "progress", "honor",
                "wealth", "knowledge", "faith", "unity", "independence",
            ]
            swap_idx = rng.randint(0, len(new_values) - 1)
            available_values = [v for v in _VALUE_POOL if v not in new_values]
            if available_values:
                new_values[swap_idx] = rng.choice(available_values)

        def _min_dist_to_parent(rn: str) -> int:
            return min(
                (graph_distance(world.regions, rn, pr) for pr in remaining_regions),
                default=0,
            )
        breakaway_capital = min(breakaway_regions, key=_min_dist_to_parent)

        # M51: Create breakaway civ with placeholder leader, then apply regnal naming
        placeholder_leader = Leader(
            name="Placeholder",
            trait=new_trait,
            reign_start=world.turn,
            succession_type="secession",
        )

        breakaway_civ = Civilization(
            name=breakaway_name,
            population=max(split_pop, 1),
            military=max(split_mil, 0),
            economy=max(split_eco, 0),
            culture=civ.culture,
            stability=40,
            treasury=split_tre,
            tech_era=civ.tech_era,
            leader=placeholder_leader,
            regions=breakaway_regions,
            capital_region=breakaway_capital,
            domains=list(civ.domains),
            values=new_values,
            asabiya=0.7,
            leader_name_pool=list(civ.leader_name_pool or []),
        )

        # M55b: Initialize breakaway region asabiya
        for rname in breakaway_regions:
            br = next((r for r in world.regions if r.name == rname), None)
            if br is not None:
                br.asabiya_state.asabiya = 0.7

        # Apply regnal naming to the breakaway leader now that breakaway_civ exists
        regnal_rng = random.Random(
            stable_hash_int("secession_regnal", world.seed, world.turn, breakaway_name)
        )
        title, throne_name, ordinal = _pick_regnal_name(breakaway_civ, world, regnal_rng)
        leader_name = _compose_regnal_name(title, throne_name, ordinal)
        breakaway_civ.leader.name = leader_name
        breakaway_civ.leader.throne_name = throne_name
        breakaway_civ.leader.regnal_ordinal = ordinal

        breakaway_civ.founded_turn = world.turn

        # M17d: Tradition inheritance through secession
        breakaway_civ.traditions = list(civ.traditions)

        civ_idx = civ_index(world, civ.name)
        new_civ_id = len(world.civilizations) + len(new_civs)
        mult = get_severity_multiplier(civ, world)
        secession_stab_loss = int(get_override(world, K_SECESSION_STABILITY_LOSS, 10))
        if world.agent_mode == "hybrid":
            world.pending_shocks.append(CivShock(civ_idx,
                military_shock=normalize_shock(split_mil, civ.military),
                economy_shock=normalize_shock(split_eco, civ.economy),
                stability_shock=normalize_shock(int(secession_stab_loss * mult), civ.stability)))
            civ.treasury -= split_tre  # treasury stays Python-side
            bridge = getattr(world, "_agent_bridge", None)
            if bridge is not None:
                events.extend(
                    bridge.apply_secession_transitions(
                        civ,
                        breakaway_civ,
                        breakaway_regions,
                        new_civ_id,
                        turn=world.turn,
                        world=world,
                        old_civ_id=civ_idx,
                    )
                )
        elif acc is not None:
            acc.add(civ_idx, civ, "military", -split_mil, "guard")
            acc.add(civ_idx, civ, "economy", -split_eco, "guard")
            acc.add(civ_idx, civ, "treasury", -split_tre, "keep")
            acc.add(civ_idx, civ, "stability", -int(secession_stab_loss * mult), "signal")
        else:
            civ.military = max(civ.military - split_mil, 0)
            civ.economy = max(civ.economy - split_eco, 0)
            civ.treasury -= split_tre
            civ.stability = clamp(civ.stability - int(secession_stab_loss * mult), STAT_FLOOR["stability"], 100)
        civ.regions = remaining_regions

        for rn in breakaway_regions:
            if rn in region_map:
                region_map[rn].controller = breakaway_name
                # M48: Transient memory signal — region seceded this turn
                region_map[rn]._seceded_this_turn = True

        sync_civ_population(civ, world)

        if civ.name not in world.relationships:
            world.relationships[civ.name] = {}
        if breakaway_name not in world.relationships:
            world.relationships[breakaway_name] = {}
        world.relationships[civ.name][breakaway_name] = Relationship(
            disposition=Disposition.HOSTILE,
        )
        world.relationships[breakaway_name][civ.name] = Relationship(
            disposition=Disposition.HOSTILE,
        )
        for other_civ in world.civilizations:
            if other_civ.name not in (civ.name, breakaway_name):
                if other_civ.name not in world.relationships:
                    world.relationships[other_civ.name] = {}
                world.relationships[breakaway_name][other_civ.name] = Relationship(
                    disposition=Disposition.NEUTRAL,
                )
                world.relationships[other_civ.name][breakaway_name] = Relationship(
                    disposition=Disposition.NEUTRAL,
                )

        new_civs.append(breakaway_civ)

        events.append(Event(
            turn=world.turn,
            event_type="secession",
            actors=[civ.name, breakaway_name],
            description=f"The Secession of {breakaway_name} from {civ.name}",
            importance=9,
        ))
        civ.event_counts["secession_occurred"] = civ.event_counts.get("secession_occurred", 0) + 1

    world.civilizations.extend(new_civs)
    return events


def check_capital_loss(world: WorldState, acc=None) -> list[Event]:
    """Phase 10: Check if any civ lost its capital and handle reassignment."""
    events: list[Event] = []
    for civ in world.civilizations:
        if civ.capital_region is None or civ.capital_region in civ.regions:
            continue
        if not civ.regions:
            continue

        # Capital lost
        civ_idx = civ_index(world, civ.name)
        mult = get_severity_multiplier(civ, world)
        cap_loss_stab = int(get_override(world, K_CAPITAL_LOSS_STABILITY, 20))
        if world.agent_mode == "hybrid":
            world.pending_shocks.append(CivShock(civ_idx,
                stability_shock=normalize_shock(int(cap_loss_stab * mult), civ.stability)))
        elif acc is not None:
            acc.add(civ_idx, civ, "stability", -int(cap_loss_stab * mult), "signal")
        else:
            civ.stability = clamp(civ.stability - int(cap_loss_stab * mult), STAT_FLOOR["stability"], 100)

        # Pick best remaining region (highest effective_capacity)
        from chronicler.ecology import effective_capacity
        region_map = {r.name: r for r in world.regions}
        best_region = max(
            civ.regions,
            key=lambda rn: (
                effective_capacity(region_map[rn])
                if rn in region_map else 0
            ),
        )
        old_capital = civ.capital_region
        civ.capital_region = best_region

        events.append(Event(
            turn=world.turn,
            event_type="capital_loss",
            actors=[civ.name],
            description=f"{civ.name} lost capital {old_capital}, relocated to {best_region}",
            importance=8,
        ))
        civ.event_counts["capital_lost"] = civ.event_counts.get("capital_lost", 0) + 1
    return events


_ABSORPTION_BIAS_TRAITS = {"ambitious", "aggressive", "zealous"}
_VASSAL_BIAS_TRAITS = {"cautious", "shrewd", "visionary", "calculating"}


def choose_vassalize_or_absorb(
    winner: Civilization, loser: Civilization, world: WorldState,
) -> bool:
    """Return True to vassalize, False to absorb."""
    if winner.stability <= 40:
        return False
    rng = random.Random(
        stable_hash_int("vassalize_or_absorb", world.seed, world.turn, winner.name)
    )
    trait = winner.leader.trait
    if trait in _ABSORPTION_BIAS_TRAITS:
        threshold = 0.3
    elif trait in _VASSAL_BIAS_TRAITS:
        threshold = 0.8
    else:
        threshold = 0.5
    return rng.random() < threshold


def resolve_vassalization(winner: Civilization, loser: Civilization, world: WorldState) -> list[Event]:
    """Apply full vassalization resolution steps."""
    events: list[Event] = []

    # Remove from active_wars and war_start_turns
    world.active_wars = [
        w for w in world.active_wars
        if not (set(w) == {winner.name, loser.name})
    ]
    key = war_key(winner.name, loser.name)
    world.war_start_turns.pop(key, None)

    # Create VassalRelation
    tribute_rate = get_override(world, K_VASSAL_TRIBUTE_RATE, 0.15)
    world.vassal_relations.append(VassalRelation(
        overlord=winner.name, vassal=loser.name, tribute_rate=tribute_rate,
    ))

    # Set dispositions
    if winner.name not in world.relationships:
        world.relationships[winner.name] = {}
    if loser.name not in world.relationships:
        world.relationships[loser.name] = {}
    world.relationships[winner.name][loser.name] = Relationship(disposition=Disposition.SUSPICIOUS)
    world.relationships[loser.name][winner.name] = Relationship(disposition=Disposition.HOSTILE)

    events.append(Event(
        turn=world.turn,
        event_type="vassalization",
        actors=[winner.name, loser.name],
        description=f"The Subjugation of {loser.name}",
        importance=7,
    ))
    return events


def collect_tribute(world: WorldState, acc=None) -> list[Event]:
    """Phase 2: Collect tribute from vassals to overlords."""
    events: list[Event] = []
    civ_map = {c.name: c for c in world.civilizations}
    for vr in world.vassal_relations:
        vassal = civ_map.get(vr.vassal)
        overlord = civ_map.get(vr.overlord)
        if vassal is None or overlord is None:
            continue
        perceived_econ = get_perceived_stat(overlord, vassal, "economy", world)
        # NOTE: None should be unreachable — vassal/overlord grants +0.5 accuracy.
        # If this fires, compute_accuracy has a bug.
        tribute = math.floor((perceived_econ if perceived_econ is not None else vassal.economy) * vr.tribute_rate)
        if acc is not None:
            vassal_idx = civ_index(world, vassal.name)
            overlord_idx = civ_index(world, overlord.name)
            acc.add(vassal_idx, vassal, "treasury", -tribute, "keep")
            acc.add(overlord_idx, overlord, "treasury", tribute, "keep")
        else:
            vassal.treasury -= tribute
            overlord.treasury += tribute
        vr.turns_active += 1
    return events


def check_vassal_rebellion(world: WorldState, acc=None) -> list[Event]:
    """Phase 10: Check if vassals rebel against weak overlords."""
    events: list[Event] = []
    civ_map = {c.name: c for c in world.civilizations}
    to_remove: list[VassalRelation] = []
    rebelled_overlords: set[str] = set()

    for vr in list(world.vassal_relations):
        overlord = civ_map.get(vr.overlord)
        vassal = civ_map.get(vr.vassal)
        if overlord is None or vassal is None:
            to_remove.append(vr)
            continue

        perceived_stab = get_perceived_stat(vassal, overlord, "stability", world)
        perceived_treas = get_perceived_stat(vassal, overlord, "treasury", world, max_value=500)
        # NOTE: None should be unreachable — vassal/overlord grants +0.5 accuracy.
        # If this fires, compute_accuracy has a bug.
        eff_stab = perceived_stab if perceived_stab is not None else overlord.stability
        eff_treas = perceived_treas if perceived_treas is not None else overlord.treasury
        if eff_stab >= 25 and eff_treas >= 10:
            continue

        rng = random.Random(
            stable_hash_int("vassal_rebellion", world.seed, world.turn, vr.vassal)
        )
        prob = get_override(world, K_VASSAL_REBELLION_REDUCED_PROB, 0.05) if vr.overlord in rebelled_overlords else get_override(world, K_VASSAL_REBELLION_BASE_PROB, 0.15)

        if vr.overlord in rebelled_overlords:
            rel = world.relationships.get(vr.vassal, {}).get(vr.overlord)
            if rel is None or rel.disposition not in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                continue

        if rng.random() >= prob:
            continue

        to_remove.append(vr)
        rebelled_overlords.add(vr.overlord)
        vassal_idx = civ_index(world, vassal.name)
        if world.agent_mode == "hybrid":
            world.pending_shocks.append(CivShock(vassal_idx,
                stability_shock=min(1.0, 10 / max(vassal.stability, 1))))
        elif acc is not None:
            acc.add(vassal_idx, vassal, "stability", 10, "guard-shock")
        else:
            vassal.stability = clamp(vassal.stability + 10, STAT_FLOOR["stability"], 100)
        from chronicler.simulation import _apply_asabiya_to_regions
        _apply_asabiya_to_regions(world, vassal.name, 0.2)

        if vr.vassal in world.relationships and vr.overlord in world.relationships[vr.vassal]:
            world.relationships[vr.vassal][vr.overlord].disposition = Disposition.HOSTILE

        events.append(Event(
            turn=world.turn,
            event_type="vassal_rebellion",
            actors=[vr.vassal, vr.overlord],
            description=f"The {vr.vassal} Rebellion against {vr.overlord}",
            importance=8,
        ))

    for vr in to_remove:
        if vr in world.vassal_relations:
            world.vassal_relations.remove(vr)

    return events


# --- Federation mechanics ---

_FEDERATION_ADJECTIVES = [
    "Northern", "Southern", "Eastern", "Western", "Iron",
    "Golden", "Silver", "Maritime", "Sacred", "Grand",
]
_FEDERATION_NOUNS = [
    "Accord", "Pact", "League", "Alliance", "Compact", "Coalition", "Confederation",
]


def _civ_in_federation(civ_name: str, world: WorldState) -> "Federation | None":
    """Return the federation a civ belongs to, or None."""
    from chronicler.models import Federation
    for fed in world.federations:
        if civ_name in fed.members:
            return fed
    return None


def _is_vassal(civ_name: str, world: WorldState) -> bool:
    """Check if a civ is a vassal."""
    return any(vr.vassal == civ_name for vr in world.vassal_relations)


def update_allied_turns(world: WorldState) -> None:
    """Phase 10: Update allied_turns counters on all relationships."""
    for civ_name, rels in world.relationships.items():
        for other_name, rel in rels.items():
            if rel.disposition == Disposition.ALLIED:
                rel.allied_turns += 1
            elif rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS, Disposition.NEUTRAL):
                rel.allied_turns = 0


def check_federation_formation(world: WorldState) -> list[Event]:
    """Phase 10: Check if any allied pairs can form or join federations."""
    from chronicler.models import Federation
    events: list[Event] = []
    checked_pairs: set[tuple[str, str]] = set()

    for civ_a in world.civilizations:
        if _is_vassal(civ_a.name, world):
            continue
        rels_a = world.relationships.get(civ_a.name, {})
        for civ_b_name, rel_ab in rels_a.items():
            fed_turns_req = int(get_override(world, K_FEDERATION_ALLIED_TURNS, 10))
            if rel_ab.allied_turns < fed_turns_req:
                continue
            pair = tuple(sorted([civ_a.name, civ_b_name]))
            if pair in checked_pairs:
                continue
            checked_pairs.add(pair)

            rel_ba = world.relationships.get(civ_b_name, {}).get(civ_a.name)
            if rel_ba is None or rel_ba.allied_turns < fed_turns_req:
                continue
            if _is_vassal(civ_b_name, world):
                continue

            fed_a = _civ_in_federation(civ_a.name, world)
            fed_b = _civ_in_federation(civ_b_name, world)

            if fed_a and fed_b:
                continue
            elif fed_a and not fed_b:
                fed_a.members.append(civ_b_name)
            elif fed_b and not fed_a:
                fed_b.members.append(civ_a.name)
            else:
                rng = random.Random(world.seed + world.turn)
                adj = rng.choice(_FEDERATION_ADJECTIVES)
                noun = rng.choice(_FEDERATION_NOUNS)
                fed_name = f"The {adj} {noun}"
                new_fed = Federation(
                    name=fed_name,
                    members=[civ_a.name, civ_b_name],
                    founded_turn=world.turn,
                )
                world.federations.append(new_fed)
                events.append(Event(
                    turn=world.turn,
                    event_type="federation_formed",
                    actors=[civ_a.name, civ_b_name],
                    description=f"Formation of {fed_name}",
                    importance=7,
                ))

    return events


def check_federation_dissolution(world: WorldState, acc=None) -> list[Event]:
    """Phase 10: Check if any federation members want to exit."""
    events: list[Event] = []
    feds_to_remove = []

    for fed in world.federations:
        exiting: list[str] = []
        for member in fed.members:
            rels = world.relationships.get(member, {})
            for other_member in fed.members:
                if other_member == member:
                    continue
                rel = rels.get(other_member)
                if rel and rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS, Disposition.NEUTRAL):
                    exiting.append(member)
                    break

        fed_exit_stab = int(get_override(world, K_FEDERATION_EXIT_STABILITY, 15))
        fed_remain_stab = int(get_override(world, K_FEDERATION_REMAINING_STABILITY, 5))
        for member in exiting:
            fed.members.remove(member)
            civ = next((c for c in world.civilizations if c.name == member), None)
            if civ:
                civ_idx = civ_index(world, civ.name)
                mult = get_severity_multiplier(civ, world)
                if world.agent_mode == "hybrid":
                    world.pending_shocks.append(CivShock(civ_idx,
                        stability_shock=normalize_shock(int(fed_exit_stab * mult), civ.stability)))
                elif acc is not None:
                    acc.add(civ_idx, civ, "stability", -int(fed_exit_stab * mult), "signal")
                else:
                    civ.stability = clamp(civ.stability - int(fed_exit_stab * mult), STAT_FLOOR["stability"], 100)
            for remaining in fed.members:
                rc = next((c for c in world.civilizations if c.name == remaining), None)
                if rc:
                    rc_idx = civ_index(world, rc.name)
                    rc_mult = get_severity_multiplier(rc, world)
                    if world.agent_mode == "hybrid":
                        world.pending_shocks.append(CivShock(rc_idx,
                            stability_shock=normalize_shock(int(fed_remain_stab * rc_mult), rc.stability)))
                    elif acc is not None:
                        acc.add(rc_idx, rc, "stability", -int(fed_remain_stab * rc_mult), "signal")
                    else:
                        rc.stability = clamp(rc.stability - int(fed_remain_stab * rc_mult), STAT_FLOOR["stability"], 100)

        if len(fed.members) <= 1:
            feds_to_remove.append(fed)
            events.append(Event(
                turn=world.turn,
                event_type="federation_collapsed",
                actors=fed.members,
                description=f"Collapse of {fed.name}",
                importance=7,
            ))

    for fed in feds_to_remove:
        world.federations.remove(fed)

    return events


def trigger_federation_defense(attacker: str, defender: str, world: WorldState) -> list[Event]:
    """Called during war resolution: if defender is in a federation, allies join."""
    events: list[Event] = []
    fed = _civ_in_federation(defender, world)
    if fed is None:
        return events

    for member in fed.members:
        if member == defender or member == attacker:
            continue
        war_pair = (attacker, member)
        if war_pair not in world.active_wars and (member, attacker) not in world.active_wars:
            world.active_wars.append(war_pair)
            world.war_start_turns[war_key(attacker, member)] = world.turn
            events.append(Event(
                turn=world.turn,
                event_type="federation_defense",
                actors=[member, defender, attacker],
                description=f"{member} joins war against {attacker} in defense of {defender}",
                importance=6,
            ))

    return events


# --- Proxy war mechanics ---

def apply_proxy_wars(world: WorldState, acc=None) -> list[Event]:
    """Phase 2: Apply ongoing proxy war costs and effects."""
    events: list[Event] = []
    civ_map = {c.name: c for c in world.civilizations}
    to_remove = []

    for pw in world.proxy_wars:
        sponsor = civ_map.get(pw.sponsor)
        target = civ_map.get(pw.target_civ)
        if sponsor is None or target is None:
            to_remove.append(pw)
            continue

        mult = get_severity_multiplier(target, world)
        pw_stab = int(get_override(world, K_PROXY_WAR_STABILITY_DRAIN, 3))
        pw_econ = int(get_override(world, K_PROXY_WAR_ECONOMY_DRAIN, 2))
        if acc is not None:
            sponsor_idx = civ_index(world, sponsor.name)
            target_idx = civ_index(world, target.name)
            acc.add(sponsor_idx, sponsor, "treasury", -pw.treasury_per_turn, "keep")
            acc.add(target_idx, target, "stability", -int(pw_stab * mult), "signal")
            acc.add(target_idx, target, "economy", -int(pw_econ * mult), "signal")
        else:
            sponsor.treasury -= pw.treasury_per_turn
            target.stability = clamp(target.stability - int(pw_stab * mult), STAT_FLOOR["stability"], 100)
            target.economy = clamp(target.economy - int(pw_econ * mult), STAT_FLOOR["economy"], 100)
        pw.turns_active += 1

        if sponsor.treasury < 0:
            to_remove.append(pw)
            continue

        if pw.target_region not in target.regions:
            to_remove.append(pw)
            continue

        rel = world.relationships.get(pw.sponsor, {}).get(pw.target_civ)
        if rel and rel.disposition in (Disposition.FRIENDLY, Disposition.ALLIED):
            to_remove.append(pw)
            continue

        if not sponsor.regions:
            to_remove.append(pw)

    for pw in to_remove:
        if pw in world.proxy_wars:
            world.proxy_wars.remove(pw)

    return events


def check_proxy_detection(world: WorldState, acc=None) -> list[Event]:
    """Phase 10: Check if proxy wars are detected by target civs."""
    events: list[Event] = []
    civ_map = {c.name: c for c in world.civilizations}

    for pw in world.proxy_wars:
        if pw.detected:
            continue
        target = civ_map.get(pw.target_civ)
        if target is None:
            continue

        rng = random.Random(
            stable_hash_int(
                "proxy_detection",
                world.seed,
                world.turn,
                pw.sponsor,
                pw.target_civ,
            )
        )
        detection_prob = target.culture / 100
        if rng.random() < detection_prob:
            pw.detected = True
            target_idx = civ_index(world, target.name)
            if world.agent_mode == "hybrid":
                world.pending_shocks.append(CivShock(target_idx,
                    stability_shock=max(-1.0, -5 / max(target.stability, 1))))
            elif acc is not None:
                acc.add(target_idx, target, "stability", -5, "guard-shock")
            else:
                target.stability = clamp(target.stability - 5, STAT_FLOOR["stability"], 100)

            rels = world.relationships.get(pw.target_civ, {})
            if pw.sponsor in rels:
                rels[pw.sponsor].disposition = Disposition.HOSTILE

            events.append(Event(
                turn=world.turn,
                event_type="proxy_detected",
                actors=[pw.sponsor, pw.target_civ],
                description=f"{pw.sponsor} exposed funding separatists in {pw.target_region}",
                importance=7,
            ))

    return events


# --- Diplomatic congress ---

def check_congress(world: WorldState, acc=None) -> list[Event]:
    """Phase 7: Check for diplomatic congress when 3+ civs at war."""
    events: list[Event] = []

    participants = set()
    for a, b in world.active_wars:
        participants.add(a)
        participants.add(b)
    if len(participants) < 3:
        return events

    rng = random.Random(world.seed + world.turn)
    congress_prob = get_override(world, K_CONGRESS_PROBABILITY, 0.05)
    if rng.random() >= congress_prob:
        return events

    civ_map = {c.name: c for c in world.civilizations}

    # M24: Congress organizer = highest actual culture (world fact, not perceived)
    organizer = max(
        (civ_map[n] for n in participants if n in civ_map),
        key=lambda c: c.culture, default=None,
    )
    powers: dict[str, float] = {}
    for name in participants:
        civ = civ_map.get(name)
        if civ is None:
            continue
        matching_starts = [
            world.war_start_turns[key] for key in world.war_start_turns
            if name in key.split(":")
        ]
        longest_war = world.turn - min(matching_starts) if matching_starts else 1
        fed = _civ_in_federation(name, world)
        fed_allies = len(fed.members) - 1 if fed else 0
        # M24: organizer perceives each participant's military and economy
        if organizer is not None:
            p_mil = get_perceived_stat(organizer, civ, "military", world)
            p_econ = get_perceived_stat(organizer, civ, "economy", world)
        else:
            p_mil, p_econ = None, None
        # Self-perception is always accurate (compute_accuracy returns 1.0 for self)
        # None filtered: if organizer doesn't know a civ, use actual as fallback
        eff_mil = p_mil if p_mil is not None else civ.military
        eff_econ = p_econ if p_econ is not None else civ.economy
        powers[name] = (eff_mil + eff_econ + fed_allies * 10) / max(longest_war, 1)

    roll = rng.random()
    if roll < 0.40:
        # Full peace
        world.active_wars = [
            w for w in world.active_wars
            if w[0] not in participants or w[1] not in participants
        ]
        for key in list(world.war_start_turns):
            parts = key.split(":")
            if parts[0] in participants or parts[1] in participants:
                del world.war_start_turns[key]

        for a in participants:
            for b in participants:
                if a != b and a in world.relationships and b in world.relationships.get(a, {}):
                    world.relationships[a][b].disposition = Disposition.NEUTRAL

        highest_culture_civ = max(
            (civ_map[n] for n in participants if n in civ_map),
            key=lambda c: c.culture, default=None,
        )
        location = highest_culture_civ.capital_region if highest_culture_civ else "unknown"
        events.append(Event(
            turn=world.turn, event_type="congress_peace",
            actors=list(participants),
            description=f"The Congress of {location}",
            importance=9,
        ))
    elif roll < 0.75:
        # Partial ceasefire
        sorted_powers = sorted(powers.items(), key=lambda x: x[1], reverse=True)
        if len(sorted_powers) >= 2:
            a, b = sorted_powers[0][0], sorted_powers[1][0]
            world.active_wars = [
                w for w in world.active_wars
                if not (set(w) == {a, b})
            ]
            world.war_start_turns.pop(war_key(a, b), None)
            if a in world.relationships and b in world.relationships.get(a, {}):
                world.relationships[a][b].disposition = Disposition.NEUTRAL
            if b in world.relationships and a in world.relationships.get(b, {}):
                world.relationships[b][a].disposition = Disposition.NEUTRAL
        events.append(Event(
            turn=world.turn, event_type="congress_ceasefire",
            actors=list(participants),
            description="Partial ceasefire achieved at diplomatic congress",
            importance=7,
        ))
    else:
        # Collapse
        for name in participants:
            civ = civ_map.get(name)
            if civ:
                civ_idx = civ_index(world, civ.name)
                mult = get_severity_multiplier(civ, world)
                if world.agent_mode == "hybrid":
                    world.pending_shocks.append(CivShock(civ_idx,
                        stability_shock=normalize_shock(int(5 * mult), civ.stability)))
                elif acc is not None:
                    acc.add(civ_idx, civ, "stability", -int(5 * mult), "signal")
                else:
                    civ.stability = clamp(civ.stability - int(5 * mult), STAT_FLOOR["stability"], 100)
        events.append(Event(
            turn=world.turn, event_type="congress_collapse",
            actors=list(participants),
            description="The Failed Congress",
            importance=6,
        ))

    return events


# --- Governments in exile ---

def create_exile(eliminated: Civilization, conqueror: Civilization, world: WorldState) -> ExileModifier:
    """Create an exile modifier when a civ is eliminated."""
    exile = ExileModifier(
        original_civ_name=eliminated.name,
        absorber_civ=conqueror.name,
        conquered_regions=list(eliminated.regions),
        turns_remaining=int(get_override(world, K_EXILE_DURATION, 20)),
    )
    world.exile_modifiers.append(exile)
    return exile


def apply_exile_effects(world: WorldState, acc=None) -> list[Event]:
    """Phase 2: Drain absorber stability for each active exile modifier."""
    events: list[Event] = []
    civ_map = {c.name: c for c in world.civilizations}
    to_remove = []

    for exile in world.exile_modifiers:
        absorber = civ_map.get(exile.absorber_civ)
        if absorber:
            mult = get_severity_multiplier(absorber, world)
            if acc is not None:
                absorber_idx = civ_index(world, absorber.name)
                acc.add(absorber_idx, absorber, "stability", -int(5 * mult), "signal")
            else:
                absorber.stability = clamp(absorber.stability - int(5 * mult), STAT_FLOOR["stability"], 100)
        exile.turns_remaining -= 1
        if exile.turns_remaining <= 0:
            to_remove.append(exile)

    for exile in to_remove:
        world.exile_modifiers.remove(exile)

    return events


def check_restoration(world: WorldState) -> list[Event]:
    """Phase 10: Check if any exiled civs can be restored."""
    events: list[Event] = []
    civ_map = {c.name: c for c in world.civilizations}
    region_map = {r.name: r for r in world.regions}
    to_remove = []

    for exile in world.exile_modifiers:
        absorber = civ_map.get(exile.absorber_civ)
        if absorber is None or absorber.stability >= 20 or exile.turns_remaining <= 0:
            continue

        available = [r for r in exile.conquered_regions
                     if r in region_map and region_map[r].controller == exile.absorber_civ]
        if not available:
            continue

        prob = get_override(world, K_RESTORATION_BASE_PROB, 0.05) + get_override(world, K_RESTORATION_RECOGNITION_BONUS, 0.03) * len(exile.recognized_by)
        rng = random.Random(
            stable_hash_int(
                "restoration",
                world.seed,
                world.turn,
                exile.original_civ_name,
            )
        )
        if rng.random() >= prob:
            continue

        # Restoration fires
        from chronicler.ecology import effective_capacity as _eff_cap
        target_region = max(available,
                           key=lambda rn: _eff_cap(region_map[rn]))

        from chronicler.models import TechEra
        era_order = list(TechEra)
        absorber_idx = era_order.index(absorber.tech_era)
        restored_era = era_order[max(0, absorber_idx - 1)]

        rng_trait = random.Random(world.seed + world.turn)
        new_trait = rng_trait.choice(_TRAIT_POOL)

        restored_population = 30
        if world.agent_mode == "hybrid":
            restored_population = region_map[target_region].population
        else:
            region_map[target_region].population = 30
        restored_leader = Leader(name="Placeholder", trait=new_trait, reign_start=world.turn)
        restored_civ = next(
            (
                civ for civ in world.civilizations
                if civ.name == exile.original_civ_name and len(civ.regions) == 0
            ),
            None,
        )
        if restored_civ is None:
            restored_civ = Civilization(
                name=exile.original_civ_name,
                population=restored_population, military=20, economy=20,
                culture=30, stability=50, treasury=0,
                tech_era=restored_era, asabiya=0.8,
                leader=restored_leader,
                regions=[target_region], capital_region=target_region,
                founded_turn=world.turn,
            )
            world.civilizations.append(restored_civ)
        else:
            restored_civ.population = restored_population
            restored_civ.military = 20
            restored_civ.economy = 20
            restored_civ.culture = 30
            restored_civ.stability = 50
            restored_civ.treasury = 0
            restored_civ.tech_era = restored_era
            restored_civ.leader = restored_leader
            restored_civ.regions = [target_region]
            restored_civ.capital_region = target_region
            restored_civ.founded_turn = world.turn
            restored_civ.decline_turns = 0
            restored_civ.stats_sum_history = []
        # M55b: Initialize restored region asabiya
        for rname in restored_civ.regions:
            rr = next((r for r in world.regions if r.name == rname), None)
            if rr is not None:
                rr.asabiya_state.asabiya = 0.8
        # Apply regnal naming now that restored_civ exists
        regnal_rng = random.Random(
            stable_hash_int(
                "restoration_regnal",
                world.seed,
                world.turn,
                exile.original_civ_name,
            )
        )
        title, throne_name, ordinal = _pick_regnal_name(restored_civ, world, regnal_rng)
        leader_name = _compose_regnal_name(title, throne_name, ordinal)
        restored_civ.leader.name = leader_name
        restored_civ.leader.throne_name = throne_name
        restored_civ.leader.regnal_ordinal = ordinal

        restored_civ_id = len(world.civilizations) - 1
        restored_civ_id = next(
            i for i, existing_civ in enumerate(world.civilizations)
            if existing_civ is restored_civ
        )
        absorber_civ_id = next(
            i for i, existing_civ in enumerate(world.civilizations)
            if existing_civ is absorber
        )

        if target_region in absorber.regions:
            absorber.regions.remove(target_region)
        if len(absorber.regions) == 0:
            from chronicler.simulation import reset_war_frequency_on_extinction
            reset_war_frequency_on_extinction(absorber)
        region_map[target_region].controller = exile.original_civ_name
        if world.agent_mode == "hybrid":
            bridge = getattr(world, "_agent_bridge", None)
            if bridge is not None:
                bridge.apply_restoration_transitions(
                    absorber,
                    restored_civ,
                    [target_region],
                    absorber_civ_id=absorber_civ_id,
                    restored_civ_id=restored_civ_id,
                    world=world,
                )
        sync_civ_population(absorber, world)
        sync_civ_population(restored_civ, world)

        world.relationships[exile.original_civ_name] = {}
        for c in world.civilizations:
            if c.name == exile.original_civ_name:
                continue
            if c.name == exile.absorber_civ:
                disp = Disposition.HOSTILE
            elif c.name in exile.recognized_by:
                disp = Disposition.FRIENDLY
            else:
                disp = Disposition.NEUTRAL
            world.relationships[exile.original_civ_name][c.name] = Relationship(disposition=disp)
            if c.name not in world.relationships:
                world.relationships[c.name] = {}
            world.relationships[c.name][exile.original_civ_name] = Relationship(disposition=disp)

        to_remove.append(exile)
        events.append(Event(
            turn=world.turn, event_type="restoration",
            actors=[exile.original_civ_name, exile.absorber_civ],
            description=f"Restoration of {exile.original_civ_name}",
            importance=9,
        ))

    for exile in to_remove:
        world.exile_modifiers.remove(exile)
    return events


# --- M14d: Systemic Dynamics ---

def apply_balance_of_power(world: WorldState) -> list[Event]:
    """Phase 2: Apply coalition pressure against dominant civs."""
    events: list[Event] = []
    living = [c for c in world.civilizations if c.regions]
    if len(living) < 2:
        return events

    scores = {c.name: c.military + c.economy + len(c.regions) * 5 for c in living}
    total = sum(scores.values())
    if total == 0:
        return events

    dominant = max(scores, key=scores.get)
    bop_threshold = get_override(world, K_BALANCE_OF_POWER_DOMINANCE, 0.40)
    if scores[dominant] / total <= bop_threshold:
        world.balance_of_power_turns = 0
        return events

    world.balance_of_power_turns += 1

    bop_period = int(get_override(world, K_BALANCE_OF_POWER_PERIOD, 5))
    if world.balance_of_power_turns % bop_period == 0:
        DISPOSITION_UPGRADE = {
            Disposition.HOSTILE: Disposition.SUSPICIOUS,
            Disposition.SUSPICIOUS: Disposition.NEUTRAL,
            Disposition.NEUTRAL: Disposition.FRIENDLY,
            Disposition.FRIENDLY: Disposition.ALLIED,
            Disposition.ALLIED: Disposition.ALLIED,
        }
        non_dominant = [c.name for c in living if c.name != dominant]
        for i, name_a in enumerate(non_dominant):
            for name_b in non_dominant[i+1:]:
                for a, b in [(name_a, name_b), (name_b, name_a)]:
                    rel = world.relationships.get(a, {}).get(b)
                    if rel:
                        rel.disposition = DISPOSITION_UPGRADE[rel.disposition]

    return events


def update_peak_regions(world: WorldState) -> None:
    """Phase 2: Update peak_region_count for all civs."""
    for civ in world.civilizations:
        if len(civ.regions) == 0:
            continue
        civ.peak_region_count = max(civ.peak_region_count, len(civ.regions))


def _is_fallen_empire(civ: Civilization, world: "WorldState | None" = None) -> bool:
    """Check if civ qualifies as a fallen empire."""
    peak_threshold = int(get_override(world, K_FALLEN_EMPIRE_PEAK_REGIONS, 5)) if world else 5
    return civ.peak_region_count >= peak_threshold and len(civ.regions) == 1


def apply_fallen_empire(world: WorldState, acc=None) -> list[Event]:
    """Phase 2: Apply fallen empire modifiers (asabiya boost)."""
    events: list[Event] = []
    for civ in world.civilizations:
        if not _is_fallen_empire(civ, world):
            continue
        asabiya_boost = get_override(world, K_FALLEN_EMPIRE_ASABIYA_BOOST, 0.05)
        from chronicler.simulation import _apply_asabiya_to_regions
        _apply_asabiya_to_regions(world, civ.name, asabiya_boost)
    return events


def update_decline_tracking(world: WorldState) -> None:
    """End of phase 10: Update decline tracking for all civs."""
    for civ in world.civilizations:
        if len(civ.regions) == 0:
            continue
        current_sum = civ.economy + civ.military + civ.culture
        civ.stats_sum_history.append(current_sum)
        if len(civ.stats_sum_history) > 20:
            civ.stats_sum_history = civ.stats_sum_history[-20:]
        if len(civ.stats_sum_history) == 20:
            if current_sum < civ.stats_sum_history[0]:
                civ.decline_turns += 1
            else:
                civ.decline_turns = 0


def _in_twilight(civ: Civilization, world: "WorldState | None" = None) -> bool:
    twilight_turns = int(get_override(world, K_TWILIGHT_DECLINE_TURNS, 20)) if world else 20
    return civ.decline_turns >= twilight_turns and len(civ.regions) == 1


def apply_twilight(world: WorldState, acc=None) -> list[Event]:
    """Phase 2: Apply twilight stat drains."""
    events: list[Event] = []
    for civ in world.civilizations:
        if not _in_twilight(civ, world):
            continue
        twilight_pop = int(get_override(world, K_TWILIGHT_POP_DRAIN, 3))
        civ_regions = [r for r in world.regions if r.controller == civ.name]
        if civ_regions:
            if acc is not None:
                civ_idx = civ_index(world, civ.name)
                acc.add(civ_idx, civ, "population", -twilight_pop, "guard")
            else:
                target_r = max(civ_regions, key=lambda r: r.population)
                drain_region_pop(target_r, twilight_pop)
                sync_civ_population(civ, world)
        mult = get_severity_multiplier(civ, world)
        twilight_culture = int(get_override(world, K_TWILIGHT_CULTURE_DRAIN, 2))
        if acc is not None:
            civ_idx = civ_index(world, civ.name)
            acc.add(civ_idx, civ, "culture", -int(twilight_culture * mult), "signal")
        else:
            civ.culture = clamp(civ.culture - int(twilight_culture * mult), STAT_FLOOR["culture"], 100)
        twilight_threshold = int(get_override(world, K_TWILIGHT_DECLINE_TURNS, 20))
        if civ.decline_turns == twilight_threshold:
            events.append(Event(
                turn=world.turn, event_type="twilight",
                actors=[civ.name],
                description=f"The Twilight of {civ.name}",
                importance=7,
            ))
    return events


def check_twilight_absorption(world: WorldState) -> list[Event]:
    """Phase 10: Peacefully absorb civs in terminal twilight."""
    events: list[Event] = []

    for civ in list(world.civilizations):
        # M22: Absorb structurally unviable civs
        from chronicler.factions import total_effective_capacity
        if total_effective_capacity(civ, world) < 10 and (world.turn - civ.founded_turn) > 30:
            region_map_u = {r.name: r for r in world.regions}
            best_absorber_u = None
            best_culture_u = -1
            for rn in civ.regions:
                civ_r = region_map_u.get(rn)
                if civ_r is None:
                    continue
                for adj_name in getattr(civ_r, 'adjacencies', []):
                    adj_region = region_map_u.get(adj_name)
                    if adj_region and adj_region.controller and adj_region.controller != civ.name:
                        absorber = next((c for c in world.civilizations if c.name == adj_region.controller), None)
                        if absorber and absorber.culture > best_culture_u:
                            best_culture_u = absorber.culture
                            best_absorber_u = absorber
            if best_absorber_u is not None:
                absorbed_regions = list(civ.regions)
                civ_id = next(
                    i for i, existing_civ in enumerate(world.civilizations)
                    if existing_civ is civ
                )
                absorber_id = next(
                    i for i, existing_civ in enumerate(world.civilizations)
                    if existing_civ is best_absorber_u
                )
                for rn in absorbed_regions:
                    best_absorber_u.regions.append(rn)
                    if rn in region_map_u:
                        region_map_u[rn].controller = best_absorber_u.name
                civ.regions = []
                from chronicler.simulation import reset_war_frequency_on_extinction
                reset_war_frequency_on_extinction(civ)
                # M52: Artifact lifecycle intent for twilight absorption
                from chronicler.artifacts import emit_conquest_lifecycle_intent
                for rn in absorbed_regions:
                    emit_conquest_lifecycle_intent(
                        world, losing_civ=civ.name, gaining_civ=best_absorber_u.name,
                        region=rn,
                        is_capital=(rn == civ.capital_region),
                        is_destructive=False,
                        action="twilight_absorption",
                    )
                if world.agent_mode == "hybrid":
                    bridge = getattr(world, "_agent_bridge", None)
                    if bridge is not None:
                        bridge.apply_absorption_transitions(
                            civ,
                            best_absorber_u,
                            absorbed_regions,
                            losing_civ_id=civ_id,
                            absorber_civ_id=absorber_id,
                            world=world,
                        )
                sync_civ_population(best_absorber_u, world)
                sync_civ_population(civ, world)
                world.exile_modifiers.append(ExileModifier(
                    original_civ_name=civ.name,
                    absorber_civ=best_absorber_u.name,
                    conquered_regions=absorbed_regions,
                    turns_remaining=10,
                ))
                events.append(Event(
                    turn=world.turn, event_type="twilight_absorption",
                    actors=[civ.name, best_absorber_u.name],
                    description=f"The Quiet End of {civ.name}",
                    importance=6,
                ))
                continue

        if civ.decline_turns < int(get_override(world, K_TWILIGHT_ABSORPTION_DECLINE, 40)) or len(civ.regions) != 1:
            continue

        region_map = {r.name: r for r in world.regions}
        civ_region = region_map.get(civ.regions[0])
        if civ_region is None:
            continue

        best_absorber = None
        best_culture = -1
        for adj_name in getattr(civ_region, 'adjacencies', []):
            adj_region = region_map.get(adj_name)
            if adj_region and adj_region.controller and adj_region.controller != civ.name:
                absorber = next((c for c in world.civilizations if c.name == adj_region.controller), None)
                if absorber and absorber.culture > best_culture:
                    best_culture = absorber.culture
                    best_absorber = absorber

        if best_absorber is None:
            continue

        absorbed_regions_tw = list(civ.regions)
        civ_id = next(
            i for i, existing_civ in enumerate(world.civilizations)
            if existing_civ is civ
        )
        absorber_id = next(
            i for i, existing_civ in enumerate(world.civilizations)
            if existing_civ is best_absorber
        )
        for rn in civ.regions:
            best_absorber.regions.append(rn)
            if rn in region_map:
                region_map[rn].controller = best_absorber.name
        civ.regions = []
        from chronicler.simulation import reset_war_frequency_on_extinction
        reset_war_frequency_on_extinction(civ)
        # M52: Artifact lifecycle intent for twilight absorption
        from chronicler.artifacts import emit_conquest_lifecycle_intent
        for rn in absorbed_regions_tw:
            emit_conquest_lifecycle_intent(
                world, losing_civ=civ.name, gaining_civ=best_absorber.name,
                region=rn,
                is_capital=(rn == civ.capital_region),
                is_destructive=False,
                action="twilight_absorption",
            )
        if world.agent_mode == "hybrid":
            bridge = getattr(world, "_agent_bridge", None)
            if bridge is not None:
                bridge.apply_absorption_transitions(
                    civ,
                    best_absorber,
                    absorbed_regions_tw,
                    losing_civ_id=civ_id,
                    absorber_civ_id=absorber_id,
                    world=world,
                )
        sync_civ_population(best_absorber, world)
        sync_civ_population(civ, world)

        world.exile_modifiers.append(ExileModifier(
            original_civ_name=civ.name,
            absorber_civ=best_absorber.name,
            conquered_regions=[civ_region.name],
            turns_remaining=10,
        ))

        events.append(Event(
            turn=world.turn, event_type="twilight_absorption",
            actors=[civ.name, best_absorber.name],
            description=f"The Quiet End of {civ.name}",
            importance=6,
        ))

    return events


def apply_long_peace(world: WorldState, acc=None) -> list[Event]:
    """Phase 2: Apply long peace effects when no wars for 30+ turns."""
    events: list[Event] = []

    if world.active_wars:
        world.peace_turns = 0
        return events

    world.peace_turns += 1
    if world.peace_turns < 30:
        return events

    living = [c for c in world.civilizations if c.regions]

    # Military restlessness
    for civ in living:
        if civ.military > 60:
            mult = get_severity_multiplier(civ, world)
            if acc is not None:
                civ_idx = civ_index(world, civ.name)
                acc.add(civ_idx, civ, "stability", -int(2 * mult), "signal")
            else:
                civ.stability = clamp(civ.stability - int(2 * mult), STAT_FLOOR["stability"], 100)

    # Economic inequality
    if len(living) >= 2:
        richest = max(living, key=lambda c: c.economy)
        poorest = min(living, key=lambda c: c.economy)
        if acc is not None:
            richest_idx = civ_index(world, richest.name)
            poorest_idx = civ_index(world, poorest.name)
            acc.add(richest_idx, richest, "economy", 1, "guard")
            acc.add(poorest_idx, poorest, "economy", -1, "guard")
        else:
            richest.economy = clamp(richest.economy + 1, STAT_FLOOR["economy"], 100)
            poorest.economy = clamp(poorest.economy - 1, STAT_FLOOR["economy"], 100)

    # ALLIED disposition decay every 10 peace turns
    if world.peace_turns % 10 == 0:
        DOWNGRADE = {Disposition.ALLIED: Disposition.FRIENDLY}
        for civ_name, rels in world.relationships.items():
            for other_name, rel in rels.items():
                if rel.disposition in DOWNGRADE:
                    rel.disposition = DOWNGRADE[rel.disposition]

    return events


# --- FUND_INSTABILITY resolution ---

def resolve_fund_instability(civ: Civilization, world: WorldState, acc=None) -> Event:
    """Resolve FUND_INSTABILITY action: start covert destabilization."""
    civ_map = {c.name: c for c in world.civilizations}

    # Find most hostile viable target (deterministic ranking).
    # Rank by disposition hostility, then by region count, then name.
    rels = world.relationships.get(civ.name, {})
    candidates: list[tuple[int, int, str, Civilization]] = []
    for other_name, rel in rels.items():
        if rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
            other = civ_map.get(other_name)
            if other and other.regions:
                hostility_rank = 2 if rel.disposition == Disposition.HOSTILE else 1
                candidates.append((hostility_rank, len(other.regions), other.name, other))

    if not candidates:
        return Event(turn=world.turn, event_type="fund_instability_failed",
                     actors=[civ.name], description=f"{civ.name} found no viable target", importance=3)

    candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
    target = candidates[0][3]

    # Pick most distant region from target's capital
    target_region = target.regions[0]
    if target.capital_region and len(target.regions) > 1:
        from chronicler.adjacency import graph_distance
        target_region = max(target.regions,
                           key=lambda rn: graph_distance(world.regions, target.capital_region, rn))

    if acc is not None:
        civ_idx = civ_index(world, civ.name)
        acc.add(civ_idx, civ, "treasury", -8, "keep")
    else:
        civ.treasury -= 8
    world.proxy_wars.append(ProxyWar(
        sponsor=civ.name, target_civ=target.name, target_region=target_region,
    ))

    return Event(turn=world.turn, event_type="fund_instability",
                 actors=[civ.name], description="Covert operation initiated", importance=3)


# ────────────────────────────────────────────────────────────────────
# M54c: Dedicated FFI Builders and Ordered Apply Helpers
#
# These are the dedicated politics pack/unpack/apply surfaces for the
# Rust politics migration.  They do NOT reuse build_region_batch() or
# set_region_state().  The actual Arrow conversion will happen in Task 3
# when the FFI surface is wired; these produce dict-of-list payloads
# that can be trivially converted to RecordBatches.
# ────────────────────────────────────────────────────────────────────

# --- Disposition u8 encoding ---
_DISPOSITION_TO_U8 = {
    Disposition.HOSTILE: 0,
    Disposition.SUSPICIOUS: 1,
    Disposition.NEUTRAL: 2,
    Disposition.FRIENDLY: 3,
    Disposition.ALLIED: 4,
}
_U8_TO_DISPOSITION = {v: k for k, v in _DISPOSITION_TO_U8.items()}

# --- Op-type enums for reconstruct / apply layer ---
# CivOp types
CIV_OP_CREATE_BREAKAWAY = 0
CIV_OP_RESTORE = 1
CIV_OP_ABSORB = 2
CIV_OP_REASSIGN_CAPITAL = 3
CIV_OP_STRIP_TO_FIRST_REGION = 4

# RegionOp types
REGION_OP_SET_CONTROLLER = 0
REGION_OP_NULLIFY_CONTROLLER = 1
REGION_OP_SET_SECEDED_TRANSIENT = 2

# RelationshipOp types
REL_OP_INIT_PAIR = 0
REL_OP_SET_DISPOSITION = 1
REL_OP_RESET_ALLIED_TURNS = 2
REL_OP_INCREMENT_ALLIED_TURNS = 3

# FederationOp types
FED_OP_CREATE = 0
FED_OP_APPEND_MEMBER = 1
FED_OP_REMOVE_MEMBER = 2
FED_OP_DISSOLVE = 3

# VassalOp types
VASSAL_OP_REMOVE = 0

# ExileOp types
EXILE_OP_APPEND = 0
EXILE_OP_REMOVE = 1

# ProxyWarOp types
PROXY_OP_SET_DETECTED = 0

# CivEffectOp routing tags
ROUTING_KEEP = 0
ROUTING_SIGNAL = 1
ROUTING_GUARD_SHOCK = 2
ROUTING_DIRECT_ONLY = 3
ROUTING_HYBRID_SHOCK = 4

# BookkeepingDelta types
BK_APPEND_STATS_HISTORY = 0
BK_INCREMENT_DECLINE = 1
BK_RESET_DECLINE = 2
BK_INCREMENT_EVENT_COUNT = 3

# BridgeTransitionOp types
BRIDGE_SECESSION = 0
BRIDGE_RESTORATION = 1
BRIDGE_ABSORPTION = 2

# CivRef encoding
REF_EXISTING = 0
REF_NEW = 1

# FederationRef encoding
FED_REF_EXISTING = 0
FED_REF_NEW = 1

# Sentinel for no controller / no civ
CIV_NONE: int = 0xFFFF


def build_politics_civ_input_batch(world: WorldState) -> dict:
    """Pack per-civ state needed by the Rust politics pass.

    Returns a dict-of-lists that maps 1:1 to an Arrow RecordBatch schema.
    Each list has len == len(world.civilizations).  Dead civs (regions=[])
    are included with their scalar state so Rust can index by position.
    """
    from chronicler.factions import get_dominant_faction, total_effective_capacity

    region_name_to_idx = {r.name: i for i, r in enumerate(world.regions)}
    dominant_faction_map = {"military": 0, "merchant": 1, "cultural": 2, "clergy": 3}

    n = len(world.civilizations)
    # Pre-size all columns
    civ_idx_col = list(range(n))
    civ_name_col = []
    stability_col = []
    military_col = []
    economy_col = []
    culture_col = []
    treasury_col = []
    asabiya_col = []
    population_col = []
    decline_turns_col = []
    founded_turn_col = []
    civ_stress_col = []
    civ_majority_faith_col = []
    active_focus_col = []
    total_eff_cap_col = []
    capital_region_col = []
    num_regions_col = []
    dominant_faction_col = []
    secession_occurred_col = []
    capital_lost_col = []
    # Stats sum history: pack as a flat list + offsets
    stats_sum_history_offsets = [0]
    stats_sum_history_values: list[int] = []
    # Region membership: pack as a flat list + offsets
    region_offsets = [0]
    region_values: list[int] = []

    for civ in world.civilizations:
        civ_name_col.append(civ.name)
        stability_col.append(civ.stability)
        military_col.append(civ.military)
        economy_col.append(civ.economy)
        culture_col.append(civ.culture)
        treasury_col.append(civ.treasury)
        asabiya_col.append(float(civ.asabiya))
        population_col.append(civ.population)
        decline_turns_col.append(civ.decline_turns)
        founded_turn_col.append(civ.founded_turn)
        civ_stress_col.append(getattr(civ, "civ_stress", 0))
        civ_majority_faith_col.append(getattr(civ, "civ_majority_faith", 0xFF))
        active_focus_col.append(civ.active_focus or "")
        total_eff_cap_col.append(total_effective_capacity(civ, world))
        cap_idx = region_name_to_idx.get(civ.capital_region, CIV_NONE) if civ.capital_region else CIV_NONE
        capital_region_col.append(cap_idx)
        num_regions_col.append(len(civ.regions))
        dominant = get_dominant_faction(civ.factions)
        dominant_faction_col.append(dominant_faction_map.get(dominant.value, 0))
        secession_occurred_col.append(civ.event_counts.get("secession_occurred", 0))
        capital_lost_col.append(civ.event_counts.get("capital_lost", 0))

        # Stats sum history
        for v in civ.stats_sum_history:
            stats_sum_history_values.append(v)
        stats_sum_history_offsets.append(len(stats_sum_history_values))

        # Region indices
        for rn in civ.regions:
            idx = region_name_to_idx.get(rn, CIV_NONE)
            if idx != CIV_NONE:
                region_values.append(idx)
        region_offsets.append(len(region_values))

    return {
        "civ_idx": civ_idx_col,
        "civ_name": civ_name_col,
        "stability": stability_col,
        "military": military_col,
        "economy": economy_col,
        "culture": culture_col,
        "treasury": treasury_col,
        "asabiya": asabiya_col,
        "population": population_col,
        "decline_turns": decline_turns_col,
        "founded_turn": founded_turn_col,
        "civ_stress": civ_stress_col,
        "civ_majority_faith": civ_majority_faith_col,
        "active_focus": active_focus_col,
        "total_effective_capacity": total_eff_cap_col,
        "capital_region": capital_region_col,
        "num_regions": num_regions_col,
        "dominant_faction": dominant_faction_col,
        "secession_occurred_count": secession_occurred_col,
        "capital_lost_count": capital_lost_col,
        "stats_sum_history_offsets": stats_sum_history_offsets,
        "stats_sum_history_values": stats_sum_history_values,
        "region_offsets": region_offsets,
        "region_values": region_values,
    }


def build_politics_region_input_batch(world: WorldState) -> dict:
    """Pack per-region state needed by the Rust politics pass.

    Returns a dict-of-lists that maps 1:1 to an Arrow RecordBatch schema.
    """
    civ_name_to_id = {c.name: i for i, c in enumerate(world.civilizations)}
    region_name_to_idx = {r.name: i for i, r in enumerate(world.regions)}

    n = len(world.regions)
    region_idx_col = list(range(n))
    controller_col = []
    carrying_capacity_col = []
    population_col = []
    majority_belief_col = []
    # Adjacencies: flat list + offsets
    adj_offsets = [0]
    adj_values: list[int] = []

    for r in world.regions:
        ctrl = civ_name_to_id.get(r.controller, CIV_NONE) if r.controller else CIV_NONE
        controller_col.append(ctrl)
        carrying_capacity_col.append(r.carrying_capacity)
        population_col.append(r.population)
        majority_belief_col.append(getattr(r, "majority_belief", 0xFF))
        for adj_name in r.adjacencies:
            idx = region_name_to_idx.get(adj_name)
            if idx is not None:
                adj_values.append(idx)
        adj_offsets.append(len(adj_values))

    return {
        "region_idx": region_idx_col,
        "controller": controller_col,
        "carrying_capacity": carrying_capacity_col,
        "population": population_col,
        "majority_belief": majority_belief_col,
        "adjacency_offsets": adj_offsets,
        "adjacency_values": adj_values,
    }


def build_politics_relationship_batch(world: WorldState) -> dict:
    """Pack pairwise relationship state for the Rust politics pass.

    Returns a dict-of-lists with one row per ordered (civ_a, civ_b) pair.
    """
    civ_name_to_id = {c.name: i for i, c in enumerate(world.civilizations)}
    civ_a_col: list[int] = []
    civ_b_col: list[int] = []
    disposition_col: list[int] = []
    allied_turns_col: list[int] = []

    for civ_name, rels in sorted(world.relationships.items()):
        a_id = civ_name_to_id.get(civ_name, CIV_NONE)
        for other_name, rel in sorted(rels.items()):
            b_id = civ_name_to_id.get(other_name, CIV_NONE)
            civ_a_col.append(a_id)
            civ_b_col.append(b_id)
            disposition_col.append(_DISPOSITION_TO_U8.get(rel.disposition, 2))
            allied_turns_col.append(rel.allied_turns)

    return {
        "civ_a": civ_a_col,
        "civ_b": civ_b_col,
        "disposition": disposition_col,
        "allied_turns": allied_turns_col,
    }


def build_politics_vassal_batch(world: WorldState) -> dict:
    """Pack vassal relations for the Rust politics pass."""
    civ_name_to_id = {c.name: i for i, c in enumerate(world.civilizations)}
    overlord_col: list[int] = []
    vassal_col: list[int] = []

    for vr in world.vassal_relations:
        overlord_col.append(civ_name_to_id.get(vr.overlord, CIV_NONE))
        vassal_col.append(civ_name_to_id.get(vr.vassal, CIV_NONE))

    return {
        "overlord": overlord_col,
        "vassal": vassal_col,
    }


def build_politics_federation_batch(world: WorldState) -> dict:
    """Pack federation state for the Rust politics pass."""
    civ_name_to_id = {c.name: i for i, c in enumerate(world.civilizations)}
    fed_idx_col: list[int] = []
    name_col: list[str] = []
    founded_turn_col: list[int] = []
    # Members: flat + offsets
    member_offsets: list[int] = [0]
    member_values: list[int] = []

    for i, fed in enumerate(world.federations):
        fed_idx_col.append(i)
        name_col.append(fed.name)
        founded_turn_col.append(fed.founded_turn)
        for m in fed.members:
            mid = civ_name_to_id.get(m, CIV_NONE)
            member_values.append(mid)
        member_offsets.append(len(member_values))

    return {
        "federation_idx": fed_idx_col,
        "name": name_col,
        "founded_turn": founded_turn_col,
        "member_offsets": member_offsets,
        "member_values": member_values,
    }


def build_politics_war_batch(world: WorldState) -> dict:
    """Pack active wars for the Rust politics pass."""
    civ_name_to_id = {c.name: i for i, c in enumerate(world.civilizations)}
    civ_a_col: list[int] = []
    civ_b_col: list[int] = []

    for a, b in world.active_wars:
        civ_a_col.append(civ_name_to_id.get(a, CIV_NONE))
        civ_b_col.append(civ_name_to_id.get(b, CIV_NONE))

    return {
        "civ_a": civ_a_col,
        "civ_b": civ_b_col,
    }


def build_politics_embargo_batch(world: WorldState) -> dict:
    """Pack embargoes for the Rust politics pass."""
    civ_name_to_id = {c.name: i for i, c in enumerate(world.civilizations)}
    civ_a_col: list[int] = []
    civ_b_col: list[int] = []

    for a, b in world.embargoes:
        civ_a_col.append(civ_name_to_id.get(a, CIV_NONE))
        civ_b_col.append(civ_name_to_id.get(b, CIV_NONE))

    return {
        "civ_a": civ_a_col,
        "civ_b": civ_b_col,
    }


def build_politics_proxy_war_batch(world: WorldState) -> dict:
    """Pack proxy wars for the Rust politics pass."""
    civ_name_to_id = {c.name: i for i, c in enumerate(world.civilizations)}
    region_name_to_idx = {r.name: i for i, r in enumerate(world.regions)}

    sponsor_col: list[int] = []
    target_civ_col: list[int] = []
    target_region_col: list[int] = []
    detected_col: list[bool] = []

    for pw in world.proxy_wars:
        sponsor_col.append(civ_name_to_id.get(pw.sponsor, CIV_NONE))
        target_civ_col.append(civ_name_to_id.get(pw.target_civ, CIV_NONE))
        target_region_col.append(region_name_to_idx.get(pw.target_region, CIV_NONE))
        detected_col.append(pw.detected)

    return {
        "sponsor": sponsor_col,
        "target_civ": target_civ_col,
        "target_region": target_region_col,
        "detected": detected_col,
    }


def build_politics_exile_batch(world: WorldState) -> dict:
    """Pack exile modifiers for the Rust politics pass."""
    civ_name_to_id = {c.name: i for i, c in enumerate(world.civilizations)}
    region_name_to_idx = {r.name: i for i, r in enumerate(world.regions)}

    original_civ_col: list[int] = []
    absorber_civ_col: list[int] = []
    turns_remaining_col: list[int] = []
    # Conquered regions: flat + offsets
    region_offsets: list[int] = [0]
    region_values: list[int] = []
    # Recognized by: flat + offsets
    recognized_offsets: list[int] = [0]
    recognized_values: list[int] = []

    for exile in world.exile_modifiers:
        # For exiled civs, use name match (they may be dead with regions=[])
        orig_id = civ_name_to_id.get(exile.original_civ_name, CIV_NONE)
        original_civ_col.append(orig_id)
        absorber_civ_col.append(civ_name_to_id.get(exile.absorber_civ, CIV_NONE))
        turns_remaining_col.append(exile.turns_remaining)
        for rn in exile.conquered_regions:
            idx = region_name_to_idx.get(rn, CIV_NONE)
            region_values.append(idx)
        region_offsets.append(len(region_values))
        for rn in exile.recognized_by:
            rid = civ_name_to_id.get(rn, CIV_NONE)
            recognized_values.append(rid)
        recognized_offsets.append(len(recognized_values))

    return {
        "original_civ": original_civ_col,
        "absorber_civ": absorber_civ_col,
        "turns_remaining": turns_remaining_col,
        "region_offsets": region_offsets,
        "region_values": region_values,
        "recognized_offsets": recognized_offsets,
        "recognized_values": recognized_values,
    }


def build_politics_context(world: WorldState, hybrid_mode: bool) -> dict:
    """Pack run-level scalar context for the Rust politics pass."""
    return {
        "seed": world.seed,
        "turn": world.turn,
        "hybrid_mode": hybrid_mode,
    }


def reconstruct_politics_ops(
    civ_ops_batch: dict,
    region_ops_batch: dict,
    relationship_ops_batch: dict,
    federation_ops_batch: dict,
    vassal_ops_batch: dict,
    exile_ops_batch: dict,
    proxy_war_ops_batch: dict,
    civ_effect_batch: dict,
    bookkeeping_batch: dict,
    artifact_intent_batch: dict,
    bridge_transition_batch: dict,
    event_trigger_batch: dict,
) -> list[tuple]:
    """Unpack Rust op batches into a sorted list of (step, seq, family, payload) tuples.

    Each batch must have ``step`` and ``seq`` columns.  The return is sorted
    by (step, seq) so the apply layer can iterate in order.

    The tuple format is fixed:
        (step: int, seq: int, family: str, payload: dict)

    where ``family`` is one of:
        'civ_op', 'region_op', 'relationship_op', 'federation_op',
        'vassal_op', 'exile_op', 'proxy_war_op', 'civ_effect',
        'bookkeeping', 'artifact_intent', 'bridge_transition', 'event_trigger'
    """
    ops: list[tuple] = []

    def _extract_region_indices(row: dict) -> list[int]:
        if "region_indices" in row:
            return [ri for ri in (row["region_indices"] or []) if ri != CIV_NONE]
        if "conquered_regions" in row:
            return [ri for ri in (row["conquered_regions"] or []) if ri != CIV_NONE]
        if "regions" in row:
            return [ri for ri in (row["regions"] or []) if ri != CIV_NONE]
        count = int(row.get("region_count", 0))
        if count <= 0:
            return []
        region_indices: list[int] = []
        for idx in range(min(count, 4)):
            region_idx = row.get(f"region_{idx}", CIV_NONE)
            if region_idx != CIV_NONE:
                region_indices.append(region_idx)
        return region_indices

    def _extract(batch: dict, family: str):
        if not batch or "step" not in batch:
            return
        n = len(batch["step"])
        for i in range(n):
            row = {k: v[i] for k, v in batch.items()}
            if (
                ("region_count" in row or "region_indices" in row
                 or "conquered_regions" in row or "regions" in row)
                and "region_indices" not in row
            ):
                row["region_indices"] = _extract_region_indices(row)
            ops.append((row["step"], row["seq"], family, row))

    _extract(civ_ops_batch, "civ_op")
    _extract(region_ops_batch, "region_op")
    _extract(relationship_ops_batch, "relationship_op")
    _extract(federation_ops_batch, "federation_op")
    _extract(vassal_ops_batch, "vassal_op")
    _extract(exile_ops_batch, "exile_op")
    _extract(proxy_war_ops_batch, "proxy_war_op")
    _extract(civ_effect_batch, "civ_effect")
    _extract(bookkeeping_batch, "bookkeeping")
    _extract(artifact_intent_batch, "artifact_intent")
    _extract(bridge_transition_batch, "bridge_transition")
    _extract(event_trigger_batch, "event_trigger")

    ops.sort(key=lambda t: (t[0], t[1]))
    return ops


def apply_politics_ops(
    world: WorldState,
    ops: list[tuple],
    *,
    new_civ_map: dict | None = None,
    new_fed_map: dict | None = None,
) -> list[Event]:
    """Apply an ordered list of politics ops onto world state.

    ``ops`` is the output of ``reconstruct_politics_ops()``: a list of
    (step, seq, family, payload) tuples, already sorted by (step, seq).

    ``new_civ_map`` tracks CivRef.New(local_id) -> real civ index.
    ``new_fed_map`` tracks FederationRef.New(local_id) -> real federation index.
    Existing federation refs are resolved through a stable map as well so
    later ops still hit the right federation after an earlier dissolve shifts
    ``world.federations``.

    Returns the list of events produced by the apply pass.
    """
    if new_civ_map is None:
        new_civ_map = {}
    if new_fed_map is None:
        new_fed_map = {}
    existing_fed_map = {idx: idx for idx in range(len(world.federations))}

    events: list[Event] = []
    pending_hybrid_shock: tuple[int, CivShock] | None = None

    def _flush_pending_hybrid_shock() -> None:
        nonlocal pending_hybrid_shock
        if pending_hybrid_shock is None:
            return
        world.pending_shocks.append(pending_hybrid_shock[1])
        pending_hybrid_shock = None

    for step, seq, family, payload in ops:
        if (
            family == "civ_effect"
            and world.agent_mode == "hybrid"
            and payload.get("routing", ROUTING_DIRECT_ONLY) == ROUTING_HYBRID_SHOCK
        ):
            civ_idx = _resolve_civ_ref(
                world,
                payload.get("civ_ref_kind", 0),
                payload.get("civ_ref_id", 0),
                new_civ_map,
            )
            field = payload.get("field", "")
            delta = payload.get("delta", 0.0)
            shock_field_map = {
                "stability": "stability_shock",
                "military": "military_shock",
                "economy": "economy_shock",
                "culture": "culture_shock",
            }
            shock_attr = shock_field_map.get(field)
            if civ_idx < len(world.civilizations) and shock_attr is not None:
                if pending_hybrid_shock is None or pending_hybrid_shock[0] != civ_idx:
                    _flush_pending_hybrid_shock()
                    pending_hybrid_shock = (civ_idx, CivShock(civ_id=civ_idx))
                setattr(pending_hybrid_shock[1], shock_attr, delta)
                continue

        _flush_pending_hybrid_shock()
        if family == "civ_op":
            _apply_civ_op(world, payload, new_civ_map, events)
        elif family == "region_op":
            _apply_region_op(world, payload, new_civ_map)
        elif family == "relationship_op":
            _apply_relationship_op(world, payload, new_civ_map)
        elif family == "federation_op":
            _apply_federation_op(
                world,
                payload,
                new_civ_map,
                existing_fed_map,
                new_fed_map,
            )
        elif family == "vassal_op":
            _apply_vassal_op(world, payload, new_civ_map)
        elif family == "exile_op":
            _apply_exile_op(world, payload, new_civ_map)
        elif family == "proxy_war_op":
            _apply_proxy_war_op(world, payload, new_civ_map)
        elif family == "civ_effect":
            _apply_civ_effect(world, payload, new_civ_map)
        elif family == "bookkeeping":
            _apply_bookkeeping(world, payload, new_civ_map)
        elif family == "artifact_intent":
            _apply_artifact_intent(world, payload, new_civ_map)
        elif family == "bridge_transition":
            _apply_bridge_transition(world, payload, new_civ_map, events)
        elif family == "event_trigger":
            _apply_event_trigger(world, payload, new_civ_map, events)

    _flush_pending_hybrid_shock()
    return events


def _resolve_civ_ref(world: WorldState, ref_kind: int, ref_id: int,
                     new_civ_map: dict) -> int:
    """Resolve a CivRef to a concrete civ index."""
    if ref_kind == REF_EXISTING:
        return ref_id
    return new_civ_map.get(ref_id, ref_id)


def _normalize_politics_asabiya(value: float | None, default: float) -> float:
    """Canonicalize known Rust politics constants after float32 round-trip."""
    if value is None:
        return default
    value = float(value)
    for canonical in (0.0, 0.7, 0.8):
        if math.isclose(value, canonical, rel_tol=0.0, abs_tol=1e-6):
            return canonical
    return value


def _resolve_fed_ref(
    ref_kind: int,
    ref_id: int,
    existing_fed_map: dict,
    new_fed_map: dict,
) -> int:
    """Resolve a FederationRef to a concrete federation index."""
    if ref_kind == FED_REF_EXISTING:
        return existing_fed_map.get(ref_id, ref_id)
    return new_fed_map.get(ref_id, ref_id)


def _build_breakaway_civ(
    world: WorldState,
    source_civ: Civilization,
    breakaway_regions: list[str],
    remaining_regions: list[str],
    payload: dict,
) -> Civilization:
    rng = random.Random(
        stable_hash_int("secession", world.seed, world.turn, source_civ.name)
    )
    # Consume the probability roll so later draws match the preserved oracle.
    rng.random()

    existing_names = {c.name for c in world.civilizations}
    prefix = _SECESSION_PREFIXES[rng.randint(0, len(_SECESSION_PREFIXES) - 1)]
    base_name = breakaway_regions[0] if rng.random() < 0.5 else source_civ.name
    breakaway_name = f"{prefix} {base_name}"
    attempts = 0
    while breakaway_name in existing_names and attempts < len(_SECESSION_PREFIXES):
        prefix = _SECESSION_PREFIXES[attempts]
        breakaway_name = f"{prefix} {base_name}"
        attempts += 1
    if breakaway_name in existing_names:
        breakaway_name = f"{prefix} {base_name} {world.turn}"

    parent_trait = source_civ.leader.trait
    available_traits = [t for t in _TRAIT_POOL if t != parent_trait]
    new_trait = rng.choice(available_traits) if available_traits else parent_trait

    new_values = list(source_civ.values)
    if new_values:
        value_pool = [
            "freedom", "order", "tradition", "progress", "honor",
            "wealth", "knowledge", "faith", "unity", "independence",
        ]
        swap_idx = rng.randint(0, len(new_values) - 1)
        available_values = [v for v in value_pool if v not in new_values]
        if available_values:
            new_values[swap_idx] = rng.choice(available_values)

    def _min_dist_to_parent(region_name: str) -> int:
        return min(
            (
                graph_distance(world.regions, region_name, parent_region)
                for parent_region in remaining_regions
            ),
            default=0,
        )

    breakaway_capital = min(breakaway_regions, key=_min_dist_to_parent)
    founded_turn = payload.get("founded_turn", world.turn)
    placeholder_leader = Leader(
        name="Placeholder",
        trait=new_trait,
        reign_start=founded_turn,
        succession_type="secession",
    )
    breakaway_civ = Civilization(
        name=breakaway_name,
        population=max(payload.get("stat_population", 1), 1),
        military=max(payload.get("stat_military", 0), 0),
        economy=max(payload.get("stat_economy", 0), 0),
        culture=payload.get("stat_culture", source_civ.culture),
        stability=payload.get("stat_stability", 40),
        treasury=payload.get("stat_treasury", 0),
        tech_era=source_civ.tech_era,
        leader=placeholder_leader,
        regions=list(breakaway_regions),
        capital_region=breakaway_capital,
        domains=list(source_civ.domains),
        values=new_values,
        asabiya=_normalize_politics_asabiya(payload.get("stat_asabiya"), 0.7),
        leader_name_pool=list(source_civ.leader_name_pool or []),
    )
    regnal_rng = random.Random(
        stable_hash_int("secession_regnal", world.seed, world.turn, breakaway_name)
    )
    title, throne_name, ordinal = _pick_regnal_name(breakaway_civ, world, regnal_rng)
    leader_name = _compose_regnal_name(title, throne_name, ordinal)
    breakaway_civ.leader.name = leader_name
    breakaway_civ.leader.throne_name = throne_name
    breakaway_civ.leader.regnal_ordinal = ordinal
    breakaway_civ.founded_turn = founded_turn
    breakaway_civ.traditions = list(source_civ.traditions)
    return breakaway_civ


def _materialize_breakaway_civ(world: WorldState, payload: dict, new_civ_map: dict) -> None:
    src_idx = _resolve_civ_ref(
        world,
        payload.get("source_ref_kind", 0),
        payload.get("source_ref_id", 0),
        new_civ_map,
    )
    if src_idx >= len(world.civilizations):
        return
    source_civ = world.civilizations[src_idx]
    region_indices = payload.get("region_indices", [])
    breakaway_regions = [
        world.regions[ri].name for ri in region_indices if ri < len(world.regions)
    ]
    if not breakaway_regions:
        return
    remaining_regions = [rn for rn in source_civ.regions if rn not in breakaway_regions]
    breakaway_civ = _build_breakaway_civ(
        world,
        source_civ,
        breakaway_regions,
        remaining_regions,
        payload,
    )
    source_civ.regions = remaining_regions
    sync_civ_population(source_civ, world)
    world.civilizations.append(breakaway_civ)
    world.relationships.setdefault(breakaway_civ.name, {})
    if payload.get("target_ref_kind", REF_EXISTING) != REF_EXISTING:
        new_civ_map[payload.get("target_ref_id", 0)] = len(world.civilizations) - 1


def _materialize_restored_civ(world: WorldState, payload: dict, new_civ_map: dict) -> None:
    from chronicler.models import TechEra

    absorber_idx = _resolve_civ_ref(
        world,
        payload.get("source_ref_kind", 0),
        payload.get("source_ref_id", 0),
        new_civ_map,
    )
    if absorber_idx >= len(world.civilizations):
        return
    absorber = world.civilizations[absorber_idx]
    region_indices = payload.get("region_indices", [])
    if not region_indices:
        return
    target_region_idx = region_indices[0]
    if target_region_idx >= len(world.regions):
        return
    target_region = world.regions[target_region_idx].name

    target_kind = payload.get("target_ref_kind", REF_EXISTING)
    target_ref_id = payload.get("target_ref_id", 0)
    restored_civ = None
    restored_name = None
    if target_kind == REF_EXISTING and target_ref_id < len(world.civilizations):
        restored_civ = world.civilizations[target_ref_id]
        restored_name = restored_civ.name
    else:
        for exile in world.exile_modifiers:
            if exile.absorber_civ == absorber.name and target_region in exile.conquered_regions:
                restored_name = exile.original_civ_name
                break
        if restored_name is None:
            return

    era_order = list(TechEra)
    absorber_era_idx = era_order.index(absorber.tech_era)
    restored_era = era_order[max(0, absorber_era_idx - 1)]

    rng_trait = random.Random(world.seed + world.turn)
    new_trait = rng_trait.choice(_TRAIT_POOL)
    restored_population = max(payload.get("stat_population", 30), 1)
    if world.agent_mode != "hybrid":
        world.regions[target_region_idx].population = restored_population
    restored_leader = Leader(name="Placeholder", trait=new_trait, reign_start=world.turn)

    if restored_civ is None:
        restored_civ = Civilization(
            name=restored_name,
            population=restored_population,
            military=payload.get("stat_military", 20),
            economy=payload.get("stat_economy", 20),
            culture=payload.get("stat_culture", 30),
            stability=payload.get("stat_stability", 50),
            treasury=payload.get("stat_treasury", 0),
            tech_era=restored_era,
            asabiya=_normalize_politics_asabiya(payload.get("stat_asabiya"), 0.8),
            leader=restored_leader,
            regions=[target_region],
            capital_region=target_region,
            founded_turn=payload.get("founded_turn", world.turn),
        )
        world.civilizations.append(restored_civ)
        if target_kind != REF_EXISTING:
            new_civ_map[target_ref_id] = len(world.civilizations) - 1
    else:
        restored_civ.population = restored_population
        restored_civ.military = payload.get("stat_military", 20)
        restored_civ.economy = payload.get("stat_economy", 20)
        restored_civ.culture = payload.get("stat_culture", 30)
        restored_civ.stability = payload.get("stat_stability", 50)
        restored_civ.treasury = payload.get("stat_treasury", 0)
        restored_civ.tech_era = restored_era
        restored_civ.leader = restored_leader
        restored_civ.regions = [target_region]
        restored_civ.capital_region = target_region
        restored_civ.founded_turn = payload.get("founded_turn", world.turn)
        restored_civ.decline_turns = 0
        restored_civ.stats_sum_history = []
        target_region_obj = next((r for r in world.regions if r.name == target_region), None)
        if target_region_obj is not None:
            target_region_obj.asabiya_state.asabiya = _normalize_politics_asabiya(
                payload.get("stat_asabiya"), 0.8,
            )

    regnal_rng = random.Random(
        stable_hash_int("restoration_regnal", world.seed, world.turn, restored_civ.name)
    )
    title, throne_name, ordinal = _pick_regnal_name(restored_civ, world, regnal_rng)
    leader_name = _compose_regnal_name(title, throne_name, ordinal)
    restored_civ.leader.name = leader_name
    restored_civ.leader.throne_name = throne_name
    restored_civ.leader.regnal_ordinal = ordinal

    if target_region in absorber.regions:
        absorber.regions.remove(target_region)
    if len(absorber.regions) == 0:
        from chronicler.simulation import reset_war_frequency_on_extinction
        reset_war_frequency_on_extinction(absorber)
    restored_civ.regions = [target_region]
    restored_civ.capital_region = target_region
    world.relationships.setdefault(restored_civ.name, {})
    sync_civ_population(absorber, world)
    sync_civ_population(restored_civ, world)


def _apply_civ_op(world: WorldState, payload: dict, new_civ_map: dict,
                  events: list[Event]) -> None:
    op_type = payload.get("op_type", -1)
    if op_type == CIV_OP_CREATE_BREAKAWAY:
        _materialize_breakaway_civ(world, payload, new_civ_map)
    elif op_type == CIV_OP_RESTORE:
        _materialize_restored_civ(world, payload, new_civ_map)
    elif op_type == CIV_OP_REASSIGN_CAPITAL:
        civ_idx = _resolve_civ_ref(world, payload.get("source_ref_kind", 0),
                                   payload.get("source_ref_id", 0), new_civ_map)
        if 0 <= civ_idx < len(world.civilizations):
            region_indices = payload.get("region_indices", [])
            region_idx = region_indices[0] if region_indices else payload.get("region_0", CIV_NONE)
            if region_idx != CIV_NONE and region_idx < len(world.regions):
                world.civilizations[civ_idx].capital_region = world.regions[region_idx].name
    elif op_type == CIV_OP_STRIP_TO_FIRST_REGION:
        civ_idx = _resolve_civ_ref(world, payload.get("source_ref_kind", 0),
                                   payload.get("source_ref_id", 0), new_civ_map)
        if 0 <= civ_idx < len(world.civilizations):
            civ = world.civilizations[civ_idx]
            if len(civ.regions) > 1:
                lost = civ.regions[1:]
                civ.regions = civ.regions[:1]
                for region in world.regions:
                    if region.name in lost:
                        region.controller = None
    elif op_type == CIV_OP_ABSORB:
        # Transfer regions from source to target, set source regions=[]
        src_idx = _resolve_civ_ref(world, payload.get("source_ref_kind", 0),
                                   payload.get("source_ref_id", 0), new_civ_map)
        tgt_idx = _resolve_civ_ref(world, payload.get("target_ref_kind", 0),
                                   payload.get("target_ref_id", 0), new_civ_map)
        if 0 <= src_idx < len(world.civilizations) and 0 <= tgt_idx < len(world.civilizations):
            src_civ = world.civilizations[src_idx]
            tgt_civ = world.civilizations[tgt_idx]
            region_map = {r.name: r for r in world.regions}
            for rn in list(src_civ.regions):
                tgt_civ.regions.append(rn)
                if rn in region_map:
                    region_map[rn].controller = tgt_civ.name
            src_civ.regions = []
            from chronicler.simulation import reset_war_frequency_on_extinction
            reset_war_frequency_on_extinction(src_civ)
            sync_civ_population(tgt_civ, world)
            sync_civ_population(src_civ, world)


def _apply_region_op(world: WorldState, payload: dict, new_civ_map: dict) -> None:
    op_type = payload.get("op_type", -1)
    region_idx = payload.get("region", CIV_NONE)
    if region_idx == CIV_NONE or region_idx >= len(world.regions):
        return
    region = world.regions[region_idx]

    if op_type == REGION_OP_SET_CONTROLLER:
        civ_idx = _resolve_civ_ref(world, payload.get("controller_ref_kind", 0),
                                   payload.get("controller_ref_id", 0), new_civ_map)
        if 0 <= civ_idx < len(world.civilizations):
            old_controller = region.controller
            new_controller = world.civilizations[civ_idx].name
            region.controller = new_controller
            civ_map = {c.name: c for c in world.civilizations}
            if old_controller in civ_map:
                sync_civ_population(civ_map[old_controller], world)
            if new_controller in civ_map:
                sync_civ_population(civ_map[new_controller], world)
    elif op_type == REGION_OP_NULLIFY_CONTROLLER:
        old_controller = region.controller
        region.controller = None
        civ_map = {c.name: c for c in world.civilizations}
        if old_controller in civ_map:
            sync_civ_population(civ_map[old_controller], world)
    elif op_type == REGION_OP_SET_SECEDED_TRANSIENT:
        region._seceded_this_turn = True


def _apply_relationship_op(world: WorldState, payload: dict,
                           new_civ_map: dict) -> None:
    op_type = payload.get("op_type", -1)
    a_idx = _resolve_civ_ref(world, payload.get("civ_a_ref_kind", 0),
                             payload.get("civ_a_ref_id", 0), new_civ_map)
    b_idx = _resolve_civ_ref(world, payload.get("civ_b_ref_kind", 0),
                             payload.get("civ_b_ref_id", 0), new_civ_map)
    if a_idx >= len(world.civilizations) or b_idx >= len(world.civilizations):
        return
    a_name = world.civilizations[a_idx].name
    b_name = world.civilizations[b_idx].name

    if op_type == REL_OP_INIT_PAIR:
        disp_u8 = payload.get("disposition", 2)
        disp = _U8_TO_DISPOSITION.get(disp_u8, Disposition.NEUTRAL)
        if a_name not in world.relationships:
            world.relationships[a_name] = {}
        if b_name not in world.relationships:
            world.relationships[b_name] = {}
        world.relationships[a_name][b_name] = Relationship(disposition=disp)
        world.relationships[b_name][a_name] = Relationship(disposition=disp)
    elif op_type == REL_OP_SET_DISPOSITION:
        disp_u8 = payload.get("disposition", 2)
        disp = _U8_TO_DISPOSITION.get(disp_u8, Disposition.NEUTRAL)
        if a_name in world.relationships and b_name in world.relationships[a_name]:
            world.relationships[a_name][b_name].disposition = disp
    elif op_type == REL_OP_RESET_ALLIED_TURNS:
        if a_name in world.relationships and b_name in world.relationships[a_name]:
            world.relationships[a_name][b_name].allied_turns = 0
    elif op_type == REL_OP_INCREMENT_ALLIED_TURNS:
        if a_name in world.relationships and b_name in world.relationships[a_name]:
            world.relationships[a_name][b_name].allied_turns += 1


def _apply_federation_op(
    world: WorldState,
    payload: dict,
    new_civ_map: dict,
    existing_fed_map: dict,
    new_fed_map: dict,
) -> None:
    op_type = payload.get("op_type", -1)
    civ_idx = _resolve_civ_ref(world, payload.get("civ_ref_kind", 0),
                               payload.get("civ_ref_id", 0), new_civ_map)
    civ_name = world.civilizations[civ_idx].name if 0 <= civ_idx < len(world.civilizations) else None

    if op_type == FED_OP_CREATE:
        from chronicler.models import Federation
        member_count = int(payload.get("member_count", 0))
        member_names: list[str] = []
        for idx in range(min(member_count, 2)):
            member_idx = _resolve_civ_ref(
                world,
                payload.get(f"member_{idx}_ref_kind", REF_EXISTING),
                payload.get(f"member_{idx}_ref_id", CIV_NONE),
                new_civ_map,
            )
            if 0 <= member_idx < len(world.civilizations):
                member_name = world.civilizations[member_idx].name
                if member_name not in member_names:
                    member_names.append(member_name)
        if not member_names and civ_name:
            member_names.append(civ_name)

        fed_name = payload.get("federation_name")
        if not fed_name:
            context_seed = int(payload.get("context_seed", 0))
            if context_seed:
                rng = random.Random(context_seed)
                fed_name = f"The {rng.choice(_FEDERATION_ADJECTIVES)} {rng.choice(_FEDERATION_NOUNS)}"
            else:
                fed_name = "New Federation"

        new_fed = Federation(name=fed_name, members=member_names,
                             founded_turn=payload.get("founded_turn", world.turn))
        world.federations.append(new_fed)
        local_id = payload.get("federation_ref_id", 0)
        new_fed_map[local_id] = len(world.federations) - 1
    elif op_type == FED_OP_APPEND_MEMBER:
        fed_idx = _resolve_fed_ref(
            payload.get("federation_ref_kind", 0),
            payload.get("federation_ref_id", 0),
            existing_fed_map,
            new_fed_map,
        )
        if 0 <= fed_idx < len(world.federations) and civ_name:
            world.federations[fed_idx].members.append(civ_name)
    elif op_type == FED_OP_REMOVE_MEMBER:
        fed_idx = _resolve_fed_ref(
            payload.get("federation_ref_kind", 0),
            payload.get("federation_ref_id", 0),
            existing_fed_map,
            new_fed_map,
        )
        if 0 <= fed_idx < len(world.federations) and civ_name:
            if civ_name in world.federations[fed_idx].members:
                world.federations[fed_idx].members.remove(civ_name)
    elif op_type == FED_OP_DISSOLVE:
        ref_kind = payload.get("federation_ref_kind", 0)
        ref_id = payload.get("federation_ref_id", 0)
        fed_idx = _resolve_fed_ref(
            ref_kind,
            ref_id,
            existing_fed_map,
            new_fed_map,
        )
        if 0 <= fed_idx < len(world.federations):
            world.federations.pop(fed_idx)
            if ref_kind == FED_REF_EXISTING:
                existing_fed_map.pop(ref_id, None)
            else:
                new_fed_map.pop(ref_id, None)
            for fed_map in (existing_fed_map, new_fed_map):
                for key, value in list(fed_map.items()):
                    if value > fed_idx:
                        fed_map[key] = value - 1


def _apply_vassal_op(world: WorldState, payload: dict,
                     new_civ_map: dict) -> None:
    op_type = payload.get("op_type", -1)
    if op_type == VASSAL_OP_REMOVE:
        vassal_idx = _resolve_civ_ref(world, payload.get("vassal_ref_kind", 0),
                                      payload.get("vassal_ref_id", 0), new_civ_map)
        overlord_idx = _resolve_civ_ref(world, payload.get("overlord_ref_kind", 0),
                                        payload.get("overlord_ref_id", 0), new_civ_map)
        if vassal_idx < len(world.civilizations) and overlord_idx < len(world.civilizations):
            v_name = world.civilizations[vassal_idx].name
            o_name = world.civilizations[overlord_idx].name
            world.vassal_relations = [
                vr for vr in world.vassal_relations
                if not (vr.vassal == v_name and vr.overlord == o_name)
            ]


def _apply_exile_op(world: WorldState, payload: dict,
                    new_civ_map: dict) -> None:
    op_type = payload.get("op_type", -1)
    if op_type == EXILE_OP_APPEND:
        orig_idx = _resolve_civ_ref(world, payload.get("original_civ_ref_kind", 0),
                                    payload.get("original_civ_ref_id", 0), new_civ_map)
        absorber_idx = _resolve_civ_ref(world, payload.get("absorber_civ_ref_kind", 0),
                                        payload.get("absorber_civ_ref_id", 0), new_civ_map)
        if orig_idx < len(world.civilizations) and absorber_idx < len(world.civilizations):
            region_indices = payload.get("region_indices", [])
            region_names = [
                world.regions[ri].name for ri in region_indices
                if ri < len(world.regions)
            ]
            world.exile_modifiers.append(ExileModifier(
                original_civ_name=world.civilizations[orig_idx].name,
                absorber_civ=world.civilizations[absorber_idx].name,
                conquered_regions=region_names,
                turns_remaining=payload.get("turns_remaining", 10),
            ))
    elif op_type == EXILE_OP_REMOVE:
        orig_idx = _resolve_civ_ref(world, payload.get("original_civ_ref_kind", 0),
                                    payload.get("original_civ_ref_id", 0), new_civ_map)
        if orig_idx < len(world.civilizations):
            orig_name = world.civilizations[orig_idx].name
            world.exile_modifiers = [
                em for em in world.exile_modifiers
                if em.original_civ_name != orig_name
            ]


def _apply_proxy_war_op(world: WorldState, payload: dict,
                        new_civ_map: dict) -> None:
    op_type = payload.get("op_type", -1)
    if op_type == PROXY_OP_SET_DETECTED:
        sponsor_idx = _resolve_civ_ref(world, payload.get("sponsor_ref_kind", 0),
                                       payload.get("sponsor_ref_id", 0), new_civ_map)
        target_idx = _resolve_civ_ref(world, payload.get("target_civ_ref_kind", 0),
                                      payload.get("target_civ_ref_id", 0), new_civ_map)
        if sponsor_idx < len(world.civilizations) and target_idx < len(world.civilizations):
            sponsor_name = world.civilizations[sponsor_idx].name
            target_name = world.civilizations[target_idx].name
            target_region_idx = payload.get("target_region", CIV_NONE)
            target_region_name = None
            if 0 <= target_region_idx < len(world.regions):
                target_region_name = world.regions[target_region_idx].name
            for pw in world.proxy_wars:
                if pw.sponsor != sponsor_name or pw.target_civ != target_name:
                    continue
                if target_region_name is not None and pw.target_region != target_region_name:
                    continue
                pw.detected = True


_CIV_EFFECT_FIELDS = {"military", "economy", "stability", "culture", "treasury", "asabiya"}


def _apply_civ_effect(world: WorldState, payload: dict,
                      new_civ_map: dict) -> None:
    civ_idx = _resolve_civ_ref(world, payload.get("civ_ref_kind", 0),
                               payload.get("civ_ref_id", 0), new_civ_map)
    if civ_idx >= len(world.civilizations):
        return
    civ = world.civilizations[civ_idx]
    field = payload.get("field", "")
    delta = payload.get("delta", 0.0)
    routing = payload.get("routing", ROUTING_DIRECT_ONLY)

    if routing == ROUTING_HYBRID_SHOCK and world.agent_mode == "hybrid":
        # Convert to pending shock
        shock_field_map = {
            "stability": "stability_shock",
            "military": "military_shock",
            "economy": "economy_shock",
            "culture": "culture_shock",
        }
        if field in shock_field_map:
            shock_attr = shock_field_map[field]
            for shock in reversed(world.pending_shocks):
                if shock.civ_id != civ_idx:
                    continue
                if getattr(shock, shock_attr) == 0:
                    setattr(shock, shock_attr, delta)
                    return
            world.pending_shocks.append(CivShock(civ_id=civ_idx, **{shock_attr: delta}))
        return

    # Direct application
    if field == "asabiya":
        from chronicler.simulation import _apply_asabiya_to_regions
        _apply_asabiya_to_regions(world, civ.name, delta)
    elif field == "treasury":
        civ.treasury = int(civ.treasury + delta)
    elif field in ("military", "economy", "stability", "culture"):
        old_val = getattr(civ, field)
        new_val = clamp(int(old_val + delta), STAT_FLOOR.get(field, 0), 100)
        setattr(civ, field, new_val)


def _apply_bookkeeping(world: WorldState, payload: dict,
                       new_civ_map: dict) -> None:
    civ_idx = _resolve_civ_ref(world, payload.get("civ_ref_kind", 0),
                               payload.get("civ_ref_id", 0), new_civ_map)
    if civ_idx >= len(world.civilizations):
        return
    civ = world.civilizations[civ_idx]
    bk_type = payload.get("bk_type", -1)

    if bk_type == BK_APPEND_STATS_HISTORY:
        value = payload.get("value", 0)
        civ.stats_sum_history.append(value)
        if len(civ.stats_sum_history) > 20:
            civ.stats_sum_history = civ.stats_sum_history[-20:]
    elif bk_type == BK_INCREMENT_DECLINE:
        civ.decline_turns += 1
    elif bk_type == BK_RESET_DECLINE:
        civ.decline_turns = 0
    elif bk_type == BK_INCREMENT_EVENT_COUNT:
        key = payload.get("event_key", "")
        if key:
            civ.event_counts[key] = civ.event_counts.get(key, 0) + 1


def _apply_artifact_intent(world: WorldState, payload: dict,
                           new_civ_map: dict) -> None:
    from chronicler.artifacts import emit_conquest_lifecycle_intent
    losing_idx = _resolve_civ_ref(world, payload.get("losing_civ_ref_kind", 0),
                                  payload.get("losing_civ_ref_id", 0), new_civ_map)
    gaining_idx = _resolve_civ_ref(world, payload.get("gaining_civ_ref_kind", 0),
                                   payload.get("gaining_civ_ref_id", 0), new_civ_map)
    region_idx = payload.get("region", CIV_NONE)
    if losing_idx < len(world.civilizations) and gaining_idx < len(world.civilizations) and region_idx < len(world.regions):
        emit_conquest_lifecycle_intent(
            world,
            losing_civ=world.civilizations[losing_idx].name,
            gaining_civ=world.civilizations[gaining_idx].name,
            region=world.regions[region_idx].name,
            is_capital=payload.get("is_capital", False),
            is_destructive=payload.get("is_destructive", False),
            action=payload.get("action", "twilight_absorption"),
        )


def _apply_bridge_transition(world: WorldState, payload: dict,
                             new_civ_map: dict, events: list[Event]) -> None:
    bridge = getattr(world, "_agent_bridge", None)
    if bridge is None or world.agent_mode != "hybrid":
        return

    trans_type = payload.get("transition_type", -1)
    src_idx = _resolve_civ_ref(world, payload.get("source_ref_kind", 0),
                               payload.get("source_ref_id", 0), new_civ_map)
    tgt_idx = _resolve_civ_ref(world, payload.get("target_ref_kind", 0),
                               payload.get("target_ref_id", 0), new_civ_map)
    if src_idx >= len(world.civilizations) or tgt_idx >= len(world.civilizations):
        return
    src_civ = world.civilizations[src_idx]
    tgt_civ = world.civilizations[tgt_idx]
    region_indices = payload.get("region_indices", [])
    region_names = [
        world.regions[ri].name for ri in region_indices
        if ri < len(world.regions)
    ]

    if trans_type == BRIDGE_SECESSION:
        transition_events = bridge.apply_secession_transitions(
            src_civ, tgt_civ, region_names,
            new_civ_id=tgt_idx, turn=world.turn,
            world=world, old_civ_id=src_idx,
        )
        events.extend(transition_events)
    elif trans_type == BRIDGE_RESTORATION:
        bridge.apply_restoration_transitions(
            src_civ, tgt_civ, region_names,
            absorber_civ_id=src_idx, restored_civ_id=tgt_idx,
            world=world,
        )
    elif trans_type == BRIDGE_ABSORPTION:
        bridge.apply_absorption_transitions(
            src_civ, tgt_civ, region_names,
            losing_civ_id=src_idx, absorber_civ_id=tgt_idx,
            world=world,
        )


def _apply_event_trigger(world: WorldState, payload: dict,
                         new_civ_map: dict, events: list[Event]) -> None:
    event_type = payload.get("event_type", "unknown")
    actor_count = payload.get("actor_count", 0)
    actors: list[str] = []
    for slot in range(min(actor_count, 2)):
        kind = payload.get(f"actor_{slot}_ref_kind", 0)
        ref_id = payload.get(f"actor_{slot}_ref_id", CIV_NONE)
        if ref_id == CIV_NONE:
            continue
        idx = _resolve_civ_ref(world, kind, ref_id, new_civ_map)
        if idx < len(world.civilizations):
            actors.append(world.civilizations[idx].name)
    importance = payload.get("importance", 5)
    description = payload.get("description", "")
    events.append(Event(
        turn=world.turn,
        event_type=event_type,
        actors=actors,
        description=description,
        importance=importance,
    ))


# ────────────────────────────────────────────────────────────────────
# M54c Task 4: Politics runtime configuration helper
# ────────────────────────────────────────────────────────────────────


def configure_politics_runtime(simulator, world: WorldState) -> None:
    """Wire politics config from tuning overrides onto a Rust simulator.

    Works for both AgentSimulator and PoliticsSimulator — both expose
    set_politics_config() with identical signatures.

    Reads tuning overrides from world.tuning_overrides; falls back to
    PoliticsConfig::default() values when no override is present.
    """
    from chronicler.tuning import (
        get_override,
        K_SECESSION_STABILITY_THRESHOLD, K_SECESSION_SURVEILLANCE_THRESHOLD,
        K_PROXY_WAR_SECESSION_BONUS, K_SECESSION_STABILITY_LOSS,
        K_SECESSION_LIKELIHOOD, K_CAPITAL_LOSS_STABILITY,
        K_VASSAL_REBELLION_BASE_PROB, K_VASSAL_REBELLION_REDUCED_PROB,
        K_FEDERATION_ALLIED_TURNS, K_FEDERATION_EXIT_STABILITY,
        K_FEDERATION_REMAINING_STABILITY,
        K_RESTORATION_BASE_PROB, K_RESTORATION_RECOGNITION_BONUS,
        K_TWILIGHT_ABSORPTION_DECLINE,
        K_SEVERITY_STRESS_DIVISOR, K_SEVERITY_STRESS_SCALE,
        K_SEVERITY_CAP, K_SEVERITY_MULTIPLIER,
    )
    simulator.set_politics_config(
        # Match the preserved Python oracle defaults used by the phase helpers.
        secession_stability_threshold=int(get_override(world, K_SECESSION_STABILITY_THRESHOLD, 10)),
        secession_surveillance_threshold=int(get_override(world, K_SECESSION_SURVEILLANCE_THRESHOLD, 5)),
        proxy_war_secession_bonus=float(get_override(world, K_PROXY_WAR_SECESSION_BONUS, 0.05)),
        secession_stability_loss=int(get_override(world, K_SECESSION_STABILITY_LOSS, 10)),
        secession_likelihood_multiplier=float(get_override(world, K_SECESSION_LIKELIHOOD, 1.0)),
        capital_loss_stability=int(get_override(world, K_CAPITAL_LOSS_STABILITY, 20)),
        vassal_rebellion_base_prob=float(get_override(world, K_VASSAL_REBELLION_BASE_PROB, 0.15)),
        vassal_rebellion_reduced_prob=float(get_override(world, K_VASSAL_REBELLION_REDUCED_PROB, 0.05)),
        federation_allied_turns=int(get_override(world, K_FEDERATION_ALLIED_TURNS, 10)),
        federation_exit_stability=int(get_override(world, K_FEDERATION_EXIT_STABILITY, 15)),
        federation_remaining_stability=int(get_override(world, K_FEDERATION_REMAINING_STABILITY, 5)),
        restoration_base_prob=float(get_override(world, K_RESTORATION_BASE_PROB, 0.05)),
        restoration_recognition_bonus=float(get_override(world, K_RESTORATION_RECOGNITION_BONUS, 0.03)),
        twilight_absorption_decline=int(get_override(world, K_TWILIGHT_ABSORPTION_DECLINE, 40)),
        severity_stress_divisor=float(get_override(world, K_SEVERITY_STRESS_DIVISOR, 20.0)),
        severity_stress_scale=float(get_override(world, K_SEVERITY_STRESS_SCALE, 0.5)),
        severity_cap=float(get_override(world, K_SEVERITY_CAP, 2.0)),
        severity_multiplier=float(get_override(world, K_SEVERITY_MULTIPLIER, 1.0)),
    )


# ────────────────────────────────────────────────────────────────────
# M54c Task 3: Arrow batch conversion and Rust FFI call wrapper
# ────────────────────────────────────────────────────────────────────


def _dict_to_civ_input_batch(d: dict):
    """Convert the civ input dict-of-lists to a pyarrow RecordBatch.

    Packed list columns (stats_sum_history, regions) use Arrow list types
    so all columns have the same row count (= number of civs).
    """
    import pyarrow as pa

    n = len(d["civ_idx"])

    # Unpack the flat offsets+values into per-row lists for Arrow list columns
    ssh_offsets = d["stats_sum_history_offsets"]
    ssh_values = d["stats_sum_history_values"]
    ssh_lists = []
    for i in range(n):
        start = ssh_offsets[i]
        end = ssh_offsets[i + 1]
        ssh_lists.append(ssh_values[start:end])

    reg_offsets = d["region_offsets"]
    reg_values = d["region_values"]
    reg_lists = []
    for i in range(n):
        start = reg_offsets[i]
        end = reg_offsets[i + 1]
        reg_lists.append(reg_values[start:end])

    # Build the flat packed arrays with matching row count
    # Offsets: n+1 elements; we pad values to get consistent columns.
    # Use a separate approach: build individual arrays and construct batch
    # with from_arrays to allow mixed-length auxiliary columns.
    #
    # Actually, the Rust FFI parser expects flat columns for offsets/values.
    # We need to use pa.RecordBatch.from_arrays with explicit schema to
    # allow different-length columns. But Arrow does not allow that.
    #
    # Solution: use pa.Table and convert, or pass auxiliary data separately.
    #
    # Pragmatic fix: embed the packed data as Arrow list<int32>/list<uint16>
    # columns, and adjust the Rust parser to read list arrays.
    #
    # Simplest approach: pass flat offset+value arrays as separate batches
    # alongside the main civ batch.
    #
    # For M54c, we use the simplest correct approach: build the packed data
    # as flat lists in Arrow using list types, and have the Rust side
    # reconstruct the offsets+values from list arrays.

    fields = [
        pa.field("civ_idx", pa.uint16()),
        pa.field("civ_name", pa.string()),
        pa.field("stability", pa.int32()),
        pa.field("military", pa.int32()),
        pa.field("economy", pa.int32()),
        pa.field("culture", pa.int32()),
        pa.field("treasury", pa.int32()),
        pa.field("asabiya", pa.float32()),
        pa.field("population", pa.int32()),
        pa.field("decline_turns", pa.int32()),
        pa.field("founded_turn", pa.uint32()),
        pa.field("civ_stress", pa.int32()),
        pa.field("civ_majority_faith", pa.uint8()),
        pa.field("active_focus", pa.uint8()),
        pa.field("total_effective_capacity", pa.int32()),
        pa.field("capital_region", pa.uint16()),
        pa.field("num_regions", pa.uint16()),
        pa.field("dominant_faction", pa.uint8()),
        pa.field("secession_occurred_count", pa.int32()),
        pa.field("capital_lost_count", pa.int32()),
        pa.field("stats_sum_history", pa.list_(pa.int32())),
        pa.field("regions_list", pa.list_(pa.uint16())),
    ]
    schema = pa.schema(fields)

    arrays = [
        pa.array(d["civ_idx"], type=pa.uint16()),
        pa.array(d["civ_name"], type=pa.string()),
        pa.array(d["stability"], type=pa.int32()),
        pa.array(d["military"], type=pa.int32()),
        pa.array(d["economy"], type=pa.int32()),
        pa.array(d["culture"], type=pa.int32()),
        pa.array(d["treasury"], type=pa.int32()),
        pa.array(d["asabiya"], type=pa.float32()),
        pa.array(d["population"], type=pa.int32()),
        pa.array(d["decline_turns"], type=pa.int32()),
        pa.array(d["founded_turn"], type=pa.uint32()),
        pa.array(d["civ_stress"], type=pa.int32()),
        pa.array(d["civ_majority_faith"], type=pa.uint8()),
        pa.array(
            [14 if f == "surveillance" else 0 for f in d["active_focus"]],
            type=pa.uint8(),
        ),
        pa.array(d["total_effective_capacity"], type=pa.int32()),
        pa.array(d["capital_region"], type=pa.uint16()),
        pa.array(d["num_regions"], type=pa.uint16()),
        pa.array(d.get("dominant_faction", [0] * n), type=pa.uint8()),
        pa.array(d.get("secession_occurred_count", [0] * n), type=pa.int32()),
        pa.array(d.get("capital_lost_count", [0] * n), type=pa.int32()),
        pa.array(ssh_lists, type=pa.list_(pa.int32())),
        pa.array(reg_lists, type=pa.list_(pa.uint16())),
    ]
    return pa.RecordBatch.from_arrays(arrays, schema=schema)


def _dict_to_region_input_batch(d: dict):
    """Convert the region input dict-of-lists to a pyarrow RecordBatch.

    Adjacency data uses Arrow list<uint16> column so all columns share
    the same row count (= number of regions).
    """
    import pyarrow as pa

    n = len(d["region_idx"])
    adj_offsets = d["adjacency_offsets"]
    adj_values = d["adjacency_values"]
    adj_lists = []
    for i in range(n):
        start = adj_offsets[i]
        end = adj_offsets[i + 1]
        adj_lists.append(adj_values[start:end])

    fields = [
        pa.field("region_idx", pa.uint16()),
        pa.field("controller", pa.uint16()),
        pa.field("carrying_capacity", pa.uint16()),
        pa.field("population", pa.uint16()),
        pa.field("majority_belief", pa.uint8()),
        pa.field("effective_capacity", pa.uint16()),
        pa.field("adjacencies", pa.list_(pa.uint16())),
    ]
    arrays = [
        pa.array(d["region_idx"], type=pa.uint16()),
        pa.array(d["controller"], type=pa.uint16()),
        pa.array(d["carrying_capacity"], type=pa.uint16()),
        pa.array(d["population"], type=pa.uint16()),
        pa.array(d["majority_belief"], type=pa.uint8()),
        pa.array(d.get("effective_capacity", d["carrying_capacity"]), type=pa.uint16()),
        pa.array(adj_lists, type=pa.list_(pa.uint16())),
    ]
    return pa.RecordBatch.from_arrays(arrays, schema=pa.schema(fields))


def _dict_to_pair_batch(d: dict, key_a: str = "civ_a", key_b: str = "civ_b"):
    """Convert a pairwise dict-of-lists to a pyarrow RecordBatch."""
    import pyarrow as pa
    return pa.record_batch({
        key_a: pa.array(d[key_a], type=pa.uint16()),
        key_b: pa.array(d[key_b], type=pa.uint16()),
    })


def _dict_to_relationship_batch(d: dict):
    """Convert relationship dict-of-lists to a pyarrow RecordBatch."""
    import pyarrow as pa
    return pa.record_batch({
        "civ_a": pa.array(d["civ_a"], type=pa.uint16()),
        "civ_b": pa.array(d["civ_b"], type=pa.uint16()),
        "disposition": pa.array(d["disposition"], type=pa.uint8()),
        "allied_turns": pa.array(d["allied_turns"], type=pa.int32()),
    })


def _dict_to_vassal_batch(d: dict):
    """Convert vassal dict-of-lists to a pyarrow RecordBatch."""
    import pyarrow as pa
    return pa.record_batch({
        "vassal": pa.array(d["vassal"], type=pa.uint16()),
        "overlord": pa.array(d["overlord"], type=pa.uint16()),
    })


def _dict_to_federation_batch(d: dict):
    """Convert federation dict-of-lists to a pyarrow RecordBatch."""
    import pyarrow as pa
    n = len(d["federation_idx"])
    m_offsets = d["member_offsets"]
    m_values = d["member_values"]
    m_lists = []
    for i in range(n):
        start = m_offsets[i]
        end = m_offsets[i + 1]
        m_lists.append(m_values[start:end])
    fields = [
        pa.field("federation_idx", pa.uint16()),
        pa.field("founded_turn", pa.uint32()),
        pa.field("members", pa.list_(pa.uint16())),
    ]
    arrays = [
        pa.array(d["federation_idx"], type=pa.uint16()),
        pa.array(d["founded_turn"], type=pa.uint32()),
        pa.array(m_lists, type=pa.list_(pa.uint16())),
    ]
    return pa.RecordBatch.from_arrays(arrays, schema=pa.schema(fields))


def _dict_to_proxy_war_batch(d: dict):
    """Convert proxy war dict-of-lists to a pyarrow RecordBatch."""
    import pyarrow as pa
    return pa.record_batch({
        "sponsor": pa.array(d["sponsor"], type=pa.uint16()),
        "target_civ": pa.array(d["target_civ"], type=pa.uint16()),
        "target_region": pa.array(d["target_region"], type=pa.uint16()),
        "detected": pa.array(d["detected"], type=pa.bool_()),
    })


def _dict_to_exile_batch(d: dict):
    """Convert exile dict-of-lists to a pyarrow RecordBatch."""
    import pyarrow as pa
    n = len(d["original_civ"])
    r_off = d["region_offsets"]
    r_val = d["region_values"]
    r_lists = []
    for i in range(n):
        r_lists.append(r_val[r_off[i]:r_off[i + 1]])
    rec_off = d["recognized_offsets"]
    rec_val = d["recognized_values"]
    rec_lists = []
    for i in range(n):
        rec_lists.append(rec_val[rec_off[i]:rec_off[i + 1]])
    fields = [
        pa.field("original_civ", pa.uint16()),
        pa.field("absorber_civ", pa.uint16()),
        pa.field("turns_remaining", pa.int32()),
        pa.field("conquered_regions", pa.list_(pa.uint16())),
        pa.field("recognized_by", pa.list_(pa.uint16())),
    ]
    arrays = [
        pa.array(d["original_civ"], type=pa.uint16()),
        pa.array(d["absorber_civ"], type=pa.uint16()),
        pa.array(d["turns_remaining"], type=pa.int32()),
        pa.array(r_lists, type=pa.list_(pa.uint16())),
        pa.array(rec_lists, type=pa.list_(pa.uint16())),
    ]
    return pa.RecordBatch.from_arrays(arrays, schema=pa.schema(fields))


def _batch_to_dict(batch) -> dict:
    """Convert a pyarrow RecordBatch (or arro3 RecordBatch) to a dict-of-lists.

    Handles both pyarrow and arro3-core RecordBatch objects by converting
    column values to Python lists.
    """
    result = {}
    for i in range(batch.num_columns):
        name = batch.schema.field(i).name
        col = batch.column(i)
        result[name] = col.to_pylist()
    return result


def _build_region_input_with_eff_cap(world: WorldState) -> dict:
    """Build region input dict with effective_capacity populated from ecology."""
    from chronicler.ecology import effective_capacity as _eff_cap
    d = build_politics_region_input_batch(world)
    eff_caps = []
    for r in world.regions:
        eff_caps.append(min(int(_eff_cap(r, world)), 65535))
    d["effective_capacity"] = eff_caps
    return d


def call_rust_politics(
    simulator,
    world: WorldState,
    hybrid_mode: bool,
) -> list[tuple]:
    """Build input batches, call Rust tick_politics(), reconstruct ops.

    This is the Task 3 Python wrapper that bridges:
      Task 1 builders -> Arrow conversion -> Rust FFI -> Task 1 reconstruct

    Returns the sorted (step, seq, family, payload) list ready for
    apply_politics_ops().
    """
    # 1. Build dict-of-lists from Task 1 builders
    civ_dict = build_politics_civ_input_batch(world)
    region_dict = _build_region_input_with_eff_cap(world)
    rel_dict = build_politics_relationship_batch(world)
    vassal_dict = build_politics_vassal_batch(world)
    fed_dict = build_politics_federation_batch(world)
    war_dict = build_politics_war_batch(world)
    embargo_dict = build_politics_embargo_batch(world)
    proxy_dict = build_politics_proxy_war_batch(world)
    exile_dict = build_politics_exile_batch(world)
    ctx = build_politics_context(world, hybrid_mode)

    # 2. Convert to Arrow RecordBatches
    civ_rb = _dict_to_civ_input_batch(civ_dict)
    region_rb = _dict_to_region_input_batch(region_dict)
    rel_rb = _dict_to_relationship_batch(rel_dict)
    vassal_rb = _dict_to_vassal_batch(vassal_dict)
    fed_rb = _dict_to_federation_batch(fed_dict)
    war_rb = _dict_to_pair_batch(war_dict)
    embargo_rb = _dict_to_pair_batch(embargo_dict)
    proxy_rb = _dict_to_proxy_war_batch(proxy_dict)
    exile_rb = _dict_to_exile_batch(exile_dict)

    # 3. Call Rust FFI
    result_tuple = simulator.tick_politics(
        civ_rb, region_rb, rel_rb, vassal_rb, fed_rb,
        war_rb, embargo_rb, proxy_rb, exile_rb,
        ctx["turn"], ctx["seed"], ctx["hybrid_mode"],
    )

    # 4. Convert returned Arrow batches to dict-of-lists
    batch_dicts = [_batch_to_dict(b) for b in result_tuple]

    # 5. Reconstruct ops via Task 1 reconstruct
    return reconstruct_politics_ops(*batch_dicts)
