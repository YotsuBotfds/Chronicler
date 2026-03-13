"""Tests for scenario loading, validation, and application."""
import pytest
import yaml
from pathlib import Path
from types import SimpleNamespace
from chronicler.scenario import (
    ScenarioConfig, RegionOverride, CivOverride, LeaderOverride, ConditionConfig,
    load_scenario, apply_scenario, resolve_scenario_params,
)
from chronicler.world_gen import generate_world
from chronicler.simulation import run_turn
from chronicler.action_engine import ActionEngine
from chronicler.models import (
    ActiveCondition, Civilization, Disposition, Leader, Region,
    Relationship, TechEra, WorldState,
)


class TestScenarioModels:
    def test_minimal_config(self):
        """Minimal valid config: just a name."""
        config = ScenarioConfig(name="Test")
        assert config.name == "Test"
        assert config.civilizations == []
        assert config.regions == []
        assert config.relationships == {}

    def test_name_required(self):
        with pytest.raises(Exception):
            ScenarioConfig()

    def test_region_override_name_required(self):
        r = RegionOverride(name="Willmar")
        assert r.terrain is None
        assert r.carrying_capacity is None

    def test_civ_override_all_optional_except_name(self):
        c = CivOverride(name="Farmer Co-ops")
        assert c.population is None
        assert c.military is None
        assert c.leader is None

    def test_leader_override_all_optional(self):
        lo = LeaderOverride()
        assert lo.name is None
        assert lo.trait is None

    def test_condition_config_fields(self):
        cc = ConditionConfig(type="drought", affected=["Civ A"], duration=3, severity=4)
        assert cc.type == "drought"
        assert cc.affected == ["Civ A"]

    def test_full_config(self):
        """Full config with all fields populated."""
        config = ScenarioConfig(
            name="Test Scenario",
            description="A test",
            world_name="Testworld",
            seed=42,
            num_civs=2,
            num_regions=4,
            num_turns=50,
            reflection_interval=10,
            regions=[RegionOverride(name="Region A", terrain="plains")],
            civilizations=[CivOverride(
                name="Civ A", economy=8, leader=LeaderOverride(trait="cautious"),
            )],
            relationships={"Civ A": {"Civ B": "hostile"}},
            event_probability_overrides={"drought": 0.1},
            starting_conditions=[ConditionConfig(type="drought", affected=["Civ A"], duration=3, severity=4)],
        )
        assert config.seed == 42
        assert config.civilizations[0].economy == 8
        assert config.civilizations[0].leader.trait == "cautious"

    def test_event_flavor_field(self):
        from chronicler.scenario import EventFlavor
        config = ScenarioConfig(
            name="Test",
            event_flavor={"drought": {"name": "Harsh Winter", "description": "Cold"}},
        )
        assert config.event_flavor["drought"].name == "Harsh Winter"

    def test_event_flavor_none_by_default(self):
        config = ScenarioConfig(name="Test")
        assert config.event_flavor is None

    def test_narrative_style_field(self):
        config = ScenarioConfig(name="Test", narrative_style="Terse and pragmatic.")
        assert config.narrative_style == "Terse and pragmatic."

    def test_narrative_style_none_by_default(self):
        config = ScenarioConfig(name="Test")
        assert config.narrative_style is None

    def test_leader_name_pool_on_civ_override(self):
        c = CivOverride(name="Test", leader_name_pool=["A", "B", "C", "D", "E"])
        assert c.leader_name_pool == ["A", "B", "C", "D", "E"]

    def test_leader_name_pool_none_by_default(self):
        c = CivOverride(name="Test")
        assert c.leader_name_pool is None

    def test_region_override_controller_field(self):
        r = RegionOverride(name="Test", controller="Civ A")
        assert r.controller == "Civ A"

    def test_region_override_controller_none_by_default(self):
        r = RegionOverride(name="Test")
        assert r.controller is None


