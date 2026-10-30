"""Closed live-cache identity representation for a distinct diagnostic pilot.

No runtime/product imports at module import. The legacy fingerprint modules stay
byte-exact. Token-segment digests below are observations of the SAME global
traversal/reference ordinals, never independently re-rooted value fingerprints.
"""
from __future__ import annotations

import hashlib
import time
from collections import deque

import wholeturn_state_proof as old
from wholeturn_live_proof import LiveFingerprint, arrow_adapter
import wholeturn_cache_protocol as p

ENCODING = "validated-agent-bridge-cache-identity-v1"
FIELD_RECORDS = 512
FIELD_BYTES = 64 * 1024
BINDING_BYTES = 16 * 1024
SEGMENT_SCOPE = "SAME_GLOBAL_EMITTED_TOKEN_SEGMENT_WITH_REFERENCE_ORDINALS"


def _mapping(value, reason):
    old.require(type(value) is dict, reason)
    return value


def _ref(index, value):
    ordinal = index.memo.get(id(value))
    old.require(type(ordinal) is int and 0 <= ordinal < len(index.objects)
                and index.objects[ordinal] is value, "orphan cache identity reference")
    return ordinal


def _raw_key(key):
    if type(key) is int:
        return key
    if type(key) is str:
        return key
    old.require(type(key) is tuple, "unsupported cache key witness")
    return [_raw_key(part) for part in key]


