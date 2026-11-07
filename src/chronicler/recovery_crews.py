"""PL3 recovery crews (``--recovery-crews``, default off).

Requires ``--agents hybrid`` and ``--repair-projects`` (RS2). Modes
(``--recovery-crew-mode``): ``paid`` (default) and the control ``unpaid``.
Phase plan: ``docs/superpowers/roadmaps/productive-recovery-phase.md`` (PL3);
integration page ``docs/integration/recovery-crews.md``.

Granary crews. Without this switch RS2's granary work is anonymous farm
labour: the project writes ``granary_work_requested`` and the native economy
removes ``min(request, farm labour)`` farmer-equivalents from the region's
farming (``economy.rs``: ``headcount_labor = farmers x farm_labor_factor``,
after health work, and ``delivered = min(requested, headcount_labor)``).
With it, that labour has names. RS2 first sizes the work it can fund and
supply (``planned``: the per-turn cap, the remaining scope, free timber,
coins and the L9 envelope). The crew is then named from the living adult
farmers resident in the granary's region who hold no other work this turn
(not on a trip, not enlisted, no registry reservation, no rural health work,
not a mentor RS1 seated), RS3's priority veterans first, then by ascending
id. Each member gives at most their own farm time: 1 for a rural farmer,
``URBAN_FARM_LABOR[rank]`` for an urban farmer (the city has the rest; the
same share the cities' ``farm_labor_factor`` already counts). Members are
added until their farm time covers the planned work, and the native request
becomes ``min(planned, crew farm time)``. The request therefore never
exceeds what the named people farm, which is part of the region's farm
labour, so the native step delivers it (to f32 rounding) and removes exactly
the crew's time from farming. When fewer farmers are free than the work
planned, the request shrinks to the crew (``no_labor`` among the receipt's
limits) and RS2 holds timber and plans coins only for it; with no free
adult farmer at all the project stalls ``no_labor`` and asks nothing.
Children and people already working elsewhere remain in the native farm
labour but never on a crew.

Each member is reserved for the turn in the shared work registry (category
``repair``, all or none, before the native economy runs). After the tick
the delivered work ``D`` is split by the planned shares (each scaled by
``D / requested``, never above the reservation); that share of the person's
ordinary income is withheld by the next wealth phase (``extend_paid_work``,
merged with RS2's own install). In ``paid`` mode the granary's coins per
delivered work (``grain_storage.COINS_PER_WORK``, the charge RS2 already
makes and that otherwise leaves the economy as a material sink) are paid to
the members by stable id, by delivered share (largest remainder, then id),
through ``AgentSimulator.transfer_wealth`` under purpose ``repair_wage``,
batch ``GRANARY_WAGE_BATCH`` (RS2's workshop wages use batch 0). No money is
created: RS2's treasury charge is unchanged, and the coin cost now splits
into wages and the part a wealth ceiling refuses, which stays a sink.
``unpaid`` names, reserves and withholds identically and keeps the charge
and the whole sink: it isolates the wage channel to households.

Workshop repair crews. RS2 draws a site's repair crew from the native crew
planner (adult urban farmers of the site's city). With this switch the pool
is every adult farmer resident in the site's region and every eligible RS3
veteran resident there, of any non-enlisted occupation (RS3's eligibility,
the same in both RS3 modes; ``record_only`` only removes the ordering), with
the same exclusions. Order: RS2's priority list (qualified veterans, the
qualified, veterans), then ascending id. Every member works the site's
diverted share ``d`` and has it withheld; a farmer who is not an urban farmer
of the site's city gives ``max(0, d - own diverted share)`` of farm time
(rural: ``d``), removed from the region's farm labour through the
``farm_labor_factor`` column, so no time is used twice. A veteran of another
occupation gives time the economy does not count as production; only the
income share is withheld (a declared limit).

Woodcutting. :func:`eligible_ids` offers the same pool for woodcutting
crews (PL1); PL1 does not call it today: it chooses its expedition crews with
its own rule.

Records: per project and turn a crew receipt (eligible people, planned,
capacity, requested and delivered work, members with origin, share, worked
share, farm time, veteran flag, wages and the income withheld) and per civ a
ledger whose closure is checked when it is written
(:func:`check_ledger`). All parameters are declared modeling choices, not
calibrated.
"""
from __future__ import annotations

