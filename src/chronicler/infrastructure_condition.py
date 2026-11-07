"""Infrastructure condition, service and repair (``--infrastructure-condition``, default off).

Connected-world program, lane B3. Design: the Program B audit, section 7.3,
following its sibling-record alternative (``livelihoods.infrastructure_condition``:
the works are not RS2 projects, so RS2's schema, record and viewer stay
unchanged); the lead's decisions in the connected-world roadmap, section 5.2;
integration page ``docs/integration/infrastructure-condition.md``.

Scope. Irrigation works and roads (``KINDS``). Ports are deferred (no
consumer reads the type; maritime treats coastal regions as ports).

Requires ``--agents hybrid``. Modes (``--infrastructure-condition-mode``):

* ``repair`` (default) and ``cost_only`` (RS2's cost control: works plan,
  hold timber, use labour and pay identically, and credit no condition) need
  ``--repair-projects``: the works are repaired by the same authorities, inside
  RS2's own Phase 2 (RS2's ``prepare_phase2``/``finish_phase2`` call this
  module after their own planning and settlement);
* ``record_only``: condition is tracked and recorded, service is forced to
  1.0 and no work opens, so every output except this record equals the
  switch off;
* ``wear_only``: wear, damage and service act and nothing repairs: the
  control that measures repair against the same wear assumption.

Assets. Each active irrigation or road record gets an asset with a stable,
never-reused ``aid`` when first seen (Phase 10 reconciliation, or a damage
hook earlier in the turn), at condition 1.0. It is matched each turn by
``(region, record_index, type, built_turn, builder_civ)``. A record that turns
inactive makes its asset ``inactive`` with the cause read from dated world
state (``scorch``, ``earthquake``, ``depopulation``, else ``unknown``); a
removed record list (supervolcano) makes it ``destroyed``. A rebuild is a new
record and a new asset. Conquest keeps the asset: responsibility moves to the
region's new controller with a dated note (RS2's rule), and an open work is
inherited.

Wear and service (declared, uncalibrated). Every Phase 10 a serving asset
loses ``WEAR[kind]`` condition (irrigation 0.01, the grain-storage rate;
roads 0.005). Damage: ``WAR_DAMAGE`` (0.25, times RS2's tuning key
``repair_projects.war_damage``) at RS2's two existing war hooks (region
conquest, city sack; at most one damage per asset per turn); flood damage
through :func:`flood_damage`, the seam for the watershed's flow mode (no
caller until that mode exists). Service ``s = min(1, condition / 0.5)``.
Condition 0 means ``failed``: the record stays active, so BUILD never
replaces it; it must be repaired.

Consumers, through :func:`service` (exactly 1.0 while off or in
``record_only``, so ``0.10 x 1.0 == 0.10`` keeps the switch-off path
bit-identical): irrigation's arable-capacity bonus
(``economy.arable_capacity``: ``+ FARM_CEILING_IRRIGATION x s``) and the native
``has_irrigation`` flag (``agent_bridge``: active and ``s >= 0.5``); roads'
two-hop trade range (``techniques.extend_trade_routes``, ``resources``'
railways rule) needs ``s >= 0.5``. No transport discount is added.

Works (``repair``/``cost_only``). A work opens in Phase 10 (before the L9
decision) for an asset below ``OPEN_BELOW`` (cause ``wear``) or carrying an
unrepaired damage record (``war``/``flood``), when its region has a
controller. Scope ``(1 - condition) x WORK_PER_CONDITION``; each delivered
unit credits ``1 / WORK_PER_CONDITION`` condition. Inside RS2's Phase 2, after
RS2 planned its own projects:

* Labour: anonymous farmer-equivalent work through the native
  ``granary_work_requested`` column (appended when grain storage is off),
  removed from farming by the native economy as storage work is; the farmers
  are **not paid** (paying named crews needs a treasury-to-agent payment the
  payment seam does not support yet). The column is shared in a fixed order,
  granary -> irrigation -> roads, decided by storage's **actual** request this
  turn: a region where storage asks for work is the granary's (stall
  ``granary_first``); in a region under an RS2 granary project the works add
  to RS2's request and RS2 takes ``min(delivered, its request)`` first; a
  region where storage asked for nothing is claimed for the works (added to
  the storage plan's suspended regions, so storage's settlement, whose
  request there is 0, ignores the works' delivered work). The split is
  recorded.
* Timber: ``TIMBER_PER_WORK`` (irrigation 0.25, roads 0.5) from RS2's free
  timber after RS2's holds (stockpile minus merchant commitments, plus the
  PL1 store), held in RS2's per-region holds (so a failed tick returns it with
  RS2's) and the unused part returned after the tick.
* Coins: ``COIN_MILLI_PER_WORK`` per delivered unit (a whole repair from 0
  costs at most the BUILD cost of a new record: irrigation 12, roads 10), one
  whole-unit charge per civ and turn with the sub-unit remainder prepaid
  (RS2's rule), paid from the treasury to the declared sink ``public_works``
  through the payment seam (``money.pay``, purpose ``infrastructure_repair``).
  The sink has no payee: the coins leave the economy, as the storage
  channel's granary coins do (a deflationary leak to count in A1/A2
  calibration). Planned after every Phase 2 bill RS2 plans around and after
  RS2's own planned charge (RS2's rounding reserved whole); later planners
  see the works' planned coins rounded on their own
  (``repair_projects.pending_bills`` adds the two roundings).
* L9 (``--local-budgets``): the works are their **own** proposal (service
  ``infrastructure_works``, :data:`BUDGET_PROVIDER`), never pooled with RS2's:
  irrigation works only, with their own cost and the commons' food at risk
  relieved = the irrigation arable ceiling the work keeps over L9's
  ``horizon`` (service with the work minus without, turn by turn, under
  declared wear) x the region's observed food production / its arable
  capacity. That rule assumes food output scales with the arable ceiling (an
  upper bound where labour, not land, limits output). Works certain to stall
  are screened out first (no farmer, storage set to ask for work, no free
  timber after RS2's needs). With L9 the works spend only within that
  envelope; roads carry no relief, are not proposed and so get no envelope.
* Stalls (a turn without delivered work): ``no_timber``, ``no_coins``,
  ``no_labor``, ``no_envelope``, ``granary_first``.

Closure, per civ and turn: ``charged x 1000 + prepaid_before == coin_cost +
prepaid_after`` (each prepaid in [0, 1000)); per work: timber held = used +
returned, used = delivered x rate; delivered <= requested. No random draws.
"""
from __future__ import annotations

import math

from chronicler.infrastructure_condition_state import (
    COUNTERS, KINDS, MAX_CLOSED, MAX_DAMAGES, MAX_HISTORY, MAX_TERMINAL, MODES, WORK_MODES,
    InfraAsset, InfraDamage, InfrastructureConditionState, InfraWork, UnmetWork, WorkReceipt, WorksLedger,
)

