"""A conserved water account on the drainage graph (``--watershed``, default off).

``--watershed-mode record_only`` (B1, S1-A, the default) records the account
beside the water index and changes nothing; ``--watershed-mode flow`` (B2)
makes the derived index the index the simulation uses, replacing (never
stacking on) the native water climate terms, the irrigation water bonus and
the downstream deforestation cascade, and lets each flood event act once at
its onset (native ecology only). See :mod:`chronicler.livelihoods` and
docs/integration/watershed.md.

Graph. Built once at enable from the world's saved procedural geography
(``world.geography``, ``Region.geo``): a coastal region drains to the sea
(any bordering open water: ocean, sea or lake); an inland region drains to
its lowest land neighbour (``Region.adjacencies`` without
``geography.sea_lanes``) that is lower than itself, ties to the lower
index; an inland region with no lower land neighbour is a sink. Elevation
strictly falls along every edge, so the graph is acyclic and every region
has exactly one destination. The graph must reproduce every persisted river
step (``world.rivers``), and the rivers themselves must be well formed (no
step and its reverse, no cycle, one downstream target per region), or
enable is refused. Template worlds have no elevation and are refused with a
clear message, at startup and on a state-file resume: an intentional,
documented boundary.

Account (per turn, in Phase 9, deterministic, float64, no RNG). Water units
(wu): one region's storage capacity without forest cover is
``STORAGE_BASE``. Regions are processed in ``graph.order`` (every region
after all regions that drain into it), so each unit of water leaves a region
by exactly one path and a confluence sums its tributaries' outflows once::

    C   = STORAGE_BASE x (1 + FOREST_RETENTION x cover)            capacity
    X   = (index now - index after the last Phase 9) / span x C     external (e.g. a coastal flood)
    P   = PRECIPITATION_BASE x (0.2 + moisture) x phase factor x (1 - shock)  (+ tundra melt in warming)
    I   = sum of the outflows of the regions draining here          downstream transfer, same turn
    A   = S + P + X_in - X_out + I
    E   = min(A, EVAPORATION_BASE x phase x terrain x (1 + TRANSPIRATION x cover))
    W   = min(A - E, IRRIGATION_DEMAND) with an active irrigation work, else 0
    S'  = (1 - BASEFLOW) x min(A - E - W, C);  Q = A - E - W - S'   (baseflow and overflow)
    Q  -> I of the destination | outflow to the sea | sink loss (a closed basin evaporates it)

``X_out`` is limited to the storage; any remainder is recorded as unmet
(``external_out_unmet``), never taken from elsewhere. Closure is checked
every turn before anything is committed (relative ``CLOSURE_TOLERANCE``,
``math.fsum``), region by region and in total::

    sum(S' - S) = sum(P + X_in - X_out - E - W) - to_sea - sink_loss

with ``0 <= S' <= C``, every flow non-negative and each region's inflow
equal to the sum of its tributaries' outflows. Cumulative totals close
against the opening storage the same way.

Index. The account derives the water index it would set,
``floor + (cap - floor) x min(1, S'/C + IRRIGATION_WETTING x W/C)`` (``cap``
the terrain's water cap), and records it beside the index the simulation
actually used after the ecology tick (``index_observed``). The opening
storage is ``C x (index - floor)/(cap - floor)``, so the derived index is
continuous at enable and the world-generation river bonus is inside it.

Conditions. A flood event starts on a settled turn whose arrivals ``P + I``
(channel flow; an external inflow is not counted) exceed the region's
channel capacity while no event is open there, and stays open while
arrivals exceed ``flood_recession`` x channel (hysteresis). The channel is
``channel_ratio`` x the normal precipitation of the region's drainage basin
(B1: a fixed ``CHANNEL_CAPACITY``, x ``RIVER_CHANNEL_FACTOR`` on a named river
region). The onset record keeps the arrivals by source, each tributary's
outflow and the upstream cover. A terrain transition of the Phase 9
post-pass that clamps the index to a new cap is recorded as a cap change. A
drought is a run of at least ``DROUGHT_TURNS`` settled turns with ``S'/C``
below ``DROUGHT_FRACTION``; its record keeps the precipitation against the
normal precipitation (the forcing deficit), inflow, evaporation, the
region's and its upstream regions' irrigation withdrawals and the upstream
cover.

``record_only`` changes nothing outside this package's own state and draws
no randomness: :func:`before_ecology` computes and checks the account from
the pre-tick world, :func:`after_ecology` reads the observed index and
commits. A plan left by a failed ecology tick is dropped at the next
planning; nothing was settled. Works in every ecology path (native and the
pure-Python fallback) and every agent mode. Three constants are fitted to the
old index on development worlds; the others are declared or fixed with a
stated reason (``PARAMETERS``).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
from functools import lru_cache
from typing import NamedTuple

from chronicler.watershed_state import (
    COUNTER_KEYS, EVENT_COUNTER_KEYS, FLOW_COUNTER_KEYS, FLOW_KEYS, FRAME_COLUMNS, LAKE, SEA, SINK,
    ActiveConsequence, CapChange, DroughtSpell, ExternalFlow, FloodConsequence, FloodEvent, FloodRecord,
    SupersededFlood, WatershedFrame, WatershedGraph, WatershedState,
)

#: The native ecology terms ``flow`` replaces, switched off exactly once, in the
#: native ``EcologyConfig`` (``agent_bridge.configure_ecology_runtime``): the
#: climate water terms, the irrigation water bonus and its drought multiplier,
#: and the downstream deforestation cascade. The harvest shock's water loss is
#: switched off through the climate config (the crops keep the trend share).
FLOW_REPLACED_TERMS: dict[str, float] = {
    "water_drought": 0.0, "water_recovery": 0.0, "cooling_water_loss": 0.0, "warming_tundra_water_gain": 0.0,
    "irrigation_water_bonus": 0.0, "irrigation_drought_mult": 1.0, "deforestation_water_loss": 0.0,
}
FLOW_NATIVE_REFUSAL = (
    "--watershed-mode flow requires the native ecology (the compiled chronicler_agents extension): it "
    "replaces the native water terms, and the pure-Python fallback's terms cannot be replaced")

MODES = ("record_only", "flow")
SCHEMA_VERSION = 1
#: The slice that defined the record this code writes (both modes): B2 records
#: carry flood events, terrain cap changes and the B2 constants; B1 records
#: (record_only only) are still read by the viewer.
STAGE = "B2"
STAGES = {"record_only": STAGE, "flow": STAGE}


@dataclass(frozen=True)
class Parameters:
    """The account's declared constants (water units, wu, per turn unless noted)."""

    #: Storage capacity of a region without forest cover.
    storage_base: float = 1.0
    #: Forest soils hold more: capacity x (1 + forest_retention x cover).
    forest_retention: float = 0.5
    #: Precipitation at (0.2 + moisture) = 1, phase factor 1, no shock.
    precipitation_base: float = 0.1
    #: Precipitation factor by global climate phase (scaled by the region's
    #: latitude exposure and the climate trend share).
    phase_precipitation: dict = field(default_factory=lambda: {
        "temperate": 1.0, "warming": 0.85, "drought": 0.3, "cooling": 0.6})
    #: A bad harvest year of depth h cuts precipitation by h x this.
    shock_precipitation: float = 1.0
    #: Snowmelt added to tundra precipitation in the warming phase.
    tundra_melt: float = 0.05
    #: Potential evapotranspiration at phase factor 1.
    evaporation_base: float = 0.03
    phase_evaporation: dict = field(default_factory=lambda: {
        "temperate": 1.0, "warming": 1.3, "drought": 1.6, "cooling": 0.7})
    terrain_evaporation: dict = field(default_factory=lambda: {"desert": 1.6, "steppe": 1.25, "tundra": 0.5})
    #: Forests transpire more: evaporation x (1 + transpiration x cover).
    transpiration: float = 0.3
    #: Share of storage released downstream each turn (overflow above capacity also leaves).
    baseflow: float = 0.05
    #: Consumptive irrigation use of a region with an active irrigation work (service 1.0).
    irrigation_demand: float = 0.02
    #: The derived index counts irrigation water applied to fields: W/C x this.
    irrigation_wetting: float = 1.0
    #: Arrivals a region's channel passes without flooding ...
    channel_capacity: float = 0.25
    #: ... larger on a named river region (B1's fixed channel).
    river_channel_factor: float = 2.0
    #: B2: when set, a region's channel is this multiple of its drainage basin's normal
    #: precipitation (the region's and every region's upstream, at phase factor 1 and no
    #: shock), replacing the fixed channel: channels carry what their basin normally
    #: delivers, so a confluence is not a permanent flood site.
    channel_ratio: float | None = None
    #: A drought: storage below this fraction of capacity ...
    drought_fraction: float = 0.2
    #: ... for at least this many consecutive settled turns.
    drought_turns: int = 3
    #: Upstream regions below this cover count as deforested in a flood record.
    deforested_cover: float = 0.2
    #: The water index floor (``ecology._FLOOR_WATER``).
    index_floor: float = 0.10
    #: Relative closure tolerance of every per-turn and cumulative check.
    closure_tolerance: float = 1e-9
    #: ``flow`` mode: a flood's capacity modifier (the old river flood's), ...
    flood_capacity_modifier: float = 0.85
    #: ... the silt it adds to the soil (the old river flood's), ...
    flood_silt: float = 0.15
    #: ... and the excess (wu) from which it lasts two turns instead of one.
    flood_long_excess: float = 0.1
    #: A flood event, once started (arrivals above the channel), stays open
    #: while arrivals exceed this share of the channel (hysteresis).
    flood_recession: float = 0.75

    def as_dict(self) -> dict:
        return {f.name: (dict(v) if isinstance(v := getattr(self, f.name), dict) else v) for f in fields(self)}


