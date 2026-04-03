import pytest
from chronicler.models import (
    ActionType, Belief, Civilization, Disposition, GreatPerson, InfrastructureType, Leader, PendingBuild, Region, Relationship, TechEra, WorldState,
)
from chronicler.action_engine import ActionEngine, WarResult, resolve_action, resolve_war, _resolve_war_action
from chronicler.tuning import K_WAR_DAMPER_THRESHOLD, K_WAR_DAMPER_FLOOR, K_WAR_WEARINESS_DIVISOR
from chronicler.utils import stable_hash_int


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

    def test_trade_defaults_missing_relationships_to_neutral(self, engine_world):
        engine = ActionEngine(engine_world)
        engine_world.relationships = {}
        assert ActionType.TRADE in engine.get_eligible_actions(engine_world.civilizations[0])

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

    def test_embargo_routes_target_penalty_as_shock_signal_in_accumulator_mode(self, engine_world):
        from chronicler.accumulator import StatAccumulator

        civ = engine_world.civilizations[0]
        acc = StatAccumulator()

        event = resolve_action(civ, ActionType.EMBARGO, engine_world, acc=acc)

        shocks = acc.to_shock_signals()
        demand_signals = acc.to_demand_signals({1: 10})

        assert event.event_type == "embargo"
        assert len(shocks) == 1
        assert shocks[0].civ_id == 1
        assert shocks[0].stability_shock < 0
        assert demand_signals == []


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

    def test_militant_faith_hostile_neighbor_boosts_war(self, engine_world):
        civ = engine_world.civilizations[0]
        rival = engine_world.civilizations[1]
        civ.leader.trait = "cautious"
        civ.traditions = []
        civ.military = 40
        civ.stability = 80
        civ.civ_majority_faith = 1
        rival.civ_majority_faith = 2
        engine_world.belief_registry = [
            Belief(faith_id=1, name="Militant", civ_origin=0, doctrines=[0, 0, 1, 0, 0]),
            Belief(faith_id=2, name="Peaceful", civ_origin=1, doctrines=[0, 0, -1, 0, 0]),
        ]

        holy_war_weights = ActionEngine(engine_world).compute_weights(civ)

        rival.civ_majority_faith = 1
        normal_weights = ActionEngine(engine_world).compute_weights(civ)

        assert holy_war_weights[ActionType.WAR] > normal_weights[ActionType.WAR]


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

    def test_zero_threshold_override_uses_floor(self, engine_world, monkeypatch):
        civ = engine_world.civilizations[0]
        civ.stability = 20

        def fake_get_override(world, key, default):
            if key == K_WAR_DAMPER_THRESHOLD:
                return 0.0
            return default

        monkeypatch.setattr("chronicler.action_engine.get_override", fake_get_override)
        weights = ActionEngine(engine_world).compute_weights(civ)
        assert weights[ActionType.WAR] > 0


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
        attacker.stability = 40  # Ensure absorption path (vassalization requires >40)
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

    def test_conquest_clears_pending_build(self, engine_world):
        attacker = engine_world.civilizations[0]
        defender = engine_world.civilizations[1]
        contested = engine_world.regions[2]
        attacker.military = 100
        defender.military = 10
        attacker.stability = 40
        contested.pending_build = PendingBuild(
            type=InfrastructureType.ROADS,
            builder_civ=defender.name,
            started_turn=1,
            turns_remaining=2,
        )

        result = resolve_war(attacker, defender, engine_world, seed=0)

        assert result.outcome == "attacker_wins"
        assert contested.pending_build is None

    @pytest.mark.parametrize("outcome,loser_idx,winner_idx", [
        ("attacker_wins", 1, 0),   # loser=defender(1), winner=attacker(0)
        ("defender_wins", 0, 1),   # loser=attacker(0), winner=defender(1)
    ])
    def test_war_capture_passes_bridge_to_capture_hostage(
        self, engine_world, monkeypatch, outcome, loser_idx, winner_idx,
    ):
        """_resolve_war_action passes world._agent_bridge on both war outcomes."""
        class _FakeSim:
            def __init__(self):
                self.calls = []
            def set_agent_civ(self, agent_id, civ_id):
                self.calls.append((agent_id, civ_id))

        class _FakeBridge:
            def __init__(self):
                self._sim = _FakeSim()

        # Give the loser a GP with agent_id so capture_hostage has a candidate
        loser = engine_world.civilizations[loser_idx]
        gp = GreatPerson(
            name="Capturable", role="general", trait="bold",
            civilization=loser.name, origin_civilization=loser.name,
            born_turn=5, agent_id=99,
        )
        loser.great_persons = [gp]

        monkeypatch.setattr("chronicler.action_engine.resolve_war",
            lambda attacker, defender, world, seed=0, acc=None: WarResult(outcome, "Region C"))
        monkeypatch.setattr("chronicler.action_engine.get_perceived_stat",
            lambda *args, **kwargs: 50)

        bridge = _FakeBridge()
        engine_world._agent_bridge = bridge

        _resolve_war_action(engine_world.civilizations[0], engine_world)

        # GP synced to the winner's civ index
        assert bridge._sim.calls == [(99, winner_idx)]

    def test_turn_level_war_seed_includes_both_combatants(self, engine_world, monkeypatch):
        seeds = []

        def fake_resolve_war(attacker, defender, world, seed=0, acc=None):
            seeds.append((attacker.name, defender.name, seed))
            return WarResult("stalemate", None)

        monkeypatch.setattr("chronicler.action_engine.resolve_war", fake_resolve_war)
        monkeypatch.setattr("chronicler.action_engine.get_perceived_stat", lambda *args, **kwargs: 50)

        _resolve_war_action(engine_world.civilizations[0], engine_world)
        _resolve_war_action(engine_world.civilizations[1], engine_world)

        assert len(seeds) == 2
        assert seeds[0][2] != seeds[1][2]
        for attacker_name, defender_name, seed in seeds:
            expected = stable_hash_int("war", engine_world.seed, engine_world.turn, attacker_name, defender_name)
            assert seed == expected

    def test_war_skips_dead_hostile_targets(self, engine_world, monkeypatch):
        dead_civ = Civilization(
            name="Dead Civ", population=0, military=10, economy=10, culture=10,
            stability=10, tech_era=TechEra.IRON, treasury=0,
            leader=Leader(name="Ghost", trait="bold", reign_start=0),
            regions=[],
        )
        engine_world.civilizations.append(dead_civ)
        engine_world.relationships["Civ A"]["Dead Civ"] = Relationship(
            disposition=Disposition.HOSTILE
        )
        engine_world.relationships["Dead Civ"] = {
            "Civ A": Relationship(disposition=Disposition.HOSTILE)
        }

        monkeypatch.setattr("chronicler.action_engine.get_perceived_stat", lambda *args, **kwargs: 50)

        calls = []

        def fake_resolve_war(attacker, defender, world, seed=0, acc=None):
            calls.append(defender.name)
            return WarResult("stalemate", None)

        monkeypatch.setattr("chronicler.action_engine.resolve_war", fake_resolve_war)

        _resolve_war_action(engine_world.civilizations[0], engine_world)

        assert calls == ["Civ B"]

    def test_stalemate_losses_use_severity_multiplier(self, engine_world, monkeypatch):
        from chronicler.emergence import get_severity_multiplier
        from chronicler.utils import STAT_FLOOR, clamp

        attacker = engine_world.civilizations[0]
        defender = engine_world.civilizations[1]
        attacker.military = 50
        defender.military = 50
        attacker.stability = 10
        defender.stability = 10
        attacker.civ_stress = 20
        defender.civ_stress = 20

        class _FixedRng:
            def __init__(self, seed):
                self.seed = seed

            def choice(self, seq):
                return seq[0]

            def uniform(self, a, b):
                return 0.0

        monkeypatch.setattr("chronicler.action_engine.random.Random", _FixedRng)

        mult_att = get_severity_multiplier(attacker, engine_world)
        mult_def = get_severity_multiplier(defender, engine_world)
        expected_att = clamp(50 - int(10 * mult_att), STAT_FLOOR["military"], 100)
        expected_def = clamp(50 - int(10 * mult_def), STAT_FLOOR["military"], 100)

        result = resolve_war(attacker, defender, engine_world, seed=0)

        assert result.outcome == "stalemate"
        assert attacker.military == expected_att
        assert defender.military == expected_def


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

    def test_zero_divisor_override_uses_floor(self, engine_world, monkeypatch):
        civ = engine_world.civilizations[0]
        civ.war_weariness = 10.0

        def fake_get_override(world, key, default):
            if key == K_WAR_WEARINESS_DIVISOR:
                return 0.0
            return default

        monkeypatch.setattr("chronicler.action_engine.get_override", fake_get_override)
        weights = ActionEngine(engine_world).compute_weights(civ)
        assert weights[ActionType.WAR] > 0


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

        # Peace dividend applies ~5x raw boost, but 2.5x multiplier cap limits final ratio
        assert develop_peace > develop_base, "Peace should boost DEVELOP"
        assert trade_peace > trade_base, "Peace should boost TRADE"
        # Post-cap: ratio depends on how close base already is to cap
        develop_ratio = develop_peace / develop_base
        trade_ratio = trade_peace / trade_base
        assert develop_ratio > 1.5, f"Expected meaningful DEVELOP ratio, got {develop_ratio}"
        assert trade_ratio > 1.5, f"Expected meaningful TRADE ratio, got {trade_ratio}"

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


