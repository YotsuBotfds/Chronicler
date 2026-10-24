"""Great-person agendas: generals, merchants, prophets and scientists with
objectives of their own (``--gp-agendas``, default off).

The agenda framework is the M66b ruler-ambition kernel
(:mod:`chronicler.ruler_ambitions`). Each agenda is one
``ruler_ambitions.Ambition`` of a great-person ``AmbitionType`` (appended
after the ruler types), held in a one-objective ``RulerAmbitions`` record
keyed by the person, fed ``EvidenceEvent``s built from the turn's events and
resolved by ``evaluate_ambitions``: state predicates (ownership, the trade
route surface, belief shares), on-time evidence (a coup, a completed temple,
an invention) and, for great persons only, thwarting evidence (a crushed
coup, a broken route, the holder's death or retirement). This module chooses
agendas, performs their deeds and turns outcomes into consequences.

Turn placement
    ``tick_gp_agendas`` runs once per turn after Phase 10 (after politics,
    factions, governance and diplomacy) and before the Phase 10 accumulator
    flush, reading that turn's events. Agenda effects that other phases read
    are persisted state, read on the next turn: the governance action-weight
    bucket (``agenda_weight_factors``), domestic credit
    (``crown_credit_factor``), invention steering (``invention_targets``) and
    the succession-crisis candidate weights (``back_candidates``). The only
    bridge signal touched is a region's conversion signal (prophets
    preaching), which its builder rewrites every Phase 10.

Roles and agendas
    * general: ``lead_campaign`` (take a hostile neighbour's region; WAR
      weight; renown and prestige from victories) and ``seize_throne`` (a
      coup against a weak ruler through the existing succession path,
      citing the grievance or ambition that drives it).
    * merchant: ``open_trade_route`` (trade missions warm a bordering civ),
      ``protect_trade_route`` (keep a route to the deadline), ``found_trading_
      house`` (a trade-good artifact and merchant influence) and, with
      ``--finance``, ``lend_to_crown`` (deeper domestic credit; completes on
      the crown's next domestic loan).
    * prophet: ``spread_faith`` (preaching adds the prophet's pressure to a
      region's conversion signal, within realms that hold the faith and never
      under persecution; agent modes) and ``found_shrine`` (commission a
      temple that becomes a pilgrimage shrine).
    * scientist: ``advance_learning`` (the next era) or, with
      ``--techniques``, ``invent_technique`` (steers the civ's invention).

Bonds
    Alliances (``loyalty`` to the ruler, ``conspiracy`` behind a plotting
    general, ``partnership`` of merchants courting each other's civ) and
    rivalries (``opposition`` to the ruler, ``feud`` between persons whose
    agendas collide) change coup odds, shift faction influence and decide
    who backs whom in a succession crisis.

Every draw is ``stable_hash_int`` on a ``gp_agenda.*`` stream; nothing reads
the action RNG. Provenance: declarations cite the person's rise and motive,
deeds cite the declaration and the event that occasioned them, outcomes cite
the declaration and their evidence, and a coup cites its grievance or
ambition and its conspirators. See ``docs/integration/great-person-agendas.md``.
"""
from __future__ import annotations

import random
from fractions import Fraction
from typing import TYPE_CHECKING, Iterable

from chronicler import provenance as prov
from chronicler import ruler_ambitions as g04
from chronicler.governance_state import GovernanceAmbition
from chronicler.gp_agendas_state import (
    ALLIANCE_KINDS,
    AgendaBond,
    AgendaLogEntry,
    AgendaRecord,
    GPAgendaState,
    gp_agendas_on,
)
from chronicler.models import ActionType, Disposition, Event, FactionType
from chronicler.utils import stable_hash_int

if TYPE_CHECKING:  # pragma: no cover
    from chronicler.models import GreatPerson, WorldState

T = g04.AmbitionType
A = ActionType

# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

DEFAULT_ENABLED_FOR_NEW_WORLDS = False


def gp_agendas_enabled(world) -> bool:
    return gp_agendas_on(world)


def set_gp_agendas_enabled(world: "WorldState", enabled: bool) -> None:
    """Enable (an empty state) or disable (drop the state) great-person agendas."""
    if enabled:
        if not gp_agendas_on(world):
            world.gp_agendas = GPAgendaState()
    else:
        world.gp_agendas = None


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

AGENDA_ROLES = ("general", "merchant", "prophet", "scientist")
MIN_DURATION = g04.GP_AGENDA_MIN_DURATION   # 10
MAX_DURATION = 25
DECLARE_COOLDOWN = 3          # turns between an agenda's end and the next declaration
# Neutral legitimacy calibration: a person's outcome never touches the ruler's
# legitimacy (governance alone owns it); the kernel only settles the objective.
CALIBRATION = g04.AmbitionCalibration(2, 20, 40, 0.0, 0.0, ())

# Action-weight factors per open agenda, folded into the governance bucket
# (pre-clamped there to [1/1.5, 1.5] with institutions and the ruler's
# ambitions; the global 2.5x cap still applies). At most two agendas of one
# kind count per civ.
AGENDA_ACTION_BIAS: dict[T, dict[ActionType, float]] = {
    T.LEAD_CAMPAIGN: {A.WAR: 1.1},
    T.OPEN_TRADE_ROUTE: {A.TRADE: 1.1, A.DIPLOMACY: 1.05},
    T.PROTECT_TRADE_ROUTE: {A.DIPLOMACY: 1.1, A.WAR: 0.95},
    T.FOUND_TRADING_HOUSE: {A.TRADE: 1.1},
    T.SPREAD_FAITH: {A.INVEST_CULTURE: 1.1},
    T.FOUND_SHRINE: {A.BUILD: 1.05},
    T.ADVANCE_LEARNING: {A.DEVELOP: 1.1},
    T.INVENT_TECHNIQUE: {A.DEVELOP: 1.05},
}
MAX_BIASED_PER_KIND = 2

# Trait leanings (kind weight multipliers); base weight 1.0.
_TRAIT_LEANING: dict[T, tuple[tuple[str, ...], float]] = {
    T.LEAD_CAMPAIGN: (("aggressive", "bold", "zealous"), 2.0),
    T.SEIZE_THRONE: (("ambitious", "bold", "aggressive"), 2.0),
    T.PROTECT_TRADE_ROUTE: (("cautious",), 1.5),
    T.FOUND_TRADING_HOUSE: (("shrewd", "calculating", "ambitious"), 1.5),
    T.SPREAD_FAITH: (("zealous",), 2.0),
    T.FOUND_SHRINE: (("cautious", "visionary"), 1.5),
}
_BASE_WEIGHT: dict[T, float] = {T.SEIZE_THRONE: 1.5, T.LEND_TO_CROWN: 1.5}

# Generals
VICTORY_RENOWN = 1            # renown per victory of the civ, for every active general
COMMAND_RENOWN = 2            # ... when the general commanded the winning army
VICTORY_PRESTIGE = 1          # civ prestige per campaign victory (keep)
CAMPAIGN_PRESTIGE = 2         # civ prestige when the campaign takes its region
COUP_RENOWN_WEIGHT = 0.05     # coup success per point of renown (victories, fulfilled vows), at most four
COUP_MIN_REIGN = 5            # a ruler is not plotted against in the first turns of a reign
COUP_MIN_MILITARY_INFLUENCE = 0.2
WEAK_STABILITY = 30
UNEASY_STABILITY = 45
WEAK_LEGITIMACY = 0.35
UNEASY_LEGITIMACY = 0.5
COUP_ATTEMPT_P = 0.2
COUP_ATTEMPT_PER_CONSPIRATOR = 0.05
COUP_BASE_SUCCESS = 0.3
COUP_MILITARY_WEIGHT = 0.5
COUP_BOND_WEIGHT = 0.1        # per conspirator (+) or loyalist (-), at most two each
COUP_LEGITIMACY_WEIGHT = 0.3
COUP_SUCCESS_RANGE = (0.1, 0.85)
COUP_FAILED_STABILITY = 3
MAX_CONSPIRATORS = 2
AGITATION_P = 0.1             # per turn: sour relations with the target's ruler one step
AGITATION_GRIEVANCE = 5.0     # --diplomacy: border grievance the agitation plants in the civ's memory

# Merchants
MISSION_P = 0.15              # per turn: warm the target's disposition one step
PARTNERSHIP_MISSION_FACTOR = 2.0
INTERCEDE_P = 0.3             # protect: restore a partner's disposition that fell
MISSION_GOODWILL = 5.0        # --diplomacy: goodwill a mission leaves in both memories
TRADING_HOUSE_COST = 15
TRADING_HOUSE_P = 0.25
TRADING_HOUSE_MIN_PARTNERS = 2  # a house needs two trading partners (and one free region)
CROWN_CREDIT_PER_LENDER = 0.5  # domestic credit capacity x (1 + 0.5 per lending merchant)
MAX_CROWN_LENDERS = 2
LEND_MIN_STRESS = 0.25

# Prophets
SPREAD_CANDIDATE_SHARE = 0.4
SPREAD_TARGET_SHARE = 0.5
PREACHING_RATE = 0.02         # the prophet's own pressure on the target region's conversion signal per turn
SHRINE_PRESTIGE = 10          # temple prestige a consecrated shrine starts with (pilgrimage magnet)

# Scientists (techniques)
INVENTION_STEER = 2           # candidate score bonus for a targeted technique
INVENTION_RESEARCH = 0.25     # invention chance bonus when the targeted technique is chosen

# Outcomes
FULFIL_RENOWN = 2
FAIL_RENOWN = -1
FULFIL_FACTION_SHIFT = 0.03
OPPOSITION_FACTION_SHIFT = 0.01
BACKING_WEIGHT = 0.05
LOG_LIMIT = 200
# Bond caps: a person holds at most one bond of each person-to-person kind;
# a ruler accepts at most three loyalists.
BOND_CAP = {"conspiracy": 1, "partnership": 1, "feud": 1, "loyalty": 1, "opposition": 1}
LOYALISTS_PER_RULER = 3

ROLE_FACTION: dict[str, FactionType] = {
    "general": FactionType.MILITARY,
    "merchant": FactionType.MERCHANT,
    "prophet": FactionType.CLERGY,
    "scientist": FactionType.CULTURAL,
}

_PHRASES: dict[T, str] = {
    T.LEAD_CAMPAIGN: "lead a campaign to take {t}",
    T.SEIZE_THRONE: "seize the throne",
    T.OPEN_TRADE_ROUTE: "open a trade route to {t}",
    T.PROTECT_TRADE_ROUTE: "keep the trade road to {t} open",
    T.FOUND_TRADING_HOUSE: "found a trading house",
    T.LEND_TO_CROWN: "lend to the crown",
    T.SPREAD_FAITH: "bring the faith to {t}",
    T.FOUND_SHRINE: "raise a pilgrimage shrine in {t}",
    T.ADVANCE_LEARNING: "carry learning into the {t} era",
    T.INVENT_TECHNIQUE: "discover {t}",
}


