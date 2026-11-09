"""Default-off public granary assets, with paid aggregate construction work.

Assumptions are fixed modeling choices, not calibrated policy defaults. Enabling
endows each existing granary at condition 1 with capacity max(existing grain,
4 * current Phase-2 food demand). A tick then wears condition by 0.01. Effective
capacity scales with condition and the normal storage loss increases by up to
0.07 at condition zero. Neglect requests no work. Maintain spends four delivered
farmer-equivalent work to restore 0.10 condition; expand spends twelve to add
max(4, 25% of built capacity). Each delivered work costs one timber and two
whole treasury units, rounded up per region. Work budget is capped at four per
region per turn. Unfinished work persists with the asset through owner changes.

`prepare_storage_work` holds only free physical timber before native input is
packed, after merchant commitments. `finish_storage_work` uses authoritative
native work actually delivered, pays for it and returns unused timber only
after native economy execution. `rollback_storage_work` restores held timber
if that call fails; it does not promise rollback of a native kernel. The caller
must always finish or rollback a plan before another turn or checkpoint.

RS2 seam (``--repair-projects``; inert otherwise): a region whose granary has
an open repair project has its ordinary request suspended for the turn (the
plan's ``suspended`` regions), and the native work delivered there belongs to
the project, which plans, holds timber for and pays it itself.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import json
import struct
from typing import Sequence

from chronicler.grain_storage_state import GrainStorageState, StorageAsset, StoragePolicy, StorageReceipt

ENDOWMENT_DEMAND_TURNS = 4.0
CONDITION_WEAR = 0.01
EXTRA_SPOILAGE = 0.07
REPAIR_WORK = 4.0
REPAIR_GAIN = 0.10
EXPANSION_WORK = 12.0
EXPANSION_FRACTION = 0.25
EXPANSION_MINIMUM = 4.0
TIMBER_PER_WORK = 1.0
COINS_PER_WORK = 2.0
MAX_WORK_BUDGET = 4.0


def _state(world):
    from chronicler.grain_reserves_state import grain_reserves_on
    if not grain_reserves_on(world):
        return None
    return getattr(world.grain_reserves, "storage", None)


def enable_storage(world) -> GrainStorageState:
    """Enable without fabricating demand: initial capacity is fixed at first tick."""
    from chronicler.grain_reserves_state import grain_reserves_on
    if not grain_reserves_on(world):
        raise ValueError("public granaries must be enabled before storage assets")
    # Granaries are normally populated lazily at Phase 2; storage can be
    # enabled earlier, immediately after enabling the reserve feature.
    from chronicler.grain_reserves import _ensure
    _ensure(world)
    state = _state(world)
    if state is None:
        state = GrainStorageState(assets=[None for _ in world.regions],
                                  policies=[StoragePolicy() for _ in world.regions])
        world.grain_reserves.storage = state
    _validate_shape(world, state)
    return state


def _validate_shape(world, state):
    if len(state.assets) != len(world.regions) or len(state.policies) != len(world.regions):
        raise ValueError("storage asset and policy arrays must match world regions")
    if len(world.grain_reserves.granaries) != len(world.regions):
        raise ValueError("granary array must match world regions")


def set_storage_policy(world, region: int, policy: str, work_budget: float) -> None:
    state = _state(world)
    if state is None:
        raise ValueError("storage assets are disabled")
    _validate_shape(world, state)
    if not 0 <= region < len(world.regions):
        raise ValueError("invalid storage region")
    if getattr(state, "_active_plan", None) is not None:
        raise RuntimeError("cannot change storage policy during a pending plan")
    state.policies[region] = StoragePolicy(policy=policy, work_budget=work_budget)


def _f32_floor(value: float) -> float:
    """Never reserve less than the f32 request actually handed to native code."""
    if value <= 0:
        return 0.0
    packed = struct.pack("<f", value)
    result = struct.unpack("<f", packed)[0]
    if result > value:
        bits = struct.unpack("<I", packed)[0] - 1
        result = struct.unpack("<f", struct.pack("<I", bits))[0]
    return result


@dataclass
class _WorkRow:
    region: int
    owner: int
    controller: str | None
    asset: StorageAsset
    policy: str
    request: float
    held: float


@dataclass
class StorageWorkPlan:
    world_id: int
    state: GrainStorageState | None
    turn: int
    rows: list[_WorkRow]
    requests: list[float]
    status: str = "pending"
    suspended: frozenset = frozenset()


def _repair_suspended(world) -> frozenset:
    """RS2 seam: regions under an open granary repair project (empty unless
    ``--repair-projects`` is active)."""
    if getattr(getattr(world, "livelihoods", None), "repair_projects", None) is None:
        return frozenset()
    from chronicler.repair_projects import storage_suspended_regions
    return storage_suspended_regions(world)


def prepare_storage_work(world, food_demand: Sequence[float], *, acc=None, simulator=None,
                         commitments=None) -> StorageWorkPlan:
    """Reserve physical timber; provide requests in world-region order.

    Demand is the current authoritative region-aligned food demand, not a
    model-population estimate. A hybrid caller must supply its live simulator,
    or an already validated commitments mapping for detached pure tests.
    No treasury is charged until finish. Calls are paired and non-reentrant.
    """
    n = len(world.regions)
    state = _state(world)
    if state is None or world.agent_mode in (None, "off"):
        return StorageWorkPlan(id(world), None, world.turn, [], [0.0] * n)
    _validate_shape(world, state)
    if getattr(state, "_active_plan", None) is not None:
        raise RuntimeError("storage work plan already pending")
    if state.receipt_turn == world.turn:
        raise RuntimeError("storage work already completed for this turn")
    if len(food_demand) != n or any(not math.isfinite(x) or x < 0 for x in food_demand):
        raise ValueError("storage requires finite nonnegative region-aligned food demand")
    if commitments is None:
        if world.agent_mode == "hybrid":
            if simulator is None:
                raise ValueError("hybrid storage requires native stockpile commitments")
            from chronicler.mutual_aid import read_stockpile_commitments
            commitments = read_stockpile_commitments(world, simulator)
        else:
            commitments = {}
    from chronicler.mutual_aid import _treasury_budget
    index = {c.name: i for i, c in enumerate(world.civilizations)}
    budgets = [max(0, math.floor(_treasury_budget(world, c, acc))) for c in world.civilizations]
    suspended = _repair_suspended(world)
    rows = []
    for rid, (region, granary, policy) in enumerate(zip(
            world.regions, world.grain_reserves.granaries, state.policies, strict=True)):
        owner = index.get(region.controller, -1)
        asset = state.assets[rid]
        if asset is None:
            asset = StorageAsset(capacity=max(float(granary.grain),
                                            ENDOWMENT_DEMAND_TURNS * food_demand[rid]), owner=owner)
        else:
            asset = asset.model_copy(deep=True)
        if (asset.repair_progress >= REPAIR_WORK or asset.expansion_progress >= EXPANSION_WORK):
            raise ValueError("storage work progress exceeds a completed batch")
        timber = float(region.stockpile.goods.get("timber", 0.0))
        committed = float(commitments.get(region.name, {}).get("timber", 0.0))
        if not all(math.isfinite(x) and x >= 0 for x in (timber, committed)):
            raise ValueError("invalid timber stock or merchant commitment")
        remaining = 0.0
        if owner >= 0 and policy.policy == "maintain" and asset.condition < 1.0:
            remaining = REPAIR_WORK - asset.repair_progress
        elif owner >= 0 and policy.policy == "expand":
            remaining = EXPANSION_WORK - asset.expansion_progress
        if rid in suspended:
            remaining = 0.0
        amount = 0.0
        if remaining > 0:
            amount = _f32_floor(min(policy.work_budget, remaining,
                                    max(0.0, timber - committed) / TIMBER_PER_WORK,
                                    budgets[owner] / COINS_PER_WORK))
            budgets[owner] -= math.ceil(amount * COINS_PER_WORK)
        rows.append(_WorkRow(rid, owner, region.controller, asset, policy.policy,
                             amount, amount * TIMBER_PER_WORK))
    plan = StorageWorkPlan(id(world), state, world.turn, rows, [r.request for r in rows], suspended=suspended)
    for row in rows:
        if row.held:
            goods = world.regions[row.region].stockpile.goods
            goods["timber"] -= row.held
    state._active_plan = plan
    return plan


def _check_plan(world, plan):
    if plan.world_id != id(world) or plan.turn != world.turn or plan.status != "pending":
        raise ValueError("storage plan does not match this world, turn or lifecycle")
    if plan.state is not None and (_state(world) is not plan.state or plan.state._active_plan is not plan):
        raise ValueError("storage plan no longer matches the active asset state")


def rollback_storage_work(world, plan: StorageWorkPlan) -> None:
    _check_plan(world, plan)
    for row in plan.rows:
        if row.held:
            goods = world.regions[row.region].stockpile.goods
            goods["timber"] = goods.get("timber", 0.0) + row.held
    if plan.state is not None:
        plan.state._active_plan = None
    plan.status = "rolled_back"


def finish_storage_work(world, plan: StorageWorkPlan, delivered: Sequence[float], *, acc=None) -> None:
    """Charge delivered work and complete its asset batches after native success."""
    _check_plan(world, plan)
    if len(delivered) != len(plan.requests):
        raise ValueError("storage delivered work must match region count")
    if plan.suspended:
        delivered = [0.0 if rid in plan.suspended else x for rid, x in enumerate(delivered)]
    if any(not math.isfinite(x) or x < 0 or x > request
           for x, request in zip(delivered, plan.requests, strict=True)):
        raise ValueError("storage delivered work must be finite and within request")
    if plan.state is None:
        if any(delivered):
            raise ValueError("disabled storage cannot deliver work")
        plan.status = "finished"
        return
    from chronicler.mutual_aid import _treasury_budget
    bills = [0] * len(world.civilizations)
    for row, work in zip(plan.rows, delivered, strict=True):
        if world.regions[row.region].controller != row.controller:
            raise ValueError("storage owner changed while work was pending")
        if row.owner >= 0:
            bills[row.owner] += math.ceil(work * COINS_PER_WORK)
    if any(bills[i] > _treasury_budget(world, civ, acc) for i, civ in enumerate(world.civilizations)):
        raise ValueError("storage funds changed while work was pending")
    receipts, assets = [], []
    for row, work in zip(plan.rows, delivered, strict=True):
        asset = row.asset
        before_condition, before_capacity = asset.condition, asset.capacity
        asset.owner = row.owner
        asset.condition = max(0.0, asset.condition - CONDITION_WEAR)
        if row.policy == "maintain" and work:
            asset.repair_progress += work
            if asset.repair_progress >= REPAIR_WORK:
                asset.repair_progress -= REPAIR_WORK
                asset.condition = min(1.0, asset.condition + REPAIR_GAIN)
        elif row.policy == "expand" and work:
            asset.expansion_progress += work
            if asset.expansion_progress >= EXPANSION_WORK:
                asset.expansion_progress -= EXPANSION_WORK
                asset.capacity += max(EXPANSION_MINIMUM, asset.capacity * EXPANSION_FRACTION)
        used = work * TIMBER_PER_WORK
        returned = row.held - used
        if returned:
            goods = world.regions[row.region].stockpile.goods
            goods["timber"] = goods.get("timber", 0.0) + returned
        cost = math.ceil(work * COINS_PER_WORK)
        receipts.append(StorageReceipt(turn=plan.turn, region=row.region, owner=row.owner,
            policy=row.policy, requested=row.request, delivered=work, timber_reserved=row.held,
            timber_used=used, timber_returned=returned, treasury_paid=cost,
            condition_before=before_condition, condition_after=asset.condition,
            capacity_before=before_capacity, capacity_after=asset.capacity,
            repair_progress=asset.repair_progress, expansion_progress=asset.expansion_progress))
        assets.append(asset)
    for i, cost in enumerate(bills):
        if cost:
            civ = world.civilizations[i]
            if acc is None:
                civ.treasury -= cost
            else:
                acc.add(i, civ, "treasury", -cost, "keep")
    plan.state.assets = assets
    plan.state.receipts = receipts
    plan.state.receipt_turn = plan.turn
    plan.state._active_plan = None
    plan.status = "finished"


def storage_limit(world, region: int) -> float | None:
    state = _state(world)
    if state is None or world.agent_mode in (None, "off"):
        return None
    _validate_shape(world, state)
    asset = state.assets[region]
    if asset is None:
        raise RuntimeError("storage assets not initialized before granary opening")
    return asset.capacity * asset.condition


def storage_spoilage(world, region: int, default_rate: float) -> float:
    state = _state(world)
    if state is None or world.agent_mode in (None, "off"):
        return default_rate
    _validate_shape(world, state)
    asset = state.assets[region]
    if asset is None:
        raise RuntimeError("storage assets not initialized before granary opening")
    return min(1.0, max(0.0, default_rate + EXTRA_SPOILAGE * (1.0 - asset.condition)))


@dataclass(frozen=True, slots=True)
class StorageSnapshot:
    """Frozen capture; `as_dict` provides a fresh JSON-compatible export."""
    _payload: str

    def as_dict(self) -> dict:
        return json.loads(self._payload)


def storage_snapshot(world) -> StorageSnapshot | None:
    """Freeze current recorded state without reconciling or mutating the world."""
    state = _state(world)
    return None if state is None else StorageSnapshot(state.model_dump_json())


def settle_storage_capacity(world) -> None:
    """Late Phase10: cap targets and conservatively return excess to the market.

    Public release/spoilage occurred in Phase2. Arrivals settle before this
    boundary; capacity cannot erase already-paid cargo. These returned goods
    reach native consumption next turn, never retrospectively this turn.
    """
    state = _state(world)
    if state is None or world.agent_mode in (None, "off"):
        return
    _validate_shape(world, state)
    from chronicler.grain_reserves import _flows, _bump
    from chronicler.grain_reserves_state import ReserveFlow, STORAGE_RETURNED
    receipts = {r.region: r for r in state.receipts} if state.receipt_turn == world.turn else {}
    flows = _flows(world, world.grain_reserves)
    for rid, (region, granary) in enumerate(zip(world.regions, world.grain_reserves.granaries, strict=True)):
        limit = storage_limit(world, rid)
        requested = granary.target
        granary.target = min(granary.target, limit)
        excess = max(0.0, granary.grain - limit)
        if excess:
            before = granary.grain
            granary.grain -= excess
            goods = region.stockpile.goods
            goods["grain"] = goods.get("grain", 0.0) + excess
            flows.append(ReserveFlow(kind=STORAGE_RETURNED, region=rid, source=rid,
                                     amount=excess, buyer=granary.owner, seller=granary.owner,
                                     before=before, after=granary.grain))
            _bump(world.grain_reserves, "storage_returned", excess)
        if rid in receipts:
            receipts[rid].target_requested = requested
            receipts[rid].target_feasible = granary.target
            receipts[rid].capacity_returned += excess
