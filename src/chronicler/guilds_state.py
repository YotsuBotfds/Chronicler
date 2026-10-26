"""Persisted state of guilds (see :mod:`chronicler.guilds`).

Pure data with no simulation imports, so :mod:`chronicler.models` can import
it. A guild is identified by its index in ``GuildState.guilds`` (dissolved
guilds stay in the list); its city by the M56a ``settlement_id``; regions by
their index in ``world.regions`` and civilizations by their index in
``world.civilizations``.

Tuple orders below are declaration orders: append new values at the end,
never reorder (stored values index into them).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

#: ``Guild.kind`` names: a craft guild works the city's wares, a merchant
#: guild its trade.
KIND_NAMES: tuple[str, ...] = ("craft", "merchant")
CRAFT, MERCHANT = range(len(KIND_NAMES))

#: ``Guild.history`` entry kinds.
HISTORY_KINDS: tuple[str, ...] = (
    "founded", "privilege", "lost", "levy", "threat", "movement", "charter", "repealed",
    "walls", "dissolved",
)

#: Threats to a guild's privileges (``Guild.history`` "threat" entries name
#: them; each may raise a guild movement).
THREAT_NAMES: tuple[str, ...] = ("levy", "charter", "sack", "occupation", "repeal")
LEVY, CHARTER_REVOKED, SACK, OCCUPATION, REPEAL = range(len(THREAT_NAMES))

#: Cumulative counters kept on ``GuildState.counters`` (insertion order).
COUNTER_KEYS: tuple[str, ...] = (
    "founded", "dissolved", "privileges", "privileges_lost", "levies", "threats",
    "movements", "charters", "take", "walls", "burghers_formed", "burghers_dissolved",
)


class Guild(BaseModel):
    """One city's guild, from its founding to its dissolution."""

    city: int                        # settlement id of its city
    region: int                      # region index of the city
    name: str
    kind: int = CRAFT
    founded_turn: int
    masters: float = 0.0             # merchants and craftworkers at the last tick (reference scale)
    peak_masters: float = 0.0
    wealth: float = 0.0              # the guild's purse: its take of the city's commerce
    monopoly: bool = False           # wares production (granted with market rights)
    say: bool = False                # a say in civic dues (granted with self-government)
    last_charter: int = 0            # the city's charter level at the last tick
    lord: int = -1                   # civ index of the city's lord at the last tick
    occupied: bool = False           # its region occupied at the last tick
    levy_turn: int | None = None     # turn the lord last raised its dues
    charter_reform: int = -1         # index of the guild charter (a movement reform) it holds
    movement: int = -1               # index of its last guild movement
    last_threat: int = -1000
    low_turns: int = 0               # consecutive turns below the dissolution floor
    dissolved_turn: int | None = None
    # (turn, kind, event id) in order; kinds from HISTORY_KINDS.
    history: list[tuple[int, str, str]] = Field(default_factory=list)


class GuildState(BaseModel):
    """World-level switch and bookkeeping (``WorldState.guilds``).

    ``burgher_idle`` counts, per civ index, the consecutive turns a realm with
    a burgher faction has had no chartered city, free city or guild."""

    guilds: list[Guild] = Field(default_factory=list)
    counters: dict[str, float] = Field(default_factory=lambda: {k: 0 for k in COUNTER_KEYS})
    burgher_idle: list[int] = Field(default_factory=list)
    last_tick_turn: int | None = None


def guilds_on(world) -> bool:
    """True only for a real guild state on ``world`` (mocks and None read as off)."""
    return isinstance(getattr(world, "guilds", None), GuildState)
