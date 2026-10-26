"""Pastoral and nomadic peoples: subsistence modes, herds, raids, tribute,
hordes and sedentarization (``--nomads``).

Behind ``WorldState.nomads`` (CLI ``--nomads``, on by default for new worlds,
persisted on the world so a resumed run keeps it). With the switch off nothing
in this module runs, except :func:`food_yields`, which returns its input list
unchanged, and every output is identical to the simulation without it. See
``docs/integration/nomads.md``.

Subsistence mode (``NomadState.modes``, per civ)
    ``sedentary``, ``agro_pastoral`` or ``nomadic``, seeded from the
    population-weighted pastoral suitability of a civ's land when the switch
    is turned on (and for polities founded later, at their first tick):
    steppe, desert and tundra favour herding, farmland favours the plough.

Herds (``NomadState.herds``, per region)
    Herd stock grazing a region held by a pastoral civ: logistic growth on
    pasture (terrain x grass, so drought shrinks it), die-off above the
    seasonal carrying capacity, dzud winters on cold pasture. Nomads move
    their herds between summer and winter pastures (transhumance), so they
    lose less to the season and the dzud than herders who stay put. Herd
    food reaches the harvest through one hook in the food path
    (``ecology.compute_resource_yields`` -> :func:`food_yields`).

Raids, tribute
    Pastoral civs raid settled neighbours (more when their herds are short or
    they ride in a horde): plunder taken from the treasury, people killed,
    a stability shock, worse dispositions and, with diplomacy on, a border
    grievance. Raiders and garrisons fight with the campaign layer's power
    terms (``war.battles``). A settled civ raided repeatedly and too weak to
    resist buys peace with a tribute pact; a payer grown strong repudiates
    it. Conquest goes through the existing war paths.

Hordes
    A nomadic khan with high asabiya unites weaker pastoral neighbours into a
    horde, kept as a federation in ``world.federations`` (federation defense,
    the Rust/Python federation dissolution rule and every federation consumer
    apply). The horde rides in conquest waves: the khan declares war on a
    settled neighbour and summons the members through the campaign WAR path
    (``war.runtime.declare_or_press_war``); its wars aim at conquest. When the
    founding khan dies the horde breaks apart at once: the federation is
    dissolved, the heirs quarrel and the core loses stability and asabiya.

Sedentarization
    A pastoral civ whose people live mostly on farmland (conquered or not)
    settles after a generation of it: nomadic -> agro-pastoral -> sedentary.
    Farmland held by herders erodes their asabiya; settling costs more.

Identity: region = index in ``world.regions``, civ = index in
``world.civilizations``. All randomness comes from
``random.Random(stable_hash_int("nomads", <namespace>, seed, turn, ...))``.
Stat changes use the existing accumulator categories.
"""
from __future__ import annotations

import random
from collections import deque
from typing import TYPE_CHECKING, Iterable

from chronicler.nomads_state import (
    AGRO_PASTORAL, COUNTER_KEYS, NOMADIC, SEDENTARY, SUBSISTENCE_MODES,
    Conquest, Horde, NomadState, Raid, TributePact, nomads_on,
)
from chronicler.utils import stable_hash_int

if TYPE_CHECKING:  # pragma: no cover
    from chronicler.models import Civilization, Event, Region, WorldState


# ---------------------------------------------------------------------------
# Parameters ([CALIBRATE]; documented in docs/integration/nomads.md)
# ---------------------------------------------------------------------------

#: Default for worlds created by the CLI/batch/live entry points
#: (on since the 2026-10 Wave 8 full gate, ``docs/integration/defaults-wave8.md``;
#: ``--no-nomads`` opts out; loaded worlds keep their saved setting).
DEFAULT_ENABLED_FOR_NEW_WORLDS = True

# Subsistence: pastoral suitability of terrain (share of a people that herds).
PASTORAL_SUITABILITY: dict[str, float] = {
    "steppe": 1.0, "desert": 0.85, "tundra": 0.85, "hills": 0.5, "mountains": 0.5,
    "plains": 0.3, "river": 0.15, "marsh": 0.15, "coast": 0.1, "forest": 0.1, "jungle": 0.0,
}
DEFAULT_SUITABILITY = 0.3
NOMADIC_SHARE = 0.70           # seeding: pastoral share for a nomadic people
AGRO_SHARE = 0.45              # seeding: pastoral share for herders who also farm
NOMADIC_FLOOR = 0.50           # a nomadic people below this share starts to settle
AGRO_FLOOR = 0.30              # an agro-pastoral people below this share starts to settle
GENERATION = 25                # turns below the floor before a people settles
SETTLE_RECOVERY = 2            # generation clock lost per turn back above the floor

# Herds (100 head = a full steppe pasture with normal grass).
HERD_SCALE = 100.0
PASTURE: dict[str, float] = {
    "steppe": 1.0, "plains": 0.8, "river": 0.7, "hills": 0.6, "tundra": 0.5,
    "mountains": 0.4, "desert": 0.35, "coast": 0.3, "marsh": 0.25, "forest": 0.2, "jungle": 0.05,
}
DEFAULT_PASTURE = 0.3
#: Seasonal pasture (spring, summer, autumn, winter): high summer grazing in
#: the mountains and tundra, winter grazing in the desert and lowlands.
SEASON_PASTURE: dict[str, tuple[float, float, float, float]] = {
    "tundra": (0.8, 1.4, 0.8, 0.2),
    "mountains": (0.8, 1.4, 0.8, 0.3),
    "hills": (0.9, 1.2, 0.9, 0.6),
    "steppe": (1.0, 1.1, 1.0, 0.7),
    "desert": (1.1, 0.6, 1.0, 1.3),
    "plains": (1.0, 1.0, 1.0, 0.9),
    "river": (1.0, 1.0, 1.0, 0.9),
}
DEFAULT_SEASON_PASTURE = (1.0, 1.0, 1.0, 0.8)
HERD_GROWTH = 0.06             # logistic growth per turn
HERD_INFLOW = 0.01             # restocking (share of capacity) while a pasture is nearly empty
HERD_DIEOFF = 0.35             # share of the overshoot lost per turn above capacity
HERD_SETTLED_DECAY = 0.8       # herds on land settled people hold (slaughtered, sold)
HERD_OCCUPIED_DECAY = 0.9      # herds on land an enemy occupies
HERD_START: dict[int, float] = {AGRO_PASTORAL: 0.4, NOMADIC: 0.6}
MOBILITY: dict[int, float] = {AGRO_PASTORAL: 0.2, NOMADIC: 0.6}
DZUD_TERRAINS = frozenset({"tundra", "steppe", "mountains", "hills"})
DZUD_CHANCE = 0.03             # per winter turn on cold pasture
DZUD_COOLING = 2.0
DZUD_POLAR = 1.5               # tundra and subpolar latitudes
DZUD_DRY = 1.5                 # a dry year leaves no hay
DZUD_LOSS = (0.25, 0.5)
DZUD_EVENT_MIN = 5.0           # head lost by a civ in one tick worth a report
PASTURE_EVENT_MIN = 15.0

# The food hook (harvest index units; see ecology.compute_resource_yields).
HERD_FOOD = 0.40               # harvest index per 100 head, for nomads
HERD_FOOD_SHARE: dict[int, float] = {AGRO_PASTORAL: 0.6, NOMADIC: 1.0}
HERD_FOOD_SEASON = (1.0, 1.2, 1.0, 0.8)
CROP_SHARE: dict[int, float] = {AGRO_PASTORAL: 0.9, NOMADIC: 0.7}

# Asabiya (Ibn Khaldun): the steppe breeds it, settled life wears it away.
NOMAD_ASABIYA_GROWTH = 0.04    # logistic, nomads on pasture
SETTLED_ASABIYA_DECAY = 0.004  # per turn on farmland held by herders
SEDENTARIZATION_ASABIYA = 0.9  # asabiya kept when a people settles

# Loose hold: nomads move on from pasture that has stood empty.
LOOSE_TURNS = 15
LOOSE_HERD = 0.05
LOOSE_POP = 10

