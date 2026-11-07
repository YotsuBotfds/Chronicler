"""Persisted state of RS3 veteran reintegration (``--veteran-reintegration``, default off).

Owned by :mod:`chronicler.veteran_reintegration`. Pure data with no simulation imports, so
:mod:`chronicler.livelihoods_state` can import it.

Identities: ``agent_id`` is a native stable id; ``civ`` is the served
civilization's index in ``world.civilizations``; ``region`` and
``released_region`` are indices in ``world.regions``; ``army_id`` is the
campaign layer's persisted army id; a war is ``(war_key, war_start)``, the
civ pair key and the war record's start turn (``war_key`` alone is reused by
later wars of the same pair). ``record_id`` is a stable, never reused counter.

Everything is bounded: at most ``MAX_OPEN`` open records (captures beyond it
are counted, never stored), each with at most ``MAX_OUTCOMES`` dated outcomes
and ``MAX_SPELLS`` placement spells (older ones are dropped and counted),
``MAX_ARCHIVE`` closed records, ``MAX_PLACED_IDS`` ids for the unique-person
count and one completed-turn frame whose lists hold at most
``MAX_FRAME_ROWS`` rows each. Lifetime totals are scalar counters keyed by
``COUNTERS``. A world that never enabled the switch has no sub-state, so
feature-off output is unchanged.

``record_only`` is the control: veterans are captured and tracked
without priority.

Tuple orders below are declaration orders: append new values at the end,
never reorder.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

MAX_OPEN = 512
MAX_OUTCOMES = 24
MAX_SPELLS = 8
MAX_ARCHIVE = 64
MAX_PLACED_IDS = 4096
MAX_FRAME_ROWS = 128

#: Modes (first: the default when enabled).
MODES: tuple[str, ...] = ("priority", "record_only")
#: Dated outcome kinds of a veteran record (phase plan RS3), in declaration
#: order (append only). Other lanes report placements through
#: :func:`chronicler.veteran_reintegration.note_outcome`. ``pool_reset``
#: closes a record whose id belonged to a rebuilt native pool.
OUTCOMES: tuple[str, ...] = (
    "placed:crew", "placed:apprentice", "placed:repair", "waiting", "remobilised",
    "died", "migrated", "control_lost", "expired", "pool_reset",
)
#: Placement kinds (a subset of ``OUTCOMES``).
PLACEMENTS: tuple[str, ...] = ("placed:crew", "placed:apprentice", "placed:repair")
#: Outcomes that close a record (a subset of ``OUTCOMES``).
CLOSING: tuple[str, ...] = ("remobilised", "died", "expired", "pool_reset")
#: How a person left an army alive: ``desertion`` and ``scattered`` at
#: ``release_soldiers``; ``demobilised`` and ``destroyed`` at ``disband``
#: (people still on the roster when it is cleared); ``dissolved`` when the
#: campaign layer drops an army whose civilization is gone or whose region
#: vanished (``war/runtime.py``), its roster still alive.
CAUSES: tuple[str, ...] = ("desertion", "scattered", "demobilised", "destroyed", "dissolved", "wounded")
#: Why an open record is not eligible this turn.
INELIGIBLE_REASONS: tuple[str, ...] = ("control_lost", "minor", "unobserved")
#: Why an eligible (waiting) veteran had no placement this turn.
#: ``no_site``: no open workshop site in their region; ``site_idle``: a site
#: that did not operate (building, unfunded or worn), so no crew work;
#: ``not_crew_eligible``: the site operated but the person is not one of its
#: resident adult urban farmers; ``crew_full``: they are, and the crew cap was
#: filled ahead of them; ``unplaced``: none of these was observed (a trip,
#: other work, or a site Phase 2 did not plan).
UNMET_REASONS: tuple[str, ...] = ("no_site", "site_idle", "not_crew_eligible", "crew_full", "unplaced")

#: Lifetime counters (insertion order; the activation funnel reads them).
COUNTERS: tuple[str, ...] = (
    "captured", "captured_desertion", "captured_scattered", "captured_demobilised",
    "captured_destroyed", "captured_dissolved", "capture_duplicates", "capture_overflow", "captured_wounded",
    "captures_discarded",
    "offered", "would_offer",
    "placements", "placements_crew", "placements_apprentice", "placements_repair",
    "placement_turns", "placed_prioritised", "people_placed", "people_placed_unverified",
    "waiting_turns", "unmet_no_site", "unmet_site_idle", "unmet_not_crew_eligible",
    "unmet_crew_full", "unmet_unplaced",
    "migrations", "control_lost",
    "closed_remobilised", "closed_died", "closed_expired", "closed_pool_reset",
    "outcomes_dropped", "spells_dropped", "notes_discarded", "pool_resets", "captures_untrusted",
)

Detail = dict[str, int | float | str | bool | None]


class VeteranOutcome(BaseModel):
    turn: int
    kind: Literal["placed:crew", "placed:apprentice", "placed:repair", "waiting", "remobilised",
                  "died", "migrated", "control_lost", "expired", "pool_reset"]
    detail: Detail | None = None


class PlacementSpell(BaseModel):
    """Consecutive turns placed in one kind of opening at one site."""

    kind: Literal["placed:crew", "placed:apprentice", "placed:repair"]
    site: int | None = None
    region: int
    start_turn: int
    last_turn: int
    turns: int = 1
    #: Placed while ``priority`` mode put them first (False in the control).
    prioritised: bool = False


class VeteranRecord(BaseModel):
    record_id: int
    agent_id: int
    civ: int
    army_id: str
    war_key: str | None = None
    war_start: int | None = None
    cause: Literal["desertion", "scattered", "demobilised", "destroyed", "dissolved", "wounded"]
    released_turn: int
    released_region: int
    #: Last observed residence (post-tick snapshot) and age (None: unobserved).
    region: int
    age: int | None = None
    #: ``waiting``: eligible, not placed this turn; ``placed``: placed this
    #: turn (eligible or not); ``ineligible``: see ``reason``; ``closed``.
    status: Literal["waiting", "placed", "ineligible", "closed"] = "waiting"
    #: Why the record is not eligible (``INELIGIBLE_REASONS``), also while
    #: placed; None when eligible or closed.
    reason: str | None = None
    closed_turn: int | None = None
    closed_reason: str | None = None
    placements: int = 0
    placed_turns: int = 0
    spells: list[PlacementSpell] = Field(default_factory=list)
    outcomes: list[VeteranOutcome] = Field(default_factory=list)
    outcomes_dropped: int = 0


class CaptureRow(BaseModel):
    agent_id: int
    civ: int
    army_id: str
    war_key: str | None = None
    war_start: int | None = None
    cause: str
    region: int


class FramePlacement(BaseModel):
    agent_id: int
    kind: str
    region: int
    site: int | None = None
    prioritised: bool = False
    new_spell: bool = True


class FrameWaiting(BaseModel):
    agent_id: int
    region: int
    reason: str


class FrameOutcome(BaseModel):
    agent_id: int
    record_id: int
    kind: str
    detail: Detail | None = None


class VeteranFrame(BaseModel):
    """One completed turn: captures, offers, placements, waiting and outcomes.

    ``offered`` lists, per workshop site region, the eligible veterans in
    priority order: the list the crew planner received in ``priority`` mode,
    or the one it would have received in the ``record_only`` control
    (``priority_applied`` False); None when no Phase 2 was observed.
    """

    turn: int
    priority_applied: bool
    captured: list[CaptureRow] = Field(default_factory=list)
    captured_total: int = 0
    captured_by_cause: dict[str, int] = Field(default_factory=dict)
    offered: list[tuple[int, list[int]]] | None = None
    placed: list[FramePlacement] = Field(default_factory=list)
    waiting: list[FrameWaiting] = Field(default_factory=list)
    outcomes: list[FrameOutcome] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    rows_dropped: int = 0


class VeteranReintegrationState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["priority", "record_only"] = "priority"
    records: list[VeteranRecord] = Field(default_factory=list)
    archive: list[VeteranRecord] = Field(default_factory=list)
    next_record_id: int = 0
    #: Distinct people (stable ids of the current pool) placed at least once.
    ever_placed: list[int] = Field(default_factory=list)
    #: The last turn whose captures and outcomes were committed (exactly once).
    last_settled_turn: int | None = None
    #: The turn of a native pool rebuild that found enlisted rosters: those
    #: rosters named the old pool (kept or redrafted by ``rebind_rosters``), so
    #: releases from armies raised before it are not trusted as veterans.
    pool_reset_turn: int | None = None
    frame_turn: int | None = None
    frame: VeteranFrame | None = None
    #: Scalar lifetime counters (bounded: the ``COUNTERS`` key set).
    counters: dict[str, int] = Field(default_factory=dict)
    # Transient, within one turn (empty at every checkpoint boundary):
    # captures from the war phase, this turn's Phase 2 offers and crew facts,
    # and outcomes reported by other packages. Committed once in Phase 10.
    _captures: list = PrivateAttr(default_factory=list)
    _phase2: object | None = PrivateAttr(default=None)
    _noted: list = PrivateAttr(default_factory=list)
    # Transient: (turn, frame outcome rows) of a pool reset at this turn's first
    # hook, carried into the frame Phase 10 builds.
    _carry: tuple | None = PrivateAttr(default=None)

    def __setstate__(self, state):
        super().__setstate__(state)
        # Exact pickle restoration bypasses Pydantic defaults: a pickle of the
        # RS0 stub holds only the switch, its mode and counters.
        for name, field in type(self).model_fields.items():
            if name not in self.__dict__:
                self.__dict__[name] = field.get_default(call_default_factory=True)
        private = getattr(self, "__pydantic_private__", None)
        if private is None:
            private = {}
            object.__setattr__(self, "__pydantic_private__", private)
        private.setdefault("_captures", [])
        private.setdefault("_phase2", None)
        private.setdefault("_noted", [])
        private.setdefault("_carry", None)
