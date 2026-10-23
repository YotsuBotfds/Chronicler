"""M60a production logistics: the detached kernel's tick, per army cohort.

Frozen order per army (kernel ``ORDERING``): orders -> replenish -> consume ->
stress -> desert -> move -> settle. Orders come from :mod:`chronicler.war.ai`;
movement and settlement happen in :func:`move_armies` after every army has
finished its logistics step, so stress uses start-of-turn locations exactly as
the kernel does.

Production inputs replace the kernel's explicit tick records:

* supply sources: regions the civ holds (owned and unoccupied, or occupied by
  it); distance uses the kernel's sorted-neighbor BFS;
* unmet needs: unpaid fraction of this turn's treasury upkeep;
* information quality: the civ's intelligence accuracy about its enemy;
* desertion draws: one namespaced RNG draw on the cohort's expected deserters.

Production extensions the kernel does not model: treasury upkeep, terrain
attrition deaths (with hunger, distance, winter and siege disease terms),
terrain movement cost, and foraging in non-friendly land.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from chronicler.campaign_logistics import next_morale, shortest_path, stress_components, supply_distance
from chronicler.tuning import get_override
from chronicler.war import params as P
from chronicler.war.armies import apply_casualties, general_of, release_soldiers
from chronicler.war.common import WarContext, bernoulli_round, holds, spend, war_for, war_rng

if TYPE_CHECKING:
    from chronicler.models import Army, Civilization

POLICY = P.POLICY
_SHREWD = {"shrewd", "calculating", "visionary"}


def supply_sources(ctx: WarContext, civ_name: str) -> tuple[int, ...]:
    return tuple(i for i, r in enumerate(ctx.world.regions) if holds(r, civ_name))


def upkeep_cost(world, army: "Army") -> int:
    per_10 = get_override(world, P.K_UPKEEP_PER_10, P.UPKEEP_PER_10_SOLDIERS)
    return -(-army.soldiers * int(per_10) // 10)  # ceiling


def _information_quality(ctx: WarContext, civ: "Civilization", army: "Army") -> int:
    from chronicler.intelligence import compute_accuracy
    war = war_for(ctx.world, army.war_key)
    if war is None:
        return 1000
    enemy = ctx.world.civ_map.get(war.defender if civ.name == war.attacker else war.attacker)
    if enemy is None:
        return 1000
    return max(0, min(1000, int(round(1000 * compute_accuracy(civ, enemy, ctx.world)))))


def logistics_step(ctx: WarContext, army: "Army", civ: "Civilization", sources: tuple[int, ...],
                   *, winter: bool) -> dict:
    """Upkeep, replenish, consume, stress, desert and attrition for one army."""
    world = ctx.world
    region = world.region_map[army.region]
    here = ctx.index[army.region]
    receipt: dict = {"army": army.army_id, "soldiers_before": army.soldiers, "morale_before": army.morale}

    # Upkeep -> unmet needs (kernel Condition.unmet_needs).
    cost = upkeep_cost(world, army)
    paid = spend(ctx, civ, cost)
    unmet = (cost - paid) * 1000 // cost if cost else 0
    army.unpaid_turns = army.unpaid_turns + 1 if unmet else 0

    # Replenish along the supply line, plus foraging off friendly land.
    distance = supply_distance(ctx.graph, here, sources)
    army.supply_distance = distance
    capacity = army.soldiers * POLICY.carried_limit
    refill = 0
    if distance is not None and distance in P.REFILL_BY_DISTANCE:
        refill = army.soldiers * POLICY.ration_demand * P.REFILL_BY_DISTANCE[distance]
        refill = refill * (1000 - unmet) // 1000
    forage = 0
    if not holds(region, civ.name):
        forage = (min(region.population // 5, army.soldiers) * POLICY.ration_demand
                  * P.FORAGE_BY_TERRAIN.get(region.terrain, 1) // 2)
    army.rations = min(capacity, army.rations + refill + forage)

    # Consume.
    demand = army.soldiers * POLICY.ration_demand
    consumed = min(army.rations, demand)
    army.rations -= consumed

    # Stress (kernel arithmetic, cohort demand).
    hunger, dist_stress, needs, info = stress_components(
        POLICY, demand=max(1, demand), consumed=consumed, distance=distance,
        unmet_needs=unmet, information_quality=_information_quality(ctx, civ, army))
    stress = hunger + dist_stress + needs + info
    army.morale = next_morale(POLICY, army.morale, stress)

    # Desert (kernel threshold/chance applied to the cohort's expectation).
    deserted = 0
    if army.morale <= POLICY.desertion_threshold and army.soldiers:
        rng = war_rng(ctx, "desert", army.army_id)
        expected = army.soldiers * POLICY.desertion_chance // 10  # thousandths of a soldier
        before = army.soldiers
        deserted = release_soldiers(ctx, army, bernoulli_round(expected, rng), cause="desertion")
        if deserted and before:
            army.rations -= army.rations * deserted // before

    # Attrition deaths by terrain, hunger, distance, winter and siege disease.
    permille = P.ATTRITION_PERMILLE.get(region.terrain, 3)
    gp = general_of(world, army)
    if gp is not None and gp.trait in _SHREWD:
        permille //= 2
    if consumed < demand:
        permille += P.HUNGER_ATTRITION_PERMILLE
    if distance is None:
        permille += P.UNREACHABLE_ATTRITION_PERMILLE
    elif distance > P.SUPPLY_RANGE:
        permille += P.DISTANCE_ATTRITION_PERMILLE * (distance - P.SUPPLY_RANGE)
    if winter and region.terrain in ("mountains", "tundra", "forest"):
        permille += P.WINTER_ATTRITION_PERMILLE
    if army.phase == "sieging":
        permille += P.SIEGE_DISEASE_PERMILLE
    rng = war_rng(ctx, "attrition", army.army_id)
    lost = apply_casualties(ctx, army, bernoulli_round(army.soldiers * permille, rng), cause="attrition")
    if lost:
        enlisted = max(1, sum(a.soldiers for a in world.war_state.armies if a.civ == civ.name) + lost)
        ctx.military_loss[civ.name] = (ctx.military_loss.get(civ.name, 0.0)
                                       + P.MIL_LOSS_ATTRITION_SCALE * lost / enlisted)
    receipt.update({
        "upkeep": cost, "paid": paid, "unmet_needs": unmet, "supply_distance": distance,
        "refill": refill, "forage": forage, "consumed": consumed, "demand": demand,
        "stress": (hunger, dist_stress, needs, info), "morale_after": army.morale,
        "deserted": deserted, "attrition": lost, "attrition_permille": permille,
    })
    return receipt


def move_armies(ctx: WarContext, armies: list["Army"]) -> None:
    """Move each army at most one legal edge toward its objective.

    Armies sharing a region with a hostile army are engaged and hold. An army
    entering a region that holds a hostile army stops there (a battle
    follows). Mountains and tundra cost two turns of marching.
    """
    from chronicler.war.common import at_war
    world = ctx.world
    for army in sorted(armies, key=lambda a: _serial(a)):
        if army not in world.war_state.armies or army.soldiers <= 0:
            continue
        if army.objective is None or army.objective == army.region:
            army.move_progress = 0
            continue
        if army.phase in ("sieging", "holding"):
            continue
        hostile_here = any(o.region == army.region and o.civ != army.civ and at_war(world, o.civ, army.civ)
                           for o in world.war_state.armies if o is not army and o.soldiers > 0)
        if hostile_here:
            continue
        if (army.morale < POLICY.movement_min_morale and army.phase not in ("returning", "regrouping")):
            continue
        path = shortest_path(ctx.graph, ctx.index[army.region], ctx.index[army.objective])
        if len(path) < 2:
            continue
        nxt = world.regions[path[1]]
        army.move_progress += 1
        if army.move_progress < P.MOVE_COST.get(nxt.terrain, 1):
            continue
        army.move_progress = 0
        army.region = nxt.name
        if army.phase == "rally":
            army.phase = "marching"


def _serial(army: "Army") -> int:
    try:
        return int(army.army_id.split("-")[-1])
    except ValueError:
        return 0


def run_logistics(ctx: WarContext) -> list[dict]:
    from chronicler.resources import get_season_id
    world = ctx.world
    winter = get_season_id(world.turn) == 3
    receipts = []
    source_cache: dict[str, tuple[int, ...]] = {}
    for army in sorted(list(world.war_state.armies), key=_serial):
        civ = world.civ_map.get(army.civ)
        if civ is None or army.soldiers <= 0 or army.region not in world.region_map:
            continue
        if army.civ not in source_cache:
            source_cache[army.civ] = supply_sources(ctx, army.civ)
        receipts.append(logistics_step(ctx, army, civ, source_cache[army.civ], winter=winter))
    return receipts
