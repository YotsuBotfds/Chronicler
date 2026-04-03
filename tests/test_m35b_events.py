import random
from chronicler.models import Region, RegionEcology, ResourceType, EMPTY_SLOT
from chronicler.world_gen import generate_world


def _make_world_with_region(terrain="plains", water=0.6, soil=0.8, pop=40, capacity=60, resource_types=None):
    world = generate_world(seed=42)
    region = world.regions[0]
    region.terrain = terrain
    region.ecology.water = water
    region.ecology.soil = soil
    region.population = pop
    region.carrying_capacity = capacity
    if resource_types is not None:
        region.resource_types = resource_types
    region.disaster_cooldowns = {}
    return world, region


def test_locust_never_fires_in_mountains():
    from chronicler.emergence import check_environmental_events
    world, region = _make_world_with_region(
        terrain="mountains",
        resource_types=[ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT],
    )
    rng = random.Random(42)
    events = check_environmental_events(world, rng)
    assert not any(e.event_type == "locust_swarm" for e in events)


def test_locust_requires_grain():
    from chronicler.emergence import check_environmental_events
    world, region = _make_world_with_region(
        terrain="plains",
        resource_types=[ResourceType.ORE, EMPTY_SLOT, EMPTY_SLOT],
    )
    rng = random.Random(42)
    events = check_environmental_events(world, rng)
    assert not any(e.event_type == "locust_swarm" for e in events)


def test_no_event_when_cooldown_active():
    from chronicler.emergence import check_environmental_events
    world, region = _make_world_with_region(
        terrain="plains",
        resource_types=[ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT],
    )
    region.disaster_cooldowns = {"earthquake": 5}
    rng = random.Random(42)
    events = check_environmental_events(world, rng)
    locust_events = [e for e in events if e.event_type == "locust_swarm" and region.name in e.description]
    assert len(locust_events) == 0


def test_flood_requires_river_mask():
    from chronicler.emergence import check_environmental_events
    world, region = _make_world_with_region(water=0.9)
    region.river_mask = 0
    rng = random.Random(42)
    events = check_environmental_events(world, rng)
    assert not any(e.event_type == "flood" for e in events)


def test_ecological_recovery_restores_yield():
    from chronicler.emergence import _check_ecological_recovery
    world, region = _make_world_with_region(
        resource_types=[ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT],
    )
    region.resource_base_yields = [1.0, 0.0, 0.0]
    region.resource_effective_yields = [0.5, 0.0, 0.0]
    rng = random.Random(42)
    # Try many times to ensure at least one fires (2% probability)
    for _ in range(200):
        if _check_ecological_recovery(region, world, rng):
            break
    assert region.resource_effective_yields[0] <= region.resource_base_yields[0]
    assert region.resource_effective_yields[0] > 0.5


def test_ecological_recovery_never_exceeds_base():
    from chronicler.emergence import _check_ecological_recovery
    world, region = _make_world_with_region(
        resource_types=[ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT],
    )
    region.resource_base_yields = [1.0, 0.0, 0.0]
    region.resource_effective_yields = [0.95, 0.0, 0.0]
    # Not eligible (0.95 >= 0.8 * 1.0), so recovery should not fire
    rng = random.Random(42)
    result = _check_ecological_recovery(region, world, rng)
    assert result is None
    assert region.resource_effective_yields[0] == 0.95
