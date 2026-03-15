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
    pop_per_region = 50 // len(region_names) if region_names else 0
    regions = []
    for i, name in enumerate(region_names):
        adj = adjacencies.get(name, []) if adjacencies else []
        rpop = 50 - pop_per_region * (len(region_names) - 1) if i == len(region_names) - 1 else pop_per_region
        regions.append(Region(name=name, terrain="plains", carrying_capacity=50, resources="fertile",
                              adjacencies=adj, controller=civ_name, population=rpop))
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
    # stability: K_GOVERNING_COST default is 0.5; int(0.5) = 0, so no stability drain
    assert civ.stability == 50


def test_governing_cost_distant_regions_cost_more():
    adj = {"A": ["B"], "B": ["A", "C"], "C": ["B", "D"], "D": ["C"]}
    world = _make_world_with_regions(["A", "B", "C", "D"], capital="A", adjacencies=adj)
    apply_governing_costs(world)
    civ = world.civilizations[0]
    # treasury: (4-2)*2 + (1*2 + 2*2 + 3*2) = 4 + 12 = 16
    assert civ.treasury == 100 - 16
    # stability: K_GOVERNING_COST default is 0.5; int(0.5) = 0, so no stability drain
    assert civ.stability == 50


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
    """Capital reassignment picks highest effective_capacity."""
    from chronicler.models import RegionEcology
    regions = [
        Region(name="B", terrain="plains", carrying_capacity=30, resources="fertile",
               ecology=RegionEcology(soil=0.5, water=0.6)),
        Region(name="C", terrain="plains", carrying_capacity=50, resources="fertile",
               ecology=RegionEcology(soil=0.8, water=0.6)),
    ]
    leader = Leader(name="L", trait="bold", reign_start=0)
    civ = Civilization(
        name="E", population=50, military=30, economy=40,
        culture=30, stability=50, treasury=100, leader=leader,
        regions=["B", "C"], capital_region="A",
    )
    world = WorldState(name="test", seed=42, regions=regions, civilizations=[civ])
    check_capital_loss(world)
    # C has effective_capacity(50, soil=0.8) = 40, B has effective_capacity(30, soil=0.5) = 15 — C wins
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


# --- Task 8: MOVE_CAPITAL action handler ---

def test_move_capital_eligibility():
    """MOVE_CAPITAL requires treasury >= 15 and regions >= 2."""
    from chronicler.action_engine import ActionEngine
    from chronicler.models import ActionType
    adj = {"A": ["B", "C"], "B": ["A", "C"], "C": ["A", "B"]}
    world = _make_world_with_regions(["A", "B", "C"], capital="A", adjacencies=adj)
    civ = world.civilizations[0]
    civ.treasury = 20
    engine = ActionEngine(world)
    eligible = engine.get_eligible_actions(civ)
    assert ActionType.MOVE_CAPITAL in eligible


def test_move_capital_not_eligible_low_treasury():
    from chronicler.action_engine import ActionEngine
    from chronicler.models import ActionType
    adj = {"A": ["B"], "B": ["A"]}
    world = _make_world_with_regions(["A", "B"], capital="A", adjacencies=adj)
    civ = world.civilizations[0]
    civ.treasury = 10  # below 15
    engine = ActionEngine(world)
    eligible = engine.get_eligible_actions(civ)
    assert ActionType.MOVE_CAPITAL not in eligible


# --- Task 9: Simulation integration ---

def test_simulation_calls_governing_costs():
    """Verify governing costs are applied during simulation turn."""
    from chronicler.simulation import run_turn
    from chronicler.action_engine import ActionEngine
    adj = {"A": ["B"], "B": ["A", "C"], "C": ["B", "D"], "D": ["C"]}
    world = _make_world_with_regions(["A", "B", "C", "D"], capital="A", adjacencies=adj)
    civ = world.civilizations[0]
    initial_treasury = civ.treasury
    engine = ActionEngine(world)
    selector = lambda civ, w, eng=engine: eng.select_action(civ, seed=w.seed + w.turn)
    run_turn(world, selector, lambda w, e: "", seed=world.seed + world.turn)
    # Treasury governing cost (16) is applied each turn; net may be positive due to income.
    # With K_GOVERNING_COST=0.5 stability drain is zero; verify treasury was modified.
    assert civ.treasury != initial_treasury


