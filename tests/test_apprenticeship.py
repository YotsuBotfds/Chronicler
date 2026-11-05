"""RS1 apprenticeship and skill continuity without the native extension.

A stand-in simulator keeps a small pool of people by stable id and the native
contracts the package relies on: the crew planner (priority ids, exclusions,
read-only without a turn), the shared work registry (all or none, one holder
per person and turn), the paid-work install/extension consumed once by the
wealth phase, and stable-id wealth transfers applied once per key. Everything
else is the real L1 workshop, L6a payroll and RS1 code, driven through the
livelihoods phase hooks in their production order.
"""
from __future__ import annotations

import json
import math
import pickle
from types import SimpleNamespace

import pyarrow as pa
import pytest

from chronicler import apprenticeship as A
from chronicler import livelihoods as L
from chronicler import workshop_payroll as P
from chronicler import workshops as W
from chronicler.apprenticeship_state import COUNTERS
from chronicler.cities_state import City, CityState
from chronicler.livelihoods_state import LivelihoodsState
from chronicler.workshop_payroll_state import WorkshopFirm, WorkshopPayrollState
from chronicler.workshops_state import WorkshopState

SITE_REGION = 2
SETTLEMENT = 1
MAX_WEALTH = 100.0


class Person:
    def __init__(self, aid, region=SITE_REGION, settlement=SETTLEMENT, occupation=0, age=30, wealth=10.0):
        self.id, self.region, self.settlement, self.occupation, self.age = aid, region, settlement, occupation, age
        self.wealth, self.trip, self.alive = wealth, False, True


class FakeSim:
    """Native stand-in with the contracts of ``workshop_work.rs`` and ``wealth_transfer.rs``."""

    def __init__(self, ids=range(1, 13), income=0.4):
        self.people = {aid: Person(aid) for aid in ids}
        self.registry: list[tuple[int, int, int, float]] = []
        self.health: set[int] = set()
        self.income = income
        self.paid = self.receipt = self.inputs = None
        self.keys: list[tuple[int, int, int]] = []
        self.transfers: list[tuple[int, int, int, list]] = []
        self.die_in_tick: set[int] = set()
        self.fail_tick = False
        self.cancelled = 0
        self.plans: list[dict] = []

    def add(self, aid, **kwargs):
        self.people[aid] = Person(aid, **kwargs)

    def _alive(self):
        return [p for _, p in sorted(self.people.items()) if p.alive]

    def get_snapshot(self):
        ps = self._alive()
        return pa.record_batch({
            "id": pa.array([p.id for p in ps], pa.uint32()), "region": pa.array([p.region for p in ps], pa.uint16()),
            "settlement_id": pa.array([p.settlement for p in ps], pa.uint16()),
            "occupation": pa.array([p.occupation for p in ps], pa.uint8()),
            "age": pa.array([p.age for p in ps], pa.uint16()),
            "wealth": pa.array([p.wealth for p in ps], pa.float32())})

    def _holders(self, turn):
        return {r[1] for r in self.registry if r[0] == turn} | self.health

    def plan_workshop_crews(self, requests, enlisted, turn=None, *, priority_ids=None):
        priority = list(priority_ids or [])
        if len(set(priority)) != len(priority):
            raise ValueError("duplicate agent in crew priority")
        rank = {aid: i for i, aid in enumerate(priority)}
        assigned = set(self.health) | ({r[1] for r in self.registry if r[0] == turn} if turn is not None else set())
        enlisted = set(enlisted)
        rows, crews = [], []
        for site, region, settlement, d, cap in requests:
            residents = [p for p in self._alive() if p.occupation == 0 and p.age >= 20
                         and p.region == region and p.settlement == settlement]
            trip = sum(p.trip for p in residents)
            army = sum(1 for p in residents if not p.trip and p.id in enlisted)
            held = sum(1 for p in residents if not p.trip and p.id not in enlisted and p.id in assigned)
            cands = sorted((p.id for p in residents if not p.trip and p.id not in enlisted and p.id not in assigned),
                           key=lambda a: (rank.get(a, 10**9), a))
            crew = []
            for aid in cands[:cap]:
                assigned.add(aid)
                crew.append(aid)
            rows.append((site, region, settlement, len(residents), trip, army, held, len(cands), crew,
                         [30] * len(crew), d * len(crew)))
            crews.extend((aid, d) for aid in crew)
        self.plans.append({"turn": turn, "priority": priority, "crews": [r[8] for r in rows]})
        if turn is not None:
            self.reserve_work(turn, 0, crews)
        return rows

    def reserve_work(self, turn, category, rows):
        if category > 3:
            raise ValueError("unknown work reservation category")
        held, seen = self._holders(turn), set()
        for aid, fraction in rows:
            if not 0.0 < fraction <= 1.0:
                raise ValueError("work reservation fraction must be in (0, 1]")
            if aid in seen:
                raise ValueError("duplicate agent in work reservation")
            seen.add(aid)
            person = self.people.get(aid)
            if person is None or not person.alive:
                raise ValueError("work reservation names no living agent")
            if aid in held:
                raise ValueError("agent already holds work this turn")
        self.registry = [r for r in self.registry if r[0] == turn] + [(turn, a, category, f) for a, f in rows]

    def work_reservations(self, turn):
        return [(a, c, f) for t, a, c, f in self.registry if t == turn]

    def _check_paid(self, turn, rows):
        for aid, share in rows:
            reserved = sum(f for t, a, _c, f in self.registry if t == turn and a == aid)
            if not 0.0 < share <= 1.0 or share > reserved + 1e-6:
                raise ValueError("paid work exceeds the agent's work reservation this turn")

    def install_paid_work(self, turn, rows):
        if self.paid is not None:
            raise ValueError("paid work share already pending")
        self._check_paid(turn, rows)
        self.paid = (turn, dict(rows))

    def extend_paid_work(self, turn, rows):
        if self.paid is not None and self.paid[0] != turn:
            raise ValueError("pending paid work belongs to another turn")
        current = dict(self.paid[1]) if self.paid is not None else {}
        if any(aid in current for aid, _ in rows):
            raise ValueError("agent already has a pending paid-work share")
        self._check_paid(turn, rows)
        current.update(rows)
        self.paid = (turn, current)

    def cancel_paid_work(self):
        had = self.paid is not None
        self.paid = None
        self.cancelled += had
        return had

    def tick(self, *args, **kwargs):
        if self.fail_tick:
            raise RuntimeError("native tick failed")
        ids = [r[1] for r in self.registry]
        assert len(ids) == len(set(ids)), "the native tick refuses a work overlap"
        for aid in self.die_in_tick:
            self.people[aid].alive = False
        self.die_in_tick = set()
        if self.paid is not None:
            turn, rows = self.paid
            out = []
            for aid, share in sorted(rows.items()):
                person = self.people[aid]
                if not person.alive:
                    continue
                out.append((aid, share, self.income, self.income * share))
                person.wealth = min(MAX_WEALTH, person.wealth + self.income * (1 - share))
            self.receipt, self.paid = (turn, out), None
        self.registry = []
        return []

    def take_paid_work_receipt(self):
        out, self.receipt = self.receipt, None
        return out

    def transfer_wealth(self, turn, purpose, batch, rows):
        if (turn, purpose, batch) in self.keys:
            raise ValueError("wealth transfer already applied for this turn, purpose and batch")
        if len({aid for aid, _ in rows}) != len(rows):
            raise ValueError("duplicate agent in wealth transfer")
        self.keys.append((turn, purpose, batch))
        self.transfers.append((turn, purpose, batch, list(rows)))
        out = []
        for aid, amount in rows:
            person = self.people.get(aid)
            if person is None or not person.alive:
                out.append((aid, amount, 0, amount, 2))
                continue
            applied = min(amount, math.floor((MAX_WEALTH - person.wealth) * 1000))
            person.wealth += applied / 1000
            out.append((aid, amount, applied, amount - applied, 0 if applied == amount else 1))
        return out

    def take_craft_inputs(self):
        out, self.inputs = self.inputs, None
        return out


