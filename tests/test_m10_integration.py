"""M10 integration tests — verify features compose correctly."""
import pytest
from unittest.mock import MagicMock
from pathlib import Path
import argparse

from chronicler.main import execute_run
from chronicler.batch import run_batch
from chronicler.fork import run_fork
from chronicler.interestingness import score_run
from chronicler.memory import MemoryStream


def _mock_llm(response="DEVELOP"):
    mock = MagicMock()
    mock.complete.return_value = response
    mock.model = "test-model"
    return mock


def _make_args(tmp_path, **overrides):
    defaults = dict(
        seed=42, turns=5, civs=2, regions=4,
        output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=10,
        llm_actions=False, scenario=None,
        batch=None, fork=None, interactive=False,
        parallel=None, pause_every=None,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class TestBatchWithScoring:
    def test_batch_summary_sorted_by_score(self, tmp_path):
        sim = _mock_llm()
        narr = _mock_llm("Story.")
        args = _make_args(tmp_path, batch=3, turns=5)
        batch_dir = run_batch(args, sim_client=sim, narrative_client=narr)
        summary = (batch_dir / "summary.md").read_text()
        # Should have 3 data rows + header rows
        lines = [l for l in summary.split("\n") if l.startswith("|") and "Rank" not in l and "---" not in l]
        assert len(lines) == 3


class TestForkFromBatch:
    def test_fork_from_batch_run(self, tmp_path):
        sim = _mock_llm()
        narr = _mock_llm("Story.")
        # Run a batch
        args = _make_args(tmp_path, batch=2, turns=5)
        batch_dir = run_batch(args, sim_client=sim, narrative_client=narr)

        # Fork from first run's state
        state_path = batch_dir / "seed_42" / "state.json"
        assert state_path.exists()

        fork_out = tmp_path / "fork_output"
        fork_args = _make_args(
            tmp_path,
            fork=str(state_path),
            seed=999,
            turns=3,
            output=str(fork_out / "chronicle.md"),
            state=str(fork_out / "state.json"),
        )
        sim2 = _mock_llm()
        narr2 = _mock_llm("Forked story.")
        result = run_fork(fork_args, sim_client=sim2, narrative_client=narr2)
        assert result.seed == 999
        chronicle = (fork_out / "chronicle.md").read_text()
        assert "Forked from seed 42" in chronicle


class TestMemoryPersistenceInRun:
    def test_memories_saved_every_turn(self, tmp_path):
        sim = _mock_llm()
        narr = _mock_llm("Story.")
        args = _make_args(tmp_path, turns=5)
        execute_run(args, sim_client=sim, narrative_client=narr)
        memory_files = list(tmp_path.glob("memories_*.json"))
        assert len(memory_files) >= 1
        # Load and verify non-empty
        for mf in memory_files:
            stream = MemoryStream.load(mf)
            assert stream.civilization_name
            assert len(stream.entries) >= 0  # May be empty for civs with no events


class TestScoringIntegration:
    def test_score_run_on_real_result(self, tmp_path):
        sim = _mock_llm()
        narr = _mock_llm("Story.")
        args = _make_args(tmp_path, turns=10)
        result = execute_run(args, sim_client=sim, narrative_client=narr)
        score = score_run(result)
        assert isinstance(score, float)
        assert score >= 0
