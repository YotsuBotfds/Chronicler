import pytest
from chronicler.models import InfrastructureType, Infrastructure, InfrastructureType as IType
from chronicler.infrastructure import (
    BUILD_SPECS, _region_has_temple, _count_civ_temples,
    destroy_temple_on_conquest, MAX_TEMPLES_PER_REGION, MAX_TEMPLES_PER_CIV,
    TEMPLE_CONVERSION_BOOST,
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
