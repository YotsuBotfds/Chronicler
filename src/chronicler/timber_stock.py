"""L3: a renewable harvestable timber stock with delayed recovery (default off).

``--timber-stock`` (see :mod:`chronicler.livelihoods`). Each region slot whose
resource is timber holds an explicit harvestable stock, in the goods the
economy's ``slot_output`` counts. Before the native economy tick
(``prepare_phase2``) the stock is offered as a per-slot production cap
(``timber_harvest_cap_{slot}``), so the realized harvest cannot exceed it.
After a successful tick (``finish_phase2``) one account per slot is settled,
in this order:

1. ``cleared``: the stock above this turn's effective capacity. Capacity
   follows the current forest cover, so cover lost to clearing, cooling,
   wildfire or succession takes the timber standing on it. This is a loss of
   its own, never extraction, and it precedes the harvest (cover changes in
   Phase 9 of the previous turn and Phase 1 of this one, both before Phase 2;
   the cap offered already excludes it).
2. ``extraction``: the realized timber output (``slot_output``) of the slot.
3. ``regrowth``: logistic growth toward the effective capacity, with a
   seedling term so a cut stand regrows, while the region's water is at or
   above the forest regrowth water gate (as forest cover regrowth).

``stock = opening - cleared - (extraction - overdraft) + regrowth - removed``
is checked every turn and a violation raises. The stock never changes forest
cover, soil or any other world state, consumes no RNG and emits no events.

Ablation (cost-retaining control): tuning ``livelihoods.timber.enforce_cap``
0 keeps the whole accounting and the columns (all null) but applies no cap;
realized extraction beyond the stock is recorded as ``overdraft`` and the
stock floors at zero. Outcomes then match a run without the stock.

Every parameter below is a declared modeling choice, not a calibration.
"""
from __future__ import annotations

import math
from typing import Any

from chronicler.timber_stock_state import (
    TimberLedgerRow, TimberSlotStock, TimberStockState, TimberTotals,
)

#: Logistic regrowth rate per turn (a turn is a month: ``get_season_id``).
#: Matches the time scale of forest cover regrowth (+0.01 cover a turn, about
#: 90 turns from bare ground to woodland), not real forestry: with the seed
#: term a stand cut to nothing is back to 90% of capacity in about 167 turns,
#: one cut to half in about 68.
REGROWTH_RATE = 0.03
#: Seedlings and coppice: regrowth from a cut stand starts as if this share of
#: capacity were standing (``r * (S + a K) * (1 - S / K)``). Without it a
#: harvested-out logistic stock never regrows.
SEED_FRACTION = 0.05
#: Capacity anchor: the woodland's reference crew (the economy's woodland
#: curve reference labour, ``economy.RAW_REFERENCE_DENSITY`` per unit of
#: carrying capacity, at the healthy woodland cover) harvesting the slot's base
#: goods yield takes exactly this many times the stock's maximum sustained
#: yield. 1.0: the reference crew is sustainable; larger crews (the curve gives
#: up to twice the reference labour's output) deplete the stock.
REFERENCE_CREWS_AT_MSY = 1.0
#: Tuning key of the ablation control (1: enforce the cap, 0: account only).
K_TIMBER_ENFORCE_CAP = "livelihoods.timber.enforce_cap"
#: Native economy input columns (Float32 per region; null = no cap).
CAP_COLUMNS = tuple(f"timber_harvest_cap_{slot}" for slot in range(3))
#: Relative tolerance of the ledger identity check (float64 arithmetic).
LEDGER_TOLERANCE = 1e-9
SCHEMA_VERSION = 1


# --- State access ---------------------------------------------------------------

def _state(world) -> TimberStockState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "timber_stock", None) if container is not None else None


def timber_stock_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled


def enforce_cap(world) -> bool:
    """False under the cost-retaining ablation (``livelihoods.timber.enforce_cap`` 0)."""
    from chronicler.tuning import get_override
    value = get_override(world, K_TIMBER_ENFORCE_CAP, 1.0)
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{K_TIMBER_ENFORCE_CAP} must be a finite number")
    return bool(value)


# --- Capacity and growth ----------------------------------------------------------

