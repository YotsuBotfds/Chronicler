"""Farmland and regional climate.

Farm labour has diminishing returns on a region's land (``economy.effective_farm_labor``:
output per farmer falls as farmers crowd the arable capacity and rises as they
thin; the native economy kernel computes the same curve from two optional
columns). The global climate phase is the long trend at
``climate.CLIMATE_TREND_SHARE`` of its crop and water effects; the rest of the
pressure comes as regional harvest shocks, bad harvest years of clusters of
neighbouring regions (``climate.harvest_shock``). See
docs/integration/farmland-climate.md.
"""
from __future__ import annotations

import re
import statistics
from pathlib import Path

import pytest

import chronicler.climate as climate
import chronicler.ecology as eco
import chronicler.economy as econ
from chronicler.economy import (
    AGGREGATE_FARMER_SHARE,
    FARM_CEILING_IRRIGATION,
    FARM_LABOR_ELASTICITY,
    FARM_REFERENCE_DENSITY,
    EconomyResult,
    aggregate_farm_productivity,
    arable_capacity,
    effective_farm_labor,
    farm_labor_curve,
)
from chronicler.models import (
    EMPTY_SLOT,
    Civilization,
    ClimatePhase,
    Infrastructure,
    InfrastructureType,
    Leader,
    Region,
    RegionEcology,
    ResourceType,
    WorldState,
)
from chronicler.resources import CLIMATE_CLASS_MOD, _CLIMATE_PHASE_INDEX

ROOT = Path(__file__).resolve().parents[1]


def _region(name: str, adjacencies: list[str] | None = None, *, cap: int = 100, pop: int = 40) -> Region:
    return Region(
        name=name, terrain="plains", carrying_capacity=cap, resources="fertile",
        population=pop, controller="Farmers", adjacencies=adjacencies or [],
        ecology=RegionEcology(soil=0.9, water=0.6, forest_cover=0.2),
        resource_types=[ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT],
        resource_base_yields=[1.0, 0.0, 0.0],
        resource_effective_yields=[1.0, 0.0, 0.0],
    )


def _world(regions: list[Region], *, seed: int = 42, overrides: dict | None = None) -> WorldState:
    civ = Civilization(
        name="Farmers", population=sum(r.population for r in regions), military=20, economy=40,
        culture=30, stability=80, regions=[r.name for r in regions],
        leader=Leader(name="Farmer", trait="cautious", reign_start=0),
    )
    world = WorldState(name="Fields", seed=seed, turn=0, regions=regions, civilizations=[civ])
    if overrides:
        world.tuning_overrides = dict(overrides)
    return world


def _chain(n: int) -> list[Region]:
    names = [f"R{i}" for i in range(n)]
    return [_region(names[i], [names[j] for j in (i - 1, i + 1) if 0 <= j < n]) for i in range(n)]


# --- diminishing returns to farm labour -------------------------------------------------------

def test_effective_labor_is_exact_at_the_reference_and_concave_around_it():
    ref, half = 20.0, 20.0
    assert effective_farm_labor(20.0, ref, half) == pytest.approx(20.0)
    # Half the farmers grow a third more each; twice as many a third less.
    assert effective_farm_labor(10.0, ref, half) / 10.0 == pytest.approx(4.0 / 3.0)
    assert effective_farm_labor(40.0, ref, half) / 40.0 == pytest.approx(2.0 / 3.0)
    # Output keeps rising with labour but never passes the land's ceiling.
    values = [effective_farm_labor(x, ref, half) for x in (5, 10, 20, 40, 80, 1e6)]
    assert values == sorted(values) and values[-1] < ref + half
    # Off (no reference) and nobody farming: the labour itself.
    assert effective_farm_labor(17.0, 0.0, 0.0) == 17.0
    assert effective_farm_labor(0.0, ref, half) == 0.0


def test_curve_reads_the_arable_capacity_and_its_elasticity():
    region = _region("Fields", cap=100)
    world = _world([region])
    labor_ref, labor_half = farm_labor_curve(world, region)
    assert labor_ref == pytest.approx(FARM_REFERENCE_DENSITY * 100)
    assert labor_half == pytest.approx(labor_ref * FARM_LABOR_ELASTICITY / (1 - FARM_LABOR_ELASTICITY))
    # Elasticity at the reference: d ln E / d ln L.
    h = 1e-4
    e1 = effective_farm_labor(labor_ref * (1 + h), labor_ref, labor_half)
    e0 = effective_farm_labor(labor_ref * (1 - h), labor_ref, labor_half)
    assert (e1 - e0) / (2 * h * labor_ref) == pytest.approx(FARM_LABOR_ELASTICITY, rel=1e-3)
    # A density of 0 restores constant returns.
    off = _world([_region("Fields")], overrides={"economy.farm_reference_density": 0.0})
    assert farm_labor_curve(off, off.regions[0]) == (0.0, 0.0)


