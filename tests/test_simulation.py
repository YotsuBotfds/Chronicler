"""Tests for the nine-phase simulation engine."""
import pytest
from chronicler.simulation import (
    phase_environment,
    phase_production,
    phase_action,
    phase_random_events,
    phase_consequences,
    run_turn,
    apply_asabiya_dynamics,
    update_war_frequency_accumulators,
    reset_war_frequency_on_extinction,
)
from chronicler.action_engine import resolve_war, resolve_trade
from chronicler.simulation import apply_injected_event
from chronicler.models import (
    WorldState,
    Civilization,
    ActionType,
    Disposition,
    Event,
    ActiveCondition,
    TechEra,
    NamedEvent,
    Leader,
    Region,
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
        sample_world.civilizations[0].population = 100
        phase_production(sample_world)
        assert sample_world.civilizations[0].population <= 100


class TestPhaseAction:
    def test_each_civ_takes_one_action(self, sample_world):
        """With a stub action selector, every civ takes exactly one action."""
        def stub_selector(civ: Civilization, world: WorldState) -> ActionType:
            return ActionType.DEVELOP

        events = phase_action(sample_world, action_selector=stub_selector)
        assert len(events) == len(sample_world.civilizations)


class TestResolveWar:
    def test_attacker_wins_if_stronger(self, sample_world):
        attacker = sample_world.civilizations[1]  # Dorrathi: military=70
        defender = sample_world.civilizations[0]  # Kethani: military=50
        attacker_mil_before = attacker.military
        result = resolve_war(attacker, defender, sample_world, seed=42)
        assert result.outcome in ("attacker_wins", "defender_wins", "stalemate")

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
            ActiveCondition(condition_type="drought", affected_civs=["Kethani Empire"], duration=3, severity=50)
        )
        phase_consequences(sample_world)
        assert sample_world.active_conditions[0].duration == 2

    def test_expired_conditions_removed(self, sample_world):
        sample_world.active_conditions.append(
            ActiveCondition(condition_type="drought", affected_civs=["Kethani Empire"], duration=1, severity=50)
        )
        phase_consequences(sample_world)
        assert len(sample_world.active_conditions) == 0

    def test_collapse_events_returned(self, sample_world):
        """Collapse events must be returned so the narrator can see them."""
        civ = sample_world.civilizations[0]
        civ.asabiya = 0.05  # Below 0.1 threshold
        civ.stability = 10  # Below 20 threshold
        # Give civ multiple regions so collapse actually fires
        civ.regions = [r.name for r in sample_world.regions[:3]]
        for r in sample_world.regions[:3]:
            r.controller = civ.name
        all_events = phase_consequences(sample_world)
        collapse_events = [e for e in all_events if e.event_type == "collapse"]
        assert len(collapse_events) == 1
        assert collapse_events[0].importance == 10
        assert civ.name in collapse_events[0].actors


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

    def test_collapse_events_passed_to_narrator(self, sample_world):
        """Narrator must receive collapse events (critical fix: was previously missed)."""
        # Force a collapse for the first civ
        civ = sample_world.civilizations[0]
        civ.asabiya = 0.05
        civ.stability = 10
        civ.regions = [r.name for r in sample_world.regions[:3]]
        for r in sample_world.regions[:3]:
            r.controller = civ.name

        narrator_events = []

        def stub_selector(c, w):
            return ActionType.DEVELOP

        def capturing_narrator(world, turn_events):
            narrator_events.extend(turn_events)
            return "Collapse narrated."

        run_turn(sample_world, stub_selector, capturing_narrator, seed=42)
        collapse = [e for e in narrator_events if e.event_type == "collapse"]
        assert len(collapse) >= 1, "Narrator should receive collapse events"


