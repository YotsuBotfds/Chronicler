"""One-hop public grain orders: dispatch T, arrive Phase10 T+1.

Cargo is buyer-titled until its named granary receives it. It is neither a
regional market stock nor food available to agents while pending. Permission
is checked at dispatch; this first deterministic model has no interdiction.
"""
from __future__ import annotations

import math

from chronicler.grain_reserves_state import (
    ARRIVED, DISPATCHED, ReserveFlow, grain_reserves_on,
)
from chronicler.public_grain_shipments_state import (
    COUNTERS, MAX_FRAME, MAX_ORDER, MAX_PENDING, MAX_PER_DEST,
    PublicGrainOrder, PublicGrainShipmentState, PublicGrainTransition, shipment_id,
)


def shipment_state(world):
    if not grain_reserves_on(world):
        return None
    state = getattr(world.grain_reserves, "shipments", None)
    if state is not None and type(state) is not PublicGrainShipmentState:
        raise ValueError("unknown public grain shipment state")
    return state


def set_public_grain_shipments_enabled(world, enabled: bool) -> None:
    if not grain_reserves_on(world):
        if enabled:
            raise ValueError("public grain shipments require --grain-reserves")
        return
    state = shipment_state(world)
    if enabled and world.agent_mode in (None, "off"):
        raise ValueError("public grain shipments require an agent-backed goods economy")
    if state is None:
        if enabled:
            world.grain_reserves.shipments = PublicGrainShipmentState()
    else:
        validate_shipments(world)
        state.accept_orders = bool(enabled)  # disabling drains; retain IDs forever


def _validate_order(world, row, next_order):
    if (type(row.order) is not int or not 0 <= row.order < next_order
            or type(row.dispatch_turn) is not int or type(row.due_turn) is not int
            or row.dispatch_turn < 0 or row.dispatch_turn > world.turn
            or row.due_turn != row.dispatch_turn + 1 or row.buyer == row.seller
            or row.source == row.dest
            or type(row.paid) is not int or row.paid <= 0):
        raise ValueError("invalid public grain order identity, timing or payment")
    for index, name in ((row.source, row.source_name), (row.dest, row.dest_name)):
        if (type(index) is not int or not 0 <= index <= 65534 or index >= len(world.regions)
                or world.regions[index].name != name):
            raise ValueError("public grain order region was removed or replaced")
    for index, name in ((row.buyer, row.buyer_name), (row.seller, row.seller_name)):
        if (type(index) is not int or not 0 <= index <= 253 or index >= len(world.civilizations)
                or world.civilizations[index].name != name):
            raise ValueError("public grain order civilization was removed or replaced")
    if (not all(math.isfinite(v) and v >= 0 for v in (row.sent, row.net, row.loss))
            or row.net <= 0 or row.sent <= 0 or row.net > row.sent
            or abs(row.sent - row.net - row.loss) > 1e-9 * max(1.0, row.sent)):
        raise ValueError("public grain order cargo does not balance")


