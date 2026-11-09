"""L5 named learners at academies (``--learning-cohorts``, default off).

Extends the academy-services candidate (``--academy-services``) from
learner-equivalents to finite cohorts of named people who attend, pay for
their study with their time, progress and complete, with an actual change in
an individual capability. Requires ``--agents hybrid`` and active academy
services (hence ``--scholarship`` and ``--techniques``).

Modes (``--learning-cohort-mode``): ``learn`` (default) and ``no_learning``,
the cost-retaining control: cohorts form, attend, withhold the same income
and occupy the same delivered teaching and paid supplies, and completions are
recorded, but completion grants nothing. (Turning off academy services
instead restores the legacy unmetered technique adoption; it is not this
control.)

Learning outcome. A course teaches the trade a learner practises when
enrolling: completion raises the learner's skill in that occupation
(``AgentPool.skills[slot * 5 + occupation]``) by ``COMPLETION_GAIN``, never
above 1. Existing native consumers then read it: the hybrid write-back of a
civilization's military, economy and culture from its soldiers', merchants',
scholars' and priests' active skill (``AgentPool::compute_aggregates``), the
purpose need (``needs.rs``) and the named-character promotion gate (skill
above 0.9 for 20 turns). Ordinary practice also raises skill by 0.05 a turn
up to 1, so a course brings capability forward; it does not raise the
ceiling. The skill is the person's: it travels with a migrant and counts for
whichever civilization controls the region they live in. Individual skill is
kept distinct from regional technique practice, which academy services keep
scaling from delivered learner-equivalents as before.

Cohorts. At most one open cohort per live academy incarnation (seat index,
region, founder, founding turn, name; the academy-services binding) and
``MAX_COHORTS`` in all; at most ``MAX_LEARNERS`` members with stable ids. A
cohort forms only where the academy holds paid supplies for at least one
learner and at least ``MIN_COHORT`` people are eligible:
living adults who are not Scholars (Scholars teach), resident in the
academy's region, not on a merchant trip, not on an army roster, not already
holding work this turn (shared work registry, rural health care) and with
room to learn (current-occupation skill at most ``ELIGIBLE_SKILL_MAX``),
lowest skill first, then stable id. Cohorts are finite: nobody joins later.

Each turn, immediately before the native agent tick (after Phase 2 health
work and workshop crews are in the registry), the native planner reports
every active member's availability. Dead members exit (``died``); members in
another region exit (``migrated``: completed learning already went with
them, unfinished progress does not); members practising another occupation
exit (``occupation_changed``); members on a trip, enlisted or holding other
work miss the session and exit (``absent``) after ``ABSENCE_LIMIT``
consecutive misses. Available members are reserved in the work registry
(category learning) for ``ATTENDANCE_FRACTION`` of the turn. The native
wealth phase then seats them from this turn's actual delivered academy
teaching (one delivered Scholar work unit seats ``LEARNERS_PER_SCHOLAR``
learners, the academy-services unit, each backed by one paid craft that
academy services consumes) and withholds the attended fraction of a seated
learner's ordinary occupational income. No teacher, no supplies or unpaid
upkeep means no teaching, no seat, no cost and no progress that turn.

Seats go to members in enrolment order. After the tick, each seated
learner gains one attended session; at
``SESSIONS_TO_COMPLETE`` sessions the member completes and, in ``learn``
mode, the skill is granted; it is read by the consumers from the next native
tick. A cohort without a session for ``STALL_LIMIT`` turns closes
(``stalled``); one whose academy falls or is replaced closes
(``academy_lost``: progress is not transferred to a successor academy);
one with no active member left closes (``finished``). Closed cohorts are
archived (``MAX_ARCHIVE``), the latest completions kept (``MAX_GRADUATES``).

Timing and identity: observations are dated by ``source_turn``; unknown is
None, never zero. No randomness is drawn. All parameters below are declared
modeling choices, not calibrated.
"""
from __future__ import annotations

import math

from chronicler.learning_cohorts_state import (
    ATTENDANCE_OUTCOMES, COUNTERS, MAX_ARCHIVE, MAX_COHORTS, MAX_GRADUATES, MAX_LEARNERS,
    MEMBER_STATUSES, Cohort, CohortMember, CohortReceipt, Graduate, LearningCohortState,
)
from chronicler.switch_state import sub_state_getter

ATTENDANCE_FRACTION = 0.5
SESSIONS_TO_COMPLETE = 4
COMPLETION_GAIN = 0.25
ELIGIBLE_SKILL_MAX = 0.75
MIN_COHORT = 2
ABSENCE_LIMIT = 3
STALL_LIMIT = 6

