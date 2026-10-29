"""Only tiny synthetic source/metadata/files. No host/probe/child/World calls."""
from datetime import datetime, timezone
import ast
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import zipfile

import pytest


ROOT = Path(__file__).parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


O = load("passive090_owner_test_metadata", ROOT / "scripts/current090_profile_owner.py")
I = load("passive090_inputs_test_metadata", ROOT / "scripts/current090_profile_inputs.py")
REFERENCE = json.loads((ROOT / "docs/experiments/current090-passive-profile-inputs.json").read_text())


def test_null_source_approval_precedes_any_host_or_source_access(monkeypatch):
    monkeypatch.setattr(O, "EXECUTION_APPROVAL", None)
    assert O.EXECUTION_APPROVAL is None
    monkeypatch.setattr(O, "modules", lambda *a: pytest.fail("source access before approval"))
    monkeypatch.setattr(O, "context", lambda *a: pytest.fail("host access before approval"))
    with pytest.raises(O.Refused, match="approval is null"): O.execute(None)
    with pytest.raises(O.Refused, match="approval is null"): O.main([])
    with pytest.raises(O.Refused, match="approval is null"): O.child(None, None, None, None)


def test_pinned_sources_reference_and_old_cost_are_literal():
    assert O.CORE_SHA == REFERENCE["core_sha256"] == hashlib.sha256((ROOT / "scripts/current090_passive_profile.py").read_bytes()).hexdigest()
    assert O.REFERENCE_SHA == hashlib.sha256((ROOT / "docs/experiments/current090-passive-profile-inputs.json").read_bytes()).hexdigest()
    assert O.TRANSPORT_SHA == hashlib.sha256((ROOT / "scripts/current090_profile_inputs.py").read_bytes()).hexdigest()
    assert REFERENCE["source"] == "0900f3d203cc74102809bb871a1a057ba91a951f"
    assert REFERENCE["controls_source"] == "1421621b4393d08cedb0d3505ae26b96dfa6563c"
    assert REFERENCE["actual_new_schemas"] is REFERENCE["actual_execution_approval"] is None
    assert len(REFERENCE["historical_schema_reference"]) == 3


def valid_context():
    return {"GITHUB_REPOSITORY": O.REPOSITORY, "GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "push",
            "GITHUB_REF": "refs/heads/" + O.ACTIVE_BRANCH,
            "GITHUB_WORKFLOW_REF": O.REPOSITORY + "/" + O.WORKFLOW_PATH + "@refs/heads/" + O.ACTIVE_BRANCH,
            "GITHUB_RUN_ATTEMPT": "1", "GITHUB_JOB": O.JOB_KEY, "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123"}


@pytest.mark.parametrize("key", ["GITHUB_REPOSITORY", "GITHUB_EVENT_NAME", "GITHUB_REF", "GITHUB_WORKFLOW_REF",
                                "GITHUB_RUN_ATTEMPT", "GITHUB_JOB", "GITHUB_SHA", "GITHUB_RUN_ID"])
def test_closed_context_refuses_other_scope(key):
    env = valid_context(); assert O.context(env)["GITHUB_RUN_ATTEMPT"] == "1"
    env[key] = "wrong"
    with pytest.raises(O.Refused): O.context(env)