#: The B1 (S1-A) constants, declared and uncalibrated; kept for comparison.
B1_PARAMETERS = Parameters()
#: The constants in force (B2, refit after review): three fitted in ``record_only``
#: on the procedural development worlds 7, 11, 13, 17, 21, 31, 302 and 303 (32x10,
#: 400 turns, hybrid) by ``scripts/watershed_replay.py fit --form core``
#: (precipitation_base, baseflow, cooling precipitation); every other constant is
#: fixed with a stated reason (docs/integration/watershed.md, "Calibration"):
#: evaporation 0.03 (only the precipitation/evaporation ratio is identified),
#: warming factors 1.0 (the old index has no warming-phase water term), drought
#: precipitation -1.0 and evaporation 4.0 (their physical limits, where every
#: freer fit put them), cooling evaporation 1.0, harvest shock 1.0 and the forest
#: linkage (retention 0.5, transpiration 0.3) at their declared values. The
#: channel is the basin's normal precipitation (``channel_ratio`` 1.0, not fitted).
#: Leave-two-out cross-validation and a 64x16 transfer check are reported there.
PARAMETERS = Parameters(
    precipitation_base=0.3488, evaporation_base=0.03, baseflow=0.0644,
    phase_precipitation={"temperate": 1.0, "warming": 1.0, "drought": -1.0, "cooling": -0.3936},
    phase_evaporation={"temperate": 1.0, "warming": 1.0, "drought": 4.0, "cooling": 1.0},
    shock_precipitation=1.0, forest_retention=0.5, transpiration=0.3, channel_ratio=1.0)

STORAGE_BASE = PARAMETERS.storage_base
FOREST_RETENTION = PARAMETERS.forest_retention
PRECIPITATION_BASE = PARAMETERS.precipitation_base
PHASE_PRECIPITATION = PARAMETERS.phase_precipitation
SHOCK_PRECIPITATION = PARAMETERS.shock_precipitation
TUNDRA_MELT = PARAMETERS.tundra_melt
EVAPORATION_BASE = PARAMETERS.evaporation_base
PHASE_EVAPORATION = PARAMETERS.phase_evaporation
TERRAIN_EVAPORATION = PARAMETERS.terrain_evaporation
TRANSPIRATION = PARAMETERS.transpiration
BASEFLOW = PARAMETERS.baseflow
IRRIGATION_DEMAND = PARAMETERS.irrigation_demand
IRRIGATION_WETTING = PARAMETERS.irrigation_wetting
CHANNEL_CAPACITY = PARAMETERS.channel_capacity
RIVER_CHANNEL_FACTOR = PARAMETERS.river_channel_factor
DROUGHT_FRACTION = PARAMETERS.drought_fraction
DROUGHT_TURNS = PARAMETERS.drought_turns
DEFORESTED_COVER = PARAMETERS.deforested_cover
INDEX_FLOOR = PARAMETERS.index_floor
CLOSURE_TOLERANCE = PARAMETERS.closure_tolerance

TEMPLATE_REFUSAL = (
    "--watershed requires a procedural world (--worldgen procedural, or more than 12 regions with "
    "--worldgen auto): its drainage graph is derived from saved procedural elevation, and template "
    "worlds have none (an intentional boundary of this slice)")


class _Plan:
    """The account of one turn, computed before the ecology tick."""

    def __init__(self, turn: int, phase: str, columns: dict[str, list[float]], routed: dict[str, list[float]],
                 contributions: list[list[tuple[int, float]]], normal: list[float], cover: list[float],
                 unmet: list[float], channel: list[float], residual: float, external: list[ExternalFlow],
                 stale: bool):
        self.turn, self.phase, self.columns, self.routed = turn, phase, columns, routed
        self.contributions, self.normal, self.cover, self.unmet = contributions, normal, cover, unmet
        self.channel, self.residual, self.external, self.stale = channel, residual, external, stale
        self.consequences: dict[int, FloodConsequence] = {}
        #: ``flow``: onsets whose consequence was withheld, with the cooldowns the region held.
        self.withheld: dict[int, list[str]] = {}
        #: The pre-tick terrain and water-index cap of each region (inputs).
        self.terrain: list[str] = []
        self.caps: list[float] = []


