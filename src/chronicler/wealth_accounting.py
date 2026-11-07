"""Observation-only wealth ledger (A1, ``--wealth-accounting``, default off).

Requires ``--agents hybrid``. Design: the connected-world A1-A2 income and
wealth audit (section 3.2, slice 1; on the lead's branch as
``docs/superpowers/audits/connected-world/audit-a1-a2-income-wealth.md``);
integration page ``docs/integration/wealth-accounting.md``.

Why. Agent ``wealth`` (native ``AgentPool.wealth``, f32) is the one spendable
balance every payer debits, but most of what enters it is created by the
native model (occupational income) and most of what leaves it is destroyed by
it (the 2% decay), and no check covers it as a whole. This package observes it:
per turn and per region it reads the balance at the Phase 2 opening and after
every payer of Phase 10, collects each package's committed receipts as typed
flows, and writes the identity

    close - open = (typed_in - typed_out) / 1000 + native_model

per region (with the balances of people who moved carried across regions as
``migration``) and for the world, where ``native_model`` is the explicitly
labelled residual of the native model flows it does not itemize in slice 1:
occupational income net of withheld shares, decay, the wealth ceiling, birth
endowments, estates without heirs and inheritance overflow.

It never writes wealth, a treasury or any package's state, draws no random
number and registers no agent-tick hook (so the post-tick snapshot hand-over
is unchanged): with the switch on, every output except this package's record
equals the switch off.

Seams (Python only; no edit to any payer):

1. ``prepare_phase2`` (the Phase 2 agent snapshot, before any Phase 2 writer):
   the opening, checked bit for bit against the previous closing (a SHA-256
   of each person's f32 wealth bits and region, in id order) - the
   no-hidden-writer check. Counter baselines for the packages whose per-turn
   totals are read as counter deltas are taken here.
2. ``phase10`` (the last livelihoods hook, after every payer, granary
   procurement included): typed flows from the packages' committed receipts
   and ledgers (L6a wages and RS1 stipends from the firm receipts, RS2 and PL1
   wages and charges, PL3 granary wages and sinks, L6b purchases and
   procurement credits, RS4 remittances, L7 fares and assistance, domestic
   credit), each with its own closure re-checked; the shared paid-work
   receipt (``livelihoods.paid_work_receipt``) attributed row by row to the
   package that installed it, which splits PL3's withheld income into granary
   and workshop crews (recorded limit RL7); the treasury side (wages paid from
   treasuries and firm cash beside the treasury tax created this turn, and the
   clergy tithe's potential and its approximate collected part); then the
   closing. Every payer path (module, function, writer or routing helper,
   purpose and batch, with its number of call sites) must be in
   ``WEALTH_WRITERS``, and every other reference to a writer's name in
   ``WEALTH_WRITER_REFERENCES`` (a test walks ``src/`` and fails closed), so
   ``typed_complete`` means "every known channel of an active package had
   this turn's record".
3. ``on_pool_reset``: a rebuilt pool drops the closing with a dated record;
   the next opening is unchecked (balances are never carried across pools).

Records (``snapshot.livelihoods.wealth_accounting``, stage ``A1``, dated by
``source_turn``): the completed turn's ``frame`` (None when that turn was not
observed: unknown, not zero), lifetime totals, counters, a dated log and the
labels. Unit conventions: balances in wealth units, typed flows in milli-units,
treasury amounts in whole treasury units.
"""
from __future__ import annotations

import copy
import hashlib
import math
from importlib import import_module

from chronicler.wealth_accounting_state import (
    CHANNEL_NAMES, CHANNELS, COUNTERS, LIFETIME, MAX_CONTINUITY_REGIONS, MAX_LOG, WITHHELD_PACKAGES, Closing, LedgerRecord,
    WealthAccountingState,
)

MILLI = 1000
STAGE = "A1"
#: Relative tolerance of a float comparison (sums of f32 receipt values).
REL_TOL = 1e-9

#: What each derived quantity means (copied into every record).
LABELS: dict[str, str] = {
    "native_model": (
        "native model flows, not itemized in slice 1: occupational income net of withheld shares, decay, "
        "the wealth ceiling, birth endowments, estates without heirs and inheritance overflow, plus the "
        "f32 rounding of typed transfers; per region it ALSO holds every unlocated typed flow (the frame's "
        "unlocated_in_milli/unlocated_out_milli: granary procurement, L7 fares beyond the kept sample, "
        "domestic credit, wages of PL3 receipts dropped by its row cap) and typed flows a package recorded "
        "in another region than the payee's opening region, so a region's residual is not model-only "
        "while unlocated flows are non-zero"),
    "typed": "conserved or declared transfers through keyed native wealth transfers (payer debited)",
    "typed_complete": ("every known channel of an active package had this turn's record (WEALTH_WRITERS "
                       "registers every payer path - module, function, writer or router, purpose and batch - "
                       "with its call sites; a test fails on an unregistered one)"),
    "migration": "closing balances of people whose region changed during the turn (they carry them)",
    "withheld": ("ordinary income the native wealth phase withheld for paid work, and farm income L6b "
                 "replaced by sales (no money moves); L5 learning attendance, academy teaching and rural "
                 "health work also withhold income: registered, not itemized in slice 1 (in native_model)"),
    "treasury_tax": "the 5% treasury tax on merchant wealth: credited to the treasury, debited from nobody",
    "tithe": ("potential: TITHE_RATE x the economy's tithe base per civilization with regions, an upper "
              "bound, NOT created money; at_threshold_after_tick: the part of civilizations whose clergy "
              "influence is at the faction threshold after the faction tick (approximate: the tick tests the "
              "threshold before normalizing influence); collected is None (not observed in slice 1). The "
              "collected tithe is credited to the treasury and debited from nobody"),
}

#: (package, counter) read as per-turn deltas between the opening and Phase 10.
_BASELINES: tuple[tuple[str, str], ...] = (
    ("relocation_costs", "fare_debited_milli"), ("relocation_costs", "fare_residual_milli"),
    ("relocation_costs", "fare_due_milli"), ("relocation_costs", "assistance_granted_milli"),
    ("relocation_costs", "fare_not_charged_milli"), ("relocation_costs", "travel_sink_milli"),
    ("workshop_payroll", "income_replaced"), ("apprenticeship", "income_forgone"),
    ("repair_projects", "income_replaced"), ("recovery_crews", "income_replaced"),
    ("recovery_crews", "rows_dropped"), ("timber_supply", "income_withheld"),
    ("workshop_economics", "asset_subsidy_idle_units"),
)