def test_irrigation_and_disasters_move_the_arable_capacity():
    region = _region("Fields", cap=100)
    world = _world([region])
    assert arable_capacity(world, region) == pytest.approx(100.0)
    region.infrastructure.append(Infrastructure(type=InfrastructureType.IRRIGATION, builder_civ="Farmers", built_turn=0))
    assert arable_capacity(world, region) == pytest.approx(100.0 * (1 + FARM_CEILING_IRRIGATION))
    region.infrastructure[0].active = False
    region.capacity_modifier = 0.5
    assert arable_capacity(world, region) == pytest.approx(50.0)


def test_farming_techniques_raise_the_ceiling():
    from chronicler.techniques import FARM_CEILING, farm_ceiling_multiplier
    from chronicler.techniques_state import TECHNIQUE_INDEX, TechniqueState

    region = _region("Fields")
    world = _world([region])
    assert farm_ceiling_multiplier(world, region) == 1.0  # techniques off
    world.techniques = TechniqueState()
    world.techniques.rows = [(0, TECHNIQUE_INDEX["irrigation"], 1.0, -1, 0, -1),
                             (0, TECHNIQUE_INDEX["heavy_plough"], 0.5, -1, 0, -1)]
    world.techniques._cache.practice = None
    expected = 1.0 + FARM_CEILING["irrigation"] + 0.5 * FARM_CEILING["heavy_plough"]
    assert farm_ceiling_multiplier(world, region) == pytest.approx(expected)
    assert arable_capacity(world, region) == pytest.approx(100.0 * expected)


def test_aggregate_food_per_head_falls_with_crowding_and_rises_as_land_empties():
    region = _region("Fields", cap=100)
    world = _world([region])
    ref_pop = FARM_REFERENCE_DENSITY * 100 / AGGREGATE_FARMER_SHARE
    region.population = round(ref_pop)
    assert aggregate_farm_productivity(world, region) == pytest.approx(1.0, abs=0.02)
    region.population = 90
    assert aggregate_farm_productivity(world, region) < 0.85
    region.population = 10
    assert aggregate_farm_productivity(world, region) > 1.4
    region.population = 0
    assert aggregate_farm_productivity(world, region) == 1.0


def test_aggregate_famine_check_reads_the_crowding(monkeypatch):
    """--agents off: the same harvest starves a crowded region, not a sparse one."""
    def famine(pop: int) -> bool:
        region = _region("Fields", cap=100, pop=pop)
        world = _world([region])
        world.agent_mode = None
        events = eco._check_famine_yield(
            world, {"Fields": [0.15, 0.0, 0.0]}, ClimatePhase.TEMPERATE, threshold=0.12,
            subsistence_base=0.15,
        )
        return any(e.event_type == "famine" for e in events)

    assert famine(95) and not famine(30)
    off = {"economy.farm_reference_density": 0.0}

    def famine_off(pop: int) -> bool:
        region = _region("Fields", cap=100, pop=pop)
        world = _world([region], overrides=off)
        world.agent_mode = None
        return any(e.event_type == "famine" for e in eco._check_famine_yield(
            world, {"Fields": [0.15, 0.0, 0.0]}, ClimatePhase.TEMPERATE, threshold=0.12,
            subsistence_base=0.15))

    assert not famine_off(95) and not famine_off(30)


def test_economy_batch_carries_the_curve_only_when_on():
    pytest.importorskip("pyarrow")
    regions = [_region("A", cap=80), _region("B", cap=40)]
    batch = econ.build_economy_region_input_batch(_world(regions))
    assert batch.column("farm_labor_ref").to_pylist() == pytest.approx([80 * 0.33, 40 * 0.33], rel=1e-6)
    assert batch.column("farm_labor_half").to_pylist() == pytest.approx([80 * 0.33, 40 * 0.33], rel=1e-6)
    off = econ.build_economy_region_input_batch(
        _world([_region("A")], overrides={"economy.farm_reference_density": 0.0}))
    assert "farm_labor_ref" not in off.schema.names and "farm_labor_half" not in off.schema.names