def _is_timber(rtype) -> bool:
    from chronicler.models import ResourceType
    return int(rtype) == int(ResourceType.TIMBER)


def timber_slots(world) -> list[tuple[int, int]]:
    """(region index, slot) of every timber slot, in order."""
    return [(rid, slot) for rid, region in enumerate(world.regions)
            for slot, rtype in enumerate(region.resource_types) if _is_timber(rtype)]


def woodland_reference_cover() -> float:
    """The healthy woodland cover the economy's woodland curve is relative to."""
    from chronicler.ecology import TERRAIN_ECOLOGY_DEFAULTS
    return TERRAIN_ECOLOGY_DEFAULTS["forest"].forest_cover


def reference_harvest(region, slot: int) -> float:
    """Goods a turn the woodland's reference crew takes at healthy cover.

    ``base yield x RAW_REFERENCE_DENSITY x carrying capacity``: the economy's
    woodland curve reference labour at healthy cover (its effective labour
    equals its headcount there) times the slot's mean goods yield per worker
    on healthy land (``ecology.goods_per_worker`` normalizes to the base yield).
    The temporary ``capacity_modifier`` (drought, flood) is left out, so a
    drought does not fell the stand.
    """
    from chronicler.economy import RAW_REFERENCE_DENSITY
    base = max(0.0, float(region.resource_base_yields[slot]))
    return base * RAW_REFERENCE_DENSITY * max(1.0, float(region.carrying_capacity))


def reference_capacity(region, slot: int) -> float:
    """Capacity at healthy woodland cover: its maximum sustained yield
    ``r K (1 + a)^2 / 4`` equals the reference harvest x REFERENCE_CREWS_AT_MSY."""
    msy_factor = REGROWTH_RATE * (1.0 + SEED_FRACTION) ** 2 / 4.0
    return REFERENCE_CREWS_AT_MSY * reference_harvest(region, slot) / msy_factor


def effective_capacity(region, slot: int) -> float:
    """This turn's capacity: the reference capacity scaled by the current cover."""
    cover = max(0.0, float(region.ecology.forest_cover))
    return reference_capacity(region, slot) * cover / woodland_reference_cover()


def water_gate_open(world, region) -> bool:
    """Forest regrowth's water gate (``ecology.forest_regrowth_water_gate``)."""
    from chronicler.tuning import K_FOREST_REGROWTH_WATER_GATE, get_override
    return region.ecology.water >= get_override(world, K_FOREST_REGROWTH_WATER_GATE, 0.3)


def regrowth(stock: float, capacity: float, gate_open: bool) -> float:
    """Logistic regrowth with the seed term; never beyond capacity."""
    if not gate_open or capacity <= 0.0 or stock >= capacity:
        return 0.0
    grown = REGROWTH_RATE * (stock + SEED_FRACTION * capacity) * (1.0 - stock / capacity)
    return min(max(grown, 0.0), capacity - stock)


def _f32_floor(value: float) -> float:
    """The largest float32 not above ``value`` (the cap may not exceed the stock)."""
    import numpy as np
    f = np.float32(value)
    if float(f) > value:
        f = np.nextafter(f, np.float32(-np.inf), dtype=np.float32)
    return max(0.0, float(f))


# --- Opening stocks and caps ----------------------------------------------------

def _opening(world, state: TimberStockState) -> dict[tuple[int, int], float]:
    """Each current timber slot's opening stock; a slot with no stock yet
    (a resource that became timber) opens at its effective capacity."""
    held = {(row.region_id, row.slot): row.stock for row in state.stocks}
    opening = {}
    for rid, slot in timber_slots(world):
        if (rid, slot) in held:
            opening[(rid, slot)] = held[(rid, slot)]
        else:
            opening[(rid, slot)] = effective_capacity(world.regions[rid], slot)
    return opening


def harvest_caps(world) -> dict[tuple[int, int], float]:
    """The float32 harvest limit of each timber slot: what is standing within
    this turn's capacity, rounded down. Reads state only."""
    state = _state(world)
    if state is None:
        return {}
    caps = {}
    for (rid, slot), stock in _opening(world, state).items():
        capacity = effective_capacity(world.regions[rid], slot)
        caps[(rid, slot)] = _f32_floor(min(stock, capacity))
    return caps


