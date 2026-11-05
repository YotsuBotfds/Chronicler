"""L5 learning cohorts: offline lifecycle contract (no native extension).

A small fake stands in for the five native calls with the same rules as
``chronicler-agents/src/learning_work.rs`` (availability, recruitment order,
seats from delivered teaching, income withheld, capped skill grants); the
real-native path is in ``test_learning_cohorts_native.py``.
"""
from __future__ import annotations

import json
import math
import pickle

import pytest

from chronicler import learning_cohorts as L
from chronicler.learning_cohorts_state import (
    ATTENDANCE_OUTCOMES, COUNTERS, EXIT_REASONS, MAX_ARCHIVE, MEMBER_STATUSES, LearningCohortState,
)
from chronicler.learning_services import (
    LEARNERS_PER_SCHOLAR, set_learning_services_enabled,
)
from chronicler.learning_services_state import AcademyMaterialInventory, AcademyTeachingReceipt
from chronicler.livelihoods import configure_livelihoods, livelihoods_snapshot_fields
from chronicler.livelihoods_state import LivelihoodsState
from chronicler.main import _build_parser
from chronicler.scholarship_state import ACADEMY, ScholarshipState, Seat
from chronicler.world_gen import generate_world

SCHOLAR = 3


class FakeSim:
    """Native learning attendance rules over a dict of people (stable ids)."""

    def __init__(self, people):
        self.people = {p["id"]: dict(p) for p in people}
        self.plan = None
        self.health = set()   # ids holding other work this turn
        self.calls = []

    def _status(self, p, region, enlisted):
        if p is None or not p["alive"]:
            return "dead"
        if p["region"] != region:
            return "elsewhere"
        if p["occ"] == SCHOLAR or p["age"] < 20:
            return "not_eligible"
        if p.get("trip"):
            return "on_trip"
        if p["id"] in enlisted:
            return "enlisted"
        if p["id"] in self.health:
            return "assigned"
        return "available"

    def plan_learners(self, turn, cohorts, enlisted):
        self.calls.append(("plan", turn))
        enlisted = set(enlisted)
        members = {aid for _, ids, _, _ in cohorts for aid in ids}
        out = []
        for region, ids, recruit, max_skill in cohorts:
            rows = []
            for aid in ids:
                p = self.people.get(aid)
                status = self._status(p, region, enlisted)
                alive = p is not None and p["alive"]
                rows.append((aid, MEMBER_STATUSES.index(status), p["occ"] if alive else 0,
                             p["skill"][p["occ"]] if alive else 0.0))
            recruits = []
            if recruit:
                cands = [p for p in self.people.values()
                         if p["alive"] and p["age"] >= 20 and p["region"] == region and p["occ"] != SCHOLAR
                         and p["id"] not in members and not p.get("trip") and p["id"] not in enlisted
                         and p["id"] not in self.health and p["skill"][p["occ"]] <= max_skill]
                cands.sort(key=lambda p: (p["skill"][p["occ"]], p["id"]))
                recruits = [(p["id"], p["occ"], p["skill"][p["occ"]], p["age"]) for p in cands[:recruit]]
            out.append((rows, recruits, [0] * 8))
        return out

    def reserve_learning_attendance(self, turn, lpt, rows):
        assert self.plan is None and rows
        assert lpt == LEARNERS_PER_SCHOLAR
        self.plan = {"turn": turn, "rows": list(rows), "consumed": False}

    def tick(self, turn, delivered_work: dict[int, float], income=1.0, kill_before=(), kill_after=(),
             move_after=()):
        """Wealth-phase seating, then later-in-tick deaths and moves."""
        for aid in kill_before:
            self.people[aid]["alive"] = False
        if self.plan is not None:
            assert self.plan["turn"] == turn
            seats = {r: math.floor(w * LEARNERS_PER_SCHOLAR + 1e-6) for r, w in delivered_work.items()}
            rows = []
            for aid, region, fraction in self.plan["rows"]:
                p = self.people[aid]
                if not p["alive"] or p["region"] != region:
                    rows.append((aid, region, fraction, 3, 0.0, 0.0))
                elif seats.get(region, 0) > 0:
                    seats[region] -= 1
                    rows.append((aid, region, fraction, 1, income, income * fraction))
                else:
                    rows.append((aid, region, fraction, 2, 0.0, 0.0))
            n = max(delivered_work, default=-1) + 1
            self.plan.update(consumed=True, rows=rows,
                             delivered=[(delivered_work.get(r, 0.0), 0) for r in range(n)] if delivered_work else [])
        for aid in kill_after:
            self.people[aid]["alive"] = False
        for aid, region in move_after:
            self.people[aid]["region"] = region
        for p in self.people.values():
            if p["alive"]:
                p["skill"][p["occ"]] = min(1.0, p["skill"][p["occ"]] + 0.05)

    def take_learning_attendance(self, turn):
        if self.plan is None or not self.plan["consumed"] or self.plan["turn"] != turn:
            return None
        plan, self.plan = self.plan, None
        return plan["delivered"], plan["rows"]

    def cancel_learning_attendance(self, turn):
        self.plan = None
        return True

    def grant_learning_skill(self, rows):
        out = []
        for aid, occ, gain in rows:
            p = self.people.get(aid)
            if p is None or not p["alive"]:
                out.append((aid, occ, False, 0.0, 0.0))
                continue
            before = p["skill"][occ]
            p["skill"][occ] = min(1.0, before + gain)
            out.append((aid, occ, True, before, p["skill"][occ]))
        return out


