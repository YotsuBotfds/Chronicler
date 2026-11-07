"""A4 titled trade (``--titled-trade``, default off): merchants buy owned food.

Requires ``--agents hybrid`` and ``--household-retail`` in mode ``retail`` or
``no_relief`` with retail rules version 2 (``free_exchange`` moves no money and
``record_only`` holds no food). Design: the connected-world A4 audit (section
5) and the lead's decisions (plan section 5.7); integration page
``docs/integration/titled-trade.md``. Food only, between retail pilot regions
(slice A4-1). No random draws; every order is by region index, stable id or
shipment id. Parameters are declared modelling choices, not calibrated.

* **Title and custody (Python, per shipment by stable id).** A shipment
  (``titled_trade_state.Shipment``, a monotone never-reused id) holds its
  cargo in milli-food per retail good while it travels; the cargo is in no
  region's commons and no retail pool. Its holder (title) is the merchant who
  bought it; while reserved, that merchant is also its carrier.
* **Purchase (Phase 10, inside retail's frame).** In each pilot origin, each
  eligible merchant resident there (an adult living Merchant, not on a native
  trip, on no army roster, carrying nothing, with cash above a reserve of
  ``RESERVE_RATIONS`` rations at the home price) may buy owners' **surplus
  above their fair-share reserve** (``OWNER_KEEP``), pro rata to each owner's
  surplus (largest remainder, ties by id), at the origin's **local retail
  price** (retail's installed price per ration this turn), paying each owner
  ``ceil(milli x price / ration)`` directly through :mod:`chronicler.money`
  (one pairwise bill, purpose ``cargo_purchase``, keyed by the shipment id,
  validated whole before anything moves). The claims leave the origin pool
  (retail flow ``sold_merchant``) and title passes to the shipment. An owner
  sells at most what its wealth ceiling lets it be paid for. The quantity is
  the largest that still earns ``LOAD_MARGIN`` between the destination's
  price (after the cargo's transit decay) and the origin's, with each read
  as if the cargo (and every shipment already heading there or leaving this
  turn) had moved - the native merchant planner's rule - within the path's
  cargo capacity, the owners' surplus and the merchant's cash. Destinations
  are pilot regions with residents within ``MAX_HOPS`` on this turn's agent
  merchant graph (quarantine closures, sieges, wars and blockades remove
  edges); the one with the largest margin wins (ties to the lower region).
* **Transport.** One edge a turn, from the turn after dispatch, in Phase 10;
  a sea lane with a raid risk loses ``floor(v x risk)`` of each good (the
  expected native loss, deterministic). The carrier is reserved for every
  turn its shipment travels under the native work category ``trade`` (the
  native merchant planner skips it: nobody does both kinds of trip) and its
  whole ordinary income is withheld through the shared paid-work seam with an
  exact per-turn receipt (``extend_paid_work`` share 1.0): **margins replace
  the model merchant income, never stack on it**.
* **Arrival.** Transit decay once, ``floor(v x rate)`` per good (the native
  rates); the rest becomes the holder's retail claim at the destination
  (``consigned_in``), sold to households through the existing native
  settlement (paid by id; purpose ``food_purchase``) or to the destination's
  granaries; a claim the claims cap refuses goes to the destination's commons.
* **One declared outcome per event** (``OUTCOMES``): a conquest of the
  destination (its controller changed since dispatch), a quarantine closure
  of any edge of the remaining route, the route lost (no path within
  ``MAX_HOPS``) or the destination leaving the pilot return the shipment to
  its origin at full value as the holder's claim there (``returned_in``; the
  native unwind's rule); the holder's death escheats the cargo to the commons
  of the region it stands in (recorded); a rebuilt native pool or
  ``--no-titled-trade`` ends it with its cargo in the commons where it
  stands. A carrier who migrates, changes occupation, enlists, goes on a
  native trip or holds other work is released (no reservation, no withheld
  income) and the holder keeps title; the shipment continues. War does not
  reach cargo in transit in this slice (counted, ``war_exempt_turns``). No
  tolls or fees.

Declared limits (A4-1): carriers stay home in the native pool (PL1's
boundary: no packets, contact or food demand travel with them); prices within
``MAX_HOPS`` are known at once (omniscient, as the native bootstrap); trips to
or from non-pilot regions stay legacy native commons trips with model income;
the shipment's hops carry no epidemic contact; holders' sales are attributed
by stable id from retail's settlement (exact unless a claim mixes delivered
cargo with other food, or a seller hit the wealth ceiling).
"""
from __future__ import annotations

import math
from fractions import Fraction

from chronicler import money
from chronicler.titled_trade_state import (
    COUNTERS, DEPOSIT_REASONS, MAX_CLOSED, MAX_FRAME_SELLERS, MAX_HISTORY, MAX_LOG, MAX_LOTS, MAX_SHIPMENTS,
    OUTCOMES, RELEASE_REASONS, RETURN_CAUSES, Lot, Shipment, TitledTradeState, TradeRecord,
)

