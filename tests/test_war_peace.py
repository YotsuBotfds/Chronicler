"""War aims, war score, peace terms, reconciliation and the action hooks."""
from __future__ import annotations

from chronicler.action_engine import ACTION_REGISTRY
from chronicler.models import ActionType, Disposition, VassalRelation
from chronicler.war import params as P
from chronicler.war.common import build_context
from chronicler.war.occupation import occupation_of, start_occupation
from chronicler.war.peace import (
    choose_aim, conclude_peace, evaluate_peace, reconcile_wars, sue_for_peace, update_score, war_key,
)
from chronicler.war.runtime import declare_or_press_war
from war_fixtures import place_army, start_war, war_world


def _occupy(world, ctx, war, region, occupier="A"):
    return start_occupation(ctx, world.region_map[region], world.civ_map[occupier], war, None)


def test_aim_liberation_when_kin_live_under_enemy_rule():
    world = war_world()
    world.region_map["Edge"].cultural_identity = "A"
    ctx = build_context(world)
    assert choose_aim(ctx, world.civ_map["A"], world.civ_map["B"]) == ("liberation", "Edge")


def test_aim_vassalization_or_conquest_depends_on_strength_and_seed():
    aims = set()
    for seed in range(30):
        world = war_world(seed=seed, mil_a=90, mil_b=10)
        world.turn = seed
        aims.add(choose_aim(build_context(world), world.civ_map["A"], world.civ_map["B"])[0])
    assert {"vassalization", "conquest"} <= aims
    poor = war_world(treasury_a=10, mil_a=30, mil_b=30)
    assert choose_aim(build_context(poor), poor.civ_map["A"], poor.civ_map["B"])[0] == "tribute"


def test_score_counts_occupations_capitals_and_battles():
    world = war_world()
    ctx, war = start_war(world)
    _occupy(world, ctx, war, "Edge")
    update_score(ctx, war)
    assert war.score == P.OCC_POINTS
    _occupy(world, ctx, war, "Dun")
    war.battle_points = 10
    update_score(ctx, war)
    assert war.score == 2 * P.OCC_POINTS + P.OCC_CAPITAL_POINTS + 10
    _occupy(world, ctx, war, "Brook", occupier="B")
    update_score(ctx, war)
    assert war.score == P.OCC_POINTS + P.OCC_CAPITAL_POINTS + 10


def test_capitulation_cedes_occupied_regions_and_closes_war():
    world = war_world()
    ctx, war = start_war(world)
    war.aim = "conquest"
    _occupy(world, ctx, war, "Edge")
    _occupy(world, ctx, war, "Crag")
    army = place_army(world, "A", "Edge", 10, war.war_key)
    treaty = conclude_peace(ctx, war, "capitulation", "A")
    assert sorted(treaty.regions_ceded) == ["Crag", "Edge"]
    assert world.region_map["Edge"].controller == "A" and world.region_map["Crag"].controller == "A"
    assert world.active_wars == [] and war_key("A", "B") not in world.war_start_turns
    assert war not in world.war_state.wars and war in world.war_state.ended_wars
    assert army.phase == "returning"
    rel = world.relationships["A"]["B"]
    assert rel.disposition == Disposition.SUSPICIOUS and treaty.name in rel.treaties
    assert any(ne.event_type == "treaty" and ne.name == treaty.name for ne in world.named_events)
    assert any(e.event_type == "peace_treaty" for e in ctx.events)


def test_negotiated_peace_cedes_one_region_and_never_the_last():
    world = war_world()
    ctx, war = start_war(world)
    for region in ("Crag", "Dun", "Edge"):
        _occupy(world, ctx, war, region)
    treaty = conclude_peace(ctx, war, "negotiated", "A")
    assert len(treaty.regions_ceded) == 1
    assert world.civ_map["B"].regions
    assert all(occupation_of(world, r) is None for r in ("Crag", "Dun", "Edge"))


def test_vassalization_terms_create_vassal_relation():
    world = war_world()
    ctx, war = start_war(world)
    war.aim = "vassalization"
    _occupy(world, ctx, war, "Dun")
    treaty = conclude_peace(ctx, war, "capitulation", "A")
    assert treaty.vassalized
    assert any(vr.overlord == "A" and vr.vassal == "B" for vr in world.vassal_relations)
    assert world.region_map["Dun"].controller == "B" and world.region_map["Dun"].occupied_by is None
    assert world.active_wars == []


def test_tribute_terms_transfer_treasury():
    world = war_world(treasury_b=100)
    ctx, war = start_war(world)
    war.aim = "tribute"
    war.score = 40
    a0 = world.civ_map["A"].treasury
    treaty = conclude_peace(ctx, war, "negotiated", "A")
    assert treaty.treasury_paid == P.TRIBUTE_BASE + 20
    assert world.civ_map["B"].treasury == 100 - treaty.treasury_paid
    assert world.civ_map["A"].treasury == a0 + treaty.treasury_paid


def test_white_peace_returns_everything():
    world = war_world()
    ctx, war = start_war(world)
    _occupy(world, ctx, war, "Edge")
    treaty = conclude_peace(ctx, war, "white_peace", None)
    assert treaty.regions_ceded == [] and treaty.winner is None
    assert world.region_map["Edge"].occupied_by is None and world.region_map["Edge"].controller == "B"


def test_external_war_end_is_reconciled():
    world = war_world()
    ctx, war = start_war(world)
    _occupy(world, ctx, war, "Edge")
    world.active_wars.clear()  # e.g. diplomacy or a congress ended it
    reconcile_wars(ctx)
    assert war in world.war_state.ended_wars and war.outcome == "external"
    assert world.region_map["Edge"].occupied_by is None
    # New pairs from other systems (federation defense) get records.
    world.active_wars.append(("B", "A"))
    reconcile_wars(ctx)
    assert world.war_state.wars and world.war_state.wars[0].attacker == "B"