class _Turn:
    """One observed turn, Phase 2 opening to Phase 10 (never checkpointed)."""

    __slots__ = ("turn", "opening", "continuity", "baselines", "carry", "credit")

    def __init__(self, turn: int):
        self.turn = turn
        self.opening = None          # (ids, region, wealth) or None
        self.continuity: dict = {}
        self.baselines: dict[tuple[str, str], float] = {}
        self.carry: dict[int, float] = {}
        self.credit: tuple[float, float] | None = None


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

def _state(world) -> WealthAccountingState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "wealth_accounting", None) if container is not None else None


def _bump(state: WealthAccountingState, key: str, amount: int = 1) -> None:
    if key not in COUNTERS:
        raise KeyError(f"undeclared wealth-accounting counter {key!r}")
    state.counters[key] = state.counters.get(key, 0) + amount


def _total(state: WealthAccountingState, key: str, amount) -> None:
    if key not in LIFETIME:
        raise KeyError(f"undeclared wealth-accounting total {key!r}")
    state.lifetime[key] = state.lifetime.get(key, 0) + amount


def _log(state: WealthAccountingState, turn: int, kind: str, **detail) -> None:
    state.log.append(LedgerRecord(turn=int(turn), kind=kind, detail=detail))
    if len(state.log) > MAX_LOG:
        state.log_dropped += len(state.log) - MAX_LOG
        del state.log[:-MAX_LOG]


def set_wealth_accounting_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable, or end with a dated record: turning it off drops the closing and
    the frame (balances are never carried across a turn the ledger did not
    observe); lifetime totals, counters and the log are kept."""
    turn = int(getattr(world, "turn", 0))
    state = _state(world)
    if state is None:
        world.livelihoods.wealth_accounting = state = WealthAccountingState(enabled=bool(value))
        if value:
            _bump(state, "switched_on")
            _log(state, turn, "switched_on")
        return
    t = state._turn
    if t is not None and t.turn == turn:
        raise RuntimeError("cannot change wealth accounting while a turn is pending")
    if bool(value) == state.enabled:
        return
    state.enabled = bool(value)
    if value:
        _bump(state, "switched_on")
        _log(state, turn, "switched_on")
        return
    _log(state, turn, "switched_off", closing_turn=state.closing.turn if state.closing is not None else None,
         frame_turn=state.frame_turn)
    _bump(state, "switched_off")
    state.closing, state.frame, state.frame_turn, state.reset_turn = None, None, None, None
    state._turn = None


def wealth_accounting_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled and getattr(world, "agent_mode", None) == "hybrid"


def _active(world, name: str):
    """The sub-state of package ``name`` while it is active, else None."""
    container = getattr(world, "livelihoods", None)
    sub = getattr(container, name, None) if container is not None else None
    if sub is None:
        return None
    if not getattr(import_module("chronicler." + name), f"{name}_active")(world):
        return None
    return sub


# ---------------------------------------------------------------------------
# Balances
# ---------------------------------------------------------------------------

def _balances(snapshot):
    """(ids, region, wealth) of a native agent snapshot, or None."""
    import numpy as np
    from chronicler.columnar import batch_arrays
    arrays = batch_arrays(snapshot, ("id", "region", "wealth"))
    if arrays is None:
        return None
    ids, region, wealth = arrays
    return ids.astype(np.int64), region.astype(np.int64), np.asarray(wealth, dtype=np.float32)


def _digests(ids, region, wealth) -> tuple[str, str]:
    """SHA-256 of (id, f32 wealth bits) and of (id, region), ascending id."""
    import numpy as np
    order = np.argsort(ids, kind="stable")
    sorted_ids = ids[order].astype("<u4").tobytes()
    bits = np.ascontiguousarray(wealth[order]).astype("<f4").view("<u4").tobytes()
    places = region[order].astype("<i4").tobytes()
    return (hashlib.sha256(sorted_ids + bits).hexdigest(), hashlib.sha256(sorted_ids + places).hexdigest())


def _region_sums(region, wealth64, n: int) -> tuple[list[float], list[int]]:
    import numpy as np
    mask = (region >= 0) & (region < n)
    sums = np.bincount(region[mask], weights=wealth64[mask], minlength=n)[:n]
    counts = np.bincount(region[mask], minlength=n)[:n]
    return [float(v) for v in sums], [int(v) for v in counts]


def _counter(world, package: str, key: str) -> float:
    sub = getattr(getattr(world, "livelihoods", None), package, None)
    counters = getattr(sub, "counters", None) if sub is not None else None
    return counters.get(key, 0) if counters else 0


def _credit_state(world):
    from chronicler.domestic_credit_state import domestic_credit_on
    if not domestic_credit_on(world) or getattr(world, "finance", None) is None:
        return None
    return world.domestic_credit


# ---------------------------------------------------------------------------
# Phase 2: the opening
# ---------------------------------------------------------------------------

def _continuity(state: WealthAccountingState, turn: int, opening, n: int) -> dict:
    closing = state.closing
    if opening is None:
        return {"status": "unchecked", "reason": "no_opening", "previous_close_turn": None}
    if closing is None:
        reason = "pool_reset" if state.reset_turn == turn else "first_turn"
        return {"status": "unchecked", "reason": reason, "previous_close_turn": None}
    if closing.turn != turn - 1:
        return {"status": "unchecked", "reason": "gap", "previous_close_turn": closing.turn}
    import numpy as np
    ids, region, wealth = opening
    digest, region_digest = _digests(ids, region, wealth)
    if digest == closing.digest and region_digest == closing.region_digest:
        return {"status": "exact", "reason": None, "previous_close_turn": closing.turn}
    total = math.fsum(wealth.astype(np.float64).tolist())
    sums, counts = _region_sums(region, wealth.astype(np.float64), n)
    width = max(len(closing.regions), n)
    rows = []
    for r in range(width):
        before = closing.regions[r] if r < len(closing.regions) else 0.0
        after = sums[r] if r < n else 0.0
        people = (counts[r] if r < n else 0) - (closing.counts[r] if r < len(closing.counts) else 0)
        if after != before or people:
            rows.append([r, after - before, people])
    return {"status": "broken", "reason": None, "previous_close_turn": closing.turn,
            "wealth_changed": digest != closing.digest, "region_changed": region_digest != closing.region_digest,
            "difference": total - closing.total, "agents_difference": int(len(ids)) - closing.agents,
            "regions": rows[:MAX_CONTINUITY_REGIONS], "regions_dropped": max(0, len(rows) - MAX_CONTINUITY_REGIONS)}


def prepare_phase2(world, region_input, agent_bridge, snapshot, acc):
    """Read the opening from the Phase 2 agent snapshot (before any Phase 2
    writer) and check it against the previous closing; changes nothing."""
    state = _state(world)
    turn = int(world.turn)
    if state._turn is not None and state._turn.turn == turn:
        raise RuntimeError("wealth accounting already opened for this turn")
    t = _Turn(turn)
    t.opening = _balances(snapshot)
    t.continuity = _continuity(state, turn, t.opening, len(world.regions))
    t.baselines = {key: _counter(world, *key) for key in _BASELINES}
    t.carry = {int(k): float(v) for k, v in (getattr(world, "_treasury_tax_carry", None) or {}).items()}
    credit = _credit_state(world)
    if credit is not None:
        t.credit = (float(credit.merchant_sent), float(credit.merchant_applied))
    state._turn = t
    return region_input


def rollback_phase2(world) -> None:
    state = _state(world)
    if state is not None and state._turn is not None and state._turn.turn == getattr(world, "turn", None):
        state._turn = None


def rollback_agent_tick(world, agent_bridge) -> None:
    rollback_phase2(world)


def on_pool_reset(world) -> None:
    """A rebuilt native pool: the closing belongs to other people now. Drop it
    with a dated record; the next opening is unchecked (a no-op in a fresh run,
    which has no closing yet)."""
    state = _state(world)
    if state is None:
        return
    state._turn = None
    if state.closing is None:
        return
    turn = int(getattr(world, "turn", 0))
    _log(state, turn, "pool_reset", closing_turn=state.closing.turn, closing_total=state.closing.total,
         closing_agents=state.closing.agents)
    _bump(state, "pool_resets")
    state.closing = None
    state.reset_turn = turn


# ---------------------------------------------------------------------------
# Phase 10: typed flows
# ---------------------------------------------------------------------------

def _close_enough(a: float, b: float) -> bool:
    return abs(a - b) <= REL_TOL * max(1.0, abs(a), abs(b))


class _Book:
    """This turn's typed flows, closures and treasury side, as collected."""

    def __init__(self, n_regions: int):
        self.n = n_regions
        self.rows: list[dict] = []
        self.located: dict[int, list[int]] = {}
        self.closures: list[dict] = []
        self.complete = True
        self.civ: dict[int, dict[str, int]] = {}
        self.treasury = {
            "to_households_milli": {"repair_wage": 0, "granary_crew_wage": 0, "woodcut_wage": 0,
                                    "food_procurement": 0},
            "firm_cash": {"sales_from_treasury_milli": 0, "wages_milli": 0, "stipends_milli": 0,
                          "distributions_to_treasury_milli": 0, "written_off_milli": 0},
            "charged": {"repair_projects": 0, "timber_supply": 0, "relocation_assistance": 0},
            "sinks_milli": {"repair_coins": 0, "granary_wage_residual": 0, "remittance_fee": 0,
                            "relocation_fare": 0, "relocation_assistance": 0, "procurement_residual": 0},
        }

    def channel(self, name: str, package: str | None, payer: str, observed: bool, total_in=0, total_out=0,
                by_region=()) -> None:
        loc_in = loc_out = 0
        for region, inflow, outflow in by_region:
            region = int(region)
            if not 0 <= region < self.n or not (inflow or outflow):
                continue
            cell = self.located.setdefault(region, [0, 0])
            cell[0] += int(inflow)
            cell[1] += int(outflow)
            loc_in += int(inflow)
            loc_out += int(outflow)
        if not observed:
            self.complete = False
        self.rows.append({"channel": name, "package": package, "payer": payer, "observed": bool(observed),
                          "in_milli": total_in, "out_milli": total_out,
                          "unlocated_in_milli": total_in - loc_in, "unlocated_out_milli": total_out - loc_out})
        if (total_in - loc_in) < 0 or (total_out - loc_out) < 0:
            self.closure(name, "located flows do not exceed the package's total", loc_in + loc_out,
                         total_in + total_out, (total_in - loc_in) >= 0 and (total_out - loc_out) >= 0)

    def closure(self, channel: str, check: str, lhs, rhs, closes: bool | None = None) -> None:
        if closes is None:
            closes = lhs == rhs if isinstance(lhs, int) and isinstance(rhs, int) else _close_enough(lhs, rhs)
        self.closures.append({"channel": channel, "check": check, "lhs": lhs, "rhs": rhs, "closes": bool(closes)})

    def civ_add(self, civ, key: str, amount: int) -> None:
        if civ is None or int(civ) < 0 or not amount:
            return
        row = self.civ.setdefault(int(civ), {})
        row[key] = row.get(key, 0) + int(amount)