MILLI = 1000
#: Milli-food every owner keeps (its fair-share reserve: one turn's two rations).
OWNER_KEEP = 1000
#: Rations at the home price a carrier keeps in cash.
RESERVE_RATIONS = 6
#: Price gap each unit must earn, price units (native ``merchant::LOAD_MARGIN``).
LOAD_MARGIN = 0.25
#: The smallest cargo worth a trip, milli-food (native ``MIN_CARGO``).
MIN_CARGO = 10
#: The longest route a shipment plans, in hops.
MAX_HOPS = 3
#: Cargo per trip by the narrowest leg, milli-food (native land, river, sea caps).
LAND_CAP, RIVER_CAP, SEA_CAP = 2000, 5000, 10000
#: Transit decay per retail good (native ``economy::TRANSIT_DECAY``: grain,
#: fish, salt, botanicals, exotic).
TRANSIT_DECAY: tuple[float, ...] = (0.05, 0.08, 0.0, 0.04, 0.06)
#: Native codes: ``Occupation::Merchant``, ``AGE_ADULT``, the work category.
MERCHANT = 2
ADULT_AGE = 20
CATEGORY_TRADE = 4
#: Native ``agent::MAX_WEALTH`` (the wealth ceiling, wealth units).
MAX_WEALTH = 100.0
SHARE = 1.0
_NATIVE = ("reserve_work", "extend_paid_work", "cancel_paid_work", "take_paid_work_receipt", "settle_pairs",
           "trip_agent_ids", "work_reservation_categories", "wealth_transfer_purposes", "get_snapshot")


class _Turn:
    """One turn in flight (never checkpointed)."""

    def __init__(self, turn: int, sim=None):
        self.turn = turn
        self.sim = sim
        self.reserved: list[int] = []          # shipment ids whose carrier is reserved
        self.installed = False
        self.receipt = None
        self.events: list[dict] = []
        self.withheld: list[dict] = []
        self.sales: list[dict] = []
        self.dispatched: list[dict] = []
        self.plans: dict[str, int] = {}
        self.closed_carriers: set[int] = set()


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

def _state(world) -> TitledTradeState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "titled_trade", None) if container is not None else None


def _bump(state: TitledTradeState, key: str, amount: int = 1) -> None:
    if key not in COUNTERS:
        raise KeyError(f"undeclared titled trade counter {key!r}")
    state.counters[key] = state.counters.get(key, 0) + int(amount)


def _log(state: TitledTradeState, turn: int, kind: str, shipment: int | None = None, **detail) -> None:
    state.log.append(TradeRecord(turn=int(turn), kind=kind, shipment=shipment, detail=detail))
    if len(state.log) > MAX_LOG:
        state.log_dropped += len(state.log) - MAX_LOG
        del state.log[:-MAX_LOG]


def _note(ship: Shipment, turn: int, event: str, region: int) -> None:
    ship.history.append([int(turn), event, int(region)])
    del ship.history[:-MAX_HISTORY]


def set_titled_trade_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    turn = int(getattr(world, "turn", 0))
    state = _state(world)
    if state is None:
        world.livelihoods.titled_trade = state = TitledTradeState(enabled=bool(value))
        if value:
            _log(state, turn, "switched_on")
        return
    if state._turn is not None:
        raise RuntimeError("cannot change titled trade while a turn is pending")
    if bool(value) != state.enabled:
        if not value:
            # Every live shipment ends with its cargo in the commons where it
            # stands, dated (configuration time: no retail turn is open).
            for ship in list(state.shipments):
                _deposit(world, state, ship, ship.region(), "switched_off")
                _close(world, state, ship, turn, "switched_off", None)
            state.lots = []
        state.enabled = bool(value)
        _log(state, turn, "switched_on" if value else "switched_off")


def titled_trade_active(world) -> bool:
    """Enabled in a hybrid run with household retail active."""
    state = _state(world)
    if state is None or not state.enabled or getattr(world, "agent_mode", None) != "hybrid":
        return False
    from chronicler.household_retail import household_retail_active
    return household_retail_active(world)


def _retail(world):
    """Retail's state, refused when its mode or rules cannot carry title."""
    retail = world.livelihoods.household_retail
    if retail.mode not in ("retail", "no_relief") or retail.rules_version < 2:
        raise RuntimeError("titled trade requires household retail in mode retail or no_relief with rules "
                           "version 2")
    return retail


def _native(agent_bridge):
    sim = getattr(agent_bridge, "_sim", None)
    if sim is None or not all(callable(getattr(sim, name, None)) for name in _NATIVE):
        raise RuntimeError("titled trade requires a fresh native build with settle_pairs and the trade work "
                           "category")
    cats = list(sim.work_reservation_categories())
    if CATEGORY_TRADE >= len(cats) or cats[CATEGORY_TRADE] != "trade":
        raise RuntimeError("titled trade requires a native build whose work category 4 is trade")
    return sim


def _begin(world, state: TitledTradeState, sim=None) -> _Turn:
    t = state._turn
    if t is not None and t.turn == world.turn:
        return t
    t = state._turn = _Turn(int(world.turn), sim)
    return t


# ---------------------------------------------------------------------------
# People and the graph
# ---------------------------------------------------------------------------

def _people(snapshot) -> dict[int, tuple[int, int, int, float]]:
    """``{id: (region, occupation, age, wealth)}`` of the living agents."""
    cols = [snapshot.column(name).to_pylist() for name in ("id", "region", "occupation", "age", "wealth")]
    return {int(i): (int(r), int(o), int(a), float(w)) for i, r, o, a, w in zip(*cols)}


