"""M13 contracts disband at war end; the same grant cannot be hired again."""

from types import SimpleNamespace

import pyarrow as pa
import pytest

from chronicler.accumulator import StatAccumulator
from chronicler.agent_bridge import AgentBridge
from chronicler.bundle import assemble_bundle
from chronicler.demand_signals import DemandSignalManager
from chronicler.models import WorldState
from chronicler.politics import check_restoration, create_exile
from chronicler.politics_bridge import _materialize_restored_civ
from chronicler.simulation import apply_automatic_effects
from chronicler.tech_focus import TechFocus, apply_focus_effects
from chronicler.tuning import K_RESTORATION_BASE_PROB


def company(strength=6):
    return dict(strength=strength, origin_civ="Civ1", location="Civ1_region",
                available=True, hired_by=None)


def tick(world, route="direct", acc=None):
    if route != "direct":
        acc = acc or StatAccumulator()
    apply_automatic_effects(world, acc=acc, cross_routes=[])
    if route == "aggregate":
        acc.apply(world)
    elif route == "agents":
        acc.apply_keep(world)
    world.turn += 1
    return acc


def at_war(make_world):
    world = make_world()
    hirer, enemy = world.civilizations
    hirer.military, enemy.military = 20, 80
    hirer.treasury = enemy.treasury = 100
    world.mercenary_companies = [company()]
    world.active_wars = [(hirer.name, enemy.name)]
    return world, hirer, enemy


@pytest.mark.parametrize("route", ["direct", "aggregate", "agents"])
def test_disband_prevents_same_company_rehire(make_world, route):
    world, hirer, enemy = at_war(make_world)
    tick(world, route)
    expected = 20 if route == "agents" else 26
    assert hirer.military == expected
    assert hirer.treasury == 87  # war costs 3, existing hire price 10
    assert world.mercenary_companies[0]["hired_by"] == hirer.name
    world.active_wars = []
    tick(world, route)
    assert world.mercenary_companies == []
    assert hirer.military == expected
    assert hirer.treasury == 87
    world.active_wars = [(hirer.name, enemy.name)]
    tick(world, route)
    assert world.mercenary_companies == []
    assert hirer.military == expected  # baseline bug: 26 becomes 32
    assert hirer.treasury == 84  # another war cost, no second hire payment


@pytest.mark.parametrize("route", ["direct", "aggregate", "agents"])
@pytest.mark.parametrize("military", [0, 17, 33, 100])
def test_disband_preserves_other_military_and_repeated_cleanup(make_world, route, military):
    world, hirer, _ = at_war(make_world)
    tick(world, route)
    # Casualties, recruitment, or native writeback can change the shared scalar.
    hirer.military = military
    world.active_wars = []
    tick(world, route)
    tick(world, route)
    assert hirer.military == military
    assert world.mercenary_companies == []


@pytest.mark.parametrize("route", ["direct", "aggregate"])
@pytest.mark.parametrize("initial", [0, 95, 100])
def test_hire_bounds_and_capped_disband(make_world, route, initial):
    world, hirer, enemy = at_war(make_world)
    hirer.military, enemy.military = initial, 100
    hirer.treasury = 500  # wins military ties
    tick(world, route)
    assert hirer.military == min(100, initial + 6)
    world.active_wars = []
    tick(world, route)
    assert hirer.military == min(100, initial + 6)
    assert world.mercenary_companies == []


@pytest.mark.parametrize("route", ["direct", "aggregate", "agents"])
def test_overlapping_wars_do_not_end_contract_early(make_world, route):
    world = make_world(num_civs=3)
    hirer, b, c = world.civilizations
    hirer.military, b.military, c.military = 20, 80, 80
    world.active_wars = [(hirer.name, b.name), (hirer.name, c.name)]
    world.mercenary_companies = [company()]
    tick(world, route)
    world.active_wars.pop()
    tick(world, route)
    assert len(world.mercenary_companies) == 1
    assert world.mercenary_companies[0]["hired_by"] == hirer.name
    world.active_wars = []
    tick(world, route)
    assert world.mercenary_companies == []
    assert hirer.military == (20 if route == "agents" else 26)


