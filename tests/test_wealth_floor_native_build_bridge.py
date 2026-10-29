"""Pure paired-native provenance and bounded-read contracts; no native import."""
from copy import deepcopy
import errno
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import zipfile

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def B():
    return load("wealth_native_bridge_contract", ROOT / "scripts/wealth_floor_native_build_bridge.py")


@pytest.fixture(scope="module")
def C():
    return load("wealth_native_controller_contract", ROOT / "scripts/wealth_floor_native_build_controller.py")


def context(B):
    flags = {name: None for name in B.REQUIRED_FLAGS | B.OPTIONAL_FLAGS}
    flags.update(CARGO_TARGET_DIR="/tmp/full-gates-cargo", CARGO_BUILD_JOBS="1", CARGO_INCREMENTAL="0")
    return dict(unknown=[], rustc="rustc 1.99.1 (58cf8f9c3 2026-10-13)\ncommit-hash: " + B.RUSTC_COMMIT + "\nLLVM version: 23.1.1",
        cargo="cargo 1.99.1 (5f94df478 2026-08-27)", maturin="maturin 1.15.0", uv="uv 0.13.6 (x86_64-unknown-linux-gnu)",
        python="3.13.17", target=B.TARGET, flags=flags,
        linker=dict(path="/usr/bin/ld", version="GNU ld fixture", executable_sha256="f" * 64),
        executables=[dict(path="/usr/bin/" + name, version="observed fixture", sha256="f" * 64) for name in ("rustc", "cargo", "ld")],
        host=dict(system="Linux", machine="x86_64", platform="Linux fixture", image_os="ubuntu24", image_version="fixture"),
        release_profile={"codegen-units": 1, "lto": True, "opt-level": 3}, features=["pyo3/extension-module"],
        lock_sha256=B.LOCK_SHA256, pyproject_sha256=B.PYPROJECT_SHA256,
        manifest_path="/work/candidate/chronicler-agents/Cargo.toml", target_path="/tmp/full-gates-cargo",
        staging_wheel_path="/tmp/full-gates-build/wheels",
        build_argv=["-m", "maturin", "build", "--release", "--locked", "--manifest-path",
            "/work/candidate/chronicler-agents/Cargo.toml", "--out", "/tmp/full-gates-build/wheels"],
        cargo_config=dict(checked_absent_paths=["/home/runner/.cargo/config", "/home/runner/.cargo/config.toml"],
            scope="Cargo home and command/manifest ancestors; config files absent"))


def phase(B, role, *, baseline_hash=None):
    native = (baseline_hash or B.OLD_NATIVE) if role == "baseline" else "a" * 64
    environment = "/tmp/probe-" + role
    return dict(source_sha=B.SOURCES[role][0], crate_tree=B.SOURCES[role][1], source_clean=True,
        build_complete=True, cleanup_complete=True, source_before_sha256="1" * 64, source_after_sha256="1" * 64,
        wheel=dict(filename=B.WHEEL_NAME, bytes=100, sha256=("2" if role == "baseline" else "3") * 64,
            native_sha256=native, native_member=B.NATIVE_MEMBER),
        probe=dict(compiled_extension=True, real_exported_classes=True, native_sha256=native, python=B.PYTHON_VERSION,
            native_path=environment + "/lib/python3.13/site-packages/" + B.NATIVE_MEMBER, environment_root=environment,
            source_imports=[], native_pools_created=0,
            schemas={name: dict(version=row[0], fingerprint=row[1], schema_sha256=row[2]) for name, row in B.OLD_SCHEMAS.items()}),
        context=context(B), regressions=None if role == "baseline" else {name: "PASS" for name in B.REGRESSIONS})


def closed_clock():
    return dict(final_observation=True, cleanup_complete=True, live_processes=0, wall_seconds=20.0, wall_limit_seconds=1800,
        controller_measured_cpu_seconds=1.0, waited_children_cpu_seconds=15.0)


def test_exact_rebuild_is_only_a_pending_historical_bridge(B):
    result = B.classify_pair(phase(B, "baseline"), phase(B, "candidate"), closed_clock())
    assert result["historical_reuse_eligible"] is True
    assert result["classification"] == "historical_reuse_eligible"
    assert result["status"] == "build_complete_pending_job"
    assert result["candidate_worlds_admitted"] is False
    assert result["baseline_context_sha256"] == result["candidate_context_sha256"] == B.digest(context(B))
    assert "linker/full argv" in result["original_context_unknown"]