# Raids.
RAID_BASE: dict[int, float] = {AGRO_PASTORAL: 0.03, NOMADIC: 0.10}
RAID_HUNGER = 1.5
RAID_HORDE = 2.0
RAID_MAX = 0.6
RAID_MILITARY_SHARE = 0.25
RAID_POP_PERMILLE = 60
MIN_RAIDERS = 3
MOUNTED: dict[int, float] = {AGRO_PASTORAL: 1.1, NOMADIC: 1.3}
RAID_MORALE = 750
RAID_LOOT_SHARE = 0.06
RAID_LOOT_CAP = 30
RAID_KILL_SHARE = 0.02
RAID_STABILITY = 2
RAID_WIN_LOSS = 0.05
RAID_REPULSED_LOSS = 0.25
RAID_MILITARY_PER_RAIDER = 0.3
RAID_MEMORY = 40

# Tribute.
TRIBUTE_RAIDS = 2
TRIBUTE_WINDOW = 12
TRIBUTE_POWER = 1.5            # a payer at least this much stronger than the raider fights instead
TRIBUTE_CHANCE = 0.5
TRIBUTE_CHANCE_CAUTIOUS = 0.8
TRIBUTE_CHANCE_BOLD = 0.2
TRIBUTE_RATE = 0.08            # of the payer's economy per turn
TRIBUTE_MIN, TRIBUTE_MAX = 1, 15
TRIBUTE_TERM = 40
TRIBUTE_REPUDIATE_RATIO = 1.4
TRIBUTE_REPUDIATE_CHANCE = 0.25
TRIBUTE_MAX_MISSED = 2
CAUTIOUS_TRAITS = frozenset({"cautious", "shrewd", "calculating"})
BOLD_TRAITS = frozenset({"aggressive", "bold", "stubborn", "zealous"})

# Hordes.
HORDE_ASABIYA = 0.55
HORDE_STABILITY = 15
HORDE_CHANCE = 0.06
HORDE_STRONG_TRAIT = 1.5
STRONG_TRAITS = frozenset({"aggressive", "bold", "ambitious", "zealous"})
HORDE_REACH = 3
SUBMIT_BASE = 0.3
SUBMIT_SLOPE = 0.3
SUBMIT_MAX = 0.9
HORDE_WAVE_CHANCE = 0.2
HORDE_RIDE_CHANCE = 0.6
FRAGMENT_STABILITY = 15
FRAGMENT_MEMBER_STABILITY = 5
FRAGMENT_ASABIYA = 0.85
HORDE_ADJECTIVES = ("Golden", "Blue", "White", "Black", "Grey", "Red", "Great", "Iron", "Sky", "Silver")

# Action weights (one contributor bucket, clamped like diplomacy's).
NOMAD_WAR_WEIGHT = 1.2
HORDE_WAR_WEIGHT = 1.4
WEIGHT_CEILING = 1.5

CONQUEST_MEMORY = 80
TRIBUTE_HISTORY = 50


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

def nomads_enabled(world) -> bool:
    """True only for a real nomad state (mocks and ``None`` read as off)."""
    return nomads_on(world)


def set_nomads_enabled(world: "WorldState", enabled: bool) -> None:
    """Enable (seeding subsistence modes and herds from terrain) or disable."""
    if enabled:
        if world.nomads is None:
            world.nomads = seed_state(world)
        return
    world.nomads = None


def seed_state(world: "WorldState") -> NomadState:
    """A fresh state: modes from the terrain each civ lives on, starting herds."""
    state = NomadState()
    _sync_civs(world, state)
    state.herds = [0.0] * len(world.regions)
    state.dry = [0] * len(world.regions)
    index = world.civ_index_map
    for ri, region in enumerate(world.regions):
        ci = index.get(region.controller, -1) if region.controller else -1
        mode = state.mode(ci)
        if mode != SEDENTARY:
            state.herds[ri] = round(HERD_START[mode] * capacity(region), 4)
    state.controllers = _controllers(world)
    return state


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _rng(world, namespace: str, *parts) -> random.Random:
    return random.Random(stable_hash_int("nomads", namespace, world.seed, world.turn, *parts))


def _bump(state: NomadState, key: str, n: float = 1) -> None:
    state.counters[key] = round(state.counters.get(key, 0) + n, 4)


def _controllers(world) -> list[int]:
    index = world.civ_index_map
    return [index.get(r.controller, -1) if r.controller else -1 for r in world.regions]


def _region_index(world) -> dict[str, int]:
    cache = world.nomads._cache
    index = cache.region_index
    if index is None or len(index) != len(world.regions):
        index = {r.name: i for i, r in enumerate(world.regions)}
        cache.region_index = index
    return index


def suitability(region: "Region") -> float:
    return PASTORAL_SUITABILITY.get(region.terrain, DEFAULT_SUITABILITY)


def pastoral_share(world, civ: "Civilization") -> float:
    """Population-weighted pastoral suitability of a civ's land (0 when landless)."""
    region_map = world.region_map
    total = weighted = 0.0
    for name in civ.regions:
        region = region_map.get(name)
        if region is None:
            continue
        w = max(1, region.population)
        total += w
        weighted += w * suitability(region)
    return weighted / total if total > 0 else 0.0


def seed_mode(share: float) -> int:
    if share >= NOMADIC_SHARE:
        return NOMADIC
    if share >= AGRO_SHARE:
        return AGRO_PASTORAL
    return SEDENTARY


def mode_of(world, civ: "Civilization | None") -> int:
    """Subsistence mode of a civ (sedentary when nomads are off or unknown)."""
    if civ is None or not nomads_on(world):
        return SEDENTARY
    return world.nomads.mode(world.civ_index_map.get(civ.name))


def mode_name(world, civ: "Civilization | None") -> str:
    return SUBSISTENCE_MODES[mode_of(world, civ)]


def capacity(region: "Region") -> float:
    """Herd carrying capacity of a region's pasture (before the season)."""
    from chronicler.ecology import TERRAIN_ECOLOGY_DEFAULTS
    base = PASTURE.get(region.terrain, DEFAULT_PASTURE) * HERD_SCALE
    ref = TERRAIN_ECOLOGY_DEFAULTS.get(region.terrain, TERRAIN_ECOLOGY_DEFAULTS["plains"]).water
    grass = min(1.2, 0.3 + 0.7 * region.ecology.water / max(ref, 0.05))
    return base * grass * min(1.0, max(0.0, region.capacity_modifier))


def seasonal_capacity(region: "Region", season_id: int) -> float:
    mult = SEASON_PASTURE.get(region.terrain, DEFAULT_SEASON_PASTURE)[season_id]
    return capacity(region) * mult


def _sea_lanes(world) -> set[tuple[str, str]]:
    geo = getattr(world, "geography", None)
    if geo is None:
        return set()
    out = set()
    for a, b in geo.sea_lanes:
        out.add((a, b))
        out.add((b, a))
    return out


def _land_neighbors(world, region: "Region", lanes: set) -> list["Region"]:
    region_map = world.region_map
    out = []
    for name in region.adjacencies:
        other = region_map.get(name)
        if other is not None and other is not region and (region.name, name) not in lanes:
            out.append(other)
    return out


def _at_war(world, a: str, b: str) -> bool:
    return (a, b) in world.active_wars or (b, a) in world.active_wars


def _war_enemies(world, name: str) -> set[str]:
    out = set()
    for a, b in world.active_wars:
        if a == name:
            out.add(b)
        elif b == name:
            out.add(a)
    return out


def _federation_of(world, name: str):
    for fed in world.federations:
        if name in fed.members:
            return fed
    return None


def _subject_pairs(world) -> set[tuple[str, str]]:
    out = set()
    for vr in world.vassal_relations:
        out.add((vr.overlord, vr.vassal))
        out.add((vr.vassal, vr.overlord))
    return out


def _is_vassal(world, name: str) -> bool:
    return any(vr.vassal == name for vr in world.vassal_relations)


def _in_truce(world, a: str, b: str) -> bool:
    from chronicler.war import params as P
    pair = {a, b}
    return any(set(t.parties) == pair and world.turn - t.turn < P.TRUCE_TURNS
               for t in world.war_state.treaties)


def _horde_of(state: NomadState, ci: int) -> Horde | None:
    for horde in state.hordes:
        if horde.status == "active" and ci in horde.members:
            return horde
    return None


