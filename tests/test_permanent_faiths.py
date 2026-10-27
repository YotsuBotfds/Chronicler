"""Permanent faith identities (``chronicler.faiths``; docs/integration/permanent-faiths.md).

A faith's native id is a reusable slot; its permanent id is its index in
``WorldState.faiths``. These tests run without the extension: the
recycling path is ``agent_movements._schism`` with a full registry and
Phase 10 rows built as the native snapshot carries them.
"""
from __future__ import annotations

import json
import pickle

import pytest

from chronicler import faiths as F
from chronicler.agent_movements_state import ENDED, FADED, LAPSED, SCHISM, SECT, TOLERATION, Reform
from chronicler.models import Belief, Event, FaithRecord, WorldState
from chronicler.world_gen import generate_world

from tests.test_agent_movements import (
    KETHANI, THORNWALL, THORNWOOD, _full_registry_world, _place, _restless, _tick as _movement_tick,
)


def _recycle(world, slot: int, name: str) -> int:
    """As ``agent_movements._schism`` with a full registry: the faith in
    ``slot`` is gone and a new sect takes its slot and registry position."""
    pos = next(k for k, b in enumerate(world.belief_registry) if b.faith_id == slot)
    old = world.belief_registry[pos]
    new = Belief(faith_id=slot, name=name, civ_origin=old.civ_origin, doctrines=list(old.doctrines))
    world.belief_registry[pos] = new
    F.release(world, slot)
    return F.found(world, new, origin=F.SECT)


def _schism_world():
    """The full-registry template world after a sect took slot 4 (the
    lowest free one) at turn 30: permanent id 16, the vanished faith keeps 4."""
    world = _full_registry_world()
    F.ensure(world)   # the hand-added faiths, recorded as founded at turn 1
    for rec in world.faiths:
        if rec.origin == F.UNRECORDED:
            rec.founded_turn = 1
    m = _restless(world, creed=SECT, stability=60)
    m.grievance = 0.25
    events = _movement_tick(world, members={(0, THORNWOOD): 8})
    assert "Schism" in [e.event_type for e in events] and m.end == SCHISM
    return world, m


# --- the table ---------------------------------------------------------------------

def test_world_generation_records_the_founding_faiths():
    world = generate_world(seed=7)
    assert len(world.faiths) == len(world.belief_registry) == len(world.civilizations)
    for k, (rec, belief) in enumerate(zip(world.faiths, world.belief_registry)):
        assert (rec.slot, rec.name, rec.civ, rec.founded_turn, rec.origin) == (
            belief.faith_id, belief.name, k, 0, "founding")
        assert F.uid_of(world, belief.faith_id) == F.slot_of(world, k) == k
    # Serialized: the table travels in state.json (omitted for a world without faiths).
    assert json.loads(world.model_dump_json())["faiths"][0]["name"] == world.belief_registry[0].name
    assert "faiths" not in json.loads(WorldState(name="empty", seed=1).model_dump_json())


def test_a_recycled_slot_names_two_churches_by_two_permanent_ids():
    world, m = _schism_world()
    old, sect = world.faiths[4], world.faiths[16]
    assert (old.name, old.slot, old.released_turn) == ("Old Faith 4", 4, world.turn)
    assert (sect.slot, sect.founded_turn, sect.origin, sect.released_turn) == (4, world.turn, "sect", None)
    assert sect.movement == world.agent_movements.movements.index(m)
    assert F.uid_of(world, 4) == 16 and F.slot_of(world, 16) == 4 and F.slot_of(world, 4) is None
    assert F.name_of(world, 4) == "Old Faith 4" and F.name_of(world, 16) == sect.name
    assert (m.schism_from, m.schism_to, m.successor, m.faith) == (sect.parent, 16, 16, 16)
    # The native table gets the sect's slot for the tick after the schism.
    from chronicler import agent_movements as M
    world.turn += 1
    table = M.movement_table(world).to_pydict()
    row = table["movement_id"].index(world.agent_movements.movements.index(m) + 1)
    assert (table["convert_from"][row], table["convert_to"][row]) == (F.slot_of(world, m.schism_from), 4)


