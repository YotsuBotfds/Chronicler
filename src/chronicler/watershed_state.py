"""Persisted state of the watershed account (``--watershed``, default off).

Owned by :mod:`chronicler.watershed`; pure data. One drainage graph built at
enable from the world's saved procedural geography (each region's single
destination: a region index, the sea or a sink), the storage of every region
in water units, the water index observed after the last settled Phase 9, the
running drought spells and flood events, the last settled turn's frame
(per-region account, floods that started, flood events and droughts that
ended, terrain cap changes, totals) and cumulative totals and counters. A
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
#: Counters of the B2 record, both modes (flood events; added to a B1 account when it settles).
EVENT_COUNTER_KEYS: tuple[str, ...] = ("floods_started", "floods_ended", "terrain_cap_changes")
#: Counters of ``flow`` mode only (added when the account opens in flow mode).
FLOW_COUNTER_KEYS: tuple[str, ...] = (
    "flood_consequences", "flood_consequences_withheld", "superseded_river_floods",
)


def _empty(value) -> bool:
    return not value


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


class FloodConsequence(BaseModel):
    """What a flood did in ``flow`` mode, through the existing fields (applied
    before the Phase 9 sync): the capacity modifier it set (never raising a
    lower one), the ``disaster_cooldowns["flood"]`` it set (never shortening a
    longer one) and the silt it added to the soil (capped at the terrain's)."""
    model_config = ConfigDict(extra="forbid")

    capacity_modifier: float = Field(gt=0.0, le=1.0)
    cooldown: int = Field(ge=1)
    soil_before: float = _amount()
    soil_after: float = _amount()


class SupersededFlood(BaseModel):
    """A river flood ``emergence._check_flood`` drew in ``flow`` mode: its draws
    were kept (the shared environment stream does not shift) and its effect
    suppressed, superseded by the account's own floods."""
    model_config = ConfigDict(extra="forbid")

    turn: int = Field(ge=0)
    region: int = Field(ge=0)
    duration: int = Field(ge=1)


class FloodRecord(BaseModel):
    """The onset of a flood event: the first settled turn whose arrivals exceed
    the region's channel capacity while no event is open there, with the
    conditions that caused it. ``arrivals = precipitation + inflow`` (B2; a
    B1 record also counted ``external_in``); ``excess = arrivals - channel``.
    ``tributaries`` lists each region draining directly into this one with
    the outflow it sent this turn; ``upstream_cover`` is the mean forest cover
    of every region upstream (None for a headwater region) and
    ``upstream_deforested`` how many of them are below the deforestation
    threshold."""
    model_config = ConfigDict(extra="forbid")

    turn: int = Field(ge=0)
    region: int = Field(ge=0)
    excess: float = _amount()
    arrivals: float = _amount()
    channel: float = _amount()
    precipitation: float = _amount()
    inflow: float = _amount()
    #: B1 only (B1 arrivals included the external inflow); None in B2.
    external_in: float | None = Field(default=None, ge=0.0, allow_inf_nan=False, exclude_if=lambda v: v is None)
    storage_open: float = _amount()
    capacity: float = _amount()
    tributaries: list[tuple[int, float]] = Field(default_factory=list)
    upstream_cover: float | None = None
    upstream_deforested: int = Field(default=0, ge=0)
    #: ``flow`` mode only: what the flood did (absent in ``record_only``), or
    #: None when it was withheld (``withheld_by``).
    consequence: FloodConsequence | None = Field(default=None, exclude_if=lambda v: v is None)
    #: ``flow`` mode only: the disaster cooldowns the region held at onset, for
    #: which the consequence was withheld (as the old river flood skipped a
    #: region with any cooldown); empty when it acted.
    withheld_by: list[str] = Field(default_factory=list, exclude_if=_empty)

    def __setstate__(self, state):
        super().__setstate__(state)
        self.__dict__.setdefault("consequence", None)          # a B1 checkpoint
        self.__dict__.setdefault("withheld_by", [])


class FloodEvent(BaseModel):
    """A flood event: it starts when arrivals cross the channel capacity from
    below and stays open while they exceed the recession threshold
    (``flood_recession`` x channel, hysteresis); ``turns`` counts its settled
    turns, ``peak_excess`` its largest excess above the channel."""
    model_config = ConfigDict(extra="forbid")

    region: int = Field(ge=0)
    start_turn: int = Field(ge=0)
    turns: int = Field(ge=1)
    peak_excess: float = _amount()
    end_turn: int | None = None


class ActiveConsequence(BaseModel):
    """``flow``: a flood consequence whose capacity modifier the account ends
    itself when its cooldown expires, if another disaster's cooldown would
    otherwise hold it (``simulation`` restores the modifier only when every
    cooldown is gone)."""
    model_config = ConfigDict(extra="forbid")

    region: int = Field(ge=0)
    expires_turn: int = Field(ge=0)
    modifier: float = Field(gt=0.0, le=1.0)
    before: float = Field(gt=0.0, le=1.0)


class CapChange(BaseModel):
    """A terrain transition in this turn's Phase 9 post-pass changed the
    region's water-index cap (``emergence.tick_terrain_succession``, which
    clamps the index to the new cap). In ``flow`` the index the simulation
    used is then ``min(index_derived, cap_after)``: ``index_out`` is the
    index the clamp removed, an attributed outflow of the index, not of
    storage (the next turn derives the index from the same storage under the
    new cap)."""
    model_config = ConfigDict(extra="forbid")

    region: int = Field(ge=0)
    source: Literal["terrain_cap_change"] = "terrain_cap_change"
    terrain_before: str
    terrain_after: str
    cap_before: float = _amount()
    cap_after: float = _amount()
    index_out: float | None = Field(default=None, ge=0.0, allow_inf_nan=False, exclude_if=lambda v: v is None)


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
    #: Flood events that started this turn (their onset records).
    floods: list[FloodRecord] = Field(default_factory=list)
    #: Flood events that ended this turn (B2).
    floods_ended: list[FloodEvent] = Field(default_factory=list, exclude_if=_empty)
    droughts_ended: list[DroughtSpell] = Field(default_factory=list)
    #: External flows by source (non-zero entries only).
    external: list[ExternalFlow] = Field(default_factory=list)
    #: The baseline index was not observed after the previous turn's tick (a
    #: dropped plan or a missing turn): this turn's external flows include
    #: unsettled index changes and are all unattributed. ``flow`` mode must
    #: refuse or reconcile such a turn.
    stale_baseline: bool = False
    #: ``flow`` mode only: river floods superseded in this turn.
    superseded: list[SupersededFlood] = Field(default_factory=list, exclude_if=_empty)
    #: Terrain cap changes of this turn's post-pass (B2).
    cap_changes: list[CapChange] = Field(default_factory=list, exclude_if=_empty)
    totals: dict[str, float]
    storage_open: float = _amount()
    storage_close: float = _amount()
    #: ``storage_close - storage_open`` minus the net of the flows (water units).
    closure_residual: float = Field(allow_inf_nan=False)

    def __setstate__(self, state):
        super().__setstate__(state)
        self.__dict__.setdefault("superseded", [])             # a B1 checkpoint
        self.__dict__.setdefault("floods_ended", [])
        self.__dict__.setdefault("cap_changes", [])


class WatershedState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["record_only", "flow"] = "record_only"
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
    #: Open flood events, by region (B2).
    flood_events: list[FloodEvent] = Field(default_factory=list, exclude_if=_empty)
    #: ``flow``: flood consequences whose capacity modifier is still to end.
    active_consequences: list[ActiveConsequence] = Field(default_factory=list, exclude_if=_empty)
    frame: WatershedFrame | None = None
    cumulative: dict[str, float] = Field(default_factory=lambda: {key: 0.0 for key in FLOW_KEYS})
    counters: dict[str, int] = Field(default_factory=lambda: {key: 0 for key in COUNTER_KEYS})
    #: ``flow`` mode: river floods superseded since this turn's Phase 1, moved
    #: into the frame when the turn settles (empty between turns).
    pending_superseded: list[SupersededFlood] = Field(default_factory=list, exclude_if=_empty)
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
        # A B1 (record_only) checkpoint predates the flow and B2 fields.
        self.__dict__.setdefault("pending_superseded", [])
        self.__dict__.setdefault("flood_events", [])
        self.__dict__.setdefault("active_consequences", [])
        private = getattr(self, "__pydantic_private__", None)
        if private is None:
            object.__setattr__(self, "__pydantic_private__", {"_plan": None})
        else:
            private.setdefault("_plan", None)