# --- State and switch -----------------------------------------------------------------

def _state(world) -> WatershedState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "watershed", None) if container is not None else None


def watershed_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled


def flow_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled and state.mode == "flow"


def native_available() -> bool:
    """Whether the compiled extension (the native ecology) can be imported."""
    import importlib.util
    try:
        return importlib.util.find_spec("chronicler_agents") is not None
    except (ImportError, ValueError):
        return False


def native_overrides(world) -> tuple[dict[str, float], float | None]:
    """The native ``EcologyConfig`` fields and the harvest shock's water loss
    that ``flow`` switches off (``FLOW_REPLACED_TERMS``); ``({}, None)``
    otherwise, so the configuration is exactly as before. Read by the one
    pinned seam, ``agent_bridge.configure_ecology_runtime``. The native config
    is checkpointed with the run, which is why a mode change on resume is
    refused."""
    if not flow_active(world):
        return {}, None
    return dict(FLOW_REPLACED_TERMS), 0.0


def check_request(world, value: bool | None, args=None) -> None:
    """Refuse a request this world cannot honour, before anything changes.

    Called by ``livelihoods._check_prerequisites``. A new account opens only
    with a new world (turn 0) built from procedural geography; a world that
    keeps an account cannot end it or change its mode on a resume (a switch
    change on resume is refused), and its geography must still give the
    saved graph."""
    mode = getattr(args, "watershed_mode", None) if args is not None else None
    if mode is not None and mode not in MODES:
        raise ValueError(f"watershed_mode must be one of {MODES}")
    state = _state(world)
    if state is None:
        if value is not True:
            if mode is not None and value is None:
                # Easy to mistake for a flow run that did nothing (review n1).
                raise ValueError(f"--watershed-mode {mode} requires --watershed (this world has no watershed "
                                 "account)")
            return
        build_graph(world)          # template worlds first: the same refusal at startup and on resume
        if int(world.turn) > 0:
            raise ValueError(
                f"--watershed opens its account with a new world (turn 0); this world is at turn {world.turn}: "
                "a switch change on resume is refused")
        if (mode or MODES[0]) == "flow" and not native_available():
            raise ValueError(FLOW_NATIVE_REFUSAL)
        return
    if value is False:
        raise ValueError("--no-watershed: this world keeps a watershed account; a switch change on resume is "
                         "refused (the account cannot be ended)")
    if mode is not None and mode != state.mode:
        raise ValueError(f"--watershed-mode {mode} conflicts with this world's watershed account (mode "
                         f"{state.mode}); a switch change on resume is refused")
    if state.mode == "flow" and not native_available():
        raise ValueError(FLOW_NATIVE_REFUSAL)
    if build_graph(world).down != state.graph.down:
        raise ValueError("this world's geography no longer gives its saved drainage graph")