class CacheBindings:
    """Validate source-owned caches against one completed legacy traversal.

    The index retains its actual referents. No cache or live state is changed;
    stale lengths/off-window strong references remain hashed as ordinary data.
    """

    def __init__(self, index, bridge_class):
        old.require(getattr(index, "global_complete", False) is True,
                    "completed old global traversal required")
        self.index = index
        state = index.state
        bridge = state.agent_bridge
        old.require(type(bridge) is bridge_class, "exact admitted bridge class")
        fields = _mapping(vars(bridge), "ordinary bridge fields")
        self.maps, self.key_tuples, self.targets, self.entries = {}, {}, {}, []
        self.bound_ordinals = set()
        self.states = {}
        window = fields.get("_event_window", ())
        old.require(type(window) in (deque, tuple, list), "closed event window witness")
        self.window = window
        for name, kind in (("_window_stats_cache", "window"), ("_named_actor_memo", "memo")):
            if name not in fields:
                self.states[name] = "ABSENT"
                continue
            cache = fields[name]
            if cache is None:
                self.states[name] = "NONE"
                continue
            _mapping(cache, "exact cache dictionary")
            ident = id(cache)
            old.require(ident not in self.maps, "ambiguous aliased cache dictionaries")
            self.maps[ident] = {"object": cache, "name": name, "entries": []}
            self.states[name] = "DICT"
            _ref(index, cache)
            for ordinal, (key, value) in enumerate(cache.items()):
                old.require(type(value) is tuple and len(value) == 3,
                            "exact retained cache value tuple")
                _ref(index, value)
                _mapping(value[2], "exact cache result mapping")
                entry = {"cache": name, "order": ordinal, "raw_key": _raw_key(key),
                         "cache_ref_ordinal": _ref(index, cache),
                         "key_ref_ordinal": None if type(key) is int else _ref(index, key),
                         "value_ref_ordinal": _ref(index, value),
                         "stats_ref_ordinal": _ref(index, value[2])}
                if kind == "window":
                    old.require(type(key) is int and type(value[0]) is list
                                and key == id(value[0]), "window key identity binding")
                    old.require(type(value[1]) is int and value[1] >= 0,
                                "cached length is an observed nonnegative integer")
                    ref = _ref(index, value[0])
                    self.bound_ordinals.add(ref)
                    entry.update(key_binding={"scalar_ref": ref}, event_refs=[ref],
                                 event_counts=[len(value[0])], cached_length=value[1],
                                 window_memberships=[self._membership(value[0])])
                else:
                    old.require(type(key) is tuple, "exact memo key tuple")
                    if len(key) == 2:
                        old.require(type(value[0]) is list, "memo retained events")
                        _mapping(value[1], "memo retained named mapping")
                        descriptor = {0: self._id_slot(key[0], value[0]),
                                      1: self._id_slot(key[1], value[1])}
                        self._tuple(key, descriptor)
                        lists = (value[0],)
                        entry["memo_form"] = "region"
                    else:
                        old.require(len(key) == 3 and key[0] == "lists"
                                    and type(key[1]) is tuple and type(value[0]) is tuple
                                    and len(key[1]) == len(value[0]), "memo retained list key form")
                        _mapping(value[1], "memo retained named mapping")
                        old.require(all(type(events) is list for events in value[0]),
                                    "memo retained exact event lists")
                        inner = {i: self._id_slot(k, events)
                                 for i, (k, events) in enumerate(zip(key[1], value[0]))}
                        self._tuple(key[1], inner)
                        self._tuple(key, {2: self._id_slot(key[2], value[1])})
                        lists = value[0]
                        entry["memo_form"] = "lists"
                    entry.update(event_refs=[_ref(index, events) for events in lists],
                                 event_counts=[len(events) for events in lists],
                                 named_mapping_ref=_ref(index, value[1]),
                                 window_memberships=[self._membership(events) for events in lists])
                self._target(value, "value")
                self._target(value[2], "stats")
                self.maps[ident]["entries"].append(entry)
                self.entries.append(entry)
                old.require(len(old.canonical_bytes(self.entries)) <= BINDING_BYTES,
                            "binding witness preliminary byte limit")

    def _membership(self, events):
        return [i for i, current in enumerate(self.window) if current is events]

    def _id_slot(self, key, referent):
        old.require(type(key) is int and key == id(referent), "memo integer identity binding")
        ordinal = _ref(self.index, referent)
        self.bound_ordinals.add(ordinal)
        return ordinal

    def _tuple(self, key, descriptor):
        _ref(self.index, key)
        previous = self.key_tuples.get(id(key))
        old.require(previous is None or previous["object"] is key and previous["slots"] == descriptor,
                    "conflicting aliased key-container bindings")
        self.key_tuples[id(key)] = {"object": key, "slots": descriptor}

    def _target(self, value, label):
        ident = id(value)
        target = self.targets.setdefault(ident, {"object": value, "ordinal": _ref(self.index, value), "labels": []})
        old.require(target["object"] is value, "target identity recycled")
        target["labels"].append(label)

    def witness(self, fingerprint):
        for ordinal in self.bound_ordinals:
            referent = self.index.objects[ordinal]
            old.require(fingerprint.memo.get(id(referent)) == ordinal,
                        "bound referent changed global traversal ordinal")
        rows = []
        for entry in self.entries:
            row = dict(entry)
            for label, ordinal in (("value", entry["value_ref_ordinal"]),
                                   ("stats", entry["stats_ref_ordinal"])):
                obj = self.index.objects[ordinal]
                segment = fingerprint.target_segments.get(id(obj))
                old.require(segment is not None and fingerprint.memo.get(id(obj)) == ordinal,
                            "cache target lacks matching global traversal witness")
                row[label + "_SAME_GLOBAL_token_segment"] = segment
            rows.append(row)
        result = {"encoding": ENCODING, "states": self.states, "entries": rows,
                  "scope": "Verified ID-to-retained-reference bindings; value/stats hashes are SAME GLOBAL first-emitted token segments including reference ordinals, not standalone deep hashes."}
        old.require(len(old.canonical_bytes(result)) <= BINDING_BYTES, "complete binding witness byte limit")
        return result


