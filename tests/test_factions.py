"""Tests for faction system — influence, power struggles, weight modifiers, succession."""
import pytest
from chronicler.models import FactionType, FactionState, Civilization, Leader, CivSnapshot
from chronicler.models import WorldState, Event
from chronicler.factions import (
    normalize_influence,
    shift_faction_influence,
    get_dominant_faction,
    get_leader_faction_alignment,
    TRAIT_FACTION_MAP,
    FOCUS_FACTION_MAP,
    TITHE_RATE,
)
from chronicler.factions import count_faction_wins, _event_is_win
from chronicler.factions import (
    generate_faction_candidates, inherit_grudges_with_factions,
    FACTION_CANDIDATE_TYPE, GP_ROLE_TO_FACTION,
    _build_gp_successor_candidate, _select_succession_winner,
    _apply_gp_successor_winner, _build_succession_resolution_description,
)
from chronicler.utils import STAT_FLOOR


class TestFactionDataModel:
    def test_faction_type_values(self):
        assert FactionType.MILITARY.value == "military"
        assert FactionType.MERCHANT.value == "merchant"
        assert FactionType.CULTURAL.value == "cultural"
        assert FactionType.CLERGY.value == "clergy"

    def test_faction_state_defaults(self):
        fs = FactionState()
        assert fs.influence[FactionType.MILITARY] == pytest.approx(0.25)
        assert fs.influence[FactionType.MERCHANT] == pytest.approx(0.25)
        assert fs.influence[FactionType.CULTURAL] == pytest.approx(0.25)
        assert fs.influence[FactionType.CLERGY] == pytest.approx(0.25)
        assert fs.power_struggle is False
        assert fs.power_struggle_turns == 0

    def test_civilization_has_factions(self):
        leader = Leader(name="Test", trait="bold", reign_start=0)
        civ = Civilization(
            name="TestCiv", population=50, military=40, economy=60,
            culture=30, stability=70, regions=["r1"], leader=leader,
        )
        assert isinstance(civ.factions, FactionState)
        assert civ.founded_turn == 0

    def test_civ_snapshot_has_factions(self):
        snap = CivSnapshot(
            population=50, military=40, economy=60, culture=30,
            stability=70, treasury=100, asabiya=0.5, tech_era="tribal",
            trait="bold", regions=["r1"], leader_name="Test", alive=True,
        )
        assert snap.factions is None


class TestNormalization:
    def test_normalize_sums_to_one(self):
        fs = FactionState()
        fs.influence[FactionType.MILITARY] = 0.5
        fs.influence[FactionType.MERCHANT] = 0.3
        fs.influence[FactionType.CULTURAL] = 0.1
        fs.influence[FactionType.CLERGY] = 0.1
        normalize_influence(fs)
        assert sum(fs.influence.values()) == pytest.approx(1.0)
        # All four factions should be present and at or above floor
        for ft in FactionType:
            assert ft in fs.influence

    def test_normalize_enforces_floor(self):
        fs = FactionState()
        fs.influence[FactionType.MILITARY] = 0.90
        fs.influence[FactionType.MERCHANT] = 0.04
        fs.influence[FactionType.CULTURAL] = 0.01
        fs.influence[FactionType.CLERGY] = 0.05
        normalize_influence(fs)
        # FACTION_FLOOR is 0.08 — all factions must be at or above it
        for ft in FactionType:
            assert fs.influence[ft] >= 0.08, f"{ft} below floor"
        assert sum(fs.influence.values()) == pytest.approx(1.0)

    def test_normalize_after_zero(self):
        fs = FactionState()
        fs.influence[FactionType.MILITARY] = 1.0
        fs.influence[FactionType.MERCHANT] = 0.0
        fs.influence[FactionType.CULTURAL] = 0.0
        fs.influence[FactionType.CLERGY] = 0.0
        normalize_influence(fs)
        # FACTION_FLOOR is 0.08 — all factions must be at or above it
        assert fs.influence[FactionType.MERCHANT] >= 0.08
        assert fs.influence[FactionType.CULTURAL] >= 0.08
        assert fs.influence[FactionType.CLERGY] >= 0.08
        assert sum(fs.influence.values()) == pytest.approx(1.0)

    def test_normalize_handles_all_zero_input(self):
        fs = FactionState()
        for faction_type in FactionType:
            fs.influence[faction_type] = 0.0
        normalize_influence(fs)
        assert sum(fs.influence.values()) == pytest.approx(1.0)
        for faction_type in FactionType:
            assert fs.influence[faction_type] == pytest.approx(0.25)


