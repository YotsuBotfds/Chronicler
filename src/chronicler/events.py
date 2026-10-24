"""Event types and the decaying-hazard (self/cross-exciting) event model.

Correction (2026-10, see docs/integration/extinction-fix-2026-10.md):
until this change every rolled event permanently added its
``EVENT_CASCADE_RULES`` deltas to the world-level ``event_probabilities``.
Nothing ever decayed, so within ~100 turns rebellion, migration, border
incidents and leader deaths sat at probability 1.0 and plague at ~0.5,
striking a random half of all living civilizations regardless of contact.
Every default world went extinct.

The replacement keeps the same vocabulary but models each event type as a
per-civilization hazard rate:

    lambda_{c,k}(t) = lambda0_k * f_k(c, state) + E_{c,k}(t)
    P(k fires for c in turn t) = 1 - exp(-lambda_{c,k}(t))

* ``lambda0_k`` is derived from ``world.event_probabilities[k]`` which is now a
  constant *base rate* ``mu_k`` (old saves load unchanged; their stored values
  are read as base rates).  ``mu_k = 1.0`` still means "certain".
* ``f_k`` reads real state: drought from the climate phase and regional water,
  plague from endemic disease and crowding, border incidents from shared
  borders x hostility, rebellion/migration from unrest (or, in hybrid agent
  mode, from the agents' own rebel/migrant decisions), and so on.
* ``E_{c,k}`` is an exponentially decaying excitation (a Markov Hawkes kernel):
  every turn it is multiplied by ``exp(-1/HAZARD_DECAY_TAU)`` and every event
  that happened adds ``EVENT_CASCADE_RULES[source][k]`` to the civs it involved.
  Plague additionally excites plague in civs in contact (shared border or trade
  route) with the infected civ, and a border incident excites one in the
  counterparty.  With tau = 8 the branching ratio of the rule matrix is ~0.45,
  so cascades are subcritical and die out.

Leader deaths use their own hazard (``leader_mortality_hazard``): an age-based
Gompertz term plus war and coup terms plus the decaying excitation.
"""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from chronicler.models import Event

if TYPE_CHECKING:
    from chronicler.models import Civilization, Leader, WorldState

# Events that can occur during the Environment phase (natural causes)
ENVIRONMENT_EVENTS: list[str] = ["drought", "plague", "earthquake"]

# Non-environment hazards rolled in Phase 7 (leader_death has its own model).
RANDOM_EVENT_TYPES: list[str] = [
    "religious_movement",
    "discovery",
    "rebellion",
    "migration",
    "cultural_renaissance",
    "border_incident",
]

# When event X occurs, the civs involved get these hazard excitations
# (per-turn hazard units, decaying with HAZARD_DECAY_TAU).
EVENT_CASCADE_RULES: dict[str, dict[str, float]] = {
    "drought": {
        "plague": +0.02,        # Weakened populations get sick
        "migration": +0.04,     # People flee famine
        "rebellion": +0.03,     # Hungry people revolt
        "discovery": -0.02,     # Less resources for research
    },
    "plague": {
        "rebellion": +0.03,
        "migration": +0.03,
        "leader_death": +0.02,  # Leaders die too
        "cultural_renaissance": -0.02,
        "plague": -0.06,        # Survivors are immune for a while (self-inhibition)
    },
    "earthquake": {
        "migration": +0.02,
        "discovery": +0.01,     # Ruins exposed, new resources found
        "border_incident": +0.02,
    },
    "religious_movement": {
        "rebellion": +0.02,
        "cultural_renaissance": +0.03,
        "border_incident": +0.01,
    },
    "discovery": {
        "cultural_renaissance": +0.03,
        "border_incident": +0.02,  # Others covet the discovery
        "rebellion": -0.01,
    },
    "leader_death": {
        "rebellion": +0.05,
        "border_incident": +0.03,  # Neighbors sense weakness
        "migration": +0.01,
    },
    "rebellion": {
        "leader_death": +0.03,
        "migration": +0.02,
        "plague": +0.01,          # War brings disease
        "border_incident": +0.02,
    },
    "migration": {
        "border_incident": +0.03,
        "cultural_renaissance": +0.01,  # New ideas arrive
        "rebellion": +0.01,
    },
    "cultural_renaissance": {
        "discovery": +0.04,
        "rebellion": -0.02,       # People are content
        "religious_movement": +0.02,
    },
    "border_incident": {
        "rebellion": +0.01,
        "migration": +0.01,
    },
    # The four sources below were dead under the old cascade (they are emitted
    # by the tech, succession and leader phases, never rolled), so their rules
    # never ran.  They now excite through ingest_turn_events() (tech_advancement
    # from its Event; coup, legacy and rival_fall from their NamedEvents, which
    # every emitter records).  Their former "trade"/"war" targets were action
    # outcomes, not hazards, and had no consumer; they are dropped (action
    # weights keep their own capped system).
    "tech_advancement": {
        "discovery": 0.03,
        "cultural_renaissance": 0.02,
    },
    "coup": {
        "rebellion": 0.05,
        "border_incident": 0.03,
        "migration": 0.02,
    },
    "legacy": {
        "cultural_renaissance": 0.02,
        "discovery": 0.01,
    },
    "rival_fall": {
        "border_incident": -0.02,
    },
}

