"""Maritime layer: fleets, sea-zone control, blockade, naval campaigns,
piracy and colonization by sea.

Default off behind ``WorldState.maritime`` (CLI ``--maritime``). With the
switch off nothing in this module runs and every output is identical to the
simulation without it. See ``docs/integration/maritime.md``.

Sea model
    Procedural worlds use Geography 2.0's named sea zones; every sea lane
    (``WorldGeography.sea_lanes``) belongs to one zone. Template worlds have no
    sea zones, only the coast "clique" (every coast/river/maritime region
    adjacent to every other): each connected group of those regions becomes
    one derived zone and every edge between two of them a sea lane. The model
    is built once when the switch is turned on (adjacency never changes during
    a run) and saved on the world.

Per turn (``tick_maritime``, right after Phase 5 actions, before campaigns)
    1. fleets of fallen civs are dropped; measured sea trade and piracy since
       the last tick are consumed (piracy reports, treasury losses);
    2. upkeep (unpaid squadrons lose ships), then each coastal civ's naval
       programme commissions ships at its ports (treasury, and timber where
       the goods economy is physical);
    3. orders and one zone of movement per fleet (escort, war, colony, patrol);
    4. storms; naval battles between fleets of civs at war sharing a zone;
    5. zone control, blockades (closing an enemy's sea lanes) and pirates.

Consumers (each guarded by ``maritime_enabled``)
    trade routes and goods-economy boundary pairs skip blockaded lanes; the
    native merchant route graph drops them and carries a per-lane raid risk
    (the native ``Raid`` loss reason); the contact ledger's ``--agents off``
    route proxy is cut and skimmed; campaign armies cross sea lanes only with
    an escort or under their own control, landings fight through the normal
    battle code, and supply lines do not run through enemy-controlled zones;
    EXPAND reaches overseas coasts only where the civ has a fleet.

Identity: region = index in ``world.regions``, civ = index in
``world.civilizations``, zone = index in ``MaritimeState.zones``. All
randomness comes from ``random.Random(stable_hash_int("maritime", ...))``.
"""
from __future__ import annotations

import math
import random
from collections import deque
from typing import TYPE_CHECKING, Callable, Iterable

from chronicler.maritime_state import (
    CONTESTED, CONTROLLED, COUNTER_KEYS, UNCONTESTED,
    Blockade, Colony, EscortRequest, Fleet, MaritimeState, NavalBattle, SeaZoneState,
)
from chronicler.utils import stable_hash_int

if TYPE_CHECKING:  # pragma: no cover
    from chronicler.models import Civilization, Event, Region, WorldState


# ---------------------------------------------------------------------------
# Parameters ([CALIBRATE]; documented in docs/integration/maritime.md)
# ---------------------------------------------------------------------------

#: Default for worlds created by the CLI/batch/live entry points.
DEFAULT_ENABLED_FOR_NEW_WORLDS = False

# Ships and fleets.
SHIP_COST = 8                  # treasury per ship
SHIP_TIMBER = 2.0              # timber per ship where stocks are physical (hybrid)
TIMBER_PRICE = 3               # treasury per timber unit bought in (or not stocked)
UPKEEP_SHIPS_PER_COIN = 2      # one treasury per two ships per turn (ceiling)
UNPAID_LOSS_SHARE = 0.10       # ships laid up per unpaid turn
BUILD_PER_TURN = 4
BUILD_SHARE = 0.3              # share of spare treasury a programme spends per turn
TREASURY_RESERVE = 30
MAX_FLEETS_PER_CIV = 3
SHIPS_PER_PORT = 6
MAX_SHIPS_PER_CIV = 60
MIN_FLEET_SHIPS = 2
PATROL_SHIPS = 4
COLONY_SHIPS = 3
WAR_SHIPS = 6
WAR_SHIPS_MATCH = 1.25         # ships wanted per enemy ship in a zone at war
FLEET_RANGE = 3                # zone hops from home waters (+ navigation level)
SOLDIERS_PER_SHIP = 20         # escort capacity per ship per turn

# Fleet quality.
ERA_QUALITY_STEP = 0.12
NAVIGATION_QUALITY = 0.10      # per navigation technique level
NAVAL_POWER_FOCUS = 1.25       # tech focus "naval_power"
HOME_WATERS = 1.10             # fighting in a zone with own ports

# Naval battles.
DECISIVE_RATIO = 1.2
NAVAL_POINTS_BASE = 4
NAVAL_POINTS_SCALE = 8
REFIT_TURNS = 3
EVADE_RATIO = 1.5
NAVAL_DEFEAT_STABILITY = 2
NAVAL_WEARINESS = 0.5

# Storms.
STORM_CHANCE = 0.01
STORM_KIND = {"ocean": 1.5, "sea": 1.0, "lake": 0.3, "coast": 0.8}
STORM_WINTER = 2.0
STORM_NAVIGATION = 0.15        # chance reduction per navigation level (floor 0.3x)
STORM_NAVIGATION_FOCUS = 0.7   # tech focus "navigation"
STORM_LOSS = (0.15, 0.35)

# Zone control.
CONTROL_RATIO = 2.0            # strength over all hostile strength in the zone
MIN_CONTROL_SHIPS = 3

# Piracy.
PIRATE_START = {"ocean": 0.05, "sea": 0.05, "coast": 0.05, "lake": 0.0}
PIRATE_MAX = {"lake": 0.3}
PIRATE_GROWTH = 0.03           # uncontested, at full traffic
PIRATE_GROWTH_CONTESTED = 0.04
PIRATE_DECAY = 0.01            # uncontested without traffic
PIRATE_SUPPRESSION = 0.25      # controlled zones
PIRATE_TRAFFIC_REF = 1.0       # sea cargo per turn that counts as full traffic
PIRACY_MAX_SKIM = 0.25         # share of sea cargo taken at full pirate pressure
PIRATE_PATROL_MIN = 0.15
PIRACY_TREASURY_PER_UNIT = 2.0
PIRACY_EVENT_MIN = 0.5

# Campaigns.
LANDING_POWER = 0.85           # an army fights at this power the turn it lands

_MISSION_RANK = {"escort": 0, "war": 1, "colony": 2, "patrol": 3}


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

def maritime_enabled(world) -> bool:
    """True only for a real maritime state (mocks and ``None`` read as off)."""
    return isinstance(getattr(world, "maritime", None), MaritimeState)


def set_maritime_enabled(world: "WorldState", enabled: bool) -> None:
    """Enable (building the sea model) or disable the maritime layer."""
    if enabled:
        if world.maritime is None:
            world.maritime = build_sea_model(world)
        return
    world.maritime = None


def navigation_level(world, civ) -> int:
    """The civ's navigation technique level; 0 (neutral) when no registry exists.

    The technique registry is owned by another line of work. This is the only
    place maritime reads it, so the rest of the layer is neutral until a
    registry exposing ``chronicler.techniques.technique_level(world, civ,
    name)`` lands.
    """
    try:
        from chronicler import techniques  # type: ignore[attr-defined]
    except ImportError:
        return 0
    getter = getattr(techniques, "technique_level", None)
    if getter is None:
        return 0
    return max(0, int(getter(world, civ, "navigation") or 0))


# ---------------------------------------------------------------------------
# Sea model
# ---------------------------------------------------------------------------

def _components(n: int, neighbors: list[set[int]], members: Iterable[int] | None = None) -> list[list[int]]:
    pool = sorted(range(n) if members is None else members)
    allowed = set(pool)
    seen: set[int] = set()
    comps: list[list[int]] = []
    for start in pool:
        if start in seen:
            continue
        seen.add(start)
        comp = [start]
        queue = deque([start])
        while queue:
            cur = queue.popleft()
            for nb in sorted(neighbors[cur]):
                if nb in allowed and nb not in seen:
                    seen.add(nb)
                    comp.append(nb)
                    queue.append(nb)
        comps.append(sorted(comp))
    return comps


def _neighbor_sets(world) -> list[set[int]]:
    index = {r.name: i for i, r in enumerate(world.regions)}
    nbs: list[set[int]] = [set() for _ in world.regions]
    for i, region in enumerate(world.regions):
        for adj in region.adjacencies:
            j = index.get(adj)
            if j is not None and j != i:
                nbs[i].add(j)
                nbs[j].add(i)
    return nbs


def _zone_title(word: str) -> str:
    return f"the {word} Sea"


