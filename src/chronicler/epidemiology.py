"""Epidemiology: one regional SEIRS disease model for plague and pandemics.

With the switch on, this module replaces both earlier disease paths:

* the hazard-rolled ``plague`` event of Phase 1 (``simulation.phase_environment``),
  which struck a civilization with a fixed toll whenever a per-civ hazard fired;
* the M18 black-swan ``pandemic`` (``emergence.tick_pandemic``), which spread a
  timer-driven infection along adjacency or contact and charged a per-civ toll.

Model
    A small registry of pathogens (:data:`PATHOGENS`; identity is the index,
    never reorder) with transmissibility (``r0``), latency (``onset``),
    infectious period (``recovery``), severity (``cfr``), immunity duration and
    mutation. Each region keeps S/E/I/R shares per pathogen
    (:class:`RegionInfection`). Within a region the shares follow a discrete
    SEIRS recursion over :data:`SUBSTEPS` seasons per turn; nothing is random
    there. Randomness enters only through *introductions*: spillover from a
    pathogen's reservoir regions (``homelands``) and imports along the contact
    ledger's region x region flows (trade, migrants, soldiers, pilgrims), each
    one namespaced ``stable_hash_int`` draw.

First contact
    A population that has never had a pathogen (``seen``) has no immunity and
    suffers a higher case fatality (:data:`VIRGIN_SOIL_CFR`). Homelands start
    half immune, so their outbreaks are mild while the same pathogen carried
    to a newly contacted population is a virgin-soil epidemic.

Mortality
    Deaths go through the same path as the hazard plague: ``drain_region_pop``
    on the region plus ``stage_region_catastrophe_deaths`` when the Rust agent
    pool tracks population, so hybrid deaths reach the agents.

Second-order effects
    Famine and crowding raise susceptibility (famine also raises fatality);
    states facing a foreign epidemic close their borders (quarantine cuts
    foreign imports and costs treasury); epidemic deaths leave a decaying
    labour scarcity that eases popular immiseration in the governance PSI.
    A civ whose regions fall sick suffers a ``plague`` outbreak exactly as the
    hazard plague did (stability, ``plague`` condition, hazard cascade).

The world field ``WorldState.epidemics`` doubles as the switch: ``None`` means
off, nothing here runs and every output is identical to a run without this
module. See ``docs/integration/epidemiology.md``.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:  # pragma: no cover
    from chronicler.models import Event, WorldState


#: Default for worlds newly created by the CLI/batch/live entry points
#: (``--epidemiology`` opts in; loaded worlds keep their saved setting).
DEFAULT_ENABLED_FOR_NEW_WORLDS = False


# ---------------------------------------------------------------------------
# Pathogen registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Pathogen:
    """One disease. Rates are per season (``SUBSTEPS`` seasons per turn)."""

    name: str              # stable identifier (narration category)
    label: str             # narrated name
    r0: float              # basic reproduction number
    onset: float           # P(exposed -> infectious) per season (latency)
    recovery: float        # P(leaving infectious) per season (infectious period)
    cfr: float             # P(death) on leaving the infectious state
    immunity_turns: float  # mean immunity in turns; 0 means lifelong
    mutation: float        # P(new strain) per turn while the pathogen circulates
    escape: float          # share of existing immunity a new strain escapes
    spillover: float       # per-turn emergence hazard in a homeland region
    vector: str | None     # homeland selector: M35b vector label, "crowd", or None
    importance: int        # base importance of its outbreak events


#: Index is identity (persisted in state); append new pathogens, never reorder.
PATHOGENS: tuple[Pathogen, ...] = (
    Pathogen("plague", "the plague", r0=2.4, onset=0.7, recovery=0.85, cfr=0.10,
             immunity_turns=30, mutation=0.0, escape=0.0, spillover=0.004,
             vector="plague", importance=7),
    Pathogen("pox", "the pox", r0=3.0, onset=0.6, recovery=0.8, cfr=0.08,
             immunity_turns=0, mutation=0.0, escape=0.0, spillover=0.0025,
             vector="crowd", importance=7),
    Pathogen("fever", "the marsh fever", r0=1.9, onset=0.9, recovery=0.9, cfr=0.02,
             immunity_turns=12, mutation=0.03, escape=0.6, spillover=0.006,
             vector="fever", importance=5),
    Pathogen("flux", "the bloody flux", r0=1.8, onset=0.9, recovery=0.9, cfr=0.04,
             immunity_turns=8, mutation=0.0, escape=0.0, spillover=0.007,
             vector="cholera", importance=5),
    Pathogen("pestilence", "the great pestilence", r0=3.0, onset=0.7, recovery=0.8, cfr=0.18,
             immunity_turns=40, mutation=0.0, escape=0.0, spillover=0.0,
             vector=None, importance=9),
)
PATHOGEN_INDEX: dict[str, int] = {p.name: i for i, p in enumerate(PATHOGENS)}
PLAGUE = PATHOGEN_INDEX["plague"]
PESTILENCE = PATHOGEN_INDEX["pestilence"]


# ---------------------------------------------------------------------------
# Parameters ([CALIBRATE] values are documented in docs/integration/epidemiology.md)
# ---------------------------------------------------------------------------

SUBSTEPS = 4                 # seasons per turn in the within-region recursion
QUANTUM_DIGITS = 9           # stored shares are rounded to this many decimals
EXTINCT_PEOPLE = 0.5         # an outbreak with fewer exposed+infectious people dies out
IMMUNITY_FLOOR = 1e-4        # rows with less immunity than this (and no infection) are dropped
INTRO_PEOPLE = 1.0           # exposed people seeded by one spillover or import
BLACK_SWAN_INTRO_SHARE = 0.05  # share of the origin seeded by a black-swan pandemic
INJECTED_INTRO_SHARE = 0.05    # share of the region seeded by an injected plague

#: Import hazard per unit of (weighted contact x source infectious share x r0 x
#: target susceptibility). Contact is the ledger's decayed stock (about ten
#: turns of flow), weighted by ``contact_ledger.CONTACT_WEIGHTS``.
IMPORT_SCALE = 0.1

#: An outbreak is reported (and counts as an epidemic) when its new infections
#: in a turn reach this many people and this share of the region.
EPIDEMIC_MIN_CASES = 2.0
EPIDEMIC_MIN_SHARE = 0.03

#: Spillover rises with the region's M35b endemic severity over its baseline
#: (flares from crowding, armies, bad water, season), up to this factor.
ENDEMIC_SPILLOVER_CAP = 3.0

#: Homeland (reservoir) regions start with this share immune.
HOMELAND_IMMUNITY = 0.5
#: One region in ``HOMELAND_ODDS`` of a pathogen's vector becomes a homeland.
HOMELAND_ODDS = 3

#: A civ suffers a ``plague`` outbreak (stability, condition, hazard cascade)
#: when an epidemic in its regions kills at least this share of the infected.
MAJOR_CFR = 0.08

#: Virgin-soil fatality multiplier (the pathogen never reached the population).
VIRGIN_SOIL_CFR = 1.5
#: Susceptibility: famine and crowding (population over carrying capacity).
FAMINE_SUSCEPTIBILITY = 0.2
CROWDING_SUSCEPTIBILITY = 0.5
CROWDING_THRESHOLD = 0.8
FAMINE_CFR = 0.25
MAX_CFR = 0.9
#: Safety bound on one region's epidemic deaths in a turn (share of its people).
MAX_TURN_MORTALITY = 0.25

#: Quarantine: a state with this stability and treasury closes its borders
#: while an epidemic rages in a region of another polity it is in contact with.
QUARANTINE_MIN_STABILITY = 30
QUARANTINE_COST = 2          # treasury per turn ("keep")
QUARANTINE_EFFICACY = 0.7    # share of foreign import pressure stopped

#: Labour scarcity: share of a civ's people killed by epidemics, decayed per turn.
LABOUR_DECAY = 0.9
LABOUR_FLOOR = 1e-4
#: Popular immiseration (governance MMP) is divided by 1 + gain x scarcity.
LABOUR_WAGE_GAIN = 5.0

#: Leader mortality: chance = exposure x the capital's epidemic death share.
LEADER_EXPOSURE = 1.0
LEADER_MAX_P = 0.5

CHANNEL_CARRIERS: tuple[str, ...] = ("Merchants", "Migrants", "Soldiers", "Pilgrims")


# ---------------------------------------------------------------------------
# Persisted state
# ---------------------------------------------------------------------------

class RegionInfection(BaseModel):
    """S/E/I/R shares of one pathogen in one region (identity: indices)."""

    region: int
    pathogen: int
    n: int                    # population the shares describe (at the last tick)
    s: float = 1.0
    e: float = 0.0
    i: float = 0.0
    r: float = 0.0
    burden: float = 0.0       # mean infectious share over the last tick (drives exports)
    cases: float = 0.0        # new infections in the last tick (people)
    virgin: bool = False      # the running outbreak reached a never-exposed population
    reported: bool = False    # the running outbreak has been reported (an open episode)
    cause: str = ""           # event the next onset report cites (pandemic, injection, last outbreak)
    # Contact import awaiting its onset report: source region, ledger channel
    # and the turn it arrived (the arrival event is emitted with the onset).
    source: int = -1
    channel: int = -1
    arrival_turn: int = -1


class EpidemicState(BaseModel):
    """Per-region infection rows plus the small amount of world-level memory."""

    initialized_turn: int | None = None
    last_tick_turn: int = -1
    rows: list[RegionInfection] = Field(default_factory=list)
    # (region, pathogen) pairs: reservoirs, and populations that ever had it.
    homelands: list[tuple[int, int]] = Field(default_factory=list)
    seen: list[tuple[int, int]] = Field(default_factory=list)
    strains: list[int] = Field(default_factory=lambda: [0] * len(PATHOGENS))
    quarantine: list[int] = Field(default_factory=list)        # civ indices closed to imports
    scarcity: list[tuple[int, float]] = Field(default_factory=list)  # (civ index, decayed share)
    last_deaths: list[tuple[int, int, int]] = Field(default_factory=list)  # (region, pathogen, deaths)
    deaths_total: int = 0


# ---------------------------------------------------------------------------
# Switch and queries
# ---------------------------------------------------------------------------

def epidemiology_enabled(world) -> bool:
    """True only for a real state (mocks and ``None`` read as off)."""
    return isinstance(getattr(world, "epidemics", None), EpidemicState)


def set_epidemiology_enabled(world: "WorldState", enabled: bool) -> None:
    """Enable (creating an empty state) or disable epidemiology on a world."""
    if enabled:
        if world.epidemics is None:
            world.epidemics = EpidemicState()
    else:
        world.epidemics = None


def _reportable(row: RegionInfection) -> bool:
    return row.cases >= max(EPIDEMIC_MIN_CASES, EPIDEMIC_MIN_SHARE * row.n)


def active_region_names(world) -> set[str]:
    """Regions with a reported epidemic in the last tick (empty when off)."""
    if not epidemiology_enabled(world):
        return set()
    n = len(world.regions)
    return {world.regions[row.region].name for row in world.epidemics.rows
            if row.region < n and _reportable(row)}


def labour_scarcity(world, civ_idx: int) -> float:
    """Decayed share of a civ's people lost to epidemics (0 when off)."""
    if not epidemiology_enabled(world):
        return 0.0
    for idx, value in world.epidemics.scarcity:
        if idx == civ_idx:
            return value
    return 0.0