class TestLoadScenario:
    def _write_yaml(self, tmp_path: Path, data: dict) -> Path:
        p = tmp_path / "scenario.yaml"
        p.write_text(yaml.dump(data))
        return p

    def test_load_valid_minimal(self, tmp_path):
        path = self._write_yaml(tmp_path, {"name": "Test"})
        config = load_scenario(path)
        assert config.name == "Test"

    def test_load_missing_name(self, tmp_path):
        path = self._write_yaml(tmp_path, {"description": "No name"})
        with pytest.raises(ValueError, match="name"):
            load_scenario(path)

    def test_load_invalid_tech_era(self, tmp_path):
        path = self._write_yaml(tmp_path, {
            "name": "Test",
            "civilizations": [{"name": "Civ A", "tech_era": "stone_age"}],
        })
        with pytest.raises(ValueError, match="tech_era"):
            load_scenario(path)

    def test_load_stat_out_of_range(self, tmp_path):
        path = self._write_yaml(tmp_path, {
            "name": "Test",
            "civilizations": [{"name": "Civ A", "population": 15}],
        })
        with pytest.raises(ValueError):
            load_scenario(path)

    def test_load_invalid_disposition(self, tmp_path):
        path = self._write_yaml(tmp_path, {
            "name": "Test",
            "relationships": {"A": {"B": "angry"}},
        })
        with pytest.raises(ValueError, match="disposition"):
            load_scenario(path)

    def test_load_invalid_event_key(self, tmp_path):
        path = self._write_yaml(tmp_path, {
            "name": "Test",
            "event_probability_overrides": {"coup": 0.5},
        })
        with pytest.raises(ValueError, match="coup"):
            load_scenario(path)

    def test_load_event_probability_out_of_range(self, tmp_path):
        path = self._write_yaml(tmp_path, {
            "name": "Test",
            "event_probability_overrides": {"drought": 1.5},
        })
        with pytest.raises(ValueError, match="probability"):
            load_scenario(path)

    def test_load_num_civs_less_than_defined(self, tmp_path):
        path = self._write_yaml(tmp_path, {
            "name": "Test",
            "num_civs": 1,
            "civilizations": [{"name": "A"}, {"name": "B"}],
        })
        with pytest.raises(ValueError, match="num_civs"):
            load_scenario(path)

    def test_load_num_regions_less_than_defined(self, tmp_path):
        path = self._write_yaml(tmp_path, {
            "name": "Test",
            "num_regions": 1,
            "regions": [{"name": "A"}, {"name": "B"}],
        })
        with pytest.raises(ValueError, match="num_regions"):
            load_scenario(path)

    def test_load_num_regions_less_than_num_civs(self, tmp_path):
        path = self._write_yaml(tmp_path, {
            "name": "Test",
            "num_civs": 4,
            "num_regions": 2,
        })
        with pytest.raises(ValueError, match="num_regions"):
            load_scenario(path)

    def test_load_negative_treasury(self, tmp_path):
        path = self._write_yaml(tmp_path, {
            "name": "Test",
            "civilizations": [{"name": "A", "treasury": -5}],
        })
        with pytest.raises(ValueError):
            load_scenario(path)

    def test_load_zero_duration(self, tmp_path):
        path = self._write_yaml(tmp_path, {
            "name": "Test",
            "starting_conditions": [{"type": "drought", "affected": ["A"], "duration": 0, "severity": 3}],
        })
        with pytest.raises(ValueError):
            load_scenario(path)

    def test_load_full_scenario(self, tmp_path):
        data = {
            "name": "Full Test",
            "world_name": "Testworld",
            "seed": 42,
            "num_civs": 3,
            "num_regions": 6,
            "num_turns": 50,
            "civilizations": [
                {"name": "Civ A", "economy": 8, "tech_era": "iron", "leader": {"trait": "cautious"}},
                {"name": "Civ B", "military": 7},
            ],
            "regions": [{"name": "Region X", "terrain": "plains", "carrying_capacity": 9}],
            "relationships": {"Civ A": {"Civ B": "hostile"}},
            "event_probability_overrides": {"drought": 0.12},
            "starting_conditions": [{"type": "drought", "affected": ["Civ A"], "duration": 3, "severity": 4}],
        }
        path = self._write_yaml(tmp_path, data)
        config = load_scenario(path)
        assert config.name == "Full Test"
        assert config.civilizations[0].economy == 8
        assert config.civilizations[0].leader.trait == "cautious"
        assert config.relationships == {"Civ A": {"Civ B": "hostile"}}

    def test_load_invalid_event_flavor_key(self, tmp_path):
        path = self._write_yaml(tmp_path, {
            "name": "Test",
            "event_flavor": {"tech_advancement": {"name": "X", "description": "Y"}},
        })
        with pytest.raises(ValueError, match="tech_advancement"):
            load_scenario(path)

    def test_load_valid_event_flavor(self, tmp_path):
        path = self._write_yaml(tmp_path, {
            "name": "Test",
            "event_flavor": {"drought": {"name": "Harsh Winter", "description": "Cold"}},
        })
        config = load_scenario(path)
        assert config.event_flavor["drought"].name == "Harsh Winter"

    def test_load_leader_name_pool_too_few(self, tmp_path):
        path = self._write_yaml(tmp_path, {
            "name": "Test",
            "civilizations": [{"name": "Civ A", "leader_name_pool": ["A", "B"]}],
        })
        with pytest.raises(ValueError, match="leader_name_pool"):
            load_scenario(path)

    def test_load_leader_name_pool_empty_list(self, tmp_path):
        path = self._write_yaml(tmp_path, {
            "name": "Test",
            "civilizations": [{"name": "Civ A", "leader_name_pool": []}],
        })
        with pytest.raises(ValueError, match="leader_name_pool"):
            load_scenario(path)

    def test_load_leader_name_pool_valid(self, tmp_path):
        path = self._write_yaml(tmp_path, {
            "name": "Test",
            "civilizations": [{"name": "Civ A", "leader_name_pool": ["A", "B", "C", "D", "E"]}],
        })
        config = load_scenario(path)
        assert config.civilizations[0].leader_name_pool == ["A", "B", "C", "D", "E"]

    def test_load_cross_pool_duplicate_raises(self, tmp_path):
        path = self._write_yaml(tmp_path, {
            "name": "Test",
            "civilizations": [
                {"name": "Civ A", "leader_name_pool": ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]},
                {"name": "Civ B", "leader_name_pool": ["Alpha", "Zeta", "Eta", "Theta", "Iota"]},
            ],
        })
        with pytest.raises(ValueError, match="Alpha"):
            load_scenario(path)

    def test_load_controller_invalid_civ_name(self, tmp_path):
        path = self._write_yaml(tmp_path, {
            "name": "Test",
            "regions": [{"name": "R1", "controller": "Nonexistent Civ"}],
        })
        with pytest.raises(ValueError, match="controller"):
            load_scenario(path)

    def test_load_controller_valid_civ_name(self, tmp_path):
        path = self._write_yaml(tmp_path, {
            "name": "Test",
            "civilizations": [{"name": "Civ A"}],
            "regions": [{"name": "R1", "controller": "Civ A"}],
        })
        config = load_scenario(path)
        assert config.regions[0].controller == "Civ A"

    def test_load_controller_none_accepted(self, tmp_path):
        path = self._write_yaml(tmp_path, {
            "name": "Test",
            "regions": [{"name": "R1"}],
        })
        config = load_scenario(path)
        assert config.regions[0].controller is None

    def test_load_controller_none_string(self, tmp_path):
        """The literal string 'none' (quoted in YAML) means explicitly uncontrolled."""
        path = self._write_yaml(tmp_path, {
            "name": "Test",
            "regions": [{"name": "R1", "controller": "none"}],
        })
        config = load_scenario(path)
        assert config.regions[0].controller == "none"


