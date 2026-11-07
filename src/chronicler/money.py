"""The shared payment seam for new payers (connected-world program).

Design: the A1-A2 income and wealth audit (section 3.3) and the A3 workshop
economics audit (section 5); integration page
``docs/integration/workshop-economics.md``. First user: A3
(``--workshop-economics``). Existing packages are **not** refactored onto it
(their witness pins and output identity stay as they are); the A1 ledger
reads their own receipts and this seam's register.

One rule set for every new payment:

* **Accounts** (``ACCOUNT_KINDS``): a civilization's treasury (index in
  ``world.civilizations``), a firm's cash (the firm id the caller names),
  an agent's native wealth (stable id) and a declared sink (``SINKS``).
* **Units.** Every amount is a whole number of milli-units (1000 = one
  treasury unit = one native wealth unit, the equivalence domestic credit
  and L6a already use). Treasuries hold whole units: a treasury *debit* must
  be a whole number of units; a treasury *credit* below a whole unit is held
  as a persisted ``carry`` of the paying package's book (per civilization and
  purpose) and paid in whole units as it accumulates, so nothing is rounded
  away and nothing is created. A treasury pays agents only for a declared
  purpose (``TREASURY_AGENT_PURPOSES``, C2's ``care_wage``): its lines may be
  sub-unit, the bill is paid from that book's prepaid carry first and then in
  whole units, and the unspent rest of the last unit stays prepaid.
* **Whole-bill validation before any move.** The purpose is registered, the
  amounts are positive integers, the counterparties are unique, the key
  ``(turn, purpose, batch)`` has not settled, and the payer covers the whole
  bill: a treasury its projected budget (``mutual_aid._treasury_budget``,
  accumulator-aware), a firm its cash, and in a collection each paying agent
  its own wealth (``floor(wealth x 1000)`` from one fresh snapshot read). A
  bill that fails is refused whole: nothing moves and nothing settles.
* **Exactly once.** A settled ``(turn, purpose, batch)`` is refused again,
  as the native key log refuses it; the book's ``settled`` keys are
  persisted, so an exact checkpoint resume refuses a repeat too.
* **Residuals.** What an agent's wealth ceiling refuses (a credit) or what
  an absent id cannot take returns to the payer (``return_to_payer``, the
  default) unless the bill names a declared sink (``sink:<name>``), which then
  receives it and records it. A collection has no residual: the caller
  limits each line to what its payer holds, and a line the native transfer
  does not apply in full is an error (the snapshot was stale).
* **Register.** Every applied line becomes a typed :class:`MoneyFlow` in the
  book's ``flows`` (the last settled turn's, bounded), which the A1 ledger
  reads by purpose (``flows_for_turn``).

No random draws; every order is by account identity. Native transfers go
through ``AgentSimulator.transfer_wealth`` (append-only purposes; this seam
verifies the extension names the purpose, or the native purpose it rides
(``NATIVE_ALIASES``), at the code it uses).

**Pairwise payments** (A4 titled trade): a bill whose payer is an agent and
whose payee lines are agents, under a pairwise purpose
(``PAIRWISE_PURPOSES``: ``cargo_purchase``, ``cargo_sale``), is settled by
the native ``settle_pairs`` (no fee, no trip rule) through the one router
``_native_pairs``. Before any move the payer's wealth must cover the whole
bill and every payee must be alive (one fresh snapshot read); a payee's
ceiling refusal never leaves the payer (``return_to_payer``, recorded as the
line's residual); a payer row the native limits is an error (a stale read).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

MILLI = 1000

#: Native ``wealth_transfer::PURPOSES`` in declaration order (append only;
#: never renumber). ``wares_purchase`` (7) was appended by A3,
#: ``cargo_purchase`` (8) and ``cargo_sale`` (9) by A4 (pairwise).
NATIVE_PURPOSES: tuple[str, ...] = (
    "workshop_wage", "relocation_fare", "apprentice_stipend", "repair_wage", "remittance",
    "food_purchase", "food_procurement", "wares_purchase", "cargo_purchase", "cargo_sale",
)
#: Purposes an agent may pay agents for (``settle_pairs``; append only).
PAIRWISE_PURPOSES: tuple[str, ...] = ("cargo_purchase", "cargo_sale")
#: Purposes Python-only accounts use (treasury <-> firm cash); they never
#: reach native code (append only).
PYTHON_PURPOSES: tuple[str, ...] = ("firm_capital", "firm_input_purchase")
#: Seam purposes that ride an existing native purpose code (append only).
#: The connected-world Python-only lanes cannot add a native code, so a new
#: agent-wealth purpose is keyed natively under an existing code with batches
#: its caller keeps disjoint from that code's other users (the native key log
#: is per turn, code and batch); the seam's own book keys it by its own name.
#: ``care_wage`` (C2): treasury -> epidemic carers, under ``repair_wage`` (as
#: PL1 woodcut and PL3 granary crew wages are), batches ``epidemic_care.CARE_WAGE_BATCH + civ``.
NATIVE_ALIASES: dict[str, str] = {"care_wage": "repair_wage"}
#: Every registered purpose -> its native code (None: Python accounts only).
PURPOSES: dict[str, int | None] = {
    **{name: code for code, name in enumerate(NATIVE_PURPOSES)},
    **{name: None for name in PYTHON_PURPOSES},
    **{name: NATIVE_PURPOSES.index(native) for name, native in NATIVE_ALIASES.items()},
}
#: Purposes for which a treasury may pay agents (append only). Lines may be
#: sub-unit: the treasury pays whole units and the remainder is prepaid into
#: the book's carry for (civ, purpose), spent first by the next bill; what an
#: agent's wealth ceiling refuses (or an absent id cannot take) returns to that
#: carry (``return_to_payer``), whole units of it to the treasury.
TREASURY_AGENT_PURPOSES: tuple[str, ...] = ("care_wage",)
#: Account kinds, in declaration order (append only).
ACCOUNT_KINDS: tuple[str, ...] = ("civ_treasury", "firm_cash", "agent_wealth", "sink")
#: Declared sinks a bill may name for its residual or as a payee (append only).
#: ``unowned_commons``: inputs taken from the commons of a region nobody
#: controls (paid, but to nobody); ``credit_refused``: agent credits a
#: ceiling refused, when the paying package chooses not to keep them.
SINKS: tuple[str, ...] = ("unowned_commons", "credit_refused")
#: The most flows one book keeps for its last settled turn.
MAX_FLOWS = 512


class MoneyError(RuntimeError):
    """A payment the seam refuses to make or a settlement that does not close."""


def _is_none(value) -> bool:
    return value is None


class _Backfilled(BaseModel):
    """Exact pickle restoration bypasses defaults: fields added later (A4's
    ``payer_region``) read their default when an older pickle lacks them."""

    def __setstate__(self, state):
        super().__setstate__(state)
        for name, field in type(self).model_fields.items():
            if name not in self.__dict__:
                self.__dict__[name] = field.get_default(call_default_factory=True)


# ---------------------------------------------------------------------------
# Persisted book (owned by the calling package's state) and its flows
# ---------------------------------------------------------------------------

class MoneyFlow(_Backfilled):
    """One applied line of a settled bill. ``requested`` = ``applied`` +
    ``residual``; ``residual_to`` is ``"payer"`` or ``"sink:<name>"`` when a
    residual exists. Treasury sides record the whole units moved and the
    sub-unit carry before and after (a credit) in milli-units."""

    turn: int
    phase: str
    purpose: str
    batch: int
    payer: tuple[str, int | str]
    payee: tuple[str, int | str]
    region: int | None = None
    requested: int
    applied: int
    residual: int = 0
    residual_to: str | None = None
    status: Literal["applied", "limited", "absent"] = "applied"
    treasury_units: int = 0
    carry_before: int | None = None
    carry_after: int | None = None
    #: A pairwise payment (A4): the paying agent's region (``region`` is the
    #: payee's); omitted otherwise, so earlier books keep their bytes.
    payer_region: int | None = Field(default=None, exclude_if=_is_none)


class FlowTotal(_Backfilled):
    """The exact sum of one settled turn's applied flows of one purpose
    between two account kinds in one region (never truncated, unlike the
    flow list): what the ledger reads. A treasury side keeps its civilization
    (``payer_civ``/``payee_civ``, None otherwise), so per-civilization
    attribution is exact too, with the whole units moved and the change of
    the sub-unit carry."""

    purpose: str
    payer_kind: str
    payee_kind: str
    region: int | None = None
    payer_civ: int | None = None
    payee_civ: int | None = None
    applied: int = 0
    residual: int = 0
    count: int = 0
    treasury_units: int = 0
    carry_change: int = 0
    #: A pairwise payment's payer region (A4; ``region`` is the payee's).
    payer_region: int | None = Field(default=None, exclude_if=_is_none)


class MoneyBook(_Backfilled):
    """What one package's payments through the seam must remember."""

    #: Settled keys of the latest settled turn: ``[turn, purpose, batch]``.
    settled: list[tuple[int, str, int]] = Field(default_factory=list)
    #: Sub-unit treasury credits held for a civilization: ``"<civ>:<purpose>"`` -> milli (0..999).
    carry: dict[str, int] = Field(default_factory=dict)
    #: Lifetime milli-units received by each declared sink.
    sinks: dict[str, int] = Field(default_factory=dict)
    #: The flows of the last settled turn (``flows_turn``), at most ``MAX_FLOWS``.
    flows_turn: int | None = None
    flows: list[MoneyFlow] = Field(default_factory=list)
    #: Flows of ``flows_turn`` beyond ``MAX_FLOWS`` that the list does not keep
    #: (their amounts are in ``totals``, which is never truncated).
    flows_dropped: int = 0
    totals: list[FlowTotal] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Bills
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Account:
    kind: str
    ident: int | str

    def key(self) -> tuple[int, Any]:
        return (ACCOUNT_KINDS.index(self.kind), self.ident)