class ObservedLiveFingerprint(LiveFingerprint):
    """Optional observer subclass, never described as the unmodified old class.

    With bindings=None its global bytes/counters match the unchanged legacy
    class; pure contracts compare those directly. Only known field maps are
    intercepted, with the original exact-dict token sequence preserved.
    """

    def __init__(self, state, classes, numpy_api=None, inspect_arrow=None, *, bindings=None):
        super().__init__(state, classes, numpy_api, inspect_arrow)
        self.bindings = bindings
        self.global_complete = False
        self.token_count = 0
        self.active = []
        self.field_records = []
        self.target_segments = {}
        self.target_active = set()
        self.field_maps = {}
        targets = [("RunState", vars(state)), ("AgentBridge.__dict__", vars(state.agent_bridge)),
                   ("World.public", vars(state.world))]
        for attr, name in (("__pydantic_private__", "World.private"),
                           ("__pydantic_extra__", "World.extra")):
            value = getattr(state.world, attr, None)
            if value is not None:
                targets.append((name, value))
        for name, mapping in targets:
            _mapping(mapping, "exact field trace mapping")
            previous = self.field_maps.get(id(mapping))
            old.require(previous is None or previous[1] is mapping and previous[0] == name,
                        "ambiguous aliased field map")
            self.field_maps[id(mapping)] = (name, mapping)

    def emit(self, tag, data=b""):
        super().emit(tag, data)
        token = tag.encode() + b":" + str(len(data)).encode() + b":" + data + b";"
        self.token_count += 1
        for capture in self.active:
            capture["hash"].update(token)
            capture["tokens"] += 1

    def _begin(self):
        capture = {"hash": hashlib.sha256(), "tokens": 0, "start": self.token_count}
        self.active.append(capture)
        return capture

    def _end(self, capture):
        old.require(self.active.pop() is capture, "token observer stack")
        return {"sha256": capture["hash"].hexdigest(), "tokens": capture["tokens"],
                "global_token_start": capture["start"], "global_token_end": self.token_count}

    def _enter(self, value):
        self.nodes += 1
        old.require(self.nodes <= 5_000_000, "state node cap")
        ident = id(value)
        if ident in self.memo:
            self.emit("reference", str(self.memo[ident]).encode())
            return False
        self.memo[ident] = len(self.objects)
        self.objects.append(value)
        self.emit("type", (type(value).__module__ + "." + type(value).__qualname__).encode())
        return True

    def _bound_int(self, ordinal):
        self.nodes += 1
        old.require(self.nodes <= 5_000_000, "state node cap")
        self.emit("verified-cache-identity-int", str(ordinal).encode())

    def visit(self, value):
        ident = id(value)
        target = (self.bindings.targets.get(ident) if self.bindings is not None else None)
        capture = None
        if target is not None and ident not in self.target_segments and ident not in self.target_active:
            old.require(target["object"] is value, "cache target object changed")
            self.target_active.add(ident)
            capture = self._begin()
        try:
            field_map = self.field_maps.get(ident)
            cache = self.bindings.maps.get(ident) if self.bindings is not None else None
            key_tuple = self.bindings.key_tuples.get(ident) if self.bindings is not None else None
            if field_map is not None or cache is not None:
                old.require(type(value) is dict, "exact intercepted mapping")
                return self._visit_mapping(value, field_map, cache)
            if key_tuple is not None:
                old.require(type(value) is tuple and key_tuple["object"] is value, "retained bound key tuple")
                if self._enter(value):
                    try:
                        for i, item in enumerate(value):
                            if i in key_tuple["slots"]:
                                self._bound_int(key_tuple["slots"][i])
                            else:
                                self.visit(item)
                    finally:
                        self.emit("end")
                return None
            return super().visit(value)
        finally:
            if capture is not None:
                self.target_segments[ident] = self._end(capture)
                self.target_active.remove(ident)

    def _visit_mapping(self, value, field_map, cache):
        if not self._enter(value):
            return
        try:
            if cache is not None:
                old.require(cache["object"] is value and len(value) == len(cache["entries"]),
                            "cache changed after binding validation")
            for position, (key, item) in enumerate(value.items()):
                if cache is not None:
                    expected = cache["entries"][position]
                    old.require(item is self.bindings.index.objects[expected["value_ref_ordinal"]],
                                "retained cache value changed after validation")
                    if expected["key_ref_ordinal"] is not None:
                        old.require(key is self.bindings.index.objects[expected["key_ref_ordinal"]],
                                    "retained memo key changed after validation")
                capture, record = None, None
                if field_map is not None:
                    old.require(type(key) is str, "field trace key must be a string")
                    path = field_map[0] + "." + key
                    old.require(len(path.encode()) <= 512 and len(self.field_records) < FIELD_RECORDS,
                                "field trace record/path bound")
                    record = {"path": path, "field_order": position,
                              "mapping_reference_ordinal": self.memo[id(value)]}
                    self.field_records.append(record)
                    capture = self._begin()
                try:
                    if cache is not None and cache["name"] == "_window_stats_cache":
                        entry = cache["entries"][position]
                        old.require(key == entry["raw_key"] and type(key) is int,
                                    "cache dictionary changed after validation")
                        self._bound_int(entry["key_binding"]["scalar_ref"])
                    else:
                        self.visit(key)
                    if value is self.marker_mapping and key == "_war_roster_sim":
                        self.emit("checkpoint-rebound", b"agent_bridge._sim")
                    else:
                        self.visit(item)
                finally:
                    if capture is not None:
                        record.update(self._end(capture))
        finally:
            self.emit("end")

    def result(self):
        result = super().result()
        self.global_complete = True
        return result


