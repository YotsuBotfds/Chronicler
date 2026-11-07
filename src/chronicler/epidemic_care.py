"""Bounded epidemic care capacity (connected-world C2; ``--epidemic-care``, default off).

Requires ``--agents hybrid``, ``--local-budgets`` (L9, which itself requires
``--grain-reserves``) and epidemiology with the contact ledger (on by default
for new worlds); refused with ``--wealth-accounting`` (A1 does not itemize care
wages yet). Modes (``--epidemic-care-mode``): ``care`` (default) and the cost
control ``cost_only``. Design: audit C section 6.3, plan section 5.3 (lead
decisions); integration page ``docs/integration/epidemic-care.md``.

Funding (one authority). An L9 provider (:data:`BUDGET_PROVIDER`, service
``epidemic_care``, group ``relief``) proposes, in Phase 10 of turn T for turn
T + 1, one divisible envelope per ruler covering every region of it with a
reported outbreak at T's tick: the wages of the care time their infectious
people need (``infectious / PATIENTS_PER_CARER`` worker-turns at
``WAGE_MILLI``), rounded up once to L9's whole coin (at most one coin per civ
and turn beyond the need; an award's unspent part lapses at settlement, as
every envelope's does). The commons' stake is the deaths care would avert at
full coverage (persistence
forecast from T's tick: ``CARE_CFR_REDUCTION x sum over pathogens of burden x
n x SUBSTEPS x recovery x cfr``) valued at ``DEATH_FOOD_EQUIVALENT`` food
units each (L9's ``horizon`` turns of one person's food), the unit the
commons' other proposals use. Nothing is spent outside an accepted envelope;
there is no treasury charge of its own and no flat cost.

Carers (Phase 2 of T + 1, after every other work consumer). Each open
envelope serves its regions most infectious first; the carers are named from
the living adult farmers resident in a region who hold no other work this
turn (:func:`labour_reservations.booked`:
rural health patients and caregivers, the shared native work registry, trips,
the enlisted, seated mentors), in ascending stable id: no random draw. Each
gives at most their own farm time (1 for a rural farmer,
``cities.URBAN_FARM_LABOR[rank]`` for an urban one) until the care time
covers the region's infectious people at this turn's tick, within the
envelope's wages and the payer's projected treasury. They are reserved in the
shared work registry (category ``repair``: the native registry's categories
are fixed, as PL1's woodcutters use it; the shared query labels them
``registry_care``), so that turn they are neither drafted by campaigns nor
taken for academy teaching (both skip registry holders: part of care's cost).
Their farm time leaves the region's native farm labour through
``farm_labor_factor`` (``recovery_crews.remove_farm_time``). After the economy
tick, once every earlier package has charged the treasury, each paying civ's
wage bill is quoted again: a bill that would be refused pays nobody and
withholds nothing, and its carers give no capacity (their booked farm time is
lost, recorded as ``farm_time_unpaid``). Otherwise the same share of the
carers' ordinary income is withheld by the next wealth phase
(``extend_paid_work``) and their wages are paid by stable id through the
payment seam (``money.pay``, purpose ``care_wage``, one bill per paying civ,
batch ``CARE_WAGE_BATCH + civ``; whole bill or nothing, exactly once).

Capacity. The patients they can serve (``care time x PATIENTS_PER_CARER``)
are recorded as dated state ``(region, source_turn T + 1, patients)`` and
read by the next epidemic tick only (Phase 1 of T + 2), which consumes it: a
row of any other date, or naming no region, is refused (``stale``,
``future``, ``out_of_range``) and never applied.

Effect (``care`` only). At that tick, coverage ``c = min(1, patients /
infectious)`` with the infectious people of the last tick (sum over pathogens
of ``burden x n`` before the tick absorbs population change); the region's
case fatality is multiplied by ``1 - CARE_CFR_REDUCTION x c`` in the epidemic
model's own modifier list, combined with practised medicine under one floor
(``max(techniques.CFR_FLOOR, techniques x care)``: care never takes fatality
below the techniques floor). Deaths are still drawn only by
``epidemiology._apply_deaths``: no second mortality path; native endemic
(M35b) mortality and rural health care are untouched. ``cost_only`` names,
reserves, removes farm time, withholds and pays identically and applies no
factor (it records the factor it would have applied).

No random draws; every order is by index or stable id. All constants are
declared modelling choices, not calibrations; none was tuned on any run.
"""
from __future__ import annotations

import math

from chronicler.epidemic_care_state import (
    COUNTERS, MAX_FRAME_ROWS, MODES, CapacityRefusal, CareApplied, CareCapacity, CareReceipt, Carer,
    CivWageLedger, EpidemicCareState, TickRegion,
)

