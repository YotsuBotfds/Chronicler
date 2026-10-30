"""A01 slice 1: exact consumers, lazy failures, ownership and extraction sharing."""
from __future__ import annotations

from collections import Counter
from dataclasses import FrozenInstanceError
import gc
import random
import weakref

import pyarrow as pa
import pytest

from chronicler.culture import (
    apply_value_drift, compute_civ_cultural_profile, tick_cultural_assimilation,
)
from chronicler.economy import EconomyResult
from chronicler.great_persons import check_pilgrimages
from chronicler.models import AgentEventRecord
from chronicler.religion import (
    MAX_FAITHS, compute_majority_belief, compute_civ_majority_faith,
    compute_conversion_signals, compute_persecution, detect_schisms,
)
from chronicler.turn_artifacts import (
    AgentRows, Phase10Inputs, Stamp, TurnArtifacts, TurnObservation, TurnResult,
)

# Reuse admitted unit fixtures; no generated scientific study worlds.
from test_culture import assimilation_world, drift_world
from test_pilgrimages import _make_gp, _make_snapshot, _make_temple
from test_schisms import _make_belief, _make_civ, _make_region


class CountingBatch:
    """Instrument real Arrow decodes without patching native Arrow classes."""

    def __init__(self, batch, failures=None):
        self.batch = batch
        self.schema = batch.schema
        self.num_rows = batch.num_rows
        self.calls = Counter()
        self.failures = dict(failures or {})
        self.accesses = Counter()

    def column(self, name):
        self.accesses[name] += 1
        column = self.batch.column(name)
        owner = self

        class Column:
            def to_pylist(self):
                owner.calls[name] += 1
                if owner.failures.get(name, 0):
                    owner.failures[name] -= 1
                    raise RuntimeError(f"injected decode failure: {name}")
                return column.to_pylist()

        return Column()


def rows_for(batch, turn=0):
    return AgentRows(Stamp(turn, "phase10_entry"), batch)


def consumer_batch():
    # Tie in R0, insertion order starts with faith 1; sentinels and zero kept.
    return pa.record_batch({
        "id": pa.array([4, 1, 3, 2, 7, 6], type=pa.uint32()),
        "region": pa.array([0, 0, 0, 0, 1, 1], type=pa.uint16()),
        "civ_affinity": pa.array([0, 0, 0, 0, 1, 1], type=pa.uint16()),
        "occupation": pa.array([4, 4, 0, 0, 4, 0], type=pa.uint8()),
        "belief": pa.array([1, 0, 1, 0, 255, 0], type=pa.uint8()),
        "cultural_value_0": pa.array([1, 0, 1, 0, 255, 6], type=pa.uint8()),
        "cultural_value_1": pa.array([255] * 6, type=pa.uint8()),
        "cultural_value_2": pa.array([255] * 6, type=pa.uint8()),
        "loyalty_trait": pa.array([0.8] * 6, type=pa.float32()),
        "loyalty": pa.array([0.9] * 6, type=pa.float32()),
        "x": pa.array([0.0] * 6, type=pa.float32()),
        "y": pa.array([0.0] * 6, type=pa.float32()),
    })


def religion_inputs():
    regions = [_make_region("r0"), _make_region("r1")]
    civ = _make_civ(region_names=["r0", "r1"], faith_id=0)
    beliefs = [_make_belief(0, doctrines=[0, 0, 1, 0, 0]), _make_belief(1)]
    return regions, [civ], beliefs