# ---------------------------------------------------------------------------
# Identity and small helpers
# ---------------------------------------------------------------------------

def gp_key(gp: "GreatPerson") -> str:
    """Record key: name and birth turn, plus the agent id of an agent-backed
    person (promotion can give two agents the same name in one turn)."""
    if gp.agent_id is not None:
        return f"{gp.name}|{gp.born_turn}|a{gp.agent_id}"
    return f"{gp.name}|{gp.born_turn}"


def _ruler_ref(civ_idx: int) -> str:
    return f"ruler:{civ_idx}"


def _rng(label: str, world, *parts) -> random.Random:
    return random.Random(stable_hash_int(f"gp_agenda.{label}", world.seed, world.turn, *parts))


def _eligible(gp: "GreatPerson") -> bool:
    return (gp.role in AGENDA_ROLES and gp.active and gp.alive and not gp.is_hostage)


def _count(state: GPAgendaState, *keys: str) -> None:
    for k in keys:
        state.counts[k] = state.counts.get(k, 0) + 1


def _ambition(a: GovernanceAmbition) -> g04.Ambition:
    predicate = None
    if a.conversion_faith_id is not None:
        predicate = g04.ConversionPredicate(a.target, a.conversion_faith_id,
                                            minimum_share=a.conversion_minimum_share)
    return g04.Ambition(T(a.ambition_type), a.target, a.generated_turn, a.deadline_turn,
                        a.generated_event_cursor, predicate, a.completed, a.failed)


def _is_open(rec: AgendaRecord) -> bool:
    return rec.agenda is not None and not (rec.agenda.completed or rec.agenda.failed)


def _civ_name(world, idx_text: str | None) -> str | None:
    if idx_text is None or not idx_text.isdigit():
        return idx_text
    idx = int(idx_text)
    return world.civilizations[idx].name if idx < len(world.civilizations) else idx_text


def describe(world, kind: T, target: str | None) -> str:
    if kind in (T.OPEN_TRADE_ROUTE, T.PROTECT_TRADE_ROUTE):
        target = _civ_name(world, target)
    elif kind == T.INVENT_TECHNIQUE and target is not None:
        from chronicler.techniques_state import TECHNIQUE_INDEX, TECHNIQUES
        k = TECHNIQUE_INDEX.get(target)
        target = TECHNIQUES[k].label if k is not None else target
    return _PHRASES.get(kind, kind.value).format(t=target)


def _event(world, event_type: str, gp_name: str, civ, description: str, importance: int,
           region: str | None = None, extra_actors: Iterable[str] = ()) -> Event:
    actors = [gp_name, civ.name, *extra_actors]
    return Event(turn=world.turn, event_type=event_type, actors=actors, description=description,
                 importance=importance, civs=[civ.name], region=region)


def _stat(world, acc, civ_idx: int, civ, stat: str, delta: int, category: str) -> None:
    if not delta:
        return
    if acc is not None:
        acc.add(civ_idx, civ, stat, delta, category)
    elif stat in ("treasury", "prestige"):
        setattr(civ, stat, max(0, getattr(civ, stat) + delta))
    else:
        from chronicler.utils import STAT_FLOOR, clamp
        setattr(civ, stat, clamp(getattr(civ, stat) + delta, STAT_FLOOR.get(stat, 0), 100))


def _projected_treasury(civ_idx: int, civ, acc) -> int:
    projected = int(civ.treasury)
    for change in getattr(acc, "_changes", ()) if acc is not None else ():
        if change.civ_id == civ_idx and change.category == "keep" and change.stat == "treasury":
            projected += change.delta
    return projected


def _shift_faction(civ, faction: FactionType | None, amount: float) -> None:
    if faction is None or not amount:
        return
    from chronicler.factions import shift_faction_influence
    shift_faction_influence(civ.factions, faction, amount)


def _deed(gp, text: str, world, region: str | None = None) -> None:
    from chronicler.great_persons import _append_deed
    _append_deed(gp, text, region=region or gp.region, turn=world.turn, civ=gp.civilization)


def _deed_event(world, gp, ev: Event) -> None:
    """Make ``ev`` the person's latest deed (cited by state completions)."""
    prov.remember(world, prov.key("gp_deed", gp_key(gp)), ev)


# ---------------------------------------------------------------------------
# Turn context
# ---------------------------------------------------------------------------

class _Ctx:
    """Read-only lookups for one tick (built once; routes recomputed on demand)."""

    def __init__(self, world, turn_events: list[Event], phase10) -> None:
        self.world = world
        self.events = [e for e in turn_events if e.turn == world.turn]
        self.civ_index = {c.name: i for i, c in enumerate(world.civilizations)}
        self.region_index = {r.name: i for i, r in enumerate(world.regions)}
        self.region_map = {r.name: r for r in world.regions}
        self._partners: dict[str, set[str]] | None = None
        self.region_beliefs: dict[int, dict[int, int]] | None = None
        rows = getattr(phase10, "agents", None) if phase10 is not None else None
        if rows is not None:
            arrays = rows.arrays("region", "belief")
            if arrays is not None:
                from chronicler.columnar import ordered_counts
                self.region_beliefs = {rid: dict(counts) for rid, counts
                                       in ordered_counts(*arrays).items()}
            else:
                beliefs: dict[int, dict[int, int]] = {}
                for rid, bid in zip(rows.ints("region"), rows.ints("belief")):
                    beliefs.setdefault(rid, {})
                    beliefs[rid][bid] = beliefs[rid].get(bid, 0) + 1
                self.region_beliefs = beliefs

    def partners(self) -> dict[str, set[str]]:
        """Current trade-route partners by civ name (fresh, cache-neutral)."""
        if self._partners is None:
            from chronicler.resources import _compute_active_trade_routes
            partners: dict[str, set[str]] = {}
            for a, b in _compute_active_trade_routes(self.world):
                partners.setdefault(a, set()).add(b)
                partners.setdefault(b, set()).add(a)
            self._partners = partners
        return self._partners

    def routes_changed(self) -> None:
        self._partners = None
        self.world.invalidate_trade_route_cache()

    def share(self, region_name: str, faith: int) -> float | None:
        if self.region_beliefs is None:
            return None
        rid = self.region_index.get(region_name)
        dist = self.region_beliefs.get(rid, {}) if rid is not None else {}
        total = sum(dist.values())
        return dist.get(faith, 0) / total if total else None


def _at_war(world, a: str, b: str) -> bool:
    return (a, b) in world.active_wars or (b, a) in world.active_wars


def _hostile(world, a: str, b: str) -> bool:
    rel = world.relationships.get(a, {}).get(b)
    return rel is not None and rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS)


def _won(event: Event, civ_name: str) -> bool:
    """A war event (instant war or campaign battle) the civ won."""
    if event.event_type != "war" or len(event.actors) < 2 or civ_name not in event.actors[:2]:
        return False
    attacker = event.actors[0] == civ_name
    return ("attacker_wins" in event.description) if attacker else ("defender_wins" in event.description)


def _pair_event(event: Event, a: str, b: str) -> bool:
    return len(event.actors) >= 2 and {event.actors[0], event.actors[1]} == {a, b}


# ---------------------------------------------------------------------------
# Ruler weakness, bonds
# ---------------------------------------------------------------------------

def _legitimacy(world, civ) -> tuple[float | None, bool]:
    gov = getattr(civ, "governance", None)
    if getattr(world, "governance", None) is None or gov is None:
        return None, False
    return float(gov.ruler_legitimacy), bool(gov.legitimacy_crisis)


def ruler_weakness(world, civ) -> tuple[bool, bool]:
    """(weak, uneasy): stability and, with governance, legitimacy."""
    legit, crisis = _legitimacy(world, civ)
    weak = civ.stability < WEAK_STABILITY or crisis or (legit is not None and legit < WEAK_LEGITIMACY)
    uneasy = weak or civ.stability < UNEASY_STABILITY or (legit is not None and legit < UNEASY_LEGITIMACY)
    return weak, uneasy


def _bonds_with(state: GPAgendaState, key: str, kinds: Iterable[str]) -> list[AgendaBond]:
    kinds = set(kinds)
    return [b for b in state.bonds if b.kind in kinds and (b.a == key or b.b == key)]


def _has_bond(state: GPAgendaState, kind: str, a: str, b: str) -> bool:
    return any(x.kind == kind and {x.a, x.b} == {a, b} for x in state.bonds)


def _form_bond(world, state: GPAgendaState, kind: str, a: str, b: str, civ_idx: int, civ,
               a_name: str, b_label: str, why: str, causes: Iterable[str | None],
               ruler: str | None = None) -> Event | None:
    if a == b or _has_bond(state, kind, a, b):
        return None
    cap = BOND_CAP.get(kind)
    if kind in ("loyalty", "opposition"):
        if sum(1 for x in state.bonds if x.kind == kind and x.a == a) >= cap:
            return None
        if kind == "loyalty" and sum(1 for x in state.bonds if x.kind == kind and x.b == b
                                     and x.ruler == ruler) >= LOYALISTS_PER_RULER:
            return None
    elif cap is not None and any(sum(1 for x in state.bonds if x.kind == kind and key in (x.a, x.b)) >= cap
                                 for key in (a, b)):
        return None
    alliance = kind in ALLIANCE_KINDS
    etype = "gp_alliance_formed" if alliance else "gp_rivalry_formed"
    ev = _event(world, etype, a_name, civ, why, 4,
                extra_actors=() if b.startswith("ruler:") else (b_label,))
    prov.cite(ev, *causes)
    eid = prov.ensure_id(world, ev)
    state.bonds.append(AgendaBond(kind=kind, a=a, b=b, civ=civ_idx, ruler=ruler,
                                  formed_turn=world.turn, event_id=eid))
    prov.remember(world, prov.key("gp_bond", *sorted((a, b))), ev)
    _count(state, f"bond:{kind}")
    return ev


def _prune_bonds(world, state: GPAgendaState, active: dict[str, tuple[int, "GreatPerson"]]) -> None:
    keep = []
    for bond in state.bonds:
        if bond.a not in active:
            continue
        if bond.b.startswith("ruler:"):
            civ_idx = int(bond.b.split(":", 1)[1])
            civ = world.civilizations[civ_idx] if civ_idx < len(world.civilizations) else None
            if civ is None or not civ.regions or civ.leader.name != bond.ruler or active[bond.a][0] != civ_idx:
                continue
        elif bond.b not in active:
            continue
        keep.append(bond)
    state.bonds = keep


