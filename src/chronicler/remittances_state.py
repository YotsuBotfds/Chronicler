"""Persisted state of RS4 migration, knowledge and household support (``--remittances``, default off).

Owned by :mod:`chronicler.remittances`. Pure data with no simulation imports, so
:mod:`chronicler.livelihoods_state` can import it.

Identities: people are native stable ids (never slot indexes); regions are
indices in ``world.regions``. Money is in whole milli-units (1000 = one
native wealth unit), as the native wealth transfer counts it.

Everything is bounded: the diaspora ledger (at most ``MAX_ENTRIES`` open
entries, one per person; a full ledger refuses new departures and counts
them), one completed-turn frame (bounded samples of moves, closures,
receipts and unmet senders; one row per touched region; a funnel), the last
pool reset and scalar lifetime counters. The ledger is id-bound: a rebuilt
native pool closes every entry (``remittances.on_pool_reset``).

``record_only`` is the control: the ledger and every eligibility and amount
are computed the same way, and nothing is sent.

Tuple orders below are declaration orders: append new values at the end,
never reorder.
"""
from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from chronicler.switch_state import SwitchStateMixin

#: Modes (first: the default when enabled).
MODES: tuple[str, ...] = ("send", "record_only")
#: Native ``wealth_transfer`` row statuses, in code order.
TRANSFER_STATUSES: tuple[str, ...] = ("applied", "limited", "absent")
#: Receipt statuses: the native ones, then ``not_sent`` (the record_only control).
RECEIPT_STATUSES: tuple[str, ...] = TRANSFER_STATUSES + ("not_sent",)
#: Why a ledger entry closed.
CLOSE_REASONS: tuple[str, ...] = ("return", "death", "pool_reset", "unobserved_gap")
#: Kinds of an applied move seen by the ledger (``unrecorded``: a new
#: departure refused by a full ledger).
MOVE_KINDS: tuple[str, ...] = ("departure", "onward", "return", "unrecorded")
#: Why a migrant with an open entry was not an eligible sender this turn (first failing check).
SENDER_REASONS: tuple[str, ...] = ("child", "unsettled", "on_trip", "elsewhere", "already_sent")
#: Why an eligible sender had no linked recipient (unmet).
UNLINKED_REASONS: tuple[str, ...] = ("no_bond", "recipient_away", "recipient_on_trip")
#: Bonds a remittance may follow (native ``BondType`` names).
BOND_KINDS: tuple[str, ...] = ("marriage", "kin")

MAX_ENTRIES = 2048
MAX_MOVES = 64
MAX_CLOSURES = 64
MAX_RECEIPTS = 64
MAX_UNMET = 32

#: Lifetime counters (insertion order). ``*_milli`` are money; the rest count people or rows.
COUNTERS: tuple[str, ...] = (
    "turns", "moves_seen", "departures", "onward_moves", "returns", "entries_refused",
    "deaths", "pool_resets", "entries_closed_on_reset", "gap_closures",
    "qualified_departures", "qualified_arrivals", "qualified_returns",
    "sender_turns_evaluated", "eligible_sender_turns", "linked_sender_turns", "unlinked_sender_turns",
    "no_surplus_sender_turns", "rows", "rows_applied", "rows_limited", "rows_absent", "rows_not_sent",
    "requested_milli", "fee_requested_milli", "sent_milli", "fee_milli", "credited_milli",
    "refunded_milli", "not_sent_milli",
)


class DiasporaEntry(BaseModel):
    """One open migration: where the person left, when, and where they live now."""

    id: int
    origin: int                          # the region left at the first recorded departure
    departure_turn: int
    destination: int                     # where the last applied move took them
    arrival_turn: int
    moves: int = 1                       # applied moves since the departure (onward moves add)
    qualified: bool = False              # held an RS1 workshop qualification at the last move
    last_sent_turn: int | None = None    # per-sender exactly-once guard
    sent_turns: int = 0
    credited_milli: int = 0              # lifetime credited to the origin


class MoveRecord(BaseModel):
    """An applied native migration of this turn, as the ledger read it."""

    id: int
    from_region: int
    to_region: int
    kind: str                            # MOVE_KINDS
    qualified: bool = False
    driver: int | None = None            # native migration driver (None: not recorded)


class Closure(BaseModel):
    id: int
    origin: int
    destination: int
    departure_turn: int
    closed_turn: int
    reason: str                          # CLOSE_REASONS


class RemittanceReceipt(BaseModel):
    """One sender's row this turn: the requested remittance and what moved."""

    turn: int
    sender: int
    recipient: int
    bond: str                            # BOND_KINDS
    sentiment: int
    origin: int                          # the recipient's region
    destination: int                     # the sender's region
    wealth_milli: int                    # the sender's wealth before the row
    amount: int                          # requested for the recipient
    fee_requested: int
    sent: int = 0                        # left the sender
    fee: int = 0                         # kept by the courier sink
    credited: int = 0                    # reached the recipient
    refunded: int = 0                    # refused by the recipient's ceiling, back to the sender
    status: str                          # RECEIPT_STATUSES


class UnmetSender(BaseModel):
    """An eligible sender with no linked recipient this turn."""

    id: int
    origin: int
    destination: int
    reason: str                          # UNLINKED_REASONS
    surplus_milli: int                   # wealth above the reserve (0 when none)


class RegionFlow(BaseModel):
    """A region's diaspora this turn: losses and gains kept separate, with the
    stock of open entries after the turn and the remittances that crossed it."""

    region: int
    departures: int = 0                  # applied moves out (losses)
    arrivals: int = 0                    # applied moves in (gains)
    returns_home: int = 0                # arrivals that closed an entry as a return
    qualified_departures: int = 0        # skill leaving
    qualified_arrivals: int = 0          # skill arriving
    diaspora_out: int = 0                # open entries that left this region
    diaspora_in: int = 0                 # open entries living here
    qualified_out: int = 0
    qualified_in: int = 0
    senders: int = 0                     # rows sent from here (host)
    recipients: int = 0                  # rows received here (origin)
    outflow_milli: int = 0               # host: senders' net loss (credited + fee)
    fee_milli: int = 0                   # host: of which the courier fee
    refunded_milli: int = 0              # host: returned to senders here
    inflow_milli: int = 0                # origin: credited to recipients here


class PoolReset(BaseModel):
    turn: int
    entries_closed: int
    reason: str


class RemittancesState(SwitchStateMixin, BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["send", "record_only"] = "send"
    last_settled_turn: int | None = None
    #: The diaspora ledger: open entries, ascending id.
    entries: list[DiasporaEntry] = Field(default_factory=list)
    # One completed-turn frame (empty until a turn was settled).
    frame_turn: int | None = None
    moves: list[MoveRecord] = Field(default_factory=list)
    moves_dropped: int = 0
    closures: list[Closure] = Field(default_factory=list)
    closures_dropped: int = 0
    receipts: list[RemittanceReceipt] = Field(default_factory=list)
    receipts_dropped: int = 0
    unmet: list[UnmetSender] = Field(default_factory=list)
    unmet_dropped: int = 0
    regions: list[RegionFlow] = Field(default_factory=list)
    funnel: dict[str, int] = Field(default_factory=dict)
    totals: dict[str, int] = Field(default_factory=dict)
    last_pool_reset: PoolReset | None = None
    #: Scalar lifetime counters (bounded: the fixed ``COUNTERS`` key set).
    counters: dict[str, int] = Field(default_factory=dict)
    _BUMP: ClassVar[dict] = {"allowed": COUNTERS, "coerce": int}