class TestTradeRouteCheck:
    """M-AF1 #2: TRADE should require an active trade route."""

    def test_trade_requires_active_route(self, engine_world):
        """TRADE should fall back to develop when no trade route exists."""
        civ = engine_world.civilizations[0]
        # Set disposition to NEUTRAL so the partner check passes
        engine_world.relationships["Civ A"]["Civ B"].disposition = Disposition.NEUTRAL
        engine_world.relationships["Civ B"]["Civ A"].disposition = Disposition.NEUTRAL
        # Remove all adjacencies so no trade route can exist
        for r in engine_world.regions:
            r.adjacencies = []

        pre_treasury = civ.treasury
        event = resolve_action(civ, ActionType.TRADE, engine_world)

        # Without a route, trade should fall back to develop
        assert event.event_type == "develop", \
            f"Expected 'develop' fallback, got '{event.event_type}'"

    def test_trade_works_with_active_route(self, engine_world):
        """TRADE should succeed when an active trade route exists."""
        civ = engine_world.civilizations[0]
        # Set disposition to NEUTRAL so the partner check passes
        engine_world.relationships["Civ A"]["Civ B"].disposition = Disposition.NEUTRAL
        engine_world.relationships["Civ B"]["Civ A"].disposition = Disposition.NEUTRAL
        # Create adjacency so a trade route exists
        engine_world.regions[0].adjacencies = ["Region C"]  # Civ A's region adjacent to Civ B's
        engine_world.regions[2].adjacencies = ["Region A"]  # Civ B's region adjacent to Civ A's

        event = resolve_action(civ, ActionType.TRADE, engine_world)

        assert event.event_type == "trade", \
            f"Expected 'trade' with active route, got '{event.event_type}'"
        assert "traded with" in event.description

    def test_trade_works_with_missing_relationship_when_route_exists(self, engine_world):
        civ = engine_world.civilizations[0]
        engine_world.relationships = {}
        engine_world.regions[0].adjacencies = ["Region C"]
        engine_world.regions[2].adjacencies = ["Region A"]

        event = resolve_action(civ, ActionType.TRADE, engine_world)

        assert event.event_type == "trade"
        assert event.actors == ["Civ A", "Civ B"]


