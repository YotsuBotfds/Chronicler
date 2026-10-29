"""Tiny stdlib/surrogate boundary fixtures; no transfer, subprocess or World."""
import ast
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import stat
import tomllib
from types import SimpleNamespace as NS
import urllib.error
import urllib.request
import zipfile

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docs/experiments/research-practice-original-audit-workflow.yml"
WORKFLOW_BODY_SHA = "565f11e8e113faeb70999ec713cdc8a287b4149daa376b871940415408b132cf"


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return tuple(importlib.import_module(name) for name in ("research_practice_original_audit",
        "audit_research_practice_original", "research_practice_contract"))


def archive(items):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as z:
        for name, value in items:
            z.writestr(name, value)
    return zipfile.ZipFile(io.BytesIO(out.getvalue()))


@pytest.mark.parametrize("name", ["", "/absolute", "../escape", "x/../z", "x/./z", "x//z", "x/", "x\\z", "x\0z", "//x"])
def test_path_aliases_refused(modules, name):
    A, _, _ = modules
    with pytest.raises(A.Refused): A.relative(name)


@pytest.mark.parametrize("fault", ["link", "special", "encrypted", "compression", "oversize", "negative", "duplicate", "prefix", "count", "total"])
def test_central_rejects_before_copy(modules, fault):
    A, _, _ = modules
    def info(name="a", **kw):
        return NS(filename=name, external_attr=stat.S_IFREG << 16, flag_bits=0, compress_type=0,
                  file_size=1, is_dir=lambda: False, **kw)
    rows = [info()]
    if fault == "link": rows[0].external_attr = stat.S_IFLNK << 16
    elif fault == "special": rows[0].external_attr = stat.S_IFIFO << 16
    elif fault == "encrypted": rows[0].flag_bits = 1
    elif fault == "compression": rows[0].compress_type = 99
    elif fault == "oversize": rows[0].file_size = A.MAX_MEMBER + 1
    elif fault == "negative": rows[0].file_size = -1
    elif fault == "duplicate": rows.append(info())
    elif fault == "prefix": rows.append(info("a/b"))
    with pytest.raises(A.Refused):
        A.central(NS(infolist=lambda: rows), count=2 if fault == "count" else None,
                  expanded=2 if fault == "total" else None)


def test_all_member_crc_hash_and_length_not_only_index(modules):
    A, _, _ = modules
    with archive([("a", b"one"), ("b", b"two")]) as z:
        rows = A.central(z, count=2, expanded=6)
        assert A.member(z, rows["a"], A.pin(b"one")) == b"one"
        with pytest.raises(A.Refused): A.member(z, rows["b"], A.pin(b"bad"))
        with pytest.raises(A.Refused): A.member(z, rows["a"], A.pin(b"long"))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z: z.writestr("a", b"abc")
    raw = bytearray(out.getvalue()); raw[31] ^= 1
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        with pytest.raises(zipfile.BadZipFile): A.member(z, z.getinfo("a"), A.pin(b"abc"))


def test_map_is_new_fixed_policy_and_encoding_not_old_globals(modules):
    A, _, C = modules
    reg = json.loads((ROOT / "scripts/research_practice_original_registration.json").read_bytes())
    c = reg["expected_archive_closure"]
    assert (A.MAX_ENTRIES, A.MAX_EXPANSION, A.MAX_MEMBER) == (5000, 512 * 1024**2, 64 * 1024**2)
    assert (c["expected_file_members"], c["expected_expanded_bytes"]) == (2455, 502390864)
    assert c["expected_member_map_sha256"] == "8f2a0923119ea08ef6136e0e9175aeb6dc7d1fe382146de0a1d768263b85c47c"
    value = {"z": {"sha256": "a", "bytes": 0}, "a": "é"}
    assert A.canonical(value) == b'{"a":"\\u00e9","z":{"bytes":0,"sha256":"a"}}'
    assert A.canonical(value) != C.encoded(value)
    assert all(v is None for v in reg["pending_actual_facts"].values())


def test_missing_pinned_member_cannot_build_a_partial_map(modules):
    A, _, _ = modules
    reg = json.loads((ROOT / "scripts/research_practice_original_registration.json").read_bytes())
    with archive([("unrelated", b"x")]) as z:
        with pytest.raises(KeyError): A.expected_map(z, A.central(z), reg)


def test_closed_map_requires_complete_set_and_registered_hash(modules):
    A, _, _ = modules
    pins = {"a": A.pin(b"x"), "b": A.pin(b"yz")}
    rows = {n: NS(file_size=p["bytes"]) for n, p in pins.items()}
    closure = dict(expected_file_members=2, expected_expanded_bytes=3,
                   expected_member_map_sha256=hashlib.sha256(A.canonical(pins)).hexdigest())
    assert A.close_map(rows, pins, closure) is pins
    changed = deepcopy(pins); changed["a"]["sha256"] = "0" * 64
    with pytest.raises(A.Refused): A.close_map(rows, changed, closure)
    with pytest.raises(A.Refused): A.close_map({"a": rows["a"]}, pins, closure)


def test_exclusive_copy_readonly_and_cleanup_preserves_unowned(modules, tmp_path):
    A, _, _ = modules
    outside = tmp_path / "preserve"; outside.write_bytes(b"keep")
    lease = A.lease_targets(tmp_path)
    with archive([("practice-study-evidence/a/b", b"payload")]) as z:
        A.copy_member(z, z.getinfo("practice-study-evidence/a/b"), A.pin(b"payload"), tmp_path, lease, lambda: None)
    path = tmp_path / "practice-study-evidence/a/b"
    assert path.read_bytes() == b"payload" and stat.S_IMODE(path.stat().st_mode) == 0o444
    A.cleanup_targets(tmp_path, lease)
    assert list(tmp_path.iterdir()) == [outside] and outside.read_bytes() == b"keep"


