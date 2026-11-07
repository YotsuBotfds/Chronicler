"""Persisted state of cross-border guild leagues (D1b, ``--guild-leagues``, default off).

Owned by :mod:`chronicler.guild_leagues`. Pure data with no simulation imports,
so :mod:`chronicler.livelihoods_state` can import it. A world that never
enabled the switch has no sub-state, so feature-off output is unchanged.

Identities: a league is its ``league`` id (assigned from ``next_league``,
never reused, checkpointed); a guild is its index in ``GuildState.guilds``
(dissolved guilds stay in that list); a city its ``settlement_id``; regions and
civilizations their indices. No native id is stored.

Units: money in whole milli-units of the guild and civic purses (1000 = one
purse unit; the purses themselves are floats rounded to 1e-4, so a transfer
moves exactly ``milli / 1000`` within that rounding, checked).

Everything is bounded: the living leagues (each at most ``MAX_MEMBERS``), the
last ``MAX_DISSOLVED`` dissolved leagues, at most ``MAX_LINKS`` link records, one
completed-turn frame, a rolling dated log and fixed-key counters. Tuple orders
are declaration orders: append, never reorder.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

#: ``--guild-league-mode`` choices (the first is the default when enabled).
MODES: tuple[str, ...] = ("mutual", "dues_only")
#: Recorded member losses a league fund pays (city history kinds).
CLAIM_KINDS: tuple[str, ...] = ("levy", "sack")
#: Membership changes and dissolution reasons.
CHANGE_KINDS: tuple[str, ...] = ("founded", "joined", "left", "dissolved")
LEAVE_REASONS: tuple[str, ...] = ("guild_dissolved", "city_fallen", "lord_changed")
DISSOLVE_REASONS: tuple[str, ...] = ("war_between_members", "too_few_members", "one_realm", "dormant",
                                     "switched_off")
LOG_KINDS: tuple[str, ...] = ("switched_on", "switched_off", "fund_unclaimed", "claim_unverified")
MAX_LOG = 64
MAX_DISSOLVED = 32
MAX_LINKS = 512
#: Scalar lifetime counters (declaration order; append only).
COUNTERS: tuple[str, ...] = (
    "turns", "leagues_founded", "joins", "departures", "dissolutions", "dues_milli", "dues_rows",
    "payouts_milli", "payouts_levy_milli", "payouts_sack_milli", "payout_rows", "claims_unpaid_milli",
    "returned_milli", "unclaimed_milli", "links_pruned",
)


class Member(BaseModel):
    guild: int                       # index in GuildState.guilds
    city: int                        # settlement id
    region: int
    lord: int                        # civ index of the city's lord when it joined
    joined_turn: int
    dues_milli: int = 0              # lifetime dues paid into this league
    payouts_milli: int = 0           # lifetime claims paid to its city


class League(BaseModel):
    league: int                      # id, never reused
    founded_turn: int
    members: list[Member] = Field(default_factory=list)
    fund_milli: int = 0
    last_trade_turn: int             # last turn with a recorded delivery between two members' regions
    dues_turn: int | None = None     # last turn its dues settled (exactly once a turn)
    dissolved_turn: int | None = None
    dissolved_reason: str | None = None


class Link(BaseModel):
    """Recorded merchant deliveries between two guilds' regions of different
    realms: the turns they were seen (most recent last, at most ``LINK_TURNS``)."""

    a: int                           # guild index (a < b)
    b: int
    turns: list[int] = Field(default_factory=list)


class Change(BaseModel):
    league: int
    kind: str                        # CHANGE_KINDS
    guild: int | None = None
    city: int | None = None
    reason: str | None = None        # LEAVE_REASONS / DISSOLVE_REASONS
    returned_milli: int | None = None   # a dissolution: the fund returned to the remaining members' purses
    unclaimed_milli: int | None = None  # ... or lost with no member left


class Dues(BaseModel):
    league: int
    guild: int
    city: int
    milli: int


class Payout(BaseModel):
    """A claim on a member's recorded loss: the levy's share of this turn's
    dues, or the plunder of a sack (city history ``levy`` / ``sacked``)."""

    league: int
    guild: int
    city: int
    kind: str                        # CLAIM_KINDS
    loss_milli: int                  # the recorded loss
    paid_milli: int                  # what the fund paid the city's purse (<= loss, cap, fund)
    event_id: str = ""               # the city history entry it answers


class LeagueRow(BaseModel):
    league: int
    founded_turn: int
    members: list[Member] = Field(default_factory=list)
    fund_open_milli: int = 0
    dues_milli: int = 0
    payouts_milli: int = 0
    returned_milli: int = 0
    unclaimed_milli: int = 0
    fund_close_milli: int = 0
    cap_milli: int = 0
    dissolved: str | None = None


class LeagueFrame(BaseModel):
    turn: int
    leagues: list[LeagueRow] = Field(default_factory=list)
    dues: list[Dues] = Field(default_factory=list)
    payouts: list[Payout] = Field(default_factory=list)
    changes: list[Change] = Field(default_factory=list)
    links: int = 0                   # link records held after this turn
    candidates: int = 0              # cross-border pairs with enough recorded deliveries this turn


class LeagueRecord(BaseModel):
    turn: int
    kind: str                        # LOG_KINDS
    league: int | None = None
    milli: int | None = None
    note: str = ""


class GuildLeagueState(BaseModel):
    enabled: bool = True
    mode: Literal["mutual", "dues_only"] = "mutual"
    next_league: int = 1
    leagues: list[League] = Field(default_factory=list)          # living
    dissolved: list[League] = Field(default_factory=list)        # the last MAX_DISSOLVED
    dissolved_dropped: int = 0
    links: list[Link] = Field(default_factory=list)
    frame: LeagueFrame | None = None
    frame_turn: int | None = None
    log: list[LeagueRecord] = Field(default_factory=list)
    log_dropped: int = 0
    counters: dict[str, int] = Field(default_factory=dict)
    # Transient, within one turn (the cities tick -> Phase 10): settlement id ->
    # {"levy": milli, "sack": milli, "sack_event": id} noted at the event. Never serialized.
    _turn: object | None = PrivateAttr(default=None)

    def __getstate__(self):
        state = super().__getstate__()
        private = state.get("__pydantic_private__")
        if private and private.get("_turn") is not None:
            state = {**state, "__pydantic_private__": {**private, "_turn": None}}
        return state
