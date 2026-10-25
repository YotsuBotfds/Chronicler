"""Cities as historical actors (``--cities``).

Default off behind ``WorldState.cities`` (CLI ``--cities``, persisted on the
world so a resumed run keeps it). With the switch off nothing in this module
runs and every output is identical to the simulation without it. See
``docs/integration/cities.md``.

A city is an M56a settlement (``chronicler.settlements``) grown to town size,
identified by its ``settlement_id``. Each turn, from the Phase 10 agent rows:

Rise and fall
    Founding at town size; ranks town, city, great city by residents (the
    agents whose ``settlement_id`` it is); decline after turns below a
    rank's floor; the fall when M56a dissolves the settlement or the city
    stands nearly empty.

Wealth
    Commerce from its residents by occupation, the region's trade routes
    and food. Dues (by charter) go to the lord, paid as ``keep`` treasury in
    the next turn's Phase 2 (:func:`pay_dues`); the rest fills a civic purse
    that pays for charters and walls and is plundered in a sack.

Population drawn from the hinterland
    :func:`region_pulls` gives each region a ``city_pull`` for the region
    batch; the Rust urban driver (``migration_drivers.rs``) draws rural
    adults of the same realm toward it.

Political voice
    Patricians raise the lord's merchant faction; cities petition for
    charters; unrest from hunger, misery, dues, occupation and grievance
    breaks out in revolts that end in suppression, concession or, against a
    weak lord, a free city (a new civilization, as secession builds one).

War and disease
    Sacks on occupation or conquest; walls through the infrastructure
    pipeline; with ``--epidemiology`` density raises susceptibility
    (:func:`epidemic_susceptibility_factors`).

Identity: region = index in ``world.regions``, civ = index in
``world.civilizations``, city = ``settlement_id``. All randomness comes from
``random.Random(stable_hash_int("cities", <namespace>, seed, turn, id))``.
Stat changes use the existing accumulator categories.
"""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Iterable

from chronicler.cities_state import (
    CHARTER_NAMES, CITY, COUNTER_KEYS, FREE_CITY, GREAT_CITY, MARKET_RIGHTS, NO_CHARTER,
    RANK_NAMES, SELF_GOVERNMENT, TOWN, City, CityState, cities_on,
)
from chronicler.utils import stable_hash_int

if TYPE_CHECKING:  # pragma: no cover
    from chronicler.models import Civilization, Event, Region, WorldState


# ---------------------------------------------------------------------------
# Parameters ([CALIBRATE]; documented in docs/integration/cities.md)
# ---------------------------------------------------------------------------

#: Default for worlds created by the CLI/batch/live entry points.
DEFAULT_ENABLED_FOR_NEW_WORLDS = False

# Ranks (residents at a mean region carrying capacity of REFERENCE_CAPACITY).
REFERENCE_CAPACITY = 60.0
RANK_POP = (0.0, 12.0, 25.0, 40.0)   # by rank: -, town, city, great city
DOWN_FACTOR = 0.7                    # a rank is lost below this share of its threshold ...
DOWN_TURNS = 10                      # ... for this many turns
FALL_POP = 5.0                       # a city with fewer residents ...
FALL_TURNS = 10                      # ... for this many turns is deserted
SIZE_RATE = 0.05                     # share of the gap to M56a's estimate closed per turn
COMPOSITION_MIN = 3                  # footprint agents needed to read the mix and satisfaction
HISTORY_CAP = 60                     # history entries kept per city (the founding always)
MISFORTUNE_GAP = 30                  # turns between plague (or famine) entries in a history
MISFORTUNE_IMPORTANCE = 7            # epidemics entered in a history (plague, pox, pestilence)

# Commerce: treasury per resident by occupation (farmer, soldier, merchant,
# scholar, priest), times market access and food. Residents are counted at
# the reference scale (size / scale(world)), so a city's commerce does not
# grow with the agent count of the world, only with its standing in it.
COMMERCE_WEIGHTS = (0.025, 0.05, 0.3, 0.12, 0.1)
#: Occupation mix assumed until agents are counted (and with --agents off).
OFF_MODE_MIX = (0.45, 0.15, 0.15, 0.15, 0.10)
ROUTE_ACCESS = 0.15                  # per goods trade route of the region ...
ROUTE_ACCESS_CAP = 4                 # ... counted up to this many
OCCUPIED_COMMERCE = 0.25             # share of commerce while an enemy occupies the region
OFF_MODE_FAMINE_FOOD = 0.5           # food factor of a famine region with --agents off
WEALTH_DECAY = 0.02                  # civic purse, per turn
#: Share of commerce owed to the lord by charter (a free city keeps its
#: share for its own treasury).
DUES = (0.30, 0.20, 0.10, 0.30)

# Political voice.
VOICE_PER_WEIGHT = 0.002             # merchant influence per rank x (1 + charter / 2)
VOICE_CAP = 0.015                    # per lord per turn

# Charters.
CHARTER_FEE = (0.0, 15.0, 40.0)      # by level: -, market rights, self-government
CHARTER_MIN_RANK = (0, TOWN, CITY)
PETITION_INTERVAL = 15
GRANT_BASE = 0.45
GRANT_TRAIT = 0.25
GRANT_POOR = 0.15                    # lord's treasury below GRANT_POOR_TREASURY
GRANT_POOR_TREASURY = 30
GRANT_WEAK = 0.15                    # lord's stability below GRANT_WEAK_STABILITY
GRANT_WEAK_STABILITY = 30
GRANT_MERCHANT = 0.6                 # times (merchant influence - 0.25)
GRANT_MIN, GRANT_MAX = 0.05, 0.95
SELLING_TRAITS = frozenset({"cautious", "calculating", "shrewd", "opportunistic"})
REFUSING_TRAITS = frozenset({"aggressive", "zealous", "stubborn", "bold"})
REFUSAL_GRIEVANCE = 0.25
CHARTER_MERCHANT = 0.03              # merchant influence of a grant or concession

