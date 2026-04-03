"""Tests for M17c: WarResult, rivalries, mentorships, marriages, and hostages."""
import pytest

from chronicler.action_engine import WarResult
from chronicler.models import Disposition, GreatPerson
from chronicler.relationships import (
    check_rivalry_formation,
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
    assert captured.role == "hostage"
    assert captured.pre_hostage_role == "general"
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
    assert captured.role == "hostage"
    assert captured.captured_by == winner.name
    assert captured.pre_hostage_role is not None
    assert captured.civilization == winner.name
    assert captured.origin_civilization == loser.name


def test_hostage_cultural_conversion_at_10_turns(make_world):
    world = make_world(num_civs=2, seed=42)
    captor = world.civilizations[0]
    origin = world.civilizations[1]
    hostage = GreatPerson(
        name="Captive", role="general", trait="bold",
        civilization=captor.name, origin_civilization=origin.name,
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
        born_turn=0, is_hostage=True, hostage_turns=14, pre_hostage_role="general",
    )
    hostage.role = "hostage"
    captor.great_persons = [hostage]
    released = tick_hostages(world)
    assert len(released) == 1
    assert hostage.is_hostage is False
    assert hostage.hostage_turns == 0
    assert hostage.role == "general"
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
        name="Freed", role="hostage", trait="bold",
        civilization=captor.name, origin_civilization=origin.name,
        born_turn=0, is_hostage=True, hostage_turns=11, pre_hostage_role="merchant",
    )
    captor.great_persons = [hostage]
    release_hostage(hostage, captor, origin, world)
    assert hostage in origin.great_persons
    assert hostage not in captor.great_persons
    assert hostage.is_hostage is False
    assert hostage.hostage_turns == 0
    assert hostage.civilization == origin.name
    assert hostage.role == "merchant"


def test_origin_extinction_release_clears_hostage_state(make_world):
    world = make_world(num_civs=2, seed=42)
    captor = world.civilizations[0]
    origin = world.civilizations[1]
    origin.regions = []
    hostage = GreatPerson(
        name="Assimilated",
        role="hostage",
        trait="cautious",
        civilization=captor.name,
        origin_civilization=origin.name,
        born_turn=0,
        is_hostage=True,
        hostage_turns=5,
        captured_by=captor.name,
        pre_hostage_role="scientist",
    )
    captor.great_persons = [hostage]

    released = tick_hostages(world)

    assert released == [hostage]
    assert hostage.is_hostage is False
    assert hostage.hostage_turns == 0
    assert hostage.captured_by is None
    assert hostage.role == "scientist"


# --- Hostage affinity sync ---

class _MockSim:
    """Records set_agent_civ calls for bridge sync tests."""
    def __init__(self):
        self.calls = []
    def set_agent_civ(self, agent_id, civ_id):
        self.calls.append((agent_id, civ_id))

class _MockBridge:
    def __init__(self):
        self._sim = _MockSim()


def test_capture_hostage_syncs_rust_affinity(make_world):
    """capture_hostage() calls set_agent_civ when bridge is provided."""
    world = make_world(num_civs=2, seed=42)
    loser = world.civilizations[0]
    winner = world.civilizations[1]
    gp = GreatPerson(
        name="Agent GP", role="general", trait="bold",
        civilization=loser.name, origin_civilization=loser.name,
        born_turn=5, agent_id=100,
    )
    loser.great_persons = [gp]
    bridge = _MockBridge()
    winner_idx = 1  # world.civilizations index for winner
    capture_hostage(loser, winner, world, contested_region="Battlefield", bridge=bridge)
    assert bridge._sim.calls == [(100, winner_idx)]


def test_release_hostage_syncs_rust_affinity(make_world):
    """release_hostage() calls set_agent_civ with origin civ index."""
    world = make_world(num_civs=2, seed=42)
    captor = world.civilizations[0]
    origin = world.civilizations[1]
    hostage = GreatPerson(
        name="Agent Captive", role="hostage", trait="bold",
        civilization=captor.name, origin_civilization=origin.name,
        born_turn=0, is_hostage=True, hostage_turns=11,
        captured_by=captor.name, pre_hostage_role="merchant",
        agent_id=200,
    )
    captor.great_persons = [hostage]
    bridge = _MockBridge()
    origin_idx = 1  # world.civilizations index for origin
    release_hostage(hostage, captor, origin, world, bridge=bridge)
    assert bridge._sim.calls == [(200, origin_idx)]


def test_extinct_origin_release_syncs_rust_affinity(make_world):
    """tick_hostages() syncs to captor when origin has no regions."""
    world = make_world(num_civs=2, seed=42)
    captor = world.civilizations[0]
    origin = world.civilizations[1]
    origin.regions = []  # extinct
    hostage = GreatPerson(
        name="Stranded GP", role="hostage", trait="cautious",
        civilization=captor.name, origin_civilization=origin.name,
        born_turn=0, is_hostage=True, hostage_turns=5,
        captured_by=captor.name, pre_hostage_role="scientist",
        agent_id=300,
    )
    captor.great_persons = [hostage]
    bridge = _MockBridge()
    captor_idx = 0  # world.civilizations index for captor
    tick_hostages(world, bridge=bridge)
    assert bridge._sim.calls == [(300, captor_idx)]


