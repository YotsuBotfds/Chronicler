"""L9 local collective budgets and material bargaining (``--local-budgets``, default off).

One existing decision point per civilization, its ruler (judged at its seat
city), makes a finite budget choice in Phase 10 of turn T for turn T+1 among
executable public services. Requires ``--agents hybrid`` and
``--grain-reserves``; a service whose own switch is off simply produces no
proposal. While active, the governed services spend only through an
accepted envelope: an unfunded promise does nothing.

Services (built-in providers; each reuses an existing public API)
    ``relief``: public granary procurement (``grain_reserves.tick_grain_reserves``,
    Phase 10 of T+1) is capped by the civ's relief envelope instead of its own
    budget share; the grain is released in a later shortfall (to the poorest
    households under ``--food-allocation-regime targeted_relief``).
    ``granary_maintain`` / ``granary_expand``: storage work through
    ``grain_storage.set_storage_policy`` (installed here for the next Phase 2;
    every storage region without an envelope is set to neglect). The two
    claim the same storage slot, so they are incompatible.
    ``workshop``: an L1 site's next bill is paid only if its envelope covers it
    (``workshops._plan_funding`` consults :func:`workshop_funded`).
    ``teaching_supplies``: an academy's purchase from an L6a workshop firm
    (``--workshop-payroll``) is paid only within the envelope for (ruler,
    firm site) (``workshop_payroll._sell`` reads :func:`envelope`). The
    academies' own market procurement (``learning_services``) cannot be
    capped without editing a byte-pinned file: its dated upper bound is
    reserved first as a standing obligation, so no envelope promises the
    coins it takes. L5 learning cohorts spend no treasury.
    ``wardens``: an L8 commons rule's warden bill (``--commons-rules``) is
    paid, and a new rule adopted, only within the envelope for its stand
    (``commons_rules.prepare_phase2`` reads :func:`envelope`).
    ``repairs``: all RS2 repair spending of a ruler (``--repair-projects``:
    workshop repair wages and granary repair coins, hence the timber that
    work uses) stays within its one ``repairs:<civ>`` envelope
    (``repair_projects`` reads :func:`envelope`); a granary under a repair
    project takes no ``granary_*`` envelope (its storage request is
    suspended).

Budget. ``budget = floor(ENVELOPE_SHARE x max(0, projected - FLOOR -
obligations - committed))``: the projected treasury replays queued ``keep``
changes (``finance._projections``); obligations are the teaching reserve;
committed is any envelope still open. Every accepted envelope of a civ is
committed against this one budget, so services never spend the same coins.

Proposals (dated observations of turn T only; at most ``MAX_PROPOSALS``).
Each has an executable cost, eligible recipients, an expected delivery and
the burden it relieves for each constituency:

* commons, the poorer households (their voice: the faction the existing
  movements model allies with the commons creed, ``agent_movements._ally_faction``):
  burden = food shortfall of the poorer half by means (L2 receipts; without
  them the regional shortfall), plus granary wear (extra spoilage over
  ``HORIZON`` turns and the reserve target the worn capacity cannot hold);
* patricians, the towns' merchants and burghers (``cities._merchant_influence``):
  burden = workshop crew work standing idle.

Arbitration (``bargained``). Each constituency proposes its own preferred
feasible allocation (greedy by its relieved burden per coin, partial funding
only for divisible services, one award per claim). A compromise allocation
is greedy by the influence-weighted shares of each constituency's own best.
The council adopts the candidate maximising ``sum(influence x satisfaction)``,
satisfaction being the share of a constituency's own best feasible relief
(1 for a constituency with nothing to gain); ties go to the compromise, then
constituencies in declaration order. Promises are the adopted allocation's
awards, so no constituency holds incompatible promises.
``fixed_shares`` is the cost-retaining control: the same budget split by
``FIXED_SHARES`` per service group in a fixed order, no bargaining, no
political response.

Delivery and response. At the next Phase 10 each envelope is settled from
the service's own receipts: kept (delivered at least ``KEPT_RATIO`` of the
promise, or the need met), deferred with a dated reason (budget loss,
inputs, work, supply, a lost recipient) or lapsed. In ``bargained`` mode the
observed delivery, not the selection, moves the venue city's grievance
(``+BROKEN_GRIEVANCE x (1 - delivered share)`` for a deferral,
``-KEPT_GRIEVANCE`` for a kept promise), capped at ``RESPONSE_CAP`` per city
per turn and kept in [0, 1]. Grievance already feeds the cities' unrest
target, revolts, concessions and free cities; those existing outcomes are
the consequences, not new ones, and no second unrest signal is added.

No random draws; civs, regions, sites and commitments are visited by index.
All parameters are declared modeling choices, not calibrated.
"""
from __future__ import annotations

import math
from importlib import import_module

from chronicler.local_budgets_state import (
    CANDIDATES, CONSTITUENCIES, MAX_PROPOSALS, MAX_SETTLED, REASONS, SERVICES,
    Award, Commitment, Decision, LocalBudgetState, Proposal, Response,
)

# Declared modeling choices (proposed tuning keys ``livelihoods.budgets.*``).
ENVELOPE_SHARE = 0.25      # of the disposable treasury per turn, for all governed services
FLOOR = 20                 # treasury a ruler keeps out of the budget (as grain reserves' TREASURY_FLOOR)
HORIZON = 10.0             # turns over which granary wear is counted
KEPT_RATIO = 0.95          # delivered share that keeps a promise
BROKEN_GRIEVANCE = 0.10    # city grievance per broken promise, times the undelivered share
KEPT_GRIEVANCE = 0.03      # city grievance eased per kept promise
RESPONSE_CAP = 0.10        # |grievance change| per city per turn
#: fixed_shares control: budget share per service group (fixed order). The
#: built-in groups sum to 1; a registered group adds its weight only while its
#: provider is active, and every share is then divided by the active total,
#: so with only the built-in groups the split is exactly 0.4 / 0.3 / 0.3.
FIXED_SHARES: dict[str, float] = {"relief": 0.4, "granary": 0.3, "workshop": 0.3,
                                  "teaching": 0.15, "wardens": 0.15, "repairs": 0.2}
_BUILT_IN_GROUPS = ("relief", "granary", "workshop")
EPS = 1e-9

#: Proposal providers, in declaration order (append only). Each resolves to
#: an object with ``services``, ``group``, ``proposals``, ``install``,
#: ``settle`` and ``obligations`` (see :class:`Provider`). L5/L6/L8 append here.
PROVIDERS: tuple[str, ...] = (
    "chronicler.local_budgets:RELIEF",
    "chronicler.local_budgets:GRANARY",
    "chronicler.local_budgets:WORKSHOP",
    "chronicler.local_budgets:TEACHING",
    "chronicler.local_budgets:WARDENS",
    "chronicler.local_budgets:RELOCATION",
    "chronicler.local_budgets:REPAIRS",
)


def _state(world) -> LocalBudgetState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "local_budgets", None) if container is not None else None


def _reserves_on(world) -> bool:
    from chronicler.grain_reserves_state import grain_reserves_on
    return grain_reserves_on(world)


def local_budgets_active(world) -> bool:
    state = _state(world)
    return (state is not None and state.enabled and getattr(world, "agent_mode", None) == "hybrid"
            and _reserves_on(world))


def _bump(state, key: str, value: float = 1) -> None:
    state.counters[key] = round(state.counters.get(key, 0) + value, 6)


def _param(world, name: str, default: float) -> float:
    from chronicler.tuning import get_override
    return float(get_override(world, f"livelihoods.budgets.{name}", default))


def _parameters(world) -> dict[str, float]:
    p = {"envelope_share": _param(world, "envelope_share", ENVELOPE_SHARE),
         "floor": _param(world, "floor", FLOOR),
         "horizon": _param(world, "horizon", HORIZON),
         "broken_grievance": _param(world, "broken_grievance", BROKEN_GRIEVANCE),
         "kept_grievance": _param(world, "kept_grievance", KEPT_GRIEVANCE),
         "response_cap": _param(world, "response_cap", RESPONSE_CAP)}
    if not (0.0 <= p["envelope_share"] <= 1.0 and p["floor"] >= 0 and p["horizon"] >= 0
            and 0.0 <= p["broken_grievance"] <= 1.0 and 0.0 <= p["kept_grievance"] <= 1.0
            and 0.0 <= p["response_cap"] <= 1.0):
        raise ValueError("livelihoods.budgets parameters out of range")
    return p


def _storage(world):
    reserves = getattr(world, "grain_reserves", None)
    return getattr(reserves, "storage", None) if _reserves_on(world) else None