_NATIVE = ("plan_learners", "reserve_learning_attendance", "take_learning_attendance",
           "cancel_learning_attendance", "grant_learning_skill")
_UNAVAILABLE = ("on_trip", "enlisted", "assigned")


class _CohortTurn:
    """One cohort's decisions before the tick (committed after it)."""

    __slots__ = ("cohort", "new", "exits", "unavailable", "reserved", "closing")

    def __init__(self, cohort: Cohort, new: bool, closing: str | None = None):
        self.cohort, self.new, self.closing = cohort, new, closing
        self.exits: dict[int, str] = {}
        self.unavailable: dict[int, str] = {}
        self.reserved: list[int] = []


class _Pending:
    __slots__ = ("turn", "cohorts", "reserved", "academies")

    def __init__(self, turn: int, cohorts: list[_CohortTurn], reserved: bool, academies: int):
        self.turn, self.cohorts, self.reserved, self.academies = turn, cohorts, reserved, academies


_state = sub_state_getter("learning_cohorts")


def _bump(state: LearningCohortState, key: str, amount: float = 1) -> None:
    state.bump(key, amount)


def _close(state: LearningCohortState, cohort: Cohort, turn: int, reason: str, exit_reason: str) -> None:
    for m in cohort.members:
        if m.status == "active":
            m.status, m.exit_turn, m.exit_reason = "exited", turn, exit_reason
            _bump(state, "exit_" + exit_reason)
    cohort.status, cohort.closed_turn, cohort.closed_reason = "closed", turn, reason
    _bump(state, "cohorts_" + reason)
    state.cohorts = [c for c in state.cohorts if c is not cohort]
    state.archive.append(cohort)
    del state.archive[:-MAX_ARCHIVE]


def set_learning_cohorts_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    mode = getattr(args, "learning_cohort_mode", None) if args is not None else None
    state = _state(world)
    if state is None:
        world.livelihoods.learning_cohorts = state = LearningCohortState(mode=mode or "learn")
    elif mode is not None and mode != state.mode:
        if state.cohorts:
            raise ValueError("cannot switch the learning cohort mode while cohorts are open")
        state.mode = mode
    if not value and state.enabled:
        if getattr(state, "_pending", None) is not None:
            raise RuntimeError("cannot disable learning cohorts while attendance is pending")
        for cohort in list(state.cohorts):
            _close(state, cohort, world.turn, "disabled", "disabled")
    state.enabled = bool(value)


def learning_cohorts_active(world) -> bool:
    state = _state(world)
    if state is None or not state.enabled or getattr(world, "agent_mode", None) != "hybrid":
        return False
    from chronicler.learning_services import learning_services_active
    return learning_services_active(world)


def _enlisted(world) -> list[int]:
    armies = getattr(getattr(world, "war_state", None), "armies", [])
    return sorted({int(aid) for army in armies for aid, _ in army.roster})


def _identity(cohort: Cohort) -> tuple:
    return (cohort.seat_id, cohort.region, cohort.founder, cohort.founded_turn, cohort.seat_name)


