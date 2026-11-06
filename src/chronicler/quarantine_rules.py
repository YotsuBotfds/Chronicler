"""Quarantine rules (connected-world C1): a real, dated trade restriction and its costs.

``--quarantine-mode`` replaces the epidemic model's abstract quarantine
multiplier with a decision whose effect runs through the journeys it closes.

Modes
    ``legacy`` (also: the option omitted) keeps today's rule byte for byte: a
    state in ledger contact with a reported foreign outbreak pays 2 treasury
    and 70-90% of the foreign import pressure on its regions is multiplied
    away (``epidemiology._introduce``). Nothing here runs and the world keeps
    no rules state.

    ``none``: no quarantine decision, no cost, no restriction, no multiplier.

    ``cost_only``: the same decisions and the same declared enforcement cost
    as ``closure``, no restriction and no multiplier (the cost control).

    ``closure``: the decided closures cut trade between the closing polity and
    each polity it closes against: their economy trade routes (and with them
    route income, goods flows, the aggregate trade proxy and the TRADE
    action's choice of partner) and the agent merchants' cross-border edges.
    No multiplier: exposure falls only through the contacts that no longer
    happen, so the decayed contact stock keeps carrying the pressure of the
    journeys made before the closure (the dated lag of a real closure).

Decision (both restricting modes)
    The legacy trigger, with information available at the time: a living
    polity with stability >= 30 and treasury >= the enforcement cost, in
    contact-ledger contact with a region that reported an outbreak this tick
    and that another polity controls, closes against each polity controlling
    such a region (uncontrolled regions have no route to close). Decided in
    Phase 1 of turn T, the closure applies to the journeys of T (Phase 2
    routes, the TRADE action, the agent tick) and is renewed each turn the
    trigger holds; otherwise it lapses at the next decision.

Identity and receipts
    One closure per (closing polity, target polity) pair, identified by an
    id from ``next_closure_id``: stable, checkpointed and never reused; a
    lapse followed by a new closure of the same pair gets a new id. Civ
    identity is the index in ``world.civilizations``. Each turn's receipt
    records the decisions, the enforcement paid, the routes the closure
    removed from the Phase 2 route set (counterfactual minus actual), the
    route income both sides forwent (2 per goods route per side per turn,
    ``simulation.apply_automatic_effects``) and the agent merchant edges cut.

Boundaries (intentional, C1)
    Relief grain shipments and convoys read their own graph
    (``grain_reserves._route_graph``) and stay open; armies, hostages,
    migrants and pilgrims are not restricted. No new random draws: everything
    runs in sorted order.

Migration channel (C1b, ``--quarantine-channels trade,migration``)
    Opt-in under ``closure`` in an agent mode where the native pool owns the
    population (hybrid, demographics-only; shadow is refused: its Python
    population still migrates through climate overflow and famine refugees):
    before each agent tick the closed pairs and the controllers of every
    region are installed natively (``AgentSimulator.set_migration_closure``);
    a decided migration between the two polities of a closed pair, either
    way, is refused at the border and the mover stays home with its household
    (lead decision: refused, not diverted). The tick's receipt (refusals by
    origin, destination and driver, and the refused agents' stable ids) is
    taken right after the tick and attributed to the closure of the polity
    whose border the mover would have entered (else the one it would have
    left); the install is released if the tick raises. Moves already applied
    are never reversed (a native migration is decided and applied in one
    tick, so none is in flight); refugees are not exempt and their refusals
    are counted apart (``FLIGHT_DRIVERS``, and hunger-driven moves in
    ``HUNGER_DRIVERS``). The default ``trade`` keeps C1 byte for byte. Every
    new field is read with ``getattr`` (C1-era pickles lack them).

The state lives inside ``EpidemicState.quarantine_rules`` (omitted while
None) and is always read with ``getattr`` so checkpoints pickled before this
module load unchanged. See ``docs/integration/quarantine-rules.md``.
"""
from __future__ import annotations

import argparse
from typing import Any

from pydantic import BaseModel, Field

#: Choices of ``--quarantine-mode``; the first is the CLI default (option omitted).
QUARANTINE_MODES: tuple[str, ...] = ("legacy", "none", "cost_only", "closure")
#: Modes that keep a rules state on the world (``legacy`` keeps none).
RULE_MODES: tuple[str, ...] = ("none", "cost_only", "closure")
#: Modes that make the quarantine decision and pay its enforcement cost.
DECIDING_MODES: tuple[str, ...] = ("cost_only", "closure")

#: Declared enforcement cost per closing polity per closed turn (treasury,
#: accumulator category ``keep``): border watch and administration. It replaces
#: the legacy flat charge that "stood in for lost commerce"; lost commerce now
#: emerges from the closed routes. Declared, not calibrated.
ENFORCEMENT_COST = 2
#: Route income per goods route per side per turn (``apply_automatic_effects``),
#: used only to state the forgone income in the receipt.
ROUTE_INCOME = 2
#: Journeys a closure restricts in C1.
CHANNELS: tuple[str, ...] = ("trade",)
#: Choices of ``--quarantine-channels`` (C1b); the first is the default (option omitted).
QUARANTINE_CHANNELS: tuple[str, ...] = ("trade", "trade,migration")
#: Agent modes in which the native pool owns the population, so its migrations
#: are the only ones (the migration channel's scope). Shadow is not one: Python
#: still moves its population (``climate.process_migration`` overflow and
#: ``ecology`` famine refugees), which a native closure cannot refuse.
MIGRATION_AGENT_MODES: tuple[str, ...] = ("hybrid", "demographics-only")
#: Migration drivers (``get_migration_driver_stats`` term names) whose refused
#: moves count as flight from war, famine or persecution (a harm reported
#: apart). It excludes the hunger-driven moves of ``HUNGER_DRIVERS``.
FLIGHT_DRIVERS: tuple[str, ...] = ("persecution", "famine_memory", "battle_memory", "conquest_memory",
                                   "persecution_memory", "safety_need")
