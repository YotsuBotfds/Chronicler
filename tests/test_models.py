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
    Event,
    NamedEvent,
    ActiveCondition,
    WorldState,
    TurnSnapshot,
)


class TestRegion:
    def test_create_valid_region(self):
        r = Region(name="Verdant Plains", terrain="plains", carrying_capacity=70, resources="fertile")
        assert r.name == "Verdant Plains"
        assert r.controller is None

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

    def test_load_ignores_legacy_historical_figures_field(self, sample_world):
        payload = sample_world.model_dump()
        payload["historical_figures"] = [
            {
                "name": "Legacy Figure",
                "role": "ruler",
                "traits": ["bold"],
                "civilization": sample_world.civilizations[0].name,
                "alive": True,
                "deeds": ["Founded a city"],
            }
        ]
        loaded = WorldState.model_validate(payload)
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


def test_turn_snapshot_has_climate_phase():
    snap = TurnSnapshot(turn=1, civ_stats={}, region_control={}, relationships={})
    assert snap.climate_phase == ""


def test_turn_snapshot_has_active_conditions():
    snap = TurnSnapshot(turn=1, civ_stats={}, region_control={}, relationships={})
    assert snap.active_conditions == []


def test_world_state_has_tuning_overrides(sample_world):
    assert sample_world.tuning_overrides == {}


from chronicler.models import (
    NarrativeRole, CausalLink, GapSummary, NarrativeMoment,
)


def test_narrative_role_values():
    assert NarrativeRole.INCITING == "inciting"
    assert NarrativeRole.ESCALATION == "escalation"
    assert NarrativeRole.CLIMAX == "climax"
    assert NarrativeRole.RESOLUTION == "resolution"
    assert NarrativeRole.CODA == "coda"


def test_causal_link_creation():
    link = CausalLink(
        cause_turn=10, cause_event_type="drought",
        effect_turn=18, effect_event_type="famine",
        pattern="drought→famine",
    )
    assert link.cause_turn == 10
    assert link.pattern == "drought→famine"


def test_gap_summary_stat_deltas_shape():
    gap = GapSummary(
        turn_range=(10, 30), event_count=15,
        top_event_type="war",
        stat_deltas={"Vrashni": {"population": -20, "military": 5, "stability": -12}},
        territory_changes=3,
    )
    assert gap.stat_deltas["Vrashni"]["population"] == -20
    assert gap.turn_range == (10, 30)


def test_narrative_moment_creation():
    from chronicler.models import Event
    event = Event(turn=10, event_type="war", actors=["Vrashni"], description="test")
    moment = NarrativeMoment(
        anchor_turn=10, turn_range=(8, 12),
        events=[event], named_events=[], score=15.0,
        causal_links=[], narrative_role=NarrativeRole.CLIMAX,
        bonus_applied=3.0,
    )
    assert moment.anchor_turn == 10
    assert moment.narrative_role == NarrativeRole.CLIMAX
    assert moment.bonus_applied == 3.0


def test_causal_link_round_trip():
    link = CausalLink(
        cause_turn=10, cause_event_type="drought",
        effect_turn=18, effect_event_type="famine",
        pattern="drought→famine",
    )
    data = link.model_dump()
    restored = CausalLink.model_validate(data)
    assert restored == link


def test_gap_summary_round_trip():
    gap = GapSummary(
        turn_range=(10, 30), event_count=15,
        top_event_type="war",
        stat_deltas={"Vrashni": {"population": -20}},
        territory_changes=3,
    )
    data = gap.model_dump()
    restored = GapSummary.model_validate(data)
    assert restored == gap