def test_view_is_lazy_read_only_and_preserves_arrow_values():
    batch = pa.record_batch({
        "id": pa.array([0, None, 2**32 - 1], type=pa.uint32()),
        "x": pa.array([0.0, None, 0.1], type=pa.float32()),
        "settlement_id": pa.array([0, 65535, None], type=pa.uint16()),
    })
    probe = CountingBatch(batch)
    rows = rows_for(probe)
    assert rows.batch is probe and not probe.calls
    assert rows.has("settlement_id") and not rows.has("region")
    assert not probe.calls
    ids = rows.ints("id")
    assert ids == tuple(batch.column("id").to_pylist())
    assert ids is rows.ints("id")
    assert rows.floats("x") == tuple(batch.column("x").to_pylist())
    assert rows.ints("settlement_id") == (0, 65535, None)
    assert probe.calls == {"id": 1, "x": 1, "settlement_id": 1}
    with pytest.raises(TypeError):
        ids[0] = 1
    with pytest.raises(FrozenInstanceError):
        rows.batch = batch
    with pytest.raises(FrozenInstanceError):
        rows.stamp = Stamp(1, "phase10_entry")
    assert not hasattr(rows, "__dict__")


def test_failed_and_missing_decodes_are_not_cached():
    probe = CountingBatch(consumer_batch(), {"belief": 1})
    rows = rows_for(probe)
    with pytest.raises(RuntimeError):
        rows.ints("belief")
    assert rows.ints("belief") == (1, 0, 1, 0, 255, 0)
    assert rows.ints("belief") is rows.ints("belief")
    assert probe.calls["belief"] == 2
    for _ in range(2):
        with pytest.raises(KeyError):
            rows.ints("settlement_id")
    assert probe.accesses["settlement_id"] == 2


def test_handoff_copies_names_but_borrows_economy_and_death_records():
    batch = consumer_batch()
    rows = rows_for(batch, 7)
    names = {4: "Named Prophet"}
    economy = EconomyResult()
    death = AgentEventRecord(7, 4, "death", 0, 0, 0, 4, belief=1)
    deaths = [death]
    inputs = Phase10Inputs(7, rows, names, economy, deaths)
    names[4] = "Changed"
    deaths.clear()
    assert dict(inputs.named_agents) == {4: "Named Prophet"}
    with pytest.raises(TypeError):
        inputs.named_agents[4] = "Changed"
    assert inputs.economy is economy and inputs.deaths == (death,)
    assert inputs.deaths[0] is death
    economy.treasury_tax[0] = 1.0
    assert inputs.economy.treasury_tax[0] == 1.0
    with pytest.raises(FrozenInstanceError):
        inputs.economy = None
    owner, next_owner = TurnArtifacts(7), TurnArtifacts(8)
    owner.conquered_civ_ids.add(0)
    assert next_owner.conquered_civ_ids == set()
    result = TurnResult("text", TurnObservation(7, 8, rows))
    assert result.observation.phase10_agents is rows
    assert result.observation.completed_turn == 8
    assert Phase10Inputs(7, None, None, None, ()).named_agents is None
    assert dict(Phase10Inputs(7, None, {}, None, ()).named_agents) == {}


def test_stamp_and_explicit_source_turn_checks():
    batch = consumer_batch()
    rows = rows_for(batch, 7)
    with pytest.raises(ValueError):
        Stamp(7, "latest")
    with pytest.raises(ValueError):
        Phase10Inputs(8, rows, None, None, ())
    with pytest.raises(ValueError):
        TurnObservation(8, 9, rows)
    with pytest.raises(ValueError):
        TurnObservation(7, 7, rows)
    with pytest.raises(ValueError):
        check_pilgrimages([], [], batch, 8, agent_rows=rows)
    with pytest.raises(ValueError):
        compute_persecution([], [], [], batch, 8, set(), agent_rows=rows)
    with pytest.raises(ValueError):
        detect_schisms([], [], [], batch, 8, agent_rows=rows)


@pytest.mark.parametrize("consumer", [compute_civ_cultural_profile, compute_majority_belief, compute_civ_majority_faith])
def test_reduction_parity_and_batch_identity(consumer):
    batch = consumer_batch()
    before = batch.to_pydict()
    assert consumer(batch, agent_rows=rows_for(batch)) == consumer(batch)
    assert batch.to_pydict() == before
    equivalent_batch = pa.record_batch(batch.to_pydict(), schema=batch.schema)
    assert equivalent_batch.equals(batch) and equivalent_batch is not batch
    with pytest.raises(ValueError):
        consumer(equivalent_batch, agent_rows=rows_for(batch))
    with pytest.raises(ValueError):
        consumer(None, agent_rows=rows_for(batch))
    assert consumer(None) == {}
    empty = CountingBatch(batch.slice(0, 0))
    assert consumer(empty, agent_rows=rows_for(empty)) == {}
    assert not empty.calls