def _power(civ) -> float:
    from chronicler.diplomacy import power
    return power(civ)


def _disposition_step(world, holder: str, other: str, *, floor_name: str = "hostile",
                      only_above: str | None = None) -> None:
    """Move ``holder``'s disposition toward ``other`` one step colder."""
    from chronicler.models import Disposition
    order = list(Disposition)
    rel = world.relationships.get(holder, {}).get(other)
    if rel is None:
        return
    cur = order.index(rel.disposition)
    if only_above is not None and cur <= order.index(Disposition(only_above)):
        return
    if cur > order.index(Disposition(floor_name)):
        rel.disposition = order[cur - 1]
        rel.disposition_drift = 0


def _set_disposition(world, a: str, b: str, disposition) -> None:
    from chronicler.models import Relationship
    for x, y in ((a, b), (b, a)):
        rels = world.relationships.setdefault(x, {})
        rel = rels.get(y)
        if rel is None:
            rels[y] = Relationship(disposition=disposition)
        else:
            rel.disposition = disposition
            rel.disposition_drift = 0


class _Tick:
    """Duck-types the ``WarContext`` subset the war stat helpers use."""

    def __init__(self, world, acc, agent_bridge) -> None:
        self.world = world
        self.acc = acc
        self.bridge = agent_bridge
        self.events: list = []
        self.state: NomadState = world.nomads
        self.lanes = _sea_lanes(world)
        self.index = _region_index(world)


def _emit(t: _Tick, event_type: str, actors: list[str], description: str, *,
          importance: int = 5, region: str | None = None, causes: Iterable[str | None] = (),
          observe: bool = True) -> "Event":
    from chronicler import provenance
    from chronicler.models import Event
    ev = Event(turn=t.world.turn, event_type=event_type, actors=list(actors),
               description=description, importance=importance, region=region)
    provenance.cite(ev, *causes)
    if observe:
        # Same-tick chains (raids -> tribute, horde -> war) resolve in order.
        provenance.observe_now(t.world, ev)
    t.events.append(ev)
    return ev


def _poss(name: str) -> str:
    """English possessive of a name ("the Jatain Clans'", "Qeduni Empire's")."""
    return name + ("'" if name.endswith("s") else "'s")


def _add_stat(t: _Tick, civ, stat: str, delta: float, category: str) -> None:
    from chronicler.war.common import add_stat
    add_stat(t, civ, stat, delta, category)


def _spend(t: _Tick, civ, amount: int) -> int:
    from chronicler.war.common import spend
    return spend(t, civ, int(amount))


def _projected_treasury(t: _Tick, civ) -> int:
    from chronicler.war.common import projected_treasury
    return projected_treasury(t, civ)


def _agents_own_population(world) -> bool:
    return getattr(world, "agent_mode", None) in ("hybrid", "demographics-only")


def _kill(t: _Tick, civ, region_names: list[str], amount: int) -> int:
    """People killed in a raid, through the campaign layer's population drain
    (staged as native deaths in agent modes)."""
    from chronicler.war.armies import drain_population
    killed = drain_population(t, region_names, amount)
    if killed and not _agents_own_population(t.world):
        from chronicler.utils import sync_civ_population
        sync_civ_population(civ, t.world)
    return killed


# ---------------------------------------------------------------------------
# The food hook (ecology.compute_resource_yields)
# ---------------------------------------------------------------------------

def food_yields(world, region: "Region", yields: list[float], season_id: int) -> list[float]:
    """Harvest yields of one region with its herds (the one food-path hook).

    Returns ``yields`` itself, unchanged, when nomads are off or the region is
    not held by herders. Otherwise herders farm less (``CROP_SHARE`` on grain
    and botanical slots) and their herd adds milk and meat to the region's
    first food slot, in harvest-index units.
    """
    if not nomads_on(world):
        return yields
    owner = region.controller
    if owner is None:
        return yields
    state = world.nomads
    mode = state.mode(world.civ_index_map.get(owner))
    if mode == SEDENTARY:
        return yields
    from chronicler.models import FOOD_TYPES, ResourceType
    out = list(yields)
    crop = CROP_SHARE[mode]
    first_food = None
    for slot, rtype in enumerate(region.resource_types):
        if rtype in (ResourceType.GRAIN, ResourceType.BOTANICALS):
            out[slot] *= crop
        if first_food is None and rtype in FOOD_TYPES:
            first_food = slot
    ri = _region_index(world).get(region.name, -1)
    herd = state.herds[ri] if 0 <= ri < len(state.herds) else 0.0
    if first_food is not None and herd > 0:
        out[first_food] += (HERD_FOOD * herd / HERD_SCALE * HERD_FOOD_SHARE[mode]
                            * HERD_FOOD_SEASON[season_id])
    return out


# ---------------------------------------------------------------------------
# Other hooks (action weights, EXPAND reach, war aims)
# ---------------------------------------------------------------------------

def _neighbor_civs(world, civ: "Civilization", lanes: set | None = None) -> set[str]:
    lanes = _sea_lanes(world) if lanes is None else lanes
    region_map = world.region_map
    out = set()
    for name in civ.regions:
        region = region_map.get(name)
        if region is None:
            continue
        for other in _land_neighbors(world, region, lanes):
            if other.controller is not None and other.controller != civ.name:
                out.add(other.controller)
    return out


def weight_modifiers(civ: "Civilization", world) -> dict:
    """Nomad contributor bucket for action weights, clamped to [1/1.5, 1.5].

    Nomads (and every horde member) facing a hostile settled neighbour lean
    toward war; a horde rides harder.
    """
    if not nomads_on(world) or not civ.regions:
        return {}
    from chronicler.models import ActionType, Disposition
    state = world.nomads
    ci = world.civ_index_map.get(civ.name)
    mode = state.mode(ci)
    if mode == SEDENTARY:
        return {}
    in_horde = _horde_of(state, ci) is not None
    if mode != NOMADIC and not in_horde:
        return {}
    rels = world.relationships.get(civ.name, {})
    civ_map = world.civ_map
    hostile_settled = False
    for name in sorted(_neighbor_civs(world, civ)):
        other = civ_map.get(name)
        rel = rels.get(name)
        if other is None or not other.regions or rel is None:
            continue
        if (rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS)
                and state.mode(world.civ_index_map.get(name)) == SEDENTARY):
            hostile_settled = True
            break
    if not hostile_settled:
        return {}
    war = HORDE_WAR_WEIGHT if in_horde else NOMAD_WAR_WEIGHT
    floor = 1.0 / WEIGHT_CEILING
    return {ActionType.WAR: min(WEIGHT_CEILING, max(floor, war))}


def harsh_terrains(world, civ: "Civilization", harsh):
    """EXPAND: herders range over desert and tundra in any era."""
    if mode_of(world, civ) != SEDENTARY:
        return frozenset()
    return harsh


def horde_conquest(world, attacker: "Civilization", defender: "Civilization") -> bool:
    """A horde member going to war on a settled people seeks conquest."""
    if not nomads_on(world):
        return False
    state = world.nomads
    index = world.civ_index_map
    ai = index.get(attacker.name)
    return (ai is not None and _horde_of(state, ai) is not None
            and state.mode(index.get(defender.name)) == SEDENTARY)


# ---------------------------------------------------------------------------
# The per-turn tick
# ---------------------------------------------------------------------------

def tick_nomads(world: "WorldState", acc=None, agent_bridge=None) -> list["Event"]:
    """Advance pastoral peoples one turn (after Phase 5 and the maritime
    tick, before campaigns). Returns the events produced."""
    if not nomads_on(world) or not world.regions:
        return []
    t = _Tick(world, acc, agent_bridge)
    _sync_regions(t)
    _detect_conquests(t)
    _sync_civs(world, t.state)
    _update_hordes(t)
    _herds(t)
    _loose_hold(t)
    _asabiya(t)
    _sedentarize(t)
    _tributes(t)
    _raids(t)
    _new_tributes(t)
    _form_hordes(t)
    _conquest_waves(t)
    _prune(t)
    t.state.controllers = _controllers(world)
    return t.events


