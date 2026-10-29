#!/usr/bin/env python3
"""Dormant bounded owner for the fixed genuine forecast study.

No activation at import. Stock runner/CLI alone owns simulation and restoration.
Selected low-level file/runtime helpers retain the reviewed4164 source bodies;
C60/27f session/process and R44/D2 helpers are loaded from exact donor bytes.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import resource
import runpy
import shutil
import stat
import sys
import time
import types

EXECUTION_APPROVAL = None
PYTHON = "3.13.17"
UV = "0.13.6"
REPOSITORY = "YotsuBotfds/Chronicler"
ACTIVE_BRANCH = "lead/cloud-forecast-local-credibility-h26-20261029"
WORKFLOW_PATH = ".github/workflows/forecast-credibility-study.yml"
JOB_KEY = "forecast-credibility-study"
GIB = 1024**3
CAPS = {key: "1" for key in ("BLIS_NUM_THREADS", "CARGO_BUILD_JOBS", "GOTO_NUM_THREADS", "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "PYTHON_CPU_COUNT",
        "RAYON_NUM_THREADS", "RUST_TEST_THREADS", "VECLIB_MAXIMUM_THREADS")}
CAPS.update(PYTHONHASHSEED="0", OPENBLAS_THREAD_TIMEOUT="16")

class Refused(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise Refused(message)

def regular(path):
    path = Path(path)
    require(path.is_absolute(), "absolute path required")
    for parent in reversed(path.parents):
        require(not parent.is_symlink(), "symlink ancestor refused")
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and not path.is_symlink(), "regular unique input")
    return info


def sha(path):
    regular(path)
    hashed = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): hashed.update(block)
    return hashed.hexdigest()


def write(path, value, limit=8 * 1024**2):
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    require(len(raw) <= limit, "metadata byte cap")
    temporary = path.with_name(path.name + ".pending")
    require(not temporary.exists() and not temporary.is_symlink(), "metadata temporary occupied")
    with temporary.open("xb") as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def load_module(path, name, expected):
    require(name not in sys.modules, "control module already loaded")
    info = regular(path)
    require(info.st_size <= 128 * 1024, "control source cap")
    with path.open("rb") as stream: raw = stream.read(128 * 1024 + 1)
    require(len(raw) <= 128 * 1024 and hashlib.sha256(raw).hexdigest() == expected, "control source identity")
    module = types.ModuleType(name); module.__file__ = str(path)
    sys.modules[name] = module
    try: exec(compile(raw, str(path), "exec"), module.__dict__)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def package_digest(source):
    folder = source / "src/chronicler"
    rows, hashed, total = [], hashlib.sha256(), 0
    for path in sorted(folder.rglob("*.py")):
        info = regular(path); total += info.st_size
        require(len(rows) < 181 and total <= 5 * 1024**2, "source package bounds")
        relative = path.relative_to(folder).as_posix()
        content = sha(path)
        rows.append({"path": relative, "sha256": content})
        hashed.update(relative.encode() + b"\0" + content.encode() + b"\n")
    require(len(rows) == 181, "source package file count")
    return hashed.hexdigest(), rows


def source_files(source, names):
    """Closed tracked-file witness, excluding Git's mutable administration."""
    require(type(names) is list and 0 < len(names) <= 3000 and len(set(names)) == len(names), "tracked source file count")
    rows, total = {}, 0
    for name in names:
        require(type(name) is str and name and not name.startswith("/") and "\\" not in name
                and all(part not in ("", ".", "..", ".git") for part in name.split("/")), "tracked source path")
        path = source / name; info = regular(path); total += info.st_size
        require(total <= 64 * 1024**2, "tracked source byte cap")
        rows[name] = {"bytes": info.st_size, "sha256": sha(path)}
    return rows


def cpu_seconds():
    own, waited = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    return own.ru_utime + own.ru_stime + waited.ru_utime + waited.ru_stime


def module_origins(source, prefix):
    for name, module in tuple(sys.modules.items()):
        if name == "chronicler" or name.startswith("chronicler."):
            path = getattr(module, "__file__", None)
            require(path is not None and Path(path).resolve().is_relative_to(source / "src/chronicler"),
                    "wrong producer module origin")
        if name == "chronicler_agents" or name.startswith("chronicler_agents."):
            path = getattr(module, "__file__", None)
            require(path is not None and Path(path).resolve().is_relative_to(prefix), "native prefix origin")


def runtime_file(value):
    path = Path(value).resolve()
    before = path.stat()
    require(stat.S_ISREG(before.st_mode), "runtime regular file")
    hashed = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): hashed.update(block)
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_nlink)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_nlink), "runtime file changed")
    return {"path": str(path), "bytes": after.st_size, "sha256": hashed.hexdigest(), "nlink": after.st_nlink}


def loader_identity(*, config=None, base_prefix=None, environment=None):
    if config is None:
        import sysconfig
        config = {name: sysconfig.get_config_var(name) for name in ("LIBDIR", "LDLIBRARY")}
    base_prefix = Path(sys.base_prefix if base_prefix is None else base_prefix).resolve()
    environment = os.environ if environment is None else environment
    directory = base_prefix / "lib"
    require(type(config["LIBDIR"]) is str and Path(config["LIBDIR"]) == directory
            and not directory.is_symlink(), "selected Python LIBDIR")
    require(config["LDLIBRARY"] in ("libpython3.13.so", "libpython3.13.so.1.0"), "selected Python library name")
    require(environment.get("LD_PRELOAD", "") == "" and environment.get("DYLD_LIBRARY_PATH", "") == ""
            and environment.get("LD_LIBRARY_PATH", "") in ("", str(directory)), "unexpected inherited loader path")
    actual = (directory / config["LDLIBRARY"]).resolve()
    require(actual.parent == directory and actual.is_file(), "selected Python library identity")
    return {"LIBDIR": str(directory), "LDLIBRARY": config["LDLIBRARY"], "actual": runtime_file(actual),
            "child_LD_LIBRARY_PATH": str(directory)}


