"""Seats of learning (``--scholarship``, default off).

Off by default behind ``WorldState.scholarship`` (CLI ``--scholarship`` /
``--no-scholarship``, persisted on the world so a resumed run keeps its
setting). With the switch off nothing in this module runs, the bridge sends
no ``seat_pull`` or ``seat_flight`` column, and every output is identical
to the simulation without it. See ``docs/integration/scholarship.md``.

Seats
    A seat of learning is one per region, with a level (modest, renowned,
    great), an upkeep and a patron: an **academy** founded by a ruler at its
    capital and kept from the treasury; a **temple school** founded at a
    prestigious temple and kept by its offerings (temple prestige); a
    **library** founded by a city of rank 2 or more and kept from its civic
    purse. A seat rises a level when its scholars are many enough and its
    patron pays the fee; unpaid upkeep costs it a level.

Scholars
    The agents of the scholar occupation in its region (with ``--agents
    off``, a share of the region's people), the great scholars (great-person
    scientists) of its ruler who teach there, and refugees from fallen seats.
    The Rust learning driver (``migration_drivers.rs``) draws scholar agents
    of the realm toward a seat by ``seat_pull``; after a fall, ``seat_flight``
    lets the scholars of that region cross a border to a seat next door.

What learning does
    Invention research of the seats' ruler (:func:`research_factor`);
    adoption and keeping of techniques in and next to a seat
    (:func:`learning_factors`); copies of the archives kept in its region and
    realm (:func:`archive_copies`, read by historiography).

What destroys it
    A sack (an enemy occupying or taking the region, a city sacked there), a
    famine, persecution of the scholars' faith, or the loss of patronage
    (unpaid upkeep, the temple or the city gone, no ruler). A fallen seat's
    scholars flee to the nearest seat of a rival (or any seat in reach),
    carrying techniques its region practised that the refuge can take up
    (:func:`apply_carries`, in the next technique tick); part of the practice
    of the higher techniques is lost where it fell.

Identity: region = index in ``world.regions``, civ = index in
``world.civilizations``, seat = index in ``ScholarshipState.seats``, a
library's city = ``settlement_id``. Randomness: ``random.Random(
stable_hash_int("scholarship", <namespace>, seed, turn, ...))``. Stat changes
use the existing accumulator categories (treasury ``keep``).
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING, Iterable

from chronicler.scholarship_state import (
    ACADEMY, COUNTER_KEYS, FALL_CAUSES, FAMINE, KIND_NAMES, LEVEL_NAMES, LIBRARY, PATRONAGE,
    PERSECUTION, SACK, TEMPLE_SCHOOL, ScholarshipState, Seat, scholarship_on,
)
from chronicler.utils import stable_hash_int

if TYPE_CHECKING:  # pragma: no cover
    from chronicler.models import Event, WorldState


# ---------------------------------------------------------------------------
# Parameters ([CALIBRATE]; documented in docs/integration/scholarship.md)
# ---------------------------------------------------------------------------

#: Default for worlds created by the CLI/batch/live entry points
#: (``--scholarship`` opts in; loaded worlds keep their saved setting).
DEFAULT_ENABLED_FOR_NEW_WORLDS = False

# Founding.
ACADEMY_TREASURY = 60         # a ruler with this in the treasury ...
ACADEMY_CULTURE = 30          # ... this culture ...
ACADEMY_STABILITY = 30        # ... and stability may found an academy at its capital
ACADEMY_FEE = 30              # treasury (keep)
ACADEMY_CHANCE = 0.03         # per turn
LEARNED_FACTOR = 2.0          # x the chance under the scholarship focus or a learned value
LEARNED_VALUES = frozenset({"Knowledge"})
SCHOOL_PRESTIGE = 20          # temple prestige from which a temple founds a school ...
SCHOOL_COST = 10              # ... paying this much of it
SCHOOL_CHANCE = 0.02
LIBRARY_RANK = 2              # a city of this rank (cities_state.CITY) ...
LIBRARY_FEE = 20.0            # ... with this in its purse founds a library
LIBRARY_CHANCE = 0.05

# Upkeep (by level; treasury, temple prestige or civic purse), the fraction carried.
UPKEEP = (0.0, 0.3, 0.6, 1.0)
NEGLECT_PAYMENTS = 4          # failed payments in a row before the seat loses a level

# Growth.
RISE_INTERVAL = 20            # turns between changes of level
RISE_SCHOLARS = (0.0, 0.0, 5.0, 10.0)  # scholar body (reference scale) a level needs
RISE_FEE = (0.0, 0.0, 20.0, 40.0)      # paid by the patron for the rise
MASTER_SCHOLARS = 2.0         # body of a great scholar teaching there
REFUGEE_DECAY = 0.05          # share of the refugees who settle or leave per turn
OFF_SCHOLAR_SHARE = 0.10      # --agents off: scholars as a share of the region's people

# Strikes and falls.
STRIKE_COOLDOWN = 10          # turns between strikes on one seat
SACK_FALL = 0.5               # a sack destroys the seat with this chance (else a level)
FAMINE_STRIKE = 0.3           # a famine report in its region costs a level with this chance
PERSECUTION_TURNS = 5         # turns of persecution of its faith that close the seat

# Flight and carried knowledge.
FLIGHT_RANGE = 4              # region hops within which fleeing scholars find a seat
FLIGHT_SHARE = 0.5            # share of the fallen seat's body that reaches it
FLIGHT_TURNS = 10             # turns the region of a fallen seat sends scholars away
CARRY_MIN = 0.25              # practice at the fallen seat of a technique they carry ...
CARRY_LEVEL = 0.20            # ... started at this in the refuge's region
CARRY_MAX = 3                 # techniques carried (highest tier first)
FALL_LOSS = 0.3               # share of the practice of tier >= FALL_LOSS_TIER lost where it fell
FALL_LOSS_TIER = 2

# Effects.
RESEARCH_PER_LEVEL = 0.15     # invention research x(1 + this x levels of the ruler's seats) ...
RESEARCH_LEVELS = 4           # ... counted up to this many levels
LEARN_HAZARD = 0.4            # adoption hazard x(1 + this x level) in the seat's region ...
LEARN_NEAR = 0.15             # ... x(1 + this x level) next to it
LEARN_KEEP = 0.15             # forgetting x(1 - this x level) in the seat's region
SEAT_COPIES_CAP = 3           # archive copies seats add (historiography)

# Migration (seat_pull, the Rust learning driver).
LEVEL_PULL = (0.0, 0.4, 0.7, 1.0)
UNPAID_PULL = 0.5             # x while the patron fails to pay

QUANTUM_DIGITS = 4
HISTORY_CAP = 60
TEACHERS_CAP = 20             # names of great scholars who taught at a seat, kept
SCHOLAR_OCCUPATION = 3        # agent occupation code (agent.rs Occupation::Scholar)


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

def scholarship_enabled(world) -> bool:
    """True only for a real scholarship state (mocks and ``None`` read as off)."""
    return scholarship_on(world)


def set_scholarship_enabled(world: "WorldState", enabled: bool) -> None:
    """Enable (an empty state; seats are founded as patrons can pay) or
    disable (dropping every seat)."""
    if enabled:
        if world.scholarship is None:
            world.scholarship = ScholarshipState()
        return
    world.scholarship = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _q(x: float) -> float:
    return round(x, QUANTUM_DIGITS)


def _rng(world, namespace: str, *parts) -> random.Random:
    return random.Random(stable_hash_int("scholarship", namespace, world.seed, world.turn, *parts))


def _bump(state: ScholarshipState, key: str, n: float = 1) -> None:
    state.counters[key] = round(state.counters.get(key, 0) + n, 4)


def _note(seat: Seat, turn: int, kind: str, event_id: str = "") -> None:
    seat.history.append((turn, kind, event_id))
    if len(seat.history) > HISTORY_CAP:
        del seat.history[1]   # keep the founding


def living_seats(world) -> list[tuple[int, Seat]]:
    if not scholarship_on(world):
        return []
    return [(i, s) for i, s in enumerate(world.scholarship.seats) if s.fallen_turn is None]


def seat_label(seat: Seat) -> str:
    """"the renowned academy" (its level and kind)."""
    return f"{LEVEL_NAMES[seat.level]} {KIND_NAMES[seat.kind]}"


def _cap(name: str) -> str:
    return name[:1].upper() + name[1:]


def _occupied(region) -> bool:
    return region.occupied_by is not None and region.occupied_by != region.controller


def _temple(region, faith: int):
    from chronicler.models import InfrastructureType
    for infra in region.infrastructure:
        if infra.type == InfrastructureType.TEMPLES and infra.active and infra.faith_id == faith:
            return infra
    return None


def _any_temple(region):
    from chronicler.models import InfrastructureType
    for infra in region.infrastructure:
        if infra.type == InfrastructureType.TEMPLES and infra.active:
            return infra
    return None


def _persecuted(region, faith: int) -> bool:
    """The region's ruler persecutes ``faith`` (everyone outside the ruler's own)."""
    enforced = region.persecuting_faith
    return (region.persecution_intensity > 0.0 and enforced is not None
            and faith != 0xFF and faith != enforced)


def _faith_name(world, faith: int) -> str | None:
    """The faith's name ("the Faith of Thornwall" for "Faith of Thornwall
    Confederacy", as the chroniclers write it), or None."""
    for b in world.belief_registry:
        if b.faith_id == faith:
            name = b.name
            if name.startswith("Faith of "):
                words = name[len("Faith of "):].split()
                if len(words) >= 2 and words[-1].lower() in _POLITY_WORDS:
                    words = words[:-1]
                return "the Faith of " + " ".join(words)
            return name
    return None