# Unrest (0..1).
SAT_CALM = 0.5                       # residents' mean satisfaction below this ...
SAT_UNREST = 2.0                     # ... raises the target by this per unit
HUNGER_FLOOR = 0.8                   # food sufficiency below this ...
HUNGER_UNREST = 0.5                  # ... raises the target up to this at no food
DUES_UNREST = (0.10, 0.05, 0.0, 0.0)
OCCUPIED_UNREST = 0.3
UNREST_RATE = 0.2                    # share of the gap to the target closed per turn
GRIEVANCE_DECAY = 0.96

# Revolts.
REVOLT_UNREST = 0.6
REVOLT_CHANCE = 0.2                  # per turn at unrest 1, from 0 at REVOLT_UNREST
REVOLT_COOLDOWN = 12
REVOLT_STABILITY = 5                 # lord, guard-shock
CONCESSION_STABILITY = 30            # a lord below this yields
CONCESSION_CHANCE = 0.3              # otherwise
SUPPRESSION_FINE = 0.25              # share of the purse
SUPPRESSED_UNREST = 0.4              # unrest removed
SUPPRESSED_GRIEVANCE = 0.1

# Free cities.
FREE_CITY_LORD_STABILITY = 30        # a lord below this loses the city
FREE_CITY_MIN_RANK = CITY
FREE_CITY_MIN_CHARTER = MARKET_RIGHTS
FREE_CITY_MIN_LORD_REGIONS = 2
FREE_CITY_STABILITY = 50
FREE_CITY_ASABIYA = 0.6
FREE_CITY_TREASURY_SHARE = 0.5       # of the purse
FREE_CITY_LORD_LOSS = 10             # lord's stability, guard-shock
FREE_CITY_TRAITS = ("shrewd", "calculating", "cautious")
FREE_CITY_VALUE = "freedom"
#: Free cities are not created when the civ registry is this close to the
#: native uint8 limit (``ffi_constants.MAX_CIV_RECORDS``).
FREE_CITY_CIV_HEADROOM = 4

# War.
SACK_SHARE = 0.5
SACK_GRIEVANCE = 0.3
SACK_COOLDOWN = 20
WALL_COST = 30.0
WALL_MIN_RANK = CITY

# Migration pull by rank (region batch ``city_pull``).
RANK_PULL = (0.0, 0.4, 0.7, 1.0)

# Disease: susceptibility x (1 + URBAN_SUSCEPTIBILITY x urban share).
URBAN_SUSCEPTIBILITY = 0.5

# Credit: lord's domestic credit x (1 + CREDIT_PER_CHARTER per charter level).
CREDIT_PER_CHARTER = 0.1
CREDIT_CAP = 1.5

#: Stored floats are rounded to this many decimals.
QUANTUM_DIGITS = 4



# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

def cities_enabled(world) -> bool:
    """True only for a real city state (mocks and ``None`` read as off)."""
    return cities_on(world)


def set_cities_enabled(world: "WorldState", enabled: bool) -> None:
    """Enable (an empty state; cities are founded from settlements as they
    grow) or disable (dropping every city record)."""
    if enabled:
        if world.cities is None:
            world.cities = CityState()
        return
    world.cities = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _q(x: float) -> float:
    return round(x, QUANTUM_DIGITS)


def _rng(world, namespace: str, *parts) -> random.Random:
    return random.Random(stable_hash_int("cities", namespace, world.seed, world.turn, *parts))


def _bump(state: CityState, key: str, n: float = 1) -> None:
    state.counters[key] = round(state.counters.get(key, 0) + n, 4)


def scale(world) -> float:
    """World scale of the rank thresholds: mean region carrying capacity / 60."""
    caps = [r.carrying_capacity for r in world.regions if r.carrying_capacity > 0]
    if not caps:
        return 1.0
    return (sum(caps) / len(caps)) / REFERENCE_CAPACITY


def rank_for(residents: float, k: float) -> int:
    """Highest rank whose threshold ``residents`` meets (0 below town size)."""
    rank = 0
    for r in (TOWN, CITY, GREAT_CITY):
        if residents >= RANK_POP[r] * k:
            rank = r
    return rank


def _at_war(world, a: str, b: str) -> bool:
    return (a, b) in world.active_wars or (b, a) in world.active_wars


def _civ_at_war(world, name: str) -> bool:
    return any(name in pair for pair in world.active_wars)


def _occupied(region) -> bool:
    return region.occupied_by is not None and region.occupied_by != region.controller


class _Tick:
    def __init__(self, world, acc, agent_bridge, economy_result) -> None:
        self.world = world
        self.acc = acc
        self.bridge = agent_bridge
        self.economy = economy_result
        self.state: CityState = world.cities
        self.events: list = []
        self.index = {c.name: i for i, c in enumerate(world.civilizations)}

    def civ(self, idx: int):
        civs = self.world.civilizations
        return civs[idx] if 0 <= idx < len(civs) else None

    def food(self, region) -> float:
        """Region food sufficiency capped at 1 (economy result; famine proxy
        with --agents off)."""
        if self.economy is not None:
            return min(1.0, float(self.economy.food_sufficiency.get(region.name, 1.0)))
        return OFF_MODE_FAMINE_FOOD if region.famine_cooldown > 0 else 1.0

    def routes(self, region) -> int:
        if self.economy is None:
            return 0
        return int(self.economy.trade_route_counts.get(region.name, 0))


