"""RS1 apprenticeship and skill continuity (``--apprenticeship``, default off).

Requires ``--workshops`` in ``operate`` mode and ``--agents hybrid``. Modes
(``--apprenticeship-mode``): ``train`` (default) and the cost-retaining control
``no_qualification``. Phase plan:
``docs/superpowers/roadmaps/recovery-skills-phase.md`` (RS1); integration page:
``docs/integration/apprenticeship.md``.

Why a separate record. Occupation skill rises by 0.05 every turn in a person's
current trade whether or not they work and never decays, and farmer skill feeds
no capacity, so it cannot say who can keep a workshop. RS1 keeps an explicit
**workshop qualification** by stable id, ``{agent_id, earned_turn, site,
settlement_id, region, via}``. It never touches ``pool.skills``. It is held for
life and travels with the person: a migrant is qualified wherever they live; a
death retires the record (dated).

* **Service.** A crew member of an *operating* site (the funded L1 crew whose
  work replaced the craft ceiling that turn) counts one crew-turn, taken from the
  actual planned crews. ``SERVICE_TURNS`` crew-turns at any site earn a
  qualification ``via="service"`` (in both modes: this is how the first mentors
  appear, with no external grant).
* **Apprenticeship.** ``COMPLETION_TURNS`` attended turns earn one
  ``via="apprenticeship"`` in ``train`` mode only.

What it enables (the real activity). With the switch on (both modes) a funded
operating site wears ``OPERATING_WEAR`` per turn (the RS0 ``_operating_wear``
seam; the constant now lives in :mod:`chronicler.operating_wear`, PL2, and
``--apprenticeship`` implies that wear). Qualified crew members present that turn do the upkeep: in crew order
each spends up to ``UPKEEP_SHARE`` of their crew time, only as much as the turn's
wear needs, and each unit of upkeep work offsets ``WEAR_PER_UPKEEP_WORK`` of
condition, so the offset never exceeds the wear and condition stays in [0, 1]. A
site with no qualified person on its crew wears down; below
``workshops.OPERATE_CONDITION`` it cannot operate until repaired (RS2 when that
is on, otherwise the existing L1 lump). Upkeep and teaching time come out of the
crew's time: the craft work allocated (and so the craft ceiling, ``K x work``) is
the crew's diverted time minus upkeep and teaching (the workshops
``_crew_maintenance`` seam). Crew time is reserved and paid once, as before.

Crew order. While the switch is active the crew planner lists living qualified
ids first (then any RS3 veterans, then ascending id), so a qualified resident is
on the crew whenever the site's crew cap allows (``workshops._crew_priority``).

Mentors and apprentices. Before the crews are planned
(``workshops._before_crews``), two read-only native planner passes with this
turn's requests (``plan_workshop_crews`` without a turn) find, per site, the
qualified people who will be on this turn's crew (the first ``max_workers``
eligible qualified ids: the mentors) and the eligible non-qualified residents.
Apprentices must be living adult urban Farmers resident in the site's settlement
and region, not on a trip or an army roster, not holding other work this turn
and not qualified (the crew pool's predicate, the planner's exclusions);
veterans come first (``veteran_reintegration.priority_ids``), then ascending id.
A site that cannot operate (building, or worn without an allowed repair) seats
nobody. Each predicted mentor teaches up to ``PER_MENTOR`` apprentices; a site
has at most ``PER_SITE`` open apprenticeships. Continuing apprentices keep their
seats first (enrolment order); new ones fill what remains. Seated apprentices
are reserved in the shared work registry (category 2, ``apprentice``) for
``APPRENTICE_FRACTION`` of the turn **before** the planner runs, so the crew
excludes them. After funding is planned, each actual qualified crew member
(mentor) is assigned up to ``PER_MENTOR`` seated apprentices in seat order and
spends ``TEACH_SHARE`` of their crew time per apprentice taught.

Costs. An apprentice who is taught (attends) gives up ``APPRENTICE_FRACTION``
of their ordinary occupational income through the shared paid-work seam
(``extend_paid_work`` in ``finish_phase2``; L6a payroll installs first). The
amount comes from the shared receipt after the tick
(``livelihoods.paid_work_receipt``). With ``--workshop-payroll`` (mode not
``unpaid_labor``) the site's firm pays each attending apprentice a stipend of
``STIPEND_PER_WORK`` per unit of attended time from its cash, after this turn's
wages, under transfer purpose 2 (``apprentice_stipend``), once per turn and site
(``workshop_payroll.pay_from_firm``); short cash is shared pro rata and is not
owed. Without payroll, or without a firm at the site, the time is unpaid.

Attendance and endings. A turn counts only if the apprentice was reserved, the
site operated and a mentor on its crew taught them, and the apprentice survived
the tick. Any other turn of an open apprenticeship is an interruption
(``unavailable``, ``no_mentor``, ``site_not_operating``,
``reservation_refused``); more than ``MAX_GAP`` in a row is a ``dropout``.
Dated endings: ``completed``, ``dropout``, ``died``, ``migrated`` (another
region), ``departed`` (left the city in the same region), ``occupation_changed``,
``site_closed``, ``remobilised`` (on an army roster), ``pool_reset`` and
``disabled``. A change of the site's controller (conquest) does not end an
apprenticeship: the site, its condition, arrears and firm belong to the asset
and follow it through a change of controller (L1/L6a), so teaching continues
under the new ruler; a dated ``conquest`` event names the open apprentices.
Losing the city closes the site and ends its apprenticeships ``site_closed``.

Continuity. Per open site and turn: the qualified people living in its
settlement and region at the start of the turn (the community's teaching
capacity) and those on its crew; separately, qualified people alive anywhere
(retained by people). A dated ``teaching_lost`` event fires when a site that had
a qualified resident has none, naming where each went (died or the region they
live in now) and how many still hold their record; ``teaching_restored`` when
one returns. :func:`qualified_ids` serves RS2 repair crews.

Rules version 2 (PL2; every new state; ``docs/integration/apprenticeship.md``,
"RS1 rules version 2"). The paragraphs above describe version 1, which only a
state saved before PL2 runs (it resumes under those rules unchanged). Version 2
changes who attends and how progress is kept; wear, upkeep, service, teaching
time, stipends, mentors and the qualification are as above:

* Crews are planned exactly as before (qualified first, RS3 veterans, then
  ascending id); nobody is reserved ahead of them, so no crew is displaced.
* Presence is by region: an open apprenticeship continues while the apprentice
  lives in the region of an open site. A migrant transfers to the site of the
  region they now live in (when it holds fewer than ``PER_SITE``).
* Training is on the job. At an operating site (:func:`crew_maintenance`) an
  apprentice on the planned crew trains on crew time; one who is not (the native
  planner draws only the city's adult urban farmers, so a resident outside the
  city box is never on it) is *attached*: reserved for ``APPRENTICE_FRACTION``
  after the crew was planned, that share of ordinary income withheld, and a
  stipend from firm cash with L6a; attached time adds no craft work. A turn
  counts when a qualified crew member (``PER_MENTOR`` each) teaches them.
* Missed turns pause progress. Only a long absence ends it: more than
  ``MAX_GAP`` consecutive turns living where no open site (with room) is
  (``long_absence``). Death, an occupation change, an army roster, a service
  qualification, a pool reset and disabling end it as before; a closed site
  makes its apprentices absent until they reach another site.
* New apprentices: RS3 veterans, then members of this turn's crew, then the
  region's other adult farmers (attached); youngest first within each, and
  nobody older than :func:`max_entry_age` (they would reach ``AGE_ELDER``
  before completing).
* Useful-work records per operating site-turn: the qualified members aboard,
  the graduates on the crew, coverage, full offset and the upkeep offset by
  qualification route and by graduates; ``graduates`` keeps every living
  person who completed (either mode) and their crew-turns since.

Identity, timing and bounds: stable native ids only; observations are dated by
``source_turn`` and unknown is None, never zero; no RNG is drawn; every list is
bounded (``apprenticeship_state``). ``on_pool_reset`` retires every qualification
and ends every apprenticeship with reason ``pool_reset``. A failed Phase 2 or
agent tick charges nothing: the paid-work extension is cancelled and nothing
persisted changes (registry rows of the failed turn are dropped by the next
turn's first reservation, as for workshop crews). All parameters below are
declared modeling choices, not calibrated.
"""
from __future__ import annotations

import math

from chronicler import operating_wear as _ow
from chronicler.apprenticeship_state import (
    COUNTERS, MAX_ARCHIVE, MAX_EVENTS, MAX_MENTORS, MAX_QUALIFIED, MAX_RETIRED, MAX_SERVICE, MODES,
    Apprenticeship, ApprenticeshipState, ContinuityEvent, GraduateRecord, Qualification, Seat,
    ServiceRecord, SiteContinuity, SiteReceipt,
)
# Moved unchanged to ``operating_wear`` (PL2); RS1 reads it there at call time.
from chronicler.operating_wear import OPERATING_WEAR  # noqa: F401  (re-exported)
from chronicler.switch_state import health_holders, sub_state_getter

