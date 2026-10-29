#!/usr/bin/env python3
"""Stage 1 only: passive current090 worker and strict observer proof.

There is deliberately no executable study CLI. The hosted owner, its admission,
schema reference and actual execution approval are a separate source stage.
No World, native module or project module is imported at module import time.
"""
from __future__ import annotations

import cProfile
from collections import Counter, OrderedDict, defaultdict, deque
import dataclasses
from enum import Enum
import hashlib
import json
import math
from pathlib import Path, PosixPath, PurePath, PurePosixPath, PureWindowsPath, WindowsPath
import random
import struct
import time

SOURCE = "0900f3d203cc74102809bb871a1a057ba91a951f"
PACKAGE = "1f1c720880e45e0e835e033da216b3deee1f755a497b8e189abaf97c2fe9f656"
NATIVE = "14a67f283cf57dc738e05d43d7b86aeca9039821e453e70274dfc1bb42e70e8c"
EXECUTION_APPROVAL = None
HORIZON = 97
WINDOWS = ((8, 16), (88, 96))
CASES = (("small", 12, 2000, ("plain", "profiled")),
         ("agents", 12, 20000, ("profiled", "plain")),
         ("regions", 48, 20000, ("plain", "profiled")))
KINDS = ("AgentSimulator", "EcologySimulator", "PoliticsSimulator")
LIMITS = {"owner_wall_seconds": 2400, "owner_cpu_seconds": 1800,
          "role_wall_seconds": 300, "role_cpu_seconds": 240,
          "address_space_bytes": 4 * 1024**3, "observed_rss_bytes": 2 * 1024**3,
          "entry_disk_bytes": 12 * 1024**3, "entry_ram_bytes": 4 * 1024**3,
          "run_disk_bytes": 3 * 1024**3, "run_ram_bytes": 1024**3,
          "role_output_bytes": 512 * 1024**2, "total_output_bytes": 3 * 1024**3,
          "total_output_files": 5000}