def test_preexisting_target_never_reused_or_deleted(modules, tmp_path):
    A, _, _ = modules
    target = tmp_path / "practice-study-evidence"; target.mkdir(); (target / "old").write_bytes(b"x")
    with pytest.raises(A.Refused): A.lease_targets(tmp_path)
    assert (target / "old").read_bytes() == b"x"


def test_changed_root_or_alias_refuses_cleanup(modules, tmp_path):
    A, _, _ = modules
    lease = A.lease_targets(tmp_path)
    root = tmp_path / "practice-study-evidence"
    root.rename(tmp_path / "old-root"); root.mkdir()
    with pytest.raises(A.Refused): A.owned_root(tmp_path, root.name, lease)
    assert root.exists() and (tmp_path / "old-root").exists()


def test_symlink_parent_cannot_escape_copy(modules, tmp_path):
    A, _, _ = modules
    lease = A.lease_targets(tmp_path)
    outside = tmp_path / "outside"; outside.mkdir()
    (tmp_path / "practice-study-evidence/link").symlink_to(outside, target_is_directory=True)
    with archive([("practice-study-evidence/link/no", b"x")]) as z:
        with pytest.raises(OSError):
            A.copy_member(z, z.getinfo("practice-study-evidence/link/no"), A.pin(b"x"), tmp_path, lease, lambda: None)
    assert not list(outside.iterdir())
    with pytest.raises(A.Refused): A.cleanup_targets(tmp_path, lease)


def test_hardlink_input_refuses_hash_and_cleanup(modules, tmp_path):
    A, _, _ = modules
    lease = A.lease_targets(tmp_path)
    one = tmp_path / "practice-study-evidence/a"; one.write_bytes(b"x")
    os.link(one, tmp_path / "alias")
    with pytest.raises(A.Refused): A.file_pin(one)
    with pytest.raises(A.Refused): A.cleanup_targets(tmp_path, lease)
    assert one.exists()


@pytest.mark.parametrize("initial,next_bytes,free,ram,accept", [
    (True, 0, 12, 2, True), (False, 0, 3, 1, True),
    (True, 0, 11, 2, False), (True, 0, 12, 1, False),
    (False, 1, 3, 1, False), (False, 0, 2, 1, False), (False, 0, 3, 0, False)])
def test_resource_floors_include_next_copy_and_metadata_reserve(modules, tmp_path, initial, next_bytes, free, ram, accept):
    A, _, _ = modules
    kw = dict(initial=initial, next_bytes=next_bytes,
        disk_usage=lambda path: NS(free=free * A.GIB + A.PUBLICATION_BYTES))
    resolver = lambda: dict(available_bytes=ram * A.GIB, visibility_limits=["fixture"])
    if accept:
        assert A.resources(tmp_path, resolver, **kw)["memory"]["visibility_limits"] == ["fixture"]
    else:
        with pytest.raises(A.AdmissionRefused) as caught: A.resources(tmp_path, resolver, **kw)
        assert caught.value.observation["free_disk_bytes"] == free * A.GIB + A.PUBLICATION_BYTES


@pytest.mark.parametrize("name", ["chronicler", "chronicler.models", "chronicler_agents.x", "pickle", "_pickle", "numpy", "pyarrow", "dill"])
def test_import_guard_refuses_without_importing_any_forbidden_module(modules, name):
    A, _, _ = modules
    guard = A.ImportGuard()
    with pytest.raises(A.Refused): guard.find_spec(name)
    assert guard.attempts == [name]
    assert guard.find_spec("research_practice_trace_reader") is None


def publication(C, A):
    closed = dict(charged_aggregate_cpu_seconds=11.0, measured_to_seal_cpu_seconds=10.0,
                  finalization_cpu_reserve_seconds=1.0, aggregate_wall_seconds=20.0)
    base = dict(controller_charged_upper_bound_cpu_seconds=11.0, controller_measured_to_seal_cpu_seconds=10.0,
                controller_finalization_cpu_reserve_seconds=1.0, aggregate_wall_seconds=20.0, within_registered_limits=True)
    def annotation(cpu, wall):
        return dict(reader_cpu_seconds=cpu, controller_charge_plus_reader_measured_cpu_upper_bound_seconds=11.0 + cpu,
                    total_cpu_accounting_scope=A.SCOPE, controller_to_readout_wall_seconds=wall)
    rebuilt = dict(z=[1, 2], signed=-0.0, budgets=base, tail="retained")
    original = deepcopy(rebuilt); original["publication_status"] = "provisional_until_matching_completion_seal"
    original["budgets"].update(annotation(1.0, 21.0))
    def receipt(cpu, wall):
        row = {k: v for k, v in base.items() if k not in ("aggregate_wall_seconds", "within_registered_limits")}
        row.update(annotation(cpu, wall))
        return dict(budget_observation=row)
    return rebuilt, C.loads(C.encoded(original)), closed, receipt(2.0, 22.0), receipt(3.0, 23.0)


def test_exact_original_writer_roundtrip_preserves_insertion_order(modules):
    A, _, C = modules
    rebuilt, original, closed, receipt, completion = publication(C, A)
    annotations = A.historical_annotations(C, original, closed, receipt, completion)
    assert list(C.loads(C.encoded(rebuilt))) == list(rebuilt) != sorted(rebuilt)
    assert A.semantic_replay(C, NS(markdown=lambda r: "same"), rebuilt, original, annotations, b"same")["whole_original_reconstructed"]


