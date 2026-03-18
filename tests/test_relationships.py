"""Tests for M17c: WarResult, rivalries, mentorships, marriages, and hostages."""
import pytest

from chronicler.action_engine import WarResult
from chronicler.models import Disposition, GreatPerson
from chronicler.relationships import (
    check_rivalry_formation,
    dissolve_dead_relationships,
    check_mentorship_formation,
    check_marriage_formation,
    capture_hostage,
    tick_hostages,
    release_hostage,
)


# --- Task 14: WarResult namedtuple ---

def test_war_result_namedtuple():
    result = WarResult("attacker_wins", "Plains")
    assert result.outcome == "attacker_wins"
    assert result.contested_region == "Plains"


def test_war_result_stalemate():
    result = WarResult("stalemate", None)
    assert result.outcome == "stalemate"
    assert result.contested_region is None


def test_war_result_defender_wins():
    result = WarResult("defender_wins", "Iron Peaks")
    assert result.outcome == "defender_wins"
    assert result.contested_region == "Iron Peaks"


# --- Task 15: Rivalries ---

def test_rivalry_forms_between_generals_at_war(make_world):
    world = make_world(num_civs=2, seed=42)
    civ1 = world.civilizations[0]
    civ2 = world.civilizations[1]
    civ1.great_persons = [
        GreatPerson(
            name="Gen1", role="general", trait="bold",
            civilization=civ1.name, origin_civilization=civ1.name, born_turn=0,
        )
    ]
    civ2.great_persons = [
        GreatPerson(
            name="Gen2", role="general", trait="aggressive",
            civilization=civ2.name, origin_civilization=civ2.name, born_turn=0,
        )
    ]
    world.active_wars = [(civ1.name, civ2.name)]
    formed = check_rivalry_formation(world)
    assert len(formed) == 1
    assert formed[0]["type"] == "rivalry"


def test_rivalry_not_formed_different_roles(make_world):
    world = make_world(num_civs=2, seed=42)
    civ1 = world.civilizations[0]
    civ2 = world.civilizations[1]
    civ1.great_persons = [
        GreatPerson(name="Gen1", role="general", trait="bold", civilization=civ1.name, origin_civilization=civ1.name, born_turn=0)
    ]
    civ2.great_persons = [
        GreatPerson(name="Mer2", role="merchant", trait="shrewd", civilization=civ2.name, origin_civilization=civ2.name, born_turn=0)
    ]
    world.active_wars = [(civ1.name, civ2.name)]
    formed = check_rivalry_formation(world)
    assert len(formed) == 0


def test_rivalry_not_duplicated(make_world):
    world = make_world(num_civs=2, seed=42)
    civ1 = world.civilizations[0]
    civ2 = world.civilizations[1]
    civ1.great_persons = [
        GreatPerson(name="Gen1", role="general", trait="bold", civilization=civ1.name, origin_civilization=civ1.name, born_turn=0)
    ]
    civ2.great_persons = [
        GreatPerson(name="Gen2", role="general", trait="aggressive", civilization=civ2.name, origin_civilization=civ2.name, born_turn=0)
    ]
    world.active_wars = [(civ1.name, civ2.name)]
    # Pre-populate existing rivalry
    world.character_relationships = [
        {"type": "rivalry", "person_a": "Gen1", "person_b": "Gen2", "civ_a": civ1.name, "civ_b": civ2.name, "formed_turn": 0}
    ]
    formed = check_rivalry_formation(world)
    assert len(formed) == 0


def test_rivalry_dissolved_on_death(make_world):
    world = make_world(num_civs=2, seed=42)
    world.character_relationships = [
        {"type": "rivalry", "person_a": "Gen1", "person_b": "Gen2", "civ_a": "Civ1", "civ_b": "Civ2", "formed_turn": 0},
    ]
    dissolved = dissolve_dead_relationships(world, dead_names={"Gen1"})
    assert len(world.character_relationships) == 0
    assert len(dissolved) == 1