import math
from importlib import import_module

from chronicler.recovery_crews_state import (
    COUNTERS, KINDS, MAX_FRAME_ROWS, MODES, CivCrewLedger, CrewMember, CrewReceipt, RecoveryCrewsState,
)

MILLI = 1000
#: Native ``agent::AGE_ADULT`` (the crew planners' age).
AGE_ADULT = 20
#: Native ``Occupation::Farmer``.
FARMER = 0
#: ``transfer_wealth`` batch of granary crew wages under purpose ``repair_wage``
#: (RS2's workshop repair wages use batch 0 the same turn).
GRANARY_WAGE_BATCH = 1
#: Least share of one person's turn a granary crew names them for (declared).
MIN_SHARE = 1e-3
EPS = 1e-9


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

class _Turn:
    """One turn in flight, Phase 2 to Phase 10 (never checkpointed)."""

    def __init__(self, turn: int, sim):
        self.turn, self.sim = turn, sim
        self.people = None
        self.receipts: list[CrewReceipt] = []
        self.ledger: dict[int, CivCrewLedger] = {}
        self.finished = False
        self.receipt_read = False
        #: Counter increments, applied when the turn commits (a failed turn
        #: changes no counter).
        self.counts: dict[str, float] = {}

    def bump(self, key: str, amount=1) -> None:
        if key not in COUNTERS:
            raise KeyError(f"undeclared recovery-crews counter {key!r}")
        self.counts[key] = self.counts.get(key, 0) + amount


def _state(world) -> RecoveryCrewsState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "recovery_crews", None) if container is not None else None


def _bump(state, key: str, amount=1) -> None:
    if key not in COUNTERS:
        raise KeyError(f"undeclared recovery-crews counter {key!r}")
    state.counters[key] = state.counters.get(key, 0) + amount


def set_recovery_crews_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable (with ``--recovery-crew-mode``, default ``paid``) or disable; an
    omitted mode keeps the saved one."""
    mode = getattr(args, "recovery_crew_mode", None) if args is not None else None
    state = _state(world)
    if state is None:
        world.livelihoods.recovery_crews = state = RecoveryCrewsState(mode=mode or MODES[0])
    else:
        t = state._turn
        if t is not None and t.turn == getattr(world, "turn", None) and not t.finished:
            raise RuntimeError("cannot change recovery crews while a turn is pending")
        if mode is not None:
            state.mode = mode
    state.enabled = bool(value)


def recovery_crews_active(world) -> bool:
    """Enabled in a hybrid run while RS2 repair projects are active."""
    state = _state(world)
    if state is None or not state.enabled or getattr(world, "agent_mode", None) != "hybrid":
        return False
    if getattr(world.livelihoods, "repair_projects", None) is None:
        return False
    from chronicler.repair_projects import repair_projects_active
    return repair_projects_active(world)


def _lane_active(world, name: str) -> bool:
    if getattr(getattr(world, "livelihoods", None), name, None) is None:
        return False
    return bool(getattr(import_module("chronicler." + name), f"{name}_active")(world))


def _begin(world, sim) -> _Turn:
    state = _state(world)
    t = state._turn
    if t is not None and t.turn == world.turn:
        if t.finished:
            raise RuntimeError("recovery crews already settled for this turn")
        return t
    if state.last_settled_turn is not None and world.turn <= state.last_settled_turn:
        raise RuntimeError("recovery crews already settled for this turn")
    if t is not None:
        _bump(state, "turns_discarded")       # a failed turn left rows of another turn
    t = state._turn = _Turn(world.turn, sim)
    return t


# ---------------------------------------------------------------------------
# Who may join a crew
# ---------------------------------------------------------------------------

class _People:
    """One Phase 2 view of the residents, from the agent rows the economy
    reads (the snapshot is not changed between Phase 2's start and the native
    economy tick). Exclusions that change within the turn (the registry) are
    read again at every call."""

    def __init__(self, world, snapshot):
        from chronicler.columnar import batch_arrays
        arrays = batch_arrays(snapshot, ("id", "region", "occupation", "age", "settlement_id"))
        if arrays is None:
            raise RuntimeError("recovery crews require the Phase 2 agent snapshot")
        self.ids, self.region, self.occupation, self.age, self.settlement = (a.astype("int64") for a in arrays)
        self._regions: dict[int, list[tuple[int, int, int]]] = {}
        self.farmers = None

    def residents(self, region: int) -> list[tuple[int, int, int]]:
        """Adult residents (id, occupation, settlement id), ascending id."""
        rows = self._regions.get(region)
        if rows is None:
            import numpy as np
            idx = np.flatnonzero((self.region == region) & (self.age >= AGE_ADULT))
            rows = sorted((int(self.ids[i]), int(self.occupation[i]), int(self.settlement[i])) for i in idx)
            self._regions[region] = rows
        return rows

    def farmer_counts(self, n: int) -> list[int]:
        """Living farmers of any age per region (the native farmer count)."""
        if self.farmers is None:
            import numpy as np
            mask = (self.occupation == FARMER) & (self.region >= 0) & (self.region < n)
            self.farmers = [int(c) for c in np.bincount(self.region[mask], minlength=n)[:n]]
        return self.farmers


def _people(world, t: _Turn, snapshot, sim) -> _People:
    if t.people is None:
        if snapshot is None:
            getter = getattr(sim, "get_snapshot", None)
            snapshot = getter() if callable(getter) else None
        t.people = _People(world, snapshot)
    return t.people


def _health_holders(world) -> set[int]:
    """Patients and carers of this turn's prepared rural health work."""
    health = getattr(world, "health_care", None)
    rows = getattr(health, "_prepared", None) if health is not None else None
    out: set[int] = set()
    for aid, _region, giver, care in rows or ():
        out.add(int(aid))
        if int(giver) and float(care) > 0:
            out.add(int(giver))
    return out


