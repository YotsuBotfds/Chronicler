"""Read-only merchant observations with Python-authoritative voyage continuity.

No observation establishes private title, a cash account or insurance liability.
Only a complete, observed reservation start establishes a trajectory-local voyage.
"""
from __future__ import annotations

import hashlib
import json
import math

from chronicler.transaction_receipts_state import (
    ActiveVoyage, TransactionObservation, TransactionReceiptState, transaction_receipts_on,
)

_MODES = {"hybrid", "shadow", "demographics-only"}
_OPERATIONS = {
    0: ("reserved", "reserved_shared_stock"),
    1: ("departed", "departure_queued_gross"),
    2: ("reservation_cancelled", "reservation_released"),
    3: ("replanned", "cargo_in_transit_unchanged"),
    4: ("returned", "return_credit_queued_gross"),
    5: ("sea_crossing", "cargo_crossing_gross"),
    6: ("arrived", "arrival_queued_before_transit_decay"),
    7: ("active", "mobility_phase_commitment"),
}


def set_transaction_receipts_enabled(world, enabled: bool, *, max_rows: int = 4096,
                                     namespace: str | None = None) -> None:
    if not enabled:
        world.transaction_receipts = None
    elif not transaction_receipts_on(world):
        world.transaction_receipts = TransactionReceiptState(
            max_rows=max_rows, namespace=namespace or f"seed:{world.seed}")


def validate_transaction_receipts(world, *, agent_mode: str | None = None) -> None:
    mode = agent_mode if agent_mode is not None else getattr(world, "agent_mode", "off")
    if transaction_receipts_on(world) and mode not in _MODES:
        raise ValueError("transaction receipts require hybrid, shadow or demographics-only agents")


def validate_fresh_transaction_receipt_pool(world) -> None:
    """Reject ID continuity when a raw WorldState would seed a different pool.

    Call from fresh AgentBridge.__init__, never exact-checkpoint __setstate__.
    Seed, turn and equal integer IDs cannot prove native pool identity.
    """
    if transaction_receipts_on(world):
        state = world.transaction_receipts
        if state.source_turn is not None or state.active or state.frame:
            raise ValueError(
                "saved transaction receipt identities require an exact native checkpoint; "
                "a raw WorldState restart creates a fresh agent pool. Explicitly disable "
                "transaction receipts to discard the journal before starting a fresh pool")


def transaction_receipts_active(world) -> bool:
    return transaction_receipts_on(world) and getattr(world, "agent_mode", "off") in _MODES


def prepare_transaction_receipts(world, bridge) -> None:
    """Rebuild transient native configuration before each tick and after resume."""
    sim = getattr(bridge, "_sim", bridge)
    configure = getattr(sim, "configure_transaction_receipts", None)
    active = transaction_receipts_active(world)
    if configure is None:
        if active:
            raise RuntimeError("transaction receipts require a native build with receipt support")
        return
    configure(active, world.transaction_receipts.max_rows if active else 4096)


def capture_transaction_receipts(world, bridge) -> None:
    """Call only after a successful native tick, before Python world postprocessing."""
    if not transaction_receipts_active(world):
        return
    sim = getattr(bridge, "_sim", bridge)
    source_turn, limit, dropped, executed, batch = sim.get_transaction_receipt_frame()
    if source_turn is None:
        return  # Restored transient buffer: saved Python frame remains authoritative.
    rows = batch.to_pylist() if hasattr(batch, "to_pylist") else list(batch)
    consume_transaction_frame(world, source_turn, limit, dropped, executed, rows)


def _civ(world, ident):
    if ident == 255:
        return None, None
    if not 0 <= ident < len(world.civilizations):
        raise ValueError("transaction receipt has unknown civilization index")
    return ident, world.civilizations[ident].name


def _voyage_matches(voyage, row) -> bool:
    return (voyage.origin_region, voyage.dest_region, voyage.good_slot) == (
        row["origin_region"], row["dest_region"], row["good_slot"])


