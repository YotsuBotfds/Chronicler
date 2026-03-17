import pytest
from chronicler.models import InfrastructureType, Infrastructure, InfrastructureType as IType
from chronicler.infrastructure import (
    BUILD_SPECS, _region_has_temple, _count_civ_temples,
    destroy_temple_on_conquest, MAX_TEMPLES_PER_REGION, MAX_TEMPLES_PER_CIV,
    TEMPLE_CONVERSION_BOOST,
    tick_temple_prestige, TEMPLE_PRESTIGE_PER_TURN, CIV_PRESTIGE_PER_TEMPLE,
)

def test_infrastructure_type_has_temples():
    assert hasattr(InfrastructureType, "TEMPLES")

def test_infrastructure_has_faith_id():
    infra = Infrastructure(type=IType.TEMPLES, builder_civ="Civ1", built_turn=10, faith_id=2)
    assert infra.faith_id == 2
    assert infra.temple_prestige == 0

def test_non_temple_faith_id_default():
    infra = Infrastructure(type=IType.ROADS, builder_civ="Civ1", built_turn=10)
    assert infra.faith_id == -1

def test_temple_build_specs():
    assert IType.TEMPLES in BUILD_SPECS
    cost, turns = BUILD_SPECS[IType.TEMPLES].cost, BUILD_SPECS[IType.TEMPLES].turns
    assert cost == 10
    assert turns == 3

def test_region_has_temple():
    class R:
        infrastructure = [Infrastructure(type=IType.TEMPLES, builder_civ="C", built_turn=1)]
    assert _region_has_temple(R()) is True

def test_region_has_no_temple():
    class R:
        infrastructure = [Infrastructure(type=IType.ROADS, builder_civ="C", built_turn=1)]
    assert _region_has_temple(R()) is False

def test_destroy_temple_on_conquest():
    temple = Infrastructure(type=IType.TEMPLES, builder_civ="Old", built_turn=1, faith_id=0)
    class R:
        infrastructure = [temple]
        name = "Region0"
    class C:
        name = "Attacker"
    class W:
        turn = 10
    event = destroy_temple_on_conquest(R(), C(), W())
    assert event is not None
    assert event.event_type == "temple_destroyed"
    assert temple.active is False


def test_tick_temple_prestige():
    from unittest.mock import MagicMock
    world = MagicMock()
    civ = MagicMock()
    civ.name = "Civ1"
    civ.prestige = 10
    temple = Infrastructure(type=IType.TEMPLES, builder_civ="Civ1", built_turn=1, faith_id=0, temple_prestige=5)
    region = MagicMock()
    region.controller = "Civ1"
    region.infrastructure = [temple]
    world.regions = [region]
    world.civilizations = [civ]
    tick_temple_prestige(world)
    assert temple.temple_prestige == 6
    assert civ.prestige == 11


def test_tick_temple_prestige_credits_controller():
    """After conquest, prestige goes to region controller, not builder."""
    from unittest.mock import MagicMock
    world = MagicMock()
    old_civ = MagicMock()
    old_civ.name = "OldCiv"
    old_civ.prestige = 10
    new_civ = MagicMock()
    new_civ.name = "NewCiv"
    new_civ.prestige = 5
    temple = Infrastructure(type=IType.TEMPLES, builder_civ="OldCiv", built_turn=1, faith_id=0)
    region = MagicMock()
    region.controller = "NewCiv"  # conquered
    region.infrastructure = [temple]
    world.regions = [region]
    world.civilizations = [old_civ, new_civ]
    tick_temple_prestige(world)
    assert new_civ.prestige == 6  # controller gets prestige
    assert old_civ.prestige == 10  # builder gets nothing