def _world(mode=None, rank=1, treasury=10_000):
    civs = [SimpleNamespace(name=f"Civ{i}", treasury=treasury) for i in range(2)]
    world = SimpleNamespace(
        turn=1, agent_mode="hybrid", civilizations=civs,
        regions=[SimpleNamespace(name=f"R{i}", controller="Civ0", stockpile=SimpleNamespace(goods={"crafts": 0.0}))
                 for i in range(4)],
        cities=CityState(cities=[City(settlement_id=SETTLEMENT, region=SITE_REGION, name="C1", founded_turn=0,
                                      founder=0, rank=rank, size=10.0)]),
        livelihoods=LivelihoodsState(), war_state=SimpleNamespace(armies=[]), scholarship=None)
    world.livelihoods.workshops = WorkshopState(mode="operate")
    A.set_apprenticeship_enabled(world, True, args=SimpleNamespace(apprenticeship_mode=mode))
    return world


def _batch(n=4):
    return pa.record_batch({"region_id": pa.array(range(n), pa.uint16()),
                            "craft_raw_demand": pa.array([1.5] * n, pa.float32())})


def _turn(world, sim, output=0.0, fail=None):
    """One turn through the livelihoods hooks in production order."""
    bridge = SimpleNamespace(_sim=sim)
    econ = SimpleNamespace(craft_output={r.name: output for r in world.regions})
    try:
        batch = L.prepare_phase2(world, _batch(len(world.regions)), bridge, None, acc=None)
        sim.inputs = [[0.0] * 9 for _ in world.regions]
        if fail == "phase2":
            raise RuntimeError("economy tick failed")
        L.finish_phase2(world, econ, bridge, acc=None)
    except Exception:
        L.rollback_phase2(world)
        raise
    L.wrap_agent_tick(world, bridge, sim.tick, econ)()
    L.phase10_before_reserves(world, acc=None, economy_result=econ, agent_bridge=bridge)
    L.phase10(world, acc=None, economy_result=econ, agent_bridge=bridge)
    world.turn += 1
    return batch


def _state(world):
    return world.livelihoods.apprenticeship


def _site(world):
    return world.livelihoods.workshops.sites[0]


def _receipt(world):
    return _state(world).frame[0]


