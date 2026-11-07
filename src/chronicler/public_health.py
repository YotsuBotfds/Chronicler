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


def _state(world):
    return getattr(getattr(world, "livelihoods", None), "public_health", None)


def public_health_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled


def set_public_health_enabled(world, value, *, args=None, agent_mode=None):
    state = _state(world)
    if state is None:
        world.livelihoods.public_health = state = PublicHealthState()
    for field in ("mode", "policy", "report_delay"):
        given = getattr(args, f"public_health_{field}", None) if args is not None else None
        if given is not None:
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
    for field in ("mode", "policy", "report_delay"):
        value = getattr(args, f"public_health_{field}", None) if args is not None else None
        if value is not None:
            PublicHealthState(**{field: value})
            if not requested:
                raise ValueError(f"--public-health-{field.replace('_', '-')} requires --public-health")
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


def supply_estimate(world, infectious: float, regions) -> int:
    """Gross milli-unit reserve in the single L9 care proposal.

    Unknown past prices use one coin/load for planning only; settlement never
    buys at that guess. The actual dated price is required at settlement.
    """
    state = _state(world)
    if state is None or not state.enabled:
        return 0
    prices = [state.prices[r] for r in regions if r in state.prices]
    price = max(prices, default=1000)
    return math.ceil(infectious * _ration(world) * price)


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


def _available(world, rid, commitments):
    from chronicler.household_retail import pilot_entry
    region = world.regions[rid]
    held = float(commitments.get(region.name, {}).get("grain", 0.0))
    pilot = pilot_entry(world, rid)
    owned = pilot.goods[0] / 1000 if pilot is not None else 0.0
    return max(0, math.floor((float(region.stockpile.goods.get("grain", 0.0)) - held - owned) * 1000))


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
    budgets = {civ: max(0, coins * 1000 - wages.get(civ, 0)) for civ, coins in care_turn.envelopes.items()}
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
            budget = min(budgets.get(care.civ, 0), money._civ_budget(world, care.civ, acc) * 1000)
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
    return sum(r.charged_milli for r in state.supplies if r.civ == civ)


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
    rows = []
    for rid in range(len(world.regions)):
        r = regions.get(rid)
        displaced = min(1.0, max(0.0, r["displaced"] / max(1, r["residents"]))) if r else 0.0
        service = sanitation[rid] if rid < len(sanitation) else 0.0
        rows.append({"region": rid, "source_turn": world.turn - 1,
                     "residence_observed": frame is not None, "sanitation_observed": rid < len(sanitation),
                     "displaced_share": displaced, "water_service": service,
                     "crowding_factor": 1.0 + DISPLACEMENT_CROWDING * displaced,
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
    return []


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
    state.reports = [r for r in state.reports if r.expires >= world.turn]
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
    # Current own observations become prior experience at the next decision.
    _learn_fatality(world, state)
    return allowed


def snapshot_summary(world):
    state = _state(world)
    if state is None:
        return None
    source = world.turn - 1
    reports_fresh = state.report_turn == source
    environment_fresh = state.environment_turn == source
    supply_fresh = state.supply_turn == source
    return {"schema_version": 1, "source_turn": source, "enabled": state.enabled, "mode": state.mode, "policy": state.policy,
            "report_delay": state.report_delay, "report_turn": state.report_turn if reports_fresh else None,
            "reports": [r.model_dump() for r in state.reports], "decisions": state.decisions if reports_fresh else [],
            "environment_turn": state.environment_turn if environment_fresh else None,
            "environment": state.environment if environment_fresh else [],
            "supply_turn": state.supply_turn if supply_fresh else None,
            "supplies": [r.model_dump() for r in state.supplies] if supply_fresh else [],
            "totals": dict(state.totals), "parameters": {"sanitation_reduction": SANITATION_REDUCTION,
            "displacement_crowding": DISPLACEMENT_CROWDING, "life_value": LIFE_VALUE,
            "report_lifetime": REPORT_LIFETIME}}