class TestCoreHelpers:
    def test_shift_faction_influence(self):
        fs = FactionState()
        shift_faction_influence(fs, FactionType.MILITARY, 0.10)
        assert fs.influence[FactionType.MILITARY] > 0.25
        assert sum(fs.influence.values()) == pytest.approx(1.0)

    def test_get_dominant_faction(self):
        fs = FactionState()
        fs.influence[FactionType.MILITARY] = 0.6
        fs.influence[FactionType.MERCHANT] = 0.2
        fs.influence[FactionType.CULTURAL] = 0.2
        assert get_dominant_faction(fs) == FactionType.MILITARY

    def test_leader_alignment_military_trait(self):
        leader = Leader(name="Test", trait="aggressive", reign_start=0)
        fs = FactionState()
        fs.influence[FactionType.MILITARY] = 0.6
        fs.influence[FactionType.MERCHANT] = 0.2
        fs.influence[FactionType.CULTURAL] = 0.2
        assert get_leader_faction_alignment(leader, fs) == pytest.approx(0.6)

    def test_leader_alignment_neutral_trait(self):
        leader = Leader(name="Test", trait="stubborn", reign_start=0)
        fs = FactionState()
        assert get_leader_faction_alignment(leader, fs) == pytest.approx(0.5)

    def test_trait_faction_map_covers_actual_traits(self):
        mapped = set(TRAIT_FACTION_MAP.keys())
        actual_traits = {"ambitious", "cautious", "aggressive", "calculating",
                         "zealous", "opportunistic", "stubborn", "bold",
                         "shrewd", "visionary"}
        assert mapped.issubset(actual_traits)

    def test_focus_faction_map_covers_all_focuses(self):
        assert len(FOCUS_FACTION_MAP) == 15

    def test_clergy_alignment_reachable_from_zealous_trait(self):
        """H-27 regression: clergy must be reachable via leader traits."""
        leader = Leader(name="Test", trait="zealous", reign_start=0)
        fs = FactionState()
        fs.influence[FactionType.CLERGY] = 0.40
        alignment = get_leader_faction_alignment(leader, fs)
        assert alignment == pytest.approx(0.40), (
            "zealous trait should align with clergy faction"
        )

    def test_all_four_factions_reachable_from_traits(self):
        """H-27 regression: every FactionType must appear in TRAIT_FACTION_MAP values."""
        reachable = set(TRAIT_FACTION_MAP.values())
        for ft in FactionType:
            assert ft in reachable, (
                f"{ft} is not reachable from any leader trait in TRAIT_FACTION_MAP"
            )


def _make_world(turn: int = 10, events: list[Event] | None = None) -> WorldState:
    """Minimal WorldState for testing."""
    world = WorldState(name="test", seed=42, turn=turn)
    if events:
        world.events_timeline = events
    return world


def _make_civ(name: str = "TestCiv") -> Civilization:
    leader = Leader(name="Leader", trait="bold", reign_start=0)
    return Civilization(
        name=name, population=50, military=40, economy=60,
        culture=30, stability=70, regions=["r1"], leader=leader,
    )


