"""Bounded observations of existing public procurement, never private sales."""
from __future__ import annotations

import hashlib
import json
import math

from chronicler.transaction_receipts import transaction_receipts_active
from chronicler.transaction_receipts_state import PublicPurchaseFrame, PublicPurchaseObservation

_COUNTERS = ("frames", "unavailable_frames", "observed_purchases", "dropped_rows",
             "duplicate_keys", "buyer_paid", "foreign_ruler_credited", "domestic_producer_sink",
             "sent", "received", "transit_loss")


def capture_public_purchases(world, *, economy_result, opening_treasuries=None,
                             demand=None, price=None, flow_start: int = 0) -> None:
    """After a successful granary pass, observe its existing committed flows.

    Opening projections/demand/price are the exact vectors already computed by
    procurement. Replay only its successful payment legs, without scanning the
    accumulator again, mutating accounts or truncating authoritative flows.
    """
    if not transaction_receipts_active(world):
        return
    from chronicler.grain_reserves_state import BOUGHT, grain_reserves_on
    state = world.transaction_receipts
    old = getattr(state, "public_purchases", None)
    if old is not None and old.source_turn > world.turn:
        raise ValueError("public purchase receipt state is ahead of the world turn")
    reason = None
    if not grain_reserves_on(world):
        reason = "granaries_unavailable"
    elif economy_result is None:
        reason = "economy_unavailable"
    elif opening_treasuries is None or demand is None or price is None:
        reason = "procurement_basis_unavailable"
    elif world.grain_reserves.flows_turn != world.turn:
        reason = "current_flows_unavailable"
    available = reason is None
    rows, seen = [], set()
    observed, dropped, duplicates = 0, 0, 0
    sums = {key: 0 for key in _COUNTERS}
    digest = hashlib.sha256()
    digest.update(json.dumps([world.turn, state.max_rows, available, reason, flow_start]).encode())
    if available:
        # Civ/region vectors, already built by the existing purchase kernel;
        # copying balances once costs O(civs), not O(civs * purchases).
        if (len(opening_treasuries) != len(world.civilizations)
                or len(demand) != len(world.regions) or len(price) != len(world.regions)):
            raise ValueError("public purchase receipt basis has invalid dimensions")
        if not 0 <= flow_start <= len(world.grain_reserves.flows):
            raise ValueError("public purchase receipt flow window is invalid")
        balances = list(opening_treasuries)
        for i, flow in enumerate(world.grain_reserves.flows):
            if i < flow_start or flow.kind != BOUGHT:
                continue
            buyer, seller, src, dest = flow.buyer, flow.seller, flow.source, flow.region
            if not (0 <= buyer < len(balances) and 0 <= seller < len(balances)
                    and 0 <= src < len(world.regions) and 0 <= dest < len(world.regions)):
                raise ValueError("public purchase receipt has unknown public identities")
            keeper = world.grain_reserves.granaries[dest].owner
            if keeper != buyer or flow.cost <= 0 or flow.cost > balances[buyer]:
                raise ValueError("public purchase receipt does not match committed keeper/payment")
            if (not all(math.isfinite(v) and v >= 0 for v in (flow.sent, flow.amount, demand[src], demand[dest], price[src]))
                    or flow.sent + 1e-9 < flow.amount):
                raise ValueError("public purchase receipt has invalid quantity/price basis")
            foreign = seller != buyer
            before = balances[buyer]
            seller_before = balances[seller] if foreign else None
            balances[buyer] -= flow.cost
            if foreign:
                balances[seller] += flow.cost
            ident = f"{state.namespace}:public-grain:{world.turn}:{buyer}:{dest}:{src}"
            row = PublicPurchaseObservation(
                id=ident, source_turn=world.turn, source_region=src,
                source_region_name=world.regions[src].name, dest_region=dest,
                dest_region_name=world.regions[dest].name, buyer=buyer,
                buyer_name=world.civilizations[buyer].name, keeper=keeper,
                keeper_name=world.civilizations[keeper].name, source_controller=seller,
                source_controller_name=world.civilizations[seller].name,
                purchase_kind="foreign" if foreign else "own_market" if src == dest else "same_realm",
                sent=flow.sent, received=flow.amount, transit_loss=max(0.0, flow.sent-flow.amount),
                buyer_paid=flow.cost, foreign_ruler_credited=flow.cost if foreign else 0,
                domestic_producer_sink=0 if foreign else flow.cost,
                buyer_treasury_before=before, buyer_treasury_after=balances[buyer],
                seller_treasury_before=seller_before,
                seller_treasury_after=balances[seller] if foreign else None,
                buyer_demand=demand[dest], source_demand=demand[src], source_market_price=price[src],
            )
            data = row.model_dump(mode="json")
            digest.update(json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
            observed += 1
            for key in ("buyer_paid", "foreign_ruler_credited", "domestic_producer_sink", "sent", "received", "transit_loss"):
                sums[key] += data[key]
            if ident in seen:
                duplicates += 1
                dropped += 1
            elif len(rows) == state.max_rows:
                dropped += 1
            else:
                rows.append(row)
                seen.add(ident)
    fingerprint = digest.hexdigest()
    if old is not None and old.source_turn == world.turn:
        if old.frame_digest != fingerprint:
            raise ValueError("conflicting public purchase receipt frame for processed turn")
        return
    counters = {key: (old.counters.get(key, 0) if old is not None else 0) for key in _COUNTERS}
    sums.update(frames=1, unavailable_frames=int(not available), observed_purchases=observed,
                dropped_rows=dropped, duplicate_keys=duplicates)
    for key, value in sums.items():
        counters[key] += value
    state.public_purchases = PublicPurchaseFrame(
        source_turn=world.turn, available=available, complete=available and dropped == 0,
        unavailable_reason=reason, max_rows=state.max_rows, dropped_rows=dropped,
        duplicate_keys=duplicates, observed_purchases=observed, rows=rows,
        frame_digest=fingerprint, counters=counters)


def snapshot_summary(world) -> dict:
    if not transaction_receipts_active(world):
        return {}
    frame = getattr(world.transaction_receipts, "public_purchases", None)
    if frame is not None and frame.source_turn == world.turn - 1:
        return frame.model_dump(mode="json", exclude={"frame_digest"})
    return {"source_turn": None, "as_of_turn": world.turn - 1,
            "phase": "phase10_granary_procurement", "available": False,
            "complete": False, "unavailable_reason": "not_captured", "rows": []}
