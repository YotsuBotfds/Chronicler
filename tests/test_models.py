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
    NamedEvent,
    ActiveCondition,
    WorldState,
)


class TestRegion:
    def test_create_valid_region(self):
        r = Region(name="Verdant Plains", terrain="plains", carrying_capacity=70, resources="fertile")
        assert r.name == "Verdant Plains"
        assert r.controller is None

    def test_carrying_capacity_bounds(self):
        with pytest.raises(Exception):
            Region(name="X", terrain="plains", carrying_capacity=0, resources="fertile")
        with pytest.raises(Exception):
            Region(name="X", terrain="plains", carrying_capacity=101, resources="fertile")


class TestCivilization:
    def test_create_with_defaults(self):
        leader = Leader(name="Kael", trait="ambitious", reign_start=0)
        civ = Civilization(
            name="Kethani Empire",
            population=50,
            military=40,
            economy=60,
            culture=70,
            stability=50,
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
                name="Bad", population=0, military=10, economy=10,
                culture=10, stability=10, leader=leader,
            )
        with pytest.raises(Exception):
            Civilization(
                name="Bad", population=101, military=10, economy=10,
                culture=10, stability=10, leader=leader,
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


def test_named_event_model():
    ne = NamedEvent(
        name="The Siege of Thornwood",
        event_type="battle",
        turn=5,
        actors=["Kethani Empire"],
        region="Thornwood",
        description="A decisive victory",
    )
    assert ne.name == "The Siege of Thornwood"
    assert ne.region == "Thornwood"


def test_named_event_optional_region():
    ne = NamedEvent(
        name="The Iron Accord",
        event_type="treaty",
        turn=3,
        actors=["Kethani Empire", "Dorrathi Clans"],
        description="A peace treaty",
    )
    assert ne.region is None


def test_leader_new_fields():
    leader = Leader(name="Test", trait="bold", reign_start=0)
    assert leader.succession_type == "founder"
    assert leader.predecessor_name is None
    assert leader.rival_leader is None
    assert leader.rival_civ is None
    assert leader.secondary_trait is None


def test_civilization_new_fields():
    leader = Leader(name="Test", trait="bold", reign_start=0)
    civ = Civilization(
        name="Test Civ",
        population=50, military=50, economy=50, culture=50, stability=50,
        leader=leader, regions=["Region A"],
    )
    assert civ.cultural_milestones == []
    assert civ.action_counts == {}


def test_world_state_new_fields():
    ws = WorldState(name="Test", seed=42)
    assert ws.named_events == []
    assert ws.used_leader_names == []
    assert ws.action_history == {}


def test_named_event_serialization():
    ne = NamedEvent(
        name="The Siege of Thornwood",
        event_type="battle",
        turn=5,
        actors=["Kethani Empire"],
        region="Thornwood",
        description="A decisive victory",
    )
    data = ne.model_dump()
    restored = NamedEvent.model_validate(data)
    assert restored == ne


def test_civilization_leader_name_pool_default_none():
    civ = Civilization(
        name="Test", population=50, military=50, economy=50, culture=50, stability=50,
        leader=Leader(name="Test Leader", trait="bold", reign_start=0),
    )
    assert civ.leader_name_pool is None

def test_civilization_leader_name_pool_set():
    civ = Civilization(
        name="Test", population=50, military=50, economy=50, culture=50, stability=50,
        leader=Leader(name="Test Leader", trait="bold", reign_start=0),
        leader_name_pool=["A", "B", "C"],
    )
    assert civ.leader_name_pool == ["A", "B", "C"]


def test_world_state_scenario_name_default_none(sample_world):
    assert sample_world.scenario_name is None


def test_world_state_scenario_name_persists(sample_world, tmp_path):
    sample_world.scenario_name = "Dead Miles"
    path = tmp_path / "state.json"
    sample_world.save(path)
    loaded = WorldState.load(path)
    assert loaded.scenario_name == "Dead Miles"
