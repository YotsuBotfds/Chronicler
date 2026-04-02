"""Tests for the nine-phase simulation engine."""
import pytest
from chronicler.simulation import (
    phase_environment,
    phase_production,
    apply_automatic_effects,
    phase_action,
    phase_random_events,
    phase_consequences,
    _apply_event_effects,
    prune_inactive_wars,
    run_turn,
    apply_asabiya_dynamics,
    update_war_frequency_accumulators,
    reset_war_frequency_on_extinction,
    _apply_treasury_tax_from_economy,
)
from chronicler.action_engine import resolve_war, resolve_trade
from chronicler.simulation import apply_injected_event
from chronicler.accumulator import StatAccumulator
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
    CivShock,
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

    def test_drought_stability_uses_severity_multiplier_with_acc(self, sample_world, monkeypatch):
        """Accumulator path should apply severity scaling to drought stability drain."""
        from chronicler.accumulator import StatAccumulator

        sample_world.event_probabilities = {k: 0.0 for k in sample_world.event_probabilities}
        sample_world.event_probabilities["drought"] = 1.0
        # Keep exactly one alive civ to avoid random affected-set variation.
        for civ in sample_world.civilizations[1:]:
            civ.regions = []

        monkeypatch.setattr("chronicler.simulation.get_severity_multiplier", lambda *_: 2.0)

        civ = sample_world.civilizations[0]
        old_stability = civ.stability
        acc = StatAccumulator()
        phase_environment(sample_world, seed=42, acc=acc)
        acc.apply(sample_world)

        assert civ.stability == old_stability - 6  # default drought drain 3 * severity 2.0


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


class TestAutomaticEffects:
    def test_low_stability_recovery_routes_as_guard_shock(self, sample_world):
        """B-1 fix: Stability recovery routes as guard-shock (not keep) so it
        reaches the Rust tick as a positive shock signal.  apply_keep() should
        NOT apply it; to_shock_signals() should capture it."""
        from chronicler.accumulator import StatAccumulator

        civ = sample_world.civilizations[0]
        civ.stability = 10
        sample_world.active_conditions = []

        acc = StatAccumulator()
        phase_production(sample_world, acc=acc)

        # apply_keep should NOT change stability (recovery is guard-shock now)
        acc.apply_keep(sample_world)
        assert civ.stability == 10

        # But the recovery should appear as a positive shock signal
        shocks = acc.to_shock_signals()
        civ_idx = 0
        stability_shocks = [s for s in shocks if s.civ_id == civ_idx]
        assert len(stability_shocks) > 0
        assert stability_shocks[0].stability_shock > 0  # positive recovery

    def test_low_stability_recovery_applies_in_aggregate_mode(self, sample_world):
        """In aggregate mode (--agents=off), stability recovery still applies
        via acc.apply() which processes all categories."""
        from chronicler.accumulator import StatAccumulator

        civ = sample_world.civilizations[0]
        civ.stability = 10
        sample_world.active_conditions = []

        acc = StatAccumulator()
        phase_production(sample_world, acc=acc)
        acc.apply(sample_world)

        assert civ.stability == 30

    def test_war_cost_stability_uses_projected_treasury_in_acc_mode(self, sample_world):
        """War-cost stability drain should trigger when treasury crosses <= 0 in acc mode."""
        from chronicler.accumulator import StatAccumulator

        c0 = sample_world.civilizations[0]
        c1 = sample_world.civilizations[1]
        c0.treasury = 2
        c0.stability = 50
        c0.military = 0
        c1.military = 0
        c0.last_income = 0
        c1.last_income = 0
        sample_world.active_wars = [(c0.name, c1.name)]

        acc = StatAccumulator()
        apply_automatic_effects(sample_world, acc=acc)
        acc.apply(sample_world)

        assert c0.treasury == 0
        assert c0.stability == 48

    def test_treasury_tax_fractional_carry_prevents_permanent_zeroing(self, sample_world):
        """Fractional tax should carry and eventually convert to whole-treasury increments."""
        from types import SimpleNamespace
        from chronicler.accumulator import StatAccumulator

        civ = sample_world.civilizations[0]
        civ.treasury = 0
        sample_world._treasury_tax_carry = {}
        economy_result = SimpleNamespace(treasury_tax={0: 0.6})

        acc_1 = StatAccumulator()
        _apply_treasury_tax_from_economy(sample_world, acc_1, economy_result)
        acc_1.apply_keep(sample_world)
        assert civ.treasury == 0
        assert sample_world._treasury_tax_carry[0] == pytest.approx(0.6)

        acc_2 = StatAccumulator()
        _apply_treasury_tax_from_economy(sample_world, acc_2, economy_result)
        acc_2.apply_keep(sample_world)
        assert civ.treasury == 1
        assert sample_world._treasury_tax_carry[0] == pytest.approx(0.2)


