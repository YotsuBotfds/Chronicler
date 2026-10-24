"""Diplomacy: diplomatic memory, treaties and the polity ladder (``--diplomacy``).

The simulation decides outcomes; this module models how civilizations
remember each other, what they agree to and how subject polities move toward
or away from their overlords. It is default-off behind
``WorldState.diplomacy`` (CLI ``--diplomacy``, persisted on the world so a
resumed run keeps it). With the switch off nothing here runs and every
output is byte-identical to the pre-diplomacy simulation.

Memory (``Relationship.memory``; directed: how *a* regards *b*)
    Trust in [-100, 100], goodwill and six grievance stocks
    (:data:`chronicler.diplomacy_state.GRIEVANCE_KINDS`), each decaying with
    its own half-life. Inputs are read from state once per turn (battles,
    occupations, land that changed hands, border incidents, persecution,
    embargoes, trade flow, alliances) or recorded where they happen (war
    declarations, breaches, refused calls to arms, aid). Memory caps how
    warm a disposition can get, nudges disposition drift, raises revanchist
    war targets, feeds the capped action-weight bucket and every acceptance
    decision.

Treaties (``DiplomacyState.treaties``)
    ``peace`` (emitted by the war package), ``non_aggression``, defensive
    ``alliance``, ``trade_pact`` and ``tribute`` (a war's tribute paid in
    installments). Each has terms, a start and an expiry and can be broken;
    breaking one costs trust (also with third parties), prestige and
    stability and leaves a grievance. Offers are made through the DIPLOMACY
    action and take effect only when the target's utility is positive.

Polity ladder (``VassalRelation.stage``)
    ``client`` -> ``vassal`` -> ``union`` (personal union) -> annexation.
    Each stage has its own tribute and constraints. It generalizes the
    twilight tributary step (``politics.prepare_twilight_absorption``):
    declining or unviable states become clients of a stable neighbour instead
    of being absorbed at once, a capitulation that would extinguish a state
    makes it a vassal, and only an integrated union is annexed. Subjects
    loosen their bonds when the overlord weakens; the existing vassal
    rebellion (Rust politics step) still ends any stage.

All randomness uses ``random.Random(stable_hash_int("diplomacy", <namespace>,
seed, turn, ...))``. Stat changes go through the accumulator with the
existing categories. Civilization and region identity are indices.
See ``docs/integration/diplomacy.md``.
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING, Iterable, NamedTuple

from chronicler import provenance as prov
from chronicler.diplomacy_state import (
    BORDER, EMBARGO, FAITH, GRIEVANCE_KINDS, OCCUPATION, TREATY, TREATY_KINDS, WAR,
    DiplomacyState, DiplomaticMemory, Treaty,
)
from chronicler.models import ActionType, Disposition, Event, NamedEvent, VassalRelation
from chronicler.utils import STAT_FLOOR, civ_index, clamp, stable_hash_int

if TYPE_CHECKING:  # pragma: no cover
    from chronicler.models import Civilization, Relationship, WorldState

# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

#: Default for worlds newly created by the CLI/batch/live entry points
#: (``--diplomacy`` opts in; loaded worlds keep their saved setting).
DEFAULT_ENABLED_FOR_NEW_WORLDS = False


def diplomacy_enabled(world) -> bool:
    """True only for a real diplomacy state (mocks and ``None`` read as off)."""
    return isinstance(getattr(world, "diplomacy", None), DiplomacyState)


def set_diplomacy_enabled(world: "WorldState", enabled: bool) -> None:
    """Enable (creating an empty state) or disable diplomacy on a world.

    Disabling also drops the dormant memory and ladder fields, so a world
    switched off carries no diplomacy data.
    """
    if enabled:
        if world.diplomacy is None:
            world.diplomacy = DiplomacyState()
        return
    world.diplomacy = None
    for rels in world.relationships.values():
        for rel in rels.values():
            rel.memory = None
    for vr in world.vassal_relations:
        vr.stage = vr.stage_turn = vr.integration = vr.crown = None


# ---------------------------------------------------------------------------
# Parameters ([CALIBRATE]; documented in docs/integration/diplomacy.md)
# ---------------------------------------------------------------------------

#: Grievance half-lives in turns, per GRIEVANCE_KINDS.
GRIEVANCE_HALF_LIFE: tuple[float, ...] = (40.0, 60.0, 50.0, 12.0, 30.0, 15.0)
GOODWILL_HALF_LIFE = 25.0
#: Trust relaxes toward 0 by this retention per turn.
TRUST_RETENTION = 0.99
TRUST_MIN, TRUST_MAX = -100.0, 100.0
#: Stored values are rounded to this many decimals; smaller stocks drop to 0.
QUANTUM_DIGITS = 4
STOCK_EPSILON = 0.01

# Grievance inputs.
GRIEVANCE_WAR_DECLARED = 8.0
GRIEVANCE_BATTLE_LOST = 2.0
GRIEVANCE_BATTLE_FOUGHT = 1.0
GRIEVANCE_BATTLE_CASUALTIES = 10.0   # times the side's losses over its soldiers
GRIEVANCE_INSTANT_DEFEAT = 6.0       # instant-war path (--no-campaigns)
GRIEVANCE_OCCUPIED_TURN = 1.5        # per turn a region of ours is occupied
GRIEVANCE_LAND_LOST = 12.0           # per region that passes to the other civ
GRIEVANCE_CAPITAL_LOST = 8.0
GRIEVANCE_SUBJUGATION = 10.0
GRIEVANCE_BREACH = 25.0
GRIEVANCE_REVOLT = 20.0
GRIEVANCE_ABANDONED = 8.0            # an overlord that did not defend its subject
GRIEVANCE_BORDER = 3.0
GRIEVANCE_PERSECUTION = 2.0          # times the persecution intensity, per region
GRIEVANCE_PERSECUTED_PEOPLE = 1.0
GRIEVANCE_EMBARGO_IMPOSED = 4.0
GRIEVANCE_EMBARGO_TURN = 1.0

# Goodwill inputs.
GOODWILL_TRADE_MAX = 0.5             # per turn, at F_ab >= GOODWILL_TRADE_SCALE * max
GOODWILL_TRADE_SCALE = 20.0
GOODWILL_TRADE_MIN_FLOW = 1.0
GOODWILL_ROUTE = 0.3                 # --no-contact-ledger: per turn with an active route
GOODWILL_ALLIANCE = 0.5
GOODWILL_TRADE_PACT = 0.2
GOODWILL_KEPT = 3.0                  # a treaty kept to its expiry
GOODWILL_AID_PER_TREASURY = 0.5
GOODWILL_DEFENDED = 5.0

# Trust inputs.
TRUST_TREATY_TURN = 0.25
TRUST_KEPT = 5.0
TRUST_BREACH_VICTIM = -35.0
TRUST_BREACH_WITNESS = -5.0          # every other living civ: reputation
TRUST_REFUSED_CALL = -10.0           # on top of the breach
TRUST_DEFAULT = -15.0
TRUST_REVOLT = -30.0
TRUST_AGGRESSION = -10.0
TRUST_DEFENDED = 10.0
TRUST_AID = 2.0

#: Disposition ceilings by effective grievance (grievance - offset x goodwill).
GOODWILL_OFFSET = 0.5
GRIEVANCE_CEILINGS: tuple[tuple[float, Disposition], ...] = (
    (70.0, Disposition.SUSPICIOUS), (40.0, Disposition.NEUTRAL), (20.0, Disposition.FRIENDLY),
)
TRUST_CEILINGS: tuple[tuple[float, Disposition], ...] = (
    (-50.0, Disposition.NEUTRAL), (-25.0, Disposition.FRIENDLY),
)
#: Disposition drift from memory (accumulates into disposition_drift, threshold 10).
DRIFT_GRIEVANCE = 20.0
DRIFT_GOODWILL = 10.0

# Treaties.
TREATY_DURATION: dict[str, int] = {
    "peace": 20, "non_aggression": 30, "alliance": 40, "trade_pact": 30, "tribute": 0,
}
PROTECTING_KINDS = ("peace", "non_aggression", "alliance")
RENEWABLE_KINDS = ("non_aggression", "alliance", "trade_pact")
TREATY_LABELS: dict[str, str] = {
    "peace": "peace", "non_aggression": "non-aggression pact", "alliance": "defensive alliance",
    "trade_pact": "trade pact", "tribute": "tribute", "client": "protectorate",
}
TREATY_IMPORTANCE: dict[str, int] = {
    "peace": 6, "non_aggression": 5, "alliance": 6, "trade_pact": 4, "tribute": 5,
}
REJECT_COOLDOWN = 8
OFFER_MIN_UTILITY = 0.05
#: A proposer sounds the target out first: it makes an offer only when its
#: estimate of the target's utility (without the target's private noise)
#: is above this.
OFFER_MIN_ESTIMATE = -0.1
ACCEPT_NOISE = 0.2
BREACH_STABILITY = 5
BREACH_PRESTIGE = 10
TRIBUTE_INSTALLMENTS = 8
TRIBUTE_MAX_MISSED = 2
AID_MIN_TREASURY = 60
AID_MAX = 10
AID_COOLDOWN = 10
AGGRESSIVE_TRAITS = frozenset({"aggressive", "bold", "zealous", "ambitious"})

# Polity ladder.
CLIENT_TRIBUTE_RATE = 0.05
UNION_TRIBUTE_RATE = 0.25
LADDER_MIN_TURNS = {"client": 15, "vassal": 20, "union": 20}
#: A subject on the fast track (structurally unviable, or down to one region:
#: the states the old paths absorb outright) needs only these turns per
#: stage, no integration and an overlord merely stronger than itself, so it
#: is annexed on about the old tributary's 30-turn timescale.
LADDER_FAST_TURNS = {"client": 6, "vassal": 8, "union": 6}
FAST_POWER_RATIO = 1.0
UNION_MIN_INTEGRATION = 20.0
ANNEX_MIN_INTEGRATION = 40.0
FAST_MIN_INTEGRATION = 0.0
ANNEX_MAX_REGIONS = 3
PROMOTE_POWER_RATIO = 1.5
# Stability thresholds are set against living hybrid worlds, where civ
# stability runs at about 20-40 (median about 29).
PROMOTE_MIN_STABILITY = 25
ANNEX_MIN_STABILITY = 22
#: A would-be absorber this stable takes a declining neighbour as a client
#: (the legacy tributary step needs more than 40, which living worlds rarely reach).
CLIENT_MIN_OVERLORD_STABILITY = 20
LADDER_COOLDOWN = 5
WEAK_STABILITY = 20
WEAK_POWER_RATIO = 0.75
WEAK_DEFEAT_TURNS = 10
LOOSEN_CHANCE = {"client": 0.10, "vassal": 0.12, "union": 0.15}
CROWN_KEEP_INTEGRATION = 40.0
CROWN_PART_CHANCE = 0.35
LOOSEN_STABILITY = 5
INTEGRATION_STAGE_RATE = {"client": 0.5, "vassal": 1.0, "union": 1.5}

POWER_MILITARY_FLOOR = 10.0
#: A subject bond is at least this old before it can loosen.
LOOSEN_MIN_TURNS = 5
WEAKNESS_TEXT = {
    "unrest": "torn by unrest", "outgrown": "which it has outgrown",
    "defeat": "humbled in war", "crisis": "in the grip of crisis",
}

_ORDER: list[Disposition] = list(Disposition)  # HOSTILE .. ALLIED
_HOSTILE = (Disposition.HOSTILE, Disposition.SUSPICIOUS)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _q(value: float) -> float:
    return round(value, QUANTUM_DIGITS) if abs(value) >= STOCK_EPSILON else 0.0


def _rng(world, namespace: str, *parts) -> random.Random:
    return random.Random(stable_hash_int("diplomacy", namespace, world.seed, world.turn, *parts))


def _noise(world, namespace: str, *parts) -> float:
    return (_rng(world, namespace, *parts).random() - 0.5) * 2.0 * ACCEPT_NOISE


def _bump(state: DiplomacyState, key: str, n: int = 1) -> None:
    state.counts[key] = state.counts.get(key, 0) + n


def _living(world) -> list[tuple[int, "Civilization"]]:
    return [(i, c) for i, c in enumerate(world.civilizations) if c.regions]


def _idx(world, name: str | None) -> int | None:
    if name is None:
        return None
    return world.civ_index_map.get(name)


def _power_of(military: float, civ: "Civilization") -> float:
    size = 1.0 + 0.1 * min(10, max(0, len(civ.regions) - 1))
    people = (max(1, civ.population) / 100.0) ** 0.5
    return ((max(0.0, float(military)) + POWER_MILITARY_FLOOR)
            * (0.75 + clamp(civ.stability, 0, 100) / 200.0) * size * people)


def power(civ: "Civilization") -> float:
    """Rough national strength: military (floored, since the agent-mode
    military stat swings with soldier counts), steadied by stability, scaled
    by size and population."""
    return _power_of(civ.military, civ)


def _perceived_power(world, observer: "Civilization", target: "Civilization") -> float | None:
    """``target``'s power as ``observer`` perceives its military (None if unknown)."""
    from chronicler.intelligence import get_perceived_stat
    mil = get_perceived_stat(observer, target, "military", world)
    if mil is None:
        return None
    return _power_of(mil, target)