def _enlisted(world) -> set[int]:
    armies = getattr(getattr(world, "war_state", None), "armies", None) or []
    return {int(aid) for army in armies for aid, _ in army.roster}


def _trips(sim) -> set[int]:
    return {int(a) for a in sim.trip_agent_ids()}


def _graph(world) -> tuple[dict[tuple[int, int], tuple[bool, float]], set[tuple[int, int]]]:
    """This turn's agent merchant graph as the native tick receives it
    (diplomacy, maritime blockades and raid risk, cities cut off) as
    ``{(from, to): (is_river, sea risk or -1)}``, with the quarantine-closed
    edges removed and returned apart (read without touching the quarantine
    receipt). Relief convoys build their own graph; shipments do not."""
    from chronicler.agent_bridge import _city_route_graph
    from chronicler.economy import build_merchant_route_graph
    batch = build_merchant_route_graph(world)
    if getattr(world, "maritime", None) is not None:
        from chronicler.maritime import merchant_route_graph
        batch = merchant_route_graph(world, batch)
    batch = _city_route_graph(world, batch)
    names = set(batch.schema.names)
    src = batch.column("from_region").to_pylist()
    dst = batch.column("to_region").to_pylist()
    river = batch.column("is_river").to_pylist()
    risk = batch.column("sea_raid_risk").to_pylist() if "sea_raid_risk" in names else [-1.0] * len(src)
    from chronicler.quarantine_rules import closed_pairs
    pairs = closed_pairs(world)
    regions = world.regions
    edges, closed = {}, set()
    for a, b, r, k in zip(src, dst, river, risk):
        a, b = int(a), int(b)
        ca, cb = regions[a].controller, regions[b].controller
        if pairs and ca is not None and cb is not None and ca != cb and ((ca, cb) if ca < cb else (cb, ca)) in pairs:
            closed.add((a, b))
            continue
        edges[(a, b)] = (bool(r), float(k) if k is not None else -1.0)
    return edges, closed


def _bfs(edges, start: int, limit: int = MAX_HOPS) -> dict[int, list[int]]:
    """Shortest paths from ``start`` within ``limit`` hops (neighbours in
    ascending order, so ties go to the lower region)."""
    adj: dict[int, list[int]] = {}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
    for v in adj.values():
        v.sort()
    paths = {start: [start]}
    frontier = [start]
    for _ in range(limit):
        nxt = []
        for a in frontier:
            for b in adj.get(a, ()):
                if b not in paths:
                    paths[b] = paths[a] + [b]
                    nxt.append(b)
        frontier = nxt
    return paths


def _capacity(edges, path: list[int]) -> int:
    cap = SEA_CAP
    for a, b in zip(path, path[1:]):
        river, risk = edges[(a, b)]
        cap = min(cap, SEA_CAP if risk >= 0.0 else RIVER_CAP if river else LAND_CAP)
    return cap


# ---------------------------------------------------------------------------
# Phase 2: carriers
# ---------------------------------------------------------------------------

def _release(state, t: _Turn, ship: Shipment, reason: str) -> None:
    if reason not in RELEASE_REASONS:
        raise KeyError(reason)
    ship.carrier, ship.released = None, reason
    _note(ship, t.turn, f"released_{reason}", ship.region())
    _bump(state, "carriers_released")
    _log(state, t.turn, "carrier_released", ship.id, holder=ship.holder, reason=reason)
    t.events.append({"shipment": ship.id, "event": "carrier_released", "reason": reason, "region": ship.region()})


def reserve_first(world, agent_bridge, snapshot) -> None:
    """Livelihoods seam, before every package plans this turn's work: re-check
    and reserve each live shipment's carrier under ``trade`` (its whole turn),
    so no other planner, and not the native merchant planner, gives it work.
    A holder dead since the last tick escheats its cargo where it stands."""
    state = _state(world)
    _retail(world)
    sim = _native(agent_bridge)
    t = _begin(world, state, sim)
    if t.reserved or t.installed:
        raise RuntimeError("titled trade carriers already reserved for this turn")
    t.sim = sim
    if not state.shipments:
        return
    people = _people(snapshot)
    enlisted = _enlisted(world)
    trips = _trips(sim)
    for ship in sorted(state.shipments, key=lambda s: s.id):
        if ship.holder not in people:
            _escheat(world, state, t, ship)
            continue
        aid = ship.carrier
        if aid is None:
            continue
        region, occupation, _age, _w = people[aid]
        reason = ("migrated" if region != ship.origin else "occupation" if occupation != MERCHANT
                  else "enlisted" if aid in enlisted else "on_trip" if aid in trips else None)
        if reason is None:
            try:
                sim.reserve_work(int(world.turn), CATEGORY_TRADE, [(aid, SHARE)])
            except ValueError as error:
                if "already holds work" not in str(error):
                    raise
                reason = "other_work"
        if reason is not None:
            _release(state, t, ship, reason)
            continue
        t.reserved.append(ship.id)


