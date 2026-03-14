"""Tests for GreatPerson model and M17 fields on Civilization, WorldState, CivSnapshot."""
import pytest
from chronicler.models import GreatPerson, Civilization, WorldState, CivSnapshot


def test_great_person_creation():
    gp = GreatPerson(
        name="General Khotun",
        role="general",
        trait="aggressive",
        civilization="Mongol",
        origin_civilization="Mongol",
        born_turn=10,
    )
    assert gp.alive is True
    assert gp.active is True
    assert gp.fate == "active"
    assert gp.deeds == []
    assert gp.movement_id is None


def test_civilization_great_person_fields(make_civ):
    """New M17 fields have correct defaults."""
    civ = make_civ("TestCiv")
    assert civ.great_persons == []
    assert civ.traditions == []
    assert civ.legacy_counts == {}
    assert civ.event_counts == {}
    assert civ.war_win_turns == []
    assert civ.folk_heroes == []
    assert civ.succession_crisis_turns_remaining == 0
    assert civ.succession_candidates == []


def test_leader_grudges_field(make_civ):
    """Leader.grudges has correct default."""
    civ = make_civ("TestCiv")
    assert civ.leader.grudges == []


def test_worldstate_great_person_fields(make_world):
    """New M17 WorldState fields have correct defaults."""
    world = make_world(num_civs=2)
    assert world.retired_persons == []
    assert world.character_relationships == []
    assert world.great_person_cooldowns == {}


def test_civsnapshot_great_person_fields():
    """New M17 CivSnapshot fields have correct defaults."""
    from chronicler.models import TechEra
    snap = CivSnapshot(
        population=50, military=30, economy=40, culture=30, stability=50,
        treasury=50, asabiya=0.5, tech_era=TechEra.IRON,
        trait="cautious", regions=["r1"], leader_name="Leader", alive=True,
    )
    assert snap.great_persons == []
    assert snap.traditions == []
    assert snap.folk_heroes == []
    assert snap.active_crisis is False


def test_great_person_movement_id_is_str():
    """movement_id must be str, not int (Movement.id is str)."""
    gp = GreatPerson(
        name="Prophet Zara",
        role="prophet",
        trait="charismatic",
        civilization="Kethani",
        origin_civilization="Kethani",
        born_turn=5,
        movement_id="mv_001",
    )
    assert isinstance(gp.movement_id, str)
    assert gp.movement_id == "mv_001"


def test_great_person_hostage_defaults():
    """Hostage-related fields default to safe values."""
    gp = GreatPerson(
        name="Noble Hostage",
        role="hostage",
        trait="diplomatic",
        civilization="Dorrathi",
        origin_civilization="Kethani",
        born_turn=20,
    )
    assert gp.is_hostage is False
    assert gp.hostage_turns == 0
    assert gp.captured_by is None
    assert gp.recognized_by == []