# --- Protocol: switch ----------------------------------------------------------

def set_timber_stock_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable (initializing every timber slot without a stock at its
    cover-implied capacity) or disable (stocks freeze; re-enabling resumes)."""
    state = _state(world)
    if state is None:
        if not value:
            return  # never enabled: nothing to record
        if getattr(world, "livelihoods", None) is None:
            from chronicler.livelihoods_state import LivelihoodsState
            world.livelihoods = LivelihoodsState()
        world.livelihoods.timber_stock = state = TimberStockState()
    state.enabled = bool(value)
    if state.enabled:
        opening = _opening(world, state)
        held = {(row.region_id, row.slot) for row in state.stocks}
        if set(opening) - held:
            kept = list(state.stocks)
            kept += [TimberSlotStock(region_id=rid, slot=slot, stock=initial)
                     for (rid, slot), initial in opening.items() if (rid, slot) not in held]
            state.stocks = sorted(kept, key=lambda row: (row.region_id, row.slot))


# --- Protocol: Phase 2 ---------------------------------------------------------

def _farmers_by_region(snapshot, n: int) -> list[int] | None:
    """Farmers (occupation 0) per region index of the Phase 2 agent snapshot,
    the pool the native economy derives its labour from; None when unknown."""
    from chronicler.columnar import batch_arrays

    arrays = batch_arrays(snapshot, ("region", "occupation"))
    if arrays is None:
        return None
    import numpy as np

    regions = arrays[0].astype(np.int64)
    farmers = (regions >= 0) & (regions < n) & (arrays[1] == 0)
    return np.bincount(regions[farmers], minlength=n).tolist()


def prepare_phase2(world, region_input, agent_bridge, snapshot, acc):
    """Append ``timber_harvest_cap_{slot}`` (Float32; null off timber slots and
    under the ablation). Charges nothing and changes no stock; remembers what
    it offered (and whether a harvest was possible: a positive goods yield in
    the batch and farmers in the region) for this turn's finish only."""
    import pyarrow as pa

    state = _state(world)
    names = set(region_input.schema.names)
    if names & set(CAP_COLUMNS):
        raise ValueError("timber harvest cap columns are owned by the timber stock")
    n = len(world.regions)
    if region_input.num_rows != n:
        raise ValueError("economy region input must have one row per region")
    if "region_id" in names and region_input.column("region_id").to_pylist() != list(range(n)):
        raise ValueError("economy region input rows must follow world.regions")
    for slot in range(3):
        column = f"resource_type_{slot}"
        if column in names:
            types = region_input.column(column).to_pylist()
            if [int(t) for t in types] != [int(r.resource_types[slot]) for r in world.regions]:
                raise ValueError(f"economy region input {column} does not match world.regions")
    caps = harvest_caps(world) if enforce_cap(world) else {}
    for slot, name in enumerate(CAP_COLUMNS):
        values = [caps.get((rid, slot)) for rid in range(n)]
        region_input = region_input.append_column(name, pa.array(values, type=pa.float32()))
    farmers = _farmers_by_region(snapshot, n)
    offered = {}
    for rid, slot in timber_slots(world):
        column = f"resource_yield_{slot}"
        if column in names:
            goods_yield = region_input.column(column)[rid].as_py()
        else:
            from chronicler.experimental.fisheries import economy_yield
            goods_yield = economy_yield(world, world.regions[rid], slot)
        possible = None if farmers is None else bool(goods_yield and goods_yield > 0.0 and farmers[rid] > 0)
        offered[(rid, slot)] = (caps.get((rid, slot)), possible)
    state._offered = offered
    return region_input


def offered_caps(world) -> dict | None:
    """A copy of what this turn's prepare offered: ``{(region, slot): (cap,
    harvest possible)}`` (cap None under the ablation); None outside Phase 2."""
    state = _state(world)
    offered = getattr(state, "_offered", None) if state is not None else None
    return dict(offered) if offered is not None else None