def finish_phase2(world, economy_result, agent_bridge, acc):
    """After the native economy tick: arm the reserved carriers' paid share
    (their whole ordinary income is withheld by the next wealth phase)."""
    state = _state(world)
    t = state._turn
    if t is None or t.turn != world.turn:
        if state.shipments:
            raise RuntimeError("titled trade carriers were not reserved this turn")
        return []
    carriers = sorted(state.shipment(sid).carrier for sid in t.reserved)
    if carriers:
        t.sim.extend_paid_work(int(world.turn), [(aid, SHARE) for aid in carriers])
        t.installed = True
    return []


def rollback_phase2(world) -> None:
    """A failed Phase 2: disarm the shared paid share; nothing moved."""
    state = _state(world)
    t = state._turn if state is not None else None
    if t is None or t.turn != getattr(world, "turn", None):
        return
    if t.installed and t.sim is not None:
        t.sim.cancel_paid_work()
    state._turn = None


def rollback_agent_tick(world, agent_bridge) -> None:
    """The agent tick raised: disarm an unconsumed paid share."""
    state = _state(world)
    t = state._turn if state is not None else None
    if t is not None and t.turn == world.turn and t.installed and t.receipt is None and t.sim is not None:
        t.sim.cancel_paid_work()
        t.installed = False


# ---------------------------------------------------------------------------
# After the tick: withheld income, holders' deaths
# ---------------------------------------------------------------------------

def after_agent_tick(world, agent_bridge):
    """Take the carriers' paid-work rows (an exact per-turn receipt of the
    model income withheld) and escheat the cargo of holders who died."""
    state = _state(world)
    turn = int(world.turn)
    if state.last_settled_turn is not None and turn <= state.last_settled_turn:
        raise RuntimeError("titled trade already settled for this turn")
    t = state._turn
    if t is None or t.turn != turn:
        if state.shipments:
            raise RuntimeError("titled trade turn missing at the agent tick")
        t = _begin(world, state, getattr(agent_bridge, "_sim", None))
    sim = agent_bridge._sim
    receipt = None
    if t.installed:
        from chronicler.livelihoods import paid_work_receipt
        receipt = paid_work_receipt(world, sim)
        if receipt is None:
            raise RuntimeError("paid work receipt missing for this turn")
        t.receipt = receipt
    people = _people(sim.get_snapshot()) if state.shipments else {}
    trips = _trips(sim) if t.reserved else set()
    for sid in t.reserved:
        ship = state.shipment(sid)
        aid = ship.carrier
        if aid in trips:
            raise RuntimeError(f"titled trade carrier {aid} was planned on a native merchant trip")
        row = receipt.get(aid) if receipt is not None else None
        if row is None:
            if aid in people:
                raise RuntimeError(f"titled trade carrier {aid} has no paid-work receipt row")
            continue                                   # died before the wealth phase
        share, ordinary, deducted = row
        if abs(share - SHARE) > 1e-6:
            raise RuntimeError(f"titled trade carrier {aid} withheld share {share}, not {SHARE}")
        ship.withheld = round(ship.withheld + deducted, 9)
        ship.withheld_turns += 1
        _bump(state, "carrier_turns")
        _bump(state, "receipt_rows")
        _bump(state, "income_withheld_micro", round(deducted * 1_000_000))
        t.withheld.append({"shipment": sid, "carrier": aid, "share": share, "ordinary": ordinary,
                           "deducted": deducted})
    for ship in sorted(list(state.shipments), key=lambda s: s.id):
        if ship.holder not in people:
            _escheat(world, state, t, ship)
    state.last_settled_turn = turn
    return []


# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------

def _deposit(world, state, ship: Shipment, rid: int, reason: str, cargo: list[int] | None = None) -> int:
    """Cargo into region ``rid``'s commons (title lost), dated by the caller."""
    if reason not in DEPOSIT_REASONS:
        raise KeyError(reason)
    from chronicler.household_retail_state import RETAIL_GOODS
    cargo = list(ship.cargo) if cargo is None else cargo
    goods = world.regions[rid].stockpile.goods
    for g, v in enumerate(cargo):
        if v:
            goods[RETAIL_GOODS[g]] = goods.get(RETAIL_GOODS[g], 0.0) + v / MILLI
    total = sum(cargo)
    ship.deposited += total
    ship.deposit_reason = reason
    ship.cargo = [0] * len(ship.cargo)
    _bump(state, "deposited_milli", total)
    return total


def _close(world, state, ship: Shipment, turn: int, outcome: str, cause: str | None, t: _Turn | None = None) -> None:
    if outcome not in OUTCOMES or ship.status != "moving" or ship.outcome is not None:
        raise RuntimeError(f"shipment {ship.id} already closed or unknown outcome {outcome!r}")
    if any(ship.cargo):
        raise RuntimeError(f"shipment {ship.id} closes with cargo aboard")
    lost = sum(ship.losses.values())
    if sum(ship.cargo_open) != lost + ship.delivered + ship.returned + ship.deposited:
        raise RuntimeError(f"shipment {ship.id}: cargo does not close")
    ship.status, ship.outcome, ship.cause = "closed", outcome, cause
    ship.closed_turn, ship.closed_region = int(turn), ship.region()
    _note(ship, turn, outcome, ship.region())
    state.shipments = [s for s in state.shipments if s is not ship]
    state.closed.append(ship)
    del state.closed[:-MAX_CLOSED]
    _bump(state, outcome)
    if cause is not None:
        _bump(state, f"{outcome}_{cause}")
    _log(state, turn, "closed", ship.id, outcome=outcome, cause=cause, region=ship.region(),
         delivered=ship.delivered, returned=ship.returned, deposited=ship.deposited)
    if t is not None:
        if ship.carrier is not None:
            t.closed_carriers.add(ship.carrier)
        t.events.append({"shipment": ship.id, "event": outcome, "cause": cause, "region": ship.region(),
                         "delivered": ship.delivered, "returned": ship.returned, "deposited": ship.deposited,
                         "losses": dict(ship.losses)})


