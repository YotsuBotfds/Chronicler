"""RS5: funded protection of forest cover against population-driven clearing (default off).

``--clearing-protection`` (modes ``enforced``, the default, and ``cost_only``;
see :mod:`chronicler.livelihoods`). Works in every ecology path: the native
ecology (``AgentSimulator`` in agent modes, ``EcologySimulator`` with
``--agents off``) and the pure-Python fallback without an extension. Every
parameter below is a declared modeling choice, not a calibration.
docs/integration/clearing-protection.md.

Mechanism. Population-driven clearing removes a flat ``forest_clearing``
(0.02) of cover from a controlled region whose population is above
``forest_pop_ratio`` (0.5) of its carrying capacity, and regrowth is blocked
while it is. A protection p in [0, 1] is applied at that authoritative
decision, never by restoring cover afterwards: the ecology tick removes
``forest_clearing x (1 - p)`` (native ``ecology::tick_forest_controlled_protected``,
Python ``ecology._tick_forest``). The value travels as the optional Float32
region-batch column ``clearing_protection`` (one row per region, sent only
while a plan is pending, i.e. only with the switch on); the native tick
consumes it and returns per-region ``clearing_active`` and
``cover_not_cleared`` receipts. Cooling, wildfire, volcanoes and succession
are untouched. Because regrowth stays blocked under pressure, protection
freezes cover against clearing; it restores nothing.

Adoption (Phase 9, before the ecology tick; deterministic). The controller
of a region (the civilization at its index in ``world.civilizations``) may
protect a region it controls whose forest cover is at least ``MIN_COVER``
and whose population is above the clearing threshold at planning time. Each
civilization holds at most ``MAX_REGIONS`` protections; candidates are taken
by descending cover, then region index, and only if the projected treasury
can pay the first turn's ``WARDEN_COST`` in full.

Payment. Each protected region-turn with clearing pressure at planning needs
``WARDEN_COST`` coins of wardens, planned against the projected treasury
(queued accumulator changes replayed as the accumulator will apply them)
before the tick, existing protections first in region order. A short
treasury pays what it can: ``p = PROTECTION x paid / WARDEN_COST``. After the
tick the planned payment is charged once, as a disclosed public cost
(accumulator ``keep``), and only for region-turns in which the clearing was
actually active (the authoritative receipt); a tick that failed charges
nothing (its plan is dropped at the next planning). ``cost_only`` adopts,
plans and charges identically but sends p = 0, so the clearing is unchanged;
its receipts record the cover the payment would have kept.

With ``--local-budgets`` (L9) the warden bill is paid only within the ruler's
envelope for ``clearing:<region>`` (service ``clearing_wardens``, in the
``wardens`` group it shares with the L8 commons wardens): see
:data:`BUDGET_PROVIDER`.

Endings. A protection ends when its region changes controller (responsibility
does not transfer: the new controller decides afresh, with its own treasury
and its own ``MAX_REGIONS``, in the same planning), when the region is
uncontrolled, when its cover fell below ``MIN_COVER``, after ``IDLE_LIMIT``
consecutive settled turns without clearing, or after ``UNFUNDED_LIMIT``
consecutive clearing turns with nothing paid.

Trade-off (stated, not modeled as a choice). Protection keeps standing cover:
timber yield (linear in cover), the forest soil bonus above 0.5 cover and
downstream water (the deforestation cascade below 0.2). It forgoes the
forest-to-plains succession after 50 turns below 0.2 cover, which adds 20
carrying capacity.

No RNG, no events.
"""
from __future__ import annotations

import math

import numpy

from chronicler.clearing_protection_state import (
    COUNTER_KEYS, ClearingProtectionState, Protection, ProtectionDecision,
    ProtectionReceipt, UnprotectedRegion,
)
from chronicler.switch_state import bump_counter, sub_state_getter

