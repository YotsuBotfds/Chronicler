"""Per-turn campaign orchestration (runs right after Phase 5 actions).

Order within :func:`tick_campaigns`:

1. reconcile WarRecords with ``world.active_wars``; drop dead armies;
2. rebind native rosters if the agent pool changed (resume);
3. threat-driven mobilization (defenders, and attackers whose land is hit);
4. orders for every army (``ai.assign_orders``);
5. M60a logistics per army (upkeep, supply, rations, morale, desertion,
   attrition) then movement;
6. field battles where hostile armies share a region;
7. sieges, skirmishes against garrisons, liberation of own land;
8. occupation upkeep, revolts and annexation;
9. war score and peace evaluation;
10. demobilization of returning armies; military-stat losses flushed.

All mutations route through the turn accumulator when one is supplied.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from chronicler.war import params as P
from chronicler.war.ai import assign_orders, threat_regions
from chronicler.war.armies import (
    can_raise, disband, raise_army, rebind_rosters, refresh_generals, release_soldiers,
)
from chronicler.war.battles import (
    garrison_size, side_for, siege_turn, skirmish, fight,
)
from chronicler.war.common import (
    WarContext, armies_of, at_war, build_context, flush_military_losses, holds, living_civ,
    other_side, spend, war_for,
)
from chronicler.war.logistics import move_armies, run_logistics
from chronicler.war.occupation import end_occupation, occupation_of, start_occupation, tick_occupations
from chronicler.war.peace import evaluate_peace, open_war, reconcile_wars, war_key

if TYPE_CHECKING:
    from chronicler.models import Army, Civilization, Event, WarRecord, WorldState


def _serial(army: "Army") -> int:
    try:
        return int(army.army_id.split("-")[-1])
    except ValueError:
        return 0


def _has_work(world: "WorldState") -> bool:
    state = world.war_state
    return bool(world.active_wars or state.wars or state.armies or state.occupations)


def tick_campaigns(world: "WorldState", acc=None, agent_bridge=None) -> list["Event"]:
    """Advance all campaigns one turn. Returns the events produced."""
    if not world.campaigns_enabled or not world.regions or not _has_work(world):
        return []
    ctx = build_context(world, acc, bridge=agent_bridge)
    reconcile_wars(ctx)
    _validate_armies(ctx)
    rebind_rosters(ctx)
    refresh_generals(world)
    _mobilize(ctx)
    for army in sorted(list(world.war_state.armies), key=_serial):
        assign_orders(ctx, army)
    run_logistics(ctx)
    _drop_empty(ctx)
    move_armies(ctx, list(world.war_state.armies))
    _field_battles(ctx)
    _sieges_and_liberation(ctx)
    tick_occupations(ctx)
    evaluate_peace(ctx)
    _demobilize(ctx)
    _drop_empty(ctx)
    flush_military_losses(ctx)
    _sync_occupied_flags(world)
    return ctx.events


# --- WAR action hook ----------------------------------------------------------------

def declare_or_press_war(civ: "Civilization", target: "Civilization", world: "WorldState",
                         acc=None) -> "Event":
    """Campaign replacement for instant WAR resolution.

    Declares war on ``target`` (or, if this civ already prosecutes an
    offensive war, presses that war instead of opening a second front) and
    raises or reinforces a field army for it.
    """
    from chronicler.models import Event
    from chronicler.politics import trigger_federation_defense
    from chronicler.tuning import K_WAR_ATTACKER_TREASURY_COST, get_override
    ctx = build_context(world, acc)
    reconcile_wars(ctx)
    war = None
    if at_war(world, civ.name, target.name):
        war = war_for(world, war_key(civ.name, target.name))
    if war is None:
        offensive = [w for w in world.war_state.wars
                     if w.attacker == civ.name and living_civ(world, w.defender) is not None]
        if offensive:
            war = sorted(offensive, key=lambda w: w.start_turn)[0]
            target = world.civ_map[war.defender]
    declared = False
    if war is None and _in_truce(world, civ.name, target.name):
        return Event(turn=world.turn, event_type="war", actors=[civ.name, target.name],
                     description=f"{civ.name} rattled sabres at {target.name} but honoured the truce.",
                     importance=3)
    if war is None and not can_raise(ctx, civ):
        # No army to march: the threat stays a threat (no phony war).
        return Event(turn=world.turn, event_type="war", actors=[civ.name, target.name],
                     description=f"{civ.name} threatened {target.name} but could not muster an army.",
                     importance=3)
    if war is None:
        world.active_wars.append((civ.name, target.name))
        world.war_start_turns.setdefault(war_key(civ.name, target.name), world.turn)
        world.invalidate_trade_route_cache()
        war = open_war(ctx, civ, target)
        spend(ctx, civ, int(get_override(world, K_WAR_ATTACKER_TREASURY_COST, 20)) // 2)
        world.events_timeline.extend(trigger_federation_defense(civ.name, target.name, world))
        from chronicler.leaders import update_rivalries
        update_rivalries(civ, target, world)
        declared = True
    enemy = other_side(war, civ.name)
    toward = _war_focus(ctx, civ.name, enemy, war)
    mine = [a for a in armies_of(world, civ.name) if a.war_key == war.war_key]
    raised = None
    if not mine or len(armies_of(world, civ.name)) < P.MAX_ARMIES_PER_CIV:
        raised = raise_army(ctx, civ, war, toward, reason="war_action")
    if raised is None:
        for army in mine:
            army.morale = min(1000, army.morale + 60)
    world.events_timeline.extend(ctx.events)
    flush_military_losses(ctx)
    if declared:
        desc = f"{civ.name} declared war on {enemy} ({war.aim}); campaign begins."
    elif raised is not None:
        desc = f"{civ.name} raised {raised.name} against {enemy}."
    else:
        desc = f"{civ.name} pressed its war against {enemy}."
    return Event(turn=world.turn, event_type="war", actors=[civ.name, enemy],
                 description=desc, importance=7 if declared else 5)


def _in_truce(world: "WorldState", a: str, b: str) -> bool:
    """A treaty between the pair within ``TRUCE_TURNS`` forbids a new war."""
    pair = {a, b}
    return any(set(t.parties) == pair and world.turn - t.turn < P.TRUCE_TURNS
               for t in world.war_state.treaties)


def _war_focus(ctx: WarContext, civ_name: str, enemy_name: str, war: "WarRecord") -> str | None:
    world = ctx.world
    if war.aim_region and war.aim_region in world.region_map and civ_name == war.attacker:
        return war.aim_region
    enemy = world.civ_map.get(enemy_name)
    if enemy is not None and enemy.regions:
        return enemy.capital_region if enemy.capital_region in enemy.regions else enemy.regions[0]
    return None


# --- phases -------------------------------------------------------------------------

def _validate_armies(ctx: WarContext) -> None:
    world = ctx.world
    for army in sorted(list(world.war_state.armies), key=_serial):
        civ = living_civ(world, army.civ)
        if civ is None or army.region not in world.region_map:
            if army in world.war_state.armies:
                world.war_state.armies.remove(army)
            continue
        if war_for(world, army.war_key) is None and army.phase != "returning":
            army.phase = "returning"
            army.siege_turns = 0


def _mobilize(ctx: WarContext) -> None:
    """Civs at war raise armies when hostile forces threaten their land."""
    world = ctx.world
    for war in sorted(world.war_state.wars, key=lambda w: w.war_key):
        for civ_name in (war.defender, war.attacker):
            civ = living_civ(world, civ_name)
            if civ is None:
                continue
            if any(a.war_key == war.war_key for a in armies_of(world, civ_name)):
                continue
            threats = threat_regions(ctx, civ_name)
            occupied = [r.name for r in world.regions
                        if r.controller == civ_name and r.occupied_by not in (None, civ_name)]
            if not threats and not occupied:
                continue
            toward = (occupied or threats)[0]
            raise_army(ctx, civ, war, toward, reason="defense")


def _drop_empty(ctx: WarContext) -> None:
    for army in sorted(list(ctx.world.war_state.armies), key=_serial):
        if army.soldiers < P.MIN_ARMY:
            if army.soldiers > 0:
                release_soldiers(ctx, army, army.soldiers, cause="scattered")
            disband(ctx, army, "destroyed" if army.casualties else "demobilized")


def _hostile_groups(ctx: WarContext) -> dict[str, dict[str, list["Army"]]]:
    groups: dict[str, dict[str, list["Army"]]] = {}
    for army in sorted(ctx.world.war_state.armies, key=_serial):
        if army.soldiers > 0:
            groups.setdefault(army.region, {}).setdefault(army.civ, []).append(army)
    return groups


def _field_battles(ctx: WarContext) -> None:
    world = ctx.world
    groups = _hostile_groups(ctx)
    for region_name in sorted(groups, key=lambda n: ctx.index[n]):
        by_civ = groups[region_name]
        civs = sorted(by_civ)
        fought = set()
        for i, a in enumerate(civs):
            for b in civs[i + 1:]:
                if not at_war(world, a, b) or a in fought or b in fought:
                    continue
                war = war_for(world, war_key(a, b))
                if war is None:
                    continue
                region = world.region_map[region_name]
                # The side holding the ground defends; else the war's defender.
                if holds(region, a) and not holds(region, b):
                    dfn, att = a, b
                elif holds(region, b) and not holds(region, a):
                    dfn, att = b, a
                else:
                    dfn = war.defender if war.defender in (a, b) else a
                    att = b if dfn == a else a
                att_armies = [x for x in by_civ[att] if x in world.war_state.armies]
                def_armies = [x for x in by_civ[dfn] if x in world.war_state.armies]
                if not att_armies or not def_armies:
                    continue
                fight(ctx, war, region, side_for(world, world.civ_map[att], att_armies),
                      side_for(world, world.civ_map[dfn], def_armies), kind="field")
                fought.update((a, b))


def _sieges_and_liberation(ctx: WarContext) -> None:
    world = ctx.world
    groups = _hostile_groups(ctx)
    for region_name in sorted(groups, key=lambda n: ctx.index[n]):
        region = world.region_map[region_name]
        for civ_name in sorted(groups[region_name]):
            armies = [a for a in groups[region_name][civ_name] if a in world.war_state.armies]
            if not armies:
                continue
            civ = living_civ(world, civ_name)
            if civ is None:
                continue
            hostile_present = any(
                other != civ_name and at_war(world, other, civ_name)
                and any(x in world.war_state.armies for x in groups[region_name][other])
                for other in groups[region_name])
            if hostile_present:
                continue
            # Liberate own land held by an enemy.
            if region.controller == civ_name and region.occupied_by not in (None, civ_name):
                occ = occupation_of(world, region_name)
                occupier = living_civ(world, region.occupied_by)
                war = war_for(world, occ.war_key) if occ else None
                if occ is None or occupier is None or war is None:
                    region.occupied_by = None
                    continue
                if skirmish(ctx, war, region, armies, civ, occupier, P.MIN_GARRISON):
                    end_occupation(ctx, occ, "liberated")
                continue
            owner = living_civ(world, region.controller)
            if owner is None or not at_war(world, civ_name, owner.name):
                for army in armies:
                    if army.phase == "sieging":
                        army.phase = "marching"
                        army.siege_turns = 0
                continue
            if region.occupied_by == civ_name:
                for army in armies:
                    if army.objective == region_name:
                        army.phase = "holding"
                continue
            war = war_for(world, war_key(civ_name, owner.name))
            if war is None:
                continue
            if region.occupied_by is not None:
                # A third party holds it; leave it be.
                continue
            from chronicler.war.common import is_fortified
            if is_fortified(world, region):
                if siege_turn(ctx, war, region, armies, civ, owner):
                    start_occupation(ctx, region, civ, war, armies[0])
                    for army in armies:
                        if army in world.war_state.armies:
                            army.phase = "holding"
                            army.siege_turns = 0
            else:
                if skirmish(ctx, war, region, armies, civ, owner, garrison_size(world, region, owner)):
                    survivors = [a for a in armies if a in world.war_state.armies]
                    start_occupation(ctx, region, civ, war, survivors[0] if survivors else None)
                    for army in survivors:
                        army.phase = "holding"


def _demobilize(ctx: WarContext) -> None:
    world = ctx.world
    for army in sorted(list(world.war_state.armies), key=_serial):
        if army.phase != "returning":
            continue
        region = world.region_map.get(army.region)
        if region is not None and region.controller == army.civ and region.occupied_by in (None, army.civ):
            disband(ctx, army, "demobilized")
            continue
        # Returning armies with no reachable home simply dissolve after a while.
        if world.turn - army.raised_turn > 60:
            release_soldiers(ctx, army, army.soldiers, cause="scattered")
            disband(ctx, army, "demobilized")


def end_of_turn_sync(world: "WorldState") -> None:
    """Drop occupations invalidated after the campaign tick (Phase 10).

    Secession, absorption or restoration can change a region's owner after
    campaigns ran; the occupation of a region its owner no longer holds, or
    held by a vanished occupier, is void. Silent: the next tick narrates any
    war that ended meanwhile.
    """
    if not world.campaigns_enabled:
        return
    state = world.war_state
    region_map = world.region_map
    state.occupations = [
        o for o in state.occupations
        if o.region in region_map and region_map[o.region].controller == o.owner
        and living_civ(world, o.occupier) is not None
    ]
    state.armies = [a for a in state.armies if living_civ(world, a.civ) is not None]
    _sync_occupied_flags(world)


def _sync_occupied_flags(world: "WorldState") -> None:
    occupied = {o.region: o.occupier for o in world.war_state.occupations}
    for region in world.regions:
        want = occupied.get(region.name)
        if region.occupied_by != want:
            region.occupied_by = want


# --- observers ----------------------------------------------------------------------

def contested_region_names(world: "WorldState") -> set[str]:
    """Regions with belligerent armies, battles or occupations (bridge signal)."""
    names = {o.region for o in world.war_state.occupations}
    names.update(a.region for a in world.war_state.armies if a.soldiers > 0)
    names.update(b.region for b in world.war_state.battles if b.turn == world.turn)
    return names


def snapshot_summary(world: "WorldState") -> dict[str, list[dict]]:
    """Viewer-facing campaign state for ``TurnSnapshot`` (completed turn N+1)."""
    if not world.campaigns_enabled:
        return {"armies": [], "battles": [], "occupations": [], "wars": []}
    state = world.war_state
    last_turn = world.turn - 1
    return {
        "armies": [
            {"id": a.army_id, "name": a.name, "civ": a.civ, "region": a.region,
             "objective": a.objective, "phase": a.phase, "soldiers": a.soldiers,
             "morale": a.morale, "rations": a.rations, "supply_distance": a.supply_distance,
             "general": a.general, "war": a.war_key, "siege_turns": a.siege_turns}
            for a in state.armies
        ],
        "battles": [b.model_dump() for b in state.battles if b.turn == last_turn],
        "occupations": [o.model_dump() for o in state.occupations],
        "wars": [
            {"war": w.war_key, "attacker": w.attacker, "defender": w.defender, "aim": w.aim,
             "aim_region": w.aim_region, "score": w.score, "start_turn": w.start_turn,
             "battles": w.battles}
            for w in state.wars
        ],
    }
