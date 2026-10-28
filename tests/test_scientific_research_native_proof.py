"""Pure runner orchestration guards; these tests execute no native worlds."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def runner():
    path = Path(__file__).resolve().parents[1] / "scripts/scientific_research_native_proof.py"
    spec = importlib.util.spec_from_file_location("research_native_proof", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_registered_main_arguments_keep_full_window_and_actual_checkpoint_boundary(tmp_path):
    from chronicler.main import _build_parser
    r = runner()
    args = _build_parser().parse_args(r.cli(tmp_path, 42))
    assert args.turns == 29 and args.checkpoint_turns == (27, 29)
    assert args.scientific_research_agendas is args.scientific_claims is args.scholarship is args.techniques is True
    assert all(getattr(args, feature) is True for feature in r.FEATURES)
    assert args.agents == "hybrid" and args.simulate_only and args.validation_sidecar


def _mocked(r, tmp_path, monkeypatch, *, spent=0):
    monkeypatch.setattr(r, "assert_frozen", lambda args: {"fixed": True})
    monkeypatch.setattr(r, "preflight", lambda seed: {"seed": seed})
    monkeypatch.setattr(r.resource, "getrusage", lambda kind: SimpleNamespace(ru_utime=spent, ru_stime=0))
    freeze = tmp_path / "freeze.json"
    freeze.write_text("prospectively recorded identity")
    return SimpleNamespace(source_root=str(tmp_path), freeze=str(freeze), output_root=str(tmp_path / "evidence"))


def test_failed_first_worker_stops_all_remaining_executions_and_preserves_receipts(tmp_path, monkeypatch):
    r = runner()
    args = _mocked(r, tmp_path, monkeypatch)
    calls = []

    def fail(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(r.subprocess, "run", fail)
    assert not r.orchestrate(args)
    report = json.loads((Path(args.output_root) / "report.json").read_text())
    assert len(calls) == 1 and len(report["runs"]) == 6
    assert report["runs"][0]["status"] == "failed"
    assert all(row["status"] == "not_attempted_after_failure" for row in report["runs"][1:])
    assert "seed-42-finite_direct.log" in report["files"]


def test_budget_reserves_full_worker_allowance_before_starting_another(tmp_path, monkeypatch):
    r = runner()
    args = _mocked(r, tmp_path, monkeypatch, spent=49)
    monkeypatch.setattr(r.subprocess, "run", lambda *a, **k: pytest.fail("no CPU budget for another worker"))
    assert not r.orchestrate(args)
    report = json.loads((Path(args.output_root) / "report.json").read_text())
    assert len(report["runs"]) == 6 and all(row["status"] == "budget_censored" for row in report["runs"])


def test_fixture_failure_records_exact_error_and_starts_no_worker(tmp_path, monkeypatch):
    r = runner()
    args = _mocked(r, tmp_path, monkeypatch)

    def fail(seed):
        raise ValueError("invalid owner index")

    monkeypatch.setattr(r, "preflight", fail)
    monkeypatch.setattr(r.subprocess, "run", lambda *a, **k: pytest.fail("fixture failed"))
    with pytest.raises(ValueError, match="owner index"):
        r.orchestrate(args)
    assert json.loads((Path(args.output_root) / "fixture-preflight-failure.json").read_text()) == {
        "type": "ValueError", "message": "invalid owner index"}


def test_exact_comparison_preserves_world_history_events_and_all_postcheckpoint_outputs(tmp_path):
    r = runner()
    left, right = tmp_path / "direct", tmp_path / "resume"
    for folder in (left, right):
        folder.mkdir()
        (folder / "chronicle_bundle.json").write_text(json.dumps({"metadata": {"generated_at": str(folder)},
            "world_state": {"retained": True}, "history": [{"turn": 3}, {"turn": 29}],
            "events_timeline": [{"turn": 27, "event_id": "actual-renewal"}]}))
        (folder / "mechanical-summary.json").write_text(json.dumps({"native_agent_final_sha256": "fixed", "rng": {"python": "fixed"}}))
        (folder / "ordinary_turn_29.json").write_text("actual-common-output")
    (left / "ordinary_turn_27.json").write_text("direct-prefix-only")
    good = r.compare(left, right)
    assert good["file_set_equal"] and all(good["files"].values()) and good["native_agent_equal"] and good["rng_equal"]
    data = json.loads((right / "chronicle_bundle.json").read_text())
    data["history"][0]["turn"] = 4  # full original prefix must still compare
    (right / "chronicle_bundle.json").write_text(json.dumps(data))
    assert not r.compare(left, right)["files"]["chronicle_bundle.json"]