MILLI = 1000
#: Share of case fatality removed at full coverage (declared). The size of
#: the strongest practised-medicine reduction already in the model
#: (``techniques.CFR_REDUCTION``: vaccination 0.30; physicians 0.10, herbalism
#: and lazarets 0.05): basic nursing (water, food, warmth, cleaning) for the
#: sick is the main pre-modern lever on dehydrating and wasting disease
#: (flux, fever, pox), and weak against plague; one value for every pathogen.
CARE_CFR_REDUCTION = 0.3
#: Patients one carer serves for a whole worker-turn (declared): rural health
#: care's full care effect needs 0.2 worker-turn per patient-turn
#: (``health_care_state.HealthCareState.care_fraction``; recovery
#: ``1 + min(1, 5 x care)``), so one worker-turn serves 1 / 0.2 = 5.
PATIENTS_PER_CARER = 5.0
#: Wage per carer for a whole worker-turn, milli-units: RS2's
#: ``repair_projects.WAGE_PER_WORK``, which PL1 woodcutters are also paid.
WAGE_MILLI = 500
#: Native work registry category the carers are reserved under (the
#: registry's four categories are fixed natively; PL1 woodcutters use it too).
CATEGORY_REPAIR = 3
#: Payment seam batch of a civ's care wages: ``CARE_WAGE_BATCH + civ`` under
#: purpose ``care_wage`` (native code ``repair_wage``, whose other users take
#: batches 0, 1 and 2: RS2, PL3, PL1).
CARE_WAGE_BATCH = 0xC2000
#: Least care time one person is named for (declared, as PL3's ``MIN_SHARE``).
MIN_SHARE = 1e-3
#: Native ``agent::AGE_ADULT`` and ``Occupation::Farmer``.
AGE_ADULT = 20
FARMER = 0
#: The L9 service name (one claim per region: ``epidemic_care:<region>``).
SERVICE = "epidemic_care"
PURPOSE = "care_wage"
EPS = 1e-9
_NATIVE = ("reserve_work", "work_reservations", "extend_paid_work", "cancel_paid_work",
           "wealth_transfer_purposes", "get_snapshot")


class _Turn:
    """One turn in flight, Phase 2 to Phase 10 (never checkpointed)."""

    def __init__(self, turn: int, sim):
        self.turn, self.sim = turn, sim
        self.receipts: list[CareReceipt] = []
        #: civ -> coins of the care envelopes it executes this turn.
        self.envelopes: dict[int, int] = {}
        self.prepared = False
        self.finished = False
        self.installed = False
        self.receipt_read = False


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

def _state(world) -> EpidemicCareState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "epidemic_care", None) if container is not None else None


def _bump(state, key: str, amount=1) -> None:
    if key not in COUNTERS:
        raise KeyError(f"undeclared epidemic care counter {key!r}")
    state.counters[key] = round(state.counters.get(key, 0) + amount, 6)


