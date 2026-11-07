"""Persisted state of the residence ledger (X1, ``--residence-ledger``, default off).

Owned by :mod:`chronicler.residence_ledger` (the lead-owned displacement
contract, ``docs/integration/residence-ledger.md``). Pure data with no
simulation imports, so :mod:`chronicler.livelihoods_state` can import it. A
world that never enabled the switch has no sub-state, so feature-off output is
unchanged.

Identities: people are native stable agent ids; regions are indices in
``world.regions``; armies are their ``army_id``. Everything is bounded: one row
per observed living person (at most ``MAX_ROWS``), one watch row per region,
the completed turn's frame and its spell events (at most ``MAX_EVENTS``), a
rolling dated log (``MAX_LOG``) and lifetime counters with the fixed key set
``COUNTERS``. Tuple orders below are declaration orders: append new values at
the end, never reorder (``CAUSES`` will take D3's ``evacuated``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

#: Declared, uncalibrated constants (audit A6 section 11.1).
#: A displacement spell resettles after this many turns at one residence.
REHOME_TURNS = 20
#: A departure is anchored to a home-region event dated in this many turns before it.
ANCHOR_TURNS = 5

#: Displacement causes (a spell's ``cause``): the driver group of the move that
#: opened it (``quarantine_rules.FLIGHT_DRIVERS`` / ``HUNGER_DRIVERS``).
CAUSES: tuple[str, ...] = ("flight", "hunger")
#: Home-region event kinds a departure can be anchored to, in priority order (the
#: first present is the spell's ``anchor``; every present kind is kept in
#: ``anchor_kinds``). Append only.
EVENT_KINDS: tuple[str, ...] = ("war", "famine", "persecution")
#: A spell's ``anchor``: an event kind, or ``none`` when no event is dated in the
#: window. Append only: a new event kind is appended here after ``none`` (and to
#: ``EVENT_KINDS``), never inserted.
ANCHORS: tuple[str, ...] = ("war", "famine", "persecution", "none")
#: Every applied move's driver group: the two causes, the voluntary drivers
#: (``models.VOLUNTARY_MIGRATION_DRIVERS``) and every other or missing driver.
MOVE_GROUPS: tuple[str, ...] = ("flight", "hunger", "voluntary", "other")
#: How a spell closes.
CLOSURES: tuple[str, ...] = ("returned", "resettled", "died", "pool_reset", "unobserved_gap")
#: Causes of a separation (computed on demand, never stored), in priority order.
SEPARATION_CAUSES: tuple[str, ...] = ("trip", "attached", "displaced", "migrated")

#: Keys of a frame region row (declaration order; append only).
REGION_KEYS: tuple[str, ...] = (
    "region", "residents",
    "displaced", "displaced_flight", "displaced_hunger",
    "displaced_war", "displaced_famine", "displaced_persecution", "displaced_none",
    "displaced_from",
    "arrivals", "arrivals_displaced",
    "departures", "departures_flight", "departures_hunger", "departures_voluntary", "departures_other",
    "opened", "returned", "resettled", "died_displaced", "deaths",
    "attached", "attached_away", "in_transit",
    # Review M1 (appended): arrivals and departures by cause and anchor (audit 11.3).
    *(f"opened_{cause}" for cause in CAUSES),
    *(f"opened_{anchor}" for anchor in ANCHORS),
    *(f"returned_{anchor}" for anchor in ANCHORS),
    *(f"displaced_from_{anchor}" for anchor in ANCHORS),
    *(f"arrivals_{group}" for group in MOVE_GROUPS),
    *(f"arrivals_displaced_{anchor}" for anchor in ANCHORS),
)
#: Keys of a frame's world totals (declaration order; append only).
TOTAL_KEYS: tuple[str, ...] = (
    "alive", "observed", "deferred",
    "displaced", "displaced_flight", "displaced_hunger",
    "displaced_war", "displaced_famine", "displaced_persecution", "displaced_none",
    "anchor_any_war", "anchor_any_famine", "anchor_any_persecution", "anchor_war_or_famine", "anchor_partial",
    "moves", "moves_flight", "moves_hunger", "moves_voluntary", "moves_other",
    "opened", "returned", "resettled", "died", "pool_reset", "unobserved_gap", "rehomed", "deaths",
    "attached", "attached_away", "in_transit",
    "new_rows", "newborn_rows", "trip_relocations", "unexplained_relocations", "move_origin_mismatches",
    # Record-only comparisons with the measures the contract replaces (audit section 10).
    "recent_movers_native", "away_from_birth_region",
    # Review M1 and nits (appended).
    *(f"opened_{cause}" for cause in CAUSES),
    *(f"opened_{anchor}" for anchor in ANCHORS),
    *(f"returned_{anchor}" for anchor in ANCHORS),
    *(f"displaced_from_{anchor}" for anchor in ANCHORS),
    *(f"arrivals_{group}" for group in MOVE_GROUPS),
    *(f"arrivals_displaced_{anchor}" for anchor in ANCHORS),
    "invalid_moves",
)
#: Lifetime counters (declaration order; append only).
COUNTERS: tuple[str, ...] = (
    "turns_observed", "turns_unobserved", "switched_on", "switched_off", "pool_resets", "gaps",
    "moves_seen", "rehomed", "rows_refused", "events_dropped", "trip_relocations", "unexplained_relocations",
    "move_origin_mismatches",
    *(f"opened_{cause}" for cause in CAUSES),
    *(f"opened_{anchor}" for anchor in ANCHORS),
    *(f"closed_{reason}" for reason in CLOSURES),
    # Review nit (appended): native moves naming an invalid route, counted and skipped.
    "invalid_moves",
)
#: Dated log kinds.
LOG_KINDS: tuple[str, ...] = ("switched_on", "switched_off", "pool_reset", "gap", "unobserved", "rows_refused")
MAX_LOG = 64
#: At most this many spell events (openings and closures) are kept per frame.
MAX_EVENTS = 512
#: At most this many person rows (living observed people) are kept.
MAX_ROWS = 262_144


def _is_none(value) -> bool:
    return value is None


@dataclass(slots=True)
class Spell:
    """An open displacement spell (one per person at most). A slotted record:
    person-level state lives only in exact checkpoints (review m2: cheap to
    hold and update at scale)."""

    start: int                          # the turn of the move that opened it
    origin: int                         # home when it opened (region index)
    cause: str                          # CAUSES
    anchor: str                         # ANCHORS (the first kind present, else "none")
    anchor_kinds: list[str] = field(default_factory=list)   # every EVENT_KINDS kind dated in the window
    anchor_partial: bool = False        # the window reaches before the ledger watched the regions
    moves: int = 1                      # moves while displaced, the opening one included
    #: The opening move's native driver code (``models.MIGRATION_DRIVER_NAMES``),
    #: kept across onward moves (review M2).
    driver: int | None = None


@dataclass(slots=True)
class ResidenceRow:
    """One observed living person, keyed by stable id in ``ResidenceLedgerState.rows``."""

    home: int                           # region index
    home_since: int                     # the turn home was set (first observation: when first seen)
    res: int                            # residence: the native region after the tick (a traveller keeps it)
    res_since: int                      # the turn the person arrived at this residence (or was first seen)
    first_seen: int
    move_turn: int | None = None        # the last applied move
    move_from: int | None = None
    move_driver: int | None = None      # native code (None: no driver)
    spell: Spell | None = None
    army: str | None = None             # attachment after reconcile_rosters
    army_region: int | None = None


class RegionWatch(BaseModel):
    """What the ledger last read of one region, and the last turn of each event kind."""

    controller: str | None = None
    controller_seen: bool = False
    war: int | None = None
    famine: int | None = None
    persecution: int | None = None


class LogRecord(BaseModel):
    turn: int
    kind: str                            # LOG_KINDS
    detail: dict[str, Any] = Field(default_factory=dict)


class ResidenceLedgerState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    #: The first turn of the current observation epoch (None: nothing observed
    #: since the switch was turned on, the pool was rebuilt or a gap). History
    #: before it is unknown, not zero.
    observed_from: int | None = None
    #: The first turn the regions were watched in this epoch (anchor windows
    #: reaching before it are partial).
    watch_from: int | None = None
    #: The last observed turn.
    last_turn: int | None = None
    #: The completed turn's frame (aggregates) and spell events. None: not observed.
    #: The frame and events are in every snapshot record, so JSON output leaves
    #: them out (review nit); exact checkpoints keep them.
    frame_turn: int | None = None
    frame: dict[str, Any] | None = Field(default=None, exclude=True)
    events: list[dict[str, Any]] | None = Field(default=None, exclude=True)
    events_dropped: int = 0
    #: Per-person state (``exclude=True``): kept in exact checkpoints (the
    #: pickled world), left out of JSON output (the bundle's world state and the
    #: state file), which only a legacy resume reads back, and a legacy resume
    #: rebuilds the pool, which closes every spell anyway (``rows_held``,
    #: ``open_spells_held`` report what it held).
    #: Observed living people by stable id (ascending).
    rows: dict[int, ResidenceRow] = Field(default_factory=dict, exclude=True)
    #: Travellers alive when first seen, waiting for the end of their trip (ascending ids).
    deferred: list[int] = Field(default_factory=list, exclude=True)
    #: People on a native trip at the last write (ascending ids): a trip that
    #: ends away from the residence (a native unwind leaves the traveller where
    #: it was) is recognised as such at the next write.
    travelling: list[int] = Field(default_factory=list, exclude=True)
    #: People on an army roster at the last write (ascending ids): the next
    #: write clears only their attachment (review m2).
    attached: list[int] = Field(default_factory=list, exclude=True)
    #: The number of person rows and open spells held after the last write (in JSON too).
    rows_held: int = 0
    open_spells_held: int = 0
    #: One watch row per region (list index = region index).
    regions: list[RegionWatch] = Field(default_factory=list)
    #: Closures taken outside the writer in this turn (a pool reset in Phase 2),
    #: reported in this turn's frame; None outside a turn that had one.
    pending: dict[str, Any] | None = Field(default=None, exclude_if=_is_none)
    #: Lifetime counters (the fixed key set ``COUNTERS``).
    counters: dict[str, int] = Field(default_factory=dict)
    #: Rolling dated log (the last ``MAX_LOG`` records).
    log: list[LogRecord] = Field(default_factory=list)
    log_dropped: int = 0

    def __setstate__(self, state):
        # Exact pickle restoration bypasses Pydantic defaults: fields appended
        # later take their defaults.
        super().__setstate__(state)
        for name, field in type(self).model_fields.items():
            if name not in self.__dict__:
                self.__dict__[name] = field.get_default(call_default_factory=True)
