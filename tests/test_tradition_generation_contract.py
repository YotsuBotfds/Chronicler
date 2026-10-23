"""M17 tradition cooldown contract for aggregate great-person generation."""
import pytest

from chronicler.great_persons import _is_on_cooldown, check_great_person_generation
from chronicler.models import WorldState
from chronicler.traditions import check_tradition_acquisition


def _qualify(civ, role, turn):
    """Supply real achievement state without changing generation thresholds."""
    if role == "general":
        civ.war_win_turns = [turn - 2, turn - 1, turn]
    elif role == "merchant":
        civ.event_counts["high_trade_route_turns"] = 10
    elif role == "scientist":
        civ.event_counts["tech_advanced"] = 1
    elif role == "prophet":
        civ.event_counts["prophet_trigger"] = 1


@pytest.mark.parametrize("last_spawn", [0, 5])
@pytest.mark.parametrize("offset", [-1, 0, 1])
@pytest.mark.parametrize("traditions,role,duration", [
    (["martial"], "general", 18),
    (["diplomatic"], "merchant", 18),
    ([], "general", 20),
    ([], "merchant", 20),
    (["diplomatic"], "general", 20),
    (["martial"], "merchant", 20),
    (["food_stockpiling", "resilience"], "general", 20),
    (["food_stockpiling", "resilience"], "merchant", 20),
    (["martial", "diplomatic"], "scientist", 20),
    (["martial", "diplomatic"], "prophet", 25),
])
def test_cooldown_boundaries(make_world, traditions, role, duration, offset, last_spawn):
    world = make_world(num_civs=1)
    civ = world.civilizations[0]
    civ.traditions = traditions
    world.great_person_cooldowns = {civ.name: {role: last_spawn}}
    world.turn = last_spawn + duration + offset

    assert _is_on_cooldown(civ.name, role, world) is (offset < 0)
    assert world.great_person_cooldowns == {civ.name: {role: last_spawn}}


@pytest.mark.parametrize("offset", [-1, 0, 1])
@pytest.mark.parametrize("traditions,role,duration", [
    (["martial", "diplomatic"], "general", 18),
    (["martial", "diplomatic"], "merchant", 18),
    ([], "general", 20),
    ([], "merchant", 20),
    (["martial", "diplomatic"], "scientist", 20),
    (["martial", "diplomatic"], "prophet", 25),
])
def test_actual_generation_at_boundary(make_world, traditions, role, duration, offset):
    world = make_world(num_civs=1)
    civ = world.civilizations[0]
    civ.traditions = traditions
    world.turn = duration + offset
    world.great_person_cooldowns = {civ.name: {role: 0}}
    _qualify(civ, role, world.turn)

    spawned = check_great_person_generation(civ, world)
    assert [gp.role for gp in spawned] == ([role] if offset >= 0 else [])
    assert world.great_person_cooldowns[civ.name][role] == (world.turn if offset >= 0 else 0)


def test_original_turn18_reproduction_with_both_traditions(make_world):
    world = make_world(num_civs=1)
    civ = world.civilizations[0]
    civ.traditions = ["martial", "diplomatic"]
    world.turn = 18
    world.great_person_cooldowns = {civ.name: {"general": 0, "merchant": 0}}
    for role in ["general", "merchant"]:
        _qualify(civ, role, world.turn)
        assert not _is_on_cooldown(civ.name, role, world)
    assert [gp.role for gp in check_great_person_generation(civ, world)] == ["general", "merchant"]
    assert world.great_person_cooldowns[civ.name] == {"general": 18, "merchant": 18}


@pytest.mark.parametrize("tradition,role", [("martial", "general"), ("diplomatic", "merchant")])
def test_consecutive_achievements_reset_only_after_spawn(make_world, tradition, role):
    world = make_world(num_civs=1)
    civ = world.civilizations[0]
    civ.traditions = [tradition]
    last_spawn = None

    for turn in [5, 5, 6, 22, 23, 23, 24, 40, 41]:
        world.turn = turn
        _qualify(civ, role, turn)
        expected_spawn = last_spawn is None or turn - last_spawn >= 18
        spawned = check_great_person_generation(civ, world)
        assert [gp.role for gp in spawned] == ([role] if expected_spawn else [])
        if expected_spawn:
            last_spawn = turn
        assert world.great_person_cooldowns == {civ.name: {role: last_spawn}}

    assert [gp.born_turn for gp in civ.great_persons] == [5, 23, 41]