#: RS1 rules version of every new state (``ApprenticeshipState.schema_version``);
#: a state saved under version 1 keeps it (see ``apprenticeship_state``).
RULES_VERSION = 2

# Declared, uncalibrated modeling choices.
#: Operating crew-turns (at any site) that earn a service qualification.
SERVICE_TURNS = 12
#: Most of a qualified crew member's crew time spent on upkeep in one turn.
UPKEEP_SHARE = 0.25
#: Condition one unit of upkeep work (one person's whole turn) offsets.
WEAR_PER_UPKEEP_WORK = 0.2
#: Share of a mentor's crew time per apprentice taught.
TEACH_SHARE = 0.2
PER_MENTOR = 2
PER_SITE = 4
#: Share of an apprentice's turn reserved for training (and withheld from income).
APPRENTICE_FRACTION = 0.5
#: Version 1: consecutive missed turns tolerated; one more is a dropout.
#: Version 2: consecutive absent turns tolerated (no open site with room in the
#: apprentice's region); one more ends it (``long_absence``). Other missed
#: turns pause progress and never end it.
MAX_GAP = 4
COMPLETION_TURNS = 10
#: Version 2: consecutive missed turns of any reason tolerated (pauses, and
#: absences shorter than a long absence); one more ends the apprenticeship as
#: ``stalled`` and frees its place. Declared, not tuned: twice
#: ``COMPLETION_TURNS``, so a record that has not attended for as long as two
#: whole apprenticeships no longer holds one of ``PER_SITE`` places.
MAX_PAUSE = 20
#: Stipend per unit of attended apprentice time (milli-units; half the L6a wage).
STIPEND_PER_WORK = 250

#: Native ``workshop_work::RESERVATION_CATEGORIES`` index of apprentice seats.
CATEGORY_APPRENTICE = 2
#: Native ``wealth_transfer::PURPOSES`` index of apprentice stipends.
PURPOSE_APPRENTICE_STIPEND = 2
_FARMER = 0          # Occupation::Farmer
_AGE_ADULT = 20      # agent.rs AGE_ADULT
_AGE_ELDER = 60      # agent.rs AGE_ELDER (adult mortality 0.0025, elder 0.016 a turn)
_MAX_CREW = 8
_NATIVE = ("plan_workshop_crews", "reserve_work", "work_reservations", "extend_paid_work",
           "cancel_paid_work", "take_paid_work_receipt", "get_snapshot")
#: Version 2 also reads merchant trips for apprentices outside the crew pool.
_NATIVE_V2 = ("trip_agent_ids",)


def max_entry_age() -> int:
    """Version 2 age rule: the oldest age at which an apprentice is taken on,
    so that ``COMPLETION_TURNS`` attended turns end before ``AGE_ELDER``."""
    return _AGE_ELDER - COMPLETION_TURNS


class _SiteTurn:
    """One open site's decisions this turn (committed after the agent tick)."""

    def __init__(self, site, region, settlement, city_name, diverted, max_workers, condition, controller):
        self.site, self.region, self.settlement, self.city_name = site, region, settlement, city_name
        self.diverted, self.max_workers = diverted, max_workers
        self.condition_before, self.controller = condition, controller
        self.present: list[int] = []
        self.in_region: list[int] = []
        self.mentors_pred: list[int] = []
        self.residents = self.candidates = self.eligible = self.capacity = 0
        self.refused_new = 0
        self.seats: list[tuple[int, bool, bool]] = []      # (id, new, veteran), reserved, in seat order
        self.missed: dict[int, str] = {}
        self.ended: dict[int, str] = {}
        self.operating = False
        self.crew: list[int] = []
        self.qualified_on_crew: list[int] = []
        self.assigned: dict[int, int] = {}                 # apprentice -> mentor
        self.attending: list[int] = []
        self.crew_work = self.upkeep_work = self.teaching_work = self.craft_work = 0.0
        self.wear = self.offset = self.net_wear = 0.0
        self.wear_applied = False
        self.condition_after: float | None = None
        # Version 2 only.
        self.continuing: list[int] = []                    # open records present here, enrolment order
        self.transfers_in: dict[int, int] = {}             # id -> the site it moves from
        self.open_after = 0                                # records attached here after this turn
        self.pool: list[int] = []                          # new candidates, in enrolment order
        self.vets: set[int] = set()
        self.aboard: dict[int, str] = {}                   # taught id -> "crew" | "attached"
        self.new: list[int] = []
        self.taught: list[int] = []


class _Pending:
    def __init__(self, turn: int, sim, people: dict, living_q: list[int]):
        self.turn, self.sim, self.people, self.living_q = turn, sim, people, living_q
        self.held = set(living_q)
        self.sites: dict[int, _SiteTurn] = {}
        self.closed: dict[int, str] = {}                   # apprentices of sites no longer open
        self.extended = False
        self.committed = False
        self.stipends: dict[int, dict[int, int]] = {}
        self.records: dict[int, Apprenticeship] = {}
        self.receipts: dict[int, SiteReceipt] = {}
        # Version 2 only.
        self.detached: dict[int, str] = {}                 # absent records of sites not open
        self.via: dict[int, str] = {}                      # qualified id -> route (turn start)
        self.graduates: set[int] = set()                   # living graduates (turn start)
        self.trips: set[int] | None = None


# ---------------------------------------------------------------------------
# Switch and lookups
# ---------------------------------------------------------------------------

_state = sub_state_getter("apprenticeship")


def _bump(state: ApprenticeshipState, key: str, amount: float = 1) -> None:
    if key not in COUNTERS:
        raise KeyError(key)
    state.counters[key] = state.counters.get(key, 0) + amount