def _excluded(world, sim, turn: int) -> set[int]:
    """Everyone who may not join a crew now: registry holders, rural health
    work, people on a trip, the enlisted and the mentors RS1 seated."""
    from chronicler.workshops import _enlisted
    out = {int(aid) for aid, _cat, _f in sim.work_reservations(turn)}
    out |= _health_holders(world)
    trips = getattr(sim, "trip_agent_ids", None)
    if callable(trips):
        out |= {int(a) for a in trips()}
    out |= set(_enlisted(world))
    if _lane_active(world, "apprenticeship"):
        from chronicler.apprenticeship import seated_mentors
        out |= set(seated_mentors(world))
    return out


def _veterans(world, region: int) -> list[int]:
    """RS3's eligible veterans resident in ``region`` (its public rule, the
    same in both RS3 modes), earliest release first."""
    if not _lane_active(world, "veteran_reintegration"):
        return []
    from chronicler.veteran_reintegration import eligible_ids as veteran_ids
    return veteran_ids(world, int(region))


def _cities(world) -> dict[int, tuple[int, int]]:
    """settlement id -> (region, rank) of each city while cities are on."""
    from chronicler.cities_state import cities_on
    if not cities_on(world):
        return {}
    return {int(c.settlement_id): (int(c.region), int(c.rank)) for c in world.cities.cities}


def _farm_share(cities, region: int, settlement: int) -> tuple[float, float, bool]:
    """(farm time, diverted share, urban) of one farmer's turn: rural 1 and 0;
    an urban farmer of a city of the region ``URBAN_FARM_LABOR[rank]`` and the
    rest (the shares the cities' ``farm_labor_factor`` counts)."""
    from chronicler.cities import URBAN_FARM_LABOR
    city = cities.get(settlement)
    if city is None or city[0] != region:
        return 1.0, 0.0, False
    farm = float(URBAN_FARM_LABOR[max(0, min(city[1], len(URBAN_FARM_LABOR) - 1))])
    return farm, 1.0 - farm, True


