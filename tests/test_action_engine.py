import pytest
from chronicler.models import (
    ActionType, Civilization, Disposition, Leader, Region, Relationship, TechEra, WorldState,
)
from chronicler.action_engine import ActionEngine


@pytest.fixture
def engine_world():
    civ1 = Civilization(
        name="Civ A", population=5, military=5, economy=5, culture=5,
        stability=5, tech_era=TechEra.IRON, treasury=15,
        leader=Leader(name="Vaelith", trait="aggressive", reign_start=0),
        regions=["Region A", "Region B"], domains=["warfare"],
    )
    civ2 = Civilization(
        name="Civ B", population=5, military=5, economy=5, culture=5,
        stability=5, tech_era=TechEra.IRON, treasury=15,
        leader=Leader(name="Gorath", trait="cautious", reign_start=0),
        regions=["Region C"], domains=["commerce"],
    )
    return WorldState(
        name="Test", seed=42, turn=5,
        regions=[
            Region(name="Region A", terrain="plains", carrying_capacity=8, resources="fertile", controller="Civ A"),
            Region(name="Region B", terrain="forest", carrying_capacity=6, resources="timber", controller="Civ A"),
            Region(name="Region C", terrain="coast", carrying_capacity=7, resources="maritime", controller="Civ B"),
            Region(name="Region D", terrain="plains", carrying_capacity=5, resources="fertile"),
        ],
        civilizations=[civ1, civ2],
        relationships={
            "Civ A": {"Civ B": Relationship(disposition=Disposition.HOSTILE)},
            "Civ B": {"Civ A": Relationship(disposition=Disposition.HOSTILE)},
        },
    )


class TestEligibility:
    def test_expand_requires_unclaimed_regions(self, engine_world):
        engine = ActionEngine(engine_world)
        for r in engine_world.regions:
            r.controller = "Civ A"
        assert ActionType.EXPAND not in engine.get_eligible_actions(engine_world.civilizations[0])

    def test_expand_requires_military(self, engine_world):
        engine = ActionEngine(engine_world)
        engine_world.civilizations[0].military = 2
        assert ActionType.EXPAND not in engine.get_eligible_actions(engine_world.civilizations[0])

    def test_war_requires_hostile_neighbor(self, engine_world):
        engine = ActionEngine(engine_world)
        engine_world.relationships["Civ A"]["Civ B"].disposition = Disposition.FRIENDLY
        assert ActionType.WAR not in engine.get_eligible_actions(engine_world.civilizations[0])

    def test_trade_requires_bronze_era(self, engine_world):
        engine = ActionEngine(engine_world)
        engine_world.civilizations[0].tech_era = TechEra.TRIBAL
        assert ActionType.TRADE not in engine.get_eligible_actions(engine_world.civilizations[0])

    def test_trade_requires_neutral_plus_partner(self, engine_world):
        engine = ActionEngine(engine_world)
        assert ActionType.TRADE not in engine.get_eligible_actions(engine_world.civilizations[0])

    def test_develop_always_eligible(self, engine_world):
        assert ActionType.DEVELOP in ActionEngine(engine_world).get_eligible_actions(engine_world.civilizations[0])

    def test_diplomacy_always_eligible(self, engine_world):
        assert ActionType.DIPLOMACY in ActionEngine(engine_world).get_eligible_actions(engine_world.civilizations[0])


class TestPersonalityWeights:
    def test_aggressive_favors_war(self, engine_world):
        w = ActionEngine(engine_world).compute_weights(engine_world.civilizations[0])
        assert w[ActionType.WAR] > w[ActionType.DEVELOP]

    def test_cautious_favors_develop(self, engine_world):
        engine_world.relationships["Civ B"]["Civ A"].disposition = Disposition.NEUTRAL
        w = ActionEngine(engine_world).compute_weights(engine_world.civilizations[1])
        assert w[ActionType.DEVELOP] > w[ActionType.WAR]

    def test_stubborn_boosts_last_action(self, engine_world):
        civ = engine_world.civilizations[0]
        civ.leader.trait = "stubborn"
        engine_world.action_history["Civ A"] = ["develop"]
        w = ActionEngine(engine_world).compute_weights(civ)
        assert w[ActionType.DEVELOP] > w[ActionType.WAR]