def _people(state: GPAgendaState, active, key: str, kinds: Iterable[str], same_civ: int | None = None) -> list:
    """Active persons bonded to ``key`` by ``kinds`` (optionally in one civ)."""
    out = []
    for bond in _bonds_with(state, key, kinds):
        other = bond.b if bond.a == key else bond.a
        hit = active.get(other)
        if hit is None or (same_civ is not None and hit[0] != same_civ):
            continue
        out.append((other, hit[1], bond))
    return out


def _ruler_bonds(state: GPAgendaState, civ_idx: int, kind: str, ruler: str) -> list[AgendaBond]:
    ref = _ruler_ref(civ_idx)
    return [b for b in state.bonds if b.kind == kind and b.b == ref and b.ruler == ruler]


# ---------------------------------------------------------------------------
# Read API for other phases (persisted state only)
# ---------------------------------------------------------------------------

def _open_agendas_of(world, civ) -> list[tuple["GreatPerson", AgendaRecord]]:
    state = world.gp_agendas
    out = []
    for gp in civ.great_persons:
        if not _eligible(gp):
            continue
        rec = state.records.get(gp_key(gp))
        if rec is not None and _is_open(rec):
            out.append((gp, rec))
    return out


def agenda_weight_factors(world, civ) -> dict[ActionType, float]:
    """Per-action factors of the civ's open agendas (governance bucket input)."""
    if not gp_agendas_on(world):
        return {}
    mods: dict[ActionType, float] = {}
    seen: dict[T, int] = {}
    for _gp, rec in _open_agendas_of(world, civ):
        kind = T(rec.agenda.ambition_type)
        bias = AGENDA_ACTION_BIAS.get(kind)
        if not bias or seen.get(kind, 0) >= MAX_BIASED_PER_KIND:
            continue
        seen[kind] = seen.get(kind, 0) + 1
        for action, m in bias.items():
            mods[action] = mods.get(action, 1.0) * m
    return mods


def crown_credit_factor(world, civ_idx: int) -> float:
    """Domestic credit multiplier from merchants vowing to lend to the crown."""
    if not gp_agendas_on(world) or civ_idx >= len(world.civilizations):
        return 1.0
    lenders = sum(1 for _gp, rec in _open_agendas_of(world, world.civilizations[civ_idx])
                  if rec.agenda.ambition_type == T.LEND_TO_CROWN.value)
    return 1.0 + CROWN_CREDIT_PER_LENDER * min(lenders, MAX_CROWN_LENDERS)


def invention_targets(world, civ) -> frozenset[str]:
    """Technique keys the civ's scientists have vowed to discover."""
    if not gp_agendas_on(world):
        return frozenset()
    return frozenset(rec.agenda.target for _gp, rec in _open_agendas_of(world, civ)
                     if rec.agenda.ambition_type == T.INVENT_TECHNIQUE.value)


# ---------------------------------------------------------------------------
# Agenda pools (what a person could vow now)
# ---------------------------------------------------------------------------

_HOT_HEADED = ("aggressive", "bold", "zealous", "ambitious")


def _campaign_targets(world, ctx: _Ctx, civ, gp) -> list[str]:
    """Neighbouring regions a general would march on: a war enemy's, else a
    hostile or suspicious neighbour's, else (hot-headed generals only) a
    neutral neighbour's. Friends and allies are never targets."""
    owned = set(civ.regions)
    enemies, hostile, neutral = set(), set(), set()
    for name in civ.regions:
        region = ctx.region_map.get(name)
        if region is None:
            continue
        for adj in region.adjacencies:
            other = ctx.region_map.get(adj)
            if other is None or adj in owned or other.controller in (None, civ.name):
                continue
            if _at_war(world, civ.name, other.controller):
                enemies.add(adj)
            elif _hostile(world, civ.name, other.controller):
                hostile.add(adj)
            else:
                rel = world.relationships.get(civ.name, {}).get(other.controller)
                if rel is not None and rel.disposition == Disposition.NEUTRAL:
                    neutral.add(adj)
    if not (enemies or hostile) and gp.trait in _HOT_HEADED:
        return sorted(neutral)
    return sorted(enemies or hostile)


def _coup_motive(world, ctx: _Ctx, state: GPAgendaState, civ_idx: int, civ, gp, rec: AgendaRecord,
                 active) -> list[str] | None:
    """Grievance (or ambition) event ids that drive a general to plot, or None."""
    if len(civ.regions) < 2 or not civ.leader.alive:
        return None
    if civ.succession_crisis_turns_remaining > 0 or world.turn - civ.leader.reign_start < COUP_MIN_REIGN:
        return None
    if civ.factions.influence.get(FactionType.MILITARY, 0.0) < COUP_MIN_MILITARY_INFLUENCE:
        return None
    key = gp_key(gp)
    if any(b.a == key for b in _ruler_bonds(state, civ_idx, "loyalty", civ.leader.name)):
        return None  # a loyalist does not plot
    for other, orec in state.records.items():
        if (other != key and other in active and orec.civ == civ_idx and _is_open(orec)
                and orec.agenda.ambition_type == T.SEIZE_THRONE.value):
            return None  # one plot at a time
    weak, uneasy = ruler_weakness(world, civ)
    opposed = any(b.a == gp_key(gp) for b in _ruler_bonds(state, civ_idx, "opposition", civ.leader.name))
    if not (weak or (uneasy and opposed)):
        return None
    grievances = [prov.recall(world, prov.key("legitimacy", civ.name), within=20),
                  prov.recall(world, prov.key("psi", civ.name)),
                  prov.recall(world, prov.key("revolt", civ.name), within=10),
                  prov.recall(world, prov.key("ambition_failed", civ.name), within=10),
                  prov.recall(world, prov.key("gp_agenda_failed", key), within=20)]
    grievances += [b.event_id for b in _ruler_bonds(state, civ_idx, "opposition", civ.leader.name)
                   if b.a == key]
    motive = [g for g in grievances if g]
    if not motive:
        ambition = prov.recall(world, prov.key("gp_agenda_done", key), within=30)
        motive = [ambition] if ambition else []
    if not motive:
        # No named grievance or ambition: the distress that drained the
        # ruler's stability (famines, wars, revolts, plague) is the grievance.
        motive = [d for d in prov._distress(world, civ.name) if d]
    return motive


def _bordering_civs(ctx: _Ctx, civ) -> list[int]:
    owned = set(civ.regions)
    out = set()
    for name in civ.regions:
        region = ctx.region_map.get(name)
        if region is None:
            continue
        for adj in region.adjacencies:
            other = ctx.region_map.get(adj)
            if other is not None and adj not in owned and other.controller not in (None, civ.name):
                idx = ctx.civ_index.get(other.controller)
                if idx is not None and ctx.world.civilizations[idx].regions:
                    out.add(idx)
    return sorted(out)


def _embargoed(world, a: str, b: str) -> bool:
    return (a, b) in world.embargoes or (b, a) in world.embargoes


def _shrine_targets(world, ctx: _Ctx, civ) -> list[str]:
    from chronicler.infrastructure import valid_build_types
    from chronicler.models import InfrastructureType
    faith = getattr(civ, "civ_majority_faith", 0xFF)
    if not world.belief_registry or faith in (None, 0xFF, -1):
        return []
    out = []
    for name in sorted(civ.regions):
        region = ctx.region_map.get(name)
        if region is None or region.pending_build is not None:
            continue
        if any(i.type == InfrastructureType.TEMPLES and i.active for i in region.infrastructure):
            continue
        if InfrastructureType.TEMPLES in valid_build_types(region, civ=civ, world=world):
            out.append(name)
    return out


def _open_to_preaching(world, ctx: _Ctx, region, faith: int) -> bool:
    """Whether a prophet of ``faith`` preaches in ``region`` this turn.

    Only within the faith's realms: the region's ruler holds the faith (the
    prophet's own people or co-religionists). Preaching there gathers a
    realm's minorities into its own faith; preached into a realm of another
    faith it would tip that realm's majority, and with it whether the realm
    persecutes. And not while the region is under persecution: the agent
    tick applies the intensity (live, or left over by a ruler who no longer
    persecutes) to everyone outside the local majority, converts included.
    """
    if region.persecution_intensity > 0:
        return False
    idx = ctx.civ_index.get(region.controller) if region.controller is not None else None
    if idx is None:
        return False
    return getattr(world.civilizations[idx], "civ_majority_faith", 0xFF) == faith


def _spread_targets(world, ctx: _Ctx, civ) -> list[str]:
    faith = getattr(civ, "civ_majority_faith", 0xFF)
    if ctx.region_beliefs is None or not world.belief_registry or faith in (None, 0xFF, -1):
        return []
    names = set(civ.regions)
    for name in civ.regions:
        region = ctx.region_map.get(name)
        if region is not None:
            names.update(adj for adj in region.adjacencies if adj in ctx.region_map)
    out = []
    for name in sorted(names):
        share = ctx.share(name, faith)
        region = ctx.region_map.get(name)
        if (share is not None and share < SPREAD_CANDIDATE_SHARE and region is not None
                and _open_to_preaching(world, ctx, region, faith)):
            out.append(name)
    return out


def _invention_candidates(world, civ_idx: int, civ) -> list[str]:
    """The inventions ``techniques._invent`` could choose for the civ now, of
    the lowest tier it would try first: unknown techniques of at most the next
    era's tier whose prerequisites the civ knows and that have a site, an
    inhabited region of the civ that suits them and practises their
    prerequisites (this turn's practice, read after Phase 4). A technique
    without a site is never chosen, so a vow for it could only run out."""
    from chronicler import techniques as tq
    from chronicler.tech import _era_index
    from chronicler.techniques_state import TECHNIQUES, TECHNIQUE_INDEX, techniques_on
    if not techniques_on(world):
        return []
    st = world.techniques
    if civ_idx >= len(st.known):
        return []
    known = set(st.known[civ_idx])
    era_idx = _era_index(civ.tech_era)
    cands = [(spec.tier, k, spec.key) for k, spec in enumerate(TECHNIQUES)
             if k not in known and spec.tier <= era_idx + 1
             and all(TECHNIQUE_INDEX[q] in known for q in spec.prereqs)]
    if not cands:
        return []
    ctrl = tq._controllers(world, tq._civ_indices(world))
    members = [r for r, c in enumerate(ctrl) if c == civ_idx]
    suit = tq._suitability(world, ctrl, tq._contacts(world, ctrl))
    practice = {(row[0], row[1]): row[2] for row in st.rows}
    regions = world.regions

    def sited(k: int) -> bool:
        return any(suit[r][k] and regions[r].population > 0
                   and all(practice.get((r, q), 0.0) >= tq.PREREQ_LEVEL for q in tq._PREREQS[k])
                   for r in members)

    cands = [(t, key) for t, k, key in cands if sited(k)]
    if not cands:
        return []
    low = min(t for t, _ in cands)
    return sorted(key for t, key in cands if t == low)


