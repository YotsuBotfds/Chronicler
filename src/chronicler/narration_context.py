"""Narration-side reading of what a run recorded.

Nothing here is read by the simulation, and nothing here changes a run's
outputs. It turns recorded events, their provenance and the per-turn
snapshots into the bounded lines the curated narrator receives, the
mechanical chronicle's sentences and the weights the curator gives event
kinds. It describes what the simulation recorded; it never decides, invents
or infers an outcome. Every choice is a deterministic function of its inputs
(no sets are iterated for output order, no random draws).

* :func:`event_text` - an event's line: its recorded description, a label for
  the event types that carry none (hazard rolls, native politics triggers),
  and a few corrections where a recorded description misleads.
* :data:`ROUTINE_TYPES`, :func:`is_bookkeeping` - routine actions and
  episode bookkeeping, which never carry a moment or fill its event list.
* :func:`select_prompt_events` - the moment's events worth a line (at most
  ``MAX_PROMPT_EVENTS``), repeats of one kind folded into one line, and a
  count of the rest.
* :func:`standing_state_lines` - the standing state at the moment from its
  snapshot: rulers, wars, living movements, reforms in force, chartered and
  great cities, regions short of food with their recorded dearth or famine.
* :class:`TimelineView` - lookups over the whole event timeline: the
  recorded consequences of a moment outside it, and food-crisis episodes.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Iterable, Sequence

if TYPE_CHECKING:  # pragma: no cover
    from chronicler.models import Event, TurnSnapshot, WorldState

# ---------------------------------------------------------------------------
# Event lines
# ---------------------------------------------------------------------------

#: Labels for events recorded without a description: the per-civ hazard rolls
#: (the old narrator filled these in) and the native politics triggers. "{a}"
#: is the first actor, "{b}" the second, "{all}" every actor.
EVENT_LABELS: dict[str, str] = {
    "drought": "drought strikes {all}",
    "plague": "plague strikes {all}",
    "earthquake": "an earthquake shakes {all}",
    "border_incident": "a border incident between {a} and {b}",
    "rebellion": "rebellion breaks out in {a}",
    "migration": "a wave of emigration leaves {a}",
    "religious_movement": "a religious movement stirs {a}",
    "discovery": "{a} makes a discovery",
    "cultural_renaissance": "a cultural renaissance flowers in {a}",
    "leader_death": "the ruler of {a} dies",
    # Native politics triggers (chronicler-agents politics.rs).
    "proxy_detected": "{a} is exposed funding separatists in {b}",
    "federation_formed": "{all} form a federation",
    "federation_collapsed": "the federation of {all} breaks apart",
    "capital_loss": "{a} loses its capital",
    "secession": "{b} breaks away from {a}",
    "vassal_rebellion": "{a} rises against its overlord {b}",
    "restoration": "{a} is restored, breaking free of {b}",
    "twilight_absorption": "{a} is absorbed into {b}",
    "collapse": "{a} collapses",
}

# Recorded descriptions that mislead, read as what was recorded.
_SAME_CAPITAL = re.compile(r"^(?P<civ>.+) relocated capital from (?P<old>.+) to (?P<new>.+?)\.?$")
# The template a mass migration had before its driver was recorded: the move
# is not known to be flight.
_UNDRIVEN_FLIGHT = re.compile(r"^(?P<count>\d+) (?P<who>\w+) fled (?P<rest>.+ for .+)$")
_SCHOLARS_FLED = re.compile(r"^(?P<count>\d+) scholars fled (?P<rest>.+)$")
# religion.py records "Mass Migration" when the persecuted share of a region
# passes a threshold; it counts no one leaving.
_FAITHFUL_FLEE = re.compile(r"^Religious minorities flee (?P<region>.+) due to persecution "
                            r"\(minority_ratio=(?P<ratio>[\d.]+)\)$")
# infrastructure.py names a temple's faith by its id.
_TEMPLE_OF_FAITH = re.compile(r"^Temple of faith (?P<id>\d+) (?P<what>destroyed|replaced) in (?P<region>.+)$")


def _words(event_type: str) -> str:
    return event_type.replace("_", " ").strip().lower()


def event_text(ev: "Event", faiths: dict[int, str] | None = None) -> str:
    """The event's narrator line, without a trailing full stop.

    With ``faiths`` (faith id -> name, from ``world.belief_registry``) a
    temple recorded by faith id is named by its faith.

    The recorded description, or a label for types recorded without one.
    Four recorded descriptions are reworded to say no more than the record:
    a capital "relocated" to the region it already stood in (the cost was paid,
    the seat did not move), a mass migration without a recorded driver (it
    "left", not "fled"), scholars who migrated (they "left"), and religious
    minorities said to "flee" where the record is only their persecuted share.
    """
    desc = (ev.description or "").strip()
    if desc:
        if ev.event_type == "move_capital":
            m = _SAME_CAPITAL.match(desc)
            if m and m.group("old") == m.group("new"):
                return f"{m.group('civ')} spent on moving its capital but kept it at {m.group('new')}"
        elif ev.event_type == "mass_migration" and not getattr(ev, "driver", None):
            m = _UNDRIVEN_FLIGHT.match(desc)
            if m:
                return f"{m.group('count')} {m.group('who')} left {m.group('rest')}".rstrip(".")
        elif ev.event_type == "brain_drain":
            m = _SCHOLARS_FLED.match(desc)
            if m:
                return f"{m.group('count')} scholars left {m.group('rest')}".rstrip(".")
        elif ev.event_type == "temple_destroyed" and faiths:
            m = _TEMPLE_OF_FAITH.match(desc)
            name = faiths.get(int(m.group("id"))) if m else None
            if m and name:
                return f"The temple of the {name} is {m.group('what')} in {m.group('region')}"
        elif ev.event_type == "Mass Migration":
            m = _FAITHFUL_FLEE.match(desc)
            if m:
                share = round(100 * float(m.group("ratio")))
                return (f"Persecution presses the religious minorities of {m.group('region')} "
                        f"({share}% of its people) to flee")
        return desc.rstrip(".").rstrip()
    actors = [a for a in ev.actors if a]
    template = EVENT_LABELS.get(ev.event_type)
    if template is not None and actors:
        text = template.format(a=actors[0], b=actors[1] if len(actors) > 1 else "its neighbours",
                               all=" and ".join(actors))
    elif actors:
        text = f"{_words(ev.event_type)} in {', '.join(actors)}"
    else:
        text = _words(ev.event_type)
    region = getattr(ev, "region", None)
    if region and region not in text:
        text += f" ({region})"
    return text[:1].upper() + text[1:]


#: The plain words for a migration's recorded driver (``models.MIGRATION_DRIVER_NAMES``).
DRIVER_WORDS: dict[str, str] = {
    "frontier": "open land to settle", "wage": "work and wages", "chain": "kin who went before",
    "urban": "the city", "learning": "a seat of learning", "famine_memory": "memory of hunger",
    "opp_food": "food elsewhere",
    "persecution": "persecution", "persecution_memory": "memory of persecution",
    "battle_memory": "memory of war", "conquest_memory": "memory of conquest",
    "low_satisfaction": "hardship", "safety_need": "want of safety", "material_need": "want",
    "spiritual_need": "spiritual want", "social_need": "isolation", "opp_satisfaction": "better prospects",
    "opp_capacity": "room to live", "opp_river": "a river valley", "opp_news": "news of better land",
}

# ---------------------------------------------------------------------------
# Event classes (narration weights)
# ---------------------------------------------------------------------------

#: Routine actions and recurring administration: they never carry a moment
#: and are counted, not listed, in a prompt. (The historiography layer's
#: ``ROUTINE`` plus the declarations, adoptions and spreads that recur every
#: few turns.) Guild events (``guild_founded``, ``guild_privilege``,
#: ``guild_privilege_lost``, ``guild_levy``, ``guild_dissolved``) weigh by their
#: importance like other events; the standing state names the guilds. A
#: faction taking the lead at court (``faction_dominance_shift``, the burghers'
#: rise with ``--guilds``) is a political change, not routine. Seats of
#: learning (``--scholarship``): a founding, rise, decline, fall or flight
#: weighs by its importance; a new patron or a great scholar teaching there
#: is routine. Public granaries (``--grain-reserves``): an opening against
#: dearth or famine and an emptied granary weigh by their importance; grain
#: bought abroad for them is routine.
ROUTINE_TYPES: frozenset[str] = frozenset({
    "develop", "invest_culture", "diplomacy", "trade", "build_started",
    "infrastructure_completed", "fund_instability", "fund_instability_failed", "action",
    "treaty_renewed", "treaty_expired", "loan_taken", "debt_written_off",
    "army_raised", "army_disbanded", "mercenary_spawned", "tech_focus_selected",
    "trait_evolution", "institutional_regime_shift",
    "quarantine", "aid_convoy", "mutual_aid", "price_inflation",
    "reform_pressure", "fiscal_strain", "elite_overproduction", "terrain_transition",
    "settlement_dissolved", "explore_failed", "pandemic_spread", "move_capital", "none",
    "supply_shock", "occupation_shift", "notable_migration", "economic_shock",
    "agenda_declared", "ambition_declared", "technique_adopted", "movement_spread",
    "institution_enforcement_lapse", "reform_lapsed", "preaching", "shrine_commissioned",
    "seat_patron", "seat_master", "grain_bought",
})


#: Endings the simulation records as events in their own right (a peace, a
#: tribute lifted), not as the closing record of an episode.
SUBSTANTIVE_ENDINGS: frozenset[str] = frozenset({"war_ended", "tribute_ended"})


def is_bookkeeping(ev: "Event") -> bool:
    """Closing and repeat records of an episode (``*_ended``), and capability unlocks."""
    t = ev.event_type
    if t in SUBSTANTIVE_ENDINGS:
        return False
    return (ev.episode in ("repeat", "end") or t.endswith("_ended") or t.startswith("capability_"))


def is_routine(ev: "Event") -> bool:
    return ev.event_type in ROUTINE_TYPES or is_bookkeeping(ev)


#: Events at or above this importance are turning points (curator bonus).
TURNING_POINT_IMPORTANCE = 8

# ---------------------------------------------------------------------------
# Prompt event selection
# ---------------------------------------------------------------------------

MAX_PROMPT_EVENTS = 12
ROUTINE_FILL = 4        # routine lines are listed only while fewer lines than this exist
MAX_EXTRA_TURNING_LINES = 4  # beyond the limit, for turning points of kinds no line shows
MAX_FOLDED_PLACES = 4
MAX_OMITTED_KINDS = 8


SCARCE_IN_RUN = 5      # a kind seen at most this often in the run is scarce (+2)
UNCOMMON_IN_RUN = 20   # ... at most this often, uncommon (+1)
COMMON_IN_RUN = 40     # ... more often, common: -log2(count / 40), at most 2
MAX_LINES_PER_KIND = 2  # further lines of a kind fold into its best one


def salience(ev: "Event", chained: bool = False, named: bool = False,
             focused: bool = False, run_count: int | None = None) -> float:
    """How much an event deserves a prompt line: its importance; +3 when it
    is a step of the moment's recorded causal chains, +2 when a named event
    marks it, +1.5 when it involves the civs of the moment's two most
    important events; +2 for a kind seen at most SCARCE_IN_RUN times in the
    run, +1 at most UNCOMMON_IN_RUN, -log2(count / COMMON_IN_RUN) (at most 2)
    above COMMON_IN_RUN; routine kinds -2; +2 for a founding the record
    links to news of a like movement's won demand elsewhere."""
    s = float(ev.importance)
    if chained:
        s += 3.0
    if named or news_sparked(ev):
        s += 2.0
    if focused:
        s += 1.5
    if run_count is not None:
        if run_count <= SCARCE_IN_RUN:
            s += 2.0
        elif run_count <= UNCOMMON_IN_RUN:
            s += 1.0
        elif run_count > COMMON_IN_RUN:
            s -= min(2.0, math.log2(run_count / COMMON_IN_RUN))
    if ev.event_type in ROUTINE_TYPES:
        s -= 2.0
    return s


