"""Detached admitted worker; no product/native/profiler import at module load."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time

import wholeturn_build as build
import wholeturn_protocol as p
import wholeturn_state_proof as proof


class Journal:
    def __init__(self, path):
        self.stream = Path(path).open("xb")

    def emit(self, value):
        # Real endpoints are int nanoseconds. Malformed/failing samples have
        # explicit JSON-safe tags; numerical validation follows this write.
        body = p.canonical(value)
        p.require(len(body) <= 65536, "journal row bound")
        self.stream.write(body)
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def close(self):
        self.stream.close()


class Boundary:
    """Only the existing late turn-boundary seam; no native proxy or tick call."""
    def __init__(self, profiled, windows, journal, factory, *, cpu=time.process_time_ns,
                 wall=time.perf_counter_ns):
        self.profiled, self.windows, self.journal = profiled, windows, journal
        self.cpu, self.wall = cpu, wall
        self.profiles = [factory(timer=time.process_time, subcalls=True, builtins=True)
                         for _ in windows]
        self.last, self.active, self.save, self.config = 0, None, None, None
        self.starts, self.records = {}, []

    def bind(self, save, run_config):
        p.require(self.save is None and callable(save) and type(run_config) is dict, "bind once")
        self.save, self.config = save, run_config

    def live_record(self):
        return None

    def turn_end(self, world):
        turn = world.turn
        p.require(type(turn) is int and turn == self.last+1 and turn <= 200,
                  "complete ordered World boundaries")
        self.last = turn  # record the witnessed boundary even if its clock fails
        for i, (start, end) in enumerate(self.windows):
            if turn == end:
                p.require(self.active == i if self.profiled else self.active is None,
                          "profile window state")
                if self.profiled:
                    self.profiles[i].disable()
                begin = self.starts[i]
                raw = {"CPU_start_ns": begin[0], "CPU_end_ns": p.sample_ns(self.cpu),
                       "wall_start_ns": begin[1], "wall_end_ns": p.sample_ns(self.wall)}
                self.journal.emit({"kind": "WINDOW_RAW", "start": start, "end": end, **raw})
                row = p.interval(raw)
                self.records.append({"start": start, "end": end, **row})
                p.require(row["numerically_valid"], "nonpositive/malformed window interval")
                self.active = None
        for i, (start, _end) in enumerate(self.windows):
            if turn == start:
                self.starts[i] = (p.sample_ns(self.cpu), p.sample_ns(self.wall))
                self.journal.emit({"kind": "WINDOW_START_RAW", "start": start,
                                   "CPU_start_ns": self.starts[i][0], "wall_start_ns": self.starts[i][1]})
                p.require(all(type(v) is int and 0 <= v < 2**63 for v in self.starts[i]),
                          "malformed window starting clock")
                if self.profiled:
                    self.active = i
                    self.profiles[i].enable()
        return False

    def stop(self):
        first = None
        for profile in self.profiles:
            try:
                profile.disable()
            except BaseException as exc:
                first = first or exc
        self.active = None
        if first is not None:
            raise first

    def details(self):
        result = []
        if self.profiled:
            for i, profiler in enumerate(self.profiles):
                profiler.create_stats()
                p.require(len(profiler.stats) <= 20000, "profile function row cap")
                rows, edges = [], []
                for (filename, line, name), (primitive, calls, own, cumulative, callers) in sorted(profiler.stats.items()):
                    p.require(len(filename.encode()) <= 2048 and len(name.encode()) <= 2048,
                              "profile label cap")
                    p.require(all(type(x) in (int, float) and x >= 0 and x < float("inf")
                                  for x in (own, cumulative)), "profile time shape")
                    rows.append({"filename": filename, "line": line, "function": name,
                                 "primitive_calls": primitive, "calls": calls,
                                 "self_CPU_seconds": own, "cumulative_CPU_seconds": cumulative,
                                 "caller_count": len(callers)})
                    for caller, counts in sorted(callers.items()):
                        p.require(type(caller) is tuple and len(caller) == 3
                                  and type(caller[0]) is str and type(caller[2]) is str
                                  and len(caller[0].encode()) <= 2048 and len(caller[2].encode()) <= 2048,
                                  "caller identity/label cap")
                        p.require(type(counts) is tuple and len(counts) == 4
                                  and all(type(n) in (int, float) and n >= 0 and n < float("inf") for n in counts),
                                  "caller counter shape")
                        edges.append({"callee": [filename, line, name], "caller": list(caller),
                                      "primitive_calls": counts[0], "calls": counts[1],
                                      "self_CPU_seconds": counts[2], "cumulative_CPU_seconds": counts[3]})
                        p.require(len(edges) <= 40000, "profile caller edge cap")
                result.append({"window": i, "rows": rows,
                               "caller_edges": edges,
                               "coverage": "Complete bounded function rows; cumulative values overlap; no residual forcing."})
        return result


def offline_audit():
    blocked, metadata_reads = [], []
    def audit(event, args):
        if event == "socket.gethostname":
            metadata_reads.append(event)
            return
        if event.startswith("socket.") or event in {
            "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.fork", "os.forkpty"}:
            blocked.append(event)
            raise RuntimeError("offline whole-turn runtime forbids "+event)
    sys.addaudithook(audit)
    return blocked, metadata_reads


def import_runtime(value):
    """Called only after ready registration and exact source/context checks."""
    measured = Path(value["measured_root"])
    p.require(not any(n == "chronicler" or n.startswith("chronicler.")
                      for n in sys.modules), "foreign product already loaded")
    sys.path.insert(0, str(measured/"src"))
    import platform
    platform.platform()  # existing metadata startup, before offline audit
    import cProfile
    import random
    import numpy as np
    import pyarrow as pa
    from arro3.core import RecordBatch
    import chronicler_agents as native
    import chronicler_agents.chronicler_agents as compiled
    from importlib.machinery import ExtensionFileLoader
    from chronicler import main, run_checkpoint
    p.require(type(compiled.__loader__) is ExtensionFileLoader
              and Path(compiled.__file__).resolve() == Path(value["native_file"]),
              "fresh actual compiled worker origin")
    classes = tuple(getattr(native, name) for name in build.CLASSES)
    p.require(all(cls is getattr(compiled, name) for cls, name in zip(classes, build.CLASSES)),
              "actual compiled worker classes")
    p.require({name: list(cls.checkpoint_schema()) for name, cls in zip(build.CLASSES, classes)}
              == value["schemas"], "actual worker schemas changed")
    return main, run_checkpoint, classes, np, pa, RecordBatch, cProfile, random


def execute_role(controller_root, build_file, index, ordinary, output, shared_rng):
    reg = p.load_registration(controller_root)
    p.require(type(index) is int and 0 <= index < 12, "registered role index")
    context = build.github_context(controller_root)
    request = p.schedule(reg)[index]
    value = p.read_json(build_file, 512*1024)
    p.require(value["arm"] == request["arm"] and value["source_commit"] == request["source_commit"]
              and value["native_tree"] == request["native_tree"] and value["github"] == context
              and value["driver_pins"] == build.driver_pins(controller_root), "worker measured source join")
    p.require(len(os.sched_getaffinity(0)) == 1 and os.environ.get("PYTHONHASHSEED") == "0"
              and sys.dont_write_bytecode, "single CPU/hashseed/no-bytecode")
    for name in ("RAYON_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                 "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS", "GOTO_NUM_THREADS"):
        p.require(os.environ.get(name) == "1", "one math thread: "+name)
    build.recheck_build(value)
    output, ordinary, shared_rng = Path(output), Path(ordinary), Path(shared_rng)
    p.require(output.is_dir() and ordinary.is_dir() and not list(ordinary.iterdir()), "fresh role/ordinary roots")
    journal = Journal(output/"timing.jsonl")
    summary = {"kind": "MATCHED_WHOLETURN_ROLE", "protocol": p.PROTOCOL, "request": request,
               "controller_commit": context["GITHUB_SHA"], "github": context,
               "status": "STARTED", "run_complete": False, "proof_complete": False,
               "performance_qualification": None, "scientific_qualification": None}
    observer = None
    raw = {k: None for k in ("CPU_start_ns", "CPU_end_ns", "wall_start_ns", "wall_end_ns")}
    try:
        main, rc, classes, np, pa, arro3, profiler, random = import_runtime(value)
        expected_identity = rc.runtime_identity()
        p.require(expected_identity["source"] == {"git_sha": value["source_commit"], "package_digest": value["package_digest"]}
                  and expected_identity["native"]["sha256"] == value["wheel_receipt"]["installed_native"]["sha256"],
                  "actual measured runtime identity")
        summary["runtime_identity"] = expected_identity
        observer = Boundary(request["profiled"], reg["windows"], journal, profiler.Profile)
        # Fixed input, then actual state capture/replay; never seed-only equality.
        random.seed(reg["global_rng_seed"])
        np.random.seed(reg["global_rng_seed"])
        if shared_rng.exists():
            rng = p.read_json(shared_rng, 65536)
        else:
            rng = proof.capture_rng(np)
            p.write_new(shared_rng, rng, 65536)
        proof.restore_rng(rng, np)
        p.require(proof.same_rng(proof.capture_rng(np), rng), "actual initial RNG replay")
        summary["initial_rng"] = rng
        blocked, hostname_reads = offline_audit()
        args = main._build_parser().parse_args([
            "--seed", str(request["seed"]), "--turns", "200", "--worldgen", request["worldgen"],
            "--regions", str(request["regions"]), "--civs", str(request["civilizations"]),
            "--agents", "hybrid", "--agent-scale-mode", "exact", "--narrator", "local",
            "--simulate-only", "--validation-sidecar", "--output", str(ordinary/"chronicle.md"),
            "--state", str(ordinary/"state.json")])
        raw["CPU_start_ns"], raw["wall_start_ns"] = p.sample_ns(time.process_time_ns), p.sample_ns(time.perf_counter_ns)
        journal.emit({"kind": "EXECUTE_START", **raw})
        p.require(all(type(raw[k]) is int and 0 <= raw[k] < 2**63
                      for k in ("CPU_start_ns", "wall_start_ns")), "malformed execute starting clock")
        result = None
        try:
            result = main.execute_run(args, turn_boundary=observer)
        finally:
            stop_error = None
            try:
                observer.stop()
            except BaseException as exc:
                stop_error = exc
            raw["CPU_end_ns"], raw["wall_end_ns"] = p.sample_ns(time.process_time_ns), p.sample_ns(time.perf_counter_ns)
            journal.emit({"kind": "EXECUTE_END", **raw})
            summary["run_clock"] = p.interval(raw)
            summary["World_boundaries_observed"] = observer.last
            summary["windows"] = observer.records
            summary["run_config"] = observer.config
            summary["final_rng"] = proof.capture_rng(np)
            summary["run_process_lifetime_RSS_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
            p.write_new(output/"scalar-before-proof.json", summary, 512*1024)
            if stop_error is not None:
                raise stop_error
        p.require(result is not None and type(result.total_turns) is int and result.total_turns == 200
                  and observer.last == 200 and len(observer.records) == 2
                  and summary["run_clock"]["numerically_valid"], "incomplete or invalid measured run")
        summary["run_complete"] = True
        from wholeturn_live_proof import capture_terminal, arrow_adapter
        proof_start = (p.sample_ns(time.process_time_ns), p.sample_ns(time.perf_counter_ns))
        outcome = capture_terminal(observer.save, output/"terminal.ckpt", rc, classes, np,
                                   expected_rng=summary["final_rng"],
                                   inspect_arrow=arrow_adapter(pa, arro3))
        header = outcome.pop("checkpoint_header")
        identity = header["identity"]
        p.require(header["turn"] == 200 and header["num_turns"] == 200
                  and header["seed"] == request["seed"] and header["world"]["regions"] == request["regions"]
                  and identity["source"]["git_sha"] == request["source_commit"]
                  and identity["native"]["sha256"] == value["wheel_receipt"]["installed_native"]["sha256"],
                  "own terminal checkpoint identity/config")
        p.require(identity == expected_identity, "complete own checkpoint environment/source/native identity")
        summary["checkpoint_identity"] = identity
        summary["effective_flags"] = header["flags"]
        summary["proof"] = outcome
        summary["proof_clock"] = p.interval({"CPU_start_ns": proof_start[0], "CPU_end_ns": p.sample_ns(time.process_time_ns),
                                             "wall_start_ns": proof_start[1], "wall_end_ns": p.sample_ns(time.perf_counter_ns)})
        summary["proof_complete"] = True
        profiles = observer.details()
        summary["profiles"] = p.write_new(output/"profile-functions.json", profiles, 32*p.MIB)
        p.require(not blocked, "offline runtime violation")
        summary["offline_audit"] = {"blocked_attempts": blocked, "local_hostname_reads": len(hostname_reads),
                                    "startup_platform_uname_before_audit": True, "kernel_sandbox_claim": False}
        build.recheck_files(value)
        p.require(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024 <= reg["limits"]["role_observed_RSS_bytes"],
                  "role lifetime RSS refusal")
        summary["status"] = "COMPLETE_ROLE_PENDING_PAIR_COMPARISON"
    except BaseException as exc:
        summary["status"] = "FIRST_ROLE_FAILURE"
        summary["error"] = {"type": type(exc).__name__, "message": str(exc)[:512]}
    finally:
        if observer is not None:
            try:
                observer.stop()
            except BaseException as exc:
                summary["status"] = "FIRST_ROLE_FAILURE"
                summary["stop_error"] = type(exc).__name__
        summary["final_process_lifetime_RSS_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
        journal.emit({"kind": "ROLE_TERMINAL", "status": summary["status"]})
        journal.close()
        p.write_new(output/"result.json", summary, 512*1024)
    return 0 if summary["status"] == "COMPLETE_ROLE_PENDING_PAIR_COMPARISON" else 2


def require_matching_inputs(left, right):
    for field in ("run_config", "effective_flags"):
        p.require(left[field] == right[field], "paired configuration mismatch: "+field)
    for field in ("initial_rng", "final_rng"):
        p.require(proof.same_rng(left[field], right[field]), "paired exact RNG mismatch: "+field)


def compare_roles(controller_root, baseline_build, left, right, left_ordinary, right_ordinary, output):
    reg = p.load_registration(controller_root)
    context = build.github_context(controller_root)
    value = p.read_json(baseline_build, 512*1024)
    build.recheck_build(value)
    sys.path.insert(0, str(Path(value["measured_root"])/"src"))
    from cities_identity import compare
    from turn_speed_identity import _raw_bundle_problems
    a, b = p.read_json(left, 512*1024), p.read_json(right, 512*1024)
    for x in (a, b):
        p.require(x["run_complete"] and x["proof_complete"] and x["status"] == "COMPLETE_ROLE_PENDING_PAIR_COMPARISON",
                  "cannot compare incomplete role")
        request = x["request"]
        p.require(type(request["index"]) is int and 0 <= request["index"] < 12
                  and request == p.schedule(reg)[request["index"]]
                  and x["github"] == context and x["controller_commit"] == context["GITHUB_SHA"]
                  and x["runtime_identity"]["source"]["git_sha"] == request["source_commit"]
                  and x["checkpoint_identity"] == x["runtime_identity"], "comparison source/runtime/controller joins")
    p.require({a["request"]["arm"], b["request"]["arm"]} == {"baseline", "candidate"}
              and a["request"]["pair"] == b["request"]["pair"], "exact measured pair")
    require_matching_inputs(a, b)
    p.require(a["runtime_identity"]["environment"] == b["runtime_identity"]["environment"]
              and a["runtime_identity"]["native"]["state_layouts"] == b["runtime_identity"]["native"]["state_layouts"],
              "paired actual environment/state layouts")
    for field in ("live", "decoded", "coverage"):
        p.require(a["proof"][field] == b["proof"][field], "paired complete graph mismatch: "+field)
    blocked, _hostname_reads = offline_audit()
    checked, problems = compare(Path(left_ordinary), Path(right_ordinary))
    problems += _raw_bundle_problems(Path(left_ordinary), Path(right_ordinary))
    p.require(not blocked, "comparison offline violation")
    by_arm = {a["request"]["arm"]: a, b["request"]["arm"]: b}
    record = {"kind": "MATCHED_WHOLETURN_PAIR", "left": a["request"], "right": b["request"],
              "checked_files": checked, "ordinary_problems": problems,
              "ratios": p.ratio(by_arm["baseline"]["run_clock"], by_arm["candidate"]["run_clock"]),
              "status": "EQUAL" if checked > 0 and not problems else "MISMATCH",
              "scientific_qualification": None, "performance_qualification": None}
    p.write_new(output, record, p.MIB)
    return 0 if record["status"] == "EQUAL" else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("record-build", "role", "compare"))
    for name in ("controller-root", "measured-root", "wheel-dir", "output", "build", "ordinary",
                 "shared-rng", "left", "right", "left-ordinary", "right-ordinary"):
        parser.add_argument("--"+name, type=Path)
    parser.add_argument("--arm", choices=("baseline", "candidate"))
    parser.add_argument("--index", type=int)
    args = parser.parse_args(argv)
    p.require(args.controller_root is not None, "controller root required")
    p.load_registration(args.controller_root)  # first public gate, before project/native/Git work
    if args.command == "record-build":
        build.record_build(args.controller_root, args.measured_root, args.arm, args.wheel_dir, args.output)
        return 0
    if args.command == "role":
        p.require(type(args.index) is int and 0 <= args.index < 12, "registered role index")
        return execute_role(args.controller_root, args.build, args.index, args.ordinary, args.output, args.shared_rng)
    return compare_roles(args.controller_root, args.build, args.left, args.right,
                         args.left_ordinary, args.right_ordinary, args.output)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except p.Refused as exc:
        print("WHOLETURN_REFUSED: "+str(exc), file=sys.stderr)
        raise SystemExit(2)