def _emit(t: _Tick, event_type: str, actors: Iterable[str], description: str, *,
          importance: int = 5, region: str | None = None,
          causes: Iterable[str | None] = ()) -> "Event":
    from chronicler import provenance
    from chronicler.models import Event
    ev = Event(turn=t.world.turn, event_type=event_type,
               actors=[a for a in actors if a], description=description,
               importance=importance, region=region)
    provenance.cite(ev, *causes)
    # Same-tick chains (revolt -> free city) resolve in order.
    provenance.observe_now(t.world, ev)
    t.events.append(ev)
    return ev


def _note(city: City, turn: int, kind: str, event_id: str = "") -> None:
    city.history.append((turn, kind, event_id))
    if len(city.history) > HISTORY_CAP:
        del city.history[1]   # keep the founding


def _add_stat(t: _Tick, civ, stat: str, delta: float, category: str) -> None:
    from chronicler.war.common import add_stat
    add_stat(t, civ, stat, delta, category)


def _owe(t: _Tick, civ_idx: int, amount: float) -> None:
    if civ_idx < 0 or amount <= 0:
        return
    state = t.state
    while len(state.owed) <= civ_idx:
        state.owed.append(0.0)
        state.carry.append(0.0)
    state.owed[civ_idx] = round(state.owed[civ_idx] + amount, 6)


def _lord_name(t: _Tick, city: City) -> str | None:
    civ = t.civ(city.lord)
    return civ.name if civ is not None else None


def _label(city: City) -> str:
    return RANK_NAMES[city.rank]


def _sack_key(city: City) -> str:
    from chronicler import provenance as prov
    return prov.key("city_sack", str(city.settlement_id))


def _refusal_key(city: City) -> str:
    from chronicler import provenance as prov
    return prov.key("city_refusal", str(city.settlement_id))


def _region_causes(t: _Tick, region_name: str) -> list[str | None]:
    """The region's latest sack-worthy or misery causes: occupation, epidemic, famine."""
    from chronicler import provenance as prov
    w = t.world
    return [
        prov.recall(w, prov.key("occupation", region_name), within=10),
        prov.recall(w, prov.key("pandemic", region_name), within=10),
        prov.open_episode(w, "famine", region_name),
    ]


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------

class _Observation:
    """Footprint residents per settlement id from the Phase 10 agent rows:
    their count by occupation and their satisfaction sum."""

    def __init__(self, counts, occupations, sat_sum) -> None:
        self.counts = counts
        self.occupations = occupations
        self.sat_sum = sat_sum

    def of(self, sid: int) -> tuple[int, list[float], float]:
        if sid >= len(self.counts):
            return 0, [0.0] * 5, 0.0
        return (int(self.counts[sid]), [float(o[sid]) for o in self.occupations],
                float(self.sat_sum[sid]))


def _observe(phase10) -> _Observation | None:
    rows = getattr(phase10, "agents", None) if phase10 is not None else None
    if rows is None:
        return None
    arrays = rows.arrays("settlement_id", "occupation", "satisfaction")
    if arrays is None:
        return None
    import numpy as np
    sid, occ, sat = arrays
    sid = sid.astype(np.int64)
    n = int(sid.max()) + 1 if sid.size else 1
    counts = np.bincount(sid, minlength=n)
    occupations = [np.bincount(sid[occ == k], minlength=n) for k in range(5)]
    sat_sum = np.bincount(sid, weights=sat.astype(np.float64), minlength=n)
    return _Observation(counts, occupations, sat_sum)


def _composition(city: City, obs: _Observation | None) -> None:
    """Occupation shares and mean satisfaction of the agents now in the
    footprint, when there are at least COMPOSITION_MIN of them; otherwise
    the last ones are kept (with --agents off: the default mix, no
    satisfaction)."""
    if obs is None:
        return
    n, occ, sat_sum = obs.of(city.settlement_id)
    if n < COMPOSITION_MIN:
        return
    city.mix = [_q(o / n) for o in occ]
    city.satisfaction = _q(sat_sum / n)


# ---------------------------------------------------------------------------
# The tick (Phase 10)
# ---------------------------------------------------------------------------