def set_epidemic_care_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable (with ``--epidemic-care-mode``, default ``care``) or disable. A
    disabled world drops its pending capacity (nothing applies at the next
    tick); the book and counters stay."""
    mode = getattr(args, "epidemic_care_mode", None) if args is not None else None
    state = _state(world)
    if state is None:
        world.livelihoods.epidemic_care = state = EpidemicCareState(mode=mode or MODES[0])
    else:
        t = state._turn
        if t is not None and t.turn == getattr(world, "turn", None) and not t.finished:
            raise RuntimeError("cannot change epidemic care while a turn is pending")
        if mode is not None:
            state.mode = mode
    state.enabled = bool(value)
    if not value:
        state.capacity = []


def epidemic_care_active(world) -> bool:
    """Enabled in a hybrid run with epidemiology and active L9 budgets."""
    state = _state(world)
    if state is None or not state.enabled or getattr(world, "agent_mode", None) != "hybrid":
        return False
    from chronicler.epidemiology import epidemiology_enabled
    if not epidemiology_enabled(world):
        return False
    from chronicler.local_budgets import local_budgets_active
    return local_budgets_active(world)


def check_request(world, values: dict, args, *, agent_mode: str, on) -> None:
    """``livelihoods._check_prerequisites``: refuse what C2 cannot honour.

    ``on(name)``: the switch requested on, or omitted with a saved enabled
    state. Also when only saved: a resume outside hybrid, without L9, without
    epidemiology or the contact ledger, or with the A1 ledger is refused until
    ``--no-epidemic-care`` ends it. A mode needs the switch; a world keeps the
    mode it ran with."""
    state = _state(world)
    mode = getattr(args, "epidemic_care_mode", None) if args is not None else None
    if mode is not None and mode not in MODES:
        raise ValueError(f"epidemic_care_mode must be one of {MODES}")
    switched = on("epidemic_care")
    if mode is not None and not switched:
        raise ValueError("--epidemic-care-mode requires --epidemic-care")
    if not switched:
        return
    from chronicler.contact_ledger import ledger_enabled
    from chronicler.epidemiology import epidemiology_enabled
    missing = []
    if agent_mode != "hybrid":
        missing.append("--agents hybrid")
    if not on("local_budgets"):
        missing.append("--local-budgets")
    if not (epidemiology_enabled(world) and ledger_enabled(world)):
        missing.append("epidemiology with the contact ledger")
    saved = values.get("epidemic_care") is not True
    end = "; this world has it on: pass --no-epidemic-care to end it" if saved else ""
    # A saved world's refusal names the option that ends it and exits without a
    # traceback at the command line (``LivelihoodsRefusal``, a ValueError).
    from chronicler.livelihoods import LivelihoodsRefusal
    refuse = LivelihoodsRefusal if saved else ValueError
    if missing:
        raise refuse("--epidemic-care requires " + ", ".join(missing) + end)
    if on("wealth_accounting"):
        raise refuse("--epidemic-care cannot run with --wealth-accounting (the A1 ledger does not itemize "
                     "care wages)" + end)
    if mode is not None and state is not None and mode != state.mode and (
            state.tick_turn is not None or state.frame_turn is not None):
        raise ValueError(f"--epidemic-care-mode {mode} conflicts with the saved world (saved: {state.mode}); a "
                         "world keeps its epidemic care mode for its whole run")


def _native(agent_bridge):
    sim = getattr(agent_bridge, "_sim", None) if agent_bridge is not None else None
    if sim is None or not all(callable(getattr(sim, name, None)) for name in _NATIVE):
        raise RuntimeError("--epidemic-care requires a native build with the work registry, paid work "
                           "and wealth transfers")
    return sim


# ---------------------------------------------------------------------------
# Regional epidemic quantities (read only)
# ---------------------------------------------------------------------------

def _infectious(world, rows) -> list[float]:
    """Infectious people per region: sum over pathogens of ``burden x n``."""
    n = len(world.regions)
    out = [0.0] * n
    for row in rows:
        if 0 <= row.region < n:
            out[row.region] += row.burden * row.n
    return out


def _expected_deaths(world, rows) -> list[float]:
    """Deaths per turn among the infectious people at the pathogens' own case
    fatality (the persistence forecast L9's proposal values): ``burden x n x
    SUBSTEPS x recovery x cfr`` summed over pathogens."""
    from chronicler.epidemiology import PATHOGENS, SUBSTEPS
    n = len(world.regions)
    out = [0.0] * n
    for row in rows:
        if 0 <= row.region < n and 0 <= row.pathogen < len(PATHOGENS):
            p = PATHOGENS[row.pathogen]
            out[row.region] += row.burden * row.n * SUBSTEPS * p.recovery * p.cfr
    return out


# ---------------------------------------------------------------------------
# The epidemic tick (Phase 1): dated capacity -> a case-fatality factor
# ---------------------------------------------------------------------------

def care_factors(world, rows) -> list[float] | None:
    """Phase 1 of turn T, before the tick absorbs population change: consume
    the capacity dated T - 1 and return each region's care factor (``care``
    mode), or None when no region's factor differs from 1 (every
    ``cost_only`` tick; the epidemic model then runs its own path unchanged).
    Capacity of any other date is refused and recorded, never applied. Records
    the tick (coverage, the factor applied and the one it would apply, the
    practised-medicine factor and the combined factor after the one floor)."""
    state = _state(world)
    if state is None or not state.enabled:
        return None
    turn = world.turn
    n = len(world.regions)
    applying: dict[int, CareCapacity] = {}
    refused: list[CapacityRefusal] = []
    for c in state.capacity:
        if c.source_turn == turn - 1 and 0 <= c.region < n:
            if c.region in applying:
                raise RuntimeError(f"two care capacity rows for region {c.region}")
            applying[c.region] = c
        else:
            reason = ("out_of_range" if c.source_turn == turn - 1 else
                      "future" if c.source_turn >= turn else "stale")
            refused.append(CapacityRefusal(region=c.region, source_turn=c.source_turn, reason=reason))
            _bump(state, f"capacity_{reason}")
    state.capacity = []
    infectious = _infectious(world, rows)
    techniques = None
    from chronicler.techniques_state import techniques_on
    if applying and techniques_on(world):
        from chronicler.techniques import epidemic_cfr_factors
        techniques = epidemic_cfr_factors(world)
    factors = [1.0] * n
    applied = []
    for rid in sorted(applying):
        c = applying[rid]
        inf = infectious[rid]
        coverage = min(1.0, c.patients / inf) if inf > EPS else 0.0
        would = 1.0 - CARE_CFR_REDUCTION * coverage
        from chronicler.public_health import care_allowed
        factor = would if state.mode == "care" and care_allowed(world) else 1.0
        factors[rid] = factor
        tech = techniques[rid] if techniques is not None else None
        combined = combine_one(tech, factor)
        applied.append(CareApplied(region=rid, source_turn=c.source_turn, patients=c.patients, infectious=inf,
                                   coverage=coverage, care_factor=factor, would_be=would, techniques_factor=tech,
                                   combined_factor=combined, floored=factor != 1.0 and combined > (tech or 1.0) * factor))
        _bump(state, "capacity_applied")
        if coverage > 0.0:
            _bump(state, "covered_region_turns")
    state.tick_turn = turn
    state.applied = applied
    state.regions = []          # filled after the tick (Phase 2, ``_observe_tick``)
    state.refused = sorted(refused, key=lambda r: (r.region, r.source_turn, r.reason))
    _bump(state, "ticks_observed")
    if all(f == 1.0 for f in factors):
        return None
    return factors


def combine_one(techniques: float | None, care: float) -> float:
    """One region's fatality factor: practised medicine (1 when off) times
    care, under the one floor ``techniques.CFR_FLOOR``; exactly the
    techniques factor when care is 1."""
    t = 1.0 if techniques is None else techniques
    if care == 1.0:
        return t
    from chronicler.techniques import CFR_FLOOR
    return max(CFR_FLOOR, t * care)


def combine(techniques: list[float] | None, care: list[float]) -> list[float]:
    """Per region (index order): :func:`combine_one` over ``care``."""
    return [combine_one(None if techniques is None else techniques[i], f) for i, f in enumerate(care)]


def _observe_tick(world, state) -> None:
    """Phase 2: this turn's tick, after it (dated the tick): every region with
    an infection row or deaths (deaths, infectious person-turns, new
    infections), and the same for the regions where capacity applied."""
    if state.tick_turn != world.turn:
        return
    epi = world.epidemics
    n = len(world.regions)
    deaths: dict[int, int] = {}
    by_pathogen: dict[int, dict[int, list]] = {}
    for j, k, d in epi.last_deaths:
        deaths[j] = deaths.get(j, 0) + int(d)
        by_pathogen.setdefault(j, {}).setdefault(int(k), [0, 0.0])[0] += int(d)
    cases: dict[int, float] = {}
    for row in epi.rows:
        cases[row.region] = cases.get(row.region, 0.0) + row.cases
        by_pathogen.setdefault(row.region, {}).setdefault(int(row.pathogen), [0, 0.0])[1] += row.burden * row.n
    after = _infectious(world, epi.rows)
    present = {row.region for row in epi.rows if 0 <= row.region < n} | {j for j in deaths if 0 <= j < n}
    state.regions = [TickRegion(region=j, deaths=deaths.get(j, 0), infectious_pt=after[j],
                                cases=round(cases.get(j, 0.0), 6),
                                pathogens=[(k, d, i) for k, (d, i) in sorted(by_pathogen.get(j, {}).items())])
                     for j in sorted(present)]
    for a in state.applied:
        a.deaths = deaths.get(a.region, 0)
        a.cases = round(cases.get(a.region, 0.0), 6)
        a.infectious_after = after[a.region]


# ---------------------------------------------------------------------------
# Phase 2: carers named, reserved, farm time removed; wages after the tick
# ---------------------------------------------------------------------------

def _envelopes(world) -> list:
    """This turn's open L9 commitments for care (one per civ), by civ then cid."""
    from chronicler.local_budgets import _open_for, _state as budget_state
    budgets = budget_state(world)
    if budgets is None:
        return []
    return sorted(_open_for(budgets, world, SERVICE), key=lambda c: (c.civ, c.cid))


