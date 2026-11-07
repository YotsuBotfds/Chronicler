"""L6a workshop payroll with an actual public customer (``--workshop-payroll``).

Default off; requires ``--workshops`` in operate mode (L1B). A bounded,
debt-free transactional layer around the actual L1 workshop, not a finance
rewrite. Modes (``--workshop-payroll-mode``): ``paid`` (default), the
cost-retaining ablation ``unpaid_labor`` (the firm sells and its crew's
ordinary income share is replaced, but no wage is paid) and the demand
control ``no_customer`` (wages are owed, nothing is sold).

Accounts. An operating L1 site gets one firm when an academy of its region's
ruler has an open order (last turn's fully informed procurement left need
and budget); until then the site stays an L1B public workshop. A firm has
working cash (starts at 0, never negative, no borrowing, no rescue) and
owned wares inventory. Once open it keeps operating after its customer
goes away (the demand-collapse path below). Money is
kept in whole milli-units: 1000 milli-units are one treasury unit and one
native wealth unit (the equivalence domestic credit already uses). Wares
are kept in milli-loads. The firm is the site's: it follows the site through
a change of controller, as the L1B asset's arrears do.

Title (pilot custodian rule). The native economy puts this turn's craft
output into the region's shared stock, and the same tick's wares use by the
people, merchant departures, wear and the stock cap draw on that stock. When
the site operated, the whole region's craft output is its crew's (L1 replaces
the region's craft ceiling with the site's). After the successful tick the
firm takes title to at most that output, only from the region's stock not
already committed to merchants, and only up to ``INVENTORY_CAP``: exactly that
quantity leaves the region's stock and enters the firm's inventory, so it is
never counted twice. What the region's market used first is not titled.

Customer. The only existing public purchaser of crafts is academy supply
procurement (``learning_services``; ``--scholarship --techniques
--academy-services``). After that Phase 10 procurement has run, an academy
whose ruler controls the firm's region and whose procurement this turn was
fully informed (upkeep paid, counts, price and commitments known) may buy
from the firm for its remaining need, ``min(learners, 8 x scholars) - held``
crafts, at the craft price its own procurement used, within its ruler's
projected treasury. A sale settles in whole treasury units: the ruler's
treasury pays (accumulator ``keep``), the firm's cash receives the same
amount, and the wares those units buy (rounded down to a milli-load) move
from the firm's inventory into the academy's material inventory at once.
Delivery within the realm is a declared simplification (no transport time
or loss). Payment and delivery settle together, so there are no refunds.

Payroll. Paid time is the crew's scheduled diverted time (L1: ``d = 1 -
URBAN_FARM_LABOR[rank]``, times the firm's hours). The native wealth phase
withholds that share of each worker's ordinary occupational income
(``AgentSimulator.install_paid_work``) and reports the actual amount, so a
wage replaces that income instead of adding to it. In Phase 10, after sales,
the firm pays each worker ``WAGE_PER_WORK`` per unit of paid time plus any
wages owed, from cash only, pro rata when short (largest remainder, ties by
id), by stable id through ``AgentSimulator.transfer_wealth`` (once per turn
and firm). What a worker's wealth ceiling refuses stays in the firm's cash
(recorded, not owed). A dead worker's claim lapses (recorded). Unpaid wages
are owed (arrears) and are paid first from later cash.

Pressure. A turn that ends with wages owed is insolvent: hours fall by
``HOURS_STEP`` (to at least ``MIN_HOURS``) for the next turn; from the
``LAYOFF_AFTER``-th insolvent turn in a row the crew cap falls by
``LAYOFF_STEP``; after ``CLOSE_AFTER`` the firm closes and its L1 site closes
with reason ``insolvent``. A solvent turn whose cash covers the next turn's
bill at the next step restores one step of hours and one crew place. Cash
above ``RESERVE_TURNS`` full wage bills is distributed to the region's
controller (keep). At any closure the firm pays wages owed from cash (when
it has not paid this turn), writes off what remains owed, returns its
inventory to the region's market stock, distributes its cash in whole units
to the region's controller and writes off the sub-unit remainder.

Accounting closes exactly, per firm and in integers: ``cash = sales - wages
applied - distributions - write-offs`` and ``inventory = titled - delivered -
worn - returned`` (inventory wears ``WARES_WEAR`` a turn, the native wares
storage rate). Model-provided ordinary income, wealth decay and the wealth
ceiling remain the native model's separately labelled sources and sinks.
All parameters below are declared modeling choices, not calibrated.
"""
from __future__ import annotations

import math

from chronicler.workshop_payroll_state import (
    MAX_CLOSED, MAX_HISTORY, MAX_OWED, MAX_TRANSFERS, MaterialTransfer, MoneyTransfer, OwedWage,
    PayrollReceipt, WorkshopFirm, WorkshopPayrollState,
)

