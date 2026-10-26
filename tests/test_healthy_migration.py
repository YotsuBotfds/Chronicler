"""Healthy-world migration drivers through the native agent tick.

The drivers live in Rust (chronicler-agents/src/migration_drivers.rs); there
is no Python mirror of the decision model. These tests drive the real
extension through AgentBridge and read the native migration budget.
"""
from __future__ import annotations

import pytest

from chronicler.agent_bridge import AgentBridge

DRIVER_TERMS = (
    "low_satisfaction", "opp_satisfaction", "opp_capacity", "opp_food", "opp_river",
    "opp_news", "persecution", "famine_memory", "battle_memory", "conquest_memory",
    "persecution_memory", "safety_need", "material_need", "spiritual_need",
    "frontier", "wage", "chain", "urban", "social_need", "learning",
)


def _require_native():
    chronicler_agents = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(chronicler_agents, "AgentSimulator", None), type):
        pytest.skip("requires the chronicler_agents Rust extension")


def _frontier_world(make_world, *, internal: bool):
    """Civ0 holds a full region (30 of 30) next to an under-filled one (12 of
    60) on the same grain land, which it rules too (internal) or Civ1 rules."""
    world = make_world(num_civs=2)
    world.agent_mode = "hybrid"
    full, empty = world.regions
    full.carrying_capacity, full.population = 30, 30
    empty.carrying_capacity, empty.population = 60, 12
    full.adjacencies = [empty.name]
    empty.adjacencies = [full.name]
    for region in (full, empty):
        # Grain land: a year's harvest per farmer 2.0 x 0.95 x 0.8 x 0.6 = 0.91.
        region.resource_types = [0, 255, 255]
        region.resource_base_yields = [2.0, 0.0, 0.0]
    civ0, civ1 = world.civilizations
    if internal:
        empty.controller = civ0.name
        civ0.regions = [full.name, empty.name]
        civ1.regions = []
    civ0.population = sum(r.population for r in world.regions if r.controller == civ0.name)
    civ1.population = sum(r.population for r in world.regions if r.controller == civ1.name)
    return world


def _run(world, turns: int):
    bridge = AgentBridge(world, mode="hybrid")
    moves, budget = [], {}
    for turn in range(1, turns + 1):
        snap = bridge.get_snapshot()
        ages = dict(zip(snap.column("id").to_pylist(), snap.column("age").to_pylist()))
        before = len(world.agent_events_raw)
        world.turn = turn
        bridge.tick(world)
        for event in world.agent_events_raw[before:]:
            if event.event_type == "migration":
                moves.append((event.region, event.target_region, ages.get(event.agent_id)))
        for key, value in bridge._sim.get_migration_driver_stats().items():
            budget[key] = budget.get(key, 0.0) + value
    return moves, budget


def test_native_migration_budget_reports_every_term(make_world):
    _require_native()
    _, budget = _run(_frontier_world(make_world, internal=True), 1)
    expected = {"evaluated", "decided", "unexplained"}
    expected |= {f"{kind}_{t}" for kind in ("share", "present", "follow") for t in DRIVER_TERMS}
    expected |= {f"{kind}_{driver}" for kind in ("open", "gate")
                 for driver in ("frontier", "wage", "chain", "urban", "learning")}
    expected |= {f"{kind}_age_{band}" for kind in ("decided", "voluntary")
                 for band in ("under20", "20_34", "35_49", "50_64", "65plus")}
    assert set(budget) == expected
    assert budget["evaluated"] > 0
    assert sum(budget[f"share_{t}"] for t in DRIVER_TERMS) == pytest.approx(
        budget["decided"] - budget["unexplained"])


def test_native_migration_budget_is_reset_every_tick(make_world):
    _require_native()
    world = _frontier_world(make_world, internal=True)
    bridge = AgentBridge(world, mode="hybrid")
    for turn in range(1, 4):
        alive_before = bridge.get_snapshot().num_rows
        world.turn = turn
        bridge.tick(world)
        budget = bridge._sim.get_migration_driver_stats()
        assert 0 < budget["evaluated"] <= alive_before
        assert budget["decided"] <= budget["evaluated"]


def test_native_frontier_settlement_stays_inside_the_realm(make_world):
    """Young farmers leave the full region for the emptier land of their own
    realm; a foreign-ruled neighbour draws no frontier settlers."""
    _require_native()
    internal_moves, internal = _run(_frontier_world(make_world, internal=True), 6)
    _, foreign = _run(_frontier_world(make_world, internal=False), 6)

    assert internal["share_frontier"] > 0
    assert internal["open_frontier"] > 0
    assert foreign["share_frontier"] == 0
    assert foreign["open_frontier"] == 0
    settlers = [m for m in internal_moves if (m[0], m[1]) == (0, 1)]
    assert len(settlers) >= 3
    assert not [m for m in internal_moves if (m[0], m[1]) == (1, 0)]
    # Life course: roots are zero up to 35 and grow with age, so settlers are
    # mostly young adults (household followers, of any age, come along with
    # them).
    ages = sorted(age for _, _, age in settlers if age is not None)
    assert ages and ages[len(ages) // 2] <= 35
