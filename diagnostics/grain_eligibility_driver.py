"""Opt-in custody controller for one passive historical-wheel diagnostic.

Readiness binds to the committed protocol. No runtime flag bypasses that state.
It never calls the ordinary current-own-wheel helper with historical metadata.
"""
from __future__ import annotations
import argparse
import ast
import base64
import csv
from importlib import metadata, util
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import resource
import selectors
import signal
import stat
import subprocess
import sys
import sysconfig
import time
import zipfile
import hashlib

from grain_eligibility_session import (durable_bytes, durable_directory, run_owned,
    capture_allowed, clean_command, collect_snapshot, publish_snapshot, remember_failure)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "diagnostics/grain_eligibility_protocol.json"
TARGET = "tests/test_live_checkpoints_native.py::test_enabled_public_grain_live_midtransit_native_checkpoint_is_exact"
WHEEL_NAME = "chronicler_agents-0.1.0-cp313-cp313-manylinux_2_34_x86_64.whl"
WHEEL_MEMBER = "chronicler_agents/chronicler_agents.cpython-313-x86_64-linux-gnu.so"
OUTER_NAMES = {"ci-native-wheel/build.json", "chronicler-agents/target/wheels/" + WHEEL_NAME}
PROTECTED = ("src", "scripts", "tests", "chronicler-agents", "pyproject.toml", "uv.lock")
PRIVATE_ENV = ("TMPDIR", "PD_EVIDENCE_DIR", "R007_EVIDENCE_DIR", "Q009_EVIDENCE_DIR")
THREAD_ENV = ("RAYON_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")
OUTPUT_CAP = 256 * 1024
NATIVE_BUNDLE_CAP = 32 * 1024**2

class Refused(ValueError):
    pass

def require(value, message):
    if not value:
        raise Refused(message)

def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()

def sha(data):
    return hashlib.sha256(data).hexdigest()

def strict_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    def bad_constant(value):
        raise Refused("nonfinite JSON")
    return json.loads(data, object_pairs_hook=unique, parse_constant=bad_constant)

def write_once(path, data, cap):
    require(type(data) is bytes and len(data) <= cap, "bounded output")
    return durable_bytes(path, data, cap)

def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], timeout=15)

def file_sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

CENSUS_REASONS = frozenset(("ROOT_NOT_DIRECTORY", "DIRECTORY_IDENTITY_CHANGED",
                            "ENTRY_NOT_REGULAR_OR_LINK"))
CENSUS_SITES = frozenset(("live_private_tmp", "live_output", "closed_private_tmp"))

class CensusRefused(Refused):
    def __init__(self, reason):
        require(reason in CENSUS_REASONS, "registered census reason")
        self.reason = reason
        super().__init__(reason)

def resource_observer_failure(site, error):
    """Bounded parent metadata only: never retain exception messages or paths."""
    require(site in CENSUS_SITES, "registered resource observer site")
    number = getattr(error, "errno", None)
    return {"site": site, "type": type(error).__name__[:64],
            "errno": number if type(number) is int and 0 <= number < 2**31 else None,
            "reason": error.reason if type(error) is CensusRefused else
                      "OS_ERROR" if isinstance(error, OSError) else "OBSERVER_ERROR"}

def observed_resource_charge(paths, site, failures):
    try:
        return sum(tree_charge(path) for path in paths)
    except BaseException as error:
        if not failures:
            failures.append(resource_observer_failure(site, error))
        raise

def tree_charge(path):
    """Descriptor-relative nofollow census under a trusted owned private root.

    Symlinks count only their own logical/allocated bytes. Their target is never
    opened, statted, readlinked or traversed. Directory identities are checked
    after nofollow opens; disappearance and replacement fail closed.
    """
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    def identity(st):
        return st.st_dev, st.st_ino, stat.S_IFMT(st.st_mode)
    def same_directory(before, opened):
        if not stat.S_ISDIR(opened.st_mode) or identity(before) != identity(opened):
            raise CensusRefused("DIRECTORY_IDENTITY_CHANGED")
    def visit(fd):
        total = os.fstat(fd).st_blocks * 512
        with os.scandir(fd) as entries:
            for entry in entries:
                before = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(before.st_mode):
                    child = os.open(entry.name, flags, dir_fd=fd)
                    try:
                        same_directory(before, os.fstat(child))
                        total += visit(child)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
                    total += max(before.st_size, before.st_blocks * 512)
                else:
                    raise CensusRefused("ENTRY_NOT_REGULAR_OR_LINK")
        return total
    before = os.stat(path, follow_symlinks=False)
    if not stat.S_ISDIR(before.st_mode):
        raise CensusRefused("ROOT_NOT_DIRECTORY")
    fd = os.open(path, flags)
    try:
        same_directory(before, os.fstat(fd))
        return visit(fd)
    finally:
        os.close(fd)