@pytest.mark.parametrize("fault", ["value", "type", "list", "sign", "order", "unknown", "status", "annotation_type", "scope", "regression", "bound"])
def test_semantics_and_only_exact_typed_publisher_annotations(modules, fault):
    A, _, C = modules
    rebuilt, original, closed, receipt, completion = publication(C, A)
    if fault == "value": rebuilt["z"][0] = 9
    elif fault == "type": rebuilt["z"][0] = True
    elif fault == "list": rebuilt["z"].reverse()
    elif fault == "sign": rebuilt["signed"] = 0.0
    elif fault == "order": rebuilt = dict(reversed(list(rebuilt.items())))
    elif fault == "unknown": original["budgets"]["other"] = 1.0
    elif fault == "status": original["publication_status"] = True
    elif fault == "annotation_type": original["budgets"]["reader_cpu_seconds"] = 1
    elif fault == "scope": receipt["budget_observation"]["total_cpu_accounting_scope"] = "measured total"
    elif fault == "regression": completion["budget_observation"]["reader_cpu_seconds"] = 0.0
    elif fault == "bound": completion["budget_observation"]["controller_to_readout_wall_seconds"] = 1801.0
    with pytest.raises((A.Refused, C.ContractError)):
        annotations = A.historical_annotations(C, original, closed, receipt, completion)
        A.semantic_replay(C, NS(markdown=lambda r: "same"), rebuilt, original, annotations, b"same")


def metadata(A, role):
    p = A.INPUTS[role]
    return dict(run=dict(id=p["run"], run_attempt=1, head_sha=p["source"], head_branch=p["branch"], event=p["event"],
        path=p["workflow"], status="completed", conclusion="success", repository=dict(id=A.REPO_ID, full_name=A.REPO)),
        job=dict(id=p["job"], run_id=p["run"], run_attempt=1, head_sha=p["source"], status="completed", conclusion="success"),
        artifact=dict(id=p["id"], name=p["name"], size_in_bytes=p["bytes"], digest="sha256:" + p["sha256"], expired=False,
            expires_at=p["expiry"], workflow_run=dict(id=p["run"], head_sha=p["source"], repository_id=A.REPO_ID, head_repository_id=A.REPO_ID)))


@pytest.mark.parametrize("role", ["raw", "wheel"])
def test_exact_completed_producer_and_distinct_expiries(modules, role):
    A, _, _ = modules
    value = metadata(A, role)
    assert A.metadata_contract(role, value, datetime(2026, 10, 29, tzinfo=timezone.utc)) == A.INPUTS[role]
    with pytest.raises(A.Refused): A.metadata_contract(role, value, datetime(2026, 12, 1, tzinfo=timezone.utc))
    value["run"]["run_attempt"] = True
    with pytest.raises(A.Refused): A.metadata_contract(role, value)


def test_real_urllib_redirect_recomputes_host_and_drops_all_origin_headers(modules):
    A, _, _ = modules
    endpoint = "https://api.github.com/repos/" + A.REPO + "/actions/artifacts/12898552635/zip"
    old = urllib.request.Request(endpoint, headers={"Authorization": "Bearer secret", "Accept": "github", "X-GitHub-Api-Version": "x"})
    handler = urllib.request.HTTPHandler()
    handler.add_parent(NS(addheaders=[]))
    handler.do_request_(old)
    assert old.get_header("Host") == "api.github.com"
    new = A.FixedRedirect(endpoint, []).redirect_request(old, None, 302, "", {}, "https://unit.blob.core.windows.net/x?signed=secret")
    handler.do_request_(new)
    assert new.get_header("Host") == "unit.blob.core.windows.net"
    assert all(new.get_header(k) is None for k in ("Authorization", "Accept", "X-github-api-version"))


def test_denied_response_body_url_token_and_headers_never_escape(modules):
    A, _, _ = modules
    class Denied(urllib.error.HTTPError):
        def read(self, *a): raise AssertionError("body must not be read")
    error = Denied("https://unit.blob.core.windows.net/x?secret=token", 403, "secret body", {"secret": "token"}, None)
    fake = NS(open=lambda *a, **kw: (_ for _ in ()).throw(error))
    t = A.Transport("raw", "secret-token", lambda: None, 10**30, opener=fake)
    with pytest.raises(A.TransportFailure) as caught:
        t.request(t.zip_endpoint, "zip_get", 8)
    assert caught.value.facts == dict(stage="azure_redirect", http_status=403, provider_kind="azure_blob")
    assert "secret" not in str(caught.value) and "token" not in str(caught.value)
    with pytest.raises(A.Refused): t.request("https://alternate.invalid", "zip_get", 8)


@pytest.mark.parametrize("fault", ["result_write", "hash", "completion_write", "completion_rename"])
def test_publication_expiry_preserves_negative_and_no_positive_seal(modules, tmp_path, monkeypatch, fault):
    A, E, _ = modules
    monkeypatch.setattr(A, "unexpired_inputs", lambda: None)  # Wall faults use no real UTC clock.
    state = {"expired": False}
    original_write, original_pin, original_replace = E.write, A.file_pin, E.os.replace
    def guard():
        if state["expired"]: raise A.Refused("expired")
    def write(path, value, **kwargs):
        original_write(path, value, **kwargs)
        if (fault == "result_write" and path.name == "result.json") or (fault == "completion_write" and path.name == "completion.json"):
            state["expired"] = True
    def file_pin(path, check):
        if fault == "hash": state["expired"] = True
        return original_pin(path, check)
    def replace(source, target):
        original_replace(source, target)
        if fault == "completion_rename" and Path(target).name == "completion.json": state["expired"] = True
    monkeypatch.setattr(E, "write", write); monkeypatch.setattr(A, "file_pin", file_pin); monkeypatch.setattr(E.os, "replace", replace)
    with pytest.raises(A.Refused): E.publish(tmp_path, dict(qualified=True), guard, lambda: dict(wall=1.0))
    assert not (tmp_path / "completion.json").exists() and not (tmp_path / "result.json").exists()
    assert (tmp_path / "incomplete-result.json").exists()