@dataclass(frozen=True)
class Bill:
    """A payment (one ``payer``, many payee ``lines``) or a collection (many
    payer ``lines``, one ``payee``). Exactly one of ``payer``/``payee`` is
    set. ``lines``: ``(account, milli > 0)``; ``regions`` optionally names the
    region each line's agent belongs to (for the ledger)."""

    purpose: str
    batch: int
    phase: str
    lines: tuple[tuple[Account, int], ...]
    payer: Account | None = None
    payee: Account | None = None
    residual: str = "return_to_payer"
    regions: tuple[int | None, ...] | None = None
    #: A pairwise bill (an agent paying agents): the payer's region.
    payer_region: int | None = None


@dataclass(frozen=True)
class Quote:
    ok: bool
    reason: str | None
    total: int
    available: int | None


@dataclass
class Receipt:
    ok: bool
    reason: str | None
    total: int = 0
    applied: int = 0
    residual: int = 0
    sunk: int = 0
    treasury_units: int = 0
    flows: list[MoneyFlow] | None = None


def treasury(civ: int) -> Account:
    return Account("civ_treasury", int(civ))


def firm_cash(firm: int) -> Account:
    return Account("firm_cash", int(firm))


def agent(aid: int) -> Account:
    return Account("agent_wealth", int(aid))


