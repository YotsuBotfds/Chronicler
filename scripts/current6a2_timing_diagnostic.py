"""Inactive current6a2 timing-only worker. This is not the accepted090 profiler.

Public runtime entry points refuse before project/native imports while approval
is NULL. Production/native source and the old5M checkpoint proof are untouched.
"""
from __future__ import annotations

import hashlib
import importlib
import math
import os
from pathlib import Path
import random
import re
import sys
import time

import current6a2_timing_records as records

SOURCE = "6a2a7b84b7d6ea10bfa4f6574e1f5dc793c092e8"
SOURCE_DIGEST = "513b1087cfb977306df70075118b78c082644f2bade337c68934d08b6b318a53"
NATIVE_SHA = "1ec3282dd43bc1ecfa2459960f19047aec5d8744406b5655aef44202585eaf72"
NATIVE_BYTES = 13765672
WHEEL_SHA = "a68aac26f4c5571034f10352db8b44da99acfa66aa378d1a5d90f13fc48082fc"
WHEEL_BYTES = 3947205
EXECUTION_APPROVAL = None
JOB_CLOCK_ADMISSION_APPROVAL = None
HORIZON = 97
WINDOWS = ((8, 16), (88, 96))
KINDS = ("AgentSimulator", "EcologySimulator", "PoliticsSimulator")
CASES = (("small", 12, 2000, ("plain", "profiled")),
         ("agents", 12, 20000, ("profiled", "plain")),
         ("regions", 48, 20000, ("plain", "profiled")))
CAPS = {key: "1" for key in ("BLIS_NUM_THREADS", "CARGO_BUILD_JOBS", "GOTO_NUM_THREADS",
        "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
        "PYTHON_CPU_COUNT", "RAYON_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")}
CAPS.update(PYTHONHASHSEED="0", OPENBLAS_THREAD_TIMEOUT="16")
TARGETS = frozenset(("execute_run", "run_turn_result", "_process_tick_results",
                    "_process_promotions", "_get_agent_memory_records", "_decode_agent_memory_row",
                    "_save_memory_streams", "_write_state_checkpoint", "assemble_bundle", "write_bundle"))
GETTERS = ("get_agent_memories", "get_agent_needs", "get_agent_relationships")
require = records.require


def require_approval():
    require(EXECUTION_APPROVAL is not None, "timing diagnostic execution approval is NULL")
    require(JOB_CLOCK_ADMISSION_APPROVAL is not None, "actual job-clock review approval is NULL")


def schedule():
    result = []
    for case, regions, target, roles in CASES:
        for role in roles:
            result.append(dict(index=len(result), case=case, regions=regions,
                               aggregate_target_request=target, role=role, seed=42,
                               civilizations=4, requested_turns=97))
    return result


def validate_request(request):
    require(type(request) is dict and request in schedule(), "unregistered diagnostic role")
    for key in ("index", "regions", "aggregate_target_request", "seed", "civilizations", "requested_turns"):
        require(type(request.get(key)) is int, "exact role integer type")
    require(type(request["case"]) is str and type(request["role"]) is str, "exact role labels")
    return request


def scale_world(world, target, sync_civ_population):
    """The existing090 arithmetic, now explicitly bound to current6a2 input."""
    require(type(target) is int and target in (2000, 20000), "scaling target")
    original_population = sum(r.population for r in world.regions)
    multiplier = target / max(1, original_population)
    for region in world.regions:
        region.carrying_capacity = max(1, round(region.carrying_capacity * multiplier))
        region.population = round(region.population * multiplier)
        require(region.carrying_capacity <= 60000 and region.population <= 60000,
                "region exceeds u16 bridge range")
    for civilization in world.civilizations:
        sync_civ_population(civilization, world)
    return {"base_Python_region_population": original_population, "multiplier": multiplier,
            "start_Python_region_population": sum(r.population for r in world.regions),
            "requested_target": target, "actual_native_population": None}


