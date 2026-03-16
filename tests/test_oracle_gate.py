# tests/test_oracle_gate.py

import json
import sys
import tempfile
from pathlib import Path
import pytest

# Make scripts/ importable
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


def _make_bundle(seed_dir: Path, history: list[dict]) -> None:
    """Write a minimal chronicle_bundle.json."""
    seed_dir.mkdir(parents=True, exist_ok=True)
    bundle = {"history": history, "metadata": {"seed": 0}}
    with open(seed_dir / "chronicle_bundle.json", "w") as f:
        json.dump(bundle, f)


def _make_snapshot(turn: int, civs: dict[str, dict]) -> dict:
    """Create a TurnSnapshot-like dict."""
    return {"turn": turn, "civ_stats": civs}


class TestAdapter:
    def test_basic_extraction(self, tmp_path):
        """Adapter extracts matching civ stats at checkpoints."""
        from scripts.run_oracle_gate import load_comparison_data

        agg_dir = tmp_path / "aggregate"
        hyb_dir = tmp_path / "hybrid"

        civ_stats = {"Aram": {"population": 50, "military": 30, "economy": 25,
                              "culture": 20, "stability": 40}}
        history = [_make_snapshot(t, civ_stats) for t in range(501)]

        _make_bundle(agg_dir / "seed_0", history)
        _make_bundle(hyb_dir / "seed_0", history)

        data = load_comparison_data(agg_dir, hyb_dir, checkpoints=[100, 250, 500])
        assert len(data["turn"]) == 3  # 3 checkpoints x 1 civ x 1 seed
        assert data["agent_population"] == [50, 50, 50]
        assert data["agg_population"] == [50, 50, 50]

    def test_multiple_seeds_and_civs(self, tmp_path):
        """Adapter handles multiple seeds and multiple civs."""
        from scripts.run_oracle_gate import load_comparison_data

        agg_dir = tmp_path / "aggregate"
        hyb_dir = tmp_path / "hybrid"

        for seed in range(3):
            civs = {
                "Aram": {"population": 50 + seed, "military": 30, "economy": 25,
                         "culture": 20, "stability": 40},
                "Bora": {"population": 60 + seed, "military": 35, "economy": 28,
                         "culture": 22, "stability": 45},
            }
            history = [_make_snapshot(t, civs) for t in range(501)]
            _make_bundle(agg_dir / f"seed_{seed}", history)
            _make_bundle(hyb_dir / f"seed_{seed}", history)

        data = load_comparison_data(agg_dir, hyb_dir, checkpoints=[100, 250, 500])
        # 3 checkpoints x 2 civs x 3 seeds = 18
        assert len(data["turn"]) == 18

    def test_mismatched_civs_excluded(self, tmp_path):
        """Civs in one run but not the other are excluded."""
        from scripts.run_oracle_gate import load_comparison_data

        agg_dir = tmp_path / "aggregate"
        hyb_dir = tmp_path / "hybrid"

        agg_civs = {"Aram": {"population": 50, "military": 30, "economy": 25,
                             "culture": 20, "stability": 40}}
        hyb_civs = {
            "Aram": {"population": 55, "military": 32, "economy": 27,
                     "culture": 21, "stability": 42},
            "NewCiv": {"population": 10, "military": 5, "economy": 3,
                       "culture": 2, "stability": 15},
        }

        _make_bundle(agg_dir / "seed_0",
                     [_make_snapshot(t, agg_civs) for t in range(501)])
        _make_bundle(hyb_dir / "seed_0",
                     [_make_snapshot(t, hyb_civs) for t in range(501)])

        data = load_comparison_data(agg_dir, hyb_dir, checkpoints=[100, 250, 500])
        # Only Aram matches — 3 checkpoints x 1 civ x 1 seed
        assert len(data["turn"]) == 3
