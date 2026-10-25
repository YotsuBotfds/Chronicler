"""Merchant routing by market prices (2026-10 city markets).

Every merchant cargo travels by its price gap: the native economy reports
its demand and post-trade supply per goods category, the region batch
carries them to the merchant planner, trade packets advertise markets, and
merchants plan against the cargo already committed to each market. See
``docs/integration/city-markets.md``. Native tests run the real extension.
"""
from __future__ import annotations

import pytest

from chronicler.agent_bridge import build_region_batch
from chronicler.economy import CATEGORIES, EconomyResult
from chronicler.world_gen import generate_world

MARKET_COLUMNS = [f"{p}_{c}" for p in ("market_demand", "market_supply") for c in CATEGORIES]


def _require_native():
    chronicler_agents = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(chronicler_agents, "AgentSimulator", None), type):
        pytest.skip("requires the chronicler_agents Rust extension")


def test_region_batch_carries_the_market_columns_of_the_economy_result():
    world = generate_world(seed=42)
    first, second = world.regions[0].name, world.regions[1].name
    result = EconomyResult()
    result.market_demand = {first: (5.0, 0.9, 0.2), second: (3.0, 0.0, 0.0)}
    result.market_supply = {first: (4.0, 0.3, 0.0), second: (6.0, 2.0, 0.0)}
    batch = build_region_batch(world, result)
    for name in MARKET_COLUMNS:
        assert name in batch.schema.names
    col = {name: batch.column(name).to_pylist() for name in MARKET_COLUMNS}
    assert col["market_demand_food"][:2] == [5.0, 3.0]
    assert col["market_demand_raw_material"][0] == pytest.approx(0.9)
    assert col["market_supply_raw_material"][:2] == [pytest.approx(0.3), 2.0]
    assert col["market_demand_luxury"][0] == pytest.approx(0.2)
    # Regions the result does not cover, and a turn without a result, have no market.
    assert all(v == 0.0 for v in col["market_demand_food"][2:])
    empty = build_region_batch(world, None)
    assert all(v == 0.0 for name in MARKET_COLUMNS for v in empty.column(name).to_pylist())


@pytest.mark.native
def test_native_economy_reports_demand_and_supply_by_category(tmp_path, monkeypatch):
    """The economy result carries the kernel's demand and post-trade supply
    per category for every region, each turn."""
    _require_native()
    import chronicler.economy as eco
    from chronicler.main import _build_parser, execute_run
    seen = []
    real = eco.reconstruct_economy_result

    def spy(*args, **kwargs):
        result = real(*args, **kwargs)
        world = args[5]
        seen.append(({r.name: r.population for r in world.regions}, result))
        return result

    monkeypatch.setattr(eco, "reconstruct_economy_result", spy)
    out = tmp_path / "run"
    execute_run(_build_parser().parse_args([
        "--seed", "42", "--turns", "6", "--civs", "4", "--regions", "8", "--agents", "hybrid",
        "--simulate-only", "--output", str(out / "chronicle.md")]))
    assert len(seen) >= 4
    for pops, result in seen[1:]:
        assert set(result.market_demand) == set(pops)
        for name, (food, raw, lux) in result.market_demand.items():
            assert food >= 0 and raw >= 0 and lux >= 0
            supply = result.market_supply[name]
            assert all(s >= 0 for s in supply)
        assert any(d[0] > 0 for d in result.market_demand.values())
        assert any(d[1] > 0 for d in result.market_demand.values()), "soldiers want raw materials"


def _two_region_world(make_world):
    world = make_world(num_civs=2)
    world.agent_mode = "hybrid"
    home, market = world.regions
    home.carrying_capacity = market.carrying_capacity = 60
    home.population, market.population = 30, 20
    home.adjacencies = [market.name]
    market.adjacencies = [home.name]
    civ0, civ1 = world.civilizations
    market.controller = civ0.name
    civ0.regions, civ1.regions = [home.name, market.name], []
    civ0.population, civ1.population = 50, 0
    for region in world.regions:
        region.stockpile.goods = {g: 0.0 for g in region.stockpile.goods}
    home.stockpile.goods["timber"] = 20.0
    return world


@pytest.mark.native
def test_native_market_columns_are_consumed_and_reset_each_turn(make_world):
    """Non-food cargo moves only while the batch carries a market for it:
    the planner reads the columns every tick and returns to no market (0)
    once they are absent."""
    _require_native()
    from chronicler.agent_bridge import AgentBridge
    world = _two_region_world(make_world)
    home, market = world.regions
    bridge = AgentBridge(world, mode="hybrid")
    plans = []
    for turn in range(1, 9):
        world.turn = turn
        if turn <= 3:
            result = EconomyResult()
            result.food_sufficiency = {home.name: 1.0, market.name: 1.0}
            result.market_demand = {home.name: (15.0, 0.0, 0.0), market.name: (10.0, 6.0, 0.0)}
            result.market_supply = {home.name: (15.0, 20.0, 0.0), market.name: (10.0, 0.5, 0.0)}
            bridge._economy_result = result
        else:
            bridge._economy_result = None   # the columns disappear (all 0)
        bridge.tick(world)
        ks = bridge._sim.get_knowledge_stats()
        plans.append(int(ks["merchant_plans_packet_driven"] + ks["merchant_plans_bootstrap"]))
    assert sum(plans[:3]) > 0, plans
    # Merchants still loading or travelling finish their trips; nobody new
    # plans a timber trip once the market is gone.
    assert plans[4:] == [0, 0, 0, 0], plans
