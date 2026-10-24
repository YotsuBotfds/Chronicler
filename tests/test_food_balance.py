"""Food-balance corrections (2026-10): see docs/integration/food-balance-2026-10.md.

Each test pins one correction: aggregate migration is a no-op for agent-owned
populations, and soil degrades against potential capacity.
"""
from __future__ import annotations

import pytest

from chronicler.climate import process_migration
from chronicler.ecology import _tick_soil, potential_capacity
from chronicler.models import (
    Civilization,
    ClimatePhase,
    Disposition,
    Leader,
    Region,
    RegionEcology,
    Relationship,
    WorldState,
)


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
    return WorldState(name="T", seed=1, regions=[region], civilizations=[_civ("Rome", ["P"])])


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
