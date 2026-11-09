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

Recovery-skills seams (RS0; each is inert unless its switch is active, so a
world without those switches runs exactly the code above): before the crew
planner, ``apprenticeship.before_crews`` (RS1 seats); the planner's
``priority_ids``, this turn's workshop-qualified ids first
(``apprenticeship.crew_priority_ids``, RS1) and then
``veteran_reintegration.priority_ids`` per site region (RS3), omitted from
the native call when empty; for an operating site, the crew time its
qualified members spend on upkeep and teaching
(``apprenticeship.crew_maintenance``, RS1) comes out of the craft work
allocated and so out of the ceiling; in ``_bill``, the lump repair only while
``repair_projects.legacy_workshop_repair_allowed`` (RS2); and at settlement,
the operating wear of a funded operating site (``operating_wear.operating_wear``
with ``--operating-wear``, PL2, else ``apprenticeship.operating_wear``, RS1,
which implies it; condition is untouched when it is 0). RS2 adds two guarded seams:
right after the RS1 seats and before the crew planner,
``repair_projects.before_crews`` reserves each open repair project's named
crew (registry category ``repair``), so the L1 planner never also employs a
repairer; and :func:`_pending_storage_bills` includes the repair work planned
but not yet charged (``repair_projects.pending_bills``), so the L1 funding and
every later planner leave room for it.

A3 seams (``--workshop-economics``; inert unless active):
:func:`_firm_input_cap` bounds an operate-mode site's ceiling by the raw
inputs its workshop firm pays for (``workshop_economics.input_capacity``);
a site whose firm can pay for none, or that has no firm, does not operate
this turn (no production from unpaid inputs under A3); and
:func:`_never_readmit` keeps every city whose A3 firm closed out of
:func:`refresh_sites` for good.
"""
from __future__ import annotations

import math

from chronicler.workshops_state import (
    MAX_CLOSED, MAX_CREW, MAX_HISTORY, MAX_SITES, WorkshopReceipt, WorkshopSite, WorkshopState,
)
from chronicler.switch_state import lane_active, sub_state_getter

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
    __slots__ = ("site", "payer", "controller", "bill", "funded", "operating", "ceiling", "row", "work")

    def __init__(self, site, payer, controller, bill, funded, operating, ceiling, row, work=0.0):
        self.site, self.payer, self.controller = site, payer, controller
        self.bill, self.funded, self.operating = bill, funded, operating
        # ``work``: the crew time allocated to crafting when operating (the
        # crew's diverted time less any RS1 upkeep and teaching time).
        self.ceiling, self.row, self.work = ceiling, row, work


class _Plan:
    def __init__(self, turn: int, sites: list[_SitePlan], legacy: dict[int, float | None]):
        self.turn, self.sites, self.legacy = turn, sites, legacy


_state = sub_state_getter("workshops")


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
    closed_ids = {s.settlement_id for s in state.closed} | _never_readmit(world)
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


def _never_readmit(world) -> set[int]:
    """A3 seam: settlement ids of cities whose workshop firm closed, kept by
    workshop economics without L1's eight-entry bound (so none is readmitted
    with fresh capital); empty while A3 is inactive (the L1 rule, unchanged)."""
    if not _lane_active(world, "workshop_economics"):
        return set()
    return set(world.livelihoods.workshop_economics.closed_settlements)


def _crew_terms(world, site: int) -> tuple[int, float]:
    """(crew cap, hours) an L6a payroll firm set for the site (``workshop_payroll``);
    (MAX_CREW, 1.0) without payroll. Hours scale each member's diverted time."""
    if getattr(getattr(world, "livelihoods", None), "workshop_payroll", None) is None:
        return MAX_CREW, 1.0
    from chronicler.workshop_payroll import crew_terms
    return crew_terms(world, site)


def close_site(world, site: int, reason: str) -> None:
    """Close an open site for ``reason`` (L6a: an insolvent payroll firm)."""
    state = _state(world)
    _close(state, next(s for s in state.sites if s.site == site), world.turn, reason)


def _enlisted(world) -> list[int]:
    armies = getattr(getattr(world, "war_state", None), "armies", [])
    return sorted({int(aid) for army in armies for aid, _ in army.roster})


def _column(region_input, name: str):
    names = region_input.schema.names
    if name not in names:
        return None
    return region_input.column(names.index(name)).to_pylist()


_lane_active = lane_active


def _legacy_repair_allowed(world) -> bool:
    """RS0 seam (RS2): whether the L1 lump repair may be billed."""
    if world is None or not _lane_active(world, "repair_projects"):
        return True
    from chronicler.repair_projects import legacy_workshop_repair_allowed
    return bool(legacy_workshop_repair_allowed(world))


