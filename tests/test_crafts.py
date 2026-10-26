"""Crafts (2026-10): wares made in cities from raw materials, used by every
region's people, traded by merchants. See ``docs/integration/bulk-trade-crafts.md``.
Native tests run the real extension."""
from __future__ import annotations

from types import SimpleNamespace

import pyarrow as pa
import pytest

import chronicler.cities as C
from chronicler.agent_bridge import _FIXED_GOODS, _MARKET_CATEGORIES, build_region_batch
from chronicler.cities_state import CITY, City
from chronicler.economy import (
    CATEGORIES, CATEGORY_GOODS, FIXED_GOODS, SHOCK_CATEGORIES, STORAGE_DECAY, TRANSIT_DECAY,
    EconomyResult, reconstruct_economy_result,
)
from chronicler.world_gen import generate_world

VERDANT = 2   # template seed 42 (tests/test_cities.py)


def _require_native():
    chronicler_agents = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(chronicler_agents, "AgentSimulator", None), type):
        pytest.skip("requires the chronicler_agents Rust extension")


def test_wares_are_the_ninth_good_and_fourth_category():
    assert FIXED_GOODS[8] == "crafts" and _FIXED_GOODS == FIXED_GOODS
    assert CATEGORIES == ("food", "raw_material", "luxury", "craft") == _MARKET_CATEGORIES
    assert CATEGORY_GOODS["craft"] == frozenset({"crafts"})
    assert "craft" not in SHOCK_CATEGORIES, "wares stock swings are not supply shocks"
    assert TRANSIT_DECAY["crafts"] == 0.0 and STORAGE_DECAY["crafts"] == pytest.approx(0.01)


def _result_batches(n: int, crafts: list[float] | None, extra: dict | None = None):
    """Minimal native-shaped economy batches for ``reconstruct_economy_result``."""
    goods = FIXED_GOODS if crafts is not None else FIXED_GOODS[:8]
    rr = {"region_id": pa.array(range(n), type=pa.uint16())}
    for g in goods:
        rr[f"stockpile_{g}"] = pa.array(crafts if g == "crafts" else [1.0] * n, type=pa.float32())
    for name in ("farmer_income_modifier", "food_sufficiency", "merchant_margin", "merchant_trade_income"):
        rr[name] = pa.array([1.0] * n, type=pa.float32())
    rr["trade_route_count"] = pa.array([0] * n, type=pa.uint16())
    cats = CATEGORIES if crafts is not None else CATEGORIES[:3]
    for prefix in ("market_demand", "market_supply"):
        for cat in cats:
            rr[f"{prefix}_{cat}"] = pa.array([2.0] * n, type=pa.float32())
    rr.update(extra or {})
    civ = pa.record_batch({"civ_id": pa.array([], type=pa.uint8()),
                           **{k: pa.array([], type=pa.float32()) for k in ("treasury_tax", "tithe_base", "priest_tithe_share")}})
    obs = {"region_id": pa.array(range(n), type=pa.uint16())}
    for cat in cats:
        obs[f"imports_{cat}"] = pa.array([0.0] * n, type=pa.float32())
        obs[f"stockpile_{cat}"] = pa.array([0.0] * n, type=pa.float32())
    obs["import_share"] = pa.array([0.0] * n, type=pa.float32())
    obs["trade_dependent"] = pa.array([False] * n)
    up = pa.record_batch({k: pa.array([], type=pa.uint16()) for k in ("dest_region_id", "source_ordinal", "source_region_id")})
    cons = pa.record_batch({k: pa.array([0.0], type=pa.float64()) for k in (
        "production", "transit_loss", "consumption", "storage_loss", "cap_overflow", "clamp_floor_loss")})
    return pa.record_batch(rr), civ, pa.record_batch(obs), up, cons


