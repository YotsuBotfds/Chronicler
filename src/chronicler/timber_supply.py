"""PL1 timber supply: named, paid woodcutting expeditions (``--timber-supply``, default off).

Requires ``--agents hybrid``, ``--repair-projects`` (RS2) and ``--timber-stock``
(L3, the ecological account). Modes (``--timber-supply-mode``): ``supply``
(default) and the cost-retaining control ``cost_only``.

Why. RS2 repair projects stall for want of timber, and the cause is
production, not placement (PL0 diagnosis D1): most stalled regions have no
timber slot, and where forest stands nobody works it for the repairs. An
expedition adds harvest where forest stands and carries it to the repairs;
its labour cost falls on the community that needs the timber, and the
harvest goes through the forest's own L3 account.

Need (Phase 10, after RS2 opened this turn's projects). For each region with
open RS2 projects of a controlling civilization: the timber those projects
could use in one turn at their per-turn caps (a granary's work cap times its
timber rate; a workshop crew's ``MAX_CREW`` diverted shares at its rate),
less the free timber RS2 sees (stockpile less merchant commitments, plus this
package's store) and the cargo of the region's live expeditions after the
way home. A gap of at least ``MIN_GAP`` without a live expedition for the
region launches one, or records why not (``REFUSALS``, first failing check):

* ``no_forest``: no timber slot in a region the civ controls or nobody
  controls (never another civ's) is reachable on the region graph;
* ``too_far``: none within ``MAX_HOPS`` hops;
* ``forest_depleted``: every one in range is below ``GUARD_SHARE`` of its L3
  capacity (the declared ecological guard);
* ``forest_busy``: every healthy one in range is already being cut by
  another expedition (one expedition per forest);
* ``no_crew``: nobody in the region is eligible;
* ``no_coins``: the controller's projected treasury cannot pay the whole
  expedition's wages and its other live expeditions' remaining wages.

B3's works (``--infrastructure-condition`` in ``repair`` or ``cost_only``)
are served after every RS2 need row of the turn, by the same planner
(``_plan_works``): per region with open works that can use timber next Phase
2 (``infrastructure_condition.timber_wants``: only works already opened, one
turn at their per-turn cap), the works' want against what the free timber and
the cargo on its way leave after RS2's want there; a region with a live
expedition gets no second one, and a gap of at least ``MIN_GAP`` launches one
under the same checks, crew rule, wages and work reservation (no other labour
authority), or records the refusal. The rows go to B3's record; this
package's need rows and their counters stay RS2's, and the works' launches
count in ``launched_works`` (``launched`` stays RS2's). The store is kept
only in regions whose works ask (the same screen). Off, and in B3's
``record_only``/``wear_only``, nothing here changes.

Who goes. At most ``CREW_CAP`` living adults resident in the home region,
of any occupation but Soldier, not on an army roster, not away on a merchant
trip and not on another crew; eligible RS3 veterans first
(``veteran_reintegration.priority_ids``), then ascending stable id. They stay
in the native pool at home: no agent moves. Each turn of the expedition, in
Phase 2 after every earlier work consumer, each member is reserved in the
shared work registry (category ``repair``, the whole turn); a member who
already holds work that turn, or who died, moved, enlisted or left on a
trip, leaves the crew (a dated drop). Only the home economy loses their
labour: the farmers' farm shares (1, or ``URBAN_FARM_LABOR[rank]`` for a
farmer living in a city) go out in the native ``woodcut_labor_away`` column,
and the economy removes at most the region's farm labour, before granary
work. Each member is paid ``repair_wage`` (purpose 3, batch
``WAGE_BATCH``) of ``round(SHARE x WAGE_PER_WORK)`` milli-units by stable id
from the controller's treasury, and the same share of ordinary income is
withheld by the next wealth phase (``extend_paid_work``): the wage replaces
that income instead of adding to it. The treasury pays whole units once per
civ and turn, the sub-unit remainder prepaid (as RS2).

Where and how long. The forest is the chosen region's first timber slot (a
region with several timber slots is worked on its lowest-index one: the
native kernel's rule, and no development world has a second). The crew
walks one hop a turn (``outbound``), cuts for ``CUT_TURNS`` turns
(``cutting``) and walks home (``returning``); a forest in the home region
has no travel. While cutting in ``supply`` mode its headcount goes to the
forest's timber slot in the native ``woodcut_labor`` column: on the slot's
own labour curve, the crew's output is the marginal harvest (the slot's
total with the crew, under any L3 or L8 cap, less the residents' output),
reported as ``woodcut_output``. It counts in the slot's output, so the L3
extraction account debits it, but it never enters the forest region's
stockpile (the native conservation summary carries it as
``woodcut_outflow``). Before each cutting turn the guard is checked again: a
stand below ``GUARD_SHARE`` of its capacity, or a forest that fell to
another civ, ends the cutting (the crew turns home with what it cut).

Cargo and store. Cut timber is carried home and loses the economy's timber
transit decay per hop (``TRANSIT_DECAY``). On arrival (Phase 10) it is
credited to an RS2-earmarked store of the home region. RS2 reads the store as
free timber ahead of the stockpile, and its holds take from the store first
(the PL1 seam in ``repair_projects``; B3's works hold through RS2's holds);
nothing else can take it (it is not in the native stockpile). Timber left in
a region without an open RS2 project (or, with B3's works on, an open work
that asks for timber) is released to the region's stockpile, and the release
is recorded.

A turn the controller cannot pay recalls the expedition: the crew stops
cutting and walks home with the cargo, and every return-leg turn it cannot
pay is walked unpaid (reserved and away, its ordinary income withheld, no
wage; ``unpaid_turns``). Lost members leave the crew; the expedition goes on
while one remains.

Endings. Delivered; or abandoned when no crew member is left, the home region
changes hands, the forest is lost before the crew got there, the native pool
is rebuilt or the switch is turned off. Cut timber never vanishes: an
abandoned expedition's cargo is deposited in the forest region's stockpile as
commons (``abandoned``; no position is tracked on the way home), and only
transit decay is lost.

Closure, every turn: per civ ``charged x 1000 + prepaid before == wages
applied + prepaid after`` and ``wages applied + residual == wages due``; per
expedition ``cut == cargo + delivered + lost + abandoned`` (``lost``: transit
decay only); per store region ``opening -
held + returned + delivered - released == closing``; the economy's
``woodcut_output`` is exactly what the crews cut, only where a crew cut.

All constants are declared modelling choices, not calibrations; none was
tuned on any run.
"""
from __future__ import annotations

import math

from chronicler.timber_supply_state import (
    MAX_CLOSED, MAX_DROPS, MAX_HISTORY, MAX_NEEDS, MODES, Expedition, ExpeditionReceipt,
    NeedRow, StoreRow, TimberSupplyState, WageLedger,
)
from chronicler.switch_state import lane_active, sub_state_getter