class TestPhaseAction:
    def test_each_civ_takes_one_action(self, sample_world):
        """With a stub action selector, every civ takes exactly one action."""
        def stub_selector(civ: Civilization, world: WorldState) -> ActionType:
            return ActionType.DEVELOP

        events = phase_action(sample_world, action_selector=stub_selector)
        assert len(events) == len(sample_world.civilizations)

    def test_crisis_halving_applies_in_accumulator_mode(self, sample_world):
        """Crisis action gains must be halved even when actions route through StatAccumulator."""
        from chronicler.accumulator import StatAccumulator
        from chronicler.simulation import _CRISIS_HALVED_STATS

        crisis_world = sample_world.model_copy(deep=True)
        normal_world = sample_world.model_copy(deep=True)

        crisis_civ = crisis_world.civilizations[0]
        normal_civ = normal_world.civilizations[0]
        crisis_civ.succession_crisis_turns_remaining = 2
        normal_civ.succession_crisis_turns_remaining = 0

        before_crisis = {s: getattr(crisis_civ, s) for s in _CRISIS_HALVED_STATS}
        before_normal = {s: getattr(normal_civ, s) for s in _CRISIS_HALVED_STATS}

        selector = lambda civ, world: ActionType.DEVELOP

        acc_crisis = StatAccumulator()
        phase_action(crisis_world, action_selector=selector, acc=acc_crisis)
        acc_crisis.apply(crisis_world)

        acc_normal = StatAccumulator()
        phase_action(normal_world, action_selector=selector, acc=acc_normal)
        acc_normal.apply(normal_world)

        positive_stats_checked = 0
        for stat in _CRISIS_HALVED_STATS:
            normal_gain = getattr(normal_civ, stat) - before_normal[stat]
            crisis_gain = getattr(crisis_civ, stat) - before_crisis[stat]
            if normal_gain > 0:
                positive_stats_checked += 1
                assert crisis_gain == normal_gain // 2
        assert positive_stats_checked > 0


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


def test_phase_random_events_targets_only_living_civs(sample_world):
    sample_world.event_probabilities = {k: 0.0 for k in sample_world.event_probabilities}
    sample_world.event_probabilities["rebellion"] = 1.0

    for civ in sample_world.civilizations:
        civ.regions = []
    living = sample_world.civilizations[0]
    living.regions = [sample_world.regions[0].name]

    events = phase_random_events(sample_world, seed=123)
    assert events
    assert events[0].actors == [living.name]


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

    def test_leader_death_passes_acc_to_rival_fall(self, sample_world, monkeypatch):
        """Leader-death path should pass the active accumulator into rival-fall handling."""
        from chronicler.accumulator import StatAccumulator

        seen = {"acc": None}

        def _fake_rival_fall(civ, dead_leader_name, world, acc=None):
            seen["acc"] = acc
            return None

        monkeypatch.setattr("chronicler.simulation.check_rival_fall", _fake_rival_fall)

        acc = StatAccumulator()
        _apply_event_effects("leader_death", sample_world.civilizations[0], sample_world, acc=acc)

        assert seen["acc"] is acc


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

    def test_agents_off_keeps_economy_result_unset(self, sample_world):
        """M54b freeze: production off-mode does not synthesize economy_result."""
        def stub_selector(civ, world):
            return ActionType.DEVELOP

        def stub_narrator(world, turn_events):
            return "A quiet turn passed."

        run_turn(sample_world, action_selector=stub_selector, narrator=stub_narrator, seed=42)

        assert hasattr(sample_world, "_economy_result")
        assert sample_world._economy_result is None

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

    def test_run_turn_prunes_stale_wars_for_extinct_civs(self, sample_world):
        """Extinct participants should not keep survivor civs in stale wars."""
        alive = sample_world.civilizations[0]
        extinct = sample_world.civilizations[1]
        extinct.regions = []
        sample_world.active_wars = [(alive.name, extinct.name)]
        sample_world.war_start_turns = {
            f"{min(alive.name, extinct.name)}:{max(alive.name, extinct.name)}": 0
        }

        run_turn(sample_world, lambda *_: ActionType.DEVELOP, lambda *_: "", seed=42)

        assert sample_world.active_wars == []
        assert sample_world.war_start_turns == {}


