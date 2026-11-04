"""Opt-in paid academy supplies and separately measured native teaching work.

The earlier immediate-purchase/count-based settlement was a partial prototype:
Phase 10 alive scholar counts are capacity upper bounds, not available work.
Now one learner-equivalent consumes one purchased craft; one actual native
scholar-day serves eight learner-equivalents. These fixed units are assumptions,
not calibrated efficacy. Purchases and work take place in separate phases/turns.
"""
from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
import math
import struct
from types import SimpleNamespace

from chronicler.learning_services_state import (
    AcademyMaterialInventory, AcademyProcurementReceipt, AcademySupplyLoss,
    AcademyTeachingReceipt, LearningServicesState,
)
from chronicler.scholarship_state import ACADEMY, scholarship_on
from chronicler.war.common import add_stat, projected_treasury

LEARNERS_PER_SCHOLAR = 8.0
CRAFTS_PER_LEARNER = 1.0


@dataclass(frozen=True)
class AcademyUpkeepObservation:
    seat_id: int
    region: int
    founder: int
    founded_turn: int
    seat_name: str
    lord: int
    source_turn: int
    due: int
    paid: int
    satisfied: bool


@dataclass(frozen=True)
class LearningCounts:
    """A dated native alive-count snapshot; staff are only an upper bound."""
    source_turn: int
    scholars: tuple[int, ...]
    learners: tuple[int, ...]


def _int(value):
    return type(value) is int and value >= 0


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _identity(seat_id, seat):
    return (seat_id, seat.region, seat.founder, seat.founded_turn, seat.name)


def _asset_identity(asset):
    return (asset.seat_id, asset.region, asset.founder, asset.founded_turn, asset.seat_name)


def _state(world):
    if not scholarship_on(world):
        return None
    state = getattr(world.scholarship, "learning_services", None)
    if state is not None and not isinstance(state, LearningServicesState):
        raise ValueError("invalid learning services state")
    return state


def learning_services_active(world):
    """Enabled and backed by the hybrid native economy/work runtime."""
    state = _state(world)
    return state is not None and getattr(state, "enabled", True) and getattr(world, "agent_mode", None) == "hybrid"


def set_learning_services_enabled(world, enabled: bool):
    """Pause without deleting held materials; enabling requires scholarship."""
    if type(enabled) is not bool:
        raise ValueError("academy services enabled must be boolean")
    if not scholarship_on(world):
        if enabled:
            raise ValueError("academy services require scholarship")
        return
    state = _state(world)
    if state is None:
        if enabled:
            world.scholarship.learning_services = LearningServicesState()
        return
    if getattr(state, "_active_plan", None) is not None:
        raise RuntimeError("cannot toggle academy services while work is pending")
    if getattr(state, "enabled", True) != enabled:
        state.enabled = enabled


def _live_academies(world):
    """Refuse duplicate live hosts before any allocation or inventory change."""
    seen, rows = set(), []
    for seat_id, seat in enumerate(world.scholarship.seats):
        if seat.kind != ACADEMY or seat.fallen_turn is not None or seat.level <= 0:
            continue
        if not _int(seat.region) or seat.region >= len(world.regions):
            raise ValueError("invalid live academy region")
        if seat.region in seen:
            raise ValueError("duplicate live academy host")
        seen.add(seat.region)
        rows.append((seat_id, seat))
    return rows


def _hosted(world, seat):
    return (type(seat.lord) is int and 0 <= seat.lord < len(world.civilizations)
            and world.regions[seat.region].controller == world.civilizations[seat.lord].name)


def _validated_counts(counts, source_turn, n):
    if counts is None or not isinstance(counts, LearningCounts) or counts.source_turn != source_turn:
        return None
    if (len(counts.scholars) != n or len(counts.learners) != n
            or any(not _int(v) for v in (*counts.scholars, *counts.learners))):
        raise ValueError("invalid native learning count upper bounds")
    return counts