def test_python_curve_mirrors_the_native_kernel():
    src = (ROOT / "chronicler-agents" / "src" / "economy.rs").read_text(encoding="utf-8")
    assert "labor * (labor_ref + labor_half) / (labor + labor_half)" in src
    assert "effective_farm_labor(headcount_labor, inp.farm_labor_ref, inp.farm_labor_half)" in src


# --- regional climate --------------------------------------------------------------------------

def test_global_phase_stays_pure():
    from chronicler.models import ClimateConfig
    cfg = ClimateConfig()
    assert [climate.get_climate_phase(t, cfg) for t in range(150)] == \
           [climate.get_climate_phase(t, cfg) for t in range(150)]
    assert climate.get_climate_phase(50, cfg) == ClimatePhase.DROUGHT


def test_crop_phase_table_mirrors_the_resource_modifiers():
    for phase, mod in climate._CROP_PHASE_MOD.items():
        assert CLIMATE_CLASS_MOD[0][_CLIMATE_PHASE_INDEX[phase.value]] == mod


def test_harvest_shock_is_pure_and_constant_within_a_harvest_year():
    climate._YEAR_CACHE.clear()
    a = [climate.harvest_shock(7, "R0", t) for t in range(600)]
    climate._YEAR_CACHE.clear()
    b = [climate.harvest_shock(7, "R0", t) for t in reversed(range(600))][::-1]
    assert a == b
    for y in range(50):
        assert len(set(a[y * 12:(y + 1) * 12])) == 1
    lo, hi = climate.BAD_YEAR_DEPTH
    assert all(v == 0.0 or lo <= v <= hi for v in a)
    assert climate.harvest_shock(7, "R0", 30, trend_share=1.0) == 0.0
    assert climate.harvest_shock(7, "R0", 30) != climate.harvest_shock(8, "R0", 30) or \
        climate.harvest_shock(7, "R0", 42) != climate.harvest_shock(8, "R0", 42) or \
        climate.harvest_shock(7, "R0", 66) != climate.harvest_shock(8, "R0", 66)


def test_shocks_keep_the_cycle_mean_crop_climate_and_persist():
    """Over many years the mean shock is the regional share of the global
    schedule's mean crop loss, bad years cluster, and the long-run crop climate
    factor (trend plus shock) matches the global schedule's."""
    trend = climate.CLIMATE_TREND_SHARE
    years = []
    for cluster in range(40):
        years.extend(climate.harvest_shock(11, f"C{cluster}", y * 12) for y in range(400))
    mean = statistics.fmean(years)
    assert mean == pytest.approx(climate.mean_harvest_shock(trend), rel=0.06)
    bad = [v > 0 for v in years]
    pairs = [(bad[i], bad[i + 1]) for i in range(len(bad) - 1) if (i + 1) % 400]
    after_bad = [b for a, b in pairs if a]
    assert statistics.fmean(after_bad) == pytest.approx(climate.BAD_YEAR_PERSISTENCE, abs=0.04)
    assert statistics.fmean(bad) == pytest.approx(climate.bad_year_share(trend), abs=0.02)
    from chronicler.models import ClimateConfig
    cfg = ClimateConfig()
    global_mean = statistics.fmean(climate._CROP_PHASE_MOD[climate.get_climate_phase(t, cfg)] for t in range(750))
    regional = statistics.fmean(
        climate.regional_crop_climate(climate._CROP_PHASE_MOD[climate.get_climate_phase(t, cfg)], trend,
                                      climate.harvest_shock(11, f"C{c}", t))
        for c in range(20) for t in range(0, 4800, 4))
    assert regional == pytest.approx(global_mean, abs=0.01)


def test_shock_water_loss_replaces_the_trend_share_of_the_cycle_budget():
    world = _world([_region("A")])
    trend = climate.CLIMATE_TREND_SHARE
    k = climate.harvest_shock_water_loss(world, trend)
    per_turn_global = 0.2 * 0.04 + 0.2 * 0.02
    assert k * climate.mean_harvest_shock(trend) == pytest.approx((1 - trend) * per_turn_global)
    assert climate.harvest_shock_water_loss(world, 1.0) == 0.0


