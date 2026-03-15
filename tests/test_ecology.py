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

    def test_skips_uncontrolled_regions(self):
        w = self._make_world()
        w.regions[0].controller = None
        old = w.regions[0].ecology.soil
        tick_ecology(w, ClimatePhase.TEMPERATE)
        assert w.regions[0].ecology.soil == old

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
    def _make_world(self, water=0.15, pop=50):
        from chronicler.models import Leader, Civilization
        r = Region(
            name="TestRegion", terrain="plains", carrying_capacity=100,
            resources="fertile", population=pop, controller="TestCiv",
            ecology=RegionEcology(soil=0.8, water=water, forest_cover=0.3),
        )
        civ = Civilization(
            name="TestCiv", population=pop, military=30, economy=40,
            culture=30, stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["TestRegion"],
        )
        return WorldState(name="T", seed=42, regions=[r], civilizations=[civ])

    def test_famine_fires_when_water_below_threshold(self):
        w = self._make_world(water=0.15)
        events = tick_ecology(w, ClimatePhase.TEMPERATE)
        famine_events = [e for e in events if e.event_type == "famine"]
        assert len(famine_events) == 1
        assert "TestRegion" in famine_events[0].description

    def test_no_famine_when_water_above_threshold(self):
        w = self._make_world(water=0.5)
        events = tick_ecology(w, ClimatePhase.TEMPERATE)
        famine_events = [e for e in events if e.event_type == "famine"]
        assert len(famine_events) == 0

    def test_no_famine_during_cooldown(self):
        w = self._make_world(water=0.15)
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