def _escheat(world, state, t: _Turn, ship: Shipment) -> None:
    """The holder died: the cargo goes to the commons of the region it stands in."""
    _deposit(world, state, ship, ship.region(), "holder_died")
    _close(world, state, ship, t.turn, "escheated", None, t)


def _return(world, state, t: _Turn, ship: Shipment, cause: str) -> None:
    """Back to the origin at full value (no decay): the holder's claim there,
    else the origin's commons."""
    if cause not in RETURN_CAUSES:
        raise KeyError(cause)
    from chronicler.household_retail import consign, pilot_entry
    cargo = list(ship.cargo)
    total = sum(cargo)
    ship.cursor = 0                                     # unwound to the origin
    if total and consign(world, ship.origin, ship.holder, cargo, "returned_in"):
        ship.returned += total
        ship.cargo = [0] * len(cargo)
        _bump(state, "returned_milli", total)
    elif total:
        reason = "not_pilot" if pilot_entry(world, ship.origin) is None else "claims_refused"
        _deposit(world, state, ship, ship.origin, reason)
    _close(world, state, ship, t.turn, "returned", cause, t)


def _arrive(world, state, t: _Turn, ship: Shipment) -> None:
    from chronicler.household_retail import consign, pilot_entry
    decay = [math.floor(v * rate) for v, rate in zip(ship.cargo, TRANSIT_DECAY)]
    if sum(decay):
        ship.losses["transit_decay"] = ship.losses.get("transit_decay", 0) + sum(decay)
        _bump(state, "transit_decay_milli", sum(decay))
    rest = [v - d for v, d in zip(ship.cargo, decay)]
    ship.cargo = rest
    total = sum(rest)
    if total and consign(world, ship.dest, ship.holder, rest, "consigned_in"):
        ship.delivered += total
        ship.cargo = [0] * len(rest)
        _bump(state, "consigned_milli", total)
        _add_lot(state, ship.holder, ship.dest, total, ship.id)
    elif total:
        reason = "not_pilot" if pilot_entry(world, ship.dest) is None else "claims_refused"
        _deposit(world, state, ship, ship.dest, reason)
    _close(world, state, ship, t.turn, "delivered", None, t)


def _add_lot(state, holder: int, region: int, milli: int, sid: int) -> None:
    lot = next((x for x in state.lots if x.holder == holder and x.region == region), None)
    if lot is None:
        lot = Lot(holder=holder, region=region, milli=0)
        state.lots.append(lot)
        state.lots.sort(key=lambda x: (x.region, x.holder))
        del state.lots[MAX_LOTS:]
    lot.milli += milli
    lot.shipments = sorted(set(lot.shipments) | {sid})[-MAX_HISTORY:]


# ---------------------------------------------------------------------------
# Phase 10 (inside retail's frame): sales, movement, purchases
# ---------------------------------------------------------------------------

def _war_pressed(world, rid: int) -> bool:
    region = world.regions[rid]
    if region.occupied_by is not None and region.occupied_by != region.controller:
        return True
    if getattr(region, "last_conquered_turn", None) == world.turn:
        return True
    armies = getattr(getattr(world, "war_state", None), "armies", [])
    return any(a.phase == "sieging" and a.region == region.name and a.civ != region.controller for a in armies)


def _move(world, state, t: _Turn, ship: Shipment, edges, closed) -> None:
    from chronicler.household_retail import pilot_entry
    turn = t.turn
    if ship.last_moved_turn is not None and ship.last_moved_turn >= turn:
        raise RuntimeError(f"shipment {ship.id} moved twice in one turn")
    if world.regions[ship.dest].controller != ship.controllers[1]:
        _return(world, state, t, ship, "destination_conquered")
        return
    if pilot_entry(world, ship.dest) is None:
        _return(world, state, t, ship, "destination_left_pilot")
        return
    ahead = list(zip(ship.path[ship.cursor:], ship.path[ship.cursor + 1:]))
    if any(edge in closed for edge in ahead):
        _return(world, state, t, ship, "quarantine_closure")
        return
    if any(edge not in edges for edge in ahead):
        path = _bfs(edges, ship.region()).get(ship.dest)
        if path is None:
            _return(world, state, t, ship, "route_lost")
            return
        ship.path = ship.path[:ship.cursor] + path
        _bump(state, "replanned")
        _note(ship, turn, "replanned", ship.region())
    a, b = ship.path[ship.cursor], ship.path[ship.cursor + 1]
    _river, risk = edges[(a, b)]
    if risk > 0.0:
        lost = [math.floor(v * risk) for v in ship.cargo]
        if sum(lost):
            ship.cargo = [v - x for v, x in zip(ship.cargo, lost)]
            ship.losses["sea_loss"] = ship.losses.get("sea_loss", 0) + sum(lost)
            _bump(state, "sea_loss_milli", sum(lost))
    ship.cursor += 1
    ship.last_moved_turn = turn
    _bump(state, "hops")
    _note(ship, turn, "moved", b)
    t.events.append({"shipment": ship.id, "event": "moved", "region": b})
    if _war_pressed(world, b):
        ship.war_exempt_turns += 1
        _bump(state, "war_exempt_turns")
    if ship.cursor == len(ship.path) - 1:
        _arrive(world, state, t, ship)