def test_changed_old_native_keeps_fresh_pair_but_refuses_historical_reuse(B):
    result = B.classify_pair(phase(B, "baseline", baseline_hash="b" * 64), phase(B, "candidate"), closed_clock())
    assert result["historical_reuse_eligible"] is False
    assert result["classification"] == "fresh_baseline_required"
    assert result["candidate_worlds_admitted"] is False


@pytest.mark.parametrize("denied", [False, True])
def test_deployment_observations_survive_pair_classification_and_raw_light_publication(B, C, tmp_path, monkeypatch, denied):
    import wealth_floor_hosted_deployment as D
    def namespace(path):
        if denied and path == "/proc/1/ns/cgroup":
            raise PermissionError(errno.EACCES, "private text must not enter receipt")
        return "cgroup:[12]"
    deployment = D.hosted_vm_precondition(environ={"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted"},
        read_text=lambda _path: "systemd\n", read_link=namespace)
    report = dict(phases={role: phase(B, role) for role in ("baseline", "candidate")},
        producer=dict(control_sha="fixture", run_id="fixture"), deployment=deployment,
        regression_loader=dict(scope="candidate-regressions child only", LD_LIBRARY_PATH="/selected/python/lib"),
        legacy_supervisor_source=C.LEGACY_SOURCE, legacy_supervisor_sha256=C.LEGACY_SHA)
    result = C.classify_build_report(report, closed_clock())
    assert result["deployment"] == deployment
    assert result["candidate_worlds_admitted"] is False
    monkeypatch.setattr(C, "direct_children", lambda: [])
    completion = C.publish_complete(tmp_path, result, lambda: None, closed_clock)
    raw = json.loads((tmp_path / "build-manifest.json").read_text())
    light = json.loads((tmp_path / "light/build-manifest.json").read_text())
    assert raw["deployment"] == light["deployment"] == deployment
    assert raw["regression_loader"] == light["regression_loader"] == report["regression_loader"]
    assert raw["deployment"]["namespace_equal"] is (None if denied else True)
    assert raw["deployment"]["namespace_equality_verified"] is (not denied)
    assert completion["files"]["build-manifest.json"]["sha256"] == C.sha(tmp_path / "light/build-manifest.json")


@pytest.mark.parametrize("fault", ["unknown_flags", "missing_flags", "extra_flags", "wrapper", "wrong_compiler", "wrong_python",
    "wrong_lock", "wrong_profile", "profile_type_alias", "wrong_features", "unobserved_linker", "missing_compiler_identity",
    "config_unrecorded", "different_context", "source", "source_dirty", "source_changed", "schema", "stale_native",
    "python_source_import", "native_pool", "pool_type_alias", "fake_class", "outside_environment", "same_environment",
    "same_native", "same_wheel", "missing_regression", "late_wall", "cleanup", "live_child", "invalid_clock"])
