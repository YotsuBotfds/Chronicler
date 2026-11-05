"""L7 costly voluntary relocation (``--relocation-costs``, default off).

Turns the household liquidity gate into an actual travel expenditure on a
committed ordinary move. Requires ``--agents hybrid``; it cannot run with the
household-mobility liquid reserve (``household_mobility_liquid_requirement``),
which uses the same gate.

What is priced. One ordinary adjacency move per household and turn: the
native consolidator's household group (a moving lead, and the spouse and
dependent children it actually linked, with the same origin and
destination). The fare is ``FARE_MILLI`` per person, children included. It
is required at the native gate (``chronicler-agents/src/relocation.rs``)
from the adult movers' liquid wealth; a household that cannot cover it is
blocked before any move is applied. Merchant trips, refugees, conquest
flows and moves the consolidator cancelled (a rebelling spouse, a contested
destination) never reach the gate and are never charged; an unknown or
non-adjacent route, or a member on a trip, passes unpriced (as the liquid
reserve lets them pass). A return is a new move and pays again.

Modes (``--relocation-mode``):

* ``paid`` (default): the movers' share is debited after the move was
  actually applied;
* ``assisted``: as paid, and the destination's ruler funds a bounded scheme:
  a household short of the fare is offered ``ASSIST_MILLI`` per person
  (never more than the fare) from that ruler's budget for the turn,
  ``ASSIST_SHARE`` of its projected treasury after other pending livelihoods
  bills, reserved in the gate's order. With it, some short households move;
  they pay the rest;
* ``liquidity_only``: the control. The same gate requires the fare, nothing
  is paid and nobody is assisted (a liquidity restriction alone).

Payment, arrival and service are recorded separately. Arrival: the native
receipt names every group and whether every member is now alive in the
destination (the only native relocation of ordinary agents is the apply
phase). Payment: right after the tick, before Phase 10 wages, the movers'
share (fare minus assistance) is debited from the adult movers, split pro
rata by their liquid wealth at the gate (largest remainder, ties by id),
through ``transfer_wealth`` under the appended purpose ``relocation_fare``.
Whatever the transfer cannot take (a death later in the tick, less wealth)
is recorded as a residual, never forgiven silently. The fare goes to a
disclosed travel-cost sink (provisions, carts and tolls; no recipient).
Assistance is charged once in Phase 10 (``phase10_before_reserves``, keep
accumulator), only for applied assisted moves, after re-checking that the
same civilization still rules the destination and that its projected
treasury covers it; a conquest or secession in between, or a short
treasury, refuses the charge and records the grant as unfunded (the move
stands). Service: next turn, the tracked arrivals' region food signal and,
with ``--food-allocation``, their own rations against the residents'.
Arrivals compete for the destination's finite food, work and care like
everyone else; nothing is granted on arrival.

Receiving pressure per touched region and turn: arrivals and departures
(people, households, assisted), alive counts before the gate and after the
moves (only moves change them in between) against carrying capacity, and
the turn's food sufficiency. No randomness; deterministic stable-id order;
settlement is once per turn across exact checkpoints (``last_settled_turn``,
``last_assistance_turn``). Parameters are declared modeling choices.
"""
from __future__ import annotations

import math

from chronicler.relocation_costs_state import (
    COUNTERS, GATE_REASONS, MAX_HOUSEHOLDS, MAX_TRACKED, TRANSFER_STATUSES,
    AssistanceCharge, HouseholdMove, RegionPressure, RelocationCostsState, ServiceReceipt,
)

FARE_MILLI = 1000            # per person, children included (one wealth unit)
ASSIST_MILLI = 500           # per person, to a household short of the fare
ASSIST_SHARE = 0.05          # of the destination ruler's projected treasury per turn
#: Native ``wealth_transfer::PURPOSES`` index of relocation fares.
PURPOSE_RELOCATION_FARE = 1
FARE_BATCH = 0