def merge_field_segments(raw_view, bound_view):
    left, right = raw_view.field_records, bound_view.field_records
    old.require(len(left) == len(right) <= FIELD_RECORDS, "complete paired field record count")
    rows = []
    for a, b in zip(left, right):
        keys = ("path", "field_order", "mapping_reference_ordinal")
        old.require(all(a[k] == b[k] for k in keys), "same global field ownership/order")
        rows.append({**{k: a[k] for k in keys},
                     "old_raw": {k: a[k] for k in a if k not in keys},
                     "validated_bound": {k: b[k] for k in b if k not in keys}})
    old.require(len(old.canonical_bytes(rows)) <= FIELD_BYTES, "complete field diagnostic byte cap")
    return rows


def first_field_difference(left, right):
    """Compare saved SAME GLOBAL bound segments; never normalize/re-root them."""
    for position, (a, b) in enumerate(zip(left, right)):
        if a["path"] != b["path"] or a["field_order"] != b["field_order"]:
            return {"kind": "FIELD_OWNERSHIP_OR_ORDER_DIFFERS", "index": position,
                    "left_path": a["path"], "right_path": b["path"],
                    "left_order": a["field_order"], "right_order": b["field_order"]}
        if a["validated_bound"] != b["validated_bound"]:
            return {"path": a["path"], "left": a["validated_bound"], "right": b["validated_bound"],
                    "scope": "First recorded unequal SAME GLOBAL token segment; not a deep value/path cause."}
    if len(left) != len(right):
        return {"kind": "FIELD_RECORD_COUNT_DIFFERS", "left": len(left), "right": len(right)}
    return None


