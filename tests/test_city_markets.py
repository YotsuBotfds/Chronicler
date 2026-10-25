"""Merchant routing by market prices (2026-10 city markets).

Every merchant cargo travels by its price gap: the native economy reports
its demand and post-trade supply per goods category, the region batch
carries them to the merchant planner, trade packets advertise markets, and
merchants plan against the cargo already committed to each market. See
``docs/integration/city-markets.md``. Native tests run the real extension.
"""
from __future__ import annotations

import pyarrow as pa
import pytest

import chronicler.cities as C
from chronicler.agent_bridge import build_region_batch
from chronicler.cities_state import CITY, GREAT_CITY, TOWN, City
from chronicler.economy import CATEGORIES, EconomyResult
from chronicler.models import Army
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


# --- Cities as markets (--cities) ---------------------------------------------------

FROST, VERDANT, THORNWOOD, AMBER = 0, 2, 4, 5   # template seed 42 (tests/test_cities.py)


def _city_world():
    world = generate_world(seed=42)
    C.set_cities_enabled(world, True)
    return world


def _add_city(world, sid: int, region: int, rank: int) -> City:
    city = City(settlement_id=sid, region=region, name=f"Town {sid}", founded_turn=0,
                founder=-1, lord=-1, rank=rank)
    world.cities.cities.append(city)
    return city


def _rows(*groups):
    """Agent rows: groups of (count, region, occupation, settlement_id)."""
    region, occupation, sid = [], [], []
    for count, r, o, s in groups:
        region += [r] * count
        occupation += [o] * count
        sid += [s] * count
    return pa.record_batch({
        "region": pa.array(region, type=pa.uint16()),
        "occupation": pa.array(occupation, type=pa.uint8()),
        "settlement_id": pa.array(sid, type=pa.uint16()),
    })


def test_economy_columns_count_city_farmers_and_craftsmen():
    world = _city_world()
    _add_city(world, 3, VERDANT, CITY)
    _add_city(world, 4, VERDANT, TOWN)
    _add_city(world, 5, AMBER, GREAT_CITY)
    rows = _rows(
        (10, VERDANT, 0, 0),   # rural farmers
        (6, VERDANT, 0, 3),    # city farmers
        (4, VERDANT, 0, 4),    # town farmers
        (5, VERDANT, 2, 3),    # city merchants
        (3, VERDANT, 1, 3),    # city soldiers (no craft demand)
        (8, AMBER, 0, 5),      # every Amber farmer lives in the great city
        (2, AMBER, 3, 5),      # scholars
    )
    cols = C.economy_columns(world, rows)
    factor, craft = cols["farm_labor_factor"], cols["craft_raw_demand"]
    # Verdant: 20 farmers, 6 in the city and 4 in the town.
    labor = C.URBAN_FARM_LABOR
    assert factor[VERDANT] == pytest.approx(1.0 - (1 - labor[CITY]) * 6 / 20 - (1 - labor[TOWN]) * 4 / 20)
    assert factor[AMBER] == pytest.approx(C.URBAN_FARM_LABOR[GREAT_CITY])
    assert factor[FROST] == 1.0
    assert craft[VERDANT] == pytest.approx(C.CRAFT_RAW_PER_RESIDENT * (6 + 5 + 4))
    assert craft[AMBER] == pytest.approx(C.CRAFT_RAW_PER_RESIDENT * 10)
    assert craft[FROST] == 0.0
    # Without cities every region is at 1.0 and 0.0; switched off, no columns.
    world.cities.cities.clear()
    cols = C.economy_columns(world, rows)
    assert set(cols["farm_labor_factor"]) == {1.0} and set(cols["craft_raw_demand"]) == {0.0}
    C.set_cities_enabled(world, False)
    assert C.economy_columns(world, rows) is None
    assert C.economy_columns(_city_world(), None) is None


def test_economy_input_batch_gains_the_city_columns_only_when_on():
    from chronicler.economy import build_economy_region_input_batch
    world = _city_world()
    _add_city(world, 3, VERDANT, CITY)
    rows = _rows((4, VERDANT, 0, 3), (4, VERDANT, 0, 0))
    base = build_economy_region_input_batch(world)
    batch = C.with_economy_columns(world, base, rows)
    assert batch.schema.names == base.schema.names + ["farm_labor_factor", "craft_raw_demand"]
    assert batch.column("farm_labor_factor").to_pylist()[VERDANT] == pytest.approx(
        1.0 - (1.0 - C.URBAN_FARM_LABOR[CITY]) * 0.5)
    C.set_cities_enabled(world, False)
    assert C.with_economy_columns(world, base, rows) is base


def _edges(pairs):
    return pa.record_batch({
        "from_region": pa.array([a for a, _ in pairs], type=pa.uint16()),
        "to_region": pa.array([b for _, b in pairs], type=pa.uint16()),
        "is_river": pa.array([False] * len(pairs)),
        "transport_cost": pa.array([1.0] * len(pairs), type=pa.float32()),
    })