def _payroll(world, book: _Book, turn: int) -> None:
    st = _active(world, "workshop_payroll")
    rs1 = _active(world, "apprenticeship") is not None
    if st is None:
        if rs1:
            # RS1 without L6a: no firm, no stipend (a recorded zero).
            book.channel("apprentice_stipend", "apprenticeship", CHANNELS[1][2], True)
        return
    fresh = st.frame_turn == turn
    a3 = _active(world, "workshop_economics") is not None
    wages = stipends = 0
    by_wage, by_stipend = [], []
    lhs = rhs = 0
    tr = book.treasury["firm_cash"]
    for r in (st.frame if fresh else ()):
        w, s = int(r.wages_paid), int(r.stipends or 0)
        wages += w
        stipends += s
        by_wage.append((r.region, w, 0))
        by_stipend.append((r.region, s, 0))
        lhs += int(r.cash_open) + int(r.sales) - w - s - int(r.distributed) - int(r.written_off)
        # A3 (workshop economics): capital, household sales and inputs (absent: 0).
        lhs += sum(int(getattr(r, k, None) or 0) for k in ("capital", "household_sales")) \
            - int(getattr(r, "inputs", None) or 0)
        rhs += int(r.cash_close)
        tr["sales_from_treasury_milli"] += int(r.sales)
        tr["distributions_to_treasury_milli"] += int(r.distributed)
        tr["written_off_milli"] += int(r.written_off)
        book.civ_add(r.controller, "firm_sales_milli", int(r.sales))
        book.civ_add(r.controller, "firm_distributions_milli", int(r.distributed))
    tr["wages_milli"] += wages
    tr["stipends_milli"] += stipends
    book.channel("workshop_wage", "workshop_payroll", CHANNELS[0][2], fresh, wages, 0, by_wage)
    if rs1 or stipends:
        book.channel("apprentice_stipend", "apprenticeship", CHANNELS[1][2], fresh, stipends, 0, by_stipend)
    if fresh:
        check = ("firm cash: open + capital + academy sales + household sales - inputs - wages - stipends - "
                 "distributions - write-offs = close" if a3 else
                 "firm cash: open + sales - wages - stipends - distributions - write-offs = close")
        book.closure("workshop_wage", check, lhs, rhs)