def capture_terminal(save, checkpoint, rc, classes, np, *, expected_rng,
                     bridge_class, inspect_arrow=None, progress=None,
                     cpu=time.process_time_ns, wall=time.perf_counter_ns):
    """One existing save, with old/bound proofs and bounded diagnostics outside physics.

    This uses observer subclasses of the unchanged legacy encoder, not a claim
    that a modified class is unmodified. Partial failures keep completed old
    hashes and subphase endpoints in the caller's summary carrier.
    """
    progress = {} if progress is None else progress
    progress.update(method=ENCODING, subphases={}, save_wrapper_calls=0,
                    checkpoint_write_calls=0, checkpoint_write_completed=False,
                    proof_load_calls=0, extra_physics_runs=0)
    original = rc.write_checkpoint
    before_rng = old.capture_rng(np)
    old.require(old.same_rng(expected_rng, before_rng), "measured-end to proof RNG changed")
    progress["measured_end_to_proof_RNG_invariance"] = True
    captured = {}

    def phase(name, action):
        raw = {"CPU_start_ns": p.sample_ns(cpu), "wall_start_ns": p.sample_ns(wall),
               "CPU_end_ns": None, "wall_end_ns": None}
        record = {"status": "STARTED", "clock": None}
        progress["subphases"][name] = record
        try:
            value = action()
            record["status"] = "COMPLETE"
            return value
        except BaseException as exc:
            record.update(status="FAILED", error={"type": type(exc).__name__, "message": str(exc)[:512]})
            raise
        finally:
            raw.update(CPU_end_ns=p.sample_ns(cpu), wall_end_ns=p.sample_ns(wall))
            # Additional cost observations preserve zero/invalid samples. They
            # are not a new performance claim or a relaxation of run_clock.
            record["clock"] = p.interval(raw)

    def raw_view(state, label):
        view = ObservedLiveFingerprint(state, classes, np, inspect_arrow)
        result = view.result()
        captured[label] = (view, result)
        progress[label] = result
        return view, result

    def bound_view(state, raw_label, label):
        raw_fp, raw_result = captured[raw_label]
        bindings = CacheBindings(raw_fp, bridge_class)
        view = ObservedLiveFingerprint(state, classes, np, inspect_arrow, bindings=bindings)
        result = view.result()
        old.require({k: v for k, v in result.items() if k != "sha256"}
                    == {k: v for k, v in raw_result.items() if k != "sha256"},
                    "old/bound node/reference/coverage counters changed")
        witness = bindings.witness(view)
        fields = merge_field_segments(raw_fp, view)
        captured[label] = (view, result, witness, fields)
        progress[label] = result
        progress[label + "_witness_sha256"] = hashlib.sha256(old.canonical_bytes(witness)).hexdigest()
        return result

    def write(path, state, *args, **kwargs):
        progress["save_wrapper_calls"] += 1
        old.require(progress["save_wrapper_calls"] == 1, "terminal checkpoint called more than once")
        # The diagnostic carrier receives precisely the stock writer marker;
        # no live World value, cache or key is rewritten.
        state.markers = rc._markers(state)
        old.marker_view(state, classes[0])
        phase("old_live_before", lambda: raw_view(state, "old_before"))
        phase("bound_live_before", lambda: bound_view(state, "old_before", "bound_before"))

        def real_write():
            progress["checkpoint_write_calls"] += 1
            value = original(path, state, *args, **kwargs)
            progress["checkpoint_write_completed"] = True
            return value

        result = phase("checkpoint_write", real_write)
        phase("old_live_after", lambda: raw_view(state, "old_after"))
        phase("bound_live_after", lambda: bound_view(state, "old_after", "bound_after"))
        old.require(captured["old_before"][1] == captured["old_after"][1],
                    "checkpoint write mutated old raw live graph")
        old.require(captured["bound_before"][1] == captured["bound_after"][1]
                    and progress["bound_before_witness_sha256"] == progress["bound_after_witness_sha256"],
                    "checkpoint write mutated validated bound graph/bindings")
        progress["own_old_raw_write_invariance"] = True
        progress["own_bound_write_invariance"] = True
        return result

    try:
        rc.write_checkpoint = write
        try:
            path = save(checkpoint)
        finally:
            rc.write_checkpoint = original
        old.require(progress["save_wrapper_calls"] == progress["checkpoint_write_calls"] == 1
                    and progress["checkpoint_write_completed"], "one real terminal save required")

        def load():
            progress["proof_load_calls"] += 1
            return rc.read_checkpoint(path, allow_mismatch=False)

        loaded = phase("checkpoint_load", load)
        old.require(loaded.exact, "own checkpoint not exact")
        decoded = phase("decoded_fingerprint", lambda: old.StateFingerprint(loaded.state, classes, np).result())
        sim = loaded.state.agent_bridge._sim
        native_before = hashlib.sha256(bytes(sim.checkpoint_state())).hexdigest()
        population = old.native_region_counts(sim, len(loaded.state.world.regions))
        old.require(native_before == hashlib.sha256(bytes(sim.checkpoint_state())).hexdigest(),
                    "proof population getter changed persistent native state")
        old.require(old.same_rng(before_rng, old.capture_rng(np)), "proof changed global RNG")
        progress["global_RNG_read_invariance"] = True
        after = captured["bound_after"]
        return {
            "encoding": ENCODING, "old_raw_live": captured["old_after"][1],
            "live": after[1], "decoded": decoded,
            "cache_identity_witness": after[2], "SAME_GLOBAL_field_token_segments": after[3],
            "field_and_cache_segment_scope": SEGMENT_SCOPE,
            "subphase_progress": progress,
            "own_live_write_invariance": True, "own_old_raw_write_invariance": True,
            "global_RNG_read_invariance": True, "measured_end_to_proof_RNG_invariance": True,
            "checkpoint_header": loaded.header, "actual_final_native": population,
            "proof_loads": progress["proof_load_calls"], "save_calls": progress["checkpoint_write_calls"],
            "extra_physics_runs": 0,
            "native_objects_loaded": sum(s["name"].startswith("native.") for s in loaded.header["sections"]),
            "live_equals_decoded_claim": False,
            "coverage": {
                "decoded_persistent_graph_native_and_memory_identity": True,
                "live_python_private_extras_slots_and_container_aliases": True,
                "validated_cache_identity_key_positions_only": ENCODING,
                "old_raw_live_retained_as_diagnostic_not_cross_source_gate": True,
                "readonly_Arrow_interface_schema_offsets_nulls_primitive_buffer_bits": True,
                "external_writable_owner_Arrow_aliases": "UNOBSERVED",
                "internal_C_Arrow_storage_aliases": "UNOBSERVED",
                "native_transient_caches": "not native checkpoint payload; no byte-identity claim",
                "unsupported_types": "REFUSE",
            },
        }
    except BaseException as exc:
        progress["failure"] = {"type": type(exc).__name__, "message": str(exc)[:512]}
        raise
    finally:
        rc.write_checkpoint = original
        try:
            progress["final_RNG_read_invariance"] = old.same_rng(before_rng, old.capture_rng(np))
        except BaseException as exc:
            progress["final_RNG_observation_error"] = {"type": type(exc).__name__, "message": str(exc)[:512]}
            if "failure" not in progress:
                raise
        if "failure" not in progress:
            old.require(progress.get("final_RNG_read_invariance") is True,
                        "final proof RNG observation differs")
