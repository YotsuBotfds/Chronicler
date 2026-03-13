"""Tests for core data models — validation, serialization, and invariants."""
import pytest
from chronicler.models import (
    TechEra,
    Disposition,
    ActionType,
    Region,
    Leader,
    Civilization,
    Relationship,
    HistoricalFigure,
    Event,
    ActiveCondition,
    WorldState,
)


class TestRegion:
    def test_create_valid_region(self):
        r = Region(name="Verdant Plains", terrain="plains", carrying_capacity=7, resources="fertile")
        assert r.name == "Verdant Plains"
        assert r.controller is None

    def test_carrying_capacity_bounds(self):
        with pytest.raises(Exception):
            Region(name="X", terrain="plains", carrying_capacity=0, resources="fertile")
        with pytest.raises(Exception):
            Region(name="X", terrain="plains", carrying_capacity=11, resources="fertile")


class TestCivilization:
    def test_create_with_defaults(self):
        leader = Leader(name="Kael", trait="ambitious", reign_start=0)
        civ = Civilization(
            name="Kethani Empire",
            population=5,
            military=4,
            economy=6,
            culture=7,
            stability=5,
            leader=leader,
            domains=["maritime", "commerce"],
            values=["Honor", "Trade"],
        )
        assert civ.tech_era == TechEra.TRIBAL
        assert civ.treasury == 0
        assert civ.asabiya == 0.5

    def test_stat_bounds(self):
        leader = Leader(name="X", trait="bold", reign_start=0)
        with pytest.raises(Exception):
            Civilization(
                name="Bad", population=0, military=1, economy=1,
                culture=1, stability=1, leader=leader,
            )
        with pytest.raises(Exception):
            Civilization(
                name="Bad", population=11, military=1, economy=1,
                culture=1, stability=1, leader=leader,
            )


class TestRelationship:
    def test_defaults(self):
        r = Relationship()
        assert r.disposition == Disposition.NEUTRAL
        assert r.treaties == []
        assert r.grievances == []
        assert r.trade_volume == 0


class TestWorldState:
    def test_json_round_trip(self, sample_world):
        """WorldState serializes to JSON and deserializes identically."""
        json_str = sample_world.model_dump_json(indent=2)
        restored = WorldState.model_validate_json(json_str)
        assert restored.name == sample_world.name
        assert len(restored.civilizations) == len(sample_world.civilizations)
        assert restored.turn == sample_world.turn

    def test_save_and_load_file(self, sample_world, tmp_path):
        """WorldState persists to a JSON file and loads back."""
        path = tmp_path / "world.json"
        path.write_text(sample_world.model_dump_json(indent=2))
        loaded = WorldState.model_validate_json(path.read_text())
        assert loaded.name == sample_world.name
        assert loaded.civilizations[0].name == sample_world.civilizations[0].name


class TestWorldStatePersistence:
    def test_save_creates_file(self, sample_world, tmp_path):
        path = tmp_path / "state.json"
        sample_world.save(path)
        assert path.exists()

    def test_load_restores_state(self, sample_world, tmp_path):
        path = tmp_path / "state.json"
        sample_world.save(path)
        loaded = WorldState.load(path)
        assert loaded.name == sample_world.name
        assert len(loaded.civilizations) == 2

    def test_load_nonexistent_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            WorldState.load(tmp_path / "nope.json")