#: Protections a civilization may hold at once.
MAX_REGIONS = 2
#: Wardens' cost per protected region-turn with clearing pressure (treasury coins).
WARDEN_COST = 2
#: Share of the clearing a fully paid protection suspends.
PROTECTION = 1.0
#: Forested: cover at least this (the succession and deforestation-cascade threshold).
MIN_COVER = 0.2
#: End after this many consecutive settled turns without clearing ...
IDLE_LIMIT = 12
#: ... or this many consecutive clearing turns with nothing paid.
UNFUNDED_LIMIT = 3
MODES = ("enforced", "cost_only")
SCHEMA_VERSION = 1
#: The L9 service and claim prefix of the clearing wardens.
BUDGET_SERVICE = "clearing_wardens"
EPS = 1e-9


class _Row:
    __slots__ = ("protection", "new", "payer", "cover_before", "pressure", "required", "envelope",
                 "paid", "p_planned", "p_applied")

    def __init__(self, **values):
        for name in self.__slots__:
            setattr(self, name, values.get(name))


class _Plan:
    def __init__(self, turn, rows, decisions, column, eligible, candidates, over_limit, unaffordable,
                 unmet=None):
        self.turn, self.rows, self.decisions, self.column = turn, rows, decisions, column
        #: region -> (controller, reason, pressure at planning, cover before the tick)
        self.unmet: dict[int, tuple[int, str, bool, float]] = unmet or {}
        self.eligible, self.candidates = eligible, candidates
        self.over_limit, self.unaffordable = over_limit, unaffordable
        self.receipts: list[tuple[bool, float]] | None = None
        self.source: str | None = None


# --- State and switch -----------------------------------------------------------

_state = sub_state_getter("clearing_protection")


def clearing_protection_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled


