"""Incremental history indexes answer exactly as the full rescans they replace."""
from __future__ import annotations

import argparse
import copy
import random
from types import SimpleNamespace

import pytest

from chronicler.history_index import HistoryIndex, history_index
from chronicler.models import AgentEventRecord, Event, NamedEvent, WorldState
from chronicler.movements import _detect_schisms
from chronicler.named_events import deduplicate_name


# --- Reference (pre-index) implementations --------------------------------

def naive_events_for_turn(world, turn):
    return [e for e in world.events_timeline if e.turn == turn]


def naive_events_for_actor(world, actor):
    return [e for e in world.events_timeline if actor in e.actors]


def naive_names(world):
    return [ne.name for ne in world.named_events]


def naive_schism_fired(world, movement_id, a, b):
    return any(
        ne.event_type == "movement_schism"
        and a in ne.actors and b in ne.actors
        and movement_id in ne.description
        for ne in world.named_events
    )


def naive_hegemony_fired(world, civ_name):
    return any(ne.event_type == "cultural_hegemony" and civ_name in ne.actors
               for ne in world.named_events)


def naive_enlightenment_fired(world, movement_id):
    return any(ne.event_type == "universal_enlightenment" and movement_id in ne.description
               for ne in world.named_events)


def naive_agent_counts(world, agent_id):
    migrations = [e for e in world.agent_events_raw
                  if e.agent_id == agent_id and e.event_type == "migration"]
    switches = sum(1 for e in world.agent_events_raw
                   if e.agent_id == agent_id and e.event_type == "occupation_switch")
    return len(migrations), switches


def naive_agent_migrations(world, turn):
    return [e for e in world.agent_events_raw if e.event_type == "migration" and e.turn == turn]


def naive_detect_schisms(world):
    """The pre-index movements._detect_schisms, verbatim."""
    from itertools import combinations
    for movement in world.movements:
        adherent_names = list(movement.adherents.keys())
        for a, b in combinations(adherent_names, 2):
            divergence = abs(movement.adherents[a] - movement.adherents[b])
            if divergence >= 3:
                if not naive_schism_fired(world, movement.id, a, b):
                    world.named_events.append(NamedEvent(
                        name=f"Schism of {movement.id.replace('_', ' ')}",
                        event_type="movement_schism",
                        turn=world.turn,
                        actors=[a, b],
                        description=f"[{movement.id}] Schism between {a} and {b}.",
                        importance=7,
                    ))


# --- Fixtures ---------------------------------------------------------------

CIVS = ["Aram", "Bel", "Cor", "Dun", "Esk"]
EVENT_TYPES = ["war", "trade", "famine", "cultural_work", "expand", "rebellion"]
NAMED_TYPES = ["battle", "movement_schism", "cultural_hegemony", "universal_enlightenment", "treaty"]


def _world():
    return WorldState(name="Index", seed=3)


def _random_event(rng, turn):
    actors = rng.sample(CIVS, rng.randint(0, 3))
    if actors and rng.random() < 0.2:
        actors.append(actors[0])  # duplicate actor entries must count once
    return Event(turn=turn, event_type=rng.choice(EVENT_TYPES), actors=actors,
                 description=f"d{rng.randint(0, 9)}", importance=rng.randint(1, 9))


def _random_named(rng, turn):
    event_type = rng.choice(NAMED_TYPES)
    movement = f"movement_{rng.choice([1, 2, 10, 12, 21])}"
    return NamedEvent(
        name=rng.choice(["The Sack of X", "The Iron Pact", "Schism", f"N{rng.randint(0, 5)}"]),
        event_type=event_type, turn=turn, actors=rng.sample(CIVS, rng.randint(1, 3)),
        description=f"[{movement}] something", importance=5,
    )


def _random_agent_event(rng, turn):
    return AgentEventRecord(
        turn=turn, agent_id=rng.randint(1, 6),
        event_type=rng.choice(["migration", "occupation_switch", "death", "birth"]),
        region=rng.randint(0, 3), target_region=rng.randint(0, 3),
        civ_affinity=rng.randint(0, 2), occupation=rng.randint(0, 2),
    )


def _assert_all_queries_match(world, index):
    turns = {e.turn for e in world.events_timeline} | {e.turn for e in world.agent_events_raw} | {-1, 999}
    for turn in sorted(turns):
        assert index.events_for_turn(world, turn) == naive_events_for_turn(world, turn)
        assert index.agent_migrations_for_turn(world, turn) == naive_agent_migrations(world, turn)
    for actor in CIVS + ["Nobody"]:
        assert index.events_for_actor(world, actor) == naive_events_for_actor(world, actor)
        assert index.hegemony_fired(world, actor) == naive_hegemony_fired(world, actor)
    names = index.named_event_names(world)
    expected = naive_names(world)
    assert len(names) == len(expected)
    for candidate in set(expected) | {"absent", "The Second Sack of X"}:
        assert (candidate in names) == (candidate in expected)
    for movement in ("movement_1", "movement_2", "movement_10", "movement_3"):
        assert index.enlightenment_fired(world, movement) == naive_enlightenment_fired(world, movement)
        for a in CIVS:
            for b in CIVS:
                assert index.schism_fired(world, movement, a, b) == naive_schism_fired(world, movement, a, b)
    for agent_id in range(0, 8):
        assert index.agent_event_counts(world, agent_id) == naive_agent_counts(world, agent_id)