def test_evaluate_peace_capitulates_crushed_side_eventually():
    world = war_world()
    ctx, war = start_war(world)
    for region in ("Crag", "Dun"):
        _occupy(world, ctx, war, region)
    war.battle_points = 60
    world.civ_map["B"].war_weariness = 30.0
    for turn in range(P.MIN_WAR_TURNS, P.MIN_WAR_TURNS + 10):
        world.turn = turn
        evaluate_peace(ctx)
        if not world.war_state.wars:
            break
    assert not world.war_state.wars
    treaty = world.war_state.treaties[-1]
    assert treaty.kind == "capitulation" and treaty.winner == "A"


def test_declare_war_marks_hostility_raises_army_and_records_war():
    world = war_world()
    world.relationships["A"]["B"].disposition = Disposition.SUSPICIOUS
    event = declare_or_press_war(world.civ_map["A"], world.civ_map["B"], world)
    assert event.event_type == "war" and "attacker_wins" not in event.description
    assert ("A", "B") in world.active_wars
    assert world.relationships["A"]["B"].disposition == Disposition.HOSTILE
    assert world.relationships["B"]["A"].disposition == Disposition.HOSTILE
    assert len(world.war_state.wars) == 1 and world.war_state.armies
    assert world.war_state.armies[0].civ == "A"
    assert any(e.event_type == "war_declared" for e in world.events_timeline)
    # Pressing again neither duplicates the war nor opens a second front.
    declare_or_press_war(world.civ_map["A"], world.civ_map["B"], world)
    assert world.active_wars == [("A", "B")] and len(world.war_state.wars) == 1


def test_no_phony_war_without_an_army():
    world = war_world(treasury_a=0)
    event = declare_or_press_war(world.civ_map["A"], world.civ_map["B"], world)
    assert world.active_wars == [] and not world.war_state.wars
    assert event.event_type == "war" and "could not muster" in event.description


def test_war_action_routes_to_campaigns_only_when_enabled():
    on = war_world()
    ACTION_REGISTRY[ActionType.WAR](on.civ_map["A"], on)
    assert on.war_state.wars and not any(r.controller == "A" for r in on.regions if r.name == "Crag")
    off = war_world(campaigns=False)
    ACTION_REGISTRY[ActionType.WAR](off.civ_map["A"], off)
    assert not off.war_state.wars and not off.war_state.armies


def test_diplomacy_with_enemy_is_a_peace_offer():
    world = war_world()
    ctx, war = start_war(world)
    world.turn = P.MIN_WAR_TURNS + 1
    for region in ("Crag", "Edge"):
        _occupy(world, ctx, war, region)
    war.battle_points = 10  # A clearly ahead
    world.civ_map["B"].war_weariness = 40.0
    event = sue_for_peace(world.civ_map["A"], world.civ_map["B"], world)
    assert event.event_type == "diplomacy"
    assert not world.war_state.wars
    assert world.war_state.treaties[-1].winner == "A"
    # Through the real DIPLOMACY action, a losing civ accepts the enemy's terms.
    world2 = war_world()
    ctx2, war2 = start_war(world2)
    world2.turn = P.MIN_WAR_TURNS + 1
    _occupy(world2, ctx2, war2, "Brook", occupier="B")
    war2.battle_points = -30
    results = []
    for turn in range(world2.turn, world2.turn + 15):
        world2.turn = turn
        results.append(ACTION_REGISTRY[ActionType.DIPLOMACY](world2.civ_map["A"], world2).description)
        if not world2.war_state.wars:
            break
    assert not world2.war_state.wars
    assert world2.war_state.treaties[-1].winner == "B"
    assert world2.region_map["Brook"].controller == "B"


def test_vassal_overlord_relation_counts_as_external_vassal_end():
    world = war_world()
    ctx, war = start_war(world)
    world.vassal_relations.append(VassalRelation(overlord="A", vassal="B"))
    world.active_wars.clear()
    reconcile_wars(ctx)
    assert war.outcome == "vassalized"


def test_treaty_imposes_truce_before_a_new_war():
    world = war_world()
    ctx, war = start_war(world)
    conclude_peace(ctx, war, "white_peace", None)
    world.turn += 1
    event = declare_or_press_war(world.civ_map["A"], world.civ_map["B"], world)
    assert "truce" in event.description and world.active_wars == []
    world.turn += P.TRUCE_TURNS
    world.war_state.last_raise_turn.clear()
    declare_or_press_war(world.civ_map["A"], world.civ_map["B"], world)
    assert world.active_wars == [("A", "B")]


def test_parity_peace_offer_needs_a_war_of_some_length():
    world = war_world()
    ctx, war = start_war(world)
    world.civ_map["A"].war_weariness = world.civ_map["B"].war_weariness = 50.0
    world.turn = P.PARITY_PEACE_TURNS - 1
    for _ in range(5):
        sue_for_peace(world.civ_map["A"], world.civ_map["B"], world)
    assert world.war_state.wars, "parity peace refused before PARITY_PEACE_TURNS"
    world.turn = P.PARITY_PEACE_TURNS
    for turn in range(P.PARITY_PEACE_TURNS, P.PARITY_PEACE_TURNS + 10):
        world.turn = turn
        sue_for_peace(world.civ_map["A"], world.civ_map["B"], world)
        if not world.war_state.wars:
            break
    assert not world.war_state.wars and world.war_state.treaties[-1].kind == "white_peace"
