"""Persisted maritime state (see :mod:`chronicler.maritime`).

Pure data with no simulation imports, so :mod:`chronicler.models` can import
it. Region identity is the index in ``world.regions``, civilization identity
the index in ``world.civilizations`` and sea-zone identity the index in
``MaritimeState.zones``; nothing here is identified by a name.

Tuple orders below are declaration orders: append new values at the end,
never reorder (stored rows index into them).
"""
from __future__ import annotations

from pydantic import BaseModel, Field, PrivateAttr

#: Sea-zone control states (``SeaZoneState.status``).
ZONE_STATUSES: tuple[str, ...] = ("uncontested", "contested", "controlled")
UNCONTESTED, CONTESTED, CONTROLLED = ZONE_STATUSES

#: What a fleet is doing this turn (``Fleet.mission``).
FLEET_MISSIONS: tuple[str, ...] = ("patrol", "escort", "war", "colony", "refit")

#: Cumulative counters kept on ``MaritimeState.counters`` (insertion order).
COUNTER_KEYS: tuple[str, ...] = (
    "fleets_commissioned", "ships_built", "ships_lost_battle", "ships_lost_storm",
    "ships_lost_upkeep", "fleets_sunk", "naval_battles", "blockades", "blockade_turns",
    "piracy_losses", "piracy_treasury", "sea_trade", "landings", "overseas_campaigns",
    "colonies", "crossings", "timber_spent", "treasury_spent",
)


class _CacheSlot:
    """Holder for derived lookups. Never serialized; a copy starts empty, and
    a cache (present, absent or stale) never makes two states compare unequal."""

    __slots__ = ("value",)

    def __init__(self) -> None:
        self.value = None

    def __copy__(self) -> "_CacheSlot":
        return _CacheSlot()

    def __deepcopy__(self, memo: dict) -> "_CacheSlot":
        return _CacheSlot()

    def __reduce__(self):
        return (_CacheSlot, ())

    def __eq__(self, other: object) -> bool:
        return other is None or isinstance(other, _CacheSlot)

    __hash__ = None  # type: ignore[assignment]


class SeaZoneState(BaseModel):
    """One sea zone: its ports, neighbours, control and pirates."""

    name: str
    kind: str = "sea"                 # ocean, sea, lake, or "coast" (derived template zone)
    ports: list[int] = Field(default_factory=list)       # coastal region indices
    neighbors: list[int] = Field(default_factory=list)   # zone indices
    status: str = UNCONTESTED
    controller: int | None = None     # civ index while controlled
    since_turn: int = 0               # turn the current status began
    pirates: float = 0.0              # raider pressure in [0, 1]
    # Causal provenance: the event that set the current status (control won,
    # contested, lost); empty while the zone never changed hands.
    status_event_id: str = ""


class Fleet(BaseModel):
    """A civilization's squadron in one sea zone."""

    fleet_id: int
    name: str
    civ: int
    zone: int
    home_port: int                    # region index of the shipyard
    ships: int
    built_turn: int
    mission: str = "patrol"
    battles_won: int = 0
    battles_lost: int = 0
    refit_until: int = -1             # after a defeat the fleet holds home waters
    event_id: str = ""                # commissioning event


class NavalBattle(BaseModel):
    turn: int
    zone: int
    attacker: int
    defender: int
    attacker_ships: int
    defender_ships: int
    attacker_losses: int
    defender_losses: int
    winner: int | None = None
    event_id: str = ""


class Blockade(BaseModel):
    """A zone controller closing an enemy's sea lanes and sea supply."""

    zone: int
    blockader: int
    target: int
    start_turn: int
    end_turn: int | None = None
    event_id: str = ""


class Colony(BaseModel):
    region: int
    civ: int
    zone: int
    turn: int
    event_id: str = ""


class EscortRequest(BaseModel):
    """An army waiting on a shore for a crossing (consumed by the next tick)."""

    civ: int
    zone: int
    ships: int


class MaritimeState(BaseModel):
    """World-level maritime switch and bookkeeping (``WorldState.maritime``).

    ``lanes`` rows are ``(a, b, zone)`` with region indices ``a < b``, sorted.
    ``landmass`` maps each region index to the component it belongs to when
    sea lanes are removed (expansion and colonization use it). ``blocked``
    lists the lanes closed by blockades, as ``(a, b)`` with ``a < b``.

    ``pending_*`` hold the sea trade and piracy measured since the last
    maritime tick (Phase 2 in ``--agents off``, the native merchant crossing
    log after the agent tick otherwise). They are persisted so a resumed run
    consumes exactly what an uninterrupted one would, and the next tick
    consumes and resets them.
    """

    derived: bool = False             # zones derived from a template coast clique
    zones: list[SeaZoneState] = Field(default_factory=list)
    lanes: list[tuple[int, int, int]] = Field(default_factory=list)
    landmass: list[int] = Field(default_factory=list)
    fleets: list[Fleet] = Field(default_factory=list)
    next_fleet_id: int = 1
    fleet_counts: dict[int, int] = Field(default_factory=dict)  # per-civ naming ordinal
    battles: list[NavalBattle] = Field(default_factory=list)
    blockades: list[Blockade] = Field(default_factory=list)
    colonies: list[Colony] = Field(default_factory=list)
    blocked: list[tuple[int, int]] = Field(default_factory=list)
    escort_requests: list[EscortRequest] = Field(default_factory=list)
    # Armies that landed from the sea: army id -> turn (landing penalty, counts).
    landings: dict[str, int] = Field(default_factory=dict)
    landed_armies: list[str] = Field(default_factory=list)
    pending_sea_trade: list[float] = Field(default_factory=list)   # per zone
    pending_piracy: list[float] = Field(default_factory=list)      # per zone
    pending_piracy_civ: dict[int, float] = Field(default_factory=dict)
    counters: dict[str, float] = Field(default_factory=lambda: {k: 0 for k in COUNTER_KEYS})
    # Last tick's per-zone measurements (viewer/analytics only).
    last_sea_trade: list[float] = Field(default_factory=list)
    last_piracy: list[float] = Field(default_factory=list)
    # Derived lookups (chronicler.maritime; never serialized).
    _cache: _CacheSlot = PrivateAttr(default_factory=_CacheSlot)

    def active_blockades(self) -> list[Blockade]:
        return [b for b in self.blockades if b.end_turn is None]