MILLI = 1000
#: Condition lost per turn by a serving asset (declared).
WEAR: dict[str, float] = {"irrigation": 0.01, "roads": 0.005}
#: Condition at which service is full: ``s = min(1, condition / SERVICE_FULL)``.
SERVICE_FULL = 0.5
#: Least service at which irrigation sets the native flag and a road extends range.
SERVICE_GATE = 0.5
#: A wear work opens below this condition (RS2's threshold).
OPEN_BELOW = 0.75
#: Work units restoring a whole unit of condition (declared).
WORK_PER_CONDITION: dict[str, float] = {"irrigation": 20.0, "roads": 20.0}
#: Most work one asset's work asks per turn (the storage channel's batch).
WORK_PER_TURN = 4.0
#: Timber per work unit (lead decision).
TIMBER_PER_WORK: dict[str, float] = {"irrigation": 0.25, "roads": 0.5}
#: Coins (milli-units) per delivered work unit: a work's whole repair from
#: condition 0 costs at most the BUILD cost of a new record of its type
#: (``infrastructure.BUILD_SPECS``, undiscounted: irrigation 12, roads 10 over
#: ``WORK_PER_CONDITION`` work), so repairing is never dearer in coins than
#: rebuilding; labour and timber are its additional real inputs.
COIN_MILLI_PER_WORK: dict[str, int] = {"irrigation": 600, "roads": 500}
#: Condition one real war event takes (times ``repair_projects.war_damage``).
WAR_DAMAGE = 0.25
#: Flood damage per unit of excess water, capped (the B2 flow-mode seam).
FLOOD_DAMAGE_PER_EXCESS = 0.5
FLOOD_DAMAGE_CAP = 0.5
#: Least work a proposal may promise (RS2's ``MIN_PROPOSAL_WORK``).
MIN_PROPOSAL_WORK = 1e-3
#: Remaining work below this is delivered (RS2's ``DONE``).
DONE = 1e-6
EPS = 1e-9
PURPOSE = "infrastructure_repair"
SINK = "public_works"
#: The works' own L9 service (``BUDGET_PROVIDER``, group ``repairs``).
BUDGET_SERVICE = "infrastructure_works"
_TYPES = {"IRRIGATION": "irrigation", "ROADS": "roads"}


# ---------------------------------------------------------------------------
# Switch and lookups
# ---------------------------------------------------------------------------

def _state(world) -> InfrastructureConditionState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "infrastructure_condition", None) if container is not None else None


def infrastructure_condition_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled and getattr(world, "agent_mode", None) == "hybrid"


def _rs2_active(world) -> bool:
    if getattr(getattr(world, "livelihoods", None), "repair_projects", None) is None:
        return False
    from chronicler.repair_projects import repair_projects_active
    return repair_projects_active(world)


def _works_on(world, state) -> bool:
    """Works plan and pay: a work mode with RS2 active."""
    return state is not None and state.mode in WORK_MODES and infrastructure_condition_active(world) \
        and _rs2_active(world)


def _bump(state, key: str, amount=1) -> None:
    if key not in COUNTERS:
        raise KeyError(f"undeclared infrastructure-condition counter {key!r}")
    state.counters[key] = state.counters.get(key, 0) + amount


def _note(item, turn: int, event: str, civ: int, amount: int = 0) -> None:
    item.history.append((int(turn), event, int(civ), int(amount)))
    del item.history[:-MAX_HISTORY]


def _controller(world, region: int) -> int:
    name = world.regions[region].controller
    if name is None:
        return -1
    for i, civ in enumerate(world.civilizations):
        if civ.name == name:
            return i if getattr(civ, "regions", None) else -1
    return -1


def _index(world, region) -> int:
    """The region's index; a Region not in ``world.regions`` is matched by its
    (unique) name. An unknown region raises: service never fails open."""
    if isinstance(region, int) and not isinstance(region, bool):
        if 0 <= region < len(world.regions):
            return region
        raise ValueError(f"unknown region index {region}")
    for i, r in enumerate(world.regions):
        if r is region:
            return i
    name = getattr(region, "name", None)
    matches = [i for i, r in enumerate(world.regions) if r.name == name]
    if len(matches) == 1:
        return matches[0]
    raise ValueError(f"unknown region {name!r}: infrastructure service cannot be read")


def service_of(condition: float) -> float:
    return min(1.0, max(0.0, float(condition)) / SERVICE_FULL)


def _live(world) -> InfrastructureConditionState | None:
    """The state whose condition reaches consumers (None: service is 1.0)."""
    container = getattr(world, "livelihoods", None)
    if container is None:
        return None
    state = getattr(container, "infrastructure_condition", None)
    if state is None or state.mode == "record_only" or not infrastructure_condition_active(world):
        return None
    return state


def service(world, region, kind: str) -> float:
    """Service of ``region``'s ``kind`` asset in [0, 1]: exactly 1.0 while the
    switch is off, in ``record_only``, or for a record not yet registered (a
    new work starts at condition 1.0). ``region``: a Region or its index."""
    state = _live(world)
    if state is None:
        return 1.0
    rid = _index(world, region)
    best = None
    for a in state.assets:
        if a.region == rid and a.kind == kind and a.status in ("serving", "failed"):
            s = service_of(a.condition)
            best = s if best is None else max(best, s)
    return 1.0 if best is None else best


def serves(world, region, kind: str) -> bool:
    """Whether the asset still serves its gated consumer (``s >= SERVICE_GATE``);
    True while the switch is off."""
    return service(world, region, kind) >= SERVICE_GATE


# ---------------------------------------------------------------------------
# Enable, prerequisites
# ---------------------------------------------------------------------------

def check_request(world, value: bool | None, args=None, *, agent_mode=None, rs2: bool = False) -> None:
    """Refuse a request this world cannot honour, before anything changes
    (``livelihoods._check_prerequisites``). The mode is chosen when the record
    opens; a mode change on resume is refused. Work modes need
    ``--repair-projects``; every mode needs ``--agents hybrid``. Ending the
    switch (``--no-infrastructure-condition``) is always allowed."""
    mode = getattr(args, "infrastructure_condition_mode", None) if args is not None else None
    if mode is not None and mode not in MODES:
        raise ValueError(f"infrastructure_condition_mode must be one of {MODES}")
    state = _state(world)
    if mode is not None and (value is False or (value is None and (state is None or not state.enabled))):
        raise ValueError("--infrastructure-condition-mode requires --infrastructure-condition (this world does not "
                         "have the switch on)")
    if value is False:
        return
    if state is not None and mode is not None and mode != state.mode:
        raise ValueError(f"--infrastructure-condition-mode {mode} conflicts with this world's infrastructure "
                         f"record (mode {state.mode}); a mode change on resume is refused")
    on = value is True or (value is None and state is not None and state.enabled)
    if not on:
        return
    saved = value is not True
    tail = "; this world has it on: pass --no-infrastructure-condition to end it" if saved else ""
    if agent_mode != "hybrid":
        raise ValueError("--infrastructure-condition requires --agents hybrid" + tail)
    effective = mode or (state.mode if state is not None else MODES[0])
    if effective in WORK_MODES and not rs2:
        raise ValueError(f"--infrastructure-condition-mode {effective} requires --repair-projects (its works use "
                         "RS2's labour, timber and repairs budget; record_only and wear_only need only "
                         "--agents hybrid)" + tail)


