"""Persisted technique state and the technique registry (see :mod:`chronicler.techniques`).

Pure data with no simulation imports, so :mod:`chronicler.models` can import
it. Region identity is the index in ``world.regions`` and civilization
identity the index in ``world.civilizations``; every stored row uses those
indices.

Declaration orders below are storage orders: stored rows index into
:data:`TECHNIQUES`, :data:`DOMAINS` and :data:`CHANNELS`, so new entries are
appended at the end and existing ones are never reordered or removed.
"""
from __future__ import annotations

from typing import NamedTuple

from pydantic import BaseModel, Field, PrivateAttr

# ``chronicler.models.ResourceType`` values (models imports this module, so
# they are restated here; tests pin the equality).
GRAIN, TIMBER, BOTANICALS, FISH, SALT, ORE, PRECIOUS, EXOTIC = range(8)

#: Technique domains (``TechniqueSpec.domain`` holds an index into this tuple).
DOMAINS: tuple[str, ...] = (
    "agriculture",
    "metallurgy",
    "construction",
    "navigation",
    "writing",       # writing and administration
    "medicine",
    "commerce",      # commerce and banking
    "military",
)
(AGRICULTURE, METALLURGY, CONSTRUCTION, NAVIGATION, WRITING, MEDICINE,
 COMMERCE, MILITARY) = range(len(DOMAINS))

#: How a practice row arrived in its region. The first four are the contact
#: ledger's channels in its own order (``chronicler.contact_ledger.CHANNELS``);
#: ``neighbours`` is the adjacency of regions under one controller (and every
#: adjacency while the ledger is off); ``invention`` a civ's own discovery;
#: ``seeded`` the practice a world already had when techniques were switched on.
CHANNELS: tuple[str, ...] = ("trade", "people", "soldiers", "pilgrims", "neighbours",
                             "invention", "seeded")
(CH_TRADE, CH_PEOPLE, CH_SOLDIERS, CH_PILGRIMS, CH_NEIGHBOURS, CH_INVENTION,
 CH_SEEDED) = range(len(CHANNELS))
#: Pseudo-channel for counting gains of a civ: a region that changed hands
#: carried the practice with it (conquest, secession, absorption, settlement).
CONQUEST = "conquest"


class TechniqueSpec(NamedTuple):
    key: str
    label: str
    domain: int
    tier: int                       # era index it belongs to (BRONZE = 1 ... INFORMATION = 7)
    prereqs: tuple[str, ...] = ()
    terrains: tuple[str, ...] = ()  # any of these terrains suits a region ...
    resources: tuple[int, ...] = ()  # ... or any of these resources ...
    river: bool = False             # ... or a river
    supply: bool = False            # resources may come from the civ's other regions or imports