class FakeBridge:
    def __init__(self, sim):
        self._sim = sim


def person(aid, region=0, occ=0, skill=0.2, age=30):
    s = [0.0] * 5
    s[occ] = skill
    return {"id": aid, "region": region, "occ": occ, "skill": s, "age": age, "alive": True}


def _world(mode="learn", held=16.0):
    world = generate_world(seed=42, num_regions=4, num_civs=2)
    world.agent_mode = "hybrid"
    owner = 0
    world.regions[0].controller = world.civilizations[owner].name
    world.scholarship = ScholarshipState(seats=[Seat(region=0, kind=ACADEMY, name="Declared Academy",
                                                     founded_turn=0, founder=owner, lord=owner)])
    set_learning_services_enabled(world, True)
    world.scholarship.learning_services.inventories = [AcademyMaterialInventory(
        seat_id=0, region=0, founder=owner, founded_turn=0, seat_name="Declared Academy",
        held=held, purchased_total=held, used_total=0.0, lost_total=0.0)]
    args = _build_parser().parse_args(["--learning-cohorts", "--learning-cohort-mode", mode])
    configure_livelihoods(world, args, agent_mode="hybrid")
    return world


def _receipt(world, seat_id, work, held=16.0, staff=2, upkeep=True):
    seat = world.scholarship.seats[seat_id]
    learners = None if work is None else work * LEARNERS_PER_SCHOLAR
    return AcademyTeachingReceipt(
        seat_id=seat_id, region=seat.region, founder=seat.founder, founded_turn=seat.founded_turn,
        seat_name=seat.name, lord=seat.lord, source_turn=world.turn, available_turn=world.turn + 1,
        learner_upper_bound=40, scholar_upper_bound=staff, upkeep_source_turn=world.turn - 1,
        upkeep_lord=seat.lord, upkeep_due=1, upkeep_amount_paid=1 if upkeep else 0,
        upkeep_satisfied=upkeep, upkeep_applies=True, held_before=held,
        work_requested=work or 0.0, work_available=work, work_reserved=work, work_delivered=work,
        learners_delivered=learners, crafts_used=learners, held_after=held - (learners or 0.0),
        native_dropped=0)


def turn(world, sim, work=1.0, receipt=None, **tick):
    """One turn: before hook, fake native tick, academy receipt, after hook."""
    bridge = FakeBridge(sim)
    L.before_agent_tick(world, bridge, None)
    seat = world.scholarship.seats[0]
    delivered = {seat.region: work} if work else {}
    sim.tick(world.turn, delivered, **tick)
    world.scholarship.learning_services.teaching_receipts = [receipt or _receipt(world, 0, work if work else None)]
    events = L.after_agent_tick(world, bridge)
    assert events == [] and world.livelihoods.learning_cohorts._pending is None
    world.turn += 1
    return world.livelihoods.learning_cohorts


def _people(n=6, region=0):
    return [person(10 + i, region=region, occ=i % 3, skill=0.1 * (i % 4)) for i in range(n)]