class TestSituationalOverrides:
    def test_low_stability_boosts_diplomacy(self, engine_world):
        civ = engine_world.civilizations[0]
        civ.stability = 2
        w = ActionEngine(engine_world).compute_weights(civ)
        assert w[ActionType.DIPLOMACY] > w[ActionType.WAR]

    def test_high_military_hostile_boosts_war(self, engine_world):
        civ = engine_world.civilizations[0]
        civ.military = 8
        w = ActionEngine(engine_world).compute_weights(civ)
        assert w[ActionType.WAR] > w[ActionType.DIPLOMACY]

    def test_low_treasury_suppresses_develop(self, engine_world):
        civ = engine_world.civilizations[0]
        civ.treasury = 2
        w = ActionEngine(engine_world).compute_weights(civ)
        assert w[ActionType.DEVELOP] < 0.2 * 0.5


class TestStreakBreaker:
    def test_streak_of_3_zeroes_action(self, engine_world):
        engine_world.action_history["Civ A"] = ["develop", "develop", "develop"]
        w = ActionEngine(engine_world).compute_weights(engine_world.civilizations[0])
        assert w[ActionType.DEVELOP] == 0.0

    def test_stubborn_streak_breaks_at_5(self, engine_world):
        civ = engine_world.civilizations[0]
        civ.leader.trait = "stubborn"
        engine_world.action_history["Civ A"] = ["develop", "develop", "develop"]
        w = ActionEngine(engine_world).compute_weights(civ)
        assert w[ActionType.DEVELOP] > 0.0
        engine_world.action_history["Civ A"] = ["develop"] * 5
        w = ActionEngine(engine_world).compute_weights(civ)
        assert w[ActionType.DEVELOP] == 0.0


class TestSelection:
    def test_deterministic(self, engine_world):
        engine = ActionEngine(engine_world)
        civ = engine_world.civilizations[0]
        assert engine.select_action(civ, seed=42) == engine.select_action(civ, seed=42)

    def test_returns_valid_action_type(self, engine_world):
        assert isinstance(ActionEngine(engine_world).select_action(engine_world.civilizations[0], seed=42), ActionType)

    def test_all_ineligible_falls_back_to_develop(self, engine_world):
        civ = engine_world.civilizations[0]
        civ.military = 1
        civ.tech_era = TechEra.TRIBAL
        for r in engine_world.regions:
            r.controller = "Civ A"
        engine_world.relationships["Civ A"]["Civ B"].disposition = Disposition.FRIENDLY
        action = ActionEngine(engine_world).select_action(civ, seed=42)
        assert action in [ActionType.DEVELOP, ActionType.DIPLOMACY]


class TestSecondaryTrait:
    def test_secondary_trait_boosts_action(self, engine_world):
        civ = engine_world.civilizations[0]
        civ.leader.secondary_trait = "warlike"
        w_with = ActionEngine(engine_world).compute_weights(civ)
        civ.leader.secondary_trait = None
        w_without = ActionEngine(engine_world).compute_weights(civ)
        assert w_with[ActionType.WAR] > w_without[ActionType.WAR]


class TestRivalryBoost:
    def test_rivalry_boosts_war_against_rival(self, engine_world):
        civ = engine_world.civilizations[0]
        civ.leader.rival_leader = "Gorath"
        civ.leader.rival_civ = "Civ B"
        w_with = ActionEngine(engine_world).compute_weights(civ)
        civ.leader.rival_leader = None
        civ.leader.rival_civ = None
        w_without = ActionEngine(engine_world).compute_weights(civ)
        assert w_with[ActionType.WAR] > w_without[ActionType.WAR]
