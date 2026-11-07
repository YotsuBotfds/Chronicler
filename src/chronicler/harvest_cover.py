"""B4: depleted timber stands open canopy gaps, opt-in and default off.

Runs after every timber harvester settled Phase 2 and before Phase 9 ecology.
L3 remains the sole standing-stock authority. Its settled rows supply the
current stock (including L3 regrowth and PL1 extraction). Canopy loss never
lowers any timber slot's effective capacity below its standing stock, so the
same wood is not lost again as clearing next turn. Ecology owns canopy
regrowth and the watershed reads the resulting cover through its own account.
"""
from __future__ import annotations

import math

from chronicler.harvest_cover_state import COUNTERS, MODES, CoverRow, HarvestCoverState

GAP_THRESHOLD = 0.3
LOSS_RATE = 0.05


def _state(world):
    return getattr(getattr(world, "livelihoods", None), "harvest_cover", None)


def harvest_cover_active(world):
    state = _state(world)
    return state is not None and state.enabled


def check_request(world, value, args, *, agent_mode, timber_on):
    state = _state(world)
    mode = getattr(args, "harvest_cover_mode", None)
    if mode is not None and mode not in MODES:
        raise ValueError("unknown harvest-cover mode")
    if mode is not None and (value is False or (value is None and not harvest_cover_active(world))):
        raise ValueError("--harvest-cover-mode requires --harvest-cover")
    if value is False:
        return
    if state is not None and mode is not None and state.mode != mode:
        raise ValueError("a harvest-cover mode change on resume is refused")
    if value is True or (value is None and harvest_cover_active(world)):
        if agent_mode != "hybrid" or not timber_on:
            raise ValueError("--harvest-cover requires --agents hybrid and --timber-stock; "
                             "pass --no-harvest-cover to end a saved switch")


def set_harvest_cover_enabled(world, value, *, args=None, agent_mode=None):
    mode = getattr(args, "harvest_cover_mode", None)
    state = _state(world)
    if state is None:
        world.livelihoods.harvest_cover = HarvestCoverState(enabled=bool(value), mode=mode or MODES[0])
    else:
        if mode is not None and mode != state.mode:
            raise ValueError("a harvest-cover mode change on resume is refused")
        state.enabled = bool(value)


def finish_phase2(world, economy_result, agent_bridge, acc):
    state = _state(world)
    if state is None or not state.enabled:
        return []
    if state.frame_turn is not None and state.frame_turn >= world.turn:
        raise RuntimeError("harvest cover already settled this turn")
    from chronicler import timber_stock as timber
    stock = timber._state(world)
    if stock is None or not stock.enabled or stock.ledger_turn != world.turn:
        raise RuntimeError("harvest cover requires this turn's settled timber account")
    by_region = {}
    for row in stock.ledger:
        if row.capacity > 0:
            by_region.setdefault(row.region_id, []).append(row)
    rows = []
    for rid, stands in sorted(by_region.items()):
        region = world.regions[rid]
        cover = float(region.ecology.forest_cover)
        standing = math.fsum(row.stock for row in stands)
        capacity = math.fsum(row.capacity for row in stands)
        ratio = standing / capacity
        # Shared canopy: respect the fullest slot, even if a neighbouring slot
        # is exhausted. No timber slot is allowed to lose its existing wood.
        supported = max(timber.woodland_reference_cover() * row.stock /
                        timber.reference_capacity(region, row.slot) for row in stands)
        proposed = max(0.0, min(LOSS_RATE * (GAP_THRESHOLD - ratio), cover - supported))
        loss = proposed if state.mode == "loss" else 0.0
        after = cover - loss
        if loss:
            region.ecology.forest_cover = after
        rows.append(CoverRow(region=rid, slots=[r.slot for r in stands], standing=standing,
                             capacity=capacity, ratio=ratio, cover_before=cover, supported_cover=supported,
                             proposed_loss=proposed, loss=loss, cover_after=after))
    state.rows, state.frame_turn = rows, world.turn
    values = (1, sum(r.proposed_loss > 0 for r in rows), math.fsum(r.loss for r in rows),
              math.fsum(r.proposed_loss for r in rows))
    for key, value in zip(COUNTERS, values, strict=True):
        state.counters[key] = state.counters.get(key, 0) + value
    return []


def snapshot_summary(world):
    state = _state(world)
    source = world.turn - 1
    return {"schema_version": 1, "stage": "B4", "source_turn": source, "mode": state.mode,
            "rows": [r.model_dump() for r in state.rows] if state.frame_turn == source else None,
            "counters": dict(state.counters),
            "parameters": {"gap_threshold": GAP_THRESHOLD, "loss_rate": LOSS_RATE,
                           "units": "canopy_fraction"}}
