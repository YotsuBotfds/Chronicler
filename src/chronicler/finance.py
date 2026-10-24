"""Money, credit and public finance (``--finance``; default off).

The world field ``WorldState.finance`` doubles as the switch: ``None`` means
off, nothing in this module runs and every output is identical to the
finance-free simulation. Everything here is deterministic (no random draws,
fixed iteration order by civilization and region index) and every treasury
change goes through the accumulator as ``keep``, like tax and trade income.

State
    Per civilization (``FinanceState.civs``, aligned with
    ``world.civilizations``; a civilization's identity is its index):
    smoothed revenue, the price index and coin fineness, credit standing
    (premium, default memory, domestic trust, arrears), creditor grievance
    and cumulative accounts. Per region (aligned with ``world.regions``): the
    specie (silver) its people hold and its smoothed real output. Loans
    (``FinanceState.loans``) name borrower and lender by civ index; the
    domestic creditor class is ``DOMESTIC`` (-1).

Fiscal tick (Phase 3b, right after production; :func:`tick_finance`)
    1. Revenue: this turn's ordinary treasury income (every positive ``keep``
       treasury change recorded so far: production, tax, trade, prestige,
       tribute, institutions), smoothed. Part of it is ad valorem and follows
       the price index (``TAX_INDEXATION``); the crown's share of new bullion
       is paid in.
    2. Obligations: upkeep of the army (``military``) and of the
       administration (regions, people), both at current prices, plus debt
       service (interest and amortization) on every outstanding loan.
    3. Financing: when the treasury would fall below a reserve floor the
       state borrows, first from its own merchant/elite creditor class
       (capacity from merchant wealth, which the goods economy reports as the
       tax base, and merchant faction influence), then from wealthy foreign
       civs it is in contact with (contact-ledger flows; trade partners or
       neighbours when the ledger is off). Still short of its obligations it
       debases the coinage (seigniorage now, inflation later); otherwise it
       falls into arrears and, after ``ARREARS_LIMIT`` turns, defaults.
    4. Payments: upkeep first, then debt service, oldest loan first
       (unpaid interest is capitalized). Surpluses above the reserve target
       prepay debt and fund the court (a share of revenue scaled by the
       governance conspicuous-consumption ratchet, plus part of any idle
       surplus), so treasuries no longer pile up.
    5. Consequences: unpaid troops desert, inflation and debasement cost
       stability, defaults cost stability, legitimacy, merchant influence,
       domestic trust and raise the interest premium; foreign creditors gain
       grievance and sour on the defaulter.
    6. Fiscal stress (debt, service and deficit relative to revenue, arrears,
       recent default, inflation) feeds the governance PSI ``state_debt``
       input (:func:`psi_fiscal_distress`), replacing the
       governing-cost/treasury proxy.

Monetary update (end of turn; :func:`update_money`)
    Real output per region ``population * (0.5 + economy / 100)`` is
    smoothed; precious-metal slots mint new silver (the crown takes
    ``ROYAL_SHARE``); a newly occupied region is sacked of ``SACK_SHARE`` of
    its specie, carried to the occupier's capital; every region's specie
    flows back toward the money demand of its output (Hume's price-specie
    flow). A civ's target price is its specie over the demand of its output,
    divided by its fineness; the price index closes ``PRICE_ADJUST`` of the
    gap per turn (sticky prices), so large inflows (loot, new mines, foreign
    loans) and debasement produce a slow price revolution rather than a jump.

Leverage
    :func:`finance_weight_modifiers` is a contributor bucket of action
    weights, clamped to ``[1/FINANCE_WEIGHT_CEILING, FINANCE_WEIGHT_CEILING]``
    before the global weight cap: foreign debt pushes debtors toward trade
    and away from war, fiscal stress toward austerity, and grievance pushes
    a defaulted creditor toward war and embargo.

API for other systems (diplomacy, tribute)
    :func:`transfer` moves treasury (and specie) between civs;
    :func:`extend_loan` books a loan between two civs on agreed terms;
    :func:`outstanding_debt` / :func:`creditor_claims` read the book.

See ``docs/integration/money-credit.md``.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Iterable

from pydantic import BaseModel, Field

from chronicler.techniques_state import techniques_on

if TYPE_CHECKING:  # pragma: no cover
    from chronicler.models import Civilization, Event, WorldState

# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

#: Default for worlds newly created by the CLI/batch/live entry points
#: (on since the 2026-10 all-on full gate; ``--no-finance`` opts out; loaded
#: worlds keep their saved setting).
DEFAULT_ENABLED_FOR_NEW_WORLDS = True

#: Lender id of the domestic merchant/elite creditor class.
DOMESTIC = -1

# ---------------------------------------------------------------------------
# Calibration ([CALIBRATE] values are documented in docs/integration/money-credit.md)
# ---------------------------------------------------------------------------

# --- money and prices
MONEY_PER_OUTPUT = 6.0        # specie demanded per unit of real output at P = 1
OUTPUT_EMA_ALPHA = 0.05       # smoothing of real output per region
GROWTH_MONETIZATION = 1.0     # share of new output's money demand met at once (commerce brings coin)
DECLINE_DEMONETIZATION = 0.8  # share of lost output's coin that leaves with it at once
SPECIE_FLOW = 0.04            # share of a region's remaining specie gap to demand closed per turn
PRICE_ELASTICITY = 0.5        # pass-through of excess specie to prices (velocity absorbs the rest)
PRICE_ADJUST = 0.1            # share of the gap to the target price closed per turn
PRICE_MIN = 0.25
PRICE_MAX = 25.0
INFLATION_EMA_ALPHA = 0.2
MINT_PER_YIELD = 12.0         # silver minted per unit of effective precious yield per turn
ROYAL_SHARE = 0.2             # crown's share of new bullion (paid into the treasury)
SACK_SHARE = 0.25             # share of an occupied region's specie carried off
LOAN_SPECIE_SHARE = 0.25      # share of a foreign loan (or its service) that moves as specie
TRANSFER_SPECIE_SHARE = 1.0   # share of a transfer (tribute, indemnity) that moves as specie

# --- revenue and spending
REVENUE_EMA_ALPHA = 0.2
TAX_INDEXATION = 0.75         # share of revenue that is ad valorem (follows prices)
ARMY_UPKEEP_PER_MILITARY = 0.15
ADMIN_PER_REGION = 1.0
ADMIN_PER_100_POP = 1.0
COURT_REVENUE_SHARE = 0.3     # court and patronage: share of smoothed revenue (at a full reserve)
COURT_CONSUMPTION_WEIGHT = 0.5  # extra court share per unit of the elite consumption ratchet
RESERVE_TURNS = 8.0           # reserve target in turns of revenue
RESERVE_TECH_MARGIN = 1.5     # ... and at least this times the next tech advance
SURPLUS_SPEND_RATE = 0.08     # share of the surplus above the reserve spent on the court
PREPAY_RATE = 0.5             # share of the surplus above the reserve used to prepay debt
INDEBTED_RESERVE_SHARE = 0.5  # an indebted state repays from above this share of its reserve
INDEBTED_COURT_TURNS = 2.0    # court spending halves at this many turns of revenue owed

# --- credit
MIN_RESERVE_TURNS = 1.0       # borrow when the treasury would not cover obligations plus this many turns of upkeep
WAR_CHEST_SHARE = 1.0         # at war, borrow to keep this share of the reserve target
WAR_COURT_SHARE = 0.5         # the court's share of its peacetime spending while at war
DEBT_CEILING_TURNS = 10.0     # creditors stop lending at this many turns of revenue
MIN_LOAN = 10
BORROW_BUFFER_TURNS = 3.0     # a loan covers the gap plus this many turns of upkeep
LOAN_EVENT_TURNS = 1.0        # an advance on an open line of at least this many turns of revenue ...
LOAN_EVENT_GROWTH = 0.5       # ... that also grows the line by this share is an event
LOAN_TERM = 20
MAX_NEW_LOANS = 2             # per civ per turn
DOMESTIC_RATE = 0.04          # per turn (one turn is a year)
FOREIGN_RATE = 0.06
RATE_PER_DEBT_TURN = 0.003    # premium per turn of revenue already owed
MAX_RATE = 0.25
DOMESTIC_WEALTH_SHARE = 0.5   # creditor class lends up to this share of merchant wealth
DOMESTIC_REVENUE_TURNS = 3.0  # ... plus this many turns of revenue times merchant influence
OFF_MERCHANT_WEALTH = 1.5     # --agents off: merchant wealth proxy per economy point per region
FOREIGN_LEND_SHARE = 0.5      # share of a lender's free treasury it will lend
LENDER_RESERVE_SHARE = 0.5    # a lender keeps this share of its reserve target ...
LENDER_MIN_RESERVE_TURNS = 4.0  # ... and at least this many turns of its obligations
TRUST_RECOVERY = 0.02         # domestic trust regained per turn (toward 1)

# --- default and arrears
ARREARS_LIMIT = 2             # turns of material arrears before a default
ARREARS_MATERIAL_SHARE = 0.25  # unpaid share of the service due that counts as arrears
DEFAULT_MIN_DEBT_TURNS = 1.0  # debts below this many turns of revenue are rolled over, not repudiated
DEFAULT_GRACE = 8             # turns after a restructuring before arrears count again
CREDIT_EXCLUSION_TURNS = 15   # foreign lenders shun a defaulter this long per default (up to 3)
EXCLUDED_DOMESTIC_SHARE = 0.25  # share of domestic capacity still offered while excluded
DEFAULT_HAIRCUT = 0.5
REPEAT_HAIRCUT = 0.8           # write-off when the last default is still remembered (memory >= 0.5)
DEFAULT_STABILITY = 10
DEFAULT_ECONOMY = 3
DEFAULT_LEGITIMACY = 0.1
DEFAULT_MERCHANT_INFLUENCE = 0.05
DEFAULT_PREMIUM = 0.04
DEFAULT_TRUST = 0.5           # domestic trust multiplier after a default
PREMIUM_DECAY = 0.97
DEFAULT_MEMORY_DECAY = 0.98
GRIEVANCE_DECAY = 0.97
UNPAID_UPKEEP_MILITARY = 2
UNPAID_UPKEEP_STABILITY = 2

# --- debasement
DEBASE_STEP = 0.15
MIN_FINENESS = 0.25
DEBASE_COOLDOWN = 15
DEBASE_MIN_SHORTFALL = 0.25   # debase only for a shortfall of this share of obligations
SEIGNIORAGE_SHARE = 0.5       # crown's share of the nominal coin added by recoinage
DEBASE_PREMIUM = 0.01
DEBASE_STABILITY = 2
DEBASE_MERCHANT_INFLUENCE = 0.02

# --- inflation consequences
INFLATION_UNREST = 0.03       # per-turn inflation above which stability suffers
INFLATION_STABILITY_PER_PCT = 0.5
INFLATION_STABILITY_CAP = 4
INFLATION_REPORT = 0.02       # per-turn inflation reported as a price-inflation episode

# --- fiscal stress and the PSI
DEBT_REFERENCE_TURNS = 10.0
STRESS_CAP = 4.0
ARREARS_STRESS = 0.5
DEFAULT_STRESS = 1.0
DEFAULT_STRESS_TURNS = 10.0
INFLATION_STRESS = 10.0       # stress per unit of smoothed per-turn inflation
STRAIN_REPORT = 1.0           # fiscal stress reported as a fiscal-strain episode
SFD_SCALE = 0.04              # raw SFD per unit of fiscal stress (governance sfd_reference)

# --- action-weight leverage
LEVERAGE_WEIGHT = 0.15
AUSTERITY_WEIGHT = 0.1
GRIEVANCE_WEIGHT = 0.2
FINANCE_WEIGHT_CEILING = 1.25

_TOTAL_KEYS = ("issued_domestic", "issued_foreign", "repaid_principal", "interest_domestic",
               "interest_foreign", "capitalized", "written_off", "seigniorage", "royal_bullion")


# ---------------------------------------------------------------------------
# Persisted state
# ---------------------------------------------------------------------------

class Loan(BaseModel):
    """One outstanding loan. Principal and payments are whole treasury units."""

    loan_id: str
    borrower: int
    lender: int                 # civ index, or DOMESTIC
    principal: int
    original: int               # principal at issue (or at the last rescheduling)
    rate: float                 # per turn
    term: int
    issued_turn: int
    interest_carry: float = 0.0  # fractional interest not yet due as a whole unit
    capitalized: int = 0         # unpaid interest added to the principal so far
    event_id: str = ""           # provenance id of the loan's ``loan_taken`` event


class CivFinance(BaseModel):
    initialized: bool = False
    price_index: float = 1.0
    target_price: float = 1.0
    inflation: float = 0.0        # last turn's change of the price index
    inflation_ema: float = 0.0
    fineness: float = 1.0
    revenue_ema: float = 0.0
    merchant_wealth: float = 0.0  # creditor class wealth (smoothed)
    cost_carry: float = 0.0
    royal_bullion: float = 0.0    # crown share of new bullion awaiting the next fiscal tick
    domestic_trust: float = 1.0
    credit_premium: float = 0.0
    default_memory: float = 0.0
    arrears_turns: int = 0
    grace_until: int | None = None  # no default before this turn (after a restructuring)
    excluded_until: int | None = None  # foreign creditors refuse until this turn (after a default)
    fiscal_stress: float = 0.0
    defaults: int = 0
    debasements: int = 0
    last_default_turn: int | None = None
    last_debasement_turn: int | None = None
    # creditor side: grievance toward defaulted debtors (debtor civ index -> grievance)
    grievance: dict[int, float] = Field(default_factory=dict)
    # last fiscal tick (whole treasury units)
    last_revenue: int = 0
    last_upkeep: int = 0
    last_court: int = 0
    last_service: int = 0
    last_interest: int = 0
    last_borrowed: int = 0
    last_shortfall: int = 0
    # cumulative accounts
    borrowed_total: int = 0
    repaid_total: int = 0
    interest_total: int = 0
    written_off_total: int = 0
    seigniorage_total: int = 0
    loot_specie: float = 0.0      # specie carried home from sacks (cumulative)


class FinanceState(BaseModel):
    last_tick_turn: int = -1
    last_money_turn: int = -1
    civs: list[CivFinance] = Field(default_factory=list)
    loans: list[Loan] = Field(default_factory=list)
    next_loan: int = 0
    region_specie: list[float] = Field(default_factory=list)
    region_output: list[float] = Field(default_factory=list)
    region_occupier: list[int] = Field(default_factory=list)
    totals: dict[str, int] = Field(default_factory=lambda: {k: 0 for k in _TOTAL_KEYS})


# ---------------------------------------------------------------------------
# Switch helpers
# ---------------------------------------------------------------------------

def finance_enabled(world) -> bool:
    """True only for a real finance state (mocks and ``None`` read as off)."""
    return isinstance(getattr(world, "finance", None), FinanceState)


def set_finance_enabled(world: "WorldState", enabled: bool) -> None:
    """Enable (creating an empty state, initialized on the first tick) or disable."""
    if enabled:
        if not finance_enabled(world):
            world.finance = FinanceState()
    else:
        world.finance = None


def _ensure(world: "WorldState") -> FinanceState:
    st = world.finance
    while len(st.civs) < len(world.civilizations):
        st.civs.append(CivFinance())
    n = len(world.regions)
    if len(st.region_specie) < n:
        missing = range(len(st.region_specie), n)
        for r in missing:
            y = _region_output_now(world, r)
            st.region_output.append(y)
            st.region_specie.append(MONEY_PER_OUTPUT * y)
            st.region_occupier.append(_occupier_index(world, world.regions[r]))
    for key in _TOTAL_KEYS:
        st.totals.setdefault(key, 0)
    return st


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _civ_index(world) -> dict[str, int]:
    return {c.name: i for i, c in enumerate(world.civilizations)}


def _occupier_index(world, region) -> int:
    if not region.occupied_by:
        return -1
    for i, c in enumerate(world.civilizations):
        if c.name == region.occupied_by:
            return i
    return -1


def _region_output_now(world, r: int) -> float:
    region = world.regions[r]
    econ = 0
    if region.controller:
        for c in world.civilizations:
            if c.name == region.controller:
                econ = c.economy
                break
    return max(0.0, float(region.population)) * (0.5 + max(0, econ) / 100.0)


def _region_indices(world) -> dict[str, int]:
    return {r.name: i for i, r in enumerate(world.regions)}


def _anchor_region(world, civ, index: dict[str, int]) -> int | None:
    """The civ's capital region index, else its first region."""
    if civ.capital_region in index and civ.capital_region in civ.regions:
        return index[civ.capital_region]
    for name in civ.regions:
        if name in index:
            return index[name]
    return None