def set_clearing_protection_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable (with ``--clearing-protection-mode``, default enforced) or
    disable (protections freeze: no column, no bills; re-enabling resumes them)."""
    mode = getattr(args, "clearing_protection_mode", None) if args is not None else None
    if mode is not None and mode not in MODES:
        raise ValueError(f"clearing_protection_mode must be one of {MODES}")
    state = _state(world)
    if state is None:
        if not value:
            return
        world.livelihoods.clearing_protection = state = ClearingProtectionState(mode=mode or "enforced")
    elif mode is not None:
        state.mode = mode
    state.enabled = bool(value)
    if not value:
        state._plan = None


# --- Observations ---------------------------------------------------------------

def _controller(world, rid: int) -> int:
    name = world.regions[rid].controller
    if name is None:
        return -1
    return world.civ_index_map.get(name, -1)


def forest_pop_ratio(world) -> float:
    from chronicler.tuning import K_FOREST_POP_RATIO, get_override
    return float(get_override(world, K_FOREST_POP_RATIO, 0.5))


def forest_clearing(world) -> float:
    from chronicler.tuning import K_FOREST_CLEARING, get_override
    return float(get_override(world, K_FOREST_CLEARING, 0.02))


def native_ecology(world) -> bool:
    """Whether this run's clearing is decided by the native ecology (f32):
    as Phase 9 last reported it, else every agent mode (the bridge's
    ecology) and agents-off only with a native ecology runtime."""
    state = _state(world)
    flag = state._native_ecology if state is not None else None
    if flag is None:
        flag = getattr(world, "agent_mode", None) not in (None, "off")
    return bool(flag)


def under_pressure(world, region, ratio: float | None = None) -> bool:
    """The ecology's clearing condition, read before the tick, in the
    precision of the engine that decides it: ``ecology::tick_forest_controlled``
    compares ``population as f32 > capacity as f32 * ratio`` in f32, the
    Python fallback (``ecology._tick_forest``) in float64. They differ only for
    a tuned ``ecology.forest_pop_ratio`` that f32 cannot represent exactly
    (review B, 2026-11-05); the default 0.5 is exact in both."""
    ratio = forest_pop_ratio(world) if ratio is None else ratio
    if native_ecology(world):
        f32 = numpy.float32
        return bool(f32(region.population) > f32(region.carrying_capacity) * f32(ratio))
    return region.population > region.carrying_capacity * ratio


def projected_treasury(world, civ_idx: int, acc) -> float:
    """The civ's treasury as the accumulator will leave it after the changes
    queued so far: ``keep`` changes in agent modes (``apply_keep``), every
    category with ``--agents off`` (``apply``), each floored at zero and cast
    as :class:`chronicler.accumulator.StatAccumulator` does."""
    civ = world.civilizations[civ_idx]
    budget = civ.treasury
    if acc is None:
        return float(budget)
    every = getattr(world, "agent_mode", None) in (None, "off")
    start = 0 if every else acc._keep_applied_up_to
    for change in acc._changes[start:]:
        if change.civ_id == civ_idx and change.stat == "treasury" and (every or change.category == "keep"):
            budget = type(civ.treasury)(max(0, budget + change.delta))
    return float(budget)


def _envelope(world, owner: int, rid: int) -> int | None:
    from chronicler.local_budgets import envelope
    return envelope(world, owner, BUDGET_SERVICE, claim=f"clearing:{rid}")


# --- Protocol: Phase 9 ------------------------------------------------------------

def before_ecology(world, acc, *, native: bool | None = None) -> None:
    """Decide (end, adopt) and plan the warden bills and the protection
    column from the pre-tick state. Charges nothing and changes no
    protection; a plan left by a failed tick is dropped first (counted as
    ``abandoned_plans``: it charged nothing). ``native``: whether the native
    ecology decides this turn's clearing (Phase 9), so planning tests the
    clearing condition in that engine's precision (:func:`under_pressure`)."""
    state = _state(world)
    if native is not None:
        state._native_ecology = bool(native)
    if state._plan is not None:
        state._plan = None
        state.counters["abandoned_plans"] = state.counters.get("abandoned_plans", 0) + 1
    turn = world.turn
    ratio = forest_pop_ratio(world)
    enforced = state.mode == "enforced"
    budgets = [max(0, math.floor(projected_treasury(world, i, acc))) for i in range(len(world.civilizations))]
    decisions: list[ProtectionDecision] = []
    rows: list[_Row] = []
    caps: dict[int, int | None] = {}

    def payable(owner: int, rid: int) -> int:
        cap = _envelope(world, owner, rid)
        caps[rid] = cap
        return budgets[owner] if cap is None else min(budgets[owner], cap)

    def plan_row(protection: Protection, owner: int, new: bool, paid: int | None = None) -> _Row:
        region = world.regions[protection.region_id]
        pressure = under_pressure(world, region, ratio)
        required = WARDEN_COST if pressure else 0
        if paid is None:
            paid = min(required, payable(owner, protection.region_id))
        p = PROTECTION * paid / WARDEN_COST if required else 0.0
        budgets[owner] -= paid
        return _Row(protection=protection, new=new, payer=owner,
                    cover_before=float(region.ecology.forest_cover), pressure=pressure,
                    required=required, envelope=caps.get(protection.region_id), paid=paid,
                    p_planned=p, p_applied=p if enforced else 0.0)

    # Existing protections: end or continue (commitments are funded first).
    held: dict[int, int] = {}
    for protection in sorted(state.protections, key=lambda p: p.region_id):
        rid = protection.region_id
        owner = _controller(world, rid)
        reason = None
        if owner < 0:
            reason = "uncontrolled"
        elif owner != protection.payer:
            reason = "controller_changed"
        elif world.regions[rid].ecology.forest_cover < MIN_COVER:
            reason = "cover_lost"
        elif protection.idle_turns >= IDLE_LIMIT:
            reason = "idle"
        elif protection.unfunded_turns >= UNFUNDED_LIMIT:
            reason = "unfunded"
        if reason is not None:
            decisions.append(ProtectionDecision(turn=turn, region_id=rid, civ=protection.payer,
                                                kind="ended", reason=reason))
            continue
        rows.append(plan_row(protection, owner, False))
        held[owner] = held.get(owner, 0) + 1

    # Adoption by the controller, from the pre-tick state.
    protected = {row.protection.region_id for row in rows}
    candidates_by_civ: dict[int, list[int]] = {}
    unmet: dict[int, tuple[int, str, bool, float]] = {}
    eligible = 0
    for rid, region in enumerate(world.regions):
        owner = _controller(world, rid)
        if owner < 0 or not under_pressure(world, region, ratio):
            continue
        if region.ecology.forest_cover < MIN_COVER:
            if rid not in protected:
                unmet[rid] = (owner, "not_forested", True, float(region.ecology.forest_cover))
            continue
        eligible += 1
        if rid not in protected:
            candidates_by_civ.setdefault(owner, []).append(rid)
    candidates = over_limit = unaffordable = 0
    for owner in sorted(candidates_by_civ):
        ranked = sorted(candidates_by_civ[owner], key=lambda r: (-world.regions[r].ecology.forest_cover, r))
        for rid in ranked:
            candidates += 1
            cover = float(world.regions[rid].ecology.forest_cover)
            if held.get(owner, 0) >= MAX_REGIONS:
                over_limit += 1
                unmet[rid] = (owner, "over_limit", True, cover)
                continue
            if payable(owner, rid) < WARDEN_COST:
                unaffordable += 1
                unmet[rid] = (owner, "unaffordable", True, cover)
                continue
            protection = Protection(region_id=rid, payer=owner, adopted_turn=turn)
            rows.append(plan_row(protection, owner, True, paid=WARDEN_COST))
            held[owner] = held.get(owner, 0) + 1
            decisions.append(ProtectionDecision(turn=turn, region_id=rid, civ=owner,
                                                kind="adopted", reason="clearing_pressure"))

    rows.sort(key=lambda r: r.protection.region_id)
    column = [0.0] * len(world.regions)
    for row in rows:
        column[row.protection.region_id] = row.p_applied
    # Controlled regions without pressure at planning: kept so that a clearing
    # the tick reports there anyway (``not_planned``) is still recorded.
    planned = {row.protection.region_id for row in rows}
    for rid, region in enumerate(world.regions):
        owner = _controller(world, rid)
        if owner >= 0 and rid not in planned and rid not in unmet:
            unmet[rid] = (owner, "not_planned", False, float(region.ecology.forest_cover))
    state._plan = _Plan(turn, rows, decisions, column, eligible, candidates, over_limit, unaffordable, unmet)