def _workshop_economics(world, book: _Book, t: _Turn, turn: int) -> None:
    """A3: the payment seam's agent-wealth channels (``MONEY_PURPOSE_CHANNELS``,
    read generically with signs from the seam's exact per-turn totals, so a turn
    beyond the flow list's bound is still counted in full) and the treasury
    side of firm capital, input purchases and the owner's building subsidy,
    each re-checked against the A3 receipts."""
    st = _active(world, "workshop_economics")
    if st is None:
        return
    from chronicler.money import totals_for_turn
    from chronicler.wealth_accounting_state import MONEY_PURPOSE_CHANNELS
    fresh = st.frame_turn == turn
    totals = (totals_for_turn(world, turn) or []) if fresh else []
    channel_of = {name: (i, package) for i, (name, package, _payer) in enumerate(CHANNELS)}
    moved = {}
    for purpose, channel in MONEY_PURPOSE_CHANNELS.items():
        if CHANNELS[channel_of[channel][0]][1] != "workshop_economics":
            continue    # another payer's purpose (C2 care wages: excluded with this ledger)
        inflow = outflow = 0
        by_region: dict[int, list[int]] = {}
        for x in totals:
            if x.purpose != purpose:
                continue
            cell = by_region.setdefault(int(x.region), [0, 0]) if x.region is not None else [0, 0]
            if x.payee_kind == "agent_wealth":
                inflow += x.applied
                cell[0] += x.applied
            if x.payer_kind == "agent_wealth":
                outflow += x.applied
                cell[1] += x.applied
        idx, package = channel_of[channel]
        book.channel(channel, package, CHANNELS[idx][2], fresh, inflow, outflow,
                     [(r, v[0], v[1]) for r, v in sorted(by_region.items())])
        moved[purpose] = (inflow, outflow)
    if not fresh:
        return

    def applied(purpose, payee_kind=None):
        return sum(x.applied for x in totals if x.purpose == purpose
                   and (payee_kind is None or x.payee_kind == payee_kind))

    receipts = list(st.frame)
    got = {"capital": sum(r.capital_in for r in receipts),
           "household": sum(int((r.households or {}).get("paid_milli", 0)) for r in receipts),
           "inputs": sum(int((r.inputs or {}).get("charged_milli", 0)) for r in receipts),
           "subsidy": sum(r.owner_asset_spend for r in receipts)}
    idle = int(_counter(world, "workshop_economics", "asset_subsidy_idle_units")
               - t.baselines.get(("workshop_economics", "asset_subsidy_idle_units"), 0))
    to_treasury = [x for x in totals if x.purpose == "firm_input_purchase" and x.payee_kind == "civ_treasury"]
    units = sum(x.treasury_units for x in to_treasury)
    carried = sum(x.carry_change for x in to_treasury)
    paid = moved.get("wares_purchase", (0, 0))[1]
    book.treasury["firm_economics"] = {
        "capital_from_treasury_milli": applied("firm_capital"),
        "inputs_to_treasury_milli": applied("firm_input_purchase", "civ_treasury"),
        "input_treasury_units": units, "input_carry_change_milli": carried,
        "inputs_to_sink_milli": applied("firm_input_purchase", "sink"),
        "household_sales_milli": paid, "asset_subsidy_firm_units": got["subsidy"], "asset_subsidy_idle_units": idle,
        "firm_cash_open_milli": sum(r.cash_open for r in receipts),
        "firm_cash_close_milli": sum(r.cash_close for r in receipts),
        "flows_dropped": int(st.book.flows_dropped if st.book.flows_turn == turn else 0),
    }
    # Per civilization from the exact totals (the flow list may be truncated).
    for x in totals:
        if x.purpose == "firm_capital" and x.payer_civ is not None:
            book.civ_add(x.payer_civ, "firm_capital_milli", x.applied)
        elif x.purpose == "firm_input_purchase" and x.payee_civ is not None:
            book.civ_add(x.payee_civ, "firm_inputs_milli", x.applied)
    for r in receipts:
        book.civ_add(r.owner, "asset_subsidy_units", r.owner_asset_spend)
    book.closure("wares_purchase", "households debited = firm cash credited (A3 receipts)", paid, got["household"])
    book.closure("wares_purchase", "capital flows = capital received (A3 receipts)", applied("firm_capital"),
                 got["capital"])
    book.closure("wares_purchase", "input purchase flows = inputs charged (A3 receipts)",
                 applied("firm_input_purchase"), got["inputs"])
    book.closure("wares_purchase", "inputs to treasuries = whole units x 1000 + carry change",
                 applied("firm_input_purchase", "civ_treasury"), units * MILLI + carried)


def _repairs(world, book: _Book, turn: int) -> None:
    st = _active(world, "repair_projects")
    if st is None:
        return
    fresh = st.frame_turn == turn and st.receipts is not None
    wages, by_region = 0, []
    for r in (st.receipts if fresh else ()):
        wages += int(r.wages_milli)
        by_region.append((r.region, int(r.wages_milli), 0))
    book.channel("repair_wage", "repair_projects", CHANNELS[2][2], fresh, wages, 0, by_region)
    if not fresh:
        return
    lhs = rhs = applied = coins = 0
    for row in st.ledger or ():
        lhs += int(row.charged) * MILLI + int(row.prepaid_before_milli)
        rhs += int(row.coin_cost_milli) + int(row.wages_applied_milli) + int(row.prepaid_after_milli)
        applied += int(row.wages_applied_milli)
        coins += int(row.coin_cost_milli)
        book.treasury["charged"]["repair_projects"] += int(row.charged)
        book.civ_add(row.civ, "charged", int(row.charged))
        book.civ_add(row.civ, "to_households_milli", int(row.wages_applied_milli))
    book.treasury["to_households_milli"]["repair_wage"] += applied
    book.treasury["sinks_milli"]["repair_coins"] += coins       # PL3 below moves its wage part out
    book.closure("repair_wage", "treasury: charged x 1000 + prepaid before = coin costs + wages + prepaid after",
                 lhs, rhs)
    book.closure("repair_wage", "ledger wages applied = receipt wages credited", applied, wages)