#: Drivers of hunger-driven moves (food opportunity, material need), a second
#: harm line beside flight.
HUNGER_DRIVERS: tuple[str, ...] = ("opp_food", "material_need")
#: Native methods the migration channel needs (a fresh build).
_MIGRATION_NATIVE: tuple[str, ...] = ("set_migration_closure", "cancel_migration_closure",
                                      "take_migration_closure_receipt")
#: Movements a closure leaves open, with the reason (recorded in every snapshot).
EXEMPT: dict[str, str] = {
    "relief_grain": "public grain shipments and grain convoys use their own route graph",
    "armies": "campaigns are not halted by a quarantine",
    "hostages": "diplomatic custody, not restricted",
    "migrants": "migration closure needs a native input (slice C1b)",
    "pilgrims": "not restricted in C1 (a very small channel)",
}

_HELP = (
    "Quarantine rules (connected-world C1): legacy (default, the same as omitting it, needs "
    "nothing): the abstract import multiplier and a flat charge; none: no quarantine; cost_only: "
    "the same decisions and enforcement cost as closure, nothing restricted; closure: trade "
    "routes and agent merchant edges between a closing polity and each polity with a reported "
    "outbreak it is in contact with are closed while the outbreak is reported, at a declared "
    "enforcement cost, with no import multiplier (relief grain, armies and hostages stay open; "
    "migrants too unless --quarantine-channels trade,migration); none, cost_only and closure "
    "require epidemiology and the contact ledger; saved "
    "on the world (docs/integration/quarantine-rules.md)"
)
_CHANNELS_HELP = (
    "Journeys --quarantine-mode closure restricts (connected-world C1b): trade (default, the same "
    "as omitting it): trade routes and agent merchant edges; trade,migration: also refuses native "
    "migrations between the two polities of each closed pair, either way, while the closure lasts "
    "(refugees included, counted apart; moves already made stay); trade,migration requires "
    "--quarantine-mode closure and an agent mode in which the native pool owns the population "
    "(hybrid or demographics-only; not shadow, whose Python population still migrates); saved on "
    "the world (docs/integration/quarantine-rules.md)"
)


def _is_none(value: object) -> bool:
    return value is None


def _is_false(value: object) -> bool:
    return value is False


# ---------------------------------------------------------------------------
# Persisted state (inside EpidemicState.quarantine_rules)
# ---------------------------------------------------------------------------

class QuarantineClosure(BaseModel):
    """One closed polity pair: ``civ`` closes its border against ``target``."""

    id: int
    civ: int                  # closing civilization (index)
    target: int               # civilization closed against (index)
    opened_turn: int
    last_renewed_turn: int
    cause: str = ""           # event id of the outbreak report that opened it
    channels: list[str] = Field(default_factory=lambda: list(CHANNELS))


class QuarantineReceipt(BaseModel):
    """What the rules did in one turn (``turn``), filled phase by phase."""

    turn: int
    #: (civ, target) pairs decided at this turn's Phase 1 (closed in
    #: ``closure``; declared but not restricted in ``cost_only``).
    decided: list[tuple[int, int]] = Field(default_factory=list)
    #: Polity pairs (low index first) closed at the previous turn's decision
    #: and again at this one, by either side.
    continued: list[tuple[int, int]] = Field(default_factory=list)
    #: Polity pairs (low index first) closed at the previous turn's decision
    #: (``closure``): closed during the agent tick whose deliveries Phase 2 of
    #: this turn reads, whether or not they are still closed now.
    closed_last_tick: list[tuple[int, int]] = Field(default_factory=list)
    opened: list[int] = Field(default_factory=list)    # closure ids opened
    renewed: list[int] = Field(default_factory=list)   # closure ids renewed
    lapsed: list[int] = Field(default_factory=list)    # closure ids that lapsed
    enforcement: list[tuple[int, int]] = Field(default_factory=list)  # (civ, treasury paid)
    #: Phase 2 (``closure``): set once the authoritative route set was built.
    phase2_observed: bool = False
    routes_removed: list[tuple[int, int]] = Field(default_factory=list)  # civ pairs, low index first
    forgone_income: list[tuple[int, int]] = Field(default_factory=list)  # (civ, treasury not earned)
    #: Agent tick (``closure``, agent modes): directed merchant edges cut;
    #: None while no agent merchant graph was built this turn.
    merchant_edges_removed: int | None = Field(default=None, exclude_if=_is_none)
    #: Phase 2 (``closure``, agent modes): merchant deliveries of the previous
    #: agent tick whose origin and destination polities form a pair closed
    #: during that tick (``closed_last_tick``, a closure's last tick included):
    #: journeys that crossed before the closure, or that reached the
    #: destination through a third polity whose borders are open. Controllers
    #: are read at this reading. None while no delivery record was read.
    leaked_deliveries: int | None = Field(default=None, exclude_if=_is_none)
    leaked_quantity: float | None = Field(default=None, exclude_if=_is_none)
    #: Agent tick (C1b migration channel): refused moves as (closure id,
    #: origin region, destination region, driver, persons), sorted; None
    #: while no native migration receipt was read this turn.
    migrants_blocked: list[tuple[int, int, int, str, int]] | None = Field(default=None, exclude_if=_is_none)
    #: Agent tick (C1b): agents refused this tick for the first time in the
    #: run (by stable id); None with ``migrants_blocked``.
    migrants_refused_first: int | None = Field(default=None, exclude_if=_is_none)