def pending_protection(world) -> list[float] | None:
    """The protection column of this turn's pending plan (one p per region
    index), or None when no plan awaits this turn's ecology tick. Read by
    ``agent_bridge.build_region_batch`` and the Python ecology fallback."""
    state = _state(world)
    plan = getattr(state, "_plan", None) if state is not None else None
    if plan is None or plan.turn != getattr(world, "turn", None) or plan.receipts is not None:
        return None
    return list(plan.column)


def record_clearing(world, receipts: list[tuple[bool, float]], source: str) -> None:
    """The ecology tick's clearing receipts (clearing active, cover not
    cleared) for every region, from the tick that applied the pending column."""
    state = _state(world)
    plan = getattr(state, "_plan", None) if state is not None else None
    if plan is None or plan.turn != world.turn or plan.receipts is not None:
        raise RuntimeError("clearing receipts without a pending clearing protection plan")
    if len(receipts) != len(world.regions):
        raise RuntimeError("clearing receipts do not cover every region")
    rows = []
    for active, kept in receipts:
        kept = float(kept)
        if not math.isfinite(kept) or kept < 0.0:
            raise RuntimeError(f"invalid cover_not_cleared {kept!r}")
        rows.append((bool(active), kept))
    plan.receipts, plan.source = rows, source


def observe_native(world, region_batch) -> None:
    """Read the native tick's clearing receipts when a column was sent; an
    extension that ignored the column (no receipts returned) raises."""
    if pending_protection(world) is None:
        return
    from chronicler.columnar import pylist, schema_names
    names = set(schema_names(region_batch))
    if "clearing_active" not in names or "cover_not_cleared" not in names:
        raise RuntimeError("clearing protection requires a native extension that returns clearing receipts")
    ids = pylist(region_batch.column("region_id"))
    if ids != list(range(len(world.regions))):
        raise RuntimeError("native ecology rows do not follow world.regions")
    record_clearing(world, list(zip(pylist(region_batch.column("clearing_active")),
                                    pylist(region_batch.column("cover_not_cleared")), strict=True)),
                    "native")


def _bump(counters: dict, key: str, amount) -> None:
    bump_counter(counters, key, amount)