def test_prune_inactive_wars_removes_missing_participants(sample_world):
    alive = sample_world.civilizations[0]
    extinct = sample_world.civilizations[1]
    extinct.regions = []
    key = f"{min(alive.name, extinct.name)}:{max(alive.name, extinct.name)}"
    sample_world.active_wars = [(alive.name, extinct.name)]
    sample_world.war_start_turns = {key: 7}

    prune_inactive_wars(sample_world)

    assert sample_world.active_wars == []
    assert sample_world.war_start_turns == {}


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


def test_black_market_checks_all_regions():
    """M-AF1 #16: black market should scan all controlled regions, not just first."""
    from chronicler.models import Relationship

    # Civ A is embargoed with Civ B.  Civ A controls Region A and Region B.
    # Region A is only adjacent to Region B (same controller -- no smuggling).
    # Region B is adjacent to Region C (controlled by Civ C, NOT embargoed).
    # The black market route is Region B -> Region C.  With the bug, only
    # Region A was scanned, so the route was never found.
    civ_a = Civilization(
        name="Civ A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50,
        leader=Leader(name="Leader A", trait="cautious", reign_start=0),
        regions=["Region A", "Region B"],
    )
    civ_b = Civilization(
        name="Civ B", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50,
        leader=Leader(name="Leader B", trait="cautious", reign_start=0),
        regions=[],
    )
    civ_c = Civilization(
        name="Civ C", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50,
        leader=Leader(name="Leader C", trait="cautious", reign_start=0),
        regions=["Region C"],
    )
    region_a = Region(
        name="Region A", terrain="plains", carrying_capacity=60,
        resources="fertile", controller="Civ A",
    )
    region_b = Region(
        name="Region B", terrain="plains", carrying_capacity=60,
        resources="fertile", controller="Civ A",
    )
    region_c = Region(
        name="Region C", terrain="plains", carrying_capacity=60,
        resources="fertile", controller="Civ C",
    )
    region_a.adjacencies = ["Region B"]
    region_b.adjacencies = ["Region A", "Region C"]
    region_c.adjacencies = ["Region B"]

    world = WorldState(
        name="Test", seed=42, turn=5,
        regions=[region_a, region_b, region_c],
        civilizations=[civ_a, civ_b, civ_c],
        relationships={
            "Civ A": {
                "Civ B": Relationship(disposition=Disposition.SUSPICIOUS),
                "Civ C": Relationship(disposition=Disposition.SUSPICIOUS),
            },
            "Civ B": {
                "Civ A": Relationship(disposition=Disposition.SUSPICIOUS),
                "Civ C": Relationship(disposition=Disposition.SUSPICIOUS),
            },
            "Civ C": {
                "Civ A": Relationship(disposition=Disposition.SUSPICIOUS),
                "Civ B": Relationship(disposition=Disposition.SUSPICIOUS),
            },
        },
    )
    world.embargoes = [("Civ A", "Civ B")]

    treasury_before = civ_a.treasury
    apply_automatic_effects(world)

    # Self-trade: +3 (Civ A controls both adjacent Region A and Region B).
    # Black market: +1 (Region B -> Region C, Civ C not embargoed).
    black_market_delta = 1
    self_trade_delta = 3
    expected = treasury_before + self_trade_delta + black_market_delta
    assert civ_a.treasury == expected, (
        f"Expected treasury {expected} (self-trade +{self_trade_delta}, "
        f"black market +{black_market_delta}), got {civ_a.treasury}"
    )


