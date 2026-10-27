"""Production ledger (2026-10, docs/integration/production-ledger.md): the
Python lane. Yields carry the overextraction penalty, the overextraction take
follows realized output where an economy reports it, the fishery stock is
charged for the landed catch, scenario slots start undegraded, and the ledger
balances (CHRONICLER_CHECK_RESOURCES=1) without touching state or RNG."""
import json

import pytest

from chronicler.economy import EconomyResult, compute_allocated_production
from chronicler.ecology import (
    compute_resource_yields, harvest_normal_index, overextraction_take, update_depletion_feedback,
    yield_penalty_factor,
)
from chronicler.experimental.fisheries import (
    apply_fishery_feedback, step_fishery, unlanded_stock,
)
from chronicler.models import ClimatePhase, EMPTY_SLOT, ResourceType
from chronicler.production_ledger import (
    LEDGER_COLUMNS, RESOURCE_CHECK_ENV, STOCK_FISH, STOCK_RESERVE, ResourceLedgerTurn,
    read_ledger, start_turn_ledger, summarize_ledger, write_ledger,
)


@pytest.fixture
def fish_world(make_world):
    world = make_world(num_civs=1)
    region = world.regions[0]
    region.terrain = "coast"
    region.population = 40
    region.carrying_capacity = 60
    region.resource_types = [ResourceType.FISH, ResourceType.ORE, EMPTY_SLOT]
    region.resource_base_yields = [1.0, 0.5, 0.0]
    region.resource_effective_yields = [1.0, 0.5, 0.0]
    region.resource_current_yields = [1.0, 0.5, 0.0]
    world.civilizations[0].population = region.population
    world.fishery_experiment.enabled = True
    world.tuning_overrides = {"economy.farm_reference_density": 0.0}
    return world


# --- the overextraction penalty reaches the yields ---------------------------------------

def test_an_undegraded_slot_keeps_its_yield_bits(fish_world):
    region = fish_world.regions[0]
    assert yield_penalty_factor(region, 0) == 1.0
    before = compute_resource_yields(region, 1, ClimatePhase.TEMPERATE, 0, fish_world, deplete_reserves=False)
    fish_world.tuning_overrides["ecology.yield_penalty_reaches_goods"] = 0
    off = compute_resource_yields(region, 1, ClimatePhase.TEMPERATE, 0, fish_world, deplete_reserves=False)
    assert [y.hex() for y in before] == [y.hex() for y in off]


def test_a_degraded_slot_yields_its_share_and_the_key_restores_base_yields(fish_world):
    region = fish_world.regions[0]
    whole = compute_resource_yields(region, 1, ClimatePhase.TEMPERATE, 0, fish_world, deplete_reserves=False)
    region.resource_effective_yields = [0.81, 0.45, 0.0]  # two penalties on fish, one on ore
    assert yield_penalty_factor(region, 0) == pytest.approx(0.81)
    degraded = compute_resource_yields(region, 1, ClimatePhase.TEMPERATE, 0, fish_world, deplete_reserves=False)
    assert degraded[0] == pytest.approx(0.81 * whole[0])
    assert degraded[1] == pytest.approx(0.9 * whole[1])
    # An exhausted mine's trickle carries it too.
    region.resource_reserves[1] = 0.0
    trickle = compute_resource_yields(region, 1, ClimatePhase.TEMPERATE, 0, fish_world, deplete_reserves=False)
    assert trickle[1] == pytest.approx(0.5 * 0.04 * 0.9)
    fish_world.tuning_overrides["ecology.yield_penalty_reaches_goods"] = 0
    region.resource_reserves[1] = 1.0
    old = compute_resource_yields(region, 1, ClimatePhase.TEMPERATE, 0, fish_world, deplete_reserves=False)
    assert old == whole