def _neglect_all(world) -> None:
    storage = _storage(world)
    if storage is None or getattr(storage, "_active_plan", None) is not None:
        return
    from chronicler.grain_storage import set_storage_policy
    for rid in range(len(storage.policies)):
        set_storage_policy(world, rid, "neglect", 0.0)


def set_local_budgets_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    mode = getattr(args, "local_budget_mode", None) if args is not None else None
    state = _state(world)
    was_on = state is not None and state.enabled
    if state is None:
        world.livelihoods.local_budgets = state = LocalBudgetState(mode=mode or "bargained")
    elif mode is not None:
        state.mode = mode
    state.enabled = bool(value)
    if value and not was_on:
        # L9 owns the storage policy while active; nothing is funded before
        # the first decision.
        _neglect_all(world)
    if not value and was_on:
        for c in state.open:
            c.outcome, c.reason, c.settled_turn = "lapsed", "switched_off", getattr(world, "turn", None)
            _bump(state, "lapsed")
        state.open = []


# ---------------------------------------------------------------------------
# Execution hooks called by the governed services (identity when inactive)
# ---------------------------------------------------------------------------

def _open_for(state, world, service: str):
    return [c for c in state.open if c.service == service and c.for_turn == world.turn]


def workshop_funded(world, payer: int, site, cost: int, funded: bool) -> bool:
    """L1 Phase 2 gate: with L9 active a bill is paid only within its envelope."""
    state = _state(world)
    if state is None or not local_budgets_active(world):
        return funded
    allowed = False
    for c in _open_for(state, world, "workshop"):
        if c.site != site.site:
            continue
        mine = c.civ == payer
        allowed = allowed or (mine and funded and c.amount >= cost)
        state._trace[("workshop", c.cid)] = {"turn": world.turn, "payer": payer, "cost": int(cost),
                                             "treasury_ok": bool(funded), "allowed": bool(mine and funded and c.amount >= cost)}
    return allowed


def procurement_budget(world, budget: list[int], projected: list[int]) -> list[int]:
    """Phase 10 granary purchases: with L9 active only the relief envelope
    (within the treasury above the floor) may be spent."""
    state = _state(world)
    if state is None or not local_budgets_active(world):
        return budget
    floor = int(_parameters(world)["floor"])
    out = [0] * len(budget)
    for c in _open_for(state, world, "relief"):
        if not 0 <= c.civ < len(out) or not world.civilizations[c.civ].regions:
            continue
        available = max(0, int(projected[c.civ]) - floor)
        cap = min(c.amount, available)
        out[c.civ] = cap
        state._trace[("relief", c.cid)] = {"turn": world.turn, "available": available, "cap": cap}
    return out


# ---------------------------------------------------------------------------
# Dated observations of the turn being settled
# ---------------------------------------------------------------------------

class _Obs:
    """Observations of turn ``turn`` (completed phases), read in its Phase 10."""

    def __init__(self, world, economy, bridge):
        self.turn = world.turn
        self.economy = economy
        self.bridge = bridge
        self.index = {c.name: i for i, c in enumerate(world.civilizations)}
        n = len(world.regions)
        from chronicler.economy import PER_CAPITA_FOOD
        from chronicler.tuning import get_override
        self.pcf = float(get_override(world, "economy.per_capita_food", PER_CAPITA_FOOD))
        self.demand = [0.0] * n
        self.price = [0.0] * n
        self.surplus = [0.0] * n
        self.hunger: list[float | None] = [None] * n
        self.hunger_source = None
        self.trace: dict = {}
        self.graph = None
        self.own_need = None
        self.held: dict = {}
        if economy is None:
            return
        from chronicler.grain_reserves import _demand, _food_price
        self.demand = [_demand(economy, r.name) for r in world.regions]
        self.price = [_food_price(economy, r.name) for r in world.regions]
        self._surplus(world)
        self._hunger(world)

    def _surplus(self, world) -> None:
        from chronicler.economy import FOOD_GOODS
        from chronicler.grain_reserves import GRAIN, KEEP_TURNS
        held_all = {}
        if self.bridge is not None and getattr(world, "agent_mode", None) == "hybrid":
            from chronicler.mutual_aid import read_stockpile_commitments
            held_all = read_stockpile_commitments(world, self.bridge._sim)
        self.held = held_all
        for rid, region in enumerate(world.regions):
            if region.controller not in self.index or self.demand[rid] <= 0 or region.population <= 0:
                continue
            held = held_all.get(region.name, {})
            goods = region.stockpile.goods
            free = {g: max(0.0, goods.get(g, 0.0) - held.get(g, 0.0)) for g in sorted(FOOD_GOODS)}
            self.surplus[rid] = max(0.0, min(free[GRAIN], math.fsum(free.values()) - KEEP_TURNS * self.demand[rid]))

    def _hunger(self, world) -> None:
        container = getattr(world, "livelihoods", None)
        food = getattr(container, "food_allocation", None)
        from chronicler.food_allocation import food_allocation_active
        if food is not None and food_allocation_active(world):
            if food.frame_turn != self.turn:
                return                                     # unknown, not zero
            self.hunger = [0.0] * len(world.regions)
            for row in food.regions:
                rid = int(row["region"])
                if 0 <= rid < len(self.hunger):
                    self.hunger[rid] = float(row["shortfall_poorer_half"]) * self.pcf
            self.hunger_source = "poorer_half"
            return
        suff = getattr(self.economy, "food_sufficiency", {}) or {}
        for rid, region in enumerate(world.regions):
            s = suff.get(region.name)
            if isinstance(s, (int, float)) and math.isfinite(s):
                self.hunger[rid] = max(0.0, 1.0 - float(s)) * self.demand[rid]
        self.hunger_source = "regional"


def _own_needs(world, obs) -> dict[int, float]:
    """Each ruler's own granary deficits (net of grain on the road)."""
    inbound = _inbound(world)
    need: dict[int, float] = {}
    for rid, (region, g) in enumerate(zip(world.regions, world.grain_reserves.granaries)):
        if g.owner >= 0 and obs.index.get(region.controller) == g.owner and obs.demand[rid] > 0:
            need[g.owner] = need.get(g.owner, 0.0) + max(0.0, g.target - g.grain - inbound[rid])
    return need


def _expected_short(world, rid: int, obs) -> float:
    """Food the region's own harvest record (the granary's yearly harvest
    mean, counted up to the need) expects it to lack over ``HORIZON`` turns."""
    granary = world.grain_reserves.granaries[rid]
    if granary.observed <= 0:
        return 0.0
    return _parameters(world)["horizon"] * max(0.0, 1.0 - granary.harvest_mean) * obs.demand[rid]


def _purchase_estimate(world, name: str, deficits: dict[int, float], obs):
    """What the granary purchase rule could buy for these deficits from the
    observed surpluses with an unlimited envelope: its own realm within
    ``MAX_HOPS`` of the route graph (nearest, then cheapest), then one step
    abroad (cheapest), where every ruler first buys for its own granaries,
    so a foreign market sells only beyond its own ruler's granary deficits;
    whole coins per purchase (one below a coin buys nothing); transit loss
    off the granary's own market. Returns (grain received, coins, grain by
    granary)."""
    from chronicler.grain_reserves import MAX_HOPS, _realm_hops, _transit_loss
    if obs.graph is None:
        obs.graph = _route_graph(world)
    if obs.own_need is None:
        obs.own_need = _own_needs(world, obs)
    loss = _transit_loss()
    surplus = list(obs.surplus)
    for src, region in enumerate(world.regions):
        ruler = obs.index.get(region.controller)
        if region.controller != name and ruler is not None:
            surplus[src] = max(0.0, surplus[src] - obs.own_need.get(ruler, 0.0))
    grain, coins, bought = 0.0, 0, {}
    for rid in sorted(deficits):
        hops = _realm_hops(world, obs.graph, rid, name)
        steps = {}
        for own, h in hops.items():
            if h < MAX_HOPS:
                for src in obs.graph.get(own, ()):
                    ctrl = world.regions[src].controller
                    if ctrl is not None and ctrl != name and ctrl in obs.index and (src not in steps or h + 1 < steps[src]):
                        steps[src] = h + 1
        order = (sorted(hops, key=lambda s: (hops[s], obs.price[s], s))
                 + sorted(steps, key=lambda s: (obs.price[s], steps[s], s)))
        deficit = deficits[rid]
        for src in order:
            p = obs.price[src]
            if deficit <= EPS:
                break
            if surplus[src] <= EPS or p <= 0:
                continue
            keep = 1.0 if src == rid else 1.0 - loss
            cost = int(math.floor(min(surplus[src], deficit / keep) * p + EPS))
            if cost < 1:
                continue
            sent = min(surplus[src], cost / p)
            surplus[src] -= sent
            deficit -= sent * keep
            grain += sent * keep
            coins += cost
            bought[rid] = bought.get(rid, 0.0) + sent * keep
    return grain, coins, bought