# --- Tests --------------------------------------------------------------------

@pytest.mark.parametrize("seed", range(6))
def test_interleaved_appends_and_queries_match_full_rescans(seed):
    rng = random.Random(seed)
    world = _world()
    index = history_index(world)
    for turn in range(25):
        # Out-of-order turns are legal in the timeline; buckets keep list order.
        for _ in range(rng.randint(0, 6)):
            world.events_timeline.append(_random_event(rng, turn + rng.choice([0, 0, 0, -1, 1])))
        for _ in range(rng.randint(0, 3)):
            world.named_events.append(_random_named(rng, turn))
        for _ in range(rng.randint(0, 8)):
            world.agent_events_raw.append(_random_agent_event(rng, turn))
        if rng.random() < 0.5:
            _assert_all_queries_match(world, index)
    _assert_all_queries_match(world, index)
    assert history_index(world) is index


def test_replaced_shortened_or_rewritten_lists_are_rebuilt():
    rng = random.Random(11)
    world = _world()
    index = history_index(world)
    for turn in range(5):
        world.events_timeline.extend(_random_event(rng, turn) for _ in range(4))
        world.named_events.extend(_random_named(rng, turn) for _ in range(3))
        world.agent_events_raw.extend(_random_agent_event(rng, turn) for _ in range(4))
    _assert_all_queries_match(world, index)

    # Shortened in place.
    del world.events_timeline[3:]
    del world.named_events[2:]
    del world.agent_events_raw[1:]
    _assert_all_queries_match(world, index)
    # Same length, different tail object.
    world.events_timeline[-1] = _random_event(rng, 77)
    world.named_events[-1] = _random_named(rng, 77)
    world.agent_events_raw[-1] = _random_agent_event(rng, 77)
    _assert_all_queries_match(world, index)
    # Cleared then regrown past the old length.
    world.events_timeline.clear()
    world.events_timeline.extend(_random_event(rng, 5) for _ in range(9))
    _assert_all_queries_match(world, index)
    # Replaced list objects.
    world.events_timeline = [_random_event(rng, 6) for _ in range(3)]
    world.named_events = [_random_named(rng, 6) for _ in range(3)]
    world.agent_events_raw = [_random_agent_event(rng, 6) for _ in range(3)]
    _assert_all_queries_match(world, index)
    world.events_timeline = []
    _assert_all_queries_match(world, index)


def test_schism_check_keeps_substring_semantics():
    """movement_1's check also matches '[movement_10]' descriptions, as before."""
    world = _world()
    world.named_events.append(NamedEvent(
        name="Schism of movement 10", event_type="movement_schism", turn=1,
        actors=["Bel", "Aram", "Cor"], description="[movement_10] Schism between Bel and Aram.",
        importance=7))
    index = history_index(world)
    assert index.schism_fired(world, "movement_1", "Aram", "Bel")
    assert index.schism_fired(world, "movement_10", "Cor", "Aram")
    assert not index.schism_fired(world, "movement_2", "Aram", "Bel")
    assert not index.schism_fired(world, "movement_10", "Aram", "Dun")


@pytest.mark.parametrize("seed", range(4))
def test_detect_schisms_matches_reference_implementation(seed):
    from chronicler.models import Movement
    rng = random.Random(seed)
    current, reference = _world(), _world()
    for turn in range(40):
        if turn % 7 == 0:
            movement_id = f"movement_{len(current.movements) * 9 // 4}"
            adherents = {name: rng.randint(0, 2) for name in rng.sample(CIVS, rng.randint(2, 5))}
            for world in (current, reference):
                world.movements.append(Movement(id=movement_id, origin_civ=next(iter(adherents)),
                                                origin_turn=turn, value_affinity="Honor",
                                                adherents=dict(adherents)))
        bumps = [(m_index, name) for m_index, m in enumerate(current.movements)
                 for name in m.adherents if rng.random() < 0.3]
        for world in (current, reference):
            world.turn = turn
            for m_index, name in bumps:
                world.movements[m_index].adherents[name] += 1
        _detect_schisms(current)
        naive_detect_schisms(reference)
        assert [ne.model_dump() for ne in current.named_events] == \
            [ne.model_dump() for ne in reference.named_events]
    assert any(ne.event_type == "movement_schism" for ne in current.named_events)