def test_holder_at_reads_a_slot_as_it_stood_at_the_end_of_a_turn():
    world, _m = _schism_world()
    t = world.turn
    assert F.holder_at(world.faiths, 4, t - 1) == 4     # the vanished faith before the schism
    assert F.holder_at(world.faiths, 4, t) == 16        # the sect from its founding turn on
    assert F.holder_at(world.faiths, 4, None) == 16     # the end of the run
    assert F.holder_at(world.faiths, 0, 0) == 0
    assert F.holder_at(world.faiths, 0xFF, t) is None
    assert F.label(world.faiths[16]).endswith(f", founded turn {t}")


def test_ensure_records_a_faith_added_outside_the_founding_paths():
    world = generate_world(seed=42)
    n = len(world.faiths)
    world.belief_registry.append(Belief(faith_id=n, name="Hand-made", civ_origin=0, doctrines=[0] * 5))
    F.ensure(world)
    assert (world.faiths[n].name, world.faiths[n].origin, world.faiths[n].slot) == ("Hand-made", "unrecorded", n)
    before = [r.model_dump() for r in world.faiths]
    F.ensure(world)   # in step: nothing changes
    assert [r.model_dump() for r in world.faiths] == before


def test_permanent_ids_skip_the_no_faith_sentinel():
    world = generate_world(seed=42)
    while len(world.faiths) < F.NO_FAITH:
        world.faiths.append(FaithRecord(name="x", slot=99, released_turn=0))
    belief = Belief(faith_id=3, name="Late", civ_origin=0, doctrines=[0] * 5)
    F.release(world, 3)
    uid = F.found(world, belief, origin=F.SECT)
    assert uid == F.NO_FAITH + 1 and world.faiths[F.NO_FAITH].origin == F.RESERVED
    assert F.uid_of(world, 3) == uid and F.name_of(world, F.NO_FAITH) is None


# --- records ------------------------------------------------------------------------

def test_a_toleration_keeps_its_faith_through_a_later_recycle_of_its_slot():
    """A repealed toleration of faith 7 is no longer remembered; a sect takes
    slot 7: the reform still names the vanished faith, by name too."""
    from chronicler import agent_movements as M
    world = _full_registry_world()
    state = world.agent_movements
    state.reforms.append(Reform(kind=TOLERATION, civ=KETHANI, enacted_turn=1, faith=7,
                                repeal=LAPSED, repealed_turn=2))
    for f in (4, 5, 6):  # keep the lower free slots referenced
        state.reforms.append(Reform(kind=TOLERATION, civ=KETHANI, enacted_turn=3, faith=f))
    m = _restless(world, creed=SECT, stability=60)
    m.grievance = 0.25
    _movement_tick(world, members={(0, THORNWOOD): 8})
    assert F.slot_of(world, m.schism_to) == 7 and m.schism_to == 16
    old = state.reforms[0]
    assert old.faith == 7 and M.reform_name(world, old) == "the toleration of the Old Faith 7"
    assert [r for r in M.reform_table(world).to_pydict()["faith"]] == [4, 5, 6]


def test_temple_records_carry_the_permanent_id_and_narration_names_the_right_faith():
    from chronicler.infrastructure import destroy_temple_on_conquest
    from chronicler.models import Infrastructure
    from chronicler.narration_context import event_text
    world, _m = _schism_world()
    region = world.regions[THORNWOOD]
    region.infrastructure.append(Infrastructure(type="temples", builder_civ="x", built_turn=1, faith_id=4))
    ev = destroy_temple_on_conquest(region, world.civilizations[KETHANI], world)
    assert ev.description == f"Temple of faith 16 destroyed in {region.name}"
    names = F.names(world)
    assert event_text(ev, names) == f"The temple of the {world.faiths[16].name} is destroyed in {region.name}"
    old = Event(turn=5, event_type="temple_destroyed", actors=[], description="Temple of faith 4 replaced in X")
    assert event_text(old, names) == "The temple of the Old Faith 4 is replaced in X"


# --- live references (corrections) ---------------------------------------------------

