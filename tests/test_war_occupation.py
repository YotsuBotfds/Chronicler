"""M60b occupation: owner vs occupier, unrest, revolts, annexation, liberation."""
from __future__ import annotations

from chronicler.models import ProxyWar
from chronicler.war import params as P
from chronicler.war.occupation import (
    annex_occupation, end_occupation, occupation_of, start_occupation, tick_occupations,
)
from war_fixtures import place_army, start_war, war_world


def _occupy(world, ctx, war, region="Edge", garrison=0):
    army = place_army(world, "A", region, garrison, war.war_key, phase="holding") if garrison else None
    return start_occupation(ctx, world.region_map[region], world.civ_map["A"], war, army), army


def test_occupation_keeps_owner_and_marks_occupier():
    world = war_world()
    ctx, war = start_war(world)
    treasury = world.civ_map["A"].treasury
    occ, _ = _occupy(world, ctx, war)
    edge = world.region_map["Edge"]
    assert edge.controller == "B" and edge.occupied_by == "A"
    assert "Edge" in world.civ_map["B"].regions and "Edge" not in world.civ_map["A"].regions
    assert occ.owner == "B" and occ.occupier == "A" and occ.since_turn == world.turn
    assert world.civ_map["A"].treasury == treasury + edge.population // 10  # plunder
    assert any(e.event_type == "occupation" for e in ctx.events)
    assert any(ne.event_type == "occupation" for ne in world.named_events)


def test_capital_occupation_shocks_owner_stability():
    world = war_world()
    ctx, war = start_war(world)
    before = world.civ_map["B"].stability
    _occupy(world, ctx, war, region="Dun")
    assert world.civ_map["B"].stability < before
    assert any("capital" in e.description for e in ctx.events if e.event_type == "occupation")


def test_occupation_sacks_the_fallen_region():
    world = war_world()
    ctx, war = start_war(world)
    _occupy(world, ctx, war, region="Edge")
    _occupy(world, ctx, war, region="Dun")  # B's capital
    sacks = [(i.action, i.losing_civ, i.gaining_civ, i.region, i.is_capital)
             for i in world._artifact_lifecycle_intents]
    assert sacks == [("occupation_sack", "B", "A", "Edge", False),
                     ("occupation_sack", "B", "A", "Dun", True)]


def test_unrest_grows_without_garrison_and_is_suppressed_by_one():
    world = war_world()
    ctx, war = start_war(world)
    bare, _ = _occupy(world, ctx, war, region="Edge")
    held, _ = _occupy(world, ctx, war, region="Crag", garrison=30)
    world.regions[2].cultural_identity = "A"  # Crag welcomes A
    u_bare, u_held = bare.unrest, held.unrest
    tick_occupations(ctx)
    assert bare.unrest > u_bare
    assert held.unrest < u_held


def test_occupation_costs_owner_and_feeds_occupier():
    world = war_world()
    ctx, war = start_war(world)
    _occupy(world, ctx, war)
    a0, b0, s0 = world.civ_map["A"].treasury, world.civ_map["B"].treasury, world.civ_map["B"].stability
    tick_occupations(ctx)
    assert world.civ_map["B"].treasury == b0 - P.OCC_TAX_LOSS
    assert world.civ_map["A"].treasury == a0 + P.OCC_REQUISITION
    assert world.civ_map["B"].stability < s0


def test_proxy_war_funding_inflames_occupied_land():
    world = war_world()
    ctx, war = start_war(world)
    occ, _ = _occupy(world, ctx, war)
    tick_occupations(ctx)
    calm = occ.unrest
    world2 = war_world()
    ctx2, war2 = start_war(world2)
    occ2, _ = _occupy(world2, ctx2, war2)
    world2.proxy_wars.append(ProxyWar(sponsor="B", target_civ="A", target_region="Avalon"))
    tick_occupations(ctx2)
    assert occ2.unrest == calm + P.UNREST_PROXY


def _revolt_outcomes(garrison: int) -> set[str]:
    outcomes = set()
    for seed in range(40):
        world = war_world(seed=seed)
        ctx, war = start_war(world)
        occ, army = _occupy(world, ctx, war, garrison=garrison)
        occ.unrest = 1000
        pop0 = world.region_map["Edge"].population
        tick_occupations(ctx)
        if occupation_of(world, "Edge") is None:
            outcomes.add("liberated")
            assert world.region_map["Edge"].occupied_by is None
            assert any(e.event_type == "occupation_revolt" for e in ctx.events)
            assert army.phase == "regrouping" and army.casualties > 0
        elif any(e.event_type == "occupation_revolt" for e in ctx.events):
            outcomes.add("crushed")
            assert world.region_map["Edge"].population < pop0
            assert occ.unrest < 1000
    return outcomes


def test_high_unrest_revolt_beats_weak_garrison_and_fails_against_strong():
    assert _revolt_outcomes(3) == {"liberated"}
    assert _revolt_outcomes(25) == {"crushed"}


def test_quiet_long_occupation_is_annexed_via_conquest_path():
    world = war_world()
    ctx, war = start_war(world)
    occ, army = _occupy(world, ctx, war, garrison=30)
    world.regions[4].cultural_identity = "A"
    occ.unrest = 0
    world.turn = occ.since_turn + P.ANNEX_TURNS
    tick_occupations(ctx)
    edge = world.region_map["Edge"]
    assert edge.controller == "A" and edge.occupied_by is None
    assert "Edge" in world.civ_map["A"].regions and "Edge" not in world.civ_map["B"].regions
    assert edge.last_conquered_turn == world.turn
    assert any(e.event_type == "annexation" for e in ctx.events)
    assert occupation_of(world, "Edge") is None


def test_annexing_last_region_extinguishes_owner():
    world = war_world()
    ctx, war = start_war(world)
    occs = [_occupy(world, ctx, war, region=r)[0] for r in ("Crag", "Dun", "Edge")]
    for occ in occs:
        annex_occupation(ctx, occ, "treaty")
    assert world.civ_map["B"].regions == []
    assert any(e.event_type == "civ_conquered" for e in ctx.events)


def test_ownership_change_or_collapse_ends_occupation():
    world = war_world()
    ctx, war = start_war(world)
    occ, _ = _occupy(world, ctx, war)
    world.region_map["Edge"].controller = "C"  # e.g. a secession
    tick_occupations(ctx)
    assert occupation_of(world, "Edge") is None and world.region_map["Edge"].occupied_by is None
    world = war_world()
    ctx, war = start_war(world)
    occ, _ = _occupy(world, ctx, war)
    world.civ_map["A"].regions = []  # occupier collapses
    tick_occupations(ctx)
    assert occupation_of(world, "Edge") is None
    assert any(e.event_type == "liberation" for e in ctx.events)


def test_end_occupation_liberation_event():
    world = war_world()
    ctx, war = start_war(world)
    occ, _ = _occupy(world, ctx, war)
    end_occupation(ctx, occ, "liberated")
    assert world.region_map["Edge"].occupied_by is None
    assert ctx.events[-1].event_type == "liberation"