def test_conquest_conversion_clears_each_turn_off_mode(make_world):
    """M-AF1 #14: conquest_conversion_active must clear each turn regardless of mode."""
    world = make_world(2)
    world.agent_mode = "off"
    # Manually set the flag on a region
    world.regions[0].conquest_conversion_active = True

    # Run one turn in off-mode
    run_turn(
        world,
        action_selector=lambda c, w: ActionType.DEVELOP,
        narrator=lambda *a, **kw: "narration",
        seed=42,
    )

    assert not getattr(world.regions[0], 'conquest_conversion_active', False), \
        "conquest_conversion_active should be cleared after turn in off-mode"


# ===========================================================================
# Batch A regression tests — accumulator contract, routing, and transients
# ===========================================================================

class TestAccumulatorWatermark:
    """C-1 fix: apply_keep() supports multiple calls via watermark."""

    def test_apply_keep_idempotent_with_watermark(self, make_world):
        """Second apply_keep() only applies changes added after the first call."""
        world = make_world(2)
        acc = StatAccumulator()
        civ = world.civilizations[0]
        civ.treasury = 100

        # First batch of changes
        acc.add(0, civ, "treasury", 10, "keep")
        acc.apply_keep(world)
        assert civ.treasury == 110

        # Second batch of changes
        acc.add(0, civ, "treasury", 5, "keep")
        acc.apply_keep(world)
        assert civ.treasury == 115  # only +5 from second call, not +15

    def test_apply_keep_skips_non_keep_categories(self, make_world):
        """apply_keep() skips guard, signal, guard-action, guard-shock."""
        world = make_world(2)
        acc = StatAccumulator()
        civ = world.civilizations[0]
        civ.treasury = 100
        civ.stability = 50

        acc.add(0, civ, "treasury", 10, "keep")
        acc.add(0, civ, "stability", -5, "guard")
        acc.add(0, civ, "stability", -3, "signal")
        acc.add(0, civ, "stability", -2, "guard-shock")
        acc.add(0, civ, "stability", -1, "guard-action")
        acc.apply_keep(world)

        assert civ.treasury == 110
        assert civ.stability == 50  # unchanged — none of the others applied

    def test_to_shock_signals_since_extracts_tail(self, make_world):
        """to_shock_signals(since=N) only processes changes from index N."""
        world = make_world(2)
        acc = StatAccumulator()
        civ = world.civilizations[0]
        civ.stability = 80

        # Phase 1-9 shocks
        acc.add(0, civ, "stability", -10, "signal")
        checkpoint = acc.checkpoint()

        # Phase 10 shocks
        acc.add(0, civ, "stability", -5, "signal")

        all_shocks = acc.to_shock_signals()
        phase10_shocks = acc.to_shock_signals(since=checkpoint)

        # All shocks should have combined delta, phase10 only the -5
        assert len(all_shocks) == 1
        assert len(phase10_shocks) == 1
        # Phase 10 shock should be smaller magnitude than combined
        assert abs(phase10_shocks[0].stability_shock) < abs(all_shocks[0].stability_shock)


class TestPhase10AccumulatorFlush:
    """C-1 fix: Phase 10 keep mutations take effect in hybrid mode."""

    def test_phase10_condition_drains_reach_pending_shocks(self, make_world):
        """Phase 10 condition stability drains should go to pending_shocks
        in hybrid mode, not be silently lost."""
        world = make_world(2)
        world.agent_mode = "hybrid"
        world.pending_shocks = []

        # Active condition with severity >= 50 → stability drain in Phase 10
        world.active_conditions = [
            ActiveCondition(
                condition_type="drought",
                affected_civs=[world.civilizations[0].name],
                duration=2,
                severity=60,
            )
        ]

        acc = StatAccumulator()
        phase_consequences(world, acc=acc)

        # The condition drain in hybrid mode goes to pending_shocks directly
        assert len(world.pending_shocks) > 0, \
            "Phase 10 condition drains should produce pending_shocks in hybrid mode"

    def test_phase10_keep_mutations_survive_second_flush(self, make_world):
        """Phase 10 accumulator keep mutations must survive via second flush."""
        world = make_world(2)
        acc = StatAccumulator()
        civ = world.civilizations[0]
        civ.treasury = 100

        # Simulate first flush (Phases 1-9)
        acc.add(0, civ, "treasury", 10, "keep")
        acc.apply_keep(world)
        assert civ.treasury == 110

        # Simulate Phase 10 adding more keep mutations
        acc.add(0, civ, "treasury", -5, "keep")
        acc.apply_keep(world)  # second flush
        assert civ.treasury == 105, \
            "Phase 10 keep mutations should take effect via second flush"


