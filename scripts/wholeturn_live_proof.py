"""Untimed live and decoded proof; no simulator proxies or runtime imports.

The frozen090 proof covers the decoded graph. This layer separately captures
the terminal live RunState because checkpoint reducers intentionally omit live
HistoryIndex, sidecar, historian/language and bridge caches. Exact immutable
Arrow batch values have a closed logical-buffer adapter. Internal C Arrow
storage aliases are explicitly unobserved, never presented as generic alias
attestation. Root's source-owned decision must review this coverage boundary.
"""
from __future__ import annotations

from types import MethodDescriptorType
import hashlib

import wholeturn_state_proof as old

MAX_ARROW_BYTES = 512*1024**2


def trusted_raw_batch(value, pa, arro3_type):
    cls = type(value)
    if cls is pa.RecordBatch or cls is arro3_type:
        return True
    if type(cls) is not type:
        return False
    fields = type.__getattribute__(cls, "__dict__")
    if (type.__getattribute__(cls, "__module__") != "arro3.core._core"
            or type.__getattribute__(cls, "__name__") != "RecordBatch"
            or type.__getattribute__(cls, "__base__") is not object):
        return False
    return all(type(fields.get(name)) is MethodDescriptorType
               and fields[name].__objclass__ is cls
               for name in ("__arrow_c_array__", "column"))


def arrow_adapter(pa, arro3_type):
    """Build after admission; exact primitive schema/buffer contents, no coercion.

    This is the pinned trusted Arrow contract, not arbitrary C attestation.
    No external writable Arrow buffers, nested arrays or dictionary encoding
    are accepted. Offsets, null counts, field/schema metadata and float bits
    remain visible; no value to_pylist()/float normalization is used.
    """
    def inspect(value):
        if not trusted_raw_batch(value, pa, arro3_type):
            return None
        batch = pa.record_batch(value)
        schema = batch.schema.serialize().to_pybytes()
        used = len(schema)
        columns = []
        for array in batch.columns:
            dtype = array.type
            old.require(pa.types.is_integer(dtype) or pa.types.is_floating(dtype)
                        or pa.types.is_boolean(dtype), "live Arrow type unsupported")
            buffers = []
            for buf in array.buffers():
                if buf is None:
                    buffers.append(None)
                    continue
                old.require(type(buf.is_mutable) is bool and not buf.is_mutable,
                            "live Arrow mutable buffer unsupported")
                used += buf.size
                old.require(used <= MAX_ARROW_BYTES, "live Arrow buffer bound")
                buffers.append(bytes(buf))
            columns.append({"type": str(dtype), "length": len(array),
                            "offset": array.offset, "null_count": array.null_count,
                            "buffers": buffers})
        return {"source_class": type(value).__module__+"."+type(value).__qualname__,
                "schema": schema, "rows": batch.num_rows, "columns": columns}
    return inspect


class LiveFingerprint(old.StateFingerprint):
    def __init__(self, state, classes, numpy_api, inspect_arrow=None):
        super().__init__(state, classes, numpy_api)
        self.inspect_arrow = inspect_arrow
        self.arrow_batches = 0

    def visit(self, value):
        arrow = self.inspect_arrow(value) if self.inspect_arrow is not None else None
        if arrow is None:
            return super().visit(value)
        self.nodes += 1
        old.require(self.nodes <= 5_000_000, "state node cap")
        ident = id(value)
        if ident in self.memo:
            return self.emit("reference", str(self.memo[ident]).encode())
        self.memo[ident] = len(self.objects)
        self.objects.append(value)
        self.arrow_batches += 1
        self.emit("immutable-arrow-logical-value")
        self.visit(arrow)
        self.emit("end")

    def result(self):
        result = super().result()
        result["live_Arrow_batches_observed"] = self.arrow_batches
        return result


def capture_terminal(save, checkpoint, rc, classes, np, *, inspect_arrow=None):
    """Intercept one existing terminal save, after run clocks have stopped.

    The fresh diagnostic carrier's markers are set exactly as the stock writer
    sets them. No live World field is rewritten. Only this save call is wrapped;
    the real writer runs once and its module binding is restored on every exit.
    Live-before/live-after equality is separate from decoded A/B equality.
    """
    original = rc.write_checkpoint
    before_rng = old.capture_rng(np)
    captured = {}
    calls = 0

    def write(path, state, *args, **kwargs):
        nonlocal calls
        calls += 1
        old.require(calls == 1, "terminal checkpoint called more than once")
        state.markers = rc._markers(state)
        old.marker_view(state, classes[0])
        captured["before"] = LiveFingerprint(state, classes, np, inspect_arrow).result()
        result = original(path, state, *args, **kwargs)
        captured["after"] = LiveFingerprint(state, classes, np, inspect_arrow).result()
        old.require(captured["before"] == captured["after"], "checkpoint write mutated live graph")
        return result

    try:
        rc.write_checkpoint = write
        path = save(checkpoint)
    finally:
        rc.write_checkpoint = original
    old.require(calls == 1 and set(captured) == {"before", "after"}, "one terminal live capture required")
    loaded = rc.read_checkpoint(path, allow_mismatch=False)
    old.require(loaded.exact, "own checkpoint not exact")
    decoded = old.StateFingerprint(loaded.state, classes, np).result()
    sim = loaded.state.agent_bridge._sim
    native_before = hashlib.sha256(bytes(sim.checkpoint_state())).hexdigest()
    population = old.native_region_counts(sim, len(loaded.state.world.regions))
    old.require(native_before == hashlib.sha256(bytes(sim.checkpoint_state())).hexdigest(),
                "proof population getter changed persistent native state")
    old.require(old.same_rng(before_rng, old.capture_rng(np)), "proof changed global RNG")
    return {
        "live": captured["after"], "decoded": decoded,
        "own_live_write_invariance": True, "global_RNG_read_invariance": True,
        "checkpoint_header": loaded.header, "actual_final_native": population,
        "proof_loads": 1, "save_calls": calls, "extra_physics_runs": 0,
        "native_objects_loaded": sum(s["name"].startswith("native.")
                                     for s in loaded.header["sections"]),
        "live_equals_decoded_claim": False,
        "coverage": {
            "live_python_private_extras_slots_and_container_aliases": True,
            "decoded_persistent_graph_native_and_memory_identity": True,
            "immutable_Arrow_schema_offsets_nulls_primitive_buffer_bits": True,
            "internal_C_Arrow_storage_aliases": "UNOBSERVED",
            "native_transient_caches": "not native checkpoint payload; no byte-identity claim",
            "unsupported_types": "REFUSE",
        },
    }
