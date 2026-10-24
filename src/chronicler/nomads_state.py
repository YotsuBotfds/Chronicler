"""Persisted state of pastoral and nomadic peoples (see :mod:`chronicler.nomads`).

Pure data with no simulation imports, so :mod:`chronicler.models` can import
it. Region identity is the index in ``world.regions`` and civilization
identity the index in ``world.civilizations``; nothing here is identified by
a name (a horde's federation keeps the federation's own name, which is how
``world.federations`` identifies it).

Tuple orders below are declaration orders: append new values at the end,
never reorder (stored rows index into them).
"""
from __future__ import annotations

from pydantic import BaseModel, Field, PrivateAttr

#: Ways of life (``NomadState.modes``), most settled first.
SUBSISTENCE_MODES: tuple[str, ...] = ("sedentary", "agro_pastoral", "nomadic")
SEDENTARY, AGRO_PASTORAL, NOMADIC = range(len(SUBSISTENCE_MODES))

#: ``Horde.status``.
HORDE_STATUSES: tuple[str, ...] = ("active", "fragmented", "dissolved")

#: ``TributePact.status``.
TRIBUTE_STATUSES: tuple[str, ...] = ("active", "repudiated", "lapsed", "expired", "ended")

#: Cumulative counters kept on ``NomadState.counters`` (insertion order).
COUNTER_KEYS: tuple[str, ...] = (
    "raids", "raids_repulsed", "plunder", "raid_deaths", "tributes", "tribute_paid",
    "tributes_repudiated", "hordes_formed", "hordes_fragmented", "hordes_dissolved",
    "horde_rides", "horde_wars", "nomad_conquests", "sedentarizations", "dzuds",
    "herds_lost_dzud", "herds_lost_pasture", "pastures_abandoned",
)


class _CacheSlot:
    """Holder for derived lookups. Never serialized; a copy starts empty, and
    a cache (present, absent or stale) never makes two states compare unequal."""

    __slots__ = ("region_index",)

    def __init__(self) -> None:
        self.region_index = None

    def __copy__(self) -> "_CacheSlot":
        return _CacheSlot()

    def __deepcopy__(self, memo: dict) -> "_CacheSlot":
        return _CacheSlot()

    def __reduce__(self):
        return (_CacheSlot, ())

    def __eq__(self, other: object) -> bool:
        return other is None or isinstance(other, _CacheSlot)

    __hash__ = None  # type: ignore[assignment]


class Raid(BaseModel):
    """One raid on a settled neighbour (kept for ``RAID_MEMORY`` turns)."""

    turn: int
    raider: int                  # civ index
    target: int                  # civ index
    region: int                  # region index raided
    raiders: int
    success: bool
    loot: int = 0
    killed: int = 0
    event_id: str = ""


class TributePact(BaseModel):
    """A settled people buying peace from raiders: ``payer`` pays
    ``amount`` treasury per turn and is not raided by ``recipient``."""

    pact_id: int
    payer: int
    recipient: int
    amount: int
    start_turn: int
    status: str = "active"
    end_turn: int | None = None
    paid: int = 0
    missed: int = 0
    event_id: str = ""
    end_event_id: str = ""


class Horde(BaseModel):
    """A steppe confederation under one khan, kept as ``federation`` in
    ``world.federations`` while it stands."""

    horde_id: int
    name: str                    # also the federation's name
    khan: int                    # civ index
    khan_leader: str             # the founding khan; the horde breaks when he goes
    founded_turn: int
    members: list[int] = Field(default_factory=list)   # civ indices, khan first
    peak_members: int = 0
    status: str = "active"
    end_turn: int | None = None
    wars: int = 0                # wars the horde rode to (declared or joined)
    conquests: int = 0           # regions its members took from other peoples
    event_id: str = ""
    end_event_id: str = ""


class Conquest(BaseModel):
    """A region a pastoral people took from another polity."""

    turn: int
    region: int
    civ: int
    from_civ: int
    event_id: str = ""


class NomadState(BaseModel):
    """World-level switch and bookkeeping (``WorldState.nomads``).

    Per-civ lists (``modes``, ``mode_turn``, ``mode_event``, ``settle``) are
    indexed by civ index and extended when new polities appear. Per-region
    lists (``herds``, ``dry``, ``controllers``) are indexed by region index.
    ``herds`` is the herd stock grazing each region (100 is a full steppe
    pasture). ``controllers`` is the controller civ index (-1 unclaimed) at
    the end of the last tick, read by the next tick to detect conquests.
    """

    modes: list[int] = Field(default_factory=list)
    mode_turn: list[int] = Field(default_factory=list)
    mode_event: list[str] = Field(default_factory=list)
    settle: list[int] = Field(default_factory=list)      # generation clock toward settling
    herds: list[float] = Field(default_factory=list)
    dry: list[int] = Field(default_factory=list)         # ticks a nomad pasture stood empty
    controllers: list[int] = Field(default_factory=list)
    raids: list[Raid] = Field(default_factory=list)
    tributes: list[TributePact] = Field(default_factory=list)
    hordes: list[Horde] = Field(default_factory=list)
    conquests: list[Conquest] = Field(default_factory=list)
    next_pact_id: int = 1
    next_horde_id: int = 1
    counters: dict[str, float] = Field(default_factory=lambda: {k: 0 for k in COUNTER_KEYS})
    # Derived lookups (chronicler.nomads; never serialized).
    _cache: _CacheSlot = PrivateAttr(default_factory=_CacheSlot)

    def mode(self, civ_idx: int | None) -> int:
        """Subsistence mode of a civ index (sedentary when unknown)."""
        if civ_idx is None or civ_idx < 0 or civ_idx >= len(self.modes):
            return SEDENTARY
        return self.modes[civ_idx]

    def active_hordes(self) -> list[Horde]:
        return [h for h in self.hordes if h.status == "active"]

    def active_tributes(self) -> list[TributePact]:
        return [p for p in self.tributes if p.status == "active"]


def nomads_on(world) -> bool:
    """True only for a real nomad state on ``world`` (mocks and None read as off)."""
    return isinstance(getattr(world, "nomads", None), NomadState)