def test_incomplete_or_substituted_proof_cannot_become_a_bridge(B, fault):
    old, new, clock = phase(B, "baseline"), phase(B, "candidate"), closed_clock()
    c = new["context"]
    if fault == "unknown_flags": c["unknown"] = ["effective flags unknown"]
    elif fault == "missing_flags": del c["flags"]["RUSTDOCFLAGS"]
    elif fault == "extra_flags": c["flags"]["CARGO_PROFILE_RELEASE_PANIC"] = "abort"
    elif fault == "wrapper": c["flags"]["RUSTC_WRAPPER"] = "/tmp/wrapper"
    elif fault == "wrong_compiler": c["rustc"] = "rustc stable"
    elif fault == "wrong_python": c["python"] = "3.13.5"
    elif fault == "wrong_lock": c["lock_sha256"] = "0" * 64
    elif fault == "wrong_profile": c["release_profile"]["opt-level"] = 2
    elif fault == "profile_type_alias": c["release_profile"]["lto"] = 1
    elif fault == "wrong_features": c["features"] += ["jemalloc"]
    elif fault == "unobserved_linker": c["linker"]["executable_sha256"] = "0" * 64
    elif fault == "missing_compiler_identity": c["executables"] = c["executables"][1:]
    elif fault == "config_unrecorded": del c["cargo_config"]
    elif fault == "different_context": c["host"]["image_version"] = "different current image"
    elif fault == "source": new["source_sha"] = B.BASELINE_SOURCE
    elif fault == "source_dirty": new["source_clean"] = False
    elif fault == "source_changed": new["source_after_sha256"] = "0" * 64
    elif fault == "schema": new["probe"]["schemas"]["AgentSimulator"]["fingerprint"] = "different"
    elif fault == "stale_native": new["probe"]["native_sha256"] = B.OLD_NATIVE
    elif fault == "python_source_import": new["probe"]["source_imports"] = ["chronicler"]
    elif fault == "native_pool": new["probe"]["native_pools_created"] = 1
    elif fault == "pool_type_alias": new["probe"]["native_pools_created"] = False
    elif fault == "fake_class": new["probe"]["real_exported_classes"] = False
    elif fault == "outside_environment": new["probe"]["native_path"] = "/tmp/outside/" + B.NATIVE_MEMBER
    elif fault == "same_environment":
        new["probe"]["environment_root"] = old["probe"]["environment_root"]
        new["probe"]["native_path"] = old["probe"]["native_path"]
    elif fault == "same_native":
        new["wheel"]["native_sha256"] = new["probe"]["native_sha256"] = B.OLD_NATIVE
    elif fault == "same_wheel": new["wheel"]["sha256"] = old["wheel"]["sha256"]
    elif fault == "missing_regression": new["regressions"].pop(B.REGRESSIONS[0])
    elif fault == "late_wall": clock["wall_seconds"] = 1800.001
    elif fault == "cleanup": clock["cleanup_complete"] = False
    elif fault == "live_child": clock["live_processes"] = 1
    else: clock["waited_children_cpu_seconds"] = float("nan")
    with pytest.raises(B.BridgeRefused):
        B.classify_pair(old, new, clock)


def call(path, argv, *, result=0):
    return f'execve({json.dumps(path)}, {json.dumps(argv)}, 0x1234 /* 12 vars */) = {result}'


def test_passive_trace_keeps_only_selected_tools_and_never_environment_or_ignored_child_args(B):
    trace = B.TraceAccumulator()
    trace.feed(("123 170000.1 " + call("/tmp/build-script-build", ["ignored", "private-value-not-retained"]) + "\n").encode())
    trace.feed(("124 170000.2 " + call("/usr/bin/rustc", ["rustc", "--crate-name", "chronicler_agents"]) + "\n").encode())
    trace.feed(("125 170000.3 " + call("/usr/bin/ld", ["ld", "-o", "libchronicler_agents.so"]) + "\n").encode())
    result = trace.finish()
    assert result["unknown"] == []
    assert len(result["records"]) == 2 and result["ignored_calls"] == 1
    assert "private-value-not-retained" not in json.dumps(result)
    assert "12 vars" not in json.dumps(result)


def test_hex_encoded_and_split_execve_calls_are_supported_without_eval(B):
    trace = B.TraceAccumulator()
    def literal(s): return '"' + ''.join(f'\\x{ord(c):02x}' for c in s) + '"'
    raw = f'execve({literal("/usr/bin/rustc")}, [{literal("rustc")}], 0x1234 /* 12 vars */) = 0'
    trace.feed(("12 100.1 " + raw + "\n").encode())
    linker = call("/usr/bin/ld", ["ld", "-o", "libchronicler_agents.so"])
    trace.feed(("13 100.2 " + linker.split(") = ")[0] + " <unfinished ...>\n").encode())
    trace.feed(b"13 100.3 <... execve resumed>) = 0\n")
    assert trace.finish()["unknown"] == []