class QuarantineTotals(BaseModel):
    """Counters folded from completed receipts (the current one excluded)."""

    receipts: int = 0
    closed_pair_turns: int = 0
    closures_opened: int = 0
    closures_lapsed: int = 0
    enforcement_paid: int = 0
    route_turns_removed: int = 0
    forgone_income: int = 0
    merchant_edges_removed: int = 0
    leaked_deliveries: int = 0
    leaked_quantity: float = 0.0
    #: C1b migration channel only (None otherwise, omitted): refusals summed
    #: over ticks (person-ticks: an agent refused on k ticks counts k times),
    #: of them fleeing war, famine or persecution (``FLIGHT_DRIVERS``) and
    #: hunger-driven (``HUNGER_DRIVERS``), and the distinct agents refused.
    migrants_blocked: int | None = Field(default=None, exclude_if=_is_none)
    migrants_blocked_flight: int | None = Field(default=None, exclude_if=_is_none)
    migrants_blocked_hunger: int | None = Field(default=None, exclude_if=_is_none)
    migrants_refused_persons: int | None = Field(default=None, exclude_if=_is_none)


class QuarantineRulesState(BaseModel):
    """The run's quarantine mode, its open closures and its receipts."""

    mode: str
    #: C1b: closures also refuse migration (``--quarantine-channels
    #: trade,migration``; ``closure`` only). Omitted while False.
    migration: bool = Field(default=False, exclude_if=_is_false)
    #: C1b: stable ids of every agent refused so far, ascending (distinct
    #: persons); None without the migration channel. A rebuilt native pool
    #: (a JSON resume) starts a new id space, so the count is then a lower bound.
    refused_ids: list[int] | None = Field(default=None, exclude_if=_is_none)
    next_closure_id: int = 1
    closures: list[QuarantineClosure] = Field(default_factory=list)
    receipt: QuarantineReceipt | None = Field(default=None, exclude_if=_is_none)
    totals: QuarantineTotals = Field(default_factory=QuarantineTotals)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def rules_of(world: Any) -> QuarantineRulesState | None:
    """The world's rules state, or None (legacy, epidemiology off, mocks).

    ``getattr`` throughout: an epidemic state unpickled from a checkpoint
    written before this module has no ``quarantine_rules`` attribute."""
    from chronicler.epidemiology import EpidemicState
    state = getattr(world, "epidemics", None)
    if not isinstance(state, EpidemicState):
        return None
    rules = getattr(state, "quarantine_rules", None)
    return rules if isinstance(rules, QuarantineRulesState) else None


def effective_mode(world: Any) -> str | None:
    """``legacy``/``none``/``cost_only``/``closure`` with epidemiology on, else None."""
    from chronicler.epidemiology import epidemiology_enabled
    if not epidemiology_enabled(world):
        return None
    rules = rules_of(world)
    return "legacy" if rules is None else rules.mode


def _migration(rules: Any) -> bool:
    """``rules.migration``; False on a rules state pickled before C1b."""
    return getattr(rules, "migration", False) is True


def _refusals(receipt: Any) -> list | None:
    """``receipt.migrants_blocked``; None on a receipt pickled before C1b."""
    return getattr(receipt, "migrants_blocked", None)


def channels_of(rules: QuarantineRulesState | None) -> list[str]:
    """Journeys the rules restrict: none outside ``closure``."""
    if rules is None or rules.mode != "closure":
        return []
    return list(CHANNELS) + (["migration"] if _migration(rules) else [])


def migration_closure_on(world: Any) -> bool:
    """Whether this world's closures also refuse migration (C1b)."""
    rules = rules_of(world)
    return rules is not None and rules.mode == "closure" and _migration(rules)


def closed_pairs(world: Any) -> set[tuple[str, str]]:
    """Civ-name pairs (sorted) whose trade is closed now (``closure`` only)."""
    rules = rules_of(world)
    if rules is None or rules.mode != "closure" or not rules.closures:
        return set()
    civs = world.civilizations
    pairs = set()
    for closure in rules.closures:
        if 0 <= closure.civ < len(civs) and 0 <= closure.target < len(civs):
            a, b = civs[closure.civ].name, civs[closure.target].name
            if a != b:
                pairs.add((a, b) if a < b else (b, a))
    return pairs


def _current_receipt(world: Any, rules: QuarantineRulesState) -> QuarantineReceipt | None:
    receipt = rules.receipt
    return receipt if receipt is not None and receipt.turn == world.turn else None


# ---------------------------------------------------------------------------
# Restriction hooks
# ---------------------------------------------------------------------------