def _granary_crews(world, book: _Book, turn: int) -> None:
    st = _active(world, "recovery_crews")
    if st is None:
        return
    fresh = st.frame_turn == turn and st.ledger is not None
    wages = residual = sunk = coins = due = 0
    for row in (st.ledger if fresh else ()):
        wages += int(row.wages_milli)
        residual += int(row.wage_residual_milli)
        sunk += int(row.sunk_milli)
        coins += int(row.coin_cost_milli)
        due += int(row.wages_due_milli)
        book.civ_add(row.civ, "to_households_milli", int(row.wages_milli))
    by_region = [(r.region, int(r.wages_milli), 0) for r in (st.receipts or ()) if fresh and r.kind == "granary"]
    book.channel("granary_crew_wage", "recovery_crews", CHANNELS[3][2], fresh, wages, 0, by_region)
    if not fresh:
        return
    book.treasury["to_households_milli"]["granary_crew_wage"] += wages
    book.treasury["sinks_milli"]["repair_coins"] -= wages
    book.treasury["sinks_milli"]["granary_wage_residual"] += residual
    book.closure("granary_crew_wage", "granary coins = wages + sunk (" + st.mode + ")", coins, wages + sunk)
    book.closure("granary_crew_wage", "wages + ceiling residual = wages due", wages + residual, due)


def _woodcut(world, book: _Book, turn: int) -> None:
    st = _active(world, "timber_supply")
    if st is None:
        return
    fresh = st.frame_turn == turn and st.receipts is not None
    wages, by_region = 0, []
    for r in (st.receipts if fresh else ()):
        wages += int(r.wages_milli)
        by_region.append((r.home, int(r.wages_milli), 0))
    book.channel("woodcut_wage", "timber_supply", CHANNELS[4][2], fresh, wages, 0, by_region)
    if not fresh:
        return
    lhs = rhs = applied = 0
    for row in st.ledger or ():
        lhs += int(row.charged) * MILLI + int(row.prepaid_before_milli)
        rhs += int(row.wages_applied_milli) + int(row.prepaid_after_milli)
        applied += int(row.wages_applied_milli)
        book.treasury["charged"]["timber_supply"] += int(row.charged)
        book.civ_add(row.civ, "charged", int(row.charged))
        book.civ_add(row.civ, "to_households_milli", int(row.wages_applied_milli))
    book.treasury["to_households_milli"]["woodcut_wage"] += applied
    book.closure("woodcut_wage", "treasury: charged x 1000 + prepaid before = wages + prepaid after", lhs, rhs)
    book.closure("woodcut_wage", "ledger wages applied = receipt wages credited", applied, wages)


def _retail(world, book: _Book, turn: int) -> None:
    st = _active(world, "household_retail")
    if st is None:
        return
    fresh = st.frame_turn == turn
    money = dict(st.money or {}) if fresh else {}
    paid, credited, refunded = (int(money.get(k, 0)) for k in ("paid_milli", "credited_milli", "refunded_milli"))
    by_region = []
    for f in (st.frame if fresh else ()):
        p = f.provisioning
        if p:
            c, pd, rf = (int(round(float(p.get(k, 0.0)))) for k in ("credited_milli", "paid_milli", "refunded_milli"))
            by_region.append((f.region, c, pd - rf))
    book.channel("food_purchase", "household_retail", CHANNELS[6][2], fresh, credited, paid - refunded, by_region)
    owed, got, rest, unpaid = (int(money.get("procurement_" + k, 0))
                               for k in ("owed_milli", "credited_milli", "residual_milli", "unpaid_milli"))
    book.channel("food_procurement", "household_retail", CHANNELS[5][2], fresh, got, 0, ())
    if not fresh:
        return
    book.treasury["to_households_milli"]["food_procurement"] += got
    book.treasury["sinks_milli"]["procurement_residual"] += rest
    book.closure("food_purchase", "buyers paid = sellers credited + refunds", paid, credited + refunded)
    book.closure("food_procurement", "owners' share owed = credited + ceiling residual + unpaid", owed,
                 got + rest + unpaid)


def _remittances(world, book: _Book, turn: int) -> None:
    st = _active(world, "remittances")
    if st is None:
        return
    fresh = st.frame_turn == turn
    totals = dict(st.totals or {}) if fresh else {}
    credited, debited, fee, sent, refunded = (int(totals.get(k + "_milli", 0))
                                              for k in ("credited", "debited", "fee", "sent", "refunded"))
    by_region = [(r.region, int(r.inflow_milli), int(r.outflow_milli)) for r in (st.regions if fresh else ())]
    book.channel("remittance", "remittances", CHANNELS[7][2], fresh, credited, debited, by_region)
    if not fresh:
        return
    book.treasury["sinks_milli"]["remittance_fee"] += fee
    book.closure("remittance", "senders debited = recipients credited + courier fee", debited, credited + fee)
    book.closure("remittance", "sent = debited + refunded", sent, debited + refunded)


def _relocation(world, book: _Book, t: _Turn, turn: int) -> None:
    st = _active(world, "relocation_costs")
    if st is None:
        return

    def delta(key):
        return int(_counter(world, "relocation_costs", key) - t.baselines.get(("relocation_costs", key), 0))

    fare = delta("fare_debited_milli")
    fresh = st.frame_turn == turn
    by_region = [(h.from_region, 0, int(h.paid)) for h in (st.households if fresh else ())
                 if h.applied and h.reason in ("passed", "assisted") and h.paid]
    book.channel("relocation_fare", "relocation_costs", CHANNELS[8][2], True, 0, fare, by_region)
    coins = 0
    if st.last_assistance_turn == turn:
        for c in st.assistance or ():
            if c.status == "charged":
                coins += int(c.charged_coins)
                book.civ_add(c.civ, "charged", int(c.charged_coins))
    book.treasury["charged"]["relocation_assistance"] += coins
    book.treasury["sinks_milli"]["relocation_fare"] += fare
    book.treasury["sinks_milli"]["relocation_assistance"] += coins * MILLI
    book.closure("relocation_fare", "fares due - assistance = debited + residual + not charged",
                 delta("fare_due_milli") - delta("assistance_granted_milli"),
                 fare + delta("fare_residual_milli") + delta("fare_not_charged_milli"))
    book.closure("relocation_fare", "travel sink = fares debited + assistance coins x 1000",
                 delta("travel_sink_milli"), fare + coins * MILLI)


def _credit(world, book: _Book, t: _Turn) -> None:
    st = _credit_state(world)
    if st is None:
        return
    if t.credit is None:
        book.channel("domestic_credit", None, CHANNELS[9][2], False)
        return
    # Whole milli-units, as every channel; the sub-milli rest of the f32
    # change stays in the native-model residual.
    net = int(round((float(st.merchant_applied) - t.credit[1]) * MILLI))
    book.channel("domestic_credit", None, CHANNELS[9][2], True, max(net, 0), max(-net, 0), ())


