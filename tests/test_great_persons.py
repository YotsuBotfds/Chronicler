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


# ---------------------------------------------------------------------------
# Task 2: Modifier registry tests
# ---------------------------------------------------------------------------

from chronicler.great_persons import get_modifiers


def test_get_modifiers_general(make_civ):
    gp = GreatPerson(name="Khotun", role="general", trait="aggressive", civilization="Mongol", origin_civilization="Mongol", born_turn=0)
    civ = make_civ("Mongol")
    civ.great_persons = [gp]
    mods = get_modifiers(civ, "military")
    assert len(mods) == 1
    assert mods[0]["domain"] == "military"
    assert mods[0]["value"] == 10


def test_get_modifiers_excludes_hostages(make_civ):
    gp = GreatPerson(name="Khotun", role="general", trait="aggressive", civilization="Mongol", origin_civilization="Mongol", born_turn=0, is_hostage=True)
    civ = make_civ("Mongol")
    civ.great_persons = [gp]
    mods = get_modifiers(civ, "military")
    assert len(mods) == 0


def test_get_modifiers_merchant(make_civ):
    gp = GreatPerson(name="Lysander", role="merchant", trait="shrewd", civilization="Greek", origin_civilization="Greek", born_turn=0)
    civ = make_civ("Greek")
    civ.great_persons = [gp]
    mods = get_modifiers(civ, "trade")
    assert len(mods) == 1
    assert mods[0]["value"] == 3
    assert mods[0]["per"] == "route"


def test_get_modifiers_scientist(make_civ):
    gp = GreatPerson(name="Hypatia", role="scientist", trait="visionary", civilization="Egypt", origin_civilization="Egypt", born_turn=0)
    civ = make_civ("Egypt")
    civ.great_persons = [gp]
    mods = get_modifiers(civ, "tech")
    assert len(mods) == 1
    assert mods[0]["value"] == -0.30
    assert mods[0]["mode"] == "multiplier"


def test_get_modifiers_prophet(make_civ):
    gp = GreatPerson(name="Zara", role="prophet", trait="zealous", civilization="Persia", origin_civilization="Persia", born_turn=0, movement_id="1")
    civ = make_civ("Persia")
    civ.great_persons = [gp]
    mods = get_modifiers(civ, "culture")
    assert len(mods) == 1
    assert mods[0]["mode"] == "behavioral"


def test_get_modifiers_wrong_domain_returns_empty(make_civ):
    gp = GreatPerson(name="Khotun", role="general", trait="aggressive", civilization="Mongol", origin_civilization="Mongol", born_turn=0)
    civ = make_civ("Mongol")
    civ.great_persons = [gp]
    mods = get_modifiers(civ, "trade")
    assert len(mods) == 0


def test_get_modifiers_excludes_inactive(make_civ):
    gp = GreatPerson(name="Khotun", role="general", trait="aggressive", civilization="Mongol", origin_civilization="Mongol", born_turn=0, active=False, fate="retired")
    civ = make_civ("Mongol")
    civ.great_persons = [gp]
    mods = get_modifiers(civ, "military")
    assert len(mods) == 0


def test_get_modifiers_excludes_exile_role(make_civ):
    gp = GreatPerson(name="Deposed King", role="exile", trait="ambitious", civilization="Host", origin_civilization="Origin", born_turn=0)
    civ = make_civ("Host")
    civ.great_persons = [gp]
    mods = get_modifiers(civ, "military")
    assert len(mods) == 0
    mods = get_modifiers(civ, "trade")
    assert len(mods) == 0


# ---------------------------------------------------------------------------
# Task 3: Achievement-triggered generation tests
# ---------------------------------------------------------------------------

from chronicler.great_persons import check_great_person_generation


def test_general_spawns_after_3_war_wins_in_window(make_world):
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    civ.war_win_turns = [5, 8, 12]
    spawned = check_great_person_generation(civ, world)
    assert len(spawned) == 1
    assert spawned[0].role == "general"


def test_general_not_spawned_if_wins_outside_window(make_world):
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    world.turn = 30
    civ.war_win_turns = [1, 5, 10]
    spawned = check_great_person_generation(civ, world)
    assert len(spawned) == 0


def test_cooldown_blocks_spawn(make_world):
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    civ.war_win_turns = [5, 8, 12]
    world.great_person_cooldowns = {civ.name: {"general": 5}}
    world.turn = 15
    spawned = check_great_person_generation(civ, world)
    assert len(spawned) == 0


def test_scientist_spawns_on_era_advance(make_world):
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    civ.event_counts["tech_advanced"] = 1
    spawned = check_great_person_generation(civ, world)
    assert any(s.role == "scientist" for s in spawned)


def test_scientist_spawns_on_high_economy(make_world):
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    civ.economy = 85
    civ.event_counts["high_economy_turns"] = 15
    spawned = check_great_person_generation(civ, world)
    assert any(s.role == "scientist" for s in spawned)