def _attribute_sales(world, state, t: _Turn) -> None:
    """Holders' sales of delivered cargo this turn, from retail's settlement:
    sold milli-food from the claim rows (drawn from the delivered lot first)
    and the money the native credited them, reproduced exactly from the
    region's payments split over its sellers by sold food (largest remainder,
    ties by id) when no seller there hit the wealth ceiling; then each lot is
    clamped to what the claim still holds (decay, war, procurement, death)."""
    from chronicler.household_retail import largest_remainder, pilot_entry, turn_settlement
    money_rows, claim_sold, region_money, procurement = turn_settlement(world)
    holders = {lot.holder for lot in state.lots}
    for lot in list(state.lots):
        reg = pilot_entry(world, lot.region)
        sold = (claim_sold or {}).get((lot.holder, lot.region), 0)
        cargo_sold = min(sold, lot.milli)
        if cargo_sold:
            paid, _credited, refunded = (region_money or {}).get(lot.region, (0, 0, 0))
            sellers = {o: v for (o, r), v in (claim_sold or {}).items() if r == lot.region and v > 0}
            share = largest_remainder(paid, sellers.items()).get(lot.holder, 0)
            exact = refunded == 0 and cargo_sold == sold
            credit = share if cargo_sold == sold else (share * cargo_sold) // sold
            if refunded:
                # A seller in the region hit the ceiling: the holder's own row
                # bounds what it received.
                credit = min(credit, (money_rows or {}).get(lot.holder, (0, 0, 0))[1])
            _bump(state, "cargo_sold_milli", cargo_sold)
            _bump(state, "cargo_sales_credited_milli", credit)
            if not exact:
                _bump(state, "cargo_sales_inexact_milli", credit)
            t.sales.append({"holder": lot.holder, "region": lot.region, "sold": sold, "cargo_sold": cargo_sold,
                            "credited": credit, "exact": exact})
            lot.milli -= cargo_sold
        claim = reg.claims.get(lot.holder, 0) if reg is not None else 0
        lot.milli = min(lot.milli, claim)
        if lot.milli <= 0:
            state.lots.remove(lot)
    for aid, credit in sorted((procurement or {}).items()):
        if aid in holders:
            _bump(state, "holder_procurement_credited_milli", credit)


def _dbar(goods: list[int]) -> float:
    total = sum(goods)
    return sum(v * rate for v, rate in zip(goods, TRANSIT_DECAY)) / total if total else 0.0


def _price(market: tuple[float, float], delta: float) -> float:
    """Retail's price band over the economy's food price read as if ``delta``
    food units had arrived (negative: left): ``demand / (supply + delta)``."""
    from chronicler.household_retail import PRICE_CAP, PRICE_FLOOR
    demand, supply = market
    return min(PRICE_CAP, max(PRICE_FLOOR, demand / max(supply + delta, 0.1)))


def _plan_quantity(origin, dest, dbar: float, q_max: int) -> int:
    """The largest milli-food quantity whose last unit still earns
    ``LOAD_MARGIN`` (0 when even ``MIN_CARGO`` does not)."""
    def gap(q):
        return _price(dest, q / MILLI) * (1.0 - dbar) - _price(origin, -q / MILLI)
    if q_max < MIN_CARGO or gap(MIN_CARGO) < LOAD_MARGIN:
        return 0
    if gap(q_max) >= LOAD_MARGIN:
        return q_max
    lo, hi = MIN_CARGO, q_max
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if gap(mid) >= LOAD_MARGIN:
            lo = mid
        else:
            hi = mid
    return lo


def _market(economy_result, world, rid: int, tally: dict[int, float]) -> tuple[float, float]:
    name = world.regions[rid].name
    demand = float((getattr(economy_result, "market_demand", {}) or {}).get(name, (0.0,))[0])
    supply = float((getattr(economy_result, "market_supply", {}) or {}).get(name, (0.0,))[0])
    return demand, supply + tally.get(rid, 0.0)


