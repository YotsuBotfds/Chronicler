"""Persisted state of infrastructure condition and repair (``--infrastructure-condition``, default off).

Owned by :mod:`chronicler.infrastructure_condition`. Pure data with no
simulation imports, so :mod:`chronicler.livelihoods_state` can import it.
Connected-world program, lane B3; design: the Program B audit, section 7.3
("sibling record ``infrastructure_works``"); integration page
``docs/integration/infrastructure-condition.md``.

Identities. An asset's ``aid`` is a persisted sequence number allocated when
an active irrigation or road record is first seen, never reused; it is
matched to its record by ``(region, record_index, type, built_turn,
builder_civ)`` (records are append-only; a removed record list destroys the
assets it held, and a rebuild is a new record with a new ``aid``). ``region``
is the index in ``world.regions``; ``record_index`` the index in that
region's ``infrastructure`` list; ``builder_civ`` the builder's name as the
record holds it; ``responsible``/``payer``/``civ`` are indices in
``world.civilizations`` (-1: none). A work's ``wid`` and a damage record's
``did`` are persisted sequence numbers, never reused.

Bounded: at most one open work per asset, ``MAX_CLOSED`` closed works,
``MAX_DAMAGES`` recent damage records, ``MAX_TERMINAL`` assets kept after
they turned inactive or destroyed, ``MAX_HISTORY`` dated entries per asset
and work, and one completed-turn frame. A world that never enabled the switch
has no sub-state, so feature-off output is unchanged.

Tuple orders below are declaration orders: append new values at the end,
never reorder.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

from chronicler.money import MoneyBook

#: Modes (first: the default when enabled). ``repair``: works repair
#: condition; ``record_only``: condition is tracked and recorded, service is
#: forced to 1.0 and no work opens (equals the switch off except the record);
#: ``wear_only``: condition and service act, nothing repairs (the control
#: against the same wear assumption); ``cost_only``: works plan, hold, use
#: and pay identically but credit no condition (RS2's cost control).
MODES: tuple[str, ...] = ("repair", "record_only", "wear_only", "cost_only")
#: Modes whose works plan and pay (they need ``--repair-projects``).
WORK_MODES: tuple[str, ...] = ("repair", "cost_only")
#: Asset kinds, in the fixed split order of shared labour, timber and coins.
KINDS: tuple[str, ...] = ("irrigation", "roads")
#: ``serving``: the record is active and condition > 0; ``failed``: the record
#: is active and condition is 0 (serves nothing; must be repaired, cannot be
#: rebuilt); ``inactive``: the record was deactivated (scorch, earthquake,
#: depopulation, ...); ``destroyed``: the record list was removed.
STATUSES: tuple[str, ...] = ("serving", "failed", "inactive", "destroyed")
#: Why an asset turned inactive or destroyed (read from dated world state).
END_CAUSES: tuple[str, ...] = ("scorch", "earthquake", "depopulation", "unknown", "record_removed")
#: Real events that record damage (``flood``: a watershed ``flow`` flood's
#: onset, ``watershed._apply_flow``).
DAMAGE_EVENTS: tuple[str, ...] = ("conquest", "sack", "flood")
#: Why a work exists.
WORK_CAUSES: tuple[str, ...] = ("wear", "war", "flood")
WORK_STATUSES: tuple[str, ...] = ("open", "completed", "abandoned")
#: Why a work ended before its scope was delivered.
ABANDON_REASONS: tuple[str, ...] = ("asset_lost", "no_controller", "switched_off")
#: What limited or stopped a work in a turn. ``granary_first``: the region's
#: granary (storage or an RS2 project) holds the shared labour column this
#: turn (the fixed split order granary -> irrigation -> roads).
REASONS: tuple[str, ...] = ("no_timber", "no_coins", "no_labor", "no_envelope", "granary_first")
#: Why an asset below the opening threshold has no work.
UNMET_REASONS: tuple[str, ...] = ("no_controller",)

#: Every lifetime counter name; ``infrastructure_condition._bump`` refuses
#: any other, so a renamed counter cannot silently read as zero.
COUNTERS: frozenset[str] = frozenset({
    "assets_opened", "assets_failed", "assets_restored", "assets_inactive", "assets_destroyed",
    "responsibility_moved", "wear", "damages", "damage", "cap_waste",
    "progress_turns", "stalled_turns", "work_delivered", "work_credited", "timber_used",
    "charged", "coin_cost_milli", "prepaid_written_off_milli", "settled_turns", "inherited",
    "shared_regions", "damages_dropped", "damages_dropped_unattached", "damages_skipped_same_turn",
    *(f"damages_skipped_{e}" for e in DAMAGE_EVENTS),
    *(f"assets_opened_{k}" for k in KINDS),
    *(f"assets_failed_{k}" for k in KINDS),
    *(f"{k}_work" for k in KINDS),
    *(f"wear_{k}" for k in KINDS),
    *(f"damage_{k}" for k in KINDS),
    *(f"{s}_{c}" for s in ("inactive", "destroyed") for c in END_CAUSES),
    *(f"damages_{e}" for e in DAMAGE_EVENTS),
    *(f"opened_{c}" for c in WORK_CAUSES),
    *(f"opened_{k}" for k in KINDS),
    "completed",
    *(f"abandoned_{r}" for r in ABANDON_REASONS),
    *(f"{p}_{r}" for p in ("stalled", "limited") for r in REASONS),
    *(f"unmet_{r}" for r in UNMET_REASONS),
})

MAX_CLOSED = 16
#: Recent damage records kept (a declared bound; drops are counted).
MAX_DAMAGES = 32
MAX_TERMINAL = 32
MAX_HISTORY = 16


class InfraAsset(BaseModel):
    """One irrigation work or road, with its condition and service."""

    aid: int
    kind: Literal["irrigation", "roads"]
    region: int
    record_index: int
    built_turn: int
    builder_civ: str
    opened_turn: int
    condition: float = 1.0
    status: Literal["serving", "failed", "inactive", "destroyed"] = "serving"
    status_turn: int
    #: Why it turned inactive or destroyed (``END_CAUSES``), else None.
    cause: str | None = None
    #: The region's controller responsible for it (-1: none); moves with a
    #: dated note when the region changes hands.
    responsible: int = -1
    #: Lifetime condition lost to wear and to damage, and credited by repair.
    wear: float = 0.0
    damage: float = 0.0
    credited: float = 0.0
    #: The turn its condition last fell to 0 (it failed), if ever.
    failed_turn: int | None = None
    #: Irrigation only, observed each Phase 10 with an economy tick: the food
    #: the region would lose over L9's horizon without repair (arable ceiling
    #: lost x observed production / arable capacity); None when unobserved.
    food_at_risk: float | None = None
    #: Dated entries ``(turn, event, civ, milli)``, at most ``MAX_HISTORY``.
    history: list[tuple[int, str, int, int]] = Field(default_factory=list)


class InfraDamage(BaseModel):
    did: int
    turn: int
    aid: int
    kind: Literal["irrigation", "roads"]
    region: int
    event: str
    war_key: str | None = None
    war_start_turn: int | None = None
    #: A flood's source reference (the watershed record), else None.
    ref: str | None = None
    amount: float
    condition_before: float
    condition_after: float
    #: The work it was attached to (None until a work takes it).
    work: int | None = None


class SkippedDamage(BaseModel):
    """A damage the one-damage-per-asset-per-turn rule skipped: the asset was
    already damaged this turn (``kept``: that record's ``did``)."""

    turn: int
    aid: int
    region: int
    event: str
    war_key: str | None = None
    ref: str | None = None
    #: The condition the skipped event would have taken.
    amount: float
    kept: int


class InfraWork(BaseModel):
    """A repair work on one asset (the sibling of an RS2 project)."""

    wid: int
    aid: int
    kind: Literal["irrigation", "roads"]
    region: int
    cause: str
    status: Literal["open", "completed", "abandoned"] = "open"
    opened_turn: int
    opened_condition: float
    controller: int
    #: Work units to deliver (the deficit at opening, extended by damage).
    scope: float
    delivered: float = 0.0
    credited: float = 0.0
    timber_used: float = 0.0
    coin_cost_milli: int = 0
    work_turns: int = 0
    stalled_turns: int = 0
    #: Stall turns per reason (``REASONS``).
    stalls: dict[str, int] = Field(default_factory=dict)
    damages: list[int] = Field(default_factory=list)
    war_key: str | None = None
    war_start_turn: int | None = None
    closed_turn: int | None = None
    closed_reason: str | None = None
    history: list[tuple[int, str, int, int]] = Field(default_factory=list)


class WorkReceipt(BaseModel):
    """One work's Phase 2 of one turn."""

    turn: int
    wid: int
    aid: int
    kind: Literal["irrigation", "roads"]
    region: int
    payer: int
    status: Literal["progress", "stalled"]
    reasons: list[str] = Field(default_factory=list)
    requested: float
    delivered: float
    credited: float
    #: The granary's own request in the shared column of this region this
    #: turn (granary first), and whether the region's column was shared.
    granary_request: float = 0.0
    shared: bool = False
    timber_held: float = 0.0
    timber_used: float = 0.0
    timber_returned: float = 0.0
    coin_cost_milli: int = 0
    envelope: int | None = None
    condition_before: float
    condition_after: float
    remaining_after: float


class WorksLedger(BaseModel):
    """One civ's charge of one turn: whole units through the payment seam,
    the sub-unit remainder prepaid toward its next works (RS2's rule).
    ``charged x 1000 + prepaid_before == coin_cost + prepaid_after``."""

    turn: int
    civ: int
    works: int
    work_delivered: float
    timber_used: float
    coin_cost_milli: int
    charged: int
    prepaid_before_milli: int
    prepaid_after_milli: int
    #: The works' own L9 envelope this turn (``infrastructure_works``; None
    #: without L9), and RS2's charge to the civ (planned before the works,
    #: from its own envelope and reservation).
    envelope: int | None = None
    rs2_charged: int = 0


class UnmetWork(BaseModel):
    aid: int
    kind: Literal["irrigation", "roads"]
    region: int
    condition: float
    reason: str


class InfrastructureConditionState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["repair", "record_only", "wear_only", "cost_only"] = "repair"
    next_aid: int = 0
    next_wid: int = 0
    next_did: int = 0
    #: Assets that are serving or failed, then at most ``MAX_TERMINAL`` that
    #: turned inactive or destroyed (``terminal``).
    assets: list[InfraAsset] = Field(default_factory=list)
    terminal: list[InfraAsset] = Field(default_factory=list)
    works: list[InfraWork] = Field(default_factory=list)
    closed: list[InfraWork] = Field(default_factory=list)
    damages: list[InfraDamage] = Field(default_factory=list)
    #: Damages skipped by the one-per-asset-per-turn rule (the last ``MAX_DAMAGES``).
    skipped_damages: list[SkippedDamage] = Field(default_factory=list)
    #: The turn the registry was last reconciled with the world's records.
    reconciled_turn: int | None = None
    #: The last turn wear was applied (once per turn).
    wear_turn: int | None = None
    #: The last completed turn's frame. ``receipts``/``ledger`` are None when
    #: that turn had no settled Phase 2 (unknown, not zero) or the mode has no works.
    frame_turn: int | None = None
    receipts: list[WorkReceipt] | None = None
    ledger: list[WorksLedger] | None = None
    unmet: list[UnmetWork] = Field(default_factory=list)
    #: Regions whose shared labour column carried a granary request and works.
    shared: list[int] = Field(default_factory=list)
    last_settled_turn: int | None = None
    #: civ index -> milli-units charged in whole units and not yet used (each
    #: in [0, 1000)); written off when the civ has no regions or the switch ends.
    prepaid: dict[int, int] = Field(default_factory=dict)
    #: The payment seam's book (``chronicler.money``): settled keys and flows.
    book: MoneyBook = Field(default_factory=MoneyBook)
    counters: dict[str, float] = Field(default_factory=dict)
    # Transient, within one turn (Phase 2 -> Phase 10); never serialized.
    _turn: object | None = PrivateAttr(default=None)
    # Transient, within one Phase 10: (turn, farmers per region) observed
    # after the agent tick, read by the same Phase 10's L9 proposal.
    _labour: object | None = PrivateAttr(default=None)

    def __getstate__(self):
        state = super().__getstate__()
        private = state.get("__pydantic_private__")
        if private and (private.get("_turn") is not None or private.get("_labour") is not None):
            state = {**state, "__pydantic_private__": {**private, "_turn": None, "_labour": None}}
        return state

    def __setstate__(self, state):
        super().__setstate__(state)
        for name, field in type(self).model_fields.items():
            if name not in self.__dict__:
                self.__dict__[name] = field.get_default(call_default_factory=True)
        if getattr(self, "__pydantic_private__", None) is None:
            object.__setattr__(self, "__pydantic_private__", {"_turn": None, "_labour": None})
        else:
            self.__pydantic_private__.setdefault("_turn", None)
            self.__pydantic_private__.setdefault("_labour", None)
