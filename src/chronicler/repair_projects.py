"""RS2 maintenance, reconstruction and repair projects (``--repair-projects``, default off).

Requires ``--agents hybrid`` and ``--workshops`` or ``--grain-storage``;
workshop sites are repaired only in workshop ``operate`` mode. Modes (``--repair-mode``): ``repair`` (default) and the
cost-retaining control ``cost_only`` (projects reserve, pay and use timber
identically, and condition does not change).

Assets. The bounded asset set: L1 workshop sites (``--workshops`` in operate
mode) and public granaries (``--grain-storage``). Nothing else is repaired.

Projects. In Phase 10 (before the granaries' own tick, so the L9 decision of
the same Phase 10 sees them) a project opens for an asset whose condition is
below ``OPEN_BELOW`` (cause ``wear``), or that carries an unrepaired
war-damage record and any deficit (cause ``war``), when the region has a
controlling civilization to bill. One open project per asset. Its scope is
the actual deficit, ``(1 - condition) x WORK_PER_CONDITION`` work units (40
for a granary, the storage channel's own rate of 4 work per 0.1; 8 for a
workshop), so no work is ever planned beyond the 1.0 cap; each delivered
unit credits ``1 / WORK_PER_CONDITION`` condition pro rata. War damage to an
asset with an open project extends its scope by the damage and makes it a
reconstruction (``war``). The project completes when its scope has been
delivered; it is abandoned when its asset closes (the workshop site closed,
storage or operate-mode workshops switched off), when its region is left
without a controller, or when the switch is turned off. A change of
controller does not end it: the new controller inherits the open project
(as L1 arrears pass to a conqueror) and pays for further work; delivered
work stays credited.

Granary labour uses the existing native storage-work channel (anonymous
farmer-equivalent work removed from farming, ``granary_work_requested``):
a region with an open granary project has its ordinary storage request
(maintain or expand) suspended for that turn (``grain_storage`` seam), so
nothing is planned, done or paid twice; the project requests ``min(
GRANARY_WORK_PER_TURN, remaining scope, free timber, coins, envelope)`` and
the native economy delivers at most the farmers' labour. Zero-capacity
granaries get no project. Each delivered unit uses one timber and costs
``COINS_PER_WORK`` coins (the storage rule), charged once per civilization
per turn (each row rounded up to the milli-unit, the civ total once to a
whole unit, its remainder prepaid toward the next turn), never per region.

Workshop labour is a named crew of at most ``MAX_CREW`` adult urban farmers
resident in the site's settlement, reserved in the shared native work
registry under category ``repair`` before the L1 crew planner runs (the
``workshops`` seam next to the RS1 seats), so a repairer is never also crew,
an apprentice, a learner, a carer or teacher. Candidates come from the
native planner (living, resident, not on a trip, not enlisted, not holding
health or teaching work, then not holding a registry reservation), with
qualified people first (``apprenticeship.qualified_ids`` while RS1 is
active), veterans first among them and then (``veteran_reintegration.
priority_ids`` while RS3 is active). Each works the city's diverted share
``d = 1 - URBAN_FARM_LABOR[rank]``; a crew with a qualified member works at
rate 1, otherwise at ``UNQUALIFIED_RATE`` (so without RS1 every crew is
unqualified). The crew is sized to the remaining scope, the free timber of
the site's region and the coins. Each repairer is paid
``round(d x WAGE_PER_WORK)`` milli-units (purpose ``repair_wage``) from the
controller's treasury by stable id through ``AgentSimulator.transfer_wealth``
in Phase 2 after the economy tick, and the same share ``d`` of ordinary
income is withheld by the next wealth phase (``extend_paid_work``), so the
wage replaces that income instead of adding to it. Each work unit uses
``WORKSHOP_TIMBER_PER_WORK`` timber. With RS2 owning workshops the L1 lump
repair is disabled (:func:`legacy_workshop_repair_allowed`); a site below
``OPERATE_CONDITION`` stays shut until its project has restored it.

Timber is held from the region's free stock (stockpile minus merchant
commitments) before the native economy runs (the packed ``stockpile_timber``
column and the world stock together, as storage holds before packing) and
the unused part is returned after the tick. Coins are planned against the
projected treasury after every bill planned earlier in Phase 2 (storage,
L1 upper bounds before workshop repairs; storage, L1 funded bills, L8
warden bills and workshop repairs before granary repairs) and charged once
after the economy tick (accumulator ``keep``); a failed tick charges nothing.
Planned bills are visible to later planners through
``workshops._pending_storage_bills`` (:func:`pending_bills`). With
``--local-budgets`` all repair spending of a civilization (wages and coin
costs, hence the timber it funds) stays within its ``repairs`` envelope
(:mod:`chronicler.local_budgets`); without one its projects stall
(``no_envelope``).

War damage (record only at existing real events; no new combat): a region
conquest (``action_engine.apply_region_conquest``) takes ``WAR_DAMAGE``
condition from the region's granary and workshop site, a city sack
(``cities._sack``) from the city's workshop site and its region's granary,
and a granary seizure by an occupying or besieging army
(``war.occupation._requisition``) from the granary. Each asset takes at most
one damage record per turn. The cause is ``(war_key, war_start_turn)`` of the
war between the parties when one is found. The tuning key
``repair_projects.war_damage`` scales the damage (default 1; 0 disables it),
the screen ablation. Damage applies in both modes.

Consumers are unchanged: a granary's usable capacity and extra spoilage, a
workshop's ``OPERATE_CONDITION`` gate (and RS1 wear).

Closure, every turn and civilization: the treasury pays whole units once,
and the sub-unit remainder of the last unit is prepaid toward the civ's next
repair costs, so rounding never accumulates: ``charged x 1000 + prepaid
before == coin costs + wages applied + prepaid after`` (balances in [0,
1000), written off when the civ has no regions or the switch is turned
off). Timber used equals the work delivered times its timber rate and the
timber held is used or returned. All parameters are declared modeling choices, not calibrated.
"""
from __future__ import annotations

import math
from importlib import import_module

from chronicler.repair_projects_state import (
    MAX_CLOSED, MAX_CREW, MAX_DAMAGES, MAX_HISTORY, MODES, CivLedger, RepairProject,
    RepairProjectsState, RepairReceipt, UnmetNeed, WarDamage,
)

MILLI = 1000
#: A wear project opens below this condition (both kinds).
OPEN_BELOW = 0.75
#: Workshop repair work (crew diverted time) to restore a whole unit of condition.
WORKSHOP_WORK_PER_CONDITION = 8.0
WORKSHOP_TIMBER_PER_WORK = 1.0
#: Work rate of a crew without a qualified member (RS1).
UNQUALIFIED_RATE = 0.5
#: Wage per unit of paid time (one person's whole turn), milli-units (L6a's rate).
WAGE_PER_WORK = 500
#: Condition one real war event takes from an asset, times ``repair_projects.war_damage``.
WAR_DAMAGE = 0.25
#: Native ``wealth_transfer::PURPOSES`` index of repair wages.
PURPOSE_REPAIR_WAGE = 3
#: Native ``workshop_work::RESERVATION_CATEGORIES`` index of repair crews.
CATEGORY_REPAIR = 3
TUNING_WAR_DAMAGE = "repair_projects.war_damage"
EPS = 1e-9
#: Remaining work below this is delivered (the f32 resolution of native work requests).
DONE = 1e-6