def _f32_floor(x: float) -> float:
    from chronicler.grain_storage import _f32_floor as floor
    return floor(x)


def _wage(share: float) -> int:
    """Milli-units for ``share`` of a worker-turn (rounded, as PL1's wage)."""
    return int(round(share * WAGE_MILLI))


def prepare_phase2(world, region_input, agent_bridge, snapshot, acc):
    """Name and reserve this turn's carers and lower the regions' farm labour;
    charges nothing (wages are paid after the native economy tick).

    One envelope per civ covers all of its recipient regions: they draw on it
    in the order of their infectious people (most first, then region index),
    each up to its own need, within the envelope and the civ's projected
    treasury (plus its prepaid carry)."""
    state = _state(world)
    turn = world.turn
    _observe_tick(world, state)
    t = state._turn
    if t is not None and t.turn == turn:
        raise RuntimeError("epidemic care already planned for this turn")
    if t is not None:
        _bump(state, "turns_discarded")       # a failed turn left a plan behind
    sim = _native(agent_bridge)
    t = state._turn = _Turn(turn, sim)
    commitments = _envelopes(world)
    t.prepared = True
    if not commitments:
        return region_input
    from chronicler import labour_reservations
    from chronicler.money import _civ_budget
    from chronicler.recovery_crews import _cities, _farm_share, _People, remove_farm_time
    if snapshot is None:
        snapshot = sim.get_snapshot()
    people = _People(world, snapshot)
    cities = _cities(world)
    booked = labour_reservations.booked(world, sim, turn)
    infectious = _infectious(world, world.epidemics.rows)
    civs = world.civilizations
    n = len(world.regions)
    budgets: dict[int, int] = {}
    removal: dict[int, float] = {}
    reserve: list[tuple[int, float]] = []
    taken: set[int] = set()
    staffed: set[int] = set()
    for c in commitments:
        name = civs[c.civ].name if 0 <= c.civ < len(civs) else None
        envelope_left = int(c.amount) * MILLI
        from chronicler.public_health import guard_reserve
        envelope_left = max(0, envelope_left - guard_reserve(world, c.civ))
        t.envelopes[c.civ] = t.envelopes.get(c.civ, 0) + int(c.amount)
        order = sorted(set(c.recipients), key=lambda j: (-(infectious[j] if 0 <= j < n else 0.0), j))
        for rid in order:
            inf = infectious[rid] if 0 <= rid < n else 0.0
            need = inf / PATIENTS_PER_CARER
            r = CareReceipt(turn=turn, region=rid, civ=c.civ, commitment=c.cid, envelope=c.amount, infectious=inf,
                            need=need, eligible=0)
            t.receipts.append(r)
            if not 0 <= rid < n or name is None or world.regions[rid].controller != name or rid in staffed:
                r.limit = "recipient_lost"
                continue
            if need < MIN_SHARE:
                r.limit = "no_patients"
                continue
            if c.civ not in budgets:
                budgets[c.civ] = (_civ_budget(world, c.civ, acc) * MILLI
                                  + state.book.carry.get(f"{c.civ}:{PURPOSE}", 0))
            eligible = [(aid, settlement) for aid, occupation, settlement in people.residents(rid)
                        if occupation == FARMER and aid not in booked and aid not in taken]
            r.eligible = len(eligible)
            care, limit = 0.0, None
            for aid, settlement in eligible:
                remaining = need - care
                if remaining < MIN_SHARE:
                    limit = "need_met"
                    break
                farm, _diverted, urban = _farm_share(cities, rid, settlement)
                share = _f32_floor(min(farm, remaining))
                if share < MIN_SHARE or _wage(share) < 1:
                    # Below the wage's resolution (a zero wage would book farm time and
                    # date no capacity): nobody is named for it.
                    continue
                money_left = min(envelope_left, budgets[c.civ])
                from chronicler.public_health import wage_budget
                money_left = wage_budget(world, rid, money_left)
                wage = _wage(share)
                if wage > money_left:
                    share = _f32_floor(min(share, money_left / WAGE_MILLI))
                    limit = "envelope" if envelope_left <= budgets[c.civ] else "treasury"
                    wage = min(_wage(share), money_left)
                    if share < MIN_SHARE or wage < 1:
                        break
                if getattr(world.livelihoods, "adaptive_livelihoods", None) is not None:
                    from chronicler.adaptive_livelihoods import accepts_offer
                    if not accepts_offer(world, aid, "epidemic_care"):
                        continue
                r.carers.append(Carer(agent_id=aid, origin="urban_farmer" if urban else "rural_farmer", share=share,
                                      wage_due_milli=wage))
                care += share
                from chronicler.public_health import supply_for_work
                reserve_supplies = supply_for_work(world, rid, share)
                envelope_left -= wage + reserve_supplies
                budgets[c.civ] -= wage + reserve_supplies
                taken.add(aid)
                if limit is not None:
                    break
            if limit is None:
                limit = "need_met" if need - care < MIN_SHARE else "labour"
            r.limit = limit
            r.care_time = math.fsum(x.share for x in r.carers)
            r.patients = r.care_time * PATIENTS_PER_CARER
            r.wages_due_milli = sum(x.wage_due_milli for x in r.carers)
            r.farm_time_removed = r.care_time
            if r.carers:
                staffed.add(rid)
                removal[rid] = removal.get(rid, 0.0) + r.care_time
                reserve.extend((x.agent_id, x.share) for x in r.carers)
    if reserve:
        # All or none; the native registry refuses anyone already holding work.
        sim.reserve_work(turn, CATEGORY_REPAIR, sorted(reserve))
        region_input = remove_farm_time(world, region_input, snapshot, removal, sim=sim)
    return region_input


