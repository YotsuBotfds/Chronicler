"""Geography 2.0: procedural world generation for worlds beyond the template set.

Pipeline (all deterministic from the world seed through namespaced streams,
``stable_hash_int("geography", seed, <stream>, ...)``; no module RNG):

1. Sites. A jittered grid of ``cells ~= regions / LAND_FRACTION`` points over
   the 100 x 100 map.
2. Heightmap. Fractal value noise plus a few continent "bumps" and an edge
   falloff. The ``regions`` highest cells become land, so the land count is
   exact; the rest is water.
3. Cells. A raster Voronoi partition (each pixel belongs to its nearest site;
   the jittered grid bounds the search to the 5 x 5 surrounding grid cells)
   gives real neighbour relations: two cells are neighbours when their pixel
   areas share a border.
4. Climate. Latitude runs pole to pole along y (with a seeded offset);
   temperature falls with latitude and elevation; moisture combines latitude
   belts (wet equator and mid-latitudes, dry subtropics and poles), distance
   from the sea and noise. ``latitude_band`` (0 equatorial .. 4 polar) is
   stored per region and feeds the climate exposure of the ecology tick.
5. Terrain from elevation x moisture x temperature: mountains, hills, tundra,
   desert, steppe, jungle, marsh, forest, plains, and coast for low coastal
   plains and steppe.
6. Rivers. Every land cell drains to its lowest neighbour; rain-weighted flow
   accumulates downhill and cells above a flow threshold become river cells.
   River paths run source to mouth (upstream first); tributaries end at their
   confluence so they share that region with the main stem.
7. Water. Connected water bodies are split into named sea zones (lakes, seas,
   oceans). Zones are not ownable regions. Coastal regions bordering the same
   zone get sea lanes to their nearest same-zone neighbours within range, so
   distant coasts are not neighbours (the template generator's all-coastal
   clique is kept for template worlds only). Remaining land masses are joined
   by the shortest crossing that shares a water body.

The output is plain :class:`Region` objects plus :class:`WorldGeography`
metadata; everything downstream (resources, roles, civilizations) is applied by
``world_gen.generate_world``.
"""
from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field

from chronicler.models import Region, RegionGeography, River, SeaZone, WorldGeography
from chronicler.utils import stable_hash_int

GENERATOR_VERSION = 1
MAP_SIZE = 100.0
LAND_FRACTION = 0.5
RASTER = 6                     # pixels per grid-cell side for the Voronoi raster
MIN_SHARED_EDGE = 2            # pixel edges two cells must share to be neighbours
ZONE_CELLS = 7                 # target water cells per sea zone
LAKE_MAX_CELLS = 3
LANE_RANGE = 2.6               # sea-lane reach, in grid spacings
LANES_PER_REGION = 2
RIVER_FLOW_THRESHOLD = 2.0     # rain-weighted drainage needed to form a river
CROSSROADS_DEGREE = 7          # procedural role: hubs (interior Voronoi cells average ~6)
CHOKEPOINT_SHARE = 0.05        # procedural role: top betweenness share marked chokepoint

# Latitude bands: |latitude| upper bounds for bands 0..3; band 4 above.
LATITUDE_BAND_LIMITS = (0.15, 0.35, 0.6, 0.8)
LATITUDE_BAND_NAMES = ("equatorial", "tropical", "temperate", "subpolar", "polar")

# Climate exposure by latitude band (0 equatorial .. 4 polar): multiplies the
# climate-driven ecology losses (drought water loss; cooling water loss and
# forest damage) in both the Python and Rust ecology ticks. Template worlds
# have no band and use 1.0, which leaves their arithmetic bit-identical.
LATITUDE_CLIMATE_EXPOSURE: dict[str, tuple[float, ...]] = {
    "drought": (0.8, 1.4, 1.0, 0.7, 0.5),
    "cooling": (0.4, 0.7, 1.0, 1.4, 1.8),
}
# Disaster odds by latitude band (climate.check_disasters).
LATITUDE_DISASTER_FACTOR: dict[str, tuple[float, ...]] = {
    "flood": (1.4, 1.2, 1.0, 0.8, 0.6),
    "wildfire": (0.8, 1.3, 1.0, 0.9, 0.5),
    "sandstorm": (0.8, 1.3, 1.0, 0.6, 0.3),
}


def climate_exposure(latitude_band: int | None, phase) -> float:
    """Scale of climate-driven ecology losses for a region in ``phase``."""
    if latitude_band is None:
        return 1.0
    table = LATITUDE_CLIMATE_EXPOSURE.get(getattr(phase, "value", phase))
    return table[latitude_band] if table else 1.0


def disaster_factor(latitude_band: int | None, disaster: str) -> float:
    if latitude_band is None:
        return 1.0
    table = LATITUDE_DISASTER_FACTOR.get(disaster)
    return table[latitude_band] if table else 1.0