def set_infrastructure_condition_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Open the record (with ``--infrastructure-condition-mode``, default
    ``repair``) or end it. Ending abandons open works (``switched_off``) and
    writes off the prepaid remainders; the record is kept and service returns
    to 1.0. Re-enabling keeps the saved registry and mode."""
    mode = getattr(args, "infrastructure_condition_mode", None) if args is not None else None
    state = _state(world)
    if state is None:
        world.livelihoods.infrastructure_condition = state = InfrastructureConditionState(mode=mode or MODES[0])
    else:
        t = state._turn
        if t is not None and t.turn == getattr(world, "turn", None) and t.prepared:
            raise RuntimeError("cannot change infrastructure condition while a turn is pending")
        if mode is not None and mode != state.mode:
            raise ValueError("a mode change on resume is refused")
    if not value and state.enabled:
        turn = getattr(world, "turn", 0)
        for work in list(state.works):
            _close(state, work, turn, "abandoned", "switched_off")
        _write_off(state, list(state.prepaid))
    state.enabled = bool(value)


def _write_off(state, civs) -> None:
    for civ in civs:
        amount = state.prepaid.pop(civ, 0)
        if amount:
            _bump(state, "prepaid_written_off_milli", amount)


def _close(state, work: InfraWork, turn: int, status: str, reason: str | None) -> None:
    work.status, work.closed_turn, work.closed_reason = status, turn, reason
    _note(work, turn, status if reason is None else f"{status}_{reason}", work.controller)
    state.works = [w for w in state.works if w is not work]
    state.closed.append(work)
    del state.closed[:-MAX_CLOSED]
    _bump(state, status if reason is None else f"{status}_{reason}")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _kind(record) -> str | None:
    return _TYPES.get(getattr(getattr(record, "type", None), "name", None))


def _end_cause(world, region) -> str:
    """Why ``region``'s records turned inactive this turn, read from dated state."""
    turn = world.turn
    if getattr(region, "depopulated_since", None) == turn:
        return "depopulation"
    for event in reversed(getattr(world, "events_timeline", []) or []):
        if event.turn != turn:
            if event.turn < turn:
                break
            continue
        if event.event_type == "earthquake" and getattr(event, "region", None) == region.name:
            return "earthquake"
        if event.event_type == "scorched_earth" and f"scorched {region.name} during retreat" in (event.description or ""):
            return "scorch"
    return "unknown"


def _terminate(state, asset: InfraAsset, turn: int, status: str, cause: str) -> None:
    asset.status, asset.status_turn, asset.cause = status, turn, cause
    _note(asset, turn, f"{status}_{cause}", asset.responsible)
    state.assets = [a for a in state.assets if a is not asset]
    state.terminal.append(asset)
    del state.terminal[:-MAX_TERMINAL]
    _bump(state, f"assets_{status}")
    _bump(state, f"{status}_{cause}")


def _record(world, asset: InfraAsset):
    """The asset's record, when it is still the same record."""
    records = world.regions[asset.region].infrastructure
    rec = records[asset.record_index] if asset.record_index < len(records) else None
    if rec is None or _kind(rec) != asset.kind or rec.built_turn != asset.built_turn \
            or rec.builder_civ != asset.builder_civ:
        return None
    return rec


def _in_service(world, asset: InfraAsset) -> bool:
    rec = _record(world, asset)
    return rec is not None and bool(rec.active)


def reconcile(world, *, end: bool = True) -> None:
    """Match the registry to the world's records (idempotent). With ``end``
    (Phase 10, when the turn's events are dated in the timeline) records that
    turned inactive or were removed end their assets; mid-turn callers only
    register new records (their assets' records are checked where read)."""
    state = _state(world)
    if state is None or not infrastructure_condition_active(world):
        return
    turn = world.turn
    held = {(a.region, a.record_index): a for a in state.assets}
    for rid, region in enumerate(world.regions):
        records = region.infrastructure
        for key in ([k for k in held if k[0] == rid] if end else []):
            asset = held[key]
            rec = _record(world, asset)
            if rec is None:
                _terminate(state, asset, turn, "destroyed", "record_removed")
                del held[key]
            elif not rec.active:
                _terminate(state, asset, turn, "inactive", _end_cause(world, region))
                del held[key]
        for idx, rec in enumerate(records):
            kind = _kind(rec)
            if kind is None or not rec.active or (rid, idx) in held:
                continue
            if not end and any(a.region == rid and a.record_index == idx for a in state.assets):
                continue        # a replaced record whose old asset ends at Phase 10
            if any(a.region == rid and a.record_index == idx and a.built_turn == rec.built_turn
                   and a.builder_civ == rec.builder_civ and a.kind == kind for a in state.terminal):
                continue        # a terminal asset's record never serves again
            ctrl = _controller(world, rid)
            asset = InfraAsset(aid=state.next_aid, kind=kind, region=rid, record_index=idx,
                               built_turn=int(rec.built_turn), builder_civ=str(rec.builder_civ),
                               opened_turn=turn, status_turn=turn, responsible=ctrl)
            state.next_aid += 1
            _note(asset, turn, "opened", ctrl)
            state.assets.append(asset)
            held[(rid, idx)] = asset
            _bump(state, "assets_opened")
            _bump(state, f"assets_opened_{kind}")
    state.assets.sort(key=lambda a: a.aid)
    if end:
        state.reconciled_turn = turn


def _set_condition(state, asset: InfraAsset, value: float, turn: int) -> None:
    value = min(1.0, max(0.0, float(value)))
    was = asset.status
    asset.condition = value
    if was == "serving" and value <= 0.0:
        asset.status, asset.status_turn, asset.failed_turn = "failed", turn, turn
        _note(asset, turn, "failed", asset.responsible)
        _bump(state, "assets_failed")
        _bump(state, f"assets_failed_{asset.kind}")
    elif was == "failed" and value > 0.0:
        asset.status, asset.status_turn = "serving", turn
        _note(asset, turn, "restored", asset.responsible, round(value * MILLI))
        _bump(state, "assets_restored")


def _asset(state, aid: int) -> InfraAsset | None:
    return next((a for a in state.assets if a.aid == aid), None)


def _open_work(state, aid: int) -> InfraWork | None:
    return next((w for w in state.works if w.aid == aid), None)


# ---------------------------------------------------------------------------
# Damage (RS2's war hooks; the watershed flood seam)
# ---------------------------------------------------------------------------

def _damage(world, state, asset: InfraAsset, event: str, amount: float, key, start, ref=None) -> None:
    turn = world.turn
    if amount <= 0 or asset.status != "serving":
        return
    if any(d.turn == turn and d.aid == asset.aid for d in state.damages):
        return                                        # one damage per asset per turn
    before = asset.condition
    _set_condition(state, asset, before - amount, turn)
    after = asset.condition
    record = InfraDamage(did=state.next_did, turn=turn, aid=asset.aid, kind=asset.kind, region=asset.region,
                         event=event, war_key=key, war_start_turn=start, ref=ref, amount=before - after,
                         condition_before=before, condition_after=after)
    state.next_did += 1
    asset.damage += before - after
    _note(asset, turn, f"damage_{event}", asset.responsible, round((before - after) * MILLI))
    work = _open_work(state, asset.aid)
    if work is not None:
        record.work = work.wid
        work.damages.append(record.did)
        work.scope += record.amount * WORK_PER_CONDITION[asset.kind]
        if work.cause == "wear":
            work.cause = "war" if event != "flood" else "flood"
        if work.war_key is None and key is not None:
            work.war_key, work.war_start_turn = key, start
        _note(work, turn, f"damage_{event}", work.controller, round(record.amount * MILLI))
    state.damages.append(record)
    del state.damages[:-MAX_DAMAGES]
    _bump(state, "damages")
    _bump(state, f"damages_{event}")
    _bump(state, "damage", round(before - after, 9))
    _bump(state, f"damage_{asset.kind}", round(before - after, 9))