def _sync_civs(world, state: NomadState) -> None:
    """Seed modes for polities founded since the last tick (from their land)."""
    for ci in range(len(state.modes), len(world.civilizations)):
        civ = world.civilizations[ci]
        state.modes.append(seed_mode(pastoral_share(world, civ)) if civ.regions else SEDENTARY)
        state.mode_turn.append(world.turn)
        state.mode_event.append("")
        state.settle.append(0)


def _sync_regions(t: _Tick) -> None:
    n = len(t.world.regions)
    state = t.state
    for name in ("herds", "dry", "controllers"):
        rows = getattr(state, name)
        if len(rows) < n:
            fill = -1 if name == "controllers" else (0.0 if name == "herds" else 0)
            rows.extend([fill] * (n - len(rows)))


# --- conquests ---------------------------------------------------------------------

def _detect_conquests(t: _Tick) -> None:
    """Regions pastoral civs took from other polities since the last tick."""
    from chronicler import provenance as prov
    world, state = t.world, t.state
    prev = state.controllers
    cur = _controllers(world)
    known = len(state.modes)
    civs = world.civilizations
    for ri in range(min(len(prev), len(cur))):
        old, new = prev[ri], cur[ri]
        if old == new or old < 0 or new < 0 or new >= known or old >= len(civs):
            continue
        if state.mode(new) == SEDENTARY:
            continue
        name = world.regions[ri].name
        eid = (prov.recall(world, prov.key("conquest", name), within=2)
               or prov.recall(world, prov.key("conquered", civs[old].name), within=2)
               or prov.recall(world, prov.key("occupation", name), within=40) or "")
        state.conquests.append(Conquest(turn=world.turn, region=ri, civ=new, from_civ=old, event_id=eid))
        _bump(state, "nomad_conquests")
        horde = _horde_of(state, new)
        if horde is not None:
            horde.conquests += 1


# --- hordes: membership, fragmentation, dissolution ----------------------------------

def _end_horde(t: _Tick, horde: Horde, status: str) -> None:
    world = t.world
    horde.status = status
    horde.end_turn = world.turn
    world.federations = [f for f in world.federations if f.name != horde.name]
    _bump(t.state, "hordes_fragmented" if status == "fragmented" else "hordes_dissolved")


def _update_hordes(t: _Tick) -> None:
    from chronicler import provenance as prov
    world, state = t.world, t.state
    civs = world.civilizations
    index = world.civ_index_map
    for horde in sorted(state.active_hordes(), key=lambda h: h.horde_id):
        khan = civs[horde.khan] if horde.khan < len(civs) else None
        fed = next((f for f in world.federations if f.name == horde.name), None)
        if khan is None or not khan.regions:
            names = [civs[m].name for m in horde.members if m < len(civs)]
            _end_horde(t, horde, "dissolved")
            ev = _emit(t, "horde_dissolved", names,
                       f"With {_poss('the ' + (khan.name if khan else 'khan'))} people fallen, "
                       f"{horde.name} scatters.",
                       importance=6,
                       causes=(prov.recall(world, prov.key("conquered", khan.name), within=5) if khan else None,
                               horde.event_id))
            horde.end_event_id = ev.event_id
            continue
        if not khan.leader.alive or khan.leader.name != horde.khan_leader:
            _fragment(t, horde, khan, fed)
            continue
        if fed is None or khan.name not in fed.members or len(fed.members) <= 1 or _is_vassal(world, khan.name):
            members = [civs[m].name for m in horde.members if m < len(civs) and civs[m].regions]
            _end_horde(t, horde, "dissolved")
            why = ("bowed to an overlord" if _is_vassal(world, khan.name)
                   else "lost the clans' allegiance")
            ev = _emit(t, "horde_dissolved", members or [khan.name],
                       f"{horde.name} melts away: {horde.khan_leader} of the {khan.name} {why}.",
                       importance=6, causes=(horde.event_id,))
            horde.end_event_id = ev.event_id
            continue
        horde.members = [horde.khan] + sorted(index[m] for m in fed.members
                                              if m in index and index[m] != horde.khan)
        horde.peak_members = max(horde.peak_members, len(horde.members))


def _fragment(t: _Tick, horde: Horde, khan: "Civilization", fed) -> None:
    """The founding khan is gone: the horde breaks apart at once."""
    from chronicler import provenance as prov
    from chronicler.models import Disposition
    world = t.world
    civs = world.civilizations
    members = [civs[m] for m in horde.members if m < len(civs) and civs[m].regions]
    if fed is not None:
        names = set(fed.members)
        members = [c for c in members if c.name in names] or members
    _end_horde(t, horde, "fragmented")
    # The heirs quarrel: every bond the khan held together goes cold.
    for i, a in enumerate(members):
        for b in members[i + 1:]:
            for x, y in ((a.name, b.name), (b.name, a.name)):
                _disposition_step(world, x, y, floor_name="suspicious")
                rel = world.relationships.get(x, {}).get(y)
                if rel is not None and rel.disposition in (Disposition.ALLIED, Disposition.FRIENDLY):
                    rel.disposition = Disposition.SUSPICIOUS
    from chronicler.emergence import get_severity_multiplier
    _add_stat(t, khan, "stability", -int(FRAGMENT_STABILITY * get_severity_multiplier(khan, world)),
              "guard-shock")
    for civ in members:
        if civ.name != khan.name:
            _add_stat(t, civ, "stability",
                      -int(FRAGMENT_MEMBER_STABILITY * get_severity_multiplier(civ, world)), "guard-shock")
    for name in khan.regions:
        region = world.region_map.get(name)
        if region is not None:
            region.asabiya_state.asabiya = round(region.asabiya_state.asabiya * FRAGMENT_ASABIYA, 4)
    others = [c.name for c in members if c.name != khan.name]
    tail = f"; {', '.join(others)} go their own ways" if others else ""
    ev = _emit(t, "horde_fragmented", [khan.name, *others],
               f"With {horde.khan_leader} gone, {horde.name} breaks apart{tail}.",
               importance=8,
               causes=(prov.recall(world, prov.key("leader_death", khan.name), within=5), horde.event_id))
    horde.end_event_id = ev.event_id
    world.invalidate_trade_route_cache()


# --- herds -----------------------------------------------------------------------------

def _herds(t: _Tick) -> None:
    from chronicler import provenance as prov
    from chronicler.climate import get_climate_phase
    from chronicler.models import ClimatePhase
    from chronicler.resources import get_season_id
    world, state = t.world, t.state
    season = get_season_id(world.turn)
    phase = get_climate_phase(world.turn, world.climate_config)
    index = world.civ_index_map
    herds = state.herds
    held: dict[int, list[int]] = {}
    for ri, region in enumerate(world.regions):
        ci = index.get(region.controller, -1) if region.controller else -1
        if ci < 0 or state.mode(ci) == SEDENTARY:
            herds[ri] = 0.0 if herds[ri] * HERD_SETTLED_DECAY < 0.5 else round(herds[ri] * HERD_SETTLED_DECAY, 4)
            continue
        if region.occupied_by is not None and region.occupied_by != region.controller:
            herds[ri] = round(herds[ri] * HERD_OCCUPIED_DECAY, 4)
            continue
        held.setdefault(ci, []).append(ri)
    dzud_loss: dict[int, tuple[float, int, float]] = {}  # civ -> (loss, worst region, its loss)
    pasture_loss: dict[int, float] = {}
    for ci in sorted(held):
        ris = held[ci]
        mode = state.mode(ci)
        ks = {ri: seasonal_capacity(world.regions[ri], season) for ri in ris}
        # Transhumance: the herds follow the seasonal pasture across the civ's land.
        total = sum(herds[ri] for ri in ris)
        kt = sum(ks.values())
        if len(ris) > 1 and total > 0 and kt > 0:
            mu = MOBILITY[mode]
            for ri in ris:
                herds[ri] += mu * (total * ks[ri] / kt - herds[ri])
        for ri in ris:
            region = world.regions[ri]
            k = ks[ri]
            h = max(0.0, herds[ri])
            if h < 0.2 * k:
                h += HERD_INFLOW * k
            if h < k:
                h += HERD_GROWTH * h * (1.0 - h / k)
            elif h > k:
                loss = HERD_DIEOFF * (h - k)
                h -= loss
                pasture_loss[ci] = pasture_loss.get(ci, 0.0) + loss
            band = region.latitude_band if region.latitude_band is not None else 0
            if season == 3 and h > 0 and (region.terrain in DZUD_TERRAINS or band >= 3):
                p = DZUD_CHANCE
                if phase == ClimatePhase.COOLING:
                    p *= DZUD_COOLING
                if region.terrain == "tundra" or band >= 3:
                    p *= DZUD_POLAR
                if region.ecology.water < 0.25:
                    p *= DZUD_DRY
                rng = _rng(world, "dzud", ri)
                if rng.random() < p:
                    loss = h * rng.uniform(*DZUD_LOSS)
                    h -= loss
                    total_loss, worst, worst_loss = dzud_loss.get(ci, (0.0, ri, 0.0))
                    if loss > worst_loss:
                        worst, worst_loss = ri, loss
                    dzud_loss[ci] = (total_loss + loss, worst, worst_loss)
            herds[ri] = round(max(0.0, h), 4)
    civs = world.civilizations
    for ci in sorted(dzud_loss):
        loss, ri, _ = dzud_loss[ci]
        _bump(state, "herds_lost_dzud", round(loss, 4))
        if loss >= DZUD_EVENT_MIN:
            _bump(state, "dzuds")
            civ = civs[ci]
            _emit(t, "dzud", [civ.name],
                  f"A dzud winter kills {loss:.0f} head of {_poss('the ' + civ.name)} herds around "
                  f"{world.regions[ri].name}.",
                  importance=5, region=world.regions[ri].name,
                  causes=(prov.recall(world, prov.key("drought", civ.name), within=12),))
    for ci in sorted(pasture_loss):
        loss = pasture_loss[ci]
        _bump(state, "herds_lost_pasture", round(loss, 4))
        civ = civs[ci]
        drought = prov.recall(world, prov.key("drought", civ.name), within=10)
        if loss >= PASTURE_EVENT_MIN and (phase == ClimatePhase.DROUGHT or drought is not None):
            ri = max(held[ci], key=lambda r: (state.herds[r], -r))
            _emit(t, "pasture_drought", [civ.name],
                  f"The pastures of the {civ.name} wither; {loss:.0f} head perish.",
                  importance=4, region=world.regions[ri].name, causes=(drought,))


