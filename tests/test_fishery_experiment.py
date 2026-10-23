"""Deterministic accounting fixtures and focused default-off integration checks."""
import math

import pyarrow as pa
import pytest
from pydantic import ValidationError

from chronicler.ecology import tick_ecology
from chronicler.experimental.fisheries import (
    FisheryConfig, apply_fishery_feedback, economy_yield, step_fishery,
)
from chronicler.experimental.fisheries_bridge import build_fishery_yield_patch
from chronicler.models import ActionType, ClimatePhase, EMPTY_SLOT, Region, ResourceType, WorldState


@pytest.fixture
def fish_world(make_world):
    world = make_world(num_civs=1)
    region = world.regions[0]
    region.terrain = "coast"
    region.population = 2000
    region.carrying_capacity = 3000
    region.resource_types = [ResourceType.FISH, ResourceType.ORE, EMPTY_SLOT]
    region.resource_base_yields = [1.0, 0.5, 0.0]
    region.resource_effective_yields = [1.0, 0.5, 0.0]
    region.resource_current_yields = [1.0, 0.5, 0.0]
    world.civilizations[0].population = region.population
    return world


def test_exact_mass_balance_fixture():
    result = step_fishery(0.5, 1.0, 1.0, 200, FisheryConfig())
    assert result.capacity == 8.0
    assert result.recovery == pytest.approx(0.02)
    assert result.harvest == pytest.approx(0.125)
    assert result.stock == pytest.approx(0.395)
    assert result.yield_per_worker == 1.0


@pytest.mark.parametrize("stock", [0.0, 0.01, 0.25, 0.5, 1.0])
@pytest.mark.parametrize("workers", [0, 20, 200, 800, 100000])
@pytest.mark.parametrize("potential", [0.0, 0.6, 1.0, 100.0])
def test_conservation_and_bounded_harvest(stock, workers, potential):
    config = FisheryConfig()
    result = step_fishery(stock, 1.0, potential, workers, config)
    assert stock + result.recovery == pytest.approx(result.stock + result.harvest)
    assert 0.0 <= result.stock <= 1.0
    assert result.harvest <= (stock + result.recovery) * config.harvest_fraction + 1e-12
    assert 0.0 <= result.yield_per_worker <= potential
    assert result.harvest * result.capacity == pytest.approx(
        result.yield_per_worker * min(workers / config.reference_workers, 4.0)
    )


def test_more_effort_depletes_more_and_cannot_raise_per_worker_yield():
    results = [step_fishery(0.1, 1, 1, workers, FisheryConfig())
               for workers in (0, 20, 200, 800, 100000)]
    assert [r.stock for r in results] == sorted((r.stock for r in results), reverse=True)
    assert [r.yield_per_worker for r in results] == sorted(
        (r.yield_per_worker for r in results), reverse=True,
    )


def test_more_stock_and_recovery_cannot_reduce_catch():
    results = [step_fishery(s, 1, 1, 800, FisheryConfig()) for s in (0, .1, .5, 1)]
    assert [r.yield_per_worker for r in results] == sorted(r.yield_per_worker for r in results)
    results = [step_fishery(.1, 1, 1, 800, FisheryConfig(recovery_rate=r)) for r in (0, .04, .25)]
    assert [r.stock for r in results] == sorted(r.stock for r in results)


def test_rest_replenishes_without_creating_harvest():
    stock = 0.0
    for _ in range(50):
        result = step_fishery(stock, 1, 1, 0, FisheryConfig())
        assert result.stock > stock
        assert result.harvest == 0
        stock = result.stock
    assert stock == pytest.approx(1 - .96 ** 50)


@pytest.mark.parametrize("kwargs", [
    {"recovery_rate": -.01}, {"recovery_rate": .26}, {"recovery_rate": math.nan},
    {"reserve_turns": 1}, {"reserve_turns": math.inf}, {"harvest_fraction": 0},
    {"harvest_fraction": .51}, {"reference_workers": 0}, {"reference_workers": 10001},
])
def test_config_rejects_unbounded_parameters(kwargs):
    with pytest.raises(ValidationError):
        FisheryConfig(**kwargs)