class TestDiplomacyTargets:
    def test_diplomacy_skips_dead_targets(self, engine_world):
        from chronicler.action_engine import _resolve_diplomacy

        civ = engine_world.civilizations[0]
        other = engine_world.civilizations[1]
        civ.culture = 50
        other.regions = []
        engine_world.relationships["Civ A"]["Civ B"].disposition = Disposition.HOSTILE

        event = _resolve_diplomacy(civ, engine_world)

        assert event.event_type == "diplomacy"
        assert event.actors == ["Civ A"]


class TestWeightCap:
    def test_weight_cap_clamps_individual_actions(self, engine_world, monkeypatch):
        civ = engine_world.civilizations[0]
        civ.military = 80

        def uncapped_override(world, key, default):
            from chronicler.tuning import K_WEIGHT_CAP
            if key == K_WEIGHT_CAP:
                return 100.0
            return default

        monkeypatch.setattr("chronicler.action_engine.get_override", uncapped_override)
        uncapped = ActionEngine(engine_world).compute_weights(civ)

        def capped_override(world, key, default):
            from chronicler.tuning import K_WEIGHT_CAP
            if key == K_WEIGHT_CAP:
                return 2.5
            return default

        monkeypatch.setattr("chronicler.action_engine.get_override", capped_override)
        capped = ActionEngine(engine_world).compute_weights(civ)

        assert uncapped[ActionType.WAR] > 0.5
        assert capped[ActionType.WAR] == pytest.approx(0.5)
        assert capped[ActionType.DEVELOP] == pytest.approx(uncapped[ActionType.DEVELOP])