def _ema(previous: float, value: float, alpha: float) -> float:
    return previous + alpha * (value - previous)


def _projections(world, acc) -> list[int]:
    """Each civ's treasury as the accumulator will leave it after the changes
    recorded so far (``keep`` treasury changes after the applied watermark,
    each floored at zero and truncated exactly as ``StatAccumulator`` does)."""
    proj = [int(c.treasury) for c in world.civilizations]
    if acc is None:
        return proj
    start = getattr(acc, "_keep_applied_up_to", 0)
    for change in acc._changes[start:]:
        if change.stat == "treasury" and change.category == "keep" and change.civ_id < len(proj):
            proj[change.civ_id] = int(max(proj[change.civ_id] + change.delta, 0))
    return proj


def _turn_revenue(acc, civ_idx: int, civ) -> int:
    """Ordinary revenue recorded so far this turn: positive ``keep`` treasury changes."""
    if acc is None:
        return max(0, int(getattr(civ, "last_income", 0)))
    total = 0.0
    for change in acc._changes:
        if (change.civ_id == civ_idx and change.stat == "treasury"
                and change.category == "keep" and change.delta > 0):
            total += change.delta
    return int(total)


def _turn_spending(acc, civ_idx: int) -> int:
    """Treasury spending recorded so far this turn: negative ``keep`` treasury changes
    (governing costs, military maintenance, war costs, institutions)."""
    if acc is None:
        return 0
    total = 0.0
    for change in acc._changes:
        if (change.civ_id == civ_idx and change.stat == "treasury"
                and change.category == "keep" and change.delta < 0):
            total -= change.delta
    return int(total)


