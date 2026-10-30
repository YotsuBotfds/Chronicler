"""Opt-in compiled context API benchmark; no production wiring or World ticks.

The default invocation imports no native runtime and writes no files. Build
identity is recorded separately from the bounded comparison process. The
timed kernels include bound native reads and a common checksum consumer;
GreatPerson decoding/assignment and whole-turn performance are not measured.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
from importlib.machinery import EXTENSION_SUFFIXES, ExtensionFileLoader
import json
import os
from pathlib import Path
import platform
import statistics
import struct
import subprocess
import sys
import time

METHOD = "compiled-context-api-v1-20000records-3pairs"
NATIVE_TREE = "09ec301efc5c52a0a75f7a6edd9b99636d2953ff"
RECORDS = 20000
PAIRS = 3
WARMUP_RECORDS = 200
MAX_PLAN = 65536
MAX_RESULT = 262144
MAX_JOURNAL = 262144
MAX_BUILD = 131072
MAX_WHEEL = 16 * 1024 * 1024
MAX_NATIVE = 64 * 1024 * 1024


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def conditions():
    rows = [dict(slots=n, requests=p, layout=layout, bond_slots=0)
        for n in (512, 8192, 65536) for p in (1, 50)
        for layout in ("prefix", "spread", "missing")]
    rows += [dict(slots=8192, requests=p, layout="spread", bond_slots=8) for p in (1, 10, 50)]
    return [dict(case=i, **row) for i, row in enumerate(rows)]


def work_bounds():
    # Slot-loop visits, not retired instructions or a runtime prediction.
    rows = conditions()
    return {"scalar_slot_visit_upper_bound": sum(3*r["slots"]*RECORDS*PAIRS for r in rows),
        "batch_slot_visits": sum(r["slots"]*(RECORDS//r["requests"])*PAIRS for r in rows),
        "excludes": "Batch binary searches/sort, payload conversion, Python consumer, setup, parity and untimed warmup."}


def measurement_plan():
    return {"kind": "COMPILED_CONTEXT_API_BENCHMARK_PLAN", "method": METHOD,
        "conditions": conditions(), "records_per_helper_trial": RECORDS, "trial_pairs": PAIRS,
        "timed_samples": len(conditions())*PAIRS*2, "work_bounds": work_bounds(),
        "scope": "Actual compiled context getters and common checksum consumer; no complete Python sync or World/physics timing."}


def query_ids(ids, spec):
    n, p = spec["slots"], spec["requests"]
    require(len(ids) == n and len(set(ids)) == n and p <= n, "fresh_pool_shape")
    if spec["layout"] == "missing":
        queries = [2**32-1-i for i in range(p)]
        require(not set(queries).intersection(ids), "missing_fixture_ids_live")
        return queries, [None]*p
    if spec["layout"] == "prefix":
        positions = list(range(p))
    else:
        require(spec["layout"] == "spread", "query_layout")
        positions = [n//2] if p == 1 else [i*(n-1)//(p-1) for i in range(p)]
    return [ids[i] for i in positions], positions


def file_pin(path, cap):
    size = path.stat().st_size
    require(path.is_file() and 0 < size <= cap, "identity_file_limit")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"filename": path.name, "bytes": size, "sha256": digest}


def write_json(path, value, cap):
    body = (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode()
    require(len(body) <= cap, "evidence_file_limit")
    with path.open("xb") as stream:
        require(stream.write(body) == len(body), "short_evidence_write")
    return {"filename": path.name, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def read_build(path):
    require(path.stat().st_size <= MAX_BUILD, "build_record_limit")
    value = json.loads(path.read_text())
    require(value["kind"] == "OWN_FRESH_CONTEXT_WHEEL_BUILD" and value["native_tree"] == NATIVE_TREE,
            "build_identity")
    require(value["method"] == METHOD and value["source_commit"] == os.environ.get("GITHUB_SHA"),
            "source_identity")
    require(value["benchmark_script"] == file_pin(Path(__file__), MAX_BUILD), "benchmark_source_changed")
    return value


def compiled_module():
    package = importlib.import_module("chronicler_agents")
    native = importlib.import_module("chronicler_agents.chronicler_agents")
    path = Path(native.__file__)
    require(isinstance(native.__spec__.loader, ExtensionFileLoader)
            and any(str(path).endswith(s) for s in EXTENSION_SUFFIXES), "real_extension_required")
    require(path.resolve().is_relative_to(Path(sys.prefix).resolve()), "native_outside_current_environment")
    for name in ("AgentSimulator", "EcologySimulator", "PoliticsSimulator"):
        require(isinstance(getattr(native, name, None), type)
                and getattr(package, name, None) is getattr(native, name), "native_class_alias")
    for name in ("get_agent_context_batch", "get_agent_memories", "get_agent_needs", "get_agent_relationships"):
        require(callable(getattr(native.AgentSimulator, name, None)), "context_api_missing")
    return native, path


def record_build(root, wheel_dir, output):
    # This operation imports the built extension but constructs no simulator.
    from scripts.native_wheel_receipt import wheel_receipt

    def git(*args):
        proc = subprocess.run(["git", "--no-replace-objects", "-C", str(root), *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        require(proc.returncode == 0, "source_git_failure")
        return proc.stdout.decode().strip()

    source = git("rev-parse", "HEAD")
    require(source == os.environ.get("GITHUB_SHA") and len(source) == 40, "checkout_source_mismatch")
    require(not git("status", "--porcelain", "--untracked-files=no"), "dirty_build_source")
    require(os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "first_attempt_required")
    native_tree = git("rev-parse", "HEAD:chronicler-agents")
    require(native_tree == NATIVE_TREE, "native_source_changed")
    native, native_path = compiled_module()
    wheels = list(wheel_dir.glob("*.whl"))
    require(len(wheels) == 1, "one_fresh_wheel_required")
    file_pin(wheels[0], MAX_WHEEL)
    file_pin(native_path, MAX_NATIVE)
    link = wheel_receipt(wheel_dir, native_path, source)
    toolchain = {name: file_pin(output.parent/name, 4096)
        for name in ("rustc.txt", "cargo.txt", "maturin.txt", "uv.txt")}
    value = {"kind": "OWN_FRESH_CONTEXT_WHEEL_BUILD", "method": METHOD, "source_commit": source,
        "source_tree": git("rev-parse", "HEAD^{tree}"), "native_tree": native_tree,
        "benchmark_script": file_pin(Path(__file__), MAX_BUILD),
        "workflow": file_pin(root/".github/workflows/named-context-benchmark.yml", MAX_BUILD),
        "wheel_receipt_helper": file_pin(root/"scripts/native_wheel_receipt.py", MAX_BUILD),
        "uv_lock": file_pin(root/"uv.lock", 4*1024*1024),
        "cargo_lock": file_pin(root/"chronicler-agents/Cargo.lock", MAX_BUILD),
        "toolchain_records": toolchain,
        "wheel_receipt": link, "python": sys.version, "platform": platform.platform(),
        "github": {k: os.environ.get(k) for k in
            ("GITHUB_SHA", "GITHUB_REF", "GITHUB_JOB", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")},
        "threads": {k: os.environ.get(k) for k in
            ("RAYON_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
        "scope": "Own workflow completed release locked build/installed-byte link; no reproducibility or scientific qualification."}
    return write_json(output, value, MAX_BUILD)


def real_runtime(build, wheel_dir):
    import resource
    from scripts.native_wheel_receipt import wheel_receipt
    import pyarrow as pa

    require(os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "first_attempt_required")
    require(len(os.sched_getaffinity(0)) == 1
            and resource.getrlimit(resource.RLIMIT_CPU) == (540, 540)
            and resource.getrlimit(resource.RLIMIT_AS) == (2147483648, 2147483648),
            "comparison_process_limits")
    native, path = compiled_module()
    require(wheel_receipt(wheel_dir, path, build["source_commit"]) == build["wheel_receipt"],
            "installed_wheel_changed")

    return fixture_factory(native, pa)


def fixture_factory(native, pa):
    def pool(spec):
        n = spec["slots"]
        sim = native.AgentSimulator(num_regions=8, seed=42)
        sim.set_agent_scale_mode("exact")
        sim.set_region_state(pa.record_batch({
            "region_id": pa.array(range(8), type=pa.uint16()),
            "terrain": pa.array([0]*8, type=pa.uint8()),
            "carrying_capacity": pa.array([n//8]*8, type=pa.uint16()),
            "population": pa.array([n//8]*8, type=pa.uint16()),
            "soil": pa.array([.8]*8, type=pa.float32()),
            "water": pa.array([.6]*8, type=pa.float32()),
            "forest_cover": pa.array([.3]*8, type=pa.float32()),
            "controller_civ": pa.array([i%4 for i in range(8)], type=pa.uint8()),
        }))
        ids = pa.record_batch(sim.get_snapshot()).column("id").to_pylist()
        queries, _ = query_ids(ids, spec)
        if spec["bond_slots"]:
            require(spec["layout"] == "spread" and n == 8192, "payload_fixture")
            positions = {agent: i for i, agent in enumerate(ids)}
            edges = [(agent, ids[(positions[agent]+offset)%n]) for agent in queries for offset in range(1, 9)]
            sim.apply_relationship_ops(pa.record_batch({
                "op_type": pa.array([0]*len(edges), type=pa.uint8()),
                "agent_a": pa.array([a for a, _ in edges], type=pa.uint32()),
                "agent_b": pa.array([b for _, b in edges], type=pa.uint32()),
                "bond_type": pa.array([6]*len(edges), type=pa.uint8()),
                "sentiment": pa.array([50]*len(edges), type=pa.int8()),
                "formed_turn": pa.array([0]*len(edges), type=pa.uint16()),
            }))
        return sim, ids

    return pool


def scalar_rows(sim, ids):
    return [(agent, sim.get_agent_memories(agent), sim.get_agent_needs(agent),
             sim.get_agent_relationships(agent)) for agent in ids]


def fingerprint(rows):
    encoded = []
    for agent, memories, needs, bonds in rows:
        require(type(agent) is int and type(memories) is list
                and (needs is None or type(needs) is tuple and len(needs) == 6)
                and (bonds is None or type(bonds) is list), "context_row_shape")
        encoded.append([agent, memories, None if needs is None else
            [struct.pack("!d", value).hex() for value in needs], bonds])
    return hashlib.sha256(json.dumps(encoded, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def consume(agent, memories, needs, bonds):
    # The same small eager-materialization consumer is included on both sides.
    return agent + 3*len(memories) + 5*(needs is not None) + 7*(bonds is not None) + 11*len(bonds or ())


def scalar_kernel(sim, ids, repetitions):
    memories, needs, bonds = sim.get_agent_memories, sim.get_agent_needs, sim.get_agent_relationships
    total = 0
    for _ in range(repetitions):
        for agent in ids:
            total += consume(agent, memories(agent), needs(agent), bonds(agent))
    return total


def batch_kernel(sim, ids, repetitions):
    get = sim.get_agent_context_batch
    total = 0
    for _ in range(repetitions):
        for agent, memories, needs, bonds in get(ids):
            total += consume(agent, memories, needs, bonds)
    return total


def timed_sample(helper, sim, ids, repetitions, wall=time.perf_counter_ns, cpu=time.process_time_ns):
    wall_start = wall()
    cpu_start = cpu()
    error = None
    try:
        checksum = helper(sim, ids, repetitions)
    except Exception as exc:
        checksum = None
        error = {"type": type(exc).__name__, "message": str(exc)[:512]}
    cpu_end = cpu()
    wall_end = wall()
    result = dict(wall_start_ns=wall_start, process_CPU_start_ns=cpu_start,
        process_CPU_end_ns=cpu_end, wall_end_ns=wall_end,
        wall_ns=wall_end-wall_start, process_CPU_ns=cpu_end-cpu_start, checksum=checksum)
    if error is not None:
        result["error"] = error
    return result


def append_sample(stream, value):
    body = (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode()
    require(stream.tell()+len(body) <= MAX_JOURNAL, "timing_journal_limit")
    require(stream.write(body) == len(body), "short_journal_write")
    stream.flush()  # Preserve the row before numerical acceptance/refusal.


def _condition_result(spec, sim, ids, journal, wall, cpu, trials):
    queries, positions = query_ids(ids, spec)
    expected = scalar_rows(sim, queries)
    expected_digest = fingerprint(expected)
    require(fingerprint(sim.get_agent_context_batch(queries)) == expected_digest, "compiled_API_parity")
    require(all(not row[1] and (row[3] is None or len(row[3]) == spec["bond_slots"]) for row in expected),
            "fixture_payload")
    # Existing API duplicate/missing ordering control, outside all timing.
    control = [ids[0], ids[0], 0, 2**32-1]
    control_rows = sim.get_agent_context_batch(control)
    require(fingerprint(control_rows) == fingerprint(scalar_rows(sim, control)), "duplicate_control_parity")
    require(control_rows[0][1] is not control_rows[1][1], "duplicate_memory_alias")
    repetitions = RECORDS//spec["requests"]
    require(RECORDS % spec["requests"] == WARMUP_RECORDS % spec["requests"] == 0, "record_batch_shape")
    checksum = sum(consume(*row) for row in expected)*repetitions
    warmup = WARMUP_RECORDS//spec["requests"]
    scalar_kernel(sim, queries, warmup)
    batch_kernel(sim, queries, warmup)
    samples = []
    refused = False
    for trial in trials:
        order = ("scalar", "batch") if (spec["case"]+trial) % 2 == 0 else ("batch", "scalar")
        for side in order:
            sample = timed_sample(scalar_kernel if side == "scalar" else batch_kernel,
                sim, queries, repetitions, wall, cpu)
            sample.update(case=spec["case"], trial=trial, helper=side, order=list(order))
            sample["accepted"] = sample["wall_ns"] > 0 and sample["process_CPU_ns"] > 0 and sample["checksum"] == checksum
            append_sample(journal, sample)
            samples.append(sample)
            require("error" not in sample, "timed_helper_failed")
            refused |= not sample["accepted"]
    require(fingerprint(scalar_rows(sim, queries)) == expected_digest
            and fingerprint(sim.get_agent_context_batch(queries)) == expected_digest, "post_read_parity")
    result = dict(spec, request_ids=queries, slot_positions=positions, expected_checksum=checksum,
        ordered_payload_sha256=expected_digest, records_per_helper_trial=RECORDS,
        repetitions=repetitions, warmup_records_per_helper=WARMUP_RECORDS,
        status="refused" if refused else "complete", samples=samples)
    if not refused:
        wall_medians = {side: statistics.median(s["wall_ns"] for s in samples if s["helper"] == side)
            for side in ("scalar", "batch")}
        cpu_medians = {side: statistics.median(s["process_CPU_ns"] for s in samples if s["helper"] == side)
            for side in ("scalar", "batch")}
        result.update(median_wall_ns=wall_medians, median_process_CPU_ns=cpu_medians,
            wall_ratio_scalar_over_batch=wall_medians["scalar"]/wall_medians["batch"],
            CPU_ratio_scalar_over_batch=cpu_medians["scalar"]/cpu_medians["batch"],
            batch_wall_change_percent=(wall_medians["batch"]/wall_medians["scalar"]-1)*100)
    return result


def condition_result(spec, sim, ids, journal, wall, cpu):
    return _condition_result(spec, sim, ids, journal, wall, cpu, range(PAIRS))


def condition_trial(spec, sim, ids, journal, wall, cpu, trial):
    require(type(trial) is int and 0 <= trial < PAIRS, "registered_trial")
    result = _condition_result(spec, sim, ids, journal, wall, cpu, (trial,))
    result["trial"] = trial
    result["control_payload_sha256"] = fingerprint(
        sim.get_agent_context_batch([ids[0], ids[0], 0, 2**32-1]))
    for key in ("median_wall_ns", "median_process_CPU_ns", "wall_ratio_scalar_over_batch",
                "CPU_ratio_scalar_over_batch", "batch_wall_change_percent"):
        result.pop(key, None)
    return result


def run_suite(output, build_path, wheel_dir, runtime_factory=real_runtime,
              wall=time.perf_counter_ns, cpu=time.process_time_ns):
    require(output.is_absolute(), "absolute_output_required")
    output.mkdir(exist_ok=False)
    specs = conditions()
    plan = measurement_plan()
    write_json(output/"plan.json", plan, MAX_PLAN)
    result = {"kind": "COMPILED_CONTEXT_API_BENCHMARK_RESULT", "method": METHOD,
        "status": "failed", "conditions": [dict(s, status="not_run") for s in specs],
        "source_identity": None, "complete_Python_sync_measured": False,
        "World_physics_wholeturn_RNG_checkpoint_science_qualification": None,
        "external_whole_attempt_wall_CPU_RSS": None, "retries": 0}
    try:
        build = read_build(build_path)
        result["build_record"] = file_pin(build_path, MAX_BUILD)
        result["source_identity"] = {key: build[key] for key in ("source_commit", "source_tree", "native_tree")}
        result["runtime_context"] = {"python": sys.version, "platform": platform.platform(),
            "CPU_affinity": sorted(os.sched_getaffinity(0)), "load_average": list(os.getloadavg())}
        pool = runtime_factory(build, wheel_dir)
        with (output/"timings.jsonl").open("xb") as journal:
            for spec in specs:
                try:
                    sim, ids = pool(spec)
                    result["conditions"][spec["case"]] = condition_result(spec, sim, ids, journal, wall, cpu)
                    del sim
                except Exception as exc:
                    result["conditions"][spec["case"]] = dict(spec, status="failed",
                        error={"type": type(exc).__name__, "message": str(exc)[:512]})
                    raise
        result["status"] = "complete" if all(r["status"] == "complete" for r in result["conditions"]) else "refused"
    except Exception as exc:
        result["error"] = {"type": type(exc).__name__, "message": str(exc)[:512]}
    finally:
        write_json(output/"result.json", result, MAX_RESULT)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan-only", action="store_true")
    mode.add_argument("--record-build", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--wheel-dir", type=Path)
    parser.add_argument("--build", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not args.record_build and not args.execute and not args.plan_only:
        print('{"kind":"COMPILED_CONTEXT_API_BENCHMARK","status":"disabled"}')
        return 0
    if args.plan_only:
        if args.output is None:
            parser.error("--plan-only requires --output")
        print(json.dumps(write_json(args.output, measurement_plan(), MAX_PLAN), sort_keys=True))
        return 0
    if args.wheel_dir is None or args.build is None:
        parser.error("enabled modes require --wheel-dir and --build")
    if args.record_build:
        if args.root is None:
            parser.error("--record-build requires --root")
        print(json.dumps(record_build(args.root, args.wheel_dir, args.build), sort_keys=True))
        return 0
    if args.output is None:
        parser.error("--execute requires a fresh absolute --output")
    result = run_suite(args.output, args.build, args.wheel_dir)
    print(json.dumps({"status": result["status"], "method": METHOD}, sort_keys=True))
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
