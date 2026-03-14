"""Tests for M17b succession crisis system and personal grudges."""
from chronicler.succession import (
    compute_crisis_probability,
    trigger_crisis,
    tick_crisis,
    resolve_crisis,
    is_in_crisis,
    add_grudge,
    decay_grudges,
    inherit_grudges,
)
from chronicler.models import Civilization, Leader, VassalRelation, WorldState


# ---------------------------------------------------------------------------
# Task 8: Succession crisis formula
# ---------------------------------------------------------------------------

def test_crisis_probability_floor(make_world, make_civ):
    civ = make_civ("Stable", stability=100, asabiya=0.9, regions=["r1", "r2", "r3"],
                    traditions=["martial", "resilience"],
                    leader=Leader(name="StableKing", trait="cautious", reign_start=0, succession_type="heir"))
    world = make_world(num_civs=1, seed=42)
    world.civilizations = [civ]
    world.turn = 30
    prob = compute_crisis_probability(civ, world)
    assert prob >= 0.05


def test_crisis_probability_cap(make_world, make_civ):
    civ = make_civ("Unstable", stability=5, asabiya=0.1,
                    regions=["r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8"],
                    leader=Leader(name="WeakKing", trait="ambitious", reign_start=48, succession_type="usurper"))
    world = make_world(num_civs=1, seed=42)
    world.civilizations = [civ]
    world.turn = 50
    world.vassal_relations = [VassalRelation(overlord=civ.name, vassal="Vassal1", tribute_rate=0.15, turns_active=5)]
    prob = compute_crisis_probability(civ, world)
    assert prob <= 0.40


def test_crisis_not_triggered_with_few_regions(make_world, make_civ):
    civ = make_civ("Small", stability=10, regions=["r1", "r2"])
    world = make_world(num_civs=1, seed=42)
    world.civilizations = [civ]
    prob = compute_crisis_probability(civ, world)
    assert prob == 0.0


def test_vassal_escalation(make_world, make_civ):
    civ = make_civ("Overlord", stability=50, regions=["r1", "r2", "r3", "r4"],
                    leader=Leader(name="King", trait="bold", reign_start=0, succession_type="general"))
    world = make_world(num_civs=1, seed=42)
    world.civilizations = [civ]
    world.turn = 10
    prob_no_vassal = compute_crisis_probability(civ, world)
    world.vassal_relations = [VassalRelation(overlord=civ.name, vassal="V1", tribute_rate=0.15, turns_active=5)]
    prob_with_vassal = compute_crisis_probability(civ, world)
    assert prob_with_vassal > prob_no_vassal


def test_tradition_suppression(make_world, make_civ):
    civ = make_civ("Traditional", stability=40, regions=["r1", "r2", "r3"],
                    leader=Leader(name="King", trait="bold", reign_start=0, succession_type="heir"))
    world = make_world(num_civs=1, seed=42)
    world.civilizations = [civ]
    world.turn = 10
    prob_no_tradition = compute_crisis_probability(civ, world)
    civ.traditions = ["martial"]
    prob_with_tradition = compute_crisis_probability(civ, world)
    assert prob_with_tradition < prob_no_tradition


# ---------------------------------------------------------------------------
# Task 9: Crisis state machine
# ---------------------------------------------------------------------------

def test_trigger_crisis_sets_state(make_world):
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    civ.regions = ["r1", "r2", "r3"]
    trigger_crisis(civ, world)
    assert civ.succession_crisis_turns_remaining > 0
    assert civ.succession_crisis_turns_remaining <= 5


def test_tick_crisis_decrements(make_world):
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    civ.succession_crisis_turns_remaining = 3
    tick_crisis(civ, world)
    assert civ.succession_crisis_turns_remaining == 2


def test_resolve_crisis_creates_leader(make_world):
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    civ.succession_crisis_turns_remaining = 1
    civ.succession_candidates = [{"backer_civ": "Other", "type": "military"}]
    old_leader_name = civ.leader.name
    events = resolve_crisis(civ, world)
    assert civ.succession_crisis_turns_remaining == 0
    assert civ.leader.name != old_leader_name
    assert len(events) >= 1


def test_crisis_check(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.succession_crisis_turns_remaining = 3
    assert is_in_crisis(civ) is True


# ---------------------------------------------------------------------------
# Task 10: Personal grudges
# ---------------------------------------------------------------------------

def test_add_grudge_on_war_loss():
    leader = Leader(name="Loser", trait="bold", reign_start=0)
    add_grudge(leader, rival_name="Winner", rival_civ="EnemyCiv", turn=10)
    assert len(leader.grudges) == 1
    assert leader.grudges[0]["intensity"] == 1.0
    assert leader.grudges[0]["rival_civ"] == "EnemyCiv"


def test_grudge_decay():
    leader = Leader(name="Loser", trait="bold", reign_start=0)
    leader.grudges = [{"rival_name": "Winner", "rival_civ": "Enemy", "intensity": 1.0, "origin_turn": 0}]
    decay_grudges(leader, current_turn=5, rival_alive=True)
    assert leader.grudges[0]["intensity"] == 0.9


def test_grudge_accelerated_decay_after_target_death():
    leader = Leader(name="Loser", trait="bold", reign_start=0)
    leader.grudges = [{"rival_name": "Winner", "rival_civ": "Enemy", "intensity": 1.0, "origin_turn": 0}]
    decay_grudges(leader, current_turn=5, rival_alive=False)
    assert leader.grudges[0]["intensity"] == 0.8


def test_grudge_inheritance_at_50_percent():
    old_leader = Leader(name="Old", trait="bold", reign_start=0)
    old_leader.grudges = [{"rival_name": "Enemy", "rival_civ": "Foe", "intensity": 1.0, "origin_turn": 0}]
    new_leader = Leader(name="New", trait="cautious", reign_start=20)
    inherit_grudges(old_leader, new_leader)
    assert len(new_leader.grudges) == 1
    assert new_leader.grudges[0]["intensity"] == 0.5


def test_grudge_removed_when_intensity_zero():
    leader = Leader(name="Loser", trait="bold", reign_start=0)
    leader.grudges = [{"rival_name": "Winner", "rival_civ": "Enemy", "intensity": 0.05, "origin_turn": 0}]
    decay_grudges(leader, current_turn=5, rival_alive=True)
    assert len(leader.grudges) == 0