def _preaching_after_a_recycle(monkeypatch):
    """A prophet of Kethani's faith preaches in Ashara Desert (a realm of
    the same faith); then the faith vanishes and a sect takes its slot,
    which the realms now hold. Returns the desert's conversion signal the
    turn after, and whether the old agenda is fulfilled once the new church
    holds the desert."""
    from tests.test_gp_agendas import KETHANI as K, T, _coreligionists, _force, _gp, _next, _rec, _rows, _tick
    from tests.test_gp_agendas import _world as agenda_world
    world = agenda_world()
    prophet = _gp(world, K, "prophet", "Seer Anwe", trait="zealous")
    faith = _coreligionists(world)
    rows = {"Amber Valley": [faith] * 4, "Ashara Desert": [3, 3, 3, 3, faith]}
    _force(monkeypatch, T.SPREAD_FAITH, "Ashara Desert")
    _tick(world, phase10=_rows(world, rows))
    assert _rec(world, prophet).agenda.conversion_faith_id == faith
    desert = world.region_map["Ashara Desert"]
    desert.conversion_rate_signal, desert.conversion_target_signal = 0.0, 0xFF
    assert [e.event_type for e in _next(world, phase10=_rows(world, rows))] == ["preaching"]
    assert desert.conversion_target_signal == faith
    new = _recycle(world, faith, "Faith of the Newcomers")
    assert F.uid_of(world, faith) == new != faith
    desert.conversion_rate_signal, desert.conversion_target_signal = 0.0, 0xFF
    _next(world, phase10=_rows(world, rows))
    signal = (desert.conversion_target_signal, desert.conversion_rate_signal)
    rows["Ashara Desert"] = [faith] * 5   # the new church holds the region
    fulfilled = "agenda_fulfilled" in [e.event_type for e in _next(world, phase10=_rows(world, rows))]
    return world, faith, new, signal, fulfilled


def test_a_prophet_never_preaches_for_the_church_that_took_his_faiths_slot(monkeypatch):
    """Correction: a spread-faith agenda held its faith's slot across turns;
    after a recycle it preached for (and was fulfilled by) the new church."""
    import chronicler.gp_agendas as G
    world, faith, new, signal, fulfilled = _preaching_after_a_recycle(monkeypatch)
    assert signal == (0xFF, 0.0) and not fulfilled
    # A new agenda names the realm's church by its own permanent id.
    assert G.faiths.uid_or_slot(world, world.civilizations[1].civ_majority_faith) == new
    # Control: the agenda's faith read as a slot (main before permanent ids).
    monkeypatch.setattr(F, "slot_of", lambda w, uid: uid)
    _world, faith, _new, signal, fulfilled = _preaching_after_a_recycle(monkeypatch)
    assert signal == (faith, pytest.approx(G.PREACHING_RATE)) and fulfilled


def test_a_conversion_ambition_is_observed_by_permanent_id():
    """Correction: a ruler's conversion objective names the faith by permanent
    id; a later church in its slot never satisfies it."""
    import chronicler.governance_runtime as GR
    from chronicler import ruler_ambitions as g04
    from chronicler.governance_state import CivGovernance
    world = generate_world(seed=42)
    GR.set_governance_enabled(world, True)
    civ = world.civilizations[KETHANI]
    slot = civ.civ_majority_faith
    for region in world.regions:
        if region.controller == civ.name:
            region.majority_belief = 0xFF   # not yet converted: every owned region is a candidate
    ctx = GR._build_context(world, None)
    before = GR._ambition_snapshot(world, KETHANI, civ, CivGovernance(), ctx, 0.5, 0.0, 0)
    assert before.conversion_predicates and {p.faith_id for p in before.conversion_predicates} == {slot}
    predicate = before.conversion_predicates[0]
    new = _recycle(world, slot, "Faith of the Newcomers")
    for region in world.regions:
        if region.controller == civ.name:
            region.majority_belief = slot   # the new church holds every region of the realm
    after = GR._ambition_snapshot(world, KETHANI, civ, CivGovernance(), GR._build_context(world, None),
                                  0.5, 0.0, 0)
    assert {o.faith_id for o in after.conversion_observations} == {new}
    assert not g04._converted(predicate, after.conversion_observations)
    # Control: observed by slot (main before permanent ids), the new church's
    # believers fulfil the old objective.
    import pytest as _pytest
    with _pytest.MonkeyPatch.context() as patch:
        patch.setattr(F, "uid_or_slot", lambda w, s: s)
        by_slot = GR._ambition_snapshot(world, KETHANI, civ, CivGovernance(), GR._build_context(world, None),
                                        0.5, 0.0, 0)
    assert g04._converted(predicate, by_slot.conversion_observations)