class _Book:
    """Treasury writer for one fiscal tick: keeps the projections exact."""

    def __init__(self, world, acc):
        self.world = world
        self.acc = acc
        self.proj = _projections(world, acc)

    def add(self, civ_idx: int, delta: int) -> int:
        """Credit (or debit, never below zero) a treasury; returns the change made."""
        delta = int(delta)
        if delta < 0:
            delta = max(delta, -self.proj[civ_idx])
        if delta == 0:
            return 0
        civ = self.world.civilizations[civ_idx]
        if self.acc is not None:
            self.acc.add(civ_idx, civ, "treasury", delta, "keep")
        else:
            civ.treasury = max(0, civ.treasury + delta)
        self.proj[civ_idx] += delta
        return delta


def _stat(world, acc, civ_idx: int, stat: str, delta: int, category: str) -> None:
    if not delta:
        return
    civ = world.civilizations[civ_idx]
    if acc is not None:
        acc.add(civ_idx, civ, stat, delta, category)
    else:
        from chronicler.utils import STAT_FLOOR, clamp
        setattr(civ, stat, clamp(getattr(civ, stat) + delta, STAT_FLOOR.get(stat, 0), 100))


def _shift_merchant_influence(civ, delta: float) -> None:
    from chronicler.factions import normalize_influence
    from chronicler.models import FactionType
    inf = civ.factions.influence
    inf[FactionType.MERCHANT] = max(0.0, inf.get(FactionType.MERCHANT, 0.0) + delta)
    normalize_influence(civ.factions)


def _merchant_influence(civ) -> float:
    from chronicler.models import FactionType
    return float(civ.factions.influence.get(FactionType.MERCHANT, 0.0))


def _event(world, event_type: str, civ, description: str, importance: int,
           actors: list[str] | None = None, region: str | None = None) -> "Event":
    from chronicler.models import Event
    return Event(turn=world.turn, event_type=event_type, actors=actors or [civ.name],
                 description=description, importance=importance, civs=[civ.name],
                 region=region)


# ---------------------------------------------------------------------------
# Read API
# ---------------------------------------------------------------------------

def civ_finance(world, civ_idx: int) -> CivFinance | None:
    if not finance_enabled(world) or civ_idx >= len(world.finance.civs):
        return None
    return world.finance.civs[civ_idx]


def loans_of(world, borrower: int) -> list[Loan]:
    if not finance_enabled(world):
        return []
    return [loan for loan in world.finance.loans if loan.borrower == borrower]


def outstanding_debt(world, borrower: int, lender: int | None = None) -> int:
    """Outstanding principal a civ owes (to one lender, or in total)."""
    return sum(loan.principal for loan in loans_of(world, borrower)
               if lender is None or loan.lender == lender)


def foreign_debt(world, borrower: int) -> int:
    return sum(loan.principal for loan in loans_of(world, borrower) if loan.lender != DOMESTIC)


def creditor_claims(world, lender: int) -> dict[int, int]:
    """Outstanding principal owed to ``lender`` (a civ index or DOMESTIC), by borrower."""
    if not finance_enabled(world):
        return {}
    out: dict[int, int] = {}
    for loan in world.finance.loans:
        if loan.lender == lender:
            out[loan.borrower] = out.get(loan.borrower, 0) + loan.principal
    return out


def price_index(world, civ_idx: int) -> float:
    f = civ_finance(world, civ_idx)
    return f.price_index if f is not None else 1.0


# ---------------------------------------------------------------------------
# Write API (for diplomacy: tribute, indemnities, inter-state loans)
# ---------------------------------------------------------------------------

def _move_specie(world, from_idx: int | None, to_idx: int | None, silver: float) -> float:
    """Move silver between two civs' anchor regions (never below zero). Returns the amount moved."""
    st = world.finance
    if silver <= 0:
        return 0.0
    index = _region_indices(world)
    src = _anchor_region(world, world.civilizations[from_idx], index) if from_idx is not None else None
    dst = _anchor_region(world, world.civilizations[to_idx], index) if to_idx is not None else None
    if src is not None:
        silver = min(silver, st.region_specie[src])
        st.region_specie[src] -= silver
    if dst is not None:
        st.region_specie[dst] += silver
    return silver


def transfer(world: "WorldState", payer: int, payee: int, amount: int, *, acc=None) -> int:
    """Move up to ``amount`` treasury from ``payer`` to ``payee`` (civ indices).

    Pays at most the payer's projected treasury (``keep`` changes through
    ``acc``). With finance on, the payment also carries specie between the two
    economies (``TRANSFER_SPECIE_SHARE``), so tribute and indemnities move
    prices. Returns the amount paid. Works with finance off (treasury only).
    """
    if payer == payee or amount <= 0:
        return 0
    book = _Book(world, acc)
    paid = -book.add(payer, -int(amount))
    if paid:
        book.add(payee, paid)
        if finance_enabled(world):
            _ensure(world)
            fineness = world.finance.civs[payer].fineness
            _move_specie(world, payer, payee, TRANSFER_SPECIE_SHARE * paid * fineness)
    return paid


def _new_loan(world, borrower: int, lender: int, principal: int, rate: float, term: int) -> Loan:
    """Book ``principal`` on the borrower's credit line with this lender.

    One line per (borrower, lender): a new advance is added to an open line at
    the principal-weighted blended rate and the whole line is re-amortized
    over ``term`` turns from now; otherwise a new line is opened.
    """
    st = world.finance
    for loan in st.loans:
        if loan.borrower == borrower and loan.lender == lender and loan.principal > 0:
            total = loan.principal + principal
            loan.rate = round((loan.rate * loan.principal + rate * principal) / total, 6)
            loan.principal = total
            loan.original = total
            loan.term = max(1, term)
            return loan
    loan = Loan(loan_id=f"{world.turn}:{borrower}:{st.next_loan}", borrower=borrower, lender=lender,
                principal=principal, original=principal, rate=round(rate, 6), term=max(1, term),
                issued_turn=world.turn)
    st.next_loan += 1
    st.loans.append(loan)
    return loan