def _route_graph(world):
    from chronicler.grain_reserves import _route_graph as graph
    return graph(world)


def _inbound(world) -> list[float]:
    n = len(world.regions)
    shipments = getattr(world.grain_reserves, "shipments", None)
    if shipments is None:
        return [0.0] * n
    from chronicler.public_grain_shipments import inbound_by_destination
    inbound = list(inbound_by_destination(world) or [0.0] * n)
    if getattr(world, "livelihoods", None) is not None and getattr(world.livelihoods, "grain_convoys", None) is not None:
        from chronicler.grain_convoys import add_convoy_inbound
        add_convoy_inbound(world, inbound)
    return inbound


# ---------------------------------------------------------------------------
# Built-in providers
# ---------------------------------------------------------------------------

class Provider:
    """Proposal-provider interface (L5 learners, L6 payroll, L8 commons enforcement).

    ``services``: the service names it proposes (unique across providers);
    ``group``: its ``FIXED_SHARES`` group (0 share unless declared there).
    ``proposals(world, civ, obs)`` returns dicts with the :class:`Proposal`
    fields except ``pid``/``civ``/``source_turn``, from dated observations only.
    ``install(world, commitments)`` is called once per decision with this
    provider's new envelopes (possibly none) and must make the service spend
    only within them; the service reads its envelope back with
    :func:`envelope` at execution and may record :func:`record_execution`.
    ``settle(world, commitment, obs)`` returns the observed delivery:
    ``{"outcome": "kept"|"deferred", "reason": REASONS item or None,
    "spent": int, "delivered": float, "ratio": float, "detail": {...}}``.
    ``obligations(world, civ, obs)`` returns coins the provider will spend
    next turn that it cannot cap (reserved before any envelope).
    """

    services: tuple[str, ...] = ()
    group = ""

    def active(self, world) -> bool:
        """Whether the service runs this turn (its own switch); a registered
        group takes a fixed share only while active."""
        return True

    def proposals(self, world, civ: int, obs) -> list[dict]:
        return []

    def install(self, world, commitments: list[Commitment]) -> None:
        return None

    def settle(self, world, commitment: Commitment, obs) -> dict:
        return {"outcome": "deferred", "reason": "service_off", "spent": 0, "delivered": 0.0, "ratio": 0.0}

    def obligations(self, world, civ: int, obs) -> int:
        return 0


def envelope(world, civ: int, service: str, *, site: int | None = None, region: int | None = None,
             claim: str | None = None) -> int | None:
    """The amount a registered service may spend this turn: the sum of the
    civ's open envelopes for it (optionally one site, recipient region or
    claim); 0 without one. None while L9 is inactive: keep the legacy rule."""
    state = _state(world)
    if state is None or not local_budgets_active(world):
        return None
    total = 0
    for c in _open_for(state, world, service):
        if (c.civ == civ and (site is None or c.site == site) and (region is None or region in c.recipients)
                and (claim is None or claim in c.claims)):
            total += c.amount
    return total


def reserved(world, civ: int, group: str) -> int | None:
    """Coins the last decision reserved for ``group``'s uncapped spending this
    turn (its provider's ``obligations``, reserved before any envelope); the
    service spends no more. 0 for a civ that made no decision. None while L9
    is inactive or made no decision for this turn: keep the service's rule."""
    state = _state(world)
    if state is None or not local_budgets_active(world) or state.decision_turn != world.turn - 1:
        return None
    for d in state.decisions:
        if d.civ == civ:
            return int(d.reserved.get(group, 0))
    return 0


def record_execution(world, commitment_cid: int, service: str, **fields) -> None:
    state = _state(world)
    if state is not None:
        state._trace[(service, commitment_cid)] = {"turn": world.turn, **fields}


class _Relief(Provider):
    services = ("relief",)
    group = "relief"

    def proposals(self, world, civ, obs):
        if obs.economy is None or not _reserves_on(world):
            return []
        name = world.civilizations[civ].name
        granaries = world.grain_reserves.granaries
        if len(granaries) != len(world.regions):
            return []
        inbound = _inbound(world)
        deficits = {}
        for rid, (region, g) in enumerate(zip(world.regions, granaries)):
            if g.owner == civ and region.controller == name and obs.demand[rid] > 0:
                d = g.target - g.grain - inbound[rid]
                if d > EPS:
                    deficits[rid] = d
        need = math.fsum(deficits.values())
        grain, cost, bought = _purchase_estimate(world, name, deficits, obs)
        if grain <= EPS or cost < 1:
            return []
        price = cost / grain
        share = grain / need
        if any(obs.hunger[r] is None for r in deficits):
            relieved = None
        else:
            # The shortfall seen now plus the reserve gap: the harvest shortfall
            # the granary's own harvest record expects over the horizon.
            relieved = math.fsum(min(bought.get(r, 0.0), obs.hunger[r] + _expected_short(world, r, obs))
                                 for r in deficits)
        return [dict(service="relief", recipients=sorted(deficits), claims=[f"procurement:{civ}"],
                     cost=cost, divisible=True, unit="grain", expected=grain,
                     relief={} if relieved is None else {"commons": relieved},
                     detail={"price": round(price, 6), "deficit": round(need, 6), "share": round(share, 6),
                             "hunger": None if relieved is None else round(math.fsum(obs.hunger[r] for r in deficits), 6),
                             "expected_short": round(math.fsum(_expected_short(world, r, obs) for r in deficits), 6)})]

    def settle(self, world, c, obs):
        trace = obs.trace.get(("relief", c.cid))
        if trace is None or trace["turn"] != world.turn:
            reason = "no_economy" if obs.economy is None else "service_off"
            return {"outcome": "deferred", "reason": reason, "spent": 0, "delivered": 0.0, "ratio": 0.0}
        opening, remaining = (getattr(obs.economy, "food_procurement_budget", {}) or {}).get(c.civ, (0, 0))
        spent = max(0, int(opening) - int(remaining))
        from chronicler.grain_reserves_state import BOUGHT, DISPATCHED
        state = world.grain_reserves
        grain = math.fsum(f.amount for f in state.flows if state.flows_turn == world.turn
                          and f.buyer == c.civ and f.kind in (BOUGHT, DISPATCHED))
        # L4 convoys buy after the granary pass from what the envelope left
        # and deduct their purchase and escort fee from the same procurement
        # budget, so ``opening - remaining`` already counts both: the fees are
        # spent inside the envelope and are only itemised here.
        convoys = getattr(getattr(world, "livelihoods", None), "grain_convoys", None)
        escort = 0
        if convoys is not None and convoys.frame_turn == world.turn:
            for row in convoys.frame:
                if row.operation == "dispatched" and row.buyer == c.civ and row.turn == world.turn:
                    escort += int(row.escort_fee or 0)
                    grain += row.cargo
        inbound = _inbound(world)
        name = world.civilizations[c.civ].name
        open_need = math.fsum(max(0.0, g.target - g.grain - inbound[rid])
                              for rid, (r, g) in enumerate(zip(world.regions, state.granaries))
                              if g.owner == c.civ and r.controller == name)
        ratio = min(1.0, grain / c.expected) if c.expected > EPS else 1.0
        detail = {"cap": trace["cap"], "available": trace["available"], "open_need": round(open_need, 6),
                  "escort_fees": escort}
        if ratio >= KEPT_RATIO or spent >= KEPT_RATIO * c.amount or open_need <= EPS:
            return {"outcome": "kept", "reason": None, "spent": spent, "delivered": grain,
                    "ratio": 1.0 if open_need <= EPS else ratio, "detail": detail}
        reason = "treasury_shortfall" if trace["cap"] < c.amount and spent >= trace["cap"] - 1 else "no_supply"
        return {"outcome": "deferred", "reason": reason, "spent": spent, "delivered": grain,
                "ratio": ratio, "detail": detail}


