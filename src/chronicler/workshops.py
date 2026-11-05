"""L1 staffed public workshops (``--workshops``, default off).

Modes (``--workshop-mode``): ``operate`` (default, L1B funded operation),
``observe`` (L1A: crews and inputs only; nothing is charged or changed) and
``cost_only`` (the cost-retaining ablation: the asset is built, maintained
and paid exactly as in operate mode, but the crew's work does not replace the
region's craft ceiling, so the legacy ceiling stays in force).

Sites. Up to four open cities of rank >= 1, one per region, admitted in a
deterministic order (rank, size, settlement id) as cities exist; a closed
site (its city fell or vanished) is archived with its date and reason, its
unpaid arrears recorded as written off. A closed city is never readmitted.

Crews (L1A). Each Phase 2, before the native economy tick, the native planner
(``AgentSimulator.plan_workshop_crews``) resolves at most eight living adult
urban farmers resident in the site's settlement and region, excluding trips,
army rosters and existing work reservations, and reserves the crew in the
shared native work registry for the turn (one work commitment per person per
turn across workshops, later work consumers, rural health work and teaching;
the native tick refuses to run on an overlap). Each contributes the city's
already-diverted farming time ``d = 1 - URBAN_FARM_LABOR[rank]``; the farm
factor is untouched, so nothing is subtracted twice and the crew's ordinary
farm income share is unaffected (``affected_ordinary_income_share`` 0). No
wage is paid: there is no payroll in this sprint (deferred L6).

Funding (L1B, the staged route selected in the sprint plan). The payer is the
civilization controlling the site's region at Phase 2. All payments are a
disclosed public expenditure sink of its treasury (accumulator ``keep``),
never wages and never a private recipient. Declared, uncalibrated choices:
construction ``CONSTRUCTION_COST`` in installments of ``INSTALLMENT`` per
turn; ``UPKEEP`` per built turn; unpaid upkeep becomes arrears (capped at
``ARREARS_CAP``) and wears condition by ``CONDITION_WEAR``; below
``OPERATE_CONDITION`` the asset needs ``REPAIR_COST`` before it reopens.
A turn's bill (installment, or arrears + upkeep + any repair) is planned
against the projected treasury before the native tick and charged once after
the tick succeeded; a failed tick charges nothing. Arrears, construction
progress and condition belong to the asset and survive a change of
controller: a conqueror inherits the arrears and pays them before the site
reopens; nothing is rebuilt for free.

Work and output. A funded open site's crew is allocated its diverted time
``W = sum(d)``; the region's craft ceiling is replaced by ``K_RAW_PER_WORK *
W`` (not added to the legacy ceiling). A selected site that is building,
unfunded, in need of repair or without crew replaces the ceiling with zero.
After the tick, ``realized = craft_output / K_RAW_PER_WORK`` (at most W) is
the work the region's actual conversion used; inputs are the region's actual
native per-good craft input. Region totals are never split into site shares.
"""
from __future__ import annotations

import math

from chronicler.workshops_state import (
    MAX_CLOSED, MAX_CREW, MAX_HISTORY, MAX_SITES, WorkshopReceipt, WorkshopSite, WorkshopState,
)

#: Goods in native slot order (economy.FIXED_GOODS); only raw materials are crafted.
_RAW_GOODS = ("timber", "ore")

# Declared modeling choices (treasury units and raw loads), not calibrated.
K_RAW_PER_WORK = 2.0
CONSTRUCTION_COST = 60
INSTALLMENT = 10
UPKEEP = 3
ARREARS_CAP = 15
CONDITION_WEAR = 0.05
OPERATE_CONDITION = 0.5
REPAIR_COST = 20


class _SitePlan:
    __slots__ = ("site", "payer", "controller", "bill", "funded", "operating", "ceiling", "row")

    def __init__(self, site, payer, controller, bill, funded, operating, ceiling, row):
        self.site, self.payer, self.controller = site, payer, controller
        self.bill, self.funded, self.operating = bill, funded, operating
        self.ceiling, self.row = ceiling, row


class _Plan:
    def __init__(self, turn: int, sites: list[_SitePlan], legacy: dict[int, float | None]):
        self.turn, self.sites, self.legacy = turn, sites, legacy


def _state(world) -> WorkshopState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "workshops", None) if container is not None else None


def set_workshops_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    mode = getattr(args, "workshop_mode", None) if args is not None else None
    state = _state(world)
    if state is None:
        world.livelihoods.workshops = state = WorkshopState(mode=mode or "operate")
    elif mode is not None:
        if state.sites and state.mode != mode and "observe" in (state.mode, mode):
            raise ValueError("cannot switch workshop mode to or from observe with selected sites")
        state.mode = mode
    state.enabled = bool(value)