@pytest.mark.parametrize("attack", ["credential", "response_file", "truncated", "verbose_environment", "execveat", "relative_executable"])
def test_incomplete_or_sensitive_trace_is_refused_without_retaining_raw_argv(B, attack):
    secret = "fixture-private-secret-not-retained"
    raw = call("/usr/bin/rustc", ["rustc", "--token=" + secret])
    if attack == "response_file": raw = call("/usr/bin/ld", ["ld", "@/tmp/response-file"])
    elif attack == "truncated": raw = 'execve("/usr/bin/rustc", ["rustc", ...], 0x123 /* 2 vars */) = 0'
    elif attack == "verbose_environment": raw = call("/usr/bin/rustc", ["rustc"]).replace("0x1234 /* 12 vars */", '["TOKEN=' + secret + '"]')
    elif attack == "execveat": raw = 'execveat(3, "", ["rustc"], 0x1234 /* 12 vars */, AT_EMPTY_PATH) = 0'
    elif attack == "relative_executable": raw = call("rustc", ["rustc"])
    trace = B.TraceAccumulator(); trace.feed(("12 100.1 " + raw + "\n").encode())
    result = trace.finish()
    assert result["unknown"] and result["records"] == []
    assert secret not in json.dumps(result)


def test_trace_size_limit_and_missing_linker_cannot_produce_complete_context(B, monkeypatch):
    trace = B.TraceAccumulator()
    trace.feed((call("/usr/bin/rustc", ["rustc"]) + "\n").encode())
    assert "no_observed_actual_linker" in trace.finish()["unknown"]
    monkeypatch.setattr(B, "MAX_TRACE_BYTES", 10)
    with pytest.raises(B.BridgeRefused): B.TraceAccumulator().feed(b"x" * 11)


def wheel(B, *, extra=(), duplicate=False):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("chronicler_agents/__init__.py", b"# synthetic, never imported\n")
        z.writestr(B.NATIVE_MEMBER, b"synthetic native bytes, never imported")
        if duplicate:
            with pytest.warns(UserWarning): z.writestr(B.NATIVE_MEMBER, b"duplicate")
        for name, raw in extra: z.writestr(name, raw)
    return stream.getvalue()


def test_wheel_byte_identity_is_inspected_without_extraction(B, monkeypatch):
    monkeypatch.setattr(zipfile.ZipFile, "extract", lambda *args: pytest.fail("extraction forbidden"))
    raw = wheel(B)
    facts = B.inspect_wheel(raw, B.WHEEL_NAME)
    assert facts["sha256"] == hashlib.sha256(raw).hexdigest()
    assert facts["native_sha256"] == hashlib.sha256(b"synthetic native bytes, never imported").hexdigest()
    assert not any(name == "chronicler_agents" or name.startswith("chronicler_agents.") for name in sys.modules)


@pytest.mark.parametrize("attack", ["duplicate", "traversal", "extra_native", "symlink", "expansion", "index_size", "index_count"])
def test_unsafe_wheel_cannot_be_admitted_for_pip_install(B, attack, monkeypatch):
    extra = ()
    if attack == "traversal": extra = (("../escape", b"x"),)
    elif attack == "extra_native": extra = (("extra.so", b"x"),)
    elif attack == "symlink":
        name = zipfile.ZipInfo("link"); name.create_system = 3; name.external_attr = 0o120777 << 16
        extra = ((name, b"target"),)
    raw = wheel(B, extra=extra, duplicate=attack == "duplicate")
    if attack == "expansion": monkeypatch.setattr(B, "MAX_WHEEL_EXPANSION", 1)
    if attack in ("index_size", "index_count"):
        raw = bytearray(raw); end = raw.rfind(b"PK\x05\x06")
        struct.pack_into("<L" if attack == "index_size" else "<H", raw, end + (12 if attack == "index_size" else 10),
                         B.MIB + 1 if attack == "index_size" else 129)
        raw = bytes(raw)
        monkeypatch.setattr(zipfile, "ZipFile", lambda *args: pytest.fail("unsafe wheel index reached ZipFile"))
    with pytest.raises(B.BridgeRefused): B.inspect_wheel(raw, B.WHEEL_NAME)