def package_map():
    result = {}
    for dist in metadata.distributions():
        raw = dist.metadata["Name"]
        require(type(raw) is str and raw, "distribution name")
        key = raw.lower().replace("_", "-")
        if key == "maturin":
            continue
        require(key not in result, "duplicate normalized distribution")
        result[key] = dist.version
    return result

def source_identity(protocol):
    require(protocol.get("kind") == "grain-eligibility-passive-diagnostic-v1", "protocol kind")
    require(type(protocol.get("state")) is str and protocol["state"] == "READY" and type(protocol.get("activation_allowed")) is bool and protocol["activation_allowed"] is True,
            "UNREADY protocol: separate reviewed readiness child required")
    require(Path.cwd().resolve() == ROOT, "repository cwd")
    require(sys.version_info[:2] == (3, 13), "Python3.13 required")
    require(platform.python_implementation() == "CPython" and platform.machine() == "x86_64", "CPython/x86_64 context")
    require(not any(k in os.environ for k in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_DISABLE_PLUGIN_AUTOLOAD")),
            "unaltered pytest plugin/filter context")
    head = git("rev-parse", "HEAD").decode().strip()
    require(re.fullmatch("[0-9a-f]{40}", head) is not None and head == os.environ.get("GITHUB_SHA"), "actual current diagnostic source")
    protocol_pin = committed_protocol(protocol)
    require(os.environ.get("GITHUB_REF") == "refs/heads/" + protocol["refs"]["run"]
            and os.environ.get("GITHUB_EVENT_NAME") == "push", "dedicated opt-in push only")
    require(os.environ.get("GITHUB_JOB") == "grain-eligibility-diagnostic", "dedicated diagnostic job")
    require(os.environ.get("GITHUB_REPOSITORY") == "YotsuBotfds/Chronicler", "exact repository")
    require(len(os.sched_getaffinity(0)) == 1, "one actual CPU affinity")
    current_run = os.environ.get("GITHUB_RUN_ID", "")
    require(re.fullmatch("[1-9][0-9]*", current_run) is not None
            and os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "first current diagnostic attempt")
    require(int(current_run) != protocol["historical"]["run"], "current and historical runs separate")
    require(git("rev-parse", "HEAD:chronicler-agents").decode().strip() == protocol["historical"]["native_tree"], "historical Native source tree")
    tracked = [x for x in git("ls-files", "-z", "--", *PROTECTED).decode().split("\0") if x]
    require(len(tracked) == protocol["historical"]["protected_files"], "complete protected namespace")
    require(not git("diff", "--name-only", "HEAD", "--", *PROTECTED).strip(), "protected source clean")
    require(not git("ls-files", "--others", "--exclude-standard", "-z", "--", *PROTECTED).strip(), "untracked protected source")
    protected = {}
    for name in tracked:
        p = ROOT / name
        require(p.is_file() and not p.is_symlink(), "regular protected source")
        protected[name] = file_sha(p)
    require(sha(canonical(protected)) == protocol["historical"]["protected_digest"], "complete historical product/test/helper/UV map")
    for name, expected in protocol["code_sha256"].items():
        require(file_sha(ROOT / name) == expected, "diagnostic code pin")
        require(not git("diff", "--name-only", "HEAD", "--", name).strip(), "diagnostic code clean")
    require(file_sha(ROOT / "uv.lock") == protocol["uv_lock_sha256"], "frozen lock")
    test = ROOT / TARGET.split("::", 1)[0]
    require(protocol["target"]["nodeid"] == TARGET, "one fixed target protocol")
    require(file_sha(test) == protocol["target"]["file_sha256"], "original complete Native module")
    test_source = test.read_text()
    functions = [x for x in ast.parse(test_source).body if isinstance(x, ast.FunctionDef) and x.name == TARGET.split("::")[1]]
    require(len(functions) == 1 and sha(ast.get_source_segment(test_source, functions[0]).encode()) == protocol["target"]["function_sha256"],
            "original complete function source")
    require(all(os.environ.get(k) == "1" for k in THREAD_ENV), "one Native/BLAS/OMP worker")
    return {"source_commit": head, "source_tree": git("rev-parse", "HEAD^{tree}").decode().strip(),
            "protocol": protocol_pin,
            "run_id": int(current_run), "attempt": 1, "source_protected_digest": sha(canonical(protected)),
            "historical_source_commit": protocol["historical"]["source"],
            "historical_native_tree": protocol["historical"]["native_tree"],
            "scope": "New diagnostic code; byte-exact historical Python/product/test/UV and Native source; historical compiled wheel"}

def protocol_binding(protocol, raw, committed, git_mode, git_blob, file_mode):
    """Exact canonical object equality distinguishes JSON true/1 and false/0."""
    require(type(raw) is bytes and len(raw) <= 24 * 1024, "bounded raw protocol")
    require(git_mode == "100644" and stat.S_ISREG(file_mode) and not file_mode & 0o111,
            "tracked regular non-executable protocol mode")
    require(raw == committed, "raw protocol must be committed HEAD bytes")
    require(canonical(protocol) == canonical(strict_json(raw)), "admitted protocol object differs with strict JSON types")
    require(type(protocol["state"]) is str and type(protocol["activation_allowed"]) is bool,
            "critical protocol state types")
    return {"path": "diagnostics/grain_eligibility_protocol.json", "bytes": len(raw),
            "sha256": sha(raw), "git_blob": git_blob, "mode": git_mode}

def committed_protocol(protocol):
    before = PROTOCOL.lstat()
    require(stat.S_ISREG(before.st_mode) and not PROTOCOL.is_symlink(), "regular protocol path")
    raw = bounded_capture(PROTOCOL, 24 * 1024)
    after = PROTOCOL.lstat()
    physical = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(physical(before) == physical(after), "protocol changed during admission")
    rows = git("ls-tree", "-z", "HEAD", "--", "diagnostics/grain_eligibility_protocol.json").split(b"\0")
    rows = [x for x in rows if x]
    require(len(rows) == 1, "one committed protocol")
    meta, name = rows[0].split(b"\t", 1)
    mode, kind, blob = meta.decode().split()
    require(kind == "blob" and name == b"diagnostics/grain_eligibility_protocol.json", "committed protocol blob")
    committed = git("show", "HEAD:diagnostics/grain_eligibility_protocol.json")
    return protocol_binding(protocol, raw, committed, mode, blob, before.st_mode)

def load_protocol():
    return strict_json(bounded_capture(PROTOCOL, 24 * 1024))

def safe_zip(data, *, expanded_cap, member_cap, max_members, expected_names=None):
    """Catalogue before reads, then selected/all members with zipfile CRC checks."""
    require(type(data) is bytes, "ZIP byte domain")
    archive = zipfile.ZipFile(io.BytesIO(data))
    infos = archive.infolist()
    require(0 < len(infos) <= max_members, "ZIP member count")
    names = set()
    total = 0
    for item in infos:
        name = item.filename
        parts = name.split("/")
        require(name and name.isascii() and "\0" not in name and "\\" not in name
                and not name.startswith("/") and ":" not in name
                and all(p not in ("", ".", "..") for p in parts), "ZIP path")
        require(name not in names, "duplicate ZIP member")
        names.add(name)
        mode = item.external_attr >> 16
        require(not item.is_dir() and stat.S_IFMT(mode) in (0, stat.S_IFREG), "regular ZIP members only")
        require(not item.flag_bits & 1 and item.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), "ZIP encryption/compression")
        require(0 <= item.file_size <= member_cap and 0 <= item.compress_size <= len(data), "ZIP member bound")
        total += item.file_size
    require(total <= expanded_cap, "ZIP expanded bound")
    if expected_names is not None:
        require(names == set(expected_names), "closed ZIP inventory")
    result = {}
    for item in infos:
        with archive.open(item) as stream:
            body = stream.read(item.file_size + 1)
            require(len(body) == item.file_size and not stream.read(1), "bounded complete ZIP read/CRC")
        result[item.filename] = body
    archive.close()
    return result

