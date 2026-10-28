#!/usr/bin/env python3
"""Fixed, source-qualified default export parity; not a speed or checkpoint gate."""
from __future__ import annotations
import argparse
import ast
import hashlib
import importlib.machinery
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
import zipfile

BASE = "2f9d618b70f3304c02dcaeef12996b4a99e074c0"
CANDIDATE = "d0281e5f57c508f27cea1676f36e0e6ed1225c9d"
SCRIPT = Path(__file__).resolve()
GIB = 1024 ** 3
WALL_SECONDS = 80 * 60
CAPS = {key: "1" for key in (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS",
    "GOTO_NUM_THREADS", "RAYON_NUM_THREADS", "PYTHON_CPU_COUNT", "CARGO_BUILD_JOBS",
)}
CASES = {
    "off_s42": (["--seed", "42", "--turns", "300", "--agents", "off"], 0),
    "off_s7": (["--seed", "7", "--turns", "300", "--agents", "off"], 0),
    "hybrid_s42": (["--seed", "42", "--turns", "200", "--agents", "hybrid", "--validation-sidecar"], 0),
    "hybrid_s7": (["--seed", "7", "--turns", "200", "--agents", "hybrid", "--validation-sidecar"], 0),
    "hybrid_s1234": (["--seed", "1234", "--turns", "200", "--agents", "hybrid"], 0),
    "proc48_hybrid_s42": (["--seed", "42", "--turns", "150", "--regions", "48", "--civs", "10", "--agents", "hybrid", "--validation-sidecar"], 0),
    "proc48_off_s7": (["--seed", "7", "--turns", "200", "--regions", "48", "--civs", "10", "--agents", "off"], 0),
    "scaled22k_s42": (["--seed", "42", "--turns", "30", "--regions", "12", "--civs", "4", "--agents", "hybrid", "--validation-sidecar"], 18800),
    "scaled52k_s7": (["--seed", "7", "--turns", "20", "--regions", "12", "--civs", "4", "--agents", "hybrid"], 43700),
}
COMMON = {"chronicle.md", "state.json", "chronicle_bundle.json",
          "state.historiography.json", "state.languages.json"}
SIDECARS = {"validation_needs.arrow", "validation_relationships.arrow",
            "validation_memory_signatures.arrow", "validation_summary.json",
            "validation_community_summary.json"}
STAMP = re.compile(rb'"generated_at": ?"[^"]*"')