def _eligible(world, people: _People, sim, region: int, kind: str, priority, *,
              site_settlement: int | None = None, veterans_admitted: bool = True):
    """Ordered (id, origin, farm time, diverted share) of everyone eligible."""
    if kind not in KINDS:
        raise ValueError(f"unknown recovery crew kind {kind!r}")
    excluded = _excluded(world, sim, world.turn)
    cities = _cities(world)
    veterans = set(_veterans(world, region)) if kind != "granary" and veterans_admitted else set()
    rows = []
    for aid, occupation, settlement in people.residents(region):
        if aid in excluded:
            continue
        if occupation == FARMER:
            farm, diverted, urban = _farm_share(cities, region, settlement)
            if site_settlement is not None and settlement == site_settlement and urban:
                origin = "site_city"
            else:
                origin = "urban_farmer" if urban else "rural_farmer"
        elif aid in veterans:
            farm, diverted, origin = 0.0, 0.0, "veteran"
        else:
            continue
        rows.append((aid, origin, farm, diverted))
    rank = {int(a): i for i, a in enumerate(priority or [])}
    rows.sort(key=lambda r: (rank.get(r[0], math.inf), r[0]))
    return rows


def eligible_ids(world, region: int, kind: str, *, sim, snapshot=None, priority=None) -> list[int]:
    """Cross-lane API, offered for woodcutting (PL1 does not call it yet; it
    chooses expedition crews with its own rule): stable ids eligible now for a
    recovery crew of ``kind`` (``"granary"``, ``"workshop"`` or ``"woodcut"``)
    in ``region`` (an index in ``world.regions``), in crew order.

    Everyone listed is a living adult resident of the region holding no work
    this turn (registry, rural health work), not on a trip, not enlisted and
    not a mentor RS1 seated. ``granary``: adult farmers. ``workshop`` and
    ``woodcut``: adult farmers and, while ``--recovery-crews`` is active,
    RS3's eligible veterans of any non-enlisted occupation. Order:
    ``priority`` (default: RS3's ``priority_ids`` of the region, empty in
    ``record_only``), then ascending id. ``snapshot`` defaults to
    ``sim.get_snapshot()``. Reads only: it reserves nobody (the caller does,
    all or none, with ``reserve_work``)."""
    if priority is None:
        priority = []
        if _lane_active(world, "veteran_reintegration"):
            from chronicler.veteran_reintegration import priority_ids
            priority = priority_ids(world, region)
    if snapshot is None:
        snapshot = sim.get_snapshot()
    people = _People(world, snapshot)
    rows = _eligible(world, people, sim, int(region), kind, priority,
                     veterans_admitted=recovery_crews_active(world))
    return [aid for aid, *_ in rows]


# ---------------------------------------------------------------------------
# RS2 seams (called from repair_projects' crew sections)
# ---------------------------------------------------------------------------

def farm_labour(world, snapshot) -> list[int] | None:
    """Living farmers of any age per region index in ``snapshot`` (what the
    native economy multiplies by ``farm_labor_factor``), or None when the
    snapshot cannot be read."""
    if snapshot is None:
        return None
    try:
        people = _People(world, snapshot)
        counts = people.farmer_counts(len(world.regions))
        from chronicler.war_requisition import enlisted_ids
        service = set(enlisted_ids(world))
        if service:
            for aid, region, occupation in zip(people.ids, people.region, people.occupation):
                if int(aid) in service and int(occupation) == FARMER and 0 <= int(region) < len(counts):
                    counts[int(region)] -= 1
        return counts
    except RuntimeError:
        return None


def workshop_candidates(world, sim, site, diverted: float, priority) -> tuple[list, int]:
    """The widened workshop repair pool of ``site``: ordered (id, origin,
    farm time to remove) and how many eligible people are urban farmers of
    the site's own city (the pool RS2 had without this switch)."""
    t = _begin(world, sim)
    people = _people(world, t, None, sim)
    rows = _eligible(world, people, sim, int(site.region), "workshop", priority,
                     site_settlement=int(site.settlement_id))
    out = []
    for aid, origin, _farm, own in rows:
        if origin == "veteran" or origin == "site_city":
            removed = 0.0
        else:
            removed = max(0.0, diverted - own)
        out.append((aid, origin, removed))
    return out, sum(1 for r in rows if r[1] == "site_city")