def workshops_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled and getattr(world, "cities", None) is not None


def _diverted(rank: int) -> float:
    from chronicler.cities import URBAN_FARM_LABOR
    return 1.0 - URBAN_FARM_LABOR[max(0, min(rank, len(URBAN_FARM_LABOR) - 1))]


def _note(site: WorkshopSite, turn: int, event: str, civ: int, amount: int = 0) -> None:
    site.history.append((turn, event, civ, amount))
    del site.history[:-MAX_HISTORY]


def _close(state: WorkshopState, site: WorkshopSite, turn: int, reason: str) -> None:
    site.status, site.closed_turn, site.closed_reason = "closed", turn, reason
    if state.mode != "observe":
        if site.arrears:
            state.counters["arrears_written_off"] = state.counters.get("arrears_written_off", 0) + site.arrears
        _note(site, turn, f"closed_{reason}", site.last_payer, site.arrears)
        site.asset = "closed"
    state.sites.remove(site)
    state.closed.append(site)
    del state.closed[:-MAX_CLOSED]
    state.counters[f"closed_{reason}"] = state.counters.get(f"closed_{reason}", 0) + 1


def refresh_sites(world, state: WorkshopState) -> dict[int, object]:
    """Close sites whose city is gone; admit new cities up to the cap.

    Returns the live City object of each open site, keyed by site id.
    """
    cities = {c.settlement_id: c for c in world.cities.cities}
    fallen = {getattr(f, "settlement_id", None) for f in getattr(world.cities, "fallen", [])}
    for site in list(state.sites):
        city = cities.get(site.settlement_id)
        if city is None:
            _close(state, site, world.turn, "city_fell" if site.settlement_id in fallen else "city_missing")
        elif city.region != site.region:
            _close(state, site, world.turn, "region_changed")
    taken = {s.region for s in state.sites}
    closed_ids = {s.settlement_id for s in state.closed}
    candidates = sorted((c for c in cities.values()
                         if c.rank >= 1 and c.region not in taken and c.settlement_id not in closed_ids),
                        key=lambda c: (-c.rank, -c.size, c.settlement_id))
    for city in candidates:
        if len(state.sites) >= MAX_SITES:
            break
        if city.region in taken:
            continue
        site = WorkshopSite(site=state.next_site, region=city.region, settlement_id=city.settlement_id,
                            city_name=city.name, selected_turn=world.turn)
        if state.mode != "observe":
            _note(site, world.turn, "selected", -1)
        state.sites.append(site)
        state.next_site += 1
        taken.add(city.region)
        state.counters["selected"] = state.counters.get("selected", 0) + 1
    return {s.site: cities[s.settlement_id] for s in state.sites}


def _enlisted(world) -> list[int]:
    armies = getattr(getattr(world, "war_state", None), "armies", [])
    return sorted({int(aid) for army in armies for aid, _ in army.roster})


def _column(region_input, name: str):
    names = region_input.schema.names
    if name not in names:
        return None
    return region_input.column(names.index(name)).to_pylist()


def _bill(site: WorkshopSite) -> dict[str, int]:
    """What this turn's planned operation of a built or building asset costs."""
    if site.asset == "building" or site.construction_paid < CONSTRUCTION_COST:
        return {"construction": min(INSTALLMENT, CONSTRUCTION_COST - site.construction_paid)}
    bill = {"upkeep": UPKEEP}
    if site.arrears:
        bill["arrears"] = site.arrears
    if site.condition < OPERATE_CONDITION:
        bill["repair"] = REPAIR_COST
    return bill


def _pending_storage_bills(world) -> list[int]:
    """Upper bound of what a pending grain-storage plan will charge each civ.

    Storage budgets its work against the same projected treasury before the
    native tick and charges after it; its plan holds no accumulator entry yet,
    so the workshop must leave room for it (never spend the same coins twice).
    """
    bills = [0] * len(world.civilizations)
    storage = getattr(getattr(world, "grain_reserves", None), "storage", None)
    plan = getattr(storage, "_active_plan", None) if storage is not None else None
    if plan is not None and plan.status == "pending":
        from chronicler.grain_storage import COINS_PER_WORK
        for row in plan.rows:
            if row.owner >= 0 and row.request:
                bills[row.owner] += math.ceil(row.request * COINS_PER_WORK)
    return bills


