"""RS1 rules version 2 (PL2) without the native extension.

The same native stand-in as ``tests/test_apprenticeship.py`` (crew planner,
work registry, paid-work install and wealth transfers by stable id), driven
through the real livelihoods hooks. Version 2: attendance by presence in the
site's region; portable progress (a migrant transfers to the site of the region
they live in) that pauses on missed turns and ends only after a long absence;
training on the job (on the planned crew, or attached to it after it was
planned), so apprentices never displace the crew; the age rule; the useful-work
records; and version-1 states resuming under their own rules.
"""
from __future__ import annotations

import json
import math
import pickle
from types import SimpleNamespace

import pytest
from test_apprenticeship import (
    SETTLEMENT, SITE_REGION, FakeSim, _built, _qualify, _receipt, _seats, _site, _state, _turn, _with_firm, _world,
)

from chronicler import apprenticeship as A
from chronicler import livelihoods as L
from chronicler import workshops as W
from chronicler.apprenticeship_state import COUNTERS, ApprenticeshipState
from chronicler.cities_state import City
from chronicler.livelihoods_state import LivelihoodsState


@pytest.fixture
def quick(monkeypatch):
    monkeypatch.setattr(A, "SERVICE_TURNS", 100)
    monkeypatch.setattr(A, "COMPLETION_TURNS", 3)


def _two_sites(sim):
    """Site 0: city C1 in region 2 (rank 2, d = 0.4); site 1: city C2 in region 3 (rank 1, d = 0.2)."""
    world = _world(rank=2, rules=2)
    world.cities.cities.append(City(settlement_id=2, region=3, name="C2", founded_turn=0, founder=0, rank=1,
                                    size=5.0))
    return world


def _old(sim, *ids):
    """City farmers too old to be taken on (above the age rule for COMPLETION_TURNS >= 3),
    so the apprentices under test are the region's residents outside the city box."""
    for aid in ids or list(sim.people):
        sim.people[aid].age = 58
    return sim


def _record(world, aid):
    return next(a for a in _state(world).apprenticeships if a.agent_id == aid)


def _ended(world, aid):
    return next(a for a in _state(world).archive if a.agent_id == aid)


def _frame(world, site):
    return next(r for r in _state(world).frame if r.site == site)


# --- New states run version 2; the switch's records ------------------------------------


def test_new_states_run_version_2_and_snapshot_it():
    world = _world(rules=A.RULES_VERSION)
    state = _state(world)
    assert A.RULES_VERSION == 2 and state.rules_version == 2 and state.schema_version == 2
    assert state.graduates == [] and state.detached == []
    snap = A.snapshot_summary(world)
    assert (snap["schema_version"], snap["rules_version"], snap["stage"]) == (2, 2, "RS1")
    assert snap["parameters"]["long_absence_turns"] == A.MAX_GAP
    assert snap["parameters"]["max_entry_age"] == 60 - A.COMPLETION_TURNS
    assert snap["receipts"] is None and snap["detached"] is None


# --- Attendance by region and training on the job -------------------------------------