def tighten_harvest_caps(world, region_input, limits: dict):
    """Lower this turn's ``timber_harvest_cap_{slot}`` to external rule limits.

    The interface for rules that restrict the harvest (L8,
    :mod:`chronicler.commons_rules`). Call after :func:`prepare_phase2` in the
    same Phase 2. ``limits`` maps a timber slot offered this turn, (region
    index, slot), to a finite non-negative limit; its column value becomes the
    float32 floor of ``min(value, limit)`` (a null value, no stock cap under
    the ablation, becomes the limit). Never raises a cap and changes no state:
    the stock's account still records and checks the stock cap it offered, and
    the caller checks its own limit after the tick.
    """
    import pyarrow as pa

    offered = offered_caps(world)
    if offered is None:
        raise RuntimeError("tighten_harvest_caps requires this turn's prepared timber caps")
    names = region_input.schema.names
    for slot, name in enumerate(CAP_COLUMNS):
        targets = {rid: limit for (rid, s), limit in limits.items() if s == slot}
        if not targets:
            continue
        values = region_input.column(names.index(name)).to_pylist()
        for rid, limit in targets.items():
            if (rid, slot) not in offered:
                raise ValueError(f"region {rid} slot {slot} is not a timber slot offered this turn")
            if not isinstance(limit, (int, float)) or not math.isfinite(limit) or limit < 0.0:
                raise ValueError(f"invalid timber harvest limit {limit!r}")
            floor = _f32_floor(float(limit))
            values[rid] = floor if values[rid] is None else min(values[rid], floor)
        region_input = region_input.set_column(names.index(name), name, pa.array(values, type=pa.float32()))
    return region_input


def rollback_phase2(world) -> None:
    """A failed Phase 2 charged nothing; forget what prepare offered."""
    state = _state(world)
    if state is not None:
        state._offered = None


def _realized(economy_result, region, slot: int) -> float:
    outputs = getattr(economy_result, "slot_output", None) or {}
    if region.name not in outputs:
        raise RuntimeError("the timber stock requires the economy's slot output "
                           f"(missing for region {region.name!r})")
    value = float(outputs[region.name][slot])
    if not math.isfinite(value) or value < 0.0:
        raise RuntimeError(f"invalid timber output {value!r} in region {region.name!r}")
    return value


def _check_row(row: TimberLedgerRow) -> None:
    expected = math.fsum([row.opening, -row.cleared, -(row.extraction - row.overdraft),
                          row.regrowth, -row.removed])
    scale = max(1.0, row.opening, row.capacity, row.extraction)
    if abs(expected - row.stock) > LEDGER_TOLERANCE * scale:
        raise RuntimeError(f"timber ledger does not close for region {row.region_id} slot {row.slot}: "
                           f"{expected!r} != {row.stock!r}")
    if row.overdraft > row.extraction or (row.cap is not None and row.extraction > row.cap):
        raise RuntimeError(f"timber extraction exceeds the stock in region {row.region_id} slot {row.slot}")
    if row.stock > max(row.capacity, 0.0) * (1.0 + LEDGER_TOLERANCE) + LEDGER_TOLERANCE:
        raise RuntimeError(f"timber stock above capacity in region {row.region_id} slot {row.slot}")


def settle_slot(world, rid: int, slot: int, opening: float, extraction: float,
                *, enforced: bool, possible: bool | None = None) -> TimberLedgerRow:
    """One slot's account (cleared, extraction, regrowth); pure.

    ``possible``: whether the economy could harvest at all (positive yield and
    farmers, observed at prepare); it decides whether a zero cap bound."""
    region = world.regions[rid]
    capacity = effective_capacity(region, slot)
    available = min(opening, capacity)
    cleared = opening - available
    cap = _f32_floor(available) if enforced else None
    if cap is not None and extraction > cap:
        raise RuntimeError(
            f"the economy harvested {extraction!r} timber in region {region.name!r} slot {slot} "
            f"against a cap of {cap!r}; the native extension must apply timber_harvest_cap_{slot}")
    overdraft = max(0.0, extraction - available)
    after = available - (extraction - overdraft)
    gate = water_gate_open(world, region)
    grown = regrowth(after, capacity, gate)
    stock = min(after + grown, capacity)
    if cap is None:
        capped = None
    elif cap > 0.0:
        capped = extraction >= cap
    else:
        capped = possible  # nothing standing: it bound wherever a harvest was possible
    return TimberLedgerRow(
        region_id=rid, slot=slot, opening=opening, cleared=cleared, extraction=extraction,
        overdraft=overdraft, regrowth=grown, removed=0.0, stock=stock,
        capacity=capacity, cap=cap, capped=capped, water_gate_open=gate,
    )