def _plan_funding(world, state, acc) -> list[tuple[WorkshopSite, int, str | None, dict, bool]]:
    """Payer and bill per open site, funded against one projected budget per civ
    after any pending grain-storage bill."""
    from chronicler.mutual_aid import _treasury_budget
    from chronicler.local_budgets import workshop_funded   # L9 envelope gate (identity when off)
    index = {c.name: i for i, c in enumerate(world.civilizations)}
    storage = _pending_storage_bills(world)
    budgets = [max(0, math.floor(_treasury_budget(world, c, acc)) - storage[i])
               for i, c in enumerate(world.civilizations)]
    out = []
    for site in state.sites:                       # site order: deterministic priority
        controller = world.regions[site.region].controller
        payer = index.get(controller, -1)
        bill = _bill(site)
        cost = sum(bill.values())
        funded = workshop_funded(world, payer, site, cost, payer >= 0 and budgets[payer] >= cost)
        if funded:
            budgets[payer] -= cost
        out.append((site, payer, controller, bill, funded))
    return out


def prepare_phase2(world, region_input, agent_bridge, snapshot, acc):
    state = _state(world)
    if getattr(state, "_plan", None) is not None:
        raise RuntimeError("workshop plan already pending")
    sim = getattr(agent_bridge, "_sim", None)
    if sim is None or not callable(getattr(sim, "plan_workshop_crews", None)) \
            or not callable(getattr(sim, "take_craft_inputs", None)):
        raise RuntimeError("workshops require a fresh native build with workshop crews")
    cities = refresh_sites(world, state)
    requests = [(s.site, s.region, s.settlement_id, float(_diverted(int(cities[s.site].rank))), MAX_CREW)
                for s in state.sites]
    rows = {}
    if requests:
        for row, (site_id, _r, _s, diverted, _m) in zip(
                sim.plan_workshop_crews(requests, _enlisted(world), world.turn), requests, strict=True):
            (site, region, settlement, resident, trip, army, assigned, eligible,
             crew, ages, work) = row
            rows[site_id] = dict(site=site, region=region, settlement_id=settlement,
                                 rank=int(cities[site_id].rank), diverted_fraction=diverted,
                                 resident_adult_farmers=resident, excluded_trip=trip,
                                 excluded_army=army, excluded_assigned=assigned, eligible=eligible,
                                 crew=list(crew), crew_ages=list(ages), work_available=float(work))
    legacy_col = _column(region_input, "craft_raw_demand")
    legacy = {s.region: (float(legacy_col[s.region]) if legacy_col is not None else None)
              for s in state.sites}
    plans = []
    if state.mode == "observe":
        plans = [_SitePlan(s, None, None, {}, None, False, None, rows[s.site]) for s in state.sites]
    else:
        for site, payer, controller, bill, funded in _plan_funding(world, state, acc):
            row = rows[site.site]
            builds = "construction" in bill
            operating = (funded and not builds and state.mode == "operate"
                         and row["work_available"] > 0.0)
            ceiling = None
            if state.mode == "operate":
                ceiling = K_RAW_PER_WORK * row["work_available"] if operating else 0.0
            plans.append(_SitePlan(site, payer, controller, bill, funded, operating, ceiling, row))
        caps = {p.site.region: p.ceiling for p in plans if p.ceiling is not None}
        if caps:
            if legacy_col is None:
                raise RuntimeError("operate mode requires the cities' craft_raw_demand column")
            import pyarrow as pa
            values = list(legacy_col)
            for region, cap in caps.items():
                values[region] = cap
            idx = region_input.schema.names.index("craft_raw_demand")
            region_input = region_input.set_column(idx, "craft_raw_demand", pa.array(values, type=pa.float32()))
    # Drop any stale observation from an earlier tick before this one runs.
    sim.take_craft_inputs()
    state._plan = _Plan(world.turn, plans, legacy)
    return region_input