class TestWinCounting:
    def test_military_war_win_attacker(self):
        events = [Event(turn=5, event_type="war", actors=["TestCiv", "Enemy"],
                        description="TestCiv attacked Enemy: attacker_wins.", importance=8)]
        world = _make_world(turn=10, events=events)
        civ = _make_civ()
        assert count_faction_wins(world, civ, FactionType.MILITARY, lookback=10) == 1

    def test_military_war_win_defender(self):
        events = [Event(turn=5, event_type="war", actors=["Enemy", "TestCiv"],
                        description="Enemy attacked TestCiv: defender_wins.", importance=8)]
        world = _make_world(turn=10, events=events)
        civ = _make_civ()
        assert count_faction_wins(world, civ, FactionType.MILITARY, lookback=10) == 1

    def test_military_war_loss_not_counted(self):
        events = [Event(turn=5, event_type="war", actors=["TestCiv", "Enemy"],
                        description="TestCiv attacked Enemy: defender_wins.", importance=8)]
        world = _make_world(turn=10, events=events)
        civ = _make_civ()
        assert count_faction_wins(world, civ, FactionType.MILITARY, lookback=10) == 0

    def test_military_expansion_success(self):
        events = [Event(turn=5, event_type="expand", actors=["TestCiv"],
                        description="TestCiv expanded.", importance=6)]
        world = _make_world(turn=10, events=events)
        civ = _make_civ()
        assert count_faction_wins(world, civ, FactionType.MILITARY, lookback=10) == 1

    def test_merchant_trade_success(self):
        events = [Event(turn=5, event_type="trade", actors=["TestCiv", "Partner"],
                        description="TestCiv traded.", importance=3)]
        world = _make_world(turn=10, events=events)
        civ = _make_civ()
        assert count_faction_wins(world, civ, FactionType.MERCHANT, lookback=10) == 1

    def test_merchant_trade_failure_not_counted(self):
        events = [Event(turn=5, event_type="trade", actors=["TestCiv"],
                        description="No partners.", importance=2)]
        world = _make_world(turn=10, events=events)
        civ = _make_civ()
        assert count_faction_wins(world, civ, FactionType.MERCHANT, lookback=10) == 0

    def test_cultural_work(self):
        events = [Event(turn=5, event_type="cultural_work", actors=["TestCiv"],
                        description="Cultural work.", importance=6)]
        world = _make_world(turn=10, events=events)
        civ = _make_civ()
        assert count_faction_wins(world, civ, FactionType.CULTURAL, lookback=10) == 1

    def test_cultural_movement_adoption(self):
        events = [Event(turn=5, event_type="movement_adoption", actors=["TestCiv", "Origin"],
                        description="Adopted.", importance=5)]
        world = _make_world(turn=10, events=events)
        civ = _make_civ()
        assert count_faction_wins(world, civ, FactionType.CULTURAL, lookback=10) == 1

    def test_lookback_window_respected(self):
        events = [Event(turn=1, event_type="war", actors=["TestCiv", "Enemy"],
                        description="TestCiv attacked Enemy: attacker_wins.", importance=8)]
        world = _make_world(turn=20, events=events)
        civ = _make_civ()
        assert count_faction_wins(world, civ, FactionType.MILITARY, lookback=10) == 0


from chronicler.models import ActionType
from chronicler.factions import get_faction_weight_modifier, FACTION_WEIGHTS


class TestWeightModifier:
    def test_military_dominant_war_weight(self):
        civ = _make_civ()
        civ.factions.influence[FactionType.MILITARY] = 0.6
        civ.factions.influence[FactionType.MERCHANT] = 0.2
        civ.factions.influence[FactionType.CULTURAL] = 0.2
        mod = get_faction_weight_modifier(civ, ActionType.WAR)
        assert mod == pytest.approx(1.8 ** 0.6, rel=0.01)

    def test_equal_influence_mild_bias(self):
        civ = _make_civ()
        # Default: all factions are equal; insertion order makes MILITARY dominant.
        mod = get_faction_weight_modifier(civ, ActionType.WAR)
        assert mod == pytest.approx(1.8 ** 0.25, rel=0.01)

    def test_unlisted_action_returns_one(self):
        civ = _make_civ()
        civ.factions.influence[FactionType.MILITARY] = 0.6
        civ.factions.influence[FactionType.MERCHANT] = 0.2
        civ.factions.influence[FactionType.CULTURAL] = 0.2
        # INVEST_CULTURE not in MILITARY table -> 1.0^0.6 = 1.0
        mod = get_faction_weight_modifier(civ, ActionType.INVEST_CULTURE)
        assert mod == pytest.approx(1.0)