def _built(world, sim):
    for _ in range(W.CONSTRUCTION_COST // W.INSTALLMENT):
        _turn(world, sim)
    assert _site(world).asset == "open"


def _qualify(world, sim, ids):
    """Grant service qualifications directly (as a completed service would)."""
    st = A._SiteTurn(0, SITE_REGION, SETTLEMENT, "C1", 0.2, 8, 1.0, 0)
    for aid in ids:
        assert A._grant(_state(world), aid, world.turn - 1, st, "service", (SITE_REGION, SETTLEMENT))


def _seats(world):
    return {s.agent_id: s for s in _receipt(world).seats}


@pytest.fixture
def quick(monkeypatch):
    monkeypatch.setattr(A, "SERVICE_TURNS", 3)
    monkeypatch.setattr(A, "COMPLETION_TURNS", 3)


# --- Service qualification and the qualification record -------------------------------


def test_service_counts_only_operating_crew_turns_and_qualifies_for_life(quick):
    world, sim = _world(), FakeSim(range(1, 4))
    _built(world, sim)
    state = _state(world)
    # Construction turns are not service.
    assert state.qualifications == [] and state.counters.get("crew_turns_served", 0) == 0
    assert state.service == []
    for _ in range(2):
        _turn(world, sim)
    assert [(r.agent_id, r.crew_turns) for r in state.service] == [(1, 2), (2, 2), (3, 2)]
    _turn(world, sim)
    assert [q.agent_id for q in state.qualifications] == [1, 2, 3] and state.service == []
    q = state.qualifications[0]
    assert (q.via, q.earned_turn, q.site, q.settlement_id, q.region) == (
        "service", world.turn - 1, 0, SETTLEMENT, SITE_REGION)
    assert _receipt(world).service_qualified == [1, 2, 3]
    # It travels with the person: a migrant is qualified where they live now.
    sim.people[2].region, sim.people[2].settlement = 3, 9
    _turn(world, sim)
    assert A.qualified_ids(world, SITE_REGION) == [1, 3] and A.qualified_ids(world, 3) == [2]
    assert next(q for q in state.qualifications if q.agent_id == 2).seen_region == 3
    # A death retires the record (dated); nothing else is granted or kept.
    sim.people[3].alive = False
    _turn(world, sim)
    assert [q.agent_id for q in state.qualifications] == [1, 2]
    assert [(q.agent_id, q.retired_reason, q.retired_turn) for q in state.retired] == [(3, "died", world.turn - 1)]
    assert A.qualified_ids(world, SITE_REGION) == [1]


def test_service_is_kept_in_both_modes_and_never_touches_skill(quick):
    for mode in ("train", "no_qualification"):
        world, sim = _world(mode=mode), FakeSim(range(1, 3))
        _built(world, sim)
        for _ in range(3):
            _turn(world, sim)
        assert [q.via for q in _state(world).qualifications] == ["service", "service"], mode
        assert not hasattr(sim, "skills")


# --- Wear, upkeep and crew time ----------------------------------------------------


def test_unqualified_operating_site_wears_and_qualified_upkeep_offsets_within_crew_time():
    world, sim = _world(rank=1), FakeSim(range(1, 5))        # rank 1: d = 0.2
    _built(world, sim)
    site = _site(world)
    _turn(world, sim)
    r, w = _receipt(world), world.livelihoods.workshops.frame[0]
    assert r.operating and r.qualified_on_crew == [] and r.upkeep_work == 0.0
    assert site.condition == pytest.approx(1.0 - A.OPERATING_WEAR) and r.net_wear == A.OPERATING_WEAR
    assert w.allocated == pytest.approx(w.work_available) and r.craft_work == w.allocated
    # One qualified crew member: UPKEEP_SHARE of d, offsetting part of the wear.
    _qualify(world, sim, [3])
    before = site.condition
    _turn(world, sim)
    r, w = _receipt(world), world.livelihoods.workshops.frame[0]
    assert sim.plans[-1]["priority"][0] == 3 and w.crew[0] == 3          # qualified first
    assert r.qualified_on_crew == [3] and r.upkeep_work == pytest.approx(A.UPKEEP_SHARE * 0.2)
    assert r.upkeep_offset == pytest.approx(A.UPKEEP_SHARE * 0.2 * A.WEAR_PER_UPKEEP_WORK)
    assert site.condition == pytest.approx(before - A.OPERATING_WEAR + r.upkeep_offset)
    # Crew time is counted once: craft + upkeep + teaching = the crew's diverted time.
    assert r.craft_work + r.upkeep_work + r.teaching_work == pytest.approx(r.crew_work)
    assert w.allocated == r.craft_work and w.craft_ceiling == pytest.approx(W.K_RAW_PER_WORK * r.craft_work)
    # Two qualified: the wear is fully offset and upkeep never exceeds what it needs.
    _qualify(world, sim, [4])
    before = site.condition
    _turn(world, sim)
    r = _receipt(world)
    assert r.upkeep_offset == pytest.approx(A.OPERATING_WEAR) and r.net_wear == 0.0
    assert r.upkeep_work == pytest.approx(A.OPERATING_WEAR / A.WEAR_PER_UPKEEP_WORK)
    assert site.condition == pytest.approx(before)
    # Many qualified: still only the needed upkeep; condition never rises.
    _qualify(world, sim, [1, 2])
    _turn(world, sim)
    r = _receipt(world)
    assert r.upkeep_work == pytest.approx(A.OPERATING_WEAR / A.WEAR_PER_UPKEEP_WORK)
    assert site.condition == pytest.approx(before)


def test_a_worn_site_stops_until_repaired_by_the_lump_or_rs2(monkeypatch):
    world, sim = _world(), FakeSim(range(1, 4))
    _built(world, sim)
    site = _site(world)
    site.condition = W.OPERATE_CONDITION + 0.01
    _turn(world, sim)
    assert site.condition < W.OPERATE_CONDITION
    # The legacy lump repairs it (RS2 off) and it operates again.
    _turn(world, sim)
    assert world.livelihoods.workshops.frame[0].paid.get("repair") == W.REPAIR_COST
    assert site.condition == pytest.approx(1.0 - A.OPERATING_WEAR) and _receipt(world).operating
    # With the lump disallowed (RS2 owns repair) a worn site stays shut and seats nobody.
    from chronicler import repair_projects as RP
    site.condition = 0.3
    monkeypatch.setattr(W, "_legacy_repair_allowed", lambda w: False)
    _qualify(world, sim, [1])
    _turn(world, sim)
    assert not _receipt(world).operating and site.condition == 0.3 and _receipt(world).seat_capacity == 0
    assert RP.legacy_workshop_repair_allowed(world) is True       # the RS0 stub itself is untouched


# --- Mentors, apprentices, attendance and costs --------------------------------------


def test_mentors_seat_apprentices_who_are_never_crew_and_pay_with_their_time(quick):
    world, sim = _world(), FakeSim(range(1, 13))
    _built(world, sim)
    _qualify(world, sim, [7])                 # one mentor: PER_MENTOR seats
    _turn(world, sim)
    r = _receipt(world)
    seats = _seats(world)
    assert r.seat_capacity == A.PER_MENTOR and r.mentors == [7]
    assert [aid for aid, s in seats.items() if s.new] == [1, 2]          # ascending id
    assert all(s.outcome == "attended" and s.mentor == 7 and s.share == A.APPRENTICE_FRACTION
               for s in seats.values())
    crew = set(world.livelihoods.workshops.frame[0].crew)
    assert 7 in crew and not crew & set(seats)                           # never crew and apprentice
    assert r.teaching_work == pytest.approx(A.TEACH_SHARE * 0.2 * 2)
    # The income share was withheld once, by the shared receipt.
    assert seats[1].income_forgone == pytest.approx(sim.income * A.APPRENTICE_FRACTION)
    assert _state(world).counters["income_forgone"] == pytest.approx(2 * sim.income * A.APPRENTICE_FRACTION)
    # Without payroll the time is unpaid.
    assert r.stipend_status == "no_payroll" and seats[1].stipend_paid == 0 and sim.keys == []
    # Two mentors: up to PER_SITE open, continuing apprentices keep their seats first.
    _qualify(world, sim, [8])
    _turn(world, sim)
    seats = _seats(world)
    assert _receipt(world).seat_capacity == A.PER_SITE
    assert sorted(seats) == [1, 2, 3, 4] and [a for a, s in seats.items() if s.new] == [3, 4]
    assert {s.mentor for s in seats.values()} == {7, 8}
    assert len(_state(world).apprenticeships) == 4


def test_registry_and_paid_work_hold_each_person_once(quick):
    world, sim = _world(), FakeSim(range(1, 13))
    _built(world, sim)
    _qualify(world, sim, [9, 10])
    seen = {}
    original = sim.extend_paid_work

    def extend(turn, rows):
        reg = sim.work_reservations(turn)
        ids = [a for a, _c, _f in reg]
        assert len(ids) == len(set(ids))
        apprentices = {a: f for a, c, f in reg if c == A.CATEGORY_APPRENTICE}
        assert {a for a, _ in rows} <= set(apprentices)
        assert all(f == A.APPRENTICE_FRACTION for f in apprentices.values())
        seen["rows"] = rows
        return original(turn, rows)

    sim.extend_paid_work = extend
    _turn(world, sim)
    assert [a for a, _ in seen["rows"]] == [1, 2, 3, 4]
    # An id with a pending share (here: if a crew member were listed) is refused natively.
    sim.reserve_work(world.turn, 0, [(5, 0.2)])
    sim.install_paid_work(world.turn, [(5, 0.2)])
    with pytest.raises(ValueError, match="already has"):
        original(world.turn, [(5, 0.2)])


def test_veterans_come_first_and_their_placement_is_reported(quick, monkeypatch):
    from chronicler import veteran_reintegration as VR
    world, sim = _world(), FakeSim(range(1, 13))
    VR.set_veteran_reintegration_enabled(world, True, args=None)
    # Only the cross-lane seam (priority_ids, note_outcome) is under test: RS3's
    # own turn hooks need a native snapshot (tests/test_veteran_reintegration*.py).
    for hook in ("prepare_phase2", "finish_phase2", "rollback_phase2", "rollback_agent_tick", "phase10",
                 "on_pool_reset"):
        if hasattr(VR, hook):
            monkeypatch.delattr(VR, hook)
    monkeypatch.setattr(VR, "priority_ids", lambda w, region: [11, 4] if region == SITE_REGION else [])
    notes = []
    monkeypatch.setattr(VR, "note_outcome", lambda w, aid, kind, *, turn, detail=None: notes.append((aid, kind, turn)))
    _built(world, sim)
    _qualify(world, sim, [12])
    _turn(world, sim)
    seats = _seats(world)
    assert list(seats) == [11, 4] and all(s.veteran for s in seats.values())
    assert notes == [(11, "placed:apprentice", world.turn - 1), (4, "placed:apprentice", world.turn - 1)]
    assert _state(world).counters["veterans_enrolled"] == 2


def test_completion_grants_in_train_and_not_in_the_control_with_identical_costs(quick):
    runs = {}
    for mode in ("train", "no_qualification"):
        world, sim = _world(mode=mode), FakeSim(range(1, 13))
        _built(world, sim)
        _qualify(world, sim, [12])
        for _ in range(A.COMPLETION_TURNS):
            _turn(world, sim)
        runs[mode] = (world, sim)
    for mode, (world, sim) in runs.items():
        state = _state(world)
        done = [a for a in state.archive if a.ended_reason == "completed"]
        assert [a.agent_id for a in done] == [1, 2] and all(a.attended == A.COMPLETION_TURNS for a in done)
        assert _receipt(world).completed == [1, 2]
        held = {q.agent_id for q in state.qualifications if q.via == "apprenticeship"}
        if mode == "train":
            assert all(a.granted for a in done) and held == {1, 2}
        else:
            assert not any(a.granted for a in done) and held == set()
    a, b = (_state(runs[m][0]) for m in ("train", "no_qualification"))
    # Same attendance, income withheld and wear in both modes.
    for key in ("apprentice_turns_attended", "income_forgone", "wear", "upkeep_offset", "enrolled"):
        assert a.counters[key] == b.counters[key], key
    assert _site(runs["train"][0]).condition == _site(runs["no_qualification"][0]).condition
    # A graduate with a qualification is on the next crew and mentors in turn.
    world, sim = runs["train"]
    _turn(world, sim)
    assert {1, 2} <= set(world.livelihoods.workshops.frame[0].crew)
    assert {1, 2} <= set(_receipt(world).qualified_on_crew) and 1 in _receipt(world).mentors


def test_interruptions_and_dropout_after_more_than_max_gap(quick, monkeypatch):
    monkeypatch.setattr(A, "COMPLETION_TURNS", 50)
    monkeypatch.setattr(A, "SERVICE_TURNS", 100)
    world, sim = _world(), FakeSim(range(1, 13))
    _built(world, sim)
    _qualify(world, sim, [12])
    _turn(world, sim)
    sim.people[1].trip = True
    for i in range(A.MAX_GAP):
        _turn(world, sim)
        assert _seats(world)[1].outcome == "missed" and _seats(world)[1].reason == "unavailable"
    record = next(a for a in _state(world).apprenticeships if a.agent_id == 1)
    assert record.gap == A.MAX_GAP and record.interruptions == A.MAX_GAP
    # A return resets the gap; the seat was kept (nobody new took it).
    sim.people[1].trip = False
    _turn(world, sim)
    assert _seats(world)[1].outcome == "attended" and record.gap == 0 and record.attended == 2
    sim.people[1].trip = True
    for _ in range(A.MAX_GAP + 1):
        _turn(world, sim)
    assert _seats(world)[1].ending == "dropout"
    ended = next(a for a in _state(world).archive if a.agent_id == 1)
    assert ended.ended_reason == "dropout" and ended.ended_turn == world.turn - 1
    # Losing the mentor is an interruption too.
    sim.people[12].alive = False
    _turn(world, sim)
    assert {s.reason for s in _seats(world).values() if s.outcome == "missed"} == {"no_mentor"}


def test_lifecycle_endings_are_dated_with_their_reason(quick, monkeypatch):
    monkeypatch.setattr(A, "COMPLETION_TURNS", 50)
    world, sim = _world(), FakeSim(range(1, 13))
    _built(world, sim)
    _qualify(world, sim, [11, 12])
    _turn(world, sim)
    assert sorted(a.agent_id for a in _state(world).apprenticeships) == [1, 2, 3, 4]
    sim.people[1].alive = False                                   # died between turns
    sim.people[2].region, sim.people[2].settlement = 3, 7          # migrated
    sim.people[4].occupation = 2                                   # became a merchant
    turn = world.turn
    _turn(world, sim)
    ends = {a.agent_id: (a.ended_reason, a.ended_turn) for a in _state(world).archive}
    assert ends == {1: ("died", turn), 2: ("migrated", turn), 4: ("occupation_changed", turn)}
    # New seats were filled from the remaining residents.
    assert sorted(a.agent_id for a in _state(world).apprenticeships) == [3, 5, 6, 7]
    world.war_state.armies = [SimpleNamespace(roster=[(5, 0)])]    # remobilised
    sim.die_in_tick = {6}                                          # dies in the tick: the turn does not count
    _turn(world, sim)
    ends = {a.agent_id: a.ended_reason for a in _state(world).archive}
    assert ends[5] == "remobilised" and ends[6] == "died"
    assert next(a for a in _state(world).archive if a.agent_id == 6).attended == 1
    world.war_state.armies = []
    # Closure: the city is gone, the site closes and its apprenticeships end.
    world.cities.cities = []
    _turn(world, sim)
    assert {a.ended_reason for a in _state(world).archive if a.ended_turn == world.turn - 1} == {"site_closed"}
    assert _state(world).apprenticeships == [] and _state(world).frame == []


def test_leaving_the_city_is_an_interruption_until_it_lasts_beyond_max_gap(quick, monkeypatch):
    monkeypatch.setattr(A, "COMPLETION_TURNS", 50)
    monkeypatch.setattr(A, "SERVICE_TURNS", 100)
    world, sim = _world(), FakeSim(range(1, 13))
    _built(world, sim)
    _qualify(world, sim, [11, 12])
    _turn(world, sim)
    sim.people[1].settlement = 5                                   # outside the city, same region
    for _ in range(A.MAX_GAP):
        _turn(world, sim)
        assert (_seats(world)[1].outcome, _seats(world)[1].reason) == ("missed", "away")
        # An apprentice away still holds one of the PER_SITE places.
        assert len(_state(world).apprenticeships) == A.PER_SITE
    sim.people[1].settlement = SETTLEMENT                          # back within the gap: continues
    _turn(world, sim)
    assert _seats(world)[1].outcome == "attended"
    sim.people[1].settlement = 5
    for _ in range(A.MAX_GAP + 1):
        _turn(world, sim)
    assert _seats(world)[1].ending == "departed"
    assert next(a for a in _state(world).archive if a.agent_id == 1).ended_reason == "departed"
    # An unseated apprentice drafted onto the crew who qualifies by service ends that way.
    monkeypatch.setattr(A, "SERVICE_TURNS", 1)
    sim.people[11].alive = sim.people[12].alive = False            # no mentor: seats are not reserved
    _turn(world, sim)
    ends = {a.agent_id: a.ended_reason for a in _state(world).archive if a.ended_turn == world.turn - 1}
    assert set(ends.values()) == {"service_qualified"}
    assert all(any(q.agent_id == aid and q.via == "service" for q in _state(world).qualifications) for aid in ends)


def test_an_apprentice_who_moves_to_another_sites_crew_keeps_the_ending_of_their_site(quick, monkeypatch):
    world, sim = _world(rank=2), FakeSim(range(1, 5))
    world.cities.cities.append(City(settlement_id=2, region=3, name="C2", founded_turn=0, founder=0, rank=1,
                                    size=5.0))
    for aid in range(21, 29):
        sim.add(aid, region=3, settlement=2)
    _built(world, sim)
    assert [(s.site, s.region) for s in world.livelihoods.workshops.sites] == [(0, SITE_REGION), (1, 3)]
    st = A._SiteTurn(1, 3, 2, "C2", 0.2, 8, 1.0, 0)
    assert A._grant(_state(world), 28, world.turn - 1, st, "service", (3, 2))
    _turn(world, sim)
    assert sorted(a.agent_id for a in _state(world).apprenticeships) == [21, 22]
    monkeypatch.setattr(A, "SERVICE_TURNS", 1)
    sim.people[21].region, sim.people[21].settlement = SITE_REGION, SETTLEMENT     # into site 0's city
    _turn(world, sim)
    assert 21 in world.livelihoods.workshops.frame[0].crew                          # drafted there
    ended = next(a for a in _state(world).archive if a.agent_id == 21)
    assert (ended.site, ended.ended_reason) == (1, "migrated")
    assert next(q for q in _state(world).qualifications if q.agent_id == 21).site == 0


def test_conquest_keeps_apprenticeships_running_under_the_new_controller(quick, monkeypatch):
    monkeypatch.setattr(A, "COMPLETION_TURNS", 50)
    world, sim = _world(), FakeSim(range(1, 13))
    _built(world, sim)
    _qualify(world, sim, [12])
    _turn(world, sim)
    world.regions[SITE_REGION].controller = "Civ1"
    _turn(world, sim)
    state = _state(world)
    event = state.events[-1]
    assert (event.kind, event.turn, event.ids, event.detail) == ("conquest", world.turn - 1, [1, 2],
                                                                {"from": 0, "to": 1})
    assert _receipt(world).controller == 1 and all(s.outcome == "attended" for s in _seats(world).values())
    assert [a.attended for a in state.apprenticeships] == [2, 2]


def test_pool_reset_retires_qualifications_and_ends_apprenticeships(quick):
    world, sim = _world(), FakeSim(range(1, 13))
    _built(world, sim)
    _qualify(world, sim, [12])
    _turn(world, sim)
    _turn(world, sim)
    state = _state(world)
    assert state.service and state.apprenticeships
    fresh = FakeSim(range(1, 13))                                  # a rebuilt pool reuses the ids
    turn = world.turn
    _turn(world, fresh)
    assert {q.retired_reason for q in state.retired} == {"pool_reset"}
    assert {(a.ended_reason, a.ended_turn) for a in state.archive} == {("pool_reset", turn)}
    assert state.qualifications == [] and all(r.crew_turns == 1 for r in state.service)
    assert state.counters["end_pool_reset"] == 2 and state.counters["retired_pool_reset"] == 1
    assert not any(e.kind == "teaching_lost" for e in state.events)


def test_teaching_lost_while_graduates_elsewhere_keep_their_record(quick):
    world, sim = _world(), FakeSim(range(1, 6))
    _built(world, sim)
    _qualify(world, sim, [4, 5])
    _turn(world, sim)
    assert _state(world).sites[0].present == [4, 5]
    sim.people[4].alive = False
    sim.people[5].region, sim.people[5].settlement = 3, 8
    _turn(world, sim)
    state = _state(world)
    event = next(e for e in state.events if e.kind == "teaching_lost")
    assert event.turn == world.turn - 1 and event.ids == [4, 5] and event.site == 0
    assert event.detail["4"] == "died" and event.detail["5"] == "region:3"
    assert event.detail["still_qualified"] == 1 and A.qualified_ids(world, 3) == [5]
    assert _receipt(world).teaching_lost and state.continuity["sites_without_qualified"] == [0]
    assert state.continuity["qualified_alive"] == 1 and state.continuity["qualified_elsewhere"] == 1
    # With nobody qualified on the crew the site wears; teaching returns with the graduate.
    assert _receipt(world).net_wear == A.OPERATING_WEAR
    sim.people[5].region, sim.people[5].settlement = SITE_REGION, SETTLEMENT
    _turn(world, sim)
    assert state.events[-1].kind == "teaching_restored" and state.events[-1].ids == [5]


def test_disable_ends_open_apprenticeships_and_keeps_qualifications(quick):
    world, sim = _world(), FakeSim(range(1, 13))
    _built(world, sim)
    _qualify(world, sim, [12])
    _turn(world, sim)
    with pytest.raises(ValueError, match="mode"):
        A.set_apprenticeship_enabled(world, True, args=SimpleNamespace(apprenticeship_mode="no_qualification"))
    A.set_apprenticeship_enabled(world, False, args=None)
    state = _state(world)
    assert state.apprenticeships == [] and {a.ended_reason for a in state.archive} == {"disabled"}
    assert [q.agent_id for q in state.qualifications] == [12] and not A.apprenticeship_active(world)
    assert A.qualified_ids(world, SITE_REGION) == []


def test_bounds_refuse_grants_and_evict_stale_service(quick, monkeypatch):
    monkeypatch.setattr(A, "MAX_QUALIFIED", 2)
    monkeypatch.setattr(A, "MAX_SERVICE", 4)
    world, sim = _world(), FakeSim(range(1, 6))
    _built(world, sim)
    for _ in range(3):
        _turn(world, sim)
    state = _state(world)
    # Five crew, room for four service records: the least recently seen
    # (ties: fewest turns, then lowest id) is evicted each turn.
    assert state.counters["service_evicted"] == 2
    assert [q.agent_id for q in state.qualifications] == [2, 3]
    assert state.counters["grants_refused_cap"] == 2
    assert [r.agent_id for r in state.service] == [1, 4, 5]


def test_a_refused_reservation_costs_only_that_seat(quick):
    world, sim = _world(), FakeSim(range(1, 13))
    _built(world, sim)
    _qualify(world, sim, [11, 12])
    original = sim.reserve_work

    def reserve(turn, category, rows):
        if category == A.CATEGORY_APPRENTICE and any(aid == 2 for aid, _ in rows):
            raise ValueError("agent already holds work this turn")
        return original(turn, category, rows)

    sim.reserve_work = reserve
    _turn(world, sim)
    assert sorted(_seats(world)) == [1, 3, 4] and _state(world).counters["seat_refused"] == 1
    _turn(world, sim)
    assert _seats(world)[1].outcome == "attended" and 2 not in _seats(world)


# --- Stipends from the firm and money closure ---------------------------------------------


def _with_firm(world, cash, mode="paid"):
    world.livelihoods.workshop_payroll = WorkshopPayrollState(mode=mode)
    firm = WorkshopFirm(site=0, region=SITE_REGION, settlement_id=SETTLEMENT, city_name="C1", opened_turn=1,
                        cash=cash, totals={"sales": cash})
    world.livelihoods.workshop_payroll.firms.append(firm)
    return firm


def test_stipends_are_paid_once_from_firm_cash_after_wages_and_the_firm_closes(quick):
    world, sim = _world(), FakeSim(range(1, 13))
    _built(world, sim)
    _qualify(world, sim, [12])
    firm = _with_firm(world, cash=100_000)
    _turn(world, sim)
    seats = _seats(world)
    due = math.floor(A.APPRENTICE_FRACTION * A.STIPEND_PER_WORK + 0.5)
    assert {a: (s.stipend_due, s.stipend_paid, s.stipend_status) for a, s in seats.items()} == {
        1: (due, due, "paid"), 2: (due, due, "paid")}
    stipends = [t for t in sim.transfers if t[1] == A.PURPOSE_APPRENTICE_STIPEND]
    assert stipends == [(world.turn - 1, 2, 0, [(1, due), (2, due)])]
    wages = [t for t in sim.transfers if t[1] == P.PURPOSE_WORKSHOP_WAGE]
    assert wages and sim.transfers.index(wages[0]) < sim.transfers.index(stipends[0])     # wages first
    P.check_firm(firm)
    assert firm.totals["stipends"] == 2 * due
    pr = world.livelihoods.workshop_payroll.frame[0]
    assert pr.stipends == 2 * due and pr.cash_close == firm.cash
    assert pr.cash_close == pr.cash_open + pr.sales - pr.wages_paid - pr.distributed - pr.written_off - pr.stipends
    money = [m for m in world.livelihoods.workshop_payroll.money if m.kind == "stipend"]
    assert [(m.payer, m.payee, m.applied) for m in money] == [(("workshop_cash", 0), ("agent_wealth", 1), due),
                                                              (("workshop_cash", 0), ("agent_wealth", 2), due)]
    assert sum(a.stipends for a in _state(world).apprenticeships) == 2 * due
    # The crew's wage share and the apprentices' share were withheld once each.
    assert set(sim.receipt or ()) == set()                        # receipt taken once
    # The same key is refused natively: a second payment for the turn cannot happen.
    with pytest.raises(ValueError, match="already applied"):
        sim.transfer_wealth(world.turn - 1, A.PURPOSE_APPRENTICE_STIPEND, 0, [(1, 1)])


def test_short_cash_is_shared_pro_rata_and_not_owed(quick):
    world, sim = _world(), FakeSim(range(1, 13))
    _built(world, sim)
    _qualify(world, sim, [12])
    firm = _with_firm(world, cash=0)
    _turn(world, sim)
    assert {s.stipend_status for s in _seats(world).values()} == {"no_cash"}
    assert _receipt(world).stipend_status == "no_cash" and firm.cash == 0
    P.check_firm(firm)
    # No firm at the site, or the unpaid-labour ablation: nothing is paid.
    world.livelihoods.workshop_payroll.firms.clear()
    _turn(world, sim)
    assert _receipt(world).stipend_status == "no_firm"
    world.livelihoods.workshop_payroll.mode = "unpaid_labor"
    _turn(world, sim)
    assert _receipt(world).stipend_status == "unpaid_labor"
    assert _state(world).counters["stipends_paid"] == 0
    assert _state(world).counters["stipends_due"] == 3 * 2 * 125


def test_pay_from_firm_shares_short_cash_and_keeps_refused_amounts():
    world = _world()
    firm = _with_firm(world, cash=301)
    state = world.livelihoods.workshop_payroll
    state.last_payroll_turn = state.frame_turn = world.turn
    sim = FakeSim(range(1, 4))
    sim.people[2].wealth = MAX_WEALTH - 0.0625                     # room for 62 milli
    sim.people[3].alive = False
    out = P.pay_from_firm(world, sim, 0, {1: 200, 2: 200, 3: 200}, purpose=2)
    assert {aid: (offered, applied, status) for aid, (offered, applied, status) in out.items()} == {
        1: (101, 101, 0), 2: (100, 62, 1), 3: (100, 0, 2)}
    assert firm.cash == 301 - 163 and firm.totals["stipends"] == 163
    P.check_firm(firm)
    assert [m.status for m in state.money] == ["applied", "limited", "absent"]
    with pytest.raises(RuntimeError, match="payroll pass"):
        state.last_payroll_turn = world.turn - 1
        P.pay_from_firm(world, sim, 0, {1: 1}, purpose=2)


# --- Failure, exactly once and checkpoint ---------------------------------------------------


def test_failed_tick_or_phase2_charges_nothing_and_changes_nothing(quick):
    world, sim = _world(), FakeSim(range(1, 13))
    _built(world, sim)
    _qualify(world, sim, [12])
    firm = _with_firm(world, cash=100_000)
    _turn(world, sim)
    before = (_state(world).model_dump_json(), firm.model_dump_json(), {a: p.wealth for a, p in sim.people.items()})
    sim.fail_tick = True
    with pytest.raises(RuntimeError, match="native tick failed"):
        _turn(world, sim)
    assert sim.paid is None and _state(world)._pending is None and sim.cancelled >= 1
    assert _state(world).model_dump_json() == before[0] and firm.model_dump_json() == before[1]
    assert {a: p.wealth for a, p in sim.people.items()} == before[2]
    # Phase 2 fails after the seats were reserved: nothing is armed or kept.
    sim.fail_tick = False
    world.livelihoods.workshop_payroll._turn = None
    world.livelihoods.workshops._plan = None
    with pytest.raises(RuntimeError, match="economy tick failed"):
        _turn(world, sim, fail="phase2")
    assert sim.paid is None and _state(world)._pending is None
    assert _state(world).model_dump_json() == before[0]


def test_hooks_apply_once_per_turn():
    world, sim = _world(), FakeSim(range(1, 13))
    _built(world, sim)
    _qualify(world, sim, [12])
    bridge = SimpleNamespace(_sim=sim)
    _turn(world, sim)
    counters = dict(_state(world).counters)
    # Replaying the settled turn's hooks changes nothing; a settled turn is refused.
    assert A.after_agent_tick(world, bridge) == [] and A.phase10(world, None, None, bridge) == []
    world.turn -= 1
    with pytest.raises(ValueError, match="already settled"):
        A.before_crews(world, sim, [(0, SITE_REGION, SETTLEMENT, 0.2, 8)])
    world.turn += 1
    assert _state(world).counters == counters
    # Two pending turns at once are refused.
    A.before_crews(world, sim, [(0, SITE_REGION, SETTLEMENT, 0.2, 8)])
    with pytest.raises(RuntimeError, match="already pending"):
        A.before_crews(world, sim, [(0, SITE_REGION, SETTLEMENT, 0.2, 8)])


def test_state_resumes_exactly_inside_a_live_apprenticeship(quick, monkeypatch):
    monkeypatch.setattr(A, "COMPLETION_TURNS", 6)

    def build():
        world, sim = _world(), FakeSim(range(1, 13))
        _built(world, sim)
        _qualify(world, sim, [12])
        for _ in range(3):
            _turn(world, sim)
        return world, sim

    straight, sim_a = build()
    for _ in range(5):
        _turn(straight, sim_a)
    resumed, sim_b = build()
    assert resumed.livelihoods.apprenticeship.apprenticeships          # live records at the checkpoint
    # JSON round trip of the persisted state (what an exact checkpoint keeps), then pickle.
    text = resumed.livelihoods.model_dump_json()
    resumed.livelihoods = pickle.loads(pickle.dumps(LivelihoodsState.model_validate_json(text)))
    assert resumed.livelihoods.model_dump_json() == text
    # An exact checkpoint load re-binds the same pool without a reset.
    L.bind_native_pool(resumed, SimpleNamespace(_sim=sim_b), reset=False)
    for _ in range(5):
        _turn(resumed, sim_b)
    a, b = straight.livelihoods.apprenticeship, resumed.livelihoods.apprenticeship
    assert json.loads(a.model_dump_json()) == json.loads(b.model_dump_json())
    assert [q.via for q in a.qualifications].count("apprenticeship") >= 2


# --- Observation ---------------------------------------------------------------------------


def test_snapshot_is_dated_bounded_and_json_safe(quick):
    world, sim = _world(), FakeSim(range(1, 13))
    _built(world, sim)
    _qualify(world, sim, [12])
    _turn(world, sim)
    snap = L.livelihoods_snapshot_fields(world)["livelihoods"]["apprenticeship"]
    assert snap["stage"] == "RS1" and snap["source_turn"] == world.turn - 1
    assert snap["receipts"][0]["turn"] == world.turn - 1 and snap["continuity"]["turn"] == world.turn - 1
    assert set(snap["counters"]) <= set(COUNTERS)
    assert json.loads(json.dumps(snap)) == snap
    world.turn += 1                                              # a turn without an apprenticeship pass
    stale = A.snapshot_summary(world)
    assert stale["receipts"] is None and stale["continuity"] is None
    assert L.livelihoods_feature_flags(world)["apprenticeship"] is True


def test_feature_off_worlds_have_no_state_and_workshops_run_unchanged():
    def run(enable):
        world, sim = _world(), FakeSim(range(1, 13))
        if not enable:
            world.livelihoods.apprenticeship = None
        for _ in range(9):
            _turn(world, sim)
        return world, sim

    off, sim_off = run(False)
    assert off.livelihoods.apprenticeship is None and "apprenticeship" not in L.livelihoods_snapshot_fields(off).get(
        "livelihoods", {})
    assert all(plan["priority"] == [] for plan in sim_off.plans)
    for r in off.livelihoods.workshops.frame:
        assert r.allocated == r.work_available
    on, _ = run(True)
    assert _site(off).condition == 1.0 and _site(on).condition < 1.0


@pytest.mark.parametrize("mode", ["priority", "record_only"])
def test_a_seated_veteran_is_placed_each_turn_in_either_rs3_mode(mode, monkeypatch):
    """Review A 2026-11-05 (major): RS1 reported ``placed:apprentice`` only for a
    new seat that priority had marked as a veteran, so with the real RS3 hooks a
    veteran attending every turn became ``waiting`` (and unmet) after the first
    turn, and the record_only control never recorded the placement. Every seat
    reserved this turn is now reported; RS3 keeps one spell and no waiting row."""
    from chronicler import veteran_reintegration as VR
    from chronicler.veteran_reintegration_state import VeteranRecord
    monkeypatch.setattr(A, "SERVICE_TURNS", 3)
    monkeypatch.setattr(A, "COMPLETION_TURNS", 3)

    class Bridge:
        def __init__(self, sim):
            self._sim = sim

        def get_snapshot(self):
            return self._sim.get_snapshot()

    def turn(world, sim):
        bridge = Bridge(sim)
        econ = SimpleNamespace(craft_output={r.name: 0.0 for r in world.regions})
        L.prepare_phase2(world, _batch(len(world.regions)), bridge, sim.get_snapshot(), acc=None)
        sim.inputs = [[0.0] * 9 for _ in world.regions]
        L.finish_phase2(world, econ, bridge, acc=None)
        L.wrap_agent_tick(world, bridge, sim.tick, econ)()
        L.phase10_before_reserves(world, acc=None, economy_result=econ, agent_bridge=bridge)
        L.phase10(world, acc=None, economy_result=econ, agent_bridge=bridge)
        world.turn += 1

    world, sim = _world(), FakeSim(range(1, 13))
    world.civ_index_map = {c.name: i for i, c in enumerate(world.civilizations)}
    world.war_state = SimpleNamespace(armies=[], wars=[], ended_wars=[])
    VR.set_veteran_reintegration_enabled(world, True, args=SimpleNamespace(veteran_mode=mode))
    for _ in range(W.CONSTRUCTION_COST // W.INSTALLMENT):
        turn(world, sim)
    _qualify(world, sim, [12])
    vs = world.livelihoods.veteran_reintegration
    vs.records.append(VeteranRecord(record_id=0, agent_id=1, civ=0, army_id="army-x", cause="demobilised",
                                    released_turn=world.turn - 1, released_region=SITE_REGION,
                                    region=SITE_REGION, age=30, status="waiting"))
    vs.next_record_id, vs.last_settled_turn = 1, world.turn - 1
    for _ in range(3):
        turn(world, sim)
        seat = next(s for s in world.livelihoods.apprenticeship.frame[0].seats if s.agent_id == 1)
        assert seat.outcome == "attended" and seat.veteran == (mode == "priority")
        assert [p.kind for p in vs.frame.placed if p.agent_id == 1] == ["placed:apprentice"]
        assert not [w for w in vs.frame.waiting if w.agent_id == 1]
        assert vs.records[0].status == "placed"
    c = vs.counters
    assert (c["placement_turns"], c["placements"], c["placements_apprentice"], c["people_placed"]) == (3, 1, 1, 1)
    assert c.get("waiting_turns", 0) == 0 and not any(k.startswith("unmet_") for k in c)
    assert c.get("placed_prioritised", 0) == (1 if mode == "priority" else 0)
