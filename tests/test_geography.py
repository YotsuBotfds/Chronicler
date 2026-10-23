"""Geography 2.0: procedural worlds, sea zones, procedural civilizations."""
from __future__ import annotations

import hashlib
import math
from collections import Counter, deque

import pytest

from chronicler.geography import (
    LANE_RANGE,
    MAP_SIZE,
    PROCEDURAL_TERRAINS,
    climate_exposure,
    generate_procedural_geography,
    latitude_band,
)
from chronicler.models import ClimatePhase, WorldState
from chronicler.world_gen import (
    CIV_TEMPLATES,
    REGION_TEMPLATES,
    generate_world,
    resolve_worldgen,
)


def _bfs_reach(world, start=0):
    index = {r.name: i for i, r in enumerate(world.regions)}
    seen = {start}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        for name in world.regions[cur].adjacencies:
            nxt = index[name]
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def _dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


# --- template worlds stay byte-identical --------------------------------------

# sha256 of generate_world(...).model_dump_json() on the pre-Geography-2.0 base
# (integrate/wave-1 @ 1282630). Template worlds must not change.
TEMPLATE_DIGESTS = {
    (42, 8, 4): "6280897fa20cd5dfc1beeb5720f285ab897f1e5cde27a8ade33f2dcdbed76a04",
    (7, 12, 6): "75a08fe764095ec2d87bb4b8ffc640aa49278f51fa115739304394a024265e11",
    (1234, 5, 3): "fddb7bac3307d6f98134877944543c5988c39f9f92665a2d4fef638a4ce0b92d",
}


@pytest.mark.parametrize("key", sorted(TEMPLATE_DIGESTS))
def test_template_worlds_are_byte_identical_to_base(key):
    seed, regions, civs = key
    world = generate_world(seed=seed, num_regions=regions, num_civs=civs)
    assert world.geography is None
    digest = hashlib.sha256(world.model_dump_json().encode()).hexdigest()
    assert digest == TEMPLATE_DIGESTS[key]


def test_template_world_serialization_omits_geography_fields():
    world = generate_world(seed=3)
    data = world.model_dump(mode="json")
    assert "geography" not in data
    assert all("latitude_band" not in r and "geo" not in r for r in data["regions"])


def test_resolve_worldgen():
    assert resolve_worldgen(None, 8) == "template"
    assert resolve_worldgen("auto", len(REGION_TEMPLATES)) == "template"
    assert resolve_worldgen("auto", len(REGION_TEMPLATES) + 1) == "procedural"
    assert resolve_worldgen("procedural", 4) == "procedural"
    assert resolve_worldgen("template", 8) == "template"
    with pytest.raises(ValueError, match="worldgen"):
        resolve_worldgen("voronoi", 8)
    with pytest.raises(ValueError, match="region templates"):
        generate_world(seed=1, num_regions=13, num_civs=4, worldgen="template")


# --- procedural geography -------------------------------------------------------

def test_procedural_generation_is_deterministic():
    a = generate_world(seed=11, num_regions=64, num_civs=16)
    b = generate_world(seed=11, num_regions=64, num_civs=16)
    assert a.model_dump_json() == b.model_dump_json()
    c = generate_world(seed=12, num_regions=64, num_civs=16)
    assert [r.name for r in c.regions] != [r.name for r in a.regions]


@pytest.mark.parametrize("count", [13, 40, 64, 150, 200])
def test_every_region_reachable_and_graph_well_formed(count):
    world = generate_world(seed=count, num_regions=count, num_civs=min(8, count))
    assert len(world.regions) == count
    names = [r.name for r in world.regions]
    assert len(set(names)) == count
    by_name = {r.name: r for r in world.regions}
    for region in world.regions:
        assert region.adjacencies, region.name
        assert region.name not in region.adjacencies
        assert len(set(region.adjacencies)) == len(region.adjacencies)
        for other in region.adjacencies:
            assert region.name in by_name[other].adjacencies
    assert len(_bfs_reach(world)) == count


def test_terrain_and_climate_distribution_sanity():
    totals = Counter()
    for seed in (1, 2, 3, 4):
        world = generate_world(seed=seed, num_regions=150, num_civs=8)
        terrains = Counter(r.terrain for r in world.regions)
        assert set(terrains) <= set(PROCEDURAL_TERRAINS)
        assert len(terrains) >= 7, terrains
        assert max(terrains.values()) <= 0.4 * 150, terrains
        assert terrains["mountains"] >= 5
        bands = {r.latitude_band for r in world.regions}
        assert len(bands) >= 3
        for r in world.regions:
            assert r.latitude_band == latitude_band(r.geo.latitude)
            assert 0.0 <= r.geo.elevation <= 1.0 and 0.0 <= r.geo.moisture <= 1.0
            assert 10 <= r.carrying_capacity <= 100
            if r.terrain == "tundra":
                assert abs(r.geo.latitude) > 0.4 or r.geo.elevation > 0.5
            if r.terrain == "jungle":
                assert r.latitude_band <= 2
        totals.update(terrains)
    # Every procedural terrain shows up across a few large worlds.
    assert set(totals) == set(PROCEDURAL_TERRAINS), totals