#: Trailing polity words dropped from a faith's founder name (as
#: ``historiography.short_name`` does; that layer is not imported here).
_POLITY_WORDS = frozenset({
    "empire", "confederacy", "republic", "nomads", "kingdom", "dominion", "federation",
    "league", "sultanate", "khanate", "union", "commonwealth", "theocracy", "clans",
    "tribes", "realm", "principality", "duchy", "horde", "assembly", "state", "states",
    "hegemony", "compact", "covenant", "collective", "directorate", "protectorate",
    "caliphate", "shogunate", "tribe", "marches", "march", "throne",
})


# ---------------------------------------------------------------------------
# The tick (Phase 10, after guilds)
# ---------------------------------------------------------------------------

class _Tick:
    def __init__(self, world, acc, phase10, events) -> None:
        from chronicler.cities import scale
        self.world = world
        self.acc = acc
        self.state: ScholarshipState = world.scholarship
        self.events: list = []
        self.turn_events = list(events)
        self.index = {c.name: i for i, c in enumerate(world.civilizations)}
        self.k = scale(world)
        cities = getattr(world, "cities", None)
        self.cities = {c.settlement_id: c for c in cities.cities} if cities is not None else {}
        self.scholars = _observe(phase10, len(world.regions))

    def civ(self, idx: int):
        civs = self.world.civilizations
        return civs[idx] if 0 <= idx < len(civs) else None

    def lord_of(self, region) -> int:
        return self.index.get(region.controller, -1) if region.controller else -1


