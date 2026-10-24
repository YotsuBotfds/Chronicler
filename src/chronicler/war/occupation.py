"""M60b occupation: controller (legal owner) versus occupier.

An occupied region keeps ``Region.controller`` as its owner, so production,
politics and the native pool keep their ownership semantics. The occupier is
``Region.occupied_by`` plus an ``Occupation`` record carrying unrest. Each
turn occupation costs the owner taxes and stability, feeds the occupier small
requisitions, and accumulates unrest that can erupt into revolt. A long,
quiet occupation is annexed; revolts, relief armies or peace liberate it.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from chronicler.named_events import deduplicate_name
from chronicler.tuning import get_override
from chronicler.war import params as P
from chronicler.war.armies import apply_casualties, drain_population
from chronicler.war.common import (
    WarContext, add_stat, emit, living_civ, name_event, spend, war_for, war_rng,
)
from chronicler.diplomacy_state import diplomacy_on as _diplomacy_on

if TYPE_CHECKING:
    from chronicler.models import Army, Civilization, Occupation, Region, WarRecord

FOOD_REQUISITION = 0.8


def occupation_of(world, region_name: str) -> "Occupation | None":
    for occ in world.war_state.occupations:
        if occ.region == region_name:
            return occ
    return None


def _requisition(region: "Region", factor: float) -> None:
    from chronicler.economy import FOOD_GOODS
    for good in FOOD_GOODS:
        if good in region.stockpile.goods:
            region.stockpile.goods[good] *= factor


def start_occupation(ctx: WarContext, region: "Region", occupier: "Civilization",
                     war: "WarRecord", army: "Army | None") -> "Occupation":
    from chronicler.models import Occupation
    world = ctx.world
    owner_name = region.controller
    owner = world.civ_map.get(owner_name) if owner_name else None
    existing = occupation_of(world, region.name)
    if existing is not None:
        world.war_state.occupations.remove(existing)
    unrest = 150 + (3 * P.UNREST_CULTURE if region.cultural_identity not in (None, occupier.name) else 0)
    occ = Occupation(region=region.name, owner=owner_name or "", occupier=occupier.name,
                     war_key=war.war_key, since_turn=world.turn, unrest=min(1000, unrest))
    world.war_state.occupations.append(occ)
    region.occupied_by = occupier.name
    region._war_won_this_turn = True
    _requisition(region, FOOD_REQUISITION)
    plunder = region.population // 10
    if plunder:
        add_stat(ctx, occupier, "treasury", plunder, "keep")
    is_capital = owner is not None and owner.capital_region == region.name
    if owner is not None and is_capital:
        from chronicler.emergence import get_severity_multiplier
        add_stat(ctx, owner, "stability", -int(8 * get_severity_multiplier(owner, world)), "guard-shock")
    if owner is not None:
        # The sack: anchored treasures may be burned, a capital's portable
        # treasures are carried off (artifacts._process_sack, end of turn).
        from chronicler.artifacts import OCCUPATION_SACK_ACTION, emit_conquest_lifecycle_intent
        emit_conquest_lifecycle_intent(
            world, losing_civ=owner.name, gaining_civ=occupier.name, region=region.name,
            is_capital=is_capital, is_destructive=True, action=OCCUPATION_SACK_ACTION,
        )
    by = f" by {army.name}" if army is not None else ""
    emit(ctx, "occupation", [occupier.name, owner_name or ""],
         f"{region.name}{' (capital of ' + owner_name + ')' if is_capital else ''} is occupied{by}.",
         importance=8 if is_capital else 6, region=region.name)
    title = deduplicate_name(f"The Fall of {region.name}" if is_capital else f"The Occupation of {region.name}",
                             [ne.name for ne in world.named_events])
    name_event(ctx, title, "occupation", [occupier.name, owner_name or ""], region.name,
               f"{occupier.name} occupies {region.name}, held by {owner_name}", 7 if is_capital else 5)
    return occ


def end_occupation(ctx: WarContext, occ: "Occupation", reason: str) -> None:
    world = ctx.world
    if occ in world.war_state.occupations:
        world.war_state.occupations.remove(occ)
    region = world.region_map.get(occ.region)
    if region is not None and region.occupied_by == occ.occupier:
        region.occupied_by = None
    if reason in ("liberated", "revolt", "treaty_returned", "war_ended", "occupier_collapsed"):
        verb = {
            "liberated": "is liberated",
            "revolt": "rises and throws off its occupiers",
            "treaty_returned": "is returned by treaty",
            "war_ended": "is evacuated as the war ends",
            "occupier_collapsed": "is freed as its occupier collapses",
        }[reason]
        emit(ctx, "liberation" if reason != "revolt" else "occupation_revolt",
             [occ.owner, occ.occupier], f"{occ.region} {verb} ({occ.occupier} withdraws).",
             importance=6 if reason in ("liberated", "revolt") else 4, region=occ.region)


def annex_occupation(ctx: WarContext, occ: "Occupation", reason: str) -> bool:
    """Convert an occupation into ownership through the shared conquest path."""
    from chronicler.action_engine import apply_region_conquest
    from chronicler.utils import stable_hash_int
    world = ctx.world
    region = world.region_map.get(occ.region)
    occupier = living_civ(world, occ.occupier)
    if occ in world.war_state.occupations:
        world.war_state.occupations.remove(occ)
    if region is None or occupier is None:
        return False
    region.occupied_by = None
    owner = world.civ_map.get(region.controller) if region.controller else None
    if owner is not None and owner.name != occupier.name and region.name in owner.regions:
        seed = stable_hash_int("war", "annex", world.seed, world.turn, region.name)
        apply_region_conquest(occupier, owner, region, world, seed)
    elif region.controller != occupier.name:
        region.controller = occupier.name
        if region.name not in occupier.regions:
            occupier.regions.append(region.name)
        if owner is not None:
            owner.regions = [r for r in owner.regions if r != region.name]
    world.invalidate_trade_route_cache()
    owner_name = owner.name if owner is not None else occ.owner
    how = {"treaty": "ceded by treaty", "consolidated": "annexed after a long occupation",
           "owner_gone": "annexed as its former rulers vanish"}.get(reason, "annexed")
    annexation = emit(ctx, "annexation", [occupier.name, owner_name],
                      f"{region.name} is {how} to {occupier.name}.", importance=7, region=region.name)
    title = deduplicate_name(f"The Annexation of {region.name}", [ne.name for ne in world.named_events])
    name_event(ctx, title, "conquest", [occupier.name, owner_name], region.name,
               f"{region.name} passes from {owner_name} to {occupier.name} ({reason})", 7)
    if owner is not None and not owner.regions:
        emit(ctx, "civ_conquered", [occupier.name, owner.name],
             f"{owner.name} is extinguished; its last land falls to {occupier.name}.", importance=9,
             region=region.name, causes=[annexation.event_id])
    return True


def _garrison(world, occ: "Occupation") -> list["Army"]:
    return [a for a in world.war_state.armies
            if a.civ == occ.occupier and a.region == occ.region and a.soldiers > 0]


def tick_occupations(ctx: WarContext) -> None:
    world = ctx.world
    from chronicler.emergence import get_severity_multiplier
    annex_turns = int(get_override(world, P.K_ANNEX_TURNS, P.ANNEX_TURNS))
    revolt_threshold = int(get_override(world, P.K_REVOLT_THRESHOLD, P.REVOLT_THRESHOLD))
    proxy_targets = {pw.target_civ for pw in world.proxy_wars}
    for occ in sorted(list(world.war_state.occupations), key=lambda o: ctx.index.get(o.region, 1 << 30)):
        if occ not in world.war_state.occupations:
            continue
        region = world.region_map.get(occ.region)
        if region is None:
            world.war_state.occupations.remove(occ)
            continue
        occupier = living_civ(world, occ.occupier)
        if occupier is None:
            end_occupation(ctx, occ, "occupier_collapsed")
            continue
        if region.controller != occ.owner:
            # Ownership changed underneath (secession, politics, treaty).
            if occ in world.war_state.occupations:
                world.war_state.occupations.remove(occ)
            if region.occupied_by == occ.occupier:
                region.occupied_by = None
            continue
        owner = living_civ(world, occ.owner)
        if owner is None:
            annex_occupation(ctx, occ, "owner_gone")
            continue
        if war_for(world, occ.war_key) is None:
            end_occupation(ctx, occ, "war_ended")
            continue
        garrison = _garrison(world, occ)
        soldiers = sum(a.soldiers for a in garrison)
        delta = P.UNREST_BASE
        if region.cultural_identity not in (None, occ.occupier):
            delta += P.UNREST_CULTURE
        if occ.occupier in proxy_targets:
            delta += P.UNREST_PROXY
        delta -= min(P.UNREST_GARRISON_CAP, soldiers * P.UNREST_PER_SOLDIER)
        occ.unrest = max(0, min(1000, occ.unrest + delta))
        # Economic effects: lost taxes, requisitions, stability.
        spend(ctx, owner, P.OCC_TAX_LOSS)
        add_stat(ctx, occupier, "treasury", P.OCC_REQUISITION, "keep")
        add_stat(ctx, owner, "stability", -max(1, int(get_severity_multiplier(owner, world))), "signal")
        owner.war_weariness += P.OCCUPATION_WEARINESS
        if occ.unrest >= P.UNREST_DEPOPULATION and region.population > 2:
            drain_population(ctx, [region.name], max(1, region.population // 100))
        # Resistance.
        if occ.unrest >= revolt_threshold:
            rng = war_rng(ctx, "revolt", occ.region)
            chance = (occ.unrest - (revolt_threshold - 100)) / 2000.0
            if rng.random() < chance:
                _revolt(ctx, occ, region, owner, occupier, garrison, rng)
                continue
        # Consolidation.
        if (world.turn - occ.since_turn >= annex_turns and occ.unrest < P.ANNEX_MAX_UNREST
                and soldiers > 0 and not _ladder_holds_last_region(world, occ, owner, occupier)):
            annex_occupation(ctx, occ, "consolidated")


def _ladder_holds_last_region(world, occ, owner, occupier) -> bool:
    """Diplomacy ladder: a state's last region is not annexed by consolidation;
    the war's peace decides (a capitulation makes the state a vassal)."""
    if not _diplomacy_on(world) or owner.regions != [occ.region]:
        return False
    from chronicler.diplomacy import spares_last_region
    return spares_last_region(world, occupier, owner)


