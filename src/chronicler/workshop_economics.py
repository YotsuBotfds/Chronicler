"""A3 workshop economics (``--workshop-economics``, default off).

Requires ``--workshop-payroll`` (so ``--workshops`` in operate mode and
``--agents hybrid``). Design: the connected-world A3 audit (section 4) with
the lead's decisions; integration page
``docs/integration/workshop-economics.md``. Payments go through the shared
seam :mod:`chronicler.money`.

It turns the L6a firm of an L1 workshop site into a firm that buys its raw
inputs, starts with owner capital and sells to households as well as
academies. It registers **no hooks of its own** (so it must never define a
function named like a livelihoods hook, ``finish_phase2``, ``phase10`` and
the rest, which the fan-out would call): the L1 workshop and the L6a
payroll call it through guarded seams (``workshops._firm_input_cap``,
``workshop_payroll``'s crew terms, finish, sale, liquidation, reserve and
opening seams), so its effects run at payroll's position. No random draws.

Modes (``--workshop-economics-mode``): ``market`` (default); the cost control
``free_inputs`` (every rule as ``market``, budget, plan, crew sizing and the
ceiling included, except that the input charge is recorded and not taken);
the demand control ``academy_only`` (no household customers). Any payroll
mode is accepted: ``no_customer`` is the constructed demand collapse
(nothing is sold to anyone).

Who pays whom (milli-units; 1000 = one treasury unit = one wealth unit):

* **Starting capital.** An open, built, funded L1 site with an eligible crew
  and no firm opens one in Phase 10 when an input price exists for it (below)
  and its region's ruler can pay the declared constant ``CAPITAL`` (whole
  units) from its projected treasury (refused otherwise, with the reason, and
  retried on a later turn). Paid once per firm, never again: there is **no
  rescue**. A firm's closure closes its site, and A3 keeps the closed city's
  settlement id in its own persisted ``closed_settlements`` (not L1's
  eight-entry display list): L1 never readmits that city while A3 is active
  and A3 refuses an opening there (``closed_city``), so no city receives a
  second firm or a second capital.
* **Inputs: the plan price.** The region's ruler owns the commons the raw
  timber and ore come from. The price is the **most recent positive post-trade
  raw-material price the native economy computed for the firm's region in an
  earlier tick** (timber and ore share the ``raw_material`` category), dated;
  if the region never had one, the most recent positive one among the regions
  of the region's ruler (latest turn, then lowest region index); if none
  exists, the firm cannot buy (``price_unknown``) and a site cannot open
  (``no_input_price``). Never the price of the purchase's own tick (which
  includes the purchase's demand); it is recorded beside each purchase as a
  diagnostic only. Rounded up to whole milli-units per load; never clamped.
* **Inputs: paid before they are converted.** Each Phase 2 the firm reserves
  its ``budget`` (cash less wages owed, this turn's wage bill and a 2-milli
  slack); the budget buys ``floor(budget x 1000 / plan price)`` milli-loads and
  the region's craft ceiling becomes ``min(K x W, that)``, with the crew
  request sized to the workers those inputs occupy. The native conversion
  never exceeds the ceiling, so **the firm converts only inputs it pays for**:
  after the successful tick it pays ``ceil(used x plan price)`` (always within
  the reservation) from firm cash to the ruler's treasury (sub-unit amounts
  carried, ``money``). Raw stock it cannot pay for stays in the commons and is
  never converted (``unbought_need_milli`` records the crew's need it could not
  pay for). A failed tick charges nothing. A site with no firm, or whose firm
  has no budget or no price, does not operate: no production from unpaid
  inputs under this switch.
* **Asset.** The ruler keeps building, maintaining and repairing the L1
  asset as before (a public expenditure sink); A3 records it per site as an
  ``asset subsidy`` the firm's books exclude.
* **Customers** (Phase 10, after academy procurement): academies as in L6a,
  then (``market``) the firm region's households. Every resident wants
  ``0.01`` wares a turn (the native demand the people draw free from the
  commons). The gap is that demand less the uncommitted commons wares; the
  firm offers ``min(inventory, gap)`` at this turn's post-trade craft price
  (rounded up per load), split over households by members. A household is an
  adult and the resident children whose first living adult parent it is (a
  child with no adult parent in the region is its own household); adults pay
  (``floor(cash x 1000 / price)`` limits what a household buys), children
  only when no adult is there. Payment is one collection of keyed native
  debit rows (purpose ``wares_purchase``) into firm cash; exactly the paid
  wares move from inventory into the region's commons, where the next tick's
  free draw takes them ahead of the firm's next output (so the free draw
  consumes paid wares rather than stacking a free one on top). What
  households do not buy stays unsold.
* **Payroll, arrears, insolvency** as L6a; distributions keep a reserve of
  ``RESERVE_TURNS`` full wage and input bills. A firm that converted and sold
  nothing - it could not operate for a reason in ``IDLE_REASONS`` (no budget,
  no price, an unfunded asset or no eligible crew), or it operated with no raw
  stock to convert - for ``IDLE_CLOSE_AFTER`` turns in a row closes ``idle`` (L6a liquidation: owed wages paid from cash where it can, the rest
  written off, inventory returned to the commons, cash to the ruler).

Declared limits of this slice (A3-1): the same tick's craft output still
enters the commons before title, so the people and merchant departures can
draw on it free (recorded per firm-turn as ``free_use_upper_bound``; A3-2's
native owned-output column ends it); paid wares delivered to the commons may
be loaded by merchants free; spouses buy as separate households (Python has
no relationship read); academies are still delivered realm-wide.
"""
from __future__ import annotations

