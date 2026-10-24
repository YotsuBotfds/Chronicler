"""Causal provenance: event identity, recorded causes and chronic episodes.

The simulation decides outcomes; this module only *records* why. It never
draws random numbers, never mutates simulation state and is never read by a
simulation decision, so a run with provenance is outcome-identical to one
without (see ``docs/integration/causal-provenance.md``).

Identity
    ``Event.event_id`` is ``"<turn>:<event_type>:<n>"``: the turn being
    simulated when the event was observed, its type, and a per-(turn, type)
    counter. The turn loop observes events in emission order (phase by
    phase), so ids are a pure function of the deterministic event stream.
    ``ActiveCondition.condition_id`` is ``"<turn>:condition.<type>:<n>"``.

Causes
    ``Event.causes`` lists the ids of the events that produced an event.
    Emitters that know the exact cause stamp it (a battle cites its war, an
    occupation the battle or siege that took the region, a pandemic the
    region it spread from). For the rest, :data:`CAUSE_RULES` read the
    persisted causal index (``WorldState.provenance.keys``): the event that
    currently stands for a state the triggering mechanism reads (the open
    famine in a region, the civ's PSI crisis, the active war of a pair).
    No rule guesses from type pairs or time gaps alone.

Chronic conditions
    Conditions that used to emit one event per turn (supply shocks, regional
    agent patterns, climate flight, soil exhaustion, recurring famine) emit
    one ``episode="onset"`` event, are folded into an open
    :class:`~chronicler.models.ChronicEpisode` while they persist, and emit a
    closing ``<type>_ended`` event (``episode="end"``, with ``duration``)
    when they stop. Repeats that a simulation consumer reads (famine, read by
    traditions and factions) stay on the timeline as ``episode="tick"``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Iterable, NamedTuple

from chronicler.models import ChronicEpisode, Event, Exciter, OpenCondition

if TYPE_CHECKING:  # pragma: no cover
    from chronicler.models import WorldState


# ---------------------------------------------------------------------------
# Per-turn identity state
# ---------------------------------------------------------------------------

class TurnIds:
    """Transient per-turn counters and observation cursor.

    Lives on ``WorldState._provenance_turn``. Like the history index it is
    equality-neutral (a cache, never state) and is reset whenever the world
    moves to another turn, so a world loaded at a turn boundary resumes with
    exactly the ids an uninterrupted run would assign.
    """

    __slots__ = ("turn", "counts", "observed", "watermark", "turn_start", "last_by_type")

    def __init__(self, turn: int, watermark: int = 0) -> None:
        self.turn = turn
        self.counts: dict[str, int] = {}
        self.observed: set[str] = set()
        self.watermark = watermark
        self.turn_start = watermark
        self.last_by_type: dict[str, str] = {}

    def __eq__(self, other: object) -> bool:
        return other is None or isinstance(other, TurnIds)

    __hash__ = None  # type: ignore[assignment]

    def __copy__(self) -> "TurnIds":
        clone = TurnIds(self.turn, self.watermark)
        clone.counts = dict(self.counts)
        clone.observed = set(self.observed)
        clone.turn_start = self.turn_start
        clone.last_by_type = dict(self.last_by_type)
        return clone

    def __deepcopy__(self, memo: dict) -> "TurnIds":
        return self.__copy__()


def _turn_ids(world: "WorldState") -> TurnIds:
    ids = world._provenance_turn
    if not isinstance(ids, TurnIds) or ids.turn != world.turn:
        ids = TurnIds(world.turn, len(world.events_timeline))
        world._provenance_turn = ids
    return ids


def _next_id(ids: TurnIds, namespace: str) -> str:
    n = ids.counts.get(namespace, 0)
    ids.counts[namespace] = n + 1
    return f"{ids.turn}:{namespace}:{n}"


def ensure_id(world: "WorldState", event: Event | None) -> str | None:
    """Return the event's id, assigning the next deterministic one if missing."""
    if event is None:
        return None
    if not event.event_id:
        event.event_id = _next_id(_turn_ids(world), event.event_type)
    return event.event_id


def id_turn(event_id: str | None) -> int | None:
    """Turn encoded in an event or condition id (None for legacy/unknown ids)."""
    if not event_id:
        return None
    head = event_id.split(":", 1)[0]
    try:
        return int(head)
    except ValueError:
        return None


def cite(event: Event, *cause_ids: str | None) -> Event:
    """Append cause ids to ``event.causes`` (skipping None, self and duplicates)."""
    for cid in cause_ids:
        if cid and cid != event.event_id and cid not in event.causes:
            event.causes.append(cid)
    return event


# ---------------------------------------------------------------------------
# Causal index (persisted on WorldState.provenance.keys)
# ---------------------------------------------------------------------------

def pair(a: str, b: str) -> str:
    return f"{a}|{b}" if a <= b else f"{b}|{a}"


def key(kind: str, *parts: str) -> str:
    return f"{kind}:{'|'.join(parts)}"


def war_key(a: str, b: str) -> str:
    return "war:" + pair(a, b)