def _next_era(civ) -> str | None:
    from chronicler.models import TechEra
    eras = list(TechEra)
    i = eras.index(civ.tech_era)
    return eras[i + 1].value if i + 1 < len(eras) else None


def _house_site(state: GPAgendaState, civ, gp) -> str | None:
    """Where a merchant would found a trading house: one house per region,
    ever (``GPAgendaState.houses``); the merchant's own region, else the
    capital, else the civ's first free region by name."""
    free = [name for name in civ.regions if name not in state.houses]
    if not free:
        return None
    for preferred in (gp.region, civ.capital_region):
        if preferred in free:
            return preferred
    return sorted(free)[0]


def _taken(state: GPAgendaState, civ_idx: int, active) -> set[tuple[str, str | None]]:
    """(kind, target) vows already held by an active person of the civ."""
    return {(r.agenda.ambition_type, r.agenda.target) for k, r in state.records.items()
            if r.civ == civ_idx and _is_open(r) and k in active}


def _pool(world, ctx: _Ctx, state: GPAgendaState, civ_idx: int, civ, gp, rec: AgendaRecord,
          active) -> dict[T, tuple[list[str | None], list[str]]]:
    """Kind -> (targets, motive ids) the person could vow now. Two persons
    of one civ never hold the same vow (kind and target)."""
    pool = _raw_pool(world, ctx, state, civ_idx, civ, gp, rec, active)
    taken = _taken(state, civ_idx, active)
    out: dict[T, tuple[list[str | None], list[str]]] = {}
    for kind, (targets, motive) in pool.items():
        free = [t for t in targets if (kind.value, t) not in taken]
        if free:
            out[kind] = (free, motive)
    return out


def _raw_pool(world, ctx: _Ctx, state: GPAgendaState, civ_idx: int, civ, gp, rec: AgendaRecord,
              active) -> dict[T, tuple[list[str | None], list[str]]]:
    from chronicler.techniques_state import techniques_on
    pool: dict[T, tuple[list[str | None], list[str]]] = {}
    role = gp.role
    if role == "general":
        targets = _campaign_targets(world, ctx, civ, gp)
        if targets:
            pool[T.LEAD_CAMPAIGN] = (targets, [])
        motive = _coup_motive(world, ctx, state, civ_idx, civ, gp, rec, active)
        if motive is not None:
            pool[T.SEIZE_THRONE] = ([None], motive)
    elif role == "merchant":
        partners = ctx.partners().get(civ.name, set())
        opening = [str(i) for i in _bordering_civs(ctx, civ)
                   if world.civilizations[i].name not in partners
                   and not _at_war(world, civ.name, world.civilizations[i].name)
                   and not _embargoed(world, civ.name, world.civilizations[i].name)]
        if opening:
            pool[T.OPEN_TRADE_ROUTE] = (opening, [])
        protect = sorted(str(ctx.civ_index[p]) for p in partners if p in ctx.civ_index)
        if protect:
            pool[T.PROTECT_TRADE_ROUTE] = (sorted(protect, key=int), [])
        if len(protect) >= TRADING_HOUSE_MIN_PARTNERS and _house_site(state, civ, gp) is not None:
            pool[T.FOUND_TRADING_HOUSE] = ([None], [])
        from chronicler.finance import civ_finance, outstanding_debt
        f = civ_finance(world, civ_idx)
        if f is not None and f.initialized and (f.fiscal_stress >= LEND_MIN_STRESS or f.last_shortfall > 0
                                                or outstanding_debt(world, civ_idx) > 0):
            pool[T.LEND_TO_CROWN] = ([None], [prov.recall(world, prov.key("fiscal", civ.name))])
    elif role == "prophet":
        spread = _spread_targets(world, ctx, civ)
        if spread:
            pool[T.SPREAD_FAITH] = (spread, [])
        shrines = _shrine_targets(world, ctx, civ)
        if shrines:
            pool[T.FOUND_SHRINE] = (shrines, [])
    elif role == "scientist":
        if techniques_on(world):
            cands = _invention_candidates(world, civ_idx, civ)
            if cands:
                pool[T.INVENT_TECHNIQUE] = (cands, [])
        else:
            era = _next_era(civ)
            if era is not None:
                pool[T.ADVANCE_LEARNING] = ([era], [])
    return pool


def _kind_weight(kind: T, gp) -> float:
    weight = _BASE_WEIGHT.get(kind, 1.0)
    leaning = _TRAIT_LEANING.get(kind)
    if leaning is not None and gp.trait in leaning[0]:
        weight *= leaning[1]
    return weight


def _remaining_life(world, gp) -> int:
    """Turns this person is still visible to the agenda tick (lifespan retirement)."""
    from chronicler.great_persons import _compute_lifespan
    lifespan = _compute_lifespan(world.seed, gp.born_turn, gp.name)
    return gp.born_turn + lifespan - 1 - world.turn


# ---------------------------------------------------------------------------
# Declaration
# ---------------------------------------------------------------------------

def _declare(world, ctx: _Ctx, state: GPAgendaState, civ_idx: int, civ, gp, rec: AgendaRecord,
             active) -> list[Event]:
    room = _remaining_life(world, gp)
    if room < MIN_DURATION:
        return []
    pool = _pool(world, ctx, state, civ_idx, civ, gp, rec, active)
    if not pool:
        return []
    key = gp_key(gp)
    rng = _rng("declare", world, key)
    draw = g04.SelectionDraw(rng.random(), rng.random(), rng.random())
    kinds = sorted(pool, key=lambda k: list(T).index(k))
    weights = [Fraction(_kind_weight(k, gp)) for k in kinds]
    point = Fraction(draw.ambition) * sum(weights)
    kind = kinds[-1]
    cumulative = Fraction(0)
    for k, w in zip(kinds, weights):
        cumulative += w
        if point < cumulative:
            kind = k
            break
    targets, motive = pool[kind]
    target = targets[min(int(draw.target * len(targets)), len(targets) - 1)]
    high = min(MAX_DURATION, room)
    span = high - MIN_DURATION + 1
    duration = MIN_DURATION + min(int(draw.duration * span), span - 1)
    faith = int(getattr(civ, "civ_majority_faith")) if kind == T.SPREAD_FAITH else None
    agenda = GovernanceAmbition(
        ambition_type=kind.value, target=target, generated_turn=world.turn,
        deadline_turn=world.turn + duration, generated_event_cursor=state.evidence_cursor,
        conversion_faith_id=faith, conversion_minimum_share=SPREAD_TARGET_SHARE if faith is not None else None)
    _ambition(agenda)  # validate against the kernel contract
    rec.serial += 1
    rec.agenda = agenda
    rec.civ = civ_idx
    rec.last_evaluated_turn = world.turn
    rec.last_event_cursor = state.evidence_cursor
    rec.deed_turn = None
    rec.commissioned = False
    rec.motive_events = [m for m in motive if m]
    goal = describe(world, kind, target)
    region = target if kind in (T.LEAD_CAMPAIGN, T.SPREAD_FAITH, T.FOUND_SHRINE) else None
    ev = _event(world, "agenda_declared", gp.name, civ,
                f"{gp.name}, {gp.role} of {civ.name}, vows to {goal}.", 4, region=region)
    causes = [prov.recall(world, prov.key("gp", gp.name)), *rec.motive_events]
    if kind == T.LEAD_CAMPAIGN:
        controller = ctx.region_map[target].controller
        if controller:
            causes.append(prov.recall(world, prov.war_key(civ.name, controller)))
            causes.append(prov.recall(world, "border:" + prov.pair(civ.name, controller)))
    prov.cite(ev, *causes)
    rec.declared_event = prov.remember(world, prov.key("gp_agenda", key), ev)
    _deed(gp, f"Vowed to {goal}", world, region=region)
    _count(state, "declared", f"declared:{gp.role}", f"declared:{kind.value}")
    events = [ev]
    events.extend(_bonds_on_declaration(world, ctx, state, civ_idx, civ, gp, rec, kind, target, active))
    return events


def _bonds_on_declaration(world, ctx: _Ctx, state: GPAgendaState, civ_idx: int, civ, gp,
                          rec: AgendaRecord, kind: T, target: str | None, active) -> list[Event]:
    key = gp_key(gp)
    events: list[Event] = []

    def add(ev):
        if ev is not None:
            events.append(ev)

    if kind == T.SEIZE_THRONE:
        ruler = civ.leader.name
        add(_form_bond(world, state, "opposition", key, _ruler_ref(civ_idx), civ_idx, civ, gp.name, ruler,
                       f"{gp.name} turns against {ruler} of {civ.name}.",
                       [rec.declared_event, *rec.motive_events], ruler=ruler))
        loyal = {b.a for b in _ruler_bonds(state, civ_idx, "loyalty", ruler)}
        recruits = 0
        for other_gp in list(civ.great_persons):
            if recruits >= MAX_CONSPIRATORS:
                break
            okey = gp_key(other_gp)
            orec = state.records.get(okey)
            if okey == key or okey in loyal or not _eligible(other_gp) or orec is None:
                continue
            opposed = bool([b for b in _ruler_bonds(state, civ_idx, "opposition", ruler) if b.a == okey])
            if other_gp.role == "general" or orec.failed > 0 or opposed:
                ev = _form_bond(world, state, "conspiracy", okey, key, civ_idx, civ, other_gp.name, gp.name,
                                f"{other_gp.name} joins the plot of {gp.name} against {ruler}.",
                                [rec.declared_event, orec.declared_event])
                if ev is not None:
                    recruits += 1
                    events.append(ev)
        return events

    for other_key, (o_idx, other_gp) in active.items():
        if other_key == key:
            continue
        orec = state.records.get(other_key)
        if orec is None or not _is_open(orec):
            continue
        okind = T(orec.agenda.ambition_type)
        otarget = orec.agenda.target
        # War party against trade party (same civ): a campaign against the civ
        # a merchant trades with or courts.
        if o_idx == civ_idx:
            general = merchant = g_target = m_target = g_decl = m_decl = None
            if kind == T.LEAD_CAMPAIGN and okind in (T.OPEN_TRADE_ROUTE, T.PROTECT_TRADE_ROUTE):
                general, merchant, g_target, m_target = (key, gp), (other_key, other_gp), target, otarget
                g_decl, m_decl = rec.declared_event, orec.declared_event
            elif okind == T.LEAD_CAMPAIGN and kind in (T.OPEN_TRADE_ROUTE, T.PROTECT_TRADE_ROUTE):
                general, merchant, g_target, m_target = (other_key, other_gp), (key, gp), otarget, target
                g_decl, m_decl = orec.declared_event, rec.declared_event
            if general is not None:
                region = ctx.region_map.get(g_target)
                partner = _civ_name(world, m_target)
                if region is not None and region.controller == partner:
                    add(_form_bond(world, state, "feud", general[0], merchant[0], civ_idx, civ,
                                   general[1].name, merchant[1].name,
                                   f"{general[1].name} and {merchant[1].name} of {civ.name} quarrel: "
                                   f"one wants war on {partner}, the other its trade.", [g_decl, m_decl]))
            continue
        other_civ = world.civilizations[o_idx]
        # Generals of two civs campaigning against each other.
        if kind == T.LEAD_CAMPAIGN and okind == T.LEAD_CAMPAIGN:
            mine = ctx.region_map.get(target)
            theirs = ctx.region_map.get(otarget)
            if (mine is not None and theirs is not None and mine.controller == other_civ.name
                    and theirs.controller == civ.name):
                add(_form_bond(world, state, "feud", key, other_key, civ_idx, civ, gp.name, other_gp.name,
                               f"{gp.name} of {civ.name} and {other_gp.name} of {other_civ.name} "
                               f"become sworn enemies in the field.", [rec.declared_event, orec.declared_event]))
        # Merchants of two civs courting each other's trade.
        if kind in (T.OPEN_TRADE_ROUTE, T.PROTECT_TRADE_ROUTE) and okind in (T.OPEN_TRADE_ROUTE,
                                                                               T.PROTECT_TRADE_ROUTE):
            if target == str(o_idx) and otarget == str(civ_idx):
                add(_form_bond(world, state, "partnership", key, other_key, civ_idx, civ, gp.name,
                               other_gp.name,
                               f"{gp.name} of {civ.name} and {other_gp.name} of {other_civ.name} "
                               f"become partners in trade.", [rec.declared_event, orec.declared_event]))
    return events


