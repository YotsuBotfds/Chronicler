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


# Religion reuse is a derived-count cache, separate from the existing column cache.
def _faith_batch(kind="pyarrow"):
    batch = consumer_batch()
    if kind == "arro3":
        from arro3.core import RecordBatch
        batch = RecordBatch.from_arrow(batch)
    return batch


def _faith_chain_state(batch, rows=None):
    from copy import deepcopy

    regions, civs, beliefs = religion_inputs()
    kw = {"agent_rows": rows} if rows is not None else {}
    seen = set()
    rng = random.getstate()
    before = pa.record_batch(batch).to_pydict()
    majority = compute_majority_belief(batch, **kw)
    persecution = compute_persecution(regions, civs, beliefs, batch, 7, seen, **kw)
    schisms = detect_schisms(regions, civs, beliefs, batch, 7, **kw)
    assert random.getstate() == rng
    assert pa.record_batch(batch).to_pydict() == before
    return (list(majority.items()), [e.model_dump(mode="json") for e in persecution + schisms],
            deepcopy([(m.model_dump(mode="json"), m.__pydantic_private__)
                      for m in [*regions, *civs, *beliefs]]), seen)


@pytest.mark.parametrize("kind", ["pyarrow", "arro3"])
def test_religion_counts_reused_by_all_three_actual_consumers(kind, monkeypatch):
    import chronicler.turn_artifacts as artifacts

    batch = _faith_batch(kind)
    expected = _faith_chain_state(batch)
    original, calls = artifacts.ordered_counts, []

    def grouped(keys, values):
        calls.append((keys.tolist(), values.tolist()))
        return original(keys, values)

    monkeypatch.setattr(artifacts, "ordered_counts", grouped)
    rows = rows_for(batch, 7)
    actual = _faith_chain_state(batch, rows)
    assert actual == expected
    assert len(calls) == 1
    assert [e["event_type"] for e in actual[1]] == ["Persecution", "Mass Migration", "Schism"]
    # Reusing snapshot counts must not freeze the ruler's live faith/policy.
    regions, civs, beliefs = religion_inputs()
    compute_persecution(regions, civs, beliefs, batch, 7, set(), agent_rows=rows)
    assert any(r.persecution_intensity > 0 for r in regions)
    civs[0].civ_majority_faith = 1  # this existing faith is peaceful
    expected_regions = [r.model_copy(deep=True) for r in regions]
    expected_events = compute_persecution(expected_regions, civs, beliefs, batch, 7, set())
    actual_events = compute_persecution(regions, civs, beliefs, batch, 7, set(), agent_rows=rows)
    assert [e.model_dump() for e in actual_events] == [e.model_dump() for e in expected_events]
    assert [r.model_dump() for r in regions] == [r.model_dump() for r in expected_regions]
    assert all(r.persecution_intensity == 0 and r.persecuting_faith is None for r in regions)
    assert len(calls) == 1


@pytest.mark.parametrize("kind", ["pyarrow", "arro3"])
def test_religion_counts_filter_before_grouping_and_return_private_counters(kind, monkeypatch):
    from collections import Counter
    import chronicler.religion as religion
    import chronicler.turn_artifacts as artifacts
    from chronicler.columnar import ordered_counts

    batch = pa.record_batch({"region": [0, 1, 0, 1, 1, 0],
                             "belief": [255, 2, 1, 0, 2, 0]})
    if kind == "arro3":
        from arro3.core import RecordBatch
        batch = RecordBatch.from_arrow(batch)
    rows = rows_for(batch, 7)
    original, calls = artifacts.ordered_counts, []

    def grouped(keys, values):
        calls.append(True)
        return original(keys, values)

    monkeypatch.setattr(artifacts, "ordered_counts", grouped)
    first = religion._faith_counts_by(batch, rows, "region")
    assert list(first) == [1, 0]
    assert list(first[1].items()) == [(2, 2), (0, 1)]
    assert list(first[0].items()) == [(1, 1), (0, 1)]
    # Full255-inclusive counts have a different outer order and remain separate.
    full = ordered_counts(*rows.arrays("region", "belief"))
    assert list(full) == [0, 1] and list(full[0]) == [255, 1, 0]
    first[1].clear()
    first[0][1] = 999
    first[7] = Counter({7: 7})
    again = religion._faith_counts_by(batch, rows, "region")
    assert list(again) == [1, 0] and list(again[1].items()) == [(2, 2), (0, 1)]
    assert list(again[0].items()) == [(1, 1), (0, 1)]
    third = religion._faith_counts_by(batch, rows, "region")
    assert third == again and third is not again and third[1] is not again[1]
    assert compute_majority_belief(batch, agent_rows=rows) == {1: 2, 0: 0}
    assert len(calls) == 1