def mmp_labour_relief(world, civ_idx: int) -> float:
    """Divisor for popular immiseration: scarce labour raises relative wages."""
    return 1.0 + LABOUR_WAGE_GAIN * labour_scarcity(world, civ_idx)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _q(x: float) -> float:
    return round(x, QUANTUM_DIGITS)


def _draw(namespace: str, world, *parts: object) -> float:
    from chronicler.utils import stable_hash_int
    return random.Random(stable_hash_int(namespace, world.seed, world.turn, *parts)).random()


def _agent_pool_tracks_population(world) -> bool:
    from chronicler.simulation import _agent_pool_tracks_population as tracks
    return tracks(world)


def _vector(region) -> str:
    from chronicler.ecology import disease_vector_label
    return disease_vector_label(region)


def _row_key(row: RegionInfection) -> tuple[int, int]:
    return (row.region, row.pathogen)


def _new_row(region_idx: int, pathogen: int, n: int) -> RegionInfection:
    return RegionInfection(region=region_idx, pathogen=pathogen, n=n)


def _normalize(row: RegionInfection) -> None:
    """Round shares and restore s + e + i + r = 1 exactly up to rounding."""
    s, e, i, r = (max(0.0, v) for v in (row.s, row.e, row.i, row.r))
    total = s + e + i + r
    if total <= 0.0:
        s, e, i, r = 1.0, 0.0, 0.0, 0.0
        total = 1.0
    s, e, i = _q(s / total), _q(e / total), _q(i / total)
    r = _q(1.0 - s - e - i)
    if r < 0.0:
        s = _q(s + r)
        r = 0.0
    row.s, row.e, row.i, row.r = s, e, i, r