def _before_crews(world, sim, requests: list) -> None:
    """RS0 seam (RS1): runs before the native crew planner while apprenticeship is active."""
    if _lane_active(world, "apprenticeship"):
        from chronicler.apprenticeship import before_crews
        before_crews(world, sim, requests)


def _before_repair_crews(world, sim, requests: list, acc) -> None:
    """RS0 seam (RS2): reserves repair crews after the RS1 seats, before the
    native crew planner, while repair projects are active."""
    if _lane_active(world, "repair_projects"):
        from chronicler.repair_projects import before_crews
        before_crews(world, sim, requests, acc)


def _crew_priority(world, state: WorkshopState) -> list[int]:
    """RS0 seam (RS3, RS1): one priority list for the native planner,
    deduplicated: while apprenticeship is active, this turn's living
    workshop-qualified ids first (``apprenticeship.crew_priority_ids``, RS1),
    then each open site's ``veteran_reintegration.priority_ids`` in site order
    (RS3); [] while both are inactive."""
    out: list[int] = []
    seen: set[int] = set()
    lists = []
    if _lane_active(world, "apprenticeship"):
        from chronicler.apprenticeship import crew_priority_ids
        lists.append(crew_priority_ids(world))
    if _lane_active(world, "veteran_reintegration"):
        from chronicler.veteran_reintegration import priority_ids
        lists.extend(priority_ids(world, site.region) for site in state.sites)
    for ids in lists:
        for aid in ids:
            aid = int(aid)
            if aid not in seen:
                seen.add(aid)
                out.append(aid)
    return out


def _crew_maintenance(world, site: WorkshopSite, row: dict) -> float:
    """RS1 seam: the crew time (person-turns) an operating site's qualified crew
    spends on upkeep and teaching this turn, taken out of the craft work
    allocated; 0.0 unless apprenticeship is active."""
    if not _lane_active(world, "apprenticeship"):
        return 0.0
    from chronicler.apprenticeship import crew_maintenance
    used = float(crew_maintenance(world, site, row))
    if not (math.isfinite(used) and 0.0 <= used <= row["work_available"]):
        raise ValueError("crew maintenance time must be finite and within the crew's work")
    return used


def _firm_input_cap(world, site: WorkshopSite, row: dict, operating: bool, bill: dict, funded: bool):
    """A3 seam: the raw loads this turn's workshop firm can pay for (the
    ceiling's bound; 0.0: the site does not operate), or None while workshop
    economics is inactive (the L1 rule, unchanged)."""
    if not _lane_active(world, "workshop_economics"):
        return None
    from chronicler.workshop_economics import input_capacity
    cap = float(input_capacity(world, site, row, operating=operating, funded=bool(funded),
                               building="construction" in bill))
    if math.isnan(cap) or cap < 0.0:
        raise ValueError("a workshop firm's input capacity must be a non-negative number")
    return cap


def _owned_output_column(world, region_input, sim, open_sites):
    """A3-2 seam: with workshop economics rules version 2, the native column
    ``workshop_owned_crafts`` (the inventory at opening of each firm whose
    site is open and planned this turn; null elsewhere) that keeps those
    regions' crafted wares out of the commons; the batch unchanged otherwise.
    Refused when the extension does not honour the column (it would put the
    output into the commons and the firm's inventory both)."""
    if not _lane_active(world, "workshop_economics"):
        return region_input
    from chronicler.workshop_economics import OWNED_COLUMN, owned_column, owned_supported
    values = owned_column(world, open_sites)
    if values is None:
        return region_input
    if not owned_supported(sim):
        raise RuntimeError("--workshop-economics-rules 2 needs a native build that honours the "
                           "workshop_owned_crafts column (rebuild chronicler-agents)")
    if OWNED_COLUMN in region_input.schema.names:
        raise RuntimeError("economy batch already carries the owned workshop column")
    import pyarrow as pa
    return region_input.append_column(OWNED_COLUMN, pa.array(values, type=pa.float32()))


def _operating_wear(world, site: WorkshopSite) -> float:
    """RS0 seam (RS1, PL2): this turn's wear of a funded operating site; 0.0
    unless operating wear is active: ``--operating-wear`` (which takes RS1's
    upkeep offset when apprenticeship is active) or apprenticeship alone, which
    implies the same wear."""
    if _lane_active(world, "operating_wear"):
        from chronicler.operating_wear import operating_wear
    elif _lane_active(world, "apprenticeship"):
        from chronicler.apprenticeship import operating_wear
    else:
        return 0.0
    wear = float(operating_wear(world, site))
    if not (math.isfinite(wear) and 0.0 <= wear <= 1.0):
        raise ValueError("operating wear must be finite and in [0, 1]")
    return wear