def finish_phase2(world, economy_result, agent_bridge, acc):
    """After the native economy tick (and every earlier package's Phase 2
    charges): quote each paying civ's wage bill against its treasury now; a
    bill that would be refused pays nobody and withholds nothing, and its
    carers give no capacity (their booked farm time is lost, recorded). Then
    withhold the paid carers' income share for the next wealth phase, pay
    their wages (one keyed bill per civ), date the capacity for the next tick
    and commit the frame."""
    state = _state(world)
    t = state._turn
    if t is None or t.turn != world.turn or not t.prepared:
        raise RuntimeError("epidemic care plan missing for this turn")
    if t.finished:
        raise RuntimeError("epidemic care already settled for this turn")
    turn = world.turn
    bills = _quote_bills(world, state, t, acc)
    refused = {civ for civ, (_bill, quote, _items) in bills.items() if not quote.ok}
    for r in t.receipts:
        if r.civ in refused and r.carers:
            r.unpaid_reason = bills[r.civ][1].reason
            _bump(state, "farm_time_unpaid", r.care_time)
    rows = sorted((x.agent_id, x.share) for r in t.receipts if r.civ not in refused for x in r.carers)
    if rows:
        t.sim.extend_paid_work(turn, rows)
        t.installed = True
    ledger = _pay_wages(world, state, t, acc, bills)
    if state.capacity:
        # Unreachable while every turn's tick consumes the capacity first.
        _bump(state, "capacity_unconsumed", len(state.capacity))
    capacity = []
    for r in sorted(t.receipts, key=lambda r: r.region):
        if r.carers and r.paid:
            if any(c.region == r.region for c in capacity):
                raise RuntimeError(f"two care envelopes staffed region {r.region} in one turn")
            capacity.append(CareCapacity(region=r.region, source_turn=turn, carers=len(r.carers),
                                         care_time=r.care_time, patients=r.patients))
    people = [x.agent_id for r in t.receipts for x in r.carers]
    if len(set(people)) != len(people):
        raise RuntimeError("a carer was named twice in one turn")
    from chronicler.public_health import supply_care
    state.capacity = supply_care(world, t, capacity, economy_result, acc)
    receipts = t.receipts
    if len(receipts) > MAX_FRAME_ROWS:
        state.rows_dropped += len(receipts) - MAX_FRAME_ROWS
        receipts = receipts[:MAX_FRAME_ROWS]
    state.frame_turn, state.frame, state.ledger = turn, receipts, ledger
    _bump(state, "frames")
    for r in t.receipts:
        _bump(state, "envelopes")
        _bump(state, f"limit_{r.limit}")
        _bump(state, "carer_turns", len(r.carers))
        _bump(state, "care_time", r.care_time)
        _bump(state, "patients", r.patients)
        _bump(state, "farm_time_removed", r.farm_time_removed)
    for row in ledger:
        _bump(state, "envelope_coins", row.envelope_coins)
        _bump(state, "wages_due_milli", row.due_milli)
        _bump(state, "wages_paid_milli", row.paid_milli)
        _bump(state, "wage_residual_milli", row.residual_milli)
        _bump(state, "treasury_units", row.treasury_units)
        if row.status.startswith("refused"):
            _bump(state, "unpaid_bills")
    t.finished = True
    return []