def filter_closed_routes(world: Any, routes: set[tuple[str, str]], *, emit_events: bool = False
                         ) -> set[tuple[str, str]]:
    """``resources._compute_active_trade_routes`` post-filter: drop closed pairs.

    Removes every kind of route (adjacency, two-hop, techniques-extended,
    federation) between closed pairs; routes inside a polity and other pairs
    are untouched. At the authoritative Phase 2 call (``emit_events``) the
    removed routes and the route income both sides forgo are recorded in this
    turn's receipt (an embargoed pair has no route to remove, so its income is
    never attributed to the quarantine)."""
    pairs = closed_pairs(world)
    if not pairs:
        if emit_events:
            _record_phase2(world, [])
        return routes
    removed = sorted(routes & pairs)
    if emit_events:
        _record_phase2(world, removed)
    return routes - pairs


def _record_phase2(world: Any, removed: list[tuple[str, str]]) -> None:
    rules = rules_of(world)
    if rules is None or rules.mode != "closure":
        return
    receipt = _current_receipt(world, rules)
    if receipt is None:
        return
    from chronicler.economy import filter_goods_trade_routes
    index = world.civ_index_map
    receipt.routes_removed = sorted(
        tuple(sorted((index[a], index[b]))) for a, b in removed if a in index and b in index)
    forgone: dict[int, int] = {}
    for a, b in filter_goods_trade_routes(world, list(removed)):
        for name in (a, b):
            if name in index:
                forgone[index[name]] = forgone.get(index[name], 0) + ROUTE_INCOME
    receipt.forgone_income = sorted(forgone.items())
    receipt.phase2_observed = True


def merchant_route_graph(world: Any, batch):
    """Agent merchant graph: cut the cross-border edges of closed pairs (both directions).

    Called only at the agent-tick sites of ``agent_bridge``; relief grain
    shipments and convoys build their own graph and stay open. Native
    merchants already replan or unwind (``RETURNED``) when an edge vanishes.
    Unchanged (the same batch object) without a closure."""
    rules = rules_of(world)
    if rules is None or rules.mode != "closure":
        return batch
    pairs = closed_pairs(world)
    receipt = _current_receipt(world, rules)
    if not pairs or batch.num_rows == 0:
        if receipt is not None:
            receipt.merchant_edges_removed = 0
        return batch
    import pyarrow as pa
    from chronicler.columnar import pylist
    regions = world.regions
    n = len(regions)

    def owner(j: int) -> str | None:
        return regions[j].controller if 0 <= j < n else None

    keep = []
    for a, b in zip(pylist(batch.column("from_region")), pylist(batch.column("to_region"))):
        ca, cb = owner(int(a)), owner(int(b))
        closed = ca is not None and cb is not None and ca != cb and (
            (ca, cb) if ca < cb else (cb, ca)) in pairs
        keep.append(not closed)
    removed = keep.count(False)
    if receipt is not None:
        receipt.merchant_edges_removed = removed
    if not removed:
        return batch
    return batch.filter(pa.array(keep, type=pa.bool_()))


def observe_deliveries(world: Any, rows) -> None:
    """Phase 2 (agent modes): count deliveries of the last tick across closed pairs.

    ``rows`` are the native ``(source_region, dest_region, qty)`` arrival
    records the contact ledger reads. A pair counts when it was closed during
    the tick that made the deliveries (``closed_last_tick``), including the
    last tick of a closure that has since lapsed."""
    rules = rules_of(world)
    if rules is None or rules.mode != "closure":
        return
    receipt = _current_receipt(world, rules)
    if receipt is None:
        return
    civs = world.civilizations
    pairs = set()
    for x, y in receipt.closed_last_tick:
        if 0 <= x < len(civs) and 0 <= y < len(civs):
            a, b = civs[x].name, civs[y].name
            pairs.add((a, b) if a < b else (b, a))
    regions = world.regions
    n = len(regions)
    count, quantity = 0, 0.0
    for src, dst, qty in rows:
        src, dst = int(src), int(dst)
        if not (0 <= src < n and 0 <= dst < n) or src == dst or qty <= 0:
            continue
        ca, cb = regions[src].controller, regions[dst].controller
        if ca is None or cb is None or ca == cb:
            continue
        if ((ca, cb) if ca < cb else (cb, ca)) in pairs:
            count += 1
            quantity += float(qty)
    receipt.leaked_deliveries = count
    receipt.leaked_quantity = round(quantity, 6)


def install_migration_closure(world: Any, sim: Any) -> tuple | None:
    """Before the agent tick (C1b): install this tick's closed pairs natively.

    Called at the two agent-tick sites of ``agent_bridge``; nothing without
    the migration channel. Every tick of a run with the channel installs a
    closure (no pair when no closure is open), so each tick leaves a receipt.
    Any closure an earlier, failed tick left pending is dropped first. Returns
    the token ``take_migration_receipt`` attributes the receipt with: (turn,
    controller index per region, {(civ, target): closure id})."""
    if not migration_closure_on(world):
        return None
    if not all(callable(getattr(sim, name, None)) for name in _MIGRATION_NATIVE):
        raise RuntimeError("--quarantine-channels trade,migration requires a fresh native build "
                           "with the migration closure")
    rules = rules_of(world)
    index = world.civ_index_map
    region_civ = [index.get(r.controller, 255) if r.controller is not None else 255 for r in world.regions]
    region_civ = [c if isinstance(c, int) and 0 <= c < 255 else 255 for c in region_civ]
    civs = world.civilizations
    by_pair: dict[tuple[int, int], int] = {}
    pairs: set[tuple[int, int]] = set()
    for closure in rules.closures:
        a, b = closure.civ, closure.target
        if 0 <= a < len(civs) and 0 <= b < len(civs) and a != b and max(a, b) < 255:
            by_pair[(a, b)] = closure.id
            pairs.add((min(a, b), max(a, b)))
    sim.cancel_migration_closure()
    sim.set_migration_closure(world.turn, region_civ, sorted(pairs))
    return (world.turn, region_civ, by_pair)