def sink(name: str) -> Account:
    return Account("sink", name)


def _validate_shape(bill: Bill) -> None:
    if bill.purpose not in PURPOSES:
        raise MoneyError(f"unregistered payment purpose {bill.purpose!r}")
    if not isinstance(bill.batch, int) or isinstance(bill.batch, bool) or bill.batch < 0:
        raise MoneyError("payment batch must be a non-negative integer")
    if (bill.payer is None) == (bill.payee is None):
        raise MoneyError("a bill names exactly one payer (payment) or one payee (collection)")
    if not bill.lines:
        raise MoneyError("a bill needs at least one line")
    seen = set()
    for account, amount in bill.lines:
        if account.kind not in ACCOUNT_KINDS:
            raise MoneyError(f"unknown account kind {account.kind!r}")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise MoneyError("payment amounts must be positive whole milli-units")
        if account in seen:
            raise MoneyError("duplicate counterparty in a bill")
        seen.add(account)
    if bill.regions is not None and len(bill.regions) != len(bill.lines):
        raise MoneyError("bill regions must match its lines")
    side = bill.payer if bill.payer is not None else bill.payee
    if side.kind not in ACCOUNT_KINDS or side in seen:
        raise MoneyError("the bill's own account cannot also be a counterparty")
    for account in (side, *(a for a, _ in bill.lines)):
        if account.kind == "sink" and account.ident not in SINKS:
            raise MoneyError(f"undeclared sink {account.ident!r}")
    if bill.residual != "return_to_payer":
        if not bill.residual.startswith("sink:") or bill.residual[5:] not in SINKS:
            raise MoneyError(f"undeclared residual policy {bill.residual!r}")
    pairwise = bill.payer is not None and bill.payer.kind == "agent_wealth"
    if pairwise:
        # A4: an agent pays agents only under a pairwise purpose, by the
        # native settle_pairs, returning ceiling refusals to itself.
        if bill.purpose not in PAIRWISE_PURPOSES:
            raise MoneyError(f"purpose {bill.purpose!r} is not a pairwise purpose")
        if any(a.kind != "agent_wealth" for a, _ in bill.lines):
            raise MoneyError("a pairwise bill pays agents")
        if bill.residual != "return_to_payer":
            raise MoneyError("a pairwise bill returns refused credits to its payer")
    elif bill.purpose in PAIRWISE_PURPOSES:
        raise MoneyError(f"purpose {bill.purpose!r} is paid only by an agent to agents")
    elif bill.payer is not None:
        if bill.payer.kind in ("agent_wealth", "sink"):
            raise MoneyError("an agent or a sink pays only through a collection line")
        if bill.payer.kind == "civ_treasury" and any(a.kind == "agent_wealth" for a, _ in bill.lines) \
                and not _treasury_to_agents(bill):
            # A treasury pays agents through the packages' own prepaid rules
            # (RS2/PL1), or through this seam only for a declared purpose whose
            # every line is an agent (``TREASURY_AGENT_PURPOSES``, C2).
            raise MoneyError("a treasury payment to agents is not supported by this seam")
    else:
        if bill.payee.kind == "agent_wealth":
            raise MoneyError("a collection pays a firm, a treasury or a sink, not an agent")
        if any(a.kind != "agent_wealth" for a, _ in bill.lines):
            raise MoneyError("a collection's lines are paying agents")
    if bill.payer is not None and bill.payer.kind == "civ_treasury" and any(a % MILLI for _, a in bill.lines) \
            and not _treasury_to_agents(bill):
        raise MoneyError("a treasury pays whole units")
    if pairwise or any(a.kind == "agent_wealth" for a, _ in bill.lines):
        if PURPOSES[bill.purpose] is None:
            raise MoneyError(f"purpose {bill.purpose!r} has no native code and cannot move agent wealth")
        from chronicler.wealth_accounting_state import MONEY_PURPOSE_CHANNELS
        if bill.purpose not in MONEY_PURPOSE_CHANNELS:
            # Fail closed: an agent-wealth payment through the seam needs a ledger channel.
            raise MoneyError(f"purpose {bill.purpose!r} has no ledger channel "
                             "(wealth_accounting_state.MONEY_PURPOSE_CHANNELS)")


