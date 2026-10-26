"""In-world historiography: chroniclers, archives and their biased accounts.

An observational layer (docs/integration/historiography.md). After every
completed turn :func:`observe_turn` reads the world and that turn's events
and writes *accounts* into a :class:`HistoriographyState` that lives beside
the world (``WorldState._historiography``), never in it. The layer draws no
simulation random numbers (every choice is a namespaced ``stable_hash_int``
draw), builds none of the world's lookup caches (``civ_map``,
``region_map``, the history index, the technique practice map) and no
simulation code reads it, so the simulation, its snapshots and its saved
state are byte-identical with the layer on or off. The state is saved in a
sidecar next to the state file (``state.json`` ->
``state.historiography.json``) so ``state.json`` keeps its bytes.

Who writes:

* a **court chronicler** per civilization (``court:<civ index>``), keeping
  its archive in the civ's capital;
* a **temple chronicler** per faith with a standing temple
  (``temple:<faith id>``), keeping its archive at its most prestigious temple.

What they write: every account tells one real event (its ``event_id``).
Bias is a list of recorded transformations of that event, decided by the
chronicler's state when it wrote: the ruler's legitimacy and the factions
(loyal or disaffected court), the clergy's influence and the faith, the
grievances held against neighbours and whether the event was a victory or a
defeat. ``omit`` (silence), ``inflate`` / ``minimize`` (casualties, or the
scale of a triumph or loss), ``claim`` (a stalemate told as a victory),
``blame`` (a *different real cause* from the provenance graph, or an older
grievance the chronicler holds, named instead of the recorded cause),
``praise`` / ``condemn`` (the ruler) and ``divine`` (favour, trial or wrath
of the gods). No account is ever invented.

Archives survive or are lost: a sack or annexation of the archive's region,
the conquest or collapse of its civilization, fire, earthquake, flood and
plague each destroy part of it; every account survives an episode if one of
its copies does, and literacy techniques (writing, written law, printing,
the telegraph, when ``--techniques`` is on) add copies. A chronicler cites
only causes it still holds, so the history of a fallen civ comes down in its
victor's accounts.

:func:`export` builds the viewer bundle's optional ``historiography`` field,
including *contested accounts* (one event told differently by two
chroniclers); :class:`AccountIndex` reads that field back for the narrator
prompt, the mechanical chronicle and the curator.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Sequence

from pydantic import BaseModel, Field

from chronicler.models import VOLUNTARY_MIGRATION_DRIVERS
from chronicler.utils import stable_hash_int

if TYPE_CHECKING:  # pragma: no cover
    from chronicler.models import Event, WorldState

logger = logging.getLogger(__name__)

NAMESPACE = "historiography"
#: New worlds keep chronicles unless ``--no-historiography`` (see the doc's
#: "Default" section): the layer is observational and proven outcome-neutral.
DEFAULT_ENABLED_FOR_NEW_WORLDS = True
FORMAT = "chronicler.historiography"
VERSION = 1
SIDECAR_SUFFIX = ".historiography.json"

# ---------------------------------------------------------------------------
# Parameters (illustrative; they shape narration only)
# ---------------------------------------------------------------------------

MIN_IMPORTANCE = 6            # court chronicles skip lesser events ...
MIN_IMPORTANCE_LOW = 5        # ... except unrest, crises and rulers
TEMPLE_MIN_IMPORTANCE = 7     # temple chronicles are more selective
NOTABLE_IMPORTANCE = 7        # unclassified events this important are chronicled plainly
MAX_ACCOUNTS_PER_TURN = 8     # per chronicler, most important first
REPEAT_WINDOW = 10            # turns within which a chronicler does not retell a recurring
                              # hostility, disaster or treaty (same type, parties, region)
LOYAL_LEGITIMACY = 0.55       # a court at or above this flatters its ruler
DISAFFECTED_LEGITIMACY = 0.35  # ... below this (or in a power struggle) writes against him
DIVINE_CLERGY = 0.30          # clergy influence at which a court sees the gods' hand in disasters
TEMPLE_PIOUS_CLERGY = 0.25    # a temple praises rulers whose clergy is this strong
OMIT_DEFEAT = (0.30, 0.40)    # loyal court: P(omit a defeat) = base + slope * zeal
OMIT_DISGRACE = (0.40, 0.40)  # loyal court: P(omit unrest, crisis, regression)
OMIT_BETRAYAL = 0.50          # loyal court: P(omit its own broken treaty)
CLAIM_STALEMATE_ZEAL = 0.40   # zeal from which a stalemate is told as a victory
ANCESTRY_DEPTH = 6            # cause-graph steps searched for someone to blame
ANCESTRY_NODES = 64
PRETEXT_WINDOW = 30           # turns an archived grievance still serves as a pretext
PRETEXT_GRIEVANCE = 1.5       # grievance needed to blame an enemy without a recorded link
#: Probability that one copy of an account survives each kind of loss (one
#: episode per archive, cause and turn).
SURVIVAL: dict[str, float] = {
    "sack": 0.50, "conquest": 0.25, "collapse": 0.60, "fire": 0.70,
    "quake": 0.75, "flood": 0.85, "plague": 0.97, "desecration": 0.50,
    "absorption": 0.60,
}
#: Extra copies an archive keeps per writing technique its owner knows
#: (``--techniques`` only; one copy otherwise).
LITERACY_COPIES: tuple[tuple[str, int], ...] = (
    ("writing", 1), ("law_codes", 1), ("printing", 2), ("telegraph", 1),
)
CONTESTED_WEIGHT = 1.0        # curator bonus per kind of divergence
CONTESTED_CAP = 3.0

# ---------------------------------------------------------------------------
# Event classification
# ---------------------------------------------------------------------------

#: Two-sided events: type -> index (in ``actors``) of the side that gains.
TWO_SIDED: dict[str, int] = {
    "occupation": 0, "annexation": 0, "civ_conquered": 0, "vassalization": 0,
    "raid": 0, "hostage_taken": 0, "liberation": 0, "artifact_captured": 0,
    "raid_repulsed": 1, "secession": 1, "union_annexation": 1, "twilight_absorption": 1,
}
#: How a loser's court tells a two-sided or one-sided loss it minimizes.
MINIMIZE_PHRASES: dict[str, str] = {
    "occupation": "the garrison withdrew to fight another day",
    "annexation": "the land was ceded for the sake of peace",
    "civ_conquered": "the spirit of the realm endured",
    "vassalization": "it was an alliance between equals",
    "union_annexation": "it was a union between equals",
    "twilight_absorption": "the realm chose its protector",
    "raid": "the raiders carried off little",
    "hostage_taken": "an honoured guest, not a captive",
    "liberation": "the province was let go of the ruler's grace",
    "artifact_captured": "the treasure was a gift",
    "raid_repulsed": "the riders turned back of their own accord",
    "secession": "the province was set free of the ruler's grace",
    "army_destroyed": "they sold their lives dearly",
    "general_fallen": "he fell with honour",
    "fleet_lost": "the sea, not the enemy, took them",
    "capital_loss": "the court moved by its own choice",
    "peace_treaty": "a peace freely granted",
}
#: Engagements whose description carries the outcome token.
BATTLES = frozenset({"war", "naval_battle"})
#: The first actor suffers the loss.
ONE_SIDED_LOSS = frozenset({
    "army_destroyed", "capital_loss", "scorched_earth", "general_fallen", "fleet_lost",
    "sea_control_lost", "artifact_lost", "artifact_destroyed", "technique_lost",
})
WAR_START = frozenset({"war_declared", "horde_rides", "call_to_arms"})
#: The first actor acts against the second (``border_incident`` is mutual).
HOSTILITY = frozenset({
    "embargo", "border_incident", "proxy_detected", "treaty_broken",
    "propaganda_campaign", "blockade", "piracy", "siege_begun",
})
DISASTER = frozenset({
    "famine", "dearth", "famine_starvation", "plague", "pandemic", "epidemic", "epidemic_arrival",
    "drought", "drought_intensification", "earthquake", "flood", "wildfire",
    "locust_swarm", "sandstorm", "supervolcano", "soil_exhaustion", "mine_collapse",
    "dzud", "pasture_drought", "fishery_collapse", "migration", "mass_migration",
    "demographic_crisis", "brain_drain", "fleet_storm", "tech_accident",
    "resource_depletion", "pandemic_leader_death",
})
DISGRACE = frozenset({
    "rebellion", "local_rebellion", "revolt", "civil_war", "psi_crisis", "coup",
    "loyalty_cascade", "vassal_rebellion", "power_struggle_started", "legitimacy_crisis",
    "succession_crisis", "twilight", "collapse", "tech_regression", "ambition_failed",
    "dynasty_split", "dynasty_extinct", "horde_fragmented", "federation_collapsed",
    "congress_collapse", "fiscal_crisis", "intelligence_failure", "secession_defection",
    "movement_rising", "movement_concession",
})
GLORY = frozenset({
    "great_person_born", "cultural_work", "cultural_renaissance", "discovery",
    "tech_advancement", "tech_breakthrough", "technique_invented", "artifact_created",
    "tradition_acquired", "cognomen_awarded", "folk_hero_created", "ambition_fulfilled",
    "institution_enacted", "cultural_hegemony", "universal_enlightenment",
    "paradigm_shift", "ruin_discovery", "resource_discovery", "exploration",
    "economic_boom", "ecological_recovery", "fishery_recovery", "restoration",
    "secession_suppressed", "dynasty_founded", "exile_return", "horde_formed",
    "settlement_founded", "sea_control",
})
#: Guilds (``--guilds``), told from GUILD_MIN_IMPORTANCE (guild events are
#: minor, so they sort after the rest of a turn's picks): a guild formed or a
#: privilege or guild charter granted is the realm's prosperity (glory); a
#: privilege lost or a guild charter repealed is the ruler's act, praised by
#: a loyal court and condemned by a disaffected one (decree); a guild rising
#: as a movement is unrest (disgrace; its revolt is a ``movement_rising``).
#: Movement events count as guild events only for a guild movement or a
#: guild charter (``_Turn.guild_stance``).
GUILD_GLORY = frozenset({"guild_founded", "guild_privilege"})
GUILD_DECREE = frozenset({"guild_privilege_lost"})
GUILD_MIN_IMPORTANCE = 3
RULER = frozenset({"leader_death", "succession_crisis_resolved"})
FAITH = frozenset({
    "Persecution", "Mass Migration", "Schism", "Reformation", "temple_destroyed",
    "religious_movement", "movement_adoption", "movement_emergence", "movement_schism",
    "martyrdom", "pilgrimage_departure", "pilgrimage_return", "movement_martyr",
})
PEACE = frozenset({
    "peace_treaty", "war_ended", "congress_peace", "congress_ceasefire", "treaty_signed",
    "tribute_agreed", "federation_formed",
})
#: Never chronicled, whatever their importance (routine actions, bookkeeping).
ROUTINE = frozenset({
    "develop", "invest_culture", "diplomacy", "trade", "build_started",
    "infrastructure_completed", "fund_instability", "fund_instability_failed", "action",
    "expand", "treaty_renewed", "treaty_expired", "loan_taken", "debt_written_off",
    "army_raised", "army_disbanded", "mercenary_spawned", "tech_focus_selected",
    "trait_evolution", "faction_dominance_shift", "institutional_regime_shift",
    "government_transition", "quarantine", "aid_convoy", "mutual_aid", "price_inflation",
    "reform_pressure", "fiscal_strain", "elite_overproduction", "terrain_transition",
    "settlement_dissolved", "explore_failed", "pandemic_spread", "move_capital", "none",
    "supply_shock", "occupation_shift", "notable_migration", "economic_shock",
})
_ENDING_EPISODES = frozenset({"end", "repeat", "tick"})

_POLITY_WORDS = frozenset({
    "empire", "confederacy", "republic", "nomads", "kingdom", "dominion", "federation",
    "league", "sultanate", "khanate", "union", "commonwealth", "theocracy", "clans",
    "tribes", "realm", "principality", "duchy", "horde", "assembly", "state", "states",
    "hegemony", "compact", "covenant", "collective", "directorate", "protectorate",
    "caliphate", "shogunate", "tribe", "marches", "march", "throne",
})

# ---------------------------------------------------------------------------
# Persisted state
# ---------------------------------------------------------------------------


class Transform(BaseModel):
    """One recorded transformation of the true event in an account.

    ``kind`` is omit, inflate, minimize, claim, blame, praise, condemn or
    divine; ``detail`` holds its structured terms (true and claimed values,
    the blamed civ and the event cited instead of the recorded causes, the
    faith and whom the gods are said to punish).
    """
    kind: str
    detail: dict[str, Any] = Field(default_factory=dict)


class Account(BaseModel):
    """A chronicler's telling of one real event."""
    account_id: str                 # "<chronicler id>/<event id>"
    event_id: str
    turn: int                       # the event's turn (written when it ended)
    chronicler: str
    stance: str                     # victory, defeat, stalemate, disaster, disgrace, glory, ...
    transforms: list[Transform] = Field(default_factory=list)
    cited: list[str] = Field(default_factory=list)   # causes named (real events it holds)
    text: str = ""                  # "" for an omission
    lost_turn: int | None = None    # the turn its last copy was destroyed
    lost_cause: str | None = None