def _at_war(world, a: str, b: str) -> bool:
    return (a, b) in world.active_wars or (b, a) in world.active_wars


def _wars_of(world, name: str) -> list[str]:
    out = []
    for a, b in world.active_wars:
        if a == name:
            out.append(b)
        elif b == name:
            out.append(a)
    return out


def _rel(world, a: str, b: str) -> "Relationship | None":
    return world.relationships.get(a, {}).get(b)


def _disp(world, a: str, b: str) -> int:
    rel = _rel(world, a, b)
    return _ORDER.index(rel.disposition) if rel is not None else _ORDER.index(Disposition.NEUTRAL)


def _add_stat(world, civ, stat: str, delta: float, category: str, acc=None) -> None:
    if not delta:
        return
    if acc is not None:
        acc.add(civ_index(world, civ.name), civ, stat, delta, category)
    elif stat in ("treasury", "prestige"):
        value = int(getattr(civ, stat) + delta)
        setattr(civ, stat, max(0, value) if stat == "prestige" else value)
    else:
        setattr(civ, stat, clamp(int(getattr(civ, stat) + delta), STAT_FLOOR.get(stat, 0), 100))


def _projected_treasury(world, civ, acc=None) -> int:
    """Treasury including keep-category changes already queued this turn."""
    value = float(civ.treasury)
    if acc is not None:
        idx = civ_index(world, civ.name)
        start = getattr(acc, "_keep_applied_up_to", 0)
        for change in getattr(acc, "_changes", ())[start:]:
            if change.civ_id == idx and change.stat == "treasury" and change.category == "keep":
                value += change.delta
    return int(value)


def _emit_now(world, event: Event, causes: Iterable[str | None] = ()) -> Event:
    """Stamp causes and observe at emission (ids follow emission order)."""
    prov.cite(event, *causes)
    prov.observe_now(world, event)
    return event


def _subject_of(world) -> dict[str, VassalRelation]:
    return {vr.vassal: vr for vr in world.vassal_relations}


def _adjacent(world, a: "Civilization", b: "Civilization") -> bool:
    region_map = world.region_map
    own_b = set(b.regions)
    for rn in a.regions:
        region = region_map.get(rn)
        if region is not None and any(adj in own_b for adj in region.adjacencies):
            return True
    return False


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

def memory(world, holder: str, other: str, create: bool = False) -> DiplomaticMemory | None:
    """``holder``'s memory of ``other`` (created on demand when ``create``)."""
    rel = _rel(world, holder, other)
    if rel is None:
        return None
    if rel.memory is None and create:
        rel.memory = DiplomaticMemory()
    return rel.memory


def add_grievance(world, holder: str, other: str, kind: int, amount: float) -> None:
    if amount <= 0 or holder == other:
        return
    mem = memory(world, holder, other, create=True)
    if mem is not None:
        mem.grievance[kind] = _q(mem.grievance[kind] + amount)


def add_goodwill(world, holder: str, other: str, amount: float) -> None:
    if amount <= 0 or holder == other:
        return
    mem = memory(world, holder, other, create=True)
    if mem is not None:
        mem.goodwill = _q(mem.goodwill + amount)


def adjust_trust(world, holder: str, other: str, delta: float) -> None:
    if not delta or holder == other:
        return
    mem = memory(world, holder, other, create=True)
    if mem is not None:
        mem.trust = _q(max(TRUST_MIN, min(TRUST_MAX, mem.trust + delta)))


def grievance(world, holder: str, other: str, kinds: Iterable[int] | None = None) -> float:
    mem = memory(world, holder, other)
    if mem is None:
        return 0.0
    if kinds is None:
        return mem.total_grievance()
    return sum(mem.grievance[k] for k in kinds)


def trust(world, holder: str, other: str) -> float:
    mem = memory(world, holder, other)
    return mem.trust if mem is not None else 0.0


def goodwill(world, holder: str, other: str) -> float:
    mem = memory(world, holder, other)
    return mem.goodwill if mem is not None else 0.0


def effective_grievance(mem: DiplomaticMemory | None) -> float:
    if mem is None:
        return 0.0
    return mem.total_grievance() - GOODWILL_OFFSET * mem.goodwill


def _decay_memories(world) -> None:
    factors = tuple(0.5 ** (1.0 / h) for h in GRIEVANCE_HALF_LIFE)
    gw = 0.5 ** (1.0 / GOODWILL_HALF_LIFE)
    for rels in world.relationships.values():
        for rel in rels.values():
            mem = rel.memory
            if mem is None:
                continue
            mem.grievance = [_q(v * f) for v, f in zip(mem.grievance, factors)]
            mem.goodwill = _q(mem.goodwill * gw)
            mem.trust = _q(mem.trust * TRUST_RETENTION)


def disposition_ceiling(mem: DiplomaticMemory | None) -> Disposition:
    """The warmest disposition this memory allows."""
    cap = len(_ORDER) - 1
    if mem is None:
        return _ORDER[cap]
    e = effective_grievance(mem)
    for threshold, disp in GRIEVANCE_CEILINGS:
        if e >= threshold:
            cap = min(cap, _ORDER.index(disp))
            break
    for threshold, disp in TRUST_CEILINGS:
        if mem.trust <= threshold:
            cap = min(cap, _ORDER.index(disp))
            break
    return _ORDER[cap]


# ---------------------------------------------------------------------------
# Treaties
# ---------------------------------------------------------------------------

def treaties_between(world, a: int, b: int, kinds: Iterable[str] | None = None) -> list[Treaty]:
    """Active treaties between civ indices ``a`` and ``b``."""
    if not diplomacy_enabled(world):
        return []
    pair = {a, b}
    wanted = None if kinds is None else set(kinds)
    return [t for t in world.diplomacy.treaties
            if t.status == "active" and set(t.parties) == pair
            and (wanted is None or t.kind in wanted)]


def _other_party(treaty: Treaty, idx: int) -> int:
    return treaty.parties[1] if treaty.parties[0] == idx else treaty.parties[0]


def _treaty_name(world, a: "Civilization", b: "Civilization", kind: str) -> str:
    from chronicler.named_events import generate_treaty_name
    return generate_treaty_name(a.name, b.name, world,
                                seed=stable_hash_int("diplomacy", "treaty_name", world.seed, kind))


def _new_treaty(world, kind: str, parties: list[int], name: str, *, duration: int | None,
                terms: dict | None = None, event_id: str = "") -> Treaty:
    state = world.diplomacy
    dur = TREATY_DURATION[kind] if duration is None else duration
    treaty = Treaty(
        treaty_id=state.next_treaty_id, kind=kind, parties=list(parties), name=name,
        start_turn=world.turn, expiry_turn=(world.turn + dur) if dur else None,
        terms=dict(terms or {}), event_id=event_id,
    )
    state.next_treaty_id += 1
    state.treaties.append(treaty)
    _bump(state, "signed:" + kind)
    civs = world.civilizations
    for x, y in ((parties[0], parties[1]), (parties[1], parties[0])):
        rel = _rel(world, civs[x].name, civs[y].name)
        if rel is not None and name and name not in rel.treaties:
            rel.treaties.append(name)
    return treaty


def sign_treaty(world, kind: str, a_idx: int, b_idx: int, *, causes: Iterable[str | None] = (),
                terms: dict | None = None) -> tuple[Treaty, Event]:
    """Sign a non-war treaty (non-aggression, alliance, trade pact) and emit it."""
    a, b = world.civilizations[a_idx], world.civilizations[b_idx]
    name = _treaty_name(world, a, b, kind)
    treaty = _new_treaty(world, kind, sorted([a_idx, b_idx]), name, duration=None,
                         terms={"proposer": a_idx, **(terms or {})})
    label = TREATY_LABELS[kind]
    event = Event(
        turn=world.turn, event_type="treaty_signed", actors=[a.name, b.name],
        description=f"{a.name} and {b.name} sign {name}, a {label} for "
                    f"{TREATY_DURATION[kind]} turns.",
        importance=TREATY_IMPORTANCE[kind],
    )
    _emit_now(world, event, causes)
    treaty.event_id = event.event_id
    world.named_events.append(NamedEvent(
        name=name, event_type="treaty", turn=world.turn, actors=[a.name, b.name],
        description=f"{a.name} and {b.name} sign {name} ({label})", importance=5,
    ))
    return treaty, event


