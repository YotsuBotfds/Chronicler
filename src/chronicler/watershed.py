"""B1 (S1-A): a conserved water account on the drainage graph (``--watershed``, default off).

``--watershed`` with ``--watershed-mode record_only`` (the only mode of this
slice; see :mod:`chronicler.livelihoods`). docs/integration/watershed.md.

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

Conditions. A flood is a settled turn whose arrivals ``P + I + X_in`` exceed
the region's channel capacity (``CHANNEL_CAPACITY``, x
``RIVER_CHANNEL_FACTOR`` on a named river region); its record keeps the
arrivals by source, each tributary's outflow and the upstream cover. A
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
pure-Python fallback) and every agent mode. Every constant below is a
declared modelling choice, not a calibration.
"""
from __future__ import annotations

import math
from functools import lru_cache

from chronicler.watershed_state import (
    COUNTER_KEYS, FLOW_KEYS, FRAME_COLUMNS, LAKE, SEA, SINK, DroughtSpell, ExternalFlow, FloodRecord,
    WatershedFrame, WatershedGraph, WatershedState,
)

MODES = ("record_only",)
SCHEMA_VERSION = 1
STAGE = "B1"

#: Storage capacity of a region without forest cover (water units).
STORAGE_BASE = 1.0
#: Forest soils hold more: capacity x (1 + FOREST_RETENTION x cover).
FOREST_RETENTION = 0.5
#: Precipitation per turn at (0.2 + moisture) = 1, phase factor 1, no shock.
PRECIPITATION_BASE = 0.1
#: Precipitation factor by global climate phase (scaled by the region's
#: latitude exposure and the climate trend share).
PHASE_PRECIPITATION = {"temperate": 1.0, "warming": 0.85, "drought": 0.3, "cooling": 0.6}
#: A bad harvest year of depth h cuts precipitation by h x this.
SHOCK_PRECIPITATION = 1.0
#: Snowmelt added to tundra precipitation in the warming phase.
TUNDRA_MELT = 0.05
#: Potential evapotranspiration per turn at phase factor 1.
EVAPORATION_BASE = 0.03
PHASE_EVAPORATION = {"temperate": 1.0, "warming": 1.3, "drought": 1.6, "cooling": 0.7}
TERRAIN_EVAPORATION = {"desert": 1.6, "steppe": 1.25, "tundra": 0.5}
#: Forests transpire more: evaporation x (1 + TRANSPIRATION x cover).
TRANSPIRATION = 0.3
#: Share of storage released downstream each turn (overflow above capacity also leaves).
BASEFLOW = 0.05
#: Consumptive irrigation use per turn of a region with an active irrigation work
#: (service 1.0: this slice has no infrastructure condition).
IRRIGATION_DEMAND = 0.02
#: The derived index counts irrigation water applied to fields: W/C x this.
IRRIGATION_WETTING = 1.0
#: Arrivals per turn a region's channel passes without flooding ...
CHANNEL_CAPACITY = 0.25
#: ... larger on a named river region.
RIVER_CHANNEL_FACTOR = 2.0
#: A drought: storage below this fraction of capacity ...
DROUGHT_FRACTION = 0.2
#: ... for at least this many consecutive settled turns.
DROUGHT_TURNS = 3
#: Upstream regions below this cover count as deforested in a flood record
#: (the ecology's deforestation threshold).
DEFORESTED_COVER = 0.2
#: The water index floor (``ecology._FLOOR_WATER``).
INDEX_FLOOR = 0.10
#: Relative closure tolerance of every per-turn and cumulative check.
CLOSURE_TOLERANCE = 1e-9

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


# --- State and switch -----------------------------------------------------------------

def _state(world) -> WatershedState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "watershed", None) if container is not None else None


def watershed_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled


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
            return
        build_graph(world)          # template worlds first: the same refusal at startup and on resume
        if int(world.turn) > 0:
            raise ValueError(
                f"--watershed opens its account with a new world (turn 0); this world is at turn {world.turn}: "
                "a switch change on resume is refused")
        return
    if value is False:
        raise ValueError("--no-watershed: this world keeps a watershed account; a switch change on resume is "
                         "refused (the account cannot be ended)")
    if mode is not None and mode != state.mode:
        raise ValueError(f"--watershed-mode {mode} conflicts with this world's watershed account (mode "
                         f"{state.mode}); a switch change on resume is refused")
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


def _irrigated(world, region) -> bool:
    """An active irrigation work that serves (B3: service >= 0.5 while
    ``--infrastructure-condition`` acts; always True for an active work when
    it is off or in ``record_only``)."""
    from chronicler.infrastructure_condition import serves
    from chronicler.models import InfrastructureType
    return any(i.type == InfrastructureType.IRRIGATION and i.active for i in region.infrastructure) \
        and serves(world, region, "irrigation")