def _seed(row: RegionInfection, people: float, *, cause: str, virgin: bool,
          source: int = -1, channel: int = -1, turn: int = -1) -> None:
    """Move ``people`` susceptibles to exposed (bounded by the susceptible share)."""
    if row.n <= 0:
        return
    share = min(row.s, people / row.n)
    row.s -= share
    row.e += share
    row.cause = cause
    row.virgin = virgin
    row.reported = False
    row.source, row.channel, row.arrival_turn = source, channel, turn
    _normalize(row)


def _circulating(row: RegionInfection) -> bool:
    return (row.e + row.i) * row.n >= EXTINCT_PEOPLE


def _modifiers(region) -> tuple[float, float, bool]:
    """(susceptibility multiplier, fatality multiplier, famine) of a region."""
    famine = region.famine_cooldown > 0
    crowd = region.population / max(1, region.carrying_capacity) - CROWDING_THRESHOLD
    crowd = 0.0 if crowd < 0.0 else 1.0 if crowd > 1.0 else crowd
    susc = 1.0 + (FAMINE_SUSCEPTIBILITY if famine else 0.0) + CROWDING_SUSCEPTIBILITY * crowd
    cfr = 1.0 + (FAMINE_CFR if famine else 0.0)
    return susc, cfr, famine


# ---------------------------------------------------------------------------
# Initialization: reservoirs
# ---------------------------------------------------------------------------

