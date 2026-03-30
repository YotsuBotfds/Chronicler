"""Tests for scripts/m58b_convergence_gate.py evaluate_seed and run_gate logic."""
import json
import sys
from pathlib import Path

import pytest

# Add scripts/ to path so we can import the gate module.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from m58b_convergence_gate import evaluate_seed, run_gate  # noqa: E402


def _write_snapshot(sidecar_dir: Path, turn: int, **overrides) -> None:
    """Write a minimal economy snapshot with sensible defaults."""
    snap = {
        "turn": turn,
        "oracle_margins_by_region": {"A": 0.5, "B": 0.3},
        "post_trade_margin_by_region": {"A": 0.5, "B": 0.3},
        "oracle_trade_volume_by_category": {
            "A": {"food": 10, "raw_material": 5, "luxury": 2},
            "B": {"food": 8, "raw_material": 4, "luxury": 1},
        },
        "agent_trade_volume_by_category": {
            "A": {"food": 10, "raw_material": 5, "luxury": 2},
            "B": {"food": 8, "raw_material": 4, "luxury": 1},
        },
        "oracle_food_sufficiency_by_region": {"A": 1.2, "B": 0.9},
        "food_sufficiency_by_region": {"A": 1.2, "B": 0.9},
        "conservation": {
            "production": 100.0,
            "transit_loss": 1.0,
            "consumption": 50.0,
            "storage_loss": 0.5,
            "cap_overflow": 0.0,
            "clamp_floor_loss": 0.0,
            "in_transit_delta": 0.5,
        },
    }
    snap.update(overrides)
    path = sidecar_dir / f"economy_turn_{turn:05d}.json"
    path.write_text(json.dumps(snap))


def test_evaluate_seed_passes_with_matching_data(tmp_path):
    """When oracle and realized match, seed should pass."""
    for t in range(100, 200, 10):
        _write_snapshot(tmp_path, t)
    result = evaluate_seed(tmp_path)
    assert result["passed"], f"Should pass with matching data, got: {result.get('reasons')}"


def test_evaluate_seed_no_snapshots(tmp_path):
    """No snapshots → fail with reason."""
    result = evaluate_seed(tmp_path)
    assert not result["passed"]
    assert result["reason"] == "no_economy_snapshots"


def test_food_crisis_uses_delta_not_absolute(tmp_path):
    """Crisis rate should be oracle-vs-realized delta, not absolute realized rate."""
    # Both oracle and realized have high crisis (food_suff = 0.5 < 0.8),
    # but the DELTA is 0pp because they match. Should pass.
    for t in range(100, 200, 10):
        _write_snapshot(
            tmp_path, t,
            oracle_food_sufficiency_by_region={"A": 0.5, "B": 0.5},
            food_sufficiency_by_region={"A": 0.5, "B": 0.5},
        )
    result = evaluate_seed(tmp_path)
    assert result["food_crisis_delta_pp"] == 0.0, "Delta should be 0 when both have same crisis rate"
    # Should not fail on crisis since delta = 0.
    assert "food_crisis_delta" not in str(result.get("reasons", []))


def test_conservation_error_uses_clamp_floor_not_in_transit(tmp_path):
    """Conservation error should be clamp_floor_loss/production, not in_transit_delta."""
    # Large in_transit_delta but zero clamp_floor_loss → conservation error = 0.
    for t in range(100, 200, 10):
        _write_snapshot(
            tmp_path, t,
            conservation={
                "production": 100.0,
                "transit_loss": 1.0,
                "consumption": 50.0,
                "storage_loss": 0.5,
                "cap_overflow": 0.0,
                "clamp_floor_loss": 0.0,
                "in_transit_delta": 50.0,  # Large, but NOT an error
            },
        )
    result = evaluate_seed(tmp_path)
    assert result["conservation_error_median"] == 0.0, (
        "in_transit_delta should not count as conservation error"
    )


def test_run_gate_pass_rate(tmp_path):
    """Gate passes when >= 75% of seeds pass."""
    results = [{"passed": True}] * 8 + [{"passed": False}] * 2
    gate = run_gate(results, 10)
    assert gate["gate_passed"]
    assert gate["seed_pass_rate"] == 0.8


def test_run_gate_catastrophic_tail(tmp_path):
    """Gate fails when > 5% of seeds have catastrophic food crisis delta."""
    results = [
        {"passed": True, "food_crisis_delta_pp": 0.0}
    ] * 9 + [
        {"passed": False, "food_crisis_delta_pp": 10.0}  # catastrophic
    ] * 1
    gate = run_gate(results, 10)
    # 10% catastrophic > 5% threshold → gate fails
    assert not gate["gate_passed"]
