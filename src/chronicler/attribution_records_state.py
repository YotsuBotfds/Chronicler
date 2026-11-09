"""Persisted state of the attribution records (D2, ``--attribution-records``, default off).

Owned by :mod:`chronicler.attribution_records`. Pure data with no simulation
imports, so :mod:`chronicler.livelihoods_state` can import it. A world that
never enabled the switch has no sub-state, so feature-off output is unchanged.

Identities: regions are indices in ``world.regions``; civilizations are
indices in ``world.civilizations`` (each record also carries the name at the
event); cities are settlement ids; wars are ``(war_key, start_turn)``; armies
are their ``army_id``. A restored polity reuses the dead polity's index and
name (``politics.check_restoration``, ``politics_bridge``): the identity log
dates every reuse, so a consumer can tell the two polities apart (an
intentional boundary, ``docs/integration/attribution-records.md``).

Everything is bounded: one completed-turn frame (casualty rows per war,
victim, actor and cause; one row per granary seizure; burden pairs per kind,
nature, unit, actor and victim, and at most ``MAX_ENTRIES`` burden entries),
one identity row per civilization index, one closure baseline per live army,
a rolling identity log (``MAX_IDENTITY_LOG``), a rolling dated log
(``MAX_LOG``), lifetime totals with the fixed key set ``LIFETIME`` and scalar
counters with the fixed key set ``COUNTERS``. Tuple orders below are
declaration orders: append new values at the end, never reorder.
"""
from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, PrivateAttr

from chronicler.switch_state import SwitchStateMixin

#: Casualty causes as ``war.armies.apply_casualties`` names them, then the
#: deaths ``war.armies.reconcile_rosters`` books as casualties: ``natural``
#: (native mortality with its x2 for soldiers at war, plague and other non-war
#: catastrophes) unless the agent died in a region where a war drain
#: (``war.armies.drain_population``: siege civilians, a battle's garrison,
#: occupation depopulation, a crushed revolt) staged deaths that turn:
#: ``war_drain`` when that region's drains name one actor, ``possibly_enemy``
#: when they name several or none (nomad raids and a roster-less army's own
#: casualties name none), at most the staged count per region and turn.
CASUALTY_CAUSES: tuple[str, ...] = ("battle", "trapped", "revolt", "attrition", "natural", "war_drain",
                                    "possibly_enemy")
#: The class each cause belongs to (the separation D2 records).
CASUALTY_CLASS: dict[str, str] = {
    "battle": "combat", "trapped": "combat", "revolt": "combat", "attrition": "attrition", "natural": "natural",
    "war_drain": "war_drain", "possibly_enemy": "war_drain",
}
CASUALTY_CLASSES: tuple[str, ...] = ("combat", "attrition", "natural", "war_drain")

#: Burden kinds: ``kind -> (authority that decides it, nature, unit)``.
#: Natures: ``transfer`` (a real payment from the victim to the actor),
#: ``minted`` (credited to the actor, taken from nobody), ``destroyed`` (lost
#: by the victim, received by nobody), ``restriction`` (no amount moves: a
#: closed journey). Units: ``treasury`` (treasury units), ``food`` (commons
#: food goods), ``goods`` (all market goods), ``grain`` (granary grain),
#: ``milli_food`` (owned food, milli-units), ``routes`` (trade routes).
BURDEN_KINDS: dict[str, tuple[str, str, str]] = {
    "city_dues": ("cities._commerce (assessed at Phase 10, paid at the next Phase 2 by cities.pay_dues)",
                  "transfer", "treasury"),
    "guild_levy": ("guilds._levies raises the dues share (guilds.dues_share); the levied part of the dues",
                   "transfer", "treasury"),
    "city_sack": ("cities._sack: the plunder paid to the sacker", "transfer", "treasury"),
    "city_sack_loss": ("cities._sack: the fraction of the loot no one receives", "destroyed", "treasury"),
    "occupation_plunder": ("war.occupation.start_occupation (population // 10 to the occupier)", "minted", "treasury"),
    "occupation_requisition": ("war.occupation.tick_occupations (the occupier's per-turn requisition)",
                               "minted", "treasury"),
    "occupation_tax_loss": ("war.occupation.tick_occupations (the owner's lost taxes, spent into nothing)",
                            "destroyed", "treasury"),
    "food_requisition": ("war.occupation._requisition (siege turn x0.85, occupation start x0.8 of commons food)",
                         "destroyed", "food"),
    "conquest_stock_loss": ("action_engine.apply_region_conquest (each market good x0.5)", "destroyed", "goods"),
    "granary_seizure": ("grain_reserves.seize_granary (a SEIZED flow)", "destroyed", "grain"),
    "retail_war_loss": ("household_retail.on_conquest / on_war_loss (retail rules 2)", "destroyed", "milli_food"),
    "treaty_payment": ("war.peace.conclude_peace (reparations or tribute, loser to winner)", "transfer", "treasury"),
    "quarantine_closure": ("quarantine_rules.decide (closure mode: the closer's trade routes to the target)",
                           "restriction", "routes"),
}
# Keep pre-integration lifetime declaration order stable when adding a kind.
_LEGACY_BURDEN_KINDS = tuple(BURDEN_KINDS)
BURDEN_KINDS["infrastructure_war_damage"] = (
    "infrastructure_condition.war_damage (accepted conquest or sack damage per asset)",
    "destroyed", "condition",
)
BURDEN_NATURES: tuple[str, ...] = ("transfer", "minted", "destroyed", "restriction")
BURDEN_UNITS: tuple[str, ...] = ("treasury", "food", "goods", "grain", "milli_food", "routes", "condition")