def test_build_environment_has_closed_build_inputs_and_preserves_runtime_proxy_and_ca(C, monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy:8080")
    monkeypatch.setenv("SSL_CERT_FILE", "/trusted/ca.pem")
    monkeypatch.setenv("CODEX_RUNTIME_GUARD", "fixture-auth-guard")
    monkeypatch.setenv("CARGO_PROFILE_RELEASE_PANIC", "abort")
    monkeypatch.setenv("RUSTC_WRAPPER", "/unreviewed/wrapper")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/arbitrary/inherited-loader-path")
    env = C.build_environment(Path("/tmp/task"), "/runtime/python")
    assert env["HTTPS_PROXY"] == "http://proxy:8080" and env["SSL_CERT_FILE"] == "/trusted/ca.pem"
    assert env["CODEX_RUNTIME_GUARD"] == "fixture-auth-guard"
    assert "CARGO_PROFILE_RELEASE_PANIC" not in env and "RUSTC_WRAPPER" not in env
    assert "LD_LIBRARY_PATH" not in env
    assert env["RUSTFLAGS"] == "" and env["CARGO_INCREMENTAL"] == "0"


def python_installation(tmp_path):
    prefix = tmp_path / "selected-python"
    (prefix / "bin").mkdir(parents=True); (prefix / "lib").mkdir()
    interpreter = prefix / "bin/python3.13"; interpreter.write_bytes(b"synthetic interpreter; never executed")
    library = prefix / "lib/libpython3.13.so.1.0"; library.write_bytes(b"synthetic library; never imported")
    (prefix / "lib/libpython3.13.so").symlink_to(library.name)
    return interpreter, dict(executable=str(interpreter), base_prefix=str(prefix), libdir=str(prefix / "lib"),
        ldlibrary="libpython3.13.so", python="3.13.17")


@pytest.mark.parametrize("inherited", [None, "/arbitrary/lib", "/arbitrary/lib:/another/lib"])
def test_regression_loader_uses_only_selected_python_and_leaves_release_environment_unchanged(C, tmp_path, inherited):
    interpreter, config = python_installation(tmp_path)
    release = dict(PYO3_PYTHON="/build-environment/bin/python", RUSTFLAGS="", CARGO_BUILD_JOBS="1")
    if inherited is not None: release["LD_LIBRARY_PATH"] = inherited
    before = deepcopy(release)
    child, facts = C.regression_environment(release, str(interpreter), config)
    assert release == before and child is not release
    assert child == dict(release, LD_LIBRARY_PATH=config["libdir"])
    assert facts["LD_LIBRARY_PATH"] == str(interpreter.parents[1] / "lib")
    assert facts["library_path"].endswith("/lib/libpython3.13.so.1.0")
    assert facts["library_sha256"] == hashlib.sha256(b"synthetic library; never imported").hexdigest()
    assert facts["inherited_ld_library_path_used"] is False
    assert "candidate-regressions child only" in facts["scope"] and "release-build environments and context unchanged" in facts["scope"]


def test_selected_python_config_query_has_only_injected_stdlib_observations(C, tmp_path):
    interpreter, config = python_installation(tmp_path)
    calls, output = [], []
    def get_config_var(name):
        calls.append(name)
        return {"LIBDIR": config["libdir"], "LDLIBRARY": config["ldlibrary"]}[name]
    modules = dict(json=json, platform=SimpleNamespace(python_version=lambda: config["python"]),
        sys=SimpleNamespace(executable=str(interpreter), base_prefix=config["base_prefix"]),
        sysconfig=SimpleNamespace(get_config_var=get_config_var))
    exec(C.REGRESSION_PYTHON_CONFIG, {"__builtins__": {"__import__": lambda name, *args: modules[name],
        "print": output.append, "dict": dict}})
    assert calls == ["LIBDIR", "LDLIBRARY"] and len(output) == 1
    observed = json.loads(output[0]); assert observed == config
    child, facts = C.regression_environment({}, str(interpreter), observed)
    assert child == {"LD_LIBRARY_PATH": config["libdir"]} and facts["interpreter"] == str(interpreter)


def test_selected_interpreter_symlink_is_recorded_canonically(C, tmp_path):
    interpreter, config = python_installation(tmp_path)
    alias = interpreter.parent / "python"; alias.symlink_to(interpreter.name)
    config["executable"] = str(alias)
    child, facts = C.regression_environment({}, str(alias), config)
    assert facts["interpreter"] == str(interpreter) and child["LD_LIBRARY_PATH"] == config["libdir"]


@pytest.mark.parametrize("fault", ["missing_key", "wrong_python", "relative_executable", "relative_prefix", "relative_libdir",
    "other_interpreter", "foreign_libdir", "foreign_libdir_symlink", "library_traversal", "wrong_library_name",
    "missing_library", "foreign_library_symlink", "empty_library", "oversized_library"])
def test_unverified_python_loader_paths_cannot_enter_regression_child(C, tmp_path, monkeypatch, fault):
    interpreter, config = python_installation(tmp_path)
    library = interpreter.parents[1] / "lib/libpython3.13.so.1.0"
    foreign = tmp_path / "foreign"; foreign.mkdir()
    if fault == "missing_key": del config["libdir"]
    elif fault == "wrong_python": config["python"] = "3.13.5"
    elif fault == "relative_executable": config["executable"] = "bin/python3.13"
    elif fault == "relative_prefix": config["base_prefix"] = "relative-prefix"
    elif fault == "relative_libdir": config["libdir"] = "lib"
    elif fault == "other_interpreter":
        other = interpreter.parent / "other-python"; other.write_bytes(b"other"); config["executable"] = str(other)
    elif fault == "foreign_libdir": config["libdir"] = str(foreign)
    elif fault == "foreign_libdir_symlink":
        alias = interpreter.parents[1] / "foreign-lib"; alias.symlink_to(foreign); config["libdir"] = str(alias)
    elif fault == "library_traversal": config["ldlibrary"] = "../foreign.so"
    elif fault == "wrong_library_name": config["ldlibrary"] = "libpython3.14.so"
    elif fault == "missing_library": library.unlink()
    elif fault == "foreign_library_symlink":
        outside = foreign / library.name; outside.write_bytes(b"foreign"); library.unlink(); library.symlink_to(outside)
    elif fault == "empty_library": library.write_bytes(b"")
    else:
        monkeypatch.setattr(C.B, "MIB", 1); library.write_bytes(b"x" * 65)
    with pytest.raises((C.B.BridgeRefused, OSError)):
        C.regression_environment({"LD_LIBRARY_PATH": "/inherited"}, str(interpreter), config)


def test_cargo_configuration_presence_refuses_without_reading_credentials(C, tmp_path, monkeypatch):
    source = tmp_path / "candidate"; source.mkdir()
    home = tmp_path / "home"; (home / ".cargo").mkdir(parents=True)
    config = home / ".cargo/config.toml"; config.write_text("private contents must not be read")
    original = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda path, *args, **kwargs:
        pytest.fail("configuration contents must not be read") if path == config else original(path, *args, **kwargs))
    with pytest.raises(C.B.BridgeRefused): C.cargo_config_visibility(source, tmp_path, {"HOME": str(home)})