_NATIVE = ("set_relocation_policy", "cancel_relocation_policy", "take_relocation_receipt", "transfer_wealth")


class _Plan:
    __slots__ = ("turn", "payers", "budgets", "food")

    def __init__(self, turn, payers, budgets, food):
        self.turn, self.payers, self.budgets, self.food = turn, payers, budgets, food


def _state(world) -> RelocationCostsState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "relocation_costs", None) if container is not None else None


def _bump(state: RelocationCostsState, key: str, amount: int = 1) -> None:
    if key not in COUNTERS:
        raise KeyError(key)
    state.counters[key] = state.counters.get(key, 0) + int(amount)


def set_relocation_costs_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    mode = getattr(args, "relocation_mode", None) if args is not None else None
    state = _state(world)
    if state is None:
        world.livelihoods.relocation_costs = state = RelocationCostsState(mode=mode or "paid")
    elif mode is not None:
        if getattr(state, "_pending", None) is not None or getattr(state, "_assist", None) is not None:
            raise RuntimeError("cannot change relocation costs while a settlement is pending")
        state.mode = mode
    state.enabled = bool(value)


def relocation_costs_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled and getattr(world, "agent_mode", None) == "hybrid"


def _civ_index(world, name) -> int:
    if name is None:
        return -1
    return world.civ_index_map.get(name, -1)


def assistance_budgets(world, state) -> list[int]:
    """Milli-units each civilization may grant this turn (assisted mode only)."""
    if state.mode != "assisted":
        return [0] * len(world.civilizations)
    from chronicler.commons_rules import pending_phase2_bills
    bills = pending_phase2_bills(world)
    out = []
    for i, civ in enumerate(world.civilizations):
        projected = max(0, int(civ.treasury) - int(bills[i] if i < len(bills) else 0))
        out.append(int(math.floor(ASSIST_SHARE * projected)) * 1000)
    return out


def before_agent_tick(world, agent_bridge, economy_result) -> None:
    """Install this turn's fare policy; nothing persisted changes here."""
    state = _state(world)
    state._pending = None
    sim = agent_bridge._sim
    if not all(callable(getattr(sim, name, None)) for name in _NATIVE):
        raise RuntimeError("relocation costs require a fresh native build with relocation fares")
    if state.last_settled_turn is not None and world.turn <= state.last_settled_turn:
        raise RuntimeError("relocation fares already settled for this turn")
    payers = [_civ_index(world, r.controller) for r in world.regions]
    budgets = assistance_budgets(world, state)
    food_by_name = getattr(economy_result, "food_sufficiency", None) or {}
    food = [float(food_by_name[r.name]) if r.name in food_by_name else None for r in world.regions]
    track = list(state.tracked) if state.tracked_turn == world.turn - 1 else []
    assist = ASSIST_MILLI if state.mode == "assisted" else 0
    sim.set_relocation_policy(world.turn, FARE_MILLI, assist, payers, budgets, track)
    state._pending = _Plan(world.turn, payers, budgets, food)