class ArchiveLoss(BaseModel):
    turn: int
    cause: str                      # sack, conquest, collapse, fire, quake, flood, plague, desecration
    event_id: str                   # the event that destroyed it
    region: int | None = None       # index in world.regions
    copies: int = 1
    lost: int = 0
    survived: int = 0


class Archive(BaseModel):
    archive_id: str                 # "archive:<chronicler id>"
    owner: str                      # chronicler id
    region: int | None = None       # where it stands (index in world.regions); None when homeless
    copies: int = 1
    losses: list[ArchiveLoss] = Field(default_factory=list)


class Chronicler(BaseModel):
    chronicler_id: str              # "court:<civ index>" or "temple:<faith id>"
    kind: str                       # court, temple
    civ: int | None = None          # civ index (court)
    faith: int | None = None        # faith id (temple)
    name: str                       # "the Kethani chronicles"
    founded_turn: int
    active: bool = True


class HistoriographyState(BaseModel):
    """Everything the in-world chroniclers have written (never read by the simulation)."""
    version: int = VERSION
    enabled_turn: int = 0
    cursor: int = 0                 # events_timeline entries already observed
    last_turn: int = 0              # world.turn after the last observed turn
    chroniclers: list[Chronicler] = Field(default_factory=list)
    archives: list[Archive] = Field(default_factory=list)
    accounts: list[Account] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


class HistoriographySlot:
    """``WorldState._historiography``: the state plus derived lookups.

    Equality-neutral (like the provenance turn counters and the history
    index), so a world compares equal with the layer on or off; copies carry
    a deep copy of the state (a fork keeps its own chronicles) and fresh
    lookups.
    """

    __slots__ = ("state", "_events", "_events_upto", "_accounts", "_by_chronicler", "_recent",
                 "_zeal")

    def __init__(self, state: HistoriographyState) -> None:
        self.state = state
        self._reset_cache()

    def _reset_cache(self) -> None:
        self._events: dict[str, int] = {}
        self._events_upto = 0
        self._accounts: dict[str, int] | None = None
        self._by_chronicler: dict[str, list[int]] | None = None
        self._recent: dict[str, dict[tuple, int]] | None = None
        self._zeal: dict[tuple, float] = {}

    def __eq__(self, other: object) -> bool:
        return other is None or isinstance(other, HistoriographySlot)

    __hash__ = None  # type: ignore[assignment]

    def __copy__(self) -> "HistoriographySlot":
        return HistoriographySlot(self.state.model_copy(deep=True))

    def __deepcopy__(self, memo: dict) -> "HistoriographySlot":
        return self.__copy__()

    def __reduce__(self):
        return (_slot_from_dump, (self.state.model_dump(mode="json"),))

    # --- derived lookups (never serialized) ---------------------------------

    def index_events(self, timeline: Sequence["Event"]) -> dict[str, int]:
        """event_id -> timeline index, extended incrementally."""
        upto = self._events_upto
        if upto > len(timeline):
            self._events, upto = {}, 0
        events = self._events
        for i in range(upto, len(timeline)):
            eid = timeline[i].event_id
            if eid and eid not in events:
                events[eid] = i
        self._events_upto = len(timeline)
        return events

    def _build_accounts(self) -> None:
        self._accounts = {}
        self._by_chronicler = {}
        for i, acc in enumerate(self.state.accounts):
            self._accounts[acc.account_id] = i
            self._by_chronicler.setdefault(acc.chronicler, []).append(i)

    def account(self, account_id: str) -> Account | None:
        if self._accounts is None:
            self._build_accounts()
        i = self._accounts.get(account_id)  # type: ignore[union-attr]
        return None if i is None else self.state.accounts[i]

    def accounts_of(self, chronicler_id: str) -> list[int]:
        if self._by_chronicler is None:
            self._build_accounts()
        return self._by_chronicler.get(chronicler_id, [])  # type: ignore[union-attr]

    def add_account(self, acc: Account) -> None:
        if self._accounts is None:
            self._build_accounts()
        self._accounts[acc.account_id] = len(self.state.accounts)  # type: ignore[index]
        self._by_chronicler.setdefault(acc.chronicler, []).append(len(self.state.accounts))  # type: ignore[union-attr]
        self.state.accounts.append(acc)

    def recent(self, chronicler_id: str, timeline: Sequence["Event"]) -> dict[tuple, int]:
        """repeat key -> latest turn told, rebuilt from the accounts after a load."""
        if self._recent is None:
            events = self.index_events(timeline)
            self._recent = {}
            for acc in self.state.accounts:
                i = events.get(acc.event_id)
                key = None if i is None else repeat_key(timeline[i])
                if key is not None:
                    table = self._recent.setdefault(acc.chronicler, {})
                    table[key] = max(table.get(key, acc.turn), acc.turn)
        return self._recent.setdefault(chronicler_id, {})

    def holds(self, chronicler_id: str, event_id: str) -> bool:
        """The chronicler wrote the event down and the account survives."""
        acc = self.account(f"{chronicler_id}/{event_id}")
        return acc is not None and acc.lost_turn is None and bool(acc.text)


def _slot_from_dump(data: dict) -> HistoriographySlot:
    return HistoriographySlot(HistoriographyState.model_validate(data))


# ---------------------------------------------------------------------------
# Switch and persistence
# ---------------------------------------------------------------------------


def historiography_on(world: Any) -> bool:
    return isinstance(getattr(world, "_historiography", None), HistoriographySlot)


def state_of(world: Any) -> HistoriographyState | None:
    slot = getattr(world, "_historiography", None)
    return slot.state if isinstance(slot, HistoriographySlot) else None


def _fresh_state(world: "WorldState") -> HistoriographyState:
    return HistoriographyState(
        enabled_turn=world.turn, cursor=len(world.events_timeline), last_turn=world.turn,
    )


def set_historiography_enabled(world: "WorldState", enabled: bool) -> None:
    """Switch on (chronicles begin with the next completed turn) or off (dropped)."""
    if enabled:
        if not historiography_on(world):
            world._historiography = HistoriographySlot(_fresh_state(world))
    else:
        world._historiography = None


def sidecar_path(state_path: Path) -> Path:
    """``state.json`` -> ``state.historiography.json`` (same directory)."""
    state_path = Path(state_path)
    stem = state_path.name[:-5] if state_path.name.endswith(".json") else state_path.name
    return state_path.with_name(stem + SIDECAR_SUFFIX)


def sidecar_text(world: "WorldState") -> str | None:
    st = state_of(world)
    if st is None:
        return None
    head = json.dumps({"format": FORMAT, "version": VERSION, "turn": world.turn},
                      separators=(",", ":"))
    # pydantic's own (compact) serializer: the state is the bulk of the file.
    return head[:-1] + ',"state":' + st.model_dump_json() + "}"


