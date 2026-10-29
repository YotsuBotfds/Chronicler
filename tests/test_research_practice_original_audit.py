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
from types import SimpleNamespace as NS
import urllib.error
import urllib.request
import zipfile

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docs/experiments/research-practice-original-audit-workflow.yml"
WORKFLOW_BODY_SHA = "3d14ab309edacc3ed5c342f0e7a8551b7208b7791c54f735b4183558ad5c5209"


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


@pytest.mark.parametrize("fault", ["branch", "path", "commands", "raw_upload"])
def test_workflow_offpolicy_changes_fail_closed(modules, fault):
    A, _, _ = modules
    value = parsed_workflow(TEMPLATE.read_bytes())
    if fault == "branch": value["on"]["push"]["branches"] = ["main"]
    elif fault == "path": value["on"]["push"]["paths"] = ["**"]
    elif fault == "commands": value["jobs"]["original-audit"]["steps"][-2]["run"] += "\necho retry"
    else: value["jobs"]["original-audit"]["steps"][-1]["with"]["path"] += "\n${{ runner.temp }}/practice-study-evidence"
    with pytest.raises(AssertionError): workflow_contract(A, value)


def contract_fixture(E, base):
    root = base / "practice-original-contracts"; root.mkdir()
    guard = dict(state="PASS", test_reports=dict(passed=E.EXPECTED_PURE_CASES, failed=0, skipped=0),
        native_modules_loaded=[], native_import_attempts_blocked=[], blocked_io_attempts=[],
        python_oracle_factory_calls=dict(ecology=0, politics=0))
    (root / "guard.json").write_text(json.dumps(guard))
    (root / "junit.xml").write_text("<testsuites><testsuite>" + "<testcase/>" * E.EXPECTED_PURE_CASES + "</testsuite></testsuites>")
    return root, guard


def test_guard_and_junit_are_separate_actual_preflight_publication(modules, tmp_path):
    A, E, _ = modules
    root, guard = contract_fixture(E, tmp_path)
    assert len(E.preflight_contracts(tmp_path)) == 2
    guard["python_oracle_factory_calls"] = {}
    (root / "guard.json").write_text(json.dumps(guard))
    with pytest.raises(A.Refused): E.preflight_contracts(tmp_path)


def test_changed_or_skipped_preflight_is_not_full_coverage(modules, tmp_path):
    A, E, _ = modules
    root, guard = contract_fixture(E, tmp_path)
    (root / "junit.xml").write_text("<testsuites><testsuite><testcase><skipped/></testcase></testsuite></testsuites>")
    with pytest.raises(A.Refused): E.preflight_contracts(tmp_path)


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