def break_treaty(world, treaty: Treaty, breaker_idx: int, *, reason: str, acc=None,
                 causes: Iterable[str | None] = ()) -> Event:
    """Mark ``treaty`` broken by ``breaker_idx`` and apply the consequences."""
    state = world.diplomacy
    civs = world.civilizations
    victim_idx = _other_party(treaty, breaker_idx)
    breaker, victim = civs[breaker_idx], civs[victim_idx]
    treaty.status = "broken"
    treaty.ended_turn = world.turn
    treaty.broken_by = breaker_idx
    _bump(state, "broken:" + treaty.kind)
    add_grievance(world, victim.name, breaker.name, TREATY, GRIEVANCE_BREACH)
    adjust_trust(world, victim.name, breaker.name, TRUST_BREACH_VICTIM)
    for _, other in _living(world):
        if other.name not in (breaker.name, victim.name):
            adjust_trust(world, other.name, breaker.name, TRUST_BREACH_WITNESS)
    if breaker.regions:
        _add_stat(world, breaker, "stability", -BREACH_STABILITY, "guard-shock", acc)
        _add_stat(world, breaker, "prestige", -min(breaker.prestige, BREACH_PRESTIGE), "keep", acc)
    event = Event(
        turn=world.turn, event_type="treaty_broken", actors=[breaker.name, victim.name],
        description=f"{breaker.name} breaks {treaty.name or 'its ' + TREATY_LABELS[treaty.kind]} "
                    f"with {victim.name}: {reason}.",
        importance=7,
    )
    _emit_now(world, event, (treaty.event_id, *causes))
    treaty.end_event_id = event.event_id
    prov.remember(world, "breach:" + prov.pair(breaker.name, victim.name), event)
    return event


def _end_treaty(world, treaty: Treaty, status: str) -> None:
    treaty.status = status
    treaty.ended_turn = world.turn
    _bump(world.diplomacy, f"{status}:{treaty.kind}")


def protecting_treaties(world, civ: "Civilization", target: "Civilization") -> list[Treaty]:
    a, b = _idx(world, civ.name), _idx(world, target.name)
    if a is None or b is None:
        return []
    return treaties_between(world, a, b, PROTECTING_KINDS)


def trade_pact_pairs(world) -> set[tuple[str, str]]:
    """Name pairs (sorted) bound by an active trade pact."""
    if not diplomacy_enabled(world):
        return set()
    civs = world.civilizations
    out = set()
    for t in world.diplomacy.treaties:
        if t.status == "active" and t.kind == "trade_pact":
            a, b = civs[t.parties[0]].name, civs[t.parties[1]].name
            out.add((a, b) if a < b else (b, a))
    return out


# ---------------------------------------------------------------------------
# War package hooks
# ---------------------------------------------------------------------------