def tick_cities(world: "WorldState", events: Iterable["Event"] = (), acc=None, *,
                phase10=None, agent_bridge=None, economy_result=None) -> list["Event"]:
    """Phase 10: falls, lords and sacks, ranks, commerce, unrest, walls,
    charters, revolts, pull, foundings, voice. Returns the turn's city events."""
    if not cities_on(world):
        return []
    from chronicler.models import SettlementStatus
    t = _Tick(world, acc, agent_bridge, economy_result)
    state = t.state
    obs = _observe(phase10)
    k = scale(world)
    live = (SettlementStatus.ACTIVE, SettlementStatus.DISSOLVING)
    settlements = {}
    for ri, region in enumerate(world.regions):
        for s in region.settlements:
            if s.status in live:
                settlements[s.settlement_id] = (ri, s)
    turn_events = list(events)

    # Foundings first, so a new city takes part in this turn.
    known = {c.settlement_id for c in state.cities} | {c.settlement_id for c in state.fallen}
    for sid in sorted(settlements):
        if sid in known:
            continue
        ri, settlement = settlements[sid]
        if settlement.status != SettlementStatus.ACTIVE:
            continue
        residents = int(settlement.population_estimate)
        rank = rank_for(residents, k)
        if rank >= TOWN:
            _found(t, settlement, ri, residents, rank)

    living: list[City] = []
    for city in sorted(state.cities, key=lambda c: c.settlement_id):
        entry = settlements.get(city.settlement_id)
        if entry is None:
            _fall(t, city, "abandoned")
            continue
        ri, settlement = entry
        region = world.regions[ri]
        _lord_change(t, city, region)
        if _occupied(region):
            _occupation_sack(t, city, region)
        _composition(city, obs)
        _update_rank(t, city, region, int(settlement.population_estimate), k)
        if city.empty_turns >= FALL_TURNS:
            _fall(t, city, "deserted")
            continue
        food = t.food(region)
        _commerce(t, city, region, food, k)
        _unrest(t, city, region, food)
        _walls(t, city, region)
        _petition(t, city, region)
        _revolt(t, city, region)
        _record_misfortune(t, city, region, turn_events)
        city.pull = 0.0 if _occupied(region) else _q(
            RANK_PULL[city.rank] * (1.0 - city.unrest) * food)
        living.append(city)
    state.cities = living

    _voice(t)
    state.last_tick_turn = world.turn
    return t.events


def _found(t: _Tick, settlement, ri: int, residents: int, rank: int) -> None:
    world = t.world
    region = world.regions[ri]
    lord = t.index.get(region.controller, -1) if region.controller else -1
    city = City(settlement_id=settlement.settlement_id, region=ri, name=settlement.name,
                founded_turn=world.turn, founder=lord, lord=lord, rank=rank, peak_rank=rank,
                residents=residents, size=float(residents), peak_residents=residents,
                mix=list(OFF_MODE_MIX))
    predecessor = next((c for c in reversed(t.state.fallen) if c.region == ri), None)
    tail = ""
    if predecessor is not None:
        city.predecessor = predecessor.settlement_id
        tail = f", where {predecessor.name} once stood"
    ev = _emit(t, "city_founded", [region.controller or ""],
               f"{settlement.name} in {region.name} has grown into a {RANK_NAMES[rank]} "
               f"of {residents} people{tail}",
               importance=4 + (rank >= CITY) + (rank >= GREAT_CITY), region=region.name)
    _note(city, world.turn, "founded", ev.event_id)
    t.state.cities.append(city)
    _bump(t.state, "founded")


def _fall(t: _Tick, city: City, how: str) -> None:
    world = t.world
    region = world.regions[city.region]
    rname = region.name
    causes = _region_causes(t, rname)
    from chronicler import provenance as prov
    sack = prov.recall(world, _sack_key(city), within=40)
    cause_label = how
    if sack:
        cause_label = f"{how} after its sack"
    elif causes[1]:
        cause_label = f"{how} after plague"
    elif causes[2]:
        cause_label = f"{how} in famine"
    verb = "is abandoned" if how == "abandoned" else "stands deserted"
    ev = _emit(t, "city_fell", [region.controller or ""],
               f"The {_label(city)} of {city.name} in {rname} {verb}",
               importance=5 + (city.peak_rank >= CITY), region=rname,
               causes=(sack, *causes))
    city.fallen_turn = world.turn
    city.fall_cause = cause_label
    city.pull = 0.0
    _note(city, world.turn, "fell", ev.event_id)
    t.state.fallen.append(city)
    _bump(t.state, "fallen")


def _lord_change(t: _Tick, city: City, region) -> None:
    world = t.world
    ctrl = t.index.get(region.controller, -1) if region.controller else -1
    if ctrl == city.lord:
        return
    old = city.lord
    city.lord = ctrl
    from chronicler import provenance as prov
    conquest = (prov.recall(world, prov.key("conquest", region.name), within=1)
                or prov.recall(world, prov.key("occupation", region.name), within=1))
    old_civ, new_civ = t.civ(old), t.civ(ctrl)
    at_war = old_civ is not None and new_civ is not None and _at_war(world, old_civ.name, new_civ.name)
    if city.charter == FREE_CITY:
        city.charter = SELF_GOVERNMENT   # sovereignty ends with the city's own state
    if new_civ is not None and (conquest or at_war):
        _sack(t, city, region, ctrl, conquest, conquered=True, victim_idx=old)
    else:
        _new_lord(t, city, region, old_civ, new_civ, None)


def _new_lord(t: _Tick, city: City, region, old_civ, new_civ, cause: str | None) -> None:
    """A lord change without plunder (peaceful, or a conquest within the
    sack cooldown)."""
    old_name = old_civ.name if old_civ is not None else "no one"
    new_name = new_civ.name if new_civ is not None else "no one"
    ev = _emit(t, "city_lord_changed", [new_civ.name if new_civ else "", old_civ.name if old_civ else ""],
               f"{city.name} in {region.name} passes from {old_name} to {new_name}",
               importance=3, region=region.name, causes=(cause,))
    _note(city, t.world.turn, "lord", ev.event_id)


def _occupation_sack(t: _Tick, city: City, region) -> None:
    occupier = t.index.get(region.occupied_by, -1)
    if occupier < 0:
        return
    from chronicler import provenance as prov
    _sack(t, city, region, occupier, prov.recall(t.world, prov.key("occupation", region.name)),
          conquered=False, victim_idx=city.lord)