def war_damage(world, region, event: str, a: str | None, b: str | None) -> None:
    """RS2's ``region_conquered``/``city_sacked`` hooks: every serving asset of
    the region takes ``WAR_DAMAGE`` (times ``repair_projects.war_damage``),
    with the war's identity when found. No-op unless active (any mode)."""
    state = _state(world)
    if state is None or not infrastructure_condition_active(world):
        return
    rid = _index(world, region)
    if rid is None:
        return
    reconcile(world, end=False)
    from chronicler.repair_projects import _damage_scale, _war_identity
    amount = WAR_DAMAGE * _damage_scale(world)
    key, start = _war_identity(world, a, b)
    for asset in [x for x in state.assets if x.region == rid and _in_service(world, x)]:
        _damage(world, state, asset, event, amount, key, start)


def flood_damage(world, region: int, excess: float, *, ref: str | None = None) -> None:
    """The watershed flow mode's seam (no caller until that mode exists):
    every serving asset of ``region`` takes ``FLOOD_DAMAGE_PER_EXCESS x
    excess`` condition, capped at ``FLOOD_DAMAGE_CAP``. No-op unless active."""
    state = _state(world)
    if state is None or not infrastructure_condition_active(world):
        return
    if not (math.isfinite(excess) and excess >= 0):
        raise ValueError("flood excess must be finite and >= 0")
    reconcile(world, end=False)
    amount = min(FLOOD_DAMAGE_CAP, FLOOD_DAMAGE_PER_EXCESS * float(excess))
    for asset in [x for x in state.assets if x.region == int(region) and _in_service(world, x)]:
        _damage(world, state, asset, "flood", amount, None, None, ref=ref)


# ---------------------------------------------------------------------------
# Phase 2, inside RS2's turn
# ---------------------------------------------------------------------------

class _Plan:
    __slots__ = ("work", "kind", "region", "payer", "reasons", "request", "hold", "envelope",
                 "condition_before", "planned_milli", "granary_request", "shared", "delivered")

    def __init__(self, work, payer, condition_before):
        self.work, self.kind, self.region, self.payer = work, work.kind, work.region, payer
        self.reasons: list[str] = []
        self.request = 0.0
        self.hold = 0.0
        self.envelope = None
        self.condition_before = condition_before
        self.planned_milli = 0
        self.granary_request = 0.0
        self.shared = False
        self.delivered = 0.0


class _Turn:
    """One turn in flight, Phase 2 to Phase 10 (never checkpointed)."""

    def __init__(self, turn: int):
        self.turn = turn
        self.prepared = False
        self.finished = False
        self.plans: list[_Plan] = []
        self.base: dict[int, float] = {}            # the granary's request in the column, per region
        self.region_request: dict[int, float] = {}  # the works' part of the column, per region
        self.receipts: list[WorkReceipt] = []
        self.ledger: list[WorksLedger] = []
        self.shared: list[int] = []
        self.claimed: list[int] = []
        self.appended = False


def _f32_floor(value: float) -> float:
    from chronicler.grain_storage import _f32_floor as floor
    return floor(value)


def _coin_milli(work: float, kind: str) -> int:
    """Coin cost of ``work`` units of ``kind``, rounded up to the milli-unit."""
    return max(0, math.ceil(work * COIN_MILLI_PER_WORK[kind] - 1e-6))


def _storage_policy_works(world, rid: int) -> bool:
    """A prediction from the current storage policy (for L9 proposals): the
    region's granary is set to ask for work (expand, or maintain below full
    condition, with an owner). Phase 2 uses storage's actual request."""
    from chronicler.repair_projects import _grain_storage_on
    if not _grain_storage_on(world) or world.regions[rid].controller is None:
        return False
    storage = world.grain_reserves.storage
    policy = storage.policies[rid].policy
    asset = storage.assets[rid]
    if policy == "expand":
        return True
    return policy == "maintain" and asset is not None and asset.condition < 1.0


def _order(work) -> tuple:
    return (KINDS.index(work.kind), work.region, work.aid)


def _begin(world, state) -> _Turn:
    t = state._turn
    if t is not None and t.turn == world.turn:
        if t.prepared:
            raise RuntimeError("infrastructure works already prepared for this turn")
        return t
    if state.last_settled_turn is not None and world.turn <= state.last_settled_turn:
        raise RuntimeError("infrastructure works already settled for this turn")
    t = state._turn = _Turn(world.turn)
    return t