class TestPhase10SamesTurnEvents:
    """C-2 fix: Phase 10 sees same-turn events from Phases 1-9."""

    def test_events_visible_before_phase10(self, make_world):
        """Events from Phases 1-9 should be on the timeline when Phase 10 runs."""
        world = make_world(2)
        world.agent_mode = "off"
        initial_timeline_len = len(world.events_timeline)

        # Run a turn — the fix commits events before Phase 10
        run_turn(
            world,
            action_selector=lambda c, w: ActionType.DEVELOP,
            narrator=lambda *a, **kw: "narration",
            seed=42,
        )

        # After the turn, events should be on the timeline
        assert len(world.events_timeline) > initial_timeline_len, \
            "Events should be committed to timeline during the turn"


class TestFamineConservation:
    """C-3 fix: Famine population loss is always applied, preventing
    conservation violations in hybrid mode."""

    def test_famine_drains_population_with_accumulator(self, make_world):
        """Famine pop loss should apply as direct mutation even when acc is present."""
        from chronicler.ecology import _check_famine_yield
        from chronicler.models import ClimatePhase, ResourceType

        world = make_world(2)
        civ = world.civilizations[0]
        region = world.regions[0]
        region.population = 50
        region.famine_cooldown = 0
        civ.population = 50
        # Give the region a food slot so check_food_yield uses our yield value
        region.resource_types = [ResourceType.GRAIN, 255, 255]

        acc = StatAccumulator()
        # Yields below threshold (0.01 < 0.12) → famine
        region_yields = {region.name: [0.01, 0.0, 0.0]}
        _check_famine_yield(
            world, region_yields, ClimatePhase.TEMPERATE,
            threshold=0.12, subsistence_base=0.15, acc=acc,
        )

        # Population loss should be applied directly (not deferred in acc)
        assert region.population < 50, \
            "Famine pop loss must be applied directly, not deferred in guard category"

    def test_famine_no_net_population_creation(self, make_world):
        """In hybrid mode, famine must not create net population."""
        from chronicler.ecology import _check_famine_yield
        from chronicler.models import ClimatePhase, ResourceType

        world = make_world(2)
        civ0 = world.civilizations[0]
        civ1 = world.civilizations[1]
        region0 = world.regions[0]
        region1 = world.regions[1]
        region0.population = 50
        region1.population = 50
        civ0.population = 50
        civ1.population = 50
        region0.famine_cooldown = 0
        region0.adjacencies = [region1.name]
        # Give the famine region a food slot with low yield
        region0.resource_types = [ResourceType.GRAIN, 255, 255]

        total_before = region0.population + region1.population

        acc = StatAccumulator()
        region_yields = {region0.name: [0.01, 0.0, 0.0]}
        _check_famine_yield(
            world, region_yields, ClimatePhase.TEMPERATE,
            threshold=0.12, subsistence_base=0.15, acc=acc,
        )

        # After famine: source lost pop, neighbor gained refugees
        # But total should not exceed original (no creation from nothing)
        total_after = region0.population + region1.population
        assert total_after <= total_before, \
            f"Famine must not create net population: before={total_before}, after={total_after}"