def runtime_flags():
    value = {name: getattr(sys.flags, name) for name in
             ("safe_path", "no_user_site", "ignore_environment", "isolated", "hash_randomization")}
    value.update(cpu_count=os.cpu_count(), cpu_count_option=sys._xoptions.get("cpu_count"))
    require(value["safe_path"] is True and value["no_user_site"] == 1
            and value["ignore_environment"] == value["isolated"] == value["hash_randomization"] == 0
            and value["cpu_count"] == 1 and value["cpu_count_option"] == "1"
            and os.environ.get("PYTHONHASHSEED") == "0", "actual interpreter hash/isolation/CPU flags")
    return value


def child_environment():
    # Closed nonsecret inheritance; input transport alone receives GH_TOKEN.
    names = ("PATH", "HOME", "LANG", "LC_ALL", "TZ", "SSL_CERT_FILE", "SSL_CERT_DIR",
             "GITHUB_ACTIONS", "RUNNER_ENVIRONMENT", "GITHUB_REPOSITORY", "GITHUB_EVENT_NAME",
             "GITHUB_REF", "GITHUB_WORKFLOW_REF", "GITHUB_JOB", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA", "GITHUB_RUN_ID")
    env = {key: os.environ[key] for key in names if key in os.environ}
    env.update(CAPS, PYTHONDONTWRITEBYTECODE="1", UV_NO_PROGRESS="1", UV_LINK_MODE="copy", UV_NO_CACHE="1")
    return env


def python_command(executable, *arguments):
    # -I implies -E and would ignore the hashseed/cpu environment. Safe-path
    # and no-user-site are explicit, with actual flags checked in each child.
    return [str(executable), "-P", "-s", "-B", "-X", "cpu_count=1", *arguments]


def inventory(root, *, max_bytes=2 * GIB, max_files=4096, authority=(), guard=lambda: None):
    """Bounded descriptor traversal/hash after owned quiescence; never follows links."""
    require(set(authority) <= {"result.json", "terminal.json", "terminal-failure.json"}, "authority exclusion set")
    rows, total, visited = {}, 0, 0
    def visit(folder, relative, depth=0):
        nonlocal total, visited
        require(depth <= 64, "inventory directory depth")
        with os.scandir(folder) as entries:
            for entry in entries:
                guard(); visited += 1
                require(visited <= 10000, "inventory entry cap")
                require(entry.name not in (".", "..") and "/" not in entry.name, "inventory component")
                name = (relative + "/" if relative else "") + entry.name
                if not relative and name in authority:
                    require(regular(root / name).st_size <= 8 * 1024**2, "authority bound")
                    continue
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    descriptor = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=folder)
                    try:
                        opened = os.fstat(descriptor)
                        require((opened.st_dev, opened.st_ino) == (info.st_dev, info.st_ino), "directory changed")
                        visit(descriptor, name, depth + 1)
                    finally: os.close(descriptor)
                else:
                    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "inventory nonregular/alias")
                    require(len(rows) < max_files and total + info.st_size <= max_bytes, "inventory cap")
                    descriptor = os.open(entry.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=folder)
                    try:
                        before = os.fstat(descriptor)
                        require((before.st_dev, before.st_ino) == (info.st_dev, info.st_ino)
                                and before.st_nlink == 1, "inventory identity")
                        hashed, size = hashlib.sha256(), 0
                        while block := os.read(descriptor, 1024 * 1024):
                            guard(); size += len(block); hashed.update(block)
                        after = os.fstat(descriptor)
                        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_nlink)
                                == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_nlink)
                                and size == before.st_size, "inventory changed")
                    finally: os.close(descriptor)
                    rows[name] = {"bytes": size, "sha256": hashed.hexdigest()}; total += size
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: visit(descriptor, "")
    finally: os.close(descriptor)
    return {"files": rows, "file_count": len(rows), "bytes": total}


CONTROL_FILES = (
    "scripts/forecast_credibility_study.py", "scripts/forecast_credibility_owner.py",
    "scripts/forecast_credibility_readout.py", "scripts/forecast_credibility_transport.py",
    "scripts/exact_near_screen_session.py", "scripts/exact_near_screen_process.py",
    "scripts/wealth_floor_build_resources.py", "scripts/wealth_floor_hosted_deployment.py",
    "scripts/forecast_credibility_publish.py", "tests/test_forecast_credibility_study.py",
    "tests/test_forecast_credibility_readout.py",
    "tests/test_forecast_credibility_publication.py",
    "scripts/run_python_oracle_checks.py", "scripts/testing/native_shards_manifest.json",
    "docs/experiments/forecast-credibility-inputs.json", "docs/experiments/forecast-credibility-jobs.json",
    "docs/experiments/forecast-credibility-controls-local-credibility.json",
    "docs/experiments/forecast-credibility-controls-withheld.json",
    "docs/experiments/forecast-credibility-registration.md", "docs/experiments/forecast-credibility-study.yml.inactive",
    "docs/experiments/forecast-credibility-source-pins.json",
)


def control_pins(control):
    return {name: {"bytes": regular(control / name).st_size, "sha256": sha(control / name)} for name in CONTROL_FILES}