def test_rivers_flow_downhill_along_adjacent_regions():
    world = generate_world(seed=5, num_regions=150, num_civs=8)
    assert world.rivers
    by_name = {r.name: r for r in world.regions}
    for idx, river in enumerate(world.rivers):
        assert len(river.path) >= 2
        for a, b in zip(river.path, river.path[1:]):
            assert b in by_name[a].adjacencies
            assert by_name[b].geo.elevation <= by_name[a].geo.elevation
        for name in river.path:
            assert by_name[name].river_mask >> idx & 1
    on_river = {n for r in world.rivers for n in r.path}
    for region in world.regions:
        assert bool(region.river_mask) == (region.name in on_river)


def test_sea_zones_are_not_regions_and_distant_coasts_are_not_neighbours():
    world = generate_world(seed=9, num_regions=150, num_civs=8)
    geo = world.geography
    assert geo is not None and geo.sea_zones
    region_names = {r.name for r in world.regions}
    by_name = {r.name: r for r in world.regions}
    zone_names = {z.name for z in geo.sea_zones}
    assert not zone_names & region_names
    for zone in geo.sea_zones:
        assert zone.kind in ("ocean", "sea", "lake")
        for name in zone.coastal_regions:
            assert by_name[name].geo.coastal
            assert zone.name in by_name[name].geo.sea_zones
    coastal = [r for r in world.regions if r.geo.coastal]
    # The template generator would make every coastal region a neighbour of
    # every other one; procedural sea lanes stay local.
    assert max(len(r.adjacencies) for r in world.regions) < len(coastal) // 2
    lanes = {tuple(sorted(lane)) for lane in geo.sea_lanes}
    spacing = MAP_SIZE / math.ceil(math.sqrt(geo.cells))
    shared_zone_lanes = 0
    for a, b in lanes:
        ra, rb = by_name[a], by_name[b]
        assert b in ra.adjacencies
        if set(ra.geo.sea_zones) & set(rb.geo.sea_zones):
            shared_zone_lanes += 1
            assert _dist(ra, rb) <= LANE_RANGE * spacing * 1.5
    assert shared_zone_lanes >= len(lanes) - 6


def test_small_explicit_procedural_world():
    world = generate_world(seed=4, num_regions=8, num_civs=3, worldgen="procedural")
    assert world.geography is not None and len(world.regions) == 8
    assert len(_bfs_reach(world)) == 8


def test_procedural_world_round_trips(tmp_path):
    world = generate_world(seed=21, num_regions=40, num_civs=6)
    path = tmp_path / "state.json"
    world.save(path)
    loaded = WorldState.load(path)
    assert loaded.model_dump_json() == world.model_dump_json()
    assert loaded.geography.sea_zones == world.geography.sea_zones
    assert loaded.regions[0].latitude_band == world.regions[0].latitude_band


def test_climate_exposure_by_band():
    assert climate_exposure(None, ClimatePhase.DROUGHT) == 1.0
    assert climate_exposure(None, ClimatePhase.COOLING) == 1.0
    assert climate_exposure(2, ClimatePhase.TEMPERATE) == 1.0
    assert climate_exposure(4, ClimatePhase.COOLING) > climate_exposure(0, ClimatePhase.COOLING)
    assert climate_exposure(1, ClimatePhase.DROUGHT) > climate_exposure(4, ClimatePhase.DROUGHT)


def test_latitude_feeds_python_ecology_tick():
    from chronicler.ecology import _tick_water
    world = generate_world(seed=6, num_regions=40, num_civs=4)
    polar = world.regions[0].model_copy(deep=True)
    equator = world.regions[0].model_copy(deep=True)
    polar.latitude_band, equator.latitude_band = 4, 0
    polar.ecology.water = equator.ecology.water = 0.6
    polar.infrastructure = equator.infrastructure = []
    _tick_water(polar, None, ClimatePhase.COOLING, world)
    _tick_water(equator, None, ClimatePhase.COOLING, world)
    assert polar.ecology.water < equator.ecology.water


# --- procedural civilizations ---------------------------------------------------

def test_civ_count_honored_beyond_templates():
    assert len(CIV_TEMPLATES) == 6
    world = generate_world(seed=42, num_regions=12, num_civs=10)
    assert len(world.civilizations) == 10
    world = generate_world(seed=42, num_regions=150, num_civs=30)
    civs = world.civilizations
    assert len(civs) == 30
    assert len({c.name for c in civs}) == 30
    assert len({c.leader.name for c in civs}) == 30
    owned = Counter(r.controller for r in world.regions if r.controller)
    for civ in civs:
        assert civ.regions and civ.capital_region == civ.regions[0]
        assert owned[civ.name] == len(civ.regions)
        assert len(civ.values) == 2 and len(set(civ.values)) == 2
        assert civ.leader_name_pool and civ.leader.throne_name == civ.leader_name_pool[0]
        assert civ.population == sum(
            r.population for r in world.regions if r.controller == civ.name
        )
    assert len(world.belief_registry) == 30


