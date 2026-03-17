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


from chronicler.models import Region, RegionEcology


def _make_region(terrain="plains", water=0.6, soil=0.8, pop=40, capacity=60, baseline=0.01):
    r = Region(
        name="TestRegion", terrain=terrain, carrying_capacity=capacity,
        population=pop, resources="fertile",
        ecology=RegionEcology(soil=soil, water=water, forest_cover=0.3),
    )
    r.disease_baseline = baseline
    r.endemic_severity = baseline
    return r


def test_disease_no_triggers_decays_toward_baseline():
    from chronicler.ecology import compute_disease_severity
    r = _make_region(baseline=0.01)
    r.endemic_severity = 0.09
    compute_disease_severity(r, world=None, pre_water=0.6)
    # Decay: 0.09 - 0.25 * (0.09 - 0.01) = 0.07
    assert abs(r.endemic_severity - 0.07) < 0.001


def test_disease_overcrowding_flare():
    from chronicler.ecology import compute_disease_severity
    r = _make_region(baseline=0.01, pop=50, capacity=60)  # 50/60 = 0.83 > 0.8
    compute_disease_severity(r, world=None, pre_water=0.6)
    assert abs(r.endemic_severity - (0.01 + 0.04)) < 0.001


def test_disease_severity_capped_at_015():
    from chronicler.ecology import compute_disease_severity
    r = _make_region(baseline=0.02, pop=50, capacity=60)
    r.endemic_severity = 0.14
    compute_disease_severity(r, world=None, pre_water=0.6)
    assert r.endemic_severity <= 0.15


def test_disease_water_quality_flare():
    from chronicler.ecology import compute_disease_severity
    r = _make_region(terrain="plains", baseline=0.01, water=0.25, pop=20, capacity=60)
    compute_disease_severity(r, world=None, pre_water=0.25)
    assert abs(r.endemic_severity - (0.01 + 0.02)) < 0.001


def test_disease_water_drop_flare():
    from chronicler.ecology import compute_disease_severity
    r = _make_region(terrain="plains", baseline=0.01, water=0.5, pop=20, capacity=60)
    r.prev_turn_water = 0.65  # Previous turn had higher water
    compute_disease_severity(r, world=None, pre_water=0.5)
    assert abs(r.endemic_severity - (0.01 + 0.02)) < 0.001


def test_disease_desert_no_seasonal_peak():
    from chronicler.ecology import compute_disease_severity
    r = _make_region(terrain="desert", baseline=0.015, pop=20, capacity=60)
    compute_disease_severity(r, world=None, pre_water=0.1, season_id=1)  # summer
    assert abs(r.endemic_severity - 0.015) < 0.001