def finish_phase2(world, economy_result, agent_bridge, acc) -> list:
    """Settle every timber slot's account for this turn; commits atomically."""
    state = _state(world)
    if state is None:
        return []
    offered, state._offered = state._offered, None
    if not state.enabled:
        return []
    if state.ledger_turn is not None and state.ledger_turn >= world.turn:
        raise RuntimeError(f"timber stock already settled turn {state.ledger_turn}")
    enforced = enforce_cap(world)
    opening = _opening(world, state)
    if offered is not None and set(offered) != set(opening):
        raise RuntimeError("timber slots changed between prepare and finish")
    rows: list[TimberLedgerRow] = []
    for (rid, slot), stock in opening.items():
        extraction = _realized(economy_result, world.regions[rid], slot)
        possible = offered[(rid, slot)][1] if offered is not None else None
        row = settle_slot(world, rid, slot, stock, extraction, enforced=enforced, possible=possible)
        if offered is not None and offered[(rid, slot)][0] != row.cap:
            raise RuntimeError("the timber harvest cap changed between prepare and finish")
        rows.append(row)
    for held in state.stocks:
        if (held.region_id, held.slot) not in opening:
            # The slot is no longer timber (or its region is gone): its stock leaves.
            rows.append(TimberLedgerRow(
                region_id=held.region_id, slot=held.slot, opening=held.stock, cleared=0.0,
                extraction=0.0, overdraft=0.0, regrowth=0.0, removed=held.stock, stock=0.0,
                capacity=0.0, cap=None, capped=None, water_gate_open=False,
            ))
    rows.sort(key=lambda row: (row.region_id, row.slot))
    for row in rows:
        _check_row(row)
    totals = state.totals
    new_totals = TimberTotals(
        observed_turns=totals.observed_turns + 1,
        extraction=math.fsum([totals.extraction, *(r.extraction for r in rows)]),
        overdraft=math.fsum([totals.overdraft, *(r.overdraft for r in rows)]),
        regrowth=math.fsum([totals.regrowth, *(r.regrowth for r in rows)]),
        cleared=math.fsum([totals.cleared, *(r.cleared for r in rows)]),
        removed=math.fsum([totals.removed, *(r.removed for r in rows)]),
        capped_slot_turns=totals.capped_slot_turns + sum(1 for r in rows if r.capped),
    )
    # Commit.
    state.stocks = [TimberSlotStock(region_id=r.region_id, slot=r.slot, stock=r.stock)
                    for r in rows if (r.region_id, r.slot) in opening]
    state.ledger = rows
    state.ledger_turn = world.turn
    state.totals = new_totals
    return []


# --- Protocol: observation ------------------------------------------------------

_FLOWS = ("opening", "cleared", "extraction", "overdraft", "regrowth", "removed", "stock", "capacity")


def snapshot_summary(world) -> dict:
    """Copied record of the completed turn's accounts; never live state.

    ``observed`` is False (rows and totals None, not zero) when no account was
    settled in the completed turn (no economy tick, or the stock was enabled
    after it).
    """
    state = _state(world)
    source_turn = world.turn - 1
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "units": "timber_goods",
        "source_turn": source_turn,
        "completed_turn": world.turn,
        "enforce_cap": enforce_cap(world),
        "parameters": {"regrowth_rate": REGROWTH_RATE, "seed_fraction": SEED_FRACTION,
                       "reference_crews_at_msy": REFERENCE_CREWS_AT_MSY},
        "observed": False, "regions": None, "totals": None,
    }
    if state is None or state.ledger_turn != source_turn:
        return record
    rows = [row.model_dump() for row in state.ledger]
    totals: dict[str, Any] = {key: math.fsum(row[key] for row in rows) for key in _FLOWS}
    totals["slots"] = len(rows)
    totals["capped_slots"] = sum(1 for row in rows if row["capped"])
    record.update(observed=True, regions=rows, totals=totals)
    return record
