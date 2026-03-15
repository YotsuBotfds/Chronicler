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