def test_child_environment_strips_loader_token_and_project_contamination(monkeypatch):
    for key in ("PYTHONPATH", "PYTHONHOME", "LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "GH_TOKEN", "GITHUB_TOKEN"):
        monkeypatch.setenv(key, "must not reach the physics child")
    env = O.child_environment()
    assert all(k not in env for k in ("PYTHONPATH", "PYTHONHOME", "LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "GH_TOKEN", "GITHUB_TOKEN"))
    assert all(env[k] == v for k, v in O.CAPS.items()) and env["UV_LINK_MODE"] == "copy"


@pytest.mark.parametrize("label,expected", [("input-before", True), ("input-after", True),
                                            ("role-0", False), ("bootstrap", False), ("input-other", False)])
def test_input_token_reaches_only_the_two_owned_transport_children(monkeypatch, label, expected):
    monkeypatch.setenv("GH_TOKEN", "synthetic-read-only-token")
    monkeypatch.setenv("GITHUB_TOKEN", "synthetic-other-token")
    env = O.command_environment(label)
    assert ("GH_TOKEN" in env) is expected and "GITHUB_TOKEN" not in env
    if expected: assert env["GH_TOKEN"] == "synthetic-read-only-token"


def test_new_python_argv_honors_hash_environment_without_I_or_E():
    args = O.python_command(Path("/qualified/python"), "-c", "pass")
    assert args == ["/qualified/python", "-P", "-s", "-B", "-X", "cpu_count=1", "-c", "pass"]
    assert "-I" not in args and "-E" not in args


@pytest.mark.parametrize("fault", [None, "hash", "ignore", "isolated", "safe", "site", "logical", "option"])
def test_flags_are_checked_as_actual_interpreter_metadata(monkeypatch, fault):
    flags = SimpleNamespace(safe_path=True, no_user_site=1, ignore_environment=0, isolated=0, hash_randomization=0)
    fake_sys = SimpleNamespace(flags=flags, _xoptions={"cpu_count": "1"})
    fake_os = SimpleNamespace(cpu_count=lambda: 1, environ={"PYTHONHASHSEED": "0"})
    if fault == "hash": flags.hash_randomization = 1
    if fault == "ignore": flags.ignore_environment = 1
    if fault == "isolated": flags.isolated = 1
    if fault == "safe": flags.safe_path = False
    if fault == "site": flags.no_user_site = 0
    if fault == "logical": fake_os.cpu_count = lambda: 96
    if fault == "option": fake_sys._xoptions = {}
    monkeypatch.setattr(O, "sys", fake_sys); monkeypatch.setattr(O, "os", fake_os)
    if fault is None:
        result = O.runtime_flags()
        assert result["isolated"] == 0 and result["hash_randomization"] == 0 and result["cpu_count"] == 1
    else:
        with pytest.raises(O.Refused): O.runtime_flags()


@pytest.mark.parametrize("fault", [None, "dir", "library", "preload", "inherited", "escape"])
def test_loader_is_one_qualified_prefix_not_a_fallback(tmp_path, fault):
    base = tmp_path / "python"; lib = base / "lib"; lib.mkdir(parents=True)
    file = lib / "libpython3.13.so.1.0"; file.write_bytes(b"synthetic runtime-file metadata")
    config = {"LIBDIR": str(lib), "LDLIBRARY": file.name}; env = {}
    if fault == "dir": config["LIBDIR"] = str(tmp_path)
    if fault == "library": config["LDLIBRARY"] = "arbitrary.so"
    if fault == "preload": env["LD_PRELOAD"] = "unexpected.so"
    if fault == "inherited": env["LD_LIBRARY_PATH"] = str(tmp_path / "elsewhere")
    if fault == "escape":
        elsewhere = tmp_path / "outside"; elsewhere.write_bytes(b"outside")
        file.unlink(); file.symlink_to(elsewhere)
    if fault is None:
        result = O.loader_identity(config=config, base_prefix=base, environment=env)
        assert result["child_LD_LIBRARY_PATH"] == str(lib)
        assert result["actual"]["sha256"] == hashlib.sha256(file.read_bytes()).hexdigest()
    else:
        with pytest.raises(O.Refused): O.loader_identity(config=config, base_prefix=base, environment=env)


def test_both_modules_own_a_dedicated_unchanged_110_second_offline_chunk():
    tree = ast.parse((ROOT / "scripts/run_python_oracle_checks.py").read_bytes())
    values = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
              if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
              and node.targets[0].id in ("CHUNKS", "CHUNK_LIMIT_SECONDS")}
    assert values["CHUNK_LIMIT_SECONDS"] == 110
    modules = ["tests/test_current090_passive_profile.py", "tests/test_current090_profile_owner.py"]
    assert values["CHUNKS"]["current090-profile-metadata"] == modules
    flattened = [node for group in values["CHUNKS"].values() for node in group]
    assert all(flattened.count(name) == 1 for name in modules)


@pytest.mark.parametrize("fault", [None, "count", "skips", "guard", "source", "collection", "registry", "hashflag"])
def test_hosted_pure_must_finish_exactly_before_input_admission(fault):
    expected = {"synthetic-source.py": "a" * 64}
    value = {"passed": True, "tests": O.EXPECTED_PREFLIGHT_CASES, "errors": 0, "failures": 0, "skips": 0,
             "pytest_exit": 0, "collection_or_setup_failure": False, "blocked_operations": [],
             "project_native_imports": [], "source_unchanged": True, "before": dict(expected), "after": dict(expected),
             "registry_module_counts": {"tests/test_current090_passive_profile.py": 1,
                                        "tests/test_current090_profile_owner.py": 1},
             "runtime_flags": {"safe_path": True, "no_user_site": 1, "ignore_environment": 0,
                               "isolated": 0, "hash_randomization": 0, "cpu_count": 1}}
    if fault == "count": value["tests"] -= 1
    if fault == "skips": value["skips"] = 1
    if fault == "guard": value["blocked_operations"] = [{"import": "forbidden"}]
    if fault == "source": value["after"] = {"synthetic-source.py": "b" * 64}
    if fault == "collection": value["collection_or_setup_failure"] = True
    if fault == "registry": value["registry_module_counts"]["tests/test_current090_profile_owner.py"] = 0
    if fault == "hashflag": value["runtime_flags"]["hash_randomization"] = 1
    if fault is None: O.verify_preflight(value, expected)
    else:
        with pytest.raises(O.Refused): O.verify_preflight(value, expected)


def test_authenticate_actual_loaded_source_once_and_refuse_tamper_or_alias(tmp_path):
    path = tmp_path / "tiny.py"; path.write_text("VALUE = 7\n")
    hashed = hashlib.sha256(path.read_bytes()).hexdigest()
    name = "qualified_tiny_metadata_source"
    try:
        assert O.load_module(path, name, hashed).VALUE == 7
        with pytest.raises(O.Refused, match="already loaded"): O.load_module(path, name, hashed)
        sys.modules.pop(name)
        path.write_text("VALUE = 8\n")
        with pytest.raises(O.Refused, match="identity"): O.load_module(path, name, hashed)
        alias = tmp_path / "alias.py"; alias.symlink_to(path)
        with pytest.raises(O.Refused): O.load_module(alias, name, hashed)
    finally: sys.modules.pop(name, None)


def test_inventory_descriptor_hashes_and_authorities_have_explicit_scope(tmp_path):
    (tmp_path / "data").mkdir(); (tmp_path / "data/a").write_bytes(b"abc")
    (tmp_path / "result.json").write_text("negative authority")
    seen = []
    value = O.inventory(tmp_path, authority=("result.json",), guard=lambda: seen.append(1))
    assert value == {"files": {"data/a": {"bytes": 3, "sha256": hashlib.sha256(b"abc").hexdigest()}},
                     "file_count": 1, "bytes": 3}
    assert seen
    with pytest.raises(O.Refused, match="exclusion"): O.inventory(tmp_path, authority=("data/a",))


@pytest.mark.parametrize("fault", ["symlink", "hardlink", "bytes", "files", "guard"])
def test_inventory_refuses_unsafe_or_incomplete_retention(tmp_path, fault):
    file = tmp_path / "data"; file.write_bytes(b"abc")
    options = {}
    if fault == "symlink": (tmp_path / "alias").symlink_to(file)
    if fault == "hardlink": os.link(file, tmp_path / "hard")
    if fault == "bytes": options["max_bytes"] = 2
    if fault == "files": options["max_files"] = 0
    if fault == "guard": options["guard"] = lambda: O.require(False, "clock expired")
    with pytest.raises(O.Refused): O.inventory(tmp_path, **options)
    assert file.read_bytes() == b"abc"


def test_metadata_write_replaces_atomically_and_refuses_oversize(tmp_path):
    path = tmp_path / "result.json"
    O.write(path, {"complete": False})
    assert json.loads(path.read_text()) == {"complete": False}
    with pytest.raises(O.Refused, match="cap"): O.write(path, {"large": "x" * 100}, limit=8)
    assert json.loads(path.read_text()) == {"complete": False}
    assert not (tmp_path / "result.json.pending").exists()


def test_module_origin_checks_only_bound_namespace_metadata(tmp_path, monkeypatch):
    source, prefix = tmp_path / "producer", tmp_path / "prefix"
    source.mkdir(); prefix.mkdir()
    module = SimpleNamespace(__file__=str(source / "src/chronicler/main.py"))
    fake = SimpleNamespace(modules={"chronicler.main": module})
    monkeypatch.setattr(O, "sys", fake)
    O.module_origins(source, prefix)
    module.__file__ = str(tmp_path / "other/main.py")
    with pytest.raises(O.Refused, match="origin"): O.module_origins(source, prefix)


@pytest.mark.parametrize("fault", [None, "version_bool", "fingerprint", "descriptor", "missing"])
def test_actual_schema_forms_match_fixed_reference_without_any_class_call(fault):
    raw = {name: [1, "fixed", "synthetic schema " + name] for name in REFERENCE["historical_schema_reference"]}
    expected = {name: {"version": row[0], "fingerprint": row[1], "schema_sha256": hashlib.sha256(row[2].encode()).hexdigest()}
                for name, row in raw.items()}
    if fault == "version_bool": raw["AgentSimulator"][0] = True
    if fault == "fingerprint": raw["AgentSimulator"][1] = "changed"
    if fault == "descriptor": raw["AgentSimulator"][2] += "changed"
    if fault == "missing": raw.pop("AgentSimulator")
    if fault is None: O.pin_schemas(raw, expected)
    else:
        with pytest.raises(O.Refused): O.pin_schemas(raw, expected)


def publication(pin):
    run = {"id": pin.run_id, "head_sha": pin.source, "run_attempt": 1, "status": "completed",
           "conclusion": "success", "path": pin.workflow, "repository": {"id": I.REPOSITORY_ID}}
    job = {"id": pin.job_id, "run_id": pin.run_id, "run_attempt": 1, "head_sha": pin.source,
           "status": "completed", "conclusion": "success"}
    artifact = {"id": pin.artifact_id, "name": pin.name, "size_in_bytes": pin.size, "digest": "sha256:" + pin.sha256,
                "expired": False, "expires_at": pin.expiry, "workflow_run": {"id": pin.run_id, "head_sha": pin.source,
                "repository_id": I.REPOSITORY_ID, "head_repository_id": I.REPOSITORY_ID}}
    return run, job, artifact


@pytest.mark.parametrize("fault", [None, "source", "attempt", "size_bool", "expiry", "expired", "digest"])
def test_only_the_closed_completed_unexpired090_publication_is_admitted(fault):
    pin = I.artifact_pins(REFERENCE)[0]; run, job, artifact = publication(pin)
    now = datetime(2026, 10, 29, tzinfo=timezone.utc)
    if fault == "source": run["head_sha"] = "b" * 40
    if fault == "attempt": job["run_attempt"] = 2
    if fault == "size_bool": artifact["size_in_bytes"] = True
    if fault == "expiry": artifact["expires_at"] = "2026-11-13T11:35:09Z"
    if fault == "expired": now = datetime(2026, 12, 1, tzinfo=timezone.utc)
    if fault == "digest": artifact["digest"] = "sha256:" + "0" * 64
    if fault is None: assert I.validate_publication(pin, run, job, artifact, now)["identity"]["source"] == REFERENCE["source"]
    else:
        with pytest.raises(I.Refusal): I.validate_publication(pin, run, job, artifact, now)


@pytest.mark.parametrize("fault", [None, "extra", "hash", "expansion", "member"])
def test_tiny_zip_content_closure_crc_and_caps_without_payload_imports(fault):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr("data.txt", b"abc")
        if fault == "extra": z.writestr("extra.txt", b"no")
    stream.seek(0)
    rows = {"data.txt": {"bytes": 3, "sha256": hashlib.sha256(b"abc").hexdigest()}}
    if fault == "hash": rows["data.txt"]["sha256"] = "0" * 64
    options = {"expanded_limit": 2 if fault == "expansion" else 20, "member_limit": 2 if fault == "member" else 10}
    if fault is None:
        actual, keep = I.verify_zip(stream, rows, keep=("data.txt",), **options)
        assert actual == rows and keep == {"data.txt": b"abc"}
    else:
        with pytest.raises(I.Refusal): I.verify_zip(stream, rows, **options)


@pytest.mark.parametrize("fault", [None, "changed", "symlink", "broken"])
def test_dormant_or_exact_active_workflow_is_source_bound(tmp_path, monkeypatch, fault):
    template = tmp_path / "docs/experiments/current090-passive-profile.yml.inactive"
    template.parent.mkdir(parents=True); template.write_text("synthetic exact reviewed workflow")
    monkeypatch.setattr(O, "WORKFLOW_SHA", hashlib.sha256(template.read_bytes()).hexdigest())
    O.verify_workflow(tmp_path)  # Legitimately dormant; no actual copy exists.
    active = tmp_path / O.WORKFLOW_PATH; active.parent.mkdir(parents=True)
    if fault == "symlink": active.symlink_to(template)
    elif fault == "broken": active.symlink_to(tmp_path / "missing")
    else: active.write_bytes(template.read_bytes() + (b"changed" if fault else b""))
    if fault is None: O.verify_workflow(tmp_path)
    else:
        with pytest.raises((O.Refused, FileNotFoundError)): O.verify_workflow(tmp_path)


@pytest.mark.parametrize("fault", [None, "owner_step", "missing", "symlink", "digest", "sentinel", "cap", "source"])
def test_bounded_metadata_publication_cannot_promote_early_or_failed_owner(tmp_path, monkeypatch, fault):
    P = load("passive090_publish_test_metadata", ROOT / "scripts/current090_profile_publish.py")
    root = tmp_path / "study"; root.mkdir(); out = tmp_path / "publication"
    source = "a" * 40
    for name in P.selected_paths():
        if name == "terminal-failure.json": continue
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("{}\n")
    result = {"complete": True, "instrumentation_equal": True, "producer": {"GITHUB_SHA": source}}
    (root / "result.json").write_text(json.dumps(result))
    terminal = {"complete": True, "cleanup_complete": True, "required_wrapper_exit": 0,
                "result_sha256": hashlib.sha256((root / "result.json").read_bytes()).hexdigest()}
    if fault == "digest": terminal["result_sha256"] = "0" * 64
    (root / "terminal.json").write_text(json.dumps(terminal))
    if fault == "missing": (root / "pure-preflight/receipt.json").unlink()
    if fault == "symlink":
        path = root / "admission.json"; path.unlink(); path.symlink_to(root / "result.json")
    if fault == "sentinel": (root / "terminal-failure.json").symlink_to(root / "absent")
    if fault == "cap": monkeypatch.setattr(P, "TOTAL_LIMIT", 128)
    # A simulated raw body is outside the semantic keep set and never read.
    (root / "body.ckpt").write_bytes(b"never decoded, copied or hashed")
    observed, original = [], P.read_regular
    def observed_read(path, *args, **kwargs):
        observed.append(path.relative_to(root).as_posix()); return original(path, *args, **kwargs)
    monkeypatch.setattr(P, "read_regular", observed_read)
    report = P.publish(root, out, owner_outcome="failure" if fault == "owner_step" else "success",
                       source="b" * 40 if fault == "source" else source)
    assert report["complete"] is (fault is None)
    assert not report["raw_payload_retained"] and not report["source_publication_qualified"]
    assert "body.ckpt" not in observed and not (out / "body.ckpt").exists()
    assert json.loads((out / "publication.json").read_text()) == report
    assert len(report["files"]) < P.FILE_LIMIT and report["retained_bytes"] + 65536 <= max(P.TOTAL_LIMIT, 65536)


def closure_report():
    return {"complete": False, "instrumentation_equal": False, "cleanup_complete": True,
            "stage": "final-admission", "errors": [], "producer": {"GITHUB_SHA": "a" * 40},
            "retained_inventory": {"bytes": 0, "file_count": 0, "files": {}}}


@pytest.mark.parametrize("fault", [None, "wall", "cpu", "source", "resource", "expiry", "cancel", "source_runtime"])
def test_terminal_closure_checks_late_fault_after_actual_write_and_invalidates(tmp_path, monkeypatch, fault):
    clock = SimpleNamespace(wall=1.0, cpu=1.0, written=False)
    monkeypatch.setattr(O, "time", SimpleNamespace(monotonic=lambda: clock.wall))
    monkeypatch.setattr(O, "cpu_seconds", lambda: clock.cpu)
    original, calls = O.write, []
    def writer(path, value, limit=8 * 1024**2):
        original(path, value, limit); calls.append(path.name)
        if path.name == "terminal.json":
            clock.written = True
            if fault == "wall": clock.wall = 2401.0
            if fault == "cpu": clock.cpu = 1801.0
    monkeypatch.setattr(O, "write", writer)
    def guard():
        if clock.written and fault in ("source", "resource", "expiry", "cancel", "source_runtime"):
            raise O.Refused("synthetic late " + fault)
        O.require(clock.wall <= 2400 and clock.cpu <= 1800, "synthetic live budget")
    report = closure_report()
    accepted = O.finalize_authorities(tmp_path, report, eligible=True, guard=guard, started=0, cpu_started=0)
    assert accepted is (fault is None) and report["complete"] is (fault is None)
    assert "terminal.json" in calls
    if fault is None:
        terminal = json.loads((tmp_path / "terminal.json").read_text())
        assert terminal["complete"] is True and terminal["result_sha256"] == hashlib.sha256((tmp_path / "result.json").read_bytes()).hexdigest()
        assert not (tmp_path / "terminal-failure.json").exists()
    else:
        assert json.loads((tmp_path / "result.json").read_text())["complete"] is False
        assert json.loads((tmp_path / "terminal.json").read_text())["complete"] is False
        assert json.loads((tmp_path / "terminal-failure.json").read_text())["complete"] is False
        assert report["errors"][-1]["stage"] == "terminal-closure"


def test_terminal_closure_counts_actual_refreshed_authority_lengths_near_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "time", SimpleNamespace(monotonic=lambda: 1.0))
    monkeypatch.setattr(O, "cpu_seconds", lambda: 1.0)
    first = tmp_path / "short"; first.mkdir()
    assert O.finalize_authorities(first, closure_report(), eligible=True, guard=lambda: None,
                                  started=0, cpu_started=0, publication_bytes=0, publication_files=0)
    exact = (first / "result.json").stat().st_size + (first / "terminal.json").stat().st_size + 65536
    # This is accounting tightening, not proof the parent's conservative64KiB
    # terminal reserve was actually insufficient for a real timing value.
    monkeypatch.setattr(O, "time", SimpleNamespace(monotonic=lambda: 1e100))
    monkeypatch.setattr(O, "cpu_seconds", lambda: 1e100)
    second = tmp_path / "long"; second.mkdir(); report = closure_report()
    assert not O.finalize_authorities(second, report, eligible=True, guard=lambda: None,
        started=0, cpu_started=0, max_bytes=exact, publication_bytes=0, publication_files=0)
    assert json.loads((second / "terminal-failure.json").read_text())["complete"] is False


@pytest.mark.parametrize("fault", ["terminal_write", "negative_rewrite"])
def test_terminal_closure_partial_or_failed_invalidation_keeps_negative_sentinel(tmp_path, monkeypatch, fault):
    report, original = closure_report(), O.write
    state = {"postwrite": False}
    def writer(path, value, limit=8 * 1024**2):
        if fault == "terminal_write" and path.name == "terminal.json" and value.get("complete"):
            raise OSError("synthetic terminal fsync fault")
        if fault == "negative_rewrite" and path.name != "terminal-failure.json" and not value.get("complete"):
            raise OSError("synthetic authority invalidation write fault")
        original(path, value, limit)
        if path.name == "terminal.json": state["postwrite"] = True
    def guard():
        if fault == "negative_rewrite" and state["postwrite"]: raise O.Refused("synthetic late guard")
    monkeypatch.setattr(O, "write", writer)
    assert not O.finalize_authorities(tmp_path, report, eligible=True, guard=guard, started=0, cpu_started=0)
    assert json.loads((tmp_path / "terminal-failure.json").read_text())["complete"] is False
    for name in ("result.json", "terminal.json"):
        assert not (tmp_path / name).exists() or json.loads((tmp_path / name).read_text())["complete"] is False


def test_terminal_closure_has_no_positive_io_after_final_full_guard(tmp_path, monkeypatch):
    seen, original_write, original_sha = [], O.write, O.sha
    def writer(path, value, limit=8 * 1024**2):
        seen.append("write:" + path.name); original_write(path, value, limit)
    def hashed(path): seen.append("hash:" + path.name); return original_sha(path)
    def guard(): seen.append("guard")
    monkeypatch.setattr(O, "write", writer); monkeypatch.setattr(O, "sha", hashed)
    assert O.finalize_authorities(tmp_path, closure_report(), eligible=True, guard=guard, started=0, cpu_started=0)
    assert seen[0] == seen[-1] == "guard" and seen.count("guard") == 2
    assert seen.index("write:terminal.json") < seen.index("hash:terminal.json") < len(seen) - 1


def test_null_scenario_remains_valid_after_owner_registration(monkeypatch):
    monkeypatch.setattr(O, "EXECUTION_APPROVAL", "a" * 64)
    # Exercise the actual high-level refusal test against a registered owner's
    # starting state. It must set up NULL explicitly before reaching host I/O.
    test_null_source_approval_precedes_any_host_or_source_access(monkeypatch)
    assert O.EXECUTION_APPROVAL is None


def diagnostic_core():
    class GraphRefused(ValueError):
        def __str__(self): raise AssertionError("arbitrary exception text must not be formatted")
    fixed = {"case": "small", "regions": 12, "target": 2000, "role": "plain", "seed": 42, "civs": 4, "turns": 97}
    return SimpleNamespace(Refused=GraphRefused, schedule=lambda: [dict(fixed) for _ in range(6)])


@pytest.mark.parametrize("message,reason,name", [
    ("unsupported state type: chronicler.example.Extra", "STATE_TYPE", "chronicler.example.Extra"),
    ("unsupported NumPy dtype", "NUMPY_DTYPE", None),
    ("ambiguous duplicate slot storage", "DUPLICATE_SLOT_STORAGE", None),
])
def test_role_diagnostic_keeps_only_source_owned_graph_reason(message, reason, name):
    core = diagnostic_core(); record = O.role_failure_record(core.Refused(message), core, 0)
    assert record["reason_code"] == reason and record["type_name"] == name
    assert record["exception_code"] == "CORE_REFUSED"
    assert record["request"] == core.schedule()[0] and record["index"] == 0
    assert record["complete"] is record["role_success"] is False
    assert set(record) == {"complete", "role_success", "index", "request", "exception_code", "reason_code", "type_name"}


@pytest.mark.parametrize("fault", ["unknown", "newline", "unicode", "long", "empty", "dotted", "args", "subclass"])
def test_role_diagnostic_never_serializes_unclassified_text_or_invalid_type(fault):
    core = diagnostic_core(); prefix = "unsupported state type: "
    messages = {"unknown": "raw arbitrary state secret must not survive", "newline": prefix + "module.Type\nSECRET",
                "unicode": prefix + "module.Týpe", "long": prefix + "x" * 257,
                "empty": prefix, "dotted": prefix + "module..Type", "args": {"raw_state": "secret"}}
    if fault == "subclass":
        class Foreign(core.Refused): pass
        exc = Foreign(prefix + "module.Type")
    else: exc = core.Refused(messages[fault])
    record = O.role_failure_record(exc, core, 0)
    assert record["reason_code"] == "UNCLASSIFIED" and record["type_name"] is None
    assert record["exception_code"] == ("UNCLASSIFIED" if fault == "subclass" else "CORE_REFUSED")
    assert "secret" not in json.dumps(record).lower() and "SECRET" not in json.dumps(record)


def test_role_diagnostic_max_qualified_type_and_fixed_request_fit_4k():
    core = diagnostic_core(); name = "a." + "B" * 254
    record = O.role_failure_record(core.Refused("unsupported state type: " + name), core, 0)
    assert len(record["type_name"]) == 256
    raw = (json.dumps(record, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    assert len(raw) <= 4096 and record["complete"] is record["role_success"] is False


def test_role_diagnostic_literal_codes_are_bound_to_exact_core_source():
    tree = ast.parse((ROOT / "scripts/current090_passive_profile.py").read_bytes())
    literals = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and type(node.value) is str}
    assert set(O.GRAPH_REFUSAL_CODES) <= literals
    assert all(code and all(char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ_" for char in code)
               for code in O.GRAPH_REFUSAL_CODES.values())


def execute_retained_role_diagnostic_try(core, args, admission, writer):
    # Compile only the exact role call/diagnostic try from the reviewed source,
    # under fake arguments and function. Never execute child/admission/physics.
    import copy
    tree = ast.parse((ROOT / "scripts/current090_profile_owner.py").read_bytes())
    child = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "child")
    retained = next(node for node in ast.walk(child) if isinstance(node, ast.Try)
                    and len(node.body) == 1 and isinstance(node.body[0], ast.Assign)
                    and isinstance(node.body[0].value, ast.Call)
                    and isinstance(node.body[0].value.func, ast.Attribute)
                    and node.body[0].value.func.attr == "run_role")
    fn = ast.parse("def retained_role():\n pass\n").body[0]
    fn.body = [copy.deepcopy(retained), ast.parse("return result").body[0]]
    unit = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    scope = {"core": core, "args": args, "admission": admission, "write": writer,
             "role_failure_record": O.role_failure_record}
    exec(compile(unit, "exact-source-role-diagnostic-try", "exec"), scope)
    return scope["retained_role"]()


def test_role_diagnostic_success_preserves_same_return_and_call_without_write(tmp_path):
    core, answer, observed = diagnostic_core(), object(), []
    def run(request, **kwargs): observed.append((request, kwargs)); return answer
    core.run_role = run
    args = SimpleNamespace(index=0, ordinary=tmp_path / "ordinary", checkpoint=tmp_path / "cp", result=tmp_path / "role.json")
    admission = {"rng": object()}
    result = execute_retained_role_diagnostic_try(core, args, admission, lambda *a: pytest.fail("success diagnostic write"))
    assert result is answer and len(observed) == 1
    assert observed[0] == (core.schedule()[0], {"ordinary": args.ordinary, "checkpoint": args.checkpoint,
                                             "shared_rng": admission["rng"], "admission": admission})
    assert not args.result.exists()


@pytest.mark.parametrize("writer_exception", [OSError, KeyboardInterrupt])
def test_role_diagnostic_writer_fault_never_replaces_original_exception(tmp_path, writer_exception):
    core = diagnostic_core(); original = core.Refused("unsupported state type: module.Extra")
    def run(*args, **kwargs): raise original
    core.run_role = run; observed = []
    args = SimpleNamespace(index=0, ordinary=tmp_path / "ordinary", checkpoint=tmp_path / "cp", result=tmp_path / "role.json")
    def writer(path, value, limit):
        observed.append((path, value, limit)); raise writer_exception("synthetic writer fault")
    with pytest.raises(core.Refused) as caught:
        execute_retained_role_diagnostic_try(core, args, {"rng": None}, writer)
    assert caught.value is original and len(observed) == 1
    assert observed[0][0] == args.result and observed[0][2] == 4096 and observed[0][1]["complete"] is False


def test_role_diagnostic_failure_uses_existing_published_role_path_only(tmp_path):
    core = diagnostic_core(); original = core.Refused("unsupported NumPy exact type")
    def run(*args, **kwargs): raise original
    core.run_role = run
    args = SimpleNamespace(index=0, ordinary=tmp_path / "ordinary", checkpoint=tmp_path / "cp", result=tmp_path / "role.json")
    with pytest.raises(core.Refused) as caught:
        execute_retained_role_diagnostic_try(core, args, {"rng": None}, O.write)
    assert caught.value is original and list(tmp_path.iterdir()) == [args.result]
    record = json.loads(args.result.read_text())
    assert record["complete"] is record["role_success"] is False and record["reason_code"] == "NUMPY_EXACT_TYPE"
    assert args.result.stat().st_size <= 4096


@pytest.mark.parametrize("literal,code", [
    ("authority exclusion set", "AUTHORITY_EXCLUSION_SET"),
    ("inventory directory depth", "INVENTORY_DEPTH"),
    ("inventory entry cap", "INVENTORY_ENTRY_CAP"),
    ("inventory component", "INVENTORY_COMPONENT"),
    ("authority bound", "AUTHORITY_BOUND"),
    ("directory changed", "DIRECTORY_CHANGED"),
    ("inventory nonregular/alias", "INVENTORY_NONREGULAR_ALIAS"),
    ("inventory cap", "INVENTORY_CAP"),
    ("inventory identity", "INVENTORY_IDENTITY"),
    ("inventory changed", "INVENTORY_CHANGED"),
    ("finalization budget", "FINALIZATION_BUDGET"),
])
def test_retention_diagnostic_uses_exact_closed_owner_literals(monkeypatch, literal, code):
    def forbidden(_self): pytest.fail("exception text formatting")
    monkeypatch.setattr(O.Refused, "__str__", forbidden)
    assert O.retention_failure_record(O.Refused(literal)) == {
        "exception_code": "OWNER_REFUSED", "reason_code": code}


@pytest.mark.parametrize("fault", ["unknown", "foreign", "subclass", "string_subclass", "zero_args",
                                  "multiple_args", "nonstring", "long", "newline"])
def test_retention_diagnostic_never_formats_unclassified_arguments(fault):
    class Dangerous:
        def __str__(self): pytest.fail("arbitrary argument str")
        def __repr__(self): pytest.fail("arbitrary argument repr")
        def __hash__(self): pytest.fail("arbitrary argument hash")
    class String(str):
        def __hash__(self): pytest.fail("string subclass hash")
        def __eq__(self, _other): pytest.fail("string subclass comparison")
    class Foreign(O.Refused):
        def __str__(self): pytest.fail("foreign exception str")
    variants = {"unknown": O.Refused("private/state/path secret"), "foreign": OSError("inventory cap"),
                "subclass": Foreign("inventory cap"), "string_subclass": O.Refused(String("inventory cap")),
                "zero_args": O.Refused(), "multiple_args": O.Refused("inventory cap", Dangerous()),
                "nonstring": O.Refused(Dangerous()), "long": O.Refused("private" * 10000),
                "newline": O.Refused("inventory cap\nprivate/path secret")}
    record = O.retention_failure_record(variants[fault])
    assert record == {"exception_code": "UNKNOWN" if fault in ("foreign", "subclass") else "OWNER_REFUSED",
                      "reason_code": "UNKNOWN"}
    assert len(json.dumps(record)) < 128 and "private" not in json.dumps(record)


def test_retention_diagnostic_map_is_bound_to_inventory_and_budget_source_literals():
    tree = ast.parse((ROOT / "scripts/current090_profile_owner.py").read_bytes())
    inventory_node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "inventory")
    execute_node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "execute")
    budget = next(node for node in ast.walk(execute_node) if isinstance(node, ast.FunctionDef) and node.name == "budget_guard")
    literals = {node.value for root in (inventory_node, budget) for node in ast.walk(root)
                if isinstance(node, ast.Constant) and type(node.value) is str}
    assert set(O.INVENTORY_REFUSAL_CODES) <= literals
    assert len(O.INVENTORY_REFUSAL_CODES) == 11
    assert all(code and all(char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ_" for char in code)
               for code in O.INVENTORY_REFUSAL_CODES.values())


@pytest.mark.parametrize("fault", ["symlink", "hardlink", "bytes", "files", "budget"])
def test_real_tiny_inventory_refusals_emit_no_paths_or_body_text(tmp_path, fault):
    body = tmp_path / "private-state-name"; body.write_bytes(b"private-state-body")
    options = {}
    if fault == "symlink": (tmp_path / "private-link-name").symlink_to(body)
    if fault == "hardlink": os.link(body, tmp_path / "private-alias-name")
    if fault == "bytes": options["max_bytes"] = 0
    if fault == "files": options["max_files"] = 0
    if fault == "budget":
        def guard(): raise O.Refused("finalization budget")
        options["guard"] = guard
    with pytest.raises(O.Refused) as caught: O.inventory(tmp_path, **options)
    record = O.retention_failure_record(caught.value)
    expected = ("INVENTORY_NONREGULAR_ALIAS" if fault in ("symlink", "hardlink") else
                "FINALIZATION_BUDGET" if fault == "budget" else "INVENTORY_CAP")
    assert record == {"exception_code": "OWNER_REFUSED", "reason_code": expected}
    assert "private" not in json.dumps(record)


def unavailable_report(null=False, cleanup=False):
    report = closure_report(); report.pop("retained_inventory")
    report.update(stage="role:0", cleanup_complete=cleanup, completed_roles=[], actual_failed_role_ticks=None,
                  errors=[{"stage": "role:0", "type": "BridgeRefused"}, {"stage": "retention", "type": "Refused"}],
                  retention_diagnostic={"exception_code": "OWNER_REFUSED", "reason_code": "INVENTORY_CAP"})
    if null: report["retained_inventory"] = None
    return report


@pytest.mark.parametrize("null,cleanup", [(False, False), (False, True), (True, False), (True, True)])
def test_missing_or_null_inventory_stays_negative_and_preserves_unknown_counts(tmp_path, null, cleanup):
    report = unavailable_report(null, cleanup); prior_errors = list(report["errors"])
    assert not O.finalize_authorities(tmp_path, report, eligible=True, guard=lambda: None, started=0, cpu_started=0)
    assert report["complete"] is report["instrumentation_equal"] is False
    assert report["cleanup_complete"] is cleanup and report["errors"][:2] == prior_errors
    assert report["errors"][-1] == {"stage": "terminal-closure", "type": "Refused"}
    assert report["retention_status"] == "INVENTORY_UNAVAILABLE"
    assert ("retained_inventory" in report) is null
    if null: assert report["retained_inventory"] is None
    assert report["completed_roles"] == [] and report["actual_failed_role_ticks"] is None
    assert not {"actual_generated_stepped_runs", "actual_physics_ticks", "unstepped_final_cp_decodes",
                "bytes", "file_count", "files"} & set(report)
    for name in ("terminal-failure.json", "terminal.json"):
        terminal = json.loads((tmp_path / name).read_bytes())
        assert terminal["complete"] is False and terminal["cleanup_complete"] is cleanup
        assert terminal["retention_status"] == "INVENTORY_UNAVAILABLE" and terminal["publication_failed"] is True
    assert json.loads((tmp_path / "result.json").read_bytes()) == report


@pytest.mark.parametrize("fault", ["sentinel", "result", "terminal", "all", "interrupt"])
def test_unavailable_inventory_writer_faults_and_stale_authorities_never_promote(tmp_path, monkeypatch, fault):
    P = load("passive090_publish_inventory_fault_metadata", ROOT / "scripts/current090_profile_publish.py")
    root = tmp_path / "study"; root.mkdir(); source = "a" * 40
    for name in P.selected_paths():
        if name == "terminal-failure.json": continue
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("{}\n")
    stale = closure_report(); stale.update(complete=True, instrumentation_equal=True)
    O.write(root / "result.json", stale)
    O.write(root / "terminal.json", {"complete": True, "cleanup_complete": True, "required_wrapper_exit": 0,
            "result_sha256": hashlib.sha256((root / "result.json").read_bytes()).hexdigest()})
    original = O.write; calls = []
    def writer(path, value, limit=8 * 1024**2):
        calls.append((path.name, value["complete"]))
        selected = {"sentinel": "terminal-failure.json", "result": "result.json", "terminal": "terminal.json"}
        if fault in ("all", "interrupt") or path.name == selected[fault]:
            raise (KeyboardInterrupt if fault == "interrupt" else OSError)("private writer detail")
        return original(path, value, limit)
    report = unavailable_report()
    with monkeypatch.context() as patch:
        patch.setattr(O, "write", writer)
        if fault == "all":
            def cannot_unlink(*_args, **_kwargs): raise OSError("private invalidation detail")
            patch.setattr(Path, "unlink", cannot_unlink)
        accepted = O.finalize_authorities(root, report, eligible=True, guard=lambda: None, started=0, cpu_started=0)
    assert accepted is False and report["complete"] is report["instrumentation_equal"] is False
    assert calls[0] == ("terminal-failure.json", False) and all(not complete for _, complete in calls)
    assert report["errors"][:2] == unavailable_report()["errors"]
    if fault == "all":
        assert json.loads((root / "result.json").read_bytes())["complete"] is True
        assert json.loads((root / "terminal.json").read_bytes())["complete"] is True
        assert not (root / "terminal-failure.json").exists()
    publication = P.publish(root, tmp_path / "publication", owner_outcome="failure", source=source)
    assert publication["complete"] is False and publication["owner_step_outcome"] == "failure"
    assert "private" not in json.dumps(report)


def test_unavailable_inventory_dispatch_precedes_positive_guard_and_authority_inspection(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs): pytest.fail("positive finalization work with unavailable inventory")
    monkeypatch.setattr(O, "regular", forbidden); monkeypatch.setattr(O, "sha", forbidden)
    assert not O.finalize_authorities(tmp_path, unavailable_report(), eligible=True, guard=forbidden,
                                     started=0, cpu_started=0)


def execute_retained_finally_with_fake_inventory(root, report, inventory):
    # Compile only the owner's exact finally and outer return. The unavailable
    # inventory dispatch must prevent any positive source/runtime/host access.
    import copy
    tree = ast.parse((ROOT / "scripts/current090_profile_owner.py").read_bytes())
    execute = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "execute")
    retained = next(node for node in execute.body if isinstance(node, ast.Try) and node.finalbody)
    fn = ast.parse("def retained_finally(root, report):\n eligible = True\n").body[0]
    fn.body += copy.deepcopy(retained.finalbody) + [copy.deepcopy(execute.body[-1])]
    unit = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    scope = {"time": SimpleNamespace(monotonic=lambda: 1), "started": 0, "cpu_started": 0,
             "cpu_seconds": lambda: 1, "deadline": 2400, "supervisor": None, "require": O.require,
             "inventory": inventory, "retention_failure_record": O.retention_failure_record,
             "finalize_authorities": O.finalize_authorities}
    exec(compile(unit, "exact-source-retention-finally", "exec"), scope)
    return scope["retained_finally"](root, report)


@pytest.mark.parametrize("literal,code", [("inventory nonregular/alias", "INVENTORY_NONREGULAR_ALIAS"),
                                         ("private unclassified reason", "UNKNOWN")])
def test_retention_failure_retains_first_role_and_returns_outer_failure(tmp_path, literal, code):
    report = unavailable_report(); report["errors"] = report["errors"][:1]; report.pop("retention_diagnostic")
    def failed_inventory(*_args, **_kwargs): raise O.Refused(literal)
    assert execute_retained_finally_with_fake_inventory(tmp_path, report, failed_inventory) == 2
    assert report["errors"] == [{"stage": "role:0", "type": "BridgeRefused"},
                                {"stage": "retention", "type": "Refused"},
                                {"stage": "terminal-closure", "type": "Refused"}]
    assert report["retention_diagnostic"] == {"exception_code": "OWNER_REFUSED", "reason_code": code}
    assert report["retention_status"] == "INVENTORY_UNAVAILABLE" and report["cleanup_complete"] is False
    assert report["actual_failed_role_ticks"] is None and "retained_inventory" not in report
    assert "private" not in json.dumps(report)