@pytest.fixture
def generated_world():
    """A standard generated world for apply tests."""
    return generate_world(seed=42, num_regions=6, num_civs=3)


class TestApplyScenario:
    def test_civ_injection_replaces_name(self, generated_world):
        old_name = generated_world.civilizations[0].name
        config = ScenarioConfig(
            name="Test",
            civilizations=[CivOverride(name="New Civ")],
        )
        apply_scenario(generated_world, config)
        assert generated_world.civilizations[0].name == "New Civ"
        civ_names = [c.name for c in generated_world.civilizations]
        assert old_name not in civ_names

    def test_civ_injection_overrides_stats(self, generated_world):
        config = ScenarioConfig(
            name="Test",
            civilizations=[CivOverride(name="Strong Civ", military=9, economy=8)],
        )
        apply_scenario(generated_world, config)
        civ = generated_world.civilizations[0]
        assert civ.military == 9
        assert civ.economy == 8

    def test_civ_injection_retains_defaults(self, generated_world):
        old_pop = generated_world.civilizations[0].population
        config = ScenarioConfig(
            name="Test",
            civilizations=[CivOverride(name="Renamed")],
        )
        apply_scenario(generated_world, config)
        assert generated_world.civilizations[0].population == old_pop

    def test_leader_override_patches_trait(self, generated_world):
        config = ScenarioConfig(
            name="Test",
            civilizations=[CivOverride(
                name="Led Civ",
                leader=LeaderOverride(trait="visionary"),
            )],
        )
        apply_scenario(generated_world, config)
        assert generated_world.civilizations[0].leader.trait == "visionary"

    def test_leader_override_patches_name(self, generated_world):
        old_reign = generated_world.civilizations[0].leader.reign_start
        config = ScenarioConfig(
            name="Test",
            civilizations=[CivOverride(
                name="Led Civ",
                leader=LeaderOverride(name="Elder Johansson"),
            )],
        )
        apply_scenario(generated_world, config)
        assert generated_world.civilizations[0].leader.name == "Elder Johansson"
        assert generated_world.civilizations[0].leader.reign_start == old_reign

    def test_region_injection_replaces_name(self, generated_world):
        old_name = generated_world.regions[0].name
        config = ScenarioConfig(
            name="Test",
            regions=[RegionOverride(name="Willmar", terrain="plains", carrying_capacity=9)],
        )
        apply_scenario(generated_world, config)
        assert generated_world.regions[0].name == "Willmar"
        assert generated_world.regions[0].terrain == "plains"
        assert generated_world.regions[0].carrying_capacity == 9

    def test_region_rename_updates_civ_regions(self, generated_world):
        """Critical: civ.regions list must be updated when region is renamed."""
        old_region_name = generated_world.regions[0].name
        controlling_civ = None
        for civ in generated_world.civilizations:
            if old_region_name in civ.regions:
                controlling_civ = civ
                break
        config = ScenarioConfig(
            name="Test",
            regions=[RegionOverride(name="Willmar")],
        )
        apply_scenario(generated_world, config)
        if controlling_civ:
            assert "Willmar" in controlling_civ.regions
            assert old_region_name not in controlling_civ.regions

    def test_civ_rename_updates_region_controller(self, generated_world):
        """Critical: region.controller must be updated when civ is renamed."""
        old_civ_name = generated_world.civilizations[0].name
        controlled_regions = [r for r in generated_world.regions if r.controller == old_civ_name]
        config = ScenarioConfig(
            name="Test",
            civilizations=[CivOverride(name="New Empire")],
        )
        apply_scenario(generated_world, config)
        for r in controlled_regions:
            assert r.controller == "New Empire"

    def test_relationship_override(self, generated_world):
        civ_names = [c.name for c in generated_world.civilizations]
        config = ScenarioConfig(
            name="Test",
            civilizations=[
                CivOverride(name="Alpha"),
                CivOverride(name="Beta"),
            ],
            relationships={"Alpha": {"Beta": "hostile"}},
        )
        apply_scenario(generated_world, config)
        assert generated_world.relationships["Alpha"]["Beta"].disposition == Disposition.HOSTILE

    def test_relationship_auto_symmetry(self, generated_world):
        config = ScenarioConfig(
            name="Test",
            civilizations=[
                CivOverride(name="Alpha"),
                CivOverride(name="Beta"),
            ],
            relationships={"Alpha": {"Beta": "hostile"}},
        )
        apply_scenario(generated_world, config)
        assert generated_world.relationships["Beta"]["Alpha"].disposition == Disposition.HOSTILE

    def test_relationship_explicit_asymmetry(self, generated_world):
        config = ScenarioConfig(
            name="Test",
            civilizations=[
                CivOverride(name="Alpha"),
                CivOverride(name="Beta"),
            ],
            relationships={
                "Alpha": {"Beta": "hostile"},
                "Beta": {"Alpha": "suspicious"},
            },
        )
        apply_scenario(generated_world, config)
        assert generated_world.relationships["Alpha"]["Beta"].disposition == Disposition.HOSTILE
        assert generated_world.relationships["Beta"]["Alpha"].disposition == Disposition.SUSPICIOUS

    def test_event_probability_override(self, generated_world):
        config = ScenarioConfig(
            name="Test",
            event_probability_overrides={"drought": 0.5, "rebellion": 0.2},
        )
        apply_scenario(generated_world, config)
        assert generated_world.event_probabilities["drought"] == 0.5
        assert generated_world.event_probabilities["rebellion"] == 0.2
        assert generated_world.event_probabilities["plague"] == 0.03

    def test_starting_conditions(self, generated_world):
        civ_name = generated_world.civilizations[0].name
        config = ScenarioConfig(
            name="Test",
            starting_conditions=[
                ConditionConfig(type="drought", affected=[civ_name], duration=3, severity=4),
            ],
        )
        apply_scenario(generated_world, config)
        conds = [c for c in generated_world.active_conditions if c.condition_type == "drought"]
        assert len(conds) == 1
        assert conds[0].affected_civs == [civ_name]
        assert conds[0].duration == 3
        assert conds[0].severity == 4

    def test_world_name_override(self, generated_world):
        config = ScenarioConfig(name="Test", world_name="The River Valleys")
        apply_scenario(generated_world, config)
        assert generated_world.name == "The River Valleys"

    def test_world_name_not_overridden_when_absent(self, generated_world):
        old_name = generated_world.name
        config = ScenarioConfig(name="Test")
        apply_scenario(generated_world, config)
        assert generated_world.name == old_name

    def test_filler_civs_untouched(self, generated_world):
        """Civs not mentioned in overrides should remain as generated."""
        filler_name = generated_world.civilizations[2].name
        filler_mil = generated_world.civilizations[2].military
        config = ScenarioConfig(
            name="Test",
            civilizations=[CivOverride(name="Override A")],
        )
        apply_scenario(generated_world, config)
        assert generated_world.civilizations[2].name == filler_name
        assert generated_world.civilizations[2].military == filler_mil

    def test_civ_name_match_patches_in_place(self, generated_world):
        """If CivOverride.name matches an existing generated civ, patch it instead of replacing a slot."""
        existing_name = generated_world.civilizations[1].name
        config = ScenarioConfig(
            name="Test",
            civilizations=[CivOverride(name=existing_name, military=10)],
        )
        apply_scenario(generated_world, config)
        matched = [c for c in generated_world.civilizations if c.name == existing_name]
        assert len(matched) == 1
        assert matched[0].military == 10

    def test_tech_era_override(self, generated_world):
        config = ScenarioConfig(
            name="Test",
            civilizations=[CivOverride(name="Era Civ", tech_era="classical")],
        )
        apply_scenario(generated_world, config)
        assert generated_world.civilizations[0].tech_era == TechEra.CLASSICAL

    def test_injected_civ_has_regions(self, generated_world):
        """Positive case: injected civ inherits the replaced civ's regions."""
        config = ScenarioConfig(
            name="Test",
            civilizations=[CivOverride(name="Renamed Civ")],
        )
        apply_scenario(generated_world, config)
        injected = generated_world.civilizations[0]
        assert len(injected.regions) >= 1

    def test_post_apply_catches_orphaned_condition_civ(self, generated_world):
        """Post-apply validation: condition referencing non-existent civ should raise."""
        config = ScenarioConfig(
            name="Test",
            starting_conditions=[
                ConditionConfig(type="drought", affected=["Nonexistent Civ"], duration=3, severity=4),
            ],
        )
        with pytest.raises(ValueError, match="unknown civ"):
            apply_scenario(generated_world, config)

    def test_leader_name_pool_copied_to_civ(self, generated_world):
        pool = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]
        config = ScenarioConfig(
            name="Test",
            civilizations=[CivOverride(name="Pooled Civ", leader_name_pool=pool)],
        )
        apply_scenario(generated_world, config)
        assert generated_world.civilizations[0].leader_name_pool == pool

    def test_leader_name_pool_none_when_not_set(self, generated_world):
        config = ScenarioConfig(
            name="Test",
            civilizations=[CivOverride(name="No Pool Civ")],
        )
        apply_scenario(generated_world, config)
        assert generated_world.civilizations[0].leader_name_pool is None

    def test_controller_override_sets_region_controller(self, generated_world):
        civ_name = generated_world.civilizations[0].name
        config = ScenarioConfig(
            name="Test",
            civilizations=[CivOverride(name="Controller Civ")],
            regions=[RegionOverride(name="Controlled Region", controller="Controller Civ")],
        )
        apply_scenario(generated_world, config)
        region = next(r for r in generated_world.regions if r.name == "Controlled Region")
        assert region.controller == "Controller Civ"
        civ = next(c for c in generated_world.civilizations if c.name == "Controller Civ")
        assert "Controlled Region" in civ.regions

    def test_controller_none_makes_region_uncontrolled(self, generated_world):
        config = ScenarioConfig(
            name="Test",
            regions=[RegionOverride(name="Neutral Zone", controller="none")],
        )
        apply_scenario(generated_world, config)
        region = next(r for r in generated_world.regions if r.name == "Neutral Zone")
        assert region.controller is None