def involved(ev: "Event") -> list[str]:
    """The names an event involves: its actors, then its recorded civs."""
    out = [a for a in ev.actors if a]
    out.extend(c for c in ev.civs if c and c not in out)
    return out


def moment_focus(events: Sequence["Event"], k: int = 2) -> list[str]:
    """The names involved in a moment's k most important substantive events
    (ties: recorded order)."""
    order = sorted((i for i, ev in enumerate(events) if not is_routine(ev)),
                   key=lambda i: (-events[i].importance, i))
    out: list[str] = []
    for i in order[:k]:
        for name in involved(events[i]):
            if name not in out:
                out.append(name)
    return out


class PromptLine:
    """One listed event and the repeats of its kind folded into it (in
    recorded order)."""

    __slots__ = ("event", "score", "order", "_folded")

    def __init__(self, event: "Event", score: float, order: int) -> None:
        self.event = event
        self.score = score
        self.order = order
        self._folded: list[tuple[int, "Event"]] = []

    def fold(self, order: int, ev: "Event") -> None:
        self._folded.append((order, ev))
        self._folded.sort(key=lambda item: item[0])

    @property
    def folded(self) -> list["Event"]:
        return [ev for _i, ev in self._folded]

    @property
    def events(self) -> list["Event"]:
        return [self.event, *self.folded]