@pytest.mark.parametrize("stock", [-.1, 1.1, math.inf, math.nan])
def test_invalid_stock_rejected(stock):
    with pytest.raises(ValueError):
        step_fishery(stock, 1, 1, 10, FisheryConfig())


@pytest.mark.parametrize("field,value", [
    ("fishery_stocks", [1, 1]), ("fishery_stocks", [1, math.nan, 1]),
    ("fishery_stocks", [1, 2, 1]), ("fishery_yield_ratios", [-1, 1, 1]),
])
def test_invalid_saved_state_rejected(fish_world, field, value):
    payload = fish_world.model_dump()
    payload["regions"][0][field] = value
    with pytest.raises(ValidationError):
        WorldState.model_validate(payload)


def test_disabled_path_freezes_experiment_and_yields(fish_world):
    region = fish_world.regions[0]
    region.fishery_stocks = [.2, .3, .4]
    region.fishery_yield_ratios = [.2, .3, .4]
    before = fish_world.model_dump()
    yields = {region.name: [1.0, .5, 0.0]}
    apply_fishery_feedback(fish_world, yields)
    assert fish_world.model_dump() == before
    assert yields[region.name] == [1.0, .5, 0.0]
    assert economy_yield(fish_world, region) == 1.0


def test_removed_slot_resets_and_other_resource_is_untouched(fish_world):
    fish_world.fishery_experiment.enabled = True
    region = fish_world.regions[0]
    region.fishery_stocks = [.1, .3, .4]
    original_reserves = region.resource_reserves[:]
    yields = {region.name: [1.0, .5, 0.0]}
    apply_fishery_feedback(fish_world, yields)
    assert yields[region.name][1:] == [.5, 0.0]
    assert region.resource_reserves == original_reserves
    assert region.resource_effective_yields == [1.0, .5, 0.0]
    assert region.fishery_stocks[1:] == [1.0, 1.0]
    region.resource_types[0] = ResourceType.GRAIN
    apply_fishery_feedback(fish_world, yields)
    assert region.fishery_stocks[0] == region.fishery_yield_ratios[0] == 1
    assert region.fishery_catch_budgets[0] is None


def test_suspension_recovers_without_harvest(fish_world):
    fish_world.fishery_experiment.enabled = True
    region = fish_world.regions[0]
    region.fishery_stocks[0] = .1
    region.resource_suspensions = {ResourceType.FISH: 10}
    tick_ecology(fish_world, ClimatePhase.TEMPERATE)
    assert region.fishery_stocks[0] == pytest.approx(.136)
    assert region.resource_current_yields[0] == 0
    assert economy_yield(fish_world, region) == 0


def test_save_load_legacy_defaults_and_resume(fish_world, tmp_path):
    legacy = fish_world.model_dump()
    legacy.pop("fishery_experiment")
    for region in legacy["regions"]:
        region.pop("fishery_stocks")
        region.pop("fishery_yield_ratios")
        region.pop("fishery_catch_budgets")
    loaded_legacy = WorldState.model_validate(legacy)
    assert not loaded_legacy.fishery_experiment.enabled
    assert loaded_legacy.regions[0].fishery_stocks == [1, 1, 1]

    fish_world.fishery_experiment.enabled = True
    for turn in range(12):
        fish_world.turn = turn
        tick_ecology(fish_world, ClimatePhase.TEMPERATE)
    path = tmp_path / "state.json"
    fish_world.save(path)
    resumed = WorldState.load(path)
    for turn in range(12, 18):
        for world in (fish_world, resumed):
            world.turn = turn
            tick_ecology(world, ClimatePhase.TEMPERATE)
        assert resumed.model_dump() == fish_world.model_dump()
        assert resumed.regions[0].resource_current_yields == fish_world.regions[0].resource_current_yields


