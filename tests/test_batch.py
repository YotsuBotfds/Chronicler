"""Tests for batch runner."""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import argparse

from chronicler.batch import run_batch


@pytest.fixture
def batch_args(tmp_path):
    return argparse.Namespace(
        seed=42, turns=3, civs=2, regions=4,
        output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=10,
        local_url="http://localhost:1234/v1",
        sim_model=None, narrative_model=None,
        llm_actions=False, scenario=None,
        batch=3, fork=None, interactive=False,
        parallel=None, pause_every=None,
        tuning=None, simulate_only=False, seed_range=None,
    )


class TestRunBatch:
    def _mock_llm(self, response="DEVELOP"):
        mock = MagicMock()
        mock.complete.return_value = response
        mock.model = "test-model"
        return mock

    def test_creates_output_directories(self, batch_args, tmp_path):
        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        batch_dir = run_batch(batch_args, sim_client=sim, narrative_client=narr)
        assert batch_dir.exists()
        assert (batch_dir / "seed_42").is_dir()
        assert (batch_dir / "seed_43").is_dir()
        assert (batch_dir / "seed_44").is_dir()

    def test_each_run_produces_chronicle(self, batch_args, tmp_path):
        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        batch_dir = run_batch(batch_args, sim_client=sim, narrative_client=narr)
        for seed in [42, 43, 44]:
            assert (batch_dir / f"seed_{seed}" / "chronicle.md").exists()
            assert (batch_dir / f"seed_{seed}" / "state.json").exists()

    def test_produces_summary(self, batch_args, tmp_path):
        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        batch_dir = run_batch(batch_args, sim_client=sim, narrative_client=narr)
        summary = batch_dir / "summary.md"
        assert summary.exists()
        content = summary.read_text()
        assert "Rank" in content or "rank" in content.lower()

    def test_returns_batch_directory_path(self, batch_args, tmp_path):
        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        batch_dir = run_batch(batch_args, sim_client=sim, narrative_client=narr)
        assert batch_dir.name == "batch_42"

    def test_tuning_overrides_applied(self, batch_args, tmp_path):
        tuning_file = tmp_path / "tuning.yaml"
        tuning_file.write_text("stability:\n  drain:\n    drought_immediate: 1\n")
        batch_args.tuning = str(tuning_file)
        batch_args.simulate_only = True
        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        batch_dir = run_batch(batch_args, sim_client=sim, narrative_client=narr)
        assert batch_dir.exists()
        assert (batch_dir / "summary.md").exists()
        from chronicler.models import WorldState
        for seed in [42, 43, 44]:
            world = WorldState.load(batch_dir / f"seed_{seed}" / "state.json")
            assert "stability.drain.drought_immediate" in world.tuning_overrides
            assert world.tuning_overrides["stability.drain.drought_immediate"] == pytest.approx(1.0)

    def test_simulate_only_skips_llm(self, batch_args, tmp_path):
        """--simulate-only batch runs don't require real LLM clients."""
        batch_args.simulate_only = True
        batch_dir = run_batch(batch_args, sim_client=None, narrative_client=None)
        assert batch_dir.exists()
