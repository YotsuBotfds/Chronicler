"""Pure closed runtime-selection contracts, without native imports or study ticks."""
from copy import deepcopy
from pathlib import Path

import pytest

from test_research_natural_continuation import modules
from test_research_natural_readout import synthetic

ROOT = Path(__file__).resolve().parents[1]


def observed(c, name):
    selected = c.P.policy(name)
    threads = {key: "1" for key in (*c.THREADS, "PYTHON_CPU_COUNT")}
    threads.update(PYTHONHASHSEED="0", OPENBLAS_THREAD_TIMEOUT="16")
    return dict(source=dict(git_sha=c.SOURCE, package_digest=selected["package_digest"]),
        native=dict(status="found", sha256=selected["native_sha256"], bytes=selected["native_bytes"],
                    module_file="/explicit-fixture/compiled.so"), compiled_origin="/explicit-fixture/compiled.so",
        available_compiled_classes=deepcopy(selected["schemas"]),
        environment=dict(python=selected["python"], implementation="CPython", machine="x86_64", platform="Linux-explicit-synthetic-fixture",
            affinity_cpu_count=1, packages=deepcopy(selected["packages"]), thread_env=threads))


def test_closed_policies_preserve_default_and_do_not_alias_mutable_records(modules):
    c, _, _ = modules
    default = c.P.policy()
    assert default["name"] == "local-fb20" and default["native_sha256"] == c.NATIVE
    assert default["artifact"] is default["execution_registration"] is None
    cloud = c.P.policy("cloud-fullgate-06db")
    assert cloud["artifact"]["id"] == 12861488234 and cloud["python"] == "3.13.17"
    cloud["schemas"]["AgentSimulator"]["version"] = 99
    cloud["artifact"]["sha256"] = "supplied-digest"
    assert c.P.policy("cloud-fullgate-06db")["schemas"]["AgentSimulator"]["version"] == 1
    assert c.P.policy("cloud-fullgate-06db")["artifact"]["sha256"] != "supplied-digest"
    for name in (None, True, "fb20", default["native_sha256"], {"name": "local-fb20"}):
        with pytest.raises(ValueError, match="unregistered"):
            c.P.policy(name)


@pytest.mark.parametrize("name", ["local-fb20", "cloud-fullgate-06db"])
def test_both_registered_policies_match_only_their_exact_runtime(modules, name):
    c, _, _ = modules
    actual = observed(c, name)
    assert c.P.validate_runtime(name, actual, c.same)["name"] == name
    other = next(value for value in c.P.NAMES if value != name)
    with pytest.raises(ValueError):
        c.P.validate_runtime(other, actual, c.same)


def test_policy_schema_order_matches_live_builder_and_sorted_manifest_projection(modules):
    import ast
    import inspect
    c, runner, _ = modules
    tree = ast.parse(inspect.getsource(runner.runtime))
    constructors = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == "dict"
        and [keyword.arg for keyword in node.keywords] == ["version", "fingerprint", "schema_sha256"]]
    assert len(constructors) == 1
    for row in c.P.policy()["schemas"].values():
        assert list(row) == ["version", "fingerprint", "schema_sha256"]
    projected = c.checkpoint_projection(c.P.policy()["schemas"])
    assert list(projected["AgentSimulator"]) == ["fingerprint", "schema_sha256", "version"]
    assert not c.same(projected, c.P.policy()["schemas"])