def test_original_sources_authenticate_and_entry_clock_precedes_adapter(modules):
    A, E, _ = modules
    reg = json.loads((ROOT / "scripts/research_practice_original_registration.json").read_bytes())
    for name, row in reg["source_pins"].items():
        raw = (ROOT / name).read_bytes()
        assert A.pin(raw) == {k: row[k] for k in ("bytes", "sha256")}
    tree = ast.parse((ROOT / "scripts/audit_research_practice_original.py").read_bytes())
    entry = next(i for i, n in enumerate(tree.body) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "ENTRY_MONOTONIC" for t in n.targets))
    imports = [i for i, n in enumerate(tree.body) if isinstance(n, ast.Import) and any(x.name == "research_practice_original_audit" for x in n.names)]
    assert entry < imports[0]
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert not any(isinstance(n.func.value, ast.Name) and n.func.value.id == "D" and n.func.attr in ("main", "publish_readout") for n in calls)
    assert not any(n.func.attr in ("extractall", "loads") and isinstance(n.func.value, ast.Name) and n.func.value.id in ("pickle", "archive") for n in calls)


def parsed_workflow(raw):
    value = yaml.safe_load(raw)
    if True in value: value["on"] = value.pop(True)
    return value


def workflow_contract(A, value):
    value = deepcopy(value)
    assert value["on"] == {"push": {"branches": [A.BRANCH], "paths": [A.WORKFLOW]}}
    job = value["jobs"]["original-audit"]
    active = "$" + "{{ github.event_name == 'push' && github.ref == 'refs/heads/" + A.BRANCH + "' && github.run_attempt == 1 }}"
    assert (value.pop("name"), job.pop("if")) in (
        ("Prepared fresh practice original-byte audit", active.replace("{{ ", "{{ false && ", 1)),
        ("Fresh practice original-byte audit", active))
    assert hashlib.sha256(A.canonical(value)).hexdigest() == WORKFLOW_BODY_SHA


def test_dormant_and_only_exact_active_copy_contract(modules):
    A, _, _ = modules
    original = parsed_workflow(TEMPLATE.read_bytes())
    workflow_contract(A, original)
    active = deepcopy(original); active["name"] = "Fresh practice original-byte audit"
    active["jobs"]["original-audit"]["if"] = active["jobs"]["original-audit"]["if"].replace("false && ", "", 1)
    workflow_contract(A, active)
    path = ROOT / A.WORKFLOW
    if path.exists(): assert parsed_workflow(path.read_bytes()) == active


@pytest.mark.parametrize("fault", ["branch", "path", "commands", "raw_upload", "step_outcome_binding", "pure_step_id"])
def test_workflow_offpolicy_changes_fail_closed(modules, fault):
    A, _, _ = modules
    value = parsed_workflow(TEMPLATE.read_bytes())
    if fault == "branch": value["on"]["push"]["branches"] = ["main"]
    elif fault == "path": value["on"]["push"]["paths"] = ["**"]
    elif fault == "commands": value["jobs"]["original-audit"]["steps"][-2]["run"] += "\necho retry"
    elif fault == "raw_upload": value["jobs"]["original-audit"]["steps"][-1]["with"]["path"] += "\n${{ runner.temp }}/practice-study-evidence"
    elif fault == "step_outcome_binding": value["jobs"]["original-audit"]["steps"][-2]["env"]["PRACTICE_AUDIT_PURE_OUTCOME"] = "success"
    else: value["jobs"]["original-audit"]["steps"][-3]["id"] = "other_step"
    with pytest.raises(AssertionError): workflow_contract(A, value)


def dependency_workflow_contract(value):
    steps = value["jobs"]["original-audit"]["steps"]
    base = next(s for s in steps if s.get("name") == "Install fixed base audit prerequisites and pinned lock installer")
    prepare = next(s for s in steps if s.get("name") == "Prepare exclusive locked dependency environment only for guarded tests")
    pure = next(s for s in steps if s.get("id") == "pure_contracts")
    audit = next(s for s in steps if s.get("name") == "Audit only the fixed original bytes under a separate new clock")
    assert steps.index(base) < steps.index(prepare) < steps.index(pure) < steps.index(audit)
    assert "python -m pip install --only-binary=:all: pytest==9.1.1 PyYAML==6.0.3 uv==0.13.6" in base["run"]
    assert prepare["working-directory"] == "audit-control" and prepare["env"] == {"UV_PYTHON_DOWNLOADS": "never"}
    run = prepare["run"]
    assert 'AUDIT_BASE_PYTHON="$(command -v python)"' in run
    assert 'test "$AUDIT_BASE_PYTHON" = "$pythonLocation/bin/python"' in run
    assert 'test ! -e .venv' in run and 'test ! -L .venv' in run
    assert 'UV_PROJECT_ENVIRONMENT="$PWD/.venv" "$AUDIT_BASE_PYTHON" -m uv sync' in run
    assert '--frozen --no-dev --no-install-project --no-build --python "$AUDIT_BASE_PYTHON"' in run
    assert '"$AUDIT_BASE_PYTHON" -m uv pip install --python "$PWD/.venv/bin/python"' in run
    assert '--no-build pytest==9.1.1 PyYAML==6.0.3' in run
    assert '"$GITHUB_WORKSPACE/audit-control/.venv/bin/python" -B -m pytest' in pure["run"]
    assert '-p python_oracle_guard' in pure["run"]
    assert 'python -B audit-control/scripts/audit_research_practice_original.py audit' in audit["run"]
    assert '.venv' not in audit["run"] and audit.get("working-directory") is None
    commands = "\n".join(s.get("run", "") for s in steps)
    assert not any(v in commands for v in ('GITHUB_PATH', 'source .venv', 'activate', 'uv run', 'maturin', 'chronicler_agents', '--system'))