def _treasury_to_agents(bill: Bill) -> bool:
    """A treasury paying only agents for a declared purpose (prepaid carry rule)."""
    return (bill.payer is not None and bill.payer.kind == "civ_treasury"
            and bill.purpose in TREASURY_AGENT_PURPOSES and bill.residual == "return_to_payer"
            and all(a.kind == "agent_wealth" for a, _ in bill.lines))


def _settled(book: MoneyBook, turn: int, purpose: str, batch: int) -> bool:
    return any(p == purpose and b == batch and t >= turn for t, p, b in book.settled)


def _civ_budget(world, civ: int, acc) -> int:
    from chronicler.mutual_aid import _treasury_budget
    if not 0 <= civ < len(world.civilizations):
        raise MoneyError(f"unknown civilization {civ}")
    return max(0, math.floor(_treasury_budget(world, world.civilizations[civ], acc)))


def _wealth(sim, ids) -> dict[int, int]:
    """Whole milli-units each living id holds (one fresh snapshot read)."""
    if sim is None:
        raise MoneyError("agent payments require the native simulator")
    snap = sim.get_snapshot()
    got = dict(zip((int(a) for a in snap.column("id").to_pylist()),
                   (float(w) for w in snap.column("wealth").to_pylist()), strict=True))
    return {aid: math.floor(got[aid] * MILLI) if aid in got and got[aid] > 0 else 0
            for aid in ids if aid in got}