def _loan_event(world, civ, f: CivFinance, loan: Loan, amount: int, rate: float, lender, causes: list,
                events: list) -> None:
    """Record material borrowing as a ``loan_taken`` event: opening a credit
    line, or an advance of at least ``LOAN_EVENT_TURNS`` of revenue that also
    grows the line by ``LOAN_EVENT_GROWTH``. Routine top-ups are not events
    (the open fiscal-strain episode covers them); the line keeps its latest id."""
    from chronicler import provenance as prov
    new_line = loan.issued_turn == world.turn and loan.principal == amount
    if not new_line:
        before = loan.principal - amount
        if amount < LOAN_EVENT_TURNS * max(f.revenue_ema, 1.0) or amount < LOAN_EVENT_GROWTH * before:
            return
    if lender is None:
        ev = _event(world, "loan_taken", civ,
                    f"{civ.name} borrows {amount} from its merchant houses at {rate:.1%}.", 4)
    else:
        ev = _event(world, "loan_taken", civ,
                    f"{civ.name} borrows {amount} from {lender.name} at {rate:.1%}.", 5,
                    actors=[civ.name, lender.name])
        ev.civs = [civ.name, lender.name]
    prov.cite(ev, *causes)
    loan.event_id = prov.ensure_id(world, ev)
    events.append(ev)


def extend_loan(world: "WorldState", lender: int, borrower: int, principal: int, *, acc=None,
                rate: float | None = None, term: int | None = None) -> Loan | None:
    """Book a loan from civ ``lender`` to civ ``borrower`` on given terms.

    The lender pays at most its projected treasury; returns the booked loan
    (or None when nothing could be lent or finance is off). The loan is
    serviced by the borrower's fiscal tick like any other.
    """
    if not finance_enabled(world) or lender == borrower or principal <= 0:
        return None
    st = _ensure(world)
    book = _Book(world, acc)
    lent = -book.add(lender, -int(principal))
    if lent <= 0:
        return None
    book.add(borrower, lent)
    f_b = st.civs[borrower]
    if rate is None:
        rate = _loan_rate(world, borrower, f_b, foreign=True)
    loan = _new_loan(world, borrower, lender, lent, rate, LOAN_TERM if term is None else term)
    _move_specie(world, lender, borrower, LOAN_SPECIE_SHARE * lent * st.civs[lender].fineness)
    st.totals["issued_foreign"] += lent
    f_b.borrowed_total += lent
    return loan


# ---------------------------------------------------------------------------
# Credit terms
# ---------------------------------------------------------------------------

def _loan_rate(world, civ_idx: int, f: CivFinance, *, foreign: bool) -> float:
    debt_turns = outstanding_debt(world, civ_idx) / max(f.revenue_ema, 1.0)
    base = FOREIGN_RATE if foreign else DOMESTIC_RATE
    rate = base + RATE_PER_DEBT_TURN * debt_turns + f.credit_premium + max(0.0, f.inflation_ema)
    return min(MAX_RATE, rate)


def _debt_ceiling(f: CivFinance) -> float:
    return DEBT_CEILING_TURNS * max(f.revenue_ema, 1.0) / (1.0 + f.default_memory)


def _merchant_wealth_now(world, civ_idx: int, civ, economy_result) -> float:
    """Creditor class wealth: merchant agent wealth (the goods economy's tax
    base) in agent modes, an economy-and-size proxy with ``--agents off``."""
    if economy_result is not None:
        from chronicler.economy import TAX_RATE
        tax = economy_result.treasury_tax.get(civ_idx)
        if tax is not None and TAX_RATE > 0:
            return max(0.0, float(tax) / TAX_RATE)
    return OFF_MERCHANT_WEALTH * max(0, civ.economy) * len(civ.regions)


def _domestic_capacity(world, civ_idx: int, civ, f: CivFinance) -> int:
    capacity = (DOMESTIC_WEALTH_SHARE * f.merchant_wealth
                + DOMESTIC_REVENUE_TURNS * f.revenue_ema * _merchant_influence(civ)) * f.domestic_trust
    if techniques_on(world):
        # --techniques: coinage, banking and bookkeeping deepen domestic credit.
        from chronicler.techniques import credit_factor
        capacity *= credit_factor(world, civ_idx)
    return max(0, int(capacity) - outstanding_debt(world, civ_idx, DOMESTIC))


def _at_war(world, a: str, b: str) -> bool:
    return (a, b) in world.active_wars or (b, a) in world.active_wars


def _in_contact(world, a, b, index: dict[str, int]) -> float:
    """Contact intensity between two civs: contact-ledger flows when the ledger
    is on, else 1 for goods trade-route partners or neighbours."""
    from chronicler.contact_ledger import civ_contact, ledger_enabled
    if ledger_enabled(world):
        return civ_contact(world, a.name, b.name)
    a_regions = set(a.regions)
    for name in b.regions:
        r = world.regions[index[name]] if name in index else None
        if r is not None and any(adj in a_regions for adj in r.adjacencies):
            return 1.0
    return 0.0


def _reserve_target(civ, f: CivFinance) -> int:
    from chronicler.tech import TECH_REQUIREMENTS
    reqs = TECH_REQUIREMENTS.get(civ.tech_era)
    tech = reqs[2] * RESERVE_TECH_MARGIN if reqs is not None else 0.0
    return int(max(RESERVE_TURNS * f.revenue_ema, tech))


# ---------------------------------------------------------------------------
# Fiscal tick (Phase 3b)
# ---------------------------------------------------------------------------

class _Plan:
    """One civ's obligations this turn."""

    __slots__ = ("upkeep", "dues")

    def __init__(self, upkeep: int, dues: list[tuple[Loan, int, int, float]]):
        self.upkeep = upkeep
        self.dues = dues  # (loan, interest due, amortization due, new interest carry)

    @property
    def service(self) -> int:
        return sum(i + a for _, i, a, _ in self.dues)


def _plan(world, civ_idx: int, civ, f: CivFinance) -> _Plan:
    p = f.price_index
    upkeep_f = (ARMY_UPKEEP_PER_MILITARY * max(0, civ.military)
                + ADMIN_PER_REGION * len(civ.regions)
                + ADMIN_PER_100_POP * max(0, civ.population) / 100.0) * p + f.cost_carry
    upkeep = int(upkeep_f)
    f.cost_carry = upkeep_f - upkeep
    dues = []
    for loan in world.finance.loans:
        if loan.borrower != civ_idx or loan.principal <= 0:
            continue
        accrued = loan.principal * loan.rate + loan.interest_carry
        interest = int(accrued)
        amort = min(loan.principal, int(math.ceil(loan.original / max(1, loan.term))))
        dues.append((loan, interest, amort, accrued - interest))
    return _Plan(upkeep, dues)


def _write_off_dead(world, events: list) -> None:
    """Loans of fallen borrowers (and owed to fallen lenders) are lost."""
    st = world.finance
    keep = []
    for loan in st.loans:
        borrower = world.civilizations[loan.borrower]
        lender_dead = loan.lender != DOMESTIC and not world.civilizations[loan.lender].regions
        if borrower.regions and not lender_dead and loan.principal > 0:
            keep.append(loan)
            continue
        if loan.principal > 0:
            st.totals["written_off"] += loan.principal
            st.civs[loan.borrower].written_off_total += loan.principal
        if loan.principal >= MIN_LOAN:
            from chronicler import provenance as prov
            if not borrower.regions:
                who = "its own merchants" if loan.lender == DOMESTIC else world.civilizations[loan.lender].name
                ev = _event(world, "debt_written_off", borrower,
                            f"With {borrower.name} gone, {loan.principal} owed to {who} is lost.", 3)
                if loan.lender != DOMESTIC:
                    ev.actors.append(who)
                    ev.civs.append(who)
            else:
                lender = world.civilizations[loan.lender]
                ev = _event(world, "debt_written_off", borrower,
                            f"With {lender.name} gone, the {loan.principal} {borrower.name} owed it lapses.", 4,
                            actors=[borrower.name, lender.name])
                ev.civs = [borrower.name, lender.name]
                prov.cite(ev, prov.recall(world, prov.key("collapse", lender.name), within=5),
                          prov.recall(world, prov.key("conquered", lender.name), within=5),
                          prov.recall(world, prov.key("twilight", lender.name), within=5))
            prov.cite(ev, loan.event_id or None)
            events.append(ev)
    st.loans = keep