def _sack(t: _Tick, city: City, region, sacker_idx: int, cause: str | None, *,
          conquered: bool, victim_idx: int) -> None:
    """Plunder of the purse (at most once in SACK_COOLDOWN turns); a
    conqueror also revokes one charter level."""
    world = t.world
    if conquered and city.charter > NO_CHARTER:
        city.charter -= 1
    if world.turn - city.last_sack < SACK_COOLDOWN:
        if conquered:
            _new_lord(t, city, region, t.civ(victim_idx), t.civ(sacker_idx), cause)
        return
    sacker = t.civ(sacker_idx)
    loot = city.wealth * SACK_SHARE
    paid = int(loot)
    city.wealth = _q(city.wealth - loot)
    city.grievance = _q(min(1.0, city.grievance + SACK_GRIEVANCE))
    city.last_sack = world.turn
    if sacker is not None and paid > 0:
        _add_stat(t, sacker, "treasury", paid, "keep")
    _bump(t.state, "sacks")
    _bump(t.state, "plunder", paid)
    victim = t.civ(victim_idx)
    ev = _emit(t, "city_sacked", [sacker.name if sacker else "", victim.name if victim else ""],
               f"{sacker.name if sacker else 'Raiders'} sack {city.name} in {region.name} "
               f"and carry off {paid} in plunder",
               importance=6 + (city.rank >= CITY), region=region.name, causes=(cause,))
    from chronicler import provenance as prov
    prov.remember(world, _sack_key(city), ev)
    _note(city, world.turn, "sacked", ev.event_id)


def _update_rank(t: _Tick, city: City, region, residents: int, k: float) -> None:
    """Size follows M56a's estimate (SIZE_RATE a turn); a rank is gained when
    the size reaches the next threshold and lost after DOWN_TURNS turns
    below DOWN_FACTOR of its own."""
    world = t.world
    city.residents = residents
    city.peak_residents = max(city.peak_residents, residents)
    city.size = _q(city.size + SIZE_RATE * (residents - city.size))
    size = city.size
    city.empty_turns = city.empty_turns + 1 if size < FALL_POP * k else 0
    if city.rank < GREAT_CITY and size >= RANK_POP[city.rank + 1] * k:
        city.rank += 1
        city.below_turns = 0
        first = city.rank > city.peak_rank
        city.peak_rank = max(city.peak_rank, city.rank)
        ev = _emit(t, "city_grew", [region.controller or ""],
                   f"{city.name} in {region.name} has grown into a {_label(city)} of {round(size)} people"
                   + ("" if first else " again"),
                   importance=4 + (city.rank >= GREAT_CITY), region=region.name)
        _note(city, world.turn, "grew", ev.event_id)
        _bump(t.state, "rank_ups")
        return
    if size < DOWN_FACTOR * RANK_POP[city.rank] * k:
        city.below_turns += 1
        if city.below_turns >= DOWN_TURNS and city.rank > TOWN:
            city.rank -= 1
            city.below_turns = 0
            causes = _region_causes(t, region.name)
            from chronicler import provenance as prov
            ev = _emit(t, "city_declined", [region.controller or ""],
                       f"{city.name} in {region.name} has shrunk to a {_label(city)} of {round(size)} people",
                       importance=4, region=region.name,
                       causes=(prov.recall(world, _sack_key(city), within=40), *causes))
            _note(city, world.turn, "declined", ev.event_id)
            _bump(t.state, "rank_downs")
    else:
        city.below_turns = 0


def _commerce(t: _Tick, city: City, region, food: float, k: float) -> None:
    base = city.size / k * sum(w * m for w, m in zip(COMMERCE_WEIGHTS, city.mix))
    access = 1.0 + ROUTE_ACCESS * min(t.routes(region), ROUTE_ACCESS_CAP)
    commerce = base * access * food * (OCCUPIED_COMMERCE if _occupied(region) else 1.0)
    dues = commerce * DUES[city.charter] if city.lord >= 0 else 0.0
    _owe(t, city.lord, dues)
    city.commerce = _q(commerce)
    city.wealth = _q(city.wealth * (1.0 - WEALTH_DECAY) + commerce - dues)
    city.peak_wealth = max(city.peak_wealth, city.wealth)
    _bump(t.state, "commerce", round(commerce, 4))


def _unrest(t: _Tick, city: City, region, food: float) -> None:
    hunger = max(0.0, HUNGER_FLOOR - food) / HUNGER_FLOOR
    target = DUES_UNREST[city.charter] + city.grievance + HUNGER_UNREST * hunger
    if city.satisfaction is not None:
        target += SAT_UNREST * max(0.0, SAT_CALM - city.satisfaction)
    if _occupied(region):
        target += OCCUPIED_UNREST
    target = min(1.0, target)
    city.unrest = _q(min(1.0, max(0.0, city.unrest + UNREST_RATE * (target - city.unrest))))
    city.grievance = _q(city.grievance * GRIEVANCE_DECAY)


def _walls(t: _Tick, city: City, region) -> None:
    from chronicler.models import InfrastructureType, PendingBuild
    lord = t.civ(city.lord)
    if lord is None or city.wealth < WALL_COST or region.pending_build is not None or _occupied(region):
        return
    if city.rank < WALL_MIN_RANK and not _civ_at_war(t.world, lord.name):
        return
    if any(i.type == InfrastructureType.FORTIFICATIONS and i.active for i in region.infrastructure):
        return
    from chronicler.infrastructure import BUILD_SPECS
    region.pending_build = PendingBuild(
        type=InfrastructureType.FORTIFICATIONS, builder_civ=lord.name,
        started_turn=t.world.turn, turns_remaining=BUILD_SPECS[InfrastructureType.FORTIFICATIONS].turns,
    )
    city.wealth = _q(city.wealth - WALL_COST)
    _bump(t.state, "walls")
    ev = _emit(t, "city_walls", [lord.name],
               f"{city.name} in {region.name} begins walls at its own cost",
               importance=3, region=region.name)
    _note(city, t.world.turn, "walls", ev.event_id)