# ---------------------------------------------------------------------------
# Deeds (per open agenda, per turn) -> evidence
# ---------------------------------------------------------------------------

class _Evidence:
    """This tick's evidence for one record: (type, target, source event id)."""

    def __init__(self) -> None:
        self.items: list[tuple[str, str | None, str | None]] = []

    def add(self, event_type: str, target: str | None = None, source: str | None = None) -> None:
        self.items.append((event_type, target, source))


def _sour_disposition_step(world, a: str, b: str) -> bool:
    """Sour a neutral or suspicious pair one step (never below hostile).

    With ``--diplomacy`` the agitation also plants a border grievance in
    ``a``'s memory of ``b``, so diplomacy's own drift carries it on rather
    than its memory cap undoing it.
    """
    from chronicler.culture import _downgrade_disposition
    moved = False
    for x, y in ((a, b), (b, a)):
        rel = world.relationships.get(x, {}).get(y)
        if rel is not None and rel.disposition in (Disposition.NEUTRAL, Disposition.SUSPICIOUS):
            rel.disposition = _downgrade_disposition(rel.disposition)
            moved = True
    from chronicler.diplomacy_state import diplomacy_on
    if moved and diplomacy_on(world):
        from chronicler.diplomacy import add_grievance
        from chronicler.diplomacy_state import BORDER
        add_grievance(world, a, b, BORDER, AGITATION_GRIEVANCE)
    return moved


def _campaign_deeds(world, ctx, state, civ_idx, civ, gp, rec, acc, events) -> None:
    victories = [e for e in ctx.events if _won(e, civ.name)]
    if not victories:
        # In peace a general agitates against the people whose land he wants.
        region = ctx.region_map.get(rec.agenda.target)
        enemy = region.controller if region is not None else None
        if (enemy and enemy != civ.name and not _at_war(world, civ.name, enemy)
                and _rng("agitate", world, gp_key(gp)).random() < AGITATION_P
                and _sour_disposition_step(world, civ.name, enemy)):
            ctx.routes_changed()
            ev = _event(world, "war_agitation", gp.name, civ,
                        f"{gp.name} of {civ.name} agitates for war against {enemy}; relations sour.", 3,
                        extra_actors=(enemy,))
            prov.cite(ev, rec.declared_event)
            _deed(gp, f"Agitated for war against {enemy}", world)
            _deed_event(world, gp, ev)
            # The souring stands for the pair this turn: a trade road it cuts cites it.
            prov.remember(world, prov.key("gp_soured", prov.pair(civ.name, enemy)), ev)
            events.append(ev)
            _count(state, "war_agitation")
        return
    commanded = [e for e in victories if gp.name in e.description]
    rec.renown += COMMAND_RENOWN if commanded else VICTORY_RENOWN
    _stat(world, acc, civ_idx, civ, "prestige", VICTORY_PRESTIGE, "keep")
    lead = (commanded or victories)[0]
    enemy = lead.actors[1] if lead.actors[0] == civ.name else lead.actors[0]
    where = lead.region or "the field"
    verb = "leads" if commanded else "shares in"
    ev = _event(world, "campaign_victory", gp.name, civ,
                f"{gp.name} {verb} the victory of {civ.name} over {enemy} at {where}.", 4,
                region=lead.region, extra_actors=(enemy,))
    prov.cite(ev, prov.ensure_id(world, lead), rec.declared_event)
    _deed(gp, f"{'Led' if commanded else 'Shared in'} the victory over {enemy} at {where}", world,
          region=lead.region)
    _deed_event(world, gp, ev)
    events.append(ev)
    _count(state, "campaign_victories")


def _coup_attempt(world, ctx, state, civ_idx, civ, gp, rec, acc, events, evidence, active,
                  agent_bridge) -> None:
    key = gp_key(gp)
    ruler = civ.leader.name
    if (civ.succession_crisis_turns_remaining > 0 or not civ.leader.alive
            or world.turn - civ.leader.reign_start < COUP_MIN_REIGN or len(civ.regions) < 2):
        return
    weak, uneasy = ruler_weakness(world, civ)
    opposed = any(b.a == key for b in _ruler_bonds(state, civ_idx, "opposition", ruler))
    if not (weak or (uneasy and opposed)):
        return
    plotters = [p for p in _people(state, active, key, ("conspiracy",), same_civ=civ_idx)][:MAX_CONSPIRATORS]
    loyalists = [(b.a, active[b.a][1], b) for b in _ruler_bonds(state, civ_idx, "loyalty", ruler)
                 if b.a in active and active[b.a][0] == civ_idx][:MAX_CONSPIRATORS]
    rng = _rng("coup", world, key)
    if rng.random() >= COUP_ATTEMPT_P + COUP_ATTEMPT_PER_CONSPIRATOR * len(plotters):
        return
    legit, _crisis = _legitimacy(world, civ)
    standing = legit if legit is not None else civ.stability / 100.0
    military = civ.factions.influence.get(FactionType.MILITARY, 0.0)
    chance = (COUP_BASE_SUCCESS + COUP_MILITARY_WEIGHT * military + COUP_RENOWN_WEIGHT * min(rec.renown, 4)
              + COUP_BOND_WEIGHT * (len(plotters) - len(loyalists)) - COUP_LEGITIMACY_WEIGHT * standing)
    chance = min(COUP_SUCCESS_RANGE[1], max(COUP_SUCCESS_RANGE[0], chance))
    causes = [rec.declared_event, *rec.motive_events, *(b.event_id for _k, _g, b in plotters)]
    _count(state, "coup_attempts")
    if rng.random() < chance:
        emitted = _seize_throne(world, state, civ_idx, civ, gp, rec, acc, causes)
        evidence.add("gp_coup", None, prov.ensure_id(world, emitted[-1]))
    else:
        emitted = _crush_coup(world, state, civ_idx, civ, gp, rec, acc, causes, loyalists, agent_bridge)
        evidence.add("gp_coup_failed", None, prov.ensure_id(world, emitted[-1]))
    events.extend(emitted)


def _seize_throne(world, state, civ_idx, civ, gp, rec, acc, causes) -> list[Event]:
    """The coup succeeds: the existing GP-to-throne succession path."""
    from chronicler.factions import (
        _apply_gp_successor_winner, _build_gp_successor_candidate, get_dominant_faction,
    )
    from chronicler.leaders import apply_leader_legacy, check_rival_fall, generate_successor
    from chronicler.models import NamedEvent
    from chronicler.succession import create_exiled_leader

    events: list[Event] = []
    old = civ.leader
    old.alive = False
    legacy = apply_leader_legacy(civ, old, world)
    if legacy is not None:
        events.append(legacy)
    rival = check_rival_fall(civ, old.name, world, acc=acc)
    if rival is not None:
        events.append(rival)
    winner = _build_gp_successor_candidate(gp, civ, get_dominant_faction(civ.factions))
    new_leader = generate_successor(civ, world, seed=world.seed, force_type="general", acc=acc)
    civ.leader = new_leader
    _apply_gp_successor_winner(civ, new_leader, winner, world=world)
    civ.factions.pending_faction_shift = FactionType.MILITARY.value
    host = create_exiled_leader(old, civ, world)
    from chronicler.named_events import deduplicate_name
    name = deduplicate_name(f"The {civ.name} Coup", [ne.name for ne in world.named_events])
    world.named_events.append(NamedEvent(
        name=name, event_type="coup", turn=world.turn, actors=[civ.name],
        description=f"{new_leader.name} seizes power from {old.name}", importance=8))
    exile = f" {old.name} flees to {host}." if host else ""
    ev = _event(world, "gp_coup", gp.name, civ,
                f"{gp.name} overthrows {old.name} and takes the throne of {civ.name} as "
                f"{new_leader.name}.{exile}", 8, extra_actors=(new_leader.name,))
    prov.cite(ev, *causes)
    events.append(ev)
    rec.renown += FULFIL_RENOWN
    _deed(gp, f"Seized the throne of {civ.name} from {old.name}", world)
    _count(state, "coups", f"coups:{gp.source}")
    return events