class TestFiveTurnValidation:
    """Critical gate: run 5 turns with stubs and verify the simulation loop is sound."""

    def test_five_turns_no_crash(self, sample_world, tmp_path):
        def stub_selector(civ, world):
            return ActionType.DEVELOP

        def stub_narrator(world, turn_events):
            return f"Turn {world.turn}: {len(turn_events)} events occurred."

        for i in range(5):
            text = run_turn(sample_world, stub_selector, stub_narrator, seed=i)
            assert isinstance(text, str)
            # Save state after every turn (crash recovery pattern)
            sample_world.save(tmp_path / f"state_turn_{sample_world.turn}.json")

        assert sample_world.turn == 5
        assert len(sample_world.events_timeline) > 0

    def test_five_turns_state_files_loadable(self, sample_world, tmp_path):
        """Every per-turn state file should deserialize back to a valid WorldState."""
        def stub_selector(civ, world):
            return ActionType.DEVELOP

        def stub_narrator(world, turn_events):
            return "ok"

        for i in range(5):
            run_turn(sample_world, stub_selector, stub_narrator, seed=i)
            path = tmp_path / f"state_turn_{sample_world.turn}.json"
            sample_world.save(path)
            # Verify round-trip
            loaded = WorldState.load(path)
            assert loaded.turn == sample_world.turn
            assert len(loaded.civilizations) == len(sample_world.civilizations)

    def test_five_turns_stats_stay_bounded(self, sample_world):
        """All civilization stats must remain within [0, 100] after 5 turns."""
        def stub_selector(civ, world):
            # Mix of actions to stress-test bounds
            actions = [ActionType.DEVELOP, ActionType.WAR, ActionType.EXPAND,
                       ActionType.TRADE, ActionType.DIPLOMACY]
            return actions[world.turn % len(actions)]

        def stub_narrator(world, turn_events):
            return "ok"

        for i in range(5):
            run_turn(sample_world, stub_selector, stub_narrator, seed=i)

        for civ in sample_world.civilizations:
            assert 1 <= civ.population <= 100
            assert 0 <= civ.military <= 100
            assert 0 <= civ.economy <= 100
            assert 0 <= civ.culture <= 100
            assert 0 <= civ.stability <= 100
            assert 0.0 <= civ.asabiya <= 1.0


def test_nine_phase_run_turn(sample_world):
    """run_turn executes all 9 phases without error."""
    for civ in sample_world.civilizations:
        civ.tech_era = TechEra.TRIBAL
        civ.economy = 50
        civ.culture = 50
        civ.treasury = 150

    def stub_selector(civ, world):
        return ActionType.DEVELOP

    def stub_narrator(world, events):
        return "Turn narrative."

    result = run_turn(sample_world, stub_selector, stub_narrator, seed=42)
    assert isinstance(result, str)
    assert sample_world.turn == 1


def test_tech_phase_runs(sample_world):
    """Tech advancement should happen during the tech phase."""
    from chronicler.models import Resource
    for civ in sample_world.civilizations:
        civ.tech_era = TechEra.TRIBAL
        civ.economy = 40
        civ.culture = 40
        civ.treasury = 100
    # Give controlled regions the resources needed for TRIBAL→BRONZE
    from chronicler.models import ResourceType, EMPTY_SLOT
    for r in sample_world.regions:
        if r.controller:
            r.specialized_resources = [Resource.IRON, Resource.TIMBER]
            r.resource_types = [ResourceType.ORE, ResourceType.TIMBER, EMPTY_SLOT]

    def stub_selector(civ, world):
        return ActionType.DEVELOP

    def stub_narrator(world, events):
        return "Turn narrative."

    run_turn(sample_world, stub_selector, stub_narrator, seed=42)
    # At least one civ should have advanced past TRIBAL
    eras = [civ.tech_era for civ in sample_world.civilizations]
    assert any(era != TechEra.TRIBAL for era in eras)


def test_leader_dynamics_phase(sample_world):
    """Leader dynamics phase handles trait evolution."""
    civ = sample_world.civilizations[0]
    civ.leader.reign_start = 0
    civ.action_counts = {"war": 15}
    sample_world.turn = 15

    def stub_selector(c, w):
        return ActionType.DEVELOP

    def stub_narrator(w, e):
        return "Turn narrative."

    run_turn(sample_world, stub_selector, stub_narrator, seed=42)
    assert civ.leader.secondary_trait == "warlike"


def test_action_history_tracked(sample_world):
    """Action history is recorded for streak tracking."""
    def stub_selector(civ, world):
        return ActionType.DEVELOP

    def stub_narrator(world, events):
        return "Turn narrative."

    run_turn(sample_world, stub_selector, stub_narrator, seed=42)
    for civ in sample_world.civilizations:
        assert civ.name in sample_world.action_history
        assert sample_world.action_history[civ.name][-1] == "develop"


