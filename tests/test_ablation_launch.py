"""Contract-only stage: no controller, child, native runtime or world execution."""
from __future__ import annotations

import builtins
from dataclasses import FrozenInstanceError
import json
from types import SimpleNamespace

import pytest

from chronicler import ablation_arms as aa
from chronicler import ablation_launch as launch


def _eligible_host(monkeypatch):
    monkeypatch.setattr(launch.sys, "platform", "linux")
    monkeypatch.setattr(launch.sys, "version_info", (3, 13, 5))
    monkeypatch.setattr(launch.sys, "implementation", SimpleNamespace(name="cpython"))
    monkeypatch.setattr(launch.os, "pidfd_open", lambda *_: None, raising=False)
    monkeypatch.setattr(launch.os, "wait4", lambda *_: None, raising=False)
    monkeypatch.setattr(launch.signal, "pidfd_send_signal", lambda *_: None, raising=False)


@pytest.mark.parametrize("selection", [None, False, "typo", "models-forkserver"])
def test_backend_refuses_before_any_source_probe_destination_or_batch_read(tmp_path, monkeypatch, selection):
    _eligible_host(monkeypatch)
    original_import = builtins.__import__

    def no_source_probe(name, *args, **kwargs):
        if name == "chronicler.batch_manifest":
            pytest.fail("backend refusal reached source/native probes or destination check")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_source_probe)
    expected = launch.BackendUnavailableError if selection == "models-forkserver" else ValueError
    with pytest.raises(expected):
        aa.run_ablation_arms(tmp_path / "missing-plain", tmp_path / "unclaimed",
                             total_turns=122, launch_backend=selection)
    assert list(tmp_path.iterdir()) == []


def test_default_fresh_never_imports_new_contracts_or_changes_manifest_shape(tmp_path, monkeypatch):
    from chronicler import batch_manifest

    original_import = builtins.__import__

    def no_backend_import(name, *args, **kwargs):
        if name in {"chronicler.ablation_launch", "multiprocessing", "multiprocessing.forkserver"}:
            pytest.fail("default fresh path imported opt-in backend machinery")
        return original_import(name, *args, **kwargs)

    batch = tmp_path / "plain"
    batch.mkdir()
    (batch / "batch_manifest.json").write_text(json.dumps({
        "status": "complete", "runs": [{"seed": 42, "dir": "seed_42"}],
    }))
    monkeypatch.setattr(batch_manifest, "source_identity", lambda: {"source": "existing"})
    monkeypatch.setattr(batch_manifest, "native_identity", lambda: None)
    monkeypatch.setattr(builtins, "__import__", no_backend_import)
    result = aa.run_ablation_arms(batch, tmp_path / "forks", total_turns=100, env={}, log=lambda *_: None)
    assert result["status"] == "complete" and result["forks"] == []
    assert set(result) == {
        "kind", "schema_version", "design", "status", "started_at", "plain_batch_dir",
        "plain_manifest_sha256", "arms", "window_turns", "fork_rule", "fork_turns", "seeds",
        "source", "native", "forks", "fork_count", "seconds", "finished_at",
    }
    assert result["arms"] == ["needs", "kin_roots"]
    assert (batch / "batch_manifest.json").is_file()


@pytest.mark.parametrize("changes,match", [
    ({"parallel": 2}, "one worker"),
    ({"parallel": True}, "one worker"),
    ({"lean_output": False}, "lean"),
    ({"lean_output": 1}, "lean"),
    ({"window": 21}, "20-turn"),
    ({"window": True}, "20-turn"),
    ({"arms": ()}, "unique needs"),
    ({"arms": ("needs", "needs")}, "unique needs"),
    ({"arms": ("placebo",)}, "unique needs"),
    ({"arms": ("community_anchor",)}, "unique needs"),
    ({"arms": ([],)}, "unique needs"),
])
def test_unsupported_opt_in_configuration_refuses_without_outputs(tmp_path, monkeypatch, changes, match):
    _eligible_host(monkeypatch)
    kwargs = dict(arms=("needs", "kin_roots"), parallel=1, lean_output=True, window=20)
    kwargs.update(changes)
    with pytest.raises(ValueError, match=match):
        aa.run_ablation_arms(tmp_path / "plain", tmp_path / "out", total_turns=122,
                             launch_backend="models-forkserver", **kwargs)
    assert list(tmp_path.iterdir()) == []


def test_invalid_arm_iterator_is_consumed_only_to_the_fixed_admission_bound(monkeypatch):
    _eligible_host(monkeypatch)
    consumed = []

    def arms():
        for index in range(100):
            consumed.append(index)
            yield "needs"

    with pytest.raises(ValueError, match="unique needs"):
        launch.refuse_unqualified_backend("models-forkserver", arms=arms(), parallel=1,
                                          lean_output=True, window=20)
    assert consumed == [0, 1, 2]


