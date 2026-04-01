import pytest
from chronicler.models import (
    ActionType, Civilization, Disposition, Leader, Region, Relationship, TechEra, WorldState,
)
from chronicler.action_engine import ActionEngine, resolve_action, resolve_war
from chronicler.tuning import K_WAR_DAMPER_THRESHOLD, K_WAR_DAMPER_FLOOR


@pytest.fixture
def engine_world():
    civ1 = Civilization(
        name="Civ A", population=50, military=50, economy=50, culture=50,
        stability=50, tech_era=TechEra.IRON, treasury=150,
        leader=Leader(name="Vaelith", trait="aggressive", reign_start=0),
        regions=["Region A", "Region B"], domains=["warfare"],
    )
    civ2 = Civilization(
        name="Civ B", population=50, military=50, economy=50, culture=50,
        stability=50, tech_era=TechEra.IRON, treasury=150,
        leader=Leader(name="Gorath", trait="cautious", reign_start=0),
        regions=["Region C"], domains=["commerce"],
    )
    return WorldState(
        name="Test", seed=42, turn=5,
        regions=[
            Region(name="Region A", terrain="plains", carrying_capacity=80, resources="fertile", controller="Civ A"),
            Region(name="Region B", terrain="forest", carrying_capacity=60, resources="timber", controller="Civ A"),
            Region(name="Region C", terrain="coast", carrying_capacity=70, resources="maritime", controller="Civ B"),
            Region(name="Region D", terrain="plains", carrying_capacity=50, resources="fertile"),
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
        engine_world.civilizations[0].military = 20
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

    def test_embargo_preserves_relationship_iteration_tiebreak(self):
        civ_a = Civilization(
            name="Civ A", population=50, military=50, economy=50, culture=50,
            stability=50, tech_era=TechEra.IRON, treasury=150,
            leader=Leader(name="Vaelith", trait="aggressive", reign_start=0),
            regions=["Region A"],
        )
        civ_b = Civilization(
            name="Civ B", population=50, military=50, economy=50, culture=50,
            stability=50, tech_era=TechEra.IRON, treasury=150,
            leader=Leader(name="Gorath", trait="cautious", reign_start=0),
            regions=["Region B"],
        )
        civ_c = Civilization(
            name="Civ C", population=50, military=50, economy=50, culture=50,
            stability=50, tech_era=TechEra.IRON, treasury=150,
            leader=Leader(name="Selene", trait="bold", reign_start=0),
            regions=["Region C"],
        )
        world = WorldState(
            name="TieBreak", seed=42, turn=5,
            regions=[
                Region(name="Region A", terrain="plains", carrying_capacity=80, resources="fertile", controller="Civ A"),
                Region(name="Region B", terrain="forest", carrying_capacity=60, resources="timber", controller="Civ B"),
                Region(name="Region C", terrain="coast", carrying_capacity=70, resources="maritime", controller="Civ C"),
            ],
            civilizations=[civ_a, civ_b, civ_c],
            relationships={
                "Civ A": {
                    "Civ C": Relationship(disposition=Disposition.HOSTILE),
                    "Civ B": Relationship(disposition=Disposition.HOSTILE),
                },
                "Civ B": {"Civ A": Relationship(disposition=Disposition.HOSTILE)},
                "Civ C": {"Civ A": Relationship(disposition=Disposition.HOSTILE)},
            },
        )

        event = resolve_action(civ_a, ActionType.EMBARGO, world)

        assert event.event_type == "embargo"
        assert event.actors == ["Civ A", "Civ C"]

    def test_expand_marks_empty_region_for_stockpile_bootstrap(self, engine_world):
        civ = engine_world.civilizations[0]
        frontier = next(r for r in engine_world.regions if r.name == "Region D")
        frontier.population = 0
        frontier.resource_types[0] = 3  # fish

        resolve_action(civ, ActionType.EXPAND, engine_world)

        assert frontier.controller == civ.name
        assert getattr(frontier, "_stockpile_bootstrap_pending", False) is True


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
        # M47d: Use cautious leader — aggressive trait overwhelms situational signal with smooth damper.
        # Test intent: low stability triggers DIPLOMACY * 3.0 boost that wins over WAR for a non-aggressive leader.
        civ = engine_world.civilizations[0]
        civ.leader.trait = "cautious"
        civ.stability = 20
        w = ActionEngine(engine_world).compute_weights(civ)
        assert w[ActionType.DIPLOMACY] > w[ActionType.WAR]

    def test_high_military_hostile_boosts_war(self, engine_world):
        civ = engine_world.civilizations[0]
        civ.military = 80
        w = ActionEngine(engine_world).compute_weights(civ)
        assert w[ActionType.WAR] > w[ActionType.DIPLOMACY]

    def test_low_treasury_suppresses_develop(self, engine_world):
        civ = engine_world.civilizations[0]
        civ.treasury = 20
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
        civ.military = 10
        civ.tech_era = TechEra.TRIBAL
        civ.treasury = 5  # Below BUILD threshold of 10
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


class TestWarDamper:
    """M47d: Smooth WAR damper replaces binary cliff."""

    def test_high_stability_no_penalty(self, engine_world):
        """Stability >= threshold: WAR weight unchanged."""
        civ = engine_world.civilizations[0]
        civ.stability = 50
        engine = ActionEngine(engine_world)
        weights = engine.compute_weights(civ)
        assert weights[ActionType.WAR] > 0

    def test_mid_stability_partial_damper(self, engine_world):
        """Stability at half threshold: WAR weight halved relative to undampened."""
        civ = engine_world.civilizations[0]
        civ.stability = 25  # half of threshold 50
        engine = ActionEngine(engine_world)
        weights_low = engine.compute_weights(civ)

        civ.stability = 80  # well above threshold
        weights_high = engine.compute_weights(civ)

        ratio = weights_low[ActionType.WAR] / weights_high[ActionType.WAR]
        assert 0.45 <= ratio <= 0.55, f"Expected ~0.5 ratio, got {ratio}"

    def test_zero_stability_uses_floor(self, engine_world):
        """Stability 0: WAR weight at floor, not zero."""
        civ = engine_world.civilizations[0]
        civ.stability = 0
        engine = ActionEngine(engine_world)
        weights = engine.compute_weights(civ)
        assert weights[ActionType.WAR] > 0, "WAR should not be zero at stability 0"

    def test_damper_does_not_amplify(self, engine_world):
        """Stability above threshold should NOT boost WAR weight."""
        civ = engine_world.civilizations[0]
        engine = ActionEngine(engine_world)

        civ.stability = 50  # at threshold
        weights_at_threshold = engine.compute_weights(civ)

        civ.stability = 90
        weights_above = engine.compute_weights(civ)

        assert abs(weights_at_threshold[ActionType.WAR] - weights_above[ActionType.WAR]) < 0.001

    def test_diplomacy_boost_unchanged(self, engine_world):
        """DIPLOMACY *= 3.0 still fires at stability <= 20."""
        civ = engine_world.civilizations[0]
        civ.stability = 15
        engine = ActionEngine(engine_world)
        weights = engine.compute_weights(civ)
        assert weights[ActionType.DIPLOMACY] > weights[ActionType.DEVELOP]


class TestWarResolution:
    def test_hybrid_conquest_realigns_conquered_region_agents(self, engine_world):
        class _FakeBridge:
            def __init__(self):
                self.calls = []

            def realign_region_agents_to_civ(self, **kwargs):
                self.calls.append(kwargs)
                return {101}

        attacker = engine_world.civilizations[0]
        defender = engine_world.civilizations[1]
        attacker.military = 100
        defender.military = 10
        engine_world.agent_mode = "hybrid"
        bridge = _FakeBridge()
        engine_world._agent_bridge = bridge

        result = resolve_war(attacker, defender, engine_world, seed=0)

        assert result.outcome == "attacker_wins"
        assert bridge.calls == [{
            "world": engine_world,
            "region_names": {"Region C"},
            "old_civ_id": 1,
            "new_civ_id": 0,
        }]


class TestWarWeariness:
    """M47d: War-weariness suppresses WAR weight."""

    def test_zero_weariness_no_penalty(self, engine_world):
        """No weariness: WAR weight unaffected."""
        civ = engine_world.civilizations[0]
        civ.war_weariness = 0.0
        engine = ActionEngine(engine_world)
        weights_zero = engine.compute_weights(civ)

        civ.war_weariness = 5.0
        weights_weary = engine.compute_weights(civ)
        assert weights_zero[ActionType.WAR] > weights_weary[ActionType.WAR]

    def test_high_weariness_suppresses_war(self, engine_world):
        """Chronic warmonger weariness (~23): WAR heavily suppressed."""
        civ = engine_world.civilizations[0]
        civ.stability = 50
        engine = ActionEngine(engine_world)

        civ.war_weariness = 0.0
        war_fresh = engine.compute_weights(civ)[ActionType.WAR]

        civ.war_weariness = 23.0
        war_weary = engine.compute_weights(civ)[ActionType.WAR]

        ratio = war_weary / war_fresh
        # With divisor 0.5: 1/(1+23/0.5) = 0.021
        assert ratio < 0.05, f"Expected heavy suppression, got {ratio}"

    def test_weariness_does_not_affect_other_actions(self, engine_world):
        """Weariness only touches WAR, not DEVELOP or TRADE."""
        civ = engine_world.civilizations[0]
        civ.stability = 50
        engine = ActionEngine(engine_world)

        civ.war_weariness = 0.0
        weights_fresh = engine.compute_weights(civ)

        civ.war_weariness = 10.0
        weights_weary = engine.compute_weights(civ)

        assert abs(weights_fresh[ActionType.DEVELOP] - weights_weary[ActionType.DEVELOP]) < 0.001


class TestPeaceDividend:
    """M47d: Peace momentum boosts DEVELOP and TRADE weights."""

    def test_zero_momentum_no_bonus(self, engine_world):
        """No peace momentum: DEVELOP/TRADE unaffected."""
        civ = engine_world.civilizations[0]
        # Need NEUTRAL+ for TRADE to be eligible
        engine_world.relationships["Civ A"]["Civ B"].disposition = Disposition.NEUTRAL
        engine_world.relationships["Civ B"]["Civ A"].disposition = Disposition.NEUTRAL
        civ.peace_momentum = 0.0
        engine = ActionEngine(engine_world)
        weights = engine.compute_weights(civ)
        assert weights[ActionType.DEVELOP] > 0
        assert weights[ActionType.TRADE] > 0

    def test_high_momentum_boosts_develop_trade(self, engine_world):
        """20 turns of peace: DEVELOP and TRADE get significant bonus."""
        civ = engine_world.civilizations[0]
        civ.stability = 50
        # Need NEUTRAL+ for TRADE to be eligible
        engine_world.relationships["Civ A"]["Civ B"].disposition = Disposition.NEUTRAL
        engine_world.relationships["Civ B"]["Civ A"].disposition = Disposition.NEUTRAL
        engine = ActionEngine(engine_world)

        civ.peace_momentum = 0.0
        develop_base = engine.compute_weights(civ)[ActionType.DEVELOP]
        trade_base = engine.compute_weights(civ)[ActionType.TRADE]

        civ.peace_momentum = 20.0
        develop_peace = engine.compute_weights(civ)[ActionType.DEVELOP]
        trade_peace = engine.compute_weights(civ)[ActionType.TRADE]

        develop_ratio = develop_peace / develop_base
        trade_ratio = trade_peace / trade_base
        # With divisor 5.0: 1 + 20/5 = 5.0x bonus
        assert 4.5 <= develop_ratio <= 5.5, f"Expected ~5.0 DEVELOP ratio, got {develop_ratio}"
        assert 4.5 <= trade_ratio <= 5.5, f"Expected ~5.0 TRADE ratio, got {trade_ratio}"

    def test_momentum_does_not_affect_war(self, engine_world):
        """Peace momentum only touches DEVELOP/TRADE, not WAR."""
        civ = engine_world.civilizations[0]
        civ.stability = 50
        engine = ActionEngine(engine_world)

        civ.peace_momentum = 0.0
        war_base = engine.compute_weights(civ)[ActionType.WAR]

        civ.peace_momentum = 20.0
        war_peace = engine.compute_weights(civ)[ActionType.WAR]

        assert abs(war_base - war_peace) < 0.001


class TestWarFrequencyIntegration:
    """M47d: Verify all three mechanisms work together."""

    def test_combined_suppression(self, engine_world):
        """Low stability + high weariness + zero momentum = heavily suppressed WAR."""
        civ = engine_world.civilizations[0]
        civ.stability = 15
        civ.war_weariness = 10.0
        civ.peace_momentum = 0.0
        engine = ActionEngine(engine_world)
        weights = engine.compute_weights(civ)

        assert weights[ActionType.WAR] < weights[ActionType.DEVELOP]
        assert weights[ActionType.WAR] < weights[ActionType.DIPLOMACY]

    def test_peaceful_civ_prefers_develop(self, engine_world):
        """High stability + zero weariness + high momentum = DEVELOP/TRADE dominant.

        Uses cautious leader — aggressive trait overwhelms peace momentum for WAR-prone civs.
        NEUTRAL disposition required to make TRADE eligible.
        Test intent: peace momentum 3x boost wins over WAR for a non-aggressive leader.
        """
        civ = engine_world.civilizations[0]
        civ.leader.trait = "cautious"
        civ.stability = 50
        civ.war_weariness = 0.0
        civ.peace_momentum = 20.0
        engine_world.relationships["Civ A"]["Civ B"].disposition = Disposition.NEUTRAL
        engine_world.relationships["Civ B"]["Civ A"].disposition = Disposition.NEUTRAL
        engine = ActionEngine(engine_world)
        weights = engine.compute_weights(civ)

        assert weights[ActionType.DEVELOP] > weights[ActionType.WAR]
        assert weights[ActionType.TRADE] > weights[ActionType.WAR]

    def test_warmonger_still_can_fight(self, engine_world):
        """Even with high weariness, WAR is not zero — just suppressed."""
        civ = engine_world.civilizations[0]
        civ.stability = 50
        civ.war_weariness = 23.0
        civ.peace_momentum = 0.0
        engine = ActionEngine(engine_world)
        weights = engine.compute_weights(civ)
        assert weights[ActionType.WAR] > 0, "WAR should never be zero from weariness alone"


class TestResolvedActionBookkeeping:
    """M-AF1 #3: action_history and action_counts should record the resolved action, not the selected one."""

    def test_war_fallback_records_develop_in_history(self, engine_world):
        """WAR falling back to DEVELOP should record 'develop' in history and counts."""
        from chronicler.simulation import phase_action

        civ = engine_world.civilizations[0]
        # No hostile/suspicious target -- WAR will fall back to DEVELOP
        for name, rel in engine_world.relationships.get(civ.name, {}).items():
            rel.disposition = Disposition.FRIENDLY

        engine_world.action_history[civ.name] = []
        civ.action_counts = {}

        phase_action(engine_world, action_selector=lambda c, w: ActionType.WAR)

        # History and counts should record "develop", not "war"
        assert engine_world.action_history[civ.name][-1] == "develop", \
            f"Expected 'develop' in history, got {engine_world.action_history[civ.name][-1]}"
        assert civ.action_counts.get("develop", 0) > 0, "develop should be counted"
        assert civ.action_counts.get("war", 0) == 0, "war should NOT be counted when it fell back"
