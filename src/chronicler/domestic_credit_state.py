"""Persisted state of domestic credit (see :mod:`chronicler.domestic_credit`).

Pure data with no simulation imports, so :mod:`chronicler.models` can import
it. A lender is named by its kind and key: the merchants of a region (key =
region index in ``world.regions``), a guild (key = index in
``GuildState.guilds``), a city (key = its M56a ``settlement_id``) or, for
the abstract creditor class, ``legacy`` (key -1) or ``houses`` (key = the
borrower's civ index).
Borrowers are civilization indices in ``world.civilizations``; a credit
line is the ``finance.Loan`` with the same ``loan_id``.

Tuple orders below are declaration orders: append new values at the end,
never reorder (stored values index into them).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

#: ``Funder.kind`` names. ``legacy`` holds the part of a domestic line lent
#: before the switch was on (the abstract creditor class of ``finance``):
#: what it receives leaves the treasury into the finance ledger only.
#: ``houses`` (2026-10, second pass) is the abstract creditor class lending
#: while the agent pool's wealth is still building up from its cold start
#: (key = the borrower's civ index; its receipts leave into the finance
#: ledger as ``legacy``'s do).
KIND_NAMES: tuple[str, ...] = ("merchants", "guild", "city", "legacy", "houses")
MERCHANTS, GUILD, CITY, LEGACY, HOUSES = range(len(KIND_NAMES))

#: Flow names of the ledger (``DomesticCreditState.totals`` keys are
#: ``<flow>_<kind name>``): principal lent, interest received, principal
#: repaid, unpaid interest capitalized into the claim, claims written off in
#: a default (``written_off``), lost with a fallen borrower (``lost``) and
#: lapsed with a fallen lender (``lapsed``).
FLOW_NAMES: tuple[str, ...] = ("lent", "interest", "repaid", "capitalized", "written_off", "lost",
                               "lapsed")
TOTAL_KEYS: tuple[str, ...] = tuple(f"{flow}_{kind}" for flow in FLOW_NAMES for kind in KIND_NAMES)


class Funder(BaseModel):
    """One lender's outstanding claim on one domestic credit line."""

    kind: int
    key: int
    principal: int


class CreditLine(BaseModel):
    """Who funded a domestic loan (``finance.Loan`` with this ``loan_id``):
    the funders' claims sum to the loan's principal at every turn boundary."""

    loan_id: str
    borrower: int
    funders: list[Funder] = Field(default_factory=list)


class DomesticCreditState(BaseModel):
    """World-level switch and books (``WorldState.domestic_credit``).

    ``merchant_due`` (per region index) is what the region's merchants are
    owed (positive) or owe (negative) on the books but has not reached their
    wealth yet: every turn the finance tick sends it to the native pool and
    keeps what could not be applied (no merchants there, every one at the
    wealth ceiling). ``grievance`` (per region index, 0..1) is the region's
    merchants' grievance toward a lord that defaulted on them.
    ``merchant_sent`` / ``merchant_applied`` are cumulative.
    """

    lines: list[CreditLine] = Field(default_factory=list)
    merchant_due: list[float] = Field(default_factory=list)
    grievance: list[float] = Field(default_factory=list)
    totals: dict[str, int] = Field(default_factory=lambda: {k: 0 for k in TOTAL_KEYS})
    merchant_sent: float = 0.0
    merchant_applied: float = 0.0
    defaults_on_lenders: int = 0
    last_tick_turn: int = -1


def domestic_credit_on(world) -> bool:
    """True only for a real domestic-credit state (mocks and None read as off)."""
    return isinstance(getattr(world, "domestic_credit", None), DomesticCreditState)
