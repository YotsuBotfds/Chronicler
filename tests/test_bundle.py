"""Tests for snapshot models and bundle assembly."""
import json
import pytest
from chronicler.models import (
    CivSnapshot, RelationshipSnapshot, TurnSnapshot, TechEra, Region,
)
from chronicler.scenario import RegionOverride, ScenarioConfig, apply_scenario
from chronicler.models import WorldState, Leader, Civilization, Relationship, Disposition


class TestSnapshotModels:
    def test_civ_snapshot_round_trip(self):
        snap = CivSnapshot(
            population=7, military=5, economy=8, culture=6, stability=6,
            treasury=12, asabiya=0.6, tech_era=TechEra.IRON,
            trait="calculating", regions=["Verdant Plains", "Sapphire Coast"],
            leader_name="Empress Vaelith", alive=True,
        )
        data = json.loads(snap.model_dump_json())
        restored = CivSnapshot.model_validate(data)
        assert restored.population == 7
        assert restored.tech_era == TechEra.IRON
        assert restored.trait == "calculating"
        assert restored.alive is True
        assert restored.regions == ["Verdant Plains", "Sapphire Coast"]

    def test_relationship_snapshot_round_trip(self):
        snap = RelationshipSnapshot(disposition="hostile")
        data = json.loads(snap.model_dump_json())
        restored = RelationshipSnapshot.model_validate(data)
        assert restored.disposition == "hostile"

    def test_turn_snapshot_round_trip(self):
        snap = TurnSnapshot(
            turn=5,
            civ_stats={
                "Kethani Empire": CivSnapshot(
                    population=7, military=5, economy=8, culture=6,
                    stability=6, treasury=12, asabiya=0.6,
                    tech_era=TechEra.IRON, trait="calculating",
                    regions=["Verdant Plains"], leader_name="Empress Vaelith",
                    alive=True,
                ),
            },
            region_control={"Verdant Plains": "Kethani Empire", "Thornwood": None},
            relationships={
                "Kethani Empire": {
                    "Dorrathi Clans": RelationshipSnapshot(disposition="suspicious"),
                },
            },
        )
        data = json.loads(snap.model_dump_json())
        restored = TurnSnapshot.model_validate(data)
        assert restored.turn == 5
        assert restored.civ_stats["Kethani Empire"].population == 7
        assert restored.region_control["Thornwood"] is None
        assert restored.relationships["Kethani Empire"]["Dorrathi Clans"].disposition == "suspicious"


class TestRegionCoordinates:
    def test_region_defaults_to_no_coordinates(self):
        r = Region(name="Plains", terrain="plains", carrying_capacity=5, resources="fertile")
        assert r.x is None
        assert r.y is None

    def test_region_with_coordinates(self):
        r = Region(name="Plains", terrain="plains", carrying_capacity=5, resources="fertile",
                    x=0.3, y=0.7)
        assert r.x == 0.3
        assert r.y == 0.7


class TestRegionCoordinatePropagation:
    def test_apply_scenario_copies_coordinates(self, sample_world):
        config = ScenarioConfig(
            name="coord_test",
            regions=[
                RegionOverride(name="Verdant Plains", x=0.2, y=0.8),
            ],
        )
        apply_scenario(sample_world, config)
        region = next(r for r in sample_world.regions if r.name == "Verdant Plains")
        assert region.x == 0.2
        assert region.y == 0.8

    def test_apply_scenario_leaves_coords_none_when_absent(self, sample_world):
        config = ScenarioConfig(
            name="no_coord_test",
            regions=[
                RegionOverride(name="Verdant Plains", terrain="desert"),
            ],
        )
        apply_scenario(sample_world, config)
        region = next(r for r in sample_world.regions if r.name == "Verdant Plains")
        assert region.x is None
        assert region.y is None