def test_exact_ties_and_dictionary_order():
    batch = consumer_batch()
    rows = rows_for(batch)
    assert list(compute_majority_belief(batch, agent_rows=rows).items()) == [(0, 0), (1, 0)]
    assert list(compute_civ_majority_faith(batch, agent_rows=rows).items()) == [(0, (0, 0.5)), (1, (0, 1.0))]
    profile = compute_civ_cultural_profile(batch, agent_rows=rows)
    assert list(profile[0].items()) == [(1, 2), (0, 2)]
    assert profile[1] == Counter()


def test_value_drift_and_assimilation_parity(drift_world, assimilation_world):
    batch = consumer_batch()
    for original, consumer in [(drift_world, apply_value_drift), (assimilation_world, tick_cultural_assimilation)]:
        original.regions[0].foreign_control_turns = 9
        cached = original.model_copy(deep=True)
        consumer(original, agent_snapshot=batch)
        consumer(cached, agent_snapshot=batch, agent_rows=rows_for(batch))
        assert cached.model_dump(mode="json") == original.model_dump(mode="json")
        assert cached.regions[0].__pydantic_private__ == original.regions[0].__pydantic_private__


def test_assimilation_shares_columns_across_regions_and_respects_gate(drift_world):
    for civ in drift_world.civilizations:
        civ.values = ["Order"]
    for region in drift_world.regions:
        region.cultural_identity = "Other"
        region.foreign_control_turns = 4
    batch = consumer_batch()
    legacy, cached = CountingBatch(batch), CountingBatch(batch)
    world = drift_world.model_copy(deep=True)
    tick_cultural_assimilation(drift_world, agent_snapshot=legacy)
    tick_cultural_assimilation(world, agent_snapshot=cached, agent_rows=rows_for(cached))
    assert drift_world.model_dump(mode="json") == world.model_dump(mode="json")
    assert legacy.calls == {"region": 2, "cultural_value_0": 2, "cultural_value_1": 2, "cultural_value_2": 2}
    assert cached.calls == {name: 1 for name in legacy.calls}
    missing = CountingBatch(batch.select(["id"]))
    world = world.model_copy(deep=True)
    for region in world.regions:
        region.cultural_identity = "Other"
        region.foreign_control_turns = 0
    tick_cultural_assimilation(world, agent_snapshot=missing, agent_rows=rows_for(missing))
    assert not missing.accesses
    world.regions[0].foreign_control_turns = 4
    with pytest.raises(KeyError):
        tick_cultural_assimilation(world, agent_snapshot=missing, agent_rows=rows_for(missing))


def test_religion_mutations_and_ordered_events_match():
    batch = consumer_batch()
    outputs = []
    for use_rows in [False, True]:
        regions, civs, beliefs = religion_inputs()
        kw = {"agent_rows": rows_for(batch, 7)} if use_rows else {}
        majority = compute_majority_belief(batch, **kw)
        conversions = compute_conversion_signals(regions, majority, beliefs, batch, {4: "Prophet"}, **kw)
        seen = set()
        persecution = compute_persecution(regions, civs, beliefs, batch, 7, seen, **kw)
        schisms = detect_schisms(regions, civs, beliefs, batch, 7, **kw)
        outputs.append((conversions, [e.model_dump() for e in persecution + schisms],
                        [r.model_dump() for r in regions], [b.model_dump() for b in beliefs], seen))
    assert outputs[0] == outputs[1]
    assert [e["event_type"] for e in outputs[1][1]] == ["Persecution", "Mass Migration", "Schism"]


