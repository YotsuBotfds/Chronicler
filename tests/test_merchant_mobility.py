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


def test_thread_count_determinism(tmp_path):
    """Same seed with different thread counts produces identical merchant stats."""
    import os
    from chronicler.main import execute_run

    os.environ["RAYON_NUM_THREADS"] = "1"
    d1 = tmp_path / "run1"
    d1.mkdir()
    args1 = _make_args(d1, seed=42, turns=20, agents="hybrid")
    execute_run(args1)

    os.environ["RAYON_NUM_THREADS"] = "4"
    d2 = tmp_path / "run2"
    d2.mkdir()
    args2 = _make_args(d2, seed=42, turns=20, agents="hybrid")
    execute_run(args2)

    os.environ.pop("RAYON_NUM_THREADS", None)

    b1 = json.loads((d1 / "chronicle_bundle.json").read_text())
    b2 = json.loads((d2 / "chronicle_bundle.json").read_text())
    s1 = b1.get("metadata", {}).get("merchant_trip_stats", [])
    s2 = b2.get("metadata", {}).get("merchant_trip_stats", [])
    assert s1 == s2, f"Merchant stats diverge between thread counts"


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