def test_reconstruct_reads_wares_and_keeps_old_stock_keys_without_them():
    world = generate_world(seed=42)
    n = len(world.regions)
    keys_before = [set(r.stockpile.goods) for r in world.regions]
    crafts = [0.0] * n
    crafts[1] = 2.5
    extra = {"craft_output": pa.array([0.0, 1.5] + [0.0] * (n - 2), type=pa.float32()),
             "craft_sufficiency": pa.array([0.0, 0.8] + [0.0] * (n - 2), type=pa.float32())}
    result = reconstruct_economy_result(*_result_batches(n, crafts, extra), world)
    assert world.regions[1].stockpile.goods["crafts"] == 2.5
    # Regions without wares get no wares key (state files unchanged).
    assert all("crafts" not in world.regions[i].stockpile.goods for i in range(n) if i != 1)
    assert all("crafts" not in keys for keys in keys_before)
    name = world.regions[1].name
    assert result.craft_output == {name: 1.5} and result.craft_sufficiency == {name: pytest.approx(0.8)}
    assert len(result.market_demand[name]) == 4
    # An extension built before crafts: no wares columns, wares read 0.
    world = generate_world(seed=42)
    old = reconstruct_economy_result(*_result_batches(n, None), world)
    assert old.craft_output == {} and old.market_demand[world.regions[0].name] == (2.0, 2.0, 2.0, 0.0)
    assert all("crafts" not in r.stockpile.goods for r in world.regions)


def test_region_batch_carries_wares_sufficiency_only_with_a_wares_market():
    world = generate_world(seed=42)
    result = EconomyResult()
    result.craft_sufficiency = {world.regions[0].name: 1.2}
    # A three-category result (before crafts) reads 0 for wares.
    result.market_demand = {world.regions[0].name: (5.0, 1.0, 0.0)}
    batch = build_region_batch(world, result)
    assert batch.column("craft_sufficiency").to_pylist()[:2] == [pytest.approx(1.2), 0.0]
    assert batch.column("market_demand_craft").to_pylist()[0] == 0.0
    assert "stockpile_8" in batch.schema.names
    # Turns after: no wares in the result (or no result), no column.
    for later in (EconomyResult(), None):
        assert "craft_sufficiency" not in build_region_batch(world, later).schema.names


def _city_world():
    world = generate_world(seed=42)
    C.set_cities_enabled(world, True)
    return world


def test_every_region_wants_wares_with_the_switch_on():
    world = _city_world()
    rows = pa.record_batch({
        "region": pa.array([VERDANT] * 6 + [0] * 4, type=pa.uint16()),
        "occupation": pa.array([0] * 10, type=pa.uint8()),
        "settlement_id": pa.array([0] * 10, type=pa.uint16()),
    })
    wares = C.economy_columns(world, rows)["craft_demand"]
    assert wares[VERDANT] == pytest.approx(6 * C.CRAFT_DEMAND_PER_CAPITA)
    assert wares[0] == pytest.approx(4 * C.CRAFT_DEMAND_PER_CAPITA)
    assert wares[1] == 0.0
    C.set_cities_enabled(world, False)
    assert C.economy_columns(world, rows) is None


def test_wares_a_city_makes_raise_its_commerce_and_reach_the_snapshot():
    world = _city_world()
    city = City(settlement_id=3, region=VERDANT, name="Town 3", founded_turn=0, founder=-1, lord=-1, rank=CITY)
    world.cities.cities.append(city)
    city.size = 25.0
    verdant = world.regions[VERDANT]
    k = C.scale(world)

    def economy(wares: float):
        return SimpleNamespace(
            food_sufficiency={verdant.name: 1.0}, trade_route_counts={verdant.name: 1},
            imports_by_region={verdant.name: {"food": 0.0}},
            market_demand={verdant.name: (10.0, 0.0, 0.0, 0.1)}, craft_output={verdant.name: wares})

    commerce = []
    for wares in (0.0, 1.0, 50.0):
        city.wealth = 0.0
        C._commerce(C._Tick(world, None, None, economy(wares)), city, verdant, 1.0, k)
        commerce.append(city.commerce)
    base = 1.0 + C.ROUTE_ACCESS
    assert city.crafts == 50.0
    assert commerce[1] == pytest.approx(commerce[0] * (base + C.CRAFT_ACCESS * 0.1) / base, rel=1e-3)
    assert commerce[2] == pytest.approx(commerce[0] * (base + C.CRAFT_ACCESS_CAP) / base, rel=1e-3)
    assert C.snapshot_summary(world)["cities"][0]["crafts"] == 50.0
    # A saved city from before crafts loads with none.
    old = city.model_dump()
    old.pop("crafts")
    assert City.model_validate(old).crafts == 0.0