# --- Hazard model constants -------------------------------------------------

HAZARD_DECAY_TAU = 8.0
HAZARD_DECAY = math.exp(-1.0 / HAZARD_DECAY_TAU)
_EXCITATION_EPSILON = 1e-4

# Per-civ share of the world-level base rate.  The old roll fired at most one
# event per phase per turn on the whole world: environment events struck half
# of the living civs, other events one civ.  With the default four civs these
# shares keep the expected per-civ base rate where the old one started.
ENV_EVENT_CIV_SHARE = 0.5
RANDOM_EVENT_CIV_SHARE = 0.25

# Cross-civ excitation (per unit of contact).
PLAGUE_CONTACT_ALPHA = 0.04
BORDER_INCIDENT_RECIPROCITY_ALPHA = 0.03

# Agent roll-up references: the typical per-turn share of a civ's agents that
# rebel / migrate (regression oracle calibration band midpoints).
AGENT_REBEL_SHARE_REF = 0.05
AGENT_MIGRANT_SHARE_REF = 0.05
AGENT_ROLLUP_MAX_FACTOR = 4.0

# Leader mortality (per-turn hazards; one turn is one year for agents).
DEFAULT_LEADER_DEATH_MU = 0.03
GOMPERTZ_A = 0.004          # hazard at age 30
GOMPERTZ_B = 0.07           # doubling every ~10 years (mean reign ~30 years)
GOMPERTZ_REF_AGE = 30
LEADER_WAR_HAZARD = 0.008
LEADER_COUP_HAZARD = 0.012
LEADER_COUP_STABILITY = 30

_ACCESSION_AGE_RANGES: dict[str, tuple[int, int]] = {
    "heir": (18, 40),
    "general": (35, 55),
    "elected": (40, 62),
    "usurper": (28, 50),
}
_DEFAULT_ACCESSION_AGE_RANGE = (25, 48)

_DISPOSITION_HOSTILITY: dict[str, float] = {
    "hostile": 1.0,
    "suspicious": 0.6,
    "neutral": 0.35,
    "friendly": 0.15,
    "allied": 0.05,
}

_CLIMATE_DROUGHT_FACTOR: dict[str, float] = {
    "temperate": 0.6,
    "warming": 1.2,
    "drought": 2.0,
    "cooling": 0.8,
}


# --- Legacy helpers (kept for compatibility; no longer used by the turn loop) --