def _treasury_created(world, economy_result, acc, t: _Turn, book: _Book) -> tuple[dict, dict]:
    """The treasury tax credited this turn (reproduced exactly from the
    economy's tax and the carry read at the opening), and the tithe: its
    potential (an upper bound) and the approximate part of civilizations whose
    clergy is at the threshold after the faction tick."""
    from chronicler.factions import TITHE_RATE, TITHE_THRESHOLD, compute_tithe_base
    from chronicler.models import FactionType
    tax = 0
    n = len(world.civilizations)
    if economy_result is not None and acc is not None:
        for civ_idx, amount in getattr(economy_result, "treasury_tax", {}).items():
            if civ_idx >= n:
                continue
            whole = int(max(0.0, float(amount) + float(t.carry.get(int(civ_idx), 0.0))))
            if whole > 0:
                tax += whole
                book.civ_add(civ_idx, "treasury_tax", whole)
    potential = at_threshold = 0
    for civ_idx, civ in enumerate(world.civilizations):
        if not civ.regions:
            continue
        offered = int(TITHE_RATE * compute_tithe_base(civ, economy_result=economy_result, civ_idx=civ_idx))
        if offered <= 0:
            continue
        potential += offered
        book.civ_add(civ_idx, "tithe_potential", offered)
        if civ.factions.influence.get(FactionType.CLERGY, 0) >= TITHE_THRESHOLD:
            at_threshold += offered
            book.civ_add(civ_idx, "tithe_at_threshold_after_tick", offered)
    return ({"treasury_tax": tax},
            {"potential": potential, "at_threshold_after_tick": at_threshold, "approximate": True,
             "collected": None})


# ---------------------------------------------------------------------------
# Phase 10: withheld paid work (RL7)
# ---------------------------------------------------------------------------

def _installed(world, turn: int) -> dict[str, set[int]] | None:
    """Who each paid-work package installed this turn, from its committed
    records; None when no paid-work package is active."""
    sets: dict[str, set[int]] = {name: set() for name in WITHHELD_PACKAGES}
    seen = False
    st = _active(world, "workshop_payroll")
    if st is not None:
        seen = True
        if st.frame_turn == turn:
            sets["workshop_payroll"] = {int(a) for r in st.frame if r.operating for a in r.crew}
    st = _active(world, "apprenticeship")
    if st is not None:
        seen = True
        if st.frame_turn == turn:
            # Attended apprentices; version 2 extends only those attached
            # beside the crew (crew members give crew time, installed by L6a).
            sets["apprenticeship"] = {int(s.agent_id) for r in st.frame for s in r.seats
                                      if s.mentor is not None and s.aboard != "crew"}
    st = _active(world, "recovery_crews")
    if st is not None:
        seen = True
        if st.frame_turn == turn and st.receipts is not None:
            for r in st.receipts:
                if r.kind == "granary":
                    sets["recovery_crews_granary"] |= {int(m.agent_id) for m in r.members if m.worked > 0}
                else:
                    sets["recovery_crews_workshop"] |= {int(m.agent_id) for m in r.members}
    st = _active(world, "repair_projects")
    if st is not None:
        seen = True
        if st.frame_turn == turn and st.receipts is not None:
            sets["repair_projects"] = {int(a) for r in st.receipts if r.kind == "workshop" for a in r.crew}
    st = _active(world, "timber_supply")
    if st is not None:
        seen = True
        if st.frame_turn == turn and st.receipts is not None:
            sets["timber_supply"] = {int(a) for r in st.receipts for a in r.crew}
    return sets if seen else None


def _withheld(world, t: _Turn, turn: int) -> dict | None:
    """Withheld income of the turn (no money moves): paid work, attributed row
    by row to its installing package, and L6b's replaced farm income. None only
    when neither a paid-work package nor retail is active; inside, the paid-work
    fields are None when no paid-work package is active (not zero) and
    ``retail_income_replaced`` is None when retail is off or not observed."""
    sets = _installed(world, turn)
    retail_state = _active(world, "household_retail")
    if sets is None and retail_state is None:
        return None
    retail = None
    if retail_state is not None and retail_state.frame_turn == turn:
        replaced = (retail_state.income or {}).get("replaced")
        retail = float(replaced) if replaced is not None else None
    out = {"paid_work_active": sets is not None, "rows": None, "deducted": None, "packages": None,
           "unattributed_rows": None, "unattributed_pl3_dropped_rows": None, "unattributed_deducted": None,
           "conflicts": None, "recovery_crews": None, "retail_active": retail_state is not None,
           "retail_income_replaced": retail}
    if sets is None:
        return out
    lv = world.livelihoods
    cached = getattr(lv, "_paid_receipt", None)
    rows = cached[1] if cached is not None and cached[0] == turn else {}
    pl3_active = _active(world, "recovery_crews") is not None
    deducted = {name: [] for name in WITHHELD_PACKAGES}
    ordinary = {name: [] for name in WITHHELD_PACKAGES}
    counts = dict.fromkeys(WITHHELD_PACKAGES, 0)
    unattributed, dropped, conflicts, lost = 0, 0, 0, []
    for aid in sorted(rows):
        _share, base, cut = rows[aid]
        matches = [name for name in WITHHELD_PACKAGES if aid in sets[name]]
        if "recovery_crews_workshop" in matches and "repair_projects" in matches:
            matches.remove("repair_projects")        # one crew: PL3 widened RS2's pool
        elif pl3_active and matches == ["repair_projects"]:
            # While PL3 is active every RS2 workshop crew is a PL3 workshop
            # crew; one only RS2 names was on a receipt PL3's row cap dropped.
            # Its package is not known from the records: unattributed.
            matches = []
            dropped += 1
        if not matches:
            unattributed += 1
            lost.append(float(cut))
            continue
        if len(matches) > 1:
            conflicts += 1
        name = matches[0]
        counts[name] += 1
        deducted[name].append(float(cut))
        ordinary[name].append(float(base))

    def delta(package, key):
        if _active(world, package) is None:
            return None
        return float(_counter(world, package, key) - t.baselines.get((package, key), 0))

    sums = {name: math.fsum(deducted[name]) for name in WITHHELD_PACKAGES}
    own = {"workshop_payroll": delta("workshop_payroll", "income_replaced"),
           "apprenticeship": delta("apprenticeship", "income_forgone"),
           "repair_projects": delta("repair_projects", "income_replaced"),
           "timber_supply": delta("timber_supply", "income_withheld")}
    pl3 = delta("recovery_crews", "income_replaced")
    packages = []
    for name in WITHHELD_PACKAGES:
        total = own.get(name)
        compared = sums[name]
        if name == "repair_projects" and total is not None:
            # RS2's own counter covers its workshop crews, PL3's workshop
            # crews included (the overlap the audit names D7).
            compared = sums["repair_projects"] + sums["recovery_crews_workshop"]
        packages.append({"package": name, "rows": counts[name], "deducted": sums[name],
                         "ordinary": math.fsum(ordinary[name]), "package_total": total,
                         "matches": None if total is None else _close_enough(compared, total)})
    split = None
    if pl3 is not None:
        granary, workshop = sums["recovery_crews_granary"], sums["recovery_crews_workshop"]
        split = {"granary": granary, "workshop": workshop, "total": pl3, "difference": granary + workshop - pl3,
                 "closes": _close_enough(granary + workshop, pl3),
                 "rows_dropped": int(delta("recovery_crews", "rows_dropped") or 0)}
    out.update(rows=len(rows), deducted=math.fsum(float(v[2]) for v in rows.values()), packages=packages,
               unattributed_rows=unattributed, unattributed_pl3_dropped_rows=dropped,
               unattributed_deducted=math.fsum(lost), conflicts=conflicts, recovery_crews=split)
    return out


