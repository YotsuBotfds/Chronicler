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


class _HistogramNumericBatch:
    """Real Arrow numerical views, with observable successful column decodes."""

    def __init__(self, batch, unreadable_count=False):
        self.batch = batch
        self.schema = batch.schema
        self.calls = Counter()
        self.unreadable_count = unreadable_count

    @property
    def num_rows(self):
        if self.unreadable_count:
            raise AssertionError("the vector path must not read declared row metadata")
        return self.batch.num_rows

    def column(self, name):
        column = self.batch.column(name)
        owner = self

        class Column:
            null_count = column.null_count

            def to_numpy(self):
                owner.calls[name] += 1
                return column.to_numpy()

            def to_pylist(self):
                return column.to_pylist()

        return Column()


def _histogram_world(world):
    world = world.model_copy(deep=True)
    for civ in world.civilizations:
        civ.values = ["Order"]
    for region in world.regions:
        region.cultural_identity = "Other"
        region.foreign_control_turns = 4
    return world


def _histogram_demand_world(world, count=10):
    world = _histogram_world(world)
    originals = world.regions
    world.regions = [originals[i % len(originals)].model_copy(
        deep=True, update={"name": f"H{i}"}) for i in range(count)]
    return world


def _histogram_batch(regions, value0, value1=None, value2=None, *, region_type=None, value_type=None):
    count = len(regions)
    return pa.record_batch({
        "region": pa.array(regions, type=region_type or pa.uint16()),
        "cultural_value_0": pa.array(value0, type=value_type or pa.uint8()),
        "cultural_value_1": pa.array(value1 if value1 is not None else [255] * count,
                                      type=value_type or pa.uint8()),
        "cultural_value_2": pa.array(value2 if value2 is not None else [255] * count,
                                      type=value_type or pa.uint8()),
    })


def _histogram_parity(world, batch):
    legacy = world.model_copy(deep=True)
    cached = world.model_copy(deep=True)
    rng = random.getstate()
    tick_cultural_assimilation(legacy, agent_snapshot=batch)
    assert random.getstate() == rng
    tick_cultural_assimilation(cached, agent_snapshot=batch, agent_rows=rows_for(batch))
    assert random.getstate() == rng
    assert cached.model_dump(mode="json") == legacy.model_dump(mode="json")
    assert [r.__pydantic_private__ for r in cached.regions] == [
        r.__pydantic_private__ for r in legacy.regions
    ]
    assert [getattr(r, "_culture_investment_active", False) for r in cached.regions] == [
        getattr(r, "_culture_investment_active", False) for r in legacy.regions
    ]
    assert cached.__pydantic_private__ == legacy.__pydantic_private__
    return cached


def test_assimilation_histogram_counts_agents_not_slots_and_keeps_255_denominator(drift_world):
    world = _histogram_demand_world(drift_world)
    batch = _histogram_batch([8] * 5 + [9] * 5,
        [1, 1, 255, 255, 255, 1, 1, 1, 255, 255],
        [1, 1] + [255] * 8, [1, 1] + [255] * 8)
    result = _histogram_parity(world, batch)
    # The ninth request builds the index: H8 has two holders, not six;
    # H9 reaches the original exact3/5 threshold, including255 in its denominator.
    assert [r.cultural_identity for r in result.regions] == ["Other"] * 9 + ["CivB"]
    assert [event.region for event in result.named_events] == ["H9"]


@pytest.mark.parametrize("region_type,ids", [
    ("signed", [-1, 8, 8, 9, 9, 9, 65535]),
    ("unsigned", [2**64 - 1, 8, 8, 9, 9, 9, 2**63]),
])
def test_assimilation_histogram_filters_ids_before_bounded_cast(drift_world, monkeypatch, region_type, ids):
    import chronicler.culture as culture
    import numpy as np

    world = _histogram_demand_world(drift_world)
    batch = _histogram_batch(ids, [1, 1, 255, 1, 1, 255, 1],
        region_type=pa.int64() if region_type == "signed" else pa.uint64())
    calls = []
    original = np.bincount

    def bounded(values, *, minlength):
        assert values.dtype == np.dtype(np.intp)
        assert minlength == 10
        assert not len(values) or (int(values.min()) >= 0 and int(values.max()) < 10)
        calls.append(len(values))
        return original(values, minlength=minlength)

    monkeypatch.setattr(culture.np, "bincount", bounded)
    result = _histogram_parity(world, batch)
    assert len(calls) == 2  # one denominator, one shared target
    assert [r.cultural_identity for r in result.regions] == ["Other"] * 9 + ["CivB"]