@pytest.mark.parametrize("route", ["direct", "aggregate", "agents"])
def test_multiple_contracts_disband_independently(make_world, route):
    world = make_world(num_civs=3)
    a, b, c = world.civilizations
    a.military, b.military, c.military = 10, 30, 80
    world.active_wars = [(a.name, c.name), (b.name, c.name)]
    world.mercenary_companies = [company(8)]
    tick(world, route)
    assert world.mercenary_companies[0]["hired_by"] == a.name
    b.military = 5
    world.mercenary_companies.extend([company(6), company(4)])
    tick(world, route)
    assert [m["hired_by"] for m in world.mercenary_companies] == [a.name, b.name, b.name]
    a.military += 3
    b.military -= 2
    saved = (a.military, b.military, c.military)
    world.active_wars = [(a.name, c.name)]
    tick(world, route)
    assert len(world.mercenary_companies) == 1
    assert world.mercenary_companies[0]["hired_by"] == a.name
    assert (a.military, b.military, c.military) == saved
    world.active_wars = []
    tick(world, route)
    assert world.mercenary_companies == []
    assert (a.military, b.military, c.military) == saved


@pytest.mark.parametrize("route", ["direct", "aggregate", "agents"])
@pytest.mark.parametrize("cause", ["company_destroyed", "hirer_eliminated", "hirer_missing"])
def test_terminal_contracts_removed_despite_stale_war(make_world, route, cause):
    world, hirer, enemy = at_war(make_world)
    tick(world, route)
    expected = hirer.military
    if cause == "company_destroyed":
        world.mercenary_companies[0]["strength"] = 0
    elif cause == "hirer_eliminated":
        hirer.regions = []
        world.regions[0].controller = None
    else:
        world.civilizations.remove(hirer)
    tick(world, route)
    assert world.mercenary_companies == []
    assert hirer.military == expected
    assert enemy.military == 80


def test_dead_company_and_dead_hirer_cannot_be_hired(make_world):
    world = make_world()
    hirer, enemy = world.civilizations
    hirer.regions = []
    world.regions[0].controller = None
    world.active_wars = [(hirer.name, enemy.name)]
    world.mercenary_companies = [company(0), company(6)]
    tick(world)
    assert len(world.mercenary_companies) == 1
    assert world.mercenary_companies[0]["hired_by"] == enemy.name
    assert hirer.military == 30
    assert enemy.military == 36


@pytest.mark.parametrize("route", ["direct", "aggregate", "agents"])
def test_serialization_cannot_resurrect_disbanded_company(make_world, tmp_path, route):
    world, _, _ = at_war(make_world)
    tick(world, route)
    path = tmp_path / "active_contract.json"
    world.save(path)
    world = WorldState.load(path)  # unchanged legacy company dict schema
    assert world.mercenary_companies[0]["hired_by"] == "Civ0"
    world.active_wars = []
    tick(world, route)
    world.save(path)
    world = WorldState.load(path)
    bundle = assemble_bundle(world, [], [], {}, "test", "test", None)
    world = WorldState.model_validate(bundle["world_state"])
    assert world.mercenary_companies == []
    military = world.civilizations[0].military
    world.active_wars = [("Civ0", "Civ1")]
    tick(world, route)
    assert world.civilizations[0].military == military
    assert world.mercenary_companies == []
    fresh = make_world()
    tick(fresh, route)
    assert fresh.mercenary_companies == []
    assert fresh.civilizations[0].military == 30


@pytest.mark.parametrize("mode", ["hybrid", "shadow", "demographics-only"])
def test_off_to_agent_to_off_disbands_without_mode_inference(make_world, mode):
    world, hirer, enemy = at_war(make_world)
    tick(world, "aggregate")
    world.agent_mode = mode
    world.active_wars = []
    tick(world, "agents")
    assert hirer.military == 26
    assert world.mercenary_companies == []
    world.agent_mode = "off"
    world.active_wars = [(hirer.name, enemy.name)]
    tick(world, "aggregate")
    assert hirer.military == 26


def test_immediate_focus_and_queued_military_effects_survive_disband(make_world):
    world, hirer, enemy = at_war(make_world)
    hirer.military, enemy.military = 95, 100
    hirer.treasury = 500
    acc = StatAccumulator()
    acc.add(0, hirer, "military", -5, "signal")
    apply_automatic_effects(world, acc=acc, cross_routes=[])
    apply_focus_effects(hirer, TechFocus.METALLURGY)  # immediate Phase 4 effect
    acc.apply(world)
    assert hirer.military == 100
    world.active_wars = []
    acc = StatAccumulator()
    acc.add(0, hirer, "military", -7, "signal")
    tick(world, "aggregate", acc)
    assert hirer.military == 93
    assert world.mercenary_companies == []