MILLI = 1000
#: Most named woodcutters on one expedition: RS2's ``MAX_CREW``, the named
#: repair crew size this phase already declares (declared, uncalibrated).
CREW_CAP = 4
#: Most hops on the region graph from the needing region to the forest. A hop
#: is a turn of travel each way, as a merchant carries one load one hop a
#: turn, so the longest expedition is ``2 x MAX_HOPS + CUT_TURNS`` = 7 turns
#: (declared, uncalibrated).
MAX_HOPS = 2
#: Turns a crew cuts at the forest: one season (a turn is a month; declared).
CUT_TURNS = 3
#: No expedition cuts a stand whose L3 stock is below this share of its
#: effective capacity. The stand's logistic regrowth peaks at (1 -
#: ``timber_stock.SEED_FRACTION``) / 2 = 0.475 of capacity, so below about half
#: a further cut slows its own recovery (declared, uncalibrated).
GUARD_SHARE = 0.5
#: Least per-turn gap (timber) an expedition is launched for: RS2's
#: ``MIN_WORKER_TIMBER``, half a turn of one repairer's timber (declared).
MIN_GAP = 0.5
#: Share of a member's turn the expedition takes: all of it (paid and withheld).
SHARE = 1.0
#: Native ``wealth_transfer::PURPOSES`` index of repair wages, and this
#: package's batch key under it. Every payer of ``repair_wage`` in a turn needs
#: its own batch: RS2 workshop repair wages 0, PL3 granary crews 1, PL1 2.
PURPOSE_REPAIR_WAGE = 3
WAGE_BATCH = 2
#: Native ``workshop_work::RESERVATION_CATEGORIES`` index of repair work.
CATEGORY_REPAIR = 3
#: Native occupations and age (``agent::Occupation``, ``agent::AGE_ADULT``).
FARMER = 0
SOLDIER = 1
AGE_ADULT = 20
#: Native economy columns (Float32 per region), present only while a crew works.
AWAY_COLUMN = "woodcut_labor_away"
LABOR_COLUMN = "woodcut_labor"
EPS = 1e-9

_NATIVE = ("reserve_work", "work_reservations", "extend_paid_work", "transfer_wealth", "cancel_paid_work",
           "take_paid_work_receipt")


def transit_keep(hops: int) -> float:
    """Share of a cargo left after ``hops`` hops of the economy's timber transit decay."""
    from chronicler.economy import TRANSIT_DECAY
    return (1.0 - TRANSIT_DECAY["timber"]) ** int(hops)


def wage_milli() -> int:
    """Wage per crew member and turn (RS2's ``WAGE_PER_WORK`` for the whole turn)."""
    from chronicler.repair_projects import _wage
    return _wage(SHARE)


# ---------------------------------------------------------------------------
# Switch and lookups
# ---------------------------------------------------------------------------

class _Plan:
    """One live expedition's Phase 2 (never persisted)."""

    __slots__ = ("exp", "stage", "crew", "drops", "farm", "labor", "wage", "cut_end", "end", "idle",
                 "veterans", "unpaid", "recalled")

    def __init__(self, exp: Expedition):
        self.exp = exp
        self.stage = exp.stage
        self.crew: list[int] = []
        self.drops: list[tuple[int, str]] = []
        self.farm = 0.0          # headcount farm labour away from home
        self.labor = 0.0         # headcount on the forest slot
        self.wage = 0
        self.cut_end: str | None = None
        self.end: str | None = None
        self.idle = False        # the schedule completed without work this turn
        self.veterans: list[int] = []
        self.unpaid = False      # the civ cannot pay this turn: walked home unpaid
        self.recalled = False    # this turn's unpayable wages recalled the crew


class _Turn:
    """One turn in flight, from the first store hold of Phase 2 to Phase 10."""

    def __init__(self, turn: int, sim):
        self.turn, self.sim = turn, sim
        self.reserved = False             # the live crews were reserved (``reserve_first``)
        self.prepared = False
        self.finished = False
        self.plans: list[_Plan] = []
        self.columns = False
        self.installed = False
        self.receipt: dict | None = None
        self.receipts: list[ExpeditionReceipt] = []
        self.ledger: list[WageLedger] = []
        # Store flows of this turn, per region.
        self.store_open: dict[int, float] = {}
        self.held: dict[int, float] = {}
        self.hold_total: dict[int, float] = {}
        self.stock_left: dict[int, float] = {}
        self.returned: dict[int, float] = {}
        self.delivered: dict[int, float] = {}
        self.released: dict[int, float] = {}
        self.needs: list[NeedRow] = []
        self.needs_dropped = 0


_state = sub_state_getter("timber_supply")


def _bump(state, key: str, amount=1) -> None:
    state.bump(key, amount)


def _note(exp: Expedition, turn: int, event: str) -> None:
    exp.history.append((turn, event))
    del exp.history[:-MAX_HISTORY]


_lane_active = lane_active


def set_timber_supply_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable (with ``--timber-supply-mode``, default ``supply``) or disable; an
    omitted mode keeps the saved one. Disabling abandons live expeditions,
    releases every store to its region's stockpile and writes off prepaid
    wages."""
    mode = getattr(args, "timber_supply_mode", None) if args is not None else None
    state = _state(world)
    if state is None:
        world.livelihoods.timber_supply = state = TimberSupplyState(mode=mode or MODES[0])
    else:
        t = state._turn
        if t is not None and t.turn == getattr(world, "turn", None) and (t.prepared or t.held):
            raise RuntimeError("cannot change timber supply while a turn is pending")
        if mode is not None:
            state.mode = mode
    if not value and state.enabled:
        turn = getattr(world, "turn", 0)
        ended = len(state.expeditions)
        cargo = math.fsum(e.cargo for e in state.expeditions)
        for exp in list(state.expeditions):
            _end(world, state, exp, turn, "switched_off")
        _flush_deposits(world, state)
        released = math.fsum(state.store.values())
        for region, amount in sorted(state.store.items()):
            goods = world.regions[region].stockpile.goods
            goods["timber"] = goods.get("timber", 0.0) + amount
            _bump(state, "released", amount)
        state.store = {}
        _bump(state, "switched_off_cargo", cargo)
        _bump(state, "switched_off_store", released)
        state.switched_off.append((turn, ended, cargo, released))
        del state.switched_off[:-8]
        _write_off(state, list(state.prepaid))
    state.enabled = bool(value)


def _write_off(state, civs) -> None:
    for civ in civs:
        amount = state.prepaid.pop(civ, 0)
        if amount:
            _bump(state, "prepaid_written_off_milli", amount)


def timber_supply_active(world) -> bool:
    """Enabled in a hybrid run with RS2 and the L3 stock active."""
    state = _state(world)
    if state is None or not state.enabled or getattr(world, "agent_mode", None) != "hybrid":
        return False
    return _lane_active(world, "repair_projects") and _lane_active(world, "timber_stock")


def _controller(world, region: int) -> int:
    from chronicler.repair_projects import _controller as controller
    return controller(world, region)


def _timber_slot(region) -> int | None:
    from chronicler.models import ResourceType
    return next((s for s, rt in enumerate(region.resource_types) if int(rt) == int(ResourceType.TIMBER)), None)


def _native(agent_bridge):
    sim = getattr(agent_bridge, "_sim", None)
    if sim is None or not all(callable(getattr(sim, name, None)) for name in _NATIVE):
        raise RuntimeError("timber supply requires a fresh native build with the RS0 work registry")
    return sim


def _begin(world, state, sim=None) -> _Turn:
    t = state._turn
    if t is not None and t.turn == world.turn:
        if t.finished and t.prepared and sim is not None:
            raise RuntimeError("timber supply already settled for this turn")
        return t
    if state.last_settled_turn is not None and world.turn <= state.last_settled_turn:
        raise RuntimeError("timber supply already settled for this turn")
    t = state._turn = _Turn(world.turn, sim)
    return t


def _enlisted(world) -> set[int]:
    armies = getattr(getattr(world, "war_state", None), "armies", None) or []
    return {int(aid) for army in armies for aid, _ in army.roster}


def _trips(sim) -> set[int]:
    fn = getattr(sim, "trip_agent_ids", None)
    return {int(a) for a in fn()} if callable(fn) else set()


def _rows(snapshot):
    """(id, region, occupation, age, settlement_id) arrays of the living agents."""
    import numpy as np
    from chronicler.columnar import batch_arrays, pylist
    names = ("id", "region", "occupation", "age", "settlement_id")
    if snapshot is None:
        raise RuntimeError("timber supply requires the agent snapshot")
    arrays = batch_arrays(snapshot, names)
    if arrays is None:
        arrays = tuple(np.asarray(pylist(snapshot.column(name)), dtype=np.int64) for name in names)
    return tuple(np.asarray(a).astype(np.int64) for a in arrays)


def _facts(snapshot, wanted) -> dict[int, tuple[int, int, int, int]]:
    """``{id: (region, occupation, age, settlement)}`` for wanted ids alive in the snapshot."""
    if not wanted:
        return {}
    from chronicler.columnar import last_row_of
    ids, region, occupation, age, settlement = _rows(snapshot)
    rows = last_row_of(ids, wanted)
    return {aid: (int(region[i]), int(occupation[i]), int(age[i]), int(settlement[i])) for aid, i in rows.items()}


def _farm_share(world, home: int, fact) -> float:
    """A crew member's farm labour at home: 0 for a non-farmer; 1, or the
    city's ``URBAN_FARM_LABOR[rank]`` for a farmer living in a city of the
    region (as ``cities.economy_columns`` counts it)."""
    if fact[1] != FARMER:
        return 0.0
    from chronicler.cities import URBAN_FARM_LABOR, cities_on
    if not cities_on(world) or fact[3] <= 0:
        return 1.0
    city = next((c for c in world.cities.cities if c.settlement_id == fact[3] and c.region == home), None)
    return float(URBAN_FARM_LABOR[city.rank]) if city is not None else 1.0


def _drop_reason(fact, home: int, aid: int, enlisted, trips, soldiers=()) -> str | None:
    """Why a member leaves the crew (None: stays). A veteran admitted while of
    Soldier occupation (``soldiers``) leaves only when back on a roster."""
    if fact is None:
        return "died"
    if fact[0] != home:
        return "migrated"
    if aid in enlisted or (fact[1] == SOLDIER and aid not in soldiers):
        return "enlisted"
    if aid in trips:
        return "on_trip"
    return None


def _end(world, state, exp: Expedition, turn: int, reason: str, *, defer: bool = False,
         region: int | None = None) -> None:
    """End a live expedition without delivering. Its cargo is deposited as
    commons (``abandoned``) in ``region``'s stockpile, by default the forest
    region's: now, or at the next Phase 10 with ``defer`` (a pool rebuild can
    come after the economy batch packed the stockpiles, whose write-back
    would drop a deposit made now)."""
    if exp.cargo:
        where = exp.forest if region is None else int(region)
        amount, exp.cargo = exp.cargo, 0.0
        exp.abandoned += amount
        _bump(state, "abandoned_cargo", amount)
        state.pending_deposits[where] = state.pending_deposits.get(where, 0.0) + amount
        state.deposits.append((turn, exp.eid, where, amount))
        if not defer:
            _flush_deposits(world, state)
    exp.status, exp.ended_turn, exp.end_reason = "abandoned", turn, reason
    _note(exp, turn, f"abandoned_{reason}")
    _bump(state, f"abandoned_{reason}")
    _close(state, exp)


def _flush_deposits(world, state) -> None:
    """Add pending abandoned cargo to the forest regions' stockpiles."""
    for region, amount in sorted(state.pending_deposits.items()):
        goods = world.regions[region].stockpile.goods
        goods["timber"] = goods.get("timber", 0.0) + amount
    state.pending_deposits = {}