def verify_build(build, protocol):
    require(sha(canonical(build)) == protocol["historical"]["build_digest"], "exact producer-reported old build record")
    require(set(build) == {"kind", "identity", "manifest_digest", "producer_job_key"}
            and build["kind"] == "native-shard-current-build-v1"
            and build["producer_job_key"] == "python-native-build", "historical build schema")
    require(build["identity"] == protocol["historical"]["identity"], "complete old identity/context/wheel")
    manifest = strict_json((ROOT / "scripts/testing/native_shards_manifest.json").read_bytes())
    require(build["manifest_digest"] == sha(canonical(manifest)), "old manifest join")
    return build["identity"]

def verify_wheel(wheel, protocol):
    old = protocol["historical"]["identity"]["wheel"]
    require(len(wheel) == old["wheel"]["bytes"] and sha(wheel) == old["wheel"]["sha256"], "whole historical wheel bytes")
    files = safe_zip(wheel, expanded_cap=20 * 1024**2, member_cap=16 * 1024**2, max_members=64)
    require(WHEEL_MEMBER in files and len(files[WHEEL_MEMBER]) == old["installed_native"]["bytes"]
            and sha(files[WHEEL_MEMBER]) == old["installed_native"]["sha256"], "exact Native member")
    records = [n for n in files if n.endswith(".dist-info/RECORD")]
    require(len(records) == 1 and records[0] == "chronicler_agents-0.1.0.dist-info/RECORD", "one wheel RECORD")
    rows = list(csv.reader(io.StringIO(files[records[0]].decode("utf-8"))))
    listed = {}
    for row in rows:
        require(len(row) == 3 and row[0] not in listed, "unique wheel RECORD row")
        listed[row[0]] = row[1:]
    require(set(listed) == set(files), "complete wheel RECORD namespace")
    for name, body in files.items():
        if name == records[0]:
            require(listed[name] == ["", ""], "self RECORD row")
        else:
            encoded = base64.urlsafe_b64encode(hashlib.sha256(body).digest()).rstrip(b"=").decode()
            require(listed[name] == ["sha256=" + encoded, str(len(body))], "wheel RECORD payload hash")
    payload = {n: b for n, b in files.items() if n.startswith("chronicler_agents/")}
    require(payload and all(n.count("/") == 1 for n in payload), "closed flat Native package")
    require(set(payload) >= {WHEEL_MEMBER, "chronicler_agents/__init__.py"}, "compiled package/alias source")
    return payload, {n: {"bytes": len(b), "sha256": sha(b)} for n, b in files.items()}