def test_locked_core_graph_and_original_guard_are_not_replaced():
    for name, sha in {
        "uv.lock": "986547c01fd1dcd9bf598404124fde4ddc1e3d67db9a1d595a5304f18dacee10",
        "pyproject.toml": "d14f5588112927a0d8d889c30f04af90e81bc2cf4096b9ed91d8a51d83a2ac32",
        "scripts/testing/python_oracle_guard.py": "7e066c7474d3254dde8f0e6c2cba3f90785728a5895d723e8952e7be91d439e1",
    }.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha
    packages = {p["name"]: p for p in tomllib.loads((ROOT / "uv.lock").read_text())["package"]}
    assert {p["name"] for p in packages["chronicler"]["dependencies"]} == {
        "arro3-core", "numpy", "openai", "pyarrow", "pydantic", "pyyaml", "scipy", "websockets"}
    assert packages["chronicler"]["source"] == {"editable": "."}
    assert packages["pytest"]["version"] == "9.0.2"  # Deliberately excluded; selected pure version is9.1.1.
    assert packages["pyyaml"]["version"] == "6.0.3"
    assert all("chronicler-agents" not in name and "chronicler_agents" not in name for name in packages)


def test_pure_dependency_environment_is_separate_from_base_audit():
    dependency_workflow_contract(parsed_workflow(TEMPLATE.read_bytes()))


@pytest.mark.parametrize("fault", ["unfrozen", "project_install", "source_build", "reuse", "cwd", "base_switched", "guard"])
def test_dependency_environment_misrouting_is_refused(fault):
    value = parsed_workflow(TEMPLATE.read_bytes())
    steps = value["jobs"]["original-audit"]["steps"]
    prepare = next(s for s in steps if s.get("working-directory") == "audit-control")
    pure = next(s for s in steps if s.get("id") == "pure_contracts")
    audit = steps[-2]
    if fault == "unfrozen": prepare["run"] = prepare["run"].replace("--frozen", "")
    elif fault == "project_install": prepare["run"] = prepare["run"].replace("--no-install-project", "")
    elif fault == "source_build": prepare["run"] = prepare["run"].replace("--no-build", "")
    elif fault == "reuse": prepare["run"] = prepare["run"].replace("test ! -e .venv", "test -d .venv")
    elif fault == "cwd": prepare["working-directory"] = "control"
    elif fault == "base_switched": audit["run"] = audit["run"].replace("python -B", '.venv/bin/python -B')
    else: pure["run"] = pure["run"].replace("-p python_oracle_guard", "-p weaker_guard")
    with pytest.raises(AssertionError): dependency_workflow_contract(value)


def contract_fixture(E, base):
    root = base / "practice-original-contracts"; root.mkdir()
    guard = dict(state="PASS", test_reports=dict(passed=E.EXPECTED_PURE_CASES, failed=0, skipped=0),
        native_modules_loaded=[], native_import_attempts_blocked=[], blocked_io_attempts=[],
        python_oracle_factory_calls=dict(ecology=0, politics=0), pytest_exitstatus=0,
        guard_active_at_finish=True, runtime_factories_replaced_before_collection=True)
    (root / "guard.json").write_text(json.dumps(guard))
    (root / "junit.xml").write_text("<testsuites><testsuite>" + "<testcase/>" * E.EXPECTED_PURE_CASES + "</testsuite></testsuites>")
    return root, guard


def test_guard_and_junit_are_separate_actual_preflight_publication(modules, tmp_path):
    A, E, _ = modules
    root, guard = contract_fixture(E, tmp_path)
    assert len(E.preflight_contracts(tmp_path, step_outcome="success")) == 2
    guard["python_oracle_factory_calls"] = {}
    (root / "guard.json").write_text(json.dumps(guard))
    with pytest.raises(A.Refused): E.preflight_contracts(tmp_path, step_outcome="success")


def test_changed_or_skipped_preflight_is_not_full_coverage(modules, tmp_path):
    A, E, _ = modules
    root, guard = contract_fixture(E, tmp_path)
    (root / "junit.xml").write_text("<testsuites><testsuite><testcase><skipped/></testcase></testsuite></testsuites>")
    with pytest.raises(A.Refused): E.preflight_contracts(tmp_path, step_outcome="success")


def test_publication_cap_includes_external_guard_and_junit(modules, tmp_path):
    A, E, _ = modules
    contract_fixture(E, tmp_path)
    output = tmp_path / "publication"; output.mkdir()
    with (output / "near-cap.json").open("wb") as stream:
        stream.truncate(A.PUBLICATION_BYTES - E.TERMINAL_BYTES)
    with pytest.raises(A.Refused):
        E.copy_contracts(tmp_path, output)
    assert not (output / "contracts-guard.json").exists()
    assert not (output / "completion.json").exists()