def plan_granary_crew(world, w, planned: float, *, sim, snapshot, priority, offer_kind="granary") -> float:
    """Name and reserve the crew of RS2 granary work ``w`` (its ``_Work``)
    for ``planned`` work; returns the native request, ``min(planned, the
    crew's farm time)``, f32-floored. Stores the crew on ``w.named`` and
    ``w.short``: True only when the free adult farmers ran out with at least
    ``MIN_SHARE`` of the planned work left. A remainder below ``MIN_SHARE``
    names nobody and counts as covered (review C 2026-11-06: it read as a
    labour shortage while free farmers remained)."""
    from chronicler.grain_storage import _f32_floor
    from chronicler.repair_projects import CATEGORY_REPAIR
    t = _begin(world, sim)
    people = _people(world, t, snapshot, sim)
    rows = _eligible(world, people, sim, int(w.region), "granary", priority)
    from chronicler.work_experience import accepts_offer
    rows = [r for r in rows if accepts_offer(world, r[0], offer_kind)]
    w.eligible = len(rows)
    w.planned = planned
    chosen, capacity = [], 0.0
    for aid, origin, farm, _own in rows:
        if capacity >= planned - EPS:
            break
        take = min(farm, planned - capacity)
        if take < MIN_SHARE:
            break
        chosen.append((aid, origin, farm))
        capacity += farm
    w.short = planned - capacity >= MIN_SHARE - EPS
    request = _f32_floor(max(0.0, min(planned, capacity)))
    named, assigned = [], 0.0
    for aid, origin, farm in chosen:
        share = _f32_floor(min(farm, request - assigned))
        if share < MIN_SHARE:
            continue
        named.append((aid, origin, share))
        assigned += share
    request = _f32_floor(min(request, assigned)) if named else 0.0
    w.capacity = math.fsum(min(farm, 1.0) for _a, _o, farm in chosen)
    if not named or request <= 0.0:
        w.named = []
        return 0.0
    veterans = _open_veterans(world)
    sim.reserve_work(world.turn, CATEGORY_REPAIR, [(aid, share) for aid, _o, share in named])
    w.named = [(aid, origin, share, aid in veterans) for aid, origin, share in named]
    return request


def _open_veterans(world) -> frozenset[int]:
    if not _lane_active(world, "veteran_reintegration"):
        return frozenset()
    from chronicler.veteran_reintegration import open_record_ids
    return open_record_ids(world)


def granary_shares(w, delivered: float) -> list[tuple[int, float]]:
    """Each named member's worked share for ``delivered`` work: the planned
    share scaled by ``delivered / sum of shares`` (never above it)."""
    total = math.fsum(share for _a, _o, share, _v in w.named)
    if total <= 0 or delivered <= 0:
        return [(aid, 0.0) for aid, _o, _s, _v in w.named]
    ratio = min(1.0, delivered / total)
    return [(aid, share * ratio if ratio < 1.0 else share) for aid, _o, share, _v in w.named]


def split_wages(total_milli: int, worked: list[tuple[int, float]]) -> dict[int, int]:
    """``total_milli`` split by worked share: floors, then the remainder one
    milli-unit each by the largest fractional part, then ascending id."""
    weights = [(aid, max(0, round(share * 1_000_000))) for aid, share in worked]
    whole = sum(v for _a, v in weights)
    if total_milli <= 0 or whole <= 0:
        return {aid: 0 for aid, _s in worked}
    out, rests = {}, []
    for aid, v in weights:
        q, r = divmod(total_milli * v, whole)
        out[aid] = q
        rests.append((-r, aid))
    left = total_milli - sum(out.values())
    for _r, aid in sorted(rests)[:left]:
        out[aid] += 1
    return out


