"""Persisted state of RS2 maintenance, reconstruction and repair projects (``--repair-projects``, default off).

Owned by :mod:`chronicler.repair_projects`. Pure data with no simulation imports, so
:mod:`chronicler.livelihoods_state` can import it.

Identities: ``region`` is the index in ``world.regions``; a granary asset is
named by its region index, a workshop asset by its L1 site id (``site``, a
stable never-reused workshop counter) and its city's M56a ``settlement_id``;
``civ``/``payer``/``controller`` are indices in ``world.civilizations`` (-1:
none); agent ids are native stable ids. A project's ``pid`` and a war-damage
record's ``did`` are persisted sequence numbers, never reused; no other
identifier is invented. A war's identity is ``(war_key, war_start_turn)``
when it could be determined, else both are None.

Bounded: at most one open project per asset (at most four workshop sites and
one granary per region), ``MAX_CLOSED`` closed projects, ``MAX_DAMAGES``
recent war-damage records, ``MAX_HISTORY`` dated history entries per project
and one completed-turn frame (receipts, per-civ ledger, unmet needs). A world
that never enabled the switch has no sub-state, so feature-off output is
unchanged.

``cost_only`` is the cost-retaining control: projects reserve, pay and use
timber identically but do not change condition.

Tuple orders below are declaration orders: append new values at the end,
never reorder.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

#: Modes (first: the default when enabled).
MODES: tuple[str, ...] = ("repair", "cost_only")
#: Asset kinds of the bounded asset set.
KINDS: tuple[str, ...] = ("granary", "workshop")
#: Why a project exists: ordinary maintenance, or reconstruction after war damage.
CAUSES: tuple[str, ...] = ("wear", "war")
PROJECT_STATUSES: tuple[str, ...] = ("open", "completed", "abandoned")
#: Why a project ended before its scope was delivered.
ABANDON_REASONS: tuple[str, ...] = ("asset_closed", "no_controller", "switched_off")
#: What limited or stopped a project's work in a turn (``unqualified``: the
#: workshop crew had no qualified member and worked at ``UNQUALIFIED_RATE``).
REASONS: tuple[str, ...] = ("no_timber", "no_coins", "no_labor", "no_envelope", "unqualified")
#: The real war events that record damage.
DAMAGE_EVENTS: tuple[str, ...] = ("conquest", "sack", "seizure")
#: Why an asset below the opening threshold has no project.
UNMET_REASONS: tuple[str, ...] = ("no_controller", "zero_capacity", "building")

MAX_CLOSED = 16
MAX_DAMAGES = 32
MAX_HISTORY = 16
#: Most named workers on one workshop repair crew.
MAX_CREW = 4


class RepairProject(BaseModel):
    """One repair or reconstruction project of one asset.

    ``scope`` is the work (work units) the asset's deficit needed when the
    project opened, plus the deficit of every war damage attached while it
    was open; ``delivered`` is the work performed and paid; ``credited`` the
    part that moved condition (0 in ``cost_only``).
    """

    pid: int
    kind: Literal["granary", "workshop"]
    asset: int
    region: int
    settlement_id: int | None = None
    cause: Literal["wear", "war"]
    war_key: str | None = None
    war_start_turn: int | None = None
    damages: list[int] = Field(default_factory=list)
    opened_turn: int
    opened_condition: float
    controller: int
    scope: float
    delivered: float = 0.0
    credited: float = 0.0
    status: Literal["open", "completed", "abandoned"] = "open"
    closed_turn: int | None = None
    closed_reason: str | None = None
    work_turns: int = 0
    stalled_turns: int = 0
    stalls: dict[str, int] = Field(default_factory=dict)
    timber_used: float = 0.0
    wages_milli: int = 0
    coin_cost_milli: int = 0
    #: The last worked turn's named repair crew (workshops), by stable id;
    #: cleared with a dated note when the native pool is rebuilt.
    last_crew: list[int] = Field(default_factory=list)
    #: (turn, event, civ, amount); amounts in milli-units or milli-work.
    history: list[tuple[int, str, int, int]] = Field(default_factory=list)


class WarDamage(BaseModel):
    """Condition one real war event took from one asset (at most one record
    per asset per turn)."""

    did: int
    turn: int
    kind: Literal["granary", "workshop"]
    asset: int
    region: int
    event: Literal["conquest", "sack", "seizure"]
    war_key: str | None = None
    war_start_turn: int | None = None
    amount: float
    condition_before: float
    condition_after: float
    #: The project the damage belongs to (None until one opens).
    project: int | None = None


class RepairReceipt(BaseModel):
    """One open project's completed Phase 2."""

    turn: int
    pid: int
    kind: Literal["granary", "workshop"]
    asset: int
    region: int
    payer: int
    status: Literal["progress", "stalled"]
    reasons: list[str] = Field(default_factory=list)
    requested: float = 0.0
    delivered: float = 0.0
    credited: float = 0.0
    rate: float | None = None
    crew: list[int] = Field(default_factory=list)
    share: float | None = None
    qualified: list[int] = Field(default_factory=list)
    veterans: list[int] = Field(default_factory=list)
    timber_held: float = 0.0
    timber_used: float = 0.0
    timber_returned: float = 0.0
    wages_due_milli: int = 0
    wages_milli: int = 0
    wage_residual_milli: int = 0
    coin_cost_milli: int = 0
    envelope: int | None = None
    condition_before: float
    condition_after: float
    remaining_after: float
    #: Ordinary income the native wealth phase withheld from the crew for its
    #: paid share (None: not observed).
    income_replaced: float | None = None