def validate_shipments(world) -> None:
    """Pure active-entry admission; reject edited universes before turn effects."""
    state = shipment_state(world)
    if state is None:
        return
    if (type(state.schema_version) is not int or state.schema_version != 1 or type(state.accept_orders) is not bool
            or type(state.next_order) is not int or not 0 <= state.next_order <= MAX_ORDER
            or len(state.pending) > MAX_PENDING or len(state.frame) > MAX_FRAME
            or set(state.counters) != set(COUNTERS)
            or not all(math.isfinite(v) and v >= 0 for v in state.counters.values())):
        raise ValueError("invalid public grain shipment state")
    for turn in (state.last_arrivals_turn, state.frame_turn):
        if turn is not None and (type(turn) is not int or not 0 <= turn <= world.turn):
            raise ValueError("public grain shipment state is ahead of world turn")
    if state.pending and len(world.grain_reserves.granaries) != len(world.regions):
        raise ValueError("public grain orders require the original granary universe")
    seen, counts, destination_granaries = set(), {}, {}
    pending_net = 0.0
    for row in state.pending:
        if type(row) is not PublicGrainOrder:
            raise ValueError("unknown public grain pending record")
        _validate_order(world, row, state.next_order)
        if row.order in seen:
            raise ValueError("duplicate pending public grain order")
        seen.add(row.order)
        counts[row.dest] = counts.get(row.dest, 0) + 1
        if counts[row.dest] > MAX_PER_DEST:
            raise ValueError("public grain destination capacity exceeded")
        pending_net += row.net
        if not math.isfinite(pending_net):
            raise ValueError("public grain pending inventory overflows")
        granary = world.grain_reserves.granaries[row.dest]
        previous = destination_granaries.setdefault(id(granary), row.dest)
        if (previous != row.dest or not math.isfinite(granary.grain) or granary.grain < 0
                or not -1 <= granary.owner < len(world.civilizations)):
            raise ValueError("invalid or aliased public grain destination granary")
    transitions = set()
    for row in state.frame:
        if type(row) is not PublicGrainTransition:
            raise ValueError("unknown public grain transition record")
        _validate_order(world, row, state.next_order)
        key = (row.order, row.operation)
        if (row.id != shipment_id(row.dispatch_turn, row.order)
                or row.operation not in ("arrived", "dispatched")
                or key in transitions or row.turn != state.frame_turn
                or row.keeper < -1 or row.keeper >= len(world.civilizations)
                or (row.operation == "arrived" and row.turn < row.due_turn)
                or (row.operation == "dispatched" and row.turn != row.dispatch_turn)):
            raise ValueError("invalid public grain transition frame")
        transitions.add(key)


def inbound_by_destination(world) -> list[float] | None:
    state = shipment_state(world)
    if state is None:
        return None
    totals = [0.0] * len(world.regions)
    for row in state.pending:
        totals[row.dest] += row.net
    if not all(math.isfinite(v) for v in totals):
        raise ValueError("public grain inbound commitments overflow")
    return totals


def _event(world, row, operation, keeper):
    from chronicler.models import Event
    if operation == "dispatched":
        line = (f"{row.buyer_name} sends an order for {row.net:.1f} grain from "
                f"{row.source_name} to {row.dest_name} ({row.paid} treasury); "
                f"it is due after the next turn's granary opening.")
    else:
        custody = world.civilizations[keeper].name if keeper >= 0 else "no ruler"
        line = (f"Order {shipment_id(row.dispatch_turn, row.order)} delivers {row.net:.1f} grain to the granary in "
                f"{row.dest_name}, kept by {custody}; {row.buyer_name} paid at dispatch.")
    return Event(turn=world.turn, event_type=f"public_grain_{operation}",
                 actors=[row.buyer_name], civs=[row.seller_name], region=row.dest_name,
                 importance=2, description=line)


