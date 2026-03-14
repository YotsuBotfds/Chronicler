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


# --- Task 5: apply_governing_costs ---

from chronicler.politics import apply_governing_costs
from chronicler.models import Region


def _make_world_with_regions(region_names, civ_name="Empire", capital="A", adjacencies=None):
    """Helper: create a WorldState with a civ controlling given regions."""
    regions = []
    for name in region_names:
        adj = adjacencies.get(name, []) if adjacencies else []
        regions.append(Region(name=name, terrain="plains", carrying_capacity=50, resources="fertile",
                              adjacencies=adj, controller=civ_name))
    leader = Leader(name="Leader", trait="bold", reign_start=0)
    civ = Civilization(
        name=civ_name, population=50, military=30, economy=40,
        culture=30, stability=50, treasury=100, leader=leader,
        regions=region_names, capital_region=capital,
    )
    world = WorldState(name="test", seed=42, regions=regions, civilizations=[civ])
    return world


def test_governing_cost_no_cost_for_two_or_fewer_regions():
    world = _make_world_with_regions(["A", "B"], capital="A", adjacencies={"A": ["B"], "B": ["A"]})
    apply_governing_costs(world)
    civ = world.civilizations[0]
    assert civ.stability == 50  # unchanged
    assert civ.treasury == 100  # unchanged


def test_governing_cost_three_regions_compact():
    adj = {"A": ["B", "C"], "B": ["A", "C"], "C": ["A", "B"]}
    world = _make_world_with_regions(["A", "B", "C"], capital="A", adjacencies=adj)
    apply_governing_costs(world)
    civ = world.civilizations[0]
    # treasury: (3-2)*2 + 2*(1*2) = 2+4 = 6
    assert civ.treasury == 100 - 6
    # stability: 1+1 = 2
    assert civ.stability == 50 - 2


def test_governing_cost_distant_regions_cost_more():
    adj = {"A": ["B"], "B": ["A", "C"], "C": ["B", "D"], "D": ["C"]}
    world = _make_world_with_regions(["A", "B", "C", "D"], capital="A", adjacencies=adj)
    apply_governing_costs(world)
    civ = world.civilizations[0]
    # treasury: (4-2)*2 + (1*2 + 2*2 + 3*2) = 4 + 12 = 16
    assert civ.treasury == 100 - 16
    # stability: 1 + 2 + 3 = 6
    assert civ.stability == 50 - 6


# --- Task 6: check_capital_loss ---

from chronicler.politics import check_capital_loss


def test_capital_loss_triggers_stability_penalty():
    """When capital not in civ.regions, stability -20 and capital reassigned."""
    adj = {"B": ["C"], "C": ["B"]}
    world = _make_world_with_regions(["B", "C"], capital="A", adjacencies=adj)
    # Capital "A" is not in regions ["B", "C"]
    civ = world.civilizations[0]
    civ.stability = 50
    events = check_capital_loss(world)
    assert civ.stability <= 30  # -20
    assert civ.capital_region in civ.regions  # reassigned
    assert len(events) > 0


def test_capital_loss_picks_best_remaining_region():
    """Capital reassignment picks highest carrying_capacity * fertility."""
    regions = [
        Region(name="B", terrain="plains", carrying_capacity=30, resources="fertile", fertility=0.5),
        Region(name="C", terrain="plains", carrying_capacity=50, resources="fertile", fertility=0.8),
    ]
    leader = Leader(name="L", trait="bold", reign_start=0)
    civ = Civilization(
        name="E", population=50, military=30, economy=40,
        culture=30, stability=50, treasury=100, leader=leader,
        regions=["B", "C"], capital_region="A",
    )
    world = WorldState(name="test", seed=42, regions=regions, civilizations=[civ])
    check_capital_loss(world)
    # C has 50*0.8=40, B has 30*0.5=15 — C wins
    assert civ.capital_region == "C"


def test_no_capital_loss_when_capital_in_regions():
    adj = {"A": ["B"], "B": ["A"]}
    world = _make_world_with_regions(["A", "B"], capital="A", adjacencies=adj)
    civ = world.civilizations[0]
    civ.stability = 50
    events = check_capital_loss(world)
    assert civ.stability == 50  # unchanged
    assert len(events) == 0


# --- Task 7: check_secession ---

from chronicler.politics import check_secession


def test_secession_does_not_fire_above_threshold():
    adj = {"A": ["B", "C", "D"], "B": ["A"], "C": ["A"], "D": ["A"]}
    world = _make_world_with_regions(["A", "B", "C", "D"], capital="A", adjacencies=adj)
    civ = world.civilizations[0]
    civ.stability = 50  # well above 20
    events = check_secession(world)
    assert len(world.civilizations) == 1  # no secession


def test_secession_does_not_fire_with_too_few_regions():
    adj = {"A": ["B"], "B": ["A"]}
    world = _make_world_with_regions(["A", "B"], capital="A", adjacencies=adj)
    civ = world.civilizations[0]
    civ.stability = 5  # below 20 but only 2 regions
    events = check_secession(world)
    assert len(world.civilizations) == 1


def test_secession_fires_at_zero_stability():
    """At stability 0, probability is 20%. With a favorable seed, secession fires."""
    adj = {"A": ["B"], "B": ["A", "C"], "C": ["B", "D"], "D": ["C", "E"], "E": ["D"]}
    world = _make_world_with_regions(["A", "B", "C", "D", "E"], capital="A", adjacencies=adj)
    civ = world.civilizations[0]
    civ.stability = 0
    civ.population = 50
    civ.military = 30
    civ.economy = 40
    civ.treasury = 100
    civ.leader_name_pool = ["Name1", "Name2", "Name3"]
    fired = False
    for seed in range(100):
        world.seed = seed
        world.turn = seed
        civ.regions = ["A", "B", "C", "D", "E"]
        civ.stability = 0
        civ.population = 50
        civ.military = 30
        civ.economy = 40
        civ.treasury = 100
        world.civilizations = [civ]
        for r in world.regions:
            r.controller = civ.name
        events = check_secession(world)
        if len(world.civilizations) > 1:
            fired = True
            break
    assert fired, "Secession should fire at stability 0 within 100 seed attempts"
    breakaway = world.civilizations[1]
    assert breakaway.name != civ.name
    assert breakaway.tech_era == civ.tech_era
    assert breakaway.asabiya == 0.7
    assert breakaway.stability == 40


def test_secession_stat_split_conserves_stats():
    """Total stats before and after secession are conserved."""
    adj = {"A": ["B"], "B": ["A", "C"], "C": ["B"]}
    world = _make_world_with_regions(["A", "B", "C"], capital="A", adjacencies=adj)
    civ = world.civilizations[0]
    civ.stability = 0
    civ.population = 60
    civ.military = 30
    civ.economy = 45
    civ.treasury = 90
    civ.leader_name_pool = ["N1", "N2"]
    for seed in range(200):
        world.seed = seed
        world.turn = seed
        civ.regions = ["A", "B", "C"]
        civ.stability = 0
        civ.population = 60
        civ.military = 30
        civ.economy = 45
        civ.treasury = 90
        world.civilizations = [civ]
        for r in world.regions:
            r.controller = civ.name
        events = check_secession(world)
        if len(world.civilizations) > 1:
            parent = world.civilizations[0]
            breakaway = world.civilizations[1]
            for stat in ["population", "military", "economy", "treasury"]:
                original = {"population": 60, "military": 30, "economy": 45, "treasury": 90}
                assert getattr(parent, stat) + getattr(breakaway, stat) == original[stat]
            break
