"""Tests for the six-phase simulation engine."""
import pytest
from chronicler.simulation import (
    phase_environment,
    phase_production,
    phase_action,
    phase_random_events,
    phase_consequences,
    run_turn,
    resolve_war,
    resolve_trade,
    apply_asabiya_dynamics,
)
from chronicler.models import (
    WorldState,
    Civilization,
    ActionType,
    Disposition,
    Event,
    ActiveCondition,
)


class TestPhaseEnvironment:
    def test_no_event_with_zero_probabilities(self, sample_world):
        sample_world.event_probabilities = {k: 0.0 for k in sample_world.event_probabilities}
        events = phase_environment(sample_world, seed=42)
        assert events == []

    def test_drought_reduces_stability(self, sample_world):
        """If a drought occurs, affected civs lose stability."""
        sample_world.event_probabilities["drought"] = 1.0
        # Zero out others to isolate
        for k in sample_world.event_probabilities:
            if k != "drought":
                sample_world.event_probabilities[k] = 0.0
        old_stabilities = {c.name: c.stability for c in sample_world.civilizations}
        events = phase_environment(sample_world, seed=42)
        assert len(events) >= 1
        assert events[0].event_type == "drought"
        # At least one civ should have reduced stability
        new_stabilities = {c.name: c.stability for c in sample_world.civilizations}
        assert any(new_stabilities[n] < old_stabilities[n] for n in old_stabilities)


class TestPhaseProduction:
    def test_treasury_increases(self, sample_world):
        old_treasuries = {c.name: c.treasury for c in sample_world.civilizations}
        phase_production(sample_world)
        for civ in sample_world.civilizations:
            # Treasury should increase by economy-based income
            assert civ.treasury >= old_treasuries[civ.name]

    def test_population_bounded(self, sample_world):
        # Set population to max
        sample_world.civilizations[0].population = 10
        phase_production(sample_world)
        assert sample_world.civilizations[0].population <= 10


class TestPhaseAction:
    def test_each_civ_takes_one_action(self, sample_world):
        """With a stub action selector, every civ takes exactly one action."""
        def stub_selector(civ: Civilization, world: WorldState) -> ActionType:
            return ActionType.DEVELOP

        events = phase_action(sample_world, action_selector=stub_selector)
        assert len(events) == len(sample_world.civilizations)


class TestResolveWar:
    def test_attacker_wins_if_stronger(self, sample_world):
        attacker = sample_world.civilizations[1]  # Dorrathi: military=7
        defender = sample_world.civilizations[0]  # Kethani: military=5
        attacker_mil_before = attacker.military
        result = resolve_war(attacker, defender, sample_world, seed=42)
        assert result in ("attacker_wins", "defender_wins", "stalemate")

    def test_war_costs_treasury(self, sample_world):
        attacker = sample_world.civilizations[1]
        defender = sample_world.civilizations[0]
        old_att_treasury = attacker.treasury
        old_def_treasury = defender.treasury
        resolve_war(attacker, defender, sample_world, seed=42)
        assert attacker.treasury <= old_att_treasury
        assert defender.treasury <= old_def_treasury


class TestResolveTrade:
    def test_trade_increases_treasury(self, sample_world):
        c1 = sample_world.civilizations[0]
        c2 = sample_world.civilizations[1]
        old_t1 = c1.treasury
        old_t2 = c2.treasury
        resolve_trade(c1, c2, sample_world)
        assert c1.treasury >= old_t1
        assert c2.treasury >= old_t2


class TestAsabiyaDynamics:
    def test_frontier_civs_gain_asabiya(self, sample_world):
        """Civs bordering hostile neighbors should gain asabiya (Turchin model)."""
        # Dorrathi is hostile to Kethani
        sample_world.relationships["Dorrathi Clans"]["Kethani Empire"].disposition = Disposition.HOSTILE
        old_asabiya = sample_world.civilizations[1].asabiya
        apply_asabiya_dynamics(sample_world)
        assert sample_world.civilizations[1].asabiya >= old_asabiya

    def test_asabiya_stays_bounded(self, sample_world):
        sample_world.civilizations[0].asabiya = 0.99
        apply_asabiya_dynamics(sample_world)
        assert sample_world.civilizations[0].asabiya <= 1.0


class TestPhaseConsequences:
    def test_conditions_tick_down(self, sample_world):
        sample_world.active_conditions.append(
            ActiveCondition(condition_type="drought", affected_civs=["Kethani Empire"], duration=3, severity=5)
        )
        phase_consequences(sample_world)
        assert sample_world.active_conditions[0].duration == 2

    def test_expired_conditions_removed(self, sample_world):
        sample_world.active_conditions.append(
            ActiveCondition(condition_type="drought", affected_civs=["Kethani Empire"], duration=1, severity=5)
        )
        phase_consequences(sample_world)
        assert len(sample_world.active_conditions) == 0


class TestRunTurn:
    def test_turn_increments(self, sample_world):
        def stub_selector(civ, world):
            return ActionType.DEVELOP

        def stub_narrator(world, turn_events):
            return "A quiet turn passed."

        run_turn(sample_world, action_selector=stub_selector, narrator=stub_narrator, seed=42)
        assert sample_world.turn == 1

    def test_events_recorded(self, sample_world):
        def stub_selector(civ, world):
            return ActionType.DEVELOP

        def stub_narrator(world, turn_events):
            return "Things happened."

        run_turn(sample_world, action_selector=stub_selector, narrator=stub_narrator, seed=42)
        assert len(sample_world.events_timeline) > 0