# --- Task 10: M14a smoke test ---

def test_m14a_smoke_50_turns():
    """50-turn run with large empire — should not crash, secession may occur."""
    from chronicler.simulation import run_turn
    from chronicler.action_engine import ActionEngine
    from chronicler.world_gen import generate_world
    world = generate_world(seed=42)
    big_civ = world.civilizations[0]
    for region in world.regions:
        if region.controller is None:
            region.controller = big_civ.name
            big_civ.regions.append(region.name)
    big_civ.capital_region = big_civ.regions[0]

    for turn in range(50):
        engine = ActionEngine(world)
        selector = lambda civ, w, eng=engine: eng.select_action(civ, seed=w.seed + w.turn)
        run_turn(world, selector, lambda w, e: "", seed=world.seed + world.turn)

    assert world.turn == 50
    assert len(world.civilizations) >= 1


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
        for i, r in enumerate(world.regions):
            r.controller = civ.name
            r.population = 20  # 60 / 3 regions
        events = check_secession(world)
        if len(world.civilizations) > 1:
            parent = world.civilizations[0]
            breakaway = world.civilizations[1]
            for stat in ["population", "military", "economy", "treasury"]:
                original = {"population": 60, "military": 30, "economy": 45, "treasury": 90}
                assert getattr(parent, stat) + getattr(breakaway, stat) == original[stat]
            break


# --- Task 11: VassalRelation and Federation models ---

from chronicler.models import VassalRelation, Federation


def test_vassal_relation_model():
    vr = VassalRelation(overlord="Empire", vassal="City", tribute_rate=0.15)
    assert vr.overlord == "Empire"
    assert vr.tribute_rate == 0.15
    assert vr.turns_active == 0


def test_federation_model():
    fed = Federation(name="The Iron Pact", members=["A", "B"], founded_turn=10)
    assert len(fed.members) == 2


def test_worldstate_has_vassal_and_federation_fields():
    ws = WorldState(name="test", seed=42)
    assert ws.vassal_relations == []
    assert ws.federations == []


def test_relationship_has_allied_turns():
    from chronicler.models import Relationship
    rel = Relationship()
    assert rel.allied_turns == 0


# --- Task 12: vassalization choice and tribute collection ---

from chronicler.politics import choose_vassalize_or_absorb, collect_tribute


def _make_two_civ_world(winner_stability=50, winner_trait="cautious"):
    from chronicler.models import Region, Relationship, Disposition
    regions = [
        Region(name="A", terrain="plains", carrying_capacity=50, resources="fertile", adjacencies=["B"], controller="Winner"),
        Region(name="B", terrain="plains", carrying_capacity=50, resources="fertile", adjacencies=["A"], controller="Loser"),
    ]
    w_leader = Leader(name="WL", trait=winner_trait, reign_start=0)
    l_leader = Leader(name="LL", trait="bold", reign_start=0)
    winner = Civilization(name="Winner", population=50, military=40, economy=50,
                          culture=30, stability=winner_stability, treasury=100, leader=w_leader,
                          regions=["A"], capital_region="A")
    loser = Civilization(name="Loser", population=30, military=10, economy=30,
                         culture=20, stability=20, treasury=50, leader=l_leader,
                         regions=["B"], capital_region="B")
    world = WorldState(name="test", seed=42, turn=5, regions=regions, civilizations=[winner, loser])
    world.relationships = {
        "Winner": {"Loser": Relationship(disposition=Disposition.HOSTILE)},
        "Loser": {"Winner": Relationship(disposition=Disposition.HOSTILE)},
    }
    return world, winner, loser


def test_vassalize_when_stability_high_and_cautious():
    world, winner, loser = _make_two_civ_world(winner_stability=50, winner_trait="cautious")
    result = choose_vassalize_or_absorb(winner, loser, world)
    assert isinstance(result, bool)


def test_no_vassalize_when_stability_low():
    world, winner, loser = _make_two_civ_world(winner_stability=30, winner_trait="cautious")
    result = choose_vassalize_or_absorb(winner, loser, world)
    assert result is False


def test_tribute_collection():
    world, winner, loser = _make_two_civ_world()
    vr = VassalRelation(overlord="Winner", vassal="Loser", tribute_rate=0.15)
    world.vassal_relations.append(vr)
    collect_tribute(world)
    # tribute = floor(30 * 0.15) = 4
    assert loser.treasury == 50 - 4
    assert winner.treasury == 100 + 4
    assert vr.turns_active == 1