class TestResolveScenarioParams:
    def _cli_args(self, **kwargs):
        """Simulate CLI args. Use None for sentinel defaults (meaning user didn't pass the flag)."""
        defaults = {
            "seed": None, "turns": None, "civs": None, "regions": None,
            "reflection_interval": None, "scenario": "test.yaml", "resume": None,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_cli_wins_for_seed(self):
        config = ScenarioConfig(name="Test", seed=99)
        args = self._cli_args(seed=123)
        result = resolve_scenario_params(config, args)
        assert result["seed"] == 123

    def test_scenario_provides_seed_when_cli_default(self):
        config = ScenarioConfig(name="Test", seed=99)
        args = self._cli_args(seed=None)
        result = resolve_scenario_params(config, args)
        assert result["seed"] == 99

    def test_fallback_to_hardcoded_default(self):
        config = ScenarioConfig(name="Test")
        args = self._cli_args(seed=None)
        result = resolve_scenario_params(config, args)
        assert result["seed"] == 42

    def test_cli_wins_for_turns(self):
        config = ScenarioConfig(name="Test", num_turns=80)
        args = self._cli_args(turns=100)
        result = resolve_scenario_params(config, args)
        assert result["num_turns"] == 100

    def test_scenario_provides_turns_when_cli_default(self):
        config = ScenarioConfig(name="Test", num_turns=80)
        args = self._cli_args(turns=None)
        result = resolve_scenario_params(config, args)
        assert result["num_turns"] == 80

    def test_auto_expand_num_civs(self):
        config = ScenarioConfig(
            name="Test",
            civilizations=[CivOverride(name="A"), CivOverride(name="B"), CivOverride(name="C")],
        )
        args = self._cli_args(civs=None)
        result = resolve_scenario_params(config, args)
        assert result["num_civs"] == 3

    def test_auto_expand_num_regions(self):
        config = ScenarioConfig(
            name="Test",
            regions=[RegionOverride(name=f"R{i}") for i in range(10)],
        )
        args = self._cli_args(regions=None)
        result = resolve_scenario_params(config, args)
        assert result["num_regions"] == 10

    def test_regions_exceed_template_pool_raises(self):
        config = ScenarioConfig(
            name="Test",
            regions=[RegionOverride(name=f"R{i}") for i in range(15)],
        )
        args = self._cli_args(regions=None)
        with pytest.raises(ValueError, match="region templates exist"):
            resolve_scenario_params(config, args)

    def test_scenario_resume_mutually_exclusive(self):
        config = ScenarioConfig(name="Test")
        args = self._cli_args(resume="/some/path.json")
        with pytest.raises(ValueError, match="mutually exclusive"):
            resolve_scenario_params(config, args)


TEMPLATE_DIR = Path(__file__).parent.parent / "scenarios"


class TestTemplates:
    def test_fantasy_default_loads(self):
        config = load_scenario(TEMPLATE_DIR / "fantasy_default.yaml")
        assert config.name == "Fantasy Default"
        assert config.world_name == "Aetheris"
        assert config.civilizations == []

    def test_two_empires_loads(self):
        config = load_scenario(TEMPLATE_DIR / "two_empires.yaml")
        assert config.name == "Two Empires"
        assert len(config.civilizations) == 2
        assert config.civilizations[0].name == "Dominion of Ashar"
        assert config.civilizations[0].military == 7

    def test_golden_age_loads(self):
        config = load_scenario(TEMPLATE_DIR / "golden_age.yaml")
        assert config.name == "Golden Age"
        assert len(config.civilizations) == 4
        assert config.relationships["Aureate Republic"]["Verdant Communion"] == "allied"

    def test_fantasy_default_runs_10_turns(self):
        config = load_scenario(TEMPLATE_DIR / "fantasy_default.yaml")
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        apply_scenario(world, config)
        for i in range(10):
            engine = ActionEngine(world)
            run_turn(
                world,
                action_selector=lambda c, w, _e=engine: _e.select_action(c, seed=w.seed),
                narrator=lambda w, e: "Turn narrative.",
                seed=42 + i,
            )
        assert world.turn == 10

    def test_two_empires_runs_10_turns(self):
        config = load_scenario(TEMPLATE_DIR / "two_empires.yaml")
        world = generate_world(seed=99, num_regions=6, num_civs=2)
        apply_scenario(world, config)
        # Verify turn-0 state
        civ_names = {c.name for c in world.civilizations}
        assert "Dominion of Ashar" in civ_names
        assert "Thalassic League" in civ_names
        ashar = next(c for c in world.civilizations if c.name == "Dominion of Ashar")
        assert ashar.military == 7
        assert ashar.tech_era == TechEra.IRON
        assert world.relationships["Dominion of Ashar"]["Thalassic League"].disposition == Disposition.HOSTILE
        # Run 10 turns
        for i in range(10):
            engine = ActionEngine(world)
            run_turn(
                world,
                action_selector=lambda c, w, _e=engine: _e.select_action(c, seed=w.seed),
                narrator=lambda w, e: "Turn narrative.",
                seed=99 + i,
            )
        assert world.turn == 10

    def test_golden_age_runs_10_turns(self):
        config = load_scenario(TEMPLATE_DIR / "golden_age.yaml")
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        apply_scenario(world, config)
        # Verify relationships
        assert world.relationships["Aureate Republic"]["Verdant Communion"].disposition == Disposition.ALLIED
        assert world.relationships["Jade Consortium"]["Silverpeak Accord"].disposition == Disposition.FRIENDLY
        # Run 10 turns
        for i in range(10):
            engine = ActionEngine(world)
            run_turn(
                world,
                action_selector=lambda c, w, _e=engine: _e.select_action(c, seed=w.seed),
                narrator=lambda w, e: "Turn narrative.",
                seed=42 + i,
            )
        assert world.turn == 10


class TestIntegration:
    def test_two_empires_20_turns_produces_wars(self):
        """Two hostile iron-age powers should produce war events in 20 turns."""
        config = load_scenario(TEMPLATE_DIR / "two_empires.yaml")
        world = generate_world(seed=99, num_regions=6, num_civs=2)
        apply_scenario(world, config)
        for i in range(20):
            engine = ActionEngine(world)
            run_turn(
                world,
                action_selector=lambda c, w, _e=engine: _e.select_action(c, seed=w.seed),
                narrator=lambda w, e: "Turn narrative.",
                seed=99 + i,
            )
        war_events = [e for e in world.events_timeline if e.event_type == "war"]
        assert len(war_events) > 0, "Two hostile iron-age powers should produce war events"