def _observe(phase10, n: int) -> list[int] | None:
    """Scholar agents per region index from the Phase 10 agent rows (None
    without rows: ``--agents off``)."""
    rows = getattr(phase10, "agents", None) if phase10 is not None else None
    if rows is None:
        return None
    import numpy as np
    arrays = rows.arrays("region", "occupation")
    if arrays is None:
        if not (rows.has("region") and rows.has("occupation")):
            return None
        reg_l, occ_l = rows.ints("region"), rows.ints("occupation")
        if any(v is None for col in (reg_l, occ_l) for v in col):
            return None
        arrays = (np.asarray(reg_l, dtype=np.int64), np.asarray(occ_l, dtype=np.int64))
    region, occ = arrays
    region = region.astype(np.int64)
    picked = region[occ == SCHOLAR_OCCUPATION]
    counts = np.bincount(picked, minlength=n) if picked.size else np.zeros(n, dtype=np.int64)
    return [int(c) for c in counts[:n]]


def _emit(t: _Tick, event_type: str, actors: Iterable[str], description: str, *,
          importance: int = 4, region: str | None = None,
          causes: Iterable[str | None] = ()) -> "Event":
    from chronicler import provenance
    from chronicler.models import Event
    ev = Event(turn=t.world.turn, event_type=event_type,
               actors=[a for a in actors if a], description=description,
               importance=importance, region=region)
    provenance.cite(ev, *causes)
    provenance.observe_now(t.world, ev)
    t.events.append(ev)
    return ev


def tick_scholarship(world: "WorldState", events: Iterable["Event"] = (), acc=None, *,
                     phase10=None, agent_bridge=None) -> list["Event"]:
    """Phase 10, after cities and guilds: per living seat its ruler and
    patron, strikes (sack, famine, persecution), upkeep, scholars and
    masters, rise, pull; then foundings. Returns the turn's seat events."""
    if not scholarship_on(world):
        return []
    t = _Tick(world, acc, phase10, events)
    for si, seat in living_seats(world):
        _update(t, si, seat)
    _found_academies(t)
    _found_schools(t)
    _found_libraries(t)
    t.state.last_tick_turn = world.turn
    return t.events


def _update(t: _Tick, si: int, seat: Seat) -> None:
    world = t.world
    region = world.regions[seat.region]
    lord = t.lord_of(region)
    if lord != seat.lord:
        old = seat.lord
        seat.lord = lord
        if _strike_sack(t, si, seat, region, old, lord):
            return
        if seat.kind == ACADEMY:
            _patron_change(t, seat, region, old, lord)
    elif _occupied(region) and _newly_occupied(t, region):
        if _strike_sack(t, si, seat, region, lord, t.index.get(region.occupied_by, -1)):
            return
    elif _city_sacked(t, seat):
        if _strike_sack(t, si, seat, region, lord, -1):
            return
    if _patron_gone(t, si, seat, region):
        return
    if _famine(t, si, seat, region):
        return
    if _persecution(t, si, seat, region):
        return
    if not _upkeep(t, si, seat, region):
        return
    _scholars(t, seat, region)
    _rise(t, seat, region)
    seat.pull = 0.0 if _occupied(region) else _q(
        LEVEL_PULL[seat.level] * (UNPAID_PULL if seat.unpaid else 1.0))


# --- strikes ----------------------------------------------------------------

def _newly_occupied(t: _Tick, region) -> bool:
    from chronicler import provenance as prov
    return prov.recall(t.world, prov.key("occupation", region.name), within=0) is not None


def _city_sacked(t: _Tick, seat: Seat) -> bool:
    return any(c.region == seat.region and c.last_sack == t.world.turn for c in t.cities.values())


def _sack_cause(t: _Tick, region) -> str | None:
    from chronicler import provenance as prov
    w = t.world
    for city in t.cities.values():
        if city.region < len(w.regions) and w.regions[city.region] is region and city.last_sack == w.turn:
            sack = prov.recall(w, prov.key("city_sack", str(city.settlement_id)), within=0)
            if sack:
                return sack
    return (prov.recall(w, prov.key("conquest", region.name), within=1)
            or prov.recall(w, prov.key("occupation", region.name), within=1))


