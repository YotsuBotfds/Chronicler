"""M19 end-to-end integration test: batch → analyze → compare."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def batch_args(tmp_path):
    import argparse
    return argparse.Namespace(
        seed=1, turns=5, civs=2, regions=4,
        output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=999,
        local_url="http://localhost:1234/v1",
        sim_model=None, narrative_model=None,
        llm_actions=False, scenario=None,
        batch=3, fork=None, interactive=False,
        parallel=None, pause_every=None,
        simulate_only=True, tuning=None,
        seed_range=None, live=False,
    )


class TestM19Integration:
    def _mock_llm(self, response="DEVELOP"):
        mock = MagicMock()
        mock.complete.return_value = response
        mock.model = "test-model"
        return mock

    def test_batch_then_analyze(self, batch_args, tmp_path):
        from chronicler.batch import run_batch
        from chronicler.analytics import generate_report, format_text_report

        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        batch_dir = run_batch(batch_args, sim_client=sim, narrative_client=narr)
        assert batch_dir.exists()

        report = generate_report(batch_dir, checkpoints=[2, 4])
        assert report["metadata"]["runs"] == 3
        assert "stability" in report
        assert "event_firing_rates" in report
        assert "anomalies" in report

        text = format_text_report(report)
        assert len(text) > 50

        report_path = batch_dir / "batch_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f)
        with open(report_path) as f:
            reloaded = json.load(f)
        assert reloaded["metadata"]["runs"] == 3

    def test_tuning_overrides_in_batch(self, batch_args, tmp_path):
        from chronicler.batch import run_batch

        tuning_file = tmp_path / "tuning.yaml"
        tuning_file.write_text("stability:\n  drain:\n    drought_immediate: 1\n")
        batch_args.tuning = str(tuning_file)

        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        batch_dir = run_batch(batch_args, sim_client=sim, narrative_client=narr)
        assert batch_dir.exists()
        bundles = list(batch_dir.glob("*/chronicle_bundle.json"))
        assert len(bundles) == 3

    def test_compare_two_reports(self):
        from chronicler.analytics import format_delta_report

        baseline = {
            "stability": {"zero_rate_by_turn": {"100": 0.43}, "percentiles_by_turn": {"5": {"median": 8}}},
            "event_firing_rates": {"famine": 0.99, "war": 0.5},
            "anomalies": [{"name": "stability_collapse", "severity": "CRITICAL", "detail": "bad"}],
        }
        current = {
            "stability": {"zero_rate_by_turn": {"100": 0.08}, "percentiles_by_turn": {"5": {"median": 31}}},
            "event_firing_rates": {"famine": 0.65, "war": 0.5},
            "anomalies": [],
        }
        text = format_delta_report(baseline, current)
        assert "RESOLVED" in text
        assert "stability_collapse" in text