def _revolt(ctx: WarContext, occ, region, owner, occupier, garrison, rng) -> None:
    from chronicler.terrain import total_defense_bonus
    from chronicler.war.battles import army_power
    occ.revolts += 1
    partisans = max(2, region.population * occ.unrest // 5000)
    partisan_power = partisans * (1.0 + max(0, total_defense_bonus(region)) / 100.0) * rng.uniform(0.8, 1.2)
    if garrison:
        garrison_power = sum(army_power(ctx, occupier, a) for a in garrison)
    else:
        garrison_power = P.MIN_GARRISON * 1.0
    world = ctx.world
    if partisan_power > garrison_power:
        for army in garrison:
            apply_casualties(ctx, army, max(1, army.soldiers * 15 // 100), cause="revolt")
            army.morale = max(0, army.morale - P.BATTLE_MORALE_LOSS)
            army.phase = "regrouping"
            army.siege_turns = 0
        war = war_for(world, occ.war_key)
        if war is not None:
            war.battle_points += P.SIEGE_POINTS if occ.owner == war.attacker else -P.SIEGE_POINTS
        end_occupation(ctx, occ, "revolt")
        title = deduplicate_name(f"The {region.name} Uprising", [ne.name for ne in world.named_events])
        name_event(ctx, title, "uprising", [owner.name, occupier.name], region.name,
                   f"The people of {region.name} rise against {occupier.name}", 6)
    else:
        killed = drain_population(ctx, [region.name], partisans)
        occ.unrest = max(0, occ.unrest - 300)
        for army in garrison:
            apply_casualties(ctx, army, partisans // (3 * len(garrison)), cause="revolt")
        emit(ctx, "occupation_revolt", [owner.name, occupier.name],
             f"A rising in {region.name} is crushed by {occupier.name} ({killed} dead).", importance=5,
             region=region.name)