def _close(state, exp: Expedition) -> None:
    state.expeditions = [e for e in state.expeditions if e is not exp]
    state.closed.append(exp)
    del state.closed[:-MAX_CLOSED]
    _bump(state, "ended")
    _bump(state, "ended_wages_milli", exp.wages_milli)
    _bump(state, "ended_person_turns", exp.person_turns)
    _bump(state, "ended_away", exp.away_delivered)
    _bump(state, "ended_cut", exp.cut)
    _bump(state, "ended_delivered", exp.delivered)
    _bump(state, "ended_unpaid_turns", exp.unpaid_turns)


def _drop(state, exp: Expedition, turn: int, aid: int, reason: str) -> None:
    exp.crew = [a for a in exp.crew if a != aid]
    exp.drops.append((turn, aid, reason))
    del exp.drops[:-MAX_DROPS]
    _bump(state, f"dropped_{reason}")


# ---------------------------------------------------------------------------
# Seams: RS2's store reads and holds, the L3 stand
# ---------------------------------------------------------------------------

def store_free(world, region: int) -> float:
    """RS2 seam: the region's earmarked timber not yet held this turn (RS2
    reads it as free timber ahead of the stockpile). 0.0 while inactive."""
    state = _state(world)
    if state is None or not timber_supply_active(world):
        return 0.0
    amount = float(state.store.get(int(region), 0.0))
    if not (math.isfinite(amount) and amount >= 0.0):
        raise ValueError("invalid timber store")
    return amount



def deliver_ordered_store(world, region: int, amount: float) -> None:
    """A4-3 delivery into the existing repair store, included in PL1's account.

    Called after ``phase10_before_reserves`` and before PL1 closes its frame.
    No independent store is created and the delivery is not free commons stock.
    """
    state = _state(world)
    if state is None or not timber_supply_active(world):
        raise RuntimeError("ordered timber delivery requires active timber supply")
    if not isinstance(region, int) or not 0 <= region < len(world.regions) or not math.isfinite(amount) or amount < 0:
        raise ValueError("invalid ordered timber delivery")
    t = state._turn
    if t is None or t.turn != world.turn:
        raise RuntimeError("ordered timber delivery outside the PL1 open turn")
    t.store_open.setdefault(region, state.store.get(region, 0.0))
    state.store[region] = state.store.get(region, 0.0) + amount
    t.delivered[region] = t.delivered.get(region, 0.0) + amount

def take_store(world, region: int, amount: float) -> float:
    """RS2 seam (its holds, before the native economy): take up to ``amount``
    from the region's store first; returns what was taken (0.0 without a
    store). ``amount`` is the region's whole hold; the rest comes from the
    stockpile."""
    have = store_free(world, region)
    if have <= 0.0 or not amount > 0.0:
        return 0.0
    state = _state(world)
    t = _begin(world, state)
    region = int(region)
    taken = min(float(amount), have)
    t.store_open.setdefault(region, have)
    t.held[region] = t.held.get(region, 0.0) + taken
    t.hold_total[region] = t.hold_total.get(region, 0.0) + float(amount)
    t.stock_left.setdefault(region, 0.0)
    t.stock_left[region] += float(amount) - taken
    left = have - taken
    if left > 0.0:
        state.store[region] = left
    else:
        state.store.pop(region, None)
    return taken


def return_store(world, region: int, returned: float) -> float:
    """RS2 seam (after the economy): of ``returned`` unused held timber, put
    back into the store what the hold took from it beyond the timber used
    (the store is used first, so the stockpile's part is returned first);
    returns the store's part (0.0 without a store hold this turn)."""
    state = _state(world)
    t = state._turn if state is not None else None
    region = int(region)
    if t is None or t.turn != world.turn or t.held.get(region, 0.0) <= 0.0 or not returned > 0.0:
        return 0.0
    to_stock = min(float(returned), max(0.0, t.stock_left.get(region, 0.0)))
    t.stock_left[region] = t.stock_left.get(region, 0.0) - to_stock
    back = float(returned) - to_stock
    if back > 0.0:
        state.store[region] = state.store.get(region, 0.0) + back
        t.returned[region] = t.returned.get(region, 0.0) + back
    return back


def restore_store(world, region: int) -> float:
    """RS2 seam (a failed Phase 2): put the region's whole store hold back;
    returns it (0.0 without one)."""
    state = _state(world)
    t = state._turn if state is not None else None
    region = int(region)
    if t is None or t.turn != world.turn:
        return 0.0
    held = t.held.pop(region, 0.0) - t.returned.pop(region, 0.0)
    t.hold_total.pop(region, None)
    t.stock_left.pop(region, None)
    if held > 0.0:
        state.store[region] = state.store.get(region, 0.0) + held
    return max(0.0, held)


def _stand(world, rid: int, slot: int):
    from chronicler.timber_stock import stand
    return stand(world, rid, slot)