def open_account(world, graph: WatershedGraph, mode: str = "record_only") -> WatershedState:
    """Opening storage from the current index, so the derived index is continuous."""
    storage, index = [], []
    for region in world.regions:
        cap = capacity(_cover(region))
        water = float(region.ecology.water)
        fill = min(1.0, max(0.0, (water - INDEX_FLOOR) / _span(region)))
        storage.append(cap * fill)
        index.append(water)
    return WatershedState(mode=mode, opened_turn=int(world.turn), graph=graph, storage=storage,
                          last_index=index, opening_storage=math.fsum(storage))


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


def _external(world, region, r: int, x_in: float, x_out: float, cap: float, stale: bool) -> list[ExternalFlow]:
    """Attribute a region's external flows to their recorded source."""
    flows: list[ExternalFlow] = []
    if x_in > 0.0:
        gain = None if stale else coastal_flood_gain(world, region)
        attributed = min(x_in, gain / _span(region) * cap) if gain is not None else 0.0
        if attributed > 0.0:
            flows.append(ExternalFlow(region=r, direction="in", source="coastal_flood", amount=attributed))
        if x_in - attributed > 0.0:
            flows.append(ExternalFlow(region=r, direction="in", source="unattributed", amount=x_in - attributed))
    if x_out > 0.0:
        flows.append(ExternalFlow(region=r, direction="out", source="unattributed", amount=x_out))
    return flows


def _compute(world, state: WatershedState, stale: bool = False) -> _Plan:
    from chronicler.climate import climate_trend_share, get_climate_phase, region_harvest_shocks
    from chronicler.geography import climate_exposure
    turn = int(world.turn)
    phase = get_climate_phase(turn, world.climate_config)
    key = phase.value
    trend = climate_trend_share(world)
    shocks = region_harvest_shocks(world)
    regions = world.regions
    n = len(regions)
    if len(state.graph.down) != n or len(state.storage) != n or len(state.last_index) != n:
        raise RuntimeError("watershed state does not match the world's regions")
    cols = {name: [0.0] * n for name in FRAME_COLUMNS}
    routed = {"to_sea": [0.0] * n, "to_sink": [0.0] * n, "to_lake": [0.0] * n, "transfer": [0.0] * n}
    contributions: list[list[tuple[int, float]]] = [[] for _ in range(n)]
    external: list[ExternalFlow] = []
    normal, covers, unmet, channels = [0.0] * n, [0.0] * n, [0.0] * n, [0.0] * n
    for r in state.graph.order:
        region = regions[r]
        cover = _cover(region)
        cap = capacity(cover)
        s = float(state.storage[r])
        x = (float(region.ecology.water) - float(state.last_index[r])) / _span(region) * cap
        x_in = x if x > 0.0 else 0.0
        want = -x if x < 0.0 else 0.0
        x_out = min(s, want)
        external.extend(_external(world, region, r, x_in, x_out, cap, stale))
        exposure = climate_exposure(region.latitude_band, phase)
        p_norm = PRECIPITATION_BASE * (0.2 + float(region.geo.moisture))
        factor = max(0.0, 1.0 - (1.0 - PHASE_PRECIPITATION[key]) * exposure * trend)
        p = p_norm * factor * max(0.0, 1.0 - SHOCK_PRECIPITATION * float(shocks[r]))
        if key == "warming" and region.terrain == "tundra":
            p += TUNDRA_MELT
        i = math.fsum(q for _, q in contributions[r])
        a = s + p + x_in - x_out + i
        e_pot = (EVAPORATION_BASE * (1.0 + (PHASE_EVAPORATION[key] - 1.0) * exposure * trend)
                 * TERRAIN_EVAPORATION.get(region.terrain, 1.0) * (1.0 + TRANSPIRATION * cover))
        e = min(a, e_pot)
        t = a - e
        w = min(t, IRRIGATION_DEMAND) if _irrigated(world, region) else 0.0
        b = t - w
        s2 = (1.0 - BASEFLOW) * min(b, cap)
        q = b - s2
        d = state.graph.down[r]
        if d >= 0:
            contributions[d].append((r, q))
            routed["transfer"][r] = q
        elif d == SEA:
            routed["to_sea"][r] = q
        elif d == LAKE:
            routed["to_lake"][r] = q
        else:
            routed["to_sink"][r] = q
        channel = CHANNEL_CAPACITY * (RIVER_CHANNEL_FACTOR if region.river_mask else 1.0)
        for name, value in (("storage_open", s), ("precipitation", p), ("external_in", x_in),
                            ("external_out", x_out), ("inflow", i), ("evaporation", e), ("withdrawal", w),
                            ("outflow", q), ("storage", s2), ("capacity", cap),
                            ("index_derived", derived_index(region, s2, w, cap)),
                            ("flood_excess", max(0.0, p + i + x_in - channel))):
            cols[name][r] = value
        normal[r], covers[r], unmet[r], channels[r] = p_norm, cover, want - x_out, channel
    residual = check_closure(state.graph.down, cols, routed)
    external.sort(key=lambda f: (f.region, f.direction, f.source))
    return _Plan(turn, key, cols, routed, contributions, normal, covers, unmet, channels, residual, external, stale)


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
    plan = _compute(world, state, stale=dropped or int(world.turn) != expected)
    state._plan = plan
    state.counters["planned_turns"] = state.counters.get("planned_turns", 0) + 1