def _strike_sack(t: _Tick, si: int, seat: Seat, region, victim: int, taker: int) -> bool:
    """A sack: the region taken or occupied by an enemy at war (or a city of it
    sacked). Returns True when the seat fell."""
    from chronicler.cities import _at_war
    world = t.world
    cause = _sack_cause(t, region)
    taker_civ, victim_civ = t.civ(taker), t.civ(victim)
    hostile = cause is not None or (
        taker_civ is not None and victim_civ is not None
        and _at_war(world, taker_civ.name, victim_civ.name))
    if not hostile or world.turn - seat.last_strike < STRIKE_COOLDOWN:
        return False
    seat.last_strike = world.turn
    _bump(t.state, "strikes")
    who = taker_civ.name if taker_civ is not None else "raiders"
    if seat.level <= 1 or _rng(world, "sack", si).random() < SACK_FALL:
        _fall(t, si, seat, region, SACK, f"is burned when {who} take {region.name}",
              [cause], actors=[who if taker_civ is not None else "", victim_civ.name if victim_civ else ""])
        return True
    _decline(t, seat, region, f"loses its books and half its masters when {who} take {region.name}",
             [cause], "struck")
    return False


def _famine(t: _Tick, si: int, seat: Seat, region) -> bool:
    # A famine report of this turn in the seat's region (a dearth that
    # deepens into famine reports as a famine tick of its episode).
    onset = next((ev for ev in t.turn_events
                  if ev.event_type == "famine" and ev.region == region.name
                  and ev.episode != "end" and ev.turn == t.world.turn), None)
    if onset is None or t.world.turn - seat.last_strike < STRIKE_COOLDOWN:
        return False
    if _rng(t.world, "famine", si).random() >= FAMINE_STRIKE:
        return False
    seat.last_strike = t.world.turn
    _bump(t.state, "strikes")
    if seat.level <= 1:
        _fall(t, si, seat, region, FAMINE, f"closes as famine empties {region.name}",
              [onset.event_id])
        return True
    _decline(t, seat, region, f"loses its students to the famine in {region.name}",
             [onset.event_id], "struck")
    return False


def _persecution(t: _Tick, si: int, seat: Seat, region) -> bool:
    if not _persecuted(region, seat.faith):
        seat.persecuted = 0
        return False
    seat.persecuted += 1
    if seat.persecuted < PERSECUTION_TURNS:
        return False
    from chronicler import provenance as prov
    cause = prov.recall(t.world, prov.key("persecution", region.name))
    faith = _faith_name(t.world, seat.faith) or "their faith"
    _fall(t, si, seat, region, PERSECUTION,
          f"is closed: its scholars of {faith} are persecuted in {region.name}", [cause])
    return True


def _patron_gone(t: _Tick, si: int, seat: Seat, region) -> bool:
    """A temple school without its temple (burned by a conqueror: a sack;
    replaced by another faith's: loss of patronage), a library without its city."""
    if seat.kind == TEMPLE_SCHOOL and _temple(region, seat.faith) is None:
        razed = next((ev for ev in t.turn_events if ev.event_type == "temple_destroyed"
                      and ev.turn == t.world.turn
                      and (ev.description or "").startswith(f"Temple of faith {seat.faith} ")
                      and (ev.description or "").endswith(f" in {region.name}")), None)
        if razed is not None and " destroyed in " in razed.description:
            who = razed.actors[0] if razed.actors else "raiders"
            _fall(t, si, seat, region, SACK, f"is burned with its temple when {who} take {region.name}",
                  [razed.event_id], actors=[who, region.controller or ""])
        elif razed is not None:
            _fall(t, si, seat, region, PATRONAGE,
                  f"closes: its temple in {region.name} is given to another faith", [razed.event_id])
        else:
            _fall(t, si, seat, region, PATRONAGE, f"closes: the temple that kept it in {region.name} is gone",
                  [])
        return True
    if seat.kind == LIBRARY and seat.city not in t.cities:
        cities = getattr(t.world, "cities", None)
        fallen = next((c for c in (cities.fallen if cities is not None else [])
                       if c.settlement_id == seat.city), None)
        fell = next((eid for _turn, kind, eid in fallen.history if kind == "fell"), None) if fallen else None
        _fall(t, si, seat, region, PATRONAGE, "closes: the city that kept it has fallen", [fell])
        return True
    return False


def _patron_change(t: _Tick, seat: Seat, region, old: int, new: int) -> None:
    new_civ = t.civ(new)
    if new_civ is None:
        return
    _bump(t.state, "patron_changes")
    ev = _emit(t, "seat_patron", [new_civ.name],
               f"{new_civ.name} takes {seat.name} in {region.name} under its patronage",
               importance=3, region=region.name)
    _note(seat, t.world.turn, "patron", ev.event_id)


# --- upkeep -----------------------------------------------------------------

def _patron_funds(t: _Tick, seat: Seat, region) -> float:
    """What the patron could pay now: the ruler's treasury (with this turn's
    queued changes), the temple's prestige, the city's purse."""
    if seat.kind == ACADEMY:
        civ = t.civ(seat.lord)
        if civ is None or not civ.regions:
            return 0.0
        from chronicler.war.common import projected_treasury
        return float(projected_treasury(t, civ))
    if seat.kind == TEMPLE_SCHOOL:
        temple = _temple(region, seat.faith)
        return float(temple.temple_prestige) if temple is not None else 0.0
    city = t.cities.get(seat.city)
    return float(city.wealth) if city is not None else 0.0