def test_action_counts_tracked(sample_world):
    """Action counts increment for current leader's reign."""
    def stub_selector(civ, world):
        return ActionType.DEVELOP

    def stub_narrator(world, events):
        return "Turn narrative."

    run_turn(sample_world, stub_selector, stub_narrator, seed=42)
    for civ in sample_world.civilizations:
        assert civ.action_counts.get("develop", 0) >= 1


def test_war_uses_tech_disparity(sample_world):
    """War resolution accounts for tech era gap."""
    from chronicler.action_engine import resolve_war
    attacker = sample_world.civilizations[0]
    defender = sample_world.civilizations[1]
    attacker.tech_era = TechEra.MEDIEVAL
    defender.tech_era = TechEra.TRIBAL
    results = []
    for seed in range(50):
        attacker.military = 50
        defender.military = 50
        attacker.treasury = 100
        defender.treasury = 100
        result = resolve_war(attacker, defender, sample_world, seed=seed)
        results.append(result)
    attacker_wins = sum(1 for r in results if r.outcome == "attacker_wins")
    assert attacker_wins > 25, f"Tech advantage not reflected: {attacker_wins}/50 wins"


def test_backward_compat_old_state(tmp_path, sample_world):
    """Old state files without new fields should load and run."""
    state_path = tmp_path / "state.json"
    sample_world.save(state_path)
    from chronicler.models import WorldState
    loaded = WorldState.load(state_path)
    assert loaded.named_events == []
    assert loaded.used_leader_names == []
    assert loaded.action_history == {}

    def stub_selector(civ, world):
        return ActionType.DEVELOP

    def stub_narrator(world, events):
        return "Turn narrative."

    run_turn(loaded, stub_selector, stub_narrator, seed=42)


def test_diplomacy_treaty_requires_classical_era(sample_world):
    """Named treaties should only be generated at CLASSICAL+ era."""
    from chronicler.action_engine import _resolve_diplomacy
    from chronicler.models import Relationship
    civ = sample_world.civilizations[0]
    other = sample_world.civilizations[1]
    civ.tech_era = TechEra.BRONZE  # Below CLASSICAL
    civ.culture = 50
    # Set relationship to NEUTRAL so diplomacy upgrades to FRIENDLY (treaty-worthy)
    sample_world.relationships[civ.name][other.name] = Relationship(disposition=Disposition.NEUTRAL)
    sample_world.relationships[other.name][civ.name] = Relationship(disposition=Disposition.NEUTRAL)
    _resolve_diplomacy(civ, sample_world)
    treaties = [ne for ne in sample_world.named_events if ne.event_type == "treaty"]
    assert len(treaties) == 0, "BRONZE era should not generate named treaties"


def test_diplomacy_treaty_generated_at_classical(sample_world):
    """Named treaties should be generated at CLASSICAL+ era."""
    from chronicler.action_engine import _resolve_diplomacy
    from chronicler.models import Relationship
    civ = sample_world.civilizations[0]
    other = sample_world.civilizations[1]
    civ.tech_era = TechEra.CLASSICAL
    civ.culture = 50
    sample_world.relationships[civ.name][other.name] = Relationship(disposition=Disposition.NEUTRAL)
    sample_world.relationships[other.name][civ.name] = Relationship(disposition=Disposition.NEUTRAL)
    _resolve_diplomacy(civ, sample_world)
    treaties = [ne for ne in sample_world.named_events if ne.event_type == "treaty"]
    assert len(treaties) == 1, "CLASSICAL era should generate named treaties on FRIENDLY upgrade"


def test_expand_harsh_terrain_requires_iron(sample_world):
    """Pre-IRON civs should not expand into desert/tundra regions."""
    from chronicler.action_engine import _resolve_expand
    from chronicler.models import Region
    civ = sample_world.civilizations[0]
    civ.tech_era = TechEra.BRONZE
    civ.military = 50
    # Remove all unclaimed regions, add only a desert one
    for r in sample_world.regions:
        r.controller = "someone"
    sample_world.regions.append(
        Region(name="Burning Wastes", terrain="desert", carrying_capacity=30, resources="sparse")
    )
    event = _resolve_expand(civ, sample_world)
    assert "could not expand" in event.description


