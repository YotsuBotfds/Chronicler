"""Food-balance corrections (2026-10): see docs/integration/food-balance-2026-10.md.

Each test pins one correction: aggregate migration is a no-op for agent-owned
populations, soil degrades against potential capacity, temperate water
recovery is climatic, mines need a mineral resource, goods harvests are in
economy units, and an outbreak's contagion is spread over its contacts.
"""
from __future__ import annotations

import pytest

from chronicler.climate import PHASE_SCHEDULE, process_migration
from chronicler.ecology import (
    TERRAIN_ECOLOGY_DEFAULTS,
    _tick_soil,
    _tick_water,
    goods_per_worker,
    harvest_normal_index,
    potential_capacity,
)
from chronicler.models import (
    Civilization,
    ClimatePhase,
    Disposition,
    Event,
    InfrastructureType,
    Leader,
    Region,
    RegionEcology,
    Relationship,
    ResourceType,
    WorldState,
)
from chronicler.resources import CLIMATE_CLASS_MOD, SEASON_MOD


def _civ(name: str, regions: list[str], population: int = 40) -> Civilization:
    return Civilization(
        name=name, population=population, military=30, economy=40, culture=30,
        stability=50, treasury=100, regions=regions,
        leader=Leader(name=f"{name} I", trait="cautious", reign_start=0),
    )


def _overflow_world(agent_mode: str | None) -> WorldState:
    src = Region(name="A", terrain="desert", carrying_capacity=20, resources="mineral",
                 controller="Rome", adjacencies=["B"], population=40)
    dst = Region(name="B", terrain="plains", carrying_capacity=80, resources="fertile",
                 controller="Greece", adjacencies=["A"], population=30)
    rels = {
        "Rome": {"Greece": Relationship(disposition=Disposition.NEUTRAL)},
        "Greece": {"Rome": Relationship(disposition=Disposition.NEUTRAL)},
    }
    world = WorldState(name="T", seed=42, regions=[src, dst],
                       civilizations=[_civ("Rome", ["A"]), _civ("Greece", ["B"], 30)],
                       relationships=rels)
    world.agent_mode = agent_mode
    return world


# --- aggregate migration ------------------------------------------------------

@pytest.mark.parametrize("mode", ["hybrid", "demographics-only"])
def test_overflow_migration_is_noop_for_agent_owned_populations(mode):
    world = _overflow_world(mode)
    before = ([r.population for r in world.regions],
              [(c.population, c.stability) for c in world.civilizations])
    assert process_migration(world) == []
    after = ([r.population for r in world.regions],
             [(c.population, c.stability) for c in world.civilizations])
    assert after == before


@pytest.mark.parametrize("mode", [None, "off", "shadow"])
def test_overflow_migration_still_moves_python_owned_populations(mode):
    world = _overflow_world(mode)
    events = process_migration(world)
    assert [e.event_type for e in events] == ["migration"]
    assert world.regions[0].population < 40
    assert world.regions[1].population > 30


# --- soil ---------------------------------------------------------------------

def _plains(population: int, soil: float, water: float = 0.6) -> Region:
    return Region(name="P", terrain="plains", carrying_capacity=80, resources="fertile",
                  controller="Rome", population=population,
                  ecology=RegionEcology(soil=soil, water=water, forest_cover=0.2))


def _world_with(region: Region) -> WorldState:
    # The global climate schedule alone (2026-10 regional climate off): these
    # tests pin the phase's own water and harvest arithmetic.
    return WorldState(name="T", seed=1, regions=[region], civilizations=[_civ("Rome", ["P"])],
                      tuning_overrides={"climate.trend_share": 1.0})


def test_degraded_soil_below_potential_capacity_does_not_degrade_further():
    # Effective capacity 80 x 0.5 x 1.0 = 40 < 70 people < potential 80.
    region = _plains(population=70, soil=0.5)
    world = _world_with(region)
    _tick_soil(region, world.civilizations[0], ClimatePhase.TEMPERATE, world)
    assert region.ecology.soil == pytest.approx(0.5)


def test_soil_degrades_above_potential_capacity():
    region = _plains(population=90, soil=0.9)
    world = _world_with(region)
    assert region.population > potential_capacity(region)
    _tick_soil(region, world.civilizations[0], ClimatePhase.TEMPERATE, world)
    assert region.ecology.soil == pytest.approx(0.9 - 0.005)