def test_assimilation_histogram_has_one_total_and_at_most_six_target_counts(drift_world, monkeypatch):
    import chronicler.culture as culture
    import numpy as np

    world = _histogram_world(drift_world)
    values = ["Freedom", "Order", "Tradition", "Knowledge", "Honor", "Cunning"]
    world.civilizations = [world.civilizations[0].model_copy(deep=True, update={
        "name": f"C{i}", "values": [value], "regions": [f"H{j}" for j in range(i, 60, 6)]}) for i, value in enumerate(values)]
    world.regions = [world.regions[0].model_copy(deep=True, update={
        "name": f"H{i}", "controller": f"C{i % 6}"}) for i in range(60)]
    batch = _histogram_batch([i for i in range(60) for _ in range(5)],
        [v for i in range(60) for v in (i % 6, i % 6, 255, 255, 255)],
        [v for i in range(60) for v in (i % 6, i % 6, 255, 255, 255)],
        [v for i in range(60) for v in (i % 6, i % 6, 255, 255, 255)])
    original, calls = np.bincount, []

    def counted(ids, *, minlength):
        calls.append(minlength)
        return original(ids, minlength=minlength)

    monkeypatch.setattr(culture.np, "bincount", counted)
    result = _histogram_parity(world, batch)
    assert calls == [60] * 7
    assert [r.cultural_identity for r in result.regions] == ["Other"] * 60


def test_assimilation_histogram_reuses_numeric_columns_and_does_not_read_row_count(drift_world):
    world = _histogram_world(drift_world)
    batch = _histogram_batch([0, 0, 1, 1], [1, 255, 1, 1])
    legacy_batch = _HistogramNumericBatch(batch, unreadable_count=True)
    cached_batch = _HistogramNumericBatch(batch, unreadable_count=True)
    legacy = world.model_copy(deep=True)
    tick_cultural_assimilation(legacy, agent_snapshot=legacy_batch)
    tick_cultural_assimilation(world, agent_snapshot=cached_batch, agent_rows=rows_for(cached_batch))
    assert world.model_dump(mode="json") == legacy.model_dump(mode="json")
    names = ("region", "cultural_value_0", "cultural_value_1", "cultural_value_2")
    assert cached_batch.calls == dict.fromkeys(names, 1)
    assert legacy_batch.calls == dict.fromkeys(names, 2)


@pytest.mark.parametrize("kind", ["float-regions", "float-values", "null-values", "boolean-values"])
def test_assimilation_histogram_preserves_noninteger_and_null_fallback(drift_world, monkeypatch, kind):
    import chronicler.culture as culture

    def no_histogram(*args, **kwargs):
        raise AssertionError("unsupported columns must retain the old path")

    monkeypatch.setattr(culture.np, "bincount", no_histogram)
    if kind == "float-regions":
        batch = _histogram_batch([0.0, 0.5, 1.0, 1.5], [1, 1, 1, 255], region_type=pa.float64())
    elif kind == "float-values":
        batch = _histogram_batch([0, 0, 1, 1], [1.0, float("nan"), 1.0, 255.0],
            [255.0] * 4, [255.0] * 4, value_type=pa.float64())
    elif kind == "null-values":
        batch = _histogram_batch([0, 0, 1, 1], [1, None, 1, 1])
    else:
        batch = _histogram_batch([0, 0, 1, 1], [True, False, True, True],
            [False] * 4, [False] * 4, value_type=pa.bool_())
    _histogram_parity(_histogram_demand_world(drift_world), batch)


def test_assimilation_histogram_empty_rows_keep_timer_fallback(drift_world):
    world = _histogram_world(drift_world)
    world.regions[0].foreign_control_turns = 14
    batch = _histogram_batch([], [])
    result = _histogram_parity(world, batch)
    assert [r.cultural_identity for r in result.regions] == ["CivA", "Other"]
    assert [r.foreign_control_turns for r in result.regions] == [0, 5]