def _fold_key(ev: "Event") -> tuple:
    return (ev.event_type, ev.actors[0] if ev.actors else "")


def select_prompt_events(
    events: Sequence["Event"],
    chain_ids: Iterable[str] = (),
    named_keys: Iterable[tuple] = (),
    limit: int = MAX_PROMPT_EVENTS,
    type_counts: dict[str, int] | None = None,
) -> tuple[list[PromptLine], Counter]:
    """The moment's events worth a line, in recorded order, and the rest by type.

    Bookkeeping records are never listed. Events of one kind with the same
    first actor fold into the most salient of them (its line names the other
    places). The ``limit`` most salient lines are kept (:func:`salience`, with
    ``type_counts`` the run's count of each kind); ties go to the earlier
    event. At most MAX_LINES_PER_KIND lines show one kind: the rest fold into
    its best line. Up to MAX_EXTRA_TURNING_LINES more lines go to turning
    points (importance 8+) of kinds no kept line shows. Routine kinds are
    listed only while fewer than ROUTINE_FILL lines are kept (a quiet moment
    still reads as something).
    The returned counter counts every unlisted, unfolded event by type.
    """
    chained = set(chain_ids)
    named = set(named_keys)
    focus = set(moment_focus(events))
    groups: dict[tuple, PromptLine] = {}
    order: list[PromptLine] = []
    omitted: Counter = Counter()
    for i, ev in enumerate(events):
        if is_bookkeeping(ev):
            omitted[ev.event_type] += 1
            continue
        score = salience(ev, bool(ev.event_id and ev.event_id in chained),
                         (ev.turn, frozenset(ev.actors)) in named,
                         bool(focus.intersection(involved(ev))),
                         type_counts.get(ev.event_type) if type_counts is not None else None)
        key = _fold_key(ev)
        line = groups.get(key)
        if line is None:
            line = PromptLine(ev, score, i)
            groups[key] = line
            order.append(line)
        elif score > line.score:
            line.fold(line.order, line.event)
            line.event, line.score, line.order = ev, score, i
        else:
            line.fold(i, ev)
    ranked = sorted(order, key=lambda ln: (ln.event.event_type in ROUTINE_TYPES, -ln.score, ln.order))
    kept: list[PromptLine] = []
    extra = 0
    per_kind: dict[str, list[PromptLine]] = {}
    for line in ranked:
        same = per_kind.setdefault(line.event.event_type, [])
        routine = line.event.event_type in ROUTINE_TYPES
        if not routine and (len(same) >= MAX_LINES_PER_KIND or (same and len(kept) >= limit)):
            target = same[0]  # the kind's best line names the others
            target.fold(line.order, line.event)
            for order_, ev in line._folded:
                target.fold(order_, ev)
            continue
        turning = (not routine and line.event.importance >= TURNING_POINT_IMPORTANCE
                   and extra < MAX_EXTRA_TURNING_LINES)
        if len(kept) < (min(limit, ROUTINE_FILL) if routine else limit):
            kept.append(line)
            same.append(line)
        elif turning:
            # A turning point of a kind no line shows yet: one of a few extra lines.
            extra += 1
            kept.append(line)
            same.append(line)
        else:
            for ev in line.events:
                omitted[ev.event_type] += 1
    kept.sort(key=lambda ln: ln.order)
    return kept, omitted