# --- water --------------------------------------------------------------------

@pytest.mark.parametrize("population", [0, 40, 80, 160])
def test_temperate_water_recovery_does_not_depend_on_population(population):
    region = _plains(population=population, soil=0.9, water=0.3)
    world = _world_with(region)
    _tick_water(region, world.civilizations[0], ClimatePhase.TEMPERATE, world)
    assert region.ecology.water == pytest.approx(0.33)


def test_populated_region_recovers_its_water_over_one_climate_cycle():
    """Drought and cooling losses are made good by the temperate phase."""
    from chronicler.climate import get_climate_phase
    from chronicler.ecology import clamp_ecology

    # At capacity the old pressure multiplier (0.1) let temperate recover only
    # 0.09 of the 0.6 a drought takes, so water stayed near the floor.
    region = _plains(population=80, soil=0.9, water=0.7)
    world = _world_with(region)
    period = world.climate_config.period
    waters = []
    for turn in range(2 * period):
        phase = get_climate_phase(turn, world.climate_config)
        _tick_water(region, world.civilizations[0], phase, world)
        clamp_ecology(region)
        waters.append(region.ecology.water)
    end_of_second_temperate = period + int(PHASE_SCHEDULE[1][0] * period) - 1
    assert min(waters) == pytest.approx(0.10)  # the drought still empties it
    assert waters[end_of_second_temperate] == pytest.approx(0.70)
    assert waters[2 * period - 1] == waters[period - 1]


# --- mines --------------------------------------------------------------------

def _region_with_slots(slots: list[int]) -> Region:
    return Region(name="M", terrain="plains", carrying_capacity=60, resources="fertile",
                  controller="Rome", resource_types=slots + [255] * (3 - len(slots)))


def test_mines_are_not_valid_without_a_mineral_resource():
    from chronicler.infrastructure import valid_build_types

    farmland = _region_with_slots([int(ResourceType.GRAIN), int(ResourceType.BOTANICALS)])
    assert InfrastructureType.MINES not in valid_build_types(farmland)


@pytest.mark.parametrize("mineral", [ResourceType.ORE, ResourceType.PRECIOUS])
def test_mines_are_valid_where_there_is_ore_or_precious_metal(mineral):
    from chronicler.infrastructure import valid_build_types

    region = _region_with_slots([int(ResourceType.GRAIN), int(mineral)])
    assert InfrastructureType.MINES in valid_build_types(region)


# --- goods harvest units ------------------------------------------------------

def _cycle_mean(class_idx: int) -> float:
    bounds = [t for t, _ in PHASE_SCHEDULE] + [1.0]
    return sum((bounds[i + 1] - bounds[i]) * CLIMATE_CLASS_MOD[class_idx][i]
               for i in range(len(PHASE_SCHEDULE)))


def test_harvest_normal_index_is_derived_from_the_m34_tables():
    plains = TERRAIN_ECOLOGY_DEFAULTS["plains"]
    grain = sum(SEASON_MOD[ResourceType.GRAIN]) / 4 * _cycle_mean(0) * plains.soil * plains.water
    assert harvest_normal_index(ResourceType.GRAIN) == pytest.approx(grain)
    assert harvest_normal_index(ResourceType.GRAIN) == pytest.approx(0.95 * 0.82 * 0.54)
    assert harvest_normal_index(ResourceType.FISH) == pytest.approx(0.85 * 0.94)
    assert harvest_normal_index(ResourceType.ORE) == pytest.approx(0.95)
    forest = TERRAIN_ECOLOGY_DEFAULTS["forest"].forest_cover
    assert harvest_normal_index(ResourceType.TIMBER) == pytest.approx(0.9 * _cycle_mean(1) * forest)


def test_healthy_land_averages_the_base_yield_over_a_full_cycle():
    """Long-run goods per farmer on default farmland equal the base yield."""
    from chronicler.climate import get_climate_phase
    from chronicler.ecology import compute_resource_yields
    from chronicler.resources import get_season_id

    region = _plains(population=40, soil=0.9, water=0.6)
    region.resource_types = [int(ResourceType.GRAIN), 255, 255]
    region.resource_base_yields = [1.0, 0.0, 0.0]
    world = _world_with(region)
    period = world.climate_config.period
    total = 0.0
    turns = period * 4  # whole climate cycles and whole years
    for turn in range(turns):
        phase = get_climate_phase(turn, world.climate_config)
        index = compute_resource_yields(region, get_season_id(turn), phase, 0, world,
                                        deplete_reserves=False)[0]
        total += goods_per_worker(ResourceType.GRAIN, index)
    assert total / turns == pytest.approx(1.0, rel=0.01)


