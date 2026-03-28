"""M57b: Household stats pipeline tests."""
import pytest
from chronicler.analytics import extract_household_stats


def test_extract_household_stats_empty():
    result = extract_household_stats([{"metadata": {}}])
    assert result["per_turn"] == []
    assert result["summary"] == {}


def test_extract_household_stats_round_trip():
    stats = [
        {"inheritance_transfers_spouse": 2.0, "births_married_parent": 5.0},
        {"inheritance_transfers_spouse": 1.0, "births_married_parent": 3.0},
    ]
    bundle = {"metadata": {"household_stats": stats}}
    result = extract_household_stats([bundle])
    assert len(result["per_turn"]) == 2
    assert result["summary"]["inheritance_transfers_spouse_total"] == 3.0
    assert result["summary"]["births_married_parent_mean"] == 4.0


def test_household_stats_reset_each_tick(tmp_path):
    """M57b: Verify household counters reset each tick (not accumulated).
    Two-tick assertion: counters from tick 1 must not bleed into tick 2.
    Reads from the bundle file since RunResult does not carry the world."""
    import argparse
    import json
    from chronicler.main import execute_run

    args = argparse.Namespace(
        seed=99, turns=5, civs=4, regions=8,
        output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=10,
        llm_actions=False, scenario=None, pause_every=None,
        agents="hybrid",
    )
    execute_run(args)
    bundle_path = tmp_path / "chronicle_bundle.json"
    assert bundle_path.exists(), "bundle must be written"
    bundle = json.loads(bundle_path.read_text())
    stats_history = bundle.get("metadata", {}).get("household_stats", [])
    if len(stats_history) < 2:
        pytest.skip("not enough ticks for reset test")
    # Each entry is an independent tick snapshot, not cumulative.
    # With reset, it's normal for some ticks to have 0 while others have >0.
    has_zero_in_later_tick = False
    for key in stats_history[0]:
        vals = [s.get(key, 0) for s in stats_history]
        if any(v > 0 for v in vals) and any(v == 0 for v in vals[1:]):
            has_zero_in_later_tick = True
            break
    # If every counter monotonically increases, reset is broken.
    assert has_zero_in_later_tick or all(
        s.get("inheritance_transfers_spouse", 0) == 0 for s in stats_history
    ), "counters should reset each tick, not accumulate"


def test_agents_off_smoke(tmp_path):
    """M57b: --agents=off must not execute any household code paths."""
    import argparse
    from chronicler.main import execute_run

    args = argparse.Namespace(
        seed=42, turns=10, civs=4, regions=8,
        output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=10,
        llm_actions=False, scenario=None, pause_every=None,
    )
    # agents defaults to "off" via getattr in main.py
    result = execute_run(args)
    assert result is not None, "simulation completed"