class _Lenders:
    """Foreign lending capacity during one fiscal tick.

    A debt-free civ without arrears lends ``FOREIGN_LEND_SHARE`` of its
    treasury above its reserve and (until its own tick has paid them) its
    obligations; the cap is fixed at the start of the tick and the room is
    re-read from the live projection, so lending never depends on which civ
    happens to be processed first beyond what it has actually spent.
    """

    def __init__(self, n: int):
        self.cap = [0] * n
        self.reserve = [0] * n
        self.pending = [0] * n

    def room(self, j: int, book: _Book) -> int:
        live = book.proj[j] - self.reserve[j] - self.pending[j]
        return max(0, min(self.cap[j], int(FOREIGN_LEND_SHARE * live)))


def _borrow(world, civ_idx: int, civ, f: CivFinance, gap: int, book: _Book, lenders: _Lenders,
            index: dict[str, int], events: list, causes: list) -> int:
    """Raise up to ``gap`` (domestic first, then foreign). Returns the amount raised."""
    from chronicler.models import Disposition
    st = world.finance
    raised = 0
    ceiling = _debt_ceiling(f)
    if techniques_on(world):
        # --techniques: practised banking lets creditors carry more debt.
        from chronicler.techniques import credit_factor
        ceiling *= credit_factor(world, civ_idx)
    headroom = int(ceiling) - outstanding_debt(world, civ_idx)
    gap = min(gap, headroom)
    loans_made = 0
    excluded = f.excluded_until is not None and world.turn < f.excluded_until
    if gap >= MIN_LOAN:
        capacity = _domestic_capacity(world, civ_idx, civ, f)
        if excluded:
            capacity = int(EXCLUDED_DOMESTIC_SHARE * capacity)
        dom = min(gap, capacity)
        if dom >= MIN_LOAN:
            rate = _loan_rate(world, civ_idx, f, foreign=False)
            loan = _new_loan(world, civ_idx, DOMESTIC, dom, rate, LOAN_TERM)
            book.add(civ_idx, dom)
            st.totals["issued_domestic"] += dom
            f.borrowed_total += dom
            raised += dom
            gap -= dom
            loans_made += 1
            _loan_event(world, civ, f, loan, dom, rate, None, causes, events)
    while gap >= MIN_LOAN and loans_made < MAX_NEW_LOANS and not excluded:
        best = None
        for j, other in enumerate(world.civilizations):
            if j == civ_idx or not other.regions:
                continue
            room = lenders.room(j, book)
            if room < MIN_LOAN:
                continue
            if _at_war(world, civ.name, other.name):
                continue
            if st.civs[j].grievance.get(civ_idx, 0.0) >= 0.5:
                continue  # burned creditors refuse
            rel = world.relationships.get(other.name, {}).get(civ.name)
            if rel is not None and rel.disposition == Disposition.HOSTILE:
                continue
            contact = _in_contact(world, other, civ, index)
            if contact <= 0:
                continue
            score = room * (1.0 + min(contact, 20.0) / 10.0)
            if best is None or score > best[0]:
                best = (score, j, room)
        if best is None:
            break
        _, j, room = best
        lender = world.civilizations[j]
        rate = _loan_rate(world, civ_idx, f, foreign=True)
        lent = -book.add(j, -min(gap, room))
        if lent <= 0:
            break
        lenders.cap[j] -= lent
        book.add(civ_idx, lent)
        loan = _new_loan(world, civ_idx, j, lent, rate, LOAN_TERM)
        _move_specie(world, j, civ_idx, LOAN_SPECIE_SHARE * lent * st.civs[j].fineness)
        st.totals["issued_foreign"] += lent
        f.borrowed_total += lent
        raised += lent
        gap -= lent
        loans_made += 1
        _loan_event(world, civ, f, loan, lent, rate, lender, causes, events)
    return raised


def _debase(world, civ_idx: int, civ, f: CivFinance, book: _Book, index: dict[str, int],
            acc, events: list, causes: list) -> int:
    from chronicler import provenance as prov
    if f.fineness * (1.0 - DEBASE_STEP) < MIN_FINENESS - 1e-12:
        return 0
    if f.last_debasement_turn is not None and world.turn - f.last_debasement_turn < DEBASE_COOLDOWN:
        return 0
    st = world.finance
    silver = sum(st.region_specie[index[n]] for n in civ.regions if n in index)
    nominal = silver / max(f.fineness, 1e-9)
    gain = int(SEIGNIORAGE_SHARE * nominal * DEBASE_STEP / (1.0 - DEBASE_STEP))
    if gain < max(MIN_LOAN, f.revenue_ema):
        return 0
    f.fineness = round(f.fineness * (1.0 - DEBASE_STEP), 9)
    f.debasements += 1
    f.last_debasement_turn = world.turn
    f.credit_premium += DEBASE_PREMIUM
    gain = book.add(civ_idx, gain)
    st.totals["seigniorage"] += gain
    f.seigniorage_total += gain
    _stat(world, acc, civ_idx, "stability", -DEBASE_STABILITY, "signal")
    _shift_merchant_influence(civ, -DEBASE_MERCHANT_INFLUENCE)
    ev = _event(world, "debasement", civ,
                f"{civ.name} debases its coinage to {f.fineness:.0%} silver, raising {gain}.", 6,
                region=civ.capital_region if civ.capital_region in civ.regions else None)
    prov.cite(ev, *causes)
    prov.ensure_id(world, ev)
    events.append(ev)
    return gain


def _default(world, civ_idx: int, civ, f: CivFinance, acc, events: list, causes: list) -> None:
    from chronicler import provenance as prov
    from chronicler.culture import _downgrade_disposition
    st = world.finance
    written = 0
    foreign: dict[int, int] = {}
    domestic = 0
    loan_ids: list[str] = []
    haircut = REPEAT_HAIRCUT if f.default_memory >= 0.5 else DEFAULT_HAIRCUT
    for loan in st.loans:
        if loan.borrower != civ_idx or loan.principal <= 0:
            continue
        cut = int(loan.principal * haircut)
        loan.principal -= cut
        loan.original = loan.principal
        loan.term = LOAN_TERM
        loan.interest_carry = 0.0
        # Rescheduled at the plain base rate of its kind.
        loan.rate = min(loan.rate, DOMESTIC_RATE if loan.lender == DOMESTIC else FOREIGN_RATE)
        written += cut
        if loan.lender == DOMESTIC:
            domestic += cut
        else:
            foreign[loan.lender] = foreign.get(loan.lender, 0) + cut
        if loan.event_id:
            loan_ids.append(loan.event_id)
    st.loans = [loan for loan in st.loans if loan.principal > 0]
    st.totals["written_off"] += written
    f.written_off_total += written
    f.defaults += 1
    f.last_default_turn = world.turn
    f.arrears_turns = 0
    f.grace_until = world.turn + DEFAULT_GRACE
    f.excluded_until = world.turn + CREDIT_EXCLUSION_TURNS * min(3, f.defaults)
    f.credit_premium += DEFAULT_PREMIUM
    f.default_memory += 1.0
    _stat(world, acc, civ_idx, "stability", -DEFAULT_STABILITY, "signal")
    gov = getattr(civ, "governance", None)
    if gov is not None and getattr(world, "governance", None) is not None:
        gov.ruler_legitimacy = max(0.0, gov.ruler_legitimacy - DEFAULT_LEGITIMACY)
    if domestic:
        f.domestic_trust *= DEFAULT_TRUST
        _stat(world, acc, civ_idx, "economy", -DEFAULT_ECONOMY, "signal")
        _shift_merchant_influence(civ, -DEFAULT_MERCHANT_INFLUENCE)
    lender_names = []
    for j in sorted(foreign):
        lender = world.civilizations[j]
        lender_names.append(lender.name)
        lf = st.civs[j]
        share = foreign[j] / max(lf.revenue_ema * 5.0, 1.0)
        lf.grievance[civ_idx] = round(lf.grievance.get(civ_idx, 0.0) + 0.5 + min(1.0, share), 6)
        rel = world.relationships.get(lender.name, {}).get(civ.name)
        if rel is not None:
            rel.disposition = _downgrade_disposition(rel.disposition)
    whom = ", ".join(lender_names + (["its merchant houses"] if domestic else [])) or "its creditors"
    ev = _event(world, "state_default", civ,
                f"{civ.name} defaults on its debts, repudiating {written} owed to {whom}.", 8,
                actors=[civ.name, *lender_names],
                region=civ.capital_region if civ.capital_region in civ.regions else None)
    ev.civs = [civ.name, *lender_names]
    prov.cite(ev, *loan_ids[-4:], *causes)
    prov.ensure_id(world, ev)
    events.append(ev)