def consume_transaction_frame(world, source_turn: int, limit: int, dropped: int,
                              executed: bool, rows: list[dict]) -> None:
    """Validate an entire bounded native frame before committing identity/counters.

    Re-reading the identical frame is a no-op. Partial capture or a gap discards
    continuity: a later reservation start can establish a new known identity.
    """
    if not transaction_receipts_active(world):
        return
    state = world.transaction_receipts
    if source_turn != world.turn or (state.source_turn is not None and source_turn < state.source_turn):
        raise ValueError("transaction receipt source turn does not match current turn")
    if limit != state.max_rows or dropped < 0 or len(rows) > limit:
        raise ValueError("transaction receipt frame has invalid bounds")
    if not executed and rows:
        raise ValueError("unexecuted mobility frame contains observations")
    digest = hashlib.sha256(json.dumps(
        [source_turn, limit, dropped, executed, rows], sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode()).hexdigest()
    if source_turn == state.source_turn:
        if digest != state.frame_digest:
            raise ValueError("conflicting transaction receipt frame for processed turn")
        return
    complete = bool(executed and dropped == 0)
    consecutive = state.source_turn is None or state.source_turn == source_turn - 1
    prior = {k: v.model_copy(deep=True) for k, v in state.active.items()} if complete and consecutive else {}
    active = {}
    observations = []
    counters = dict(state.counters)
    identities = set()
    seen_active = set()
    for row in rows:
        op = row["operation"]
        if op not in _OPERATIONS:
            raise ValueError("unknown transaction receipt operation")
        quantity = row["quantity"]
        if not math.isfinite(quantity) or quantity < 0 or not 0 <= row["good_slot"] < 9:
            raise ValueError("invalid transaction receipt cargo")
        for field in ("origin_region", "dest_region", "from_region", "to_region"):
            if not 0 <= row[field] < len(world.regions):
                raise ValueError("transaction receipt has unknown region index")
        merchant = row["merchant_id"]
        if not 0 <= merchant <= 2**32 - 1:
            raise ValueError("invalid merchant identity")
        operation, basis = _OPERATIONS[op]
        # Native currently emits at most one observation of a kind per merchant
        # and leg per tick. Semantic key is deliberately not a log ordinal.
        ident = f"{state.namespace}:native:{source_turn}:{merchant}:{op}:{row['from_region']}:{row['to_region']}:{row['good_slot']}"
        if ident in identities:
            raise ValueError("duplicate transaction observation identity")
        identities.add(ident)
        voyage = prior.get(merchant)
        if voyage is not None and not _voyage_matches(voyage, row):
            voyage = None
        if op == 0 and complete:
            voyage = ActiveVoyage(
                voyage_id=f"{state.namespace}:voyage:{merchant}:{source_turn}", start_turn=source_turn,
                origin_region=row["origin_region"], dest_region=row["dest_region"], good_slot=row["good_slot"])
            prior[merchant] = voyage
            counters["observed_starts"] += 1
        if op == 7:
            if merchant in seen_active:
                raise ValueError("duplicate active merchant in transaction frame")
            seen_active.add(merchant)
            active[merchant] = voyage or ActiveVoyage(
                origin_region=row["origin_region"], dest_region=row["dest_region"], good_slot=row["good_slot"])
        civ, civ_name = _civ(world, row["merchant_civ"])
        origin_owner, origin_owner_name = _civ(world, row["origin_controller"])
        dest_owner, dest_owner_name = _civ(world, row["dest_controller"])
        loss = row["loss_reason"]
        if loss not in (1, 255) or (loss != 255 and op != 5):
            raise ValueError("unknown transaction receipt loss boundary")
        known_id = voyage.voyage_id if complete and voyage is not None else None
        observations.append(TransactionObservation(
            id=ident, source_turn=source_turn, operation=operation, merchant_id=merchant,
            merchant_civ=civ, merchant_civ_name=civ_name, voyage_id=known_id,
            origin_region=row["origin_region"], origin_region_name=world.regions[row["origin_region"]].name,
            dest_region=row["dest_region"], dest_region_name=world.regions[row["dest_region"]].name,
            from_region=row["from_region"], to_region=row["to_region"], good_slot=row["good_slot"],
            quantity=quantity, origin_controller=origin_owner, origin_controller_name=origin_owner_name,
            dest_controller=dest_owner, dest_controller_name=dest_owner_name,
            cargo_basis="regional_stock" if row["physical_stock"] else "virtual_shadow",
            quantity_basis=basis, loss_reason="raid" if loss == 1 else None,
            loss_id=f"{ident}:loss:raid" if loss == 1 else None,
        ))
        if known_id is None:
            counters["unknown_voyage_rows"] += 1
        if loss == 1:
            key = "regional_cargo_raided" if row["physical_stock"] else "virtual_cargo_raided"
            counters[key] += quantity
        if op in (2, 4, 6) or loss == 1:
            prior.pop(merchant, None)
    # An incomplete final set cannot establish absence, survival or a closed trip.
    # Clear prior identities rather than carrying potentially stale assignments.
    state.active = active
    state.frame = observations
    state.source_turn, state.frame_digest = source_turn, digest
    state.complete, state.dropped_rows = complete, dropped
    state.mobility_executed = bool(executed)
    counters["frames"] += 1
    counters["incomplete_frames"] += int(not complete)
    counters["rows"] += len(rows)
    counters["dropped_rows"] += dropped
    state.counters = counters


def snapshot_summary(world) -> dict:
    if not transaction_receipts_active(world):
        return {}
    state = world.transaction_receipts
    if state.source_turn != world.turn - 1:
        return {}
    return {
        "source_turn": state.source_turn, "phase": "merchant_mobility",
        "complete": state.complete, "mobility_executed": state.mobility_executed,
        "dropped_rows": state.dropped_rows,
        "max_rows": state.max_rows, "active_count": len(state.active),
        "known_active_count": sum(v.voyage_id is not None for v in state.active.values()),
        "counters": dict(state.counters),
        "rows": [row.model_dump(mode="json") for row in state.frame],
    }
