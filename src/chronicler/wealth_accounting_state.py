"""Persisted state of the observation-only wealth ledger (A1, ``--wealth-accounting``, default off).

Owned by :mod:`chronicler.wealth_accounting`. Pure data with no simulation
imports, so :mod:`chronicler.livelihoods_state` can import it. A world that
never enabled the switch has no sub-state, so feature-off output is unchanged.

Identities: regions are indices in ``world.regions``; civilizations are
indices in ``world.civilizations``; people are native stable ids, but no id is
persisted here (the closing balance is kept as a digest and per-region sums).
Units: native wealth units (f32 balances summed in f64) for balances and the
native model residual; whole milli-units (1000 = one wealth unit = one
treasury unit) for typed flows, as the native wealth transfer counts them;
whole treasury units for treasury charges and created treasury income.

Everything is bounded: one completed-turn frame (one row per region, one per
typed channel, one per paid-work package, one treasury row per civilization),
the last closing (a digest and one sum per region), a rolling dated log
(``MAX_LOG``), lifetime totals with the fixed key set ``LIFETIME`` and scalar
counters with the fixed key set ``COUNTERS``. Tuple orders below are
declaration orders: append new values at the end, never reorder.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, PrivateAttr

#: Typed channels: ``(channel, package switch, payer -> payee)``. A typed flow
#: moves native wealth between a named payer and payee through a keyed native
#: transfer (``wealth_transfer.rs``, ``credit.rs``); the household sector's
#: side is recorded here. ``package`` None: not a livelihoods switch.
CHANNELS: tuple[tuple[str, str | None, str], ...] = (
    ("workshop_wage", "workshop_payroll", "firm cash -> workshop crew (L6a)"),
    ("apprentice_stipend", "apprenticeship", "firm cash -> apprentice (RS1)"),
    ("repair_wage", "repair_projects", "treasury -> workshop repair crew (RS2)"),
    ("granary_crew_wage", "recovery_crews", "treasury granary coins -> granary crew (PL3)"),
    ("woodcut_wage", "timber_supply", "treasury -> woodcutting crew (PL1)"),
    ("food_procurement", "household_retail", "treasury -> owners of procured grain (L6b)"),
    ("food_purchase", "household_retail", "buyers -> sellers in the tick (L6b)"),
    ("remittance", "remittances", "sender -> recipient, fee to the courier sink (RS4)"),
    ("relocation_fare", "relocation_costs", "movers -> travel sink (L7)"),
    ("domestic_credit", None, "treasury <-> merchants, net applied (domestic credit)"),
)
CHANNEL_NAMES: tuple[str, ...] = tuple(c[0] for c in CHANNELS)

#: Packages that withhold a paid share of ordinary income through the shared
#: native paid-work receipt (``livelihoods.paid_work_receipt``), in the order
#: a receipt row is matched. PL3's granary and workshop crews are separate
#: (the recorded limit RL7); RS2's workshop crews are PL3's workshop crews
#: while PL3 is active (PL3 widens RS2's pool; RS2 installs the share).
WITHHELD_PACKAGES: tuple[str, ...] = (
    "workshop_payroll", "apprenticeship", "recovery_crews_granary", "recovery_crews_workshop",
    "repair_projects", "timber_supply",
)

#: Continuity of an opening with the previous closing.
CONTINUITY: tuple[str, ...] = ("exact", "broken", "unchecked")
#: Why a continuity check could not run.
UNCHECKED_REASONS: tuple[str, ...] = ("first_turn", "pool_reset", "gap", "no_closing", "no_opening")

#: Dated log kinds.
LOG_KINDS: tuple[str, ...] = (
    "switched_on", "switched_off", "pool_reset", "continuity_broken", "attribution", "unobserved",
)
MAX_LOG = 64
#: At most this many regions are named in a broken continuity record.
MAX_CONTINUITY_REGIONS = 16

#: Lifetime totals (declaration order; append only). ``*_milli`` are typed
#: flows in milli-units, ``native_model``/``delta``/``discontinuity`` wealth
#: units, ``withheld_*`` ordinary income withheld (wealth units),
#: ``treasury_*``/``tithe_*`` treasury units.
LIFETIME: tuple[str, ...] = (
    *(f"{name}_{side}_milli" for name in CHANNEL_NAMES for side in ("in", "out")),
    "delta", "native_model", "discontinuity",
    *(f"withheld_{name}" for name in WITHHELD_PACKAGES), "withheld_unattributed",
    "treasury_tax_created", "tithe_offered", "treasury_to_households_milli",
    "treasury_to_firm_cash_milli", "firm_cash_to_treasury_milli", "treasury_charged",
)

#: Lifetime counters (declaration order; append only).
COUNTERS: tuple[str, ...] = (
    "turns_observed", "turns_unobserved", "continuity_exact", "continuity_broken", "continuity_unchecked",
    "pool_resets", "switched_on", "switched_off", "withheld_rows", "unattributed_rows",
    "attribution_conflicts", "typed_incomplete_turns", "closures_failed",
)


def _is_none(value) -> bool:
    return value is None


class Closing(BaseModel):
    """The balance at the last observed closing (after every payer of a
    completed turn's Phase 10): a SHA-256 of ``(id, f32 wealth bits)`` and of
    ``(id, region)`` in ascending id order, the world total and agent count,
    and one sum and count per region index (``-1`` rows are not kept)."""

    turn: int
    digest: str
    region_digest: str
    total: float
    agents: int
    regions: list[float] = Field(default_factory=list)
    counts: list[int] = Field(default_factory=list)


class LedgerRecord(BaseModel):
    """A dated record: switches, pool resets, broken continuity, attribution."""

    turn: int
    kind: str                                   # LOG_KINDS
    detail: dict[str, Any] = Field(default_factory=dict)


class WealthAccountingState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    #: The last observed closing (None: none yet, or dropped by a pool reset
    #: or a switch-off: the next opening is then unchecked).
    closing: Closing | None = Field(default=None, exclude_if=_is_none)
    #: The turn a pool reset was seen (the next opening's reason).
    reset_turn: int | None = Field(default=None, exclude_if=_is_none)
    #: The completed-turn frame (JSON-ready; shape in
    #: ``docs/integration/wealth-accounting.md``). None: not observed.
    frame_turn: int | None = None
    frame: dict[str, Any] | None = None
    #: Lifetime totals (the fixed key set ``LIFETIME``).
    lifetime: dict[str, int | float] = Field(default_factory=dict)
    #: Rolling dated log (the last ``MAX_LOG`` records).
    log: list[LedgerRecord] = Field(default_factory=list)
    log_dropped: int = 0
    #: Scalar lifetime counters (the fixed key set ``COUNTERS``).
    counters: dict[str, int] = Field(default_factory=dict)
    # Transient, within one turn (Phase 2 opening -> Phase 10 closing): the
    # opening arrays and the counter baselines. Never serialized.
    _turn: object | None = PrivateAttr(default=None)

    def __getstate__(self):
        state = super().__getstate__()
        private = state.get("__pydantic_private__")
        if private and private.get("_turn") is not None:
            state = {**state, "__pydantic_private__": {**private, "_turn": None}}
        return state

    def __setstate__(self, state):
        super().__setstate__(state)
        for name, field in type(self).model_fields.items():
            if name not in self.__dict__:
                self.__dict__[name] = field.get_default(call_default_factory=True)
        if getattr(self, "__pydantic_private__", None) is None:
            object.__setattr__(self, "__pydantic_private__", {"_turn": None})
        else:
            self.__pydantic_private__.setdefault("_turn", None)
