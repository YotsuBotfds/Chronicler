"""War aims, war score and negotiated peace.

``WorldState.active_wars`` stays the single source of truth for who is at war;
``WarRecord`` adds the campaign bookkeeping. Wars started or ended by other
systems (federation defense, diplomacy, congress, vassalization, extinction)
are reconciled every turn: new pairs get a record, vanished pairs are closed
as ``external`` peace with occupations returned.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from chronicler.models import Disposition, Relationship, TreatyRecord, WarRecord
from chronicler.war import params as P
from chronicler.war.ai import region_value
from chronicler.war.common import (
    WarContext, add_stat, emit, living_civ, name_event, spend, war_rng,
)
from chronicler.war.occupation import annex_occupation, end_occupation
from chronicler.diplomacy_state import diplomacy_on as _diplomacy_on

if TYPE_CHECKING:
    from chronicler.models import Civilization

_VASSAL_BIAS = {"cautious", "shrewd", "visionary", "calculating"}
_TRIBUTE_BIAS = {"shrewd", "calculating"}


def war_key(a: str, b: str) -> str:
    from chronicler.politics import war_key as _key
    return _key(a, b)


def choose_aim(ctx: WarContext, attacker: "Civilization", defender: "Civilization") -> tuple[str, str | None]:
    """Pick a war aim and focal region for a new war."""
    from chronicler.intelligence import get_perceived_stat
    world = ctx.world
    owned = [r for r in world.regions if r.controller == defender.name]
    if not owned:
        return "conquest", None
    lost_kin = [r for r in owned if r.cultural_identity == attacker.name]
    if lost_kin:
        best = max(lost_kin, key=lambda r: (region_value(world, r), -ctx.index[r.name]))
        return "liberation", best.name
    rng = war_rng(ctx, "aim", attacker.name, defender.name)
    perceived = get_perceived_stat(attacker, defender, "military", world)
    ratio = attacker.military / max(1, perceived if perceived is not None else defender.military)
    already_vassal = any(vr.vassal == defender.name for vr in world.vassal_relations)
    vassal_bias = 0.6 if attacker.leader.trait in _VASSAL_BIAS else 0.3
    if ratio >= 1.5 and attacker.stability > 40 and not already_vassal and rng.random() < vassal_bias:
        return "vassalization", defender.capital_region
    if attacker.treasury < 40 or (attacker.leader.trait in _TRIBUTE_BIAS and rng.random() < 0.5):
        richest = max(owned, key=lambda r: (r.population, -ctx.index[r.name]))
        return "tribute", richest.name
    frontier = _frontier_regions(ctx, attacker.name, defender.name) or [r.name for r in owned]
    best = max(frontier, key=lambda n: (region_value(world, world.region_map[n]), -ctx.index[n]))
    return "conquest", best


def _frontier_regions(ctx: WarContext, civ_name: str, enemy_name: str) -> list[str]:
    world = ctx.world
    own = {r.name for r in world.regions if r.controller == civ_name}
    out = []
    for r in world.regions:
        if r.controller == enemy_name and any(adj in own for adj in r.adjacencies):
            out.append(r.name)
    return out


def open_war(ctx: WarContext, attacker: "Civilization", defender: "Civilization",
             start_turn: int | None = None) -> WarRecord:
    aim, region = choose_aim(ctx, attacker, defender)
    war = WarRecord(war_key=war_key(attacker.name, defender.name), attacker=attacker.name,
                    defender=defender.name, aim=aim, aim_region=region,
                    start_turn=ctx.world.turn if start_turn is None else start_turn)
    ctx.world.war_state.wars.append(war)
    _set_disposition(ctx.world, attacker.name, defender.name, Disposition.HOSTILE, None)
    goal = {"conquest": f"conquest of {region}" if region else "conquest",
            "vassalization": "the subjugation of " + defender.name,
            "tribute": "tribute", "liberation": f"the liberation of {region}"}[aim]
    emit(ctx, "war_declared", [attacker.name, defender.name],
         f"{attacker.name} goes to war with {defender.name}, seeking {goal}.", importance=7)
    return war


def reconcile_wars(ctx: WarContext) -> None:
    """Sync WarRecords with ``world.active_wars`` (both directions)."""
    world = ctx.world
    state = world.war_state
    active: dict[str, tuple[str, str]] = {}
    for a, b in world.active_wars:
        active.setdefault(war_key(a, b), (a, b))
    for war in list(state.wars):
        if war.war_key not in active:
            close_external(ctx, war)
    known = {w.war_key for w in state.wars}
    for key, (a, b) in active.items():
        if key in known:
            continue
        att, dfn = living_civ(world, a), living_civ(world, b)
        if att is None or dfn is None:
            continue
        open_war(ctx, att, dfn, start_turn=world.war_start_turns.get(key, world.turn))


def update_score(ctx: WarContext, war: WarRecord) -> None:
    world = ctx.world
    points = 0
    for occ in world.war_state.occupations:
        if occ.war_key != war.war_key:
            continue
        owner = world.civ_map.get(occ.owner)
        value = P.OCC_POINTS + (P.OCC_CAPITAL_POINTS if owner is not None and owner.capital_region == occ.region else 0)
        if occ.occupier == war.attacker:
            points += value
        elif occ.occupier == war.defender:
            points -= value
    war.score = max(-100, min(100, war.battle_points + points))


def evaluate_peace(ctx: WarContext) -> None:
    world = ctx.world
    for war in sorted(list(world.war_state.wars), key=lambda w: w.war_key):
        if war not in world.war_state.wars:
            continue
        att, dfn = living_civ(world, war.attacker), living_civ(world, war.defender)
        if att is None or dfn is None:
            continue
        # Old victories fade: one battle point toward zero every third turn.
        if world.turn % 3 == 0 and war.battle_points:
            war.battle_points -= 1 if war.battle_points > 0 else -1
        update_score(ctx, war)
        duration = world.turn - war.start_turn
        if duration < P.MIN_WAR_TURNS:
            continue
        rng = war_rng(ctx, "peace", war.war_key)
        roll = rng.random()
        score = war.score
        if abs(score) >= P.CAPITULATION_SCORE:
            winner, loser = (att, dfn) if score > 0 else (dfn, att)
            if roll < min(0.9, 0.25 + loser.war_weariness / 40.0):
                conclude_peace(ctx, war, "capitulation", winner.name)
            continue
        if abs(score) >= P.NEGOTIATION_SCORE and duration >= 8:
            winner, loser = (att, dfn) if score > 0 else (dfn, att)
            if roll < min(0.6, 0.04 + loser.war_weariness / 60.0 + duration / 400.0):
                conclude_peace(ctx, war, "negotiated", winner.name)
            continue
        if duration >= P.WHITE_PEACE_TURNS:
            idle = not any(a.war_key == war.war_key for a in world.war_state.armies)
            p = min(0.5, 0.02 + (att.war_weariness + dfn.war_weariness) / 100.0 + (0.15 if idle else 0.0))
            if roll < p:
                conclude_peace(ctx, war, "white_peace", None)


def _release_war_occupations(ctx: WarContext, war: WarRecord, reason: str) -> None:
    for occ in sorted([o for o in ctx.world.war_state.occupations if o.war_key == war.war_key],
                      key=lambda o: ctx.index.get(o.region, 1 << 30)):
        if living_civ(ctx.world, occ.owner) is None and living_civ(ctx.world, occ.occupier) is not None:
            annex_occupation(ctx, occ, "owner_gone")
        else:
            end_occupation(ctx, occ, reason)


def _finish(ctx: WarContext, war: WarRecord, outcome: str) -> None:
    state = ctx.world.war_state
    war.ended_turn = ctx.world.turn
    war.outcome = outcome
    if war in state.wars:
        state.wars.remove(war)
    state.ended_wars.append(war)
    for army in state.armies:
        if army.war_key == war.war_key:
            army.phase = "returning"
            army.siege_turns = 0


def _remove_active_pair(world, a: str, b: str) -> None:
    world.active_wars = [w for w in world.active_wars if set(w) != {a, b}]
    world.war_start_turns.pop(war_key(a, b), None)
    world.invalidate_trade_route_cache()


def _set_disposition(world, a: str, b: str, disposition: Disposition, treaty: str | None) -> None:
    for x, y in ((a, b), (b, a)):
        rels = world.relationships.setdefault(x, {})
        rel = rels.get(y)
        if rel is None:
            rel = Relationship()
            rels[y] = rel
        rel.disposition = disposition
        if treaty and treaty not in rel.treaties:
            rel.treaties.append(treaty)


def conclude_peace(ctx: WarContext, war: WarRecord, kind: str, winner_name: str | None) -> TreatyRecord:
    """Apply peace terms for ``war`` and close it."""
    from chronicler.named_events import generate_treaty_name
    from chronicler.politics import resolve_vassalization
    world = ctx.world
    att, dfn = world.civ_map[war.attacker], world.civ_map[war.defender]
    winner = world.civ_map.get(winner_name) if winner_name else None
    loser = (dfn if winner is att else att) if winner is not None else None
    ceded: list[str] = []
    paid = 0
    vassalized = False
    aim = war.aim if winner is att else "conquest"
    # Diplomacy (--diplomacy): tribute is paid in installments under a tribute
    # treaty, and the polity ladder spares a state a capitulation would end.
    ladder = _diplomacy_on(world)
    spare = False
    tribute_total = 0
    if winner is not None and loser is not None:
        held = [o for o in world.war_state.occupations
                if o.war_key == war.war_key and o.occupier == winner.name and o.owner == loser.name]
        held.sort(key=lambda o: (o.region != war.aim_region,
                                 -region_value(world, world.region_map[o.region]),
                                 ctx.index.get(o.region, 0)))
        already_vassal = any(vr.vassal in (loser.name, winner.name) for vr in world.vassal_relations)
        if aim == "vassalization" and kind == "capitulation" and not already_vassal:
            _release_war_occupations(ctx, war, "treaty_returned")
            ctx.events.extend(resolve_vassalization(winner, loser, world))
            vassalized = True
        else:
            if aim == "tribute":
                cede = []
            elif aim == "liberation":
                cede = [o for o in held if world.region_map[o.region].cultural_identity == winner.name] or held[:1]
            else:
                cede = held if kind == "capitulation" else held[:1]
            # Only a capitulation can extinguish the loser.
            if kind != "capitulation":
                cede = cede[:max(0, len(loser.regions) - 1)]
            elif ladder and cede and len(cede) >= len(loser.regions) and not already_vassal:
                from chronicler.diplomacy import spares_last_region
                if spares_last_region(world, winner, loser):
                    # Ladder: the loser keeps its capital (or last region) as a vassal.
                    held_regions = {o.region for o in cede}
                    keep = loser.capital_region if loser.capital_region in held_regions else cede[-1].region
                    cede = [o for o in cede if o.region != keep]
                    spare = True
            for occ in cede:
                if annex_occupation(ctx, occ, "treaty"):
                    ceded.append(occ.region)
            if aim == "tribute" or not ceded:
                amount = (P.TRIBUTE_BASE + abs(war.score) // 2) if aim == "tribute" else 10 + abs(war.score) // 3
                if aim == "tribute" and ladder and not spare:
                    tribute_total = amount
                else:
                    paid = spend(ctx, loser, amount)
                    if paid:
                        add_stat(ctx, winner, "treasury", paid, "keep")
            if spare:
                _release_war_occupations(ctx, war, "treaty_returned")
                ctx.events.extend(resolve_vassalization(winner, loser, world))
                vassalized = True
    _release_war_occupations(ctx, war, "treaty_returned")
    if not vassalized:
        _remove_active_pair(world, att.name, dfn.name)
    name = generate_treaty_name(att.name, dfn.name, world, seed=world.seed)
    if not vassalized:
        _set_disposition(world, att.name, dfn.name, Disposition.SUSPICIOUS, name)
    treaty = TreatyRecord(turn=world.turn, name=name, war_key=war.war_key, parties=[att.name, dfn.name],
                          winner=winner.name if winner else None, kind=kind, aim=war.aim,
                          regions_ceded=ceded, treasury_paid=paid, vassalized=vassalized)
    world.war_state.treaties.append(treaty)
    if vassalized:
        terms = f"{loser.name} becomes a vassal of {winner.name}"
        if ceded:
            terms = f"{loser.name} cedes " + ", ".join(ceded) + f" and becomes a vassal of {winner.name}"
    elif winner is not None:
        parts = []
        if ceded:
            parts.append("cedes " + ", ".join(ceded))
        if paid:
            parts.append(f"pays {paid} in {'tribute' if aim == 'tribute' else 'reparations'}")
        elif tribute_total:
            from chronicler.diplomacy import TRIBUTE_INSTALLMENTS
            parts.append(f"agrees to pay {tribute_total} in tribute over {TRIBUTE_INSTALLMENTS} turns")
        terms = f"{loser.name} " + (" and ".join(parts) if parts else "accepts defeat") + f" to {winner.name}"
    else:
        terms = "status quo ante bellum"
    label = {"capitulation": "capitulates", "negotiated": "negotiated peace", "white_peace": "white peace"}[kind]
    peace_event = emit(ctx, "peace_treaty", [att.name, dfn.name], f"{name} ends the war ({label}): {terms}.",
                       importance=8 if kind == "capitulation" else 6)
    if ladder:
        from chronicler.diplomacy import on_campaign_peace
        on_campaign_peace(world, treaty, peace_event, tribute_total=tribute_total)
    name_event(ctx, name, "treaty", [att.name, dfn.name], None, f"{name}: {terms}", 7 if ceded or vassalized else 5)
    _finish(ctx, war, kind)
    return treaty


def close_external(ctx: WarContext, war: WarRecord) -> None:
    """A war ended outside the campaign layer (diplomacy, congress, death...)."""
    world = ctx.world
    vassal = any({vr.overlord, vr.vassal} == {war.attacker, war.defender} for vr in world.vassal_relations)
    _release_war_occupations(ctx, war, "war_ended")
    world.war_state.treaties.append(TreatyRecord(
        turn=world.turn, name="", war_key=war.war_key, parties=[war.attacker, war.defender],
        kind="external", aim=war.aim, vassalized=vassal))
    alive = living_civ(world, war.attacker) is not None and living_civ(world, war.defender) is not None
    if alive:
        ended = emit(ctx, "war_ended", [war.attacker, war.defender],
                     f"The war between {war.attacker} and {war.defender} ends"
                     + (" in vassalage." if vassal else "."), importance=5)
        if not vassal and _diplomacy_on(world):
            from chronicler.diplomacy import on_external_peace
            on_external_peace(world, war.attacker, war.defender, ended)
    _finish(ctx, war, "vassalized" if vassal else "external")


def sue_for_peace(civ: "Civilization", enemy: "Civilization", world, acc=None):
    """DIPLOMACY toward a war enemy under campaigns: offer peace on war-score terms.

    The civ that is winning offers a negotiated peace in its favour; the one
    losing offers to accept the enemy's terms; at near-parity a white peace
    is proposed. The enemy accepts with a probability driven by its war
    weariness and the war's length. Returns the action ``Event``.
    """
    from chronicler.models import Event
    from chronicler.war.common import build_context, war_for
    ctx = build_context(world, acc)
    reconcile_wars(ctx)
    war = war_for(world, war_key(civ.name, enemy.name))
    if war is None:
        return None
    update_score(ctx, war)
    mine = war.score if civ.name == war.attacker else -war.score
    duration = world.turn - war.start_turn
    rng = war_rng(ctx, "sue", war.war_key, civ.name)
    outcome = None
    if duration >= P.MIN_WAR_TURNS:
        if mine >= P.NEGOTIATION_SCORE:
            if rng.random() < min(0.8, 0.3 + enemy.war_weariness / 40.0):
                outcome = ("negotiated", civ.name)
        elif mine <= -P.NEGOTIATION_SCORE:
            if rng.random() < 0.6:
                outcome = ("negotiated", enemy.name)
        elif (duration >= P.PARITY_PEACE_TURNS
              and rng.random() < min(0.6, 0.10 + (civ.war_weariness + enemy.war_weariness) / 80.0)):
            outcome = ("white_peace", None)
    if outcome is not None:
        treaty = conclude_peace(ctx, war, outcome[0], outcome[1])
        world.events_timeline.extend(ctx.events)
        return Event(turn=world.turn, event_type="diplomacy", actors=[civ.name, enemy.name],
                     description=f"{civ.name} made peace with {enemy.name}: {treaty.name}.", importance=6)
    world.events_timeline.extend(ctx.events)
    return Event(turn=world.turn, event_type="diplomacy", actors=[civ.name, enemy.name],
                 description=f"{civ.name} sued for peace with {enemy.name}, but was rebuffed.", importance=3)