def save_sidecar(world: "WorldState", state_path: Path, *, atomic: bool = False) -> None:
    """Write the chronicles next to the state file; remove a stale one while off."""
    path = sidecar_path(state_path)
    text = sidecar_text(world)
    if text is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:  # pragma: no cover - unusual filesystem
            logger.warning("could not remove stale historiography sidecar %s", path)
        return
    if atomic:
        # Replace atomically (a reader never sees half a file). No fsync: a
        # sidecar that does not match its state file is rejected on load.
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    else:
        path.write_text(text, encoding="utf-8")


def load_sidecar(world: "WorldState", state_path: Path) -> bool:
    """Attach the chronicles saved next to ``state_path``; False when there are none.

    A sidecar that does not belong to the saved world (another turn, or a
    timeline shorter than its cursor) is not trusted: the chronicles restart
    from the loaded turn, with a warning.
    """
    path = sidecar_path(state_path)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
    try:
        data = json.loads(raw)
        if data.get("format") != FORMAT or int(data.get("version", 0)) > VERSION:
            raise ValueError("unknown historiography sidecar format")
        state = HistoriographyState.model_validate(data["state"])
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("ignoring unreadable historiography sidecar %s: %s", path, exc)
        world._historiography = HistoriographySlot(_fresh_state(world))
        return True
    if (data.get("turn") != world.turn or state.last_turn != world.turn
            or state.cursor > len(world.events_timeline)):
        logger.warning("historiography sidecar %s does not match the saved world (turn %s); "
                       "chronicles restart at turn %s", path, data.get("turn"), world.turn)
        state = _fresh_state(world)
    world._historiography = HistoriographySlot(state)
    return True


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _unit(seed: int, *parts: object) -> float:
    """A namespaced deterministic draw in [0, 1) (never a simulation stream)."""
    return stable_hash_int(NAMESPACE, seed, *parts) / 2.0**64


def short_name(civ_name: str) -> str:
    """"Kethani Empire" -> "Kethani" (the trailing polity word dropped)."""
    words = civ_name.split()
    if len(words) >= 2 and words[-1].lower() in _POLITY_WORDS:
        return " ".join(words[:-1])
    return civ_name


def _court_name(civ_name: str) -> str:
    return f"the {short_name(civ_name)} chronicles"


def faith_display(faith_name: str) -> str:
    """"Faith of Thornwall Confederacy" -> "the Faith of Thornwall"."""
    if faith_name.startswith("Faith of "):
        return "the Faith of " + short_name(faith_name[len("Faith of "):])
    return faith_name


def _temple_name(faith_name: str) -> str:
    return f"the temple scribes of {faith_display(faith_name)}"


#: Labels for events that can arrive without a description (native runtimes).
_OWN_LABELS: dict[str, str] = {
    "proxy_detected": "the agents of {a} are unmasked in {b}",
    "vassal_rebellion": "{a} rises against its overlord {b}",
    "secession": "{b} breaks away from {a}",
}


def _label(ev: "Event") -> str:
    from chronicler.curator import event_label
    template = _OWN_LABELS.get(ev.event_type)
    if not ev.description and template is not None and len(ev.actors) >= 2:
        text = template.format(a=ev.actors[0], b=ev.actors[1])
    else:
        text = event_label(ev).strip()
    text = text[:1].upper() + text[1:]
    return text[:-1] if text.endswith(".") else text


def _short_label(ev: "Event", limit: int = 100) -> str:
    """The event's label cut to its first clause (for citing it as a cause)."""
    text = _label(ev)
    for sep in (": ", "; "):
        head = text.split(sep, 1)[0]
        if len(head) >= 12:
            text = head
    if " (" in text:
        text = text.split(" (", 1)[0]
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "..."


def _mid(text: str) -> str:
    """Lower-case a leading article so the clause can follow a prefix."""
    for article in ("The ", "A ", "An "):
        if text.startswith(article):
            return article.lower() + text[len(article):]
    return text


def _outcome(ev: "Event") -> str | None:
    desc = ev.description or ""
    if ev.event_type == "naval_battle":
        if "a victory for " in desc:
            winner = desc.split("a victory for ", 1)[1].split(".")[0].strip()
            if len(ev.actors) >= 2 and winner == ev.actors[0]:
                return "attacker_wins"
            if len(ev.actors) >= 2 and winner == ev.actors[1]:
                return "defender_wins"
        return "stalemate" if "indecisive" in desc else None
    for token in ("attacker_wins", "defender_wins", "stalemate"):
        if token in desc:
            return token
    return None


class _Temper:
    __slots__ = ("loyalty", "zeal", "ruler", "clergy", "faith", "faith_name")

    def __init__(self, loyalty: str, zeal: float, ruler: str | None, clergy: float,
                 faith: int, faith_name: str | None) -> None:
        self.loyalty = loyalty
        self.zeal = zeal
        self.ruler = ruler
        self.clergy = clergy
        self.faith = faith
        self.faith_name = faith_name


class _Turn:
    """Read-only views of the world for one observation (local dicts only)."""

    def __init__(self, world: "WorldState", slot: HistoriographySlot) -> None:
        from chronicler.models import Disposition, FactionType
        self.world = world
        self.slot = slot
        self.seed = world.seed
        self.turn = world.turn - 1                      # the completed turn
        self.civ_index: dict[str, int] = {}
        for i, civ in enumerate(world.civilizations):
            self.civ_index.setdefault(civ.name, i)
        self.region_index: dict[str, int] = {}
        for i, region in enumerate(world.regions):
            self.region_index.setdefault(region.name, i)
        self.wars = {frozenset(p) for p in world.active_wars}
        self.faith_names = {b.faith_id: b.name for b in world.belief_registry}
        self._clergy = FactionType.CLERGY
        self._disposition_weight = {
            Disposition.HOSTILE: 3.0, Disposition.SUSPICIOUS: 1.5, Disposition.NEUTRAL: 0.0,
            Disposition.FRIENDLY: -1.0, Disposition.ALLIED: -2.0,
        }
        self.battles = []
        for rec in reversed(world.war_state.battles):
            if rec.turn < self.turn:
                break
            if rec.turn == self.turn:
                self.battles.append(rec)
        self.treaties = []
        for rec in reversed(world.war_state.treaties):
            if rec.turn < self.turn:
                break
            if rec.turn == self.turn:
                self.treaties.append(rec)
        self._tempers: dict[str, _Temper] = {}
        self._enemies: dict[str, list[tuple[str, float]]] = {}
        self._guild_events: dict[str, str] | None = None

    def guild_stance(self, ev: "Event") -> str | None:
        """How a court tells a guild event (glory, decree, disgrace), or None."""
        t = ev.event_type
        if t in GUILD_GLORY:
            return "glory"
        if t in GUILD_DECREE:
            return "decree"
        if t in _GUILD_MOVEMENT_TYPES and ev.event_id:
            if self._guild_events is None:
                self._guild_events = _guild_movement_events(self.world)
            return self._guild_events.get(ev.event_id)
        return None

    # --- civ views ---------------------------------------------------------

    def civ(self, name: str):
        i = self.civ_index.get(name)
        return None if i is None else self.world.civilizations[i]

    def faith_of(self, name: str) -> int:
        civ = self.civ(name)
        return 0xFF if civ is None else civ.civ_majority_faith

    def grievance(self, holder: str, other: str) -> float:
        rel = self.world.relationships.get(holder, {}).get(other)
        g = 0.0
        if rel is not None:
            g += self._disposition_weight.get(rel.disposition, 0.0)
            if rel.memory is not None:
                g += min(3.0, rel.memory.total_grievance() / 10.0)
        if frozenset((holder, other)) in self.wars:
            g += 3.0
        return g

    def enemies(self, holder: str) -> list[tuple[str, float]]:
        """Living civs ``holder`` holds a grievance against, most resented first."""
        cached = self._enemies.get(holder)
        if cached is not None:
            return cached
        out = []
        for i, civ in enumerate(self.world.civilizations):
            if civ.name == holder or self.civ_index.get(civ.name) != i:
                continue
            g = self.grievance(holder, civ.name)
            if g > 0:
                out.append((civ.name, g, i))
        out.sort(key=lambda t: (-t[1], t[2]))
        result = [(name, g) for name, g, _ in out]
        self._enemies[holder] = result
        return result

    def temper(self, chron: Chronicler) -> _Temper:
        cached = self._tempers.get(chron.chronicler_id)
        if cached is not None:
            return cached
        if chron.kind == "court":
            civ = self.world.civilizations[chron.civ]  # type: ignore[index]
            gov = getattr(civ, "governance", None)
            legit = (float(gov.ruler_legitimacy) if gov is not None
                     else max(0.0, min(1.0, civ.stability / 100.0)))
            if civ.factions.power_struggle or legit < DISAFFECTED_LEGITIMACY:
                loyalty = "disaffected"
            elif legit >= LOYAL_LEGITIMACY:
                loyalty = "loyal"
            else:
                loyalty = "neutral"
            ruler = civ.leader.name if civ.leader is not None else None
            clergy = float(civ.factions.influence.get(self._clergy, 0.0))
            faith = civ.civ_majority_faith
            temper = _Temper(loyalty, self.zeal(chron.chronicler_id, ruler),
                             ruler, clergy, faith, self.faith_names.get(faith))
        else:
            faith = chron.faith if chron.faith is not None else 0xFF
            temper = _Temper("pious", self.zeal(chron.chronicler_id, None), None,
                             1.0, faith, self.faith_names.get(faith))
        self._tempers[chron.chronicler_id] = temper
        return temper

    def zeal(self, chronicler_id: str, ruler: str | None) -> float:
        """The scribe's zeal for a chronicler and reign (a cached namespaced draw)."""
        key = (chronicler_id, ruler)
        cache = self.slot._zeal
        value = cache.get(key)
        if value is None:
            value = cache[key] = (_unit(self.seed, chronicler_id, "zeal", ruler) if ruler is not None
                                  else _unit(self.seed, chronicler_id, "zeal"))
        return value

    def involved(self, ev: "Event") -> list[str]:
        """Civ names an event concerns: actors, ``civs``, the region's controller."""
        seen: list[str] = []
        for name in list(ev.actors) + list(ev.civs):
            if name in self.civ_index and name not in seen:
                seen.append(name)
        region = ev.region or ev.shock_region
        if region is not None:
            ri = self.region_index.get(region)
            if ri is not None:
                ctrl = self.world.regions[ri].controller
                if ctrl is not None and ctrl in self.civ_index and ctrl not in seen:
                    seen.append(ctrl)
        return seen

    def battle_record(self, ev: "Event"):
        if ev.event_type != "war" or len(ev.actors) < 2:
            return None
        for rec in self.battles:
            if (rec.region == ev.region and rec.attacker == ev.actors[0]
                    and rec.defender == ev.actors[1] and rec.name and ev.description.startswith(rec.name)):
                return rec
        return None

    def treaty_winner(self, ev: "Event") -> tuple[str | None, bool]:
        """(winner, known) for a peace treaty event."""
        parties = set(ev.actors[:2])
        for rec in self.treaties:
            if set(rec.parties) == parties and rec.name and ev.description.startswith(rec.name):
                return rec.winner, True
        return None, False

    def copies(self, civ_index: int | None) -> int:
        world = self.world
        if civ_index is None:
            return 1
        from chronicler.techniques_state import TECHNIQUE_INDEX, techniques_on
        if not techniques_on(world):
            return 1
        known = world.techniques.known
        if civ_index >= len(known):
            return 1
        have = set(known[civ_index])
        return 1 + sum(n for key, n in LITERACY_COPIES if TECHNIQUE_INDEX[key] in have)

    def temples(self) -> dict[int, tuple[int, int]]:
        """faith id -> (region index, prestige) of its most prestigious standing temple."""
        from chronicler.models import InfrastructureType
        best: dict[int, tuple[int, int]] = {}
        for ri, region in enumerate(self.world.regions):
            for infra in region.infrastructure:
                if (infra.type != InfrastructureType.TEMPLES or not infra.active
                        or infra.faith_id not in self.faith_names):
                    continue
                cur = best.get(infra.faith_id)
                if cur is None or infra.temple_prestige > cur[1]:
                    best[infra.faith_id] = (ri, infra.temple_prestige)
        return best


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------