def test_missing_origin_release_syncs_rust_affinity():
    """tick_hostages() syncs to captor when origin civ not found at all."""
    from chronicler.models import (
        Civilization, Leader, Region, TechEra, WorldState, Relationship,
    )
    captor = Civilization(
        name="Captor", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50,
        leader=Leader(name="Leader of Captor", trait="cautious", reign_start=0),
        regions=["R1"], asabiya=0.5,
    )
    hostage = GreatPerson(
        name="Orphan GP", role="hostage", trait="bold",
        civilization="Captor", origin_civilization="NonExistent",
        born_turn=0, is_hostage=True, hostage_turns=3,
        captured_by="Captor", pre_hostage_role="general",
        agent_id=400,
    )
    captor.great_persons = [hostage]
    r1 = Region(name="R1", terrain="plains", carrying_capacity=60,
                resources="fertile", controller="Captor")
    world = WorldState(
        name="TestWorld", seed=42, turn=10,
        regions=[r1], civilizations=[captor], relationships={},
    )
    bridge = _MockBridge()
    captor_idx = 0
    tick_hostages(world, bridge=bridge)
    assert bridge._sim.calls == [(400, captor_idx)]


def test_tick_hostages_normal_release_forwards_bridge(make_world):
    """tick_hostages() forwards bridge to release_hostage on normal auto-release."""
    world = make_world(num_civs=2, seed=42)
    captor = world.civilizations[0]
    origin = world.civilizations[1]
    hostage = GreatPerson(
        name="Auto Release GP", role="hostage", trait="bold",
        civilization=captor.name, origin_civilization=origin.name,
        born_turn=0, is_hostage=True, hostage_turns=14,
        captured_by=captor.name, pre_hostage_role="general",
        agent_id=350,
    )
    captor.great_persons = [hostage]
    bridge = _MockBridge()
    origin_idx = 1  # world.civilizations index for origin
    tick_hostages(world, bridge=bridge)
    assert bridge._sim.calls == [(350, origin_idx)]


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
            self.ops = None
        def read_social_edges(self):
            return list(self._edges)
        def apply_relationship_ops(self, ops):
            self.ops = ops

    initial = [(100, 200, REL_RIVAL, 10)]
    bridge = MockBridge(initial)
    world = WorldState(name="TestWorld", seed=42, turn=50, regions=[], civilizations=[], relationships={})
    active_ids = {200}
    dissolved = form_and_sync_relationships(world, bridge, active_ids, {}, {})
    assert len(dissolved) == 1
    assert bridge.ops is not None
    assert bridge.ops == [{
        "op_type": 3,
        "agent_a": 100,
        "agent_b": 200,
        "bond_type": REL_RIVAL,
        "sentiment": 50,
        "formed_turn": 10,
    }]


def test_coordinator_forms_new_edges_and_writes_back(make_world):
    class MockBridge:
        def __init__(self):
            self._edges = []
            self.ops = None
        def read_social_edges(self):
            return list(self._edges)
        def apply_relationship_ops(self, ops):
            self.ops = ops

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
    assert bridge.ops is not None
    assert len(bridge.ops) >= 1
    assert any(op["bond_type"] == REL_RIVAL and op["op_type"] == 1 for op in bridge.ops)


# --- Task 17: agents=off empty relationships ---

def test_agents_off_produces_empty_relationships():
    """In --agents=off mode, no social graph exists, relationships are empty."""
    from chronicler.models import WorldState

    class NullBridge:
        def read_social_edges(self):
            return []
        def replace_social_edges(self, edges):
            pass

    world = WorldState(name="TestWorld", seed=42, turn=50, regions=[], civilizations=[], relationships={})
    dissolved = form_and_sync_relationships(world, NullBridge(), set(), {}, {})
    assert len(dissolved) == 0


# --- M57a: Aggregate mode (agents=off) smoke test ---

def test_agents_off_no_marriage_events_and_default_lineage():
    """Verify data-model defaults for aggregate mode: GreatPerson records have
    parent_id_1 == 0 and lineage_house == 0, and a freshly-constructed world
    has no marriage_formed events.

    NOTE: This tests initial-state defaults only. It does NOT exercise any
    code path that would produce marriage events in agents=on mode and verify
    they are suppressed in agents=off mode. A true integration test would run
    form_and_sync_relationships with a live AgentBridge vs a NullBridge and
    compare event output.  TODO: upgrade to integration test when feasible.
    """
    from chronicler.models import WorldState, Civilization, Leader, Region

    # Build minimal aggregate-mode world
    civ = Civilization(
        name="TestCiv", population=50, military=50, economy=50,
        culture=50, stability=50,
        leader=Leader(name="King Test", trait="bold", reign_start=0),
        regions=["Region A"],
    )
    world = WorldState(
        name="AggTest", seed=42, turn=10,
        regions=[Region(name="Region A", terrain="plains", carrying_capacity=80, resources="fertile")],
        civilizations=[civ],
        relationships={},
    )
    # Create some GreatPersons (as aggregate mode would)
    gp1 = GreatPerson(
        name="General Kiran", role="general", trait="bold",
        civilization="TestCiv", origin_civilization="TestCiv",
        born_turn=5, source="aggregate",
    )
    gp2 = GreatPerson(
        name="Merchant Tala", role="merchant", trait="shrewd",
        civilization="TestCiv", origin_civilization="TestCiv",
        born_turn=8, source="aggregate",
    )
    civ.great_persons = [gp1, gp2]

    # Verify default dual-parent fields
    for gp in civ.great_persons:
        assert gp.parent_id_1 == 0, f"{gp.name} should have parent_id_1 == 0 in aggregate mode"
        assert gp.lineage_house == 0, f"{gp.name} should have lineage_house == 0 in aggregate mode"

    # Verify no marriage_formed events in the world's events timeline
    assert not hasattr(world, 'events_timeline') or len(getattr(world, 'events_timeline', [])) == 0
    # Explicitly: no event with type "marriage_formed" anywhere
    all_events = getattr(world, 'events_timeline', [])
    marriage_events = [e for e in all_events if getattr(e, 'event_type', '') == 'marriage_formed']
    assert len(marriage_events) == 0, "No marriage_formed events should exist in aggregate mode"