def _charge(t: _Tick, seat: Seat, region, amount: float) -> None:
    """Pay ``amount`` (an integer for treasury and prestige) from the patron."""
    if amount <= 0:
        return
    if seat.kind == ACADEMY:
        from chronicler.war.common import add_stat
        add_stat(t, t.civ(seat.lord), "treasury", -int(amount), "keep")
    elif seat.kind == TEMPLE_SCHOOL:
        temple = _temple(region, seat.faith)
        temple.temple_prestige -= int(amount)
    else:
        city = t.cities[seat.city]
        city.wealth = round(city.wealth - amount, 4)


def _upkeep(t: _Tick, si: int, seat: Seat, region) -> bool:
    """The turn's upkeep, the whole units owed paid by the patron. Returns
    False when the seat fell of neglect."""
    seat.owed = _q(seat.owed + UPKEEP[seat.level])
    due = int(seat.owed)
    if due <= 0:
        return True
    if _patron_funds(t, seat, region) >= due:
        _charge(t, seat, region, due)
        seat.owed = _q(seat.owed - due)
        seat.unpaid = 0
        _bump(t.state, "upkeep", due)
        return True
    seat.unpaid += 1
    _bump(t.state, "unpaid")
    if seat.unpaid < NEGLECT_PAYMENTS:
        return True
    seat.unpaid = 0
    seat.owed = 0.0
    who = {ACADEMY: "its ruler", TEMPLE_SCHOOL: "its temple", LIBRARY: "its city"}[seat.kind]
    if seat.level <= 1:
        _fall(t, si, seat, region, PATRONAGE, f"closes: {who} no longer pays its masters", [])
        return False
    _decline(t, seat, region, f"falls into neglect: {who} no longer pays its masters", [], "unpaid")
    return True


# --- scholars and rise --------------------------------------------------------

def _teachers(t: _Tick, seat: Seat, region) -> list[str]:
    """Great scholars of the seat's ruler who teach there: those in its
    region, and those of no region of the ruler's at its best seat."""
    civ = t.civ(seat.lord)
    if civ is None:
        return []
    names = []
    best = _best_seat(t, seat.lord)
    held = set(civ.regions)
    for gp in civ.great_persons:
        if not gp.active or gp.role != "scientist":
            continue
        if gp.region == region.name or (best is seat and gp.region not in held):
            names.append(gp.name)
    return names


def _best_seat(t: _Tick, lord: int) -> Seat | None:
    best = None
    for _i, s in living_seats(t.world):
        if s.lord == lord and (best is None or s.level > best.level):
            best = s
    return best


def _scholars(t: _Tick, seat: Seat, region) -> None:
    world = t.world
    if t.scholars is not None:
        present = t.scholars[seat.region] if seat.region < len(t.scholars) else 0
    else:
        present = max(0, int(region.population)) * OFF_SCHOLAR_SHARE
    teachers = _teachers(t, seat, region)
    newcomer = next((n for n in teachers if n not in seat.teachers), None)
    if newcomer is not None:
        seat.teachers = (seat.teachers + [newcomer])[-TEACHERS_CAP:]
    seat.masters = len(teachers)
    if newcomer is not None:
        ev = _emit(t, "seat_master", [region.controller or ""],
                   f"{newcomer} teaches at {seat.name} in {region.name}", importance=3,
                   region=region.name)
        _note(seat, world.turn, "master", ev.event_id)
    seat.refugees = _q(seat.refugees * (1.0 - REFUGEE_DECAY))
    body = present / t.k if t.k > 0 else float(present)
    seat.scholars = _q(body + MASTER_SCHOLARS * seat.masters + seat.refugees)
    seat.peak_scholars = max(seat.peak_scholars, seat.scholars)


def _rise(t: _Tick, seat: Seat, region) -> None:
    world = t.world
    if seat.level >= len(LEVEL_NAMES) - 1 or seat.unpaid or world.turn - seat.level_turn < RISE_INTERVAL:
        return
    nxt = seat.level + 1
    if seat.scholars < RISE_SCHOLARS[nxt] or _patron_funds(t, seat, region) < RISE_FEE[nxt] + 1:
        return
    _charge(t, seat, region, RISE_FEE[nxt])
    _bump(t.state, "fees", RISE_FEE[nxt])
    seat.level = nxt
    seat.peak_level = max(seat.peak_level, nxt)
    seat.level_turn = world.turn
    _bump(t.state, "rises")
    lord = t.civ(seat.lord)
    ev = _emit(t, "seat_rose", [lord.name if lord is not None else ""],
               f"{_cap(seat.name)} in {region.name} becomes a {seat_label(seat)} "
               f"of {seat.scholars:.0f} scholars", importance=4 + (nxt >= 3), region=region.name)
    _note(seat, world.turn, "rose", ev.event_id)


def _decline(t: _Tick, seat: Seat, region, what: str, causes, kind: str) -> None:
    world = t.world
    seat.level -= 1
    seat.level_turn = world.turn
    _bump(t.state, "declines")
    lord = t.civ(seat.lord)
    ev = _emit(t, "seat_declined", [lord.name if lord is not None else ""],
               f"{_cap(seat.name)} in {region.name} {what}", importance=4, region=region.name,
               causes=causes)
    _note(seat, world.turn, kind, ev.event_id)


# --- the fall and the flight --------------------------------------------------