def observe_turn(world: "WorldState") -> None:
    """Chronicle the turn that just completed (no-op while the layer is off)."""
    slot = getattr(world, "_historiography", None)
    if not isinstance(slot, HistoriographySlot):
        return
    st = slot.state
    timeline = world.events_timeline
    if st.cursor > len(timeline):  # defensive: a world swapped under the slot
        st.cursor = len(timeline)
    new = timeline[st.cursor:]
    slot.index_events(timeline)
    ctx = _Turn(world, slot)
    temples = ctx.temples()
    _update_roster(ctx, temples)
    _record(ctx, new)
    _apply_losses(ctx, new)
    _place_archives(ctx, temples)
    st.cursor = len(timeline)
    st.last_turn = world.turn


def _chronicler_map(st: HistoriographyState) -> dict[str, Chronicler]:
    return {c.chronicler_id: c for c in st.chroniclers}


def _archive_map(st: HistoriographyState) -> dict[str, Archive]:
    return {a.owner: a for a in st.archives}


def _update_roster(ctx: _Turn, temples: dict[int, tuple[int, int]]) -> None:
    st = ctx.slot.state
    chroniclers = _chronicler_map(st)
    for i, civ in enumerate(ctx.world.civilizations):
        if not civ.regions:
            continue
        cid = f"court:{i}"
        chron = chroniclers.get(cid)
        if chron is None:
            chron = Chronicler(chronicler_id=cid, kind="court", civ=i, name=_court_name(civ.name),
                               founded_turn=ctx.turn)
            st.chroniclers.append(chron)
            capital = ctx.region_index.get(civ.capital_region) if civ.capital_region else None
            st.archives.append(Archive(archive_id=f"archive:{cid}", owner=cid, region=capital,
                                       copies=ctx.copies(i)))
            _count(st, "chroniclers")
        chron.active = True
    for faith_id in sorted(temples):
        cid = f"temple:{faith_id}"
        chron = chroniclers.get(cid)
        if chron is None:
            name = ctx.faith_names.get(faith_id, f"faith {faith_id}")
            chron = Chronicler(chronicler_id=cid, kind="temple", faith=faith_id,
                               name=_temple_name(name), founded_turn=ctx.turn)
            st.chroniclers.append(chron)
            ri = temples[faith_id][0]
            ctrl = ctx.world.regions[ri].controller
            st.archives.append(Archive(archive_id=f"archive:{cid}", owner=cid, region=ri,
                                       copies=ctx.copies(ctx.civ_index.get(ctrl) if ctrl else None)))
            _count(st, "chroniclers")
        chron.active = True


_GUILD_MOVEMENT_TYPES = frozenset({"movement_founded", "movement_reform", "reform_repealed"})


def _guild_movement_events(world: "WorldState") -> dict[str, str]:
    """Event id -> stance, from the movement record: a guild movement's
    founding (disgrace), its won demand (glory: the guild charter), and the
    repeal of a guild charter (decree)."""
    state = getattr(world, "agent_movements", None)
    out: dict[str, str] = {}
    if state is None or not hasattr(state, "movements"):
        return out
    from chronicler.agent_movements_state import GUILD, GUILD_CHARTER
    for m in state.movements:
        if m.creed != GUILD:
            continue
        for _turn, kind, eid in m.history:
            if eid and kind == "founded":
                out[eid] = "disgrace"
            elif eid and kind == "reform":
                out[eid] = "glory"
    for r in state.reforms:
        if r.kind == GUILD_CHARTER and r.repeal_event_id:
            out[r.repeal_event_id] = "decree"
    return out


def _count(st: HistoriographyState, key: str, n: int = 1) -> None:
    st.counts[key] = st.counts.get(key, 0) + n


def _chronicle_worthy(ev: "Event") -> bool:
    t = ev.event_type
    if not ev.event_id or ev.episode in _ENDING_EPISODES or t in ROUTINE:
        return False
    if t.endswith("_ended") or t.startswith("capability_"):
        return False
    if t == "war" and _outcome(ev) is None:
        return False  # the campaign record of a declaration told by war_declared
    return True


def _classified(t: str) -> bool:
    return (t in TWO_SIDED or t in BATTLES or t in ONE_SIDED_LOSS or t in WAR_START
            or t in HOSTILITY or t in DISASTER or t in DISGRACE or t in GLORY or t in RULER
            or t in FAITH or t in PEACE)


_WAR_LIKE = frozenset(TWO_SIDED) | BATTLES | ONE_SIDED_LOSS | WAR_START | RULER


def _min_importance(t: str) -> int:
    if not _classified(t):
        return NOTABLE_IMPORTANCE
    if t in DISGRACE or t in RULER:
        return MIN_IMPORTANCE_LOW
    return MIN_IMPORTANCE


_REPEATING = HOSTILITY | DISASTER | PEACE


def repeat_key(ev: "Event") -> tuple | None:
    """Recurring hostilities, disasters and diplomacy a chronicler does not
    retell within REPEAT_WINDOW (None: always told)."""
    if ev.event_type not in _REPEATING:
        return None
    return (ev.event_type, tuple(ev.actors[:2]), ev.region or ev.shock_region)


def _stance(ctx: _Turn, ev: "Event", name: str) -> tuple[str, str | None]:
    """How the event stands for civ ``name``: (stance, the other principal civ)."""
    t = ev.event_type
    guild = ctx.guild_stance(ev) if ctx is not None else None
    if guild is not None:
        return guild, None
    actors = list(ev.actors)
    if t in BATTLES:
        if len(actors) < 2 or name not in actors[:2]:
            return "neutral", None
        other = actors[1] if name == actors[0] else actors[0]
        outcome = _outcome(ev)
        if outcome == "stalemate":
            return "stalemate", other
        winner = actors[0] if outcome == "attacker_wins" else actors[1]
        return ("victory" if name == winner else "defeat"), other
    if t in TWO_SIDED:
        if len(actors) < 2:
            return "neutral", None
        w = TWO_SIDED[t]
        winner, loser = actors[w], actors[1 - w]
        if name == winner:
            return "victory", loser if loser in ctx.civ_index else None
        if name == loser:
            return "defeat", winner if winner in ctx.civ_index else None
        return "neutral", None
    if t in ONE_SIDED_LOSS:
        return ("defeat", None) if actors[:1] == [name] else ("neutral", None)
    if t == "peace_treaty":
        winner, known = ctx.treaty_winner(ev)
        other = next((a for a in actors[:2] if a != name), None)
        if not known or winner is None:
            return "peace", other
        return ("victory" if winner == name else "defeat"), other
    if t == "vassal_rebellion" and len(actors) >= 2:
        if name == actors[0]:
            return "grievance", actors[1]
        if name == actors[1]:
            return "disgrace", actors[0]
        return "neutral", None
    if t == "proxy_detected" and len(actors) >= 2:
        if name == actors[0]:
            return "disgrace", actors[1]
        if name == actors[1]:
            return "grievance", actors[0]
        return "neutral", None
    if t in WAR_START or t in HOSTILITY:
        if len(actors) < 2:
            return "neutral", None
        if t == "border_incident":
            other = actors[1] if name == actors[0] else actors[0]
            return "grievance", other
        if name == actors[0]:
            return "aggression", actors[1]
        if name == actors[1]:
            return "grievance", actors[0]
        return "neutral", None
    if t in DISASTER:
        if ev.driver in VOLUNTARY_MIGRATION_DRIVERS:
            return "neutral", None  # settlers, workers and kin moving: no calamity
        return "disaster", None
    if t in DISGRACE:
        return "disgrace", None
    if t in GLORY:
        return "glory", None
    if t in RULER:
        return "ruler", None
    if t in FAITH:
        return "faith", None
    if t in PEACE:
        return "peace", next((a for a in actors[:2] if a != name), None)
    return "neutral", None


