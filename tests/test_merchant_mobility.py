"""M58a: Merchant mobility integration tests.

Verifies --agents=off mode is unaffected by M58a merchant mobility code.
"""
import argparse
import json
import pytest


def _make_args(tmp_path, seed=42, turns=10, agents="off"):
    """Build a minimal args namespace for execute_run."""
    return argparse.Namespace(
        seed=seed, turns=turns, civs=2, regions=5,
        output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=10,
        llm_actions=False, scenario=None, pause_every=None,
        simulate_only=True, agents=agents,
    )


def test_agents_off_unaffected(tmp_path):
    """--agents=off produces output regardless of M58a code."""
    from chronicler.main import execute_run

    args = _make_args(tmp_path, agents="off")
    result = execute_run(args)
    bundle_path = tmp_path / "chronicle_bundle.json"
    assert bundle_path.exists(), "Bundle should be written in agents=off mode"
    bundle = json.loads(bundle_path.read_text())
    # M58a metadata should not leak into agents=off bundles
    assert "merchant_trip_stats" not in bundle.get("metadata", {}), (
        "merchant_trip_stats should not appear in agents=off metadata"
    )
    assert result.total_turns == 10