def _dispatch(world, state, t: _Turn, sim, edges, economy_result, acc) -> None:
    from chronicler.household_retail import _ration, pilot_entry, price_milli
    retail = _retail(world)
    turn = t.turn
    if len(state.shipments) >= MAX_SHIPMENTS:
        _bump(state, "shipments_capped")
        return
    people = _people(sim.get_snapshot())
    trips = _trips(sim)
    enlisted = _enlisted(world)
    busy = {s.holder for s in state.shipments} | t.closed_carriers
    residents: dict[int, int] = {}
    for region, _o, _a, _w in people.values():
        residents[region] = residents.get(region, 0) + 1
    pilots = sorted(reg.region for reg in retail.regions)
    pilot_set = set(pilots)
    ration_milli = Fraction(_ration(world)) * MILLI
    tally = {}
    for ship in state.shipments:                        # cargo already on the road counts against its market
        tally[ship.dest] = tally.get(ship.dest, 0.0) + ship.total() / MILLI
    for o in pilots:
        reg = pilot_entry(world, o)
        if reg is None or not reg.claims:
            continue
        carriers = sorted(aid for aid, (region, occ, age, _w) in people.items()
                          if region == o and occ == MERCHANT and age >= ADULT_AGE
                          and aid not in trips and aid not in enlisted and aid not in busy)
        if not carriers:
            continue
        price_o = price_milli(world, economy_result, o)
        reachable = _bfs(edges, o)
        for aid in carriers:
            if len(state.shipments) >= MAX_SHIPMENTS:
                _bump(state, "shipments_capped")
                return
            offer = {}
            for owner, claim in reg.claims.items():
                if owner == aid or owner not in people or claim <= OWNER_KEEP:
                    continue
                room = max(0, math.floor((MAX_WEALTH - people[owner][3]) * MILLI))
                most = int(room * ration_milli // price_o)    # what its ceiling lets it be paid for
                surplus = min(claim - OWNER_KEEP, most)
                if surplus > 0:
                    offer[owner] = surplus
            if sum(offer.values()) < MIN_CARGO:
                _bump(state, "plans_no_offer")
                t.plans["no_offer"] = t.plans.get("no_offer", 0) + 1
                break
            cash = math.floor(people[aid][3] * MILLI) - RESERVE_RATIONS * price_o - len(offer)
            q_cash = int(max(0, cash) * ration_milli // price_o)
            if q_cash < MIN_CARGO:
                _bump(state, "plans_no_cash")
                t.plans["no_cash"] = t.plans.get("no_cash", 0) + 1
                continue
            dbar = _dbar(reg.goods)
            origin_market = _market(economy_result, world, o, {o: tally.get(o, 0.0)})
            best = None
            for d, path in sorted(reachable.items()):
                if d == o or d not in pilot_set or residents.get(d, 0) <= 0 or pilot_entry(world, d) is None:
                    continue
                q_max = min(_capacity(edges, path), sum(offer.values()), q_cash)
                dest_market = _market(economy_result, world, d, tally)
                q = _plan_quantity(origin_market, dest_market, dbar, q_max)
                if q <= 0:
                    continue
                x = q / MILLI
                margin = x * ((_price(dest_market, 0.0) + _price(dest_market, x)) / 2 * (1.0 - dbar)
                              - (_price(origin_market, 0.0) + _price(origin_market, -x)) / 2)
                if best is None or margin > best[0] + 1e-12:
                    best = (margin, d, path, q)
            if best is None:
                key = "no_margin" if len(reachable) > 1 else "no_destination"
                _bump(state, f"plans_{key}")
                t.plans[key] = t.plans.get(key, 0) + 1
                continue
            _margin, d, path, q = best
            _buy(world, state, t, sim, acc, aid, o, d, path, q, offer, price_o, ration_milli, people)
            tally[d] = tally.get(d, 0.0) + q / MILLI
            tally[o] = tally.get(o, 0.0) - q / MILLI
            busy.add(aid)


def _buy(world, state, t: _Turn, sim, acc, aid, o, d, path, q, offer, price_o, ration_milli, people) -> None:
    from chronicler.household_retail import largest_remainder, sell_to_merchant
    turn = t.turn
    takes = largest_remainder(q, offer.items())
    lines = tuple((money.agent(owner), math.ceil(Fraction(take * price_o) / ration_milli))
                  for owner, take in sorted(takes.items()))
    sid = state.next_shipment
    bill = money.Bill(purpose="cargo_purchase", batch=sid, phase="phase10", payer=money.agent(aid), lines=lines,
                      regions=tuple(people[int(a.ident)][0] for a, _ in lines), payer_region=o)
    quote = money.quote(world, bill, turn=turn, book=state.book, acc=acc, sim=sim)
    if not quote.ok:
        raise RuntimeError(f"titled trade purchase refused before anything moved: {quote.reason}")
    per_good = sell_to_merchant(world, o, takes)            # title passes to the shipment
    got = money.pay(world, bill, turn=turn, book=state.book, acc=acc, sim=sim)
    if not got.ok:
        raise RuntimeError(f"titled trade purchase refused after validation: {got.reason}")
    regions = world.regions
    ship = Shipment(id=sid, holder=aid, carrier=aid, origin=o, dest=d, path=list(path), cursor=0,
                    controllers=[regions[o].controller, regions[d].controller], dispatched_turn=turn,
                    cargo=list(per_good), cargo_open=list(per_good), cost_milli=got.applied, price_milli=price_o,
                    sellers=len(takes))
    _note(ship, turn, "dispatched", o)
    state.next_shipment += 1
    state.shipments.append(ship)
    _bump(state, "dispatched")
    _bump(state, "bought_milli", q)
    _bump(state, "paid_milli", got.applied)
    _bump(state, "sellers_paid", len(takes))
    _bump(state, "seller_ceiling_refunded_milli", got.residual)
    _log(state, turn, "dispatched", sid, holder=aid, origin=o, dest=d, milli=q, paid=got.applied,
         price_milli=price_o, sellers=len(takes))
    for f in got.flows:                                # later plans this phase see the new balances
        payee = int(f.payee[1])
        people[payee] = (*people[payee][:3], people[payee][3] + f.applied / MILLI)
        people[aid] = (*people[aid][:3], people[aid][3] - f.applied / MILLI)
    sellers = [[int(f.payee[1]), int(takes[int(f.payee[1])]), int(f.requested), int(f.applied)]
               for f in got.flows]
    t.dispatched.append({"shipment": sid, "holder": aid, "origin": o, "dest": d, "path": list(path), "milli": q,
                         "cargo": list(per_good), "price_milli": price_o, "paid": got.applied,
                         "refunded": got.residual, "sellers": len(takes), "seller_rows": sellers[:MAX_FRAME_SELLERS]})


def retail_phase10(world, acc, economy_result, agent_bridge) -> None:
    """Retail's Phase 10 seam, before its frame closes: holders' sales, then
    each live shipment's move (or return, or arrival), then purchases."""
    state = _state(world)
    turn = int(world.turn)
    if state.last_trade_turn is not None and turn <= state.last_trade_turn:
        raise RuntimeError("titled trade already traded this turn")
    t = _begin(world, state, getattr(agent_bridge, "_sim", None))
    sim = _native(agent_bridge)
    edges, closed = _graph(world)
    _attribute_sales(world, state, t)
    for ship in sorted(list(state.shipments), key=lambda s: s.id):
        _move(world, state, t, ship, edges, closed)
    _dispatch(world, state, t, sim, edges, economy_result, acc)
    _commit(world, state, t)
    state.last_trade_turn = turn


def phase10(world, acc, economy_result, agent_bridge) -> list:
    """Guard: the trade ran inside retail's Phase 10 this turn."""
    state = _state(world)
    if state.last_trade_turn != world.turn:
        raise RuntimeError("titled trade's Phase 10 did not run inside household retail's frame")
    return []


def _commit(world, state, t: _Turn) -> None:
    money.check_book(state.book)
    for ship in state.shipments + state.closed:
        lost = sum(ship.losses.values())
        if sum(ship.cargo_open) != sum(ship.cargo) + lost + ship.delivered + ship.returned + ship.deposited:
            raise RuntimeError(f"shipment {ship.id}: cargo does not close")
    state.frame_turn = t.turn
    state.frame = {
        "turn": t.turn, "dispatched": t.dispatched, "events": t.events, "withheld": t.withheld,
        "withheld_total": math.fsum(r["deducted"] for r in t.withheld), "sales": t.sales,
        "plans": dict(sorted(t.plans.items())), "live": len(state.shipments),
    }
    state._turn = None


# ---------------------------------------------------------------------------
# Pool reset and record
# ---------------------------------------------------------------------------

def on_pool_reset(world) -> None:
    """A rebuilt native pool: saved ids name strangers, so every live shipment
    ends ``pool_reset`` with its cargo in the commons where it stands, dated."""
    state = _state(world)
    if state is None or not state.shipments and not state.lots:
        return
    turn = int(getattr(world, "turn", 0))
    if state.shipments:
        _log(state, turn, "pool_reset", shipments=len(state.shipments))
    for ship in list(state.shipments):
        _deposit(world, state, ship, ship.region(), "pool_reset")
        _close(world, state, ship, turn, "pool_reset", None)
    state.lots = []


def snapshot_summary(world) -> dict:
    """The completed turn's copied record (``frame`` None: not observed)."""
    state = _state(world)
    source = world.turn - 1
    fresh = state.frame_turn == source and state.frame is not None
    import copy
    return {
        "schema_version": 1, "stage": "A4", "goods": state.goods, "source_turn": source,
        "units": {"food": "milli_food", "money": "milli_units", "price": "milli_per_ration",
                  "withheld": "wealth_units", "milli": MILLI},
        "shipments": [s.model_dump() for s in state.shipments],
        "closed": [s.model_dump() for s in state.closed],
        "lots": [x.model_dump() for x in state.lots],
        "frame": copy.deepcopy(state.frame) if fresh else None,
        "flows": ([f.model_dump() for f in state.book.flows] if fresh and state.book.flows_turn == source
                  else [] if fresh else None),
        "counters": {k: state.counters[k] for k in COUNTERS if k in state.counters},
        "log": [r.model_dump() for r in state.log], "log_dropped": state.log_dropped,
        "parameters": {"owner_keep_milli": OWNER_KEEP, "reserve_rations": RESERVE_RATIONS,
                       "load_margin": LOAD_MARGIN, "min_cargo_milli": MIN_CARGO, "max_hops": MAX_HOPS,
                       "cargo_caps_milli": {"land": LAND_CAP, "river": RIVER_CAP, "sea": SEA_CAP},
                       "transit_decay": list(TRANSIT_DECAY), "max_shipments": MAX_SHIPMENTS,
                       "outcomes": list(OUTCOMES), "return_causes": list(RETURN_CAUSES)},
    }