def test_a_besieged_or_occupied_city_is_cut_off_from_merchants():
    world = _city_world()
    _add_city(world, 3, VERDANT, CITY)
    pairs = [(VERDANT, THORNWOOD), (THORNWOOD, VERDANT), (AMBER, FROST), (FROST, AMBER)]
    batch = _edges(pairs)
    assert C.merchant_route_graph(world, batch) is batch          # at peace
    verdant = world.regions[VERDANT]
    kethani = world.civilizations[1].name
    world.war_state.armies.append(Army(army_id="a1", name="Host", civ=kethani, war_key="w",
                                       region=verdant.name, home_region=world.regions[AMBER].name,
                                       phase="sieging"))
    assert C.cut_off_regions(world) == {VERDANT}
    cut = C.merchant_route_graph(world, batch)
    assert list(zip(cut.column("from_region").to_pylist(), cut.column("to_region").to_pylist())) == \
        [(AMBER, FROST), (FROST, AMBER)]
    # Marching past is no siege; the lord's own army is none either.
    world.war_state.armies[0].phase = "marching"
    assert C.cut_off_regions(world) == set()
    world.war_state.armies[0].phase = "sieging"
    world.war_state.armies[0].civ = verdant.controller
    assert C.cut_off_regions(world) == set()
    # An enemy occupation cuts it off as well.
    verdant.occupied_by = kethani
    assert C.cut_off_regions(world) == {VERDANT}
    C.set_cities_enabled(world, False)
    assert C.merchant_route_graph(world, batch) is batch


def test_merchant_imports_raise_a_citys_commerce():
    from types import SimpleNamespace
    world = _city_world()
    city = _add_city(world, 3, VERDANT, CITY)
    city.size = 25.0
    verdant = world.regions[VERDANT]
    k = C.scale(world)

    def economy(imports: float):
        return SimpleNamespace(
            food_sufficiency={verdant.name: 1.0}, trade_route_counts={verdant.name: 1},
            imports_by_region={verdant.name: {"food": imports, "raw_material": 0.0, "luxury": 0.0}},
            market_demand={verdant.name: (10.0, 0.0, 0.0)})

    commerce = []
    for imports in (0.0, 2.0, 50.0):
        city.wealth = 0.0
        C._commerce(C._Tick(world, None, None, economy(imports)), city, verdant, 1.0, k)
        commerce.append(city.commerce)
    base = 1.0 + C.ROUTE_ACCESS
    assert commerce[1] == pytest.approx(commerce[0] * (base + C.TURNOVER_ACCESS * 0.2) / base, rel=1e-3)
    assert commerce[2] == pytest.approx(commerce[0] * (base + C.TURNOVER_CAP) / base, rel=1e-3)


@pytest.mark.native
def test_native_city_economy_columns_are_consumed_and_reset_each_call(make_world):
    """The economy reads farm_labor_factor and craft_raw_demand on every call
    and keeps nothing: a call without the columns is a full-labour call."""
    _require_native()
    from chronicler.agent_bridge import AgentBridge
    from chronicler.economy import build_economy_region_input_batch, build_economy_trade_route_batch
    world = make_world(num_civs=1)
    world.agent_mode = "hybrid"
    world.regions[0].population = 40
    # Constant returns to farm labour, so half the labour grows half the food.
    world.tuning_overrides = {"economy.farm_reference_density": 0.0}
    bridge = AgentBridge(world, mode="hybrid")
    world.turn = 1
    bridge.tick(world)
    routes = build_economy_trade_route_batch(world, active_trade_routes=[])

    def call(factor=None, craft=None):
        batch = build_economy_region_input_batch(world)
        data = {n: batch.column(n) for n in batch.schema.names}
        if factor is not None:
            data["farm_labor_factor"] = pa.array([factor], type=pa.float32())
            data["craft_raw_demand"] = pa.array([craft], type=pa.float32())
        rr, _civ, _obs, _up, cons = bridge._sim.tick_economy(pa.record_batch(data), routes, 0, False, 1.0)
        production = cons.column("production").to_pylist()[0]
        raw_demand = rr.column("market_demand_raw_material").to_pylist()[0]
        return production, raw_demand

    full, raw = call()
    half, raw_city = call(0.5, 2.0)
    again, raw_again = call()
    assert full > 0
    assert half == pytest.approx(full * 0.5, rel=1e-4)
    assert raw_city == pytest.approx(raw + 2.0)
    assert (again, raw_again) == (full, raw)


@pytest.mark.native
def test_native_hybrid_cities_draw_on_the_economy(tmp_path, monkeypatch):
    """With --cities a hybrid run sends the city columns to the economy every
    turn, and city regions' farmers give part of their labour to the town."""
    _require_native()
    from chronicler.main import _build_parser, execute_run
    sent = []
    real = C.with_economy_columns

    def spy(world, region_input, snapshot):
        out = real(world, region_input, snapshot)
        if "farm_labor_factor" in out.schema.names:
            sent.append((out.column("farm_labor_factor").to_pylist(),
                         out.column("craft_raw_demand").to_pylist()))
        return out

    monkeypatch.setattr(C, "with_economy_columns", spy)
    out = tmp_path / "hyb"
    execute_run(_build_parser().parse_args([
        "--seed", "42", "--turns", "40", "--civs", "4", "--regions", "8", "--agents", "hybrid",
        "--simulate-only", "--cities", "--output", str(out / "chronicle.md")]))
    assert len(sent) >= 35, "the city columns reach the economy every turn"
    assert any(min(f) < 1.0 for f, _ in sent)
    assert any(max(c) > 0.0 for _, c in sent)
    assert all(0.0 <= v <= 1.0 for f, _ in sent for v in f)