def test_an_uninitialized_effective_yield_is_whole_not_degraded(fish_world):
    """Scenario worlds saved before 2026-10 left effective yields at 0."""
    from chronicler.emergence import _check_ecological_recovery
    region = fish_world.regions[0]
    region.resource_effective_yields = [0.0, 0.5, 0.0]
    assert yield_penalty_factor(region, 0) == 1.0

    class Always:
        def random(self):
            return 0.0

    assert _check_ecological_recovery(region, fish_world, Always()) is None
    assert region.resource_effective_yields == [0.0, 0.5, 0.0]
    region.resource_effective_yields = [0.5, 0.5, 0.0]  # a real penalty is still restored
    assert _check_ecological_recovery(region, fish_world, Always()) is not None
    assert region.resource_effective_yields[0] == pytest.approx(0.75)


def test_scenario_river_fish_and_specialized_slots_start_undegraded():
    """A scenario's river fish slot and specialized resources had base yields
    and effective yields of 0 (generate_world initializes both)."""
    from chronicler.models import River
    from chronicler.scenario import RegionOverride, ScenarioConfig, apply_scenario
    from chronicler.world_gen import generate_world
    world = generate_world(seed=42, num_regions=8, num_civs=2)
    source = next(r for r in world.regions[1:] if r.adjacencies and ResourceType.FISH not in r.resource_types
                  and EMPTY_SLOT in r.resource_types)
    first = world.regions[0]
    config = ScenarioConfig(name="Test", rivers=[River(name="Test River", path=[source.name, source.adjacencies[0]])],
                            regions=[RegionOverride(name=first.name,
                                                    specialized_resources=[str(int(ResourceType.SALT))])])
    apply_scenario(world, config)
    assert first.resource_types[0] == ResourceType.SALT
    fish_slot = source.resource_types.index(ResourceType.FISH)
    assert source.resource_base_yields[fish_slot] > 0
    assert source.resource_effective_yields[fish_slot] == source.resource_base_yields[fish_slot]
    for region in world.regions:
        for slot in range(3):
            if region.resource_base_yields[slot] > 0:
                assert region.resource_effective_yields[slot] == region.resource_base_yields[slot], (
                    region.name, slot)


# --- the overextraction take ------------------------------------------------------------

def test_the_take_is_realized_output_where_reported_and_the_proxy_otherwise(fish_world):
    region = fish_world.regions[0]
    region.population = 2000
    assert overextraction_take(region, 0) == 400.0                       # population / 5
    assert overextraction_take(region, 0, (12.0, 3.0, 0.0)) == 12.0      # 12 goods at base 1.0
    assert overextraction_take(region, 1, (12.0, 3.0, 0.0)) == 6.0       # 3 ore at base 0.5
    assert overextraction_take(region, 2, (12.0, 3.0, 0.0)) == 0.0


def test_a_crowd_that_takes_little_does_not_overextract(fish_world):
    region = fish_world.regions[0]
    region.population = 2000                  # proxy: 400 workers > 200 sustainable
    update_depletion_feedback(region, fish_world)
    assert region.overextraction_streaks[0] == 1
    update_depletion_feedback(region, fish_world, realized=(20.0, 2.0, 0.0))
    assert region.overextraction_streaks[0] == 0
    region.population = 10                    # proxy: 2 workers; realized: 300 worker equivalents
    update_depletion_feedback(region, fish_world, realized=(300.0, 0.0, 0.0))
    assert region.overextraction_streaks[0] == 1


# --- the fishery is charged for the landed catch -----------------------------------------

def _fish_turn(world, landed_goods):
    region = world.regions[0]
    economy = None
    if landed_goods is not None:
        economy = EconomyResult(slot_output={region.name: (landed_goods, 0.0, 0.0)})
    apply_fishery_feedback(world, {region.name: [1.0, 0.5, 0.0]}, economy)
    return region.fishery_stocks[0], region.fishery_catch_budgets[0]