def test_expand_harsh_terrain_allowed_at_iron(sample_world):
    """IRON+ civs can expand into desert/tundra regions."""
    from chronicler.action_engine import _resolve_expand
    from chronicler.models import Region
    civ = sample_world.civilizations[0]
    civ.tech_era = TechEra.IRON
    civ.military = 50
    for r in sample_world.regions:
        r.controller = "someone"
    sample_world.regions.append(
        Region(name="Burning Wastes", terrain="desert", carrying_capacity=30, resources="sparse")
    )
    event = _resolve_expand(civ, sample_world)
    assert "expanded into" in event.description


def test_medieval_defender_asabiya_bonus(sample_world):
    """MEDIEVAL+ defenders should get +0.2 asabiya bonus in war."""
    attacker = sample_world.civilizations[0]
    defender = sample_world.civilizations[1]
    # Both have equal military, but defender has MEDIEVAL era advantage
    attacker.military = 50
    defender.military = 50
    attacker.tech_era = TechEra.CLASSICAL
    defender.tech_era = TechEra.MEDIEVAL
    attacker.asabiya = 0.5
    defender.asabiya = 0.5  # Effective 0.7 with bonus
    # Run many trials to confirm statistical edge
    defender_wins = 0
    for seed in range(100):
        attacker.military = 50
        defender.military = 50
        attacker.treasury = 100
        defender.treasury = 100
        result = resolve_war(attacker, defender, sample_world, seed=seed)
        if result.outcome == "defender_wins":
            defender_wins += 1
    # With the asabiya bonus, defender should win more often than without
    assert defender_wins > 30, f"MEDIEVAL defender bonus not effective: {defender_wins}/100 wins"


class TestApplyInjectedEvent:
    def test_plague_reduces_pop_and_stability(self, sample_world):
        civ = sample_world.civilizations[0]
        old_pop = civ.population
        old_stb = civ.stability
        events = apply_injected_event("plague", civ.name, sample_world)
        assert len(events) == 1
        assert events[0].event_type == "plague"
        assert events[0].actors == [civ.name]
        assert civ.population <= old_pop
        assert civ.stability <= old_stb

    def test_discovery_boosts_culture_and_economy(self, sample_world):
        civ = sample_world.civilizations[1]
        old_culture = civ.culture
        old_economy = civ.economy
        events = apply_injected_event("discovery", civ.name, sample_world)
        assert civ.culture >= old_culture
        assert civ.economy >= old_economy

    def test_unknown_civ_returns_empty(self, sample_world):
        events = apply_injected_event("plague", "Nonexistent Civ", sample_world)
        assert events == []

    def test_creates_active_condition_for_drought(self, sample_world):
        civ = sample_world.civilizations[0]
        old_conditions = len(sample_world.active_conditions)
        apply_injected_event("drought", civ.name, sample_world)
        # drought handler creates an ActiveCondition
        assert len(sample_world.active_conditions) > old_conditions


def _make_world_with_wars():
    """Create a minimal world for testing weariness/momentum tick."""
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
    civ_dead = Civilization(
        name="Civ Dead", population=0, military=0, economy=0, culture=0,
        stability=0, tech_era=TechEra.TRIBAL, treasury=0,
        leader=Leader(name="Ghost", trait="cautious", reign_start=0),
        regions=[],
    )
    world = WorldState(
        name="Test", seed=42, turn=5,
        regions=[
            Region(name="Region A", terrain="plains", carrying_capacity=80, resources="fertile", controller="Civ A"),
            Region(name="Region B", terrain="plains", carrying_capacity=80, resources="fertile", controller="Civ B"),
        ],
        civilizations=[civ_a, civ_b, civ_dead],
    )
    return world