def roll_for_event(
    probabilities: dict[str, float],
    turn: int,
    seed: int | None = None,
    allowed_types: list[str] | None = None,
) -> Event | None:
    """Roll against each event probability; return at most one event.

    Events are checked in shuffled order. The first one that triggers wins.
    This means at most one event fires per call.  Retained as a utility; the
    simulation uses the per-civ hazard model below.
    """
    rng = random.Random(seed)
    candidates = list(probabilities.keys())
    if allowed_types is not None:
        candidates = [c for c in candidates if c in allowed_types]
    rng.shuffle(candidates)

    for event_type in candidates:
        prob = probabilities.get(event_type, 0.0)
        if rng.random() < prob:
            return Event(
                turn=turn,
                event_type=event_type,
                actors=[],
                description="",  # Filled in by narrative engine
                importance=5,
            )
    return None


def apply_probability_cascade(
    event_type: str,
    probabilities: dict[str, float],
) -> dict[str, float]:
    """Legacy non-decaying cascade (pure function).

    Retained for compatibility with external callers.  The simulation no
    longer mutates ``world.event_probabilities``; it uses decaying per-civ
    excitations instead (see module docstring).
    """
    rules = EVENT_CASCADE_RULES.get(event_type)
    if rules is None:
        return dict(probabilities)

    updated = dict(probabilities)
    for target, delta in rules.items():
        if target in updated:
            updated[target] = max(0.0, min(1.0, updated[target] + delta))
    return updated


# --- Hazard math ------------------------------------------------------------

def base_hazard(mu: float | None, share: float = 1.0) -> float:
    """Convert a per-turn base probability into a per-civ hazard rate."""
    if mu is None or mu <= 0.0:
        return 0.0
    if mu >= 1.0:
        return math.inf
    return -math.log1p(-mu) * share


def hazard_probability(rate: float) -> float:
    """Probability that a Poisson hazard of ``rate`` fires within one turn."""
    if rate <= 0.0:
        return 0.0
    if math.isinf(rate):
        return 1.0
    return -math.expm1(-rate)


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def rule_branching_ratio(tau: float = HAZARD_DECAY_TAU) -> float:
    """Spectral radius of tau * (positive cascade matrix): < 1 means subcritical."""
    types = sorted(set(EVENT_CASCADE_RULES) | {t for r in EVENT_CASCADE_RULES.values() for t in r})
    index = {t: i for i, t in enumerate(types)}
    n = len(types)
    matrix = [[0.0] * n for _ in range(n)]
    for source, rules in EVENT_CASCADE_RULES.items():
        for target, alpha in rules.items():
            matrix[index[source]][index[target]] = max(0.0, alpha) * tau
    # Power iteration on a non-negative matrix converges to the Perron root.
    vec = [1.0] * n
    radius = 0.0
    for _ in range(500):
        nxt = [sum(matrix[i][j] * vec[i] for i in range(n)) for j in range(n)]
        norm = max(nxt) if nxt else 0.0
        if norm <= 0.0:
            return 0.0
        vec = [v / norm for v in nxt]
        radius = norm
    return radius


# --- Excitation state (stored on Civilization.event_excitation) ---------------

def excite(civ: "Civilization", target: str, alpha: float) -> None:
    if alpha == 0.0:
        return
    store = civ.event_excitation
    store[target] = store.get(target, 0.0) + alpha


def apply_event_excitation(civ: "Civilization", event_type: str, scale: float = 1.0) -> None:
    """Add the cascade-rule excitations of one event to one involved civ."""
    rules = EVENT_CASCADE_RULES.get(event_type)
    if not rules:
        return
    for target, alpha in rules.items():
        excite(civ, target, alpha * scale)


def decay_excitations(world: "WorldState") -> None:
    """Advance every civ's excitation state by one turn."""
    for civ in world.civilizations:
        store = civ.event_excitation
        if not store:
            continue
        for key in list(store):
            value = round(store[key] * HAZARD_DECAY, 6)
            if abs(value) < _EXCITATION_EPSILON:
                del store[key]
            else:
                store[key] = value