def _derived_zones(world, nbs: list[set[int]]) -> tuple[list[SeaZoneState], list[tuple[int, int, int]]]:
    """Template worlds: one zone per connected group of coast-clique regions."""
    from chronicler.adjacency import _is_sea_route_eligible
    eligible = [i for i, r in enumerate(world.regions) if _is_sea_route_eligible(r)]
    eligible_set = set(eligible)
    groups = [g for g in _components(len(world.regions), nbs, eligible) if len(g) >= 2]
    zones: list[SeaZoneState] = []
    lanes: list[tuple[int, int, int]] = []
    used: set[str] = set()
    for zi, group in enumerate(groups):
        word = world.regions[group[0]].name.split()[0]
        name = _zone_title(word)
        n = 2
        while name in used:
            name = f"{_zone_title(word)} {n}"
            n += 1
        used.add(name)
        zones.append(SeaZoneState(name=name, kind="coast", ports=list(group),
                                  pirates=PIRATE_START["coast"]))
        members = set(group)
        for a in group:
            for b in sorted(nbs[a]):
                if b > a and b in members and b in eligible_set:
                    lanes.append((a, b, zi))
    return zones, sorted(lanes)


def _procedural_zones(world) -> tuple[list[SeaZoneState], list[tuple[int, int, int]]]:
    geo = world.geography
    index = {r.name: i for i, r in enumerate(world.regions)}
    zone_index = {z.name: i for i, z in enumerate(geo.sea_zones)}
    zones = [
        SeaZoneState(
            name=z.name, kind=z.kind,
            ports=sorted(index[n] for n in z.coastal_regions if n in index),
            neighbors=sorted(zone_index[n] for n in z.neighbors if n in zone_index),
            pirates=PIRATE_START.get(z.kind, 0.0),
        )
        for z in geo.sea_zones
    ]
    port_sets = [set(z.ports) for z in zones]
    lanes: set[tuple[int, int, int]] = set()
    for a_name, b_name in geo.sea_lanes:
        a, b = index.get(a_name), index.get(b_name)
        if a is None or b is None or a == b:
            continue
        a, b = min(a, b), max(a, b)
        common = [zi for zi, ports in enumerate(port_sets) if a in ports and b in ports]
        if common:
            zone = common[0]
        else:
            ra, rb = world.regions[a], world.regions[b]
            mx = ((ra.x or 0.0) + (rb.x or 0.0)) / 2.0
            my = ((ra.y or 0.0) + (rb.y or 0.0)) / 2.0
            cands = [zi for zi, ports in enumerate(port_sets) if a in ports or b in ports]
            cands = cands or list(range(len(zones)))
            sz = geo.sea_zones
            zone = min(cands, key=lambda zi: (round((sz[zi].x - mx) ** 2 + (sz[zi].y - my) ** 2, 6), zi))
        lanes.add((a, b, zone))
    return zones, sorted(lanes)


def build_sea_model(world: "WorldState") -> MaritimeState:
    """Zones, lanes and land masses for the world as it stands."""
    nbs = _neighbor_sets(world)
    geo = getattr(world, "geography", None)
    derived = not (geo is not None and geo.sea_zones)
    zones, lanes = _derived_zones(world, nbs) if derived else _procedural_zones(world)
    land_nbs = [set(s) for s in nbs]
    for a, b, _ in lanes:
        land_nbs[a].discard(b)
        land_nbs[b].discard(a)
    landmass = [0] * len(world.regions)
    for k, comp in enumerate(_components(len(world.regions), land_nbs)):
        for i in comp:
            landmass[i] = k
    n = len(zones)
    return MaritimeState(
        derived=derived, zones=zones, lanes=lanes, landmass=landmass,
        pending_sea_trade=[0.0] * n, pending_piracy=[0.0] * n,
        last_sea_trade=[0.0] * n, last_piracy=[0.0] * n,
    )


# ---------------------------------------------------------------------------
# Derived lookups (never serialized; rebuilt lazily)
# ---------------------------------------------------------------------------

class _Lookups:
    __slots__ = ("lane_zone", "zone_lanes", "region_zones", "zone_dist", "port_sets",
                 "blocked_key", "blocked", "land")

    def __init__(self, state: MaritimeState) -> None:
        self.lane_zone: dict[tuple[int, int], int] = {}
        self.zone_lanes: list[list[tuple[int, int]]] = [[] for _ in state.zones]
        for a, b, z in state.lanes:
            self.lane_zone[(a, b)] = z
            self.lane_zone[(b, a)] = z
            if 0 <= z < len(self.zone_lanes):
                self.zone_lanes[z].append((a, b))
        self.region_zones: dict[int, list[int]] = {}
        for zi, zone in enumerate(state.zones):
            for r in zone.ports:
                self.region_zones.setdefault(r, []).append(zi)
        self.port_sets = [frozenset(z.ports) for z in state.zones]
        self.zone_dist: list[dict[int, int]] = []
        for zi in range(len(state.zones)):
            dist = {zi: 0}
            queue = deque([zi])
            while queue:
                cur = queue.popleft()
                for nb in state.zones[cur].neighbors:
                    if nb not in dist:
                        dist[nb] = dist[cur] + 1
                        queue.append(nb)
            self.zone_dist.append(dist)
        self.blocked_key = None
        self.blocked: frozenset = frozenset()
        self.land: list[tuple[int, ...]] | None = None  # adjacency minus sea lanes


def _lookups(state: MaritimeState) -> _Lookups:
    """Static lookups (zones and lanes never change after the model is built),
    plus the blocked-lane set, refreshed whenever ``state.blocked`` changes."""
    slot = state._cache
    if slot.value is None:
        slot.value = _Lookups(state)
    look = slot.value
    bkey = tuple(state.blocked)
    if look.blocked_key != bkey:
        look.blocked_key = bkey
        blocked = set()
        for a, b in state.blocked:
            blocked.add((a, b))
            blocked.add((b, a))
        look.blocked = frozenset(blocked)
    return look


def _land_graph(world) -> list[tuple[int, ...]]:
    look = _lookups(world.maritime)
    if look.land is None:
        nbs = _neighbor_sets(world)
        look.land = [tuple(sorted(j for j in nbs[i] if (i, j) not in look.lane_zone))
                     for i in range(len(nbs))]
    return look.land


def land_reachable(world, civ_name: str) -> set[int]:
    """Unclaimed regions the civ's settlers can walk to: over land edges,
    through unclaimed land only (never across water or foreign territory)."""
    land = _land_graph(world)
    regions = world.regions
    sources = [i for i, r in enumerate(regions) if r.controller == civ_name]
    seen = set(sources)
    queue = deque(sources)
    out: set[int] = set()
    while queue:
        cur = queue.popleft()
        for nb in land[cur]:
            if nb in seen:
                continue
            seen.add(nb)
            if regions[nb].controller is None:
                out.add(nb)
                queue.append(nb)
    return out


def lane_zone(world, a: int, b: int) -> int | None:
    """Zone of the sea lane between region indices ``a`` and ``b`` (None: land edge)."""
    return _lookups(world.maritime).lane_zone.get((a, b))


def is_blocked(world, a: int, b: int) -> bool:
    return (a, b) in _lookups(world.maritime).blocked


def skim_rate(world, zone: int) -> float:
    """Share of sea cargo pirates take in ``zone`` (0 in a controlled zone)."""
    z = world.maritime.zones[zone]
    if z.status == CONTROLLED:
        return 0.0
    return round(PIRACY_MAX_SKIM * z.pirates, 6)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _living(world, ci: int) -> bool:
    return 0 <= ci < len(world.civilizations) and bool(world.civilizations[ci].regions)


def _war_pairs(world) -> set[frozenset]:
    return {frozenset((a, b)) for a, b in world.active_wars}


def _at_war(pairs: set[frozenset], a: str, b: str) -> bool:
    return frozenset((a, b)) in pairs


def _own_port(region, civ_name: str) -> bool:
    return region.controller == civ_name and region.occupied_by in (None, civ_name)


def _holds(region, civ_name: str) -> bool:
    if region.occupied_by is not None:
        return region.occupied_by == civ_name
    return region.controller == civ_name


def _rng(world, namespace: str, *parts) -> random.Random:
    return random.Random(stable_hash_int("maritime", namespace, world.seed, world.turn, *parts))


def _bump(state: MaritimeState, key: str, amount: float = 1) -> None:
    value = state.counters.get(key, 0) + amount
    state.counters[key] = round(value, 4) if isinstance(value, float) else value


def era_index(civ) -> int:
    from chronicler.models import TechEra
    return list(TechEra).index(civ.tech_era)


def fleet_quality(world, civ) -> float:
    q = 1.0 + ERA_QUALITY_STEP * era_index(civ)
    q *= 1.0 + NAVIGATION_QUALITY * navigation_level(world, civ)
    if civ.active_focus == "naval_power":
        q *= NAVAL_POWER_FOCUS
    return q


def _zone_anchor(world, zone: SeaZoneState) -> str | None:
    return world.regions[zone.ports[0]].name if zone.ports else None


def _fleets_in(state: MaritimeState, zone: int, civ: int | None = None) -> list[Fleet]:
    return [f for f in state.fleets if f.zone == zone and f.ships > 0 and (civ is None or f.civ == civ)]