def pay_granary_crews(world, sim, works, delivered: dict[int, float], coin_milli) -> dict[int, tuple]:
    """Phase 2 after the economy tick (RS2's ``finish_phase2``, before its
    charge): each granary crew's worked shares and, in ``paid`` mode, one
    keyed wage batch. Returns ``{pid: (worked rows, wage due, {id: (applied,
    residual)})}``; the withheld shares are merged into RS2's paid-work
    install by the caller."""
    from chronicler.repair_projects import PURPOSE_REPAIR_WAGE
    state = _state(world)
    paid = state.mode == "paid"
    out, rows = {}, []
    for w in works:
        got = float(delivered.get(w.project.pid, 0.0))
        worked = granary_shares(w, got)
        due = coin_milli(got) if paid and got > 0 else 0
        wages = split_wages(due, worked) if due else {aid: 0 for aid, _s in worked}
        out[w.project.pid] = (worked, due, wages)
        rows.extend((aid, amount) for aid, amount in sorted(wages.items()) if amount > 0)
    applied: dict[int, tuple[int, int]] = {}
    if rows:
        rows.sort()
        for aid, requested, got, residual, status in sim.transfer_wealth(
                world.turn, PURPOSE_REPAIR_WAGE, GRANARY_WAGE_BATCH, rows):
            applied[int(aid)] = (int(got), int(residual) if status != 2 else int(requested))
    return {pid: (worked, due, {aid: applied.get(aid, (0, amount)) for aid, amount in wages.items()})
            for pid, (worked, due, wages) in out.items()}


def record(world, w, *, sim, turn: int, delivered: float, coin_cost_milli: int, paid=None) -> None:
    """Stage one RS2 project's crew receipt for this turn's frame (granary:
    with ``paid`` from :func:`pay_granary_crews`; workshop: its composition)."""
    state = _state(world)
    t = _begin(world, sim)
    veterans = _open_veterans(world)
    if w.kind == "granary":
        worked, due, wages = paid if paid is not None else ([], 0, {})
        shares = {aid: s for aid, s in worked}
        members = []
        for aid, origin, share, veteran in w.named:
            got, residual = wages.get(aid, (0, 0))
            members.append(CrewMember(agent_id=aid, origin=origin, share=share, worked=shares.get(aid, 0.0),
                                      farm_time=shares.get(aid, 0.0), veteran=veteran,
                                      wage_due_milli=got + residual, wage_milli=got,
                                      wage_residual_milli=residual))
        applied = sum(m.wage_milli for m in members)
        residual = sum(m.wage_residual_milli for m in members)
        receipt = CrewReceipt(turn=turn, pid=w.project.pid, kind="granary", region=w.region, payer=w.payer,
                              eligible=w.eligible, planned=w.planned, capacity=w.capacity,
                              requested=w.request, delivered=delivered, short=w.short, members=members,
                              coin_cost_milli=coin_cost_milli, wages_due_milli=due, wages_milli=applied,
                              wage_residual_milli=residual, sunk_milli=coin_cost_milli - applied,
                              farm_time_removed=delivered)
        row = t.ledger.get(w.payer)
        if row is None:
            row = t.ledger[w.payer] = CivCrewLedger(turn=turn, civ=w.payer, coin_cost_milli=0, wages_due_milli=0,
                                                    wages_milli=0, wage_residual_milli=0, sunk_milli=0)
        row.coin_cost_milli += coin_cost_milli
        row.wages_due_milli += due
        row.wages_milli += applied
        row.wage_residual_milli += residual
        row.sunk_milli += coin_cost_milli - applied
        t.bump("granary_crews" if members else "granary_no_crew")
        t.bump("granary_crew_person_turns", len(members))
        t.bump("granary_work_planned", w.planned)
        t.bump("granary_work_named", delivered)
        if w.short:
            t.bump("granary_crew_short")
        t.bump("granary_coin_cost_milli", coin_cost_milli)
        t.bump("granary_wages_due_milli", due)
        t.bump("granary_wages_milli", applied)
        t.bump("granary_wage_residual_milli", residual)
        t.bump("granary_sunk_milli", coin_cost_milli - applied)
        t.bump("farm_time_removed", delivered)
        for m in members:
            t.bump(f"granary_members_{m.origin}")
    else:
        origins = dict(getattr(w, "origins", None) or {})
        removed = dict(getattr(w, "removed", None) or {})
        members = [CrewMember(agent_id=aid, origin=origins.get(aid, "site_city"), share=w.share, worked=w.share,
                              farm_time=removed.get(aid, 0.0), veteran=aid in veterans)
                   for aid in w.crew]
        receipt = CrewReceipt(turn=turn, pid=w.project.pid, kind="workshop", region=w.region, payer=w.payer,
                              eligible=w.eligible, eligible_site_city=w.eligible_site_city,
                              requested=w.request, delivered=delivered, members=members,
                              farm_time_removed=math.fsum(m.farm_time for m in members))
        t.bump("workshop_crews")
        t.bump("workshop_crew_person_turns", len(members))
        t.bump("farm_time_removed", receipt.farm_time_removed)
        for m in members:
            t.bump(f"workshop_members_{m.origin}")
    t.bump("veterans_placed", sum(1 for m in members if m.veteran))
    check_receipt(receipt, state.mode)
    t.receipts.append(receipt)


