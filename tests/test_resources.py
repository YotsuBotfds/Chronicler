"""Tests for resource system."""
from chronicler.resources import (
    assign_resources,
    clear_active_trade_routes_snapshot,
    get_active_trade_routes,
    get_self_trade_civs,
    set_active_trade_routes_snapshot,
)
from chronicler.models import Region, Resource, Disposition, Relationship


# --- M34: ResourceType enum and Region extension tests ---

from chronicler.models import ResourceType

def test_resource_type_enum_values():
    assert ResourceType.GRAIN == 0
    assert ResourceType.TIMBER == 1
    assert ResourceType.BOTANICALS == 2
    assert ResourceType.FISH == 3
    assert ResourceType.SALT == 4
    assert ResourceType.ORE == 5
    assert ResourceType.PRECIOUS == 6
    assert ResourceType.EXOTIC == 7
    assert len(ResourceType) == 8


def test_region_resource_fields_defaults():
    from chronicler.models import Region, EMPTY_SLOT
    r = Region(name="Test", terrain="plains", carrying_capacity=50, resources="fertile")
    assert r.resource_types == [EMPTY_SLOT, EMPTY_SLOT, EMPTY_SLOT]
    assert r.resource_base_yields == [0.0, 0.0, 0.0]
    assert r.resource_reserves == [1.0, 1.0, 1.0]
    assert r.route_suspensions == {}
    assert r.resource_suspensions == {}


def test_resource_enum_values():
    assert Resource.GRAIN.value == "grain"
    assert Resource.RARE_MINERALS.value == "rare_minerals"


def test_assign_resources_deterministic():
    regions = [Region(name="Plains1", terrain="plains", carrying_capacity=50, resources="fertile")]
    assign_resources(regions, seed=42)
    result1 = list(regions[0].specialized_resources)
    regions[0].specialized_resources = []
    assign_resources(regions, seed=42)
    assert regions[0].specialized_resources == result1


def test_assign_resources_minimum_one():
    regions = [Region(name=f"R{i}", terrain="desert", carrying_capacity=50,
                      resources="barren") for i in range(20)]
    assign_resources(regions, seed=0)
    for r in regions:
        assert len(r.specialized_resources) >= 1


def test_assign_resources_preserves_explicit():
    regions = [Region(name="Authored", terrain="plains", carrying_capacity=50,
                      resources="fertile", specialized_resources=[Resource.IRON])]
    assign_resources(regions, seed=42)
    assert regions[0].specialized_resources == [Resource.IRON]


def test_assign_resources_plains_likely_grain():
    regions = [Region(name=f"P{i}", terrain="plains", carrying_capacity=50,
                      resources="fertile") for i in range(50)]
    assign_resources(regions, seed=42)
    grain_count = sum(1 for r in regions if Resource.GRAIN in r.specialized_resources)
    assert grain_count > 25


def test_get_active_trade_routes(sample_world):
    civ_a = sample_world.civilizations[0]
    civ_b = sample_world.civilizations[1]
    r1 = sample_world.regions[0]
    r2 = sample_world.regions[1]
    r1.controller = civ_a.name
    r2.controller = civ_b.name
    r1.adjacencies = [r2.name]
    r2.adjacencies = [r1.name]
    sample_world.relationships[civ_a.name][civ_b.name].disposition = Disposition.NEUTRAL
    sample_world.relationships[civ_b.name][civ_a.name].disposition = Disposition.NEUTRAL
    routes = get_active_trade_routes(sample_world)
    assert (civ_a.name, civ_b.name) in routes or (civ_b.name, civ_a.name) in routes
    assert routes == sorted(routes)


def test_no_trade_route_when_embargoed(sample_world):
    civ_a = sample_world.civilizations[0]
    civ_b = sample_world.civilizations[1]
    r1 = sample_world.regions[0]
    r2 = sample_world.regions[1]
    r1.controller = civ_a.name
    r2.controller = civ_b.name
    r1.adjacencies = [r2.name]
    r2.adjacencies = [r1.name]
    sample_world.relationships[civ_a.name][civ_b.name].disposition = Disposition.NEUTRAL
    sample_world.relationships[civ_b.name][civ_a.name].disposition = Disposition.NEUTRAL
    sample_world.embargoes = [(civ_a.name, civ_b.name)]
    routes = get_active_trade_routes(sample_world)
    assert len(routes) == 0


def test_get_self_trade_civs(sample_world):
    r1 = sample_world.regions[0]
    r2 = sample_world.regions[2]  # Both controlled by Kethani
    r1.adjacencies = [r2.name]
    r2.adjacencies = [r1.name]
    self_traders = get_self_trade_civs(sample_world)
    assert sample_world.civilizations[0].name in self_traders