def test_minimal_on_off_ecology_pair_and_lagged_economy(fish_world):
    from chronicler.economy import build_economy_region_input_batch
    off = fish_world.model_copy(deep=True)
    assert "fishery_catch_budget_0" not in build_economy_region_input_batch(off).schema.names
    fish_world.fishery_experiment.enabled = True
    initial_input = build_economy_region_input_batch(fish_world).column("resource_yield_0")[0].as_py()
    assert initial_input == 1
    budgets = build_economy_region_input_batch(fish_world).to_pylist()[0]
    # No prior catch means no fish credit; the ore and empty slots stay uncapped.
    assert [budgets[f"fishery_catch_budget_{slot}"] for slot in range(3)] == [0, None, None]
    for turn in range(24):
        for world in (off, fish_world):
            world.turn = turn
            tick_ecology(world, ClimatePhase.TEMPERATE)
    assert off.regions[0].fishery_stocks == [1, 1, 1]
    assert fish_world.regions[0].fishery_stocks[0] < .2
    assert 0 < fish_world.regions[0].resource_current_yields[0] < .5
    assert 0 < economy_yield(fish_world, fish_world.regions[0]) < 1
    batch_yield = build_economy_region_input_batch(fish_world).column("resource_yield_0")[0].as_py()
    assert batch_yield == pytest.approx(economy_yield(fish_world, fish_world.regions[0]))
    assert fish_world.regions[0].resource_effective_yields[0] == 1


def test_complete_turn_pair_is_deterministic(fish_world):
    from chronicler.simulation import run_turn
    for enabled in (False, True):
        left = fish_world.model_copy(deep=True)
        left.fishery_experiment.enabled = enabled
        right = left.model_copy(deep=True)
        for turn in range(8):
            for world in (left, right):
                run_turn(world, lambda *_: ActionType.DEVELOP, lambda *_: "", seed=42 + turn)
            assert left.model_dump() == right.model_dump()


def test_old_native_extension_fails_before_mutation(fish_world):
    fish_world.fishery_experiment.enabled = True
    before = fish_world.model_dump()
    with pytest.raises(RuntimeError, match="rebuilt native extension"):
        tick_ecology(fish_world, ClimatePhase.TEMPERATE, ecology_runtime=object())
    assert fish_world.model_dump() == before


def test_old_native_full_turn_fails_before_any_phase(fish_world):
    from types import SimpleNamespace
    from chronicler.simulation import run_turn
    fish_world.fishery_experiment.enabled = True
    bridge = SimpleNamespace(ecology_simulator=object(), _sim=object())
    before = fish_world.model_dump()
    with pytest.raises(RuntimeError, match="rebuilt native extension"):
        run_turn(fish_world, lambda *_: ActionType.DEVELOP, lambda *_: "", agent_bridge=bridge)
    assert fish_world.model_dump() == before


@pytest.mark.parametrize("potential,proxy_workers,farmers", [
    (.65, 200, 200), (1.0, 1600, 1600), (.6, 20, 2000), (1.0, 200, 20),
])
def test_economy_production_never_exceeds_stock_debit(fish_world, potential, proxy_workers, farmers):
    from chronicler.economy import compute_economy
    fish_world.fishery_experiment.enabled = True
    region = fish_world.regions[0]
    region.resource_types = [ResourceType.FISH, EMPTY_SLOT, EMPTY_SLOT]
    region.population = proxy_workers * 5
    region.fishery_stocks[0] = .1
    apply_fishery_feedback(fish_world, {region.name: [potential, 0, 0]})
    budget = region.fishery_catch_budgets[0]
    snapshot = pa.record_batch({
        "region": pa.array([0] * farmers, type=pa.int32()),
        "occupation": pa.array([0] * farmers, type=pa.int32()),
        "wealth": pa.array([0.0] * farmers, type=pa.float32()),
        "civ_affinity": pa.array([0] * farmers, type=pa.int32()),
    })
    result = compute_economy(fish_world, snapshot, fish_world.region_map,
                             agent_mode=True, active_trade_routes=[])
    expected = min(economy_yield(fish_world, region) * farmers, budget)
    assert result.conservation["production"] == pytest.approx(expected)
    assert result.conservation["production"] <= budget + 1e-10