def _crush_coup(world, state, civ_idx, civ, gp, rec, acc, causes, loyalists, agent_bridge) -> list[Event]:
    from chronicler.great_persons import kill_great_person
    ruler = civ.leader.name
    _deed(gp, f"Executed after a failed coup against {ruler}", world)
    agent_id = gp.agent_id
    kill_great_person(gp, civ, world, context="coup")
    if agent_id is not None and agent_bridge is not None:
        sim = getattr(agent_bridge, "_sim", None)
        if sim is not None and hasattr(sim, "queue_targeted_deaths"):
            sim.queue_targeted_deaths([int(agent_id)])
    _stat(world, acc, civ_idx, civ, "stability", -COUP_FAILED_STABILITY, "signal")
    foilers = ""
    if loyalists:
        names = [g.name for _k, g, _b in loyalists]
        foilers = f", betrayed by {' and '.join(names)}"
        for _k, g, b in loyalists:
            orec = state.records.get(gp_key(g))
            if orec is not None:
                orec.renown += 1
            causes.append(b.event_id)
    ev = _event(world, "gp_coup_failed", gp.name, civ,
                f"The coup of {gp.name} against {ruler} of {civ.name} fails{foilers}; "
                f"{gp.name} is put to death.", 7)
    prov.cite(ev, *causes)
    _count(state, "coups_failed")
    return [ev]


def _set_disposition_step(world, a: str, b: str) -> bool:
    """Warm both sides of a pair one step up to neutral. True if anything moved.

    With ``--diplomacy`` the mission also leaves goodwill in both memories,
    which lifts the cap diplomacy's memory puts on the disposition.
    """
    from chronicler.culture import upgrade_disposition
    moved = False
    for x, y in ((a, b), (b, a)):
        rel = world.relationships.get(x, {}).get(y)
        if rel is not None and rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
            rel.disposition = upgrade_disposition(rel.disposition)
            moved = True
    from chronicler.diplomacy_state import diplomacy_on
    if moved and diplomacy_on(world):
        from chronicler.diplomacy import add_goodwill
        add_goodwill(world, a, b, MISSION_GOODWILL)
        add_goodwill(world, b, a, MISSION_GOODWILL)
    return moved


def _trade_deeds(world, ctx, state, civ_idx, civ, gp, rec, kind, acc, events, evidence, active) -> None:
    key = gp_key(gp)
    target = rec.agenda.target
    if kind in (T.OPEN_TRADE_ROUTE, T.PROTECT_TRADE_ROUTE):
        other = _civ_name(world, target)
        other_civ = world.civilizations[int(target)]
        if not other_civ.regions:
            if kind == T.PROTECT_TRADE_ROUTE:
                evidence.add("trade_route_broken", target, None)
            return
        if kind == T.OPEN_TRADE_ROUTE:
            if _at_war(world, civ.name, other) or other in ctx.partners().get(civ.name, set()):
                return
            factor = PARTNERSHIP_MISSION_FACTOR if _people(state, active, key, ("partnership",)) else 1.0
            if _rng("mission", world, key).random() < MISSION_P * factor and \
                    _set_disposition_step(world, civ.name, other):
                ctx.routes_changed()
                ev = _event(world, "trade_mission", gp.name, civ,
                            f"{gp.name} of {civ.name} leads a trade mission to {other}; "
                            f"relations warm.", 3, extra_actors=(other,))
                prov.cite(ev, rec.declared_event)
                _deed(gp, f"Led a trade mission to {other}", world)
                _deed_event(world, gp, ev)
                events.append(ev)
                _count(state, "trade_missions")
            return
        # Protect: a war or embargo between the pair breaks the road; a sour
        # turn of relations can be talked down before it does.
        breach = next((e for e in ctx.events if e.event_type in ("war_declared", "war", "embargo")
                       and _pair_event(e, civ.name, other)), None)
        if breach is None and other not in ctx.partners().get(civ.name, set()) \
                and not _at_war(world, civ.name, other) and not _embargoed(world, civ.name, other):
            if _rng("intercede", world, key).random() < INTERCEDE_P and \
                    _set_disposition_step(world, civ.name, other):
                ctx.routes_changed()
                ev = _event(world, "trade_mission", gp.name, civ,
                            f"{gp.name} of {civ.name} smooths over a quarrel with {other} "
                            f"and keeps the trade road open.", 3, extra_actors=(other,))
                prov.cite(ev, rec.declared_event)
                _deed(gp, f"Kept the trade road to {other} open", world)
                _deed_event(world, gp, ev)
                events.append(ev)
                _count(state, "trade_missions")
        if breach is not None or other not in ctx.partners().get(civ.name, set()):
            source = (prov.ensure_id(world, breach) if breach is not None
                      else prov.recall(world, prov.key("gp_soured", prov.pair(civ.name, other)), within=0))
            evidence.add("trade_route_broken", target, source)
        return
    if kind == T.FOUND_TRADING_HOUSE:
        partners = ctx.partners().get(civ.name, set())
        region = _house_site(state, civ, gp)
        if (region is None or len(partners) < TRADING_HOUSE_MIN_PARTNERS
                or _projected_treasury(civ_idx, civ, acc) < 2 * TRADING_HOUSE_COST):
            return
        if _rng("trading_house", world, key).random() >= TRADING_HOUSE_P:
            return
        from chronicler.models import ArtifactIntent, ArtifactType
        _stat(world, acc, civ_idx, civ, "treasury", -TRADING_HOUSE_COST, "keep")
        state.houses[region] = world.turn
        world._artifact_intents.append(ArtifactIntent(
            artifact_type=ArtifactType.TRADE_GOOD, trigger="gp_trading_house",
            creator_name=gp.name, creator_born_turn=gp.born_turn, holder_name=None,
            holder_born_turn=None, civ_name=civ.name, region_name=region, anchored=True,
            context=f"Wares of the trading house {gp.name} founded in {region}"))
        _shift_faction(civ, FactionType.MERCHANT, FULFIL_FACTION_SHIFT)
        names = ", ".join(sorted(partners))
        ev = _event(world, "trading_house_founded", gp.name, civ,
                    f"{gp.name} founds a trading house in {region}, dealing with {names}.", 5,
                    region=region)
        prov.cite(ev, rec.declared_event)
        _deed(gp, f"Founded a trading house in {region}", world, region=region)
        events.append(ev)
        evidence.add("trading_house_founded", None, prov.ensure_id(world, ev))
        _count(state, "trading_houses")
        return
    if kind == T.LEND_TO_CROWN:
        loan = next((e for e in ctx.events if e.event_type == "loan_taken" and e.actors == [civ.name]), None)
        if loan is None:
            return
        ev = _event(world, "crown_loan", gp.name, civ,
                    f"{gp.name} underwrites the crown's borrowing from the merchant houses of {civ.name}.",
                    4)
        prov.cite(ev, prov.ensure_id(world, loan), rec.declared_event)
        _deed(gp, f"Lent to the crown of {civ.name}", world)
        events.append(ev)
        evidence.add("crown_loan", None, prov.ensure_id(world, ev))
        _count(state, "crown_loans")


def _faith_deeds(world, ctx, state, civ_idx, civ, gp, rec, kind, acc, events, evidence) -> None:
    target = rec.agenda.target
    region = ctx.region_map.get(target)
    if region is None:
        return
    if kind == T.SPREAD_FAITH:
        faith = rec.agenda.conversion_faith_id
        if ctx.region_beliefs is None or faith is None:
            return  # preaching reaches people only through the agent pool
        if region.conversion_target_signal not in (0xFF, faith):
            return  # another faith's preachers hold the region this turn
        if not _open_to_preaching(world, ctx, region, faith):
            return  # out of the faith's realms or under persecution: the prophet waits
        if region.conversion_target_signal == 0xFF:
            # An empty slot's rate (a martyrdom or conquest boost with no faith
            # to carry it) converts no one; the prophet brings his own pressure
            # and does not take that leftover over.
            region.conversion_target_signal = faith
            region.conversion_rate_signal = PREACHING_RATE
        else:
            region.conversion_rate_signal = region.conversion_rate_signal + PREACHING_RATE
        if not rec.commissioned:
            rec.commissioned = True
            gp.region = target
            ev = _event(world, "preaching", gp.name, civ,
                        f"{gp.name} of {civ.name} goes to preach the faith in {target}.", 3, region=target)
            prov.cite(ev, rec.declared_event)
            _deed(gp, f"Preached the faith in {target}", world, region=target)
            _deed_event(world, gp, ev)
            events.append(ev)
            _count(state, "preaching")
        return
    if kind == T.FOUND_SHRINE:
        from chronicler.models import InfrastructureType, PendingBuild
        done = next((e for e in ctx.events if e.event_type == "infrastructure_completed"
                     and e.actors[:1] == [civ.name]
                     and e.description == f"{InfrastructureType.TEMPLES.value} completed in {target}"), None)
        if done is not None:
            temple = next((i for i in region.infrastructure
                           if i.type == InfrastructureType.TEMPLES and i.active), None)
            if temple is not None:
                temple.temple_prestige += SHRINE_PRESTIGE
            ev = _event(world, "shrine_consecrated", gp.name, civ,
                        f"{gp.name} consecrates the temple of {target} as a shrine; pilgrims begin to come.",
                        5, region=target)
            prov.cite(ev, prov.ensure_id(world, done), rec.declared_event)
            _deed(gp, f"Consecrated the shrine of {target}", world, region=target)
            events.append(ev)
            evidence.add("infrastructure_completed", target, prov.ensure_id(world, ev))
            _count(state, "shrines")
            return
        if rec.commissioned or region.controller != civ.name or region.pending_build is not None:
            return
        from chronicler.infrastructure import get_build_specs, valid_build_types
        if InfrastructureType.TEMPLES not in valid_build_types(region, civ=civ, world=world):
            return
        spec = get_build_specs(world)[InfrastructureType.TEMPLES]
        cost = spec.cost
        from chronicler.techniques_state import techniques_on
        if techniques_on(world):
            from chronicler.techniques import build_cost
            cost = build_cost(world, region, InfrastructureType.TEMPLES, cost)
        if _projected_treasury(civ_idx, civ, acc) < cost:
            return
        _stat(world, acc, civ_idx, civ, "treasury", -cost, "keep")
        region.pending_build = PendingBuild(
            type=InfrastructureType.TEMPLES, builder_civ=civ.name, started_turn=world.turn,
            turns_remaining=spec.turns, faith_id=getattr(civ, "civ_majority_faith", -1))
        rec.commissioned = True
        ev = _event(world, "shrine_commissioned", gp.name, civ,
                    f"{gp.name} of {civ.name} commissions a temple in {target}.", 3, region=target)
        prov.cite(ev, rec.declared_event)
        _deed(gp, f"Commissioned a temple in {target}", world, region=target)
        _deed_event(world, gp, ev)
        events.append(ev)


