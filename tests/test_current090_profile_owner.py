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
