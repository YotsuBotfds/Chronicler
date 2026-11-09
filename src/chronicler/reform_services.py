"""Poor relief as a real service (D1a, ``--reform-services``, default off).

Requires ``--agents hybrid``, ``--household-retail`` (mode ``retail`` or
``no_relief``) and agent movements (on by default). Design: AUDIT-D section
7.4(a) (``docs/superpowers/audits/connected-world/audit-d-institutions-war-owned-stock.md``);
integration page ``docs/integration/reform-services.md``.

Why. A granted poor relief (a ``commons`` movement's lasting reform,
``agent_movements``) changes a label: every agent of the realm reads its
material need as ``need + 0.3 (1 - need)`` for grievance and commitment
(``movements.rs`` ``REFORM_NEED_CREDIT``), while the needs themselves are
untouched, and the realm's relief upkeep (``ceil(0.75 x regions)`` a turn, or
the Commons Management institution's enforcement cost when the reform enacted
or upholds it) is a sink. Nothing is bought; nobody eats more.

Under the switch, both modes withhold the label: the native reform table
(``agent_movements.reform_table``) omits relief rows, so no agent is credited.
The other reforms (home rule, toleration, guild charter) are untouched, and so
is the one-off grant relief every reform gives its movement's members on the
first tick (``relief_age``: a share of the creed need and a fading
satisfaction), which is not the lasting label.

* ``service`` (default): the relief's payment buys food that reaches people
  through an existing channel, the household-retail free pool. The treasury
  pays the same amount at the same time as without the switch: the standalone
  upkeep in Phase 10 (``agent_movements._tick_reforms``), or, for a relief whose
  institution is Commons Management, the institution's share of the Phase 2
  enforcement payment (``governance_runtime.fund_institutions_phase2``, split
  pro rata to enforcement cost). What would have been sunk is paid instead
  into the realm's **relief fund** through the payment seam (``money.py``,
  purpose ``relief_budget``, key ``(turn, purpose, 2 x reform [+1 for the
  institution share])``), up to ``FUND_CAP_TURNS`` turns of upkeep; the rest is
  sunk as before. After the granaries' Phase 10 procurement and before retail
  closes the turn's frame, each realm with a relief in force and money in its
  fund buys from the owners of its own pilot regions where this turn's
  provisioning recorded people priced out or short of offer, for the rations
  they lacked (persons minus rations), neediest region first: at most the unmet rations, at most
  the owned food held there (the owners' unsold surplus), at most what the fund
  can pay at the region's installed ask (``ceil(food x price / ration)``). The
  fund pays the owners by stable id, pro rata to their claims (``money.pay``,
  seam purpose ``relief_purchase`` keyed natively under ``food_procurement``, batch ``1 + region``; a wealth ceiling's
  residual returns to the fund), then retail debits their claims
  (``relief_bought``) and moves the food into the region's commons, so the next
  turn's provisioning offers it in its free pool to those who cannot buy. When
  the relief ends, the fund is returned to the treasury (``relief_refund``).
* ``cost_only``: the control. The label is withheld and the payment is sunk as
  without the switch; nothing is bought.

Nothing is minted: the fund holds only treasury payments, food moves from
owners to the commons at a price paid to the owners, and the free pool gives
only food the economy ate from the commons. Grievance responds only through
the needs that food changes (no label credit, no new grievance channel).

Delivery. The relief food is pooled with the commons, so what reached people
is bounded, never attributed by person. At the next provisioning in the
region the record keeps the free pool (``free_rations``, ``free_given``,
``free_unallocated``); at most ``min(bought, given)`` relief rations reached
people. Gross outbound food is not observed: net transport cannot establish
that the prior relief stayed in this region, even when its final commons
fell short and its storage cap cut nothing. No positive lower delivery bound
is established (None).

Information. A realm reads only its own pilot markets' recorded provisioning
of this turn (the poor roll: unmet rations) and the installed ask; never
provenance or attribution records.

Identity: region = index in ``world.regions``, civ = index in
``world.civilizations``, reform = index in ``MovementState.reforms``; owners by
native stable id. No random draws; every order is by civilization, unmet need
(descending) and region index.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction

from chronicler import money
from chronicler.reform_services_state import (
    COUNTERS, LOG_KINDS, MAX_LOG, MODES, CivRelief, Delivery, Purchase, ReformServicesState, ReliefFrame,
    ReliefRecord,
)
from chronicler.switch_state import sub_state_getter

STAGE = "D1a"
#: A relief fund holds at most this many turns of the realm's relief upkeep;
#: a turn's payment beyond it is sunk as without the switch.
FUND_CAP_TURNS = 4
#: ``food_procurement`` batch of a region's relief bill: this + region index
#: (household retail's granary procurement credit uses batch 0).
RELIEF_BATCH_BASE = 1
#: Unmet need below this many rations is no need (f64 sums of f32 rations).
RATION_EPS = 1e-6
MILLI = money.MILLI


# ---------------------------------------------------------------------------
# State and switch
# ---------------------------------------------------------------------------

_state = sub_state_getter("reform_services")


def _bump(state: ReformServicesState, key: str, amount: int = 1) -> None:
    if key not in COUNTERS:
        raise KeyError(key)
    state.counters[key] = state.counters.get(key, 0) + int(amount)


def _log(state: ReformServicesState, record: ReliefRecord) -> None:
    if record.kind not in LOG_KINDS:
        raise KeyError(record.kind)
    state.log.append(record)
    if len(state.log) > MAX_LOG:
        state.log_dropped += len(state.log) - MAX_LOG
        del state.log[:len(state.log) - MAX_LOG]


@dataclass
class _Purse:
    cash: int


@dataclass
class _Turn:
    turn: int
    civs: dict[int, CivRelief] = field(default_factory=dict)


def set_reform_services_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable, or end: every fund is returned to its treasury, dated; purchases
    awaiting their delivery reading are dropped from the record (their food is
    in the commons already)."""
    mode = getattr(args, "reform_services_mode", None) if args is not None else None
    if mode is not None and mode not in MODES:
        raise ValueError(f"reform_services_mode must be one of {MODES}")
    turn = int(getattr(world, "turn", 0))
    state = _state(world)
    if state is None:
        world.livelihoods.reform_services = state = ReformServicesState(enabled=bool(value),
                                                                        mode=mode or MODES[0])
        if value:
            _log(state, ReliefRecord(turn=turn, kind="switched_on", note=state.mode))
        return
    t = state._turn
    if t is not None and t.turn == turn:
        raise RuntimeError("cannot change reform services while a turn is pending")
    if mode is not None and mode != state.mode:
        if state.funds:
            _refund_all(world, state, turn, note=f"mode {state.mode} -> {mode}")
        state.mode = mode
    if bool(value) == state.enabled:
        return
    state.enabled = bool(value)
    if value:
        _log(state, ReliefRecord(turn=turn, kind="switched_on", note=state.mode))
        return
    _refund_all(world, state, turn, note="switched off")
    state.pending, state.pending_turn = [], None
    state.frame, state.frame_turn = None, None
    state._turn = None
    _log(state, ReliefRecord(turn=turn, kind="switched_off", note=state.mode))