def test_dissolve_keeps_unrelated_relationships(make_world):
    world = make_world(num_civs=2, seed=42)
    world.character_relationships = [
        {"type": "rivalry", "person_a": "Gen1", "person_b": "Gen2", "civ_a": "Civ1", "civ_b": "Civ2", "formed_turn": 0},
        {"type": "mentorship", "person_a": "Mentor", "person_b": "Student", "civ_a": "Civ1", "civ_b": "Civ1", "formed_turn": 0},
    ]
    dissolved = dissolve_dead_relationships(world, dead_names={"Gen1"})
    assert len(world.character_relationships) == 1
    assert world.character_relationships[0]["type"] == "mentorship"


# --- Task 16: Mentorships ---

def test_mentorship_forms_with_compatible_traits(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.leader.secondary_trait = "conqueror"
    civ.great_persons = [
        GreatPerson(
            name="OldGeneral", role="general", trait="bold",
            civilization=civ.name, origin_civilization=civ.name, born_turn=0,
        )
    ]
    formed = check_mentorship_formation(world)
    assert len(formed) == 1
    assert formed[0]["type"] == "mentorship"


def test_mentorship_not_formed_incompatible_trait(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.leader.secondary_trait = "diplomat"
    civ.great_persons = [
        GreatPerson(name="OldGeneral", role="general", trait="bold", civilization=civ.name, origin_civilization=civ.name, born_turn=0)
    ]
    formed = check_mentorship_formation(world)
    assert len(formed) == 0


def test_mentorship_not_formed_no_secondary_trait(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.leader.secondary_trait = None
    civ.great_persons = [
        GreatPerson(name="OldGeneral", role="general", trait="bold", civilization=civ.name, origin_civilization=civ.name, born_turn=0)
    ]
    formed = check_mentorship_formation(world)
    assert len(formed) == 0


def test_mentorship_not_duplicated(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.leader.secondary_trait = "conqueror"
    civ.great_persons = [
        GreatPerson(name="OldGeneral", role="general", trait="bold", civilization=civ.name, origin_civilization=civ.name, born_turn=0)
    ]
    world.character_relationships = [
        {"type": "mentorship", "person_a": "OldGeneral", "person_b": civ.leader.name, "civ_a": civ.name, "civ_b": civ.name, "formed_turn": 0}
    ]
    formed = check_mentorship_formation(world)
    assert len(formed) == 0


# --- Marriage Alliance ---

def test_marriage_alliance_requires_allied(make_world):
    world = make_world(num_civs=2, seed=42)
    civ1 = world.civilizations[0]
    civ2 = world.civilizations[1]
    rel12 = world.relationships[civ1.name][civ2.name]
    rel12.disposition = Disposition.ALLIED
    rel12.allied_turns = 15
    rel21 = world.relationships[civ2.name][civ1.name]
    rel21.disposition = Disposition.ALLIED
    rel21.allied_turns = 15
    civ1.great_persons = [
        GreatPerson(name="GP1", role="merchant", trait="shrewd", civilization=civ1.name, origin_civilization=civ1.name, born_turn=0)
    ]
    civ2.great_persons = [
        GreatPerson(name="GP2", role="general", trait="bold", civilization=civ2.name, origin_civilization=civ2.name, born_turn=0)
    ]
    formed = check_marriage_formation(world)
    assert isinstance(formed, list)


def test_marriage_not_formed_when_neutral(make_world):
    world = make_world(num_civs=2, seed=42)
    civ1 = world.civilizations[0]
    civ2 = world.civilizations[1]
    # Disposition is NEUTRAL by default
    civ1.great_persons = [
        GreatPerson(name="GP1", role="merchant", trait="shrewd", civilization=civ1.name, origin_civilization=civ1.name, born_turn=0)
    ]
    civ2.great_persons = [
        GreatPerson(name="GP2", role="general", trait="bold", civilization=civ2.name, origin_civilization=civ2.name, born_turn=0)
    ]
    formed = check_marriage_formation(world)
    assert len(formed) == 0


# --- Task 17: Hostage Exchanges ---

def test_capture_hostage_takes_youngest(make_world):
    world = make_world(num_civs=2, seed=42)
    loser = world.civilizations[0]
    winner = world.civilizations[1]
    gp_old = GreatPerson(
        name="Old", role="merchant", trait="shrewd",
        civilization=loser.name, origin_civilization=loser.name, born_turn=0,
    )
    gp_young = GreatPerson(
        name="Young", role="general", trait="bold",
        civilization=loser.name, origin_civilization=loser.name, born_turn=5,
    )
    loser.great_persons = [gp_old, gp_young]
    captured = capture_hostage(loser, winner, world, contested_region="Battlefield")
    assert captured is not None
    assert captured.name == "Young"
    assert captured.is_hostage is True
    assert captured.region == "Battlefield"
    assert captured in winner.great_persons


def test_capture_hostage_removed_from_loser(make_world):
    world = make_world(num_civs=2, seed=42)
    loser = world.civilizations[0]
    winner = world.civilizations[1]
    gp = GreatPerson(
        name="SomeGP", role="general", trait="bold",
        civilization=loser.name, origin_civilization=loser.name, born_turn=0,
    )
    loser.great_persons = [gp]
    capture_hostage(loser, winner, world)
    assert gp not in loser.great_persons


def test_capture_hostage_creates_new_when_no_candidates(make_world):
    world = make_world(num_civs=2, seed=42)
    loser = world.civilizations[0]
    winner = world.civilizations[1]
    loser.great_persons = []
    captured = capture_hostage(loser, winner, world, contested_region="Plains")
    assert captured is not None
    assert captured.is_hostage is True
    assert captured.civilization == winner.name
    assert captured.origin_civilization == loser.name


def test_hostage_cultural_conversion_at_10_turns(make_world):
    world = make_world(num_civs=2, seed=42)
    captor = world.civilizations[0]
    hostage = GreatPerson(
        name="Captive", role="general", trait="bold",
        civilization=captor.name, origin_civilization="Other",
        born_turn=0, is_hostage=True, hostage_turns=9,
    )
    captor.great_persons = [hostage]
    tick_hostages(world)
    assert hostage.hostage_turns == 10
    assert hostage.cultural_identity == captor.name


def test_hostage_auto_release_at_15_turns(make_world):
    world = make_world(num_civs=2, seed=42)
    captor = world.civilizations[0]
    origin = world.civilizations[1]
    hostage = GreatPerson(
        name="Captive", role="general", trait="bold",
        civilization=captor.name, origin_civilization=origin.name,
        born_turn=0, is_hostage=True, hostage_turns=14,
    )
    captor.great_persons = [hostage]
    released = tick_hostages(world)
    assert len(released) == 1
    assert hostage.is_hostage is False
    assert hostage in origin.great_persons


def test_hostage_not_released_before_15_turns(make_world):
    world = make_world(num_civs=2, seed=42)
    captor = world.civilizations[0]
    hostage = GreatPerson(
        name="Captive", role="general", trait="bold",
        civilization=captor.name, origin_civilization=captor.name,
        born_turn=0, is_hostage=True, hostage_turns=10,
    )
    captor.great_persons = [hostage]
    released = tick_hostages(world)
    assert len(released) == 0
    assert hostage.is_hostage is True


def test_release_hostage_moves_to_origin(make_world):
    world = make_world(num_civs=2, seed=42)
    captor = world.civilizations[0]
    origin = world.civilizations[1]
    hostage = GreatPerson(
        name="Freed", role="general", trait="bold",
        civilization=captor.name, origin_civilization=origin.name,
        born_turn=0, is_hostage=True,
    )
    captor.great_persons = [hostage]
    release_hostage(hostage, captor, origin, world)
    assert hostage in origin.great_persons
    assert hostage not in captor.great_persons
    assert hostage.is_hostage is False
    assert hostage.civilization == origin.name


# --- M40: Social Networks ---

def test_great_person_origin_region_defaults_none():
    gp = GreatPerson(
        name="Test", role="general", trait="bold",
        civilization="Civ1", origin_civilization="Civ1", born_turn=0,
    )
    assert gp.origin_region is None


# --- Task 18: Integration test ---

def test_m17c_integration_relationships_across_turns(make_world):
    from chronicler.simulation import run_turn
    from chronicler.models import ActionType
    world = make_world(num_civs=3, seed=42)
    for turn in range(10):
        world.turn = turn
        run_turn(world, action_selector=lambda c, w: ActionType.DEVELOP, narrator=lambda w, e: "", seed=world.seed)
    for rel in world.character_relationships:
        assert rel["type"] in ("rivalry", "mentorship", "marriage")