def set_watershed_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Open the account (``value`` True on a world without one); an existing
    account is kept as saved. Ending one is refused (:func:`check_request`)."""
    mode = getattr(args, "watershed_mode", None) if args is not None else None
    if mode is not None and mode not in MODES:
        raise ValueError(f"watershed_mode must be one of {MODES}")
    state = _state(world)
    if state is not None:
        if not value:
            raise ValueError("--no-watershed: a watershed account cannot be ended")
        return
    if not value:
        return
    graph = build_graph(world)
    world.livelihoods.watershed = open_account(world, graph, mode or MODES[0])


# --- Graph ----------------------------------------------------------------------------

def validate_river_paths(rivers, names) -> None:
    """Refuse rivers that cannot be read as one downstream direction.

    Each step must join two distinct known regions; a step and its reverse
    may not both appear (in one river or two); a region may have only one
    downstream target; and the steps may not form a cycle."""
    index = {name: i for i, name in enumerate(names)}
    succ: dict[int, int] = {}
    steps: set[tuple[int, int]] = set()
    for river in rivers:
        label = getattr(river, "name", "a river")
        path = list(getattr(river, "path", river))
        for a, b in zip(path, path[1:]):
            if a not in index or b not in index:
                raise ValueError(f"river {label}: step {a} -> {b} names an unknown region")
            if a == b:
                raise ValueError(f"river {label}: step {a} -> {b} does not move")
            ia, ib = index[a], index[b]
            if (ib, ia) in steps:
                raise ValueError(f"river {label}: step {a} -> {b} reverses another river step "
                                 "(a reversed duplicate)")
            if ia in succ and succ[ia] != ib:
                raise ValueError(f"river {label}: {a} flows to both {names[succ[ia]]} and {b} "
                                 "(multiple downstream targets)")
            succ[ia] = ib
            steps.add((ia, ib))
    for start in sorted(succ):
        seen = {start}
        node = start
        while node in succ:
            node = succ[node]
            if node in seen:
                raise ValueError(f"rivers form a cycle through {names[node]}")
            seen.add(node)


def build_graph(world) -> WatershedGraph:
    """The drainage graph of a procedural world, validated (see the module docstring)."""
    geography = getattr(world, "geography", None)
    regions = list(world.regions)
    if geography is None or getattr(geography, "generator", None) != "procedural" or not regions \
            or any(getattr(r, "geo", None) is None for r in regions):
        raise ValueError(TEMPLATE_REFUSAL)
    names = [r.name for r in regions]
    index = {name: i for i, name in enumerate(names)}
    if len(index) != len(names):
        raise ValueError("--watershed: region names are not unique")
    lanes = {frozenset(pair) for pair in geography.sea_lanes}
    zone_kind = {zone.name: zone.kind for zone in geography.sea_zones}
    elevation = [float(r.geo.elevation) for r in regions]
    if not all(math.isfinite(e) for e in elevation):
        raise ValueError("--watershed: a region's saved elevation is not finite")
    down: list[int] = []
    for i, region in enumerate(regions):
        if region.geo.coastal:
            # A shore on lakes only drains to closed water, never to the sea.
            kinds = [zone_kind.get(z) for z in region.geo.sea_zones]
            down.append(LAKE if kinds and all(k == "lake" for k in kinds) else SEA)
            continue
        land = sorted({index[n] for n in region.adjacencies
                       if n in index and n != region.name and frozenset((region.name, n)) not in lanes})
        lower = [j for j in land if elevation[j] < elevation[i]]
        down.append(min(lower, key=lambda j: (elevation[j], j)) if lower else SINK)
    validate_river_paths(world.rivers, names)
    steps = 0
    for river in world.rivers:
        for a, b in zip(river.path, river.path[1:]):
            got = down[index[a]]
            if got != index[b]:
                target = ("the sea" if got == SEA else "a sink" if got == SINK else "a lake" if got == LAKE
                          else names[got])
                raise ValueError(f"--watershed: river {river.name} flows {a} -> {b}, but the drainage graph "
                                 f"rebuilt from saved elevation drains {a} to {target}")
            steps += 1
    order = sorted(range(len(regions)), key=lambda i: (-elevation[i], i))
    position = {r: k for k, r in enumerate(order)}
    for i, d in enumerate(down):
        if d >= 0 and not (elevation[d] < elevation[i] and position[d] > position[i]):
            raise ValueError("--watershed: the drainage graph is not ordered downhill")  # unreachable by construction
    return WatershedGraph(down=down, order=order, river_steps=steps)


@lru_cache(maxsize=64)
def _upstream(down: tuple[int, ...]) -> tuple[tuple[int, ...], ...]:
    """Every region draining (directly or through others) into each region."""
    up: list[list[int]] = [[] for _ in down]
    for u in range(len(down)):
        node, hops = down[u], 0
        while node >= 0:
            up[node].append(u)
            node = down[node]
            hops += 1
            if hops > len(down):
                raise ValueError("drainage graph has a cycle")
    return tuple(tuple(sorted(x)) for x in up)


def upstream_regions(state: WatershedState) -> tuple[tuple[int, ...], ...]:
    return _upstream(tuple(state.graph.down))


# --- Region quantities ----------------------------------------------------------------

def _cover(region) -> float:
    return min(1.0, max(0.0, float(region.ecology.forest_cover)))


def capacity(cover: float) -> float:
    return STORAGE_BASE * (1.0 + FOREST_RETENTION * cover)


def index_cap(region) -> float:
    from chronicler.ecology import TERRAIN_ECOLOGY_CAPS
    return float(TERRAIN_ECOLOGY_CAPS.get(region.terrain, TERRAIN_ECOLOGY_CAPS["plains"])["water"])


def _span(region) -> float:
    return max(index_cap(region) - INDEX_FLOOR, 1e-9)


def derived_index(region, storage: float, withdrawal: float, cap: float) -> float:
    fill = min(1.0, storage / cap + IRRIGATION_WETTING * withdrawal / cap) if cap > 0 else 0.0
    return INDEX_FLOOR + (index_cap(region) - INDEX_FLOOR) * max(0.0, fill)


def _irrigated(region) -> bool:
    from chronicler.models import InfrastructureType
    return any(i.type == InfrastructureType.IRRIGATION and i.active for i in region.infrastructure)


def open_account(world, graph: WatershedGraph, mode: str = "record_only") -> WatershedState:
    """Opening storage from the current index, so the derived index is continuous."""
    storage, index = [], []
    for region in world.regions:
        cap = capacity(_cover(region))
        water = float(region.ecology.water)
        fill = min(1.0, max(0.0, (water - INDEX_FLOOR) / _span(region)))
        storage.append(cap * fill)
        index.append(water)
    state = WatershedState(mode=mode, opened_turn=int(world.turn), graph=graph, storage=storage,
                           last_index=index, opening_storage=math.fsum(storage))
    state.counters.update({key: 0 for key in EVENT_COUNTER_KEYS})
    if mode == "flow":
        state.counters.update({key: 0 for key in FLOW_COUNTER_KEYS})
    return state


# --- The account ----------------------------------------------------------------------

def _tolerance(terms) -> float:
    return CLOSURE_TOLERANCE * math.fsum(abs(t) for t in terms)


def coastal_flood_gain(world, region) -> float | None:
    """The index gain a coastal flood (``climate.check_disasters``) gave this
    region in Phase 1 of this turn, or None when none struck. Recomputed from
    the disaster's own deterministic roll and probability, and confirmed by
    the cooldown it set this turn (cooldowns are decremented before the
    check, and ``emergence`` skips a region with any cooldown); reads only."""
    from chronicler.climate import _deterministic_roll, _disaster_probability, get_climate_phase
    from chronicler.tuning import K_DISASTER_COOLDOWN, K_FLOOD_WATER_GAIN, get_override
    if region.terrain != "coast":
        return None
    if region.disaster_cooldowns.get("flood") != int(get_override(world, K_DISASTER_COOLDOWN, 10)):
        return None
    phase = get_climate_phase(world.turn, world.climate_config)
    prob = _disaster_probability("flood", region.terrain, phase, world.climate_config.severity)
    if region.latitude_band is not None:
        from chronicler.geography import disaster_factor
        prob *= disaster_factor(region.latitude_band, "flood")
    if _deterministic_roll(world.seed, region.name, world.turn, "flood") >= prob:
        return None
    return float(get_override(world, K_FLOOD_WATER_GAIN, 0.1))


class RegionInput(NamedTuple):
    """What the account reads of one region before the tick (pure data, so
    the account can be replayed: scripts/watershed_calibration.py)."""
    terrain: str
    moisture: float
    cover: float
    water: float
    exposure: float
    shock: float
    irrigated: bool
    river: bool
    cap: float
    #: The coastal flood's index gain this turn (``coastal_flood_gain``), or None.
    flood_gain: float | None


def region_inputs(world, state: WatershedState) -> tuple[int, str, float, list[RegionInput]]:
    """(turn, phase, trend share, per-region inputs): reads only."""
    from chronicler.climate import climate_trend_share, get_climate_phase, region_harvest_shocks
    from chronicler.geography import climate_exposure
    turn = int(world.turn)
    phase = get_climate_phase(turn, world.climate_config)
    trend = climate_trend_share(world)
    shocks = region_harvest_shocks(world)
    inputs = []
    for r, region in enumerate(world.regions):
        water = float(region.ecology.water)
        inputs.append(RegionInput(
            terrain=region.terrain, moisture=float(region.geo.moisture), cover=_cover(region), water=water,
            exposure=float(climate_exposure(region.latitude_band, phase)), shock=float(shocks[r]),
            irrigated=_irrigated(region), river=bool(region.river_mask), cap=index_cap(region),
            flood_gain=coastal_flood_gain(world, region) if water > float(state.last_index[r]) else None))
    return turn, phase.value, trend, inputs


def account_step(graph: WatershedGraph, storage: list[float], last_index: list[float], turn: int, key: str,
                 trend: float, inputs: list[RegionInput], params: Parameters = PARAMETERS,
                 stale: bool = False) -> _Plan:
    """One turn of the account from its inputs (pure: no world, no RNG)."""
    n = len(inputs)
    if len(graph.down) != n or len(storage) != n or len(last_index) != n:
        raise RuntimeError("watershed state does not match the world's regions")
    cols = {name: [0.0] * n for name in FRAME_COLUMNS}
    routed = {"to_sea": [0.0] * n, "to_sink": [0.0] * n, "to_lake": [0.0] * n, "transfer": [0.0] * n}
    contributions: list[list[tuple[int, float]]] = [[] for _ in range(n)]
    external: list[ExternalFlow] = []
    normal, covers, unmet, channels = [0.0] * n, [0.0] * n, [0.0] * n, [0.0] * n
    floor = params.index_floor
    basin = None
    if params.channel_ratio is not None:
        # Each region's drainage basin's normal precipitation (itself and everything upstream).
        basin = [params.precipitation_base * (0.2 + inp.moisture) for inp in inputs]
        for r in graph.order:
            if graph.down[r] >= 0:
                basin[graph.down[r]] += basin[r]
    for r in graph.order:
        inp = inputs[r]
        cover = inp.cover
        cap = params.storage_base * (1.0 + params.forest_retention * cover)
        span = max(inp.cap - floor, 1e-9)
        s = float(storage[r])
        x = (inp.water - float(last_index[r])) / span * cap
        x_in = x if x > 0.0 else 0.0
        want = -x if x < 0.0 else 0.0
        x_out = min(s, want)
        if x_in > 0.0:
            gain = None if stale else inp.flood_gain
            attributed = min(x_in, gain / span * cap) if gain is not None else 0.0
            if attributed > 0.0:
                external.append(ExternalFlow(region=r, direction="in", source="coastal_flood", amount=attributed))
            if x_in - attributed > 0.0:
                external.append(ExternalFlow(region=r, direction="in", source="unattributed",
                                             amount=x_in - attributed))
        if x_out > 0.0:
            external.append(ExternalFlow(region=r, direction="out", source="unattributed", amount=x_out))
        exposure = inp.exposure
        p_norm = params.precipitation_base * (0.2 + inp.moisture)
        factor = max(0.0, 1.0 - (1.0 - params.phase_precipitation[key]) * exposure * trend)
        p = p_norm * factor * max(0.0, 1.0 - params.shock_precipitation * inp.shock)
        if key == "warming" and inp.terrain == "tundra":
            p += params.tundra_melt
        i = math.fsum(q for _, q in contributions[r])
        a = s + p + x_in - x_out + i
        e_pot = (params.evaporation_base * (1.0 + (params.phase_evaporation[key] - 1.0) * exposure * trend)
                 * params.terrain_evaporation.get(inp.terrain, 1.0) * (1.0 + params.transpiration * cover))
        e = min(a, e_pot)
        t = a - e
        w = min(t, params.irrigation_demand) if inp.irrigated else 0.0
        b = t - w
        s2 = (1.0 - params.baseflow) * min(b, cap)
        q = b - s2
        d = graph.down[r]
        if d >= 0:
            contributions[d].append((r, q))
            routed["transfer"][r] = q
        elif d == SEA:
            routed["to_sea"][r] = q
        elif d == LAKE:
            routed["to_lake"][r] = q
        else:
            routed["to_sink"][r] = q
        channel = (params.channel_ratio * basin[r] if basin is not None
                   else params.channel_capacity * (params.river_channel_factor if inp.river else 1.0))
        fill = min(1.0, s2 / cap + params.irrigation_wetting * w / cap) if cap > 0 else 0.0
        for name, value in (("storage_open", s), ("precipitation", p), ("external_in", x_in),
                            ("external_out", x_out), ("inflow", i), ("evaporation", e), ("withdrawal", w),
                            ("outflow", q), ("storage", s2), ("capacity", cap),
                            ("index_derived", floor + (inp.cap - floor) * max(0.0, fill)),
                            # AUDIT-B 7.2: flood = max(0, I + P - channel); an external inflow
                            # (a coastal flood's surge) enters storage but is not channel flow.
                            ("flood_excess", max(0.0, p + i - channel))):
            cols[name][r] = value
        normal[r], covers[r], unmet[r], channels[r] = p_norm, cover, want - x_out, channel
    residual = check_closure(graph.down, cols, routed)
    external.sort(key=lambda f: (f.region, f.direction, f.source))
    plan = _Plan(turn, key, cols, routed, contributions, normal, covers, unmet, channels, residual, external, stale)
    plan.terrain = [inp.terrain for inp in inputs]
    plan.caps = [float(inp.cap) for inp in inputs]
    return plan


def _compute(world, state: WatershedState, stale: bool = False) -> _Plan:
    turn, key, trend, inputs = region_inputs(world, state)
    return account_step(state.graph, state.storage, state.last_index, turn, key, trend, inputs, PARAMETERS, stale)


def check_closure(down, cols: dict[str, list[float]], routed: dict[str, list[float]]) -> float:
    """Raise unless the account closes region by region and in total, every
    flow is non-negative, storage is within capacity and each inflow is the
    sum of its tributaries' outflows. Returns the total residual (wu).

    These are construction invariants and routing guards, not a validation
    of the water model: each region's outflow is defined as the residual of
    its account, so its closure can fail only through float pathology; the
    total and tributary checks catch water routed to no region or to a region
    already processed (a broken order), and the bounds catch negative or
    non-finite inputs."""
    n = len(down)
    for r in range(n):
        flows = [cols[k][r] for k in ("precipitation", "external_in", "external_out", "inflow", "evaporation",
                                      "withdrawal", "outflow", "storage_open")]
        if not all(math.isfinite(v) and v >= 0.0 for v in flows + [cols["storage"][r], cols["capacity"][r]]):
            raise RuntimeError(f"watershed: a negative or non-finite flow in region {r}")
        if cols["storage"][r] > cols["capacity"][r] * (1.0 + CLOSURE_TOLERANCE):
            raise RuntimeError(f"watershed: storage above capacity in region {r}")
        if cols["external_out"][r] > cols["storage_open"][r]:
            raise RuntimeError(f"watershed: external outflow above storage in region {r}")
        terms = [cols["storage"][r], cols["outflow"][r], cols["evaporation"][r], cols["withdrawal"][r],
                 cols["external_out"][r], -cols["storage_open"][r], -cols["precipitation"][r],
                 -cols["external_in"][r], -cols["inflow"][r]]
        if abs(math.fsum(terms)) > _tolerance(terms):
            raise RuntimeError(f"watershed: region {r} does not close")
        tributaries = [cols["outflow"][u] for u in range(n) if down[u] == r]
        if abs(math.fsum(tributaries) - cols["inflow"][r]) > _tolerance(tributaries + [cols["inflow"][r]]):
            raise RuntimeError(f"watershed: region {r}'s inflow is not the sum of its tributaries' outflows")
        routes = [routed["transfer"][r], routed["to_sea"][r], routed["to_sink"][r], routed["to_lake"][r]]
        if sum(1 for v in routes if v != 0.0) > 1 or abs(math.fsum(routes) - cols["outflow"][r]) > 0.0:
            raise RuntimeError(f"watershed: region {r}'s outflow is not routed to one destination")
    terms = (list(cols["storage"]) + [-v for v in cols["storage_open"]] + [-v for v in cols["precipitation"]]
             + [-v for v in cols["external_in"]] + list(cols["external_out"]) + list(cols["evaporation"])
             + list(cols["withdrawal"]) + list(routed["to_sea"]) + list(routed["to_sink"]) + list(routed["to_lake"]))
    residual = math.fsum(terms)
    if abs(residual) > _tolerance(terms):
        raise RuntimeError("watershed: the account does not close this turn")
    return residual


def _totals(plan: _Plan) -> dict[str, float]:
    c, r = plan.columns, plan.routed
    return {"precipitation": math.fsum(c["precipitation"]), "external_in": math.fsum(c["external_in"]),
            "external_out": math.fsum(c["external_out"]), "evaporation": math.fsum(c["evaporation"]),
            "withdrawal": math.fsum(c["withdrawal"]), "to_sea": math.fsum(r["to_sea"]),
            "to_sink": math.fsum(r["to_sink"]), "to_lake": math.fsum(r["to_lake"]),
            "transfer": math.fsum(r["transfer"])}


def _net(flows: dict[str, float]) -> list[float]:
    return [flows["precipitation"], flows["external_in"], -flows["external_out"], -flows["evaporation"],
            -flows["withdrawal"], -flows["to_sea"], -flows["to_sink"], -flows.get("to_lake", 0.0)]


# --- Protocol: Phase 9 ----------------------------------------------------------------

def before_ecology(world, acc, *, native: bool | None = None) -> None:
    """Compute and check this turn's account from the pre-tick world; change
    nothing outside this package's state. A plan left by a failed tick is
    dropped first (``abandoned_plans``: nothing was settled)."""
    state = _state(world)
    dropped = state._plan is not None
    if dropped:
        state._plan = None
        state.counters["abandoned_plans"] = state.counters.get("abandoned_plans", 0) + 1
    # The baseline index must be the one observed after the previous turn's
    # tick: a dropped plan or a missing turn makes it stale (recorded; the
    # external flows are then all unattributed).
    expected = state.frame.turn + 1 if state.frame is not None else state.opened_turn
    stale = dropped or int(world.turn) != expected
    if state.mode == "flow":
        if native is False:
            raise RuntimeError(FLOW_NATIVE_REFUSAL)
        if stale:
            # flow writes the index: an unsettled tick's change would be applied
            # as if it were another writer's, so the account refuses to go on.
            raise RuntimeError("watershed flow: the baseline index is stale (a tick did not settle or a turn "
                               "is missing); refusing to apply the account")
    plan = _compute(world, state, stale=stale)
    if state.mode == "flow":
        _end_expired_consequences(world, state)
        _apply_flow(world, plan, state)
    state._plan = plan
    state.counters["planned_turns"] = state.counters.get("planned_turns", 0) + 1


def _onsets(state: WatershedState, plan: _Plan) -> list[int]:
    """Regions where a flood event starts this turn: arrivals above the channel
    (``flood_excess`` > 0) and no event open there (an open event ends only
    below the recession threshold, so an onset crosses the channel from below)."""
    open_regions = {event.region for event in state.flood_events}
    return [r for r, excess in enumerate(plan.columns["flood_excess"]) if excess > 0.0 and r not in open_regions]


def _apply_flow(world, plan: _Plan, state: WatershedState) -> None:
    """``flow``: the derived index becomes the index the simulation uses, and
    each flood event acts once, at its onset, through the existing fields,
    before the Phase 9 sync so the native tick sees both. As the old river
    flood skipped a region holding any disaster cooldown, a consequence is
    withheld (and recorded so) on such a region; this also counts a coastal
    flood's storm once. Deterministic; no RNG."""
    from chronicler.ecology import TERRAIN_ECOLOGY_CAPS
    params = PARAMETERS
    for r, region in enumerate(world.regions):
        region.ecology.water = plan.columns["index_derived"][r]
    for r in _onsets(state, plan):
        region = world.regions[r]
        held = sorted(k for k, v in region.disaster_cooldowns.items() if v > 0)
        if held:
            plan.withheld[r] = held
            continue
        excess = plan.columns["flood_excess"][r]
        days = 2 if excess >= params.flood_long_excess else 1
        # Applied in Phase 9, one turn later than the old Phase-1 river flood:
        # the cooldown covers this turn's tick and the next ``days`` turns.
        cooldown = days + 1
        before = float(region.capacity_modifier)
        modifier = min(before, params.flood_capacity_modifier)
        cap = TERRAIN_ECOLOGY_CAPS.get(region.terrain, TERRAIN_ECOLOGY_CAPS["plains"])["soil"]
        soil_before = float(region.ecology.soil)
        soil_after = max(soil_before, min(float(cap), soil_before + params.flood_silt))
        region.disaster_cooldowns["flood"] = cooldown
        region.capacity_modifier = modifier
        region.ecology.soil = soil_after
        plan.consequences[r] = FloodConsequence(capacity_modifier=modifier, cooldown=cooldown,
                                                soil_before=soil_before, soil_after=soil_after)
        if modifier < before:
            state.active_consequences.append(ActiveConsequence(
                region=r, expires_turn=plan.turn + cooldown, modifier=modifier, before=before))