def grant_chance(lord, merchant_influence: float) -> float:
    """Chance that a lord grants a charter petition."""
    p = GRANT_BASE
    trait = getattr(lord.leader, "trait", "")
    if trait in SELLING_TRAITS:
        p += GRANT_TRAIT
    elif trait in REFUSING_TRAITS:
        p -= GRANT_TRAIT
    if lord.treasury < GRANT_POOR_TREASURY:
        p += GRANT_POOR
    if lord.stability < GRANT_WEAK_STABILITY:
        p += GRANT_WEAK
    p += GRANT_MERCHANT * (merchant_influence - 0.25)
    return min(GRANT_MAX, max(GRANT_MIN, p))


def _merchant_influence(civ) -> float:
    from chronicler.models import FactionType
    return float(civ.factions.influence.get(FactionType.MERCHANT, 0.25))


def _shift_merchants(civ, amount: float) -> None:
    from chronicler.factions import normalize_influence
    from chronicler.models import FactionType
    civ.factions.influence[FactionType.MERCHANT] = (
        civ.factions.influence.get(FactionType.MERCHANT, 0.0) + amount)
    normalize_influence(civ.factions)


def _petition(t: _Tick, city: City, region) -> None:
    world = t.world
    lord = t.civ(city.lord)
    if lord is None or not lord.regions or city.charter >= SELF_GOVERNMENT:
        return
    if world.turn - city.last_petition < PETITION_INTERVAL:
        return
    level = city.charter + 1
    fee = CHARTER_FEE[level]
    if city.rank < CHARTER_MIN_RANK[level] or city.wealth < fee:
        return
    city.last_petition = world.turn
    rng = _rng(world, "petition", city.settlement_id)
    if rng.random() < grant_chance(lord, _merchant_influence(lord)):
        city.charter = level
        city.wealth = _q(city.wealth - fee)
        city.grievance = _q(max(0.0, city.grievance - REFUSAL_GRIEVANCE))
        _add_stat(t, lord, "treasury", int(fee), "keep")
        _shift_merchants(lord, CHARTER_MERCHANT)
        _bump(t.state, "charters")
        _bump(t.state, "fees", int(fee))
        ev = _emit(t, "city_charter", [lord.name],
                   f"{lord.name} grants {city.name} {CHARTER_NAMES[level]} for {int(fee)}",
                   importance=5, region=region.name)
        _note(city, world.turn, "charter", ev.event_id)
    else:
        city.grievance = _q(min(1.0, city.grievance + REFUSAL_GRIEVANCE))
        _bump(t.state, "refusals")
        ev = _emit(t, "charter_refused", [lord.name],
                   f"{lord.name} refuses {city.name} {CHARTER_NAMES[level]}",
                   importance=4, region=region.name)
        from chronicler import provenance as prov
        prov.remember(world, _refusal_key(city), ev)
        _note(city, world.turn, "refused", ev.event_id)


def _revolt(t: _Tick, city: City, region) -> None:
    world = t.world
    lord = t.civ(city.lord)
    if (lord is None or not lord.regions or city.charter == FREE_CITY
            or city.unrest < REVOLT_UNREST or world.turn - city.last_revolt < REVOLT_COOLDOWN):
        return
    chance = REVOLT_CHANCE * (city.unrest - REVOLT_UNREST) / (1.0 - REVOLT_UNREST)
    rng = _rng(world, "revolt", city.settlement_id)
    if rng.random() >= chance:
        return
    from chronicler import provenance as prov
    city.last_revolt = world.turn
    _bump(t.state, "revolts")
    causes = (prov.recall(world, _sack_key(city), within=30),
              prov.recall(world, _refusal_key(city), within=30),
              *_region_causes(t, region.name))
    revolt = _emit(t, "urban_revolt", [lord.name],
                   f"The people of {city.name} in {region.name} rise against {lord.name}",
                   importance=6, region=region.name, causes=causes)
    _note(city, world.turn, "revolt", revolt.event_id)
    # The lord's standing after the revolt, read before the change is applied
    # (directly with --agents off, through the accumulator in hybrid mode).
    projected = lord.stability - REVOLT_STABILITY
    _add_stat(t, lord, "stability", -REVOLT_STABILITY, "guard-shock")
    if (projected < FREE_CITY_LORD_STABILITY and city.rank >= FREE_CITY_MIN_RANK
            and city.charter >= FREE_CITY_MIN_CHARTER and len(lord.regions) >= FREE_CITY_MIN_LORD_REGIONS
            and lord.capital_region != region.name and not _occupied(region)
            and len(world.civilizations) + FREE_CITY_CIV_HEADROOM <= _max_civs()):
        _free_city(t, city, region, lord, revolt)
        return
    if projected < CONCESSION_STABILITY or rng.random() < CONCESSION_CHANCE:
        if city.charter < SELF_GOVERNMENT:
            city.charter += 1
        city.grievance = 0.0
        city.unrest = _q(max(0.0, city.unrest - SUPPRESSED_UNREST))
        _shift_merchants(lord, CHARTER_MERCHANT)
        _bump(t.state, "concessions")
        ev = _emit(t, "urban_concession", [lord.name],
                   f"{lord.name} yields to {city.name}: {CHARTER_NAMES[city.charter]}",
                   importance=5, region=region.name, causes=(revolt.event_id,))
        _note(city, world.turn, "concession", ev.event_id)
        return
    fine = int(city.wealth * SUPPRESSION_FINE)
    city.wealth = _q(city.wealth - fine)
    city.unrest = _q(max(0.0, city.unrest - SUPPRESSED_UNREST))
    city.grievance = _q(min(1.0, city.grievance + SUPPRESSED_GRIEVANCE))
    if fine > 0:
        _add_stat(t, lord, "treasury", fine, "keep")
    _bump(t.state, "suppressions")
    _bump(t.state, "fines", fine)
    ev = _emit(t, "revolt_suppressed", [lord.name],
               f"{lord.name} puts down the revolt in {city.name} and fines the city {fine}",
               importance=5, region=region.name, causes=(revolt.event_id,))
    _note(city, world.turn, "suppressed", ev.event_id)