from chronicler.factions import check_power_struggle, get_struggling_factions, resolve_power_struggle
from chronicler.factions import tick_factions
from chronicler.factions import total_effective_capacity


class TestPowerStruggle:
    def test_trigger_when_close_and_above_threshold(self):
        fs = FactionState()
        fs.influence[FactionType.MILITARY] = 0.44
        fs.influence[FactionType.MERCHANT] = 0.42
        fs.influence[FactionType.CULTURAL] = 0.08
        fs.influence[FactionType.CLERGY] = 0.06
        result = check_power_struggle(fs)
        assert result is not None
        assert FactionType.MILITARY in result
        assert FactionType.MERCHANT in result

    def test_trigger_when_second_faction_is_viable_in_four_faction_balance(self):
        fs = FactionState()
        fs.influence[FactionType.MILITARY] = 0.34
        fs.influence[FactionType.MERCHANT] = 0.31
        fs.influence[FactionType.CULTURAL] = 0.20
        fs.influence[FactionType.CLERGY] = 0.15
        result = check_power_struggle(fs)
        assert result is not None

    def test_no_trigger_when_gap_too_large(self):
        fs = FactionState()
        fs.influence[FactionType.MILITARY] = 0.50
        fs.influence[FactionType.MERCHANT] = 0.30
        fs.influence[FactionType.CULTURAL] = 0.20
        assert check_power_struggle(fs) is None

    def test_no_trigger_when_below_threshold(self):
        fs = FactionState()
        fs.influence[FactionType.MILITARY] = 0.50
        fs.influence[FactionType.MERCHANT] = 0.26
        fs.influence[FactionType.CULTURAL] = 0.24
        assert check_power_struggle(fs) is None

    def test_resolve_power_struggle_picks_winner(self):
        civ = _make_civ()
        civ.factions.influence[FactionType.MILITARY] = 0.36
        civ.factions.influence[FactionType.MERCHANT] = 0.34
        civ.factions.influence[FactionType.CULTURAL] = 0.30
        civ.factions.power_struggle = True
        civ.factions.power_struggle_turns = 6
        events = [Event(turn=8, event_type="war", actors=["TestCiv", "Enemy"],
                        description="TestCiv attacked Enemy: attacker_wins.", importance=8)]
        world = _make_world(turn=10, events=events)
        result_events = resolve_power_struggle(civ, world)
        assert civ.factions.power_struggle is False
        assert civ.factions.power_struggle_turns == 0
        assert civ.factions.influence[FactionType.MILITARY] > 0.36
        assert len(result_events) == 1
        assert result_events[0].event_type == "power_struggle_resolved"

    def test_clergy_events_count_as_wins(self):
        civ = _make_civ()
        temple_event = Event(
            turn=10,
            event_type="build_started",
            actors=[civ.name],
            description="Temples were commissioned in the capital",
            importance=5,
        )
        assert _event_is_win(temple_event, civ, FactionType.CLERGY) is True