def quote(world, bill: Bill, *, turn: int, book: MoneyBook, acc=None, sim=None,
          firms: dict[int, Any] | None = None) -> Quote:
    """Validate the whole bill and compute what it needs; moves nothing."""
    _validate_shape(bill)
    total = sum(amount for _, amount in bill.lines)
    if _settled(book, turn, bill.purpose, bill.batch):
        return Quote(False, "already_settled", total, None)
    # Every account that receives must exist before anything moves.
    for account in ([a for a, _ in bill.lines] if bill.payer is not None else [bill.payee]):
        if account.kind == "civ_treasury" and not 0 <= int(account.ident) < len(world.civilizations):
            raise MoneyError(f"unknown civilization {account.ident}")
        if account.kind == "firm_cash" and int(account.ident) not in (firms or {}):
            raise MoneyError(f"unknown firm {account.ident}")
    if bill.payer is not None and bill.payer.kind == "agent_wealth":
        # Pairwise: the payer covers the whole bill and every payee is alive,
        # from one fresh snapshot read.
        payer = int(bill.payer.ident)
        holdings = _wealth(sim, [payer] + [int(a.ident) for a, _ in bill.lines])
        if payer not in holdings:
            return Quote(False, "payer_absent", total, None)
        if any(int(a.ident) not in holdings for a, _ in bill.lines):
            return Quote(False, "payee_absent", total, holdings[payer])
        held = holdings[payer]
        return Quote(held >= total, None if held >= total else "payer_short", total, held)
    if bill.payer is not None:
        if bill.payer.kind == "civ_treasury":
            available = _civ_budget(world, int(bill.payer.ident), acc) * MILLI
            if _treasury_to_agents(bill):
                # The prepaid remainder of earlier bills is spent first.
                available += book.carry.get(f"{int(bill.payer.ident)}:{bill.purpose}", 0)
        else:
            firm = (firms or {}).get(int(bill.payer.ident))
            if firm is None:
                raise MoneyError(f"unknown firm {bill.payer.ident}")
            available = int(firm.cash)
        return Quote(available >= total, None if available >= total else "payer_short", total, available)
    holdings = _wealth(sim, [int(a.ident) for a, _ in bill.lines])
    for account, amount in bill.lines:
        held = holdings.get(int(account.ident))
        if held is None:
            return Quote(False, "payer_absent", total, None)
        if held < amount:
            return Quote(False, "payer_short", total, held)
    return Quote(True, None, total, None)


def _native_transfer(sim, turn: int, purpose: str, batch: int, rows):
    """The seam's one native call: keyed rows for ``purpose`` and ``batch``.
    A declared router of the ledger's payer registry
    (``wealth_accounting_state.WEALTH_ROUTERS``); ``pay`` is its only caller."""
    code = _native_code(sim, purpose)
    return sim.transfer_wealth(turn, code, batch, rows)


def _native_pairs(sim, turn: int, purpose: str, batch: int, rows):
    """The seam's one pairwise native call (A4): ``(payer, payee, amount)``
    rows for ``purpose`` and ``batch`` through ``settle_pairs``. A declared
    router of the ledger's payer registry; ``pay`` is its only caller."""
    code = _native_code(sim, purpose)
    if not callable(getattr(sim, "settle_pairs", None)):
        raise MoneyError("pairwise payments need a native build with settle_pairs (rebuild chronicler-agents)")
    return sim.settle_pairs(turn, code, batch, rows)


def _native_code(sim, purpose: str) -> int:
    code = PURPOSES[purpose]
    names = list(sim.wealth_transfer_purposes()) if callable(getattr(sim, "wealth_transfer_purposes", None)) else []
    if code is None or code >= len(names) or names[code] != NATIVE_ALIASES.get(purpose, purpose):
        raise MoneyError(f"payment purpose {purpose!r} needs a native build whose wealth transfer purposes "
                         f"name it at code {code} (rebuild chronicler-agents)")
    return code