def test_the_scholars_of_a_vanished_faith_are_persecuted_under_the_church_in_its_slot(monkeypatch):
    """Correction: a seat held its scholars' faith by slot; when a later church
    took the slot and persecuted from it, the seat counted as its own faith."""
    import chronicler.scholarship as S
    from chronicler.scholarship_state import PERSECUTION
    from tests.test_scholarship import VERDANT, _no_draw, _seat, _tick
    from tests.test_scholarship import _world as learning_world
    _no_draw(monkeypatch, 0.999)
    world = learning_world()
    _si, seat = _seat(world, VERDANT, level=2, faith=3)
    _recycle(world, 3, "Faith of the Newcomers")
    region = world.regions[VERDANT]
    region.persecution_intensity, region.persecuting_faith = 0.6, 3   # the new church persecutes
    assert S._persecuted(world, region, seat.faith)
    # Control: compared as slots (main before permanent ids), the scholars
    # counted as the persecuting church's own.
    with monkeypatch.context() as patch:
        patch.setattr(F, "same_faith", lambda w, uid, slot: uid == slot)
        assert not S._persecuted(world, region, seat.faith)
    for _ in range(S.PERSECUTION_TURNS):
        world.turn += 1
        _tick(world)
    assert seat.fall_cause == PERSECUTION


def test_a_new_church_in_a_recycled_slot_keeps_its_own_temple_chronicle():
    from chronicler import historiography as H
    from chronicler.models import Infrastructure
    world, _m = _schism_world()
    H.set_historiography_enabled(world, True)
    world.regions[THORNWOOD].infrastructure.append(
        Infrastructure(type="temples", builder_civ="x", built_turn=world.turn, faith_id=4))
    world.turn += 1
    H.observe_turn(world)
    temples = [c for c in H.state_of(world).chroniclers if c.kind == "temple"]
    sect = next(c for c in temples if c.faith == 16)
    assert sect.chronicler_id == "temple:16" and world.faiths[16].name.split(" (")[0] in sect.name
    assert "temple:4" not in {c.chronicler_id for c in temples}


# --- older runs ---------------------------------------------------------------------