def split_share(share: int, adults: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Movers' share over adult movers, pro rata by gate liquidity (largest
    remainder, ties by stable id); equal shares when nobody had liquidity."""
    if share <= 0 or not adults:
        return []
    total = sum(max(0, w) for _, w in adults)
    weights = [(aid, max(0, w) if total > 0 else 1) for aid, w in adults]
    denom = sum(w for _, w in weights)
    base = [(aid, share * w // denom, (share * w) % denom) for aid, w in weights]
    left = share - sum(b for _, b, _ in base)
    order = sorted(range(len(base)), key=lambda i: (-base[i][2], base[i][0]))
    extra = set(order[:left])
    return [(aid, b + (1 if i in extra else 0)) for i, (aid, b, _) in enumerate(base)]


def _region_rows(world, receipt_groups, before, after, food) -> list[RegionPressure]:
    rows: dict[int, RegionPressure] = {}

    def row(r):
        if r not in rows:
            cap = int(world.regions[r].carrying_capacity)
            rows[r] = RegionPressure(region=r, capacity=cap, alive_before=int(before[r]), alive_after=int(after[r]),
                                     pressure_before=(before[r] / cap) if cap > 0 else None,
                                     pressure_after=(after[r] / cap) if cap > 0 else None,
                                     food_sufficiency=food[r])
        return rows[r]

    for g in receipt_groups:
        if not g.applied:
            continue
        dest, origin = row(g.to_region), row(g.from_region)
        dest.arrivals += len(g.members)
        dest.arrival_households += 1
        dest.assisted_households += 1 if g.assistance > 0 else 0
        origin.departures += len(g.members)
        origin.departure_households += 1
    return [rows[r] for r in sorted(rows)]


def on_pool_reset(world) -> None:
    """A rebuilt native pool (``livelihoods.bind_native_pool``): tracked
    arrivals and their origins name other people now and are dropped."""
    state = _state(world)
    if state is None or not (state.tracked or state.origins):
        return
    state.tracked, state.tracked_turn, state.origins = [], None, {}
    _bump(state, "pool_resets")


def rollback_agent_tick(world, agent_bridge) -> None:
    """The agent tick raised: drop an untaken fare policy; nothing is charged."""
    state = _state(world)
    if getattr(state, "_pending", None) is not None:
        state._pending = None
        agent_bridge._sim.cancel_relocation_policy()


def after_agent_tick(world, agent_bridge) -> list:
    """Record arrivals, debit the movers' share once, track arrivals for service."""
    state = _state(world)
    plan, state._pending = state._pending, None
    if plan is None:
        return []
    sim = agent_bridge._sim
    turn = plan.turn
    receipt = sim.take_relocation_receipt(turn)
    if receipt is None:
        sim.cancel_relocation_policy()
        raise RuntimeError("native relocation receipt missing for this turn")
    if state.last_settled_turn is not None and turn <= state.last_settled_turn:
        raise RuntimeError("relocation fares already settled for this turn")
    groups_raw, before, after, _budget_left, rations = receipt
    n = len(world.regions)
    if len(before) != n or len(after) != n:
        raise RuntimeError("native relocation counts do not match the region count")
    origins = dict(state.origins)
    groups: list[HouseholdMove] = []
    liquidity: dict[int, list[tuple[int, int]]] = {}     # group index -> gate liquidity per adult
    gate: dict[str, int] = {}
    for (lead, frm, to, code, applied), (members, adults, children), (liquid, fare, grant, payer) in groups_raw:
        reason = GATE_REASONS[code]
        gate[reason] = gate.get(reason, 0) + 1
        if reason == "short" and applied:
            raise RuntimeError("a blocked household cannot have moved")
        if grant < 0 or grant > fare or (grant > 0 and reason != "assisted"):
            raise RuntimeError("invalid relocation assistance")
        is_return = bool(members) and all(origins.get(m) == to for m in members)
        g = HouseholdMove(turn=turn, lead=lead, from_region=frm, to_region=to, members=list(members),
                          adults=[a for a, _ in adults], children=children, liquid=liquid, reason=reason,
                          applied=applied, fare=fare, assistance=grant, payer=payer,
                          movers_share=fare - grant, is_return=is_return and applied)
        liquidity[len(groups)] = [(a, w) for a, w in adults]
        groups.append(g)
    priced_applied = [g for g in groups if g.applied and g.reason in ("passed", "assisted")]
    # Payment: one transfer for the turn, only for moves actually applied.
    rows, owner = [], {}
    if state.mode in ("paid", "assisted"):
        for i, g in enumerate(groups):
            if not (g.applied and g.reason in ("passed", "assisted")):
                continue
            for aid, amount in split_share(g.movers_share, liquidity[i]):
                if amount > 0:
                    rows.append((aid, -amount))
                    owner[aid] = g
    if rows:
        if sorted(a for a, _ in rows) != sorted(set(a for a, _ in rows)):
            raise RuntimeError("an adult mover belongs to two households")
        for aid, requested, applied_amount, residual, status in sim.transfer_wealth(
                turn, PURPOSE_RELOCATION_FARE, FARE_BATCH, rows):
            g = owner[aid]
            g.debits.append((aid, -requested, -applied_amount, -residual, TRANSFER_STATUSES[status]))
            g.paid += -applied_amount
            g.residual += -residual
    state.last_settled_turn = turn
    # Counters.
    _bump(state, "turns")
    for g in groups:
        _bump(state, "groups_proposed")
        _bump(state, "persons_proposed", len(g.members))
        if g.reason == "short":
            _bump(state, "groups_short")
            _bump(state, "persons_short", len(g.members))
        elif g.reason in ("route", "trip"):
            _bump(state, "groups_unpriced")
        else:
            _bump(state, "groups_passed" if g.reason == "passed" else "groups_assisted")
        if g.applied:
            _bump(state, "groups_applied")
            _bump(state, "persons_applied", len(g.members))
            _bump(state, "children_applied", g.children)
            if g.is_return:
                _bump(state, "returns")
    for g in priced_applied:
        _bump(state, "fare_due_milli", g.fare)
        _bump(state, "assistance_granted_milli", g.assistance)
        if state.mode == "liquidity_only":
            _bump(state, "fare_not_charged_milli", g.movers_share)
            continue
        _bump(state, "fare_debited_milli", g.paid)
        _bump(state, "fare_residual_milli", g.residual)
        _bump(state, "travel_sink_milli", g.paid)
        if g.paid > 0:
            _bump(state, "groups_paid")
        if g.residual:
            _bump(state, "groups_with_residual")
    # Service receipts for last turn's arrivals (this tick's allocation and food signal).
    services = None
    if state.tracked_turn == turn - 1 and state.tracked:
        services = []
        if rations is not None:
            for region, arrivals, a_sum, residents, r_sum in rations:
                services.append(ServiceReceipt(
                    region=region, arrival_turn=turn - 1, food_sufficiency=plan.food[region],
                    arrivals_rationed=arrivals, residents_rationed=residents,
                    arrivals_mean_ration=(a_sum / arrivals) if arrivals else None,
                    residents_mean_ration=(r_sum / residents) if residents else None))
        else:
            # No allocation this tick: arrivals read their region's signal;
            # last turn's frame names where they arrived.
            for region in sorted({row.region for row in state.regions if row.arrivals}):
                services.append(ServiceReceipt(region=region, arrival_turn=turn - 1,
                                               food_sufficiency=plan.food[region]))
        _bump(state, "service_receipts", len(services))
    # Assistance to settle in Phase 10 (assisted mode, applied assisted moves only).
    state._assist = (turn, [g for g in priced_applied if g.assistance > 0]) if state.mode == "assisted" else None
    # Arrivals to follow next turn (bounded) and their origins (to name returns).
    tracked = []
    for g in groups:
        if g.applied:
            for m in g.members:
                origins.pop(m, None)
                origins[m] = g.from_region
                if len(tracked) < MAX_TRACKED:
                    tracked.append(m)
    while len(origins) > MAX_TRACKED:
        origins.pop(next(iter(origins)))
    state.origins = origins
    state.tracked, state.tracked_turn = tracked, turn
    state.regions = _region_rows(world, groups, before, after, plan.food)
    state.services = services
    state.gate = gate
    keep = sorted(groups, key=lambda g: (not g.applied, g.reason not in ("passed", "assisted"), g.lead))
    state.households = keep[:MAX_HOUSEHOLDS]
    state.households_dropped = max(0, len(groups) - MAX_HOUSEHOLDS)
    state.assistance = []
    state.frame_turn = turn
    return []