def _deficit_causes(world, civ) -> list[str | None]:
    """What drained the treasury: wars, revolts, famines, plague, occupation."""
    from chronicler import provenance as prov
    out: list[str | None] = [*prov._wars_of(world, civ.name)]
    out += [prov.recall(world, prov.key("revolt", civ.name), within=10),
            prov.recall(world, prov.key("civil_war", civ.name), within=20),
            prov.recall(world, prov.key("plague", civ.name), within=10),
            *prov._famines_of(world, civ.name, limit=1)]
    for name in civ.regions:
        out.append(prov.recall(world, prov.key("occupation", name)))
    return out


def tick_finance(world: "WorldState", acc=None, economy_result=None) -> list["Event"]:
    """Phase 3b: revenue, upkeep, debt service, borrowing, debasement, default."""
    if not finance_enabled(world):
        return []
    from chronicler import provenance as prov
    st = _ensure(world)
    events: list = []
    turn = world.turn
    st.last_tick_turn = turn
    _write_off_dead(world, events)
    book = _Book(world, acc)
    index = _region_indices(world)

    # Revenue and creditor wealth first (lender capacities need every civ's reserve).
    revenue: dict[int, int] = {}
    spending: dict[int, int] = {}
    indexation: dict[int, int] = {}
    for civ_idx, civ in enumerate(world.civilizations):
        f = st.civs[civ_idx]
        f.grievance = {d: round(g * GRIEVANCE_DECAY, 6) for d, g in sorted(f.grievance.items())
                       if g * GRIEVANCE_DECAY >= 0.01}
        if not civ.regions:
            continue
        base = _turn_revenue(acc, civ_idx, civ)
        # Ad valorem revenue follows prices (nominal revenue is what the books see).
        indexation[civ_idx] = int(round(TAX_INDEXATION * (f.price_index - 1.0) * base))
        r = max(0, base + indexation[civ_idx])
        revenue[civ_idx] = r
        spending[civ_idx] = _turn_spending(acc, civ_idx)
        wealth = _merchant_wealth_now(world, civ_idx, civ, economy_result)
        if not f.initialized:
            f.initialized = True
            f.revenue_ema = float(r)
            f.merchant_wealth = wealth
        else:
            f.revenue_ema = _ema(f.revenue_ema, r, REVENUE_EMA_ALPHA)
            f.merchant_wealth = _ema(f.merchant_wealth, wealth, REVENUE_EMA_ALPHA)
        f.credit_premium = round(f.credit_premium * PREMIUM_DECAY, 9)
        f.default_memory = round(f.default_memory * DEFAULT_MEMORY_DECAY, 9)
        f.domestic_trust = min(1.0, f.domestic_trust + TRUST_RECOVERY * (1.0 - f.domestic_trust))
        f.last_revenue = r

    plans: dict[int, _Plan] = {}
    lenders = _Lenders(len(world.civilizations))
    for civ_idx in revenue:
        civ = world.civilizations[civ_idx]
        f = st.civs[civ_idx]
        plans[civ_idx] = plan = _plan(world, civ_idx, civ, f)
        if outstanding_debt(world, civ_idx) == 0 and f.arrears_turns == 0:
            obligations = plan.upkeep + plan.service
            lenders.reserve[civ_idx] = max(int(LENDER_RESERVE_SHARE * _reserve_target(civ, f)),
                                           int(LENDER_MIN_RESERVE_TURNS * obligations))
            lenders.pending[civ_idx] = obligations
            free = book.proj[civ_idx] - lenders.reserve[civ_idx] - obligations
            lenders.cap[civ_idx] = max(0, int(FOREIGN_LEND_SHARE * free)) if f.revenue_ema > 0 else 0

    for civ_idx in revenue:
        civ = world.civilizations[civ_idx]
        f = st.civs[civ_idx]
        plan = plans[civ_idx]
        r = revenue[civ_idx]
        spent = spending[civ_idx]
        # 1. Ad valorem revenue follows prices; the crown's bullion is paid in.
        book.add(civ_idx, indexation[civ_idx])
        royal = int(f.royal_bullion)
        if royal:
            f.royal_bullion -= royal
            book.add(civ_idx, royal)
            st.totals["royal_bullion"] += royal
        upkeep, service = plan.upkeep, plan.service
        obligations = upkeep + service
        floor = int(MIN_RESERVE_TURNS * upkeep)
        causes = _deficit_causes(world, civ)
        reserve = _reserve_target(civ, f)
        # 2. Financing gap: borrow (wars are fought on credit: a belligerent
        # keeps a war chest), then debase.
        borrowed = 0
        target = obligations + floor
        at_war = any(civ.name in pair for pair in world.active_wars)
        if at_war:
            target = max(target, int(WAR_CHEST_SHARE * reserve))
        if book.proj[civ_idx] < target:
            request = target - book.proj[civ_idx] + int(BORROW_BUFFER_TURNS * upkeep)
            borrowed = _borrow(world, civ_idx, civ, f, request, book, lenders, index, events, causes)
        short = obligations - book.proj[civ_idx]
        if f.arrears_turns >= 1 and short > 0 and short >= DEBASE_MIN_SHORTFALL * obligations:
            _debase(world, civ_idx, civ, f, book, index, acc, events,
                    causes + [ev.event_id for ev in events[-2:] if ev.civs and ev.civs[0] == civ.name])
        # 3. Pay upkeep, then debt service (oldest loan first).
        upkeep_paid = -book.add(civ_idx, -upkeep)
        lenders.pending[civ_idx] = 0
        unpaid_service = 0
        interest_paid = 0
        principal_paid = 0
        for loan, interest, amort, carry in plan.dues:
            due = interest + amort
            pay = -book.add(civ_idx, -due)
            pay_interest = min(pay, interest)
            pay_principal = pay - pay_interest
            loan.interest_carry = round(carry, 9)
            if interest > pay_interest:  # unpaid interest is capitalized
                loan.principal += interest - pay_interest
                loan.capitalized += interest - pay_interest
                st.totals["capitalized"] += interest - pay_interest
            loan.principal -= pay_principal
            unpaid_service += due - pay
            interest_paid += pay_interest
            principal_paid += pay_principal
            if loan.lender == DOMESTIC:
                st.totals["interest_domestic"] += pay_interest
            else:
                book.add(loan.lender, pay)
                st.totals["interest_foreign"] += pay_interest
                _move_specie(world, civ_idx, loan.lender, LOAN_SPECIE_SHARE * pay * f.fineness)
            st.totals["repaid_principal"] += pay_principal
        f.repaid_total += principal_paid
        f.interest_total += interest_paid
        st.loans = [loan for loan in st.loans if loan.principal > 0]
        # 4. Arrears (a material share of upkeep and service unpaid) and default.
        unpaid = (upkeep - upkeep_paid) + unpaid_service
        material = unpaid > 0 and unpaid >= ARREARS_MATERIAL_SHARE * obligations
        f.arrears_turns = f.arrears_turns + 1 if material else 0
        debt = outstanding_debt(world, civ_idx)
        if (f.arrears_turns >= ARREARS_LIMIT and unpaid_service > 0
                and debt >= max(2 * MIN_LOAN, DEFAULT_MIN_DEBT_TURNS * f.revenue_ema)
                and (f.grace_until is None or turn >= f.grace_until)):
            _default(world, civ_idx, civ, f, acc, events, causes)
        # 5. Surplus: prepay debt (an indebted state at peace that did not just
        # borrow repays from above half its reserve), then the court.
        debt = outstanding_debt(world, civ_idx)
        surplus = book.proj[civ_idx] - (int(INDEBTED_RESERVE_SHARE * reserve) if debt else reserve)
        if surplus > 0 and debt and not borrowed and not at_war:
            prepay_budget = int(PREPAY_RATE * surplus)
            for loan in sorted((ln for ln in st.loans if ln.borrower == civ_idx),
                               key=lambda ln: (-ln.rate, ln.loan_id)):
                if prepay_budget <= 0:
                    break
                pay = -book.add(civ_idx, -min(prepay_budget, loan.principal))
                loan.principal -= pay
                prepay_budget -= pay
                principal_paid += pay
                f.repaid_total += pay
                st.totals["repaid_principal"] += pay
                if loan.lender != DOMESTIC:
                    book.add(loan.lender, pay)
                    _move_specie(world, civ_idx, loan.lender, LOAN_SPECIE_SHARE * pay * f.fineness)
            st.loans = [loan for loan in st.loans if loan.principal > 0]
        court_factor = 1.0
        gov = getattr(civ, "governance", None)
        if gov is not None:
            court_factor += COURT_CONSUMPTION_WEIGHT * min(2.0, max(0.0, gov.conspicuous_consumption_index))
        # The court economizes while the reserve is short or debts are owed,
        # and spends part of any idle surplus above the reserve.
        fullness = min(1.0, book.proj[civ_idx] / max(reserve, 1))
        restraint = 1.0 / (1.0 + outstanding_debt(world, civ_idx) / (INDEBTED_COURT_TURNS * max(f.revenue_ema, 1.0)))
        court = (COURT_REVENUE_SHARE * f.revenue_ema * court_factor * fullness * restraint
                 * (WAR_COURT_SHARE if at_war else 1.0)
                 + SURPLUS_SPEND_RATE * max(0, book.proj[civ_idx] - reserve))
        court = min(int(court), max(0, book.proj[civ_idx] - floor))
        court = -book.add(civ_idx, -court)
        # 6. Consequences of unpaid upkeep and of last turn's inflation.
        if upkeep_paid < upkeep:
            _stat(world, acc, civ_idx, "military", -UNPAID_UPKEEP_MILITARY, "guard")
            _stat(world, acc, civ_idx, "stability", -UNPAID_UPKEEP_STABILITY, "signal")
        if f.inflation > INFLATION_UNREST:
            hit = min(INFLATION_STABILITY_CAP,
                      int(round((f.inflation - INFLATION_UNREST) * 100 * INFLATION_STABILITY_PER_PCT)))
            _stat(world, acc, civ_idx, "stability", -hit, "signal")
        # 7. Bookkeeping and fiscal stress.
        f.last_upkeep = upkeep_paid
        f.last_court = court
        f.last_service = interest_paid + principal_paid
        f.last_interest = interest_paid
        f.last_borrowed = borrowed
        f.last_shortfall = max(0, upkeep - upkeep_paid) + unpaid_service
        f.fiscal_stress = _fiscal_stress(world, civ_idx, f, spent + upkeep + service, r)
        events.extend(_reports(world, civ_idx, civ, f, causes))
    return events