def test_goods_per_worker_keeps_empty_and_zero_slots():
    assert goods_per_worker(255, 0.0) == 0.0
    assert goods_per_worker(int(ResourceType.GRAIN), 0.0) == 0.0


def test_economy_yield_and_catch_budget_are_in_goods_units():
    from chronicler.experimental.fisheries import catch_budget, economy_yield, set_fisheries_enabled

    region = Region(name="C", terrain="coast", carrying_capacity=60, resources="maritime",
                    controller="Rome", resource_types=[int(ResourceType.FISH), 255, 255],
                    resource_base_yields=[1.0, 0.0, 0.0])
    region.resource_current_yields = [0.6, 0.0, 0.0]
    region.fishery_catch_budgets = [12.0, None, None]
    world = _world_with(region)
    assert economy_yield(world, region) == pytest.approx(0.6 / harvest_normal_index(ResourceType.FISH))
    assert catch_budget(world, region) is None  # fishery off: uncapped
    set_fisheries_enabled(world, True, new_world=True)
    region.fishery_yield_ratios = [0.5, 1.0, 1.0]
    assert economy_yield(world, region) == pytest.approx(0.3 / harvest_normal_index(ResourceType.FISH))
    assert catch_budget(world, region) == pytest.approx(12.0 / harvest_normal_index(ResourceType.FISH))


# --- plague contagion ---------------------------------------------------------

def _star_world(spokes: int) -> WorldState:
    """Civ H borders ``spokes`` single-region civs (shared border weight 0.5 each)."""
    names = [f"S{i}" for i in range(spokes)]
    hub = Region(name="h", terrain="plains", carrying_capacity=50, resources="fertile",
                 controller="H", adjacencies=[n.lower() for n in names], population=20)
    regions = [hub] + [
        Region(name=n.lower(), terrain="plains", carrying_capacity=50, resources="fertile",
               controller=n, adjacencies=["h"], population=20)
        for n in names
    ]
    civs = [_civ("H", ["h"])] + [_civ(n, [n.lower()]) for n in names]
    return WorldState(name="star", seed=3, regions=regions, civilizations=civs)


def _outbreak(world: WorldState) -> None:
    from chronicler.events import ingest_turn_events

    ingest_turn_events(world, [Event(turn=0, event_type="plague", actors=["H"],
                                     description="", importance=5)])


def test_outbreak_contagion_unchanged_within_the_reference_contact_weight():
    from chronicler.events import PLAGUE_CONTACT_ALPHA, PLAGUE_CONTACT_WEIGHT_REF, _civ_contact_weights

    world = _star_world(2)
    row = _civ_contact_weights(world)["H"]
    assert sum(row.values()) <= PLAGUE_CONTACT_WEIGHT_REF
    _outbreak(world)
    for civ in world.civilizations[1:]:
        assert civ.event_excitation["plague"] == PLAGUE_CONTACT_ALPHA * row[civ.name]


def test_outbreak_contagion_is_shared_across_many_contacts():
    from chronicler.events import PLAGUE_CONTACT_ALPHA, PLAGUE_CONTACT_WEIGHT_REF, _civ_contact_weights

    world = _star_world(12)
    row = _civ_contact_weights(world)["H"]
    total = sum(row.values())
    assert total > 2 * PLAGUE_CONTACT_WEIGHT_REF
    _outbreak(world)
    spread = {c.name: c.event_excitation["plague"] for c in world.civilizations[1:]}
    for name, value in spread.items():
        assert value == pytest.approx(PLAGUE_CONTACT_ALPHA * row[name] * PLAGUE_CONTACT_WEIGHT_REF / total)
    # The outbreak's total pressure no longer grows with its number of contacts.
    assert sum(spread.values()) == pytest.approx(PLAGUE_CONTACT_ALPHA * PLAGUE_CONTACT_WEIGHT_REF)