def modules(control):
    path = control / "docs/experiments/forecast-credibility-inputs.json"
    require(regular(path).st_size <= 65536, "input registration bound")
    # The later reviewed activation child supplies this constant and exact CI
    # binding. CLI arguments cannot override either gate.
    config = json.loads(path.read_bytes())
    require(config.get("execution_approval") == EXECUTION_APPROVAL and EXECUTION_APPROVAL is not None,
            "registered study execution remains held")
    core = load_module(control / "scripts/forecast_credibility_study.py", "_forecast_study", sha(control / "scripts/forecast_credibility_study.py"))
    config = core.strict_json(path.read_bytes())
    pin_path = control / "docs/experiments/forecast-credibility-source-pins.json"
    require(regular(pin_path).st_size <= 65536, "registered source pin bytes")
    pins = core.strict_json(pin_path.read_bytes())
    excluded = {"docs/experiments/forecast-credibility-source-pins.json", "docs/experiments/forecast-credibility-registration.md"}
    require(type(pins) is dict and set(pins) == set(CONTROL_FILES) - excluded, "closed registered control source set")
    require(all(pins[name] == {"bytes": regular(control / name).st_size, "sha256": sha(control / name)} for name in pins),
            "registered literal code/jobs/caps/bindings unchanged")
    protocol = control / "docs/experiments/forecast-credibility-registration.md"
    require(regular(protocol).st_size <= 65536
            and ("Source manifest SHA-256: `" + sha(pin_path) + "`") in protocol.read_text(), "protocol binds exact source manifest")
    binding = core.validate_binding(config["binding"])
    jobs = core.validate_jobs(core.strict_json((control / "docs/experiments/forecast-credibility-jobs.json").read_bytes()))
    require(jobs == core.JOBS and CAPS == core.CAPS and REPOSITORY == core.REPOSITORY
            and WORKFLOW_PATH == core.STUDY_WORKFLOW and JOB_KEY == core.STUDY_JOB and ACTIVE_BRANCH == core.STUDY_BRANCH,
            "literal jobs/thread/current job policy")
    for suffix, expected in (("local-credibility", {"preparation_policy": "local_credibility"}),
                             ("withheld", {"policy": "withhold", "preparation_policy": "local_credibility"})):
        require(core.strict_json((control / ("docs/experiments/forecast-credibility-controls-" + suffix + ".json")).read_bytes()) == expected,
                "frozen source-owned control file")
    owned = {}
    for name in ("wealth_floor_build_resources", "exact_near_screen_session", "exact_near_screen_process", "wealth_floor_hosted_deployment"):
        selected = config["helper_pins"][name + ".py"]
        helper_path = control / "scripts" / (name + ".py")
        require(regular(helper_path).st_size == selected["bytes"], "exact donor helper bytes")
        owned[name] = load_module(helper_path, name, selected["sha256"])
    transport = load_module(control / "scripts/forecast_credibility_transport.py", "_forecast_transport", config["transport_donor_sha256"])
    reader = load_module(control / "scripts/forecast_credibility_readout.py", "_forecast_readout", sha(control / "scripts/forecast_credibility_readout.py"))
    return core, reader, transport, owned, config, binding, jobs