def test_region_residents_outside_the_city_attend_attached_without_displacing_the_crew(quick):
    world, sim = _world(rules=2), _old(FakeSim(range(1, 9)))    # eight city farmers: a full crew
    for aid in (20, 21):
        sim.add(aid, settlement=0, age=22)                       # in the region, outside the city box
    _built(world, sim)
    _qualify(world, sim, [7])
    registry_at_planning = []
    plan = sim.plan_workshop_crews

    def planned(requests, enlisted, turn=None, *, priority_ids=None):
        if turn is not None:
            registry_at_planning.append(list(sim.work_reservations(turn)))
        return plan(requests, enlisted, turn, priority_ids=priority_ids)

    sim.plan_workshop_crews = planned
    extended = {}
    extend = sim.extend_paid_work

    def checked(turn, rows):
        reg = {a: (c, f) for a, c, f in sim.work_reservations(turn)}
        assert all(reg[a] == (A.CATEGORY_APPRENTICE, A.APPRENTICE_FRACTION) for a, _ in rows)
        extended["rows"] = rows
        return extend(turn, rows)

    sim.extend_paid_work = checked
    _turn(world, sim)
    crew = world.livelihoods.workshops.frame[0].crew
    # The crew is planned exactly as before: nobody was reserved ahead of it.
    assert registry_at_planning == [[]] and crew == [7, 1, 2, 3, 4, 5, 6, 8]
    seats = _seats(world)
    assert set(seats) == {20, 21}
    assert all(s.outcome == "attended" and s.aboard == "attached" and s.mentor == 7 and s.new
               and s.share == A.APPRENTICE_FRACTION for s in seats.values())
    assert extended["rows"] == [(20, A.APPRENTICE_FRACTION), (21, A.APPRENTICE_FRACTION)]
    assert seats[20].income_forgone == pytest.approx(sim.income * A.APPRENTICE_FRACTION)
    r = _receipt(world)
    assert r.teaching_work == pytest.approx(A.TEACH_SHARE * 0.2 * 2)
    assert r.craft_work + r.upkeep_work + r.teaching_work == pytest.approx(r.crew_work)
    assert world.livelihoods.workshops.frame[0].allocated == pytest.approx(r.craft_work)
    record = _record(world, 20)
    assert (record.attended, record.attached, record.on_crew, record.first_site, record.entry_age) == (1, 1, 0, 0, 22)


def test_on_the_job_counts_only_with_a_qualified_member_aboard_and_a_missed_turn_pauses(quick, monkeypatch):
    monkeypatch.setattr(A, "COMPLETION_TURNS", 5)
    world, sim = _world(rules=2), FakeSim(range(1, 5))
    sim.people[3].age, sim.people[4].age = 21, 22                # youngest first
    _built(world, sim)
    _qualify(world, sim, [1])
    _turn(world, sim)
    crew = world.livelihoods.workshops.frame[0].crew
    seats = _seats(world)
    assert crew == [1, 2, 3, 4] and set(seats) == {3, 4}
    assert all(s.aboard == "crew" and s.share == 0.0 and s.mentor == 1 for s in seats.values())
    # Crew time is their training time: no apprentice reservation, nothing withheld, no stipend.
    assert sim.receipt is None and all(s.income_forgone is None and s.stipend_due == 0 for s in seats.values())
    assert _state(world).counters["apprentice_turns_on_crew"] == 2
    assert _receipt(world).teaching_work == pytest.approx(A.TEACH_SHARE * 0.2 * 2)
    # The mentor dies: they keep working on the crew, but no turn counts; the
    # apprenticeship pauses well beyond MAX_GAP and never ends for it.
    sim.people[1].alive = False
    for _ in range(A.MAX_GAP + 3):
        _turn(world, sim)
        assert {(s.outcome, s.reason) for s in _seats(world).values()} == {("missed", "no_mentor")}
        assert {3, 4} <= set(world.livelihoods.workshops.frame[0].crew)
    record = _record(world, 3)
    assert (record.attended, record.gap, record.absent) == (1, A.MAX_GAP + 3, 0)
    assert _state(world).counters.get("end_dropout", 0) == 0
    # A mentor aboard again: progress resumes where it paused.
    _qualify(world, sim, [2])
    _turn(world, sim)
    assert {s.outcome for s in _seats(world).values()} == {"attended"} and _record(world, 3).attended == 2
    assert _record(world, 3).gap == 0


def test_capacity_follows_the_qualified_members_aboard(quick):
    world, sim = _world(rules=2), _old(FakeSim(range(1, 13)))
    for aid in range(20, 26):
        sim.add(aid, settlement=0, age=20 + aid - 20)
    _built(world, sim)
    _qualify(world, sim, [7])
    _turn(world, sim)
    assert _receipt(world).seat_capacity == A.PER_MENTOR and sorted(_seats(world)) == [20, 21]
    _qualify(world, sim, [8])
    _turn(world, sim)
    seats = _seats(world)
    assert _receipt(world).seat_capacity == A.PER_SITE and sorted(seats) == [20, 21, 22, 23]
    assert [a for a, s in seats.items() if s.new] == [22, 23] and {s.mentor for s in seats.values()} == {7, 8}