def test_catch_up_discount(make_world):
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    civ.great_persons = []
    civ.war_win_turns = [5, 8]  # only 2 wins (normally need 3, catch-up needs 2)
    spawned = check_great_person_generation(civ, world)
    assert len(spawned) == 1
    assert spawned[0].role == "general"


def test_50_cap_forces_retirement(make_world):
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    for i in range(5):
        civ.great_persons.append(GreatPerson(name=f"Person{i}", role="general", trait="bold", civilization=civ.name, origin_civilization=civ.name, born_turn=i))
    other = world.civilizations[1]
    for i in range(45):
        other.great_persons.append(GreatPerson(name=f"Other{i}", role="merchant", trait="shrewd", civilization=other.name, origin_civilization=other.name, born_turn=i))
    civ.war_win_turns = [5, 8, 12]
    spawned = check_great_person_generation(civ, world)
    assert len(spawned) == 1
    assert len(world.retired_persons) >= 1
    assert world.retired_persons[-1].name == "Person0"


# ---------------------------------------------------------------------------
# Task 4: Lifecycle management tests
# ---------------------------------------------------------------------------

from chronicler.great_persons import check_lifespan_expiry, kill_great_person, _compute_lifespan


def test_retirement_on_lifespan_expiry(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    gp = GreatPerson(name="OldGeneral", role="general", trait="bold", civilization=civ.name, origin_civilization=civ.name, born_turn=0)
    civ.great_persons = [gp]
    world.turn = 35  # guaranteed past max lifespan of 30
    retired = check_lifespan_expiry(civ, world)
    assert len(retired) == 1
    assert retired[0].fate == "retired"
    assert retired[0].active is False
    assert retired[0].alive is True
    assert retired[0].death_turn is None
    assert gp not in civ.great_persons
    assert gp in world.retired_persons


def test_death_is_separate_from_retirement(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    gp = GreatPerson(name="FallenGeneral", role="general", trait="bold", civilization=civ.name, origin_civilization=civ.name, born_turn=10)
    civ.great_persons = [gp]
    world.turn = 15
    killed = kill_great_person(gp, civ, world, context="war")
    assert killed.fate == "dead"
    assert killed.death_turn == 15
    assert killed not in civ.great_persons
    assert killed in world.retired_persons


def test_lifespan_deterministic():
    ls1 = _compute_lifespan(seed=42, born_turn=10, name="TestPerson")
    ls2 = _compute_lifespan(seed=42, born_turn=10, name="TestPerson")
    assert ls1 == ls2
    assert 20 <= ls1 <= 30


# ---------------------------------------------------------------------------
# Task 5: Phase 10 great person hooks
# ---------------------------------------------------------------------------


def test_phase10_generates_and_retires_great_persons(make_world):
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    civ.war_win_turns = [1, 3, 5]
    world.turn = 10
    from chronicler.simulation import phase_consequences
    phase_consequences(world)
    generals = [gp for gp in civ.great_persons if gp.role == "general"]
    assert len(generals) >= 1


# ---------------------------------------------------------------------------
# Task 6: CivSnapshot includes great person fields
# ---------------------------------------------------------------------------


def test_civ_snapshot_includes_great_persons(make_world):
    """Verify CivSnapshot fields are populated when building snapshots."""
    from chronicler.models import CivSnapshot, TechEra
    snap = CivSnapshot(
        population=50, military=30, economy=40, culture=30, stability=50,
        treasury=50, asabiya=0.5, tech_era=TechEra.IRON, trait="cautious",
        regions=["r1"], leader_name="Test",
        alive=True,
        great_persons=[{"name": "Gen", "role": "general", "trait": "bold"}],
        traditions=["martial"],
        folk_heroes=[{"name": "Hero", "role": "general"}],
        active_crisis=True,
    )
    assert len(snap.great_persons) == 1
    assert snap.traditions == ["martial"]
    assert snap.active_crisis is True


# ---------------------------------------------------------------------------
# Task 7: M17a end-to-end integration test
# ---------------------------------------------------------------------------


def test_m17a_integration_5_turn_simulation(make_world):
    """Run 5 turns and verify great person system doesn't crash."""
    from chronicler.simulation import run_turn
    world = make_world(num_civs=3, seed=42)
    civ = world.civilizations[0]
    civ.war_win_turns = [0, 1, 2]

    action_selector = lambda c, w: __import__("chronicler.models", fromlist=["ActionType"]).ActionType.DEVELOP
    narrator = lambda w, events: ""

    for _turn in range(5):
        run_turn(world, action_selector=action_selector, narrator=narrator, seed=world.seed)

    for c in world.civilizations:
        for gp in c.great_persons:
            assert gp.active is True
            assert gp.civilization == c.name
    for gp in world.retired_persons:
        assert gp.active is False