class Refused(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Refused(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def schedule():
    return [{"case": name, "regions": regions, "target": target, "role": role,
             "seed": 42, "civs": 4, "turns": HORIZON}
            for name, regions, target, roles in CASES for role in roles]


def validate_request(request):
    require(type(request) is dict and request in schedule(), "unregistered role")
    # Dict equality permits bool/int equivalence, so enforce each scalar type.
    require(all(type(request[key]) is int for key in ("regions", "target", "seed", "civs", "turns")),
            "role scalar type")
    require(all(type(request[key]) is str for key in ("case", "role")), "role label type")


def scale_world(world, target, sync_civ_population):
    """The old turn_speed_identity transform, with the existing u16 refusal."""
    require(type(target) is int and target in (2000, 20000), "target")
    original_population = sum(r.population for r in world.regions)
    mult = target / max(1, original_population)
    for region in world.regions:
        region.carrying_capacity = max(1, round(region.carrying_capacity * mult))
        region.population = round(region.population * mult)
        require(region.carrying_capacity <= 60000 and region.population <= 60000,
                "region exceeds u16 bridge range")
    for civ in world.civilizations:
        sync_civ_population(civ, world)
    return {"base_population": original_population, "multiplier": mult,
            "start_population": sum(r.population for r in world.regions),
            "region_population": [r.population for r in world.regions],
            "region_capacity": [r.carrying_capacity for r in world.regions]}


def capture_rng(np):
    """JSON-safe actual global states; no seed-derived reconstruction."""
    py = random.getstate()
    nt = np.random.get_state()
    return {"python": [py[0], list(py[1]), py[2]],
            "numpy": [nt[0], nt[1].tolist(), nt[2], nt[3], nt[4]]}


def validate_rng(value):
    require(type(value) is dict and set(value) == {"python", "numpy"}, "RNG keys")
    p, n = value["python"], value["numpy"]
    require(type(p) is list and len(p) == 3 and type(p[0]) is int and p[0] == 3,
            "Python RNG version")
    require(type(p[1]) is list and len(p[1]) == 625
            and all(type(x) is int and 0 <= x <= 2**32 - 1 for x in p[1][:-1])
            and type(p[1][-1]) is int and 0 <= p[1][-1] <= 624, "Python RNG words")
    require(p[2] is None or type(p[2]) is float and math.isfinite(p[2]), "Python Gaussian cache")
    require(type(n) is list and len(n) == 5 and n[0] == "MT19937", "NumPy RNG kind")
    require(type(n[1]) is list and len(n[1]) == 624
            and all(type(x) is int and 0 <= x <= 2**32 - 1 for x in n[1]), "NumPy RNG words")
    require(type(n[2]) is int and 0 <= n[2] <= 624 and type(n[3]) is int and n[3] in (0, 1)
            and type(n[4]) is float and math.isfinite(n[4]), "NumPy RNG cursor/cache")


def restore_rng(value, np):
    validate_rng(value)
    random.setstate((value["python"][0], tuple(value["python"][1]), value["python"][2]))
    n = value["numpy"]
    np.random.set_state((n[0], np.array(n[1], dtype=np.uint32), n[2], n[3], n[4]))
    require(same_rng(capture_rng(np), value), "RNG replay differs")


def same_rng(left, right):
    validate_rng(left)
    validate_rng(right)
    # Both Gaussian cache fields are finite floats. JSON keeps their signed
    # zero, unlike Python dict equality, with no coercion or seed projection.
    return canonical_bytes(left) == canonical_bytes(right)


def native_region_counts(sim, regions):
    """Actual in-domain alive counts; the exact090 getter only reads &self."""
    require(type(regions) is int and regions in (12, 48), "native count region bound")
    batch = sim.get_region_populations()
    require(type(batch.num_rows) is int and batch.num_rows == regions
            and type(batch.num_columns) is int and batch.num_columns == 2
            and batch.schema.names == ["region_id", "alive_count"], "native count table")
    ids, counts = [], []
    for name, target, maximum in (("region_id", ids, regions - 1), ("alive_count", counts, 2**32 - 1)):
        column = batch.column(name)
        require(column.null_count == 0, "native count null")
        values = column.to_pylist()
        require(type(values) is list and len(values) == regions
                and all(type(x) is int and 0 <= x <= maximum for x in values), "native count scalars")
        target.extend(values)
    require(ids == list(range(regions)), "native region order")
    # Extinction is retained, never a replacement/retry or a fabricated sample.
    return {"region_ids": ids, "alive_counts": counts, "in_domain_alive_count": sum(counts)}


class Boundary:
    """Only the existing bind/live_record/turn_end protocol; no simulator proxy."""

    def __init__(self, profiled, *, clock_cpu=time.process_time, clock_wall=time.perf_counter,
                 factory=cProfile.Profile):
        require(type(profiled) is bool, "profile flag")
        self.profiled, self.cpu, self.wall = profiled, clock_cpu, clock_wall
        # Both roles construct the same two disabled stdlib profiler objects.
        self.profiles = [factory(timer=clock_cpu) for _ in WINDOWS]
        self.last, self.active, self.save, self.config = 0, None, None, None
        self.windows, self.context = [], []
        self.starts = {}

    def bind(self, save, run_config):
        require(self.save is None and callable(save) and type(run_config) is dict, "bind once")
        self.save, self.config = save, run_config

    def live_record(self):
        return None

    def turn_end(self, world):
        turn = world.turn
        require(type(turn) is int and turn == self.last + 1 and turn <= HORIZON, "turn sequence")
        for index, (start, end) in enumerate(WINDOWS):
            if turn == end:
                require(self.active == index if self.profiled else self.active is None,
                        "profile window state")
                if self.profiled:
                    self.profiles[index].disable()
                start_cpu, start_wall = self.starts[index]
                # BOTH roles close before the end-boundary Python context work.
                self.windows.append({"start": start, "end": end,
                                     "cpu_seconds": self.cpu() - start_cpu,
                                     "wall_seconds": self.wall() - start_wall})
                self.active = None
        self.last = turn
        if turn in (8, 16, 88, 96, 97):
            # Only Python-owned context is read between physics turns. Even a
            # native &self Arrow getter could create external RandomState keys.
            self.context.append({"turn": turn, "regions": len(world.regions),
                                 "civilizations": len(world.civilizations),
                                 "aggregate_region_population": sum(r.population for r in world.regions),
                                 "timeline_events": len(world.events_timeline),
                                 "named_events": len(world.named_events)})
        for index, (start, _) in enumerate(WINDOWS):
            if turn == start:
                self.starts[index] = self.cpu(), self.wall()
                if self.profiled:
                    self.active = index
                    self.profiles[index].enable()
        return False

    def stop(self):
        for profiler in self.profiles:
            profiler.disable()
        self.active = None

    def finish(self):
        self.stop()
        require(self.save is not None and self.last == HORIZON and len(self.windows) == 2,
                "incomplete boundaries")
        return {"turns_observed": self.last, "windows": self.windows, "context": self.context,
                "profiled_ticks": 16 if self.profiled else 0}

    def rows(self):
        rows = []
        if self.profiled:
            for index, profiler in enumerate(self.profiles):
                profiler.create_stats()
                require(len(profiler.stats) <= 20000, "profile row cap")
                for (filename, line, function), (primitive, calls, own, cumulative, _) in sorted(profiler.stats.items()):
                    require(len(filename) <= 2048 and len(function) <= 2048, "profile label cap")
                    require(all(math.isfinite(x) and x >= 0 for x in (own, cumulative)), "profile time")
                    rows.append({"window": index, "filename": filename, "line": line,
                                 "function": function, "primitive_calls": primitive,
                                 "calls": calls, "self_cpu_seconds": own,
                                 "cumulative_cpu_seconds": cumulative})
        return rows


def marker_view(state, agent_class):
    """Validate the loader's one documented identity marker, never erase it."""
    require(type(state.markers) is dict and state.markers == {"war_roster_bound": True}
            and type(state.markers["war_roster_bound"]) is bool, "unbound/unknown roster marker")
    sim = state.agent_bridge._sim
    require(type(sim) is agent_class, "bridge simulator is not the admitted AgentSimulator")
    public = vars(state.world)
    private = getattr(state.world, "__pydantic_private__", None) or {}
    places = [(name, fields) for name, fields in (("dict", public), ("private", private))
              if "_war_roster_sim" in fields]
    require(len(places) == 1 and type(places[0][1]["_war_roster_sim"]) is int
            and places[0][1]["_war_roster_sim"] == id(sim), "roster marker association/storage")
    return places[0][0]


def numpy_view(value, np):
    """Closed exact types and storage graph; no raw address enters the view.

    Zero-element uint8 views obtain relative buffer addresses only. No source
    buffer is written/reinterpreted into simulation values. Unsupported object,
    structured/metadata dtype, subclass, indirect or noncontiguous base refuses.
    """
    scalar_types = tuple(getattr(np, name) for name in
                         ("bool_", "int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64",
                          "float16", "float32", "float64", "complex64", "complex128", "datetime64",
                          "timedelta64", "bytes_", "str_"))

    def address(buffer):
        if type(buffer) is np.ndarray:
            require(buffer.flags.c_contiguous or buffer.flags.f_contiguous, "noncontiguous base array")
            return buffer.__array_interface__["data"][0], buffer.nbytes
        require(type(buffer) in (bytes, bytearray, memoryview), "unsupported base buffer")
        view = memoryview(buffer)
        require(view.c_contiguous and not view.suboffsets, "unsupported base buffer layout")
        probe = np.frombuffer(view, dtype=np.uint8, count=0)
        return probe.__array_interface__["data"][0], view.nbytes

    if type(value) is memoryview:
        require(value.c_contiguous and not value.suboffsets, "unsupported memoryview layout")
        start, _ = address(value)
        origin, size = address(value.obj)
        offset = start - origin
        require(0 <= offset <= size and offset + value.nbytes <= size, "memoryview base extent")
        return ({"kind": "memoryview", "format": value.format, "itemsize": value.itemsize,
                 "shape": value.shape, "strides": value.strides, "suboffsets": value.suboffsets,
                 "readonly": value.readonly, "nbytes": value.nbytes, "offset": offset,
                 "content": value.tobytes()}, value.obj)
    require(type(value) is np.ndarray or type(value) in scalar_types, "unsupported NumPy exact type")
    dtype = value.dtype
    require(not dtype.hasobject and dtype.fields is None and dtype.subdtype is None
            and dtype.metadata is None, "unsupported NumPy dtype")
    if type(value) is not np.ndarray:
        require(value.base is None, "unexpected scalar base")
        return ({"kind": "scalar", "dtype": dtype.str, "content": value.tobytes()}, None)
    base = value.base
    offset = 0
    require(base is not None or value.flags.owndata, "unanchored nonowning array")
    if base is not None:
        origin, size = address(base)
        offset = value.__array_interface__["data"][0] - origin
        if value.size:
            low = offset + sum(min(0, (d - 1) * s) for d, s in zip(value.shape, value.strides))
            high = offset + sum(max(0, (d - 1) * s) for d, s in zip(value.shape, value.strides)) + dtype.itemsize
            require(0 <= low <= high <= size, "array base extent")
        else:
            require(0 <= offset <= size, "empty array base extent")
    return ({"kind": "ndarray", "dtype": dtype.str, "alignment": dtype.alignment,
             "shape": value.shape, "strides": value.strides, "flags": value.flags.num,
             "nbytes": value.nbytes, "offset": offset, "content": value.tobytes(order="C")}, base)


class StateFingerprint:
    """Complete decoded checkpoint content, not pickle-byte identity.

    Dict iteration order, float bits, all model private/extras and native bytes
    are retained. References/cycles use traversal ordinals, never object IDs.
    Unsupported objects refuse. The memory encoder's identity links are also
    checked explicitly. Only the validated roster marker becomes a bound token.
    """

    def __init__(self, state, native_classes, numpy_api=None):
        self.state, self.classes = state, tuple(native_classes)
        self.numpy_api = numpy_api
        require(bool(self.classes), "missing admitted native classes")
        self.marker_place = marker_view(state, self.classes[0])
        self.marker_mapping = (vars(state.world) if self.marker_place == "dict"
                               else state.world.__pydantic_private__)
        self.hash, self.memo, self.objects, self.nodes = hashlib.sha256(), {}, [], 0

    def emit(self, tag, data=b""):
        self.hash.update(tag.encode() + b":" + str(len(data)).encode() + b":" + data + b";")

    def visit(self, value):
        self.nodes += 1
        require(self.nodes <= 5_000_000, "state node cap")
        if value is None: return self.emit("none")
        if isinstance(value, Enum):
            require(type(value).__module__.startswith("chronicler."), "unqualified Enum type")
            self.emit("enum", (type(value).__module__ + "." + type(value).__qualname__).encode())
            return self.visit(value.value)
        if type(value) in (bool, int, str): return self.emit(type(value).__name__, str(value).encode())
        if type(value) is float: return self.emit("float64", struct.pack("!d", value))
        if type(value) is bytes: return self.emit("bytes", value)
        require(not isinstance(value, (bool, int, str, float, bytes, bytearray))
                or type(value) is bytearray or type(value).__module__.startswith("numpy"),
                "unsupported scalar/bytearray subclass")
        if isinstance(value, PurePath):
            require(type(value) in (Path, PosixPath, WindowsPath, PurePath, PurePosixPath, PureWindowsPath),
                    "unsupported path subclass")
            return self.emit("path", canonical_bytes([type(value).__module__, type(value).__qualname__, str(value)]))
        ident = id(value)
        if ident in self.memo:
            return self.emit("reference", str(self.memo[ident]).encode())
        self.memo[ident] = len(self.objects)
        # Keep reducer-created dictionaries alive, so temporary Python object
        # IDs cannot be recycled and mistaken for a reference during this view.
        self.objects.append(value)
        try:
            self.emit("type", (type(value).__module__ + "." + type(value).__qualname__).encode())
            if type(value) is bytearray:
                self.emit("mutable-bytes", bytes(value))
            elif type(value) in self.classes:
                self.emit("native", bytes(value.checkpoint_state()))
            elif isinstance(value, dict):
                require(type(value) in (dict, Counter, OrderedDict, defaultdict), "unsupported dict subclass")
                for key, item in value.items():
                    self.visit(key)
                    if value is self.marker_mapping and key == "_war_roster_sim":
                        self.emit("checkpoint-rebound", b"agent_bridge._sim")
                    else:
                        self.visit(item)
                if hasattr(value, "default_factory"):
                    factory = value.default_factory
                    require(factory is None or factory in (list, dict, set, int, float, Counter, OrderedDict),
                            "default factory")
                    self.visit(None if factory is None else factory.__name__)
                if hasattr(value, "__dict__"): self.visit(vars(value))
            elif isinstance(value, (list, tuple, deque)):
                require(type(value) in (list, tuple, deque), "unsupported sequence subclass")
                for item in value: self.visit(item)
                if isinstance(value, deque): self.visit(value.maxlen)
            elif isinstance(value, (set, frozenset)):
                require(type(value) in (set, frozenset), "unsupported set subclass")
                # Deterministic content order before assigning reference ordinals.
                for item in sorted(value, key=set_key): self.visit(item)
            elif type(value) is memoryview or type(value).__module__.startswith("numpy"):
                require(self.numpy_api is not None, "NumPy storage reader is not admitted")
                metadata, base = numpy_view(value, self.numpy_api)
                self.visit(metadata); self.visit(base)
            elif isinstance(value, random.Random):
                require(type(value) is random.Random, "unsupported Random subclass")
                self.visit(value.getstate())
                self.visit(vars(value))
            elif hasattr(type(value), "model_fields"):
                self.object_fields(value)
            elif dataclasses.is_dataclass(value):
                self.object_fields(value)
            elif type(value).__module__.startswith("chronicler."):
                # The strict loader has already reconstructed these objects.
                # Inspect actual decoded fields, not a reducer that can omit
                # an extra field or construct fresh alias-losing containers.
                self.object_fields(value)
            else:
                raise Refused("unsupported state type: " + type(value).__module__ + "." + type(value).__qualname__)
        finally:
            self.emit("end")

    def object_fields(self, value):
        has_dict = hasattr(value, "__dict__")
        if has_dict:
            self.visit(vars(value))
        names = []
        for cls in type(value).__mro__:
            declared = vars(cls).get("__slots__", ())
            if type(declared) is str: declared = (declared,)
            for name in declared:
                if name in ("__dict__", "__weakref__"): continue
                # Python's double-underscore slot spelling is name-mangled.
                if name.startswith("__") and not name.endswith("__"):
                    name = "_" + cls.__name__.lstrip("_") + name
                require(name not in names, "ambiguous duplicate slot storage")
                names.append(name)
        require(has_dict or bool(names), "unsupported object fields")
        for name in names:
            self.visit(name)
            if hasattr(value, name): self.visit(getattr(value, name))
            else: self.emit("absent-slot")

    def result(self):
        self.visit(self.state)
        # Keep the old memory encoder identity witness, with actual contents
        # already included by each stream's complete __getstate__/dict above.
        cache = {}
        for name, stream in self.state.memories.items():
            cache[name] = {}
            for kind, rows in vars(stream).get("_encoded", {}).items():
                require(kind in ("entries", "reflections") and len(rows) <= len(getattr(stream, kind)),
                        "memory encoder kind/length")
                require(all(row[0] is getattr(stream, kind)[index]
                            and all(row[i] is getattr(row[0], field) for i, field in
                                ((1, "turn"), (2, "text"), (3, "importance"), (4, "entry_type")))
                            for index, row in enumerate(rows)), "memory encoder identity")
                cache[name][kind] = len(rows)
        return {"sha256": self.hash.hexdigest(), "nodes": self.nodes,
                "reference_objects": len(self.objects), "memory_cache_rows": cache,
                "marker": {"storage": self.marker_place, "war_roster_bound": True}}


def set_key(value):
    """Closed ordering for checkpoint sets; no repr/identity fallback."""
    if value is None: return b"none"
    if isinstance(value, Enum):
        return canonical_bytes([type(value).__module__, type(value).__qualname__, set_key(value.value).hex()])
    if type(value) in (bool, int, str, bytes):
        content = value.hex() if type(value) is bytes else value
        return canonical_bytes([type(value).__name__, content])
    if type(value) is float: return b"float" + struct.pack("!d", value)
    if type(value) is tuple: return canonical_bytes(["tuple", [set_key(v).hex() for v in value]])
    if type(value) is frozenset: return canonical_bytes(["frozenset", sorted(set_key(v).hex() for v in value)])
    raise Refused("unsupported set member")


def profile_equivalent(left, right, compare_dirs, raw_bundle_problems, left_dir, right_dir):
    """Use the unchanged old comparator, no new output exclusions/normalizer."""
    checked, problems = compare_dirs(left_dir, right_dir)
    problems += raw_bundle_problems(left_dir, right_dir)
    require(checked > 0 and not problems, "ordinary output mismatch")
    # Paths must have been identical at production time, not normalized here.
    for key in ("initial_rng", "final_rng"):
        require(same_rng(left[key], right[key]), "observer mismatch: " + key)
    for key in ("logical_output", "state", "run_result", "identity"):
        require(canonical_bytes(left[key]) == canonical_bytes(right[key]), "observer mismatch: " + key)
    return {"checked_files": checked, "differences": 0, "instrumentation_equal": True}


def result_record(result):
    row = dataclasses.asdict(result)
    require(isinstance(row["output_dir"], Path), "run output path type")
    row["output_dir"] = str(row["output_dir"])
    return row


def run_role(request, *, ordinary, checkpoint, shared_rng, admission):
    """Future owned child entry. Unreachable until a separately reviewed stage.

    The owner must enforce LIMITS, exact44f resources, source/wheel expiry and
    all-three-schema/runtime admission before calling. Stage1 grants no owner.
    """
    require(EXECUTION_APPROVAL is not None, "actual execution is not approved")
    validate_request(request)
    require(admission.get("approval") == EXECUTION_APPROVAL, "owner admission")
    # Imports are identical for both roles and occur before replaying globals.
    import numpy as np
    import chronicler_agents as native
    from importlib import import_module
    from importlib.machinery import EXTENSION_SUFFIXES
    from chronicler import main as cm, run_checkpoint as rc
    from chronicler.batch_manifest import package_digest, native_identity
    from chronicler.utils import sync_civ_population
    import resource
    require(package_digest() == PACKAGE and native_identity().get("sha256") == NATIVE, "source/native")
    classes = tuple(getattr(native, name) for name in KINDS)
    compiled = import_module("chronicler_agents.chronicler_agents")
    require(str(compiled.__file__).endswith(tuple(EXTENSION_SUFFIXES))
            and all(isinstance(cls, type) and cls is getattr(compiled, name)
                    for name, cls in zip(KINDS, classes)), "compiled classes")
    schemas = {name: list(cls.checkpoint_schema()) for name, cls in zip(KINDS, classes)}
    require(schemas == admission["schemas"] and all(schemas.values()), "schema reference")
    require(rc.runtime_identity() == admission["identity"], "runtime identity")
    require(admission["identity"]["source"] == {"git_sha": SOURCE, "package_digest": PACKAGE},
            "exact source root")
    require(ordinary.is_absolute() and checkpoint.is_absolute() and ordinary not in checkpoint.parents,
            "separate absolute proof/output paths")
    require(not ordinary.exists() and not ordinary.is_symlink(), "fresh ordinary path")
    ordinary.mkdir(parents=True)
    observer = Boundary(request["role"] == "profiled")
    original = cm.generate_world
    scaling = {}

    def scaled(*args, **kwargs):
        world = original(*args, **kwargs)
        scaling.update(scale_world(world, request["target"], sync_civ_population))
        return world

    parser = cm._build_parser()
    args = parser.parse_args(["--seed", "42", "--turns", "97", "--worldgen", "procedural",
                              "--regions", str(request["regions"]),
                              "--civs", "4", "--agents", "hybrid", "--agent-scale-mode", "exact",
                              "--simulate-only", "--validation-sidecar", "--output",
                              str(ordinary / "chronicle.md"), "--state", str(ordinary / "state.json")])
    restore_rng(shared_rng, np)
    require(same_rng(capture_rng(np), shared_rng), "initial global RNG")
    cpu, wall = time.process_time(), time.perf_counter()
    try:
        cm.generate_world = scaled
        result = cm.execute_run(args, turn_boundary=observer)
    finally:
        try:
            observer.stop()
        finally:
            cm.generate_world = original
    run_clock = {"cpu_seconds": time.process_time() - cpu, "wall_seconds": time.perf_counter() - wall}
    run_peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    boundary = observer.finish()
    final_rng = capture_rng(np)
    require(result.total_turns == HORIZON, "early completion")
    require(run_clock["cpu_seconds"] <= LIMITS["role_cpu_seconds"]
            and run_clock["wall_seconds"] <= LIMITS["role_wall_seconds"]
            and run_peak_rss <= LIMITS["observed_rss_bytes"], "role budget")
    # The saved callback holds the final carried state, after ordinary exports.
    # Proof reads/writes are all outside both profile windows and run clocks.
    proof_cpu, proof_wall = time.process_time(), time.perf_counter()
    path = observer.save(checkpoint)
    loaded = rc.read_checkpoint(path)
    require(loaded.exact and loaded.state.world.turn == HORIZON, "own final checkpoint")
    require(loaded.header["identity"] == admission["identity"], "checkpoint identity")
    view = StateFingerprint(loaded.state, classes, np).result()
    sim = loaded.state.agent_bridge._sim
    before = digest(bytes(sim.checkpoint_state()))
    population = native_region_counts(sim, request["regions"])
    require(before == digest(bytes(sim.checkpoint_state())), "population getter changed native state")
    require(same_rng(final_rng, capture_rng(np)), "proof changed global RNG")
    require(package_digest() == PACKAGE and native_identity().get("sha256") == NATIVE,
            "final source/native bytes")
    require(rc.runtime_identity() == admission["identity"] and schemas ==
            {name: list(cls.checkpoint_schema()) for name, cls in zip(KINDS, classes)}, "final identity")
    return {"request": request, "logical_output": str(ordinary), "initial_rng": shared_rng,
            "final_rng": final_rng, "identity": admission["identity"], "state": view,
            "run_result": result_record(result), "scaling": scaling, "boundary": boundary,
            "run_clock": run_clock, "profile_rows": observer.rows(),
            "execute_run_process_peak_rss_bytes": run_peak_rss,
            "proof_process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "proof_clock": {"cpu_seconds": time.process_time() - proof_cpu,
                            "wall_seconds": time.perf_counter() - proof_wall},
            "actual_final_native": population,
            "final_history_snapshots": len(loaded.state.history),
            "checkpoint": {"path": str(path), "raw_byte_identity_claim": False}}


if __name__ == "__main__":
    raise SystemExit("Stage 1 source only: hosted ownership/admission and execution approval are absent")