@pytest.mark.parametrize("changed", ["platform", "implementation", "version", "pidfd", "wait4", "signal"])
def test_platform_primitives_are_required_before_unavailable_backend_result(monkeypatch, changed):
    _eligible_host(monkeypatch)
    if changed == "platform":
        monkeypatch.setattr(launch.sys, "platform", "win32")
    elif changed == "implementation":
        monkeypatch.setattr(launch.sys, "implementation", SimpleNamespace(name="pypy"))
    elif changed == "version":
        monkeypatch.setattr(launch.sys, "version_info", (3, 14, 0))
    elif changed == "signal":
        monkeypatch.setattr(launch.signal, "pidfd_send_signal", None)
    else:
        monkeypatch.setattr(launch.os, "pidfd_open" if changed == "pidfd" else "wait4", None)
    with pytest.raises(ValueError, match="Linux CPython 3.13"):
        launch.refuse_unqualified_backend("models-forkserver", arms=("needs",), parallel=1,
                                          lean_output=True, window=20)


def _job(job_id="job-1"):
    return launch.LaunchJob(job_id, ("python", "-m", "chronicler.main", "--resume", "/opaque path/p.ckpt"))


def _outcome(job_id="job-1", status="succeeded", returncode=0, cleanup_confirmed=True):
    return launch.LaunchOutcome(job_id, status, returncode, cleanup_confirmed)


def test_opaque_contracts_round_trip_without_rewriting_argv_and_are_immutable():
    job = _job()
    result = _outcome()
    assert launch.LaunchJob.from_payload(json.loads(json.dumps(job.payload()))) == job
    assert launch.LaunchOutcome.from_payload(json.loads(json.dumps(result.payload()))) == result
    assert job.argv[-1] == "/opaque path/p.ckpt"
    with pytest.raises(FrozenInstanceError):
        job.job_id = "changed"
    with pytest.raises(FrozenInstanceError):
        result.status = "succeeded"


@pytest.mark.parametrize("payload", [
    {"job_id": "job-1", "argv": ["python"], "world": {}},
    {"job_id": "job-1"},
    {"job_id": "../job", "argv": ["python"]},
    {"job_id": "job-1", "argv": []},
    {"job_id": "job-1", "argv": ["python", {}]},
    {"job_id": "job-1", "argv": ["python", "bad\0argument"]},
    {"job_id": "job-1", "argv": [""]},
    {"job_id": "job-1", "argv": ["python"] * (launch.MAX_ARGV_ITEMS + 1)},
    {"job_id": "job-1", "argv": ["python", "a" * (launch.MAX_ARGUMENT_BYTES + 1)]},
    {"job_id": "job-1", "argv": ["python", "\U0001f331" * 4097]},
    {"job_id": "job-1", "argv": ["python"] + ["a" * 16000] * 9},
])
def test_job_payload_is_closed_typed_and_bounded(payload):
    with pytest.raises(ValueError):
        launch.LaunchJob.from_payload(payload)


@pytest.mark.parametrize("changes", [
    {"status": "running"}, {"status": True}, {"returncode": True},
    {"returncode": None}, {"returncode": 1}, {"cleanup_confirmed": False},
    {"cleanup_confirmed": 1}, {"status": "unattempted", "returncode": 0},
    {"unknown": "field"},
])
def test_result_payload_cannot_claim_success_from_incomplete_or_untyped_evidence(changes):
    payload = _outcome().payload()
    payload.update(changes)
    with pytest.raises(ValueError):
        launch.LaunchOutcome.from_payload(payload)


def test_batch_coverage_requires_exact_unique_ids_and_restores_submission_order():
    jobs = (_job("one"), _job("two"))
    outcomes = (_outcome("two"), _outcome("one"))
    assert launch.ordered_outcomes(jobs, outcomes) == tuple(reversed(outcomes))
    assert launch.batch_succeeded(jobs, outcomes)
    for invalid in (outcomes[:1], outcomes + (_outcome("other"),),
                    (_outcome("one"), _outcome("one")), (_outcome("one"), _outcome("unknown"))):
        with pytest.raises(ValueError):
            launch.batch_succeeded(jobs, invalid)


@pytest.mark.parametrize("status,returncode,cleanup", [
    ("failed", 9, True), ("failed", 0, False), ("failed", None, False),
    ("cancelled", -15, True), ("unattempted", None, True),
])
def test_all_non_success_terminal_states_remain_batch_failure(status, returncode, cleanup):
    jobs = (_job("one"), _job("two"))
    outcomes = (_outcome("one"), _outcome("two", status, returncode, cleanup))
    assert not launch.batch_succeeded(jobs, outcomes)


def test_empty_duplicate_or_oversized_batches_never_pass_vacuously():
    for jobs, outcomes in (((), ()), ((_job(), _job()), (_outcome(), _outcome())),
                           (tuple(_job(str(i)) for i in range(9)), tuple(_outcome(str(i)) for i in range(9)))):
        with pytest.raises(ValueError):
            launch.batch_succeeded(jobs, outcomes)
