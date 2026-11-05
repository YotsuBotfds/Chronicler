"""Persisted state of RS1 apprenticeship and skill continuity (``--apprenticeship``, default off).

Owned by :mod:`chronicler.apprenticeship`. Pure data with no simulation imports, so
:mod:`chronicler.livelihoods_state` can import it. A world that never enabled the
switch has no sub-state, so feature-off output is unchanged.

Identities: ``agent_id`` is a native stable id (never a slot); ``site`` is the L1
workshop site id; ``region`` is an index in ``world.regions``; ``settlement_id`` is
the city's settlement id; civilizations are indices in ``world.civilizations``.

Bounded containers:

* ``qualifications``: held workshop qualifications of living people (at most
  ``MAX_QUALIFIED``; a grant beyond it is refused and counted);
* ``retired``: the latest ``MAX_RETIRED`` qualifications whose holder died or whose
  pool was rebuilt (``pool_reset``);
* ``service``: operating crew-turns per stable id toward a service qualification
  (at most ``MAX_SERVICE`` entries; the least recently seen is evicted and counted);
* ``apprenticeships``: open apprenticeships (at most ``PER_SITE`` per open site);
* ``archive``: the latest ``MAX_ARCHIVE`` ended apprenticeships;
* ``sites``: one continuity record per open workshop site;
* ``events``: the latest ``MAX_EVENTS`` dated continuity events;
* ``frame``: the last completed turn's per-site receipts (one frame).

``no_qualification`` is the cost-retaining control: the same wear, attendance and
costs, and no qualification from a completed apprenticeship.

Schema and rules versions (PL2). ``schema_version`` is also the version of the
RS1 rules the state runs under (:attr:`ApprenticeshipState.rules_version`):

* ``1``: the RS1 rules as merged (presence in the city box, exclusive seats
  reserved before the crew, the consecutive-miss dropout). Only a state saved
  before PL2 (an exact checkpoint or a state file) carries it; it resumes under
  those rules, unchanged, and serializes exactly as before.
* ``2``: RS1 rules version 2, the default of every new state (attendance by
  region, portable gap-tolerant progress, training on the job). Its records
  carry the fields marked "v2" below; in a version-1 state they are None and
  omitted from every dump.

Pickles written before PL2 lack the fields added since; exact pickle
restoration bypasses defaults, so ``__setstate__`` fills them (None).

Tuple orders below are declaration orders: append new values at the end, never
reorder.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr, model_validator

#: Modes (first: the default when enabled).
MODES: tuple[str, ...] = ("train", "no_qualification")

MAX_QUALIFIED = 512
MAX_RETIRED = 64
MAX_SERVICE = 256
MAX_ARCHIVE = 64
MAX_EVENTS = 64
#: At most this many distinct mentors are remembered per apprenticeship.
MAX_MENTORS = 8

#: How a qualification was earned.
VIA: tuple[str, ...] = ("service", "apprenticeship")
#: Why a held qualification was retired (``pool_reset``: the stable id names
#: someone else in a rebuilt pool).
RETIRE_REASONS: tuple[str, ...] = ("died", "pool_reset")
#: Why an apprenticeship ended. ``completed`` is the only successful ending; the
#: grant then depends on the mode (``granted``).
END_REASONS: tuple[str, ...] = (
    "completed", "dropout", "died", "migrated", "departed", "occupation_changed",
    "site_closed", "remobilised", "pool_reset", "disabled", "service_qualified",
    # v2: more than ``MAX_GAP`` consecutive turns absent (no open site with room
    # in the region the apprentice lives in).
    "long_absence",
)
#: Why an open apprenticeship missed a turn (an interruption).
MISS_REASONS: tuple[str, ...] = (
    "unavailable", "no_mentor", "site_not_operating", "reservation_refused", "away",
    # v2: no open workshop site in the apprentice's region (absent), or that
    # region's site already holds ``PER_SITE`` apprenticeships (no_room).
    "absent", "no_room",
)
#: v2: how an attending apprentice was aboard the site's crew.
ABOARD: tuple[str, ...] = ("crew", "attached")
#: Dated continuity events.
EVENT_KINDS: tuple[str, ...] = ("teaching_lost", "teaching_restored", "conquest")
#: A turn's stipend outcome for one apprentice.
STIPEND_STATUS: tuple[str, ...] = (
    "paid", "partial", "no_payroll", "no_firm", "unpaid_labor", "no_cash", "absent",
)

#: Lifetime counters (insertion order; the activation funnel reads them).
COUNTERS: tuple[str, ...] = (
    "turns", "site_turns", "operating_site_turns", "crew_turns_served",
    "qualified_service", "qualified_apprenticeship", "grants_refused_cap", "service_evicted",
    "retired_died", "retired_pool_reset",
    "mentor_turns", "upkeep_work", "upkeep_offset", "wear", "teaching_work",
    "sites_without_qualified_turns",
    "candidate_turns", "seats_offered", "enrolled", "veterans_enrolled", "seat_refused",
    "apprentice_turns_reserved", "apprentice_turns_attended",
    "miss_unavailable", "miss_no_mentor", "miss_site_not_operating", "miss_reservation_refused",
    "miss_away",
    "income_forgone", "stipends_due", "stipends_paid", "stipends_residual",
    "completions", "completions_granted",
    "end_completed", "end_dropout", "end_died", "end_migrated", "end_departed",
    "end_occupation_changed", "end_site_closed", "end_remobilised", "end_pool_reset", "end_disabled",
    "end_service_qualified",
    "teaching_lost", "teaching_restored", "conquests",
    # v2 (RS1 rules version 2) and the PL2 useful-work records.
    "miss_absent", "miss_no_room", "end_long_absence", "transferred",
    "apprentice_turns_on_crew", "apprentice_turns_attached",
    "qualified_crew_turns", "graduate_crew_turns", "graduates", "graduates_died", "graduates_refused_cap",
    "covered_site_turns", "full_offset_site_turns",
    "upkeep_offset_apprenticeship", "upkeep_offset_service", "upkeep_offset_graduates",
)


def _is_none(value) -> bool:
    return value is None


def _v2(default=None, **kwargs):
    """A field only version-2 states set: None (and omitted) in a version-1 state."""
    return Field(default=default, exclude_if=_is_none, **kwargs)


class _Record(BaseModel):
    """Restores pickles written before PL2 (which lack its fields) exactly."""

    def __setstate__(self, state):
        super().__setstate__(state)
        for name, field in type(self).model_fields.items():
            if name not in self.__dict__:
                self.__dict__[name] = field.get_default(call_default_factory=True)


class Qualification(BaseModel):
    """A workshop qualification held by one person for life. It travels with
    them: ``site``/``settlement_id``/``region`` say where it was earned and
    ``seen_*`` where the holder was last observed living."""

    agent_id: int
    earned_turn: int
    site: int
    settlement_id: int
    region: int
    via: Literal["service", "apprenticeship"]
    seen_turn: int
    seen_region: int
    seen_settlement: int
    status: Literal["held", "retired"] = "held"
    retired_turn: int | None = None
    retired_reason: str | None = None


class ServiceRecord(BaseModel):
    """Operating crew-turns toward a service qualification (any site)."""

    agent_id: int
    crew_turns: int = 0
    last_turn: int
    last_site: int


class Apprenticeship(_Record):
    """One apprenticeship. In version 2 ``site``/``settlement_id``/``region`` are
    the site it is attached to now (a migrant transfers to the site of the
    region they live in); ``first_site`` is where it began."""

    agent_id: int
    site: int
    settlement_id: int
    region: int
    started_turn: int
    veteran: bool = False
    attended: int = 0
    #: Consecutive missed turns (a dropout after more than ``MAX_GAP``).
    gap: int = 0
    interruptions: int = 0
    last_attended_turn: int | None = None
    #: Distinct mentors who taught this apprentice (bounded, first seen first).
    mentors: list[int] = Field(default_factory=list)
    #: Ordinary income the native wealth phase withheld for attended time.
    income_forgone: float = 0.0
    #: Stipends received from the site's firm (milli-units).
    stipends: int = 0
    status: Literal["active", "completed", "ended"] = "active"
    ended_turn: int | None = None
    ended_reason: str | None = None
    #: At completion: whether the qualification was granted (False in the control).
    granted: bool | None = None
    #: v2: consecutive absent turns (``absent`` or ``no_room``); more than
    #: ``MAX_GAP`` end the apprenticeship (``long_absence``).
    absent: int | None = _v2()
    #: v2: the site it began at, its age then, and how often it moved site.
    first_site: int | None = _v2()
    entry_age: int | None = _v2()
    transfers: int | None = _v2()
    #: v2: attended turns on the planned crew and attached to it.
    on_crew: int | None = _v2()
    attached: int | None = _v2()


class SiteContinuity(BaseModel):
    """Teaching capacity of one open workshop site's community."""

    site: int
    region: int
    settlement_id: int
    city_name: str
    controller: int | None = None
    #: Qualified people living in the site's region (one site per region: its
    #: community) at the start of the last observed turn.
    present: list[int] = Field(default_factory=list)
    observed_turn: int | None = None
    last_present_turn: int | None = None
    teaching_lost_turn: int | None = None


