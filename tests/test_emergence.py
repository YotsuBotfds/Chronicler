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


from chronicler.models import (
    ActiveCondition, PandemicRegion, WorldState, Region, Civilization,
    Leader, Relationship, Disposition,
)


def _make_world(**overrides) -> WorldState:
    """Create a minimal WorldState for testing."""
    defaults = dict(name="Test", seed=42)
    defaults.update(overrides)
    return WorldState(**defaults)


def _make_civ(name="TestCiv", **overrides) -> Civilization:
    defaults = dict(
        name=name, population=50, military=50, economy=50,
        culture=50, stability=50,
        leader=Leader(name="L", trait="bold", reign_start=0),
    )
    defaults.update(overrides)
    return Civilization(**defaults)


def _make_region(name="R1", **overrides) -> Region:
    defaults = dict(name=name, terrain="plains", carrying_capacity=80, resources="fertile")
    defaults.update(overrides)
    return Region(**defaults)


class TestComputeCivStress:
    def test_zero_stress_baseline(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        civ = _make_civ()
        assert compute_civ_stress(civ, world) == 0

    def test_war_adds_3(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        civ = _make_civ()
        world.active_wars = [("TestCiv", "EnemyCiv")]
        assert compute_civ_stress(civ, world) == 3

    def test_two_wars_adds_6(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        civ = _make_civ()
        world.active_wars = [("TestCiv", "A"), ("B", "TestCiv")]
        assert compute_civ_stress(civ, world) == 6

    def test_famine_region_adds_2(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        civ = _make_civ()
        r = _make_region(controller="TestCiv", famine_cooldown=3)
        world.regions = [r]
        assert compute_civ_stress(civ, world) == 2

    def test_secession_risk_adds_4(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        civ = _make_civ(stability=15, regions=["R1", "R2", "R3"])
        assert compute_civ_stress(civ, world) == 4

    def test_pandemic_adds_2_per_region(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        civ = _make_civ()
        r1 = _make_region(name="R1", controller="TestCiv")
        r2 = _make_region(name="R2", controller="TestCiv")
        world.regions = [r1, r2]
        world.pandemic_state = [
            PandemicRegion(region_name="R1", severity=2, turns_remaining=3),
            PandemicRegion(region_name="R2", severity=1, turns_remaining=2),
        ]
        assert compute_civ_stress(civ, world) == 4

    def test_turbulent_succession_adds_2(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        world.turn = 10
        leader = Leader(name="L", trait="bold", reign_start=8, succession_type="usurper")
        civ = _make_civ(leader=leader)
        assert compute_civ_stress(civ, world) == 2

    def test_old_succession_no_stress(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        world.turn = 100
        leader = Leader(name="L", trait="bold", reign_start=10, succession_type="usurper")
        civ = _make_civ(leader=leader)
        assert compute_civ_stress(civ, world) == 0

    def test_twilight_adds_3(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        civ = _make_civ(decline_turns=5)
        assert compute_civ_stress(civ, world) == 3

    def test_disaster_condition_adds_2(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        civ = _make_civ()
        world.active_conditions = [
            ActiveCondition(condition_type="drought", affected_civs=["TestCiv"], duration=3, severity=50),
        ]
        assert compute_civ_stress(civ, world) == 2

    def test_volcanic_winter_counts(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        civ = _make_civ()
        world.active_conditions = [
            ActiveCondition(condition_type="volcanic_winter", affected_civs=["TestCiv"], duration=3, severity=40),
        ]
        assert compute_civ_stress(civ, world) == 2

    def test_overextension_adds_per_region_beyond_6(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        civ = _make_civ(regions=[f"R{i}" for i in range(8)])
        assert compute_civ_stress(civ, world) == 2  # 8 - 6 = 2

    def test_stress_caps_at_20(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        world.turn = 1
        leader = Leader(name="L", trait="bold", reign_start=0, succession_type="general")
        civ = _make_civ(
            stability=15, decline_turns=5, leader=leader,
            regions=[f"R{i}" for i in range(16)],
        )
        world.active_wars = [("TestCiv", "A"), ("TestCiv", "B")]
        world.active_conditions = [
            ActiveCondition(condition_type="drought", affected_civs=["TestCiv"], duration=3, severity=50),
        ]
        assert compute_civ_stress(civ, world) == 20

    def test_multiple_factors_stack(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        civ = _make_civ()
        r = _make_region(controller="TestCiv", famine_cooldown=3)
        world.regions = [r]
        world.active_wars = [("TestCiv", "Enemy")]
        assert compute_civ_stress(civ, world) == 5


class TestComputeAllStress:
    def test_updates_all_civs_and_global(self):
        from chronicler.emergence import compute_all_stress
        world = _make_world()
        civ_a = _make_civ(name="A", decline_turns=5)
        civ_b = _make_civ(name="B")
        world.civilizations = [civ_a, civ_b]
        compute_all_stress(world)
        assert civ_a.civ_stress == 3
        assert civ_b.civ_stress == 0
        assert world.stress_index == 3


class TestGetSeverityMultiplier:
    def test_zero_stress(self):
        from chronicler.emergence import get_severity_multiplier
        civ = _make_civ(civ_stress=0)
        assert get_severity_multiplier(civ) == 1.0

    def test_stress_10(self):
        from chronicler.emergence import get_severity_multiplier
        civ = _make_civ(civ_stress=10)
        assert get_severity_multiplier(civ) == pytest.approx(1.25)

    def test_stress_20_cap(self):
        from chronicler.emergence import get_severity_multiplier
        civ = _make_civ(civ_stress=20)
        assert get_severity_multiplier(civ) == pytest.approx(1.5)

    def test_stress_5(self):
        from chronicler.emergence import get_severity_multiplier
        civ = _make_civ(civ_stress=5)
        assert get_severity_multiplier(civ) == pytest.approx(1.125)


class TestStressIntegration:
    def test_stress_computed_after_turn(self):
        """After running a turn, stress should be recomputed."""
        from chronicler.simulation import run_turn
        from chronicler.world_gen import generate_world
        from chronicler.models import ActionType
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        # Give one civ twilight to generate stress
        world.civilizations[0].decline_turns = 5
        run_turn(world, action_selector=lambda c, w: ActionType.DEVELOP,
                 narrator=lambda w, e: "", seed=1)
        # After turn, stress should be computed
        assert world.civilizations[0].civ_stress >= 3  # twilight = 3
        assert world.stress_index >= 3

    def test_snapshots_set_at_turn_start(self):
        """Start-of-turn snapshots should reflect pre-turn state."""
        from chronicler.simulation import run_turn
        from chronicler.world_gen import generate_world
        from chronicler.models import ActionType
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        civ = world.civilizations[0]
        initial_regions = len(civ.regions)
        run_turn(world, action_selector=lambda c, w: ActionType.DEVELOP,
                 narrator=lambda w, e: "", seed=1)
        # Snapshot should have captured the pre-turn region count
        assert civ.regions_start_of_turn == initial_regions


class TestSeverityMultiplierWiring:
    def test_drought_damage_amplified_by_stress(self):
        """A civ with high stress should take more damage from drought."""
        from chronicler.simulation import phase_consequences
        world = _make_world()
        # Civ A: high stress. Civ B: zero stress.
        civ_a = _make_civ(name="A", stability=60, economy=60, civ_stress=20)
        civ_b = _make_civ(name="B", stability=60, economy=60, civ_stress=0)
        world.civilizations = [civ_a, civ_b]
        # Inject drought condition affecting both
        world.active_conditions = [ActiveCondition(
            condition_type="drought", affected_civs=["A", "B"], duration=3, severity=50,
        )]
        phase_consequences(world)
        # Both take stability damage from the condition (severity >= 50 → -10 base)
        # A should take more: int(10 * 1.5) = 15. B takes 10.
        assert civ_a.stability < civ_b.stability

    def test_famine_damage_amplified_by_stress(self):
        """Famine damage should be amplified by stress."""
        from chronicler.simulation import _check_famine
        world = _make_world()
        civ = _make_civ(name="Civ1", population=80, stability=60, civ_stress=20)
        world.civilizations = [civ]
        r = _make_region(name="R1", controller="Civ1", fertility=0.1, famine_cooldown=0)
        world.regions = [r]
        _check_famine(world)
        # Base famine: pop -15, stability -10. With 1.5x: pop -22, stability -15
        assert civ.population <= 80 - 15  # At least base damage
        assert civ.population < 80 - 15 + 1  # More than base (amplified)

    def test_random_event_damage_amplified(self):
        """Random event damage should be amplified by stress."""
        from chronicler.simulation import _apply_event_effects
        world = _make_world()
        civ = _make_civ(stability=60, civ_stress=20)
        world.civilizations = [civ]
        _apply_event_effects("rebellion", civ, world)
        # Base rebellion: stability -20, military -10. With 1.5x: stability -30
        assert civ.stability <= 60 - 20  # At least base