def settle_arrivals(world) -> list:
    """Phase10 only, with an economy result available; never release food here."""
    state = shipment_state(world)
    if state is None or world.agent_mode in (None, "off"):
        return []
    validate_shipments(world)
    if state.last_arrivals_turn == world.turn:
        return []
    reserves = world.grain_reserves
    due = sorted((row for row in state.pending if row.due_turn <= world.turn),
                 key=lambda row: (row.due_turn, row.order))
    transitions, events = [], []
    grains = {}
    for row in due:
        granary = reserves.granaries[row.dest]
        if not -1 <= granary.owner < len(world.civilizations):
            raise ValueError("public grain destination has invalid keeper")
        if not math.isfinite(granary.grain) or granary.grain < 0:
            raise ValueError("public grain destination has invalid stock")
        grains[row.dest] = grains.get(row.dest, granary.grain) + row.net
        if not math.isfinite(grains[row.dest]):
            raise ValueError("public grain arrival overflows destination")
        transitions.append(PublicGrainTransition(**row.model_dump(), id=shipment_id(row.dispatch_turn, row.order), operation="arrived",
                                               turn=world.turn, keeper=granary.owner))
        events.append(_event(world, row, "arrived", granary.owner))
    arrived_flows = [ReserveFlow(kind=ARRIVED, region=row.dest, amount=row.net,
                                source=row.source, seller=row.seller, buyer=row.buyer,
                                shipment_order=row.order)
                     for row in due]
    due_ids = {row.order for row in due}
    remaining = [row for row in state.pending if row.order not in due_ids]
    original_flows, original_flows_turn = reserves.flows, reserves.flows_turn
    flows = original_flows if original_flows_turn == world.turn else []
    # Fixed local write set; restore existing list/dict/model identities.
    old = (list(state.pending), state.frame, state.frame_turn, state.last_arrivals_turn,
           dict(state.counters), len(flows),
           [(reserves.granaries[r], reserves.granaries[r].grain) for r in grains])
    try:
        reserves.__dict__.update(flows=flows, flows_turn=world.turn)
        for rid, amount in grains.items():
            reserves.granaries[rid].__dict__["grain"] = amount
        state.pending[:] = remaining
        state.__dict__["frame"] = transitions
        state.__dict__["frame_turn"] = world.turn
        state.__dict__["last_arrivals_turn"] = world.turn
        flows.extend(arrived_flows)
        for row in transitions:
            state.counters["arrived"] += 1
            state.counters["delivered"] += row.net
            if row.keeper == -1:
                state.counters["unguarded_delivery"] += row.net
            elif row.keeper != row.buyer:
                state.counters["captured_delivery"] += row.net
        if not all(math.isfinite(value) for value in state.counters.values()):
            raise ValueError("public grain arrival counters overflow")
    except Exception:
        pending, frame, frame_turn, last_turn, counters, flow_len, granaries = old
        state.pending[:] = pending
        state.__dict__.update(frame=frame, frame_turn=frame_turn, last_arrivals_turn=last_turn)
        state.counters.clear(); state.counters.update(counters)
        del flows[flow_len:]
        reserves.__dict__.update(flows=original_flows, flows_turn=original_flows_turn)
        for granary, grain in granaries:
            granary.__dict__["grain"] = grain
        raise
    return events