class DiagnosticBoundary:
    """Only bind/live_record/turn_end; no save closure, World, config or getter held."""

    def __init__(self, profiled, *, cpu=time.process_time, wall=time.perf_counter, factory=None):
        require(type(profiled) is bool, "profiled exact boolean")
        if factory is None:
            import cProfile
            factory = cProfile.Profile
        self.profiled, self.cpu, self.wall = profiled, cpu, wall
        self.profiles = [factory(timer=cpu, subcalls=True, builtins=True) for _ in WINDOWS]
        self.bound = False
        self.last = 0
        self.active = None
        self.starts = {}
        self.windows = []

    def bind(self, save, run_config):
        require(not self.bound and callable(save) and type(run_config) is dict, "bind once")
        self.bound = True

    def live_record(self):
        return None

    def turn_end(self, world):
        turn = world.turn
        require(self.bound and type(turn) is int and turn == self.last + 1 and turn <= HORIZON,
                "boundary sequence")
        for index, (start, end) in enumerate(WINDOWS):
            if turn == end:
                require(self.active == index if self.profiled else self.active is None,
                        "profile window state")
                if self.profiled:
                    self.profiles[index].disable()
                first_cpu, first_wall = self.starts[index]
                cpu, wall = self.cpu() - first_cpu, self.wall() - first_wall
                records.seconds(cpu); records.seconds(wall)
                self.windows.append(dict(start=start, end=end, cpu_seconds=cpu, wall_seconds=wall))
                self.active = None
        self.last = turn
        for index, (start, _end) in enumerate(WINDOWS):
            if turn == start:
                self.starts[index] = self.cpu(), self.wall()
                if self.profiled:
                    self.active = index
                    self.profiles[index].enable()
        return False

    def stop(self):
        failure = None
        for profile in self.profiles:
            try:
                profile.disable()
            except BaseException as exc:
                failure = failure or exc
        self.active = None
        if failure is not None:
            raise failure

    def complete(self):
        return self.bound and self.last == 97 and [(w["start"], w["end"]) for w in self.windows] == list(WINDOWS)


def _function_key(value):
    require(type(value) is tuple and len(value) == 3, "profile function key")
    filename, line, function = value
    require(type(filename) is str and type(function) is str, "profile label strings")
    require(len(filename.encode("utf-8")) <= 2048 and len(function.encode("utf-8")) <= 2048,
            "profile UTF8 label cap")
    records.integer(line)
    return {"filename": filename, "line": line, "function": function}


def _native_getter(function):
    for name in GETTERS:
        if re.fullmatch(r"<method '" + name + r"' of '(?:builtins\.|chronicler_agents(?:\.chronicler_agents)?\.)?AgentSimulator' objects>", function):
            return name
    return None


def _profile_counters(value):
    require(type(value) is tuple and len(value) == 4, "profile counter tuple")
    primitive, calls, own, cumulative = value
    records.integer(primitive); records.integer(calls)
    require(calls >= primitive, "profile call counts")
    records.seconds(own); records.seconds(cumulative)
    return dict(primitive_calls=primitive, calls=calls, self_cpu_seconds=own,
                cumulative_cpu_seconds=cumulative)


def profile_detail(boundary):
    rows, edges = [], []
    if boundary.profiled:
        for window, profile in enumerate(boundary.profiles):
            # This runs only after the immutable scalar summary is committed.
            profile.create_stats()
            require(type(profile.stats) is dict and len(profile.stats) <= 20000, "profile function row cap")
            window_edges = 0
            for key, counters in sorted(profile.stats.items()):
                name = _function_key(key)
                require(type(counters) is tuple and len(counters) == 5, "profile stats tuple")
                row = {"window": window, **name, **_profile_counters(counters[:4])}
                rows.append(row)
                # Preserve opaque C/native caller edges even when the actual
                # PyO3 label cannot yet be semantically resolved. Unknown is not
                # zero, and a later metadata reader need not rerun a World just
                # to inspect a first-run label representation.
                selected = name["function"] in TARGETS or name["filename"] == "~" or _native_getter(name["function"]) is not None
                if selected:
                    callers = counters[4]
                    require(type(callers) is dict, "selected caller map")
                    window_edges += len(callers)
                    require(window_edges <= 40000, "selected caller edge cap")
                    for caller, facts in sorted(callers.items()):
                        edges.append({"window": window, "callee": name, "caller": _function_key(caller),
                                      **_profile_counters(facts)})
    return {"kind": "TIMING_ONLY_COMPLETE_PROFILE_DETAIL", "protocol": records.PROTOCOL,
            "profiled": boundary.profiled, "function_rows": rows, "selected_caller_edges": edges,
            "table_complete": True, "timer": "time.process_time floating CPU seconds",
            "timer_event_overhead_measured": False, "native_internal_attribution": None,
            "unresolved_label_coverage_is_zero": False, "unknown": dict(records.UNKNOWN)}