def herd_ratio(world, ci: int) -> float:
    """A civ's herd against its pasture (1 = full)."""
    state = world.nomads
    civ = world.civilizations[ci]
    index = _region_index(world)
    region_map = world.region_map
    total = cap = 0.0
    for name in civ.regions:
        ri = index.get(name)
        if ri is None:
            continue
        total += state.herds[ri]
        cap += capacity(region_map[name])
    return total / cap if cap > 0 else 0.0


# --- loose hold ---------------------------------------------------------------------------

def _loose_hold(t: _Tick) -> None:
    """Nomads move on from pasture that has stood empty: the region is released."""
    from chronicler import provenance as prov
    world, state = t.world, t.state
    index = world.civ_index_map
    abandoned = False
    for ri, region in enumerate(world.regions):
        ci = index.get(region.controller, -1) if region.controller else -1
        if ci < 0 or state.mode(ci) != NOMADIC:
            state.dry[ri] = 0
            continue
        civ = world.civilizations[ci]
        if state.herds[ri] <= LOOSE_HERD * capacity(region):
            state.dry[ri] += 1
        else:
            state.dry[ri] = 0
        if (state.dry[ri] < LOOSE_TURNS or len(civ.regions) < 2 or civ.capital_region == region.name
                or region.population > LOOSE_POP or region.occupied_by is not None
                or any(i.active for i in region.infrastructure)
                or any(s.status.value in ("active", "dissolving") for s in region.settlements)):
            continue
        civ.regions = [n for n in civ.regions if n != region.name]
        region.controller = None
        region._controller_changed_this_turn = True
        state.dry[ri] = 0
        state.herds[ri] = 0.0
        abandoned = True
        _bump(state, "pastures_abandoned")
        _emit(t, "pasture_abandoned", [civ.name],
              f"The {civ.name} drive their herds away from the empty pastures of {region.name}.",
              importance=3, region=region.name,
              causes=(prov.recall(world, prov.key("herd_loss", civ.name), within=LOOSE_TURNS * 2),))
    if abandoned:
        world.invalidate_trade_route_cache()


# --- asabiya --------------------------------------------------------------------------------

def _asabiya(t: _Tick) -> None:
    world, state = t.world, t.state
    index = world.civ_index_map
    for region in world.regions:
        ci = index.get(region.controller, -1) if region.controller else -1
        mode = state.mode(ci)
        if ci < 0 or mode == SEDENTARY:
            continue
        p = suitability(region)
        a = region.asabiya_state.asabiya
        if mode == NOMADIC and p >= 0.5:
            a += NOMAD_ASABIYA_GROWTH * a * (1.0 - a)
        if p < 0.4:
            a -= SETTLED_ASABIYA_DECAY * (1.0 - p)
        region.asabiya_state.asabiya = round(max(0.0, min(1.0, a)), 4)


# --- sedentarization ------------------------------------------------------------------------

def _sedentarize(t: _Tick) -> None:
    world, state = t.world, t.state
    for ci, civ in enumerate(world.civilizations):
        mode = state.mode(ci)
        if mode == SEDENTARY or not civ.regions:
            continue
        floor = NOMADIC_FLOOR if mode == NOMADIC else AGRO_FLOOR
        if pastoral_share(world, civ) < floor:
            state.settle[ci] += 1
        else:
            state.settle[ci] = max(0, state.settle[ci] - SETTLE_RECOVERY)
        if state.settle[ci] < GENERATION:
            continue
        new_mode = mode - 1
        state.modes[ci] = new_mode
        state.mode_turn[ci] = world.turn
        state.settle[ci] = 0
        _bump(state, "sedentarizations")
        conquests = [c for c in state.conquests
                     if c.civ == ci and c.event_id and world.turn - c.turn <= CONQUEST_MEMORY]
        causes = [c.event_id for c in conquests[-3:]]
        hordes = [h for h in state.hordes if ci in h.members and h.event_id]
        if hordes:
            causes.append(hordes[-1].event_id)
        if new_mode == AGRO_PASTORAL:
            desc = (f"A generation after taking the farmland, the {civ.name} take to the plough; "
                    f"fewer of them follow the herds.")
        else:
            desc = f"The {civ.name} settle in towns and fields; the herds pass to a few clans."
        for name in civ.regions:
            region = world.region_map.get(name)
            if region is not None:
                region.asabiya_state.asabiya = round(region.asabiya_state.asabiya * SEDENTARIZATION_ASABIYA, 4)
        ev = _emit(t, "sedentarization", [civ.name], desc, importance=6,
                   region=civ.capital_region, causes=causes)
        state.mode_event[ci] = ev.event_id


# --- tribute ----------------------------------------------------------------------------------

def _pact_between(state: NomadState, payer: int, recipient: int) -> TributePact | None:
    for pact in state.tributes:
        if pact.status == "active" and pact.payer == payer and pact.recipient == recipient:
            return pact
    return None


def _close_pact(t: _Tick, pact: TributePact, status: str, description: str | None,
                importance: int = 4, causes: Iterable[str | None] = ()) -> None:
    world = t.world
    pact.status = status
    pact.end_turn = world.turn
    if description is None:
        return
    civs = world.civilizations
    ev = _emit(t, "tribute_ended", [civs[pact.payer].name, civs[pact.recipient].name], description,
               importance=importance, causes=(pact.event_id, *causes))
    pact.end_event_id = ev.event_id


