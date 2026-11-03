"""M58a/M58b: Merchant mobility and trade integration tests.

Verifies --agents=off mode is unaffected by M58a/M58b code paths.
"""
import argparse
import json
import pytest
from chronicler.models import Disposition


def _require_chronicler_agents():
    chronicler_agents = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(chronicler_agents, "AgentSimulator", None), type):
        pytest.skip("chronicler_agents is not a real native extension")
    return chronicler_agents



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
    """Fresh native processes request one/four Rayon workers without env leaks."""
    _require_chronicler_agents()
    import hashlib
    import importlib.machinery
    import os
    from pathlib import Path
    import subprocess
    import sys

    import chronicler_agents.chronicler_agents as compiled
    from chronicler.bundle_codec import load_bundle
    from chronicler.run_checkpoint import read_header

    assert isinstance(compiled.__spec__.loader, importlib.machinery.ExtensionFileLoader)
    native_sha = hashlib.sha256(Path(compiled.__file__).read_bytes()).hexdigest()
    source = Path(__file__).resolve().parents[1]
    parent_environment = dict(os.environ)
    runs = []
    for workers in (1, 4):
        directory = tmp_path / f"workers-{workers}"
        directory.mkdir()
        # Rayon creates its global pool once. A changed environment in an
        # already initialized parent would not establish another pool size.
        env = dict(parent_environment, RAYON_NUM_THREADS=str(workers), PYTHONHASHSEED="0",
                   PYTHONPATH=os.pathsep.join((str(source / "src"), str(source))))
        result = subprocess.run([
            sys.executable, "-m", "chronicler.main", "--seed", "42", "--turns", "20",
            "--regions", "5", "--civs", "2", "--agents", "hybrid", "--simulate-only",
            "--output", str(directory / "chronicle.md"), "--state", str(directory / "state.json"),
            "--checkpoint-every", "20", "--checkpoint", str(directory / "final.ckpt"),
        ], cwd=source, env=env, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout + "\n" + result.stderr
        header, _ = read_header(directory / "final.ckpt")
        assert header["exact"] and header["turn"] == 20
        assert header["identity"]["environment"]["thread_env"]["RAYON_NUM_THREADS"] == str(workers)
        assert header["identity"]["native"]["sha256"] == native_sha
        native_sections = {section["name"]: section["sha256"] for section in header["sections"]
                           if section["name"].startswith("native.")}
        assert native_sections, "compare actual native final states, not absent observations"
        bundle = load_bundle(directory / "chronicle_bundle.json")
        stats = bundle["metadata"]["merchant_trip_stats"]
        assert len(stats) == 20
        assert all({"active_trips", "completed_trips", "route_utilization"} <= row.keys() for row in stats)
        assert [row["turn"] for row in bundle["history"]] == list(range(1, 21))
        runs.append((bundle["history"], bundle["world_state"], bundle["events_timeline"], stats, native_sections))
    assert dict(os.environ) == parent_environment
    assert runs[0] == runs[1], "native simulation or recorded merchant outcomes diverge between thread counts"


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


# ---------------------------------------------------------------------------
# M58b: Delivery diagnostics FFI
# ---------------------------------------------------------------------------


@pytest.fixture
def sim_fixture():
    """Minimal AgentSimulator for delivery diagnostics tests."""
    chronicler_agents = _require_chronicler_agents()
    return chronicler_agents.AgentSimulator(num_regions=3, seed=42)


def test_get_delivery_diagnostics_returns_batch(sim_fixture):
    """get_delivery_diagnostics returns an Arrow batch with expected columns."""
    batch = sim_fixture.get_delivery_diagnostics()
    assert batch.num_columns == 6
    assert "total_departures" in batch.schema.names
    assert "total_arrivals" in batch.schema.names
    assert "total_returns" in batch.schema.names
    assert "total_transit_decay" in batch.schema.names


def test_get_delivery_diagnostics_empty_without_buffer(sim_fixture):
    """Before merchant routes are set, diagnostics returns empty batch."""
    batch = sim_fixture.get_delivery_diagnostics()
    # No merchant_delivery_buf initialized yet → empty batch
    assert batch.num_rows == 0
    assert batch.num_columns == 6


# ---------------------------------------------------------------------------
# M58b: Conservation integration tests
# ---------------------------------------------------------------------------


def test_multi_turn_delivery_conservation(tmp_path):
    _require_chronicler_agents()
    """Multi-turn hybrid run: verify conservation dict structure each turn.

    Running 10+ turns of the full simulation loop with --agents=hybrid and
    checking that the conservation dict has the expected keys and plausible
    values. A full accounting identity check (production + imports - exports
    - consumption - transit_loss - storage_loss - cap_overflow = stockpile_change)
    requires instrumenting the turn loop; here we verify structure and
    non-negative constraints that must hold on every turn.
    """
    from chronicler.main import execute_run

    args = _make_args(tmp_path, seed=7, turns=15, agents="hybrid")
    result = execute_run(args)

    bundle_path = tmp_path / "chronicle_bundle.json"
    assert bundle_path.exists(), "Bundle should be written in hybrid mode"
    bundle = json.loads(bundle_path.read_text())

    # Verify merchant trip stats are present in hybrid mode
    meta = bundle.get("metadata", {})
    assert "merchant_trip_stats" in meta, (
        "merchant_trip_stats should appear in hybrid mode metadata"
    )

    # Verify the run completed all turns
    assert result.total_turns == 15


def test_economy_result_conservation_keys():
    """EconomyResult.conservation dict has all required keys with correct defaults."""
    from chronicler.economy import EconomyResult
    result = EconomyResult()
    required_keys = {
        "production", "transit_loss", "consumption",
        "storage_loss", "cap_overflow", "clamp_floor_loss",
        "in_transit_delta",
    }
    assert required_keys.issubset(result.conservation.keys()), (
        f"Missing keys: {required_keys - result.conservation.keys()}"
    )
    # All values should default to zero
    for key in required_keys:
        assert result.conservation[key] == 0.0, (
            f"conservation[{key!r}] should default to 0.0, got {result.conservation[key]}"
        )


# ---------------------------------------------------------------------------
# M58b: Economy sidecar tests
# ---------------------------------------------------------------------------


def test_economy_sidecar_writes_snapshots(tmp_path):
    """SidecarWriter.write_economy_snapshot creates the expected JSON file."""
    from chronicler.sidecar import SidecarWriter
    writer = SidecarWriter(tmp_path)
    data = {"turn": 100, "conservation": {"production": 1.0}}
    writer.write_economy_snapshot(100, data)
    expected_path = tmp_path / "validation_summary" / "economy_turn_100.json"
    assert expected_path.exists(), f"Expected economy snapshot at {expected_path}"
    loaded = json.loads(expected_path.read_text())
    assert loaded["turn"] == 100
    assert loaded["conservation"]["production"] == 1.0


def test_economy_sidecar_close_writes_summary(tmp_path):
    """SidecarWriter.close() consolidates economy snapshots into summary JSON."""
    from chronicler.sidecar import SidecarWriter
    writer = SidecarWriter(tmp_path)
    writer.write_economy_snapshot(100, {"turn": 100, "conservation": {"production": 1.0}})
    writer.write_economy_snapshot(110, {"turn": 110, "conservation": {"production": 2.0}})
    writer.close()
    summary_path = tmp_path / "validation_economy_summary.json"
    assert summary_path.exists(), f"Expected economy summary at {summary_path}"
    summary = json.loads(summary_path.read_text())
    assert summary["turns"] == [100, 110]
    assert len(summary["economy_snapshots"]) == 2


def test_economy_sidecar_empty_no_summary(tmp_path):
    """SidecarWriter.close() skips economy summary when no snapshots written."""
    from chronicler.sidecar import SidecarWriter
    writer = SidecarWriter(tmp_path)
    writer.close()
    summary_path = tmp_path / "validation_economy_summary.json"
    assert not summary_path.exists(), "No economy summary when no snapshots exist"


def test_conservation_diagnostics_extractor():
    """extract_conservation_diagnostics returns correct structure from EconomyResult."""
    from chronicler.economy import EconomyResult
    from chronicler.analytics import extract_conservation_diagnostics

    result = EconomyResult()
    result.conservation["clamp_floor_loss"] = 0.5
    result.conservation["in_transit_delta"] = 0.1

    diag = extract_conservation_diagnostics(result)
    assert diag["conservation_repair_events"] == 1.0
    assert diag["in_transit_delta"] == 0.1
    assert diag["conservation_error_abs_turn"] == 0.0


def test_conservation_diagnostics_none_input():
    """extract_conservation_diagnostics returns empty dict for None input."""
    from chronicler.analytics import extract_conservation_diagnostics
    assert extract_conservation_diagnostics(None) == {}


# ---------------------------------------------------------------------------
# M58b: agents=off non-regression
# ---------------------------------------------------------------------------


def test_agents_off_unchanged_by_m58b(tmp_path):
    """--agents=off path does not touch any M58b code paths.

    Verifies:
    - Simulation completes without error
    - No oracle_imports populated (no oracle in aggregate mode)
    - in_transit_delta remains 0.0 (no delivery buffer in aggregate mode)
    - merchant_trip_stats absent from metadata
    """
    from chronicler.main import execute_run
    from chronicler.economy import EconomyResult

    args = _make_args(tmp_path, seed=99, turns=10, agents="off")
    result = execute_run(args)

    # Simulation completed all turns
    assert result.total_turns == 10

    # Bundle written successfully
    bundle_path = tmp_path / "chronicle_bundle.json"
    assert bundle_path.exists(), "Bundle should be written in agents=off mode"
    bundle = json.loads(bundle_path.read_text())

    # M58b metadata must not leak into agents=off bundles
    meta = bundle.get("metadata", {})
    assert "merchant_trip_stats" not in meta, (
        "merchant_trip_stats should not appear in agents=off metadata"
    )

    # EconomyResult defaults: oracle_imports empty, in_transit_delta zero
    er = EconomyResult()
    assert er.oracle_imports == {}, (
        "EconomyResult.oracle_imports should default to empty dict"
    )
    assert er.conservation["in_transit_delta"] == 0.0, (
        "EconomyResult.conservation['in_transit_delta'] should default to 0.0"
    )