def context(environment):
    require(environment.get("GITHUB_ACTIONS") == "true" and environment.get("RUNNER_ENVIRONMENT") == "github-hosted"
            and environment.get("GITHUB_REPOSITORY") == REPOSITORY and environment.get("GITHUB_EVENT_NAME") == "push"
            and environment.get("GITHUB_REF") == "refs/heads/" + ACTIVE_BRANCH
            and environment.get("GITHUB_WORKFLOW_REF") == REPOSITORY + "/" + WORKFLOW_PATH + "@refs/heads/" + ACTIVE_BRANCH
            and environment.get("GITHUB_JOB") == JOB_KEY and environment.get("GITHUB_RUN_ATTEMPT") == "1", "closed hosted first-attempt context")
    source = environment.get("GITHUB_SHA", "")
    require(len(source) == 40 and all(c in "0123456789abcdef" for c in source), "control source SHA")
    run = environment.get("GITHUB_RUN_ID", "")
    require(run.isascii() and run.isdecimal() and int(run) > 0, "control run identity")
    return {key: environment[key] for key in ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_WORKFLOW_REF", "GITHUB_JOB")}


def clock_producer(observed_context):
    return {"repository": REPOSITORY, "source": observed_context["GITHUB_SHA"],
            "run_id": int(observed_context["GITHUB_RUN_ID"]), "attempt": 1,
            "workflow": WORKFLOW_PATH, "job": JOB_KEY, "event": "push"}


def observe_job_clock(core, connection, producer, boot_id, *, monotonic=time.monotonic, utcnow=None):
    """Two closed current-run metadata reads; no artifact or product access."""
    require(type(producer) is dict and type(producer.get("run_id")) is int and producer["run_id"] > 0,
            "closed current run clock endpoint")
    utcnow = (lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")) if utcnow is None else utcnow
    remaining = 2 * 1024**2
    def read(suffix):
        nonlocal remaining
        with connection.api(suffix) as response:
            raw = response.read(remaining + 1)
            require(len(raw) <= remaining, "current job clock metadata byte cap")
            remaining -= len(raw)
            dated = response.headers.get("Date")
            aged = response.headers.get("Age")
        connection.check()
        return core.strict_json(raw), dated, aged
    run, _run_date, run_age = read("/actions/runs/" + str(producer["run_id"]))
    before = monotonic()
    utc_before = utcnow()
    jobs, http_date, http_age = read("/actions/runs/" + str(producer["run_id"]) + "/jobs?filter=latest&per_page=100")
    utc_after = utcnow()
    after = monotonic()
    return core.admit_job_clock(producer, run, jobs, http_date=http_date,
            http_age=http_age, run_http_age=run_age, utc_before=utc_before, utc_after=utc_after,
            monotonic_before=before, monotonic_after=after, boot_id=boot_id)


def tighten_deadlines(supervisor, selected):
    """Tighten every donor deadline consumer without mutating donor code."""
    require(type(selected) in (int, float) and selected > 0
            and selected <= supervisor.overall_deadline, "owner clock only tightens deadline")
    supervisor.overall_deadline = selected
    supervisor.deadline = min(supervisor.deadline, selected - 25)
    require(supervisor.deadline < supervisor.overall_deadline, "supervisor cleanup reserve")


def paths(args):
    roots = [args.control, args.baseline, args.candidate, args.prefix, args.root]
    require(all(isinstance(path, Path) and path.is_absolute() and path == path.resolve()
                and not path.is_symlink() and all(not parent.is_symlink() for parent in path.parents) for path in roots), "canonical absolute roots")
    require(len(set(roots)) == len(roots) and all(not left.is_relative_to(right) for left in roots for right in roots if left != right), "disjoint study roots")
    require(Path(__file__).resolve() == args.control / "scripts/forecast_credibility_owner.py", "actual controller origin")


def runtime_files():
    return {"python": runtime_file(sys.executable), "libpython": loader_identity()["actual"]}


def actual_runtime(source, prefix, expected, native, admitted=None):
    require(platform.python_version() == PYTHON and platform.python_implementation() == "CPython"
            and Path(sys.prefix).resolve() == prefix, "registered fresh interpreter")
    require(runtime_flags() and len(os.sched_getaffinity(0)) == 1
            and all(os.environ.get(k) == v for k, v in CAPS.items()), "actual one-CPU/runtime caps")
    require(not any(name == "chronicler" or name.startswith(("chronicler.", "chronicler_agents")) for name in sys.modules), "project/native import before producer origin")
    require(package_digest(source)[0] == expected["package_digest"], "actual producer package before import")
    sys.path.insert(0, str(source / "src"))
    import importlib
    from importlib.machinery import EXTENSION_SUFFIXES
    import chronicler_agents as public
    from chronicler.batch_manifest import source_identity, native_identity, environment_identity
    compiled = importlib.import_module("chronicler_agents.chronicler_agents")
    require(str(compiled.__file__).endswith(tuple(EXTENSION_SUFFIXES)), "real compiled submodule")
    classes = [getattr(compiled, name) for name in ("AgentSimulator", "EcologySimulator", "PoliticsSimulator")]
    require(all(isinstance(cls, type) and cls is getattr(public, name) for cls, name in zip(classes,
                ("AgentSimulator", "EcologySimulator", "PoliticsSimulator"))), "actual compiled classes")
    compiled_path = Path(compiled.__file__).resolve()
    require(sha(compiled_path) == native["sha256"] and regular(compiled_path).st_size == native["bytes"], "installed identified native bytes")
    schemas = {name: list(cls.checkpoint_schema()) for name, cls in zip(("AgentSimulator", "EcologySimulator", "PoliticsSimulator"), classes)}
    require(all(type(row) is list and len(row) == 3 and type(row[0]) is int and type(row[1]) is str
                and type(row[2]) is str and len(row[2]) <= 65536 for row in schemas.values()), "actual full schema tuple shapes")
    if admitted is not None: require(schemas == admitted["schemas"], "admitted full native tuples remain exact")
    identity = {"source": source_identity(), "native": native_identity(), "environment": environment_identity()}
    require(identity["source"]["git_sha"] == expected["source"]
            and identity["source"]["package_digest"] == expected["package_digest"]
            and identity["native"].get("sha256") == native["sha256"], "actual source/native identity")
    module_origins(source, prefix)
    return identity, schemas, str(compiled_path)


def pure_preflight(control, result):
    """Hosted before native installation/input admission. Never a World test."""
    import importlib.abc
    import io
    from xml.etree import ElementTree as ET
    before, blocked = control_pins(control), []
    class Guard(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split(".")[0] in {"chronicler", "chronicler_agents", "numpy", "pyarrow"}:
                blocked.append({"kind": "import", "name": fullname}); raise Refused("project/native import in pure preflight")
    def audit(event, _arguments):
        if event.startswith("socket.") or event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.fork"}:
            blocked.append({"kind": "process/network", "event": event}); raise Refused("child/network in pure preflight")
    sys.meta_path.insert(0, Guard()); sys.addaudithook(audit)
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    import pytest
    junit = result.parent / "junit.xml"
    status = pytest.main(["-q", "-p", "no:cacheprovider", "--noconftest", "--rootdir=" + str(control), "--confcutdir=" + str(control),
                         "--basetemp=" + str(result.parent / "fixtures"), "--junitxml=" + str(junit),
                         str(control / "tests/test_forecast_credibility_study.py"),
                         str(control / "tests/test_forecast_credibility_readout.py"),
                         str(control / "tests/test_forecast_credibility_publication.py")])
    cases = ET.parse(junit).findall(".//testcase")
    after = control_pins(control)
    loaded = [name for name in sys.modules if name.split(".")[0] in {"chronicler", "chronicler_agents", "numpy", "pyarrow"}]
    passed = sum(not any(case.find(tag) is not None for tag in ("failure", "error", "skipped")) for case in cases)
    expected = json.loads((control / "docs/experiments/forecast-credibility-inputs.json").read_bytes())["preflight_cases"]
    receipt = {"complete": status == 0 and len(cases) == passed == expected and not blocked and not loaded and before == after,
               "tests": len(cases), "passes": passed, "pytest_exit": int(status), "blocked_operations": blocked,
               "project_native_imports": loaded, "source_unchanged": before == after, "before": before, "after": after,
               "scope": "whole new metadata/fake module only; zero genuine project/native/World/checkpoint execution"}
    write(result, receipt)
    require(receipt["complete"], "hosted bounded pure preflight failed")


def child(args):
    require(EXECUTION_APPROVAL is not None, "source-only execution approval is null")
    core, reader, transport, owned, config, binding, jobs = modules(args.control)
    cpu_cap = 5 if args.child == "job-clock" else 30 if args.child == "preflight" else 60 if args.child == "bootstrap" else 100
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_cap, cpu_cap))
    resource.setrlimit(resource.RLIMIT_AS, (4 * GIB, 4 * GIB))
    resource.setrlimit(resource.RLIMIT_FSIZE, (128 * 1024**2, 128 * 1024**2))
    runtime_flags()
    if args.child == "preflight":
        pure_preflight(args.control, args.result); return
    if args.child == "job-clock":
        resource.setrlimit(resource.RLIMIT_AS, (128 * 1024**2, 128 * 1024**2))
        resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024**2, 2 * 1024**2))
        observed_context = context(os.environ)
        def admission(_phase, disk, ram):
            observed = owned["wealth_floor_build_resources"].memory_admission()
            require(shutil.disk_usage(args.root).free >= disk * GIB and observed["available_bytes"] >= ram * GIB,
                    "job clock resource floor")
        connection = transport.Transport(os.environ.get("GH_TOKEN", ""), types.SimpleNamespace(admission=admission),
                                         time.monotonic() + 15)
        result = observe_job_clock(core, connection, clock_producer(observed_context),
                owned["exact_near_screen_session"].boot_id().strip())
        write(args.result, result, 2 * 1024**2); return
    if args.child in ("input-before", "input-after"):
        def admission(_phase, disk, ram):
            observed = owned["wealth_floor_build_resources"].memory_admission()
            require(shutil.disk_usage(args.root).free >= disk * GIB and observed["available_bytes"] >= ram * GIB, "input child resource floor")
        connection = transport.Transport(os.environ.get("GH_TOKEN", ""), types.SimpleNamespace(admission=admission), time.monotonic() + 120)
        pin = transport.ArtifactPin(**binding["native"]["producer"])
        result = {"metadata": connection.metadata(pin), "actual_Worlds": 0}
        if args.child == "input-before":
            archive = args.root / "inputs/wheel.zip"
            connection.download(pin, archive)
            result["wheel"] = transport.stage_wheel(archive, args.root / "inputs" / config["wheel"]["filename"], config)
        write(args.result, result); return
    if args.child == "readout":
        registration = core.strict_json((args.root / "registration.json").read_bytes())
        records = core.strict_json((args.root / "roles.json").read_bytes())
        report = reader.read_study(args.root, registration, records)
        write(args.result, report)
        require(report.get("complete") is True, "mechanical readout rejected study")
        return
    source = args.candidate if args.child == "bootstrap" else (args.baseline if jobs[args.index]["source_alias"] == "baseline" else args.candidate)
    expected = binding["candidate"] if source == args.candidate else binding["baseline"]
    admitted = None if args.child == "bootstrap" else core.strict_json((args.root / "admission.json").read_bytes())
    identity, schemas, native_path = actual_runtime(source, args.prefix, expected, binding["native"], admitted)
    observed_runtime = runtime_files()
    if args.child == "bootstrap":
        write(args.result, {"identity": identity, "schemas": schemas, "native_file": native_path,
                            "runtime_files": observed_runtime, "runtime_flags": runtime_flags(), "actual_Worlds": 0})
        return
    require(args.child == "role" and type(args.index) is int and 0 <= args.index < 14, "closed simulation role")
    spec = jobs[args.index]; folder = args.root / "roles" / spec["name"]
    job_path = folder / "job.json"; job = core.strict_json(job_path.read_bytes())
    before = identity
    runner_path = source / "scripts/run_expansion_experiment.py"
    try:
        if job["entrypoint"] == "normal_runner_job":
            require(source == args.candidate and sha(runner_path) == binding["candidate"]["runner_sha256"], "reviewed normal runner")
            runner = load_module(runner_path, "_forecast_stock_runner", binding["candidate"]["runner_sha256"])
            runner._load_source(source)
            # Stock run_job requires exactly its existing three job fields.
            stock_job = folder / "stock-job.json"
            write(stock_job, {key: job[key] for key in ("source_root", "simulation_args", "request")})
            runner.run_job(stock_job)
            bundle = core.strict_json((folder / "ordinary/chronicle_bundle.json").read_bytes())
            receipt = bundle["metadata"]["expansion_experiment"]
            require(bundle.get("world_state", {}).get("turn") == 26 and bundle["metadata"].get("seed") == 42
                    and type(receipt) is dict and receipt.get("arm") == job["request"]["arm"]
                    and receipt.get("feature") == job["request"]["feature"], "stock matching horizon/seed/receipt")
            parent_controls = None
            if spec["parent"]:
                parent_controls = core.strict_json((args.root / "roles" / spec["parent"] / "role.json").read_bytes())["experiment_receipt"]["controls_after"]
            runner._validate_receipt_controls(receipt, job["request"], parent_controls=parent_controls)
            runner._verify_worker_identity(folder / "worker_identity.json", receipt)
        else:
            require(job["entrypoint"] == "stock_cli" and job["request"] is None, "stock CLI exact continuation")
            old_argv = sys.argv
            try:
                sys.argv = ["chronicler.main", *job["simulation_args"]]
                try: runpy.run_module("chronicler.main", run_name="__main__")
                except SystemExit as exc: require(exc.code in (None, 0), "stock CLI unsuccessful")
            finally: sys.argv = old_argv
            from chronicler.batch_manifest import source_identity, native_identity, environment_identity
            after = {"source": source_identity(), "native": native_identity(), "environment": environment_identity()}
            runner_hash = sha(Path(__file__).resolve())
            write(folder / "worker_identity.json", {"schema_version": 2, "before": before, "after": after,
                  "environment_stable": before["environment"] == after["environment"], "identities_stable": before == after,
                  "runner_sha256": runner_hash, "runner_sha256_after": runner_hash, "runner_kind": "stock_cli_wrapper"})
            receipt = None
        from chronicler.batch_manifest import source_identity, native_identity, environment_identity
        after = {"source": source_identity(), "native": native_identity(), "environment": environment_identity()}
        worker = core.strict_json((folder / "worker_identity.json").read_bytes())
        require(worker["before"] == before and worker["after"] == after and before == after
                and worker["environment_stable"] is worker["identities_stable"] is True
                and worker["runner_sha256"] == worker["runner_sha256_after"], "original worker source/native/environment stable")
        final = core.strict_json((folder / "ordinary/state.json").read_bytes())
        require(type(final.get("turn")) is int and final["turn"] == 26, "actual completed horizon")
        module_origins(source, args.prefix)
        require(runtime_files() == observed_runtime and sha(Path(native_path)) == binding["native"]["sha256"], "final runtime/native bytes")
        require(package_digest(source)[0] == expected["package_digest"] and resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 <= 2 * GIB, "source/peak RSS closure")
        write(args.result, {"status": "complete", "returncode": 0, "identity": before, "completed_horizon": 26,
              "start_turn": spec["start_turn"], "observed_ticks": 26 - spec["start_turn"],
              "worker_identity_path": "roles/" + spec["name"] + "/worker_identity.json",
              "runner_sha256": worker["runner_sha256"], "entrypoint": job["entrypoint"],
              "experiment_receipt": receipt, "schemas": schemas, "full_graph_equivalence": None, "global_rng_equivalence": None})
    except BaseException:
        # A failed body remains intact. No tick/horizon/reason is invented.
        try: write(args.result, {"status": "failed", "returncode": None, "observed_ticks": None, "completed_horizon": None})
        except BaseException: pass
        raise