def check_receipt(r: CrewReceipt, mode: str) -> None:
    """Closure of one crew receipt."""
    if r.wages_milli + r.wage_residual_milli != r.wages_due_milli:
        raise RuntimeError("recovery crew wages do not close")
    if r.kind == "granary":
        if r.coin_cost_milli != r.wages_milli + r.sunk_milli or r.sunk_milli < 0:
            raise RuntimeError("granary crew coins do not close")
        if mode == "unpaid" and r.wages_due_milli:
            raise RuntimeError("an unpaid crew was paid")
        if mode == "paid" and r.delivered > 0 and r.wages_due_milli != r.coin_cost_milli:
            raise RuntimeError("a paid crew was not paid the granary's coins")
        if r.delivered > r.requested + 1e-6 or r.requested > r.planned + 1e-6:
            raise RuntimeError("granary crew work beyond its request")
        if sum(m.worked for m in r.members) > r.requested + 1e-5:
            raise RuntimeError("granary crew worked beyond its request")
    for m in r.members:
        if not (0.0 <= m.worked <= m.share + 1e-9 and m.share <= 1.0 + 1e-9):
            raise RuntimeError("a crew member worked beyond the reservation")
    if len({m.agent_id for m in r.members}) != len(r.members):
        raise RuntimeError("a person is twice on one crew")


def check_ledger(row: CivCrewLedger) -> None:
    if row.coin_cost_milli != row.wages_milli + row.sunk_milli or row.sunk_milli < 0:
        raise RuntimeError(f"granary crew coins of civ {row.civ} do not close")
    if row.wages_milli + row.wage_residual_milli != row.wages_due_milli:
        raise RuntimeError(f"granary crew wages of civ {row.civ} do not close")


def remove_farm_time(world, region_input, snapshot, removal: dict[int, float], *, sim=None):
    """The region batch with each region's ``farm_labor_factor`` lowered so
    that ``farmers x factor`` falls by ``removal[region]`` farmer-equivalents
    (the native farm labour; health work is subtracted natively after)."""
    import pyarrow as pa
    if snapshot is None and sim is not None:
        snapshot = sim.get_snapshot()
    farmers = farm_labour(world, snapshot)
    if farmers is None:
        raise RuntimeError("recovery crews require the Phase 2 agent snapshot")
    names = region_input.schema.names
    n = len(world.regions)
    present = "farm_labor_factor" in names
    factor = (region_input.column(names.index("farm_labor_factor")).to_pylist() if present else [1.0] * n)
    for region, amount in sorted(removal.items()):
        if farmers[region] <= 0:
            raise RuntimeError("farm time removed from a region without farmers")
        factor[region] = max(0.0, float(factor[region]) - amount / farmers[region])
    column = pa.array(factor, type=pa.float32())
    if present:
        return region_input.set_column(names.index("farm_labor_factor"), "farm_labor_factor", column)
    return region_input.append_column("farm_labor_factor", column)