import math

from chronicler import money
from chronicler.workshop_economics_state import (
    COUNTERS, MAX_FRAME, MAX_LOG, MAX_POPULATION_HISTORY, EconomicsReceipt, EconomicsRecord, FirmTerms,
    PriceObservation, WorkshopEconomicsState,
)

MILLI = 1000
#: The owner's one-time starting capital, milli-units (declared, uncalibrated:
#: about three turns of a full rank-2 crew's wages, 3 x 8 x 0.15, plus three
#: turns of a full ceiling's inputs, 3 x 4.8 loads, at about 1.1 a load).
CAPITAL = 20_000
#: Idle turns in a row (no input bought, nothing sold) that close a firm.
IDLE_CLOSE_AFTER = 6
#: Why a firm could not operate that counts as idle: it cannot pay, no input
#: price exists, its owner no longer funds the asset, or its city has no
#: eligible crew. A worn site waits without counting (repair is RS2's work).
IDLE_REASONS = ("budget_exhausted", "price_unknown", "not_funded", "no_crew")
#: Milli-units kept back from the input budget for the f32 ceiling's rounding.
INPUT_SLACK = 2
#: Wares each resident wants a turn, milli-loads (``cities.CRAFT_DEMAND_PER_CAPITA``).
WARES_PER_HEAD = 10
#: Adults are 20 and older (native ``agent::AGE_ADULT``).
ADULT_AGE = 20
#: A firm region is depopulated when residents fell by this share over the window.
DEPOPULATION_SHARE = 0.25
DEPOPULATION_WINDOW = 10
_RAW = ("timber", "ore")


class _Plan:
    __slots__ = ("site", "firm", "region", "price", "budget", "capacity", "reason", "crew", "share",
                 "wage", "bill", "cash", "owed", "need")

    def __init__(self, site, firm, region):
        self.site, self.firm, self.region = site, firm, region
        self.price = self.budget = self.capacity = self.reason = self.need = None
        self.crew = 0
        self.share = self.wage = self.bill = self.cash = self.owed = 0


class _Turn:
    """One turn in flight (never checkpointed)."""

    def __init__(self, turn: int):
        self.turn = turn
        self.plans: dict[int, _Plan] = {}
        self.rows: dict[int, dict] = {}


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

def _state(world) -> WorkshopEconomicsState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "workshop_economics", None) if container is not None else None


def _bump(state: WorkshopEconomicsState, key: str, amount: int = 1) -> None:
    if key not in COUNTERS:
        raise KeyError(f"undeclared workshop economics counter {key!r}")
    state.counters[key] = state.counters.get(key, 0) + int(amount)


def _log(state: WorkshopEconomicsState, turn: int, kind: str, firm: int | None = None, **detail) -> None:
    state.log.append(EconomicsRecord(turn=int(turn), kind=kind, firm=firm, detail=detail))
    if len(state.log) > MAX_LOG:
        state.log_dropped += len(state.log) - MAX_LOG
        del state.log[:-MAX_LOG]


def set_workshop_economics_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    mode = getattr(args, "workshop_economics_mode", None) if args is not None else None
    turn = int(getattr(world, "turn", 0))
    state = _state(world)
    if state is None:
        world.livelihoods.workshop_economics = state = WorkshopEconomicsState(mode=mode or "market",
                                                                             enabled=bool(value))
        if value:
            _log(state, turn, "switched_on", mode=state.mode)
        return
    if state._turn is not None:
        raise RuntimeError("cannot change workshop economics while a turn is pending")
    if mode is not None:
        state.mode = mode
    if bool(value) != state.enabled:
        state.enabled = bool(value)
        # Switched off (a legacy resume): open firms continue as L6a firms.
        _log(state, turn, "switched_on" if value else "switched_off", mode=state.mode)


def workshop_economics_active(world) -> bool:
    state = _state(world)
    if state is None or not state.enabled:
        return False
    from chronicler.workshop_payroll import workshop_payroll_active
    return workshop_payroll_active(world)


def _payroll(world):
    return world.livelihoods.workshop_payroll


def _terms(state: WorkshopEconomicsState, firm: int) -> FirmTerms | None:
    return next((f for f in state.firms if f.firm == firm), None)


def _turn(state: WorkshopEconomicsState, world) -> _Turn:
    t = state._turn
    if t is None or t.turn != world.turn:
        t = state._turn = _Turn(world.turn)
    return t


def _controller(world, region: int) -> int | None:
    from chronicler.workshop_payroll import _controller
    return _controller(world, region)


def _diverted_of(world, site) -> float:
    from chronicler.workshops import _diverted
    city = next((c for c in world.cities.cities if c.settlement_id == site.settlement_id), None)
    return _diverted(int(city.rank)) if city is not None else 0.0


def _wage(share: float) -> int:
    from chronicler.workshop_payroll import _wage
    return _wage(share)


# ---------------------------------------------------------------------------
# Prices (the economy's own post-trade prices, observed each turn)
# ---------------------------------------------------------------------------

def _to_milli(price) -> int | None:
    if price is None:
        return None
    price = float(price)
    if not math.isfinite(price) or price <= 0.0:
        return None
    return max(1, math.ceil(price * MILLI - 1e-9))