def test_the_unlanded_allowance_returns_to_the_stock(fish_world):
    config = fish_world.fishery_experiment
    region = fish_world.regions[0]
    region.fishery_stocks[0] = 0.5
    _fish_turn(fish_world, None)              # reserves an allowance
    s0, budget = region.fishery_stocks[0], region.fishery_catch_budgets[0]
    assert budget > 0
    allowance_goods = budget / harvest_normal_index(int(ResourceType.FISH))
    units = region.resource_base_yields[0] * config.reserve_turns * config.reference_workers
    for share in (1.0, 0.5, 0.0):
        world = fish_world.model_copy(deep=True)
        s1, _ = _fish_turn(world, share * allowance_goods)
        returned = (1.0 - share) * budget / units
        expected = step_fishery(min(1.0, s0 + returned), 1.0, 1.0,
                                _proxy_fish_workers(world), config).stock
        assert s1 == pytest.approx(expected, abs=1e-12)
        assert unlanded_stock(budget, 1.0, share * allowance_goods, config) == pytest.approx(returned)
    # Everything landed: exactly the old rule.
    world_full = fish_world.model_copy(deep=True)
    world_old = fish_world.model_copy(deep=True)
    world_old.tuning_overrides["ecology.fishery_charges_landed_catch"] = 0
    assert _fish_turn(world_full, allowance_goods) == pytest.approx(_fish_turn(world_old, 0.0))


def _proxy_fish_workers(world):
    from chronicler.ecology import goods_per_worker
    from chronicler.economy import PER_CAPITA_FOOD, food_first_slot_labor
    region = world.regions[0]
    return food_first_slot_labor(
        region.resource_types,
        [goods_per_worker(rt, y) for rt, y in zip(region.resource_types, [1.0, 0.5, 0.0])],
        max(0, region.population // 5), region.population * PER_CAPITA_FOOD,
    )[0]


def test_without_an_economy_tick_the_allowance_stays_charged(fish_world):
    region = fish_world.regions[0]
    region.fishery_stocks[0] = 0.5
    _fish_turn(fish_world, None)
    a, b = fish_world.model_copy(deep=True), fish_world.model_copy(deep=True)
    assert _fish_turn(a, None) == _fish_turn(b, None)
    # A mock economy without slot output (an old extension) is no economy.
    c = fish_world.model_copy(deep=True)
    apply_fishery_feedback(c, {region.name: [1.0, 0.5, 0.0]}, EconomyResult())
    assert (c.regions[0].fishery_stocks[0], c.regions[0].fishery_catch_budgets[0]) == _fish_turn(
        fish_world.model_copy(deep=True), None)


# --- goods: the Python oracle reports what each slot made --------------------------------

def test_slot_output_and_forage_add_up_to_the_goods():
    outputs: list[float] = []
    goods = compute_allocated_production(
        [ResourceType.GRAIN, ResourceType.TIMBER, ResourceType.ORE], [1.0, 2.0, 3.0], 60,
        production_caps=[None, 5.0, None], slot_output=outputs,
    )
    assert outputs[:3] == [20.0, 5.0, 60.0] and outputs[3] == 0.0
    assert sum(outputs) == pytest.approx(sum(goods.values()))
    outputs = []
    goods = compute_allocated_production(
        [ResourceType.ORE, EMPTY_SLOT, EMPTY_SLOT], [1.0, 0.0, 0.0], 40,
        food_demand=10.0, subsistence_yield=0.3, slot_output=outputs,
    )
    assert outputs[3] == pytest.approx(goods["grain"]) and outputs[3] > 0
    assert sum(outputs) == pytest.approx(sum(goods.values()))


# --- the ledger ---------------------------------------------------------------------------

def _advance(world, turns):
    from chronicler.action_engine import ActionEngine
    from chronicler.simulation import run_turn
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn)


def _off_world(seed):
    from chronicler.experimental.fisheries import set_fisheries_enabled
    from chronicler.world_gen import generate_world
    world = generate_world(seed=seed)
    world.agent_mode = "off"
    set_fisheries_enabled(world, True, new_world=True)
    return world


def test_aggregate_turns_balance_the_resource_ledger(monkeypatch):
    monkeypatch.setenv(RESOURCE_CHECK_ENV, "1")
    for seed in (42, 7):
        world = _off_world(seed)
        _advance(world, 40)
        assert world.turn == 40


def test_the_ledger_reads_only(monkeypatch):
    plain = _off_world(42)
    checked = _off_world(42)
    monkeypatch.delenv(RESOURCE_CHECK_ENV, raising=False)
    _advance(plain, 25)
    monkeypatch.setenv(RESOURCE_CHECK_ENV, "1")
    _advance(checked, 25)
    assert json.dumps(plain.model_dump(mode="json"), sort_keys=True) == json.dumps(
        checked.model_dump(mode="json"), sort_keys=True)


