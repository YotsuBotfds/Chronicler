"""A4-3 cross-civilization timber orders with title, finite budgets and escrow.

A treasury buys only a PL1-refused repair gap. A named merchant buys real free
commons timber from the origin ruler, then carries title. The destination
escrows whole coins at dispatch and pays only delivered timber into the PL1
repair store; decay and cancelled deliveries refund the destination. Carrier
income is withheld while reserved so a trade margin replaces the model source.
A cancelled order deposits its timber at its current region as commons (the
merchant bears this explicitly recorded procurement loss); it never teleports
or destroys physical cargo. A new order always receives a new persisted id.
"""
from __future__ import annotations
import math
from types import SimpleNamespace
from chronicler import money as M
from chronicler import titled_trade as TT
from chronicler.timber_orders_state import COUNTERS, MAX_CLOSED, MAX_EVENTS, MAX_ORDERS, TimberOrder, TimberOrdersState
from chronicler.switch_state import sub_state_getter

MILLI = 1000
FREIGHT = 0.10
MAX_AGE = 12
BATCH = 0xA430000
SERVICE = "timber_orders"
REFUSALS = {"no_forest", "too_far", "forest_depleted", "forest_busy"}


_state = sub_state_getter("timber_orders")


def _bump(state, key, amount=1):
    if key not in COUNTERS:
        raise KeyError(f"undeclared timber order counter {key}")
    state.counters[key] = state.counters.get(key, 0) + int(amount)


def timber_orders_active(world):
    state = _state(world)
    return state is not None and state.enabled and getattr(world, "agent_mode", None) == "hybrid"


def set_timber_orders_enabled(world, value, *, args=None, agent_mode=None):
    if value:
        if agent_mode != "hybrid":
            raise ValueError("--timber-orders requires --agents hybrid")
        container = getattr(world, "livelihoods", None)
        if not all(getattr(getattr(container, name, None), "enabled", False)
                   for name in ("timber_supply", "local_budgets")):
            raise ValueError("--timber-orders requires --timber-supply and --local-budgets")
        if _state(world) is None:
            world.livelihoods.timber_orders = TimberOrdersState()
        _state(world).enabled = True
    elif _state(world) is not None:
        on_pool_reset(world, reason="switched_off")
        _state(world).enabled = False


def _begin(world, sim=None):
    state = _state(world)
    if state._turn is None or state._turn.turn != world.turn:
        state._turn = SimpleNamespace(turn=int(world.turn), sim=sim, events=[], dropped=0, reserved=[], installed=False,
                                      withheld=[], dispatched={}, spent={}, delivered={}, planned=False)
    elif sim is not None:
        state._turn.sim = sim
    return state._turn


def _event(state, t, kind, order, **detail):
    if len(t.events) >= MAX_EVENTS:
        t.dropped += 1
    else:
        t.events.append({"kind": kind, "order": order.id, "holder": order.holder, "origin": order.origin,
                         "dest": order.dest, "region": order.path[order.cursor], **detail})


def _controller(world, rid):
    return next((i for i, civ in enumerate(world.civilizations) if civ.name == world.regions[rid].controller), -1)


def _escrows(state):
    return {o.id: o for o in state.orders + state.closed}


def check_order(order):
    if min(order.cargo_milli, order.delivered_milli, order.lost_milli, order.deposited_milli,
           order.cash, order.credited_milli, order.refunded_milli) < 0:
        raise RuntimeError("negative timber order balance")
    if order.cargo_open_milli != order.cargo_milli + order.delivered_milli + order.lost_milli + order.deposited_milli:
        raise RuntimeError("timber order cargo does not close")
    if order.escrowed_milli != order.cash + order.credited_milli + order.refunded_milli:
        raise RuntimeError("timber order escrow does not close")
    if order.status == "closed" and (order.cargo_milli or order.cash or order.outcome is None):
        raise RuntimeError("closed timber order still holds cargo or escrow")