def test_assimilation_histogram_keeps_invalid_primary_column_demand(drift_world, monkeypatch):
    import chronicler.culture as culture

    world = _histogram_world(drift_world)
    for civ in world.civilizations:
        civ.values = ["Trade"]  # not in VALUE_TO_ID, but arrays are still requested
    probe = _HistogramNumericBatch(_histogram_batch([0, 1], [1, 1]))
    monkeypatch.setattr(culture.np, "bincount", lambda *a, **k: pytest.fail("invalid target histogram"))
    tick_cultural_assimilation(world, agent_snapshot=probe, agent_rows=rows_for(probe))
    assert set(probe.calls.values()) == {1} and len(probe.calls) == 4
    assert all(r.foreign_control_turns == 5 and r._culture_investment_active for r in world.regions)


def test_assimilation_histogram_is_call_local_and_tracks_new_primary_values(drift_world):
    world = _histogram_demand_world(drift_world)
    batch = _histogram_batch([8, 8, 9, 9], [0, 0, 1, 1])
    rows = rows_for(batch)
    tick_cultural_assimilation(world, agent_snapshot=batch, agent_rows=rows)
    for civ in world.civilizations:
        civ.values = ["Freedom"]
    for region in world.regions:
        region.cultural_identity, region.foreign_control_turns = "Other", 4
    expected = world.model_copy(deep=True)
    tick_cultural_assimilation(expected, agent_snapshot=batch)
    tick_cultural_assimilation(world, agent_snapshot=batch, agent_rows=rows)
    assert world.model_dump(mode="json") == expected.model_dump(mode="json")
    assert [r.cultural_identity for r in world.regions] == ["Other"] * 8 + ["CivA", "Other"]


@pytest.mark.parametrize("kind", ["broadcast", "mismatched", "rank-two"])
def test_assimilation_histogram_keeps_malformed_cached_array_behavior(drift_world, monkeypatch, kind):
    import chronicler.culture as culture
    import numpy as np
    from types import SimpleNamespace

    values = {
        "region": np.array([0, 0, 1, 1], dtype=np.int64),
        "cultural_value_0": np.array([1], dtype=np.uint8),
        "cultural_value_1": np.array([255], dtype=np.uint8),
        "cultural_value_2": np.array([255], dtype=np.uint8),
    }
    if kind == "mismatched":
        for name in tuple(values)[1:]:
            values[name] = np.repeat(values[name], 3)
    elif kind == "rank-two":
        for name in tuple(values)[1:]:
            values[name] = np.repeat(values[name], 4).reshape(4, 1)

    class Batch:
        schema = SimpleNamespace(names=tuple(values))
        num_rows = 4

        def column(self, name):
            class Column:
                null_count = 0

                def to_numpy(self):
                    return values[name]

                def to_pylist(self):
                    return values[name].tolist()

            return Column()

    monkeypatch.setattr(culture.np, "bincount", lambda *a, **k: pytest.fail("malformed histogram"))
    world, batch = _histogram_world(drift_world), Batch()
    if kind == "mismatched":
        with pytest.raises(ValueError):
            tick_cultural_assimilation(world, agent_snapshot=batch, agent_rows=rows_for(batch))
        assert [r.foreign_control_turns for r in world.regions] == [5, 4]
        assert [getattr(r, "_culture_investment_active", False) for r in world.regions] == [True, False]
        assert not world.named_events
    else:
        tick_cultural_assimilation(world, agent_snapshot=batch, agent_rows=rows_for(batch))
        expected = ["CivA", "CivB"] if kind == "broadcast" else ["Other", "Other"]
        assert [r.cultural_identity for r in world.regions] == expected


@pytest.mark.parametrize("requests", [1, 2, 8])
def test_assimilation_demand_first_eight_requests_do_not_build(drift_world, monkeypatch, requests):
    import chronicler.culture as culture

    world = _histogram_demand_world(drift_world, requests)
    batch = _histogram_batch([i for i in range(requests) for _ in range(5)],
        [v for _ in range(requests) for v in (1, 1, 1, 255, 255)])
    monkeypatch.setattr(culture.np, "bincount", lambda *a, **k: pytest.fail("low-demand index allocation"))
    result = _histogram_parity(world, batch)
    assert all(r.cultural_identity == r.controller for r in result.regions)


