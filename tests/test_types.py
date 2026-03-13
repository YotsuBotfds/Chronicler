"""Tests for shared types."""
from pathlib import Path
from chronicler.types import RunResult


def test_run_result_construction():
    result = RunResult(
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
    assert result.seed == 42
    assert result.war_count == 3
    assert result.dominant_faction == "Kethani Empire"
    assert result.boring_civs == []