PROCEDURAL_TERRAINS = (
    "plains", "steppe", "coast", "forest", "jungle", "marsh",
    "hills", "mountains", "desert", "tundra",
)

TERRAIN_BASE_CAPACITY: dict[str, int] = {
    "plains": 68, "steppe": 52, "coast": 58, "forest": 50, "jungle": 46,
    "marsh": 40, "hills": 44, "mountains": 34, "desert": 26, "tundra": 20,
}

TERRAIN_LEGACY_RESOURCES: dict[str, str] = {
    "plains": "fertile", "steppe": "fertile", "marsh": "fertile",
    "coast": "maritime", "forest": "timber", "jungle": "timber",
    "hills": "mineral", "mountains": "mineral", "desert": "barren", "tundra": "barren",
}

TERRAIN_NAME_SUFFIXES: dict[str, tuple[str, ...]] = {
    "plains": ("Plains", "Fields", "Vale", "Meadows", "Lowlands", "Downs"),
    "steppe": ("Steppe", "Grasslands", "Expanse", "Prairie"),
    "coast": ("Coast", "Shore", "Strand", "Shores", "Coastlands"),
    "forest": ("Forest", "Wood", "Weald", "Woods", "Greenwood"),
    "jungle": ("Jungle", "Rainforest", "Wilds", "Tangle"),
    "marsh": ("Marsh", "Fen", "Mire", "Wetlands", "Bog"),
    "hills": ("Hills", "Highlands", "Uplands", "Heights"),
    "mountains": ("Mountains", "Peaks", "Crags", "Range", "Spires"),
    "desert": ("Desert", "Wastes", "Sands", "Dunes", "Barrens"),
    "tundra": ("Tundra", "Frostlands", "Icefields", "Snowfields"),
}


# --- Names -------------------------------------------------------------------

@dataclass(frozen=True)
class Phonology:
    """A small syllable inventory; names are onset+vowel syllables + an ending."""
    key: str
    onsets: tuple[str, ...]
    vowels: tuple[str, ...]
    endings: tuple[str, ...]


PHONOLOGIES: dict[str, Phonology] = {
    "maritime": Phonology("maritime", ("th", "n", "m", "l", "s", "p", "c", "t", "r", "v", "d"),
                          ("a", "e", "i", "o", "a", "e", "y"),
                          ("ros", "nis", "ra", "lene", "rion", "thys", "ndor", "sa")),
    "steppe": Phonology("steppe", ("t", "b", "kh", "ch", "s", "m", "q", "j", "y", "d", "g"),
                        ("a", "o", "u", "e", "a", "i"),
                        ("rai", "kan", "gur", "tai", "jak", "dun", "dar", "khan")),
    "mountain": Phonology("mountain", ("gr", "d", "k", "b", "dr", "st", "th", "h", "v", "m"),
                          ("a", "o", "u", "e", "i", "a"),
                          ("dun", "rak", "grim", "mor", "hold", "gar", "dur", "heim")),
    "forest": Phonology("forest", ("l", "s", "f", "v", "th", "n", "r", "w", "m", "g"),
                        ("a", "e", "i", "o", "y", "a"),
                        ("wen", "riel", "lion", "ra", "deth", "dor", "las", "wyn")),
    "desert": Phonology("desert", ("kh", "z", "sh", "r", "m", "q", "d", "s", "h", "b"),
                        ("a", "i", "u", "e", "a"),
                        ("rad", "zar", "shan", "mir", "dum", "rah", "biya", "sul")),
    "jungle": Phonology("jungle", ("x", "tz", "k", "ch", "y", "m", "p", "t", "h", "n"),
                        ("a", "i", "o", "u", "e"),
                        ("tl", "pan", "lec", "toya", "mapa", "xa", "chum", "naca")),
    "marsh": Phonology("marsh", ("m", "b", "gl", "w", "f", "h", "br", "s", "d"),
                       ("o", "u", "e", "a"),
                       ("moor", "fen", "wick", "ley", "ham", "mere", "by", "ton")),
    "tundra": Phonology("tundra", ("k", "sk", "v", "h", "br", "fr", "t", "y", "j", "s"),
                        ("a", "e", "o", "u", "i"),
                        ("vik", "gard", "mar", "dal", "heim", "ka", "nor", "ros")),
}

TERRAIN_PHONOLOGY: dict[str, str] = {
    "coast": "maritime", "plains": "steppe", "steppe": "steppe", "hills": "mountain",
    "mountains": "mountain", "forest": "forest", "jungle": "jungle", "marsh": "marsh",
    "desert": "desert", "tundra": "tundra",
}


