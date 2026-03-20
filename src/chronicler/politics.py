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
from chronicler.utils import civ_index, clamp, STAT_FLOOR, sync_civ_population, drain_region_pop
from chronicler.intelligence import get_perceived_stat
from chronicler.emergence import get_severity_multiplier

if TYPE_CHECKING:
    pass


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

        rng = random.Random(world.seed + world.turn + hash(civ.name))
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

        name_pool = civ.leader_name_pool or ["Leader"]
        used = set(world.used_leader_names)
        leader_name = None
        for n in name_pool:
            if n not in used:
                leader_name = n
                break
        if leader_name is None:
            leader_name = f"{breakaway_name} Leader"
        world.used_leader_names.append(leader_name)

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

        new_leader = Leader(
            name=leader_name,
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
            leader=new_leader,
            regions=breakaway_regions,
            capital_region=breakaway_capital,
            domains=list(civ.domains),
            values=new_values,
            asabiya=0.7,
            leader_name_pool=list(civ.leader_name_pool or []),
        )

        breakaway_civ.founded_turn = world.turn

        # M17d: Tradition inheritance through secession
        breakaway_civ.traditions = list(civ.traditions)

        civ_idx = civ_index(world, civ.name)
        mult = get_severity_multiplier(civ, world)
        secession_stab_loss = int(get_override(world, K_SECESSION_STABILITY_LOSS, 10))
        if world.agent_mode == "hybrid":
            world.pending_shocks.append(CivShock(civ_idx,
                military_shock=normalize_shock(split_mil, civ.military),
                economy_shock=normalize_shock(split_eco, civ.economy),
                stability_shock=normalize_shock(int(secession_stab_loss * mult), civ.stability)))
            civ.treasury -= split_tre  # treasury stays Python-side
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
    rng = random.Random(world.seed + world.turn + hash(winner.name))
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

        rng = random.Random(world.seed + world.turn + hash(vr.vassal))
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
            vassal.asabiya = min(vassal.asabiya + 0.2, 1.0)
        elif acc is not None:
            acc.add(vassal_idx, vassal, "stability", 10, "guard-shock")
            acc.add(vassal_idx, vassal, "asabiya", 0.2, "keep")
        else:
            vassal.stability = clamp(vassal.stability + 10, STAT_FLOOR["stability"], 100)
            vassal.asabiya = min(vassal.asabiya + 0.2, 1.0)

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

        rng = random.Random(world.seed + world.turn + hash(pw.sponsor) + hash(pw.target_civ))
        detection_prob = target.culture / 100
        if rng.random() < detection_prob:
            pw.detected = True
            target_idx = civ_index(world, target.name)
            if world.agent_mode == "hybrid":
                world.pending_shocks.append(CivShock(target_idx,
                    stability_shock=min(1.0, 5 / max(target.stability, 1))))
            elif acc is not None:
                acc.add(target_idx, target, "stability", 5, "guard-shock")
            else:
                target.stability = clamp(target.stability + 5, STAT_FLOOR["stability"], 100)

            rels = world.relationships.get(pw.sponsor, {})
            if pw.target_civ in rels:
                rels[pw.target_civ].disposition = Disposition.HOSTILE

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
        rng = random.Random(world.seed + world.turn + hash(exile.original_civ_name))
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

        leader_name = f"{exile.original_civ_name} Restorer"
        rng_trait = random.Random(world.seed + world.turn)
        new_trait = rng_trait.choice(_TRAIT_POOL)

        region_map[target_region].population = 30
        restored_civ = Civilization(
            name=exile.original_civ_name,
            population=30, military=20, economy=20,
            culture=30, stability=50, treasury=0,
            tech_era=restored_era, asabiya=0.8,
            leader=Leader(name=leader_name, trait=new_trait, reign_start=world.turn),
            regions=[target_region], capital_region=target_region,
        )
        world.civilizations.append(restored_civ)

        if target_region in absorber.regions:
            absorber.regions.remove(target_region)
        if len(absorber.regions) == 0:
            from chronicler.simulation import reset_war_frequency_on_extinction
            reset_war_frequency_on_extinction(absorber)
        region_map[target_region].controller = exile.original_civ_name
        sync_civ_population(absorber, world)

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
        if acc is not None:
            civ_idx = civ_index(world, civ.name)
            acc.add(civ_idx, civ, "asabiya", asabiya_boost, "keep")
        else:
            civ.asabiya = min(civ.asabiya + asabiya_boost, 1.0)
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
    to_remove = []

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
                for rn in absorbed_regions:
                    best_absorber_u.regions.append(rn)
                    if rn in region_map_u:
                        region_map_u[rn].controller = best_absorber_u.name
                civ.regions = []
                from chronicler.simulation import reset_war_frequency_on_extinction
                reset_war_frequency_on_extinction(civ)
                to_remove.append(civ)
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

        for rn in civ.regions:
            best_absorber.regions.append(rn)
            if rn in region_map:
                region_map[rn].controller = best_absorber.name
        civ.regions = []
        from chronicler.simulation import reset_war_frequency_on_extinction
        reset_war_frequency_on_extinction(civ)
        to_remove.append(civ)

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

    # Find most hostile neighbor with regions
    target = None
    rels = world.relationships.get(civ.name, {})
    candidates = []
    for other_name, rel in rels.items():
        if rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
            other = civ_map.get(other_name)
            if other and len(other.regions) >= 2:
                candidates.append(other)
    if not candidates:
        # Fallback: any hostile neighbor
        for other_name, rel in rels.items():
            if rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                other = civ_map.get(other_name)
                if other and other.regions:
                    candidates.append(other)

    if not candidates:
        return Event(turn=world.turn, event_type="fund_instability_failed",
                     actors=[civ.name], description=f"{civ.name} found no viable target", importance=3)

    target = candidates[0]

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