class TestTickFactions:
    def test_tick_shifts_influence_on_war_win(self):
        civ = _make_civ()
        world = _make_world(turn=10, events=[Event(
            turn=10, event_type="war", actors=["TestCiv", "Enemy"],
            description="TestCiv attacked Enemy: attacker_wins.", importance=8,
        )])
        world.civilizations = [civ]
        mil_before = civ.factions.influence[FactionType.MILITARY]
        tick_factions(world)
        assert civ.factions.influence[FactionType.MILITARY] > mil_before

    def test_tick_skips_power_struggle_during_crisis(self):
        civ = _make_civ()
        civ.factions.power_struggle = True
        civ.factions.power_struggle_turns = 3
        civ.succession_crisis_turns_remaining = 2
        world = _make_world(turn=10)
        world.civilizations = [civ]
        tick_factions(world)
        assert civ.factions.power_struggle_turns == 3

    def test_tick_emits_dominance_shift_event(self):
        civ = _make_civ()
        civ.factions.influence[FactionType.MILITARY] = 0.50
        civ.factions.influence[FactionType.MERCHANT] = 0.30
        civ.factions.influence[FactionType.CULTURAL] = 0.20
        world = _make_world(turn=10, events=[Event(
            turn=10, event_type="war", actors=["TestCiv", "Enemy"],
            description="TestCiv attacked Enemy: defender_wins.", importance=8,
        )] * 5)
        world.civilizations = [civ]
        events = tick_factions(world)
        shift_events = [e for e in events if e.event_type == "faction_dominance_shift"]
        assert len(shift_events) == 1

    def test_tithe_routes_through_accumulator_keep_in_agent_mode(self):
        from chronicler.accumulator import StatAccumulator

        civ = _make_civ()
        civ.treasury = 100
        civ.last_income = 80
        civ.factions.influence[FactionType.CLERGY] = 0.20
        world = _make_world(turn=10)
        world.civilizations = [civ]

        acc = StatAccumulator()
        tick_factions(world, acc=acc)

        assert civ.treasury == 100

        acc.apply_keep(world)

        assert civ.treasury == 100 + int(TITHE_RATE * civ.last_income)

    def test_pending_faction_shift_is_normalized_before_dominance_check(self):
        civ = _make_civ()
        civ.factions.influence[FactionType.MILITARY] = 0.25
        civ.factions.influence[FactionType.MERCHANT] = 0.45
        civ.factions.influence[FactionType.CULTURAL] = 0.15
        civ.factions.influence[FactionType.CLERGY] = 0.15
        civ.factions.pending_faction_shift = FactionType.MILITARY.value
        world = _make_world(turn=10)
        world.civilizations = [civ]

        events = tick_factions(world)

        assert civ.factions.pending_faction_shift is None
        assert sum(civ.factions.influence.values()) == pytest.approx(1.0)
        assert get_dominant_faction(civ.factions) == FactionType.MILITARY
        assert any(e.event_type == "faction_dominance_shift" for e in events)

    def test_power_struggle_stability_clamps_to_stat_floor(self, monkeypatch):
        civ = _make_civ()
        civ.stability = 20
        civ.factions.power_struggle = True
        civ.factions.power_struggle_turns = 2
        world = _make_world(turn=10)
        world.civilizations = [civ]

        monkeypatch.setitem(STAT_FLOOR, "stability", 25)

        tick_factions(world)

        assert civ.stability == 25


class TestCandidateGeneration:
    def test_internal_candidates_per_faction(self):
        civ = _make_civ()
        world = _make_world()
        world.civilizations = [civ]
        world.relationships = {}
        candidates = generate_faction_candidates(civ, world)
        types = {c["faction"] for c in candidates}
        assert "military" in types
        assert "merchant" in types
        assert "cultural" in types

    def test_weak_faction_excluded(self):
        civ = _make_civ()
        civ.factions.influence[FactionType.CULTURAL] = 0.10
        civ.factions.influence[FactionType.MILITARY] = 0.50
        civ.factions.influence[FactionType.MERCHANT] = 0.40
        world = _make_world()
        world.civilizations = [civ]
        world.relationships = {}
        candidates = generate_faction_candidates(civ, world)
        factions = {c["faction"] for c in candidates}
        assert "cultural" not in factions

    def test_candidate_type_mapping(self):
        assert FACTION_CANDIDATE_TYPE[FactionType.MILITARY] == "general"
        assert FACTION_CANDIDATE_TYPE[FactionType.MERCHANT] == "elected"
        assert FACTION_CANDIDATE_TYPE[FactionType.CULTURAL] == "heir"