def test_regional_crop_climate_is_the_phase_modifier_at_full_trend():
    for mod in (1.0, 0.9, 0.5, 0.7):
        assert climate.regional_crop_climate(mod, 1.0, 0.0) == mod
    assert climate.regional_crop_climate(0.5, 0.5, 0.0) == pytest.approx(0.75)
    assert climate.regional_crop_climate(1.0, 0.5, 0.4) == pytest.approx(0.6)
    assert climate.regional_crop_climate(0.5, 0.5, 0.9) == 0.0


def test_clusters_are_contiguous_bounded_and_deterministic():
    regions = _chain(12)
    world = _world(regions, seed=3)
    clusters = climate.climate_clusters(world)
    assert clusters == climate.climate_clusters(_world(_chain(12), seed=3))
    names = [r.name for r in regions]
    groups: dict[str, list[int]] = {}
    for i, founder in enumerate(clusters):
        groups.setdefault(founder, []).append(i)
    assert sum(len(v) for v in groups.values()) == 12
    for founder, members in groups.items():
        assert len(members) <= climate.CLIMATE_CLUSTER_SIZE
        f = names.index(founder)
        assert f in members
        assert all(m == f or names[m] in regions[f].adjacencies for m in members)
    assert len(groups) >= 12 // climate.CLIMATE_CLUSTER_SIZE


def test_regions_of_a_cluster_share_a_harvest_and_others_differ():
    world = _world(_chain(30), seed=5)
    clusters = climate.climate_clusters(world)
    agree = differ = 0
    for t in range(0, 600, 12):
        world.turn = t
        shocks = climate.region_harvest_shocks(world)
        for i in range(30):
            for j in range(i + 1, 30):
                if clusters[i] == clusters[j]:
                    assert shocks[i] == shocks[j]
                    agree += 1
                elif shocks[i] != shocks[j]:
                    differ += 1
    assert agree > 0 and differ > 0
    world.tuning_overrides = {"climate.trend_share": 1.0}
    assert climate.region_harvest_shocks(world) == [0.0] * 30


def test_a_bad_year_cuts_the_crop_and_dries_the_land(monkeypatch):
    region = _region("A")
    world = _world([region])
    base = eco.compute_resource_yields(region, 2, ClimatePhase.TEMPERATE, 0, world, deplete_reserves=False)
    monkeypatch.setattr(climate, "region_harvest_shock", lambda w, r: 0.4)
    bad = eco.compute_resource_yields(region, 2, ClimatePhase.TEMPERATE, 0, world, deplete_reserves=False)
    assert bad[0] == pytest.approx(base[0] * 0.6)
    water = region.ecology.water
    eco._tick_water(region, None, ClimatePhase.WARMING, world)
    assert region.ecology.water == pytest.approx(water - 0.4 * climate.harvest_shock_water_loss(world, 0.5))


def test_foraging_reads_the_regional_crop_factor(monkeypatch):
    region = _region("A")
    region.resource_types = [ResourceType.ORE, EMPTY_SLOT, EMPTY_SLOT]
    world = _world([region])
    world.turn = 50  # the global drought: the trend keeps half its crop loss
    monkeypatch.setattr(climate, "region_harvest_shock", lambda w, r: 0.0)
    trend_only = econ.region_subsistence_yield(world, region, [1.0, 0.0, 0.0])
    world.tuning_overrides = {"climate.trend_share": 1.0}
    full = econ.region_subsistence_yield(world, region, [1.0, 0.0, 0.0])
    assert trend_only == pytest.approx(full * 0.75 / 0.5)


def test_trend_share_scales_the_global_drought():
    region = _region("A")
    world = _world([region])
    world.turn = 50  # a good year for this seed is not needed: no shock when trend is 1.0 below
    world.tuning_overrides = {"climate.trend_share": 1.0}
    eco._tick_water(region, None, ClimatePhase.DROUGHT, world)
    full = 0.6 - region.ecology.water
    region.ecology.water = 0.6
    world.tuning_overrides = {"climate.trend_share": 0.5}
    import chronicler.climate as cl
    shock = cl.region_harvest_shock(world, region)
    eco._tick_water(region, None, ClimatePhase.DROUGHT, world)
    half = 0.6 - region.ecology.water
    assert full == pytest.approx(0.04)
    assert half == pytest.approx(0.02 + shock * cl.harvest_shock_water_loss(world, 0.5))