def _fall(t: _Tick, si: int, seat: Seat, region, cause: int, what: str, causes, *,
          actors: list[str] | None = None) -> None:
    from chronicler import provenance as prov
    world = t.world
    lord = t.civ(seat.lord)
    if actors is None:
        actors = [lord.name if lord is not None else ""]
    ev = _emit(t, "seat_fell", actors, f"{_cap(seat.name)} in {region.name} {what}",
               importance=5 + (seat.peak_level >= 2), region=region.name, causes=causes)
    _note(seat, world.turn, "fell", ev.event_id)
    body = seat.scholars
    seat.level = 0
    seat.fallen_turn = world.turn
    seat.fall_cause = cause
    seat.pull = 0.0
    _bump(t.state, "fallen")
    _bump(t.state, f"fall_{FALL_CAUSES[cause]}")
    refuge = _refuge(t, si, seat)
    from chronicler.techniques_state import techniques_on
    if refuge >= 0:
        dst = t.state.seats[refuge]
        dst.refugees = _q(dst.refugees + FLIGHT_SHARE * body)
        seat.refuge = refuge
        _bump(t.state, "refuges")
        dst_region = world.regions[dst.region]
        dst_lord = t.civ(dst.lord)
        flight = _emit(t, "scholars_fled", [lord.name if lord is not None else "",
                                            dst_lord.name if dst_lord is not None else ""],
                       f"The scholars of {seat.name} flee to {dst.name} in {dst_region.name} "
                       f"with their books", importance=4, region=region.name,
                       causes=[ev.event_id])
        prov.remember(world, prov.key("seat_flight", region.name), flight)
        _note(seat, world.turn, "fled", flight.event_id)
        _note(dst, world.turn, "refugees", flight.event_id)
    if techniques_on(world):
        dst_region_i = t.state.seats[refuge].region if refuge >= 0 else -1
        t.state.carries.append((seat.region, dst_region_i, seat.lord, si))


def _refuge(t: _Tick, si: int, seat: Seat) -> int:
    """The nearest living seat within FLIGHT_RANGE hops, a rival's (another
    ruler's) before one's own; ties by seat index. -1 when none is in reach."""
    world = t.world
    by_region = {s.region: i for i, s in living_seats(world) if i != si}
    if not by_region:
        return -1
    names = {r.name: i for i, r in enumerate(world.regions)}
    dist = {seat.region: 0}
    frontier = [seat.region]
    for d in range(1, FLIGHT_RANGE + 1):
        nxt = []
        for r in frontier:
            for adj in world.regions[r].adjacencies:
                j = names.get(adj)
                if j is not None and j not in dist:
                    dist[j] = d
                    nxt.append(j)
        frontier = sorted(nxt)
    found = [(dist[r], i) for r, i in by_region.items() if r in dist]
    if not found:
        return -1
    rivals = [(d, i) for d, i in found if t.state.seats[i].lord != seat.lord]
    return min(rivals or found)[1]


# --- foundings ----------------------------------------------------------------

def _seat_regions(world) -> set[int]:
    return {s.region for _i, s in living_seats(world)}


def _new_seat(t: _Tick, region_i: int, kind: int, name: str, lord: int, faith: int,
              city: int = 0) -> Seat:
    world = t.world
    seat = Seat(region=region_i, kind=kind, name=name, founded_turn=world.turn, founder=lord,
                lord=lord, faith=faith, city=city, level=1, peak_level=1, level_turn=world.turn)
    t.state.seats.append(seat)
    _bump(t.state, "founded")
    _bump(t.state, {ACADEMY: "academies", TEMPLE_SCHOOL: "temple_schools", LIBRARY: "libraries"}[kind])
    return seat


def _learned(civ) -> bool:
    return civ.active_focus == "scholarship" or any(v in LEARNED_VALUES for v in civ.values)


def _found_academies(t: _Tick) -> None:
    from chronicler.war.common import add_stat, projected_treasury
    world = t.world
    taken = _seat_regions(world)
    names = {r.name: i for i, r in enumerate(world.regions)}
    has = {s.lord for _i, s in living_seats(world) if s.kind == ACADEMY}
    for ci, civ in enumerate(world.civilizations):
        if not civ.regions or ci in has or not civ.capital_region:
            continue
        ri = names.get(civ.capital_region)
        if ri is None or ri in taken or world.regions[ri].controller != civ.name:
            continue
        if (civ.culture < ACADEMY_CULTURE or civ.stability < ACADEMY_STABILITY
                or projected_treasury(t, civ) < ACADEMY_TREASURY
                or any(civ.name in pair for pair in world.active_wars)
                or world.regions[ri].famine_cooldown > 0):
            continue
        chance = ACADEMY_CHANCE * (LEARNED_FACTOR if _learned(civ) else 1.0)
        if _rng(world, "academy", ci).random() >= chance:
            continue
        region = world.regions[ri]
        add_stat(t, civ, "treasury", -ACADEMY_FEE, "keep")
        _bump(t.state, "fees", ACADEMY_FEE)
        seat = _new_seat(t, ri, ACADEMY, f"the Academy of {region.name}", ci, region.majority_belief)
        ruler = f"{civ.leader.name} of {civ.name}" if civ.leader is not None else civ.name
        ev = _emit(t, "seat_founded", [civ.name],
                   f"{ruler} founds {seat.name} at the court in {region.name}", importance=5,
                   region=region.name)
        _note(seat, world.turn, "founded", ev.event_id)
        taken.add(ri)