def _quote_bills(world, state, t: _Turn, acc) -> dict:
    """{civ: (bill, quote, items)} for every civ with wages due: the bill is
    validated whole against the payer's treasury as it stands now (after the
    other packages' Phase 2 charges), moving nothing."""
    from chronicler import money
    by_civ: dict[int, list[tuple[Carer, int, CareReceipt]]] = {}
    for r in t.receipts:
        for x in r.carers:
            if x.wage_due_milli > 0:
                by_civ.setdefault(r.civ, []).append((x, r.region, r))
    out = {}
    for civ in sorted(by_civ):
        items = sorted(by_civ[civ], key=lambda item: item[0].agent_id)
        bill = money.Bill(purpose="care_wage", batch=CARE_WAGE_BATCH + civ, phase="phase2",
                          lines=tuple((money.agent(x.agent_id), x.wage_due_milli) for x, _rid, _r in items),
                          payer=money.treasury(civ), regions=tuple(rid for _x, rid, _r in items))
        out[civ] = (bill, money.quote(world, bill, turn=world.turn, book=state.book, acc=acc, sim=t.sim), items)
    return out


def _pay_wages(world, state, t: _Turn, acc, bills: dict) -> list[CivWageLedger]:
    """Pay each quoted bill (``money.pay``: validated whole again, exactly once
    per (turn, ``care_wage``, ``CARE_WAGE_BATCH + civ``)); a ledger row for
    every civ that executed an envelope: ``paid``, ``nothing_due`` (no wage
    was due) or ``refused:<reason>`` (nobody of that civ paid or withheld)."""
    from chronicler import money
    turn = world.turn
    ledger = []
    for civ in sorted(set(t.envelopes) | set(bills)):
        key = f"{civ}:{PURPOSE}"
        before = state.book.carry.get(key, 0)
        row = CivWageLedger(turn=turn, civ=civ, envelope_coins=t.envelopes.get(civ, 0), due_milli=0,
                            carry_before=before, carry_after=before)
        ledger.append(row)
        if civ not in bills:
            row.status = "nothing_due"
            continue
        bill, quote, items = bills[civ]
        row.due_milli = sum(x.wage_due_milli for x, _rid, _r in items)
        if not quote.ok:
            row.status = f"refused:{quote.reason}"
            continue
        got = money.pay(world, bill, turn=turn, book=state.book, acc=acc, sim=t.sim)
        if not got.ok:
            raise RuntimeError(f"care wages of civ {civ} refused at payment after a passing quote ({got.reason})")
        flows = {int(f.payee[1]): f for f in got.flows or ()}
        for x, _rid, r in items:
            f = flows[x.agent_id]
            x.wage_paid_milli, x.wage_residual_milli = int(f.applied), int(f.residual)
            r.paid = True
        for r in {id(r): r for _x, _rid, r in items}.values():
            r.wages_paid_milli = sum(x.wage_paid_milli for x in r.carers)
            r.wage_residual_milli = sum(x.wage_residual_milli for x in r.carers)
        row.paid_milli, row.residual_milli = int(got.applied), int(got.residual)
        row.treasury_units = -int(got.treasury_units)
        row.carry_after = state.book.carry.get(key, 0)
        check_ledger(row)
    return ledger


def check_ledger(row: CivWageLedger) -> None:
    """A paid bill closes: units x 1000 + carry before = paid + carry after; due = paid + residual."""
    if row.status != "paid":
        return
    if row.treasury_units * MILLI + row.carry_before != row.paid_milli + row.carry_after:
        raise RuntimeError(f"care wages of civ {row.civ} do not close against the treasury")
    if row.paid_milli + row.residual_milli != row.due_milli:
        raise RuntimeError(f"care wages of civ {row.civ} do not close")
    if not 0 <= row.carry_after < MILLI or row.treasury_units < 0:
        raise RuntimeError(f"care wage carry of civ {row.civ} out of range")


