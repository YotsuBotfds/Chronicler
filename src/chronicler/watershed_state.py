"""Persisted state of the watershed account (``--watershed``, default off).

Owned by :mod:`chronicler.watershed`; pure data. One drainage graph built at
enable from the world's saved procedural geography (each region's single
destination: a region index, the sea or a sink), the storage of every region
in water units, the water index observed after the last settled Phase 9, the
running drought spells, the last settled turn's frame (per-region account,
floods, droughts that ended, totals) and cumulative totals and counters. A
region is its index in ``world.regions``. See docs/integration/watershed.md.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

#: Destination codes in ``WatershedGraph.down`` besides a region index:
#: the sea (a shore on an ocean or sea), a sink (an inland region with no
#: lower land neighbour) and a lake (a shore on lakes only: closed water).
SEA = -1
SINK = -2
LAKE = -3

#: Per-region columns of a settled frame, in record order (water units unless
#: noted). ``storage_open + precipitation + external_in - external_out +
#: inflow - evaporation - withdrawal - outflow == storage`` for every region.
FRAME_COLUMNS: tuple[str, ...] = (
    "storage_open", "precipitation", "external_in", "external_out", "inflow", "evaporation",
    "withdrawal", "outflow", "storage", "capacity", "index_observed", "index_derived",
    "flood_excess",
)
#: The account's flows (totals of a frame and cumulative totals since opening).
FLOW_KEYS: tuple[str, ...] = (
    "precipitation", "external_in", "external_out", "evaporation", "withdrawal", "to_sea",
    "to_sink", "to_lake", "transfer",
)
#: Known writers of the water index outside Phase 9 an external flow is
#: attributed to; anything else (or a stale baseline) is ``unattributed``.
EXTERNAL_SOURCES: tuple[str, ...] = ("coastal_flood", "unattributed")
#: Cumulative counters, in report order (all start at zero).
COUNTER_KEYS: tuple[str, ...] = (
    "planned_turns", "settled_turns", "abandoned_plans", "flood_region_turns",
    "drought_region_turns", "droughts_declared", "droughts_ended", "external_out_unmet_turns",
    "stale_baseline_turns",
)


def _amount():
    return Field(ge=0.0, allow_inf_nan=False)


class WatershedGraph(BaseModel):
    """The drainage graph, fixed at enable."""
    model_config = ConfigDict(extra="forbid")

    #: Per region: the region index it drains to, ``SEA`` (-1) or ``SINK`` (-2).
    down: list[int]
    #: Every region once, each after all regions that drain into it
    #: (elevation descending, then index).
    order: list[int]
    #: Persisted river steps the graph reproduces (all of them, or enable fails).
    river_steps: int = Field(ge=0)


class ExternalFlow(BaseModel):
    """One region's external inflow or outflow of a settled turn, by source:
    ``coastal_flood`` (``climate.check_disasters`` raised the index in Phase 1
    of this turn; at most its nominal gain is attributed to it) or
    ``unattributed`` (any other writer, or the remainder)."""
    model_config = ConfigDict(extra="forbid")

    region: int = Field(ge=0)
    direction: Literal["in", "out"]
    source: Literal["coastal_flood", "unattributed"]
    amount: float = Field(gt=0.0, allow_inf_nan=False)


class FloodRecord(BaseModel):
    """Arrivals above a region's channel capacity in one settled turn, with the
    conditions that caused them. ``arrivals = precipitation + inflow +
    external_in``; ``excess = arrivals - channel``. ``tributaries`` lists each
    region draining directly into this one with the outflow it sent this
    turn; ``upstream_cover`` is the mean forest cover of every region upstream
    (None for a headwater region) and ``upstream_deforested`` how many of them
    are below the deforestation threshold."""
    model_config = ConfigDict(extra="forbid")

    turn: int = Field(ge=0)
    region: int = Field(ge=0)
    excess: float = _amount()
    arrivals: float = _amount()
    channel: float = _amount()
    precipitation: float = _amount()
    inflow: float = _amount()
    external_in: float = _amount()
    storage_open: float = _amount()
    capacity: float = _amount()
    tributaries: list[tuple[int, float]] = Field(default_factory=list)
    upstream_cover: float | None = None
    upstream_deforested: int = Field(default=0, ge=0)


class DroughtSpell(BaseModel):
    """A run of consecutive settled turns with storage below the drought
    fraction of capacity, and what the region received and lost during it.
    It is a drought once ``turns`` reaches the declared length
    (``declared_turn``); runs that end earlier are not recorded.
    ``normal_precipitation`` is the precipitation the region would have had
    at the phase factor 1 and no harvest shock; the gap to ``precipitation``
    is the forcing deficit. ``upstream_withdrawal`` is the irrigation
    withdrawn by every region upstream over the run."""
    model_config = ConfigDict(extra="forbid")

    region: int = Field(ge=0)
    start_turn: int = Field(ge=0)
    turns: int = Field(ge=1)
    declared_turn: int | None = None
    end_turn: int | None = None
    min_fraction: float = _amount()
    precipitation: float = _amount()
    normal_precipitation: float = _amount()
    inflow: float = _amount()
    evaporation: float = _amount()
    withdrawal: float = _amount()
    upstream_withdrawal: float = _amount()
    upstream_cover: float | None = None


class WatershedFrame(BaseModel):
    """The account of one settled turn (full precision)."""
    model_config = ConfigDict(extra="forbid")

    turn: int = Field(ge=0)
    phase: str
    columns: dict[str, list[float]]
    #: Consecutive settled turns each region's storage has been below the
    #: drought fraction (0 when it is not).
    drought_turns: list[int]
    floods: list[FloodRecord] = Field(default_factory=list)
    droughts_ended: list[DroughtSpell] = Field(default_factory=list)
    #: External flows by source (non-zero entries only).
    external: list[ExternalFlow] = Field(default_factory=list)
    #: The baseline index was not observed after the previous turn's tick (a
    #: dropped plan or a missing turn): this turn's external flows include
    #: unsettled index changes and are all unattributed. ``flow`` mode must
    #: refuse or reconcile such a turn.
    stale_baseline: bool = False
    totals: dict[str, float]
    storage_open: float = _amount()
    storage_close: float = _amount()
    #: ``storage_close - storage_open`` minus the net of the flows (water units).
    closure_residual: float = Field(allow_inf_nan=False)


class WatershedState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["record_only"] = "record_only"
    opened_turn: int = Field(ge=0)
    graph: WatershedGraph
    #: Water units per region after the last settled turn (or at opening).
    storage: list[float]
    #: The water index observed after the last settled Phase 9 (at opening:
    #: the index the account opened from); the next turn's change before its
    #: Phase 9 is the external inflow or outflow (e.g. a coastal flood).
    last_index: list[float]
    opening_storage: float = _amount()
    #: Running below-threshold runs and declared droughts, by region.
    spells: list[DroughtSpell] = Field(default_factory=list)
    frame: WatershedFrame | None = None
    cumulative: dict[str, float] = Field(default_factory=lambda: {key: 0.0 for key in FLOW_KEYS})
    counters: dict[str, int] = Field(default_factory=lambda: {key: 0 for key in COUNTER_KEYS})
    # Transient, within one Phase 9 only: the account computed before the
    # ecology tick, committed after it. A plan left by a failed tick is
    # dropped at the next planning (nothing was settled). Never serialized.
    _plan: object | None = PrivateAttr(default=None)

    def __getstate__(self):
        state = super().__getstate__()
        private = state.get("__pydantic_private__")
        if private and private.get("_plan") is not None:
            state = {**state, "__pydantic_private__": {**private, "_plan": None}}
        return state

    def __setstate__(self, state):
        super().__setstate__(state)
        private = getattr(self, "__pydantic_private__", None)
        if private is None:
            object.__setattr__(self, "__pydantic_private__", {"_plan": None})
        else:
            private.setdefault("_plan", None)
