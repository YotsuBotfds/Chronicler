"""Own-source build receipts with actual controller identity kept separate.

No product/native import happens at module import. This reuses the existing
lower wheel receipt rather than forging GITHUB_SHA for a measured checkout.
"""
from __future__ import annotations

from importlib import metadata
import hashlib
import os
from pathlib import Path
import subprocess
import sys

import wholeturn_cache_protocol as p

CLASSES = ("AgentSimulator", "EcologySimulator", "PoliticsSimulator")
GITHUB_FIELDS = ("GITHUB_SHA", "GITHUB_REF", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_JOB")
DRIVERS = ("wholeturn_cache_protocol.py", "wholeturn_cache_build.py", "wholeturn_state_proof.py",
           "wholeturn_live_proof.py", "wholeturn_cache_identity.py", "wholeturn_cache_worker.py", "wholeturn_cache_pilot.py",
           "wholeturn_cache_records.py", "native_wheel_receipt.py", "wealth_floor_build_resources.py",
           "cities_identity.py", "turn_speed_identity.py")


def git(root, *args):
    return subprocess.check_output(["git", "--no-replace-objects", "-C", str(root), *args],
                                   env={**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0"})


def github_context(controller_root):
    p.require(os.environ.get("GITHUB_ACTIONS") == "true", "trusted hosted job required")
    values = {k: os.environ.get(k) for k in GITHUB_FIELDS}
    p.require(p.hex_value(values["GITHUB_SHA"], 40) and values["GITHUB_REF"] == p.RUN_REF
              and values["GITHUB_JOB"] == "wholeturn" and values["GITHUB_RUN_ATTEMPT"] == "1"
              and type(values["GITHUB_RUN_ID"]) is str and values["GITHUB_RUN_ID"].isdigit()
              and int(values["GITHUB_RUN_ID"]) > 0, "exact hosted run/ref/attempt")
    p.require(git(controller_root, "rev-parse", "HEAD").decode().strip() == values["GITHUB_SHA"],
              "actual controller checkout")
    p.require(not git(controller_root, "status", "--porcelain", "--untracked-files=all", "--", "scripts", "docs/experiments").strip(),
              "dirty controller source")
    current = (Path(controller_root)/p.REGISTRATION).read_bytes()
    p.require(git(controller_root, "show", "HEAD:"+p.REGISTRATION) == current,
              "registration is not committed controller source")
    return values


def driver_pins(controller_root):
    return {name: p.pin(Path(controller_root)/"scripts"/name, 256*p.MIB)
            for name in DRIVERS}


def source_manifest(root, expected):
    root = Path(root).resolve(strict=True)
    p.require(git(root, "rev-parse", "HEAD").decode().strip() == expected["source_commit"],
              "measured exact source")
    p.require(git(root, "rev-parse", "HEAD:chronicler-agents").decode().strip() == expected["native_tree"],
              "measured native subtree")
    p.require(not git(root, "status", "--porcelain", "--untracked-files=all", "--", "src", "scripts", "tests",
                      "chronicler-agents", "pyproject.toml", "uv.lock").strip(), "dirty measured source")
    names = git(root, "ls-files", "-z", "--", "src", "scripts", "tests", "chronicler-agents",
                "pyproject.toml", "uv.lock").decode().split("\0")
    files = {n: p.pin(root/n, 64*p.MIB) for n in names if n}
    return {"files": files, "count": len(files),
            "digest": hashlib.sha256(p.canonical(files)).hexdigest()}


def record_build(controller_root, measured_root, arm, wheel_dir, output):
    registration = p.load_registration(controller_root)  # null candidate refuses before runtime
    p.require(arm in ("baseline", "candidate"), "measured role")
    context = github_context(controller_root)
    expected = registration[arm]
    measured_root, wheel_dir = Path(measured_root).resolve(strict=True), Path(wheel_dir).resolve(strict=True)
    source = source_manifest(measured_root, expected)
    p.require(len(list(wheel_dir.glob("*.whl"))) == 1, "one own fresh wheel")
    # Only after committed source/candidate/context admission.
    sys.path.insert(0, str(measured_root/"src"))
    from importlib import import_module
    from importlib.machinery import ExtensionFileLoader, EXTENSION_SUFFIXES
    package = import_module("chronicler_agents")
    compiled = import_module("chronicler_agents.chronicler_agents")
    native_path = Path(compiled.__file__).resolve(strict=True)
    p.require(type(compiled.__loader__) is ExtensionFileLoader
              and str(native_path).endswith(tuple(EXTENSION_SUFFIXES))
              and native_path.is_relative_to(Path(sys.prefix).resolve()), "own compiled venv origin")
    p.require(all(isinstance(getattr(package, n, None), type)
                  and getattr(package, n) is getattr(compiled, n, None) for n in CLASSES),
              "real compiled class exports")
    from native_wheel_receipt import wheel_receipt
    wheel = wheel_receipt(wheel_dir, native_path, expected["source_commit"])
    p.require(wheel["wheel"]["bytes"] <= 8*p.MIB, "own wheel byte bound")
    p.require(p.pin(native_path, 64*p.MIB) == {
        k: wheel["installed_native"][k] for k in ("bytes", "sha256")},
        "installed native changed before own build record")
    schemas = {}
    for name in CLASSES:
        row = getattr(package, name).checkpoint_schema()
        p.require(type(row) is tuple and len(row) == 3 and type(row[0]) is int and row[0] > 0
                  and p.hex_value(row[1], 16) and type(row[2]) is str
                  and 0 < len(row[2].encode()) <= 65536, "all3 actual raw schema tuples")
        schemas[name] = list(row)
    distributions = {d.metadata["Name"].lower().replace("_", "-"): d.version
                     for d in metadata.distributions() if d.metadata["Name"].lower() != "maturin"}
    package_stream = b"".join(name.removeprefix("src/chronicler/").encode()+b"\0"
                              + entry["sha256"].encode()+b"\n"
                              for name, entry in sorted(source["files"].items())
                              if name.startswith("src/chronicler/") and name.endswith(".py"))
    value = {"kind": "MATCHED_WHOLETURN_OWN_BUILD", "protocol": p.PROTOCOL, "arm": arm,
             **expected, "controller_commit": context["GITHUB_SHA"], "github": context,
             "driver_pins": driver_pins(controller_root), "registration": p.pin(Path(controller_root)/p.REGISTRATION),
             "measured_root": str(measured_root), "venv_prefix": str(Path(sys.prefix).resolve()),
             "worker_python": str(Path(sys.executable)), "native_file": str(native_path),
             "wheel_dir": str(wheel_dir), "wheel_receipt": wheel, "schemas": schemas,
             "sealed_source": source, "python": sys.version,
             "package_digest": hashlib.sha256(package_stream).hexdigest(),
             "measured_HEAD": p.pin(measured_root/".git/HEAD", 4096),
             "python_binary": p.pin(Path(sys.executable).resolve(), 128*p.MIB),
             "distributions": distributions,
             "uv_lock": p.pin(measured_root/"uv.lock"),
             "cargo_lock": p.pin(measured_root/"chronicler-agents/Cargo.lock"),
             "cargo_manifest": p.pin(measured_root/"chronicler-agents/Cargo.toml"),
             "build_flags": {k: os.environ.get(k, "") for k in
                             ("CARGO_BUILD_JOBS", "CARGO_INCREMENTAL", "RUSTFLAGS", "CARGO_TARGET_DIR")},
             "toolchain": {name: p.pin(Path(output).parent/name, 4096) for name in
                           ("rustc.txt", "cargo.txt", "maturin.txt", "uv.txt")},
             "scope": "Own fresh source/build; no reproducibility, speed or science qualification."}
    p.write_new(output, value, 512*1024)
    return value


def validate_builds(registration, builds, context, drivers):
    p.require(set(builds) == {"baseline", "candidate"}, "two measured builds")
    for arm, value in builds.items():
        p.require(value["kind"] == "MATCHED_WHOLETURN_OWN_BUILD" and value["protocol"] == p.PROTOCOL
                  and value["arm"] == arm and value["source_commit"] == registration[arm]["source_commit"]
                  and value["native_tree"] == registration[arm]["native_tree"], "exact measured build whitelist")
        p.require(value["github"] == context and value["controller_commit"] == context["GITHUB_SHA"]
                  and value["driver_pins"] == drivers, "same actual controller/job/driver")
    a, b = builds["baseline"], builds["candidate"]
    for field in ("github", "registration", "python", "python_binary", "distributions", "uv_lock",
                  "cargo_lock", "cargo_manifest", "toolchain", "schemas"):
        p.require(a[field] == b[field], "unequal paired build environment/schema: "+field)
    for field in ("CARGO_BUILD_JOBS", "CARGO_INCREMENTAL", "RUSTFLAGS"):
        p.require(a["build_flags"][field] == b["build_flags"][field], "unequal build flags")
    p.require(a["build_flags"]["CARGO_BUILD_JOBS"] == "1"
              and a["build_flags"]["CARGO_INCREMENTAL"] == "0", "fresh serial build policy")
    for field in ("measured_root", "venv_prefix", "wheel_dir"):
        p.require(a[field] != b[field], "independent paired roots")
    p.require(a["build_flags"]["CARGO_TARGET_DIR"] != b["build_flags"]["CARGO_TARGET_DIR"],
              "independent Cargo targets")
    return builds


def recheck_build(value):
    stage = "source"
    try:
        p.require(source_manifest(value["measured_root"], value) == value["sealed_source"],
                  "measured source changed")
        stage = "installed_native"
        p.require(p.pin(value["native_file"], 64*p.MIB) == {
            k: value["wheel_receipt"]["installed_native"][k] for k in ("bytes", "sha256")},
            "installed native changed")
        stage = "wheel"
        wheel = value["wheel_receipt"]["wheel"]
        p.require(p.pin(Path(value["wheel_dir"])/wheel["filename"], 8*p.MIB) == {
            k: wheel[k] for k in ("bytes", "sha256")}, "own wheel changed")
    except Exception as exc:
        exc.build_recheck_stage = stage
        raise


def recheck_files(value):
    """Post-audit closure uses existing pins, without launching Git."""
    root = Path(value["measured_root"])
    p.require(p.pin(root/".git/HEAD", 4096) == value["measured_HEAD"], "measured HEAD changed")
    for name, expected in value["sealed_source"]["files"].items():
        p.require(p.pin(root/name, 64*p.MIB) == expected, "measured source changed: "+name)
    native = value["wheel_receipt"]["installed_native"]
    p.require(p.pin(value["native_file"], 64*p.MIB) == {k: native[k] for k in ("bytes", "sha256")},
              "native changed after execution")
    wheel = value["wheel_receipt"]["wheel"]
    p.require(p.pin(Path(value["wheel_dir"])/wheel["filename"], 8*p.MIB) == {
        k: wheel[k] for k in ("bytes", "sha256")}, "wheel changed after execution")
