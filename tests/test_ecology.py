import pytest
from chronicler.models import RegionEcology, Region


class TestRegionEcologyModel:
    def test_defaults(self):
        eco = RegionEcology()
        assert eco.soil == 0.8
        assert eco.water == 0.6
        assert eco.forest_cover == 0.3

    def test_custom_values(self):
        eco = RegionEcology(soil=0.5, water=0.4, forest_cover=0.9)
        assert eco.soil == 0.5

    def test_soil_clamped_to_01(self):
        with pytest.raises(Exception):
            RegionEcology(soil=1.5)
        with pytest.raises(Exception):
            RegionEcology(soil=-0.1)

    def test_water_clamped_to_01(self):
        with pytest.raises(Exception):
            RegionEcology(water=1.5)

    def test_forest_cover_clamped_to_01(self):
        with pytest.raises(Exception):
            RegionEcology(forest_cover=-0.1)


class TestRegionEcologyField:
    def test_region_has_ecology(self):
        r = Region(name="T", terrain="plains", carrying_capacity=60, resources="fertile")
        assert isinstance(r.ecology, RegionEcology)
        assert r.ecology.soil == 0.8

    def test_region_has_low_forest_turns(self):
        r = Region(name="T", terrain="plains", carrying_capacity=60, resources="fertile")
        assert r.low_forest_turns == 0

    def test_region_has_forest_regrowth_turns(self):
        r = Region(name="T", terrain="plains", carrying_capacity=60, resources="fertile")
        assert r.forest_regrowth_turns == 0


from chronicler.models import TurnSnapshot, WorldState


class TestTurnSnapshotEcology:
    def test_snapshot_has_ecology_field(self):
        snap = TurnSnapshot(turn=0, civ_stats={}, region_control={}, relationships={})
        assert snap.ecology == {}

    def test_snapshot_ecology_accepts_dict(self):
        snap = TurnSnapshot(
            turn=0, civ_stats={}, region_control={}, relationships={},
            ecology={"Plains": {"soil": 0.9, "water": 0.6, "forest_cover": 0.2}},
        )
        assert snap.ecology["Plains"]["soil"] == 0.9


class TestTerrainTransitionDefaults:
    def test_deforestation_rule_uses_low_forest(self):
        w = WorldState(name="T", seed=42)
        deforest = w.terrain_transition_rules[0]
        assert deforest.from_terrain == "forest"
        assert deforest.to_terrain == "plains"
        assert deforest.condition == "low_forest"

    def test_rewilding_rule_uses_forest_regrowth(self):
        w = WorldState(name="T", seed=42)
        rewild = w.terrain_transition_rules[1]
        assert rewild.from_terrain == "plains"
        assert rewild.to_terrain == "forest"
        assert rewild.condition == "forest_regrowth"


from chronicler.tuning import KNOWN_OVERRIDES


class TestEcologyTuningKeys:
    def test_old_fertility_keys_removed(self):
        assert "fertility.degradation_rate" not in KNOWN_OVERRIDES
        assert "fertility.recovery_rate" not in KNOWN_OVERRIDES
        assert "fertility.famine_threshold" not in KNOWN_OVERRIDES

    def test_ecology_keys_registered(self):
        expected = [
            "ecology.soil_degradation_rate",
            "ecology.soil_recovery_rate",
            "ecology.mine_soil_degradation_rate",
            "ecology.water_drought_rate",
            "ecology.water_recovery_rate",
            "ecology.forest_clearing_rate",
            "ecology.forest_regrowth_rate",
            "ecology.cooling_forest_damage_rate",
            "ecology.irrigation_water_bonus",
            "ecology.irrigation_drought_multiplier",
            "ecology.agriculture_soil_bonus",
            "ecology.mechanization_mine_multiplier",
            "ecology.famine_water_threshold",
        ]
        for key in expected:
            assert key in KNOWN_OVERRIDES, f"Missing tuning key: {key}"


# --- Task 4: Terrain tables & effective_capacity ---

from chronicler.ecology import effective_capacity, TERRAIN_ECOLOGY_DEFAULTS, TERRAIN_ECOLOGY_CAPS


class TestTerrainDefaults:
    def test_plains_defaults(self):
        eco = TERRAIN_ECOLOGY_DEFAULTS["plains"]
        assert eco.soil == 0.9
        assert eco.water == 0.6
        assert eco.forest_cover == 0.2

    def test_forest_defaults(self):
        eco = TERRAIN_ECOLOGY_DEFAULTS["forest"]
        assert eco.forest_cover == 0.9

    def test_desert_defaults(self):
        eco = TERRAIN_ECOLOGY_DEFAULTS["desert"]
        assert eco.soil == 0.2
        assert eco.water == 0.1
        assert eco.forest_cover == 0.05

    def test_all_six_terrains_present(self):
        assert set(TERRAIN_ECOLOGY_DEFAULTS.keys()) == {"plains", "forest", "mountains", "coast", "desert", "tundra"}


class TestTerrainCaps:
    def test_desert_caps(self):
        caps = TERRAIN_ECOLOGY_CAPS["desert"]
        assert caps["soil"] == 0.30
        assert caps["water"] == 0.20
        assert caps["forest_cover"] == 0.10

    def test_all_six_terrains_present(self):
        assert set(TERRAIN_ECOLOGY_CAPS.keys()) == {"plains", "forest", "mountains", "coast", "desert", "tundra"}


class TestEffectiveCapacity:
    def _region(self, soil=0.8, water=0.6, forest_cover=0.3, capacity=100):
        return Region(
            name="T", terrain="plains", carrying_capacity=capacity,
            resources="fertile",
            ecology=RegionEcology(soil=soil, water=water, forest_cover=forest_cover),
        )

    def test_full_soil_full_water(self):
        r = self._region(soil=1.0, water=1.0)
        assert effective_capacity(r) == 100

    def test_half_soil_full_water(self):
        r = self._region(soil=0.5, water=1.0)
        assert effective_capacity(r) == 50

    def test_full_soil_water_at_threshold(self):
        r = self._region(soil=1.0, water=0.5)
        assert effective_capacity(r) == 100

    def test_full_soil_water_below_threshold(self):
        r = self._region(soil=1.0, water=0.25)
        assert effective_capacity(r) == 50

    def test_floor_of_one(self):
        r = self._region(soil=0.05, water=0.10, capacity=1)
        assert effective_capacity(r) >= 1

    def test_combined_soil_and_water(self):
        r = self._region(soil=0.5, water=0.25)
        assert effective_capacity(r) == 25
