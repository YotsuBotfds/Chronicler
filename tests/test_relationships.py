"""Tests for M17c: WarResult, rivalries, mentorships, marriages, and hostages."""
import pytest

from chronicler.action_engine import WarResult
from chronicler.models import Disposition, GreatPerson
from chronicler.relationships import (
    check_rivalry_formation,
    dissolve_dead_relationships,
    check_mentorship_formation,
    check_marriage_formation,
    check_exile_bond_formation,
    check_coreligionist_formation,
    form_and_sync_relationships,
    capture_hostage,
    tick_hostages,
    release_hostage,
    dissolve_edges,
    REL_MENTOR,
    REL_RIVAL,
    REL_MARRIAGE,
    REL_EXILE_BOND,
    REL_CORELIGIONIST,
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


# --- Task 7: Rivalries (edge tuples) ---

def test_rivalry_forms_between_agents_at_war(make_world):
    world = make_world(num_civs=2, seed=42)
    civ1, civ2 = world.civilizations[0], world.civilizations[1]
    civ1.great_persons = [
        GreatPerson(name="Gen1", role="general", trait="bold",
                    civilization=civ1.name, origin_civilization=civ1.name,
                    born_turn=0, source="agent", agent_id=100)
    ]
    civ2.great_persons = [
        GreatPerson(name="Gen2", role="general", trait="aggressive",
                    civilization=civ2.name, origin_civilization=civ2.name,
                    born_turn=0, source="agent", agent_id=200)
    ]
    world.active_wars = [(civ1.name, civ2.name)]
    formed = check_rivalry_formation(world, [])
    assert len(formed) == 1
    agent_a, agent_b, rel_type, formed_turn = formed[0]
    assert rel_type == REL_RIVAL
    assert min(agent_a, agent_b) == 100
    assert max(agent_a, agent_b) == 200


def test_rivalry_skips_aggregate_source(make_world):
    world = make_world(num_civs=2, seed=42)
    civ1, civ2 = world.civilizations[0], world.civilizations[1]
    civ1.great_persons = [
        GreatPerson(name="Gen1", role="general", trait="bold",
                    civilization=civ1.name, origin_civilization=civ1.name,
                    born_turn=0, source="aggregate", agent_id=None)
    ]
    civ2.great_persons = [
        GreatPerson(name="Gen2", role="general", trait="aggressive",
                    civilization=civ2.name, origin_civilization=civ2.name,
                    born_turn=0, source="agent", agent_id=200)
    ]
    world.active_wars = [(civ1.name, civ2.name)]
    formed = check_rivalry_formation(world, [])
    assert len(formed) == 0


def test_rivalry_not_duplicated_edge(make_world):
    world = make_world(num_civs=2, seed=42)
    civ1, civ2 = world.civilizations[0], world.civilizations[1]
    civ1.great_persons = [
        GreatPerson(name="Gen1", role="general", trait="bold",
                    civilization=civ1.name, origin_civilization=civ1.name,
                    born_turn=0, source="agent", agent_id=100)
    ]
    civ2.great_persons = [
        GreatPerson(name="Gen2", role="general", trait="aggressive",
                    civilization=civ2.name, origin_civilization=civ2.name,
                    born_turn=0, source="agent", agent_id=200)
    ]
    world.active_wars = [(civ1.name, civ2.name)]
    existing_edges = [(100, 200, REL_RIVAL, 0)]
    formed = check_rivalry_formation(world, existing_edges)
    assert len(formed) == 0


# --- Task 8: Mentorships (edge tuples) ---

def test_mentorship_forms_same_occupation_skill_gap(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.great_persons = [
        GreatPerson(name="OldGen", role="general", trait="bold",
                    civilization=civ.name, origin_civilization=civ.name,
                    born_turn=0, source="agent", agent_id=100, region="Civ0_region"),
        GreatPerson(name="YoungGen", role="general", trait="cautious",
                    civilization=civ.name, origin_civilization=civ.name,
                    born_turn=50, source="agent", agent_id=200, region="Civ0_region"),
    ]
    formed = check_mentorship_formation(world, [])
    assert len(formed) == 1
    agent_a, agent_b, rel_type, _ = formed[0]
    assert rel_type == REL_MENTOR
    assert agent_a == 100  # mentor (senior)
    assert agent_b == 200  # apprentice


def test_mentorship_requires_same_region(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.great_persons = [
        GreatPerson(name="A", role="general", trait="bold", civilization=civ.name,
                    origin_civilization=civ.name, born_turn=0, source="agent",
                    agent_id=100, region="Region1"),
        GreatPerson(name="B", role="general", trait="bold", civilization=civ.name,
                    origin_civilization=civ.name, born_turn=50, source="agent",
                    agent_id=200, region="Region2"),
    ]
    formed = check_mentorship_formation(world, [])
    assert len(formed) == 0


def test_mentorship_requires_same_role(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.great_persons = [
        GreatPerson(name="A", role="general", trait="bold", civilization=civ.name,
                    origin_civilization=civ.name, born_turn=0, source="agent",
                    agent_id=100, region="R1"),
        GreatPerson(name="B", role="merchant", trait="bold", civilization=civ.name,
                    origin_civilization=civ.name, born_turn=50, source="agent",
                    agent_id=200, region="R1"),
    ]
    formed = check_mentorship_formation(world, [])
    assert len(formed) == 0


def test_mentorship_skips_aggregate(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.great_persons = [
        GreatPerson(name="A", role="general", trait="bold", civilization=civ.name,
                    origin_civilization=civ.name, born_turn=0, source="aggregate",
                    agent_id=None, region="R1"),
        GreatPerson(name="B", role="general", trait="bold", civilization=civ.name,
                    origin_civilization=civ.name, born_turn=50, source="agent",
                    agent_id=200, region="R1"),
    ]
    formed = check_mentorship_formation(world, [])
    assert len(formed) == 0


# --- Task 9: Marriage Alliance (edge tuples) ---

def test_marriage_forms_between_allied_agent_chars(make_world):
    world = make_world(num_civs=2, seed=42)
    civ1, civ2 = world.civilizations[0], world.civilizations[1]
    rel12 = world.relationships[civ1.name][civ2.name]
    rel12.disposition = Disposition.ALLIED
    rel12.allied_turns = 15
    civ1.great_persons = [
        GreatPerson(name="GP1", role="merchant", trait="shrewd",
                    civilization=civ1.name, origin_civilization=civ1.name,
                    born_turn=0, source="agent", agent_id=100)
    ]
    civ2.great_persons = [
        GreatPerson(name="GP2", role="general", trait="bold",
                    civilization=civ2.name, origin_civilization=civ2.name,
                    born_turn=0, source="agent", agent_id=200)
    ]
    formed = check_marriage_formation(world, [])
    for edge in formed:
        assert edge[2] == REL_MARRIAGE


def test_marriage_skips_aggregate(make_world):
    world = make_world(num_civs=2, seed=42)
    civ1, civ2 = world.civilizations[0], world.civilizations[1]
    rel12 = world.relationships[civ1.name][civ2.name]
    rel12.disposition = Disposition.ALLIED
    rel12.allied_turns = 15
    civ1.great_persons = [
        GreatPerson(name="GP1", role="merchant", trait="shrewd",
                    civilization=civ1.name, origin_civilization=civ1.name,
                    born_turn=0, source="aggregate", agent_id=None)
    ]
    civ2.great_persons = [
        GreatPerson(name="GP2", role="general", trait="bold",
                    civilization=civ2.name, origin_civilization=civ2.name,
                    born_turn=0, source="agent", agent_id=200)
    ]
    formed = check_marriage_formation(world, [])
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

# --- Task 6: dissolve_edges ---

def test_dissolve_edges_death_removes_edge():
    edges = [(100, 200, REL_RIVAL, 50)]
    active_agent_ids = {200}
    surviving, dissolved = dissolve_edges(edges, active_agent_ids)
    assert len(surviving) == 0
    assert len(dissolved) == 1


def test_dissolve_edges_both_alive_survives():
    edges = [(100, 200, REL_RIVAL, 50)]
    active_agent_ids = {100, 200}
    surviving, dissolved = dissolve_edges(edges, active_agent_ids)
    assert len(surviving) == 1
    assert len(dissolved) == 0


def test_dissolve_edges_coreligionist_belief_divergence():
    edges = [(100, 200, REL_CORELIGIONIST, 50)]
    active_agent_ids = {100, 200}
    belief_by_agent = {100: 1, 200: 2}
    surviving, dissolved = dissolve_edges(edges, active_agent_ids, belief_by_agent=belief_by_agent)
    assert len(surviving) == 0
    assert len(dissolved) == 1


def test_dissolve_edges_coreligionist_same_belief_survives():
    edges = [(100, 200, REL_CORELIGIONIST, 50)]
    active_agent_ids = {100, 200}
    belief_by_agent = {100: 1, 200: 1}
    surviving, dissolved = dissolve_edges(edges, active_agent_ids, belief_by_agent=belief_by_agent)
    assert len(surviving) == 1
    assert len(dissolved) == 0


def test_dissolve_edges_exile_bond_only_death():
    edges = [(100, 200, REL_EXILE_BOND, 50)]
    active_agent_ids = {100, 200}
    surviving, dissolved = dissolve_edges(edges, active_agent_ids)
    assert len(surviving) == 1


def test_dissolve_edges_marriage_survives_war():
    edges = [(100, 200, REL_MARRIAGE, 50)]
    active_agent_ids = {100, 200}
    surviving, dissolved = dissolve_edges(edges, active_agent_ids)
    assert len(surviving) == 1


def test_great_person_origin_region_defaults_none():
    gp = GreatPerson(
        name="Test", role="general", trait="bold",
        civilization="Civ1", origin_civilization="Civ1", born_turn=0,
    )
    assert gp.origin_region is None


# --- Task 10: Exile Bond Formation ---

def test_exile_bond_forms_shared_origin_colocated(make_world):
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    civ.great_persons = [
        GreatPerson(name="Exile1", role="general", trait="bold",
                    civilization=civ.name, origin_civilization=civ.name,
                    born_turn=0, source="agent", agent_id=100,
                    origin_region="Homeland", region="Refuge"),
        GreatPerson(name="Exile2", role="merchant", trait="shrewd",
                    civilization=civ.name, origin_civilization=civ.name,
                    born_turn=10, source="agent", agent_id=200,
                    origin_region="Homeland", region="Refuge"),
    ]
    formed = check_exile_bond_formation(world, [])
    assert len(formed) == 1
    assert formed[0][2] == REL_EXILE_BOND


def test_exile_bond_skips_none_origin(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.great_persons = [
        GreatPerson(name="A", role="general", trait="bold",
                    civilization=civ.name, origin_civilization=civ.name,
                    born_turn=0, source="agent", agent_id=100,
                    origin_region=None, region="Refuge"),
        GreatPerson(name="B", role="merchant", trait="shrewd",
                    civilization=civ.name, origin_civilization=civ.name,
                    born_turn=10, source="agent", agent_id=200,
                    origin_region="Homeland", region="Refuge"),
    ]
    formed = check_exile_bond_formation(world, [])
    assert len(formed) == 0


def test_exile_bond_requires_same_region(make_world):
    world = make_world(num_civs=2, seed=42)
    civ1, civ2 = world.civilizations[0], world.civilizations[1]
    civ1.great_persons = [
        GreatPerson(name="A", role="general", trait="bold",
                    civilization=civ1.name, origin_civilization=civ1.name,
                    born_turn=0, source="agent", agent_id=100,
                    origin_region="Homeland", region="Refuge1"),
    ]
    civ2.great_persons = [
        GreatPerson(name="B", role="merchant", trait="shrewd",
                    civilization=civ2.name, origin_civilization=civ2.name,
                    born_turn=10, source="agent", agent_id=200,
                    origin_region="Homeland", region="Refuge2"),
    ]
    formed = check_exile_bond_formation(world, [])
    assert len(formed) == 0


# --- Task 11: Co-religionist Formation ---

def test_coreligionist_forms_shared_minority_faith(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.great_persons = [
        GreatPerson(name="A", role="prophet", trait="wise",
                    civilization=civ.name, origin_civilization=civ.name,
                    born_turn=0, source="agent", agent_id=100, region="R1"),
        GreatPerson(name="B", role="prophet", trait="pious",
                    civilization=civ.name, origin_civilization=civ.name,
                    born_turn=10, source="agent", agent_id=200, region="R1"),
    ]
    belief_by_agent = {100: 5, 200: 5}
    region_belief_fractions = {"R1": {5: 0.20, 1: 0.80}}
    formed = check_coreligionist_formation(world, [], belief_by_agent, region_belief_fractions)
    assert len(formed) == 1
    assert formed[0][2] == REL_CORELIGIONIST


def test_coreligionist_not_formed_majority_faith(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.great_persons = [
        GreatPerson(name="A", role="prophet", trait="wise",
                    civilization=civ.name, origin_civilization=civ.name,
                    born_turn=0, source="agent", agent_id=100, region="R1"),
        GreatPerson(name="B", role="prophet", trait="pious",
                    civilization=civ.name, origin_civilization=civ.name,
                    born_turn=10, source="agent", agent_id=200, region="R1"),
    ]
    belief_by_agent = {100: 5, 200: 5}
    region_belief_fractions = {"R1": {5: 0.50}}
    formed = check_coreligionist_formation(world, [], belief_by_agent, region_belief_fractions)
    assert len(formed) == 0


def test_coreligionist_requires_colocation(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.great_persons = [
        GreatPerson(name="A", role="prophet", trait="wise",
                    civilization=civ.name, origin_civilization=civ.name,
                    born_turn=0, source="agent", agent_id=100, region="R1"),
        GreatPerson(name="B", role="prophet", trait="pious",
                    civilization=civ.name, origin_civilization=civ.name,
                    born_turn=10, source="agent", agent_id=200, region="R2"),
    ]
    belief_by_agent = {100: 5, 200: 5}
    region_belief_fractions = {"R1": {5: 0.10}, "R2": {5: 0.10}}
    formed = check_coreligionist_formation(world, [], belief_by_agent, region_belief_fractions)
    assert len(formed) == 0


# --- Task 12: Coordinator form_and_sync_relationships ---

def test_coordinator_dissolves_dead_agent_edges():
    from chronicler.models import WorldState

    class MockBridge:
        def __init__(self, initial_edges):
            self._edges = initial_edges
            self.replaced = None
        def read_social_edges(self):
            return list(self._edges)
        def replace_social_edges(self, edges):
            self.replaced = edges

    initial = [(100, 200, REL_RIVAL, 10)]
    bridge = MockBridge(initial)
    world = WorldState(name="TestWorld", seed=42, turn=50, regions=[], civilizations=[], relationships={})
    active_ids = {200}
    dissolved = form_and_sync_relationships(world, bridge, active_ids, {}, {})
    assert len(dissolved) == 1
    assert bridge.replaced is not None
    assert len(bridge.replaced) == 0


def test_coordinator_forms_new_edges_and_writes_back(make_world):
    class MockBridge:
        def __init__(self):
            self._edges = []
            self.replaced = None
        def read_social_edges(self):
            return list(self._edges)
        def replace_social_edges(self, edges):
            self.replaced = edges

    bridge = MockBridge()
    world = make_world(num_civs=2, seed=42)
    civ1, civ2 = world.civilizations[0], world.civilizations[1]
    civ1.great_persons = [
        GreatPerson(name="Gen1", role="general", trait="bold",
                    civilization=civ1.name, origin_civilization=civ1.name,
                    born_turn=0, source="agent", agent_id=100)
    ]
    civ2.great_persons = [
        GreatPerson(name="Gen2", role="general", trait="aggressive",
                    civilization=civ2.name, origin_civilization=civ2.name,
                    born_turn=0, source="agent", agent_id=200)
    ]
    world.active_wars = [(civ1.name, civ2.name)]
    dissolved = form_and_sync_relationships(world, bridge, {100, 200}, {}, {})
    assert len(dissolved) == 0
    assert bridge.replaced is not None
    assert len(bridge.replaced) >= 1
    assert any(e[2] == REL_RIVAL for e in bridge.replaced)