def _end_expired_consequences(world, state: WatershedState) -> None:
    """``flow``: end a flood's capacity modifier when its cooldown has expired.
    ``simulation`` restores the modifier in Phase 1 only when every cooldown
    is gone, so another disaster's cooldown (begun after the onset) would
    otherwise keep it; the account restores its own value here, at its next
    Phase 9, unless another system has changed it since."""
    keep = []
    for active in state.active_consequences:
        if int(world.turn) < active.expires_turn:
            keep.append(active)
            continue
        region = world.regions[active.region]
        if ("flood" not in region.disaster_cooldowns and float(region.capacity_modifier) == active.modifier
                and region.disaster_cooldowns):
            region.capacity_modifier = active.before
    state.active_consequences = keep


def supersede_river_flood(world, region, duration: int) -> bool:
    """``flow``: ``emergence._check_flood`` drew a river flood (its draws are
    kept, so the shared environment stream does not shift); its effect is
    suppressed and recorded here as superseded by the account's floods.
    Returns False (the flood acts as before) unless ``flow`` is active."""
    if not flow_active(world):
        return False
    state = _state(world)
    index = next(i for i, r in enumerate(world.regions) if r is region or r.name == region.name)
    state.pending_superseded.append(SupersededFlood(turn=int(world.turn), region=index, duration=int(duration)))
    return True