def _civ_contact_weights(world: "WorldState") -> dict[str, dict[str, float]]:
    """Contact strength between living civs: shared border edges + trade routes."""
    region_map = world.region_map
    contact: dict[str, dict[str, float]] = {}
    for region in world.regions:
        owner = region.controller
        if owner is None:
            continue
        for adj_name in region.adjacencies:
            adj = region_map.get(adj_name)
            if adj is None or adj.controller is None or adj.controller == owner:
                continue
            row = contact.setdefault(owner, {})
            row[adj.controller] = row.get(adj.controller, 0.0) + 0.5
    try:
        from chronicler.resources import get_active_trade_routes
        routes = get_active_trade_routes(world)
    except Exception:  # pragma: no cover - defensive for partial test worlds
        routes = []
    for a, b in routes:
        if a == b:
            continue
        contact.setdefault(a, {})[b] = contact.setdefault(a, {}).get(b, 0.0) + 0.5
        contact.setdefault(b, {})[a] = contact.setdefault(b, {}).get(a, 0.0) + 0.5
    for row in contact.values():
        for key in row:
            row[key] = min(1.5, row[key])
    return contact


HAZARD_EVENT_TYPES: frozenset[str] = frozenset(
    ENVIRONMENT_EVENTS + RANDOM_EVENT_TYPES + ["leader_death"]
)
# Cascade sources read from the turn's other output (formerly dead rules).
TIMELINE_CASCADE_SOURCES: frozenset[str] = frozenset({"tech_advancement"})
NAMED_EVENT_CASCADE_SOURCES: frozenset[str] = frozenset({"coup", "legacy", "rival_fall"})


def record_hazard_event(world: "WorldState", event: Event) -> None:
    """Mark an event as rolled by the hazard model (or injected) this turn.

    Other phases emit events of the same type (e.g. climate "migration" and
    "earthquake" disasters) that are not hazard draws and must not excite.
    """
    world._hazard_events.append(event)


def take_turn_cascade_events(world: "WorldState", timeline_slice: list[Event]) -> list[Event]:
    """Hazard-rolled events plus formerly-dead timeline sources; clears the transient."""
    events = list(world._hazard_events)
    world._hazard_events.clear()
    events.extend(e for e in timeline_slice if e.event_type in TIMELINE_CASCADE_SOURCES)
    return events


def ingest_turn_events(
    world: "WorldState",
    events: list[Event],
    named_events: list | None = None,
) -> None:
    """Decay excitations one turn, then excite from this turn's cascade sources.

    ``events`` are the hazard-rolled/injected events plus tech_advancement
    events; ``named_events`` supply coup, legacy and rival_fall (the first
    actor of a NamedEvent is the civ it happened to).
    """
    from chronicler.provenance import note_excitation

    decay_excitations(world)
    civ_map = world.civ_map
    contact = None
    for event in events:
        etype = event.event_type
        if etype not in EVENT_CASCADE_RULES or etype in NAMED_EVENT_CASCADE_SOURCES:
            continue
        involved = []
        for actor in event.actors:
            civ = civ_map.get(actor)
            if civ is not None and civ.regions and civ not in involved:
                involved.append(civ)
        if not involved:
            continue
        for civ in involved:
            apply_event_excitation(civ, etype)
            note_excitation(world, civ.name, EVENT_CASCADE_RULES[etype], event)
        if etype == "plague":
            if contact is None:
                contact = _civ_contact_weights(world)
            infected = {c.name for c in involved}
            for civ in involved:
                for other_name, weight in sorted(contact.get(civ.name, {}).items()):
                    if other_name in infected:
                        continue
                    other = civ_map.get(other_name)
                    if other is not None and other.regions:
                        excite(other, "plague", PLAGUE_CONTACT_ALPHA * weight)
                        note_excitation(world, other.name, (("plague", PLAGUE_CONTACT_ALPHA * weight),), event)
        elif etype == "border_incident" and len(involved) >= 2:
            excite(involved[1], "border_incident", BORDER_INCIDENT_RECIPROCITY_ALPHA)
            note_excitation(world, involved[1].name,
                            (("border_incident", BORDER_INCIDENT_RECIPROCITY_ALPHA),), event)
    for named in named_events or []:
        etype = getattr(named, "event_type", None)
        if etype not in NAMED_EVENT_CASCADE_SOURCES or not named.actors:
            continue
        civ = civ_map.get(named.actors[0])
        if civ is not None and civ.regions:
            apply_event_excitation(civ, etype)