def _legacy(data: dict) -> dict:
    """An older run's state: no table, faiths named by slot (the projection
    scripts/turn_speed_identity.py applies)."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from turn_speed_identity import FaithProjection
    FaithProjection(data["faiths"])("state.json", data)
    assert "faiths" not in data
    return data


def test_an_older_save_gets_its_table_rebuilt_and_its_dated_references_mapped(tmp_path):
    world, m = _schism_world()
    # An ended movement that held the vanished faith before the schism.
    old = _place(world, creed=SECT, target=KETHANI, faith=4, stage=ENDED, end=FADED,
                 ended_turn=world.turn - 5)
    old.name = "the Old Believers"   # movement names are unique in a run
    recorded = [r.model_dump() for r in world.faiths]
    data = _legacy(json.loads(world.model_dump_json()))
    assert data["agent_movements"]["movements"][-1]["faith"] == 4
    path = tmp_path / "state.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = WorldState.load(path)
    # Live faiths keep id == slot; the vanished one gets a new id after them.
    table = loaded.faiths
    assert [(r.slot, r.name) for r in table[:16]] == [(b.faith_id, b.name) for b in
                                                      sorted(loaded.belief_registry, key=lambda b: b.faith_id)]
    gone = table[16]
    # Its founding (a hand-added faith) is in no event: its record says so.
    assert (gone.name, gone.slot, gone.released_turn, gone.founded_turn, gone.legacy) == (
        "Old Faith 4", 4, world.turn, None, "unresolved")
    sect = table[4]
    assert (sect.founded_turn, sect.origin, sect.movement) == (world.turn, "sect", recorded[16]["movement"])
    movements = loaded.agent_movements.movements
    assert movements[-1].faith == 16          # dated before the schism: the vanished faith
    assert movements[recorded[16]["movement"]].schism_to == 4   # the sect, whose id is its slot here
    # Rebuilt from its own events, the table names the same faiths as the
    # recorded one (the hand-added ones without the founding no event holds).
    key = lambda r: (r["name"], r["slot"], r.get("released_turn"))
    assert sorted(key(r.model_dump()) for r in table) == sorted(key(r) for r in recorded)
    dated = lambda r: (r["name"], r["slot"], r["founded_turn"], r["origin"])
    assert (sorted(dated(r.model_dump()) for r in table if r.origin != "unrecorded")
            == sorted(dated(r) for r in recorded if r["origin"] != "unrecorded"))


def test_an_older_record_without_its_schisms_marks_the_untraced_faiths():
    rows = F.reconstruct(
        [{"faith_id": 0, "name": "Faith of A", "civ_origin": 0},
         {"faith_id": 1, "name": "Faith of B", "civ_origin": 1},
         {"faith_id": 2, "name": "Faith of A (Reformed)", "civ_origin": 0}],
        [], ["A", "B"])
    assert [(r["founded_turn"], r["origin"], r["legacy"]) for r in rows] == [
        (0, "founding", "reconstructed"), (0, "founding", "reconstructed"),
        (None, "unrecorded", "unresolved")]
    assert not F.needs_mapping(rows)


def test_an_older_bundle_is_upgraded_in_place():
    registry = [{"faith_id": s, "name": f"Faith of C{s}" if s < 2 else f"Faith of C0 (Reformed {s})",
                 "civ_origin": 0} for s in range(3)]
    registry[2]["name"] = "New Sect"
    events = [
        {"turn": 10, "event_type": "Schism", "actors": ["C0"], "description":
            "A schism fractures C0: 'Faith of C0 (Reformed)' splits from the majority faith in R1 (minority_ratio=0.40)"},
        {"turn": 30, "event_type": "temple_destroyed", "actors": [], "description": "Temple of faith 2 replaced in R1"},
        {"turn": 50, "event_type": "Schism", "actors": ["C1"], "description":
            "the Seekers of R0 breaks away from the Faith of C1 in R0: 'New Sect' is founded in place of the "
            "vanished 'Faith of C0 (Reformed)'"},
        {"turn": 60, "event_type": "temple_destroyed", "actors": [], "description": "Temple of faith 2 destroyed in R0"},
    ]
    bundle = {
        "metadata": {"total_turns": 80},
        "world_state": {"belief_registry": registry, "civilizations": [{"name": "C0"}, {"name": "C1"}],
                        "regions": [{"name": "R0"}, {"name": "R1"}],
                        "agent_movements": {"movements": [{"name": "the Seekers of R0", "faith": 2,
                                                           "schism_turn": 50, "schism_from": 1, "schism_to": 2,
                                                           "end": 4, "successor": 2, "ended_turn": 50}],
                                            "reforms": [{"kind": 2, "faith": 2, "enacted_turn": 20}]}},
        "history": [{"turn": 41, "agent_movements": {"reforms": [{"kind": "toleration", "faith": 2}]}},
                    {"turn": 61, "agent_movements": {"reforms": [{"kind": "toleration", "faith": 2}]}}],
        "events_timeline": events,
    }
    assert F.upgrade_bundle(bundle)
    table = bundle["world_state"]["faiths"]
    assert [(r["name"], r["slot"], r["founded_turn"], r.get("released_turn")) for r in table] == [
        ("Faith of C0", 0, 0, None), ("Faith of C1", 1, 0, None), ("New Sect", 2, 50, None),
        ("Faith of C0 (Reformed)", 2, 10, 50)]
    assert table[3]["parent"] == 0 and table[2]["parent"] == 1 and table[2]["movement"] == 0
    assert [e["description"] for e in events if e["event_type"] == "temple_destroyed"] == [
        "Temple of faith 3 replaced in R1", "Temple of faith 2 destroyed in R0"]
    assert bundle["world_state"]["agent_movements"]["reforms"][0]["faith"] == 3
    assert [s["agent_movements"]["reforms"][0]["faith"] for s in bundle["history"]] == [3, 2]
    m = bundle["world_state"]["agent_movements"]["movements"][0]
    assert (m["faith"], m["schism_from"], m["schism_to"], m["successor"]) == (2, 1, 2, 2)
    assert not F.upgrade_bundle(bundle)   # once only


# --- checkpoints ----------------------------------------------------------------------

def test_checkpoints_carry_the_table_and_older_ones_get_it_rebuilt(tmp_path):
    from chronicler import run_checkpoint as RC
    world, _m = _schism_world()
    path = tmp_path / "w.ckpt"
    RC.save_world(path, world)
    back = RC.load_world(path)
    assert [r.model_dump() for r in back.faiths] == [r.model_dump() for r in world.faiths]
    # A world pickled before the field existed.
    legacy = generate_world(seed=42)
    legacy.__dict__.pop("faiths")
    RC.save_world(tmp_path / "old.ckpt", legacy)
    old = RC.load_world(tmp_path / "old.ckpt")
    assert [(r.slot, r.founded_turn) for r in old.faiths] == [(b.faith_id, 0) for b in old.belief_registry]
