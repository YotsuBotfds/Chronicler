import pytest
from chronicler.models import (
    ClimatePhase, InfrastructureType, Region, RegionEcology, WorldState,
    Infrastructure, EMPTY_SLOT, ResourceType,
)


class TestRegionEcologyModel:
    def test_defaults(self):
        eco = RegionEcology()
        assert eco.soil == 0.8
        assert eco.water == 0.6
        assert eco.forest_cover == 0.3

    def test_custom_values(self):
        eco = RegionEcology(soil=0.5, water=0.4, forest_cover=0.9)
        assert eco.soil == 0.5

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


from chronicler.models import TurnSnapshot


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


# --- Terrain tables & effective_capacity ---

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


# --- tick_ecology orchestrator and famine check ---
# M54a: tick_ecology now always uses Rust (auto-creates EcologySimulator if needed)

from chronicler.ecology import tick_ecology


class TestTickEcology:
    def _make_world(self, pop=50, soil=0.8, water=0.6, forest=0.3, terrain="plains"):
        from chronicler.models import Leader, Civilization
        r = Region(
            name="TestRegion", terrain=terrain, carrying_capacity=100,
            resources="fertile", population=pop, controller="TestCiv",
            ecology=RegionEcology(soil=soil, water=water, forest_cover=forest),
        )
        civ = Civilization(
            name="TestCiv", population=pop, military=30, economy=40,
            culture=30, stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["TestRegion"],
        )
        return WorldState(name="T", seed=42, regions=[r], civilizations=[civ])

    def test_returns_event_list(self):
        w = self._make_world()
        events = tick_ecology(w, ClimatePhase.TEMPERATE)
        assert isinstance(events, list)

    def test_uncontrolled_regions_skip_civ_effects(self):
        """Uncontrolled regions skip civ-dependent bonuses (agriculture, irrigation, etc)."""
        w = self._make_world(pop=0, soil=0.95)
        w.regions[0].controller = None
        w.regions[0].population = 0
        # With soil already near cap and pop=0, natural recovery should still apply
        # but civ-specific bonuses (agriculture) are absent — just verify no crash
        events = tick_ecology(w, ClimatePhase.TEMPERATE)
        assert isinstance(events, list)

    def test_uncontrolled_regions_still_recover(self):
        """Abandoned regions should recover naturally."""
        w = self._make_world(pop=0, soil=0.3, water=0.4, forest=0.2)
        w.regions[0].controller = None
        w.regions[0].population = 0
        old_soil = w.regions[0].ecology.soil
        tick_ecology(w, ClimatePhase.TEMPERATE)
        assert w.regions[0].ecology.soil > old_soil

    def test_ecology_clamped_after_tick(self):
        w = self._make_world(soil=0.01, terrain="desert")
        tick_ecology(w, ClimatePhase.TEMPERATE)
        assert w.regions[0].ecology.soil >= 0.05

    def test_famine_cooldown_decremented(self):
        w = self._make_world()
        w.regions[0].famine_cooldown = 3
        tick_ecology(w, ClimatePhase.TEMPERATE)
        assert w.regions[0].famine_cooldown == 2

    def test_famine_cooldown_not_decremented_for_uncontrolled_region(self):
        w = self._make_world(pop=0)
        w.regions[0].controller = None
        w.regions[0].famine_cooldown = 3
        tick_ecology(w, ClimatePhase.TEMPERATE)
        assert w.regions[0].famine_cooldown == 3


class TestFamineCheck:
    def _make_world(self, water=0.15, pop=50, grain_base=0.10, soil=0.10):
        """Build world with a GRAIN food slot so yield-based famine can trigger.

        Default: soil=0.10, water=0.15, grain_base=0.10 -> yield very low -> famine.
        """
        from chronicler.models import Leader, Civilization
        r = Region(
            name="TestRegion", terrain="plains", carrying_capacity=100,
            resources="fertile", population=pop, controller="TestCiv",
            ecology=RegionEcology(soil=soil, water=water, forest_cover=0.3),
        )
        # Give region a GRAIN food slot so yield-based famine can fire
        r.resource_types = [ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT]
        r.resource_base_yields = [grain_base, 0.0, 0.0]
        civ = Civilization(
            name="TestCiv", population=pop, military=30, economy=40,
            culture=30, stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["TestRegion"],
        )
        return WorldState(name="T", seed=42, regions=[r], civilizations=[civ])

    def test_famine_fires_when_food_yield_low(self):
        # Low soil + low water + low base -> grain yield << 0.12 -> famine
        w = self._make_world(water=0.15, soil=0.10, grain_base=0.10)
        events = tick_ecology(w, ClimatePhase.TEMPERATE)
        famine_events = [e for e in events if e.event_type == "famine"]
        assert len(famine_events) == 1
        assert "TestRegion" in famine_events[0].description

    def test_no_famine_when_food_yield_high(self):
        # High soil + high water + high base -> grain yield >> 0.12 -> no famine
        w = self._make_world(water=0.6, soil=0.8, grain_base=1.0)
        events = tick_ecology(w, ClimatePhase.TEMPERATE)
        famine_events = [e for e in events if e.event_type == "famine"]
        assert len(famine_events) == 0

    def test_no_famine_during_cooldown(self):
        w = self._make_world(water=0.15, soil=0.10, grain_base=0.10)
        w.regions[0].famine_cooldown = 3
        events = tick_ecology(w, ClimatePhase.TEMPERATE)
        famine_events = [e for e in events if e.event_type == "famine"]
        assert len(famine_events) == 0