@pytest.mark.parametrize("requests", [9, 10])
def test_assimilation_demand_builds_once_on_ninth_request(drift_world, monkeypatch, requests):
    import chronicler.culture as culture
    import numpy as np

    world = _histogram_demand_world(drift_world, requests)
    batch = _histogram_batch([i for i in range(requests) for _ in range(5)],
        [v for _ in range(requests) for v in (1, 1, 1, 255, 255)])
    original, calls = np.bincount, []

    def counted(ids, *, minlength):
        calls.append(minlength)
        return original(ids, minlength=minlength)

    monkeypatch.setattr(culture.np, "bincount", counted)
    result = _histogram_parity(world, batch)
    assert calls == [requests, requests]
    assert all(r.cultural_identity == r.controller for r in result.regions)


@pytest.mark.parametrize("second_requests", [1, 2, 8, 9])
def test_assimilation_demand_each_target_has_its_own_eight_scans(drift_world, monkeypatch, second_requests):
    import chronicler.culture as culture
    import numpy as np

    count = 9 + second_requests
    world = _histogram_demand_world(drift_world, count)
    world.civilizations[1].values = ["Freedom"]
    for i, region in enumerate(world.regions):
        region.controller = world.civilizations[0 if i < 9 else 1].name
    batch = _histogram_batch([i for i in range(count) for _ in range(5)],
        [v for i in range(count) for v in ((1 if i < 9 else 0),) * 3 + (255, 255)])
    original, calls = np.bincount, []

    def counted(ids, *, minlength):
        calls.append(minlength)
        return original(ids, minlength=minlength)

    monkeypatch.setattr(culture.np, "bincount", counted)
    result = _histogram_parity(world, batch)
    assert calls == [count] * (3 if second_requests == 9 else 2)
    assert all(r.cultural_identity == r.controller for r in result.regions)


def test_assimilation_demand_counts_only_after_original_gates(drift_world, monkeypatch):
    import chronicler.culture as culture
    import numpy as np

    world = _histogram_demand_world(drift_world, 13)
    world.regions[8].controller = None
    world.regions[9].cultural_identity = world.regions[9].controller
    world.regions[10].foreign_control_turns = 0
    invalid = world.civilizations[0].model_copy(deep=True, update={"name": "Invalid", "values": ["Trade"]})
    world.civilizations.append(invalid)
    world.regions[11].controller = "Invalid"
    batch = _histogram_batch([12] * 5, [1, 1, 1, 255, 255])
    expected = world.model_copy(deep=True)
    tick_cultural_assimilation(expected, agent_snapshot=batch)
    original, calls = np.bincount, []

    def counted(ids, *, minlength):
        assert world.regions[12]._culture_investment_active
        assert world.regions[10].foreign_control_turns == 1
        assert world.regions[11]._culture_investment_active
        calls.append(minlength)
        return original(ids, minlength=minlength)

    monkeypatch.setattr(culture.np, "bincount", counted)
    tick_cultural_assimilation(world, agent_snapshot=batch, agent_rows=rows_for(batch))
    assert calls == [13, 13]
    assert world.model_dump(mode="json") == expected.model_dump(mode="json")
    assert world.__pydantic_private__ == expected.__pydantic_private__
    assert [r.__pydantic_private__ for r in world.regions] == [r.__pydantic_private__ for r in expected.regions]


def test_assimilation_demand_numeric_columns_decode_once_after_build(drift_world):
    world = _histogram_demand_world(drift_world)
    batch = _histogram_batch([8, 8, 9, 9], [1, 255, 1, 1])
    legacy_batch = _HistogramNumericBatch(batch, unreadable_count=True)
    cached_batch = _HistogramNumericBatch(batch, unreadable_count=True)
    expected = world.model_copy(deep=True)
    tick_cultural_assimilation(expected, agent_snapshot=legacy_batch)
    tick_cultural_assimilation(world, agent_snapshot=cached_batch, agent_rows=rows_for(cached_batch))
    assert world.model_dump(mode="json") == expected.model_dump(mode="json")
    names = ("region", "cultural_value_0", "cultural_value_1", "cultural_value_2")
    assert cached_batch.calls == dict.fromkeys(names, 1)
    assert legacy_batch.calls == dict.fromkeys(names, 10)