def _healthy(stand) -> bool:
    return stand is not None and stand[1] > 0.0 and stand[0] >= GUARD_SHARE * stand[1]


def pending_bills(world) -> list[int]:
    """Whole units each civ's planned, not yet charged expedition wages will
    cost this Phase 2 (for planners that run after this package; nothing
    reads it yet: the lead wires it where later lanes need it)."""
    out = [0] * len(world.civilizations)
    state = _state(world)
    t = state._turn if state is not None else None
    if t is None or t.turn != world.turn or t.finished or not t.prepared:
        return out
    milli = [0] * len(out)
    for p in t.plans:
        if p.crew and 0 <= p.exp.civ < len(milli):
            milli[p.exp.civ] += len(p.crew) * p.wage
    return [-(-m // MILLI) for m in milli]


# ---------------------------------------------------------------------------
# Phase 2
# ---------------------------------------------------------------------------

def _forest_problem(world, exp: Expedition) -> str | None:
    """Why the crew cannot cut its forest this turn (None: it can)."""
    region = world.regions[exp.forest]
    if _timber_slot(region) != exp.slot:
        return "forest_lost"
    controller = region.controller
    if controller is not None and controller != world.civilizations[exp.civ].name:
        return "forest_lost"
    if not _healthy(_stand(world, exp.forest, exp.slot)):
        return "forest_depleted"
    return None


def _budgets(world, acc) -> list[int]:
    """Whole units each civ may still spend this Phase 2: the projected
    treasury less every bill planned earlier and not yet charged (storage,
    the funded L1 bills, the L8 warden bills and RS2's planned repairs)."""
    from chronicler.mutual_aid import _treasury_budget
    from chronicler.repair_projects import _pending_before_granaries, pending_bills
    others = _pending_before_granaries(world)
    repairs = pending_bills(world)
    return [max(0, math.floor(_treasury_budget(world, c, acc)) - others[i] - repairs[i])
            for i, c in enumerate(world.civilizations)]


def _reserve(sim, turn: int, aid: int) -> bool:
    """Reserve one member's whole turn; False when they already hold work."""
    try:
        sim.reserve_work(turn, CATEGORY_REPAIR, [(aid, SHARE)])
    except ValueError as error:
        if "already holds work" in str(error):
            return False
        raise
    return True


def reserve_first(world, agent_bridge, snapshot) -> None:
    """Livelihoods seam, before any package plans this turn's work (review A,
    2026-11-06): the crews of live expeditions are away, so they are re-checked
    and reserved here, ahead of the L1 crews, RS1 seats and attached
    apprentices, RS2 workshop repair crews and PL3 granary and workshop crews,
    which all exclude registry holders. Only rural health work and a teaching
    plan, prepared before the livelihoods hooks, come first. Charges nothing."""
    state = _state(world)
    sim = _native(agent_bridge)
    t = _begin(world, state, sim)
    if t.reserved or t.prepared:
        raise RuntimeError("timber supply crews already reserved for this turn")
    t.sim, t.reserved = sim, True
    live = sorted(state.expeditions, key=lambda e: e.eid)
    if not live:
        return
    facts = _facts(snapshot, {a for e in live for a in e.crew})
    t.individual_occupations = {aid: fact[1] for aid, fact in facts.items()}
    enlisted = _enlisted(world)
    trips = _trips(sim)
    open_veterans = frozenset()
    if _lane_active(world, "veteran_reintegration"):
        from chronicler.veteran_reintegration import open_record_ids
        open_veterans = open_record_ids(world)
    for exp in live:
        plan = _Plan(exp)
        t.plans.append(plan)
        if _controller(world, exp.home) != exp.civ:
            plan.end = "home_lost"
            continue
        crew = []
        for aid in exp.crew:
            reason = _drop_reason(facts.get(aid), exp.home, aid, enlisted, trips, exp.soldier_veterans)
            if reason is None:
                crew.append(aid)
            else:
                plan.drops.append((aid, reason))
        if plan.stage == "outbound" and _forest_problem(world, exp) == "forest_lost":
            plan.end = "forest_lost"
            continue
        if plan.stage == "cutting":
            problem = _forest_problem(world, exp)
            if problem is not None:
                plan.cut_end, plan.stage = problem, "returning"
                if exp.hops == 0:
                    plan.idle = True          # home already: nothing to walk, nothing paid
                    continue
        if not crew:
            plan.end = "crew_lost"
            continue
        for aid in crew:
            if _reserve(sim, world.turn, aid):
                plan.crew.append(aid)
            else:
                plan.drops.append((aid, "other_work"))
        if not plan.crew:
            plan.end = "crew_lost"
            continue
        plan.farm = math.fsum(_farm_share(world, exp.home, facts[aid]) for aid in plan.crew)
        plan.veterans = [a for a in plan.crew if a in open_veterans]


def prepare_phase2(world, region_input, agent_bridge, snapshot, acc):
    """After every earlier Phase 2 planner: plan the reserved crews' wages
    (a turn the civ cannot pay recalls the crew) and append the woodcut
    columns; charges nothing."""
    state = _state(world)
    sim = _native(agent_bridge)
    t = _begin(world, state, sim)
    if t.prepared:
        raise RuntimeError("timber supply already prepared for this turn")
    if state.expeditions and not t.reserved:
        raise RuntimeError("timber supply crews were not reserved before the Phase 2 planners")
    t.sim = sim
    names = set(region_input.schema.names)
    if names & {AWAY_COLUMN, LABOR_COLUMN}:
        raise ValueError("woodcut columns are owned by timber supply")
    if not t.plans:
        t.prepared = True
        return region_input
    budgets = _budgets(world, acc)
    planned = [0] * len(budgets)
    wage = wage_milli()
    n = len(world.regions)
    away = [0.0] * n
    labor = [0.0] * n
    for plan in t.plans:
        exp = plan.exp
        if plan.end is not None or plan.idle:
            continue
        if budgets[exp.civ] * MILLI - planned[exp.civ] < len(plan.crew) * wage:
            # A turn the civ cannot pay: the crew stops cutting and walks home
            # with the cargo, unpaid for the turns it cannot pay.
            plan.unpaid = True
            if plan.stage != "returning":
                plan.recalled = True
                back = exp.travelled if plan.stage == "outbound" else exp.hops
                if plan.stage == "cutting":
                    plan.cut_end = "recalled"
                plan.stage = "returning"
                if back == 0:
                    # Home already: arrives this turn. The turn's reservation,
                    # made before anything was planned, is not worked or paid.
                    plan.idle, plan.crew, plan.farm, plan.veterans = True, [], 0.0, []
                    continue
        if not plan.unpaid:
            plan.wage = wage
            planned[exp.civ] += len(plan.crew) * wage
        away[exp.home] += plan.farm
        if plan.stage == "cutting" and state.mode == "supply":
            plan.labor = float(len(plan.crew))
            labor[exp.forest] += plan.labor
    if any(p.crew for p in t.plans):
        import pyarrow as pa
        region_input = region_input.append_column(AWAY_COLUMN, pa.array(away, type=pa.float32()))
        region_input = region_input.append_column(LABOR_COLUMN, pa.array(labor, type=pa.float32()))
        t.columns = True
    t.prepared = True
    return region_input


def finish_phase2(world, economy_result, agent_bridge, acc):
    """After the native economy tick: pay the crews once, take the cut timber
    on board, advance each expedition and arm the paid share."""
    state = _state(world)
    t = state._turn
    if t is None or t.turn != world.turn or not t.prepared or t.finished:
        raise RuntimeError("timber supply plan missing for this turn")
    sim = t.sim
    import numpy as np
    away_out = getattr(economy_result, "woodcut_labor_away_delivered", None) or {}
    cut_out = getattr(economy_result, "woodcut_output", None) or {}
    if t.columns and (set(away_out) != set(range(len(world.regions))) or set(cut_out) != set(away_out)):
        raise RuntimeError("timber supply requires a native extension with the woodcut columns")
    if not t.columns and (away_out or cut_out):
        raise RuntimeError("woodcut results without woodcut columns")
    labor_at = {p.exp.forest: p for p in t.plans if p.labor > 0}
    away_at = {p.exp.home: p for p in t.plans if p.crew}
    for rid, value in cut_out.items():
        if not (math.isfinite(value) and value >= 0.0) or (value > 0.0 and rid not in labor_at):
            raise RuntimeError("woodcut output where no crew cut")
    for rid, value in away_out.items():
        plan = away_at.get(rid)
        asked = float(np.float32(plan.farm)) if plan is not None else 0.0
        if not (math.isfinite(value) and 0.0 <= value <= asked):
            raise RuntimeError("woodcut labour away beyond the request")
    # Validate the bill before anything moves.
    due = [0] * len(world.civilizations)
    for p in t.plans:
        if p.crew:
            if _controller(world, p.exp.home) != p.exp.civ:
                raise RuntimeError("expedition payer changed while its wages were pending")
            due[p.exp.civ] += len(p.crew) * p.wage
    from chronicler.mutual_aid import _treasury_budget
    for i, civ in enumerate(world.civilizations):
        if due[i] and _treasury_budget(world, civ, acc) < -(-due[i] // MILLI):
            raise RuntimeError("expedition wages exceed the projected treasury at settlement")
    rows = sorted((aid, SHARE) for p in t.plans for aid in p.crew)
    if rows:
        sim.extend_paid_work(world.turn, rows)
        t.installed = True
    wages = sorted((aid, p.wage) for p in t.plans for aid in p.crew if p.wage > 0)
    applied: dict[int, tuple[int, int]] = {}
    if wages:
        for aid, requested, got, residual, status in sim.transfer_wealth(
                world.turn, PURPOSE_REPAIR_WAGE, WAGE_BATCH, wages):
            applied[int(aid)] = (int(got), int(residual) if status != 2 else int(requested))
    t.individual_wages = applied
    accounts = _settled_accounts(world)
    turn = world.turn
    ledger: dict[int, dict] = {}
    receipts = []
    for p in t.plans:
        exp = p.exp
        for aid, reason in p.drops:
            _drop(state, exp, turn, aid, reason)
        if p.end is not None:
            _end(world, state, exp, turn, p.end)
            continue
        if p.recalled:
            back = exp.travelled if exp.stage == "outbound" else exp.hops
            exp.recalled_turn = turn
            exp.stage, exp.stage_turns, exp.return_hops = "returning", 0, back
            _bump(state, "recalls")
            _note(exp, turn, "recalled")
        if p.cut_end is not None:
            _bump(state, f"cut_end_{p.cut_end}")
            _note(exp, turn, f"cut_end_{p.cut_end}")
            exp.cut_end, exp.stage, exp.stage_turns, exp.return_hops = p.cut_end, "returning", 0, exp.hops
        if p.idle:
            exp.arrived = True
            continue
        cut = float(cut_out.get(exp.forest, 0.0)) if p.labor > 0 else 0.0
        paid = sum(applied.get(a, (0, 0))[0] for a in p.crew)
        residual = sum(applied.get(a, (0, p.wage))[1] for a in p.crew)
        delivered_away = float(away_out.get(exp.home, 0.0))
        account = accounts.get((exp.forest, exp.slot)) if p.stage == "cutting" else None
        row = ledger.setdefault(exp.civ, dict(expeditions=0, people=0, due=0, applied=0, residual=0)) \
            if not p.unpaid else dict(expeditions=0, people=0, due=0, applied=0, residual=0)
        row["expeditions"] += 1
        row["people"] += len(p.crew)
        row["due"] += len(p.crew) * p.wage
        row["applied"] += paid
        row["residual"] += residual
        exp.cargo += cut
        exp.cut += cut
        exp.worked_turns += 1
        exp.person_turns += len(p.crew)
        exp.wages_milli += paid
        exp.wage_residual_milli += residual
        exp.away_requested += p.farm
        exp.away_delivered += delivered_away
        if p.unpaid:
            exp.unpaid_turns += 1
            _bump(state, "unpaid_turns")
        receipts.append(ExpeditionReceipt(
            turn=turn, eid=exp.eid, civ=exp.civ, home=exp.home, forest=exp.forest, slot=exp.slot,
            stage=p.stage, crew=list(p.crew), veterans=list(p.veterans), dropped=list(p.drops),
            away_requested=p.farm, away_delivered=delivered_away, crew_labor=p.labor, cut=cut,
            cargo_after=exp.cargo,
            stock_before=account[0] if account is not None else None,
            stock_after=account[1] if account is not None else None,
            capacity=account[2] if account is not None else None,
            wages_due_milli=len(p.crew) * p.wage, wages_milli=paid, wage_residual_milli=residual,
            cut_end=p.cut_end, unpaid=p.unpaid, recalled=p.recalled))
        _bump(state, "person_turns", len(p.crew))
        _bump(state, f"crew_turns_{p.stage}", len(p.crew))
        _bump(state, "cut", cut)
        _bump(state, "away_requested", p.farm)
        _bump(state, "away_delivered", delivered_away)
        _bump(state, "crew_labor", p.labor)
        _advance(state, exp, p.stage, turn)
    out = []
    for civ in sorted(ledger):
        r = ledger[civ]
        before = int(state.prepaid.get(civ, 0))
        need = r["applied"] - before
        charged = max(0, -(-need // MILLI))
        after = charged * MILLI - need
        if after:
            state.prepaid[civ] = after
        else:
            state.prepaid.pop(civ, None)
        if charged:
            target = world.civilizations[civ]
            if acc is None:
                target.treasury -= charged
            else:
                acc.add(civ, target, "treasury", -charged, "keep")
        out.append(WageLedger(turn=turn, civ=civ, expeditions=r["expeditions"], person_turns=r["people"],
                              wages_due_milli=r["due"], wages_applied_milli=r["applied"],
                              wage_residual_milli=r["residual"], charged=charged,
                              prepaid_before_milli=before, prepaid_after_milli=after))
        _bump(state, "charged", charged)
        _bump(state, "wages_due_milli", r["due"])
        _bump(state, "wages_milli", r["applied"])
        _bump(state, "wage_residual_milli", r["residual"])
    for row in out:
        check_ledger(row)
    t.receipts, t.ledger = receipts, out
    t.finished = True
    if _lane_active(world, "veteran_reintegration"):
        from chronicler.veteran_reintegration import note_outcome
        for r in receipts:
            for aid in r.veterans:
                note_outcome(world, aid, "placed:repair", turn=turn,
                             detail={"expedition": r.eid, "region": r.home, "forest": r.forest})
                _bump(state, "veterans_placed")
    return []


def _advance(state, exp: Expedition, stage: str, turn: int) -> None:
    """One worked turn of ``stage`` is done."""
    exp.stage_turns += 1
    if stage == "outbound":
        exp.travelled += 1
        if exp.travelled >= exp.hops:
            exp.stage, exp.stage_turns = "cutting", 0
            _note(exp, turn, "at_forest")
    elif stage == "cutting":
        exp.cut_turns += 1
        if exp.cut_turns >= CUT_TURNS:
            exp.cut_end, exp.stage, exp.stage_turns, exp.return_hops = "completed", "returning", 0, exp.hops
            _bump(state, "cut_end_completed")
            _note(exp, turn, "cut_end_completed")
            if exp.hops == 0:
                exp.arrived = True
    elif exp.stage_turns >= exp.return_hops:
        exp.arrived = True


def _settled_accounts(world) -> dict[tuple[int, int], tuple[float, float, float]]:
    """This turn's L3 accounts: (opening, stock after, capacity) per slot."""
    from chronicler.timber_stock import settled_accounts
    return settled_accounts(world)


def check_ledger(row: WageLedger) -> None:
    """Exact integer closure of one civ's expedition wages in one turn."""
    if row.charged * MILLI + row.prepaid_before_milli != row.wages_applied_milli + row.prepaid_after_milli \
            or not 0 <= row.prepaid_before_milli < MILLI or not 0 <= row.prepaid_after_milli < MILLI \
            or row.charged < 0:
        raise RuntimeError(f"expedition accounts of civ {row.civ} do not close")
    if row.wages_applied_milli + row.wage_residual_milli != row.wages_due_milli:
        raise RuntimeError(f"expedition wages of civ {row.civ} do not close")


def rollback_phase2(world) -> None:
    """A failed Phase 2: nothing was charged or carried; disarm the paid share."""
    state = _state(world)
    t = state._turn if state is not None else None
    if t is None or t.turn != getattr(world, "turn", None):
        return
    # RS2's own rollback puts its store holds back (``restore_store``), and
    # only while its work is unsettled: settled work used the timber.
    if t.installed and t.sim is not None:
        t.sim.cancel_paid_work()
    state._turn = None


def rollback_agent_tick(world, agent_bridge) -> None:
    """The agent tick raised: disarm an unconsumed paid share."""
    state = _state(world)
    t = state._turn if state is not None else None
    if t is not None and t.turn == world.turn and t.installed and t.receipt is None and t.sim is not None:
        t.sim.cancel_paid_work()
        t.installed = False


def after_agent_tick(world, agent_bridge):
    state = _state(world)
    t = state._turn
    if t is None or t.turn != world.turn or not t.installed:
        return []
    from chronicler.livelihoods import paid_work_receipt
    receipt = paid_work_receipt(world, t.sim)    # shared with other paid-work packages
    if receipt is None:
        raise RuntimeError("paid work receipt missing for this turn")
    t.receipt = receipt
    by_eid = {e.eid: e for e in state.expeditions}
    for r in t.receipts:
        if r.crew:
            r.income_withheld = math.fsum(receipt[a][2] for a in r.crew if a in receipt)
            _bump(state, "income_withheld", r.income_withheld)
            from chronicler.work_experience import record
            for aid in r.crew:
                record(world, aid, "woodcut", paid_milli=getattr(t, "individual_wages", {}).get(aid, (0, 0))[0],
                       receipt=receipt, share=SHARE, region=r.home,
                       occupation=getattr(t, "individual_occupations", {}).get(aid),
                       source="timber_supply:untruncated individual wage + keyed paid-work receipt")
            exp = by_eid.get(r.eid)
            if exp is not None:
                exp.income_withheld += r.income_withheld
    return []


def on_pool_reset(world) -> None:
    """A rebuilt native pool (``livelihoods.bind_native_pool``): saved crew ids
    would name other people, so every live expedition is abandoned (its cargo
    is lost); the stores are not id-bound and stay."""
    state = _state(world)
    if state is None:
        return
    if state.expeditions:
        _bump(state, "pool_resets")
    for exp in list(state.expeditions):
        _end(world, state, exp, getattr(world, "turn", 0), "pool_reset", defer=True)


# ---------------------------------------------------------------------------
# Phase 10: crews, arrivals, releases, need and launches
# ---------------------------------------------------------------------------

def _wants(world) -> dict[int, float]:
    """Timber a turn each region's open RS2 projects could use at their
    per-turn caps: a granary's work cap, a workshop crew of ``MAX_CREW`` at
    its diverted share and rate (1 with RS1 active, else RS2's
    ``UNQUALIFIED_RATE``), each at most the project's remaining work, times
    its timber rate. A granary project RS2 suspends ``no_people`` (no farm
    labour in its region at this Phase 10, PL3) uses nothing and is skipped."""
    from chronicler import repair_projects as RP
    rp = RP._state(world)
    seen = getattr(rp, "_labour", None)
    labour = seen[1] if seen is not None and seen[0] == world.turn else None
    _per_condition, per_turn, timber_rate, _coins = RP._storage_rules()
    rate = 1.0 if _lane_active(world, "apprenticeship") else RP.UNQUALIFIED_RATE
    sites = RP._sites(world)
    out: dict[int, float] = {}
    for p in rp.projects:
        remaining = max(0.0, p.scope - p.delivered)
        if remaining <= RP.DONE or _controller(world, p.region) < 0:
            continue
        if p.kind == "granary":
            if labour is not None and labour[p.region] == 0:
                continue
            want = min(per_turn, remaining) * timber_rate
        else:
            site = sites.get(p.asset)
            if site is None:
                continue
            want = min(RP.MAX_CREW * RP._diverted(world, site) * rate, remaining) * RP.WORKSHOP_TIMBER_PER_WORK
        out[p.region] = out.get(p.region, 0.0) + want
    return out


def _hops_from(world, start: int) -> dict[int, int]:
    """Hops on the region graph (``Region.adjacencies``, sea lanes included) from ``start``."""
    index = {r.name: i for i, r in enumerate(world.regions)}
    dist = {start: 0}
    frontier = [start]
    while frontier:
        nxt = []
        for i in frontier:
            for name in world.regions[i].adjacencies:
                j = index.get(name)
                if j is not None and j not in dist:
                    dist[j] = dist[i] + 1
                    nxt.append(j)
        frontier = sorted(nxt)
    return dist


def _choose_forest(world, state, civ: int, home: int) -> tuple[tuple | None, str | None]:
    """The forest an expedition from ``home`` would cut, or the refusal."""
    name = world.civilizations[civ].name
    dist = _hops_from(world, home)
    busy = {e.forest for e in state.expeditions}
    candidates = []
    for rid, region in enumerate(world.regions):
        slot = _timber_slot(region)
        if slot is None or (region.controller is not None and region.controller != name) or rid not in dist:
            continue
        candidates.append((dist[rid], rid, slot))
    if not candidates:
        return None, "no_forest"
    in_range = [c for c in candidates if c[0] <= MAX_HOPS]
    if not in_range:
        return None, "too_far"
    healthy = []
    for hops, rid, slot in in_range:
        stand = _stand(world, rid, slot)
        if _healthy(stand):
            healthy.append((hops, -stand[0], rid, slot))
    if not healthy:
        return None, "forest_depleted"
    free = sorted(c for c in healthy if c[2] not in busy)
    if not free:
        return None, "forest_busy"
    hops, _neg, rid, slot = free[0]
    return (hops, rid, slot), None


def _choose_crew(world, state, snapshot, home: int, enlisted, trips) -> tuple[list[int], set[int]]:
    """At most ``CREW_CAP`` eligible residents of ``home``, RS3 veterans first,
    and which of them were admitted while of Soldier occupation. Eligible:
    living adults resident there, not on an army roster, not on a trip, not on
    another crew, of any occupation but Soldier; RS3-eligible veterans of any
    occupation, Soldier included (released, on no roster; the plan's "any
    non-enlisted occupation"), in both RS3 modes, first only under RS3
    ``priority``."""
    import numpy as np
    ids, region, occupation, age, _settlement = _rows(snapshot)
    resident = (region == home) & (age >= AGE_ADULT)
    taken = {a for e in state.expeditions for a in e.crew}

    def free(a: int) -> bool:
        return a not in enlisted and a not in trips and a not in taken

    eligible = sorted(int(a) for a in np.unique(ids[resident & (occupation != SOLDIER)]) if free(int(a)))
    soldiers = {int(a) for a in np.unique(ids[resident & (occupation == SOLDIER)]) if free(int(a))}
    first = []
    if _lane_active(world, "veteran_reintegration"):
        from chronicler.veteran_reintegration import eligible_ids, priority_ids
        # Released veterans of Soldier occupation on no roster are eligible in
        # both RS3 modes (RS3's own rule, ``eligible_ids``); only ``priority``
        # puts veterans first (integration, 2026-11-06).
        veterans = {int(a) for a in eligible_ids(world, home)}
        eligible = sorted(set(eligible) | (soldiers & veterans))
        pool = set(eligible)
        first = [int(a) for a in priority_ids(world, home) if int(a) in pool]
    seen = set(first)
    from chronicler.work_experience import accepts_offer
    order = [a for a in first + [a for a in eligible if a not in seen] if accepts_offer(world, a, "woodcut")][:CREW_CAP]
    return order, {a for a in order if a in soldiers}


def _remaining_bill(exp: Expedition, wage: int) -> int:
    """Milli-units the rest of a live expedition's schedule costs at full crew."""
    if exp.arrived:
        return 0
    if exp.stage == "outbound":
        turns = (exp.hops - exp.travelled) + CUT_TURNS + exp.hops
    elif exp.stage == "cutting":
        turns = (CUT_TURNS - exp.cut_turns) + exp.hops
    else:
        turns = exp.return_hops - exp.stage_turns
    return max(0, turns) * len(exp.crew) * wage


def phase10_before_reserves(world, acc, economy_result, agent_bridge):
    """After the agent tick and RS2's lifecycle: observe the crews, deliver
    arrived cargo, release stores without a project, then plan the need and
    launch expeditions (before RS3 commits its outcomes)."""
    state = _state(world)
    turn = world.turn
    t = _begin(world, state)
    if agent_bridge is None or getattr(agent_bridge, "_sim", None) is None:
        raise RuntimeError("timber supply requires the native agent pool")
    sim = agent_bridge._sim
    snapshot = agent_bridge.get_snapshot()
    if snapshot is None:
        raise RuntimeError("timber supply requires the post-tick agent snapshot")
    _flush_deposits(world, state)               # cargo abandoned at a pool rebuild
    enlisted = _enlisted(world)
    trips = _trips(sim)
    facts = _facts(snapshot, {a for e in state.expeditions for a in e.crew})
    for exp in sorted(state.expeditions, key=lambda e: e.eid):
        if exp.arrived:
            # The crew walked home in Phase 2: it delivers before the tick's
            # deaths and moves are observed (review A, 2026-11-06).
            _arrive(world, state, t, exp, turn)
            continue
        for aid in list(exp.crew):
            fact = facts.get(aid)
            reason = _drop_reason(fact, exp.home, aid, enlisted, (), exp.soldier_veterans)
            if reason is not None:
                _drop(state, exp, turn, aid, reason)
        if not exp.crew:
            _end(world, state, exp, turn, "crew_lost")
    from chronicler.repair_projects import _state as rp_state
    open_regions = {p.region for p in rp_state(world).projects} | _works_regions(world)
    for region in sorted(state.store):
        amount = state.store[region]
        if region in open_regions:
            continue
        t.store_open.setdefault(region, amount)
        goods = world.regions[region].stockpile.goods
        goods["timber"] = goods.get("timber", 0.0) + amount
        t.released[region] = t.released.get(region, 0.0) + amount
        _bump(state, "released", amount)
        del state.store[region]
    t.needs, t.needs_dropped = _plan_launches(world, state, snapshot, sim, acc, enlisted, trips)
    _write_off(state, [civ for civ in sorted(state.prepaid)
                       if not 0 <= civ < len(world.civilizations) or not world.civilizations[civ].regions])
    return []


def _arrive(world, state, t, exp: Expedition, turn: int) -> None:
    """An arrived crew's cargo, less the way home's decay, goes to the home
    region's store (``delivered``), or, when nothing is left to deliver, the
    expedition has ``returned``. If the home region changed hands on the way,
    the cargo is deposited there as commons (``home_lost``)."""
    keep = transit_keep(exp.return_hops)
    delivered = exp.cargo * keep
    lost = exp.cargo - delivered
    exp.lost += lost
    _bump(state, "lost", lost)
    if _controller(world, exp.home) != exp.civ:
        exp.cargo = delivered
        _end(world, state, exp, turn, "home_lost", region=exp.home)
        return
    exp.delivered, exp.cargo, exp.ended_turn = delivered, 0.0, turn
    if delivered > 0.0:
        exp.status = "delivered"
        _note(exp, turn, "delivered")
        _bump(state, "delivered_expeditions")
        _bump(state, "delivered", delivered)
        t.store_open.setdefault(exp.home, state.store.get(exp.home, 0.0))
        state.store[exp.home] = state.store.get(exp.home, 0.0) + delivered
        t.delivered[exp.home] = t.delivered.get(exp.home, 0.0) + delivered
    else:
        exp.status = "returned"
        _note(exp, turn, "returned")
        _bump(state, "returned_expeditions")
    _close(state, exp)


def _works_wants(world) -> list:
    """B3 seam: the open infrastructure works' timber need per region
    (``infrastructure_condition.timber_wants``); empty unless the works are on."""
    if getattr(getattr(world, "livelihoods", None), "infrastructure_condition", None) is None:
        return []
    from chronicler.infrastructure_condition import timber_wants
    return timber_wants(world)


def _works_regions(world) -> frozenset[int]:
    """B3 seam: regions whose open infrastructure works ask for timber (the
    screen of ``timber_wants``; the store is kept there for them, as for an
    open RS2 project); empty unless the works are on."""
    if getattr(getattr(world, "livelihoods", None), "infrastructure_condition", None) is None:
        return frozenset()
    from chronicler.infrastructure_condition import timber_regions
    return timber_regions(world)


def _try_launch(world, state, snapshot, civ: int, region: int, gap: float, acc, enlisted, trips, wage: int,
                turn: int, counter: str = "launched") -> tuple[str | None, Expedition | None]:
    """Launch an expedition from ``region`` for ``gap``, or name the first
    failing check (``REFUSALS`` order): ``(None, expedition)`` or ``(reason, None)``.
    ``counter``: ``launched`` for RS2's need, ``launched_works`` for B3's works."""
    from chronicler.mutual_aid import _treasury_budget
    forest, reason = _choose_forest(world, state, civ, region)
    crew, soldiers = [], set()
    if reason is None:
        crew, soldiers = _choose_crew(world, state, snapshot, region, enlisted, trips)
        if not crew:
            reason = "no_crew"
    if reason is None:
        hops = forest[0]
        bill = len(crew) * wage * (2 * hops + CUT_TURNS)
        bill += sum(_remaining_bill(e, wage) for e in state.expeditions if e.civ == civ)
        budget = math.floor(_treasury_budget(world, world.civilizations[civ], acc)) * MILLI
        if budget < bill:
            reason = "no_coins"
    if reason is not None:
        return reason, None
    hops, rid, slot = forest
    veterans = []
    if _lane_active(world, "veteran_reintegration"):
        from chronicler.veteran_reintegration import open_record_ids
        vet = open_record_ids(world)
        veterans = [a for a in crew if a in vet]
    exp = Expedition(eid=state.next_eid, civ=civ, home=region, forest=rid, slot=slot, hops=hops,
                     launched_turn=turn, stage="outbound" if hops > 0 else "cutting",
                     crew=list(crew), launched_crew=list(crew), veterans=veterans,
                     soldier_veterans=sorted(soldiers), need=gap)
    state.next_eid += 1
    _note(exp, turn, "launched")
    state.expeditions.append(exp)
    _bump(state, counter)
    _bump(state, "launched_veterans", len(veterans))
    _bump(state, "soldier_veterans", len(soldiers))
    return None, exp


def _plan_launches(world, state, snapshot, sim, acc, enlisted, trips):
    """RS2's need rows first (each region ascending), then, with B3's works on,
    the works' (``_plan_works``): one planner, one set of forests, crews and
    coins, so the works are served only after every RS2 need of the turn."""
    from chronicler import repair_projects as RP
    wants = _wants(world)
    works = _works_wants(world)
    rows: list[NeedRow] = []
    if not wants and not works:
        return rows, 0
    commitments = RP._commitments(world, sim)
    wage = wage_milli()
    turn = world.turn
    for region in sorted(wants):
        civ = _controller(world, region)
        want = wants[region]
        free = RP._free_timber(world, region, commitments, 0.0)
        store = float(state.store.get(region, 0.0))
        homed = [e for e in state.expeditions if e.home == region]
        transit = math.fsum(e.cargo * transit_keep(e.hops) for e in homed)
        gap = max(0.0, want - free - transit)
        row = NeedRow(region=region, civ=civ, want=want, free=free, store=store, in_transit=transit, gap=gap,
                      status="supplied")
        _bump(state, "need_rows")
        _bump(state, "want", want)
        _bump(state, "gap", gap)
        if homed:
            row.status = "expedition"
            row.eid = homed[0].eid
        elif gap >= MIN_GAP:
            reason, exp = _try_launch(world, state, snapshot, civ, region, gap, acc, enlisted, trips, wage, turn)
            if reason is not None:
                row.status, row.reason = "refused", reason
                _bump(state, f"refused_{reason}")
            else:
                row.status, row.eid = "launched", exp.eid
        _bump(state, f"need_{row.status}")
        rows.append(row)
    if works:
        _plan_works(world, state, snapshot, acc, enlisted, trips, works, wants, commitments, wage, turn)
    dropped = max(0, len(rows) - MAX_NEEDS)
    return rows[:MAX_NEEDS], dropped


def _plan_works(world, state, snapshot, acc, enlisted, trips, works, wants, commitments, wage, turn) -> None:
    """B3's works' timber need (``--infrastructure-condition`` in a work mode),
    after every RS2 need row of the turn: per region, the works' one-turn want
    against what the free timber and the cargo on its way leave after RS2's
    want there (RS2 first, in the region as in the planner). A region with a
    live expedition gets no second one (whoever launched it); a gap of at least
    ``MIN_GAP`` launches one under the same checks, crew rule, wages and
    reservation as RS2's (no other labour authority), or records the refusal.
    The rows go to B3's record (``TimberNeed``); PL1's need rows and their
    counters stay RS2's, and the works' launches count in ``launched_works``
    (``launched`` stays RS2's; the veteran and per-expedition counters count
    every expedition). The cargo is delivered to the home region's store,
    which RS2's holds (the works' included) take first."""
    from chronicler import repair_projects as RP
    from chronicler.infrastructure_condition import record_timber_needs
    from chronicler.infrastructure_condition_state import TimberNeed
    out = []
    for region, want, wids in works:
        civ = _controller(world, region)
        free = RP._free_timber(world, region, commitments, 0.0)
        homed = [e for e in state.expeditions if e.home == region]
        transit = math.fsum(e.cargo * transit_keep(e.hops) for e in homed)
        first = float(wants.get(region, 0.0))
        gap = max(0.0, want - max(0.0, free + transit - first))
        row = TimberNeed(region=region, civ=civ, works=list(wids), want=want, rs2_want=first, free=free,
                         in_transit=transit, gap=gap, status="supplied")
        if homed:
            row.status, row.eid = "expedition", homed[0].eid
        elif gap >= MIN_GAP:
            reason, exp = _try_launch(world, state, snapshot, civ, region, gap, acc, enlisted, trips, wage, turn,
                                      counter="launched_works")
            if reason is not None:
                row.status, row.reason = "refused", reason
            else:
                row.status, row.eid = "launched", exp.eid
        out.append(row)
    record_timber_needs(world, out)


def phase10(world, acc, economy_result, agent_bridge):
    """Close the turn's frame (dated to this turn)."""
    state = _state(world)
    t = state._turn
    turn = world.turn
    if t is not None and t.turn == turn and t.finished:
        if t.installed and t.receipt is None:
            t.sim.cancel_paid_work()            # no wealth phase took it: unknown, not zero
        state.receipts, state.ledger = t.receipts, t.ledger
        state.last_settled_turn = turn
        _bump(state, "settled_turns")
    else:
        if t is not None and t.turn == turn and t.installed:
            t.sim.cancel_paid_work()
        state.receipts, state.ledger = None, None
    stores = []
    if t is not None and t.turn == turn:
        for region in sorted(set(t.store_open) | set(state.store)):
            opening = t.store_open.get(region, state.store.get(region, 0.0))
            row = StoreRow(region=region, opening=opening, held=t.held.get(region, 0.0),
                           returned=t.returned.get(region, 0.0), delivered=t.delivered.get(region, 0.0),
                           released=t.released.get(region, 0.0), closing=state.store.get(region, 0.0))
            check_store(row)
            stores.append(row)
            _bump(state, "store_held", row.held)
            _bump(state, "store_returned", row.returned)
        state.needs, state.needs_dropped = list(t.needs), int(t.needs_dropped)
    else:
        stores = [StoreRow(region=r, opening=a, closing=a) for r, a in sorted(state.store.items())]
        state.needs, state.needs_dropped = [], 0
    state.stores = stores
    state.deposits = [d for d in state.deposits if d[0] == turn]
    state.frame_turn = turn
    state._turn = None
    return []


def check_store(row: StoreRow) -> None:
    """One region's store closes this turn (float, relative 1e-9)."""
    expected = math.fsum([row.opening, -row.held, row.returned, row.delivered, -row.released])
    scale = max(1.0, row.opening, row.held, row.delivered)
    if abs(expected - row.closing) > 1e-9 * scale or row.closing < -1e-12:
        raise RuntimeError(f"timber store of region {row.region} does not close")


def _per_expedition(state) -> dict | None:
    """Mean cost and yield of the expeditions that ended so far (None before
    any ended): the control matches ``supply`` per expedition, not in total."""
    c = state.counters
    n = c.get("ended", 0)
    if not n:
        return None
    return {"ended": n, "wages_milli": c.get("ended_wages_milli", 0) / n,
            "person_turns": c.get("ended_person_turns", 0) / n, "farm_labor_away": c.get("ended_away", 0.0) / n,
            "unpaid_turns": c.get("ended_unpaid_turns", 0) / n, "cut": c.get("ended_cut", 0.0) / n,
            "delivered": c.get("ended_delivered", 0.0) / n}


def snapshot_summary(world) -> dict:
    """The completed-turn observation: live and recent expeditions, that turn's
    receipts and per-civ wage ledger (None: no Phase 2, unknown rather than
    zero), its store flows and need rows; never final state."""
    state = _state(world)
    source = world.turn - 1
    fresh = state.frame_turn == source
    return {
        "schema_version": 1, "stage": "PL1", "mode": state.mode, "source_turn": source,
        "units": {"money": "milli_treasury_units", "timber": "goods", "labor": "headcount", "milli": MILLI},
        "expeditions": [e.model_dump() for e in state.expeditions],
        "closed": [e.model_dump() for e in state.closed],
        "store": {str(r): a for r, a in sorted(state.store.items())},
        "receipts": [r.model_dump() for r in state.receipts] if fresh and state.receipts is not None else None,
        "ledger": [r.model_dump() for r in state.ledger] if fresh and state.ledger is not None else None,
        "stores": [r.model_dump() for r in state.stores] if fresh else None,
        "needs": [r.model_dump() for r in state.needs] if fresh else None,
        "needs_dropped": state.needs_dropped if fresh else None,
        "deposits": [list(d) for d in state.deposits if d[0] == source] if fresh else None,
        "per_expedition": _per_expedition(state),
        "prepaid": {str(civ): amount for civ, amount in sorted(state.prepaid.items())},
        "counters": dict(state.counters),
        "parameters": {"crew_cap": CREW_CAP, "max_hops": MAX_HOPS, "cut_turns": CUT_TURNS,
                       "guard_share": GUARD_SHARE, "min_gap": MIN_GAP, "share": SHARE,
                       "wage_milli": wage_milli(), "transit_decay": 1.0 - transit_keep(1)},
    }