def _ships_in(state: MaritimeState, zone: int, civ: int) -> int:
    return sum(f.ships for f in state.fleets if f.zone == zone and f.civ == civ)


class _Tick:
    """Duck-types the ``WarContext`` subset the stat helpers use."""

    def __init__(self, world, acc, agent_bridge) -> None:
        self.world = world
        self.acc = acc
        self.bridge = agent_bridge
        self.events: list = []
        self.state: MaritimeState = world.maritime
        self.look = _lookups(world.maritime)
        self.wars = _war_pairs(world)
        self.battle_zones: dict[int, str] = {}  # zone -> naval battle event id this turn


def _emit(t: _Tick, event_type: str, actors: list[str], description: str, *,
          importance: int = 5, region: str | None = None, causes=(), observe: bool = True) -> "Event":
    from chronicler import provenance
    from chronicler.models import Event
    ev = Event(turn=t.world.turn, event_type=event_type, actors=list(actors),
               description=description, importance=importance, region=region)
    provenance.cite(ev, *causes)
    if observe:
        # Same-tick chains (battle -> control -> blockade) resolve in order.
        provenance.observe_now(t.world, ev)
    t.events.append(ev)
    return ev


def _war_cause(world, a: str, b: str) -> str | None:
    from chronicler import provenance
    return provenance.recall(world, provenance.war_key(a, b))


def _spend(t: _Tick, civ, amount: int) -> int:
    from chronicler.war.common import spend
    return spend(t, civ, int(amount))


# ---------------------------------------------------------------------------
# The per-turn tick
# ---------------------------------------------------------------------------

def tick_maritime(world: "WorldState", acc=None, agent_bridge=None) -> list["Event"]:
    """Advance the maritime layer one turn (after Phase 5). Returns its events."""
    if not maritime_enabled(world) or not world.regions:
        return []
    t = _Tick(world, acc, agent_bridge)
    state = t.state
    _validate_fleets(t)
    traffic = _consume_measurements(t)
    _upkeep(t)
    needs = {ci: _naval_needs(t, ci) for ci in range(len(world.civilizations)) if _living(world, ci)}
    _build_ships(t, needs)
    _orders_and_moves(t, needs)
    state.escort_requests = []  # consumed; the campaign tick files this turn's
    _storms(t)
    _naval_battles(t)
    _update_control(t)
    _update_blockades(t)
    _update_pirates(t, traffic)
    # Landings older than this turn no longer weaken their army.
    state.landings = {k: v for k, v in sorted(state.landings.items()) if v >= world.turn}
    return t.events


def _validate_fleets(t: _Tick) -> None:
    world, state = t.world, t.state
    kept = []
    for fleet in state.fleets:
        if not _living(world, fleet.civ) or fleet.ships < MIN_FLEET_SHIPS:
            continue
        civ = world.civilizations[fleet.civ]
        home = world.regions[fleet.home_port] if 0 <= fleet.home_port < len(world.regions) else None
        if home is None or not _own_port(home, civ.name):
            # Re-home to the civ's nearest remaining port (zone hops, then index).
            best = None
            for zi, zone in enumerate(state.zones):
                for r in zone.ports:
                    if _own_port(world.regions[r], civ.name):
                        d = t.look.zone_dist[fleet.zone].get(zi, 99)
                        key = (d, r)
                        if best is None or key < best[0]:
                            best = (key, r)
            if best is not None:
                fleet.home_port = best[1]
        kept.append(fleet)
    state.fleets = kept


def _consume_measurements(t: _Tick) -> list[float]:
    """Piracy reports and losses, and the traffic pirates feed on."""
    world, state = t.world, t.state
    n = len(state.zones)
    traffic = list(state.pending_sea_trade) + [0.0] * (n - len(state.pending_sea_trade))
    piracy = list(state.pending_piracy) + [0.0] * (n - len(state.pending_piracy))
    state.last_sea_trade = [round(v, 4) for v in traffic[:n]]
    state.last_piracy = [round(v, 4) for v in piracy[:n]]
    _bump(state, "sea_trade", round(sum(traffic), 4))
    _bump(state, "piracy_losses", round(sum(piracy), 4))
    for zi in range(n):
        loss = piracy[zi]
        if loss < PIRACY_EVENT_MIN:
            continue
        zone = state.zones[zi]
        victims = sorted({world.regions[p].controller for p in zone.ports
                          if world.regions[p].controller is not None})
        _emit(t, "piracy", victims,
              f"Raiders in {zone.name} seized {loss:.1f} loads of cargo.",
              importance=4, region=_zone_anchor(world, zone),
              causes=(zone.status_event_id,), observe=False)
    for ci in sorted(state.pending_piracy_civ):
        loss = state.pending_piracy_civ[ci]
        if not _living(world, ci):
            continue
        # Whole coins, plus one more with the fractional chance (so small
        # per-turn losses still cost something on average).
        whole, frac = divmod(loss * PIRACY_TREASURY_PER_UNIT, 1.0)
        amount = int(whole) + (1 if _rng(world, "piracy", ci).random() < frac else 0)
        if amount > 0:
            paid = _spend(t, world.civilizations[ci], amount)
            _bump(state, "piracy_treasury", paid)
    state.pending_sea_trade = [0.0] * n
    state.pending_piracy = [0.0] * n
    state.pending_piracy_civ = {}
    return traffic[:n]