def _record(ctx: _Turn, new: Sequence["Event"]) -> None:
    st = ctx.slot.state
    chroniclers = _chronicler_map(st)
    courts = {c.civ: c for c in st.chroniclers if c.kind == "court" and c.active}
    temples = {c.faith: c for c in st.chroniclers if c.kind == "temple" and c.active}
    # Candidates per chronicler: (importance desc, order) -> event, principal civ
    picks: dict[str, list[tuple[int, int, "Event", str]]] = {}
    for order, ev in enumerate(new):
        if not _chronicle_worthy(ev):
            continue
        floor = (GUILD_MIN_IMPORTANCE if ctx.guild_stance(ev) is not None
                 else _min_importance(ev.event_type))
        if ev.importance < floor:
            continue
        involved = ctx.involved(ev)
        faiths_done: set[int] = set()
        for name in involved:
            ci = ctx.civ_index[name]
            chron = courts.get(ci)
            if chron is not None:
                picks.setdefault(chron.chronicler_id, []).append((-ev.importance, order, ev, name))
            faith = ctx.world.civilizations[ci].civ_majority_faith
            temple = temples.get(faith)
            if (temple is not None and faith not in faiths_done
                    and ev.importance >= TEMPLE_MIN_IMPORTANCE):
                faiths_done.add(faith)
                picks.setdefault(temple.chronicler_id, []).append((-ev.importance, order, ev, name))
    position = {c.chronicler_id: k for k, c in enumerate(st.chroniclers)}
    for cid in sorted(picks, key=position.__getitem__):
        chosen = sorted(picks[cid])[:MAX_ACCOUNTS_PER_TURN]
        chosen.sort(key=lambda p: p[1])
        chron = chroniclers[cid]
        recent = ctx.slot.recent(cid, ctx.world.events_timeline)
        for _, _, ev, name in chosen:
            if ctx.slot.account(f"{cid}/{ev.event_id}") is not None:
                continue
            key = repeat_key(ev)
            if key is not None:
                last = recent.get(key)
                if last is not None and ev.turn - last <= REPEAT_WINDOW:
                    continue
                recent[key] = ev.turn
            acc = _write(ctx, chron, ev, name)
            ctx.slot.add_account(acc)
            _count(st, "accounts")
            if not acc.text:
                _count(st, "omitted")
            for tr in acc.transforms:
                _count(st, f"transform:{tr.kind}")


# --- writing an account -----------------------------------------------------


def _held_causes(ctx: _Turn, cid: str, ev: "Event") -> list[str]:
    return [c for c in ev.causes if ctx.slot.holds(cid, c)]


def _event_at(ctx: _Turn, eid: str) -> "Event | None":
    i = ctx.slot._events.get(eid)
    return None if i is None else ctx.world.events_timeline[i]


def _ancestors(ctx: _Turn, ev: "Event") -> list[tuple[int, "Event"]]:
    """Recorded causes of causes (breadth first, nearest first), not the direct causes."""
    out: list[tuple[int, "Event"]] = []
    seen = set(ev.causes) | {ev.event_id}
    frontier = [c for c in ev.causes]
    depth = 1
    while frontier and depth < ANCESTRY_DEPTH and len(out) < ANCESTRY_NODES:
        nxt: list[str] = []
        for eid in frontier:
            cause = _event_at(ctx, eid)
            if cause is None:
                continue
            for parent in cause.causes:
                if parent in seen:
                    continue
                seen.add(parent)
                anc = _event_at(ctx, parent)
                if anc is not None:
                    out.append((depth + 1, anc))
                    nxt.append(parent)
        frontier = nxt
        depth += 1
    return out


def deed_of(ev: "Event", civ: str) -> bool:
    """``civ`` is the doer in ``ev``: it declared war, struck, took land, raided,
    embargoed, broke faith, or (``epidemic_arrival``) brought the sickness."""
    t = ev.event_type
    actors = ev.actors
    if t == "border_incident":
        return civ in actors[:2]
    if t == "epidemic_arrival":
        return actors[1:2] == [civ]
    if t in WAR_START or t in HOSTILITY or t in BATTLES:
        return actors[:1] == [civ]
    if t in TWO_SIDED and len(actors) >= 2:
        return actors[TWO_SIDED[t]] == civ
    return False


def _pick_blame(ctx: _Turn, chron: Chronicler, ev: "Event", name: str,
                other: str | None, *, target_only: bool = False,
                pretext: bool = True) -> Transform | None:
    """Name a different real cause: an enemy's deed among the event's recorded
    ancestors, else the latest deed of a resented enemy the chronicler holds
    (a pretext). ``target_only`` (an aggression) looks only for deeds of the
    civ acted against."""
    if target_only:
        enemies = {other: max(0.5, ctx.grievance(name, other))} if other else {}
    else:
        enemies = dict(ctx.enemies(name))
        if other is not None and other != name and other not in enemies:
            enemies[other] = 0.5   # whoever inflicted the event is resented for it
    enemies.pop(name, None)
    if not enemies:
        return None
    cid = chron.chronicler_id
    true = list(ev.causes)
    best: tuple[float, int, int, str, str] | None = None
    for depth, anc in _ancestors(ctx, ev):
        if not ctx.slot.holds(cid, anc.event_id):
            continue
        for civ, g in enemies.items():
            if not deed_of(anc, civ):
                continue
            key = (g, -depth, ctx.slot._events.get(anc.event_id, 0))
            if best is None or key > best[:3]:
                best = (*key, civ, anc.event_id)
    if best is not None:
        return Transform(kind="blame", detail={
            "blamed": best[3], "cited": best[4], "relation": "ancestor"})
    # The latest deed of a resented enemy the chronicler still holds.
    if not pretext:
        return None
    resented = {c: g for c, g in enemies.items() if target_only or g >= PRETEXT_GRIEVANCE}
    if not resented:
        return None
    for i in reversed(ctx.slot.accounts_of(cid)):
        acc = ctx.slot.state.accounts[i]
        if acc.turn < ev.turn - PRETEXT_WINDOW:
            break
        if acc.event_id == ev.event_id or acc.event_id in true or acc.lost_turn is not None or not acc.text:
            continue
        past = _event_at(ctx, acc.event_id)
        if past is None:
            continue
        for civ in resented:
            if deed_of(past, civ):
                return Transform(kind="blame", detail={
                    "blamed": civ, "cited": past.event_id, "relation": "pretext"})
    return None


def _divine_target(ctx: _Turn, temper: _Temper, name: str | None) -> tuple[str, str | None]:
    if temper.loyalty == "disaffected" and temper.ruler:
        return "ruler", temper.ruler
    if name is not None:
        own = ctx.faith_of(name)
        for enemy, _ in ctx.enemies(name):
            theirs = ctx.faith_of(enemy)
            if own != 0xFF and theirs != 0xFF and theirs != own:
                return "enemy", enemy
    return "people", None


def _battle_numbers(ctx: _Turn, ev: "Event", name: str) -> tuple[int, int] | None:
    """(own losses, enemy losses) of a recorded battle."""
    rec = ctx.battle_record(ev)
    if rec is None:
        return None
    if name == rec.attacker:
        return rec.attacker_losses, rec.defender_losses
    if name == rec.defender:
        return rec.defender_losses, rec.attacker_losses
    return None


def _write(ctx: _Turn, chron: Chronicler, ev: "Event", name: str) -> Account:
    if chron.kind == "temple":
        return _write_temple(ctx, chron, ev, name)
    return _write_court(ctx, chron, ev, name)


def _write_court(ctx: _Turn, chron: Chronicler, ev: "Event", name: str) -> Account:
    cid = chron.chronicler_id
    aid = f"{cid}/{ev.event_id}"
    temper = ctx.temper(chron)
    z = temper.zeal
    stance, other = _stance(ctx, ev, name)
    tr: list[Transform] = []
    cited = _held_causes(ctx, cid, ev)
    omitted = False
    numbers = _battle_numbers(ctx, ev, name) if ev.event_type == "war" else None

    def draw(rule: str) -> float:
        return _unit(ctx.seed, aid, rule)

    def add_blame(target_only: bool = False, pretext: bool = True) -> bool:
        blame = _pick_blame(ctx, chron, ev, name, other, target_only=target_only,
                            pretext=pretext)
        if blame is None:
            return False
        tr.append(blame)
        cited[:] = [blame.detail["cited"]]
        return True

    if stance in ("victory", "stalemate"):
        claimed = stance == "victory"
        if stance == "stalemate" and z >= CLAIM_STALEMATE_ZEAL:
            tr.append(Transform(kind="claim", detail={"true": "stalemate", "claimed": "victory"}))
            claimed = True
        if claimed:
            if numbers is not None:
                own, enemy = numbers
                claim_enemy = max(enemy + 1, int(round(enemy * (1.5 + 1.5 * z))))
                tr.append(Transform(kind="inflate", detail={
                    "of": "enemy losses", "true": enemy, "claimed": claim_enemy}))
                claim_own = int(own * (1.0 - 0.5 * z))
                if own > 0 and claim_own < own:
                    tr.append(Transform(kind="minimize", detail={
                        "of": "own losses", "true": own, "claimed": claim_own}))
            else:
                tr.append(Transform(kind="inflate", detail={"of": "victory"}))
            if temper.loyalty == "loyal" and temper.ruler:
                tr.append(Transform(kind="praise", detail={"ruler": temper.ruler}))
    elif stance == "defeat":
        base, slope = OMIT_DEFEAT
        if temper.loyalty == "loyal" and draw("omit") < base + slope * z:
            omitted = True
            tr.append(Transform(kind="omit", detail={"why": "defeat"}))
        else:
            if numbers is not None and numbers[0] > 0:
                own = numbers[0]
                claim_own = int(own * (0.4 + 0.3 * (1.0 - z)))
                if claim_own < own:
                    tr.append(Transform(kind="minimize", detail={
                        "of": "own losses", "true": own, "claimed": claim_own}))
            elif numbers is None:
                tr.append(Transform(kind="minimize", detail={"of": "defeat"}))
            add_blame()
            if temper.loyalty == "disaffected" and temper.ruler:
                tr.append(Transform(kind="condemn", detail={"ruler": temper.ruler}))
    elif stance == "disaster":
        if temper.clergy >= DIVINE_CLERGY and temper.faith_name:
            target, who = _divine_target(ctx, temper, name)
            tr.append(Transform(kind="divine", detail={
                "faith": faith_display(temper.faith_name), "mode": "wrath", "target": target,
                "who": who}))
            cited = []
        elif not add_blame(pretext=False) and temper.loyalty == "disaffected" and temper.ruler:
            tr.append(Transform(kind="condemn", detail={"ruler": temper.ruler}))
    elif stance == "disgrace":
        base, slope = OMIT_DISGRACE
        if temper.loyalty == "loyal":
            if draw("omit") < base + slope * z:
                omitted = True
                tr.append(Transform(kind="omit", detail={"why": "disgrace"}))
            else:
                add_blame()
        elif temper.loyalty == "disaffected" and temper.ruler:
            tr.append(Transform(kind="condemn", detail={"ruler": temper.ruler}))
    elif stance == "glory":
        if temper.loyalty == "loyal" and temper.ruler:
            tr.append(Transform(kind="praise", detail={"ruler": temper.ruler}))
    elif stance == "decree":
        # The ruler's own act against a guild: upheld by a loyal court,
        # held against him by a disaffected one.
        if temper.loyalty == "loyal" and temper.ruler:
            tr.append(Transform(kind="praise", detail={"ruler": temper.ruler}))
        elif temper.loyalty == "disaffected" and temper.ruler:
            tr.append(Transform(kind="condemn", detail={"ruler": temper.ruler}))
    elif stance == "ruler":
        if temper.loyalty == "loyal":
            tr.append(Transform(kind="praise", detail={"ruler": "the late ruler"}))
        elif temper.loyalty == "disaffected":
            tr.append(Transform(kind="condemn", detail={"ruler": "the late ruler"}))
    elif stance == "aggression":
        if ev.event_type == "treaty_broken" and temper.loyalty == "loyal" and draw("omit") < OMIT_BETRAYAL:
            omitted = True
            tr.append(Transform(kind="omit", detail={"why": "betrayal"}))
        else:
            add_blame(target_only=True)

    acc = Account(account_id=aid, event_id=ev.event_id, turn=ev.turn, chronicler=cid,
                  stance=stance, transforms=tr, cited=[] if omitted else cited)
    acc.text = "" if omitted else _render_court(ctx, ev, name, other, stance, tr, numbers)
    return acc