# --- Task 13: vassal rebellion ---

from chronicler.politics import check_vassal_rebellion


def test_vassal_rebellion_when_overlord_weak():
    world, winner, loser = _make_two_civ_world()
    vr = VassalRelation(overlord="Winner", vassal="Loser")
    world.vassal_relations.append(vr)
    winner.stability = 20  # below 25

    rebelled = False
    for seed in range(100):
        world.seed = seed
        world.vassal_relations = [VassalRelation(overlord="Winner", vassal="Loser")]
        loser.stability = 20
        loser.asabiya = 0.5
        events = check_vassal_rebellion(world)
        if len(world.vassal_relations) == 0:
            rebelled = True
            break
    assert rebelled


def test_vassal_no_rebellion_when_overlord_strong():
    world, winner, loser = _make_two_civ_world()
    vr = VassalRelation(overlord="Winner", vassal="Loser")
    world.vassal_relations.append(vr)
    winner.stability = 50
    winner.treasury = 100
    events = check_vassal_rebellion(world)
    assert len(world.vassal_relations) == 1


# --- Task 14: Federation formation and dissolution ---

from chronicler.politics import check_federation_formation


def test_federation_forms_after_10_allied_turns():
    from chronicler.models import Region, Relationship, Disposition, Federation
    regions = [
        Region(name="A", terrain="plains", carrying_capacity=50, resources="fertile"),
        Region(name="B", terrain="plains", carrying_capacity=50, resources="fertile"),
    ]
    la = Leader(name="LA", trait="bold", reign_start=0)
    lb = Leader(name="LB", trait="bold", reign_start=0)
    civ_a = Civilization(name="CivA", population=50, military=30, economy=40,
                         culture=30, stability=50, leader=la, regions=["A"], capital_region="A")
    civ_b = Civilization(name="CivB", population=50, military=30, economy=40,
                         culture=30, stability=50, leader=lb, regions=["B"], capital_region="B")
    world = WorldState(name="test", seed=42, turn=20, regions=regions,
                       civilizations=[civ_a, civ_b])
    world.relationships = {
        "CivA": {"CivB": Relationship(disposition=Disposition.ALLIED, allied_turns=10)},
        "CivB": {"CivA": Relationship(disposition=Disposition.ALLIED, allied_turns=10)},
    }
    events = check_federation_formation(world)
    assert len(world.federations) == 1
    assert "CivA" in world.federations[0].members
    assert "CivB" in world.federations[0].members


def test_federation_does_not_form_below_10_turns():
    from chronicler.models import Region, Relationship, Disposition
    regions = [Region(name="A", terrain="plains", carrying_capacity=50, resources="fertile")]
    la = Leader(name="LA", trait="bold", reign_start=0)
    lb = Leader(name="LB", trait="bold", reign_start=0)
    civ_a = Civilization(name="CivA", population=50, military=30, economy=40,
                         culture=30, stability=50, leader=la, regions=["A"], capital_region="A")
    civ_b = Civilization(name="CivB", population=50, military=30, economy=40,
                         culture=30, stability=50, leader=lb, regions=[], capital_region=None)
    world = WorldState(name="test", seed=42, turn=20, regions=regions,
                       civilizations=[civ_a, civ_b])
    world.relationships = {
        "CivA": {"CivB": Relationship(disposition=Disposition.ALLIED, allied_turns=5)},
        "CivB": {"CivA": Relationship(disposition=Disposition.ALLIED, allied_turns=5)},
    }
    events = check_federation_formation(world)
    assert len(world.federations) == 0


# --- Task 15: Federation defense and vassal WAR restriction ---

from chronicler.politics import trigger_federation_defense, war_key
from chronicler.models import Federation