class _Granary(Provider):
    services = ("granary_maintain", "granary_expand")
    group = "granary"

    def proposals(self, world, civ, obs):
        storage = _storage(world)
        if storage is None or obs.economy is None:
            return []
        from chronicler import grain_storage as G
        name = world.civilizations[civ].name
        receipts = {r.region: r for r in storage.receipts} if storage.receipt_turn == obs.turn else {}
        horizon = _parameters(world)["horizon"]
        busy = _repair_regions(world)
        out = []
        for rid, (region, asset) in enumerate(zip(world.regions, storage.assets)):
            receipt = receipts.get(rid)
            if asset is None or receipt is None or asset.owner != civ or region.controller != name \
                    or rid in busy:
                continue
            grain = world.grain_reserves.granaries[rid].grain
            c, k = asset.condition, asset.capacity
            requested = receipt.target_requested if receipt.target_requested is not None else 0.0
            cut = max(0.0, requested - k * c)
            committed = float(obs.held.get(region.name, {}).get("timber", 0.0))
            timber = max(0.0, float(region.stockpile.goods.get("timber", 0.0)) - committed) / G.TIMBER_PER_WORK
            base = {"condition": round(c, 6), "capacity": round(k, 6), "grain": round(grain, 6),
                    "target_cut": round(cut, 6), "timber_work": round(timber, 6)}
            if c < 1.0:
                work = min(G.MAX_WORK_BUDGET, G.REPAIR_WORK - asset.repair_progress, timber)
                if work > EPS:
                    gain = min(1.0 - c, G.REPAIR_GAIN * work / G.REPAIR_WORK)
                    relieved = horizon * G.EXTRA_SPOILAGE * gain * grain + min(cut, k * gain)
                    out.append(dict(service="granary_maintain", recipients=[rid], claims=[f"storage:{rid}"],
                                    cost=math.ceil(work * G.COINS_PER_WORK - EPS), divisible=True,
                                    unit="work", expected=work, relief={"commons": relieved}, detail=base))
            if cut > EPS:
                work = min(G.MAX_WORK_BUDGET, G.EXPANSION_WORK - asset.expansion_progress, timber)
                if work > EPS:
                    added = max(G.EXPANSION_MINIMUM, G.EXPANSION_FRACTION * k) * work / G.EXPANSION_WORK
                    out.append(dict(service="granary_expand", recipients=[rid], claims=[f"storage:{rid}"],
                                    cost=math.ceil(work * G.COINS_PER_WORK - EPS), divisible=True,
                                    unit="work", expected=work, relief={"commons": min(cut, added * c)}, detail=base))
        return out

    def install(self, world, commitments):
        storage = _storage(world)
        if storage is None:
            return
        from chronicler.grain_storage import COINS_PER_WORK, MAX_WORK_BUDGET, set_storage_policy
        chosen = {c.recipients[0]: c for c in commitments}
        for rid in range(len(storage.policies)):
            c = chosen.get(rid)
            if c is None:
                set_storage_policy(world, rid, "neglect", 0.0)
            else:
                policy = "maintain" if c.service == "granary_maintain" else "expand"
                set_storage_policy(world, rid, policy, min(MAX_WORK_BUDGET, c.amount / COINS_PER_WORK))

    def settle(self, world, c, obs):
        storage = _storage(world)
        rid = c.recipients[0]
        receipts = {r.region: r for r in storage.receipts} if storage is not None and storage.receipt_turn == world.turn else {}
        receipt = receipts.get(rid)
        if receipt is None:
            return {"outcome": "deferred", "reason": "service_off", "spent": 0, "delivered": 0.0, "ratio": 0.0}
        promised = c.expected                      # work promised (the coins are rounded up)
        spent = int(receipt.treasury_paid) if receipt.owner == c.civ else 0
        delivered = float(receipt.delivered) if receipt.owner == c.civ else 0.0
        ratio = min(1.0, delivered / promised) if promised > 0 else 1.0
        detail = {"requested": round(receipt.requested, 6), "condition_after": round(receipt.condition_after, 6),
                  "capacity_after": round(receipt.capacity_after, 6)}
        if receipt.owner != c.civ:
            return {"outcome": "deferred", "reason": "recipient_lost", "spent": 0, "delivered": 0.0,
                    "ratio": 0.0, "detail": {**detail, "foreign_paid": int(receipt.treasury_paid)}}
        if ratio >= KEPT_RATIO:
            return {"outcome": "kept", "reason": None, "spent": spent, "delivered": delivered, "ratio": ratio, "detail": detail}
        trace = obs.trace.get(("granary", c.cid)) or {}
        if receipt.requested < KEPT_RATIO * promised:
            reason = "treasury_shortfall" if trace.get("budget", c.amount) < c.amount else "inputs_short"
        else:
            reason = "work_short"
        return {"outcome": "deferred", "reason": reason, "spent": spent, "delivered": delivered, "ratio": ratio, "detail": detail}


class _Workshop(Provider):
    services = ("workshop",)
    group = "workshop"

    def proposals(self, world, civ, obs):
        container = getattr(world, "livelihoods", None)
        state = getattr(container, "workshops", None)
        from chronicler.workshops import workshops_active
        if state is None or not workshops_active(world) or state.mode == "observe":
            return []
        from chronicler import workshops as W
        name = world.civilizations[civ].name
        frame = {r.site: r for r in state.frame} if state.frame_turn == obs.turn else {}
        out = []
        for site in state.sites:
            if world.regions[site.region].controller != name:
                continue
            receipt = frame.get(site.site)
            work = float(receipt.work_available) if receipt is not None else 0.0
            bill = W._bill(site, world)      # the RS2 legacy-repair gate, as the workshop plans it
            cost = int(sum(bill.values()))
            if cost < 1:
                continue
            if state.mode != "operate":
                stake = 0.0                                  # cost_only: funding never puts the crew to work
            elif "construction" in bill:
                stake = work * bill["construction"] / W.CONSTRUCTION_COST
            else:
                stake = work
            out.append(dict(service="workshop", recipients=[site.region], site=site.site,
                            claims=[f"workshop:{site.site}"], cost=cost, divisible=False, unit="work",
                            expected=stake, relief={"patricians": stake},
                            detail={"asset": site.asset, "arrears": site.arrears,
                                    "condition": round(site.condition, 6), "work_available": round(work, 6),
                                    **{f"bill_{k}": v for k, v in bill.items()}}))
        return out

    def settle(self, world, c, obs):
        state = getattr(world.livelihoods, "workshops", None)
        frame = {r.site: r for r in state.frame} if state is not None and state.frame_turn == world.turn else {}
        receipt = frame.get(c.site)
        trace = obs.trace.get(("workshop", c.cid))
        if state is None:
            return {"outcome": "deferred", "reason": "service_off", "spent": 0, "delivered": 0.0, "ratio": 0.0}
        if receipt is None:
            # Closed site (its city fell or changed) versus a turn without an
            # economy tick or without planning: only the first lost its recipient.
            if all(site.site != c.site for site in state.sites):
                reason = "recipient_lost"
            else:
                reason = "no_economy" if obs.economy is None else "service_off"
            return {"outcome": "deferred", "reason": reason, "spent": 0, "delivered": 0.0, "ratio": 0.0}
        if trace is None:
            return {"outcome": "deferred", "reason": "service_off", "spent": 0, "delivered": 0.0, "ratio": 0.0}
        detail = {"cost": trace["cost"], "asset": receipt.asset, "arrears_after": receipt.arrears_after}
        if receipt.payer == c.civ and receipt.funded:
            return {"outcome": "kept", "reason": None, "spent": int(sum((receipt.paid or {}).values())),
                    "delivered": float(receipt.allocated), "ratio": 1.0, "detail": detail}
        if trace["payer"] != c.civ:
            reason = "recipient_lost"
        elif trace["cost"] > c.amount:
            reason = "cost_rose"
        else:
            reason = "treasury_shortfall"
        return {"outcome": "deferred", "reason": reason, "spent": 0, "delivered": 0.0, "ratio": 0.0, "detail": detail}


def _payroll(world):
    container = getattr(world, "livelihoods", None)
    return getattr(container, "workshop_payroll", None) if container is not None else None


def _academy_customers(world, civ: int, turn: int):
    """The civ's academies whose supply procurement of ``turn`` was fully
    informed, with their material inventory, in seat order (as L6a sells)."""
    services = getattr(getattr(world, "scholarship", None), "learning_services", None)
    if services is None or not getattr(services, "enabled", True):
        return []
    assets = {(a.seat_id, a.region, a.founder, a.founded_turn, a.seat_name): a
              for a in (getattr(services, "inventories", None) or []) if not a.retired}
    out = []
    for r in getattr(services, "procurement_receipts", None) or []:
        if (r.source_turn != turn or r.lord != civ or r.shortfalls or not r.craft_price or r.craft_price <= 0
                or r.scholar_upper_bound is None or r.learner_upper_bound is None):
            continue
        asset = assets.get((r.seat_id, r.region, r.founder, r.founded_turn, r.seat_name))
        if asset is not None and asset.held is not None:
            out.append((r, asset))
    return sorted(out, key=lambda ra: ra[0].seat_id)


