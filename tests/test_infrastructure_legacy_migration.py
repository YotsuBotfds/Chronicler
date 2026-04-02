"""Migrated legacy infrastructure regressions from the retired test/ tree."""

from chronicler.accumulator import StatAccumulator
from chronicler.infrastructure import tick_temple_prestige
from chronicler.models import Civilization, Infrastructure, InfrastructureType, Leader, Region, WorldState


def _make_civ(name: str, regions: list[str], prestige: int) -> Civilization:
    return Civilization(
        name=name,
        population=50,
        military=30,
        economy=40,
        culture=30,
        stability=50,
        treasury=100,
        prestige=prestige,
        leader=Leader(name=f"Leader {name}", trait="bold", reign_start=0),
        regions=regions,
    )


def test_tick_temple_prestige_credits_region_controller_not_builder():
    temple = Infrastructure(
        type=InfrastructureType.TEMPLES,
        builder_civ="OldCiv",
        built_turn=1,
        faith_id=0,
    )
    region = Region(
        name="Border Temple",
        terrain="plains",
        carrying_capacity=50,
        resources="fertile",
        controller="NewCiv",
        infrastructure=[temple],
    )
    old_civ = _make_civ("OldCiv", regions=[], prestige=10)
    new_civ = _make_civ("NewCiv", regions=[region.name], prestige=5)
    world = WorldState(
        name="Temple World",
        seed=42,
        regions=[region],
        civilizations=[old_civ, new_civ],
    )

    tick_temple_prestige(world)

    assert temple.temple_prestige == 1
    assert new_civ.prestige == 6
    assert old_civ.prestige == 10


def test_tick_temple_prestige_routes_prestige_through_accumulator():
    temple = Infrastructure(
        type=InfrastructureType.TEMPLES,
        builder_civ="OldCiv",
        built_turn=1,
        faith_id=0,
    )
    region = Region(
        name="Border Temple",
        terrain="plains",
        carrying_capacity=50,
        resources="fertile",
        controller="NewCiv",
        infrastructure=[temple],
    )
    old_civ = _make_civ("OldCiv", regions=[], prestige=10)
    new_civ = _make_civ("NewCiv", regions=[region.name], prestige=5)
    world = WorldState(
        name="Temple World",
        seed=42,
        regions=[region],
        civilizations=[old_civ, new_civ],
    )

    acc = StatAccumulator()
    tick_temple_prestige(world, acc=acc)

    assert temple.temple_prestige == 1
    assert new_civ.prestige == 5

    acc.apply_keep(world)

    assert new_civ.prestige == 6
    assert old_civ.prestige == 10