def sync_opportunity(detail, windows, source_root):
    """Inclusive opportunity only; memory helper work is not all removable work."""
    result = []
    expected_file = str(Path(source_root) / "src/chronicler/agent_bridge.py")
    for index, clock in enumerate(windows):
        candidates = []
        for edge in detail["selected_caller_edges"]:
            caller, callee = edge["caller"], edge["callee"]
            if edge["window"] != index or caller != {"filename": expected_file,
                    "line": 1511, "function": "_process_tick_results"}:
                continue
            target = callee["function"] if callee["filename"] == expected_file else _native_getter(callee["function"])
            if target in ("_get_agent_memory_records", "get_agent_needs", "get_agent_relationships"):
                candidates.append((target, edge["cumulative_cpu_seconds"]))
        labels = [label for label, _ in candidates]
        covered = sorted(labels) == sorted(("_get_agent_memory_records", "get_agent_needs", "get_agent_relationships"))
        total = sum(value for _label, value in candidates) if covered else None
        fraction = total / clock["cpu_seconds"] if covered and clock["cpu_seconds"] > 0 else None
        if fraction is not None and (not math.isfinite(fraction) or not 0 <= fraction <= 1):
            covered, total, fraction = False, None, None
        result.append({"window": index, "complete_selected_caller_coverage": covered,
                       "inclusive_sync_opportunity_cpu_seconds": total,
                       "observed_profiled_window_CPU_fraction": fraction,
                       "interpretation": "includes memory decoding; not removable CPU or predicted gain"})
    return result


def capture_rng(np):
    py, nt = random.getstate(), np.random.get_state()
    return {"python": [py[0], list(py[1]), py[2]],
            "numpy": [nt[0], nt[1].tolist(), nt[2], nt[3], nt[4]]}


def validate_rng(value):
    require(type(value) is dict and set(value) == {"python", "numpy"}, "RNG keys")
    p, n = value["python"], value["numpy"]
    require(type(p) is list and len(p) == 3 and type(p[0]) is int and p[0] == 3, "Python RNG version")
    require(type(p[1]) is list and len(p[1]) == 625 and all(type(x) is int and 0 <= x <= 2**32 - 1 for x in p[1][:-1])
            and type(p[1][-1]) is int and 0 <= p[1][-1] <= 624, "Python RNG words")
    require(p[2] is None or type(p[2]) is float and math.isfinite(p[2]), "Python Gaussian cache")
    require(type(n) is list and len(n) == 5 and n[0] == "MT19937", "NumPy RNG kind")
    require(type(n[1]) is list and len(n[1]) == 624 and all(type(x) is int and 0 <= x <= 2**32 - 1 for x in n[1]), "NumPy RNG words")
    require(type(n[2]) is int and 0 <= n[2] <= 624 and type(n[3]) is int and n[3] in (0, 1)
            and type(n[4]) is float and math.isfinite(n[4]), "NumPy RNG cursor/cache")


def restore_rng(value, np):
    validate_rng(value)
    random.setstate((value["python"][0], tuple(value["python"][1]), value["python"][2]))
    n = value["numpy"]
    np.random.set_state((n[0], np.array(n[1], dtype=np.uint32), n[2], n[3], n[4]))
    observed = capture_rng(np)
    validate_rng(observed)
    require(records.canonical(observed) == records.canonical(value), "initial RNG replay differs")


def verify_producer(source_root, expected_hashes):
    source_root = records.absolute(source_root)
    require(type(expected_hashes) is dict and len(expected_hashes) == 803
            and records.digest(expected_hashes) == SOURCE_DIGEST, "803 protected source pins")
    actual = {}
    discovered = {"pyproject.toml", "uv.lock"}
    for directory in ("src", "scripts", "tests", "chronicler-agents"):
        observed = records.stat_inventory(source_root / directory)
        discovered.update(directory + "/" + name for name in observed["identities"])
    require(discovered == set(expected_hashes), "closed protected producer file set")
    for name, expected in sorted(expected_hashes.items()):
        require(type(name) is str and not name.startswith("/") and ".." not in Path(name).parts,
                "relative source pin path")
        actual[name] = records.hash_regular(source_root / name, 16 * 1024**2)["sha256"]
        require(actual[name] == expected, "producer source file differs")
    require(records.digest(actual) == SOURCE_DIGEST, "producer source digest differs")