def observe_prices(world, economy_result) -> None:
    """Record this tick's post-trade raw-material and craft prices of every
    region (payroll's finish seam, after the economy tick), keeping each
    region's most recent positive raw price and its turn (the plan price of
    later purchases)."""
    state = _state(world)
    prices = getattr(economy_result, "market_prices", None) if economy_result is not None else None
    kept = {p.region: p for p in state.prices if 0 <= p.region < len(world.regions)}
    for region in range(len(world.regions)):
        name = world.regions[region].name
        row = prices.get(name) if isinstance(prices, dict) else None
        raw = row.get("raw_material") if isinstance(row, dict) else None
        craft = row.get("craft") if isinstance(row, dict) else None
        raw = float(raw) if raw is not None and math.isfinite(float(raw)) else None
        craft = float(craft) if craft is not None and math.isfinite(float(craft)) else None
        before = kept.get(region)
        obs = PriceObservation(region=region, turn=world.turn, raw=raw, raw_milli=_to_milli(raw),
                               craft=craft, craft_milli=_to_milli(craft))
        if obs.raw_milli is not None:
            obs.plan_raw_milli, obs.plan_turn = obs.raw_milli, world.turn
        elif before is not None:
            obs.plan_raw_milli, obs.plan_turn = before.plan_raw_milli, before.plan_turn
        if obs.plan_raw_milli is None and obs.craft_milli is None and before is None:
            continue                          # nothing to remember about this region
        kept[region] = obs
    state.prices = [kept[r] for r in sorted(kept)]


def tick_price(world, economy_result, region: int, category: str) -> int | None:
    """This tick's post-trade price of ``category`` in ``region`` as the native
    economy computed it, milli-units per load rounded up; None when absent or
    not positive. A diagnostic beside each purchase: never what is charged."""
    prices = getattr(economy_result, "market_prices", None) if economy_result is not None else None
    row = prices.get(world.regions[region].name) if isinstance(prices, dict) else None
    value = row.get(category) if isinstance(row, dict) else None
    return _to_milli(value) if value is not None and math.isfinite(float(value)) else None


def _price(state, region: int, turn: int | None = None) -> PriceObservation | None:
    obs = next((p for p in state.prices if p.region == region), None)
    if obs is None or (turn is not None and obs.turn != turn):
        return None
    return obs


def plan_price(world, region: int) -> dict | None:
    """The plan price of raw inputs for a firm in ``region``, from earlier
    ticks only: the region's most recent positive post-trade raw price, dated;
    else the most recent positive one among the regions of the region's ruler
    (latest turn, then lowest region index); None when neither exists.
    ``{"price_milli", "turn", "region", "source": "region" | "realm"}``."""
    state = _state(world)
    obs = _price(state, region)
    if obs is not None and obs.plan_raw_milli is not None:
        return {"price_milli": obs.plan_raw_milli, "turn": obs.plan_turn, "region": region, "source": "region"}
    ruler = world.regions[region].controller
    if ruler is None:
        return None
    best = None
    for p in state.prices:
        if p.plan_raw_milli is None or not 0 <= p.region < len(world.regions) \
                or world.regions[p.region].controller != ruler:
            continue
        if best is None or p.plan_turn > best.plan_turn:
            best = p
    if best is None:
        return None
    return {"price_milli": best.plan_raw_milli, "turn": best.plan_turn, "region": best.region, "source": "realm"}


# ---------------------------------------------------------------------------
# Phase 2: crew terms and input capacity (workshop seams)
# ---------------------------------------------------------------------------

def _budget(firm, crew: int, share: float) -> int:
    owed = sum(o.amount for o in firm.owed)
    return firm.cash - owed - crew * _wage(share) - INPUT_SLACK


def _capacity(budget: int, price_milli: int) -> int:
    """Milli-loads of raw input ``budget`` milli-units buy at the price."""
    return (max(0, budget) * MILLI) // price_milli


def crew_terms(world, site: int, cap: int, hours: float) -> tuple[int, float]:
    """(crew cap, hours) for this turn's request: an A3 firm asks for the crew
    its affordable inputs occupy at the plan price (at least one: the native
    planner's floor; a firm that can buy nothing does not operate,
    ``input_capacity``), in every mode. A site without a firm asks for one
    person (it cannot operate under A3)."""
    from chronicler.workshop_payroll import _firm
    from chronicler.workshops import K_RAW_PER_WORK
    firm = _firm(_payroll(world), site)
    if firm is None:
        return 1, 1.0
    price = plan_price(world, firm.region)
    if price is None:
        return 1, hours                        # no price: the site will not operate
    ws_site = next(s for s in world.livelihoods.workshops.sites if s.site == site)
    share = _diverted_of(world, ws_site) * hours
    if share <= 0.0:
        return 1, hours
    per_worker = K_RAW_PER_WORK * share * MILLI          # milli-loads one worker converts
    for n in range(cap, 0, -1):
        need = math.ceil(_capacity(_budget(firm, n, share), price["price_milli"]) / per_worker)
        if need >= n:
            return n, hours
    return 1, hours