def places_of(events: Sequence["Event"]) -> list[str]:
    out: list[str] = []
    for ev in events:
        place = ev.region or ev.shock_region
        if place and place not in out:
            out.append(place)
    return out


#: A like movement's success whose news can spark a founding elsewhere
#: (``agent_movements.news_cause`` cites it on the founding).
NEWS_SUCCESS_TYPES: frozenset[str] = frozenset({"movement_reform", "movement_concession"})


def _id_type(event_id: str) -> str:
    """The type an event id names (``<turn>:<type>:<n>``), or ""."""
    parts = event_id.split(":", 2)
    return parts[1] if len(parts) == 3 else ""


def news_sparked(ev: "Event") -> bool:
    """A founding whose recorded causes include a like movement's won demand."""
    return ev.event_type == "movement_founded" and any(
        _id_type(c) in NEWS_SUCCESS_TYPES for c in ev.causes)


def news_spark(ev: "Event", timeline: "TimelineView | None") -> "Event | None":
    """The like movement's success in another region whose news the record
    says sparked this founding, or None."""
    if ev.event_type != "movement_founded" or timeline is None:
        return None
    for cid in ev.causes:
        cause = timeline.by_id.get(cid)
        if (cause is not None and cause.event_type in NEWS_SUCCESS_TYPES
                and cause.region and cause.region != ev.region):
            return cause
    return None


def render_prompt_line(line: PromptLine, faiths: dict[int, str] | None = None,
                       timeline: "TimelineView | None" = None) -> str:
    """``- [turn 31] famine: Famine strikes X, devastating Y (importance 8; 2 more
    reports: Thornwood, Amber Valley)``. With the run's ``timeline`` a founding
    sparked by news names the success it heard of."""
    ev = line.event
    text = event_text(ev, faiths)
    notes = [f"importance {ev.importance}"]
    driver = getattr(ev, "driver", None)
    if driver:
        notes.append(f"driven by {DRIVER_WORDS.get(driver, driver.replace('_', ' '))}")
    spark = news_spark(ev, timeline)
    if spark is not None:
        notes.append(f"stirred by news of the demand won in {spark.region} in turn {spark.turn}")
    unnamed = [a for a in ev.actors if a and a not in text]
    if unnamed:
        notes.append("with " + ", ".join(unnamed[:3]))
    if line.folded:
        places = [p for p in places_of(line.folded) if p != (ev.region or ev.shock_region)]
        more = f"{len(line.folded)} more alike, turns {line.folded[0].turn}-{line.folded[-1].turn}"
        if places:
            more += ": " + ", ".join(places[:MAX_FOLDED_PLACES])
            if len(places) > MAX_FOLDED_PLACES:
                more += f" and {len(places) - MAX_FOLDED_PLACES} more"
        notes.append(more)
    return f"- [turn {ev.turn}] {ev.event_type}: {text} ({'; '.join(notes)})"


