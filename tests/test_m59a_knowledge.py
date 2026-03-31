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
                {"packets_created": 5, "live_packet_count": 3},
                {"packets_created": 2, "live_packet_count": 4},
            ],
        }
    }]
    result = extract_knowledge_stats(bundles)
    assert len(result["by_seed"][42]) == 2
    assert result["by_seed"][42][0]["packets_created"] == 5


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