def test_starting_positions_are_spread():
    world = generate_world(seed=8, num_regions=150, num_civs=20)
    index = {r.name: i for i, r in enumerate(world.regions)}
    capitals = [index[c.capital_region] for c in world.civilizations]
    adjacency = [[index[a] for a in r.adjacencies] for r in world.regions]

    def hops(start):
        dist = {start: 0}
        queue = deque([start])
        while queue:
            cur = queue.popleft()
            for nxt in adjacency[cur]:
                if nxt not in dist:
                    dist[nxt] = dist[cur] + 1
                    queue.append(nxt)
        return dist

    def mean_nearest(points):
        nearest = []
        for k, cap in enumerate(points):
            d = hops(cap)
            nearest.append(min(d[o] for j, o in enumerate(points) if j != k))
        return min(nearest), sum(nearest) / len(nearest)

    closest, mean = mean_nearest(capitals)
    assert closest >= 2
    import random
    rng = random.Random(0)
    baseline = [mean_nearest(rng.sample(range(len(world.regions)), len(capitals)))[1]
                for _ in range(5)]
    assert mean > max(baseline)


def test_civ_request_errors_are_clear():
    with pytest.raises(ValueError, match="only 12 regions"):
        generate_world(seed=1, num_regions=12, num_civs=13)
    with pytest.raises(ValueError, match="at most 254"):
        generate_world(seed=1, num_regions=300, num_civs=255)
    with pytest.raises(ValueError, match="at least 1"):
        generate_world(seed=1, num_regions=20, num_civs=0)


def test_254_civ_world_generates():
    world = generate_world(seed=2, num_regions=260, num_civs=254)
    assert len(world.civilizations) == 254
    from chronicler.ffi_constants import check_civ_capacity
    check_civ_capacity(world)


# --- scenarios on procedural worlds --------------------------------------------

def test_scenario_on_procedural_world_keeps_generated_graph():
    from chronicler.scenario import CivOverride, RegionOverride, ScenarioConfig, apply_scenario
    world = generate_world(seed=17, num_regions=30, num_civs=4)
    before = {r.name: list(r.adjacencies) for r in world.regions}
    first = world.regions[0].name
    config = ScenarioConfig(
        name="Test",
        regions=[RegionOverride(name="Renamed Vale")],
        civilizations=[CivOverride(name="Test Realm")],
    )
    apply_scenario(world, config)
    names = {r.name for r in world.regions}
    assert "Renamed Vale" in names and first not in names
    for region in world.regions:
        assert all(a in names for a in region.adjacencies)
        old = first if region.name == "Renamed Vale" else region.name
        expected = ["Renamed Vale" if a == first else a for a in before[old]]
        assert region.adjacencies == expected
    assert any(c.name == "Test Realm" for c in world.civilizations)


# --- native runs beyond 32 regions ------------------------------------------------

@pytest.mark.parametrize("mode", ["hybrid", "off"])
def test_large_world_runs(tmp_path, mode):
    import argparse
    import json
    if mode == "hybrid":
        pytest.importorskip("chronicler_agents")
    from chronicler.main import execute_run

    args = argparse.Namespace(
        seed=5, turns=12, civs=10, regions=48,
        output=str(tmp_path / "chronicle.md"), state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=10, llm_actions=False, scenario=None,
        pause_every=None, simulate_only=True, agents=mode,
    )
    result = execute_run(args)
    assert result.total_turns == 12
    state = json.loads((tmp_path / "state.json").read_text())
    assert len(state["regions"]) == 48 and len(state["civilizations"]) >= 10
    assert state["geography"]["generator"] == "procedural"
    if mode == "hybrid":
        # Agents live in regions with ids >= 32 (impossible with u32 masks).
        assert any(r["population"] > 0 for r in state["regions"][32:])


def test_cli_worldgen_flag():
    from chronicler.main import _build_parser
    parser = _build_parser()
    assert parser.parse_args([]).worldgen is None
    assert parser.parse_args(["--worldgen", "procedural"]).worldgen == "procedural"
    with pytest.raises(SystemExit):
        parser.parse_args(["--worldgen", "hexes"])


def test_procedural_roles_are_mixed():
    world = generate_world(seed=7, num_regions=150, num_civs=8)
    roles = Counter(r.role for r in world.regions)
    assert roles["chokepoint"] >= 3 and roles["crossroads"] >= 3
    assert roles["standard"] > len(world.regions) // 2
    for region in world.regions:
        if region.role == "frontier":
            assert len(region.adjacencies) <= 2
        if region.role == "crossroads":
            assert len(region.adjacencies) >= 7
