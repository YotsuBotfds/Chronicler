"""Harvest previews and food-availability famine checks share one turn contract."""

from types import SimpleNamespace

import pyarrow as pa
import pytest

from chronicler.ecology import (
    _check_famine_yield,
    compute_resource_yields,
    effective_capacity,
    refresh_resource_yields,
    tick_ecology,
)
from chronicler.economy import EconomyResult, compute_economy
from chronicler.models import (
    EMPTY_SLOT,
    ActionType,
    Civilization,
    ClimatePhase,
    Leader,
    Region,
    RegionEcology,
    ResourceType,
    WorldState,
)
from chronicler.resources import get_season_id


def _world(*, mode="hybrid", turn=0, minerals=False):
    region = Region(
        name="Fields", terrain="plains", carrying_capacity=100,
        resources="fertile", population=20, controller="Farmers",
        ecology=RegionEcology(soil=0.9, water=0.6, forest_cover=0.2),
        resource_types=[ResourceType.GRAIN, ResourceType.ORE if minerals else EMPTY_SLOT, EMPTY_SLOT],
        resource_base_yields=[1.0, 0.8 if minerals else 0.0, 0.0],
        resource_effective_yields=[1.0, 0.8 if minerals else 0.0, 0.0],
        resource_reserves=[1.0, 0.2, 1.0],
    )
    civ = Civilization(
        name="Farmers", population=20, military=20, economy=40,
        culture=30, stability=80, regions=[region.name],
        leader=Leader(name="Farmer", trait="cautious", reign_start=0),
    )
    return WorldState(
        name="Harvest", seed=42, turn=turn, agent_mode=mode,
        regions=[region], civilizations=[civ],
    )


def _snapshot(world, *, merchants=0):
    rows = [
        (idx, 2 if idx > 0 and agent < merchants else 0, idx)
        for idx, region in enumerate(world.regions)
        for agent in range(region.population)
    ]
    return pa.record_batch({
        "region": pa.array([r[0] for r in rows], type=pa.uint16()),
        "occupation": pa.array([r[1] for r in rows], type=pa.uint8()),
        "civ_affinity": pa.array([r[2] for r in rows], type=pa.uint16()),
        "wealth": pa.array([5.0] * len(rows), type=pa.float32()),
    })


def _famine(world, result=None, *, yields=None):
    return _check_famine_yield(
        world, yields or {r.name: [0.01, 0.0, 0.0] for r in world.regions},
        ClimatePhase.DROUGHT, threshold=0.12, subsistence_base=0.15,
        economy_result=result,
    )


def test_harvest_preview_is_repeatable_without_ecology_or_depletion_mutations():
    world = _world(minerals=True)
    region = world.regions[0]
    before = world.model_dump()

    refresh_resource_yields(world, ClimatePhase.DROUGHT)
    harvest = list(region.resource_current_yields)
    refresh_resource_yields(world, ClimatePhase.DROUGHT)

    assert world.model_dump() == before  # Only transient yield publication changes.
    assert region.resource_current_yields == harvest
    assert harvest[0] > 0
    assert harvest[1] > 0


def test_current_climate_season_and_suspensions_affect_harvest_immediately():
    world = _world()
    region = world.regions[0]
    refresh_resource_yields(world, ClimatePhase.TEMPERATE)
    temperate = region.resource_current_yields[0]
    refresh_resource_yields(world, ClimatePhase.DROUGHT)
    drought = region.resource_current_yields[0]
    assert 0 < drought < temperate

    world.turn = 9  # Winter, without a Phase 9 tick in between previews.
    refresh_resource_yields(world, ClimatePhase.DROUGHT)
    assert 0 < region.resource_current_yields[0] < drought

    region.resource_suspensions = {int(ResourceType.GRAIN): 2}
    refresh_resource_yields(world, ClimatePhase.DROUGHT)
    assert region.resource_current_yields == [0.0, 0.0, 0.0]


def test_preview_reconstructs_identical_yields_after_save_resume():
    world = _world(turn=31, minerals=True)
    refresh_resource_yields(world, ClimatePhase.DROUGHT)
    resumed = WorldState.model_validate_json(world.model_dump_json())
    assert resumed.regions[0].resource_current_yields == [0.0, 0.0, 0.0]

    refresh_resource_yields(resumed, ClimatePhase.DROUGHT)
    assert resumed.regions[0].resource_current_yields == world.regions[0].resource_current_yields
    assert resumed.model_dump() == world.model_dump()