class TestFeedbackLoops:
    def _run_turns(self, world, phase, n):
        from chronicler.ecology import tick_ecology
        all_events = []
        for _ in range(n):
            world.turn += 1
            events = tick_ecology(world, phase)
            all_events.extend(events)
        return all_events

    def test_deforestation_spiral_terminates(self):
        from chronicler.models import Leader, Civilization
        r = Region(
            name="T", terrain="forest", carrying_capacity=80,
            resources="timber", population=70, controller="TestCiv",
            ecology=RegionEcology(soil=0.7, water=0.7, forest_cover=0.9),
        )
        civ = Civilization(
            name="TestCiv", population=70, military=30, economy=40,
            culture=30, stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["T"],
        )
        w = WorldState(name="T", seed=42, regions=[r], civilizations=[civ])
        self._run_turns(w, ClimatePhase.TEMPERATE, 100)
        assert r.ecology.soil > 0.05 or r.ecology.forest_cover > 0.0

    def test_irrigation_trap_drought_spike(self):
        from chronicler.models import Leader, Civilization
        r = Region(
            name="T", terrain="plains", carrying_capacity=100,
            resources="fertile", population=80, controller="TestCiv",
            ecology=RegionEcology(soil=0.9, water=0.6, forest_cover=0.2),
        )
        r.infrastructure.append(Infrastructure(
            type=InfrastructureType.IRRIGATION, builder_civ="TestCiv",
            built_turn=0, active=True,
        ))
        civ = Civilization(
            name="TestCiv", population=80, military=30, economy=40,
            culture=30, stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["T"],
        )
        w = WorldState(name="T", seed=42, regions=[r], civilizations=[civ])
        self._run_turns(w, ClimatePhase.DROUGHT, 10)
        assert r.ecology.water < 0.3


def test_rewilding_counter_increments_on_plains(make_world):
    """M-AF1 #13: plains rewilding counter should increment when conditions are met."""
    world = make_world(2)
    region = world.regions[0]
    region.terrain = "plains"
    region.ecology.forest_cover = 0.38  # Below plains cap of 0.40, above threshold
    region.population = 2  # Below threshold of 5
    region.forest_regrowth_turns = 0

    from chronicler.ecology import _update_ecology_counters
    _update_ecology_counters(world)

    assert region.forest_regrowth_turns > 0, \
        f"Rewilding counter should have incremented, got {region.forest_regrowth_turns}"

    def test_mining_collapse_and_recovery(self):
        from chronicler.models import Leader, Civilization
        r = Region(
            name="T", terrain="mountains", carrying_capacity=40,
            resources="mineral", population=30, controller="TestCiv",
            ecology=RegionEcology(soil=0.4, water=0.8, forest_cover=0.3),
        )
        r.infrastructure.append(Infrastructure(
            type=InfrastructureType.MINES, builder_civ="TestCiv",
            built_turn=0, active=True,
        ))
        civ = Civilization(
            name="TestCiv", population=30, military=30, economy=40,
            culture=30, stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["T"], active_focus="mechanization",
        )
        w = WorldState(name="T", seed=42, regions=[r], civilizations=[civ])
        self._run_turns(w, ClimatePhase.TEMPERATE, 20)
        assert r.ecology.soil <= 0.10


# --- Season/Climate modifier tables ---

from chronicler.resources import get_season_id, get_season_step


def test_season_clock():
    assert get_season_step(0) == 0   # Spring turn 0
    assert get_season_id(0) == 0     # Spring
    assert get_season_step(2) == 2   # Spring close
    assert get_season_id(2) == 0     # Still Spring
    assert get_season_step(3) == 3   # Summer open
    assert get_season_id(3) == 1     # Summer
    assert get_season_step(11) == 11 # Winter close
    assert get_season_id(11) == 3    # Winter
    assert get_season_step(12) == 0  # Wraps to Spring
    assert get_season_id(12) == 0


def test_season_modifier_table_shape():
    from chronicler.resources import SEASON_MOD
    assert len(SEASON_MOD) == 8   # 8 resource types
    assert len(SEASON_MOD[0]) == 4  # 4 seasons


def test_climate_class_mod_shape():
    from chronicler.resources import CLIMATE_CLASS_MOD
    assert len(CLIMATE_CLASS_MOD) == 5   # 5 mechanical classes
    assert len(CLIMATE_CLASS_MOD[0]) == 4  # 4 climate phases


