"""Tests for interestingness scoring."""
import pytest
from pathlib import Path
from chronicler.interestingness import score_run, find_boring_civs, DEFAULT_WEIGHTS
from chronicler.types import RunResult


@pytest.fixture
def sample_result():
    return RunResult(
        seed=42,
        output_dir=Path("output/seed_42"),
        war_count=3,
        collapse_count=1,
        named_event_count=5,
        distinct_action_count=4,
        reflection_count=2,
        tech_advancement_count=1,
        max_stat_swing=12.5,
        action_distribution={
            "Kethani Empire": {"develop": 10, "trade": 5, "war": 3},
            "Dorrathi Clans": {"war": 8, "expand": 4, "develop": 6},
        },
        dominant_faction="Kethani Empire",
        total_turns=50,
        boring_civs=[],
    )


class TestScoreRun:
    def test_default_weights(self, sample_result):
        score = score_run(sample_result)
        # war_count(3)*3 + collapse_count(1)*5 + named_event_count(5)*1
        # + distinct_action_count(4)*1 + reflection_count(2)*2
        # + tech_advancement_count(1)*2 + max_stat_swing(12.5)*1
        expected = 3*3 + 1*5 + 5*1 + 4*1 + 2*2 + 1*2 + 12.5*1
        assert score == pytest.approx(expected)

    def test_custom_weights_override_defaults(self, sample_result):
        custom = {"war_count": 10, "collapse_count": 0}
        score = score_run(sample_result, weights=custom)
        # war_count(3)*10 + collapse_count(1)*0 + rest at defaults
        expected = 3*10 + 1*0 + 5*1 + 4*1 + 2*2 + 1*2 + 12.5*1
        assert score == pytest.approx(expected)

    def test_all_zeros_result(self):
        result = RunResult(
            seed=1, output_dir=Path("."), war_count=0, collapse_count=0,
            named_event_count=0, distinct_action_count=0, reflection_count=0,
            tech_advancement_count=0, max_stat_swing=0.0,
            action_distribution={}, dominant_faction="None", total_turns=10,
            boring_civs=[],
        )
        assert score_run(result) == 0.0


class TestFindBoringCivs:
    def test_no_boring_civs(self):
        dist = {
            "Civ A": {"develop": 5, "trade": 5, "war": 5},
            "Civ B": {"expand": 4, "develop": 4, "war": 4},
        }
        result = RunResult(
            seed=1, output_dir=Path("."), war_count=0, collapse_count=0,
            named_event_count=0, distinct_action_count=3, reflection_count=0,
            tech_advancement_count=0, max_stat_swing=0.0,
            action_distribution=dist, dominant_faction="Civ A",
            total_turns=10, boring_civs=[],
        )
        assert find_boring_civs(result) == []

    def test_detects_boring_civ(self):
        dist = {
            "Boring Civ": {"develop": 18, "trade": 1, "war": 1},  # 90% develop
            "Good Civ": {"develop": 5, "trade": 5, "war": 5},
        }
        result = RunResult(
            seed=1, output_dir=Path("."), war_count=0, collapse_count=0,
            named_event_count=0, distinct_action_count=3, reflection_count=0,
            tech_advancement_count=0, max_stat_swing=0.0,
            action_distribution=dist, dominant_faction="Good Civ",
            total_turns=20, boring_civs=[],
        )
        boring = find_boring_civs(result)
        assert any("Boring Civ" in b for b in boring)
        assert not any("Good Civ" in b for b in boring)

    def test_threshold_boundary(self):
        # Exactly 60% should NOT be boring (threshold is >60%)
        dist = {"Edge Civ": {"develop": 6, "trade": 4}}
        result = RunResult(
            seed=1, output_dir=Path("."), war_count=0, collapse_count=0,
            named_event_count=0, distinct_action_count=2, reflection_count=0,
            tech_advancement_count=0, max_stat_swing=0.0,
            action_distribution=dist, dominant_faction="Edge Civ",
            total_turns=10, boring_civs=[],
        )
        assert find_boring_civs(result) == []

    def test_empty_distribution(self):
        result = RunResult(
            seed=1, output_dir=Path("."), war_count=0, collapse_count=0,
            named_event_count=0, distinct_action_count=0, reflection_count=0,
            tech_advancement_count=0, max_stat_swing=0.0,
            action_distribution={}, dominant_faction="None",
            total_turns=10, boring_civs=[],
        )
        assert find_boring_civs(result) == []


class TestDefaultWeights:
    def test_all_expected_keys_present(self):
        expected_keys = {
            "war_count", "collapse_count", "named_event_count",
            "distinct_action_count", "reflection_count",
            "tech_advancement_count", "max_stat_swing",
        }
        assert set(DEFAULT_WEIGHTS.keys()) == expected_keys
