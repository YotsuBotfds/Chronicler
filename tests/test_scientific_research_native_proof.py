"""Pure runner orchestration guards; these tests execute no native worlds."""
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import zlib

import pytest

pytestmark = pytest.mark.skipif(os.name != "posix", reason="proof uses POSIX per-worker CPU limits")


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
        (folder / "chronicle_bundle.json").write_text(json.dumps({"metadata": {"generated_at": "2026-10-29T00:00:00+00:00"},
            "world_state": {"retained": True}, "history": [{"turn": 3}, {"turn": 29}],
            "events_timeline": [{"turn": 27, "event_id": "actual-renewal"}]}))
        (folder / "mechanical-summary.json").write_text(json.dumps({"native_agent_final_sha256": "fixed",
            "active_native_pools": {"native.agent.0": {"sha256": "fixed"}}, "rng": {"python": "fixed"},
            "resume_provenance_validated": True, "expected_resume_metadata": None, "resume_metadata": None}))
        (folder / "ordinary_turn_29.json").write_text("actual-common-output")
    (left / "ordinary_turn_27.json").write_text("direct-prefix-only")
    good = r.compare(left, right)
    assert good["file_set_equal"] and all(good["files"].values()) and good["native_agent_equal"] and good["rng_equal"]
    data = json.loads((right / "chronicle_bundle.json").read_text())
    data["history"][0]["turn"] = 4  # full original prefix must still compare
    (right / "chronicle_bundle.json").write_text(json.dumps(data))
    assert not r.compare(left, right)["files"]["chronicle_bundle.json"]
    assert r.compare(left, right)["raw_bundle_differences"][0]["path"] == "$.history[0].turn"
    data["history"][0]["turn"] = 3
    data["metadata"]["resume"] = {"kind": "checkpoint", "exact": False, "mismatches": ["waived"]}
    (right / "chronicle_bundle.json").write_text(json.dumps(data))
    invalid = r.compare(left, right)
    assert not invalid["provenance_validated"] and not invalid["files"]["chronicle_bundle.json"]
    assert any(row["path"].startswith("$.metadata.resume") for row in invalid["raw_bundle_differences"])


def test_every_actual_native_section_is_hashed_and_linked_including_direct_runtime_slots(tmp_path, monkeypatch):
    from chronicler import run_checkpoint
    r = runner()
    def native_class(name):
        return type(name, (), {"checkpoint_state": lambda self: self.blob,
            "checkpoint_schema": staticmethod(lambda: (1, "fingerprint", "schema"))})
    classes = {name: native_class(name) for name in ("AgentSimulator", "EcologySimulator", "PoliticsSimulator")}
    monkeypatch.setitem(sys.modules, "chronicler_agents", SimpleNamespace(**classes))
    body, sections, objects = b"", [], {}
    for class_name, kind in (("AgentSimulator", "agent"), ("EcologySimulator", "ecology"), ("PoliticsSimulator", "politics")):
        obj = classes[class_name]()
        obj.blob = (kind + " actual native state").encode()
        objects[kind] = obj
        packed = zlib.compress(obj.blob)
        sections.append(dict(name="native." + kind + ".0", offset=len(body), length=len(packed),
            raw_length=len(obj.blob), sha256=r.hashlib.sha256(packed).hexdigest()))
        body += packed
    header = {"sections": sections}
    loaded = SimpleNamespace(header=header, state=SimpleNamespace(agent_bridge=SimpleNamespace(_sim=objects["agent"]),
        ecology_runtime=objects["ecology"], politics_runtime=objects["politics"]))
    monkeypatch.setattr(run_checkpoint, "read_header", lambda path: (header, body))
    result = r.native_sections(loaded, tmp_path / "checkpoint", retain=tmp_path)
    assert set(result) == {"native.agent.0", "native.ecology.0", "native.politics.0"}
    for kind, obj in objects.items():
        assert (tmp_path / ("native." + kind + ".0-final.bin")).read_bytes() == obj.blob
        assert result["native." + kind + ".0"]["sha256"] == r.hashlib.sha256(obj.blob).hexdigest()
    loaded.state.politics_runtime = None
    with pytest.raises(AssertionError, match="active pools differ"):
        r.native_sections(loaded, tmp_path / "checkpoint")