def set_apprenticeship_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable (with ``--apprenticeship-mode``, default ``train``, and
    ``--apprenticeship-rules``, default ``RULES_VERSION``) or disable; an
    omitted option keeps the saved value. The mode cannot change while an
    apprenticeship is open, and a saved state's rules version never changes (it
    resumes under the rules it recorded); disabling ends open apprenticeships
    (``disabled``) and keeps every qualification."""
    mode = getattr(args, "apprenticeship_mode", None) if args is not None else None
    rules = getattr(args, "apprenticeship_rules", None) if args is not None else None
    state = _state(world)
    if state is None:
        version = int(rules) if rules is not None else RULES_VERSION
        world.livelihoods.apprenticeship = state = ApprenticeshipState(
            mode=mode or MODES[0], schema_version=version,
            **({"graduates": [], "detached": []} if version >= 2 else {}))
    elif rules is not None and int(rules) != state.rules_version:
        raise ValueError(f"--apprenticeship-rules {rules} conflicts with the saved RS1 state "
                         f"(rules version {state.rules_version}, which it keeps)")
    if mode is not None and mode != state.mode:
        if state.apprenticeships:
            raise ValueError("cannot switch the apprenticeship mode while apprenticeships are open")
        state.mode = mode
    if not value and state.enabled:
        if state._pending is not None:
            raise RuntimeError("cannot disable apprenticeship while a turn is pending")
        for record in list(state.apprenticeships):
            _end(state, record, world.turn, "disabled")
    state.enabled = bool(value)


def apprenticeship_active(world) -> bool:
    state = _state(world)
    if state is None or not state.enabled or getattr(world, "agent_mode", None) != "hybrid":
        return False
    from chronicler.workshops import workshops_active
    return workshops_active(world) and world.livelihoods.workshops.mode == "operate"


def _native(sim, names=_NATIVE):
    if sim is None or not all(callable(getattr(sim, name, None)) for name in names):
        raise RuntimeError("apprenticeship requires a fresh native build with the work registry seams")
    return sim


def _v2(state: ApprenticeshipState) -> bool:
    return state.rules_version >= 2


def _people(sim) -> dict[int, tuple[int, int, int, int]]:
    """Living stable id -> (region, settlement id, occupation, age), from the
    native snapshot of the living pool."""
    snap = sim.get_snapshot()
    cols = [snap.column(name).to_pylist() for name in ("id", "region", "settlement_id", "occupation", "age")]
    return {int(i): (int(r), int(s), int(o), int(a)) for i, r, s, o, a in zip(*cols, strict=True)}


def _controller(world, region: int) -> int | None:
    name = world.regions[region].controller
    if name is None:
        return None
    return next((i for i, civ in enumerate(world.civilizations) if civ.name == name), None)


def _veterans(world, region: int) -> list[int]:
    from chronicler.workshops import _lane_active
    if not _lane_active(world, "veteran_reintegration"):
        return []
    from chronicler.veteran_reintegration import priority_ids
    out, seen = [], set()
    for aid in priority_ids(world, region):
        aid = int(aid)
        if aid not in seen:
            seen.add(aid)
            out.append(aid)
    return out


def _operable(world, site) -> bool:
    """Whether a site could operate this turn if funded: built, and in
    condition or carrying an allowed repair in its bill."""
    from chronicler.workshops import OPERATE_CONDITION, _bill
    bill = _bill(site, world)
    return "construction" not in bill and (site.condition >= OPERATE_CONDITION or "repair" in bill)


def _pending(world) -> _Pending:
    state = _state(world)
    p = getattr(state, "_pending", None) if state is not None else None
    if p is None or p.turn != world.turn:
        raise RuntimeError("apprenticeship turn missing for this workshop turn")
    return p


def _archive(state: ApprenticeshipState, record: Apprenticeship) -> None:
    state.apprenticeships = [a for a in state.apprenticeships if a is not record]
    state.archive.append(record)
    del state.archive[:-MAX_ARCHIVE]


def _end(state: ApprenticeshipState, record: Apprenticeship, turn: int, reason: str) -> None:
    record.status = "completed" if reason == "completed" else "ended"
    record.ended_turn, record.ended_reason = turn, reason
    _bump(state, "end_" + reason)
    _archive(state, record)


def _event(state: ApprenticeshipState, **fields) -> None:
    state.events.append(ContinuityEvent(**fields))
    del state.events[:-MAX_EVENTS]


def _retire(state: ApprenticeshipState, q: Qualification, turn: int, reason: str) -> None:
    q.status, q.retired_turn, q.retired_reason = "retired", turn, reason
    state.qualifications = [x for x in state.qualifications if x is not q]
    state.retired.append(q)
    del state.retired[:-MAX_RETIRED]
    _bump(state, "retired_" + reason)


def _grant(state: ApprenticeshipState, aid: int, turn: int, st: _SiteTurn, via: str, where) -> bool:
    if any(q.agent_id == aid for q in state.qualifications):
        return False
    if len(state.qualifications) >= MAX_QUALIFIED:
        _bump(state, "grants_refused_cap")
        return False
    region, settlement = where
    state.qualifications.append(Qualification(
        agent_id=aid, earned_turn=turn, site=st.site, settlement_id=st.settlement, region=st.region,
        via=via, seen_turn=turn, seen_region=region, seen_settlement=settlement))
    _bump(state, "qualified_" + via)
    return True


# ---------------------------------------------------------------------------
# Cross-lane API and workshops seams
# ---------------------------------------------------------------------------

def qualified_ids(world, region: int) -> list[int]:
    """Stable ids holding a workshop qualification, alive and living in
    ``region`` (an index in ``world.regions``), ascending; [] while the switch
    is inactive. Within a turn, before the agent tick, residence is this turn's
    start-of-turn native snapshot; otherwise the last observed residence (the end
    of the latest completed tick)."""
    state = _state(world)
    if state is None or not apprenticeship_active(world):
        return []
    p = state._pending
    if p is not None and p.turn == world.turn and not p.committed:
        return sorted(a for a in p.living_q if p.people[a][0] == region)
    return sorted(q.agent_id for q in state.qualifications if q.seen_region == region)


def seated_mentors(world) -> frozenset[int]:
    """This turn's predicted mentors that seated apprentices rely on: per site,
    the first ``ceil(seats / PER_MENTOR)`` of its predicted mentors (empty
    before ``before_crews`` or while inactive). RS2 leaves them off its repair
    crews, so a mentor counted on to teach is not taken away to repair after
    the seats were reserved (review C 2026-11-05)."""
    state = _state(world)
    p = getattr(state, "_pending", None) if state is not None else None
    if p is None or p.turn != world.turn:
        return frozenset()
    out: set[int] = set()
    v2 = _v2(state)
    for st in p.sites.values():
        # Version 2 reserves nobody before the crew: the mentors the present
        # continuing apprentices rely on are kept off repair crews instead.
        need = len(st.continuing) if v2 else len(st.seats)
        if need:
            out.update(st.mentors_pred[:math.ceil(need / PER_MENTOR)])
    return frozenset(out)


def crew_priority_ids(world) -> list[int]:
    """This turn's living qualified ids, ascending: the crew planner lists them
    first (``workshops._crew_priority``). Requires :func:`before_crews`."""
    return list(_pending(world).living_q)


def before_crews(world, sim, requests: list) -> None:
    """Seat this turn's apprentices before the native crew planner runs.

    ``requests`` are the workshop's ``(site, region, settlement, diverted
    fraction, max workers)`` rows. Decides endings, interruptions and new
    enrolments and reserves the seated apprentices in the registry (category
    2); nothing persisted changes until the tick succeeded."""
    state = _state(world)
    if state._pending is not None:
        raise RuntimeError("apprenticeship turn already pending")
    if state.last_settled_turn is not None and world.turn <= state.last_settled_turn:
        raise ValueError("apprenticeship already settled for this turn")
    _native(sim)
    from chronicler.workshops import _enlisted
    turn = world.turn
    ws = world.livelihoods.workshops
    people = _people(sim)
    enlisted = _enlisted(world)
    army = set(enlisted)
    holding = {int(row[0]) for row in sim.work_reservations(turn)}
    held = {q.agent_id for q in state.qualifications}
    living_q = sorted(a for a in held if a in people)
    p = _Pending(turn, sim, people, living_q)
    state._pending = p
    requested = [(int(s), int(r), int(st), float(d), int(m)) for s, r, st, d, m in requests]
    open_sites = {s.site: s for s in ws.sites}
    if _v2(state):
        _native(sim, _NATIVE_V2)
        _before_crews_v2(world, sim, state, p, requested, open_sites, enlisted, holding)
        return
    by_site: dict[int, list[Apprenticeship]] = {}
    for record in state.apprenticeships:
        if record.site in {r[0] for r in requested}:
            by_site.setdefault(record.site, []).append(record)
        else:
            p.closed[record.agent_id] = "site_closed"
    if not requested:
        return
    residents: dict[tuple[int, int], list[int]] = {}
    for aid, (region, settlement, occupation, age) in people.items():
        if occupation == _FARMER and age >= _AGE_ADULT:
            residents.setdefault((region, settlement), []).append(aid)
    full = [(s, r, st, d, _MAX_CREW) for s, r, st, d, _m in requested]
    qualified_rows = sim.plan_workshop_crews(full, enlisted, None, priority_ids=living_q) if living_q else None
    apprenticing = {a.agent_id for a in state.apprenticeships}
    listing: list[int] = []
    plans = []
    for site_id, region, settlement, diverted, max_workers in requested:
        site = open_sites[site_id]
        st = _SiteTurn(site_id, region, settlement, site.city_name, diverted, max_workers,
                       float(site.condition), _controller(world, region))
        p.sites[site_id] = st
        local = sorted(residents.get((region, settlement), []))
        st.residents = len(local)
        st.present = [a for a in living_q if people[a][0] == region and people[a][1] == settlement]
        st.in_region = [a for a in living_q if people[a][0] == region]
        continuing = []
        for record in by_site.get(site_id, []):
            aid = record.agent_id
            here = people.get(aid)
            if here is None:
                st.ended[aid] = "died"
            elif aid in army:
                st.ended[aid] = "remobilised"
            elif here[0] != region:
                st.ended[aid] = "migrated"
            elif here[2] != _FARMER:
                st.ended[aid] = "occupation_changed"
            elif aid in held:
                st.ended[aid] = "service_qualified"
            elif here[1] != settlement:
                # Settlement membership is positional (the city's grid cells):
                # outside the city but in the region is an interruption; a gap
                # beyond MAX_GAP away ends the apprenticeship as ``departed``.
                st.missed[aid] = "away"
            else:
                continuing.append(aid)
        from chronicler.adaptive_livelihoods import accepts_offer
        pool = [a for a in local if a not in held and a not in apprenticing and a not in army
                and accepts_offer(world, a, "apprenticeship")]
        st.candidates = len(pool)
        vets = [v for v in _veterans(world, region) if v in set(pool)]
        ordered = vets + [a for a in pool if a not in set(vets)]
        listing.extend(continuing + ordered)
        plans.append((st, site, continuing, ordered, set(vets)))
    eligible_rows = sim.plan_workshop_crews(full, enlisted, None, priority_ids=listing) if listing else None
    seat_rows: list[tuple[int, float]] = []
    for i, (st, site, continuing, ordered, vets) in enumerate(plans):
        if qualified_rows is not None:
            qualified = [int(a) for a in qualified_rows[i][8] if int(a) in p.held and int(a) not in holding]
        else:
            qualified = []
        st.mentors_pred = qualified[:st.max_workers]
        eligible = set()
        if eligible_rows is not None:
            eligible = {int(a) for a in eligible_rows[i][8] if int(a) not in holding}
        candidates = set(ordered)
        st.eligible = len(eligible & candidates)
        operable = _operable(world, site)
        st.capacity = min(PER_SITE, PER_MENTOR * len(st.mentors_pred)) if operable else 0
        seated = []
        for aid in continuing:
            if aid in st.missed:
                continue
            if not operable:
                st.missed[aid] = "site_not_operating"
            elif aid not in eligible:
                st.missed[aid] = "unavailable"
            elif len(seated) >= st.capacity:
                st.missed[aid] = "no_mentor"
            else:
                seated.append(aid)
        # Every apprenticeship not ending this turn keeps its place, seated or
        # not (an apprentice away or unavailable still holds one of PER_SITE).
        open_after = sum(1 for r in by_site.get(st.site, []) if r.agent_id not in st.ended)
        room = max(0, min(PER_SITE - open_after, st.capacity - len(seated)))
        fresh = [a for a in ordered if a in eligible][:room]
        records = {r.agent_id: r for r in by_site.get(st.site, [])}
        st.seats = [(aid, False, records[aid].veteran) for aid in seated] + \
                   [(aid, True, aid in vets) for aid in fresh]
        seat_rows.extend((aid, APPRENTICE_FRACTION) for aid, _new, _vet in st.seats)
    if not seat_rows:
        return
    try:
        sim.reserve_work(turn, CATEGORY_APPRENTICE, seat_rows)
    except ValueError:
        # All or none was refused: reserve one by one (deterministic order) so a
        # single holder does not cost everyone else their seat.
        refused = set()
        for row in seat_rows:
            try:
                sim.reserve_work(turn, CATEGORY_APPRENTICE, [row])
            except ValueError:
                refused.add(row[0])
        for st in p.sites.values():
            kept = []
            for aid, new, vet in st.seats:
                if aid not in refused:
                    kept.append((aid, new, vet))
                elif not new:
                    st.missed[aid] = "reservation_refused"
                else:
                    st.refused_new += 1          # counted when the turn commits
            st.seats = kept


def crew_maintenance(world, site, row: dict) -> float:
    """Workshops seam: this operating site's crew time spent on upkeep and
    teaching this turn (person-turns, at most the crew's ``work_available``);
    the craft work allocated is the rest. Records the upkeep offset that
    :func:`operating_wear` applies at settlement."""
    st = _pending(world).sites.get(site.site)
    if st is None:
        raise RuntimeError("operating workshop site was not prepared by apprenticeship")
    p = _pending(world)
    st.operating = True
    st.crew = [int(a) for a in row["crew"]]
    st.qualified_on_crew = [a for a in st.crew if a in p.held]
    st.crew_work = float(row["work_available"])
    d = float(row["diverted_fraction"])
    # Each qualified crew member gives up to UPKEEP_SHARE of their crew time,
    # only as much as the turn's wear needs: the offset is at most the wear.
    # (The diverted fraction is 1 - a rounded farm factor, so "enough" allows a
    # relative 1e-9 for float noise.)
    capacity = UPKEEP_SHARE * d * len(st.qualified_on_crew)
    wear = _ow.OPERATING_WEAR
    need = wear / WEAR_PER_UPKEEP_WORK
    full = capacity >= need * (1.0 - 1e-9)
    st.upkeep_work = need if full else capacity
    st.wear = wear
    st.offset = wear if full else min(wear, capacity * WEAR_PER_UPKEEP_WORK)
    st.net_wear = max(0.0, wear - st.offset)
    if _v2(_state(world)):
        seated = _aboard_v2(world, p, st)
    else:
        seated = [aid for aid, _new, _vet in st.seats if aid not in st.missed]
    st.assigned = {}
    queue = iter(seated)
    for mentor in st.qualified_on_crew:
        for _ in range(PER_MENTOR):
            aid = next(queue, None)
            if aid is None:
                break
            st.assigned[aid] = mentor
    st.teaching_work = TEACH_SHARE * d * len(st.assigned)
    used = min(st.crew_work, st.upkeep_work + st.teaching_work)
    st.craft_work = st.crew_work - used
    return used


def operating_wear(world, site) -> float:
    """Workshops seam: this turn's net wear of the funded operating ``site``:
    ``OPERATING_WEAR`` less its qualified crew's upkeep offset (in [0, wear])."""
    st = _pending(world).sites.get(site.site)
    if st is None or not st.operating:
        raise RuntimeError("operating wear requested for a site without a prepared crew")
    st.wear_applied = True
    return st.net_wear


def upkeep_offset(world, site) -> tuple[float, list[int]]:
    """PL2 seam (``operating_wear``): this turn's upkeep offset of the funded
    operating ``site`` and its qualified crew members (after :func:`crew_maintenance`)."""
    st = _pending(world).sites.get(site.site)
    if st is None or not st.operating:
        raise RuntimeError("upkeep offset requested for a site without a prepared crew")
    return st.offset, list(st.qualified_on_crew)


# ---------------------------------------------------------------------------
# Phase hooks
# ---------------------------------------------------------------------------

def finish_phase2(world, economy_result, agent_bridge, acc):
    """After workshop settlement and the L6a install: decide who was taught and
    withhold their apprentice time from ordinary income (``extend_paid_work``)."""
    p = _pending(world)
    ws = world.livelihoods.workshops
    if ws.frame_turn != world.turn:
        raise RuntimeError("workshop receipts missing for this turn")
    receipts = {r.site: r for r in ws.frame}
    sites = {s.site: s for s in ws.sites}
    rows = []
    v2 = _v2(_state(world))
    for st in p.sites.values():
        site = sites.get(st.site)
        st.condition_after = float(site.condition) if site is not None else None
        receipt = receipts.get(st.site)
        if st.operating:
            if receipt is None or abs(float(receipt.allocated) - st.craft_work) > 1e-9:
                raise RuntimeError("workshop craft work does not match the apprenticeship crew time")
            if not st.wear_applied:
                raise RuntimeError("operating wear was not applied to an operating site")
        if v2:
            rows.extend(_attending_v2(st))
            continue
        for aid, _new, _vet in st.seats:
            if aid in st.missed:
                continue
            if not st.operating:
                st.missed[aid] = "site_not_operating"
            elif aid not in st.assigned:
                st.missed[aid] = "no_mentor"
            else:
                st.attending.append(aid)
                rows.append((aid, APPRENTICE_FRACTION))
    if rows:
        p.sim.extend_paid_work(world.turn, rows)   # validated against the registry natively
        p.extended = True
    return []


def rollback_phase2(world) -> None:
    state = _state(world)
    p = getattr(state, "_pending", None) if state is not None else None
    if p is not None and p.turn == world.turn:
        if p.extended:
            p.sim.cancel_paid_work()
        state._pending = None


def rollback_agent_tick(world, agent_bridge) -> None:
    """The agent tick raised: disarm the unconsumed paid-work share and drop the
    turn's decisions; nothing persisted changed."""
    state = _state(world)
    p = getattr(state, "_pending", None) if state is not None else None
    if p is not None and p.turn == world.turn:
        if p.extended:
            p.sim.cancel_paid_work()
        state._pending = None


def on_pool_reset(world) -> None:
    """A rebuilt native pool (``livelihoods.bind_native_pool``): saved ids name
    other people now, so every qualification is retired, service progress is
    cleared and every open apprenticeship ends, each with reason ``pool_reset``
    (dated). Sites forget their present qualified people (no ``teaching_lost``:
    nobody left; the ids changed meaning)."""
    state = _state(world)
    if state is None:
        return
    turn = world.turn
    for q in list(state.qualifications):
        _retire(state, q, turn, "pool_reset")
    state.service = []
    for record in list(state.apprenticeships):
        _end(state, record, turn, "pool_reset")
    for sc in state.sites:
        sc.present = []
    if _v2(state):
        state.graduates = []
        state.detached = []
    state._pending = None


def after_agent_tick(world, agent_bridge) -> list:
    """Commit the turn: attendance, interruptions, endings, completions, service
    qualifications, retirements and continuity, against the living pool after
    the tick and the shared paid-work receipt."""
    state = _state(world)
    p = state._pending
    if p is None or p.turn != world.turn or p.committed:
        return []
    sim = agent_bridge._sim
    receipt = None
    if p.extended:
        from chronicler.livelihoods import paid_work_receipt
        receipt = paid_work_receipt(world, sim)
        if receipt is None:
            raise RuntimeError("paid work receipt missing for this turn")
    after = _people(sim)
    if _v2(state):
        _commit_v2(world, state, p, after, receipt)
    else:
        _commit(world, state, p, after, receipt)
    p.committed = True
    return []


def _commit(world, state: ApprenticeshipState, p: _Pending, after: dict, receipt) -> None:
    turn = p.turn
    train = state.mode == "train"
    _bump(state, "turns")
    active = {a.agent_id: a for a in state.apprenticeships}
    for aid, reason in sorted(p.closed.items()):
        _end(state, active.pop(aid), turn, reason)
    # Retire the qualifications of people who died (in this tick or before).
    for q in list(state.qualifications):
        if q.agent_id not in after:
            _retire(state, q, turn, "died")
    service = {r.agent_id: r for r in state.service}
    frame = []
    for st in p.sites.values():
        _bump(state, "site_turns")
        _bump(state, "candidate_turns", st.candidates)
        _bump(state, "seats_offered", st.capacity)
        _bump(state, "apprentice_turns_reserved", len(st.seats))
        if st.refused_new:
            _bump(state, "seat_refused", st.refused_new)
        seats: list[Seat] = []
        completed: list[int] = []
        for aid, reason in st.ended.items():
            record = active.pop(aid)
            seats.append(Seat(agent_id=aid, veteran=record.veteran, outcome="ended", reason=reason))
            _end(state, record, turn, reason)
        seated = {aid for aid, _new, _vet in st.seats}
        order = list(st.seats) + [(aid, False, False) for aid in st.missed if aid not in seated]
        for aid, new, veteran in order:
            if new:
                record = Apprenticeship(agent_id=aid, site=st.site, settlement_id=st.settlement,
                                        region=st.region, started_turn=turn, veteran=veteran)
                state.apprenticeships.append(record)
                active[aid] = record
                _bump(state, "enrolled")
                if veteran:
                    _bump(state, "veterans_enrolled")
            record = active[aid]
            if aid in seated and aid in after:
                # RS3: every seat reserved this turn is a dated training placement
                # of whoever holds an open veteran record (other ids are ignored),
                # in either RS3 mode and whether or not priority seated them.
                from chronicler.veteran_reintegration import note_outcome
                note_outcome(world, aid, "placed:apprentice", turn=turn,
                             detail={"site": st.site, "region": st.region, "attended": aid in st.attending})
            p.records[aid] = record
            seat = Seat(agent_id=aid, new=new, veteran=record.veteran, outcome="missed",
                        share=APPRENTICE_FRACTION if aid in seated else 0.0)
            seats.append(seat)
            if aid in st.attending:
                seat.mentor = st.assigned[aid]
                forgone = receipt[aid][2] if receipt is not None and aid in receipt else None
                seat.income_forgone = forgone
                if forgone is not None:
                    record.income_forgone += forgone
                    _bump(state, "income_forgone", forgone)
                if aid not in after:              # died later in the tick: the turn does not count
                    seat.outcome, seat.reason = "ended", "died"
                    _end(state, record, turn, "died")
                    active.pop(aid)
                    continue
                seat.outcome = "attended"
                record.attended += 1
                record.gap = 0
                record.last_attended_turn = turn
                if seat.mentor not in record.mentors and len(record.mentors) < MAX_MENTORS:
                    record.mentors.append(seat.mentor)
                _bump(state, "apprentice_turns_attended")
                seat.stipend_due = math.floor(seat.share * STIPEND_PER_WORK + 0.5)
                p.stipends.setdefault(st.site, {})[aid] = seat.stipend_due
                if record.attended >= COMPLETION_TURNS:
                    completed.append(aid)
                    _bump(state, "completions")
                    record.granted = bool(train and _grant(state, aid, turn, st, "apprenticeship",
                                                           after[aid][:2]))
                    if record.granted:
                        _bump(state, "completions_granted")
                    seat.ending = "completed"
                    _end(state, record, turn, "completed")
                    active.pop(aid)
                continue
            seat.reason = st.missed[aid]
            record.gap += 1
            record.interruptions += 1
            _bump(state, "miss_" + seat.reason)
            if record.gap > MAX_GAP:
                seat.ending = "departed" if seat.reason == "away" else "dropout"
                _end(state, record, turn, seat.ending)
                active.pop(aid)
        # Service: the crew of an operating site served this turn.
        service_qualified = []
        if st.operating:
            _bump(state, "operating_site_turns")
            _bump(state, "mentor_turns", len(set(st.assigned.values())))
            _bump(state, "upkeep_work", st.upkeep_work)
            _bump(state, "upkeep_offset", st.offset)
            _bump(state, "wear", st.wear)
            _bump(state, "teaching_work", st.teaching_work)
            held = {q.agent_id for q in state.qualifications}
            for aid in st.crew:
                if aid in held:
                    continue
                _bump(state, "crew_turns_served")
                rec = service.get(aid)
                if rec is None:
                    rec = service[aid] = ServiceRecord(agent_id=aid, last_turn=turn, last_site=st.site)
                rec.crew_turns += 1
                rec.last_turn, rec.last_site = turn, st.site
                if rec.crew_turns >= SERVICE_TURNS and aid in after:
                    if _grant(state, aid, turn, st, "service", after[aid][:2]):
                        service_qualified.append(aid)
                        del service[aid]
                        if aid in active and active[aid].site == st.site and aid not in st.ended:
                            # An apprentice without a seat this turn served on
                            # this site's crew and qualified that way. (An
                            # apprentice of another site who moved here keeps
                            # the ending decided for that site.)
                            seat = next(s for s in seats if s.agent_id == aid)
                            seat.ending = "service_qualified"
                            _end(state, active.pop(aid), turn, "service_qualified")
        if not st.in_region:
            _bump(state, "sites_without_qualified_turns")
        frame.append(SiteReceipt(
            turn=turn, site=st.site, region=st.region, settlement_id=st.settlement,
            controller=st.controller, operating=st.operating, crew=list(st.crew),
            qualified_present=list(st.present), qualified_in_region=list(st.in_region),
            qualified_on_crew=list(st.qualified_on_crew),
            mentors=sorted(set(st.assigned.values())), crew_work=st.crew_work, craft_work=st.craft_work,
            upkeep_work=st.upkeep_work, teaching_work=st.teaching_work,
            condition_before=st.condition_before, wear=st.wear, upkeep_offset=st.offset,
            net_wear=st.net_wear, condition_after=st.condition_after, residents=st.residents,
            candidates=st.candidates, eligible=st.eligible, seat_capacity=st.capacity, seats=seats,
            service_qualified=service_qualified, completed=completed))
    # Service progress of the dead lapses; the record stays bounded.
    kept = [r for aid, r in sorted(service.items()) if aid in after]
    if len(kept) > MAX_SERVICE:
        kept.sort(key=lambda r: (r.last_turn, r.crew_turns, r.agent_id))
        _bump(state, "service_evicted", len(kept) - MAX_SERVICE)
        kept = kept[len(kept) - MAX_SERVICE:]
    state.service = sorted(kept, key=lambda r: r.agent_id)
    for q in state.qualifications:
        q.seen_turn = turn
        q.seen_region, q.seen_settlement = after[q.agent_id][0], after[q.agent_id][1]
    _continuity(world, state, p, frame, after)
    state.frame = frame
    state.frame_turn = turn
    p.receipts = {r.site: r for r in frame}


def _continuity(world, state: ApprenticeshipState, p: _Pending, frame: list[SiteReceipt], after: dict) -> None:
    turn = p.turn
    records = {sc.site: sc for sc in state.sites}
    held = {q.agent_id for q in state.qualifications}
    out = []
    for receipt in frame:
        st = p.sites[receipt.site]
        sc = records.get(st.site) or SiteContinuity(site=st.site, region=st.region,
                                                    settlement_id=st.settlement, city_name=st.city_name,
                                                    controller=st.controller)
        if sc.observed_turn is not None and st.controller != sc.controller:
            apprentices = sorted(a.agent_id for a in state.apprenticeships if a.site == st.site)
            if apprentices or st.in_region:
                _event(state, turn=turn, kind="conquest", site=st.site, region=st.region, ids=apprentices,
                       detail={"from": sc.controller, "to": st.controller})
                _bump(state, "conquests")
        sc.controller = st.controller
        if sc.present and not st.in_region:
            detail: dict[str, int | str | None] = {}
            for aid in sc.present:
                detail[str(aid)] = "died" if aid not in after else f"region:{after[aid][0]}"
            detail["still_qualified"] = sum(1 for aid in sc.present if aid in held)
            detail["qualified_alive"] = len(held)
            _event(state, turn=turn, kind="teaching_lost", site=st.site, region=st.region,
                   ids=list(sc.present), detail=detail)
            _bump(state, "teaching_lost")
            sc.teaching_lost_turn = turn
            receipt.teaching_lost = True
        elif st.in_region and not sc.present and sc.teaching_lost_turn is not None:
            _event(state, turn=turn, kind="teaching_restored", site=st.site, region=st.region,
                   ids=list(st.in_region), detail={"lost_turn": sc.teaching_lost_turn})
            _bump(state, "teaching_restored")
        sc.present = list(st.in_region)
        sc.observed_turn = turn
        if st.in_region:
            sc.last_present_turn = turn
        out.append(sc)
    state.sites = out
    present = {a for receipt in frame for a in receipt.qualified_in_region}
    state.continuity = {
        "turn": turn,
        "qualified_alive": len(held),
        "qualified_in_site_regions": len(present & held),
        "qualified_in_site_cities": sum(len(r.qualified_present) for r in frame),
        "qualified_on_crews": sum(len(r.qualified_on_crew) for r in frame),
        "qualified_elsewhere": len(held - present),
        "sites": len(frame),
        "sites_without_qualified": [r.site for r in frame if not r.qualified_in_region],
        "service_in_progress": len(state.service),
    }


# ---------------------------------------------------------------------------
# RS1 rules version 2 (PL2): attendance by region, portable gap-tolerant
# progress and training on the job. Version-1 states never reach this code.
# ---------------------------------------------------------------------------

def _absent_v2(p: _Pending, record: Apprenticeship, reason: str) -> None:
    """An open record that cannot attend anywhere this turn: missed at its site
    of record when that site is open, otherwise detached."""
    st = p.sites.get(record.site)
    if st is not None:
        st.missed[record.agent_id] = reason
    else:
        p.detached[record.agent_id] = reason


def _before_crews_v2(world, sim, state: ApprenticeshipState, p: _Pending, requested: list,
                     open_sites: dict, enlisted: list[int], holding: set[int]) -> None:
    """Version 2, before the crew planner: endings, presence by region,
    transfers and the new candidates. Nobody is reserved here, so apprentices
    never displace the crew; :func:`_aboard_v2` places them after it."""
    people, army, held = p.people, set(enlisted), p.held | {q.agent_id for q in state.qualifications}
    p.via = {q.agent_id: q.via for q in state.qualifications}
    p.graduates = {g.agent_id for g in state.graduates or []}
    site_by_region = {}
    for site_id, region, settlement, diverted, max_workers in requested:
        site = open_sites[site_id]
        st = _SiteTurn(site_id, region, settlement, site.city_name, diverted, max_workers,
                       float(site.condition), _controller(world, region))
        p.sites[site_id] = st
        st.present = [a for a in p.living_q if people[a][0] == region and people[a][1] == settlement]
        st.in_region = [a for a in p.living_q if people[a][0] == region]
        site_by_region[region] = site_id
    # Endings and presence, in enrolment order. ``held_here`` counts the
    # records attached to each site after the decisions made so far; a move is
    # accepted only into room that exists when it is decided (moves are decided
    # in enrolment order), so no site ever holds more than PER_SITE.
    held_here = {site_id: 0 for site_id in p.sites}
    movers = []
    for record in state.apprenticeships:
        aid = record.agent_id
        here = people.get(aid)
        reason = None
        if here is None:
            reason = "died"
        elif aid in army:
            reason = "remobilised"
        elif here[2] != _FARMER:
            reason = "occupation_changed"
        elif aid in held:
            reason = "service_qualified"
        if reason is not None:
            if record.site in p.sites:
                p.sites[record.site].ended[aid] = reason
            else:
                p.closed[aid] = reason
            continue
        if record.site in held_here:
            held_here[record.site] += 1
        target = site_by_region.get(here[0])
        if target is None:
            _absent_v2(p, record, "absent")
        elif target == record.site:
            p.sites[target].continuing.append(aid)
        else:
            movers.append((record, target))
    for record, target in movers:
        if held_here[target] < PER_SITE:
            st = p.sites[target]
            st.continuing.append(record.agent_id)
            st.transfers_in[record.agent_id] = record.site
            held_here[target] += 1
            if record.site in held_here:
                held_here[record.site] -= 1
        else:
            _absent_v2(p, record, "no_room")
    apprenticing = {a.agent_id for a in state.apprenticeships}
    # Nobody completes twice: living graduates (either mode; in the control
    # they hold no qualification) and archived completions are never taken on
    # again (review B 2026-11-06: the control re-enrolled its own graduates).
    apprenticing |= {g.agent_id for g in state.graduates or []}
    apprenticing |= {a.agent_id for a in state.archive if a.ended_reason == "completed"}
    oldest = max_entry_age()
    region_farmers: dict[int, list[tuple[int, int]]] = {}
    for aid, (region, _settlement, occupation, age) in people.items():
        if occupation == _FARMER and age >= _AGE_ADULT and region in site_by_region:
            region_farmers.setdefault(region, []).append((age, aid))
    for st in p.sites.values():
        st.open_after = held_here[st.site]
        local = region_farmers.get(st.region, [])
        st.residents = len(local)
        # Age rule: youngest first, and nobody who would reach AGE_ELDER before
        # completing (D2: 80% of qualifications ended in death within the run).
        from chronicler.adaptive_livelihoods import accepts_offer
        pool = [aid for age, aid in sorted(local)
                if age <= oldest and aid not in held and aid not in apprenticing and aid not in army
                and accepts_offer(world, aid, "apprenticeship")]
        # Veterans keep RS3's own order (earliest release first, as on every
        # opening RS3 prioritises); the age rule still bounds who is eligible.
        vets = [v for v in _veterans(world, st.region) if v in set(pool)]
        st.vets = set(vets)
        st.pool = vets + [a for a in pool if a not in st.vets]
        st.candidates = len(st.pool)
    # The mentors the present apprentices rely on (``seated_mentors``, RS2):
    # one read-only planner pass with the qualified listed first.
    if p.living_q and any(st.continuing for st in p.sites.values()):
        full = [(s, r, stl, d, _MAX_CREW) for s, r, stl, d, _m in requested]
        rows = sim.plan_workshop_crews(full, enlisted, None, priority_ids=p.living_q)
        for (site_id, *_rest), row in zip(requested, rows, strict=True):
            st = p.sites[site_id]
            qualified = [int(a) for a in row[8] if int(a) in p.held and int(a) not in holding]
            st.mentors_pred = qualified[:st.max_workers]


def _aboard_v2(world, p: _Pending, st: _SiteTurn) -> list[int]:
    """Version 2, at an operating site after its crew was planned: who is
    aboard and taught this turn, in order (continuing first, then new).

    An apprentice on the planned crew trains on crew time. One who is not (the
    native planner draws only adult urban farmers of the city, so an apprentice
    living in the region outside the city box is never on it) is *attached*:
    reserved for ``APPRENTICE_FRACTION`` in the registry now, after the crew,
    so the crew is never displaced. Teaching capacity is ``PER_MENTOR`` per
    qualified crew member."""
    sim = p.sim
    if p.trips is None:
        # Away on a trip, or holding rural health work (a patient or a carer:
        # a work commitment the native registry also refuses). Teaching work is
        # prepared later, at the agent tick, for Scholars only.
        p.trips = {int(a) for a in sim.trip_agent_ids()} | _health_holders(world)
    holding = {int(row[0]) for row in sim.work_reservations(p.turn)}
    on_crew = set(st.crew)
    st.capacity = min(PER_SITE, PER_MENTOR * len(st.qualified_on_crew))
    taught: list[int] = []

    def board(aid: int) -> str | None:
        if aid in on_crew:
            return "crew"
        if aid in p.trips or aid in holding:
            return None
        try:
            sim.reserve_work(p.turn, CATEGORY_APPRENTICE, [(aid, APPRENTICE_FRACTION)])
        except ValueError:
            return "refused"
        holding.add(aid)
        return "attached"

    for aid in st.continuing:
        if len(taught) >= st.capacity:
            st.missed[aid] = "no_mentor"
            continue
        how = board(aid)
        if how is None:
            st.missed[aid] = "unavailable"
        elif how == "refused":
            st.missed[aid] = "reservation_refused"
        else:
            st.aboard[aid] = how
            taught.append(aid)
    room = max(0, min(PER_SITE - st.open_after, st.capacity - len(taught)))
    # New apprentices: RS3 veterans first, then members of this turn's crew
    # (the qualification is used only on the crew: upkeep and teaching), then
    # the region's other residents, attached; youngest first within each.
    ordered = ([a for a in st.pool if a in st.vets] + [a for a in st.pool if a not in st.vets and a in on_crew]
               + [a for a in st.pool if a not in st.vets and a not in on_crew])
    eligible = 0
    for aid in ordered:
        if aid not in on_crew and (aid in p.trips or aid in holding):
            continue
        eligible += 1
        if room <= 0:
            continue
        how = board(aid)
        if how == "refused":
            st.refused_new += 1
            continue
        st.aboard[aid] = how
        st.new.append(aid)
        taught.append(aid)
        room -= 1
    st.eligible = eligible
    st.taught = taught
    return taught


def _attending_v2(st: _SiteTurn) -> list[tuple[int, float]]:
    """Version 2, after funding: the taught apprentices attend; attached ones
    give up ``APPRENTICE_FRACTION`` of their ordinary income (crew members
    already give their crew time, paid once as crew time)."""
    if not st.operating:
        for aid in st.continuing:
            st.missed.setdefault(aid, "site_not_operating")
        return []
    rows = []
    for aid in st.taught:
        if aid not in st.assigned:
            raise RuntimeError("a taught apprentice has no mentor")
        st.attending.append(aid)
        if st.aboard[aid] == "attached":
            rows.append((aid, APPRENTICE_FRACTION))
    return rows


def _miss_v2(state: ApprenticeshipState, record: Apprenticeship, seat: Seat, turn: int) -> bool:
    """Count a missed turn: progress pauses; only a long absence ends it.
    Returns True when the record ended."""
    record.gap += 1
    record.interruptions += 1
    _bump(state, "miss_" + seat.reason)
    if seat.reason in ("absent", "no_room"):
        record.absent = (record.absent or 0) + 1
        if record.absent > MAX_GAP:
            seat.ending = "long_absence"
            _end(state, record, turn, "long_absence")
            return True
    else:
        record.absent = 0
    if record.gap > MAX_PAUSE:
        seat.ending = "stalled"
        _end(state, record, turn, "stalled")
        return True
    return False


_health_holders = health_holders


def _upkeep_split(st: _SiteTurn, p: _Pending) -> tuple[dict[str, float], dict[int, float]]:
    """The upkeep offset by qualification route and by member: in crew order
    each qualified member gives up to ``UPKEEP_SHARE`` of their crew time until
    the wear's need is met (as :func:`crew_maintenance` counts it)."""
    d = st.diverted
    share = UPKEEP_SHARE * d
    remaining = st.upkeep_work
    work: dict[int, float] = {}
    for aid in st.qualified_on_crew:
        given = min(share, remaining)
        if given <= 0.0:
            break
        work[aid] = given
        remaining -= given
    total = sum(work.values())
    per = {aid: (st.offset * w / total if total > 0.0 else 0.0) for aid, w in work.items()}
    by_via = {"apprenticeship": 0.0, "service": 0.0}
    for aid, amount in per.items():
        by_via[p.via.get(aid, "service")] += amount
    return by_via, per


def _commit_v2(world, state: ApprenticeshipState, p: _Pending, after: dict, receipt) -> None:
    turn = p.turn
    train = state.mode == "train"
    _bump(state, "turns")
    active = {a.agent_id: a for a in state.apprenticeships}
    for aid, reason in sorted(p.closed.items()):
        _end(state, active.pop(aid), turn, reason)
    detached: list[Seat] = []
    for aid, reason in p.detached.items():
        record = active[aid]
        seat = Seat(agent_id=aid, veteran=record.veteran, outcome="missed", reason=reason)
        if _miss_v2(state, record, seat, turn):
            active.pop(aid)
        detached.append(seat)
    for q in list(state.qualifications):
        if q.agent_id not in after:
            _retire(state, q, turn, "died")
    graduates = {g.agent_id: g for g in state.graduates or []}
    for aid in [a for a in graduates if a not in after]:
        del graduates[aid]
        _bump(state, "graduates_died")
    service = {r.agent_id: r for r in state.service}
    frame = []
    from chronicler.veteran_reintegration import note_outcome
    for st in p.sites.values():
        _bump(state, "site_turns")
        _bump(state, "candidate_turns", st.candidates)
        _bump(state, "seats_offered", st.capacity)
        attached = [aid for aid in st.taught if st.aboard.get(aid) == "attached"]
        _bump(state, "apprentice_turns_reserved", len(attached))
        if st.refused_new:
            _bump(state, "seat_refused", st.refused_new)
        seats: list[Seat] = []
        completed: list[int] = []
        for aid, reason in st.ended.items():
            record = active.pop(aid)
            seats.append(Seat(agent_id=aid, veteran=record.veteran, outcome="ended", reason=reason))
            _end(state, record, turn, reason)
        for aid, source in st.transfers_in.items():
            record = active[aid]
            record.site, record.region, record.settlement_id = st.site, st.region, st.settlement
            record.transfers = (record.transfers or 0) + 1
            _bump(state, "transferred")
        missed_here = [aid for aid in st.missed if aid not in st.continuing]
        for aid in st.new:
            veteran = aid in st.vets
            record = Apprenticeship(agent_id=aid, site=st.site, settlement_id=st.settlement, region=st.region,
                                    started_turn=turn, veteran=veteran, absent=0, first_site=st.site,
                                    entry_age=p.people[aid][3], transfers=0, on_crew=0, attached=0)
            state.apprenticeships.append(record)
            active[aid] = record
            _bump(state, "enrolled")
            if veteran:
                _bump(state, "veterans_enrolled")
        new = set(st.new)
        for aid in st.continuing + missed_here + st.new:
            record = active[aid]
            how = st.aboard.get(aid)
            if how is not None and aid in after:
                # RS3: every apprentice aboard this turn is a dated training
                # placement of whoever holds an open veteran record.
                note_outcome(world, aid, "placed:apprentice", turn=turn,
                             detail={"site": st.site, "region": st.region, "attended": aid in st.attending})
            p.records[aid] = record
            seat = Seat(agent_id=aid, new=aid in new, veteran=record.veteran, outcome="missed",
                        share=APPRENTICE_FRACTION if how == "attached" else 0.0, aboard=how,
                        transferred_from=st.transfers_in.get(aid))
            seats.append(seat)
            if aid in st.attending:
                seat.mentor = st.assigned[aid]
                if how == "attached":
                    forgone = receipt[aid][2] if receipt is not None and aid in receipt else None
                    seat.income_forgone = forgone
                    if forgone is not None:
                        record.income_forgone += forgone
                        _bump(state, "income_forgone", forgone)
                if aid not in after:              # died later in the tick: the turn does not count
                    seat.outcome, seat.reason = "ended", "died"
                    _end(state, record, turn, "died")
                    active.pop(aid)
                    continue
                seat.outcome = "attended"
                record.attended += 1
                record.gap = 0
                record.absent = 0
                record.last_attended_turn = turn
                if how == "crew":
                    record.on_crew = (record.on_crew or 0) + 1
                    _bump(state, "apprentice_turns_on_crew")
                else:
                    record.attached = (record.attached or 0) + 1
                    _bump(state, "apprentice_turns_attached")
                if seat.mentor not in record.mentors and len(record.mentors) < MAX_MENTORS:
                    record.mentors.append(seat.mentor)
                _bump(state, "apprentice_turns_attended")
                if how == "attached":
                    seat.stipend_due = math.floor(seat.share * STIPEND_PER_WORK + 0.5)
                    p.stipends.setdefault(st.site, {})[aid] = seat.stipend_due
                if record.attended >= COMPLETION_TURNS:
                    completed.append(aid)
                    _bump(state, "completions")
                    record.granted = bool(train and _grant(state, aid, turn, st, "apprenticeship",
                                                           after[aid][:2]))
                    if record.granted:
                        _bump(state, "completions_granted")
                    if aid in graduates:
                        pass                      # keep the first record (a state saved before the fix)
                    elif len(graduates) < MAX_QUALIFIED:
                        graduates[aid] = GraduateRecord(agent_id=aid, completed_turn=turn, site=st.site,
                                                        region=st.region, granted=record.granted)
                        _bump(state, "graduates")
                    else:
                        _bump(state, "graduates_refused_cap")
                    seat.ending = "completed"
                    _end(state, record, turn, "completed")
                    active.pop(aid)
                continue
            seat.reason = st.missed[aid]
            if _miss_v2(state, record, seat, turn):
                active.pop(aid)
        service_qualified = []
        useful: dict = {}
        if st.operating:
            _bump(state, "operating_site_turns")
            _bump(state, "mentor_turns", len(set(st.assigned.values())))
            _bump(state, "upkeep_work", st.upkeep_work)
            _bump(state, "upkeep_offset", st.offset)
            _bump(state, "wear", st.wear)
            _bump(state, "teaching_work", st.teaching_work)
            # Useful work: who kept the site this turn.
            by_via, per = _upkeep_split(st, p)
            on_crew_graduates = [a for a in st.crew if a in p.graduates]
            by_graduates = sum((per.get(a, 0.0) for a in on_crew_graduates), 0.0)
            for aid in on_crew_graduates:
                g = graduates.get(aid)
                if g is not None:
                    g.crew_turns += 1
                    g.upkeep_offset += per.get(aid, 0.0)
                    g.last_crew_turn = turn
            covered = bool(st.qualified_on_crew)
            full_offset = st.offset >= st.wear
            _bump(state, "qualified_crew_turns", len(st.qualified_on_crew))
            _bump(state, "graduate_crew_turns", len(on_crew_graduates))
            _bump(state, "covered_site_turns", int(covered))
            _bump(state, "full_offset_site_turns", int(full_offset))
            _bump(state, "upkeep_offset_apprenticeship", by_via["apprenticeship"])
            _bump(state, "upkeep_offset_service", by_via["service"])
            _bump(state, "upkeep_offset_graduates", by_graduates)
            useful = dict(graduates_on_crew=on_crew_graduates, covered=covered, full_offset=full_offset,
                          offset_by_via=by_via, offset_by_graduates=by_graduates)
            held = {q.agent_id for q in state.qualifications}
            for aid in st.crew:
                if aid in held:
                    continue
                _bump(state, "crew_turns_served")
                rec = service.get(aid)
                if rec is None:
                    rec = service[aid] = ServiceRecord(agent_id=aid, last_turn=turn, last_site=st.site)
                rec.crew_turns += 1
                rec.last_turn, rec.last_site = turn, st.site
                if rec.crew_turns >= SERVICE_TURNS and aid in after:
                    if _grant(state, aid, turn, st, "service", after[aid][:2]):
                        service_qualified.append(aid)
                        del service[aid]
                        if aid in active and active[aid].site == st.site:
                            # An apprentice of this site on its crew qualified
                            # by service first (the apprenticeship ends so).
                            seat = next(s for s in seats if s.agent_id == aid)
                            seat.ending = "service_qualified"
                            _end(state, active.pop(aid), turn, "service_qualified")
        if not st.in_region:
            _bump(state, "sites_without_qualified_turns")
        frame.append(SiteReceipt(
            turn=turn, site=st.site, region=st.region, settlement_id=st.settlement,
            controller=st.controller, operating=st.operating, crew=list(st.crew),
            qualified_present=list(st.present), qualified_in_region=list(st.in_region),
            qualified_on_crew=list(st.qualified_on_crew),
            mentors=sorted(set(st.assigned.values())), crew_work=st.crew_work, craft_work=st.craft_work,
            upkeep_work=st.upkeep_work, teaching_work=st.teaching_work,
            condition_before=st.condition_before, wear=st.wear, upkeep_offset=st.offset,
            net_wear=st.net_wear, condition_after=st.condition_after, residents=st.residents,
            candidates=st.candidates, eligible=st.eligible, seat_capacity=st.capacity, seats=seats,
            service_qualified=service_qualified, completed=completed, **useful))
    kept = [r for aid, r in sorted(service.items()) if aid in after]
    if len(kept) > MAX_SERVICE:
        kept.sort(key=lambda r: (r.last_turn, r.crew_turns, r.agent_id))
        _bump(state, "service_evicted", len(kept) - MAX_SERVICE)
        kept = kept[len(kept) - MAX_SERVICE:]
    state.service = sorted(kept, key=lambda r: r.agent_id)
    for q in state.qualifications:
        q.seen_turn = turn
        q.seen_region, q.seen_settlement = after[q.agent_id][0], after[q.agent_id][1]
    state.graduates = sorted(graduates.values(), key=lambda g: g.agent_id)
    state.detached = detached
    _continuity(world, state, p, frame, after)
    state.frame = frame
    state.frame_turn = turn
    p.receipts = {r.site: r for r in frame}


def _snapshot_v2(state: ApprenticeshipState, source: int, fresh: bool) -> dict:
    return {
        "schema_version": 2, "rules_version": 2, "stage": "RS1", "mode": state.mode, "source_turn": source,
        "units": {"stipend": "milli_treasury_units", "work": "person_turns", "milli": 1000},
        "qualifications": [q.model_dump() for q in state.qualifications],
        "retired": [q.model_dump() for q in state.retired],
        "apprenticeships": [a.model_dump() for a in state.apprenticeships],
        "archive": [a.model_dump() for a in state.archive],
        "graduates": [g.model_dump() for g in state.graduates or []],
        "sites": [s.model_dump() for s in state.sites],
        "events": [e.model_dump() for e in state.events],
        # None: no completed apprenticeship pass in the source turn (unknown, not zero).
        "receipts": [r.model_dump() for r in state.frame] if fresh else None,
        "detached": [s.model_dump() for s in state.detached or []] if fresh else None,
        "continuity": dict(state.continuity) if fresh and state.continuity else None,
        "counters": {k: state.counters[k] for k in COUNTERS if k in state.counters},
        "parameters": {
            "service_turns": SERVICE_TURNS, "operating_wear": _ow.OPERATING_WEAR, "upkeep_share": UPKEEP_SHARE,
            "wear_per_upkeep_work": WEAR_PER_UPKEEP_WORK, "teach_share": TEACH_SHARE,
            "per_mentor": PER_MENTOR, "per_site": PER_SITE, "apprentice_fraction": APPRENTICE_FRACTION,
            "long_absence_turns": MAX_GAP, "max_pause": MAX_PAUSE, "completion_turns": COMPLETION_TURNS,
            "stipend_per_work": STIPEND_PER_WORK, "max_entry_age": max_entry_age(),
        },
    }


def phase10(world, acc, economy_result, agent_bridge) -> list:
    """Pay this turn's stipends from the sites' firm cash after wages (L6a on),
    exactly once, then close the turn."""
    state = _state(world)
    p = state._pending
    if p is None or p.turn != world.turn:
        return []
    state._pending = None
    if not p.committed:
        # No agent tick ran after Phase 2: nobody attended; disarm the extension.
        if p.extended:
            p.sim.cancel_paid_work()
        return []
    from chronicler.workshops import _lane_active
    payroll = _lane_active(world, "workshop_payroll")
    unpaid = payroll and world.livelihoods.workshop_payroll.mode == "unpaid_labor"
    for site_id, due in p.stipends.items():
        receipt = p.receipts[site_id]
        seats = {s.agent_id: s for s in receipt.seats if s.outcome == "attended"}
        total = sum(due.values())
        _bump(state, "stipends_due", total)
        result = None
        if not payroll:
            status = "no_payroll"
        elif unpaid:
            status = "unpaid_labor"
        else:
            from chronicler.workshop_payroll import pay_from_firm
            result = pay_from_firm(world, _native(getattr(agent_bridge, "_sim", None)), site_id, due,
                                   purpose=PURPOSE_APPRENTICE_STIPEND, kind="stipend")
            status = "no_firm" if result is None else None
        paid = 0
        for aid, amount in due.items():
            seat = seats[aid]
            if result is None:
                seat.stipend_status = status
                continue
            offered, applied, code = result[aid]
            seat.stipend_paid = applied
            seat.stipend_status = ("absent" if code == 2 else "paid" if applied == amount
                                   else "no_cash" if applied == 0 else "partial")
            paid += applied
            p.records[aid].stipends += applied
        _bump(state, "stipends_paid", paid)
        _bump(state, "stipends_residual", total - paid)
        receipt.stipend_status = status or ("paid" if paid == total else "no_cash" if paid == 0 else "partial")
    from chronicler.adaptive_livelihoods import note_work, forgone_title
    for receipt in p.receipts.values():
        for seat in receipt.seats:
            # Crew-attached training has no additional diverted time; wages
            # are accounted as workshop work separately, never paid twice.
            on_crew = getattr(seat, "aboard", None) == "crew"
            note_work(world, seat.agent_id, "apprenticeship", paid_milli=seat.stipend_paid,
                      withheld_milli=0 if on_crew else (round(seat.income_forgone * 1000)
                                                        if seat.income_forgone is not None else None),
                      title_forgone_milli=0 if on_crew else forgone_title(world, receipt.region),
                      progress=seat.outcome == "attended", source="apprenticeship:personal seat + stipend receipt")
    state.last_settled_turn = p.turn
    return []


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------

def snapshot_summary(world) -> dict:
    """The completed-turn observation; dated by ``source_turn``, never final state."""
    state = _state(world)
    source = world.turn - 1
    fresh = state.frame_turn == source
    if _v2(state):
        return _snapshot_v2(state, source, fresh)
    return {
        "schema_version": 1, "stage": "RS1", "mode": state.mode, "source_turn": source,
        "units": {"stipend": "milli_treasury_units", "work": "person_turns", "milli": 1000},
        "qualifications": [q.model_dump() for q in state.qualifications],
        "retired": [q.model_dump() for q in state.retired],
        "apprenticeships": [a.model_dump() for a in state.apprenticeships],
        "archive": [a.model_dump() for a in state.archive],
        "sites": [s.model_dump() for s in state.sites],
        "events": [e.model_dump() for e in state.events],
        # None: no completed apprenticeship pass in the source turn (unknown, not zero).
        "receipts": [r.model_dump() for r in state.frame] if fresh else None,
        "continuity": dict(state.continuity) if fresh and state.continuity else None,
        "counters": {k: state.counters[k] for k in COUNTERS if k in state.counters},
        "parameters": {
            "service_turns": SERVICE_TURNS, "operating_wear": _ow.OPERATING_WEAR, "upkeep_share": UPKEEP_SHARE,
            "wear_per_upkeep_work": WEAR_PER_UPKEEP_WORK, "teach_share": TEACH_SHARE,
            "per_mentor": PER_MENTOR, "per_site": PER_SITE, "apprentice_fraction": APPRENTICE_FRACTION,
            "max_gap": MAX_GAP, "completion_turns": COMPLETION_TURNS, "stipend_per_work": STIPEND_PER_WORK,
        },
    }
