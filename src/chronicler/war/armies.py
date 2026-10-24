"""Army lifecycle: enlistment, casualties, desertion, generals, demobilization.

Enlistment is drawn from population:

* ``--agents off``: the muster is an aggregate head count computed from the
  civ's controlled population and military readiness. Soldiers stay part of
  the population; casualties permanently drain it.
* agent modes (demographics-only, shadow, hybrid): the muster selects real
  native agents (soldiers first, then farmer levies) of the civ's polity from
  the current snapshot. The army roster stores their stable ids. Casualties
  queue those exact ids for death in the next native tick
  (``AgentSimulator.queue_targeted_deaths``) and drain the Python-side region
  population so same-turn phases agree. After the tick, rosters are
  reconciled against the Phase 10 snapshot so natural deaths shrink armies.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from chronicler.columnar import batch_arrays, last_row_of, pylist
from chronicler.tuning import get_override
from chronicler.utils import distribute_pop_loss, drain_region_pop, stage_region_catastrophe_deaths
from chronicler.war import params as P
from chronicler.war.common import (
    WarContext, armies_of, distances_from, emit, own_free_regions, spend, war_rng,
)

if TYPE_CHECKING:
    from chronicler.models import Army, Civilization, GreatPerson, WarRecord


SOLDIER_OCCUPATION = 1
FARMER_OCCUPATION = 0


def enlisted(world, civ_name: str) -> int:
    return sum(a.soldiers for a in world.war_state.armies if a.civ == civ_name)


def muster_capacity(world, civ: "Civilization") -> int:
    """Soldiers the civ could raise now from its controlled population."""
    pop = sum(r.population for r in world.regions if r.controller == civ.name)
    base = get_override(world, P.K_MOBILIZATION_BASE, P.MOBILIZATION_BASE_PERMILLE)
    per_mil = get_override(world, P.K_MOBILIZATION_PER_MILITARY, P.MOBILIZATION_PER_MILITARY_PERMILLE)
    cap_rate = get_override(world, P.K_MAX_MOBILIZATION, P.MAX_MOBILIZATION_PERMILLE)
    rate = base + per_mil * max(0, civ.military)
    target = max(P.MIN_ARMY, int(pop * rate) // 1000)
    cap = int(pop * cap_rate) // 1000 - enlisted(world, civ.name)
    return max(0, min(target, cap))


def can_raise(ctx: WarContext, civ: "Civilization") -> bool:
    """Whether :func:`raise_army` could field an army now (ignoring staging)."""
    world = ctx.world
    if len(armies_of(world, civ.name)) >= P.MAX_ARMIES_PER_CIV:
        return False
    last = world.war_state.last_raise_turn.get(civ.name)
    if last is not None and world.turn - last < P.RAISE_COOLDOWN_TURNS:
        return False
    per_10 = get_override(world, P.K_RAISE_COST_PER_10, P.RAISE_COST_PER_10_SOLDIERS)
    affordable = (max(0, _treasury(ctx, civ)) * 10) // max(1, int(per_10))
    return min(muster_capacity(world, civ), affordable) >= P.MIN_ARMY


def staging_region(ctx: WarContext, civ: "Civilization", toward: str | None) -> str | None:
    """Own unoccupied region closest to ``toward`` (capital when no target)."""
    own = own_free_regions(ctx.world, civ.name)
    if not own:
        return None
    if toward is None:
        return civ.capital_region if civ.capital_region in own else own[0]
    dist = distances_from(ctx, toward)
    region_map = ctx.world.region_map
    return min(own, key=lambda n: (dist.get(n, 10_000), -region_map[n].population, ctx.index[n]))


def _army_name(ctx: WarContext, civ: "Civilization") -> str:
    counts = ctx.world.war_state.raised_counts
    n = counts.get(civ.name, 0)
    counts[civ.name] = n + 1
    noun = P.ARMY_NOUNS.get(civ.tech_era.value, "Host")
    ordinal = P.ORDINALS[n] if n < len(P.ORDINALS) else f"{n + 1}th"
    return f"The {ordinal} {noun} of {civ.name}"


def _select_recruits_columnar(ctx, civ, civ_idx, taken, dist, count, ids, regs, occs, affs):
    """``select_recruits``' candidate filter and sort over NumPy columns.

    Per-region eligibility (controller, occupation, distance) is a table
    lookup; candidates sort by the same key ``(soldier first, hops, id,
    region)`` (lexsort, ids breaking every tie the key can have).
    """
    regions = ctx.world.regions
    hops_of = np.full(len(regions) + 1, -1, dtype=np.int64)
    for idx, region in enumerate(regions):
        if region.controller != civ.name or region.occupied_by not in (None, civ.name):
            continue
        hops = dist.get(region.name)
        if hops is not None:
            hops_of[idx] = hops
    ids = np.asarray(ids, dtype=np.int64)
    regs = np.asarray(regs, dtype=np.int64)
    occs = np.asarray(occs, dtype=np.int64)
    hops = hops_of[np.where((regs >= 0) & (regs < len(regions)), regs, len(regions))]
    keep = ((np.asarray(affs, dtype=np.int64) == civ_idx)
            & ((occs == SOLDIER_OCCUPATION) | (occs == FARMER_OCCUPATION)) & (hops >= 0))
    if taken:
        keep &= ~np.isin(ids, np.fromiter(taken, dtype=np.int64, count=len(taken)))
    rank = np.where(occs[keep] == SOLDIER_OCCUPATION, 0, 1)
    cand_ids, cand_regs = ids[keep], regs[keep]
    order = np.lexsort((cand_regs, cand_ids, hops[keep], rank))[:max(count, 0)]
    return list(zip(cand_ids[order].tolist(), cand_regs[order].tolist()))


def select_recruits(ctx: WarContext, civ: "Civilization", staging: str, count: int) -> list[tuple[int, int]]:
    """Pick ``count`` native agents of the civ: soldiers first, nearest first.

    Named characters and agents already enlisted are excluded. Returns
    ``(agent_id, region_index)`` pairs ordered by priority.
    """
    if count <= 0 or ctx.bridge is None:
        return []
    try:
        snap = ctx.bridge.get_snapshot()
    except Exception:
        return []
    if snap is None or getattr(snap, "num_rows", 0) == 0:
        return []
    from chronicler.utils import civ_index
    civ_idx = civ_index(ctx.world, civ.name)
    taken = {aid for army in ctx.world.war_state.armies for aid, _ in army.roster}
    taken.update(getattr(ctx.bridge, "named_agents", {}) or {})
    dist = distances_from(ctx, staging)
    regions = ctx.world.regions
    arrays = batch_arrays(snap, ("id", "region", "occupation", "civ_affinity"))
    if arrays is not None and isinstance(civ_idx, int):
        return _select_recruits_columnar(ctx, civ, civ_idx, taken, dist, count, *arrays)
    ids = pylist(snap.column("id"))
    regs = pylist(snap.column("region"))
    occs = pylist(snap.column("occupation"))
    affs = pylist(snap.column("civ_affinity"))
    candidates = []
    for aid, reg, occ, aff in zip(ids, regs, occs, affs):
        aid, reg, occ, aff = int(aid), int(reg), int(occ), int(aff)
        if aid in taken or aff != civ_idx or occ not in (SOLDIER_OCCUPATION, FARMER_OCCUPATION):
            continue
        if not 0 <= reg < len(regions):
            continue
        region = regions[reg]
        if region.controller != civ.name or region.occupied_by not in (None, civ.name):
            continue
        hops = dist.get(region.name)
        if hops is None:
            continue
        candidates.append((0 if occ == SOLDIER_OCCUPATION else 1, hops, aid, reg))
    candidates.sort()
    return [(aid, reg) for _, _, aid, reg in candidates[:count]]


def raise_army(ctx: WarContext, civ: "Civilization", war: "WarRecord", toward: str | None,
               *, reason: str = "mobilization") -> "Army | None":
    """Raise a field army for ``war`` at the own region closest to ``toward``."""
    from chronicler.models import Army
    world = ctx.world
    state = world.war_state
    if len(armies_of(world, civ.name)) >= P.MAX_ARMIES_PER_CIV:
        return None
    last = state.last_raise_turn.get(civ.name)
    if last is not None and world.turn - last < P.RAISE_COOLDOWN_TURNS:
        return None
    staging = staging_region(ctx, civ, toward)
    if staging is None:
        return None
    size = muster_capacity(world, civ)
    raise_cost_per_10 = get_override(world, P.K_RAISE_COST_PER_10, P.RAISE_COST_PER_10_SOLDIERS)
    affordable = (max(0, _treasury(ctx, civ)) * 10) // max(1, int(raise_cost_per_10))
    size = min(size, affordable)
    if size < P.MIN_ARMY:
        return None
    roster: list[tuple[int, int]] = []
    if ctx.agent_pool:
        roster = select_recruits(ctx, civ, staging, size)
        size = len(roster)
        if size < P.MIN_ARMY:
            return None
    spend(ctx, civ, max(1, size * int(raise_cost_per_10) // 10))
    serial = state.next_army_serial
    state.next_army_serial += 1
    state.last_raise_turn[civ.name] = world.turn
    morale = max(400, min(900, P.INITIAL_MORALE_BASE + 2 * civ.military + int(100 * (civ.asabiya - 0.5))))
    army = Army(
        army_id=f"army-{serial}",
        name=_army_name(ctx, civ),
        civ=civ.name,
        war_key=war.war_key,
        region=staging,
        home_region=staging,
        objective=None,
        phase="rally",
        soldiers=size,
        raised=size,
        morale=morale,
        rations=size * P.POLICY.carried_limit,
        roster=roster,
        raised_turn=world.turn,
    )
    army.general = pick_general(world, civ)
    state.armies.append(army)
    led = f", led by {army.general}" if army.general else ""
    emit(ctx, "army_raised", [civ.name, other_name(war, civ.name)],
         f"{civ.name} raises {army.name} ({size} soldiers) at {staging}{led}.", importance=4)
    return army


def other_name(war: "WarRecord", civ_name: str) -> str:
    return war.defender if civ_name == war.attacker else war.attacker


def _treasury(ctx: WarContext, civ: "Civilization") -> int:
    from chronicler.war.common import projected_treasury
    return projected_treasury(ctx, civ)


# --- generals ------------------------------------------------------------------

def pick_general(world, civ: "Civilization") -> str | None:
    used = {a.general for a in world.war_state.armies if a.civ == civ.name and a.general}
    for gp in sorted(civ.great_persons, key=lambda g: (g.born_turn, g.name)):
        if (gp.role == "general" and gp.active and gp.alive and not gp.is_hostage
                and gp.name not in used):
            return gp.name
    return None


def general_of(world, army: "Army") -> "GreatPerson | None":
    if army.general is None:
        return None
    civ = world.civ_map.get(army.civ)
    if civ is not None:
        for gp in civ.great_persons:
            if (gp.name == army.general and gp.role == "general" and gp.active
                    and gp.alive and not gp.is_hostage):
                return gp
    army.general = None
    return None


def refresh_generals(world) -> None:
    for army in world.war_state.armies:
        general_of(world, army)
        if army.general is None:
            civ = world.civ_map.get(army.civ)
            if civ is not None:
                army.general = pick_general(world, civ)


def kill_general(ctx: WarContext, army: "Army", region: str) -> str | None:
    """A general falls in battle. Agent-backed generals die natively."""
    from chronicler.great_persons import _append_deed
    gp = general_of(ctx.world, army)
    if gp is None:
        return None
    civ = ctx.world.civ_map[army.civ]
    _append_deed(gp, f"Fell in battle at {region}", region=region, turn=ctx.turn, civ=civ.name)
    army.general = None
    if ctx.agent_pool and gp.agent_id is not None:
        # The bridge's death processing retires the named character.
        queue_deaths(ctx, [gp.agent_id])
    else:
        gp.alive = False
        gp.active = False
        gp.fate = "dead"
        gp.death_turn = ctx.turn
        if gp in civ.great_persons:
            civ.great_persons.remove(gp)
        ctx.world.retired_persons.append(gp)
    emit(ctx, "general_fallen", [civ.name], f"{gp.name}, general of {civ.name}, falls at {region}.",
         importance=6, region=region)
    return gp.name


# --- casualties / desertion --------------------------------------------------------

def queue_deaths(ctx: WarContext, agent_ids: list[int]) -> None:
    if not agent_ids or ctx.bridge is None:
        return
    sim = getattr(ctx.bridge, "_sim", None)
    if sim is not None and hasattr(sim, "queue_targeted_deaths"):
        sim.queue_targeted_deaths(sorted(int(a) for a in agent_ids))


def drain_population(ctx: WarContext, region_names: list[str], amount: int) -> int:
    """Remove ``amount`` people across regions (civilian/militia deaths)."""
    if amount <= 0:
        return 0
    regions = [ctx.world.region_map[n] for n in region_names if n in ctx.world.region_map]
    regions = [r for r in regions if r.population > 0]
    if not regions:
        return 0
    drains = distribute_pop_loss(regions, amount)
    if getattr(ctx.world, "agent_mode", None) in ("demographics-only", "shadow", "hybrid"):
        for region, actual in zip(regions, drains):
            stage_region_catastrophe_deaths(region, actual)
    return sum(drains)


def apply_casualties(ctx: WarContext, army: "Army", count: int, *, cause: str) -> int:
    """Kill ``count`` soldiers of ``army``; returns the number killed."""
    count = max(0, min(int(count), army.soldiers))
    if count == 0:
        return 0
    if army.roster:
        rng = war_rng(ctx, "casualty", army.army_id, cause)
        pool = sorted(army.roster)
        victims = pool if count >= len(pool) else rng.sample(pool, count)
        dead = set(victims)
        army.roster = [entry for entry in army.roster if entry not in dead]
        queue_deaths(ctx, [aid for aid, _ in victims])
        for _, reg in victims:
            if 0 <= reg < len(ctx.world.regions):
                drain_region_pop(ctx.world.regions[reg], 1)
        count = len(victims)
    else:
        civ_regions = [r.name for r in ctx.world.regions if r.controller == army.civ]
        drain_population(ctx, civ_regions, count)
    army.soldiers -= count
    army.casualties += count
    if cause == "attrition":
        army.attrition += count
    # Kits of the fallen exceed what survivors can carry (M60a kit limit).
    army.rations = min(army.rations, army.soldiers * P.POLICY.carried_limit)
    return count


def release_soldiers(ctx: WarContext, army: "Army", count: int, *, cause: str = "desertion") -> int:
    """Soldiers leave the army alive (desertion or demobilization)."""
    count = max(0, min(int(count), army.soldiers))
    if count == 0:
        return 0
    if army.roster:
        rng = war_rng(ctx, "release", army.army_id, cause)
        pool = sorted(army.roster)
        leaving = set(pool if count >= len(pool) else rng.sample(pool, count))
        army.roster = [entry for entry in army.roster if entry not in leaving]
        count = len(leaving)
    army.soldiers -= count
    if cause == "desertion":
        army.deserted += count
    army.rations = min(army.rations, army.soldiers * P.POLICY.carried_limit)
    return count


def disband(ctx: WarContext, army: "Army", reason: str) -> None:
    state = ctx.world.war_state
    if army in state.armies:
        state.armies.remove(army)
    army.roster = []
    if reason == "destroyed":
        emit(ctx, "army_destroyed", [army.civ], f"{army.name} is destroyed at {army.region}.",
             importance=6, region=army.region)
    elif reason == "demobilized":
        emit(ctx, "army_disbanded", [army.civ],
             f"{army.name} returns home and disbands ({army.soldiers} survivors).", importance=3)


# --- native roster reconciliation ----------------------------------------------------

def reconcile_rosters(world, snapshot) -> int:
    """Drop roster agents no longer alive in the post-tick snapshot.

    Returns the number of soldiers removed by natural (non-campaign) deaths.
    Also refreshes each enlisted agent's region from the snapshot.
    """
    armies = [a for a in world.war_state.armies if a.roster]
    if not armies or snapshot is None:
        return 0
    arrays = batch_arrays(snapshot, ("id", "region"))
    if arrays is not None:
        # Only enlisted ids are looked up; the last row per id wins, as in
        # the full id -> region dict.
        rows = last_row_of(arrays[0], {aid for army in armies for aid, _ in army.roster})
        alive = {aid: int(arrays[1][row]) for aid, row in rows.items()}
    else:
        try:
            ids = pylist(snapshot.column("id"))
            regs = pylist(snapshot.column("region"))
        except Exception:
            return 0
        alive = {int(a): int(r) for a, r in zip(ids, regs)}
    removed = 0
    for army in armies:
        kept = [(aid, alive[aid]) for aid, _ in army.roster if aid in alive]
        lost = len(army.roster) - len(kept)
        if lost:
            army.casualties += lost
            removed += lost
        army.roster = kept
        army.soldiers = len(kept)
        army.rations = min(army.rations, army.soldiers * P.POLICY.carried_limit)
    return removed


def rebind_rosters(ctx: WarContext) -> None:
    """Re-enlist rosters against a different native pool (e.g. after resume).

    Agent ids are pool-scoped; a fresh simulator invalidates every stored id.
    Each army keeps its strength by drafting the same head count anew.
    """
    world = ctx.world
    sim = getattr(ctx.bridge, "_sim", None) if ctx.bridge is not None else None
    marker = id(sim) if sim is not None else None
    if getattr(world, "_war_roster_sim", "unset") == marker:
        return
    world._war_roster_sim = marker
    if not ctx.agent_pool:
        for army in world.war_state.armies:
            army.roster = []
        return
    try:
        snap = ctx.bridge.get_snapshot()
        live = {int(a) for a in pylist(snap.column("id"))}
    except Exception:
        live = set()
    for army in sorted(world.war_state.armies, key=lambda a: a.army_id):
        if army.roster and all(aid in live for aid, _ in army.roster):
            continue
        civ = world.civ_map.get(army.civ)
        army.roster = []
        if civ is None:
            continue
        staging = army.home_region if army.home_region in world.region_map else army.region
        army.roster = select_recruits(ctx, civ, staging, army.soldiers)
        army.soldiers = len(army.roster)
