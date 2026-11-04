"""Evidence-harness failures, parent sharing and fresh-configuration boundary."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _runner():
    spec = importlib.util.spec_from_file_location("expansion_runner", ROOT / "scripts/run_expansion_experiment.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module._load_source(ROOT)
    return module


def _args(runner, path, *extra):
    return runner.build_parser().parse_args([
        "--feature", "harvest_forecasts", "--cohort", "development", "--seeds", "42",
        "--turns", "12", "--output-root", str(path), *extra,
    ])


def test_seed_ranges_do_not_manufacture_replicates():
    runner = _runner()
    assert runner.parse_seeds("7,0-2,42") == [0, 1, 2, 7, 42]
    for value in ("", "1,1", "2-1", "1-3,3", "-1", "true", "1-999999999"):
        with pytest.raises(ValueError):
            runner.parse_seeds(value)


def test_source_selection_refuses_to_mix_an_already_imported_checkout(tmp_path):
    runner = _runner()
    other = tmp_path / "other" / "src" / "chronicler"
    other.mkdir(parents=True)
    (other / "main.py").write_text("# Different source fixture")
    before = runner.source_identity()
    with pytest.raises(ValueError, match="different Chronicler source"):
        runner._load_source(tmp_path / "other")
    assert runner.source_identity() == before


@pytest.mark.parametrize("enabled", [True, False])
def test_research_initial_policy_is_explicit_only_on_parent_resumes_inherit_actual_saved_mode(tmp_path, enabled):
    runner = _runner()
    from chronicler.main import _build_parser
    config = {"feature": "scientific_claims", "worldgen": "template", "regions": 8, "civs": 4,
              "scientific_research_agendas": enabled}
    fresh = _build_parser().parse_args(runner._simulation_args(42, 30, tmp_path, config))
    resumed = _build_parser().parse_args(runner._simulation_args(42, 30, tmp_path, config, resume=tmp_path / "parent.ckpt"))
    assert fresh.scientific_research_agendas is enabled
    assert resumed.scientific_research_agendas is None


def test_research_policy_requires_supported_science_before_output_claim(tmp_path, monkeypatch):
    runner = _runner()
    output = tmp_path / "unused"
    with pytest.raises(ValueError, match="initial research policy requires"):
        runner.run_experiment(_args(runner, output, "--scientific-research-agendas"))
    monkeypatch.setattr(runner, "RESEARCH_CONFIGURATION_SUPPORTED", False)
    with pytest.raises(ValueError, match="initial research policy requires"):
        runner.run_experiment(_args(runner, output, "--feature", "scientific_claims", "--scientific-research-agendas"))
    assert not output.exists()


def test_new_external_runner_rejects_older_source_without_feature_before_claiming_output(tmp_path, monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner, "CONTROL_FIELDS", {key: value for key, value in runner.CONTROL_FIELDS.items()
                                                  if key != "scientific_claims"})
    output = tmp_path / "unused"
    with pytest.raises(ValueError, match="source does not register"):
        runner.run_experiment(_args(runner, output, "--feature", "scientific_claims"))
    assert not output.exists()


def test_worker_calls_real_entrypoint_without_supplying_a_preconfigured_world(tmp_path, monkeypatch):
    runner = _runner()
    from chronicler import main
    directory = tmp_path / "run"
    directory.mkdir()
    config = {"feature": "harvest_forecasts", "worldgen": "template", "regions": 8, "civs": 4}
    cli = runner._simulation_args(42, 4, directory, config, checkpoint=4)
    request = {"feature": "harvest_forecasts", "arm": "parent"}
    path = directory / "job.json"
    path.write_text(json.dumps({"source_root": str(ROOT), "simulation_args": cli, "request": request}))
    calls = []

    def capture(args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(main, "execute_run", capture)
    runner.run_job(path)
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert "world" not in kwargs and kwargs["checkpoint_resume"] is None
    assert kwargs["expansion_experiment"] == request
    assert args.harvest_forecasts is args.grain_reserves is args.contact_ledger is True
    assert args.health_care is args.ritual_gatherings is None
    assert args.agents == "hybrid" and args.simulate_only is True
    identity = json.loads((directory / "worker_identity.json").read_text())
    assert runner._identity_key(identity["before"]) == runner._identity_key(identity["after"])
    assert identity["schema_version"] == 2
    assert identity["before"]["environment"] == identity["after"]["environment"] == runner.environment_identity()
    assert identity["environment_stable"] is identity["identities_stable"] is True
    assert identity["runner_sha256"] == identity["runner_sha256_after"] == runner.file_sha256(Path(runner.__file__))


@pytest.mark.parametrize("change", ["thread_env", "packages", "python", "affinity_cpu_count"])
def test_actual_worker_environment_changes_fail_and_remain_in_receipt(tmp_path, monkeypatch, change):
    runner = _runner()
    from chronicler import main
    config = {"feature": "scientific_claims", "worldgen": "template", "regions": 8, "civs": 4}
    job = tmp_path / "job.json"
    job.write_text(json.dumps({"source_root": str(ROOT), "simulation_args": runner._simulation_args(
        42, 60, tmp_path, config), "request": {"feature": "scientific_claims", "arm": "parent"}}))
    before = runner.environment_identity()
    after = deepcopy(before)
    after[change] = {"changed": "observed"} if change in ("thread_env", "packages") else "changed"
    environments = iter((before, after))
    monkeypatch.setattr(runner, "environment_identity", lambda: next(environments))
    monkeypatch.setattr(main, "execute_run", lambda *a, **kw: None)
    with pytest.raises(RuntimeError, match="worker environment"):
        runner.run_job(job)
    saved = json.loads((tmp_path / "worker_identity.json").read_text())
    assert saved["before"]["environment"] == before and saved["after"]["environment"] == after
    assert saved["environment_stable"] is saved["identities_stable"] is False
    assert runner._identity_key(saved["before"]) == runner._identity_key(saved["after"])


def test_failed_worker_retains_measured_environment_without_hiding_original_error(tmp_path, monkeypatch):
    runner = _runner()
    from chronicler import main
    config = {"feature": "scientific_claims", "worldgen": "template", "regions": 8, "civs": 4}
    job = tmp_path / "job.json"
    job.write_text(json.dumps({"source_root": str(ROOT), "simulation_args": runner._simulation_args(
        42, 60, tmp_path, config), "request": {"feature": "scientific_claims", "arm": "parent"}}))

    def fail(*a, **kw):
        raise ValueError("original simulation failure")

    monkeypatch.setattr(main, "execute_run", fail)
    with pytest.raises(ValueError, match="original simulation failure"):
        runner.run_job(job)
    saved = json.loads((tmp_path / "worker_identity.json").read_text())
    assert saved["before"]["environment"] == saved["after"]["environment"] == runner.environment_identity()
    assert saved["environment_stable"] is saved["identities_stable"] is True


def test_all_arms_reference_one_parent_and_keep_their_full_controls(tmp_path, monkeypatch):
    runner = _runner()
    from chronicler.ablation_arms import CHECKPOINT_TURN_FILENAME
    calls = []

    def execute(path, seed, horizon, args, request, env):
        path.mkdir(parents=True)
        calls.append((path, horizon, args, request))
        if request["arm"] == "parent":
            (path / CHECKPOINT_TURN_FILENAME.format(turn=4)).write_bytes(b"parent-fixture")
        return {"seed": seed, "arm": request["arm"], "status": "complete"}

    monkeypatch.setattr(runner, "_execute", execute)
    config = {"feature": "ritual_gatherings", "name": "registered", "cohort": "development",
              "registration": None, "controls": {}, "fork_turn": 4, "turns": 12,
              "worldgen": "template", "regions": 8, "civs": 4, "arms": list(runner.ARMS["ritual_gatherings"])}
    records = runner._seed_runs(42, tmp_path, config, {})
    assert len(records) == 5
    assert calls[0][3]["fork"] is False
    parents = [call[3]["parent_checkpoint"] for call in calls[1:]]
    assert all(parent == parents[0] for parent in parents)
    assert parents[0]["sha256"] == runner.file_sha256(Path(parents[0]["path"]))
    assert all(call[3]["fork"] is True and call[1] == 12 for call in calls[1:])
    assert {call[3]["arm"]: call[3]["controls"] for call in calls[1:]} == runner.ARMS["ritual_gatherings"]


def test_scientific_arms_have_complete_distinct_controls_and_real_prerequisite_flags(tmp_path):
    runner = _runner()
    expected = {
        "normal": {"withhold_information": False, "transmission_enabled": True, "uninformative_tests": False},
        "withheld": {"withhold_information": True, "transmission_enabled": True, "uninformative_tests": False},
        "no_transmission": {"withhold_information": False, "transmission_enabled": False, "uninformative_tests": False},
        "uninformative": {"withhold_information": False, "transmission_enabled": True, "uninformative_tests": True},
    }
    assert runner.ARMS["scientific_claims"] == expected
    from chronicler.main import _build_parser
    config = {"feature": "scientific_claims", "worldgen": "template", "regions": 8, "civs": 4}
    parsed = _build_parser().parse_args(runner._simulation_args(42, 60, tmp_path, config, checkpoint=1))
    assert parsed.scientific_claims is parsed.scholarship is parsed.techniques is True
    assert parsed.agents == "hybrid" and parsed.checkpoint_turns == (1,)
    assert parsed.harvest_forecasts is parsed.ritual_gatherings is parsed.health_care is None
    assert parsed.grain_reserves is parsed.contact_ledger is None


def test_scientific_forks_share_pre_resolution_parent_without_clearing_state(tmp_path, monkeypatch):
    runner = _runner()
    from chronicler.ablation_arms import CHECKPOINT_TURN_FILENAME
    calls = []

    def execute(path, seed, horizon, args, request, env):
        path.mkdir(parents=True)
        calls.append((horizon, args, request))
        if request["arm"] == "parent":
            (path / CHECKPOINT_TURN_FILENAME.format(turn=1)).write_bytes(b"common-scientific-checkpoint")
        return {"seed": seed, "arm": request["arm"], "status": "complete"}

    monkeypatch.setattr(runner, "_execute", execute)
    config = {"feature": "scientific_claims", "name": "science-probe", "cohort": "development",
              "registration": None, "controls": {"publication_rule": "current-context-v1"}, "fork_turn": 1, "turns": 60,
              "worldgen": "template", "regions": 8, "civs": 4, "arms": list(runner.ARMS["scientific_claims"])}
    records = runner._seed_runs(42, tmp_path, config, {})
    assert len(records) == 5 and len(calls) == 5
    parents = [call[2]["parent_checkpoint"] for call in calls[1:]]
    assert all(parent == parents[0] for parent in parents)
    assert {call[2]["arm"]: call[2]["controls"] for call in calls[1:]} == {
        name: {"publication_rule": "current-context-v1", **controls}
        for name, controls in runner.ARMS["scientific_claims"].items()}
    assert all(set(call[2]["controls"]) == set(runner.CONTROL_FIELDS["scientific_claims"]) for call in calls[1:])
    assert all(call[0] == 60 and call[2]["fork"] is True for call in calls[1:])


def test_worker_rejects_a_receipt_parent_different_from_its_actual_resume_path(tmp_path):
    runner = _runner()
    config = {"feature": "harvest_forecasts", "worldgen": "template", "regions": 8, "civs": 4}
    cli = runner._simulation_args(42, 12, tmp_path, config, resume=tmp_path / "actual.ckpt")
    path = tmp_path / "job.json"
    path.write_text(json.dumps({"source_root": str(ROOT), "simulation_args": cli, "request": {
        "parent_checkpoint": {"path": str(tmp_path / "claimed.ckpt"), "sha256": "unused"}}}))
    with pytest.raises(ValueError, match="checkpoint being resumed"):
        runner.run_job(path)


def test_a_failed_parent_never_launches_its_treatment_arms(tmp_path, monkeypatch):
    runner = _runner()
    calls = []
    monkeypatch.setattr(runner, "_execute", lambda *a: calls.append(a) or {"status": "failed"})
    config = {"feature": "harvest_forecasts", "name": "test", "cohort": "development",
              "registration": None, "controls": {}, "fork_turn": 4, "turns": 12,
              "worldgen": "template", "regions": 8, "civs": 4, "arms": ["normal", "withheld"]}
    assert runner._seed_runs(42, tmp_path, config, {}) == [{"status": "failed"}]
    assert len(calls) == 1


def test_used_destinations_and_unregistered_control_changes_are_refused(tmp_path):
    runner = _runner()
    out = tmp_path / "used"
    out.mkdir()
    existing = out / "keep.txt"
    existing.write_text("preserve me")
    with pytest.raises(ValueError, match="not empty"):
        runner.run_experiment(_args(runner, out))
    assert existing.read_text() == "preserve me" and sorted(p.name for p in out.iterdir()) == ["keep.txt"]
    controls = tmp_path / "controls.json"
    controls.write_text('{"policy":"withhold"}')
    with pytest.raises(ValueError, match="arm-defining"):
        runner.run_experiment(_args(runner, tmp_path / "new", "--controls", str(controls)))
    assert not (tmp_path / "new").exists()
    with pytest.raises(ValueError, match="registration"):
        runner.run_experiment(_args(runner, tmp_path / "confirmatory", "--cohort", "confirmatory"))


@pytest.mark.parametrize("exit_code,completed", [(7, None), (0, 6)])
def test_failed_or_truncated_workers_are_hashed_failures_not_completed_runs(
    tmp_path, monkeypatch, exit_code, completed,
):
    runner = _runner()

    def child(command, **kwargs):
        if completed is not None:
            path = Path(command[-1]).parent / "chronicle_bundle.json"
            path.write_text(json.dumps({"world_state": {"turn": completed}, "metadata": {"seed": 42}}))
        return SimpleNamespace(returncode=exit_code)

    monkeypatch.setattr(runner.subprocess, "run", child)
    row = runner._execute(tmp_path / "worker", 42, 12, [],
                          {"arm": "normal", "feature": "harvest_forecasts"}, {})
    assert row["status"] == "failed" and row["error"]["type"] == "RuntimeError"
    assert row["command"][-2] == "--job"
    assert "job.json" in row["files"] and "worker.log" in row["files"]
    assert "receipt" not in row


@pytest.mark.parametrize("defect", [None, "missing", "missing_environment", "environment_drift",
                                   "source_drift", "native_drift", "runner_drift", "false_stability"])
def test_completed_workers_require_actual_hashed_stable_environment_receipts(tmp_path, monkeypatch, defect):
    runner = _runner()
    request = {"arm": "normal", "feature": "scientific_claims"}
    identity = {"source": runner.source_identity(), "native": runner.native_identity(),
                "environment": runner.environment_identity()}
    receipt = {"source": identity["source"], "native": identity["native"], **request,
               "controls_after": {"publication_rule": "current-context-v1", **runner.ARMS["scientific_claims"]["normal"]}}
    worker = {"schema_version": 2, "before": deepcopy(identity), "after": deepcopy(identity),
              "environment_stable": True, "identities_stable": True,
              "runner_sha256": runner.file_sha256(Path(runner.__file__)),
              "runner_sha256_after": runner.file_sha256(Path(runner.__file__))}
    if defect == "missing_environment":
        worker["before"].pop("environment")
    elif defect == "environment_drift":
        worker["after"]["environment"]["thread_env"] = {"OPENBLAS_NUM_THREADS": "8"}
    elif defect == "source_drift":
        worker["after"]["source"]["package_digest"] = "changed"
    elif defect == "native_drift":
        worker["after"]["native"]["sha256"] = "changed"
    elif defect == "runner_drift":
        worker["runner_sha256_after"] = "changed"
    elif defect == "false_stability":
        worker["environment_stable"] = False

    def child(command, **kwargs):
        path = Path(command[-1]).parent
        (path / "chronicle_bundle.json").write_text(json.dumps({
            "world_state": {"turn": 60}, "metadata": {"seed": 42, "expansion_experiment": receipt}}))
        if defect != "missing":
            (path / "worker_identity.json").write_text(json.dumps(worker))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", child)
    row = runner._execute(tmp_path / "worker", 42, 60, [], request, {})
    assert row["status"] == ("complete" if defect is None else "failed")
    if defect is None:
        assert row["worker_identity_verified"] is True
        assert "worker_identity.json" in row["files"]
    else:
        assert "worker_identity_verified" not in row and "receipt" not in row


def test_source_changes_cannot_be_labelled_a_completed_experiment(tmp_path, monkeypatch):
    runner = _runner()
    before = {"git_sha": "before", "package_digest": "same"}
    after = {"git_sha": "after", "package_digest": "changed"}
    source = iter([before, after])
    monkeypatch.setattr(runner, "source_identity", lambda: next(source))
    native = runner.native_identity()

    def seed_runs(seed, root, config, env):
        return [{"seed": seed, "arm": arm, "status": "complete", "receipt": {
            "source": before, "native": native}} for arm in ("parent", *config["arms"])]

    monkeypatch.setattr(runner, "_seed_runs", seed_runs)
    manifest = runner.run_experiment(_args(runner, tmp_path / "changed"))
    assert manifest["status"] == "failed" and manifest["identities_stable"] is False
    saved = json.loads((tmp_path / "changed" / runner.MANIFEST).read_text())
    assert saved["source_after"] == after and len(saved["runs"]) == 4


def test_worker_import_source_labels_do_not_confuse_identical_native_bytes():
    runner = _runner()
    left = {"source": {"git_sha": "a", "package_digest": "b"},
            "native": {"status": "found", "source": "import_path", "sha256": "c"}}
    right = {"source": left["source"],
             "native": {"status": "found", "source": "imported", "sha256": "c"}}
    assert runner._identity_key(left) == runner._identity_key(right)


# This selection loads only the stdlib runner and source AST literals. It never
# calls _load_source, imports a product module or starts a simulation worker.
def _receipt_only_runner(script=None, *, legacy=False):
    import ast
    script = ROOT / "scripts/run_expansion_experiment.py" if script is None else script
    spec = importlib.util.spec_from_file_location("receipt_only_expansion_runner", script)
    runner = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(runner)
    source = ast.parse((ROOT / "src/chronicler/expansion_experiment.py").read_text())
    literals = {target.id: ast.literal_eval(node.value)
                for node in source.body if isinstance(node, ast.Assign)
                for target in node.targets if isinstance(target, ast.Name)
                and target.id in ("CONTROL_FIELDS", "_RECEIPT_CONTROL_POLICIES")}
    runner.CONTROL_FIELDS = literals["CONTROL_FIELDS"]
    policies = {} if legacy else literals["_RECEIPT_CONTROL_POLICIES"]
    runner.receipt_control_policy = policies.get
    assert runner._LOADED_SOURCE is False
    return runner


def _receipt_policy_values(feature):
    return ({"policy": "normal"} if feature == "harvest_forecasts" else
            {"care_enabled": True, "injury_rate": 0.05, "impairment": 0.5,
             "care_fraction": 0.1, "recovery_work": 2.0})


def _receipt_policy_case(runner, feature, case):
    field, (legacy, active) = runner.receipt_control_policy(feature)
    controls, before, after = {}, _receipt_policy_values(feature), _receipt_policy_values(feature)
    if case == "explicit_optin":
        controls[field], before[field], after[field] = active, legacy, active
    elif case == "explicit_legacy":
        controls[field] = before[field] = after[field] = legacy
    elif case == "inherited_active":
        before[field] = after[field] = active
    elif case == "explicit_reversion":
        controls[field], before[field], after[field] = legacy, active, legacy
    elif case == "explicit_active_noop":
        controls[field] = before[field] = after[field] = active
    elif case != "legacy_omitted":
        raise AssertionError(case)
    request = {"feature": feature, "arm": "normal", "controls": controls}
    return request, {"feature": feature, "arm": "normal", "controls_before": before, "controls_after": after}


def _receipt_fake_execute(runner, monkeypatch, directory, request, receipt):
    import hashlib
    runner.atomic_write_json = lambda path, value: path.write_text(json.dumps(value))
    runner.strict_json_loads = lambda text, **kwargs: json.loads(text)
    runner.file_sha256 = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    identity = {"source": {"git_sha": "fake-source", "package_digest": "fake-package"},
                "native": {"status": "found", "sha256": "fake-native"},
                "environment": {"python": "fake-worker"}}
    receipt = {**receipt, "source": identity["source"], "native": identity["native"]}
    worker = {"schema_version": 2, "before": deepcopy(identity), "after": deepcopy(identity),
              "environment_stable": True, "identities_stable": True,
              "runner_sha256": runner.file_sha256(Path(runner.__file__)),
              "runner_sha256_after": runner.file_sha256(Path(runner.__file__))}
    calls = []
    def child(command, **kwargs):
        calls.append(command)
        folder = Path(command[-1]).parent
        (folder / "chronicle_bundle.json").write_text(json.dumps({
            "world_state": {"turn": 12}, "metadata": {"seed": 42, "expansion_experiment": receipt}}))
        (folder / "worker_identity.json").write_text(json.dumps(worker))
        return SimpleNamespace(returncode=0)
    # Replace the script's module binding, not the process-wide subprocess API.
    monkeypatch.setattr(runner, "subprocess", SimpleNamespace(run=child, STDOUT=-2))
    row = runner._execute(directory, 42, 12, [], request, {})
    assert len(calls) == 1 and runner._LOADED_SOURCE is False
    return row


@pytest.mark.parametrize("feature", ["harvest_forecasts", "health_care"])
def test_policy_receipt_descriptor_matches_source_getter_literals_without_product_import(feature):
    import ast
    runner = _receipt_only_runner()
    field, values = runner.receipt_control_policy(feature)
    path = ROOT / "src/chronicler" / ("harvest_forecasts.py" if feature == "harvest_forecasts" else "health_care.py")
    tree = ast.parse(path.read_text())
    name = "get_preparation_policy" if feature == "harvest_forecasts" else "get_health_care_policy"
    getter = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    get = next(node for node in ast.walk(getter) if isinstance(node, ast.Call)
               and isinstance(node.func, ast.Name) and node.func.id == "getattr")
    assert ast.literal_eval(get.args[1]) == field and ast.literal_eval(get.args[2]) == values[0]
    allowed = next(node for node in ast.walk(getter) if isinstance(node, ast.Compare)
                   and any(isinstance(op, ast.NotIn) for op in node.ops))
    assert ast.literal_eval(allowed.comparators[0]) == values


@pytest.mark.parametrize("feature", ["harvest_forecasts", "health_care"])
@pytest.mark.parametrize("case", ["legacy_omitted", "explicit_optin", "explicit_legacy", "inherited_active",
                                 "explicit_reversion", "explicit_active_noop"])
def test_policy_receipt_valid_worker_completes_without_product_import(tmp_path, monkeypatch, feature, case):
    runner = _receipt_only_runner()
    request, receipt = _receipt_policy_case(runner, feature, case)
    original = deepcopy(receipt)
    row = _receipt_fake_execute(runner, monkeypatch, tmp_path / "worker", request, receipt)
    assert row["status"] == "complete" and row["worker_identity_verified"] is True
    assert row["receipt"]["controls_before"] == original["controls_before"]
    assert row["receipt"]["controls_after"] == original["controls_after"]
    assert receipt == original and "worker_identity.json" in row["files"]


@pytest.mark.parametrize("feature", ["harvest_forecasts", "health_care"])
@pytest.mark.parametrize("defect", ["extra_after", "missing_base_after", "extra_before", "missing_base_before",
    "missing_before_policy", "missing_after_policy", "missing_both_explicit", "missing_before", "invalid_before",
    "invalid_after", "boolean_policy", "invalid_request", "request_mismatch", "unrequested_change", "redundant_legacy"])
def test_policy_receipt_invalid_worker_fails_without_product_import(tmp_path, monkeypatch, feature, defect):
    runner = _receipt_only_runner()
    request, receipt = _receipt_policy_case(runner, feature, "explicit_optin")
    field, (legacy, active) = runner.receipt_control_policy(feature)
    before, after = receipt["controls_before"], receipt["controls_after"]
    if defect == "extra_after": after["unknown"] = True
    elif defect == "missing_base_after": after.pop(next(iter(_receipt_policy_values(feature))))
    elif defect == "extra_before": before["unknown"] = True
    elif defect == "missing_base_before": before.pop(next(iter(_receipt_policy_values(feature))))
    elif defect == "missing_before_policy": before.pop(field)
    elif defect == "missing_after_policy": after.pop(field)
    elif defect == "missing_both_explicit": before.pop(field); after.pop(field)
    elif defect == "missing_before": receipt.pop("controls_before")
    elif defect == "invalid_before": before[field] = "unknown"
    elif defect == "invalid_after": after[field] = "unknown"
    elif defect == "boolean_policy": after[field] = True
    elif defect == "invalid_request": request["controls"][field] = False
    elif defect == "request_mismatch": after[field] = legacy
    elif defect == "unrequested_change": request["controls"] = {}; before[field], after[field] = active, legacy
    elif defect == "redundant_legacy": request["controls"] = {}; before[field] = after[field] = legacy
    row = _receipt_fake_execute(runner, monkeypatch, tmp_path / "worker", request, receipt)
    assert row["status"] == "failed" and row["error"]["type"] == "RuntimeError"
    assert "receipt" not in row and "worker_identity_verified" not in row
    assert "chronicle_bundle.json" in row["files"] and "worker.log" in row["files"]


@pytest.mark.parametrize("feature", ["harvest_forecasts", "health_care"])
@pytest.mark.parametrize("case", ["inherited_active", "legacy_omitted", "explicit_reversion", "explicit_optin"])
def test_policy_receipt_parent_matching_preserves_resolved_modes(feature, case):
    runner = _receipt_only_runner()
    request, receipt = _receipt_policy_case(runner, feature, case)
    parent = deepcopy(receipt["controls_before"])
    original = deepcopy((receipt, request, parent))
    runner._validate_receipt_controls(receipt, request, parent_controls=parent)
    assert (receipt, request, parent) == original


@pytest.mark.parametrize("feature", ["harvest_forecasts", "health_care"])
@pytest.mark.parametrize("defect", ["both_omitted_inherited", "different_before", "invalid_parent"])
def test_policy_receipt_parent_rejects_inherited_omission_and_mismatch(feature, defect):
    runner = _receipt_only_runner()
    request, receipt = _receipt_policy_case(runner, feature, "inherited_active")
    field, (legacy, active) = runner.receipt_control_policy(feature)
    parent = deepcopy(receipt["controls_before"])
    if defect == "both_omitted_inherited":
        receipt["controls_before"].pop(field); receipt["controls_after"].pop(field)
        # Individually it has the valid legacy omitted shape; parent binding
        # supplies the independent evidence that this fork lost its policy.
        runner._validate_receipt_controls(receipt, request)
    elif defect == "different_before":
        parent.pop(field)
    elif defect == "invalid_parent": parent[field] = "unknown"
    with pytest.raises(RuntimeError, match="shared parent"):
        runner._validate_receipt_controls(receipt, request, parent_controls=parent)


def test_policy_receipt_shared_parent_check_precedes_noop_state_comparison():
    import ast
    runner = _receipt_only_runner()
    tree = ast.parse(Path(runner.__file__).read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_seed_runs")
    checks = [node for node in ast.walk(function) if isinstance(node, ast.Call)
              and isinstance(node.func, ast.Name) and node.func.id == "_validate_receipt_controls"]
    assert len(checks) == 1
    assert any(key.arg == "parent_controls" and isinstance(key.value, ast.Name)
               and key.value.id == "parent_controls" for key in checks[0].keywords)
    noop = next(node for node in ast.walk(function) if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "research_policy" for target in node.targets))
    assert checks[0].lineno < noop.lineno


@pytest.mark.parametrize("feature", ["harvest_forecasts", "health_care"])
@pytest.mark.parametrize("case", ["legacy_omitted", "explicit_optin", "explicit_legacy", "inherited_active"])
def test_policy_receipt_older_source_fallback_remains_exact(tmp_path, monkeypatch, feature, case):
    current = _receipt_only_runner()
    request, receipt = _receipt_policy_case(current, feature, case)
    runner = _receipt_only_runner(legacy=True)
    row = _receipt_fake_execute(runner, monkeypatch, tmp_path / "worker", request, receipt)
    assert row["status"] == ("complete" if case == "legacy_omitted" else "failed")


@pytest.mark.parametrize("defect", [None, "research_in_after", "research_instead_of_base", "unknown_after"])
def test_policy_receipt_science_research_metadata_stays_separate(tmp_path, monkeypatch, defect):
    runner = _receipt_only_runner()
    request = {"feature": "scientific_claims", "arm": "normal", "controls": {"research_enabled": True}}
    controls = {"publication_rule": "current-context-v1", **runner.ARMS["scientific_claims"]["normal"]}
    receipt = {"feature": "scientific_claims", "arm": "normal", "controls_after": controls,
               "research_policy": {"before": {"mode": "legacy"}, "after": {"mode": "finite-v1"}}}
    if defect == "research_in_after": controls["research_enabled"] = True
    elif defect == "research_instead_of_base": controls.pop("publication_rule"); controls["research_enabled"] = True
    elif defect == "unknown_after": controls["unknown"] = True
    row = _receipt_fake_execute(runner, monkeypatch, tmp_path / "worker", request, receipt)
    assert row["status"] == ("complete" if defect is None else "failed")