class TestGrudgeInheritance:
    def test_same_faction_high_rate(self):
        old = Leader(name="Old", trait="aggressive", reign_start=0)
        old.grudges = [{"target": "Enemy", "intensity": 1.0}]
        new = Leader(name="New", trait="bold", reign_start=10)
        fs = FactionState()
        inherit_grudges_with_factions(old, new, fs)
        assert len(new.grudges) == 1
        assert new.grudges[0]["intensity"] == pytest.approx(0.7)

    def test_different_faction_low_rate(self):
        old = Leader(name="Old", trait="aggressive", reign_start=0)
        old.grudges = [{"target": "Enemy", "intensity": 1.0}]
        new = Leader(name="New", trait="cautious", reign_start=10)
        fs = FactionState()
        inherit_grudges_with_factions(old, new, fs)
        assert len(new.grudges) == 1
        assert new.grudges[0]["intensity"] == pytest.approx(0.3)

    def test_neutral_trait_default_rate(self):
        old = Leader(name="Old", trait="stubborn", reign_start=0)
        old.grudges = [{"target": "Enemy", "intensity": 1.0}]
        new = Leader(name="New", trait="opportunistic", reign_start=10)
        fs = FactionState()
        inherit_grudges_with_factions(old, new, fs)
        assert new.grudges[0]["intensity"] == pytest.approx(0.5)

    def test_low_intensity_filtered(self):
        old = Leader(name="Old", trait="aggressive", reign_start=0)
        old.grudges = [{"target": "Enemy", "intensity": 0.01}]
        new = Leader(name="New", trait="cautious", reign_start=10)
        fs = FactionState()
        inherit_grudges_with_factions(old, new, fs)
        assert len(new.grudges) == 0


class TestGPSuccessorCandidate:
    def test_build_gp_successor_candidate_includes_lineage_fields(self):
        from chronicler.models import GreatPerson
        gp = GreatPerson(
            name="General Kiran", role="general", trait="bold",
            civilization="TestCiv", origin_civilization="TestCiv",
            born_turn=5, source="agent", agent_id=100, parent_id_0=50,
            dynasty_id=7,
        )
        civ = _make_civ()
        dominant = FactionType.MILITARY
        candidate = _build_gp_successor_candidate(gp, civ, dominant)
        assert candidate["agent_id"] == 100
        assert candidate["parent_id_0"] == 50
        assert candidate["dynasty_id"] == 7
        assert candidate["gp_base_name"] is None  # base_name not set
        assert candidate["source"] == "great_person"
        assert candidate["gp_name"] == "General Kiran"
        assert candidate["gp_trait"] == "bold"

    def test_build_gp_successor_candidate_adds_dominant_bonus(self):
        from chronicler.models import GreatPerson
        gp = GreatPerson(
            name="General Kiran", role="general", trait="bold",
            civilization="TestCiv", origin_civilization="TestCiv",
            born_turn=5, source="agent",
        )
        civ = _make_civ()
        civ.factions.influence[FactionType.MILITARY] = 0.40
        # When dominant matches GP faction
        candidate = _build_gp_successor_candidate(gp, civ, FactionType.MILITARY)
        assert candidate["weight"] == pytest.approx(0.50)
        # When dominant doesn't match
        candidate2 = _build_gp_successor_candidate(gp, civ, FactionType.MERCHANT)
        assert candidate2["weight"] == pytest.approx(0.40)