class Refusal(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise Refusal(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def strict_json(raw):
    def pairs(rows):
        out = {}
        for key, value in rows:
            if key in out:
                raise Refusal("duplicate JSON key")
            out[key] = value
        return out

    def number(token):
        value = float(token)
        require(math.isfinite(value), "non-finite JSON number")
        return value

    def constant(token):
        raise Refusal("non-finite JSON constant")
    return json.loads(raw, object_pairs_hook=pairs, parse_float=number, parse_constant=constant)


def timestamp_paths(value, path=()):
    result = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "generated_at":
                result.append(path + (key,))
            result.extend(timestamp_paths(child, path + (key,)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.extend(timestamp_paths(child, path + (index,)))
    return result


def require_stamp(raw):
    parsed = strict_json(raw)
    require(timestamp_paths(parsed) == [("metadata", "generated_at")],
            "only metadata.generated_at may be normalized")
    require(isinstance(parsed["metadata"]["generated_at"], str), "timestamp must be a string")
    require(len(STAMP.findall(raw)) == 1, "raw timestamp normalization must match exactly once")


def case_contract(name, files, state, bundle):
    cli, target = CASES[name]
    value = lambda flag, default=None: cli[cli.index(flag) + 1] if flag in cli else default
    turns, seed = int(value("--turns")), int(value("--seed"))
    mode, regions, civs = value("--agents"), int(value("--regions", 8)), int(value("--civs", 4))
    required = set(COMMON)
    if mode == "hybrid":
        required.add("agent_events.arrow")
    if "--validation-sidecar" in cli:
        required.update(SIDECARS)
    require(required <= files, "missing required exports: " + repr(sorted(required - files)))
    require(any(name.startswith("memories_") and name.endswith(".json") for name in files),
            "memory stream exports missing")
    for world in (state, bundle["world_state"]):
        require(type(world.get("turn")) is int and world["turn"] == turns, "incomplete world horizon")
        require(type(world.get("seed")) is int and world["seed"] == seed, "wrong world seed")
        require(world.get("agent_mode") == mode, "wrong agent mode")
        require(len(world["regions"]) == regions, "wrong region shape")
        require(len(world["civilizations"]) >= civs, "starting civilizations missing")
    metadata = bundle["metadata"]
    require(metadata.get("seed") == seed and metadata.get("total_turns") == turns, "wrong bundle horizon")
    require([row["turn"] for row in bundle["history"]] == list(range(1, turns + 1)),
            "history must cover every completed turn")
    return {"seed": seed, "turns": turns, "mode": mode, "regions": regions,
            "initial_civs_requested": civs, "final_civs": len(state["civilizations"]),
            "scale_target": target, "files": len(files)}


def require_case_sets(baseline, candidate):
    require(set(baseline) == set(CASES) and set(candidate) == set(CASES),
            "case directory set differs from registration")


def payload_inventory(root, exclude=()):
    result = {}
    for path in sorted(Path(root).rglob("*")):
        relative = path.relative_to(root).as_posix()
        require(not path.is_symlink(), "symlink in evidence: " + relative)
        if path.is_dir():
            continue
        require(stat.S_ISREG(path.stat().st_mode), "nonregular evidence file")
        if relative not in exclude:
            result[relative] = {"bytes": path.stat().st_size, "sha256": sha(path)}
    return result


def source_snapshot(root, expected, deadline):
    def git(*args):
        remaining = deadline - time.monotonic()
        require(remaining > 0, "aggregate child wall limit reached")
        return subprocess.check_output(["git", "-c", "core.fsmonitor=false", "-C", str(root), *args],
                                       timeout=min(30, remaining))
    require(git("rev-parse", "HEAD").decode().strip() == expected, "wrong source commit")
    require(not git("status", "--porcelain=v1", "--untracked-files=all"), "source is not clean")
    files = {}
    for row in git("ls-files", "--stage", "-z").split(b"\0"):
        if not row:
            continue
        prefix, name = row.decode("utf-8").split("\t", 1)
        mode, blob, stage = prefix.split()
        path = root / name
        require(stage == "0" and mode in ("100644", "100755"), "unsupported tracked source entry")
        require(not path.is_symlink() and path.is_file(), "source entry is not a regular file")
        require(bool(path.stat().st_mode & stat.S_IXUSR) == (mode == "100755"), "source executable mode changed")
        files[name] = {"sha256": sha(path), "bytes": path.stat().st_size,
                       "mode": stat.S_IMODE(path.stat().st_mode), "blob": blob}
    return {"sha": expected, "crate_tree": git("rev-parse", "HEAD:chronicler-agents").decode().strip(),
            "files": files}


def require_matrix(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    matches = [node.value for node in tree.body
               if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
               and node.target.id == "CASES"]
    require(len(matches) == 1 and ast.literal_eval(matches[0]) == CASES, "case matrix changed")


def resources(path):
    available = None
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            available = int(line.split()[1]) * 1024
    require(available is not None, "MemAvailable unavailable")
    limits = []
    observed_v2 = False
    # Conservatively count charged cgroup page cache as used; do not invent reclaimable RAM.
    for line in Path("/proc/self/cgroup").read_text().splitlines():
        group, controllers, relative = line.split(":", 2)
        if group != "0" or controllers:
            continue
        observed_v2 = True
        require(relative.startswith("/") and ".." not in Path(relative).parts, "invalid cgroup path")
        current = Path("/sys/fs/cgroup").joinpath(*Path(relative).parts[1:])
        while True:
            maximum, usage = current / "memory.max", current / "memory.current"
            if maximum.is_file() and usage.is_file():
                cap, used = maximum.read_text().strip(), int(usage.read_text())
                if cap != "max":
                    limits.append({"path": str(current), "max": int(cap), "current": used})
            if current == Path("/sys/fs/cgroup"):
                break
            current = current.parent
    require(observed_v2, "cgroup v2 resource visibility required")
    ram = min([available] + [max(0, row["max"] - row["current"]) for row in limits])
    return {"disk_free": shutil.disk_usage(path).free, "ram_available": ram,
            "host_mem_available": available, "cgroup_limits": limits}


def admit(observation, disk, ram):
    require(observation["disk_free"] >= disk * GIB, "disk admission refused")
    require(observation["ram_available"] >= ram * GIB, "RAM admission refused")


def process_stat(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return {"pid": int(pid), "state": fields[0], "pgrp": int(fields[2]),
                "session": int(fields[3]), "birth": int(fields[19])}
    except (FileNotFoundError, ProcessLookupError):
        return None


def session_live(sid):
    rows = []
    for path in Path("/proc").iterdir():
        if path.name.isdecimal():
            row = process_stat(path.name)
            if row and row["session"] == sid and row["state"] not in ("Z", "X"):
                rows.append(row)
    return rows


class Supervisor:
    def __init__(self, root, deadline):
        self.root, self.deadline = root, deadline

    def event(self, kind, **fields):
        with (self.root / "progress.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"at": time.time(), "event": kind, **fields}, allow_nan=False) + "\n")
            stream.flush()

    def admission(self, phase, disk, ram):
        row = resources(self.root)
        self.event("resources", phase=phase, **row)
        admit(row, disk, ram)

    def command(self, label, command, env, cwd):
        require(time.monotonic() < self.deadline, "aggregate 80-minute child wall limit reached")
        self.admission(label + ":before", 3, 1)
        self.event("child_start", label=label, command=command, cwd=str(cwd))
        log = self.root / "logs" / (label + ".log")
        with log.open("wb") as stream:
            child = subprocess.Popen(command, cwd=cwd, env=env, stdout=stream,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            # Do not poll/wait/communicate until the private session is quiescent.
            owner = process_stat(child.pid)
            boot = Path("/proc/sys/kernel/random/boot_id").read_text()
            require(owner and owner["session"] == child.pid and owner["pgrp"] == child.pid,
                    "private child session could not be established")
            failed = None
            try:
                while True:
                    if os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT):
                        break
                    require(time.monotonic() < self.deadline, "aggregate 80-minute child wall limit reached")
                    self.admission(label + ":running", 3, 1)
                    time.sleep(1)
                require(not session_live(child.pid), "child exited with live same-session descendants")
            except Exception as exc:
                failed = exc
            finally:
                live = session_live(child.pid)
                if live:
                    current = process_stat(child.pid)
                    require(current and current["birth"] == owner["birth"] and
                            current["session"] == child.pid and
                            Path("/proc/sys/kernel/random/boot_id").read_text() == boot,
                            "child ownership lease changed; cleanup refused")
                    require(all(row["pgrp"] == child.pid for row in live),
                            "unexpected child process group; cleanup uncertain")
                    for sig, seconds in ((signal.SIGTERM, 10), (signal.SIGKILL, 5)):
                        try:
                            os.killpg(child.pid, sig)
                        except ProcessLookupError:
                            pass
                        end = time.monotonic() + seconds
                        while session_live(child.pid) and time.monotonic() < end:
                            time.sleep(.1)
                        if not session_live(child.pid):
                            break
                remaining = session_live(child.pid)
                self.event("child_cleanup", label=label, same_session_live=remaining)
                require(not remaining, "live owned writers remain; cleanup incomplete")
                child.wait(timeout=2)
                self.event("child_exit", label=label, returncode=child.returncode)
            if failed:
                raise failed
            require(child.returncode == 0, label + " exited " + str(child.returncode))


def probe(args):
    import chronicler
    import chronicler_agents as package
    import chronicler_agents.chronicler_agents as native
    from chronicler.batch_manifest import source_identity, native_identity, environment_identity
    require(sys.version_info[:2] == (3, 13), "Python 3.13 required")
    require(Path(sys.prefix).resolve() == Path(args.venv).resolve(), "wrong Python environment")
    require(Path(chronicler.__file__).resolve() == Path(args.source_root).resolve() / "src/chronicler/__init__.py",
            "wrong running package source")
    source = source_identity()
    require(source["git_sha"] == args.expected_sha, "wrong imported source revision")
    require(Path(source["package_dir"]).resolve() == Path(args.source_root).resolve() / "src/chronicler",
            "wrong imported package directory")
    origin = Path(native.__file__).resolve()
    require(str(origin).endswith(tuple(importlib.machinery.EXTENSION_SUFFIXES)), "native module is not compiled")
    require(origin.is_relative_to(Path(args.venv).resolve()), "native module is outside qualified environment")
    schemas = {}
    for name in ("AgentSimulator", "EcologySimulator", "PoliticsSimulator"):
        cls = getattr(package, name)
        require(isinstance(cls, type) and cls is getattr(native, name), "native class export mismatch")
        version, fingerprint, schema = cls.checkpoint_schema()
        schemas[name] = {"version": version, "fingerprint": fingerprint,
                         "schema_sha256": hashlib.sha256(schema.encode()).hexdigest()}
    require(len(os.sched_getaffinity(0)) == 1, "world process affinity is not one CPU")
    require(all(os.environ.get(key) == value for key, value in CAPS.items()), "thread cap changed")
    write(args.out, {"source": source, "native": native_identity(), "schemas": schemas,
                     "source_file": chronicler.__file__, "native_file": native.__file__,
                     "environment": environment_identity(), "affinity": sorted(os.sched_getaffinity(0)),
                     "prefix": sys.prefix})


def inspect_case(args):
    from chronicler.bundle_codec import load_bundle
    root = Path(args.case_root)
    files = payload_inventory(root)
    raw = (root / "chronicle_bundle.json").read_bytes()
    require_stamp(raw)
    state = strict_json((root / "state.json").read_bytes())
    summary = case_contract(args.case, set(files), state, load_bundle(root / "chronicle_bundle.json"))
    for name in COMMON | SIDECARS | {name for name in files if name.startswith("memories_")}:
        if name in files:
            require(files[name]["bytes"] > 0, "empty required export: " + name)
    if "agent_events.arrow" in files:
        require(files["agent_events.arrow"]["bytes"] > 0, "empty agent event export")
    write(args.out, {**summary, "files": files})


def execute(args):
    root = Path(args.evidence).resolve()
    root.mkdir(parents=True, exist_ok=False)
    for folder in ("logs", "probes", "audits", "raw", "wheels", "native"):
        (root / folder).mkdir()
    deadline = time.monotonic() + WALL_SECONDS
    supervisor = Supervisor(root, deadline)
    environment = dict(os.environ, **CAPS, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1",
                       PYTHONNOUSERSITE="1", CHRONICLER_QUIET="1")
    before = {}
    rows = [{"arm": arm, "case": name, "status": "not_attempted"} for arm in ("baseline", "candidate") for name in CASES]
    report = {"qualified": False, "baseline": BASE, "candidate": CANDIDATE, "cases": rows,
              "normalization": "metadata.generated_at only; logs/run_manifest.json excluded by existing comparator",
              "limitations": ["exports only; checkpoint/native/RNG state bytes not captured",
                              "no timing/speed or feature-efficacy claim", "one fixed environment and case matrix"]}
    native_file = wheel = None
    wheel_sha = native_expected = None
    roots = {"baseline": Path(args.baseline_root).resolve(), "candidate": Path(args.candidate_root).resolve(),
             "control": SCRIPT.parents[1]}
    expected = {"baseline": BASE, "candidate": CANDIDATE, "control": os.environ["GITHUB_SHA"]}
    py = str(Path(args.python).absolute())
    venv = Path(py).parent.parent
    try:
        require(not [key for key in os.environ if key.startswith("CHRONICLER_") and key != "CHRONICLER_QUIET"],
                "unexpected simulation environment switch")
        allowed = os.sched_getaffinity(0)
        os.sched_setaffinity(0, {min(allowed)})
        require(len(set(roots.values())) == 3, "source checkouts must be separate")
        require(all(not root.is_relative_to(source) for source in roots.values()), "evidence must be external")
        before = {name: source_snapshot(source, expected[name], deadline) for name, source in roots.items()}
        base, candidate = roots["baseline"], roots["candidate"]
        require(before["baseline"]["crate_tree"] == before["candidate"]["crate_tree"], "crate trees differ")
        for relative in ("uv.lock", "pyproject.toml", "scripts/turn_speed_identity.py", "scripts/cities_identity.py"):
            require(sha(base / relative) == sha(candidate / relative), "shared input differs: " + relative)
        for source in (base, candidate):
            require_matrix(source / "scripts/turn_speed_identity.py")
        write(root / "freeze.json", {"sources": before, "script_sha256": sha(SCRIPT),
                                     "matrix": CASES, "thread_caps": CAPS, "affinity": sorted(os.sched_getaffinity(0))})
        target = Path(os.environ["CARGO_TARGET_DIR"]).resolve()
        require(not target.exists() and all(not target.is_relative_to(source) for source in roots.values()),
                "Cargo build target must be fresh and external")
        environment["CARGO_TARGET_DIR"] = str(target)
        for label, command in (
            ("rustc-version", ["rustc", "--version", "--verbose"]),
            ("cargo-version", ["cargo", "--version"]),
            ("maturin-version", [py, "-m", "maturin", "--version"]),
            ("uv-version", ["uv", "--version"]),
        ):
            supervisor.command(label, command, environment, root)
        supervisor.admission("before_build", 12, 2)
        supervisor.command("build", [py, "-m", "maturin", "build", "--release", "--locked",
                           "--manifest-path", str(candidate / "chronicler-agents/Cargo.toml"),
                           "--out", str(root / "wheels")], environment, root)
        wheels = list((root / "wheels").glob("*.whl"))
        require(len(wheels) == 1, "exactly one fresh wheel required")
        wheel = wheels[0]
        wheel_sha = sha(wheel)
        with zipfile.ZipFile(wheel) as archive:
            members = [name for name in archive.namelist()
                       if name.endswith(tuple(importlib.machinery.EXTENSION_SUFFIXES))]
            require(len(members) == 1, "exactly one compiled wheel member required")
            wheel_native_sha = hashlib.sha256(archive.read(members[0])).hexdigest()
            native_expected = wheel_native_sha
        supervisor.command("install", ["uv", "pip", "install", "--no-deps", "--python", py, str(wheel)],
                           environment, root)
        supervisor.admission("after_build", 6, 2)
        native_sha, schemas, package_digests = None, None, {}
        for row in rows:
            arm, name = row["arm"], row["case"]
            source = roots[arm]
            arm_root = root / "raw" / arm
            arm_root.mkdir(exist_ok=True)
            env = dict(environment, PYTHONPATH=str(source / "src"))
            for stage in ("before", "after"):
                output = root / "probes" / (arm + "-" + name + "-" + stage + ".json")
                supervisor.command("probe-" + arm + "-" + name + "-" + stage,
                    [py, str(SCRIPT), "probe", "--source-root", str(source), "--expected-sha", expected[arm],
                     "--venv", str(venv), "--out", str(output)], env, arm_root)
                identity = strict_json(output.read_bytes())
                require(identity["native"]["sha256"] == wheel_native_sha, "loaded binary differs from built wheel")
                if native_sha is None:
                    native_sha, schemas = identity["native"]["sha256"], identity["schemas"]
                    native_file = Path(identity["native"]["module_file"])
                    shutil.copyfile(native_file, root / "native" / native_file.name)
                require(identity["native"]["sha256"] == native_sha and identity["schemas"] == schemas,
                        "native identity changed")
                digest = identity["source"]["package_digest"]
                require(package_digests.setdefault(arm, digest) == digest, "running package digest changed")
                if stage == "before":
                    row["status"] = "started"
                    supervisor.command("world-" + arm + "-" + name,
                        [py, str(source / "scripts/turn_speed_identity.py"), "run", str(arm_root),
                         "--source-root", str(source), "--case", name], env, arm_root)
                    which = (arm_root / "which.txt").read_text()
                    require(which == "chronicler " + identity["source_file"] + "\nnative " +
                            identity["native_file"] + " " + native_sha + "\n", "driver native/source diagnostic failed")
                    (root / "probes" / (arm + "-" + name + "-which.txt")).write_text(which)
            audit = root / "audits" / (arm + "-" + name + ".json")
            supervisor.command("audit-" + arm + "-" + name,
                [py, str(SCRIPT), "inspect", "--case-root", str(arm_root / name),
                 "--case", name, "--out", str(audit)], env, arm_root)
            row["status"] = "complete"
            supervisor.event("case_complete", arm=arm, case=name, audit_sha256=sha(audit))
        require_case_sets(*[{path.name for path in (root / "raw" / arm).iterdir() if path.is_dir()}
                            for arm in ("baseline", "candidate")])
        supervisor.command("compare", [py, str(candidate / "scripts/turn_speed_identity.py"), "compare",
                           str(root / "raw/baseline"), str(root / "raw/candidate")],
                           dict(environment, PYTHONPATH=str(candidate / "src")), root)
        report.update(qualified=True, wheel_sha256=wheel_sha, native_sha256=native_sha,
                      schemas=schemas, package_digests=package_digests)
    except Exception as exc:
        report["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        try:
            after = {name: source_snapshot(source, expected[name], deadline) for name, source in roots.items()}
            write(root / "sources-after.json", after)
            require(before == after, "tracked source bytes/modes or source standing changed")
            if native_file is not None:
                require(sha(native_file) == native_expected, "installed native binary changed")
            if wheel is not None:
                require(sha(wheel) == wheel_sha, "built wheel changed")
            require(time.monotonic() <= deadline, "aggregate child wall budget exceeded")
        except Exception as exc:
            report["qualified"] = False
            report["final_identity_error"] = type(exc).__name__ + ": " + str(exc)
        for row in rows:
            if row["status"] == "started":
                row["status"] = "failed"
        report["elapsed_wall_seconds"] = WALL_SECONDS - max(0, deadline - time.monotonic())
        write(root / "result.json", report)
        write(root / "inventory.json", payload_inventory(root, exclude=("inventory.json",)))
    print(json.dumps({"qualified": report["qualified"], "error": report.get("error"),
                      "final_identity_error": report.get("final_identity_error")}), flush=True)
    return 0 if report["qualified"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    for name in ("baseline-root", "candidate-root", "python", "evidence"):
        run.add_argument("--" + name, required=True)
    probe_parser = commands.add_parser("probe")
    for name in ("source-root", "expected-sha", "venv", "out"):
        probe_parser.add_argument("--" + name, required=True)
    inspect_parser = commands.add_parser("inspect")
    for name in ("case-root", "case", "out"):
        inspect_parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    if args.command == "probe":
        probe(args)
        return 0
    if args.command == "inspect":
        inspect_case(args)
        return 0
    return execute(args)


if __name__ == "__main__":
    raise SystemExit(main())
