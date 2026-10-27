"""Persisted state of agent movements (see :mod:`chronicler.agent_movements`).

Pure data with no simulation imports, so :mod:`chronicler.models` can import
it. A movement is identified by its index in ``MovementState.movements``
(ended movements stay in the list); agents carry that index + 1 as their
``movement_id``. Regions are indices in ``world.regions``, civilizations
indices in ``world.civilizations``, faiths permanent ids (indices in
``world.faiths``, chronicler.faiths; the native tables get their slots).

Tuple orders below are declaration orders: append new values at the end,
never reorder (stored values index into them). ``CREED_NAMES`` and the first
five ``STAGE_NAMES`` mirror the native constants in ``movements.rs``.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

#: ``Movement.creed`` names: the grievance a movement carries. ``guild``
#: (guilds, ``--guilds``): a city's guild defending its privileges, founded
#: by :mod:`chronicler.guilds` when they are threatened, never from the census.
CREED_NAMES: tuple[str, ...] = ("commons", "liberty", "sect", "guild")
COMMONS, LIBERTY, SECT, GUILD = range(len(CREED_NAMES))
#: Creeds whose grievance is a need (the native census counts these).
NEED_CREEDS = 3

#: ``Movement.stage`` names (all but ``ended`` are sent to the agent tick).
STAGE_NAMES: tuple[str, ...] = ("gathering", "pressing", "suppressed", "rising", "satisfied", "ended")
GATHERING, PRESSING, SUPPRESSED, RISING, SATISFIED, ENDED = range(len(STAGE_NAMES))

#: ``Movement.end`` names (0 while living).
END_NAMES: tuple[str, ...] = ("", "faded", "won", "seceded", "schism", "crushed", "dissolved")
LIVING, FADED, WON, SECEDED, SCHISM, CRUSHED, DISSOLVED = range(len(END_NAMES))

#: ``Movement.history`` entry kinds.
HISTORY_KINDS: tuple[str, ...] = (
    "founded", "spread", "demand", "reform", "refused", "crackdown", "martyr", "rising",
    "concession", "crushed", "seceded", "schism", "ended", "dispersed", "leader",
)

#: Cumulative counters kept on ``MovementState.counters`` (insertion order).
COUNTER_KEYS: tuple[str, ...] = (
    "founded", "demands", "reforms", "refusals", "crackdowns", "martyrs", "risings",
    "concessions", "crushed", "secessions", "schisms", "faded", "won", "broken",
    "dissolved", "relief_cost", "enacted", "extended", "repealed", "lapsed", "restored",
    "upkeep", "leaders", "charters",
)

#: ``Reform.kind`` names: the lasting reform a creed wins (index = creed).
#: ``guild_charter``: the guild's privileges and lower dues in its city
#: (``regions`` its region, ``cities`` its settlement id).
REFORM_NAMES: tuple[str, ...] = ("relief", "home_rule", "toleration", "guild_charter")
RELIEF, HOME_RULE, TOLERATION, GUILD_CHARTER = range(len(REFORM_NAMES))

#: ``Reform.repeal`` names (0 while in force). ``lapsed`` ends a reform
#: without a grievance (its realm, region or faith is gone).
REPEAL_NAMES: tuple[str, ...] = ("", "neglect", "opposition", "ruler", "fiscal", "inquisition",
                                 "lapsed")
IN_FORCE, NEGLECT, OPPOSITION, RULER, FISCAL, INQUISITION, LAPSED = range(len(REPEAL_NAMES))


class Movement(BaseModel):
    """One movement, from its founding to its end."""

    name: str
    creed: int
    founded_turn: int
    home_region: int                 # region index of the founding
    target: int                      # civ index of the ruler it opposes
    leader: str = ""                 # great person who founded it ("" none)
    leader_agent: int = 0            # the leader's agent id (0 none)
    idea: str = ""                   # M16b movement id it carries ("" none)
    faith: int = 255                 # members' commonest faith, permanent id (255 unknown)
    stage: int = GATHERING
    stage_turn: int = 0
    members: int = 0                 # at the last Phase 10
    peak_members: int = 0
    # [region index, members] for regions with members, ascending region.
    member_regions: list[list[int]] = Field(default_factory=list)
    strength: float = 0.0            # members' share of the target realm's adults
    stronghold: int = -1             # realm region with the largest member share
    stronghold_share: float = 0.0
    grievance: float = 0.0           # refusals and crackdowns, 0..1.5
    martyrs: int = 0
    low_turns: int = 0               # consecutive turns below the fade floor
    demands: int = 0
    last_demand: int = -1000
    last_rising: int = -1000
    reform_turn: int | None = None
    crackdown_turn: int | None = None
    crackdown_region: int = -1
    rising_turn: int | None = None
    rising_region: int = -1
    rising_members: int = 0          # members in the stronghold when it rose
    schism_turn: int | None = None
    schism_from: int = 255           # the church it broke from (permanent id)
    schism_to: int = 255             # the church it became (permanent id)
    leader_mourned: bool = False
    ended_turn: int | None = None
    end: int = LIVING
    successor: int = -1              # civ index (seceded) or permanent faith id (schism)
    regions_reached: list[int] = Field(default_factory=list)
    # (turn, kind, event id) in order; kinds from HISTORY_KINDS.
    history: list[tuple[int, str, str]] = Field(default_factory=list)
    reform: int = -1                 # index in MovementState.reforms of the reform it won
    restores: int = -1               # index of the repealed reform it wants restored
    leader_candidate: int = 0        # agent id queued for promotion as its leader (0 none)
    leader_turn: int | None = None   # turn its leader was queued


class Reform(BaseModel):
    """A lasting reform: what a movement won, in force until repealed.

    ``kind`` is the creed it answers (``REFORM_NAMES``). Coverage: ``relief``
    the realm of ``civ``; ``home_rule`` the realm's regions in ``regions``;
    ``toleration`` the believers of ``faith`` in the realm (``church``: the
    ruler's own faith, whose church the grant reformed). ``institution``
    names the governance institution it enacted or upholds ("" none)."""

    kind: int
    civ: int                         # civ index of the ruler who granted it
    movement: int = -1               # movement index that won it
    enacted_turn: int
    regions: list[int] = Field(default_factory=list)
    faith: int = 255                 # toleration: permanent faith id
    church: bool = False             # toleration of the ruler's own faith: its church reformed
    institution: str = ""
    founded_institution: bool = False  # the grant enacted it (a ruler's repeal takes it)
    cities: list[int] = Field(default_factory=list)  # settlement ids its charters raised
    ruler: str = ""                  # the reign it was last judged under
    ruler_start: int = 0
    arrears: int = 0                 # consecutive turns its upkeep went unpaid
    restores: int = -1               # index of the repealed reform it restores
    event_id: str = ""               # the grant
    repealed_turn: int | None = None
    repeal: int = IN_FORCE
    repeal_event_id: str = ""


class MovementState(BaseModel):
    """World-level switch and bookkeeping (``WorldState.agent_movements``)."""

    movements: list[Movement] = Field(default_factory=list)
    counters: dict[str, float] = Field(default_factory=lambda: {k: 0 for k in COUNTER_KEYS})
    last_tick_turn: int | None = None
    reforms: list[Reform] = Field(default_factory=list)


def agent_movements_on(world) -> bool:
    """True only for a real movement state on ``world`` (mocks and None read as off)."""
    return isinstance(getattr(world, "agent_movements", None), MovementState)