def after_ecology(world, acc) -> list:
    """Record the index the tick produced beside the derived one, the
    floods and droughts with their conditions, and commit the turn."""
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

    floods = []
    for r in range(n):
        if cols["flood_excess"][r] > 0.0:
            floods.append(FloodRecord(
                turn=plan.turn, region=r, excess=cols["flood_excess"][r],
                arrivals=cols["precipitation"][r] + cols["inflow"][r] + cols["external_in"][r],
                channel=plan.channel[r], precipitation=cols["precipitation"][r], inflow=cols["inflow"][r],
                external_in=cols["external_in"][r], storage_open=cols["storage_open"][r],
                capacity=cols["capacity"][r], tributaries=list(plan.contributions[r]),
                upstream_cover=mean_cover(r),
                upstream_deforested=sum(1 for u in up[r] if plan.cover[u] < DEFORESTED_COVER)))

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
                           totals=totals, storage_open=storage_open, storage_close=storage_close,
                           closure_residual=plan.residual, drought_turns=drought_turns,
                           external=plan.external, stale_baseline=plan.stale)

    # Commit: storage, the observed index, the spells, the frame and the totals.
    state.storage = list(cols["storage"])
    state.last_index = list(cols["index_observed"])
    state.spells = spells
    state.frame = frame
    state.cumulative = cumulative
    counters = state.counters
    for key in COUNTER_KEYS:
        counters.setdefault(key, 0)
    counters["settled_turns"] += 1
    counters["flood_region_turns"] += len(floods)
    counters["drought_region_turns"] += open_count
    counters["droughts_declared"] += declared
    counters["droughts_ended"] += ended_count
    counters["external_out_unmet_turns"] += 1 if unmet > 0.0 else 0
    counters["stale_baseline_turns"] += 1 if plan.stale else 0
    return []


# --- Protocol: observation ------------------------------------------------------------

def parameters() -> dict:
    """The declared constants (uncalibrated)."""
    return {
        "storage_base": STORAGE_BASE, "forest_retention": FOREST_RETENTION,
        "precipitation_base": PRECIPITATION_BASE, "phase_precipitation": dict(PHASE_PRECIPITATION),
        "shock_precipitation": SHOCK_PRECIPITATION, "tundra_melt": TUNDRA_MELT,
        "evaporation_base": EVAPORATION_BASE, "phase_evaporation": dict(PHASE_EVAPORATION),
        "terrain_evaporation": dict(TERRAIN_EVAPORATION), "transpiration": TRANSPIRATION,
        "baseflow": BASEFLOW, "irrigation_demand": IRRIGATION_DEMAND, "irrigation_wetting": IRRIGATION_WETTING,
        "channel_capacity": CHANNEL_CAPACITY, "river_channel_factor": RIVER_CHANNEL_FACTOR,
        "drought_fraction": DROUGHT_FRACTION, "drought_turns": DROUGHT_TURNS,
        "deforested_cover": DEFORESTED_COVER, "index_floor": INDEX_FLOOR,
        "closure_tolerance": CLOSURE_TOLERANCE,
    }


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
        out[key] = _r(out[key])
    out["tributaries"] = [[int(u), _r(q)] for u, q in flood.tributaries]
    if out["upstream_cover"] is not None:
        out["upstream_cover"] = _r(out["upstream_cover"])
    return out


#: Per-region columns of the snapshot record. ``outflow`` is left out: it is
#: the residual of each region's account by construction, so a reader derives
#: it (``storage_open + precipitation + external_in - external_out + inflow -
#: evaporation - withdrawal - storage``); the state keeps it.
SNAPSHOT_COLUMNS: tuple[str, ...] = tuple(name for name in FRAME_COLUMNS if name != "outflow")


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
    ``floods``, ``droughts``, ``external`` and ``totals`` None, not empty)
    when no Phase 9 was settled in the completed turn; ``storage`` (the
    account's current storage) is recorded only then, since a settled
    turn's ``regions.storage`` is the same list."""
    state = _state(world)
    source_turn = world.turn - 1
    frame = state.frame
    observed = frame is not None and frame.turn == source_turn
    cumulative = {key: _r(value) for key, value in state.cumulative.items()}
    storage_now = math.fsum(state.storage)
    record = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
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
        "droughts": None,
        "external": None,
        "totals": None,
        "storage": None if observed else [_r(v) for v in state.storage],
        "cumulative": {**cumulative, "opening_storage": _r(state.opening_storage), "storage": _r(storage_now),
                       "closure_residual": math.fsum([storage_now, -state.opening_storage]
                                                     + [-v for v in _net(state.cumulative)])},
        "counters": dict(state.counters),
    })
    if observed:
        record["regions"] = {**{name: [_r(v) for v in frame.columns[name]] for name in SNAPSHOT_COLUMNS},
                             "drought_turns": list(frame.drought_turns)}
        record["floods"] = [_flood(f) for f in frame.floods]
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
    return record