def test_python_regional_climate_mirrors_the_native_ecology():
    src = (ROOT / "chronicler-agents" / "src" / "ecology.rs").read_text(encoding="utf-8")
    assert "(1.0 - trend_share * (1.0 - crop_mod) - shock).max(0.0)" in src
    assert "region.harvest_shock * config.harvest_shock_water_loss" in src
    assert re.search(r"rate \* config\.climate_trend_share", src)


# --- native ------------------------------------------------------------------------------------

def _require_native():
    chronicler_agents = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(chronicler_agents, "AgentSimulator", None), type):
        pytest.skip("requires the chronicler_agents Rust extension")


@pytest.mark.native
def test_native_farm_productivity_scales_farmer_income_and_resets(make_world):
    """Farmer income follows output per farmer; a batch without the column
    reads constant returns again (nothing carries over inside Rust)."""
    _require_native()
    import pyarrow as pa
    from chronicler.agent_bridge import AgentBridge

    def run(steps: list[float | None]) -> list[float]:
        world = make_world(num_civs=2)
        world.agent_mode = "hybrid"
        for region in world.regions:
            region.population = 40
            region.resource_types = [ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT]
            region.resource_current_yields = [0.8, 0.0, 0.0]
        bridge = AgentBridge(world, mode="hybrid")
        names = [r.name for r in world.regions]
        out = []
        for fp in steps:
            result = EconomyResult(food_sufficiency={n: 1.5 for n in names})
            if fp is not None:
                result.farm_productivity = {n: fp for n in names}
            bridge.set_economy_result(result)
            world.turn += 1
            bridge.tick(world)
            snap = pa.record_batch(bridge._sim.get_snapshot())
            occ = snap.column("occupation").to_pylist()
            wealth = snap.column("wealth").to_pylist()
            out.append(sum(w for o, w in zip(occ, wealth) if o == 0))
        return out

    low = run([0.5, None])
    same = run([1.0, None])
    plain = run([None, None])
    assert low[0] < plain[0]
    assert same == plain
    # The second turn had no column: it pays constant returns in both runs.
    assert low[1] - low[0] == pytest.approx(plain[1] - plain[0], rel=0.05)


@pytest.mark.native
def test_native_economy_reports_farm_productivity(make_world):
    _require_native()
    from chronicler.agent_bridge import AgentBridge
    from chronicler.economy import (
        build_economy_region_input_batch, build_economy_trade_route_batch, reconstruct_economy_result,
    )

    world = make_world(num_civs=2)
    world.agent_mode = "hybrid"
    for region in world.regions:
        region.population = 50
        region.resource_types = [ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT]
        region.resource_base_yields = [1.0, 0.0, 0.0]
        region.resource_current_yields = [0.5, 0.0, 0.0]
    world.regions[0].carrying_capacity = 20   # crowded
    world.regions[1].carrying_capacity = 400  # empty land
    bridge = AgentBridge(world, mode="hybrid")
    rust = bridge._sim.tick_economy(
        build_economy_region_input_batch(world), build_economy_trade_route_batch(world, []), 2, False, 1.0,
    )
    result = reconstruct_economy_result(*rust, world)
    fp = result.farm_productivity
    assert fp[world.regions[0].name] < 1.0 < fp[world.regions[1].name]


@pytest.mark.native
def test_native_ecology_reads_the_harvest_shock(make_world, monkeypatch):
    _require_native()
    from chronicler.agent_bridge import build_region_batch, configure_ecology_runtime
    from chronicler_agents import EcologySimulator
    from chronicler.columnar import pylist

    def tick(shock: float):
        world = make_world(num_civs=2)
        for region in world.regions:
            region.population = 20
            region.resource_types = [ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT]
            region.resource_base_yields = [1.0, 0.0, 0.0]
        monkeypatch.setattr(climate, "region_harvest_shocks", lambda w, turn=None: [shock, 0.0])
        sim = EcologySimulator()
        configure_ecology_runtime(sim, world)
        sim.set_region_state(build_region_batch(world))
        batch, _ = sim.tick_ecology(10, 0, [False, False], [False, False])
        return pylist(batch.column("current_turn_yield_0")), pylist(batch.column("water"))

    y0, w0 = tick(0.0)
    y1, w1 = tick(0.4)
    assert y1[1] == pytest.approx(y0[1]) and w1[1] == pytest.approx(w0[1])
    assert w1[0] < w0[0]
    assert y1[0] < y0[0]
