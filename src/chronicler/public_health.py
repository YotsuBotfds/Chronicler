"""Connected public health, opt-in: real supplies, water service and dated advice.

Regional epidemic parameters remain the only disease-death authority. Irrigation
is an explicitly declared proxy for maintained water management, not a new asset.
Public grain belongs to its controller; a local allocation has no cash
transfer. Foreign direct-neighbor purchases pay that
controller. Both consume actual uncommitted, untitled grain. No teleport beyond
one open adjacent region, borrowing, free patient food or invented stock.
"""
from __future__ import annotations

import math

from chronicler.public_health_state import OutbreakReport, PublicHealthState, SupplyReceipt

SANITATION_REDUCTION = 0.20  # flux susceptibility, at full maintained service
DISPLACEMENT_CROWDING = 0.25  # extra susceptibility at a fully displaced region
REPORT_LIFETIME = 5
MAX_REPORTS = 262144
LIFE_VALUE = 100.0  # explicit treasury-unit value in the policy's loss function
SUPPLY_BATCH = 0xC2B000
GUARD_BATCH = 0xC12000
GUARDS_PER_PAIR = 1.0
GUARD_WAGE_MILLI = 500


def _state(world):
    return getattr(getattr(world, "livelihoods", None), "public_health", None)


def public_health_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled


def set_public_health_enabled(world, value, *, args=None, agent_mode=None):
    state = _state(world)
    if state is None:
        world.livelihoods.public_health = state = PublicHealthState(crowding="density_only")
    for field in ("mode", "policy", "report_delay", "crowding"):
        given = getattr(args, f"public_health_{field}", None) if args is not None else None
        if given is not None:
            given = int(given) if field == "report_delay" else given
            if state.report_turn is not None and given != getattr(state, field):
                raise ValueError(f"--public-health-{field.replace('_', '-')} conflicts with the saved world")
            # Validate even callers outside argparse.
            checked = PublicHealthState(**{field: given})
            setattr(state, field, getattr(checked, field))
    state.enabled = bool(value)
    if not value:
        state.sanitation, state.sanitation_turn = [], None


def check_request(world, values, args, *, agent_mode, on):
    requested = on("public_health")
    for field in ("mode", "policy", "report_delay", "crowding"):
        value = getattr(args, f"public_health_{field}", None) if args is not None else None
        if value is not None:
            PublicHealthState(**{field: value})
            if not requested:
                raise ValueError(f"--public-health-{field.replace('_', '-')} requires --public-health")
            saved = _state(world)
            if saved is not None and value != getattr(saved, field):
                raise ValueError(f"--public-health-{field.replace('_', '-')} conflicts with the saved world")
    if not requested:
        return
    needed = [flag for flag in ("epidemic_care", "infrastructure_condition", "residence_ledger") if not on(flag)]
    if agent_mode != "hybrid":
        needed.append("agents hybrid")
    from chronicler.quarantine_rules import rules_of
    rules = rules_of(world)
    mode = getattr(args, "quarantine_mode", None) if args is not None else None
    if (mode or (rules.mode if rules is not None else None)) not in ("closure", "cost_only"):
        needed.append("quarantine-mode closure or cost_only")
    if needed:
        raise ValueError("--public-health requires " + ", ".join("--" + f.replace("_", "-") for f in needed))


def _bump(state, key, value):
    state.totals[key] = round(state.totals.get(key, 0.0) + value, 6)


def _ration(world):
    from chronicler.household_retail import _ration as ration
    return ration(world)


def supply_estimate(world, infectious: float, regions, *, infectious_by_region=None) -> int:
    """Gross milli-unit reserve in the single L9 care proposal.

    Unknown past prices use one coin/load for planning only; settlement never
    buys at that guess. The actual dated price is required at settlement.
    """
    state = _state(world)
    if state is None or not state.enabled:
        return 0
    prices = [state.prices[r] for r in regions if r in state.prices]
    price = max(prices, default=1000)
    if infectious_by_region is not None:
        # One expected whole-coin purchase per region with patients. Unknown
        # split-source rounding may still reduce delivery; settlement never
        # exceeds either actual envelope to meet an estimate.
        return sum(_cash_due(math.ceil(infectious_by_region[r] * _ration(world) * price), 0)
                   for r in regions if infectious_by_region[r] > 0)
    return math.ceil(infectious * _ration(world) * price)