def make_name(rng: random.Random, phon: Phonology, *, min_syllables: int = 1,
              max_syllables: int = 2) -> str:
    """Compose a pronounceable name from ``phon`` (capitalized)."""
    parts = []
    for _ in range(rng.randint(min_syllables, max_syllables)):
        parts.append(rng.choice(phon.onsets) + rng.choice(phon.vowels))
    parts.append(rng.choice(phon.endings))
    word = "".join(parts)
    # Collapse tripled letters that the syllable joins can produce.
    out = []
    for ch in word:
        if len(out) >= 2 and out[-1] == ch and out[-2] == ch:
            continue
        out.append(ch)
    return "".join(out).capitalize()


def unique_name(rng: random.Random, used: set[str], build) -> str:
    """Draw names from ``build(rng)`` until one is unused; record it."""
    for _ in range(64):
        name = build(rng)
        if name not in used:
            used.add(name)
            return name
    base = build(rng)
    n = 2
    while f"{base} {n}" in used:
        n += 1
    used.add(f"{base} {n}")
    return f"{base} {n}"


# --- Noise -------------------------------------------------------------------

class _ValueNoise:
    """Seeded 2D value noise with smoothstep interpolation and fBm octaves."""

    def __init__(self, seed: int, stream: str) -> None:
        rng = random.Random(stable_hash_int("geography", seed, "noise", stream))
        self._perm = list(range(256))
        rng.shuffle(self._perm)
        self._perm += self._perm
        self._values = [rng.random() for _ in range(256)]

    def _lattice(self, ix: int, iy: int) -> float:
        return self._values[self._perm[(self._perm[ix & 255] + iy) & 255]]

    def noise(self, x: float, y: float) -> float:
        ix, iy = math.floor(x), math.floor(y)
        fx, fy = x - ix, y - iy
        sx = fx * fx * (3.0 - 2.0 * fx)
        sy = fy * fy * (3.0 - 2.0 * fy)
        a = self._lattice(ix, iy)
        b = self._lattice(ix + 1, iy)
        c = self._lattice(ix, iy + 1)
        d = self._lattice(ix + 1, iy + 1)
        top = a + (b - a) * sx
        bottom = c + (d - c) * sx
        return top + (bottom - top) * sy

    def fbm(self, u: float, v: float, *, base: float = 3.0, octaves: int = 4) -> float:
        total, amp, norm, freq = 0.0, 1.0, 0.0, base
        for octave in range(octaves):
            total += amp * self.noise(u * freq + 17.0 * octave, v * freq + 31.0 * octave)
            norm += amp
            amp *= 0.5
            freq *= 2.0
        return total / norm


def _q(value: float) -> float:
    """Quantize generator floats so libm last-ulp differences cannot flip ties."""
    return round(value, 6)


def latitude_band(latitude: float) -> int:
    a = abs(latitude)
    for band, limit in enumerate(LATITUDE_BAND_LIMITS):
        if a < limit:
            return band
    return len(LATITUDE_BAND_LIMITS)


# --- Generator ---------------------------------------------------------------

@dataclass
class ProceduralGeography:
    regions: list[Region]
    rivers: list[River]
    geography: WorldGeography
    # Land-mass crossings added for connectivity (region-name pairs; also sea lanes).
    crossings: list[tuple[str, str]] = field(default_factory=list)
    # Diagnostics (not persisted)
    cell_count: int = 0
    land_cells: list[int] = field(default_factory=list)


def _stream(seed: int, *parts: object) -> random.Random:
    return random.Random(stable_hash_int("geography", seed, *parts))