def take_migration_receipt(world: Any, sim: Any, token: tuple | None) -> None:
    """After a successful agent tick (C1b): read the tick's refused moves once.

    Each refused move (origin ruled by polity X, destination by Y, read when
    the closure was installed) is attributed to Y's closure against X, the
    border it would have entered, else to X's closure against Y. The rows go
    to this turn's receipt; the persons fold into the totals at the next
    decision. Nothing without a token."""
    if token is None:
        return
    turn, region_civ, by_pair = token
    got = sim.take_migration_closure_receipt(turn)
    if got is None:
        sim.cancel_migration_closure()
        raise RuntimeError("native migration closure receipt missing for this turn")
    rows, ids = got
    ids = [int(i) for i in ids]
    if len(set(ids)) != len(ids):
        raise RuntimeError("native migration closure receipt repeats an agent id")
    rules = rules_of(world)
    receipt = _current_receipt(world, rules) if rules is not None else None
    if receipt is None or receipt.turn != turn:
        raise RuntimeError("no quarantine receipt for the migration closure's turn")
    out: list[tuple[int, int, int, str, int]] = []
    n = len(region_civ)
    for frm, to, driver, persons in rows:
        frm, to, persons = int(frm), int(to), int(persons)
        if not (0 <= frm < n and 0 <= to < n) or persons <= 0:
            raise RuntimeError(f"malformed native migration closure row {(frm, to, driver, persons)!r}")
        x, y = region_civ[frm], region_civ[to]
        closure_id = by_pair.get((y, x), by_pair.get((x, y)))
        if closure_id is None:
            raise RuntimeError(f"native migration closure refused an open crossing {frm}->{to}")
        out.append((closure_id, frm, to, str(driver), persons))
    if sum(r[4] for r in out) != len(ids):
        raise RuntimeError("native migration closure rows and refused ids disagree")
    known = set(getattr(rules, "refused_ids", None) or [])
    receipt.migrants_blocked = sorted(out)
    receipt.migrants_refused_first = sum(1 for i in ids if i not in known)
    rules.refused_ids = sorted(known.union(ids))


def migration_closure_tick(world: Any, sim: Any, tick):
    """Run ``tick()`` (the native agent tick) inside this turn's migration closure.

    Installs the closure first and takes its receipt after a successful tick
    (C1b); whatever happens, nothing stays pending natively afterwards (a
    tick that raises leaves no closure or receipt behind). Without the
    migration channel it only calls ``tick()``."""
    token = install_migration_closure(world, sim)
    if token is None:
        return tick()
    try:
        result = tick()
        take_migration_receipt(world, sim, token)
    finally:
        sim.cancel_migration_closure()
    return result


def blocked_counts(rows) -> tuple[int, int, int]:
    """(persons refused, of them fleeing war, famine or persecution, of them
    hunger-driven) of receipt rows."""
    persons = sum(r[4] for r in rows)
    flight = sum(r[4] for r in rows if r[3] in FLIGHT_DRIVERS)
    hunger = sum(r[4] for r in rows if r[3] in HUNGER_DRIVERS)
    return persons, flight, hunger


# ---------------------------------------------------------------------------
# The decision (Phase 1, end of the epidemic tick)
# ---------------------------------------------------------------------------

def _fold(totals: QuarantineTotals, receipt: QuarantineReceipt) -> None:
    totals.receipts += 1
    totals.closed_pair_turns += len(receipt.decided)
    totals.closures_opened += len(receipt.opened)
    totals.closures_lapsed += len(receipt.lapsed)
    totals.enforcement_paid += sum(v for _, v in receipt.enforcement)
    totals.route_turns_removed += len(receipt.routes_removed)
    totals.forgone_income += sum(v for _, v in receipt.forgone_income)
    totals.merchant_edges_removed += receipt.merchant_edges_removed or 0
    totals.leaked_deliveries += receipt.leaked_deliveries or 0
    totals.leaked_quantity = round(totals.leaked_quantity + (receipt.leaked_quantity or 0.0), 6)
    rows = _refusals(receipt)
    if rows is not None:
        persons, flight, hunger = blocked_counts(rows)
        totals.migrants_blocked = (getattr(totals, "migrants_blocked", None) or 0) + persons
        totals.migrants_blocked_flight = (getattr(totals, "migrants_blocked_flight", None) or 0) + flight
        totals.migrants_blocked_hunger = (getattr(totals, "migrants_blocked_hunger", None) or 0) + hunger
        totals.migrants_refused_persons = ((getattr(totals, "migrants_refused_persons", None) or 0)
                                           + (getattr(receipt, "migrants_refused_first", None) or 0))