def test_schism_capacity_gate_reads_no_columns():
    batch = CountingBatch(consumer_batch().select(["id"]))
    assert detect_schisms([], [], [None] * MAX_FAITHS, batch, 0, agent_rows=rows_for(batch)) == []
    assert not batch.accesses


@pytest.mark.parametrize("belief_available", [True, False])
def test_pilgrimage_parity_including_optional_belief(belief_available):
    batch = _make_snapshot(1, 4, 0.8, 0.9, 0)
    if not belief_available:
        batch = batch.select([n for n in batch.schema.names if n != "belief"])
    results = []
    for use_rows in [False, True]:
        gp = _make_gp()
        temples = [("Shrine", _make_temple(0, 20))]
        kw = {"agent_rows": rows_for(batch, 7)} if use_rows else {}
        events = check_pilgrimages([gp], temples, batch, 7, **kw)
        results.append(([e.model_dump() for e in events], gp.model_dump()))
    assert results[0] == results[1]
    assert bool(results[1][0]) == belief_available


def test_pilgrimage_failed_belief_does_not_poison_other_consumers():
    batch = CountingBatch(_make_snapshot(1, 4, 0.8, 0.9, 0), {"belief": 1})
    rows = rows_for(batch, 7)
    assert check_pilgrimages([_make_gp()], [("Shrine", _make_temple(0, 20))], batch, 7, agent_rows=rows) == []
    assert compute_majority_belief(batch, agent_rows=rows) == {0: 0}
    assert batch.calls["belief"] == 2


def test_shared_phase10_decodes_and_no_added_rng():
    batch = CountingBatch(consumer_batch())
    rows = rows_for(batch)
    before = random.getstate()
    compute_civ_cultural_profile(batch, agent_rows=rows)
    compute_majority_belief(batch, agent_rows=rows)
    compute_civ_majority_faith(batch, agent_rows=rows)
    regions, civs, beliefs = religion_inputs()
    compute_conversion_signals(regions, {0: 0}, beliefs, batch, {4: "Prophet"}, agent_rows=rows)
    compute_persecution(regions, civs, beliefs, batch, 0, set(), agent_rows=rows)
    detect_schisms(regions, civs, beliefs, batch, 0, agent_rows=rows)
    check_pilgrimages([_make_gp(agent_id=4)], [], batch, 0, agent_rows=rows)
    assert random.getstate() == before
    assert len(batch.calls) == 10 and all(n == 1 for n in batch.calls.values())
    assert not batch.calls["x"] and not batch.calls["y"]


def test_views_are_fresh_per_batch_and_release_without_global_retention():
    refs = []
    for turn in range(30):
        batch = consumer_batch()
        rows = rows_for(batch, turn)
        rows.ints("belief")
        refs.append(weakref.ref(rows))
    del rows
    gc.collect()
    assert all(ref() is None for ref in refs)
    first = consumer_batch()
    second = first.set_column(first.schema.get_field_index("belief"), "belief", pa.array([0] * 6, type=pa.uint8()))
    assert rows_for(first, 7).ints("belief") != rows_for(second, 8).ints("belief")


@pytest.mark.parametrize("consumer", [compute_majority_belief, compute_civ_majority_faith, compute_civ_cultural_profile])
def test_required_missing_column_failure_matches_legacy(consumer):
    batch = consumer_batch().select(["id"])
    with pytest.raises(KeyError) as legacy:
        consumer(batch)
    with pytest.raises(KeyError) as cached:
        consumer(batch, agent_rows=rows_for(batch))
    assert cached.value.args == legacy.value.args


def test_null_cultural_value_retains_original_failure():
    batch = consumer_batch()
    batch = batch.set_column(batch.schema.get_field_index("cultural_value_0"),
                             "cultural_value_0", pa.array([None] * 6, type=pa.uint8()))
    with pytest.raises(TypeError) as legacy:
        compute_civ_cultural_profile(batch)
    with pytest.raises(TypeError) as cached:
        compute_civ_cultural_profile(batch, agent_rows=rows_for(batch))
    assert cached.value.args == legacy.value.args