@pytest.mark.parametrize("left,right", [({"nested": [True]}, {"nested": [1]}),
    ({"nested": [-0.0]}, {"nested": [0.0]}), ({"a": 1, "b": 2}, {"b": 2, "a": 1})])
def test_full_json_differences_keep_nested_number_types_signed_zero_and_key_order(left, right):
    r = runner()
    assert r.json_differences(left, right)


def _comparison(seed):
    return dict(seed=seed, shared_parent_equal=True,
        exact_resume=dict(file_set_equal=True, files={"bundle": True}, native_agent_equal=True,
                          native_sections_equal=True, rng_equal=True, provenance_validated=True),
        pause_assessment=dict(archive_prefix_preserved=True, no_new_trial_funding=True, trial_spent_delta=0))


@pytest.mark.parametrize("failure", ["file", "native", "rng", "parent", "pause", "missing_seed", "budget"])
def test_completed_workers_are_not_qualification_when_a_required_comparison_fails(failure):
    r = runner()
    rows = [_comparison(42), _comparison(7)]
    assert r.qualification_pass(True, rows, [], 59)
    if failure == "file":
        rows[0]["exact_resume"]["files"]["bundle"] = False
    elif failure in ("native", "rng"):
        rows[0]["exact_resume"]["native_sections_equal" if failure == "native" else "rng_equal"] = False
    elif failure == "parent":
        rows[0]["shared_parent_equal"] = False
    elif failure == "pause":
        rows[0]["pause_assessment"]["no_new_trial_funding"] = False
    elif failure == "missing_seed":
        rows.pop()
    assert not r.qualification_pass(True, rows, [], 61 if failure == "budget" else 59)


def _pause_records():
    from copy import deepcopy
    plan = dict(schema_version=1, rule="finite-retained-v1", enabled=True, enabled_turn=2,
        policy_changed_turn=2, host_seal="host", next_open_turn=27, origin_cursor=0,
        academy_births=[{"seat": 0}], cycles=[])
    science = dict(research_agendas=plan, seat_ids=[0], claims=[{"id": 0}], trials=[{
        "id": 0, "funded_turn": 25, "cost": 3, "status": "running", "resolved_turn": None}],
        trial_spent=3, effort_spent=2, proposals=[{"claim": 0}], receipts=[], messages=[{"pending": True}])
    parent = dict(science=science, history=[{"turn": 27}], events=[{"turn": 26}])
    final = deepcopy(parent)
    after = final["science"]
    after["research_agendas"].update(enabled=False, policy_changed_turn=27)
    after["trials"][0].update(status="completed", resolved_turn=27)
    after["messages"] = []  # Delivery/expiry is allowed while admissions pause.
    final["history"].append({"turn": 29})
    receipt = {"research_policy": {"before": {"mode": plan["rule"], **deepcopy(plan)},
        "after": {"mode": plan["rule"], **deepcopy(after["research_agendas"])}, "requested_enabled": False}}
    return parent, final, receipt


@pytest.mark.parametrize("failure", ["funding", "host", "claim", "history"])
def test_pause_archive_rejects_new_funding_lineage_reset_or_prefix_rewrite(failure):
    r = runner()
    parent, final, receipt = _pause_records()
    assert r.validate_pause_archive(parent, final, receipt)["no_new_trial_funding"] is True
    if failure == "funding":
        final["science"]["trials"].append({"id": 1, "funded_turn": 27})
    elif failure == "host":
        final["science"]["research_agendas"]["host_seal"] = "replacement"
    elif failure == "claim":
        final["science"]["claims"][0]["id"] = 1
    else:
        final["history"][0]["turn"] = 28
    with pytest.raises(AssertionError):
        r.validate_pause_archive(parent, final, receipt)