def decide(world: Any, state: Any, rules: QuarantineRulesState, reports: dict, acc) -> list:
    """Targeted closures for this turn's journeys; sets ``state.quarantine``.

    ``reports`` are this tick's outbreak reports by (region, pathogen). Uses
    only information of this tick: the reports and the contact ledger."""
    from chronicler import contact_ledger as cl
    from chronicler import provenance
    from chronicler.epidemiology import PATHOGENS, QUARANTINE_MIN_STABILITY, _report_cause
    from chronicler.models import Event

    turn = world.turn
    previous = rules.receipt
    if previous is not None:
        _fold(rules.totals, previous)
    receipt = rules.receipt = QuarantineReceipt(turn=turn)
    events: list = []
    regions = world.regions
    civs = world.civilizations
    index = world.civ_index_map
    before = {(c.civ, c.target): c for c in rules.closures}
    decided: dict[tuple[int, int], str] = {}   # (civ, target) -> cause
    closing: list[int] = []
    if rules.mode in DECIDING_MODES and cl.ledger_enabled(world):
        sick = sorted(reports)
        neighbors = world.contact_ledger.neighbors()
        for idx, civ in enumerate(civs):
            if not civ.regions:
                continue
            own = {j for j, r in enumerate(regions) if r.controller == civ.name}
            targets: dict[int, tuple[int, int]] = {}
            for key in sick:
                j = key[0]
                ctrl = regions[j].controller
                if ctrl == civ.name or not any(t in own for t in neighbors.get(j, ())):
                    continue
                t_idx = index.get(ctrl) if ctrl is not None else None
                if t_idx is not None and t_idx != idx:
                    targets.setdefault(t_idx, key)
            if not targets:
                continue
            if civ.stability < QUARANTINE_MIN_STABILITY or civ.treasury < ENFORCEMENT_COST:
                continue
            closing.append(idx)
            receipt.enforcement.append((idx, ENFORCEMENT_COST))
            if acc is not None:
                acc.add(idx, civ, "treasury", -ENFORCEMENT_COST, "keep")
            else:
                civ.treasury -= ENFORCEMENT_COST
            first = min(targets.values())
            for t_idx, key in targets.items():
                decided[(idx, t_idx)] = _report_cause(world, reports[key]) or ""
            names = [civs[t].name for t in sorted(targets)]
            listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
            label = PATHOGENS[first[1]].label
            where = regions[first[0]].name
            if rules.mode == "closure" and _migration(rules):
                text = (f"{civ.name} closes its borders to trade and migration with {listed} against "
                        f"{label} raging in {where}.")
            elif rules.mode == "closure":
                text = f"{civ.name} closes its borders to trade with {listed} against {label} raging in {where}."
            else:
                text = (f"{civ.name} declares a quarantine against {listed} for {label} raging in "
                        f"{where}, paying for border watch but closing no route.")
            seat = civ.capital_region if civ.capital_region in civ.regions else civ.regions[0]
            ev = Event(turn=turn, event_type="quarantine", actors=[civ.name],
                       description=text, importance=4, region=seat)
            provenance.cite(ev, _report_cause(world, reports[first]))
            events.append(ev)
    kept: list[QuarantineClosure] = []
    for pair in sorted(decided):
        closure = before.get(pair)
        if closure is None:
            closure = QuarantineClosure(id=rules.next_closure_id, civ=pair[0], target=pair[1],
                                        opened_turn=turn, last_renewed_turn=turn, cause=decided[pair])
            if _migration(rules):
                closure.channels = channels_of(rules)
            rules.next_closure_id += 1
            receipt.opened.append(closure.id)
        else:
            closure.last_renewed_turn = turn
            receipt.renewed.append(closure.id)
        kept.append(closure)
    receipt.lapsed = sorted(c.id for pair, c in before.items() if pair not in decided)
    receipt.opened.sort()
    receipt.renewed.sort()
    receipt.decided = sorted(decided)
    if previous is not None and previous.turn == turn - 1:
        def undirected(pairs):
            return {(min(p), max(p)) for p in pairs}
        receipt.continued = sorted(undirected(previous.decided) & undirected(decided))
        if rules.mode == "closure":
            receipt.closed_last_tick = sorted(undirected(previous.decided))
    changed = set(before) != set(decided)
    rules.closures = sorted(kept, key=lambda c: c.id)
    state.quarantine = closing
    if changed and rules.mode == "closure" and hasattr(world, "invalidate_trade_route_cache"):
        # Routes read later this turn (Phase 2, actions) must see the new closures.
        world.invalidate_trade_route_cache()
    return events


# ---------------------------------------------------------------------------
# Snapshot and metrics
# ---------------------------------------------------------------------------