@pytest.mark.native
def test_native_economy_honors_lagged_budget(fish_world):
    """Fish (slot 0) and ore (slot 1) split farmers; only the fish share is capped."""
    from chronicler.agent_bridge import build_region_batch
    from chronicler.ecology import refresh_resource_yields
    from chronicler.economy import (
        build_economy_region_input_batch, build_economy_trade_route_batch, compute_economy,
    )
    runtime = _native_class("AgentSimulator")(1, 42)
    fish_world.fishery_experiment.enabled = True
    region = fish_world.regions[0]
    region.fishery_stocks[0] = .1
    apply_fishery_feedback(fish_world, {region.name: [.65, .5, 0]})
    runtime.set_region_state(build_region_batch(fish_world))
    refresh_resource_yields(fish_world, ClimatePhase.TEMPERATE)  # run_turn Phase 2 order
    batch = build_economy_region_input_batch(fish_world)
    snapshot = pa.record_batch(runtime.get_snapshot())
    oracle_world = fish_world.model_copy(deep=True)
    oracle = compute_economy(oracle_world, snapshot, oracle_world.region_map,
                             agent_mode=True, active_trade_routes=[])
    result = runtime.tick_economy(batch,
                                 build_economy_trade_route_batch(fish_world, active_trade_routes=[]),
                                 0, False, 1.0)
    production = pa.record_batch(result[4]).column("production")[0].as_py()
    farmers = sum(1 for occupation, rid in zip(snapshot.column("occupation").to_pylist(),
                                               snapshot.column("region").to_pylist())
                  if occupation == 0 and rid == 0)
    row = batch.to_pylist()[0]
    budget = region.fishery_catch_budgets[0]
    from chronicler.economy import PER_CAPITA_FOOD, food_first_slot_labor
    eaters = sum(1 for rid in snapshot.column("region").to_pylist() if rid == 0)
    labor = food_first_slot_labor(
        region.resource_types,
        [row["resource_yield_0"], row["resource_yield_1"], row["resource_yield_2"]],
        farmers, eaters * PER_CAPITA_FOOD,
    )
    uncapped_fish = row["resource_yield_0"] * labor[0]
    ore = row["resource_yield_1"] * labor[1]
    assert row["fishery_catch_budget_0"] == pytest.approx(budget)
    assert row["fishery_catch_budget_1"] is None and row["fishery_catch_budget_2"] is None
    assert uncapped_fish > budget > 0 and ore > 0  # the cap binds only the fish share
    assert production == pytest.approx(budget + ore, rel=1e-5)
    assert production == pytest.approx(oracle.conservation["production"], rel=1e-5)


@pytest.mark.native
def test_native_economy_rejects_catch_budget_on_nonfish_slot(fish_world):
    from chronicler.agent_bridge import build_region_batch
    from chronicler.economy import build_economy_region_input_batch, build_economy_trade_route_batch
    runtime = _native_class("AgentSimulator")(1, 42)
    fish_world.fishery_experiment.enabled = True
    runtime.set_region_state(build_region_batch(fish_world))
    batch = build_economy_region_input_batch(fish_world)
    index = batch.schema.get_field_index("fishery_catch_budget_1")
    bad = batch.set_column(index, "fishery_catch_budget_1", pa.array([5.0], type=pa.float32()))
    with pytest.raises(ValueError, match="invalid fishery catch budget"):
        runtime.tick_economy(bad, build_economy_trade_route_batch(fish_world, active_trade_routes=[]),
                             0, False, 1.0)