def before_agent_tick(world, agent_bridge, economy_result) -> None:
    """Decide exits and formation, reserve available members; mutate nothing persisted."""
    from chronicler.learning_services import (
        CRAFTS_PER_LEARNER, LEARNERS_PER_SCHOLAR, _asset_identity, _identity as _seat_identity,
        _live_academies,
    )
    state = _state(world)
    state._pending = None
    sim = agent_bridge._sim
    if not all(callable(getattr(sim, name, None)) for name in _NATIVE):
        raise RuntimeError("learning cohorts require a fresh native build with learning attendance")
    turn = world.turn
    live = _live_academies(world)
    live_ids = {_seat_identity(i, s) for i, s in live}
    turns: list[_CohortTurn] = []
    open_ = []
    for cohort in state.cohorts:
        if _identity(cohort) in live_ids:
            open_.append(cohort)
        else:
            turns.append(_CohortTurn(cohort, False, closing="academy_lost"))
    services = world.scholarship.learning_services
    assets = {_asset_identity(a): a for a in (services.inventories or []) if not a.retired}
    taken = {c.region for c in open_}
    forming = []
    for seat_id, seat in live:
        if len(open_) + len(forming) >= MAX_COHORTS:
            break
        if seat.region in taken:
            continue
        asset = assets.get(_seat_identity(seat_id, seat))
        held = asset.held if asset is not None else None
        if held is None or held < CRAFTS_PER_LEARNER:
            continue
        forming.append((seat_id, seat))
    requests = [(c.region, [m.agent_id for m in c.members if m.status == "active"], 0, ELIGIBLE_SKILL_MAX)
                for c in open_]
    requests += [(seat.region, [], MAX_LEARNERS, ELIGIBLE_SKILL_MAX) for _, seat in forming]
    plans = sim.plan_learners(turn, requests, _enlisted(world)) if requests else []
    if len(plans) != len(requests):
        raise RuntimeError("native learner plan does not match the cohort requests")
    rows: list[tuple[int, int, float]] = []
    for cohort, (members, _recruits, _counts) in zip(open_, plans[:len(open_)], strict=True):
        ct = _CohortTurn(cohort, False)
        active = {m.agent_id: m for m in cohort.members if m.status == "active"}
        if [row[0] for row in members] != list(active):
            raise RuntimeError("native learner plan does not match the cohort's members")
        for aid, code, occupation, _skill in members:
            status = MEMBER_STATUSES[code]
            member = active[aid]
            if status == "dead":
                ct.exits[aid] = "died"
            elif status == "elsewhere":
                ct.exits[aid] = "migrated"
            elif status == "not_eligible" or occupation != member.occupation:
                ct.exits[aid] = "occupation_changed"
            elif status in _UNAVAILABLE:
                ct.unavailable[aid] = status
                if member.absent_streak + 1 >= ABSENCE_LIMIT:
                    ct.exits[aid] = "absent"
            else:
                ct.reserved.append(aid)
                rows.append((aid, cohort.region, ATTENDANCE_FRACTION))
        turns.append(ct)
    for (seat_id, seat), (_members, recruits, _counts) in zip(forming, plans[len(open_):], strict=True):
        from chronicler.adaptive_livelihoods import accepts_offer
        recruits = [r for r in recruits if accepts_offer(world, int(r[0]), "academy_training")]
        if len(recruits) < MIN_COHORT:
            continue
        cohort = Cohort(cohort_id=state.next_cohort_id + sum(t.new for t in turns), seat_id=seat_id,
                        region=seat.region, founder=seat.founder, founded_turn=seat.founded_turn,
                        seat_name=seat.name, formed_turn=turn,
                        members=[CohortMember(agent_id=aid, joined_turn=turn, occupation=occupation,
                                              skill_at_join=float(skill))
                                 for aid, occupation, skill, _age in recruits])
        ct = _CohortTurn(cohort, True)
        for aid, *_ in recruits:
            ct.reserved.append(aid)
            rows.append((aid, seat.region, ATTENDANCE_FRACTION))
        turns.append(ct)
    if rows:
        sim.reserve_learning_attendance(turn, float(LEARNERS_PER_SCHOLAR), rows)
    state._pending = _Pending(turn, turns, bool(rows), len(live))


def _no_session_reason(ct: _CohortTurn, receipt) -> str:
    if not ct.reserved:
        return "no_available_member"
    if receipt is None or receipt.held_before is None:
        return "services_unknown"
    if receipt.upkeep_satisfied is not True or receipt.upkeep_applies is not True:
        return "upkeep_unmet"
    if receipt.held_before <= 0:
        return "no_supplies"
    if not receipt.scholar_upper_bound or not receipt.work_delivered:
        return "no_teacher"
    if receipt.learners_delivered is not None and receipt.learners_delivered < 1.0 - 1e-6:
        return "too_little_teaching"
    return "members_absent"


def on_pool_reset(world) -> None:
    """A rebuilt native pool (``livelihoods.bind_native_pool``): the saved
    members' ids name other people now, so every open cohort closes with
    reason ``pool_reset`` and nobody inherits a member's sessions."""
    state = _state(world)
    if state is None:
        return
    for cohort in list(state.cohorts):
        if cohort.status == "open":
            _close(state, cohort, world.turn, "pool_reset", "pool_reset")


def rollback_agent_tick(world, agent_bridge) -> None:
    """The agent tick raised: release this turn's unconsumed attendance and its
    registry rows (as academy services cancel their teaching reservation) and
    drop the pending decisions; nothing persisted changed before the tick."""
    state = _state(world)
    pending, state._pending = getattr(state, "_pending", None), None
    if pending is not None and pending.reserved:
        agent_bridge._sim.cancel_learning_attendance(pending.turn)