def verify_archive(data, protocol):
    old = protocol["historical"]
    require(len(data) == old["artifact"]["bytes"] and sha(data) == old["artifact"]["sha256"], "exact outer artifact ZIP bytes before parse")
    files = safe_zip(data, expanded_cap=5 * 1024**2, member_cap=4 * 1024**2,
                     max_members=2, expected_names=OUTER_NAMES)
    build_data = files["ci-native-wheel/build.json"]
    require(len(build_data) <= 64 * 1024, "raw build bound")
    build = strict_json(build_data)
    verify_build(build, protocol)
    wheel = files["chronicler-agents/target/wheels/" + WHEEL_NAME]
    payload, catalogue = verify_wheel(wheel, protocol)
    return build, wheel, payload, catalogue, {"bytes": len(build_data), "sha256": sha(build_data)}

def stream_command(command, env, caps, wall, *, cwd=ROOT, watch=None, cpu_limit=None,
                   as_limit=None, control=None, stage=None, identity=None):
    if control is None:
        # Retained FIRST49 contracts have exactly these two real stdlib argv.
        allowed = [
            [sys.executable, "-c", "import sys;sys.stdout.buffer.write(b'x'*10000)"],
            [sys.executable, "-c", "print('first');raise SystemExit(7)"],
        ]
        require(command in allowed and caps == (128, 128) and wall == 5,
                "unregistered stand-alone subprocess")
        control, stage = Path(cwd) / "stream-control", "registered-pure-stdlib"
    return run_owned(command, env, caps, wall, cwd=cwd, control=control, stage=stage,
                     identity=identity, watch=watch, cpu_limit=cpu_limit, as_limit=as_limit)

def minimal_env():
    # In particular GH_TOKEN/GITHUB_TOKEN/ACTIONS_* credentials never reach the test child.
    allowed = ("PATH", "HOME", "LANG", "LC_ALL", "VIRTUAL_ENV", "LD_LIBRARY_PATH",
               "GITHUB_SHA", "GITHUB_REF", "GITHUB_EVENT_NAME", "GITHUB_JOB",
               "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_REPOSITORY", "RUNNER_TEMP")
    return {k: os.environ[k] for k in allowed if k in os.environ}