def render_omitted(omitted: Counter) -> str:
    """``Also recorded in these turns (not listed): 41 develop, 9 trade, ...``."""
    if not omitted:
        return ""
    kinds = sorted(omitted.items(), key=lambda kv: (-kv[1], kv[0]))
    parts = [f"{n} {_words(t)}" for t, n in kinds[:MAX_OMITTED_KINDS]]
    rest = sum(n for _t, n in kinds[MAX_OMITTED_KINDS:])
    if rest:
        parts.append(f"{rest} others")
    return "Also recorded in these turns (not listed): " + ", ".join(parts) + "."


# ---------------------------------------------------------------------------
# Timeline lookups
# ---------------------------------------------------------------------------

MAX_CONSEQUENCES = 4


class TimelineView:
    """Lookups over a run's whole event timeline (built once per narration)."""

    def __init__(self, timeline: Sequence["Event"]) -> None:
        self.timeline = list(timeline)
        self.type_counts: dict[str, int] = dict(Counter(ev.event_type for ev in self.timeline))
        self.by_id: dict[str, "Event"] = {}
        self.children: dict[str, list[int]] = {}
        # A movement keeps its dead leader's name; the martyrdom is the record.
        self.martyred: dict[str, int] = {}
        for i, ev in enumerate(self.timeline):
            if ev.event_id and ev.event_id not in self.by_id:
                self.by_id[ev.event_id] = ev
            for cid in ev.causes:
                self.children.setdefault(cid, []).append(i)
            if ev.event_type == "movement_martyr" and len(ev.actors) > 1:
                self.martyred.setdefault(ev.actors[1], ev.turn)
        self._crises = self._food_crises()

    def consequences(self, moment_events: Sequence["Event"], end_turn: int,
                     limit: int = MAX_CONSEQUENCES) -> list["Event"]:
        """Later events (after ``end_turn``) whose recorded causes include an
        event of the moment: the most important first, one per kind and first
        actor, routine and bookkeeping kinds left out."""
        seen: set[int] = set()
        found: list[tuple[int, int, "Event"]] = []
        for ev in moment_events:
            for j in self.children.get(ev.event_id, ()) if ev.event_id else ():
                if j in seen:
                    continue
                seen.add(j)
                eff = self.timeline[j]
                if eff.turn <= end_turn or is_routine(eff):
                    continue
                found.append((-eff.importance, eff.turn, eff))
        found.sort(key=lambda x: (x[0], x[1], x[2].event_id))
        out: list["Event"] = []
        keys: list[tuple] = []
        for _imp, _turn, eff in found:
            key = _fold_key(eff)
            if key in keys:
                continue
            keys.append(key)
            out.append(eff)
            if len(out) >= limit:
                break
        return out

    # --- food crises ---------------------------------------------------------

    def _food_crises(self) -> dict[str, list[tuple[int, int | None, str, tuple[int, ...]]]]:
        """Per region: (start, end or None, label, report turns) spans of
        recorded dearth and famine reports, as the viewer's Food tab reads
        them: an onset opens a span, a report with the other label closes it
        and opens one of that label, and ``famine_ended`` / ``dearth_ended``
        closes it."""
        spans: dict[str, list[list]] = {}
        open_: dict[str, list] = {}
        for ev in self.timeline:
            region = ev.region
            if not region:
                continue
            t = ev.event_type
            if t in ("famine", "dearth"):
                cur = open_.get(region)
                if ev.episode == "onset" or cur is None or cur[2] != t:
                    if cur is not None:
                        cur[1] = ev.turn
                    span = [ev.turn, None, t, [ev.turn]]
                    spans.setdefault(region, []).append(span)
                    open_[region] = span
                else:
                    cur[3].append(ev.turn)
            elif t in ("famine_ended", "dearth_ended"):
                cur = open_.pop(region, None)
                if cur is not None:
                    cur[1] = ev.turn
        return {r: [(s[0], s[1], s[2], tuple(s[3])) for s in ss] for r, ss in spans.items()}

    def food_crisis_at(self, region: str, turn: int) -> tuple[int, str, int] | None:
        """The recorded dearth or famine running in ``region`` at ``turn``:
        (start, label, reports up to ``turn``), or None."""
        for start, end, label, reports in reversed(self._crises.get(region, [])):
            if start <= turn and (end is None or end > turn):
                return start, label, sum(1 for r in reports if r <= turn)
        return None