def _upkeep(t: _Tick) -> None:
    world, state = t.world, t.state
    for fleet in sorted(state.fleets, key=lambda f: f.fleet_id):
        civ = world.civilizations[fleet.civ]
        cost = -(-fleet.ships // UPKEEP_SHIPS_PER_COIN)
        paid = _spend(t, civ, cost)
        _bump(state, "treasury_spent", paid)
        if paid < cost:
            lost = max(1, int(math.ceil(fleet.ships * UNPAID_LOSS_SHARE)))
            fleet.ships = max(0, fleet.ships - lost)
            _bump(state, "ships_lost_upkeep", lost)
    state.fleets = [f for f in state.fleets if f.ships >= MIN_FLEET_SHIPS]


# --- naval programme ---------------------------------------------------------------

def _ports_of(t: _Tick, civ_name: str) -> dict[int, list[int]]:
    """Zone -> own unoccupied ports of the civ."""
    out: dict[int, list[int]] = {}
    for zi, zone in enumerate(t.state.zones):
        ports = [r for r in zone.ports if _own_port(t.world.regions[r], civ_name)]
        if ports:
            out[zi] = ports
    return out


def _fleet_range(world, civ) -> int:
    return FLEET_RANGE + navigation_level(world, civ)


def _reach(t: _Tick, ci: int, port_zones: Iterable[int]) -> set[int]:
    civ = t.world.civilizations[ci]
    rng = _fleet_range(t.world, civ)
    reach: set[int] = set()
    for z in port_zones:
        reach.update(k for k, d in t.look.zone_dist[z].items() if d <= rng)
    reach.update(f.zone for f in t.state.fleets if f.civ == ci)
    return reach


def _colony_targets(world, zone: int, walkable: set[int]) -> list[int]:
    """Unclaimed coastal regions of ``zone`` the civ cannot walk to."""
    return [r for r in world.maritime.zones[zone].ports
            if world.regions[r].controller is None and r not in walkable]


def _naval_needs(t: _Tick, ci: int) -> dict[int, tuple[int, str]]:
    """Zone -> (ships wanted, mission) for one civ."""
    from chronicler.tuning import K_EXPAND_MILITARY_THRESHOLD, get_override
    world, state = t.world, t.state
    civ = world.civilizations[ci]
    ports = _ports_of(t, civ.name)
    if not ports and not any(f.civ == ci for f in state.fleets):
        return {}
    reach = _reach(t, ci, ports)
    enemies = {i for i, c in enumerate(world.civilizations)
               if i != ci and c.regions and _at_war(t.wars, civ.name, c.name)}
    escort: dict[int, int] = {}
    for req in state.escort_requests:
        if req.civ == ci:
            escort[req.zone] = escort.get(req.zone, 0) + req.ships
    walkable = land_reachable(world, civ.name)
    expand_ok = (civ.military >= int(get_override(world, K_EXPAND_MILITARY_THRESHOLD, 30))
                 and not walkable)
    needs: dict[int, tuple[int, str]] = {}
    for z in sorted(reach):
        zone = state.zones[z]
        want, why = 0, "patrol"
        if z in ports and state.last_sea_trade[z] > 0 and zone.pirates >= PIRATE_PATROL_MIN:
            want = PATROL_SHIPS  # raiders threaten the civ's sea lanes
        if expand_ok and _colony_targets(world, z, walkable) and want < COLONY_SHIPS:
            want, why = COLONY_SHIPS, "colony"
        if enemies:
            enemy_ships = sum(f.ships for f in state.fleets if f.zone == z and f.civ in enemies)
            enemy_ports = any(_holds(world.regions[r], world.civilizations[e].name)
                              for r in zone.ports for e in enemies)
            if enemy_ships or enemy_ports:
                war_want = WAR_SHIPS + int(math.ceil(WAR_SHIPS_MATCH * enemy_ships))
                if war_want > want:
                    want, why = war_want, "war"
        if escort.get(z, 0) > 0:
            esc = escort[z]
            if esc >= want or why == "patrol":
                want, why = max(want, esc), "escort"
        if want:
            needs[z] = (want, why)
    return needs


def _max_ships(t: _Tick, civ) -> int:
    ports = sum(len(p) for p in _ports_of(t, civ.name).values())
    return min(MAX_SHIPS_PER_CIV, SHIPS_PER_PORT * ports + max(0, civ.military) // 5
               + 2 * navigation_level(t.world, civ))


def _free_timber(t: _Tick, civ) -> list[tuple[int, float]]:
    """(region index, free timber) for the civ's regions, physical stocks only."""
    world = t.world
    if world.agent_mode != "hybrid" or t.bridge is None:
        return []
    from chronicler.mutual_aid import read_stockpile_commitments
    commitments = read_stockpile_commitments(world, t.bridge._sim)
    out = []
    for i, region in enumerate(world.regions):
        if region.controller != civ.name:
            continue
        free = region.stockpile.goods.get("timber", 0.0) - commitments.get(region.name, {}).get("timber", 0.0)
        if free > 1e-9:
            out.append((i, free))
    return out


def _build_ships(t: _Tick, needs: dict[int, dict[int, tuple[int, str]]]) -> None:
    from chronicler.war.common import projected_treasury
    world, state = t.world, t.state
    for ci in sorted(needs):
        need = needs[ci]
        if not need:
            continue
        civ = world.civilizations[ci]
        ports = _ports_of(t, civ.name)
        if not ports:
            continue
        owned = sum(f.ships for f in state.fleets if f.civ == ci)
        wanted = min(sum(w for w, _ in need.values()), _max_ships(t, civ))
        count = min(BUILD_PER_TURN, wanted - owned)
        if count <= 0:
            continue
        spare = projected_treasury(t, civ) - TREASURY_RESERVE
        if spare <= 0:
            continue
        # Timber comes from physical stocks where the goods economy keeps them
        # (hybrid); a shortfall, or every plank where no stocks exist, is
        # bought in coin.
        timber = _free_timber(t, civ)
        stock = sum(v for _, v in timber)
        budget = int(spare * BUILD_SHARE)
        affordable = 0
        for k in range(1, count + 1):
            timber_short = max(0.0, k * SHIP_TIMBER - stock)
            cost = k * SHIP_COST + int(math.ceil(timber_short * TIMBER_PRICE))
            if cost <= budget:
                affordable = k
        if affordable <= 0:
            continue
        # Shipyard: the zone with the largest unmet need that has a port.
        def unmet(z: int) -> int:
            return need[z][0] - _ships_in(state, z, ci)
        port_needs = [z for z in need if z in ports and unmet(z) > 0]
        if port_needs:
            target = yard_zone = min(port_needs, key=lambda z: (_MISSION_RANK[need[z][1]], -unmet(z), z))
        else:
            target = min(need, key=lambda z: (_MISSION_RANK[need[z][1]], -unmet(z), z))
            yard_zone = min(ports, key=lambda z: (t.look.zone_dist[z].get(target, 99), z))
        port = max(ports[yard_zone], key=lambda r: (world.regions[r].population, -r))
        fleet = _receiving_fleet(t, ci, yard_zone)
        if fleet is None or (fleet.fleet_id == 0 and affordable < MIN_FLEET_SHIPS):
            continue  # a new squadron waits until it can sail at strength
        # Pay: timber from stocks where they exist (port first), the rest in coin.
        timber_needed = affordable * SHIP_TIMBER
        used = 0.0
        if timber:
            order = sorted(timber, key=lambda iv: (iv[0] != port, iv[0]))
            for ri, free in order:
                take = min(free, timber_needed - used)
                if take <= 0:
                    break
                goods = world.regions[ri].stockpile.goods
                goods["timber"] = round(goods.get("timber", 0.0) - take, 6)
                used += take
        coin = affordable * SHIP_COST + int(math.ceil(max(0.0, timber_needed - used) * TIMBER_PRICE))
        paid = _spend(t, civ, coin)
        _bump(state, "treasury_spent", paid)
        _bump(state, "timber_spent", round(used, 4))
        _bump(state, "ships_built", affordable)
        if fleet.fleet_id == 0:
            _commission(t, fleet, civ, port, yard_zone, affordable, need[target][1])
        else:
            fleet.ships += affordable


def _receiving_fleet(t: _Tick, ci: int, zone: int) -> Fleet | None:
    """The civ's fleet in ``zone`` (largest), a new one, or its nearest fleet."""
    state = t.state
    here = [f for f in state.fleets if f.civ == ci and f.zone == zone]
    if here:
        return max(here, key=lambda f: (f.ships, -f.fleet_id))
    mine = [f for f in state.fleets if f.civ == ci]
    if len(mine) < MAX_FLEETS_PER_CIV:
        return Fleet(fleet_id=0, name="", civ=ci, zone=zone, home_port=-1, ships=0, built_turn=t.world.turn)
    reachable = [f for f in mine if t.look.zone_dist[zone].get(f.zone) is not None]
    if not reachable:
        return None
    return min(reachable, key=lambda f: (t.look.zone_dist[zone][f.zone], f.fleet_id))


_FLEET_ORDINALS = ("First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh",
                   "Eighth", "Ninth", "Tenth")


def _commission(t: _Tick, fleet: Fleet, civ, port: int, zone: int, ships: int, mission: str) -> None:
    world, state = t.world, t.state
    ci = fleet.civ
    n = state.fleet_counts.get(ci, 0)
    state.fleet_counts[ci] = n + 1
    ordinal = _FLEET_ORDINALS[n] if n < len(_FLEET_ORDINALS) else f"{n + 1}th"
    fleet.fleet_id = state.next_fleet_id
    state.next_fleet_id += 1
    fleet.name = f"the {ordinal} Fleet of {civ.name}"
    fleet.home_port = port
    fleet.ships = ships
    fleet.mission = mission
    zone_name = state.zones[zone].name
    why = {"war": "for war", "escort": "to carry its armies", "colony": "to seek new shores",
           "patrol": "to guard its sea lanes"}.get(mission, "")
    causes = []
    if mission == "war":
        for e in sorted(world.civilizations, key=lambda c: c.name):
            if e.regions and _at_war(t.wars, civ.name, e.name):
                causes.append(_war_cause(world, civ.name, e.name))
    if mission == "patrol" and state.zones[zone].pirates >= PIRATE_PATROL_MIN:
        causes.append(state.zones[zone].status_event_id or None)
    ev = _emit(t, "fleet_commissioned", [civ.name],
               f"{civ.name} commissions {fleet.name} ({ships} ships) at {world.regions[port].name} "
               f"in {zone_name} {why}.".replace(" .", "."),
               importance=4, region=world.regions[port].name, causes=causes)
    fleet.event_id = ev.event_id
    state.fleets.append(fleet)
    _bump(state, "fleets_commissioned")


# --- orders and movement ---------------------------------------------------------------

def _strength(world, state: MaritimeState, zone: int, civs: Iterable[int]) -> float:
    total = 0.0
    for ci in civs:
        ships = _ships_in(state, zone, ci)
        if ships:
            total += ships * fleet_quality(world, world.civilizations[ci])
    return total


def _hostile_civs(t: _Tick, ci: int) -> list[int]:
    name = t.world.civilizations[ci].name
    return [i for i, c in enumerate(t.world.civilizations)
            if i != ci and c.regions and _at_war(t.wars, name, c.name)]


def _step_toward(t: _Tick, fleet: Fleet, target: int) -> None:
    if fleet.zone == target:
        return
    zones = t.state.zones
    best = None
    for nb in zones[fleet.zone].neighbors:
        d = t.look.zone_dist[nb].get(target)
        if d is None:
            continue
        key = (d, nb)
        if best is None or key < best[0]:
            best = (key, nb)
    if best is not None:
        fleet.zone = best[1]


def _home_zone(t: _Tick, fleet: Fleet) -> int:
    zones = t.look.region_zones.get(fleet.home_port, [])
    if not zones:
        return fleet.zone
    return min(zones, key=lambda z: (t.look.zone_dist[fleet.zone].get(z, 99), z))


def _orders_and_moves(t: _Tick, needs: dict[int, dict[int, tuple[int, str]]]) -> None:
    world, state = t.world, t.state
    by_civ: dict[int, list[Fleet]] = {}
    for f in state.fleets:
        by_civ.setdefault(f.civ, []).append(f)
    for ci in sorted(by_civ):
        civ = world.civilizations[ci]
        need = needs.get(ci, {})
        hostile = _hostile_civs(t, ci)
        q = fleet_quality(world, civ)
        rng_hops = _fleet_range(world, civ)
        plan = sorted(need.items(), key=lambda kv: (_MISSION_RANK[kv[1][1]], -kv[1][0], kv[0]))
        alloc: dict[int, int] = {}
        for fleet in sorted(by_civ[ci], key=lambda f: (-f.ships, f.fleet_id)):
            home = _home_zone(t, fleet)
            if fleet.refit_until >= world.turn:
                fleet.mission = "refit"
                _step_toward(t, fleet, home)
                continue
            best = None
            for z, (want, why) in plan:
                if alloc.get(z, 0) >= want:
                    continue
                d = t.look.zone_dist[fleet.zone].get(z)
                if d is None or d > rng_hops:
                    continue
                enemy = _strength(world, state, z, hostile)
                ours = (alloc.get(z, 0) + fleet.ships) * q
                if enemy > EVADE_RATIO * ours and z != home:
                    continue
                key = (_MISSION_RANK[why], d, z)
                if best is None or key < best[0]:
                    best = (key, z, why)
            if best is None:
                fleet.mission = "patrol"
                _step_toward(t, fleet, home)
                continue
            _, z, why = best
            alloc[z] = alloc.get(z, 0) + fleet.ships
            fleet.mission = why
            _step_toward(t, fleet, z)


# --- storms ----------------------------------------------------------------------------

def _storms(t: _Tick) -> None:
    from chronicler.resources import get_season_id
    world, state = t.world, t.state
    winter = get_season_id(world.turn) == 3
    for fleet in sorted(state.fleets, key=lambda f: f.fleet_id):
        civ = world.civilizations[fleet.civ]
        zone = state.zones[fleet.zone]
        chance = STORM_CHANCE * STORM_KIND.get(zone.kind, 1.0) * (STORM_WINTER if winter else 1.0)
        chance *= max(0.3, 1.0 - STORM_NAVIGATION * navigation_level(world, civ))
        if civ.active_focus == "navigation":
            chance *= STORM_NAVIGATION_FOCUS
        rng = _rng(world, "storm", fleet.fleet_id)
        if rng.random() >= chance:
            continue
        lost = min(fleet.ships, max(1, int(round(fleet.ships * rng.uniform(*STORM_LOSS)))))
        fleet.ships -= lost
        _bump(state, "ships_lost_storm", lost)
        sunk = fleet.ships < MIN_FLEET_SHIPS
        _emit(t, "fleet_storm", [civ.name],
              f"A storm in {zone.name} sank {lost} ships of {fleet.name}"
              + ("; the fleet is lost." if sunk else "."),
              importance=5 if sunk else 3, region=_zone_anchor(world, zone),
              causes=(fleet.event_id,))
        if sunk:
            _bump(state, "fleets_sunk")
    state.fleets = [f for f in state.fleets if f.ships >= MIN_FLEET_SHIPS]


# --- naval battles ---------------------------------------------------------------------

def _split(total: int, weights: list[int]) -> list[int]:
    s = sum(weights)
    if total <= 0 or s <= 0:
        return [0] * len(weights)
    raw = [total * w / s for w in weights]
    base = [int(x) for x in raw]
    rem = total - sum(base)
    order = sorted(range(len(weights)), key=lambda i: (-(raw[i] - base[i]), i))
    for i in order[:rem]:
        base[i] += 1
    return [min(b, w) for b, w in zip(base, weights)]


def _side_power(t: _Tick, ci: int, fleets: list[Fleet], zone: int) -> float:
    world = t.world
    civ = world.civilizations[ci]
    power = sum(f.ships for f in fleets) * fleet_quality(world, civ)
    if any(_own_port(world.regions[r], civ.name) for r in t.state.zones[zone].ports):
        power *= HOME_WATERS
    return power


def _naval_battles(t: _Tick) -> None:
    world, state = t.world, t.state
    for zi in range(len(state.zones)):
        present = sorted({f.civ for f in _fleets_in(state, zi)})
        fought: set[int] = set()
        for i, a in enumerate(present):
            for b in present[i + 1:]:
                if a in fought or b in fought:
                    continue
                ca, cb = world.civilizations[a], world.civilizations[b]
                if not _at_war(t.wars, ca.name, cb.name):
                    continue
                _fight(t, zi, a, b)
                fought.update((a, b))
    state.fleets = [f for f in state.fleets if f.ships >= MIN_FLEET_SHIPS]


def _attacker_defender(t: _Tick, zone: int, a: int, b: int) -> tuple[int, int]:
    world = t.world
    ca, cb = world.civilizations[a], world.civilizations[b]
    ports = t.state.zones[zone].ports
    a_home = any(_own_port(world.regions[r], ca.name) for r in ports)
    b_home = any(_own_port(world.regions[r], cb.name) for r in ports)
    if a_home != b_home:
        return (b, a) if a_home else (a, b)
    from chronicler.war.common import war_for
    from chronicler.war.peace import war_key
    war = war_for(world, war_key(ca.name, cb.name)) if world.campaigns_enabled else None
    if war is not None:
        return (a, b) if war.attacker == ca.name else (b, a)
    for x, y in world.active_wars:
        if {x, y} == {ca.name, cb.name}:
            return (a, b) if x == ca.name else (b, a)
    return a, b


def _fight(t: _Tick, zone: int, a: int, b: int) -> None:
    from chronicler.emergence import get_severity_multiplier
    from chronicler.models import NamedEvent
    from chronicler.named_events import deduplicate_name
    from chronicler.war.common import add_stat
    world, state = t.world, t.state
    att, dfn = _attacker_defender(t, zone, a, b)
    catt, cdfn = world.civilizations[att], world.civilizations[dfn]
    att_fleets = sorted(_fleets_in(state, zone, att), key=lambda f: f.fleet_id)
    def_fleets = sorted(_fleets_in(state, zone, dfn), key=lambda f: f.fleet_id)
    a_n = sum(f.ships for f in att_fleets)
    d_n = sum(f.ships for f in def_fleets)
    rng = _rng(world, "battle", zone, att, dfn)
    a_pow = _side_power(t, att, att_fleets, zone) * rng.uniform(0.85, 1.15)
    d_pow = _side_power(t, dfn, def_fleets, zone) * rng.uniform(0.85, 1.15)
    ratio = a_pow / max(d_pow, 1e-9)
    if ratio >= DECISIVE_RATIO:
        winner, loser, r = att, dfn, ratio
    elif ratio <= 1.0 / DECISIVE_RATIO:
        winner, loser, r = dfn, att, 1.0 / ratio
    else:
        winner = loser = None
        r = 1.0
    if winner is None:
        a_rate = d_rate = 0.10
    else:
        loser_rate = min(0.6, 0.25 + 0.15 * (r - 1.0))
        winner_rate = max(0.05, 0.15 - 0.05 * (r - 1.0))
        a_rate, d_rate = (winner_rate, loser_rate) if winner == att else (loser_rate, winner_rate)
    a_loss = min(a_n, int(round(a_n * a_rate * rng.uniform(0.8, 1.2))))
    d_loss = min(d_n, int(round(d_n * d_rate * rng.uniform(0.8, 1.2))))
    for fleets, loss in ((att_fleets, a_loss), (def_fleets, d_loss)):
        for f, share in zip(fleets, _split(loss, [f.ships for f in fleets])):
            f.ships -= share
    _bump(state, "ships_lost_battle", a_loss + d_loss)
    _bump(state, "naval_battles")
    zname = state.zones[zone].name
    outcome = ("a victory for " + world.civilizations[winner].name) if winner is not None else "indecisive"
    name = deduplicate_name(f"The Battle of {zname}", [ne.name for ne in world.named_events])
    causes = [_war_cause(world, catt.name, cdfn.name)]
    causes += [f.event_id for f in att_fleets + def_fleets if f.event_id]
    ev = _emit(t, "naval_battle", [catt.name, cdfn.name],
               f"{name}: {catt.name} ({a_n} ships) against {cdfn.name} ({d_n}) in {zname}: "
               f"{outcome}. Ships lost {a_loss}/{d_loss}.",
               importance=7 if winner is not None else 5, region=_zone_anchor(world, state.zones[zone]),
               causes=causes)
    t.battle_zones[zone] = ev.event_id
    state.battles.append(NavalBattle(
        turn=world.turn, zone=zone, attacker=att, defender=dfn, attacker_ships=a_n, defender_ships=d_n,
        attacker_losses=a_loss, defender_losses=d_loss, winner=winner, event_id=ev.event_id,
    ))
    if winner is not None:
        world.named_events.append(NamedEvent(
            name=name, event_type="battle", turn=world.turn, actors=[catt.name, cdfn.name],
            region=_zone_anchor(world, state.zones[zone]),
            description=f"{catt.name} vs {cdfn.name} at sea: {outcome}", importance=6,
        ))
    # War bookkeeping (campaign layer): war score, last combat, weariness.
    for ci, ships, lost in ((att, a_n, a_loss), (dfn, d_n, d_loss)):
        civ = world.civilizations[ci]
        civ.war_weariness += NAVAL_WEARINESS + 2.0 * lost / max(1, ships)
    if world.campaigns_enabled:
        from chronicler.war.common import war_for
        from chronicler.war.peace import war_key
        war = war_for(world, war_key(catt.name, cdfn.name))
        if war is not None:
            war.last_combat_turn = world.turn
            if winner is not None:
                l_ships, l_lost = (d_n, d_loss) if loser == dfn else (a_n, a_loss)
                points = NAVAL_POINTS_BASE + int(NAVAL_POINTS_SCALE * l_lost / max(1, l_ships))
                war.battle_points += points if world.civilizations[winner].name == war.attacker else -points
    if winner is None:
        return
    lciv = world.civilizations[loser]
    add_stat(t, lciv, "stability", -int(NAVAL_DEFEAT_STABILITY * get_severity_multiplier(lciv, world)),
             "guard-shock")
    for f in _fleets_in(state, zone, winner):
        f.battles_won += 1
    for f in [x for x in state.fleets if x.zone == zone and x.civ == loser]:
        f.battles_lost += 1
        if f.ships < MIN_FLEET_SHIPS:
            _bump(state, "fleets_sunk")
            _emit(t, "fleet_lost", [lciv.name, world.civilizations[winner].name],
                  f"{f.name} is sunk in {zname}.", importance=6,
                  region=_zone_anchor(world, state.zones[zone]), causes=(ev.event_id,))
            continue
        f.refit_until = world.turn + REFIT_TURNS
        f.mission = "refit"
        _step_toward(t, f, _home_zone(t, f))


# --- control, blockades, pirates -----------------------------------------------------

def _update_control(t: _Tick) -> None:
    world, state = t.world, t.state
    for zi, zone in enumerate(state.zones):
        civs = sorted({f.civ for f in _fleets_in(state, zi)})
        status, controller = UNCONTESTED, None
        if civs:
            strength = {ci: _strength(world, state, zi, [ci]) for ci in civs}
            top = min(civs, key=lambda ci: (-strength[ci], ci))
            hostile = [ci for ci in civs if ci != top and _at_war(
                t.wars, world.civilizations[top].name, world.civilizations[ci].name)]
            hostile_strength = sum(strength[ci] for ci in hostile)
            if (_ships_in(state, zi, top) >= MIN_CONTROL_SHIPS
                    and strength[top] >= CONTROL_RATIO * hostile_strength):
                status, controller = CONTROLLED, top
            elif hostile:
                status = CONTESTED
        if (status, controller) == (zone.status, zone.controller):
            continue
        prev_status, prev_controller = zone.status, zone.controller
        zone.status, zone.controller, zone.since_turn = status, controller, world.turn
        battle = t.battle_zones.get(zi)
        if status == CONTROLLED:
            civ = world.civilizations[controller]
            lead = max(_fleets_in(state, zi, controller), key=lambda f: (f.ships, -f.fleet_id))
            # Peacetime patrols come and go silently; command won from a
            # rival, out of a contest or against an enemy's ports is news.
            enemy_ports = any(
                _holds(world.regions[r], e.name) for r in zone.ports for e in world.civilizations
                if e.regions and e.name != civ.name and _at_war(t.wars, civ.name, e.name))
            if prev_status == CONTESTED or prev_controller is not None or battle or enemy_ports:
                ev = _emit(t, "sea_control", [civ.name],
                           f"{civ.name} commands {zone.name}.", importance=4,
                           region=_zone_anchor(world, zone), causes=(battle or lead.event_id,))
                zone.status_event_id = ev.event_id
            else:
                zone.status_event_id = lead.event_id
        elif status == CONTESTED:
            names = sorted(world.civilizations[ci].name for ci in civs)
            arrivals = [f.event_id for f in _fleets_in(state, zi) if f.event_id]
            ev = _emit(t, "sea_contested", names,
                       f"Rival fleets contest {zone.name}.", importance=4,
                       region=_zone_anchor(world, zone), causes=(battle, *arrivals[:2]))
            zone.status_event_id = ev.event_id
        else:
            if prev_controller is not None and battle is not None:
                civ = world.civilizations[prev_controller]
                ev = _emit(t, "sea_control_lost", [civ.name],
                           f"{civ.name} loses command of {zone.name}.", importance=4,
                           region=_zone_anchor(world, zone), causes=(battle,))
                zone.status_event_id = ev.event_id
            else:
                zone.status_event_id = ""


def _update_blockades(t: _Tick) -> None:
    world, state = t.world, t.state
    wanted: dict[tuple[int, int, int], None] = {}
    for zi, zone in enumerate(state.zones):
        if zone.status != CONTROLLED or zone.controller is None:
            continue
        cname = world.civilizations[zone.controller].name
        for ei, enemy in enumerate(world.civilizations):
            if ei == zone.controller or not enemy.regions or not _at_war(t.wars, cname, enemy.name):
                continue
            if any(_holds(world.regions[r], enemy.name) for r in zone.ports):
                wanted[(zi, zone.controller, ei)] = None
    active = {(b.zone, b.blockader, b.target): b for b in state.active_blockades()}
    for key in sorted(active):
        if key not in wanted:
            b = active[key]
            b.end_turn = world.turn
            zone = state.zones[b.zone]
            names = [world.civilizations[b.blockader].name, world.civilizations[b.target].name]
            _emit(t, "blockade_lifted", names,
                  f"The blockade of {names[1]}'s ports in {zone.name} is lifted.", importance=4,
                  region=_zone_anchor(world, zone), causes=(b.event_id,))
    for key in sorted(wanted):
        if key in active:
            continue
        zi, bi, ei = key
        zone = state.zones[zi]
        names = [world.civilizations[bi].name, world.civilizations[ei].name]
        ev = _emit(t, "blockade", names,
                   f"{names[0]} blockades {names[1]}'s ports in {zone.name}.", importance=6,
                   region=_zone_anchor(world, zone),
                   causes=(zone.status_event_id, _war_cause(world, names[0], names[1])))
        state.blockades.append(Blockade(zone=zi, blockader=bi, target=ei, start_turn=world.turn,
                                        event_id=ev.event_id))
        _bump(state, "blockades")
    blocked: set[tuple[int, int]] = set()
    active_now = state.active_blockades()
    _bump(state, "blockade_turns", len(active_now))
    for b in active_now:
        target = world.civilizations[b.target].name
        for a, c in t.look.zone_lanes[b.zone]:
            if _holds(world.regions[a], target) or _holds(world.regions[c], target):
                blocked.add((a, c))
    new_blocked = sorted(blocked)
    if new_blocked != state.blocked:
        state.blocked = new_blocked
        world.invalidate_trade_route_cache()


def _update_pirates(t: _Tick, traffic: list[float]) -> None:
    state = t.state
    for zi, zone in enumerate(state.zones):
        p = zone.pirates
        tr = min(1.0, traffic[zi] / PIRATE_TRAFFIC_REF) if zi < len(traffic) else 0.0
        if zone.status == CONTROLLED:
            p *= 1.0 - PIRATE_SUPPRESSION
        elif zone.status == CONTESTED:
            p += PIRATE_GROWTH_CONTESTED * max(tr, 0.5) * (1.0 - p)
        else:
            p += PIRATE_GROWTH * tr * (1.0 - p) - PIRATE_DECAY * (1.0 - tr) * p
        cap = PIRATE_MAX.get(zone.kind, 1.0)
        zone.pirates = round(max(0.0, min(cap, p)), 4)


# ---------------------------------------------------------------------------
# Trade consumers
# ---------------------------------------------------------------------------

def edge_blocked(world, a: int, b: int) -> bool:
    """Blockaded sea lane (``False`` with the switch off)."""
    if not maritime_enabled(world) or not world.maritime.blocked:
        return False
    return (a, b) in _lookups(world.maritime).blocked


def blocked_name_pairs(world) -> frozenset:
    """Blockaded lanes as (region name, region name), both directions."""
    if not maritime_enabled(world) or not world.maritime.blocked:
        return frozenset()
    regions = world.regions
    out = set()
    for a, b in world.maritime.blocked:
        out.add((regions[a].name, regions[b].name))
        out.add((regions[b].name, regions[a].name))
    return frozenset(out)


def ledger_trade_adjuster(world) -> Callable[[int, int, float], float] | None:
    """Contact-ledger route-proxy hook: blockaded lanes carry nothing and
    pirates skim the rest of the sea trade. ``None`` with the switch off."""
    if not maritime_enabled(world):
        return None
    look = _lookups(world.maritime)
    rates = [skim_rate(world, z) for z in range(len(world.maritime.zones))]

    def adjust(a: int, b: int, value: float) -> float:
        z = look.lane_zone.get((a, b))
        if z is None:
            return value
        if (a, b) in look.blocked:
            return 0.0
        return value * (1.0 - rates[z])

    return adjust


def observe_phase2(world, routes: list[tuple[str, str]]) -> None:
    """``--agents off``: measure this turn's sea-lane trade and piracy.

    Uses the contact ledger's goods-route proxy rows (computed even with the
    ledger off), so the maritime measurement and the ledger agree.
    """
    if not maritime_enabled(world):
        return
    from chronicler.contact_ledger import off_mode_trade_rows
    state = world.maritime
    look = _lookups(state)
    n = len(state.zones)
    if len(state.pending_sea_trade) != n:
        state.pending_sea_trade = [0.0] * n
        state.pending_piracy = [0.0] * n
    civ_index = world.civ_index_map
    rates = [skim_rate(world, z) for z in range(n)]
    for a, b, value in off_mode_trade_rows(world, routes):
        z = look.lane_zone.get((a, b))
        if z is None or (a, b) in look.blocked:
            continue
        state.pending_sea_trade[z] = round(state.pending_sea_trade[z] + value, 6)
        skim = value * rates[z]
        if skim <= 0:
            continue
        state.pending_piracy[z] = round(state.pending_piracy[z] + skim, 6)
        owner = world.regions[a].controller
        if owner in civ_index:
            ci = civ_index[owner]
            state.pending_piracy_civ[ci] = round(state.pending_piracy_civ.get(ci, 0.0) + skim, 6)


def filter_boundary_batch(world, batch, from_col: str, to_col: str):
    """Drop blockaded sea lanes from an Arrow edge batch (goods economy)."""
    if not maritime_enabled(world) or not world.maritime.blocked or batch.num_rows == 0:
        return batch
    import pyarrow as pa
    look = _lookups(world.maritime)
    src = batch.column(from_col).to_pylist()
    dst = batch.column(to_col).to_pylist()
    mask = [(a, b) not in look.blocked for a, b in zip(src, dst)]
    if all(mask):
        return batch
    return batch.filter(pa.array(mask, type=pa.bool_()))


def merchant_route_graph(world, batch):
    """Native merchant graph: blockaded lanes removed; every sea lane carries
    its raid risk (``sea_raid_risk``; -1 on land edges)."""
    if not maritime_enabled(world):
        return batch
    import pyarrow as pa
    batch = filter_boundary_batch(world, batch, "from_region", "to_region")
    look = _lookups(world.maritime)
    rates = [skim_rate(world, z) for z in range(len(world.maritime.zones))]
    src = batch.column("from_region").to_pylist()
    dst = batch.column("to_region").to_pylist()
    risk = []
    for a, b in zip(src, dst):
        z = look.lane_zone.get((a, b))
        risk.append(-1.0 if z is None else rates[z])
    columns = {name: batch.column(name) for name in batch.schema.names}
    columns["sea_raid_risk"] = pa.array(risk, type=pa.float32())
    return pa.record_batch(columns)


def observe_agent_sea_trade(world, agent_bridge) -> None:
    """Agent modes: fold the native sea crossing log (cargo and raids) into
    the pending measurement for the next tick."""
    if not maritime_enabled(world) or agent_bridge is None:
        return
    sim = getattr(agent_bridge, "_sim", None)
    if sim is None:
        return
    if not hasattr(sim, "get_sea_trade_log"):
        raise RuntimeError("Maritime in agent modes needs get_sea_trade_log; rebuild chronicler-agents")
    batch = sim.get_sea_trade_log()
    if batch.num_rows == 0:
        return
    state = world.maritime
    look = _lookups(state)
    n = len(state.zones)
    if len(state.pending_sea_trade) != n:
        state.pending_sea_trade = [0.0] * n
        state.pending_piracy = [0.0] * n
    civ_index = world.civ_index_map
    cols = [batch.column(c).to_pylist() for c in ("from_region", "to_region", "origin_region", "qty", "raided")]
    crossings = 0
    for a, b, origin, qty, raided in zip(*cols):
        z = look.lane_zone.get((int(a), int(b)))
        if z is None or qty <= 0:
            continue
        crossings += 1
        state.pending_sea_trade[z] = round(state.pending_sea_trade[z] + float(qty), 6)
        if raided:
            state.pending_piracy[z] = round(state.pending_piracy[z] + float(qty), 6)
            owner = world.regions[int(origin)].controller if 0 <= int(origin) < len(world.regions) else None
            if owner in civ_index:
                ci = civ_index[owner]
                state.pending_piracy_civ[ci] = round(state.pending_piracy_civ.get(ci, 0.0) + float(qty), 6)
    _bump(state, "crossings", crossings)


# ---------------------------------------------------------------------------
# Campaign consumers (armies at sea)
# ---------------------------------------------------------------------------

class NavalContext:
    """Per-campaign-tick view of the sea for armies (``WarContext.naval``)."""

    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.world = ctx.world
        self.state: MaritimeState = ctx.world.maritime
        self.look = _lookups(self.state)
        self.wars = _war_pairs(ctx.world)
        self._planning: dict[str, dict[int, tuple[int, ...]]] = {}
        self._supply: dict[str, dict[int, tuple[int, ...]]] = {}
        self._capacity: dict[tuple[int, int], int] = {}

    def _ci(self, civ_name: str) -> int | None:
        return self.world.civ_index_map.get(civ_name)

    def _enemy_controls(self, civ_name: str, zone: SeaZoneState) -> bool:
        if zone.status != CONTROLLED or zone.controller is None:
            return False
        other = self.world.civilizations[zone.controller].name
        return other != civ_name and _at_war(self.wars, civ_name, other)

    def _filtered(self, keep) -> dict[int, tuple[int, ...]]:
        graph = self.ctx.graph
        out = {}
        for i, nbs in graph.items():
            out[i] = tuple(j for j in nbs if (z := self.look.lane_zone.get((i, j))) is None or keep(z))
        return out

    def planning_graph(self, civ_name: str) -> dict[int, tuple[int, ...]]:
        """Lanes the civ could cross with a fleet it has or can send."""
        if civ_name not in self._planning:
            ci = self._ci(civ_name)
            ports = {zi for zi, zone in enumerate(self.state.zones)
                     if any(_own_port(self.world.regions[r], civ_name) for r in zone.ports)}

            def keep(z: int) -> bool:
                zone = self.state.zones[z]
                mine = _ships_in(self.state, z, ci) > 0 if ci is not None else False
                if zone.status == CONTROLLED and zone.controller == ci:
                    return True
                if self._enemy_controls(civ_name, zone):
                    return False
                return mine or z in ports
            self._planning[civ_name] = self._filtered(keep)
        return self._planning[civ_name]

    def supply_graph(self, civ_name: str) -> dict[int, tuple[int, ...]]:
        """Supply runs over every lane not in an enemy-controlled zone."""
        if civ_name not in self._supply:
            self._supply[civ_name] = self._filtered(
                lambda z: not self._enemy_controls(civ_name, self.state.zones[z]))
        return self._supply[civ_name]

    def distances(self, civ_name: str, start: str) -> dict[str, int]:
        origin = self.ctx.index.get(start)
        if origin is None:
            return {}
        graph = self.planning_graph(civ_name)
        dist = {origin: 0}
        queue = deque([origin])
        while queue:
            node = queue.popleft()
            for nb in graph[node]:
                if nb not in dist:
                    dist[nb] = dist[node] + 1
                    queue.append(nb)
        return {self.ctx.names[i]: d for i, d in dist.items()}

    def path(self, army) -> list[int]:
        from chronicler.campaign_logistics import shortest_path
        return shortest_path(self.planning_graph(army.civ), self.ctx.index[army.region],
                             self.ctx.index[army.objective])

    def crossing(self, army, a: int, b: int) -> tuple[bool, Fleet | None]:
        """Whether the army may cross a -> b now (and the escorting fleet)."""
        z = self.look.lane_zone.get((a, b))
        if z is None:
            return True, None
        ci = self._ci(army.civ)
        zone = self.state.zones[z]
        if zone.status == CONTROLLED and zone.controller == ci:
            return True, None
        if self._enemy_controls(army.civ, zone):
            return False, None
        if self._escort_capacity(ci, z) >= army.soldiers:
            fleets = _fleets_in(self.state, z, ci)
            return True, max(fleets, key=lambda f: (f.ships, -f.fleet_id)) if fleets else None
        if ci is not None:
            need = max(1, -(-army.soldiers // SOLDIERS_PER_SHIP))
            self.state.escort_requests.append(EscortRequest(civ=ci, zone=z, ships=need))
        return False, None

    def _escort_capacity(self, ci: int | None, z: int) -> int:
        """Soldiers the civ's ships in ``z`` can still carry this turn."""
        if ci is None:
            return 0
        cap = self._capacity.get((ci, z))
        if cap is None:
            cap = _ships_in(self.state, z, ci) * SOLDIERS_PER_SHIP
            self._capacity[(ci, z)] = cap
        return cap

    def can_retreat(self, army, a: int, b: int) -> bool:
        z = self.look.lane_zone.get((a, b))
        if z is None:
            return True
        ci = self._ci(army.civ)
        zone = self.state.zones[z]
        if zone.status == CONTROLLED and zone.controller == ci:
            return True
        return not self._enemy_controls(army.civ, zone) and _ships_in(self.state, z, ci) > 0

    def note_crossing(self, army, a: int, b: int, fleet: Fleet | None) -> None:
        from chronicler.war.common import emit, war_for
        world, state = self.world, self.state
        z = self.look.lane_zone.get((a, b))
        if z is None:
            return
        ci = self._ci(army.civ)
        if fleet is not None:
            # The escort's lift is spent for this turn.
            self._capacity[(ci, z)] = self._escort_capacity(ci, z) - army.soldiers
        _bump(state, "crossings")
        dest = world.regions[b]
        if _holds(dest, army.civ):
            return
        state.landings[army.army_id] = world.turn
        _bump(state, "landings")
        if army.army_id not in state.landed_armies:
            state.landed_armies.append(army.army_id)
            _bump(state, "overseas_campaigns")
        zone = state.zones[z]
        war = war_for(world, army.war_key)
        enemy = None
        if war is not None:
            enemy = war.defender if army.civ == war.attacker else war.attacker
        causes = [fleet.event_id if fleet is not None else zone.status_event_id]
        if enemy is not None:
            causes.append(_war_cause(world, army.civ, enemy))
        how = f"escorted by {fleet.name}" if fleet is not None else f"under its command of {zone.name}"
        emit(self.ctx, "amphibious_landing", [army.civ] + ([enemy] if enemy else []),
             f"{army.name} lands at {dest.name} from {zone.name}, {how}.",
             importance=6, region=dest.name, causes=[c for c in causes if c])


def attach_naval_context(ctx) -> None:
    """Give a campaign ``WarContext`` its naval view (switch on only)."""
    if maritime_enabled(ctx.world):
        ctx.naval = NavalContext(ctx)


def landing_factor(world, army) -> float:
    """Combat power multiplier for an army that landed from the sea this turn."""
    if not maritime_enabled(world):
        return 1.0
    return LANDING_POWER if world.maritime.landings.get(army.army_id) == world.turn else 1.0


# ---------------------------------------------------------------------------
# Expansion consumer (colonization through EXPAND)
# ---------------------------------------------------------------------------

def _reach_zones(world, civ) -> set[int]:
    state = world.maritime
    ci = world.civ_index_map.get(civ.name)
    wars = _war_pairs(world)
    out = set()
    for f in state.fleets:
        if f.civ != ci or f.ships <= 0:
            continue
        zone = state.zones[f.zone]
        if zone.status == CONTROLLED and zone.controller not in (None, ci):
            other = world.civilizations[zone.controller].name
            if _at_war(wars, civ.name, other):
                continue
        out.add(f.zone)
    return out


def expansion_candidates(world, civ, unclaimed: list["Region"]) -> list["Region"]:
    """EXPAND targets with the sea in the way.

    An unclaimed coastal region (a port of some sea zone) that the civ's
    settlers cannot walk to (:func:`land_reachable`) is overseas: it is a
    target only while the civ has a fleet in one of its zones. Every other
    target is unchanged (the base EXPAND reach). Order is preserved."""
    if not maritime_enabled(world):
        return unclaimed
    if not any(r.controller == civ.name for r in world.regions):
        return unclaimed
    look = _lookups(world.maritime)
    if not look.region_zones:
        return unclaimed
    index = {r.name: i for i, r in enumerate(world.regions)}
    walkable = None
    reach = None
    out = []
    for region in unclaimed:
        i = index[region.name]
        zones = look.region_zones.get(i)
        if zones:
            if walkable is None:
                walkable = land_reachable(world, civ.name)
                reach = _reach_zones(world, civ)
            if i not in walkable and not any(z in reach for z in zones):
                continue
        out.append(region)
    return out


def overseas_zone(world, civ, target: "Region") -> int | None:
    """Zone a chosen EXPAND target is reached across (None: reached by land).
    Call before the target is claimed."""
    if not maritime_enabled(world):
        return None
    ti = next(i for i, r in enumerate(world.regions) if r.name == target.name)
    if not _lookups(world.maritime).region_zones.get(ti) or ti in land_reachable(world, civ.name):
        return None
    reach = _reach_zones(world, civ)
    zones = [z for z in _lookups(world.maritime).region_zones.get(ti, ()) if z in reach]
    return zones[0] if zones else None


def note_colony(world, civ, target: "Region", zone: int, event: "Event") -> None:
    """Record a colony settled by sea through EXPAND, citing the fleet."""
    from chronicler import provenance
    state = world.maritime
    ti = next(i for i, r in enumerate(world.regions) if r.name == target.name)
    ci = world.civ_index_map.get(civ.name)
    fleet = max([f for f in state.fleets if f.civ == ci and f.zone == zone],
                key=lambda f: (f.ships, -f.fleet_id), default=None)
    provenance.ensure_id(world, event)
    if fleet is not None:
        provenance.cite(event, fleet.event_id)
    event.description = (f"{civ.name} settled {target.name} across {state.zones[zone].name}"
                         + (f", carried by {fleet.name}." if fleet is not None else "."))
    event.region = target.name
    state.colonies.append(Colony(region=ti, civ=ci, zone=zone, turn=world.turn,
                                 event_id=event.event_id))
    _bump(state, "colonies")


# ---------------------------------------------------------------------------
# Viewer / analytics
# ---------------------------------------------------------------------------

def snapshot_summary(world) -> dict:
    """Per-turn maritime summary for ``TurnSnapshot.maritime``."""
    state = world.maritime
    civs = world.civilizations

    def cname(ci):
        return civs[ci].name if ci is not None and 0 <= ci < len(civs) else None

    zones = []
    for zi, zone in enumerate(state.zones):
        ships: dict[str, int] = {}
        for f in state.fleets:
            if f.zone == zi:
                ships[cname(f.civ)] = ships.get(cname(f.civ), 0) + f.ships
        zones.append({
            "zone": zone.name, "status": zone.status, "controller": cname(zone.controller),
            "pirates": zone.pirates, "ships": dict(sorted(ships.items())),
            "sea_trade": state.last_sea_trade[zi] if zi < len(state.last_sea_trade) else 0.0,
            "piracy": state.last_piracy[zi] if zi < len(state.last_piracy) else 0.0,
        })
    return {
        "zones": zones,
        "fleets": [{"id": f.fleet_id, "name": f.name, "civ": cname(f.civ), "zone": state.zones[f.zone].name,
                    "ships": f.ships, "mission": f.mission} for f in state.fleets],
        "blockades": [{"zone": state.zones[b.zone].name, "blockader": cname(b.blockader),
                       "target": cname(b.target), "since": b.start_turn} for b in state.active_blockades()],
        "blocked_lanes": len(state.blocked),
        "counters": {k: state.counters.get(k, 0) for k in COUNTER_KEYS},
    }


def extract_maritime_metrics(bundles: list[dict]) -> dict:
    """Analytics section from ``history[n].maritime`` (empty when no bundle has it)."""
    runs = []
    for bundle in bundles:
        series = [h.get("maritime") for h in bundle.get("history", []) if h.get("maritime")]
        if not series:
            continue
        fleets = [len(s["fleets"]) for s in series]
        ships = [sum(f["ships"] for f in s["fleets"]) for s in series]
        controlled = [sum(1 for z in s["zones"] if z["status"] == CONTROLLED) for s in series]
        contested = [sum(1 for z in s["zones"] if z["status"] == CONTESTED) for s in series]
        blockades = [len(s["blockades"]) for s in series]
        runs.append({
            "seed": bundle.get("metadata", {}).get("seed"),
            "turns": len(series),
            "zones": len(series[-1]["zones"]),
            "counters": dict(series[-1].get("counters", {})),
            "mean_fleets": sum(fleets) / len(fleets),
            "mean_ships": sum(ships) / len(ships),
            "mean_controlled_zones": sum(controlled) / len(controlled),
            "mean_contested_zones": sum(contested) / len(contested),
            "mean_active_blockades": sum(blockades) / len(blockades),
        })
    if not runs:
        return {}
    totals: dict[str, float] = {}
    for run in runs:
        for k, v in run["counters"].items():
            totals[k] = totals.get(k, 0) + v
    return {
        "runs": runs,
        "mean_counters": {k: v / len(runs) for k, v in sorted(totals.items())},
    }