class ContinuityEvent(BaseModel):
    turn: int
    kind: str
    site: int | None = None
    region: int | None = None
    ids: list[int] = Field(default_factory=list)
    detail: dict[str, int | str | None] = Field(default_factory=dict)


class Seat(_Record):
    """One open apprenticeship's turn at a site: taught, missed or ended."""

    agent_id: int
    new: bool = False
    veteran: bool = False
    mentor: int | None = None
    outcome: Literal["attended", "missed", "ended"]
    #: ``missed``: the interruption (``MISS_REASONS``); ``ended``: the ending
    #: decided before or during the tick (``END_REASONS``).
    reason: str | None = None
    #: An ending this turn's outcome caused (``completed`` or ``dropout``).
    ending: str | None = None
    #: Share of the turn reserved (and, when attended, withheld from ordinary income).
    share: float = 0.0
    #: Ordinary income withheld for the attended time (None: not attended or no
    #: wealth-phase observation; unknown, not zero).
    income_forgone: float | None = None
    stipend_due: int = 0
    stipend_paid: int = 0
    stipend_status: str | None = None
    #: v2: ``crew`` (a member of the planned crew, training on crew time) or
    #: ``attached`` (reserved for ``APPRENTICE_FRACTION`` beside the crew).
    aboard: str | None = _v2()
    #: v2: the site this record transferred from this turn.
    transferred_from: int | None = _v2()