#: The registry. Append only: rows store the index.
TECHNIQUES: tuple[TechniqueSpec, ...] = (
    # Tier 1 (Bronze)
    TechniqueSpec("irrigation", "irrigation", AGRICULTURE, 1,
                  terrains=("river",), resources=(GRAIN,), river=True),
    TechniqueSpec("bronze_working", "bronze working", METALLURGY, 1,
                  resources=(ORE,), supply=True),
    TechniqueSpec("masonry", "masonry", CONSTRUCTION, 1),
    TechniqueSpec("sailing", "coastal sailing", NAVIGATION, 1,
                  terrains=("coast",), resources=(FISH,)),
    TechniqueSpec("writing", "writing", WRITING, 1),
    TechniqueSpec("herbalism", "herbal lore", MEDICINE, 1,
                  terrains=("forest", "jungle", "marsh"), resources=(BOTANICALS,)),
    # Tier 2 (Iron)
    TechniqueSpec("iron_working", "iron working", METALLURGY, 2, ("bronze_working",),
                  resources=(ORE,), supply=True),
    TechniqueSpec("coinage", "coinage", COMMERCE, 2, ("writing",),
                  resources=(PRECIOUS, ORE), supply=True),
    TechniqueSpec("horsemanship", "horsemanship", MILITARY, 2,
                  terrains=("plains", "steppe", "desert")),
    TechniqueSpec("ox_plough", "the ox plough", AGRICULTURE, 2, ("irrigation",),
                  resources=(GRAIN,)),
    TechniqueSpec("roads", "road building", CONSTRUCTION, 2, ("masonry",)),
    # Tier 3 (Classical)
    TechniqueSpec("law_codes", "written law", WRITING, 3, ("writing", "coinage")),
    TechniqueSpec("aqueducts", "aqueducts", CONSTRUCTION, 3, ("masonry", "roads")),
    TechniqueSpec("celestial_navigation", "celestial navigation", NAVIGATION, 3,
                  ("sailing", "writing"), terrains=("coast",)),
    TechniqueSpec("siegecraft", "siegecraft", MILITARY, 3, ("iron_working", "masonry")),
    TechniqueSpec("physicians", "physicians", MEDICINE, 3, ("herbalism", "writing")),
    # Tier 4 (Medieval)
    TechniqueSpec("heavy_plough", "the heavy plough", AGRICULTURE, 4,
                  ("ox_plough", "iron_working"), resources=(GRAIN,)),
    TechniqueSpec("castles", "castle building", CONSTRUCTION, 4, ("aqueducts", "siegecraft")),
    TechniqueSpec("stirrup", "the stirrup", MILITARY, 4, ("horsemanship", "iron_working"),
                  terrains=("plains", "steppe", "desert")),
    TechniqueSpec("banking", "banking", COMMERCE, 4, ("coinage", "law_codes")),
    TechniqueSpec("compass", "the compass", NAVIGATION, 4, ("celestial_navigation",),
                  terrains=("coast",)),
    TechniqueSpec("lazarets", "quarantine lazarets", MEDICINE, 4, ("physicians", "law_codes")),
    # Tier 5 (Renaissance)
    TechniqueSpec("printing", "printing", WRITING, 5, ("law_codes", "iron_working")),
    TechniqueSpec("gunpowder", "gunpowder", MILITARY, 5, ("siegecraft", "castles"),
                  resources=(SALT,), supply=True),
    TechniqueSpec("double_entry", "double-entry bookkeeping", COMMERCE, 5, ("banking",)),
    TechniqueSpec("ocean_navigation", "ocean navigation", NAVIGATION, 5, ("compass",),
                  terrains=("coast",)),
    # Tier 6 (Industrial)
    TechniqueSpec("steam_power", "steam power", METALLURGY, 6, ("iron_working", "printing"),
                  resources=(ORE, TIMBER), supply=True),
    TechniqueSpec("vaccination", "vaccination", MEDICINE, 6, ("lazarets", "printing")),
    TechniqueSpec("railways", "railways", CONSTRUCTION, 6, ("steam_power", "roads")),
    # Tier 7 (Information)
    TechniqueSpec("telegraph", "the telegraph", WRITING, 7, ("steam_power", "printing")),
)
TECHNIQUE_INDEX: dict[str, int] = {t.key: i for i, t in enumerate(TECHNIQUES)}
#: Highest tier (the INFORMATION era index).
MAX_TIER = 7

#: One practice row: (region index, technique index, level in [0, 1],
#: source region index (-1 none), arrival channel index, source civ index (-1 none)).
PracticeRow = tuple[int, int, float, int, int, int]


class _StateCache:
    """Derived lookups over the rows (never serialized; equality-neutral)."""

    __slots__ = ("practice", "region_index")

    def __init__(self) -> None:
        self.practice = None
        self.region_index = None

    def __copy__(self) -> "_StateCache":
        return _StateCache()

    def __deepcopy__(self, memo: dict) -> "_StateCache":
        return _StateCache()

    def __reduce__(self):
        return (_StateCache, ())

    def __eq__(self, other: object) -> bool:
        return other is None or isinstance(other, _StateCache)

    __hash__ = None  # type: ignore[assignment]


class TechniqueState(BaseModel):
    """World-level technique switch and practice table (``WorldState.techniques``).

    ``None`` on the world means the feature is off. ``rows`` is the sparse
    per-region practice table sorted by (region, technique). ``known`` and
    ``controllers`` mirror the end of the previous tick (techniques each civ
    knew, each region's controller civ index or -1), so the next tick can tell
    what was gained or lost and how, whichever system moved the land.
    """

    initialized_turn: int | None = None
    last_tick_turn: int = -1
    rows: list[PracticeRow] = Field(default_factory=list)
    known: list[list[int]] = Field(default_factory=list)
    controllers: list[int] = Field(default_factory=list)
    # Civ practice of each technique over its suitable regions, as measured at
    # the last tick: per civ index, sorted (technique, level) pairs >= 0.01.
    # Civ-wide effects (arms, credit, quarantine, research) read these.
    civ_levels: list[list[tuple[int, float]]] = Field(default_factory=list)
    # Per civ index: consecutive ticks its techniques fell short of its era.
    era_strain: list[int] = Field(default_factory=list)
    # Cumulative counters (invented, gained:<channel>, lost:<cause>, era_up, era_down, ...).
    counts: dict[str, int] = Field(default_factory=dict)
    _cache: _StateCache = PrivateAttr(default_factory=_StateCache)

    def invalidate(self) -> None:
        self._cache = _StateCache()

    def practice_map(self) -> dict[tuple[int, int], float]:
        """(region, technique) -> practice level."""
        cache = self._cache
        if cache.practice is None:
            cache.practice = {(r[0], r[1]): r[2] for r in self.rows}
        return cache.practice


def techniques_on(world) -> bool:
    """True only for a real technique state on ``world`` (mocks and None read as off)."""
    return isinstance(getattr(world, "techniques", None), TechniqueState)