def generate_procedural_geography(count: int, seed: int) -> ProceduralGeography:
    """Generate ``count`` land regions with neighbours, terrain, rivers and seas."""
    if count < 2:
        raise ValueError(f"Procedural worlds need at least 2 regions (got {count})")

    # 1. Sites on a jittered grid.
    target = max(count + 4, math.ceil(count / LAND_FRACTION))
    cols = max(3, math.ceil(math.sqrt(target)))
    rows = max(3, math.ceil(target / cols))
    n_cells = cols * rows
    sx, sy = MAP_SIZE / cols, MAP_SIZE / rows
    site_rng = _stream(seed, "sites")
    xs: list[float] = []
    ys: list[float] = []
    for j in range(rows):
        for i in range(cols):
            xs.append(_q((i + 0.5 + site_rng.uniform(-0.38, 0.38)) * sx))
            ys.append(_q((j + 0.5 + site_rng.uniform(-0.38, 0.38)) * sy))

    # 2. Heightmap; the `count` highest cells are land.
    shape_rng = _stream(seed, "continents")
    n_continents = max(1, min(7, 1 + count // 30))
    continents = [
        (shape_rng.uniform(0.2, 0.8), shape_rng.uniform(0.2, 0.8),
         shape_rng.uniform(0.16, 0.3), shape_rng.uniform(0.45, 0.7))
        for _ in range(n_continents)
    ]
    height_noise = _ValueNoise(seed, "height")
    elevation: list[float] = []
    for c in range(n_cells):
        u, v = xs[c] / MAP_SIZE, ys[c] / MAP_SIZE
        e = 0.55 * height_noise.fbm(u, v)
        for cu, cv, radius, weight in continents:
            e += weight * math.exp(-((u - cu) ** 2 + (v - cv) ** 2) / (radius * radius))
        edge = max(abs(u - 0.5), abs(v - 0.5)) * 2.0
        e -= 0.6 * edge ** 4
        elevation.append(_q(e))
    ranked = sorted(range(n_cells), key=lambda c: (-elevation[c], c))
    is_land = [False] * n_cells
    for c in ranked[:count]:
        is_land[c] = True
    sea_level = elevation[ranked[count - 1]]

    # 3. Raster Voronoi neighbours.
    neighbours = _voronoi_neighbours(xs, ys, cols, rows)

    land_cells = [c for c in range(n_cells) if is_land[c]]  # row-major = region order
    region_of = {c: k for k, c in enumerate(land_cells)}

    # 4. Climate fields.
    lat_rng = _stream(seed, "latitude")
    span = lat_rng.uniform(2.2, 2.5)  # land sits mid-map; reach both polar bands
    lat_north = _q(span / 2.0 + lat_rng.uniform(-0.15, 0.15))  # latitude at y = 0
    ocean_dist = _water_distance(n_cells, neighbours, is_land)
    land_elev = sorted(elevation[c] for c in land_cells)
    max_elev = land_elev[-1]
    elev_rank: dict[int, float] = {}
    order = sorted(land_cells, key=lambda c: (elevation[c], c))
    for r, c in enumerate(order):
        elev_rank[c] = r / max(1, len(order) - 1)
    moist_noise = _ValueNoise(seed, "moisture")
    temp_noise = _ValueNoise(seed, "temperature")
    latitude: dict[int, float] = {}
    moisture: dict[int, float] = {}
    temperature: dict[int, float] = {}
    elev_norm: dict[int, float] = {}
    for c in land_cells:
        u, v = xs[c] / MAP_SIZE, ys[c] / MAP_SIZE
        lat = _q(lat_north - v * span)
        latitude[c] = max(-1.0, min(1.0, lat))
        a = abs(latitude[c])
        # Wet equator and mid-latitudes, dry subtropics and poles.
        belt = 0.5 + 0.38 * math.cos(a * 3.0 * math.pi)
        near_sea = math.exp(-(ocean_dist[c] - 1) / 1.5)
        m = 0.5 * belt + 0.3 * near_sea + 0.2 * moist_noise.fbm(u, v, base=4.0)
        moisture[c] = _q(max(0.0, min(1.0, m)))
        en = (elevation[c] - sea_level) / max(1e-9, max_elev - sea_level)
        elev_norm[c] = _q(max(0.0, min(1.0, en)))
        t = 1.0 - a * 1.05 - 0.3 * elev_rank[c] + 0.12 * (temp_noise.fbm(u, v) - 0.5)
        temperature[c] = _q(t)

    coastal = {c: any(not is_land[n] for n in neighbours[c]) for c in land_cells}

    # 5. Terrain.
    terrain: dict[int, str] = {}
    for c in land_cells:
        terrain[c] = _classify_terrain(
            elev_rank[c], moisture[c], temperature[c], coastal[c],
        )

    # 6. Rivers (cell paths, upstream first).
    river_cells = _river_paths(land_cells, neighbours, elevation, is_land, moisture)

    # 7. Sea zones and sea lanes.
    zones, cell_zone = _sea_zones(n_cells, neighbours, is_land, xs, ys, cols, rows)

    # --- Build regions -------------------------------------------------------
    name_rng = _stream(seed, "names", "regions")
    used_names: set[str] = set()
    cap_rng = _stream(seed, "capacity")
    regions: list[Region] = []
    for k, c in enumerate(land_cells):
        t = terrain[c]
        phon = PHONOLOGIES[TERRAIN_PHONOLOGY[t]]
        suffixes = TERRAIN_NAME_SUFFIXES[t]
        name = unique_name(
            name_rng, used_names,
            lambda r, phon=phon, suffixes=suffixes: f"{make_name(r, phon)} {r.choice(suffixes)}",
        )
        capacity = TERRAIN_BASE_CAPACITY[t] + cap_rng.randint(-6, 6) + round(8 * moisture[c])
        capacity = max(12, min(80, capacity))
        region = Region(
            name=name,
            terrain=t,
            carrying_capacity=capacity,
            resources=TERRAIN_LEGACY_RESOURCES[t],
            x=xs[c],
            y=ys[c],
        )
        region.latitude_band = latitude_band(latitude[c])
        region.geo = RegionGeography(
            elevation=elev_norm[c], moisture=moisture[c], latitude=latitude[c],
            coastal=coastal[c],
        )
        regions.append(region)

    # Land adjacency (sorted by region index for deterministic iteration).
    adjacency: list[set[int]] = [set() for _ in land_cells]
    for k, c in enumerate(land_cells):
        for n in neighbours[c]:
            if is_land[n]:
                adjacency[k].add(region_of[n])

    # Sea zones: names, coastal regions, neighbour zones.
    zone_rng = _stream(seed, "names", "seas")
    zone_names: list[str] = []
    sea_phon = PHONOLOGIES["maritime"]
    for z in zones:
        if z["kind"] == "lake":
            build = lambda r: f"Lake {make_name(r, sea_phon)}"
        else:
            forms = ("the {} Sea", "the Gulf of {}", "the {} Deep", "the {} Bight",
                     "the {} Sound") if z["kind"] == "ocean" else ("the {} Sea", "the {} Basin")
            build = lambda r, forms=forms: r.choice(forms).format(make_name(r, sea_phon))
        zone_names.append(unique_name(zone_rng, used_names, build))
    zone_coast: list[set[int]] = [set() for _ in zones]
    zone_nbrs: list[set[int]] = [set() for _ in zones]
    region_zones: list[set[int]] = [set() for _ in land_cells]
    for c in range(n_cells):
        if is_land[c]:
            for n in neighbours[c]:
                if not is_land[n]:
                    zone_coast[cell_zone[n]].add(region_of[c])
                    region_zones[region_of[c]].add(cell_zone[n])
        else:
            for n in neighbours[c]:
                if not is_land[n] and cell_zone[n] != cell_zone[c]:
                    zone_nbrs[cell_zone[c]].add(cell_zone[n])

    # Sea lanes: each coastal region links to its nearest same-zone coasts.
    lane_range2 = (LANE_RANGE * max(sx, sy)) ** 2
    lanes: set[tuple[int, int]] = set()
    for zi in range(len(zones)):
        members = sorted(zone_coast[zi])
        for a in members:
            cands = []
            for b in members:
                if b == a or b in adjacency[a]:
                    continue
                d2 = _d2(xs, ys, land_cells[a], land_cells[b])
                if d2 <= lane_range2:
                    cands.append((d2, b))
            cands.sort()
            for _, b in cands[:LANES_PER_REGION]:
                lanes.add((min(a, b), max(a, b)))
    for a, b in lanes:
        adjacency[a].add(b)
        adjacency[b].add(a)

    # Join remaining land masses by the shortest crossing over a shared water body.
    body_of_zone = [z["body"] for z in zones]
    region_bodies = [{body_of_zone[z] for z in zs} for zs in region_zones]
    crossing_ids = _connect_components(adjacency, land_cells, xs, ys, region_bodies, lanes)

    for k, region in enumerate(regions):
        region.adjacencies = [regions[n].name for n in sorted(adjacency[k])]
        region.geo.sea_zones = [zone_names[z] for z in sorted(region_zones[k])]

    rivers = _name_rivers(river_cells, region_of, regions, seed, used_names)

    sea_zones = [
        SeaZone(
            name=zone_names[zi], kind=z["kind"], x=z["x"], y=z["y"], cells=len(z["cells"]),
            coastal_regions=[regions[k].name for k in sorted(zone_coast[zi])],
            neighbors=[zone_names[o] for o in sorted(zone_nbrs[zi])],
        )
        for zi, z in enumerate(zones)
    ]
    geography = WorldGeography(
        generator="procedural",
        version=GENERATOR_VERSION,
        cells=n_cells,
        land_regions=count,
        sea_zones=sea_zones,
        sea_lanes=sorted((regions[a].name, regions[b].name) for a, b in sorted(lanes)),
    )
    return ProceduralGeography(
        regions=regions, rivers=rivers, geography=geography,
        crossings=[(regions[a].name, regions[b].name) for a, b in crossing_ids],
        cell_count=n_cells, land_cells=land_cells,
    )


def classify_procedural_roles(
    regions: list[Region], crossings: list[tuple[str, str]],
) -> dict[str, str]:
    """Region roles for procedural graphs.

    ``adjacency.classify_regions`` calls every region with 3+ neighbours a
    crossroads, which on a Voronoi map is nearly all of them. Here:
    frontier = at most 2 neighbours; chokepoint = articulation point, an
    endpoint of a land-mass crossing, or a bottleneck (betweenness centrality
    in the top CHOKEPOINT_SHARE and above twice the mean); crossroads = at
    least CROSSROADS_DEGREE neighbours; standard otherwise.
    """
    from chronicler.adjacency import _find_articulation_points
    articulation = _find_articulation_points({r.name: list(r.adjacencies) for r in regions})
    straits = {name for pair in crossings for name in pair}
    betweenness = _betweenness(regions)
    mean = sum(betweenness) / max(1, len(betweenness))
    ranked = sorted(range(len(regions)), key=lambda i: (-betweenness[i], i))
    bottlenecks = {
        regions[i].name
        for i in ranked[:max(1, round(CHOKEPOINT_SHARE * len(regions)))]
        if betweenness[i] > 2.0 * mean
    }
    roles: dict[str, str] = {}
    for region in regions:
        degree = len(region.adjacencies)
        if degree <= 2:
            roles[region.name] = "frontier"
        elif region.name in articulation or region.name in straits or region.name in bottlenecks:
            roles[region.name] = "chokepoint"
        elif degree >= CROSSROADS_DEGREE:
            roles[region.name] = "crossroads"
        else:
            roles[region.name] = "standard"
    return roles


def _betweenness(regions: list[Region]) -> list[float]:
    """Unweighted betweenness centrality (Brandes); exact up to 400 regions,
    then estimated from every k-th source (deterministic)."""
    index = {r.name: i for i, r in enumerate(regions)}
    adj = [sorted(index[a] for a in r.adjacencies if a in index) for r in regions]
    n = len(regions)
    step = max(1, math.ceil(n / 400))
    score = [0.0] * n
    for s in range(0, n, step):
        stack: list[int] = []
        preds: list[list[int]] = [[] for _ in range(n)]
        sigma = [0] * n
        sigma[s] = 1
        dist = [-1] * n
        dist[s] = 0
        queue: deque[int] = deque([s])
        while queue:
            v = queue.popleft()
            stack.append(v)
            for w in adj[v]:
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    queue.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    preds[w].append(v)
        delta = [0.0] * n
        while stack:
            w = stack.pop()
            for v in preds[w]:
                delta[v] += sigma[v] / sigma[w] * (1.0 + delta[w])
            if w != s:
                score[w] += delta[w]
    return [_q(x * step) for x in score]


def _classify_terrain(rank: float, moisture: float, temp: float, coastal: bool) -> str:
    if rank >= 0.9:
        return "mountains"
    if temp < 0.1:
        return "tundra"
    if rank >= 0.77:
        return "hills" if temp >= 0.2 else "tundra"
    if moisture < 0.3:
        terrain = "desert" if temp >= 0.5 else "steppe"
    elif moisture < 0.43:
        terrain = "steppe" if temp < 0.85 or moisture < 0.36 else "plains"
    elif moisture >= 0.64 and temp >= 0.72:
        terrain = "jungle"
    elif moisture >= 0.68 and rank < 0.2:
        terrain = "marsh"
    elif moisture >= 0.58:
        terrain = "forest"
    else:
        terrain = "plains"
    if coastal and terrain in ("plains", "steppe"):
        return "coast"
    return terrain


def _d2(xs: list[float], ys: list[float], a: int, b: int) -> float:
    dx = xs[a] - xs[b]
    dy = ys[a] - ys[b]
    return dx * dx + dy * dy


def _voronoi_neighbours(xs: list[float], ys: list[float], cols: int, rows: int) -> list[list[int]]:
    """Cells whose raster Voronoi areas share at least MIN_SHARED_EDGE pixel edges."""
    width, height = cols * RASTER, rows * RASTER
    px_w, px_h = MAP_SIZE / width, MAP_SIZE / height
    owner = [0] * (width * height)
    for gj in range(rows):
        for gi in range(cols):
            cands = [
                jj * cols + ii
                for jj in range(max(0, gj - 2), min(rows, gj + 3))
                for ii in range(max(0, gi - 2), min(cols, gi + 3))
            ]
            for py in range(gj * RASTER, (gj + 1) * RASTER):
                y = (py + 0.5) * px_h
                row = py * width
                for px in range(gi * RASTER, (gi + 1) * RASTER):
                    x = (px + 0.5) * px_w
                    best, best_d = cands[0], float("inf")
                    for c in cands:
                        dx = x - xs[c]
                        dy = y - ys[c]
                        d = dx * dx + dy * dy
                        if d < best_d:
                            best, best_d = c, d
                    owner[row + px] = best
    shared: dict[tuple[int, int], int] = {}
    for py in range(height):
        row = py * width
        for px in range(width):
            a = owner[row + px]
            if px + 1 < width:
                b = owner[row + px + 1]
                if a != b:
                    key = (a, b) if a < b else (b, a)
                    shared[key] = shared.get(key, 0) + 1
            if py + 1 < height:
                b = owner[row + width + px]
                if a != b:
                    key = (a, b) if a < b else (b, a)
                    shared[key] = shared.get(key, 0) + 1
    nbrs: list[set[int]] = [set() for _ in range(cols * rows)]
    for (a, b), n in shared.items():
        if n >= MIN_SHARED_EDGE:
            nbrs[a].add(b)
            nbrs[b].add(a)
    return [sorted(s) for s in nbrs]


def _water_distance(n_cells: int, neighbours: list[list[int]], is_land: list[bool]) -> list[int]:
    """Hop distance from each cell to the nearest water cell (0 for water)."""
    dist = [-1] * n_cells
    queue: deque[int] = deque()
    for c in range(n_cells):
        if not is_land[c]:
            dist[c] = 0
            queue.append(c)
    while queue:
        c = queue.popleft()
        for n in neighbours[c]:
            if dist[n] < 0:
                dist[n] = dist[c] + 1
                queue.append(n)
    return [d if d >= 0 else n_cells for d in dist]


def _river_paths(
    land_cells: list[int], neighbours: list[list[int]], elevation: list[float],
    is_land: list[bool], moisture: dict[int, float],
) -> list[list[int]]:
    """Downhill drainage -> river cell paths (source first, mouth or confluence last)."""
    downhill: dict[int, int | None] = {}
    for c in land_cells:
        lowest = min(neighbours[c], key=lambda n: (elevation[n], n), default=None)
        downhill[c] = lowest if lowest is not None and elevation[lowest] < elevation[c] else None
    flow = {c: 0.2 + moisture[c] for c in land_cells}
    for c in sorted(land_cells, key=lambda c: (-elevation[c], c)):
        d = downhill[c]
        if d is not None and is_land[d]:
            flow[d] += flow[c]
    river = {c for c in land_cells if flow[c] >= RIVER_FLOW_THRESHOLD}
    upstream: dict[int, list[int]] = {c: [] for c in river}
    for c in river:
        d = downhill[c]
        if d is not None and d in river:
            upstream[d].append(c)
    sources = [c for c in sorted(river) if not upstream[c]]

    def trace(c: int) -> list[int]:
        path = [c]
        while True:
            d = downhill[path[-1]]
            if d is None or not is_land[d] or d not in river:
                return path
            path.append(d)

    traced = sorted((trace(s) for s in sources), key=lambda p: (-len(p), p[0]))
    claimed: set[int] = set()
    paths: list[list[int]] = []
    for full in traced:
        path: list[int] = []
        for c in full:
            path.append(c)
            if c in claimed:
                break
        if len(path) >= 2:
            claimed.update(path)
            paths.append(path)
    return paths


def _name_rivers(
    river_cells: list[list[int]], region_of: dict[int, int], regions: list[Region],
    seed: int, used: set[str],
) -> list[River]:
    rng = _stream(seed, "names", "rivers")
    rivers: list[River] = []
    for path in river_cells:
        source = regions[region_of[path[0]]]
        phon = PHONOLOGIES[TERRAIN_PHONOLOGY[source.terrain]]
        name = unique_name(rng, used, lambda r, phon=phon: f"the {make_name(r, phon)} River")
        rivers.append(River(name=name, path=[regions[region_of[c]].name for c in path]))
    return rivers


def _sea_zones(
    n_cells: int, neighbours: list[list[int]], is_land: list[bool],
    xs: list[float], ys: list[float], cols: int, rows: int,
) -> tuple[list[dict], list[int]]:
    """Split water bodies into zones of about ZONE_CELLS cells."""
    cell_zone = [-1] * n_cells
    body = [-1] * n_cells
    zones: list[dict] = []
    bodies: list[list[int]] = []
    for c in range(n_cells):
        if is_land[c] or body[c] >= 0:
            continue
        comp = []
        body[c] = len(bodies)
        queue: deque[int] = deque([c])
        while queue:
            cur = queue.popleft()
            comp.append(cur)
            for n in neighbours[cur]:
                if not is_land[n] and body[n] < 0:
                    body[n] = body[c]
                    queue.append(n)
        bodies.append(sorted(comp))
    for bi, comp in enumerate(bodies):
        touches_edge = any(
            c % cols in (0, cols - 1) or c // cols in (0, rows - 1) for c in comp
        )
        if touches_edge:
            kind = "ocean"
        elif len(comp) <= LAKE_MAX_CELLS:
            kind = "lake"
        else:
            kind = "sea"
        n_zones = max(1, round(len(comp) / ZONE_CELLS)) if kind != "lake" else 1
        cx = sum(xs[c] for c in comp) / len(comp)
        cy = sum(ys[c] for c in comp) / len(comp)
        first = min(comp, key=lambda c: ((xs[c] - cx) ** 2 + (ys[c] - cy) ** 2, c))
        seeds = [first]
        min_d = {c: _d2(xs, ys, c, first) for c in comp}
        while len(seeds) < n_zones:
            nxt = max(comp, key=lambda c: (min_d[c], -c))
            if min_d[nxt] <= 0.0:
                break
            seeds.append(nxt)
            for c in comp:
                d = _d2(xs, ys, c, nxt)
                if d < min_d[c]:
                    min_d[c] = d
        base = len(zones)
        queue = deque()
        for k, s in enumerate(seeds):
            cell_zone[s] = base + k
            queue.append(s)
        while queue:
            cur = queue.popleft()
            for n in neighbours[cur]:
                if not is_land[n] and cell_zone[n] < 0:
                    cell_zone[n] = cell_zone[cur]
                    queue.append(n)
        for k in range(len(seeds)):
            cells = [c for c in comp if cell_zone[c] == base + k]
            zones.append({
                "kind": kind, "body": bi, "cells": cells,
                "x": _q(sum(xs[c] for c in cells) / len(cells)),
                "y": _q(sum(ys[c] for c in cells) / len(cells)),
            })
    return zones, cell_zone


def _components(adjacency: list[set[int]]) -> list[list[int]]:
    seen = [False] * len(adjacency)
    comps = []
    for start in range(len(adjacency)):
        if seen[start]:
            continue
        seen[start] = True
        comp = [start]
        queue: deque[int] = deque([start])
        while queue:
            cur = queue.popleft()
            for n in sorted(adjacency[cur]):
                if not seen[n]:
                    seen[n] = True
                    comp.append(n)
                    queue.append(n)
        comps.append(comp)
    return comps


def _connect_components(
    adjacency: list[set[int]], land_cells: list[int], xs: list[float], ys: list[float],
    region_bodies: list[set[int]], lanes: set[tuple[int, int]],
) -> None:
    """Add shortest crossings until the region graph is connected.

    Prefers coastal pairs on a common water body; falls back to the nearest
    shore pair (a land mass whose shores touch no shared body). Returns the
    crossings added, as region-index pairs.
    """
    added: list[tuple[int, int]] = []
    comps = _components(adjacency)
    while len(comps) > 1:
        best = None
        # Separate land masses are split by water, so only shores can join.
        shore = [[k for k in comp if region_bodies[k]] or comp for comp in comps]
        for other in shore[1:]:
            for a in shore[0]:
                for b in other:
                    shares = bool(region_bodies[a] & region_bodies[b])
                    key = (0 if shares else 1, _d2(xs, ys, land_cells[a], land_cells[b]), a, b)
                    if best is None or key < best:
                        best = key
        _, _, a, b = best
        adjacency[a].add(b)
        adjacency[b].add(a)
        lanes.add((min(a, b), max(a, b)))
        added.append((min(a, b), max(a, b)))
        comps = _components(adjacency)
    return added


# --- Rivers on regions (shared with scenario rivers) -------------------------

def assign_river_masks(regions: list[Region], rivers: list[River]) -> None:
    """Set bit ``i`` of ``Region.river_mask`` for every region on river ``i``."""
    region_map = {r.name: r for r in regions}
    for river_idx, river in enumerate(rivers):
        bit = 1 << river_idx
        for rname in river.path:
            region_map[rname].river_mask |= bit


def apply_river_bonuses(regions: list[Region], seed: int, tuning=None) -> None:
    """M35a river bonuses: water, carrying capacity and a fish slot.

    ``tuning`` is anything with ``tuning_overrides`` (a WorldState) or None
    for defaults. Applied once per river region, not per river.
    """
    from chronicler.ecology import clamp_ecology
    from chronicler.models import EMPTY_SLOT, ResourceType
    from chronicler.resources import RESOURCE_BASE
    from chronicler.tuning import K_RIVER_CAPACITY_MULTIPLIER, K_RIVER_WATER_BONUS, get_override

    water_bonus = get_override(tuning, K_RIVER_WATER_BONUS, 0.15)
    cap_mult = get_override(tuning, K_RIVER_CAPACITY_MULTIPLIER, 1.2)
    for region in regions:
        if region.river_mask == 0:
            continue
        # Water baseline
        region.ecology.water += water_bonus
        clamp_ecology(region)
        # Carrying capacity
        region.carrying_capacity = int(region.carrying_capacity * cap_mult)
        # Fish resource (Phoebe N-2: must also set base_yield)
        if ResourceType.FISH not in region.resource_types:
            for slot in range(3):
                if region.resource_types[slot] == EMPTY_SLOT:
                    region.resource_types[slot] = ResourceType.FISH
                    rng = random.Random(stable_hash_int("river_fish", seed, region.name))
                    variance = rng.uniform(-0.2, 0.2)
                    region.resource_base_yields[slot] = RESOURCE_BASE[ResourceType.FISH] * (1.0 + variance)
                    break