# --- State drivers f_k --------------------------------------------------------

class HazardContext:
    """Per-phase snapshot of the state the hazard drivers read."""

    def __init__(self, world: "WorldState", agent_unrest: dict | None = None):
        from chronicler.climate import get_climate_phase

        self.world = world
        self.region_map = world.region_map
        self.civ_regions: dict[str, list] = {c.name: [] for c in world.civilizations}
        for region in world.regions:
            if region.controller in self.civ_regions:
                self.civ_regions[region.controller].append(region)
        self.borders: dict[str, dict[str, int]] = {}
        for region in world.regions:
            owner = region.controller
            if owner is None:
                continue
            for adj_name in region.adjacencies:
                adj = self.region_map.get(adj_name)
                if adj is None or adj.controller is None or adj.controller == owner:
                    continue
                row = self.borders.setdefault(owner, {})
                row[adj.controller] = row.get(adj.controller, 0) + 1
        self.war_pairs: set[tuple[str, str]] = set()
        for pair in world.active_wars:
            a, b = pair[0], pair[1]
            self.war_pairs.add((a, b))
            self.war_pairs.add((b, a))
        self.at_war = {a for a, _ in self.war_pairs}
        self.conditions: dict[str, set[str]] = {}
        for cond in world.active_conditions:
            for name in cond.affected_civs:
                self.conditions.setdefault(name, set()).add(cond.condition_type)
        self.climate_phase = get_climate_phase(world.turn, world.climate_config).value
        # civ index -> (rebel_share, migrant_share) from the last agent tick
        self.agent_unrest = agent_unrest

    def has_condition(self, civ_name: str, condition: str) -> bool:
        return condition in self.conditions.get(civ_name, ())

    def hardship(self, civ: "Civilization") -> float:
        score = 0.0
        if self.has_condition(civ.name, "plague"):
            score += 0.5
        if self.has_condition(civ.name, "drought"):
            score += 0.5
        if any(r.famine_cooldown > 0 for r in self.civ_regions.get(civ.name, [])):
            score += 0.5
        return min(1.0, score)


def _drought_driver(civ, ctx: HazardContext) -> float:
    if ctx.has_condition(civ.name, "drought"):
        return 0.0  # an ongoing drought is not a new one
    from chronicler.ecology import TERRAIN_ECOLOGY_CAPS

    regions = ctx.civ_regions.get(civ.name, [])
    if regions:
        dryness = sum(
            _clamp01(1.0 - r.ecology.water / max(0.05, TERRAIN_ECOLOGY_CAPS.get(
                r.terrain, TERRAIN_ECOLOGY_CAPS["plains"])["water"]))
            for r in regions
        ) / len(regions)
    else:
        dryness = 0.0
    return _CLIMATE_DROUGHT_FACTOR.get(ctx.climate_phase, 1.0) * (0.5 + dryness)


def _plague_driver(civ, ctx: HazardContext) -> float:
    if ctx.has_condition(civ.name, "plague"):
        return 0.0  # the outbreak is already running
    regions = ctx.civ_regions.get(civ.name, [])
    total_pop = sum(r.population for r in regions)
    if regions:
        if total_pop > 0:
            severity = sum(r.endemic_severity * r.population for r in regions) / total_pop
        else:
            severity = sum(r.endemic_severity for r in regions) / len(regions)
        carry = sum(r.carrying_capacity for r in regions)
        crowd = _clamp01(total_pop / max(1, carry) - 0.8)
    else:
        severity = 0.0
        crowd = 0.0
    return 0.35 + 4.0 * severity + 0.5 * crowd