def remember(world: "WorldState", k: str, event: Event) -> str | None:
    """Make ``event`` the one that currently stands for ``k``."""
    eid = ensure_id(world, event)
    if eid:
        world.provenance.keys[k] = eid
    return eid


def recall(world: "WorldState", k: str, within: int | None = None) -> str | None:
    """Id registered for ``k`` (optionally only if at most ``within`` turns old)."""
    eid = world.provenance.keys.get(k)
    if eid is None or within is None:
        return eid
    t = id_turn(eid)
    if t is None or world.turn - t > within:
        return None
    return eid


def forget(world: "WorldState", k: str) -> None:
    world.provenance.keys.pop(k, None)


def episode_key(event_type: str, region: str | None, category: str | None = None) -> str:
    return f"{event_type}|{region or ''}|{category or ''}"


def open_episode(world: "WorldState", event_type: str, region: str | None,
                 category: str | None = None) -> str | None:
    """Latest kept report of the open chronic episode of this type in
    ``region``: the latest tick (a recurring famine's current strike, whose
    own causes are the conditions of that turn) or else the onset."""
    ep = world.provenance.episodes.get(episode_key(event_type, region, category))
    if ep is None:
        return None
    return ep.last_id or ep.onset_id


# ---------------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------------

# Read-only access only: provenance never builds or touches the world's
# lookup caches (civ_map, region_map, trade-route caches), because building a
# cache earlier than the simulation would can change what a later stale-cache
# read returns.

def _civ_names(world: "WorldState") -> set[str]:
    return {c.name for c in world.civilizations}


def _civ(world: "WorldState", name: str):
    for c in world.civilizations:
        if c.name == name:
            return c
    return None


def event_civs(world: "WorldState", event: Event) -> list[str]:
    """Civilizations an event involves: ``civs`` when stamped, else civ actors."""
    if event.civs:
        return list(event.civs)
    names = _civ_names(world)
    return [a for a in dict.fromkeys(event.actors) if a in names]


def event_region(event: Event) -> str | None:
    return event.region or event.shock_region


def _regions_of(world: "WorldState", civ_name: str) -> list[str]:
    civ = _civ(world, civ_name)
    return list(civ.regions) if civ is not None else []


def _wars_of(world: "WorldState", civ_name: str) -> list[str]:
    out = []
    for a, b in world.active_wars:
        if civ_name in (a, b):
            eid = recall(world, war_key(a, b))
            if eid:
                out.append(eid)
    return out


def _famines_of(world: "WorldState", civ_name: str, limit: int = 2) -> list[str]:
    """Latest reports of the open famines in the civ's regions, newest episode first."""
    eps = []
    for rname in _regions_of(world, civ_name):
        ep = world.provenance.episodes.get(episode_key("famine", rname))
        if ep is not None:
            eps.append(ep)
    eps.sort(key=lambda ep: (-ep.onset_turn, ep.onset_id))
    return [ep.last_id or ep.onset_id for ep in eps[:limit]]


# ---------------------------------------------------------------------------
# Cause rules: state-derived causes for emitters that did not stamp their own
# ---------------------------------------------------------------------------

CauseRule = Callable[["WorldState", Event], list]


def _distress(world: "WorldState", civ: str) -> list[str | None]:
    """Conditions that drain a civ's stability (the input of secession,
    rebellion and collapse checks): open famines in its regions, its PSI
    crisis, recent revolts, active wars and recent plague."""
    return [
        *_famines_of(world, civ),
        recall(world, key("psi", civ)),
        recall(world, key("revolt", civ), within=20),
        *_wars_of(world, civ),
        recall(world, key("plague", civ), within=10),
    ]


def _first_civ(world: "WorldState", ev: Event) -> str | None:
    civs = event_civs(world, ev)
    return civs[0] if civs else None


def _pair_of(world: "WorldState", ev: Event) -> tuple[str, str] | None:
    civs = event_civs(world, ev)
    return (civs[0], civs[1]) if len(civs) >= 2 else None


def _rule_famine(world: "WorldState", ev: Event) -> list:
    region = event_region(ev)
    civ = _first_civ(world, ev)
    out: list[str | None] = []
    if civ is not None:
        out.append(recall(world, key("drought", civ), within=10))
    if region is not None:
        out += [
            recall(world, key("disaster", region), within=5),
            open_episode(world, "soil_exhaustion", region),
            open_episode(world, "supply_shock", region, "food"),
            recall(world, key("siege", region), within=20),
            recall(world, key("occupation", region)),
            recall(world, key("pandemic", region), within=10),
        ]
    return out


def _rule_regional_flight(world: "WorldState", ev: Event) -> list:
    """People leave a region (climate flight, agent mass migration, brain
    drain, demographic collapse): hunger, war, disease and persecution there."""
    region = event_region(ev)
    civ = _first_civ(world, ev)
    out: list[str | None] = []
    if region is not None:
        out += [
            open_episode(world, "famine", region),
            recall(world, key("battle", region), within=3),
            recall(world, key("occupation", region)),
            recall(world, key("pandemic", region), within=10),
            recall(world, key("disaster", region), within=5),
            recall(world, key("persecution", region), within=10),
        ]
    if civ is not None:
        out.append(recall(world, key("drought", civ), within=5))
    return out


