"""Arc output parity against frozen d028 source, not a wall-time benchmark."""
from __future__ import annotations

import hashlib
import inspect
from itertools import product
from pathlib import Path
import pickle
import random
from types import SimpleNamespace

import numpy as np
import pytest

from chronicler.arcs import classify_arc
from chronicler.dynasties import Dynasty, DynastyRegistry
from chronicler.history_index import history_index
from chronicler.models import Event, GreatPerson

REFERENCE = Path(__file__).parent / "fixtures/performance/arcs_d0281e5f.py.txt"
REFERENCE_BLOB = "87f38c36f85f514e0dc409864afaa700fd7fcc25"


@pytest.fixture(scope="module")
def legacy_classifier():
    # The LF source fixture is byte-pinned. Checkout CRLF is only a source-text
    # portability issue; simulation outputs are never normalized by these tests.
    raw = REFERENCE.read_bytes().replace(b"\r\n", b"\n")
    blob = b"blob " + str(len(raw)).encode() + b"\0" + raw
    assert hashlib.sha1(blob, usedforsecurity=False).hexdigest() == REFERENCE_BLOB
    namespace = {"__name__": "_frozen_arcs_d028_reference"}
    exec(compile(raw, str(REFERENCE), "exec"), namespace)
    return namespace["classify_arc"]


def _gp(**changes):
    values = dict(name="Kiran", role="general", trait="cautious",
                  civilization="Aram", origin_civilization="Aram",
                  born_turn=100, source="agent", agent_id=1)
    values.update(changes)
    return GreatPerson(**values)


def _event(kind, turn=150, actors=None):
    return Event(turn=turn, event_type=kind,
                 actors=["Kiran", "Aram"] if actors is None else actors,
                 description="frozen-classifier parity fixture")


def test_public_classifier_signature_is_unchanged(legacy_classifier):
    assert inspect.signature(classify_arc) == inspect.signature(legacy_classifier)


def test_all_event_predicate_combinations_preserve_precedence(legacy_classifier):
    kinds = ("character_death", "conquest_exile", "exile_return",
             "secession_defection", "pilgrimage_return")
    people = [
        (_gp(trait=trait, role=role, death_turn=100 + career if dead else None,
             fate="dead" if dead else "active", active=not dead, alive=not dead,
             civilization="Bora" if dead else "Aram"), 100 + career)
        for trait, role, career, dead in product(
            ("bold", "cautious"), ("general", "prophet"), (19, 20, 34, 35), (False, True))
    ]
    people.extend([
        (_gp(active=False, fate="exile", civilization="Bora"), 200),
        (_gp(role="prophet", active=False, fate="exile", civilization="Bora"), 200),
        (_gp(role="prophet", pilgrimage_return_turn=500), 200),
        (_gp(born_turn=195, trait="bold", civilization="Bora"), 200),
    ])
    for flags in product((False, True), repeat=len(kinds)):
        for migrations in range(5):
            events = [_event(kind, turn=-200 + index, actors=["Kiran", "Kiran", "Aram"])
                      for index, (kind, present) in enumerate(zip(kinds, flags)) if present]
            events += [_event("notable_migration", turn=9999 + index) for index in range(migrations)]
            events += [_event("CONQUEST_EXILE"), _event("notable_migration_extra"),
                       _event("pilgrimage_return", actors=[]),
                       _event("character_death", actors=["Other"])]
            # Neither implementation filters event turns or requires chronology.
            events.reverse()
            for gp, current_turn in people:
                expected = legacy_classifier(gp, events, None, current_turn)
                assert classify_arc(gp, events, None, current_turn) == expected, (flags, migrations, gp)


def test_dynasty_and_competing_complete_matches_keep_first_dynasty_and_last_arc(legacy_classifier):
    gp = _gp(role="prophet", trait="bold", active=False, alive=False,
             fate="dead", death_turn=120, dynasty_id=7, civilization="Bora")
    events = [_event(kind) for kind in (
        "character_death", "conquest_exile", "exile_return",
        "secession_defection", "pilgrimage_return",
        "notable_migration", "notable_migration", "notable_migration",
    )]
    for founder, members in ((1, [1]), (1, [1, 2]), (9, [9, 1])):
        registry = DynastyRegistry()
        registry.dynasties = [
            Dynasty(dynasty_id=7, founder_id=founder, founder_name="Kiran", civ_id="Aram", members=members),
            Dynasty(dynasty_id=7, founder_id=1, founder_name="Kiran", civ_id="Aram", members=[1, 2, 3]),
        ]
        assert classify_arc(gp, events, registry, 200) == legacy_classifier(gp, events, registry, 200)
    assert classify_arc(gp, events, None, 200) == (None, "Exile-and-Return")