def assert_environment(identity, *, installed):
    require(sys.version == identity["python"] and platform.python_implementation() == identity["implementation"]
            and platform.machine() == identity["machine"], "historical interpreter/ABI context")
    actual = package_map()
    expected = dict(identity["packages"])
    if not installed:
        expected.pop("chronicler-agents")
    require(actual == expected, "complete frozen installed package context")
    return actual

def private_root(path):
    path = Path(path).resolve()
    runner = Path(os.environ["RUNNER_TEMP"]).resolve()
    require(path.parent == runner and path.name == "grain-eligibility-diagnostic", "fixed private runner root")
    require(not path.exists(), "private root created once")
    durable_directory(path)
    for name in ("bundle", "control", "pipes", "output", "negative", "tmp", "pd", "r007", "q009", "pycache"):
        durable_directory(path / name)
    return path

def prepare(protocol, path):
    identity = source_identity(protocol)
    old_identity = protocol["historical"]["identity"]
    assert_environment(old_identity, installed=False)
    require(util.find_spec("chronicler_agents") is None, "Native absent before verified historical install")
    work = private_root(path)
    archive_path = work / "bundle/historical-artifact.zip"
    require(not archive_path.exists(), "no download retry")
    fetch_env = minimal_env()
    fetch_env["GH_TOKEN"] = os.environ["GH_TOKEN"]
    command = ["gh", "api", "--hostname", "github.com", "--method", "GET",
               "/repos/YotsuBotfds/Chronicler/actions/artifacts/12976786591/zip"]
    info, streams = stream_command(command, fetch_env, (3881660, 8192), 60,
                                   control=work / "control/gh", stage="gh-artifact", identity=identity)
    # Always retain the first bounded byte domain, including mismatches, once.
    write_once(archive_path, streams[0], 3881661)
    archive_path.chmod(0o400)
    fetch_record = {**info, "command": ["gh", "api", "--hostname", "github.com", "--method", "GET", "PINNED_ARTIFACT_ZIP_ENDPOINT"],
                    "artifact_id": 12976786591, "archive_bytes": len(streams[0]),
                    "archive_sha256": sha(streams[0]), "stderr_text_retained": False,
                    "reference_calls": 0, "bounded_zip_GET_processes": 1}
    write_once(work / "control/fetch.json", canonical(fetch_record), 8192)
    require(clean_command(info), "first artifact transfer custody failed; no retry")
    build, wheel, payload, catalogue, raw_build = verify_archive(streams[0], protocol)
    require(tree_charge(work / "bundle") + len(wheel) + sum(len(b) for b in payload.values()) <= NATIVE_BUNDLE_CAP,
            "historical bundle forecast")
    wheel_path = work / "bundle" / WHEEL_NAME
    write_once(wheel_path, wheel, 4 * 1024**2)
    wheel_path.chmod(0o400)
    install, _ = stream_command(["uv", "pip", "install", "--python", sys.executable, "--no-deps",
                                "--link-mode", "copy", str(wheel_path)],
                               minimal_env(), (8192, 8192), 60,
                               control=work / "control/uv", stage="uv-install", identity=identity)
    write_once(work / "control/install.json", canonical(install), 8192)
    require(clean_command(install), "verified-wheel install custody failed; no fallback")
    installed = installed_payload(payload)
    require(tree_charge(work / "bundle") + sum(x["bytes"] for x in installed.values()) <= NATIVE_BUNDLE_CAP,
            "historical bundle actual")
    assert_environment(old_identity, installed=True)
    require(source_identity(protocol) == identity, "current identity unchanged across custody")
    verification = {"state": "VERIFIED_HISTORICAL_DIAGNOSTIC_ONLY", "current": identity,
                    "historical_identity": old_identity, "raw_build_json": raw_build,
                    "source_format_build_digest": sha(canonical(build)), "wheel_catalogue": catalogue,
                    "installed_payload": installed, "archive": fetch_record,
                    "command_custody": {"gh": info, "uv": install},
                    "claims": {"current_fresh_wheel_CI": False, "feature_PASS": False, "performance": False}}
    write_once(work / "control/verification.json", canonical(verification), 24 * 1024)
    return work