def after_ecology(world, acc) -> list:
    """Record the index the tick produced beside the derived one, the
    flood events and droughts with their conditions and the terrain cap
    changes of the post-pass, and commit the turn. In ``flow`` each flood
    event that acted is also a chronicle event."""
    state = _state(world)
    plan, state._plan = state._plan, None
    if plan is None or plan.turn != world.turn:
        raise RuntimeError("watershed plan missing for this turn")
    regions = world.regions
    n = len(regions)
    cols = {name: list(values) for name, values in plan.columns.items()}
    cols["index_observed"] = [float(region.ecology.water) for region in regions]
    up = upstream_regions(state)

    def mean_cover(r: int) -> float | None:
        return math.fsum(plan.cover[u] for u in up[r]) / len(up[r]) if up[r] else None

    # Flood events: an onset crosses the channel from below (no event open);
    # an open event lasts while arrivals exceed the recession threshold.
    recession = PARAMETERS.flood_recession
    open_events = {event.region: event for event in state.flood_events}
    onsets = set(_onsets(state, plan))
    floods: list[FloodRecord] = []
    flood_events: list[FloodEvent] = []
    floods_ended: list[FloodEvent] = []
    for r in range(n):
        arrivals = cols["precipitation"][r] + cols["inflow"][r]
        excess = cols["flood_excess"][r]
        event = open_events.get(r)
        if event is not None:
            if arrivals > recession * plan.channel[r]:
                flood_events.append(event.model_copy(update={
                    "turns": event.turns + 1, "peak_excess": max(event.peak_excess, excess)}))
            else:
                floods_ended.append(event.model_copy(update={"end_turn": plan.turn}))
        elif r in onsets:
            floods.append(FloodRecord(
                turn=plan.turn, region=r, excess=excess, arrivals=arrivals,
                channel=plan.channel[r], precipitation=cols["precipitation"][r], inflow=cols["inflow"][r],
                storage_open=cols["storage_open"][r],
                capacity=cols["capacity"][r], tributaries=list(plan.contributions[r]),
                upstream_cover=mean_cover(r),
                upstream_deforested=sum(1 for u in up[r] if plan.cover[u] < DEFORESTED_COVER),
                consequence=plan.consequences.get(r), withheld_by=plan.withheld.get(r, [])))
            flood_events.append(FloodEvent(region=r, start_turn=plan.turn, turns=1, peak_excess=excess))

    # Terrain transitions in this Phase 9's post-pass clamp the index to the
    # new terrain's cap (emergence.tick_terrain_succession): recorded so the
    # index used is explained (flow: min(index_derived, cap_after)).
    cap_changes: list[CapChange] = []
    for r, region in enumerate(regions):
        if region.terrain != plan.terrain[r]:
            cap_after = index_cap(region)
            cap_changes.append(CapChange(
                region=r, terrain_before=plan.terrain[r], terrain_after=region.terrain,
                cap_before=plan.caps[r], cap_after=cap_after,
                index_out=max(0.0, cols["index_derived"][r] - cap_after) if state.mode == "flow" else None))

    running = {spell.region: spell for spell in state.spells}
    spells: list[DroughtSpell] = []
    ended: list[DroughtSpell] = []
    drought_turns = [0] * n
    declared = ended_count = open_count = 0
    for r in range(n):
        fraction = cols["storage"][r] / cols["capacity"][r]
        spell = running.get(r)
        if fraction < DROUGHT_FRACTION:
            upstream_w = math.fsum(cols["withdrawal"][u] for u in up[r])
            if spell is None:
                spell = DroughtSpell(region=r, start_turn=plan.turn, turns=1, min_fraction=fraction,
                                     precipitation=cols["precipitation"][r], normal_precipitation=plan.normal[r],
                                     inflow=cols["inflow"][r], evaporation=cols["evaporation"][r],
                                     withdrawal=cols["withdrawal"][r], upstream_withdrawal=upstream_w,
                                     upstream_cover=mean_cover(r))
            else:
                spell = spell.model_copy(update={
                    "turns": spell.turns + 1, "min_fraction": min(spell.min_fraction, fraction),
                    "precipitation": spell.precipitation + cols["precipitation"][r],
                    "normal_precipitation": spell.normal_precipitation + plan.normal[r],
                    "inflow": spell.inflow + cols["inflow"][r],
                    "evaporation": spell.evaporation + cols["evaporation"][r],
                    "withdrawal": spell.withdrawal + cols["withdrawal"][r],
                    "upstream_withdrawal": spell.upstream_withdrawal + upstream_w})
            if spell.declared_turn is None and spell.turns >= DROUGHT_TURNS:
                spell = spell.model_copy(update={"declared_turn": plan.turn})
                declared += 1
            if spell.declared_turn is not None:
                open_count += 1
            drought_turns[r] = spell.turns
            spells.append(spell)
        elif spell is not None and spell.declared_turn is not None:
            ended.append(spell.model_copy(update={"end_turn": plan.turn}))
            ended_count += 1

    totals = _totals(plan)
    unmet = math.fsum(plan.unmet)
    totals["external_out_unmet"] = unmet
    for direction, source in (("in", "coastal_flood"), ("in", "unattributed"), ("out", "unattributed")):
        totals[f"external_{direction}_{source}"] = math.fsum(
            f.amount for f in plan.external if f.direction == direction and f.source == source)
    storage_open = math.fsum(cols["storage_open"])
    storage_close = math.fsum(cols["storage"])
    cumulative = {key: state.cumulative.get(key, 0.0) + totals[key] for key in FLOW_KEYS}
    terms = [storage_close, -state.opening_storage] + [-v for v in _net(cumulative)]
    if abs(math.fsum(terms)) > _tolerance(terms):
        raise RuntimeError("watershed: the cumulative account does not close against the opening storage")
    frame = WatershedFrame(turn=plan.turn, phase=plan.phase, columns=cols, floods=floods, droughts_ended=ended,
                           floods_ended=floods_ended, totals=totals, storage_open=storage_open,
                           storage_close=storage_close, closure_residual=plan.residual,
                           drought_turns=drought_turns, external=plan.external, stale_baseline=plan.stale,
                           superseded=[f for f in state.pending_superseded if f.turn == plan.turn],
                           cap_changes=cap_changes)

    # Commit: storage, the observed index, the spells, the frame and the totals.
    state.storage = list(cols["storage"])
    state.last_index = list(cols["index_observed"])
    state.spells = spells
    state.flood_events = flood_events
    state.frame = frame
    state.cumulative = cumulative
    counters = state.counters
    for key in COUNTER_KEYS + EVENT_COUNTER_KEYS:
        counters.setdefault(key, 0)
    counters["settled_turns"] += 1
    counters["flood_region_turns"] += sum(1 for v in cols["flood_excess"] if v > 0.0)
    counters["floods_started"] += len(floods)
    counters["floods_ended"] += len(floods_ended)
    counters["terrain_cap_changes"] += len(cap_changes)
    counters["drought_region_turns"] += open_count
    counters["droughts_declared"] += declared
    counters["droughts_ended"] += ended_count
    counters["external_out_unmet_turns"] += 1 if unmet > 0.0 else 0
    counters["stale_baseline_turns"] += 1 if plan.stale else 0
    if state.mode == "flow":
        for key in FLOW_COUNTER_KEYS:
            counters.setdefault(key, 0)
        counters["flood_consequences"] += len(plan.consequences)
        counters["flood_consequences_withheld"] += len(plan.withheld)
        counters["superseded_river_floods"] += len(frame.superseded)
    state.pending_superseded = []
    return _flood_events(world, plan) if state.mode == "flow" else []