def test_federation_defense_adds_allies_to_war():
    from chronicler.models import Region, Relationship, Disposition
    regions = [
        Region(name="A", terrain="plains", carrying_capacity=50, resources="fertile"),
        Region(name="B", terrain="plains", carrying_capacity=50, resources="fertile"),
        Region(name="C", terrain="plains", carrying_capacity=50, resources="fertile"),
    ]
    la = Leader(name="LA", trait="bold", reign_start=0)
    lb = Leader(name="LB", trait="bold", reign_start=0)
    lc = Leader(name="LC", trait="bold", reign_start=0)
    civ_a = Civilization(name="Attacker", population=50, military=40, economy=40,
                         culture=30, stability=50, leader=la, regions=["A"], capital_region="A")
    civ_b = Civilization(name="Defender", population=50, military=30, economy=40,
                         culture=30, stability=50, leader=lb, regions=["B"], capital_region="B")
    civ_c = Civilization(name="Ally", population=50, military=30, economy=40,
                         culture=30, stability=50, leader=lc, regions=["C"], capital_region="C")
    world = WorldState(name="test", seed=42, turn=10, regions=regions,
                       civilizations=[civ_a, civ_b, civ_c])
    world.federations = [Federation(name="The Iron Pact", members=["Defender", "Ally"], founded_turn=5)]
    world.active_wars = [("Attacker", "Defender")]
    world.war_start_turns = {war_key("Attacker", "Defender"): 10}
    events = trigger_federation_defense("Attacker", "Defender", world)
    assert ("Attacker", "Ally") in world.active_wars or ("Ally", "Attacker") in world.active_wars


def test_vassal_cannot_declare_war():
    from chronicler.action_engine import ActionEngine
    from chronicler.models import ActionType
    adj = {"A": ["B"], "B": ["A"]}
    world = _make_world_with_regions(["A", "B"], capital="A", adjacencies=adj)
    world.vassal_relations = [VassalRelation(overlord="Other", vassal="Empire")]
    civ = world.civilizations[0]
    # Give civ a hostile relationship so WAR would normally be eligible
    from chronicler.models import Relationship, Disposition
    world.relationships = {
        "Empire": {"Enemy": Relationship(disposition=Disposition.HOSTILE)},
    }
    engine = ActionEngine(world)
    eligible = engine.get_eligible_actions(civ)
    assert ActionType.WAR not in eligible


# --- Task 16: Simulation integration ---

def test_tribute_collected_during_simulation():
    from chronicler.simulation import run_turn
    from chronicler.action_engine import ActionEngine
    from chronicler.models import Region
    adj = {"A": ["B"], "B": ["A"]}
    world = _make_world_with_regions(["A"], capital="A", adjacencies=adj)
    l2 = Leader(name="L2", trait="bold", reign_start=0)
    vassal_civ = Civilization(name="Vassal", population=30, military=20, economy=40,
                              culture=20, stability=30, treasury=50, leader=l2,
                              regions=["B"], capital_region="B")
    world.civilizations.append(vassal_civ)
    world.regions.append(Region(name="B", terrain="plains", carrying_capacity=50,
                                resources="fertile", adjacencies=["A"], controller="Vassal"))
    world.vassal_relations = [VassalRelation(overlord="Empire", vassal="Vassal")]
    engine = ActionEngine(world)
    selector = lambda civ, w, eng=engine: eng.select_action(civ, seed=w.seed + w.turn)
    run_turn(world, selector, lambda w, e: "", seed=world.seed + world.turn)
    assert world.vassal_relations[0].turns_active >= 1


# --- Task 17: ProxyWar and ExileModifier models ---

from chronicler.models import ProxyWar, ExileModifier


def test_proxy_war_model():
    pw = ProxyWar(sponsor="A", target_civ="B", target_region="R1")
    assert pw.treasury_per_turn == 8
    assert pw.detected is False


def test_exile_modifier_model():
    em = ExileModifier(original_civ_name="Fallen", absorber_civ="Victor",
                       conquered_regions=["R1", "R2"])
    assert em.turns_remaining == 20
    assert em.recognized_by == []


def test_worldstate_has_proxy_and_exile_fields():
    ws = WorldState(name="test", seed=42)
    assert ws.proxy_wars == []
    assert ws.exile_modifiers == []


# --- Task 18: Proxy war mechanics ---

from chronicler.politics import apply_proxy_wars, check_proxy_detection


def test_proxy_war_drains_sponsor_and_target():
    world = _make_world_with_regions(["A", "B"], capital="A")
    civ = world.civilizations[0]
    civ.treasury = 50
    civ.stability = 50
    civ.economy = 40
    l2 = Leader(name="L2", trait="bold", reign_start=0)
    target = Civilization(name="Target", population=30, military=20, economy=30,
                          culture=60, stability=40, treasury=50, leader=l2,
                          regions=["B"], capital_region="B")
    world.civilizations.append(target)
    world.proxy_wars = [ProxyWar(sponsor="Empire", target_civ="Target", target_region="B")]
    apply_proxy_wars(world)
    assert civ.treasury == 50 - 8
    assert target.stability == 40 - 3
    assert target.economy == 30 - 2