# ---------------------------------------------------------------------------
# Standing state
# ---------------------------------------------------------------------------

MAX_STATE_LINES = 10
MAX_PER_KIND = 3


def focus_of(events: Sequence["Event"], snapshot: "TurnSnapshot | None",
             limit_civs: int = 3, limit_regions: int = 4) -> tuple[list[str], list[str]]:
    """The civs and regions a moment is about, in order of first mention by
    the most important events (ties: recorded order)."""
    ranked = sorted(range(len(events)), key=lambda i: (is_routine(events[i]), -events[i].importance, i))
    civs: list[str] = []
    regions: list[str] = []
    known = set(snapshot.civ_stats) if snapshot is not None else set()
    for i in ranked:
        ev = events[i]
        for name in list(ev.actors) + list(ev.civs):
            if name in known and name not in civs and len(civs) < limit_civs:
                civs.append(name)
        for place in (ev.region, ev.shock_region):
            if place and place not in regions and len(regions) < limit_regions:
                regions.append(place)
    return civs, regions


def _civ_name(world: "WorldState | None", idx: Any) -> str | None:
    if world is None or not isinstance(idx, int) or not 0 <= idx < len(world.civilizations):
        return None
    return world.civilizations[idx].name


def _region_name(world: "WorldState | None", idx: Any) -> str | None:
    if world is None or not isinstance(idx, int) or not 0 <= idx < len(world.regions):
        return None
    return world.regions[idx].name


def _reform_label(world: "WorldState | None", row: dict) -> str:
    from chronicler.agent_movements_state import REFORM_NAMES
    kind = row.get("kind")
    try:
        index = REFORM_NAMES.index(kind)
    except ValueError:
        return str(kind or "a reform")
    if world is None:
        return f"the {str(kind).replace('_', ' ')}"
    from chronicler.agent_movements import reform_name
    r = SimpleNamespace(kind=index, regions=list(row.get("regions") or []),
                        faith=row.get("faith", -1), church=bool(row.get("church")),
                        movement=int(row.get("movement", -1)), cities=list(row.get("cities") or []))
    return reform_name(world, r)


def standing_state_lines(
    snapshot: "TurnSnapshot | None",
    events: Sequence["Event"],
    world: "WorldState | None" = None,
    timeline: TimelineView | None = None,
    at_turn: int | None = None,
) -> list[str]:
    """Compact lines of the standing state in a snapshot (see
    :func:`standing_state_facts`, which also names the values each reads)."""
    return [text for _keys, text in standing_state_facts(snapshot, events, world, timeline, at_turn)]