class _Teaching(Provider):
    """Academy supplies.

    The academies' own market procurement (``learning_services``) cannot be
    capped without editing a byte-pinned file: its dated upper bound is
    reserved first (``obligations``). Their purchase from an L6a workshop
    firm (``--workshop-payroll``) is the ruler's Phase 10 treasury spend in a
    sprint module, so it is a bargained service, ``teaching_supplies``:
    ``workshop_payroll._sell`` reads the envelope for (ruler, firm site).
    The stake the patricians weigh is the firm crew's wages the sale's cash
    would cover (owed wages plus next turn's bill beyond the firm's cash), in
    crew work units; the learners have no separate voice (see the docs).
    """

    services = ("teaching_supplies",)
    group = "teaching"

    def active(self, world):
        from chronicler.workshop_payroll import workshop_payroll_active
        state = _payroll(world)
        return state is not None and workshop_payroll_active(world) and state.mode != "no_customer"

    def proposals(self, world, civ, obs):
        if obs.economy is None or not self.active(world):
            return []
        from chronicler import workshop_payroll as P
        from chronicler.learning_services import CRAFTS_PER_LEARNER, LEARNERS_PER_SCHOLAR
        state = _payroll(world)
        customers = _academy_customers(world, civ, obs.turn)
        if not customers:
            return []
        need = {}
        for r, asset in customers:
            want = min(float(r.learner_upper_bound), r.scholar_upper_bound * LEARNERS_PER_SCHOLAR)
            need[r.seat_id] = math.floor(max(0.0, want * CRAFTS_PER_LEARNER - asset.held) * P.MILLI)
        name = world.civilizations[civ].name
        # The firm titles next turn's output before it sells: last turn's
        # titled wares are the dated estimate of what it adds.
        titled = {r.site: r.titled for r in state.frame} if state.frame_turn == obs.turn else {}
        out = []
        for firm in sorted(state.firms, key=lambda f: f.site):
            stock = firm.inventory + titled.get(firm.site, 0)
            if firm.status != "open" or stock <= 0 or world.regions[firm.region].controller != name:
                continue
            inventory, units, quantity = stock, 0, 0
            for r, _asset in customers:
                if need[r.seat_id] <= 0 or inventory <= 0:
                    continue
                price = float(r.craft_price)
                cap = min(inventory, need[r.seat_id])
                u = math.floor(cap * price / P.MILLI)
                while u > 0 and math.floor(u * P.MILLI / price) > cap:
                    u -= 1
                q = math.floor(u * P.MILLI / price) if u else 0
                if u <= 0 or q <= 0:
                    continue
                units, quantity, inventory = units + u, quantity + q, inventory - q
                need[r.seat_id] -= q
            if units < 1:
                continue
            owed = sum(o.amount for o in firm.owed)
            bill = P._bill(firm, firm.crew_cap, firm.hours) if state.mode != "unpaid_labor" else 0
            covered = min(units * P.MILLI, max(0, owed + bill - firm.cash))
            out.append(dict(service="teaching_supplies", recipients=[firm.region], site=firm.site,
                            claims=[f"teaching:{firm.site}"], cost=units, divisible=True, unit="crafts",
                            expected=quantity / P.MILLI,
                            relief={"patricians": covered / P.WAGE_PER_WORK} if covered > 0 else {},
                            detail={"inventory": firm.inventory, "titled_last": titled.get(firm.site, 0),
                                    "cash": firm.cash, "owed": owed,
                                    "next_bill": bill, "learners_served": round(quantity / P.MILLI, 6)}))
        return out

    def settle(self, world, c, obs):
        from chronicler import workshop_payroll as P
        state = _payroll(world)
        frame = {r.site: r for r in state.frame} if state is not None and state.frame_turn == world.turn else {}
        row = frame.get(c.site)
        if row is None or row.controller != c.civ:
            return {"outcome": "deferred", "reason": "recipient_lost", "spent": 0, "delivered": 0.0, "ratio": 0.0}
        spent = row.sales // P.MILLI
        delivered = row.sold / P.MILLI
        ratio = min(1.0, delivered / c.expected) if c.expected > EPS else 1.0
        remaining = math.fsum(P._remaining_need(r, asset) for r, asset in _academy_customers(world, c.civ, world.turn))
        detail = {"customers": row.customers, "inventory_open": row.inventory_open,
                  "remaining_need": round(remaining, 6)}
        if spent >= KEPT_RATIO * c.amount or ratio >= KEPT_RATIO or (row.sold and remaining * P.MILLI < 1):
            return {"outcome": "kept", "reason": None, "spent": spent, "delivered": delivered,
                    "ratio": 1.0 if remaining * P.MILLI < 1 else ratio, "detail": detail}
        prices = [float(r.craft_price) for r, _ in _academy_customers(world, c.civ, world.turn)]
        left = row.inventory_open - row.sold
        if remaining * P.MILLI < 1:
            reason = "no_demand"                    # no informed order with need left
        elif left <= 0 or not prices or math.floor(min(left, remaining * P.MILLI) * max(prices) / P.MILLI) < 1:
            reason = "inputs_short"                 # the wares left are worth less than a coin
        else:
            reason = "treasury_shortfall"
        return {"outcome": "deferred", "reason": reason, "spent": spent, "delivered": delivered,
                "ratio": ratio, "detail": detail}

    def obligations(self, world, civ, obs):
        from chronicler.learning_services import LEARNERS_PER_SCHOLAR, learning_services_active
        services = getattr(getattr(world, "scholarship", None), "learning_services", None)
        if services is None or not learning_services_active(world):
            return 0
        total = 0
        for r in getattr(services, "procurement_receipts", None) or []:
            if r.source_turn != obs.turn or r.lord != civ:
                continue
            if r.craft_price is not None and r.learner_upper_bound is not None and r.scholar_upper_bound is not None:
                want = min(float(r.learner_upper_bound), r.scholar_upper_bound * LEARNERS_PER_SCHOLAR)
                total += max(int(r.paid), math.ceil(want * r.craft_price - EPS))
            else:
                total += int(r.paid)
        return total


def _commons(world):
    container = getattr(world, "livelihoods", None)
    return getattr(container, "commons_rules", None) if container is not None else None


