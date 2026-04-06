"""M35b regression tests: verify existing behavior is not broken."""
from chronicler.world_gen import generate_world
from chronicler.models import ClimatePhase
from chronicler.ecology import tick_ecology


def test_existing_ecology_works_with_disease_fields():
    world = generate_world(seed=42)
    for _ in range(5):
        tick_ecology(world, ClimatePhase.TEMPERATE)
    for r in world.regions:
        assert 0.0 <= r.ecology.soil <= 1.0
        assert 0.0 <= r.ecology.water <= 1.0
        # Allow f32 precision loss: severity round-trips through Rust f32
        assert r.endemic_severity >= r.disease_baseline - 1e-6
        assert r.endemic_severity <= 0.15 + 1e-6


def test_effective_yields_ceiling():
    world = generate_world(seed=42)
    for _ in range(10):
        tick_ecology(world, ClimatePhase.TEMPERATE)
    for r in world.regions:
        for slot in range(3):
            assert r.resource_effective_yields[slot] <= r.resource_base_yields[slot] + 0.001


def test_prev_turn_water_updated():
    world = generate_world(seed=42)
    # Before first tick, prev_turn_water is -1.0 (sentinel)
    assert world.regions[0].prev_turn_water == -1.0
    tick_ecology(world, ClimatePhase.TEMPERATE)
    # After first tick, prev_turn_water should be set to post-tick water
    for r in world.regions:
        assert r.prev_turn_water >= 0.0
        assert abs(r.prev_turn_water - r.ecology.water) < 0.001