def after_agent_tick(world, agent_bridge) -> list:
    """Commit exits, attendance, progress and completions of the finished tick."""
    from chronicler.learning_services import CRAFTS_PER_LEARNER
    state = _state(world)
    pending, state._pending = state._pending, None
    if pending is None:
        return []
    sim = agent_bridge._sim
    turn = pending.turn
    delivered, outcomes = [], {}
    if pending.reserved:
        result = sim.take_learning_attendance(turn)
        if result is None:
            sim.cancel_learning_attendance(turn)
            raise RuntimeError("native learning attendance was not consumed by the tick")
        delivered, rows = result
        for aid, region, _fraction, code, income, charged in rows:
            outcomes[aid] = (region, ATTENDANCE_OUTCOMES[code], float(income), float(charged))
    services = world.scholarship.learning_services
    teaching = {r.seat_id: r for r in (services.teaching_receipts or []) if r.source_turn == turn}
    _bump(state, "academy_turns", pending.academies)
    pending_completion: dict[int, tuple[_CohortTurn, CohortMember]] = {}
    receipts = []
    for ct in pending.cohorts:
        cohort = ct.cohort
        if ct.new:
            cohort.cohort_id = state.next_cohort_id
            state.next_cohort_id += 1
            state.cohorts.append(cohort)
            _bump(state, "cohorts_formed")
            _bump(state, "learners_enrolled", len(cohort.members))
        if ct.closing is not None:
            exited = [m.agent_id for m in cohort.members if m.status == "active"]
            _close(state, cohort, turn, ct.closing, ct.closing)
            receipts.append(CohortReceipt(turn=turn, cohort_id=cohort.cohort_id, seat_id=cohort.seat_id,
                                          region=cohort.region, members_active=0,
                                          exited={ct.closing: exited} if exited else {}))
            continue
        receipt = teaching.get(cohort.seat_id)
        if receipt is not None and (receipt.region, receipt.founder, receipt.founded_turn, receipt.seat_name) != (
                cohort.region, cohort.founder, cohort.founded_turn, cohort.seat_name):
            receipt = None
        work = receipt.work_delivered if receipt is not None else None
        learners_delivered = receipt.learners_delivered if receipt is not None else None
        if delivered and cohort.region < len(delivered):
            native_work, _seats = delivered[cohort.region]
            if (work is None and native_work > 0) or (work is not None and abs(work - native_work) > 1e-9):
                raise RuntimeError("native learner seats do not match the academy's delivered teaching")
        active = {m.agent_id: m for m in cohort.members if m.status == "active"}
        exited: dict[str, list[int]] = {}
        for aid, reason in ct.exits.items():
            m = active.pop(aid)
            m.status, m.exit_turn, m.exit_reason = "exited", turn, reason
            exited.setdefault(reason, []).append(aid)
            _bump(state, "exit_" + reason)
        unavailable: dict[str, int] = {}
        for aid, status in ct.unavailable.items():
            unavailable[status] = unavailable.get(status, 0) + 1
            if aid in active:
                active[aid].absent_streak += 1
        _bump(state, "member_turns", len(ct.reserved) + len(ct.unavailable))
        _bump(state, "member_turns_unavailable", len(ct.unavailable))
        _bump(state, "learner_turns_reserved", len(ct.reserved))
        attended, no_seat, absent = [], [], []
        charged = 0.0
        for aid in ct.reserved:
            region, outcome, _income, cost = outcomes[aid]
            from chronicler.adaptive_livelihoods import note_work, forgone_title
            note_work(world, aid, "academy_training", paid_milli=0, withheld_milli=round(cost * 1000),
                      title_forgone_milli=forgone_title(world, region, occupation=active[aid].occupation),
                      progress=outcome == "attended", source="learning_cohorts:personal native attendance receipt")
            if region != cohort.region:
                raise RuntimeError("native attendance region does not match the cohort")
            m = active[aid]
            if outcome == "attended":
                attended.append(aid)
                charged += cost
                m.attended += 1
                m.last_attended_turn = turn
                m.absent_streak = 0
                if m.attended >= SESSIONS_TO_COMPLETE:
                    pending_completion[aid] = (ct, m)
            elif outcome == "no_seat":
                no_seat.append(aid)
                m.absent_streak = 0
            else:
                absent.append(aid)
        if learners_delivered is not None and len(attended) > math.floor(learners_delivered + 1e-6):
            raise RuntimeError("more learners attended than the academy's delivered teaching serves")
        if attended and learners_delivered is None:
            raise RuntimeError("learners attended without a known academy teaching delivery")
        session = bool(attended)
        _bump(state, "cohort_turns")
        _bump(state, "learner_turns_attended", len(attended))
        _bump(state, "learner_turns_no_seat", len(no_seat))
        _bump(state, "learner_turns_absent", len(absent))
        _bump(state, "attendance_income_charged", charged)
        _bump(state, "supplies_used_by_attendees", len(attended) * CRAFTS_PER_LEARNER)
        reason = None
        if session:
            cohort.sessions += 1
            cohort.idle_streak = 0
            cohort.last_session_turn = turn
            _bump(state, "sessions")
        else:
            cohort.idle_streak += 1
            reason = _no_session_reason(ct, receipt)
            _bump(state, "no_session_" + reason)
        receipts.append(CohortReceipt(
            turn=turn, cohort_id=cohort.cohort_id, seat_id=cohort.seat_id, region=cohort.region,
            members_active=len(active), available=list(ct.reserved), unavailable=unavailable,
            reserved=list(ct.reserved), attended=attended, no_seat=no_seat, absent=absent,
            session=session, no_session_reason=reason, teaching_work_delivered=work,
            teaching_learners_delivered=learners_delivered, income_charged=charged,
            supplies_used=len(attended) * CRAFTS_PER_LEARNER, exited=exited))
    # Completions: one native call; dead graduates (died later in the tick) exit instead.
    by_cohort = {r.cohort_id: r for r in receipts}
    if pending_completion:
        gain = COMPLETION_GAIN if state.mode == "learn" else 0.0
        grants = [(aid, m.occupation, gain) for aid, (_ct, m) in pending_completion.items()]
        for aid, occupation, alive, before, after in sim.grant_learning_skill(grants):
            ct, m = pending_completion[aid]
            r = by_cohort[ct.cohort.cohort_id]
            if not alive:
                m.status, m.exit_turn, m.exit_reason = "exited", turn, "died"
                r.exited.setdefault("died", []).append(aid)
                r.members_active -= 1
                _bump(state, "exit_died")
                _bump(state, "grants_refused")
                continue
            m.status, m.completed_turn = "completed", turn
            m.skill_before, m.skill_after = float(before), float(after)
            r.completed.append(aid)
            r.members_active -= 1
            _bump(state, "completions")
            if after > before:
                _bump(state, "capability_changes")
                _bump(state, "skill_granted", float(after) - float(before))
            state.graduates.append(Graduate(agent_id=aid, cohort_id=ct.cohort.cohort_id,
                                            region=ct.cohort.region, occupation=occupation,
                                            completed_turn=turn, skill_before=float(before),
                                            skill_after=float(after), granted=after > before))
        del state.graduates[:-MAX_GRADUATES]
    for ct in pending.cohorts:
        cohort = ct.cohort
        if ct.closing is not None or cohort.status != "open":
            continue
        if not any(m.status == "active" for m in cohort.members):
            _close(state, cohort, turn, "finished", "stalled")
        elif cohort.idle_streak >= STALL_LIMIT:
            stalled = [m.agent_id for m in cohort.members if m.status == "active"]
            _close(state, cohort, turn, "stalled", "stalled")
            by_cohort[cohort.cohort_id].exited.setdefault("stalled", []).extend(stalled)
            by_cohort[cohort.cohort_id].members_active = 0
    state.frame = receipts
    state.frame_turn = turn
    return []