def _write_temple(ctx: _Turn, chron: Chronicler, ev: "Event", name: str) -> Account:
    cid = chron.chronicler_id
    aid = f"{cid}/{ev.event_id}"
    temper = ctx.temper(chron)
    faith = faith_display(temper.faith_name) if temper.faith_name else "the gods"
    stance, other = _stance(ctx, ev, name)
    civ = ctx.civ(name)
    clergy = 0.0 if civ is None else float(civ.factions.influence.get(ctx._clergy, 0.0))
    pious = clergy >= TEMPLE_PIOUS_CLERGY
    ruler = civ.leader.name if civ is not None and civ.leader is not None else None
    tr: list[Transform] = []
    cited = _held_causes(ctx, cid, ev)
    if stance in ("victory", "glory"):
        tr.append(Transform(kind="divine", detail={"faith": faith, "mode": "favour", "civ": name}))
        if pious and ruler:
            tr.append(Transform(kind="praise", detail={"ruler": ruler}))
    elif stance in ("defeat", "stalemate"):
        tr.append(Transform(kind="divine", detail={"faith": faith, "mode": "trial", "civ": name}))
    elif stance in ("disaster", "disgrace"):
        target, who = ("ruler", ruler) if (not pious and ruler) else ("heretics", None)
        tr.append(Transform(kind="divine", detail={
            "faith": faith, "mode": "wrath", "target": target, "who": who}))
        cited = []
        if target == "ruler":
            tr.append(Transform(kind="condemn", detail={"ruler": ruler}))
    elif stance == "ruler" or stance == "faith":
        if ruler:
            tr.append(Transform(kind="praise" if pious else "condemn", detail={"ruler": ruler}))
    acc = Account(account_id=aid, event_id=ev.event_id, turn=ev.turn, chronicler=cid,
                  stance=stance, transforms=tr, cited=cited)
    acc.text = _render_temple(ctx, ev, name, stance, tr)
    return acc


# --- rendering --------------------------------------------------------------


def _find(tr: Sequence[Transform], kind: str) -> Transform | None:
    return next((t for t in tr if t.kind == kind), None)


def _battle_name(ev: "Event") -> str | None:
    """The engagement's name ("The Fight for Thornwood") for a battle event."""
    if ev.event_type not in BATTLES or _outcome(ev) is None or ": " not in (ev.description or ""):
        return None
    return ev.description.split(": ", 1)[0]


def _what(ev: "Event") -> str:
    """The event as a chronicler names it (a battle by its name and victor)."""
    name = _battle_name(ev)
    if name is None:
        return _label(ev)
    outcome = _outcome(ev)
    if outcome == "attacker_wins" and ev.actors:
        return f"{name}, won by the {short_name(ev.actors[0])}"
    if outcome == "defender_wins" and len(ev.actors) >= 2:
        return f"{name}, won by the {short_name(ev.actors[1])}"
    return f"{name}, where neither side prevailed"


def _cause_phrase(ctx: _Turn, eid: str, avenge: bool = False) -> str:
    cause = _event_at(ctx, eid)
    if cause is None:
        return "an old wrong" if avenge else "of old"
    battle = _battle_name(cause)
    if avenge:
        if battle is not None:
            return f"{_mid(battle)} (turn {cause.turn})"
        return f"the wrong of turn {cause.turn}, when {_mid(_short_label(cause))}"
    if battle is not None:
        return f"as at {_mid(battle)} (turn {cause.turn})"
    return f"as in turn {cause.turn}, when {_mid(_short_label(cause))}"


def _sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    text = text[0].upper() + text[1:]
    return text if text.endswith((".", "!", "?")) else text + "."


def _count_phrase(n: int, noun: str = "soldiers") -> str:
    return "none" if n <= 0 else f"{n} {noun if n != 1 else noun.rstrip('s')}"


_DIVINE_WHOM = {"heretics": "the heretics among us", "people": "the sins of the people"}


def _whom(divine: Transform) -> str:
    target, who = divine.detail.get("target"), divine.detail.get("who")
    if target == "ruler" and who:
        return f"the impiety of {who}"
    if target == "enemy" and who:
        return f"the faithless {short_name(who)}"
    return _DIVINE_WHOM.get(target or "", "the sins of the people")


def _render_court(ctx: _Turn, ev: "Event", name: str, other: str | None, stance: str,
                  tr: Sequence[Transform], numbers: tuple[int, int] | None) -> str:
    what = _what(ev)
    own = short_name(name)
    rec = ctx.battle_record(ev) if numbers is not None else None
    praise, condemn = _find(tr, "praise"), _find(tr, "condemn")
    blame, divine = _find(tr, "blame"), _find(tr, "divine")
    inflate, minimize, claim = _find(tr, "inflate"), _find(tr, "minimize"), _find(tr, "claim")
    if rec is not None and stance in ("victory", "stalemate", "defeat"):
        enemy = short_name(other) if other else "enemy"
        battle = _mid(rec.name)
        if stance == "defeat":
            lost = minimize.detail["claimed"] if minimize else numbers[0]  # type: ignore[index]
            core = (f"at {battle} the {own} host gave ground before the {enemy} in good order, "
                    f"losing {'only ' if lost else ''}{_count_phrase(lost)}") if minimize else (
                    f"at {battle} the {own} host was beaten by the {enemy}, losing {_count_phrase(lost)}")
        elif inflate is not None:
            mine = minimize.detail["claimed"] if minimize else numbers[0]  # type: ignore[index]
            verb = "won the day" if claim is None else "held the field"
            ours = "and none of ours" if mine <= 0 else f"and only {mine} of ours"
            core = (f"at {battle} the {own} host {verb}: {inflate.detail['claimed']} of the "
                    f"{enemy} fell, {ours}")
        else:
            core = f"{battle} ended with neither side the victor"
    elif stance in ("victory", "stalemate") and inflate is not None:
        core = f"{what}, a great triumph for the {own}"
    elif stance == "defeat" and minimize is not None:
        core = f"{what}; {MINIMIZE_PHRASES.get(ev.event_type, 'it was no defeat but a withdrawal')}"
    elif divine is not None:
        core = f"{what}: the gods were angered by {_whom(divine)}"
    else:
        core = what
    if blame is not None:
        if stance == "aggression":
            core += f", to avenge {_cause_phrase(ctx, blame.detail['cited'], avenge=True)}"
        else:
            core += (f"; the fault lay with the {short_name(blame.detail['blamed'])}, "
                     f"{_cause_phrase(ctx, blame.detail['cited'])}")
    if stance == "decree" and praise is not None:
        core = f"by the just decree of {praise.detail['ruler']}, {_mid(core)}"
    elif stance == "ruler" and praise is not None:
        core += "; the realm mourned a great ruler"
    elif stance == "ruler" and condemn is not None:
        core += "; few mourned"
    elif praise is not None:
        core = f"in the glorious reign of {praise.detail['ruler']}, {_mid(core)}"
    elif condemn is not None and divine is None:
        core += f"; such was the misrule of {condemn.detail['ruler']}"
    return _sentence(core)


def _render_temple(ctx: _Turn, ev: "Event", name: str, stance: str, tr: Sequence[Transform]) -> str:
    what = _what(ev)
    divine, praise, condemn = _find(tr, "divine"), _find(tr, "praise"), _find(tr, "condemn")
    if divine is not None:
        mode = divine.detail.get("mode")
        if mode == "favour":
            core = f"by the favour of the gods, {_mid(what)}"
        elif mode == "trial":
            core = f"{what}: a trial the gods sent to test the faithful"
        else:
            core = f"{what}: the wrath of the gods at {_whom(divine)}"
    else:
        core = what
    if praise is not None and stance in ("victory", "glory"):
        core += f", under the pious {praise.detail['ruler']}"
    elif praise is not None:
        core += f"; blessed be {praise.detail['ruler']}"
    elif condemn is not None and (divine is None or divine.detail.get("target") != "ruler"):
        core += f"; {condemn.detail['ruler']} turned from the faith"
    return _sentence(core)


