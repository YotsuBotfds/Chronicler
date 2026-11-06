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
    migrants and pilgrims are not restricted (migration closure is the later
    native slice C1b). No new random draws: everything runs in sorted order.

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
    "enforcement cost, with no import multiplier (relief grain, armies, hostages and migrants "
    "stay open); none, cost_only and closure require epidemiology and the contact ledger; saved "
    "on the world (docs/integration/quarantine-rules.md)"
)


def _is_none(value: object) -> bool:
    return value is None


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


class QuarantineRulesState(BaseModel):
    """The run's quarantine mode, its open closures and its receipts."""

    mode: str
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
            if rules.mode == "closure":
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
        "channels": list(CHANNELS) if rules.mode == "closure" else [],
        "exempt": sorted(EXEMPT),
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


def quarantine_arguments(args: Any) -> list[str]:
    """Forward an explicit mode (``legacy`` included) to child runs."""
    value = getattr(args, "quarantine_mode", None)
    if value is None:
        return []
    if value not in QUARANTINE_MODES:
        raise ValueError(f"quarantine_mode must be one of {QUARANTINE_MODES}")
    return [f"--quarantine-mode={value}"]


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
    before its first turn) takes the requested mode."""
    mode = getattr(args, "quarantine_mode", None)
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


def quarantine_resume_conflicts(world: Any, args: Any, recorded: dict) -> list[str]:
    """An explicit mode an exact resume of ``world`` cannot honour.

    A mode the checkpoint recorded is left to the generic adoption in
    ``main``; otherwise the retained world state is authoritative. Never
    changes ``world`` or ``args``."""
    given = getattr(args, "quarantine_mode", None)
    if given is None or "quarantine_mode" in recorded:
        return []
    saved = effective_mode(world)
    if saved is None:
        if given == "legacy":
            return []   # the option omitted: nothing to honour
        return [f"--quarantine-mode {given!r} conflicts with the checkpoint (saved: epidemiology off)"]
    if given != saved:
        return [f"--quarantine-mode {given!r} conflicts with the checkpoint (saved: {saved!r})"]
    return []