def input_capacity(world, site, row: dict, *, operating: bool, funded: bool, building: bool) -> float:
    """Raw loads this turn's firm pays for (the ceiling's bound: it converts
    nothing it has not paid for); 0.0 when the site cannot operate under A3 (no
    firm, no budget, no price, or an L1 reason). The same in every mode: the
    ``free_inputs`` control differs only in the charge. Records the plan for
    the finish seam."""
    state = _state(world)
    t = _turn(state, world)
    from chronicler.workshop_payroll import _firm
    from chronicler.workshops import K_RAW_PER_WORK, OPERATE_CONDITION
    firm = _firm(_payroll(world), site.site)
    plan = t.plans[site.site] = _Plan(site.site, firm.site if firm is not None else None, site.region)
    if firm is None:
        plan.reason = "no_firm"
        _bump(state, "sites_without_firm_turns")
        return 0.0
    crew = len(row.get("crew") or ())
    share = float(row["diverted_fraction"])
    plan.crew, plan.share, plan.wage = crew, share, _wage(share)
    plan.bill = crew * plan.wage
    plan.cash, plan.owed = firm.cash, sum(o.amount for o in firm.owed)
    plan.need = math.floor(K_RAW_PER_WORK * firm.crew_cap * share * MILLI)
    if not operating:
        plan.reason = ("not_built" if building else "not_funded" if not funded
                       else "no_crew" if not crew or not row.get("work_available")
                       else "worn" if site.condition < OPERATE_CONDITION else "not_operating")
        plan.capacity = 0
        return 0.0
    plan.price = plan_price(world, firm.region)
    plan.budget = _budget(firm, crew, share)
    if plan.price is None:
        plan.reason, plan.capacity = "price_unknown", 0
        _bump(state, "price_unknown_turns")
        _bump(state, "input_capacity_zero_turns")
        return 0.0
    plan.capacity = _capacity(plan.budget, plan.price["price_milli"])
    if plan.capacity <= 0:
        plan.reason = "budget_exhausted"
        _bump(state, "input_capacity_zero_turns")
        return 0.0
    if plan.price["source"] == "realm":
        _bump(state, "plan_price_realm_turns")
    return plan.capacity / MILLI


# ---------------------------------------------------------------------------
# Phase 2 finish: charge the inputs used (payroll seam)
# ---------------------------------------------------------------------------

def _row(t: _Turn, firm) -> dict:
    row = t.rows.get(firm.site)
    if row is None:
        row = t.rows[firm.site] = {"firm": firm.site, "region": firm.region, "inputs": None, "households": None,
                                   "customer_absent": [], "produced": 0, "titled": 0, "free_use_upper_bound": 0,
                                   "owner_asset_spend": 0, "operating": False}
    return row


def _money_transfer(pt, firm, kind: str, payer, payee, amount: int, phase: str) -> None:
    from chronicler.workshop_payroll_state import MoneyTransfer
    pt.money.append(MoneyTransfer(id=f"wp:{pt.turn}:{kind}:{firm.site}", turn=pt.turn, phase=phase, kind=kind,
                                  payer=payer, payee=payee, amount=amount, applied=amount))


def _used(receipt) -> tuple[float, float]:
    used = receipt.region_craft_input if receipt is not None else None
    return float((used or {}).get("timber", 0.0)), float((used or {}).get("ore", 0.0))