def phase10_before_reserves(world, acc, economy_result, agent_bridge) -> list:
    """Charge each destination ruler once for the assistance actually used."""
    state = _state(world)
    pending, state._assist = state._assist, None
    if pending is None:
        return []
    turn, groups = pending
    if turn != world.turn:
        raise RuntimeError("relocation assistance pending for another turn")
    if state.last_assistance_turn is not None and turn <= state.last_assistance_turn:
        raise RuntimeError("relocation assistance already settled for this turn")
    from chronicler.mutual_aid import _treasury_budget
    by_civ: dict[int, list[HouseholdMove]] = {}
    for g in groups:
        by_civ.setdefault(g.payer, []).append(g)
    charges = []
    for civ_idx in sorted(by_civ):
        civ = world.civilizations[civ_idx] if 0 <= civ_idx < len(world.civilizations) else None
        same, moved = [], []
        for g in by_civ[civ_idx]:
            ruler = _civ_index(world, world.regions[g.to_region].controller)
            (same if civ is not None and ruler == civ_idx else moved).append(g)
        for g in moved:
            g.assistance_status = "controller_changed"
        refused = sum(g.assistance for g in moved)
        if moved:
            charges.append(AssistanceCharge(civ=civ_idx, turn=turn, granted=refused, refused=refused,
                                            status="controller_changed"))
        granted = sum(g.assistance for g in same)
        if granted:
            coins = -(-granted // 1000)
            if _treasury_budget(world, civ, acc) < coins:
                for g in same:
                    g.assistance_status = "treasury_short"
                charges.append(AssistanceCharge(civ=civ_idx, turn=turn, granted=granted, refused=granted,
                                                status="treasury_short"))
                refused += granted
            else:
                if acc is None:
                    civ.treasury -= coins
                else:
                    acc.add(civ_idx, civ, "treasury", -coins, "keep")
                for g in same:
                    g.assistance_status = "charged"
                charges.append(AssistanceCharge(civ=civ_idx, turn=turn, granted=granted, charged_coins=coins,
                                                status="charged"))
                _bump(state, "assistance_charged_milli", granted)
                # The treasury pays whole units: the sink receives them all,
                # and the rounding above the grant is disclosed.
                _bump(state, "travel_sink_milli", coins * 1000)
                _bump(state, "assistance_rounding_milli", coins * 1000 - granted)
        _bump(state, "assistance_refused_milli", refused)
    # Mirror the statuses into the kept household sample.
    status = {(g.lead, g.turn): g.assistance_status for g in groups}
    for h in state.households:
        if (h.lead, h.turn) in status:
            h.assistance_status = status[(h.lead, h.turn)]
    state.assistance = charges
    state.last_assistance_turn = turn
    return []


def snapshot_summary(world) -> dict:
    state = _state(world)
    source = world.turn - 1
    observed = state.frame_turn == source
    return {
        "schema_version": 1, "stage": "L7", "mode": state.mode, "source_turn": source,
        # None: no relocation turn was completed in the source turn (unknown, not zero).
        "gate": dict(state.gate) if observed else None,
        "households": [h.model_dump() for h in state.households] if observed else None,
        "households_dropped": state.households_dropped if observed else None,
        "regions": [r.model_dump() for r in state.regions] if observed else None,
        "services": ([s.model_dump() for s in state.services] if state.services is not None else None)
                    if observed else None,
        "assistance": [a.model_dump() for a in state.assistance] if observed else None,
        "counters": {k: state.counters[k] for k in COUNTERS if k in state.counters},
        "parameters": {"fare_milli": FARE_MILLI, "assist_milli": ASSIST_MILLI if state.mode == "assisted" else 0,
                       "assist_share": ASSIST_SHARE if state.mode == "assisted" else 0.0,
                       "max_households": MAX_HOUSEHOLDS, "max_tracked": MAX_TRACKED},
    }