def _rule_local_unrest(world: "WorldState", ev: Event) -> list:
    region = event_region(ev)
    civ = _first_civ(world, ev)
    out: list[str | None] = []
    if region is not None:
        out += [
            open_episode(world, "famine", region),
            recall(world, key("occupation", region)),
            recall(world, key("conquest", region), within=20),
            recall(world, key("persecution", region), within=10),
        ]
    if civ is not None:
        out.append(recall(world, key("psi", civ)))
    return out


def _rule_civ_distress(world: "WorldState", ev: Event) -> list:
    civ = _first_civ(world, ev)
    return _distress(world, civ) if civ is not None else []


def _rule_secession(world: "WorldState", ev: Event) -> list:
    civs = event_civs(world, ev)
    out: list[str | None] = []
    # The parent is the civ that loses regions; actors are (parent, breakaway)
    # for secessions and (parent,) for suppressed attempts.
    if civs:
        out += _distress(world, civs[0])
        out.append(recall(world, key("legitimacy", civs[0]), within=20))
    return out


def _rule_collapse(world: "WorldState", ev: Event) -> list:
    civ = _first_civ(world, ev)
    if civ is None:
        return []
    return [*_distress(world, civ), recall(world, key("secession", civ), within=20)]


def _rule_twilight(world: "WorldState", ev: Event) -> list:
    out: list[str | None] = []
    for civ in event_civs(world, ev):
        out += [recall(world, key("collapse", civ), within=50),
                recall(world, key("twilight", civ)),
                recall(world, key("secession", civ), within=50)]
    return out


def _rule_tech_regression(world: "WorldState", ev: Event) -> list:
    civ = _first_civ(world, ev)
    if civ is None:
        return []
    return [recall(world, key("collapse", civ), within=0),
            recall(world, key("black_swan", civ), within=0),
            recall(world, key("secession", civ), within=0),
            recall(world, key("capital_loss", civ), within=0)]


def _rule_war_open(world: "WorldState", ev: Event) -> list:
    """A declaration of war: the frictions the WAR weight reads."""
    p = _pair_of(world, ev)
    if p is None:
        return []
    k = pair(*p)
    return [recall(world, "border:" + k, within=10),
            recall(world, "embargo:" + k, within=20),
            recall(world, "proxy:" + k, within=20),
            recall(world, "peace:" + k, within=30)]


def _rule_war_event(world: "WorldState", ev: Event) -> list:
    """Battles, raids and threats between a pair cite the pair's war;
    the first war event of a pair (instant-war path) is its declaration."""
    p = _pair_of(world, ev)
    if p is None:
        return []
    war = recall(world, war_key(*p))
    if war is not None:
        return [war, recall(world, key("siege", ev.region), within=10) if ev.region else None]
    return _rule_war_open(world, ev)


def _rule_civ_war(world: "WorldState", ev: Event) -> list:
    civ = _first_civ(world, ev)
    return _wars_of(world, civ) if civ is not None else []


def _rule_battle_aftermath(world: "WorldState", ev: Event) -> list:
    """Losses in a battle (a fallen general, a destroyed army, a hostage)
    cite that battle; otherwise the civ's wars."""
    region = event_region(ev)
    battle = recall(world, key("battle", region), within=0) if region else None
    if battle is not None:
        return [battle]
    return _rule_civ_war(world, ev)


def _rule_war_end(world: "WorldState", ev: Event) -> list:
    p = _pair_of(world, ev)
    return [recall(world, war_key(*p))] if p else []


def _rule_region_war(world: "WorldState", ev: Event) -> list:
    region = event_region(ev)
    if region is None:
        return _rule_war_end(world, ev)
    return [recall(world, key("siege", region), within=20), recall(world, key("battle", region), within=0)]


def _rule_occupation_end(world: "WorldState", ev: Event) -> list:
    region = event_region(ev)
    return [recall(world, key("occupation", region))] if region else []


def _rule_psi_crisis(world: "WorldState", ev: Event) -> list:
    civ = _first_civ(world, ev)
    if civ is None:
        return []
    return [recall(world, key("elite", civ), within=40),
            recall(world, key("fiscal", civ), within=30),
            *_famines_of(world, civ)]


def _rule_by_key(kind: str, within: int | None = None) -> CauseRule:
    def rule(world: "WorldState", ev: Event) -> list:
        civ = _first_civ(world, ev)
        return [recall(world, key(kind, civ), within=within)] if civ is not None else []
    rule.__name__ = f"_rule_{kind}"
    return rule


def _rule_supply_shock(world: "WorldState", ev: Event) -> list:
    region = event_region(ev)
    civ = _first_civ(world, ev)
    out: list[str | None] = []
    if region is not None:
        out += [recall(world, key("disaster", region), within=5),
                recall(world, key("siege", region), within=20),
                recall(world, key("occupation", region))]
    if civ is not None:
        out.append(recall(world, key("drought", civ), within=5))
        out += _wars_of(world, civ)
        for k, eid in sorted(world.provenance.keys.items()):
            if k.startswith("embargo:") and civ in k[len("embargo:"):].split("|"):
                t = id_turn(eid)
                if t is not None and world.turn - t <= 5:
                    out.append(eid)
    return out