# --- Portability, pause and long absence ---------------------------------------------------


def test_a_migrant_continues_at_the_site_of_the_new_region(quick, monkeypatch):
    monkeypatch.setattr(A, "COMPLETION_TURNS", 30)   # max entry age 30
    sim = FakeSim(range(1, 5))
    world = _two_sites(sim)
    for aid in range(21, 25):
        sim.add(aid, region=3, settlement=2)
    _old(sim)
    sim.add(30, settlement=0, age=20)
    _built(world, sim)
    assert [(s.site, s.region) for s in world.livelihoods.workshops.sites] == [(0, SITE_REGION), (1, 3)]
    _qualify(world, sim, [4])
    st = A._SiteTurn(1, 3, 2, "C2", 0.2, 8, 1.0, 0)
    for mentor in (23, 24):                                        # site 1: room to teach a newcomer
        assert A._grant(_state(world), mentor, world.turn - 1, st, "service", (3, 2))
    _turn(world, sim)
    assert _record(world, 30).site == 0 and _record(world, 30).attended == 1
    assert [a.agent_id for a in _state(world).apprenticeships] == [30]
    sim.people[30].region = 3                                      # migrates, outside C2's box too
    _turn(world, sim)
    seat = next(s for s in _frame(world, 1).seats if s.agent_id == 30)
    assert (seat.outcome, seat.aboard, seat.transferred_from) == ("attended", "attached", 0)
    record = _record(world, 30)
    assert (record.site, record.region, record.settlement_id, record.transfers, record.attended) == (1, 3, 2, 1, 2)
    assert record.first_site == 0 and _state(world).counters["transferred"] == 1
    # Away from every site region: absent, paused; back within MAX_GAP: continues.
    sim.people[30].region = 0
    for i in range(A.MAX_GAP):
        _turn(world, sim)
        seat = next(s for s in _frame(world, 1).seats if s.agent_id == 30)
        assert (seat.outcome, seat.reason, seat.aboard) == ("missed", "absent", None)
        assert _record(world, 30).absent == i + 1
    sim.people[30].region = 3
    _turn(world, sim)
    assert _record(world, 30).attended == 3 and _record(world, 30).absent == 0
    # A long absence (more than MAX_GAP turns) ends it.
    sim.people[30].region = 0
    for _ in range(A.MAX_GAP + 1):
        _turn(world, sim)
    ended = _ended(world, 30)
    assert (ended.ended_reason, ended.ended_turn, ended.attended) == ("long_absence", world.turn - 1, 3)
    assert next(s for s in _frame(world, 1).seats if s.agent_id == 30).ending == "long_absence"
    assert _state(world).counters["end_long_absence"] == 1


def test_a_full_site_refuses_a_transfer_and_that_counts_as_absence(quick, monkeypatch):
    monkeypatch.setattr(A, "COMPLETION_TURNS", 30)   # max entry age 30
    sim = FakeSim(range(1, 5))
    world = _two_sites(sim)
    for aid in range(21, 29):
        sim.add(aid, region=3, settlement=2)
    _old(sim, 1, 2, 3)
    sim.add(30, settlement=0, age=20)
    _built(world, sim)
    _qualify(world, sim, [4, 27, 28])                              # site 1 has two mentors: four places
    _turn(world, sim)
    assert len([a for a in _state(world).apprenticeships if a.site == 1]) == A.PER_SITE
    assert _record(world, 30).site == 0
    sim.people[30].region = 3
    for i in range(A.MAX_GAP + 1):
        _turn(world, sim)
        assert len([a for a in _state(world).apprenticeships if a.site == 1]) == A.PER_SITE
        if i < A.MAX_GAP:
            seat = next(s for s in _frame(world, 0).seats if s.agent_id == 30)
            assert (seat.outcome, seat.reason) == ("missed", "no_room") and _record(world, 30).site == 0
    assert _ended(world, 30).ended_reason == "long_absence"
    assert _state(world).counters["miss_no_room"] == A.MAX_GAP + 1