def _flood_events(world, plan: _Plan) -> list:
    """``flow``: a chronicle event for each flood event that acted (its record
    is the cause), replacing the superseded river flood's event."""
    from chronicler.models import Event
    events = []
    for r in sorted(plan.consequences):
        region = world.regions[r]
        events.append(Event(
            turn=world.turn, event_type="flood", region=region.name,
            actors=[region.controller] if region.controller else [],
            description=(f"Swollen waters overflow the channels of {region.name}, depositing rich silt "
                         "but damaging infrastructure"),
            importance=6))
    return events


# --- Protocol: observation ------------------------------------------------------------

def parameters() -> dict:
    """The declared constants in force."""
    return PARAMETERS.as_dict()


def _r(value: float) -> float:
    return round(float(value), 6)


def _spell(spell: DroughtSpell) -> dict:
    out = spell.model_dump()
    for key in ("min_fraction", "precipitation", "normal_precipitation", "inflow", "evaporation", "withdrawal",
                "upstream_withdrawal"):
        out[key] = _r(out[key])
    if out["upstream_cover"] is not None:
        out["upstream_cover"] = _r(out["upstream_cover"])
    return out


def _flood(flood: FloodRecord) -> dict:
    out = flood.model_dump()
    for key in ("excess", "arrivals", "channel", "precipitation", "inflow", "external_in", "storage_open",
                "capacity"):
        if key in out:
            out[key] = _r(out[key])
    out["tributaries"] = [[int(u), _r(q)] for u, q in flood.tributaries]
    if out["upstream_cover"] is not None:
        out["upstream_cover"] = _r(out["upstream_cover"])
    if "consequence" in out:
        out["consequence"] = {key: (_r(v) if isinstance(v, float) else v) for key, v in out["consequence"].items()}
    return out