def _tributes(t: _Tick) -> None:
    world, state = t.world, t.state
    civs = world.civilizations
    for pact in sorted(state.active_tributes(), key=lambda p: p.pact_id):
        payer, recipient = civs[pact.payer], civs[pact.recipient]
        if not payer.regions or not recipient.regions:
            _close_pact(t, pact, "ended", None)
            continue
        if _at_war(world, payer.name, recipient.name):
            from chronicler import provenance as prov
            _close_pact(t, pact, "ended", f"War between {payer.name} and {recipient.name} ends the tribute.",
                        causes=(prov.recall(world, prov.war_key(payer.name, recipient.name)),))
            continue
        if pact.start_turn >= world.turn:
            continue
        if (_power(payer) > TRIBUTE_REPUDIATE_RATIO * _power(recipient)
                and _rng(world, "repudiate", pact.pact_id).random() < TRIBUTE_REPUDIATE_CHANCE):
            _bump(state, "tributes_repudiated")
            _disposition_step(world, recipient.name, payer.name)
            _close_pact(t, pact, "repudiated",
                        f"Grown strong, {payer.name} refuses further tribute to {recipient.name}.",
                        importance=6)
            world.invalidate_trade_route_cache()
            continue
        if world.turn - pact.start_turn > TRIBUTE_TERM:
            _close_pact(t, pact, "expired",
                        f"The tribute {payer.name} paid {recipient.name} lapses after {TRIBUTE_TERM} years.",
                        importance=3)
            continue
        paid = _spend(t, payer, pact.amount)
        if paid:
            _add_stat(t, recipient, "treasury", paid, "keep")
        pact.paid += paid
        _bump(state, "tribute_paid", paid)
        if paid < pact.amount:
            pact.missed += 1
            if pact.missed >= TRIBUTE_MAX_MISSED:
                _close_pact(t, pact, "lapsed",
                            f"{payer.name} can no longer pay its tribute to {recipient.name}.",
                            importance=4)


def _new_tributes(t: _Tick) -> None:
    """Settled peoples raided again and again, and too weak to fight, pay."""
    world, state = t.world, t.state
    civs = world.civilizations
    recent: dict[tuple[int, int], list[Raid]] = {}
    for raid in state.raids:
        if raid.success and world.turn - raid.turn < TRIBUTE_WINDOW:
            recent.setdefault((raid.raider, raid.target), []).append(raid)
    for (ri, ti), raids in sorted(recent.items()):
        if len(raids) < TRIBUTE_RAIDS or raids[-1].turn != world.turn:
            continue
        raider, target = civs[ri], civs[ti]
        if not raider.regions or not target.regions or _pact_between(state, ti, ri) is not None:
            continue
        if _at_war(world, raider.name, target.name):
            continue
        if _power(target) >= TRIBUTE_POWER * _power(raider):
            continue
        trait = target.leader.trait
        chance = (TRIBUTE_CHANCE_CAUTIOUS if trait in CAUTIOUS_TRAITS
                  else TRIBUTE_CHANCE_BOLD if trait in BOLD_TRAITS else TRIBUTE_CHANCE)
        if _rng(world, "tribute", ti, ri).random() >= chance:
            continue
        amount = max(TRIBUTE_MIN, min(TRIBUTE_MAX, int(target.economy * TRIBUTE_RATE) + 1))
        pact = TributePact(pact_id=state.next_pact_id, payer=ti, recipient=ri, amount=amount,
                           start_turn=world.turn)
        state.next_pact_id += 1
        state.tributes.append(pact)
        _bump(state, "tributes")
        ev = _emit(t, "tribute_agreed", [target.name, raider.name],
                   f"{target.name} agrees to pay {raider.name} {amount} a year to spare its borders.",
                   importance=6, causes=[r.event_id for r in raids[-3:]])
        pact.event_id = ev.event_id


# --- raids ------------------------------------------------------------------------------------

def _raid_targets(t: _Tick, ci: int) -> list[tuple[int, int, int]]:
    """(target region, target civ, raider border region) candidates, sorted."""
    from chronicler.models import Disposition
    world, state = t.world, t.state
    civ = world.civilizations[ci]
    mode = state.mode(ci)
    index = world.civ_index_map
    rels = world.relationships.get(civ.name, {})
    fed = _federation_of(world, civ.name)
    subjects = _subject_pairs(world)
    from chronicler.diplomacy import PROTECTING_KINDS, diplomacy_enabled, treaties_between
    diplomacy = diplomacy_enabled(world)
    region_map = world.region_map
    best: dict[tuple[int, int], int] = {}
    for name in civ.regions:
        home = region_map.get(name)
        if home is None or (home.occupied_by is not None and home.occupied_by != civ.name):
            continue
        hi = t.index[name]
        for other in _land_neighbors(world, home, t.lanes):
            owner = other.controller
            if owner is None or owner == civ.name or other.occupied_by not in (None, owner):
                continue
            ti = index.get(owner)
            if ti is None:
                continue
            target = world.civilizations[ti]
            if not target.regions or state.mode(ti) >= mode:
                continue
            if fed is not None and owner in fed.members:
                continue
            if (civ.name, owner) in subjects or _at_war(world, civ.name, owner):
                continue
            if _pact_between(state, ti, ci) is not None or _in_truce(world, civ.name, owner):
                continue
            rel = rels.get(owner)
            back = world.relationships.get(owner, {}).get(civ.name)
            if rel is not None and rel.disposition in (Disposition.FRIENDLY, Disposition.ALLIED):
                continue
            if back is not None and back.disposition == Disposition.ALLIED:
                continue
            if diplomacy and treaties_between(world, ci, ti, PROTECTING_KINDS):
                continue
            key = (t.index[other.name], ti)
            prev = best.get(key)
            if prev is None or (home.population, -hi) > (world.regions[prev].population, -prev):
                best[key] = hi
    return [(tr, ti, best[(tr, ti)]) for tr, ti in sorted(best)]


def raid_chance(world, ci: int) -> float:
    state = world.nomads
    civ = world.civilizations[ci]
    mode = state.mode(ci)
    if mode == SEDENTARY:
        return 0.0
    hunger = max(0.0, min(1.0, (0.6 - herd_ratio(world, ci)) / 0.6))
    region_map = world.region_map
    from chronicler.ecology import food_crisis_weight
    crisis = max((food_crisis_weight(region_map[n]) for n in civ.regions if n in region_map),
                 default=0.0)
    if crisis > 0.0:
        hunger = max(hunger, 0.5 * crisis)
    p = RAID_BASE[mode] * (1.0 + RAID_HUNGER * hunger) * (0.5 + max(0.0, min(1.0, civ.asabiya)))
    if _horde_of(state, ci) is not None:
        p *= RAID_HORDE
    return min(RAID_MAX, p)


def _combat_factor(world, civ, enemy, attacking: bool) -> float:
    from chronicler.tech import tech_war_multiplier
    from chronicler.techniques_state import techniques_on
    f = tech_war_multiplier(civ.tech_era, enemy.tech_era)
    if techniques_on(world):
        from chronicler.techniques import military_factor
        f *= military_factor(world, civ, attacking)
    return f