MILLI = 1000
#: Wage per unit of paid work time (one person's whole turn), milli-units.
WAGE_PER_WORK = 500
#: Most wares one firm holds (milli-loads).
INVENTORY_CAP = 20_000
#: Wear of held wares per turn (the native crafts storage rate).
WARES_WEAR = 0.01
HOURS_STEP = 0.25
MIN_HOURS = 0.25
LAYOFF_AFTER = 2
LAYOFF_STEP = 2
CLOSE_AFTER = 6
RESERVE_TURNS = 4
#: Native ``wealth_transfer::PURPOSES`` index of workshop wages.
PURPOSE_WORKSHOP_WAGE = 0
_FULL_CREW = 8

# ``stipends`` (RS1 apprentice stipends, :func:`pay_from_firm`) is absent from
# every firm unless apprenticeship paid one, so it reads as 0 otherwise; so are
# A3's ``capital``, ``inputs``, ``household_sales`` and ``household_delivered``
# (``--workshop-economics``).
_TOTAL_KEYS = ("sales", "wages", "distributed", "written_off", "titled", "delivered", "worn", "returned",
               "stipends", "capital", "inputs", "household_sales", "household_delivered")


class _Work:
    __slots__ = ("site", "crew", "shares", "output", "basis", "titled")

    def __init__(self, site, crew, shares, output, basis, titled):
        self.site, self.crew, self.shares = site, crew, shares
        self.output, self.basis, self.titled = output, basis, titled


class _Turn:
    """One turn in flight (never checkpointed: cleared by Phase 10)."""

    def __init__(self, turn: int, sim=None):
        self.turn, self.sim = turn, sim
        self.work: dict[int, _Work] = {}
        self.installed = False
        self.receipt: dict[int, tuple[float, float, float]] | None = None
        self.money: list[MoneyTransfer] = []
        self.materials: list[MaterialTransfer] = []
        self.rows: dict[int, dict] = {}
        self.alive: set[int] | None = None       # living ids after the tick, read once


# ---------------------------------------------------------------------------
# Switch and lookups
# ---------------------------------------------------------------------------

def _state(world) -> WorkshopPayrollState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "workshop_payroll", None) if container is not None else None


def _workshops(world):
    container = getattr(world, "livelihoods", None)
    return getattr(container, "workshops", None) if container is not None else None


def set_workshop_payroll_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    mode = getattr(args, "workshop_payroll_mode", None) if args is not None else None
    state = _state(world)
    if state is None:
        world.livelihoods.workshop_payroll = state = WorkshopPayrollState(mode=mode or "paid")
    elif mode is not None:
        if state._turn is not None:
            raise RuntimeError("cannot switch payroll mode while a turn is pending")
        state.mode = mode
    state.enabled = bool(value)


def workshop_payroll_active(world) -> bool:
    state = _state(world)
    if state is None or not state.enabled:
        return False
    from chronicler.workshops import workshops_active
    return workshops_active(world) and _workshops(world).mode == "operate"


def _economics(world):
    """A3 seam (``--workshop-economics``): its module while it is active, else
    None (never imported for a world that never enabled it)."""
    if getattr(getattr(world, "livelihoods", None), "workshop_economics", None) is None:
        return None
    from chronicler import workshop_economics
    return workshop_economics if workshop_economics.workshop_economics_active(world) else None


def _firm(state: WorkshopPayrollState, site: int) -> WorkshopFirm | None:
    return next((f for f in state.firms if f.site == site), None)


def crew_terms(world, site: int) -> tuple[int, float]:
    """(crew cap, hours) the site's firm sets for this turn's crew request."""
    state = _state(world)
    if state is None or not workshop_payroll_active(world):
        return _FULL_CREW, 1.0
    firm = _firm(state, site)
    terms = (firm.crew_cap, firm.hours) if firm is not None else (_FULL_CREW, 1.0)
    economics = _economics(world)
    if economics is not None:            # A3: the crew its affordable inputs occupy
        return economics.crew_terms(world, site, *terms)
    return terms


def _controller(world, region: int) -> int | None:
    name = world.regions[region].controller
    if name is None:
        return None
    for i, civ in enumerate(world.civilizations):
        if civ.name == name:
            return i
    return None


def _bump(state, key: str, amount=1) -> None:
    state.counters[key] = state.counters.get(key, 0) + amount


def _total(firm: WorkshopFirm, key: str, amount: int) -> None:
    firm.totals[key] = firm.totals.get(key, 0) + amount


def _note(firm: WorkshopFirm, turn: int, event: str, amount: int = 0) -> None:
    firm.history.append((turn, event, amount))
    del firm.history[:-MAX_HISTORY]


def _row(t: _Turn, firm: WorkshopFirm) -> dict:
    row = t.rows.get(firm.site)
    if row is None:
        row = t.rows[firm.site] = dict(site=firm.site, region=firm.region, cash_open=firm.cash,
                                       inventory_open=firm.inventory, hours=firm.hours,
                                       crew_cap=firm.crew_cap)
    return row


def _add(row: dict, key: str, amount) -> None:
    row[key] = row.get(key, 0) + amount


