"""Public granaries: stock-target grain procurement and reserves
(``--grain-reserves``, default off).

Off by default behind ``WorldState.grain_reserves`` (CLI ``--grain-reserves``
/ ``--no-grain-reserves``, persisted on the world so a resumed run keeps its
setting). With the switch off nothing in this module runs and every output
is identical to the simulation without it. Granaries move goods-economy
stocks, so they need an agent mode; under ``--agents off`` a saved setting is
dormant (a strict no-op). See ``docs/integration/grain-reserves.md``.

Who keeps them
    The ruler of a region keeps its granary (``GrainReserveState.granaries``,
    one per region, index-aligned with ``world.regions``). Nothing else in
    the simulation holds food on purpose: a region's market stock is what is
    left after its people eat, merchants ship it where it is dearest now, and
    mutual aid and allied relief convoys answer hunger already reported.

Target (Phase 10)
    Turns of the region's food demand in proportion to the observed swing of
    its own harvest: ``target = min(MAX_TURNS, TURNS_PER_CV x cv) x demand``,
    where ``cv`` is the coefficient of variation of the region's food harvest
    over its food demand, the harvest counted up to the need
    (``HARVEST_CAP``: grain beyond it feeds no shortfall), in exponential
    means over about a year (``HARVEST_EMA``). A region whose harvest always
    covers its people, or never varies, keeps no reserve: a steady shortfall
    is trade's to cover, not a granary's.

Procurement (Phase 10, after the merchants planned their trips)
    Real surplus only: a market sells grain it holds beyond its merchants'
    commitments (loading and departing cargo) and beyond ``KEEP_TURNS`` turns
    of its own food demand, at its own market price (the economy's food
    demand over its post-trade supply), paid in whole treasury units. A ruler
    spends at most ``BUDGET_SHARE`` of its treasury above ``TREASURY_FLOOR``
    in a turn. It buys first in its own realm (the granary's own market, then
    its other regions within ``MAX_HOPS`` steps of the merchant route graph
    through its own land), then, once every ruler has bought at home, from
    foreign markets one step beyond. The route graph carries the merchants'
    permissions: no edge across a war, an embargo, a hostile disposition, a
    suspended route, a blockaded sea lane or a besieged city. Grain that
    leaves another market loses ``TRANSIT_DECAY["grain"]`` on the way, as a
    merchant's cargo does. Grain bought in the realm is paid to its own
    producers (it leaves the treasury); grain bought abroad is paid to the
    seller's ruler (``finance.transfer``). Granaries emptiest against their
    target buy first.

Release (Phase 2, right after the goods economy)
    When the economy finds food on hand below the people's need (food
    sufficiency below 1, dearth or famine), a granary holding at least
    ``RESERVE_FOR_FAMINE`` of its target covers the rest of the need; one
    holding less lifts the people only to the famine line (sufficiency 0.6,
    ``ecology.FAMINE_SEVERE_SUFFICIENCY``) and keeps the rest for worse. This
    happens before the agents' mortality, fertility and the famine labels
    read the sufficiency. Released grain is eaten that turn. The release does
    not pass through the market: prices and incomes the economy computed
    stay; the food sufficiency the agents, the famine labels, mutual aid and
    merchants read is raised.

Storage
    A granary loses ``STORAGE_DECAY["grain"]`` of its grain a turn, as the
    market's grain does without salt. A conquest destroys the share of the
    region's stocks a conquest destroys (``CONQUEST_STOCKPILE_SURVIVAL``),
    an occupying or besieging army takes its requisition share, a new ruler
    takes over the rest, and a region left without a ruler gets the grain in
    its market.

Conservation: no grain or money is created. Grain moves between markets and
granaries with recorded transit and storage losses and is eaten when
released; money moves from the buyer's treasury to the seller's ruler or to
the realm's own producers. ``CHRONICLER_CHECK_RESOURCES=1`` checks every
balance each turn (:class:`ReserveLedger`); with the validation sidecar the
ledger is written as ``validation_reserve_ledger.arrow``.

Identity: region = index in ``world.regions``, civ = index in
``world.civilizations``. No random draws. Treasury changes are ``keep``.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from chronicler.grain_reserves_state import (
    ABANDONED, BOUGHT, CAPTURED, COUNTER_KEYS, FLOW_KINDS, RELEASED, SEIZED, SPOILED, GrainReserveState, Granary,
    ReserveFlow, grain_reserves_on,
)

if TYPE_CHECKING:  # pragma: no cover
    from chronicler.economy import EconomyResult
    from chronicler.models import Event, WorldState


# ---------------------------------------------------------------------------
# Parameters ([CALIBRATE]; documented in docs/integration/grain-reserves.md)
# ---------------------------------------------------------------------------

#: Default for worlds created by the CLI/batch/live entry points
#: (``--grain-reserves`` opts in; loaded worlds keep their saved setting).
DEFAULT_ENABLED_FOR_NEW_WORLDS = False

TURNS_PER_CV = 6.0         # turns of the region's food demand a granary holds per unit of its harvest's CV ...
MAX_TURNS = 4.0            # ... at most this many turns
HARVEST_CAP = 1.0          # the harvest is counted up to this share of the need (surplus feeds no shortfall)
RESERVE_FOR_FAMINE = 0.5   # below this share of its target a granary lifts the people only to the famine line
HARVEST_EMA = 1.0 / 12.0   # weight of a turn in the harvest means (about a year)
KEEP_TURNS = 4.0           # a market sells only grain beyond this many turns of its own demand
MAX_HOPS = 3               # realm regions within this many steps of the route graph
BUDGET_SHARE = 0.10        # share of the treasury above the floor spent in a turn
TREASURY_FLOOR = 20        # a ruler with less buys nothing
RELEASE_TO = 1.0           # a release covers the need up to this food sufficiency
EVENT_SHARE = 0.1          # an opening is an event once a turn's release feeds this share of the need
PRICE_SUPPLY_FLOOR = 0.1   # the economy's SUPPLY_FLOOR in its food price
EPS = 1e-9
DUST = 1e-6                # grain below this spoils at once (no endless crumbs)
GRAIN = "grain"

#: Event types (each with a readable line; see ``docs/integration/grain-reserves.md``).
EVENT_TYPES: tuple[str, ...] = ("granary_opened", "granary_exhausted", "grain_bought")


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

def grain_reserves_enabled(world) -> bool:
    """True only for a real granary state (mocks and ``None`` read as off)."""
    return grain_reserves_on(world)


def set_grain_reserves_enabled(world: "WorldState", enabled: bool) -> None:
    """Switch granaries on (a fresh state, or the saved one kept) or off."""
    if enabled:
        if not grain_reserves_on(world):
            world.grain_reserves = GrainReserveState()
    else:
        world.grain_reserves = None


def grain_reserves_active(world) -> bool:
    """Switched on and running on an agent-backed goods economy."""
    return grain_reserves_on(world) and world.agent_mode not in (None, "off")


def snapshot_summary(world: "WorldState") -> dict:
    """Read the completed turn's stocks and flows without changing simulation state.

    A snapshot at T is taken after simulation turn T-1. Never repeat an old
    flow list when a turn made no movements, and never initialise missing
    granaries or infer their owner from the current territorial controller.
    Ownership is the granary's recorded keeper (settled in Phase 2).
    """
    if not grain_reserves_active(world):
        return {}
    state = world.grain_reserves
    source_turn = world.turn - 1

    def owner_name(index: int) -> str | None:
        return world.civilizations[index].name if 0 <= index < len(world.civilizations) else None

    return {
        "source_turn": source_turn,
        "granaries": [
            {"region": rid, "region_name": region.name, "owner": granary.owner,
             "owner_name": owner_name(granary.owner), "controller": region.controller,
             "grain": granary.grain, "target": granary.target, "observed": granary.observed}
            for rid, (region, granary) in enumerate(zip(world.regions, state.granaries))
        ],
        "flows": [
            {**flow.model_dump(), "kind": FLOW_KINDS[flow.kind],
             "buyer_name": owner_name(flow.buyer), "seller_name": owner_name(flow.seller)}
            for flow in state.flows if state.flows_turn == source_turn
        ],
        "counters": dict(state.counters),
    }


def _spoilage() -> float:
    from chronicler.economy import STORAGE_DECAY
    return STORAGE_DECAY[GRAIN]


def _transit_loss() -> float:
    from chronicler.economy import TRANSIT_DECAY
    return TRANSIT_DECAY[GRAIN]


def _ensure(world: "WorldState") -> GrainReserveState:
    state = world.grain_reserves
    while len(state.granaries) < len(world.regions):
        state.granaries.append(Granary())
    for key in COUNTER_KEYS:
        state.counters.setdefault(key, 0.0)
    return state


def _civ_index(world) -> dict[str, int]:
    """Civ name -> index, built here (the world's lookup caches are left alone)."""
    return {c.name: i for i, c in enumerate(world.civilizations)}


def _flows(world: "WorldState", state: GrainReserveState) -> list[ReserveFlow]:
    """This turn's flow list (a new one at the first movement of a turn)."""
    if state.flows_turn != world.turn:
        state.flows = []
        state.flows_turn = world.turn
    return state.flows


def _bump(state: GrainReserveState, key: str, value: float) -> None:
    state.counters[key] = state.counters.get(key, 0.0) + value


def _demand(economy_result, name: str) -> float:
    demand = economy_result.market_demand.get(name)
    return float(demand[0]) if demand else 0.0


def _food_price(economy_result, name: str) -> float:
    """The economy's post-trade food price: demand over supply (0 without demand)."""
    demand = economy_result.market_demand.get(name)
    supply = economy_result.market_supply.get(name)
    if not demand or not supply or demand[0] <= 0:
        return 0.0
    return float(demand[0]) / max(float(supply[0]), PRICE_SUPPLY_FLOOR)


# ---------------------------------------------------------------------------
# Phase 2: owners, release, spoilage
# ---------------------------------------------------------------------------

def open_granaries(world: "WorldState", economy_result: "EconomyResult | None",
                   agent_bridge=None) -> list["Event"]:
    """Right after the goods economy: settle owners, release grain where food
    on hand falls short of need (raising ``economy_result``'s food
    sufficiency and post-trade food supply), then spoil. Returns events."""
    if not grain_reserves_active(world):
        return []
    from chronicler.harvest_forecasts_state import harvest_forecasts_on
    if harvest_forecasts_on(world):
        from chronicler.harvest_forecasts import clear_stale_preparedness
        clear_stale_preparedness(world)
    from chronicler.ecology import FAMINE_SEVERE_SUFFICIENCY, FAMINE_SEVERE_TURNS
    from chronicler.models import Event
    from chronicler import provenance as prov

    state = _ensure(world)
    ledger = ReserveLedger.begin(world, state, agent_bridge)
    flows = _flows(world, state)
    civs = world.civilizations
    index = _civ_index(world)
    events: list[Event] = []

    # Owners: a granary belongs to the region's ruler.
    for rid, (region, granary) in enumerate(zip(world.regions, state.granaries)):
        ruler = index.get(region.controller) if region.controller is not None else None
        if ruler is None:
            if granary.grain > 0:
                if ledger is not None:
                    ledger.market_before(rid, region)
                goods = region.stockpile.goods
                goods[GRAIN] = goods.get(GRAIN, 0.0) + granary.grain
                flows.append(ReserveFlow(kind=ABANDONED, region=rid, amount=granary.grain,
                                         buyer=granary.owner))
                _bump(state, "abandoned", granary.grain)
                granary.grain = 0.0
            granary.owner = -1
            granary.releasing = granary.announced = granary.emptied = False
            continue
        if granary.owner != ruler:
            if granary.grain > 0:
                flows.append(ReserveFlow(kind=CAPTURED, region=rid, amount=granary.grain,
                                         buyer=ruler, seller=granary.owner))
                _bump(state, "captured", granary.grain)
            granary.owner = ruler
            granary.releasing = granary.announced = granary.emptied = False

    # Release: cover the shortfall of food on hand before the people eat it.
    if economy_result is not None:
        for rid, (region, granary) in enumerate(zip(world.regions, state.granaries)):
            name = region.name
            sufficiency = economy_result.food_sufficiency.get(name)
            demand = _demand(economy_result, name)
            if (granary.owner < 0 or granary.grain <= EPS or sufficiency is None or demand <= 0
                    or region.population <= 0 or sufficiency >= 1.0 - 1e-6):
                granary.releasing = granary.announced = granary.emptied = False
                continue
            # Well stocked, it covers the whole shortfall; low, it keeps the
            # people above the famine line and saves the rest for worse.
            full = granary.target <= EPS or granary.grain >= RESERVE_FOR_FAMINE * granary.target
            level = RELEASE_TO if full else FAMINE_SEVERE_SUFFICIENCY
            if sufficiency >= level - 1e-6:
                granary.releasing = granary.announced = granary.emptied = False
                continue
            gap = (level - sufficiency) * demand
            released = min(granary.grain, gap)
            granary.grain -= released
            covered = released >= gap - EPS
            after = level if covered else sufficiency + released / demand
            economy_result.food_sufficiency[name] = after
            supply = economy_result.market_supply.get(name)
            if supply:
                economy_result.market_supply[name] = (supply[0] + released,) + tuple(supply[1:])
            flows.append(ReserveFlow(kind=RELEASED, region=rid, amount=released, buyer=granary.owner,
                                     before=sufficiency, after=after))
            _bump(state, "released", released)
            severe = sufficiency < FAMINE_SEVERE_SUFFICIENCY
            if severe:
                _bump(state, "released_severe", released)
            owner = civs[granary.owner].name
            # The labels' rule: a famine is a severe shortage in its third turn.
            famine = severe and (region.food_severe_turns or 0) + 1 >= FAMINE_SEVERE_TURNS
            causes = [c for c in (prov.open_episode(world, "famine", name),
                                  prov.open_episode(world, "dearth", name)) if c]
            if not granary.releasing:
                _bump(state, "openings", 1)
            if not granary.announced and released >= EVENT_SHARE * demand:
                granary.announced = True
                events.append(Event(
                    turn=world.turn, event_type="granary_opened", actors=[owner], region=name,
                    importance=5 if severe else 4, causes=causes[:1],
                    description=(f"{owner} opens its granary in {name} against the "
                                 f"{'famine' if famine else 'dearth'}: {released:.1f} grain feeds the "
                                 f"hungry (food {sufficiency:.2f} -> {after:.2f} of need)."),
                ))
            if not covered and not granary.emptied:
                _bump(state, "exhausted", 1)
                granary.emptied = True
                if granary.announced:
                    events.append(Event(
                        turn=world.turn, event_type="granary_exhausted", actors=[owner], region=name,
                        importance=5 if severe else 4, causes=causes[:1],
                        description=(f"The granary of {owner} in {name} is empty: its last "
                                     f"{released:.1f} grain leaves the people at {after:.2f} of "
                                     f"their need."),
                    ))
            granary.releasing = True

    # Storage: grain spoils in the granary as it does in the market.
    rate = _spoilage()
    for rid, granary in enumerate(state.granaries):
        if granary.grain <= 0:
            granary.grain = 0.0
            continue
        loss = granary.grain * rate
        if granary.grain - loss < DUST:
            loss = granary.grain  # the last crumbs spoil
        granary.grain -= loss
        flows.append(ReserveFlow(kind=SPOILED, region=rid, amount=loss, buyer=granary.owner,
                                 before=granary.grain + loss))
        _bump(state, "spoiled", loss)
    if ledger is not None:
        ledger.after_open(world, state, economy_result)
    return events


# ---------------------------------------------------------------------------
# Conquest and occupation
# ---------------------------------------------------------------------------

def seize_granary(world: "WorldState", region, survival: float) -> float:
    """A conquest or an occupying army takes ``1 - survival`` of the region's
    granary (the share it takes of the region's stocks). Returns the grain
    taken; a no-op unless granaries are active."""
    if not grain_reserves_active(world):
        return 0.0
    state = _ensure(world)
    rid = next((i for i, r in enumerate(world.regions) if r is region), None)
    if rid is None:
        return 0.0
    granary = state.granaries[rid]
    if granary.grain <= 0:
        return 0.0
    taken = granary.grain * (1.0 - survival)
    granary.grain -= taken
    _flows(world, state).append(ReserveFlow(kind=SEIZED, region=rid, amount=taken, buyer=granary.owner))
    _bump(state, "seized", taken)
    return taken


# ---------------------------------------------------------------------------
# Phase 10: harvests, targets, procurement
# ---------------------------------------------------------------------------

def _harvest(world, economy_result, region) -> float:
    """Food the region grew this turn (its food slots' output and foraging)."""
    from chronicler.economy import FOOD_GOODS, map_resource_to_good
    out = economy_result.slot_output.get(region.name) or (0.0, 0.0, 0.0)
    total = economy_result.forage_output.get(region.name, 0.0)
    for slot, rtype in enumerate(region.resource_types):
        if map_resource_to_good(rtype) in FOOD_GOODS:
            total += out[slot]
    return float(total)


def _observe(world, state, economy_result) -> None:
    """Update each owned, populated region's harvest means and target."""
    for region, granary in zip(world.regions, state.granaries):
        demand = _demand(economy_result, region.name)
        if granary.owner < 0 or demand <= 0 or region.population <= 0:
            continue
        ratio = min(HARVEST_CAP, _harvest(world, economy_result, region) / demand)
        if granary.observed == 0:
            granary.harvest_mean = ratio
            granary.harvest_sq = ratio * ratio
        else:
            granary.harvest_mean += HARVEST_EMA * (ratio - granary.harvest_mean)
            granary.harvest_sq += HARVEST_EMA * (ratio * ratio - granary.harvest_sq)
        granary.observed += 1
        granary.target = target_grain(granary, demand)


def harvest_cv(granary: Granary) -> float:
    """Coefficient of variation of the region's harvest over its demand,
    counted up to the need (0 when it grows nothing: no harvest to swing)."""
    if granary.harvest_mean <= EPS:
        return 0.0
    var = max(0.0, granary.harvest_sq - granary.harvest_mean * granary.harvest_mean)
    return math.sqrt(var) / granary.harvest_mean


def target_grain(granary: Granary, demand: float) -> float:
    """``TURNS_PER_CV x cv`` turns of the region's food demand, at most ``MAX_TURNS``."""
    return min(MAX_TURNS, TURNS_PER_CV * harvest_cv(granary)) * demand


def _route_graph(world) -> dict[int, list[int]]:
    """Permitted shipment edges, as the merchants' route graph: destination ->
    sorted origins (war, embargo, disposition, suspended routes; blockaded
    sea lanes; besieged cities). Read-only."""
    from chronicler.columnar import pylist
    from chronicler.economy import build_merchant_route_graph
    batch = build_merchant_route_graph(world)
    if getattr(world, "maritime", None) is not None:
        from chronicler.maritime import filter_boundary_batch, maritime_enabled
        if maritime_enabled(world):
            batch = filter_boundary_batch(world, batch, "from_region", "to_region")
    from chronicler.agent_bridge import _city_route_graph
    batch = _city_route_graph(world, batch)
    into: dict[int, set[int]] = {}
    for a, b in zip(pylist(batch.column("from_region")), pylist(batch.column("to_region"))):
        into.setdefault(int(b), set()).add(int(a))
    return {dst: sorted(src) for dst, src in into.items()}


def _realm_hops(world, graph, target: int, owner_name: str) -> dict[int, int]:
    """Own regions from which grain can reach ``target`` through the realm,
    with the fewest steps (``MAX_HOPS`` at most)."""
    hops = {target: 0}
    frontier = [target]
    for step in range(1, MAX_HOPS + 1):
        nxt = []
        for dst in frontier:
            for src in graph.get(dst, ()):
                if src not in hops and world.regions[src].controller == owner_name:
                    hops[src] = step
                    nxt.append(src)
        frontier = sorted(nxt)
    return hops


def tick_grain_reserves(world: "WorldState", acc=None, economy_result: "EconomyResult | None" = None,
                        agent_bridge=None) -> list["Event"]:
    """Phase 10: observe harvests, set targets, buy toward them. Returns events."""
    if not grain_reserves_active(world):
        return []
    from chronicler.economy import FOOD_GOODS
    from chronicler.finance import _projections, transfer
    from chronicler.models import Event

    state = _ensure(world)
    ledger = ReserveLedger.current(world, state)
    events: list[Event] = []
    if economy_result is None:
        from chronicler.harvest_forecasts_state import harvest_forecasts_on
        if harvest_forecasts_on(world):
            from chronicler.harvest_forecasts import tick_harvest_forecasts
            events.extend(tick_harvest_forecasts(world, None))
        if ledger is not None:
            ledger.finish(world, state, agent_bridge)
        from chronicler.transaction_receipts_state import transaction_receipts_on
        if transaction_receipts_on(world):
            from chronicler.public_purchase_receipts import capture_public_purchases
            capture_public_purchases(world, economy_result=None)
        return events
    _observe(world, state, economy_result)
    # Default-off public assessments see only the production already measured
    # this turn. Rebuild their temporary target from the normal target above.
    from chronicler.harvest_forecasts_state import harvest_forecasts_on
    if harvest_forecasts_on(world):
        from chronicler.harvest_forecasts import apply_preparedness, tick_harvest_forecasts
        events.extend(tick_harvest_forecasts(world, economy_result))
        apply_preparedness(world, economy_result)

    civs = world.civilizations
    index = _civ_index(world)
    regions = world.regions
    commitments: dict[str, dict[str, float]] = {}
    if agent_bridge is not None and world.agent_mode == "hybrid":
        from chronicler.mutual_aid import read_stockpile_commitments
        commitments = read_stockpile_commitments(world, agent_bridge._sim)
    demand = [_demand(economy_result, r.name) for r in regions]
    price = [_food_price(economy_result, r.name) for r in regions]
    surplus = []
    for rid, region in enumerate(regions):
        if region.controller not in index or demand[rid] <= 0 or region.population <= 0:
            surplus.append(0.0)
            continue
        held = commitments.get(region.name, {})
        goods = region.stockpile.goods
        free = {g: max(0.0, goods.get(g, 0.0) - held.get(g, 0.0)) for g in sorted(FOOD_GOODS)}
        surplus.append(max(0.0, min(free[GRAIN], math.fsum(free.values()) - KEEP_TURNS * demand[rid])))
    if ledger is not None:
        ledger.before_buy(world, acc, surplus)
    projected = _projections(world, acc)
    budget = [int(BUDGET_SHARE * max(0, projected[i] - TREASURY_FLOOR)) if civs[i].regions else 0
              for i in range(len(civs))]
    loss = _transit_loss()
    flows = _flows(world, state)
    purchase_flow_start = len(flows)
    graph = _route_graph(world)
    foreign_bought: dict[int, list] = {}

    for foreign in (False, True):
        for ci, civ in enumerate(civs):
            if budget[ci] <= 0:
                continue
            targets = [rid for rid, (r, g) in enumerate(zip(regions, state.granaries))
                       if g.owner == ci and r.controller == civ.name and demand[rid] > 0
                       and g.target - g.grain > EPS]
            targets.sort(key=lambda rid: (state.granaries[rid].grain / state.granaries[rid].target,
                                          economy_result.food_sufficiency.get(regions[rid].name, 0.0), rid))
            for rid in targets:
                granary = state.granaries[rid]
                hops = _realm_hops(world, graph, rid, civ.name)
                if not foreign:
                    sources = sorted(hops, key=lambda s: (hops[s], price[s], s))
                    steps = hops
                else:
                    steps = {}
                    for own, h in hops.items():
                        if h >= MAX_HOPS:
                            continue
                        for src in graph.get(own, ()):
                            r = regions[src]
                            if r.controller is None or r.controller == civ.name or r.controller not in index:
                                continue
                            if src not in steps or h + 1 < steps[src]:
                                steps[src] = h + 1
                    sources = sorted(steps, key=lambda s: (price[s], steps[s], s))
                for src in sources:
                    if budget[ci] <= 0 or granary.target - granary.grain <= EPS:
                        break
                    p = price[src]
                    if surplus[src] <= EPS or p <= 0:
                        continue
                    keep = 1.0 if steps[src] == 0 else 1.0 - loss
                    want = (granary.target - granary.grain) / keep
                    cost = min(budget[ci], int(math.floor(min(surplus[src], want) * p + EPS)))
                    if cost < 1:
                        continue
                    sent = min(surplus[src], cost / p)
                    received = sent * keep
                    seller = index[regions[src].controller]
                    if seller == ci:
                        if acc is not None:
                            acc.add(ci, civ, "treasury", -cost, "keep")
                        else:
                            civ.treasury = max(0, civ.treasury - cost)
                        paid = cost
                    else:
                        paid = transfer(world, ci, seller, cost, acc=acc)
                        if paid != cost:
                            raise AssertionError(f"granary purchase of {cost} paid {paid}")
                    goods = regions[src].stockpile.goods
                    goods[GRAIN] = goods.get(GRAIN, 0.0) - sent
                    surplus[src] -= sent
                    budget[ci] -= cost
                    granary.grain += received
                    flows.append(ReserveFlow(kind=BOUGHT, region=rid, amount=received, source=src,
                                             seller=seller, buyer=ci, sent=sent, cost=cost))
                    kind = "bought_own" if src == rid else ("bought_realm" if seller == ci else "bought_foreign")
                    _bump(state, kind, received)
                    _bump(state, "sent", sent)
                    _bump(state, "transit_loss", sent - received)
                    _bump(state, "paid_own" if seller == ci else "paid_foreign", cost)
                    if seller != ci:
                        foreign_bought.setdefault(ci, []).append((seller, rid, received, cost))

    for ci in sorted(foreign_bought):
        rows = foreign_bought[ci]
        sellers = sorted({s for s, _, _, _ in rows})
        names = [civs[s].name for s in sellers]
        grain = math.fsum(r[2] for r in rows)
        cost = sum(r[3] for r in rows)
        main_region = max(rows, key=lambda r: (r[2], -r[1]))[1]
        events.append(Event(
            turn=world.turn, event_type="grain_bought", actors=[civs[ci].name], civs=names,
            region=regions[main_region].name, importance=2,
            description=(f"{civs[ci].name} buys {grain:.1f} grain for its granaries in the markets "
                         f"of {', '.join(names)} ({cost} treasury)."),
        ))
    if ledger is not None:
        ledger.after_buy(world, acc, state)
        ledger.finish(world, state, agent_bridge)
    if harvest_forecasts_on(world):
        from chronicler.harvest_forecasts import record_preparedness_purchases
        events.extend(record_preparedness_purchases(world))
    from chronicler.transaction_receipts_state import transaction_receipts_on
    if transaction_receipts_on(world):
        from chronicler.public_purchase_receipts import capture_public_purchases
        capture_public_purchases(world, economy_result=economy_result,
                                 opening_treasuries=projected, demand=demand, price=price,
                                 flow_start=purchase_flow_start)
    return events


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def extract_grain_reserve_metrics(bundles: list[dict]) -> dict:
    """Per run (bundles whose final ``world_state`` holds granaries): the
    cumulative counters and the grain held and targeted at the end, as means
    over the runs. Granary levels over time are in the validation sidecar's
    ``validation_reserve_ledger.arrow``."""
    runs = []
    for bundle in bundles:
        state = (bundle.get("world_state") or {}).get("grain_reserves")
        if not state:
            continue
        granaries = state.get("granaries", [])
        runs.append({
            "counters": state.get("counters", {}),
            "grain_final": sum(g.get("grain", 0.0) for g in granaries),
            "target_final": sum(g.get("target", 0.0) for g in granaries),
        })
    if not runs:
        return {"runs": 0}
    keys = sorted({k for r in runs for k in r["counters"]})
    return {
        "runs": len(runs),
        "grain_final_mean": sum(r["grain_final"] for r in runs) / len(runs),
        "target_final_mean": sum(r["target_final"] for r in runs) / len(runs),
        "counters_mean": {k: sum(r["counters"].get(k, 0.0) for r in runs) / len(runs) for k in keys},
    }


# ---------------------------------------------------------------------------
# Resource ledger (CHRONICLER_CHECK_RESOURCES=1, validation sidecar)
# ---------------------------------------------------------------------------

RESERVE_LEDGER_FILENAME = "validation_reserve_ledger.arrow"

#: Column name -> pyarrow type name, in file order: one row per granary that
#: held grain or moved any this turn.
RESERVE_LEDGER_COLUMNS: dict[str, str] = {
    "turn": "uint32",
    "region": "uint16",
    "owner": "int16",
    "grain_before": "float64",
    "bought": "float64",
    "released": "float64",
    "spoiled": "float64",
    "seized": "float64",
    "abandoned": "float64",
    "grain_after": "float64",
    "target": "float64",
    "sent_from_market": "float64",
    "paid": "int32",
    "sufficiency_before": "float32",
    "sufficiency_after": "float32",
}

_TOL = 1e-9


class ReserveLedger:
    """One turn's granary balances, from the Phase 2 tick to the end of the
    Phase 10 tick. Built only when ``CHRONICLER_CHECK_RESOURCES=1`` asks for
    its checks or the validation sidecar records it; it only reads.

    Checks (``AssertionError("resource ledger does not balance ...")``):

    * every granary: grain after = grain before + bought (received) -
      released - spoiled - seized - abandoned, never negative;
    * every market touched by the ticks: its grain changed by exactly the
      grain it sold (sent) and the grain abandoned to it;
    * shipments: received = sent x (1 - transit decay) from another region,
      = sent from the granary's own market; nothing sold beyond the
      market's free surplus;
    * releases: only below a full meal, never above the shortfall, and the
      economy's food sufficiency raised by exactly release / demand;
    * spoilage at the storage rate;
    * money: each buyer's treasury fell by its payments, each foreign
      seller's rose by its receipts (no treasury created).
    """

    def __init__(self, world, state, check: bool, record: bool) -> None:
        self.turn = world.turn
        self.check = check
        self.record = record
        self.start = [g.grain for g in state.granaries]
        self.market: dict[int, float] = {}
        self.market_after: dict[int, float] = {}
        self.problems: list[str] = []
        self.surplus: list[float] | None = None
        self.treasury: list[int] | None = None
        self.sufficiency: dict[int, tuple[float, float, float]] = {}

    @staticmethod
    def begin(world, state, agent_bridge=None) -> "ReserveLedger | None":
        from chronicler.production_ledger import resource_check_enabled
        sidecar = getattr(agent_bridge, "_sidecar", None) if agent_bridge is not None else None
        check = resource_check_enabled()
        if sidecar is None and not check:
            state._ledger = None
            return None
        ledger = ReserveLedger(world, state, check, sidecar is not None)
        # Snapshot every market before the Phase 2 tick (abandoned grain).
        for rid, region in enumerate(world.regions):
            ledger.market[rid] = region.stockpile.goods.get(GRAIN, 0.0)
        state._ledger = ledger
        return ledger

    @staticmethod
    def current(world, state) -> "ReserveLedger | None":
        ledger = state._ledger
        if ledger is not None and ledger.turn != world.turn:
            state._ledger = None
            return None
        return ledger

    def market_before(self, rid: int, region) -> None:
        self.market.setdefault(rid, region.stockpile.goods.get(GRAIN, 0.0))

    def after_open(self, world, state, economy_result) -> None:
        flows = [f for f in state.flows]
        abandoned: dict[int, float] = {}
        for f in flows:
            if f.kind == ABANDONED:
                abandoned[f.region] = abandoned.get(f.region, 0.0) + f.amount
            elif f.kind == RELEASED and economy_result is not None:
                name = world.regions[f.region].name
                demand = _demand(economy_result, name)
                gap = (RELEASE_TO - f.before) * demand
                if f.before >= 1.0 - 1e-6:
                    self.problems.append(f"region {f.region}: released at sufficiency {f.before}")
                if f.amount > gap + _TOL * max(1.0, demand) or f.amount < -_TOL:
                    self.problems.append(f"region {f.region}: released {f.amount} for a shortfall of {gap}")
                expect = f.before + f.amount / demand
                now = economy_result.food_sufficiency.get(name)
                if (now is None or abs(now - expect) > 1e-9 or abs(f.after - expect) > 1e-9
                        or f.after > RELEASE_TO + 1e-12):
                    self.problems.append(f"region {f.region}: sufficiency {f.before} + release "
                                         f"{f.amount} / {demand} recorded {f.after}, economy {now}")
                self.sufficiency[f.region] = (f.before, f.after, f.amount)
            elif f.kind == SPOILED:
                pass
        for rid, before in self.market.items():
            now = world.regions[rid].stockpile.goods.get(GRAIN, 0.0)
            if abs(now - before - abandoned.get(rid, 0.0)) > _TOL * max(1.0, abs(before)):
                self.problems.append(f"region {rid}: market grain {before} -> {now} in the Phase 2 tick, "
                                     f"abandoned {abandoned.get(rid, 0.0)}")
        self.market = {}

    def before_buy(self, world, acc, surplus) -> None:
        from chronicler.finance import _projections
        self.surplus = list(surplus)
        self.treasury = _projections(world, acc)
        self.market = {rid: r.stockpile.goods.get(GRAIN, 0.0) for rid, r in enumerate(world.regions)}

    def after_buy(self, world, acc, state) -> None:
        from chronicler.finance import _projections
        loss = _transit_loss()
        sold: dict[int, float] = {}
        paid: dict[int, int] = {}
        got: dict[int, int] = {}
        for f in state.flows:
            if f.kind != BOUGHT:
                continue
            sold[f.source] = sold.get(f.source, 0.0) + f.sent
            paid[f.buyer] = paid.get(f.buyer, 0) + f.cost
            if f.seller != f.buyer:
                got[f.seller] = got.get(f.seller, 0) + f.cost
            keep = 1.0 if f.source == f.region else 1.0 - loss
            if abs(f.amount - f.sent * keep) > _TOL * max(1.0, f.sent):
                self.problems.append(f"granary {f.region}: received {f.amount} of {f.sent} sent from {f.source}")
            if f.cost < 1 or f.sent <= 0:
                self.problems.append(f"granary {f.region}: a purchase of {f.sent} for {f.cost}")
        for rid, before in self.market.items():
            now = world.regions[rid].stockpile.goods.get(GRAIN, 0.0)
            if abs((before - now) - sold.get(rid, 0.0)) > _TOL * max(1.0, before):
                self.problems.append(f"region {rid}: market grain {before} -> {now}, sold {sold.get(rid, 0.0)}")
            if self.surplus is not None and sold.get(rid, 0.0) > self.surplus[rid] + _TOL * max(1.0, before):
                self.problems.append(f"region {rid}: sold {sold.get(rid, 0.0)} beyond its surplus {self.surplus[rid]}")
            if now < -_TOL:
                self.problems.append(f"region {rid}: market grain {now}")
        after = _projections(world, acc)
        for ci, before in enumerate(self.treasury or []):
            change = after[ci] - before
            expect = got.get(ci, 0) - paid.get(ci, 0)
            if change != expect:
                self.problems.append(f"civ {ci}: treasury {before} -> {after[ci]}, purchases expect {expect:+d}")
        self.market = {}

    def finish(self, world, state, agent_bridge=None) -> None:
        """Granary balances over the turn; rows to the sidecar; raise on a
        broken balance when checking."""
        rate = _spoilage()
        sums: dict[int, dict[str, float]] = {}
        for f in state.flows if state.flows_turn == self.turn else []:
            row = sums.setdefault(f.region, {"bought": 0.0, "released": 0.0, "spoiled": 0.0, "seized": 0.0,
                                             "abandoned": 0.0, "sent": 0.0, "paid": 0.0})
            if f.kind == BOUGHT:
                row["bought"] += f.amount
                row["paid"] += f.cost
                src = sums.setdefault(f.source, {"bought": 0.0, "released": 0.0, "spoiled": 0.0, "seized": 0.0,
                                                 "abandoned": 0.0, "sent": 0.0, "paid": 0.0})
                src["sent"] += f.sent
            elif f.kind == RELEASED:
                row["released"] += f.amount
            elif f.kind == SPOILED:
                row["spoiled"] += f.amount
                if (abs(f.before * rate - f.amount) > _TOL * max(1.0, f.before)
                        and not (f.amount == f.before and f.before * (1.0 - rate) < DUST)):
                    self.problems.append(f"granary {f.region}: spoiled {f.amount} of {f.before}")
            elif f.kind == SEIZED:
                row["seized"] += f.amount
            elif f.kind == ABANDONED:
                row["abandoned"] += f.amount
        columns: dict[str, list] = {name: [] for name in RESERVE_LEDGER_COLUMNS}
        for rid, granary in enumerate(state.granaries):
            before = self.start[rid] if rid < len(self.start) else 0.0
            row = sums.get(rid, {"bought": 0.0, "released": 0.0, "spoiled": 0.0, "seized": 0.0,
                                 "abandoned": 0.0, "sent": 0.0, "paid": 0.0})
            expect = before + row["bought"] - row["released"] - row["spoiled"] - row["seized"] - row["abandoned"]
            if abs(granary.grain - expect) > _TOL * max(1.0, before + row["bought"]):
                self.problems.append(f"granary {rid}: grain {before} -> {granary.grain}, flows give {expect}")
            if granary.grain < 0:
                self.problems.append(f"granary {rid}: grain {granary.grain}")
            if before <= 0 and granary.grain <= 0 and not any(row.values()):
                continue
            s0, s1, _ = self.sufficiency.get(rid, (float("nan"), float("nan"), 0.0))
            values = (self.turn, rid, granary.owner, before, row["bought"], row["released"], row["spoiled"],
                      row["seized"], row["abandoned"], granary.grain, granary.target, row["sent"],
                      int(row["paid"]), s0, s1)
            for name, value in zip(RESERVE_LEDGER_COLUMNS, values):
                columns[name].append(value)
        state._ledger = None
        if self.record:
            sidecar = getattr(agent_bridge, "_sidecar", None) if agent_bridge is not None else None
            if sidecar is not None:
                sidecar.add_reserve_ledger_rows(columns)
        if self.check and self.problems:
            raise AssertionError(
                f"resource ledger does not balance at turn {self.turn} (granaries): "
                + "; ".join(self.problems[:8])
                + (f" (+{len(self.problems) - 8} more)" if len(self.problems) > 8 else "")
            )


def write_reserve_ledger(path, columns: dict[str, list], *, artifact_budget=None) -> None:
    """Write the granary ledger's column lists as an Arrow IPC file."""
    import pyarrow as pa
    import pyarrow.ipc as ipc
    arrays = [pa.array(columns.get(name, []), type=getattr(pa, kind)())
              for name, kind in RESERVE_LEDGER_COLUMNS.items()]
    batch = pa.record_batch(arrays, names=list(RESERVE_LEDGER_COLUMNS))
    options = ipc.IpcWriteOptions(compression="zstd") if pa.Codec.is_available("zstd") else None
    if artifact_budget is None:
        with pa.OSFile(str(path), "wb") as handle:
            writer = ipc.new_file(handle, batch.schema, options=options)
            writer.write_batch(batch)
            writer.close()
    else:
        artifact_budget.require_healthy()
        with pa.BufferOutputStream() as handle:
            writer = ipc.new_file(handle, batch.schema, options=options)
            writer.write_batch(batch)
            writer.close()
            content = handle.getvalue().to_pybytes()
        artifact_budget.write_bytes(path, content)


def read_reserve_ledger(path) -> dict[str, list]:
    import pyarrow as pa
    import pyarrow.ipc as ipc
    with pa.memory_map(str(path), "r") as source:
        table = ipc.open_file(source).read_all()
    return {name: table.column(name).to_pylist() for name in table.column_names}
