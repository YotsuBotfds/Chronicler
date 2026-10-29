#!/usr/bin/env python3
"""Inactive owned caller for the fixed current090 passive profiling study.

Source stage only. No command, probe, installer or World runs while the closed
source approval remains null. Bootstrap Python/checkout are job preconditions;
all study environment setup, input transfer, probes, roles and proofs are owned.
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
import shutil
import stat
import sys
import time
import types

EXECUTION_APPROVAL = None
REFERENCE_SHA = "4e7d5bf43d618da6d0228c24a56d0f4f5c54f8db526a5801abf2985a98dda9a9"
TRANSPORT_SHA = "257910d4139afdf81e5b1b75c2c598d3a652c1c22ed89a6e3783cffafa49e489"
CORE_SHA = "3ef91319a1e69470e2358774a9690c99f1e908890bb0bb6326ee2914a934e2aa"
REPOSITORY = "YotsuBotfds/Chronicler"
ACTIVE_BRANCH = "lead/cloud-current090-passive-profile-20261029"
WORKFLOW_PATH = ".github/workflows/current090-passive-profile.yml"
JOB_KEY = "current090-passive-profile"
PYTHON = "3.13.17"
UV = "0.13.6"
EXPECTED_PREFLIGHT_CASES = 194
WORKFLOW_SHA = '1307757f8b8e409d811e67a23737eadac64794173a02d79b3b3add48f1bb0def'
GIB = 1024**3
CAPS = {key: "1" for key in ("BLIS_NUM_THREADS", "CARGO_BUILD_JOBS", "GOTO_NUM_THREADS", "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "PYTHON_CPU_COUNT",
        "RAYON_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")}
CAPS.update(PYTHONHASHSEED="0", OPENBLAS_THREAD_TIMEOUT="16")


class Refused(ValueError):
    pass


def require(condition, message):
    if not condition: raise Refused(message)


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


def modules(control, controls):
    core = load_module(control / "scripts/current090_passive_profile.py", "_passive090_core", CORE_SHA)
    inputs = load_module(control / "scripts/current090_profile_inputs.py", "_passive090_inputs", TRANSPORT_SHA)
    reference_path = control / "docs/experiments/current090-passive-profile-inputs.json"
    require(regular(reference_path).st_size <= 65536, "reference source bound")
    with reference_path.open("rb") as stream: raw = stream.read(65537)
    require(len(raw) <= 65536 and hashlib.sha256(raw).hexdigest() == REFERENCE_SHA, "reference source identity")
    reference = inputs.strict_json(raw)
    names = ("wealth_floor_build_resources", "exact_near_screen_session", "exact_near_screen_process",
             "wealth_floor_hosted_deployment")
    owned = {}
    for name in names:
        pin = reference["controls"][name + ".py"]
        path = controls / "scripts" / (name + ".py")
        require(regular(path).st_size == pin["bytes"], "selected helper bytes")
        owned[name] = load_module(path, name, pin["sha256"])
    return core, inputs, reference, owned


def context(env):
    require(env.get("GITHUB_REPOSITORY") == REPOSITORY and env.get("GITHUB_ACTIONS") == "true"
            and env.get("GITHUB_EVENT_NAME") == "push" and env.get("GITHUB_REF") == "refs/heads/" + ACTIVE_BRANCH
            and env.get("GITHUB_WORKFLOW_REF") == REPOSITORY + "/" + WORKFLOW_PATH + "@refs/heads/" + ACTIVE_BRANCH
            and env.get("GITHUB_RUN_ATTEMPT") == "1" and env.get("GITHUB_JOB") == JOB_KEY,
            "closed first-attempt push required")
    require(len(env.get("GITHUB_SHA", "")) == 40 and all(c in "0123456789abcdef" for c in env["GITHUB_SHA"]),
            "control source SHA")
    require(env.get("GITHUB_RUN_ID", "").isascii() and env["GITHUB_RUN_ID"].isdigit()
            and int(env["GITHUB_RUN_ID"]) > 0, "run identity")
    return {key: env[key] for key in ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT",
                                     "GITHUB_WORKFLOW_REF", "GITHUB_JOB")}


def verify_workflow(control):
    template = control / "docs/experiments/current090-passive-profile.yml.inactive"
    require(sha(template) == WORKFLOW_SHA, "reviewed workflow template")
    actual = control / WORKFLOW_PATH
    if actual.exists() or actual.is_symlink():
        require(sha(actual) == WORKFLOW_SHA, "exact active workflow copy")


def child_environment():
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("PYTHON") or key in ("UV_PROJECT_ENVIRONMENT", "UV_CACHE_DIR", "VIRTUAL_ENV"):
            env.pop(key)
    for key in ("PYTHONPATH", "PYTHONHOME", "LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH",
                "GH_TOKEN", "GITHUB_TOKEN"):
        env.pop(key, None)
    env.update(CAPS, PYTHONDONTWRITEBYTECODE="1", UV_NO_PROGRESS="1", UV_LINK_MODE="copy", UV_NO_CACHE="1")
    return env


def python_command(executable, *arguments):
    # -I implies -E and would ignore the hashseed/cpu environment. Safe-path
    # and no-user-site are explicit, with actual flags checked in each child.
    return [str(executable), "-P", "-s", "-B", "-X", "cpu_count=1", *arguments]


def runtime_flags():
    value = {name: getattr(sys.flags, name) for name in
             ("safe_path", "no_user_site", "ignore_environment", "isolated", "hash_randomization")}
    value.update(cpu_count=os.cpu_count(), cpu_count_option=sys._xoptions.get("cpu_count"))
    require(value["safe_path"] is True and value["no_user_site"] == 1
            and value["ignore_environment"] == value["isolated"] == value["hash_randomization"] == 0
            and value["cpu_count"] == 1 and value["cpu_count_option"] == "1"
            and os.environ.get("PYTHONHASHSEED") == "0", "actual interpreter hash/isolation/CPU flags")
    return value


def command_environment(label):
    env = child_environment()
    if label in ("input-before", "input-after"):
        token = os.environ.get("GH_TOKEN", "")
        require(bool(token), "read-only input token required")
        env["GH_TOKEN"] = token
    return env


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


def cpu_seconds():
    own, waited = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    return own.ru_utime + own.ru_stime + waited.ru_utime + waited.ru_stime


def validate_paths(args):
    folders = [args.control, args.controls, args.source, args.prefix, args.root]
    require(all(isinstance(p, Path) and p.is_absolute() for p in folders), "absolute study paths")
    for path in folders:
        require(not path.is_symlink() and all(not p.is_symlink() for p in path.parents), "study path symlink")
        require(path == path.resolve(), "canonical study paths")
    require(all(not left.is_relative_to(right) for left in folders for right in folders if left != right)
            and len(set(folders)) == 5, "disjoint study roots")
    require(Path(__file__).resolve() == args.control / "scripts/current090_profile_owner.py", "actual control origin")


def pin_schemas(raw, reference):
    require(type(raw) is dict and set(raw) == set(reference), "all three schema kinds")
    for name, row in raw.items():
        require(type(row) is list and len(row) == 3 and type(row[0]) is int
                and type(row[1]) is str and type(row[2]) is str, "actual schema form")
        require({"version": row[0], "fingerprint": row[1],
                 "schema_sha256": hashlib.sha256(row[2].encode()).hexdigest()} == reference[name],
                "historical qualified schema reference")


def preflight_sources(control):
    paths = ("tests/test_current090_passive_profile.py", "tests/test_current090_profile_owner.py",
             "scripts/current090_passive_profile.py", "scripts/current090_profile_owner.py",
             "scripts/current090_profile_inputs.py", "scripts/current090_profile_contracts.py",
             "scripts/current090_profile_publish.py", "docs/experiments/current090-passive-profile.yml.inactive",
             "scripts/run_python_oracle_checks.py", "docs/experiments/current090-passive-profile-inputs.json")
    return {name: sha(control / name) for name in paths}


def verify_preflight(value, expected):
    require(value.get("passed") is True and type(value.get("tests")) is int
            and value["tests"] == EXPECTED_PREFLIGHT_CASES
            and value.get("errors") == value.get("failures") == value.get("skips") == value.get("pytest_exit") == 0
            and value.get("collection_or_setup_failure") is False, "hosted pure outcome")
    require(value.get("blocked_operations") == [] and value.get("project_native_imports") == []
            and value.get("source_unchanged") is True and value.get("before") == value.get("after") == expected,
            "hosted pure guard/source identities")
    require(value.get("registry_module_counts") == {"tests/test_current090_passive_profile.py": 1,
            "tests/test_current090_profile_owner.py": 1}, "hosted actual registry list")
    flags = value.get("runtime_flags", {})
    require(flags == {"safe_path": True, "no_user_site": 1, "ignore_environment": 0,
                      "isolated": 0, "hash_randomization": 0, "cpu_count": 1}, "hosted pure actual runtime flags")


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


def runtime_files():
    import cProfile
    import _lsprof
    result = {name: runtime_file(value) for name, value in
              (("python", sys.executable), ("cProfile", cProfile.__file__), ("_lsprof", _lsprof.__file__))}
    result["libpython"] = loader_identity()["actual"]
    return result


GRAPH_REFUSAL_CODES = {
    "unsupported base buffer": "BASE_BUFFER_TYPE", "unsupported base buffer layout": "BASE_BUFFER_LAYOUT",
    "unsupported memoryview layout": "MEMORYVIEW_LAYOUT", "unsupported NumPy exact type": "NUMPY_EXACT_TYPE",
    "unsupported NumPy dtype": "NUMPY_DTYPE", "unexpected scalar base": "SCALAR_BASE",
    "unanchored nonowning array": "ARRAY_UNANCHORED", "array base extent": "ARRAY_BASE_EXTENT",
    "empty array base extent": "EMPTY_ARRAY_BASE_EXTENT", "state node cap": "STATE_NODE_CAP",
    "unqualified Enum type": "ENUM_TYPE", "unsupported scalar/bytearray subclass": "SCALAR_SUBCLASS",
    "unsupported path subclass": "PATH_SUBCLASS", "unsupported dict subclass": "DICT_SUBCLASS",
    "unsupported sequence subclass": "SEQUENCE_SUBCLASS", "unsupported set subclass": "SET_SUBCLASS",
    "unsupported Random subclass": "RANDOM_SUBCLASS", "NumPy storage reader is not admitted": "NUMPY_NOT_ADMITTED",
    "default factory": "DEFAULT_FACTORY", "ambiguous duplicate slot storage": "DUPLICATE_SLOT_STORAGE",
    "unsupported object fields": "OBJECT_FIELDS", "unsupported set member": "SET_MEMBER",
}


def role_failure_record(exc, core, index):
    """Closed negative metadata only; never copy arbitrary exception text/state."""
    require(type(index) is int and 0 <= index < 6, "fixed failure role index")
    code, reason, name = "UNCLASSIFIED", "UNCLASSIFIED", None
    if type(exc) is core.Refused:
        code = "CORE_REFUSED"
        if type(exc.args) is tuple and len(exc.args) == 1 and type(exc.args[0]) is str:
            message = exc.args[0]
            if message in GRAPH_REFUSAL_CODES:
                reason = GRAPH_REFUSAL_CODES[message]
            else:
                prefix = "unsupported state type: "
                if message.startswith(prefix) and len(prefix) < len(message) <= len(prefix) + 256:
                    candidate = message[len(prefix):]
                    first = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_"
                    rest = first + "0123456789"
                    if all(part and part[0] in first and all(char in rest for char in part)
                           for part in candidate.split(".")):
                        reason, name = "STATE_TYPE", candidate
    return {"complete": False, "role_success": False, "index": index,
            "request": dict(core.schedule()[index]), "exception_code": code,
            "reason_code": reason, "type_name": name}


def child(args, core, inputs, reference, owned=None):
    require(EXECUTION_APPROVAL is not None, "source-only execution approval is null")
    resource.setrlimit(resource.RLIMIT_CPU, (240, 240))
    resource.setrlimit(resource.RLIMIT_AS, (4 * GIB, 4 * GIB))
    actual_flags = runtime_flags()
    require(len(os.sched_getaffinity(0)) == 1 and all(os.environ.get(k) == v for k, v in CAPS.items()), "child CPU/caps")
    if args.child in ("input-before", "input-after"):
        # The complete HTTP/TLS/read operation stays inside an owned, hard-wall
        # private-session child. API credentials never reach a physics child.
        def admission(_phase, disk, ram):
            observed = owned["wealth_floor_build_resources"].memory_admission()
            require(shutil.disk_usage(args.input_dir).free >= disk * GIB
                    and observed["available_bytes"] >= ram * GIB, "input child resources")
        transport = inputs.Transport(os.environ.get("GH_TOKEN", ""), types.SimpleNamespace(admission=admission),
                                     time.monotonic() + 120)
        pins = inputs.artifact_pins(reference)
        result = {"metadata": [transport.metadata(pin) for pin in pins], "actual_World_calls": 0, "runtime_flags": actual_flags}
        if args.child == "input-before":
            pin = next(pin for pin in pins if pin.artifact_id == 12893517727)
            archive = args.input_dir / "wheel.zip"
            transport.download(pin, archive)
            result["wheel"] = inputs.stage_wheel(archive, args.input_dir / reference["wheel"]["filename"], reference)
        write(args.result, result)
        return
    require(not any(name == "chronicler" or name.startswith(("chronicler.", "chronicler_agents"))
                    for name in sys.modules), "project/native import before producer origin")
    source, prefix = args.source.resolve(), args.prefix.resolve()
    require(Path(sys.prefix).resolve() == prefix and platform.python_version() == PYTHON
            and platform.python_implementation() == "CPython", "fresh interpreter prefix/version")
    require(len(os.sched_getaffinity(0)) == 1 and os.cpu_count() == 1
            and all(os.environ.get(k) == v for k, v in CAPS.items()), "one-CPU caps")
    require(package_digest(source)[0] == core.PACKAGE, "producer package")
    sys.path.insert(0, str(source / "src"))
    import importlib.metadata
    import numpy as np
    import chronicler_agents as native
    from chronicler import main as cm, run_checkpoint as rc
    from chronicler.batch_manifest import native_identity
    from chronicler.utils import sync_civ_population
    from importlib import import_module
    from importlib.machinery import EXTENSION_SUFFIXES
    compiled = import_module("chronicler_agents.chronicler_agents")
    classes = tuple(getattr(compiled, name) for name in core.KINDS)
    require(str(compiled.__file__).endswith(tuple(EXTENSION_SUFFIXES))
            and all(isinstance(cls, type) and cls is getattr(native, name)
                    for cls, name in zip(classes, core.KINDS)), "real compiled classes")
    require(sha(Path(compiled.__file__).resolve()) == core.NATIVE
            and native_identity().get("bytes") == reference["native"]["bytes"], "installed native linkage")
    require({name: importlib.metadata.version(name) for name in reference["packages"]} == reference["packages"],
            "locked package versions")
    schemas = {name: list(cls.checkpoint_schema()) for name, cls in zip(core.KINDS, classes)}
    pin_schemas(schemas, reference["historical_schema_reference"])
    identity = rc.runtime_identity()
    actual_runtime_files = runtime_files()
    require(identity["source"] == {"git_sha": core.SOURCE, "package_digest": core.PACKAGE}, "exact090 runtime")
    module_origins(source, prefix)
    core.EXECUTION_APPROVAL = EXECUTION_APPROVAL
    try:
        if args.child == "bootstrap":
            result = {"approval": EXECUTION_APPROVAL, "identity": identity, "schemas": schemas,
                      "source_root": str(source), "prefix": str(prefix), "native_file": str(compiled.__file__),
                      "rng": core.capture_rng(np), "actual_World_calls": 0, "runtime_files": actual_runtime_files,
                      "python": sys.version, "platform": platform.platform(),
                      "affinity": sorted(os.sched_getaffinity(0)), "thread_env": {k: os.environ[k] for k in CAPS}}
            result["runtime_flags"] = actual_flags
            core.validate_rng(result["rng"])
        elif args.child == "role":
            require(type(args.index) is int and 0 <= args.index < 6, "fixed role index")
            admission = inputs.strict_json(args.admission.read_bytes())
            require(admission["approval"] == EXECUTION_APPROVAL and admission["schemas"] == schemas
                    and admission["identity"] == identity and admission["source_root"] == str(source)
                    and admission["prefix"] == str(prefix) and admission["runtime_files"] == actual_runtime_files
                    and admission["affinity"] == sorted(os.sched_getaffinity(0))
                    and admission["runtime_flags"] == actual_flags,
                    "same admitted runtime")
            try:
                result = core.run_role(core.schedule()[args.index], ordinary=args.ordinary,
                                       checkpoint=args.checkpoint, shared_rng=admission["rng"], admission=admission)
            except BaseException as exc:
                try:
                    write(args.result, role_failure_record(exc, core, args.index), 4096)
                except BaseException:
                    pass  # Diagnostic failure must never replace the original exception.
                raise
        else:
            require(args.child == "compare", "closed child action")
            source_scripts = source / "scripts"
            city = load_module(source_scripts / "cities_identity.py", "_passive090_cities",
                               "d60534b31d128eb7b71b2798b17799dbc32c4dd27a90f8d3301163501833cd3a")
            speed = load_module(source_scripts / "turn_speed_identity.py", "_passive090_speed",
                                "2828aeffd0942a186c94db20406efbce4912d8c7867bad3b68527edd5d8ce642")
            a, b = inputs.strict_json(args.left.read_bytes()), inputs.strict_json(args.right.read_bytes())
            result = core.profile_equivalent(a, b, city.compare, speed._raw_bundle_problems,
                                              args.left.parent / "ordinary", args.right.parent / "ordinary")
        module_origins(source, prefix)
        require(runtime_files() == actual_runtime_files, "final Python/profiler runtime files")
        result["runtime_files"] = actual_runtime_files
        result["runtime_flags"] = actual_flags
        require(sha(Path(compiled.__file__).resolve()) == core.NATIVE, "final installed native")
        require(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 <= 2 * GIB, "whole child peak RSS")
        write(args.result, result)
    finally:
        core.EXECUTION_APPROVAL = None


def inventory(root, *, max_bytes=3 * GIB, max_files=5000, authority=(), guard=lambda: None):
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


def finalize_authorities(root, report, *, eligible, guard, started, cpu_started,
                         max_bytes=3 * GIB, max_files=5000, publication_bytes=64 * 1024**2,
                         publication_files=128):
    """Commit actual authority bytes, then check the full live guard last.

    A failed final write/guard cannot leave an accepted positive authority.
    Invalidation is best-effort under a broken filesystem; the owner also exits
    unsuccessfully, which the separate publisher independently requires.
    """
    try:
        guard()
        report["owner_wall_seconds"] = time.monotonic() - started
        report["owner_measured_cpu_seconds"] = cpu_seconds() - cpu_started
        report["timing_observation"] = "before_terminal_commit"
        report["complete"] = report["instrumentation_equal"] = eligible and not report["errors"]
        raw = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
        terminal = {"complete": report["complete"], "cleanup_complete": report["cleanup_complete"],
                    "required_wrapper_exit": 0, "result_sha256": hashlib.sha256(raw).hexdigest(),
                    "source_publication_qualified": False,
                    "owner_wall_seconds_at_terminal_start": time.monotonic() - started,
                    "owner_measured_cpu_seconds_at_terminal_start": cpu_seconds() - cpu_started}
        terminal_raw = (json.dumps(terminal, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
        observed = report["retained_inventory"]
        require(observed["bytes"] + len(raw) + len(terminal_raw) + 65536 + publication_bytes <= max_bytes
                and observed["file_count"] + 3 + publication_files <= max_files,
                "actual authority-inclusive retention cap")
        write(root / "result.json", report)
        write(root / "terminal.json", terminal, 65536)
        require(regular(root / "result.json").st_size == len(raw)
                and sha(root / "result.json") == terminal["result_sha256"]
                and regular(root / "terminal.json").st_size == len(terminal_raw)
                and sha(root / "terminal.json") == hashlib.sha256(terminal_raw).hexdigest(),
                "committed authority identity")
        # No positive I/O or expensive source work follows this full guard.
        # Its live CPU/wall reads are last, after resource/source/expiry checks.
        guard()
        return report["complete"]
    except BaseException as exc:
        report["complete"] = report["instrumentation_equal"] = False
        report["errors"].append({"stage": "terminal-closure", "type": type(exc).__name__})
        negative = {"complete": False, "cleanup_complete": report["cleanup_complete"],
                    "publication_failed": True, "stage": report["stage"], "type": type(exc).__name__}
        # Sentinel first: even a subsequent invalidation write fault cannot
        # promote a stale positive pair. The outer step also returns failure.
        try: write(root / "terminal-failure.json", negative, 65536)
        except BaseException: pass
        for name, value, limit in (("result.json", report, 8 * 1024**2),
                                   ("terminal.json", negative, 65536)):
            try: write(root / name, value, limit)
            except BaseException:
                try: (root / name).unlink(missing_ok=True)
                except OSError: pass
        return False


def execute(args):
    require(EXECUTION_APPROVAL is not None, "source-only execution approval is null")
    started, cpu_started = time.monotonic(), cpu_seconds()
    require(platform.python_version() == PYTHON and sys.platform == "linux", "registered hosted bootstrap")
    producer = context(os.environ)
    validate_paths(args)
    root = args.root.resolve()
    require(not root.exists() and not root.is_symlink(), "fresh owner output")
    root.mkdir(parents=True); (root / "logs").mkdir()
    report = {"complete": False, "instrumentation_equal": False, "stage": "bootstrap", "errors": [],
              "producer": producer, "actual_new_schemas": None, "completed_roles": [], "cleanup_complete": False}
    write(root / "result.json", report)
    write(root / "terminal.json", {"complete": False, "cleanup_complete": False, "required_wrapper_exit": 0})
    supervisor, core, reference, owned = None, None, None, None
    deadline, eligible = started + 2400, False
    try:
        report["runtime_flags"] = runtime_flags()
        core, inputs, reference, owned = modules(args.control.resolve(), args.controls.resolve())
        verify_workflow(args.control)
        own = owned["exact_near_screen_process"]
        legacy = owned["exact_near_screen_session"]
        deployment = owned["wealth_floor_hosted_deployment"].hosted_vm_precondition()
        report["deployment"] = deployment
        require(not args.prefix.exists() and not args.prefix.is_symlink(), "fresh study prefix")
        require(args.source.resolve() != args.control.resolve(), "separate090 producer checkout required")
        require(package_digest(args.source.resolve())[0] == core.PACKAGE, "producer source bytes")
        env = child_environment()
        report["loader"] = loader_identity()
        env["LD_LIBRARY_PATH"] = report["loader"]["child_LD_LIBRARY_PATH"]
        require(all(os.environ.get(k) == v for k, v in CAPS.items()), "owner startup thread/hash policy")
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
        with own.Cancellation() as cancellation, own.SubreaperLease() as lease:
            supervisor = own.make_supervisor(legacy, root, deadline, lease, cancellation)
            supervisor.admission("initial", 12, 4)
            def check():
                supervisor.check()
                require(cpu_seconds() - cpu_started <= 1800, "owner measured CPU budget")
            def command(label, argv, *, wall=300):
                check()
                # One actual affinity CPU bounds the aggregate CPU a private
                # command tree can consume within this remaining wall slice.
                remaining = int(1800 - (cpu_seconds() - cpu_started) - 30)
                require(remaining > 0, "owner CPU finalization reserve")
                selected_env = dict(env)
                if label in ("input-before", "input-after"):
                    selected_env["GH_TOKEN"] = command_environment(label)["GH_TOKEN"]
                supervisor.command(label, ["/usr/bin/timeout", "--signal=TERM", "--kill-after=5s",
                                          str(min(wall, remaining)), *argv],
                                   selected_env, root)
                check()
            for label, folder, expected in (("control", args.control, producer["GITHUB_SHA"]),
                                             ("producer", args.source, core.SOURCE),
                                             ("ownership", args.controls, reference["controls_source"])):
                command(label + "-source", ["git", "-C", str(folder), "rev-parse", "HEAD"])
                require(supervisor.last_stdout.strip().decode() == expected, "checkout identity")
                command(label + "-clean", ["git", "-C", str(folder), "status", "--porcelain=v1"])
                require(not supervisor.last_stdout, "dirty/untracked checkout refused")
            source_files = {name: sha(args.source / name) for name in ("pyproject.toml", "uv.lock")}
            report["stage"] = "environment"
            command("install-uv", python_command(sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                                    "--no-cache-dir", "--only-binary=:all:", "uv==" + UV))
            uv = Path(sys.executable).parent / "uv"
            require(regular(uv).st_size > 0, "installed uv executable")
            uv_sha = sha(uv)
            command("uv-version", [str(uv), "--version"])
            require(supervisor.last_stdout.decode().strip().split(" ", 2)[:2] == ["uv", UV], "actual installer version")
            env["UV_PROJECT_ENVIRONMENT"] = str(args.prefix)
            command("check-lock", [str(uv), "lock", "--project", str(args.source), "--check"])
            command("fresh-env", [str(uv), "sync", "--project", str(args.source), "--frozen", "--group", "dev",
                                   "--no-install-project", "--no-build", "--python", sys.executable])
            py = args.prefix / "bin/python"
            command("fresh-prefix-probe", python_command(py, "-c",
                "import importlib.util as u,json,platform,sys; "
                "assert platform.python_version()=='3.13.17'; "
                "assert u.find_spec('chronicler') is None and u.find_spec('chronicler_agents') is None; "
                "print(json.dumps({'prefix':sys.prefix,'project_native_absent':True}))"))
            require(inputs.strict_json(supervisor.last_stdout) == {"prefix": str(args.prefix), "project_native_absent": True},
                    "fresh physical environment")
            report["stage"] = "pure-preflight"
            pure_output = root / "pure-preflight"
            command("pure-preflight", python_command(py, str(args.control / "scripts/current090_profile_contracts.py"),
                    "--control", str(args.control), "--output", str(pure_output)), wall=110)
            pure = inputs.strict_json((pure_output / "receipt.json").read_bytes())
            admitted_control_sources = preflight_sources(args.control)
            verify_preflight(pure, admitted_control_sources)
            report["hosted_pure_preflight"] = pure
            report["stage"] = "inputs"
            pins = inputs.artifact_pins(reference)
            (root / "inputs").mkdir()
            script = args.control / "scripts/current090_profile_owner.py"
            control_cli = [str(script), "--control", str(args.control), "--controls", str(args.controls),
                           "--source", str(args.source), "--prefix", str(args.prefix)]
            command("input-before", python_command(sys.executable, *control_cli, "--child", "input-before",
                    "--input-dir", str(root / "inputs"), "--result", str(root / "input-before.json")), wall=120)
            initial_inputs = inputs.strict_json((root / "input-before.json").read_bytes())
            report["inputs_before"], report["wheel"] = initial_inputs["metadata"], initial_inputs["wheel"]
            wheel = root / "inputs" / reference["wheel"]["filename"]
            check()
            command("install-wheel", [str(uv), "pip", "install", "--no-deps", "--python", str(py), str(wheel)])
            require(sha(uv) == uv_sha, "installer changed")
            base = python_command(py, *control_cli)
            admission = root / "admission.json"
            report["stage"] = "fresh-schema-and-rng"
            command("bootstrap", [*base, "--child", "bootstrap", "--result", str(admission)])
            admitted = inputs.strict_json(admission.read_bytes())
            pin_schemas(admitted["schemas"], reference["historical_schema_reference"])
            report["actual_new_schemas"] = admitted["schemas"]
            (root / "roles").mkdir(); (root / "work").mkdir()
            for index, request in enumerate(core.schedule()):
                report["stage"] = "role:" + str(index)
                require(datetime.now(timezone.utc) < min(inputs.utc(pin.expiry) for pin in pins), "input expiry before role")
                role = root / "roles" / f"{index}-{request['case']}-{request['role']}"
                role.mkdir()
                logical = root / "work" / request["case"]
                result = role / "role.json"
                command("role-" + str(index), [*base, "--child", "role", "--admission", str(admission),
                        "--index", str(index), "--ordinary", str(logical), "--checkpoint", str(role / "final.ckpt"),
                        "--result", str(result)])
                facts = inputs.strict_json(result.read_bytes())
                require(facts["request"] == request and facts["boundary"]["turns_observed"] == 97, "actual role completion")
                # Only a quiescent successful child may have its ordinary tree archived.
                role_inventory = inventory(role, max_bytes=512 * 1024**2, guard=check)
                ordinary_inventory = inventory(logical, max_bytes=512 * 1024**2, guard=check)
                require(role_inventory["bytes"] + ordinary_inventory["bytes"] <= 512 * 1024**2, "whole role output cap")
                require(supervisor.cleanup_complete, "role ownership cleanup")
                os.rename(logical, role / "ordinary")
                require(inventory(role / "ordinary", guard=check) == ordinary_inventory
                        and not logical.exists(), "archival identity")
                report["completed_roles"].append({"index": index, "request": request, "actual_ticks": 97,
                                                  "role_files": role_inventory, "ordinary_files": ordinary_inventory})
                write(root / "result.json", report)
                if index % 2:
                    left = root / "roles" / f"{index-1}-{request['case']}-{core.schedule()[index-1]['role']}" / "role.json"
                    comparison = root / (request["case"] + "-comparison.json")
                    command("compare-" + request["case"], [*base, "--child", "compare", "--left", str(left),
                                                             "--right", str(result), "--result", str(comparison)])
                    require(inputs.strict_json(comparison.read_bytes())["instrumentation_equal"] is True,
                            "strict observer proof")
            report["stage"] = "final-admission"
            command("input-after", python_command(sys.executable, *control_cli, "--child", "input-after",
                    "--input-dir", str(root / "inputs"), "--result", str(root / "input-after.json")), wall=120)
            report["inputs_after"] = inputs.strict_json((root / "input-after.json").read_bytes())["metadata"]
            require(package_digest(args.source)[0] == core.PACKAGE and sha(uv) == uv_sha, "final source/installer")
            require({name: sha(args.source / name) for name in source_files} == source_files, "final lock/package source")
            require(sha(Path(admitted["native_file"]).resolve()) == core.NATIVE, "final installed native bytes")
            for label, folder, expected in (("control", args.control, producer["GITHUB_SHA"]),
                                             ("producer", args.source, core.SOURCE),
                                             ("ownership", args.controls, reference["controls_source"])):
                command(label + "-final-source", ["git", "-C", str(folder), "rev-parse", "HEAD"])
                require(supervisor.last_stdout.strip().decode() == expected, "final checkout identity")
                command(label + "-final-clean", ["git", "-C", str(folder), "status", "--porcelain=v1"])
                require(not supervisor.last_stdout, "final checkout dirty")
            check(); supervisor.check(final=True)
        require(not own.direct_children() and supervisor.cleanup_complete, "final owned quiescence")
        require(time.monotonic() <= deadline and cpu_seconds() - cpu_started <= 1800, "final budgets")
        report.update(cleanup_complete=True,
                      actual_generated_stepped_runs=6, actual_physics_ticks=582, unstepped_final_cp_decodes=6)
        eligible = True
    except BaseException as exc:
        report["errors"].append({"stage": report["stage"], "type": type(exc).__name__})
        report["complete"] = report["instrumentation_equal"] = False
    finally:
        report["owner_wall_seconds"] = time.monotonic() - started
        report["owner_measured_cpu_seconds"] = cpu_seconds() - cpu_started
        report["actual_failed_role_ticks"] = None if report["errors"] and report["stage"].startswith("role:") else 0
        # Never delete failed payloads or invent an unobserved final turn.
        def budget_guard():
            require(time.monotonic() <= deadline and cpu_seconds() - cpu_started <= 1800,
                    "finalization budget")
        try:
            report["retained_inventory"] = inventory(root,
                authority=("result.json", "terminal.json", "terminal-failure.json"), guard=budget_guard)
        except BaseException as exc:
            report["errors"].append({"stage": "retention", "type": type(exc).__name__})
            eligible = False
        def final_guard():
            if supervisor is not None: supervisor.check(final=True)
            if eligible:
                require(supervisor.cleanup_complete and not own.direct_children(), "terminal owned quiescence")
                require(preflight_sources(args.control) == admitted_control_sources, "terminal control source bytes")
                require(package_digest(args.source)[0] == core.PACKAGE
                        and {name: sha(args.source / name) for name in source_files} == source_files,
                        "terminal producer source bytes")
                require(sha(uv) == uv_sha, "terminal installer bytes")
                for name, row in reference["controls"].items():
                    require(sha(args.controls / "scripts" / name) == row["sha256"], "terminal helper bytes")
                require(sha(Path(admitted["native_file"]).resolve()) == core.NATIVE, "terminal native bytes")
                require({name: runtime_file(row["path"]) for name, row in admitted["runtime_files"].items()}
                        == admitted["runtime_files"], "terminal Python/profiler runtime bytes")
                require(datetime.now(timezone.utc) < min(inputs.utc(pin.expiry) for pin in pins),
                        "terminal input expiry")
            # Resource/source work above can itself consume time/CPU. These
            # live reads stay last, including after fsync of terminal.json.
            budget_guard()
        finalize_authorities(root, report, eligible=eligible, guard=final_guard,
                             started=started, cpu_started=cpu_started)
    return 0 if report["complete"] else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("control", "controls", "source", "prefix", "root", "result", "admission", "ordinary",
                 "checkpoint", "left", "right", "input-dir"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--child", choices=("input-before", "input-after", "bootstrap", "role", "compare"))
    parser.add_argument("--index", type=int)
    args = parser.parse_args(argv)
    require(EXECUTION_APPROVAL is not None, "source-only execution approval is null")
    if args.child:
        core, inputs, reference, owned = modules(args.control.resolve(), args.controls.resolve())
        child(args, core, inputs, reference, owned)
        return 0
    return execute(args)


if __name__ == "__main__":
    raise SystemExit(main())