def installed_payload(payload):
    site = Path(sysconfig.get_paths()["platlib"]).resolve()
    package = site / "chronicler_agents"
    require(package.is_dir() and not package.is_symlink(), "Native package in this environment")
    expected_names = {str(PurePosixPath(n).relative_to("chronicler_agents")) for n in payload}
    actual_names = set()
    for p in package.rglob("*"):
        require(not p.is_symlink(), "installed package symlink")
        if p.is_file():
            rel = p.relative_to(package).as_posix()
            # Bytecode is prevented in child; uv may compile only when explicitly asked (not used).
            actual_names.add(rel)
    require(actual_names == expected_names, "complete installed Native package namespace")
    result = {}
    for name, body in payload.items():
        p = site / name
        require(p.is_file() and p.stat().st_size == len(body) and file_sha(p) == sha(body), "installed wheel payload exact before import")
        result[name] = {"bytes": len(body), "sha256": sha(body)}
    spec = util.find_spec("chronicler_agents")
    require(spec is not None and Path(spec.origin).resolve() == package / "__init__.py", "no checkout Native package shadow")
    return result

def compiled_aliases():
    # Import follows complete installed-byte verification; no object construction/getters/schema calls.
    import chronicler_agents as aliases
    import chronicler_agents.chronicler_agents as compiled
    from importlib.machinery import EXTENSION_SUFFIXES
    origin = Path(compiled.__file__).resolve()
    expected = Path(sysconfig.get_paths()["platlib"]).resolve() / WHEEL_MEMBER
    require(origin == expected and str(origin).endswith(tuple(EXTENSION_SUFFIXES)), "actual compiled Native origin")
    names = ("AgentSimulator", "EcologySimulator", "PoliticsSimulator")
    require(all(type(vars(compiled).get(n)) is type and vars(aliases).get(n) is vars(compiled).get(n) for n in names),
            "actual three compiled aliases")
    return {"classes": list(names), "native_sha256": file_sha(origin),
            "native_bytes": origin.stat().st_size, "compiled_origin": "this-venv/" + WHEEL_MEMBER,
            "constructed_simulators": 0, "schema_getter_calls": 0}

def worker(protocol, work):
    source = source_identity(protocol)
    archive = (work / "bundle/historical-artifact.zip").read_bytes()
    build, _, payload, _, _ = verify_archive(archive, protocol)
    installed_payload(payload)
    assert_environment(build["identity"], installed=True)
    require("chronicler_agents" not in sys.modules, "no preloaded Native before custody")
    aliases = compiled_aliases()
    write_once(work / "output/aliases.json", canonical(aliases), 4096)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))
    from grain_eligibility_trace import PassiveTrace, pytest_plugin
    trace = PassiveTrace(ROOT / "src/chronicler/grain_reserves.py",
                         protocol["tick"]["source_sha256"], protocol["tick"]["schema"],
                         work / "output/trace.jsonl", protocol["filters"],
                         {"diagnostic_kind": "PASSIVE-HISTORICAL-GRAIN-TRACE-v1", "current": source,
                          "historical_source": protocol["historical"]["source"],
                          "target": TARGET, "filters": protocol["filters"],
                          "schema": protocol["tick"]["schema"],
                          "granary_target_and_grain": "UNAVAILABLE: no product-object field reads",
                          "context": "one isolated original node; full-owner order history differs"})
    plugin = pytest_plugin(trace, TARGET)
    import pytest
    start = time.monotonic()
    code = pytest.main(["-q", "--tb=short", "-o", "cache_dir=" + str(work / "tmp/cache"),
                        "--basetemp", str(work / "tmp/pytest"), "--junitxml", str(work / "output/native.xml"),
                        TARGET], plugins=[plugin])
    after_source = source_identity(protocol)
    installed_payload(payload)
    same_source = after_source == source
    phases = plugin.case_reports
    expected_phases = [x["when"] for x in phases] == ["setup", "call", "teardown"]
    no_skip = expected_phases and all(x["outcome"] in ("passed", "failed") for x in phases)
    result = {"state": "DIAGNOSTIC_COMPLETE" if trace.complete and same_source and no_skip
              and plugin.calls == 1 and plugin.trace_close_error is None else "DIAGNOSTIC_INCOMPLETE",
              "pytest_exit": int(code), "case_reports": phases, "collection": plugin.collection,
              "trace_complete": trace.complete, "trace_close_error": plugin.trace_close_error,
              "source_unchanged": same_source, "call_wall_seconds": time.monotonic() - start,
              "assertion_outcome": "PASS_NONREPRODUCTION" if int(code) == 0 else "FAIL_RETAINED",
              "scope": "Passive actual gates in one isolated test; no feature, fix, original full-owner reproduction, or performance qualification"}
    write_once(work / "output/test-result.json", canonical(result), 8192)
    return 0 if result["state"] == "DIAGNOSTIC_COMPLETE" else 2