def _treasury(world, civ: int, delta: int, acc) -> None:
    if not delta:
        return
    target = world.civilizations[civ]
    if acc is None:
        target.treasury += delta
    else:
        acc.add(civ, target, "treasury", delta, "keep")


def _budget(world, civ: int, acc) -> int:
    from chronicler.mutual_aid import _treasury_budget
    return max(0, math.floor(_treasury_budget(world, world.civilizations[civ], acc)))


def check_firm(firm: WorkshopFirm) -> None:
    """Exact integer closure of the firm's cash and inventory accounts."""
    t = {k: firm.totals.get(k, 0) for k in _TOTAL_KEYS}
    if firm.cash != (t["capital"] + t["sales"] + t["household_sales"] - t["inputs"] - t["wages"]
                     - t["distributed"] - t["written_off"] - t["stipends"]) or firm.cash < 0:
        raise RuntimeError(f"workshop firm {firm.site} cash does not close")
    if firm.inventory != (t["titled"] - t["delivered"] - t["household_delivered"] - t["worn"] - t["returned"]) \
            or firm.inventory < 0:
        raise RuntimeError(f"workshop firm {firm.site} inventory does not close")


# ---------------------------------------------------------------------------
# Money movements
# ---------------------------------------------------------------------------

def _pro_rata(cash: int, due: dict[int, int]) -> dict[int, int]:
    total = sum(due.values())
    if cash >= total:
        return dict(due)
    pay, rest = {}, []
    for aid in sorted(due):
        num = cash * due[aid]
        pay[aid] = num // total
        rest.append((-(num % total), aid))
    left = cash - sum(pay.values())
    for _, aid in sorted(rest)[:left]:
        pay[aid] += 1
    return pay


def _living(t: _Turn) -> set[int]:
    """Stable ids alive now (deaths happen only in the native tick), from the
    native snapshot of the living pool, read once per phase: before the tick
    for a Phase 2 liquidation, after it for Phase 10 wages (``phase10`` resets it)."""
    if t.sim is None:
        raise RuntimeError("workshop wages require the native simulator")
    if t.alive is None:
        t.alive = {int(a) for a in t.sim.get_snapshot().column("id").to_pylist()}
    return t.alive


def _pay(world, state, firm: WorkshopFirm, t: _Turn, due: dict[int, int], phase: str) -> dict:
    """Pay ``due`` (milli-units by stable id) from cash once; update owed.

    Dead workers' claims lapse first, so scarce cash is shared only among the
    living (a lead review on 2026-11-05 found the first landing shared it with
    the dead, kept their share in cash and left a dead claim with a zero share
    owed)."""
    row = _row(t, firm)
    since = {o.agent_id: o.since_turn for o in firm.owed}
    if due:
        living = _living(t)
        for aid in sorted(a for a in due if a not in living):
            _add(row, "owed_lapsed", due[aid])
            _bump(state, "owed_lapsed", due[aid])
        due = {aid: amount for aid, amount in due.items() if aid in living}
    pay = _pro_rata(firm.cash, due)
    rows = [(aid, amount) for aid, amount in sorted(pay.items()) if amount > 0]
    result = {}
    if rows:
        if t.sim is None:
            raise RuntimeError("workshop wages require the native simulator")
        for aid, requested, applied, residual, status in t.sim.transfer_wealth(
                t.turn, PURPOSE_WORKSHOP_WAGE, firm.site, rows):
            result[aid] = (int(applied), int(residual), int(status))
    owed = []
    for aid in sorted(due):
        applied, residual, status = result.get(aid, (0, 0, 0))
        if status == 2:                       # absent (defensive: the living set was read first)
            _add(row, "owed_lapsed", due[aid])
            _bump(state, "owed_lapsed", due[aid])
            residual = 0
        else:
            remaining = due[aid] - pay[aid]
            if remaining > 0:
                owed.append(OwedWage(agent_id=aid, amount=remaining, since_turn=since.get(aid, t.turn)))
        if applied:
            firm.cash -= applied
            _total(firm, "wages", applied)
            _add(row, "wages_paid", applied)
            _bump(state, "wages_paid", applied)
        if residual:
            _add(row, "wages_cap_residual", residual)
            _bump(state, "wage_cap_residual", residual)
        if pay[aid]:
            t.money.append(MoneyTransfer(
                id=f"wp:{t.turn}:wage:{firm.site}:{aid}", turn=t.turn, phase=phase, kind="wage",
                payer=("workshop_cash", firm.site), payee=("agent_wealth", aid), amount=pay[aid],
                applied=applied, residual=pay[aid] - applied,
                status=("absent" if status == 2 else "limited" if applied != pay[aid] else "applied")))
    owed.sort(key=lambda o: (o.since_turn, o.agent_id))
    if len(owed) > MAX_OWED:
        dropped = owed[:-MAX_OWED]
        owed = owed[-MAX_OWED:]
        lost = sum(o.amount for o in dropped)
        _bump(state, "owed_written_off", lost)
        _note(firm, t.turn, "owed_written_off", lost)
    firm.owed = owed
    return result


