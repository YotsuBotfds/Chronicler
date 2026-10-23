"""M24 hostage intelligence through the existing M17 lifecycle."""
from unittest.mock import MagicMock

import pytest

from chronicler.great_persons import kill_great_person
from chronicler.intelligence import compute_accuracy, get_perceived_stat
from chronicler.models import FactionState, FactionType, Federation, GreatPerson, WorldState
from chronicler.relationships import capture_hostage, release_hostage, tick_hostages


@pytest.fixture
def hostage_world(make_world):
    world = make_world(num_civs=3)
    for civ in world.civilizations:
        civ.factions = FactionState(influence={
            FactionType.MILITARY: 0.7, FactionType.MERCHANT: 0.1,
            FactionType.CULTURAL: 0.1, FactionType.CLERGY: 0.1,
        })
    origin, captor, _ = world.civilizations
    origin.great_persons.append(GreatPerson(
        name="Prince", role="general", trait="bold", civilization=origin.name,
        origin_civilization=origin.name, born_turn=1,
    ))
    return world


def test_capture_gives_directional_contact_and_bounded_perception(hostage_world):
    world = hostage_world
    origin, captor, unrelated = world.civilizations
    assert compute_accuracy(origin, captor, world) == 0.0
    assert get_perceived_stat(origin, captor, "military", world) is None
    gp = capture_hostage(origin, captor, world)
    assert gp.civilization == captor.name
    assert gp.origin_civilization == origin.name
    assert compute_accuracy(origin, captor, world) == pytest.approx(0.3)
    assert compute_accuracy(captor, origin, world) == 0.0
    assert compute_accuracy(unrelated, captor, world) == 0.0
    assert compute_accuracy(origin, unrelated, world) == 0.0
    assert compute_accuracy(origin, origin, world) == 1.0
    for stat in ("military", "economy", "stability"):
        value = get_perceived_stat(origin, captor, stat, world)
        assert value == get_perceived_stat(origin, captor, stat, world)
        assert abs(value - getattr(captor, stat)) <= 14
        assert 0 <= value <= 100


@pytest.mark.parametrize("field,value", [
    ("alive", False), ("active", False), ("is_hostage", False),
    ("origin_civilization", "Civ2"), ("civilization", "Civ2"),
])
def test_ineligible_captive_gives_no_contact(hostage_world, field, value):
    world = hostage_world
    origin, captor, _ = world.civilizations
    gp = capture_hostage(origin, captor, world)
    setattr(gp, field, value)
    assert compute_accuracy(origin, captor, world) == 0.0
    assert get_perceived_stat(origin, captor, "military", world) is None


def test_hostage_on_wrong_roster_gives_no_contact(hostage_world):
    world = hostage_world
    origin, captor, _ = world.civilizations
    gp = capture_hostage(origin, captor, world)
    captor.great_persons.remove(gp)
    origin.great_persons.append(gp)
    assert compute_accuracy(origin, captor, world) == 0.0


def test_legacy_merchant_hostage_does_not_give_captor_merchant_bonus(hostage_world):
    world = hostage_world
    origin, captor, _ = world.civilizations
    gp = capture_hostage(origin, captor, world)
    # Older saves can retain the pre-capture role and omit captured_by.
    gp.role = "merchant"
    gp.captured_by = None
    assert compute_accuracy(origin, captor, world) == pytest.approx(0.3)
    assert compute_accuracy(captor, origin, world) == 0.0


def test_synthetic_hostage_gives_contact(hostage_world):
    world = hostage_world
    origin, captor, _ = world.civilizations
    origin.great_persons.clear()
    gp = capture_hostage(origin, captor, world)
    assert gp.source == "aggregate"
    assert gp.agent_id is None
    assert compute_accuracy(origin, captor, world) == pytest.approx(0.3)


def test_auto_release_expires_contact_and_clears_state(hostage_world):
    world = hostage_world
    origin, captor, _ = world.civilizations
    gp = capture_hostage(origin, captor, world)
    for _ in range(14):
        assert tick_hostages(world) == []
        assert compute_accuracy(origin, captor, world) == pytest.approx(0.3)
    assert gp.cultural_identity == captor.name
    assert gp.hostage_turns == 14
    assert tick_hostages(world) == [gp]
    assert gp in origin.great_persons
    assert gp.role == "general"
    assert gp.is_hostage is False
    assert gp.hostage_turns == 0
    assert gp.captured_by is None
    assert compute_accuracy(origin, captor, world) == 0.0
    assert get_perceived_stat(origin, captor, "military", world) is None