def test_the_ledger_is_off_by_default(monkeypatch):
    monkeypatch.delenv(RESOURCE_CHECK_ENV, raising=False)
    assert start_turn_ledger(_off_world(42), None) is None


def _one_turn_rows(world, mutate=None):
    """Rows of one off-mode Phase 9, with ``mutate`` applied after the tick."""
    from chronicler.climate import get_climate_phase
    from chronicler.ecology import tick_ecology
    ledger = ResourceLedgerTurn(world, None, check=True, record=True)
    tick_ecology(world, get_climate_phase(world.turn, world.climate_config))
    if mutate is not None:
        mutate(world)
    return ledger.finish(world)


def test_rows_reconcile_stock_by_stock(monkeypatch):
    world = _off_world(42)
    _advance(world, 10)
    for _ in range(5):
        rows = _one_turn_rows(world)
        world.turn += 1
        n = len(rows["turn"])
        assert n > 0 and set(rows) == set(LEDGER_COLUMNS)
        kinds = set(rows["stock_kind"])
        assert STOCK_RESERVE in kinds and STOCK_FISH in kinds
        for i in range(n):
            if rows["stock_kind"][i]:
                assert rows["stock_after"][i] == pytest.approx(
                    rows["stock_before"][i] - rows["depletion"][i] + rows["recovery"][i], abs=1e-9)
            if rows["stock_kind"][i] == STOCK_RESERVE:
                assert rows["recovery"][i] == 0.0
                assert rows["depletion"][i] == rows["proxy_depletion"][i]  # the proxy is the rule here
            if rows["stock_kind"][i] == STOCK_FISH:
                # No economy: the whole allowance is charged, landed or not.
                assert rows["depletion"][i] == pytest.approx(rows["reserved_before"][i])


@pytest.mark.parametrize("stray", ["reserve", "fish"])
def test_the_check_catches_a_stray_change(stray):
    world = _off_world(42)
    _advance(world, 10)
    region_index = next(i for i, r in enumerate(world.regions)
                        if (ResourceType.ORE if stray == "reserve" else ResourceType.FISH) in r.resource_types)

    def mutate(w):
        region = w.regions[region_index]
        if stray == "reserve":
            slot = region.resource_types.index(ResourceType.ORE)
            region.resource_reserves[slot] += 0.01        # a reserve that grows
        else:
            slot = region.resource_types.index(ResourceType.FISH)
            region.fishery_stocks[slot] = max(0.0, region.fishery_stocks[slot] - 0.01)

    with pytest.raises(AssertionError, match="resource ledger does not balance"):
        _one_turn_rows(world, mutate)


def test_the_goods_check_reconciles_output_with_production():
    from chronicler.production_ledger import _check_goods
    economy = EconomyResult(slot_output={"A": (1.0, 2.0, 0.0), "B": (0.5, 0.0, 0.0)},
                            forage_output={"A": 0.25}, craft_output={"B": 0.5})
    economy.conservation["production"] = 4.25
    problems: list[str] = []
    _check_goods(problems, economy)
    assert problems == []
    economy.conservation["production"] = 4.5
    _check_goods(problems, economy)
    assert problems and "economy production" in problems[0]


def test_the_ledger_file_round_trips_and_summarizes(tmp_path):
    world = _off_world(42)
    _advance(world, 10)
    columns = {name: [] for name in LEDGER_COLUMNS}
    for _ in range(3):
        rows = _one_turn_rows(world)
        world.turn += 1
        for name in LEDGER_COLUMNS:
            columns[name].extend(rows[name])
    path = tmp_path / "ledger.arrow"
    write_ledger(path, columns)
    back = read_ledger(path)
    assert list(back) == list(LEDGER_COLUMNS) and back["turn"] == columns["turn"]
    summary = summarize_ledger(back)
    assert summary["rows"] == len(columns["turn"]) and summary["turns"] == 3
    assert summary["mineral_depletion_realized"] == pytest.approx(summary["mineral_depletion_proxy"])
    assert summary["fish_lost"] >= 0 and summary["mineral_slots"] > 0