def _distribute(world, state, firm: WorkshopFirm, t: _Turn, amount: int, acc, phase: str,
                write_rest: bool) -> None:
    """Move ``amount`` milli-units of cash to the region's controller in whole
    units; with ``write_rest`` the sub-unit remainder (or everything, when no
    civilization controls the region) goes to a named sink."""
    row = _row(t, firm)
    owner = _controller(world, firm.region)
    units = amount // MILLI if owner is not None else 0
    if units:
        firm.cash -= units * MILLI
        _total(firm, "distributed", units * MILLI)
        _treasury(world, owner, units, acc)
        _add(row, "distributed", units * MILLI)
        _bump(state, "distributed", units * MILLI)
        t.money.append(MoneyTransfer(
            id=f"wp:{t.turn}:distribution:{firm.site}", turn=t.turn, phase=phase, kind="distribution",
            payer=("workshop_cash", firm.site), payee=("civ_treasury", owner),
            amount=units * MILLI, applied=units * MILLI))
    rest = amount - units * MILLI
    if write_rest and rest > 0:
        firm.cash -= rest
        _total(firm, "written_off", rest)
        _add(row, "written_off", rest)
        _bump(state, "cash_written_off", rest)
        t.money.append(MoneyTransfer(
            id=f"wp:{t.turn}:write_off:{firm.site}", turn=t.turn, phase=phase, kind="write_off",
            payer=("workshop_cash", firm.site), payee=("sink", 0), amount=rest, applied=rest))


def _material(t: _Turn, firm: WorkshopFirm, kind: str, source, dest, amount: int, phase: str) -> None:
    t.materials.append(MaterialTransfer(
        id=f"wp:{t.turn}:{kind}:{firm.site}:{len(t.materials)}", turn=t.turn, phase=phase, kind=kind,
        source=source, dest=dest, requested=amount, delivered=amount))


def _liquidate(world, state, firm: WorkshopFirm, t: _Turn, reason: str, acc, phase: str,
               pay_owed: bool) -> None:
    row = _row(t, firm)
    if pay_owed and firm.owed and firm.cash > 0:
        _pay(world, state, firm, t, {o.agent_id: o.amount for o in firm.owed}, phase)
    lost = sum(o.amount for o in firm.owed)
    if lost:
        _bump(state, "owed_written_off", lost)
        _note(firm, t.turn, "owed_written_off", lost)
        firm.owed = []
    if firm.inventory:
        amount = firm.inventory
        goods = world.regions[firm.region].stockpile.goods
        goods["crafts"] = goods.get("crafts", 0.0) + amount / MILLI
        firm.inventory = 0
        _total(firm, "returned", amount)
        _add(row, "returned", amount)
        _bump(state, "returned", amount)
        _material(t, firm, "return", ("workshop_inventory", firm.site), ("region_market", firm.region),
                  amount, phase)
    _distribute(world, state, firm, t, firm.cash, acc, phase, write_rest=True)
    check_firm(firm)
    firm.status, firm.closed_turn, firm.closed_reason = "closed", t.turn, reason
    _note(firm, t.turn, f"closed_{reason}")
    row["event"] = f"closed_{reason}"
    state.firms.remove(firm)
    state.closed.append(firm)
    del state.closed[:-MAX_CLOSED]
    _bump(state, f"closed_{reason}")
    economics = _economics(world)
    if economics is not None:
        economics.on_closed(world, firm, reason, t.turn)


# ---------------------------------------------------------------------------
# Phase hooks
# ---------------------------------------------------------------------------

def _native(agent_bridge):
    sim = getattr(agent_bridge, "_sim", None)
    if sim is None or not all(callable(getattr(sim, name, None)) for name in (
            "transfer_wealth", "install_paid_work", "cancel_paid_work", "take_paid_work_receipt")):
        raise RuntimeError("workshop payroll requires a fresh native build with wealth transfers")
    return sim


def prepare_phase2(world, region_input, agent_bridge, snapshot, acc):
    state = _state(world)
    _native(agent_bridge)
    if state._turn is not None:
        raise RuntimeError("workshop payroll turn already pending")
    if state.last_payroll_turn is not None and world.turn <= state.last_payroll_turn:
        raise ValueError("workshop payroll already settled for this turn")
    return region_input