def reform_services_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled and getattr(world, "agent_mode", None) == "hybrid"


def withholds_relief_credit(world) -> bool:
    """Both modes withhold the relief label from the native reform table."""
    return reform_services_active(world)


def _turn(state: ReformServicesState, world) -> _Turn:
    t = state._turn
    if t is None or t.turn != world.turn:
        t = state._turn = _Turn(int(world.turn))
    return t


def _row(state: ReformServicesState, t: _Turn, civ: int) -> CivRelief:
    row = t.civs.get(civ)
    if row is None:
        held = state.funds.get(civ, 0)
        row = t.civs[civ] = CivRelief(civ=civ, fund_open_milli=held, fund_close_milli=held)
    return row


def note_withheld(world, rows: int) -> None:
    """The reform table omitted ``rows`` relief rows this tick (counted)."""
    state = _state(world)
    if state is not None and rows:
        _bump(state, "credit_rows_withheld", rows)


# ---------------------------------------------------------------------------
# Payments into the fund (the treasury's existing relief payment, redirected)
# ---------------------------------------------------------------------------

def _cap_milli(world, civ: int) -> int:
    from chronicler.agent_movements import RELIEF_UPKEEP
    regions = len(world.civilizations[civ].regions)
    return FUND_CAP_TURNS * math.ceil(RELIEF_UPKEEP * regions) * MILLI