def test_religion_region_counts_do_not_reuse_civ_key_or_other_view(monkeypatch):
    import chronicler.religion as religion
    import chronicler.turn_artifacts as artifacts

    batch = pa.record_batch({"region": [0, 1, 0], "civ_affinity": [4, 4, 3], "belief": [255, 2, 1]})
    rows = rows_for(batch, 7)
    original, calls = artifacts.ordered_counts, []

    def grouped(keys, values):
        calls.append(True)
        return original(keys, values)

    monkeypatch.setattr(artifacts, "ordered_counts", grouped)
    assert list(religion._faith_counts_by(batch, rows, "region")) == [1, 0]
    assert list(religion._faith_counts_by(batch, rows, "civ_affinity")) == [4, 3]
    assert list(religion._faith_counts_by(batch, rows_for(batch, 8), "region")) == [1, 0]
    assert len(calls) == 2  # separate view/stamp, not a global batch memo


@pytest.mark.parametrize("mismatch", ["batch", "persecution-turn", "schism-turn"])
def test_religion_warm_summary_does_not_bypass_identity_checks(mismatch, monkeypatch):
    import chronicler.turn_artifacts as artifacts

    batch = _faith_batch()
    rows = rows_for(batch, 7)
    compute_majority_belief(batch, agent_rows=rows)
    monkeypatch.setattr(artifacts, "ordered_counts", lambda *a: pytest.fail("identity failure grouped"))
    regions, civs, beliefs = religion_inputs()
    before = [r.model_dump() for r in regions]
    with pytest.raises(ValueError):
        if mismatch == "batch":
            compute_majority_belief(_faith_batch(), agent_rows=rows)
        elif mismatch == "persecution-turn":
            compute_persecution(regions, civs, beliefs, batch, 8, set(), agent_rows=rows)
        else:
            detect_schisms(regions, civs, beliefs, batch, 8, agent_rows=rows)
    assert [r.model_dump() for r in regions] == before


@pytest.mark.parametrize("kind", ["float", "boolean", "null"])
def test_religion_unsupported_arrays_keep_original_uncached_fallback(kind, monkeypatch):
    import chronicler.turn_artifacts as artifacts

    values = ([1.0, 1.0, 2.0] if kind == "float" else
              [True, True, False] if kind == "boolean" else [None, 1, 1])
    batch = pa.record_batch({"region": [0, 0, 0], "belief": values})
    expected = compute_majority_belief(batch)
    rows = rows_for(batch)
    original, calls = artifacts.ordered_counts, []

    def grouped(keys, values):
        calls.append(True)
        return original(keys, values)

    monkeypatch.setattr(artifacts, "ordered_counts", grouped)
    assert compute_majority_belief(batch, agent_rows=rows) == expected
    assert compute_majority_belief(batch, agent_rows=rows) == expected
    # This PyArrow bit-packed bool column cannot expose a zero-copy NumPy view.
    # Like nulls, it retains the original scalar fallback and makes no groups.
    assert len(calls) == (0 if kind in ("boolean", "null") else 2)


class _FaithMutableBatch:
    def __init__(self):
        from types import SimpleNamespace
        import numpy as np
        self.values = {"region": np.array([0, 0, 0], dtype=np.uint16),
                       "belief": np.array([1, 1, 2], dtype=np.uint8)}
        self.schema = SimpleNamespace(names=tuple(self.values))
        self.num_rows = 3

    def column(self, name):
        values = self.values[name]

        class Column:
            null_count = 0

            def to_numpy(self):
                # A readonly decoded view does not freeze the external owner.
                return values.view()

            def to_pylist(self):
                return values.tolist()

        return Column()


def test_religion_numeric_duck_batch_recomputes_after_external_alias_change():
    batch = _FaithMutableBatch()
    rows = rows_for(batch)
    assert compute_majority_belief(batch, agent_rows=rows) == {0: 1}
    batch.values["belief"][:2] = 2
    assert compute_majority_belief(batch, agent_rows=rows) == {0: 2}
    assert compute_majority_belief(batch) == {0: 2}


