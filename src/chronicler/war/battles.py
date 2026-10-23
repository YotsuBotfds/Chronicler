"""M60b battles and sieges, resolved deterministically with namespaced seeds.

Power = soldiers x quality, where quality multiplies tech era, morale,
supply, asabiya, martial tradition and the commanding general. The side that
holds the ground multiplies its power by terrain/role defense, rivers,
fortifications (scaled by the era fortification bonus) and home ground. Both
sides draw a bounded noise factor from ``war_rng("battle", ...)``. Casualties
follow the power ratio; losers retreat, broken armies are destroyed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from chronicler.models import InfrastructureType, TechEra
from chronicler.named_events import deduplicate_name, generate_battle_name
from chronicler.tuning import K_FORT_DEFENSE_BONUS, get_override
from chronicler.war import params as P
from chronicler.war.armies import (
    apply_casualties, disband, drain_population, general_of, kill_general, release_soldiers,
)
from chronicler.war.common import (
    WarContext, add_stat, emit, holds, name_event, war_rng,
)

if TYPE_CHECKING:
    from chronicler.models import Army, Civilization, Region, WarRecord

_ERAS = list(TechEra)
_ATTACK_TRAITS = {"aggressive", "bold", "ambitious", "zealous"}
_DEFENSE_TRAITS = {"cautious", "stubborn"}
_SHREWD_TRAITS = {"shrewd", "calculating", "visionary"}


def era_index(era: TechEra) -> int:
    return _ERAS.index(era)


def commander_bonus(trait: str | None, attacking: bool) -> float:
    if trait is None:
        return 0.0
    bonus = P.COMMANDER_BASE
    if attacking and trait in _ATTACK_TRAITS:
        bonus += 0.10
    elif not attacking and trait in _DEFENSE_TRAITS:
        bonus += 0.10
    elif trait in _SHREWD_TRAITS:
        bonus += 0.05
    return bonus


def quality(civ: "Civilization", morale: int, *, fed: bool = True,
            general_trait: str | None = None, attacking: bool = True) -> float:
    q = 1.0 + P.ERA_QUALITY_STEP * era_index(civ.tech_era)
    q *= 0.5 + max(0, min(1000, morale)) / 1000.0
    q *= 1.0 if fed else 0.8
    q *= 0.75 + 0.5 * max(0.0, min(1.0, civ.asabiya))
    if "martial" in civ.traditions:
        q *= 1.10
    q *= 1.0 + commander_bonus(general_trait, attacking)
    return q


def army_power(ctx: WarContext, civ: "Civilization", army: "Army", *, attacking: bool = True) -> float:
    gp = general_of(ctx.world, army)
    fed = army.rations > 0
    return army.soldiers * quality(civ, army.morale, fed=fed,
                                   general_trait=gp.trait if gp else None, attacking=attacking)


def garrison_size(world, region: "Region", owner: "Civilization | None") -> int:
    militia = region.population * P.GARRISON_PERMILLE // 1000
    if owner is not None:
        militia += owner.military // 10
    return max(P.MIN_GARRISON, militia)


def defense_multiplier(world, region: "Region", defender_name: str, *, fort_weight: float = 1.0) -> float:
    from chronicler.tech import get_era_bonus
    from chronicler.terrain import total_defense_bonus
    bonus = total_defense_bonus(region) / 100.0
    if region.river_mask:
        bonus += P.RIVER_DEFENSE
    if any(i.type == InfrastructureType.FORTIFICATIONS and i.active for i in region.infrastructure):
        owner = world.civ_map.get(region.controller) if region.controller else None
        era_mult = get_era_bonus(owner.tech_era, "fortification_multiplier", 1.0) if owner else 1.0
        bonus += get_override(world, K_FORT_DEFENSE_BONUS, 15) / 100.0 * max(1.0, era_mult) * fort_weight
    if region.controller == defender_name:
        bonus += P.HOME_GROUND_DEFENSE
    return max(0.7, 1.0 + bonus)


def merc_strength(world, civ_name: str) -> int:
    """Hired mercenary strength in military-stat points."""
    return sum(int(m.get("strength", 0)) for m in world.mercenary_companies
               if m.get("hired_by") == civ_name and m.get("strength", 0) > 0)


def merc_soldiers(world, civ: "Civilization", army: "Army") -> int:
    """Mercenary head count marching with ``army``.

    Company strength is in military-stat points; it converts to soldiers in
    proportion to the army's own muster per point of the hirer's military.
    """
    points = merc_strength(world, civ.name)
    if points <= 0:
        return 0
    return max(1, army.raised * points // max(10, civ.military))


def lead_army(world, civ_name: str) -> "Army | None":
    """The civ's largest army (mercenaries march with it)."""
    armies = [a for a in world.war_state.armies if a.civ == civ_name and a.soldiers > 0]
    if not armies:
        return None
    return max(armies, key=lambda a: (a.soldiers, -int(a.army_id.split("-")[-1])))


