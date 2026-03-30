"""M58a: Merchant mobility integration tests.

Verifies --agents=off mode is unaffected by M58a merchant mobility code.
"""
import argparse
import json
import pytest
from chronicler.models import Disposition


def _configure_two_region_world(sample_world):
    """Prepare two adjacent controlled regions with neutral diplomacy."""
    civ_a = sample_world.civilizations[0].name
    civ_b = sample_world.civilizations[1].name
    r1 = sample_world.regions[0]
    r2 = sample_world.regions[1]

    r1.controller = civ_a
    r2.controller = civ_b
    r1.adjacencies = [r2.name]
    r2.adjacencies = [r1.name]
    r1.route_suspensions = {}
    r2.route_suspensions = {}

    sample_world.active_wars = []
    sample_world.embargoes = []
    sample_world.relationships[civ_a][civ_b].disposition = Disposition.NEUTRAL
    sample_world.relationships[civ_b][civ_a].disposition = Disposition.NEUTRAL
    return r1, r2


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


def test_route_suspension_blocks_cross_civ_edges(sample_world):
    """Endpoint route_suspensions must block cross-civ edges."""
    from chronicler.economy import build_merchant_route_graph

    r1, _r2 = _configure_two_region_world(sample_world)

    batch = build_merchant_route_graph(sample_world)
    assert batch.num_rows == 2, "Expected two directed edges without suspension"

    r1.route_suspensions["trade_route"] = 3
    blocked = build_merchant_route_graph(sample_world)
    assert blocked.num_rows == 0, "Any endpoint suspension should block both directions"


def test_route_suspension_blocks_intra_civ_edges(sample_world):
    """Endpoint route_suspensions must also block intra-civ movement edges."""
    from chronicler.economy import build_merchant_route_graph

    r1, r2 = _configure_two_region_world(sample_world)
    r2.controller = r1.controller

    batch = build_merchant_route_graph(sample_world)
    assert batch.num_rows == 2, "Expected two directed intra-civ edges without suspension"

    r2.route_suspensions["trade_route"] = 2
    blocked = build_merchant_route_graph(sample_world)
    assert blocked.num_rows == 0, "Intra-civ edges touching suspended regions must be blocked"


def test_economy_result_has_in_transit_delta():
    """EconomyResult.conservation dict includes in_transit_delta key."""
    from chronicler.economy import EconomyResult
    result = EconomyResult()
    assert "in_transit_delta" in result.conservation
    assert result.conservation["in_transit_delta"] == 0.0