def _found_schools(t: _Tick) -> None:
    world = t.world
    taken = _seat_regions(world)
    for ri, region in enumerate(world.regions):
        if ri in taken or not region.controller or _occupied(region):
            continue
        temple = _any_temple(region)
        if temple is None or temple.temple_prestige < SCHOOL_PRESTIGE + SCHOOL_COST:
            continue
        if _persecuted(region, temple.faith_id):
            continue
        if _rng(world, "school", ri).random() >= SCHOOL_CHANCE:
            continue
        temple.temple_prestige -= SCHOOL_COST
        _bump(t.state, "fees", SCHOOL_COST)
        faith = _faith_name(world, temple.faith_id)
        seat = _new_seat(t, ri, TEMPLE_SCHOOL, f"the Temple School of {region.name}",
                         t.lord_of(region), temple.faith_id)
        priests = f"The priests of {faith}" if faith else f"The temple priests of {region.name}"
        ev = _emit(t, "seat_founded", [region.controller],
                   f"{priests} open {seat.name} at their temple", importance=4,
                   region=region.name)
        _note(seat, world.turn, "founded", ev.event_id)
        taken.add(ri)


def _found_libraries(t: _Tick) -> None:
    world = t.world
    if not t.cities:
        return
    taken = _seat_regions(world)
    for sid in sorted(t.cities):
        city = t.cities[sid]
        if city.region in taken or city.rank < LIBRARY_RANK or city.wealth < LIBRARY_FEE:
            continue
        region = world.regions[city.region]
        if _occupied(region):
            continue
        if _rng(world, "library", sid).random() >= LIBRARY_CHANCE:
            continue
        city.wealth = round(city.wealth - LIBRARY_FEE, 4)
        _bump(t.state, "fees", LIBRARY_FEE)
        seat = _new_seat(t, city.region, LIBRARY, f"the Library of {city.name}", t.lord_of(region),
                         region.majority_belief, city=sid)
        ev = _emit(t, "seat_founded", [region.controller or ""],
                   f"The burghers of {city.name} found {seat.name}", importance=4,
                   region=region.name)
        _note(seat, world.turn, "founded", ev.event_id)
        taken.add(city.region)


# ---------------------------------------------------------------------------
# Effects read by other systems (scholarship on only)
# ---------------------------------------------------------------------------

def research_factor(world, civ) -> float:
    """Invention research multiplier of a ruler's seats (1.0 without any)."""
    if not scholarship_on(world):
        return 1.0
    ci = next((i for i, c in enumerate(world.civilizations) if c is civ or c.name == civ.name), -1)
    levels = sum(s.level for _i, s in living_seats(world) if s.lord == ci)
    if levels <= 0:
        return 1.0
    return 1.0 + RESEARCH_PER_LEVEL * min(RESEARCH_LEVELS, levels)


def learning_factors(world) -> tuple[dict[int, float], dict[int, float]] | None:
    """(adoption hazard factor, forgetting factor) by region index near
    living seats; None with the switch off."""
    if not scholarship_on(world):
        return None
    hazard: dict[int, float] = {}
    forget: dict[int, float] = {}
    names = {r.name: i for i, r in enumerate(world.regions)}
    for _i, s in living_seats(world):
        if s.region >= len(world.regions) or s.level <= 0:
            continue
        hazard[s.region] = max(hazard.get(s.region, 1.0), 1.0 + LEARN_HAZARD * s.level)
        forget[s.region] = min(forget.get(s.region, 1.0), 1.0 - LEARN_KEEP * s.level)
        for adj in world.regions[s.region].adjacencies:
            j = names.get(adj)
            if j is not None:
                hazard[j] = max(hazard.get(j, 1.0), 1.0 + LEARN_NEAR * s.level)
    return hazard, forget


def apply_carries(world, practice: dict, meta: dict, suit, prereqs, channel: int) -> None:
    """The next technique tick after a fall: the fleeing scholars start the
    techniques they carry in the refuge's region (CARRY_LEVEL, channel
    ``scholars``), and the region where the seat fell loses FALL_LOSS of its
    practice of the higher techniques. Consumes the pending carries."""
    if not scholarship_on(world) or not world.scholarship.carries:
        return
    from chronicler.techniques_state import TECHNIQUES
    state = world.scholarship
    n = len(world.regions)
    for src, dst, civ, _seat in state.carries:
        if not 0 <= src < n:
            continue
        here = sorted(((k, p) for (r, k), p in practice.items() if r == src and p > 0.0),
                      key=lambda kp: (-TECHNIQUES[kp[0]].tier, kp[0]))
        if 0 <= dst < n and world.regions[dst].population > 0:
            carried = 0
            for k, p in here:
                if carried >= CARRY_MAX:
                    break
                if p < CARRY_MIN or practice.get((dst, k), 0.0) >= CARRY_LEVEL:
                    continue
                if any(practice.get((dst, q), 0.0) < 0.2 for q in prereqs[k]):
                    continue
                from chronicler.techniques import GAIN_LEVEL, UNSUITED_CAP
                level = CARRY_LEVEL if suit[dst][k] else min(CARRY_LEVEL, UNSUITED_CAP)
                before = practice.get((dst, k), 0.0)
                practice[(dst, k)] = round(max(before, level), 6)
                if before < GAIN_LEVEL:
                    meta[(dst, k)] = (src, channel, civ)
                carried += 1
            _bump(state, "carried", carried)
        lost = 0
        for k, p in here:
            if TECHNIQUES[k].tier >= FALL_LOSS_TIER:
                practice[(src, k)] = round(p * (1.0 - FALL_LOSS), 6)
                lost += 1
        _bump(state, "practice_lost", lost)
    state.carries = []


