"""Tests for shadow oracle comparison framework."""
import tempfile
from pathlib import Path
import pyarrow as pa
import pyarrow.ipc as ipc
import numpy as np
import pytest
from chronicler.shadow import SHADOW_SCHEMA
from chronicler.shadow_oracle import (
    shadow_oracle_report, load_shadow_data, extract_at_turn, OracleReport,
    compare_distributions,
)


def write_synthetic_shadow(path: Path, turns: list[int], n_civs: int = 3,
                           diverge: bool = False, seed: int = 42) -> None:
    rng = np.random.default_rng(seed)
    sink = pa.OSFile(str(path), "wb")
    writer = ipc.new_file(sink, SHADOW_SCHEMA)

    for turn in turns:
        for civ in range(n_civs):
            agent_pop = max(0, int(rng.normal(50, 5)))
            agent_mil = max(0, int(rng.normal(30, 3)))
            agent_eco = max(0, int(rng.normal(25, 3)))
            agent_cul = max(0, int(rng.normal(20, 3)))
            agent_stb = max(0, int(rng.normal(40, 4)))
            if diverge:
                agg_pop = max(0, int(rng.normal(80, 5)))
            else:
                agg_pop = max(0, int(rng.normal(50, 5)))
            agg_mil = max(0, int(rng.normal(30, 3)))
            agg_eco = max(0, int(rng.normal(25, 3)))
            agg_cul = max(0, int(rng.normal(20, 3)))
            agg_stb = max(0, int(rng.normal(40, 4)))
            batch = pa.record_batch({
                "turn": pa.array([turn], type=pa.uint32()),
                "civ_id": pa.array([civ], type=pa.uint16()),
                "agent_population": pa.array([agent_pop], type=pa.uint32()),
                "agent_military": pa.array([agent_mil], type=pa.uint32()),
                "agent_economy": pa.array([agent_eco], type=pa.uint32()),
                "agent_culture": pa.array([agent_cul], type=pa.uint32()),
                "agent_stability": pa.array([agent_stb], type=pa.uint32()),
                "agg_population": pa.array([agg_pop], type=pa.uint32()),
                "agg_military": pa.array([agg_mil], type=pa.uint32()),
                "agg_economy": pa.array([agg_eco], type=pa.uint32()),
                "agg_culture": pa.array([agg_cul], type=pa.uint32()),
                "agg_stability": pa.array([agg_stb], type=pa.uint32()),
            }, schema=SHADOW_SCHEMA)
            writer.write_batch(batch)
    writer.close()


class TestShadowDataIO:
    def test_write_and_read(self):
        with tempfile.NamedTemporaryFile(suffix=".arrow", delete=False) as f:
            path = Path(f.name)
        write_synthetic_shadow(path, [100, 250, 500])
        data = load_shadow_data([path])
        assert "turn" in data
        assert len(data["turn"]) == 3 * 3  # 3 turns x 3 civs

    def test_extract_at_turn(self):
        with tempfile.NamedTemporaryFile(suffix=".arrow", delete=False) as f:
            path = Path(f.name)
        write_synthetic_shadow(path, [100, 250])
        data = load_shadow_data([path])
        vals = extract_at_turn(data, "agent_population", 100)
        assert len(vals) == 3


class TestOracleReport:
    def test_matching_distributions_pass(self):
        paths = []
        for seed in range(50):
            with tempfile.NamedTemporaryFile(suffix=".arrow", delete=False) as f:
                path = Path(f.name)
            write_synthetic_shadow(path, [100, 250, 500], diverge=False, seed=seed)
            paths.append(path)
        report = shadow_oracle_report(paths)
        assert report.ks_pass_count >= 10

    def test_divergent_distributions_detect(self):
        paths = []
        for seed in range(50):
            with tempfile.NamedTemporaryFile(suffix=".arrow", delete=False) as f:
                path = Path(f.name)
            write_synthetic_shadow(path, [100, 250, 500], diverge=True, seed=seed)
            paths.append(path)
        report = shadow_oracle_report(paths)
        pop_results = [r for r in report.results
                       if hasattr(r, "metric") and r.metric == "population"]
        assert any(not r.passed for r in pop_results)


class TestCompareDistributions:
    def test_matching_data_passes(self):
        """compare_distributions with matching synthetic data passes."""
        rng = np.random.default_rng(42)
        data = {"turn": [], "agent_population": [], "agg_population": [],
                "agent_military": [], "agg_military": [],
                "agent_economy": [], "agg_economy": [],
                "agent_culture": [], "agg_culture": [],
                "agent_stability": [], "agg_stability": []}
        for turn in [100, 250, 500]:
            for _ in range(200):
                data["turn"].append(turn)
                for metric in ["population", "military", "economy", "culture", "stability"]:
                    val = int(rng.normal(50, 5))
                    data[f"agent_{metric}"].append(max(0, val))
                    data[f"agg_{metric}"].append(max(0, int(rng.normal(50, 5))))
        report = compare_distributions(data)
        assert report.ks_pass_count >= 12
        assert report.correlation_passed

    def test_divergent_data_detects(self):
        """compare_distributions with divergent population detects failure."""
        rng = np.random.default_rng(42)
        data = {"turn": [], "agent_population": [], "agg_population": [],
                "agent_military": [], "agg_military": [],
                "agent_economy": [], "agg_economy": [],
                "agent_culture": [], "agg_culture": [],
                "agent_stability": [], "agg_stability": []}
        for turn in [100, 250, 500]:
            for _ in range(200):
                data["turn"].append(turn)
                data["agent_population"].append(max(0, int(rng.normal(80, 5))))
                data["agg_population"].append(max(0, int(rng.normal(50, 5))))
                for metric in ["military", "economy", "culture", "stability"]:
                    val = int(rng.normal(50, 5))
                    data[f"agent_{metric}"].append(max(0, val))
                    data[f"agg_{metric}"].append(max(0, int(rng.normal(50, 5))))
        report = compare_distributions(data)
        pop_results = [r for r in report.results
                       if hasattr(r, "metric") and r.metric == "population"]
        assert any(not r.passed for r in pop_results)