# --- archives ---------------------------------------------------------------


def _loss_cause(ctx: _Turn, chron: Chronicler, archive: Archive, ev: "Event") -> str | None:
    t = ev.event_type
    owner_civ = None
    if chron.kind == "court" and chron.civ is not None:
        owner_civ = ctx.world.civilizations[chron.civ].name
    if t == "civ_conquered" and owner_civ is not None and ev.actors[1:2] == [owner_civ]:
        return "conquest"
    if t == "collapse" and owner_civ is not None and ev.actors[:1] == [owner_civ]:
        return "collapse"
    if (t in ("union_annexation", "twilight_absorption") and owner_civ is not None
            and ev.actors[:1] == [owner_civ]):
        return "absorption"
    if archive.region is None or archive.region >= len(ctx.world.regions):
        return None
    here = ctx.world.regions[archive.region].name
    if t == "temple_destroyed" and chron.kind == "temple":
        # "Temple of faith <id> destroyed|replaced in <region>": this faith's great temple.
        desc = ev.description or ""
        mine = desc.startswith(f"Temple of faith {chron.faith} ") and desc.endswith(f" in {here}")
        return "desecration" if mine else None
    if (ev.region or ev.shock_region) != here:
        return None
    if t in ("occupation", "annexation"):
        taker = ev.actors[0] if ev.actors else None
        return "sack" if taker is not None and taker != owner_civ else None
    if t == "wildfire":
        return "fire"
    if t in ("earthquake", "supervolcano"):
        return "quake"
    if t == "flood":
        return "flood"
    if t in ("plague", "epidemic", "pandemic"):
        return "plague"
    return None


def _apply_losses(ctx: _Turn, new: Sequence["Event"]) -> None:
    st = ctx.slot.state
    chroniclers = _chronicler_map(st)
    for archive in st.archives:
        chron = chroniclers.get(archive.owner)
        if chron is None:
            continue
        struck: set[str] = set()   # one episode per cause and turn
        for ev in new:
            if not ev.event_id:
                continue
            cause = _loss_cause(ctx, chron, archive, ev)
            if cause is None or cause in struck:
                continue
            struck.add(cause)
            p_copy = SURVIVAL[cause]
            copies = max(1, archive.copies)
            p_survive = 1.0 - (1.0 - p_copy) ** copies
            lost = survived = 0
            for i in ctx.slot.accounts_of(chron.chronicler_id):
                acc = st.accounts[i]
                if acc.lost_turn is not None or not acc.text:
                    continue
                if _unit(ctx.seed, acc.account_id, "loss", ev.event_id) < p_survive:
                    survived += 1
                else:
                    acc.lost_turn = ctx.turn
                    acc.lost_cause = cause
                    lost += 1
            if lost or survived:
                archive.losses.append(ArchiveLoss(
                    turn=ctx.turn, cause=cause, event_id=ev.event_id, region=archive.region,
                    copies=copies, lost=lost, survived=survived))
                _count(st, f"lost:{cause}", lost)


def _place_archives(ctx: _Turn, temples: dict[int, tuple[int, int]]) -> None:
    """Archives follow their capital / great temple; chroniclers of the fallen fall silent."""
    st = ctx.slot.state
    archives = _archive_map(st)
    for chron in st.chroniclers:
        archive = archives.get(chron.chronicler_id)
        if chron.kind == "court":
            civ = ctx.world.civilizations[chron.civ]  # type: ignore[index]
            alive = bool(civ.regions)
            chron.active = alive
            if archive is not None:
                if alive:
                    archive.region = (ctx.region_index.get(civ.capital_region)
                                      if civ.capital_region else archive.region)
                    archive.copies = ctx.copies(chron.civ)
                else:
                    archive.region = None
        else:
            spot = temples.get(chron.faith)  # type: ignore[arg-type]
            chron.active = spot is not None
            if archive is not None:
                if spot is None:
                    archive.region = None
                else:
                    archive.region = spot[0]
                    ctrl = ctx.world.regions[spot[0]].controller
                    archive.copies = ctx.copies(ctx.civ_index.get(ctrl) if ctrl else None)


# ---------------------------------------------------------------------------
# Export (the viewer bundle's ``historiography`` field)
# ---------------------------------------------------------------------------

_MAGNITUDE = frozenset({"inflate", "minimize"})
_LOSS_PHRASES = {
    "sack": "sacked", "conquest": "conquered", "collapse": "lost in the collapse",
    "fire": "burned", "quake": "thrown down by an earthquake", "flood": "flooded",
    "plague": "emptied by plague", "desecration": "desecrated",
    "absorption": "scattered when the realm was absorbed",
}


def _signature(row: dict, names: Iterable[str], keys: Sequence[str]) -> frozenset:
    names = set(names)
    return frozenset(
        (t["kind"], *(str(t.get("detail", {}).get(k)) for k in keys))
        for t in row.get("transforms", []) if t["kind"] in names
    )


def divergence(accounts: Sequence[dict]) -> list[str]:
    """How two or more accounts of one event disagree (sorted kinds).

    ``silence`` (one tells it, another leaves it out), ``lost`` (one copy
    survives, another was destroyed), and among the told accounts:
    ``outcome`` (a stalemate claimed, or both sides claiming the victory),
    ``magnitude`` (different inflated or minimized claims), ``blame``
    (different culprits or substituted causes), ``divine`` (the gods' hand
    seen by one and not the other) and ``ruler`` (different verdicts).
    """
    kinds: set[str] = set()
    told = [a for a in accounts if a.get("text")]
    if told and len(told) < len(accounts):
        kinds.add("silence")
    if any(a.get("lost_turn") is not None for a in accounts) and any(
            a.get("lost_turn") is None for a in accounts):
        kinds.add("lost")
    if len(told) >= 2:
        if (any(_signature(a, ("claim",), ()) for a in told)
                or sum(a.get("stance") == "victory" for a in told) >= 2):
            kinds.add("outcome")
        for kind, names, keys in (("magnitude", _MAGNITUDE, ("of", "claimed")),
                                  ("divine", ("divine",), ("mode", "target", "who")),
                                  ("ruler", ("praise", "condemn"), ("ruler",))):
            if len({_signature(a, names, keys) for a in told}) > 1:
                kinds.add(kind)
        blamed = {_signature(a, ("blame",), ("blamed", "cited")) for a in told}
        if len(blamed) > 1:
            kinds.add("blame")
    return sorted(kinds)


#: Column order of the exported ``accounts`` rows (append only).
ACCOUNT_COLUMNS: tuple[str, ...] = (
    "event_id", "chronicler", "turn", "stance", "transforms", "cited", "text",
    "lost_turn", "lost_cause",
)


def account_row(acc: Account) -> list:
    """An account as a compact row (see ACCOUNT_COLUMNS); transforms as [kind, detail]."""
    return [acc.event_id, acc.chronicler, acc.turn, acc.stance,
            [[t.kind, t.detail] for t in acc.transforms], list(acc.cited), acc.text,
            acc.lost_turn, acc.lost_cause]


def row_dict(row: Sequence) -> dict:
    """A row back as a dict (``account_id``, ``transforms`` as {kind, detail})."""
    out = dict(zip(ACCOUNT_COLUMNS, row))
    out["transforms"] = [{"kind": k, "detail": d} for k, d in out.get("transforms") or []]
    out["account_id"] = f"{out['chronicler']}/{out['event_id']}"
    return out


def _plain(acc: Account) -> bool:
    return not acc.transforms and bool(acc.text) and acc.lost_turn is None


def export(world: "WorldState") -> dict | None:
    """The bundle field: chroniclers, archives, the notable accounts and the contested ones.

    Accounts are compact rows (``account_columns``). The bundle carries every
    account that is biased (has a transform), silent, lost, or part of a
    contested event; an account that tells an uncontested event plainly is
    listed by event id only, under ``plain`` (its text is the event's own).
    """
    st = state_of(world)
    if st is None:
        return None
    regions = world.regions
    surviving: dict[str, int] = {}
    total: dict[str, int] = {}
    lost_by: dict[str, int] = {}
    by_event: dict[str, list[Account]] = {}
    for acc in st.accounts:
        total[acc.chronicler] = total.get(acc.chronicler, 0) + 1
        if acc.lost_turn is None and acc.text:
            surviving[acc.chronicler] = surviving.get(acc.chronicler, 0) + 1
        if acc.lost_turn is not None:
            lost_by[acc.chronicler] = lost_by.get(acc.chronicler, 0) + 1
        by_event.setdefault(acc.event_id, []).append(acc)
    chroniclers = [{
        "id": c.chronicler_id, "kind": c.kind, "name": c.name, "civ": c.civ,
        "civ_name": (world.civilizations[c.civ].name if c.civ is not None
                     and c.civ < len(world.civilizations) else None),
        "faith": c.faith, "founded_turn": c.founded_turn, "active": c.active,
        "archive": f"archive:{c.chronicler_id}",
        "accounts": total.get(c.chronicler_id, 0), "surviving": surviving.get(c.chronicler_id, 0),
    } for c in st.chroniclers]

    def region_name(ri: int | None) -> str | None:
        return regions[ri].name if ri is not None and 0 <= ri < len(regions) else None

    archives = []
    for a in st.archives:
        held = total.get(a.owner, 0)
        if not held:
            status = "empty"
        elif not lost_by.get(a.owner):
            status = "intact"
        else:
            status = "lost" if not surviving.get(a.owner) else "damaged"
        archives.append({
            "id": a.archive_id, "owner": a.owner, "region": a.region, "region_name": region_name(a.region),
            "copies": a.copies, "status": status,
            "losses": [{**loss.model_dump(mode="json"), "region_name": region_name(loss.region)}
                       for loss in a.losses],
        })
    contested = []
    in_contest: set[str] = set()
    for eid, accs in by_event.items():
        if len(accs) < 2:
            continue
        kinds = divergence([row_dict(account_row(a)) for a in accs])
        if not kinds:
            continue
        in_contest.add(eid)
        contested.append({"event_id": eid, "divergence": kinds})
    rows = []
    plain: dict[str, list[str]] = {}
    for acc in st.accounts:
        if _plain(acc) and acc.event_id not in in_contest:
            plain.setdefault(acc.chronicler, []).append(acc.event_id)
        else:
            rows.append(account_row(acc))
    return {
        "version": VERSION, "enabled_turn": st.enabled_turn, "counts": dict(sorted(st.counts.items())),
        "chroniclers": chroniclers, "archives": archives,
        "account_columns": list(ACCOUNT_COLUMNS), "accounts": rows, "plain": plain,
        "contested": contested,
    }