def archive_copies(world, civ_index: int | None, region: int | None) -> int:
    """Archive copies seats keep (historiography): the level of a seat in the
    archive's region, +1 for another seat of the owner's realm; at most
    SEAT_COPIES_CAP. 0 with the switch off."""
    if not scholarship_on(world):
        return 0
    copies = 0
    other = False
    for _i, s in living_seats(world):
        if region is not None and s.region == region:
            copies += s.level
        elif civ_index is not None and s.lord == civ_index:
            other = True
    return min(SEAT_COPIES_CAP, copies + (1 if other else 0))


def region_pulls(world: "WorldState") -> tuple[list[float], list[bool]]:
    """``seat_pull`` and ``seat_flight`` per region index (the region batch
    columns), recomputed from persisted seats: a living seat's pull; a region
    whose seat fell within FLIGHT_TURNS turns and has none now sends its
    scholars away."""
    n = len(world.regions)
    pulls = [0.0] * n
    flight = [False] * n
    if not scholarship_on(world):
        return pulls, flight
    for s in world.scholarship.seats:
        if s.region >= n:
            continue
        if s.fallen_turn is None:
            pulls[s.region] = max(pulls[s.region], s.pull)
        elif world.turn - s.fallen_turn <= FLIGHT_TURNS:
            flight[s.region] = True
    for r in range(n):
        if pulls[r] > 0.0:
            flight[r] = False
    return pulls, flight


# ---------------------------------------------------------------------------
# Snapshot, history and metrics
# ---------------------------------------------------------------------------

def snapshot_summary(world: "WorldState") -> dict:
    """Per-turn summary for ``TurnSnapshot.scholarship``."""
    state = world.scholarship
    regions = world.regions
    civs = world.civilizations
    seats = []
    for si, s in living_seats(world):
        row = {"id": si, "name": s.name, "kind": KIND_NAMES[s.kind],
               "region": regions[s.region].name if s.region < len(regions) else None,
               "lord": civs[s.lord].name if 0 <= s.lord < len(civs) else None,
               "level": s.level, "scholars": round(s.scholars, 1), "masters": s.masters}
        if s.refugees >= 0.05:
            row["refugees"] = round(s.refugees, 1)
        if s.unpaid:
            row["unpaid"] = s.unpaid
        seats.append(row)
    return {
        "seats": seats,
        "fallen": sum(1 for s in state.seats if s.fallen_turn is not None),
        "counters": {k: state.counters.get(k, 0) for k in COUNTER_KEYS},
    }


def seat_history(world: "WorldState", index: int) -> list[str]:
    """One seat's record as text lines, with the event text the simulation wrote."""
    s = world.scholarship.seats[index]
    by_id = {e.event_id: e for e in world.events_timeline if e.event_id}
    region = world.regions[s.region].name
    civs = world.civilizations
    founder = civs[s.founder].name if 0 <= s.founder < len(civs) else "no one"
    if s.fallen_turn is not None:
        status = f"fell turn {s.fallen_turn} ({FALL_CAUSES[s.fall_cause]})"
        if s.refuge >= 0:
            status += f", its scholars to {world.scholarship.seats[s.refuge].name}"
    else:
        lord = civs[s.lord].name if 0 <= s.lord < len(civs) else "no one"
        status = f"standing: {seat_label(s)}, {s.scholars:.1f} scholars, under {lord}"
    lines = [f"{s.name} ({KIND_NAMES[s.kind]}), {region}; founded turn {s.founded_turn} under {founder}; "
             f"peak {LEVEL_NAMES[s.peak_level]} ({s.peak_scholars:.1f} scholars); {status}"]
    for turn, kind, eid in s.history:
        ev = by_id.get(eid)
        lines.append(f"  {turn:>4}: {kind}: {ev.description if ev is not None else ''}")
    return lines


def extract_scholarship_metrics(bundles: list[dict]) -> dict:
    """Analytics: per run, the final counters and the peak living seats."""
    runs = 0
    totals: dict[str, float] = {k: 0 for k in COUNTER_KEYS}
    peak = []
    for bundle in bundles:
        rows = [h.get("scholarship") for h in bundle.get("history") or []
                if isinstance(h, dict) and h.get("scholarship")]
        if not rows:
            continue
        runs += 1
        last = rows[-1].get("counters", {})
        for k in COUNTER_KEYS:
            totals[k] += float(last.get(k, 0))
        peak.append(max(len(r.get("seats", [])) for r in rows))
    if not runs:
        return {"runs": 0}
    return {
        "runs": runs,
        "per_run": {k: round(v / runs, 3) for k, v in totals.items()},
        "peak_seats_mean": round(sum(peak) / runs, 3),
    }