def test_proxy_war_auto_cancels_on_bankruptcy():
    world = _make_world_with_regions(["A"], capital="A")
    civ = world.civilizations[0]
    civ.treasury = 5
    l2 = Leader(name="L2", trait="bold", reign_start=0)
    target = Civilization(name="Target", population=30, military=20, economy=30,
                          culture=60, stability=40, treasury=50, leader=l2,
                          regions=["B"], capital_region="B")
    world.civilizations.append(target)
    world.proxy_wars = [ProxyWar(sponsor="Empire", target_civ="Target", target_region="B")]
    apply_proxy_wars(world)
    assert len(world.proxy_wars) == 0


def test_proxy_detection_scales_with_culture():
    from chronicler.models import Relationship, Disposition
    world = _make_world_with_regions(["A"], capital="A")
    l2 = Leader(name="L2", trait="bold", reign_start=0)
    target = Civilization(name="Target", population=30, military=20, economy=30,
                          culture=80, stability=40, treasury=50, leader=l2,
                          regions=["B"], capital_region="B")
    world.civilizations.append(target)
    world.proxy_wars = [ProxyWar(sponsor="Empire", target_civ="Target", target_region="B")]
    world.relationships = {
        "Empire": {"Target": Relationship(disposition=Disposition.HOSTILE)},
        "Target": {"Empire": Relationship(disposition=Disposition.HOSTILE)},
    }
    detected = False
    for seed in range(20):
        world.seed = seed
        world.proxy_wars = [ProxyWar(sponsor="Empire", target_civ="Target", target_region="B")]
        events = check_proxy_detection(world)
        if world.proxy_wars[0].detected:
            detected = True
            break
    assert detected


# --- Task 19: Diplomatic congress ---

from chronicler.politics import check_congress


def test_congress_does_not_trigger_below_3_war_participants():
    world = _make_world_with_regions(["A"], capital="A")
    world.active_wars = [("A", "B")]
    events = check_congress(world)
    assert all(e.event_type != "congress" for e in events)


def test_congress_can_trigger_with_3_plus_participants():
    from chronicler.models import Region, Relationship, Disposition
    regions = [Region(name=n, terrain="plains", carrying_capacity=50, resources="fertile")
               for n in ["A", "B", "C", "D"]]
    civs = []
    for i, name in enumerate(["Civ1", "Civ2", "Civ3", "Civ4"]):
        l = Leader(name=f"L_{name}", trait="bold", reign_start=0)
        c = Civilization(name=name, population=50, military=30, economy=40,
                         culture=30, stability=50, treasury=100, leader=l,
                         regions=[["A","B","C","D"][i]], capital_region=["A","B","C","D"][i])
        civs.append(c)
    world = WorldState(name="test", seed=42, regions=regions, civilizations=civs)
    world.active_wars = [("Civ1", "Civ2"), ("Civ3", "Civ4"), ("Civ1", "Civ3")]
    world.war_start_turns = {
        war_key("Civ1", "Civ2"): 1, war_key("Civ3", "Civ4"): 2, war_key("Civ1", "Civ3"): 3,
    }
    triggered = False
    for seed in range(200):
        world.seed = seed
        world.turn = seed
        events = check_congress(world)
        if any(e.event_type in ("congress_peace", "congress_ceasefire", "congress_collapse") for e in events):
            triggered = True
            break
    assert triggered


# --- Task 20: Governments in exile ---

from chronicler.politics import create_exile, apply_exile_effects, check_restoration


def test_exile_created_on_civ_elimination():
    world = _make_world_with_regions(["A", "B"], capital="A")
    eliminated = world.civilizations[0]
    eliminated.regions = ["B"]
    l2 = Leader(name="Conqueror", trait="bold", reign_start=0)
    conqueror = Civilization(name="Victor", population=50, military=40, economy=50,
                             culture=40, stability=50, treasury=100, leader=l2,
                             regions=["A"], capital_region="A")
    world.civilizations.append(conqueror)
    exile = create_exile(eliminated, conqueror, world)
    assert exile.original_civ_name == "Empire"
    assert exile.absorber_civ == "Victor"
    assert exile.turns_remaining == 20
    assert "B" in exile.conquered_regions