class SiteReceipt(_Record):
    """One open site's completed turn. Work is in person-turns of the crew's
    diverted time; for an operating site ``crew_work = craft_work +
    upkeep_work + teaching_work`` (crew time is never counted twice)."""

    turn: int
    site: int
    region: int
    settlement_id: int
    controller: int | None = None
    operating: bool = False
    crew: list[int] = Field(default_factory=list)
    #: Qualified people living in the site's settlement and region this turn
    #: (who can be on its crew: this turn's teaching capacity).
    qualified_present: list[int] = Field(default_factory=list)
    #: Qualified people living anywhere in the site's region (its community).
    qualified_in_region: list[int] = Field(default_factory=list)
    #: Qualified members of this turn's crew (upkeep and teaching).
    qualified_on_crew: list[int] = Field(default_factory=list)
    mentors: list[int] = Field(default_factory=list)
    crew_work: float = 0.0
    craft_work: float = 0.0
    upkeep_work: float = 0.0
    teaching_work: float = 0.0
    condition_before: float | None = None
    wear: float = 0.0
    upkeep_offset: float = 0.0
    net_wear: float = 0.0
    condition_after: float | None = None
    residents: int = 0
    candidates: int = 0
    eligible: int = 0
    seat_capacity: int = 0
    seats: list[Seat] = Field(default_factory=list)
    service_qualified: list[int] = Field(default_factory=list)
    completed: list[int] = Field(default_factory=list)
    teaching_lost: bool = False
    stipend_status: str | None = None
    # v2 useful-work records of an operating site-turn (None in version 1).
    #: Completed apprentices (either mode) on the crew.
    graduates_on_crew: list[int] | None = _v2()
    #: An operating site-turn with at least one qualified crew member.
    covered: bool | None = _v2()
    #: The whole wear was offset by qualified upkeep.
    full_offset: bool | None = _v2()
    #: The upkeep offset by the route of the qualification that delivered it
    #: (``apprenticeship``, ``service``), and by completed apprentices.
    offset_by_via: dict[str, float] | None = _v2()
    offset_by_graduates: float | None = _v2()


class GraduateRecord(BaseModel):
    """v2: a living person who completed an apprenticeship (granted or, in the
    control, not), and the work they did on operating crews since."""

    agent_id: int
    completed_turn: int
    site: int
    region: int
    granted: bool
    crew_turns: int = 0
    upkeep_offset: float = 0.0
    last_crew_turn: int | None = None


class ApprenticeshipState(_Record):
    #: Also the RS1 rules version (see the module docstring): 1 only in a state
    #: saved before PL2, 2 for every new state.
    schema_version: Literal[1, 2] = 2
    enabled: bool = True
    mode: Literal["train", "no_qualification"] = "train"
    #: Scalar lifetime counters (bounded: the fixed key set ``COUNTERS``).
    counters: dict[str, float] = Field(default_factory=dict)
    qualifications: list[Qualification] = Field(default_factory=list)
    retired: list[Qualification] = Field(default_factory=list)
    service: list[ServiceRecord] = Field(default_factory=list)
    apprenticeships: list[Apprenticeship] = Field(default_factory=list)
    archive: list[Apprenticeship] = Field(default_factory=list)
    sites: list[SiteContinuity] = Field(default_factory=list)
    events: list[ContinuityEvent] = Field(default_factory=list)
    frame_turn: int | None = None
    frame: list[SiteReceipt] = Field(default_factory=list)
    #: Continuity totals of the frame's turn (qualified alive anywhere versus
    #: present at the sites; sites without a qualified resident).
    continuity: dict[str, int | list[int]] = Field(default_factory=dict)
    #: The last turn whose apprenticeship pass settled (exactly-once guard).
    last_settled_turn: int | None = None
    #: v2: living graduates (at most ``MAX_QUALIFIED``; the dead are dropped).
    graduates: list[GraduateRecord] | None = _v2()
    #: v2: the frame turn's misses of open apprenticeships whose site is not
    #: open (absent after a closure or a move), with their site of record.
    detached: list[Seat] | None = _v2()
    _pending: object | None = PrivateAttr(default=None)

    @property
    def rules_version(self) -> int:
        return int(self.schema_version)

    @model_validator(mode="after")
    def _rules_fields(self):
        if self.schema_version == 1 and (self.graduates is not None or self.detached is not None):
            raise ValueError("a version-1 apprenticeship state has no version-2 records")
        return self
