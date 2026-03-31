"""M59a: Knowledge stats integration tests."""
import argparse
import json
import subprocess
import sys

import pytest


def test_knowledge_stats_property_exists():
    """Verify the knowledge_stats property exists on AgentBridge."""
    from chronicler.agent_bridge import AgentBridge
    assert hasattr(AgentBridge, "knowledge_stats"), "AgentBridge should have knowledge_stats property"


def test_extract_knowledge_stats_empty():
    """Verify extractor handles bundles with no knowledge_stats."""
    from chronicler.analytics import extract_knowledge_stats

    bundles = [{"metadata": {"seed": 42}}]
    result = extract_knowledge_stats(bundles)
    assert result == {"by_seed": {42: []}}


def test_extract_knowledge_stats_with_data():
    """Verify extractor routes per-turn stats by seed."""
    from chronicler.analytics import extract_knowledge_stats

    bundles = [{
        "metadata": {
            "seed": 42,
            "knowledge_stats": [
                {
                    "packets_created": 5,
                    "live_packet_count": 3,
                    "created_by_type": {"threat": 4, "trade": 1, "religious": 0},
                    "transmitted_by_type": {"threat": 2, "trade": 0, "religious": 1},
                },
                {
                    "packets_created": 2,
                    "live_packet_count": 4,
                    "created_by_type": {"threat": 1, "trade": 1, "religious": 0},
                    "transmitted_by_type": {"threat": 0, "trade": 1, "religious": 0},
                },
            ],
        }
    }]
    result = extract_knowledge_stats(bundles)
    assert len(result["by_seed"][42]) == 2
    assert result["by_seed"][42][0]["packets_created"] == 5
    assert result["by_seed"][42][0]["created_by_type"]["threat"] == 4


