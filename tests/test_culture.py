"""Tests for M16a cultural foundations."""
import pytest
from chronicler.models import Civilization, Region, Relationship, Leader, TechEra, Disposition, WorldState
from chronicler.culture import VALUE_OPPOSITIONS, apply_value_drift


class TestModelFields:
    def test_civilization_has_prestige_field(self):
        civ = Civilization(
            name="Test", population=50, military=50, economy=50, culture=50,
            stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            domains=["trade"], values=["Trade"], regions=["R1"],
        )
        assert civ.prestige == 0

    def test_region_has_cultural_identity_field(self):
        region = Region(name="R1", terrain="plains", carrying_capacity=5, resources="fertile")
        assert region.cultural_identity is None
        assert region.foreign_control_turns == 0

    def test_relationship_has_disposition_drift_field(self):
        rel = Relationship()
        assert rel.disposition_drift == 0


@pytest.fixture
def drift_world():
    """Two civs with known value relationships."""
    regions = [
        Region(name="R1", terrain="plains", carrying_capacity=5, resources="fertile", controller="CivA"),
        Region(name="R2", terrain="plains", carrying_capacity=5, resources="fertile", controller="CivB"),
    ]
    civs = [
        Civilization(
            name="CivA", population=50, military=50, economy=50, culture=50,
            stability=50, leader=Leader(name="LA", trait="cautious", reign_start=0),
            domains=["trade"], values=["Trade", "Order"], regions=["R1"],
        ),
        Civilization(
            name="CivB", population=50, military=50, economy=50, culture=50,
            stability=50, leader=Leader(name="LB", trait="cautious", reign_start=0),
            domains=["trade"], values=["Trade", "Freedom"], regions=["R2"],
        ),
    ]
    relationships = {
        "CivA": {"CivB": Relationship(disposition=Disposition.NEUTRAL)},
        "CivB": {"CivA": Relationship(disposition=Disposition.NEUTRAL)},
    }
    return WorldState(
        name="test", seed=42, regions=regions,
        civilizations=civs, relationships=relationships,
    )


class TestValueOppositions:
    def test_freedom_opposes_order(self):
        assert VALUE_OPPOSITIONS["Freedom"] == "Order"

    def test_neutral_values_not_in_table(self):
        assert "Strength" not in VALUE_OPPOSITIONS
        assert "Destiny" not in VALUE_OPPOSITIONS


class TestValueDrift:
    def test_shared_value_positive_drift(self, drift_world):
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == 0  # shared=1, opposing=1 -> net=0

    def test_pure_shared_values_drift(self, drift_world):
        drift_world.civilizations[1].values = ["Trade", "Order"]
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == 4  # shared=2, opposing=0

    def test_drift_upgrades_disposition_at_threshold(self, drift_world):
        drift_world.civilizations[1].values = ["Trade", "Order"]
        drift_world.relationships["CivA"]["CivB"].disposition_drift = 8
        drift_world.relationships["CivB"]["CivA"].disposition_drift = 8
        apply_value_drift(drift_world)
        rel_ab = drift_world.relationships["CivA"]["CivB"]
        assert rel_ab.disposition == Disposition.FRIENDLY
        assert rel_ab.disposition_drift == 0

    def test_drift_downgrades_disposition_at_negative_threshold(self, drift_world):
        drift_world.civilizations[0].values = ["Freedom"]
        drift_world.civilizations[1].values = ["Order"]
        drift_world.relationships["CivA"]["CivB"].disposition_drift = -9
        drift_world.relationships["CivB"]["CivA"].disposition_drift = -9
        apply_value_drift(drift_world)
        rel_ab = drift_world.relationships["CivA"]["CivB"]
        assert rel_ab.disposition == Disposition.SUSPICIOUS
        assert rel_ab.disposition_drift == 0

    def test_empty_values_no_drift(self, drift_world):
        drift_world.civilizations[0].values = []
        apply_value_drift(drift_world)
        rel = drift_world.relationships["CivA"]["CivB"]
        assert rel.disposition_drift == 0