def test_release_and_recapture_moves_contact_without_cache(hostage_world):
    world = hostage_world
    origin, captor, next_captor = world.civilizations
    gp = capture_hostage(origin, captor, world)
    assert compute_accuracy(origin, captor, world) == pytest.approx(0.3)
    release_hostage(gp, captor, origin, world)
    assert compute_accuracy(origin, captor, world) == 0.0
    capture_hostage(origin, next_captor, world)
    assert gp.hostage_turns == 0
    assert compute_accuracy(origin, captor, world) == 0.0
    assert compute_accuracy(origin, next_captor, world) == pytest.approx(0.3)


def test_death_ends_contact_even_when_retired_hostage_state_is_preserved(hostage_world):
    world = hostage_world
    origin, captor, _ = world.civilizations
    gp = capture_hostage(origin, captor, world)
    assert compute_accuracy(origin, captor, world) == pytest.approx(0.3)
    kill_great_person(gp, captor, world)
    assert gp in world.retired_persons
    assert gp.is_hostage is True
    assert compute_accuracy(origin, captor, world) == 0.0


@pytest.mark.parametrize("missing", [False, True])
def test_origin_loss_clears_hostage_contact(hostage_world, missing):
    world = hostage_world
    origin, captor, unrelated = world.civilizations
    gp = capture_hostage(origin, captor, world)
    if missing:
        world.civilizations.remove(origin)
    else:
        origin.regions.clear()
    assert tick_hostages(world) == [gp]
    assert gp.is_hostage is False
    assert compute_accuracy(origin, captor, world) == 0.0
    assert compute_accuracy(unrelated, captor, world) == 0.0


def test_multiple_hostages_are_one_contact_source(hostage_world):
    world = hostage_world
    origin, captor, _ = world.civilizations
    first = capture_hostage(origin, captor, world)
    second = capture_hostage(origin, captor, world)
    assert compute_accuracy(origin, captor, world) == pytest.approx(0.3)
    release_hostage(first, captor, origin, world)
    assert compute_accuracy(origin, captor, world) == pytest.approx(0.3)
    release_hostage(second, captor, origin, world)
    assert compute_accuracy(origin, captor, world) == 0.0


def test_hostage_source_stacks_with_existing_sources_and_caps(hostage_world):
    world = hostage_world
    origin, captor, _ = world.civilizations
    world.active_wars = [(origin.name, captor.name)]
    world.federations = [Federation(name="Alliance", members=[origin.name, captor.name],
                                    founded_turn=1)]
    # Federation also supplies trade contact: 0.4 + 0.2 + war 0.3.
    assert compute_accuracy(origin, captor, world) == pytest.approx(0.9)
    capture_hostage(origin, captor, world)
    assert compute_accuracy(origin, captor, world) == 1.0
    assert get_perceived_stat(origin, captor, "military", world) == captor.military


def test_save_roundtrip_preserves_contact_and_release(hostage_world):
    world = hostage_world
    origin, captor, _ = world.civilizations
    capture_hostage(origin, captor, world)
    perceived = get_perceived_stat(origin, captor, "military", world)
    restored = WorldState.model_validate_json(world.model_dump_json())
    restored_origin, restored_captor, _ = restored.civilizations
    assert compute_accuracy(restored_origin, restored_captor, restored) == pytest.approx(0.3)
    assert get_perceived_stat(restored_origin, restored_captor, "military", restored) == perceived
    release_hostage(restored_captor.great_persons[0], restored_captor, restored_origin, restored)
    reset = WorldState.model_validate_json(restored.model_dump_json())
    assert compute_accuracy(reset.civilizations[0], reset.civilizations[1], reset) == 0.0
    # Loading/releasing another world cannot mutate the original world's contact.
    assert compute_accuracy(origin, captor, world) == pytest.approx(0.3)


def test_agent_civ_sync_and_intelligence_share_capture_release_state(hostage_world):
    world = hostage_world
    origin, captor, _ = world.civilizations
    origin.great_persons[0].source = "agent"
    origin.great_persons[0].agent_id = 123
    bridge = MagicMock()
    gp = capture_hostage(origin, captor, world, bridge=bridge)
    bridge._sim.set_agent_civ.assert_called_once_with(123, 1)
    assert compute_accuracy(origin, captor, world) == pytest.approx(0.3)
    release_hostage(gp, captor, origin, world, bridge=bridge)
    assert bridge._sim.set_agent_civ.call_count == 2
    bridge._sim.set_agent_civ.assert_called_with(123, 0)
    assert compute_accuracy(origin, captor, world) == 0.0