@pytest.mark.parametrize("consumer", ["drift", "assimilation", "conversion", "persecution", "schism", "pilgrimage"])
def test_mutating_consumers_reject_batch_disagreement(consumer, drift_world):
    batch = consumer_batch()
    rows = rows_for(consumer_batch())
    regions, civs, beliefs = religion_inputs()
    calls = {
        "drift": lambda: apply_value_drift(drift_world, batch, agent_rows=rows),
        "assimilation": lambda: tick_cultural_assimilation(drift_world, None, batch, agent_rows=rows),
        "conversion": lambda: compute_conversion_signals(regions, {}, beliefs, batch, agent_rows=rows),
        "persecution": lambda: compute_persecution(regions, civs, beliefs, batch, 0, set(), agent_rows=rows),
        "schism": lambda: detect_schisms(regions, civs, beliefs, batch, 0, agent_rows=rows),
        "pilgrimage": lambda: check_pilgrimages([], [], batch, 0, agent_rows=rows),
    }
    before = drift_world.model_dump()
    with pytest.raises(ValueError):
        calls[consumer]()
    assert drift_world.model_dump() == before


def test_cached_columns_do_not_freeze_live_religion_inputs():
    batch = consumer_batch()
    rows = rows_for(batch)
    regions, _, beliefs = religion_inputs()
    first = compute_conversion_signals(regions, {0: 0}, beliefs, batch, agent_rows=rows)
    regions[0].martyrdom_boost = 0.1
    second = compute_conversion_signals(regions, {0: 0}, beliefs, batch, agent_rows=rows)
    raw = compute_conversion_signals(regions, {0: 0}, beliefs, batch)
    assert first != second == raw
    assert rows.ints("belief") == (1, 0, 1, 0, 255, 0)


@pytest.mark.parametrize("available", [False, True])
def test_missing_and_empty_batches_keep_return_and_zero_believer_behavior(available):
    batch = consumer_batch().slice(0, 0) if available else None
    kw = {"agent_rows": rows_for(batch, 7)} if available else {}
    regions, civs, beliefs = religion_inputs()
    regions[0].persecution_intensity = 0.5
    assert compute_persecution(regions, civs, beliefs, batch, 7, set(), **kw) == []
    assert regions[0].persecution_intensity == 0.0
    assert detect_schisms(regions, civs, beliefs, batch, 7, **kw) == []
    gp = _make_gp()
    gp.pilgrimage_destination = "Shrine"
    gp.pilgrimage_return_turn = 7
    events = check_pilgrimages([gp], [], batch, 7, **kw)
    assert [e.event_type for e in events] == ["pilgrimage_return"]
    assert gp.pilgrimage_return_turn is None


# Needs-sidecar decode reuse: real Arrow payloads, no native construction here.
def _needs_real_batch(kind="pyarrow", *, count=4, mutable=False, diagnostic=False):
    import struct

    specs = [("agent_id", "I", pa.uint32()),
             *[(name, "f", pa.float32()) for name in
               ("safety", "autonomy", "social", "spiritual", "material", "purpose")],
             ("civ_affinity", "B", pa.uint8()), ("region", "H", pa.uint16()),
             ("occupation", "B", pa.uint8()),
             *[(name, "f", pa.float32()) for name in
               ("satisfaction", "boldness", "ambition", "loyalty_trait")]]
    arrays, fields, storage, data = [], [], {}, {}
    for name, code, dtype in specs:
        if name == "agent_id": values = [101, 102, 103, 2**32 - 1]
        elif name == "civ_affinity": values = [0, 255, 1, 0]
        elif name == "region": values = [0, 0, 0, 0]
        elif name == "occupation": values = [0, 1, 3, 4]
        else: values = [0.125, 0.25, 0.5, 0.75]
        raw = struct.pack("<" + code * count, *values[:count])
        if diagnostic and name == "safety" and count:
            # Both signed zeros and two signed quiet-NaN payloads are diagnostic.
            raw = struct.pack("<4I", 0, 0x80000000, 0x7fc00001, 0xffc01234)
        storage[name] = bytearray(raw) if mutable else raw
        arrays.append(pa.Array.from_buffers(dtype, count, [None, pa.py_buffer(storage[name])]))
        fields.append(pa.field(name, dtype, nullable=False))
        data[name] = list(struct.unpack("<" + code * count, raw))
    batch = pa.RecordBatch.from_arrays(arrays, schema=pa.schema(fields))
    if not mutable:
        assert all(a.buffers()[0] is None and (a.buffers()[1] is None or not a.buffers()[1].is_mutable) for a in arrays)
    if kind == "arro3":
        from arro3.core import RecordBatch
        batch = RecordBatch.from_arrow(batch)
    return batch, storage, data