def test_get_active_trade_routes_uses_turn_snapshot_when_present(sample_world):
    civ_a = sample_world.civilizations[0]
    civ_b = sample_world.civilizations[1]
    snapshot_routes = [(civ_a.name, civ_b.name)]
    set_active_trade_routes_snapshot(sample_world, snapshot_routes)
    sample_world.relationships[civ_a.name][civ_b.name].disposition = Disposition.HOSTILE
    sample_world.relationships[civ_b.name][civ_a.name].disposition = Disposition.HOSTILE
    assert get_active_trade_routes(sample_world) == snapshot_routes
    clear_active_trade_routes_snapshot(sample_world)


def test_get_active_trade_routes_ignores_stale_snapshot(sample_world):
    civ_a = sample_world.civilizations[0]
    civ_b = sample_world.civilizations[1]
    r1 = sample_world.regions[0]
    r2 = sample_world.regions[1]
    r1.controller = civ_a.name
    r2.controller = civ_b.name
    r1.adjacencies = [r2.name]
    r2.adjacencies = [r1.name]
    sample_world.relationships[civ_a.name][civ_b.name].disposition = Disposition.NEUTRAL
    sample_world.relationships[civ_b.name][civ_a.name].disposition = Disposition.NEUTRAL

    set_active_trade_routes_snapshot(sample_world, [])
    sample_world.turn += 1

    routes = get_active_trade_routes(sample_world)

    assert (civ_a.name, civ_b.name) in routes or (civ_b.name, civ_a.name) in routes
    clear_active_trade_routes_snapshot(sample_world)


# --- M34: Task 2 — assign_resource_types tests ---

from chronicler.models import EMPTY_SLOT
from chronicler.resources import assign_resource_types


def test_assign_primary_deterministic():
    """Every terrain gets its locked primary resource."""
    terrain_expected = {
        "plains": ResourceType.GRAIN,
        "forest": ResourceType.TIMBER,
        "mountains": ResourceType.ORE,
        "coast": ResourceType.FISH,
        "desert": ResourceType.EXOTIC,
        "tundra": ResourceType.EXOTIC,
        "river": ResourceType.GRAIN,
        "hills": ResourceType.GRAIN,
    }
    for terrain, expected in terrain_expected.items():
        r = Region(name=f"Test_{terrain}", terrain=terrain, carrying_capacity=50, resources="fertile")
        assign_resource_types([r], seed=42)
        assert r.resource_types[0] == expected, f"{terrain} primary should be {expected.name}"


def test_assign_slot1_never_empty():
    """Slot 1 is always filled for any terrain, any seed."""
    for seed in range(100):
        for terrain in ("plains", "forest", "mountains", "coast", "desert", "tundra", "river", "hills"):
            r = Region(name=f"R_{terrain}_{seed}", terrain=terrain, carrying_capacity=50, resources="fertile")
            assign_resource_types([r], seed=seed)
            assert r.resource_types[0] != EMPTY_SLOT, f"Slot 1 empty for {terrain} seed={seed}"


def test_assign_base_yields_variance():
    """Base yields have ±20% variance around RESOURCE_BASE."""
    regions = []
    for i in range(200):
        r = Region(name=f"Plains_{i}", terrain="plains", carrying_capacity=50, resources="fertile")
        regions.append(r)
    assign_resource_types(regions, seed=12345)
    yields = [r.resource_base_yields[0] for r in regions]
    assert min(yields) >= 0.8 * 1.0  # RESOURCE_BASE * 0.8
    assert max(yields) <= 1.2 * 1.0  # RESOURCE_BASE * 1.2
    assert min(yields) < max(yields)  # Not all identical


def test_assign_mineral_reserves_one():
    """All resources start with reserves=1.0."""
    r = Region(name="Peaks", terrain="mountains", carrying_capacity=50, resources="mineral")
    assign_resource_types([r], seed=42)
    assert all(res == 1.0 for res in r.resource_reserves)


def test_assign_idempotent():
    """Calling assign on already-assigned regions doesn't overwrite."""
    r = Region(name="Test", terrain="plains", carrying_capacity=50, resources="fertile")
    assign_resource_types([r], seed=42)
    original = r.resource_types[:]
    assign_resource_types([r], seed=99)  # Different seed
    assert r.resource_types == original


# --- M34: Task 3 — Legacy Bridge tests ---

from chronicler.resources import populate_legacy_resources


def test_legacy_bridge_populates_specialized_resources():
    r = Region(name="Test", terrain="plains", carrying_capacity=50, resources="fertile")
    assign_resource_types([r], seed=42)
    populate_legacy_resources([r])
    assert len(r.specialized_resources) > 0
    assert Resource.GRAIN in r.specialized_resources