def finish_phase2(world, economy_result, agent_bridge, acc):
    """After the workshop settled: title this turn's output, arm the paid-work
    income share and liquidate firms whose site closed."""
    state = _state(world)
    ws = _workshops(world)
    sim = _native(agent_bridge)
    if ws.frame_turn != world.turn:
        raise RuntimeError("workshop receipts missing for this turn")
    t = _Turn(world.turn, sim)
    economics = _economics(world)
    commitments = None
    plans, rows = [], []
    orders = None
    for receipt in ws.frame:                       # site order
        if not receipt.allocated or not receipt.crew:
            continue
        order = None
        if _firm(state, receipt.site) is None and economics is not None:
            continue                                # A3: firms open with owner capital (Phase 10)
        if _firm(state, receipt.site) is None:
            # A firm opens around an actual order: an academy of the region's
            # ruler whose last procurement left need it could pay for.
            if orders is None:
                orders = _open_orders(world)
            order = orders.get(_controller(world, receipt.region))
            if order is None:
                _bump(state, "operating_without_order")
                continue
        share = float(receipt.diverted_fraction)
        output = receipt.region_craft_output
        titled, basis = 0, None
        firm = _firm(state, receipt.site)
        held = firm.inventory if firm is not None else 0
        if output is not None and output > 0 and economics is not None and economics.owned_output(world):
            # A3-2: the native column kept the whole output out of the commons;
            # the firm takes all of it (its ceiling was bounded by its room).
            titled = math.floor(output * MILLI)
            if titled > INVENTORY_CAP - held:
                raise RuntimeError(f"workshop firm {receipt.site} produced beyond its inventory room")
        elif output is not None and output > 0:
            if commitments is None:
                from chronicler.mutual_aid import read_stockpile_commitments
                commitments = read_stockpile_commitments(world, sim)
            region = world.regions[receipt.region]
            stock = float(region.stockpile.goods.get("crafts", 0.0))
            basis = max(0.0, stock - float(commitments.get(region.name, {}).get("crafts", 0.0)))
            titled = max(0, min(math.floor(output * MILLI), math.floor(basis * MILLI), INVENTORY_CAP - held))
        plans.append((receipt, share, output, basis, titled, order))
        rows.extend((aid, share) for aid in receipt.crew)
    if rows:
        sim.install_paid_work(world.turn, rows)    # validates against the work registry first
        t.installed = True
    state._turn = t
    for receipt, share, output, basis, titled, order in plans:
        firm = _firm(state, receipt.site)
        if firm is None:
            site = next(s for s in ws.sites if s.site == receipt.site)
            firm = WorkshopFirm(site=site.site, region=site.region, settlement_id=site.settlement_id,
                                city_name=site.city_name, opened_turn=world.turn)
            _note(firm, world.turn, "opened", order)
            state.firms.append(firm)
            _bump(state, "firms_opened")
        firm.diverted = share / firm.hours
        row = _row(t, firm)
        receipt.affected_ordinary_income_share = share
        t.work[firm.site] = _Work(firm.site, list(receipt.crew), [share] * len(receipt.crew),
                                  output, basis, titled)
        row.update(operating=True, crew=list(receipt.crew), shares=[share] * len(receipt.crew),
                   output=output, title_basis=basis, titled=titled)
        _bump(state, "operating_site_turns")
        _bump(state, "paid_person_turns", len(receipt.crew))
        if output:
            _bump(state, "output", math.floor(output * MILLI))
        if titled:
            owned = economics is not None and economics.owned_output(world)
            if not owned:
                goods = world.regions[firm.region].stockpile.goods
                goods["crafts"] = goods.get("crafts", 0.0) - titled / MILLI
            firm.inventory += titled
            _total(firm, "titled", titled)
            _bump(state, "titled", titled)
            _material(t, firm, "title", ("workshop_output", firm.site) if owned else ("region_market", firm.region),
                      ("workshop_inventory", firm.site), titled, "phase2")
    if economics is not None:                     # A3: charge the inputs used, observe prices
        economics.charge_inputs(world, t, acc, economy_result)
    open_sites = {s.site for s in ws.sites}
    reasons = {s.site: s.closed_reason for s in ws.closed}
    for firm in list(state.firms):
        if firm.site not in open_sites:
            _liquidate(world, state, firm, t, reasons.get(firm.site) or "city_missing", acc, "phase2",
                       pay_owed=True)
    return []


def rollback_phase2(world) -> None:
    state = _state(world)
    t = getattr(state, "_turn", None) if state is not None else None
    if t is not None and t.turn == world.turn:
        if t.installed and t.sim is not None:
            t.sim.cancel_paid_work()
        state._turn = None
    if getattr(getattr(world, "livelihoods", None), "workshop_economics", None) is not None:
        from chronicler.workshop_economics import rollback
        rollback(world)


def on_pool_reset(world) -> None:
    """A rebuilt native pool (``livelihoods.bind_native_pool``): wages owed to
    saved ids would go to other people, so they lapse with reason
    ``pool_reset`` (recorded per firm and in ``owed_pool_reset``)."""
    state = _state(world)
    if state is None:
        return
    for firm in state.firms:
        lapsed = sum(o.amount for o in firm.owed)
        if lapsed:
            _total(firm, "owed_pool_reset", lapsed)
            _note(firm, world.turn, "owed_pool_reset", lapsed)
            _bump(state, "owed_pool_reset", lapsed)
        firm.owed = []


def rollback_agent_tick(world, agent_bridge) -> None:
    """The agent tick raised: disarm an unconsumed paid-work share. A failed
    turn is abandoned, so its Phase 10 (and any wage) never runs."""
    state = _state(world)
    t = getattr(state, "_turn", None) if state is not None else None
    if t is not None and t.turn == world.turn and t.installed and t.sim is not None:
        t.sim.cancel_paid_work()
        t.installed = False