def _initialize(world, state: EpidemicState) -> None:
    """Choose each pathogen's homelands deterministically; they start half immune.

    A homeland is a region whose M35b disease vector matches the pathogen
    (``crowd``: the more populous half of the land), selected by a hash of
    the world seed, pathogen and region index, at least one per pathogen.
    """
    from chronicler.utils import stable_hash_int

    regions = world.regions
    homelands: list[tuple[int, int]] = []
    caps = sorted((r.carrying_capacity for r in regions), reverse=True)
    crowd_cut = caps[(len(caps) - 1) // 2] if caps else 0
    for k, p in enumerate(PATHOGENS):
        if p.vector is None or p.spillover <= 0.0:
            continue
        if p.vector == "crowd":
            eligible = [j for j, r in enumerate(regions) if r.carrying_capacity >= crowd_cut]
        else:
            eligible = [j for j, r in enumerate(regions) if _vector(r) == p.vector]
        if not eligible:
            continue
        hashes = {j: stable_hash_int("epidemic_homeland", world.seed, k, j) for j in eligible}
        chosen = [j for j in eligible if hashes[j] % HOMELAND_ODDS == 0]
        if not chosen:
            chosen = [min(eligible, key=lambda j: (hashes[j], j))]
        homelands.extend((j, k) for j in chosen)
    homelands.sort()
    state.homelands = homelands
    state.seen = list(homelands)
    rows = {_row_key(row): row for row in state.rows}
    for j, k in homelands:
        n = int(regions[j].population)
        if n <= 0 or (j, k) in rows:
            continue
        row = _new_row(j, k, n)
        row.s, row.r = 1.0 - HOMELAND_IMMUNITY, HOMELAND_IMMUNITY
        _normalize(row)
        rows[(j, k)] = row
    state.rows = [rows[key] for key in sorted(rows)]
    if len(state.strains) < len(PATHOGENS):
        state.strains = list(state.strains) + [0] * (len(PATHOGENS) - len(state.strains))
    state.initialized_turn = world.turn


# ---------------------------------------------------------------------------
# Introductions from outside the turn loop (black swan, injection)
# ---------------------------------------------------------------------------

def _row_for(state: EpidemicState, region_idx: int, pathogen: int, n: int) -> RegionInfection:
    for row in state.rows:
        if row.region == region_idx and row.pathogen == pathogen:
            return row
    row = _new_row(region_idx, pathogen, n)
    state.rows.append(row)
    state.rows.sort(key=_row_key)
    return row


def _is_virgin(state: EpidemicState, region_idx: int, pathogen: int) -> bool:
    """True if the population never had an epidemic of the pathogen."""
    return (region_idx, pathogen) not in state.seen


def _mark_seen(state: EpidemicState, region_idx: int, pathogen: int) -> None:
    """Record that the population had an epidemic (reported outbreak)."""
    key = (region_idx, pathogen)
    if key not in state.seen:
        state.seen.append(key)
        state.seen.sort()


def seed_pandemic(world, region_idx: int, event: "Event") -> None:
    """M18 black swan under epidemiology: a novel strain of the great pestilence.

    Nobody is immune to a new strain and no population has met it, so every
    region is virgin soil. ``event`` (the ``pandemic`` event) is the cause the
    origin's outbreak cites.
    """
    from chronicler import provenance

    state = world.epidemics
    if state.initialized_turn is None:
        _initialize(world, state)
    k = PESTILENCE
    state.strains[k] += 1
    state.seen = [key for key in state.seen if key[1] != k]
    for row in state.rows:
        if row.pathogen == k:
            row.s += row.r
            row.r = 0.0
            _normalize(row)
    region = world.regions[region_idx]
    n = int(region.population)
    if n <= 0:
        return
    row = _row_for(state, region_idx, k, n)
    row.n = n
    virgin = _is_virgin(state, region_idx, k)
    _seed(row, max(INTRO_PEOPLE, BLACK_SWAN_INTRO_SHARE * n),
          cause=provenance.ensure_id(world, event) or "", virgin=virgin)


def seed_injection(world, civ, event: "Event") -> bool:
    """An injected plague seeds the plague in the civ's capital (or largest region)."""
    from chronicler import provenance

    state = world.epidemics
    if state.initialized_turn is None:
        _initialize(world, state)
    index = {r.name: j for j, r in enumerate(world.regions)}
    owned = [j for j, r in enumerate(world.regions) if r.controller == civ.name and r.population > 0]
    if not owned:
        return False
    capital = index.get(civ.capital_region) if civ.capital_region else None
    target = capital if capital in owned else max(owned, key=lambda j: (world.regions[j].population, -j))
    n = int(world.regions[target].population)
    row = _row_for(state, target, PLAGUE, n)
    row.n = n
    virgin = _is_virgin(state, target, PLAGUE)
    _seed(row, max(INTRO_PEOPLE, INJECTED_INTRO_SHARE * n),
          cause=provenance.ensure_id(world, event) or "", virgin=virgin)
    return True


# ---------------------------------------------------------------------------
# The turn tick (Phase 1, after the environment hazards)
# ---------------------------------------------------------------------------

def tick_epidemics(world: "WorldState", acc=None) -> list["Event"]:
    """Advance every outbreak one turn; return the turn's disease events.

    Order: absorb population change, introductions (spillover and contact
    imports), the within-region SEIRS recursion, deaths, reports (with the
    contact arrival that caused an onset), mutation, civ responses (outbreak,
    leader deaths), quarantine decisions for the next turn. Uses only
    namespaced hash draws.
    """
    from chronicler.models import Event

    state = world.epidemics
    if not isinstance(state, EpidemicState):
        return []
    if state.initialized_turn is None:
        _initialize(world, state)
    regions = world.regions
    n_regions = len(regions)
    events: list[Event] = []

    rows: dict[tuple[int, int], RegionInfection] = {}
    for row in state.rows:
        if row.region >= n_regions:
            continue
        _absorb_population(row, int(regions[row.region].population))
        rows[_row_key(row)] = row
    mods = [_modifiers(region) for region in regions]

    _introduce(world, state, rows, mods)

    # Within-region dynamics; expected deaths per row.
    expected: dict[tuple[int, int], float] = {}
    for key in sorted(rows):
        row = rows[key]
        if row.n <= 0:
            continue
        expected[key] = _step(row, PATHOGENS[row.pathogen], mods[row.region])

    deaths = _apply_deaths(world, state, rows, expected, acc)

    # Extinction of small outbreaks and compaction.
    kept: list[RegionInfection] = []
    for key in sorted(rows):
        row = rows[key]
        n_now = int(regions[row.region].population)
        row.n = n_now
        if n_now <= 0:
            continue
        if not _circulating(row):
            row.r += row.e + row.i
            row.e = row.i = 0.0
        _normalize(row)
        if row.e == 0.0 and row.i == 0.0 and row.r < IMMUNITY_FLOOR and row.cases == 0.0:
            continue
        kept.append(row)
    state.rows = kept

    report_events, reports = _reports(world, state)
    events.extend(report_events)
    events.extend(_mutate(world, state, reports))
    events.extend(_civ_responses(world, state, reports, deaths, acc))
    events.extend(_decide_quarantine(world, state, reports, acc))
    state.last_tick_turn = world.turn
    return events


def _absorb_population(row: RegionInfection, n_now: int) -> None:
    """Population change since the last tick: newcomers (births, immigrants)
    are susceptible; losses remove every compartment proportionally."""
    n_prev = row.n
    if n_now > n_prev:
        if n_prev <= 0:
            row.s, row.e, row.i, row.r = 1.0, 0.0, 0.0, 0.0
        else:
            f = n_prev / n_now
            row.s = row.s * f + (1.0 - f)
            row.e *= f
            row.i *= f
            row.r *= f
        _normalize(row)
    row.n = max(0, n_now)
    row.cases = 0.0


def _introduce(world, state: EpidemicState, rows: dict, mods: list) -> None:
    """Spillover in homelands and imports along contact-ledger flows."""
    from chronicler import contact_ledger as cl

    regions = world.regions
    n_regions = len(regions)
    homelands = set(state.homelands)
    quarantined = {world.civilizations[c].name for c in state.quarantine if c < len(world.civilizations)}
    ledger_on = cl.ledger_enabled(world)
    neighbors = world.contact_ledger.neighbors() if ledger_on else {}
    edge_map = world.contact_ledger.edge_map() if ledger_on else {}

    for k, pathogen in enumerate(PATHOGENS):
        # Exporters: last tick's infectious burden.
        exporters = sorted((row.region, row.burden) for (j, kk), row in rows.items()
                           if kk == k and row.burden > 0.0)
        pressure: dict[int, list[tuple[float, int]]] = {}
        for j, burden in exporters:
            src_ctrl = regions[j].controller
            for t in neighbors.get(j, ()):
                if t == j or t >= n_regions:
                    continue
                contact = cl.region_contact(world, j, t)
                if contact <= 0.0:
                    continue
                value = contact * burden
                dst_ctrl = regions[t].controller
                if dst_ctrl in quarantined and src_ctrl != dst_ctrl:
                    value *= 1.0 - QUARANTINE_EFFICACY
                pressure.setdefault(t, []).append((value, j))
        for t in range(n_regions):
            region = regions[t]
            n = int(region.population)
            if n < 1:
                continue
            row = rows.get((t, k))
            if row is not None and _circulating(row):
                continue
            s_share = row.s if row is not None else 1.0
            susc = mods[t][0]
            # Spillover from the reservoir.
            if (t, k) in homelands and pathogen.spillover > 0.0:
                endemic = min(ENDEMIC_SPILLOVER_CAP, max(
                    1.0, region.endemic_severity / max(1e-6, region.disease_baseline)))
                h = pathogen.spillover * susc * endemic
                if _draw("epidemic_spillover", world, k, t) < -math.expm1(-h):
                    if row is None:
                        row = rows[(t, k)] = _new_row(t, k, n)
                    _seed(row, INTRO_PEOPLE, cause="", virgin=_is_virgin(state, t, k))
                    continue
            # Imports along recorded contact.
            sources = pressure.get(t)
            if not sources:
                continue
            total = sum(v for v, _ in sources)
            h = IMPORT_SCALE * pathogen.r0 * susc * s_share * total
            if h <= 0.0 or _draw("epidemic_import", world, k, t) >= -math.expm1(-h):
                continue
            value, src = max(sources, key=lambda vs: (vs[0], -vs[1]))
            if row is None:
                row = rows[(t, k)] = _new_row(t, k, n)
            zero = (0.0, 0.0, 0.0, 0.0)
            ab, ba = edge_map.get((src, t), zero), edge_map.get((t, src), zero)
            weights = cl.CONTACT_WEIGHTS
            channel = max(range(4), key=lambda c: (weights[c] * (ab[c] + ba[c]), -c))
            _seed(row, INTRO_PEOPLE, cause="", virgin=_is_virgin(state, t, k),
                  source=src, channel=channel, turn=world.turn)


def _arrival_event(world, row: RegionInfection) -> "Event":
    """The contact edge that carried an outbreak, emitted with its onset report.

    It cites the source region's latest outbreak of the pathogen (the
    epidemic that was exporting it), or nothing for a quiet reservoir.
    """
    from chronicler import provenance
    from chronicler.models import Event

    pathogen = PATHOGENS[row.pathogen]
    source, target = world.regions[row.source], world.regions[row.region]
    actors = [c for c in dict.fromkeys((target.controller, source.controller)) if c]
    carriers = CHANNEL_CARRIERS[row.channel] if 0 <= row.channel < len(CHANNEL_CARRIERS) else "Travellers"
    text = f"{carriers} from {source.name} carry {pathogen.label} to {target.name}"
    if row.virgin:
        text += ", a land that has never known it"
    ev = Event(
        turn=world.turn, event_type="epidemic_arrival", actors=actors,
        description=text + ".", importance=pathogen.importance - 1 + (1 if row.virgin else 0),
        region=target.name, shock_category=pathogen.name,
    )
    provenance.cite(ev, provenance.recall(
        world, provenance.key("epidemic", source.name, pathogen.name)))
    return ev


def _effective_cfr(row: RegionInfection, pathogen: Pathogen, cfr_mult: float) -> float:
    """Case fatality of an outbreak: famine and virgin soil raise it."""
    return min(MAX_CFR, pathogen.cfr * cfr_mult * (VIRGIN_SOIL_CFR if row.virgin else 1.0))


def _step(row: RegionInfection, pathogen: Pathogen, mods: tuple[float, float, bool]) -> float:
    """SUBSTEPS seasons of the discrete SEIRS recursion. Returns the death share."""
    susc, cfr_mult, _ = mods
    beta = pathogen.r0 * pathogen.recovery * susc
    waning = 0.0 if pathogen.immunity_turns <= 0 else -math.expm1(-1.0 / (pathogen.immunity_turns * SUBSTEPS))
    cfr = _effective_cfr(row, pathogen, cfr_mult)
    s, e, i, r = row.s, row.e, row.i, row.r
    dead = cases = burden = 0.0
    for _ in range(SUBSTEPS):
        new_e = s * -math.expm1(-beta * i) if i > 0.0 else 0.0
        new_i = e * pathogen.onset
        leave = i * pathogen.recovery
        died = leave * cfr
        wane = r * waning
        s += wane - new_e
        e += new_e - new_i
        i += new_i - leave
        r += leave - died - wane
        dead += died
        cases += new_e
        burden += i
    row.s, row.e, row.i, row.r = s, e, i, r
    row.cases = round(cases * row.n, 6)
    row.burden = _q(burden / SUBSTEPS)
    return dead


def _apply_deaths(world, state: EpidemicState, rows: dict, expected: dict, acc) -> dict[int, int]:
    """Integer deaths per region through the plague death path. Returns region -> deaths."""
    from chronicler.utils import drain_region_pop, stage_region_catastrophe_deaths, sync_civ_population

    regions = world.regions
    by_region: dict[int, list[tuple[int, int]]] = {}
    for (j, k), share in sorted(expected.items()):
        by_region.setdefault(j, []).append((k, share))
    deaths: dict[int, int] = {}
    last: list[tuple[int, int, int]] = []
    tracks = _agent_pool_tracks_population(world)
    touched_civs: list[str] = []
    pops_before: dict[str, int] = {}
    for civ in world.civilizations:
        pops_before[civ.name] = sum(r.population for r in regions if r.controller == civ.name)
    for j in sorted(by_region):
        region = regions[j]
        n = int(region.population)
        if n <= 0:
            continue
        items = by_region[j]
        total = sum(share for _, share in items)
        scale = min(1.0, MAX_TURN_MORTALITY / total) if total > 0.0 else 1.0
        region_deaths = 0
        for k, share in items:
            row = rows[(j, k)]
            spared = share * (1.0 - scale)
            if spared > 0.0:
                row.r += spared  # deaths above the bound recover instead
            x = share * scale * n
            whole = int(x)
            if _draw("epidemic_deaths", world, k, j) < x - whole:
                whole += 1
            whole = min(whole, n - region_deaths)
            if whole > 0:
                region_deaths += whole
                last.append((j, k, whole))
        if region_deaths <= 0:
            continue
        actual = drain_region_pop(region, region_deaths)
        if tracks:
            stage_region_catastrophe_deaths(region, actual)
        deaths[j] = actual
        if region.controller and region.controller not in touched_civs:
            touched_civs.append(region.controller)
    civ_map = {c.name: (idx, c) for idx, c in enumerate(world.civilizations)}
    lost: dict[int, int] = {}
    for j, d in deaths.items():
        ctrl = regions[j].controller
        if ctrl in civ_map:
            idx = civ_map[ctrl][0]
            lost[idx] = lost.get(idx, 0) + d
    for name in touched_civs:
        sync_civ_population(civ_map[name][1], world)
    # Labour scarcity: decay, then add this turn's losses.
    scarcity: dict[int, float] = {}
    for idx, value in state.scarcity:
        decayed = round(value * LABOUR_DECAY, 6)
        if decayed >= LABOUR_FLOOR:
            scarcity[idx] = decayed
    for idx, d in sorted(lost.items()):
        before = max(1, pops_before.get(world.civilizations[idx].name, 0))
        scarcity[idx] = round(scarcity.get(idx, 0.0) + d / before, 6)
    state.scarcity = sorted(scarcity.items())
    state.last_deaths = sorted(last)
    state.deaths_total += sum(deaths.values())
    return deaths


def _mutate(world, state: EpidemicState, reports: dict) -> list["Event"]:
    """A circulating pathogen may produce a strain that escapes part of the immunity."""
    from chronicler import provenance
    from chronicler.models import Event

    events: list[Event] = []
    for k, pathogen in enumerate(PATHOGENS):
        if pathogen.mutation <= 0.0:
            continue
        active = [row for row in state.rows if (row.region, row.pathogen) in reports and row.pathogen == k]
        if not active or _draw("epidemic_mutation", world, k) >= pathogen.mutation:
            continue
        state.strains[k] += 1
        for row in state.rows:
            if row.pathogen == k and row.r > 0.0:
                moved = row.r * pathogen.escape
                row.r -= moved
                row.s += moved
                _normalize(row)
        where = max(active, key=lambda row: (row.cases, -row.region))
        region = world.regions[where.region]
        ev = Event(
            turn=world.turn, event_type="pathogen_mutation",
            actors=[region.controller] if region.controller else [],
            description=(f"A new strain of {pathogen.label} (strain {state.strains[k]}) emerges in "
                         f"{region.name}; old immunity no longer protects against it."),
            importance=4, region=region.name, shock_category=pathogen.name,
        )
        provenance.cite(ev, _report_cause(world, reports[_row_key(where)]))
        events.append(ev)
    return events


def _reports(world, state: EpidemicState) -> tuple[list["Event"], dict[tuple[int, int], "Event"]]:
    """One ``epidemic`` report per reportable outbreak (a chronic episode).

    Returns the events in emission order (each contact arrival right before
    the onset it causes) and the reports by (region, pathogen).
    """
    from chronicler import provenance
    from chronicler.models import Event

    events: list[Event] = []
    out: dict[tuple[int, int], Event] = {}
    for row in state.rows:
        region = world.regions[row.region]
        pathogen = PATHOGENS[row.pathogen]
        if not _reportable(row):
            if row.reported:
                # The outbreak subsided: the population now knows the pathogen,
                # and a later flare-up of it is a return, not an arrival.
                row.reported = row.virgin = False
                row.source = row.channel = row.arrival_turn = -1
                row.cause = provenance.recall(
                    world, provenance.key("epidemic", region.name, pathogen.name)) or ""
            continue
        onset = provenance.open_episode(world, "epidemic", region.name, pathogen.name) is None
        row.reported = True
        _mark_seen(state, row.region, row.pathogen)
        if onset and row.source >= 0 and row.source < len(world.regions):
            arrival = _arrival_event(world, row)
            row.cause = provenance.ensure_id(world, arrival) or ""
            row.source = row.channel = row.arrival_turn = -1
            events.append(arrival)
        label = pathogen.label[0].upper() + pathogen.label[1:]
        if row.virgin:
            text = f"{label} sweeps through {region.name}, whose people have never known it."
        else:
            text = f"{label} breaks out in {region.name}."
        ev = Event(
            turn=world.turn, event_type="epidemic",
            actors=[region.controller] if region.controller else [],
            description=text, importance=pathogen.importance + (1 if row.virgin else 0),
            region=region.name, shock_category=pathogen.name,
        )
        causes = [row.cause] if row.cause else []
        if region.famine_cooldown > 0:
            causes.append(provenance.open_episode(world, "famine", region.name))
        provenance.cite(ev, *causes)
        if onset:
            provenance.ensure_id(world, ev)  # ids follow emission order; repeats get none
        out[_row_key(row)] = ev
        events.append(ev)
    return events, out


def _report_cause(world, report: "Event") -> str | None:
    """Id to cite for a regional report: the open episode's onset when the
    report will fold into it (a repeat gets no id), else the report itself."""
    from chronicler import provenance

    onset = provenance.open_episode(world, "epidemic", report.region, report.shock_category)
    return onset or provenance.ensure_id(world, report)


def _civ_responses(world, state: EpidemicState, reports: dict, deaths: dict, acc) -> list["Event"]:
    """Civ outbreaks (the ``plague`` event and condition) and leader deaths."""
    from chronicler import provenance
    from chronicler.emergence import get_severity_multiplier
    from chronicler.events import record_hazard_event
    from chronicler.models import ActiveCondition, Event
    from chronicler.tuning import K_PLAGUE_STABILITY, get_override
    from chronicler.utils import STAT_FLOOR, clamp

    events: list[Event] = []
    regions = world.regions
    index = {r.name: j for j, r in enumerate(regions)}
    rows = {_row_key(r): r for r in state.rows}
    by_civ: dict[str, list[tuple[int, int]]] = {}
    for key in sorted(reports):
        ctrl = regions[key[0]].controller
        row = rows[key]
        cfr = _effective_cfr(row, PATHOGENS[row.pathogen], _modifiers(regions[row.region])[1])
        if ctrl and cfr >= MAJOR_CFR:
            by_civ.setdefault(ctrl, []).append(key)
    for civ_idx, civ in enumerate(world.civilizations):
        if not civ.regions:
            continue
        keys = by_civ.get(civ.name)
        if keys:
            cond = next((c for c in world.active_conditions
                         if c.condition_type == "plague" and civ.name in c.affected_civs), None)
            if cond is not None:
                cond.duration = max(cond.duration, 2)
            else:
                lead = max(keys, key=lambda kk: (rows[kk].cases, -kk[0], -kk[1]))
                pathogen = PATHOGENS[lead[1]]
                virgin = any(rows[kk].virgin for kk in keys)
                ev = Event(
                    turn=world.turn, event_type="plague", actors=[civ.name],
                    description=(f"{pathogen.label[0].upper() + pathogen.label[1:]} spreads through "
                                 f"{civ.name}, from {regions[lead[0]].name}."),
                    importance=pathogen.importance + (1 if virgin else 0),
                    region=regions[lead[0]].name,
                )
                provenance.cite(ev, _report_cause(world, reports[lead]))
                mult = get_severity_multiplier(civ, world)
                drain = int(get_override(world, K_PLAGUE_STABILITY, 3) * mult)
                if acc is not None:
                    acc.add(civ_idx, civ, "stability", -drain, "signal")
                else:
                    civ.stability = clamp(civ.stability - drain, STAT_FLOOR["stability"], 100)
                world.active_conditions.append(ActiveCondition(
                    condition_type="plague", affected_civs=[civ.name], duration=2, severity=60,
                ))
                record_hazard_event(world, ev)
                events.append(ev)
        cap = index.get(civ.capital_region) if civ.capital_region else None
        if cap is not None and deaths.get(cap):
            leader_ev = _leader_death(world, civ, civ_idx, cap, deaths[cap], reports, acc)
            if leader_ev is not None:
                events.append(leader_ev)
    return events


def _leader_death(world, civ, civ_idx: int, cap: int, cap_deaths: int, reports: dict, acc):
    from chronicler import provenance
    from chronicler.events import leader_age, record_hazard_event
    from chronicler.models import Event
    from chronicler.succession import is_in_crisis

    if not civ.leader.alive or is_in_crisis(civ):
        return None
    region = world.regions[cap]
    share = cap_deaths / max(1, region.population + cap_deaths)
    p = min(LEADER_MAX_P, LEADER_EXPOSURE * share)
    if p <= 0.0 or _draw("epidemic_leader", world, civ_idx) >= p:
        return None
    from chronicler.simulation import _apply_event_effects

    # The pathogen that killed most people in the capital this turn.
    tolls = [(d, -k, k) for j, k, d in world.epidemics.last_deaths if j == cap]
    killer = (cap, max(tolls)[2]) if tolls else None
    label = PATHOGENS[killer[1]].label if killer else "the sickness"
    old = civ.leader
    age = leader_age(old, world)
    mark = len(world.events_timeline)
    _apply_event_effects("leader_death", civ, world, acc=acc, cause="disease")
    ev = Event(
        turn=world.turn, event_type="leader_death", actors=[civ.name],
        description=f"{old.name} of {civ.name} dies of {label} at the age of {age}.",
        importance=6, region=region.name,
    )
    if killer is not None and killer in reports:
        provenance.cite(ev, _report_cause(world, reports[killer]))
    for other in world.events_timeline[mark:]:
        if other.event_type == "succession_crisis" and other.actors[:1] == [civ.name]:
            provenance.cite(other, provenance.ensure_id(world, ev))
    record_hazard_event(world, ev)
    return ev


def _decide_quarantine(world, state: EpidemicState, reports: dict, acc) -> list["Event"]:
    """States in contact with a foreign epidemic close their borders for next turn."""
    from chronicler import contact_ledger as cl
    from chronicler import provenance
    from chronicler.models import Event
    from chronicler.utils import civ_index

    events: list[Event] = []
    regions = world.regions
    if not cl.ledger_enabled(world):
        state.quarantine = []
        return events
    sick = sorted(reports)
    neighbors = world.contact_ledger.neighbors()
    closed: list[int] = []
    for idx, civ in enumerate(world.civilizations):
        if not civ.regions:
            continue
        own = {j for j, r in enumerate(regions) if r.controller == civ.name}
        threat = None
        for key in sick:
            j = key[0]
            if regions[j].controller == civ.name:
                continue
            if any(t in own for t in neighbors.get(j, ())):
                threat = key
                break
        if threat is None:
            continue
        if civ.stability < QUARANTINE_MIN_STABILITY or civ.treasury < QUARANTINE_COST:
            continue
        closed.append(idx)
        if acc is not None:
            acc.add(civ_index(world, civ.name), civ, "treasury", -QUARANTINE_COST, "keep")
        else:
            civ.treasury -= QUARANTINE_COST
        seat = civ.capital_region if civ.capital_region in civ.regions else civ.regions[0]
        ev = Event(
            turn=world.turn, event_type="quarantine", actors=[civ.name],
            description=(f"{civ.name} closes its borders against {PATHOGENS[threat[1]].label} "
                         f"raging in {regions[threat[0]].name}."),
            importance=4, region=seat,
        )
        provenance.cite(ev, _report_cause(world, reports[threat]))
        events.append(ev)
    state.quarantine = closed
    return events


# ---------------------------------------------------------------------------
# Viewer / analytics summaries
# ---------------------------------------------------------------------------

def snapshot_summary(world) -> dict:
    """Small per-turn summary for ``TurnSnapshot.epidemics``."""
    state = world.epidemics
    regions = world.regions
    active = [
        {
            "region": regions[row.region].name,
            "pathogen": PATHOGENS[row.pathogen].name,
            "prevalence": round(row.burden, 4),
            "immune": round(row.r, 4),
            "cases": round(row.cases, 2),
            "virgin": row.virgin,
        }
        for row in state.rows if row.region < len(regions) and _reportable(row)
    ]
    deaths = sum(d for _, _, d in state.last_deaths)
    return {
        "active": active,
        "deaths": deaths,
        "deaths_by_pathogen": {
            PATHOGENS[k].name: sum(d for _, kk, d in state.last_deaths if kk == k)
            for k in sorted({k for _, k, _ in state.last_deaths})
        },
        "deaths_total": state.deaths_total,
        "quarantine": [world.civilizations[c].name for c in state.quarantine
                       if c < len(world.civilizations)],
        "strains": {p.name: state.strains[k] for k, p in enumerate(PATHOGENS)
                    if k < len(state.strains) and state.strains[k]},
    }


def extract_epidemic_metrics(bundles: list[dict]) -> dict:
    """Analytics section from ``history[n].epidemics`` (empty when no bundle has it)."""
    runs = []
    for bundle in bundles:
        series = [h.get("epidemics") for h in bundle.get("history", []) if h.get("epidemics") is not None]
        if not series:
            continue
        onsets = 0
        regions: set[str] = set()
        open_: set[tuple[str, str]] = set()
        peak = 0.0
        by_pathogen: dict[str, int] = {}
        for snap in series:
            now = {(a["region"], a["pathogen"]) for a in snap["active"]}
            onsets += len(now - open_)
            open_ = now
            for a in snap["active"]:
                regions.add(a["region"])
                peak = max(peak, a["prevalence"])
            for name, d in snap.get("deaths_by_pathogen", {}).items():
                by_pathogen[name] = by_pathogen.get(name, 0) + d
        runs.append({
            "seed": bundle.get("metadata", {}).get("seed"),
            "turns": len(series),
            "epidemics": onsets,
            "deaths": sum(s["deaths"] for s in series),
            "deaths_by_pathogen": dict(sorted(by_pathogen.items())),
            "peak_prevalence": round(peak, 4),
            "regions_affected": len(regions),
            "quarantine_turns": sum(len(s["quarantine"]) for s in series),
        })
    if not runs:
        return {}
    n = len(runs)
    return {
        "runs": n,
        "mean_epidemics": sum(r["epidemics"] for r in runs) / n,
        "mean_deaths": sum(r["deaths"] for r in runs) / n,
        "mean_peak_prevalence": sum(r["peak_prevalence"] for r in runs) / n,
        "mean_regions_affected": sum(r["regions_affected"] for r in runs) / n,
        "by_seed": runs,
    }