def test_unavailable_turns_pause_without_ending(quick, monkeypatch):
    monkeypatch.setattr(A, "COMPLETION_TURNS", 30)   # max entry age 30
    world, sim = _world(rules=2), _old(FakeSim(range(1, 5)))
    sim.add(30, settlement=0, age=20)
    _built(world, sim)
    _qualify(world, sim, [4])
    _turn(world, sim)
    sim.people[30].trip = True
    for _ in range(A.MAX_GAP + 2):
        _turn(world, sim)
        assert _seats(world)[30].reason == "unavailable"
    assert _record(world, 30).attended == 1 and _record(world, 30).absent == 0
    sim.people[30].trip = False
    _turn(world, sim)
    assert _seats(world)[30].outcome == "attended" and _record(world, 30).attended == 2


# --- Endings, closure and controller change ---------------------------------------------------


def test_death_occupation_army_and_death_in_the_tick_end_with_their_reason(quick, monkeypatch):
    monkeypatch.setattr(A, "COMPLETION_TURNS", 30)   # max entry age 30
    world, sim = _world(rules=2), _old(FakeSim(range(1, 5)))
    for aid, age in ((30, 20), (31, 21), (32, 22), (33, 23), (34, 24), (35, 25)):
        sim.add(aid, settlement=0, age=age)
    _built(world, sim)
    _qualify(world, sim, [3, 4])
    _turn(world, sim)
    assert sorted(a.agent_id for a in _state(world).apprenticeships) == [30, 31, 32, 33]
    sim.people[30].alive = False
    sim.people[31].occupation = 2
    world.war_state.armies = [SimpleNamespace(roster=[(32, 0)])]
    sim.die_in_tick = {33}
    turn = world.turn
    _turn(world, sim)
    ends = {a.agent_id: (a.ended_reason, a.ended_turn) for a in _state(world).archive}
    assert ends == {30: ("died", turn), 31: ("occupation_changed", turn), 32: ("remobilised", turn),
                    33: ("died", turn)}
    assert _ended(world, 33).attended == 1                       # the turn of the death does not count
    # The freed places are refilled from the region's remaining candidates.
    assert sorted(a.agent_id for a in _state(world).apprenticeships) == [34, 35]
    assert _record(world, 34).started_turn == turn


def test_site_closure_pauses_until_a_transfer_or_a_long_absence(quick, monkeypatch):
    monkeypatch.setattr(A, "COMPLETION_TURNS", 30)   # max entry age 30
    sim = FakeSim(range(1, 5))
    world = _two_sites(sim)
    for aid in range(21, 25):
        sim.add(aid, region=3, settlement=2)
    _old(sim)
    sim.add(30, settlement=0, age=20)
    sim.add(31, settlement=0, age=21)
    _built(world, sim)
    _qualify(world, sim, [4, 23, 24])
    _turn(world, sim)
    assert {_record(world, a).site for a in (30, 31)} == {0}
    world.cities.cities = [c for c in world.cities.cities if c.region != SITE_REGION]   # C1 falls
    _turn(world, sim)
    assert [s.site for s in world.livelihoods.workshops.sites] == [1]
    detached = {s.agent_id: (s.outcome, s.reason) for s in _state(world).detached}
    assert detached == {30: ("missed", "absent"), 31: ("missed", "absent")}
    assert _record(world, 30).site == 0 and _record(world, 30).absent == 1
    snap = A.snapshot_summary(world)
    assert [s["agent_id"] for s in snap["detached"]] == [30, 31]
    sim.people[31].region = 3                                    # moves to the other site's region
    _turn(world, sim)
    assert _record(world, 31).site == 1 and _record(world, 31).attended == 2
    for _ in range(A.MAX_GAP - 1):
        _turn(world, sim)
    assert _ended(world, 30).ended_reason == "long_absence" and _record(world, 31).absent == 0