def bounded_capture(path, cap):
    before = Path(path).lstat()
    require(stat.S_ISREG(before.st_mode), "regular snapshot member")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(fd)
        require((opened.st_dev, opened.st_ino, opened.st_size) == (before.st_dev, before.st_ino, before.st_size)
                and opened.st_size <= cap, "bounded stable snapshot member")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            body = stream.read(cap + 1)
        after = os.fstat(fd)
        require(len(body) == before.st_size and len(body) <= cap
                and (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                == (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns),
                "complete unchanged snapshot member")
        return body
    finally:
        os.close(fd)

def emit_raw_allowed(value):
    require(type(value) is bool, "boolean publication gate")
    fd = os.open(os.environ["GITHUB_OUTPUT"], os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), "runner output is regular")
        body = b"raw_allowed=true\n" if value else b"raw_allowed=false\n"
        require(os.write(fd, body) == len(body), "complete runner output")
        os.fsync(fd)
    finally:
        os.close(fd)

def run(protocol, path):
    emit_raw_allowed(False)
    source = source_identity(protocol)
    work = Path(path).resolve()
    require(work == Path(os.environ["RUNNER_TEMP"]).resolve() / "grain-eligibility-diagnostic", "prepared private path")
    control = work / "control"
    verification = strict_json((control / "verification.json").read_bytes())
    require(verification["state"] == "VERIFIED_HISTORICAL_DIAGNOSTIC_ONLY"
            and verification["current"] == source
            and all(clean_command(verification["command_custody"][stage]) for stage in ("gh", "uv")),
            "same prepared custody/current source")
    # Parent intent is exclusive and durably fsynced before any worker launch.
    write_once(control / "invocation.json", canonical({"state": "ATTEMPTED", "target": TARGET,
               "current": source, "automatic_retry": False}), 4096)
    env = minimal_env()
    env.update({k: "1" for k in THREAD_ENV})
    env.update({"PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": str(ROOT / "src") + os.pathsep + str(ROOT),
                "PYTHONPYCACHEPREFIX": str(work / "pycache"),
                "TMPDIR": str(work / "tmp"), "PD_EVIDENCE_DIR": str(work / "pd"),
                "R007_EVIDENCE_DIR": str(work / "r007"), "Q009_EVIDENCE_DIR": str(work / "q009")})
    watched = [work / n for n in ("tmp", "pd", "r007", "q009", "pycache", "negative")]
    resource_failures = []
    info, streams = stream_command([sys.executable, "-B", str(Path(__file__).resolve()), "worker", "--work", str(work)],
                                  env, (16 * 1024, 16 * 1024), 120, cpu_limit=60, as_limit=2 * 1024**3,
                                  control=control / "worker", stage="native-worker", identity=source,
                                  watch=lambda: observed_resource_charge(watched, "live_private_tmp", resource_failures) <= 64 * 1024**2
                                  and observed_resource_charge([work / "output"], "live_output", resource_failures) <= OUTPUT_CAP)
    # These are parent-owned pipe prefixes, never child filesystem reads.
    write_once(work / "pipes/stdout.log", streams[0], 16 * 1024 + 1)
    write_once(work / "pipes/stderr.log", streams[1], 16 * 1024 + 1)
    info["stream_prefix_truncated"] = [len(streams[i]) > 16 * 1024 for i in (0, 1)]
    info["context"] = "one original node/historical wheel; no retry; trusted same-session Linux scope"
    bodies, errors = {}, []
    if capture_allowed(info):
        # Every child lookup/read/hash below follows positive waited closure.
        try:
            info["temporary_charged_bytes_at_close"] = observed_resource_charge(watched, "closed_private_tmp", resource_failures)
        except BaseException as error:
            errors.append({"stage": "closed_resource_census", "type": type(error).__name__})
            info["temporary_charged_bytes_at_close"] = "UNOBSERVED_CENSUS_ERROR"
        requests = [(name, work / "output" / name, cap) for name, cap in (
            ("aliases.json", 4096), ("trace.jsonl", 65536),
            ("native.xml", 32768), ("test-result.json", 8192))]
        bodies, capture_errors = collect_snapshot(info, requests, reader=bounded_capture)
        errors.extend(capture_errors)
        try:
            test = strict_json(bodies["test-result.json"])
            info["test_result_state"] = test["state"]
            info["diagnostic_state"] = test["state"] if clean_command(info) else "DIAGNOSTIC_INCOMPLETE"
        except BaseException as error:
            errors.append({"stage": "result_parse", "type": type(error).__name__})
            info["diagnostic_state"] = "DIAGNOSTIC_INCOMPLETE"
            info["test_result_state"] = "ABSENT_OR_INVALID"
    else:
        # No exists/stat/rglob/read/hash/rename on ANY child output path here.
        info["diagnostic_state"] = "UNKNOWN"
        info["test_result_state"] = "UNOBSERVED_CUSTODY"
        info["temporary_charged_bytes_at_close"] = "UNOBSERVED_CUSTODY"
    if resource_failures:
        info["resource_observer_failure"] = resource_failures[0]
    info["pin_errors"] = errors
    if errors:
        remember_failure(info, "CHILD_CAPTURE_INCOMPLETE", "capture")
        info["diagnostic_state"] = "DIAGNOSTIC_INCOMPLETE"
    info["snapshot_pins"] = {name: {"bytes": len(raw), "sha256": sha(raw)} for name, raw in bodies.items()}
    # Durable parent endpoint precedes snapshot and the workflow true gate.
    write_once(control / "controller.json", canonical(info), 16 * 1024)
    if capture_allowed(info) and not errors and info["streams_complete"]:
        try:
            expected = {"aliases.json", "trace.jsonl", "native.xml", "test-result.json"}
            require(set(bodies) == expected, "closed child snapshot inventory")
            bodies["stdout.log"], bodies["stderr.log"] = streams
            parent_names = ("fetch.json", "install.json", "verification.json", "invocation.json", "controller.json")
            for name in parent_names:
                bodies[name] = bounded_capture(control / name, 24 * 1024)
            for stage in ("gh", "uv", "worker"):
                for name in ("launch-intent.json", "launch-started.json", "endpoint.json"):
                    flat = stage + "-" + name
                    bodies[flat] = bounded_capture(control / stage / name, 8192)
            expected = (expected | {"stdout.log", "stderr.log"} | set(parent_names)
                        | {stage + "-" + name for stage in ("gh", "uv", "worker")
                           for name in ("launch-intent.json", "launch-started.json", "endpoint.json")})
            published = publish_snapshot(work / "publication", info, bodies, expected)
            require(published, "complete proven snapshot required")
            # Snapshot is complete/durable; no later code mutates its files.
            emit_raw_allowed(True)
        except BaseException as error:
            write_once(control / "publication-error.json", canonical({
                "state": "DIAGNOSTIC_INCOMPLETE", "type": type(error).__name__,
                "first_failure": info.get("first_failure"), "raw_allowed": False}), 4096)
            return 2
    else:
        return 2
    return 0 if info["diagnostic_state"] == "DIAGNOSTIC_COMPLETE" else 2

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("admit", "prepare", "run", "worker"))
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args(argv)
    protocol = load_protocol()
    source_identity(protocol)
    if args.command == "admit":
        assert_environment(protocol["historical"]["identity"], installed=False)
        require(util.find_spec("chronicler_agents") is None, "fresh locked environment has no Native package")
        return 0
    if args.command == "prepare":
        prepare(protocol, args.work)
        return 0
    if args.command == "run":
        return run(protocol, args.work)
    return worker(protocol, args.work)

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        label = type(error).__name__
        print("diagnostic refusal type: " + label, file=sys.stderr)
        try:
            parser = argparse.ArgumentParser(add_help=False)
            parser.add_argument("command")
            parser.add_argument("--work", type=Path, required=True)
            args, _ = parser.parse_known_args()
            fixed = Path(os.environ["RUNNER_TEMP"]).resolve() / "grain-eligibility-diagnostic"
            if args.work.resolve() == fixed:
                if args.command == "worker":
                    destination = fixed / "output/worker-failure.json"
                else:
                    destination = fixed / "control/parent-failure.json"
                # Parent never looks at the child namespace on an unknown path.
                if destination.parent.is_dir():
                    write_once(destination, canonical({"state": "DIAGNOSTIC_INCOMPLETE",
                               "command": args.command, "type": label,
                               "message_not_retained": True, "retry": False}), 4096)
        except Exception:
            pass
        raise SystemExit(2)