def test_long_history_duplicate_entries_and_actors_preserve_multiplicity(legacy_classifier):
    gp = _gp()
    migration = _event("notable_migration", turn=-999, actors=["Kiran", "Kiran"])
    events = [_event("unrelated_type", actors=["Kiran"]) for _ in range(3000)]
    events += [_event("exile_return", actors=["Other"]) for _ in range(2000)]
    events += [migration, migration]
    assert classify_arc(gp, events, None, 200) == legacy_classifier(gp, events, None, 200)
    assert classify_arc(gp, events, None, 200) == ("wandering", None)
    events.append(migration)
    assert classify_arc(gp, events, None, 200) == ("wandering", "Wanderer")
    assert classify_arc(gp, list(reversed(events)), None, 200) == legacy_classifier(
        gp, list(reversed(events)), None, 200)


def test_same_list_append_rewrite_actor_rename_and_type_change_reclassify(legacy_classifier):
    gp = _gp()
    events = [_event("notable_migration") for _ in range(3)]

    def check():
        assert classify_arc(gp, events, None, 200) == legacy_classifier(gp, events, None, 200)

    check()
    events.append(_event("conquest_exile", turn=-1))
    check()
    events.append(_event("exile_return", turn=9999))
    check()
    assert classify_arc(gp, events, None, 200) == (None, "Exile-and-Return")
    events[-1].event_type = "unrelated_type"
    check()
    events[-1].actors[:] = ["Renamed"]
    gp.name = "Renamed"
    check()
    assert classify_arc(gp, events, None, 200) == ("rising", None)
    events[:] = [_event("pilgrimage_return", turn=-9, actors=["Renamed"])]
    check()
    assert classify_arc(gp, events, None, 200) == ("converting", "Prophet")


def test_actor_index_consumer_still_filters_removed_actors_and_detected_rewrites(legacy_classifier):
    gp = _gp()
    events = [_event("notable_migration") for _ in range(3)]
    world = SimpleNamespace(events_timeline=events)
    index = history_index(world)

    def check():
        bucket = index.events_for_actor(world, gp.name)
        assert classify_arc(gp, bucket, None, 200) == legacy_classifier(
            gp, world.events_timeline, None, 200)

    check()
    # Existing cursor cannot detect same-object actor removal. The classifier's
    # actor filter is deliberately retained, so a stale bucket cannot count it.
    events[0].actors[:] = ["Other"]
    check()
    assert classify_arc(gp, index.events_for_actor(world, gp.name), None, 200) == ("wandering", None)
    events.append(_event("conquest_exile"))
    check()
    events[-1] = _event("pilgrimage_return")
    check()
    del events[1:]
    check()
    world.events_timeline = [_event("character_death", turn=-1)]
    check()


def test_classifier_does_not_mutate_inputs_raw_pickle_or_rng(legacy_classifier):
    gp = _gp(dynasty_id=7, civilization="Bora")
    registry = DynastyRegistry()
    registry.dynasties = [
        Dynasty(dynasty_id=7, founder_id=1, founder_name="Kiran", civ_id="Aram", members=[1, 2]),
    ]
    events = [_event(kind) for kind in ("conquest_exile", "exile_return", "notable_migration")]
    inputs = (gp, events, registry)
    before = pickle.dumps(inputs, protocol=5)
    model_json = gp.model_dump_json()
    event_json = [event.model_dump_json() for event in events]
    python_rng = pickle.dumps(random.getstate(), protocol=5)
    numpy_rng = pickle.dumps(np.random.get_state(), protocol=5)
    expected = legacy_classifier(gp, events, registry, 200)
    assert classify_arc(gp, events, registry, 200) == expected
    assert classify_arc(gp, events, registry, 200) == expected
    assert pickle.dumps(inputs, protocol=5) == before
    assert gp.model_dump_json() == model_json
    assert [event.model_dump_json() for event in events] == event_json
    assert pickle.dumps(random.getstate(), protocol=5) == python_rng
    assert pickle.dumps(np.random.get_state(), protocol=5) == numpy_rng


def test_event_type_projection_reads_each_matching_attribute_once(legacy_classifier):
    class ObservedEvent:
        def __init__(self, kind, actors):
            self.kind, self.actors, self.reads = kind, actors, 0

        @property
        def event_type(self):
            self.reads += 1
            return self.kind

    gp = _gp(role="prophet", civilization="Bora")
    events = [ObservedEvent("unrelated_type", ["Kiran"]) for _ in range(100)]
    events += [ObservedEvent("notable_migration", ["Other"]) for _ in range(100)]
    expected = legacy_classifier(gp, events, None, 200)
    legacy_reads = sum(event.reads for event in events)
    for event in events:
        event.reads = 0
    assert classify_arc(gp, events, None, 200) == expected
    assert [event.reads for event in events] == [1] * 100 + [0] * 100
    assert legacy_reads > sum(event.reads for event in events)