def _bill(site: WorkshopSite, world=None) -> dict[str, int]:
    """What this turn's planned operation of a built or building asset costs.
    With ``world``, the lump repair also needs the RS2 legacy-repair gate."""
    if site.asset == "building" or site.construction_paid < CONSTRUCTION_COST:
        return {"construction": min(INSTALLMENT, CONSTRUCTION_COST - site.construction_paid)}
    bill = {"upkeep": UPKEEP}
    if site.arrears:
        bill["arrears"] = site.arrears
    if site.condition < OPERATE_CONDITION and _legacy_repair_allowed(world):
        bill["repair"] = REPAIR_COST
    return bill


def _pending_storage_bills(world) -> list[int]:
    """Upper bound of what a pending grain-storage plan will charge each civ.

    Storage budgets its work against the same projected treasury before the
    native tick and charges after it; its plan holds no accumulator entry yet,
    so the workshop must leave room for it (never spend the same coins twice).
    With RS2 active it includes the repair work planned and not yet charged.
    """
    bills = [0] * len(world.civilizations)
    storage = getattr(getattr(world, "grain_reserves", None), "storage", None)
    plan = getattr(storage, "_active_plan", None) if storage is not None else None
    if plan is not None and plan.status == "pending":
        from chronicler.grain_storage import COINS_PER_WORK
        for row in plan.rows:
            if row.owner >= 0 and row.request:
                bills[row.owner] += math.ceil(row.request * COINS_PER_WORK)
    if _lane_active(world, "repair_projects"):
        from chronicler.repair_projects import pending_bills
        for i, amount in enumerate(pending_bills(world)):
            bills[i] += amount
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
        bill = _bill(site, world)
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
    terms = {s.site: _crew_terms(world, s.site) for s in state.sites}
    requests = [(s.site, s.region, s.settlement_id,
                 float(_diverted(int(cities[s.site].rank)) * terms[s.site][1]), terms[s.site][0])
                for s in state.sites]
    _before_crews(world, sim, requests)
    _before_repair_crews(world, sim, requests, acc)
    rows = {}
    # Observe mode employs nobody: its crews are available, not employed, so
    # they hold no work commitment in the shared registry (L5 learners and
    # teaching would otherwise treat them as already working).
    reserve_turn = None if state.mode == "observe" else world.turn
    if requests:
        priority = _crew_priority(world, state)
        from chronicler.adaptive_livelihoods import declined_ids
        declined = declined_ids(world, "workshop")
        choice_kw = {"declined_ids": declined} if declined else {}
        if priority:
            planned = sim.plan_workshop_crews(requests, _enlisted(world), reserve_turn, priority_ids=priority, **choice_kw)
        else:
            planned = sim.plan_workshop_crews(requests, _enlisted(world), reserve_turn, **choice_kw)
        for row, (site_id, _r, _s, diverted, _m) in zip(planned, requests, strict=True):
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
            # A worn site operates only once repaired. While the L1 lump is
            # allowed, a built site below OPERATE_CONDITION always carries the
            # repair in its bill, so this adds no condition (RS0 seam for RS2).
            operating = (funded and not builds and state.mode == "operate"
                         and row["work_available"] > 0.0
                         and (site.condition >= OPERATE_CONDITION or "repair" in bill))
            limit = _firm_input_cap(world, site, row, operating, bill, funded) if state.mode == "operate" else None
            if limit is not None and limit <= 0.0:
                operating = False                     # A3: no affordable input (or no firm)
            ceiling = None
            work = row["work_available"]
            if operating:
                used = _crew_maintenance(world, site, row)    # RS1 seam: 0.0 when inactive
                if used:
                    work = work - used
            if state.mode == "operate":
                ceiling = K_RAW_PER_WORK * work if operating else 0.0
                if operating and limit is not None:
                    ceiling = min(ceiling, limit)
            plans.append(_SitePlan(site, payer, controller, bill, funded, operating, ceiling, row, work))
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
        region_input = _owned_output_column(world, region_input, sim, {p.site.site for p in plans})
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
    if plan_site.operating:
        wear = _operating_wear(world, site)
        if wear:
            site.condition = max(0.0, site.condition - wear)
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
            allocated = p.work if p.operating else 0.0
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