def test_switch_requires_hybrid_and_academy_services():
    world = generate_world(seed=42, num_regions=4, num_civs=2)
    parse = _build_parser().parse_args
    with pytest.raises(ValueError, match="hybrid"):
        configure_livelihoods(world, parse(["--learning-cohorts"]), agent_mode="off")
    with pytest.raises(ValueError, match="academy-services"):
        configure_livelihoods(world, parse(["--learning-cohorts"]), agent_mode="hybrid")
    assert world.livelihoods is None
    world = _world()
    state = world.livelihoods.learning_cohorts
    assert state.mode == "learn" and state.enabled and L.learning_cohorts_active(world)
    world.scholarship.learning_services.enabled = False          # paused services: dormant
    assert not L.learning_cohorts_active(world)


def test_matched_staff_and_supplies_progress_to_a_completed_capability():
    world, sim = _world(), FakeSim(_people(6))
    state = turn(world, sim, work=1.0)
    assert [c.cohort_id for c in state.cohorts] == [0] and state.next_cohort_id == 1
    cohort = state.cohorts[0]
    # Lowest current skill first, then stable id; at most eight.
    assert [m.agent_id for m in cohort.members] == [10, 14, 11, 15, 12, 13]
    r = state.frame[0]
    assert r.session and r.attended == r.reserved == [10, 14, 11, 15, 12, 13]
    assert r.income_charged == pytest.approx(6 * L.ATTENDANCE_FRACTION)
    assert r.supplies_used == 6 and r.teaching_learners_delivered == 8
    before = {m.agent_id: sim.people[m.agent_id]["skill"][m.occupation] for m in cohort.members}
    for _ in range(L.SESSIONS_TO_COMPLETE - 1):
        state = turn(world, sim, work=1.0)
    assert state.cohorts == [] and state.archive[-1].closed_reason == "finished"
    done = state.archive[-1]
    assert all(m.status == "completed" and m.attended == L.SESSIONS_TO_COMPLETE for m in done.members)
    for m in done.members:
        assert m.skill_after == pytest.approx(min(1.0, m.skill_before + L.COMPLETION_GAIN))
        # Ordinary growth during the course, then the grant on top.
        assert m.skill_before == pytest.approx(min(1.0, before[m.agent_id] + 0.05 * (L.SESSIONS_TO_COMPLETE - 1)))
        assert sim.people[m.agent_id]["skill"][m.occupation] == pytest.approx(m.skill_after)
    c = state.counters
    assert (c["cohorts_formed"], c["completions"], c["capability_changes"], c["sessions"]) == (1, 6, 6, 4)
    assert c["learner_turns_attended"] == 24 and c["attendance_income_charged"] == pytest.approx(12.0)
    assert len(state.graduates) == 6 and all(g.granted for g in state.graduates)


def test_no_learning_control_keeps_costs_and_changes_no_capability():
    runs = {}
    for mode in ("learn", "no_learning"):
        world, sim = _world(mode), FakeSim(_people(6))
        for _ in range(L.SESSIONS_TO_COMPLETE):
            state = turn(world, sim, work=1.0)
        runs[mode] = (state, sim)
    learn, control = runs["learn"][0], runs["no_learning"][0]
    for key in ("learner_turns_attended", "attendance_income_charged", "supplies_used_by_attendees",
                "sessions", "completions"):
        assert learn.counters[key] == control.counters[key]
    assert control.counters.get("capability_changes", 0) == 0 and control.counters.get("skill_granted", 0) == 0
    assert all(not g.granted and g.skill_after == g.skill_before for g in control.graduates)
    assert learn.counters["skill_granted"] > 0
    learned = {g.agent_id: g.skill_after for g in learn.graduates}
    controlled = {g.agent_id: g.skill_after for g in control.graduates}
    assert all(learned[a] > controlled[a] for a in learned)


@pytest.mark.parametrize("receipt_kw, reason", [
    ({"held": 0.0}, "no_supplies"),
    ({"staff": 0}, "no_teacher"),
    ({"upkeep": False}, "upkeep_unmet"),
])
def test_no_teacher_or_supplies_means_no_seat_no_cost_no_progress(receipt_kw, reason):
    world, sim = _world(), FakeSim(_people(4))
    bridge = FakeBridge(sim)
    L.before_agent_tick(world, bridge, None)
    sim.tick(world.turn, {})
    world.scholarship.learning_services.teaching_receipts = [_receipt(world, 0, None, **receipt_kw)]
    L.after_agent_tick(world, bridge)
    state = world.livelihoods.learning_cohorts
    r = state.frame[0]
    assert not r.session and r.no_session_reason == reason
    assert r.attended == [] and r.no_seat == r.reserved and r.income_charged == 0.0
    assert all(m.attended == 0 for m in state.cohorts[0].members)
    assert state.counters["no_session_" + reason] == 1