def _archived(cohort: Cohort) -> dict:
    statuses = [m.status for m in cohort.members]
    return {"cohort_id": cohort.cohort_id, "seat_id": cohort.seat_id, "region": cohort.region,
            "seat_name": cohort.seat_name, "formed_turn": cohort.formed_turn,
            "closed_turn": cohort.closed_turn, "closed_reason": cohort.closed_reason,
            "sessions": cohort.sessions, "members": len(statuses),
            "completed": statuses.count("completed"), "exited": statuses.count("exited")}


def snapshot_summary(world) -> dict:
    state = _state(world)
    source = world.turn - 1
    observed = state.frame_turn == source
    return {
        "schema_version": 1, "stage": "L5", "mode": state.mode, "source_turn": source,
        "cohorts": [c.model_dump() for c in state.cohorts],
        "archive": [_archived(c) for c in state.archive],
        "graduates": [g.model_dump() for g in state.graduates],
        # None: no cohort turn was completed in the source turn (unknown, not zero).
        "receipts": [r.model_dump() for r in state.frame] if observed else None,
        "counters": {k: state.counters[k] for k in COUNTERS if k in state.counters},
        "parameters": {
            "attendance_fraction": ATTENDANCE_FRACTION, "sessions_to_complete": SESSIONS_TO_COMPLETE,
            "completion_gain": COMPLETION_GAIN, "eligible_skill_max": ELIGIBLE_SKILL_MAX,
            "min_cohort": MIN_COHORT, "max_learners": MAX_LEARNERS, "absence_limit": ABSENCE_LIMIT,
            "stall_limit": STALL_LIMIT,
        },
    }
