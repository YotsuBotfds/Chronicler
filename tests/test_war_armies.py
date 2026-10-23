"""Army lifecycle: aggregate and native enlistment, casualties, desertion, reconciliation."""
from __future__ import annotations

from chronicler.models import GreatPerson
from chronicler.war import params as P
from chronicler.war.armies import (
    apply_casualties, can_raise, kill_general, muster_capacity, raise_army, rebind_rosters,
    reconcile_rosters, release_soldiers, select_recruits,
)
from chronicler.war.common import build_context
from war_fixtures import FakeBridge, FakeSnapshot, place_army, start_war, war_world


def test_muster_scales_with_population_and_military():
    world = war_world(pop_a=100, mil_a=50)
    civ = world.civ_map["A"]
    base = muster_capacity(world, civ)
    assert base == 200 * (P.MOBILIZATION_BASE_PERMILLE + P.MOBILIZATION_PER_MILITARY_PERMILLE * 50) // 1000
    civ.military = 90
    assert muster_capacity(world, civ) > base
    # Enlisted soldiers count against the mobilization ceiling.
    ctx, war = start_war(world)
    place_army(world, "A", "Brook", 200 * P.MAX_MOBILIZATION_PERMILLE // 1000, war.war_key)
    assert muster_capacity(world, civ) == 0


def test_raise_army_aggregate_mode_pays_and_stages_toward_target():
    world = war_world()
    ctx, war = start_war(world)
    civ = world.civ_map["A"]
    treasury = civ.treasury
    expected = muster_capacity(world, civ)
    army = raise_army(ctx, civ, war, "Dun")
    assert army is not None
    assert army.region == "Brook"  # own region closest to Dun
    assert army.soldiers == army.raised == expected
    assert army.rations == army.soldiers * P.POLICY.carried_limit
    assert army.roster == []
    assert civ.treasury == treasury - max(1, army.soldiers * P.RAISE_COST_PER_10_SOLDIERS // 10)
    assert army.name.startswith("The First Host of A")
    assert any(e.event_type == "army_raised" for e in ctx.events)
    # Cooldown blocks an immediate second muster.
    assert raise_army(ctx, civ, war, "Dun") is None
    assert not can_raise(ctx, civ)


def test_raise_army_refuses_when_broke_or_tiny():
    world = war_world(treasury_a=0)
    ctx, war = start_war(world)
    assert raise_army(ctx, world.civ_map["A"], war, "Dun") is None
    world = war_world(pop_a=4)
    ctx, war = start_war(world)
    assert raise_army(ctx, world.civ_map["A"], war, "Dun") is None


def test_aggregate_casualties_drain_population_permanently():
    world = war_world()
    ctx, war = start_war(world)
    army = place_army(world, "A", "Brook", 10, war.war_key)
    before = sum(r.population for r in world.regions if r.controller == "A")
    killed = apply_casualties(ctx, army, 4, cause="battle")
    after = sum(r.population for r in world.regions if r.controller == "A")
    assert killed == 4 and army.soldiers == 6 and army.casualties == 4
    assert before - after == 4
    assert apply_casualties(ctx, army, 99, cause="battle") == 6 and army.soldiers == 0


def test_desertion_releases_without_killing():
    world = war_world()
    ctx, war = start_war(world)
    army = place_army(world, "A", "Brook", 10, war.war_key)
    before = sum(r.population for r in world.regions)
    assert release_soldiers(ctx, army, 3) == 3
    assert army.soldiers == 7 and army.deserted == 3
    assert sum(r.population for r in world.regions) == before


def _agent_world():
    world = war_world()
    world.agent_mode = "hybrid"
    # (id, region, occupation, civ_affinity): A is civ 0, holds regions 0-1.
    rows = [(1, 0, 0, 0), (2, 0, 1, 0), (3, 1, 1, 0), (4, 1, 0, 0), (5, 1, 2, 0),
            (6, 2, 1, 1), (7, 0, 1, 1), (8, 1, 1, 0), (9, 0, 1, 0)]
    bridge = FakeBridge(rows)
    world._agent_bridge = bridge
    return world, bridge


def test_select_recruits_prefers_soldiers_near_staging_and_skips_named():
    world, bridge = _agent_world()
    bridge.named_agents[9] = "Hero"
    ctx = build_context(world, bridge=bridge)
    picks = select_recruits(ctx, world.civ_map["A"], "Brook", 4)
    # Soldiers of civ 0 first (Brook before Avalon), then farmers; never priests,
    # other civs' agents, or named characters.
    assert [aid for aid, _ in picks] == [3, 8, 2, 4]
    assert all(reg in (0, 1) for _, reg in picks)


def test_native_casualties_queue_exact_roster_ids():
    world, bridge = _agent_world()
    ctx, war = start_war(world)
    ctx.bridge = bridge
    army = raise_army(ctx, world.civ_map["A"], war, "Dun")
    assert army is not None and len(army.roster) == army.soldiers >= P.MIN_ARMY
    roster_ids = {aid for aid, _ in army.roster}
    killed = apply_casualties(ctx, army, 2, cause="battle")
    assert killed == 2 and len(bridge._sim.queued) == 2
    assert set(bridge._sim.queued) <= roster_ids
    assert not set(bridge._sim.queued) & {aid for aid, _ in army.roster}
    assert army.soldiers == len(army.roster)


def test_reconcile_rosters_drops_natural_deaths():
    world, bridge = _agent_world()
    ctx, war = start_war(world)
    army = place_army(world, "A", "Brook", 3, war.war_key, roster=[(2, 0), (3, 1), (8, 1)])
    survivors = FakeSnapshot([(2, 0, 1, 0), (8, 0, 1, 0)])
    assert reconcile_rosters(world, survivors) == 1
    assert army.roster == [(2, 0), (8, 0)] and army.soldiers == 2 and army.casualties == 1


def test_rebind_rosters_after_pool_change():
    world, bridge = _agent_world()
    ctx, war = start_war(world)
    ctx.bridge = bridge
    army = place_army(world, "A", "Brook", 3, war.war_key, roster=[(901, 0), (902, 1), (903, 1)])
    rebind_rosters(ctx)  # ids 901-903 do not exist in this pool
    assert len(army.roster) == 3 and all(aid < 10 for aid, _ in army.roster)
    marker = world._war_roster_sim
    rebind_rosters(ctx)  # same pool: no-op
    assert world._war_roster_sim == marker


def test_off_mode_rebind_clears_stale_rosters():
    world = war_world()
    ctx, war = start_war(world)
    army = place_army(world, "A", "Brook", 3, war.war_key, roster=[(1, 0), (2, 0), (3, 1)])
    rebind_rosters(ctx)
    assert army.roster == [] and army.soldiers == 3


def test_general_assignment_and_death_in_aggregate_mode():
    world = war_world()
    civ = world.civ_map["A"]
    gp = GreatPerson(name="Varro", role="general", trait="bold", civilization="A",
                     origin_civilization="A", born_turn=0)
    civ.great_persons.append(gp)
    ctx, war = start_war(world)
    army = raise_army(ctx, civ, war, "Dun")
    assert army.general == "Varro"
    assert kill_general(ctx, army, "Crag") == "Varro"
    assert not gp.alive and gp.fate == "dead" and gp in world.retired_persons
    assert army.general is None