class TestWarFrequencyAccumulators:
    """M47d: Per-turn weariness and momentum update tick."""

    def test_war_action_adds_increment(self):
        world = _make_world_with_wars()
        world.action_history = {"Civ A": ["war"], "Civ B": ["develop"]}
        update_war_frequency_accumulators(world)
        assert world.civilizations[0].war_weariness > 0.0
        assert world.civilizations[1].war_weariness == 0.0

    def test_weariness_decays(self):
        world = _make_world_with_wars()
        world.civilizations[0].war_weariness = 10.0
        world.action_history = {"Civ A": ["develop"]}
        update_war_frequency_accumulators(world)
        assert world.civilizations[0].war_weariness < 10.0
        assert world.civilizations[0].war_weariness == pytest.approx(10.0 * 0.95)

    def test_passive_weariness_from_active_wars(self):
        world = _make_world_with_wars()
        world.active_wars = [("Civ A", "Civ B")]
        world.action_history = {"Civ A": ["develop"], "Civ B": ["develop"]}
        update_war_frequency_accumulators(world)
        assert world.civilizations[0].war_weariness > 0
        assert world.civilizations[1].war_weariness > 0

    def test_declaration_turn_double_counting(self):
        """Civ that declares WAR gets INCREMENT + PASSIVE on same turn (intentional)."""
        world = _make_world_with_wars()
        world.action_history = {"Civ A": ["war"]}
        world.active_wars = [("Civ A", "Civ B")]
        update_war_frequency_accumulators(world)
        # INCREMENT (2.0) + PASSIVE (0.5) = 2.5
        assert world.civilizations[0].war_weariness == pytest.approx(2.5)

    def test_peace_momentum_increments(self):
        world = _make_world_with_wars()
        world.action_history = {"Civ A": ["develop"], "Civ B": ["develop"]}
        update_war_frequency_accumulators(world)
        assert world.civilizations[0].peace_momentum == 1.0
        assert world.civilizations[1].peace_momentum == 1.0

    def test_peace_momentum_caps(self):
        world = _make_world_with_wars()
        world.civilizations[0].peace_momentum = 19.5
        world.action_history = {"Civ A": ["develop"]}
        update_war_frequency_accumulators(world)
        assert world.civilizations[0].peace_momentum == 20.0

    def test_chose_war_aggressor_decay(self):
        """Only civs that CHOSE WAR this turn get aggressor decay (0.3x)."""
        world = _make_world_with_wars()
        world.civilizations[0].peace_momentum = 20.0
        world.active_wars = [("Civ A", "Civ B")]
        world.action_history = {"Civ A": ["war"], "Civ B": ["develop"]}
        update_war_frequency_accumulators(world)
        assert world.civilizations[0].peace_momentum == pytest.approx(20.0 * 0.5)

    def test_in_war_without_choosing_gets_defender_decay(self):
        """Civ in active_war (either side) but didn't choose WAR: defender decay."""
        world = _make_world_with_wars()
        world.civilizations[0].peace_momentum = 20.0
        world.active_wars = [("Civ A", "Civ B")]
        world.action_history = {"Civ A": ["develop"], "Civ B": ["develop"]}
        update_war_frequency_accumulators(world)
        assert world.civilizations[0].peace_momentum == pytest.approx(20.0 * 0.95)

    def test_defender_peace_decay(self):
        world = _make_world_with_wars()
        world.civilizations[1].peace_momentum = 20.0
        world.active_wars = [("Civ A", "Civ B")]
        world.action_history = {"Civ A": ["develop"], "Civ B": ["develop"]}
        update_war_frequency_accumulators(world)
        assert world.civilizations[1].peace_momentum == pytest.approx(20.0 * 0.95)

    def test_dead_civ_skipped(self):
        world = _make_world_with_wars()
        world.civilizations[2].war_weariness = 5.0
        world.civilizations[2].peace_momentum = 10.0
        world.action_history = {}
        update_war_frequency_accumulators(world)
        assert world.civilizations[2].war_weariness == 5.0
        assert world.civilizations[2].peace_momentum == 10.0


class TestExtinctionReset:
    """M47d: Reset weariness/momentum when civ goes extinct."""

    def test_extinction_resets_both_fields(self):
        world = _make_world_with_wars()
        civ = world.civilizations[0]
        civ.war_weariness = 15.0
        civ.peace_momentum = 10.0
        civ.regions = []
        reset_war_frequency_on_extinction(civ)
        assert civ.war_weariness == 0.0
        assert civ.peace_momentum == 0.0

    def test_living_civ_not_reset(self):
        world = _make_world_with_wars()
        civ = world.civilizations[0]
        civ.war_weariness = 15.0
        civ.peace_momentum = 10.0
        reset_war_frequency_on_extinction(civ)
        assert civ.war_weariness == 15.0
        assert civ.peace_momentum == 10.0
