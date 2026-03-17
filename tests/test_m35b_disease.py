from chronicler.models import Region
from chronicler.world_gen import generate_world


def test_region_has_disease_fields():
    r = Region(name="Test", terrain="plains", carrying_capacity=60, resources="fertile")
    assert r.disease_baseline == 0.01
    assert r.endemic_severity == 0.01
    assert r.soil_pressure_streak == 0
    assert r.overextraction_streaks == {}
    assert r.resource_effective_yields == [0.0, 0.0, 0.0]
    assert r.capacity_modifier == 1.0
    assert r.prev_turn_water == -1.0


def test_disease_baseline_assigned_at_worldgen():
    world = generate_world(seed=42)
    for region in world.regions:
        assert region.disease_baseline > 0.0, f"{region.name} has no disease baseline"
        assert region.endemic_severity == region.disease_baseline
        if region.terrain == "desert":
            assert region.disease_baseline == 0.015
        elif region.ecology.water > 0.6 and region.ecology.soil > 0.5:
            assert region.disease_baseline == 0.02
        else:
            assert region.disease_baseline == 0.01


def test_effective_yields_initialized_at_worldgen():
    world = generate_world(seed=42)
    for region in world.regions:
        assert region.resource_effective_yields == region.resource_base_yields