def _learning_deeds(world, ctx, civ, rec, kind, evidence) -> None:
    if kind == T.ADVANCE_LEARNING:
        adv = next((e for e in ctx.events if e.event_type == "tech_advancement"
                    and e.actors[:1] == [civ.name]), None)
        if adv is not None:
            evidence.add("tech_advancement", civ.tech_era.value, prov.ensure_id(world, adv))
        return
    if kind == T.INVENT_TECHNIQUE:
        from chronicler.techniques_state import TECHNIQUES
        for e in ctx.events:
            if e.event_type != "technique_invented" or e.actors[:1] != [civ.name]:
                continue
            for spec in TECHNIQUES:
                if f" develops {spec.label} in " in e.description:
                    evidence.add("technique_invented", spec.key, prov.ensure_id(world, e))
                    break


# ---------------------------------------------------------------------------
# Evaluation and outcomes
# ---------------------------------------------------------------------------

def _evaluate(world, ctx: _Ctx, state: GPAgendaState, key: str, rec: AgendaRecord, civ,
              evidence: _Evidence) -> tuple[g04.AmbitionOutcome | None, list[str | None]]:
    """Resolve the open agenda with this tick's evidence. Returns the outcome
    (or None) and the source event ids of the evidence that settled it."""
    agenda = rec.agenda
    ambition = _ambition(agenda)
    ruler_id = f"{key}#{rec.serial}"
    sources: dict[int, str | None] = {}
    proofs = []
    for etype, target, source in evidence.items:
        state.evidence_cursor += 1
        sources[state.evidence_cursor] = source
        proofs.append(g04.EvidenceEvent(world.turn, state.evidence_cursor, key, etype, target))
    reign = g04.RulerAmbitions(key, ruler_id, agenda.generated_turn, agenda.generated_event_cursor,
                               (ambition,), (), rec.last_evaluated_turn, rec.last_event_cursor)
    kind = ambition.ambition_type
    owned = tuple(civ.regions) if civ is not None else ()
    partners: tuple[str, ...] = ()
    observations: tuple = ()
    if civ is not None and kind in (T.OPEN_TRADE_ROUTE, T.PROTECT_TRADE_ROUTE):
        partners = tuple(str(ctx.civ_index[p]) for p in ctx.partners().get(civ.name, set())
                         if p in ctx.civ_index)
    if kind == T.SPREAD_FAITH and agenda.conversion_faith_id is not None:
        share = ctx.share(agenda.target, agenda.conversion_faith_id)
        if share is not None:
            observations = (g04.ConversionObservation(agenda.target, agenda.conversion_faith_id,
                                                      belief_share=min(1.0, share)),)
    snapshot = g04.AmbitionSnapshot(
        civ_id=key, ruler_id=ruler_id, turn=world.turn, event_cursor=state.evidence_cursor,
        legitimacy=0.5, political_capital=0.0, owned_regions=owned,
        active_trade_partners=partners, conversion_observations=observations)
    result = g04.evaluate_ambitions(reign, snapshot, CALIBRATION, tuple(proofs))
    settled = result.reign.ambitions[0]
    rec.last_evaluated_turn = result.reign.last_evaluated_turn
    rec.last_event_cursor = result.reign.last_event_cursor
    rec.agenda = agenda.model_copy(update={"completed": settled.completed, "failed": settled.failed})
    if not result.outcomes:
        return None, []
    outcome = result.outcomes[0]
    wanted = (g04._EVENT_GOALS.get(kind, ()) if outcome.event_type == "ambition_fulfilled"
              else g04.GP_THWARTING_EVENTS.get(kind, ()))
    cited = [sources.get(p.sequence) for p in proofs if p.event_type in wanted]
    return outcome, cited


def _state_cause(world, ctx: _Ctx, civ, rec: AgendaRecord) -> list[str | None]:
    """Best evidence for a state goal reached this turn (the taking of the region)."""
    kind = T(rec.agenda.ambition_type)
    target = rec.agenda.target
    if kind == T.LEAD_CAMPAIGN:
        hit = next((e for e in ctx.events if (e.region == target or target in e.description)
                    and e.event_type in ("annexation", "occupation", "war", "expand", "conquest")), None)
        return [prov.ensure_id(world, hit) if hit is not None else None,
                prov.recall(world, prov.key("conquest", target), within=0),
                prov.recall(world, prov.key("occupation", target), within=0)]
    if kind == T.OPEN_TRADE_ROUTE and civ is not None:
        other = _civ_name(world, target)
        hit = next((e for e in reversed(ctx.events) if e.event_type == "trade_mission"
                    and other in e.actors), None)
        if hit is None:
            hit = next((e for e in reversed(ctx.events) if e.event_type in ("trade", "diplomacy")
                        and _pair_event(e, civ.name, other)), None)
        return [prov.ensure_id(world, hit) if hit is not None else None]
    return []


def _close(world, ctx: _Ctx, state: GPAgendaState, key: str, rec: AgendaRecord, civ_idx: int, civ,
           gp, outcome: g04.AmbitionOutcome, cited: list[str | None], acc, reason: str | None) -> list[Event]:
    kind = outcome.ambition_type
    goal = describe(world, kind, outcome.target)
    fulfilled = outcome.event_type == "ambition_fulfilled"
    name = rec.gp_name
    holder_civ = civ if civ is not None else world.civilizations[civ_idx]
    events: list[Event] = []
    region = outcome.target if kind in (T.LEAD_CAMPAIGN, T.SPREAD_FAITH, T.FOUND_SHRINE) else None
    if fulfilled:
        rec.completed += 1
        if kind != T.SEIZE_THRONE:
            rec.renown += FULFIL_RENOWN
        ev = _event(world, "agenda_fulfilled", name, holder_civ,
                    f"{name} of {holder_civ.name} fulfils the vow to {goal}.", 5, region=region)
        causes = [rec.declared_event, *cited]
        if not cited:
            causes += _state_cause(world, ctx, civ, rec)
            deed = prov.recall(world, prov.key("gp_deed", key))
            if deed is not None and (prov.id_turn(deed) or 0) >= rec.agenda.generated_turn:
                causes.append(deed)
        prov.cite(ev, *causes)
        prov.remember(world, prov.key("gp_agenda_done", key), ev)
        events.append(ev)
        if civ is not None and kind != T.SEIZE_THRONE:
            if kind == T.LEAD_CAMPAIGN:
                _stat(world, acc, civ_idx, civ, "prestige", CAMPAIGN_PRESTIGE, "keep")
            if kind not in (T.FOUND_TRADING_HOUSE,):
                _shift_faction(civ, ROLE_FACTION.get(rec.role), FULFIL_FACTION_SHIFT)
            # A person whose vow served the ruler's own faction (or who lent the
            # crown money) becomes the ruler's loyalist.
            from chronicler.factions import TRAIT_FACTION_MAP
            if civ.leader.alive and (kind == T.LEND_TO_CROWN or
                                     TRAIT_FACTION_MAP.get(civ.leader.trait) == ROLE_FACTION.get(rec.role)):
                bond = _form_bond(world, state, "loyalty", key, _ruler_ref(civ_idx), civ_idx, civ, name,
                                  civ.leader.name, f"{name} becomes a loyal servant of {civ.leader.name} "
                                  f"of {civ.name}.", [prov.ensure_id(world, ev)], ruler=civ.leader.name)
                if bond is not None:
                    events.append(bond)
        if gp is not None:
            _deed(gp, f"Fulfilled the vow to {goal}", world, region=region)
        _count(state, "fulfilled", f"fulfilled:{rec.role}", f"fulfilled:{kind.value}")
    else:
        rec.failed += 1
        rec.renown = max(0, rec.renown + FAIL_RENOWN)
        because = f" ({reason})" if reason else ""
        ev = _event(world, "agenda_failed", name, holder_civ,
                    f"{name} of {holder_civ.name} fails the vow to {goal}{because}.", 3, region=region)
        prov.cite(ev, rec.declared_event, *cited)
        prov.remember(world, prov.key("gp_agenda_failed", key), ev)
        events.append(ev)
        if gp is not None and gp.active:
            _deed(gp, f"Failed the vow to {goal}", world, region=region)
        _count(state, "failed", f"failed:{rec.role}", f"failed:{kind.value}")
    state.log.append(AgendaLogEntry(gp=name, role=rec.role, civ=rec.civ, kind=kind.value,
                                    target=outcome.target, start=rec.agenda.generated_turn, end=world.turn,
                                    outcome="fulfilled" if fulfilled else "failed", reason=reason))
    if len(state.log) > LOG_LIMIT:
        del state.log[:-LOG_LIMIT]
    rec.next_turn = world.turn + DECLARE_COOLDOWN
    rec.declared_event = None
    rec.motive_events = []
    return events


# ---------------------------------------------------------------------------
# Tick
# ---------------------------------------------------------------------------

def _active_persons(world) -> dict[str, tuple[int, "GreatPerson"]]:
    active: dict[str, tuple[int, "GreatPerson"]] = {}
    for civ_idx, civ in enumerate(world.civilizations):
        if not civ.regions:
            continue
        for gp in civ.great_persons:
            if _eligible(gp):
                active[gp_key(gp)] = (civ_idx, gp)
    return active


def _whereabouts(world, key: str, rec: AgendaRecord) -> str:
    """Why a record's holder is no longer an active agenda holder of its civ."""
    for gp in reversed(world.retired_persons):
        if gp_key(gp) == key:
            return _GONE_REASONS.get(gp.fate, gp.fate)
    for civ_idx, civ in enumerate(world.civilizations):
        for gp in civ.great_persons:
            if gp_key(gp) == key:
                if gp.is_hostage or gp.role == "hostage":
                    return "captivity"
                return "a change of allegiance" if civ_idx != rec.civ else "a change of calling"
    civ = world.civilizations[rec.civ] if rec.civ < len(world.civilizations) else None
    return "the fall of their people" if civ is not None and not civ.regions else "fate"


_GONE_REASONS = {
    "dead": "death", "retired": "retirement", "ascended_to_leadership": "a throne",
    "ascended": "a throne",
}