def _rule_artifact_loss(world: "WorldState", ev: Event) -> list:
    out: list[str | None] = []
    for civ in event_civs(world, ev):
        out += [recall(world, key("conquered", civ), within=0),
                recall(world, key("collapse", civ), within=0)]
    if ev.region:
        out += [recall(world, key("conquest", ev.region), within=0),
                recall(world, key("occupation", ev.region), within=0)]
    return out


CAUSE_RULES: dict[str, CauseRule] = {
    # Hunger and its consequences
    "famine": _rule_famine,
    "famine_starvation": lambda w, ev: [open_episode(w, "famine", event_region(ev))],
    "supply_shock": _rule_supply_shock,
    "migration": _rule_regional_flight,
    "mass_migration": _rule_regional_flight,
    "brain_drain": _rule_regional_flight,
    "demographic_crisis": _rule_regional_flight,
    "notable_migration": _rule_regional_flight,
    "Mass Migration": lambda w, ev: [recall(w, key("persecution", ev.region))] if ev.region else [],
    "Persecution": lambda w, ev: [recall(w, key("conquest", ev.region), within=50)] if ev.region else [],
    "Schism": lambda w, ev: [recall(w, key("persecution", ev.region), within=50)] if ev.region else [],
    # Unrest and fragmentation
    "local_rebellion": _rule_local_unrest,
    "loyalty_cascade": _rule_local_unrest,
    "rebellion": _rule_civ_distress,
    "vassal_rebellion": _rule_civ_distress,
    "secession": _rule_secession,
    "secession_suppressed": _rule_secession,
    "secession_defection": lambda w, ev: [recall(w, key("secession", c), within=0)
                                          for c in event_civs(w, ev)[:1]],
    "conquest_exile": lambda w, ev: [
        *(recall(w, key("conquered", c), within=0) for c in event_civs(w, ev)[:1]),
        recall(w, key("conquest", ev.region), within=0) if ev.region else None],
    "exile_return": lambda w, ev: [recall(w, key("exile", a)) for a in ev.actors[:1]],
    "collapse": _rule_collapse,
    "twilight": _rule_twilight,
    "twilight_absorption": _rule_twilight,
    "restoration": lambda w, ev: [recall(w, key("conquered", c)) for c in event_civs(w, ev)],
    "tech_regression": _rule_tech_regression,
    # Governance (emitters stamp most of these; rules cover direct callers)
    "psi_crisis": _rule_psi_crisis,
    "revolt": _rule_by_key("psi"),
    "psi_recovery": _rule_by_key("psi"),
    "legitimacy_crisis": _rule_by_key("ambition_failed", within=10),
    "succession_crisis_resolved": lambda w, ev: [
        recall(w, key("civil_war", c), within=30) for c in event_civs(w, ev)[:1]],
    "government_transition": lambda w, ev: [
        recall(w, key("civil_war", c), within=20) for c in event_civs(w, ev)[:1]],
    # War
    "war_declared": _rule_war_open,
    "war": _rule_war_event,
    "army_raised": _rule_war_event,
    "army_destroyed": _rule_battle_aftermath,
    "army_disbanded": _rule_civ_war,
    "general_fallen": _rule_battle_aftermath,
    "hostage_taken": _rule_battle_aftermath,
    "siege_begun": _rule_war_event,
    "occupation": _rule_region_war,
    "annexation": _rule_occupation_end,
    "liberation": _rule_occupation_end,
    "occupation_revolt": _rule_occupation_end,
    "civ_conquered": _rule_war_end,
    "peace_treaty": _rule_war_end,
    "war_ended": _rule_war_end,
    "congress_peace": _rule_war_end,
    "congress_ceasefire": _rule_war_end,
    "federation_defense": _rule_war_end,
    "capital_loss": lambda w, ev: [recall(w, key("capital_taken", c), within=0)
                                   for c in event_civs(w, ev)[:1]],
    "move_capital": _rule_by_key("capital_loss", within=5),
    "temple_destroyed": _rule_civ_war,
    "scorched_earth": _rule_civ_war,
    # Disease and disaster
    "pandemic_leader_death": lambda w, ev: [recall(w, key("plague_civ", c), within=0)
                                            for c in event_civs(w, ev)[:1]],
    "drought_intensification": _rule_by_key("drought", within=10),
    "ecological_recovery": lambda w, ev: [
        open_episode(w, "soil_exhaustion", ev.region),
        recall(w, key("depletion", ev.region))] if ev.region else [],
    # Great persons' deeds cite the person's emergence
    "artifact_created": lambda w, ev: [recall(w, key("gp", a)) for a in ev.actors[:1]],
    "pilgrimage_departure": lambda w, ev: [recall(w, key("gp", a)) for a in ev.actors[:1]],
    "pilgrimage_return": lambda w, ev: [recall(w, key("pilgrimage", a)) for a in ev.actors[:1]],
    # Artifacts change hands when their holders fall
    "artifact_captured": _rule_artifact_loss,
    "artifact_lost": _rule_artifact_loss,
    "artifact_destroyed": _rule_artifact_loss,
}


