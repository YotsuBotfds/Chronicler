"""Needs calibration (docs/integration/needs-calibration.md).

The region batch carries the controller's harsh rule (martial law) for the
autonomy need, recomputed every batch, and a one-turn raid signal for the
safety need; the native migration budget appends a social-need term after
the earlier ones, so saved driver codes keep their meaning.
"""
from __future__ import annotations

import pytest

from chronicler.agent_bridge import MASS_MIGRATION_BY_DRIVER, build_region_batch
from chronicler.governance_state import CivGovernance, GovernanceInstitution
from chronicler.models import MIGRATION_DRIVER_NAMES, migration_driver_name


def _martial_law(turn: int = 0) -> GovernanceInstitution:
    return GovernanceInstitution(
        institution_type="martial_law", enacted_turn=turn, opposing_faction="cultural",
    )


def test_region_batch_harsh_rule_follows_the_controllers_martial_law(make_world):
    world = make_world(num_civs=2)
    batch = build_region_batch(world)
    assert batch.schema.field("harsh_rule").type.bit_width == 32
    assert batch.column("harsh_rule").to_pylist() == [0.0, 0.0]

    world.civilizations[1].governance = CivGovernance(institutions=[_martial_law()])
    assert build_region_batch(world).column("harsh_rule").to_pylist() == [0.0, 1.0]
    # Another institution is not harsh rule.
    world.civilizations[0].governance = CivGovernance(institutions=[GovernanceInstitution(
        institution_type="written_law", enacted_turn=0, opposing_faction="military",
    )])
    assert build_region_batch(world).column("harsh_rule").to_pylist() == [0.0, 1.0]
    # The region follows its controller, and a repeal clears it next batch.
    world.regions[0].controller = world.civilizations[1].name
    assert build_region_batch(world).column("harsh_rule").to_pylist() == [1.0, 1.0]
    world.civilizations[1].governance = CivGovernance(institutions=[])
    assert build_region_batch(world).column("harsh_rule").to_pylist() == [0.0, 0.0]
    world.regions[0].controller = None
    assert build_region_batch(world).column("harsh_rule").to_pylist() == [0.0, 0.0]


def test_region_batch_raid_signal_is_read_once(make_world):
    """A raid marks its region for one batch; the builder clears it, so the
    next turn's batch carries no stale raid."""
    world = make_world(num_civs=2)
    assert build_region_batch(world).column("raided_this_turn").to_pylist() == [False, False]
    world.regions[1]._raided_this_turn = True
    assert build_region_batch(world).column("raided_this_turn").to_pylist() == [False, True]
    assert build_region_batch(world).column("raided_this_turn").to_pylist() == [False, False]
    world.regions[0]._raided_this_turn = True
    world.regions[1]._raided_this_turn = True
    assert build_region_batch(world).column("raided_this_turn").to_pylist() == [True, True]
    assert build_region_batch(world).column("raided_this_turn").to_pylist() == [False, False]


def test_social_need_driver_is_appended():
    assert MIGRATION_DRIVER_NAMES[:18][-4:] == ("frontier", "wage", "chain", "urban")
    assert MIGRATION_DRIVER_NAMES[18] == "social_need"
    assert len(MIGRATION_DRIVER_NAMES) == 19
    assert migration_driver_name(18) == "social_need"
    assert migration_driver_name(11) == "safety_need"
    assert "social_need" in MASS_MIGRATION_BY_DRIVER


def _require_native():
    chronicler_agents = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(chronicler_agents, "AgentSimulator", None), type):
        pytest.skip("requires the chronicler_agents Rust extension")


@pytest.mark.native
def test_native_migration_budget_names_match_python():
    _require_native()
    from chronicler_agents import AgentSimulator

    sim = AgentSimulator(num_regions=1, seed=1)
    stats = sim.get_migration_driver_stats()
    for name in MIGRATION_DRIVER_NAMES:
        assert f"share_{name}" in stats


def _region_autonomy(bridge, region: int) -> float:
    needs = bridge._sim.get_all_needs().to_pydict()
    values = [a for a, r in zip(needs["autonomy"], needs["region"]) if r == region]
    assert values
    return sum(values) / len(values)


@pytest.mark.native
def test_native_harsh_rule_presses_autonomy_each_turn_and_clears(make_world):
    """Two twin worlds whose second region is ruled by the first region's civ;
    one ruler enacts martial law. The foreign-ruled people lose autonomy faster
    while it lasts; after the repeal the batch carries 0 and the gap stops
    growing."""
    _require_native()
    from chronicler.agent_bridge import AgentBridge

    def setup():
        world = make_world(num_civs=2)
        world.agent_mode = "hybrid"
        for region in world.regions:
            region.population = 40
        bridge = AgentBridge(world, mode="hybrid")
        # Region 1's people (civ 1) come under civ 0.
        world.regions[1].controller = world.civilizations[0].name
        return world, bridge

    plain_world, plain = setup()
    harsh_world, harsh = setup()
    harsh_world.civilizations[0].governance = CivGovernance(institutions=[_martial_law()])

    def tick(world, bridge):
        world.turn += 1
        bridge.tick(world)

    for _ in range(3):
        tick(plain_world, plain)
        tick(harsh_world, harsh)
    gap = _region_autonomy(plain, 1) - _region_autonomy(harsh, 1)
    assert gap > 0.05

    harsh_world.civilizations[0].governance = CivGovernance(institutions=[])
    assert build_region_batch(harsh_world).column("harsh_rule").to_pylist() == [0.0, 0.0]
    for _ in range(3):
        tick(plain_world, plain)
        tick(harsh_world, harsh)
    later_gap = _region_autonomy(plain, 1) - _region_autonomy(harsh, 1)
    assert later_gap < gap