def _fiscal_stress(world, civ_idx: int, f: CivFinance, obligations: int, revenue: int) -> float:
    rev = max(f.revenue_ema, 1.0)
    debt = outstanding_debt(world, civ_idx)
    service = sum(loan.principal * loan.rate + loan.original / max(1, loan.term)
                  for loan in loans_of(world, civ_idx))
    stress = debt / (rev * DEBT_REFERENCE_TURNS) + service / rev
    stress += max(0.0, obligations - revenue) / rev
    if f.arrears_turns:
        stress += ARREARS_STRESS
    if f.last_default_turn is not None:
        stress += DEFAULT_STRESS * math.exp(-(world.turn - f.last_default_turn) / DEFAULT_STRESS_TURNS)
    stress += INFLATION_STRESS * max(0.0, f.inflation_ema)
    return round(min(STRESS_CAP, stress), 9)


def _reports(world, civ_idx: int, civ, f: CivFinance, causes: list) -> list:
    """Chronic per-turn reports (folded into episodes by provenance)."""
    from chronicler import provenance as prov
    region = civ.capital_region if civ.capital_region in civ.regions else (civ.regions[0] if civ.regions else None)
    if region is None:
        return []
    out = []
    if f.fiscal_stress >= STRAIN_REPORT:
        debt = outstanding_debt(world, civ_idx)
        what = (f"labours under its debts ({debt} owed" if debt
                else "cannot balance its books (spending outruns revenue")
        ev = _event(world, "fiscal_strain", civ,
                    f"{civ.name} {what}, stress {f.fiscal_stress:.1f}).", 5, region=region)
        loan_ids = [loan.event_id for loan in loans_of(world, civ_idx) if loan.event_id][-3:]
        prov.cite(ev, *loan_ids, prov.recall(world, prov.key("default", civ.name), within=20),
                  prov.recall(world, prov.key("debasement", civ.name), within=20), *causes)
        out.append(ev)
    if f.inflation >= INFLATION_REPORT:
        ev = _event(world, "price_inflation", civ,
                    f"Prices in {civ.name} climb {f.inflation:.1%} in a year (index {f.price_index:.2f}).", 4,
                    region=region)
        prov.cite(ev, prov.recall(world, prov.key("debasement", civ.name), within=40),
                  prov.recall(world, prov.key("specie", civ.name), within=40),
                  *[loan.event_id for loan in loans_of(world, civ_idx)
                    if loan.lender != DOMESTIC and loan.event_id][-2:])
        out.append(ev)
    return out


# ---------------------------------------------------------------------------
# Monetary update (end of turn)
# ---------------------------------------------------------------------------