def runtime_flags():
    require(sys.platform == "linux" and sys.version_info[:2] == (3, 13), "admitted Linux CPython3.13")
    require(sys.flags.safe_path and sys.flags.no_user_site and not sys.flags.ignore_environment
            and not sys.flags.isolated and not sys.flags.hash_randomization, "actual runtime flags")
    require(os.cpu_count() == 1 and len(os.sched_getaffinity(0)) == 1, "one actual CPU")
    require(all(os.environ.get(key) == value for key, value in CAPS.items()), "thread/hash environment")
    return {"safe_path": True, "no_user_site": True, "ignore_environment": False,
            "isolated": False, "hash_randomization": False, "logical_CPUs": 1,
            "affinity_CPUs": 1, "RSS_unit": "LinuxKiB", "python": sys.version}


def import_runtime(source_root, prefix, expected_hashes):
    require_approval()
    verify_producer(source_root, expected_hashes)
    flags = runtime_flags()
    # Bootstrap and roles complete the same pre-run imports before RNG capture/replay.
    # No profiler object is enabled here, and the NULL guard precedes this import.
    import cProfile
    import numpy as np
    import chronicler_agents as native
    from importlib.machinery import EXTENSION_SUFFIXES
    from chronicler import main as cm
    from chronicler.utils import sync_civ_population
    compiled = importlib.import_module("chronicler_agents.chronicler_agents")
    path = records.absolute(Path(compiled.__file__))
    prefix = records.absolute(prefix)
    require(path.is_relative_to(prefix) and str(path).endswith(tuple(EXTENSION_SUFFIXES)), "compiled extension origin")
    require(records.hash_regular(path, NATIVE_BYTES) == {"bytes": NATIVE_BYTES, "sha256": NATIVE_SHA}, "fresh6a2 native bytes")
    require(all(isinstance(getattr(native, name), type) and getattr(native, name) is getattr(compiled, name)
                for name in KINDS), "compiled class exports")
    src = records.absolute(Path(source_root) / "src")
    for name, module in list(sys.modules.items()):
        if name == "chronicler" or name.startswith("chronicler."):
            require(module is not None and getattr(module, "__file__", None)
                    and Path(module.__file__).resolve().is_relative_to(src), "project import origin")
    identity = {"producer_source": SOURCE, "source_digest": SOURCE_DIGEST,
                "native_sha256": NATIVE_SHA, "native_bytes": NATIVE_BYTES,
                "compiled_classes": list(KINDS), "runtime_flags": flags,
                "actual_schema_tuples": None, "installed_new_API_execution": None}
    return cm, np, sync_civ_population, identity