def _max_civs() -> int:
    from chronicler.ffi_constants import MAX_CIV_RECORDS
    return MAX_CIV_RECORDS


def _free_city_name(world, region) -> str:
    existing = {c.name for c in world.civilizations}
    name = f"Free City of {region.name}"
    if name in existing:
        name = f"Free City of {region.name} {world.turn}"
    return name


def _free_city(t: _Tick, city: City, region, lord, revolt) -> None:
    """The city's region secedes as a city-state, built as ``check_secession``
    builds a breakaway (one region, hostile to its old lord)."""
    from chronicler.leaders import _compose_regnal_name, _pick_regnal_name
    from chronicler.models import Civilization, Disposition, Leader, Relationship
    from chronicler.utils import sync_civ_population
    world = t.world
    lord_idx = t.index[lord.name]
    name = _free_city_name(world, region)
    share = region.population / max(1, lord.population)
    split_mil = math.floor(lord.military * share)
    split_eco = math.floor(lord.economy * share)
    treasury = int(city.wealth * FREE_CITY_TREASURY_SHARE)
    city.wealth = _q(city.wealth - treasury)
    rng = _rng(world, "free_city", city.settlement_id)
    values = list(lord.values)
    if values and FREE_CITY_VALUE not in values:
        values[-1] = FREE_CITY_VALUE
    leader = Leader(name="Placeholder", trait=rng.choice(FREE_CITY_TRAITS),
                    reign_start=world.turn, succession_type="election")
    new = Civilization(
        name=name, population=max(region.population, 1), military=max(split_mil, 0),
        economy=max(split_eco, 0), culture=lord.culture, stability=FREE_CITY_STABILITY,
        treasury=treasury, tech_era=lord.tech_era, leader=leader, regions=[region.name],
        capital_region=region.name, domains=list(lord.domains), values=values,
        asabiya=FREE_CITY_ASABIYA, leader_name_pool=list(lord.leader_name_pool or []),
    )
    region.asabiya_state.asabiya = FREE_CITY_ASABIYA
    regnal = random.Random(stable_hash_int("cities", "regnal", world.seed, world.turn, name))
    title, throne, ordinal = _pick_regnal_name(new, world, regnal)
    new.leader.name = _compose_regnal_name(title, throne, ordinal)
    new.leader.throne_name = throne
    new.leader.regnal_ordinal = ordinal
    new.founded_turn = world.turn
    new.traditions = list(lord.traditions)
    new_idx = len(world.civilizations)

    _add_stat(t, lord, "military", -split_mil, "guard")
    _add_stat(t, lord, "economy", -split_eco, "guard")
    _add_stat(t, lord, "stability", -FREE_CITY_LORD_LOSS, "guard-shock")
    events: list = []
    bridge = t.bridge if t.bridge is not None else getattr(world, "_agent_bridge", None)
    if world.agent_mode == "hybrid" and bridge is not None:
        events = bridge.apply_secession_transitions(
            lord, new, [region.name], new_idx, turn=world.turn, world=world, old_civ_id=lord_idx,
        )
    lord.regions = [r for r in lord.regions if r != region.name]
    region.controller = name
    region._seceded_this_turn = True
    sync_civ_population(lord, world)
    rels = world.relationships
    rels.setdefault(lord.name, {})[name] = Relationship(disposition=Disposition.HOSTILE)
    rels.setdefault(name, {})[lord.name] = Relationship(disposition=Disposition.HOSTILE)
    for other in world.civilizations:
        if other.name != lord.name:
            rels.setdefault(other.name, {})[name] = Relationship(disposition=Disposition.NEUTRAL)
            rels[name][other.name] = Relationship(disposition=Disposition.NEUTRAL)
    world.civilizations.append(new)
    t.index[name] = new_idx
    city.charter = FREE_CITY
    city.lord = new_idx
    city.grievance = 0.0
    city.unrest = _q(max(0.0, city.unrest - SUPPRESSED_UNREST))
    _bump(t.state, "free_cities")
    ev = _emit(t, "free_city", [lord.name, name],
               f"{city.name} throws off {lord.name}'s rule: the {name}",
               importance=8, region=region.name, causes=(revolt.event_id,))
    _note(city, world.turn, "free_city", ev.event_id)
    for e in events:
        t.events.append(e)