@dataclass
class Side:
    civ: "Civilization"
    armies: list = field(default_factory=list)
    garrison: int = 0
    mercs: int = 0

    @property
    def soldiers(self) -> int:
        return sum(a.soldiers for a in self.armies) + self.garrison + self.mercs


def _side_power(ctx: WarContext, side: Side, enemy: "Civilization", attacking: bool) -> float:
    from chronicler.tech import tech_war_multiplier
    power = sum(army_power(ctx, side.civ, a, attacking=attacking) for a in side.armies)
    if side.mercs:
        power += side.mercs * quality(side.civ, 650, attacking=attacking)
    if side.garrison:
        power += side.garrison * quality(side.civ, 600, attacking=attacking)
    return power * tech_war_multiplier(side.civ.tech_era, enemy.tech_era)


def _split(total: int, weights: list[int]) -> list[int]:
    """Largest-remainder split of ``total`` across nonnegative weights."""
    s = sum(weights)
    if total <= 0 or s <= 0:
        return [0] * len(weights)
    raw = [total * w / s for w in weights]
    base = [int(x) for x in raw]
    rem = total - sum(base)
    order = sorted(range(len(weights)), key=lambda i: (-(raw[i] - base[i]), i))
    for i in order[:rem]:
        base[i] += 1
    return [min(b, w) for b, w in zip(base, weights)]