def test_cumulative_write_refuses_before_allocation_but_keeps_terminal_room(modules, tmp_path):
    A, E, _ = modules
    missing = sum(maximum for _, maximum in E.CONTRACT_COPIES.values())
    with (tmp_path / "previous.json").open("wb") as stream:
        stream.truncate(A.PUBLICATION_BYTES - E.TERMINAL_BYTES - missing - 2)
    with pytest.raises(A.Refused, match="cumulative_publication_bound"):
        E.write_raw(tmp_path / "next.json", b"xxx", publication=True)
    assert not (tmp_path / "next.json").exists() and not (tmp_path / "pending-next.json").exists()
    E.write(tmp_path / "terminal-negative.json", dict(qualified=False), publication=True, terminal=True)
    assert sum(p.stat().st_size for p in tmp_path.iterdir()) <= A.PUBLICATION_BYTES


def test_oversized_preflight_is_not_copied_or_uploaded(modules, tmp_path):
    A, E, _ = modules
    root, _ = contract_fixture(E, tmp_path)
    with (root / "junit.xml").open("wb") as stream: stream.truncate(512 * 1024 + 1)
    output = tmp_path / "publication"; output.mkdir()
    with pytest.raises(A.Refused): E.copy_contracts(tmp_path, output)
    assert (output / "contracts-guard.json").read_bytes() == (root / "guard.json").read_bytes()
    assert not (output / "contracts-junit.xml").exists() and (root / "junit.xml").exists()


