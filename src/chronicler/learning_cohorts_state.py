"""Persisted state of the L5 academy learning cohorts (default off).

Owned by :mod:`chronicler.learning_cohorts`. Pure data with no simulation
imports, so :mod:`chronicler.livelihoods_state` can import it.

Identities: ``region`` is the index in ``world.regions``; ``seat_id`` is the
index in ``world.scholarship.seats`` and, with ``region``, ``founder``,
``founded_turn`` and ``seat_name``, names one academy incarnation (the same
binding the academy-services inventory uses); ``agent_id`` is a native stable
id; ``cohort_id`` is a stable, never reused counter. Everything is bounded:
at most ``MAX_COHORTS`` open cohorts (one per live academy), each with at most
``MAX_LEARNERS`` members, ``MAX_ARCHIVE`` closed cohorts, ``MAX_GRADUATES``
recent completions and one completed-turn frame. Lifetime totals are scalar
counters keyed by ``COUNTERS``.

Tuple orders below are declaration orders: append new values at the end,
never reorder.
"""
from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, Field, PrivateAttr

from chronicler.switch_state import SwitchStateMixin

MAX_COHORTS = 8
MAX_LEARNERS = 8
MAX_ARCHIVE = 16
MAX_GRADUATES = 32

MODES: tuple[str, ...] = ("learn", "no_learning")
#: Why a member's enrolment ended without completion.
EXIT_REASONS: tuple[str, ...] = (
    "died", "migrated", "occupation_changed", "absent", "academy_lost", "stalled", "disabled",
    "pool_reset",
)
#: Why a cohort closed.
CLOSE_REASONS: tuple[str, ...] = ("finished", "academy_lost", "stalled", "disabled", "pool_reset")
#: A member's availability this turn, by native planner status code.
MEMBER_STATUSES: tuple[str, ...] = (
    "available", "dead", "elsewhere", "on_trip", "enlisted", "assigned", "not_eligible",
)
#: The native wealth phase's attendance outcome codes.
ATTENDANCE_OUTCOMES: tuple[str, ...] = ("pending", "attended", "no_seat", "absent")
#: Why a cohort with available members had no session (from the actual
#: teaching receipt of its academy for the same turn).
NO_SESSION_REASONS: tuple[str, ...] = (
    "no_available_member", "services_unknown", "no_supplies", "upkeep_unmet", "no_teacher",
    "too_little_teaching", "members_absent",
)

#: Lifetime counters (insertion order; the activation funnel reads them).
COUNTERS: tuple[str, ...] = (
    "academy_turns", "cohorts_formed", "learners_enrolled", "member_turns",
    "member_turns_unavailable", "learner_turns_reserved", "cohort_turns", "sessions",
    "learner_turns_attended", "learner_turns_no_seat", "learner_turns_absent",
    "attendance_income_charged", "supplies_used_by_attendees",
    "completions", "capability_changes", "skill_granted", "grants_refused",
    "no_session_no_available_member", "no_session_services_unknown", "no_session_no_supplies",
    "no_session_upkeep_unmet", "no_session_no_teacher", "no_session_too_little_teaching",
    "no_session_members_absent",
    "exit_died", "exit_migrated", "exit_occupation_changed", "exit_absent", "exit_academy_lost",
    "exit_stalled", "exit_disabled",
    "cohorts_finished", "cohorts_academy_lost", "cohorts_stalled", "cohorts_disabled",
    "exit_pool_reset", "cohorts_pool_reset",
)


class CohortMember(BaseModel):
    agent_id: int
    joined_turn: int
    #: Occupation code at enrolment; the course teaches this trade's skill.
    occupation: int
    skill_at_join: float
    attended: int = 0
    last_attended_turn: int | None = None
    #: Consecutive turns the member was unavailable (trip, army, other work).
    absent_streak: int = 0
    status: Literal["active", "completed", "exited"] = "active"
    completed_turn: int | None = None
    exit_turn: int | None = None
    exit_reason: str | None = None
    #: At completion: the learned trade's skill before and after the grant
    #: (equal in the no-learning control; None if not completed).
    skill_before: float | None = None
    skill_after: float | None = None


class Cohort(BaseModel):
    cohort_id: int
    seat_id: int
    region: int
    founder: int
    founded_turn: int
    seat_name: str
    formed_turn: int
    status: Literal["open", "closed"] = "open"
    closed_turn: int | None = None
    closed_reason: str | None = None
    members: list[CohortMember] = Field(default_factory=list)
    sessions: int = 0
    #: Consecutive turns without a session (bounded by the stall limit).
    idle_streak: int = 0
    last_session_turn: int | None = None


class CohortReceipt(BaseModel):
    """One open cohort's completed turn: who was planned, who attended and why not.

    ``teaching_learners_delivered`` is the academy's actual delivered
    learner-equivalents from the same turn's academy-services receipt (None:
    unknown); ``attended`` never exceeds it. ``income_charged`` is the
    ordinary occupational income the native wealth phase withheld from the
    attending members (their actual attendance cost).
    """

    turn: int
    cohort_id: int
    seat_id: int
    region: int
    members_active: int
    available: list[int] = Field(default_factory=list)
    unavailable: dict[str, int] = Field(default_factory=dict)
    reserved: list[int] = Field(default_factory=list)
    attended: list[int] = Field(default_factory=list)
    no_seat: list[int] = Field(default_factory=list)
    absent: list[int] = Field(default_factory=list)
    session: bool = False
    no_session_reason: str | None = None
    teaching_work_delivered: float | None = None
    teaching_learners_delivered: float | None = None
    income_charged: float = 0.0
    supplies_used: float = 0.0
    completed: list[int] = Field(default_factory=list)
    exited: dict[str, list[int]] = Field(default_factory=dict)


class Graduate(BaseModel):
    agent_id: int
    cohort_id: int
    region: int
    occupation: int
    completed_turn: int
    skill_before: float
    skill_after: float
    granted: bool


class LearningCohortState(SwitchStateMixin, BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["learn", "no_learning"] = "learn"
    cohorts: list[Cohort] = Field(default_factory=list)
    archive: list[Cohort] = Field(default_factory=list)
    graduates: list[Graduate] = Field(default_factory=list)
    next_cohort_id: int = 0
    frame_turn: int | None = None
    frame: list[CohortReceipt] = Field(default_factory=list)
    counters: dict[str, float] = Field(default_factory=dict)
    _pending: object | None = PrivateAttr(default=None)
    _BUMP: ClassVar[dict] = {"allowed": COUNTERS}