@pytest.mark.parametrize("kind", ["python", "borrowed-C"])
def test_religion_arrow_name_spoofs_and_borrowed_descriptors_fall_back(kind):
    import chronicler.turn_artifacts as artifacts
    from arro3.core import RecordBatch as ArrowRecordBatch

    class RecordBatch:
        __module__ = "arro3.core._core"
        __arrow_c_array__ = ArrowRecordBatch.__arrow_c_array__
        column = ArrowRecordBatch.column

        def __init__(self, inner):
            self.inner = inner

        def __getattribute__(self, name):
            if name in ("column", "schema", "num_rows"):
                return getattr(object.__getattribute__(self, "inner"), name)
            return object.__getattribute__(self, name)

    if kind == "python":
        def no_export(self, *args):
            raise AssertionError("fallback must not invoke an exporter")
        RecordBatch.__arrow_c_array__ = no_export
    inner = _FaithMutableBatch()
    batch = RecordBatch(inner)
    assert not artifacts._immutable_record_batch(batch)
    rows = rows_for(batch)
    assert compute_majority_belief(batch, agent_rows=rows) == {0: 1}
    inner.values["belief"][:2] = 2
    assert compute_majority_belief(batch, agent_rows=rows) == {0: 2}


def test_religion_exact_view_subclass_keeps_original_grouping(monkeypatch):
    import chronicler.religion as religion
    import chronicler.turn_artifacts as artifacts

    class DerivedRows(AgentRows):
        pass

    batch = _faith_batch()
    rows = DerivedRows(Stamp(7, "phase10_entry"), batch)
    original, calls = religion.ordered_counts, []

    def grouped(keys, values):
        calls.append(True)
        return original(keys, values)

    monkeypatch.setattr(religion, "ordered_counts", grouped)
    monkeypatch.setattr(artifacts, "ordered_counts", lambda *a: pytest.fail("subclass retained summary"))
    first = religion.compute_majority_belief(batch, agent_rows=rows)
    assert religion.compute_majority_belief(batch, agent_rows=rows) == first
    assert len(calls) == 2


def test_religion_failed_grouping_is_retried_without_retaining_partial_summary(monkeypatch):
    import chronicler.turn_artifacts as artifacts

    batch = _faith_batch()
    rows = rows_for(batch)
    original, calls = artifacts.ordered_counts, []

    def grouped(keys, values):
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError("injected grouping failure")
        return original(keys, values)

    monkeypatch.setattr(artifacts, "ordered_counts", grouped)
    with pytest.raises(RuntimeError, match="injected grouping failure"):
        compute_majority_belief(batch, agent_rows=rows)
    assert compute_majority_belief(batch, agent_rows=rows) == {0: 0, 1: 0}
    assert compute_majority_belief(batch, agent_rows=rows) == {0: 0, 1: 0}
    assert len(calls) == 2


def test_religion_original_empty_capacity_and_missing_gates_remain_lazy(monkeypatch):
    import chronicler.turn_artifacts as artifacts

    missing = CountingBatch(consumer_batch().select(["id"]))
    monkeypatch.setattr(artifacts, "ordered_counts", lambda *a: pytest.fail("gate grouped"))
    assert detect_schisms([], [], [None] * MAX_FAITHS, missing, 7, agent_rows=rows_for(missing, 7)) == []
    assert not missing.accesses
    empty = pa.record_batch({"region": pa.array([], type=pa.uint16())})
    assert compute_majority_belief(empty, agent_rows=rows_for(empty)) == {}
    assert compute_persecution([], [], [], empty, 7, set(), agent_rows=rows_for(empty, 7)) == []
    with pytest.raises(KeyError):
        compute_majority_belief(missing, agent_rows=rows_for(missing))


def test_religion_all_255_keeps_an_empty_successful_summary(monkeypatch):
    import chronicler.religion as religion
    import chronicler.turn_artifacts as artifacts

    batch = pa.record_batch({"region": [0, 1, 0], "belief": [255, 255, 255]})
    rows = rows_for(batch)
    original, calls = artifacts.ordered_counts, []

    def grouped(keys, values):
        calls.append(True)
        return original(keys, values)

    monkeypatch.setattr(artifacts, "ordered_counts", grouped)
    assert religion._faith_counts_by(batch, rows, "region") == {}
    assert religion._faith_counts_by(batch, rows, "region") == {}
    assert len(calls) == 1