_NATIVE = ("reserve_work", "work_reservations", "extend_paid_work", "transfer_wealth",
           "cancel_paid_work", "take_paid_work_receipt")


def _storage_rules():
    """The storage channel's own rates (``grain_storage``): work per unit of
    condition, per-turn cap, timber and coins per work."""
    from chronicler import grain_storage as G
    return G.REPAIR_WORK / G.REPAIR_GAIN, G.MAX_WORK_BUDGET, G.TIMBER_PER_WORK, G.COINS_PER_WORK


def work_per_condition(kind: str) -> float:
    return _storage_rules()[0] if kind == "granary" else WORKSHOP_WORK_PER_CONDITION


# ---------------------------------------------------------------------------
# Switch and lookups
# ---------------------------------------------------------------------------

class _Work:
    """One project's planned work this turn (never persisted)."""

    __slots__ = ("project", "kind", "payer", "region", "reasons", "request", "rate", "crew", "share",
                 "wage", "qualified", "veterans", "hold", "envelope", "condition_before", "planned_milli")

    def __init__(self, project, payer, condition_before):
        self.project, self.kind, self.payer = project, project.kind, payer
        self.region = project.region
        self.reasons: list[str] = []
        self.request = 0.0
        self.rate = None
        self.crew: list[int] = []
        self.share = None
        self.wage = 0
        self.qualified: list[int] = []
        self.veterans: list[int] = []
        self.hold = 0.0
        self.envelope = None
        self.condition_before = condition_before
        self.planned_milli = 0


class _Turn:
    """One turn in flight, from Phase 2 to Phase 10 (never checkpointed)."""

    def __init__(self, turn: int, sim):
        self.turn, self.sim = turn, sim
        self.seam = False                 # the workshop crew seam ran
        self.prepared = False             # timber held, columns written
        self.finished = False             # charged and credited
        self.work: dict[int, _Work] = {}
        self.holds: dict[int, float] = {}
        self.installed = False
        self.receipt: dict | None = None
        self.receipts: list[RepairReceipt] = []
        self.ledger: list[CivLedger] = []
        self.suspended: list[int] = []


def _state(world) -> RepairProjectsState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "repair_projects", None) if container is not None else None


def _bump(state, key: str, amount=1) -> None:
    state.counters[key] = state.counters.get(key, 0) + amount


def _note(project: RepairProject, turn: int, event: str, civ: int, amount: int = 0) -> None:
    project.history.append((turn, event, civ, int(amount)))
    del project.history[:-MAX_HISTORY]


def _close(state, project: RepairProject, turn: int, status: str, reason: str | None) -> None:
    project.status, project.closed_turn, project.closed_reason = status, turn, reason
    _note(project, turn, status if reason is None else f"{status}_{reason}", project.controller)
    project.last_crew = []
    state.projects = [p for p in state.projects if p is not project]
    state.closed.append(project)
    del state.closed[:-MAX_CLOSED]
    _bump(state, status if reason is None else f"{status}_{reason}")


def set_repair_projects_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable (with ``--repair-mode``, default ``repair``) or disable; an
    omitted mode keeps the saved one. Disabling abandons open projects."""
    mode = getattr(args, "repair_mode", None) if args is not None else None
    state = _state(world)
    if state is None:
        world.livelihoods.repair_projects = state = RepairProjectsState(mode=mode or MODES[0])
    else:
        t = getattr(state, "_turn", None)
        if t is not None and t.turn == getattr(world, "turn", None) and t.prepared:
            raise RuntimeError("cannot change repair projects while a turn is pending")
        if mode is not None:
            state.mode = mode
    if not value and state.enabled:
        for project in list(state.projects):
            _close(state, project, getattr(world, "turn", 0), "abandoned", "switched_off")
        _write_off(state, list(state.prepaid))
    state.enabled = bool(value)


def _write_off(state, civs) -> None:
    for civ in civs:
        amount = state.prepaid.pop(civ, 0)
        if amount:
            _bump(state, "prepaid_written_off_milli", amount)


def _grain_storage_on(world) -> bool:
    from chronicler.grain_reserves_state import grain_reserves_on
    return grain_reserves_on(world) and getattr(world.grain_reserves, "storage", None) is not None


def _workshops_operate(world) -> bool:
    from chronicler.workshops import workshops_active
    return workshops_active(world) and world.livelihoods.workshops.mode == "operate"


def repair_projects_active(world) -> bool:
    """Enabled in a hybrid run with workshops (any mode) or grain storage. The
    workshop half acts only on operate-mode sites (:func:`_sites`); in observe
    or cost-only workshop mode RS2 repairs granaries only and the L1 lump
    repair stays in force."""
    state = _state(world)
    if state is None or not state.enabled or getattr(world, "agent_mode", None) != "hybrid":
        return False
    from chronicler.workshops import workshops_active
    return workshops_active(world) or _grain_storage_on(world)


def _lane_active(world, name: str) -> bool:
    if getattr(getattr(world, "livelihoods", None), name, None) is None:
        return False
    return bool(getattr(import_module("chronicler." + name), f"{name}_active")(world))


def _storage(world):
    return world.grain_reserves.storage if _grain_storage_on(world) else None


def _sites(world) -> dict:
    """Open L1 sites by id while RS2 owns workshop repair (operate mode)."""
    if not _workshops_operate(world):
        return {}
    return {s.site: s for s in world.livelihoods.workshops.sites}


def _built(site) -> bool:
    from chronicler.workshops import CONSTRUCTION_COST
    return site.asset in ("open", "idle") and site.construction_paid >= CONSTRUCTION_COST


def _controller(world, region: int) -> int:
    name = world.regions[region].controller
    if name is None:
        return -1
    for i, civ in enumerate(world.civilizations):
        if civ.name == name:
            return i if getattr(civ, "regions", None) else -1
    return -1


def _condition(world, kind: str, asset: int) -> float | None:
    if kind == "granary":
        storage = _storage(world)
        if storage is None or not 0 <= asset < len(storage.assets) or storage.assets[asset] is None:
            return None
        return float(storage.assets[asset].condition)
    site = _sites(world).get(asset)
    return None if site is None else float(site.condition)


def _set_condition(world, kind: str, asset: int, value: float) -> None:
    value = min(1.0, max(0.0, value))
    if kind == "granary":
        world.grain_reserves.storage.assets[asset].condition = value
    else:
        _sites(world)[asset].condition = value


def _open_project(state, kind: str, asset: int) -> RepairProject | None:
    return next((p for p in state.projects if p.kind == kind and p.asset == asset), None)


def _diverted(world, site) -> float:
    from chronicler.workshops import _diverted as diverted
    city = next((c for c in world.cities.cities if c.settlement_id == site.settlement_id), None)
    return float(diverted(int(city.rank) if city is not None else 1))


def _wage(share: float) -> int:
    return math.floor(share * WAGE_PER_WORK + 0.5)


def _coin_milli(work: float) -> int:
    """Coin cost of granary work, rounded up to the milli-unit (never down)."""
    coins = _storage_rules()[3]
    return max(0, math.ceil(work * coins * MILLI - 1e-6))


def _commitments(world, sim) -> dict:
    from chronicler.mutual_aid import read_stockpile_commitments
    return read_stockpile_commitments(world, sim)


def _free_timber(world, region: int, commitments: dict, held: float) -> float:
    r = world.regions[region]
    stock = float(r.stockpile.goods.get("timber", 0.0))
    committed = float(commitments.get(r.name, {}).get("timber", 0.0))
    if not all(math.isfinite(x) and x >= 0 for x in (stock, committed)):
        raise ValueError("invalid timber stock or merchant commitment")
    return max(0.0, stock - committed - held)


def _envelope(world, civ: int) -> int | None:
    from chronicler.local_budgets import envelope   # L9 repairs envelope (None: no budget rule)
    return envelope(world, civ, "repairs")


# ---------------------------------------------------------------------------
# Cross-lane and seam API
# ---------------------------------------------------------------------------

def legacy_workshop_repair_allowed(world) -> bool:
    """RS0 seam: whether the L1 lump repair may still be billed. False while
    RS2 owns workshop repair (active, with workshops in operate mode): project
    work is then the only thing that moves a site's condition."""
    return not (repair_projects_active(world) and _workshops_operate(world))