def plan_phase2(world, rs2, region_input, snapshot, acc, commitments):
    """RS2's ``prepare_phase2`` seam, after RS2 planned its own projects and
    before RS2 applies the turn's timber holds: plan each open work's labour,
    timber and coins, add its request to the labour column and its timber to
    RS2's per-region holds. Charges nothing. Returns the region batch."""
    state = _state(world)
    if not _works_on(world, state):
        return region_input
    from chronicler import repair_projects as R
    t = _begin(world, state)
    turn = world.turn
    for work in list(state.works):
        if _controller(world, work.region) < 0:
            _close(state, work, turn, "abandoned", "no_controller")
    # A work whose record turned inactive this turn plans nothing; it is
    # abandoned (asset_lost) when Phase 10 ends the asset with its dated cause.
    works = sorted((w for w in state.works if (a := _asset(state, w.aid)) is not None and _in_service(world, a)),
                   key=_order)
    names = region_input.schema.names
    present = "granary_work_requested" in names
    storage_on = R._grain_storage_on(world)
    if storage_on and not present:
        raise RuntimeError("infrastructure works with grain storage require the storage work column")
    n = len(world.regions)
    column = (list(region_input.column(names.index("granary_work_requested")).to_pylist()) if present
              else [0.0] * n)
    plan = getattr(world.grain_reserves.storage, "_active_plan", None) if storage_on else None
    if storage_on and plan is None:
        raise RuntimeError("infrastructure works with grain storage require this turn's storage plan")
    rs2_regions = set(getattr(plan, "suspended", ()) or ()) if storage_on else set()
    labour = R._farm_labour(world, snapshot) if works else None
    if commitments is None:
        commitments = R._commitments(world, rs2.sim) if works else {}
    # Coins: after every bill RS2 plans around and after RS2's own planned
    # charge, its rounding reserved whole (RS2 never charges above it).
    from chronicler.mutual_aid import _treasury_budget
    others = R._pending_before_granaries(world)
    rs2_milli = [0] * len(world.civilizations)
    for w in rs2.work.values():
        if 0 <= w.payer < len(rs2_milli):
            rs2_milli[w.payer] += w.planned_milli
    rs2_units = [-(-m // MILLI) for m in rs2_milli]
    budgets = [max(0, math.floor(_treasury_budget(world, c, acc)) - others[i] - rs2_units[i])
               for i, c in enumerate(world.civilizations)]
    milli = [0] * len(budgets)
    holds: dict[int, float] = {}
    env_milli: dict[int, int] = {}
    from chronicler.local_budgets import envelope
    for work in works:
        asset = _asset(state, work.aid)
        payer = _controller(world, work.region)
        p = _Plan(work, payer, float(asset.condition))
        t.plans.append(p)
        rid = work.region
        # The works' own L9 envelope (None without L9: the treasury rule). Only
        # irrigation is proposed; with L9 a road has no envelope.
        env = envelope(world, payer, BUDGET_SERVICE)
        if env is not None and work.kind != "irrigation":
            env = 0
        p.envelope = env
        if storage_on and rid not in rs2_regions and float(column[rid]) > 0.0:
            p.reasons = ["granary_first"]            # storage asks for work here this turn
            continue
        if labour is not None and labour[rid] == 0:
            p.reasons = ["no_labor"]
            continue
        remaining = max(0.0, work.scope - work.delivered)
        want = min(WORK_PER_TURN, remaining)
        rate = TIMBER_PER_WORK[work.kind]
        free = R._free_timber(world, rid, commitments, rs2.holds.get(rid, 0.0) + holds.get(rid, 0.0))
        per = COIN_MILLI_PER_WORK[work.kind]
        limits = {"no_timber": free / rate,
                  "no_coins": max(0, budgets[payer] * MILLI - milli[payer]) / per}
        if env is not None:
            limits["no_envelope"] = max(0, env * MILLI - env_milli.get(payer, 0)) / per
        amount = _f32_floor(max(0.0, min([want, *limits.values()])))
        p.reasons = [reason for reason, value in limits.items() if value + EPS < want]
        p.request = amount
        if amount > 0:
            p.hold = amount * rate
            p.planned_milli = _coin_milli(amount, work.kind)
            milli[payer] += p.planned_milli
            if env is not None:
                env_milli[payer] = env_milli.get(payer, 0) + p.planned_milli
            holds[rid] = holds.get(rid, 0.0) + p.hold
            t.region_request[rid] = t.region_request.get(rid, 0.0) + amount
    for rid in sorted(t.region_request):
        base = float(column[rid])
        t.base[rid] = base
        total = _f32_floor(base + t.region_request[rid])
        # The f32 column holds the sum; the works' part is what it adds to the granary's.
        t.region_request[rid] = max(0.0, total - base)
        column[rid] = total
        if base > 0:
            t.shared.append(rid)
        for p in t.plans:
            if p.region == rid:
                p.granary_request, p.shared = base, base > 0
    for rid, amount in sorted(holds.items()):
        rs2.holds[rid] = rs2.holds.get(rid, 0.0) + amount
    claimed = frozenset(rid for rid in t.region_request if storage_on and rid not in rs2_regions)
    if claimed:
        # Regions where storage asked for nothing this turn: the column's work
        # is the works'; storage's settlement reads them as suspended (its
        # request there is 0, so nothing of storage's changes).
        if any(plan.requests[rid] != 0.0 for rid in claimed):
            raise RuntimeError("infrastructure works claimed a region where storage asked for work")
        plan.suspended = frozenset(plan.suspended) | claimed
        t.claimed = sorted(claimed)
    if t.region_request:
        import pyarrow as pa
        array = pa.array(column, type=pa.float32())
        if present:
            region_input = region_input.set_column(names.index("granary_work_requested"),
                                                   "granary_work_requested", array)
        else:
            region_input = region_input.append_column("granary_work_requested", array)
            t.appended = True
    t.prepared = True
    return region_input


def shares(world) -> dict[int, float]:
    """RS2's ``finish_phase2`` seam: the works' part of the labour column per
    region this turn (RS2 then takes ``min(delivered, its request)`` first)."""
    state = _state(world)
    t = state._turn if state is not None else None
    if t is None or t.turn != world.turn or not t.prepared:
        return {}
    return {rid: amount for rid, amount in t.region_request.items() if amount > 0}


def pending_milli(world) -> list[int]:
    """Planned, not yet charged work coins per civ (``repair_projects.pending_bills``)."""
    out = [0] * len(world.civilizations)
    state = _state(world)
    t = state._turn if state is not None else None
    if t is None or t.turn != world.turn or not t.prepared or t.finished:
        return out
    for p in t.plans:
        if 0 <= p.payer < len(out):
            out[p.payer] += p.planned_milli
    return out


def settle_phase2(world, rs2, economy_result, acc) -> None:
    """RS2's ``finish_phase2`` seam, after RS2 charged: split the delivered
    column work (granary first, then irrigation, then roads), credit condition
    (``repair``), return unused timber and charge each civ once through the
    payment seam."""
    state = _state(world)
    t = state._turn if state is not None else None
    if t is None or t.turn != world.turn or not t.prepared:
        return
    if t.finished:
        raise RuntimeError("infrastructure works already settled for this turn")
    from chronicler import repair_projects as R
    delivered = getattr(economy_result, "granary_work_delivered", None) or {}
    for rid, request in sorted(t.region_request.items()):
        if request <= 0:
            continue
        if rid not in delivered:
            raise RuntimeError("infrastructure works require delivered-work observations from the native economy")
        total = float(delivered[rid])
        if not (math.isfinite(total) and 0.0 <= total <= t.base.get(rid, 0.0) + request + 1e-6):
            raise RuntimeError("delivered column work beyond its requests")
        left = min(request, max(0.0, total - min(total, t.base.get(rid, 0.0))))
        for p in [p for p in t.plans if p.region == rid]:        # plans are in split order
            got = min(left, p.request)
            left -= got
            p.delivered = got
            if got < p.request - DONE and "no_labor" not in p.reasons:
                p.reasons.append("no_labor")
    turn = world.turn
    repairs = state.mode == "repair"
    # Validate every civ's whole bill before anything is credited or moved.
    from chronicler.local_budgets import envelope
    from chronicler.money import quote
    costs: dict[int, int] = {}
    for p in t.plans:
        if p.payer < 0 or _controller(world, p.region) != p.payer:
            if p.delivered > 0:
                raise RuntimeError("infrastructure work payer changed while its work was pending")
        if p.payer >= 0:
            costs[p.payer] = costs.get(p.payer, 0) + _coin_milli(p.delivered, p.kind)
    charges: dict[int, tuple[int, int, int]] = {}
    for civ in sorted(costs):
        before = int(state.prepaid.get(civ, 0))
        need = costs[civ] - before
        charged = max(0, -(-need // MILLI))
        charges[civ] = (before, charged, charged * MILLI - need)
        if charged:
            q = quote(world, _bill(civ, charged), turn=turn, book=state.book, acc=acc)
            if not q.ok:
                raise RuntimeError(f"infrastructure works charge refused at settlement ({q.reason}); "
                                   "another spender was missed")
    rows: dict[int, dict] = {}
    receipts = []
    for p in t.plans:
        work = p.work
        asset = _asset(state, work.aid)
        done = p.delivered
        rate = TIMBER_PER_WORK[work.kind]
        used = done * rate
        returned = p.hold - used
        if returned < -1e-9:
            raise RuntimeError("infrastructure work used more timber than it held")
        returned = max(0.0, returned)
        if returned:
            to_store = R._return_store(world, rs2, p.region, returned)
            if to_store < returned:
                goods = world.regions[p.region].stockpile.goods
                goods["timber"] = goods.get("timber", 0.0) + (returned - to_store)
        cost = _coin_milli(done, work.kind)
        credit = done if repairs else 0.0
        before = asset.condition if asset is not None else p.condition_before
        if credit and asset is not None:
            gain = credit / WORK_PER_CONDITION[work.kind]
            if before + gain > 1.0 + 1e-9:
                _bump(state, "cap_waste", round(before + gain - 1.0, 9))
            _set_condition(state, asset, before + gain, turn)
            asset.credited += min(gain, 1.0 - before)
        after = asset.condition if asset is not None else before
        work.delivered += done
        work.credited += credit
        work.timber_used += used
        work.coin_cost_milli += cost
        if work.controller != p.payer and p.payer >= 0:
            _note(work, turn, "controller", p.payer)
            work.controller = p.payer
        if done > 0:
            work.work_turns += 1
            _bump(state, "progress_turns")
        else:
            work.stalled_turns += 1
            _bump(state, "stalled_turns")
        for reason in p.reasons:
            stalled = done <= 0
            if stalled:
                work.stalls[reason] = work.stalls.get(reason, 0) + 1
            _bump(state, f"{'stalled' if stalled else 'limited'}_{reason}")
        remaining = max(0.0, work.scope - work.delivered)
        receipts.append(WorkReceipt(
            turn=turn, wid=work.wid, aid=work.aid, kind=work.kind, region=p.region, payer=p.payer,
            status="progress" if done > 0 else "stalled", reasons=list(p.reasons), requested=p.request,
            delivered=done, credited=credit, granary_request=p.granary_request, shared=p.shared,
            timber_held=p.hold, timber_used=used, timber_returned=returned, coin_cost_milli=cost,
            envelope=p.envelope, condition_before=p.condition_before, condition_after=after,
            remaining_after=remaining))
        if p.payer >= 0:
            row = rows.setdefault(p.payer, dict(works=0, work=0.0, timber=0.0, cost=0,
                                                envelope=envelope(world, p.payer, BUDGET_SERVICE)))
            row["works"] += 1
            row["work"] += done
            row["timber"] += used
            row["cost"] += cost
        _bump(state, "work_delivered", done)
        _bump(state, "work_credited", credit)
        _bump(state, "timber_used", used)
        _bump(state, f"{work.kind}_work", done)
        if remaining <= DONE:
            _close(state, work, turn, "completed", None)
    rs2_charged = {row.civ: int(row.charged) for row in (rs2.ledger or [])}
    ledger = []
    for civ in sorted(rows):
        r = rows[civ]
        before, charged, after = charges[civ]
        if r["cost"] != costs[civ]:
            raise RuntimeError("infrastructure works cost changed between validation and settlement")
        if after:
            state.prepaid[civ] = after
        else:
            state.prepaid.pop(civ, None)
        if charged:
            receipt = _charge(world, state, civ, charged, turn, acc)
            if not receipt.ok:
                raise RuntimeError(f"infrastructure works charge refused at settlement ({receipt.reason}); "
                                   "another spender was missed")
        row = WorksLedger(turn=turn, civ=civ, works=r["works"], work_delivered=r["work"], timber_used=r["timber"],
                          coin_cost_milli=r["cost"], charged=charged, prepaid_before_milli=before,
                          prepaid_after_milli=after, envelope=r["envelope"], rs2_charged=rs2_charged.get(civ, 0))
        check_ledger(row)
        ledger.append(row)
        _bump(state, "charged", charged)
        _bump(state, "coin_cost_milli", r["cost"])
    _bump(state, "shared_regions", len(t.shared))
    t.receipts, t.ledger = receipts, ledger
    t.finished = True


def _bill(civ: int, charged: int):
    """One civ's whole-unit charge: the treasury pays the declared sink
    ``public_works`` (keyed by the civ: once a turn). The sink has no payee:
    these coins leave the economy, as the storage channel's granary coins do;
    the farmers whose time does the work are not paid."""
    from chronicler.money import Bill, sink, treasury
    return Bill(purpose="infrastructure_repair", batch=int(civ), phase="phase2", payer=treasury(civ),
                lines=((sink(SINK), int(charged) * MILLI),))


def _charge(world, state, civ: int, charged: int, turn: int, acc):
    from chronicler.money import pay
    return pay(world, _bill(civ, charged), turn=turn, book=state.book, acc=acc)


def check_ledger(row: WorksLedger) -> None:
    """Exact integer closure of one civ's works accounts in one turn, and the
    works' own L9 envelope."""
    if row.charged * MILLI + row.prepaid_before_milli != row.coin_cost_milli + row.prepaid_after_milli \
            or not 0 <= row.prepaid_before_milli < MILLI or not 0 <= row.prepaid_after_milli < MILLI \
            or row.charged < 0:
        raise RuntimeError(f"infrastructure works accounts of civ {row.civ} do not close")
    if row.envelope is not None and row.charged > row.envelope:
        raise RuntimeError(f"infrastructure works of civ {row.civ} spent beyond their envelope")


def rollback_phase2(world) -> None:
    """A failed Phase 2: RS2 returns every hold of the turn (the works' included);
    nothing of this turn is recorded."""
    state = _state(world)
    if state is not None and state._turn is not None and state._turn.turn == getattr(world, "turn", None) \
            and not state._turn.finished:
        state._turn = None


# ---------------------------------------------------------------------------
# L9: the works' part of RS2's ``repairs`` proposal
# ---------------------------------------------------------------------------

def food_at_risk_relieved(world, region: int, condition: float, amount: float, horizon: float,
                          produced: float) -> float:
    """The declared L9 relief of irrigation work (owned here): over the
    horizon, the arable ceiling the work keeps (service with the work minus
    service without, each turn under ``WEAR``) times the region's observed
    food production over its arable capacity. Positive before failure, once
    service would fall within the horizon."""
    if amount <= 0 or produced <= 0:
        return 0.0
    from chronicler.economy import FARM_CEILING_IRRIGATION, arable_capacity
    from chronicler.ecology import potential_capacity
    reg = world.regions[region]
    capacity = arable_capacity(world, reg)
    if not capacity > 0:
        return 0.0
    wear = WEAR["irrigation"]
    c0 = float(condition)
    c1 = min(1.0, c0 + amount / WORK_PER_CONDITION["irrigation"])
    kept = math.fsum(service_of(c1 - h * wear) - service_of(c0 - h * wear)
                     for h in range(1, int(math.floor(horizon)) + 1))
    return produced * potential_capacity(reg) * FARM_CEILING_IRRIGATION * kept / capacity


def food_at_risk(world, region: int, condition: float, horizon: float, produced: float) -> float:
    """The food ``region`` would lose over the horizon without repair: the
    arable ceiling lost each turn under ``WEAR`` (full service minus service)
    times its observed food production over its arable capacity."""
    if produced <= 0:
        return 0.0
    from chronicler.economy import FARM_CEILING_IRRIGATION, arable_capacity
    from chronicler.ecology import potential_capacity
    reg = world.regions[region]
    capacity = arable_capacity(world, reg)
    if not capacity > 0:
        return 0.0
    lost = math.fsum(1.0 - service_of(condition - h * WEAR["irrigation"])
                     for h in range(1, int(math.floor(horizon)) + 1))
    return produced * potential_capacity(reg) * FARM_CEILING_IRRIGATION * lost / capacity


def _observe_food_at_risk(world, state, economy_result) -> None:
    ledger = getattr(economy_result, "food_ledger", None) if economy_result is not None else None
    from chronicler.local_budgets import HORIZON, _parameters
    horizon = _parameters(world)["horizon"] if getattr(world.livelihoods, "local_budgets", None) is not None \
        else HORIZON
    for asset in state.assets:
        if asset.kind != "irrigation":
            continue
        row = ledger.get(asset.region) if ledger else None
        asset.food_at_risk = (None if row is None or len(row) < 2
                              else round(food_at_risk(world, asset.region, asset.condition, horizon, float(row[1])), 9))


def _rs2_timber_estimate(world) -> dict[int, float]:
    """Timber RS2's open projects would hold next turn per region (RS2 plans
    first in Phase 2): a granary project's full per-turn batch, a workshop
    project's full crew at the qualified rate; an upper bound for proposals."""
    from chronicler import repair_projects as R
    state = R._state(world)
    out: dict[int, float] = {}
    if state is None or not R.repair_projects_active(world):
        return out
    _per_condition, per_turn, timber_rate, _coins = R._storage_rules()
    for p in state.projects:
        remaining = max(0.0, p.scope - p.delivered)
        if p.kind == "granary":
            out[p.region] = out.get(p.region, 0.0) + min(per_turn, remaining) * timber_rate
        else:
            out[p.region] = out.get(p.region, 0.0) + min(float(R.MAX_CREW), remaining) * R.WORKSHOP_TIMBER_PER_WORK
    return out


def works_proposal(world, civ: int, obs) -> list[dict]:
    """The works' own L9 proposal (service ``infrastructure_works``, claim
    ``infrastructure:<civ>``), never pooled with RS2's: next turn's planned
    work of ``civ``'s open **irrigation** works at their current inputs, its
    cost in whole units (its own rounding: the works are charged on their own)
    and the commons' food at risk it relieves (the declared rule of
    :func:`food_at_risk_relieved`). Screened out before proposing, as RS2
    skips granaries without farm labour: works in a region with no farmer
    after this turn's agent tick (``no_labor``), works whose region's storage
    is set to ask for work next turn (``granary_first``, predicted from the
    current storage policy), works without free timber after RS2's open
    projects' needs (``no_timber``), and roads (no relief measure; with L9
    they have no envelope). The detail records the cost, the work, the relief
    and every screened work, so the proposal can be audited."""
    state = _state(world)
    if not _works_on(world, state) or obs.economy is None:
        return []
    works = sorted((w for w in state.works if _controller(world, w.region) == civ), key=_order)
    if not works:
        return []
    from chronicler import repair_projects as R
    from chronicler.local_budgets import _parameters
    horizon = _parameters(world)["horizon"]
    ledger = getattr(obs.economy, "food_ledger", None) or {}
    seen = state._labour
    labour = seen[1] if seen is not None and seen[0] == world.turn else None
    rs2_regions = R.storage_suspended_regions(world)
    held = _rs2_timber_estimate(world)
    milli, work_sum, commons, regions, wids = 0, 0.0, 0.0, set(), []
    screened = {"roads": 0, "no_labor": 0, "granary_first": 0, "no_timber": 0}
    for w in works:
        asset = _asset(state, w.aid)
        remaining = max(0.0, w.scope - w.delivered)
        if asset is None or remaining <= DONE:
            continue
        if w.kind != "irrigation":
            screened["roads"] += 1
            continue
        if labour is not None and labour[w.region] == 0:
            screened["no_labor"] += 1
            continue
        if w.region not in rs2_regions and _storage_policy_works(world, w.region):
            screened["granary_first"] += 1
            continue
        rate = TIMBER_PER_WORK[w.kind]
        free = R._free_timber(world, w.region, obs.held, held.get(w.region, 0.0))
        amount = min(WORK_PER_TURN, remaining, free / rate)
        if amount < MIN_PROPOSAL_WORK:
            screened["no_timber"] += 1
            continue
        milli += _coin_milli(amount, w.kind)
        held[w.region] = held.get(w.region, 0.0) + amount * rate
        row = ledger.get(w.region)
        produced = float(row[1]) if row is not None and len(row) > 1 else 0.0
        commons += food_at_risk_relieved(world, w.region, asset.condition, amount, horizon, produced)
        work_sum += amount
        regions.add(w.region)
        wids.append(w.wid)
    cost = -(-milli // MILLI)
    if cost < 1 or work_sum < MIN_PROPOSAL_WORK:
        return []
    relief = {"commons": commons} if commons > EPS else {}
    detail = {"works": len(wids), "cost_milli": milli, "work": round(work_sum, 6),
              "food_at_risk_relieved": round(commons, 6),
              **{f"screened_{k}": v for k, v in screened.items()}}
    return [dict(service=BUDGET_SERVICE, recipients=sorted(regions), claims=[f"infrastructure:{civ}"], cost=cost,
                 divisible=True, unit="work", expected=work_sum, relief=relief, detail=detail)]


def works_settlement(world, c, obs) -> dict:
    """The observed delivery of a works envelope (this turn's works ledger and
    receipts of the civ's irrigation works, the only ones it funds)."""
    from chronicler.local_budgets import KEPT_RATIO
    state = _state(world)
    if not _works_on(world, state):
        return {"outcome": "deferred", "reason": "service_off", "spent": 0, "delivered": 0.0, "ratio": 0.0}
    t = state._turn
    if t is None or t.turn != world.turn or not t.finished:
        reason = "no_economy" if obs.economy is None else "service_off"
        return {"outcome": "deferred", "reason": reason, "spent": 0, "delivered": 0.0, "ratio": 0.0}
    row = next((r for r in t.ledger if r.civ == c.civ), None)
    mine = [r for r in t.receipts if r.payer == c.civ and r.kind == "irrigation"]
    if row is None or not mine:
        return {"outcome": "deferred", "reason": "recipient_lost", "spent": 0, "delivered": 0.0, "ratio": 0.0}
    spent = int(row.charged)
    delivered = math.fsum(r.delivered for r in mine)
    ratio = min(1.0, delivered / c.expected) if c.expected > EPS else 0.0
    done = all(r.remaining_after <= DONE for r in mine)
    detail = {"works": len(mine), "charged": spent, "prepaid_after_milli": row.prepaid_after_milli}
    if ratio >= KEPT_RATIO or spent >= KEPT_RATIO * c.amount or done:
        return {"outcome": "kept", "reason": None, "spent": spent, "delivered": delivered,
                "ratio": 1.0 if done else ratio, "detail": detail}
    reasons = [reason for r in mine for reason in r.reasons]
    reason = ("inputs_short" if "no_timber" in reasons else "work_short" if ("no_labor" in reasons
              or "granary_first" in reasons) else "treasury_shortfall" if "no_coins" in reasons else "work_short")
    return {"outcome": "deferred", "reason": reason, "spent": spent, "delivered": delivered,
            "ratio": ratio, "detail": detail}


class _WorksBudget:
    """L9 provider (``chronicler.local_budgets.PROVIDERS``): the works' own
    service ``infrastructure_works`` in the ``repairs`` group it shares with
    RS2 (one fixed share under ``fixed_shares``). Phase 2 spends only within
    the envelope (:func:`plan_phase2`)."""

    services = (BUDGET_SERVICE,)
    group = "repairs"

    def active(self, world) -> bool:
        return _works_on(world, _state(world))

    def proposals(self, world, civ, obs):
        return works_proposal(world, civ, obs)

    def install(self, world, commitments) -> None:
        return None

    def settle(self, world, c, obs):
        return works_settlement(world, c, obs)

    def obligations(self, world, civ, obs) -> int:
        return 0


#: The L9 provider instance (``"chronicler.infrastructure_condition:BUDGET_PROVIDER"``).
BUDGET_PROVIDER = _WorksBudget()


# ---------------------------------------------------------------------------
# Phase 10: registry, responsibility, wear, works lifecycle and the frame
# ---------------------------------------------------------------------------

def phase10_before_reserves(world, acc, economy_result, agent_bridge):
    """Reconcile the registry with the records (after BUILD, conquest and
    every destroyer of the turn), move responsibility, apply the turn's wear,
    then (work modes) abandon, inherit and open works before the L9 decision
    of this Phase 10."""
    state = _state(world)
    turn = world.turn
    reconcile(world)
    for asset in state.assets:
        ctrl = _controller(world, asset.region)
        if ctrl != asset.responsible:
            _note(asset, turn, "responsibility", ctrl, asset.responsible)
            asset.responsible = ctrl
            _bump(state, "responsibility_moved")
    if state.wear_turn != turn:
        for asset in state.assets:
            if asset.status != "serving":
                continue
            amount = min(asset.condition, WEAR[asset.kind])
            asset.wear += amount
            _set_condition(state, asset, asset.condition - amount, turn)
            _bump(state, "wear", round(amount, 9))
            _bump(state, f"wear_{asset.kind}", round(amount, 9))
        state.wear_turn = turn
    unmet = []
    state._labour = None
    if _works_on(world, state) and getattr(world.livelihoods, "local_budgets", None) is not None:
        # Farmers per region after this turn's agent tick (the pool the next
        # Phase 2 reads), for the L9 proposal's screen; None when unreadable.
        from chronicler.repair_projects import _farm_labour
        getter = getattr(agent_bridge, "get_snapshot", None) if agent_bridge is not None else None
        state._labour = (turn, _farm_labour(world, getter()) if callable(getter) else None)
    if _works_on(world, state):
        for work in list(state.works):
            if _asset(state, work.aid) is None:
                _close(state, work, turn, "abandoned", "asset_lost")
                continue
            ctrl = _controller(world, work.region)
            if ctrl < 0:
                _close(state, work, turn, "abandoned", "no_controller")
            elif ctrl != work.controller:
                _note(work, turn, "controller", ctrl)
                work.controller = ctrl
                _bump(state, "inherited")
        for asset in state.assets:
            if _open_work(state, asset.aid) is not None:
                continue
            damage = [d for d in state.damages if d.aid == asset.aid and d.work is None]
            cond = asset.condition
            if not (cond < OPEN_BELOW - EPS or (damage and cond < 1.0 - EPS)):
                continue
            ctrl = _controller(world, asset.region)
            if ctrl < 0:
                unmet.append(UnmetWork(aid=asset.aid, kind=asset.kind, region=asset.region, condition=cond,
                                       reason="no_controller"))
                _bump(state, "unmet_no_controller")
                continue
            cause = ("flood" if damage and damage[-1].event == "flood" else "war") if damage else "wear"
            work = InfraWork(wid=state.next_wid, aid=asset.aid, kind=asset.kind, region=asset.region, cause=cause,
                             opened_turn=turn, opened_condition=cond, controller=ctrl,
                             scope=(1.0 - cond) * WORK_PER_CONDITION[asset.kind])
            state.next_wid += 1
            for d in damage:
                d.work = work.wid
                work.damages.append(d.did)
            keyed = [d for d in damage if d.war_key is not None]
            if keyed:
                work.war_key, work.war_start_turn = keyed[-1].war_key, keyed[-1].war_start_turn
            _note(work, turn, f"opened_{cause}", ctrl, round(work.scope * MILLI))
            state.works.append(work)
            _bump(state, f"opened_{cause}")
            _bump(state, f"opened_{asset.kind}")
        _write_off(state, [civ for civ in sorted(state.prepaid)
                           if not 0 <= civ < len(world.civilizations) or not world.civilizations[civ].regions])
    state.unmet = unmet
    return []


def phase10(world, acc, economy_result, agent_bridge):
    """Close the turn's frame (dated to this turn)."""
    state = _state(world)
    _observe_food_at_risk(world, state, economy_result)
    t = state._turn
    if t is not None and t.turn == world.turn and t.finished:
        state.receipts, state.ledger = t.receipts, t.ledger
        state.shared = sorted(t.shared)
        state.last_settled_turn = world.turn
        _bump(state, "settled_turns")
    else:
        state.receipts, state.ledger, state.shared = None, None, []
    state.frame_turn = world.turn
    state._turn = None
    return []


def snapshot_summary(world) -> dict:
    """The completed-turn observation (``livelihoods.infrastructure_condition``):
    every serving or failed asset with its condition and the service consumers
    read, recent terminal assets, open and recent closed works, recent damage,
    that turn's receipts and per-civ ledger (None: no settled Phase 2, unknown
    rather than zero; always None in ``record_only``/``wear_only``), unmet
    needs; never final state."""
    state = _state(world)
    source = world.turn - 1
    fresh = state.frame_turn == source
    forced = state.mode == "record_only"

    def asset_row(a: InfraAsset) -> dict:
        row = a.model_dump()
        row["service"] = 1.0 if forced or a.status not in ("serving", "failed") else service_of(a.condition)
        row["condition_service"] = service_of(a.condition) if a.status in ("serving", "failed") else 0.0
        return row

    from chronicler.repair_projects import _damage_scale
    return {
        "schema_version": 1, "stage": "B3", "mode": state.mode, "source_turn": source,
        "works_enabled": state.mode in WORK_MODES,
        "units": {"money": "milli_treasury_units", "work": "work_units", "timber": "loads", "milli": MILLI},
        "assets": [asset_row(a) for a in state.assets],
        "terminal": [asset_row(a) for a in state.terminal],
        "works": [w.model_dump() for w in state.works],
        "closed": [w.model_dump() for w in state.closed],
        "damages": [d.model_dump() for d in state.damages],
        "receipts": [r.model_dump() for r in state.receipts] if fresh and state.receipts is not None else None,
        "ledger": [r.model_dump() for r in state.ledger] if fresh and state.ledger is not None else None,
        "unmet": [u.model_dump() for u in state.unmet] if fresh else None,
        "shared": list(state.shared) if fresh else None,
        "prepaid": {str(civ): amount for civ, amount in sorted(state.prepaid.items())},
        "sink_milli": int(state.book.sinks.get(SINK, 0)),
        "counters": dict(state.counters),
        "parameters": {"wear": dict(WEAR), "service_full": SERVICE_FULL, "service_gate": SERVICE_GATE,
                       "open_below": OPEN_BELOW, "work_per_condition": dict(WORK_PER_CONDITION),
                       "work_per_turn": WORK_PER_TURN, "timber_per_work": dict(TIMBER_PER_WORK),
                       "coin_milli_per_work": dict(COIN_MILLI_PER_WORK),
                       "war_damage": WAR_DAMAGE * (_damage_scale(world) if state.enabled else 1.0),
                       "flood_damage_per_excess": FLOOD_DAMAGE_PER_EXCESS, "flood_damage_cap": FLOOD_DAMAGE_CAP},
    }