def test_relative_cargo_home_cannot_hide_command_relative_configuration(C, tmp_path):
    with pytest.raises(C.B.BridgeRefused, match="absolute path"):
        C.cargo_config_visibility(tmp_path, tmp_path, {"HOME": str(tmp_path), "CARGO_HOME": "relative-cargo"})


@pytest.mark.parametrize("kwargs", [{"wall_seconds": 1801}, {"cleanup_wall_reserve": 1},
    {"admission_ram_bytes": 1}, {"running_disk_bytes": 1}])
def test_protocol_budgets_and_resource_floors_cannot_be_relaxed(B, kwargs):
    with pytest.raises(B.BridgeRefused): B.Policy(**kwargs)


def test_pure_library_build_entry_refuses_before_any_execution(B):
    with pytest.raises(B.BridgeRefused): B.main(["build"])


def process_stat_fixture(pid, parent, birth=10):
    fields = ["S", str(parent), *("0" for _ in range(17)), str(birth)]
    return (str(pid) + " (fixture ) name) " + " ".join(fields) + "\n").encode()


def test_proc_ppid_fallback_finds_only_direct_children_without_kernel_wait(C, tmp_path):
    for pid, parent in ((222, 1), (223, 222), (224, 1)):
        folder = tmp_path / str(pid); folder.mkdir(); (folder / "stat").write_bytes(process_stat_fixture(pid, parent))
    result = C.direct_children(proc_root=tmp_path, process_id=222,
        waitid_fn=lambda *args: pytest.fail("nonempty scan must preserve all child wait state"))
    assert result == [223]


def test_kernel_children_file_is_used_without_proc_scan_or_wait(C, tmp_path):
    folder = tmp_path / "self/task/222"; folder.mkdir(parents=True)
    (folder / "children").write_bytes(b"224 223\n")
    assert C.direct_children(proc_root=tmp_path, process_id=222,
        waitid_fn=lambda *args: pytest.fail("nonempty kernel list must not wait")) == [223, 224]