def test_too_little_teaching_and_absent_members_are_named():
    world, sim = _world(), FakeSim(_people(3))
    state = turn(world, sim, work=0.1)              # 0.8 learner-equivalents: no whole seat
    r = state.frame[0]
    assert r.no_seat == r.reserved and r.no_session_reason == "too_little_teaching"
    state = turn(world, sim, kill_before=list(r.reserved))
    r = state.frame[0]
    assert r.absent == r.reserved and r.no_session_reason == "members_absent" and r.income_charged == 0.0
    state = turn(world, sim)
    assert state.cohorts == [] and {m.exit_reason for m in state.archive[-1].members} == {"died"}


def test_no_student_time_reserves_nobody_and_absence_ends_membership():
    world, sim = _world(), FakeSim(_people(3))
    turn(world, sim)
    state = world.livelihoods.learning_cohorts
    members = [m.agent_id for m in state.cohorts[0].members]
    for aid in members:
        sim.people[aid]["trip"] = True
    for k in range(1, L.ABSENCE_LIMIT + 1):
        state = turn(world, sim)
        r = state.frame[0]
        assert r.reserved == [] and r.unavailable == {"on_trip": len(members)}
        assert r.no_session_reason == "no_available_member" and r.income_charged == 0.0
    assert state.cohorts == [] and all(m.exit_reason == "absent" for m in state.archive[-1].members)
    assert state.counters["exit_absent"] == len(members)


def test_interrupted_cohort_death_migration_and_occupation_change():
    world, sim = _world(), FakeSim(_people(6))
    state = turn(world, sim)
    ids = [m.agent_id for m in state.cohorts[0].members]
    dead, mover, switcher, late = ids[0], ids[1], ids[2], ids[3]
    # A death before the wealth phase: absent this turn, exits as died next turn.
    state = turn(world, sim, kill_before=[dead], move_after=[(mover, 2)])
    assert dead in state.frame[0].absent and mover in state.frame[0].attended
    sim.people[switcher]["occ"] = 4
    state = turn(world, sim)
    exited = state.frame[0].exited
    assert exited == {"died": [dead], "migrated": [mover], "occupation_changed": [switcher]}
    # Those left keep going; a member who dies after completing their last
    # session gets no grant and exits as died.
    state = turn(world, sim, kill_after=[late])
    archived = state.archive[-1]
    by_id = {m.agent_id: m for m in archived.members}
    assert by_id[late].status == "exited" and by_id[late].exit_reason == "died"
    assert state.counters["grants_refused"] == 1
    assert sorted(a for a, m in by_id.items() if m.status == "completed") == sorted(ids[4:])
    # A migrant's unfinished progress does not travel; their skill is untouched.
    assert by_id[mover].status == "exited" and by_id[mover].skill_after is None


def test_lost_or_replaced_academy_closes_the_cohort_and_a_new_one_starts_fresh():
    world, sim = _world(), FakeSim(_people(4))
    turn(world, sim)
    turn(world, sim)
    state = world.livelihoods.learning_cohorts
    old = state.cohorts[0]
    assert all(m.attended == 2 for m in old.members)
    seat = world.scholarship.seats[0]
    seat.fallen_turn = world.turn
    world.scholarship.seats.append(Seat(region=0, kind=ACADEMY, name="Second Academy",
                                        founded_turn=world.turn, founder=0, lord=0))
    services = world.scholarship.learning_services
    services.inventories[0].retired = True
    services.inventories[0].lost_total, services.inventories[0].held = 16.0, 0.0
    services.inventories.append(AcademyMaterialInventory(
        seat_id=1, region=0, founder=0, founded_turn=world.turn, seat_name="Second Academy",
        held=16.0, purchased_total=16.0, used_total=0.0, lost_total=0.0))
    bridge = FakeBridge(sim)
    L.before_agent_tick(world, bridge, None)
    sim.tick(world.turn, {0: 1.0})
    services.teaching_receipts = [_receipt(world, 1, 1.0)]
    L.after_agent_tick(world, bridge)
    assert state.archive[-1].cohort_id == old.cohort_id and state.archive[-1].closed_reason == "academy_lost"
    assert all(m.exit_reason == "academy_lost" for m in state.archive[-1].members)
    new = state.cohorts[0]
    assert new.cohort_id == old.cohort_id + 1 and new.seat_id == 1 and new.seat_name == "Second Academy"
    # Same people re-enrol from scratch; progress does not transfer.
    assert {m.agent_id for m in new.members} == {m.agent_id for m in old.members}
    assert all(m.attended == 1 for m in new.members)