def test_fishing_effort_uses_the_production_labor_share(fish_world):
    """Biomass is debited only for the farmers the economy assigns to fishing."""
    fish_world.fishery_experiment.enabled = True
    single = fish_world.model_copy(deep=True)
    single.regions[0].resource_types = [ResourceType.FISH, EMPTY_SLOT, EMPTY_SLOT]
    for world in (fish_world, single):
        world.regions[0].fishery_stocks[0] = .5
        apply_fishery_feedback(world, {world.regions[0].name: [1.0, .5, 0.0]})
    shared, alone = fish_world.regions[0], single.regions[0]
    # pop 2000 -> 400 proxy workers. Shared with ore, the food-first split
    # gives fishing the labor the economy assigns it (the 1000-food demand
    # pulls it above the 200 equal share, ore keeps a quarter of its share: 350).
    from chronicler.economy import PER_CAPITA_FOOD, food_first_slot_labor
    shared_workers = food_first_slot_labor(
        shared.resource_types, [1.0, .5, 0.0], 400, 2000 * PER_CAPITA_FOOD,
    )[0]
    assert shared_workers == pytest.approx(350.0)
    expected_shared = step_fishery(.5, 1.0, 1.0, shared_workers, FisheryConfig())
    expected_alone = step_fishery(.5, 1.0, 1.0, 400, FisheryConfig())
    assert shared.fishery_stocks[0] == pytest.approx(expected_shared.stock)
    assert alone.fishery_stocks[0] == pytest.approx(expected_alone.stock)
    # With the larger food-first share both efforts can hit the biomass limit,
    # so less effort never catches more or leaves less stock.
    assert shared.fishery_catch_budgets[0] <= alone.fishery_catch_budgets[0]
    assert shared.fishery_stocks[0] >= alone.fishery_stocks[0]


def test_python_economy_caps_each_fish_slot_after_labor_split(fish_world):
    from chronicler.economy import compute_economy
    fish_world.fishery_experiment.enabled = True
    region = fish_world.regions[0]
    region.resource_types = [ResourceType.FISH, ResourceType.ORE, ResourceType.FISH]
    region.resource_base_yields = [1.0, 0.5, 1.0]
    region.resource_effective_yields = [1.0, 0.5, 1.0]
    region.resource_current_yields = [1.0, 0.5, 1.0]
    region.fishery_catch_budgets = [3.0, None, 50.0]
    farmers = 60
    snapshot = pa.record_batch({
        "region": pa.array([0] * farmers, type=pa.int32()),
        "occupation": pa.array([0] * farmers, type=pa.int32()),
        "wealth": pa.array([0.0] * farmers, type=pa.float32()),
        "civ_affinity": pa.array([0] * farmers, type=pa.int32()),
    })
    result = compute_economy(fish_world, snapshot, fish_world.region_map,
                             agent_mode=True, active_trade_routes=[])
    # 20 farmers per slot: fish capped at 3, ore 10, second fish uncapped at 20 <= 50.
    assert result.conservation["production"] == pytest.approx(3.0 + 10.0 + 20.0)
    assert result.region_goods[region.name].production["raw_material"] == pytest.approx(10.0)


@pytest.mark.native
def test_native_agents_consume_catch_after_postpass_recompute(fish_world, monkeypatch):
    from chronicler.agent_bridge import AgentBridge
    _native_class("AgentSimulator")
    fish_world.fishery_experiment.enabled = True
    fish_world.agent_mode = "demographics-only"
    fish_world.regions[0].fishery_stocks[0] = .1
    unpatched = fish_world.model_copy(deep=True)
    correct_bridge = AgentBridge(fish_world, mode="demographics-only")
    unpatched_bridge = AgentBridge(unpatched, mode="demographics-only")

    class OmitCatchPatch:
        def __getattr__(self, name):
            return getattr(unpatched_bridge.ecology_simulator, name)

        def apply_fishery_yield_patch(self, _patch):
            pass

    def force_recompute(world):
        world.regions[0].ecology.soil = .6

    monkeypatch.setattr("chronicler.traditions.apply_soil_floor", force_recompute)
    for world, bridge, runtime in (
        (fish_world, correct_bridge, correct_bridge.ecology_simulator),
        (unpatched, unpatched_bridge, OmitCatchPatch()),
    ):
        bridge.sync_regions(world)
        tick_ecology(world, ClimatePhase.TEMPERATE, ecology_runtime=runtime)
        bridge.tick_agents(world)

    def farmer_wealth(bridge):
        snapshot = pa.record_batch(bridge.get_snapshot())
        return {row["id"]: row["wealth"] for row in snapshot.to_pylist()
                if row["occupation"] == 0}

    correct, bypassed = farmer_wealth(correct_bridge), farmer_wealth(unpatched_bridge)
    common = correct.keys() & bypassed.keys()
    assert len(common) > 100
    assert sum(correct[i] for i in common) < sum(bypassed[i] for i in common)