def test_terminal_records_cannot_spend_more_than_reserved_space(modules, tmp_path):
    A, E, _ = modules
    with pytest.raises(A.Refused, match="terminal_record_bound"):
        E.write_raw(tmp_path / "negative.json", b"x" * (E.TERMINAL_BYTES // E.TERMINAL_FILES + 1),
                    publication=True, terminal=True)
    assert not list(tmp_path.iterdir())


def test_failed_preflight_keeps_bytes_and_never_reaches_worker_or_transport(modules, tmp_path, monkeypatch):
    A, E, _ = modules
    root, guard = contract_fixture(E, tmp_path)
    guard["test_reports"].update(passed=E.EXPECTED_PURE_CASES - 1, failed=1)
    (root / "guard.json").write_text(json.dumps(guard))
    monkeypatch.setattr(E, "WORK", tmp_path / "audit")
    monkeypatch.setattr(E, "OWNED_WORK", None)
    monkeypatch.setenv("PRACTICE_AUDIT_PURE_OUTCOME", "success")
    monkeypatch.setattr(A, "TEMP", tmp_path)
    monkeypatch.setattr(E, "registration", lambda env: dict(GITHUB_SHA="a" * 40))
    monkeypatch.setattr(E, "selected_helpers", lambda *args: (None, NS(memory_admission=None), None, None, None, None))
    monkeypatch.setattr(A, "resources", lambda *args, **kwargs: dict(fixture_admission=True))
    def forbidden(*args, **kwargs): raise AssertionError("worker/transport must not start")
    monkeypatch.setattr(E.subprocess, "Popen", forbidden); monkeypatch.setattr(A, "Transport", forbidden)
    with pytest.raises(A.Refused, match="pure_preflight_guard"): E.audit()
    output = tmp_path / "audit/publication"
    assert (output / "contracts-guard.json").read_bytes() == (root / "guard.json").read_bytes()
    assert (output / "contracts-junit.xml").read_bytes() == (root / "junit.xml").read_bytes()
    assert not (tmp_path / "audit/raw.zip").exists()


def test_registration_uses_closed_workflow_identity_and_actual_runtime_facts(modules, monkeypatch):
    A, E, _ = modules
    env = dict(GITHUB_ACTIONS="true", GITHUB_REPOSITORY=A.REPO, GITHUB_EVENT_NAME="push",
        GITHUB_REF="refs/heads/" + A.BRANCH, GITHUB_WORKFLOW_REF=A.REPO + "/" + A.WORKFLOW + "@refs/heads/" + A.BRANCH,
        GITHUB_JOB="original-audit", GITHUB_RUN_ATTEMPT="1", GITHUB_SHA="a" * 40, GITHUB_RUN_ID="123",
        GITHUB_WORKSPACE=str(A.WORKSPACE), RUNNER_TEMP=str(A.TEMP), PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1", **E.CAPS)
    monkeypatch.setattr(E, "ROOT", A.WORKSPACE / "audit-control")
    monkeypatch.setattr(E.platform, "python_version", lambda: "3.13.17")
    monkeypatch.setattr(E.platform, "python_implementation", lambda: "CPython")
    monkeypatch.setattr(E.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(E.os, "sched_getaffinity", lambda pid: {1})
    monkeypatch.setattr(importlib.metadata, "version", lambda name: {"pytest": "9.1.1", "PyYAML": "6.0.3"}[name])
    assert E.registration(env)["GITHUB_SHA"] == "a" * 40
    for key, value in (("GITHUB_REF", "refs/heads/main"), ("GITHUB_RUN_ATTEMPT", "2"),
                       ("GITHUB_EVENT_NAME", "workflow_dispatch"), ("RUNNER_TEMP", "/other")):
        changed = dict(env); changed[key] = value
        with pytest.raises(A.Refused): E.registration(changed)
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "wrong")
    with pytest.raises(A.Refused, match="pure_dependency_versions"): E.registration(env)


@pytest.mark.parametrize("fault", ["post_restore_expiry", "restore_error"])
def test_outer_timer_teardown_cannot_leave_positive_seal(modules, tmp_path, monkeypatch, fault):
    A, E, _ = modules
    work = tmp_path / "audit"; work.mkdir(); output = work / "publication"; output.mkdir()
    (output / "result.json").write_bytes(b"new")
    (output / "completion.json").write_bytes(b"new seal")
    (output / "incomplete-result.json").write_bytes(b"first failure")
    row, clock, previous = work.stat(), {"now": 1.0}, object()
    def handler(signum, value):
        if value is previous:
            if fault == "restore_error": raise OSError("fixture restoration failure")
            clock["now"] = 600.1
    fake = NS(SIGALRM=14, ITIMER_REAL=0, getsignal=lambda sig: previous,
              getitimer=lambda timer: (0.0, 0.0), signal=handler, setitimer=lambda *args: None)
    monkeypatch.setattr(E, "signal", fake); monkeypatch.setattr(E, "ENTRY_MONOTONIC", 0.0)
    monkeypatch.setattr(E, "WORK", work); monkeypatch.setattr(E, "OWNED_WORK", (row.st_dev, row.st_ino))
    monkeypatch.setattr(E.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(E, "audit", lambda imports: 0)
    monkeypatch.setattr(A, "import_guard", lambda: nullcontext((NS(attempts=[]), [])))
    assert E.audit_with_timer() == 1
    assert not (output / "result.json").exists() and not (output / "completion.json").exists()
    assert (output / "incomplete-result.json").read_bytes() == b"first failure"
    assert (output / "incomplete-1-result.json").read_bytes() == b"new"
    assert json.loads((output / "terminal-negative.json").read_bytes())["qualified"] is False


def fake_audit_owner(A, E, tmp_path, monkeypatch, outcome, *, admission_failure=False):
    """No real handlers, admission, credentials, subprocesses or transport."""
    monkeypatch.setattr(E, "WORK", tmp_path / "audit")
    monkeypatch.setattr(E, "OWNED_WORK", None)
    monkeypatch.setattr(A, "TEMP", tmp_path)
    monkeypatch.setattr(E, "registration", lambda env: dict(GITHUB_SHA="a" * 40, GITHUB_RUN_ID="123",
        GITHUB_RUN_ATTEMPT="1", GITHUB_JOB="original-audit"))
    if outcome is None:
        monkeypatch.delenv("PRACTICE_AUDIT_PURE_OUTCOME", raising=False)
    else:
        monkeypatch.setenv("PRACTICE_AUDIT_PURE_OUTCOME", outcome)
    fake = NS(SIGALRM=14, ITIMER_REAL=0, getsignal=lambda sig: None,
        getitimer=lambda timer: (0.0, 0.0), signal=lambda *args: None, setitimer=lambda *args: None)
    monkeypatch.setattr(E, "signal", fake)
    monkeypatch.setattr(A, "import_guard", lambda: nullcontext((NS(attempts=[]), [])))
    calls = dict(Popen=0, Transport=0, helpers=0, resources=0)
    def forbidden(name):
        def call(*args, **kwargs):
            calls[name] += 1
            raise AssertionError(name + " must not start")
        return call
    monkeypatch.setattr(E.subprocess, "Popen", forbidden("Popen"))
    monkeypatch.setattr(A, "Transport", forbidden("Transport"))
    if admission_failure:
        def helpers(*args):
            calls["helpers"] += 1
            return None, NS(memory_admission=None), None, None, None, None
        def resources(*args, **kwargs):
            calls["resources"] += 1
            raise A.AdmissionRefused("ram_floor", dict(fixture_admission_refused=True))
        monkeypatch.setattr(E, "selected_helpers", helpers)
        monkeypatch.setattr(A, "resources", resources)
        monkeypatch.setattr(A, "unexpired_inputs", lambda: None)
    else:
        monkeypatch.setattr(E, "selected_helpers", forbidden("helpers"))
        monkeypatch.setattr(A, "resources", forbidden("resources"))
    return calls


@pytest.mark.parametrize("fault", ["exit2", "exit3", "exit_missing", "exit_false", "exit_true",
    "active_false", "active_missing", "active_int", "factories_false", "factories_missing", "factories_int",
    "outcome_failed", "outcome_cancelled", "outcome_missing", "outcome_skipped", "timeout_after_clean_reports"])
def test_actual_preflight_authority_failure_is_bounded_negative_without_launch(modules, tmp_path, monkeypatch, fault):
    A, E, _ = modules
    root, guard = contract_fixture(E, tmp_path)
    outcome = "success"
    if fault.startswith("exit"):
        value = {"exit2": 2, "exit3": 3, "exit_false": False, "exit_true": True}.get(fault)
        if fault == "exit_missing": del guard["pytest_exitstatus"]
        else: guard["pytest_exitstatus"] = value
    elif fault.startswith("active"):
        if fault == "active_missing": del guard["guard_active_at_finish"]
        else: guard["guard_active_at_finish"] = False if fault == "active_false" else 1
    elif fault.startswith("factories"):
        if fault == "factories_missing": del guard["runtime_factories_replaced_before_collection"]
        else: guard["runtime_factories_replaced_before_collection"] = False if fault == "factories_false" else 1
    else:
        outcome = {"outcome_failed": "failure", "outcome_cancelled": "cancelled", "outcome_missing": None,
                   "outcome_skipped": "skipped", "timeout_after_clean_reports": "failure"}[fault]
        # Includes the important witness: published int0 and clean JUnit can
        # precede a process-shutdown timeout; only actual Actions outcome denies it.
        assert guard["pytest_exitstatus"] == 0
    (root / "guard.json").write_text(json.dumps(guard))
    calls = fake_audit_owner(A, E, tmp_path, monkeypatch, outcome)
    assert E.audit_with_timer() == 1
    output = tmp_path / "audit/publication"
    negative = json.loads((output / "terminal-negative.json").read_bytes())
    assert negative["qualified"] is False
    assert negative["error_code"] == ("pure_step_outcome" if outcome != "success" else "pure_preflight_guard")
    assert (output / "contracts-guard.json").read_bytes() == (root / "guard.json").read_bytes()
    assert (output / "contracts-junit.xml").read_bytes() == (root / "junit.xml").read_bytes()
    assert json.loads((output / "entry-pending.json").read_bytes())["qualified"] is False
    assert calls == dict(Popen=0, Transport=0, helpers=0, resources=0)
    assert not (output / "completion.json").exists() and not (output / "admission.json").exists()
    assert sum(p.stat().st_size for p in output.iterdir()) <= A.PUBLICATION_BYTES


def test_pending_negative_precedes_required_admission_without_granting_authority(modules, tmp_path, monkeypatch):
    A, E, _ = modules
    contract_fixture(E, tmp_path)
    calls = fake_audit_owner(A, E, tmp_path, monkeypatch, "success", admission_failure=True)
    assert E.audit_with_timer() == 1
    output = tmp_path / "audit/publication"
    assert json.loads((output / "entry-pending.json").read_bytes())["qualified"] is False
    assert json.loads((output / "terminal-negative.json").read_bytes())["error_code"] == "ram_floor"
    assert calls == dict(Popen=0, Transport=0, helpers=1, resources=1)
    assert not (output / "admission.json").exists() and not (output / "completion.json").exists()


@pytest.mark.parametrize("role", ["raw", "wheel"])
def test_both_fixed_inputs_must_be_strictly_unexpired(modules, role):
    A, _, _ = modules
    fresh = datetime(2026, 11, 1, tzinfo=timezone.utc)
    assert A.unexpired_inputs(fresh)["registered_expiries"] == {k: v["expiry"] for k, v in A.INPUTS.items()}
    boundary = datetime.fromisoformat(A.INPUTS[role]["expiry"].replace("Z", "+00:00"))
    with pytest.raises(A.Refused, match="original_" + role + "_expired"):
        A.unexpired_inputs(boundary)


@pytest.mark.parametrize("role", ["raw", "wheel"])
@pytest.mark.parametrize("phase", ["before_seal", "seal_commit", "after_guard"])
def test_input_expiry_during_finalization_invalidates_positive_seal(modules, tmp_path, monkeypatch, role, phase):
    A, E, _ = modules
    state = dict(now=datetime(2026, 11, 1, tzinfo=timezone.utc))
    expired = datetime.fromisoformat(A.INPUTS[role]["expiry"].replace("Z", "+00:00"))
    real_check, real_write, real_replace = A.unexpired_inputs, E.write, E.os.replace
    monkeypatch.setattr(A, "unexpired_inputs", lambda: real_check(state["now"]))
    def write(path, value, **kwargs):
        real_write(path, value, **kwargs)
        if phase == "before_seal" and path.name == "result.json": state["now"] = expired
    def replace(source, target):
        real_replace(source, target)
        if phase == "seal_commit" and Path(target).name == "completion.json": state["now"] = expired
    def guard():
        if phase == "after_guard" and (tmp_path / "completion.json").exists(): state["now"] = expired
    monkeypatch.setattr(E, "write", write); monkeypatch.setattr(E.os, "replace", replace)
    with pytest.raises(A.Refused, match="original_" + role + "_expired"):
        E.publish(tmp_path, dict(qualified=True), guard, lambda: dict(wall=1.0))
    assert not (tmp_path / "completion.json").exists() and not (tmp_path / "result.json").exists()
    assert (tmp_path / "incomplete-result.json").exists()
    E.write(tmp_path / "negative.json", dict(qualified=False), publication=True, terminal=True)
    assert sum(p.stat().st_size for p in tmp_path.iterdir()) <= A.PUBLICATION_BYTES


@pytest.mark.parametrize("role", ["raw", "wheel"])
def test_input_expiry_after_timer_restoration_removes_positive_seal(modules, tmp_path, monkeypatch, role):
    A, E, _ = modules
    work = tmp_path / "audit"; work.mkdir(); output = work / "publication"; output.mkdir()
    (output / "result.json").write_bytes(b"positive")
    (output / "completion.json").write_bytes(b"positive seal")
    row, previous = work.stat(), object()
    state = dict(now=datetime(2026, 11, 1, tzinfo=timezone.utc))
    expired = datetime.fromisoformat(A.INPUTS[role]["expiry"].replace("Z", "+00:00"))
    real_check = A.unexpired_inputs
    monkeypatch.setattr(A, "unexpired_inputs", lambda: real_check(state["now"]))
    def handler(signum, value):
        if value is previous: state["now"] = expired
    fake = NS(SIGALRM=14, ITIMER_REAL=0, getsignal=lambda sig: previous,
        getitimer=lambda timer: (0.0, 0.0), signal=handler, setitimer=lambda *args: None)
    monkeypatch.setattr(E, "signal", fake); monkeypatch.setattr(E, "ENTRY_MONOTONIC", 0.0)
    monkeypatch.setattr(E.time, "monotonic", lambda: 1.0)
    monkeypatch.setattr(E, "WORK", work); monkeypatch.setattr(E, "OWNED_WORK", (row.st_dev, row.st_ino))
    monkeypatch.setattr(E, "audit", lambda imports: 0)
    monkeypatch.setattr(A, "import_guard", lambda: nullcontext((NS(attempts=[]), [])))
    assert E.audit_with_timer() == 1
    assert not (output / "result.json").exists() and not (output / "completion.json").exists()
    assert json.loads((output / "terminal-negative.json").read_bytes())["error_code"] == "original_" + role + "_expired"