def storage_suspended_regions(world) -> frozenset[int]:
    """``grain_storage`` seam: regions whose granary has an open project; their
    ordinary storage request is suspended this turn and the native work
    channel belongs to the project. Empty while inactive."""
    state = _state(world)
    if state is None or not repair_projects_active(world) or _storage(world) is None:
        return frozenset()
    return frozenset(p.region for p in state.projects if p.kind == "granary")


def pending_bills(world) -> list[int]:
    """Whole units each civ's planned, not yet charged repair work will cost
    (``workshops._pending_storage_bills`` adds them for later planners)."""
    out = [0] * len(world.civilizations)
    state = _state(world)
    t = getattr(state, "_turn", None) if state is not None else None
    if t is None or t.turn != world.turn or t.finished:
        return out
    milli = [0] * len(out)
    for w in t.work.values():
        if 0 <= w.payer < len(milli):
            milli[w.payer] += w.planned_milli
    return [-(-m // MILLI) for m in milli]


def _begin(world, state, sim) -> _Turn:
    t = state._turn
    if t is not None and t.turn == world.turn:
        if t.finished:
            raise RuntimeError("repair projects already settled for this turn")
        return t
    if state.last_settled_turn is not None and world.turn <= state.last_settled_turn:
        raise RuntimeError("repair projects already settled for this turn")
    t = state._turn = _Turn(world.turn, sim)
    return t


def _native(agent_bridge):
    sim = getattr(agent_bridge, "_sim", None)
    if sim is None or not all(callable(getattr(sim, name, None)) for name in _NATIVE):
        raise RuntimeError("repair projects require a fresh native build with the RS0 work registry")
    return sim


def _priority(world, regions) -> tuple[list[int], set[int], set[int]]:
    """One planner priority list: per site region, qualified veterans, the
    qualified, then veterans (each list only while its lane is active)."""
    qualified_on = _lane_active(world, "apprenticeship")
    veterans_on = _lane_active(world, "veteran_reintegration")
    out, seen, qualified, veterans = [], set(), set(), set()
    for region in regions:
        q = []
        v = []
        if qualified_on:
            from chronicler.apprenticeship import qualified_ids
            q = [int(a) for a in qualified_ids(world, region)]
        if veterans_on:
            from chronicler.veteran_reintegration import priority_ids
            v = [int(a) for a in priority_ids(world, region)]
        qualified.update(q)
        veterans.update(v)
        qs = set(q)
        for aid in [a for a in v if a in qs] + q + v:
            if aid not in seen:
                seen.add(aid)
                out.append(aid)
    return out, qualified, veterans


def _pending_storage_raw(world) -> list[int]:
    """The pending storage plan's own bill per civ (upper bound), as
    ``workshops._pending_storage_bills`` computes it without RS2."""
    bills = [0] * len(world.civilizations)
    storage = getattr(getattr(world, "grain_reserves", None), "storage", None)
    plan = getattr(storage, "_active_plan", None) if storage is not None else None
    if plan is not None and plan.status == "pending":
        coins = _storage_rules()[3]
        for row in plan.rows:
            if row.owner >= 0 and row.request:
                bills[row.owner] += math.ceil(row.request * coins)
    return bills


def before_crews(world, sim, requests: list, acc=None) -> None:
    """``workshops`` seam (after the RS1 seats, before the L1 crew planner):
    plan and reserve each open workshop project's named repair crew.

    Coins are planned after the storage plan and an upper bound of every L1
    bill of the payer (L1 upkeep comes first); the planned wage bill is then
    visible to the L1 funding and later planners (:func:`pending_bills`)."""
    state = _state(world)
    if state is None or not repair_projects_active(world) or not _workshops_operate(world):
        return
    projects = [p for p in state.projects if p.kind == "workshop"]
    if not projects:
        return
    t = _begin(world, state, sim)
    if t.seam:
        raise RuntimeError("repair crews already planned for this turn")
    t.seam = True
    sites = _sites(world)
    for p in list(projects):
        site = sites.get(p.asset)
        if site is None or not _built(site):
            _close(state, p, world.turn, "abandoned", "asset_closed")
            projects.remove(p)
        elif _controller(world, site.region) < 0:
            _close(state, p, world.turn, "abandoned", "no_controller")
            projects.remove(p)
    if not projects:
        return
    if not all(callable(getattr(sim, name, None)) for name in _NATIVE):
        raise RuntimeError("repair projects require a fresh native build with the RS0 work registry")
    from chronicler.mutual_aid import _treasury_budget
    from chronicler.workshops import _bill, _enlisted
    budgets = [max(0, math.floor(_treasury_budget(world, c, acc))) for c in world.civilizations]
    storage = _pending_storage_raw(world)
    upper = [0] * len(budgets)
    for site in sites.values():
        payer = _controller(world, site.region)
        if payer >= 0:
            upper[payer] += sum(_bill(site, world).values())
    budgets = [max(0, b - storage[i] - upper[i]) for i, b in enumerate(budgets)]
    commitments = _commitments(world, sim)
    turn = world.turn
    held = {aid for aid, _cat, _f in sim.work_reservations(turn)}
    priority, qualified, veterans = _priority(world, [sites[p.asset].region for p in projects])
    asks = [(sites[p.asset].site, sites[p.asset].region, sites[p.asset].settlement_id,
             float(_diverted(world, sites[p.asset])), 8) for p in projects]
    if priority:
        planned = sim.plan_workshop_crews(asks, _enlisted(world), None, priority_ids=priority)
    else:
        planned = sim.plan_workshop_crews(asks, _enlisted(world), None)
    milli = [0] * len(budgets)
    for p, ask, row in zip(projects, asks, planned, strict=True):
        site = sites[p.asset]
        payer = _controller(world, site.region)
        w = t.work[p.pid] = _Work(p, payer, float(site.condition))
        d = ask[3]
        candidates = [int(a) for a in row[8] if int(a) not in held]
        rate = 1.0 if candidates and candidates[0] in qualified else UNQUALIFIED_RATE
        remaining = max(0.0, p.scope - p.delivered)
        per = d * rate
        want = min(MAX_CREW, math.ceil(remaining / per - EPS)) if remaining > DONE else 0
        wage = _wage(d)
        free = _free_timber(world, site.region, commitments, t.holds.get(site.region, 0.0))
        limits = {
            "no_labor": len(candidates),
            "no_timber": math.ceil(min(remaining, free / WORKSHOP_TIMBER_PER_WORK) / per - EPS)
            if free > EPS else 0,
            "no_coins": max(0, budgets[payer] * MILLI - milli[payer]) // wage if wage > 0 else MAX_CREW,
        }
        env = _envelope(world, payer)
        w.envelope = env
        if env is not None:
            limits["no_envelope"] = max(0, env * MILLI - milli[payer]) // wage if wage > 0 else MAX_CREW
        n = max(0, min([want, *limits.values()]))
        w.reasons = [reason for reason, value in limits.items() if value < want]
        if rate < 1.0:
            w.reasons.append("unqualified")
        w.rate, w.share, w.wage = rate, d, wage
        w.qualified = [a for a in candidates[:n] if a in qualified]
        w.veterans = [a for a in candidates[:n] if a in veterans]
        if n <= 0:
            continue
        crew = candidates[:n]
        sim.reserve_work(turn, CATEGORY_REPAIR, [(aid, d) for aid in crew])
        held.update(crew)
        w.crew = crew
        w.request = min(n * per, remaining, free / WORKSHOP_TIMBER_PER_WORK)
        w.hold = w.request * WORKSHOP_TIMBER_PER_WORK
        t.holds[site.region] = t.holds.get(site.region, 0.0) + w.hold
        w.planned_milli = n * wage
        milli[payer] += w.planned_milli


def granary_seized(world, region) -> None:
    """``war.occupation._requisition`` hook: an occupying or besieging army
    seized grain from the region's granary (no-op unless active)."""
    state = _state(world)
    if state is None or not repair_projects_active(world):
        return
    rid = _region_index(world, region)
    if rid is None:
        return
    key = None
    occ = next((o for o in world.war_state.occupations if o.region == region.name), None)
    if occ is not None:
        key = occ.war_key
    else:
        sieging = sorted((a for a in world.war_state.armies if a.region == region.name and a.phase == "sieging"),
                         key=lambda a: a.army_id)
        key = sieging[0].war_key if sieging else None
    key, start = _war_identity(world, None, None, key)
    _damage(world, state, "granary", rid, rid, "seizure", key, start)


def region_conquered(world, region, attacker: str | None, defender: str | None) -> None:
    """``action_engine.apply_region_conquest`` hook: the region's granary and
    workshop site are damaged (no-op unless active)."""
    state = _state(world)
    if state is None or not repair_projects_active(world):
        return
    rid = _region_index(world, region)
    if rid is None:
        return
    key, start = _war_identity(world, attacker, defender)
    _damage(world, state, "granary", rid, rid, "conquest", key, start)
    for site in sorted(_sites(world).values(), key=lambda s: s.site):
        if site.region == rid:
            _damage(world, state, "workshop", site.site, rid, "conquest", key, start)


def city_sacked(world, settlement_id: int, region: int, sacker: str | None, victim: str | None) -> None:
    """``cities._sack`` hook (a real plunder, after the sack cooldown): the
    city's workshop site and its region's granary are damaged."""
    state = _state(world)
    if state is None or not repair_projects_active(world):
        return
    key, start = _war_identity(world, sacker, victim)
    _damage(world, state, "granary", region, region, "sack", key, start)
    for site in sorted(_sites(world).values(), key=lambda s: s.site):
        if site.settlement_id == settlement_id:
            _damage(world, state, "workshop", site.site, region, "sack", key, start)


def _region_index(world, region) -> int | None:
    return next((i for i, r in enumerate(world.regions) if r is region), None)


def _war_identity(world, a: str | None, b: str | None, key: str | None = None):
    """``(war_key, start_turn)`` of the war between ``a`` and ``b`` (or named by
    ``key``): an active campaign record, a war ended this turn, or the
    aggregate war's start; (None, None) when none is found."""
    if key is None:
        if not a or not b or a == b:
            return None, None
        from chronicler.politics import war_key
        key = war_key(a, b)
    ws = getattr(world, "war_state", None)
    for war in getattr(ws, "wars", []) or []:
        if war.war_key == key:
            return key, int(war.start_turn)
    ended = [w for w in getattr(ws, "ended_wars", []) or []
             if w.war_key == key and w.ended_turn is not None and w.ended_turn >= world.turn - 1]
    if ended:
        return key, int(max(ended, key=lambda w: w.start_turn).start_turn)
    start = (getattr(world, "war_start_turns", None) or {}).get(key)
    if start is not None:
        return key, int(start)
    return None, None


def _damage_scale(world) -> float:
    from chronicler.tuning import get_override
    scale = float(get_override(world, TUNING_WAR_DAMAGE, 1.0))
    if not math.isfinite(scale) or scale < 0:
        raise ValueError(f"{TUNING_WAR_DAMAGE} must be finite and >= 0")
    return scale


def _damage(world, state, kind: str, asset: int, region: int, event: str, key, start) -> None:
    amount = WAR_DAMAGE * _damage_scale(world)
    if amount <= 0:
        return
    turn = world.turn
    if any(d.turn == turn and d.kind == kind and d.asset == asset for d in state.damages):
        return                                        # one damage per asset per turn
    before = _condition(world, kind, asset)
    if before is None or before <= 0.0:
        return
    after = max(0.0, before - amount)
    _set_condition(world, kind, asset, after)
    record = WarDamage(did=state.next_did, turn=turn, kind=kind, asset=asset, region=region, event=event,
                       war_key=key, war_start_turn=start, amount=before - after,
                       condition_before=before, condition_after=after)
    state.next_did += 1
    project = _open_project(state, kind, asset)
    if project is not None:
        _attach(project, record, work_per_condition(kind))
    state.damages.append(record)
    del state.damages[:-MAX_DAMAGES]
    _bump(state, "damages")
    _bump(state, f"damages_{event}")
    _bump(state, f"damage_{kind}", round(before - after, 9))


def _attach(project: RepairProject, record: WarDamage, per: float) -> None:
    record.project = project.pid
    project.damages.append(record.did)
    project.scope += record.amount * per
    if project.cause != "war" or project.war_key is None:
        project.cause = "war"
        if project.war_key is None:
            project.war_key, project.war_start_turn = record.war_key, record.war_start_turn
    _note(project, record.turn, f"war_damage_{record.event}", project.controller,
          round(record.amount * per * MILLI))


# ---------------------------------------------------------------------------
# Phase 2
# ---------------------------------------------------------------------------

def prepare_phase2(world, region_input, agent_bridge, snapshot, acc):
    """Plan granary work (the storage channel) and hold the timber of every
    planned project before the native economy runs; charges nothing."""
    state = _state(world)
    sim = _native(agent_bridge)
    t = _begin(world, state, sim)
    if t.prepared:
        raise RuntimeError("repair projects already prepared for this turn")
    t.sim = sim
    if _workshops_operate(world) and not t.seam and any(p.kind == "workshop" for p in state.projects):
        raise RuntimeError("workshop repair crews were not planned before the crew planner")
    storage = _storage(world)
    plan = getattr(storage, "_active_plan", None) if storage is not None else None
    suspended = set(getattr(plan, "suspended", ()) or ()) if plan is not None else set()
    t.suspended = sorted(suspended)
    granaries = [p for p in state.projects if p.kind == "granary"]
    for p in list(granaries):
        if storage is None or storage.assets[p.asset] is None:
            _close(state, p, world.turn, "abandoned", "asset_closed")
            granaries.remove(p)
        elif _controller(world, p.region) < 0:
            _close(state, p, world.turn, "abandoned", "no_controller")
            granaries.remove(p)
        elif plan is None or p.region not in suspended:
            raise RuntimeError("a granary under a repair project kept its storage request")
    commitments = _commitments(world, sim) if (granaries or t.work) else {}
    # Workshop crews were sized against the free timber at the seam; holds of
    # other Phase 2 planners since then are re-checked here.
    for w in t.work.values():
        if w.kind == "workshop" and w.hold > 0:
            free = _free_timber(world, w.region, commitments, t.holds[w.region] - w.hold)
            if free + EPS < w.hold:
                t.holds[w.region] -= w.hold - free
                w.hold = free
                w.request = free / WORKSHOP_TIMBER_PER_WORK
                if "no_timber" not in w.reasons:
                    w.reasons.insert(0, "no_timber")
    if granaries:
        per_condition, per_turn, timber_rate, coins = _storage_rules()
        from chronicler.grain_storage import _f32_floor
        from chronicler.mutual_aid import _treasury_budget
        others = _pending_before_granaries(world)
        budgets = [max(0, math.floor(_treasury_budget(world, c, acc)) - others[i])
                   for i, c in enumerate(world.civilizations)]
        milli = [0] * len(budgets)
        for w in t.work.values():
            if 0 <= w.payer < len(milli):
                milli[w.payer] += w.planned_milli
        names = region_input.schema.names
        if "granary_work_requested" not in names:
            raise RuntimeError("granary repair projects require the storage work column")
        requested = region_input.column(names.index("granary_work_requested")).to_pylist()
        for p in granaries:
            payer = _controller(world, p.region)
            asset = storage.assets[p.asset]
            w = t.work[p.pid] = _Work(p, payer, float(asset.condition))
            remaining = max(0.0, p.scope - p.delivered)
            want = min(per_turn, remaining)
            free = _free_timber(world, p.region, commitments, t.holds.get(p.region, 0.0))
            limits = {"no_timber": free / timber_rate,
                      "no_coins": max(0, budgets[payer] * MILLI - milli[payer]) / (coins * MILLI)}
            env = _envelope(world, payer)
            w.envelope = env
            if env is not None:
                limits["no_envelope"] = max(0, env * MILLI - milli[payer]) / (coins * MILLI)
            amount = _f32_floor(max(0.0, min([want, *limits.values()])))
            w.reasons = [reason for reason, value in limits.items() if value + EPS < want]
            if requested[p.region] != 0.0:
                raise RuntimeError("storage requested work in a region under a repair project")
            w.request = amount
            w.hold = amount * timber_rate
            if amount > 0:
                w.planned_milli = _coin_milli(amount)
                milli[payer] += w.planned_milli
                t.holds[p.region] = t.holds.get(p.region, 0.0) + w.hold
                requested[p.region] = amount
        import pyarrow as pa
        idx = names.index("granary_work_requested")
        region_input = region_input.set_column(idx, "granary_work_requested",
                                               pa.array(requested, type=pa.float32()))
    if any(v > 0 for v in t.holds.values()):
        import pyarrow as pa
        names = region_input.schema.names
        if "stockpile_timber" not in names:
            raise RuntimeError("repair projects require the packed timber stock column")
        idx = names.index("stockpile_timber")
        column = region_input.column(idx).to_pylist()
        for region, amount in sorted(t.holds.items()):
            if amount > 0:
                goods = world.regions[region].stockpile.goods
                goods["timber"] = goods.get("timber", 0.0) - amount
                column[region] = goods["timber"]
        region_input = region_input.set_column(idx, "stockpile_timber", pa.array(column, type=pa.float32()))
    t.prepared = True
    return region_input


def _pending_before_granaries(world) -> list[int]:
    """Bills planned earlier in Phase 2 and not yet charged, per civ: the
    storage plan, the funded L1 bills and the L8 warden bills (RS2's own
    workshop repairs are counted by the caller)."""
    bills = _pending_storage_raw(world)
    workshops = getattr(getattr(world, "livelihoods", None), "workshops", None)
    plan = getattr(workshops, "_plan", None) if workshops is not None else None
    if plan is not None and plan.turn == world.turn:
        for site in plan.sites:
            if site.funded and site.payer is not None and 0 <= site.payer < len(bills):
                bills[site.payer] += sum(site.bill.values())
    commons = getattr(getattr(world, "livelihoods", None), "commons_rules", None)
    cplan = getattr(commons, "_plan", None) if commons is not None else None
    if cplan is not None and getattr(cplan, "turn", None) == world.turn:
        for row in cplan.rows:
            if row.paid and row.owner is not None and 0 <= row.owner < len(bills):
                bills[row.owner] += int(row.paid)
    return bills


def finish_phase2(world, economy_result, agent_bridge, acc):
    """After the native economy tick: pay the delivered work once, credit
    condition (repair mode), return unused timber and arm the paid share."""
    state = _state(world)
    t = state._turn
    if t is None or t.turn != world.turn or not t.prepared or t.finished:
        raise RuntimeError("repair project plan missing for this turn")
    sim = t.sim
    from chronicler.mutual_aid import _treasury_budget
    delivered = getattr(economy_result, "granary_work_delivered", None) or {}
    per_condition, _per_turn, timber_rate, _coins = _storage_rules()
    work: dict[int, float] = {}
    for pid, w in sorted(t.work.items()):
        if w.kind == "granary":
            got = float(delivered.get(w.region, 0.0)) if w.request > 0 else 0.0
            if not (math.isfinite(got) and 0.0 <= got <= w.request):
                raise RuntimeError("granary repair work beyond its request")
            if w.request > 0 and got < w.request and "no_labor" not in w.reasons:
                w.reasons.append("no_labor")
            work[pid] = got
        else:
            work[pid] = w.request if w.crew else 0.0
    # Validate the whole bill before anything moves.
    due = [0] * len(world.civilizations)
    for pid, w in t.work.items():
        if w.payer < 0 or _controller(world, w.region) != w.payer:
            if work[pid] > 0 or w.crew:
                raise RuntimeError("repair payer changed while its work was pending")
            continue
        due[w.payer] += (_coin_milli(work[pid]) if w.kind == "granary" else len(w.crew) * w.wage)
    for i, civ in enumerate(world.civilizations):
        if due[i] and _treasury_budget(world, civ, acc) < -(-due[i] // MILLI):
            # Planning left room for every earlier Phase 2 bill; a shortfall
            # here means another spender was missed.
            raise RuntimeError("repair bill exceeds the projected treasury at settlement")
    rows = sorted((aid, w.share) for w in t.work.values() if w.kind == "workshop" for aid in w.crew)
    if rows:
        sim.extend_paid_work(world.turn, rows)
        t.installed = True
    wages = sorted((aid, w.wage) for w in t.work.values() if w.kind == "workshop" for aid in w.crew)
    applied: dict[int, tuple[int, int]] = {}
    wages = [(aid, amount) for aid, amount in wages if amount > 0]
    if wages:
        for aid, requested, got, residual, status in sim.transfer_wealth(
                world.turn, PURPOSE_REPAIR_WAGE, 0, wages):
            applied[int(aid)] = (int(got), int(residual) if status != 2 else int(requested))
    ledger: dict[int, dict] = {}
    receipts = []
    mode_repairs = state.mode == "repair"
    for pid, w in sorted(t.work.items()):
        p = w.project
        done = work[pid]
        row = ledger.setdefault(w.payer, dict(projects=0, work=0.0, timber=0.0, cost=0, due=0, applied=0,
                                              residual=0, envelope=w.envelope))
        row["projects"] += 1
        cost = _coin_milli(done) if w.kind == "granary" else 0
        paid = sum(applied.get(a, (0, 0))[0] for a in w.crew)
        residual = sum(applied.get(a, (0, w.wage))[1] for a in w.crew)
        rate = timber_rate if w.kind == "granary" else WORKSHOP_TIMBER_PER_WORK
        used = done * rate
        returned = w.hold - used
        if returned < -1e-9:
            raise RuntimeError("repair work used more timber than it held")
        returned = max(0.0, returned)
        if returned:
            goods = world.regions[w.region].stockpile.goods
            goods["timber"] = goods.get("timber", 0.0) + returned
        before = _condition(world, p.kind, p.asset)
        credit = done if mode_repairs else 0.0
        if credit:
            gain = credit / work_per_condition(p.kind)
            if before + gain > 1.0 + 1e-9:
                _bump(state, "cap_waste", round(before + gain - 1.0, 9))
            _set_condition(world, p.kind, p.asset, before + gain)
        after = _condition(world, p.kind, p.asset)
        p.delivered += done
        p.credited += credit
        p.timber_used += used
        p.coin_cost_milli += cost
        p.wages_milli += paid
        if p.controller != w.payer:
            _note(p, world.turn, "controller", w.payer)
            p.controller = w.payer
        if w.kind == "workshop":
            p.last_crew = list(w.crew)
        status = "progress" if done > 0 else "stalled"
        if done > 0:
            p.work_turns += 1
            _bump(state, "progress_turns")
        else:
            p.stalled_turns += 1
            _bump(state, "stalled_turns")
        for reason in w.reasons:
            # A reduced rate (unqualified) limits work; it never stops it.
            stalled = done <= 0 and reason != "unqualified"
            if stalled:
                p.stalls[reason] = p.stalls.get(reason, 0) + 1
            _bump(state, f"{'stalled' if stalled else 'limited'}_{reason}")
        remaining = max(0.0, p.scope - p.delivered)
        receipts.append(RepairReceipt(
            turn=world.turn, pid=pid, kind=p.kind, asset=p.asset, region=w.region, payer=w.payer,
            status=status, reasons=list(w.reasons), requested=w.request, delivered=done, credited=credit,
            rate=w.rate, crew=list(w.crew), share=w.share, qualified=list(w.qualified),
            veterans=list(w.veterans), timber_held=w.hold, timber_used=used, timber_returned=returned,
            wages_due_milli=len(w.crew) * w.wage, wages_milli=paid, wage_residual_milli=residual,
            coin_cost_milli=cost, envelope=w.envelope, condition_before=w.condition_before,
            condition_after=after, remaining_after=remaining))
        row["work"] += done
        row["timber"] += used
        row["cost"] += cost
        row["due"] += len(w.crew) * w.wage
        row["applied"] += paid
        row["residual"] += residual
        _bump(state, "work_delivered", done)
        _bump(state, "work_credited", credit)
        _bump(state, "timber_used", used)
        _bump(state, f"{p.kind}_work", done)
        if w.crew:
            _bump(state, "crew_person_turns", len(w.crew))
            _bump(state, "qualified_crew_turns" if w.rate == 1.0 else "unqualified_crew_turns")
        if remaining <= DONE:
            _close(state, p, world.turn, "completed", None)
    out = []
    for civ in sorted(ledger):
        r = ledger[civ]
        total = r["cost"] + r["applied"]
        before = int(state.prepaid.get(civ, 0))
        need = total - before
        charged = max(0, -(-need // MILLI))
        after = charged * MILLI - need
        if after:
            state.prepaid[civ] = after
        else:
            state.prepaid.pop(civ, None)
        if civ >= 0 and charged:
            target = world.civilizations[civ]
            if acc is None:
                target.treasury -= charged
            else:
                acc.add(civ, target, "treasury", -charged, "keep")
        out.append(CivLedger(turn=world.turn, civ=civ, projects=r["projects"], work_delivered=r["work"],
                             timber_used=r["timber"], coin_cost_milli=r["cost"], wages_due_milli=r["due"],
                             wages_applied_milli=r["applied"], wage_residual_milli=r["residual"],
                             charged=charged, prepaid_before_milli=before, prepaid_after_milli=after,
                             envelope=r["envelope"]))
        _bump(state, "charged", charged)
        _bump(state, "coin_cost_milli", r["cost"])
        _bump(state, "wages_milli", r["applied"])
        _bump(state, "wage_residual_milli", r["residual"])

    for row in out:
        check_ledger(row)
        if row.envelope is not None and row.charged > row.envelope:
            raise RuntimeError("repair spending beyond the civ's repairs envelope")
    t.receipts, t.ledger = receipts, out
    t.finished = True
    if _lane_active(world, "veteran_reintegration"):
        from chronicler.veteran_reintegration import note_outcome
        for r in receipts:
            for aid in r.veterans:
                note_outcome(world, aid, "placed:repair", turn=world.turn,
                             detail={"site": r.asset, "region": r.region})
                _bump(state, "veterans_placed")
    return []


def check_ledger(row: CivLedger) -> None:
    """Exact integer closure of one civ's repair accounts in one turn."""
    if row.charged * MILLI + row.prepaid_before_milli \
            != row.coin_cost_milli + row.wages_applied_milli + row.prepaid_after_milli \
            or not 0 <= row.prepaid_before_milli < MILLI or not 0 <= row.prepaid_after_milli < MILLI \
            or row.charged < 0:
        raise RuntimeError(f"repair accounts of civ {row.civ} do not close")
    if row.wages_applied_milli + row.wage_residual_milli != row.wages_due_milli:
        raise RuntimeError(f"repair wages of civ {row.civ} do not close")


def rollback_phase2(world) -> None:
    """Return held timber and disarm the paid share; a failed tick charges nothing."""
    state = _state(world)
    t = getattr(state, "_turn", None) if state is not None else None
    if t is None or t.turn != getattr(world, "turn", None):
        return
    if t.prepared and not t.finished:
        for region, amount in sorted(t.holds.items()):
            if amount > 0:
                goods = world.regions[region].stockpile.goods
                goods["timber"] = goods.get("timber", 0.0) + amount
    if t.installed and t.sim is not None:
        t.sim.cancel_paid_work()
    state._turn = None


def rollback_agent_tick(world, agent_bridge) -> None:
    """The agent tick raised: disarm an unconsumed paid share."""
    state = _state(world)
    t = getattr(state, "_turn", None) if state is not None else None
    if t is not None and t.turn == world.turn and t.installed and t.receipt is None and t.sim is not None:
        t.sim.cancel_paid_work()
        t.installed = False


def after_agent_tick(world, agent_bridge):
    state = _state(world)
    t = getattr(state, "_turn", None)
    if t is None or t.turn != world.turn or not t.installed:
        return []
    from chronicler.livelihoods import paid_work_receipt
    receipt = paid_work_receipt(world, t.sim)    # shared with other paid-work packages
    if receipt is None:
        raise RuntimeError("paid work receipt missing for this turn")
    t.receipt = receipt
    for r in t.receipts:
        if r.crew:
            r.income_replaced = math.fsum(receipt[a][2] for a in r.crew if a in receipt)
            _bump(state, "income_replaced", r.income_replaced)
    return []


def on_pool_reset(world) -> None:
    """A rebuilt native pool (``livelihoods.bind_native_pool``): saved crew ids
    would name other people, so each project's last crew is cleared with a
    dated note (crews are re-planned from the live pool every turn)."""
    state = _state(world)
    if state is None:
        return
    for p in state.projects:
        if p.last_crew:
            _note(p, world.turn, "pool_reset", p.controller, len(p.last_crew))
            p.last_crew = []
            _bump(state, "crews_pool_reset")


# ---------------------------------------------------------------------------
# Phase 10: lifecycle and the frame
# ---------------------------------------------------------------------------

def _assets(world):
    """(kind, asset, region, condition, built, capacity) in deterministic order."""
    storage = _storage(world)
    if storage is not None:
        for rid, asset in enumerate(storage.assets):
            if asset is not None:
                yield "granary", rid, rid, float(asset.condition), True, float(asset.capacity)
    for site in sorted(_sites(world).values(), key=lambda s: s.site):
        yield "workshop", site.site, site.region, float(site.condition), _built(site), None


def phase10_before_reserves(world, acc, economy_result, agent_bridge):
    """Abandon projects whose asset or controller is gone, note inherited
    projects and open new ones (before the L9 decision of this Phase 10)."""
    state = _state(world)
    turn = world.turn
    live = {(kind, asset): (region, cond) for kind, asset, region, cond, _b, _c in _assets(world)}
    for p in list(state.projects):
        if (p.kind, p.asset) not in live:
            _close(state, p, turn, "abandoned", "asset_closed")
            continue
        ctrl = _controller(world, p.region)
        if ctrl < 0:
            _close(state, p, turn, "abandoned", "no_controller")
        elif ctrl != p.controller:
            _note(p, turn, "controller", ctrl)
            p.controller = ctrl
            _bump(state, "inherited")
    unmet = []
    for kind, asset, region, cond, built, capacity in _assets(world):
        if _open_project(state, kind, asset) is not None:
            continue
        war = [d for d in state.damages if d.kind == kind and d.asset == asset and d.project is None]
        if not (cond < OPEN_BELOW - EPS or (war and cond < 1.0 - EPS)):
            continue
        ctrl = _controller(world, region)
        reason = ("no_controller" if ctrl < 0 else "zero_capacity" if capacity is not None and capacity <= 0
                  else "building" if not built else None)
        if reason is not None:
            unmet.append(UnmetNeed(kind=kind, asset=asset, region=region, condition=cond, reason=reason))
            _bump(state, f"unmet_{reason}")
            continue
        per = work_per_condition(kind)
        settlement = None
        if kind == "workshop":
            settlement = _sites(world)[asset].settlement_id
        p = RepairProject(pid=state.next_pid, kind=kind, asset=asset, region=region, settlement_id=settlement,
                          cause="war" if war else "wear", opened_turn=turn, opened_condition=cond,
                          controller=ctrl, scope=(1.0 - cond) * per)
        state.next_pid += 1
        for d in war:
            d.project = p.pid
            p.damages.append(d.did)
        if war:
            last = war[-1]
            p.war_key, p.war_start_turn = last.war_key, last.war_start_turn
        _note(p, turn, f"opened_{p.cause}", ctrl, round(p.scope * MILLI))
        state.projects.append(p)
        _bump(state, f"opened_{p.cause}")
        _bump(state, f"opened_{kind}")
    state.unmet = unmet
    _write_off(state, [civ for civ in sorted(state.prepaid)
                       if not 0 <= civ < len(world.civilizations) or not world.civilizations[civ].regions])
    return []


def phase10(world, acc, economy_result, agent_bridge):
    """Close the turn's frame (dated to this turn)."""
    state = _state(world)
    t = state._turn
    if t is not None and t.turn == world.turn and t.finished:
        if t.installed and t.receipt is None:
            t.sim.cancel_paid_work()            # no wealth phase took it: unknown, not zero
        state.receipts, state.ledger = t.receipts, t.ledger
        state.suspended = list(t.suspended)
        state.last_settled_turn = world.turn
        _bump(state, "settled_turns")
    else:
        if t is not None and t.turn == world.turn and t.installed:
            t.sim.cancel_paid_work()
        state.receipts, state.ledger = None, None
        state.suspended = []
    state.frame_turn = world.turn
    state._turn = None
    return []


def snapshot_summary(world) -> dict:
    """The completed-turn observation: projects as of the end of the source
    turn, that turn's receipts and per-civ ledger (None: no Phase 2, unknown
    rather than zero), recent war damage and unmet needs; never final state."""
    state = _state(world)
    source = world.turn - 1
    fresh = state.frame_turn == source
    per_condition, per_turn, timber_rate, coins = _storage_rules()
    return {
        "schema_version": 1, "stage": "RS2", "mode": state.mode, "source_turn": source,
        "units": {"money": "milli_treasury_units", "work": "work_units", "timber": "loads", "milli": MILLI},
        "projects": [p.model_dump() for p in state.projects],
        "closed": [p.model_dump() for p in state.closed],
        "damages": [d.model_dump() for d in state.damages],
        "receipts": [r.model_dump() for r in state.receipts] if fresh and state.receipts is not None else None,
        "ledger": [r.model_dump() for r in state.ledger] if fresh and state.ledger is not None else None,
        "unmet": [u.model_dump() for u in state.unmet] if fresh else None,
        "suspended": list(state.suspended) if fresh else None,
        "prepaid": {str(civ): amount for civ, amount in sorted(state.prepaid.items())},
        "counters": dict(state.counters),
        "parameters": {"open_below": OPEN_BELOW, "granary_work_per_condition": per_condition,
                       "granary_work_per_turn": per_turn, "granary_timber_per_work": timber_rate,
                       "granary_coins_per_work": coins,
                       "workshop_work_per_condition": WORKSHOP_WORK_PER_CONDITION,
                       "workshop_timber_per_work": WORKSHOP_TIMBER_PER_WORK,
                       "unqualified_rate": UNQUALIFIED_RATE, "wage_per_work": WAGE_PER_WORK,
                       "max_crew": MAX_CREW, "war_damage": WAR_DAMAGE * _damage_scale(world)},
    }


# ---------------------------------------------------------------------------
# L9 local budgets (the ``repairs`` envelope; ``local_budgets.REPAIRS``)
# ---------------------------------------------------------------------------

def budget_proposal(world, civ: int, obs) -> list[dict]:
    """One divisible ``repairs`` proposal per civ: next turn's planned work of
    its open projects at their current inputs, its cost in whole units (one
    whole-unit charge) and the burden it relieves (commons: granary spoilage and the
    reserve target worn capacity cannot hold; patricians: workshop crew work
    standing idle at a site shut for repair), from dated observations."""
    state = _state(world)
    if state is None or not repair_projects_active(world) or obs.economy is None:
        return []
    projects = [p for p in state.projects if _controller(world, p.region) == civ]
    if not projects:
        return []
    per_condition, per_turn, timber_rate, _coins = _storage_rules()
    from chronicler.grain_storage import EXTRA_SPOILAGE
    from chronicler.workshops import OPERATE_CONDITION
    storage = _storage(world)
    receipts = ({r.region: r for r in storage.receipts} if storage is not None
                and storage.receipt_turn == obs.turn else {})
    ws = getattr(world.livelihoods, "workshops", None)
    frame = {r.site: r for r in ws.frame} if ws is not None and ws.frame_turn == obs.turn else {}
    from chronicler.local_budgets import _parameters
    horizon = _parameters(world)["horizon"]
    held: dict[int, float] = {}
    milli, work, commons, patricians, regions = 0, 0.0, 0.0, 0.0, set()
    for p in projects:
        remaining = max(0.0, p.scope - p.delivered)
        free = _free_timber(world, p.region, obs.held, held.get(p.region, 0.0))
        cond = _condition(world, p.kind, p.asset)
        if cond is None or remaining <= DONE:
            continue
        if p.kind == "granary":
            asset = storage.assets[p.asset]
            amount = min(per_turn, remaining, free / timber_rate)
            if amount <= EPS or asset.capacity <= 0:
                continue
            milli += _coin_milli(amount)
            gain = amount / per_condition
            grain = world.grain_reserves.granaries[p.asset].grain
            r = receipts.get(p.asset)
            target = r.target_requested if r is not None and r.target_requested is not None else 0.0
            cut = max(0.0, target - asset.capacity * cond)
            commons += horizon * EXTRA_SPOILAGE * gain * grain + min(cut, asset.capacity * gain)
            held[p.region] = held.get(p.region, 0.0) + amount * timber_rate
        else:
            site = _sites(world)[p.asset]
            d = _diverted(world, site)
            per = d * UNQUALIFIED_RATE
            amount = min(MAX_CREW * per, remaining, free / WORKSHOP_TIMBER_PER_WORK)
            if amount <= EPS:
                continue
            milli += math.ceil(amount / per - EPS) * _wage(d)
            receipt = frame.get(site.site)
            if receipt is not None and cond < OPERATE_CONDITION:
                idle = max(0.0, float(receipt.work_available) - float(receipt.allocated))
                patricians += idle * min(1.0, (amount / WORKSHOP_WORK_PER_CONDITION)
                                         / max(EPS, OPERATE_CONDITION - cond))
            held[p.region] = held.get(p.region, 0.0) + amount * WORKSHOP_TIMBER_PER_WORK
        work += amount
        regions.add(p.region)
    cost = -(-milli // MILLI)
    if cost < 1 or work <= EPS:
        return []
    relief = {}
    if commons > EPS:
        relief["commons"] = commons
    if patricians > EPS:
        relief["patricians"] = patricians
    return [dict(service="repairs", recipients=sorted(regions), claims=[f"repairs:{civ}"], cost=cost,
                 divisible=True, unit="work", expected=work, relief=relief,
                 detail={"projects": len(projects), "work": round(work, 6), "cost_milli": milli})]


def budget_settlement(world, c, obs) -> dict:
    """The observed delivery of a ``repairs`` envelope (this turn's ledger)."""
    from chronicler.local_budgets import KEPT_RATIO
    state = _state(world)
    if state is None or not repair_projects_active(world):
        return {"outcome": "deferred", "reason": "service_off", "spent": 0, "delivered": 0.0, "ratio": 0.0}
    t = state._turn
    if t is None or t.turn != world.turn or not t.finished:
        reason = "no_economy" if obs.economy is None else "service_off"
        return {"outcome": "deferred", "reason": reason, "spent": 0, "delivered": 0.0, "ratio": 0.0}
    row = next((r for r in t.ledger if r.civ == c.civ), None)
    mine = [r for r in t.receipts if r.payer == c.civ]
    if row is None or not mine:
        return {"outcome": "deferred", "reason": "recipient_lost", "spent": 0, "delivered": 0.0, "ratio": 0.0}
    spent, delivered = int(row.charged), float(row.work_delivered)
    ratio = min(1.0, delivered / c.expected) if c.expected > EPS else 1.0
    done = all(r.remaining_after <= DONE for r in mine)
    detail = {"projects": len(mine), "charged": spent, "prepaid_after_milli": row.prepaid_after_milli}
    if ratio >= KEPT_RATIO or spent >= KEPT_RATIO * c.amount or done:
        return {"outcome": "kept", "reason": None, "spent": spent, "delivered": delivered,
                "ratio": 1.0 if done else ratio, "detail": detail}
    reasons = [reason for r in mine for reason in r.reasons]
    reason = ("inputs_short" if "no_timber" in reasons else "work_short" if "no_labor" in reasons
              else "treasury_shortfall" if "no_coins" in reasons else "work_short")
    return {"outcome": "deferred", "reason": reason, "spent": spent, "delivered": delivered,
            "ratio": ratio, "detail": detail}