def _raids(t: _Tick) -> None:
    from chronicler import provenance as prov
    from chronicler.war.battles import defense_multiplier, garrison_size, quality
    world, state = t.world, t.state
    civs = world.civilizations
    for ci, civ in enumerate(civs):
        mode = state.mode(ci)
        if mode == SEDENTARY or not civ.regions:
            continue
        targets = _raid_targets(t, ci)
        if not targets:
            continue
        rng = _rng(world, "raid", ci)
        if rng.random() >= raid_chance(world, ci):
            continue
        weights = [world.regions[tr].population + 10 for tr, _, _ in targets]
        tr, ti, hi = rng.choices(targets, weights=weights, k=1)[0]
        region, home, target = world.regions[tr], world.regions[hi], civs[ti]
        raiders = max(MIN_RAIDERS, int(civ.military * RAID_MILITARY_SHARE
                                       + home.population * RAID_POP_PERMILLE / 1000))
        attack = (raiders * quality(civ, RAID_MORALE, attacking=True) * MOUNTED[mode]
                  * _combat_factor(world, civ, target, True) * rng.uniform(0.85, 1.15))
        garrison = garrison_size(world, region, target)
        defense = (garrison * quality(target, 600, attacking=False)
                   * _combat_factor(world, target, civ, False)
                   * defense_multiplier(world, region, target.name) * rng.uniform(0.85, 1.15))
        success = attack >= defense
        loot = killed = 0
        if success:
            ratio = attack / max(defense, 1e-9)
            cap = min(RAID_LOOT_CAP, int(_projected_treasury(t, target) * RAID_LOOT_SHARE))
            loot = _spend(t, target, max(0, int(cap * min(1.0, ratio / 1.5))))
            if loot:
                _add_stat(t, civ, "treasury", loot, "keep")
            killed = _kill(t, target, [region.name], max(1, int(region.population * RAID_KILL_SHARE)))
            # One-turn signal for the agents' safety need (read and cleared by
            # agent_bridge.build_region_batch).
            region._raided_this_turn = True
            from chronicler.emergence import get_severity_multiplier
            _add_stat(t, target, "stability",
                      -int(RAID_STABILITY * get_severity_multiplier(target, world)), "signal")
            losses = int(raiders * RAID_WIN_LOSS)
        else:
            losses = max(1, int(raiders * RAID_REPULSED_LOSS))
        if losses:
            _kill(t, civ, [home.name], losses)
            mil = int(round(losses * RAID_MILITARY_PER_RAIDER))
            if mil:
                _add_stat(t, civ, "military", -mil, "guard-action")
        _disposition_step(world, target.name, civ.name)
        _disposition_step(world, civ.name, target.name, only_above="suspicious")
        world.invalidate_trade_route_cache()
        horde = _horde_of(state, ci)
        last_end = None
        for pact in reversed(state.tributes):
            if pact.payer == ti and pact.recipient == ci and pact.end_turn is not None:
                if world.turn - pact.end_turn <= 10:
                    last_end = pact.end_event_id
                break
        causes = (prov.recall(world, prov.key("herd_loss", civ.name), within=12),
                  prov.open_episode(world, "famine", home.name),
                  horde.event_id if horde is not None else None, last_end)
        if success:
            _bump(state, "raids")
            _bump(state, "plunder", loot)
            _bump(state, "raid_deaths", killed)
            took = [f"carrying off {loot} in plunder"] if loot else []
            if killed:
                took.append(f"killing {killed} of {_poss(target.name)} people")
            what = " and ".join(took) if took else "but find little to take"
            ev = _emit(t, "raid", [civ.name, target.name],
                       f"Riders of the {civ.name} raid {region.name}, {what}.",
                       importance=5, region=region.name, causes=causes)
        else:
            _bump(state, "raids_repulsed")
            ev = _emit(t, "raid_repulsed", [civ.name, target.name],
                       f"{target.name} drives off a raid by the {civ.name} on {region.name}.",
                       importance=4, region=region.name, causes=causes)
        state.raids.append(Raid(turn=world.turn, raider=ci, target=ti, region=tr, raiders=raiders,
                                success=success, loot=loot, killed=killed, event_id=ev.event_id))


# --- hordes: formation and conquest waves ---------------------------------------------------

def _reach(world, civ: "Civilization", lanes: set, depth: int) -> set[str]:
    """Civs controlling land within ``depth`` hops of ``civ``'s territory."""
    region_map = world.region_map
    seen = {n for n in civ.regions if n in region_map}
    frontier = deque((n, 0) for n in sorted(seen))
    out = set()
    while frontier:
        name, d = frontier.popleft()
        if d >= depth:
            continue
        for other in _land_neighbors(world, region_map[name], lanes):
            if other.name in seen:
                continue
            seen.add(other.name)
            if other.controller is not None and other.controller != civ.name:
                out.add(other.controller)
            frontier.append((other.name, d + 1))
    return out


def _horde_name(world, rng: random.Random, civ: "Civilization") -> str:
    taken = {f.name for f in world.federations} | {h.name for h in world.nomads.hordes}
    adj = rng.choice(HORDE_ADJECTIVES)
    name = f"The {adj} Horde"
    if name in taken:
        name = f"The {adj} Horde of the {civ.name}"
    n = 2
    base = name
    while name in taken:
        name = f"{base} ({n})"
        n += 1
    return name


def _form_hordes(t: _Tick) -> None:
    from chronicler import provenance as prov
    from chronicler.models import Disposition, Federation
    world, state = t.world, t.state
    civs = world.civilizations
    index = world.civ_index_map
    taken: set[int] = {m for h in state.active_hordes() for m in h.members}
    for ci, civ in enumerate(civs):
        if (state.mode(ci) != NOMADIC or not civ.regions or ci in taken
                or _is_vassal(world, civ.name)
                or civ.asabiya < HORDE_ASABIYA or civ.stability < HORDE_STABILITY
                or not civ.leader.alive or world.turn - civ.leader.reign_start < 2):
            continue
        chance = HORDE_CHANCE * (HORDE_STRONG_TRAIT if civ.leader.trait in STRONG_TRAITS else 1.0)
        rng = _rng(world, "horde", ci)
        if rng.random() >= chance:
            continue
        fed = _federation_of(world, civ.name)
        if fed is not None:
            _horde_from_federation(t, ci, civ, fed, rng, taken)
            continue
        khan_power = _power(civ)
        followers: list[int] = []
        for name in sorted(_reach(world, civ, t.lanes, HORDE_REACH), key=lambda n: index.get(n, 0)):
            fi = index.get(name)
            if fi is None or fi in taken:
                continue
            other = civs[fi]
            if (not other.regions or state.mode(fi) == SEDENTARY
                    or _federation_of(world, name) is not None or _is_vassal(world, name)
                    or any(vr.vassal == civ.name and vr.overlord == name for vr in world.vassal_relations)
                    or _at_war(world, civ.name, name)
                    or any(_at_war(world, civs[f].name, name) for f in followers)
                    or not _could_be_sworn(world, civ.name, name)):
                continue
            ratio = khan_power / max(_power(other), 1e-9)
            if ratio <= 1.0:
                continue
            submit = min(SUBMIT_MAX, SUBMIT_BASE + SUBMIT_SLOPE * (ratio - 1.0))
            if _rng(world, "submit", ci, fi).random() < submit:
                followers.append(fi)
        if not followers:
            continue
        name = _horde_name(world, rng, civ)
        members = [ci] + followers
        world.federations.append(Federation(name=name, members=[civs[m].name for m in members],
                                            founded_turn=world.turn))
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                _set_disposition(world, civs[a].name, civs[b].name, Disposition.ALLIED)
        world.invalidate_trade_route_cache()
        horde = Horde(horde_id=state.next_horde_id, name=name, khan=ci, khan_leader=civ.leader.name,
                      founded_turn=world.turn, members=members, peak_members=len(members))
        state.next_horde_id += 1
        state.hordes.append(horde)
        taken.update(members)
        _bump(state, "hordes_formed")
        raids = [r.event_id for r in state.raids
                 if r.raider == ci and r.success and r.event_id and world.turn - r.turn <= 20][-2:]
        followers_text = ", ".join(civs[f].name for f in followers)
        verb = "swears" if len(followers) == 1 else "swear"
        ev = _emit(t, "horde_formed", [civ.name, *(civs[f].name for f in followers)],
                   f"{civ.leader.name} of the {civ.name} unites the clans: {followers_text} "
                   f"{verb} allegiance to {name}.",
                   importance=8, region=civ.capital_region,
                   causes=(prov.recall(world, prov.key("war_win", civ.name), within=20), *raids))
        horde.event_id = ev.event_id


def _could_be_sworn(world, a: str, b: str) -> bool:
    """Neither side hostile, and (with diplomacy on) no memory that caps their
    bond below friendly: the federation rule would shed such a clan at once."""
    from chronicler.models import Disposition
    for x, y in ((a, b), (b, a)):
        rel = world.relationships.get(x, {}).get(y)
        if rel is not None and rel.disposition == Disposition.HOSTILE:
            return False
    from chronicler.diplomacy import diplomacy_enabled
    if not diplomacy_enabled(world):
        return True
    from chronicler.diplomacy import disposition_ceiling, memory
    order = list(Disposition)
    friendly = order.index(Disposition.FRIENDLY)
    return all(order.index(disposition_ceiling(memory(world, x, y))) >= friendly
               for x, y in ((a, b), (b, a)))