@pytest.mark.native
def test_minimal_hybrid_full_turn_pair(fish_world):
    from chronicler.agent_bridge import AgentBridge
    from chronicler.simulation import run_turn
    _native_class("AgentSimulator")
    traces = []
    for enabled in (False, True):
        world = fish_world.model_copy(deep=True)
        world.agent_mode = "hybrid"
        world.fishery_experiment.enabled = enabled
        world.regions[0].population = 120
        world.regions[0].carrying_capacity = 200
        world.civilizations[0].population = 120
        world.regions[0].fishery_stocks[0] = .1
        bridge = AgentBridge(world, mode="hybrid")
        stocks = []
        for turn in range(4):
            run_turn(world, lambda *_: ActionType.DEVELOP, lambda *_: "", seed=42 + turn, agent_bridge=bridge)
            assert 0 <= world.regions[0].fishery_stocks[0] <= 1
            stocks.append(world.regions[0].fishery_stocks[0])
        traces.append(stocks)
    assert traces[0] == [.1] * 4
    assert traces[1] != traces[0]


def _native_class(name):
    try:
        import chronicler_agents
        cls = getattr(chronicler_agents, name)
    except (ImportError, AttributeError):
        pytest.skip("requires compiled chronicler_agents extension")
    assert hasattr(cls, "apply_fishery_yield_patch"), "rebuild native extension for experiment"
    return cls


@pytest.mark.native
@pytest.mark.parametrize("runtime_name", ["EcologySimulator", "AgentSimulator"])
def test_native_catch_matches_python_and_patch_validates(fish_world, runtime_name):
    from chronicler.agent_bridge import build_region_batch, configure_ecology_runtime
    runtime = (_native_class(runtime_name)(1, 42) if runtime_name == "AgentSimulator"
               else _native_class(runtime_name)())
    fish_world.fishery_experiment.enabled = True
    python_world = fish_world.model_copy(deep=True)
    configure_ecology_runtime(runtime, fish_world)
    for turn in range(24):
        for world in (fish_world, python_world):
            world.turn = turn
        runtime.set_region_state(build_region_batch(fish_world))
        tick_ecology(fish_world, ClimatePhase.TEMPERATE, ecology_runtime=runtime)
        tick_ecology(python_world, ClimatePhase.TEMPERATE)
        assert fish_world.regions[0].fishery_stocks[0] == pytest.approx(python_world.regions[0].fishery_stocks[0], abs=1e-7)
        assert fish_world.regions[0].resource_current_yields[0] == pytest.approx(python_world.regions[0].resource_current_yields[0], abs=1e-7)
    patch = build_fishery_yield_patch(fish_world)
    assert patch.num_rows == 1
    runtime.apply_fishery_yield_patch(patch)
    for slot, value in ((1, .1), (0, math.nan), (0, -.1), (3, .1)):
        bad = pa.record_batch({"region_id": pa.array([0], type=pa.uint16()),
                               "slot": pa.array([slot], type=pa.uint8()),
                               "yield": pa.array([value], type=pa.float32())})
        with pytest.raises(ValueError):
            runtime.apply_fishery_yield_patch(bad)
