"""Persisted state of bounded epidemic care capacity (connected-world C2, default off).

Owned by :mod:`chronicler.epidemic_care`. Pure data, importable by
:mod:`chronicler.livelihoods_state` (a world that never enabled
``--epidemic-care`` has no sub-state, so feature-off output is unchanged).

Identities: ``region`` is an index in ``world.regions``; ``civ`` an index in
``world.civilizations``; carers are native stable ids (``agent_id``); an L9
commitment is its ``cid``. No identifier is invented.

Dates: a :class:`CareCapacity` row is written in Phase 2 of turn T
(``source_turn`` T) and read by the epidemic tick of T + 1 only; the tick
consumes it (applied or refused, never twice). The tick's record
(``applied``/``refused``, dated ``tick_turn``) and the Phase 2 frame
(``frame``/``ledger``, dated ``frame_turn``) keep only the last turn: never
a lifetime copy. Tuple orders below are declaration orders (append only).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

from chronicler.money import MoneyBook

#: ``--epidemic-care-mode`` values (first: the default when enabled).
MODES: tuple[str, ...] = ("care", "cost_only")
#: Why a capacity row did not apply at a tick (append only). ``out_of_range``:
#: dated right but naming no region of the world.
CAPACITY_REFUSALS: tuple[str, ...] = ("stale", "future", "out_of_range")
#: What limited a region's carers in Phase 2 (append only). ``need_met``: the
#: carers cover the infectious people; ``envelope``: the L9 envelope's wages;
#: ``treasury``: the payer's projected treasury; ``labour``: no more eligible
#: adult farmers; ``no_patients``: nobody infectious at the last tick;
#: ``recipient_lost``: the region left the envelope's civilization.
LIMITS: tuple[str, ...] = ("need_met", "envelope", "treasury", "labour", "no_patients", "recipient_lost")
#: Origins of a carer (append only).
ORIGINS: tuple[str, ...] = ("rural_farmer", "urban_farmer")
#: Lifetime counters (fixed key set, declaration order; append only).
COUNTERS: tuple[str, ...] = (
    "ticks_observed", "covered_region_turns", "capacity_applied", "capacity_stale", "capacity_future",
    "frames", "envelopes", "carer_turns", "care_time", "patients", "farm_time_removed",
    "wages_due_milli", "wages_paid_milli", "wage_residual_milli", "treasury_units", "unpaid_bills",
    "income_withheld", "pool_resets", "turns_discarded",
    *(f"limit_{name}" for name in LIMITS),
    # Review of 3e5ee44d (appended): coins of the care envelopes C2 executed;
    # farm time given by carers of a civ whose wage bill was refused at payment
    # (no wage, no income withheld, no capacity); capacity rows dated wrongly
    # because their region is out of range; rows a settlement found unconsumed.
    "envelope_coins", "farm_time_unpaid", "capacity_out_of_range", "capacity_unconsumed",
)
#: Settled rows kept in one frame (bounded).
MAX_FRAME_ROWS = 256


def _is_none(value) -> bool:
    return value is None


class CareCapacity(BaseModel):
    """Patients the carers named in Phase 2 of ``source_turn`` can serve at
    the next epidemic tick (``source_turn + 1``)."""

    region: int
    source_turn: int
    carers: int
    care_time: float          # worker-turns of care (each carer's farm time given)
    patients: float           # care_time x PATIENTS_PER_CARER


class CapacityRefusal(BaseModel):
    """A capacity row the tick ignored, with the reason (``CAPACITY_REFUSALS``)."""

    region: int
    source_turn: int
    reason: str


class TickRegion(BaseModel):
    """One region at one epidemic tick, after the tick (every region with an
    infection row or deaths): its epidemic deaths, the infectious person-turns
    the tick spent (sum over pathogens of the tick's mean infectious share x
    population, ``burden x n``) and its new infections. Recorded in every
    care arm, covered or not, so a region-turn can be read the same way in
    ``care`` and ``cost_only``."""

    region: int
    deaths: int
    infectious_pt: float
    cases: float
    #: The same by pathogen index (``epidemiology.PATHOGENS``), every pathogen with a
    #: row or deaths there: ``(pathogen, deaths, infectious person-turns)``.
    pathogens: list[tuple[int, int, float]] = Field(default_factory=list)


class CareApplied(BaseModel):
    """One region at one epidemic tick (``tick_turn``) with capacity applying."""

    region: int
    source_turn: int
    patients: float
    #: Infectious people at the last tick: sum over pathogens of burden x n.
    infectious: float
    coverage: float           # min(1, patients / infectious); 0 without infectious people
    #: The care factor this tick applied: 1 - CARE_CFR_REDUCTION x coverage in
    #: ``care``, 1.0 in ``cost_only`` (which records ``would_be`` instead).
    care_factor: float
    would_be: float
    #: Practised medicine's factor (None: techniques off) and the combined
    #: factor after the one floor (``techniques.CFR_FLOOR``).
    techniques_factor: float | None = None
    combined_factor: float
    floored: bool = False
    #: Filled after the tick (Phase 2 of the same turn): the region's epidemic
    #: deaths and new infections in this tick, and its infectious people after
    #: it. None: not observed.
    deaths: int | None = None
    cases: float | None = None
    infectious_after: float | None = None


class Carer(BaseModel):
    agent_id: int
    origin: str               # ORIGINS
    share: float              # care time = farm time removed = income share withheld
    wage_due_milli: int
    wage_paid_milli: int = 0
    wage_residual_milli: int = 0
    #: The ordinary income the next wealth phase withheld (paid-work receipt);
    #: None until read.
    income_withheld: float | None = None


class CareReceipt(BaseModel):
    """One region's carers for one turn, within one L9 envelope."""

    turn: int
    region: int
    civ: int
    commitment: int           # the L9 commitment's cid
    envelope: int             # coins promised
    infectious: float         # at the tick of this turn (burden x n)
    need: float               # care time the infectious people need (infectious / PATIENTS_PER_CARER)
    eligible: int             # eligible adult farmers (not booked elsewhere this turn)
    carers: list[Carer] = Field(default_factory=list)
    care_time: float = 0.0
    patients: float = 0.0
    wages_due_milli: int = 0
    wages_paid_milli: int = 0
    wage_residual_milli: int = 0
    farm_time_removed: float = 0.0
    limit: str = "need_met"   # LIMITS
    paid: bool = False        # the civ's wage bill settled (False: refused or nothing due)
    #: The payment seam's refusal of the civ's bill at payment (``payer_short``,
    #: ...): its carers were neither paid nor withheld and gave no capacity.
    unpaid_reason: str | None = None


