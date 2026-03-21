from chronicler.sidecar import SidecarWriter, SidecarReader
import tempfile, pathlib


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