def tick_gp_agendas(world: "WorldState", turn_events: list[Event], acc=None, phase10=None,
                    agent_bridge=None) -> list[Event]:
    """Once per turn after Phase 10: close departed holders' agendas, perform
    deeds, resolve agendas, declare new ones and apply bond effects."""
    state = world.gp_agendas
    if not isinstance(state, GPAgendaState):
        return []
    ctx = _Ctx(world, turn_events, phase10)
    events: list[Event] = []
    active = _active_persons(world)

    # 1. Holders that left (death, retirement, a throne, captivity, a fallen
    #    civ): this turn's evidence first, then the departure itself.
    for key in list(state.records):
        rec = state.records[key]
        hit = active.get(key)
        if hit is not None and hit[0] == rec.civ and hit[1].role == rec.role:
            continue
        if _is_open(rec):
            civ = world.civilizations[rec.civ] if rec.civ < len(world.civilizations) else None
            civ = civ if civ is not None and civ.regions else None
            evidence = _Evidence()
            if civ is not None:
                kind = T(rec.agenda.ambition_type)
                if kind in (T.ADVANCE_LEARNING, T.INVENT_TECHNIQUE):
                    _learning_deeds(world, ctx, civ, rec, kind, evidence)
            evidence.add("holder_gone", None, None)
            outcome, cited = _evaluate(world, ctx, state, key, rec, civ, evidence)
            if outcome is not None:
                reason = None if outcome.event_type == "ambition_fulfilled" else \
                    f"cut short by {_whereabouts(world, key, rec)}"
                events.extend(_close(world, ctx, state, key, rec, rec.civ, civ, None, outcome, cited, acc,
                                     reason))
        del state.records[key]
    _prune_bonds(world, state, active)

    # 2. Active persons, in civ then roster order.
    for civ_idx, civ in enumerate(world.civilizations):
        if not civ.regions:
            continue
        for gp in list(civ.great_persons):
            if not _eligible(gp):
                continue
            key = gp_key(gp)
            rec = state.records.get(key)
            if rec is None:
                rec = AgendaRecord(gp_name=gp.name, born_turn=gp.born_turn, role=gp.role, civ=civ_idx,
                                   agent_id=gp.agent_id)
                state.records[key] = rec
            campaigning = _is_open(rec) and rec.agenda.ambition_type == T.LEAD_CAMPAIGN.value
            if gp.role == "general" and not campaigning:
                # Every general shares in the civ's victories (campaigners also
                # earn a deed and prestige, below).
                victories = [e for e in ctx.events if _won(e, civ.name)]
                if victories:
                    commanded = any(gp.name in e.description for e in victories)
                    rec.renown += COMMAND_RENOWN if commanded else VICTORY_RENOWN
            if _is_open(rec):
                if rec.agenda.generated_turn == world.turn:
                    continue
                events.extend(_advance(world, ctx, state, key, rec, civ_idx, civ, gp, acc, active,
                                       agent_bridge))
                continue
            if world.turn >= rec.next_turn and gp.active:
                events.extend(_declare(world, ctx, state, civ_idx, civ, gp, rec, active))

    # 3. Opposition agitates: the faction of a person set against the ruler.
    for bond in state.bonds:
        if bond.kind != "opposition" or bond.a not in active:
            continue
        civ_idx, gp = active[bond.a]
        if gp.active:
            _shift_faction(world.civilizations[civ_idx], ROLE_FACTION.get(gp.role), OPPOSITION_FACTION_SHIFT)
    return events


def _advance(world, ctx, state, key, rec, civ_idx, civ, gp, acc, active, agent_bridge) -> list[Event]:
    """One turn of an open agenda: its deed, then the kernel's verdict."""
    kind = T(rec.agenda.ambition_type)
    events: list[Event] = []
    evidence = _Evidence()
    if kind == T.LEAD_CAMPAIGN:
        _campaign_deeds(world, ctx, state, civ_idx, civ, gp, rec, acc, events)
    elif kind == T.SEIZE_THRONE:
        _coup_attempt(world, ctx, state, civ_idx, civ, gp, rec, acc, events, evidence, active, agent_bridge)
    elif kind in (T.OPEN_TRADE_ROUTE, T.PROTECT_TRADE_ROUTE, T.FOUND_TRADING_HOUSE, T.LEND_TO_CROWN):
        _trade_deeds(world, ctx, state, civ_idx, civ, gp, rec, kind, acc, events, evidence, active)
    elif kind in (T.SPREAD_FAITH, T.FOUND_SHRINE):
        _faith_deeds(world, ctx, state, civ_idx, civ, gp, rec, kind, acc, events, evidence)
    else:
        _learning_deeds(world, ctx, civ, rec, kind, evidence)
    outcome, cited = _evaluate(world, ctx, state, key, rec, civ, evidence)
    if outcome is not None:
        reason = None
        if outcome.event_type == "ambition_failed":
            if any(e[0] == "trade_route_broken" for e in evidence.items):
                reason = "the trade road was cut"
            elif any(e[0] == "gp_coup_failed" for e in evidence.items):
                reason = "the coup was crushed"
            else:
                reason = "time ran out"
        holder = gp if gp.active else None
        events.extend(_close(world, ctx, state, key, rec, civ_idx, civ, holder, outcome, cited, acc, reason))
    return events


# ---------------------------------------------------------------------------
# Succession crisis: who backs whom
# ---------------------------------------------------------------------------

def back_candidates(world, civ, candidates: list[dict]) -> None:
    """Alliances and rivalries weigh on a crisis's candidates (in place).

    A great-person candidate gains ``BACKING_WEIGHT`` per ally (conspiracy or
    partnership) in the civ and loses it per feuding rival; the outgoing
    ruler's loyalists back the internal candidate of the ruler's faction.
    Backers and opponents are recorded on the candidate by name.
    """
    state = getattr(world, "gp_agendas", None)
    if not isinstance(state, GPAgendaState) or not candidates:
        return
    from chronicler.factions import TRAIT_FACTION_MAP
    civ_idx = next((i for i, c in enumerate(world.civilizations) if c.name == civ.name), None)
    if civ_idx is None:
        return
    active = _active_persons(world)
    eligible = [gp for gp in civ.great_persons if _eligible(gp)]
    for cand in candidates:
        if cand.get("source") != "great_person":
            continue
        agent_id = cand.get("agent_id")
        gp = next((g for g in eligible if (g.agent_id == agent_id if agent_id is not None
                                           else g.agent_id is None and g.name == cand.get("gp_name"))), None)
        if gp is None:
            continue
        key = gp_key(gp)
        backers = sorted(g.name for _k, g, _b in _people(state, active, key, ("conspiracy", "partnership"),
                                                          same_civ=civ_idx))
        opponents = sorted(g.name for _k, g, _b in _people(state, active, key, ("feud",), same_civ=civ_idx))
        if backers or opponents:
            cand["weight"] = max(0.01, cand["weight"] + BACKING_WEIGHT * (len(backers) - len(opponents)))
            if backers:
                cand["backers"] = backers
            if opponents:
                cand["opponents"] = opponents
    loyalists = sorted(active[b.a][1].name for b in _ruler_bonds(state, civ_idx, "loyalty", civ.leader.name)
                       if b.a in active and active[b.a][0] == civ_idx)
    faction = TRAIT_FACTION_MAP.get(civ.leader.trait)
    if loyalists and faction is not None:
        for cand in candidates:
            if cand.get("source") == "internal" and cand.get("faction") == faction.value:
                cand["weight"] = cand["weight"] + BACKING_WEIGHT * len(loyalists)
                cand["backers"] = sorted(set(cand.get("backers", [])) | set(loyalists))
                break


def note_succession(world, civ, winner: dict | None, old_leader, new_leader) -> list[Event]:
    """After a crisis: the winner's backers become loyalists of the new ruler,
    a winning great person's feuding rivals its opposition."""
    state = getattr(world, "gp_agendas", None)
    if not isinstance(state, GPAgendaState) or not winner:
        return []
    civ_idx = next((i for i, c in enumerate(world.civilizations) if c.name == civ.name), None)
    if civ_idx is None:
        return []
    backers = winner.get("backers") or []
    opponents = winner.get("opponents") or []
    if not backers and not opponents:
        return []
    events: list[Event] = []
    by_name = {gp.name: gp for gp in civ.great_persons if _eligible(gp)}
    crisis = prov.recall(world, prov.key("leader_death", civ.name))
    if backers:
        ev = Event(turn=world.turn, event_type="succession_backed", actors=[civ.name, new_leader.name, *backers],
                   description=f"{new_leader.name} takes the throne of {civ.name} with the backing of "
                               f"{' and '.join(backers)}.", importance=6, civs=[civ.name])
        prov.cite(ev, crisis)
        events.append(ev)
        for name in backers:
            gp = by_name.get(name)
            if gp is None:
                continue
            bond = _form_bond(world, state, "loyalty", gp_key(gp), _ruler_ref(civ_idx), civ_idx, civ, gp.name,
                              new_leader.name, f"{gp.name} stands by {new_leader.name}, whom they raised "
                              f"to the throne of {civ.name}.", [prov.ensure_id(world, ev)],
                              ruler=new_leader.name)
            if bond is not None:
                events.append(bond)
    for name in opponents:
        gp = by_name.get(name)
        if gp is None:
            continue
        bond = _form_bond(world, state, "opposition", gp_key(gp), _ruler_ref(civ_idx), civ_idx, civ, gp.name,
                          new_leader.name, f"{gp.name} refuses to accept {new_leader.name} as ruler of "
                          f"{civ.name}.", [crisis], ruler=new_leader.name)
        if bond is not None:
            events.append(bond)
    return events


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def snapshot_summary(world) -> dict:
    """Per-turn summary for the bundle history (``history[n].gp_agendas``)."""
    state = world.gp_agendas
    open_agendas = []
    for rec in state.records.values():
        if not _is_open(rec):
            continue
        a = rec.agenda
        open_agendas.append({"gp": rec.gp_name, "role": rec.role, "civ": rec.civ, "kind": a.ambition_type,
                             "target": a.target, "deadline": a.deadline_turn, "renown": rec.renown})
    bonds: dict[str, int] = {}
    for bond in state.bonds:
        bonds[bond.kind] = bonds.get(bond.kind, 0) + 1
    totals = {k: state.counts.get(k, 0) for k in ("declared", "fulfilled", "failed", "coups", "coups_failed")}
    return {"open": open_agendas, "bonds": bonds, "totals": totals}


def run_metrics(state: dict | None) -> dict:
    """Counts from a saved world's ``gp_agendas`` (``None``: switch off)."""
    counts = (state or {}).get("counts", {})
    out = {"on": state is not None}
    for role in AGENDA_ROLES:
        out[f"declared_{role}"] = counts.get(f"declared:{role}", 0)
        out[f"fulfilled_{role}"] = counts.get(f"fulfilled:{role}", 0)
        out[f"failed_{role}"] = counts.get(f"failed:{role}", 0)
    for k in ("declared", "fulfilled", "failed", "coups", "coups_failed", "coup_attempts",
              "campaign_victories", "trade_missions", "trading_houses", "crown_loans", "shrines", "preaching"):
        out[k] = counts.get(k, 0)
    for kind in T:
        if kind in g04.GP_AGENDA_TYPES:
            out[f"declared:{kind.value}"] = counts.get(f"declared:{kind.value}", 0)
            out[f"fulfilled:{kind.value}"] = counts.get(f"fulfilled:{kind.value}", 0)
    out["bonds"] = {k.split(":", 1)[1]: v for k, v in counts.items() if k.startswith("bond:")}
    return out