def _needs_value_bits(value):
    import struct
    if type(value) is float:
        return ("float", struct.pack("!d", value))
    if type(value) is dict:
        return [(key, _needs_value_bits(item)) for key, item in value.items()]
    if type(value) in (list, tuple):
        return [_needs_value_bits(item) for item in value]
    return (type(value).__name__, value)


class _NeedsForeignSim:
    def __init__(self, needs):
        self.needs = needs
        self.getter_reads = self.getter_calls = 0

    @property
    def get_all_needs(self):
        self.getter_reads += 1
        def read():
            self.getter_calls += 1
            return self.needs
        return read

    def get_all_relationships(self):
        return pa.record_batch({"agent_id": pa.array([], type=pa.uint32())})

    def get_all_memories(self):
        return pa.record_batch({"agent_id": pa.array([], type=pa.uint32())})

    def get_snapshot(self):
        return pa.record_batch({
            "id": pa.array([101, 102, 103, 104], type=pa.uint32()),
            "civ_affinity": pa.array([0] * 4, type=pa.uint8()),
            "region": pa.array([0] * 4, type=pa.uint16()),
            "occupation": pa.array([0, 1, 3, 4], type=pa.uint8()),
            "satisfaction": pa.array([0.25, 0.5, 0.75, 1.0], type=pa.float32()),
        })


def _needs_bridge_and_world(sim, writer, bridge_type=None):
    from types import SimpleNamespace
    from chronicler.agent_bridge import AgentBridge
    bridge = (bridge_type or AgentBridge).__new__(bridge_type or AgentBridge)
    bridge._sim, bridge._sidecar, bridge._gini_by_civ = sim, writer, {}
    world = SimpleNamespace(turn=0, civilizations=[SimpleNamespace(name="C0")],
                            regions=[SimpleNamespace(name="R0", controller="C0")])
    return bridge, world


@pytest.mark.parametrize("kind", ["pyarrow", "arro3"])
@pytest.mark.parametrize("count", [0, 4])
def test_needs_private_writer_preserves_all_columns_return_and_float_bits(tmp_path, kind, count):
    import json
    from chronicler.columnar import pylist
    from chronicler.sidecar import SidecarWriter

    batch, _, expected = _needs_real_batch(kind, count=count, diagnostic=True)
    public = SidecarWriter(tmp_path / "public")
    private = SidecarWriter(tmp_path / "private")
    assert public.write_needs_snapshot(turn=0, needs_batch=batch) is None
    data = private._write_needs_snapshot_data(0, batch)
    # Original writer decoding and the bridge's old NumPy route must agree bitwise.
    old_bridge_data = {name: pylist(batch.column(name)) for name in expected}
    assert _needs_value_bits(data) == _needs_value_bits(old_bridge_data)
    assert _needs_value_bits(data) == _needs_value_bits(expected)
    assert list(data) == list(expected) and len(data) == 14
    assert _needs_value_bits(public._needs_rows) == _needs_value_bits(private._needs_rows)
    assert set(public.__dict__) == set(private.__dict__)
    raw = (tmp_path / "public/validation_summary/needs_turn_000.json").read_bytes()
    assert raw == (tmp_path / "private/validation_summary/needs_turn_000.json").read_bytes()
    assert raw == json.dumps({"turn": 0, "columns": expected}, separators=(",", ":")).encode()
    public.close()
    private.close()
    assert {p.relative_to(tmp_path / "public"): p.read_bytes() for p in (tmp_path / "public").rglob("*") if p.is_file()} == {
        p.relative_to(tmp_path / "private"): p.read_bytes() for p in (tmp_path / "private").rglob("*") if p.is_file()}