class TestSuccessionHelpers:
    def test_select_succession_winner_empty_returns_none(self):
        import random
        rng = random.Random(42)
        assert _select_succession_winner([], rng) is None

    def test_apply_gp_successor_winner_copies_name_and_trait(self):
        from chronicler.models import GreatPerson
        civ = _make_civ()
        gp = GreatPerson(
            name="High Priestess Zara", role="prophet", trait="zealous",
            civilization="TestCiv", origin_civilization="TestCiv",
            born_turn=5, source="agent",
        )
        gp.base_name = "Zara"
        civ.great_persons.append(gp)
        new_leader = Leader(name="Placeholder", trait="cautious", reign_start=10,
                            throne_name=None)
        winner = {
            "gp_name": "High Priestess Zara", "gp_trait": "zealous",
            "gp_base_name": "Zara", "source": "great_person",
        }
        _apply_gp_successor_winner(civ, new_leader, winner)
        # Throne name is stripped base name
        assert new_leader.throne_name == "Zara"
        assert new_leader.trait == "zealous"
        # Display name should be a composed regnal name containing the throne name
        assert "Zara" in new_leader.name
        assert new_leader.regnal_ordinal == 0
        assert civ.regnal_name_counts.get("Zara", 0) == 1

    def test_apply_gp_successor_winner_marks_gp_ascended(self):
        from chronicler.models import GreatPerson
        civ = _make_civ()
        gp = GreatPerson(
            name="Warchief Kiran", role="general", trait="bold",
            civilization="TestCiv", origin_civilization="TestCiv",
            born_turn=5, source="agent",
        )
        gp.agent_id = 99
        civ.great_persons.append(gp)
        new_leader = Leader(name="Temp", trait="bold", reign_start=10, throne_name=None)
        winner = {"gp_name": "Warchief Kiran", "gp_trait": "bold",
                  "gp_base_name": "Kiran", "agent_id": 99}
        _apply_gp_successor_winner(civ, new_leader, winner)
        assert gp.active is False
        assert gp.alive is False
        assert gp.fate == "ascended_to_leadership"

    def test_build_succession_resolution_description_matches_existing_text(self):
        civ = _make_civ()
        old_leader = Leader(name="OldKing", trait="bold", reign_start=0)
        new_leader = Leader(name="NewKing", trait="cautious", reign_start=10)
        desc = _build_succession_resolution_description(civ, old_leader, new_leader)
        assert "The succession crisis in TestCiv ends:" in desc
        assert "NewKing rises to power" in desc
        assert "fall of OldKing" in desc


class TestPowerStruggleEffectiveness:
    def test_power_struggle_reduces_action_effectiveness(self):
        from chronicler.action_engine import _power_struggle_factor
        civ = _make_civ()
        assert _power_struggle_factor(civ) == 1.0
        civ.factions.power_struggle = True
        assert _power_struggle_factor(civ) == 0.8


class TestSecessionViability:
    def test_total_effective_capacity(self):
        from chronicler.models import Region
        regions = [
            Region(name="plains1", terrain="plains", carrying_capacity=50, resources="grain"),
            Region(name="desert1", terrain="desert", carrying_capacity=20, resources="none"),
        ]
        world = _make_world()
        world.regions = regions
        civ = _make_civ()
        civ.regions = ["plains1", "desert1"]
        cap = total_effective_capacity(civ, world)
        assert cap > 0


class TestHolyWarClergyBoost:
    """B1 regression: conquest_conversion_active must survive compute_conversion_signals
    so that tick_factions can read it and apply EVT_HOLY_WAR_WON to clergy influence."""

    def test_clergy_boost_after_conversion_signals(self, make_world):
        from chronicler.models import Event, FactionType, Region
        from chronicler.factions import tick_factions, EVT_HOLY_WAR_WON
        from chronicler.religion import compute_conversion_signals

        world = make_world(num_civs=2)
        civ = world.civilizations[0]
        region_name = civ.regions[0]

        # Set the one-shot conquest flag on the civ's region
        region_map = {r.name: r for r in world.regions}
        region_map[region_name].conquest_conversion_active = True

        # Add a war-win event on the current turn
        world.turn = 10
        world.events_timeline.append(Event(
            turn=10, event_type="war", actors=[civ.name, world.civilizations[1].name],
            description=f"{civ.name} attacked {world.civilizations[1].name}: attacker_wins.",
            importance=8,
        ))

        clergy_before = civ.factions.influence[FactionType.CLERGY]

        # Phase 10 order: compute_conversion_signals runs first, then tick_factions
        compute_conversion_signals(
            regions=world.regions,
            majority_beliefs={},
            belief_registry=[],
            snapshot=None,
        )
        tick_factions(world)

        clergy_after = civ.factions.influence[FactionType.CLERGY]
        # After normalization the raw +0.04 is diluted, but clergy must still
        # increase (it decreases without the fix because military's +0.05
        # gets spread and clergy gets nothing).
        assert clergy_after > clergy_before, (
            f"clergy influence should increase from holy-war bonus "
            f"but went from {clergy_before} to {clergy_after}"
        )