def after_agent_tick(world, agent_bridge):
    """The ordinary income the wealth phase withheld from each carer (the
    shared paid-work receipt, taken once per turn by whichever package asks first)."""
    state = _state(world)
    t = state._turn
    if t is None or t.turn != world.turn or not t.finished:
        return []
    from chronicler.livelihoods import paid_work_receipt
    receipt = paid_work_receipt(world, t.sim) if t.installed else {}
    if receipt is None and t.installed:
        raise RuntimeError("paid work receipt missing for this turn's carers")
    adaptive = getattr(world.livelihoods, "adaptive_livelihoods", None)
    for r in t.receipts:
        for x in r.carers:
            observed = receipt.get(x.agent_id)
            if observed is not None:
                x.income_withheld = float(observed[2])
                _bump(state, "income_withheld", x.income_withheld)
            if adaptive is not None:
                from chronicler.adaptive_livelihoods import forgone_title, note_work
                withheld = (round(float(observed[2]) * MILLI) if observed is not None
                            and abs(float(observed[0]) - x.share) <= 1e-6
                            else 0 if not r.paid else None)
                note_work(world, x.agent_id, "epidemic_care", paid_milli=x.wage_paid_milli,
                          withheld_milli=withheld, title_forgone_milli=forgone_title(world, r.region),
                          source="epidemic_care:untruncated keyed wage and attributable paid-work receipt")
    t.receipt_read = True
    return []


def rollback_phase2(world) -> None:
    """A failed Phase 2 before settlement: nothing of this turn is recorded or
    charged (the native reservations belong to the failed turn)."""
    state = _state(world)
    t = state._turn if state is not None else None
    if t is not None and t.turn == getattr(world, "turn", None) and not t.finished:
        state._turn = None


def rollback_agent_tick(world, agent_bridge) -> None:
    """A failed agent tick: release the paid share still pending natively."""
    state = _state(world)
    t = state._turn if state is not None else None
    if t is not None and t.turn == getattr(world, "turn", None) and t.installed and not t.receipt_read:
        t.sim.cancel_paid_work()


def phase10(world, acc, economy_result, agent_bridge):
    """The turn is complete: drop the in-flight plan (the frame is committed)."""
    state = _state(world)
    if state._turn is not None and state._turn.turn == world.turn:
        state._turn = None
    return []


def on_pool_reset(world) -> None:
    """A rebuilt native pool (a legacy state-file resume): the frame's stable
    ids would name other people, so it is dropped. Pending capacity is
    regional (people served, not ids) and stays dated."""
    state = _state(world)
    if state is None:
        return
    if state.frame:
        _bump(state, "pool_resets")
    state.frame, state.ledger = None, None
    state._turn = None


# ---------------------------------------------------------------------------
# L9 provider: one divisible envelope per region with a reported outbreak
# ---------------------------------------------------------------------------