def learning_counts_from_snapshot(snapshot, source_turn: int, region_count: int):
    """Read a pre-Phase 2 native batch without fetching another snapshot.

    Null, noninteger, malformed or out-of-range columns return unknown. These
    are alive scholar/non-scholar upper bounds, not a roster of eligible staff.
    """
    if not _int(source_turn) or not _int(region_count):
        return None
    from chronicler.columnar import batch_arrays
    arrays = batch_arrays(snapshot, ("region", "occupation"))
    if arrays is None:
        return None
    regions, occupations = arrays
    if (regions.dtype.kind not in "iu" or occupations.dtype.kind not in "iu"
            or ((regions < 0) | (regions >= region_count)).any()
            or ((occupations < 0) | (occupations > 4)).any()):
        return None
    import numpy as np
    staff = np.bincount(regions[occupations == 3].astype(np.int64, copy=False), minlength=region_count)
    learners = np.bincount(regions[occupations != 3].astype(np.int64, copy=False), minlength=region_count)
    return LearningCounts(source_turn, tuple(map(int, staff)), tuple(map(int, learners)))


def native_learning_counts(phase10, source_turn: int, region_count: int):
    """Read a dated Phase 10 snapshot as upper bounds for purchasing only."""
    rows = getattr(phase10, "agents", None)
    if (getattr(phase10, "source_turn", None) != source_turn or rows is None
            or getattr(getattr(rows, "stamp", None), "source_turn", None) != source_turn
            or getattr(getattr(rows, "stamp", None), "stage", None) != "phase10_entry"):
        return None
    return learning_counts_from_snapshot(getattr(rows, "batch", None), source_turn, region_count)