def dispatch_order(world, *, buyer, seller, source, dest, sent, net, cost,
                   graph, surplus, budget, inbound, flows, acc=None):
    """Commit one paid order atomically; None means capacity/identity exhaustion."""
    state = shipment_state(world)
    if state is None or not state.accept_orders or world.agent_mode in (None, "off"):
        raise ValueError("public grain dispatch is unavailable")
    if state.last_arrivals_turn != world.turn or state.frame_turn != world.turn:
        raise ValueError("public grain arrivals must precede dispatch")
    if state.next_order == MAX_ORDER:
        state.counters["identity_refusals"] += 1
        return None
    if (len(state.pending) >= MAX_PENDING
            or sum(row.dest == dest for row in state.pending) >= MAX_PER_DEST):
        state.counters["capacity_refusals"] += 1
        return None
    regions, civs = world.regions, world.civilizations
    if (not 0 <= buyer < len(civs) or not 0 <= seller < len(civs) or buyer == seller
            or not 0 <= source < len(regions) or not 0 <= dest < len(regions)
            or source not in graph.get(dest, ())
            or regions[source].controller != civs[seller].name
            or regions[dest].controller != civs[buyer].name
            or world.grain_reserves.granaries[dest].owner != buyer
            or len(surplus) != len(regions) or len(inbound) != len(regions)
            or len(budget) != len(civs)):
        raise ValueError("public grain dispatch identities/route are invalid")
    if (civs[buyer] is civs[seller] or civs[buyer].name == civs[seller].name
            or regions[source] is regions[dest] or regions[source].name == regions[dest].name):
        raise ValueError("public grain dispatch parties must have distinct identities")
    from chronicler.finance import _capture_exact_transfer, _projections, transfer
    from chronicler.grain_reserves import _transit_loss
    goods = regions[source].stockpile.goods
    available = goods.get("grain", 0.0)
    if (type(cost) is not int or cost <= 0 or cost > budget[buyer]
            or cost > _projections(world, acc)[buyer]
            or not all(math.isfinite(v) and v >= 0 for v in
                       (sent, net, available, surplus[source], inbound[dest]))
            or sent <= 0 or net <= 0 or sent > available or sent > surplus[source]
            or abs(net - sent * (1.0 - _transit_loss())) > 1e-9 * max(1.0, sent)
            or not math.isfinite(inbound[dest] + net)):
        raise ValueError("public grain dispatch cargo/payment is invalid")
    row = PublicGrainOrder(order=state.next_order, source=source,
                          source_name=regions[source].name, dest=dest, dest_name=regions[dest].name,
                          buyer=buyer, buyer_name=civs[buyer].name, seller=seller,
                          seller_name=civs[seller].name, dispatch_turn=world.turn,
                          due_turn=world.turn + 1, sent=float(sent), net=float(net),
                          loss=float(sent - net), paid=cost)
    transition = PublicGrainTransition(**row.model_dump(), id=shipment_id(row.dispatch_turn, row.order), operation="dispatched",
                                       turn=world.turn, keeper=buyer)
    flow = ReserveFlow(kind=DISPATCHED, region=dest, amount=net, source=source,
                       seller=seller, buyer=buyer, sent=sent, cost=cost, shipment_order=row.order)
    event = _event(world, row, "dispatched", buyer)
    payment = _capture_exact_transfer(world, buyer, seller, cost, acc=acc)
    old = ("grain" in goods, available, surplus[source], budget[buyer], inbound[dest],
           len(state.pending), len(state.frame), len(flows), state.next_order,
           dict(state.counters), dict(world.grain_reserves.counters))
    try:
        paid = transfer(world, buyer, seller, cost, acc=acc)
        if paid != cost:
            raise ValueError("public grain dispatch payment was partial")
        payment.check_specie()
        goods["grain"] = available - sent
        surplus[source] -= sent
        budget[buyer] -= cost
        inbound[dest] += net
        state.pending.append(row)
        state.frame.append(transition)
        flows.append(flow)
        state.__dict__["next_order"] += 1
        for key, value in (("dispatched", 1), ("sent", sent), ("committed_net", net),
                           ("transit_loss", sent-net), ("paid", cost)):
            state.counters[key] += value
        for key, value in (("sent", sent), ("transit_loss", sent-net), ("paid_foreign", cost)):
            world.grain_reserves.counters[key] += value
        if (not all(math.isfinite(v) for v in state.counters.values())
                or not all(math.isfinite(world.grain_reserves.counters[key])
                           for key in ("sent", "transit_loss", "paid_foreign"))):
            raise ValueError("public grain dispatch counters overflow")
    except Exception:
        had, grain, old_surplus, old_budget, old_inbound, pending_len, frame_len, flow_len, order, counters, reserves_counters = old
        payment.restore()
        if had:
            goods["grain"] = grain
        else:
            goods.pop("grain", None)
        surplus[source], budget[buyer], inbound[dest] = old_surplus, old_budget, old_inbound
        del state.pending[pending_len:]
        del state.frame[frame_len:]
        del flows[flow_len:]
        state.__dict__["next_order"] = order
        state.counters.clear(); state.counters.update(counters)
        world.grain_reserves.counters.clear(); world.grain_reserves.counters.update(reserves_counters)
        raise
    return event


def snapshot_summary(world) -> dict:
    state = shipment_state(world)
    if state is None:
        return {}
    return {"schema_version": 1, "accept_orders": state.accept_orders,
            "pending_count": len(state.pending),
            "pending_net": math.fsum(row.net for row in state.pending),
            "source_turn": world.turn - 1,
            "transitions": [row.model_dump() for row in state.frame]
            if state.frame_turn == world.turn - 1 else [],
            "counters": dict(state.counters)}