def test_phase9_updates_next_harvest_and_depletes_minerals_only_once():
    world = _world(minerals=True)
    region = world.regions[0]
    region.ecology.soil = 0.95  # At cap: no recovery obscures drought's water effect.
    reserve_before = region.resource_reserves[1]
    refresh_resource_yields(world, ClimatePhase.DROUGHT)
    first_harvest = list(region.resource_current_yields)
    assert region.resource_reserves[1] == reserve_before

    tick_ecology(world, ClimatePhase.DROUGHT)
    expected_extraction = 0.8 * ((region.population // 5) / max(1, effective_capacity(region) // 3)) * 0.009
    assert region.resource_reserves[1] == pytest.approx(reserve_before - expected_extraction)
    assert region.ecology.water == pytest.approx(0.56)
    assert region.resource_current_yields[0] < first_harvest[0]
    post_tick_reserve = region.resource_reserves[1]

    world.turn += 1  # Same season, so this isolates the ecological carryover.
    refresh_resource_yields(world, ClimatePhase.DROUGHT)
    assert region.resource_current_yields[0] < first_harvest[0]
    assert region.resource_current_yields[1] < first_harvest[1]
    assert region.resource_reserves[1] == post_tick_reserve


@pytest.mark.parametrize("mode", ["hybrid", "shadow", "demographics-only"])
@pytest.mark.parametrize("sufficiency, famine", [
    (0.0, True), (0.8, True), (0.999, True),
    (0.99999994, False), (1.0, False), (2.0, False),
])
def test_agent_famine_uses_food_sufficiency_instead_of_raw_yield(mode, sufficiency, famine):
    world = _world(mode=mode)
    result = EconomyResult(food_sufficiency={"Fields": sufficiency})
    # Productive land can still fail to feed its population; poor land can be fed.
    yields = {"Fields": [1.0 if famine else 0.01, 0.0, 0.0]}
    events = _famine(world, result, yields=yields)
    assert bool(events) is famine
    assert world.regions[0].population == (15 if famine and mode == "shadow" else 20)
    assert world.regions[0].famine_cooldown == (5 if famine else 0)
    assert world.civilizations[0].stability == (77 if famine else 80)


@pytest.mark.parametrize("mode", ["hybrid", "shadow", "demographics-only", "off"])
def test_only_macro_population_modes_move_famine_population_and_refugees(mode):
    world = _world(mode=mode)
    region = world.regions[0]
    neighbor = region.model_copy(deep=True)
    neighbor.name = "Neighbor"
    neighbor.controller = "Neighbors"
    region.adjacencies = [neighbor.name]
    world.regions.append(neighbor)
    neighbor_civ = world.civilizations[0].model_copy(deep=True)
    neighbor_civ.name = neighbor.controller
    neighbor_civ.regions = [neighbor.name]
    world.civilizations.append(neighbor_civ)

    result = EconomyResult(food_sufficiency={region.name: 0.0, neighbor.name: 1.0})
    events = _famine(world, result, yields={region.name: [0.01, 0.0, 0.0], neighbor.name: [1.0, 0.0, 0.0]})
    assert len(events) == 1
    expected = [15, 25] if mode in ("off", "shadow") else [20, 20]
    assert [r.population for r in world.regions] == expected
    assert [c.population for c in world.civilizations] == expected


@pytest.mark.parametrize("result", [None, EconomyResult()])
def test_agent_famine_never_reuses_a_stale_result_or_missing_region(result):
    world = _world()
    world._economy_result = EconomyResult(food_sufficiency={"Fields": 0.0})
    assert _famine(world, result) == []
    assert world.regions[0].population == 20


@pytest.mark.parametrize("mode", [None, "off"])
def test_aggregate_famine_preserves_yield_fallback(mode):
    world = _world(mode=mode)
    world.regions[0].stockpile.goods = {"grain": 100.0}
    result = EconomyResult(food_sufficiency={"Fields": 2.0})
    assert len(_famine(world, result)) == 1


def test_famine_still_respects_cooldown_with_food_shortage():
    world = _world()
    world.regions[0].famine_cooldown = 3
    assert _famine(world, EconomyResult(food_sufficiency={"Fields": 0.0})) == []


@pytest.mark.parametrize("sufficiency", [0.0, 2.0])
def test_rust_ecology_postpass_uses_current_economy_food_result(sufficiency):
    from chronicler.agent_bridge import build_region_batch

    world = _world()
    batch = build_region_batch(world)
    for slot, value in enumerate([0.01, 0.0, 0.0]):
        batch = batch.append_column(f"current_turn_yield_{slot}", pa.array([value], type=pa.float32()))

    class EcologyRuntime:
        calls = 0
        patch = None

        def tick_ecology(self, *args):
            self.calls += 1
            return batch, pa.record_batch({"event_type": pa.array([], type=pa.uint8())})

        def apply_region_postpass_patch(self, patch):
            self.patch = patch

    runtime = EcologyRuntime()
    result = EconomyResult(food_sufficiency={"Fields": sufficiency})
    events = tick_ecology(world, ClimatePhase.DROUGHT, ecology_runtime=runtime, economy_result=result)
    assert any(event.event_type == "famine" for event in events) is (sufficiency < 1.0)
    assert runtime.calls == 1
    assert runtime.patch is not None
    assert world.regions[0].population == 20


@pytest.mark.parametrize("protection", ["none", "reserves", "imports"])
def test_stored_food_and_delivered_imports_avert_drought_famine(protection):
    world = _world()
    region = world.regions[0]
    region.ecology.soil = 0.1
    region.ecology.water = 0.1
    routes = []
    if protection == "reserves":
        region.stockpile.goods = {"grain": 10.0}
    elif protection == "imports":
        supplier = region.model_copy(deep=True)
        supplier.name = "Storehouse"
        supplier.controller = "Traders"
        supplier.population = 40
        supplier.stockpile.goods = {"grain": 100.0}
        supplier.adjacencies = [region.name]
        region.adjacencies = [supplier.name]
        world.regions.append(supplier)
        trader = world.civilizations[0].model_copy(deep=True)
        trader.name = supplier.controller
        trader.population = supplier.population
        trader.regions = [supplier.name]
        world.civilizations.append(trader)
        routes = [("Farmers", "Traders")]

    refresh_resource_yields(world, ClimatePhase.DROUGHT)
    assert region.resource_current_yields[0] < 0.12
    result = compute_economy(
        world, _snapshot(world, merchants=20), world.region_map,
        agent_mode=True, active_trade_routes=routes,
    )
    if protection == "imports":
        assert result.imports_by_region[region.name]["food"] > 0.0
    assert (result.food_sufficiency[region.name] >= 1.0) is (protection != "none")

    events = tick_ecology(world, ClimatePhase.DROUGHT, economy_result=result)
    field_famines = [event for event in events if event.event_type == "famine" and "Farmers" in event.actors]
    assert bool(field_famines) is (protection == "none")


def test_run_turn_previews_after_environment_and_passes_current_food_result(monkeypatch):
    """Exercise the orchestration up through the real Phase 9 tick without Rust."""
    from chronicler.simulation import run_turn

    world = _world(mode="shadow", minerals=True)
    region = world.regions[0]
    world._economy_result = EconomyResult(food_sufficiency={region.name: 0.0})
    region.stockpile.goods = {"grain": 30.0}
    snapshot = _snapshot(world)
    calls = []
    current_result = None

    def environment(*args, **kwargs):
        region.ecology.water = 0.2
        calls.append("environment")
        return []

    def economy(*args, **kwargs):
        nonlocal current_result
        expected = compute_resource_yields(
            region, get_season_id(world.turn), ClimatePhase.DROUGHT,
            0, world, deplete_reserves=False,
        )
        assert region.resource_current_yields == expected
        assert region.resource_reserves[1] == 0.2
        calls.append("economy")
        current_result = compute_economy(
            world, snapshot, world.region_map, agent_mode=True, active_trade_routes=[],
        )
        return (current_result,)

    def ecology(*args, **kwargs):
        assert kwargs["economy_result"] is current_result
        assert current_result.food_sufficiency[region.name] >= 1.0
        calls.append("ecology")
        events = tick_ecology(*args, **kwargs)
        assert not any(event.event_type == "famine" for event in events)
        return events

    class StopAfterEcology(Exception):
        pass

    def tick_agents(*args, **kwargs):
        calls.append("agents")
        raise StopAfterEcology

    bridge = SimpleNamespace(
        get_snapshot=lambda: snapshot,
        _sim=SimpleNamespace(tick_economy=economy),
        set_economy_result=lambda result: None,
        sync_regions=lambda world: calls.append("sync"),
        ecology_simulator=None,
        tick_agents=tick_agents,
    )
    monkeypatch.setattr("chronicler.climate.get_climate_phase", lambda *args: ClimatePhase.DROUGHT)
    monkeypatch.setattr("chronicler.simulation.phase_environment", environment)
    monkeypatch.setattr("chronicler.ecology.tick_ecology", ecology)
    monkeypatch.setattr("chronicler.economy.reconstruct_economy_result", lambda result, *args, **kwargs: result)
    for phase in (
        "apply_automatic_effects", "phase_production", "phase_technology",
        "phase_action", "phase_cultural_milestones", "phase_random_events",
        "phase_leader_dynamics",
    ):
        monkeypatch.setattr(f"chronicler.simulation.{phase}", lambda *args, **kwargs: [])
    for phase in ("check_black_swans", "check_environmental_events"):
        monkeypatch.setattr(f"chronicler.emergence.{phase}", lambda *args, **kwargs: [])

    with pytest.raises(StopAfterEcology):
        run_turn(world, lambda *args: ActionType.DEVELOP, lambda *args: "", agent_bridge=bridge)
    assert calls == ["environment", "economy", "sync", "ecology", "agents"]
    expected_extraction = 0.8 * ((region.population // 5) / max(1, effective_capacity(region) // 3)) * 0.009
    assert region.resource_reserves[1] == pytest.approx(0.2 - expected_extraction)