def _refund(world, state, order, acc=None):
    if order.cash:
        amount = order.cash
        got = M.pay(world, M.Bill(purpose="timber_escrow", batch=BATCH + order.id * 4 + 2, phase="phase10",
                    payer=M.escrow(order.id), lines=((M.treasury(order.payer), amount),)),
                    turn=world.turn, book=state.book, escrows=_escrows(state), acc=acc)
        if not got.ok:
            raise RuntimeError(f"timber escrow refund refused: {got.reason}")
        order.refunded_milli += got.applied
        _bump(state, "refunded_milli", got.applied)


def _seizing_actor(world, order):
    from chronicler.war_requisition import war_requisition_active
    if not war_requisition_active(world):
        return None
    region = world.regions[order.path[order.cursor]]
    from chronicler.war.common import at_war
    origin_polity = world.civilizations[order.seller].name
    actors = sorted((a for a in world.war_state.armies if a.region == region.name and a.soldiers > 0
                     and at_war(world, a.civ, origin_polity)), key=lambda a: a.army_id)
    return actors[0].civ if actors else None


def _close(world, state, t, order, reason, sim=None, acc=None):
    if order.status == "closed":
        return
    if reason == "delivered":
        from chronicler.timber_supply import deliver_ordered_store
        quantity = order.cargo_milli
        amount = min(order.cash, quantity * order.sale_price_milli // MILLI)
        if amount:
            got = M.pay(world, M.Bill(purpose="timber_freight", batch=BATCH + order.id, phase="phase10",
                        payer=M.escrow(order.id), lines=((M.agent(order.holder), amount),), regions=(order.dest,)),
                        turn=world.turn, book=state.book, escrows=_escrows(state), sim=sim, acc=acc)
            if not got.ok:
                raise RuntimeError(f"timber freight payment refused: {got.reason}")
            order.credited_milli += got.applied
            _bump(state, "carrier_credited_milli", got.applied)
            _bump(state, "ceiling_refused_milli", got.residual)
        deliver_ordered_store(world, order.dest, quantity / MILLI)
        order.delivered_milli += quantity
        t.delivered[order.dest] = t.delivered.get(order.dest, 0) + quantity
        _bump(state, "delivered_milli", quantity)
    else:
        region = order.path[order.cursor]
        goods = world.regions[region].stockpile.goods
        goods["timber"] = goods.get("timber", 0.0) + order.cargo_milli / MILLI
        order.deposited_milli += order.cargo_milli
        if reason == "seized":
            from chronicler.war_requisition import note_cargo_seizure
            actor = _seizing_actor(world, order)
            if actor is None:
                raise RuntimeError("timber seizure has no actual seizing actor")
            value = order.purchase_milli * order.cargo_milli // order.cargo_open_milli
            note_cargo_seizure(world, owner=order.holder, region=region, actor=actor,
                              value_milli=value, shipment=order.id, goods="timber", quantity_milli=order.cargo_milli)
        _bump(state, "deposited_milli", order.cargo_milli)
    order.cargo_milli = 0
    _refund(world, state, order, acc)
    order.status, order.outcome, order.closed_turn = "closed", reason, int(world.turn)
    _bump(state, reason if reason in ("delivered", "pool_reset", "expired", "seized") else "cancelled")
    _event(state, t, reason, order, delivered_milli=order.delivered_milli, deposited_milli=order.deposited_milli,
           credited_milli=order.credited_milli, refunded_milli=order.refunded_milli)
    state.orders.remove(order)
    state.closed.append(order)
    # Preserve the physical terminal outcome and its cargo namespace. A local
    # commons deposit is not a return to the original owner or region.
    from chronicler.adaptive_livelihoods import note_trade
    note_trade(world, order.holder, order.dest, reason, None, order.id, package="timber_orders")
    del state.closed[:-MAX_CLOSED]
    check_order(order)


def reserve_first(world, agent_bridge, snapshot):
    state, sim = _state(world), TT._native(agent_bridge)
    t = _begin(world, sim)
    if t.reserved or t.installed:
        raise RuntimeError("timber order carriers already reserved")
    people, enlisted, trips = TT._people(snapshot), TT._enlisted(world), TT._trips(sim)
    for order in sorted(list(state.orders), key=lambda o: o.id):
        person = people.get(order.holder)
        reason = "holder_died" if person is None else "carrier_released" if person[0] != order.origin or person[1] != TT.MERCHANT or order.holder in enlisted or order.holder in trips else None
        if reason is None:
            try:
                sim.reserve_work(int(world.turn), TT.CATEGORY_TRADE, [(order.holder, 1.0)])
            except ValueError as error:
                if "already holds work" not in str(error):
                    raise
                reason = "carrier_released"
        if reason:
            _close(world, state, t, order, reason)
        else:
            t.reserved.append(order.id)


def finish_phase2(world, economy_result, agent_bridge, acc):
    state, t = _state(world), _begin(world, agent_bridge._sim)
    people = [(o.holder, 1.0) for o in state.orders if o.id in t.reserved]
    if people:
        t.sim.extend_paid_work(int(world.turn), people)
        t.installed = True
    return []


def after_agent_tick(world, agent_bridge):
    state, t = _state(world), _begin(world, agent_bridge._sim)
    if t.installed:
        from chronicler.livelihoods import paid_work_receipt
        receipt = paid_work_receipt(world, t.sim)
        if receipt is None:
            raise RuntimeError("timber order carrier income receipt missing")
        people = TT._people(t.sim.get_snapshot())
        for o in list(state.orders):
            if o.id not in t.reserved:
                continue
            row = receipt.get(o.holder)
            if row is None:
                if o.holder in people:
                    raise RuntimeError("timber order carrier missing from income receipt")
                _close(world, state, t, o, "holder_died")
                continue
            share, ordinary, deducted = row
            if abs(share - 1.0) > 1e-6:
                raise RuntimeError("timber order carrier income share is not whole")
            o.withheld += deducted
            _bump(state, "carrier_turns")
            _bump(state, "income_withheld_micro", round(deducted * 1_000_000))
            t.withheld.append({"order": o.id, "holder": o.holder, "ordinary": ordinary, "deducted": deducted})
    return []


def rollback_phase2(world):
    state = _state(world)
    if state is not None and state._turn is not None:
        if state._turn.installed and state._turn.sim is not None:
            state._turn.sim.cancel_paid_work()
        state._turn = None


def rollback_agent_tick(world, agent_bridge):
    rollback_phase2(world)


def _needs(world):
    """Current PL1 refusals, RS2 plus B3 work, net of this lane's real cargo.

    B3's want is already incremental after RS2. Combine the two per region
    before subtracting the same in-flight or newly arrived cargo once. The
    latter arrives after PL1 measured its gap, so that observation otherwise
    requests a duplicate shipment before the next turn sees its new store.
    """
    from chronicler import timber_supply as TS
    ts = TS._state(world)
    t = ts._turn if ts is not None else None
    rows = list(t.needs if t is not None and t.turn == world.turn else
                ts.needs if ts is not None and ts.frame_turn == world.turn else [])
    infrastructure = getattr(getattr(world, "livelihoods", None), "infrastructure_condition", None)
    if (infrastructure is not None and infrastructure.enabled
            and infrastructure.timber_needs_turn == world.turn):
        rows.extend(infrastructure.timber_needs)
    state = _state(world)
    gaps = {}
    for row in rows:
        if row.status == "refused" and row.reason in REFUSALS:
            key = (row.region, row.civ)
            gaps[key] = gaps.get(key, 0.0) + row.gap
    delivered = state._turn.delivered if state._turn is not None and state._turn.turn == world.turn else {}
    out = []
    for (region, civ), requested in sorted(gaps.items()):
        transit = math.fsum(o.cargo_milli * 0.99 ** (len(o.path) - 1 - o.cursor) / MILLI
                            for o in state.orders if o.dest == region)
        gap = max(0.0, requested - transit - delivered.get(region, 0) / MILLI)
        if gap >= 0.01:
            out.append((region, civ, gap))
    return out


def _price(world, state, region):
    ruler = _controller(world, region)
    candidates = [(turn, -rid, price) for rid, (turn, price) in state.prices.items()
                  if turn < world.turn and (rid == region or _controller(world, rid) == ruler)]
    own = state.prices.get(region)
    if own is not None and own[0] < world.turn:
        return own
    return (max(candidates)[0], max(candidates)[2]) if candidates else None


_UNREAD = object()

def dispatch(world, state, t, sim, origin, dest, holder, path, quantity, price, budget, acc=None, *, known_markets=_UNREAD,
             _planning_people=None):
    """Validated atomic dispatch: exact stock, merchant purchase and real escrow."""
    from chronicler import repair_projects as RP
    from chronicler import timber_supply as TS
    seller, payer = _controller(world, origin), _controller(world, dest)
    if seller < 0 or payer < 0 or seller == payer or quantity <= 0 or len(path) < 2 or path[0] != origin or path[-1] != dest or any(o.holder == holder for o in state.orders):
        return None
    # During this single planner call only wealth can change in the native
    # pool: earlier arrivals may credit a carrier and dispatch may debit one.
    # Physical eligibility (id, region, occupation, age) is invariant.  Most
    # candidates are refused by their own market knowledge, so do not rebuild
    # every living person's five columns for each such refusal.  The public
    # standalone path keeps its fresh eligibility read, and every accepted
    # planned candidate refreshes the full person/wallet below, before any
    # quantity, quote, stock or money calculation.  The cache contains no wallet.
    person = (TT._people(sim.get_snapshot()).get(holder) if _planning_people is None
              else _planning_people.get(holder))
    if person is None or person[0] != origin or person[1] != TT.MERCHANT or person[2] < TT.ADULT_AGE or holder in TT._enlisted(world) or holder in TT._trips(sim):
        return None
    if len(state.orders) >= MAX_ORDERS:
        _bump(state, "orders_capped")
        return None
    price_turn, price_milli = price
    if price_turn >= world.turn or price_milli <= 0:
        raise RuntimeError("timber orders refuse same-turn/future/invalid plan prices")
    from chronicler.adaptive_livelihoods import trade_destinations, accepts_trade_destination
    if known_markets is _UNREAD:
        known_markets = trade_destinations(world, sim, [holder])
    if not accepts_trade_destination(world, holder, dest, known_markets):
        return None
    if _planning_people is not None:
        person = TT._people(sim.get_snapshot()).get(holder)
        if person is None or person[0] != origin or person[1] != TT.MERCHANT or person[2] < TT.ADULT_AGE:
            return None
    commitments = RP._commitments(world, sim)
    works_wants = getattr(TS, "_works_wants", lambda _: [])
    local_works = math.fsum(want for region, want, _wids in works_wants(world) if region == origin)
    free = max(0.0, RP._free_timber(world, origin, commitments, 0.0) - TS.store_free(world, origin)
               - TS._wants(world).get(origin, 0.0) - local_works)
    quantity = min(quantity, math.floor(free * MILLI), TT._capacity(TT._graph(world)[0], path))
    sale_price = math.ceil(price_milli / (0.99 ** (len(path) - 1)) * (1 + FREIGHT * (len(path) - 1)))
    quantity = min(quantity, max(0, budget) * MILLI * MILLI // sale_price,
                   max(0, math.floor(person[3] * MILLI)) * MILLI // price_milli)
    cost = math.ceil(quantity * price_milli / MILLI)
    reserve = math.ceil(quantity * sale_price / MILLI / MILLI) * MILLI
    if quantity < 10 or cost <= 0 or reserve > budget * MILLI:
        return None
    order = TimberOrder(id=state.next_order, holder=holder, origin=origin, dest=dest, seller=seller, payer=payer,
                        path=list(path), dispatched_turn=world.turn, cargo_open_milli=quantity, cargo_milli=quantity,
                        purchase_milli=cost, sale_price_milli=sale_price, price_turn=price_turn, escrowed_milli=reserve)
    escrows = {**_escrows(state), order.id: order}
    purchase = M.Bill(purpose="timber_purchase", batch=BATCH + order.id, phase="phase10", payee=M.treasury(seller),
                      lines=((M.agent(holder), cost),), regions=(origin,))
    escrow = M.Bill(purpose="timber_escrow", batch=BATCH + order.id * 4, phase="phase10", payer=M.treasury(payer),
                    lines=((M.escrow(order.id), reserve),))
    if not M.quote(world, purchase, turn=world.turn, book=state.book, sim=sim).ok or not M.quote(world, escrow, turn=world.turn, book=state.book, escrows=escrows, acc=acc).ok:
        return None
    got = M.pay(world, escrow, turn=world.turn, book=state.book, escrows=escrows, acc=acc)
    if not got.ok:
        return None
    # No intervening native work after quote: a collection must now apply whole.
    got = M.pay(world, purchase, turn=world.turn, book=state.book, sim=sim, acc=acc)
    if not got.ok:
        raise RuntimeError("prevalidated timber purchase changed before dispatch")
    goods = world.regions[origin].stockpile.goods
    goods["timber"] -= quantity / MILLI
    state.orders.append(order)
    state.next_order += 1
    t.spent[payer] = t.spent.get(payer, 0) + reserve // MILLI
    t.dispatched[payer] = t.dispatched.get(payer, 0) + quantity
    for key, amount in (("dispatched", 1), ("bought_milli", quantity), ("purchase_milli", cost), ("escrowed_milli", reserve)):
        _bump(state, key, amount)
    _event(state, t, "dispatched", order, bought_milli=quantity, purchase_milli=cost, escrowed_milli=reserve)
    check_order(order)
    return order


def phase10_before_reserves(world, acc, economy_result, agent_bridge):
    """Run after PL1's before-reserves seam and before L9 settles this turn."""
    state, sim = _state(world), TT._native(agent_bridge)
    t = _begin(world, sim)
    if t.planned:
        raise RuntimeError("timber orders already planned this turn")
    t.planned = True
    edges, _closed = TT._graph(world)
    people, enlisted, trips = TT._people(sim.get_snapshot()), TT._enlisted(world), TT._trips(sim)
    for order in list(state.orders):
        person = people.get(order.holder)
        actor = _seizing_actor(world, order)
        reason = ("seized" if actor is not None else "holder_died" if person is None else "carrier_released" if person[0] != order.origin or person[1] != TT.MERCHANT or order.holder in enlisted or order.holder in trips else
                  "recipient_lost" if _controller(world, order.dest) != order.payer else
                  "expired" if world.turn - order.dispatched_turn > MAX_AGE else None)
        if reason:
            _close(world, state, t, order, reason, sim, acc)
            continue
        if order.dispatched_turn == world.turn or order.last_moved_turn == world.turn:
            continue
        a, b = order.path[order.cursor:order.cursor + 2]
        if (a, b) not in edges:
            _close(world, state, t, order, "route_lost", sim, acc)
            continue
        # Use the same graph and dated sea-raid risk as other merchant routes;
        # timber decay is the native 1% per journey hop declared by this slice.
        risk = max(0.0, edges[(a, b)][1])
        kept = math.floor(order.cargo_milli * 0.99 * (1 - min(1.0, risk)))
        loss = order.cargo_milli - kept
        order.cargo_milli, order.lost_milli = kept, order.lost_milli + loss
        _bump(state, "lost_milli", loss)
        order.cursor += 1
        order.last_moved_turn = world.turn
        if _seizing_actor(world, order) is not None:
            _close(world, state, t, order, "seized", sim, acc)
        elif order.cursor == len(order.path) - 1:
            _close(world, state, t, order, "delivered", sim, acc)
    from chronicler.local_budgets import envelope
    busy = {o.holder for o in state.orders} | enlisted | trips
    retail = TT._state(world)
    if retail is not None and retail.enabled:
        busy |= {s.holder for s in retail.shipments}
    if callable(getattr(sim, "work_reservations", None)):
        busy |= {int(r[0]) for r in sim.work_reservations(world.turn)}
    from chronicler.adaptive_livelihoods import trade_destinations
    known_markets = trade_destinations(world, sim, people)
    # These facts do not change while this synchronous planning loop runs.
    # Keep them local: a later turn, closure, controller or price change must
    # rebuild them.  Wallets, treasuries, stock, orders and bookings are never
    # memoized; dispatch and the payment seam still read their live values.
    planning_people = None
    paths_by_origin, prices_by_origin = {}, {}
    for dest, payer, gap in _needs(world):
        allowance = max(0, (envelope(world, payer, SERVICE, region=dest) or 0) - t.spent.get(payer, 0))
        if not allowance:
            continue
        candidates = []
        for holder, (origin, occ, age, _wealth) in people.items():
            if holder in busy or occ != TT.MERCHANT or age < TT.ADULT_AGE or origin == dest:
                continue
            if origin not in paths_by_origin:
                paths_by_origin[origin] = TT._bfs(edges, origin)
                prices_by_origin[origin] = _price(world, state, origin)
            path = paths_by_origin[origin].get(dest)
            price = prices_by_origin[origin]
            if path is not None and price is not None:
                candidates.append((len(path), origin, holder, path, price))
        for _hops, origin, holder, path, price in sorted(candidates):
            if planning_people is None:
                # No-demand/no-envelope phases need no extra population map.
                # The initial physical facts are still valid at first dispatch;
                # wallets and accepted-candidate eligibility remain live below.
                planning_people = {aid: person[:3] for aid, person in people.items()}
            order = dispatch(world, state, t, sim, origin, dest, holder, path, math.floor(gap * MILLI), price, allowance, acc,
                             known_markets=known_markets, _planning_people=planning_people)
            if order is not None:
                busy.add(holder)
                break
    return []


def phase10(world, acc, economy_result, agent_bridge):
    state, t = _state(world), _begin(world, getattr(agent_bridge, "_sim", None))
    prices = getattr(economy_result, "market_prices", None)
    if isinstance(prices, dict):
        for rid, region in enumerate(world.regions):
            value = prices.get(region.name, {}).get("raw_material")
            if value is not None and math.isfinite(float(value)) and float(value) > 0:
                state.prices[rid] = (int(world.turn), math.ceil(float(value) * MILLI))
    for order in state.orders + state.closed:
        check_order(order)
    M.check_book(state.book)
    state.frame_turn = int(world.turn)
    state.frame = {"turn": world.turn, "events": t.events, "events_dropped": t.dropped, "withheld": t.withheld,
                   "dispatched": dict(t.dispatched), "spent": dict(t.spent)}
    # Retain uncapped per-region arrivals through L9's observation of the
    # pre-arrival PL1 needs. _begin clears them next turn; checkpoint
    # serialization excludes all private turn state.
    return []


def on_pool_reset(world, reason="pool_reset"):
    state = _state(world)
    if state is None:
        return
    t = _begin(world)
    for order in list(state.orders):
        _close(world, state, t, order, reason)


def snapshot_summary(world):
    state = _state(world)
    source = world.turn - 1
    return {"schema_version": 1, "stage": "A4-3", "source_turn": source,
            "orders": [o.model_dump() for o in state.orders], "closed": [o.model_dump() for o in state.closed],
            "frame": state.frame if state.frame_turn == source else None, "counters": dict(state.counters),
            "parameters": {"freight": FREIGHT, "max_age": MAX_AGE, "max_orders": MAX_ORDERS, "max_events": MAX_EVENTS}}


def potential_repair_work(world, civ, gaps, obs):
    """Conservative patrician work stake; timber is never nutrition.

    Conservatively reserve granary input needs before valuing workshop
    repairs; B3 follows RS2, then irrigation before roads. The real planners
    still decide actual delivery and may use a different RS2 mix. Only current workshop idle work
    and outstanding road work can be valued. Inputs promise no future repair:
    labor, later budgets and actual delivery may still fail.
    """
    from chronicler import repair_projects as R, infrastructure_condition as I
    from chronicler.workshops import OPERATE_CONDITION
    turn = getattr(obs, "turn", None)
    if turn != world.turn:
        return {}
    repair = R._state(world)
    projects = repair.projects if repair is not None and R.repair_projects_active(world) else []
    workshops = getattr(world.livelihoods, "workshops", None)
    frame = ({r.site: r for r in workshops.frame} if workshops is not None
             and workshops.frame_turn == turn else {})
    sites = R._sites(world) if projects else {}
    infrastructure = I._state(world)
    works = I._asking_works(world, infrastructure)
    result = {}
    for region, gap in gaps:
        if _controller(world, region) != civ:
            continue
        available, relief = max(0.0, float(gap)), 0.0
        for project in sorted(projects, key=lambda p: (p.kind != "granary", p.pid)):
            if project.region != region:
                continue
            remaining = max(0.0, project.scope - project.delivered)
            condition = R._condition(world, project.kind, project.asset)
            if condition is None or remaining <= R.DONE:
                continue
            if project.kind == "granary":
                _per_condition, per_turn, rate, _coins = R._storage_rules()
                # No established granary-to-food benefit is inferred here.
                available = max(0.0, available - min(per_turn, remaining) * rate)
                continue
            site, receipt = sites.get(project.asset), frame.get(project.asset)
            if site is None:
                continue
            per_turn = R.MAX_CREW * R._diverted(world, site) * R.UNQUALIFIED_RATE
            amount = min(remaining, per_turn, available / R.WORKSHOP_TIMBER_PER_WORK)
            available = max(0.0, available - amount * R.WORKSHOP_TIMBER_PER_WORK)
            if receipt is not None and condition < OPERATE_CONDITION:
                idle = max(0.0, float(receipt.work_available) - float(receipt.allocated))
                service_gain = (amount / R.WORKSHOP_WORK_PER_CONDITION) / max(R.EPS, OPERATE_CONDITION - condition)
                relief += min(idle, remaining, amount, idle * min(1.0, service_gain))
        for work in works:                     # B3's fixed irrigation -> roads order
            if work.region != region:
                continue
            remaining = max(0.0, work.scope - work.delivered)
            rate = I.TIMBER_PER_WORK[work.kind]
            amount = min(I.WORK_PER_TURN, remaining, available / rate)
            available = max(0.0, available - amount * rate)
            if work.kind == "roads":
                relief += amount              # bounded outstanding road worker-turns
        if relief > 1e-9:
            result[region] = relief
    return result


from chronicler.local_budgets import Provider
class _TimberOrders(Provider):
    services = (SERVICE,)
    group = "repairs"
    def active(self, world):
        return timber_orders_active(world)
    def proposals(self, world, civ, obs):
        if not self.active(world):
            return []
        gaps = [(region, gap) for region, payer, gap in _needs(world) if payer == civ]
        work = potential_repair_work(world, civ, gaps, obs)
        gaps = [(region, gap) for region, gap in gaps if region in work]
        if not gaps:
            return []
        prices = [price for turn, price in _state(world).prices.values() if turn < world.turn]
        if not prices:
            return []
        expected = math.fsum(gap for _, gap in gaps)
        cost = max(1, math.ceil(expected * max(prices) * (1 + FREIGHT * TT.MAX_HOPS) / 0.99 ** TT.MAX_HOPS / MILLI))
        return [dict(service=SERVICE, recipients=[r for r, _ in gaps], claims=[f"timber_orders:{civ}"],
                     cost=cost, divisible=True, unit="timber dispatched", expected=expected,
                     relief={"patricians": math.fsum(work.values())},
                     detail={"gap": expected, "potential_repair_work": math.fsum(work.values()),
                             "relief_unit": "bounded workshop idle/road repair worker-turns",
                             "promise": "timber dispatch only; repair and service restoration unproved"})]
    def settle(self, world, commitment, obs):
        state = _state(world)
        t = state._turn if state is not None else None
        if t is None or t.turn != world.turn:
            return super().settle(world, commitment, obs)
        quantity = t.dispatched.get(commitment.civ, 0) / MILLI
        spent = t.spent.get(commitment.civ, 0)
        ratio = min(1.0, quantity / commitment.expected) if commitment.expected > 0 else 1.0
        return {"outcome": "kept" if ratio >= .8 else "deferred", "reason": None if ratio >= .8 else "no_supply",
                "spent": spent, "delivered": quantity, "ratio": ratio,
                "detail": {"escrowed": spent, "unit": "timber dispatched; physical delivery recorded separately"}}
BUDGET_PROVIDER = _TimberOrders()