def test_empty_proc_scan_needs_echild_and_preserves_wait_ownership(C, tmp_path):
    calls = []
    def no_children(*args):
        calls.append(args)
        raise ChildProcessError
    assert C.direct_children(proc_root=tmp_path, process_id=222, waitid_fn=no_children) == []
    assert calls == [(C.os.P_ALL, 0, C.os.WEXITED | C.os.WNOHANG | C.os.WNOWAIT)]


@pytest.mark.parametrize("kernel_result", [None, object()])
def test_empty_proc_scan_cannot_hide_a_kernel_child(C, tmp_path, kernel_result):
    with pytest.raises(C.B.BridgeRefused, match="ECHILD"):
        C.direct_children(proc_root=tmp_path, process_id=222, waitid_fn=lambda *args: kernel_result)


@pytest.mark.parametrize("attack", ["malformed_stat", "wrong_pid", "oversized_stat", "duplicate_children", "oversized_children"])
def test_proc_visibility_errors_are_refused_without_claiming_quiescence(C, tmp_path, attack):
    if attack in ("duplicate_children", "oversized_children"):
        path = tmp_path / "self/task/222"; path.mkdir(parents=True)
        (path / "children").write_bytes(b"223 223" if attack == "duplicate_children" else b"x" * 65537)
    else:
        path = tmp_path / "223"; path.mkdir()
        value = {"malformed_stat": b"bad", "wrong_pid": process_stat_fixture(224, 222), "oversized_stat": b"x" * 65537}[attack]
        (path / "stat").write_bytes(value)
    with pytest.raises(C.B.BridgeRefused):
        C.direct_children(proc_root=tmp_path, process_id=222,
            waitid_fn=lambda *args: pytest.fail("untrustworthy scan must refuse before wait"))


def test_workflow_template_stays_dormant_and_preserves_exact_source_chain_and_budgets(B):
    path = ROOT / "docs/experiments/wealth-floor-native-build-bridge-workflow.yml"
    workflow = yaml.safe_load(path.read_text())
    trigger = workflow.get("on", workflow.get(True))
    assert trigger == {"workflow_dispatch": {}}
    job = workflow["jobs"]["paired-native-build"]
    assert job["if"] == "${{ false }}" and job["timeout-minutes"] == 45 and job["runs-on"] == "ubuntu-24.04"
    steps = job["steps"]
    producer = next(s for s in steps if s["name"] == "Check out the exact candidate and its two ancestors")
    assert producer["with"]["ref"] == "503070175e3e78d9014add158ead8f16ce940843" and producer["with"]["fetch-depth"] == 3
    assert B.workflow_contract(workflow) == "prepared"
    active = ROOT / B.WORKFLOW_PATH
    if active.exists():
        assert B.workflow_contract(yaml.safe_load(active.read_text())) == "activated"


@pytest.mark.parametrize("fault", [None, "wrong_branch", "wrong_path", "manual_dispatch", "guard", "source", "budget", "raw_guard"])
def test_known_future_activation_cannot_change_science_sources_commands_or_retention(B, fault):
    workflow = yaml.safe_load((ROOT / "docs/experiments/wealth-floor-native-build-bridge-workflow.yml").read_text())
    workflow.pop(True, None); workflow["on"] = {"push": {"branches": [B.ACTIVE_BRANCH], "paths": [B.WORKFLOW_PATH]}}
    job = workflow["jobs"]["paired-native-build"]
    job["if"] = "${{ github.event_name == 'push' && github.ref == 'refs/heads/" + B.ACTIVE_BRANCH + "' }}"
    if fault is None:
        assert B.workflow_contract(workflow) == "activated"
        return
    if fault == "wrong_branch": workflow["on"]["push"]["branches"] = ["main"]
    elif fault == "wrong_path": workflow["on"]["push"]["paths"] = ["scripts/**"]
    elif fault == "manual_dispatch": workflow["on"]["workflow_dispatch"] = {}
    elif fault == "guard": job["if"] = "always()"
    elif fault == "source": job["steps"][1]["with"]["ref"] = "main"
    elif fault == "budget": job["timeout-minutes"] = 90
    else: job["steps"][-1]["if"] = "success()"
    with pytest.raises(B.BridgeRefused): B.workflow_contract(workflow)