def _timber_capacity_kept(world, rid: int, kept: float) -> float | None:
    from chronicler import timber_stock as ts
    if not ts.timber_stock_active(world):
        return None
    region = world.regions[rid]
    return math.fsum(ts.reference_capacity(region, slot) * kept / ts.woodland_reference_cover()
                     for r, slot in ts.timber_slots(world) if r == rid)


def after_ecology(world, acc) -> list:
    """Charge the planned bills once, for the region-turns whose clearing was
    active, record the receipts and commit the plan."""
    state = _state(world)
    plan, state._plan = state._plan, None
    if plan is None or plan.turn != world.turn:
        raise RuntimeError("clearing protection plan missing for this turn")
    if plan.receipts is None:
        raise RuntimeError("the ecology tick returned no clearing receipts for the protection plan")
    clearing = forest_clearing(world)

    # Validate everything before committing anything.
    charges: list[int] = []
    totals: dict[int, int] = {}
    for row in plan.rows:
        if _controller(world, row.protection.region_id) != row.payer:
            raise RuntimeError("clearing protection payer changed while its bill was pending")
        active, _ = plan.receipts[row.protection.region_id]
        charge = row.paid if active else 0
        charges.append(charge)
        if charge:
            totals[row.payer] = totals.get(row.payer, 0) + charge
    for owner, amount in totals.items():
        if projected_treasury(world, owner, acc) < amount:
            raise RuntimeError("clearing protection bill exceeds the projected treasury at settlement")

    receipts: list[ProtectionReceipt] = []
    for row, charge in zip(plan.rows, charges, strict=True):
        rid = row.protection.region_id
        active, kept = plan.receipts[rid]
        would = clearing * row.p_planned if active else 0.0
        receipts.append(ProtectionReceipt(
            region_id=rid, payer=row.payer, new=row.new, cover_before=row.cover_before,
            cover_after=float(world.regions[rid].ecology.forest_cover), pressure_planned=row.pressure,
            required=row.required, envelope=row.envelope, paid_planned=row.paid,
            p_planned=row.p_planned, p_applied=row.p_applied, clearing_active=active,
            cover_not_cleared=kept, cover_would_keep=would, charged=charge,
            timber_capacity_kept=_timber_capacity_kept(world, rid, kept), source=plan.source,
        ))

    protected = {row.protection.region_id for row in plan.rows}
    unprotected: list[UnprotectedRegion] = []
    for rid in sorted(plan.unmet):
        if rid in protected:
            continue
        owner, reason, pressure, cover = plan.unmet[rid]
        active, _ = plan.receipts[rid]
        if not pressure and not active:
            continue
        unprotected.append(UnprotectedRegion(
            region_id=rid, controller=owner, reason=reason, pressure_planned=pressure,
            clearing_active=active, cover_before=cover,
            cover_after=float(world.regions[rid].ecology.forest_cover), cleared=clearing if active else 0.0))

    # Commit: charge once, then the protections, the record and the counters.
    for owner, amount in sorted(totals.items()):
        civ = world.civilizations[owner]
        if acc is None:
            civ.treasury -= amount
        else:
            acc.add(owner, civ, "treasury", -amount, "keep")
    counters = state.counters
    for key in COUNTER_KEYS:
        counters.setdefault(key, 0)
    _bump(counters, "planned_turns", 1)
    _bump(counters, "settled_turns", 1)
    _bump(counters, "eligible_region_turns", plan.eligible)
    _bump(counters, "adoption_candidates", plan.candidates)
    _bump(counters, "adoption_over_limit", plan.over_limit)
    _bump(counters, "adoption_unaffordable", plan.unaffordable)
    protections = []
    for row, receipt in zip(plan.rows, receipts, strict=True):
        p = row.protection
        if receipt.clearing_active:
            p.idle_turns = 0
            p.unfunded_turns = p.unfunded_turns + 1 if receipt.charged == 0 else 0
            p.active_turns += 1
        else:
            p.idle_turns += 1
        p.charged += receipt.charged
        p.cover_not_cleared += receipt.cover_not_cleared
        protections.append(p)
        _bump(counters, "adopted", 1 if row.new else 0)
        _bump(counters, "protected_region_turns", 1)
        _bump(counters, "pressure_planned_turns", 1 if receipt.pressure_planned else 0)
        _bump(counters, "clearing_active_turns", 1 if receipt.clearing_active else 0)
        _bump(counters, "required", receipt.required)
        _bump(counters, "paid_planned", receipt.paid_planned)
        _bump(counters, "charged", receipt.charged)
        if receipt.required:
            kind = ("full" if receipt.paid_planned >= receipt.required
                    else "zero" if receipt.paid_planned <= 0 else "partial")
            _bump(counters, f"{kind}_funded_turns", 1)
        _bump(counters, "cover_not_cleared", receipt.cover_not_cleared)
        _bump(counters, "cover_would_keep", receipt.cover_would_keep)
        _bump(counters, "timber_capacity_kept", receipt.timber_capacity_kept or 0.0)
    for decision in plan.decisions:
        if decision.kind == "ended":
            _bump(counters, f"ended_{decision.reason}", 1)
    for row in unprotected:
        _bump(counters, "unprotected_clearing_turns", 1 if row.clearing_active else 0)
        _bump(counters, "cover_cleared_unprotected", row.cleared)
    state.protections = sorted(protections, key=lambda p: p.region_id)
    # This turn's decisions in full (at most two per region: an end and an
    # adoption); the snapshot and the L9 settlement read only the current
    # turn, so older turns are not kept. Review B 2026-11-05: a rolling cap
    # of 64 silently dropped decisions of a turn with more.
    state.decisions = list(plan.decisions)
    state.frame = receipts
    state.unprotected = unprotected
    state.frame_turn = plan.turn
    return []