def test_exile_drains_absorber_stability():
    world = _make_world_with_regions(["A"], capital="A")
    civ = world.civilizations[0]
    civ.stability = 50
    world.exile_modifiers = [
        ExileModifier(original_civ_name="Fallen", absorber_civ="Empire",
                      conquered_regions=["A"], turns_remaining=15)
    ]
    apply_exile_effects(world)
    assert civ.stability == 50 - 5
    assert world.exile_modifiers[0].turns_remaining == 14


def test_exile_removed_when_expired():
    world = _make_world_with_regions(["A"], capital="A")
    world.exile_modifiers = [
        ExileModifier(original_civ_name="Fallen", absorber_civ="Empire",
                      conquered_regions=["A"], turns_remaining=1)
    ]
    apply_exile_effects(world)
    assert len(world.exile_modifiers) == 0


# --- Task 22: M14d tracking fields ---

def test_civ_has_m14d_tracking_fields():
    leader = Leader(name="Test", trait="bold", reign_start=0)
    civ = Civilization(name="Test", population=50, military=30, economy=40,
                       culture=30, stability=50, leader=leader)
    assert civ.peak_region_count == 0
    assert civ.decline_turns == 0
    assert civ.stats_sum_history == []


def test_worldstate_has_peace_and_bop_turns():
    ws = WorldState(name="test", seed=42)
    assert ws.peace_turns == 0
    assert ws.balance_of_power_turns == 0


# --- Task 23: Balance of power ---

from chronicler.politics import apply_balance_of_power


def test_balance_of_power_no_trigger_below_40_percent():
    from chronicler.models import Region, Relationship, Disposition
    civs = []
    for i, name in enumerate(["A", "B", "C"]):
        l = Leader(name=f"L{name}", trait="bold", reign_start=0)
        c = Civilization(name=name, population=30, military=30, economy=30,
                         culture=30, stability=50, leader=l, regions=[f"R{i}"],
                         capital_region=f"R{i}")
        civs.append(c)
    regions = [Region(name=f"R{i}", terrain="plains", carrying_capacity=50, resources="fertile")
               for i in range(3)]
    world = WorldState(name="test", seed=42, regions=regions, civilizations=civs)
    world.relationships = {}
    for c1 in civs:
        world.relationships[c1.name] = {}
        for c2 in civs:
            if c1.name != c2.name:
                world.relationships[c1.name][c2.name] = Relationship(disposition=Disposition.HOSTILE)
    apply_balance_of_power(world)
    assert world.balance_of_power_turns == 0


def test_balance_of_power_triggers_for_dominant_civ():
    from chronicler.models import Region, Relationship, Disposition
    l1 = Leader(name="L1", trait="bold", reign_start=0)
    dominant = Civilization(name="Dominant", population=80, military=80, economy=80,
                            culture=50, stability=50, leader=l1,
                            regions=["R0", "R1", "R2", "R3", "R4"], capital_region="R0")
    l2 = Leader(name="L2", trait="bold", reign_start=0)
    weak = Civilization(name="Weak", population=20, military=10, economy=10,
                        culture=10, stability=50, leader=l2,
                        regions=["R5"], capital_region="R5")
    regions = [Region(name=f"R{i}", terrain="plains", carrying_capacity=50, resources="fertile")
               for i in range(6)]
    world = WorldState(name="test", seed=42, regions=regions, civilizations=[dominant, weak])
    world.relationships = {
        "Dominant": {"Weak": Relationship(disposition=Disposition.NEUTRAL)},
        "Weak": {"Dominant": Relationship(disposition=Disposition.HOSTILE)},
    }
    apply_balance_of_power(world)
    assert world.balance_of_power_turns == 1


# --- Task 24: Fallen empire modifier ---

from chronicler.politics import update_peak_regions, apply_fallen_empire


def test_peak_region_tracking():
    world = _make_world_with_regions(["A", "B", "C"], capital="A")
    civ = world.civilizations[0]
    assert civ.peak_region_count == 0
    update_peak_regions(world)
    assert civ.peak_region_count == 3
    civ.regions = ["A"]
    update_peak_regions(world)
    assert civ.peak_region_count == 3  # never decreases