@pytest.mark.parametrize("fault", ["source", "package", "native", "bytes", "origin", "schema", "python", "platform", "affinity", "packages", "threads"])
def test_recorded_policy_cannot_admit_mismatched_identity(modules, fault):
    c, _, _ = modules
    actual = observed(c, c.P.CLOUD_POLICY)
    if fault == "source": actual["source"]["git_sha"] = "different"
    elif fault == "package": actual["source"]["package_digest"] = "different"
    elif fault == "native": actual["native"]["sha256"] = c.NATIVE
    elif fault == "bytes": actual["native"]["bytes"] = True
    elif fault == "origin": actual["compiled_origin"] = "/another/compiled.so"
    elif fault == "schema": actual["available_compiled_classes"]["AgentSimulator"]["version"] = True
    elif fault == "python": actual["environment"]["python"] = "3.13.5"
    elif fault == "platform": actual["environment"]["platform"] = "Darwin-explicit-synthetic-fixture"
    elif fault == "affinity": actual["environment"]["affinity_cpu_count"] = True
    elif fault == "packages": actual["environment"]["packages"]["numpy"] = "different"
    else: actual["environment"]["thread_env"]["UNREGISTERED"] = "1"
    frozen = dict(runtime_policy=c.P.policy(c.P.CLOUD_POLICY), runtime=actual)
    with pytest.raises(c.ContractError, match="runtime policy"):
        c.selected_policy(frozen)


def test_reader_refuses_a_changed_policy_before_strict_comparison(synthetic):
    c, reader, root, frozen, decode, prune = synthetic
    changed = deepcopy(frozen)
    changed["runtime_policy"]["native_sha256"] = "arbitrary-allowed-digest"
    with pytest.raises(c.ContractError, match="closed registration"):
        reader.inspect_role(root, 2000, "active", changed, decode, prune)
    changed = deepcopy(frozen)
    changed["runtime_policy"] = c.P.policy(c.P.CLOUD_POLICY)
    with pytest.raises(c.ContractError, match="runtime policy"):
        reader.inspect_role(root, 2000, "active", changed, decode, prune)


def test_local_policy_refuses_wheel_evidence_and_cloud_requires_it(modules, tmp_path):
    c, runner, _ = modules
    with pytest.raises(c.ContractError, match="does not accept"):
        runner.policy_evidence(tmp_path, c.P.policy(), tmp_path / "unregistered.json")
    with pytest.raises(c.ContractError, match="requires verified"):
        runner.policy_evidence(tmp_path, c.P.policy(c.P.CLOUD_POLICY), None)


def test_worker_cannot_claim_a_different_selected_policy(synthetic):
    c, reader, root, frozen, decode, prune = synthetic
    path = root / "seed-2000/active/worker-summary.json"
    value = c.read(path)
    value["runtime_policy"] = c.P.CLOUD_POLICY
    path.write_bytes(c.encoded(value))
    with pytest.raises(c.ContractError, match="worker runtime policy"):
        reader.inspect_role(root, 2000, "active", frozen, decode, prune)


def test_freeze_mismatched_explicit_policy_stops_before_runtime_inspection(modules, tmp_path, monkeypatch):
    c, runner, _ = modules
    path = tmp_path / "freeze.json"
    c.write(path, dict(runtime_policy=c.P.policy(), runtime=observed(c, c.P.DEFAULT_POLICY)))
    monkeypatch.setattr(runner, "identity", lambda *a: pytest.fail("mismatched policy must stop before runtime imports"))
    with pytest.raises(c.ContractError, match="explicit runtime policy"):
        runner.verify_freeze(tmp_path, path, c.P.CLOUD_POLICY)


def test_cli_policy_choice_has_no_digest_override_or_environment_fallback(modules, tmp_path, monkeypatch):
    c, runner, _ = modules
    selected = []
    monkeypatch.setenv("CHRONICLER_NATIVE_SHA256", "supplied-digest")
    monkeypatch.setattr(runner, "identity", lambda source, policy_name, receipt: selected.append((policy_name, receipt)) or {})
    assert runner.main(["freeze", "--source-root", str(tmp_path), "--freeze", str(tmp_path / "freeze.json")]) == 0
    assert selected == [(c.P.DEFAULT_POLICY, None)]
    with pytest.raises(SystemExit):
        runner.main(["freeze", "--source-root", str(tmp_path), "--freeze", str(tmp_path / "other.json"),
                     "--runtime-policy", "supplied-digest"])
