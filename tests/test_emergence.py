"""Tests for M18 Emergence and Chaos systems."""
import pytest
from chronicler.models import PandemicRegion, TerrainTransitionRule


class TestPandemicRegion:
    def test_create(self):
        pr = PandemicRegion(region_name="Verdant Plains", severity=2, turns_remaining=5)
        assert pr.region_name == "Verdant Plains"
        assert pr.severity == 2
        assert pr.turns_remaining == 5

    def test_serialization_roundtrip(self):
        pr = PandemicRegion(region_name="Iron Peaks", severity=1, turns_remaining=4)
        data = pr.model_dump()
        pr2 = PandemicRegion(**data)
        assert pr2 == pr


class TestTerrainTransitionRule:
    def test_create(self):
        rule = TerrainTransitionRule(
            from_terrain="forest", to_terrain="plains",
            condition="low_fertility", threshold_turns=50,
        )
        assert rule.from_terrain == "forest"
        assert rule.threshold_turns == 50

    def test_serialization_roundtrip(self):
        rule = TerrainTransitionRule(
            from_terrain="plains", to_terrain="forest",
            condition="depopulated", threshold_turns=100,
        )
        data = rule.model_dump()
        rule2 = TerrainTransitionRule(**data)
        assert rule2 == rule


from chronicler.models import (
    Region, Civilization, WorldState, ClimateConfig, Leader,
    PandemicRegion, TerrainTransitionRule,
)


class TestM18ModelExtensions:
    def test_region_has_low_fertility_turns(self):
        r = Region(name="T", terrain="plains", carrying_capacity=80, resources="fertile")
        assert r.low_fertility_turns == 0

    def test_civilization_has_stress_fields(self):
        c = Civilization(
            name="T", population=50, military=50, economy=50,
            culture=50, stability=50, leader=Leader(name="L", trait="bold", reign_start=0),
        )
        assert c.civ_stress == 0
        assert c.regions_start_of_turn == 0
        assert c.was_in_twilight is False
        assert c.capital_start_of_turn is None

    def test_world_has_emergence_fields(self):
        w = WorldState(name="T", seed=42)
        assert w.stress_index == 0
        assert w.black_swan_cooldown == 0
        assert w.pandemic_state == []
        assert len(w.terrain_transition_rules) == 2
        assert w.terrain_transition_rules[0].from_terrain == "forest"
        assert w.terrain_transition_rules[1].from_terrain == "plains"
        assert w.chaos_multiplier == 1.0
        assert w.black_swan_cooldown_turns == 30

    def test_climate_config_has_phase_offset(self):
        cfg = ClimateConfig()
        assert cfg.phase_offset == 0

    def test_world_state_serialization_with_m18_fields(self):
        w = WorldState(name="T", seed=42)
        w.stress_index = 5
        w.black_swan_cooldown = 10
        w.pandemic_state.append(PandemicRegion(region_name="X", severity=2, turns_remaining=3))
        data = w.model_dump()
        w2 = WorldState(**data)
        assert w2.stress_index == 5
        assert w2.black_swan_cooldown == 10
        assert len(w2.pandemic_state) == 1
        assert w2.pandemic_state[0].region_name == "X"


from chronicler.scenario import ScenarioConfig


class TestScenarioM18:
    def test_scenario_has_chaos_multiplier(self):
        cfg = ScenarioConfig(name="test")
        assert cfg.chaos_multiplier == 1.0

    def test_scenario_has_cooldown_turns(self):
        cfg = ScenarioConfig(name="test")
        assert cfg.black_swan_cooldown_turns == 30

    def test_scenario_terrain_rules_override(self):
        """Verify that scenario can override terrain transition rules."""
        from chronicler.world_gen import generate_world
        from chronicler.scenario import apply_scenario
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        assert len(world.terrain_transition_rules) == 2
        cfg = ScenarioConfig(name="test", terrain_transition_rules=[])
        apply_scenario(world, cfg)
        assert world.terrain_transition_rules == []


from chronicler.models import CivSnapshot, TurnSnapshot


class TestSnapshotExtensions:
    def test_civ_snapshot_has_stress(self):
        snap = CivSnapshot(
            population=50, military=50, economy=50, culture=50,
            stability=50, treasury=100, asabiya=0.5, tech_era="tribal",
            trait="bold", regions=["R1"], leader_name="L", alive=True,
        )
        assert snap.civ_stress == 0

    def test_turn_snapshot_has_stress_index(self):
        snap = TurnSnapshot(turn=0, civ_stats={}, region_control={}, relationships={})
        assert snap.stress_index == 0
        assert snap.pandemic_regions == []
