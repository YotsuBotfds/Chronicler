"""Tests for resource system."""
from chronicler.resources import assign_resources, get_active_trade_routes, get_self_trade_civs
from chronicler.models import Region, Resource, Disposition, Relationship


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