# ---------------------------------------------------------------------------
# Phase 10: the frame
# ---------------------------------------------------------------------------

def _frame(world, t: _Turn, closing, economy_result, acc) -> dict:
    import numpy as np
    turn = int(world.turn)
    n = len(world.regions)
    ids_o, reg_o, w_o = t.opening
    ids_c, reg_c, w_c = closing
    w64_o, w64_c = w_o.astype(np.float64), w_c.astype(np.float64)
    open_r, count_o = _region_sums(reg_o, w64_o, n)
    close_r, count_c = _region_sums(reg_c, w64_c, n)
    _common, io, ic = np.intersect1d(ids_o, ids_c, assume_unique=True, return_indices=True)
    moved = reg_o[io] != reg_c[ic]
    carried = w64_c[ic][moved]
    mig_out, _ = _region_sums(reg_o[io][moved], carried, n)
    mig_in, _ = _region_sums(reg_c[ic][moved], carried, n)
    born = np.isin(ids_c, ids_o, assume_unique=True, invert=True)
    died = np.isin(ids_o, ids_c, assume_unique=True, invert=True)
    birth_w, birth_n = _region_sums(reg_c[born], w64_c[born], n)
    death_w, death_n = _region_sums(reg_o[died], w64_o[died], n)

    book = _Book(n)
    _payroll(world, book, turn)
    _workshop_economics(world, book, t, turn)
    _repairs(world, book, turn)
    _granary_crews(world, book, turn)
    _woodcut(world, book, turn)
    _retail(world, book, turn)
    _remittances(world, book, turn)
    _relocation(world, book, t, turn)
    _credit(world, book, t)
    created, tithe = _treasury_created(world, economy_result, acc, t, book)
    order = {name: i for i, name in enumerate(CHANNEL_NAMES)}
    book.rows.sort(key=lambda row: order[row["channel"]])

    typed_in = sum(r["in_milli"] for r in book.rows)
    typed_out = sum(r["out_milli"] for r in book.rows)
    open_total = math.fsum(w64_o.tolist())
    close_total = math.fsum(w64_c.tolist())
    delta = close_total - open_total
    regions = []
    for r in range(n):
        inflow, outflow = book.located.get(r, (0, 0))
        if not (count_o[r] or count_c[r] or inflow or outflow):
            continue
        change = close_r[r] - open_r[r]
        regions.append({
            "region": r, "open": open_r[r], "close": close_r[r], "agents_open": count_o[r],
            "agents_close": count_c[r], "migration_in": mig_in[r], "migration_out": mig_out[r],
            "births": birth_n[r], "births_close": birth_w[r], "deaths": death_n[r], "deaths_open": death_w[r],
            "typed_in_milli": inflow, "typed_out_milli": outflow,
            "native_model": change - (mig_in[r] - mig_out[r]) - (inflow - outflow) / MILLI,
        })
    placed_o = int(((reg_o >= 0) & (reg_o < n)).sum())
    placed_c = int(((reg_c >= 0) & (reg_c < n)).sum())
    world_row = {
        "open": open_total, "close": close_total, "delta": delta,
        "agents_open": int(len(ids_o)), "agents_close": int(len(ids_c)),
        "births": int(born.sum()), "births_close": math.fsum(w64_c[born].tolist()),
        "deaths": int(died.sum()), "deaths_open": math.fsum(w64_o[died].tolist()),
        "moved": int(moved.sum()), "moved_close": math.fsum(carried.tolist()),
        "typed_in_milli": typed_in, "typed_out_milli": typed_out, "typed_net_milli": typed_in - typed_out,
        "unlocated_in_milli": sum(r["unlocated_in_milli"] for r in book.rows),
        "unlocated_out_milli": sum(r["unlocated_out_milli"] for r in book.rows),
        "native_model": delta - (typed_in - typed_out) / MILLI,
        "unplaced_agents": (int(len(ids_o)) - placed_o) + (int(len(ids_c)) - placed_c),
    }
    treasury = {"created": created, "tithe": tithe, **book.treasury,
                "by_civ": [{"civ": c, **{k: v for k, v in sorted(book.civ[c].items())}} for c in sorted(book.civ)]}
    return {
        "turn": turn, "continuity": t.continuity, "typed_complete": book.complete, "world": world_row,
        "regions": regions, "typed": book.rows, "closures": book.closures, "withheld": _withheld(world, t, turn),
        "treasury": treasury,
    }


def phase10(world, acc, economy_result, agent_bridge):
    """After every payer (the last livelihoods hook): the closing, the turn's
    typed flows, the identities and the treasury side. Changes nothing but
    this package's own state."""
    state = _state(world)
    turn = int(world.turn)
    t, state._turn = state._turn, None
    if t is not None and t.turn != turn:
        t = None
    sim = getattr(agent_bridge, "_sim", None) if agent_bridge is not None else None
    closing = _balances(sim.get_snapshot()) if sim is not None else None
    frame = None
    if t is not None and t.opening is not None and closing is not None:
        frame = _frame(world, t, closing, economy_result, acc)
    if frame is None:
        _bump(state, "turns_unobserved")
        _log(state, turn, "unobserved", opening=t is not None and t.opening is not None,
             closing=closing is not None)
    else:
        _commit(state, frame, turn)
    state.frame, state.frame_turn = frame, turn
    if closing is None:
        state.closing = None
    else:
        import numpy as np
        ids, region, wealth = closing
        digest, region_digest = _digests(ids, region, wealth)
        w64 = wealth.astype(np.float64)
        sums, counts = _region_sums(region, w64, len(world.regions))
        state.closing = Closing(turn=turn, digest=digest, region_digest=region_digest,
                                total=math.fsum(w64.tolist()), agents=int(len(ids)), regions=sums, counts=counts)
    return []