def after_agent_tick(world, agent_bridge):
    state = _state(world)
    t = state._turn
    if t is None or t.turn != world.turn or not t.installed:
        return []
    from chronicler.livelihoods import paid_work_receipt
    receipt = paid_work_receipt(world, t.sim)   # shared with other paid-work packages
    if receipt is None:
        raise RuntimeError("paid work receipt missing for this turn")
    t.receipt = receipt
    return []


def _customers(world) -> list[tuple[int, object, object]]:
    """Academy purchasers whose procurement ran fully informed this turn:
    (lord, procurement receipt, material inventory), in seat order."""
    services = getattr(getattr(world, "scholarship", None), "learning_services", None)
    if services is None or not getattr(services, "enabled", True) \
            or getattr(services, "last_procurement_turn", None) != world.turn:
        return []
    assets = {(a.seat_id, a.region, a.founder, a.founded_turn, a.seat_name): a
              for a in (getattr(services, "inventories", None) or []) if not a.retired}
    out = []
    for r in getattr(services, "procurement_receipts", None) or []:
        if r.source_turn != world.turn or r.shortfalls or not r.craft_price or r.craft_price <= 0:
            continue
        asset = assets.get((r.seat_id, r.region, r.founder, r.founded_turn, r.seat_name))
        if asset is None or asset.held is None or r.scholar_upper_bound is None or r.learner_upper_bound is None:
            continue
        out.append((r.lord, r, asset))
    return sorted(out, key=lambda c: c[1].seat_id)


def _open_orders(world) -> dict[int, int]:
    """Rulers with an open academy order from last turn's procurement: a
    fully informed purchaser with need left after its purchases and budget
    left for at least one unit. Maps civ index -> seat id (first by seat)."""
    from chronicler.learning_services import CRAFTS_PER_LEARNER, LEARNERS_PER_SCHOLAR
    services = getattr(getattr(world, "scholarship", None), "learning_services", None)
    if services is None or not getattr(services, "enabled", True):
        return {}
    out: dict[int, int] = {}
    for r in sorted(getattr(services, "procurement_receipts", None) or [], key=lambda r: r.seat_id):
        if (r.source_turn != world.turn - 1 or r.shortfalls or not r.craft_price or r.held_after is None
                or r.scholar_upper_bound is None or r.learner_upper_bound is None or r.budget_before is None):
            continue
        need = (min(float(r.learner_upper_bound), r.scholar_upper_bound * LEARNERS_PER_SCHOLAR)
                * CRAFTS_PER_LEARNER - r.held_after)
        if need * MILLI >= 1 and r.budget_before - r.paid >= 1:
            out.setdefault(r.lord, r.seat_id)
    return out


def _remaining_need(receipt, asset) -> float:
    from chronicler.learning_services import CRAFTS_PER_LEARNER, LEARNERS_PER_SCHOLAR
    want = min(float(receipt.learner_upper_bound), receipt.scholar_upper_bound * LEARNERS_PER_SCHOLAR)
    return max(0.0, want * CRAFTS_PER_LEARNER - asset.held)