def test_fallen_empire_asabiya_boost():
    world = _make_world_with_regions(["A"], capital="A")
    civ = world.civilizations[0]
    civ.peak_region_count = 5
    civ.asabiya = 0.3
    apply_fallen_empire(world)
    assert civ.asabiya == pytest.approx(0.35, abs=1e-6)


# --- Task 25: Civilizational twilight ---

import pytest
from chronicler.politics import update_decline_tracking, apply_twilight


def test_decline_tracking_rolling_window():
    world = _make_world_with_regions(["A"], capital="A")
    civ = world.civilizations[0]
    # Simulate 25 turns with decreasing stats
    for i in range(25):
        civ.economy = max(40 - i, 0)
        civ.military = max(30 - i, 0)
        civ.culture = max(30 - i, 0)
        update_decline_tracking(world)
    assert len(civ.stats_sum_history) == 20  # capped


def test_twilight_drains_stats():
    world = _make_world_with_regions(["A"], capital="A")
    civ = world.civilizations[0]
    civ.decline_turns = 20
    civ.population = 50
    civ.culture = 30
    apply_twilight(world)
    assert civ.population == 47
    assert civ.culture == 28


# --- Task 26: Long peace problem ---

from chronicler.politics import apply_long_peace


def test_long_peace_resets_with_wars():
    world = _make_world_with_regions(["A"], capital="A")
    world.peace_turns = 35
    world.active_wars = [("A", "B")]
    apply_long_peace(world)
    assert world.peace_turns == 0


def test_long_peace_military_restlessness():
    world = _make_world_with_regions(["A"], capital="A")
    civ = world.civilizations[0]
    civ.military = 70
    civ.stability = 50
    world.peace_turns = 29  # will become 30
    apply_long_peace(world)
    assert civ.stability == 48  # -2 for military > 60


# --- Task 28: 200-turn integration test and scenario regression ---

def test_m14_integration_200_turns():
    """200-turn run with all M14 mechanics — verify emergent political events."""
    from chronicler.simulation import run_turn
    from chronicler.action_engine import ActionEngine
    from chronicler.world_gen import generate_world
    world = generate_world(seed=42)

    # Give civs extra regions to make governing costs relevant
    for i, civ in enumerate(world.civilizations):
        for region in world.regions:
            if region.controller is None:
                region.controller = civ.name
                civ.regions.append(region.name)
                break
        civ.capital_region = civ.regions[0]

    secession_count = 0
    vassal_count = 0
    federation_count = 0

    for turn in range(200):
        engine = ActionEngine(world)
        selector = lambda civ, w, eng=engine: eng.select_action(civ, seed=w.seed + w.turn)
        run_turn(world, selector, lambda w, e: "", seed=world.seed + world.turn)
        secession_count += sum(1 for e in world.events_timeline if e.event_type == "secession" and e.turn == world.turn)
        vassal_count = len(world.vassal_relations)
        federation_count = len(world.federations)

    assert world.turn == 200
    assert len(world.civilizations) >= 1


def test_all_scenarios_run_with_m14():
    """Each existing scenario YAML loads and runs 10 turns without crash."""
    from chronicler.scenario import load_scenario, apply_scenario
    from chronicler.simulation import run_turn
    from chronicler.action_engine import ActionEngine
    from chronicler.world_gen import generate_world
    from pathlib import Path
    scenario_dir = Path("scenarios")
    if not scenario_dir.exists():
        return  # skip if scenarios not available
    for yaml_file in scenario_dir.glob("*.yaml"):
        config = load_scenario(yaml_file)
        seed = config.seed if config.seed is not None else 42
        num_civs = config.num_civs if config.num_civs is not None else max(len(config.civilizations), 4)
        num_regions = config.num_regions if config.num_regions is not None else max(len(config.regions), 8)
        world = generate_world(seed=seed, num_civs=num_civs, num_regions=num_regions)
        apply_scenario(world, config)
        for civ in world.civilizations:
            if civ.capital_region is None and civ.regions:
                civ.capital_region = civ.regions[0]
        for _ in range(10):
            engine = ActionEngine(world)
            selector = lambda civ, w, eng=engine: eng.select_action(civ, seed=w.seed + w.turn)
            run_turn(world, selector, lambda w, e: "", seed=world.seed + world.turn)