class _Wardens(Provider):
    """L8 commons enforcement: a ruler's warden bills for its timber rules
    (``--commons-rules``). ``commons_rules.prepare_phase2`` pays each rule's
    bill (and adopts a new rule) only within the envelope for
    ``wardens:<region>:<slot>``. Proposals read the timber account the next
    planning will read (settled in this turn's Phase 2): rules that would
    continue (no repeal reason), and adoption candidates by L8's own rule.
    The stake is the timber the rule keeps from open access over ``HORIZON``
    turns: the L3 reference crew's harvest (``timber_stock.reference_harvest``;
    zero when the last receipt shows nobody could harvest) above the rule's
    quota, bounded by the standing stock and its regrowth, counted as the
    crew work its raw loads could supply the towns' crafts
    (``workshops.K_RAW_PER_WORK``): the patricians' stake. The commons, whose
    timber access the rule restricts, gain nothing from it; the rule's own
    grievance channel already carries their side of the conflict. The full
    bill is promised: the institution's share L8 applies at planning is not
    known at the decision."""

    services = ("wardens",)
    group = "wardens"

    def active(self, world):
        from chronicler.commons_rules import commons_rules_active
        return commons_rules_active(world)

    def _observations(self, world, turn):
        from chronicler.commons_rules_state import StockObservation
        from chronicler.timber_stock import _state as timber_state
        stock = timber_state(world)
        if stock is None or stock.ledger_turn != turn:
            return {}
        return {(row.region_id, row.slot): StockObservation(
                    turn=stock.ledger_turn, stock=row.stock, capacity=row.capacity,
                    extraction=row.extraction, water_gate_open=row.water_gate_open)
                for row in stock.ledger if row.removed == 0.0}

    def proposals(self, world, civ, obs):
        if obs.economy is None or not self.active(world):
            return []
        from chronicler import commons_rules as R
        from chronicler.timber_stock import reference_harvest, regrowth, timber_slots
        from chronicler.workshops import K_RAW_PER_WORK
        state = _commons(world)
        receipts = {(r.region_id, r.slot): r for r in state.frame} if state.frame_turn == obs.turn else {}
        name = world.civilizations[civ].name
        observations = self._observations(world, obs.turn)
        slots = set(timber_slots(world))
        # The full warden bill is promised. L8 applies Commons Management's
        # share from the last settled funding ratio when it plans next turn;
        # the institution's legitimacy can still change before then, so
        # promising the full bill never under-commits. When the institution
        # covers part of it, at most 2 coins per rule per turn stay unspent
        # inside the envelope (settlement spends min(envelope, actual bill)).
        bill = R.bill_for(0.0)
        horizon = _parameters(world)["horizon"]

        def item(rid, slot, observation, new, status=None):
            receipt = receipts.get((rid, slot))
            pressure = 0.0 if receipt is not None and receipt.possible is False \
                else reference_harvest(world.regions[rid], slot)
            quota = 0.0 if R.next_status(status, observation) == "rest" else R.allowable_harvest(
                observation.stock, observation.capacity, observation.water_gate_open)
            kept = horizon * max(0.0, min(pressure, observation.stock) - quota)
            supply = observation.stock + horizon * regrowth(observation.stock, observation.capacity,
                                                            observation.water_gate_open)
            stake = min(kept, supply) / K_RAW_PER_WORK
            return dict(service="wardens", recipients=[rid], claims=[f"wardens:{rid}:{slot}"], cost=bill,
                        divisible=not new, unit="coverage", expected=1.0,
                        relief={"patricians": stake} if stake > EPS else {},
                        detail={"slot": slot, "new": int(new), "stock": round(observation.stock, 6),
                                "capacity": round(observation.capacity, 6),
                                "extraction": round(observation.extraction, 6)})

        out, held = [], set()
        for rule in state.rules:
            key = (rule.region_id, rule.slot)
            if rule.owner != civ or key not in slots or world.regions[rule.region_id].controller != name:
                continue
            held.add(key)
            observation = observations.get(key, rule.observation)
            if observation is None or R._repeal_reason(world, rule, observation) is not None:
                continue
            out.append(item(rule.region_id, rule.slot, observation, False, rule.status))
        cooling = {(c.region_id, c.slot) for c in state.cooldowns if c.until > obs.turn + 1}
        for key in sorted(observations):
            rid, slot = key
            o = observations[key]
            if (key not in slots or key in held or key in cooling or world.regions[rid].controller != name
                    or o.extraction <= 0.0 or o.capacity <= 0.0 or o.stock >= R.ADOPT_BELOW * o.capacity):
                continue
            out.append(item(rid, slot, o, True))
        return out

    def settle(self, world, c, obs):
        state = _commons(world)
        rid, slot = c.recipients[0], int(c.claims[0].rsplit(":", 1)[1])
        receipts = {(r.region_id, r.slot): r for r in state.frame} if state.frame_turn == world.turn else {}
        receipt = receipts.get((rid, slot))
        if receipt is None:
            decision = next((d for d in state.decisions if d.turn == world.turn and d.region_id == rid
                             and d.slot == slot), None)
            if decision is not None and decision.kind == "repealed" and decision.reason == "recovered":
                return {"outcome": "kept", "reason": None, "spent": 0, "delivered": 0.0, "ratio": 1.0,
                        "detail": {"ended": "recovered"}}
            reason = ("recipient_lost" if decision is not None and decision.kind == "lapsed"
                      else "service_off" if decision is not None else "not_adopted")
            return {"outcome": "deferred", "reason": reason, "spent": 0, "delivered": 0.0, "ratio": 0.0,
                    "detail": {"decision": None if decision is None else f"{decision.kind}:{decision.reason}"}}
        if receipt.owner != c.civ:
            return {"outcome": "deferred", "reason": "recipient_lost", "spent": 0, "delivered": 0.0, "ratio": 0.0}
        due = min(c.amount, receipt.bill)
        detail = {"bill": receipt.bill, "coverage": round(receipt.coverage, 6), "status": receipt.status}
        ratio = min(1.0, receipt.paid / due) if due else 1.0
        if receipt.paid >= due:
            return {"outcome": "kept", "reason": None, "spent": receipt.paid, "delivered": receipt.coverage,
                    "ratio": 1.0, "detail": detail}
        rose = receipt.bill > int(c.detail.get("cost", receipt.bill))
        return {"outcome": "deferred", "reason": "cost_rose" if rose else "treasury_shortfall",
                "spent": receipt.paid, "delivered": receipt.coverage, "ratio": ratio, "detail": detail}


class _RelocationAssistance(Provider):
    """L7 assisted relocation: the destination ruler's fare assistance is
    Phase 10 treasury spending L9 cannot cap (it depends on next turn's
    moves), so its ceiling is reserved as an obligation before any envelope.
    Added after a lead review on 2026-11-05 found it outside the one budget.
    The gate installs at most this reservation next turn
    (``relocation_costs.assistance_budgets`` reads :func:`reserved`): review
    R2 (2026-11-05) found the ceiling recomputed on next turn's larger
    treasury, beyond what was reserved."""

    group = "relocation"

    def obligations(self, world, civ, obs):
        container = getattr(world, "livelihoods", None)
        state = getattr(container, "relocation_costs", None) if container is not None else None
        if state is None or not getattr(state, "enabled", False) or state.mode != "assisted":
            return 0
        from chronicler.relocation_costs import ASSIST_SHARE
        return int(math.floor(ASSIST_SHARE * max(0, int(world.civilizations[civ].treasury))))


def _repair_regions(world) -> frozenset:
    """Regions whose granary is under an RS2 repair project (empty unless active)."""
    if getattr(getattr(world, "livelihoods", None), "repair_projects", None) is None:
        return frozenset()
    from chronicler.repair_projects import storage_suspended_regions
    return storage_suspended_regions(world)


class _Repairs(Provider):
    """RS2 repair projects (``--repair-projects``): one divisible proposal per
    ruler for next turn's work on its open projects (workshop repair wages
    and granary repair coins, one rounding), relieving the commons' granary
    wear and the patricians' crew work idle at a site shut for repair.
    ``repair_projects`` spends only within the ``repairs`` envelope and
    reports the turn's charge, which settles it."""

    services = ("repairs",)
    group = "repairs"

    def active(self, world):
        if getattr(getattr(world, "livelihoods", None), "repair_projects", None) is None:
            return False
        from chronicler.repair_projects import repair_projects_active
        return repair_projects_active(world)

    def proposals(self, world, civ, obs):
        if not self.active(world):
            return []
        from chronicler.repair_projects import budget_proposal
        return budget_proposal(world, civ, obs)

    def settle(self, world, c, obs):
        from chronicler.repair_projects import budget_settlement
        return budget_settlement(world, c, obs)


RELIEF, GRANARY, WORKSHOP, TEACHING, WARDENS = _Relief(), _Granary(), _Workshop(), _Teaching(), _Wardens()
RELOCATION = _RelocationAssistance()
REPAIRS = _Repairs()


def _providers() -> list[Provider]:
    out = []
    for path in PROVIDERS:
        module, attr = path.split(":")
        out.append(getattr(import_module(module), attr))
    return out


# ---------------------------------------------------------------------------
# Constituencies and arbitration
# ---------------------------------------------------------------------------

def _influence(civ) -> dict[str, float]:
    from chronicler.agent_movements import _ally_faction
    from chronicler.agent_movements_state import COMMONS
    from chronicler.cities import _merchant_influence
    voice = _ally_faction(COMMONS, civ)
    return {"commons": round(float(civ.factions.influence.get(voice, 0.25)), 6),
            "patricians": round(float(_merchant_influence(civ)), 6)}


def _burdens(world, civ: int, obs) -> dict[str, float | None]:
    name = world.civilizations[civ].name
    regions = [rid for rid, r in enumerate(world.regions) if r.controller == name]
    hunger = [obs.hunger[r] for r in regions]
    commons = None if any(h is None for h in hunger) else math.fsum(hunger)
    if commons is not None and _reserves_on(world) and obs.economy is not None:
        granaries = world.grain_reserves.granaries
        for rid in regions:
            g = granaries[rid] if rid < len(granaries) else None
            if g is not None and g.owner == civ:
                commons += min(max(0.0, g.target - g.grain), _expected_short(world, rid, obs))
    storage = _storage(world)
    if commons is not None and storage is not None and storage.receipt_turn == obs.turn:
        from chronicler.grain_storage import EXTRA_SPOILAGE
        horizon = _parameters(world)["horizon"]
        receipts = {r.region: r for r in storage.receipts}
        for rid in regions:
            asset, receipt = storage.assets[rid], receipts.get(rid)
            if asset is None or receipt is None or asset.owner != civ:
                continue
            grain = world.grain_reserves.granaries[rid].grain
            requested = receipt.target_requested or 0.0
            commons += (horizon * EXTRA_SPOILAGE * (1.0 - asset.condition) * grain
                        + max(0.0, requested - asset.capacity * asset.condition))
    patricians = 0.0
    workshops = getattr(world.livelihoods, "workshops", None)
    if workshops is not None and workshops.frame_turn == obs.turn:
        for r in workshops.frame:
            if r.region in regions:
                patricians += max(0.0, r.work_available - r.allocated)
    return {"commons": None if commons is None else round(commons, 6), "patricians": round(patricians, 6)}