def _credit_treasury(world, civ: int, purpose: str, amount: int, book: MoneyBook, acc) -> tuple[int, int, int]:
    key = f"{civ}:{purpose}"
    before = book.carry.get(key, 0)
    units, after = divmod(before + amount, MILLI)
    if after:
        book.carry[key] = after
    else:
        book.carry.pop(key, None)
    _move_treasury(world, civ, units, acc)
    return units, before, after


def _move_treasury(world, civ: int, units: int, acc) -> None:
    if not units:
        return
    target = world.civilizations[civ]
    if acc is None:
        target.treasury += units
    else:
        acc.add(civ, target, "treasury", units, "keep")


def _debit_prepaid(world, civ: int, purpose: str, debit: int, flows: list[MoneyFlow], book: MoneyBook,
                   acc) -> int:
    """A treasury -> agents bill (``TREASURY_AGENT_PURPOSES``): ``debit`` (what
    the agents took) is paid from the prepaid carry first, then in whole
    treasury units; the unspent rest of the last unit stays prepaid. Exact:
    ``units x 1000 + carry before == debit + carry after``. Each flow records
    its share of the units (negative, by what its agent took); the first flow
    the carry before, the last the carry after. Returns the units paid."""
    key = f"{civ}:{purpose}"
    before = book.carry.get(key, 0)
    units = max(0, -(-(debit - before) // MILLI))
    after = before + units * MILLI - debit
    if not 0 <= after < MILLI:
        raise MoneyError("a prepaid treasury carry left its range")
    if after:
        book.carry[key] = after
    else:
        book.carry.pop(key, None)
    _move_treasury(world, civ, -units, acc)
    # The units are split over the flows by what each agent took (largest
    # remainder, then flow order), so per-region totals add up to the bill's
    # units; the carry is the bill's (first flow before, last flow after).
    weights = [f.applied for f in flows]
    whole = sum(weights)
    shares = [units * w // whole if whole else 0 for w in weights]
    rests = sorted(range(len(flows)), key=lambda i: (-(units * weights[i] % whole if whole else 0), i))
    for i in rests[:units - sum(shares)]:
        shares[i] += 1
    for f, share in zip(flows, shares):
        f.treasury_units = -share
    if flows:
        flows[0].carry_before = before
        flows[-1].carry_after = after
    return units


def _record(book: MoneyBook, turn: int, flows: list[MoneyFlow]) -> None:
    if book.flows_turn != turn:
        book.flows_turn, book.flows, book.flows_dropped, book.totals = turn, [], 0, []
    def civ(account):
        return int(account[1]) if account[0] == "civ_treasury" else None

    index = {(t.purpose, t.payer_kind, t.payer_civ, t.payee_kind, t.payee_civ, t.region, t.payer_region): t
             for t in book.totals}
    for f in flows:
        key = (f.purpose, f.payer[0], civ(f.payer), f.payee[0], civ(f.payee), f.region, f.payer_region)
        total = index.get(key)
        if total is None:
            total = index[key] = FlowTotal(purpose=f.purpose, payer_kind=f.payer[0], payee_kind=f.payee[0],
                                           region=f.region, payer_civ=civ(f.payer), payee_civ=civ(f.payee),
                                           payer_region=f.payer_region)
            book.totals.append(total)
        total.applied += f.applied
        total.residual += f.residual
        total.count += 1
        total.treasury_units += f.treasury_units
        total.carry_change += (f.carry_after or 0) - (f.carry_before or 0)
    book.flows.extend(flows)
    if len(book.flows) > MAX_FLOWS:
        book.flows_dropped += len(book.flows) - MAX_FLOWS
        del book.flows[MAX_FLOWS:]


def pay(world, bill: Bill, *, turn: int, book: MoneyBook, acc=None, sim=None,
        firms: dict[int, Any] | None = None) -> Receipt:
    """Validate the whole bill, then move it once; a refused bill moves nothing."""
    q = quote(world, bill, turn=turn, book=book, acc=acc, sim=sim, firms=firms)
    if not q.ok:
        return Receipt(False, q.reason, total=q.total)
    flows: list[MoneyFlow] = []
    regions = bill.regions or (None,) * len(bill.lines)
    order = sorted(range(len(bill.lines)), key=lambda i: bill.lines[i][0].key())
    applied_total = residual_total = sunk = units_total = 0
    if bill.payer is not None and bill.payer.kind == "agent_wealth":
        payer = int(bill.payer.ident)
        rows = [(payer, int(bill.lines[i][0].ident), bill.lines[i][1]) for i in order]
        got = _native_pairs(sim, turn, bill.purpose, bill.batch, rows)
        if len(got) != len(rows):
            raise MoneyError("native pairwise rows do not match the bill")
        for i, row, (gp, ge, requested, sent, credited, refunded, status) in zip(order, rows, got, strict=True):
            if (int(gp), int(ge), int(requested)) != row:
                raise MoneyError("native pairwise rows do not match the bill")
            sent, credited, refunded = int(sent), int(credited), int(refunded)
            if int(status) == 2 or sent != int(requested):
                raise MoneyError("a pairwise payer row was not paid in full (stale wealth read)")
            if credited + refunded != sent or min(credited, refunded) < 0:
                raise MoneyError("native pairwise rows do not close")
            applied_total += credited
            residual_total += refunded
            flows.append(MoneyFlow(turn=turn, phase=bill.phase, purpose=bill.purpose, batch=bill.batch,
                                   payer=("agent_wealth", payer), payee=("agent_wealth", row[1]),
                                   region=regions[i], requested=row[2], applied=credited, residual=refunded,
                                   residual_to="payer" if refunded else None,
                                   status="limited" if refunded else "applied", payer_region=bill.payer_region))
    elif bill.payer is not None:
        payer = bill.payer
        native = {}
        rows = [(int(a.ident), amount) for a, amount in bill.lines if a.kind == "agent_wealth"]
        if rows:
            for aid, requested, applied, residual, status in _native_transfer(sim, turn, bill.purpose, bill.batch,
                                                                              sorted(rows)):
                if int(applied) + int(residual) != int(requested):
                    raise MoneyError("native transfer rows do not close")
                native[int(aid)] = (int(applied), int(status))
        debit = 0
        for i in order:
            account, amount = bill.lines[i]
            status, applied, units, before, after = "applied", amount, 0, None, None
            if account.kind == "agent_wealth":
                applied, code_status = native[int(account.ident)]
                status = "absent" if code_status == 2 else "limited" if applied != amount else "applied"
            elif account.kind == "civ_treasury":
                units, before, after = _credit_treasury(world, int(account.ident), bill.purpose, amount, book, acc)
            elif account.kind == "firm_cash":
                firm = (firms or {}).get(int(account.ident))
                if firm is None:
                    raise MoneyError(f"unknown firm {account.ident}")
                firm.cash += amount
            else:
                book.sinks[str(account.ident)] = book.sinks.get(str(account.ident), 0) + amount
            residual = amount - applied
            to = None
            if residual:
                if bill.residual == "return_to_payer":
                    to = "payer"
                else:
                    to = bill.residual
                    name = bill.residual[5:]
                    book.sinks[name] = book.sinks.get(name, 0) + residual
                    sunk += residual
            debit += applied + (residual if to not in (None, "payer") else 0)
            applied_total += applied
            residual_total += residual
            units_total += units
            flows.append(MoneyFlow(turn=turn, phase=bill.phase, purpose=bill.purpose, batch=bill.batch,
                                   payer=(payer.kind, payer.ident), payee=(account.kind, account.ident),
                                   region=regions[i], requested=amount, applied=applied, residual=residual,
                                   residual_to=to, status=status, treasury_units=units, carry_before=before,
                                   carry_after=after))
        if payer.kind == "civ_treasury" and _treasury_to_agents(bill):
            units_total = -_debit_prepaid(world, int(payer.ident), bill.purpose, debit, flows, book, acc)
        elif payer.kind == "civ_treasury":
            # Every line is whole units and never limited (no agent payee).
            _move_treasury(world, int(payer.ident), -(debit // MILLI), acc)
            for f in flows:
                f.treasury_units = -(f.applied // MILLI)
            units_total = -(debit // MILLI)
        else:
            firms[int(payer.ident)].cash -= debit
            if firms[int(payer.ident)].cash < 0:
                raise MoneyError("firm cash went negative")
    else:
        payee = bill.payee
        rows = sorted((int(a.ident), -amount) for a, amount in bill.lines)
        got = {}
        for aid, requested, applied, residual, status in _native_transfer(sim, turn, bill.purpose, bill.batch, rows):
            if int(applied) != int(requested):
                raise MoneyError("a collection line was not applied in full (stale wealth read)")
            got[int(aid)] = -int(applied)
        received = 0
        for i in order:
            account, amount = bill.lines[i]
            applied = got[int(account.ident)]
            received += applied
            applied_total += applied
            flows.append(MoneyFlow(turn=turn, phase=bill.phase, purpose=bill.purpose, batch=bill.batch,
                                   payer=(account.kind, account.ident), payee=(payee.kind, payee.ident),
                                   region=regions[i], requested=amount, applied=applied))
        if payee.kind == "firm_cash":
            firms[int(payee.ident)].cash += received
        elif payee.kind == "civ_treasury":
            units, before, after = _credit_treasury(world, int(payee.ident), bill.purpose, received, book, acc)
            units_total += units
            if flows:
                flows[-1].treasury_units, flows[-1].carry_before, flows[-1].carry_after = units, before, after
        else:
            book.sinks[str(payee.ident)] = book.sinks.get(str(payee.ident), 0) + received
    book.settled = [k for k in book.settled if k[0] >= turn]
    book.settled.append((turn, bill.purpose, bill.batch))
    _record(book, turn, flows)
    return Receipt(True, None, total=q.total, applied=applied_total, residual=residual_total, sunk=sunk,
                   treasury_units=units_total, flows=flows)


# ---------------------------------------------------------------------------
# The register the A1 ledger reads
# ---------------------------------------------------------------------------

#: Packages whose persisted state keeps a :class:`MoneyBook` (``state.book``; append only).
MONEY_BOOKS: tuple[str, ...] = ("workshop_economics", "epidemic_care", "titled_trade")


def flows_for_turn(world, turn: int) -> list[MoneyFlow] | None:
    """Every flow the seam settled in ``turn``, from the active packages that
    keep a book; None when no such package is active."""
    container = getattr(world, "livelihoods", None)
    seen = False
    out: list[MoneyFlow] = []
    for name in MONEY_BOOKS:
        sub = getattr(container, name, None) if container is not None else None
        if sub is None or not getattr(sub, "enabled", False):
            continue
        seen = True
        book = sub.book
        if book.flows_turn == turn:
            out.extend(book.flows)
    return out if seen else None


def totals_for_turn(world, turn: int) -> list[FlowTotal] | None:
    """The exact per-(purpose, account kinds, region) totals the seam settled in
    ``turn``, from the active packages that keep a book; None when no such
    package is active. The ledger reads these, so a turn with more flows than
    ``MAX_FLOWS`` is still counted in full."""
    container = getattr(world, "livelihoods", None)
    seen = False
    out: list[FlowTotal] = []
    for name in MONEY_BOOKS:
        sub = getattr(container, name, None) if container is not None else None
        if sub is None or not getattr(sub, "enabled", False):
            continue
        seen = True
        if sub.book.flows_turn == turn:
            out.extend(sub.book.totals)
    return out if seen else None


def check_book(book: MoneyBook) -> None:
    """Carries below one unit; sinks non-negative; flows close."""
    if any(not 0 < v < MILLI for v in book.carry.values()):
        raise MoneyError("a treasury carry must be between 1 and 999 milli-units")
    if any(v < 0 for v in book.sinks.values()):
        raise MoneyError("a sink balance is negative")
    for f in book.flows:
        if f.applied + f.residual != f.requested or f.requested <= 0:
            raise MoneyError("a money flow does not close")
    if sum(t.count for t in book.totals) != len(book.flows) + book.flows_dropped:
        raise MoneyError("the turn's flow totals do not count every flow")
    if not book.flows_dropped:
        for t in book.totals:
            applied = sum(f.applied for f in book.flows if (f.purpose, f.payer[0], f.payee[0], f.region,
                                                             f.payer_region)
                          == (t.purpose, t.payer_kind, t.payee_kind, t.region, t.payer_region)
                          and (t.payer_civ is None or f.payer[1] == t.payer_civ)
                          and (t.payee_civ is None or f.payee[1] == t.payee_civ))
            if applied != t.applied:
                raise MoneyError("a flow total does not match its flows")
