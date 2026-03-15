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
)
from chronicler.factions import count_faction_wins, _event_is_win
from chronicler.factions import generate_faction_candidates, inherit_grudges_with_factions, FACTION_CANDIDATE_TYPE, GP_ROLE_TO_FACTION


class TestFactionDataModel:
    def test_faction_type_values(self):
        assert FactionType.MILITARY.value == "military"
        assert FactionType.MERCHANT.value == "merchant"
        assert FactionType.CULTURAL.value == "cultural"

    def test_faction_state_defaults(self):
        fs = FactionState()
        assert fs.influence[FactionType.MILITARY] == pytest.approx(0.33)
        assert fs.influence[FactionType.MERCHANT] == pytest.approx(0.33)
        assert fs.influence[FactionType.CULTURAL] == pytest.approx(0.34)
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
        fs.influence[FactionType.CULTURAL] = 0.2
        normalize_influence(fs)
        assert sum(fs.influence.values()) == pytest.approx(1.0)

    def test_normalize_enforces_floor(self):
        fs = FactionState()
        fs.influence[FactionType.MILITARY] = 0.95
        fs.influence[FactionType.MERCHANT] = 0.04
        fs.influence[FactionType.CULTURAL] = 0.01
        normalize_influence(fs)
        assert fs.influence[FactionType.CULTURAL] >= 0.05
        assert fs.influence[FactionType.MERCHANT] >= 0.05
        assert sum(fs.influence.values()) == pytest.approx(1.0)

    def test_normalize_after_zero(self):
        fs = FactionState()
        fs.influence[FactionType.MILITARY] = 1.0
        fs.influence[FactionType.MERCHANT] = 0.0
        fs.influence[FactionType.CULTURAL] = 0.0
        normalize_influence(fs)
        assert fs.influence[FactionType.MERCHANT] >= 0.05
        assert fs.influence[FactionType.CULTURAL] >= 0.05


class TestCoreHelpers:
    def test_shift_faction_influence(self):
        fs = FactionState()
        shift_faction_influence(fs, FactionType.MILITARY, 0.10)
        assert fs.influence[FactionType.MILITARY] > 0.33
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
        # Default: CULTURAL dominant at 0.34
        mod = get_faction_weight_modifier(civ, ActionType.WAR)
        assert mod == pytest.approx(0.4 ** 0.34, rel=0.01)

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


class TestPowerStruggle:
    def test_trigger_when_close_and_above_threshold(self):
        fs = FactionState()
        fs.influence[FactionType.MILITARY] = 0.36
        fs.influence[FactionType.MERCHANT] = 0.34
        fs.influence[FactionType.CULTURAL] = 0.30
        result = check_power_struggle(fs)
        assert result is not None
        assert FactionType.MILITARY in result
        assert FactionType.MERCHANT in result

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