def _apply_side_losses(ctx: WarContext, side: Side, losses: int, region: "Region", cause: str) -> int:
    parts = [a.soldiers for a in side.armies] + [side.mercs, side.garrison]
    shares = _split(losses, parts)
    killed = 0
    for army, share in zip(side.armies, shares):
        killed += apply_casualties(ctx, army, share, cause=cause)
    merc_loss = shares[len(side.armies)]
    if merc_loss and side.mercs:
        killed += merc_loss
        # Companies lose strength points in proportion to head count lost.
        points = merc_strength(ctx.world, side.civ.name)
        remaining = -(-points * merc_loss // max(1, side.mercs))
        side.mercs -= merc_loss
        for merc in ctx.world.mercenary_companies:
            if merc.get("hired_by") == side.civ.name and remaining > 0:
                take = min(int(merc["strength"]), remaining)
                merc["strength"] -= take
                remaining -= take
    garrison_loss = shares[-1]
    if garrison_loss:
        side.garrison -= garrison_loss
        killed += drain_population(ctx, [region.name], garrison_loss)
    return killed


def _retreat(ctx: WarContext, army: "Army") -> None:
    """Fall back one edge toward held territory; trapped armies bleed."""
    world = ctx.world
    here = ctx.index.get(army.region)
    if here is None:
        return
    enemy_regions = {a.region for a in world.war_state.armies if a.civ != army.civ}
    options = []
    for nb in ctx.graph[here]:
        region = world.regions[nb]
        if region.name in enemy_regions:
            continue
        rank = 0 if holds(region, army.civ) else 1
        options.append((rank, nb))
    army.phase = "regrouping"
    army.siege_turns = 0
    army.move_progress = 0
    if options:
        army.region = world.regions[min(options)[1]].name
    else:
        apply_casualties(ctx, army, max(1, army.soldiers // 5), cause="trapped")


def fight(ctx: WarContext, war: "WarRecord", region: "Region", attacker: Side, defender: Side,
          *, kind: str, fort_weight: float = 1.0) -> str | None:
    """Resolve one engagement. Returns the winning civ name, or None on stalemate."""
    world = ctx.world
    a_n, d_n = attacker.soldiers, defender.soldiers
    if a_n <= 0 or d_n <= 0:
        return attacker.civ.name if d_n <= 0 < a_n else None
    rng = war_rng(ctx, "battle", war.war_key, region.name, kind, attacker.civ.name)
    a_pow = _side_power(ctx, attacker, defender.civ, True) * rng.uniform(0.85, 1.15)
    d_pow = (_side_power(ctx, defender, attacker.civ, False)
             * defense_multiplier(world, region, defender.civ.name, fort_weight=fort_weight)
             * rng.uniform(0.85, 1.15))
    ratio = a_pow / max(d_pow, 1e-9)
    scale = get_override(world, P.K_BATTLE_CASUALTY_SCALE, 1.0)
    if ratio >= P.DECISIVE_RATIO:
        winner, loser, r = attacker, defender, ratio
    elif ratio <= 1.0 / P.DECISIVE_RATIO:
        winner, loser, r = defender, attacker, 1.0 / ratio
    else:
        winner = loser = None
        r = 1.0
    if winner is None:
        a_rate = d_rate = 0.10
    else:
        loser_rate = min(0.6, 0.18 + 0.12 * (r - 1.0))
        winner_rate = max(0.04, 0.14 - 0.04 * (r - 1.0))
        a_rate, d_rate = (winner_rate, loser_rate) if winner is attacker else (loser_rate, winner_rate)
    a_loss = int(round(a_n * a_rate * rng.uniform(0.8, 1.2) * scale))
    d_loss = int(round(d_n * d_rate * rng.uniform(0.8, 1.2) * scale))
    a_gen = attacker.armies and general_of(world, attacker.armies[0])
    d_gen = defender.armies and general_of(world, defender.armies[0])
    a_killed = _apply_side_losses(ctx, attacker, a_loss, region, "battle")
    d_killed = _apply_side_losses(ctx, defender, d_loss, region, "battle")

    outcome = ("attacker_wins" if winner is attacker else "defender_wins" if winner is defender
               else "stalemate")
    if kind == "assault":
        name = deduplicate_name(f"The Siege of {region.name}", [ne.name for ne in world.named_events])
    elif kind == "skirmish":
        name = f"The Fight for {region.name}"
    else:
        name = generate_battle_name(region.name, attacker.civ.tech_era, world, seed=world.seed)
    from chronicler.models import BattleRecord
    world.war_state.battles.append(BattleRecord(
        turn=world.turn, name=name, kind=kind, region=region.name, war_key=war.war_key,
        attacker=attacker.civ.name, defender=defender.civ.name,
        attacker_soldiers=a_n, defender_soldiers=d_n,
        attacker_power=int(round(a_pow * 10)), defender_power=int(round(d_pow * 10)),
        attacker_losses=a_killed, defender_losses=d_killed,
        winner=winner.civ.name if winner else None,
        attacker_general=a_gen.name if a_gen else None,
        defender_general=d_gen.name if d_gen else None,
    ))
    lead = f"; {a_gen.name} commands" if a_gen else ""
    emit(ctx, "war", [attacker.civ.name, defender.civ.name],
         f"{name}: {attacker.civ.name} ({a_n}) vs {defender.civ.name} ({d_n}) at {region.name}: "
         f"{outcome}. Losses {a_killed}/{d_killed}{lead}.",
         importance=7 if kind in ("field", "assault") else 5)
    if kind in ("field", "assault"):
        name_event(ctx, name, "battle", [attacker.civ.name, defender.civ.name], region.name,
                   f"{attacker.civ.name} vs {defender.civ.name}: {outcome}", 7 if kind == "field" else 6)
    region._war_won_this_turn = True
    ctx.battle_regions.add(region.name)

    # War bookkeeping.
    war.battles += 1
    war.last_combat_turn = world.turn
    for side, killed in ((attacker, a_killed), (defender, d_killed)):
        if side.civ.name == war.attacker:
            war.attacker_losses += killed
        else:
            war.defender_losses += killed
        engaged = max(1, side.soldiers + killed)
        side.civ.war_weariness += P.BATTLE_WEARINESS + P.LOSS_WEARINESS * killed / engaged
        enlisted = max(1, sum(a.soldiers for a in world.war_state.armies if a.civ == side.civ.name) + killed)
        ctx.military_loss[side.civ.name] = (ctx.military_loss.get(side.civ.name, 0.0)
                                            + P.MIL_LOSS_BATTLE_SCALE * killed / enlisted)
    if winner is not None:
        loser_killed = d_killed if loser is defender else a_killed
        points = P.BATTLE_POINTS_BASE + int(P.BATTLE_POINTS_SCALE * loser_killed / max(1, loser.soldiers + loser_killed))
        war.battle_points += points if winner.civ.name == war.attacker else -points
        from chronicler.emergence import get_severity_multiplier
        add_stat(ctx, loser.civ, "stability", -int(3 * get_severity_multiplier(loser.civ, world)), "guard-shock")
        for army in winner.armies:
            army.morale = min(1000, army.morale + P.BATTLE_MORALE_WIN)
            army.battles_won += 1
            army.last_combat_turn = world.turn
        for army in loser.armies:
            army.morale = max(0, army.morale - P.BATTLE_MORALE_LOSS)
            army.battles_lost += 1
            army.last_combat_turn = world.turn
        _general_fate(ctx, loser, region, rng, P.GENERAL_DEATH_CHANCE)
        _general_fate(ctx, winner, region, rng, P.GENERAL_DEATH_CHANCE / 4)
        _intelligence_failure(ctx, attacker, defender, winner)
        from chronicler.leaders import update_rivalries
        update_rivalries(attacker.civ, defender.civ, world)
    else:
        for army in attacker.armies + defender.armies:
            army.morale = max(0, army.morale - 50)
            army.last_combat_turn = world.turn

    # Broken armies: destroyed outright, otherwise losers fall back.
    for side in (attacker, defender):
        for army in list(side.armies):
            if army.soldiers < P.MIN_ARMY:
                _destroy(ctx, army, side, winner, region, rng)
            elif side is loser and kind in ("field", "skirmish", "assault"):
                if kind != "assault" or side is attacker:
                    _retreat(ctx, army)
    return winner.civ.name if winner else None


def _general_fate(ctx: WarContext, side: Side, region: "Region", rng, chance: float) -> None:
    for army in side.armies:
        if army.general and rng.random() < chance:
            kill_general(ctx, army, region.name)


def _intelligence_failure(ctx: WarContext, attacker: Side, defender: Side, winner: Side | None) -> None:
    if winner is not defender or not attacker.armies:
        return
    from chronicler.intelligence import emit_intelligence_failure, get_perceived_stat
    perceived = get_perceived_stat(attacker.civ, defender.civ, "military", ctx.world)
    if perceived is not None and perceived <= 0.7 * defender.civ.military:
        ctx.events.append(emit_intelligence_failure(
            attacker.civ, defender.civ, perceived, defender.civ.military, ctx.world))


def _destroy(ctx: WarContext, army: "Army", side: Side, winner: Side | None, region: "Region", rng) -> None:
    world = ctx.world
    if army.general and rng.random() < 0.5:
        kill_general(ctx, army, region.name)
    if army.soldiers > 0:
        # Survivors of a broken army scatter home alive.
        release_soldiers(ctx, army, army.soldiers, cause="scattered")
    side.armies.remove(army)
    disband(ctx, army, "destroyed")
    if winner is not None and winner is not side:
        from chronicler.relationships import capture_hostage
        hostage = capture_hostage(side.civ, winner.civ, world, contested_region=region.name,
                                  bridge=ctx.bridge)
        if hostage:
            emit(ctx, "hostage_taken", [winner.civ.name, side.civ.name],
                 f"{winner.civ.name} takes {hostage.name} hostage from {side.civ.name}.", importance=6)


# --- sieges -------------------------------------------------------------------------

def siege_required(world, region: "Region", owner: "Civilization | None", ratio: float) -> int:
    from chronicler.tech import get_era_bonus
    turns = P.SIEGE_BASE_TURNS
    if any(i.type == InfrastructureType.FORTIFICATIONS and i.active for i in region.infrastructure):
        era_mult = get_era_bonus(owner.tech_era, "fortification_multiplier", 1.0) if owner else 1.0
        turns += 2 + (1 if era_mult >= 2.0 else 0)
    if owner is not None and owner.capital_region == region.name:
        turns += 1
    if any(s.status.value in ("active", "dissolving") for s in region.settlements):
        turns += 1
    if ratio >= 2.5:
        turns -= 1
    return max(1, turns)


def siege_turn(ctx: WarContext, war: "WarRecord", region: "Region", armies: list["Army"],
               besieger: "Civilization", owner: "Civilization") -> bool:
    """Advance a siege; returns True when the region falls this turn."""
    world = ctx.world
    garrison = garrison_size(world, region, owner)
    besiegers = Side(besieger, list(armies))
    defenders = Side(owner, [], garrison=garrison)
    ratio = (_side_power(ctx, besiegers, owner, True)
             / max(1e-9, _side_power(ctx, defenders, besieger, False)
                   * defense_multiplier(world, region, owner.name)))
    required = siege_required(world, region, owner, ratio)
    lead = armies[0]
    first = lead.siege_turns == 0
    for army in armies:
        army.phase = "sieging"
        army.siege_turns += 1
    if first:
        emit(ctx, "siege_begun", [besieger.name, owner.name],
             f"{lead.name} lays siege to {region.name} ({required} turns to breach).", importance=5)
    drain_population(ctx, [region.name], region.population * P.SIEGE_CIVILIAN_LOSS_PERMILLE // 1000)
    from chronicler.war.occupation import _requisition
    _requisition(region, 0.85)
    if lead.siege_turns < required:
        return False
    winner = fight(ctx, war, region, besiegers, defenders, kind="assault", fort_weight=0.5)
    if winner == besieger.name:
        war.battle_points += P.SIEGE_POINTS if besieger.name == war.attacker else -P.SIEGE_POINTS
        return True
    for army in besiegers.armies:
        army.siege_turns = max(0, required - 2)
    return False


def skirmish(ctx: WarContext, war: "WarRecord", region: "Region", armies: list["Army"],
             invader: "Civilization", holder: "Civilization", garrison: int) -> bool:
    """Fight a region's militia/occupation garrison; True when the invader wins."""
    winner = fight(ctx, war, region, Side(invader, list(armies)), Side(holder, [], garrison=garrison),
                   kind="skirmish")
    return winner == invader.name


def side_for(world, civ: "Civilization", armies: list["Army"]) -> Side:
    side = Side(civ, list(armies))
    lead = lead_army(world, civ.name)
    if lead is not None and lead in armies:
        side.mercs = merc_soldiers(world, civ, lead)
    return side