def snapshot_summary(world: Any) -> dict | None:
    """``history[n].epidemics.quarantine_rules`` (None in legacy mode)."""
    rules = rules_of(world)
    if rules is None:
        return None
    civs = world.civilizations

    def name(i: int) -> str:
        return civs[i].name if 0 <= i < len(civs) else f"civ {i}"

    receipt = rules.receipt
    totals = rules.totals.model_copy()
    if receipt is not None:
        _fold(totals, receipt)
    out: dict[str, Any] = {
        "schema_version": 1,
        "mode": rules.mode,
        "channels": channels_of(rules),
        "exempt": sorted(k for k in EXEMPT if not (k == "migrants" and migration_closure_on(world))),
        "import_multiplier": False,
        "enforcement_cost": ENFORCEMENT_COST if rules.mode in DECIDING_MODES else 0,
        "closures": [
            {"id": c.id, "civ": name(c.civ), "target": name(c.target), "opened_turn": c.opened_turn,
             "last_renewed_turn": c.last_renewed_turn, "cause": c.cause}
            for c in rules.closures
        ],
        "receipt": None,
        "totals": totals.model_dump(),
    }
    if receipt is not None:
        out["receipt"] = {
            "turn": receipt.turn,
            "decided": [[name(a), name(b)] for a, b in receipt.decided],
            "continued": [[name(a), name(b)] for a, b in receipt.continued],
            "closed_last_tick": [[name(a), name(b)] for a, b in receipt.closed_last_tick],
            "opened": list(receipt.opened),
            "renewed": list(receipt.renewed),
            "lapsed": list(receipt.lapsed),
            "enforcement": {name(c): v for c, v in receipt.enforcement},
            "phase2_observed": receipt.phase2_observed,
            "routes_removed": [[name(a), name(b)] for a, b in receipt.routes_removed],
            "forgone_income": {name(c): v for c, v in receipt.forgone_income},
            "merchant_edges_removed": receipt.merchant_edges_removed,
            "leaked_deliveries": receipt.leaked_deliveries,
            "leaked_quantity": receipt.leaked_quantity,
        }
        if _migration(rules):
            # C1b: refused moves (None: no native migration receipt read yet this turn).
            rows = _refusals(receipt)
            regions = world.regions

            def region(i: int) -> str:
                return regions[i].name if 0 <= i < len(regions) else f"region {i}"

            persons, flight, hunger = blocked_counts(rows) if rows is not None else (None, None, None)
            out["receipt"]["migrants_blocked"] = persons
            out["receipt"]["migrants_blocked_flight"] = flight
            out["receipt"]["migrants_blocked_hunger"] = hunger
            out["receipt"]["migrants_refused_first"] = (
                None if rows is None else getattr(receipt, "migrants_refused_first", None) or 0)
            out["receipt"]["migration_refusals"] = None if rows is None else [
                {"closure": c, "from": region(a), "to": region(b), "driver": d, "persons": p}
                for c, a, b, d, p in rows]
    return out


def extract_metrics(series: list[dict]) -> dict | None:
    """Per-run closure counters from ``history[n].epidemics`` (None in legacy runs)."""
    records = [s.get("quarantine_rules") for s in series if isinstance(s, dict)]
    records = [r for r in records if isinstance(r, dict)]
    if not records:
        return None
    last = records[-1]
    # Turns with an open closure (closure) or a declared quarantine (cost_only);
    # likewise closed_pair_turns counts declared pairs under cost_only.
    turns_with_decision = sum(1 for r in records if r.get("closures"))
    return {"mode": last.get("mode"), "turns_with_decision": turns_with_decision, **last.get("totals", {})}


# ---------------------------------------------------------------------------
# CLI, configuration and resume
# ---------------------------------------------------------------------------

def add_quarantine_arguments(parser: argparse.ArgumentParser, *, forwarding: bool = False) -> None:
    prefix = "Forward --quarantine-mode to every run. " if forwarding else ""
    parser.add_argument("--quarantine-mode", choices=QUARANTINE_MODES, default=None, help=prefix + _HELP)
    prefix = "Forward --quarantine-channels to every run. " if forwarding else ""
    parser.add_argument("--quarantine-channels", choices=QUARANTINE_CHANNELS, default=None,
                        help=prefix + _CHANNELS_HELP)


def quarantine_arguments(args: Any) -> list[str]:
    """Forward an explicit mode (``legacy`` included) and channels to child runs."""
    flags = []
    value = getattr(args, "quarantine_mode", None)
    if value is not None:
        if value not in QUARANTINE_MODES:
            raise ValueError(f"quarantine_mode must be one of {QUARANTINE_MODES}")
        flags.append(f"--quarantine-mode={value}")
    channels = getattr(args, "quarantine_channels", None)
    if channels is not None:
        if channels not in QUARANTINE_CHANNELS:
            raise ValueError(f"quarantine_channels must be one of {QUARANTINE_CHANNELS}")
        flags.append(f"--quarantine-channels={channels}")
    return flags


def saved_rules_error(world: Any, switch: str) -> str | None:
    """Why ``switch`` (--no-epidemiology, --no-contact-ledger) cannot be applied:
    the world carries saved quarantine rules that need it (a JSON resume is
    refused as an exact resume is). None when it has none."""
    rules = rules_of(world)
    if rules is None:
        return None
    return (f"{switch} conflicts with this world's saved quarantine rules (--quarantine-mode "
            f"{rules.mode}), which need epidemiology and the contact ledger; a world keeps its "
            "quarantine rules for its whole run")


def _requirement_error(world: Any) -> str | None:
    from chronicler.contact_ledger import ledger_enabled
    from chronicler.epidemiology import epidemiology_enabled
    if epidemiology_enabled(world) and ledger_enabled(world):
        return None
    return ("--quarantine-mode requires epidemiology and the contact ledger (on by default for new "
            "worlds); it cannot run with --no-epidemiology or --no-contact-ledger")