# ---------------------------------------------------------------------------
# Hazard excitation (events.py): which event raised a civ's hazard
# ---------------------------------------------------------------------------

# A rolled hazard event cites the event that excited its hazard when that
# event's (decaying) excitation is at least this share of the rate the event
# was rolled at. In a Hawkes process the probability that an event was
# triggered by one excitation term is that term's share of the rate.
EXCITATION_SHARE = 0.5
EXCITATION_WITHIN = 24  # three decay time constants (tau = 8 turns)


def _decay() -> float:
    from chronicler.events import HAZARD_DECAY
    return HAZARD_DECAY


def note_excitation(world: "WorldState", civ_name: str, alphas, event: Event) -> None:
    """Record ``event`` exciting ``civ_name`` by ``alphas`` ({target: alpha}
    or (target, alpha) pairs). Per target the event with the largest current
    (decayed) contribution is kept; inhibiting (negative) terms are ignored."""
    if not event.event_id:
        return
    store = world.provenance.exciters
    decay = _decay()
    items = alphas.items() if isinstance(alphas, dict) else alphas
    for target, alpha in items:
        if alpha <= 0.0:
            continue
        k = f"{civ_name}|{target}"
        current = store.get(k)
        if current is not None and current.alpha * decay ** (world.turn - current.turn) >= alpha:
            continue
        store[k] = Exciter(event_id=event.event_id, alpha=alpha, turn=world.turn)


def excitation_cause(world: "WorldState", civ, event_type: str, rate: float) -> str | None:
    """The dominant exciting event, if its excitation carried at least
    EXCITATION_SHARE of ``rate`` (the rate the event was rolled at)."""
    exciter = world.provenance.exciters.get(f"{civ.name}|{event_type}")
    if exciter is None or not rate:
        return None
    age = world.turn - exciter.turn
    if age > EXCITATION_WITHIN:
        return None
    # Excitation is ingested at the end of its turn and decays once per turn
    # before the next roll; the net stored excitation bounds the term.
    contribution = min(exciter.alpha * _decay() ** max(0, age - 1),
                       civ.event_excitation.get(event_type, 0.0))
    if contribution < EXCITATION_SHARE * rate:
        return None
    return exciter.event_id


def great_person_causes(world: "WorldState", civ: str, role: str) -> list[str | None]:
    """The achievement each great-person threshold counts (great_persons.py)."""
    if role == "general":  # war wins clustered in a 20-turn window
        return [recall(world, key("war_win", civ), within=20)]
    if role == "scientist":  # an era advance since the last scientist (or high economy)
        tech = recall(world, key("tech", civ))
        last = recall(world, key("gp_role", civ, role))
        if tech is not None and (last is None or (id_turn(tech) or 0) >= (id_turn(last) or 0)):
            return [tech]
        return []
    if role == "prophet":  # a movement adoption or emergence
        return [recall(world, key("movement", civ), within=10)]
    return []


def leader_death_causes(world: "WorldState", civ, cause: str) -> list[str | None]:
    """Causes of a leader's death from the mortality component that drew it."""
    name = civ.name
    if cause == "battle":
        return _wars_of(world, name)
    if cause == "coup":
        return [recall(world, key("psi", name)), recall(world, key("revolt", name), within=10),
                recall(world, key("civil_war", name), within=20),
                recall(world, key("legitimacy", name), within=20)]
    if cause == "misfortune":
        exciter = world.provenance.exciters.get(f"{name}|leader_death")
        if exciter is not None and world.turn - exciter.turn <= EXCITATION_WITHIN:
            return [exciter.event_id]
    return []


# ---------------------------------------------------------------------------
# Registration: which events stand for a state other events cite
# ---------------------------------------------------------------------------

Register = Callable[["WorldState", Event], None]

_DISASTER_TYPES = frozenset({
    "earthquake", "flood", "wildfire", "sandstorm", "locust_swarm", "mine_collapse",
    "drought_intensification", "supervolcano",
})
_BLACK_SWAN_TYPES = frozenset({"pandemic", "supervolcano", "resource_discovery", "tech_accident"})
_PER_CIV_KEYS: dict[str, str] = {
    "psi_crisis": "psi", "elite_overproduction": "elite", "fiscal_crisis": "fiscal",
    "legitimacy_crisis": "legitimacy", "ambition_failed": "ambition_failed",
    "revolt": "revolt", "rebellion": "revolt", "local_rebellion": "revolt",
    "vassal_rebellion": "revolt", "civil_war": "civil_war", "collapse": "collapse",
    "secession": "secession", "leader_death": "leader_death", "drought": "drought",
    "plague": "plague", "twilight": "twilight", "capital_loss": "capital_loss",
    "vassalization": "vassal", "federation_formed": "federation",
}
_PAIR_KEYS: dict[str, str] = {
    "border_incident": "border", "embargo": "embargo", "proxy_detected": "proxy",
}
_WAR_END_TYPES = frozenset({"peace_treaty", "war_ended", "congress_peace", "congress_ceasefire"})


