"""Persisted state of L6a workshop payroll (``--workshop-payroll``, default off).

One debt-free firm account per operating L1 workshop site: working cash in
whole milli-units (1000 = one treasury unit = one native wealth unit), owned
wares in milli-loads, wages owed to named workers (stable native ids) and the
firm's current hours and crew cap. Identities: ``site`` is the L1 site id,
``region`` an index in ``world.regions``, civilizations are indices in
``world.civilizations``, academy seats are indices in
``world.scholarship.seats``. Receipts and typed transfers describe the last
completed turn only (one frame); each firm keeps bounded lifetime totals and
a bounded dated history, never a lifetime copy of its flows. Pure data.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

#: Payroll modes, in declaration order (append only). ``paid``: sales fund
#: wages; ``unpaid_labor`` (cost-retaining ablation): the firm still sells and
#: the crew's ordinary income share is still replaced, but no wage is paid;
#: ``no_customer`` (demand-collapse control): wages are owed but nothing is sold.
PAYROLL_MODES: tuple[str, ...] = ("paid", "unpaid_labor", "no_customer")
#: Firm closure reasons, in declaration order (append only). ``insolvent``
#: is a declared run of insolvent turns; the others mirror the L1 site's.
FIRM_CLOSE_REASONS: tuple[str, ...] = ("insolvent", "city_fell", "city_missing", "region_changed")
#: Money transfer kinds (append only). ``sale``: buyer treasury -> firm cash;
#: ``wage``: firm cash -> agent wealth; ``distribution``: firm cash -> owner
#: treasury; ``write_off``: firm cash -> named sink (no owner, sub-unit rest);
#: ``stipend`` (RS1): firm cash -> an apprentice's wealth.
MONEY_KINDS: tuple[str, ...] = ("sale", "wage", "distribution", "write_off", "stipend")
#: Material transfer kinds (append only). ``title``: region market -> firm
#: inventory; ``delivery``: firm inventory -> academy inventory; ``wear``:
#: firm inventory -> named sink; ``return``: firm inventory -> region market.
MATERIAL_KINDS: tuple[str, ...] = ("title", "delivery", "wear", "return")
#: Account kinds named by transfers (append only).
ACCOUNT_KINDS: tuple[str, ...] = (
    "civ_treasury", "workshop_cash", "agent_wealth", "region_market", "workshop_inventory",
    "academy_inventory", "sink",
)

MAX_OWED = 16


def _is_none(value) -> bool:
    return value is None

MAX_CLOSED = 8
MAX_HISTORY = 16
MAX_TRANSFERS = 512


class OwedWage(BaseModel):
    agent_id: int
    amount: int                      # milli-units still owed
    since_turn: int


class WorkshopFirm(BaseModel):
    site: int
    region: int
    settlement_id: int
    city_name: str
    opened_turn: int
    status: Literal["open", "closed"] = "open"
    closed_turn: int | None = None
    closed_reason: str | None = None
    cash: int = 0                    # milli-units, never negative (debt-free)
    inventory: int = 0               # milli-loads of wares the firm holds title to
    owed: list[OwedWage] = Field(default_factory=list)
    hours: float = 1.0
    crew_cap: int = 8
    insolvent_run: int = 0
    diverted: float = 0.0            # the city's diverted share at full hours, last observed
    totals: dict[str, int] = Field(default_factory=dict)
    history: list[tuple[int, str, int]] = Field(default_factory=list)   # (turn, event, amount)


class MoneyTransfer(BaseModel):
    """Typed money movement. Amounts are milli-units; ``applied`` is what
    actually moved, ``residual`` what the recipient's limit refused (it stays
    with the payer)."""

    id: str
    turn: int
    phase: Literal["phase2", "phase10"]
    kind: str
    payer: tuple[str, int]
    payee: tuple[str, int]
    amount: int
    applied: int
    residual: int = 0
    status: str = "applied"


class MaterialTransfer(BaseModel):
    """Typed movement of wares, in milli-loads."""

    id: str
    turn: int
    phase: Literal["phase2", "phase10"]
    kind: str
    source: tuple[str, int]
    dest: tuple[str, int]
    good: str = "crafts"
    requested: int
    delivered: int
    status: str = "delivered"


class PayrollReceipt(BaseModel):
    """One firm's completed turn. Money in milli-units, wares in milli-loads.

    ``crew``/``shares`` are this turn's paid workers and each one's share of
    the turn (the scheduled diverted time). ``income_replaced`` is the actual
    ordinary income the native wealth phase withheld for that time (None when
    no wealth phase observation exists: unknown, not zero).
    """

    turn: int
    site: int
    region: int
    controller: int | None = None
    operating: bool = False
    hours: float
    crew_cap: int
    crew: list[int] = Field(default_factory=list)
    shares: list[float] = Field(default_factory=list)
    output: float | None = None
    title_basis: float | None = None            # uncommitted region stock after the tick
    titled: int = 0
    cash_open: int = 0
    inventory_open: int = 0
    customers: int = 0
    sold: int = 0
    sales: int = 0
    wages_due: int = 0
    wages_paid: int = 0
    wages_cap_residual: int = 0
    owed_lapsed: int = 0
    owed_after: int = 0
    income_replaced: float | None = None
    worn: int = 0
    returned: int = 0
    distributed: int = 0
    written_off: int = 0
    cash_close: int = 0
    inventory_close: int = 0
    insolvent: bool = False
    hours_next: float | None = None
    crew_cap_next: int | None = None
    event: str | None = None
    #: RS1 apprentice stipends paid from cash after this receipt's payroll pass
    #: (``cash_close`` already net of them); absent unless apprenticeship paid one.
    stipends: int | None = Field(default=None, exclude_if=_is_none)


class WorkshopPayrollState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["paid", "unpaid_labor", "no_customer"] = "paid"
    firms: list[WorkshopFirm] = Field(default_factory=list)
    closed: list[WorkshopFirm] = Field(default_factory=list)
    frame_turn: int | None = None
    frame: list[PayrollReceipt] = Field(default_factory=list)
    money: list[MoneyTransfer] = Field(default_factory=list)
    materials: list[MaterialTransfer] = Field(default_factory=list)
    counters: dict[str, float] = Field(default_factory=dict)
    last_payroll_turn: int | None = None
    _turn: object | None = PrivateAttr(default=None)