def _horde_from_federation(t: _Tick, ci: int, civ: "Civilization", fed, rng: random.Random,
                           taken: set[int]) -> None:
    """The strongest member of a federation, a nomad, takes command of it: the
    federation (renamed) becomes the horde, its members the khan's allies."""
    from chronicler import provenance as prov
    world, state = t.world, t.state
    index = world.civ_index_map
    civs = world.civilizations
    members = [index[m] for m in fed.members if m in index and civs[index[m]].regions]
    others = [m for m in members if m != ci]
    if not others or any(m in taken for m in members):
        return
    khan_power = _power(civ)
    if any(_power(civs[m]) >= khan_power for m in others):
        return
    old_name = fed.name
    name = _horde_name(world, rng, civ)
    fed.name = name
    ordered = [ci] + sorted(others)
    horde = Horde(horde_id=state.next_horde_id, name=name, khan=ci, khan_leader=civ.leader.name,
                  founded_turn=world.turn, members=ordered, peak_members=len(ordered))
    state.next_horde_id += 1
    state.hordes.append(horde)
    taken.update(ordered)
    _bump(state, "hordes_formed")
    raids = [r.event_id for r in state.raids
             if r.raider == ci and r.success and r.event_id and world.turn - r.turn <= 20][-2:]
    ev = _emit(t, "horde_formed", [civs[m].name for m in ordered],
               f"{civ.leader.name} of the {civ.name} takes command of {old_name}; "
               f"it rides as {name}.",
               importance=8, region=civ.capital_region,
               causes=(prov.recall(world, prov.key("federation", civ.name)),
                       prov.recall(world, prov.key("war_win", civ.name), within=20), *raids))
    horde.event_id = ev.event_id


def _settled_targets(t: _Tick, horde: Horde, members: list["Civilization"],
                     riders: Iterable["Civilization"]) -> list["Civilization"]:
    world, state = t.world, t.state
    index = world.civ_index_map
    names = {m.name for m in members}
    subjects = _subject_pairs(world)
    out = set()
    for rider in riders:
        for name in _neighbor_civs(world, rider, t.lanes):
            ti = index.get(name)
            if ti is None or name in names or state.mode(ti) != SEDENTARY:
                continue
            if not world.civilizations[ti].regions:
                continue
            if any((m.name, name) in subjects for m in members):
                continue
            if any(_pact_between(state, ti, index[m.name]) is not None for m in members):
                continue
            out.add(ti)
    return [world.civilizations[i] for i in sorted(out)]


def _ride(t: _Tick, civ: "Civilization", target: "Civilization") -> "Event | None":
    """Go to war through the campaign WAR path (the action's own resolution)."""
    world = t.world
    if not world.campaigns_enabled or _in_truce(world, civ.name, target.name):
        return None
    from chronicler.diplomacy import diplomacy_enabled
    broken = ()
    if diplomacy_enabled(world):
        from chronicler.diplomacy import war_guard
        allowed, broken = war_guard(world, civ, target)
        if not allowed:
            return None
    from chronicler.war.runtime import declare_or_press_war
    before = _war_enemies(world, civ.name)
    event = declare_or_press_war(civ, target, world, acc=t.acc)
    if target.name in before or target.name not in _war_enemies(world, civ.name):
        return None
    if diplomacy_enabled(world):
        from chronicler.diplomacy import on_war_declared
        world.events_timeline.extend(on_war_declared(
            world, civ, target, broken=broken, acc=t.acc, enemies_before=before))
    return event


def _conquest_waves(t: _Tick) -> None:
    """The horde rides: the khan opens a war on a settled neighbour and the
    members adjacent to the enemy join it."""
    from chronicler import provenance as prov
    world, state = t.world, t.state
    if not world.campaigns_enabled:
        return
    civs = world.civilizations
    for horde in sorted(state.active_hordes(), key=lambda h: h.horde_id):
        members = [civs[m] for m in horde.members if m < len(civs) and civs[m].regions]
        khan = civs[horde.khan]
        if not khan.regions:
            continue
        settled_enemies = sorted(
            n for n in _war_enemies(world, khan.name)
            if n in world.civ_map and state.mode(world.civ_index_map[n]) == SEDENTARY)
        if not settled_enemies:
            targets = _settled_targets(t, horde, members, [khan])
            rng = _rng(world, "wave", horde.horde_id)
            if targets and rng.random() < HORDE_WAVE_CHANCE:
                weights = [(c.population + max(0, c.treasury) / 10 + 1) / max(_power(c), 1.0) for c in targets]
                target = rng.choices(targets, weights=weights, k=1)[0]
                war_event = _ride(t, khan, target)
                if war_event is not None:
                    t.events.append(war_event)
                    horde.wars += 1
                    _bump(state, "horde_wars")
                    _emit(t, "horde_rides", [khan.name, target.name],
                          f"{horde.name} rides against {target.name}.", importance=7,
                          causes=(prov.recall(world, prov.war_key(khan.name, target.name)), horde.event_id))
                    settled_enemies = [target.name]
        for enemy_name in settled_enemies:
            enemy = world.civ_map[enemy_name]
            for member in members:
                if member.name == khan.name or _at_war(world, member.name, enemy_name):
                    continue
                if enemy_name not in _neighbor_civs(world, member, t.lanes):
                    continue
                mi = world.civ_index_map[member.name]
                if _rng(world, "ride", horde.horde_id, mi, world.civ_index_map[enemy_name]).random() >= HORDE_RIDE_CHANCE:
                    continue
                war_event = _ride(t, member, enemy)
                if war_event is None:
                    continue
                t.events.append(war_event)
                horde.wars += 1
                _bump(state, "horde_rides")
                _emit(t, "horde_rides", [member.name, khan.name, enemy_name],
                      f"The {member.name} ride with {horde.name} against {enemy_name}.", importance=6,
                      causes=(prov.recall(world, prov.war_key(member.name, enemy_name)),
                              prov.recall(world, prov.war_key(khan.name, enemy_name)), horde.event_id))


def _prune(t: _Tick) -> None:
    world, state = t.world, t.state
    turn = world.turn
    state.raids = [r for r in state.raids if turn - r.turn < RAID_MEMORY]
    state.conquests = [c for c in state.conquests if turn - c.turn <= CONQUEST_MEMORY]
    state.tributes = [p for p in state.tributes
                      if p.status == "active" or p.end_turn is None or turn - p.end_turn <= TRIBUTE_HISTORY]


# ---------------------------------------------------------------------------
# Viewer / analytics
# ---------------------------------------------------------------------------

def snapshot_summary(world) -> dict:
    """Per-turn nomad summary for ``TurnSnapshot.nomads``."""
    state = world.nomads
    civs = world.civilizations
    herds_by_civ: dict[str, float] = {}
    for ri, region in enumerate(world.regions):
        if region.controller is not None and ri < len(state.herds) and state.herds[ri] > 0:
            herds_by_civ[region.controller] = herds_by_civ.get(region.controller, 0.0) + state.herds[ri]
    return {
        "modes": {c.name: SUBSISTENCE_MODES[state.mode(i)] for i, c in enumerate(civs) if c.regions},
        "herds": {name: round(v, 1) for name, v in sorted(herds_by_civ.items())},
        "herd_total": round(sum(state.herds), 1),
        "tributes": [{"payer": civs[p.payer].name, "recipient": civs[p.recipient].name, "amount": p.amount}
                     for p in state.active_tributes()],
        "hordes": [{"name": h.name, "khan": civs[h.khan].name,
                    "members": [civs[m].name for m in h.members if m < len(civs)]}
                   for h in state.active_hordes()],
        "counters": {k: state.counters.get(k, 0) for k in COUNTER_KEYS},
    }


def extract_nomad_metrics(bundles: list[dict]) -> dict:
    """Per-run nomad metrics from bundles that carry ``history[n].nomads``."""
    runs = []
    for bundle in bundles:
        rows = [h["nomads"] for h in bundle.get("history", []) if h.get("nomads")]
        if not rows:
            continue
        last = rows[-1]
        counters = last.get("counters", {})
        runs.append({
            "nomadic_civs_peak": max(sum(1 for m in r["modes"].values() if m == "nomadic") for r in rows),
            "pastoral_civs_peak": max(sum(1 for m in r["modes"].values() if m != "sedentary") for r in rows),
            "herd_mean": round(sum(r["herd_total"] for r in rows) / len(rows), 1),
            "herd_final": last["herd_total"],
            **{k: counters.get(k, 0) for k in COUNTER_KEYS},
        })
    if not runs:
        return {"runs": []}
    keys = [k for k in runs[0] if isinstance(runs[0][k], (int, float))]
    means = {k: round(sum(r[k] for r in runs) / len(runs), 3) for k in keys}
    return {"runs": runs, "means": means}