def _earthquake_driver(civ, ctx: HazardContext) -> float:
    regions = ctx.civ_regions.get(civ.name, [])
    if not regions:
        return 0.2
    mountains = sum(1 for r in regions if r.terrain == "mountains") / len(regions)
    coast = sum(1 for r in regions if r.terrain == "coast") / len(regions)
    return 0.2 + 2.0 * mountains + 0.6 * coast


def _religious_driver(civ, ctx: HazardContext) -> float:
    return 0.5 + (100 - civ.stability) / 100.0


def _discovery_driver(civ, ctx: HazardContext) -> float:
    return 0.4 + 0.6 * civ.culture / 100.0 + 0.4 * civ.economy / 100.0


def _renaissance_driver(civ, ctx: HazardContext) -> float:
    return 0.3 + 0.6 * civ.culture / 100.0 + 0.5 * civ.stability / 100.0


def _unrest(civ) -> float:
    return _clamp01((50 - civ.stability) / 50.0)


def _rebellion_driver(civ, ctx: HazardContext) -> float:
    return 0.25 + 1.75 * _unrest(civ) + 0.5 * ctx.hardship(civ)


def _migration_driver(civ, ctx: HazardContext) -> float:
    from chronicler.ecology import effective_capacity

    regions = ctx.civ_regions.get(civ.name, [])
    total_pop = sum(r.population for r in regions)
    eff = sum(effective_capacity(r) for r in regions)
    crowd = _clamp01(total_pop / max(1, eff) - 1.0)
    return 0.3 + 0.8 * ctx.hardship(civ) + 0.7 * crowd + 0.3 * _unrest(civ)


def border_incident_partners(civ, ctx: HazardContext) -> list[tuple[str, float]]:
    """Neighbors weighted by shared border length x hostility (x1.5 at war)."""
    partners: list[tuple[str, float]] = []
    relations = ctx.world.relationships.get(civ.name, {})
    for other, edges in sorted(ctx.borders.get(civ.name, {}).items()):
        rel = relations.get(other)
        disposition = getattr(getattr(rel, "disposition", None), "value", "neutral")
        weight = min(2, edges) * _DISPOSITION_HOSTILITY.get(disposition, 0.35)
        if (civ.name, other) in ctx.war_pairs:
            weight *= 1.5
        if weight > 0.0:
            partners.append((other, weight))
    return partners


def _border_driver(civ, ctx: HazardContext) -> float:
    total = sum(w for _, w in border_incident_partners(civ, ctx))
    return min(3.0, 0.8 * total)


_DRIVERS = {
    "drought": _drought_driver,
    "plague": _plague_driver,
    "earthquake": _earthquake_driver,
    "religious_movement": _religious_driver,
    "discovery": _discovery_driver,
    "cultural_renaissance": _renaissance_driver,
    "rebellion": _rebellion_driver,
    "migration": _migration_driver,
    "border_incident": _border_driver,
}

# In hybrid agent mode these civ events are a roll-up of the agents' own
# decisions (see civ_event_hazard).
_AGENT_ROLLUP_TYPES = {"rebellion": 0, "migration": 1}
_AGENT_ROLLUP_REFS = (AGENT_REBEL_SHARE_REF, AGENT_MIGRANT_SHARE_REF)


def hazard_driver(world: "WorldState", civ, event_type: str, ctx: HazardContext) -> float:
    driver = _DRIVERS.get(event_type)
    if driver is None:
        return 1.0
    return max(0.0, driver(civ, ctx))


def agents_own_unrest(world: "WorldState") -> bool:
    """Hybrid mode: rebellion/migration are agent decisions, not dice."""
    return getattr(world, "agent_mode", None) == "hybrid"


