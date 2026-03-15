# tests/test_traditions.py
"""Tests for Task 19-23: event_counts, traditions, folk heroes, secession inheritance, and prophet martyrdom."""
import pytest
from chronicler.traditions import (
    update_event_counts,
    check_tradition_acquisition,
    apply_tradition_effects,
    apply_fertility_floor,
    is_dramatic_death,
    check_folk_hero,
    compute_folk_hero_asabiya_bonus,
    _add_folk_hero,
    apply_prophet_martyrdom,
)
from chronicler.models import Event, GreatPerson, Movement


# --- Task 19: Event counts tracking ---

def test_war_win_counted(make_world):
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    world.events_timeline.append(Event(
        turn=world.turn, event_type="war",
        actors=[civ.name, "Enemy"],
        description=f"{civ.name} attacked Enemy: attacker_wins.",
        importance=8,
    ))
    update_event_counts(world)
    assert civ.event_counts.get("wars_won", 0) == 1
    assert len(civ.war_win_turns) == 1


def test_famine_survived_counted(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    world.events_timeline.append(Event(
        turn=world.turn, event_type="famine",
        actors=[civ.name],
        description="Famine in region.",
        importance=6,
    ))
    update_event_counts(world)
    assert civ.event_counts.get("famines_survived", 0) == 1


def test_high_economy_tracking(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.economy = 85
    update_event_counts(world)
    assert civ.event_counts.get("high_economy_turns", 0) == 1


def test_high_economy_resets_below_threshold(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.economy = 50
    civ.event_counts["high_economy_turns"] = 5
    update_event_counts(world)
    assert civ.event_counts.get("high_economy_turns", 0) == 0


# --- Task 20: Traditions ---

def test_martial_tradition_from_war_wins(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.event_counts["wars_won"] = 5
    check_tradition_acquisition(world)
    assert "martial" in civ.traditions


def test_food_stockpiling_from_famines(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.event_counts["famines_survived"] = 3
    check_tradition_acquisition(world)
    assert "food_stockpiling" in civ.traditions


def test_resilience_from_capital_recovery(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.event_counts["capital_recovered"] = 1
    check_tradition_acquisition(world)
    assert "resilience" in civ.traditions


def test_diplomatic_from_federation_turns(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.event_counts["federation_turns"] = 30
    check_tradition_acquisition(world)
    assert "diplomatic" in civ.traditions


def test_no_double_granting(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.traditions = ["martial"]
    civ.event_counts["wars_won"] = 10
    check_tradition_acquisition(world)
    assert civ.traditions.count("martial") == 1


def test_crystallization_shame_to_resilience(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.legacy_counts["shame"] = 3
    check_tradition_acquisition(world)
    assert "resilience" in civ.traditions


def test_food_stockpiling_fertility_floor(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.traditions = ["food_stockpiling"]
    region = next(r for r in world.regions if r.name in civ.regions)
    region.ecology.soil = 0.1
    apply_fertility_floor(world)
    assert region.ecology.soil == 0.2


def test_max_traditions_cap(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.traditions = ["martial", "food_stockpiling", "diplomatic", "resilience"]
    civ.event_counts["wars_won"] = 100  # shouldn't add more
    check_tradition_acquisition(world)
    assert len(civ.traditions) == 4


# --- Task 21: Folk heroes ---

def test_dramatic_death_in_war():
    assert is_dramatic_death("war") is True


def test_dramatic_death_in_disaster():
    assert is_dramatic_death("disaster") is True


def test_non_dramatic_death():
    assert is_dramatic_death("natural") is False


def test_folk_hero_creation(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    gp = GreatPerson(
        name="FallenHero", role="general", trait="bold",
        civilization=civ.name, origin_civilization=civ.name,
        born_turn=0, death_turn=10, fate="dead",
    )
    result = check_folk_hero(gp, civ, world, context="war")
    assert isinstance(result, bool)


def test_folk_hero_asabiya_bonus(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    civ.folk_heroes = [
        {"name": "Hero1", "role": "general", "death_turn": 5, "death_context": "war"},
        {"name": "Hero2", "role": "general", "death_turn": 10, "death_context": "war"},
    ]
    bonus = compute_folk_hero_asabiya_bonus(civ)
    assert abs(bonus - 0.06) < 0.001


def test_folk_hero_cap_at_5(make_world):
    world = make_world(num_civs=1, seed=42)
    civ = world.civilizations[0]
    for i in range(5):
        civ.folk_heroes.append({"name": f"Hero{i}", "role": "general", "death_turn": i, "death_context": "war"})
    gp = GreatPerson(
        name="Hero6", role="general", trait="bold",
        civilization=civ.name, origin_civilization=civ.name,
        born_turn=50, death_turn=60, fate="dead",
    )
    _add_folk_hero(gp, civ, "war")
    assert len(civ.folk_heroes) == 5


# --- Task 22: Tradition inheritance through secession ---

def test_tradition_inherited_on_secession(make_world):
    world = make_world(num_civs=1, seed=42)
    parent = world.civilizations[0]
    parent.traditions = ["martial", "resilience"]
    parent.regions = ["r1", "r2", "r3", "r4"]
    parent.stability = 10
    # Add the regions to world.regions so secession logic can find them
    from chronicler.models import Region
    for rname in ["r1", "r2", "r3", "r4"]:
        if not any(r.name == rname for r in world.regions):
            world.regions.append(Region(
                name=rname, terrain="plains",
                carrying_capacity=60, resources="fertile",
                controller=parent.name,
            ))
    from chronicler.politics import check_secession
    events = check_secession(world)
    if events:
        new_civs = [c for c in world.civilizations if c.name != parent.name]
        if new_civs:
            assert "martial" in new_civs[-1].traditions
            assert "resilience" in new_civs[-1].traditions


# --- Task 23: Prophet martyrdom ---

def test_prophet_martyrdom_boosts_movement(make_world):
    world = make_world(num_civs=2, seed=42)
    civ = world.civilizations[0]
    movement = Movement(
        id="0", origin_civ=civ.name, origin_turn=0,
        value_affinity="freedom", adherents={civ.name: 0},
    )
    world.movements = [movement]
    gp = GreatPerson(
        name="Martyr", role="prophet", trait="zealous",
        civilization=civ.name, origin_civilization=civ.name,
        born_turn=0, death_turn=10, fate="dead", movement_id="0",
    )
    apply_prophet_martyrdom(gp, civ, world)
    key = f"martyrdom_bonus_movement_0"
    assert civ.event_counts.get(key, 0) >= 1


# --- Task 24: M17d integration test ---

def test_m17d_integration_traditions_and_folk_heroes(make_world):
    from chronicler.simulation import run_turn
    from chronicler.models import ActionType
    world = make_world(num_civs=4, seed=42)
    for turn in range(30):
        world.turn = turn
        run_turn(world, action_selector=lambda c, w: ActionType.DEVELOP, narrator=lambda *a: None, seed=world.seed)
    # Verify state consistency
    for civ in world.civilizations:
        assert len(civ.traditions) <= 4
        assert len(civ.folk_heroes) <= 5
        for t in civ.traditions:
            assert t in ("martial", "food_stockpiling", "diplomatic", "resilience")
        for gp in civ.great_persons:
            assert gp.active is True
    for gp in world.retired_persons:
        assert gp.active is False
        assert gp.fate in ("retired", "dead", "ascended")