def test_civilizations_and_roles_have_independent_cooldowns(make_world):
    world = make_world(num_civs=3)
    martial, diplomatic, ordinary = world.civilizations
    martial.traditions = ["martial"]
    diplomatic.traditions = ["diplomatic"]
    for civ in world.civilizations:
        world.great_person_cooldowns[civ.name] = {"general": 0, "merchant": 0}
        for role in ["general", "merchant"]:
            _qualify(civ, role, 18)

    world.turn = 18
    assert [gp.role for gp in check_great_person_generation(martial, world)] == ["general"]
    assert [gp.role for gp in check_great_person_generation(diplomatic, world)] == ["merchant"]
    assert check_great_person_generation(ordinary, world) == []
    assert world.great_person_cooldowns == {
        martial.name: {"general": 18, "merchant": 0},
        diplomatic.name: {"general": 0, "merchant": 18},
        ordinary.name: {"general": 0, "merchant": 0},
    }


@pytest.mark.parametrize("tradition,role", [("martial", "general"), ("diplomatic", "merchant")])
def test_expiry_still_requires_an_achievement(make_world, tradition, role):
    world = make_world(num_civs=1)
    civ = world.civilizations[0]
    civ.traditions = [tradition]
    world.great_person_cooldowns = {civ.name: {role: 0}}
    world.turn = 18

    assert check_great_person_generation(civ, world) == []
    assert world.great_person_cooldowns == {civ.name: {role: 0}}
    _qualify(civ, role, world.turn)
    assert [gp.role for gp in check_great_person_generation(civ, world)] == [role]
    assert world.great_person_cooldowns == {civ.name: {role: 18}}


@pytest.mark.parametrize("tradition,role,key,value", [
    ("martial", "general", "wars_won", 5),
    ("diplomatic", "merchant", "federation_turns", 30),
])
def test_new_tradition_changes_duration_without_rewriting_spawn_turn(make_world, tradition, role, key, value):
    world = make_world(num_civs=1)
    civ = world.civilizations[0]
    world.turn = 18
    world.great_person_cooldowns = {civ.name: {role: 0}}
    assert _is_on_cooldown(civ.name, role, world)

    civ.event_counts[key] = value
    assert check_tradition_acquisition(world) == [(civ.name, tradition)]
    assert not _is_on_cooldown(civ.name, role, world)
    assert world.great_person_cooldowns == {civ.name: {role: 0}}


@pytest.mark.parametrize("tradition,role", [("martial", "general"), ("diplomatic", "merchant")])
def test_save_load_preserves_spawn_clock_and_generation(make_world, tmp_path, tradition, role):
    world = make_world(num_civs=1)
    civ = world.civilizations[0]
    civ.traditions = [tradition]
    world.turn = 17
    world.great_person_cooldowns = {civ.name: {role: 0}}
    _qualify(civ, role, world.turn)
    path = tmp_path / "state.json"
    world.save(path)
    loaded = WorldState.load(path)
    loaded_civ = loaded.civilizations[0]

    assert loaded.great_person_cooldowns == {civ.name: {role: 0}}
    assert loaded_civ.traditions == [tradition]
    assert check_great_person_generation(loaded_civ, loaded) == []
    for candidate, owner in [(world, civ), (loaded, loaded_civ)]:
        candidate.turn = 18
        assert [gp.role for gp in check_great_person_generation(owner, candidate)] == [role]
    assert loaded.model_dump() == world.model_dump()


def test_missing_and_cleared_cooldowns_do_not_leak_between_worlds(make_world):
    world = make_world(num_civs=1)
    civ = world.civilizations[0]
    civ.traditions = ["martial", "diplomatic"]
    world.great_person_cooldowns = {civ.name: {"general": 0}}
    assert _is_on_cooldown(civ.name, "general", world)
    assert not _is_on_cooldown(civ.name, "merchant", world)
    assert not _is_on_cooldown("unknown", "general", world)

    fresh_world = make_world(num_civs=1)
    assert fresh_world.great_person_cooldowns == {}
    assert not _is_on_cooldown(civ.name, "general", fresh_world)
    world.great_person_cooldowns.clear()
    assert not _is_on_cooldown(civ.name, "general", world)


@pytest.mark.parametrize("tradition,role,key,value", [
    ("martial", "general", "wars_won", 5),
    ("diplomatic", "merchant", "federation_turns", 30),
])
def test_phase10_acquisition_applies_to_same_turn_generation(make_world, tradition, role, key, value):
    from chronicler.simulation import phase_consequences

    world = make_world(num_civs=5)
    world.agent_mode = "off"
    world.turn = 18
    civ = world.civilizations[0]
    civ.event_counts[key] = value
    world.great_person_cooldowns = {civ.name: {role: 0}}
    _qualify(civ, role, world.turn)
    if role == "merchant":
        for relationship in world.relationships[civ.name].values():
            relationship.trade_volume = 1

    events = phase_consequences(world)
    assert tradition in civ.traditions
    assert [gp.role for gp in civ.great_persons] == [role]
    assert world.great_person_cooldowns[civ.name][role] == 18
    assert any(e.event_type == "tradition_acquired" for e in events)
    assert any(e.event_type == "great_person_born" for e in events)