#: Identity events (restored civilization identity reuse and its relatives).
IDENTITY_KINDS: tuple[str, ...] = ("restored", "revived", "name_reused", "renamed")

#: Dated log kinds.
LOG_KINDS: tuple[str, ...] = ("switched_on", "switched_off", "note_after_close", "unobserved")
MAX_LOG = 64
MAX_IDENTITY_LOG = 64
#: At most this many burden entries are kept per frame (pairs stay exact).
MAX_ENTRIES = 256

#: Lifetime totals (declaration order; append only): deaths per cause, then
#: each burden kind's amount (its own unit) and its number of events.
LIFETIME: tuple[str, ...] = (
    *(f"deaths_{cause}" for cause in CASUALTY_CAUSES[:5]),
    *(f"burden_{kind}" for kind in _LEGACY_BURDEN_KINDS),
    *(f"burden_{kind}_events" for kind in _LEGACY_BURDEN_KINDS),
    # Review m1 (appended): deaths at reconciliation in a region a war drain hit.
    "deaths_war_drain", "deaths_possibly_enemy",
    # B3 integration (appended): accepted asset-condition loss, never money or food.
    "burden_infrastructure_war_damage", "burden_infrastructure_war_damage_events",
)

#: Lifetime counters (declaration order; append only).
COUNTERS: tuple[str, ...] = (
    "turns_observed", "turns_unobserved", "switched_on", "switched_off", "notes_after_close",
    "combat_unresolved", "army_closures_checked", "army_closures_failed", "army_closures_unchecked",
    "granary_seizures", "granary_unattributed", "retail_war_losses", "retail_unattributed",
    "entries_dropped", "identity_events",
    # Review m1, m2 and n1 (appended).
    "war_drain_deaths", "battle_checks", "battle_checks_failed", "zero_amount_events",
)


def _is_none(value) -> bool:
    return value is None


class CivIdentity(BaseModel):
    """What the records last saw at one civilization index (Phase 10)."""

    name: str
    alive: bool                      # held at least one region
    founded_turn: int | None = None
    last_alive_turn: int | None = None   # the last observed turn it held a region (None: not seen alive)
    since_turn: int                  # the first turn the records saw this index


class IdentityRecord(BaseModel):
    """A dated identity event at one civilization index."""

    turn: int
    kind: str                        # IDENTITY_KINDS
    civ: int
    name: str
    detail: dict[str, Any] = Field(default_factory=dict)


class LogRecord(BaseModel):
    turn: int
    kind: str                        # LOG_KINDS
    detail: dict[str, Any] = Field(default_factory=dict)


class AttributionRecordsState(SwitchStateMixin, BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    #: The completed-turn frame (JSON-ready; shape in
    #: ``docs/integration/attribution-records.md``). None: not observed.
    frame_turn: int | None = None
    frame: dict[str, Any] | None = None
    #: One row per civilization index the records have seen (list index =
    #: civilization index).
    civs: list[CivIdentity] = Field(default_factory=list)
    #: Each live army's casualty counter at the last commit (the closure
    #: baseline) and that commit's turn; None: no baseline yet.
    army_casualties: dict[str, int] = Field(default_factory=dict)
    baseline_turn: int | None = None
    #: Rolling identity log (the last ``MAX_IDENTITY_LOG`` records).
    identity_log: list[IdentityRecord] = Field(default_factory=list)
    identity_dropped: int = 0
    #: Lifetime totals (the fixed key set ``LIFETIME``).
    lifetime: dict[str, int | float] = Field(default_factory=dict)
    #: Scalar lifetime counters (the fixed key set ``COUNTERS``).
    counters: dict[str, int] = Field(default_factory=dict)
    #: Rolling dated log (the last ``MAX_LOG`` records).
    log: list[LogRecord] = Field(default_factory=list)
    log_dropped: int = 0
    # Transient, within one turn (the first note -> the Phase 10 commit): the
    # notes taken at the events. Never serialized.
    _turn: object | None = PrivateAttr(default=None)

    _FILL_DEFAULTS: ClassVar[bool] = True
    _FILL_PRIVATE: ClassVar[tuple[str, ...]] = ("_turn",)
    _TRANSIENT: ClassVar[tuple[str, ...]] = ("_turn",)
    _BUMP: ClassVar[dict] = {"allowed": COUNTERS, "message": "undeclared attribution-records counter {key!r}"}