def standing_state_facts(
    snapshot: "TurnSnapshot | None",
    events: Sequence["Event"],
    world: "WorldState | None" = None,
    timeline: TimelineView | None = None,
    at_turn: int | None = None,
) -> list[tuple[list[tuple], str]]:
    """Compact lines of the standing state in a snapshot, each with the
    snapshot values it reads: ``(kind, key)`` pairs, a key being a civ
    ``("civ", name)``, a region ``("region", name)``, a pair of civs or a
    snapshot row's own id (``narration_provenance`` makes them fact ids).

    A snapshot of turn T holds the state after turn T - 1 (its food is what
    turn T - 1 observed); ``at_turn`` is that completed turn (default T - 1).
    Rulers and capitals of the moment's civs, their wars, living movements
    against them (creed, stage, members, leader, stronghold), reforms in force
    in them, chartered or great cities in their lands or the moment's regions,
    those cities' guilds and the burgher faction (``--guilds``), seats of
    learning in the moment's regions or its civs' lands (``--scholarship``),
    and the moment's regions short of food with the dearth or famine the
    timeline records there. Civ and region identities are indices into ``world``;
    without a world those lines are left out.
    """
    if snapshot is None:
        return []
    if at_turn is None:
        at_turn = snapshot.turn - 1
    civs, regions = focus_of(events, snapshot)
    lines: list[tuple[list[tuple], str]] = []

    rulers = []
    ruler_keys: list[tuple] = []
    for name in civs:
        cs = snapshot.civ_stats.get(name)
        if cs is None or not cs.alive:
            continue
        part = f"{name}: {cs.leader_name}" if cs.leader_name else name
        extra = []
        if cs.capital_region:
            extra.append(f"capital {cs.capital_region}")
        if cs.is_vassal:
            extra.append("a vassal")
        if cs.federation_name:
            extra.append(f"in {cs.federation_name}")
        if extra:
            part += f" ({', '.join(extra)})"
        rulers.append(part)
        ruler_keys.append(("ruler", ("civ", name)))
    if rulers:
        lines.append((ruler_keys, "Rulers: " + "; ".join(rulers)))

    # Wars: the campaign layer's record (aim, start, war score from the
    # attacker's side, -100..100) when present, else the plain war pairs.
    wars = []
    war_keys: list[tuple] = []
    campaign_wars = (snapshot.campaign or {}).get("wars") or []
    for w in campaign_wars:
        a, b = w.get("attacker"), w.get("defender")
        if a in civs or b in civs:
            text = f"{a} against {b} since turn {w.get('start_turn')}"
            aim = str(w.get("aim") or "").replace("_", " ")
            if aim:
                text += f" ({aim}" + (f" of {w['aim_region']}" if w.get("aim_region") else "")
                text += f"; war score {int(w.get('score', 0)):+d} for {a})"
            wars.append(text)
            war_keys.append(("war", (("civ", a), ("civ", b))))
    if not campaign_wars:
        for pair in snapshot.active_wars:
            a, b = pair[0], pair[1]
            if (a in civs or b in civs) and f"{a} and {b}" not in wars:
                wars.append(f"{a} and {b}")
                war_keys.append(("war", (("civ", a), ("civ", b))))
    if wars:
        lines.append((war_keys[:MAX_PER_KIND], "At war: " + "; ".join(wars[:MAX_PER_KIND])))

    am = snapshot.agent_movements or {}
    if world is not None:
        living = [row for row in am.get("living", [])
                  if _civ_name(world, row.get("target")) in civs and int(row.get("members", 0)) > 0]
        living.sort(key=lambda r: (-int(r.get("members", 0)), int(r.get("id", 0))))
        for row in living[:MAX_PER_KIND]:
            civ = _civ_name(world, row.get("target"))
            text = (f"Movement: {row.get('name')} ({row.get('creed')}, {row.get('stage')}) against {civ}, "
                    f"{row.get('members')} members ({round(100 * float(row.get('strength', 0)))}% of its people)")
            if row.get("leader"):
                died = timeline.martyred.get(row["leader"]) if timeline is not None else None
                if died is not None and died <= at_turn:
                    text += f", its leader {row['leader']} martyred in turn {died}"
                else:
                    text += f", led by {row['leader']}"
            stronghold = _region_name(world, row.get("stronghold"))
            if stronghold:
                text += f", strongest in {stronghold}"
            lines.append(([("movement", row.get("id"))], text))
        reforms = [row for row in am.get("reforms", []) if _civ_name(world, row.get("civ")) in civs]
        reforms.sort(key=lambda r: (int(r.get("since", 0)), int(r.get("id", 0))))
        for row in reforms[:MAX_PER_KIND]:
            text = f"Reform in force: {_reform_label(world, row)} in {_civ_name(world, row.get('civ'))}"
            text += f" since turn {row.get('since')}"
            if row.get("institution"):
                text += f" (as {str(row['institution']).replace('_', ' ')})"
            lines.append(([("reform", row.get("id"))], text))

    cities_state = snapshot.cities or {}
    if cities_state:
        from chronicler.cities_state import CHARTER_NAMES, RANK_NAMES
        rows = [r for r in cities_state.get("cities", [])
                if (r.get("region") in regions or r.get("lord") in civs)
                and (int(r.get("charter", 0)) > 0 or int(r.get("rank", 0)) >= 2)]
        rows.sort(key=lambda r: (-int(r.get("rank", 0)), -int(r.get("charter", 0)),
                                 -int(r.get("residents", 0)), int(r.get("id", 0))))
        for r in rows[:MAX_PER_KIND]:
            rank = int(r.get("rank", 0))
            charter = int(r.get("charter", 0))
            text = f"City: {r.get('name')} ({RANK_NAMES[rank] if 0 <= rank < len(RANK_NAMES) else rank}"
            text += f" in {r.get('region')}" if r.get("region") else ""
            text += f", lord {r.get('lord')})" if r.get("lord") else ", no lord)"
            if charter > 0:
                text += f", {CHARTER_NAMES[charter] if charter < len(CHARTER_NAMES) else charter}"
            text += f", unrest {float(r.get('unrest', 0.0)):.2f}"
            lines.append(([("city", r.get("id"))], text))

    # Guilds (``TurnSnapshot.guilds``, --guilds): those of the moment's regions
    # or of cities in its civs' lands, with the privileges their charters grant.
    guild_state = getattr(snapshot, "guilds", None) or {}
    if guild_state:
        burghers = guild_state.get("burghers") or {}
        city_regions = {r.get("region") for r in (cities_state or {}).get("cities", [])
                        if r.get("lord") in civs}
        rows = [g for g in guild_state.get("guilds", [])
                if g.get("region") in regions or g.get("region") in city_regions]
        rows.sort(key=lambda g: (g.get("region") not in regions, -float(g.get("masters", 0)), int(g.get("id", 0))))
        for g in rows[:MAX_PER_KIND - 1]:
            text = f"Guild: {g.get('name')} ({g.get('kind')} guild in {g.get('region')}, {g.get('masters')} masters)"
            rights = [w for w, on in (("a monopoly of wares", g.get("monopoly")), ("a say in civic dues", g.get("say")),
                                      ("a charter won as a movement", g.get("charter") is not None))
                      if on]
            if rights:
                text += ": " + ", ".join(rights)
            if g.get("levy"):
                text += "; its city's dues raised"
            lines.append(([("guild", g.get("id"))], text))
        shares = [f"{c} {round(100 * float(burghers[c]))}%" for c in civs if c in burghers]
        if rows and shares:
            lines.append(([("burghers", ("civ", c)) for c in civs if c in burghers],
                          "Burgher faction's influence at court: " + ", ".join(shares)))

    # Seats of learning (``TurnSnapshot.scholarship``, --scholarship): those of
    # the moment's regions or of its civs' lands, with their patron and scholars.
    seat_state = getattr(snapshot, "scholarship", None) or {}
    if seat_state:
        lines.extend(([("seat", sid)], text) for sid, text in _seat_rows(seat_state, civs, regions))

    food = snapshot.food or {}
    hungry_regions = list(regions)
    for ev in events:
        if ev.event_type in ("famine", "dearth") and ev.region and ev.region not in hungry_regions:
            hungry_regions.append(ev.region)
    food_lines = []
    if world is not None:
        index = {r.name: i for i, r in enumerate(world.regions)}
        sufficiency = food.get("sufficiency") or []
        for region in hungry_regions:
            i = index.get(region)
            value = sufficiency[i] if i is not None and i < len(sufficiency) else None
            crisis = timeline.food_crisis_at(region, at_turn) if timeline is not None else None
            if crisis is None and (value is None or value >= 1.0):
                continue
            text = f"Food in {region}:"
            if value is not None:
                text += f" food on hand covers {round(100 * value)}% of need"
            if crisis is not None:
                start, label, reports = crisis
                text += ("," if value is not None else "") + f" {label} recorded since turn {start}"
                if reports > 1:
                    text += f" ({reports} reports)"
            food_lines.append(([("food", ("region", region))], text))
    lines.extend(food_lines[:MAX_PER_KIND])
    return lines[:MAX_STATE_LINES]