def proposal_cost(world, civ, wages, supplies, guards):
    """Whole coins covering value and fresh purpose-specific wage prefunding.

    Supply reserve allows a foreign purchase. Local public allocation uses its
    gross value but does not spend that cash. Quotes/caps decide actual work.
    """
    gross = wages + supplies + guards
    state = _state(world)
    if state is None or not state.enabled:
        return max(1, (gross + 999) // 1000)
    care = world.livelihoods.epidemic_care
    fresh = (_cash_due(wages, care.book.carry.get(f"{civ}:care_wage", 0)) + supplies
             + _cash_due(guards, state.book.carry.get(f"{civ}:guard_wage", 0)))
    return max(1, (max(gross, fresh) + 999) // 1000)


def wage_budget(world, region: int, budget: int) -> int:
    """Leave the expected patient supply cost alongside the wage reservation."""
    state = _state(world)
    if state is None or not state.enabled:
        return budget
    from chronicler.epidemic_care import PATIENTS_PER_CARER, WAGE_MILLI
    price = state.prices.get(region, 1000)
    ratio = PATIENTS_PER_CARER * _ration(world) * price / WAGE_MILLI
    return max(0, math.floor(budget / (1.0 + ratio)))


def supply_for_work(world, region: int, share: float) -> int:
    state = _state(world)
    if state is None or not state.enabled:
        return 0
    from chronicler.epidemic_care import PATIENTS_PER_CARER
    return math.ceil(share * PATIENTS_PER_CARER * _ration(world) * state.prices.get(region, 1000))


def _cash_due(value, carry):
    """Whole-unit fresh funding after spending this purpose's prepaid carry."""
    return (max(0, int(value) - int(carry)) + 999) // 1000 * 1000


def _envelope_value(world, civ):
    pending = getattr(world.livelihoods.epidemic_care, "_turn", None)
    if pending is not None and pending.turn == world.turn:
        return pending.cash_envelopes.get(civ, 0)
    from chronicler.epidemic_care import _envelopes
    return sum(c.amount for c in _envelopes(world) if c.civ == civ) * 1000


def _care_due(world, civ):
    care = getattr(world.livelihoods, "epidemic_care", None)
    pending = getattr(care, "_turn", None)
    return pending.wages_planned.get(civ, 0) if pending is not None and pending.turn == world.turn else 0


def guard_cash_reserve(world, civ):
    state = _state(world)
    if state is None or not state.enabled:
        return 0
    value = (sum(m["wage_due_milli"] for r in state.guards if r["civ"] == civ for m in r["members"])
             if state.guard_turn == world.turn else guard_reserve(world, civ))
    return _cash_due(value, state.book.carry.get(f"{civ}:guard_wage", 0))


def care_cash_available(world, civ):
    """Maximum new care credit after prior care shares and guard cash reserve."""
    state = _state(world)
    if state is None or not state.enabled:
        return None
    care = world.livelihoods.epidemic_care
    pending = care._turn
    if civ not in pending.health_cash_limits:
        cash = max(0, _envelope_value(world, civ) - guard_cash_reserve(world, civ))
        pending.health_cash_limits[civ] = care.book.carry.get(f"{civ}:care_wage", 0) + cash
    return max(0, pending.health_cash_limits[civ] - _care_due(world, civ))


def care_bill_fits(world, civ, total):
    state = _state(world)
    if state is None or not state.enabled:
        return True
    carry = world.livelihoods.epidemic_care.book.carry.get(f"{civ}:care_wage", 0)
    return _cash_due(total, carry) + guard_cash_reserve(world, civ) <= _envelope_value(world, civ)


def note_care_funding(world, care_turn, ledger):
    """Retain exact cash and prepaid carry beside the separate gross value cap."""
    state = _state(world)
    if state is None or not state.enabled:
        return
    if state.funding_turn == world.turn:
        raise RuntimeError("public-health care funding already recorded")
    by_civ = {r.civ: r for r in ledger}
    state.funding_turn, state.funding = world.turn, []
    for civ, amount in sorted(care_turn.envelopes.items()):
        care = by_civ[civ]
        guard_carry = state.book.carry.get(f"{civ}:guard_wage", 0)
        state.funding.append({"turn": world.turn, "civ": civ, "envelope_milli": amount * 1000,
                              "care_paid_milli": care.paid_milli, "care_cash_milli": care.treasury_units * 1000,
                              "care_carry_before": care.carry_before, "care_carry_after": care.carry_after,
                              "supply_cash_milli": 0, "guard_cash_milli": 0, "guard_paid_milli": 0,
                              "guard_carry_before": guard_carry, "guard_carry_after": guard_carry})
        _bump(state, "care_cash_milli", care.treasury_units * 1000)


def _funding(world, civ):
    state = _state(world)
    if state.funding_turn != world.turn:
        raise RuntimeError("public-health funding requires current care settlement")
    return next((row for row in state.funding if row["civ"] == civ), None)


def _cash_remaining(row):
    return row["envelope_milli"] - row["care_cash_milli"] - row["supply_cash_milli"] - row["guard_cash_milli"]


def guard_regions(world, civ):
    """Own customs regions on a ledger edge to an advised foreign polity."""
    state = _state(world)
    if state is None or not state.enabled:
        return []
    target_names = {world.civilizations[r["target"]].name for r in state.guard_plan if r["civ"] == civ}
    neighbors = world.contact_ledger.neighbors()
    name = world.civilizations[civ].name
    return [rid for rid, region in enumerate(world.regions) if region.controller == name
            and any(world.regions[j].controller in target_names for j in neighbors.get(rid, ()))]


def guard_reserve(world, civ):
    state = _state(world)
    if state is None or not state.enabled:
        return 0
    return math.ceil(sum(r["civ"] == civ for r in state.guard_plan) * GUARDS_PER_PAIR * GUARD_WAGE_MILLI)


def guard_work(world, civ):
    state = _state(world)
    if state is None or not state.enabled or state.guard_turn != world.turn:
        return 0.0
    return math.fsum(r["work"] for r in state.guards if r["civ"] == civ and r["staffed"])


def guard_expected_deaths(world, civ):
    state = _state(world)
    if state is None or not state.enabled:
        return 0.0
    return math.fsum(d["expected_loss_units"] / LIFE_VALUE for d in state.decisions
                     if d["civ"] == civ and d["close"])


def staffed_targets(world, targets):
    """Phase 1 gate: a declaration restricts journeys only with T-1 paid work.
    Cost-only quarantine names and pays the identical guards but closes none.
    """
    state = _state(world)
    if state is None or not state.enabled:
        return targets
    funded = set(state.guard_capacity) if state.guard_capacity_turn == world.turn - 1 else set()
    return {civ: {target: key for target, key in rows.items() if (civ, target) in funded}
            for civ, rows in targets.items()}


def enforcement_cost(world, default):
    """Named guard wages replace C1's anonymous flat charge while on."""
    return 0 if public_health_active(world) else default


def _available(world, rid, commitments):
    region = world.regions[rid]
    held = float(commitments.get(region.name, {}).get("grain", 0.0))
    # Retail titles have their separate `reg.goods` physical store. The
    # economy returns only commons into region.stockpile: subtracting owned
    # goods here again would understate reachable public supply.
    return max(0, math.floor((float(region.stockpile.goods.get("grain", 0.0)) - held) * 1000))


def _sources(world, rid, civ):
    from chronicler.quarantine_rules import closed_pairs
    closed = closed_pairs(world)
    names = {r.name: i for i, r in enumerate(world.regions)}
    payer = world.civilizations[civ].name
    candidates = [rid] + sorted(names[n] for n in world.regions[rid].adjacencies if n in names and names[n] != rid)
    for source in candidates:
        seller = world.civ_index_map.get(world.regions[source].controller)
        if seller is None:
            continue  # no known owner to sell it
        name = world.civilizations[seller].name
        if seller != civ and (tuple(sorted((payer, name))) in closed):
            continue
        yield source, seller


def supply_care(world, care_turn, capacity, economy_result, acc):
    """After C2 wages: buy real rations within its remaining L9 envelope,
    then restrict its next-tick capacity to the patients actually supplied.

    The money book rejects duplicate purchase keys. Capacity is not dated
    until the caller commits the complete care frame. Short supply records
    wasted paid labour rather than minting the missing food.
    """
    state = _state(world)
    if state is None or not state.enabled:
        return capacity
    if state.supply_turn == world.turn:
        raise RuntimeError("public-health supplies already settled this turn")
    from chronicler import money
    from chronicler.mutual_aid import read_stockpile_commitments
    commitments = read_stockpile_commitments(world, care_turn.sim)
    wages = {}
    for r in care_turn.receipts:
        wages[r.civ] = wages.get(r.civ, 0) + r.wages_paid_milli
    budgets = {civ: max(0, coins * 1000 - wages.get(civ, 0) - guard_reserve(world, civ))
               for civ, coins in care_turn.envelopes.items()}
    state.supplies = []
    by_region = {r.region: r for r in care_turn.receipts if r.paid}
    result = []
    ration = _ration(world)
    for cap in sorted(capacity, key=lambda c: c.region):
        care = by_region[cap.region]
        need = math.ceil(cap.patients * ration * 1000)
        remaining, supplied = need, 0
        for source, seller in _sources(world, cap.region, care.civ):
            price = state.prices.get(source) if state.price_turn == world.turn - 1 else None
            row = SupplyReceipt(turn=world.turn, civ=care.civ, region=cap.region, source=source, seller=seller,
                                need_milli=remaining, price_milli=price)
            state.supplies.append(row)
            if price is None:
                row.reason = "price_unobserved"
                continue
            budget = budgets.get(care.civ, 0)
            funding = _funding(world, care.civ)
            if seller != care.civ:
                cash = max(0, _cash_remaining(funding) - guard_cash_reserve(world, care.civ))
                budget = min(budget, cash, money._civ_budget(world, care.civ, acc) * 1000)
            # A treasury pays whole units. A partial purchase never exceeds the
            # gross envelope, even where the owner and buyer are the same.
            affordable = (budget // 1000) * 1_000_000 // price
            food = min(remaining, _available(world, source, commitments), affordable)
            if food <= 0:
                row.reason = "budget" if affordable <= 0 else "stock"
                continue
            charged = math.ceil(food * price / 1_000_000) * 1000
            batch = SUPPLY_BATCH + cap.region * len(world.regions) + source
            if seller != care.civ:
                bill = money.Bill(purpose="care_supply", batch=batch, phase="phase2", payer=money.treasury(care.civ),
                                  lines=((money.treasury(seller), charged),), regions=(source,))
                got = money.pay(world, bill, turn=world.turn, book=state.book, acc=acc)
                if not got.ok:
                    row.reason = "payment_refused:" + str(got.reason)
                    continue
                funding["supply_cash_milli"] += charged
                _bump(state, "supply_cash_milli", charged)
            region = world.regions[source]
            before = float(region.stockpile.goods.get("grain", 0.0))
            region.stockpile.goods["grain"] = before - food / 1000
            if region.stockpile.goods["grain"] < -1e-8:
                raise RuntimeError("public-health ration purchase overdraws actual grain")
            row.food_milli = food
            row.charged_milli = charged if seller != care.civ else 0
            row.internal_milli = charged if seller == care.civ else 0
            row.patients, row.reason = food / (1000 * ration), "supplied"
            budgets[care.civ] -= charged
            supplied += food
            remaining -= food
            if remaining <= 0:
                break
        if not any(r.region == cap.region for r in state.supplies):
            state.supplies.append(SupplyReceipt(turn=world.turn, civ=care.civ, region=cap.region,
                                                need_milli=need, reason="owner_unobserved"))
        got_patients = min(cap.patients, supplied / (1000 * ration))
        result.append(cap.model_copy(update={"patients": got_patients}))
        _bump(state, "patients_unsupplied", cap.patients - got_patients)
    state.supply_turn = world.turn
    for r in state.supplies:
        _bump(state, "food_consumed_milli", r.food_milli)
        _bump(state, "gross_supplies_milli", r.charged_milli + r.internal_milli)
        _bump(state, "internal_supplies_milli", r.internal_milli)
    # Only completed current prices become next turn's planning information.
    observed = getattr(economy_result, "market_prices", {})
    state.prices = {rid: math.ceil(float(observed[r.name]["food"]) * 1000)
                    for rid, r in enumerate(world.regions) if r.name in observed
                    and "food" in observed[r.name] and math.isfinite(float(observed[r.name]["food"]))
                    and float(observed[r.name]["food"]) > 0}
    state.price_turn = world.turn
    return result


def care_allowed(world):
    state = _state(world)
    return state is None or not state.enabled or state.mode == "active"


def supply_spent(world, civ):
    state = _state(world)
    if state is None or not state.enabled or state.supply_turn != world.turn:
        return 0
    return (sum(r.charged_milli for r in state.supplies if r.civ == civ)
            + sum(m["wage_paid_milli"] for r in state.guards if r["civ"] == civ for m in r["members"]))


def environment_factors(world):
    """One guarded T-1 residence read; never use narration's bridge share.
    Stale sanitation is neutral and recorded as unobserved, never carried on.
    """
    state = _state(world)
    if state is None or not state.enabled:
        return None
    from chronicler.residence_ledger import read_frame
    frame = read_frame(world, consumer_turn=world.turn)
    regions = {r["region"]: r for r in (frame or {}).get("regions", [])}
    sanitation = state.sanitation if state.sanitation_turn == world.turn - 1 else []
    arrival = (frame or {}).get("arrival_diagnostics")
    arrival_complete = arrival.get("complete") if isinstance(arrival, dict) else None
    rows = []
    for rid in range(len(world.regions)):
        r = regions.get(rid)
        displaced = min(1.0, max(0.0, r["displaced"] / max(1, r["residents"]))) if r else 0.0
        # X1 spells classify motives, not housing/contact conditions. Unknown
        # attribution must not alter exposure for the same physical trajectory.
        # Epidemiology's existing population/capacity density remains in force.
        crowding = 1.0 + DISPLACEMENT_CROWDING * displaced if state.crowding == "legacy_displacement" else 1.0
        recent = (r or {}).get("recent_residence_arrivals")
        recent_share = (recent / max(1, r["residents"]) if arrival_complete is True
                        and isinstance(recent, int) and r is not None else None)
        if arrival_complete is True and r is None:
            recent_share = 0.0
        service = sanitation[rid] if rid < len(sanitation) else 0.0
        rows.append({"region": rid, "source_turn": world.turn - 1,
                     "residence_observed": frame is not None, "sanitation_observed": rid < len(sanitation),
                     "displaced_share": displaced, "water_service": service,
                     "crowding_factor": crowding, "crowding_basis": state.crowding,
                     "recent_arrival_share": recent_share, "arrival_diagnostics_complete": arrival_complete,
                     "flux_factor": 1.0 - SANITATION_REDUCTION * service if state.mode == "active" else 1.0})
    state.environment_turn, state.environment = world.turn, rows
    return rows


def phase10(world, acc, economy_result, agent_bridge):
    """Date B3's actual serving water assets for the next epidemic tick."""
    state = _state(world)
    if state is None or not state.enabled:
        return []
    from chronicler.infrastructure_condition import service
    values = []
    for rid, region in enumerate(world.regions):
        water = any(str(getattr(i.type, "value", i.type)) == "irrigation" and i.active
                    for i in region.infrastructure)
        values.append(service(world, rid, "irrigation") if water else 0.0)
    state.sanitation_turn, state.sanitation = world.turn, values
    state._guard_tick = None
    return []


def prepare_phase2(world, region_input, agent_bridge, snapshot, acc):
    """Name customs guards after all other work consumers, within C2's L9
    envelope. Full payment and a whole guard-equivalent are needed per pair.
    Partial or unpaid work is still a recorded labour cost, never enforcement.
    """
    state = _state(world)
    if state is None or not state.enabled:
        return region_input
    from chronicler import labour_reservations
    from chronicler.epidemic_care import _native, _envelopes, _f32_floor
    from chronicler.recovery_crews import _cities, _farm_share, _People, remove_farm_time
    from chronicler.money import _civ_budget
    sim = _native(agent_bridge)
    if state._guard_tick is not None:
        raise RuntimeError("public-health guards already planned")
    state._guard_tick = (world.turn, sim)
    state.guard_turn, state.guards = world.turn, []
    people = _People(world, snapshot if snapshot is not None else sim.get_snapshot())
    cities = _cities(world)
    booked = set(labour_reservations.booked(world, sim, world.turn))
    envelopes = {}
    for c in _envelopes(world):
        envelopes[c.civ] = envelopes.get(c.civ, 0) + c.amount * 1000
    care = getattr(world.livelihoods, "epidemic_care", None)
    for r in getattr(getattr(care, "_turn", None), "receipts", []):
        envelopes[r.civ] = max(0, envelopes.get(r.civ, 0) - r.wages_due_milli
                               - supply_for_work(world, r.region, r.care_time))
    cash_credits = {}
    for civ in envelopes:
        care_carry = care.book.carry.get(f"{civ}:care_wage", 0)
        care_cash = _cash_due(_care_due(world, civ), care_carry)
        guard_carry = state.book.carry.get(f"{civ}:guard_wage", 0)
        cash_credits[civ] = guard_carry + max(0, _envelope_value(world, civ) - care_cash)
    reserve, removal = [], {}
    for plan in state.guard_plan:
        civ, target = plan["civ"], plan["target"]
        need, members = GUARDS_PER_PAIR, []
        budget = min(envelopes.get(civ, 0), cash_credits.get(civ, 0),
                     _civ_budget(world, civ, acc) * 1000 + state.book.carry.get(f"{civ}:guard_wage", 0))
        eligible_regions = guard_regions(world, civ)
        for rid in eligible_regions:
            for aid, occupation, settlement in people.residents(rid):
                if occupation != 0 or aid in booked:
                    continue
                farm, _diverted, _urban = _farm_share(cities, rid, settlement)
                share = _f32_floor(min(need, farm, budget / GUARD_WAGE_MILLI))
                wage = round(share * GUARD_WAGE_MILLI)
                if share < 1e-3 or wage <= 0:
                    continue
                if getattr(world.livelihoods, "adaptive_livelihoods", None) is not None:
                    from chronicler.adaptive_livelihoods import accepts_offer
                    if not accepts_offer(world, aid, "border_guard"):
                        continue
                members.append({"agent_id": aid, "region": rid, "share": share,
                                "wage_due_milli": wage, "wage_paid_milli": 0,
                                "wage_residual_milli": 0, "income_withheld": None})
                booked.add(aid)
                reserve.append((aid, share))
                removal[rid] = removal.get(rid, 0.0) + share
                need -= share
                budget -= wage
                envelopes[civ] -= wage
                cash_credits[civ] -= wage
                if need <= 1e-6:
                    break
            if need <= 1e-6:
                break
        state.guards.append({"turn": world.turn, "civ": civ, "target": target, "members": members,
                             "need": GUARDS_PER_PAIR, "work": GUARDS_PER_PAIR - need,
                             "staffed": False, "payment": "pending"})
    if reserve:
        sim.reserve_work(world.turn, 3, sorted(reserve))
        region_input = remove_farm_time(world, region_input, snapshot, removal, sim=sim)
    return region_input


def finish_phase2(world, economy_result, agent_bridge, acc):
    state = _state(world)
    if state is None or not state.enabled:
        return []
    from chronicler import money
    turn, sim = state._guard_tick
    if turn != world.turn:
        raise RuntimeError("guard plan belongs to another turn")
    if state.guard_capacity_turn == world.turn:
        raise RuntimeError("guards already settled")
    funded = []
    for civ in sorted({r["civ"] for r in state.guards}):
        teams = [r for r in state.guards if r["civ"] == civ]
        members = sorted((m for r in teams for m in r["members"]), key=lambda m: m["agent_id"])
        if not members:
            for r in teams:
                r["payment"] = "no_workers"
            continue
        bill = money.Bill(purpose="guard_wage", batch=GUARD_BATCH + civ, phase="phase2",
                          payer=money.treasury(civ), lines=tuple((money.agent(m["agent_id"]), m["wage_due_milli"])
                                                               for m in members),
                          regions=tuple(m["region"] for m in members))
        quote = money.quote(world, bill, turn=world.turn, book=state.book, acc=acc, sim=sim)
        funding = _funding(world, civ)
        cash_due = _cash_due(quote.total, state.book.carry.get(f"{civ}:guard_wage", 0))
        if funding is None or cash_due > _cash_remaining(funding):
            for r in teams:
                r["payment"] = "refused:cash_envelope"
            continue
        if not quote.ok:
            for r in teams:
                r["payment"] = "refused:" + str(quote.reason)
            continue
        sim.extend_paid_work(world.turn, [(m["agent_id"], m["share"]) for m in members])
        got = money.pay(world, bill, turn=world.turn, book=state.book, acc=acc, sim=sim)
        if not got.ok:
            raise RuntimeError("quoted guard wage bill failed at settlement")
        funding["guard_cash_milli"] += -got.treasury_units * 1000
        funding["guard_paid_milli"] += got.applied
        funding["guard_carry_after"] = state.book.carry.get(f"{civ}:guard_wage", 0)
        if _cash_remaining(funding) < 0:
            raise RuntimeError("public-health cash funding exceeded its single envelope")
        _bump(state, "guard_cash_milli", -got.treasury_units * 1000)
        flows = {int(f.payee[1]): f for f in got.flows}
        for m in members:
            flow = flows[m["agent_id"]]
            m["wage_paid_milli"], m["wage_residual_milli"] = flow.applied, flow.residual
        for r in teams:
            r["payment"] = "paid"
            r["staffed"] = r["work"] >= GUARDS_PER_PAIR - 1e-6 and all(
                m["wage_paid_milli"] == m["wage_due_milli"] for m in r["members"])
            if r["staffed"]:
                funded.append((civ, r["target"]))
    state.guard_capacity_turn, state.guard_capacity = world.turn, funded
    for r in state.guards:
        _bump(state, "guard_farm_time", r["work"])
        _bump(state, "guard_wages_milli", sum(m["wage_paid_milli"] for m in r["members"]))
    return []


def after_agent_tick(world, agent_bridge):
    state = _state(world)
    if state is None or state.guard_turn != world.turn or not state.guards:
        return []
    from chronicler.livelihoods import paid_work_receipt
    receipt = paid_work_receipt(world, agent_bridge._sim)
    adaptive = getattr(world.livelihoods, "adaptive_livelihoods", None)
    for r in state.guards:
        for member in r["members"]:
            observed = receipt.get(member["agent_id"]) if receipt is not None else None
            if observed is not None:
                member["income_withheld"] = float(observed[2])
                _bump(state, "guard_income_withheld", member["income_withheld"])
            if adaptive is not None:
                from chronicler.adaptive_livelihoods import forgone_title, note_work
                withheld = (round(float(observed[2]) * 1000) if observed is not None
                            and abs(float(observed[0]) - member["share"]) <= 1e-6
                            else 0 if str(r["payment"]).startswith("refused:") else None)
                note_work(world, member["agent_id"], "border_guard", paid_milli=member["wage_paid_milli"],
                          withheld_milli=withheld, title_forgone_milli=forgone_title(world, member["region"]),
                          source="public_health:untruncated keyed guard wage and attributable paid-work receipt")
    return []


def farm_time(world, turn: int) -> dict[int, float]:
    """Current named guard plan's full prepared farm removal, by stable ID.

    Guard member.share is the urban/partial farm-equivalent work actually
    removed from farm_labor_factor. Refused or ceiling-limited payment does
    not restore that lost farm time. No capped or historical frame is read.
    """
    state = _state(world)
    if state is None or not state.enabled or turn != world.turn or state.guard_turn != turn \
            or state._guard_tick is None or state._guard_tick[0] != turn:
        return {}
    removed = {}
    for row in state.guards:
        for person in row["members"]:
            aid = person["agent_id"]
            removed[aid] = removed.get(aid, 0.0) + person["share"]
    return removed


def rollback_phase2(world):
    state = _state(world)
    if state is not None:
        state._guard_tick = None
        state.funding_turn, state.funding = None, []


def rollback_agent_tick(world, agent_bridge):
    state = _state(world)
    if state is not None and state._guard_tick is not None:
        agent_bridge._sim.cancel_paid_work()


def _learn_fatality(world, state):
    deaths = {}
    for rid, pathogen, count in world.epidemics.last_deaths:
        deaths[(rid, pathogen)] = count
    for row in world.epidemics.rows:
        civ = world.civ_index_map.get(world.regions[row.region].controller)
        if civ is None or not row.reported:
            continue
        key = f"{civ}:{row.pathogen}"
        d, inf = state.fatality.get(key, [0.0, 0.0])
        state.fatality[key] = [d + deaths.get((row.region, row.pathogen), 0), inf + row.burden * row.n]


def report_targets(world, reports):
    """C4: delivered reports and own observed fatality determine targets.

    Reports carry what was observed at issuance; closed borders never grant
    knowledge of current unseen disease rows. The shuffled arm rotates source
    prevalence among same-pathogen issued reports without changing delivery,
    recipients, target edges, costs or random streams.
    """
    state = _state(world)
    if state is None or not state.enabled:
        return None
    if state.report_turn == world.turn:
        raise RuntimeError("public-health reports already issued this turn")
    from chronicler import contact_ledger as cl
    from chronicler.epidemiology import IMPORT_SCALE, PATHOGENS
    from chronicler.quarantine_rules import ENFORCEMENT_COST, migration_closure_on
    neighbors = world.contact_ledger.neighbors()
    index = world.civ_index_map
    # Only the newest delivered report can affect a decision. Retain pending
    # messages and that one delivered message per recipient/source/pathogen;
    # obsolete copies add checkpoint/bundle bytes without information.
    delivered_latest = {}
    pending_prior = []
    for report in state.reports:
        if report.expires < world.turn:
            continue
        if report.delivery > world.turn:
            pending_prior.append(report)
        else:
            delivered_latest[(report.recipient, report.source, report.pathogen)] = report
    state.reports = sorted(pending_prior + list(delivered_latest.values()), key=lambda r: r.id)
    observations = {(row.region, row.pathogen): row for row in world.epidemics.rows if row.reported}
    # The emission registry comes from current reports, not provenance.
    pending = []
    for rid, pathogen in sorted(reports):
        row = observations.get((rid, pathogen))
        target = index.get(world.regions[rid].controller)
        if row is None or target is None:
            continue
        recipients = {target} | {index[world.regions[j].controller] for j in neighbors.get(rid, ())
                                if world.regions[j].controller in index}
        for civ in sorted(recipients):
            delay = (1 if civ == target else 2) + state.report_delay
            pending.append(OutbreakReport(id=state.next_report, recipient=civ, source=rid, target=target,
                                         pathogen=pathogen, issued=world.turn, delivery=world.turn + delay,
                                         expires=world.turn + delay + REPORT_LIFETIME, prevalence=row.burden))
            state.next_report += 1
    if state.policy == "shuffled":
        for pathogen in sorted({r.pathogen for r in pending}):
            group = [r for r in pending if r.pathogen == pathogen]
            source_values = {r.source: r.prevalence for r in group}
            sources = sorted(source_values)
            rotated = {source: source_values[sources[(i + 1) % len(sources)]] for i, source in enumerate(sources)}
            for report in group:
                report.prevalence = rotated[report.source]
    state.reports.extend(pending)
    if len(state.reports) > MAX_REPORTS:
        # Fail closed rather than silently select a favorable information set.
        raise RuntimeError("public-health report capacity exceeded")
    state.report_turn, state.decisions = world.turn, []
    edge_map = world.contact_ledger.edge_map()
    allowed = {}
    # Use the newest delivered report for each recipient/source/pathogen.
    delivered = {}
    for r in state.reports:
        if r.delivery <= world.turn <= r.expires and r.recipient != r.target:
            delivered[(r.recipient, r.source, r.pathogen)] = r
    grouped = {}
    for report in delivered.values():
        grouped.setdefault((report.recipient, report.target), []).append(report)
    for (civ, target), inbox in sorted(grouped.items()):
        own = {j for j, region in enumerate(world.regions) if region.controller == world.civilizations[civ].name}
        hazard, food_cost, routes = 0.0, 0.0, set()
        known = False
        for report in inbox:
            d, inf = state.fatality.get(f"{civ}:{report.pathogen}", [0.0, 0.0])
            if inf <= 0:
                continue
            known = True
            fatality = min(1.0, d / inf)
            for destination in sorted(own & set(neighbors.get(report.source, ()))):
                ab = edge_map.get((report.source, destination), (0.0,) * 4)
                ba = edge_map.get((destination, report.source), (0.0,) * 4)
                contact = cl.CONTACT_WEIGHTS[cl.TRADE] * (ab[cl.TRADE] + ba[cl.TRADE])
                if migration_closure_on(world):
                    contact += cl.CONTACT_WEIGHTS[cl.PEOPLE] * (ab[cl.PEOPLE] + ba[cl.PEOPLE])
                hazard += (-math.expm1(-IMPORT_SCALE * PATHOGENS[report.pathogen].r0
                                      * contact * report.prevalence)) * fatality * LIFE_VALUE
                # Goods contact is an observed coarse cost proxy; never call it
                # known imported food. Distinguish it in the receipt.
                food_cost += ab[cl.TRADE]
                if contact > 0:
                    routes.add((report.source, destination))
        cost = ENFORCEMENT_COST + 2.0 * len(routes) + food_cost
        choose = known and hazard > cost
        state.decisions.append({"civ": civ, "target": target, "report_ids": sorted(r.id for r in inbox),
                                "expected_loss_units": hazard, "cost_units": cost,
                                "goods_contact_cost_proxy": food_cost, "fatality_observed": known,
                                "close": choose})
        if choose:
            # Quarantine's cause field remains historical attribution only.
            first = min(inbox, key=lambda r: (r.source, r.pathogen))
            allowed.setdefault(civ, {})[target] = (first.source, first.pathogen)
    state.guard_plan = [{"civ": civ, "target": target} for civ, targets in sorted(allowed.items())
                        for target in sorted(targets)]
    # Current own observations become prior experience at the next decision.
    _learn_fatality(world, state)
    return allowed


def on_pool_reset(world):
    state = _state(world)
    if state is not None:
        state.guard_turn, state.guards = None, []
        state.guard_capacity_turn, state.guard_capacity = None, []
        state._guard_tick = None


def snapshot_summary(world):
    state = _state(world)
    if state is None:
        return None
    source = world.turn - 1
    reports_fresh = state.report_turn == source
    environment_fresh = state.environment_turn == source
    supply_fresh = state.supply_turn == source
    return {"schema_version": 1, "source_turn": source, "enabled": state.enabled, "mode": state.mode, "policy": state.policy,
            "crowding": state.crowding,
            "report_delay": state.report_delay, "report_turn": state.report_turn if reports_fresh else None,
            "reports": [r.model_dump() for r in state.reports], "decisions": state.decisions if reports_fresh else [],
            "environment_turn": state.environment_turn if environment_fresh else None,
            "environment": state.environment if environment_fresh else [],
            "supply_turn": state.supply_turn if supply_fresh else None,
            "supplies": [r.model_dump() for r in state.supplies] if supply_fresh else [],
            "guard_turn": state.guard_turn if state.guard_turn == source else None,
            "guards": state.guards if state.guard_turn == source else [],
            "guard_capacity_turn": state.guard_capacity_turn,
            "guard_capacity": state.guard_capacity,
            "funding_turn": state.funding_turn if state.funding_turn == source else None,
            "funding": state.funding if state.funding_turn == source else [],
            "totals": dict(state.totals), "parameters": {"sanitation_reduction": SANITATION_REDUCTION,
            "displacement_crowding": DISPLACEMENT_CROWDING, "life_value": LIFE_VALUE,
            "report_lifetime": REPORT_LIFETIME}}