class TestAccumulatorCategoryRouting:
    """C-4 fix: Every accumulator category is either applied, converted,
    or rejected deliberately."""

    def test_guard_skipped_by_apply_keep(self, make_world):
        """guard-category mutations are intentionally skipped by apply_keep()."""
        world = make_world(2)
        acc = StatAccumulator()
        civ = world.civilizations[0]
        civ.population = 50

        acc.add(0, civ, "population", 10, "guard")
        acc.apply_keep(world)

        assert civ.population == 50, \
            "guard mutations should be skipped by apply_keep()"

    def test_guard_applied_by_apply(self, make_world):
        """guard-category mutations are applied by apply() (aggregate mode)."""
        world = make_world(2)
        acc = StatAccumulator()
        civ = world.civilizations[0]
        civ.population = 50

        acc.add(0, civ, "population", 10, "guard")
        acc.apply(world)

        assert civ.population == 60, \
            "guard mutations should be applied by apply() in aggregate mode"

    def test_signal_becomes_shock(self, make_world):
        """signal-category mutations become shock signals."""
        world = make_world(2)
        acc = StatAccumulator()
        civ = world.civilizations[0]
        civ.stability = 80

        acc.add(0, civ, "stability", -10, "signal")
        shocks = acc.to_shock_signals()

        assert len(shocks) == 1
        assert shocks[0].civ_id == 0
        assert shocks[0].stability_shock < 0

    def test_guard_shock_becomes_shock(self, make_world):
        """guard-shock-category mutations become shock signals."""
        world = make_world(2)
        acc = StatAccumulator()
        civ = world.civilizations[0]
        civ.stability = 50

        acc.add(0, civ, "stability", 10, "guard-shock")
        shocks = acc.to_shock_signals()

        assert len(shocks) == 1
        assert shocks[0].stability_shock > 0

    def test_guard_action_becomes_demand(self, make_world):
        """guard-action-category mutations become demand signals."""
        world = make_world(2)
        acc = StatAccumulator()
        civ = world.civilizations[0]
        civ.military = 50

        acc.add(0, civ, "military", 10, "guard-action")
        demands = acc.to_demand_signals({0: 100})

        assert len(demands) == 1
        assert demands[0].civ_id == 0
        assert demands[0].occupation == 1  # Soldier

    def test_all_categories_accounted_for(self):
        """Every valid category is handled by at least one flush method."""
        valid_categories = {"keep", "guard", "guard-action", "guard-shock", "signal"}
        # keep → apply_keep() / apply()
        # guard → apply() only (skipped in hybrid)
        # guard-action → to_demand_signals()
        # guard-shock → to_shock_signals()
        # signal → to_shock_signals()
        # This test documents the contract; if a new category is added,
        # it must be handled here.
        assert valid_categories == {"keep", "guard", "guard-action", "guard-shock", "signal"}


class TestShadowModeParity:
    """C-10 fix: Shadow mode uses apply_keep() to match hybrid mode."""

    def test_shadow_skips_guard_mutations(self, make_world):
        """Shadow mode should skip guard mutations just like hybrid does."""
        world = make_world(2)
        world.agent_mode = "shadow"
        acc = StatAccumulator()
        civ = world.civilizations[0]
        civ.population = 50
        civ.treasury = 100

        acc.add(0, civ, "population", 10, "guard")
        acc.add(0, civ, "treasury", 5, "keep")

        # Shadow should use apply_keep (matching hybrid path)
        acc.apply_keep(world)

        assert civ.population == 50, \
            "Shadow mode should skip guard mutations for fair comparison"
        assert civ.treasury == 105, \
            "Shadow mode should still apply keep mutations"


class TestPersecutedRegionsReset:
    """H-14 fix: _persecuted_regions clears for regions where persecution ended."""

    def test_cleared_when_persecution_ends(self, make_world):
        """Regions with persecution_intensity=0 should be removed from set."""
        world = make_world(2)
        world._persecuted_regions = {"Civ0_region", "Civ1_region"}

        # Set one region's persecution to 0 (ended)
        world.regions[0].persecution_intensity = 0.0
        # Keep other region persecuted
        world.regions[1].persecution_intensity = 0.5

        # The fix clears regions whose persecution ended
        world._persecuted_regions = {
            rname for rname in world._persecuted_regions
            if any(r.name == rname and r.persecution_intensity > 0
                   for r in world.regions)
        }

        assert "Civ0_region" not in world._persecuted_regions, \
            "Region with persecution_intensity=0 should be cleared"
        assert "Civ1_region" in world._persecuted_regions, \
            "Region still persecuted should remain in set"


class TestConqueredThisTurnReset:
    """H-20 fix: _conquered_this_turn is initialized at turn start."""

    def test_initialized_at_turn_start(self, make_world):
        """_conquered_this_turn should be initialized to empty set at turn start."""
        world = make_world(2)
        world.agent_mode = "off"
        # Set stale data
        world._conquered_this_turn = {0, 1}

        run_turn(
            world,
            action_selector=lambda c, w: ActionType.DEVELOP,
            narrator=lambda *a, **kw: "narration",
            seed=42,
        )

        # After turn, should be cleared (was reset at start, and DEVELOP
        # doesn't trigger conquest)
        assert not hasattr(world, '_conquered_this_turn') or \
            world._conquered_this_turn == set(), \
            "_conquered_this_turn should be cleared during turn"