def _settle(world, state, plan_site: _SitePlan, acc, turn: int) -> dict[str, int]:
    """Charge the planned bill once and advance the asset; returns what was paid."""
    site = plan_site.site
    if not plan_site.funded:
        if site.asset == "building":
            _note(site, turn, "unfunded_construction", plan_site.payer)
            return {}
        # Built but unfunded: upkeep accrues as arrears and condition wears.
        site.arrears = min(ARREARS_CAP, site.arrears + UPKEEP)
        site.condition = max(0.0, site.condition - CONDITION_WEAR)
        if site.asset != "idle":
            _note(site, turn, "idle_unfunded", plan_site.payer)
        site.asset = "idle"
        return {}
    if world.regions[site.region].controller != plan_site.controller:
        raise ValueError("workshop payer changed while its bill was pending")
    paid = dict(plan_site.bill)
    cost = sum(paid.values())
    civ = world.civilizations[plan_site.payer]
    from chronicler.mutual_aid import _treasury_budget
    if _treasury_budget(world, civ, acc) < cost:
        # Planning left room for every other Phase 2 bill; a shortfall here
        # means another spender was missed, so refuse rather than record an
        # unpaid payment.
        raise RuntimeError("workshop bill exceeds the projected treasury at settlement")
    if acc is None:
        civ.treasury -= cost
    else:
        acc.add(plan_site.payer, civ, "treasury", -cost, "keep")
    if site.last_payer != plan_site.payer:
        _note(site, turn, "payer", plan_site.payer)
    site.last_payer = plan_site.payer
    if "construction" in paid:
        site.construction_paid += paid["construction"]
        if site.construction_paid >= CONSTRUCTION_COST:
            site.asset = "open"
            _note(site, turn, "built", plan_site.payer, site.construction_paid)
        return paid
    if "repair" in paid:
        site.condition = 1.0
        _note(site, turn, "repaired", plan_site.payer, paid["repair"])
    if "arrears" in paid:
        _note(site, turn, "arrears_paid", plan_site.payer, paid["arrears"])
        site.arrears = 0
    if site.asset != "open":
        _note(site, turn, "reopened", plan_site.payer)
    site.asset = "open"
    for kind, amount in paid.items():
        state.counters[f"paid_{kind}"] = state.counters.get(f"paid_{kind}", 0) + amount
    return paid


def finish_phase2(world, economy_result, agent_bridge, acc):
    state = _state(world)
    plan = getattr(state, "_plan", None)
    if plan is None or plan.turn != world.turn:
        raise RuntimeError("workshop plan missing for this turn")
    inputs = agent_bridge._sim.take_craft_inputs()
    if inputs is not None and len(inputs) != len(world.regions):
        raise RuntimeError("native craft inputs do not match the region count")
    from chronicler.economy import FIXED_GOODS
    frame = []
    for p in plan.sites:
        row = p.row
        name = world.regions[row["region"]].name
        region_input = None
        output = None
        if inputs is not None:
            region_input = {g: float(inputs[row["region"]][FIXED_GOODS.index(g)]) for g in _RAW_GOODS}
            output = float(economy_result.craft_output.get(name, 0.0))
        extra = {}
        if state.mode != "observe":
            paid = _settle(world, state, p, acc, plan.turn)
            if "construction" in paid:
                state.counters["paid_construction"] = (state.counters.get("paid_construction", 0)
                                                       + paid["construction"])
            allocated = row["work_available"] if p.operating else 0.0
            realized = 0.0
            if p.operating and output is not None:
                realized = min(allocated, output / K_RAW_PER_WORK)
            extra = dict(asset=p.site.asset, payer=p.payer, funded=p.funded, craft_ceiling=p.ceiling,
                         paid=paid, arrears_after=p.site.arrears, condition_after=round(p.site.condition, 6),
                         allocated=allocated, realized=realized)
            state.counters["work_allocated"] = state.counters.get("work_allocated", 0.0) + allocated
            state.counters["work_realized"] = state.counters.get("work_realized", 0.0) + realized
            if p.operating:
                state.counters["operating_site_turns"] = state.counters.get("operating_site_turns", 0) + 1
        frame.append(WorkshopReceipt(
            turn=plan.turn, **row, legacy_craft_ceiling=plan.legacy.get(row["region"]),
            region_craft_output=output, region_craft_input=region_input, **extra))
    state.frame = frame
    state.frame_turn = plan.turn
    state.counters["planned_turns"] = state.counters.get("planned_turns", 0) + 1
    state.counters["crew_available_turns"] = (state.counters.get("crew_available_turns", 0)
                                              + sum(len(r.crew) for r in frame))
    state._plan = None
    return []


def rollback_phase2(world) -> None:
    state = _state(world)
    if state is not None:
        state._plan = None


def snapshot_summary(world) -> dict:
    state = _state(world)
    source = world.turn - 1
    frame = [r.model_dump() for r in state.frame] if state.frame_turn == source else None
    return {
        "schema_version": 1, "stage": "L1A" if state.mode == "observe" else "L1B",
        "mode": state.mode, "source_turn": source,
        "sites": [s.model_dump() for s in state.sites],
        "closed": [s.model_dump() for s in state.closed],
        # None: no completed Phase 2 observation for this turn (unknown, not zero).
        "receipts": frame,
        "counters": dict(state.counters),
        "parameters": {"k_raw_per_work": K_RAW_PER_WORK, "construction_cost": CONSTRUCTION_COST,
                       "installment": INSTALLMENT, "upkeep": UPKEEP, "arrears_cap": ARREARS_CAP,
                       "condition_wear": CONDITION_WEAR, "operate_condition": OPERATE_CONDITION,
                       "repair_cost": REPAIR_COST},
    }