def _validate_inventory(asset):
    upkeep = (asset.upkeep_source_turn, asset.upkeep_lord, asset.upkeep_due,
              asset.upkeep_amount_paid, asset.upkeep_satisfied)
    if not all(value is None for value in upkeep):
        source, lord, due, paid, satisfied = upkeep
        if (not all(_int(x) for x in (source, lord, due, paid))
                or type(satisfied) is not bool or (satisfied and paid != due)
                or (not satisfied and paid != 0)):
            raise ValueError("invalid academy upkeep evidence")
    vals = (asset.held, asset.purchased_total, asset.used_total, asset.lost_total)
    if all(v is None for v in vals):
        return
    if any(v is None or not _number(v) for v in vals):
        raise ValueError("invalid academy material inventory")
    if asset.retired and asset.held != 0:
        raise ValueError("retired academy cannot hold accounted materials")
    if not math.isclose(asset.purchased_total - asset.used_total - asset.lost_total,
                        asset.held, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError("academy material inventory does not balance")


def _upkeep_for(world, seat_id, seat, observations):
    row = observations.get(seat_id) if isinstance(observations, dict) else None
    if not isinstance(row, AcademyUpkeepObservation):
        return None
    if ((row.seat_id, row.region, row.founder, row.founded_turn, row.seat_name,
         row.lord, row.source_turn) != (*_identity(seat_id, seat), seat.lord, world.turn)
            or not _int(row.due) or not _int(row.paid) or type(row.satisfied) is not bool
            or (row.satisfied and row.paid != row.due)
            or (not row.satisfied and row.paid != 0)):
        return None
    return row



def reconcile_learning_assets(world):
    """Record loss once when a stored seat falls/is replaced, even if paused.

    This performs no purchase or work and is also safe in an agent-off world.
    The root coordinator should call it after scholarship lifecycle changes.
    """
    state = _state(world)
    if state is None:
        return ()
    if getattr(state, "_active_plan", None) is not None:
        raise RuntimeError("cannot reconcile while teaching work is pending")
    live = _live_academies(world)
    existing = getattr(state, "inventories", None)
    if existing is None:
        return ()
    assets = [a.model_copy(deep=True) for a in existing]
    for asset in assets:
        _validate_inventory(asset)
    active = [_asset_identity(a) for a in assets if not a.retired]
    if len(active) != len(set(active)):
        raise ValueError("duplicate live academy inventory")
    live_ids = {_identity(i, s) for i, s in live}
    losses = []
    for asset in assets:
        if asset.retired or _asset_identity(asset) in live_ids:
            continue
        lost = asset.held
        if lost is not None:
            asset.lost_total += lost
            asset.held = 0.0
        asset.retired = True
        losses.append(AcademySupplyLoss(seat_id=asset.seat_id, region=asset.region,
            founder=asset.founder, founded_turn=asset.founded_turn, seat_name=asset.seat_name,
            source_turn=world.turn, held_before=lost, lost=lost, held_after=asset.held))
    if losses:
        state.inventories = assets
        previous = [r for r in (getattr(state, "supply_losses", None) or []) if r.source_turn == world.turn]
        state.supply_losses = previous + losses
    elif getattr(state, "supply_losses", None) and state.supply_losses[0].source_turn < world.turn:
        state.supply_losses = []
    return tuple(losses)

def procure_learning_supplies(world, phase10, actual_upkeep, *, commitments, acc=None):
    """Phase 10: buy bounded crafts into the institution, never teach from them now.

    Requires this turn's real upkeep evidence, current craft price, dated
    native count upper bounds and known merchant commitments. A domestic
    purchase debits market crafts and projected treasury exactly once.
    """
    state = _state(world)
    if state is None:
        return ()
    if not learning_services_active(world):
        reconcile_learning_assets(world)
        return ()
    if getattr(state, "_active_plan", None) is not None:
        raise RuntimeError("cannot procure while teaching work is pending")
    if not _int(world.turn) or (getattr(state, "last_procurement_turn", None) is not None
                                and world.turn <= state.last_procurement_turn):
        raise ValueError("academy procurement already settled or out of order")
    live = _live_academies(world)
    counts = native_learning_counts(phase10, world.turn, len(world.regions))
    economy = getattr(phase10, "economy", None) if getattr(phase10, "source_turn", None) == world.turn else None
    initial = getattr(state, "inventories", None)
    unknown_legacy = initial is None and (getattr(state, "last_source_turn", None) is not None
                                          or bool(getattr(state, "receipts", [])))
    inventories = [] if initial is None else [a.model_copy(deep=True) for a in initial]
    for asset in inventories:
        _validate_inventory(asset)
    active = {_asset_identity(a): a for a in inventories if not a.retired}
    if len(active) != sum(not a.retired for a in inventories):
        raise ValueError("duplicate live academy inventory")
    live_ids = {_identity(i, s) for i, s in live}
    losses = []
    for asset in inventories:
        if asset.retired or _asset_identity(asset) in live_ids:
            continue
        lost = asset.held
        if lost is not None:
            asset.lost_total += lost
            asset.held = 0.0
        asset.retired = True
        losses.append(AcademySupplyLoss(seat_id=asset.seat_id, region=asset.region,
            founder=asset.founder, founded_turn=asset.founded_turn, seat_name=asset.seat_name,
            source_turn=world.turn, held_before=lost, lost=lost, held_after=asset.held))
    for seat_id, seat in live:
        ident = _identity(seat_id, seat)
        if ident not in active:
            init = None if unknown_legacy else 0.0
            asset = AcademyMaterialInventory(seat_id=seat_id, region=seat.region, founder=seat.founder,
                founded_turn=seat.founded_turn, seat_name=seat.name, held=init,
                purchased_total=init, used_total=init, lost_total=init)
            inventories.append(asset)
            active[ident] = asset
    ctx = SimpleNamespace(world=world, acc=acc)
    budgets = [max(0, int(projected_treasury(ctx, civ))) for civ in world.civilizations]
    receipts, changes = [], []
    for seat_id, seat in live:
        asset = active[_identity(seat_id, seat)]
        region = world.regions[seat.region]
        hosted = _hosted(world, seat)
        upkeep = _upkeep_for(world, seat_id, seat, actual_upkeep) if hosted else None
        asset.upkeep_source_turn = upkeep.source_turn if upkeep else None
        asset.upkeep_lord = upkeep.lord if upkeep else None
        asset.upkeep_due = upkeep.due if upkeep else None
        asset.upkeep_amount_paid = upkeep.paid if upkeep else None
        asset.upkeep_satisfied = upkeep.satisfied if upkeep else None
        staff = counts.scholars[seat.region] if counts else None
        learners = counts.learners[seat.region] if counts else None
        native_prices = getattr(economy, "market_prices", None)
        prices = native_prices.get(region.name) if isinstance(native_prices, dict) else None
        if prices is None:
            # The Python oracle's own prices are genuine observations too.
            # Native region_goods is empty; an old native binary stays unknown.
            goods = getattr(economy, "region_goods", None)
            prices = getattr(goods.get(region.name), "prices", {}) if isinstance(goods, dict) else {}
        price = prices.get("craft") if isinstance(prices, dict) else None
        price = float(price) if _number(price) and price > 0 else None
        held = commitments.get(region.name, {}).get("crafts") if isinstance(commitments, dict) and isinstance(commitments.get(region.name), dict) else None
        held = float(held) if _number(held) else None
        stock = region.stockpile.goods.get("crafts", 0.0)
        if not _number(stock):
            raise ValueError("invalid crafts market stock")
        stock = float(stock)
        budget = budgets[seat.lord] if hosted else None
        before = asset.held
        requested = 0.0
        if (hosted and upkeep is not None and upkeep.satisfied and staff is not None and learners is not None
                and price is not None and held is not None and before is not None):
            wanted = max(0.0, min(float(learners), staff * LEARNERS_PER_SCHOLAR) * CRAFTS_PER_LEARNER - before)
            requested = min(wanted, max(0.0, stock - held), budget / price)
            while requested > 0 and math.ceil(requested * price) > budget:
                requested = math.nextafter(requested, 0.0)
        cost = math.ceil(requested * price) if requested and price is not None else 0
        if requested:
            asset.held += requested
            asset.purchased_total += requested
            budgets[seat.lord] -= cost
            changes.append((seat.lord, seat.region, requested, cost))
        shortfalls = []
        if not hosted: shortfalls.append("host_not_controlled")
        if upkeep is None: shortfalls.append("upkeep_unknown")
        elif not upkeep.satisfied: shortfalls.append("upkeep_unpaid")
        if counts is None: shortfalls.append("counts_unknown")
        if price is None: shortfalls.append("price_unknown")
        if held is None: shortfalls.append("commitments_unknown")
        if before is None: shortfalls.append("held_unknown")
        receipts.append(AcademyProcurementReceipt(seat_id=seat_id, region=seat.region,
            founder=seat.founder, founded_turn=seat.founded_turn, seat_name=seat.name,
            lord=seat.lord, source_turn=world.turn, upkeep_source_turn=upkeep.source_turn if upkeep else None,
            upkeep_due=upkeep.due if upkeep else None, upkeep_amount_paid=upkeep.paid if upkeep else None,
            upkeep_satisfied=upkeep.satisfied if upkeep else None, scholar_upper_bound=staff,
            learner_upper_bound=learners, craft_price=price, market_stock=stock,
            market_commitments=held, budget_before=budget, held_before=before,
            purchased=requested, paid=cost, held_after=asset.held, shortfalls=tuple(shortfalls)))
    # No financial mutation occurs before the full host/input pass above.
    for lord, rid, amount, cost in changes:
        world.regions[rid].stockpile.goods["crafts"] -= amount
        add_stat(ctx, world.civilizations[lord], "treasury", -cost, "keep")
    state.inventories = inventories
    state.procurement_receipts = receipts
    previous_losses = [r for r in (getattr(state, "supply_losses", None) or [])
                       if r.source_turn == world.turn]
    state.supply_losses = previous_losses + losses
    state.last_procurement_turn = world.turn
    return tuple(receipts)


def learning_inventory_totals(world):
    """Read lifetime opening/purchases/use/loss/closing for the resource ledger.

    The opening endowment is zero for new assets. If any carried legacy
    holdings are unknown, all material totals remain unknown, not partial sums.
    Capture this before and after a turn and difference the cumulative flows.
    """
    state = _state(world)
    if state is None:
        return None
    assets = getattr(state, "inventories", None)
    if assets is None:
        if getattr(state, "last_source_turn", None) is not None or bool(getattr(state, "receipts", [])):
            return {"held": None, "purchased": None, "used": None, "lost": None}
        return {"held": 0.0, "purchased": 0.0, "used": 0.0, "lost": 0.0}
    if any(a.held is None for a in assets):
        return {"held": None, "purchased": None, "used": None, "lost": None}
    for a in assets:
        _validate_inventory(a)
    return {"held": math.fsum(a.held for a in assets),
            "purchased": math.fsum(a.purchased_total for a in assets),
            "used": math.fsum(a.used_total for a in assets),
            "lost": math.fsum(a.lost_total for a in assets)}


def learning_inventory_turn_balance(opening, closing):
    """Difference authoritative snapshots; None means unknown, never zero."""
    if opening is None or closing is None:
        return None
    keys = ("held", "purchased", "used", "lost")
    if any(opening.get(k) is None or closing.get(k) is None for k in keys):
        return {"opening": None, "purchased": None, "used": None, "lost": None, "closing": None}
    for row in (opening, closing):
        if any(not _number(row.get(k)) for k in keys):
            raise ValueError("invalid academy material totals")
    result = {"opening": opening["held"], "closing": closing["held"]}
    for key in ("purchased", "used", "lost"):
        result[key] = closing[key] - opening[key]
        if result[key] < -1e-6:
            raise ValueError("academy material cumulative totals went backward")
    if not math.isclose(result["opening"] + result["purchased"] - result["used"] - result["lost"],
                        result["closing"], rel_tol=0.0, abs_tol=1e-6):
        raise ValueError("academy material turn balance does not reconcile")
    return result


def _f32_floor(value):
    if value <= 0:
        return 0.0
    packed = struct.pack("<f", value)
    result = struct.unpack("<f", packed)[0]
    if result > value:
        bits = struct.unpack("<I", packed)[0] - 1
        result = struct.unpack("<f", struct.pack("<I", bits))[0]
    return result


@dataclass(frozen=True)
class _TeachingEntry:
    seat_id: int
    identity: tuple
    lord: int
    staff: int | None
    learners: int | None
    upkeep_source: int | None
    upkeep_lord: int | None
    upkeep_due: int | None
    upkeep_paid: int | None
    upkeep_satisfied: bool | None
    upkeep_applies: bool | None
    held: float | None
    known: bool
    request: float


@dataclass
class LearningWorkPlan:
    source_turn: int
    requests: tuple[float, ...]
    entries: tuple[_TeachingEntry, ...]
    world_id: int
    state: LearningServicesState
    status: str = "pending"


def prepare_learning_work(world, counts: LearningCounts | None):
    """Before native tick, return region requests and a transient plan.

    Call immediately before the native agent tick (after Phase 9/politics),
    using the already captured Phase 2 native snapshot as a dated upper bound.
    `counts` must be stamped with this turn; absent/stale counts, prior upkeep, or paid inventory yield zero request and
    unknown receipt. The scholar count is an upper bound only. Native
    `prepare_teaching_work` determines actual eligible work. No source IDs or
    materials are reserved by this helper. The caller must cancel/finish both
    native and Python plans before saving a checkpoint.
    """
    state = _state(world)
    n = len(world.regions)
    if state is None or not learning_services_active(world):
        return (0.0,) * n, None
    if getattr(state, "_active_plan", None) is not None:
        raise RuntimeError("academy teaching work already pending")
    if not _int(world.turn) or (getattr(state, "last_service_turn", None) is not None
                                and world.turn <= state.last_service_turn):
        raise ValueError("academy service already settled or out of order")
    live = _live_academies(world)
    counts = _validated_counts(counts, world.turn, n)
    assets = getattr(state, "inventories", None) or []
    for asset in assets:
        _validate_inventory(asset)
    active = {_asset_identity(a): a for a in assets if not a.retired}
    if len(active) != sum(not a.retired for a in assets):
        raise ValueError("duplicate live academy inventory")
    requests = [0.0] * n
    entries = []
    for seat_id, seat in live:
        asset = active.get(_identity(seat_id, seat))
        staff = counts.scholars[seat.region] if counts else None
        learners = counts.learners[seat.region] if counts else None
        up_to_date = asset is not None and asset.upkeep_source_turn == world.turn - 1
        satisfied = asset.upkeep_satisfied if up_to_date else None
        upkeep_applies = (asset.upkeep_lord == seat.lord) if up_to_date else None
        held = asset.held if asset is not None else None
        known = (_hosted(world, seat) and staff is not None and learners is not None
                 and up_to_date and upkeep_applies is True and satisfied is True and held is not None)
        request = (_f32_floor(min(float(staff), learners / LEARNERS_PER_SCHOLAR,
                                   held / (LEARNERS_PER_SCHOLAR * CRAFTS_PER_LEARNER)))
                   if known else 0.0)
        requests[seat.region] = request
        entries.append(_TeachingEntry(seat_id, _identity(seat_id, seat), seat.lord,
            staff, learners, asset.upkeep_source_turn if up_to_date else None,
            asset.upkeep_lord if up_to_date else None, asset.upkeep_due if up_to_date else None,
            asset.upkeep_amount_paid if up_to_date else None, satisfied, upkeep_applies, held, known, request))
    plan = LearningWorkPlan(world.turn, tuple(requests), tuple(entries), id(world), state)
    state._active_plan = plan
    return plan.requests, plan


def learning_work_pending(world):
    state = _state(world)
    return state is not None and getattr(state, "_active_plan", None) is not None


def _check_plan(world, plan):
    if (not isinstance(plan, LearningWorkPlan) or plan.world_id != id(world)
            or plan.source_turn != world.turn or plan.status != "pending"
            or _state(world) is not plan.state or plan.state._active_plan is not plan):
        raise ValueError("academy teaching plan does not match world, turn or lifecycle")


def cancel_learning_work(world, plan):
    _check_plan(world, plan)
    plan.state._active_plan = None
    plan.status = "cancelled"


def _work_rows(result, plan):
    if result is None:
        return None, None
    if not isinstance(result, tuple) or len(result) != 4:
        raise ValueError("invalid native teaching result")
    source, rows, people, dropped = result
    if not _int(source) or source != plan.source_turn or not isinstance(rows, list) or len(rows) != len(plan.requests):
        raise ValueError("invalid native teaching result source or regions")
    if not isinstance(people, list) or len(people) > 128 or not _int(dropped):
        raise ValueError("invalid native teaching receipt bound")
    result_rows = []
    for rid, row in enumerate(rows):
        if not isinstance(row, tuple) or len(row) != 5 or type(row[0]) is not int or row[0] != rid:
            raise ValueError("invalid native teaching region row")
        _, available, requested, reserved, delivered = row
        if (not all(_number(x) for x in (available, requested, reserved, delivered))
                or not math.isclose(requested, plan.requests[rid], rel_tol=0, abs_tol=1e-6)
                or delivered > reserved + 1e-6 or reserved > available + 1e-6
                or reserved > requested + 1e-6):
            raise ValueError("invalid native teaching work bounds")
        result_rows.append((available, reserved, delivered))
    seen = set()
    person_totals = [[0.0, 0.0] for _ in rows]
    for row in people:
        if not isinstance(row, tuple) or len(row) != 4:
            raise ValueError("invalid native teaching person row")
        agent_id, rid, reserved, delivered = row
        if (not _int(agent_id) or agent_id > 2**32 - 1 or agent_id in seen or not _int(rid) or rid >= len(rows)
                or not _number(reserved) or reserved > 1.0 + 1e-6
                or not _number(delivered) or delivered > reserved + 1e-6):
            raise ValueError("invalid native teaching person row")
        seen.add(agent_id)
        person_totals[rid][0] += reserved
        person_totals[rid][1] += delivered
    for rid, (_, reserved, delivered) in enumerate(result_rows):
        for observed, total in zip(person_totals[rid], (reserved, delivered), strict=True):
            tolerance = 1e-6 * max(1.0, total)
            if observed > total + tolerance or (dropped == 0 and abs(observed - total) > tolerance):
                raise ValueError("native teaching person and region work disagree")
    return result_rows, dropped


def finish_learning_work(world, plan, native_result):
    """After the native tick, spend only actual delivered work's paid supplies.

    `native_result` is `(source_turn, region_rows, bounded_agent_rows, dropped)`
    from `get_teaching_work_result`, or None if no authoritative result exists.
    Its scholar-day totals are the actual opportunity cost of teaching work;
    native applies that cost against ordinary scholar income, not as a wage.
    """
    if plan is None:
        if native_result is not None:
            raise ValueError("native teaching result without a Python plan")
        return ()
    _check_plan(world, plan)
    rows, dropped = _work_rows(native_result, plan)
    assets = getattr(plan.state, "inventories", None) or []
    active = {_asset_identity(a): a for a in assets if not a.retired}
    # Validate everything before debiting held goods.
    staged = []
    for entry in plan.entries:
        asset = active.get(entry.identity)
        if entry.held is not None and (asset is None or asset.held != entry.held):
            raise ValueError("academy paid inventory changed during teaching")
        rid = entry.identity[1]
        native = rows[rid] if rows is not None else None
        if not entry.known or native is None:
            work_available = work_reserved = work_delivered = delivered = used = None
        else:
            available, reserved, work_delivered = native
            work_available = available if entry.request > 0 else None
            work_reserved = reserved
            delivered = work_delivered * LEARNERS_PER_SCHOLAR
            used = delivered * CRAFTS_PER_LEARNER
            if used > entry.held + 1e-6 or delivered > entry.learners + 1e-6:
                raise ValueError("native teaching exceeds paid supply or demand")
            if used > entry.held:  # only f32 round-off, not extra work
                used = entry.held
        staged.append((entry, asset, work_available, work_reserved, work_delivered, delivered, used))
    receipts = []
    for entry, asset, available, reserved, work, learners, used in staged:
        if used is not None:
            asset.held -= used
            asset.used_total += used
            _validate_inventory(asset)
        receipts.append(AcademyTeachingReceipt(seat_id=entry.seat_id, region=entry.identity[1],
            founder=entry.identity[2], founded_turn=entry.identity[3], seat_name=entry.identity[4],
            lord=entry.lord, source_turn=plan.source_turn, available_turn=plan.source_turn + 1,
            learner_upper_bound=entry.learners, scholar_upper_bound=entry.staff,
            upkeep_source_turn=entry.upkeep_source, upkeep_lord=entry.upkeep_lord,
            upkeep_due=entry.upkeep_due, upkeep_amount_paid=entry.upkeep_paid,
            upkeep_satisfied=entry.upkeep_satisfied, upkeep_applies=entry.upkeep_applies,
            held_before=entry.held, work_requested=entry.request, work_available=available,
            work_reserved=reserved, work_delivered=work, learners_delivered=learners,
            crafts_used=used, held_after=asset.held if asset is not None else None,
            native_dropped=dropped))
    plan.state.teaching_receipts = receipts
    plan.state.last_service_turn = plan.source_turn
    plan.state._active_plan = None
    plan.status = "finished"
    return tuple(receipts)


def academy_service_fraction(world, seat_id: int, *, turn: int) -> float:
    """Use only the previous completed actual-work receipt for this incarnation."""
    state = _state(world)
    if state is None or not learning_services_active(world):
        return 1.0
    if not _int(seat_id) or seat_id >= len(world.scholarship.seats) or not _int(turn) or turn != world.turn:
        return 0.0
    seat = world.scholarship.seats[seat_id]
    if seat.kind != ACADEMY:
        return 1.0
    if (seat.fallen_turn is not None or seat.level <= 0 or not _int(seat.region)
            or seat.region >= len(world.regions) or not _hosted(world, seat)
            or getattr(state, "last_service_turn", None) != turn - 1):
        return 0.0
    receipts = getattr(state, "teaching_receipts", None) or []
    rows = [r for r in receipts if r.seat_id == seat_id]
    if len(rows) != 1:
        return 0.0
    row = rows[0]
    if ((row.seat_id, row.region, row.founder, row.founded_turn, row.seat_name) != _identity(seat_id, seat)
            or row.source_turn != turn - 1 or row.available_turn != turn
            or row.learner_upper_bound is None or row.learner_upper_bound <= 0
            or row.learners_delivered is None or not _number(row.learners_delivered)
            or row.learners_delivered > row.learner_upper_bound + 1e-6):
        return 0.0
    return min(1.0, row.learners_delivered / row.learner_upper_bound)


def learning_services_snapshot(world):
    """Detached, dated schema-1 view; missing old evidence stays unknown."""
    state = _state(world)
    if state is None:
        return None
    def rows(name):
        value = getattr(state, name, None)
        return None if value is None else [row.model_dump(mode="json") for row in value]
    return {"schema_version": 1, "captured_turn": world.turn,
            "enabled": getattr(state, "enabled", True),
            "active": learning_services_active(world),
            "inventories": rows("inventories"),
            "procurement_receipts": rows("procurement_receipts"),
            "teaching_receipts": rows("teaching_receipts"),
            "supply_losses": rows("supply_losses"),
            "material_balance": deepcopy(getattr(state, "material_balance", None)),
            "totals": learning_inventory_totals(world)}