#: Who keeps a seat of learning, by kind (``scholarship_state.KIND_NAMES``).
SEAT_PATRONS: dict[str, str] = {"academy": "kept by its ruler", "temple school": "kept by its temple",
                                "library": "kept by its city"}


def seat_lines(state: dict, civs: Sequence[str], regions: Sequence[str],
               limit: int = MAX_PER_KIND - 1) -> list[str]:
    """Standing-state lines for the seats of learning of a snapshot's
    ``scholarship`` summary in the moment's regions or its civs' lands."""
    return [text for _sid, text in _seat_rows(state, civs, regions, limit)]


def _seat_rows(state: dict, civs: Sequence[str], regions: Sequence[str],
               limit: int = MAX_PER_KIND - 1) -> list[tuple[Any, str]]:
    """``seat_lines`` with each seat's id."""
    from chronicler.scholarship_state import LEVEL_NAMES
    rows = [s for s in state.get("seats", []) if s.get("region") in regions or s.get("lord") in civs]
    rows.sort(key=lambda s: (s.get("region") not in regions, -int(s.get("level", 0)),
                             -float(s.get("scholars", 0)), int(s.get("id", 0))))
    out = []
    for s in rows[:limit]:
        level = int(s.get("level", 0))
        name = str(s.get("name", ""))
        text = f"Seat of learning: {name[:1].upper() + name[1:]} ("
        text += f"{LEVEL_NAMES[level] if 0 <= level < len(LEVEL_NAMES) else level} {s.get('kind')}"
        text += f" in {s.get('region')}" if s.get("region") else ""
        text += f" under {s.get('lord')}" if s.get("lord") else ""
        text += f", {SEAT_PATRONS.get(str(s.get('kind')), 'kept by its patron')})"
        text += f", {float(s.get('scholars', 0)):.0f} scholars"
        masters = int(s.get("masters", 0))
        if masters:
            text += f", {masters} great scholar{'s' if masters != 1 else ''} teaching"
        if s.get("refugees"):
            text += ", refugees from a fallen seat among them"
        if s.get("unpaid"):
            text += "; its upkeep unpaid"
        out.append((s.get("id"), text))
    return out


def render_standing_state(lines: Sequence[str], turn: int) -> str:
    """The block, headed with the completed turn the state stood after."""
    if not lines:
        return ""
    return (f"\n\nSTANDING STATE after turn {turn} (as recorded; describe it, do not change it):\n"
            + "\n".join(f"- {line}" for line in lines))
