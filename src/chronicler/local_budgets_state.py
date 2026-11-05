"""Persisted state of the L9 local collective budgets (default off).

Identities: ``civ`` is an index in ``world.civilizations``; region numbers
(``recipients``) are indices in ``world.regions``; ``site`` is an L1 workshop
site id; ``venue``/``seat``/``settlement_id`` are city settlement ids. No new
identifiers are invented: a proposal's ``pid`` is its position in one
civ-turn's bounded proposal list and a commitment's ``cid`` is a persisted
sequence number.

Only the last decision frame (one row per deciding civ), the last settlement
frame, the commitments still open and scalar counters are kept: never a
lifetime copy. Tuple orders below are declaration orders (append only).
Pure data, importable by :mod:`chronicler.livelihoods_state`.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

#: ``--local-budget-mode`` values (first: the default when enabled).
MODES: tuple[str, ...] = ("bargained", "fixed_shares")
#: Built-in services in declaration order. Registered providers add their own.
SERVICES: tuple[str, ...] = ("relief", "granary_maintain", "granary_expand", "workshop",
                              "teaching_supplies", "wardens")
#: Existing constituencies that bargain, in declaration order (the tie-break).
CONSTITUENCIES: tuple[str, ...] = ("commons", "patricians")
#: Candidate allocations, in arbitration tie-break order.
CANDIDATES: tuple[str, ...] = ("compromise",) + CONSTITUENCIES
#: Settled commitment outcomes.
OUTCOMES: tuple[str, ...] = ("kept", "deferred", "lapsed")
#: Dated deferral reasons (append only).
REASONS: tuple[str, ...] = (
    "treasury_shortfall", "cost_rose", "recipient_lost", "inputs_short", "work_short",
    "no_supply", "service_off", "no_economy", "switched_off", "no_demand", "not_adopted",
)
#: Reasons a proposal was not awarded.
REFUSALS: tuple[str, ...] = ("no_support", "budget", "incompatible", "share", "not_chosen")
#: Proposals kept per civ per turn (the bounded proposal process).
MAX_PROPOSALS = 8
#: Settled commitments kept in the last settlement frame.
MAX_SETTLED = 256


class Proposal(BaseModel):
    """One candidate expenditure with an executable cost and dated benefit."""

    pid: int
    service: str
    civ: int
    source_turn: int
    recipients: list[int] = Field(default_factory=list)
    site: int | None = None
    claims: list[str] = Field(default_factory=list)
    cost: int
    divisible: bool = False
    unit: str
    expected: float
    #: Burden each constituency expects relieved at full cost, in its own unit.
    relief: dict[str, float] = Field(default_factory=dict)
    detail: dict[str, float | int | str | None] = Field(default_factory=dict)


class Award(BaseModel):
    pid: int
    amount: int
    sponsor: str | None = None


class Decision(BaseModel):
    """One civilization's budget decision (made in Phase 10 for the next turn)."""

    turn: int
    civ: int
    mode: str
    seat: int | None = None
    projected: int
    floor: int
    obligations: int
    committed: int
    budget: int
    influence: dict[str, float] = Field(default_factory=dict)
    #: Measured burden per constituency from dated observations (None: unknown).
    burdens: dict[str, float | None] = Field(default_factory=dict)
    proposals: list[Proposal] = Field(default_factory=list)
    dropped: int = 0
    #: Candidate allocation -> [[pid, amount], ...].
    candidates: dict[str, list[list[int]]] = Field(default_factory=dict)
    #: Candidate -> constituency -> share of its own best feasible relief.
    satisfaction: dict[str, dict[str, float]] = Field(default_factory=dict)
    scores: dict[str, float] = Field(default_factory=dict)
    chosen: str | None = None
    #: none, uncontested, commons_first, patricians_first, compromise or fixed_shares.
    outcome: str | None = None
    awards: list[Award] = Field(default_factory=list)
    refused: list[tuple[int, str]] = Field(default_factory=list)


class Commitment(BaseModel):
    """An accepted envelope: spending authority for one service, one turn."""

    cid: int
    civ: int
    service: str
    pid: int
    decided_turn: int
    for_turn: int
    recipients: list[int] = Field(default_factory=list)
    site: int | None = None
    claims: list[str] = Field(default_factory=list)
    amount: int
    unit: str
    expected: float
    sponsor: str | None = None
    venue: int | None = None
    # Settlement (None while open).
    outcome: Literal["kept", "deferred", "lapsed"] | None = None
    reason: str | None = None
    spent: int | None = None
    delivered: float | None = None
    ratio: float | None = None
    settled_turn: int | None = None
    response: float | None = None
    detail: dict[str, float | int | str | None] = Field(default_factory=dict)


class Response(BaseModel):
    """A city's grievance answering the observed delivery of its promises."""

    turn: int
    civ: int
    settlement_id: int
    before: float
    raw: float
    applied: float
    after: float


class LocalBudgetState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["bargained", "fixed_shares"] = "bargained"
    next_cid: int = 0
    open: list[Commitment] = Field(default_factory=list)
    decision_turn: int | None = None
    decisions: list[Decision] = Field(default_factory=list)
    settled_turn: int | None = None
    settled: list[Commitment] = Field(default_factory=list)
    responses: list[Response] = Field(default_factory=list)
    counters: dict[str, float] = Field(default_factory=dict)
    #: Execution observations recorded by the services within one turn and
    #: consumed (cleared) by that turn's settlement; empty between turns.
    _trace: dict = PrivateAttr(default_factory=dict)