def _deposit(world, state: ReformServicesState, acc, civ: int, reform: int, units: int, *, path: str,
             batch: int, phase: str) -> int:
    """Pay up to ``units`` of the treasury's relief payment into the fund (to
    its cap); returns the whole units paid in (the caller sinks the rest as
    without the switch)."""
    t = _turn(state, world)
    row = _row(state, t, civ)
    row.reform, row.path = reform, path
    cap = _cap_milli(world, civ)
    row.cap_milli = cap
    held = state.funds.get(civ, 0)
    room = max(0, (cap - held) // MILLI)
    put = min(int(units), room)
    if put > 0:
        purse = _Purse(held)
        bill = money.Bill(purpose="relief_budget", batch=batch, phase=phase, payer=money.treasury(civ),
                          lines=((money.relief_fund(civ), put * MILLI),))
        got = money.pay(world, bill, turn=int(world.turn), book=state.book, acc=acc, funds={civ: purse})
        if not got.ok:
            _log(state, ReliefRecord(turn=int(world.turn), kind="purchase_refused", civ=civ,
                                     milli=put * MILLI, note=f"fund payment refused: {got.reason}"))
            put = 0
        else:
            state.funds[civ] = purse.cash
    row.to_fund_milli += put * MILLI
    row.sunk_units += int(units) - put
    row.fund_close_milli = state.funds.get(civ, 0)
    _bump(state, "upkeep_to_fund_units" if path == "upkeep" else "institution_to_fund_units", put)
    _bump(state, "sunk_units", int(units) - put)
    return put


def _note_sunk(world, state: ReformServicesState, civ: int, reform: int, units: int, *, path: str) -> None:
    """``cost_only``: the relief payment is sunk as without the switch (recorded)."""
    row = _row(state, _turn(state, world), civ)
    row.reform, row.path = reform, path
    row.sunk_units += int(units)
    _bump(state, "sunk_units", int(units))


def relief_upkeep(world, acc, civ: int, reform: int, due: int) -> int:
    """``agent_movements._tick_reforms``: a standalone relief's upkeep ``due``
    (already affordable). Returns the whole units paid into the fund (service
    mode); the caller sinks ``due`` minus that, as without the switch."""
    state = _state(world)
    if state is None or not reform_services_active(world):
        return 0
    if state.mode != "service":
        _note_sunk(world, state, civ, reform, due, path="upkeep")
        return 0
    return _deposit(world, state, acc, civ, reform, due, path="upkeep", batch=2 * reform, phase="phase10")


def institution_upkeep(world, acc, civ: int, snapshot, paid: int, demand: float) -> int:
    """``governance_runtime.fund_institutions_phase2``: of the enforcement
    payment ``paid`` (whole units, against ``demand``), the Commons Management
    share (pro rata to enforcement cost, floor) when a relief in force has it as
    its institution. Returns the whole units paid into the fund (service mode);
    the caller sinks ``paid`` minus that, as without the switch."""
    state = _state(world)
    if state is None or not reform_services_active(world) or paid <= 0 or not demand > 0:
        return 0
    from chronicler.agent_movements_state import IN_FORCE, RELIEF
    movements = getattr(world, "agent_movements", None)
    reform = next((k for k, r in enumerate(movements.reforms if movements is not None else ())
                   if r.kind == RELIEF and r.repeal == IN_FORCE and r.civ == civ
                   and r.institution == "commons_management"), None)
    if reform is None:
        return 0
    cost = next((i.enforcement_cost for i in snapshot.institutions
                 if getattr(i.institution_type, "value", i.institution_type) == "commons_management"), None)
    if cost is None or not cost > 0:
        # The reform names the institution, but this turn's payment covered no such institution.
        _log(state, ReliefRecord(turn=int(world.turn), kind="institution_share_unknown", civ=civ,
                                 note="the relief's institution is not in this turn's enforcement snapshot"))
        return 0
    share = min(int(paid), math.floor(Fraction(int(paid)) * Fraction(cost) / Fraction(demand)))
    if share <= 0:
        return 0
    if state.mode != "service":
        _note_sunk(world, state, civ, reform, share, path="institution")
        return 0
    return _deposit(world, state, acc, civ, reform, share, path="institution", batch=2 * reform + 1,
                    phase="phase2")


# ---------------------------------------------------------------------------
# Phase 10: deliveries, refunds, purchases
# ---------------------------------------------------------------------------

def _in_force(world) -> dict[int, int]:
    """civ -> index of its relief in force (a realm has at most one)."""
    from chronicler.agent_movements_state import IN_FORCE, RELIEF
    movements = getattr(world, "agent_movements", None)
    out: dict[int, int] = {}
    for k, r in enumerate(movements.reforms if movements is not None else ()):
        if r.kind == RELIEF and r.repeal == IN_FORCE and 0 <= r.civ < len(world.civilizations):
            out.setdefault(r.civ, k)
    return out


def _refund(world, state: ReformServicesState, acc, civ: int, row: CivRelief | None) -> int:
    held = state.funds.get(civ, 0)
    if held <= 0:
        state.funds.pop(civ, None)
        return 0
    purse = _Purse(held)
    bill = money.Bill(purpose="relief_refund", batch=civ, phase="phase10", payer=money.relief_fund(civ),
                      lines=((money.treasury(civ), held),))
    got = money.pay(world, bill, turn=int(world.turn), book=state.book, acc=acc, funds={civ: purse})
    if not got.ok:
        raise money.MoneyError(f"relief fund {civ} could not be returned: {got.reason}")
    state.funds.pop(civ, None)
    if row is not None:
        row.refunded_milli += held
    _bump(state, "refunded_to_treasury_milli", held)
    _log(state, ReliefRecord(turn=int(world.turn), kind="fund_refunded", civ=civ, milli=held))
    return held


def _refund_all(world, state: ReformServicesState, turn: int, *, note: str) -> None:
    """Configuration time (outside a turn, no accumulator): every fund back to
    its treasury through the seam (whole units now, the rest as the book's carry)."""
    for civ in sorted(state.funds):
        held = state.funds[civ]
        if held > 0 and 0 <= civ < len(world.civilizations):
            _refund(world, state, None, civ, None)
            state.log[-1].note = note
        else:
            state.funds.pop(civ, None)


def _ration_milli(world) -> Fraction:
    from chronicler.household_retail import _ration
    return Fraction(_ration(world)) * MILLI


def _deliveries(world, state: ReformServicesState, frame: ReliefFrame, prov: dict | None, turn: int, economy_result=None) -> None:
    if not state.pending:
        return
    rm = _ration_milli(world)
    fresh = state.pending_turn == turn - 1
    for p in state.pending:
        row = (prov or {}).get(p.region) if fresh else None
        if row is None:
            bought = state.pending_turn if state.pending_turn is not None else turn - 1
            frame.deliveries.append(Delivery(region=p.region, civ=p.civ, bought_turn=bought,
                                             rations_bought=p.rations, observed=False))
            _bump(state, "deliveries_unobserved")
            _log(state, ReliefRecord(turn=turn, kind="delivery_unobserved", civ=p.civ, region=p.region,
                                     milli=p.food_milli, note="no provisioning of the region the next turn"))
            continue
        bought = p.rations
        given, pool, left = row["free_given"], row["free_rations"], row["free_unallocated"]
        at_most = min(bought, given)
        # The food ledger's transport column is net: equal outbound/inbound
        # food can hide export of prior relief. A short final commons and no
        # cap overflow therefore do not prove that bought food survived here.
        # Keep the historical field, but do not turn unknown lineage into a
        # positive lower bound. This observer never changes provisioning.
        d = Delivery(region=p.region, civ=p.civ, bought_turn=state.pending_turn, rations_bought=bought,
                     free_rations=round(pool, 6), free_given=round(given, 6), free_unallocated=round(left, 6),
                     delivered_at_most=round(at_most, 6),
                     delivered_at_least=None,
                     priced_out_persons=int(row["priced_out_persons"]),
                     unmet_rations=round(max(0.0, row["persons"] - row["rations"]), 6))
        frame.deliveries.append(d)
        _bump(state, "deliveries_measured")
        _bump(state, "delivered_at_most_milli", math.floor(Fraction(at_most) * rm))


def _purchases(world, state: ReformServicesState, t: _Turn, frame: ReliefFrame, prov: dict | None,
               in_force: dict[int, int], acc, agent_bridge) -> None:
    from chronicler import household_retail as hr
    if not prov:
        return
    turn = int(world.turn)
    rm = _ration_milli(world)
    names = [c.name for c in world.civilizations]
    sim = getattr(agent_bridge, "_sim", None) if agent_bridge is not None else None
    for civ in sorted(in_force):
        need = []
        for rid, row in prov.items():
            if world.regions[rid].controller != names[civ]:
                continue
            # The poor roll: people the provisioning recorded as priced out or
            # short of offer, and the rations they lacked (f32 rounding alone,
            # with nobody recorded short, is no need).
            short = row["priced_out_persons"] + row["offer_short_persons"]
            unmet = max(0.0, row["persons"] - row["rations"])
            if short >= 1 and unmet > RATION_EPS:
                need.append((-unmet, rid, unmet, row))
        if not need:
            continue
        crow = _row(state, t, civ)
        crow.reform = in_force[civ]
        for _key, rid, unmet, row in sorted(need):
            price = int(row["price_milli"])
            cash = state.funds.get(civ, 0)
            owned = hr.owned_milli(world, rid)
            if owned <= 0:
                _bump(state, "need_without_owned_food")
                continue
            if cash <= 0 or price <= 0:
                _bump(state, "need_without_fund")
                continue
            wanted = math.ceil(Fraction(unmet) * rm)
            afford = math.floor(Fraction(cash) * rm / price)
            food = min(wanted, owned, afford)
            if food <= 0:
                _bump(state, "need_without_fund")
                continue
            cost = math.ceil(Fraction(food) * price / rm)
            if not 0 < cost <= cash:
                raise money.MoneyError("a relief purchase costs more than its fund holds")
            shares = hr.relief_shares(world, rid, food)
            pay = hr.largest_remainder(cost, shares.items())
            lines = tuple((money.agent(aid), amount) for aid, amount in sorted(pay.items()) if amount > 0)
            bill = money.Bill(purpose="relief_purchase", batch=RELIEF_BATCH_BASE + rid, phase="phase10",
                              payer=money.relief_fund(civ), lines=lines, regions=(rid,) * len(lines))
            purse = _Purse(cash)
            got = money.pay(world, bill, turn=turn, book=state.book, acc=acc, sim=sim, funds={civ: purse})
            if not got.ok:
                _bump(state, "purchases_refused")
                _log(state, ReliefRecord(turn=turn, kind="purchase_refused", civ=civ, region=rid, milli=cost,
                                         note=str(got.reason)))
                continue
            state.funds[civ] = purse.cash
            taken, goods = hr.take_relief(world, rid, food)
            if taken != shares:
                raise money.MoneyError("relief purchase debited other owners than it paid")
            p = Purchase(region=rid, civ=civ, reform=in_force[civ], unmet_rations=round(unmet, 6),
                         price_milli=price, food_milli=food, goods_milli=list(goods),
                         rations=round(float(Fraction(food) / rm), 6), cost_milli=cost,
                         credited_milli=got.applied, residual_milli=got.residual, sellers=len(shares))
            frame.purchases.append(p)
            state.pending.append(p)
            crow.spent_milli += got.applied
            crow.residual_milli += got.residual
            _bump(state, "purchases")
            _bump(state, "food_bought_milli", food)
            _bump(state, "cost_milli", cost)
            _bump(state, "credited_milli", got.applied)
            _bump(state, "residual_milli", got.residual)
    if state.pending:
        state.pending_turn = turn


def phase10(world, acc, economy_result, agent_bridge):
    """After the granaries' procurement and before retail closes the turn's
    frame (this switch is declared before ``household_retail``): read the
    deliveries of last turn's purchases, return the funds of realms whose relief
    ended, then buy for this turn's recorded need."""
    state = _state(world)
    turn = int(world.turn)
    if state.frame_turn is not None and state.frame_turn >= turn:
        raise RuntimeError("reform services committed twice in one turn")
    t = _turn(state, world)
    frame = ReliefFrame(turn=turn)
    _bump(state, "turns")
    service = state.mode == "service"
    prov = None
    if service:
        from chronicler.household_retail import household_retail_active, settled_provisioning
        prov = settled_provisioning(world) if household_retail_active(world) else None
    _deliveries(world, state, frame, prov, turn, economy_result)
    state.pending, state.pending_turn = [], None
    in_force = _in_force(world)
    for civ in sorted(state.funds):
        if civ not in in_force:
            _refund(world, state, acc, civ, _row(state, t, civ))
    if service:
        _purchases(world, state, t, frame, prov, in_force, acc, agent_bridge)
    for civ in sorted(set(t.civs) | set(in_force)):
        row = _row(state, t, civ)
        if civ in in_force:
            row.reform = in_force[civ]
        row.fund_close_milli = state.funds.get(civ, 0)
        if row.cap_milli == 0 and civ in in_force:
            row.cap_milli = _cap_milli(world, civ)
        if (row.fund_open_milli + row.to_fund_milli - row.spent_milli - row.refunded_milli
                != row.fund_close_milli):
            raise money.MoneyError(f"relief fund {civ} does not close")
        frame.civs.append(row)
    money.check_book(state.book)
    state.frame, state.frame_turn = frame, turn
    state._turn = None
    return []


# ---------------------------------------------------------------------------
# Snapshot and reading
# ---------------------------------------------------------------------------

def snapshot_summary(world) -> dict:
    """The completed turn's record, dated by ``source_turn``; ``frame`` is None
    when that turn was not observed (unknown, not zero)."""
    state = _state(world)
    source = world.turn - 1
    fresh = state.frame_turn == source and state.frame is not None
    return {
        "schema_version": 1, "stage": STAGE, "mode": state.mode, "source_turn": source,
        "frame": state.frame.model_dump() if fresh else None,
        "funds": {str(k): v for k, v in sorted(state.funds.items())},
        "counters": {k: state.counters[k] for k in COUNTERS if k in state.counters},
        "log": [r.model_dump() for r in state.log], "log_dropped": state.log_dropped,
        "parameters": {"fund_cap_turns": FUND_CAP_TURNS, "units": "milli_wealth_and_milli_food",
                       "ration_food": float(_ration_milli(world) / MILLI),
                       "delivery_bounds": "upper_only_gross_outbound_unobserved"},
    }


#: Keys every observed frame carries.
FRAME_KEYS: tuple[str, ...] = ("turn", "civs", "purchases", "deliveries")


def record_status(snapshot) -> tuple[str, dict | None]:
    """How a reader treats one history snapshot's record (the reference for the
    viewer and analysis readers): ``absent``, ``malformed``, ``unobserved``,
    ``recorded_zero`` (observed; no relief money moved, nothing bought or
    delivered) or ``recorded``."""
    livelihoods = snapshot.get("livelihoods") if isinstance(snapshot, dict) else None
    if not isinstance(livelihoods, dict) or "reform_services" not in livelihoods:
        return "absent", None
    record = livelihoods["reform_services"]
    source = record.get("source_turn") if isinstance(record, dict) else None
    if (not isinstance(record, dict) or record.get("schema_version") != 1 or record.get("stage") != STAGE
            or record.get("mode") not in MODES or not isinstance(source, int) or isinstance(source, bool)
            or "frame" not in record):
        return "malformed", None
    frame = record["frame"]
    if frame is None:
        return "unobserved", None
    if (not isinstance(frame, dict) or any(k not in frame for k in FRAME_KEYS) or frame["turn"] != source
            or not all(isinstance(frame[k], list) for k in FRAME_KEYS[1:])):
        return "malformed", None
    from pydantic import ValidationError
    try:
        ReliefFrame.model_validate(frame, strict=True)
    except ValidationError:
        return "malformed", None
    moved = any(c.get("to_fund_milli") or c.get("spent_milli") or c.get("refunded_milli") or c.get("sunk_units")
                for c in frame["civs"])
    empty = not moved and not frame["purchases"] and not frame["deliveries"]
    return ("recorded_zero" if empty else "recorded"), frame
