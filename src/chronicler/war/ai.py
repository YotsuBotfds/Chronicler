"""Deterministic army orders: objectives per war aim, defense and regrouping.

Each turn every army gets an objective region and a phase. Choices depend
only on world state, sorted iteration and region-index tie breaks; no RNG.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from chronicler.war import params as P
from chronicler.war.common import (
    WarContext, at_war, distances_from, holds, living_civ, nearest, other_side, own_free_regions,
    war_for,
)

if TYPE_CHECKING:
    from chronicler.models import Army, Region, WarRecord


def region_value(world, region: "Region") -> int:
    value = region.population + region.carrying_capacity // 2
    owner = world.civ_map.get(region.controller) if region.controller else None
    if owner is not None and owner.capital_region == region.name:
        value += 30
    return value


def offensive_targets(ctx: WarContext, civ_name: str, enemy_name: str, war: "WarRecord") -> list[str]:
    """Enemy-owned regions this civ does not already hold, for this war's aim."""
    world = ctx.world
    pool = [r for r in world.regions if r.controller == enemy_name and r.occupied_by != civ_name]
    aim = war.aim if civ_name == war.attacker else "conquest"
    if aim == "liberation":
        cultural = [r for r in pool if r.cultural_identity == civ_name]
        pool = cultural or pool
    if aim == "vassalization":
        enemy = world.civ_map.get(enemy_name)
        capital = [r for r in pool if enemy is not None and r.name == enemy.capital_region]
        pool = capital or pool
    return [r.name for r in pool]


def pick_offensive_objective(ctx: WarContext, army: "Army", war: "WarRecord") -> str | None:
    enemy = other_side(war, army.civ)
    targets = offensive_targets(ctx, army.civ, enemy, war)
    if not targets:
        return None
    dist = distances_from(ctx, army.region)
    region_map = ctx.world.region_map
    preferred = war.aim_region if (army.civ == war.attacker and war.aim_region in targets) else None

    def key(name: str):
        d = dist.get(name, 10_000)
        bonus = 2 if name == preferred else 0
        return (d - bonus, -region_value(ctx.world, region_map[name]), ctx.index[name])

    reachable = [t for t in targets if t in dist]
    return min(reachable, key=key) if reachable else None


def _enemy_armies(world, civ_name: str) -> list["Army"]:
    return [a for a in world.war_state.armies
            if a.civ != civ_name and a.soldiers > 0 and at_war(world, a.civ, civ_name)]


def threat_regions(ctx: WarContext, civ_name: str) -> list[str]:
    """Regions with hostile armies inside or within THREAT_RANGE of own land."""
    world = ctx.world
    own = own_free_regions(world, civ_name) + [r.name for r in world.regions
                                               if r.controller == civ_name and r.occupied_by not in (None, civ_name)]
    if not own:
        return []
    threats = []
    for enemy in _enemy_armies(world, civ_name):
        dist = distances_from(ctx, enemy.region)
        if min((dist.get(n, 10_000) for n in own), default=10_000) <= P.THREAT_RANGE:
            threats.append(enemy.region)
    return sorted(set(threats), key=lambda n: ctx.index[n])


def assign_orders(ctx: WarContext, army: "Army") -> None:
    world = ctx.world
    war = war_for(world, army.war_key)
    home = _home(ctx, army)
    if war is None:
        army.phase = "returning"
        army.objective = home
        return
    enemy_name = other_side(war, army.civ)
    if living_civ(world, enemy_name) is None:
        army.phase = "returning"
        army.objective = home
        return
    region = world.region_map[army.region]

    # Regroup when broken; recover in friendly land.
    if army.phase == "regrouping":
        if army.morale >= P.REGROUP_RECOVERED_MORALE and holds(region, army.civ):
            army.phase = "marching"
        else:
            army.objective = home
            return
    if (army.morale < P.REGROUP_MORALE
            or army.soldiers < max(P.MIN_ARMY, int(army.raised * P.REGROUP_STRENGTH_FRACTION))):
        army.phase = "regrouping"
        army.siege_turns = 0
        army.objective = home
        return

    # Continue a siege in progress where we stand.
    if (army.phase == "sieging" and region.controller == enemy_name and region.occupied_by != army.civ):
        army.objective = army.region
        return
    if army.phase == "sieging":
        army.phase = "marching"
        army.siege_turns = 0

    # Liberate own occupied land first.
    occupied_own = [r.name for r in world.regions
                    if r.controller == army.civ and r.occupied_by == enemy_name]
    # Engage hostile armies threatening our land if we are not hopelessly weaker.
    threats = threat_regions(ctx, army.civ)
    my_power = army.soldiers * max(1, army.morale)
    engage = None
    if threats:
        dist = distances_from(ctx, army.region)
        best = None
        for name in threats:
            foes = [a for a in _enemy_armies(world, army.civ) if a.region == name]
            foe_power = sum(a.soldiers * max(1, a.morale) for a in foes)
            if foe_power and my_power < 0.6 * foe_power:
                continue
            key = (dist.get(name, 10_000), ctx.index[name])
            if best is None or key < best[0]:
                best = (key, name)
        engage = best[1] if best else None

    is_attacker = army.civ == war.attacker
    if engage is not None and (not is_attacker or distances_from(ctx, army.region).get(engage, 99) <= 1):
        army.objective = engage
    elif occupied_own:
        army.objective = nearest(ctx, army.region, occupied_own)
    elif is_attacker or _counteroffensive(world, war, army):
        army.objective = pick_offensive_objective(ctx, army, war) or _frontier(ctx, army, enemy_name)
    else:
        army.objective = _frontier(ctx, army, enemy_name)
    if army.phase in ("rally", "holding", "returning"):
        army.phase = "marching"
    if army.objective is None:
        army.objective = army.region


def _counteroffensive(world, war: "WarRecord", army: "Army") -> bool:
    """Defenders strike back once clearly winning the war."""
    return war.score <= -20 or army.battles_won >= 2


def _home(ctx: WarContext, army: "Army") -> str:
    world = ctx.world
    own = own_free_regions(world, army.civ)
    if army.home_region in own:
        if army.region in own:
            return army.region
        return nearest(ctx, army.region, own) or army.home_region
    return nearest(ctx, army.region, own) or army.region


def _frontier(ctx: WarContext, army: "Army", enemy_name: str) -> str:
    """Own region closest to the enemy's land: a defensive posting."""
    world = ctx.world
    own = own_free_regions(world, army.civ)
    if not own:
        return army.region
    enemy_land = [r.name for r in world.regions if r.controller == enemy_name]
    if not enemy_land:
        return army.region
    best = None
    for name in own:
        dist = distances_from(ctx, name)
        d = min((dist.get(e, 10_000) for e in enemy_land), default=10_000)
        key = (d, -world.region_map[name].population, ctx.index[name])
        if best is None or key < best[0]:
            best = (key, name)
    return best[1]
