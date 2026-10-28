#!/usr/bin/env python3
"""Read-only, checkpoint-backed writer-cadence correctness/profile diagnostic.

This never changes the orchestrator, source checkout, horizons or saved feature
controls. Outputs must be new. Profiles under shared load establish no speedup.
See docs/performance/ablation-writer-cadence-preregistration.md.
"""
from __future__ import annotations

import argparse
import cProfile
from collections import deque
import dataclasses
from datetime import datetime, timezone
from enum import Enum
import hashlib
import io
import json
import os
from pathlib import Path
import pickle
import pstats
import shutil
import subprocess
import sys
import time

CONTROLS = {"full10": (False, 10), "lean10": (True, 10), "lean61": (True, 61)}
EXPECTED_SOURCE = "d051d7c06b1a490841d148b8906bde22f2f5d0f0"
EXPECTED_NATIVE = "fb20dbc81828420fedc9a0b25fb8791a694a158d2c502ec915b8132a52875317"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    """Fail closed on unsupported state; never fall back to repr/object IDs."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Enum):
        return {"enum": type(value).__qualname__, "value": canonical(value.value)}
    if isinstance(value, bytes):
        return {"bytes": len(value), "sha256": sha(value)}
    if isinstance(value, dict):
        rows = [(canonical(k), canonical(v)) for k, v in value.items()]
        return {"mapping": sorted(rows, key=lambda row: json.dumps(row[0], sort_keys=True))}
    if isinstance(value, (set, frozenset)):
        return {"set": sorted((canonical(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))}
    if isinstance(value, (tuple, list)):
        return [canonical(v) for v in value]
    if isinstance(value, deque):
        return {"deque": [canonical(v) for v in value], "maxlen": value.maxlen}
    if dataclasses.is_dataclass(value):
        return {"type": type(value).__qualname__,
                "fields": {f.name: canonical(getattr(value, f.name)) for f in dataclasses.fields(value)}}
    if hasattr(type(value), "model_fields"):
        # Include exclude=True fields, including pending signals and raw events.
        return {"type": type(value).__qualname__,
                "fields": {k: canonical(getattr(value, k)) for k in type(value).model_fields}}
    if type(value).__module__.startswith("numpy"):
        return {"type": type(value).__qualname__, "value": canonical(value.tolist())}
    if type(value).__module__.startswith("chronicler.") and hasattr(value, "__dict__"):
        return {"type": type(value).__qualname__, "fields": canonical(vars(value))}
    if type(value).__module__.startswith("chronicler.") and hasattr(type(value), "__slots__"):
        names = [name for cls in type(value).__mro__ for name in getattr(cls, "__slots__", ())
                 if name not in ("__dict__", "__weakref__")]
        return {"type": type(value).__qualname__, "slots": {name: canonical(getattr(value, name)) for name in names}}
    raise TypeError(f"unsupported diagnostic state: {type(value).__module__}.{type(value).__qualname__}")


def signature(value):
    return sha(json.dumps(canonical(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def inventory(folder):
    return {p.relative_to(folder).as_posix(): {"bytes": p.stat().st_size, "sha256": sha(p.read_bytes())}
            for p in sorted(folder.rglob("*")) if p.is_file()}


def memory_cache(memories):
    result = {}
    for name, stream in memories.items():
        kinds = {}
        for kind, rows in stream.__dict__.get("_encoded", {}).items():
            kinds[kind] = {"rows": len(rows), "signature": signature(rows),
                           "valid_identity_rows": sum(
                               all(row[i] is getattr(row[0], field) for i, field in
                                   ((1, "turn"), (2, "text"), (3, "importance"), (4, "entry_type")))
                               for row in rows)}
        result[name] = kinds
    return result


def state_view(state):
    from chronicler import run_checkpoint as rc
    world = state.world
    # Native blobs include RNG, slots, queues, trip state and registries. Use
    # the actual checkpoint reducer, including any additional native runtimes.
    buf = io.BytesIO()
    pickler = rc._Pickler(buf)
    pickler.dump(state)
    archives = {name: (None if getattr(world, name) is None else getattr(world, name).state)
                for name in ("_historiography", "_languages")}
    private_signals = {name: getattr(world, name) for name in
                      ("_artifact_intents", "_artifact_lifecycle_intents", "_artifact_prestige_by_civ",
                       "_hazard_events", "_contact_pending")}
    extras = {k: v for k, v in vars(world).items()
              if k not in type(world).model_fields and k != "_war_roster_sim"}
    bridge = state.agent_bridge
    bridge_fields = {} if bridge is None else {
        k: v for k, v in bridge.__getstate__().items() if k not in ("_sim", "_sidecar", "_shadow_logger")}
    memories = {name: {"civilization_name": stream.civilization_name,
                       "entries": stream.entries, "reflections": stream.reflections}
                for name, stream in state.memories.items()}
    carried = {"world": world, "world_extras": extras, "private_signals": private_signals,
               "archives": archives, "bridge_python": bridge_fields,
               "memories": memories, "history": state.history,
               "chronicle_entries": state.chronicle_entries, "era_reflections": state.era_reflections,
               "pending_injections": state.pending_injections, "economy_tracker": state.economy_tracker}
    return {"turn": world.turn, "carried": {k: signature(v) for k, v in carried.items()},
            "native": {k: {"bytes": len(v), "sha256": sha(v)} for k, v in pickler.natives.items()},
            "memory_pickle_sha256": sha(pickle.dumps(state.memories, protocol=rc.PICKLE_PROTOCOL)),
            "memory_cache": memory_cache(state.memories),
            "python_pickle_sha256": sha(buf.getvalue())}


def worker(args):
    # Profiling begins before Chronicler imports, and ends before evidence
    # serialization. Correctness workers have no profiler.
    profiler = cProfile.Profile() if args.phase == "profile" else None
    if profiler is not None:
        profiler.enable()
    from chronicler import main as main_module
    from chronicler import run_checkpoint as rc
    from chronicler.ablation_arms import _compress_events, fork_info
    from chronicler.artifact_io import atomic_write_json
    from chronicler.bundle_codec import load_bundle

    args.output_root.mkdir(parents=True, exist_ok=False)
    loaded = rc.read_checkpoint(args.parent)
    parser = main_module._build_parser()
    lean, cadence = CONTROLS[args.control]
    cli = ["--resume", str(args.parent), "--turns", "60", "--simulate-only",
           "--decision-ablation", "needs", "--ablation-start-turn", "30", "--state-every", str(cadence),
           "--output", str(args.output_root / "chronicle.md"), "--state", str(args.output_root / "state.json")]
    if lean:
        cli.append("--ablation-output")
    run_args = parser.parse_args(cli)
    conflicts = main_module._adopt_checkpoint_args(parser, run_args, loaded)
    if conflicts:
        raise ValueError(conflicts)
    observations, calls, checkpoint_record = [], [], {}

    class Boundary:
        def bind(self, save, run_config):
            self.save, self.config = save, run_config

        def live_record(self):
            return None

        def turn_end(self, world):
            state = dataclasses.replace(loaded.state, run_config=self.config)
            observations.append(state_view(state))
            if world.turn == 40:
                path = self.save(str(args.output_root / "probe40.ckpt"))
                header, body = rc.read_header(path)
                checkpoint_record.update({"path": str(path), "sha256": sha(path.read_bytes()),
                    "header": header, "section_raw_sha256": {
                        s["name"]: sha(rc._section(path, header, body, s["name"])) for s in header["sections"]}})
            return False

    original_turn = main_module._run_turn_deferring_sigint

    def observed_turn(world, **kwargs):
        calls.append([world.turn, kwargs["seed"], kwargs["force_settlement_detection"]])
        return original_turn(world, **kwargs)

    observer = None
    if args.phase == "correctness":
        observer = Boundary()
        main_module._run_turn_deferring_sigint = observed_turn
    started = time.perf_counter()
    try:
        result = main_module.execute_run(run_args, checkpoint_resume=loaded, turn_boundary=observer)
    finally:
        main_module._run_turn_deferring_sigint = original_turn
        if profiler is not None:
            profiler.disable()
    seconds = time.perf_counter() - started
    final_state = dataclasses.replace(loaded.state, run_config=(observer.config if observer else loaded.state.run_config))
    final = state_view(final_state)
    if profiler is not None:
        profiler.dump_stats(args.output_root / "profile.pstats")
        stats = pstats.Stats(profiler)
        rows = [{"file": key[0], "line": key[1], "function": key[2],
                 "primitive_calls": value[0], "calls": value[1],
                 "self_seconds": value[2], "cumulative_seconds": value[3]}
                for key, value in stats.stats.items()]
        atomic_write_json(args.output_root / "profile-functions.json", {
            "total_calls": stats.total_calls, "total_seconds": stats.total_tt,
            "functions": sorted(rows, key=lambda row: row["cumulative_seconds"], reverse=True)})
    if not lean:
        metadata = load_bundle(args.output_root / "chronicle_bundle.json")["metadata"]
        atomic_write_json(args.output_root / "fork.json", fork_info(metadata))
    raw_events = sha((args.output_root / "agent_events.arrow").read_bytes())
    compressed = args.output_root / "agent_events.compressed.arrow"
    shutil.copyfile(args.output_root / "agent_events.arrow", compressed)
    _compress_events(compressed)
    record = {"status": "complete", "phase": args.phase, "control": args.control,
              "cli": cli, "source_turn": loaded.header["turn"], "completed_turn": loaded.state.world.turn,
              "execute_seconds": seconds, "boundaries": observations, "calls": calls,
              "final": final, "checkpoint40": checkpoint_record,
              "raw_events_sha256": raw_events, "compressed_events_sha256": sha(compressed.read_bytes()),
              "fork_sha256": sha((args.output_root / "fork.json").read_bytes()),
              "result": {k: v for k, v in dataclasses.asdict(result).items() if k != "output_dir"},
              "inventory": inventory(args.output_root)}
    atomic_write_json(args.output_root / "worker.json", record)


def equivalence(view):
    # Deliberately separate the stricter serialized-cache promise below.
    return {key: view[key] for key in ("turn", "carried", "native")}


def controller(args):
    from chronicler.artifact_io import atomic_write_json
    from chronicler.batch_manifest import package_digest, native_identity
    from chronicler.run_checkpoint import describe, runtime_identity
    script = Path(__file__).resolve()
    git = ["git", "-C", str(args.source_root)]

    def frozen():
        revision = subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(git + ["status", "--porcelain", "--untracked-files=no"], text=True)
        if revision != EXPECTED_SOURCE or dirty or package_digest() != package_sha or sha(script.read_bytes()) != script_sha:
            raise RuntimeError("source/package/runner changed")
        if native_identity().get("sha256") != EXPECTED_NATIVE:
            raise RuntimeError("native extension differs from the registered receipt release")

    script_sha, package_sha = sha(script.read_bytes()), package_digest()
    frozen()
    parent_header = describe(args.parent)
    if parent_header["turn"] != 30 or parent_header["num_turns"] != 60:
        raise ValueError("use the registered exact parent30 with original horizon60")
    args.output_root.mkdir(parents=True, exist_ok=False)
    logs = args.output_root / "logs"
    logs.mkdir()
    receipt_path = args.output_root / "diagnostic.json"
    evidence = {"status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
                "source_root": str(args.source_root), "identity": runtime_identity(),
                "runner": {"path": str(script), "sha256": script_sha},
                "parent": {"path": str(args.parent), "sha256": sha(args.parent.read_bytes()), "header": parent_header},
                "known_load": "two scholarship workers; another bounded lane may run; not a quiet benchmark",
                "initial_inspection_failure": "Exact loader refused omitted PYTHONHASHSEED=0; corrected without allow_mismatch",
                "commands": [], "checks": {}}

    def persist():
        atomic_write_json(receipt_path, evidence)

    def launch(label, phase, control, parent):
        frozen()
        folder = args.output_root / label
        command = [sys.executable, str(script), "--worker", "--source-root", str(args.source_root),
                   "--parent", str(parent), "--output-root", str(folder), "--phase", phase, "--control", control]
        started = time.perf_counter()
        with (logs / f"{label}.stdout").open("w") as stdout, (logs / f"{label}.stderr").open("w") as stderr:
            process = subprocess.run(command, cwd=args.source_root, stdout=stdout, stderr=stderr, check=False)
        evidence["commands"].append({"label": label, "command": command, "exit_code": process.returncode,
                                     "seconds": time.perf_counter() - started})
        persist()
        frozen()
        if process.returncode:
            raise RuntimeError(f"{label} failed; retained logs and outputs")
        print(f"completed {label}", flush=True)
        return json.loads((folder / "worker.json").read_text())

    persist()
    try:
        direct, continued = {}, {}
        for control in CONTROLS:
            direct[control] = launch(f"correctness-{control}", "correctness", control, args.parent)
        baseline = direct["full10"]
        expected_calls = [[t, 42 + t, t == 59] for t in range(30, 60)]
        for control, record in direct.items():
            if (record["calls"] != expected_calls or len(record["boundaries"]) != 30
                    or record["completed_turn"] != 60 or record["result"] != baseline["result"]
                    or [equivalence(v) for v in record["boundaries"]] != [equivalence(v) for v in baseline["boundaries"]]
                    or equivalence(record["final"]) != equivalence(baseline["final"])):
                raise AssertionError(f"authoritative direct-boundary divergence: {control}")
            for field in ("raw_events_sha256", "compressed_events_sha256", "fork_sha256"):
                if record[field] != baseline[field]:
                    raise AssertionError(f"retained event/receipt divergence: {control}/{field}")
        evidence["checks"]["direct_physical_native_history_events_equal"] = True
        evidence["checks"]["memory_pickle_difference_turns"] = {
            control: [a["turn"] for a, b in zip(baseline["boundaries"], record["boundaries"])
                      if a["memory_pickle_sha256"] != b["memory_pickle_sha256"]]
            for control, record in direct.items()}
        evidence["checks"]["strict_memory_checkpoint_equivalence"] = not any(
            evidence["checks"]["memory_pickle_difference_turns"].values())
        persist()
        evidence["checks"]["continuation_memory_pickle_difference_turns"] = {}
        evidence["checks"]["continuation_cache_difference_turns"] = {}
        for control in CONTROLS:
            continued[control] = launch(f"continuation-{control}", "correctness", control,
                                       Path(direct[control]["checkpoint40"]["path"]))
            record, original = continued[control], direct[control]
            expected = [equivalence(v) for v in original["boundaries"] if v["turn"] > 40]
            if ([equivalence(v) for v in record["boundaries"]] != expected
                    or equivalence(record["final"]) != equivalence(original["final"])
                    or record["calls"] != expected_calls[10:] or record["completed_turn"] != 60):
                raise AssertionError(f"genuine checkpoint continuation diverged: {control}")
            if record["raw_events_sha256"] != original["raw_events_sha256"]:
                raise AssertionError(f"continued agent events diverged: {control}")
            original_tail = [v for v in original["boundaries"] if v["turn"] > 40]
            for field, output_key in (("memory_pickle_sha256", "continuation_memory_pickle_difference_turns"),
                                      ("memory_cache", "continuation_cache_difference_turns")):
                evidence["checks"][output_key][control] = [a["turn"] for a, b in zip(original_tail, record["boundaries"])
                                                          if a[field] != b[field]]
        evidence["checks"]["genuine40_to60_continuations_equal"] = True
        persist()
        for control in CONTROLS:
            profiled = launch(f"profile-{control}", "profile", control, args.parent)
            if (equivalence(profiled["final"]) != equivalence(baseline["final"])
                    or profiled["raw_events_sha256"] != baseline["raw_events_sha256"]):
                raise AssertionError(f"profiled execution diverged: {control}")
        evidence["status"] = "complete"
        evidence["adoption"] = "none; diagnostic only; strict serialized promise evaluated separately"
    except BaseException as exc:
        evidence["status"] = "failed"
        evidence["failure"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
        persist()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--phase", choices=("correctness", "profile"), default="correctness", help=argparse.SUPPRESS)
    parser.add_argument("--control", choices=CONTROLS, default="full10", help=argparse.SUPPRESS)
    args = parser.parse_args()
    for name in ("source_root", "parent", "output_root"):
        setattr(args, name, getattr(args, name).resolve())
    if args.output_root == args.source_root or args.source_root in args.output_root.parents:
        raise ValueError("evidence must be outside the frozen source")
    for key in ("RAYON_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        if os.environ.get(key) != "1":
            raise ValueError(f"set {key}=1")
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise ValueError("set PYTHONHASHSEED=0 to match the exact parent")
    sys.path.insert(0, str(args.source_root / "src"))
    worker(args) if args.worker else controller(args)


if __name__ == "__main__":
    main()