def _register(world: "WorldState", ev: Event) -> None:
    etype = ev.event_type
    eid = ev.event_id
    keys = world.provenance.keys
    civs = event_civs(world, ev)
    region = event_region(ev)
    per_civ = _PER_CIV_KEYS.get(etype)
    if per_civ is not None:
        for civ in civs:
            keys[key(per_civ, civ)] = eid
    if etype == "psi_recovery":
        for civ in civs:
            keys.pop(key("psi", civ), None)
    if etype in _PAIR_KEYS and len(civs) >= 2:
        keys[_PAIR_KEYS[etype] + ":" + pair(civs[0], civs[1])] = eid
    if etype == "war_declared" and len(civs) >= 2:
        keys[war_key(civs[0], civs[1])] = eid
    elif etype == "war" and len(civs) >= 2:
        wk = war_key(civs[0], civs[1])
        if wk not in keys and (civs[0], civs[1]) in _active_pairs(world):
            keys[wk] = eid  # instant-war path: the first war event declares it
        if region is not None:
            keys[key("battle", region)] = eid
    elif etype in _WAR_END_TYPES and len(civs) >= 2:
        keys.pop(war_key(civs[0], civs[1]), None)
        keys["peace:" + pair(civs[0], civs[1])] = eid
    elif etype == "siege_begun" and region is not None:
        keys[key("siege", region)] = eid
    elif etype == "occupation" and region is not None:
        keys.pop(key("siege", region), None)
        keys[key("occupation", region)] = eid
        _capital_taken(world, region, eid)
    elif etype in ("annexation", "liberation", "occupation_revolt") and region is not None:
        keys.pop(key("occupation", region), None)
        keys.pop(key("siege", region), None)
        if etype == "annexation":
            keys[key("conquest", region)] = eid
            _capital_taken(world, region, eid)
    elif etype == "civ_conquered" and len(civs) >= 2:
        keys[key("conquered", civs[1])] = eid
    elif etype in ("pandemic", "pandemic_spread"):
        if region is not None:
            keys[key("pandemic", region)] = eid
    elif etype == "epidemic" and region is not None:
        # Epidemiology onsets stand for disease in the region, so the famine
        # and flight rules (which read pandemic:<region>) cite them too.
        keys[key("pandemic", region)] = eid
        keys[key("epidemic", region, ev.shock_category or "")] = eid
    if etype in _DISASTER_TYPES:
        if region is not None:
            keys[key("disaster", region)] = eid
    if etype in _BLACK_SWAN_TYPES:
        keys[key("black_swan_world")] = eid
        for civ in civs:
            keys[key("black_swan", civ)] = eid
    if etype == "plague":
        for civ in civs:
            keys[key("plague_civ", civ)] = eid
    if etype == "Persecution" and region is not None:
        keys[key("persecution", region)] = eid
    if etype == "resource_depletion" and region is not None:
        keys[key("depletion", region)] = eid
    if etype == "war" and ev.actors and "attacker_wins" in ev.description:
        keys[key("war_win", ev.actors[0])] = eid  # what traditions counts as a win
    if etype == "tech_advancement":
        for civ in civs:
            keys[key("tech", civ)] = eid
    if etype in ("movement_adoption", "movement_emergence"):
        for civ in civs[:1]:
            keys[key("movement", civ)] = eid
    if etype == "great_person_born":
        role = ev.description.split("A great ", 1)[-1].split(" ", 1)[0]
        for civ in civs[:1]:
            keys[key("gp_role", civ, role)] = eid
    if etype == "pilgrimage_departure" and ev.actors:
        keys[key("pilgrimage", ev.actors[0])] = eid
    if etype == "conquest_exile" and ev.actors:
        keys[key("exile", ev.actors[0])] = eid


def _active_pairs(world: "WorldState") -> set[tuple[str, str]]:
    out = set()
    for a, b in world.active_wars:
        out.add((a, b))
        out.add((b, a))
    return out


def _capital_taken(world: "WorldState", region: str, eid: str) -> None:
    for civ in world.civilizations:
        if civ.capital_region == region or getattr(civ, "capital_start_of_turn", None) == region:
            world.provenance.keys[key("capital_taken", civ.name)] = eid


# ---------------------------------------------------------------------------
# Chronic episodes
# ---------------------------------------------------------------------------

class ChronicSpec(NamedTuple):
    gap: int            # max turns between reports that continue one episode
    keep_ticks: bool    # keep repeats on the timeline (a simulation consumer reads them)
    importance_cap: int | None
    label: str


# Diagnostic switch for identity proofs against pre-provenance oracles
# (tests, scripts/provenance_identity.py): ids, causes and the causal index
# are recorded as usual, but the timeline is left exactly as a
# provenance-free run would write it: chronic repeats stay (as
# ``episode="repeat"``), onset importance is not capped and no ``*_ended``
# events are added. Never set in production.
LEGACY_TIMELINE = False

