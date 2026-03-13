"""Tests for fork mode."""
import pytest
from unittest.mock import MagicMock
from pathlib import Path
import argparse

from chronicler.fork import run_fork
from chronicler.main import execute_run
from chronicler.memory import MemoryStream, sanitize_civ_name


class TestRunFork:
    def _mock_llm(self, response="DEVELOP"):
        mock = MagicMock()
        mock.complete.return_value = response
        mock.model = "test-model"
        return mock

    def _run_parent(self, tmp_path):
        """Run a parent chronicle that produces state + memory files."""
        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        parent_dir = tmp_path / "parent"
        parent_dir.mkdir()
        args = argparse.Namespace(
            seed=42, turns=5, civs=2, regions=4,
            output=str(parent_dir / "chronicle.md"),
            state=str(parent_dir / "state.json"),
            resume=None, reflection_interval=10,
            llm_actions=False, scenario=None,
            batch=None, fork=None, interactive=False,
            parallel=None, pause_every=None,
        )
        execute_run(args, sim_client=sim, narrative_client=narr)
        return parent_dir

    def test_fork_produces_chronicle_with_provenance(self, tmp_path):
        parent_dir = self._run_parent(tmp_path)
        sim = self._mock_llm()
        narr = self._mock_llm("Forked story.")
        fork_args = argparse.Namespace(
            seed=999, turns=8, civs=2, regions=4,
            output=str(tmp_path / "fork_out" / "chronicle.md"),
            state=str(tmp_path / "fork_out" / "state.json"),
            resume=None, reflection_interval=10,
            llm_actions=False, scenario=None,
            batch=None, fork=str(parent_dir / "state.json"),
            interactive=False, parallel=None, pause_every=None,
        )
        result = run_fork(fork_args, sim_client=sim, narrative_client=narr)
        chronicle = (tmp_path / "fork_out" / "chronicle.md").read_text()
        assert "Forked from seed 42" in chronicle
        assert result.total_turns > 0

    def test_fork_loads_memory_streams(self, tmp_path):
        parent_dir = self._run_parent(tmp_path)
        # Verify parent produced memory files
        memory_files = list(parent_dir.glob("memories_*.json"))
        assert len(memory_files) >= 1

        sim = self._mock_llm()
        narr = self._mock_llm("Forked.")
        fork_args = argparse.Namespace(
            seed=999, turns=8, civs=2, regions=4,
            output=str(tmp_path / "fork_out" / "chronicle.md"),
            state=str(tmp_path / "fork_out" / "state.json"),
            resume=None, reflection_interval=10,
            llm_actions=False, scenario=None,
            batch=None, fork=str(parent_dir / "state.json"),
            interactive=False, parallel=None, pause_every=None,
        )
        result = run_fork(fork_args, sim_client=sim, narrative_client=narr)
        assert result.seed == 999

    def test_fork_warns_about_missing_scenario(self, tmp_path, capsys):
        parent_dir = self._run_parent(tmp_path)
        # Set scenario_name on the saved state
        from chronicler.models import WorldState
        world = WorldState.load(parent_dir / "state.json")
        world.scenario_name = "Dead Miles"
        world.save(parent_dir / "state.json")

        sim = self._mock_llm()
        narr = self._mock_llm("Forked.")
        fork_args = argparse.Namespace(
            seed=999, turns=8, civs=2, regions=4,
            output=str(tmp_path / "fork_out" / "chronicle.md"),
            state=str(tmp_path / "fork_out" / "state.json"),
            resume=None, reflection_interval=10,
            llm_actions=False, scenario=None,
            batch=None, fork=str(parent_dir / "state.json"),
            interactive=False, parallel=None, pause_every=None,
        )
        run_fork(fork_args, sim_client=sim, narrative_client=narr)
        captured = capsys.readouterr()
        assert "Dead Miles" in captured.out
        assert "scenario" in captured.out.lower()

    def test_fork_requires_seed(self, tmp_path):
        parent_dir = self._run_parent(tmp_path)
        fork_args = argparse.Namespace(
            seed=None, turns=5, civs=2, regions=4,
            output=str(tmp_path / "fork_out" / "chronicle.md"),
            state=str(tmp_path / "fork_out" / "state.json"),
            resume=None, reflection_interval=10,
            llm_actions=False, scenario=None,
            batch=None, fork=str(parent_dir / "state.json"),
            interactive=False, parallel=None, pause_every=None,
        )
        with pytest.raises(ValueError, match="--seed is required"):
            run_fork(fork_args, sim_client=self._mock_llm(), narrative_client=self._mock_llm("Story."))

    def test_fork_requires_turns(self, tmp_path):
        parent_dir = self._run_parent(tmp_path)
        fork_args = argparse.Namespace(
            seed=999, turns=None, civs=2, regions=4,
            output=str(tmp_path / "fork_out" / "chronicle.md"),
            state=str(tmp_path / "fork_out" / "state.json"),
            resume=None, reflection_interval=10,
            llm_actions=False, scenario=None,
            batch=None, fork=str(parent_dir / "state.json"),
            interactive=False, parallel=None, pause_every=None,
        )
        with pytest.raises(ValueError, match="--turns is required"):
            run_fork(fork_args, sim_client=self._mock_llm(), narrative_client=self._mock_llm("Story."))