@pytest.mark.native
def test_native_hybrid_cities_make_and_trade_wares(tmp_path, monkeypatch):
    """Cities make wares and merchants carry some out; with --no-cities no
    wares are made and no region's stock ever holds a wares key."""
    _require_native()
    import json

    import chronicler.agent_bridge as ab
    import chronicler.economy as eco
    from chronicler.main import _build_parser, execute_run

    def run(flag: str, label: str):
        made, carried = [], []
        real_reconstruct, real_process = eco.reconstruct_economy_result, ab.AgentBridge._process_tick_results

        def reconstruct(*args, **kwargs):
            result = real_reconstruct(*args, **kwargs)
            made.append(sum(result.craft_output.values()))
            return result

        def process(self, agent_events, world, *a, **k):
            arrivals = self._sim.get_pending_arrivals()
            carried.extend(q for g, q in zip(arrivals.column("good_slot").to_pylist(),
                                             arrivals.column("qty").to_pylist()) if g == 8)
            return real_process(self, agent_events, world, *a, **k)

        out = tmp_path / label
        with monkeypatch.context() as m:
            m.setattr(eco, "reconstruct_economy_result", reconstruct)
            m.setattr(ab.AgentBridge, "_process_tick_results", process)
            execute_run(_build_parser().parse_args([
                "--seed", "44", "--turns", "80", "--civs", "4", "--regions", "8", "--agents", "hybrid",
                "--simulate-only", flag, "--output", str(out / "chronicle.md"), "--state", str(out / "state.json")]))
        return sum(made), carried, json.loads((out / "state.json").read_text())

    made, carried, _ = run("--cities", "on")
    assert made > 0, "cities make wares"
    assert carried, "merchants carry wares"
    made, carried, state = run("--no-cities", "off")
    assert made == 0 and not carried
    assert all("crafts" not in r["stockpile"]["goods"] for r in state["regions"])


@pytest.mark.native
def test_native_wares_sufficiency_restores_the_material_need():
    """One tick with the column against one without: the same agents end
    with more material need met."""
    _require_native()
    from chronicler_agents import AgentSimulator

    def mean_material(craft: float | None) -> float:
        world = generate_world(seed=42)
        world.agent_mode = "hybrid"
        sim = AgentSimulator(num_regions=len(world.regions), seed=world.seed)
        batch = build_region_batch(world)
        if craft is not None:
            data = {n: batch.column(n) for n in batch.schema.names}
            data["craft_sufficiency"] = pa.array([craft] * len(world.regions), type=pa.float32())
            batch = pa.record_batch(data)
        sim.set_region_state(batch)
        needs = sim.get_all_needs()
        return sum(needs.column("material").to_pylist()) / needs.num_rows, sim, batch

    base, _, _ = mean_material(None)
    assert base > 0
    from chronicler.agent_bridge import build_signals
    world = generate_world(seed=42)
    signals = build_signals(world)

    def after_tick(craft):
        _, sim, batch = mean_material(craft)
        sim.tick(0, signals)
        needs = sim.get_all_needs()
        return sum(needs.column("material").to_pylist()) / needs.num_rows

    assert after_tick(1.0) > after_tick(None)