def _greedy(items: list[Proposal], budget: int, score, *, per_coin: bool = True
            ) -> tuple[list[tuple[Proposal, int]], dict[int, str]]:
    """Fund items in descending ``score`` per coin (or in the fixed service
    order); one award per claim; only divisible items may be funded partially.
    Returns awards and refusals."""
    if per_coin:
        ranked = sorted(((score(p), p) for p in items), key=lambda sp: (-sp[0] / sp[1].cost, _order(sp[1])))
    else:
        ranked = sorted(((score(p), p) for p in items), key=lambda sp: _order(sp[1]))
    remaining, held, awards, refused = budget, set(), [], {}
    for value, p in ranked:
        if value <= EPS:
            refused[p.pid] = "no_support"
            continue
        if any(claim in held for claim in p.claims):
            refused[p.pid] = "incompatible"
            continue
        amount = p.cost if p.cost <= remaining else (remaining if p.divisible else 0)
        if amount < 1:
            refused[p.pid] = "budget"
            continue
        awards.append((p, amount))
        remaining -= amount
        held.update(p.claims)
    return awards, refused


def _bounded(items: list[Proposal]) -> list[Proposal]:
    """Keep ``MAX_PROPOSALS``: each constituency's best items per coin in turn
    (its own unit only, never compared across units), then the rest in the
    fixed service order."""
    rank = {}
    for ci, c in enumerate(CONSTITUENCIES):
        mine = sorted((p for p in items if p.relief.get(c, 0.0) > EPS),
                      key=lambda p, c=c: (-p.relief[c] / p.cost, _order(p)))
        for r, p in enumerate(mine):
            rank[id(p)] = min(rank.get(id(p), (math.inf, 0)), (r, ci))
    ordered = sorted(items, key=lambda p: (*rank.get(id(p), (math.inf, len(CONSTITUENCIES))), _order(p)))
    return ordered[:MAX_PROPOSALS]


def _order(p: Proposal):
    service = SERVICES.index(p.service) if p.service in SERVICES else len(SERVICES)
    return (service, p.service, p.recipients[0] if p.recipients else -1, p.pid)


def _relieved(awards, constituency: str) -> float:
    return math.fsum(p.relief.get(constituency, 0.0) * amount / p.cost for p, amount in awards)


def _bargain(decision: Decision, items: list[Proposal]) -> tuple[list[tuple[Proposal, int]], dict[int, str], dict]:
    budget, influence = decision.budget, decision.influence
    bundles, refusals = {}, {}
    for c in CONSTITUENCIES:
        bundles[c], refusals[c] = _greedy(items, budget, lambda p, c=c: p.relief.get(c, 0.0))
    best = {c: _relieved(bundles[c], c) for c in CONSTITUENCIES}

    def weighted(p):
        return math.fsum(influence[c] * p.relief.get(c, 0.0) / best[c] for c in CONSTITUENCIES if best[c] > EPS)

    bundles["compromise"], refusals["compromise"] = _greedy(items, budget, weighted)
    satisfaction, scores = {}, {}
    for name in CANDIDATES:
        satisfaction[name] = {c: (round(_relieved(bundles[name], c) / best[c], 6) if best[c] > EPS else 1.0)
                              for c in CONSTITUENCIES}
        scores[name] = round(math.fsum(influence[c] * satisfaction[name][c] for c in CONSTITUENCIES), 9)
    chosen = max(CANDIDATES, key=lambda name: (scores[name], -CANDIDATES.index(name)))
    decision.candidates = {name: [[p.pid, amount] for p, amount in bundles[name]] for name in CANDIDATES}
    decision.satisfaction, decision.scores, decision.chosen = satisfaction, scores, chosen
    decision.outcome = _classify(decision)
    sponsors = {}
    for p, _ in bundles[chosen]:
        shares = [(influence[c] * p.relief.get(c, 0.0) / best[c] if best[c] > EPS else 0.0, -i, c)
                  for i, c in enumerate(CONSTITUENCIES)]
        top = max(shares)
        sponsors[p.pid] = top[2] if top[0] > EPS else None
    refused = dict(refusals[chosen])
    for p in items:
        if refused.get(p.pid) == "no_support" and any(v > EPS for v in p.relief.values()):
            refused[p.pid] = "budget"           # wanted, but no constituency could afford it
    awarded = {p.pid for p, _ in bundles[chosen]}
    for p in items:
        if p.pid not in awarded and p.pid not in refused:
            refused[p.pid] = "not_chosen"
    return bundles[chosen], refused, sponsors


def _classify(decision: Decision) -> str:
    """``none`` (nothing fundable), ``uncontested`` (the adopted allocation
    fully satisfies every constituency: the budget did not force a choice),
    ``<constituency>_first`` (it fully satisfies only that constituency) or
    ``compromise`` (it fully satisfies none)."""
    if not any(decision.candidates[name] for name in CANDIDATES):
        return "none"
    sat = decision.satisfaction[decision.chosen]
    full = [c for c in CONSTITUENCIES if sat[c] >= 1.0 - 1e-6]
    if len(full) == len(CONSTITUENCIES):
        return "uncontested"
    return f"{full[0]}_first" if len(full) == 1 else "compromise"


def _fixed_shares(decision: Decision, items: list[Proposal], groups: dict[str, str], scale: float = 1.0):
    awards, refused = [], {}
    for group in sorted({groups[p.service] for p in items}, key=lambda g: (list(FIXED_SHARES).index(g)
                                                                           if g in FIXED_SHARES else len(FIXED_SHARES), g)):
        weight = FIXED_SHARES.get(group, 0.0)
        share = int(math.floor((weight if scale == 1.0 else weight / scale) * decision.budget + EPS))
        members = sorted((p for p in items if groups[p.service] == group), key=_order)
        got, why = _greedy(members, share, lambda p: 1.0, per_coin=False)
        awards.extend(got)
        refused.update({pid: ("share" if r == "budget" else r) for pid, r in why.items()})
    decision.chosen = "fixed_shares"
    decision.outcome = "fixed_shares" if awards else "none"
    return awards, refused, {p.pid: None for p, _ in awards}


# ---------------------------------------------------------------------------
# Phase hooks
# ---------------------------------------------------------------------------

def prepare_phase2(world, region_input, agent_bridge, snapshot, acc):
    """Record what the pending storage plan requests against each envelope."""
    state = _state(world)
    storage = _storage(world)
    plan = getattr(storage, "_active_plan", None) if storage is not None else None
    granary = [c for c in state.open if c.service in ("granary_maintain", "granary_expand")
               and c.for_turn == world.turn]
    if not granary or plan is None or plan.status != "pending":
        return region_input
    from chronicler.grain_storage import COINS_PER_WORK
    from chronicler.mutual_aid import _treasury_budget
    budgets = [max(0, math.floor(_treasury_budget(world, civ, acc))) for civ in world.civilizations]
    before = {}
    for row in plan.rows:
        if row.owner >= 0:
            before[row.region] = budgets[row.owner]
            budgets[row.owner] -= math.ceil(row.request * COINS_PER_WORK)
    for c in granary:
        rid = c.recipients[0]
        state._trace[("granary", c.cid)] = {"turn": world.turn, "request": plan.rows[rid].request,
                                           "owner": plan.rows[rid].owner, "budget": before.get(rid, 0)}
    return region_input


def rollback_phase2(world) -> None:
    state = _state(world)
    if state is not None:
        state._trace = {k: v for k, v in state._trace.items() if k[0] == "relief"}


def _venue(world, civ: int, c: Commitment, seat: int | None) -> int | None:
    from chronicler.cities_state import cities_on
    if not cities_on(world):
        return None
    if c.site is not None:
        workshops = getattr(world.livelihoods, "workshops", None)
        for s in getattr(workshops, "sites", []):
            if s.site == c.site:
                return s.settlement_id
    if len(c.recipients) == 1:
        own = [city for city in world.cities.cities if city.lord == civ and city.region == c.recipients[0]]
        if own:
            return max(own, key=lambda city: (city.size, -city.settlement_id)).settlement_id
    return seat


def _seat(world, civ: int) -> int | None:
    from chronicler.cities_state import cities_on
    if not cities_on(world):
        return None
    own = [city for city in world.cities.cities if city.lord == civ]
    capital = world.civilizations[civ].capital_region
    pool = [city for city in own if world.regions[city.region].name == capital] or own
    return max(pool, key=lambda city: (city.size, -city.settlement_id)).settlement_id if pool else None