def configure_quarantine(world: Any, args: Any, *, agent_mode: str | None = None) -> None:
    """Apply an explicit ``--quarantine-mode`` after epidemiology and the ledger are set.

    Valid in every agent mode. Omitted keeps the world's saved rules (or the
    legacy rule). An explicit ``legacy`` is the option omitted: it installs
    nothing and needs neither epidemiology nor the ledger (so it can be
    forwarded to an epidemics-off arm); it only conflicts with saved rules of
    another mode. Any other mode needs epidemiology and the ledger. A world
    whose epidemic model already ran keeps its rules for the rest of its run:
    a different mode is refused (the saved mode of a world without rules is
    ``legacy``); a world whose epidemics never ticked (new, or supplied
    before its first turn) takes the requested mode. ``--quarantine-channels``
    follows the same rules (``_configure_channels``)."""
    channels = getattr(args, "quarantine_channels", None)
    if channels is not None and channels not in QUARANTINE_CHANNELS:
        raise ValueError(f"quarantine_channels must be one of {QUARANTINE_CHANNELS}")
    _configure_mode(world, getattr(args, "quarantine_mode", None))
    _configure_channels(world, channels, agent_mode)


def _configure_mode(world: Any, mode: str | None) -> None:
    if mode is None:
        return
    if mode not in QUARANTINE_MODES:
        raise ValueError(f"quarantine_mode must be one of {QUARANTINE_MODES}")
    if mode == "legacy":
        rules = rules_of(world)
        if rules is not None and world.epidemics.last_tick_turn >= 0:
            raise ValueError(f"--quarantine-mode legacy conflicts with the saved world (saved: "
                             f"{rules.mode}); a world keeps its quarantine rules for its whole run")
        if rules is not None:
            world.epidemics.quarantine_rules = None
        return
    problem = _requirement_error(world)
    if problem is not None:
        raise ValueError(problem)
    state = world.epidemics
    rules = getattr(state, "quarantine_rules", None)
    saved = rules.mode if rules is not None else "legacy"
    if saved == mode:
        return
    if state.last_tick_turn >= 0:
        raise ValueError(f"--quarantine-mode {mode} conflicts with the saved world (saved: {saved}); "
                         "a world keeps its quarantine rules for its whole run")
    state.quarantine_rules = None if mode == "legacy" else QuarantineRulesState(mode=mode)


def _channels_name(migration: bool) -> str:
    return QUARANTINE_CHANNELS[1] if migration else QUARANTINE_CHANNELS[0]


def _configure_channels(world: Any, channels: str | None, agent_mode: str | None) -> None:
    """``--quarantine-channels`` after the mode. An explicit ``trade`` is the
    option omitted (it needs nothing) unless the world already closes
    migration. ``trade,migration`` needs ``closure`` and an agent mode with
    native migration; a world whose epidemic model already ran keeps its
    channels for the rest of its run, and saved migration closure refuses a
    continuation in ``--agents off``."""
    rules = rules_of(world)
    saved = rules is not None and rules.mode == "closure" and _migration(rules)
    want = saved if channels is None else channels == QUARANTINE_CHANNELS[1]
    if want and (rules is None or rules.mode != "closure"):
        raise ValueError("--quarantine-channels trade,migration requires --quarantine-mode closure")
    if want and agent_mode not in MIGRATION_AGENT_MODES and not (channels is None and agent_mode is None):
        what = ("this world's saved quarantine rules close migration (--quarantine-channels "
                "trade,migration), which needs" if channels is None
                else "--quarantine-channels trade,migration requires")
        raise ValueError(f"{what} an agent mode in which the native pool owns the population (--agents "
                         f"hybrid or demographics-only), not --agents {agent_mode}"
                         + (": shadow's Python population still migrates (climate overflow, famine "
                            "refugees), which the native closure cannot refuse" if agent_mode == "shadow" else ""))
    if want == saved:
        return
    if world.epidemics.last_tick_turn >= 0:
        raise ValueError(f"--quarantine-channels {channels} conflicts with the saved world (saved: "
                         f"{_channels_name(saved)}); a world keeps its quarantine rules for its whole run")
    rules.migration = want
    rules.refused_ids = [] if want else None
    for name in ("migrants_blocked", "migrants_blocked_flight", "migrants_blocked_hunger",
                 "migrants_refused_persons"):
        setattr(rules.totals, name, 0 if want else None)


def quarantine_resume_conflicts(world: Any, args: Any, recorded: dict) -> list[str]:
    """An explicit mode an exact resume of ``world`` cannot honour.

    A mode the checkpoint recorded is left to the generic adoption in
    ``main``; otherwise the retained world state is authoritative. Never
    changes ``world`` or ``args``."""
    conflicts = []
    given = getattr(args, "quarantine_mode", None)
    if given is not None and "quarantine_mode" not in recorded:
        saved = effective_mode(world)
        if saved is None:
            if given != "legacy":   # an explicit legacy is the option omitted
                conflicts.append(f"--quarantine-mode {given!r} conflicts with the checkpoint (saved: epidemiology off)")
        elif given != saved:
            conflicts.append(f"--quarantine-mode {given!r} conflicts with the checkpoint (saved: {saved!r})")
    channels = getattr(args, "quarantine_channels", None)
    if channels is not None and "quarantine_channels" not in recorded:
        saved_channels = _channels_name(migration_closure_on(world))
        if channels != saved_channels:
            conflicts.append(f"--quarantine-channels {channels!r} conflicts with the checkpoint "
                             f"(saved: {saved_channels!r})")
    return conflicts