def _record_misfortune(t: _Tick, city: City, region, turn_events: list) -> None:
    """Epidemics and famine onsets in the city's region, at most one of a
    kind per MISFORTUNE_GAP turns."""
    turn = t.world.turn
    for ev in turn_events:
        if ev.region != region.name:
            continue
        if ev.event_type == "epidemic" and ev.importance >= MISFORTUNE_IMPORTANCE:
            kind = "plague"
        elif ev.event_type == "famine" and ev.episode != "tick":
            kind = "famine"
        else:
            continue
        last = next((h[0] for h in reversed(city.history) if h[1] == kind), None)
        if last is None or turn - last >= MISFORTUNE_GAP:
            _note(city, turn, kind, ev.event_id)


def _voice(t: _Tick) -> None:
    weight: dict[int, float] = {}
    for city in t.state.cities:
        if city.lord >= 0:
            weight[city.lord] = weight.get(city.lord, 0.0) + city.rank * (1.0 + city.charter / 2.0)
    for idx in sorted(weight):
        civ = t.civ(idx)
        if civ is None or not civ.regions:
            continue
        _shift_merchants(civ, min(VOICE_CAP, VOICE_PER_WEIGHT * weight[idx]))


# ---------------------------------------------------------------------------
# Hooks read by other systems
# ---------------------------------------------------------------------------

def pay_dues(world: "WorldState", acc) -> None:
    """Phase 2: dues assessed last turn, as ``keep`` treasury of each lord."""
    if not cities_on(world) or acc is None:
        return
    state = world.cities
    civs = world.civilizations
    for idx, owed in enumerate(state.owed):
        gross = owed + state.carry[idx]
        whole = int(gross)
        civ = civs[idx] if idx < len(civs) else None
        if civ is None or not civ.regions:
            state.carry[idx] = 0.0
            continue
        state.carry[idx] = round(gross - whole, 6)
        if whole > 0:
            acc.add(idx, civ, "treasury", whole, "keep")
            _bump(state, "dues", whole)
    state.owed = [0.0] * len(state.owed)


def region_pulls(world: "WorldState") -> list[float]:
    """``city_pull`` per region index (the region batch column)."""
    pulls = [0.0] * len(world.regions)
    if not cities_on(world):
        return pulls
    for city in world.cities.cities:
        if city.region < len(pulls):
            pulls[city.region] = max(pulls[city.region], city.pull)
    return pulls


def epidemic_susceptibility_factors(world: "WorldState") -> list[float]:
    """Per region: 1 + URBAN_SUSCEPTIBILITY x the share living in its cities."""
    urban = [0] * len(world.regions)
    for city in world.cities.cities:
        if city.region < len(urban):
            urban[city.region] += city.residents
    return [1.0 + URBAN_SUSCEPTIBILITY * min(1.0, urban[i] / max(1, r.population))
            for i, r in enumerate(world.regions)]


def credit_factor(world: "WorldState", civ_idx: int) -> float:
    """Domestic credit of a lord with chartered cities (merchant lenders)."""
    if not cities_on(world):
        return 1.0
    levels = sum(min(c.charter, SELF_GOVERNMENT) for c in world.cities.cities if c.lord == civ_idx)
    return min(CREDIT_CAP, 1.0 + CREDIT_PER_CHARTER * levels)


# ---------------------------------------------------------------------------
# Snapshot, history and metrics
# ---------------------------------------------------------------------------

def snapshot_summary(world: "WorldState") -> dict:
    """Per-turn summary for ``TurnSnapshot.cities``."""
    state = world.cities
    civs = world.civilizations
    regions = world.regions
    return {
        "cities": [
            {"id": c.settlement_id, "name": c.name,
             "region": regions[c.region].name if c.region < len(regions) else None,
             "lord": civs[c.lord].name if 0 <= c.lord < len(civs) else None,
             "rank": c.rank, "residents": c.residents, "wealth": round(c.wealth, 1),
             "charter": c.charter, "unrest": round(c.unrest, 2),
             "satisfaction": None if c.satisfaction is None else round(c.satisfaction, 2)}
            for c in state.cities
        ],
        "fallen": len(state.fallen),
        "counters": {k: state.counters.get(k, 0) for k in COUNTER_KEYS},
    }


def city_history(world: "WorldState", settlement_id: int) -> list[str]:
    """One line per recorded moment of a city, from the event timeline."""
    state = world.cities
    city = next((c for c in state.cities + state.fallen if c.settlement_id == settlement_id), None)
    if city is None:
        return []
    by_id = {ev.event_id: ev for ev in world.events_timeline if ev.event_id}
    lines = []
    for turn, kind, eid in city.history:
        ev = by_id.get(eid)
        lines.append(f"{turn}: {kind}: {ev.description}" if ev is not None else f"{turn}: {kind}")
    return lines


def extract_city_metrics(bundles: list[dict]) -> dict:
    """Per-run city metrics from bundles that carry ``history[n].cities``."""
    runs = []
    for bundle in bundles:
        rows = [h["cities"] for h in bundle.get("history", []) if h.get("cities")]
        if not rows:
            continue
        last = rows[-1]
        runs.append({
            "seed": bundle.get("metadata", {}).get("seed"),
            "cities_peak": max(len(r["cities"]) for r in rows),
            "great_cities_peak": max(sum(1 for c in r["cities"] if c["rank"] >= GREAT_CITY) for r in rows),
            "cities_final": len(last["cities"]),
            "fallen": last["fallen"],
            "counters": dict(last.get("counters", {})),
        })
    return {"runs": runs}