# Event types that exist only to carry provenance (no simulation consumer):
# the contact edge a pandemic crossed. Dropped from a legacy timeline.
PROVENANCE_ONLY_TYPES = frozenset({"pandemic_spread"})

CHRONIC: dict[str, ChronicSpec] = {
    # Famine strikes at most every 5 turns per region (famine cooldown), and
    # traditions/factions count every strike: keep the repeats as ticks.
    "famine": ChronicSpec(5, True, None, "famine"),
    "supply_shock": ChronicSpec(1, False, 6, "shortage"),
    "economic_boom": ChronicSpec(1, False, None, "economic boom"),
    "brain_drain": ChronicSpec(1, False, None, "flight of scholars"),
    "demographic_crisis": ChronicSpec(1, False, None, "population collapse"),
    "loyalty_cascade": ChronicSpec(1, False, None, "shift of allegiance"),
    "occupation_shift": ChronicSpec(1, False, None, "change of trades"),
    "mass_migration": ChronicSpec(1, False, None, "exodus"),
    "local_rebellion": ChronicSpec(1, False, None, "uprising"),
    "migration": ChronicSpec(1, False, None, "flight"),
    "soil_exhaustion": ChronicSpec(1, False, None, "exhaustion of the soil"),
    "famine_starvation": ChronicSpec(1, False, None, "starvation"),
    "Mass Migration": ChronicSpec(1, False, None, "flight of the faithful"),
    # Epidemiology (chronicler.epidemiology): one report per turn per region
    # and pathogen (the category) while an outbreak runs; one per closed state.
    "epidemic": ChronicSpec(1, False, None, "epidemic"),
    "quarantine": ChronicSpec(1, False, None, "border closure"),
}


def _gate(world: "WorldState", ids: TurnIds, ev: Event) -> bool:
    """Fold a chronic report into its episode. Returns False to drop it."""
    spec = CHRONIC.get(ev.event_type)
    region = event_region(ev)
    if spec is None or region is None or ev.episode is not None:
        return True
    ek = episode_key(ev.event_type, region, ev.shock_category)
    episodes = world.provenance.episodes
    ep = episodes.get(ek)
    if ep is not None and ids.turn - ep.last_turn <= spec.gap:
        ep.last_turn = ids.turn
        ep.count += 1
        if not spec.keep_ticks:
            if not LEGACY_TIMELINE:
                return False
            ev.episode = "repeat"
            cite(ev, ep.onset_id)
            return True
        # A kept repeat is a new report of the same condition: it gets the
        # causes of its own turn (the cause rules), not a link to the onset.
        ev.episode = "tick"
        ep.last_id = ensure_id(world, ev)
        return True
    ev.episode = "onset"
    if spec.importance_cap is not None and ev.importance > spec.importance_cap and not LEGACY_TIMELINE:
        ev.importance = spec.importance_cap
    eid = ensure_id(world, ev)
    episodes[ek] = ChronicEpisode(
        onset_id=eid, event_type=ev.event_type, onset_turn=ids.turn, last_turn=ids.turn,
        region=region, category=ev.shock_category, civs=event_civs(world, ev),
    )
    return True


def _close_episodes(world: "WorldState", ids: TurnIds) -> list[Event]:
    out: list[Event] = []
    episodes = world.provenance.episodes
    for ek in sorted(episodes):
        ep = episodes[ek]
        spec = CHRONIC.get(ep.event_type)
        gap = spec.gap if spec is not None else 1
        if ep.last_turn == ids.turn or ids.turn - ep.last_turn < gap:
            continue
        del episodes[ek]
        duration = max(1, ids.turn - ep.onset_turn)
        label = spec.label if spec is not None else ep.event_type.replace("_", " ")
        what = f"{ep.category} {label}" if ep.category else label
        out.append(Event(
            turn=world.turn, event_type=f"{ep.event_type}_ended", actors=list(ep.civs),
            description=(f"The {what} in {ep.region} ends after {duration} "
                         f"turn{'s' if duration != 1 else ''} ({ep.count} report"
                         f"{'s' if ep.count != 1 else ''})."),
            importance=4 if ep.event_type == "famine" else 3,
            region=ep.region, episode="end", duration=duration, causes=[ep.onset_id],
        ))
    return out


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------

# ActiveCondition.condition_type -> event type that creates it.
CONDITION_SOURCES: dict[str, str] = {
    "drought": "drought", "plague": "plague", "volcanic_winter": "supervolcano",
    "capital_relocation": "move_capital",
}


def _observe_conditions(world: "WorldState", ids: TurnIds) -> None:
    conds = world.provenance.conditions
    for cond in world.active_conditions:
        if cond.condition_id:
            continue
        cond.condition_id = _next_id(ids, "condition." + cond.condition_type)
        cond.onset_turn = ids.turn
        source = CONDITION_SOURCES.get(cond.condition_type) or (
            "leader_death" if cond.condition_type.endswith("_legacy") else cond.condition_type)
        cond.cause_id = ids.last_by_type.get(source)
        conds[cond.condition_id] = OpenCondition(
            condition_type=cond.condition_type, affected_civs=list(cond.affected_civs),
            onset_turn=ids.turn, cause_id=cond.cause_id,
        )