def finish_turn(world, sim) -> None:
    """RS2's ``finish_phase2`` settled: the frame is complete for this turn."""
    t = _begin(world, sim)
    people = [m.agent_id for r in t.receipts for m in r.members]
    if len(set(people)) != len(people):
        raise RuntimeError("a person is on two recovery crews in one turn")
    for row in t.ledger.values():
        check_ledger(row)
    t.finished = True


# ---------------------------------------------------------------------------
# Package hooks
# ---------------------------------------------------------------------------

def rollback_phase2(world) -> None:
    """A failed Phase 2: nothing of this turn is recorded (RS2 releases the
    timber and the paid share; the registry is the native turn's)."""
    state = _state(world)
    if state is not None and state._turn is not None and state._turn.turn == getattr(world, "turn", None):
        state._turn = None


def rollback_agent_tick(world, agent_bridge) -> None:
    """A failed agent tick: the frame of this turn is dropped (RS2 cancels the
    pending paid share)."""
    rollback_phase2(world)


def after_agent_tick(world, agent_bridge):
    state = _state(world)
    t = state._turn
    if t is None or t.turn != world.turn or not t.finished:
        return []
    if not any(r.members for r in t.receipts):
        return []
    from chronicler.livelihoods import paid_work_receipt
    receipt = paid_work_receipt(world, t.sim)
    if receipt is None:
        raise RuntimeError("paid work receipt missing for this turn's recovery crews")
    for r in t.receipts:
        for m in r.members:
            if m.worked > 0 and m.agent_id in receipt:
                m.income_replaced = float(receipt[m.agent_id][2])
                t.bump("income_replaced", m.income_replaced)
            if r.kind == "granary" and m.worked > 0:
                from chronicler.work_experience import record
                record(world, m.agent_id, "granary", paid_milli=m.wage_milli, receipt=receipt, share=m.worked,
                       region=r.region, occupation=FARMER, source="recovery_crews:individual wage + keyed paid-work receipt")
    t.receipt_read = True
    return []


def phase10(world, acc, economy_result, agent_bridge):
    """Commit the turn's frame (dated to this turn) once."""
    state = _state(world)
    t = state._turn
    if t is not None and t.turn == world.turn and t.finished:
        receipts = t.receipts
        if len(receipts) > MAX_FRAME_ROWS:
            dropped = len(receipts) - MAX_FRAME_ROWS
            receipts = receipts[:MAX_FRAME_ROWS]
            state.rows_dropped += dropped
            _bump(state, "rows_dropped", dropped)
        state.receipts = receipts
        state.ledger = [t.ledger[c] for c in sorted(t.ledger)]
        state.last_settled_turn = world.turn
        for key, amount in t.counts.items():
            _bump(state, key, amount)
        _bump(state, "settled_turns")
    else:
        state.receipts, state.ledger = None, None
    state.frame_turn = world.turn
    state._turn = None
    return []


def on_pool_reset(world) -> None:
    """A rebuilt native pool: the frame's ids would name other people."""
    state = _state(world)
    if state is None:
        return
    if state.receipts:
        _bump(state, "pool_resets")
    state.receipts, state.ledger = None, None
    state._turn = None


def snapshot_summary(world) -> dict:
    """The completed-turn observation; ``receipts`` and ``ledger`` are None
    when that turn had no settled Phase 2 (unknown, not zero)."""
    from chronicler.grain_storage import COINS_PER_WORK
    state = _state(world)
    source = world.turn - 1
    fresh = state.frame_turn == source
    return {
        "schema_version": 1, "stage": "PL3", "mode": state.mode, "source_turn": source,
        "units": {"money": "milli_treasury_units", "work": "work_units", "milli": MILLI},
        "receipts": [r.model_dump() for r in state.receipts] if fresh and state.receipts is not None else None,
        "ledger": [r.model_dump() for r in state.ledger] if fresh and state.ledger is not None else None,
        "rows_dropped": state.rows_dropped,
        "counters": dict(state.counters),
        "parameters": {"age_adult": AGE_ADULT, "min_share": MIN_SHARE, "granary_coins_per_work": COINS_PER_WORK,
                       "granary_wage_batch": GRANARY_WAGE_BATCH, "max_frame_rows": MAX_FRAME_ROWS},
    }