@pytest.mark.parametrize("kind", ["pyarrow", "arro3"])
def test_needs_foreign_arrow_full_bridge_preserves_getter_and_outputs(tmp_path, kind):
    import json
    from chronicler.agent_bridge import _owns_native_needs_getter
    from chronicler.sidecar import SidecarWriter
    batch, _, expected = _needs_real_batch(kind)
    sim = _NeedsForeignSim(batch)
    writer = SidecarWriter(tmp_path)
    bridge, world = _needs_bridge_and_world(sim, writer)
    bridge._write_sidecar_snapshot(world)
    assert (sim.getter_reads, sim.getter_calls) == (1, 1)
    assert not _owns_native_needs_getter(sim, object())
    assert json.loads((tmp_path / "validation_summary/needs_turn_000.json").read_text())["columns"] == expected
    assert len(writer._needs_rows) == 4 and all(list(row) == ["turn", *expected] for row in writer._needs_rows)
    assert writer._aggregate_by_turn["0"]["civ_0"]["need_means"]["safety"] == 0.4062


@pytest.mark.parametrize("kind", ["pyarrow", "arro3"])
def test_needs_mutable_foreign_buffers_still_decode_after_write(tmp_path, kind):
    import json
    import struct
    from chronicler.sidecar import SidecarWriter
    batch, storage, before = _needs_real_batch(kind, mutable=True)
    writer = SidecarWriter(tmp_path)
    class MutatingRows(list):
        def append(self, row):
            super().append(row)
            if len(self) == 1:
                struct.pack_into("<f", storage["safety"], 0, 0.875)
    writer._needs_rows = MutatingRows()
    bridge, world = _needs_bridge_and_world(_NeedsForeignSim(batch), writer)
    bridge._write_sidecar_snapshot(world)
    # Arrow C exports can hide external mutability: all foreign CData stays legacy.
    assert json.loads((tmp_path / "validation_summary/needs_turn_000.json").read_text())["columns"] == before
    assert writer._needs_rows[0]["safety"] == 0.125
    assert writer._aggregate_by_turn["0"]["civ_0"]["need_means"]["safety"] == 0.5938


@pytest.mark.parametrize("mode", ["subclass", "instance", "class", "private", "private_instance", "bridge_subclass"])
def test_needs_writer_and_bridge_overrides_keep_original_public_call(tmp_path, monkeypatch, mode):
    from types import MethodType
    from chronicler.agent_bridge import AgentBridge
    from chronicler.sidecar import SidecarWriter
    batch, _, _ = _needs_real_batch()
    seen = []
    original = SidecarWriter.write_needs_snapshot
    def observed(self, turn, needs_batch):
        seen.append(needs_batch)
        return original(self, turn, needs_batch)
    class CustomWriter(SidecarWriter):
        write_needs_snapshot = observed
    class CustomBridge(AgentBridge):
        pass
    writer = CustomWriter(tmp_path) if mode == "subclass" else SidecarWriter(tmp_path)
    if mode == "instance": writer.write_needs_snapshot = MethodType(observed, writer)
    elif mode == "class": monkeypatch.setattr(SidecarWriter, "write_needs_snapshot", observed)
    elif mode == "private":
        old_data = SidecarWriter._write_needs_snapshot_data
        def observe_data(self, turn, needs_batch):
            seen.append(needs_batch)
            return old_data(self, turn, needs_batch)
        monkeypatch.setattr(SidecarWriter, "_write_needs_snapshot_data", observe_data)
    elif mode == "private_instance": writer._write_needs_snapshot_data = lambda *a, **k: pytest.fail("new private collision")
    elif mode == "bridge_subclass": writer.write_needs_snapshot = MethodType(observed, writer)
    bridge, world = _needs_bridge_and_world(_NeedsForeignSim(batch), writer,
                                          CustomBridge if mode == "bridge_subclass" else None)
    bridge._write_sidecar_snapshot(world)
    assert seen == ([] if mode in ("private", "private_instance") else [batch])
    assert len(writer._needs_rows) == 4 and writer._aggregate_by_turn["0"]["civ_0"]["agent_count"] == 4