def test_a_change_of_controller_keeps_apprenticeships_running(quick, monkeypatch):
    monkeypatch.setattr(A, "COMPLETION_TURNS", 30)   # max entry age 30
    world, sim = _world(rules=2), _old(FakeSim(range(1, 5)))
    sim.add(30, settlement=0, age=20)
    _built(world, sim)
    _qualify(world, sim, [4])
    _turn(world, sim)
    world.regions[SITE_REGION].controller = "Civ1"
    _turn(world, sim)
    event = _state(world).events[-1]
    assert event.kind == "conquest" and 30 in event.ids and event.detail == {"from": 0, "to": 1}
    assert _seats(world)[30].outcome == "attended" and _record(world, 30).attended == 2


# --- Who is taken on --------------------------------------------------------------------------


def test_youngest_first_and_nobody_who_would_reach_elder_age_before_completing(quick, monkeypatch):
    monkeypatch.setattr(A, "COMPLETION_TURNS", 10)
    world, sim = _world(rules=2), FakeSim(range(1, 3))
    for aid, age in ((30, 55), (31, 51), (32, 50), (33, 19), (34, 36)):
        sim.add(aid, settlement=0, age=age)
    _built(world, sim)
    _qualify(world, sim, [1, 2])
    _turn(world, sim)
    assert A.max_entry_age() == 50
    assert sorted(_seats(world)) == [32, 34]                     # 36 then 50; 51+ and minors excluded
    assert _receipt(world).candidates == 2


def test_crew_members_are_taken_on_before_other_residents_of_the_region(quick):
    world, sim = _world(rules=2), FakeSim(range(1, 5))
    sim.people[2].age, sim.people[3].age = 41, 33                 # crew members (city), older
    sim.people[1].age = 58                                        # too old to be taken on
    for aid, age in ((30, 20), (31, 21)):
        sim.add(aid, settlement=0, age=age)                       # younger, outside the city box
    _built(world, sim)
    _qualify(world, sim, [4, 1])
    _turn(world, sim)
    seats = _seats(world)
    # On the crew first (youngest first), then attached residents: 3, 2, then 30, 31.
    assert list(seats) == [3, 2, 30, 31]
    assert [seats[a].aboard for a in (3, 2, 30, 31)] == ["crew", "crew", "attached", "attached"]


def test_veterans_come_first_in_version_2(quick, monkeypatch):
    from chronicler import veteran_reintegration as VR
    world, sim = _world(rules=2), _old(FakeSim(range(1, 3)))
    for aid, age in ((30, 20), (31, 21), (32, 40)):
        sim.add(aid, settlement=0, age=age)
    VR.set_veteran_reintegration_enabled(world, True, args=None)
    for hook in ("prepare_phase2", "finish_phase2", "rollback_phase2", "rollback_agent_tick", "phase10",
                 "on_pool_reset"):
        if hasattr(VR, hook):
            monkeypatch.delattr(VR, hook)
    monkeypatch.setattr(VR, "priority_ids", lambda w, region: [32] if region == SITE_REGION else [])
    notes = []
    monkeypatch.setattr(VR, "note_outcome", lambda w, aid, kind, *, turn, detail=None: notes.append((aid, kind)))
    _built(world, sim)
    _qualify(world, sim, [1])
    _turn(world, sim)
    seats = _seats(world)
    assert list(seats) == [32, 30] and seats[32].veteran and not seats[30].veteran
    assert notes == [(32, "placed:apprentice"), (30, "placed:apprentice")]


# --- Completion, the control and useful work --------------------------------------------------


def _graduating(mode):
    world, sim = _world(mode=mode, rules=2), FakeSim(range(1, 5))
    sim.people[3].age, sim.people[4].age = 21, 22
    _built(world, sim)
    _qualify(world, sim, [1])
    for _ in range(A.COMPLETION_TURNS):
        _turn(world, sim)
    return world, sim