def _commit(state: WealthAccountingState, frame: dict, turn: int) -> None:
    _bump(state, "turns_observed")
    continuity = frame["continuity"]
    _bump(state, "continuity_" + continuity["status"])
    if continuity["status"] == "broken":
        _total(state, "discontinuity", continuity["difference"])
        _log(state, turn, "continuity_broken", difference=continuity["difference"],
             agents_difference=continuity["agents_difference"], previous_close_turn=continuity["previous_close_turn"])
    if not frame["typed_complete"]:
        _bump(state, "typed_incomplete_turns")
    failed = [c for c in frame["closures"] if not c["closes"]]
    if failed:
        _bump(state, "closures_failed", len(failed))
    for row in frame["typed"]:
        _total(state, f"{row['channel']}_in_milli", row["in_milli"])
        _total(state, f"{row['channel']}_out_milli", row["out_milli"])
    _total(state, "delta", frame["world"]["delta"])
    _total(state, "native_model", frame["world"]["native_model"])
    withheld = frame["withheld"]
    if withheld is not None and withheld["retail_income_replaced"] is not None:
        _total(state, "withheld_retail", withheld["retail_income_replaced"])
    if withheld is not None and withheld["paid_work_active"]:
        _bump(state, "withheld_rows", withheld["rows"])
        for row in withheld["packages"]:
            _total(state, f"withheld_{row['package']}", row["deducted"])
        _total(state, "withheld_unattributed", withheld["unattributed_deducted"])
        if withheld["unattributed_rows"]:
            _bump(state, "unattributed_rows", withheld["unattributed_rows"])
        if withheld["conflicts"]:
            _bump(state, "attribution_conflicts", withheld["conflicts"])
        if withheld["unattributed_pl3_dropped_rows"]:
            _bump(state, "unattributed_pl3_dropped_rows", withheld["unattributed_pl3_dropped_rows"])
        if withheld["unattributed_rows"] or withheld["conflicts"]:
            _log(state, turn, "attribution", unattributed=withheld["unattributed_rows"],
                 pl3_dropped=withheld["unattributed_pl3_dropped_rows"], conflicts=withheld["conflicts"])
    tr = frame["treasury"]
    _total(state, "treasury_tax_created", tr["created"]["treasury_tax"])
    _total(state, "tithe_potential", tr["tithe"]["potential"])
    _total(state, "tithe_at_threshold_after_tick", tr["tithe"]["at_threshold_after_tick"])
    _total(state, "treasury_to_households_milli", sum(tr["to_households_milli"].values()))
    _total(state, "treasury_to_firm_cash_milli", tr["firm_cash"]["sales_from_treasury_milli"])
    _total(state, "firm_cash_to_treasury_milli", tr["firm_cash"]["distributions_to_treasury_milli"])
    _total(state, "treasury_charged", sum(tr["charged"].values()))
    firm = tr.get("firm_economics")
    if firm is not None:
        _total(state, "treasury_to_firm_capital_milli", firm["capital_from_treasury_milli"])
        _total(state, "firm_inputs_to_treasury_milli", firm["inputs_to_treasury_milli"])
        _total(state, "asset_subsidy_units", firm["asset_subsidy_firm_units"] + firm["asset_subsidy_idle_units"])


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------

def snapshot_summary(world) -> dict:
    """The completed-turn observation, dated by ``source_turn``; ``frame`` is
    None when that turn was not observed (unknown, not zero)."""
    from chronicler.factions import TITHE_RATE, TITHE_THRESHOLD
    state = _state(world)
    source = world.turn - 1
    fresh = state.frame_turn == source and state.frame is not None
    return {
        "schema_version": 1, "stage": STAGE, "source_turn": source,
        "units": {"balance": "wealth_units", "typed": "milli_units", "treasury": "treasury_units", "milli": MILLI},
        # A copy: the record never aliases the ledger's own state.
        "frame": copy.deepcopy(state.frame) if fresh else None,
        "lifetime": {k: state.lifetime[k] for k in LIFETIME if k in state.lifetime},
        "counters": {k: state.counters[k] for k in COUNTERS if k in state.counters},
        "log": [r.model_dump() for r in state.log], "log_dropped": state.log_dropped,
        "labels": dict(LABELS),
        "parameters": {"rel_tol": REL_TOL, "max_log": MAX_LOG, "tithe_rate": TITHE_RATE,
                       "tithe_threshold": TITHE_THRESHOLD, "channels": [c[0] for c in CHANNELS],
                       "withheld_packages": list(WITHHELD_PACKAGES)},
    }


#: Keys every observed frame carries (the record shape a reader may rely on).
FRAME_KEYS: tuple[str, ...] = ("turn", "continuity", "typed_complete", "world", "regions", "typed", "closures",
                               "withheld", "treasury")


def record_status(snapshot) -> tuple[str, dict | None]:
    """How a reader treats one history snapshot's ledger record (the reference
    for viewer and analysis readers): ``("absent", None)`` - the switch was
    never on or is off in that turn; ``("malformed", None)`` - present but not
    this record's shape; ``("unobserved", None)`` - the source turn was not
    observed (unknown, not zero); ``("observed", frame)`` - the frame, whose
    zeros are recorded zeros."""
    livelihoods = snapshot.get("livelihoods") if isinstance(snapshot, dict) else None
    if not isinstance(livelihoods, dict) or "wealth_accounting" not in livelihoods:
        return "absent", None
    record = livelihoods["wealth_accounting"]
    source = record.get("source_turn") if isinstance(record, dict) else None
    if (not isinstance(record, dict) or record.get("schema_version") != 1 or record.get("stage") != STAGE
            or not isinstance(source, int) or isinstance(source, bool) or "frame" not in record):
        return "malformed", None
    frame = record["frame"]
    if frame is None:
        return "unobserved", None
    if not isinstance(frame, dict) or any(key not in frame for key in FRAME_KEYS) or frame["turn"] != source \
            or not isinstance(frame["world"], dict) or not isinstance(frame["regions"], list):
        return "malformed", None
    return "observed", frame