@pytest.mark.parametrize("mode", ["raise", "change"])
def test_needs_stateful_decode_retains_second_decode_failure_boundary(tmp_path, monkeypatch, mode):
    import json
    import chronicler.agent_bridge as module
    from chronicler.sidecar import SidecarWriter
    _, _, first = _needs_real_batch()
    history, logged = [], []
    class Stateful:
        calls = 0
        @property
        def to_pydict(self):
            history.append("get")
            def read():
                history.append("call")
                self.calls += 1
                if self.calls == 2:
                    if mode == "raise": raise ValueError("second decode")
                    return {**first, "safety": [0.875] * 4}
                return first
            return read
    writer = SidecarWriter(tmp_path)
    bridge, world = _needs_bridge_and_world(_NeedsForeignSim(Stateful()), writer)
    monkeypatch.setattr(module.logger, "exception", lambda message: logged.append(message))
    bridge._write_sidecar_snapshot(world)
    assert history == ["get", "get", "call", "get", "get", "call"]
    assert json.loads((tmp_path / "validation_summary/needs_turn_000.json").read_text())["columns"] == first
    assert len(writer._needs_rows) == 4
    aggregate = writer._aggregate_by_turn["0"]["civ_0"]
    if mode == "raise":
        assert logged == ["Sidecar needs snapshot: failed to read/write needs"]
        assert aggregate["need_means"] == {}
    else:
        assert not logged and aggregate["need_means"]["safety"] == 0.875


def test_needs_successful_write_survives_later_aggregate_conversion_error(tmp_path, monkeypatch):
    import chronicler.agent_bridge as module
    from chronicler.sidecar import SidecarWriter
    batch, _, expected = _needs_real_batch()
    class BadSnapshot(_NeedsForeignSim):
        def get_snapshot(self):
            return pa.record_batch({"id": [101], "civ_affinity": [0], "satisfaction": [0.5],
                                    "occupation": [0], "region": ["bad-region"]})
    writer = SidecarWriter(tmp_path)
    bridge, world = _needs_bridge_and_world(BadSnapshot(batch), writer)
    logged = []
    monkeypatch.setattr(module.logger, "exception", lambda message: logged.append(message))
    bridge._write_sidecar_snapshot(world)
    assert (tmp_path / "validation_summary/needs_turn_000.json").is_file()
    assert len(writer._needs_rows) == 4 and list(writer._needs_rows[0]) == ["turn", *expected]
    assert not writer._aggregate_by_turn
    assert logged == ["Sidecar agent aggregate: failed to build/write aggregate snapshot",
                      "Sidecar community summary: failed to build/write summary"]


def test_needs_provenance_rejects_unloaded_and_python_producers_without_import(monkeypatch):
    import sys
    from chronicler.agent_bridge import _owns_native_needs_getter
    sim = _NeedsForeignSim(None)
    getter = sim.get_all_needs
    monkeypatch.delitem(sys.modules, "chronicler_agents.chronicler_agents", raising=False)
    assert not _owns_native_needs_getter(sim, getter)
    assert (sim.getter_reads, sim.getter_calls) == (1, 0)