def test_completion_grants_in_train_only_and_graduates_keep_the_site(quick):
    runs = {mode: _graduating(mode) for mode in ("train", "no_qualification")}
    for mode, (world, _sim) in runs.items():
        state = _state(world)
        done = [a for a in state.archive if a.ended_reason == "completed"]
        assert [a.agent_id for a in done] == [3, 4] and _receipt(world).completed == [3, 4]
        assert [(g.agent_id, g.granted) for g in state.graduates] == [(3, mode == "train"), (4, mode == "train")]
        held = {q.agent_id for q in state.qualifications if q.via == "apprenticeship"}
        assert held == ({3, 4} if mode == "train" else set())
    a, b = (_state(runs[m][0]) for m in ("train", "no_qualification"))
    for key in ("apprentice_turns_attended", "apprentice_turns_on_crew", "wear", "upkeep_offset", "enrolled",
                "teaching_work", "income_forgone", "stipends_due"):
        assert a.counters.get(key) == b.counters.get(key), key
    # The next operating turn: graduates are on the crew in both arms; only
    # trained graduates are qualified, keep the site and teach.
    for world, sim in runs.values():
        _turn(world, sim)
    tw, nw = runs["train"][0], runs["no_qualification"][0]
    t, n = _receipt(tw), _receipt(nw)
    assert t.graduates_on_crew == [3, 4] and n.graduates_on_crew == [3, 4]
    assert t.qualified_on_crew == [1, 3, 4] and n.qualified_on_crew == [1]
    assert t.covered and n.covered and t.full_offset and not n.full_offset
    # d = 0.2: each qualified member offsets up to 0.25 * 0.2 * 0.2 = 0.01 of the 0.02 wear.
    assert t.offset_by_via == pytest.approx({"service": 0.01, "apprenticeship": 0.01})
    assert t.offset_by_graduates == pytest.approx(0.01) and n.offset_by_graduates == 0.0
    assert n.offset_by_via == pytest.approx({"service": 0.01, "apprenticeship": 0.0})
    ts, ns = _state(tw), _state(nw)
    assert ts.counters["graduate_crew_turns"] == ns.counters["graduate_crew_turns"] == 2
    assert ts.counters["full_offset_site_turns"] == 1 and ns.counters.get("full_offset_site_turns", 0) == 0
    assert {g.agent_id: (g.crew_turns, g.last_crew_turn) for g in ts.graduates} == {
        3: (1, tw.turn - 1), 4: (1, tw.turn - 1)}
    assert sum(g.upkeep_offset for g in ts.graduates) == pytest.approx(ts.counters["upkeep_offset_graduates"])
    # A graduate's death drops the record and is counted.
    sim = runs["train"][1]
    sim.people[3].alive = False
    _turn(tw, sim)
    assert [g.agent_id for g in ts.graduates] == [4] and ts.counters["graduates_died"] == 1


def test_stipends_are_paid_for_attached_time_only(quick):
    world, sim = _world(rules=2), _old(FakeSim(range(1, 4)), 2)
    sim.people[3].age = 21
    sim.add(30, settlement=0, age=20)
    _built(world, sim)
    _qualify(world, sim, [1])
    _with_firm(world, cash=100_000)
    _turn(world, sim)
    seats = _seats(world)
    due = math.floor(A.APPRENTICE_FRACTION * A.STIPEND_PER_WORK + 0.5)
    assert (seats[30].aboard, seats[30].stipend_due, seats[30].stipend_paid, seats[30].stipend_status) == (
        "attached", due, due, "paid")
    assert (seats[3].aboard, seats[3].stipend_due, seats[3].stipend_paid) == ("crew", 0, 0)
    stipends = [t for t in sim.transfers if t[1] == A.PURPOSE_APPRENTICE_STIPEND]
    assert stipends == [(world.turn - 1, A.PURPOSE_APPRENTICE_STIPEND, 0, [(30, due)])]