def _settle(world, state: LocalBudgetState, obs, providers) -> list:
    by_service = {s: p for p in providers for s in p.services}
    params = _parameters(world)
    settled, keep_open = [], []
    for c in state.open:
        if c.for_turn > world.turn:
            keep_open.append(c)
            continue
        if c.for_turn < world.turn:
            result = {"outcome": "lapsed", "reason": "service_off", "spent": 0, "delivered": 0.0, "ratio": 0.0}
        else:
            provider = by_service.get(c.service)
            result = provider.settle(world, c, obs) if provider is not None else {
                "outcome": "deferred", "reason": "service_off", "spent": 0, "delivered": 0.0, "ratio": 0.0}
        c.outcome, c.reason = result["outcome"], result.get("reason")
        if c.reason is not None and c.reason not in REASONS:
            raise ValueError(f"unknown deferral reason {c.reason!r}")
        c.spent, c.delivered = int(result.get("spent", 0)), round(float(result.get("delivered", 0.0)), 6)
        c.ratio = round(float(result.get("ratio", 0.0)), 6)
        c.detail = {**c.detail, **result.get("detail", {})}
        c.settled_turn = world.turn
        if c.spent > c.amount:
            raise RuntimeError(f"{c.service} spent {c.spent} beyond its envelope of {c.amount}")
        _bump(state, c.outcome)
        _bump(state, "spent_coins", c.spent)
        if c.reason is not None:
            _bump(state, f"deferred_{c.reason}")
        settled.append(c)
    state.open = keep_open
    responses = []
    if state.mode == "bargained":
        responses = _respond(world, state, settled, params)
    state.settled = settled[-MAX_SETTLED:]
    state.settled_turn = world.turn
    state.responses = responses
    return _deferral_events(world, settled)


def _respond(world, state, settled, params) -> list[Response]:
    """Grievance at each venue city follows observed delivery (capped)."""
    from chronicler.cities import _q
    from chronicler.cities_state import cities_on
    if not cities_on(world):
        return []
    raw: dict[tuple[int, int], float] = {}
    for c in settled:
        if c.sponsor is None or c.venue is None or c.outcome == "lapsed":
            continue
        if c.outcome == "kept":
            c.response = -params["kept_grievance"]
        else:
            c.response = params["broken_grievance"] * (1.0 - (c.ratio or 0.0))
        c.response = round(c.response, 6)
        key = (c.civ, c.venue)
        raw[key] = raw.get(key, 0.0) + c.response
    cities = {city.settlement_id: city for city in world.cities.cities}
    out = []
    cap = params["response_cap"]
    for (civ, sid), value in sorted(raw.items()):
        city = cities.get(sid)
        if city is None or city.lord != civ:
            _bump(state, "responses_lost")
            continue
        applied = max(-cap, min(cap, value))
        before = city.grievance
        city.grievance = _q(min(1.0, max(0.0, before + applied)))
        out.append(Response(turn=world.turn, civ=civ, settlement_id=sid, before=before,
                            raw=round(value, 6), applied=round(city.grievance - before, 6), after=city.grievance))
        _bump(state, "responses")
        _bump(state, "grievance_raised" if city.grievance > before else "grievance_eased" if city.grievance < before
              else "grievance_unchanged")
    return out


def _deferral_events(world, settled) -> list:
    from chronicler.models import Event
    events = []
    for civ in sorted({c.civ for c in settled if c.outcome == "deferred"}):
        rows = [c for c in settled if c.civ == civ and c.outcome == "deferred"]
        what = "; ".join(f"{c.service.replace('_', ' ')} ({c.reason.replace('_', ' ')})" for c in rows[:4])
        more = f" and {len(rows) - 4} more" if len(rows) > 4 else ""
        name = world.civilizations[civ].name
        events.append(Event(turn=world.turn, event_type="budget_deferral", actors=[name], importance=2,
                            description=f"{name} defers promised spending decided in turn "
                                        f"{rows[0].decided_turn}: {what}{more}."))
    return events


def _decide(world, state: LocalBudgetState, obs, providers, acc) -> None:
    from chronicler.finance import _projections
    params = _parameters(world)
    projected = _projections(world, acc)
    groups = {s: p.group for p in providers for s in p.services}
    scale = 1.0 + math.fsum(FIXED_SHARES.get(p.group, 0.0) for p in providers
                            if p.services and p.group not in _BUILT_IN_GROUPS and p.active(world))
    decisions, new = [], {id(p): [] for p in providers}
    owner = {s: p for p in providers for s in p.services}
    for ci, civ in enumerate(world.civilizations):
        if not civ.regions:
            continue
        _bump(state, "decision_civ_turns")
        reserved: dict[str, int] = {}
        for p in providers:
            amount = int(p.obligations(world, ci, obs))
            if amount:
                key = p.group or type(p).__name__
                reserved[key] = reserved.get(key, 0) + amount
        obligations = sum(reserved.values())
        committed = sum(c.amount for c in state.open if c.civ == ci)
        disposable = max(0, int(projected[ci]) - int(params["floor"]) - obligations - committed)
        budget = int(math.floor(params["envelope_share"] * disposable + EPS))
        raw = []
        if obs.economy is not None:
            for p in providers:
                raw.extend(p.proposals(world, ci, obs))
        for row in raw:
            if row["service"] not in owner or row["cost"] < 1:
                raise ValueError(f"invalid budget proposal {row!r}")
        items = _bounded([Proposal(pid=0, civ=ci, source_turn=obs.turn, **row) for row in raw])
        dropped = len(raw) - len(items)
        for pid, p in enumerate(sorted(items, key=_order)):
            p.pid = pid
        items.sort(key=lambda p: p.pid)
        decision = Decision(turn=obs.turn, civ=ci, mode=state.mode, seat=_seat(world, ci),
                            projected=int(projected[ci]), floor=int(params["floor"]), obligations=obligations,
                            reserved=reserved, committed=committed, budget=budget, influence=_influence(civ),
                            burdens=_burdens(world, ci, obs), proposals=items, dropped=dropped)
        _bump(state, "proposals", len(items))
        _bump(state, "proposals_dropped", dropped)
        if budget >= 1:
            _bump(state, "budget_civ_turns")
        if items:
            _bump(state, "proposal_civ_turns")
        if state.mode == "bargained":
            awards, refused, sponsors = _bargain(decision, items)
        else:
            awards, refused, sponsors = _fixed_shares(decision, items, groups, scale)
        if sum(amount for _, amount in awards) > budget:
            raise RuntimeError("local budget awards exceed the committed budget")
        claims = [claim for p, _ in awards for claim in p.claims]
        if len(claims) != len(set(claims)):
            raise RuntimeError("incompatible promises in one allocation")
        decision.awards = [Award(pid=p.pid, amount=amount, sponsor=sponsors.get(p.pid)) for p, amount in awards]
        decision.refused = sorted(refused.items())
        _bump(state, f"outcome_{decision.outcome}")
        for p, amount in sorted(awards, key=lambda pa: pa[0].pid):
            c = Commitment(cid=state.next_cid, civ=ci, service=p.service, pid=p.pid, decided_turn=obs.turn,
                           for_turn=obs.turn + 1, recipients=list(p.recipients), site=p.site,
                           claims=list(p.claims), amount=amount, unit=p.unit,
                           expected=round(p.expected * amount / p.cost, 6), sponsor=sponsors.get(p.pid),
                           detail={"cost": p.cost})
            c.venue = _venue(world, ci, c, decision.seat)
            state.next_cid += 1
            state.open.append(c)
            new[id(owner[p.service])].append(c)
            _bump(state, "awards")
            _bump(state, "envelope_coins", amount)
        decisions.append(decision)
    for p in providers:
        p.install(world, new[id(p)])
    state.decisions = decisions
    state.decision_turn = obs.turn


def phase10(world, acc=None, economy_result=None, agent_bridge=None) -> list:
    """Settle the envelopes executed this turn, then decide the next turn's."""
    state = _state(world)
    providers = _providers()
    obs = _Obs(world, economy_result, agent_bridge)
    obs.trace = {k: v for k, v in state._trace.items() if v.get("turn") == world.turn}
    events = _settle(world, state, obs, providers)
    _decide(world, state, obs, providers, acc)
    state._trace = {}
    if economy_result is None:
        _bump(state, "no_economy_turns")
    return events


def snapshot_summary(world) -> dict:
    state = _state(world)
    source = world.turn - 1
    return {
        "schema_version": 1, "stage": "L9", "mode": state.mode, "source_turn": source,
        # None: no decision/settlement for this turn (unknown, not zero).
        "decisions": [d.model_dump() for d in state.decisions] if state.decision_turn == source else None,
        "settled": [c.model_dump() for c in state.settled] if state.settled_turn == source else None,
        "responses": [r.model_dump() for r in state.responses] if state.settled_turn == source else None,
        "open": [c.model_dump() for c in state.open],
        "counters": dict(state.counters),
        "parameters": {**_parameters(world), "kept_ratio": KEPT_RATIO, "max_proposals": MAX_PROPOSALS,
                       # RS2's group is listed only while its provider runs
                       # (feature-off snapshots are unchanged).
                       "fixed_shares": {k: v for k, v in FIXED_SHARES.items()
                                        if k != "repairs" or REPAIRS.active(world)}},
    }
