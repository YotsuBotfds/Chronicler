import pytest
from chronicler.models import (
    ClimatePhase, InfrastructureType, Region, RegionEcology, WorldState,
    Infrastructure,
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


# --- Task 5: _pressure_multiplier and _tick_soil ---

from chronicler.ecology import _tick_soil, _pressure_multiplier


class TestPressureMultiplier:
    def _region(self, pop, soil=0.8, water=0.6, capacity=100):
        return Region(
            name="T", terrain="plains", carrying_capacity=capacity,
            resources="fertile", population=pop,
            ecology=RegionEcology(soil=soil, water=water, forest_cover=0.3),
        )

    def test_at_capacity(self):
        r = self._region(pop=80)
        mult = _pressure_multiplier(r)
        assert mult == pytest.approx(0.1, abs=0.05)

    def test_half_capacity(self):
        r = self._region(pop=40)
        mult = _pressure_multiplier(r)
        assert mult == pytest.approx(0.5, abs=0.05)

    def test_abandoned(self):
        r = self._region(pop=0)
        mult = _pressure_multiplier(r)
        assert mult == pytest.approx(1.0)


class TestTickSoil:
    def _setup(self, pop=90, soil=0.8, focus=None, has_mine=False):
        from chronicler.models import Infrastructure, Leader, Civilization
        r = Region(
            name="T", terrain="plains", carrying_capacity=100,
            resources="fertile", population=pop, controller="TestCiv",
            ecology=RegionEcology(soil=soil, water=0.6, forest_cover=0.3),
        )
        if has_mine:
            r.infrastructure.append(Infrastructure(
                type=InfrastructureType.MINES, builder_civ="TestCiv",
                built_turn=0, active=True,
            ))
        civ = Civilization(
            name="TestCiv", population=pop, military=30, economy=40,
            culture=30, stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["T"],
        )
        if focus:
            civ.active_focus = focus
        w = WorldState(name="T", seed=42, regions=[r], civilizations=[civ])
        return r, civ, w

    def test_overpop_degrades_soil(self):
        r, civ, w = self._setup(pop=90, soil=0.8)
        old_soil = r.ecology.soil
        _tick_soil(r, civ, ClimatePhase.TEMPERATE, w)
        assert r.ecology.soil < old_soil

    def test_underpop_recovers_soil(self):
        r, civ, w = self._setup(pop=10, soil=0.4)
        old_soil = r.ecology.soil
        _tick_soil(r, civ, ClimatePhase.TEMPERATE, w)
        assert r.ecology.soil > old_soil

    def test_agriculture_bonus_recovery(self):
        r_agri, civ_agri, w_agri = self._setup(pop=10, soil=0.4, focus="agriculture")
        r_none, civ_none, w_none = self._setup(pop=10, soil=0.4)
        _tick_soil(r_agri, civ_agri, ClimatePhase.TEMPERATE, w_agri)
        _tick_soil(r_none, civ_none, ClimatePhase.TEMPERATE, w_none)
        assert r_agri.ecology.soil > r_none.ecology.soil

    def test_mine_degrades_soil(self):
        r, civ, w = self._setup(pop=60, soil=0.8, has_mine=True)
        old_soil = r.ecology.soil
        _tick_soil(r, civ, ClimatePhase.TEMPERATE, w)
        assert r.ecology.soil < old_soil

    def test_metallurgy_halves_mine_degradation(self):
        r_met, civ_met, w_met = self._setup(pop=10, soil=0.8, focus="metallurgy", has_mine=True)
        r_none, civ_none, w_none = self._setup(pop=10, soil=0.8, has_mine=True)
        _tick_soil(r_met, civ_met, ClimatePhase.TEMPERATE, w_met)
        _tick_soil(r_none, civ_none, ClimatePhase.TEMPERATE, w_none)
        assert r_met.ecology.soil > r_none.ecology.soil

    def test_mechanization_doubles_mine_degradation(self):
        r_mech, civ_mech, w_mech = self._setup(pop=10, soil=0.8, focus="mechanization", has_mine=True)
        r_none, civ_none, w_none = self._setup(pop=10, soil=0.8, has_mine=True)
        _tick_soil(r_mech, civ_mech, ClimatePhase.TEMPERATE, w_mech)
        _tick_soil(r_none, civ_none, ClimatePhase.TEMPERATE, w_none)
        assert r_mech.ecology.soil < r_none.ecology.soil


# --- Task 6: _tick_water ---

from chronicler.ecology import _tick_water


class TestTickWater:
    def _setup(self, pop=50, water=0.6, has_irrigation=False):
        from chronicler.models import Infrastructure, Leader, Civilization
        r = Region(
            name="T", terrain="plains", carrying_capacity=100,
            resources="fertile", population=pop, controller="TestCiv",
            ecology=RegionEcology(soil=0.8, water=water, forest_cover=0.3),
        )
        if has_irrigation:
            r.infrastructure.append(Infrastructure(
                type=InfrastructureType.IRRIGATION, builder_civ="TestCiv",
                built_turn=0, active=True,
            ))
        civ = Civilization(
            name="TestCiv", population=pop, military=30, economy=40,
            culture=30, stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["T"],
        )
        w = WorldState(name="T", seed=42, regions=[r], civilizations=[civ])
        return r, civ, w

    def test_drought_degrades_water(self):
        r, civ, w = self._setup(water=0.6)
        old = r.ecology.water
        _tick_water(r, civ, ClimatePhase.DROUGHT, w)
        assert r.ecology.water < old

    def test_irrigation_amplifies_drought(self):
        r_irr, civ_irr, w_irr = self._setup(water=0.6, has_irrigation=True)
        r_dry, civ_dry, w_dry = self._setup(water=0.6)
        _tick_water(r_irr, civ_irr, ClimatePhase.DROUGHT, w_irr)
        _tick_water(r_dry, civ_dry, ClimatePhase.DROUGHT, w_dry)
        assert r_irr.ecology.water < r_dry.ecology.water

    def test_temperate_recovers_water(self):
        r, civ, w = self._setup(water=0.4)
        old = r.ecology.water
        _tick_water(r, civ, ClimatePhase.TEMPERATE, w)
        assert r.ecology.water > old

    def test_irrigation_bonus_recovery(self):
        r_irr, civ_irr, w_irr = self._setup(water=0.4, has_irrigation=True)
        r_dry, civ_dry, w_dry = self._setup(water=0.4)
        _tick_water(r_irr, civ_irr, ClimatePhase.TEMPERATE, w_irr)
        _tick_water(r_dry, civ_dry, ClimatePhase.TEMPERATE, w_dry)
        assert r_irr.ecology.water > r_dry.ecology.water

    def test_cooling_degrades_water(self):
        r, civ, w = self._setup(water=0.6)
        old = r.ecology.water
        _tick_water(r, civ, ClimatePhase.COOLING, w)
        assert r.ecology.water < old

    def test_warming_tundra_melt_bonus(self):
        from chronicler.models import Leader, Civilization
        r = Region(
            name="T", terrain="tundra", carrying_capacity=20,
            resources="barren", population=5, controller="TestCiv",
            ecology=RegionEcology(soil=0.15, water=0.4, forest_cover=0.1),
        )
        civ = Civilization(
            name="TestCiv", population=5, military=30, economy=40,
            culture=30, stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["T"],
        )
        w = WorldState(name="T", seed=42, regions=[r], civilizations=[civ])
        old = r.ecology.water
        _tick_water(r, civ, ClimatePhase.WARMING, w)
        assert r.ecology.water > old

    def test_warming_non_tundra_no_effect(self):
        r, civ, w = self._setup(water=0.6)
        old = r.ecology.water
        _tick_water(r, civ, ClimatePhase.WARMING, w)
        assert r.ecology.water == old


# --- Task 7: _tick_forest ---

from chronicler.ecology import _tick_forest


class TestTickForest:
    def _setup(self, pop=60, forest=0.5, water=0.6, capacity=100):
        from chronicler.models import Leader, Civilization
        r = Region(
            name="T", terrain="forest", carrying_capacity=capacity,
            resources="timber", population=pop, controller="TestCiv",
            ecology=RegionEcology(soil=0.7, water=water, forest_cover=forest),
        )
        civ = Civilization(
            name="TestCiv", population=pop, military=30, economy=40,
            culture=30, stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["T"],
        )
        w = WorldState(name="T", seed=42, regions=[r], civilizations=[civ])
        return r, civ, w

    def test_high_pop_clears_forest(self):
        r, civ, w = self._setup(pop=60, forest=0.5)
        old = r.ecology.forest_cover
        _tick_forest(r, civ, ClimatePhase.TEMPERATE, w)
        assert r.ecology.forest_cover < old

    def test_low_pop_regrows_forest(self):
        r, civ, w = self._setup(pop=10, forest=0.5)
        old = r.ecology.forest_cover
        _tick_forest(r, civ, ClimatePhase.TEMPERATE, w)
        assert r.ecology.forest_cover > old

    def test_low_water_blocks_regrowth(self):
        r, civ, w = self._setup(pop=10, forest=0.5, water=0.2)
        old = r.ecology.forest_cover
        _tick_forest(r, civ, ClimatePhase.TEMPERATE, w)
        assert r.ecology.forest_cover == old

    def test_cooling_damages_forest(self):
        r, civ, w = self._setup(pop=10, forest=0.5)
        r2, civ2, w2 = self._setup(pop=10, forest=0.5)
        _tick_forest(r, civ, ClimatePhase.COOLING, w)
        _tick_forest(r2, civ2, ClimatePhase.TEMPERATE, w2)
        assert r.ecology.forest_cover < r2.ecology.forest_cover


# --- Task 8: _apply_cross_effects and _clamp_ecology ---

from chronicler.ecology import _apply_cross_effects, _clamp_ecology


class TestCrossEffects:
    def test_forest_provides_soil_bonus(self):
        r = Region(name="T", terrain="forest", carrying_capacity=100, resources="timber", population=0,
                   ecology=RegionEcology(soil=0.5, water=0.6, forest_cover=0.6))
        old_soil = r.ecology.soil
        _apply_cross_effects(r)
        assert r.ecology.soil > old_soil

    def test_low_forest_no_soil_bonus(self):
        r = Region(name="T", terrain="plains", carrying_capacity=100, resources="fertile", population=0,
                   ecology=RegionEcology(soil=0.5, water=0.6, forest_cover=0.3))
        old_soil = r.ecology.soil
        _apply_cross_effects(r)
        assert r.ecology.soil == old_soil


class TestClampEcology:
    def test_soil_floor(self):
        r = Region(name="T", terrain="desert", carrying_capacity=30, resources="barren",
                   ecology=RegionEcology(soil=0.01, water=0.10, forest_cover=0.0))
        _clamp_ecology(r)
        assert r.ecology.soil == 0.05

    def test_water_floor(self):
        r = Region(name="T", terrain="desert", carrying_capacity=30, resources="barren",
                   ecology=RegionEcology(soil=0.20, water=0.02, forest_cover=0.0))
        _clamp_ecology(r)
        assert r.ecology.water == 0.10

    def test_forest_floor_is_zero(self):
        r = Region(name="T", terrain="desert", carrying_capacity=30, resources="barren",
                   ecology=RegionEcology(soil=0.20, water=0.10, forest_cover=0.0))
        _clamp_ecology(r)
        assert r.ecology.forest_cover == 0.0

    def test_terrain_caps_enforced(self):
        r = Region(name="T", terrain="desert", carrying_capacity=30, resources="barren",
                   ecology=RegionEcology(soil=0.50, water=0.50, forest_cover=0.50))
        _clamp_ecology(r)
        assert r.ecology.soil == 0.30
        assert r.ecology.water == 0.20
        assert r.ecology.forest_cover == 0.10


# --- Task 9: tick_ecology orchestrator and famine check ---

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


# --- Task 4 (M34): Season/Climate modifier tables ---

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


# --- Task 5 (M34): compute_resource_yields ---

from chronicler.ecology import compute_resource_yields
from chronicler.models import EMPTY_SLOT, ResourceType


def test_yield_crop_autumn_temperate():
    """Crop: base × season × climate × ecology_mod (soil×water)."""
    r = Region(name="P", terrain="plains", carrying_capacity=50, resources="fertile")
    r.resource_types = [ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT]
    r.resource_base_yields = [1.0, 0.0, 0.0]
    r.resource_reserves = [1.0, 1.0, 1.0]
    r.ecology.soil = 0.8
    r.ecology.water = 0.7
    yields = compute_resource_yields(r, season_id=2, climate_phase=ClimatePhase.TEMPERATE, worker_count=0)
    # 1.0 × 1.5 (autumn grain) × 1.0 (temperate crop) × (0.8×0.7=0.56) × 1.0
    expected = 1.0 * 1.5 * 1.0 * 0.56 * 1.0
    assert abs(yields[0] - expected) < 0.001


def test_yield_timber_uses_forest_cover():
    r = Region(name="F", terrain="forest", carrying_capacity=50, resources="timber")
    r.resource_types = [ResourceType.TIMBER, EMPTY_SLOT, EMPTY_SLOT]
    r.resource_base_yields = [1.0, 0.0, 0.0]
    r.resource_reserves = [1.0, 1.0, 1.0]
    r.ecology.forest_cover = 0.4
    yields = compute_resource_yields(r, season_id=2, climate_phase=ClimatePhase.TEMPERATE, worker_count=0)
    # 1.0 × 1.2 (autumn timber) × 1.0 (temperate forestry) × 0.4 (forest_cover) × 1.0
    expected = 1.0 * 1.2 * 1.0 * 0.4 * 1.0
    assert abs(yields[0] - expected) < 0.001


def test_yield_fish_ecology_mod_one():
    r = Region(name="C", terrain="coast", carrying_capacity=50, resources="maritime")
    r.resource_types = [ResourceType.FISH, EMPTY_SLOT, EMPTY_SLOT]
    r.resource_base_yields = [1.0, 0.0, 0.0]
    r.resource_reserves = [1.0, 1.0, 1.0]
    r.ecology.soil = 0.1  # Bad soil shouldn't affect fish
    r.ecology.water = 0.1
    yields = compute_resource_yields(r, season_id=0, climate_phase=ClimatePhase.TEMPERATE, worker_count=0)
    # 1.0 × 1.0 (spring fish) × 1.0 × 1.0 (marine ecology_mod) × 1.0
    assert abs(yields[0] - 1.0) < 0.001


def test_yield_ore_uses_reserve_ramp():
    r = Region(name="M", terrain="mountains", carrying_capacity=60, resources="mineral")
    r.resource_types = [ResourceType.ORE, EMPTY_SLOT, EMPTY_SLOT]
    r.resource_base_yields = [1.0, 0.0, 0.0]
    r.resource_reserves = [0.10, 1.0, 1.0]  # Low reserves
    yields = compute_resource_yields(r, season_id=0, climate_phase=ClimatePhase.TEMPERATE, worker_count=0)
    # reserve_ramp = min(1.0, 0.10/0.25) = 0.4
    # 1.0 × 0.9 (spring ore) × 1.0 (mineral climate) × 1.0 (mineral ecology) × 0.4
    expected = 1.0 * 0.9 * 1.0 * 1.0 * 0.4
    assert abs(yields[0] - expected) < 0.001


def test_yield_empty_slot_zero():
    r = Region(name="T", terrain="tundra", carrying_capacity=20, resources="barren")
    r.resource_types = [ResourceType.EXOTIC, EMPTY_SLOT, EMPTY_SLOT]
    r.resource_base_yields = [1.0, 0.0, 0.0]
    r.resource_reserves = [1.0, 1.0, 1.0]
    yields = compute_resource_yields(r, season_id=0, climate_phase=ClimatePhase.TEMPERATE, worker_count=0)
    assert yields[1] == 0.0
    assert yields[2] == 0.0


def test_yield_suspension_zeroes():
    """Suspended resource yields 0."""
    r = Region(name="F", terrain="forest", carrying_capacity=50, resources="timber")
    r.resource_types = [ResourceType.TIMBER, EMPTY_SLOT, EMPTY_SLOT]
    r.resource_base_yields = [1.0, 0.0, 0.0]
    r.resource_reserves = [1.0, 1.0, 1.0]
    r.ecology.forest_cover = 0.9
    r.resource_suspensions = {int(ResourceType.TIMBER): 5}
    yields = compute_resource_yields(r, season_id=2, climate_phase=ClimatePhase.TEMPERATE, worker_count=0)
    assert yields[0] == 0.0


def test_salt_exempt_from_depletion():
    r = Region(name="C", terrain="coast", carrying_capacity=50, resources="maritime")
    r.resource_types = [ResourceType.FISH, ResourceType.SALT, EMPTY_SLOT]
    r.resource_base_yields = [1.0, 1.0, 0.0]
    r.resource_reserves = [1.0, 1.0, 1.0]
    for _ in range(500):
        compute_resource_yields(r, season_id=1, climate_phase=ClimatePhase.TEMPERATE, worker_count=10)
    assert r.resource_reserves[1] == 1.0  # Salt never depletes


# --- Task 6 (M34): check_food_yield ---

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


# --- Task 7 (Climate Suspension Split) ---

def test_suspension_split_types():
    """resource_suspensions uses int keys, route_suspensions uses str keys."""
    from chronicler.models import Region, ResourceType
    r = Region(name="Test", terrain="forest", carrying_capacity=50, resources="timber")
    r.resource_suspensions[ResourceType.TIMBER] = 10
    r.route_suspensions["trade_route"] = 5
    assert ResourceType.TIMBER in r.resource_suspensions
    assert "trade_route" in r.route_suspensions
    assert "timber" not in r.resource_suspensions  # No string keys in resource_suspensions