# --- Failure, interactions and exactly once -----------------------------------------------------


def test_a_failed_tick_keeps_nothing_and_releases_the_attached_share(quick):
    world, sim = _world(rules=2), _old(FakeSim(range(1, 4)))
    sim.add(30, settlement=0, age=20)
    _built(world, sim)
    _qualify(world, sim, [1])
    _turn(world, sim)
    before = _state(world).model_dump_json()
    sim.fail_tick = True
    with pytest.raises(RuntimeError, match="native tick failed"):
        _turn(world, sim)
    assert sim.paid is None and sim.cancelled >= 1 and _state(world)._pending is None
    assert _state(world).model_dump_json() == before


def test_seated_mentors_protects_the_mentors_present_apprentices_rely_on(quick):
    world, sim = _world(rules=2), FakeSim((2, 4))
    sim.add(30, settlement=0, age=20)
    _built(world, sim)
    _qualify(world, sim, [2, 4])
    _turn(world, sim)
    A.before_crews(world, sim, [(0, SITE_REGION, SETTLEMENT, 0.2, 8)])
    assert A.seated_mentors(world) == frozenset({2})
    _state(world)._pending = None


# --- Persistence: exact round trips and version-1 states -----------------------------------------


def test_a_version_2_state_resumes_exactly_inside_live_apprenticeships(quick, monkeypatch):
    monkeypatch.setattr(A, "COMPLETION_TURNS", 6)

    def build():
        sim = FakeSim(range(1, 5))
        world = _two_sites(sim)
        for aid in range(21, 25):
            sim.add(aid, region=3, settlement=2)
        _old(sim, 1, 2, 21, 22, 23)
        sim.add(30, settlement=0, age=20)
        sim.people[3].age = 21
        _built(world, sim)
        _qualify(world, sim, [4, 24])
        for _ in range(2):
            _turn(world, sim)
        sim.people[30].region = 3
        return world, sim

    straight, sim_a = build()
    for _ in range(6):
        _turn(straight, sim_a)
    resumed, sim_b = build()
    assert resumed.livelihoods.apprenticeship.apprenticeships
    text = resumed.livelihoods.model_dump_json()
    restored = LivelihoodsState.model_validate_json(text)
    assert restored.apprenticeship.rules_version == 2
    resumed.livelihoods = pickle.loads(pickle.dumps(restored))
    assert resumed.livelihoods.model_dump_json() == text
    L.bind_native_pool(resumed, SimpleNamespace(_sim=sim_b), reset=False)
    for _ in range(6):
        _turn(resumed, sim_b)
    a, b = straight.livelihoods.apprenticeship, resumed.livelihoods.apprenticeship
    assert json.loads(a.model_dump_json()) == json.loads(b.model_dump_json())
    assert a.counters["transferred"] == 1 and a.counters["completions"] >= 2 and a.graduates


_V2_RECORD_FIELDS = {
    "Apprenticeship": ("absent", "first_site", "entry_age", "transfers", "on_crew", "attached"),
    "Seat": ("aboard", "transferred_from"),
    "SiteReceipt": ("graduates_on_crew", "covered", "full_offset", "offset_by_via", "offset_by_graduates"),
    "ApprenticeshipState": ("graduates", "detached"),
}


def _strip_v2_fields(obj, seen=None):
    """Emulate an object graph pickled before PL2: drop the fields it added."""
    seen = set() if seen is None else seen
    if id(obj) in seen:
        return
    seen.add(id(obj))
    if isinstance(obj, list):
        for item in obj:
            _strip_v2_fields(item, seen)
        return
    names = _V2_RECORD_FIELDS.get(type(obj).__name__)
    if names is None:
        return
    for name in names:
        assert obj.__dict__.pop(name) is None
    for value in list(obj.__dict__.values()):
        _strip_v2_fields(value, seen)