class TestInvestCultureWeights:
    def test_invest_culture_boost_requires_adjacent_rival(self, engine_world):
        civ = engine_world.civilizations[0]
        other = engine_world.civilizations[1]
        civ.tech_era = TechEra.INFORMATION
        civ.culture = 80
        other.culture = 80
        engine_world.relationships["Civ A"]["Civ B"].disposition = Disposition.NEUTRAL
        engine_world.relationships["Civ B"]["Civ A"].disposition = Disposition.NEUTRAL
        engine_world.regions[0].adjacencies = []
        engine_world.regions[1].adjacencies = []
        engine_world.regions[2].adjacencies = []

        non_adjacent = ActionEngine(engine_world).compute_weights(civ)[ActionType.INVEST_CULTURE]

        engine_world.regions[0].adjacencies = ["Region C"]
        engine_world.regions[2].adjacencies = ["Region A"]
        adjacent = ActionEngine(engine_world).compute_weights(civ)[ActionType.INVEST_CULTURE]

        assert adjacent == pytest.approx(non_adjacent * 2)


class TestWarStartTurns:
    """M-AF1 #4: war_start_turns must be stamped on war resolution and cleaned on war end."""

    def test_war_stamps_war_start_turns(self, engine_world):
        """Resolving a WAR action should populate war_start_turns."""
        engine_world.turn = 10
        civ = engine_world.civilizations[0]
        civ.military = 80  # strong attacker
        # Adjacency needed so intelligence accuracy > 0 (perceived stat != None)
        engine_world.regions[0].adjacencies = ["Region C"]
        engine_world.regions[2].adjacencies = ["Region A"]

        resolve_action(civ, ActionType.WAR, engine_world)

        assert len(engine_world.war_start_turns) > 0, \
            "war_start_turns should be populated after WAR resolution"
        from chronicler.politics import war_key
        key = war_key("Civ A", "Civ B")
        assert engine_world.war_start_turns.get(key) == 10, \
            f"Expected war start turn 10, got {engine_world.war_start_turns.get(key)}"

    def test_diplomacy_cleans_war_start_turns(self, engine_world):
        """Diplomacy reaching FRIENDLY should clean war_start_turns."""
        from chronicler.politics import war_key
        key = war_key("Civ A", "Civ B")
        engine_world.war_start_turns[key] = 5
        engine_world.active_wars.append(("Civ A", "Civ B"))
        # Set disposition to NEUTRAL so one upgrade reaches FRIENDLY (triggers cleanup)
        engine_world.relationships["Civ A"]["Civ B"].disposition = Disposition.NEUTRAL
        engine_world.relationships["Civ B"]["Civ A"].disposition = Disposition.NEUTRAL

        resolve_action(engine_world.civilizations[0], ActionType.DIPLOMACY, engine_world)

        assert key not in engine_world.war_start_turns, \
            "war_start_turns should be cleaned after diplomacy resolves war"

    def test_war_does_not_overwrite_existing_start_turn(self, engine_world):
        """A second WAR action against the same target should not overwrite the start turn."""
        from chronicler.politics import war_key
        key = war_key("Civ A", "Civ B")
        engine_world.war_start_turns[key] = 3
        engine_world.turn = 10
        civ = engine_world.civilizations[0]
        civ.military = 80
        # Adjacency needed so intelligence accuracy > 0
        engine_world.regions[0].adjacencies = ["Region C"]
        engine_world.regions[2].adjacencies = ["Region A"]

        resolve_action(civ, ActionType.WAR, engine_world)

        assert engine_world.war_start_turns[key] == 3, \
            "war_start_turns should preserve the original start turn, not overwrite"