def finalize(root, report, eligible, guard, started, cpu_started, limits):
    """Authority-inclusive commit with post-terminal live guard/invalidation."""
    try:
        guard()
        report.update(complete=eligible and not report["errors"], owner_wall_seconds=time.monotonic() - started,
                      owner_measured_cpu_seconds=cpu_seconds() - cpu_started, timing_observation="before_terminal_commit")
        raw = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
        terminal = {"complete": report["complete"], "cleanup_complete": report["cleanup_complete"],
                    "result_sha256": hashlib.sha256(raw).hexdigest(), "required_wrapper_exit": 0,
                    "source_publication_qualified": False, "raw_original_artifact_qualified": None}
        terminal_raw = (json.dumps(terminal, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
        observed = report.get("retained_inventory")
        require(type(observed) is dict and type(observed.get("bytes")) is int
                and type(observed.get("file_count")) is int, "retained inventory unavailable")
        require(observed["bytes"] + len(raw) + len(terminal_raw) + 65536 + limits["publication_bytes"] <= limits["max_total_bytes"]
                and observed["file_count"] + 3 + limits["publication_files"] <= limits["max_files"], "authority-inclusive retained cap")
        write(root / "result.json", report); write(root / "terminal.json", terminal, 65536)
        require(regular(root / "result.json").st_size == len(raw) and sha(root / "result.json") == terminal["result_sha256"]
                and regular(root / "terminal.json").st_size == len(terminal_raw)
                and sha(root / "terminal.json") == hashlib.sha256(terminal_raw).hexdigest(), "committed authority bytes")
        guard()
        return report["complete"]
    except BaseException as exc:
        report["complete"] = False
        report["errors"].append({"stage": "terminal-closure", "type": type(exc).__name__[:80]})
        negative = {"complete": False, "cleanup_complete": report["cleanup_complete"], "publication_failed": True}
        try: write(root / "terminal-failure.json", negative, 65536)
        except BaseException: pass
        for name, value, bound in (("result.json", report, 8 * 1024**2), ("terminal.json", negative, 65536)):
            try: write(root / name, value, bound)
            except BaseException: pass
        return False


def execute(args):
    require(EXECUTION_APPROVAL is not None, "source-only execution approval is null")
    started, cpu_started = time.monotonic(), cpu_seconds()
    require(platform.python_version() == PYTHON and sys.platform == "linux", "registered Linux/CPython owner")
    producer = context(os.environ); paths(args)
    require(not args.root.exists() and not args.root.is_symlink() and not args.prefix.exists(), "fresh owner/prefix paths")
    args.root.mkdir(parents=True); (args.root / "logs").mkdir(); (args.root / "inputs").mkdir()
    report = {"complete": False, "cleanup_complete": False, "producer": producer, "errors": [], "stage": "admission",
              "completed_roles": [], "actual_new_schemas": None, "actual_failed_role_ticks": None,
              "full_graph_equivalence": None, "global_rng_equivalence": None, "raw_economy_contact_candidate_evidence": None,
              "efficacy": None, "performance": None, "adoption": None, "raw_original_artifact_qualified": None}
    report["role_status"] = {name: {"status": "unattempted", "observed_ticks": None} for name in
        ("legacy-default", "candidate-default", "candidate-off", "legacy-fixed", "candidate-fixed", "local-parent",
         "local-normal", "local-withheld", "local-reference", "exact-4", "exact-6", "exact-8", "exact-10", "exact-13")}
    write(args.root / "result.json", report)
    write(args.root / "terminal.json", {"complete": False, "cleanup_complete": False})
    supervisor, owned, eligible, admitted, pins = None, None, False, None, None
    limits = {"max_total_bytes": 2 * GIB, "max_files": 4096, "publication_bytes": 16 * 1024**2, "publication_files": 128}
    deadline = started + 2400
    try:
        core, reader, transport, owned, config, binding, jobs = modules(args.control)
        limits = core.LIMITS; before_control = control_pins(args.control)
        report["runtime_flags"] = runtime_flags()
        report["deployment"] = owned["wealth_floor_hosted_deployment"].hosted_vm_precondition()
        owner = owned["exact_near_screen_process"]; legacy = owned["exact_near_screen_session"]
        env = child_environment(); env.update(CHRONICLER_CHECK_RESOURCES="1", CHRONICLER_CHECK_POPULATION="1")
        loader = loader_identity(); env["LD_LIBRARY_PATH"] = loader["child_LD_LIBRARY_PATH"]
        require(all(os.environ.get(k) == v for k, v in CAPS.items()), "owner startup hash/thread caps")
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
        with owner.Cancellation() as cancellation, owner.SubreaperLease() as lease:
            supervisor = owner.make_supervisor(legacy, args.root, deadline, lease, cancellation)
            supervisor.admission("initial", 12, 4)
            def check():
                supervisor.check()
                require(cpu_seconds() - cpu_started <= 1800 and time.monotonic() <= deadline, "live owner budgets")
            def command(label, argv, wall, *, input_token=False, role=False):
                check()
                wall_left = deadline - time.monotonic() - 150
                cpu_left = 1800 - (cpu_seconds() - cpu_started) - 100
                require(wall_left > 0 and cpu_left > 0, "owner finalization reserve")
                selected = dict(env)
                if input_token:
                    require(bool(os.environ.get("GH_TOKEN")), "read-only input token")
                    selected["GH_TOKEN"] = os.environ["GH_TOKEN"]
                supervisor.command(label, ["/usr/bin/timeout", "--signal=TERM", "--kill-after=5s", str(min(wall, int(wall_left), int(cpu_left))), *argv], selected, args.root)
                require(regular(args.root / "logs" / (label + ".log")).st_size <= 2 * 1024**2, "study log acceptance cap")
                check()
            sources = {"baseline": args.baseline, "candidate": args.candidate}
            source_witnesses = {}
            for label, folder, source in (("control", args.control, producer["GITHUB_SHA"]),
                    ("baseline", args.baseline, binding["baseline"]["source"]), ("candidate", args.candidate, binding["candidate"]["source"])):
                command(label + "-source", ["git", "-C", str(folder), "rev-parse", "HEAD"], 30)
                require(supervisor.last_stdout.decode().strip() == source, "actual clean checkout source")
                command(label + "-clean", ["git", "-C", str(folder), "status", "--porcelain=v1"], 30)
                require(not supervisor.last_stdout, "dirty/untracked checkout refused")
                command(label + "-tracked", ["git", "-C", str(folder), "ls-files", "-z"], 30)
                names = supervisor.last_stdout.decode("utf-8").split("\0")
                require(names.pop() == "", "tracked source terminator")
                source_witnesses[label] = source_files(folder, names)
                if label != "control":
                    command(label + "-native-tree", ["git", "-C", str(folder), "rev-parse", "HEAD:chronicler-agents"], 30)
                    require(supervisor.last_stdout.decode().strip() == core.NATIVE_TREE, "exact native source subtree")
            write(args.root / "source-witnesses.json", source_witnesses)
            for alias, folder in sources.items():
                expected = binding[alias]
                require(package_digest(folder)[0] == expected["package_digest"]
                        and sha(folder / "pyproject.toml") == expected["pyproject_sha256"]
                        and sha(folder / "uv.lock") == expected["lock_sha256"], "source package/dependency inputs")
            require(binding["candidate"]["lock_sha256"] == binding["baseline"]["lock_sha256"], "matched dependency lock")
            clock_base = python_command(sys.executable, str(args.control / "scripts/forecast_credibility_owner.py"),
                    "--control", str(args.control), "--baseline", str(args.baseline), "--candidate", str(args.candidate),
                    "--prefix", str(args.prefix), "--root", str(args.root))
            report["stage"] = "job-clock"
            command("job-clock", [*clock_base, "--child", "job-clock", "--result", str(args.root / "job-clock.json")],
                    15, input_token=True)
            clock = core.strict_json((args.root / "job-clock.json").read_bytes())
            expected_clock = core.admit_job_clock(clock_producer(producer), clock["observed"]["run"],
                    clock["observed"]["jobs"], http_date=clock["observed"]["http_date"],
                    http_age=clock["observed"]["http_age"], run_http_age=clock["observed"]["run_http_age"],
                    utc_before=clock["observed"]["utc_before"], utc_after=clock["observed"]["utc_after"],
                    monotonic_before=clock["observed"]["monotonic_before"], monotonic_after=clock["observed"]["monotonic_after"],
                    boot_id=legacy.boot_id().strip())
            require(clock == expected_clock and supervisor.cleanup_complete, "original actual current job clock")
            deadline = core.effective_owner_deadline(started, clock["monotonic_deadline"], time.monotonic())
            tighten_deadlines(supervisor, deadline)
            report["job_clock"] = {"path": "job-clock.json", "sha256": sha(args.root / "job-clock.json"),
                    "monotonic_deadline": clock["monotonic_deadline"], "effective_owner_deadline": deadline,
                    "publication_reserve_seconds": core.PUBLICATION_RESERVE,
                    "scope": "Official current-job clock admission before any World; tighter available job deadline, unchanged2400/1800 owner maxima."}
            check()
            command("install-uv", python_command(sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-cache-dir", "--only-binary=:all:", "uv==" + UV), 120)
            uv = Path(sys.executable).parent / "uv"; uv_hash = sha(uv)
            command("uv-version", [str(uv), "--version"], 30)
            require(supervisor.last_stdout.decode().strip().split(" ", 2)[:2] == ["uv", UV], "actual uv version")
            env["UV_PROJECT_ENVIRONMENT"] = str(args.prefix)
            command("locked-environment", [str(uv), "sync", "--project", str(args.candidate), "--frozen", "--group", "dev", "--no-install-project", "--no-build", "--python", sys.executable], 120)
            py = args.prefix / "bin/python"
            base = python_command(py, str(args.control / "scripts/forecast_credibility_owner.py"), "--control", str(args.control),
                                  "--baseline", str(args.baseline), "--candidate", str(args.candidate), "--prefix", str(args.prefix), "--root", str(args.root))
            (args.root / "pure-preflight").mkdir()
            report["stage"] = "pure-preflight"
            command("pure-preflight", [*base, "--child", "preflight", "--result", str(args.root / "pure-preflight/receipt.json")], 110)
            pure = core.strict_json((args.root / "pure-preflight/receipt.json").read_bytes())
            require(pure["complete"] is True and pure["before"] == pure["after"] == before_control, "pure preflight source/guard closure")
            command("input-before", [*base, "--child", "input-before", "--result", str(args.root / "input-before.json")], 120, input_token=True)
            command("install-wheel", [str(uv), "pip", "install", "--python", str(py), "--no-cache", "--no-deps", str(args.root / "inputs" / config["wheel"]["filename"])], 120)
            command("packages-before", [str(uv), "pip", "list", "--python", str(py), "--format", "json"], 30)
            packages_before = core.strict_json(supervisor.last_stdout)
            require(type(packages_before) is list and 0 < len(packages_before) <= 512, "complete installed package inventory")
            write(args.root / "packages-before.json", packages_before)
            command("bootstrap", [*base, "--child", "bootstrap", "--result", str(args.root / "admission.json")], 90)
            admitted = core.strict_json((args.root / "admission.json").read_bytes())
            report["actual_new_schemas"] = admitted["schemas"]
            registration = core.registration(binding, jobs)
            registration["bootstrap_schemas"] = admitted["schemas"]
            write(args.root / "registration.json", registration)
            roles = {}; (args.root / "roles").mkdir()
            registration_path = args.control / "docs/experiments/forecast-credibility-registration.md"
            for index, spec in enumerate(jobs):
                report["stage"] = "role:" + spec["name"]
                require(datetime.now(timezone.utc) < transport.utc(binding["native"]["producer"]["expiry"]), "input expiry before role")
                folder = args.root / "roles" / spec["name"]; folder.mkdir(); (folder / "ordinary").mkdir()
                parent_digest = None
                if spec["parent"]:
                    parent_digest = sha(args.root / "roles" / spec["parent"] / "ordinary" / ("checkpoint_turn_" + str(spec["start_turn"]) + ".ckpt"))
                job = core.simulation_job(spec, root=str(args.root), sources=sources, registration_path=str(registration_path),
                                          registration_sha256=sha(registration_path), parent_sha256=parent_digest)
                write(folder / "job.json", job)
                argv = [*base, "--child", "role", "--index", str(index), "--result", str(folder / "role.json")]
                write(folder / "launch.json", {"argv": argv, "cwd": str(args.root), "environment": env,
                        "affinity": sorted(os.sched_getaffinity(0)), "wall_seconds": 150, "cpu_seconds": 100})
                report["role_status"][spec["name"]] = {"status": "started", "observed_ticks": None}
                write(args.root / "result.json", report)
                try: command("role-" + str(index), argv, 150, role=True)
                except BaseException:
                    report["role_status"][spec["name"]] = {"status": "failed_or_killed", "observed_ticks": None,
                        "cleanup_complete": supervisor.cleanup_complete}
                    raise
                facts = core.strict_json((folder / "role.json").read_bytes())
                require(facts["status"] == "complete" and facts["observed_ticks"] == 26 - spec["start_turn"]
                        and supervisor.cleanup_complete, "observed role completion and owned cleanup")
                original = inventory(folder / "ordinary", max_bytes=128 * 1024**2, max_files=256, guard=check)
                whole_role = inventory(folder, max_bytes=128 * 1024**2, max_files=256, guard=check)
                role_log = args.root / "logs" / ("role-" + str(index) + ".log")
                require(whole_role["bytes"] + regular(role_log).st_size <= limits["role_output_bytes"]
                        and whole_role["file_count"] + 1 <= limits["role_output_files"], "role cap includes owned log")
                facts["inventory"] = original["files"]
                roles[spec["name"]] = facts
                report["role_status"][spec["name"]] = {"status": "complete", "observed_ticks": facts["observed_ticks"],
                    "cleanup_complete": True}
                report["completed_roles"].append({"name": spec["name"], "actual_ticks": facts["observed_ticks"], "retained": whole_role})
                write(args.root / "roles.json", roles); write(args.root / "result.json", report)
            report["stage"] = "mechanical-reader"
            command("mechanical-reader", [*base, "--child", "readout", "--result", str(args.root / "mechanics.json")], 120)
            report["mechanical_readout_sha256"] = sha(args.root / "mechanics.json")
            command("input-after", [*base, "--child", "input-after", "--result", str(args.root / "input-after.json")], 120, input_token=True)
            command("packages-after", [str(uv), "pip", "list", "--python", str(py), "--format", "json"], 30)
            packages_after = core.strict_json(supervisor.last_stdout)
            write(args.root / "packages-after.json", packages_after)
            require(packages_before == packages_after, "actual installed package inventories unchanged")
            require(sha(uv) == uv_hash, "final installer identity")
            check(); supervisor.check(final=True)
        require(supervisor.cleanup_complete and not owner.direct_children(), "final owned quiescence")
        report.update(cleanup_complete=True, actual_fresh_Worlds=7, actual_restored_roles=7, actual_simulation_roles=14,
                      actual_executed_ticks=sum(row["actual_ticks"] for row in report["completed_roles"]))
        require(report["actual_executed_ticks"] == 315, "actual complete matrix")
        eligible = True
    except BaseException as exc:
        report["errors"].append({"stage": report["stage"], "type": type(exc).__name__[:80]})
    finally:
        def budget():
            require(time.monotonic() <= deadline and cpu_seconds() - cpu_started <= 1800, "final live owner budgets")
        try:
            report["retained_inventory"] = inventory(args.root, max_bytes=limits["max_total_bytes"], max_files=limits["max_files"],
                    authority=("result.json", "terminal.json", "terminal-failure.json"), guard=budget)
        except BaseException as exc:
            report["errors"].append({"stage": "retention", "type": type(exc).__name__[:80]}); eligible = False
        def guard():
            if supervisor is not None: supervisor.check(final=True)
            if eligible:
                require(supervisor.cleanup_complete and not owned["exact_near_screen_process"].direct_children(), "postterminal quiescence")
                require(sha(args.root / "job-clock.json") == report["job_clock"]["sha256"]
                        and legacy.boot_id().strip() == clock["boot_id"]
                        and deadline <= clock["monotonic_deadline"] - core.PUBLICATION_RESERVE,
                        "postterminal original job clock and publication reserve")
                require(control_pins(args.control) == before_control and sha(uv) == uv_hash, "postterminal control/installer")
                for alias, folder in sources.items():
                    require(package_digest(folder)[0] == binding[alias]["package_digest"]
                            and sha(folder / "pyproject.toml") == binding[alias]["pyproject_sha256"]
                            and sha(folder / "uv.lock") == binding[alias]["lock_sha256"], "postterminal producer source")
                for label, folder in (("control", args.control), *sources.items()):
                    require(source_files(folder, list(source_witnesses[label])) == source_witnesses[label], "postterminal complete tracked source")
                require(sha(Path(admitted["native_file"])) == binding["native"]["sha256"], "postterminal installed native")
                require(runtime_file(admitted["runtime_files"]["python"]["path"]) == admitted["runtime_files"]["python"]
                        and runtime_file(admitted["runtime_files"]["libpython"]["path"]) == admitted["runtime_files"]["libpython"], "postterminal runtime bytes")
                require(datetime.now(timezone.utc) < transport.utc(binding["native"]["producer"]["expiry"]), "postterminal input expiry")
            budget()
        finalize(args.root, report, eligible, guard, started, cpu_started, limits)
    return 0 if report["complete"] else 2


def main(argv=None):
    require(EXECUTION_APPROVAL is not None, "source-only execution approval is null")
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("control", "baseline", "candidate", "prefix", "root", "result"):
        parser.add_argument("--" + name, type=Path, required=name != "result")
    parser.add_argument("--child", choices=("job-clock", "preflight", "input-before", "input-after", "bootstrap", "role", "readout"))
    parser.add_argument("--index", type=int)
    args = parser.parse_args(argv)
    if args.child:
        require(args.result is not None, "fixed child result path")
        child(args); return 0
    return execute(args)


if __name__ == "__main__":
    raise SystemExit(main())