def test_knowledge_deterministic_cross_process(tmp_path):
    """Cross-process determinism proxy: same seed in two separate processes
    must produce identical knowledge_stats aggregate counters."""
    bundles = []
    for run_idx in range(2):
        run_dir = tmp_path / f"det_run_{run_idx}"
        run_dir.mkdir()
        script = (
            f"import argparse; "
            f"from chronicler.main import execute_run; "
            f"args = argparse.Namespace("
            f"  seed=77, turns=8, civs=2, regions=5,"
            f"  output=r'{run_dir / 'chronicle.md'}',"
            f"  state=r'{run_dir / 'state.json'}',"
            f"  resume=None, reflection_interval=10,"
            f"  llm_actions=False, scenario=None, pause_every=None,"
            f"  agents='hybrid', narrator='off', agent_narrative=False,"
            f"  relationship_stats=False, live=False,"
            f"  shadow_output=None, validation_sidecar=False,"
            f"); "
            f"execute_run(args)"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, (
            f"Run {run_idx} failed: {result.stderr[-500:]}"
        )
        bundle_path = run_dir / "chronicle_bundle.json"
        assert bundle_path.exists(), f"Run {run_idx} produced no bundle"
        bundles.append(json.loads(bundle_path.read_text()))

    k0 = bundles[0].get("metadata", {}).get("knowledge_stats", [])
    k1 = bundles[1].get("metadata", {}).get("knowledge_stats", [])
    assert len(k0) > 0, "knowledge_stats should be non-empty in hybrid mode"
    assert k0 == k1, "knowledge_stats diverged across processes"


def _make_args(tmp_path, seed=42, turns=5, agents="off"):
    """Build an args namespace matching execute_run's expected shape."""
    return argparse.Namespace(
        seed=seed,
        turns=turns,
        civs=2,
        regions=5,
        output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"),
        resume=None,
        reflection_interval=10,
        llm_actions=False,
        scenario=None,
        pause_every=None,
        agents=agents,
        narrator="off",
        agent_narrative=False,
        relationship_stats=False,
        live=False,
        shadow_output=None,
        validation_sidecar=False,
    )


def test_agents_off_no_knowledge_stats(tmp_path):
    """--agents=off should produce no knowledge_stats in bundle metadata."""
    from chronicler.main import execute_run

    args = _make_args(tmp_path, agents="off")
    execute_run(args)

    bundle_path = tmp_path / "chronicle_bundle.json"
    assert bundle_path.exists(), "execute_run should produce a bundle"
    bundle = json.loads(bundle_path.read_text())
    metadata = bundle.get("metadata", {})
    k_stats = metadata.get("knowledge_stats", [])
    assert k_stats == [] or "knowledge_stats" not in metadata


def test_agents_off_no_consumer_counters(tmp_path):
    """When --agents=off, no knowledge_stats should appear in metadata."""
    out_dir = tmp_path / "off_test"
    out_dir.mkdir()
    result = subprocess.run(
        [
            sys.executable, "-m", "chronicler.main",
            "--seed", "42", "--turns", "5", "--agents", "off",
            "--output", str(out_dir / "chronicle.md"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"Run failed: {result.stderr}"
    bundle_path = out_dir / "chronicle_bundle.json"
    assert bundle_path.exists()
    with open(bundle_path) as f:
        bundle = json.load(f)
    metadata = bundle.get("metadata", {})
    assert "knowledge_stats" not in metadata, \
        "knowledge_stats should not be present when --agents=off"


def test_hybrid_determinism_with_knowledge_stats(tmp_path):
    """Same seed in hybrid mode: two runs produce identical bundles."""
    from chronicler.main import execute_run

    results = []
    for run_idx in range(2):
        run_dir = tmp_path / f"run_{run_idx}"
        run_dir.mkdir()
        args = _make_args(run_dir, seed=42, turns=10, agents="hybrid")
        execute_run(args)
        bundle_path = run_dir / "chronicle_bundle.json"
        assert bundle_path.exists(), f"Run {run_idx} did not produce a bundle"
        results.append(json.loads(bundle_path.read_text()))

    b0, b1 = results
    assert b0["history"] == b1["history"], "history diverged"
    assert b0.get("events_timeline") == b1.get("events_timeline"), "events diverged"

    k0 = b0.get("metadata", {}).get("knowledge_stats", [])
    k1 = b1.get("metadata", {}).get("knowledge_stats", [])
    assert len(k0) == 10, f"Expected 10 turns of knowledge_stats, got {len(k0)}"
    assert k0 == k1, "knowledge_stats diverged between same-seed runs"
    assert "created_by_type" in k0[0], "bundle knowledge_stats should include created_by_type"
    assert "transmitted_by_type" in k0[0], "bundle knowledge_stats should include transmitted_by_type"
    assert "created_threat" not in k0[0], "per-type counters should be nested in created_by_type"
    assert "transmitted_threat" not in k0[0], "per-type counters should be nested in transmitted_by_type"


def test_m59b_consumer_counters_in_knowledge_stats():
    """Verify M59b consumer counters are present in knowledge_stats."""
    from chronicler.analytics import extract_knowledge_stats

    bundles = [{
        "metadata": {
            "seed": 42,
            "knowledge_stats": [
                {
                    "packets_created": 5,
                    "live_packet_count": 3,
                    "created_by_type": {"threat": 4, "trade": 1, "religious": 0},
                    "transmitted_by_type": {"threat": 2, "trade": 0, "religious": 1},
                    "merchant_plans_packet_driven": 3,
                    "merchant_plans_bootstrap": 1,
                    "merchant_no_usable_packets": 1,
                    "migration_choices_changed_by_threat": 2,
                },
            ],
        }
    }]
    result = extract_knowledge_stats(bundles)
    turn_data = result["by_seed"][42][0]
    assert turn_data["merchant_plans_packet_driven"] == 3
    assert turn_data["merchant_plans_bootstrap"] == 1
    assert turn_data["merchant_no_usable_packets"] == 1
    assert turn_data["migration_choices_changed_by_threat"] == 2