#: Per-region columns of the snapshot record. ``outflow`` is left out: it is
#: the residual of each region's account by construction, so a reader derives
#: it (``storage_open + precipitation + external_in - external_out + inflow -
#: evaporation - withdrawal - storage``); the state keeps it.
SNAPSHOT_COLUMNS: tuple[str, ...] = tuple(name for name in FRAME_COLUMNS if name != "outflow")


def _flood_event(event: FloodEvent) -> dict:
    out = event.model_dump()
    out["peak_excess"] = _r(out["peak_excess"])
    if out["end_turn"] is None:
        del out["end_turn"]
    return out


def _open_drought(spell: DroughtSpell) -> dict:
    """An open drought after its declaration turn: its identity and depth;
    the conditions are recorded in full when it is declared and when it ends."""
    return {"region": spell.region, "start_turn": spell.start_turn, "turns": spell.turns,
            "declared_turn": spell.declared_turn, "min_fraction": _r(spell.min_fraction)}


def snapshot_summary(world) -> dict:
    """Copied record of the completed turn (values rounded to 6 decimals;
    the full-precision account stays in the state); never live state.

    Every record carries the static part (``units``, ``parameters``,
    ``graph``), so any segment of a history (a state-file resume or a fork
    starts after the opening turn) reads on its own; the bundle's deltas
    write it once anyway. ``observed`` is False (``regions``,
    ``floods``, ``flood_events``, ``droughts``, ``external``,
    ``cap_changes`` and ``totals`` None, not empty) when no Phase 9 was
    settled in the completed turn; ``storage`` (the account's current
    storage) is recorded only then, since a settled turn's
    ``regions.storage`` is the same list. ``floods`` holds the flood events
    that started in the turn (their onset records)."""
    state = _state(world)
    source_turn = world.turn - 1
    frame = state.frame
    observed = frame is not None and frame.turn == source_turn
    cumulative = {key: _r(value) for key, value in state.cumulative.items()}
    storage_now = math.fsum(state.storage)
    record = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGES[state.mode],
        "mode": state.mode,
        "source_turn": source_turn,
        "completed_turn": world.turn,
        "opened_turn": state.opened_turn,
    }
    record.update({
        "units": {"water": "wu (one region's storage capacity without forest cover is 1)",
                  "index": "ecology.water (the 0-1 water index)"},
        "parameters": parameters(),
        "graph": {"down": list(state.graph.down), "sea": SEA, "sink": SINK, "lake": LAKE,
                  "river_steps": state.graph.river_steps},
    })
    record.update({
        "observed": observed,
        "phase": frame.phase if observed else None,
        "stale_baseline": frame.stale_baseline if observed else None,
        "regions": None,
        "floods": None,
        "flood_events": None,
        "droughts": None,
        "external": None,
        "cap_changes": None,
        "totals": None,
        "storage": None if observed else [_r(v) for v in state.storage],
        "cumulative": {**cumulative, "opening_storage": _r(state.opening_storage), "storage": _r(storage_now),
                       "closure_residual": math.fsum([storage_now, -state.opening_storage]
                                                     + [-v for v in _net(state.cumulative)])},
        # A B1 account resumed by this code gains the B2 counters when it settles.
        "counters": {**{key: 0 for key in COUNTER_KEYS + EVENT_COUNTER_KEYS
                        + (FLOW_COUNTER_KEYS if state.mode == "flow" else ())}, **state.counters},
    })
    if observed:
        record["regions"] = {**{name: [_r(v) for v in frame.columns[name]] for name in SNAPSHOT_COLUMNS},
                             "drought_turns": list(frame.drought_turns)}
        record["floods"] = [_flood(f) for f in frame.floods]
        record["flood_events"] = {
            "open": [_flood_event(e) for e in state.flood_events],
            "ended": [_flood_event(e) for e in frame.floods_ended]}
        record["cap_changes"] = [{key: (_r(v) if isinstance(v, float) else v)
                                  for key, v in c.model_dump().items()} for c in frame.cap_changes]
        record["droughts"] = {
            "declared": [_spell(s) for s in state.spells if s.declared_turn == frame.turn],
            "open": [_open_drought(s) for s in state.spells if s.declared_turn is not None],
            "ended": [_spell(s) for s in frame.droughts_ended]}
        # Flows below the record's precision (e.g. a coastal flood clamped at
        # the cap of an f32-rounded index) round to 0 and are left out, as
        # their columns read 0.
        record["external"] = [{"region": f.region, "direction": f.direction, "source": f.source,
                               "amount": _r(f.amount)} for f in frame.external if _r(f.amount) > 0]
        record["totals"] = {**{key: _r(value) for key, value in frame.totals.items()},
                            "storage_open": _r(frame.storage_open), "storage_close": _r(frame.storage_close),
                            "closure_residual": frame.closure_residual}
    if state.mode == "flow":
        record["superseded"] = ([f.model_dump() for f in frame.superseded] if observed else None)
    return record