def charge_inputs(world, pt, acc, economy_result) -> None:
    """After payroll's title: pay each operating firm's inputs at the plan
    price (always within its reservation, so every converted load was paid
    for), record the asset subsidy and observe this tick's prices."""
    state = _state(world)
    t = _turn(state, world)
    payroll = _payroll(world)
    ws = world.livelihoods.workshops
    from chronicler.workshop_payroll import _add, _row as payroll_row, _total
    firms = {f.site: f for f in payroll.firms}
    receipts = {r.site: r for r in ws.frame} if ws.frame_turn == world.turn else {}
    for site, plan in sorted(t.plans.items()):
        receipt = receipts.get(site)
        spend = sum((receipt.paid or {}).values()) if receipt is not None and receipt.paid else 0
        firm = firms.get(site)
        if firm is None:
            if spend:
                _bump(state, "asset_subsidy_idle_units", spend)
            continue
        terms = _terms(state, firm.site)
        row = _row(t, firm)
        row["owner_asset_spend"] = int(spend)
        if spend:
            _bump(state, "asset_subsidy_firm_units", spend)
        work = pt.work.get(site)
        price = plan.price or {}
        inputs = {"plan_price_milli": price.get("price_milli"), "plan_price_turn": price.get("turn"),
                  "plan_price_region": price.get("region"), "plan_price_source": price.get("source"),
                  "tick_price_milli": tick_price(world, economy_result, firm.region, "raw_material"),
                  "budget_milli": plan.budget, "capacity_milli": plan.capacity, "need_milli": plan.need,
                  "unbought_need_milli": 0, "crew": plan.crew, "wage_bill_milli": plan.bill,
                  "no_input_reason": None if work is not None else plan.reason,
                  "used_timber_milli": 0, "used_ore_milli": 0, "used_milli": 0, "cost_milli": 0,
                  "charged_milli": 0, "not_charged_milli": 0, "converted_unpaid_milli": 0,
                  "payee": None, "treasury_units": 0}
        row["inputs"] = inputs
        if plan.need is not None:
            inputs["unbought_need_milli"] = max(0, plan.need - (plan.capacity or 0)) if work is not None \
                else plan.need
        if work is None:
            continue
        row["operating"] = True
        if terms is not None:
            terms.operating_turns += 1
            terms.last_operating_turn = world.turn
        _bump(state, "operating_firm_turns")
        timber, ore = _used(receipt)
        loads = timber + ore
        inputs.update(used_timber_milli=math.floor(timber * MILLI), used_ore_milli=math.floor(ore * MILLI),
                      used_milli=math.floor(loads * MILLI))
        output = work.output or 0.0
        row["produced"] = math.floor(output * MILLI)
        row["titled"] = int(work.titled)
        row["free_use_upper_bound"] = max(0, row["produced"] - int(work.titled))
        _bump(state, "free_use_upper_bound", row["free_use_upper_bound"])
        _bump(state, "inputs_used", inputs["used_milli"])
        _bump(state, "unbought_need", inputs["unbought_need_milli"])
        if loads <= 0.0:
            continue
        if plan.price is None or plan.capacity is None:
            raise RuntimeError(f"workshop firm {site} converted inputs it never planned to buy")
        # Paid before converted: the conversion never exceeds the ceiling, the
        # ceiling never what the reservation buys at the plan price.
        if loads * MILLI > plan.capacity + 1e-3:
            raise RuntimeError(f"workshop firm {site} converted more raw input than it paid for")
        # At least one milli-unit for any conversion (a sub-milli use is never free).
        cost = max(1, math.ceil(loads * plan.price["price_milli"] - 1e-9))
        if cost > plan.budget + INPUT_SLACK:
            raise RuntimeError(f"workshop firm {site} input charge exceeds its reservation")
        inputs["cost_milli"] = cost
        if state.mode == "free_inputs":           # the cost control: recorded, not taken
            inputs["not_charged_milli"] = cost
            _bump(state, "inputs_not_charged", cost)
            continue
        owner = _controller(world, firm.region)
        payee = money.treasury(owner) if owner is not None else money.sink("unowned_commons")
        bill = money.Bill(purpose="firm_input_purchase", batch=site, phase="phase2",
                          payer=money.firm_cash(site), lines=((payee, cost),))
        got = money.pay(world, bill, turn=world.turn, book=state.book, acc=acc, firms=firms)
        if not got.ok:
            raise RuntimeError(f"workshop firm {site} could not pay its reserved inputs: {got.reason}")
        inputs.update(charged_milli=cost, payee=[payee.kind, payee.ident], treasury_units=got.treasury_units)
        _total(firm, "inputs", cost)
        _add(payroll_row(pt, firm), "inputs", cost)
        _bump(state, "inputs_charged", cost)
        _bump(state, "input_treasury_units", got.treasury_units)
        _money_transfer(pt, firm, "input_purchase", ("workshop_cash", site),
                        (payee.kind, payee.ident if owner is not None else 0), cost, "phase2")
        if terms is not None:
            terms.totals["inputs"] = terms.totals.get("inputs", 0) + cost
    observe_prices(world, economy_result)


def rollback(world) -> None:
    state = _state(world)
    if state is not None and state._turn is not None and state._turn.turn == world.turn:
        state._turn = None


# ---------------------------------------------------------------------------
# Phase 10: household customers (payroll seam, after academy sales)
# ---------------------------------------------------------------------------

def _depopulated(state, region: int, turn: int, residents: int) -> bool:
    rows = [r for r in state.population if not (r[0] == turn and r[1] == region)]
    rows.append((turn, region, residents))
    state.population = [r for r in rows if r[0] > turn - MAX_POPULATION_HISTORY]
    past = next((r[2] for r in state.population if r[1] == region and r[0] == turn - DEPOPULATION_WINDOW), None)
    return past is not None and past > 0 and residents <= (1.0 - DEPOPULATION_SHARE) * past


def _households(snapshot, region: int):
    """{household key: (members, payers)} of the region's living residents
    (payers ascending), and each payer's whole milli-units of wealth."""
    cols = {name: snapshot.column(name).to_pylist() for name in
            ("id", "region", "age", "parent_id_0", "parent_id_1", "wealth")}
    local = [i for i, r in enumerate(cols["region"]) if int(r) == region]
    adults = {int(cols["id"][i]) for i in local if int(cols["age"][i]) >= ADULT_AGE}
    wealth = {}
    groups: dict[int, list[int]] = {}
    members: dict[int, int] = {}
    for i in local:
        aid = int(cols["id"][i])
        w = float(cols["wealth"][i])
        wealth[aid] = math.floor(w * MILLI) if w > 0 else 0
        if aid in adults:
            key = aid
        else:
            key = next((int(p) for p in (cols["parent_id_0"][i], cols["parent_id_1"][i]) if int(p) in adults),
                       aid)
        members[key] = members.get(key, 0) + 1
        groups.setdefault(key, [])
        if aid in adults or key == aid:
            groups[key].append(aid)
    return {k: (members[k], sorted(groups[k])) for k in sorted(members)}, wealth, len(local)


def _split(total: int, weights: dict[int, int]) -> dict[int, int]:
    """Largest-remainder split of ``total`` by integer weights (ties by key)."""
    whole = sum(weights.values())
    if whole <= 0 or total <= 0:
        return dict.fromkeys(weights, 0)
    out, rest = {}, []
    for key in sorted(weights):
        num = total * weights[key]
        out[key] = num // whole
        rest.append((-(num % whole), key))
    for _, key in sorted(rest)[:total - sum(out.values())]:
        out[key] += 1
    return out