@pytest.mark.parametrize("route", ["aggregate", "agents"])
def test_repeated_cleanup_before_accumulator_flush(make_world, route):
    world, hirer, _ = at_war(make_world)
    tick(world, route)
    military = hirer.military
    world.active_wars = []
    acc = StatAccumulator()
    apply_automatic_effects(world, acc=acc, cross_routes=[])
    apply_automatic_effects(world, acc=acc, cross_routes=[])
    assert not any(c.stat == "military" for c in acc._changes)
    if route == "aggregate":
        acc.apply(world)
    else:
        acc.apply_keep(world)
    assert hirer.military == military
    assert world.mercenary_companies == []


@pytest.mark.parametrize("restoration", ["python", "native_payload"])
def test_restoration_reset_is_not_debited_by_old_contract(make_world, restoration):
    world, hirer, enemy = at_war(make_world)
    tick(world, "aggregate")
    create_exile(hirer, enemy, world)
    region = world.regions[0]
    region.controller = enemy.name
    enemy.regions.append(region.name)
    hirer.regions = []
    world.active_wars = []
    enemy.stability = 10
    if restoration == "python":
        world.tuning_overrides[K_RESTORATION_BASE_PROB] = 1
        assert any(e.event_type == "restoration" for e in check_restoration(world))
    else:
        # Exercise the existing native restoration materializer, not Rust itself.
        _materialize_restored_civ(world, {
            "source_ref_kind": 0, "source_ref_id": 1,
            "target_ref_kind": 0, "target_ref_id": 0,
            "region_indices": [0], "stat_military": 20,
        }, {})
    assert hirer.military == 20
    tick(world, "aggregate")
    assert hirer.military == 20
    assert world.mercenary_companies == []


def test_native_writeback_and_bridge_reset_are_not_debited(make_world):
    world, hirer, _ = at_war(make_world)
    tick(world, "aggregate")
    world.agent_mode = "hybrid"
    bridge = AgentBridge.__new__(AgentBridge)
    aggs = pa.table({"civ_id": [0, 1], "military": [47, 80],
                     "economy": [40, 40], "culture": [30, 30], "stability": [50, 50]})
    pops = pa.table({"region_id": [0, 1], "alive_count": [50, 50]})
    # Exercise Python writeback with the native Arrow protocol; no Rust required.
    bridge._sim = SimpleNamespace(get_aggregates=lambda: aggs,
                                  get_region_populations=lambda: pops)
    bridge._write_back(world)
    assert hirer.military == 47
    for attr in (
        "_event_window", "named_agents", "gp_by_agent_id", "_pending_dynasty_events",
        "_origin_regions", "_departure_turns", "displacement_by_region", "_gini_by_civ",
        "_wealth_stats", "_relationship_stats_history", "_household_stats_history",
        "_merchant_trip_stats_history", "_knowledge_stats_history",
    ):
        setattr(bridge, attr, {})
    bridge._demand_manager = DemandSignalManager()
    bridge.reset()
    assert len(world.mercenary_companies) == 1  # cache reset does not end a world contract
    world.active_wars = []
    tick(world, "agents")
    assert hirer.military == 47
    assert world.mercenary_companies == []


def test_disband_frees_cap_and_preserves_spawn_accounting(make_world):
    world, _, enemy = at_war(make_world)
    world.mercenary_companies = [company() for _ in range(3)]
    tick(world)
    assert len(world.mercenary_companies) == 3
    world.active_wars = []
    tick(world)
    assert world.mercenary_companies == []
    enemy.military, enemy.last_income, enemy.merc_pressure_turns = 60, 10, 2
    events = apply_automatic_effects(world, cross_routes=[])
    assert [e.event_type for e in events].count("mercenary_spawned") == 1
    assert enemy.military == 50
    assert len(world.mercenary_companies) == 1
    assert world.mercenary_companies[0]["strength"] == 8  # new idle company decays by 2


@pytest.mark.parametrize("route", ["direct", "aggregate", "agents"])
def test_unhired_decay_still_removes_only_dead_companies(make_world, route):
    world = make_world()
    world.mercenary_companies = [company(1), company(3), company(6)]
    tick(world, route)
    assert [m["strength"] for m in world.mercenary_companies] == [1, 4]
    assert all(m["available"] and m["hired_by"] is None for m in world.mercenary_companies)
    assert [c.military for c in world.civilizations] == [30, 30]