def _sell(world, state, firm: WorkshopFirm, t: _Turn, customers, acc) -> None:
    row = _row(t, firm)
    owner = _controller(world, firm.region)
    if firm.inventory <= 0:
        return
    _bump(state, "offered_firm_turns")
    if owner is None:
        return
    for lord, receipt, asset in customers:
        if lord != owner or firm.inventory <= 0:
            continue
        need = math.floor(_remaining_need(receipt, asset) * MILLI)
        budget = _budget(world, lord, acc)
        from chronicler.local_budgets import envelope   # L9 teaching envelope (None: the legacy rule)
        cap = envelope(world, lord, "teaching_supplies", site=firm.site)
        if cap is not None:
            budget = min(budget, max(0, cap - row.get("sales", 0) // MILLI))
        if need <= 0 or budget <= 0:
            continue
        _add(row, "customers", 1)
        price = float(receipt.craft_price)
        cap = min(firm.inventory, need)
        units = min(budget, math.floor(cap * price / MILLI))
        while units > 0 and math.floor(units * MILLI / price) > cap:
            units -= 1
        quantity = math.floor(units * MILLI / price) if units else 0
        if units <= 0 or quantity <= 0:
            continue
        _treasury(world, lord, -units, acc)
        firm.cash += units * MILLI
        firm.inventory -= quantity
        asset.held += quantity / MILLI
        asset.purchased_total += quantity / MILLI
        _total(firm, "sales", units * MILLI)
        _total(firm, "delivered", quantity)
        _add(row, "sales", units * MILLI)
        _add(row, "sold", quantity)
        _bump(state, "sales_paid")
        _bump(state, "sales", units * MILLI)
        _bump(state, "delivered", quantity)
        t.money.append(MoneyTransfer(
            id=f"wp:{t.turn}:sale:{firm.site}:{receipt.seat_id}", turn=t.turn, phase="phase10", kind="sale",
            payer=("civ_treasury", lord), payee=("workshop_cash", firm.site),
            amount=units * MILLI, applied=units * MILLI))
        _material(t, firm, "delivery", ("workshop_inventory", firm.site),
                  ("academy_inventory", receipt.seat_id), quantity, "phase10")
    if row.get("customers"):
        _bump(state, "customer_firm_turns")


def _wage(share: float) -> int:
    return math.floor(share * WAGE_PER_WORK + 0.5)


def _bill(firm: WorkshopFirm, crew: int, hours: float) -> int:
    return crew * _wage(firm.diverted * hours)


def phase10(world, acc, economy_result, agent_bridge):
    state = _state(world)
    t = state._turn
    sim = _native(agent_bridge)
    if t is None or t.turn != world.turn:
        t = _Turn(world.turn, sim)
    # A Phase 2 liquidation read the living before the tick; Phase 10 wages
    # share cash only among those alive after it (read once, on first use).
    t.alive = None
    if t.installed and t.receipt is None:
        sim.cancel_paid_work()               # no wealth phase took it: unknown, not zero
    customers = _customers(world) if state.mode != "no_customer" else []
    economics = _economics(world)
    for firm in list(state.firms):
        row = _row(t, firm)
        _sell(world, state, firm, t, customers, acc)
        if economics is not None:               # A3: then the region's households
            economics.sell_to_households(world, firm, t, customers, acc, sim)
        work = t.work.get(firm.site)
        due = {o.agent_id: o.amount for o in firm.owed}
        if work is not None:
            if t.receipt is not None:
                replaced = math.fsum(t.receipt[a][2] for a in work.crew if a in t.receipt)
                row["income_replaced"] = replaced
                _bump(state, "income_replaced", replaced)
            if state.mode != "unpaid_labor":
                for aid, share in zip(work.crew, work.shares):
                    due[aid] = due.get(aid, 0) + _wage(share)
                    _add(row, "wages_due", _wage(share))
                    _bump(state, "wages_due", _wage(share))
        if due:
            _pay(world, state, firm, t, due, "phase10")
        if firm.inventory:
            worn = math.floor(firm.inventory * WARES_WEAR)
            if worn:
                firm.inventory -= worn
                _total(firm, "worn", worn)
                _add(row, "worn", worn)
                _bump(state, "worn", worn)
                _material(t, firm, "wear", ("workshop_inventory", firm.site), ("sink", 0), worn, "phase10")
        owed = sum(o.amount for o in firm.owed)
        if owed and state.mode != "unpaid_labor":
            row["insolvent"] = True
            firm.insolvent_run += 1
            _bump(state, "insolvent_firm_turns")
            if firm.hours > MIN_HOURS:
                firm.hours = max(MIN_HOURS, firm.hours - HOURS_STEP)
                _note(firm, t.turn, "hours_cut", round(firm.hours * 100))
                _bump(state, "hours_cuts")
            if firm.insolvent_run >= LAYOFF_AFTER and firm.crew_cap > 1:
                firm.crew_cap = max(1, firm.crew_cap - LAYOFF_STEP)
                _note(firm, t.turn, "layoff", firm.crew_cap)
                _bump(state, "layoffs")
            if firm.insolvent_run >= CLOSE_AFTER:
                _liquidate(world, state, firm, t, "insolvent", acc, "phase10", pay_owed=False)
                from chronicler.workshops import close_site
                close_site(world, firm.site, "insolvent")
                continue
        else:
            firm.insolvent_run = 0
            if economics is not None and economics.idle_close(world, firm, t):
                _liquidate(world, state, firm, t, "idle", acc, "phase10", pay_owed=True)
                from chronicler.workshops import close_site
                close_site(world, firm.site, "idle")
                continue
            hours = min(1.0, firm.hours + HOURS_STEP)
            cap = min(_FULL_CREW, firm.crew_cap + 1)
            if (hours, cap) != (firm.hours, firm.crew_cap) and firm.cash >= _bill(firm, cap, hours):
                firm.hours, firm.crew_cap = hours, cap
                _note(firm, t.turn, "recovered", firm.crew_cap)
            reserve = RESERVE_TURNS * _bill(firm, _FULL_CREW, 1.0) if state.mode != "unpaid_labor" else 0
            if economics is not None:            # A3: keep the inputs' reserve too
                reserve += economics.input_reserve(world, firm)
            if firm.cash > reserve:
                _distribute(world, state, firm, t, firm.cash - reserve, acc, "phase10", write_rest=False)
        check_firm(firm)
        if economics is not None:
            economics.check_firm(world, firm)
    if economics is not None:                   # A3: sites without a firm may open one
        economics.open_firms(world, t, acc)
    receipts = []
    for site, row in sorted(t.rows.items()):
        firm = _firm(state, site) or next(f for f in state.closed if f.site == site)
        owner = _controller(world, firm.region)
        receipts.append(PayrollReceipt(
            turn=t.turn, controller=owner, cash_close=firm.cash, inventory_close=firm.inventory,
            owed_after=sum(o.amount for o in firm.owed), hours_next=firm.hours,
            crew_cap_next=firm.crew_cap, **row))
    state.frame = receipts
    state.frame_turn = t.turn
    state.money = t.money[-MAX_TRANSFERS:]
    state.materials = t.materials[-MAX_TRANSFERS:]
    state.last_payroll_turn = t.turn
    state._turn = None
    _bump(state, "payroll_turns")
    if economics is not None:
        economics.commit_frame(world, t)
    return []


def pay_from_firm(world, sim, site: int, due: dict[int, int], *, purpose: int,
                  kind: str = "stipend") -> dict[int, tuple[int, int, int]] | None:
    """Recovery-skills helper (RS1 apprentice stipends): pay ``due``
    (milli-units by stable id) from the cash of ``site``'s open firm, in Phase
    10 after this turn's payroll pass (wages first), once per ``(turn,
    purpose, site)`` through ``AgentSimulator.transfer_wealth``.

    Returns None when the site has no open firm (nothing is paid), otherwise
    ``{id: (offered, applied, status)}`` with the native status (0 applied, 1
    limited by the wealth ceiling, 2 absent). Short cash is shared pro rata
    (largest remainder, ties by id, as wages); what is not offered is not
    owed. Only applied amounts leave the cash: what a ceiling refuses or an
    absent id cannot take stays. Each payment is a typed ``stipend``
    :class:`MoneyTransfer`, the firm's ``totals["stipends"]`` (subtracted by
    :func:`check_firm`) and this turn's receipt (``stipends``, ``cash_close``),
    so the firm's cash closure stays exact."""
    if kind != "stipend":
        raise ValueError(f"unknown firm payment kind {kind!r}")
    state = _state(world)
    if state is None or state.last_payroll_turn != world.turn or state.frame_turn != world.turn:
        raise RuntimeError("firm payments follow this turn's payroll pass")
    firm = _firm(state, site)
    if firm is None:
        return None
    due = {int(aid): int(amount) for aid, amount in due.items()}
    if any(amount < 0 for amount in due.values()):
        raise ValueError("firm payments must be non-negative")
    pay = _pro_rata(firm.cash, due)
    rows = [(aid, amount) for aid, amount in sorted(pay.items()) if amount > 0]
    result = {aid: (pay[aid], 0, 0) for aid in due}
    if rows:
        for aid, requested, applied, residual, status in sim.transfer_wealth(world.turn, purpose, site, rows):
            if int(requested) != pay[int(aid)] or int(applied) + int(residual) != int(requested):
                raise RuntimeError("firm payment transfer does not match its rows")
            result[int(aid)] = (pay[int(aid)], int(applied), int(status))
    paid = 0
    for aid in sorted(due):
        offered, applied, status = result[aid]
        paid += applied
        if offered:
            state.money.append(MoneyTransfer(
                id=f"wp:{world.turn}:{kind}:{site}:{aid}", turn=world.turn, phase="phase10", kind=kind,
                payer=("workshop_cash", site), payee=("agent_wealth", aid), amount=offered, applied=applied,
                residual=offered - applied,
                status=("absent" if status == 2 else "limited" if applied != offered else "applied")))
    del state.money[:-MAX_TRANSFERS]
    if paid:
        firm.cash -= paid
        _total(firm, "stipends", paid)
        _bump(state, "stipends_paid", paid)
    receipt = next((r for r in state.frame if r.site == site), None)
    if receipt is not None:
        receipt.stipends = (receipt.stipends or 0) + paid
        receipt.cash_close = firm.cash
    check_firm(firm)
    return result


def snapshot_summary(world) -> dict:
    state = _state(world)
    source = world.turn - 1
    fresh = state.frame_turn == source
    return {
        "schema_version": 1, "stage": "L6a", "mode": state.mode, "source_turn": source,
        "units": {"money": "milli_treasury_units", "wares": "milli_loads", "milli": MILLI},
        "firms": [f.model_dump() for f in state.firms],
        "closed": [f.model_dump() for f in state.closed],
        # None: no completed payroll pass for this turn (unknown, not zero).
        "receipts": [r.model_dump() for r in state.frame] if fresh else None,
        "transfers": ({"money": [m.model_dump() for m in state.money],
                       "materials": [m.model_dump() for m in state.materials]} if fresh else None),
        "counters": dict(state.counters),
        "parameters": {"wage_per_work": WAGE_PER_WORK, "inventory_cap": INVENTORY_CAP,
                       "wares_wear": WARES_WEAR, "hours_step": HOURS_STEP, "min_hours": MIN_HOURS,
                       "layoff_after": LAYOFF_AFTER, "layoff_step": LAYOFF_STEP,
                       "close_after": CLOSE_AFTER, "reserve_turns": RESERVE_TURNS},
    }