def sell_to_households(world, firm, pt, customers, acc, sim) -> None:
    """After academy sales: academy and household customer outcomes; in
    ``market`` mode the firm region's households buy for the gap the free
    commons leaves."""
    state = _state(world)
    t = _turn(state, world)
    payroll = _payroll(world)
    from chronicler.workshop_payroll import _add, _bump as payroll_bump, _row as payroll_row, _total
    prow = payroll_row(pt, firm)
    row = _row(t, firm)
    absent = row["customer_absent"]
    owner = _controller(world, firm.region)
    row["academy_sales"] = int(prow.get("sales", 0))
    row["academy_sold"] = int(prow.get("sold", 0))
    if payroll.mode == "no_customer":
        absent.append("no_customer_mode")
    elif owner is None:
        absent.append("no_controller")
    elif not row["academy_sales"]:
        present = any(lord == owner for lord, _r, _a in customers)
        absent.append("academy_full" if present else "no_academy")
    if row["academy_sales"]:
        _bump(state, "academy_sales", row["academy_sales"])
    if payroll.mode == "no_customer" or owner is None:
        return
    if state.mode == "academy_only":
        absent.append("academy_only_mode")
        return
    snapshot = sim.get_snapshot()
    households, wealth, residents = _households(snapshot, firm.region)
    depopulated = _depopulated(state, firm.region, world.turn, residents)
    region = world.regions[firm.region]
    from chronicler.mutual_aid import read_stockpile_commitments
    committed = float(read_stockpile_commitments(world, sim).get(region.name, {}).get("crafts", 0.0))
    commons = max(0, math.floor((float(region.stockpile.goods.get("crafts", 0.0)) - committed) * MILLI))
    demand = WARES_PER_HEAD * residents
    gap = max(0, demand - commons)
    offered = min(firm.inventory, gap)
    obs = _price(state, firm.region, world.turn)
    price = obs.craft_milli if obs is not None else None
    info = {"residents": residents, "households": len(households), "demand_milli": demand, "commons_milli": commons,
            "gap_milli": gap, "offered_milli": offered, "price_milli": price, "bought_milli": 0, "paid_milli": 0,
            "buying_households": 0, "priced_out_households": 0, "payers": 0, "depopulated": depopulated}
    row["households"] = info
    _bump(state, "household_gap", gap)
    reason = None
    if firm.inventory <= 0:
        reason = "no_inventory"
    elif gap <= 0:
        reason = "commons_covers"
    elif price is None:
        reason = "price_unknown"
    if reason is None:
        _bump(state, "household_offered", offered)
        shares = _split(offered, {k: m for k, (m, _p) in households.items()})
        lines: dict[int, int] = {}
        bought_total = 0
        for key, (_m, payers) in households.items():
            share = shares[key]
            if share <= 0:
                continue
            cash = sum(wealth[a] for a in payers)
            bought = min(share, (cash * MILLI) // price)
            if bought < share:
                info["priced_out_households"] += 1
            if bought <= 0:
                continue
            cost = math.ceil(bought * price / MILLI)
            left = cost
            for aid in payers:
                take = min(left, wealth[aid])
                if take:
                    lines[aid] = take
                    left -= take
            if left:
                raise RuntimeError("a household's purchase exceeds its payers' wealth")
            info["buying_households"] += 1
            bought_total += bought
        if lines:
            bill = money.Bill(purpose="wares_purchase", batch=firm.site, phase="phase10",
                              payee=money.firm_cash(firm.site),
                              lines=tuple((money.agent(a), v) for a, v in sorted(lines.items())),
                              regions=tuple(firm.region for _ in lines))
            got = money.pay(world, bill, turn=world.turn, book=state.book, acc=acc, sim=sim,
                            firms={firm.site: firm})
            if not got.ok:
                raise RuntimeError(f"household wares purchase refused: {got.reason}")
            paid = got.applied
            firm.inventory -= bought_total
            region.stockpile.goods["crafts"] = region.stockpile.goods.get("crafts", 0.0) + bought_total / MILLI
            _total(firm, "household_sales", paid)
            _total(firm, "household_delivered", bought_total)
            _add(prow, "household_sales", paid)
            _add(prow, "household_sold", bought_total)
            payroll_bump(payroll, "household_sales", paid)
            info.update(bought_milli=bought_total, paid_milli=paid, payers=len(lines))
            _bump(state, "household_sale_turns")
            _bump(state, "household_sales", paid)
            _bump(state, "household_delivered", bought_total)
            _money_transfer(pt, firm, "household_sale", ("households", firm.region), ("workshop_cash", firm.site),
                            paid, "phase10")
            from chronicler.workshop_payroll import _material
            _material(pt, firm, "household_delivery", ("workshop_inventory", firm.site),
                      ("region_market", firm.region), bought_total, "phase10")
            terms = _terms(state, firm.site)
            if terms is not None:
                terms.totals["household_sales"] = terms.totals.get("household_sales", 0) + paid
        else:
            reason = "households_cannot_pay"
        _bump(state, "buying_households", info["buying_households"])
        _bump(state, "priced_out_households", info["priced_out_households"])
    if reason is not None:
        absent.append(reason)
    if not info["bought_milli"] and depopulated and "depopulated" not in absent:
        absent.append("depopulated")


# ---------------------------------------------------------------------------
# Phase 10: closure, reserve and opening (payroll seams)
# ---------------------------------------------------------------------------

def idle_close(world, firm, pt) -> bool:
    """Count an idle turn - nothing was sold and nothing was converted: the
    firm could not operate for a reason in ``IDLE_REASONS``, or it operated
    and converted nothing (no raw stock on hand; under payroll
    ``unpaid_labor`` such a firm would otherwise stay open for ever) - and
    return True when the firm should close ``idle``."""
    state = _state(world)
    t = _turn(state, world)
    terms = _terms(state, firm.site)
    if terms is None:
        return False
    plan = t.plans.get(firm.site)
    row = _row(t, firm)
    sold = row.get("academy_sales", 0) or (row["households"] or {}).get("paid_milli", 0)
    could_not_buy = plan is not None and plan.reason in IDLE_REASONS
    converted = row["operating"] and (row["inputs"] or {}).get("used_milli", 0) > 0
    if converted or sold:
        terms.idle_run = 0
    elif row["operating"]:
        terms.idle_run += 1                  # operated and converted nothing
        _bump(state, "idle_firm_turns")
        _bump(state, "idle_no_conversion_turns")
    elif could_not_buy:
        terms.idle_run += 1
        _bump(state, "idle_firm_turns")
    row["idle_run"] = terms.idle_run
    return terms.idle_run >= IDLE_CLOSE_AFTER


def input_reserve(world, firm) -> int:
    """Milli-units of ``RESERVE_TURNS`` full-crew input bills at the plan
    price (kept before distribution); 0 when no price exists."""
    from chronicler.workshop_payroll import _FULL_CREW, RESERVE_TURNS
    from chronicler.workshops import K_RAW_PER_WORK
    price = plan_price(world, firm.region)
    if price is None:
        return 0
    return RESERVE_TURNS * math.ceil(K_RAW_PER_WORK * _FULL_CREW * firm.diverted * price["price_milli"])


def on_closed(world, firm, reason: str, turn: int) -> None:
    state = _state(world)
    terms = _terms(state, firm.site)
    if terms is None:
        return
    terms.status, terms.closed_turn, terms.closed_reason = "closed", turn, reason
    settlement = firm.settlement_id
    if settlement not in state.closed_settlements:
        state.closed_settlements = sorted([*state.closed_settlements, int(settlement)])
    state.firms.remove(terms)
    state.closed.append(terms)
    del state.closed[:-8]
    _bump(state, "closed_idle" if reason == "idle" else "closed_insolvent" if reason == "insolvent"
          else "closed_other")
    _log(state, turn, "closed", firm.site, reason=reason, capital=terms.capital, turns=terms.turns,
         operating_turns=terms.operating_turns)
    if state._turn is not None and state._turn.turn == turn and firm.site in state._turn.rows:
        state._turn.rows[firm.site]["event"] = f"closed_{reason}"


def open_firms(world, pt, acc) -> None:
    """Phase 10, after the firms' turn: an open, built, funded site with an
    eligible crew and no firm opens one when its region's ruler can pay the
    starting capital once (production starts next turn)."""
    state = _state(world)
    t = _turn(state, world)
    payroll = _payroll(world)
    ws = world.livelihoods.workshops
    from chronicler.workshop_payroll import WorkshopFirm, _bump as payroll_bump, _note, _row as payroll_row, _total
    from chronicler.workshops import OPERATE_CONDITION
    if ws.frame_turn != world.turn:
        return
    receipts = {r.site: r for r in ws.frame}
    held = {f.site for f in payroll.firms} | {f.site for f in payroll.closed}
    for site in ws.sites:
        receipt = receipts.get(site.site)
        if site.site in held or receipt is None or not receipt.funded or site.asset != "open" \
                or site.condition < OPERATE_CONDITION:
            continue
        refused = None
        owner = _controller(world, site.region)
        d = _diverted_of(world, site)
        price = plan_price(world, site.region)
        if site.settlement_id in state.closed_settlements:
            refused = "closed_city"           # never a second firm or capital at a closed firm's city
        elif not receipt.eligible or d <= 0.0:
            refused = "no_crew"
        elif owner is None:
            refused = "no_controller"
        elif price is None:
            refused = "no_input_price"
        capital = CAPITAL
        if refused is None:
            firm = WorkshopFirm(site=site.site, region=site.region, settlement_id=site.settlement_id,
                                city_name=site.city_name, opened_turn=world.turn)
            firm.diverted = d
            prow = payroll_row(pt, firm)        # opens at zero cash: the capital is its first credit
            bill = money.Bill(purpose="firm_capital", batch=site.site, phase="phase10",
                              payer=money.treasury(owner), lines=((money.firm_cash(site.site), capital),))
            got = money.pay(world, bill, turn=world.turn, book=state.book, acc=acc, firms={site.site: firm})
            if not got.ok:
                refused = "treasury_short"
                del pt.rows[site.site]
        if refused is not None:
            _bump(state, f"opening_refused_{refused}")
            _log(state, world.turn, "opening_refused", site.site, reason=refused, capital=capital)
            continue
        _total(firm, "capital", capital)
        prow["capital"] = capital
        _note(firm, world.turn, "opened", capital // MILLI)
        payroll.firms.append(firm)
        payroll_bump(payroll, "firms_opened")
        _money_transfer(pt, firm, "capital", ("civ_treasury", owner), ("workshop_cash", site.site), capital,
                        "phase10")
        terms = FirmTerms(firm=site.site, region=site.region, opened_turn=world.turn,
                          settlement_id=site.settlement_id, capital=capital, capital_payer=owner)
        terms.totals["capital"] = capital
        state.firms.append(terms)
        _bump(state, "firms_opened")
        _bump(state, "capital_paid", capital)
        _log(state, world.turn, "opened", site.site, capital=capital, payer=owner, plan_price=price)
        row = _row(t, firm)
        row["capital_in"] = capital
        row["event"] = "opened"


def commit_frame(world, pt) -> None:
    """After payroll's receipts: this turn's A3 frame, one receipt per firm."""
    state = _state(world)
    t = _turn(state, world)
    payroll = _payroll(world)
    frame = []
    for receipt in payroll.frame:
        row = t.rows.get(receipt.site) or {}
        terms = _terms(state, receipt.site) or next((f for f in state.closed if f.firm == receipt.site), None)
        if terms is None:
            continue
        if terms.status == "open":
            terms.turns += 1
        _bump(state, "firm_turns")
        sold = receipt.sales + int(receipt.household_sales or 0)
        if not sold:
            _bump(state, "demand_absent_firm_turns")
        frame.append(EconomicsReceipt(
            turn=world.turn, firm=receipt.site, region=receipt.region, owner=receipt.controller,
            status=terms.status, operating=bool(row.get("operating", False)), inputs=row.get("inputs"),
            produced=int(row.get("produced", 0)), titled=int(row.get("titled", 0)),
            free_use_upper_bound=int(row.get("free_use_upper_bound", 0)),
            academy_sales=receipt.sales, academy_sold=receipt.sold, households=row.get("households"),
            customer_absent=list(row.get("customer_absent", [])), capital_in=int(receipt.capital or 0),
            wages_due=receipt.wages_due, wages_paid=receipt.wages_paid, owed_after=receipt.owed_after,
            worn=receipt.worn, returned=receipt.returned, distributed=receipt.distributed, written_off=receipt.written_off, cash_open=receipt.cash_open,
            cash_close=receipt.cash_close, inventory_open=receipt.inventory_open,
            inventory_close=receipt.inventory_close, unsold_inventory=receipt.inventory_close,
            owner_asset_spend=int(row.get("owner_asset_spend", 0)), idle_run=terms.idle_run,
            insolvent_run=next((f.insolvent_run for f in payroll.firms if f.site == receipt.site), 0),
            event=row.get("event") or receipt.event))
    for r in frame:
        paid = (r.households or {}).get("paid_milli", 0)
        bought = (r.households or {}).get("bought_milli", 0)
        charged = (r.inputs or {}).get("charged_milli", 0)
        if r.cash_close != (r.cash_open + r.capital_in + r.academy_sales + paid - charged - r.wages_paid
                            - r.distributed - r.written_off):
            raise RuntimeError(f"workshop firm {r.firm} A3 receipt cash does not close")
        if r.inventory_close != r.inventory_open + r.titled - r.academy_sold - bought - r.worn - r.returned:
            raise RuntimeError(f"workshop firm {r.firm} A3 receipt inventory does not close")
    state.frame = frame[-MAX_FRAME:]
    state.frame_turn = world.turn
    money.check_book(state.book)
    state._turn = None


def check_firm(world, firm) -> None:
    """A3's own invariants on one firm, beside L6a's ``check_firm``: the only
    credits are capital (at most once) and sales."""
    state = _state(world)
    terms = _terms(state, firm.site) or next((f for f in state.closed if f.firm == firm.site), None)
    if terms is not None and firm.totals.get("capital", 0) != terms.capital:
        raise RuntimeError(f"workshop firm {firm.site} capital does not match its single opening payment")


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------

def snapshot_summary(world) -> dict:
    state = _state(world)
    source = world.turn - 1
    fresh = state.frame_turn == source
    from chronicler.workshop_payroll import RESERVE_TURNS
    from chronicler.workshops import K_RAW_PER_WORK
    return {
        "schema_version": 1, "stage": "A3", "mode": state.mode, "source_turn": source,
        "units": {"money": "milli_treasury_units", "wares": "milli_loads", "price": "milli_per_load",
                  "milli": MILLI},
        "firms": [f.model_dump() for f in state.firms],
        "closed": [f.model_dump() for f in state.closed],
        # The observations a reader needs: open sites' regions (the full set, kept
        # for the realm fallback, can be every region).
        "prices": [p.model_dump() for p in state.prices
                   if p.region in {s.region for s in world.livelihoods.workshops.sites}],
        "closed_settlements": list(state.closed_settlements),
        # None: no completed A3 pass for the source turn (unknown, not zero).
        "receipts": [r.model_dump() for r in state.frame] if fresh else None,
        "flows": ([f.model_dump() for f in state.book.flows] if fresh and state.book.flows_turn == source
                  else [] if fresh else None),
        "book": {"carry": dict(state.book.carry), "sinks": dict(state.book.sinks)},
        "counters": {k: state.counters[k] for k in COUNTERS if k in state.counters},
        "log": [r.model_dump() for r in state.log], "log_dropped": state.log_dropped,
        "parameters": {"capital_milli": CAPITAL, "idle_close_after": IDLE_CLOSE_AFTER,
                       "input_slack_milli": INPUT_SLACK, "wares_per_head_milli": WARES_PER_HEAD,
                       "adult_age": ADULT_AGE, "depopulation_share": DEPOPULATION_SHARE,
                       "depopulation_window": DEPOPULATION_WINDOW, "k_raw_per_work": K_RAW_PER_WORK,
                       "reserve_turns": RESERVE_TURNS},
    }