def update_money(world: "WorldState") -> None:
    """Output, sacks, minting, specie flow and prices (read by next turn's tick)."""
    if not finance_enabled(world):
        return
    from chronicler import provenance as prov
    from chronicler.models import ResourceType
    st = _ensure(world)
    st.last_money_turn = world.turn
    civ_index = _civ_index(world)
    index = _region_indices(world)
    civs = world.civilizations
    # Real output per region (smoothed). Commerce monetizes new output at once
    # (coin arrives with the goods); when output falls, part of its coin
    # leaves with it and the rest becomes excess specie (scarcity inflation).
    for r, region in enumerate(world.regions):
        old = st.region_output[r]
        new = round(_ema(old, _region_output_now(world, r), OUTPUT_EMA_ALPHA), 9)
        change = MONEY_PER_OUTPUT * (new - old)
        share = GROWTH_MONETIZATION if change > 0 else DECLINE_DEMONETIZATION
        st.region_specie[r] = max(0.0, st.region_specie[r] + share * change)
        st.region_output[r] = new
    # Sacks: a newly occupied region loses part of its specie to the occupier's capital.
    for r, region in enumerate(world.regions):
        occ = civ_index.get(region.occupied_by, -1) if region.occupied_by else -1
        if occ >= 0 and occ != st.region_occupier[r]:
            dest = _anchor_region(world, civs[occ], index)
            loot = SACK_SHARE * st.region_specie[r]
            if dest is not None and dest != r and loot > 0:
                st.region_specie[r] -= loot
                st.region_specie[dest] += loot
                st.civs[occ].loot_specie = round(st.civs[occ].loot_specie + loot, 6)
                cause = prov.recall(world, prov.key("occupation", region.name))
                if cause:
                    world.provenance.keys[prov.key("specie", civs[occ].name)] = cause
        st.region_occupier[r] = occ
    # Minting: precious-metal slots of populated, controlled regions.
    for r, region in enumerate(world.regions):
        c = civ_index.get(region.controller) if region.controller else None
        if c is None or region.population <= 0:
            continue
        mined = 0.0
        for slot, rtype in enumerate(region.resource_types):
            if rtype == ResourceType.PRECIOUS:
                mined += MINT_PER_YIELD * max(0.0, region.resource_effective_yields[slot]) * min(
                    1.0, max(0.0, region.resource_reserves[slot]))
        if mined > 0:
            st.region_specie[r] += mined
            f = st.civs[c]
            f.royal_bullion = round(f.royal_bullion + ROYAL_SHARE * mined / max(f.fineness, 1e-9), 9)
    # Price-specie flow toward the money demand of each region's output.
    for r in range(len(world.regions)):
        demand = MONEY_PER_OUTPUT * st.region_output[r]
        st.region_specie[r] = round(max(0.0, st.region_specie[r] + SPECIE_FLOW * (demand - st.region_specie[r])), 9)
    # Prices.
    for c, civ in enumerate(civs):
        f = st.civs[c]
        if not civ.regions:
            continue
        silver = sum(st.region_specie[index[n]] for n in civ.regions if n in index)
        demand = MONEY_PER_OUTPUT * sum(st.region_output[index[n]] for n in civ.regions if n in index)
        if demand > 0:
            target = (silver / demand) ** PRICE_ELASTICITY / max(f.fineness, 1e-9)
        else:
            target = f.price_index
        target = min(PRICE_MAX, max(PRICE_MIN, target))
        new_price = min(PRICE_MAX, max(PRICE_MIN, _ema(f.price_index, target, PRICE_ADJUST)))
        f.inflation = round(new_price / f.price_index - 1.0, 9) if f.price_index > 0 else 0.0
        f.inflation_ema = round(_ema(f.inflation_ema, f.inflation, INFLATION_EMA_ALPHA), 9)
        f.price_index = round(new_price, 9)
        f.target_price = round(target, 9)


# ---------------------------------------------------------------------------
# Consumers: PSI and action weights
# ---------------------------------------------------------------------------

def psi_fiscal_distress(world, civ_idx: int, institutional_legitimacy: float,
                        enforcement_cost: float = 0.0) -> float:
    """Raw SFD (the PSI ``state_debt`` input) from fiscal stress.

    ``SFD_SCALE * stress * (1 + enforcement_ratio * (1 - legitimacy))`` with
    the enforcement ratio taken against revenue (roadmap decision D5's
    institutional term); a debt-free, balanced polity is neutral.
    """
    f = civ_finance(world, civ_idx)
    if f is None:
        return 0.0
    legit = min(1.0, max(0.0, institutional_legitimacy))
    enforcement_ratio = max(0.0, enforcement_cost) / max(f.revenue_ema, 1.0)
    return SFD_SCALE * f.fiscal_stress * (1.0 + enforcement_ratio * (1.0 - legit))


def finance_weight_modifiers(world, civ_idx: int) -> dict:
    """Finance contributor bucket of action weights, clamped as one bucket."""
    from chronicler.models import ActionType as A
    f = civ_finance(world, civ_idx)
    if f is None:
        return {}
    mods: dict = {}

    def mul(action, factor: float) -> None:
        mods[action] = mods.get(action, 1.0) * factor

    rev = max(f.revenue_ema, 1.0)
    leverage = min(1.5, foreign_debt(world, civ_idx) / (rev * DEBT_REFERENCE_TURNS))
    if leverage > 0:
        mul(A.WAR, 1.0 - LEVERAGE_WEIGHT * leverage)
        mul(A.TRADE, 1.0 + LEVERAGE_WEIGHT * leverage)
        mul(A.DIPLOMACY, 1.0 + 0.5 * LEVERAGE_WEIGHT * leverage)
    stress = min(2.0, f.fiscal_stress)
    if stress >= 1.0:
        mul(A.BUILD, 1.0 - AUSTERITY_WEIGHT * stress)
        mul(A.DEVELOP, 1.0 - 0.5 * AUSTERITY_WEIGHT * stress)
    grievance = 0.0
    for debtor, g in f.grievance.items():
        if debtor < len(world.civilizations) and world.civilizations[debtor].regions:
            grievance = max(grievance, g)
    if grievance > 0:
        mul(A.WAR, 1.0 + GRIEVANCE_WEIGHT * min(grievance, 1.5))
        mul(A.EMBARGO, 1.0 + GRIEVANCE_WEIGHT * min(grievance, 1.5))
    lo, hi = 1.0 / FINANCE_WEIGHT_CEILING, FINANCE_WEIGHT_CEILING
    return {a: min(hi, max(lo, m)) for a, m in mods.items() if m != 1.0}


# ---------------------------------------------------------------------------
# Viewer snapshot and analytics
# ---------------------------------------------------------------------------

def snapshot_summary(world) -> dict:
    """Per-turn finance summary for ``TurnSnapshot.finance`` (living civs)."""
    st = world.finance
    civs = {}
    for c, civ in enumerate(world.civilizations):
        if not civ.regions or c >= len(st.civs):
            continue
        f = st.civs[c]
        civs[civ.name] = {
            "debt": outstanding_debt(world, c),
            "foreign_debt": foreign_debt(world, c),
            "revenue": f.last_revenue,
            "revenue_ema": round(f.revenue_ema, 3),
            "upkeep": f.last_upkeep,
            "court": f.last_court,
            "debt_service": f.last_service,
            "interest": f.last_interest,
            "borrowed": f.last_borrowed,
            "shortfall": f.last_shortfall,
            "price_index": round(f.price_index, 4),
            "inflation": round(f.inflation, 5),
            "fineness": round(f.fineness, 4),
            "fiscal_stress": round(f.fiscal_stress, 4),
            "arrears_turns": f.arrears_turns,
            "defaults": f.defaults,
            "debasements": f.debasements,
            "credit_premium": round(f.credit_premium, 5),
        }
    return {"civs": civs, "loans": len(st.loans), "totals": dict(sorted(st.totals.items()))}


def extract_finance_metrics(bundles: Iterable[dict]) -> dict:
    """Aggregate finance metrics over bundles that carry ``history[n].finance``."""
    debt_ratio, prices, stress = [], [], []
    defaults = debasements = loans = 0
    runs = 0
    for bundle in bundles:
        history = bundle.get("history") or []
        last = None
        for snap in history:
            fin = snap.get("finance")
            if not fin:
                continue
            last = fin
            for row in fin.get("civs", {}).values():
                debt_ratio.append(row["debt"] / max(row["revenue_ema"], 1.0))
                prices.append(row["price_index"])
                stress.append(row["fiscal_stress"])
        if last is not None:
            runs += 1
            for row in last.get("civs", {}).values():
                defaults += row["defaults"]
                debasements += row["debasements"]
            loans += last.get("loans", 0)
    if not runs:
        return {}

    def pct(values, q):
        if not values:
            return 0.0
        s = sorted(values)
        return s[min(len(s) - 1, int(q * (len(s) - 1)))]

    return {
        "runs": runs,
        "debt_to_revenue": {"p50": pct(debt_ratio, 0.5), "p90": pct(debt_ratio, 0.9), "max": max(debt_ratio)},
        "price_index": {"min": min(prices), "p50": pct(prices, 0.5), "max": max(prices)},
        "fiscal_stress": {"p50": pct(stress, 0.5), "p90": pct(stress, 0.9)},
        "defaults_living_civs_end": defaults,
        "debasements_living_civs_end": debasements,
    }
