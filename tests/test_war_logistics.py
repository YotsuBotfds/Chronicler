"""M60a production logistics: kernel arithmetic reuse, supply, upkeep, attrition, movement."""
from __future__ import annotations

from dataclasses import replace

import pytest

from chronicler import campaign_logistics as cl
from chronicler.war import params as P
from chronicler.war.common import build_context, build_graph
from chronicler.war.logistics import logistics_step, move_armies, supply_sources, upkeep_cost
from war_fixtures import place_army, start_war, war_world


def test_kernel_helpers_match_detached_advance():
    """The extracted helpers reproduce the kernel's per-member arithmetic."""
    policy = replace(P.POLICY, version="t")
    for consumed in (0, 1):
        for distance in (None, 0, 2):
            for needs, info in ((0, 1000), (500, 250), (1000, 0)):
                h, d, n, i = cl.stress_components(policy, demand=1, consumed=consumed, distance=distance,
                                                  unmet_needs=needs, information_quality=info)
                assert h == (policy.hunger_stress * (1 - consumed) + 0) // 1
                assert d == (policy.unreachable_stress if distance is None else distance * policy.distance_stress)
                assert n == needs * policy.needs_stress // 1000
                assert i == (1000 - info) * policy.information_stress // 1000
    assert cl.next_morale(policy, 500, 0) == 500 + policy.morale_recovery
    assert cl.next_morale(policy, 50, 400) == 0
    assert cl.next_morale(policy, 990, 0) == 1000


def test_cohort_hunger_uses_ceiling_division():
    h, *_ = cl.stress_components(P.POLICY, demand=10, consumed=9, distance=0,
                                 unmet_needs=0, information_quality=1000)
    assert h == -(-P.POLICY.hunger_stress * 1 // 10)


def test_world_graph_is_kernel_validated_and_symmetric():
    world = war_world()
    world.regions[1].adjacencies.remove("Avalon")  # leave a one-way edge Avalon -> Brook
    world.regions[2].adjacencies.append("Nowhere")  # unknown names are dropped
    graph, index, names = build_graph(world)
    assert 1 in graph[0] and 0 in graph[1]
    for node, nbrs in graph.items():
        for nb in nbrs:
            assert node in graph[nb]
    assert names[0] == "Avalon" and index["Dun"] == 3
    assert cl.shortest_path(graph, index["Avalon"], index["Dun"]) == (0, 1, 2, 3)


def test_supply_distance_and_refill_shrink_with_distance():
    world = war_world()
    ctx, war = start_war(world)
    near = place_army(world, "A", "Brook", 10, war.war_key)
    far = place_army(world, "A", "Dun", 10, war.war_key)
    near.rations = far.rations = 0
    sources = supply_sources(ctx, "A")
    r_near = logistics_step(ctx, near, world.civ_map["A"], sources, winter=False)
    r_far = logistics_step(ctx, far, world.civ_map["A"], sources, winter=False)
    assert r_near["supply_distance"] == 0 and r_far["supply_distance"] == 2
    assert r_near["refill"] > r_far["refill"] > 0
    assert r_far["forage"] > 0  # enemy farmland feeds an army a little
    assert r_far["stress"][1] == 2 * P.POLICY.distance_stress


def test_upkeep_paid_from_treasury_and_unpaid_raises_needs_stress():
    world = war_world(treasury_a=1000)
    ctx, war = start_war(world)
    army = place_army(world, "A", "Brook", 20, war.war_key)
    civ = world.civ_map["A"]
    receipt = logistics_step(ctx, army, civ, supply_sources(ctx, "A"), winter=False)
    assert receipt["upkeep"] == upkeep_cost(world, army) == 6
    assert receipt["paid"] == 6 and receipt["unmet_needs"] == 0
    assert civ.treasury == 1000 - 6
    civ.treasury = 0
    broke = logistics_step(ctx, army, civ, supply_sources(ctx, "A"), winter=False)
    assert broke["paid"] == 0 and broke["unmet_needs"] == 1000
    assert broke["stress"][2] == P.POLICY.needs_stress
    assert army.unpaid_turns == 1


def test_starving_army_loses_morale_deserts_and_dies_faster():
    world = war_world()
    ctx, war = start_war(world)
    for region in world.regions:
        region.population = 0  # nothing to forage
    army = place_army(world, "A", "Dun", 200, war.war_key, morale=320)
    army.rations = 0
    world.regions[0].controller = world.regions[1].controller = "Z"  # no supply anywhere
    world.civ_map["A"].regions = []
    receipt = logistics_step(ctx, army, world.civ_map["A"], (), winter=False)
    assert receipt["supply_distance"] is None
    assert receipt["consumed"] == 0
    assert receipt["morale_after"] < 320
    assert receipt["deserted"] > 0
    assert receipt["attrition_permille"] >= (P.ATTRITION_PERMILLE["plains"] + P.HUNGER_ATTRITION_PERMILLE
                                             + P.UNREACHABLE_ATTRITION_PERMILLE)
    assert army.soldiers == 200 - receipt["deserted"] - receipt["attrition"]
    assert army.deserted == receipt["deserted"]


def test_terrain_attrition_harsher_in_desert_than_plains():
    world = war_world()
    world.regions[3].terrain = "desert"
    ctx, war = start_war(world)
    plains = place_army(world, "A", "Brook", 1000, war.war_key)
    desert = place_army(world, "A", "Dun", 1000, war.war_key)
    sources = supply_sources(ctx, "A")
    a = logistics_step(ctx, plains, world.civ_map["A"], sources, winter=False)
    b = logistics_step(ctx, desert, world.civ_map["A"], sources, winter=False)
    assert b["attrition_permille"] > a["attrition_permille"]
    assert b["attrition"] > a["attrition"]


def test_movement_one_edge_per_turn_and_mountains_cost_two():
    world = war_world()
    ctx, war = start_war(world)
    army = place_army(world, "A", "Avalon", 10, war.war_key)
    army.objective = "Dun"
    move_armies(ctx, [army])
    assert army.region == "Brook"
    move_armies(ctx, [army])
    assert army.region == "Brook" and army.move_progress == 1  # climbing into Crag
    move_armies(ctx, [army])
    assert army.region == "Crag"


def test_engaged_army_holds_position():
    world = war_world()
    ctx, war = start_war(world)
    army = place_army(world, "A", "Brook", 10, war.war_key)
    army.objective = "Avalon"
    place_army(world, "B", "Brook", 10, war.war_key)
    move_armies(ctx, [army])
    assert army.region == "Brook"


def test_low_morale_stalls_marching_but_not_regrouping():
    world = war_world()
    ctx, war = start_war(world)
    army = place_army(world, "A", "Avalon", 10, war.war_key, morale=P.POLICY.movement_min_morale - 1)
    army.objective = "Brook"
    move_armies(ctx, [army])
    assert army.region == "Avalon"
    army.phase = "regrouping"
    move_armies(ctx, [army])
    assert army.region == "Brook"


@pytest.mark.parametrize("terrain", sorted(P.ATTRITION_PERMILLE))
def test_every_terrain_has_logistics_parameters(terrain):
    assert terrain in P.MOVE_COST and terrain in P.FORAGE_BY_TERRAIN