def record_call(execute, args, boundary, request, summary_path, identity, *,
                cpu=time.process_time, wall=time.perf_counter, peak=None):
    """Callable-injected seam for fake clocks/runners; no import/proof/getter here."""
    validate_request(request)
    if peak is None:
        import resource
        peak = lambda: resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    result, failure, returned = None, None, False
    first_cpu = first_wall = end_cpu = end_wall = None
    clock_failed = False
    stop_failed = False
    try:
        try:
            first_cpu, first_wall = cpu(), wall()
        except BaseException as exc:
            failure, clock_failed = exc, True
        if failure is None:
            try:
                result = execute(args, turn_boundary=boundary)
                returned = True
            except BaseException as exc:
                failure = exc
        try:
            end_cpu, end_wall = cpu(), wall()
        except BaseException as exc:
            failure, clock_failed = failure or exc, True
    finally:
        try:
            boundary.stop()
        except BaseException as exc:
            failure, stop_failed = failure or exc, True
    cpu_elapsed = wall_elapsed = None
    try:
        cpu_elapsed, wall_elapsed = end_cpu - first_cpu, end_wall - first_wall
        records.seconds(cpu_elapsed); records.seconds(wall_elapsed)
    except (TypeError, ValueError):
        cpu_elapsed = wall_elapsed = None
        failure, clock_failed = failure or records.Refused("clock unavailable"), True
    peak_value, peak_failed = None, False
    try:
        peak_value = peak()
        records.integer(peak_value)
    except BaseException as exc:
        failure, peak_failed = failure or exc, True
        peak_value = None
    observed = boundary.last if boundary.last > 0 else None
    within_budget = not clock_failed and not peak_failed and cpu_elapsed <= 240 and wall_elapsed <= 300 and peak_value <= 2 * 1024**3
    complete = returned and type(getattr(result, "total_turns", None)) is int and result.total_turns == 97 and boundary.complete() and not stop_failed and within_budget
    value = {"kind": "TIMING_ONLY_ROLE_SUMMARY", "protocol": records.PROTOCOL,
             "request": request, "identity": identity, "execute_run_returned": returned,
             "role_complete": complete, "completed_world_turn_boundaries": observed,
             "closed_windows": list(boundary.windows),
             "execute_run_clock": {"cpu_seconds": cpu_elapsed, "wall_seconds": wall_elapsed},
             "process_lifetime_peak_RSS_bytes": peak_value,
             "RSS_scope": "Linux process-lifetime high-water, including imports/setup/exports",
             "profiled": request["role"] == "profiled", "bare_CLI_baseline": False,
             "failure_code": "CLOCK_READ_FAILED" if clock_failed else "RESOURCE_READ_FAILED" if peak_failed else "STOP_FAILED" if stop_failed else "EXECUTE_RAISED" if failure else "OBSERVED_ROLE_BUDGET" if not within_budget else None if complete else "INCOMPLETE_BOUNDARIES",
             "unknown": dict(records.UNKNOWN)}
    records.validate_summary(value)
    records.write_new(summary_path, value)
    if failure is not None:
        raise failure
    require(complete, "normal execute_run did not complete registered boundaries")
    return value


def run_role(request, *, source_root, prefix, expected_hashes, ordinary, role_root, shared_rng):
    require_approval()
    validate_request(request)
    cm, np, sync_civ_population, identity = import_runtime(source_root, prefix, expected_hashes)
    ordinary, role_root = records.absolute(ordinary), records.absolute(role_root)
    require(not ordinary.exists() and not ordinary.is_symlink(), "fresh ordinary path")
    ordinary.mkdir()
    require(role_root.is_dir(), "existing fresh role metadata directory")
    boundary = DiagnosticBoundary(request["role"] == "profiled")
    original = cm.generate_world
    scaling = {}
    def scaled(*args, **kwargs):
        world = original(*args, **kwargs)
        scaling.update(scale_world(world, request["aggregate_target_request"], sync_civ_population))
        return world
    args = cm._build_parser().parse_args(["--seed", "42", "--turns", "97", "--worldgen", "procedural",
            "--regions", str(request["regions"]), "--civs", "4", "--agents", "hybrid",
            "--agent-scale-mode", "exact", "--simulate-only", "--validation-sidecar",
            "--output", str(ordinary / "chronicle.md"), "--state", str(ordinary / "state.json")])
    restore_rng(shared_rng, np)
    identity["initial_rng_input_sha256"] = records.digest(shared_rng)
    try:
        cm.generate_world = scaled
        summary = record_call(cm.execute_run, args, boundary, request, role_root / "summary.json", identity)
    finally:
        cm.generate_world = original
    # Failure here cannot erase the committed scalar summary.
    require(summary["execute_run_clock"]["cpu_seconds"] <= 240
            and summary["execute_run_clock"]["wall_seconds"] <= 300
            and summary["process_lifetime_peak_RSS_bytes"] <= 2 * 1024**3, "observed role budget")
    try:
        detail = profile_detail(boundary)
        detail["scaling"] = scaling
        detail["sync_opportunity"] = sync_opportunity(detail, boundary.windows, source_root) if boundary.profiled else []
        records.write_new(role_root / "detail.json", detail, records.DETAIL_BYTES)
        detail_status = {"available": True, "reason": None}
    except Exception:
        detail_status = {"available": False, "reason": "PROFILE_DETAIL_REFUSED"}
    records.write_new(role_root / "detail-status.json", detail_status)
    import_runtime(source_root, prefix, expected_hashes)
    import resource
    require(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 <= 2 * 1024**3,
            "whole child lifetime RSS budget")
    return summary