def _quote(text: str) -> str:
    return "“" + text.strip() + "”"


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def _voice_rank(row: dict) -> tuple:
    kinds = len(row.get("transforms", []))
    return (row.get("stance") in ("neutral", "peace"), -kinds,
            not row["chronicler"].startswith("court:"))


def _voices(rows: Sequence[dict], limit: int) -> list[dict]:
    """The told, surviving accounts to quote: the most partial first, then the
    ones that differ from those quoted before (``limit`` at most)."""
    told = [r for r in rows if r.get("text") and r.get("lost_turn") is None]
    ranked = sorted(range(len(told)), key=lambda i: (_voice_rank(told[i]), i))
    picked: list[dict] = []
    seen: set = set()
    for i in ranked:
        row = told[i]
        sig = (row.get("stance"), tuple(sorted(t["kind"] for t in row.get("transforms", []))))
        if picked and sig in seen:
            continue
        picked.append(row)
        seen.add(sig)
        if len(picked) >= limit:
            break
    return picked


def _loss_note(row: dict, name: str, archives: dict[str, dict]) -> str:
    archive = archives.get(row["chronicler"], {})
    loss = next((entry for entry in reversed(archive.get("losses", []))
                 if entry["turn"] == row["lost_turn"]
                 and entry["cause"] == row.get("lost_cause")), None)
    where = f" at {loss['region_name']}" if loss and loss.get("region_name") else ""
    phrase = _LOSS_PHRASES.get(row.get("lost_cause") or "", "lost")
    return (f"No account from {name} survives: their archive{where} was "
            f"{phrase} (turn {row['lost_turn']}).")


def _telling(rows: Sequence[dict], names: dict[str, str], archives: dict[str, dict],
             voices: int | None = None, noted: set[str] | None = None,
             localize=None) -> tuple[str, list[str]]:
    """The passage and the ids of the accounts it tells (see ``telling``).

    ``localize`` (row -> text) renders a chronicler's text in its own
    language's names (``languages.NameIndex.localize_account``).
    """
    parts: list[str] = []
    ids: list[str] = []
    told = (_voices(rows, voices) if voices is not None
            else [r for r in rows if r.get("text") and r.get("lost_turn") is None])
    for k, row in enumerate(told):
        name = names.get(row["chronicler"], row["chronicler"])
        lead = f"As {name} tell it" if k == 0 else f"Though {name} say"
        text = localize(row) if localize is not None else row["text"]
        parts.append(f"{lead}: {_quote(text)}")
        ids.append(row["account_id"])
    notes = 0
    for row in rows:
        if voices is not None and notes >= 1:
            break
        cid = row["chronicler"]
        name = names.get(cid, cid)
        if row.get("lost_turn") is not None:
            if voices is not None and told and not cid.startswith("court:"):
                continue  # a lost temple copy is noted only where nothing else survives
            episode = f"{cid}@{row['lost_turn']}:{row.get('lost_cause')}"
            if noted is not None and episode in noted:
                continue
            parts.append(_loss_note(row, name, archives))
            ids.append(row["account_id"])
            if noted is not None:
                noted.add(episode)
            notes += 1
        elif not row.get("text"):
            parts.append(f"{_capital(name)} pass over it in silence.")
            ids.append(row["account_id"])
            notes += 1
    return " ".join(parts), ids


def telling(rows: Sequence[dict], names: dict[str, str], archives: dict[str, dict],
            voices: int | None = None, noted: set[str] | None = None) -> str:
    """One narratable passage for an event, from its accounts (dicts, see ``row_dict``).

    'As the Thornwall chronicles tell it: "...". Though the Kethani chronicles
    say: "...". No account from the Ashkari chronicles survives: their archive
    at Thornwood was sacked (turn 12).' Without ``voices`` every account is
    given. With ``voices`` only that many told accounts (the most divergent)
    and one note on silence or loss (a temple's loss only when no voice
    survives); ``noted`` (loss episodes already told, updated) keeps a loss
    from being retold.
    """
    return _telling(rows, names, archives, voices, noted)[0]


# ---------------------------------------------------------------------------
# Reading accounts back for narration
# ---------------------------------------------------------------------------


class AccountIndex:
    """Read-only view of a bundle's ``historiography`` field for narration.

    With ``names`` (a ``languages.NameIndex``), each chronicler's quoted text
    uses its own language's names for peoples, places and persons
    ("Ashkel Vor [Verdant Plains]"); without it the text is as written.
    """

    def __init__(self, data: dict, names=None) -> None:
        self.data = data
        self.localize = names.localize_account if names else None
        self.names = {c["id"]: c["name"] for c in data.get("chroniclers", [])}
        self.archives = {a["owner"]: a for a in data.get("archives", [])}
        columns = tuple(data.get("account_columns") or ACCOUNT_COLUMNS)
        self.by_event: dict[str, list[dict]] = {}
        for raw in data.get("accounts", []):
            row = row_dict(raw) if columns == ACCOUNT_COLUMNS else _decode(columns, raw)
            self.by_event.setdefault(row["event_id"], []).append(row)
        self.contested = {c["event_id"]: c for c in data.get("contested", [])}

    @classmethod
    def from_bundle(cls, bundle: dict | None) -> "AccountIndex | None":
        data = (bundle or {}).get("historiography")
        return cls(data) if isinstance(data, dict) else None

    def __bool__(self) -> bool:
        return bool(self.by_event)

    def contested_bonus(self) -> dict[str, float]:
        """Curator bonus per contested event id."""
        return {eid: min(CONTESTED_CAP, CONTESTED_WEIGHT * len(c["divergence"]))
                for eid, c in self.contested.items()}

    def accounts_for(self, event_id: str) -> list[dict]:
        return list(self.by_event.get(event_id, []))

    def telling_for(self, event_id: str) -> str:
        return _telling(self.by_event.get(event_id, []), self.names, self.archives,
                        localize=self.localize)[0]

    def select(self, events: Sequence["Event"], limit: int) -> list[tuple["Event", list[dict]]]:
        """The moment's events with notable accounts: contested first, then the most important."""
        ranked = []
        for order, ev in enumerate(events):
            rows = self.by_event.get(ev.event_id) if ev.event_id else None
            if not rows:
                continue
            kinds = len(self.contested.get(ev.event_id, {}).get("divergence", []))
            ranked.append((-kinds, -ev.importance, order, ev, rows))
        ranked.sort(key=lambda r: r[:3])
        return [(r[3], r[4]) for r in ranked[:limit]]

    def passage(self, events: Sequence["Event"], limit: int = 2, voices: int = 2,
                noted: set[str] | None = None) -> tuple[str, list[str]]:
        """Mechanical chronicle text ("In their own words: ...") and the account ids it tells.

        ``noted`` (loss episodes already told) carries across a chronicle so
        an archive's loss is told once.
        """
        parts, ids = [], []
        noted = set() if noted is None else noted
        for _ev, rows in self.select(events, limit):
            text, told = _telling(rows, self.names, self.archives, voices=voices, noted=noted,
                                  localize=self.localize)
            if text:
                parts.append(text)
                ids.extend(told)
        if not parts:
            return "", []
        return "In their own words: " + " ".join(parts), ids

    def prompt_block(self, events: Sequence["Event"], limit: int = 3,
                     per_event: int = 3) -> tuple[str, list[str]]:
        """Narrator prompt block and the account ids it offers."""
        lines, ids = [], []
        for ev, rows in self.select(events, limit):
            lines.append(f"- [turn {ev.turn}] {_label(ev)}")
            quoted = _voices(rows, per_event)
            others = [r for r in rows if r not in quoted
                      and (r.get("lost_turn") is not None or not r.get("text"))]
            others = others[: max(1, per_event - len(quoted))]
            for row in quoted + others:
                name = self.names.get(row["chronicler"], row["chronicler"])
                ids.append(row["account_id"])
                if row.get("lost_turn") is not None:
                    phrase = _LOSS_PHRASES.get(row.get("lost_cause") or "", "lost")
                    lines.append(f"  - {name}: lost (archive {phrase}, turn {row['lost_turn']}); "
                                 "no account survives")
                elif not row.get("text"):
                    lines.append(f"  - {name}: silent (the event is left out)")
                else:
                    kinds = sorted({t["kind"] for t in row.get("transforms", [])})
                    tag = f" ({', '.join(kinds)})" if kinds else ""
                    text = self.localize(row) if self.localize is not None else row["text"]
                    lines.append(f"  - {name}{tag}: {_quote(text)}")
        if not lines:
            return "", []
        head = ("\n\nIN-WORLD ACCOUNTS (how the world's own chroniclers recorded these events; "
                "each is a biased telling of a real event above, not the truth. Where they "
                "disagree, tell it as their claims, e.g. \"as the X chronicles tell it ..., "
                "though the Y records say ...\"):\n")
        return head + "\n".join(lines) + "\n", ids


def _decode(columns: Sequence[str], raw: Sequence) -> dict:
    """A row of another column layout: known columns by name, the rest ignored."""
    values = dict(zip(columns, raw))
    return row_dict([values.get(c) for c in ACCOUNT_COLUMNS])