def _close_conditions(world: "WorldState", ids: TurnIds) -> list[Event]:
    conds = world.provenance.conditions
    if not conds:
        return []
    live = {c.condition_id for c in world.active_conditions}
    out: list[Event] = []
    for cid in sorted(conds):
        if cid in live:
            continue
        rec = conds.pop(cid)
        duration = max(1, ids.turn - rec.onset_turn)
        label = rec.condition_type.replace("_", " ")
        who = ", ".join(rec.affected_civs) or "the land"
        out.append(Event(
            turn=world.turn, event_type=f"{rec.condition_type}_ended",
            actors=[a for a in rec.affected_civs if a in _civ_names(world)],
            description=f"The {label} afflicting {who} lifts after {duration} "
                        f"turn{'s' if duration != 1 else ''}.",
            importance=3, episode="end", duration=duration,
            causes=[c for c in (rec.cause_id,) if c],
        ))
    return out


# ---------------------------------------------------------------------------
# Turn-loop hooks
# ---------------------------------------------------------------------------

def begin_turn(world: "WorldState") -> None:
    """Start observing a turn: events appended from here on belong to it."""
    ids = _turn_ids(world)
    ids.watermark = min(ids.watermark, len(world.events_timeline))
    ids.turn_start = min(ids.turn_start, ids.watermark)


# Types whose emitter may stamp some causes (the exciting event, an upstream
# shortage) while the state rule still adds the conditions the driver read.
MERGE_RULE_TYPES = frozenset({"rebellion", "migration", "supply_shock"})


def _observe_one(world: "WorldState", ids: TurnIds, ev: Event, gate: bool) -> bool:
    if ev.event_id and ev.event_id in ids.observed:
        return True
    if gate and not _gate(world, ids, ev):
        return False
    eid = ensure_id(world, ev)
    ids.observed.add(eid)
    if not ev.causes or ev.event_type in MERGE_RULE_TYPES:
        rule = CAUSE_RULES.get(ev.event_type)
        if rule is not None:
            cite(ev, *rule(world, ev))
    _register(world, ev)
    ids.last_by_type[ev.event_type] = eid
    return True


def observe(world: "WorldState", events: Iterable[Event] = ()) -> list[Event]:
    """Observe one phase's output in emission order.

    First the events the phase appended straight to ``world.events_timeline``
    (unfiltered: they are already committed), then the events it returned.
    Each gets an id, causes (when the emitter left them empty) and is
    registered in the causal index; chronic repeats among the returned events
    are folded into their episode. Returns the returned events to keep, in
    their original order.
    """
    ids = _turn_ids(world)
    timeline = world.events_timeline
    if ids.watermark > len(timeline):
        ids.watermark = len(timeline)
    for ev in timeline[ids.watermark:]:
        _observe_one(world, ids, ev, gate=False)
    ids.watermark = len(timeline)
    kept = [ev for ev in events if _observe_one(world, ids, ev, gate=True)
            and not (LEGACY_TIMELINE and ev.event_type in PROVENANCE_ONLY_TYPES)]
    _observe_conditions(world, ids)
    return kept


def observe_now(world: "WorldState", event: Event) -> str | None:
    """Observe one event at emission (for emitters whose same-phase chains
    must resolve in order). Never folds chronic repeats."""
    _observe_one(world, _turn_ids(world), event, gate=False)
    return event.event_id


def end_turn(world: "WorldState") -> list[Event]:
    """Close finished episodes and conditions; return their end events.

    Call after the last phase, before the final timeline commit. The end
    events are already observed. Also gives an id to any event of this turn
    that reached the timeline without being observed.
    """
    ids = _turn_ids(world)
    observe(world)
    ended = _close_episodes(world, ids) + _close_conditions(world, ids)
    if LEGACY_TIMELINE:
        return []
    for ev in ended:
        _observe_one(world, ids, ev, gate=False)
    return ended


def finish_turn(world: "WorldState") -> None:
    """After the final commit: id any stragglers of this turn."""
    ids = _turn_ids(world)
    timeline = world.events_timeline
    start = min(ids.turn_start, len(timeline))
    for ev in timeline[start:]:
        if not ev.event_id:
            _observe_one(world, ids, ev, gate=False)
    ids.watermark = len(timeline)


# ---------------------------------------------------------------------------
# Read side: graph helpers for the curator, narrator and viewer
# ---------------------------------------------------------------------------

def backfill_ids(events: Iterable[Event]) -> dict[int, str]:
    """Deterministic read-time ids for events that have none (old saves).

    Returns ``{id(event): legacy_id}``; legacy ids start with ``L`` so they
    can never collide with recorded ids. Events are not modified.
    """
    counts: dict[tuple[int, str], int] = {}
    out: dict[int, str] = {}
    for ev in events:
        if ev.event_id:
            continue
        k = (ev.turn, ev.event_type)
        n = counts.get(k, 0)
        counts[k] = n + 1
        out[id(ev)] = f"L{ev.turn}:{ev.event_type}:{n}"
    return out