def test_a_cohort_without_sessions_stalls_and_formation_needs_supplies():
    world, sim = _world(held=0.5), FakeSim(_people(4))
    state = turn(world, sim)
    assert state.cohorts == [] and state.frame == []          # supplies for less than one learner
    world, sim = _world(), FakeSim(_people(4))
    turn(world, sim)
    for _ in range(L.STALL_LIMIT):
        state = turn(world, sim, work=None)
    assert state.cohorts == [] and state.archive[-1].closed_reason == "stalled"
    assert state.counters["exit_stalled"] == 4


def test_state_round_trips_exactly_and_snapshot_dates_observations():
    world, sim = _world(), FakeSim(_people(5))
    turn(world, sim)
    turn(world, sim)
    state = world.livelihoods.learning_cohorts
    assert pickle.loads(pickle.dumps(state)).model_dump_json() == state.model_dump_json()
    back = LearningCohortState.model_validate_json(state.model_dump_json())
    assert back == state
    container = LivelihoodsState.model_validate_json(world.livelihoods.model_dump_json())
    assert container.learning_cohorts == state
    fields = livelihoods_snapshot_fields(world)["livelihoods"]["learning_cohorts"]
    assert fields["source_turn"] == world.turn - 1 and fields["receipts"][0]["turn"] == world.turn - 1
    json.dumps(fields)
    assert list(fields["counters"]) == [k for k in COUNTERS if k in fields["counters"]]
    world.turn += 1     # a turn with no completed cohort turn: unknown, not empty
    assert livelihoods_snapshot_fields(world)["livelihoods"]["learning_cohorts"]["receipts"] is None


def test_disable_closes_open_cohorts_and_mode_switch_is_refused_while_open():
    world, sim = _world(), FakeSim(_people(3))
    turn(world, sim)
    parse = _build_parser().parse_args
    with pytest.raises(ValueError, match="mode"):
        configure_livelihoods(world, parse(["--learning-cohort-mode", "no_learning", "--learning-cohorts"]),
                              agent_mode="hybrid")
    configure_livelihoods(world, parse(["--no-learning-cohorts"]), agent_mode="hybrid")
    state = world.livelihoods.learning_cohorts
    assert not state.enabled and state.cohorts == [] and state.archive[-1].closed_reason == "disabled"
    assert not L.learning_cohorts_active(world)
    assert "learning_cohorts" not in livelihoods_snapshot_fields(world).get("livelihoods", {})


def test_archive_is_bounded_and_ids_are_never_reused():
    world, sim = _world(), FakeSim(_people(2))
    for _ in range((MAX_ARCHIVE + 2) * L.SESSIONS_TO_COMPLETE):
        for p in sim.people.values():
            p["skill"] = [0.0] * 5               # room to learn again
        turn(world, sim)
    state = world.livelihoods.learning_cohorts
    ids = [c.cohort_id for c in state.archive]
    assert len(state.archive) == MAX_ARCHIVE and ids == sorted(set(ids))
    assert state.next_cohort_id == MAX_ARCHIVE + 2 and len(state.graduates) <= 32


def test_declared_codes_are_append_only_prefixes():
    assert MEMBER_STATUSES[:7] == ("available", "dead", "elsewhere", "on_trip", "enlisted", "assigned",
                                   "not_eligible")
    assert ATTENDANCE_OUTCOMES[:4] == ("pending", "attended", "no_seat", "absent")
    assert EXIT_REASONS[:7] == ("died", "migrated", "occupation_changed", "absent", "academy_lost",
                                "stalled", "disabled")