class CivLedger(BaseModel):
    """One civilization's repair accounts in one turn. The treasury pays whole
    units, once per civ and turn; the sub-unit part of the last whole unit is
    prepaid toward the civ's next repair costs. Exact closure:
    ``charged * 1000 + prepaid_before_milli == coin_cost_milli +
    wages_applied_milli + prepaid_after_milli``, both balances in [0, 1000)."""

    turn: int
    civ: int
    projects: int
    work_delivered: float
    timber_used: float
    coin_cost_milli: int
    wages_due_milli: int
    wages_applied_milli: int
    wage_residual_milli: int
    charged: int
    prepaid_before_milli: int
    prepaid_after_milli: int
    envelope: int | None = None


class UnmetNeed(BaseModel):
    """An asset below the opening threshold without a project, and why."""

    kind: Literal["granary", "workshop"]
    asset: int
    region: int
    condition: float
    reason: str


class RepairProjectsState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["repair", "cost_only"] = "repair"
    next_pid: int = 0
    next_did: int = 0
    projects: list[RepairProject] = Field(default_factory=list)
    closed: list[RepairProject] = Field(default_factory=list)
    damages: list[WarDamage] = Field(default_factory=list)
    #: The last completed turn's frame. ``receipts``/``ledger`` are None when
    #: that turn had no Phase 2 (unknown, not zero).
    frame_turn: int | None = None
    receipts: list[RepairReceipt] | None = None
    ledger: list[CivLedger] | None = None
    unmet: list[UnmetNeed] = Field(default_factory=list)
    #: Regions whose ordinary storage request was suspended in the frame turn.
    suspended: list[int] = Field(default_factory=list)
    last_settled_turn: int | None = None
    #: civ index -> milli-units already charged in whole units and not yet
    #: used (each in [0, 1000)); written off when the civ has no regions or
    #: the switch is turned off.
    prepaid: dict[int, int] = Field(default_factory=dict)
    #: Scalar lifetime counters (bounded: a fixed key set).
    counters: dict[str, float] = Field(default_factory=dict)
    # Transient, within one turn (Phase 2 -> Phase 10); never serialized.
    _turn: object | None = PrivateAttr(default=None)

    def __getstate__(self):
        state = super().__getstate__()
        private = state.get("__pydantic_private__")
        if private and private.get("_turn") is not None:
            state = {**state, "__pydantic_private__": {**private, "_turn": None}}
        return state

    def __setstate__(self, state):
        super().__setstate__(state)
        # An RS0 pickle holds only the switch, mode and counters.
        for name, field in type(self).model_fields.items():
            if name not in self.__dict__:
                self.__dict__[name] = field.get_default(call_default_factory=True)
        if getattr(self, "__pydantic_private__", None) is None:
            object.__setattr__(self, "__pydantic_private__", {"_turn": None})
        else:
            self.__pydantic_private__.setdefault("_turn", None)