def civ_event_hazard(
    world: "WorldState",
    civ,
    civ_idx: int,
    event_type: str,
    ctx: HazardContext,
) -> float:
    """Per-turn hazard rate of ``event_type`` for one living civ."""
    share = ENV_EVENT_CIV_SHARE if event_type in ENVIRONMENT_EVENTS else RANDOM_EVENT_CIV_SHARE
    lam0 = base_hazard(world.event_probabilities.get(event_type), share)
    excitation = civ.event_excitation.get(event_type, 0.0)
    if event_type in _AGENT_ROLLUP_TYPES and agents_own_unrest(world):
        # Roll-up: the base rate scales with the share of the civ's agents
        # that actually rebelled/migrated last tick; excitation converts into
        # a civ-level event only while agents are restless (not amplified).
        slot = _AGENT_ROLLUP_TYPES[event_type]
        shares = (ctx.agent_unrest or {}).get(civ_idx)
        agent_share = shares[slot] if shares else 0.0
        factor = min(AGENT_ROLLUP_MAX_FACTOR, agent_share / _AGENT_ROLLUP_REFS[slot])
        if factor <= 0.0:
            return 0.0
        if math.isinf(lam0):
            return math.inf
        return max(0.0, lam0 * factor + excitation * min(1.0, factor))
    driver = hazard_driver(world, civ, event_type, ctx)
    if math.isinf(lam0):
        return math.inf if driver > 0.0 else max(0.0, excitation)
    return max(0.0, lam0 * driver + excitation)


# --- Leader age and mortality ---------------------------------------------------

def accession_age(succession_type: str, *parts: object) -> int:
    """Deterministic age at accession for a new leader."""
    from chronicler.utils import stable_hash_int

    lo, hi = _ACCESSION_AGE_RANGES.get(succession_type, _DEFAULT_ACCESSION_AGE_RANGE)
    return lo + stable_hash_int("leader_accession_age", succession_type, *parts) % (hi - lo + 1)


def ensure_leader_birth_turn(leader: "Leader", world: "WorldState") -> int:
    """Return the leader's birth turn, inferring one for founders and old saves."""
    if leader.birth_turn is None:
        leader.birth_turn = leader.reign_start - accession_age(
            leader.succession_type, world.seed, leader.name, leader.reign_start,
        )
    return leader.birth_turn


def leader_age(leader: "Leader", world: "WorldState") -> int:
    return max(0, world.turn - ensure_leader_birth_turn(leader, world))


def leader_mortality_components(
    world: "WorldState", civ, ctx: HazardContext,
) -> dict[str, float]:
    """Hazard components (per turn) of the current leader's death."""
    mu = world.event_probabilities.get("leader_death")
    lam0 = base_hazard(mu)
    if lam0 <= 0.0:
        scale = 0.0
    elif math.isinf(lam0):
        scale = math.inf
    else:
        scale = lam0 / base_hazard(DEFAULT_LEADER_DEATH_MU)
    age = leader_age(civ.leader, world)
    natural = GOMPERTZ_A * math.exp(GOMPERTZ_B * (age - GOMPERTZ_REF_AGE))
    battle = LEADER_WAR_HAZARD if civ.name in ctx.at_war else 0.0
    coup = LEADER_COUP_HAZARD * _clamp01(
        (LEADER_COUP_STABILITY - civ.stability) / LEADER_COUP_STABILITY
    )

    def _scaled(value: float) -> float:
        if value <= 0.0 or scale == 0.0:
            return 0.0
        return math.inf if math.isinf(scale) else scale * value

    return {
        "natural": _scaled(natural),
        "battle": _scaled(battle),
        "coup": _scaled(coup),
        "misfortune": max(0.0, civ.event_excitation.get("leader_death", 0.0)),
    }


def leader_mortality_hazard(world: "WorldState", civ, ctx: HazardContext) -> float:
    return sum(leader_mortality_components(world, civ, ctx).values())


def pick_mortality_cause(components: dict[str, float], draw: float) -> str:
    """Choose the death cause proportionally to the hazard components."""
    infinite = [k for k, v in components.items() if math.isinf(v)]
    if infinite:
        return infinite[0]
    total = sum(components.values())
    if total <= 0.0:
        return "natural"
    acc = 0.0
    target = draw * total
    for key, value in components.items():
        acc += value
        if target < acc:
            return key
    return next(reversed(components))