# --- Protocol: observation ------------------------------------------------------

def parameters(world=None) -> dict:
    """Declared parameters, plus the ecology's effective clearing rate and
    population ratio (tuning overrides applied) when a world is given."""
    out = {"max_regions": MAX_REGIONS, "warden_cost": WARDEN_COST, "protection": PROTECTION,
           "min_cover": MIN_COVER, "idle_limit": IDLE_LIMIT, "unfunded_limit": UNFUNDED_LIMIT}
    if world is not None:
        out.update(forest_clearing=forest_clearing(world), forest_pop_ratio=forest_pop_ratio(world))
    return out


def snapshot_summary(world) -> dict:
    """Copied record of the completed turn; never live state.

    ``observed`` is False (receipts None, not empty) when no Phase 9 was
    settled in the completed turn."""
    state = _state(world)
    source_turn = world.turn - 1
    observed = state.frame_turn == source_turn
    return {
        "schema_version": SCHEMA_VERSION,
        "units": {"cover": "forest_cover", "money": "treasury"},
        "mode": state.mode,
        "source_turn": source_turn,
        "completed_turn": world.turn,
        "parameters": parameters(world),
        "observed": observed,
        "receipts": [r.model_dump() for r in state.frame] if observed else None,
        "unprotected": [u.model_dump() for u in state.unprotected] if observed else None,
        "decisions": [d.model_dump() for d in state.decisions if d.turn == source_turn] if observed else None,
        "protections": [p.model_dump() for p in state.protections],
        "counters": dict(state.counters),
    }


# --- L9 local budgets: the clearing wardens' envelope -------------------------------

