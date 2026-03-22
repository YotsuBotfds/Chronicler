from chronicler.sidecar import SidecarWriter, SidecarReader
import tempfile, pathlib
import json

try:
    import pyarrow.ipc as ipc
    HAS_ARROW = True
except ImportError:
    HAS_ARROW = False


def test_graph_snapshot_round_trip():
    """Write a graph+memory snapshot, read it back, verify contents."""
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = SidecarWriter(pathlib.Path(tmpdir))
        edges = [(1, 2, 3, 50), (2, 3, 0, 60)]
        mem_sigs = {1: [(0, 10, -1), (6, 20, 1)], 2: [(0, 10, -1)], 3: []}
        writer.write_graph_snapshot(turn=10, edges=edges, memory_signatures=mem_sigs)
        writer.close()

        reader = SidecarReader(pathlib.Path(tmpdir))
        snapshot = reader.read_graph_snapshot(turn=10)
        assert len(snapshot["edges"]) == 2
        assert snapshot["edges"][0] == (1, 2, 3, 50)
        assert snapshot["memory_signatures"][1] == [(0, 10, -1), (6, 20, 1)]


def test_agent_aggregate_round_trip():
    """Write per-civ agent aggregate, read it back."""
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = SidecarWriter(pathlib.Path(tmpdir))
        agg = {
            "civ_0": {
                "satisfaction_mean": 0.55, "satisfaction_std": 0.12,
                "occupation_counts": {"farmers": 200, "soldiers": 50, "merchants": 30, "scholars": 10, "priests": 10},
                "agent_count": 300,
                "need_means": {"safety": 0.45, "autonomy": 0.50, "social": 0.40, "spiritual": 0.35, "material": 0.55, "purpose": 0.48},
                "memory_slot_occupancy_mean": 4.2,
            }
        }
        writer.write_agent_aggregate(turn=10, aggregates=agg)
        writer.close()

        reader = SidecarReader(pathlib.Path(tmpdir))
        result = reader.read_agent_aggregate(turn=10)
        assert abs(result["civ_0"]["satisfaction_mean"] - 0.55) < 0.001


def test_condensed_community_summary():
    """Write condensed community summary for gate runs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = SidecarWriter(pathlib.Path(tmpdir))
        summary = {
            "region_0": {"cluster_count": 3, "sizes": [5, 8, 12], "dominant_memory_type": 0},
            "region_1": {"cluster_count": 1, "sizes": [7], "dominant_memory_type": 1},
        }
        writer.write_community_summary(turn=100, summary=summary)
        writer.close()

        reader = SidecarReader(pathlib.Path(tmpdir))
        result = reader.read_community_summary(turn=100)
        assert result["region_0"]["cluster_count"] == 3


def test_sidecar_writer_emits_canonical_artifacts():
    """Close writes consolidated canonical Arrow/JSON artifacts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = pathlib.Path(tmpdir)
        writer = SidecarWriter(base)
        edges = [(1, 2, 3, 50)]
        mem_sigs = {1: [(0, 10, -1)]}
        needs = {
            "agent_id": [1],
            "civ_affinity": [0],
            "region": [2],
            "occupation": [3],
            "satisfaction": [0.55],
            "boldness": [0.4],
            "ambition": [0.5],
            "loyalty_trait": [0.6],
            "safety": [0.4],
            "autonomy": [0.5],
            "social": [0.6],
            "spiritual": [0.7],
            "material": [0.8],
            "purpose": [0.9],
        }
        aggregates = {"civ_0": {"satisfaction_mean": 0.55, "agent_count": 1}}
        writer.write_graph_snapshot(turn=10, edges=edges, memory_signatures=mem_sigs)
        writer.write_needs_snapshot(turn=10, needs_batch=needs)
        writer.write_agent_aggregate(turn=10, aggregates=aggregates)
        writer.write_community_summary(turn=10, summary={"region_0": {"cluster_count": 1}})
        writer.close()

        assert (base / "validation_summary.json").exists()
        assert (base / "validation_community_summary.json").exists()

        summary = json.loads((base / "validation_summary.json").read_text())
        assert summary["turns"] == [10]
        assert summary["agent_aggregates_by_turn"]["10"]["civ_0"]["agent_count"] == 1

        community_summary = json.loads((base / "validation_community_summary.json").read_text())
        assert community_summary["turns"] == [10]
        assert community_summary["community_summary_by_turn"]["10"]["region_0"]["cluster_count"] == 1

        if HAS_ARROW:
            rel_table = ipc.open_file(str(base / "validation_relationships.arrow")).read_all()
            rel_cols = rel_table.to_pydict()
            assert rel_cols["turn"] == [10]
            assert rel_cols["agent_id"] == [1]
            assert rel_cols["target_id"] == [2]

            mem_table = ipc.open_file(str(base / "validation_memory_signatures.arrow")).read_all()
            mem_cols = mem_table.to_pydict()
            assert mem_cols["turn"] == [10]
            assert mem_cols["event_type"] == [0]
            assert mem_cols["valence_sign"] == [-1]

            needs_table = ipc.open_file(str(base / "validation_needs.arrow")).read_all()
            needs_cols = needs_table.to_pydict()
            assert needs_cols["turn"] == [10]
            assert needs_cols["agent_id"] == [1]
            assert needs_cols["purpose"] == [0.9]
