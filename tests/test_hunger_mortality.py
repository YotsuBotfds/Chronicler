"""Hunger: graded mortality, fertility, disease and unrest by food severity.

Agent modes read the economy's food sufficiency and the run of severely
short turns (``chronicler.ecology.hunger_components``; the native
demographic tick computes the same components for agent mortality and
fertility). The Python-owned population models (``--agents off``, shadow)
scale their famine toll and growth by the same hunger. A dearth report's
stability drain and cooldown weigh a third of a famine's. See
docs/integration/hunger-mortality.md.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import chronicler.ecology as eco
import chronicler.epidemiology as ep
from chronicler.ecology import (
    DEARTH_EFFECT_WEIGHT,
    FAMINE_SEVERE_SUFFICIENCY,
    FAMINE_SEVERE_TURNS,
    _check_famine_yield,
    food_crisis_weight,
    hunger_components,
    hunger_fertility_multiplier,
    hunger_toll_share,
    population_growth_share,
    region_hunger,
)
from chronicler.economy import EconomyResult
from chronicler.models import (
    EMPTY_SLOT,
    Civilization,
    ClimatePhase,
    Leader,
    Region,
    RegionEcology,
    ResourceType,
    WorldState,
)

ROOT = Path(__file__).resolve().parents[1]


def _world(*, mode: str = "hybrid", population: int = 40) -> WorldState:
    region = Region(
        name="Fields", terrain="plains", carrying_capacity=100,
        resources="fertile", population=population, controller="Farmers",
        ecology=RegionEcology(soil=0.9, water=0.6, forest_cover=0.2),
        resource_types=[ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT],
        resource_base_yields=[1.0, 0.0, 0.0],
        resource_effective_yields=[1.0, 0.0, 0.0],
    )
    civ = Civilization(
        name="Farmers", population=population, military=20, economy=40,
        culture=30, stability=80, regions=[region.name],
        leader=Leader(name="Farmer", trait="cautious", reign_start=0),
    )
    return WorldState(name="Lean", seed=42, turn=0, agent_mode=mode, regions=[region], civilizations=[civ])


def _turn(world: WorldState, sufficiency: float | None, food_yield: float = 0.01):
    result = None if sufficiency is None else EconomyResult(food_sufficiency={"Fields": sufficiency})
    events = _check_famine_yield(
        world, {"Fields": [food_yield, 0.0, 0.0]}, ClimatePhase.TEMPERATE, threshold=0.12,
        subsistence_base=0.15, economy_result=result,
    )
    world.turn += 1
    for region in world.regions:
        if region.famine_cooldown > 0:
            region.famine_cooldown -= 1
    return events


# --- the severity components -----------------------------------------------------------------

def test_components_are_zero_when_fed_and_grade_across_dearth_and_famine():
    assert hunger_components(None, None) == (0.0, 0.0)
    assert hunger_components(1.0, 0) == (0.0, 0.0)
    assert hunger_components(1.7, 0) == (0.0, 0.0)
    assert hunger_components(0.8, None) == pytest.approx((0.5, 0.0))
    assert hunger_components(FAMINE_SEVERE_SUFFICIENCY, None) == pytest.approx((1.0, 0.0))
    # Below the severity line the famine component ramps in over a season.
    depth = (FAMINE_SEVERE_SUFFICIENCY - 0.3) / FAMINE_SEVERE_SUFFICIENCY
    ramp = [hunger_components(0.3, run)[1] for run in range(1, FAMINE_SEVERE_TURNS + 2)]
    assert ramp == pytest.approx([depth * min(1.0, r / FAMINE_SEVERE_TURNS)
                                  for r in range(1, FAMINE_SEVERE_TURNS + 2)])
    assert hunger_components(0.0, 10) == (1.0, 1.0)


def test_fertility_never_reaches_zero_and_toll_share_is_one_at_total_famine():
    assert hunger_fertility_multiplier(0.0, 0.0) == 1.0
    worst = hunger_fertility_multiplier(1.0, 1.0)
    assert worst == pytest.approx((1.0 - eco.HUNGER_DEARTH_FERTILITY) * (1.0 - eco.HUNGER_FAMINE_FERTILITY))
    assert 0.0 < worst < hunger_fertility_multiplier(1.0, 0.0) < 1.0
    assert hunger_fertility_multiplier(1.0, 0.0) == pytest.approx(1.0 - eco.HUNGER_DEARTH_FERTILITY)
    assert hunger_toll_share(0.0, 0.0) == 0.0
    assert hunger_toll_share(1.0, 1.0) == pytest.approx(1.0)
    assert hunger_toll_share(1.0, 0.0) < 0.1


def test_python_constants_mirror_the_native_demographics():
    src = (ROOT / "chronicler-agents/src/demographics.rs").read_text(encoding="utf-8")

    def native(name: str) -> float:
        m = re.search(rf"pub const {name}: \w+ = ([0-9.]+);", src)
        assert m, name
        return float(m.group(1))

    for name in ("HUNGER_DEARTH_MORTALITY", "HUNGER_FAMINE_MORTALITY",
                 "HUNGER_DEARTH_FERTILITY", "HUNGER_FAMINE_FERTILITY"):
        assert native(name) == pytest.approx(getattr(eco, name)), name
    assert native("HUNGER_FAMINE_TURNS") == FAMINE_SEVERE_TURNS
    agent = (ROOT / "chronicler-agents/src/agent.rs").read_text(encoding="utf-8")
    assert re.search(r"pub const FAMINE_MEMORY_THRESHOLD: f32 = 0\.6;", agent)
    assert FAMINE_SEVERE_SUFFICIENCY == pytest.approx(0.6)


# --- saved state: the last shortfall and the dearth cooldown ---------------------------------

def test_shortfall_is_saved_rounded_and_omitted_when_fed():
    world = _world()
    _turn(world, 0.123456)
    region = world.regions[0]
    assert region.food_shortfall == pytest.approx(0.8765)
    data = json.loads(world.model_dump_json())["regions"][0]
    assert data["food_shortfall"] == pytest.approx(0.8765) and data["dearth_cooldown"] is True
    loaded = WorldState.model_validate_json(world.model_dump_json())
    assert region_hunger(loaded.regions[0]) == region_hunger(region)
    _turn(world, 1.4)
    assert region.food_shortfall is None
    _turn(world, None)
    assert region.food_shortfall is None
    data = json.loads(world.model_dump_json())["regions"][0]
    assert "food_shortfall" not in data


def test_a_world_that_never_hungers_keeps_its_region_keys():
    world = _world()
    for _ in range(3):
        _turn(world, 1.5)
    data = json.loads(world.model_dump_json())["regions"][0]
    assert "food_shortfall" not in data and "dearth_cooldown" not in data


def test_dearth_cooldown_weighs_a_third_and_ends_or_deepens():
    world = _world()
    region = world.regions[0]
    assert food_crisis_weight(region) == 0.0
    assert [e.event_type for e in _turn(world, 0.3)] == ["dearth"]
    assert region.dearth_cooldown is True
    assert food_crisis_weight(region) == pytest.approx(DEARTH_EFFECT_WEIGHT)
    # Two more severe turns: the shortage is a famine before the next report.
    _turn(world, 0.3)
    assert region.dearth_cooldown is True
    _turn(world, 0.3)
    assert region.food_severe_turns == FAMINE_SEVERE_TURNS
    assert region.dearth_cooldown is None and food_crisis_weight(region) == 1.0
    # A dearth that does not deepen ends with its cooldown.
    world = _world()
    region = world.regions[0]
    _turn(world, 0.9)
    for _ in range(5):
        _turn(world, 1.5)
    assert region.famine_cooldown == 0 and region.dearth_cooldown is None


def test_dearth_drains_a_third_of_a_famines_stability():
    dearth_world = _world()
    _turn(dearth_world, 0.5)
    famine_world = _world()
    famine_world.regions[0].food_severe_turns = FAMINE_SEVERE_TURNS
    assert [e.event_type for e in _turn(famine_world, 0.5)] == ["famine"]
    assert famine_world.civilizations[0].stability == 77
    assert dearth_world.civilizations[0].stability == 79
    assert famine_world.regions[0].dearth_cooldown is None


def test_dearth_drain_routes_through_the_accumulator_as_signal():
    from chronicler.accumulator import StatAccumulator

    world = _world()
    acc = StatAccumulator()
    _check_famine_yield(world, {"Fields": [0.01, 0.0, 0.0]}, ClimatePhase.TEMPERATE, 0.12, 0.15, acc,
                        economy_result=EconomyResult(food_sufficiency={"Fields": 0.5}))
    changes = [c for c in acc._changes if c.stat == "stability"]
    assert [(c.delta, c.category) for c in changes] == [(-1, "signal")]


# --- Python-owned population: toll and growth --------------------------------------------------

def test_aggregate_toll_scales_with_the_yield_depth():
    def lost(food_yield: float) -> int:
        world = _world(mode="off")
        assert [e.event_type for e in _turn(world, None, food_yield=food_yield)] == ["famine"]
        return 40 - world.regions[0].population

    # The toll is the old flat toll (5) times the share of a total failure's
    # hunger: the yield's depth below the famine threshold (0.12).
    for food_yield in (0.11, 0.06, 0.001):
        depth = 1.0 - food_yield / 0.12
        assert lost(food_yield) == int(5 * hunger_toll_share(1.0, depth))
    assert lost(0.11) < lost(0.06) < lost(0.001) <= 5
    shallow = _world(mode="off")
    _turn(shallow, None, food_yield=0.10)
    # The aggregate famine keeps its label and writes no hunger state.
    assert shallow.regions[0].food_shortfall is None and shallow.regions[0].dearth_cooldown is None


def test_shadow_toll_follows_the_measured_hunger():
    mild = _world(mode="shadow")
    assert [e.event_type for e in _turn(mild, 0.9)] == ["dearth"]
    assert mild.regions[0].population == 40  # a mild dearth takes no toll
    severe = _world(mode="shadow")
    severe.regions[0].food_severe_turns = 5
    assert [e.event_type for e in _turn(severe, 0.0)] == ["famine"]
    assert severe.regions[0].population == 35


def test_hybrid_reports_never_touch_population():
    world = _world()
    world.regions[0].food_severe_turns = 5
    _turn(world, 0.0)
    assert world.regions[0].population == 40


def test_growth_share_reads_hunger_or_the_aggregate_cooldown():
    region = _world().regions[0]
    assert population_growth_share(region) == 1.0
    region.food_shortfall = 0.2  # sufficiency 0.8
    assert population_growth_share(region) == pytest.approx(hunger_fertility_multiplier(0.5, 0.0))
    region.food_shortfall = None
    region.famine_cooldown = 3  # the aggregate model's famine
    assert population_growth_share(region) == pytest.approx(hunger_fertility_multiplier(1.0, 1.0))
    region.dearth_cooldown = True
    assert population_growth_share(region) == pytest.approx(hunger_fertility_multiplier(1.0, 0.0))


def test_off_mode_growth_is_withheld_in_a_famine_region():
    from chronicler.simulation import phase_production

    def grown(cooldown: int) -> int:
        world = _world(mode="off", population=10)
        civ = world.civilizations[0]
        civ.economy, civ.stability = 80, 60
        world.regions[0].famine_cooldown = cooldown
        phase_production(world)
        return world.regions[0].population - 10

    fed, starving = grown(0), grown(3)
    assert fed == 5
    assert starving == round(5 * hunger_fertility_multiplier(1.0, 1.0))


# --- epidemics ---------------------------------------------------------------------------------

def test_agent_mode_susceptibility_rises_with_hunger_depth():
    region = _world().regions[0]
    region.population, region.carrying_capacity = 50, 100
    assert ep._modifiers(region, True) == (1.0, 1.0, False)
    region.famine_cooldown = 3  # a report alone no longer raises it in agent modes
    assert ep._modifiers(region, True) == (1.0, 1.0, False)
    region.food_shortfall = 0.2
    lean = ep._modifiers(region, True)
    region.food_shortfall = 0.7
    region.food_severe_turns = 1
    severe_new = ep._modifiers(region, True)
    region.food_severe_turns = FAMINE_SEVERE_TURNS
    famine = ep._modifiers(region, True)
    region.food_shortfall = 1.0
    total = ep._modifiers(region, True)
    assert lean[2] and famine[2]
    assert 1.0 < lean[0] < severe_new[0] < famine[0] < total[0]
    assert 1.0 < lean[1] < famine[1] < total[1]
    assert total[0] == pytest.approx(1.0 + sum(ep.HUNGER_SUSCEPTIBILITY))
    assert total[1] == pytest.approx(1.0 + sum(ep.HUNGER_CFR))


def test_aggregate_model_keeps_the_flat_famine_terms():
    region = _world(mode="off").regions[0]
    region.population, region.carrying_capacity = 50, 100
    region.famine_cooldown = 2
    assert ep._modifiers(region) == (1.0 + ep.FAMINE_SUSCEPTIBILITY, 1.0 + ep.FAMINE_CFR, True)
    assert ep._hunger_aware(_world(mode="off")) is False
    assert ep._hunger_aware(_world(mode="hybrid")) is True


# --- what reads the cooldown -------------------------------------------------------------------

def test_cooldown_readers_weigh_a_dearth_a_third():
    from chronicler.emergence import compute_civ_stress
    from chronicler.events import HazardContext

    def measures(dearth: bool):
        world = _world()
        region = world.regions[0]
        region.famine_cooldown = 3
        region.dearth_cooldown = True if dearth else None
        ctx = HazardContext(world)
        return ctx.hardship(world.civilizations[0]), compute_civ_stress(world.civilizations[0], world)

    famine_hardship, famine_stress = measures(False)
    dearth_hardship, dearth_stress = measures(True)
    assert famine_hardship == pytest.approx(0.5)
    assert dearth_hardship == pytest.approx(0.5 * DEARTH_EFFECT_WEIGHT)
    assert famine_stress > dearth_stress


# --- the region batch and the native tick ------------------------------------------------------

def test_region_batch_carries_the_previous_severe_run():
    from chronicler.agent_bridge import build_region_batch

    world = _world()
    assert build_region_batch(world).column("food_severe_turns").to_pylist() == [0]
    world.regions[0].food_severe_turns = 4
    batch = build_region_batch(world)
    assert batch.schema.field("food_severe_turns").type.bit_width == 16
    assert batch.column("food_severe_turns").to_pylist() == [4]
    world.regions[0].food_severe_turns = 10**6
    assert build_region_batch(world).column("food_severe_turns").to_pylist() == [0xFFFF]


def _require_native():
    chronicler_agents = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(chronicler_agents, "AgentSimulator", None), type):
        pytest.skip("requires the chronicler_agents Rust extension")


@pytest.mark.native
def test_native_tick_adds_hunger_deaths_and_withholds_births(make_world):
    """The tick reads this turn's sufficiency and the batch's severe run; a fed
    world shows no hunger terms, and a starving region does every turn."""
    _require_native()
    from chronicler.agent_bridge import AgentBridge

    world = make_world(num_civs=2)
    world.agent_mode = "hybrid"
    for region in world.regions:
        region.population = 40
    bridge = AgentBridge(world, mode="hybrid")
    names = [r.name for r in world.regions]

    def tick(sufficiency: dict[str, float]) -> dict:
        bridge.set_economy_result(EconomyResult(food_sufficiency=sufficiency))
        world.turn += 1
        bridge.tick(world)
        return bridge._sim.get_demographic_debug()

    fed = tick({n: 1.5 for n in names})
    assert fed["expected_hunger_deaths"] == 0.0 and fed["hunger_births_withheld"] == 0.0
    world.regions[1].food_severe_turns = 6
    starving = [tick({names[0]: 1.5, names[1]: 0.05}) for _ in range(3)]
    assert all(d["expected_hunger_deaths"] > 0.0 for d in starving)
    assert all(d["hunger_births_withheld"] > 0.0 for d in starving)
    # Back to fed: the terms reset (nothing carries over inside Rust).
    world.regions[1].food_severe_turns = None
    again = tick({n: 1.5 for n in names})
    assert again["expected_hunger_deaths"] == 0.0 and again["hunger_births_withheld"] == 0.0