class _CareEnvelopes:
    """L9 provider (``local_budgets.PROVIDERS``, appended). See the module docstring.

    One divisible proposal per civ covers every region of the civ with a
    reported outbreak (claim ``epidemic_care:<civ>``), so its cost is the
    whole wage need rounded up once to L9's coin: at most one coin per civ and
    turn is reserved beyond the need (L9 counts whole coins; the unspent part
    of an award lapses at settlement, as every envelope's does)."""

    services = (SERVICE,)
    group = "relief"

    def active(self, world) -> bool:
        return epidemic_care_active(world)

    def proposals(self, world, civ: int, obs) -> list[dict]:
        if not self.active(world):
            return []
        from chronicler.local_budgets import _parameters
        food_per_death = _parameters(world)["horizon"] * obs.pcf
        name = world.civilizations[civ].name
        rows = world.epidemics.rows
        n = len(world.regions)
        reported = sorted({row.region for row in rows if row.reported and 0 <= row.region < n})
        infectious = _infectious(world, rows)
        deaths = _expected_deaths(world, rows)
        regions = [rid for rid in reported if world.regions[rid].controller == name
                   and infectious[rid] / PATIENTS_PER_CARER >= MIN_SHARE]
        from chronicler.public_health import guard_regions, guard_reserve, guard_expected_deaths, GUARD_WAGE_MILLI
        regions = sorted(set(regions) | set(guard_regions(world, civ)))
        guards = guard_reserve(world, civ)
        if not regions:
            return []
        need = math.fsum(infectious[rid] / PATIENTS_PER_CARER for rid in regions) + guards / GUARD_WAGE_MILLI
        wages = sum(_wage_total(infectious[rid] / PATIENTS_PER_CARER) for rid in regions)
        from chronicler.public_health import supply_estimate
        supply = supply_estimate(world, math.fsum(infectious[rid] for rid in regions), regions)
        cost = max(1, -(-(wages + supply + guards) // MILLI))
        averted = CARE_CFR_REDUCTION * math.fsum(deaths[rid] for rid in regions) + guard_expected_deaths(world, civ)
        stake = averted * food_per_death
        return [dict(service=SERVICE, recipients=regions, claims=[f"{SERVICE}:{civ}"], cost=cost,
                     divisible=True, unit="care_time", expected=round(need, 6),
                     relief={"commons": round(stake, 6)} if stake > EPS else {},
                     detail={"regions": len(regions), "wages_milli": wages,
                             **({"supplies_milli": supply} if supply else {}),
                             **({"guards_milli": guards} if guards else {}),
                             "infectious": round(math.fsum(infectious[rid] for rid in regions), 6),
                             "expected_deaths": round(math.fsum(deaths[rid] for rid in regions), 6),
                             "deaths_averted": round(averted, 6), "food_per_death": round(food_per_death, 6)})]

    def install(self, world, commitments) -> None:
        return None

    def settle(self, world, c, obs) -> dict:
        state = _state(world)
        if state is None or state.frame_turn != world.turn or state.frame is None:
            reason = "no_economy" if obs.economy is None else "service_off"
            return {"outcome": "deferred", "reason": reason, "spent": 0, "delivered": 0.0, "ratio": 0.0}
        rs = [r for r in state.frame if r.commitment == c.cid]
        if not rs:
            return {"outcome": "deferred", "reason": "service_off", "spent": 0, "delivered": 0.0, "ratio": 0.0}
        paid = sum(r.wages_paid_milli for r in rs)
        delivered = math.fsum(r.care_time for r in rs if r.paid)
        from chronicler.public_health import guard_work
        guards = guard_work(world, c.civ)
        delivered += guards
        limits = [r.limit for r in rs]
        detail = {"regions": len(rs), "carers": sum(len(r.carers) for r in rs), "care_time": round(delivered, 6),
                  "limits": ",".join(sorted(set(limits))), "wages_paid_milli": paid}
        # L9 counts whole coins: the wages, floored (the civ's exact charge,
        # whole units with a prepaid carry, is C2's wage ledger).
        from chronicler.public_health import supply_spent
        supplies = supply_spent(world, c.civ)
        if supplies:
            detail["supplies_milli"] = supplies
        spent = (paid + supplies) // MILLI
        if all(limit == "recipient_lost" for limit in limits):
            return {"outcome": "deferred", "reason": "recipient_lost", "spent": 0, "delivered": 0.0, "ratio": 0.0,
                    "detail": detail}
        if any(r.unpaid_reason for r in rs):
            return {"outcome": "deferred", "reason": "treasury_shortfall", "spent": spent, "delivered": delivered,
                    "ratio": 0.0, "detail": detail}
        if not guards and all(limit in ("no_patients", "recipient_lost") for limit in limits):
            return {"outcome": "kept", "reason": None, "spent": 0, "delivered": 0.0, "ratio": 1.0, "detail": detail}
        ratio = min(1.0, delivered / c.expected) if c.expected > EPS else 1.0
        from chronicler.local_budgets import KEPT_RATIO
        if ratio >= KEPT_RATIO or all(limit in ("need_met", "no_patients", "recipient_lost") for limit in limits):
            return {"outcome": "kept", "reason": None, "spent": spent, "delivered": delivered,
                    "ratio": 1.0 if ratio < KEPT_RATIO else ratio, "detail": detail}
        # The first binding limit: an envelope that ran out while the need grew
        # since the proposal is a cost that rose (review n5), not a labour shortage.
        reasons = {"treasury": "treasury_shortfall", "labour": "work_short", "envelope": "cost_rose"}
        reason = next((reasons[limit] for limit in ("treasury", "labour", "envelope") if limit in limits),
                      "work_short")
        return {"outcome": "deferred", "reason": reason, "spent": spent, "delivered": delivered,
                "ratio": ratio, "detail": detail}

    def obligations(self, world, civ: int, obs) -> int:
        return 0


def _wage_total(care_time: float) -> int:
    """Milli-units of wages for ``care_time`` worker-turns of care."""
    return int(math.ceil(care_time * WAGE_MILLI - EPS))


#: The L9 provider instance (``"chronicler.epidemic_care:BUDGET_PROVIDER"``).
BUDGET_PROVIDER = _CareEnvelopes()


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

def parameters() -> dict:
    from chronicler.techniques import CFR_FLOOR
    return {"care_cfr_reduction": CARE_CFR_REDUCTION, "patients_per_carer": PATIENTS_PER_CARER,
            "wage_milli": WAGE_MILLI, "cfr_floor": CFR_FLOOR, "min_share": MIN_SHARE,
            "care_wage_batch": CARE_WAGE_BATCH, "registry_category": CATEGORY_REPAIR,
            "max_frame_rows": MAX_FRAME_ROWS}


def snapshot_summary(world) -> dict:
    """The completed turn's observation (``source_turn``): the tick's care
    record and the Phase 2 frame are None when that turn was not observed
    (unknown, not zero); ``capacity`` is what the next tick will read."""
    state = _state(world)
    source = world.turn - 1
    fresh = state.frame_turn == source
    tick = None
    if state.tick_turn == source:
        tick = {"turn": state.tick_turn, "applied": [a.model_dump() for a in state.applied],
                "refused": [r.model_dump() for r in state.refused],
                "regions": [r.model_dump() for r in state.regions]}
    from chronicler.public_health import care_allowed
    effective_mode = state.mode if care_allowed(world) else "cost_only"
    return {
        "schema_version": 1, "stage": "C2", "mode": effective_mode, "source_turn": source,
        "units": {"money": "milli_treasury_units", "care": "worker_turns", "patients": "people", "milli": MILLI},
        "tick": tick,
        "frame": [r.model_dump() for r in state.frame] if fresh and state.frame is not None else None,
        "ledger": [r.model_dump() for r in state.ledger] if fresh and state.ledger is not None else None,
        "capacity": [c.model_dump() for c in state.capacity],
        "rows_dropped": state.rows_dropped,
        "counters": {k: state.counters[k] for k in COUNTERS if k in state.counters},
        "parameters": parameters(),
    }