def test_resource_class_index():
    from chronicler.resources import resource_class_index
    from chronicler.models import ResourceType
    assert resource_class_index(ResourceType.GRAIN) == 0      # Crop
    assert resource_class_index(ResourceType.BOTANICALS) == 0  # Crop
    assert resource_class_index(ResourceType.EXOTIC) == 0      # Crop
    assert resource_class_index(ResourceType.TIMBER) == 1      # Forestry
    assert resource_class_index(ResourceType.FISH) == 2        # Marine
    assert resource_class_index(ResourceType.ORE) == 3         # Mineral
    assert resource_class_index(ResourceType.PRECIOUS) == 3    # Mineral
    assert resource_class_index(ResourceType.SALT) == 4        # Evaporite


# --- check_food_yield ---

from chronicler.ecology import check_food_yield
from chronicler.models import FOOD_TYPES


def test_famine_yield_based_triggers():
    r = Region(name="P", terrain="plains", carrying_capacity=50, resources="fertile", controller="Civ1", population=20)
    r.resource_types = [ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT]
    assert check_food_yield(r, [0.05, 0.0, 0.0], ClimatePhase.TEMPERATE) is True   # Below 0.12


def test_famine_yield_based_no_trigger():
    r = Region(name="P", terrain="plains", carrying_capacity=50, resources="fertile", controller="Civ1", population=20)
    r.resource_types = [ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT]
    assert check_food_yield(r, [0.50, 0.0, 0.0], ClimatePhase.TEMPERATE) is False  # Above 0.12


def test_subsistence_baseline_no_food_slots():
    r = Region(name="M", terrain="mountains", carrying_capacity=50, resources="mineral", controller="Civ1", population=20)
    r.resource_types = [ResourceType.ORE, ResourceType.PRECIOUS, EMPTY_SLOT]
    # Temperate: subsistence = 0.15 * 1.0 = 0.15 > 0.12 -> no famine
    assert check_food_yield(r, [0.9, 0.5, 0.0], ClimatePhase.TEMPERATE) is False


def test_subsistence_drought_triggers_famine():
    r = Region(name="M", terrain="mountains", carrying_capacity=50, resources="mineral", controller="Civ1", population=20)
    r.resource_types = [ResourceType.ORE, ResourceType.PRECIOUS, EMPTY_SLOT]
    # Drought: subsistence = 0.15 * 0.5 = 0.075 < 0.12 -> famine
    assert check_food_yield(r, [0.9, 0.5, 0.0], ClimatePhase.DROUGHT) is True


def test_multifood_uses_max():
    r = Region(name="C", terrain="coast", carrying_capacity=50, resources="maritime", controller="Civ1", population=20)
    r.resource_types = [ResourceType.FISH, ResourceType.BOTANICALS, EMPTY_SLOT]
    # Fish yield low (0.05) but Botanicals high (0.50) -> no famine
    assert check_food_yield(r, [0.05, 0.50, 0.0], ClimatePhase.TEMPERATE) is False


# --- Climate Suspension Split ---

def test_suspension_split_types():
    """resource_suspensions uses int keys, route_suspensions uses str keys."""
    from chronicler.models import Region, ResourceType
    r = Region(name="Test", terrain="forest", carrying_capacity=50, resources="timber")
    r.resource_suspensions[ResourceType.TIMBER] = 10
    r.route_suspensions["trade_route"] = 5
    assert ResourceType.TIMBER in r.resource_suspensions
    assert "trade_route" in r.route_suspensions
    assert "timber" not in r.resource_suspensions  # No string keys in resource_suspensions


# --- clamp_ecology (public helper) ---

from chronicler.ecology import clamp_ecology


class TestClampEcology:
    def test_soil_floor(self):
        r = Region(name="T", terrain="desert", carrying_capacity=30, resources="barren",
                   ecology=RegionEcology(soil=0.01, water=0.10, forest_cover=0.0))
        clamp_ecology(r)
        assert r.ecology.soil == 0.05

    def test_water_floor(self):
        r = Region(name="T", terrain="desert", carrying_capacity=30, resources="barren",
                   ecology=RegionEcology(soil=0.20, water=0.02, forest_cover=0.0))
        clamp_ecology(r)
        assert r.ecology.water == 0.10

    def test_forest_floor_is_zero(self):
        r = Region(name="T", terrain="desert", carrying_capacity=30, resources="barren",
                   ecology=RegionEcology(soil=0.20, water=0.10, forest_cover=0.0))
        clamp_ecology(r)
        assert r.ecology.forest_cover == 0.0

    def test_terrain_caps_enforced(self):
        r = Region(name="T", terrain="desert", carrying_capacity=30, resources="barren",
                   ecology=RegionEcology(soil=0.50, water=0.50, forest_cover=0.50))
        clamp_ecology(r)
        assert r.ecology.soil == 0.30
        assert r.ecology.water == 0.20
        assert r.ecology.forest_cover == 0.10
