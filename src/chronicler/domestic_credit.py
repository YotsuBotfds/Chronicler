"""Domestic credit through real lenders (``--domestic-credit``, default off).

With ``--finance`` (on by default) a state short of money borrows first from
its own creditor class (``finance.DOMESTIC``). Without this switch that class
is abstract: it lends against smoothed merchant wealth and merchant faction
influence, and the interest and repayments it receives leave the treasury
into the finance ledger only. With the switch on, domestic loans are funded
by the actual holders of wealth in the borrower's regions, and every unit of
principal, interest, repayment and loss lands on them:

Who lends
    Three kinds of lender, in the borrowing civ's regions: the **merchants**
    of each region (the merchant agents whose home is the region: native
    agent wealth, read from the live pool), its **guilds** (their purse,
    :mod:`chronicler.guilds`) and its **cities** (the civic purse,
    :mod:`chronicler.cities`) whose lord is the borrower. A lender's assets
    are its wealth plus its outstanding claims; it lends up to
    ``share x assets - claims`` (whole units), where ``share`` is
    ``LEND_SHARE`` times the borrower's domestic trust and the credit factors
    of techniques, great-person agendas and chartered cities, never above
    ``MAX_LEND_SHARE``: a lender always keeps at least a quarter of its
    wealth. The finance tick's request is split among the lenders pro rata
    to what each offers (largest remainder, in index order). The abstract
    revenue-times-influence part of the old capacity lends only while the
    agent pool's wealth is still building up from its cold start: as the
    realm's **merchant houses** (key = the borrower), it offers that term
    times ``(1 - COLD_START_DECAY) ** turn`` (the share of the pool's
    equilibrium wealth not yet accumulated), less what it is owed; its
    receipts leave into the finance ledger.

The borrower's room
    However rich its lenders, a borrower gets no new domestic money that
    would raise its interest due (on every line, domestic and foreign)
    above ``SERVICE_SHARE`` of its smoothed revenue: lenders lend against
    what the borrower can service, not only against what they hold. A state
    at that limit refinances no more than it repays, and pays the rest of
    its service from revenue or falls into arrears.

Cash flows
    The principal leaves the lenders' wealth when lent; interest and
    principal repayments are split among a line's funders pro rata to their
    claims and paid to them; unpaid interest capitalized into the line raises
    their claims the same way; a default's haircut writes their claims down
    pro rata (the losses land on them); a fallen borrower's lines are lost
    to them; a fallen city's or dissolved guild's claims lapse (the borrower
    owes them no more, as debts owed to a fallen foreign lender lapse).
    Guild and city purses change at once. Merchant flows accumulate per
    region in ``merchant_due`` and are sent to the native pool at the end of
    the tick (``AgentSimulator.apply_merchant_transfers``: a debit pro rata
    to wealth, a credit pro rata to wealth up to the wealth ceiling); what
    could not be applied stays due for the next tick. The books are whole
    treasury units; ``CHRONICLER_CHECK_RESOURCES=1`` checks every turn that
    claims, payments, write-offs, purses, the due and the agents' wealth
    reconcile exactly (:class:`_Ledger`).

Consequences (small, capped)
    A default keeps finance's domestic consequences (domestic trust halved,
    economy -3 ``signal``, merchant influence -0.05) and adds, from who
    lost: the merchants of each losing region gain grievance (0..1, decaying
    ``GRIEVANCE_DECAY`` a turn; sent as the region batch's
    ``creditor_grievance`` column, it costs merchants there up to
    ``CREDITOR_GRIEVANCE_WEIGHT`` = 0.10 of satisfaction inside the native
    social-penalty cap); a losing city's grievance rises (its unrest
    target; capped at 1 as before); a guild or city that lost at least
    ``THREAT_SHARE`` of its assets records the repudiation in its history,
    and for a guild it is a threat to its privileges (``guilds_state``
    ``DEFAULT``), which may raise a guild movement as other threats do.
    ``loan_taken`` and ``state_default`` events name who funded the loan and
    who lost; the event of a loan carries the main lending region.

Switch
    ``WorldState.domestic_credit`` (None = off and omitted from every
    output). It needs finance (it changes finance's domestic lender) and,
    for an explicit ``--domestic-credit``, an agent pool (merchant agents
    lend). A saved setting under ``--agents off`` keeps its books: guilds and
    cities lend if the world has them, merchants (no pool) do not, and what
    is owed to them stays due. Identity: region = index in
    ``world.regions``, civ = index in ``world.civilizations``, guild = index
    in ``GuildState.guilds``, city = ``settlement_id``. No random draws.

See ``docs/integration/domestic-credit.md``.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Iterable, Sequence

from chronicler.domestic_credit_state import (
    CITY, GUILD, HOUSES, KIND_NAMES, LEGACY, MERCHANTS, TOTAL_KEYS, CreditLine, DomesticCreditState, Funder,
    domestic_credit_on,
)

if TYPE_CHECKING:  # pragma: no cover
    from chronicler.models import Event, WorldState


# ---------------------------------------------------------------------------
# Parameters ([CALIBRATE]; documented in docs/integration/domestic-credit.md)
# ---------------------------------------------------------------------------

#: Default for worlds created by the CLI/batch/live entry points
#: (``--domestic-credit`` opts in; loaded worlds keep their saved setting).
DEFAULT_ENABLED_FOR_NEW_WORLDS = False

LEND_SHARE = 0.5          # share of its assets (wealth + claims) a lender lends at full trust, less its claims
MAX_LEND_SHARE = 0.75     # never more, whatever the credit factors (a lender keeps a quarter)
MIN_FUNDING = 1           # a lender offering less lends nothing
GRIEVANCE_PER_LOSS = 1.0  # merchants' grievance per unit of their loss over their assets ...
GRIEVANCE_STEP = 0.5      # ... at most this much from one default
GRIEVANCE_DECAY = 0.95    # per turn (half-life about 13.5 turns)
GRIEVANCE_FLOOR = 0.001   # below this a grievance is forgotten
CITY_GRIEVANCE_STEP = 0.3  # a city's grievance per default, at most (loss over its assets)
THREAT_SHARE = 0.1        # a guild or city losing this share of its assets records the repudiation
EVENT_LENDERS = 3         # lenders named in an event
DUE_EPS = 1e-6            # merchant due below this (in absolute value) is not sent
QUANTUM_DIGITS = 4        # guild and city purses are stored to this many decimals
# Second pass (2026-10; docs/integration/domestic-credit.md section 13):
SERVICE_SHARE = 0.5       # no new domestic money that would raise the borrower's interest due above this share of its revenue
COLD_START_DECAY = 0.02   # the native agents' WEALTH_DECAY (agent.rs): the share of the pool's equilibrium wealth
                          # not yet accumulated at turn t is (1 - it) ** t; the abstract houses lend that share
                          # of finance's revenue term (DOMESTIC_REVENUE_TURNS x revenue x merchant influence)


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

def domestic_credit_enabled(world) -> bool:
    """True only for a real domestic-credit state (mocks and None read as off)."""
    return domestic_credit_on(world)


def set_domestic_credit_enabled(world: "WorldState", enabled: bool) -> None:
    """Switch domestic credit on (a fresh state, or the saved one kept) or off."""
    if enabled:
        if not domestic_credit_on(world):
            world.domestic_credit = DomesticCreditState()
    else:
        world.domestic_credit = None


def _ensure(world) -> DomesticCreditState:
    st = world.domestic_credit
    n = len(world.regions)
    while len(st.merchant_due) < n:
        st.merchant_due.append(0.0)
    while len(st.grievance) < n:
        st.grievance.append(0.0)
    for key in TOTAL_KEYS:
        st.totals.setdefault(key, 0)
    return st


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def split(total: int, weights: Sequence[int]) -> list[int]:
    """``total`` whole units pro rata to integer ``weights`` (largest
    remainder, ties to the earlier index). With ``total`` at most the sum of
    the weights no part exceeds its weight."""
    weights = [max(0, int(w)) for w in weights]
    whole = sum(weights)
    if total <= 0 or whole <= 0:
        return [0] * len(weights)
    parts, rems = [], []
    for i, w in enumerate(weights):
        q, r = divmod(total * w, whole)
        parts.append(q)
        if r:
            rems.append((-r, i))
    left = total - sum(parts)
    for _r, i in sorted(rems)[:left]:
        parts[i] += 1
    return parts


def _q(x: float) -> float:
    return round(x, QUANTUM_DIGITS)


def _civ_factors(world, civ_idx: int) -> float:
    """The credit factors that deepen domestic credit (as in
    ``finance._domestic_capacity``): techniques, great merchants' vows,
    chartered cities."""
    from chronicler.techniques_state import techniques_on
    factor = 1.0
    if techniques_on(world):
        from chronicler.techniques import credit_factor
        factor *= credit_factor(world, civ_idx)
    if getattr(world, "gp_agendas", None) is not None:
        from chronicler.gp_agendas import crown_credit_factor
        factor *= crown_credit_factor(world, civ_idx)
    if getattr(world, "cities", None) is not None:
        from chronicler.cities import credit_factor as city_credit_factor
        factor *= city_credit_factor(world, civ_idx)
    return factor


def lend_share(world, civ_idx: int, trust: float) -> float:
    """Share of its assets a lender of this civ lends (before its claims)."""
    return min(MAX_LEND_SHARE, LEND_SHARE * max(0.0, trust) * _civ_factors(world, civ_idx))


def cold_start_share(turn: int) -> float:
    """Share of the agent pool's equilibrium wealth not yet accumulated at
    ``turn``: agents start near zero and their wealth closes
    ``COLD_START_DECAY`` of its gap to equilibrium a turn."""
    return (1.0 - COLD_START_DECAY) ** max(0, turn)


def houses_capacity(world, civ_idx: int, civ, f) -> float:
    """What the abstract merchant houses would lend this civ in total:
    finance's revenue term (``DOMESTIC_REVENUE_TURNS`` x revenue x merchant
    influence, times domestic trust and the credit factors), scaled by the
    cold-start share. Its claims on the civ are deducted by the caller."""
    from chronicler import finance as F
    term = (F.DOMESTIC_REVENUE_TURNS * max(0.0, f.revenue_ema) * F._merchant_influence(civ)
            * max(0.0, f.domestic_trust) * _civ_factors(world, civ_idx))
    return cold_start_share(world.turn) * term


def interest_due(world, civ_idx: int) -> float:
    """Interest a civ owes per turn on all its lines (domestic and foreign)
    at their current rates."""
    return sum(loan.principal * loan.rate for loan in world.finance.loans
               if loan.borrower == civ_idx and loan.principal > 0)


def service_room(world, civ_idx: int, f) -> int:
    """New domestic principal the borrower can take before its interest due
    reaches ``SERVICE_SHARE`` of its (smoothed) revenue, at the domestic
    rate it would pay now (whole units, never negative)."""
    from chronicler import finance as F
    rate = F._loan_rate(world, civ_idx, f, foreign=False)
    room = (SERVICE_SHARE * max(f.revenue_ema, 1.0) - interest_due(world, civ_idx)) / max(rate, 1e-9)
    return int(math.floor(room)) if room > 0 else 0


def _cities(world) -> dict:
    from chronicler.cities_state import cities_on
    return {c.settlement_id: c for c in world.cities.cities} if cities_on(world) else {}


def _guilds(world) -> list:
    from chronicler.guilds_state import guilds_on
    return list(world.guilds.guilds) if guilds_on(world) else []


def lender_name(world, kind: int, key: int) -> str:
    """Readable name of a lender (for events and histories)."""
    if kind == MERCHANTS:
        return f"the merchants of {world.regions[key].name}" if 0 <= key < len(world.regions) else "its merchants"
    if kind == GUILD:
        guilds = _guilds(world)
        return guilds[key].name if 0 <= key < len(guilds) else "a guild"
    if kind == CITY:
        from chronicler.cities_state import RANK_NAMES, cities_on
        if cities_on(world):
            for c in world.cities.cities + world.cities.fallen:
                if c.settlement_id == key:
                    return f"the {RANK_NAMES[c.rank]} of {c.name}"
        return "a city"
    return "its merchant houses"


def _lender_region(world, kind: int, key: int) -> int | None:
    if kind == MERCHANTS:
        return key
    if kind == GUILD:
        guilds = _guilds(world)
        return guilds[key].region if 0 <= key < len(guilds) else None
    if kind == CITY:
        city = _cities(world).get(key)
        return city.region if city is not None else None
    return None


def describe(world, parts: Iterable[tuple[int, int, int]]) -> str:
    """'the merchants of A (25), the city of B (10) and others' (largest first)."""
    rows = [(amount, i, kind, key) for i, (kind, key, amount) in enumerate(parts) if amount > 0]
    rows.sort(key=lambda r: (-r[0], r[1]))
    names = [f"{lender_name(world, kind, key)} ({amount})" for amount, _i, kind, key in rows[:EVENT_LENDERS]]
    if len(rows) > EVENT_LENDERS:
        names.append("others")
    if not names:
        return "its merchant houses"
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def main_region(world, parts: Iterable[tuple[int, int, int]]) -> str | None:
    """Name of the region of the largest lender (None: none known)."""
    best = None
    for i, (kind, key, amount) in enumerate(parts):
        r = _lender_region(world, kind, key)
        if amount > 0 and r is not None and (best is None or amount > best[0]):
            best = (amount, r)
    return world.regions[best[1]].name if best is not None else None


# ---------------------------------------------------------------------------
# One fiscal tick (driven by finance.tick_finance)
# ---------------------------------------------------------------------------

class Tick:
    """Domestic credit during one fiscal tick: lenders, claims and flows.

    Created by ``finance.tick_finance`` (:func:`begin`) when the switch is
    on; finance calls :meth:`capacity` / :meth:`fund` when it borrows at home,
    :meth:`service` and :meth:`repay` when it pays a domestic line,
    :meth:`write_down` and :meth:`on_default` in a default,
    :meth:`write_off_line` for a fallen borrower and :meth:`finish` at the
    end of the tick. Nothing of it survives the tick: what must carry over
    is on ``DomesticCreditState``.
    """

    def __init__(self, world, agent_bridge=None) -> None:
        self.world = world
        self.st = _ensure(world)
        self.turn = world.turn
        n = len(world.regions)
        self.sim = getattr(agent_bridge, "_sim", None) if agent_bridge is not None else None
        self.wealth = [0.0] * n
        self.merchants = [0] * n
        if self.sim is not None:
            if not hasattr(self.sim, "merchant_wealth_by_region"):
                raise RuntimeError(
                    "the installed chronicler_agents extension predates domestic credit; "
                    "rebuild it to use --domestic-credit"
                )
            wealth, counts = self.sim.merchant_wealth_by_region()
            for r in range(min(n, len(wealth))):
                self.wealth[r] = float(wealth[r])
                self.merchants[r] = int(counts[r])
        self.lines: dict[str, CreditLine] = {line.loan_id: line for line in self.st.lines}
        self.claims: dict[tuple[int, int], int] = {}
        for line in self.st.lines:
            for fu in line.funders:
                self.claims[(fu.kind, fu.key)] = self.claims.get((fu.kind, fu.key), 0) + fu.principal
        self.cities = _cities(world)
        self.guilds = _guilds(world)
        self.flows: dict[str, int] = {}
        # Merchant flows of this tick per region (for the ledger).
        self.merchant_flow = [0] * n
        self.purse_flow: dict[tuple[int, int], int] = {}
        self.hooks = {"lent": 0, "interest": 0, "repaid": 0, "capitalized": 0, "written_off": 0}
        self.ledger = _Ledger.begin(self)

    # --- books --------------------------------------------------------------

    def _flow(self, flow: str, kind: int, amount: int) -> None:
        if amount:
            key = f"{flow}_{KIND_NAMES[kind]}"
            self.flows[key] = self.flows.get(key, 0) + amount
            self.st.totals[key] = self.st.totals.get(key, 0) + amount

    def _claim(self, line: CreditLine, kind: int, key: int, delta: int) -> None:
        if not delta:
            return
        for fu in line.funders:
            if fu.kind == kind and fu.key == key:
                fu.principal += delta
                break
        else:
            line.funders.append(Funder(kind=kind, key=key, principal=delta))
        self.claims[(kind, key)] = self.claims.get((kind, key), 0) + delta

    def _pay(self, kind: int, key: int, amount: int) -> None:
        """Credit (or debit, negative) a lender's wealth."""
        if not amount:
            return
        if kind == MERCHANTS:
            self.st.merchant_due[key] += amount
            self.merchant_flow[key] += amount
        elif kind == GUILD:
            g = self.guilds[key]
            g.wealth = _q(g.wealth + amount)
            self.purse_flow[(kind, key)] = self.purse_flow.get((kind, key), 0) + amount
        elif kind == CITY:
            city = self.cities.get(key)
            if city is not None:
                city.wealth = _q(city.wealth + amount)
                self.purse_flow[(kind, key)] = self.purse_flow.get((kind, key), 0) + amount
        # LEGACY: the abstract creditor class; nothing to credit.

    def line(self, loan) -> CreditLine:
        line = self.lines.get(loan.loan_id)
        if line is None:
            line = CreditLine(loan_id=loan.loan_id, borrower=loan.borrower)
            self.st.lines.append(line)
            self.lines[loan.loan_id] = line
        return line

    def _cash(self, kind: int, key: int) -> float:
        if kind == MERCHANTS:
            return max(0.0, self.wealth[key] + self.st.merchant_due[key])
        if kind == GUILD:
            return max(0.0, self.guilds[key].wealth)
        if kind == CITY:
            city = self.cities.get(key)
            return max(0.0, city.wealth) if city is not None else 0.0
        return 0.0

    # --- lending --------------------------------------------------------------

    def lenders(self, civ_idx: int, civ, trust: float) -> list[tuple[int, int, int]]:
        """(kind, key, offer) of every lender of ``civ`` offering at least
        ``MIN_FUNDING``: merchants by region index, guilds by index, cities
        by settlement id."""
        share = lend_share(self.world, civ_idx, trust)
        out: list[tuple[int, int, int]] = []

        def offer(kind: int, key: int) -> None:
            claims = self.claims.get((kind, key), 0)
            value = share * (self._cash(kind, key) + claims) - claims
            amount = int(math.floor(value)) if value > 0 else 0
            if amount >= MIN_FUNDING:
                out.append((kind, key, amount))

        index = {r.name: i for i, r in enumerate(self.world.regions)}
        for r in sorted(index[name] for name in civ.regions if name in index):
            if self.merchants[r] > 0:
                offer(MERCHANTS, r)
        for gi, g in enumerate(self.guilds):
            if g.dissolved_turn is not None:
                continue
            city = self.cities.get(g.city)
            if city is not None and city.lord == civ_idx:
                offer(GUILD, gi)
        for sid in sorted(self.cities):
            if self.cities[sid].lord == civ_idx:
                offer(CITY, sid)
        return out

    def houses_offer(self, civ_idx: int, civ, f) -> int:
        """The abstract merchant houses' offer while the pool's wealth is
        still building up (:func:`houses_capacity`), less what the civ
        already owes them."""
        claims = self.claims.get((HOUSES, civ_idx), 0)
        value = houses_capacity(self.world, civ_idx, civ, f) - claims
        return int(math.floor(value)) if value > 0 else 0

    def capacity(self, civ_idx: int, civ, f) -> tuple[int, list[tuple[int, int, int]]]:
        """Domestic capacity (whole units) and the lenders offering it: the
        real lenders' offers and the cold-start houses', together never more
        than the borrower's room under ``SERVICE_SHARE`` (:func:`service_room`)."""
        lenders = self.lenders(civ_idx, civ, f.domestic_trust)
        houses = self.houses_offer(civ_idx, civ, f)
        if houses >= MIN_FUNDING:
            lenders.append((HOUSES, civ_idx, houses))
        offered = sum(amount for _k, _key, amount in lenders)
        return min(offered, service_room(self.world, civ_idx, f)), lenders

    def fund(self, loan, amount: int, lenders: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
        """Fund ``amount`` (at most the lenders' total offer) of ``loan``:
        returns (kind, key, part) for every lender that lent."""
        parts = split(amount, [offer for _k, _key, offer in lenders])
        line = self.line(loan)
        funded = []
        for (kind, key, _offer), part in zip(lenders, parts):
            if part <= 0:
                continue
            self._pay(kind, key, -part)
            self._claim(line, kind, key, part)
            self._flow("lent", kind, part)
            funded.append((kind, key, part))
        self.hooks["lent"] += amount
        return funded

    # --- servicing ------------------------------------------------------------

    def _shares(self, loan) -> tuple[CreditLine, list[int]] | None:
        line = self.lines.get(loan.loan_id)
        if line is None:
            return None
        return line, [fu.principal for fu in line.funders]

    def service(self, loan, interest: int, principal: int, capitalized: int) -> None:
        """A domestic line's service this turn: interest and principal paid
        (to its funders, pro rata to their claims) and unpaid interest
        capitalized into their claims (all split on the claims before)."""
        found = self._shares(loan)
        if found is None:
            return
        line, shares = found
        paid_i = split(interest, shares)
        cap_i = split(capitalized, shares)
        paid_p = split(principal, shares)
        for fu, i, c, p in zip(line.funders, paid_i, cap_i, paid_p):
            self._pay(fu.kind, fu.key, i + p)
            self._flow("interest", fu.kind, i)
            self._flow("capitalized", fu.kind, c)
            self._flow("repaid", fu.kind, p)
            fu.principal += c - p
            self.claims[(fu.kind, fu.key)] = self.claims.get((fu.kind, fu.key), 0) + c - p
        self.hooks["interest"] += interest
        self.hooks["capitalized"] += capitalized
        self.hooks["repaid"] += principal

    def repay(self, loan, principal: int) -> None:
        """A prepayment of a domestic line (to its funders, pro rata)."""
        self.service(loan, 0, principal, 0)

    def write_down(self, loan, cut: int, flow: str = "written_off") -> list[tuple[int, int, int]]:
        """Write ``cut`` off a domestic line's claims pro rata; returns the
        losses (kind, key, amount)."""
        found = self._shares(loan)
        if found is None or cut <= 0:
            return []
        line, shares = found
        losses = []
        for fu, part in zip(line.funders, split(cut, shares)):
            if part <= 0:
                continue
            fu.principal -= part
            self.claims[(fu.kind, fu.key)] = self.claims.get((fu.kind, fu.key), 0) - part
            self._flow(flow, fu.kind, part)
            losses.append((fu.kind, fu.key, part))
        if flow == "written_off":
            self.hooks["written_off"] += cut
        return losses

    def write_off_line(self, loan) -> list[tuple[int, int, int]]:
        """A fallen borrower's line: every claim is lost."""
        return self.write_down(loan, loan.principal, "lost")

    def lapse_fallen_lenders(self, events: list) -> None:
        """Claims of a fallen city or a dissolved guild lapse: the borrower
        owes them no more (as debts owed to a fallen foreign lender lapse)."""
        from chronicler import finance as F
        world, st = self.world, world_finance(self.world)
        fallen = {}
        from chronicler.cities_state import cities_on
        if cities_on(world):
            fallen = {c.settlement_id: c for c in world.cities.fallen}
        loans = {loan.loan_id: loan for loan in st.loans}
        for line in self.st.lines:
            loan = loans.get(line.loan_id)
            if loan is None:
                continue
            for fu in line.funders:
                if fu.principal <= 0 or not self._gone(fu):
                    continue
                amount = fu.principal
                fu.principal = 0
                self.claims[(fu.kind, fu.key)] = self.claims.get((fu.kind, fu.key), 0) - amount
                self._flow("lapsed", fu.kind, amount)
                loan.principal -= amount
                st.totals["written_off"] += amount
                st.civs[loan.borrower].written_off_total += amount
                if amount >= F.MIN_LOAN:
                    events.append(self._lapse_event(loan, fu, amount, fallen))
        st.loans = [loan for loan in st.loans if loan.principal > 0]

    def _gone(self, fu: Funder) -> bool:
        if fu.kind == GUILD:
            return not (0 <= fu.key < len(self.guilds)) or self.guilds[fu.key].dissolved_turn is not None
        if fu.kind == CITY:
            return fu.key not in self.cities
        return False

    def _lapse_event(self, loan, fu: Funder, amount: int, fallen: dict) -> "Event":
        from chronicler import provenance as prov
        from chronicler.models import Event
        world = self.world
        borrower = world.civilizations[loan.borrower]
        name = lender_name(world, fu.kind, fu.key)
        cause, region = None, None
        if fu.kind == GUILD and 0 <= fu.key < len(self.guilds):
            g = self.guilds[fu.key]
            cause = next((eid for _t, kind, eid in reversed(g.history) if kind == "dissolved" and eid), None)
            region = world.regions[g.region].name
        elif fu.kind == CITY and fu.key in fallen:
            c = fallen[fu.key]
            cause = next((eid for _t, kind, eid in reversed(c.history) if kind == "fell" and eid), None)
            region = world.regions[c.region].name
        ev = Event(turn=world.turn, event_type="debt_written_off", actors=[borrower.name],
                   description=f"With {name} gone, the {amount} {borrower.name} owed it lapses.",
                   importance=3, civs=[borrower.name], region=region)
        prov.cite(ev, cause, loan.event_id or None)
        return ev

    # --- default consequences -------------------------------------------------

    def on_default(self, civ_idx: int, civ, losses: list[tuple[int, int, int]], ev, acc=None) -> None:
        """Who lost in ``civ``'s default (``ev``): merchants' grievance by
        region, cities' grievance, and the repudiation in the histories of
        guilds and cities that lost a material share of their assets (for a
        guild, a threat to its privileges)."""
        total: dict[tuple[int, int], int] = {}
        for kind, key, amount in losses:
            if kind not in (LEGACY, HOUSES) and amount > 0:
                total[(kind, key)] = total.get((kind, key), 0) + amount
        if not total:
            return
        self.st.defaults_on_lenders += 1
        world = self.world
        eid = ev.event_id or ""
        for (kind, key), loss in sorted(total.items()):
            assets = max(1.0, self._cash(kind, key) + self.claims.get((kind, key), 0) + loss)
            if kind == MERCHANTS:
                step = min(GRIEVANCE_STEP, GRIEVANCE_PER_LOSS * loss / assets)
                self.st.grievance[key] = round(min(1.0, self.st.grievance[key] + step), 6)
            elif kind == CITY:
                city = self.cities.get(key)
                if city is None:
                    continue
                step = min(CITY_GRIEVANCE_STEP, loss / assets)
                city.grievance = _q(min(1.0, city.grievance + step))
                if loss >= THREAT_SHARE * assets:
                    from chronicler.cities import _note as city_note
                    city_note(city, world.turn, "repudiated", eid)
            elif kind == GUILD:
                if loss >= THREAT_SHARE * assets and 0 <= key < len(self.guilds):
                    from chronicler.guilds import _note as guild_note
                    guild_note(self.guilds[key], world.turn, "repudiated", eid)

    def note_loan(self, funded: list[tuple[int, int, int]], ev) -> None:
        """A material loan (its ``loan_taken`` event) in the histories of the
        cities and guilds that lent to it."""
        eid = ev.event_id or ""
        for kind, key, amount in funded:
            if amount <= 0:
                continue
            if kind == CITY and key in self.cities:
                from chronicler.cities import _note as city_note
                city_note(self.cities[key], self.world.turn, "loan", eid)
            elif kind == GUILD and 0 <= key < len(self.guilds):
                from chronicler.guilds import _note as guild_note
                guild_note(self.guilds[key], self.world.turn, "loan", eid)

    # --- end of tick ----------------------------------------------------------

    def finish(self) -> None:
        """Drop settled lines, send the merchants' due to the native pool
        (keeping what could not be applied) and check the books."""
        world, st = self.world, self.st
        live = {loan.loan_id for loan in world_finance(world).loans}
        self.ledger.lines(self)
        st.lines = [line for line in st.lines if line.loan_id in live]
        for line in st.lines:
            line.funders = [fu for fu in line.funders if fu.principal != 0]
        self.ledger.before_apply(self)
        if self.sim is not None:
            ids = [r for r, due in enumerate(st.merchant_due) if abs(due) >= DUE_EPS]
            if ids:
                amounts = [st.merchant_due[r] for r in ids]
                applied = self.sim.apply_merchant_transfers(ids, amounts)
                for r, sent, done in zip(ids, amounts, applied):
                    st.merchant_due[r] = sent - done
                    st.merchant_sent += sent
                    st.merchant_applied += done
                self.ledger.after_apply(self, ids, applied)
        self.ledger.close(self)
        st.last_tick_turn = world.turn


def world_finance(world):
    return world.finance


def begin(world, agent_bridge=None) -> Tick | None:
    """The tick context when domestic credit is on (finance on too), else None.
    Merchants' grievance decays here, once a turn."""
    if not domestic_credit_on(world) or getattr(world, "finance", None) is None:
        return None
    t = Tick(world, agent_bridge)
    st = t.st
    for r, g in enumerate(st.grievance):
        g = round(g * GRIEVANCE_DECAY, 6)
        st.grievance[r] = g if g >= GRIEVANCE_FLOOR else 0.0
    # Domestic lines without funders (lent before the switch was on) belong
    # to the abstract creditor class, so every line's claims add up.
    from chronicler.finance import DOMESTIC
    for loan in world.finance.loans:
        if loan.lender == DOMESTIC and loan.principal > 0 and loan.loan_id not in t.lines:
            t._claim(t.line(loan), LEGACY, -1, loan.principal)
    t.ledger.opened(t)
    return t


# ---------------------------------------------------------------------------
# Native region batch (creditor grievance)
# ---------------------------------------------------------------------------

def region_grievances(world) -> list[float] | None:
    """Per region index, its merchants' grievance toward a defaulting lord
    (the region batch's ``creditor_grievance`` column), or None when off
    (or dormant without finance, whose tick lets it decay)."""
    if not domestic_credit_on(world) or getattr(world, "finance", None) is None:
        return None
    g = world.domestic_credit.grievance
    return [min(1.0, max(0.0, g[r])) if r < len(g) else 0.0 for r in range(len(world.regions))]


# ---------------------------------------------------------------------------
# Ledger (CHRONICLER_CHECK_RESOURCES=1)
# ---------------------------------------------------------------------------

_TOL = 1e-6


class _Ledger:
    """One fiscal tick's domestic-credit balances (``CHRONICLER_CHECK_RESOURCES=1``).

    Raises ``AssertionError("credit ledger does not balance ...")`` unless:

    * every domestic loan has a credit line whose claims add up to its
      principal (whole units), and settled lines hold nothing;
    * per kind of lender, claims after = claims before + lent + capitalized
      - repaid - written off - lost - lapsed (whole units);
    * finance's own counters agree: domestic principal issued and interest
      paid this tick are what the lenders lent and received;
    * every guild and city purse changed by exactly what it lent and was
      paid, every region's merchant due by its merchants' flows;
    * the native pool's merchant wealth changed by exactly what it reports
      as applied, and no region's merchants were asked for more than they
      hold;
    * cumulatively, the merchants' flows equal what reached their wealth
      plus what is still due.
    """

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.problems: list[str] = []

    @staticmethod
    def begin(t: Tick) -> "_Ledger":
        from chronicler.production_ledger import resource_check_enabled
        return _Ledger(resource_check_enabled())

    def opened(self, t: Tick) -> None:
        if not self.enabled:
            return
        fin = world_finance(t.world)
        self.finance = {k: fin.totals.get(k, 0) for k in ("issued_domestic", "interest_domestic")}
        self.claims = self._claims_by_kind(t)
        self.due = list(t.st.merchant_due)
        self.purses = {}
        for gi, g in enumerate(t.guilds):
            self.purses[(GUILD, gi)] = g.wealth
        for sid, c in t.cities.items():
            self.purses[(CITY, sid)] = c.wealth
        self.flows_start = dict(t.st.totals)

    @staticmethod
    def _claims_by_kind(t: Tick) -> list[int]:
        out = [0] * len(KIND_NAMES)
        for line in t.st.lines:
            for fu in line.funders:
                out[fu.kind] += fu.principal
        return out

    def lines(self, t: Tick) -> None:
        if not self.enabled:
            return
        from chronicler.finance import DOMESTIC
        loans = {loan.loan_id: loan for loan in world_finance(t.world).loans}
        for line in t.st.lines:
            held = sum(fu.principal for fu in line.funders)
            loan = loans.get(line.loan_id)
            want = loan.principal if loan is not None else 0
            if held != want or any(fu.principal < 0 for fu in line.funders):
                self.problems.append(f"line {line.loan_id}: claims {held} for principal {want}")
        for loan in loans.values():
            if loan.lender == DOMESTIC and loan.loan_id not in t.lines:
                self.problems.append(f"domestic loan {loan.loan_id} has no credit line")
        claims = self._claims_by_kind(t)
        for kind, name in enumerate(KIND_NAMES):
            f = {flow: t.flows.get(f"{flow}_{name}", 0) for flow in
                 ("lent", "capitalized", "repaid", "written_off", "lost", "lapsed")}
            expect = (self.claims[kind] + f["lent"] + f["capitalized"] - f["repaid"]
                      - f["written_off"] - f["lost"] - f["lapsed"])
            if claims[kind] != expect:
                self.problems.append(f"{name} claims {self.claims[kind]} -> {claims[kind]}, flows {f}")
        fin = world_finance(t.world)
        lent = sum(t.flows.get(f"lent_{n}", 0) for n in KIND_NAMES)
        interest = sum(t.flows.get(f"interest_{n}", 0) for n in KIND_NAMES)
        if fin.totals.get("issued_domestic", 0) - self.finance["issued_domestic"] != lent:
            self.problems.append(f"issued domestic {self.finance['issued_domestic']} -> "
                                 f"{fin.totals.get('issued_domestic', 0)}, lenders lent {lent}")
        if fin.totals.get("interest_domestic", 0) - self.finance["interest_domestic"] != interest:
            self.problems.append(f"domestic interest {self.finance['interest_domestic']} -> "
                                 f"{fin.totals.get('interest_domestic', 0)}, lenders received {interest}")
        for flow in ("interest", "repaid", "capitalized", "written_off"):
            got = sum(t.flows.get(f"{flow}_{n}", 0) for n in KIND_NAMES)
            if got != t.hooks[flow]:
                self.problems.append(f"{flow}: finance {t.hooks[flow]}, split to lenders {got}")

    def before_apply(self, t: Tick) -> None:
        if not self.enabled:
            return
        for (kind, key), before in self.purses.items():
            if kind == GUILD:
                now = t.guilds[key].wealth
            else:
                city = t.cities.get(key)
                if city is None:
                    continue
                now = city.wealth
            moved = t.purse_flow.get((kind, key), 0)
            if abs(now - before - moved) > _TOL * max(1.0, abs(before)):
                self.problems.append(f"{lender_name(t.world, kind, key)}: purse {before} -> {now}, flows {moved}")
        for r, before in enumerate(self.due):
            now = t.st.merchant_due[r]
            if abs(now - before - t.merchant_flow[r]) > _TOL * max(1.0, abs(before)):
                self.problems.append(f"region {r}: merchant due {before} -> {now}, flows {t.merchant_flow[r]}")
            # A region that lent this tick is never asked for more than its
            # merchants hold (beyond a debit residual of f32 rounding carried
            # from an earlier tick, which waits in the due like any other).
            carried = max(0.0, -before)
            if (t.merchant_flow[r] < 0
                    and -now > t.wealth[r] + carried + _TOL * max(1.0, t.wealth[r])):
                self.problems.append(f"region {r}: merchants asked for {-now} holding {t.wealth[r]}")
        if t.sim is not None:
            self.pool_before = list(t.sim.merchant_wealth_by_region()[0])

    def after_apply(self, t: Tick, ids: list[int], applied: list[float]) -> None:
        if not self.enabled:
            return
        after = list(t.sim.merchant_wealth_by_region()[0])
        changed = dict(zip(ids, applied))
        for r in range(len(after)):
            delta = after[r] - self.pool_before[r]
            if abs(delta - changed.get(r, 0.0)) > _TOL * max(1.0, abs(self.pool_before[r])):
                self.problems.append(f"region {r}: merchant wealth {self.pool_before[r]} -> {after[r]}, "
                                     f"applied {changed.get(r, 0.0)}")

    def close(self, t: Tick) -> None:
        if not self.enabled:
            return
        tot = t.st.totals
        flows = (tot.get("interest_merchants", 0) + tot.get("repaid_merchants", 0)
                 - tot.get("lent_merchants", 0))
        held = t.st.merchant_applied + sum(t.st.merchant_due)
        if abs(flows - held) > _TOL * max(1.0, abs(flows), t.st.merchant_sent):
            self.problems.append(f"merchants: flows {flows}, applied {t.st.merchant_applied} + due "
                                 f"{sum(t.st.merchant_due)}")
        if self.problems:
            raise AssertionError(f"credit ledger does not balance in turn {t.turn}: " + "; ".join(self.problems))


# ---------------------------------------------------------------------------
# Viewer snapshot and analytics
# ---------------------------------------------------------------------------

def claims_by_borrower(world) -> dict[int, list[int]]:
    """Per borrower civ index, outstanding domestic claims by lender kind."""
    out: dict[int, list[int]] = {}
    if not domestic_credit_on(world):
        return out
    for line in world.domestic_credit.lines:
        row = out.setdefault(line.borrower, [0] * len(KIND_NAMES))
        for fu in line.funders:
            row[fu.kind] += fu.principal
    return out


def holders_summary(world) -> dict[str, dict]:
    """Who holds each living civ's debt, by civ name (for the viewer).

    Per borrower: ``foreign`` (lender civ name -> [principal, rate]), the
    domestic line's ``rate``, the claims of ``merchants`` by region name and
    of ``cities`` and ``guilds`` by name (the abstract ``houses`` and
    ``legacy`` claims are in the summary's ``civs``), and ``written_off``,
    the debt written off on the civ so far (finance's cumulative count).
    Empty parts are left out, and so is a civ with neither debt nor
    write-offs. Read-only: built from the persisted books."""
    from chronicler.cities_state import cities_on
    from chronicler.finance import DOMESTIC
    fin = world.finance
    civs, regions = world.civilizations, world.regions
    lines = {line.loan_id: line for line in world.domestic_credit.lines}
    city_names: dict[int, str] = {}
    if cities_on(world):
        for city in world.cities.cities + world.cities.fallen:
            city_names.setdefault(city.settlement_id, city.name)
    guilds = _guilds(world)
    by_civ: dict[int, list] = {}
    for loan in fin.loans:
        if loan.principal > 0:
            by_civ.setdefault(loan.borrower, []).append(loan)
    out: dict[str, dict] = {}
    for c, civ in enumerate(civs):
        if not civ.regions:
            continue
        foreign: dict[int, list[float]] = {}
        domestic = [0, 0.0]
        claims: dict[tuple[int, int], int] = {}
        for loan in by_civ.get(c, []):
            if loan.lender == DOMESTIC:
                domestic[0] += loan.principal
                domestic[1] += loan.principal * loan.rate
                line = lines.get(loan.loan_id)
                for fu in line.funders if line is not None else []:
                    if fu.principal > 0 and fu.kind in (MERCHANTS, CITY, GUILD):
                        claims[(fu.kind, fu.key)] = claims.get((fu.kind, fu.key), 0) + fu.principal
            else:
                row = foreign.setdefault(loan.lender, [0, 0.0])
                row[0] += loan.principal
                row[1] += loan.principal * loan.rate
        entry: dict = {}
        if foreign:
            entry["foreign"] = {civs[j].name: [p, round(i / p, 4)] for j, (p, i) in sorted(foreign.items())}
        if domestic[0]:
            entry["rate"] = round(domestic[1] / domestic[0], 4)
        for kind, label in ((MERCHANTS, "merchants"), (CITY, "cities"), (GUILD, "guilds")):
            named: dict[str, int] = {}
            for (k, key), amount in sorted(claims.items()):
                if k != kind:
                    continue
                if kind == MERCHANTS:
                    name = regions[key].name if 0 <= key < len(regions) else f"region {key}"
                elif kind == CITY:
                    name = city_names.get(key, f"city {key}")
                else:
                    name = guilds[key].name if 0 <= key < len(guilds) else f"guild {key}"
                named[name] = named.get(name, 0) + amount
            if named:
                entry[label] = named
        written = fin.civs[c].written_off_total if c < len(fin.civs) else 0
        if written:
            entry["written_off"] = written
        if entry:
            out[civ.name] = entry
    return out


def snapshot_summary(world) -> dict:
    """Per-turn summary, carried as ``TurnSnapshot.finance["domestic_credit"]``."""
    st = world.domestic_credit
    kinds = [0] * len(KIND_NAMES)
    civs = {}
    for c, row in sorted(claims_by_borrower(world).items()):
        for k, v in enumerate(row):
            kinds[k] += v
        if c < len(world.civilizations) and world.civilizations[c].regions and any(row):
            civs[world.civilizations[c].name] = {KIND_NAMES[k]: v for k, v in enumerate(row) if v}
    grievance = {world.regions[r].name: round(g, 4) for r, g in enumerate(st.grievance)
                 if g >= 0.01 and r < len(world.regions)}
    out = {
        "claims": {KIND_NAMES[k]: v for k, v in enumerate(kinds)},
        "civs": civs,
        "lenders": sum(len(line.funders) for line in st.lines),
        "merchant_due": round(sum(st.merchant_due), 4),
        "grievance": grievance,
    }
    holders = holders_summary(world)
    if holders:
        out["holders"] = holders
    return out


def extract_domestic_credit_metrics(bundles: Iterable[dict]) -> dict:
    """Aggregate domestic-credit metrics over bundles whose history carries
    ``finance["domestic_credit"]`` (and the final world state's books)."""
    runs = 0
    claim_turns = {k: 0 for k in KIND_NAMES}
    peak = 0
    grievance_turns = 0
    totals: dict[str, int] = {}
    for bundle in bundles:
        rows = [(h.get("finance") or {}).get("domestic_credit") for h in bundle.get("history") or []
                if isinstance(h, dict)]
        rows = [row for row in rows if row]
        if not rows:
            continue
        runs += 1
        for row in rows:
            claims = row.get("claims", {})
            for k in KIND_NAMES:
                claim_turns[k] += claims.get(k, 0)
            peak = max(peak, sum(claims.values()))
            grievance_turns += len(row.get("grievance", {}))
        books = ((bundle.get("world_state") or {}).get("domestic_credit") or {}).get("totals", {})
        for k, v in books.items():
            totals[k] = totals.get(k, 0) + v
    if not runs:
        return {}
    held = sum(claim_turns.values())
    return {
        "runs": runs,
        "claim_share": {k: (v / held if held else 0.0) for k, v in claim_turns.items()},
        "peak_claims": peak,
        "grievance_region_turns": grievance_turns,
        "totals": dict(sorted(totals.items())),
    }