class CivWageLedger(BaseModel):
    """One paying civilization's wage bill of one turn (one keyed money bill).
    Closure: ``treasury_units x 1000 + carry_before == paid + carry_after``."""

    turn: int
    civ: int
    #: Coins of the civ's care envelopes executed this turn (L9's award).
    envelope_coins: int = 0
    due_milli: int
    paid_milli: int = 0
    residual_milli: int = 0
    treasury_units: int = 0
    carry_before: int = 0
    carry_after: int = 0
    status: str = "paid"      # "paid", "nothing_due" (an envelope, no wage due) or "refused:<reason>"


class EpidemicCareState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["care", "cost_only"] = "care"
    #: Dated capacity for the next tick (written in Phase 2, consumed by the tick).
    capacity: list[CareCapacity] = Field(default_factory=list)
    #: The last tick's record (``tick_turn``; None: no tick observed yet).
    tick_turn: int | None = None
    applied: list[CareApplied] = Field(default_factory=list)
    refused: list[CapacityRefusal] = Field(default_factory=list)
    #: Every region of that tick, after it (filled in Phase 2 of the same turn).
    regions: list[TickRegion] = Field(default_factory=list)
    #: The last Phase 2 frame (``frame_turn``); None rows: not settled.
    frame_turn: int | None = None
    frame: list[CareReceipt] | None = Field(default=None, exclude_if=_is_none)
    ledger: list[CivWageLedger] | None = Field(default=None, exclude_if=_is_none)
    rows_dropped: int = 0
    #: The payment seam's book (exactly once per (turn, purpose, batch), the
    #: payers' sub-unit carry, the last settled turn's flows).
    book: MoneyBook = Field(default_factory=MoneyBook)
    counters: dict[str, float] = Field(default_factory=dict)
    # Transient, within one turn (Phase 2 plan -> finish -> after the tick).
    # Never serialized.
    _turn: object | None = PrivateAttr(default=None)

    def __getstate__(self):
        state = super().__getstate__()
        private = state.get("__pydantic_private__")
        if private and private.get("_turn") is not None:
            state = {**state, "__pydantic_private__": {**private, "_turn": None}}
        return state

    def __setstate__(self, state):
        super().__setstate__(state)
        private = getattr(self, "__pydantic_private__", None)
        if private is None:
            object.__setattr__(self, "__pydantic_private__", {"_turn": None})
        else:
            private.setdefault("_turn", None)
