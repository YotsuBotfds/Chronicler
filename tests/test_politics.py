"""Tests for M14a political topology model fields (Tasks 1-4)."""
from chronicler.models import ActionType, Civilization, Leader, WorldState
from chronicler.scenario import ScenarioConfig
from chronicler.world_gen import generate_world


# --- Task 1: capital_region and war_start_turns ---

def test_civilization_has_capital_region():
    leader = Leader(name="Test", trait="bold", reign_start=0)
    civ = Civilization(
        name="Test", population=50, military=30, economy=40,
        culture=30, stability=50, leader=leader,
        regions=["Alpha", "Beta"], capital_region="Alpha",
    )
    assert civ.capital_region == "Alpha"


def test_civilization_capital_region_defaults_none():
    leader = Leader(name="Test", trait="bold", reign_start=0)
    civ = Civilization(
        name="Test", population=50, military=30, economy=40,
        culture=30, stability=50, leader=leader,
    )
    assert civ.capital_region is None


def test_worldstate_has_war_start_turns():
    ws = WorldState(name="test", seed=42)
    assert ws.war_start_turns == {}


# --- Task 2: MOVE_CAPITAL action type ---

def test_move_capital_action_exists():
    assert ActionType.MOVE_CAPITAL == "move_capital"


# --- Task 3: world_gen sets capital_region ---

def test_world_gen_sets_capital_region():
    world = generate_world(seed=42)
    for civ in world.civilizations:
        assert civ.capital_region is not None
        assert civ.capital_region in civ.regions


# --- Task 4: secession_pool and capital override ---

def test_scenario_config_has_secession_pool():
    config = ScenarioConfig(name="test")
    assert config.secession_pool == []


def test_scenario_capital_override(tmp_path):
    """Scenario YAML can specify capital per civ."""
    from chronicler.scenario import load_scenario, apply_scenario
    yaml_content = """
name: test
civilizations:
  - name: TestCiv
    capital: "Region A"
"""
    p = tmp_path / "test.yaml"
    p.write_text(yaml_content)
    config = load_scenario(p)
    assert config.civilizations[0].capital == "Region A"