class _ClearingWardens:
    """L9 provider (``chronicler.local_budgets.PROVIDERS``): a ruler's warden
    bills for its clearing protections, service ``clearing_wardens`` in the
    ``wardens`` group it shares with L8. :func:`before_ecology` pays a bill,
    and adopts a protection, only within the envelope for
    ``clearing:<region>``. Proposals (Phase 10 of the turn before) read that
    turn's state: protections that would continue and adoption candidates by
    this package's own rule, each only where the population is above the
    clearing threshold now (no bill is charged without clearing). The stake is
    the patricians' (the towns' crafts): the timber a turn ``horizon`` turns of
    clearing would take from the region's timber slots at the L3 reference
    crew (``timber_stock.reference_harvest``), in the crew work its raw loads
    could supply (``workshops.K_RAW_PER_WORK``); zero without a timber slot.
    The commons' food burden is not relieved by standing forest, so they gain
    nothing. A continuing protection is divisible (a partial envelope lowers
    p); a new one is not (adoption pays the first bill in full)."""

    services = (BUDGET_SERVICE,)
    group = "wardens"

    def active(self, world) -> bool:
        return clearing_protection_active(world)

    def _stake(self, world, rid: int, horizon: float) -> float:
        from chronicler.timber_stock import reference_harvest
        from chronicler.workshops import K_RAW_PER_WORK
        region = world.regions[rid]
        harvest = math.fsum(reference_harvest(region, slot) for slot in range(3)
                            if int(region.resource_types[slot]) == 1)
        return horizon * forest_clearing(world) * harvest / K_RAW_PER_WORK

    def proposals(self, world, civ, obs):
        if obs.economy is None or not self.active(world):
            return []
        from chronicler.local_budgets import _parameters
        state = _state(world)
        horizon = _parameters(world)["horizon"]
        ratio = forest_pop_ratio(world)
        name = world.civilizations[civ].name

        def item(rid, new):
            stake = self._stake(world, rid, horizon)
            region = world.regions[rid]
            return dict(service=BUDGET_SERVICE, recipients=[rid], claims=[f"clearing:{rid}"], cost=WARDEN_COST,
                        divisible=not new, unit="protection", expected=PROTECTION,
                        relief={"patricians": stake} if stake > EPS else {},
                        detail={"new": int(new), "cover": round(float(region.ecology.forest_cover), 6),
                                "population": int(region.population),
                                "capacity": int(region.carrying_capacity)})

        out, held = [], set()
        for p in state.protections:
            region = world.regions[p.region_id]
            if p.payer != civ or region.controller != name:
                continue
            held.add(p.region_id)
            if (region.ecology.forest_cover < MIN_COVER or p.idle_turns >= IDLE_LIMIT
                    or p.unfunded_turns >= UNFUNDED_LIMIT or not under_pressure(world, region, ratio)):
                continue
            out.append(item(p.region_id, False))
        room = MAX_REGIONS - len(held)
        ranked = sorted((rid for rid, r in enumerate(world.regions)
                         if r.controller == name and rid not in held and r.ecology.forest_cover >= MIN_COVER
                         and under_pressure(world, r, ratio)),
                        key=lambda rid: (-world.regions[rid].ecology.forest_cover, rid))
        out.extend(item(rid, True) for rid in ranked[:max(0, room)])
        return out

    def install(self, world, commitments) -> None:
        return None

    def settle(self, world, c, obs):
        state = _state(world)
        rid = c.recipients[0]
        receipts = {r.region_id: r for r in state.frame} if state.frame_turn == world.turn else {}
        receipt = receipts.get(rid)
        if receipt is None:
            decision = next((d for d in state.decisions if d.turn == world.turn and d.region_id == rid), None)
            reason = ("recipient_lost" if decision is not None and decision.reason in ("controller_changed",
                                                                                       "uncontrolled")
                      else "service_off" if decision is not None else "not_adopted")
            return {"outcome": "deferred", "reason": reason, "spent": 0, "delivered": 0.0, "ratio": 0.0,
                    "detail": {"decision": None if decision is None else f"{decision.kind}:{decision.reason}"}}
        if receipt.payer != c.civ:
            return {"outcome": "deferred", "reason": "recipient_lost", "spent": 0, "delivered": 0.0, "ratio": 0.0}
        due = min(c.amount, WARDEN_COST) if receipt.clearing_active else 0
        detail = {"clearing_active": int(receipt.clearing_active), "p_planned": round(receipt.p_planned, 6)}
        if receipt.charged >= due:
            return {"outcome": "kept", "reason": None, "spent": receipt.charged, "delivered": receipt.p_planned,
                    "ratio": 1.0, "detail": detail}
        return {"outcome": "deferred", "reason": "treasury_shortfall", "spent": receipt.charged,
                "delivered": receipt.p_planned, "ratio": min(1.0, receipt.charged / due), "detail": detail}

    def obligations(self, world, civ, obs) -> int:
        return 0


#: The L9 provider instance (``"chronicler.clearing_protection:BUDGET_PROVIDER"``).
BUDGET_PROVIDER = _ClearingWardens()