def test_a_version_1_state_resumes_under_its_own_rules_and_serializes_as_before(monkeypatch):
    monkeypatch.setattr(A, "SERVICE_TURNS", 3)
    monkeypatch.setattr(A, "COMPLETION_TURNS", 6)

    def build():
        world, sim = _world(rules=1), FakeSim(range(1, 13))
        _built(world, sim)
        _qualify(world, sim, [12])
        for _ in range(3):
            _turn(world, sim)
        return world, sim

    straight, sim_a = build()
    for _ in range(5):
        _turn(straight, sim_a)
    resumed, sim_b = build()
    state = resumed.livelihoods.apprenticeship
    assert state.rules_version == 1 and state.apprenticeships and state.frame
    text = resumed.livelihoods.model_dump_json()
    dumped = json.loads(text)["apprenticeship"]
    # A version-1 state serializes exactly as before PL2: no version-2 key anywhere.
    assert dumped["schema_version"] == 1
    flat = json.dumps(dumped)
    for names in _V2_RECORD_FIELDS.values():
        for name in names:
            assert f'"{name}"' not in flat, name
    # An old pickle (without the new fields) restores exactly and resumes under version 1.
    _strip_v2_fields(state)
    blob = pickle.dumps(resumed.livelihoods)
    resumed.livelihoods = pickle.loads(blob)
    assert resumed.livelihoods.model_dump_json() == text
    assert resumed.livelihoods.apprenticeship.rules_version == 1
    # Its JSON form loads as version 1 too.
    assert LivelihoodsState.model_validate_json(text).apprenticeship.rules_version == 1
    L.bind_native_pool(resumed, SimpleNamespace(_sim=sim_b), reset=False)
    for _ in range(5):
        _turn(resumed, sim_b)
    a, b = straight.livelihoods.apprenticeship, resumed.livelihoods.apprenticeship
    assert json.loads(a.model_dump_json()) == json.loads(b.model_dump_json())
    assert b.rules_version == 1 and A.snapshot_summary(resumed)["schema_version"] == 1
    # Version-1 records: exclusive seats, never on the crew, the v1 snapshot keys.
    assert all(s.aboard is None for r in b.frame for s in r.seats)
    assert "rules_version" not in A.snapshot_summary(resumed)


def test_inconsistent_or_unknown_versions_are_refused():
    with pytest.raises(ValueError):
        ApprenticeshipState.model_validate({"schema_version": 1, "graduates": []})
    with pytest.raises(ValueError):
        ApprenticeshipState.model_validate({"schema_version": 3})
    assert ApprenticeshipState.model_validate({"schema_version": 1}).rules_version == 1


def test_the_v2_snapshot_is_dated_bounded_and_json_safe(quick):
    world, sim = _world(rules=2), FakeSim(range(1, 4))
    sim.add(30, settlement=0, age=20)
    _built(world, sim)
    _qualify(world, sim, [1])
    _turn(world, sim)
    snap = L.livelihoods_snapshot_fields(world)["livelihoods"]["apprenticeship"]
    assert snap["schema_version"] == 2 and snap["source_turn"] == world.turn - 1
    assert snap["receipts"][0]["covered"] is True and snap["detached"] == []
    assert set(snap["counters"]) <= set(COUNTERS)
    assert json.loads(json.dumps(snap)) == snap
    world.turn += 1
    stale = A.snapshot_summary(world)
    assert stale["receipts"] is None and stale["detached"] is None and stale["continuity"] is None


def test_feature_off_has_no_state_and_the_reference_crew_is_unchanged():
    world, sim = _world(rules=2), FakeSim(range(1, 9))
    world.livelihoods.apprenticeship = None
    for _ in range(8):
        _turn(world, sim)
    assert world.livelihoods.apprenticeship is None and world.livelihoods.operating_wear is None
    assert "apprenticeship" not in L.livelihoods_snapshot_fields(world).get("livelihoods", {})
    assert all(plan["priority"] == [] for plan in sim.plans)
    assert _site(world).condition == 1.0 and W.OPERATE_CONDITION == 0.5