def test_name_view_drives_deduplicate_name_like_a_list():
    world = _world()
    for name in ["The Iron Pact", "The Second Iron Pact", "The Iron Pact", "Battle"]:
        world.named_events.append(NamedEvent(name=name, event_type="treaty", turn=0,
                                             actors=[], description="", importance=1))
    view = history_index(world).named_event_names(world)
    names = naive_names(world)
    for name in ["The Iron Pact", "Battle", "Fresh", "The Second Iron Pact"]:
        assert deduplicate_name(name, view) == deduplicate_name(name, names)
    # The "(n)" fallback counts every named event, duplicates included.
    from chronicler.named_events import _ORDINALS
    for ordinal in _ORDINALS:
        world.named_events.append(NamedEvent(name=f"The {ordinal} Iron Pact", event_type="treaty",
                                             turn=0, actors=[], description="", importance=1))
    view = history_index(world).named_event_names(world)
    assert deduplicate_name("The Iron Pact", view) == deduplicate_name("The Iron Pact", naive_names(world))
    assert deduplicate_name("The Iron Pact", view).endswith(f"({len(world.named_events) + 1})")


def test_index_is_never_serialized_copied_or_compared(tmp_path):
    rng = random.Random(5)
    world = _world()
    for turn in range(6):
        world.events_timeline.extend(_random_event(rng, turn) for _ in range(5))
        world.named_events.extend(_random_named(rng, turn) for _ in range(2))
    index = history_index(world)
    _assert_all_queries_match(world, index)
    plain = world.model_dump_json(indent=2)

    # Never serialized: dumps are identical with and without a warm index.
    fresh = WorldState.model_validate_json(plain)
    assert fresh.model_dump_json(indent=2) == plain
    assert "_history_index" not in plain

    # A loaded world (resume) starts empty and rebuilds to the same answers.
    path = tmp_path / "state.json"
    world.save(path)
    loaded = WorldState.load(path)
    assert loaded._history_index is None
    _assert_all_queries_match(loaded, history_index(loaded))
    assert history_index(loaded) is not index

    # Deep copies get their own empty index; caches never make worlds unequal.
    for clone in (world.model_copy(deep=True), copy.deepcopy(world)):
        assert clone._history_index is not index
        assert clone == world
        _assert_all_queries_match(clone, history_index(clone))
    assert loaded == world
    # A shallow copy shares the lists and may share the index; both stay exact,
    # including after the copy's list is replaced.
    shallow = copy.copy(world)
    assert shallow == world
    shallow.events_timeline = shallow.events_timeline[:4]
    _assert_all_queries_match(shallow, history_index(shallow))
    _assert_all_queries_match(world, history_index(world))
    _assert_all_queries_match(shallow, history_index(shallow))


def test_duck_typed_and_unattachable_worlds_still_answer():
    events = [Event(turn=1, event_type="war", actors=["A", "B"], description="", importance=5)]
    ns = SimpleNamespace(events_timeline=list(events))
    assert history_index(ns).events_for_turn(ns, 1) == events
    assert isinstance(ns._history_index, HistoryIndex)

    class Slotted:
        __slots__ = ("events_timeline",)

    slotted = Slotted()
    slotted.events_timeline = list(events)
    assert history_index(slotted).events_for_actor(slotted, "B") == events

    from unittest.mock import MagicMock
    mock = MagicMock()
    mock.events_timeline = list(events)
    assert history_index(mock).events_for_turn(mock, 1) == events


def test_indexed_answers_match_rescans_throughout_a_real_run(tmp_path, monkeypatch):
    """Every index query during a simulation equals the full rescan at that moment."""
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda world: None)
    checks = {"count": 0}

    def checked(name, naive):
        original = getattr(HistoryIndex, name)

        def wrapper(self, world, *args):
            result = original(self, world, *args)
            expected = naive(world, *args)
            if name == "named_event_names":
                assert len(result) == len(expected)
                assert all(n in result for n in expected)
            else:
                assert result == expected, name
            checks["count"] += 1
            return result

        monkeypatch.setattr(HistoryIndex, name, wrapper)

    checked("events_for_turn", naive_events_for_turn)
    checked("events_for_actor", naive_events_for_actor)
    checked("named_event_names", naive_names)
    checked("schism_fired", naive_schism_fired)
    checked("hegemony_fired", naive_hegemony_fired)
    checked("enlightenment_fired", naive_enlightenment_fired)

    from chronicler.main import execute_run
    args = argparse.Namespace(seed=42, turns=70, civs=4, regions=8,
                              output=str(tmp_path / "chronicle.md"), state=str(tmp_path / "state.json"),
                              resume=None, reflection_interval=10, llm_actions=False, scenario=None,
                              simulate_only=True, agents="off")
    execute_run(args)
    assert checks["count"] > 140