def on_campaign_peace(world, record, peace_event: Event | None, *,
                      tribute_total: int = 0) -> list[Treaty]:
    """A campaign peace (``war.peace.conclude_peace``): record its treaties.

    The peace event already narrates the terms, so no further event is
    emitted. A vassalizing peace makes no peace treaty: the ladder's vassal
    relation replaces it. ``tribute_total`` > 0 adds a tribute treaty paid in
    installments from the next turn.
    """
    if not diplomacy_enabled(world) or record.vassalized:
        return []
    a, b = _idx(world, record.parties[0]), _idx(world, record.parties[1])
    if a is None or b is None:
        return []
    eid = peace_event.event_id if peace_event is not None else ""
    winner = _idx(world, record.winner)
    region_index = {r.name: i for i, r in enumerate(world.regions)}
    terms = {
        "outcome": record.kind, "winner": -1 if winner is None else winner, "aim": record.aim,
        "ceded": [region_index[n] for n in record.regions_ceded if n in region_index],
        "paid": record.treasury_paid,
    }
    out = [_new_treaty(world, "peace", sorted([a, b]), record.name, duration=None,
                       terms=terms, event_id=eid)]
    if tribute_total > 0 and winner is not None:
        payer = b if winner == a else a
        installment = -(-tribute_total // TRIBUTE_INSTALLMENTS)
        out.append(_new_treaty(
            world, "tribute", [payer, winner], record.name, duration=0, event_id=eid,
            terms={"total": tribute_total, "installment": installment,
                   "remaining": TRIBUTE_INSTALLMENTS, "paid": 0, "missed": 0},
        ))
    return out


def on_external_peace(world, a_name: str, b_name: str, event: Event | None) -> Treaty | None:
    """A war ended outside negotiated campaign peace (congress, diplomacy): a peace treaty."""
    if not diplomacy_enabled(world):
        return None
    a, b = _idx(world, a_name), _idx(world, b_name)
    if a is None or b is None or not world.civilizations[a].regions or not world.civilizations[b].regions:
        return None
    if treaties_between(world, a, b, ("peace",)):
        return None
    return _new_treaty(world, "peace", sorted([a, b]), "", duration=None,
                       terms={"outcome": "external", "winner": -1},
                       event_id=event.event_id if event is not None else "")


def collect_treaty_tribute(world, acc=None) -> list[Event]:
    """Phase 2: tribute installments; a default or a repudiation breaks the treaty."""
    if not diplomacy_enabled(world):
        return []
    events: list[Event] = []
    civs = world.civilizations
    for treaty in [t for t in world.diplomacy.treaties if t.status == "active" and t.kind == "tribute"]:
        payer, recipient = civs[treaty.parties[0]], civs[treaty.parties[1]]
        if not payer.regions or not recipient.regions:
            _end_treaty(world, treaty, "ended")
            continue
        if treaty.start_turn >= world.turn:
            continue  # installments start the turn after the peace
        terms = treaty.terms
        # A payer that has grown stronger than its creditor may repudiate.
        repudiate = (0.6 * (power(payer) / power(recipient) - 1.3)
                     + grievance(world, payer.name, recipient.name) / 50.0
                     - trust(world, payer.name, recipient.name) / 100.0 - 0.3
                     + _noise(world, "repudiate", treaty.treaty_id))
        if repudiate > 0:
            adjust_trust(world, recipient.name, payer.name, TRUST_DEFAULT)
            events.append(break_treaty(world, treaty, treaty.parties[0],
                                       reason="it repudiates the tribute", acc=acc))
            continue
        due = int(terms["installment"])
        paid = min(due, max(0, _projected_treasury(world, payer, acc)))
        if paid:
            _add_stat(world, payer, "treasury", -paid, "keep", acc)
            _add_stat(world, recipient, "treasury", paid, "keep", acc)
        terms["paid"] = int(terms["paid"]) + paid
        terms["remaining"] = int(terms["remaining"]) - 1
        if paid < due:
            terms["missed"] = int(terms["missed"]) + 1
            if terms["missed"] >= TRIBUTE_MAX_MISSED:
                adjust_trust(world, recipient.name, payer.name, TRUST_DEFAULT)
                events.append(break_treaty(world, treaty, treaty.parties[0],
                                           reason="it defaults on its tribute", acc=acc))
                continue
        if terms["remaining"] <= 0:
            _end_treaty(world, treaty, "expired")
            adjust_trust(world, recipient.name, payer.name, TRUST_KEPT)
            event = Event(
                turn=world.turn, event_type="treaty_expired", actors=[payer.name, recipient.name],
                description=f"{payer.name} completes its tribute of {terms['paid']} to "
                            f"{recipient.name} under {treaty.name or 'the peace'}.",
                importance=3,
            )
            events.append(_emit_now(world, event, (treaty.event_id,)))
            treaty.end_event_id = event.event_id
    return events


def war_guard(world, civ: "Civilization", target: "Civilization") -> tuple[bool, list[Treaty]]:
    """May ``civ`` pick ``target`` for a new war, and which treaties would it break?"""
    if not diplomacy_enabled(world) or _at_war(world, civ.name, target.name):
        return True, []
    vr = _subject_of(world).get(target.name)
    if vr is not None and vr.overlord == civ.name:
        return False, []  # an overlord does not make war on its own subject
    protecting = protecting_treaties(world, civ, target)
    if not protecting:
        return True, []
    if breach_utility(world, civ, target, protecting) > 0:
        return True, protecting
    return False, []


def breach_utility(world, civ: "Civilization", target: "Civilization", treaties: list[Treaty]) -> float:
    """``civ``'s utility of breaking ``treaties`` to attack ``target``."""
    seen = _perceived_power(world, civ, target)
    ratio = power(civ) / max(1.0, seen if seen is not None else power(target))
    u = (grievance(world, civ.name, target.name) / 40.0
         + 0.5 * (ratio - 1.5)
         - trust(world, civ.name, target.name) / 100.0
         - 0.4 * len(treaties) - 0.3)
    if civ.leader.trait in AGGRESSIVE_TRAITS:
        u += 0.25
    if any(t.kind == "alliance" for t in treaties):
        u -= 0.5
    return u + _noise(world, "breach", civ.name, target.name)


def revanche_bonus(world, civ: "Civilization", target: "Civilization") -> float:
    """WAR target score bonus from grievances that wars settle (war, land, treaties)."""
    if not diplomacy_enabled(world):
        return 0.0
    return min(1.0, grievance(world, civ.name, target.name, (WAR, OCCUPATION, TREATY)) / 50.0)


def on_war_declared(world, attacker: "Civilization", defender: "Civilization", *,
                    broken: Iterable[Treaty] = (), acc=None,
                    enemies_before: Iterable[str] = ()) -> list[Event]:
    """A new war: breaches, the aggression grievance and calls to arms.

    Returns the events (already observed); the caller appends them to the
    timeline. Call only when the pair was not at war before this action;
    ``enemies_before`` are the attacker's enemies before it, so civs that
    joined the defence since (federations, allies, overlords) are known: a
    joiner bound to the attacker by a protecting treaty breaks it.
    """
    if not diplomacy_enabled(world):
        return []
    events: list[Event] = []
    war_id = prov.recall(world, prov.war_key(attacker.name, defender.name))
    a_idx = _idx(world, attacker.name)
    for treaty in broken:
        if treaty.status == "active":
            events.append(break_treaty(world, treaty, a_idx, reason="it declares war", acc=acc,
                                       causes=(war_id,)))
    # Any other protecting treaty still active is broken by the declaration too.
    for treaty in protecting_treaties(world, attacker, defender):
        events.append(break_treaty(world, treaty, a_idx, reason="it declares war", acc=acc,
                                   causes=(war_id,)))
    add_grievance(world, defender.name, attacker.name, WAR, GRIEVANCE_WAR_DECLARED)
    adjust_trust(world, defender.name, attacker.name, TRUST_AGGRESSION)
    events.extend(_calls_to_arms(world, attacker, defender, war_id, acc))
    before = set(enemies_before) | {defender.name}
    joiners = sorted({b for a, b in world.active_wars if a == attacker.name and b not in before},
                     key=lambda n: _idx(world, n) if _idx(world, n) is not None else 1 << 30)
    for name in joiners:
        joiner = world.civ_map.get(name)
        if joiner is None:
            continue
        for treaty in protecting_treaties(world, joiner, attacker):
            events.append(break_treaty(
                world, treaty, _idx(world, name), acc=acc, causes=(war_id,),
                reason=f"it joins the war on {attacker.name} in defence of {defender.name}"))
    return events


def _join_war(world, joiner: "Civilization", attacker: "Civilization", acc=None) -> None:
    from chronicler.politics import war_key
    world.active_wars.append((attacker.name, joiner.name))
    world.war_start_turns.setdefault(war_key(attacker.name, joiner.name), world.turn)
    from chronicler.contact_ledger import apply_war_trade_shock, ledger_enabled
    if ledger_enabled(world):
        apply_war_trade_shock(world, attacker.name, joiner.name, acc=acc)


def _join_utility(world, ally: "Civilization", defender: "Civilization",
                  attacker: "Civilization") -> float:
    ratio = power(attacker) / max(1.0, power(ally) + power(defender))
    u = (0.45 + trust(world, ally.name, defender.name) / 100.0
         + goodwill(world, ally.name, defender.name) / 40.0
         + grievance(world, ally.name, attacker.name) / 40.0
         - 0.6 * max(0.0, ratio - 1.0)
         - (0.3 if _wars_of(world, ally.name) else 0.0)
         - (0.25 if ally.stability < 30 else 0.0))
    return u + _noise(world, "join", ally.name, defender.name, attacker.name)


def _calls_to_arms(world, attacker, defender, war_id, acc) -> list[Event]:
    events: list[Event] = []
    a_idx, d_idx = _idx(world, attacker.name), _idx(world, defender.name)
    subject_of = _subject_of(world)
    for treaty in sorted(treaties_between_any(world, d_idx, ("alliance",)), key=lambda t: t.treaty_id):
        ally_idx = _other_party(treaty, d_idx)
        ally = world.civilizations[ally_idx]
        if not ally.regions or ally_idx == a_idx or _at_war(world, ally.name, attacker.name):
            continue
        if treaties_between(world, ally_idx, a_idx, ("alliance",)) or ally.name in subject_of:
            continue  # bound to both sides, or not free to make war: stays out
        if _join_utility(world, ally, defender, attacker) > 0:
            _join_war(world, ally, attacker, acc)
            adjust_trust(world, defender.name, ally.name, TRUST_DEFENDED)
            add_goodwill(world, defender.name, ally.name, GOODWILL_DEFENDED)
            _bump(world.diplomacy, "joined:alliance")
            events.append(_emit_now(world, Event(
                turn=world.turn, event_type="call_to_arms",
                actors=[ally.name, defender.name, attacker.name],
                description=f"{ally.name} honours {treaty.name} and joins {defender.name} "
                            f"against {attacker.name}.",
                importance=6,
            ), (war_id, treaty.event_id)))
        else:
            adjust_trust(world, defender.name, ally.name, TRUST_REFUSED_CALL)
            events.append(break_treaty(world, treaty, ally_idx, acc=acc, causes=(war_id,),
                                       reason=f"it abandons its ally to {attacker.name}"))
    vr = subject_of.get(defender.name)
    overlord = world.civ_map.get(vr.overlord) if vr is not None else None
    if (overlord is not None and overlord.regions and overlord.name != attacker.name
            and overlord.name not in subject_of and not _at_war(world, overlord.name, attacker.name)):
        stage_bonus = {"client": 0.0, "vassal": 0.15, "union": 0.3}.get(vr.stage or "vassal", 0.15)
        ratio = power(attacker) / max(1.0, power(overlord))
        u = (0.4 + stage_bonus + min(0.3, defender.economy / 200.0)
             - 0.6 * max(0.0, ratio - 1.0)
             - (0.3 if _wars_of(world, overlord.name) else 0.0)
             + _noise(world, "protect", overlord.name, defender.name))
        if u > 0:
            _join_war(world, overlord, attacker, acc)
            adjust_trust(world, defender.name, overlord.name, TRUST_DEFENDED)
            _bump(world.diplomacy, "joined:overlord")
            events.append(_emit_now(world, Event(
                turn=world.turn, event_type="call_to_arms",
                actors=[overlord.name, defender.name, attacker.name],
                description=f"{overlord.name} rides to the defence of its {vr.stage or 'vassal'} "
                            f"{defender.name} against {attacker.name}.",
                importance=6,
            ), (war_id, prov.recall(world, prov.key("subject", defender.name)))))
        else:
            adjust_trust(world, defender.name, overlord.name, TRUST_REFUSED_CALL)
            add_grievance(world, defender.name, overlord.name, TREATY, GRIEVANCE_ABANDONED)
            _bump(world.diplomacy, "abandoned:subject")
    return events


def treaties_between_any(world, idx: int, kinds: Iterable[str] | None = None) -> list[Treaty]:
    """Active treaties of civ ``idx`` with anyone."""
    if not diplomacy_enabled(world) or idx is None:
        return []
    wanted = None if kinds is None else set(kinds)
    return [t for t in world.diplomacy.treaties
            if t.status == "active" and idx in t.parties and (wanted is None or t.kind in wanted)]


def note_instant_battle(world, attacker: "Civilization", defender: "Civilization", outcome: str) -> None:
    """Instant-war path (``--no-campaigns``): the battle's grievance."""
    if not diplomacy_enabled(world):
        return
    if outcome == "attacker_wins":
        add_grievance(world, defender.name, attacker.name, WAR, GRIEVANCE_INSTANT_DEFEAT)
        add_grievance(world, attacker.name, defender.name, WAR, GRIEVANCE_BATTLE_FOUGHT)
    elif outcome == "defender_wins":
        add_grievance(world, attacker.name, defender.name, WAR, GRIEVANCE_INSTANT_DEFEAT)
        add_grievance(world, defender.name, attacker.name, WAR, GRIEVANCE_BATTLE_FOUGHT)
    else:
        add_grievance(world, attacker.name, defender.name, WAR, GRIEVANCE_BATTLE_LOST)
        add_grievance(world, defender.name, attacker.name, WAR, GRIEVANCE_BATTLE_LOST)


#: Ladder lever for polity turnover (off by default): a conquest,
#: capitulation or occupation consolidation that would extinguish a state
#: makes it a vassal instead. On 20 hybrid seeds x 500 turns it ends every
#: conquest extinction but doubles wars (spared vassals revolt and seek
#: revanche) and keeps all four founders alive in half the worlds (the
#: regression oracle's civ_survival limit is a fifth); off, conquered states
#: fall as on base and the ladder replaces twilight absorption only.
#: See docs/integration/diplomacy.md.
SPARE_LAST_REGION = False


def spares_last_region(world, winner: "Civilization", loser: "Civilization") -> bool:
    """Ladder: may a conquest that would extinguish ``loser`` make it a vassal instead?"""
    if not diplomacy_enabled(world) or not SPARE_LAST_REGION:
        return False
    subject_of = _subject_of(world)
    overlords = {vr.overlord for vr in world.vassal_relations}
    return (loser.name not in subject_of and winner.name not in subject_of
            and loser.name not in overlords)


# ---------------------------------------------------------------------------
# Embargo and trade hooks
# ---------------------------------------------------------------------------

def embargo_guard(world, civ: "Civilization", target: "Civilization") -> tuple[bool, list[Treaty]]:
    """May ``civ`` embargo ``target``, and which treaties would it break?"""
    if not diplomacy_enabled(world):
        return True, []
    a, b = _idx(world, civ.name), _idx(world, target.name)
    binding = treaties_between(world, a, b, ("trade_pact", "alliance"))
    if not binding:
        return True, []
    u = (grievance(world, civ.name, target.name) / 30.0
         - trust(world, civ.name, target.name) / 100.0
         - 0.5 * len(binding) - 0.2 + _noise(world, "embargo", civ.name, target.name))
    return (True, binding) if u > 0 else (False, [])


def on_embargo(world, imposer: "Civilization", target: "Civilization", *,
               broken: Iterable[Treaty] = (), acc=None) -> list[Event]:
    """An embargo was imposed: breaches and the target's grievance."""
    if not diplomacy_enabled(world):
        return []
    events = [break_treaty(world, t, _idx(world, imposer.name), acc=acc,
                           reason="it imposes an embargo") for t in broken if t.status == "active"]
    add_grievance(world, target.name, imposer.name, EMBARGO, GRIEVANCE_EMBARGO_IMPOSED)
    return events


# ---------------------------------------------------------------------------
# Action-weight bucket and eligibility
# ---------------------------------------------------------------------------

#: The diplomacy contributor bucket is clamped to [1/ceiling, ceiling] per
#: action before the existing global weight cap applies (like governance).
DIPLOMACY_WEIGHT_CEILING = 1.5


def _threat(world, civ: "Civilization", borders: set) -> tuple[float, str | None]:
    """Strongest bordering civ that is hostile toward, or at war with, ``civ``."""
    best, who = 0.0, None
    mine = power(civ)
    for _, other in _living(world):
        if other.name == civ.name or (civ.name, other.name) not in borders:
            continue
        rel = _rel(world, other.name, civ.name)
        if not (_at_war(world, civ.name, other.name)
                or (rel is not None and rel.disposition in _HOSTILE)):
            continue
        ratio = power(other) / mine
        if ratio > best:
            best, who = ratio, other.name
    return best, who


def weight_modifiers(civ: "Civilization", world) -> dict[ActionType, float]:
    """Diplomacy contributor bucket for action weights.

    Grievance against a hostile neighbour raises WAR (revanche); hostile
    neighbours that are all bound by protecting treaties lower it. Trade
    pacts raise TRADE; a threatened civ seeks diplomacy; subjects defer
    foreign policy to their overlord.
    """
    if not diplomacy_enabled(world) or not civ.regions:
        return {}
    mods: dict[ActionType, float] = {}
    ci = _idx(world, civ.name)
    hostile = [other for _, other in _living(world)
               if other.name != civ.name
               and (rel := _rel(world, civ.name, other.name)) is not None
               and rel.disposition in _HOSTILE]
    if hostile:
        g = max(grievance(world, civ.name, o.name, (WAR, OCCUPATION, TREATY)) for o in hostile)
        war = 1.0 + 0.4 * min(1.0, g / 60.0)
        if all(protecting_treaties(world, civ, o) for o in hostile):
            war *= 0.7
        if war != 1.0:
            mods[ActionType.WAR] = war
    if treaties_between_any(world, ci, ("trade_pact",)):
        mods[ActionType.TRADE] = 1.2
    if civ.name in _subject_of(world):
        mods[ActionType.DIPLOMACY] = 0.8
    else:
        from chronicler.intelligence import border_pairs
        ratio, _ = _threat(world, civ, border_pairs(world))
        if ratio >= 1.3:
            mods[ActionType.DIPLOMACY] = 1.25
    floor = 1.0 / DIPLOMACY_WEIGHT_CEILING
    return {a: min(DIPLOMACY_WEIGHT_CEILING, max(floor, m)) for a, m in mods.items() if m != 1.0}


#: Actions a member of a personal union leaves to the overlord's court.
UNION_FORBIDDEN = frozenset({ActionType.WAR, ActionType.DIPLOMACY, ActionType.EMBARGO,
                             ActionType.FUND_INSTABILITY})


def restrict_eligible(world, civ: "Civilization", eligible: list[ActionType]) -> list[ActionType]:
    if not diplomacy_enabled(world):
        return eligible
    vr = _subject_of(world).get(civ.name)
    if vr is None or vr.stage != "union":
        return eligible
    return [a for a in eligible if a not in UNION_FORBIDDEN]


# ---------------------------------------------------------------------------
# DIPLOMACY action: offers and acceptance
# ---------------------------------------------------------------------------

class Offer(NamedTuple):
    kind: str          # non_aggression, alliance, trade_pact, client
    target: int        # civ index
    utility: float     # proposer's utility
    causes: tuple      # provenance of the motive


_OFFER_ORDER = {"non_aggression": 0, "alliance": 1, "trade_pact": 2, "client": 3}


def _on_cooldown(state: DiplomacyState, a: int, b: int, kind: str, turn: int) -> bool:
    return any(r[0] == a and r[1] == b and r[2] == kind and turn < r[3] for r in state.cooldowns)


def _set_cooldown(state: DiplomacyState, a: int, b: int, kind: str, until: int) -> None:
    rows = [r for r in state.cooldowns if not (r[0] == a and r[1] == b and r[2] == kind)]
    rows.append((a, b, kind, until))
    state.cooldowns = sorted(rows)


def _trade_flow(world, a: "Civilization", b: "Civilization", routes) -> tuple[float, float, float]:
    """(flow, dependence of a on b, dependence of b on a)."""
    from chronicler import contact_ledger as cl
    if cl.ledger_enabled(world):
        return (cl.civ_flow(world, a.name, b.name),
                cl.dependence(world, a.name, b.name), cl.dependence(world, b.name, a.name))
    pair = (a.name, b.name) if a.name < b.name else (b.name, a.name)
    return (2.0, 0.15, 0.15) if pair in routes else (0.0, 0.0, 0.0)


def _common_threat(world, a: "Civilization", b: "Civilization", borders) -> tuple[float, str | None]:
    best, who = 0.0, None
    base = min(power(a), power(b))
    for _, x in _living(world):
        if x.name in (a.name, b.name):
            continue
        if not ((a.name, x.name) in borders or (b.name, x.name) in borders):
            continue
        hostile = any(_at_war(world, x.name, y)
                      or ((rel := _rel(world, x.name, y)) is not None and rel.disposition in _HOSTILE)
                      for y in (a.name, b.name))
        if not hostile:
            continue
        ratio = power(x) / base
        if ratio >= 0.6 and ratio > best:
            best, who = ratio, x.name
    return min(2.0, best), who


def _threat_causes(world, civ_name: str, threat_name: str | None) -> tuple:
    if threat_name is None:
        return ()
    k = prov.pair(civ_name, threat_name)
    return (prov.recall(world, prov.war_key(civ_name, threat_name)),
            prov.recall(world, "border:" + k, within=20),
            prov.recall(world, "breach:" + k, within=40))


def _offers(world, civ: "Civilization") -> list[Offer]:
    from chronicler.intelligence import border_pairs
    from chronicler.resources import _compute_active_trade_routes
    from chronicler import contact_ledger as cl
    state = world.diplomacy
    ci = _idx(world, civ.name)
    borders = border_pairs(world)
    routes = set() if cl.ledger_enabled(world) else set(_compute_active_trade_routes(world))
    subject_of = _subject_of(world)
    overlords = {vr.overlord for vr in world.vassal_relations}
    threat_ratio, threat_name = _threat(world, civ, borders)
    at_war_elsewhere = bool(_wars_of(world, civ.name))
    aggressive = civ.leader.trait in AGGRESSIVE_TRAITS
    out: list[Offer] = []
    for ti, other in _living(world):
        if ti == ci or _at_war(world, civ.name, other.name):
            continue
        if _rel(world, civ.name, other.name) is None or _rel(world, other.name, civ.name) is None:
            continue
        seen = _perceived_power(world, civ, other)
        if seen is None:
            continue  # an unknown civ is not approached
        kinds = {t.kind for t in treaties_between(world, ci, ti)}
        bordering = (civ.name, other.name) in borders
        g = grievance(world, civ.name, other.name)
        tr = trust(world, civ.name, other.name)
        gw = goodwill(world, civ.name, other.name)
        turn = world.turn
        # Non-aggression: a quiet border with a strong neighbour.
        if (bordering and not kinds & set(PROTECTING_KINDS)
                and not _on_cooldown(state, ci, ti, "non_aggression", turn)):
            ratio = seen / power(civ)
            u = (0.6 * max(0.0, ratio - 0.8)
                 + (0.4 * max(0.0, threat_ratio - 1.2) if threat_name not in (None, other.name) else 0.0)
                 + (0.3 if at_war_elsewhere else 0.0)
                 - g / 50.0 + tr / 200.0 - 0.2 - (0.2 if aggressive else 0.0))
            out.append(Offer("non_aggression", ti, u, _threat_causes(world, civ.name, other.name)))
        # Defensive alliance: friends with a common enemy.
        if ("alliance" not in kinds and _disp(world, civ.name, other.name) >= 3
                and _disp(world, other.name, civ.name) >= 3
                and civ.name not in subject_of and other.name not in subject_of
                and not _on_cooldown(state, ci, ti, "alliance", turn)):
            common, enemy = _common_threat(world, civ, other, borders)
            if enemy is not None:
                u = 0.5 * common + tr / 100.0 + gw / 50.0 - 0.35
                out.append(Offer("alliance", ti, u, _threat_causes(world, civ.name, enemy)
                                 + _threat_causes(world, other.name, enemy)))
        # Trade pact: partners whose trade matters to them.
        if ("trade_pact" not in kinds and _disp(world, civ.name, other.name) >= 1
                and _disp(world, other.name, civ.name) >= 1
                and not _on_cooldown(state, ci, ti, "trade_pact", turn)):
            flow, dep, _ = _trade_flow(world, civ, other, routes)
            if flow >= GOODWILL_TRADE_MIN_FLOW:
                u = 1.2 * dep + 0.04 * min(flow, 10.0) - 0.1 + gw / 100.0
                out.append(Offer("trade_pact", ti, u, ()))
        # Clientage: a small threatened state seeks a protector.
        if (bordering and civ.name not in subject_of and civ.name not in overlords
                and other.name not in subject_of and threat_name not in (None, other.name)
                and threat_ratio >= 1.5 and len(civ.regions) <= 2
                and other.stability > PROMOTE_MIN_STABILITY
                and _disp(world, other.name, civ.name) >= 2
                and not _on_cooldown(state, ci, ti, "client", turn)
                and overlord_weakness(world, other, civ)[0] is None):
            u = (0.5 * (threat_ratio - 1.5) + 0.15 - g / 30.0 + tr / 100.0
                 - 0.2 * (len(civ.regions) - 1))
            out.append(Offer("client", ti, u, _threat_causes(world, civ.name, threat_name)))
    return [o for o in out if o.utility > OFFER_MIN_UTILITY]


def acceptance_utility(world, offer: Offer, proposer: "Civilization", *, noise: bool = True) -> float:
    """The target's utility of accepting ``offer`` (accepted when > 0).

    ``noise=False`` gives the deterministic part (the proposer's estimate).
    """
    from chronicler.intelligence import border_pairs
    from chronicler.resources import _compute_active_trade_routes
    from chronicler import contact_ledger as cl
    target = world.civilizations[offer.target]
    g = grievance(world, target.name, proposer.name)
    tr = trust(world, target.name, proposer.name)
    gw = goodwill(world, target.name, proposer.name)
    noise = _noise(world, "accept", offer.kind, proposer.name, target.name) if noise else 0.0
    aggressive = target.leader.trait in AGGRESSIVE_TRAITS
    at_war = bool(_wars_of(world, target.name))
    if offer.kind == "non_aggression":
        seen = _perceived_power(world, target, proposer) or power(proposer)
        ratio = seen / power(target)
        return (0.1 + 0.5 * max(0.0, ratio - 0.7) + (0.3 if at_war else 0.0)
                + tr / 100.0 - g / 40.0 + gw / 50.0
                - 0.3 * max(0.0, 1.0 / max(ratio, 0.01) - 1.5)
                - (0.2 if aggressive else 0.0) + noise)
    if offer.kind == "alliance":
        common, _ = _common_threat(world, proposer, target, border_pairs(world))
        return (0.45 * common + tr / 100.0 + gw / 50.0 - g / 30.0 - 0.4
                - (0.25 if _wars_of(world, proposer.name) else 0.0) + noise)
    if offer.kind == "trade_pact":
        routes = set() if cl.ledger_enabled(world) else set(_compute_active_trade_routes(world))
        flow, _, dep = _trade_flow(world, proposer, target, routes)
        return 1.2 * dep + 0.04 * min(flow, 10.0) + tr / 100.0 - g / 40.0 - 0.1 + noise
    if offer.kind == "client":
        _, threat_name = _threat(world, proposer, border_pairs(world))
        enemy = world.civ_map.get(threat_name) if threat_name else None
        hostile_to_enemy = enemy is not None and (
            _at_war(world, target.name, enemy.name) or _disp(world, target.name, enemy.name) <= 1)
        danger = power(enemy) / power(target) if enemy is not None else 0.0
        return (0.15 + 0.15 * min(1.0, proposer.economy / 30.0)
                + (0.3 if hostile_to_enemy else 0.0) + tr / 100.0 - g / 40.0
                - (0.25 if at_war else 0.0) - 0.3 * max(0.0, danger - 1.0) + noise)
    return -1.0


def resolve_diplomacy_action(civ: "Civilization", world, acc=None) -> Event | None:
    """DIPLOMACY with diplomacy on: make the best treaty offer, if any.

    Returns the action event, or None when there is nothing worth offering
    (the caller then improves relations as before).
    """
    if not diplomacy_enabled(world) or not civ.regions:
        return None
    offers = _offers(world, civ)
    offers.sort(key=lambda o: (-o.utility, o.target, _OFFER_ORDER[o.kind]))
    offer = next((o for o in offers
                  if acceptance_utility(world, o, civ, noise=False) > OFFER_MIN_ESTIMATE), None)
    if offer is None:
        return None
    target = world.civilizations[offer.target]
    ci = _idx(world, civ.name)
    label = TREATY_LABELS[offer.kind]
    if acceptance_utility(world, offer, civ) <= 0:
        _set_cooldown(world.diplomacy, ci, offer.target, offer.kind, world.turn + REJECT_COOLDOWN)
        _bump(world.diplomacy, "rejected:" + offer.kind)
        return Event(turn=world.turn, event_type="diplomacy", actors=[civ.name, target.name],
                     description=f"{civ.name} offered {target.name} a {label}, but was rebuffed.",
                     importance=3)
    if offer.kind == "client":
        event = make_subject(world, target, civ, "client", reason="protection", causes=offer.causes)
        world.events_timeline.append(event)
        return Event(turn=world.turn, event_type="diplomacy", actors=[civ.name, target.name],
                     description=f"{civ.name} placed itself under the protection of {target.name}.",
                     importance=5)
    treaty, event = sign_treaty(world, offer.kind, ci, offer.target, causes=offer.causes)
    world.events_timeline.append(event)
    return Event(turn=world.turn, event_type="diplomacy", actors=[civ.name, target.name],
                 description=f"{civ.name} concluded {treaty.name} ({label}) with {target.name}.",
                 importance=4)


# ---------------------------------------------------------------------------
# Polity ladder
# ---------------------------------------------------------------------------

def _tribute_rate(world, stage: str) -> float:
    if stage == "client":
        return CLIENT_TRIBUTE_RATE
    if stage == "union":
        return UNION_TRIBUTE_RATE
    from chronicler.tuning import K_VASSAL_TRIBUTE_RATE, get_override
    return get_override(world, K_VASSAL_TRIBUTE_RATE, 0.15)


def make_subject(world, overlord: "Civilization", vassal: "Civilization", stage: str, *,
                 reason: str, causes: Iterable[str | None] = ()) -> Event:
    """Enter the ladder: a new VassalRelation at ``stage``. Returns the (observed) event."""
    world.vassal_relations.append(VassalRelation(
        overlord=overlord.name, vassal=vassal.name, tribute_rate=_tribute_rate(world, stage),
        stage=stage, stage_turn=world.turn, integration=0.0,
    ))
    if reason == "twilight":
        description = (f"The Submission of {vassal.name}: the declining realm becomes a client "
                       f"of {overlord.name}")
        # What made the realm unviable or declining: its twilight or collapse,
        # and the famine and exhausted soil open in its land.
        causes = (*causes, prov.recall(world, prov.key("twilight", vassal.name)),
                  prov.recall(world, prov.key("collapse", vassal.name), within=50),
                  *(prov.open_episode(world, "famine", rn) for rn in vassal.regions),
                  *(prov.open_episode(world, "soil_exhaustion", rn) for rn in vassal.regions))
    else:
        description = f"{vassal.name} places itself under the protection of {overlord.name} as a client"
    event = _emit_now(world, Event(
        turn=world.turn, event_type="vassalization", actors=[overlord.name, vassal.name],
        description=description, importance=6,
    ), causes)
    prov.remember(world, prov.key("subject", vassal.name), event)
    _bump(world.diplomacy, "entered:" + stage)
    return event


def on_vassalized(world, vr: VassalRelation, old_overlord_view, old_vassal_view, event: Event) -> None:
    """``politics.resolve_vassalization`` under the ladder: the vassal stage, memory kept."""
    if not diplomacy_enabled(world):
        return
    vr.stage, vr.stage_turn, vr.integration = "vassal", world.turn, 0.0
    vr.tribute_rate = _tribute_rate(world, "vassal")
    for holder, other, old in ((vr.overlord, vr.vassal, old_overlord_view),
                               (vr.vassal, vr.overlord, old_vassal_view)):
        rel = _rel(world, holder, other)
        if rel is not None and old is not None and old.memory is not None:
            rel.memory = old.memory
    add_grievance(world, vr.vassal, vr.overlord, OCCUPATION, GRIEVANCE_SUBJUGATION)
    prov.remember(world, prov.key("subject", vr.vassal), event)
    _bump(world.diplomacy, "entered:vassal")


def overlord_weakness(world, overlord: "Civilization", vassal: "Civilization") -> tuple[str | None, list]:
    """Why ``overlord`` cannot hold ``vassal`` now (None if it can), and the causes.

    Unrest (stability below WEAK_STABILITY), a subject that has outgrown it,
    a lost war in the last WEAK_DEFEAT_TURNS turns, or a governance PSI crisis.
    """
    reason = None
    causes: list = []
    gov = getattr(overlord, "governance", None)
    if gov is not None and getattr(gov, "psi_crisis", False):
        reason = "crisis"
        causes.append(prov.recall(world, prov.key("psi", overlord.name)))
    for rec in reversed(world.war_state.treaties):
        if world.turn - rec.turn > WEAK_DEFEAT_TURNS:
            break
        if overlord.name in rec.parties and rec.winner not in (None, overlord.name):
            reason = reason or "defeat"
            causes.append(prov.recall(world, "peace:" + prov.pair(*rec.parties[:2])))
    if overlord.stability < WEAK_STABILITY:
        reason = reason or "unrest"
        causes += [prov.recall(world, prov.key("revolt", overlord.name), within=20),
                   *(prov.recall(world, prov.war_key(overlord.name, e)) for e in _wars_of(world, overlord.name))]
    if power(overlord) < WEAK_POWER_RATIO * power(vassal):
        reason = reason or "outgrown"
    return reason, causes


def _integrate(world, vr: VassalRelation, overlord, vassal, weak: bool) -> None:
    gain = 0.5
    if overlord.civ_majority_faith != 0xFF and overlord.civ_majority_faith == vassal.civ_majority_faith:
        gain += 0.5
    if set(overlord.values) & set(vassal.values):
        gain += 0.25
    if _adjacent(world, vassal, overlord):
        gain += 0.25
    gain -= min(1.0, grievance(world, vassal.name, overlord.name) / 40.0)
    if weak:
        gain -= 0.5
    rate = INTEGRATION_STAGE_RATE.get(vr.stage or "vassal", 1.0)
    vr.integration = _q(max(0.0, min(100.0, (vr.integration or 0.0) + gain * rate)))


def _set_stage(world, vr: VassalRelation, overlord, vassal, stage: str) -> None:
    vr.stage = stage
    vr.stage_turn = world.turn
    vr.crown = overlord.leader.name if stage == "union" else None
    vr.tribute_rate = _tribute_rate(world, stage)


def _ladder_event(world, event_type: str, actors: list[str], description: str, vassal: str,
                  causes: Iterable[str | None] = (), importance: int = 6) -> Event:
    event = _emit_now(world, Event(turn=world.turn, event_type=event_type, actors=actors,
                                   description=description, importance=importance),
                      (prov.recall(world, prov.key("subject", vassal)), *causes))
    return event


def fast_track(world, vassal: "Civilization") -> bool:
    """A subject the old paths would have absorbed outright: structurally
    unviable (the twilight step), or reduced to a single region (terminal
    decline, a conquest or capitulation spared as a vassal, a city-state
    under protection)."""
    from chronicler.politics import TWILIGHT_UNVIABLE_STREAK
    return vassal.unviable_turns >= TWILIGHT_UNVIABLE_STREAK or len(vassal.regions) == 1


def _maybe_advance(world, vr: VassalRelation, overlord, vassal, acc=None) -> Event | None:
    state = world.diplomacy
    oi, vi = _idx(world, overlord.name), _idx(world, vassal.name)
    if _on_cooldown(state, oi, vi, "ladder", world.turn):
        return None
    turns = world.turn - (vr.stage_turn if vr.stage_turn is not None else world.turn)
    from chronicler.politics import TWILIGHT_ABSORPTION_SPACING
    unviable = fast_track(world, vassal)
    need = (LADDER_FAST_TURNS if unviable else LADDER_MIN_TURNS)[vr.stage]
    ratio = power(overlord) / power(vassal)
    if turns < need or ratio < (FAST_POWER_RATIO if unviable else PROMOTE_POWER_RATIO):
        return None
    g = grievance(world, vassal.name, overlord.name)
    tr = trust(world, vassal.name, overlord.name)
    integration = vr.integration or 0.0
    fast = 0.6 if unviable else 0.0
    noise = _noise(world, "ladder", vassal.name, vr.stage)
    overlord_busy = 0.2 if _wars_of(world, overlord.name) else 0.0
    if vr.stage == "client":
        if overlord.stability < PROMOTE_MIN_STABILITY:
            return None
        u_overlord = 0.3 + 0.1 * min(1.0, vassal.economy / 30.0) - overlord_busy
        u_vassal = (0.5 * (ratio - PROMOTE_POWER_RATIO) / PROMOTE_POWER_RATIO
                    - g / 40.0 + tr / 100.0 + fast - 0.15 + noise)
        if u_overlord > 0 and u_vassal > 0:
            _set_stage(world, vr, overlord, vassal, "vassal")
            _bump(state, "promoted:vassal")
            event = _ladder_event(world, "vassal_promoted", [overlord.name, vassal.name],
                                  f"{overlord.name} binds its client {vassal.name} as a vassal", vassal.name)
            prov.remember(world, prov.key("subject", vassal.name), event)
            return event
    elif vr.stage == "vassal":
        min_integration = FAST_MIN_INTEGRATION if unviable else UNION_MIN_INTEGRATION
        if overlord.stability < PROMOTE_MIN_STABILITY or integration < min_integration:
            return None
        u_overlord = 0.3 - overlord_busy
        u_vassal = integration / 40.0 + tr / 100.0 - g / 40.0 - 0.4 + fast + noise
        if u_overlord > 0 and u_vassal > 0:
            _set_stage(world, vr, overlord, vassal, "union")
            _bump(state, "promoted:union")
            event = _ladder_event(
                world, "vassal_promoted", [overlord.name, vassal.name],
                f"The crown of {vassal.name} passes to {overlord.leader.name} of {overlord.name}: "
                f"a personal union", vassal.name)
            prov.remember(world, prov.key("subject", vassal.name), event)
            return event
    elif vr.stage == "union":
        min_integration = FAST_MIN_INTEGRATION if unviable else ANNEX_MIN_INTEGRATION
        last = world.last_twilight_absorption_turn
        if (overlord.stability < ANNEX_MIN_STABILITY or integration < min_integration
                or len(vassal.regions) > ANNEX_MAX_REGIONS or not _adjacent(world, vassal, overlord)
                or (last is not None and world.turn - last < TWILIGHT_ABSORPTION_SPACING)):
            return None
        u_vassal = integration / 60.0 + fast - g / 40.0 - 0.5 + noise
        if u_vassal > 0:
            return _annex(world, vr, overlord, vassal)
    else:
        return None
    _set_cooldown(state, oi, vi, "ladder", world.turn + LADDER_COOLDOWN)
    return None


def _annex(world, vr: VassalRelation, overlord, vassal) -> Event:
    from chronicler.politics import absorb_civ
    if vr in world.vassal_relations:
        world.vassal_relations.remove(vr)
    subject_id = prov.recall(world, prov.key("subject", vassal.name))
    event = absorb_civ(
        world, vassal, overlord, event_type="union_annexation",
        description=f"The union of {overlord.name} and {vassal.name} becomes one realm: "
                    f"{vassal.name} is annexed",
    )
    event.importance = 7
    _emit_now(world, event, (subject_id,))
    world.last_twilight_absorption_turn = world.turn
    prov.forget(world, prov.key("subject", vassal.name))
    _bump(world.diplomacy, "annexed")
    return event


def _maybe_loosen(world, vr: VassalRelation, overlord, vassal, weakness: str, causes: list,
                  acc=None) -> Event | None:
    stage = vr.stage or "vassal"
    if vr.stage_turn is not None and world.turn - vr.stage_turn < LOOSEN_MIN_TURNS:
        return None
    chance = LOOSEN_CHANCE[stage] + grievance(world, vassal.name, overlord.name) / 400.0
    if _rng(world, "loosen", vassal.name, overlord.name).random() >= chance:
        return None
    state = world.diplomacy
    _bump(state, "loosened:" + stage)
    _bump(state, "weakness:" + weakness)
    _add_stat(world, vassal, "stability", LOOSEN_STABILITY, "guard-shock", acc)
    why = WEAKNESS_TEXT[weakness]
    if stage == "client":
        world.vassal_relations.remove(vr)
        event = _ladder_event(world, "vassal_loosened", [vassal.name, overlord.name],
                              f"{vassal.name} renounces its tribute to {overlord.name}, {why}, "
                              f"and stands alone", vassal.name, causes)
        prov.forget(world, prov.key("subject", vassal.name))
        return event
    new_stage = "vassal" if stage == "union" else "client"
    _set_stage(world, vr, overlord, vassal, new_stage)
    if stage == "union":
        text = (f"{vassal.name} takes back its crown from {overlord.name}, {why}, "
                f"and remains a vassal")
    else:
        text = f"{vassal.name} wins autonomy from {overlord.name}, {why}, and becomes a client"
    event = _ladder_event(world, "vassal_loosened", [vassal.name, overlord.name], text, vassal.name, causes)
    prov.remember(world, prov.key("subject", vassal.name), event)
    return event


def _crown_passes(world, vr: VassalRelation, overlord, vassal) -> Event | None:
    """A union whose overlord ruler changed: the crowns may part."""
    old = vr.crown
    if (vr.integration or 0.0) < CROWN_KEEP_INTEGRATION and \
            _rng(world, "crown", vassal.name, overlord.name).random() < CROWN_PART_CHANCE:
        _set_stage(world, vr, overlord, vassal, "vassal")
        _bump(world.diplomacy, "loosened:union")
        _bump(world.diplomacy, "crown_parted")
        event = _ladder_event(
            world, "vassal_loosened", [vassal.name, overlord.name],
            f"With {old} gone, {vassal.name} refuses its crown to {overlord.leader.name}; "
            f"the union with {overlord.name} dissolves into vassalage", vassal.name,
            (prov.recall(world, prov.key("leader_death", overlord.name), within=5),))
        prov.remember(world, prov.key("subject", vassal.name), event)
        return event
    vr.crown = overlord.leader.name
    return None


def _ladder_tick(world, turn_events: list[Event], acc=None) -> list[Event]:
    state = world.diplomacy
    civs = world.civilizations
    index = world.civ_index_map
    events: list[Event] = []
    current = {(index.get(vr.overlord, -1), index.get(vr.vassal, -1)) for vr in world.vassal_relations}
    rebellions = {(ev.actors[0], ev.actors[1]) for ev in turn_events
                  if ev.event_type == "vassal_rebellion" and len(ev.actors) >= 2}
    for o, v, stage in state.subjects:
        if (o, v) in current or not (0 <= o < len(civs) and 0 <= v < len(civs)):
            continue
        overlord, vassal = civs[o], civs[v]
        if not overlord.regions or not vassal.regions:
            continue
        if (vassal.name, overlord.name) in rebellions:
            _bump(state, "revolt:" + stage)
            add_grievance(world, overlord.name, vassal.name, TREATY, GRIEVANCE_REVOLT)
            adjust_trust(world, overlord.name, vassal.name, TRUST_REVOLT)
            prov.forget(world, prov.key("subject", vassal.name))
    order = sorted(world.vassal_relations,
                   key=lambda r: (index.get(r.vassal, 1 << 30), index.get(r.overlord, 1 << 30)))
    for vr in order:
        if vr not in world.vassal_relations:
            continue
        overlord, vassal = world.civ_map.get(vr.overlord), world.civ_map.get(vr.vassal)
        if overlord is None or vassal is None or not overlord.regions or not vassal.regions:
            continue
        if vr.stage is None:  # a relation from before diplomacy was switched on
            _set_stage(world, vr, overlord, vassal, "vassal")
            vr.integration = 0.0
        weakness, causes = overlord_weakness(world, overlord, vassal)
        weak = weakness is not None
        _integrate(world, vr, overlord, vassal, weak)
        event = None
        if vr.stage == "union" and vr.crown not in (None, overlord.leader.name):
            event = _crown_passes(world, vr, overlord, vassal)
        if event is None and weak:
            event = _maybe_loosen(world, vr, overlord, vassal, weakness, causes, acc)
        elif event is None:
            event = _maybe_advance(world, vr, overlord, vassal, acc)
        if event is not None:
            events.append(event)
    return events


# ---------------------------------------------------------------------------
# Per-turn tick (after Phase 10 consequences)
# ---------------------------------------------------------------------------

def _controllers(world) -> list[int]:
    index = world.civ_index_map
    return [index.get(r.controller, -1) if r.controller else -1 for r in world.regions]


def _land_inputs(world, state: DiplomacyState) -> None:
    current = _controllers(world)
    previous = state.controllers
    if len(previous) != len(current):
        return
    civs = world.civilizations
    for ri, (old, new) in enumerate(zip(previous, current)):
        if old == new or old < 0 or new < 0:
            continue
        loser, gainer = civs[old], civs[new]
        amount = GRIEVANCE_LAND_LOST
        if loser.capital_start_of_turn == world.regions[ri].name:
            amount += GRIEVANCE_CAPITAL_LOST
        add_grievance(world, loser.name, gainer.name, OCCUPATION, amount)


def _war_inputs(world) -> None:
    turn = world.turn
    for battle in reversed(world.war_state.battles):
        if battle.turn < turn:
            break
        if battle.turn > turn:
            continue
        sides = ((battle.attacker, battle.defender, battle.attacker_losses, battle.attacker_soldiers),
                 (battle.defender, battle.attacker, battle.defender_losses, battle.defender_soldiers))
        for side, other, losses, soldiers in sides:
            lost = battle.winner is not None and battle.winner != side
            amount = ((GRIEVANCE_BATTLE_LOST if lost else GRIEVANCE_BATTLE_FOUGHT)
                      + GRIEVANCE_BATTLE_CASUALTIES * losses / max(1, soldiers))
            add_grievance(world, side, other, WAR, amount)
    for occ in world.war_state.occupations:
        add_grievance(world, occ.owner, occ.occupier, OCCUPATION, GRIEVANCE_OCCUPIED_TURN)


def _event_inputs(world, turn_events: list[Event]) -> None:
    for ev in turn_events:
        if ev.event_type == "border_incident" and len(ev.actors) >= 2:
            a, b = ev.actors[0], ev.actors[1]
            add_grievance(world, a, b, BORDER, GRIEVANCE_BORDER)
            add_grievance(world, b, a, BORDER, GRIEVANCE_BORDER)


def _persecution_inputs(world) -> None:
    living = _living(world)
    for region in world.regions:
        intensity = region.persecution_intensity
        if intensity <= 0 or region.controller is None:
            continue
        persecutor = world.civ_map.get(region.controller)
        if persecutor is None:
            continue
        for _, civ in living:
            if civ.name == persecutor.name:
                continue
            faith = civ.civ_majority_faith
            if faith != 0xFF and faith != persecutor.civ_majority_faith and region.majority_belief == faith:
                add_grievance(world, civ.name, persecutor.name, FAITH, GRIEVANCE_PERSECUTION * intensity)
            elif region.cultural_identity == civ.name and faith != persecutor.civ_majority_faith:
                add_grievance(world, civ.name, persecutor.name, FAITH,
                              GRIEVANCE_PERSECUTED_PEOPLE * intensity)


def _embargo_inputs(world) -> None:
    """A standing embargo offends while its imposer is still unfriendly; one a
    friendly imposer merely never lifted is not felt as a fresh hostility."""
    neutral = _ORDER.index(Disposition.NEUTRAL)
    for imposer, target in world.embargoes:
        a, b = world.civ_map.get(imposer), world.civ_map.get(target)
        if (a is not None and b is not None and a.regions and b.regions
                and _disp(world, imposer, target) <= neutral):
            add_grievance(world, target, imposer, EMBARGO, GRIEVANCE_EMBARGO_TURN)


def _goodwill_inputs(world) -> None:
    from chronicler import contact_ledger as cl
    living = _living(world)
    ledger = cl.ledger_enabled(world)
    if not ledger:
        from chronicler.resources import _compute_active_trade_routes
        routes = set(_compute_active_trade_routes(world))
    for i, (_, a) in enumerate(living):
        for _, b in living[i + 1:]:
            if ledger:
                flow = cl.civ_flow(world, a.name, b.name)
                amount = (min(GOODWILL_TRADE_MAX, flow / GOODWILL_TRADE_SCALE)
                          if flow >= GOODWILL_TRADE_MIN_FLOW else 0.0)
            else:
                pair = (a.name, b.name) if a.name < b.name else (b.name, a.name)
                amount = GOODWILL_ROUTE if pair in routes else 0.0
            if amount:
                add_goodwill(world, a.name, b.name, amount)
                add_goodwill(world, b.name, a.name, amount)


def _renewal_ok(world, treaty: Treaty) -> bool:
    """Renewal is a fresh offer that both parties accept on their own utility."""
    civs = world.civilizations
    a_idx, b_idx = treaty.parties
    a, b = civs[a_idx], civs[b_idx]
    if treaty.kind == "non_aggression" and not _adjacent(world, a, b):
        return False
    if treaty.kind == "alliance" and not (_disp(world, a.name, b.name) >= 3
                                          and _disp(world, b.name, a.name) >= 3):
        return False
    return all(acceptance_utility(world, Offer(treaty.kind, y_idx, 0.0, ()), x) > 0
               for x, y_idx in ((a, b_idx), (b, a_idx)))


def _war_attacker(world, a: str, b: str) -> str:
    for war in world.war_state.wars:
        if {war.attacker, war.defender} == {a, b}:
            return war.attacker
    for x, y in world.active_wars:
        if {x, y} == {a, b}:
            return x
    return a


def _treaty_upkeep(world, acc=None) -> list[Event]:
    events: list[Event] = []
    civs = world.civilizations
    for treaty in list(world.diplomacy.treaties):
        if treaty.status != "active" or treaty.kind == "tribute":
            continue
        a, b = civs[treaty.parties[0]], civs[treaty.parties[1]]
        if not a.regions or not b.regions:
            _end_treaty(world, treaty, "ended")
            continue
        if treaty.kind in PROTECTING_KINDS and _at_war(world, a.name, b.name):
            breaker = _war_attacker(world, a.name, b.name)
            events.append(break_treaty(world, treaty, _idx(world, breaker), reason="war broke out",
                                       acc=acc, causes=(prov.recall(world, prov.war_key(a.name, b.name)),)))
            continue
        adjust_trust(world, a.name, b.name, TRUST_TREATY_TURN)
        adjust_trust(world, b.name, a.name, TRUST_TREATY_TURN)
        bonus = GOODWILL_ALLIANCE if treaty.kind == "alliance" else (
            GOODWILL_TRADE_PACT if treaty.kind == "trade_pact" else 0.0)
        if bonus:
            add_goodwill(world, a.name, b.name, bonus)
            add_goodwill(world, b.name, a.name, bonus)
        if treaty.expiry_turn is None or world.turn < treaty.expiry_turn:
            continue
        if treaty.kind in RENEWABLE_KINDS and _renewal_ok(world, treaty):
            treaty.expiry_turn = world.turn + TREATY_DURATION[treaty.kind]
            treaty.terms["renewals"] = int(treaty.terms.get("renewals", 0)) + 1
            _bump(world.diplomacy, "renewed:" + treaty.kind)
            events.append(_emit_now(world, Event(
                turn=world.turn, event_type="treaty_renewed", actors=[a.name, b.name],
                description=f"{a.name} and {b.name} renew {treaty.name} for "
                            f"{TREATY_DURATION[treaty.kind]} turns.",
                importance=3,
            ), (treaty.event_id,)))
            continue
        _end_treaty(world, treaty, "expired")
        for x, y in ((a, b), (b, a)):
            adjust_trust(world, x.name, y.name, TRUST_KEPT)
            add_goodwill(world, x.name, y.name, GOODWILL_KEPT)
        label = treaty.name or ("the " + TREATY_LABELS[treaty.kind])
        event = _emit_now(world, Event(
            turn=world.turn, event_type="treaty_expired", actors=[a.name, b.name],
            description=f"{label} between {a.name} and {b.name} runs its course, kept by both.",
            importance=3,
        ), (treaty.event_id,))
        treaty.end_event_id = event.event_id
        events.append(event)
    return events


def _aid_convoys(world, turn_events: list[Event], acc=None) -> list[Event]:
    famine: dict[str, Event] = {}
    region_map = world.region_map
    for ev in turn_events:
        if ev.event_type != "famine" or not ev.region or ev.episode == "tick":
            continue
        region = region_map.get(ev.region)
        if region is not None and region.controller is not None:
            famine.setdefault(region.controller, ev)
    if not famine:
        return []
    state = world.diplomacy
    civs = world.civilizations
    events: list[Event] = []
    for treaty in sorted(world.diplomacy.active("alliance"), key=lambda t: t.treaty_id):
        for di, ri in ((treaty.parties[0], treaty.parties[1]), (treaty.parties[1], treaty.parties[0])):
            donor, recipient = civs[di], civs[ri]
            if recipient.name not in famine or donor.name in famine or not donor.regions:
                continue
            treasury = _projected_treasury(world, donor, acc)
            if treasury < AID_MIN_TREASURY or _on_cooldown(state, di, ri, "aid", world.turn):
                continue
            amount = min(AID_MAX, treasury // 10)
            _add_stat(world, donor, "treasury", -amount, "keep", acc)
            _add_stat(world, recipient, "treasury", amount, "keep", acc)
            add_goodwill(world, recipient.name, donor.name, amount * GOODWILL_AID_PER_TREASURY)
            adjust_trust(world, recipient.name, donor.name, TRUST_AID)
            _set_cooldown(state, di, ri, "aid", world.turn + AID_COOLDOWN)
            _bump(state, "aid")
            events.append(_emit_now(world, Event(
                turn=world.turn, event_type="aid_convoy", actors=[donor.name, recipient.name],
                description=f"{donor.name} sends a relief convoy worth {amount} to its famine-struck "
                            f"ally {recipient.name}.",
                importance=4, region=famine[recipient.name].region,
            ), (famine[recipient.name].event_id, treaty.event_id)))
    return events


def _apply_dispositions(world) -> None:
    """Memory caps and nudges dispositions (directed)."""
    living = {c.name for _, c in _living(world)}
    unions = {(vr.vassal, vr.overlord) for vr in world.vassal_relations if vr.stage == "union"}
    friendly = _ORDER.index(Disposition.FRIENDLY)
    changed = False
    for holder, rels in world.relationships.items():
        if holder not in living:
            continue
        for other, rel in rels.items():
            if other not in living or rel.memory is None:
                continue
            mem = rel.memory
            cur = _ORDER.index(rel.disposition)
            floor = friendly if ((holder, other) in unions or (other, holder) in unions) else 0
            cap = max(floor, _ORDER.index(disposition_ceiling(mem)))
            if cur > cap:
                rel.disposition = _ORDER[cur - 1]
                rel.disposition_drift = 0
                changed = True
                continue
            if cur < floor:
                rel.disposition = _ORDER[cur + 1]
                changed = True
                continue
            e = effective_grievance(mem)
            step = -1 if e >= DRIFT_GRIEVANCE else (1 if e <= -DRIFT_GOODWILL and mem.trust >= 0 else 0)
            if not step:
                continue
            rel.disposition_drift += step
            if rel.disposition_drift >= 10 and cur < cap:
                rel.disposition = _ORDER[cur + 1]
                rel.disposition_drift = 0
                changed = True
            elif rel.disposition_drift <= -10 and cur > floor:
                rel.disposition = _ORDER[cur - 1]
                rel.disposition_drift = 0
                changed = True
    if changed:
        world.invalidate_trade_route_cache()


def tick_diplomacy(world, turn_events: list[Event], acc=None) -> list[Event]:
    """One diplomacy turn, after the Phase 10 consequences.

    ``turn_events`` are this turn's events so far. Returns the new events
    (already observed). Routes stat changes through ``acc`` when given.
    """
    if not diplomacy_enabled(world):
        return []
    state = world.diplomacy
    _decay_memories(world)
    _land_inputs(world, state)
    _war_inputs(world)
    _event_inputs(world, turn_events)
    _persecution_inputs(world)
    _embargo_inputs(world)
    _goodwill_inputs(world)
    events = _treaty_upkeep(world, acc)
    events += _ladder_tick(world, turn_events, acc)
    events += _aid_convoys(world, turn_events, acc)
    _apply_dispositions(world)
    index = world.civ_index_map
    state.subjects = sorted(
        (index.get(vr.overlord, -1), index.get(vr.vassal, -1), vr.stage or "vassal")
        for vr in world.vassal_relations)
    state.controllers = _controllers(world)
    state.cooldowns = [r for r in state.cooldowns if r[3] > world.turn]
    return events


# ---------------------------------------------------------------------------
# Viewer / analytics
# ---------------------------------------------------------------------------

def snapshot_summary(world, top_n: int = 5) -> dict:
    """Per-turn diplomacy summary for ``TurnSnapshot.diplomacy``."""
    state = world.diplomacy
    civs = world.civilizations
    treaties = [
        {"id": t.treaty_id, "kind": t.kind, "name": t.name,
         "parties": [civs[p].name for p in t.parties], "start": t.start_turn, "expiry": t.expiry_turn}
        for t in state.active()
    ]
    subjects = [
        {"overlord": vr.overlord, "vassal": vr.vassal, "stage": vr.stage, "since": vr.stage_turn,
         "integration": vr.integration}
        for vr in world.vassal_relations
    ]
    living = {c.name for _, c in _living(world)}
    rows = []
    for holder, rels in world.relationships.items():
        if holder not in living:
            continue
        for other, rel in rels.items():
            if other in living and rel.memory is not None:
                total = rel.memory.total_grievance()
                if total > 0:
                    rows.append((-total, holder, other, rel.memory))
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    top = [{"holder": h, "target": o, "grievance": round(-t, 2), "trust": m.trust,
            "goodwill": m.goodwill,
            "kinds": {GRIEVANCE_KINDS[i]: v for i, v in enumerate(m.grievance) if v}}
           for t, h, o, m in rows[:top_n]]
    return {"treaties": treaties, "subjects": subjects, "top_grievances": top,
            "counts": dict(sorted(state.counts.items()))}


def extract_diplomacy_metrics(bundles: list[dict]) -> dict:
    """Analytics section from ``history[n].diplomacy`` (empty when no bundle has it)."""
    runs = []
    for bundle in bundles:
        series = [h.get("diplomacy") for h in bundle.get("history", []) if h.get("diplomacy")]
        if not series:
            continue
        active = [len(s["treaties"]) for s in series]
        subjects = [len(s["subjects"]) for s in series]
        stage_turns: dict[str, int] = {}
        for snap in series:
            for sub in snap["subjects"]:
                stage = sub.get("stage") or "vassal"
                stage_turns[stage] = stage_turns.get(stage, 0) + 1
        runs.append({
            "seed": bundle.get("metadata", {}).get("seed"),
            "turns": len(series),
            "counts": dict(series[-1].get("counts", {})),
            "mean_active_treaties": sum(active) / len(active),
            "mean_subjects": sum(subjects) / len(subjects),
            "stage_turns": dict(sorted(stage_turns.items())),
        })
    if not runs:
        return {}
    totals: dict[str, int] = {}
    for run in runs:
        for key, value in run["counts"].items():
            totals[key] = totals.get(key, 0) + value
    n = len(runs)
    return {
        "runs": n,
        "mean_active_treaties": sum(r["mean_active_treaties"] for r in runs) / n,
        "mean_subjects": sum(r["mean_subjects"] for r in runs) / n,
        "counts_per_run": {k: v / n for k, v in sorted(totals.items())},
        "by_seed": runs,
    }
